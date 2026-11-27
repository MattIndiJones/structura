"""Native Valo Explain gates, paired estimators and deterministic pricing witnesses."""

from datetime import datetime
from math import sqrt
from statistics import mean

import pytest
from scipy.stats import t

from backend.app.core.product.credit_default import price_credit_default
from backend.app.core.product.exotic_valuation_explain import (
    ExplainCash, ExplainIdentity, ExplainMarket, ExplainPrice, ExplainSample, ExplainScenario, ExplainSnapshot,
    credit_default_explain_observation, explain_valuations, rates_explain_observation,
)
from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.rates_pricing import price_rates
from backend.app.services import native_valuation_explain
from backend.tests.test_rates_credit_default import _prepare as prepare_july
from backend.tests.test_rates_credit_default import cds_terms, cln_terms, credit_products, facts, july_facts  # noqa: F401
from backend.tests.test_rates_credit_rates_market import abc_products, market_for  # noqa: F401
from backend.tests.test_rates_credit_rates_schedule import abc_reference, abc_terms  # noqa: F401


_IDENTITY = ExplainIdentity(
    position_id="quote-1", terms_version=1, terms_fingerprint="terms", schedule_fingerprint="schedule", nominal_eur=1_000_000,
    side="BUY", value_date_convention="valuation_day", model="deterministic", engine_version="v1", engine_fingerprint="sha",
)
_CUTOFF = datetime.fromisoformat("2021-07-20T15:00:00+02:00")


def _snapshot(archive_id, market, price, *, cutoff=_CUTOFF, cash=(), identity=_IDENTITY, state=None):
    return ExplainSnapshot(
        archive_id=archive_id, identity=identity, price=price,
        scenario=ExplainScenario(cutoff=cutoff, value_date=cutoff.date(), market=market, cash=cash, state=state or {}),
    )


def _market_price(scenario):
    values = {name: item["pv"] for name, item in scenario.market.model_dump().items() if item is not None}
    dirty = sum(values.values()) + values.get("ois", 0) * values.get("credit_quotes", 0)
    return ExplainPrice(economic_dirty_pv_eur=dirty)


def test_market_order_allocates_interaction_and_rebootstrap_only_when_declared():
    first_market = ExplainMarket(ois={"pv": 1}, credit_quotes={"pv": 2}, calibration_recovery={"pv": 3})
    second_market = ExplainMarket(ois={"pv": 2}, projection_basis={"pv": 4}, credit_quotes={"pv": 5},
                                  calibration_recovery={"pv": 6}, funding={"pv": 7}, volatility={"pv": 8}, dependence={"pv": 9})
    first = _snapshot("first", first_market, ExplainPrice(economic_dirty_pv_eur=8))
    second = _snapshot("second", second_market, ExplainPrice(economic_dirty_pv_eur=51))
    observed = explain_valuations(first, second, price=_market_price)
    assert observed.status == "attributed"
    assert all(not step.credit_rebootstrap for step in observed.effects)
    result = explain_valuations(first, second, price=_market_price, credit_rebootstrap=True)
    assert [step.factor for step in result.effects] == [
        "ois", "projection_basis", "credit_quotes", "calibration_recovery", "funding", "volatility", "dependence",
    ]
    assert [step.delta_eur for step in result.effects] == [3, 4, 9, 3, 7, 8, 9]
    assert [step.factor for step in result.effects if step.credit_rebootstrap] == ["ois", "credit_quotes", "calibration_recovery"]
    assert result.residual_eur == 0
    assert result.observed_dirty_change_eur == result.contractual_pnl_eur == 43


def test_paired_path_differences_use_their_own_error_and_keep_unresolved_effects():
    first, second = (98, 100, 102, 100), (99, 100, 103, 100)
    identity = _IDENTITY.model_copy(update={"numerical_protocol": "pseudorandom-independent-units"})

    def price(scenario):
        units = second if scenario.market.ois.to_dict()["bump"] else first
        return ExplainPrice(economic_dirty_pv_eur=mean(units),
                            sample=ExplainSample(pairing_key="grid-factors-seed-order", independent_units=units))

    start = _snapshot("first", ExplainMarket(ois={"bump": False}), ExplainPrice(economic_dirty_pv_eur=100), identity=identity)
    end = _snapshot("second", ExplainMarket(ois={"bump": True}), ExplainPrice(economic_dirty_pv_eur=100.5), identity=identity)
    result = explain_valuations(start, end, price=price)
    expected_se = sqrt(1 / 3) / 2
    interval = result.effects[0].interval
    assert result.status == "attributed" and result.interval == interval
    assert interval.independent_units == 4
    assert interval.standard_error_eur == pytest.approx(expected_se)
    assert interval.half_width_95_eur == pytest.approx(t.ppf(.975, 3) * expected_se)
    assert interval.low_95_eur < 0 < interval.high_95_eur and not interval.resolved

    def moved_grid(scenario):
        priced = price(scenario)
        sample = priced.sample.model_copy(update={"pairing_key": str(scenario.market.ois)})
        return priced.model_copy(update={"sample": sample})

    unavailable = explain_valuations(start, end, price=moved_grid)
    assert unavailable.status == "observed" and unavailable.reason_code == "EXPLAIN_MC_PAIRING"
    assert unavailable.observed_dirty_change_eur == .5 and unavailable.effects == ()


