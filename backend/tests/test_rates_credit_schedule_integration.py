"""Exercise native schedule preview and retained Product reads through HTTP."""

import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.core.product.models import Product
from backend.app.core.valuation_context import canonical_json
from backend.app.db.models import ProductCalculationRun, ProductRecord, ProductRevision, ProductTermsVersion, User
from backend.app.services.product_repository import load_product, stage_new_product, stage_revision, stage_terms
from backend.tests.test_products import _create, product_client
from backend.tests.test_rates_credit_mixed_reader import _native_terms, _project, _seed_native


_FIXTURES = Path(__file__).with_name("fixtures")
_RATES = json.loads((_FIXTURES / "rates_credit_abc.json").read_text(encoding="utf-8"))
_ISDA = json.loads((_FIXTURES / "rates_credit_isda.json").read_text(encoding="utf-8"))
_PREVIEW_URL = "/api/products/schedule/preview"


def _preview(client, terms):
    response = client.post(_PREVIEW_URL, json={"terms": terms})
    assert response.status_code == 200, response.text
    return response.json()


def _ready(client, terms):
    preview = _preview(client, terms)
    assert preview["status"] == "ready"
    assert preview["diagnostics"] == []
    return preview["schedule"]


@pytest.mark.parametrize("instrument", ["FRN", "IRS", "CDS"])
def test_preview_is_deterministic_and_does_not_create_a_product(product_client, instrument):
    native = _native_terms(instrument)
    first = _ready(product_client, native)
    assert _ready(product_client, native) == first
    assert first["instrument_type"] == instrument
    assert first["product_id"] is first["terms_version"] is None
    assert first["fingerprint"] and first["terms_fingerprint"] and first["calendar_versions"]

    if instrument in {"FRN", "IRS"}:
        floating = first["legs"][0]["periods"]
        flow_key = "frn_flow_id" if instrument == "FRN" else "irs_flow_id"
        observed = [
            (row["period_id"], row["flow_id"], row["unadjusted_end"], row["accrual_start"],
             row["accrual_end"], row["fixing_date"], row["payment_date"], row["day_count_days"],
             row["day_count_denominator"], row["projection_start"], row["projection_end"])
            for row in floating
        ]
        assert observed == [
            (row["period_id"], row[flow_key], row["end_unadjusted"], row["start_adjusted"],
             row["end_adjusted"], row["fixing_date"], row["payment_date"], row["act360_days"],
             360, row["start_adjusted"], row["end_adjusted"])
            for row in _RATES["floating_periods"]
        ]
        if instrument == "FRN":
            principal, = first["legs"][1]["events"]
            assert (principal["event_id"], principal["flow_id"], principal["date"]) == (
                "principal-01", "frn-principal", floating[-1]["payment_date"],
            )
            assert principal["flow_id"] != floating[-1]["flow_id"]
        else:
            fixed = first["legs"][1]["periods"]
            assert [(row["flow_id"], row["payment_date"], row["day_count_days"], row["fixing_date"]) for row in fixed] == [
                (row["flow_id"], row["payment_date"], 360, None) for row in _RATES["fixed_periods"]
            ]
    else:
        premiums = first["legs"][0]["periods"]
        chronology = _ISDA["cds_chronology"]
        assert len(premiums) == 21
        assert sum(row["day_count_days"] for row in premiums) == 1917
        assert premiums[0]["accrual_start"] == chronology["initial_accrual_start_date"]
        assert premiums[-1]["accrual_end"] == chronology["final_accrual_end_exclusive_date"]
        assert premiums[-1]["credit_observation_date"] == chronology["protection_end_inclusive_date"]
        assert premiums[-1]["payment_date"] == chronology["final_premium_payment_date"]
        assert [(event["kind"], event["date"]) for event in first["legs"][1]["events"]] == [
            ("step_in", chronology["step_in_date"]),
            ("protection_end", chronology["protection_end_inclusive_date"]),
        ]
        initial_settlement, = first["legs"][2]["events"]
        assert initial_settlement["date"] == chronology["initial_cash_settlement_date"]
        assert initial_settlement["accrued_days"] == 36

    assert product_client.session.exec(select(ProductRecord)).all() == []
    assert product_client.session.exec(select(ProductRevision)).all() == []
    assert product_client.session.exec(select(ProductCalculationRun)).all() == []


def test_preview_marks_incomplete_terms_without_creating_a_product(product_client):
    native = _native_terms("FRN")
    del native["floating_leg"]["fixing_calendar"]
    result = _preview(product_client, native)
    assert result["status"] == "incomplete"
    assert result["schedule"] is None
    assert result["diagnostics"]
    assert product_client.session.exec(select(ProductRecord)).all() == []


def test_preview_refuses_unknown_fixing_calendar_without_creating_a_product(product_client):
    terms = _native_terms("FRN")
    terms["floating_leg"]["fixing_calendar"] = "UNKNOWN"
    response = product_client.post(_PREVIEW_URL, json={"terms": terms})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PRODUCT_SCHEDULE_INVALID"
    assert "fixing" in response.json()["detail"]["message"]
    assert product_client.session.exec(select(ProductRecord)).all() == []


