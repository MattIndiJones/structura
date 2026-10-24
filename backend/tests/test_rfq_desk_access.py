"""New RFQs are organization-owned; desk grants, not authorship, confer access."""
import json

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import rfq as rfq_api, rfq_desks as desks_api
from backend.app.db.models import (
    Entity, RfqDesk, RfqDeskMembership, RfqOwnership, RfqRequest, User,
)
from backend.app.services.product_repository import ProductError, owned_record
from backend.tests.test_rfq import _rfq_params


@pytest.fixture
def desk_case():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Entity(id=1, name="ClientTech"), Entity(id=2, name="Autre")])
        users = [User(id=i, username=f"desk-{i}", email=f"desk-{i}@example.test",
                      password_hash="x", entity_id=entity, role=role)
                 for i, entity, role in [(1, 1, "user"), (2, 1, "user"),
                                         (3, 1, "user"), (4, 2, "user"),
                                         (5, 1, "admin")]]
        session.add_all(users)
        session.add_all([RfqDesk(id=11, entity_id=1, name="Sales"),
                         RfqDesk(id=12, entity_id=1, name="Structuration"),
                         RfqDesk(id=21, entity_id=2, name="Sales")])
        session.add_all([
            RfqDeskMembership(desk_id=11, user_id=1,
                              rights_json=json.dumps(["read", "prepare", "price", "select", "solicit", "organize", "book"])),
            RfqDeskMembership(desk_id=11, user_id=2,
                              rights_json=json.dumps(["read", "prepare"])),
            RfqDeskMembership(desk_id=12, user_id=3,
                              rights_json=json.dumps(["read", "prepare", "price"])),
            RfqDeskMembership(desk_id=21, user_id=4,
                              rights_json=json.dumps(["read", "prepare", "price"])),
        ])
        session.commit()
        yield session, users


def _create(session, user, desk_id=11):
    return rfq_api.create_rfq(rfq_api.RfqCreate(
        pilot_desk_id=desk_id, name="Athena test",
        script_snapshot="AT MATURITY\n  PAY 1", params=_rfq_params()), user, session)


def test_creation_requires_authorized_pilot_desk_and_preserves_organization(desk_case):
    session, users = desk_case
    for desk_id, status in [(None, 422), (12, 403), (21, 403)]:
        with pytest.raises(HTTPException) as failure:
            _create(session, users[0], desk_id)
        assert failure.value.status_code == status
    rfq = _create(session, users[0])
    scope = session.get(RfqOwnership, rfq["id"])
    assert (scope.entity_id, scope.pilot_desk_id) == (1, 11)
    assert rfq["entity_id"] == 1
    assert rfq["access_rights"] == sorted(json.loads(session.exec(select(
        RfqDeskMembership.rights_json).where(RfqDeskMembership.user_id == 1)).first()))


def test_same_desk_reprises_but_other_desks_and_admin_cannot_read(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    assert rfq_api.get_rfq(rfq["id"], users[1], session)["id"] == rfq["id"]
    for user in users[2:]:
        with pytest.raises(HTTPException) as failure:
            rfq_api.get_rfq(rfq["id"], user, session)
        assert failure.value.status_code == 404
        assert rfq_api.list_rfqs(user, session) == []
    assert len(rfq_api.list_rfqs(users[1], session)) == 1


def test_model_input_identity_is_private_to_pricing_right(desk_case):
    from datetime import datetime
    session, users = desk_case
    created = _create(session, users[0])
    row = session.get(RfqRequest, created['id'])
    row.model_input_hash = 'a' * 64
    row.model_price = 101.
    row.model_price_at = datetime(2026, 10, 21, 8)
    session.add(row)
    session.commit()
    priced = rfq_api.get_rfq(row.id, users[0], session)
    assert priced['model_input_hash'] == 'a' * 64 and priced['model_price'] == 101.
    reader = rfq_api.get_rfq(row.id, users[1], session)
    assert reader['model_input_hash'] is None
    assert reader['model_price'] is None and reader['model_price_at'] is None


def test_share_is_capped_by_member_rights_and_revoke_cuts_open_links(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    rfq_api.share_rfq(rfq["id"], 12, rfq_api.RfqSharePut(
        rights=["read", "price", "select"], reason="Calcul Structuration"), users[0], session)
    colleague = users[2]
    assert rfq_api.get_rfq(rfq["id"], colleague, session)["access_rights"] == ["price", "read"]
    with pytest.raises(HTTPException) as failure:
        rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=42), colleague, session)
    assert failure.value.status_code == 403
    assert owned_record(session, rfq["product_id"], colleague).id == rfq["product_id"]
    with pytest.raises(ProductError):
        owned_record(session, rfq["product_id"], colleague, right="prepare")
    assert rfq_api.rfq_terms(rfq["id"], colleague, session)["terms_version"] == 1
    rfq_api.revoke_rfq_share(rfq["id"], 12, users[0], session)
    with pytest.raises(HTTPException) as failure:
        rfq_api.get_rfq(rfq["id"], colleague, session)
    assert failure.value.status_code == 404
    assert rfq_api.list_rfqs(colleague, session) == []


