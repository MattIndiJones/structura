"""Two isolated booking-to-cash witnesses with immutable valuation proofs."""

from datetime import date, datetime, timedelta
from math import exp

import pytest
from sqlmodel import select

from backend.app.db.models import DealEvent, NativeExoticLifecycleEntry, User, ValuationRun
from backend.app.services import exotic_deal_valuation, exotic_product_lifecycle
from backend.tests.test_exotic_pricer_api import _credit, _rates
from backend.tests.test_exotic_product_booking import _fact_deal, _fact_test_users, _proposal, _response
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


def _fixture(client, monkeypatch, body):
    maker, checker = _fact_test_users(client, monkeypatch)
    deal_id, schedule = _fact_deal(client, body)
    origin = date.fromisoformat(body["valuation_date"])
    clock = lambda: datetime.fromisoformat(body["cutoff"])
    monkeypatch.setattr(exotic_product_lifecycle, "business_now", lambda: clock())
    monkeypatch.setattr(exotic_deal_valuation, "business_now", lambda: clock())
    path = f"/api/deals/{deal_id}/exotics"

    def at(day, hour):
        return datetime.fromisoformat(f"{origin + timedelta(days=day)}T{hour:02d}:00:00+01:00")

    def set_clock(day, hour):
        nonlocal clock
        clock = lambda: at(day, hour)

    def mark(day, hour, expected=201):
        request = {"cutoff": at(day, hour).isoformat(), "market_mode": "frozen_booking_roll"}
        return _response(client.post(path + "/valuations", json=request), expected)

    def validate(payload, day, hour=15):
        set_clock(day, hour - 1)
        client.current["user"] = maker
        draft = _response(client.post(path + "/facts", json=payload), 201)
        set_clock(day, hour)
        client.current["user"] = checker
        checked = _response(client.post(path + f"/facts/{draft['id']}/decision", json={
            "command_key": "check-" + payload["command_key"], "decision": "validate", "reason": "Preuve rapprochée",
        }))
        client.current["user"] = maker
        return checked

    return path, schedule, at, set_clock, mark, validate


def _pnl(client, path, start, end):
    return _response(client.post(path + "/explain", json={
        "start_run_id": start["valuation_run_id"], "end_run_id": end["valuation_run_id"],
    }))


@pytest.mark.parametrize("scripted", [False, True], ids=["template", "payscript"])
def test_booked_cms_replays_fixing_receivable_cash_and_pnl(native_recipe_client, monkeypatch, scripted):
    client = native_recipe_client
    body = _rates()
    body["market"]["volatility"] = 0
    body["terms"]["cashflows"][0].update(fixing=30 / 365, payment=60 / 365)
    if scripted:
        body["terms"]["cashflows"][0]["payscript"] = {
            "profile": "rates-exotic-coupon-v1", "source": 'AT CMS_COUPON:\n  PAY CMS_RATE * YEAR_FRACTION "Coupon CMS"',
        }
    body["terms"]["cashflows"].append({
        "kind": "fixed", "flow_id": "principal", "payment": 90 / 365, "amount_eur": 1_000_000, "is_coupon": False,
    })
    path, schedule, _, set_clock, mark, validate = _fixture(client, monkeypatch, body)
    A = mark(0, 16)
    assert A == mark(0, 16)
    assert A["result"]["state"] == "alive"
    set_clock(0, 17)
    assert mark(1, 16, 422)["detail"]["code"] == "EXOTIC_MTM_CUTOFF"
    fixing_payload = _proposal(schedule, "cms:fixing", {"kind": "rate_fixing", "rate_fraction": .024},
                               command_key="cms-actual-fixing")
    set_clock(30, 14)
    assert mark(30, 14, 422)["detail"]["code"] == "EXOTIC_FIXING_MISSING"
    fixing = validate(fixing_payload, 30)
    assert mark(30, 14, 422)["detail"]["code"] == "EXOTIC_FIXING_MISSING"
    fixed = mark(30, 15)
    coupon = next(flow for flow in fixed["result"]["flows"] if flow["flow_id"] == "cms")
    assert coupon["state"] == "receivable"
    assert coupon["fixing_fact_ids"] == [fixing["id"]]
    assert coupon["amount_eur"] == 6000
    assert coupon["pv_eur"] == pytest.approx(6000 * exp(-.02 * 30 / 365))
    assert fixed["result"]["cash_confirmed_eur"] == 0

    set_clock(60, 13)
    due = mark(60, 13)
    assert next(flow for flow in due["result"]["flows"] if flow["flow_id"] == "cms")["pv_eur"] == 6000
    payment = _proposal(schedule, "cms:payment", {"kind": "payment_confirmed", "amount_eur": 6000},
                        command_key="cms-actual-payment")
    assert client.post(path + "/facts", json={
        **payment, "fact": {"kind": "payment_confirmed", "amount_eur": 6001},
    }).json()["detail"]["code"] == "EXOTIC_FACT_PAYMENT_AMOUNT"
    paid_fact = validate(payment, 60)
    paid = mark(60, 15)
    assert paid["result"]["cash_confirmed_eur"] == 6000
    assert _pnl(client, path, due, paid)["contractual_pnl_eur"] == pytest.approx(0, abs=.000001)
    assert _pnl(client, path, paid, due)["cash_contractual_eur"] == -6000
    comparison = _pnl(client, path, due, paid)
    assert comparison["status"] == "attributed"
    assert comparison["cash"][0]["confirmation"]["fact_id"] == str(paid_fact["id"])
    assert comparison["residual_eur"] == 0
    assert mark(60, 13) == due

    principal = _proposal(schedule, "principal:payment", {"kind": "payment_confirmed", "amount_eur": 1_000_000},
                          command_key="cms-principal-payment")
    validate(principal, 90)
    closed = mark(90, 15)
    assert closed["result"]["state"] == "settled"
    assert closed["result"]["economic_dirty_pv_eur"] == 0
    assert closed["result"]["cash_confirmed_eur"] == 1_006_000
    assert len(client.session.exec(select(ValuationRun)).all()) == 5
    assert len(client.session.exec(select(NativeExoticLifecycleEntry)).all()) == 6
    assert not client.session.exec(select(DealEvent)).all()
    client.restore_archive()
    client.current["user"] = client.session.get(User, 1)
    replay = _response(client.post(path + f"/valuations/{paid['valuation_run_id']}/replay"))
    assert replay == {"matched": True, "valuation": paid}
    client.current["user"] = client.users["bob"]
    assert client.get(path + "/valuations").status_code == 404


