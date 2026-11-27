"""Retained exotic Product and atomic isolated booking with the usual Deal controls."""

from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlalchemy import text

from backend.app.db.models import BookingCommand, Counterparty, Deal, DealContractVersion, DealEvent, Entity, NativeExoticLifecycleEntry, User
from backend.app.hybrid.admin_workbench import AdminWorkbenchIdentity
from backend.app.hybrid.config import InstallationConfig
from backend.app.services import exotic_product_lifecycle
from backend.app.services.exotic_product_booking import is_native_exotic_deal
from backend.tests.test_exotic_pricer_api import _credit, _rates
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


def _response(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def _conserve(client, quote, *, key="conserve-exotic-witness"):
    return _response(client.post("/api/products/exotics/conserve", json={
        "name": "Témoin Monte Carlo", "command_key": key, "receipt": quote["receipt"],
    }), 201)


def test_exotic_product_persists_native_terms_and_receipt_without_booking(native_recipe_client, monkeypatch):
    client = native_recipe_client
    quote = _response(client.post("/api/products/exotics/price", json=_rates()))
    saved = _conserve(client, quote)
    assert saved == _conserve(client, quote)
    assert not client.session.exec(select(Deal)).all()
    product = saved["product"]
    assert product["terms"]["instrument_type"] == "EXOTIC_RATES"
    assert product["terms"]["clock"] == "ACT/365F"
    assert "nominal_eur" not in product["terms"]["contract"]
    assert "market" not in product["terms"]
    dates = product["native_schedule"]["legs"][0]["events"]
    assert any(item["model_time_years"] == 1.25 and item["date_projection"] == "nearest_calendar_day" for item in dates)
    assert not saved["booking_eligible"]
    detail = _response(client.get(f"/api/products/{product['product_id']}", params={"view": "mixed"}))
    assert detail["latest_price_unit"] == "EUR" and detail["latest_price"] == quote["result"]["pv_eur"]
    url = f"/api/products/{product['product_id']}/exotics/calculations/{saved['calculation_id']}"
    reopened = _response(client.get(url))
    assert reopened["result"] == quote["result"] and reopened["receipt"] == quote["receipt"]
    client.current["user"] = client.users["bob"]
    assert client.get(url).status_code == 404
    client.current["user"] = client.users["alice"]
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    assert not _response(client.get(url))["booking_eligible"]
    assert client.post("/api/products/exotics/conserve", json={
        "name": "Fermé", "command_key": "conserve-exotic-closed", "receipt": quote["receipt"],
    }).status_code == 403


def test_exotic_credit_contract_has_distinct_reference_and_payment_dates(native_recipe_client):
    client = native_recipe_client
    quote = _response(client.post("/api/products/exotics/price", json=_credit()))
    saved = _conserve(client, quote)
    terms = saved["product"]["terms"]
    assert terms["instrument_type"] == "EXOTIC_CREDIT"
    assert terms["reference_entities"] == sorted(terms["reference_entities"])
    assert len(terms["reference_entities"]) == 3
    events = saved["product"]["native_schedule"]["legs"][0]["events"]
    assert {"step_in", "protection_end", "cashflow", "accrual_end", "observation"} <= {item["kind"] for item in events}
    assert saved["transaction_format"] == "OTC"


def test_book_native_exotic_note_replays_receipt_once_and_freezes_deal(native_recipe_client):
    client = native_recipe_client
    client.session.add(Counterparty(id=1, name="Émetteur de recette", active=True))
    client.session.commit()
    body = _rates()
    body["position_id"] = "native-note"
    body["terms"]["cashflows"] = [
        {"kind": "fixed", "flow_id": "coupon", "payment": 1, "amount_eur": 40000, "is_coupon": True},
        {"kind": "fixed", "flow_id": "principal", "payment": 2, "amount_eur": 1000000, "is_coupon": False},
    ]
    priced = _response(client.post("/api/products/exotics/price", json=body))
    retained = _conserve(client, priced)
    assert retained["booking_eligible"]
    product = retained["product"]
    book = {
        "command_key": "book-exotic-signed-note", "calculation_id": retained["calculation_id"],
        "expected_revision": product["revision"], "expected_terms_version": product["terms_version"],
        "counterparty_id": 1, "execution_price_eur": 990000, "trade_date": body["valuation_date"], "value_date": body["valuation_date"],
    }
    route = f"/api/products/{product['product_id']}/exotics/book"
    assert client.post(route, json={**book, "value_date": "2026-11-24"}).status_code == 422
    assert not client.session.exec(select(Deal)).all()
    booked = _response(client.post(route, json=book), 201)
    assert booked == _response(client.post(route, json=book), 201)
    assert client.post(route, json={**book, "execution_price_eur": 990001}).status_code == 409
    assert len(client.session.exec(select(BookingCommand)).all()) == 1
    assert len(client.session.exec(select(Deal)).all()) == 1
    assert len(client.session.exec(select(DealContractVersion)).all()) == 1
    assert not client.session.exec(select(DealEvent)).all()
    detail = _response(client.get(f"/api/deals/{booked['deal_id']}"))
    assert detail["calendar_status"] == "FROZEN"
    assert detail["frozen_schedule"]["schedule"] == product["native_schedule"]
    assert detail["product_terms_version"] == product["terms_version"]
    assert detail["price_traded"] == 99
    assert detail["underlyings"] == []
    assert detail["market_data_provider"] == "synthetic"
    assert detail["market_snapshot"]["result_fingerprint"] == priced["receipt"]["result_fingerprint"]
    assert client.post(f"/api/deals/{booked['deal_id']}/events/refresh").json()["detail"]["code"] == "EXOTIC_LIFECYCLE_UNQUALIFIED"

    tampered = deepcopy(priced["receipt"])
    tampered["result"]["pv_eur"] = -1
    bad = client.post("/api/products/exotics/conserve", json={
        "name": "Corrompu", "command_key": "conserve-exotic-tamper", "receipt": tampered,
    })
    assert bad.status_code == 422


def _fact_deal(client, body):
    quote = _response(client.post("/api/products/exotics/price", json=body))
    retained = _conserve(client, quote)
    product = retained["product"]
    booked = _response(client.post(f"/api/products/{product['product_id']}/exotics/book", json={
        "command_key": "book-native-fact-note", "calculation_id": retained["calculation_id"],
        "expected_revision": product["revision"], "expected_terms_version": product["terms_version"],
        "counterparty_id": 1, "execution_price_eur": 990000,
        "trade_date": body["valuation_date"], "value_date": body["valuation_date"],
    }), 201)
    return booked["deal_id"], product["native_schedule"]


def _fact_test_users(client, monkeypatch):
    client.session.add(Entity(id=1, name="Recette lifecycle"))
    client.session.flush()
    maker = client.session.get(User, 1)
    maker.entity_id, maker.role = 1, "admin"
    checker = User(id=3, username="checker", email="checker@example.test", password_hash="test", role="checker", entity_id=1)
    client.session.add_all([maker, checker, Counterparty(id=1, name="Émetteur test", active=True)])
    client.session.commit()
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_USERS", "alice,checker")
    client.current["user"] = maker
    return maker, checker


def test_admin_workbench_books_in_common_booking_and_preserves_role_controls(native_recipe_client, monkeypatch):
    client = native_recipe_client
    maker, checker = _fact_test_users(client, monkeypatch)
    home = Path(os.environ["STRUCTURA_DATA_DIR"])
    config = InstallationConfig(installation_id=UUID(int=1), key="admin-workbench", name="Admin de test",
                                kind="platform", service="admin_workbench", data_dir=home, port=19808)
    manifest = home / "installation.json"
    manifest.write_text(config.model_dump_json(), encoding="utf-8")
    client.session.add(AdminWorkbenchIdentity(installation_id=str(config.installation_id), entity_id=maker.entity_id))
    client.session.commit()
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "admin_workbench")
    monkeypatch.setenv("STRUCTURA_ADMIN_WORKBENCH_CONFIG", str(manifest))
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "0")
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "0")
    capabilities = "/api/products/exotics/capabilities"
    assert not _response(client.get(capabilities))["supports_booking"]

    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "1")
    assert _response(client.get(capabilities))["supports_booking"]
    body = _rates()
    body["terms"]["cashflows"] = [
        {"kind": "fixed", "flow_id": "coupon", "payment": 1, "amount_eur": 40000, "is_coupon": True},
        {"kind": "fixed", "flow_id": "principal", "payment": 2, "amount_eur": 1000000, "is_coupon": False},
    ]
    deal, schedule = _fact_deal(client, body)
    detail = _response(client.get(f"/api/deals/{deal}"))
    assert detail["frozen_schedule"]["schedule"] == schedule
    assert detail["market_snapshot"]["booking_scope"] == "admin_workbench"
    assert _response(client.get(f"/api/deals/{deal}/exotics/facts"))["can_propose"]

    client.current["user"] = checker
    assert not _response(client.get(f"/api/deals/{deal}/exotics/facts"))["can_propose"]


