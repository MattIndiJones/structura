"""Product v1 and native terms coexist while native writes are closed."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlmodel import select

from backend.app.core.product.models import Product
from backend.app.core.valuation_context import canonical_fingerprint, canonical_json
from backend.app.db.models import (
    Deal, ProductCalculationRun, ProductCommand, ProductRecord, ProductRevision, ProductTermsVersion,
)
from backend.app.services.exotic_product import product_from_exotic_price
from backend.app.services.product_repository import stage_new_product, stage_revision, stage_terms
from backend.tests.test_products import _create, _pricing_input, product_client
from backend.tests.test_rates_credit_cln_schedule import cln_terms  # noqa: F401


_FIXTURES = Path(__file__).with_name("fixtures")
_RATES = json.loads((_FIXTURES / "rates_credit_abc.json").read_text(encoding="utf-8"))["terms"]
_ISDA = json.loads((_FIXTURES / "rates_credit_isda.json").read_text(encoding="utf-8"))


def _native_terms(instrument_type):
    terms = {
        "schema_version": 2,
        "instrument_type": instrument_type,
        "payoff_mode": "native",
        "template_id": f"{instrument_type.lower()}-eur-pilot",
        "template_version": 1,
        "currency": _RATES["currency"],
        "effective_date": _RATES["effective_date"],
        "maturity_date": _RATES["maturity_date"],
    }
    quarterly = {
        "calendar": _RATES["calendar"],
        "business_day_convention": _RATES["business_day_convention"],
        "frequency_months": _RATES["floating"]["frequency_months"],
        "day_count": _RATES["floating"]["day_count"],
        "payment_lag_business_days": _RATES["floating"]["payment_lag_target_days"],
    }
    if instrument_type in {"FRN", "IRS"}:
        terms["floating_leg"] = {
            **quarterly,
            "index": "EURIBOR_3M",
            "margin_bps": float(_RATES["frn"]["margin_bp"] if instrument_type == "FRN"
                                else _RATES["irs"]["floating_margin_bp"]),
            "fixing_calendar": _RATES["calendar"],
            "fixing_lag_business_days": _RATES["floating"]["fixing_lag_target_days"],
        }
    if instrument_type == "FRN":
        terms["redemption_fraction"] = float(_RATES["frn"]["principal_fraction"])
    if instrument_type == "IRS":
        terms["fixed_leg"] = {
            **quarterly,
            "frequency_months": _RATES["irs"]["fixed_frequency_months"],
            "day_count": _RATES["irs"]["fixed_day_count"],
            "coupon_rate": float(_RATES["irs"]["fixed_rate"]),
        }
    if instrument_type == "CDS":
        dates, conventions = _ISDA["cds_chronology"], _ISDA["cds_conventions"]
        terms.update(
            trade_date=dates["trade_date"],
            effective_date=dates["step_in_date"],
            maturity_date=dates["protection_end_inclusive_date"],
            reference_entity_id="synthetic-reference",
            seniority="senior",
            documentation="synthetic-cds-documentation",
            restructuring="synthetic-clause",
            premium_leg={
                "calendar": conventions["calendar"],
                "business_day_convention": conventions["premium_payment_adjustment"].lower(),
                "frequency_months": conventions["premium_frequency_months"],
                "day_count": conventions["premium_day_count"],
                "payment_lag_business_days": 0,
                "coupon_bps": _ISDA["contract_terms"]["coupon_bp"],
            },
            step_in_lag_calendar_days=conventions["step_in_calendar_days"],
            cash_settlement_lag_business_days=conventions["initial_settlement_business_days"],
            accrued_on_default=True,
        )
    return terms


def _seed_native(client, instrument_type, *, actor="alice", side="BUY"):
    nominal = _ISDA["contract_terms"]["notional_eur"] if instrument_type == "CDS" else int(_RATES["notional_eur"])
    product = Product.model_validate({
        "name": f"Témoin {instrument_type}",
        "terms": _native_terms(instrument_type),
        "intent": {"nominal": nominal, "side": side},
    })
    saved = stage_new_product(client.session, product, user=client.users[actor])
    client.session.commit()
    return saved


def _ids(items):
    return [row["id"] for row in items]


def _project(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def _assert_error(response, code, status=409):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def test_mixed_projection_preserves_legacy_filter_before_pagination(product_client):
    client = product_client
    old = _create(client, key="legacy-old")["product_id"]
    frn = _seed_native(client, "FRN")
    middle = _create(client, key="legacy-middle")["product_id"]
    irs = _seed_native(client, "IRS")
    cds = _seed_native(client, "CDS", side="SELL")
    recent = _create(client, key="legacy-recent")["product_id"]
    hidden = _seed_native(client, "FRN", actor="bob")

    # With the same timestamp, descending identity breaks ties in both views.
    records = client.session.exec(select(ProductRecord)).all()
    for record in records:
        record.updated_at = datetime(2026, 9, 21, 12)
        client.session.add(record)
    client.session.commit()

    legacy = [recent, middle, old]
    mixed = [recent, cds.product_id, irs.product_id, middle, frn.product_id, old]
    for suffix, expected in (("", legacy), ("&view=mixed", mixed)):
        assert _ids(_project(client, f"/api/products?limit=10{suffix}")) == expected
        for offset in range(0, len(expected), 2):
            page = _project(client, f"/api/products?paged=true&limit=2&offset={offset}{suffix}")
            assert _ids(page["items"]) == expected[offset:offset + 2]
            assert page["has_more"] is (offset + 2 < len(expected))

    for product, direction in ((frn, "long"), (irs, "receive_fixed"), (cds, "sell_protection")):
        terms = product.terms.model_dump(mode="json")
        detail = _project(client, f"/api/products/{product.product_id}?view=mixed")
        assert detail["terms"] == terms
        assert (detail["schema_version"], detail["terms_version"], detail["revision"]) == (1, 1, 1)
        assert detail["instrument_type"] == terms["instrument_type"]
        assert detail["payoff_mode"] == "native"
        assert detail["position"]["side"] == direction
        assert detail["position"]["nominal"] == product.intent.nominal
        assert detail["description"]["status"] == "ready"
        assert detail["calculations"] == []
        assert {key: detail["capabilities"][key] for key in ("prepare", "price", "write")} == {
            "prepare": False, "price": True, "write": False,
        }
        history = _project(client, f"/api/products/{product.product_id}/history?view=mixed")
        assert [(item["revision"], item["terms_version"]) for item in history["items"]] == [(1, 1)]

    native_rows = [
        row for row in _project(client, "/api/products?view=mixed") if row["id"] in {frn.product_id, irs.product_id, cds.product_id}
    ]
    assert all(row["price"] is None for row in native_rows)
    for path in ("", "/history"):
        assert client.get(f"/api/products/{hidden.product_id}{path}?view=mixed").status_code == 404


def test_native_dossier_rejects_legacy_routes_and_durable_writes(product_client):
    client = product_client
    frn = _seed_native(client, "FRN")
    url = f"/api/products/{frn.product_id}"
    before = client.session.exec(select(ProductTermsVersion)).one()
    stored = (before.terms_json, before.fingerprint)
    _assert_error(client.get(url), "PRODUCT_TERMS_UNSUPPORTED")
    _assert_error(client.get(f"{url}/history"), "PRODUCT_TERMS_UNSUPPORTED")

    terms = _native_terms("FRN")
    tagged_script = {**_pricing_input(), "schema_version": 2, "instrument_type": "FRN", "payoff_mode": "native"}
    _assert_error(client.post("/api/products", json={"command_key": "tagged-script", "pricing_input": tagged_script}),
                  "PRODUCT_TERMS_UNSUPPORTED")
    for route, body in (
        ("pricing-input", {"expected_terms_version": 1, "context": {}}),
        ("calculations", {"expected_revision": 1, "command_key": "keep-calculation", "pricing_receipt": {}}),
        ("terms", {"expected_revision": 1, "command_key": "revise-native", "pricing_input": terms, "reason": "Témoin natif"}),
        ("archive", {"expected_revision": 1, "archived": True, "reason": "Témoin natif"}),
        ("booking-forks", {"expected_revision": 1, "expected_terms_version": 1, "command_key": "fork-booking", "reason": "Témoin natif bloqué"}),
    ):
        _assert_error(client.post(f"{url}/{route}", json=body), "PRODUCT_TERMS_UNSUPPORTED")
    patched = client.patch(url, json={"expected_revision": 1, "name": "Édition refusée", "reason": "Témoin natif"})
    _assert_error(patched, "PRODUCT_TERMS_UNSUPPORTED")
    assert len(client.session.exec(select(ProductRecord)).all()) == 1
    assert len(client.session.exec(select(ProductRevision)).all()) == 1
    assert client.session.exec(select(ProductCommand)).all() == []
    assert client.session.exec(select(ProductCalculationRun)).all() == []
    assert client.session.exec(select(Deal)).all() == []
    after = client.session.exec(select(ProductTermsVersion)).one()
    assert (after.terms_json, after.fingerprint) == stored


def test_mixed_asset_filter_applies_to_page_boundaries_and_archives(product_client, cln_terms):
    from backend.tests.test_exotic_pricer_api import _credit, _rates

    client = product_client
    equity = _create(client, key="asset-equity")["product_id"]
    frn = _seed_native(client, "FRN").product_id
    cds = _seed_native(client, "CDS").product_id
    irs = _seed_native(client, "IRS").product_id
    cln = stage_new_product(client.session, Product(name="CLN", terms=cln_terms), user=client.users["alice"]).product_id
    exotic_rates = stage_new_product(client.session, product_from_exotic_price({"request": _rates()}, name="CMS"),
                                    user=client.users["alice"]).product_id
    exotic_credit = stage_new_product(client.session, product_from_exotic_price({"request": _credit()}, name="CDS MC"),
                                     user=client.users["alice"]).product_id
    archived_rates = _seed_native(client, "FRN").product_id
    archived_credit = _seed_native(client, "CDS").product_id
    hidden_rates = _seed_native(client, "FRN", actor="bob").product_id
    for row in client.session.exec(select(ProductRecord)).all():
        row.updated_at = datetime(2026, 9, 21, 12)
        row.archived = row.id in {archived_rates, archived_credit}
        client.session.add(row)
    client.session.commit()

    url = "/api/products?view=mixed"
    expected = {"equity": [equity], "rates": [exotic_rates, irs, frn], "credit": [exotic_credit, cln, cds]}
    for asset, product_ids in expected.items():
        filter_url = f"{url}&asset={asset}"
        assert _ids(_project(client, filter_url)) == product_ids
        for offset in range(len(product_ids) + 1):
            page = _project(client, f"{filter_url}&paged=true&limit=1&offset={offset}")
            assert _ids(page["items"]) == product_ids[offset:offset + 1]
            assert page["has_more"] is (offset + 1 < len(product_ids))
    assert _ids(_project(client, f"{url}&archived=true&asset=rates")) == [archived_rates]
    assert _ids(_project(client, f"{url}&archived=true&asset=credit")) == [archived_credit]
    assert _project(client, f"{url}&archived=true&asset=equity") == []
    assert hidden_rates not in _ids(_project(client, url))
    assert client.get(f"{url}&asset=unknown").status_code == 422


@pytest.mark.parametrize("case", [
    "unknown-schema", "null-version", "string-version", "implicit-native", "missing-type",
    "unsupported-mode", "missing-zero-margin", "other-family", "fingerprint",
])
def test_mixed_reader_reports_corrupted_native_terms_after_access_control(product_client, case):
    client = product_client
    irs = _seed_native(client, "IRS")
    row = client.session.exec(select(ProductTermsVersion)).one()
    terms = _native_terms("IRS")
    if case == "unknown-schema":
        terms["schema_version"] = 99
    if case == "null-version":
        terms["schema_version"] = None
    if case == "string-version":
        terms["schema_version"] = "2"
    if case == "implicit-native":
        del terms["schema_version"]
    if case == "missing-type":
        del terms["instrument_type"]
    if case == "unsupported-mode":
        terms["payoff_mode"] = "payscript"
    if case == "missing-zero-margin":
        del terms["floating_leg"]["margin_bps"]
    if case == "other-family":
        terms["redemption_fraction"] = 1.0
    row.terms_json = canonical_json(terms)
    row.fingerprint = "0" * 64 if case == "fingerprint" else canonical_fingerprint(terms)
    client.session.add(row)
    client.session.commit()

    path = f"/api/products/{irs.product_id}?view=mixed"
    _assert_error(client.get(path), "PRODUCT_TERMS_INVALID")
    assert _project(client, "/api/products?view=mixed&paged=true") == {
        "items": [], "offset": 0, "limit": 50, "has_more": False,
    }
    client.current["user"] = client.users["bob"]
    assert client.get(path).status_code == 404


def test_mixed_reader_matches_exact_historical_revision_and_terms_pair(product_client):
    client = product_client
    frn = _seed_native(client, "FRN")
    changed_terms = _native_terms("FRN")
    changed_terms["floating_leg"]["margin_bps"] = 125
    changed = Product.model_validate({"terms": changed_terms}).terms
    candidate = stage_terms(client.session, frn, changed, actor_id=client.users["alice"].id, reason="Témoin versionné")
    revised = stage_revision(client.session, candidate, expected_revision=1, actor_id=client.users["alice"].id,
                             action="PRODUCT_TERMS_REVISED", reason="Témoin versionné")
    client.session.commit()
    url = f"/api/products/{frn.product_id}?view=mixed"
    assert (revised.revision, revised.terms_version) == (2, 2)
    assert _project(client, url)["terms"]["floating_leg"]["margin_bps"] == 125
    first = _project(client, f"{url}&revision=1&terms_version=1")
    assert first["terms"]["floating_leg"]["margin_bps"] == 100
    assert (first["revision"], first["terms_version"]) == (1, 1)
    _assert_error(client.get(f"{url}&revision=1&terms_version=2"), "PRODUCT_REVISION_INCONSISTENT")
    _assert_error(client.get(f"{url}&revision=2&terms_version=1"), "PRODUCT_REVISION_INCONSISTENT")


def test_legacy_revision_preserves_original_fingerprint_of_implicit_v1_terms(product_client):
    client = product_client
    product = _create(client)
    row = client.session.exec(select(ProductTermsVersion)).one()
    terms = json.loads(row.terms_json)
    del terms["schema_version"]
    raw, fingerprint = canonical_json(terms), canonical_fingerprint(terms)
    row.terms_json, row.fingerprint = raw, fingerprint
    client.session.add(row)
    client.session.commit()

    response = client.patch(f"/api/products/{product['product_id']}", json={
        "expected_revision": 1, "name": "Historique relu", "reason": "Correction du libellé",
    })
    assert response.status_code == 200, response.text
    assert (response.json()["revision"], response.json()["terms_version"]) == (2, 1)
    saved = client.session.exec(select(ProductTermsVersion)).one()
    assert (saved.terms_json, saved.fingerprint) == (raw, fingerprint)


def test_invalid_revision_json_returns_diagnostic_even_when_paginated(product_client):
    client = product_client
    frn = _seed_native(client, "FRN")
    revision = client.session.exec(select(ProductRevision)).one()
    revision.snapshot_json = "{"
    client.session.add(revision)
    client.session.commit()

    path = f"/api/products/{frn.product_id}?view=mixed&calculations_limit=1"
    _assert_error(client.get(path), "PRODUCT_TERMS_INVALID")