def test_booked_cln_rolls_default_recovery_claim_and_late_payment(native_recipe_client, monkeypatch):
    client = native_recipe_client
    body = _credit()
    body["credit"]["contract"] = {
        "kind": "cln", "nominal_eur": 1_000_000, "maturity_years": 90 / 365, "side": "BUY",
        "coupon_bps": 400, "default_settlement_delay_years": 5 / 365,
        "coupons": [{"start": 0, "end": 20 / 365, "payment": 23 / 365, "year_fraction": 20 / 365},
                    {"start": 20 / 365, "end": 90 / 365, "payment": 90 / 365, "year_fraction": 70 / 365}],
    }
    body["credit"]["market"]["marginals"] = body["credit"]["market"]["marginals"][:1]
    body["credit"]["market"]["funding_bps"] = 40
    path, schedule, at, set_clock, mark, validate = _fixture(client, monkeypatch, body)
    assert mark(0, 16)["result"]["state"] == "alive"
    coupon = _proposal(schedule, "credit-coupon-1:payment", {"kind": "payment_confirmed", "amount_eur": 2191.78},
                       command_key="cln-first-coupon")
    validate(coupon, 23)
    alive = mark(23, 15)
    assert alive["result"]["cash_confirmed_eur"] == 2191.78

    def credit_fact(kind, effective, observed, **value):
        return {
            "command_key": f"cln-proof-{kind}", "expected_contract_version": 1, "schedule_fingerprint": schedule["fingerprint"],
            "event_id": f"credit:{kind}", "observed_at": at(observed, 9).isoformat(),
            "available_at": at(observed, 11).isoformat(), "source_reference": "Attestation de recette",
            "source_fingerprint": "b" * 64,
            "fact": {"kind": f"credit_{kind}", "reference_entity_id": "ALPHA", "effect_date": at(effective, 9).date().isoformat(), **value},
        }

    set_clock(31, 13)
    assert client.post(path + "/facts", json=credit_fact("recovery", 31, 31, recovery_fraction=.35)).json()[
        "detail"]["code"] == "EXOTIC_CLN_DEFAULT_REQUIRED"
    default_payload = credit_fact("default", 30, 31)
    wrong_ref = {**default_payload, "fact": {**default_payload["fact"], "reference_entity_id": "UNE-AUTRE"}}
    assert client.post(path + "/facts", json=wrong_ref).status_code == 422
    validate(default_payload, 31)
    pending = mark(31, 15)
    assert pending["result"]["state"] == "recovery_pending"
    assert pending["result"]["economic_dirty_pv_eur"] is None
    assert mark(30, 16)["result"]["state"] == "alive"
    validate(credit_fact("recovery", 32, 32, recovery_fraction=.35), 32)
    claim = mark(32, 15)
    assert claim["result"]["state"] == "settlement_pending"
    assert claim["result"]["economic_dirty_pv_eur"] == pytest.approx(350_000 * exp(-.024 * 3 / 365))
    assert not any(flow["flow_id"] == "credit-coupon-2" for flow in claim["result"]["flows"])
    assert _pnl(client, path, pending, claim)["status"] == "pending"
    set_clock(36, 13)
    overdue = mark(36, 13)
    assert overdue["result"]["economic_dirty_pv_eur"] == 350_000
    settlement = credit_fact("settlement", 36, 36, amount_eur=350_000)
    validate(settlement, 36)
    closed = mark(36, 15)
    assert closed["result"]["state"] == "settled"
    assert closed["result"]["economic_dirty_pv_eur"] == 0
    assert closed["result"]["cash_confirmed_eur"] == pytest.approx(352191.78)
    comparison = _pnl(client, path, overdue, closed)
    assert comparison["status"] == "attributed"
    assert comparison["cash_contractual_eur"] == 350_000
    assert comparison["contractual_pnl_eur"] == 0
    assert len(comparison["cash"]) == 1
    assert client.post(path + "/facts", json={**settlement, "command_key": "cln-duplicate-cash"}).status_code == 409
