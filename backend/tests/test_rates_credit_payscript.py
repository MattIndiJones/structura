"""Deterministic rate scripts reuse the contractual and market flows of the templates."""

from datetime import datetime
from math import exp

import pytest

from backend.app.core.payscript.parser import parse_script, script_source_hash
from backend.app.core.product.models import Product
from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_market import RatesMarket, RatesMarketError
from backend.app.core.product.rates_payscript import (
    FRN_RATES_PAYSCRIPT, IRS_RATES_PAYSCRIPT, RATES_PAYSCRIPT_PROFILE, compile_rates_payscript, rates_payoff,
)
from backend.app.core.product.rates_pricing import price_rates
from backend.tests.test_rates_credit_rates_market import abc_products, build_rates_market  # noqa: F401
from backend.tests.test_rates_credit_rates_schedule import abc_reference, abc_terms  # noqa: F401


def _scripted(product, source, *, parameters=None, changes=None):
    terms = product.terms.model_dump(mode="json")
    terms.update(changes or {})
    terms.update({
        "payoff_mode": "scripted",
        "rates_script": {
            "profile": RATES_PAYSCRIPT_PROFILE,
            "source": source,
            "parameters": parameters or {},
        },
    })
    scripted = Product.model_validate({
        "product_id": product.product_id + 10,
        "terms_version": 1, "revision": 1, "terms": terms, "intent": product.intent,
    })
    schedule = resolve_native_schedule(scripted.terms, product_id=scripted.product_id, terms_version=1).schedule
    return scripted.model_copy(update={"native_schedule": schedule})


def _context(product, market, abc_reference, case):
    cutoff = datetime.fromisoformat(abc_reference["snapshots"][case]["cutoff_local"])
    return prepare_native_context(product, valuation_date=market.market_date, cutoff=cutoff, market=market)


def _close_amount(actual, expected):
    assert actual == pytest.approx(expected, rel=0, abs=0.01)


@pytest.mark.parametrize("case", ["A", "B", "C"])
@pytest.mark.parametrize(("index", "source"), [(0, FRN_RATES_PAYSCRIPT), (1, IRS_RATES_PAYSCRIPT)], ids=["frn", "irs"])
def test_script_parity_with_native_pricing_on_each_abc_cutoff(case, index, source, abc_products, abc_reference):
    native = abc_products[index]
    scripted = _scripted(native, source)
    market = build_rates_market(abc_reference, (native, scripted), case)
    base = price_rates(native, _context(native, market, abc_reference, case))
    callback, equivalent, metadata = rates_payoff(scripted)

    def observe_open_flows(event):
        if case == "C":
            assert event.flow_id != base.flows[0].flow_id
        return callback(event)

    price = price_rates(
        scripted, _context(scripted, market, abc_reference, case),
        payoff=observe_open_flows, equivalent_payoff=equivalent,
    )
    assert price.payoff_mode == "scripted" and price.qualification == "deterministic_reference"
    assert equivalent and metadata.result_kind == "qualified_linear"
    assert metadata.source_hash == script_source_hash(source)
    assert [parameter.unit for parameter in metadata.parameters] == ["decimal_fraction"] * len(metadata.parameters)
    assert price.market_fingerprint == base.market_fingerprint
    assert price.terms_fingerprint != base.terms_fingerprint
    for scripted_flow, native_flow in zip(price.flows, base.flows, strict=True):
        assert (
            scripted_flow.flow_id, scripted_flow.period_id, scripted_flow.leg_id, scripted_flow.payment_date,
            scripted_flow.fixing_state, scripted_flow.fixing_id, scripted_flow.state, scripted_flow.bucket,
        ) == (
            native_flow.flow_id, native_flow.period_id, native_flow.leg_id, native_flow.payment_date,
            native_flow.fixing_state, native_flow.fixing_id, native_flow.state, native_flow.bucket,
        )
        _close_amount(scripted_flow.amount_eur, native_flow.amount_eur)
        _close_amount(scripted_flow.pv_eur, native_flow.pv_eur)
        if scripted_flow.state != "paid":
            assert scripted_flow.label
    _close_amount(price.sensitivities.discount_eur, base.sensitivities.discount_eur)
    _close_amount(price.sensitivities.projection_eur, base.sensitivities.projection_eur)
    _close_amount(price.cash_on_value_date_eur, base.cash_on_value_date_eur)
    if index == 0:
        assert price.clean_price_per_100 == pytest.approx(base.clean_price_per_100, rel=0, abs=1e-8)
        for field in ("clean_pv_eur", "dirty_pv_eur", "accrued_eur", "coupon_pv_eur", "principal_pv_eur"):
            _close_amount(getattr(price, field), getattr(base, field))
    else:
        assert price.par_rate == pytest.approx(base.par_rate, rel=0, abs=1e-8)
        for field in ("net_pv_eur", "fixed_pv_eur", "floating_pv_eur"):
            _close_amount(getattr(price, field), getattr(base, field))