@pytest.mark.parametrize(("changed", "expected"), [
    ({"terms_version": 2}, "EXPLAIN_TERMS"),
    ({"schedule_fingerprint": "changed"}, "EXPLAIN_SCHEDULE"),
    ({"side": "SELL"}, "EXPLAIN_POSITION"),
    ({"value_date_convention": "trade-plus-two"}, "EXPLAIN_VALUE_CONVENTION"),
    ({"engine_fingerprint": "changed"}, "EXPLAIN_ENGINE"),
    ({"model": "hull-white-v2"}, "EXPLAIN_MODEL"),
    ({"numerical_protocol": "different"}, "EXPLAIN_NUMERICAL_PROTOCOL"),
    ({"exercise_policy": "frozen", "exercise_policy_fingerprint": "learned-rule"}, "EXPLAIN_EXERCISE"),
])
def test_rejects_incompatible_archives_before_repricing(changed, expected):
    start = _snapshot("first", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=100))
    identity = start.identity.model_copy(update=changed)
    end = _snapshot("second", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=110), identity=identity)

    def price(_):
        pytest.fail("Incompatible archives must not enter a causal repricing.")

    result = explain_valuations(start, end, price=price)
    assert result.status == "observed" and result.reason_code == expected
    assert result.observed_dirty_change_eur == 10 and result.effects == () and result.interval is None


def test_replay_tolerance_scales_with_nominal_and_cannot_be_hidden_in_residual():
    start = _snapshot("first", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=100))
    end = _snapshot("second", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=100.001))
    result = explain_valuations(start, end, price=lambda _: start.price)
    assert result.status == "observed" and result.reason_code == "EXPLAIN_REPLAY"
    assert result.end_replay_error_eur == pytest.approx(-.001)
    assert result.residual_eur is None


def test_cutoffs_cash_recognition_and_reverse_attribution_are_directional():
    before = _CUTOFF.replace(hour=14, minute=59)
    late = ExplainCash(flow_id="late", fact_id="settlement-v1", version=1, amount_eur=-35,
                       effect_date=_CUTOFF.date().replace(day=19), available_at=_CUTOFF, validated_at=_CUTOFF)
    first = _snapshot("first", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=-34.75), cutoff=before)
    second = _snapshot("second", ExplainMarket(), ExplainPrice(economic_dirty_pv_eur=0), cash=(late,))

    def price(scenario):
        return second.price if scenario.cash else first.price

    forward = explain_valuations(first, second, price=price, roll_market=lambda first, _: first.market)
    reverse = explain_valuations(second, first, price=price, roll_market=lambda first, _: first.market)
    assert forward.effects[0].factor == "time_state"
    assert forward.observed_dirty_change_eur == 34.75
    assert forward.cash[0].recognized_at == _CUTOFF
    assert forward.cash_contractual_eur == -35
    assert forward.contractual_pnl_eur == -.25
    assert reverse.contractual_pnl_eur == .25 and reverse.cash_contractual_eur == 35
    assert reverse.effects[0].delta_eur == -forward.effects[0].delta_eur


