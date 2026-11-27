"""Civil dates, signed cashflow projections and retained rates MC contracts."""

from copy import deepcopy
from datetime import date, datetime
from math import fsum

import pytest

from backend.app.db.models import Counterparty
from backend.app.services import exotic_deal_valuation
from backend.app.services.exotic_backtest import _check_contracts
from backend.app.services.exotic_valuation import ExoticValuationError, read_scenario
from backend.tests.test_exotic_pricer_api import _json, _rates, product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


ROOT = "/api/products/exotics"


def _dated_rates(valuation_date="2026-11-23"):
    request = _rates()
    request.update(valuation_date=valuation_date, cutoff=f"{valuation_date}T16:00:00+01:00")
    origin = date.fromisoformat(valuation_date)

    def time(day: str) -> float:
        return (date.fromisoformat(day) - origin).days / 365

    start, roll, end = "2026-11-30", "2027-05-31", "2027-11-30"
    index_end = time("2028-05-31")
    request["terms"].update(
        contract_dates={
            "time_origin": origin.isoformat(), "start_date": start, "end_date": end,
            "accrual_periods": [
                {"flow_id": "fixed", "start_date": start, "end_date": roll},
                {"flow_id": "cms", "start_date": roll, "end_date": end},
            ],
        },
        cashflows=[
            {"kind": "fixed", "flow_id": "fixed", "payment": time("2027-06-02"), "amount_eur": 10_000},
            {"kind": "rate", "flow_id": "cms", "payment": time("2027-12-02"), "fixing": time("2027-05-27"),
             "year_fraction": 183 / 360, "index": {"kind": "swap",
             "fixed_periods": [{"payment": index_end, "year_fraction": 1}],
             "floating_periods": [{"start": time(roll), "end": index_end, "year_fraction": 366 / 360}]}},
            {"kind": "fixed", "flow_id": "principal", "payment": time("2027-12-03"),
             "amount_eur": 1_000_000, "is_coupon": False},
        ],
    )
    request["market"]["volatility"] = 0.0
    request["settings"]["paths"] = 8
    return request


def test_dated_rates_keep_signed_economics_and_legacy_receipt_shape(product_client):
    client, dated = product_client, _dated_rates()
    dated["terms"]["side"] = "SELL"
    priced = _json(client.post(f"{ROOT}/price", json=dated))
    relative = deepcopy(dated)
    del relative["terms"]["contract_dates"]
    historical = _json(client.post(f"{ROOT}/price", json=relative))

    result, old_result = priced["result"], historical["result"]
    assert result["draw_fingerprint"] == old_result["draw_fingerprint"]
    assert result["pv_eur"] == old_result["pv_eur"]
    assert "contract_dates" not in historical["receipt"]["request"]["terms"]
    flows = result["flows"]
    assert [flow["payment_date"] for flow in flows] == ["2027-06-02", "2027-12-02", "2027-12-03"]
    assert [flow["payment_event_id"] for flow in flows] == ["fixed:payment", "cms:payment", "principal:payment"]
    assert [flow["payment_role"] for flow in flows] == ["coupon", "coupon", "principal"]
    assert [flow["state"] for flow in flows] == ["fixed", "projected", "fixed"]
    assert [flow.get("amount_eur") for flow in flows] == [-10_000, None, -1_000_000]
    assert (flows[1]["accrual_start_date"], flows[1]["accrual_end_date"]) == ("2027-05-31", "2027-11-30")
    for original, current in zip(old_result["flows"], flows, strict=True):
        assert set(original) == {"flow_id", "kind", "payment", "mean_amount_eur", "pv_eur", "paid_probability"}
        assert original == {key: current[key] for key in original}
        assert current["mean_amount_eur"] < 0
    assert fsum(flow["pv_eur"] for flow in flows) == pytest.approx(result["pv_eur"], abs=1e-9)
    assert _json(client.post(f"{ROOT}/replay", json={"receipt": priced["receipt"]}))["result"] == result


@pytest.mark.parametrize("violation", ["asof", "payment", "reference", "principal_accrual"])
def test_dated_rates_reject_off_axis_or_unbound_dates(product_client, violation):
    body = _dated_rates()
    terms = body["terms"]
    if violation == "asof":
        terms["contract_dates"]["time_origin"] = "2026-11-24"
    elif violation == "payment":
        terms["cashflows"][0]["payment"] += .00001
    elif violation == "reference":
        index = terms["cashflows"][1]["index"]
        index["fixed_periods"][0]["payment"] += .00001
        index["floating_periods"][0]["end"] += .00001
    else:
        terms["contract_dates"]["accrual_periods"][0]["flow_id"] = "principal"
    assert product_client.post(f"{ROOT}/price", json=body).status_code == 422


