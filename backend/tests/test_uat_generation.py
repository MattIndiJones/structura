"""Regression tests for the Admin RFQ / booking UAT generator."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.rfq_controls import booking_gate_failures
from backend.app.db.models import (
    Alert, AuditEvent, Counterparty, Deal, DealEvent, Entity, LifecycleProposal,
    OfficialFixingVersion, RfqProvider, RfqQuote, RfqRequest,
    UatGenerationBatch, User,
)
from backend.app.services.uat_generation import (
    UatGenerationRequest, delete_batch, generate_batch, preview_generation,
)


def _session_and_users() -> tuple[Session, User, User]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    entity = Entity(name="UAT tests")
    session.add(entity)
    session.flush()
    admin = User(
        username="uat-admin", email="uat-admin@test", password_hash="x",
        role="admin", entity_id=entity.id)
    target = User(
        username="uat-target", email="uat-target@test", password_hash="x",
        role="user", entity_id=entity.id)
    ubs = Counterparty(name="UBS", country="CH", active=True)
    bnp = Counterparty(name="BNP Paribas", country="FR", active=True)
    session.add(admin); session.add(target); session.add(ubs); session.add(bnp)
    session.flush()
    session.add(RfqProvider(label="UBS", counterparty_id=ubs.id, active=True))
    session.add(RfqProvider(
        label="BNP Paribas", counterparty_id=bnp.id, active=True))
    session.commit()
    session.refresh(admin); session.refresh(target)
    return session, admin, target


def _request(target: User, **overrides) -> UatGenerationRequest:
    values = {
        "target_user_id": target.id,
        "mode": "FULL_CHAIN",
        "count": 2,
        "seed": 17,
        "product_types": ["ATHENA", "PHOENIX"],
        "underlying_tickers": ["^STOXX50E", "^GSPC"],
        "max_underlyings": 2,
        "quotes_per_rfq": 2,
    }
    values.update(overrides)
    return UatGenerationRequest(**values)


def test_preview_is_deterministic_and_read_only():
    session, _, target = _session_and_users()
    body = _request(target)
    first = preview_generation(body, session)
    second = preview_generation(body, session)
    assert first == second
    assert first["rfq_count"] == 2
    assert first["deal_count"] == 2
    assert not session.exec(select(RfqRequest)).first()
    assert not session.exec(select(Deal)).first()
    assert not session.exec(select(UatGenerationBatch)).first()


def test_full_chain_uses_uat_references_and_batch_cleanup_is_isolated():
    session, admin, target = _session_and_users()
    ordinary = Deal(
        reference="LIVE-DO-NOT-DELETE", user_id=target.id,
        script_snapshot="AT MATURITY\n  PAY 1", sens="vente",
        contrepartie="UBS", devise="EUR", nominal=100_000,
        fair_value=99.0, price_traded=99.2,
        trade_date=date.today().isoformat(), strike_date=date.today().isoformat(),
        value_date=date.today().isoformat(), maturity_date="2030-01-01", T=3.0,
        underlyings_json="[]", market_snapshot_json="{}")
    session.add(ordinary)
    session.commit()

    batch = generate_batch(_request(target), admin, session)
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).all()
    deals = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).all()
    assert batch["status"] == "COMPLETED"
    assert len(rfqs) == len(deals) == 2
    assert all(rfq.reference.startswith("UAT-RFQ-") for rfq in rfqs)
    assert all(deal.reference.startswith("UAT-DEAL-") for deal in deals)
    assert all(deal.rfq_id for deal in deals)
    assert all(rfq.status == "clos" for rfq in rfqs)
    created_audit = session.exec(select(AuditEvent).where(
        AuditEvent.action == "RFQ_CREATED",
        AuditEvent.object_id == rfqs[0].id)).one()
    booked_audit = session.exec(select(AuditEvent).where(
        AuditEvent.action == "BOOKING_ACCEPTED",
        AuditEvent.object_id == deals[0].id)).one()
    assert json.loads(created_audit.after_json)["reference"].startswith("UAT-RFQ-")
    assert json.loads(booked_audit.after_json)["reference"].startswith("UAT-DEAL-")
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "UAT_BATCH_GENERATED")).one()

    deleted = delete_batch(batch["id"], admin, session)
    assert deleted == {
        "id": batch["id"], "status": "DELETED",
        "deleted_rfqs": 2, "deleted_deals": 2,
    }
    assert session.exec(select(Deal).where(
        Deal.reference == "LIVE-DO-NOT-DELETE")).one()
    assert not session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).first()
    assert session.get(UatGenerationBatch, batch["id"]).status == "DELETED"


def test_rfq_control_mix_builds_expected_non_bookable_cases():
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, mode="RFQ_ONLY", count=4, quotes_per_rfq=1,
        rfq_profile="CONTROL_MIX"), admin, session)
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"]).order_by(RfqRequest.created_at)).all()
    assert len(rfqs) == 4

    codes_by_index = []
    for rfq in rfqs:
        selected = session.get(RfqQuote, rfq.selected_quote_id) \
            if rfq.selected_quote_id else None
        expected_counterparty = selected.provider if selected else ""
        codes_by_index.append({failure.code for failure in booking_gate_failures(
            rfq, selected,
            expected_counterparty=expected_counterparty or None,
            requested_counterparty=expected_counterparty,
        )})
    assert codes_by_index[0] == set()
    assert "QUOTE_EXPIRED" in codes_by_index[1]
    assert "QUOTE_NOT_FIRM" in codes_by_index[2]
    assert "QUOTE_NOT_SELECTED" in codes_by_index[3]


def test_invalid_ranges_are_rejected_before_batch_creation():
    session, _, target = _session_and_users()
    with pytest.raises(HTTPException) as exc:
        preview_generation(_request(
            target, maturity_min_years=5, maturity_max_years=1), session)
    assert exc.value.status_code == 422
    assert "maturité minimale" in str(exc.value.detail).lower()
    assert not session.exec(select(UatGenerationBatch)).first()


@pytest.mark.parametrize("family", [
    "ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED",
])
def test_every_offered_product_family_completes_the_full_chain(family):
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, count=1, product_types=[family], seed=3), admin, session)
    assert batch["status"] == "COMPLETED"
    assert batch["rfq_count"] == batch["deal_count"] == 1


@pytest.mark.parametrize(("profile", "family", "deal_status", "outcome"), [
    ("CURRENT_ACTIVE", "ATHENA", "actif", None),
    ("FORWARD_START", "CAPITAL_GUARANTEED", "actif", None),
    ("ACTIVE_1Y_PENDING", "ATHENA", "actif", None),
    ("ACTIVE_2Y_OFFICIAL", "PHOENIX", "actif", None),
    ("MATURED_PENDING", "REVERSE_CONVERTIBLE", "actif", None),
    ("CALLED", "ATHENA", "callé", "callé"),
    ("MATURED_FINAL", "CAPITAL_GUARANTEED", "échu", "final"),
    ("MATURED_KI", "REVERSE_CONVERTIBLE", "échu", "ki"),
])
def test_each_historical_lifecycle_profile_is_materialized_coherently(
    profile, family, deal_status, outcome,
):
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target,
        mode="BOOKED_ONLY",
        count=1,
        seed=29,
        product_types=[family],
        lifecycle_profile=profile,
    ), admin, session)
    assert batch["status"] == "COMPLETED"
    scenario = batch["result"]["scenarios"][0]
    assert scenario["profile"] == profile

    deal = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).one()
    events = session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id)).all()
    assert deal.status == deal_status
    assert deal.resolution_outcome == outcome

    if profile == "FORWARD_START":
        assert date.fromisoformat(deal.strike_date) > date.today()
        assert all(date.fromisoformat(event.event_date) > date.today()
                   for event in events)
    if profile in {"ACTIVE_1Y_PENDING", "MATURED_PENDING"}:
        missing = [event for event in events if event.fixing_status == "MISSING"]
        assert missing
        if profile == "ACTIVE_1Y_PENDING":
            assert any(event.t_years > 0 for event in missing)
        assert scenario["missing_fixings"] == len(missing)
        assert len(session.exec(select(Alert).where(Alert.deal_id == deal.id)).all()) \
            == len(missing)
    if profile == "ACTIVE_2Y_OFFICIAL":
        validated = [event for event in events if event.fixing_status == "VALIDATED"]
        assert validated
        assert any(event.t_years > 0 for event in validated)
        assert scenario["official_fixings"] == len(validated)
        assert not session.exec(select(LifecycleProposal).where(
            LifecycleProposal.deal_id == deal.id)).first()
    if outcome:
        proposal = session.exec(select(LifecycleProposal).where(
            LifecycleProposal.deal_id == deal.id)).one()
        assert proposal.status == "APPLIED"
        assert proposal.comparison_status == "MATCH"
        assert scenario["outcome"] == outcome
        assert session.exec(select(OfficialFixingVersion).where(
            OfficialFixingVersion.deal_id == deal.id)).first()


def test_complete_mix_covers_all_eight_profiles_and_cleans_terminal_dependencies():
    session, admin, target = _session_and_users()
    body = _request(
        target,
        mode="FULL_CHAIN",
        count=8,
        seed=31,
        product_types=[
            "ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED",
        ],
        lifecycle_profile="COMPLETE_MIX",
    )
    preview = preview_generation(body, session)
    assert set(preview["profile_counts"]) == {
        "CURRENT_ACTIVE", "FORWARD_START", "ACTIVE_1Y_PENDING",
        "ACTIVE_2Y_OFFICIAL", "MATURED_PENDING", "CALLED",
        "MATURED_FINAL", "MATURED_KI",
    }
    assert all(count == 1 for count in preview["profile_counts"].values())

    batch = generate_batch(body, admin, session)
    assert {row["profile"] for row in batch["result"]["scenarios"]} \
        == set(preview["profile_counts"])
    assert session.exec(select(OfficialFixingVersion)).first()
    assert session.exec(select(LifecycleProposal)).first()
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).all()
    assert len(rfqs) == 8
    assert all(rfq.status == "clos" for rfq in rfqs)
    assert any(date.fromisoformat(rfq.ao_date) < date.today() for rfq in rfqs)

    delete_batch(batch["id"], admin, session)
    assert not session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).first()
    assert not session.exec(select(OfficialFixingVersion)).first()
    assert not session.exec(select(LifecycleProposal)).first()
    assert not session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).first()


def test_periodic_historical_profile_rejects_non_periodic_product_selection():
    session, _, target = _session_and_users()
    with pytest.raises(HTTPException) as exc:
        preview_generation(_request(
            target,
            product_types=["REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED"],
            lifecycle_profile="ACTIVE_2Y_OFFICIAL",
        ), session)
    assert exc.value.status_code == 422
    assert "Athena ou Phoenix" in str(exc.value.detail)
