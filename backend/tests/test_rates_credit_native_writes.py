"""End-to-end retention and reopening on an isolated mixed Product archive."""

from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import products as products_api
from backend.app.api.auth import receipt_signing_secret
from backend.app.core import instance_signing
from backend.app.core.product import native_schedule
from backend.app.db.database import get_session
from backend.app.db import migrations
from backend.app.db.models import (
    AuditEvent, Counterparty, Deal, NativeValuationContextRecord, ProductCalculationRun,
    ProductCommand, ProductRecord, ProductRevision, ProductTermsVersion,
)
from backend.app.services.product_receipts import verify_server_receipt
from backend.app.services.product_repository import load_product
from backend.tests.test_products import _browser_json_roundtrip, _create, _pricing_input, product_client  # noqa: F401
from backend.tests.test_rates_credit_isda_market import request_data  # noqa: F401
from backend.tests.test_rates_credit_legacy_baseline import _PRICE, _TERMS_SHA256
from backend.tests.test_rates_credit_market_integration import _body, _count, _create_context, _read_context
from backend.tests.test_rates_credit_mixed_reader import _assert_error, _native_terms
from backend.tests.test_rates_credit_rates_market import build_rates_market
from backend.tests.test_rates_credit_rates_schedule import abc_reference  # noqa: F401


_CREATE = "/api/products/native"
_WRITE_TABLES = (ProductRecord, ProductTermsVersion, ProductRevision, ProductCommand, AuditEvent)


@pytest.fixture
def native_recipe_client(product_client, tmp_path, monkeypatch):
    directory = tmp_path.resolve()
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(directory))
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_DATA_DIR", str(directory))
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "1")
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_USERS", "alice,bob")

    client = product_client
    database = directory / "structura.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    assert migrations.upgrade(engine, migrations=migrations.discover()[:1])["applied"] == [1]
    migration_report = migrations.upgrade(engine, backup_dir=directory / "migration-backups")
    assert 2 in migration_report["applied"]
    assert Path(migration_report["backup"]).is_file()
    client.session = Session(engine)
    client.session.add_all(type(user).model_validate(user) for user in client.users.values())
    client.session.commit()
    client.app.dependency_overrides[get_session] = lambda: client.session

    def restore_archive():
        nonlocal engine
        client.session.close()
        engine.dispose()
        restored = directory / "restored"
        restored.mkdir()
        restored_database = restored / "structura.db"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(restored_database)) as destination:
            source.backup(destination)
        monkeypatch.setenv("STRUCTURA_DATA_DIR", str(restored))
        monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_DATA_DIR", str(restored))
        engine = create_engine(f"sqlite:///{restored_database.as_posix()}", connect_args={"check_same_thread": False})
        restored_schema = migrations.check_compatible(engine)
        assert restored_schema["version"] == restored_schema["expected"] == migration_report["to"]
        assert not (restored_schema["pending"] or restored_schema["modified"] or restored_schema["unknown"])
        client.session = Session(engine)

    client.restore_archive = restore_archive
    yield client
    client.session.close()
    engine.dispose()


def _created_body(instrument, *, key=None):
    return {
        "command_key": key or f"native-create-{instrument.lower()}",
        "name": f"Témoin {instrument}",
        "terms": _native_terms(instrument),
        "intent": {"nominal": 10_000_000 if instrument == "CDS" else 1_000_000, "side": "BUY"},
    }


def _checked_json(response, expected_status):
    assert response.status_code == expected_status, response.text
    return response.json()


def _detail(client, product_id, **params):
    return _checked_json(client.get(f"/api/products/{product_id}", params={"view": "mixed", **params}), 200)


def _revision_url(product_id):
    return f"/api/products/{product_id}/native/terms"


def _amended_terms(terms):
    amended = deepcopy(terms)
    instrument = amended["instrument_type"]
    if instrument == "FRN":
        amended["floating_leg"]["margin_bps"] = 110
    elif instrument == "IRS":
        amended["fixed_leg"]["coupon_rate"] = 0.0254021092847019
    else:
        amended["maturity_date"] = "2026-09-20"
    return amended


def _revision_body(product, *, key=None, terms=None):
    return {
        "command_key": key or f"native-revise-{product['instrument_type'].lower()}",
        "expected_revision": product["revision"],
        "reason": "Révision contractuelle de recette",
        "terms": terms if terms is not None else _amended_terms(product["terms"]),
    }


