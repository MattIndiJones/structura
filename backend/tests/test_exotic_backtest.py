"""Point-in-time replay preserves terms, acquired evidence and cash coverage."""
from datetime import date, datetime, timedelta

import pytest

from backend.app.core.valuation_context import json_transport_fingerprint
from backend.app.services.exotic_backtest import ExoticBacktestRequest, backtest_exotic_claims
from backend.app.services.exotic_valuation import (
    ExoticValuationError, exotic_engine_fingerprint, price_exotic_scenario, read_scenario, result_payload,
)
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_cds_schedule import cds_terms  # noqa: F401
from backend.tests.test_rates_credit_cln_schedule import cln_terms  # noqa: F401
from backend.tests.test_rates_credit_default import _cutoff, _prepare, credit_products, facts  # noqa: F401
from backend.tests.test_rates_credit_facts import july_facts  # noqa: F401


def _stamp(valuation_date, time="16:00", offset="+01:00"):
    cutoff = f"{valuation_date}T{time}:00{offset}"
    return dict(valuation_date=valuation_date.isoformat(), cutoff=cutoff,
                market_source=dict(source_id="test-market", version=1, available_at=cutoff, validated_at=cutoff))


def _rates(day, *, acquired=None, corrected_relative=0, exercise=False, time="16:00"):
    origin = date(2026, 1, 5) + timedelta(days=day)
    curve = {"pillars": [{"time": 0, "factor": 1}, {"time": 2, "factor": .96}]}
    flow = {"kind": "fixed", "flow_id": "principal", "payment": (365 - day + corrected_relative) / 365,
            "amount_eur": 1_000_000, "is_coupon": False}
    cashflows = [flow]
    rights = []
    if exercise:
        if day < 30:
            rights = [dict(exercise_id="call", decision=(30 - day) / 365, settlement=(30 - day) / 365,
                           redemption_eur=1_000_000, owner="issuer", coupon_priority="before")]
    else:
        cashflows.append(dict(kind="rate", flow_id="index-coupon", fixing=(10 - day) / 365, payment=(130 - day) / 365,
                              index=dict(kind="forward", start=(20 - day) / 365, end=(110 - day) / 365,
                                         year_fraction=.25), year_fraction=.25, realized_rate=acquired))
    return {"family": "rates", "position_id": "replay-rate", **_stamp(origin, time),
            "terms": {"nominal_eur": 1_000_000, "cashflows": cashflows, "exercises": rights},
            "market": {"discount": curve, "projection": curve, "mean_reversion": .1, "volatility": .01},
            "settings": {"paths": 128, "seed": 42, "training_paths": 128 if rights else None}}


def _claim(body):
    scenario = read_scenario(body)
    result = result_payload(price_exotic_scenario(scenario))
    return dict(request=scenario.model_dump(mode="json"), result=result,
                result_fingerprint=json_transport_fingerprint(result), engine_fingerprint=exotic_engine_fingerprint())


def test_rate_tape_replays_resolved_dates_and_preserves_acquired_fixings():
    first, second, third = [_claim(body) for body in (_rates(0), _rates(15, acquired=.03), _rates(16, acquired=.03))]
    reports = [backtest_exotic_claims("rate-tape", [first, second, third]) for _ in range(2)]
    assert reports[0] == reports[1]
    report = reports[0]
    assert report.method == "signed_point_in_time_replay" and report.coverage == "supplied_cutoffs_only"
    assert report.market_quality == "synthetic" and report.point_count == 3
    assert report.confirmed_cash_within_tape_eur is None
    assert [point.available_fixings for point in report.points] == [0, 1, 1]
    assert [point.dirty_pv_eur for point in report.points] == [claims["result"]["pv_eur"] for claims in (first, second, third)]
    assert report.points[0].pv_interval_95_eur == tuple(first["result"]["ci95_eur"])
    assert [point.cutoff for point in report.points] == sorted(point.cutoff for point in report.points)


def test_rejects_cutoff_order_sliding_calendar_fixing_replacement_and_mixed_positions():
    first, after = _claim(_rates(0)), _claim(_rates(15, acquired=.03))
    shifted = _claim(_rates(15, acquired=.03, corrected_relative=1))
    replaced = _claim(_rates(16, acquired=.04))
    unrelated = _claim({**_rates(15, acquired=.03), "position_id": "other"})
    for rows, code in (([after, first], "CUTOFF_ORDER"), ([first, first], "CUTOFF_ORDER"),
                       ([first, shifted], "TERMS_MISMATCH"), ([first, after, replaced], "FIXING_CHANGED"),
                       ([first, unrelated], "POSITION_MISMATCH")):
        with pytest.raises(ExoticValuationError) as rejected:
            backtest_exotic_claims("rate-tape", rows)
        assert rejected.value.code == "EXOTIC_BACKTEST_" + code


def test_rejects_crossing_exercise_without_historical_decision():
    before, after = _claim(_rates(0, exercise=True)), _claim(_rates(31, exercise=True))
    with pytest.raises(ExoticValuationError) as rejected:
        backtest_exotic_claims("exercises", [before, after])
    assert rejected.value.code == "EXOTIC_BACKTEST_EXERCISE_STATE_REQUIRED"


