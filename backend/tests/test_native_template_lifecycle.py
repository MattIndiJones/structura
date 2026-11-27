"""Validate contractual cash and lifecycle evidence from the common Booking deal."""

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pytest

from backend.app.db.models import Deal, User
from backend.app.services import exotic_product_lifecycle
from backend.tests.test_exotic_credit_calendar import _legal_otc_scope
from backend.tests.test_native_template_booking import _archive, _checked
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


_CENT = Decimal(".01")


@pytest.fixture
def booked_template(native_recipe_client, monkeypatch, instrument, case, execution_price):
    client = native_recipe_client
    _legal_otc_scope(client, scope=instrument)
    maker = client.session.get(User, 1)
    maker.role = "admin"
    checker = User(id=3, username="checker", email="checker@example.test", password_hash="test", role="checker", entity_id=1)
    client.session.add_all([maker, checker])
    client.session.commit()
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_USERS", "alice,checker")
    prefix, archive, _ = _archive(client, instrument, case)
    product = archive["product"]
    preview = _checked(client.get(f"{prefix}/native/booking", params={"calculation_id": archive["calculation_id"]}))
    assert preview["supported"], preview["diagnostics"]
    body = {
        "command_key": "native-template-booking", "calculation_id": archive["calculation_id"],
        "expected_revision": product["revision"], "expected_terms_version": product["terms_version"], "counterparty_id": 1,
        "execution_price_eur": execution_price, "trade_date": preview["trade_date"], "value_date": preview["value_date"],
    }
    if preview["transaction_format"] == "OTC":
        body.update(ccr_netting_set_id=1, documentation_reference="Accord cadre EUR de recette")
    booked = _checked(client.post(f"{prefix}/native/book", json=body), 201)
    deal_id = booked["deal_id"]
    endpoint = f"/api/deals/{deal_id}/exotics/facts"
    schedule_fingerprint = product["native_schedule"]["fingerprint"]
    return client, maker, checker, deal_id, endpoint, schedule_fingerprint, booked["product"]


def _assert_code(response, code, status=422):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def _at(monkeypatch, day, hour=16):
    current = datetime.fromisoformat(f"{day}T{hour:02}:00:00+00:00")
    monkeypatch.setattr(exotic_product_lifecycle, "business_now", lambda: current)
    return current


def _proposal(event_id, day, fact, schedule_fingerprint, suffix=""):
    return {
        "event_id": event_id, "fact": fact, "command_key": f"submit-{event_id}{suffix}",
        "expected_contract_version": 1, "schedule_fingerprint": schedule_fingerprint,
        "observed_at": f"{day}T09:00:00+00:00", "available_at": f"{day}T11:00:00+00:00",
        "source_reference": "Avis de recette signé", "source_fingerprint": "9" * 64,
    }


def _confirm(client, maker, checker, endpoint, proposal, action="validate"):
    client.current["user"] = maker
    evidence = _checked(client.post(endpoint, json=proposal), 201)
    client.current["user"] = checker
    url = f"{endpoint}/{evidence['id']}/decision"
    body = {"command_key": f"{action}-{evidence['id']}", "decision": action, "reason": "Avis vérifié et rapproché"}
    result = _checked(client.post(url, json=body))
    assert _checked(client.post(url, json=body)) == result
    client.current["user"] = maker
    return result


def _ledger(client, endpoint, **params):
    return _checked(client.get(endpoint, params=params))


def _events(ledger):
    return {row["event_id"]: row for row in ledger["contract_events"]}


def _payment(amount):
    return {"kind": "payment_confirmed", "amount_eur": amount}


