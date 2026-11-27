"""Isolated PayScript baseline for the mixed Product reader."""

import hashlib
import hmac
import json
from datetime import date
from math import exp

import pytest
from sqlmodel import select

from backend.app.api.auth import receipt_signing_secret
from backend.app.core import instance_signing
from backend.app.core.product.models import ProductTerms
from backend.app.core.valuation_context import verify_pricing_receipt
from backend.app.db.models import Deal, ProductCalculationRun, ProductRevision, ProductTermsVersion, User
from backend.app.services.product_receipts import verify_server_receipt
from backend.tests.test_products import _browser_json_roundtrip, _create, _pricing_input, product_client


_PRICE = 0.970465
_TERMS_SHA256 = "1a081b0addf947f2b6dec0b39d0b831d3ce324bb48bad641655e0a7d6c76cb5c"
_IMPLICIT_TERMS_SHA256 = "2c08dfd4601ebf205c14638af0515a9f72cef252457bcf04939d03f82e105338"


def _historical_json(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("implicit_version", [False, True], ids=["explicit-v1", "implicit-v1"])
def test_retained_payscript_terms_receipt_and_deal_round_trip(product_client, implicit_version, monkeypatch):
    client = product_client
    monkeypatch.setattr(instance_signing, "current_config", lambda: None)
    monkeypatch.setattr(instance_signing, "_PROCESS_SECRET", "rates-credit-test-only-v2")
    request = _pricing_input(N=1000)
    response = client.post("/api/price", json=request)
    assert response.status_code == 200, response.text
    priced = response.json()
    elapsed = (date.fromisoformat(request["payment_date"]) - date.fromisoformat(request["value_date"])).days
    assert round(exp(-0.03 * elapsed / 365.25), 6) == _PRICE
    assert priced["price"] == _PRICE
    receipt = _browser_json_roundtrip(priced["pricing_receipt"])
    assert receipt["signature_version"] == 2
    verified = verify_server_receipt(receipt, secret=receipt_signing_secret())
    assert verify_pricing_receipt(verified)["result"]["price"] == _PRICE

    product = _create(client, receipt=receipt, pricing_input=receipt["pricing_input"])
    terms_row = client.session.exec(select(ProductTermsVersion)).one()
    assert (product["revision"], product["terms_version"]) == (2, 1)
    assert _digest(terms_row.terms_json) == terms_row.fingerprint == _TERMS_SHA256

    if implicit_version:
        # Seed the older wire shape in the fixture DB before any read of it.
        # Its stored fingerprint identifies the same effective v1 terms.
        historical = json.loads(terms_row.terms_json)
        del historical["schema_version"]
        terms_row.terms_json = _historical_json(historical)
        client.session.add(terms_row)
        client.session.commit()
        assert _digest(terms_row.terms_json) == _IMPLICIT_TERMS_SHA256

    retained_terms = (terms_row.terms_json, terms_row.fingerprint)
    product_id = product["product_id"]
    product_url = f"/api/products/{product_id}"
    deal_response = client.post("/api/deals", json={
        "product_id": product_id, "product_terms_version": 1,
        "sens": "vente", "contrepartie": "Banque Test", "counterparty_id": 1, "devise": "EUR",
        "nominal": 1_000_000, "fair_value": receipt["price_pct"], "price_traded": 97.0,
        "trade_date": request["strike_date"], "strike_date": request["strike_date"],
        "value_date": request["value_date"], "maturity_date": request["maturity_date"],
        "payment_date": request["payment_date"], "T": request["T"],
        "underlyings": product["terms"]["underlyings"], "observation_times": [1.0],
        "script_snapshot": request["script"], "market_snapshot": {}, "pricing_receipt": receipt,
        "transaction_format": "EMTN", "instrument_family": "NOTE",
    })
    assert deal_response.status_code == 201, deal_response.text
    deal_id = deal_response.json()["id"]

    # Release the ORM identity map before opening the retained records again.
    actor_id = client.current["user"].id
    other_actor_id = client.users["bob"].id
    client.session.expunge_all()
    client.current["user"] = client.session.get(User, actor_id)
    reopened = client.get(product_url)
    assert reopened.status_code == 200, reopened.text
    dossier = reopened.json()
    assert dossier["terms"] == product["terms"]
    assert ProductTerms.model_validate(dossier["terms"]).fingerprint == _TERMS_SHA256
    assert dossier["execution"]["deal_id"] == deal_id
    historical = client.get(f"{product_url}?revision=2&terms_version=1")
    assert historical.status_code == 200, historical.text
    assert historical.json()["terms"] == dossier["terms"]

    paged = client.get("/api/products?paged=true&limit=1").json()
    assert paged["items"] == client.get("/api/products?limit=1").json()
    assert paged["items"][0]["id"] == product_id
    assert paged["items"][0]["latest_price"] == pytest.approx(100 * _PRICE, rel=0, abs=1e-10)
    history = client.get(f"{product_url}/history?limit=1").json()
    assert history["items"][0]["revision"] == dossier["revision"] == 3
    assert history["has_more"]

    run = client.session.exec(select(ProductCalculationRun)).one()
    detail = client.get(f"{product_url}/calculations/{run.id}")
    assert detail.status_code == 200, detail.text
    saved = detail.json()
    assert saved["input_hash"] == receipt["input_fingerprint"]
    assert saved["result"] == verified["result"]
    assert (saved["product_id"], saved["terms_version"]) == (product_id, 1)

    deal = client.session.get(Deal, deal_id)
    assert (deal.product_id, deal.product_terms_version) == (product_id, 1)
    assert (deal.nominal, deal.sens) == (1_000_000, "vente")
    client.current["user"] = client.session.get(User, other_actor_id)
    assert client.get(product_url).status_code == 404
    assert client.get(f"{product_url}/calculations/{run.id}").status_code == 404

    client.session.expire_all()
    unchanged = client.session.exec(select(ProductTermsVersion)).one()
    assert (unchanged.terms_json, unchanged.fingerprint) == retained_terms
    assert len(client.session.exec(select(ProductRevision)).all()) == 3


def test_original_unversioned_receipt_signature_uses_historical_canonical_json():
    # The legacy signature covers the full body and preserves the JSON numeric type.
    pricing_input = {"r": 0.03, "T": 1.0, "N": 1000, "script": "AT MATURITY\n  PAY 1\n"}
    proof = {
        "version": 1,
        "pricing_input": pricing_input,
        "input_fingerprint": _digest(_historical_json(pricing_input)),
        "price_pct": 98.25,
        "market_snapshot": {},
    }
    key = "rates-credit-test-only-v1"
    signed_message = "product-pricing-v1:" + _historical_json(proof)
    signature = hmac.new(key.encode("utf-8"), signed_message.encode("utf-8"), hashlib.sha256).hexdigest()
    receipt = {**proof, "server_signature": signature}

    assert "signature_version" not in receipt
    assert verify_server_receipt(receipt, secret=key) == proof
    assert verify_pricing_receipt(proof)["input_fingerprint"] == proof["input_fingerprint"]
    with pytest.raises(ValueError):
        verify_server_receipt({**receipt, "price_pct": 95.0}, secret=key)