def _retain_legacy_deal(client, monkeypatch):
    monkeypatch.setattr(instance_signing, "current_config", lambda: None)
    monkeypatch.setattr(instance_signing, "_PROCESS_SECRET", "rates-credit-test-only-v2")
    client.session.add(Counterparty(id=1, name="Banque Test", active=True))
    client.session.commit()
    request = _pricing_input(N=1000)
    priced = _checked_json(client.post("/api/price", json=request), 200)
    assert priced["price"] == _PRICE
    receipt = _browser_json_roundtrip(priced["pricing_receipt"])
    verified = verify_server_receipt(receipt, secret=receipt_signing_secret())
    assert receipt["signature_version"] == 2
    product = _create(client, key="legacy-before-native", receipt=receipt, pricing_input=receipt["pricing_input"])
    product_id = product["product_id"]
    deal = _checked_json(client.post("/api/deals", json={
        "product_id": product_id, "product_terms_version": 1,
        "sens": "vente", "contrepartie": "Banque Test", "counterparty_id": 1, "devise": "EUR",
        "nominal": 1_000_000, "fair_value": receipt["price_pct"], "price_traded": 97.0,
        "trade_date": request["strike_date"], "strike_date": request["strike_date"],
        "value_date": request["value_date"], "maturity_date": request["maturity_date"],
        "payment_date": request["payment_date"], "T": request["T"],
        "underlyings": product["terms"]["underlyings"], "observation_times": [1.0],
        "script_snapshot": request["script"], "market_snapshot": {}, "pricing_receipt": receipt,
        "transaction_format": "EMTN", "instrument_family": "NOTE",
    }), 201)
    assert (deal["product_id"], deal["product_terms_version"]) == (product_id, 1)
    terms = client.session.exec(select(ProductTermsVersion).where(
        ProductTermsVersion.product_id == product_id,
    )).one()
    assert terms.fingerprint == _TERMS_SHA256
    return product_id, deal["id"], terms.terms_json, verified