def test_creator_has_no_residual_access_after_membership_revoked(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    membership = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id == 11, RfqDeskMembership.user_id == 1)).first()
    membership.active = False
    session.add(membership)
    session.commit()
    with pytest.raises(HTTPException) as failure:
        rfq_api.get_rfq(rfq["id"], users[0], session)
    assert failure.value.status_code == 404
    assert rfq_api.get_rfq(rfq["id"], users[1], session)["id"] == rfq["id"]


def test_read_only_member_cannot_obtain_private_pricing_or_mutate(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    membership = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id == 11, RfqDeskMembership.user_id == 2)).first()
    membership.rights_json = '["read"]'
    session.add(membership)
    session.commit()
    row = rfq_api.get_rfq(rfq["id"], users[1], session)
    assert "underlyings" in row["params"]
    assert "model" not in row["params"]
    with pytest.raises(HTTPException) as failure:
        rfq_api.compose_rfq_pricing_input(rfq["id"], rfq_api.RfqPricingInput(
            expected_terms_version=1), users[1], session)
    assert failure.value.status_code == 403
    with pytest.raises(HTTPException) as failure:
        rfq_api.add_quote(rfq["id"], rfq_api.QuoteCreate(provider="Banque A"), users[1], session)
    assert failure.value.status_code == 403


def test_admin_can_manage_desks_without_reading_rfqs_or_granting_self(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    admin = users[4]
    with pytest.raises(HTTPException) as failure:
        rfq_api.get_rfq(rfq["id"], admin, session)
    assert failure.value.status_code == 404
    with pytest.raises(HTTPException) as failure:
        desks_api.put_membership(11, admin.id, desks_api.MembershipPut(
            user_id=admin.id, rights=["read"]), admin, session)
    assert failure.value.status_code == 403
    granted = desks_api.put_membership(11, users[1].id, desks_api.MembershipPut(
        user_id=users[1].id, rights=["read", "price"]), admin, session)
    assert granted["rights"] == ["price", "read"]
    with pytest.raises(HTTPException) as failure:
        desks_api.put_membership(21, users[3].id, desks_api.MembershipPut(
            user_id=users[3].id, rights=["read"]), admin, session)
    assert failure.value.status_code == 404


def test_assignment_replaces_responsible_without_changing_creator_or_terms(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    rfq_api.change_rfq_assignment(rfq["id"], rfq_api.RfqAssignmentPut(
        pilot_desk_id=11, responsible_user_id=users[1].id, expected_pilot_desk_id=11,
        expected_responsible_user_id=users[0].id, expected_share_desk_ids=[], retained_share_desk_ids=[],
        reason="Reprise du suivi"), users[0], session)
    updated = rfq_api.get_rfq(rfq["id"], users[0], session)
    assert updated["responsible_user_id"] == users[1].id
    assert updated["user_id"] == users[0].id
    assert updated["product_id"] == rfq["product_id"]
    assert updated["product_terms_version"] == rfq["product_terms_version"]


def test_transfer_does_not_leave_an_implicit_share_to_source_desk(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    rfq_api.share_rfq(rfq["id"], 12, rfq_api.RfqSharePut(rights=["read"], reason="Revue préalable"), users[0], session)
    rfq_api.change_rfq_assignment(rfq["id"], rfq_api.RfqAssignmentPut(
        pilot_desk_id=12, responsible_user_id=users[2].id, expected_pilot_desk_id=11,
        expected_responsible_user_id=users[0].id, expected_share_desk_ids=[12], retained_share_desk_ids=[],
        reason="Transfert Structuration"), users[0], session)
    with pytest.raises(HTTPException) as failure:
        rfq_api.get_rfq(rfq["id"], users[0], session)
    assert failure.value.status_code == 404
    assert rfq_api.get_rfq(rfq["id"], users[2], session)["pilot_desk_id"] == 12


def test_assignment_refuses_wrong_org_unentitled_responsible_and_stale_scope(desk_case):
    session, users = desk_case
    rfq = _create(session, users[0])
    settings = dict(pilot_desk_id=11, responsible_user_id=users[1].id, expected_pilot_desk_id=11,
        expected_responsible_user_id=users[0].id, expected_share_desk_ids=[], retained_share_desk_ids=[], reason="Reprise du suivi")
    for overrides, expected in [({"pilot_desk_id": 21, "responsible_user_id": users[3].id}, 422),
                                ({"responsible_user_id": users[2].id}, 422),
                                ({"expected_pilot_desk_id": 12}, 409),
                                ({"expected_share_desk_ids": [12]}, 409)]:
        with pytest.raises(HTTPException) as failure:
            rfq_api.change_rfq_assignment(rfq["id"], rfq_api.RfqAssignmentPut(**{**settings, **overrides}), users[0], session)
        assert failure.value.status_code == expected