@pytest.mark.parametrize("continuous_rate", [-0.005, 0.0])
def test_zero_and_negative_euribor_reach_the_script(abc_products, abc_reference, continuous_rate):
    native = abc_products[1]
    scripted = _scripted(native, IRS_RATES_PAYSCRIPT)
    source = build_rates_market(abc_reference, (scripted,), "A").model_dump(mode="json")
    pillars = source["projection"]["pillars"]
    days = abc_reference["snapshots"]["A"]["anchor_to_terminal_days"]
    pillars[-1]["factor"] = exp(-continuous_rate * days / 365)
    market = RatesMarket.model_validate(source)
    callback, equivalent, _ = rates_payoff(scripted)
    price = price_rates(scripted, _context(scripted, market, abc_reference, "A"),
                        payoff=callback, equivalent_payoff=equivalent)
    first = price.flows[0]
    if continuous_rate < 0:
        assert first.rate < 0
        _close_amount(first.amount_eur, 1245.80)
    else:
        assert first.rate == first.amount_eur == 0


def test_term_bound_margin_changes_the_price_and_cannot_be_overridden(abc_products, abc_reference):
    native = abc_products[0]
    first = _scripted(native, FRN_RATES_PAYSCRIPT)
    floating = native.terms.floating_leg.model_dump(mode="json")
    second = _scripted(native, FRN_RATES_PAYSCRIPT, changes={"floating_leg": {**floating, "margin_bps": 110}})
    valued = []
    for product in (first, second):
        market = build_rates_market(abc_reference, (product,), "B")
        payoff, equivalent, metadata = rates_payoff(product)
        assert equivalent
        assert metadata.parameters[0].value == product.terms.floating_leg.margin_bps / 10_000
        valued.append(price_rates(product, _context(product, market, abc_reference, "B"),
                                  payoff=payoff, equivalent_payoff=equivalent))
    first_coupon, second_coupon = (item.flows[0].amount_eur for item in valued)
    _close_amount(second_coupon - first_coupon, 1_000_000 * 0.001 * 91 / 360)
    assert valued[1].dirty_pv_eur > valued[0].dirty_pv_eur
    assert valued[0].schedule_fingerprint != valued[1].schedule_fingerprint

    invalid = _scripted(native, FRN_RATES_PAYSCRIPT, parameters={"margin": 0.02})
    with pytest.raises(ValueError, match="termes contractuels"):
        rates_payoff(invalid)
    invalid = _scripted(native, FRN_RATES_PAYSCRIPT.replace("PARAM MARGIN", "PARAM MARGIN = 2%"))
    with pytest.raises(ValueError, match="sans valeur par défaut"):
        rates_payoff(invalid)