@pytest.mark.parametrize(("instrument", "case", "execution_price", "flow", "amount"), [
    ("FRN", "A", 999_500, "frn-coupon-01", 8847.22),
    ("IRS", "A", 0, "irs-floating-01", -6319.44),
])
def test_floating_cash_requires_four_eyes_and_preserves_the_cutoff(
    booked_template, monkeypatch, instrument, flow, amount,
):
    client, maker, checker, deal_id, endpoint, fingerprint, product = booked_template
    observation_id, cash_id = f"{flow}:fixing", f"{flow}:payment"
    events = _events(_ledger(client, endpoint))
    fixing_date, payment_date = events[observation_id]["date"], events[cash_id]["date"]
    now = _at(monkeypatch, payment_date)
    ledger = _ledger(client, endpoint)
    assert _events(ledger)[cash_id]["state"] == "fixing_pending"
    assert _events(ledger)[cash_id]["expected_amount_eur"] is None
    cash = _proposal(cash_id, payment_date, _payment(amount), fingerprint)
    _assert_code(client.post(endpoint, json=cash), "NATIVE_FACT_FIXING_REQUIRED")

    fixing = _proposal(observation_id, fixing_date, {"kind": "rate_fixing", "rate_fraction": .025}, fingerprint)
    _assert_code(client.post(endpoint, json={**fixing, "schedule_fingerprint": "0" * 64}), "EXOTIC_FACT_SCOPE_STALE", 409)
    pending = _checked(client.post(endpoint, json=fixing), 201)
    assert _checked(client.post(endpoint, json=fixing), 201) == pending
    url = f"{endpoint}/{pending['id']}/decision"
    decision = {"command_key": "reject-first-fixing", "decision": "reject", "reason": "Rapport incomplet"}
    _assert_code(client.post(url, json=decision), "EXOTIC_FACT_FOUR_EYES", 403)
    client.current["user"] = checker
    _checked(client.post(url, json=decision))
    client.current["user"] = maker
    rejected = _ledger(client, endpoint)["history"][0]
    assert (rejected["status"], rejected["decided_by"], rejected["decision_reason"]) == ("rejected", checker.id, "Rapport incomplet")

    _at(monkeypatch, payment_date, 17)
    approved = _confirm(client, maker, checker, endpoint, {**fixing, "command_key": "submit-corrected-fixing"})
    previous = _ledger(client, endpoint, cutoff=now.isoformat())
    assert not previous["eligible"] and _events(previous)[observation_id]["state"] == "fixing_pending"
    assert _events(_ledger(client, endpoint))[cash_id]["expected_amount_eur"] == pytest.approx(amount, abs=.005)
    assert approved["validated_by"] == checker.id
    _assert_code(client.post(endpoint, json={**cash, "fact": _payment(-amount)}), "NATIVE_FACT_PAYMENT_AMOUNT")
    _confirm(client, maker, checker, endpoint, cash)
    row = _events(_ledger(client, endpoint))[cash_id]
    assert (row["state"], row["paid_amount_eur"]) == ("paid", amount)
    assert client.session.get(Deal, deal_id).status == "actif"
    dossier = _checked(client.get(f"/api/products/{product['product_id']}", params={"view": "mixed"}))
    assert dossier["revision"] == product["revision"] + 6
    assert dossier["lifecycle"]["native_ledger"]["schedule_fingerprint"] == fingerprint

    if instrument == "IRS":
        fixed = next(row for row in _events(_ledger(client, endpoint)).values() if row["leg_id"] == "fixed")
        assert fixed["accrual_start"] < fixed["accrual_end"] <= fixed["date"]
        assert fixed["expected_amount_eur"] == pytest.approx(25302.1092847019)