def test_native_schedule_snapshots_survive_a_database_reopen(tmp_path, monkeypatch):
    from backend.app.core.product import native_schedule

    url = f"sqlite:///{tmp_path / 'schedule-replay.sqlite'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    snapshots = {}
    try:
        with Session(engine) as session:
            actor = User(username="schedule-pilot", email="schedule@example.test", password_hash="test", role="user")
            session.add(actor)
            session.flush()
            for instrument in ("FRN", "IRS", "CDS"):
                product = Product.model_validate({"terms": _native_terms(instrument)})
                saved = stage_new_product(session, product, user=actor)
                snapshots[saved.product_id] = saved.native_schedule.model_dump(mode="json")
            session.commit()
    finally:
        engine.dispose()

    def fail_resolution(*_args, **_kwargs):
        pytest.fail("Reopening the database must not resolve the schedule again")

    monkeypatch.setattr(native_schedule, "resolve_native_schedule", fail_resolution)
    reopened_engine = create_engine(url)
    try:
        with Session(reopened_engine) as session:
            for product_id, expected in snapshots.items():
                reopened = load_product(session, product_id, allow_native=True)
                assert reopened.native_schedule.model_dump(mode="json") == expected
    finally:
        reopened_engine.dispose()


def test_native_schedules_reopen_by_terms_version_without_resolution(product_client, monkeypatch):
    from backend.app.core.product import native_schedule

    client = product_client
    frn = _seed_native(client, "FRN")
    path = f"/api/products/{frn.product_id}?view=mixed"
    original = _project(client, path)["description"]
    assert original["status"] == "ready"
    saved = original["schedule"]
    assert (saved["product_id"], saved["terms_version"], saved["terms_fingerprint"]) == (
        frn.product_id, 1, frn.terms_fingerprint,
    )
    preview = _ready(client, _native_terms("FRN"))
    assert saved["legs"] == preview["legs"]

    amended_terms = _native_terms("FRN")
    amended_terms["maturity_date"] = "2028-12-21"
    next_terms = Product.model_validate({"terms": amended_terms}).terms
    actor = client.users["alice"].id
    amended = stage_terms(client.session, frn, next_terms, actor_id=actor, reason="Témoin calendrier modifié")
    stage_revision(client.session, amended, expected_revision=1, actor_id=actor,
                   action="PRODUCT_TERMS_REVISED", reason="Témoin calendrier modifié")
    client.session.commit()
    revised = _project(client, path)["description"]
    assert revised["schedule"]["terms_version"] == 2
    assert revised["schedule"]["fingerprint"] != saved["fingerprint"]

    def fail_resolution(*_args, **_kwargs):
        pytest.fail("Opening a retained Product must use the frozen schedule")

    monkeypatch.setattr(native_schedule, "resolve_native_schedule", fail_resolution)
    client.session.expire_all()
    assert _project(client, path)["description"] == revised
    assert _project(client, f"{path}&revision=1&terms_version=1")["description"] == original
    assert _project(client, f"{path}&terms_version=1")["description"] == original
    client.current["user"] = client.users["bob"]
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("case", ["altered-fingerprint", "other-product"])
def test_mixed_detail_refuses_corrupted_and_misbound_schedules(product_client, case):
    client = product_client
    frn = _seed_native(client, "FRN")
    if case == "other-product":
        other = _seed_native(client, "FRN")
        other_row = client.session.exec(select(ProductRevision).where(ProductRevision.product_id == other.product_id)).one()
        other_schedule = json.loads(other_row.snapshot_json)["native_schedule"]

    row = client.session.exec(select(ProductRevision).where(ProductRevision.product_id == frn.product_id)).one()
    payload = json.loads(row.snapshot_json)
    if case == "other-product":
        payload["native_schedule"] = other_schedule
    else:
        payload["native_schedule"]["fingerprint"] = "0" * 64
    row.snapshot_json = canonical_json(payload)
    client.session.add(row)
    client.session.commit()

    path = f"/api/products/{frn.product_id}?view=mixed"
    response = client.get(path)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "PRODUCT_SCHEDULE_INVALID"
    client.current["user"] = client.users["bob"]
    assert client.get(path).status_code == 404


def test_payscript_detail_preserves_its_registered_calendar_when_native_preview_is_available(product_client):
    product = _create(product_client, key="payscript-before-preview")
    product_url = f"/api/products/{product['product_id']}"
    original = _project(product_client, product_url)
    stored_terms = product_client.session.exec(select(ProductTermsVersion)).one().terms_json

    _ready(product_client, _native_terms("FRN"))
    mixed = _project(product_client, f"{product_url}?view=mixed")
    assert _project(product_client, product_url) == original
    assert (mixed["terms"], mixed["description"]) == (original["terms"], original["description"])
    assert mixed["terms"]["resolved_events"] == product["terms"]["resolved_events"]
    assert product_client.session.exec(select(ProductTermsVersion)).one().terms_json == stored_terms
