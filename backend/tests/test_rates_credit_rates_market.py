"""Frozen A/B/C market selection and boundary tests for FRN and IRS."""

from datetime import date, datetime, time
from math import exp, sqrt
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from backend.app.core.product.models import Product
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_market import (
    EuriborFixing, RatesMarket, RatesMarketError, RatesMarketSelection, prepare_rates_market,
)
from backend.tests.test_rates_credit_rates_schedule import abc_reference, abc_terms


def _source(reference):
    return {"kind": "synthetic", "provider": "structura-fixture", "reference": reference}


def _fixing(record):
    return EuriborFixing.model_validate({
        **record, "source": _source(record["fixing_id"]), "rate": float(record["rate"]),
    })


@pytest.fixture(scope="module")
def abc_products(abc_reference, abc_terms):
    terms_examples = []
    for product_id, terms in enumerate(abc_terms, start=101):
        prepared = resolve_native_schedule(terms, product_id=product_id, terms_version=1)
        terms_examples.append(Product(
            product_id=product_id, terms_version=1, revision=1, terms=terms, native_schedule=prepared.schedule,
            intent={"nominal": float(abc_reference["terms"]["notional_eur"]), "side": "BUY"},
        ))
    return tuple(terms_examples)


def build_rates_market(abc_reference, products, case, *, date_override=None) -> RatesMarket:
    snapshot = abc_reference["snapshots"][case]
    zone = ZoneInfo(abc_reference["clock"]["timezone"])
    reference_date = date.fromisoformat(snapshot["market_date"])
    anchor = date_override or reference_date
    definitions = abc_reference["curve_definitions"]
    market_id = snapshot["market_id"] if anchor == reference_date else f"eur-abc-{anchor}"
    available_at = datetime.fromisoformat(snapshot["market_available_at"])
    validated_at = datetime.fromisoformat(snapshot["market_validated_at"])
    if anchor != reference_date:
        available_at = validated_at = datetime.combine(anchor, time(9), tzinfo=zone)
    curves = {}
    for key, pillar_key in (("ois", "ois_pillars"), ("euribor", "euribor_pillars")):
        definition = definitions[key]
        terminal_date = date.fromisoformat(snapshot[pillar_key][-1][0])
        pillars = snapshot[pillar_key]
        if anchor != reference_date:
            rate = float(definition["continuous_zero_rate"])
            factor = exp(-rate * (terminal_date - anchor).days / 365)
            pillars = [(anchor, 1), (terminal_date, factor)]
        curves[definition["role"]] = {
            "curve_id": f"{market_id}-{key}", "version": 1, "role": definition["role"],
            "currency": definition["currency"], "index": definition["index"], "tenor": definition.get("tenor"),
            "anchor_date": anchor, "pillars": [{"date": day, "factor": float(factor)} for day, factor in pillars],
            "source": _source(pillar_key), "available_at": available_at, "validated_at": validated_at,
            "day_count": definitions["day_count"], "interpolation": definitions["interpolation"],
            "extrapolation": definitions["extrapolation"],
        }
    payment = abc_reference["first_payment"]
    payments = []
    for product in products:
        assert product.native_schedule is not None
        instrument = product.terms.instrument_type.lower()
        payments.append({
            "fact_id": payment["fact_id"], "version": 1, "schedule_fingerprint": product.native_schedule.fingerprint,
            "flow_id": payment[f"{instrument}_flow_id"], "effect_date": payment["effect_date"],
            "amount_eur": float(payment[f"{instrument}_cash_eur"]), "status": "validated",
            "source": _source(payment["fact_id"]),
            "available_at": payment["available_at"], "validated_at": payment["validated_at"],
        })
    return RatesMarket.model_validate({
        "kind": "rates", "market_id": market_id, "market_version": snapshot["market_version"],
        "market_date": anchor, **curves, "frn_funding_bps": float(abc_reference["terms"]["frn"]["funding_bp"]),
        "fixings": tuple(_fixing(item) for item in abc_reference["fixings"]), "payments": payments,
    })


@pytest.fixture(scope="module")
def market_for(abc_reference, abc_products):
    def build_market(case, *, date_override=None):
        return build_rates_market(abc_reference, abc_products, case, date_override=date_override)
    return build_market


def _cutoff(abc_reference, case):
    return datetime.fromisoformat(abc_reference["snapshots"][case]["cutoff_local"])


