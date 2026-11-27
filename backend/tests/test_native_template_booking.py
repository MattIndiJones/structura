"""Book all four deterministic templates through their signed Product receipt."""

import pytest
from sqlmodel import select

from backend.app.db.models import Deal, DealContractVersion
from backend.app.services.lifecycle_alerts import refresh_book
from backend.tests.test_exotic_credit_calendar import _legal_otc_scope
from backend.tests.test_products import _browser_json_roundtrip, product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


def _checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def _archive(client, instrument, case):
    family = "rates" if instrument in ("FRN", "IRS") else "credit"
    pricer = f"/api/products/{family}"
    catalogue = _checked(client.get(f"{pricer}/pilots"))
    assert catalogue["booking"]["supported"]
    pilot = next(pilot for pilot in catalogue["products"] if pilot["instrument_type"] == instrument)
    draft = pilot if family == "rates" else next(item for item in pilot["cases"] if item["id"] == case)
    product = _checked(client.post("/api/products/native", json={
        "name": pilot["name"], "terms": draft["terms"], "intent": draft["intent"], "command_key": "create-template",
    }), 201)
    prefix = f"/api/products/{product['product_id']}"
    price = _checked(client.post(f"{pricer}/price", json={
        "case": case, "product_id": product["product_id"], "expected_revision": product["revision"],
        "expected_terms_version": product["terms_version"],
    }))
    archive = _checked(client.post(f"{prefix}/{family}/calculations", json=_browser_json_roundtrip({
        "command_key": "retain-template", "expected_revision": product["revision"], "receipt": price["receipt"],
    })), 201)
    return prefix, archive, price


@pytest.mark.parametrize(("instrument", "case", "trade_price"), [
    ("FRN", "A", 999_500), ("IRS", "A", 0), ("CDS", "INITIAL-DATED", -900),
    ("CLN", "INITIAL-DATED", 1_001_000), ("CDS", "ISDA-150", -238_235.61),
])
def test_template_booking_freezes_receipt_and_contract_once(native_recipe_client, instrument, case, trade_price):
    client = native_recipe_client
    _legal_otc_scope(client, scope=instrument)
    prefix, archive, price = _archive(client, instrument, case)
    product = archive["product"]
    calculation_id = archive["calculation_id"]
    preview_url = f"{prefix}/native/booking?calculation_id={calculation_id}"
    preview = _checked(client.get(preview_url))
    schedule = product["native_schedule"]
    is_otc = instrument in {"IRS", "CDS"}
    assert preview["supported"], preview["diagnostics"]
    assert preview["transaction_format"] == ("OTC" if is_otc else "NOTE")
    assert preview["effective_date"] == product["terms"]["effective_date"]
    assert preview["trade_date"] == price["context"]["valuation_date"]
    if instrument == "CDS":
        settlement = next(event for leg in schedule["legs"] for event in leg["events"]
                          if event["kind"] == "initial_settlement")
        assert preview["value_date"] == settlement["date"] > preview["trade_date"]
        assert preview["protection_start_date"] == product["terms"]["effective_date"]
    body = {"command_key": "book-template", "calculation_id": calculation_id, "expected_revision": product["revision"],
            "expected_terms_version": product["terms_version"], "counterparty_id": 1, "execution_price_eur": trade_price,
            "trade_date": preview["trade_date"], "value_date": preview["value_date"]}
    path = f"{prefix}/native/book"
    if is_otc:
        assert client.post(path, json=body).status_code == 422
        assert not client.session.exec(select(Deal)).all()
        body.update(ccr_netting_set_id=1, documentation_reference="Accord OTC EUR de recette")
    assert client.post(path, json={**body, "value_date": "2099-01-01"}).status_code == 422
    booked = _checked(client.post(path, json=body), 201)
    assert _checked(client.post(path, json=body), 201) == booked
    assert client.post(path, json={**body, "execution_price_eur": trade_price + 1}).status_code == 409
    assert booked["product"]["terms_version"] == product["terms_version"]
    row = client.session.exec(select(Deal)).one()
    assert client.session.exec(select(DealContractVersion)).one().deal_id == row.id
    detail_url = f"/api/deals/{booked['deal_id']}"
    detail = _checked(client.get(detail_url))
    assert detail["frozen_schedule"] == {"profile": "native_template_v1", "schedule": schedule}
    assert (detail["strike_date"], detail["maturity_date"]) == (preview["effective_date"], preview["maturity_date"])
    evidence = detail["market_snapshot"]
    assert evidence["execution_price_eur"] == trade_price
    assert evidence["economic_dirty_pv_eur"] == preview["fair_value_eur"]
    if instrument == "CDS":
        assert evidence["initial_settlement_eur"] == trade_price
        assert detail["price_traded"] == pytest.approx(-100 * trade_price / row.nominal)
        assert detail["margin"] == round(100 * (preview["fair_value_eur"] + evidence["initial_settlement_pv_eur"]) / row.nominal, 4)
        if case == "ISDA-150":
            assert detail["margin"] == pytest.approx(0, abs=.0001)
    assert not _checked(client.get(preview_url))["supported"]
    assert refresh_book(client.session)["coverage"]["total"] == 0
    assert client.post(f"{detail_url}/events/refresh").json()["detail"]["code"] == "EXOTIC_LIFECYCLE_UNQUALIFIED"


@pytest.mark.parametrize(("instrument", "case"), [("FRN", "C"), ("CDS", "SURVIVAL-PAR"), ("CLN", "JULY-PAID")])
def test_historical_pricing_controls_remain_readable_without_booking(native_recipe_client, instrument, case):
    client = native_recipe_client
    prefix, archive, _ = _archive(client, instrument, case)
    preview = _checked(client.get(f"{prefix}/native/booking", params={"calculation_id": archive["calculation_id"]}))
    assert not preview["supported"] and preview["diagnostics"]
    assert not client.session.exec(select(Deal)).all()
