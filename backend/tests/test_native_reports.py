"""Signed deterministic regulatory drafts retain the evidence and its units."""
from copy import deepcopy

import pytest

from backend.app.core.valuation_context import json_transport_fingerprint
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


_ROOT = "/api/products"
_REPORTS = _ROOT + "/native-reports"
_DECISION = {"client_type": "professional", "channel": "advice", "experience": "advanced",
             "max_loss_fraction": 1, "tolerance": "high", "objective": "hedging",
             "horizon_years": 1, "negative_market": "Client sans capacité de perte"}


def _json(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def _draft(client, family, instrument, *, scenario=None):
    catalogue = _json(client.get(f"{_ROOT}/{family}/pilots"))["products"]
    pilot = next(row for row in catalogue if row["instrument_type"] == instrument)
    if family == "rates":
        return {"case": "A", "terms": pilot["terms"], "intent": pilot["intent"]}
    case = next(row for row in pilot["cases"] if row["id"] == scenario)
    return {"case": case["id"], "terms": case["terms"], "intent": case["intent"]}


@pytest.mark.parametrize(("family", "instrument", "case", "unit", "quality"), [
    ("rates", "FRN", None, "per_100_notional", "synthetic"),
    ("rates", "IRS", None, "EUR", "synthetic"),
    ("credit", "CDS", "ISDA-100", "per_100_notional", "published_historical_benchmark"),
    ("credit", "CLN", "JULY-PENDING", "EUR", "synthetic"),
])
def test_four_templates_prepare_both_drafts_from_actual_receipts(product_client, family, instrument, case, unit, quality):
    draft = _draft(product_client, family, instrument, scenario=case)
    price = _json(product_client.post(f"{_ROOT}/{family}/price", json=draft))
    source = {"family": family, "receipt": price["receipt"]}
    kid = _json(product_client.post(_REPORTS, json={**source, "report": "kid", "entry_cost_eur": 42}))
    assert kid["pricing_fingerprint"] == json_transport_fingerprint(price["receipt"])
    assert kid["report"]["measure"] == price["result"]["measure"]
    assert kid["report"]["measure"]["unit"] == unit
    assert kid["report"]["market_quality"] == quality and kid["report"]["instrument_type"] == instrument
    assert kid["report"]["status"] == "INDICATIVE_NON_PRIIPS"
    assert not kid["report"]["scenarios_available"] and "percentiles" not in kid["report"]
    assert kid["report"]["entry_cost_eur"] == 42 and kid["report"]["upfront_eur"] is None
    assert kid["receipt"]["result"]["pricing_fingerprint"] == kid["pricing_fingerprint"]
    if instrument == "CLN":
        assert kid["report"]["economic_pv_eur"] is None and kid["report"]["position_state"] == "recovery_pending"
    emt = _json(product_client.post(_REPORTS, json={**source, "report": "emt", "decision": _DECISION}))
    assert emt["report"]["status"] == "INDICATIVE_NON_FINDATEX"
    assert emt["report"]["decision"] == _DECISION and emt["report"]["matters_to_review"]


def test_rejects_wrong_family_owner_tampering_and_ambiguous_sources(product_client):
    priced = _json(product_client.post(f"{_ROOT}/rates/price", json=_draft(product_client, "rates", "FRN")))
    request = {"family": "rates", "report": "kid", "receipt": priced["receipt"]}
    wrong = {**request, "family": "credit"}
    assert product_client.post(_REPORTS, json=wrong).status_code == 422
    tampered = deepcopy(request)
    tampered["receipt"]["result"]["measure"]["value"] += 1
    assert product_client.post(_REPORTS, json=tampered).status_code == 422
    assert product_client.post(_REPORTS, json={**request, "product_id": 1, "calculation_id": 1}).status_code == 422
    product_client.current["user"] = product_client.users["bob"]
    assert product_client.post(_REPORTS, json=request).status_code == 404


def test_archive_draft_keeps_calculation_binding_and_survives_pricing_key_rotation(native_recipe_client, tmp_path, monkeypatch):
    client = native_recipe_client
    draft = _draft(client, "rates", "FRN")
    product = _json(client.post(f"{_ROOT}/native", json={"command_key": "reports-frn-create", "name": "FRN preuve",
                                                       "terms": draft["terms"], "intent": draft["intent"]}), 201)
    product_id = product["product_id"]
    price = _json(client.post(f"{_ROOT}/rates/price", json={"case": "A", "product_id": product_id,
                                                           "expected_revision": product["revision"],
                                                           "expected_terms_version": product["terms_version"]}))
    kept = _json(client.post(f"{_ROOT}/{product_id}/rates/calculations", json={"command_key": "reports-frn-retain",
                                                                            "expected_revision": product["revision"],
                                                                            "receipt": price["receipt"]}), 201)
    reference = {"family": "rates", "report": "kid", "product_id": product_id, "calculation_id": kept["calculation_id"]}
    monkeypatch.setattr("backend.app.api.native_reports.receipt_signing_secret", lambda: "rotated-report-recipe-key")
    monkeypatch.setattr("backend.app.api.documents._DOCS_DIR", tmp_path / "documents")
    report = _json(client.post(_REPORTS, json=reference))
    assert report["pricing_fingerprint"] == json_transport_fingerprint(price["receipt"])
    assert client.post(_REPORTS, json={"family": "rates", "report": "kid", "receipt": price["receipt"]}).status_code == 422
    keep = {**reference, "expected_revision": kept["product"]["revision"], "command_key": "reports-frn-document",
            "receipt": report["receipt"]}
    keep = {field: value for field, value in keep.items() if field not in ("family", "report")}
    stored = _json(client.post(_REPORTS + "/retain", json=keep), 201)
    assert _json(client.post(_REPORTS + "/retain", json=keep), 201) == stored
    assert stored["product"]["documents"][-1]["doc_type"] == "native_kid_draft"
    document = _json(client.get(f"/api/documents/{stored['document_id']}/download"))
    assert document == {"report": report["receipt"]["result"], "receipt": report["receipt"]}
    assert client.post(_REPORTS + "/retain", json={**keep, "calculation_id": kept["calculation_id"] + 20}).status_code == 404
