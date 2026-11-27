"""Scoped documentation uses the frozen Product contract before returning rows."""

from backend.app.core.product.models import Product
from backend.app.db.models import Deal, Document
from backend.app.services.product_repository import stage_revision, stage_terms
from backend.tests.test_products import _create, product_client  # noqa: F401
from backend.tests.test_rates_credit_mixed_reader import _native_terms, _seed_native


def _create_document(client, title, **fields):
    document = Document(title=title, doc_type="autre", user_id=client.users["alice"].id, **fields)
    client.session.add(document)
    client.session.flush()
    return document


def _listed(client, **params):
    response = client.get("/api/documents", params=params)
    assert response.status_code == 200, response.text
    return {item["title"] for item in response.json()}


def test_classified_list_composes_acl_and_links_and_keeps_general_library(product_client):
    client = product_client
    equity = _create(client)["product_id"]
    rates = _seed_native(client, "FRN")
    credit = _seed_native(client, "CDS")
    hidden = _seed_native(client, "FRN", actor="bob")
    deal = Deal(reference="Legacy rates document fixture", user_id=client.users["alice"].id,
                product_id=rates.product_id, product_terms_version=rates.terms_version)
    client.session.add(deal)
    client.session.flush()

    _create_document(client, "Equity", product_id=equity, product_terms_version=1)
    _create_document(client, "Rates", product_id=rates.product_id, product_terms_version=rates.terms_version)
    _create_document(client, "Credit", product_id=credit.product_id, product_terms_version=credit.terms_version)
    _create_document(client, "Deal-only document", deal_id=deal.id)
    _create_document(client, "Unqualified legacy document", product_id=rates.product_id)
    _create_document(client, "Private to Bob", product_id=hidden.product_id, product_terms_version=hidden.terms_version)
    client.session.commit()

    assert _listed(client, asset="equity") == {"Equity"}
    assert _listed(client, asset="rates") == {"Rates", "Deal-only document"}
    assert _listed(client, asset="credit") == {"Credit"}
    assert _listed(client, asset="credit", product_id=rates.product_id) == set()
    assert _listed(client, asset="rates", deal_id=deal.id) == {"Deal-only document"}
    assert _listed(client) == {"Equity", "Rates", "Credit", "Deal-only document", "Unqualified legacy document"}
    assert client.get("/api/documents", params={"asset": "other"}).status_code == 422
    client.current["user"] = client.users["bob"]
    assert _listed(client, asset="rates") == {"Private to Bob"}


def test_classification_uses_the_document_version_even_if_current_terms_have_another_class(product_client):
    client = product_client
    rates = _seed_native(client, "FRN")
    next_terms = Product.model_validate({
        "name": "Distinct contract for the historical-lookup witness",
        "terms": _native_terms("CDS"),
        "intent": {"nominal": 1_000_000, "side": "BUY"},
    }).terms
    actor = client.users["alice"].id
    revised = stage_terms(client.session, rates, next_terms, actor_id=actor, reason="Historical read witness")
    revised = stage_revision(client.session, revised, expected_revision=rates.revision,
                             actor_id=actor, action="TEST_TERMS_CHANGED")
    _create_document(client, "Historical FRN", product_id=rates.product_id, product_terms_version=rates.terms_version)
    _create_document(client, "Current CDS", product_id=revised.product_id, product_terms_version=revised.terms_version)
    client.session.commit()

    assert _listed(client, asset="rates") == {"Historical FRN"}
    assert _listed(client, asset="credit") == {"Current CDS"}