@pytest.mark.parametrize(("instrument", "case", "execution_price"), [
    ("CDS", "ISDA-150", -238235.61), ("CLN", "INITIAL-DATED", 1_001_000),
])
def test_credit_default_preserves_acquired_cash_and_closes_only_on_verified_settlement(
    booked_template, monkeypatch, instrument, execution_price,
):
    client, maker, checker, deal_id, endpoint, fingerprint, product = booked_template
    ledger = _ledger(client, endpoint)
    coupons = [row for row in ledger["contract_events"] if row["kind"] == "cashflow"]
    earned, disrupted = coupons[:2]
    default_date = (datetime.fromisoformat(disrupted["accrual_start"]) + timedelta(days=10)).date().isoformat()
    _at(monkeypatch, default_date)
    if instrument == "CDS":
        upfront = next(row for row in ledger["contract_events"] if row["kind"] == "initial_settlement")
        assert upfront["expected_amount_eur"] == execution_price
        _confirm(client, maker, checker, endpoint, _proposal(upfront["event_id"], upfront["date"], _payment(execution_price), fingerprint))
    _confirm(client, maker, checker, endpoint, _proposal(earned["event_id"], earned["date"], _payment(earned["expected_amount_eur"]), fingerprint))
    target = _ledger(client, endpoint)["credit_targets"][0]
    event_id = target["event_id"]
    base = {"effect_date": default_date, "reference_entity_id": target["reference_entity_id"]}
    wrong = {"kind": "credit_default", **base, "reference_entity_id": "wrong-entity"}
    _assert_code(client.post(endpoint, json=_proposal(event_id, default_date, wrong, fingerprint)), "NATIVE_CREDIT_REFERENCE")
    _confirm(client, maker, checker, endpoint, _proposal(event_id, default_date, {"kind": "credit_default", **base}, fingerprint))
    at_default = _ledger(client, endpoint)
    rows = _events(at_default)
    assert rows[earned["event_id"]]["state"] == "paid"
    assert rows[disrupted["event_id"]]["state"] == "cancelled"
    assert all(row["state"] == "cancelled" for row in rows.values() if row["kind"] == "principal")
    assert client.session.get(Deal, deal_id).status == "actif"
    _confirm(client, maker, checker, endpoint, _proposal(
        at_default["credit_targets"][0]["event_id"], default_date,
        {"kind": "credit_recovery", **base, "recovery_fraction": .40}, fingerprint,
    ))
    settlement = _ledger(client, endpoint)["credit_targets"][0]
    if instrument == "CLN":
        assert settlement["expected_amount_eur"] == 400_000
        assert settlement["earliest_effect_date"] > default_date
    else:
        accrued = (-Decimal(10_000_000) * Decimal(".01") * 10 / 360).quantize(_CENT, rounding=ROUND_HALF_UP)
        assert settlement["expected_amount_eur"] == float(Decimal(6_000_000) + accrued)
    effective = settlement["earliest_effect_date"]
    to_pay = _events(_ledger(client, endpoint))[settlement["event_id"]]
    assert to_pay["date"] == effective and to_pay["paid_amount_eur"] is None
    now = _at(monkeypatch, effective, 17)
    payment = {"kind": "credit_settlement", **base, "effect_date": effective, "amount_eur": settlement["expected_amount_eur"]}
    _assert_code(client.post(endpoint, json=_proposal(settlement["event_id"], effective, {**payment, "amount_eur": 10}, fingerprint)),
                 "NATIVE_FACT_PAYMENT_AMOUNT")
    _assert_code(client.post(endpoint, json=_proposal(disrupted["event_id"], disrupted["date"], _payment(0), fingerprint)),
                 "NATIVE_FACT_DATE_OR_KIND")
    proposed = _proposal(settlement["event_id"], effective, payment, fingerprint)
    approved = _confirm(client, maker, checker, endpoint, proposed)
    assert _checked(client.post(endpoint, json=proposed), 201) == approved
    deal = _checked(client.get(f"/api/deals/{deal_id}"))
    assert (deal["status"], deal["resolution_outcome"], deal["settlement_date"]) == ("échu", "défaut", effective)
    ledger = _ledger(client, endpoint)
    assert not ledger["can_propose"] and not ledger["credit_targets"]
    assert _events(ledger)[settlement["event_id"]]["paid_amount_eur"] == settlement["expected_amount_eur"]
    frozen = _ledger(client, endpoint, cutoff=(now - timedelta(seconds=1)).isoformat())
    assert _events(frozen)[settlement["event_id"]]["state"] != "paid"