@pytest.mark.parametrize("case", ["A", "B", "C"])
def test_abc_products_share_dated_curves_and_select_their_own_flows(case, market_for, abc_reference, abc_products):
    market = market_for(case)
    expected = abc_reference["snapshots"][case]
    cutoff = _cutoff(abc_reference, case)
    frn, irs = (prepare_rates_market(product, market.market_date, cutoff, market) for product in abc_products)
    assert frn.market_id == irs.market_id == expected["market_id"]
    assert frn.market_fingerprint == irs.market_fingerprint
    assert frn.frn_funding_bps == 0
    for context, flow_key in ((frn, "frn_flow_id"), (irs, "irs_flow_id")):
        assert context.settlement_date == context.valuation_date == market.market_date
        assert context.cutoff_utc == datetime.fromisoformat(expected["cutoff_utc"])
        assert context.projection_dates[0] == date.fromisoformat(expected["first_required_projection_date"])
        assert [fixing.fixing_id for fixing in context.fixings] == expected["acquired_fixing_ids"]
        assert context.flows[0].flow_id == abc_reference["first_payment"][flow_key]
        assert context.flows[0].state == expected["first_payment_state"]
        assert sum(flow.fixing_state == "projected" for flow in context.flows) == 8 - len(context.fixings)
        assert context.discount.factor_at(context.valuation_date) == context.projection.factor_at(context.valuation_date) == 1
        for curve, pillars in ((context.discount, "ois_pillars"), (context.projection, "euribor_pillars")):
            terminal_day, factor = expected[pillars][-1]
            assert curve.factor_at(date.fromisoformat(terminal_day)) == float(factor)
        assert RatesMarketSelection.model_validate_json(context.model_dump_json()) == context
    if case == "A":
        assert frn.discount.factor_at(frn.flows[0].payment_date) == pytest.approx(
            float(abc_reference["additional_references"]["a_first_payment_ois_factor"]), rel=0, abs=1e-14,
        )
    if case == "C":
        assert len(frn.payments) == len(irs.payments) == 1
        assert frn.payments[0].flow_id != irs.payments[0].flow_id
        assert frn.payments[0].amount_eur > 0 > irs.payments[0].amount_eur
        assert frn.valuation_date not in frn.discount_dates


def test_fixing_boundary_is_inclusive_in_both_timezones(market_for, abc_reference, abc_products):
    boundary = abc_reference["variants"]["first_fixing_boundary"]
    before, at = (datetime.fromisoformat(boundary[field]) for field in ("before_cutoff", "at_cutoff"))
    market = market_for("A", date_override=at.date())
    frn = abc_products[0]
    projected = prepare_rates_market(frn, at.date(), before, market)
    fixed = prepare_rates_market(frn, at.date(), at, market)
    assert projected.fixings == () and projected.flows[0].fixing_state == "projected"
    assert fixed.flows[0].fixing_state == "fixed"
    assert fixed.fixings[0].rate == 0.031
    assert prepare_rates_market(frn, at.date(), fixed.cutoff_utc, market) == fixed
    early_record = market.fixings[0].model_copy(update={"available_at": before, "validated_at": before})
    early_market = market.model_copy(update={"fixings": (early_record, *market.fixings[1:])})
    assert prepare_rates_market(frn, at.date(), before, early_market) == projected


@pytest.mark.parametrize("unavailable", ["absent", "indicative", "late_publication", "late_validation", "wrong_tenor"])
def test_required_fixing_must_be_both_available_and_validated(unavailable, market_for, abc_reference, abc_products):
    market = market_for("B")
    first, second = market.fixings
    changes = {
        "indicative": {"status": "indicative", "validated_at": None},
        "late_publication": {"available_at": "2026-11-02T12:01:00+01:00"},
        "late_validation": {"validated_at": "2026-11-02T12:01:00+01:00"},
        "wrong_tenor": {"tenor": "6M"},
    }
    quote = () if unavailable == "absent" else (
        EuriborFixing.model_validate({**first.model_dump(), **changes[unavailable]}),
    )
    market = market.model_copy(update={"fixings": (*quote, second)})
    with pytest.raises(RatesMarketError, match="17/09/2026") as exc:
        prepare_rates_market(abc_products[0], market.market_date, _cutoff(abc_reference, "B"), market)
    assert exc.value.code == "RATES_FIXING_UNAVAILABLE"


