"""Pricing summaries and AI advice derive context from authorized receipts."""

from copy import deepcopy

import pytest

from backend.app.services.llm import providers
from backend.tests.test_dated_exotic_rates import _dated_rates
from backend.tests.test_exotic_pricer_api import _credit, _rates
from backend.tests.test_native_reports import _draft
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


_EXOTICS = "/api/products/exotics"
_SUMMARY = _EXOTICS + "/summary"


def _json(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.parametrize(("body", "feature"), [(_rates, "CMS"), (_credit, "défaut de rang")])
def test_monte_carlo_summary_uses_the_signed_request_and_filters_other_users(product_client, body, feature):
    client = product_client
    priced = _json(client.post(_EXOTICS + "/price", json=body()))
    source = {"receipt": priced["receipt"]}
    summary = _json(client.post(_SUMMARY, json=source))
    assert feature.casefold() in summary["resume"].casefold()
    assert "marché synthétique" in summary["resume"]
    assert summary["result_fingerprint"] == priced["receipt"]["result_fingerprint"]
    tampered = deepcopy(source)
    tampered["receipt"]["request"]["position_id"] = "modification-non-signee"
    assert client.post(_SUMMARY, json=tampered).status_code == 422
    client.current["user"] = client.users["bob"]
    assert client.post(_SUMMARY, json=source).status_code == 404
    assert client.post(_SUMMARY + "/analyse/prompt", json=source).status_code == 404


def test_second_opinion_previews_exact_context_and_keeps_workbench_provenance(product_client, monkeypatch):
    client = product_client
    signed = _json(client.post(_EXOTICS + "/price", json=_rates()))["receipt"]
    request = {"receipt": signed, "intention": "libre", "question": "Quel risque est porté ?",
               "history": [{"question": "Quels flux ?", "answer": "Relire le coupon du reçu."}]}
    summary = _json(client.post(_SUMMARY, json=request))
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        return providers.Completion(text="  Avis simulé.  ", effective_model="model-fixture")

    monkeypatch.setattr(providers, "complete_with_metadata", complete)
    prompt = _json(client.post(_SUMMARY + "/analyse/prompt", json=request))
    assert not calls
    assert prompt["user"].endswith(summary["resume"])
    assert "Quels flux ?" in prompt["user"] and "Quel risque est porté ?" in prompt["user"]
    reply = _json(client.post(_SUMMARY + "/analyse", json=request))
    assert calls[0]["user"] == prompt["user"]
    assert reply["texte"] == "Avis simulé." and reply["effective_model"] == "model-fixture"
    assert reply["intention_label"] == "Question libre" and not reply["prompt_customized"]

    override = {name: prompt[name] for name in ("base_hash", "system", "user")}
    assert client.post(_SUMMARY + "/analyse", json={**request, "question": "Autre contexte",
                                                    "prompt_override": override}).status_code == 422
    assert len(calls) == 1


def test_rates_summary_lists_civil_fixing_and_payment_from_the_signed_schedule(product_client):
    priced = _json(product_client.post(_EXOTICS + "/price", json=_dated_rates()))
    summary = _json(product_client.post(_SUMMARY, json={"receipt": priced["receipt"]}))["resume"]
    assert "Période contractuelle du 2026-11-30 au 2027-11-30" in summary
    assert "fixing le 2027-05-27" in summary
    assert "paiement le 2027-12-03" in summary


@pytest.mark.parametrize(("family", "instrument", "case", "feature"), [
    ("rates", "FRN", None, "marge"),
    ("rates", "IRS", None, "receveur du fixe"),
    ("credit", "CDS", "ISDA-100", "Prime"),
    ("credit", "CLN", "JULY-PENDING", "Recouvrement en attente"),
])
def test_native_templates_use_their_signed_terms_and_measure(product_client, family, instrument, case, feature):
    client = product_client
    priced = _json(client.post(f"/api/products/{family}/price", json=_draft(client, family, instrument, scenario=case)))
    source = {"pricing_mode": "native", "family": family, "receipt": priced["receipt"]}
    result = _json(client.post(_SUMMARY, json=source))
    assert result["resume"].startswith(instrument + " —") and feature in result["resume"]
    assert "Mesure du prix" in result["resume"]
    assert client.post(_SUMMARY, json={**source, "family": "credit" if family == "rates" else "rates"}).status_code == 422


def test_summary_reopens_the_attested_monte_carlo_archive(native_recipe_client):
    client = native_recipe_client
    signed = _json(client.post(_EXOTICS + "/price", json=_rates()))["receipt"]
    kept = _json(client.post(_EXOTICS + "/conserve", json={
        "receipt": signed, "name": "Résumé archivé", "command_key": "summary-archive-01",
    }), 201)
    source = {"product_id": kept["product"]["product_id"], "calculation_id": kept["calculation_id"]}
    assert _json(client.post(_SUMMARY, json=source)) == _json(client.post(_SUMMARY, json={"receipt": signed}))
    assert client.post(_SUMMARY, json={**source, "calculation_id": source["calculation_id"] + 1}).status_code == 404


def test_native_summary_reopens_the_archived_calculation_after_key_rotation(native_recipe_client, monkeypatch):
    client = native_recipe_client
    draft = _draft(client, "rates", "FRN")
    product = _json(client.post("/api/products/native", json={
        "command_key": "summary-frn-create", "name": "FRN archivée",
        "terms": draft["terms"], "intent": draft["intent"],
    }), 201)
    product_id = product["product_id"]
    priced = _json(client.post("/api/products/rates/price", json={
        "case": "A", "product_id": product_id, "expected_revision": product["revision"],
        "expected_terms_version": product["terms_version"],
    }))
    kept = _json(client.post(f"/api/products/{product_id}/rates/calculations", json={
        "command_key": "summary-frn-retain", "expected_revision": product["revision"], "receipt": priced["receipt"],
    }), 201)
    mode = {"pricing_mode": "native", "family": "rates"}
    source = {**mode, "receipt": priced["receipt"]}
    summary = _json(client.post(_SUMMARY, json=source))
    monkeypatch.setattr("backend.app.api.exotic_summary.receipt_signing_secret", lambda: "key-rotation-test")
    archive = {**mode, "product_id": product_id, "calculation_id": kept["calculation_id"]}
    assert _json(client.post(_SUMMARY, json=archive)) == summary
    assert client.post(_SUMMARY, json=source).status_code == 422