def test_historical_dataset_evidence_and_work_bounds_are_enforced():
    first, second = _claim(_rates(0)), _claim(_rates(15, acquired=.03))
    with pytest.raises(ExoticValuationError, match="moteur indisponible"):
        backtest_exotic_claims("replay", [first, {**second, "engine_fingerprint": "0" * 64}])
    with pytest.raises(ExoticValuationError, match="diffère du reçu"):
        backtest_exotic_claims("replay", [first, {**second, "result_fingerprint": "0" * 64}])
    with pytest.raises(ExoticValuationError, match="budget cumulé"):
        backtest_exotic_claims("replay", [{**first, "request": {**first["request"],
                                                               "settings": {**first["request"]["settings"], "paths": 250_000}}}] * 5)
    assert ExoticBacktestRequest(tape_id="replay", receipts=[first, second]).receipts[0].to_dict() == first


def _credit(product, cutoff: datetime, context=None, *, basket=False):
    nominal = product.intent.nominal
    years = (date(2026, 6, 21) - cutoff.date()).days / 365
    member = dict(reference_entity_id=product.terms.reference_entity_id, source_id="flat", source_version=1,
                  curve=dict(maturities=[6], hazards=[.02]), recovery_fraction=.4)
    contract = dict(kind="basket_cds" if basket else "cln", nominal_eur=nominal, maturity_years=years,
                    coupons=[], coupon_bps=product.terms.fixed_leg.coupon_rate * 10_000, side="BUY")
    if basket:
        contract["trigger_rank"] = 1
    raw = dict(family="credit", position_id="july-cln",
               **_stamp(cutoff.date(), cutoff.strftime("%H:%M"), offset="+02:00"), credit=dict(
                   contract=contract, market=dict(source_id="test-market", source_version=1, discount_rate=.02,
                                                  marginals=[member, {**member, "reference_entity_id": "another"}] if basket else [member]),
                   settings=dict(paths=128, seed=42)))
    if context is not None:
        raw["credit"]["realized"] = dict(product=product.model_dump(mode="json"), context=context.model_dump(mode="json"))
    return raw


def test_credit_default_tape_retains_payment_and_discloses_partial_cash(credit_products, facts):
    product = credit_products["CLN"]
    live = _claim(_credit(product, _cutoff(15, 9)))
    realized = [_claim(_credit(product, _cutoff(day), _prepare(product, _cutoff(day), facts))) for day in (15, 19, 20, 21)]
    report = backtest_exotic_claims("july", [live, *realized])
    assert [point.state for point in report.points] == ["alive", "recovery_pending", "settlement_pending", "settled", "settled"]
    assert report.points[1].dirty_pv_eur is None
    assert report.points[2].dirty_pv_eur == pytest.approx(349_980.82, abs=.01)
    assert report.points[3].dirty_pv_eur == 0
    recorded = [payment for point in report.points for payment in point.payments_newly_supplied]
    assert len(recorded) == 2
    assert [payment.within_tape for payment in recorded] == [False, True]
    assert recorded[1].confirmation.amount_eur == report.confirmed_cash_within_tape_eur == 350_000
    assert report.points[-1].payments_newly_supplied == ()
    assert report.performance_status == "historical_trade_and_cash_coverage_unavailable"
    later_live = _claim(_credit(product, _cutoff(21)))
    with pytest.raises(ExoticValuationError, match="fait de défaut"):
        backtest_exotic_claims("july", [live, realized[0], later_live])


def test_basket_tape_rejects_implicit_conditioning_on_multidate_survival(credit_products):
    product = credit_products["CLN"]
    before, after = [_claim(_credit(product, _cutoff(day), basket=True)) for day in (15, 16)]
    with pytest.raises(ExoticValuationError) as rejected:
        backtest_exotic_claims("basket", [before, after])
    assert rejected.value.code == "EXOTIC_BACKTEST_BASKET_STATE_REQUIRED"


def test_backtest_http_replays_server_signed_prices_and_enforces_receipt_ownership(product_client):
    endpoint = "/api/products/exotics"
    receipts = []
    for body in (_rates(0), _rates(15, acquired=.03)):
        response = product_client.post(endpoint + "/price", json=body)
        assert response.status_code == 200, response.text
        receipts.append(response.json()["receipt"])

    tape = {"tape_id": "http-tape", "receipts": receipts}
    response = product_client.post(endpoint + "/backtest", json=tape)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["point_count"] == 2
    assert report["points"][1]["result_fingerprint"] == receipts[1]["result_fingerprint"]
    assert report == product_client.post(endpoint + "/backtest", json=tape).json()

    tampered = {**receipts[1], "request": {**receipts[1]["request"], "position_id": "tampered"}}
    assert product_client.post(endpoint + "/backtest", json={**tape, "receipts": [receipts[0], tampered]}).status_code == 422
    product_client.current["user"] = product_client.users["bob"]
    response = product_client.post(endpoint + "/backtest", json=tape)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXOTIC_RECEIPT_NOT_FOUND"