def test_dated_callable_keeps_exercise_obligations_contingent(product_client):
    body = _dated_rates()
    terms = body["terms"]
    terms["cashflows"].pop(1)
    terms["contract_dates"]["accrual_periods"].pop(1)
    decision = terms["cashflows"][0]["payment"]
    terms["exercises"] = [dict(exercise_id="call", decision=decision, settlement=(round(decision * 365) + 1) / 365,
                               redemption_eur=950_000, owner="issuer", coupon_priority="before")]
    body["settings"]["training_paths"] = 32
    flows = _json(product_client.post(f"{ROOT}/price", json=body))["result"]["flows"]
    assert [(flow["flow_id"], flow["state"]) for flow in flows] == [
        ("fixed", "fixed"), ("call", "contingent"), ("principal", "contingent"),
    ]
    assert (flows[1]["payment_role"], flows[1]["payment_event_id"], flows[1]["payment_date"]) == (
        "exercise", "call:settlement", "2027-06-03",
    )
    assert all("amount_eur" not in flow for flow in flows[1:])


@pytest.mark.parametrize("field", ["start_date", "end_date", "accrual_periods"])
def test_dated_backtest_requires_the_same_absolute_contract_dates(field):
    first, later = _dated_rates(), _dated_rates("2026-11-24")
    _check_contracts((read_scenario(first), read_scenario(later)))
    if field == "accrual_periods":
        later["terms"]["contract_dates"][field][0]["end_date"] = "2027-05-30"
    else:
        later["terms"]["contract_dates"][field] = {"start_date": "2026-11-29", "end_date": "2027-12-01"}[field]
    with pytest.raises(ExoticValuationError) as error:
        _check_contracts((read_scenario(first), read_scenario(later)))
    assert error.value.code == "EXOTIC_BACKTEST_TERMS_MISMATCH"


def test_dated_rates_freeze_forward_start_rolls_and_distinct_settlement_at_booking(native_recipe_client, monkeypatch):
    client = native_recipe_client
    client.session.add(Counterparty(id=1, name="Émetteur de recette", active=True))
    client.session.commit()
    body = _dated_rates()
    priced = _json(client.post(f"{ROOT}/price", json=body))
    retained = _json(client.post(f"{ROOT}/conserve", json={
        "name": "Note CMS datée", "command_key": "retain-dated-cms", "receipt": priced["receipt"],
    }), 201)
    assert retained["booking_eligible"], retained
    product = retained["product"]
    assert product["terms"]["effective_date"] == "2026-11-30"
    assert product["terms"]["maturity_date"] == "2027-11-30"
    schedule = product["native_schedule"]
    events = {event["event_id"]: event for leg in schedule["legs"] for event in leg["events"]}
    assert all(event["date_projection"] == "exact" for event in events.values())
    assert events["fixed:accrual-start"]["date"] == "2026-11-30"
    assert events["fixed:accrual-end"]["date"] == events["cms:accrual-start"]["date"] == "2027-05-31"
    assert events["cms:fixing"]["date"] == "2027-05-27"
    assert events["cms:accrual-end"]["date"] == "2027-11-30"
    for row in priced["result"]["flows"]:
        assert row["payment_date"] == events[row["payment_event_id"]]["date"]
    archived = _json(client.get(f"/api/products/{product['product_id']}/exotics/calculations/{retained['calculation_id']}"))
    assert archived["receipt"] == priced["receipt"]

    booked = _json(client.post(f"/api/products/{product['product_id']}/exotics/book", json={
        "calculation_id": retained["calculation_id"], "command_key": "book-dated-cms",
        "expected_revision": product["revision"], "expected_terms_version": product["terms_version"],
        "counterparty_id": 1, "execution_price_eur": 1_000_000,
        "trade_date": body["valuation_date"], "value_date": body["valuation_date"],
    }), 201)
    deal = _json(client.get(f"/api/deals/{booked['deal_id']}"))
    assert (deal["strike_date"], deal["maturity_date"], deal["payment_date"]) == ("2026-11-30", "2027-11-30", "2027-12-03")
    assert deal["frozen_schedule"]["schedule"] == schedule

    cutoff = "2026-12-01T16:00:00+01:00"
    monkeypatch.setattr(exotic_deal_valuation, "business_now", lambda: datetime.fromisoformat(cutoff))
    residual = _json(client.post(f"/api/deals/{booked['deal_id']}/exotics/valuations", json={
        "cutoff": cutoff, "market_mode": "frozen_booking_roll",
    }), 201)["result"]
    assert [(flow["payment_date"], flow["payment_event_id"]) for flow in residual["flows"]] == [
        (row["payment_date"], row["payment_event_id"]) for row in priced["result"]["flows"]
    ]
    assert residual["cash_confirmed_eur"] == 0
