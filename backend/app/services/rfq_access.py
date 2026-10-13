"""Desk-scoped access to new RFQs. Historical rows retain creator-only access."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from ..db.models import (
    RfqDesk, RfqDeskMembership, RfqDeskShare, RfqOwnership, RfqRequest, User,
)
from ..core.audit import record_audit_event

RIGHTS = frozenset({"read", "prepare", "price", "select", "solicit", "organize", "book", "validate_quote", "publish_quote"})


def _valid(row, now: datetime) -> bool:
    return bool(row.active and (row.expires_at is None or row.expires_at > now))


def membership_rights(session: Session, desk_id: int, user: User) -> set[str]:
    desk = session.get(RfqDesk, desk_id)
    if not user.is_active or not user.entity_id or not desk or not desk.active \
            or desk.entity_id != user.entity_id:
        return set()
    membership = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id == desk_id,
        RfqDeskMembership.user_id == user.id,
    )).first()
    return set(json.loads(membership.rights_json)) & RIGHTS \
        if membership and _valid(membership, datetime.utcnow()) else set()


def ownership(session: Session, rfq_id: int) -> RfqOwnership | None:
    return session.get(RfqOwnership, rfq_id)


def effective_rights(session: Session, rfq: RfqRequest, user: User) -> set[str]:
    creator = session.get(User, rfq.user_id)
    if creator and creator.username == "__rfq_transport__":
        return set()
    scope = ownership(session, rfq.id)
    if scope is None:
        return RIGHTS if getattr(user, "is_active", True) and rfq.user_id == user.id else set()
    if not user.is_active or scope.entity_id != user.entity_id or rfq.entity_id != scope.entity_id:
        return set()
    rights = membership_rights(session, scope.pilot_desk_id, user)
    shares = session.exec(select(RfqDeskShare).where(
        RfqDeskShare.rfq_id == rfq.id,
        RfqDeskShare.active == True,  # noqa: E712
    )).all()
    now = datetime.utcnow()
    for share in shares:
        if _valid(share, now):
            rights |= membership_rights(session, share.desk_id, user) & set(
                json.loads(share.rights_json))
    return rights


def require_rfq_access(session: Session, rfq_id: int, user: User,
                       right: str = "read") -> RfqRequest:
    rfq = session.get(RfqRequest, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ introuvable")
    rights = effective_rights(session, rfq, user)
    if not rights or "read" not in rights:
        raise HTTPException(404, "RFQ introuvable")
    if right not in rights:
        raise HTTPException(403, "Habilitation RFQ insuffisante pour cette action")
    return rfq


def require_create_desk(session: Session, desk_id: int | None, user: User) -> RfqDesk:
    if desk_id is None or user.entity_id is None:
        raise HTTPException(422, "Choisissez un desk pilote habilité pour votre organisation.")
    desk = session.get(RfqDesk, desk_id)
    if not desk or not desk.active or desk.entity_id != user.entity_id \
            or "prepare" not in membership_rights(session, desk_id, user):
        raise HTTPException(403, "Création RFQ non autorisée pour ce desk.")
    return desk


def visible_rfqs(session: Session, user: User) -> list[RfqRequest]:
    # Query the user's organization plus historical creator rows, then apply
    # the same access predicate used by direct links and mutations.
    candidates = session.exec(select(RfqRequest).where(
        (RfqRequest.entity_id == user.entity_id) | (RfqRequest.user_id == user.id)
    ).order_by(RfqRequest.created_at.desc())).all()
    return [rfq for rfq in candidates if "read" in effective_rights(session, rfq, user)]


def lock_rfq_organization(session: Session, rfq_id: int, user: User, right: str = "organize") -> RfqRequest:
    """Serialize sharing/assignment and recheck grants after obtaining the write lock."""
    rfq = require_rfq_access(session, rfq_id, user, right)
    scope = ownership(session, rfq_id)
    if scope is not None:
        result = session.execute(update(RfqOwnership).where(
            RfqOwnership.rfq_id == rfq_id, RfqOwnership.pilot_desk_id == scope.pilot_desk_id,
            RfqOwnership.responsible_user_id == scope.responsible_user_id,
        ).values(pilot_desk_id=scope.pilot_desk_id)
          .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "Le périmètre du dossier a changé ; rechargez-le")
        session.expire_all()
        rfq = require_rfq_access(session, rfq_id, user, right)
    return rfq


def assign_rfq(session: Session, rfq_id: int, user: User, *, pilot_desk_id: int,
               responsible_user_id: int, expected_pilot_desk_id: int,
               expected_responsible_user_id: int | None, expected_share_desk_ids: list[int],
               retained_share_desk_ids: list[int], reason: str) -> dict:
    lock_rfq_organization(session, rfq_id, user)
    scope = ownership(session, rfq_id)
    if scope is None:
        raise HTTPException(409, "L'affectation par desk concerne les nouveaux dossiers RFQ")
    desk = session.get(RfqDesk, pilot_desk_id)
    responsible = session.get(User, responsible_user_id)
    if not desk or not desk.active or desk.entity_id != scope.entity_id or not responsible \
            or "read" not in membership_rights(session, pilot_desk_id, responsible):
        raise HTTPException(422, "Le desk cible et le responsable doivent être habilités dans l'organisation")
    if len(reason.strip()) < 3:
        raise HTTPException(422, "Le motif d'affectation est requis")
    shares = session.exec(select(RfqDeskShare).where(
        RfqDeskShare.rfq_id == rfq_id, RfqDeskShare.active == True,  # noqa: E712
    )).all()
    shared_ids = {share.desk_id for share in shares}
    retained = set(retained_share_desk_ids)
    if shared_ids != set(expected_share_desk_ids) or not retained <= shared_ids - {pilot_desk_id}:
        raise HTTPException(409, "Les partages ont changé ; rechargez leur liste avant le transfert")
    before = {"pilot_desk_id": scope.pilot_desk_id, "responsible_user_id": scope.responsible_user_id,
              "share_desk_ids": sorted(shared_ids)}
    result = session.execute(update(RfqOwnership).where(
        RfqOwnership.rfq_id == rfq_id,
        RfqOwnership.pilot_desk_id == expected_pilot_desk_id,
        RfqOwnership.responsible_user_id == expected_responsible_user_id,
    ).values(pilot_desk_id=pilot_desk_id, responsible_user_id=responsible_user_id)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "L'affectation a changé ; rechargez le dossier")
    for share in shares:
        if share.desk_id not in retained:
            share.active = False
            share.updated_at = datetime.utcnow()
            session.add(share)
    after = {"pilot_desk_id": pilot_desk_id, "responsible_user_id": responsible_user_id,
             "share_desk_ids": sorted(retained)}
    record_audit_event(session, action="RFQ_ASSIGNMENT_CHANGED", object_type="RFQ",
                       object_id=rfq_id, actor_user_id=user.id, result="SUCCESS",
                       before=before, after=after, reason=reason.strip())
    session.commit()
    session.expire_all()
    return after