def test_condition_executes_against_only_the_current_fixing_state(abc_products, abc_reference):
    source = """PARAM BONUS = 1%
AT FLOATING_COUPON:
  IF IS_FIXED:
    PAY BONUS * YEAR_FRACTION "Coupon acquis"
  ELSE:
    PAY -EURIBOR_RATE * YEAR_FRACTION "Coupon projeté"
AT PRINCIPAL:
  PAY 1 "Capital"
"""
    compiled = compile_rates_payscript(source, {"bonus": 0.02})
    fixed = compiled.evaluate("floating_coupon", rate=-0.01, year_fraction=0.5, is_fixed=True)
    projected = compiled.evaluate("floating_coupon", rate=-0.01, year_fraction=0.5, is_fixed=False)
    assert (fixed[0].factor, fixed[0].label) == (0.01, "Coupon acquis")
    assert (projected[0].factor, projected[0].label) == (0.005, "Coupon projeté")
    assert compiled.evaluate("principal")[0].factor == 1
    scripted = _scripted(abc_products[0], source, parameters={"bonus": 0.02})
    market = build_rates_market(abc_reference, (scripted,), "B")
    payoff, equivalent, metadata = rates_payoff(scripted)
    price = price_rates(scripted, _context(scripted, market, abc_reference, "B"),
                        payoff=payoff, equivalent_payoff=equivalent)
    assert not equivalent and metadata.result_kind == price.qualification == "deterministic_scenario"
    assert price.flows[0].label == "Coupon acquis"
    assert price.flows[1].label == "Coupon projeté"
    _close_amount(price.flows[0].amount_eur, 1_000_000 * 0.02 * 91 / 360)


def test_nonlinear_irs_executes_floor_and_returns_no_swap_par_rate(abc_products, abc_reference):
    source = IRS_RATES_PAYSCRIPT.replace(
        "-(EURIBOR_RATE + MARGIN)", "-MAX(EURIBOR_RATE + MARGIN, 0)",
    )
    scripted = _scripted(abc_products[1], source)
    raw = build_rates_market(abc_reference, (scripted,), "A").model_dump(mode="json")
    days = abc_reference["snapshots"]["A"]["anchor_to_terminal_days"]
    raw["projection"]["pillars"][-1]["factor"] = exp(0.005 * days / 365)
    market = RatesMarket.model_validate(raw)
    payoff, equivalent, metadata = rates_payoff(scripted)
    price = price_rates(scripted, _context(scripted, market, abc_reference, "A"),
                        payoff=payoff, equivalent_payoff=equivalent)
    assert not equivalent and metadata.result_kind == price.qualification == "deterministic_scenario"
    assert price.flows[0].rate < 0 and price.flows[0].amount_eur == 0
    assert price.par_rate is price.fixed_annuity_eur is None


def test_scripted_position_cannot_replace_an_eligible_missing_fixing_with_projection(abc_products, abc_reference):
    scripted = _scripted(abc_products[0], FRN_RATES_PAYSCRIPT)
    raw = build_rates_market(abc_reference, (scripted,), "B").model_dump(mode="json")
    raw["fixings"] = raw["fixings"][1:]
    with pytest.raises(RatesMarketError) as exc:
        _context(scripted, RatesMarket.model_validate(raw), abc_reference, "B")
    assert exc.value.code == "RATES_FIXING_UNAVAILABLE"


@pytest.mark.parametrize("source", [
    "AT FIXED_COUPON:\n  PAY EURIBOR_RATE * YEAR_FRACTION",
    "AT PRINCIPAL:\n  PAY YEAR_FRACTION",
    "AT FLOATING_COUPON:\n  PAY WOF",
    "AT FLOATING_COUPON:\n  PAY S[1]",
    "AT FLOATING_COUPON:\n  PAY S0",
    "AT FLOATING_COUPON:\n  PAY EURIBOR_RATE[2]",
    "AT FLOATING_COUPON[2]:\n  PAY YEAR_FRACTION",
    "AT MATURITY:\n  PAY 1",
    "AT PRINCIPAL:\n  PAY 1\nAT PRINCIPAL:\n  PAY 1",
    "PARAM EURIBOR_RATE\nAT PRINCIPAL:\n  PAY 1",
    "AT FLOATING_COUPON:\n  SET PREVIOUS = EURIBOR_RATE\n  PAY PREVIOUS",
])
def test_rate_profile_refuses_equity_cross_event_and_historical_observations(source):
    with pytest.raises(ValueError):
        compile_rates_payscript(source)


def test_rate_profile_requires_finite_amount_and_never_changes_legacy_parser():
    with pytest.raises(ValueError, match="Erreur d’exécution PayScript"):
        compile_rates_payscript("AT PRINCIPAL:\n  PAY 1 / 0").evaluate("principal")
    legacy = parse_script("AT MATURITY\n  PAY WOF")
    assert legacy.events[0].type == "AT_MATURITY"
    with pytest.raises(ValueError, match="identifiant inconnu"):
        parse_script("AT MATURITY\n  PAY EURIBOR_RATE")