def _proposal(schedule, event_id, fact, *, command_key):
    event = next(item for leg in schedule["legs"] for item in leg["events"] if item["event_id"] == event_id)
    day = event["date"]
    return {
        "command_key": command_key, "expected_contract_version": 1, "schedule_fingerprint": schedule["fingerprint"],
        "event_id": event_id, "observed_at": f"{day}T09:00:00+01:00", "available_at": f"{day}T11:00:00+01:00",
        "source_reference": "Fichier de recette validé", "source_fingerprint": "a" * 64, "fact": fact,
    }


def test_exotic_fact_rules_preserve_asof_and_maker_checker(native_recipe_client, monkeypatch):
    client = native_recipe_client
    maker, checker = _fact_test_users(client, monkeypatch)
    body = _rates()
    body["terms"]["cashflows"][0]["payment"] = 1.5 + .5 / 365
    body["terms"]["cashflows"].append({
        "kind": "fixed", "flow_id": "principal", "payment": 2, "amount_eur": 1_000_000, "is_coupon": False,
    })
    deal, schedule = _fact_deal(client, body)
    endpoint = f"/api/deals/{deal}/exotics/facts"
    fixing = _proposal(schedule, "cms:fixing", {"kind": "rate_fixing", "rate_fraction": .024},
                       command_key="propose-cms-fixing")
    now = datetime.fromisoformat(fixing["available_at"]).replace(minute=5)
    monkeypatch.setattr(exotic_product_lifecycle, "business_now", lambda: now)
    assert client.post(endpoint, json={**fixing, "schedule_fingerprint": "0" * 64}).status_code == 409
    proposed = _response(client.post(endpoint, json=fixing), 201)
    assert proposed == _response(client.post(endpoint, json=fixing), 201)
    decision_payload = {"decision": "validate", "reason": "Preuve contrôlée", "command_key": "validate-cms-fixing"}
    decision = f"{endpoint}/{proposed['id']}/decision"
    assert client.post(decision, json=decision_payload).json()["detail"]["code"] == "EXOTIC_FACT_FOUR_EYES"
    client.current["user"] = checker
    assert _response(client.get(f"/api/deals/{deal}"))["calendar_status"] == "FROZEN"
    assert not _response(client.get(endpoint))["can_propose"]
    assert _response(client.get(endpoint))["pending"][0]["can_decide"]
    assert client.post(endpoint, json=fixing).status_code == 403
    approval = now.replace(hour=16, minute=0)
    now = approval
    first = _response(client.post(decision, json=decision_payload))
    assert first == _response(client.post(decision, json=decision_payload))
    old = _response(client.get(endpoint, params={"cutoff": approval.replace(hour=15).isoformat()}))
    assert not old["eligible"] and [row["id"] for row in old["pending"]] == [proposed["id"]]
    eligible = _response(client.get(endpoint, params={"cutoff": approval.isoformat()}))["eligible"]
    assert [row["fact"]["rate_fraction"] for row in eligible] == [.024]
    assert eligible[0]["validated_by"] == checker.id

    client.current["user"] = maker
    variable = _proposal(schedule, "cms:payment", {"kind": "payment_confirmed", "amount_eur": 1},
                         command_key="propose-variable-cash")
    now = datetime.fromisoformat(variable["available_at"]).replace(hour=16)
    assert client.post(endpoint, json=variable).json()["detail"]["code"] == "EXOTIC_FACT_PAYMENT_AMOUNT"
    principal = _proposal(schedule, "principal:payment", {"kind": "payment_confirmed", "amount_eur": 999_999},
                          command_key="propose-fixed-cash")
    now = datetime.fromisoformat(principal["available_at"]).replace(hour=16)
    assert client.post(endpoint, json=principal).json()["detail"]["code"] == "EXOTIC_FACT_PAYMENT_AMOUNT"
    principal["fact"]["amount_eur"] = 1_000_000
    cash = _response(client.post(endpoint, json=principal), 201)
    client.current["user"] = checker
    _response(client.post(f"{endpoint}/{cash['id']}/decision", json={**decision_payload, "command_key": "validate-fixed-cash"}))
    assert len(client.session.exec(select(NativeExoticLifecycleEntry)).all()) == 4
    assert not client.session.exec(select(DealEvent)).all()
    assert client.session.get(Deal, deal).realized_payout is None
    with pytest.raises(IntegrityError, match="immuable"):
        client.session.execute(text("UPDATE native_exotic_lifecycle_entries SET command_key='changed' WHERE id=:id"), {"id": cash["id"]})
    client.session.rollback()