def test_late_correction_and_ingestion_trace_leave_historical_selection_unchanged(market_for, abc_reference, abc_products):
    market = market_for("B")
    frn = abc_products[0]
    cutoff = _cutoff(abc_reference, "B")
    historical = prepare_rates_market(frn, market.market_date, cutoff, market)
    correction = abc_reference["variants"]["late_first_fixing_correction"]
    new_fixing = _fixing(correction["fixing"])
    duplicate = market.fixings[0].model_copy(update={"ingested_at": cutoff})
    expanded = market.model_copy(update={
        "fixings": (*market.fixings, new_fixing, duplicate),
        "discount": market.discount.model_copy(update={"ingested_at": cutoff}),
    })
    assert prepare_rates_market(frn, market.market_date, cutoff, expanded) == historical
    corrected = prepare_rates_market(frn, market.market_date, datetime.fromisoformat(correction["at_cutoff"]), expanded)
    assert corrected.fixings[0].rate == 0.0311 and corrected.flows[0].fixing_version == 2
    assert corrected.fixings[0].supersedes == historical.fixings[0].fixing_id
    assert corrected.market_fingerprint == historical.market_fingerprint
    assert "ingested_at" not in corrected.model_dump_json()


def test_unranked_concurrent_fixing_sources_are_refused(market_for, abc_reference, abc_products):
    market = market_for("B")
    first = market.fixings[0]
    alternative = EuriborFixing.model_validate({
        **first.model_dump(), "source": {**first.source.model_dump(), "provider": "another-fixture"},
    })
    market = market.model_copy(update={"fixings": (*market.fixings, alternative)})
    with pytest.raises(RatesMarketError, match="Plusieurs sources") as exc:
        prepare_rates_market(abc_products[0], market.market_date, _cutoff(abc_reference, "B"), market)
    assert exc.value.code == "RATES_SOURCE_AMBIGUOUS"


def test_payment_boundary_preserves_identity_and_the_open_due_claim_at_par(market_for, abc_reference, abc_products):
    market = market_for("C")
    boundary = abc_reference["variants"]["first_payment_boundary"]
    before, at = (datetime.fromisoformat(boundary[field]) for field in ("before_cutoff", "at_cutoff"))
    irs = abc_products[1]
    opened = prepare_rates_market(irs, market.market_date, before, market)
    closed = prepare_rates_market(irs, market.market_date, at, market)
    assert opened.flows[0].state == boundary["before_state"]
    assert not opened.payments and opened.valuation_date in opened.discount_dates
    assert opened.discount.factor_at(opened.flows[0].payment_date) == 1
    assert closed.flows[0].state == boundary["at_state"]
    assert closed.flows[0].flow_id == opened.flows[0].flow_id
    assert closed.payments[0].fact_id == abc_reference["first_payment"]["fact_id"]
    assert closed.fixings == opened.fixings
    assert closed.market_fingerprint == opened.market_fingerprint

    another_day = date(2026, 12, 22)
    arrears = market_for("C", date_override=another_day).model_copy(update={"payments": ()})
    with pytest.raises(RatesMarketError, match="Créance ouverte échue") as exc:
        prepare_rates_market(irs, another_day, datetime(2026, 12, 22, 12, tzinfo=ZoneInfo("Europe/Paris")), arrears)
    assert exc.value.code == "RATES_OVERDUE_PAYMENT"


def test_payment_confirmation_is_scoped_to_the_frozen_product_schedule(market_for, abc_reference, abc_products):
    market = market_for("C")
    frn = abc_products[0]
    duplicate_terms = resolve_native_schedule(frn.terms, product_id=103, terms_version=frn.terms_version)
    another_frn = frn.model_copy(update={"product_id": 103, "native_schedule": duplicate_terms.schedule})
    cutoff = _cutoff(abc_reference, "C")
    original = prepare_rates_market(frn, market.market_date, cutoff, market)
    another = prepare_rates_market(another_frn, market.market_date, cutoff, market)
    assert original.flows[0].flow_id == another.flows[0].flow_id
    assert original.flows[0].state == "paid"
    assert another.flows[0].state == "due_open"
    assert original.market_fingerprint == another.market_fingerprint


def test_future_payment_revision_leaves_the_historical_payment_unchanged(market_for, abc_reference, abc_products):
    market = market_for("C")
    frn = abc_products[0]
    cutoff = _cutoff(abc_reference, "C")
    original = prepare_rates_market(frn, market.market_date, cutoff, market)
    payment = market.payments[0]
    later = datetime(2026, 12, 21, 16, 1, tzinfo=ZoneInfo("Europe/Paris"))
    corrected = type(payment).model_validate({
        **payment.model_dump(), "version": 2, "amount_eur": payment.amount_eur + 1, "validated_at": later,
    })
    market = market.model_copy(update={"payments": (*market.payments, corrected)})
    assert prepare_rates_market(frn, market.market_date, cutoff, market) == original
    updated = prepare_rates_market(frn, market.market_date, later, market)
    assert updated.flows[0].flow_id == original.flows[0].flow_id
    assert updated.flows[0].payment_version == 2
    assert updated.payments[0].amount_eur == original.payments[0].amount_eur + 1
    assert original.market_fingerprint == updated.market_fingerprint


