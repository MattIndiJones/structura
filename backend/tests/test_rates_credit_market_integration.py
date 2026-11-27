"""Prepare and reopen the nine native market witnesses through the Product API."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import func
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.db.database import get_session
from backend.app.db.migrations import m0002_native_valuation_contexts
from backend.app.db.models import NativeValuationContextRecord, ProductCalculationRun, ProductRevision
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_isda_market import request_data  # noqa: F401
from backend.tests.test_rates_credit_mixed_reader import _assert_error, _seed_native
from backend.tests.test_rates_credit_rates_market import build_rates_market
from backend.tests.test_rates_credit_rates_schedule import abc_reference  # noqa: F401


@pytest.fixture
def durable_product_client(product_client, tmp_path, monkeypatch):
    client = product_client
    directory = tmp_path.resolve()
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(directory))
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_DATA_DIR", str(directory))
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "1")
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES_USERS", "alice,bob")
    url = f"sqlite:///{(directory / 'structura.db').as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        m0002_native_valuation_contexts.upgrade(conn)
    client.session = Session(engine)
    client.session.add_all(type(user).model_validate(user) for user in client.users.values())
    client.session.commit()
    client.app.dependency_overrides[get_session] = lambda: client.session

    def restart_archive():
        nonlocal engine
        client.session.close()
        engine.dispose()
        engine = create_engine(url, connect_args={"check_same_thread": False})
        client.session = Session(engine)

    client.restart_archive = restart_archive
    yield client
    client.session.close()
    engine.dispose()


def _url(product):
    return f"/api/products/{product.product_id}/valuation-contexts"


def _body(product, key, cutoff, valuation_date, market):
    return {
        "terms_version": product.terms_version,
        "command_key": key,
        "cutoff": cutoff,
        "valuation_date": valuation_date,
        "market": market,
    }


def _create_context(client, product, body):
    response = client.post(_url(product), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _read_context(client, product, context_id):
    response = client.get(f"{_url(product)}/{context_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _count(client, model):
    return client.session.exec(select(func.count()).select_from(model)).one()


def test_six_rates_contexts_share_only_the_dated_market_and_reopen_without_preparation(
    durable_product_client, abc_reference, monkeypatch,
):
    client = durable_product_client
    frn, irs = (_seed_native(client, instrument) for instrument in ("FRN", "IRS"))
    archived = []
    for case, snapshot in abc_reference["snapshots"].items():
        market = build_rates_market(abc_reference, (frn, irs), case).model_dump(mode="json")
        pair = []
        for product in (frn, irs):
            instrument = product.terms.instrument_type.lower()
            body = _body(product, f"prepare-{instrument}-{case}", snapshot["cutoff_local"], snapshot["valuation_date"], market)
            reply = _create_context(client, product, body)
            context = reply["context"]
            assert context["readiness"] == "ready_for_pricing"
            assert context["terms_fingerprint"] == product.terms.fingerprint
            assert context["schedule_fingerprint"] == product.native_schedule.fingerprint
            selected = context["market"]
            assert selected["market_id"] == snapshot["market_id"]
            assert [fixing["fixing_id"] for fixing in selected["fixings"]] == snapshot["acquired_fixing_ids"]
            assert selected["flows"][0]["flow_id"] == abc_reference["first_payment"][f"{instrument}_flow_id"]
            assert selected["flows"][0]["state"] == snapshot["first_payment_state"]

            body["cutoff"] = datetime.fromisoformat(body["cutoff"]).astimezone(timezone.utc).isoformat()
            assert _create_context(client, product, body) == reply
            pair.append(context["market"]["market_fingerprint"])
            archived.append((product, reply))
        assert pair[0] == pair[1]

    assert len({reply["context"]["fingerprint"] for _, reply in archived}) == 6
    assert _count(client, NativeValuationContextRecord) == 6
    assert _count(client, ProductRevision) == 2
    assert _count(client, ProductCalculationRun) == 0

    def fail_preparation(*args, **kwargs):
        pytest.fail("Un contexte archivé ne doit pas sélectionner le marché à nouveau")

    monkeypatch.setattr("backend.app.api.products.prepare_native_context", fail_preparation)
    client.restart_archive()
    for product, reply in archived:
        assert _read_context(client, product, reply["context_id"]) == reply


def test_three_isda_contexts_preserve_quotes_and_exclude_the_oracle(durable_product_client, request_data):
    client = durable_product_client
    cds = _seed_native(client, "CDS")
    archived = []
    for scenario in request_data["scenarios"]:
        raw = {**request_data, "kind": "isda", "scenario_id": scenario["id"]}
        body = _body(cds, f"prepare-{scenario['id']}", "2021-04-26T12:00:00+02:00", "2021-04-26", raw)
        reply = _create_context(client, cds, body)
        context = reply["context"]
        selected = context["market"]
        assert context["readiness"] == "ready_for_curve_construction_and_conversion"
        assert selected["scenario"]["id"] == scenario["id"]
        assert selected["scenario"]["market_inputs"]["quoted_spread_bp"] == scenario["market_inputs"]["quoted_spread_bp"]
        assert selected["ois_quotes"]["rows"] == request_data["ois_quotes"]["rows"]
        assert selected["ois_quotes"]["rows"][0]["rate"] == -0.005683
        assert selected["ois_quotes"]["source_publication_timestamp"] is None
        assert "oracle" not in selected["scenario"]
        assert "workbook_oracle" not in selected["scenario"]
        archived.append(reply)

    assert len({reply["context"]["fingerprint"] for reply in archived}) == 3
    assert _count(client, ProductRevision) == 1
    assert _count(client, ProductCalculationRun) == 0
    client.restart_archive()
    for reply in archived:
        assert _read_context(client, cds, reply["context_id"]) == reply


def test_market_rejections_and_conflicting_key_preserve_the_existing_archive(durable_product_client, abc_reference):
    client = durable_product_client
    frn, irs = (_seed_native(client, instrument) for instrument in ("FRN", "IRS"))
    body = _body(frn, "prepare-frn-original", abc_reference["snapshots"]["A"]["cutoff_local"],
                 abc_reference["snapshots"]["A"]["valuation_date"],
                 build_rates_market(abc_reference, (frn, irs), "A").model_dump(mode="json"))
    original = _create_context(client, frn, body)
    original_url = f"{_url(frn)}/{original['context_id']}"

    conflict = {**body, "cutoff": "2026-09-16T12:01:00+02:00"}
    _assert_error(client.post(_url(frn), json=conflict), "NATIVE_CONTEXT_COMMAND_CONFLICT")

    wrong_curve = deepcopy(body)
    wrong_curve["market"]["projection"]["tenor"] = "6M"
    _assert_error(client.post(_url(frn), json=wrong_curve), "RATES_CURVE_INCOMPATIBLE", 422)

    wrong_author = deepcopy(body)
    discount = wrong_author["market"]["discount"]
    discount["override"] = {
        "override_id": "unauthorized", "pillars": discount["pillars"],
        "reason": "Test de droits", "author": "bob", "approved_at": body["cutoff"],
    }
    _assert_error(client.post(_url(frn), json=wrong_author), "MARKET_OVERRIDE_AUTHOR_MISMATCH", 403)
    _assert_error(client.get(f"{_url(irs)}/{original['context_id']}"), "NATIVE_CONTEXT_NOT_FOUND", 404)

    client.current["user"] = client.users["bob"]
    assert client.post(_url(frn), json=body).status_code == 404
    assert client.get(original_url).status_code == 404
    client.current["user"] = client.users["alice"]

    assert _read_context(client, frn, original["context_id"]) == original
    assert _count(client, NativeValuationContextRecord) == 1