def test_native_and_payscript_dossiers_reopen_with_both_versions_and_nine_prepared_contexts(
    native_recipe_client, abc_reference, request_data, monkeypatch,
):
    client = native_recipe_client
    legacy_id, legacy_deal_id, legacy_bytes, legacy_receipt = _retain_legacy_deal(client, monkeypatch)
    legacy_url = f"/api/products/{legacy_id}"
    legacy = _checked_json(client.get(legacy_url), 200)
    initial, revised, archives = {}, {}, {}
    for instrument in ("FRN", "IRS", "CDS"):
        body = _created_body(instrument)
        opened = _checked_json(client.post(_CREATE, json=body), 201)
        product_id = opened["product_id"]
        assert (opened["revision"], opened["terms_version"], opened["terms"]["schema_version"]) == (1, 1, 2)
        assert opened["instrument_type"] == instrument
        assert opened["reference"] and opened["capabilities"]["write"]
        assert opened["price"] is None and opened["calculations"] == [] and opened["execution"] is None
        assert opened["description"]["status"] == "ready"
        assert _detail(client, product_id) == opened
        initial[instrument] = opened
        archives[instrument] = []
    assert len({item["reference"] for item in initial.values()}) == 3
    frn_coupon, frn_principal = initial["FRN"]["description"]["schedule"]["legs"]
    assert len(frn_coupon["periods"]) == 8
    assert frn_principal["events"][0]["date"] == frn_coupon["periods"][-1]["payment_date"] == "2028-09-21"
    assert frn_principal["events"][0]["flow_id"] != frn_coupon["periods"][-1]["flow_id"]
    assert [item["id"] for item in _checked_json(client.get("/api/products"), 200)] == [legacy_id]
    assert {item["instrument_type"] for item in _checked_json(client.get("/api/products?view=mixed"), 200)} == {
        "PAYSCRIPT", "FRN", "IRS", "CDS",
    }
    legacy_page = _checked_json(client.get("/api/products?paged=true&limit=1"), 200)
    assert [item["id"] for item in legacy_page["items"]] == [legacy_id]
    assert not legacy_page["has_more"]

    frn, irs, cds = (
        load_product(client.session, initial[instrument]["product_id"], allow_native=True)
        for instrument in ("FRN", "IRS", "CDS")
    )
    for case, snapshot in abc_reference["snapshots"].items():
        raw_market = build_rates_market(abc_reference, (frn, irs), case).model_dump(mode="json")
        pair = []
        for product in (frn, irs):
            instrument = product.terms.instrument_type
            body = _body(product, f"native-context-{instrument}-{case}", snapshot["cutoff_local"],
                         snapshot["valuation_date"], raw_market)
            retained = _create_context(client, product, body)
            selected = retained["context"]["market"]
            assert [item["fixing_id"] for item in selected["fixings"]] == snapshot["acquired_fixing_ids"]
            first_flow = selected["flows"][0]
            assert first_flow["flow_id"] == abc_reference["first_payment"][f"{instrument.lower()}_flow_id"]
            assert first_flow["state"] == snapshot["first_payment_state"]
            pair.append(selected["market_fingerprint"])
            archives[instrument].append(retained)
        assert pair[0] == pair[1]

    for scenario in request_data["scenarios"]:
        raw_market = {**request_data, "kind": "isda", "scenario_id": scenario["id"]}
        body_for_old_isda = _body(
            cds, f"native-context-{scenario['id']}", "2021-04-26T12:00:00+02:00", "2021-04-26", raw_market,
        )
        retained = _create_context(client, cds, body_for_old_isda)
        selected = retained["context"]["market"]
        assert selected["scenario"]["id"] == scenario["id"]
        assert len(selected["ois_quotes"]["rows"]) == 17
        assert selected["ois_quotes"]["rows"][0]["rate"] == -0.005683
        archives["CDS"].append(retained)
    assert _count(client, NativeValuationContextRecord) == 9
    assert _count(client, ProductCalculationRun) == 1

    for instrument, prior in initial.items():
        product_id = prior["product_id"]
        assert _detail(client, product_id) == prior  # Contexts do not mutate Terms or Product revision.
        body = _revision_body(prior)
        amendment = _checked_json(client.post(_revision_url(product_id), json=body), 200)
        assert (amendment["product_id"], amendment["reference"]) == (product_id, prior["reference"])
        assert (amendment["revision"], amendment["terms_version"]) == (2, 2)
        assert amendment["description"]["status"] == "ready"
        old_schedule = prior["description"]["schedule"]
        assert amendment["description"]["schedule"]["fingerprint"] != old_schedule["fingerprint"]
        for archived in archives[instrument]:
            ctx = archived["context"]
            assert (ctx["product_id"], ctx["terms_version"]) == (product_id, 1)
            assert ctx["schedule_fingerprint"] == old_schedule["fingerprint"]
            assert ctx["terms_fingerprint"] == old_schedule["terms_fingerprint"]
        assert _detail(client, product_id) == amendment
        revised[instrument] = amendment

    assert revised["FRN"]["terms"]["floating_leg"]["margin_bps"] == 110
    assert revised["IRS"]["terms"]["fixed_leg"]["coupon_rate"] == 0.0254021092847019
    assert revised["CDS"]["terms"]["maturity_date"] == "2026-09-20"
    assert len(revised["CDS"]["description"]["schedule"]["legs"][0]["periods"]) == 22
    _assert_error(client.post(f"/api/products/{cds.product_id}/valuation-contexts", json={
        **body_for_old_isda,
        "command_key": "native-context-cds-incompatible-v2",
        "terms_version": 2,
    }), "ISDA_PRODUCT_INCOMPATIBLE", 422)
    assert _detail(client, cds.product_id) == revised["CDS"]
    assert _count(client, NativeValuationContextRecord) == 9

    def no_recalculation(*_args, **_kwargs):
        pytest.fail("Un dossier ou contexte figé doit être rouvert sans résolution ni préparation.")

    monkeypatch.setattr(native_schedule, "resolve_native_schedule", no_recalculation)
    monkeypatch.setattr(products_api, "prepare_native_context", no_recalculation)
    client.restore_archive()
    for product in (frn, irs, cds):
        instrument, product_id = product.terms.instrument_type, product.product_id
        assert _detail(client, product_id) == revised[instrument]
        assert _detail(client, product_id, revision=1, terms_version=1) == initial[instrument]
        archive_url = f"/api/products/{product_id}/valuation-contexts"
        old = _checked_json(client.get(archive_url, params={"terms_version": 1}), 200)["items"]
        assert {item["context_id"] for item in old} == {item["context_id"] for item in archives[instrument]}
        assert {item["fingerprint"] for item in old} == {
            item["context"]["fingerprint"] for item in archives[instrument]
        }
        assert _checked_json(client.get(archive_url, params={"terms_version": 2}), 200)["items"] == []
        assert _checked_json(client.get(archive_url), 200)["items"] == []
        persisted_versions = client.session.exec(select(ProductTermsVersion).where(
            ProductTermsVersion.product_id == product_id,
        ).order_by(ProductTermsVersion.version)).all()
        assert [(version.version, version.parent_version) for version in persisted_versions] == [(1, None), (2, 1)]
        for archived in archives[instrument]:
            assert _read_context(client, product, archived["context_id"]) == archived

    assert _checked_json(client.get(legacy_url), 200) == legacy
    run = client.session.exec(select(ProductCalculationRun)).one()
    calculation = _checked_json(client.get(f"{legacy_url}/calculations/{run.id}"), 200)
    assert calculation["result"] == legacy_receipt["result"]
    deal = client.session.get(Deal, legacy_deal_id)
    assert (deal.product_id, deal.product_terms_version) == (legacy_id, 1)
    persisted_terms = client.session.exec(select(ProductTermsVersion).where(
        ProductTermsVersion.product_id == legacy_id,
    )).one()
    assert (persisted_terms.terms_json, persisted_terms.fingerprint) == (legacy_bytes, _TERMS_SHA256)
    durable_tables = (*_WRITE_TABLES, NativeValuationContextRecord, ProductCalculationRun, Deal)
    before_close = [_count(client, model) for model in durable_tables]
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    for product in (frn, irs, cds):
        instrument = product.terms.instrument_type
        assert not _detail(client, product.product_id)["capabilities"]["write"]
        assert _detail(client, product.product_id, terms_version=1)["terms"] == initial[instrument]["terms"]
        for archived in archives[instrument]:
            assert _read_context(client, product, archived["context_id"]) == archived
    assert _checked_json(client.get(legacy_url), 200) == legacy

    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "1")
    for instrument, prior in initial.items():
        assert _checked_json(client.post(_CREATE, json=_created_body(instrument)), 201) == prior
        repeat = client.post(_revision_url(prior["product_id"]), json=_revision_body(prior))
        assert _checked_json(repeat, 200) == revised[instrument]
    assert [_count(client, model) for model in durable_tables] == before_close