@pytest.mark.parametrize(
    ("curve_field", "changes", "diagnostic"),
    [
        ("discount", {"role": "projection"}, "RATES_CURVE_INCOMPATIBLE"),
        ("discount", {"currency": "USD"}, "RATES_CURVE_INCOMPATIBLE"),
        ("projection", {"tenor": "6M"}, "RATES_CURVE_INCOMPATIBLE"),
        ("projection", {"source": {"kind": "observed", "provider": "desk", "reference": "test"}}, "RATES_SOURCE_NOT_ALLOWED"),
        ("projection", {"validated_at": "2026-09-16T12:01:00+02:00"}, "RATES_CURVE_UNAVAILABLE"),
        ("discount", {"pillars": [{"date": "2026-09-16", "factor": 1}, {"date": "2028-09-20", "factor": .96}]}, "RATES_CURVE_COVERAGE"),
        ("projection", {"pillars": [{"date": "2026-09-16", "factor": 1}, {"date": "2028-09-20", "factor": .95}]}, "RATES_CURVE_COVERAGE"),
    ],
)
def test_curves_require_eligible_compatible_covered_inputs(curve_field, changes, diagnostic, market_for, abc_reference, abc_products):
    payload = market_for("A").model_dump()
    payload[curve_field].update(changes)
    market = RatesMarket.model_validate(payload)
    with pytest.raises(RatesMarketError) as exc:
        prepare_rates_market(abc_products[0], market.market_date, _cutoff(abc_reference, "A"), market)
    assert exc.value.code == diagnostic


@pytest.mark.parametrize(
    "pillars", [
        [("2026-09-16", 1.01), ("2028-09-21", .95)],
        [("2026-09-16", 1), ("2026-09-16", .95)],
        [("2026-09-16", 1), ("2026-09-15", .95)],
        [("2026-09-16", 1), ("2028-09-21", 0)],
        [("2026-09-16", 1), ("2028-09-21", float("inf"))],
    ],
)
def test_invalid_pillars_are_refused(pillars, market_for):
    payload = market_for("A").model_dump()
    payload["discount"]["pillars"] = [{"date": day, "factor": factor} for day, factor in pillars]
    with pytest.raises(ValidationError):
        RatesMarket.model_validate(payload)


def test_negative_factors_and_authorized_override_preserve_source_values(market_for, abc_reference, abc_products):
    market = market_for("A")
    cutoff = _cutoff(abc_reference, "A")
    frn = abc_products[0]
    initial = prepare_rates_market(frn, market.market_date, cutoff, market)
    payload = market.model_dump()
    ending = market.projection.pillars[-1].date
    elapsed = (ending - market.market_date).days
    rate = float(abc_reference["variants"]["negative_projection_rate"]["continuous_zero_rate"])
    factor = exp(-rate * elapsed / 365)
    payload["projection"]["override"] = {
        "override_id": "negative-curve-scenario", "author": "fixture-operator", "reason": "Scénario de taux négatifs",
        "approved_at": "2026-09-16T12:01:00+02:00",
        "pillars": [{"date": market.market_date, "factor": 1}, {"date": ending, "factor": factor}],
    }
    overridden = RatesMarket.model_validate(payload)
    assert prepare_rates_market(frn, market.market_date, cutoff, overridden) == initial
    at = datetime.fromisoformat(payload["projection"]["override"]["approved_at"])
    selected = prepare_rates_market(frn, market.market_date, at, overridden)
    assert selected.projection.pillars == initial.projection.pillars
    assert selected.projection.override.author == "fixture-operator"
    assert selected.projection.factor_at(ending) == factor > 1
    assert selected.market_fingerprint != initial.market_fingerprint
    midpoint = date.fromordinal(market.market_date.toordinal() + elapsed // 2)
    assert elapsed % 2 == 0
    assert selected.projection.factor_at(midpoint) == pytest.approx(sqrt(factor), rel=0, abs=1e-14)


def test_missing_schedule_and_naive_cutoff_raise_typed_errors(market_for, abc_reference, abc_products):
    market = market_for("A")
    cutoff = _cutoff(abc_reference, "A")
    product = abc_products[0]
    for candidate, at, diagnostic in (
        (product.model_copy(update={"native_schedule": None}), cutoff, "RATES_SCHEDULE_REQUIRED"),
        (product, cutoff.replace(tzinfo=None), "RATES_CUTOFF_INVALID"),
    ):
        with pytest.raises(RatesMarketError) as exc:
            prepare_rates_market(candidate, market.market_date, at, market)
        assert exc.value.code == diagnostic