@pytest.mark.parametrize(("instrument", "dirty", "cash", "pnl"), [
    (0, -6763.54, 10363.89, 3600.35),
    (1, 7010.53, -7836.11, -825.58),
])
def test_real_frozen_frn_and_irs_time_and_payment(abc_reference, abc_products, market_for, instrument, dirty, cash, pnl):
    product = abc_products[instrument]
    contexts = {}
    snapshots = []
    for case in ("B", "C"):
        market = market_for(case)
        cutoff = datetime.fromisoformat(abc_reference["snapshots"][case]["cutoff_local"])
        context = prepare_native_context(product, valuation_date=market.market_date, cutoff=cutoff, market=market)
        contexts[context.fingerprint] = context
        result = price_rates(product, context)
        price, payments = rates_explain_observation(result, context)
        identity = _IDENTITY.model_copy(update={"terms_fingerprint": result.terms_fingerprint,
                                               "schedule_fingerprint": result.schedule_fingerprint,
                                               "engine_version": result.engine_version})
        snapshots.append(_snapshot(case, ExplainMarket(ois=context.market.discount.model_dump(mode="json"),
                                                       projection_basis=context.market.projection.model_dump(mode="json")),
                                   price, identity=identity, cutoff=cutoff, cash=payments,
                                   state={"context": context.fingerprint}))

    def price(scenario):
        context = contexts[scenario.state.to_dict()["context"]]
        return rates_explain_observation(price_rates(product, context), context)[0]

    result = explain_valuations(*snapshots, price=price, roll_market=lambda _, target: target.market,
                                roll_convention="flat_curves_same_rates")
    assert result.status == "attributed"
    assert result.observed_dirty_change_eur == pytest.approx(dirty, abs=.01)
    assert result.cash_contractual_eur == pytest.approx(cash, abs=.01)
    assert result.contractual_pnl_eur == pytest.approx(pnl, abs=.01)
    assert len(result.effects) == 1 and result.effects[0].factor == "time_state"
    if instrument == 0:
        assert result.observed_dirty_change_eur == pytest.approx(result.clean_change_eur + result.accrued_change_eur)


def test_real_cln_claim_rolls_to_cash_and_pending_keeps_its_status(credit_products, facts):
    product = credit_products["CLN"]
    contexts = {}
    snapshots = []
    for day, hour in ((15, 16), (19, 16), (20, 14), (20, 16)):
        cutoff = _CUTOFF.replace(day=day, hour=hour)
        context = prepare_july(product, cutoff, facts)
        contexts[context.fingerprint] = context
        result = price_credit_default(product, context)
        price, cash = credit_default_explain_observation(result, context)
        snapshots.append(_snapshot(f"{day}-{hour}", ExplainMarket(ois={"rate": .02}), price, cutoff=cutoff, cash=cash,
                                   state={"context": context.fingerprint}))

    def price(scenario):
        context = contexts[scenario.state.to_dict()["context"]]
        return credit_default_explain_observation(price_credit_default(product, context), context)[0]

    pending, previous, due, paid = snapshots
    cutoff_roll = lambda start, _: start.market
    compare = explain_valuations(previous, paid, price=price, roll_market=cutoff_roll)
    assert compare.observed_dirty_change_eur == pytest.approx(-349980.82, abs=.01)
    assert compare.cash_contractual_eur == 350000
    assert compare.contractual_pnl_eur == pytest.approx(19.18, abs=.01)
    same_day = explain_valuations(due, paid, price=price, roll_market=cutoff_roll)
    assert same_day.observed_dirty_change_eur == -350000
    assert same_day.contractual_pnl_eur == 0
    incomplete = explain_valuations(pending, paid, price=price, roll_market=cutoff_roll)
    assert incomplete.status == "pending" and incomplete.reason_code == "EXPLAIN_RECOVERY_PENDING"
    assert incomplete.observed_dirty_change_eur is None and incomplete.contractual_pnl_eur is None


def test_legacy_rate_receipts_retain_observed_amounts_without_repricing(abc_reference, abc_products, market_for, monkeypatch):
    product = abc_products[0]
    receipts = []
    for case in ("B", "C"):
        market = market_for(case)
        cutoff = datetime.fromisoformat(abc_reference["snapshots"][case]["cutoff_local"])
        context = prepare_native_context(product, valuation_date=market.market_date, cutoff=cutoff, market=market)
        priced = price_rates(product, context)
        receipts.append({
            "user_id": 1, "product_reference": product.reference, "input_revision": product.revision,
            "terms": product.terms.model_dump(mode="json"), "schedule": product.native_schedule.model_dump(mode="json"),
            "context": context.model_dump(mode="json"), "result": priced.model_dump(mode="json"), "script": None,
        })

    def price(*args, **kwargs):
        pytest.fail("A legacy receipt without engine identity cannot be repriced as qualified.")

    monkeypatch.setattr(native_valuation_explain, "price_rates", price)
    explanation = native_valuation_explain.explain_native_calculations(*receipts)
    assert explanation.status == "observed" and explanation.reason_code == "EXPLAIN_ENGINE"
    assert explanation.observed_dirty_change_eur == pytest.approx(-6763.54, abs=.01)
    assert explanation.cash_contractual_eur == pytest.approx(10363.89, abs=.01)
    assert explanation.effects == ()
