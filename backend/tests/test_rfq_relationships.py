"""Bilateral recognition and recipient gates on isolated, FK-enforced data."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api import rfq as rfq_api, rfq_relations as relations_api
from backend.app.db.models import (
    Counterparty, Entity, RfqDesk, RfqDeskMembership, RfqRelationship, User,
)
from backend.app.db.trading_models import TradingRelationship
from backend.app.runtime import business_today
from backend.app.services import rfq_relationships as service
from backend.tests.test_rfq import _rfq_params


@pytest.fixture
def network_case():
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Entity(id=1, name="ClientTech"), Entity(id=2, name="BNP"), Entity(id=3, name="Citi")])
        session.flush()
        users = [User(id=i, username=f"org-{i}", email=f"org-{i}@example.test", password_hash="x",
                      entity_id=entity, role=role) for i, entity, role in [(1, 1, "admin"), (2, 2, "admin"), (3, 3, "admin"), (4, 1, "user")]]
        session.add_all(users)
        session.flush()
        session.add_all([RfqDesk(id=11, entity_id=1, name="Sales"), RfqDesk(id=21, entity_id=2, name="Pricing"), RfqDesk(id=31, entity_id=3, name="Pricing")])
        session.add_all([Counterparty(id=1, name="BNP juridique"), Counterparty(id=2, name="ClientTech juridique")])
        session.flush()
        session.add(RfqDeskMembership(desk_id=11, user_id=4, rights_json='["read","prepare","solicit","price"]'))
        session.commit()
        rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
            pilot_desk_id=11, name="Athena", transaction_format="EMTN", instrument_family="Note",
            payoff_family="Autocall", script_snapshot="AT MATURITY\n  PAY 1", params=_rfq_params()), users[3], session)
        yield session, users, rfq


def terms(**overrides):
    return service.RelationshipTerms(formats=["EMTN"], instruments=["Note"], payoff_families=["Athena"],
        currencies=["EUR"], effective_date=business_today(), solicitation_allowed=True, **overrides)


def create(session, user, **overrides):
    values = dict(partner_entity_id=2, receiver_desk_id=21, reference="CLIENT-BNP",
                  counterparty_id=1, terms=terms(), reason="Ouverture du pilote")
    values.update(overrides)
    return service.create_relation(session, user, service.RelationshipCreate(**values))


def active(session, users):
    row = create(session, users[0])
    row = service.update_relation(session, row["id"], users[1], service.RelationshipUpdate(
        expected_version=row["version"], receiver_desk_id=21, terms=terms(), counterparty_id=2,
        contacts=[service.SharedContact(name="Desk BNP", email="pricing@bnp.test")], reason="Mapping bancaire"))
    for user in users[:2]:
        row = service.recognize_relation(session, row["id"], user, service.RelationshipDecision(
            expected_version=row["version"], reason="Reconnaissance de la version"))
    return row


def preview(rfq, relationship_ids):
    return rfq_api.RfqExchangePreview(expected_terms_version=rfq["product_terms_version"],
        shared_title="Athena partagé", response_deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        relationship_ids=relationship_ids)


def test_relation_requires_both_parties_and_explicit_local_mapping(network_case):
    session, users, rfq = network_case
    row = create(session, users[0])
    row = service.recognize_relation(session, row["id"], users[0], service.RelationshipDecision(
        expected_version=1, reason="Validation client"))
    assert row["status"] == "PENDING"
    assert rfq_api.authorized_rfq_recipients(rfq["id"], users[3], session)["eligible"] == []
    with pytest.raises(HTTPException) as failure:
        service.recognize_relation(session, row["id"], users[1], service.RelationshipDecision(
            expected_version=1, reason="Validation banque"))
    assert failure.value.status_code == 422


def test_authorized_projection_preserves_product_without_private_booking_data(network_case):
    session, users, rfq = network_case
    row = active(session, users)
    assert row["status"] == "ACTIVE"
    recipients = rfq_api.authorized_rfq_recipients(rfq["id"], users[3], session)
    assert [r["label"] for r in recipients["eligible"]] == ["BNP"]
    packet = rfq_api.preview_rfq_exchange(rfq["id"], preview(rfq, [row["id"]]), users[3], session)
    assert packet["delivery_available"] is True
    recipient = packet["messages"][0]["request"]["recipient"]
    assert recipient["organization_id"] == 2 and recipient["desk_id"] == 21
    assert recipient["relationship_version"] == row["version"]
    assert "trading_relationship_id" not in str(packet)
    assert "contacts" not in str(packet)


def test_suspension_rechecked_after_list_and_resume_needs_recognition(network_case):
    session, users, rfq = network_case
    row = active(session, users)
    service.suspend_relation(session, row["id"], users[1], service.RelationshipSuspension(
        expected_version=row["version"], suspended=True, reason="Suspension bancaire"))
    with pytest.raises(HTTPException) as failure:
        rfq_api.preview_rfq_exchange(rfq["id"], preview(rfq, [row["id"]]), users[3], session)
    assert failure.value.status_code == 422
    row = service.suspend_relation(session, row["id"], users[1], service.RelationshipSuspension(
        expected_version=row["version"], suspended=False, reason="Reprise bancaire"))
    assert row["status"] == "PENDING"


def test_changed_terms_invalidate_both_and_stale_references_are_refused(network_case):
    session, users, rfq = network_case
    row = active(session, users)
    old_version = row["version"]
    row = service.update_relation(session, row["id"], users[0], service.RelationshipUpdate(
        expected_version=old_version, receiver_desk_id=21, terms=terms(max_notional=500_000),
        counterparty_id=1, reason="Révision du plafond"))
    assert row["version"] == old_version + 1
    assert not any(p["recognized"] for p in row["recognitions"])
    with pytest.raises(HTTPException) as failure:
        service.recognize_relation(session, row["id"], users[1], service.RelationshipDecision(
            expected_version=old_version, reason="Ancienne version"))
    assert failure.value.status_code == 409


@pytest.mark.parametrize("overrides, expected", [
    ({"max_notional": 500_000}, "Nominal"), ({"currencies": ["USD"]}, "Devise"),
    ({"formats": ["OTC"]}, "Format"), ({"instruments": ["Swap"]}, "Instrument"),
    ({"payoff_families": ["Phoenix"]}, "Famille"), ({"indicative_allowed": False}, "Nature"),
    ({"effective_date": business_today() + timedelta(days=2)}, "vigueur"),
])
def test_perimeter_controls_do_not_depend_on_browser_filters(network_case, overrides, expected):
    session, users, rfq = network_case
    row = active(session, users)
    settings = terms().model_dump()
    settings.update(overrides)
    row = service.update_relation(session, row["id"], users[0], service.RelationshipUpdate(
        expected_version=row["version"], receiver_desk_id=21,
        terms=service.RelationshipTerms(**settings), counterparty_id=1, reason="Nouveau périmètre"))
    for user in users[:2]:
        service.recognize_relation(session, row["id"], user, service.RelationshipDecision(
            expected_version=row["version"], reason="Accord de périmètre"))
    result = rfq_api.authorized_rfq_recipients(rfq["id"], users[3], session)
    assert result["eligible"] == []
    assert any(expected in issue for issue in result["excluded"][0]["issues"])


def test_other_organizations_and_nonadmins_cannot_manage_relationships(network_case):
    session, users, rfq = network_case
    row = active(session, users)
    with pytest.raises(HTTPException) as failure:
        relations_api.get_relation(row["id"], users[2], session)
    assert failure.value.status_code == 404
    assert relations_api.list_relations(users[2], session) == []
    with pytest.raises(HTTPException) as failure:
        create(session, users[3], reference="SECOND")
    assert failure.value.status_code == 403
    history = relations_api.relation_history(row["id"], users[0], session, limit=100)
    assert len(history["entries"]) == 4
    assert "trading_relationship_id" not in str(history)


def test_existing_booking_agreements_are_linked_explicitly_in_local_scope(network_case):
    session, users, rfq = network_case
    session.add(TradingRelationship(id=7, entity_id=2, counterparty_id=2, reference="PRIVATE-BANK",
        terms_json=json.dumps({"status": "ACTIVE", "currency": "EUR", "documentation_reference": "DOC"}), updated_by=users[1].id))
    session.commit()
    with pytest.raises(HTTPException) as failure:
        create(session, users[0], trading_relationship_id=7)
    assert failure.value.status_code == 422
    with pytest.raises(HTTPException) as failure:
        create(session, users[0], terms=terms(to_trade_allowed=True, treatment_allowed=True, documentation_reference="DOC"))
    assert failure.value.status_code == 422


@pytest.mark.parametrize("overrides", [{"min_notional": float("nan")}, {"max_notional": float("inf")}, {"formats": ["*"]}, {"payoff_families": ["Inconnu"]}])
def test_invalid_material_terms_are_refused(overrides):
    settings = terms().model_dump()
    settings.update(overrides)
    with pytest.raises(ValidationError):
        service.RelationshipTerms(**settings)