def test_exercise_settlement_waits_for_a_validated_notice(native_recipe_client, monkeypatch):
    client = native_recipe_client
    maker, checker = _fact_test_users(client, monkeypatch)
    body = _rates()
    body["terms"]["cashflows"] = [
        {"kind": "fixed", "flow_id": "coupon", "payment": 1, "amount_eur": 40000, "is_coupon": True},
        {"kind": "fixed", "flow_id": "principal", "payment": 2, "amount_eur": 1_000_000, "is_coupon": False},
    ]
    body["terms"]["exercises"] = [{
        "exercise_id": "call", "decision": 1, "settlement": 1, "redemption_eur": 1_000_000,
        "owner": "issuer", "coupon_priority": "before",
    }]
    body["settings"]["training_paths"] = 4096
    deal, schedule = _fact_deal(client, body)
    endpoint = f"/api/deals/{deal}/exotics/facts"
    notice = _proposal(schedule, "call:decision", {"kind": "exercise_notice", "exercised": True},
                       command_key="propose-call-notice")
    payment = _proposal(schedule, "call:settlement", {"kind": "payment_confirmed", "amount_eur": 1_000_000},
                        command_key="propose-call-cash")
    now = datetime.fromisoformat(notice["available_at"]).replace(hour=14)
    monkeypatch.setattr(exotic_product_lifecycle, "business_now", lambda: now)
    assert client.post(endpoint, json=payment).json()["detail"]["code"] == "EXOTIC_FACT_PAYMENT_UNQUALIFIED"
    proposed = _response(client.post(endpoint, json=notice), 201)
    client.current["user"] = checker
    _response(client.post(f"{endpoint}/{proposed['id']}/decision", json={
        "command_key": "validate-call-notice", "decision": "validate", "reason": "Avis émetteur rapproché",
    }))
    client.current["user"] = maker
    assert _response(client.post(endpoint, json=payment), 201)["status"] == "pending"
    assert client.session.get(Deal, deal).status == "actif"
    assert not client.session.exec(select(DealEvent)).all()


@pytest.mark.parametrize("market_snapshot", ["{", "[1]", "null"])
def test_legacy_deal_reads_unusable_market_without_exotic_classification(product_client, market_snapshot):
    assert not is_native_exotic_deal(Deal(product_id=1, user_id=1, reference="UNUSABLE", market_snapshot_json=market_snapshot))
    deal = Deal(user_id=1, reference="HISTORICAL-DEAL", market_snapshot_json=market_snapshot,
                script_snapshot="PARAM COUPON = 1%\nAT 1:\n  PAY COUPON")
    product_client.session.add(deal)
    product_client.session.commit()
    response = _response(product_client.get(f"/api/deals/{deal.id}"))
    assert response["market_snapshot"] == {}
    assert response["calendar_status"] == "UNAVAILABLE"