def test_write_commands_use_scope_idempotence_and_expected_revision(native_recipe_client, monkeypatch):
    client = native_recipe_client
    body = _created_body("FRN")
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    _assert_error(client.post(_CREATE, json=body), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    assert _count(client, ProductRecord) == 0
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "1")
    initial = _checked_json(client.post(_CREATE, json=body), 201)
    product_id = initial["product_id"]
    target = _revision_url(product_id)
    assert _checked_json(client.post(_CREATE, json=body), 201) == initial
    _assert_error(client.post(_CREATE, json={**body, "name": "Autre contenu"}), "PRODUCT_COMMAND_CONFLICT")
    another = _checked_json(client.post(_CREATE, json=_created_body("FRN", key="native-create-another")), 201)

    change = _revision_body(initial)
    # The create key cannot be replayed as an edit, even on the same Product.
    _assert_error(client.post(target, json={**change, "command_key": body["command_key"]}), "PRODUCT_COMMAND_CONFLICT")
    revised = _checked_json(client.post(target, json=change), 200)
    _assert_error(client.post(_revision_url(another["product_id"]), json=change), "PRODUCT_COMMAND_CONFLICT")
    _assert_error(client.post(target, json={**change, "reason": "Motif différent"}), "PRODUCT_COMMAND_CONFLICT")
    _assert_error(client.post(target, json={**change, "command_key": "native-revise-stale"}), "PRODUCT_REVISION_STALE")
    wrong_type = _revision_body(revised, key="native-revise-type", terms=_native_terms("IRS"))
    _assert_error(client.post(target, json=wrong_type), "PRODUCT_TERMS_UNSUPPORTED")

    no_change = _revision_body(revised, key="native-revise-noop", terms=revised["terms"])
    assert _checked_json(client.post(target, json=no_change), 200) == revised
    advanced = {**no_change, "command_key": "native-revise-later", "terms": deepcopy(revised["terms"])}
    advanced["terms"]["floating_leg"]["margin_bps"] = 120
    current = _checked_json(client.post(target, json=advanced), 200)
    assert (current["revision"], current["terms_version"]) == (3, 3)
    new_intent = _revision_body(current, key="native-intent-update", terms=current["terms"])
    new_intent["intent"] = {"nominal": 2_000_000, "side": "SELL"}
    with_intent = _checked_json(client.post(target, json=new_intent), 200)
    assert (with_intent["revision"], with_intent["terms_version"]) == (4, 3)
    assert with_intent["description"]["schedule"] == current["description"]["schedule"]
    assert with_intent["position"] == {"nominal": 2_000_000, "side": "short"}
    assert _checked_json(client.post(target, json=change), 200) == revised
    assert _checked_json(client.post(_CREATE, json=body), 201) == initial

    client.current["user"] = client.users["bob"]
    assert client.post(target, json=change).status_code == 404
    assert client.get(f"/api/products/{product_id}?view=mixed").status_code == 404
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_USERS", "alice")
    _assert_error(client.post(_CREATE, json=body), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    client.current["user"] = client.users["alice"]
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    _assert_error(client.post(_CREATE, json=body), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    _assert_error(client.post(target, json=advanced), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    read_when_closed = _detail(client, product_id)
    assert not read_when_closed["capabilities"]["write"]
    assert read_when_closed["terms"] == current["terms"]
    assert _detail(client, product_id, terms_version=1)["terms"] == initial["terms"]
    assert _create(client, key="legacy-while-native-closed")["terms_version"] == 1


def test_context_retry_preserves_the_original_intent_until_a_new_key(native_recipe_client, abc_reference, monkeypatch):
    client = native_recipe_client
    draft = _checked_json(client.post(_CREATE, json=_created_body("FRN")), 201)
    product_id = draft["product_id"]
    frn = load_product(client.session, product_id, allow_native=True)
    snapshot = abc_reference["snapshots"]["A"]
    market = build_rates_market(abc_reference, (frn,), "A").model_dump(mode="json")
    body = _body(frn, "native-context-original-intent", snapshot["cutoff_local"], snapshot["valuation_date"], market)
    original = _create_context(client, frn, body)

    changed = _revision_body(draft, terms=draft["terms"])
    changed["intent"] = {"nominal": 2_000_000, "side": "SELL"}
    revised = _checked_json(client.post(_revision_url(product_id), json=changed), 200)
    assert (revised["revision"], revised["terms_version"]) == (2, 1)
    assert _create_context(client, frn, body) == original

    fresh = _create_context(client, frn, {**body, "command_key": "native-context-new-intent"})
    assert fresh["context_id"] != original["context_id"]
    assert (original["context"]["nominal"], original["context"]["side"]) == (1_000_000, "BUY")
    assert (fresh["context"]["nominal"], fresh["context"]["side"]) == (2_000_000, "SELL")

    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    endpoint = f"/api/products/{product_id}/valuation-contexts"
    _assert_error(client.post(endpoint, json=body), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    _assert_error(client.post(endpoint, json={**body, "command_key": "native-context-closed"}),
                  "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    assert _read_context(client, frn, original["context_id"]) == original
    assert _read_context(client, frn, fresh["context_id"]) == fresh
    assert _count(client, NativeValuationContextRecord) == 2


def test_incomplete_draft_and_precommit_failures_are_recoverable(native_recipe_client, monkeypatch):
    client = native_recipe_client
    body = _created_body("FRN")
    incomplete = deepcopy(body)
    incomplete["terms"]["effective_date"] = None
    initial_counts = [_count(client, model) for model in _WRITE_TABLES]
    wrong_schema = deepcopy(body)
    wrong_schema["terms"]["schema_version"] = 2.0
    assert client.post(_CREATE, json=wrong_schema).status_code == 422
    assert [_count(client, model) for model in _WRITE_TABLES] == initial_counts

    def fail_commit():
        raise RuntimeError("injected transaction failure")

    with monkeypatch.context() as fault:
        fault.setattr(client.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected transaction failure"):
            client.post(_CREATE, json=incomplete)
    assert [_count(client, model) for model in _WRITE_TABLES] == initial_counts

    saved = _checked_json(client.post(_CREATE, json=incomplete), 201)
    product_id = saved["product_id"]
    assert saved["description"]["status"] == "incomplete"
    assert saved["description"]["diagnostics"] and saved["description"]["schedule"] is None
    assert _detail(client, product_id) == saved

    before_counts = [_count(client, model) for model in _WRITE_TABLES]
    completion = _revision_body(saved, terms=body["terms"])
    with monkeypatch.context() as fault:
        fault.setattr(client.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected transaction failure"):
            client.post(_revision_url(product_id), json=completion)
    assert [_count(client, model) for model in _WRITE_TABLES] == before_counts
    assert _detail(client, product_id) == saved

    repaired = _checked_json(client.post(_revision_url(product_id), json=completion), 200)
    assert (repaired["revision"], repaired["terms_version"], repaired["description"]["status"]) == (2, 2, "ready")
    assert _checked_json(client.post(_revision_url(product_id), json=completion), 200) == repaired
    assert _count(client, ProductRecord) == 1
    assert _count(client, ProductTermsVersion) == 2
    assert _count(client, ProductRevision) == 2
    assert _count(client, ProductCommand) == 2
