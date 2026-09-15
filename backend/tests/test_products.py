"""The retained Product is explicit, immutable and isolated from market data."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api.auth import get_current_user, receipt_signing_secret
from backend.app.core.product.models import FrozenObject
from backend.app.core.schemas import PricingRequest
from backend.app.core.valuation_context import (
    build_pricing_receipt, canonical_fingerprint, pricing_input_payload,
)
from backend.app.db.database import get_session
from backend.app.db.models import (
    Counterparty, Deal, ProductCalculationRun, ProductRecord,
    ProductTermsVersion, RfqRequest, User,
)
from backend.app.services.product_receipts import signed_receipt


def _pricing_input(**overrides):
    payload = {
        "script": "# Autocall test\nAT MATURITY\n  PAY 1\n",
        "underlyings": [{
            "name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR",
            "s0": 1.0, "sigma": 0.20, "q": 0.01,
        }],
        "corr_matrix": [[1.0]],
        "r": 0.03, "T": 1.0, "N": 2000, "model": "constant",
        "strike_date": "2026-09-14", "value_date": "2026-09-16",
        "maturity_date": "2027-09-14", "payment_date": "2027-09-16",
        "settlement_ccy": "EUR",
    }
    payload.update(overrides)
    return PricingRequest.model_validate(payload).model_dump(mode="json")


@pytest.fixture
def product_client(monkeypatch, tmp_path):
    import backend.app.db.database as db
    import backend.app.api.documents as documents_api
    from backend.app.main import app

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(documents_api, "_DOCS_DIR", tmp_path / "documents")
    session = Session(engine)
    alice = User(id=1, username="alice", email="alice@desk.com",
                 password_hash="x", role="user", entity_id=None)
    bob = User(id=2, username="bob", email="bob@desk.com",
               password_hash="x", role="user", entity_id=None)
    session.add_all([alice, bob])
    session.add(Counterparty(id=1, name="Banque Test", active=True))
    session.commit()
    current = {"user": alice}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(app)
    client.session = session
    client.current = current
    client.users = {"alice": alice, "bob": bob}
    yield client
    app.dependency_overrides.clear()
    session.close()


def _create(client, *, key="create-product-001", receipt=None, pricing_input=None):
    response = client.post("/api/products", json={
        "command_key": key,
        "name": "Autocall Euro Stoxx",
        "pricing_input": pricing_input or _pricing_input(),
        "pricing_receipt": receipt,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _browser_json_roundtrip(value):
    """Model JSON.stringify: integral JavaScript numbers are posted as ints."""
    if isinstance(value, dict):
        return {key: _browser_json_roundtrip(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_browser_json_roundtrip(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def test_conservation_sans_prix_ne_stocke_que_les_termes(product_client):
    product = _create(product_client)
    assert product["revision"] == 1
    assert product["reference"].startswith("PRD-")
    assert product["calculations"] == []

    terms = product_client.session.exec(select(ProductTermsVersion)).one()
    saved = json.loads(terms.terms_json)
    assert saved["underlyings"] == [{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}]
    assert "sigma" not in terms.terms_json
    assert "corr_matrix" not in terms.terms_json
    assert "r" not in saved


def test_prix_signe_est_conserve_comme_calcul_separe(product_client):
    request = PricingRequest.model_validate(_pricing_input())
    receipt = signed_receipt(
        build_pricing_receipt(request, 0.9825),
        secret=receipt_signing_secret(), result={"price": 0.9825},
    )
    product = _create(product_client, key="create-product-priced", receipt=receipt)
    assert product["revision"] == 2
    assert product["calculations"][0]["price"] == pytest.approx(98.25)

    run = product_client.session.exec(select(ProductCalculationRun)).one()
    assert json.loads(run.input_json)["underlyings"][0]["sigma"] == pytest.approx(0.20)
    detail = product_client.get(
        f"/api/products/{product['product_id']}/calculations/{run.id}")
    assert detail.status_code == 200
    assert detail.json()["result"]["price"] == pytest.approx(0.9825)
    market = detail.json()["market_snapshot"]
    assert market["r"] == pytest.approx(3.0)
    assert market["underlyings"][0]["sigma"] == pytest.approx(20.0)
    assert market["underlyings"][0]["q"] == pytest.approx(1.0)
    assert market["corrMatrix"] == [[1.0]]


def test_recu_du_pricing_http_peut_etre_conserve_tel_quel(product_client):
    pricing_input = _pricing_input(N=1000)
    priced = product_client.post("/api/price", json=pricing_input)
    assert priced.status_code == 200, priced.text
    receipt = priced.json()["pricing_receipt"]
    assert receipt["signature_version"] == 2

    product = _create(
        product_client, key="product-from-http-receipt",
        receipt=receipt, pricing_input=receipt["pricing_input"])
    assert product["calculations"][0]["price"] == pytest.approx(priced.json()["price"] * 100)


def test_recu_pricing_supporte_un_roundtrip_json_navigateur(product_client):
    pricing_input = _pricing_input(N=1000)
    priced = product_client.post("/api/price", json=pricing_input)
    assert priced.status_code == 200, priced.text

    receipt = _browser_json_roundtrip(priced.json()["pricing_receipt"])
    product = _create(
        product_client, key="product-from-browser-receipt",
        receipt=receipt, pricing_input=receipt["pricing_input"])
    assert product["calculations"][0]["price"] == pytest.approx(priced.json()["price"] * 100)


def test_preuve_ancienne_reste_valide_apres_roundtrip_navigateur(product_client):
    request = PricingRequest.model_validate(_pricing_input(N=1000))
    legacy_input = pricing_input_payload(request)
    legacy_receipt = build_pricing_receipt(request, 0.9825)
    legacy_receipt["input_fingerprint"] = canonical_fingerprint(legacy_input)
    legacy_receipt["market_snapshot"]["pricing_input_fingerprint"] = legacy_receipt["input_fingerprint"]
    receipt = signed_receipt(
        legacy_receipt, secret=receipt_signing_secret(), result={"price": 0.9825})
    receipt = _browser_json_roundtrip(receipt)

    product = _create(
        product_client, key="product-from-legacy-browser-receipt",
        receipt=receipt, pricing_input=receipt["pricing_input"])
    assert product["calculations"][0]["price"] == pytest.approx(98.25)


def test_prix_entier_reste_signe_apres_roundtrip_navigateur(product_client):
    request = PricingRequest.model_validate(_pricing_input(N=1000))
    receipt = signed_receipt(
        build_pricing_receipt(request, 1.0),
        secret=receipt_signing_secret(), result={"price": 1.0})
    receipt = _browser_json_roundtrip(receipt)

    product = _create(
        product_client, key="product-from-integral-price",
        receipt=receipt, pricing_input=receipt["pricing_input"])
    assert product["calculations"][0]["price"] == pytest.approx(100.0)


def test_recu_modifie_est_refuse_et_transaction_annulee(product_client):
    request = PricingRequest.model_validate(_pricing_input())
    receipt = signed_receipt(
        build_pricing_receipt(request, 1.0), secret=receipt_signing_secret())
    receipt["price_pct"] = 50
    response = product_client.post("/api/products", json={
        "command_key": "tampered-product",
        "pricing_input": _pricing_input(),
        "pricing_receipt": receipt,
    })
    assert response.status_code == 422
    assert product_client.session.exec(select(ProductRecord)).all() == []


def test_creation_idempotente_et_cle_reutilisee_avec_autre_contenu_refusee(product_client):
    first = _create(product_client, key="idempotent-product")
    second = _create(product_client, key="idempotent-product")
    assert second["product_id"] == first["product_id"]
    assert len(product_client.session.exec(select(ProductRecord)).all()) == 1

    response = product_client.post("/api/products", json={
        "command_key": "idempotent-product",
        "name": "Autre nom",
        "pricing_input": _pricing_input(),
    })
    assert response.status_code == 409


def test_produit_d_un_autre_utilisateur_repond_404(product_client):
    product = _create(product_client)
    product_client.current["user"] = product_client.users["bob"]
    response = product_client.get(f"/api/products/{product['product_id']}")
    assert response.status_code == 404


def test_composition_du_pricing_reinjecte_le_marche_sans_modifier_les_termes(product_client):
    product = _create(product_client)
    market = _pricing_input()
    context = {key: value for key, value in market.items() if key not in {
        "script", "user_params", "constats", "T", "strike_date", "value_date",
        "maturity_date", "payment_date", "anchor", "settlement_ccy", "frozen_schedule",
    }}
    context["underlyings"] = [{
        key: value for key, value in market["underlyings"][0].items()
        if key not in {"name", "ticker", "ccy"}
    }]
    response = product_client.post(
        f"/api/products/{product['product_id']}/pricing-input", json={
            "expected_terms_version": product["terms_version"], "context": context})
    assert response.status_code == 200, response.text
    composed = response.json()
    assert composed["underlyings"][0]["name"] == "SX5E"
    assert composed["underlyings"][0]["sigma"] == pytest.approx(0.20)
    assert composed["frozen_schedule"]["version"] == 1

    context["script"] = "AT MATURITY\n  PAY 0"
    refused = product_client.post(
        f"/api/products/{product['product_id']}/pricing-input", json={
            "expected_terms_version": product["terms_version"], "context": context})
    assert refused.status_code == 422


def test_repricing_date_est_ajoute_sans_modifier_les_termes(product_client):
    product = _create(product_client, key="product-for-repricing")
    repricing = _pricing_input(
        r=0.035,
        underlyings=[{
            "name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR",
            "s0": 1.02, "sigma": 0.24, "q": 0.012,
        }],
    )
    receipt = signed_receipt(
        build_pricing_receipt(PricingRequest.model_validate(repricing), 0.971),
        secret=receipt_signing_secret(), result={"price": 0.971},
    )
    body = {
        "command_key": "retain-repricing-001",
        "expected_revision": product["revision"],
        "pricing_receipt": receipt,
    }
    response = product_client.post(
        f"/api/products/{product['product_id']}/calculations", json=body)
    assert response.status_code == 200, response.text
    repriced = response.json()
    assert repriced["revision"] == 2
    assert repriced["terms_version"] == 1
    assert repriced["calculations"][-1]["price"] == pytest.approx(97.1)

    repeated = product_client.post(
        f"/api/products/{product['product_id']}/calculations", json=body)
    assert repeated.status_code == 200
    assert len(product_client.session.exec(select(ProductCalculationRun)).all()) == 1


def test_repricing_sur_d_autres_termes_est_refuse(product_client):
    product = _create(product_client, key="product-for-wrong-repricing")
    other = _pricing_input(script="# Autre produit\nAT MATURITY\n  PAY 0.5\n")
    receipt = signed_receipt(
        build_pricing_receipt(PricingRequest.model_validate(other), 0.5),
        secret=receipt_signing_secret(), result={"price": 0.5},
    )
    response = product_client.post(
        f"/api/products/{product['product_id']}/calculations", json={
            "command_key": "retain-wrong-repricing",
            "expected_revision": product["revision"],
            "pricing_receipt": receipt,
        })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PRODUCT_CALCULATION_TERMS_MISMATCH"
    assert product_client.session.exec(select(ProductCalculationRun)).all() == []


def test_frozen_object_ne_partage_pas_ses_structures_internes():
    frozen = FrozenObject({"rows": [{"date": "2027-01-01"}]})
    projection = frozen.to_dict()
    projection["rows"][0]["date"] = "2099-01-01"
    assert frozen.to_dict()["rows"][0]["date"] == "2027-01-01"


def test_rfq_consomme_les_termes_du_product_et_l_enrichit(product_client):
    product = _create(product_client, key="product-for-rfq")
    response = product_client.post("/api/rfq", json={
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "name": "AO depuis Product",
        "kind": "indicatif",
        "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 0",
        "params": {
            "underlyings": [{"sigma": 0.24, "q": 0.01}],
            "corr_matrix": [[1.0]], "r": 0.03, "N": 2000,
            "model": "constant",
        },
    })
    assert response.status_code == 201, response.text
    rfq = response.json()
    assert rfq["product_id"] == product["product_id"]
    assert rfq["script_snapshot"] == product["terms"]["script"]
    assert rfq["params"]["underlyings"][0]["name"] == "SX5E"

    refreshed = product_client.get(f"/api/products/{product['product_id']}").json()
    assert refreshed["revision"] == 2
    assert refreshed["rfqs"][0]["reference"] == rfq["reference"]


def test_booking_direct_rattache_l_execution_au_product(product_client):
    pricing_input = _pricing_input()
    request = PricingRequest.model_validate(pricing_input)
    receipt = signed_receipt(
        build_pricing_receipt(request, 0.9825),
        secret=receipt_signing_secret(), result={"price": 0.9825},
    )
    product = _create(
        product_client, key="product-for-booking",
        receipt=receipt, pricing_input=pricing_input)
    response = product_client.post("/api/deals", json={
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "sens": "vente", "contrepartie": "Banque Test", "devise": "EUR",
        "nominal": 1_000_000, "fair_value": 98.25, "price_traded": 98.20,
        "trade_date": "2026-09-14", "strike_date": "2026-09-14",
        "value_date": "2026-09-16", "maturity_date": "2027-09-14",
        "payment_date": "2027-09-16", "T": 1.0,
        "underlyings": [{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}],
        "observation_times": [1.0],
        "script_snapshot": pricing_input["script"],
        "market_snapshot": {}, "pricing_receipt": receipt,
    })
    assert response.status_code == 201, response.text
    deal = response.json()
    assert deal["product_id"] == product["product_id"]
    assert deal["product_terms_version"] == product["terms_version"]

    refreshed = product_client.get(f"/api/products/{product['product_id']}").json()
    assert refreshed["execution"]["deal_id"] == deal["id"]
    assert refreshed["intent"]["counterparty_id"] == 1
    assert refreshed["lifecycle"]["deal_status"] == "actif"
    assert any(event["label"] == "Maturité"
               for event in refreshed["lifecycle"]["events"])
    assert refreshed["revision"] == 3


def test_booking_direct_refuse_un_recu_non_signe(product_client):
    pricing_input = _pricing_input()
    unsigned_receipt = build_pricing_receipt(
        PricingRequest.model_validate(pricing_input), 0.9825)
    product = _create(product_client, key="product-for-unsigned-booking")
    response = product_client.post("/api/deals", json={
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "sens": "vente", "contrepartie": "Banque Test", "devise": "EUR",
        "nominal": 1_000_000, "fair_value": 98.25, "price_traded": 98.20,
        "trade_date": "2026-09-14", "strike_date": "2026-09-14",
        "value_date": "2026-09-16", "maturity_date": "2027-09-14",
        "payment_date": "2027-09-16", "T": 1.0,
        "underlyings": [{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}],
        "observation_times": [1.0], "script_snapshot": pricing_input["script"],
        "market_snapshot": {}, "pricing_receipt": unsigned_receipt,
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PRODUCT_PRICING_RECEIPT_INVALID"
    assert product_client.session.exec(select(Deal)).all() == []


def test_kid_et_emt_s_attachent_directement_au_product(product_client):
    product = _create(product_client, key="product-for-documents")
    kid = product_client.post("/api/kid/save", json={
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "product_title": product["name"],
        "sri": 4, "mrm": 4, "crm": 2, "vev": 0.15, "T_rhp": 1.0,
        "horizons": [], "costs": {},
    })
    assert kid.status_code == 201, kid.text
    assert kid.json()["product_id"] == product["product_id"]

    emt = product_client.post("/api/emt/save", json={
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "product_title": product["name"],
        "sri": 4, "mrm": 4, "crm": 2, "T_rhp": 1.0,
        "capital_tier": "indetermine", "capital_label": "Non garanti",
        "knowledge_tier": "avance", "knowledge_label": "Client averti",
        "risk_tolerance": "Perte en capital", "objective": "Croissance",
    })
    assert emt.status_code == 201, emt.text
    assert emt.json()["product_id"] == product["product_id"]

    refreshed = product_client.get(f"/api/products/{product['product_id']}").json()
    assert [document["kind"] for document in refreshed["documents"]] == ["KID", "EMT"]
    assert refreshed["revision"] == 3


def test_calcul_emt_prend_les_termes_du_product_comme_autorite(product_client):
    product = _create(product_client, key="product-for-emt-compute")
    request = _pricing_input(
        script="# Corps client divergent\nAT MATURITY\n  PAY 0.5\n",
        T=2.0,
        maturity_date="2028-09-14",
    )
    request.update({
        "product_id": product["product_id"],
        "product_terms_version": product["terms_version"],
        "sri": 4, "mrm": 4, "crm": 2,
    })
    response = product_client.post("/api/emt/compute", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["T_rhp"] == pytest.approx(product["terms"]["T"])


def test_document_product_est_telechargeable_et_historique(product_client):
    product = _create(product_client, key="product-for-upload")
    response = product_client.post(
        "/api/documents",
        params={
            "title": "Term sheet",
            "doc_type": "termsheet_indicatif",
            "product_id": product["product_id"],
            "product_terms_version": product["terms_version"],
        },
        files={"file": ("term-sheet.pdf", b"document-test", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["product_id"] == product["product_id"]
    assert product_client.get(
        f"/api/documents/{document['id']}/download").content == b"document-test"
    assert product_client.delete(f"/api/documents/{document['id']}").status_code == 409

    refreshed = product_client.get(f"/api/products/{product['product_id']}").json()
    assert refreshed["documents"][-1]["kind"] == "DOCUMENT"


def test_migration_pose_une_protection_sql_sur_les_versions(product_client):
    from backend.app.db.product_migrations import migrate_product_links

    migrate_product_links(product_client.session.connection())
    product_client.session.commit()
    _create(product_client, key="immutable-product")
    with pytest.raises(Exception, match="Historique produit immuable"):
        product_client.session.execute(text(
            "UPDATE product_terms_versions SET reason='réécrit' WHERE id=1"))
        product_client.session.commit()
    product_client.session.rollback()
