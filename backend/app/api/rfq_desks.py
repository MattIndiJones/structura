"""Explicit RFQ desk admission and membership management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..db.database import get_session
from ..db.models import Entity, RfqDesk, RfqDeskMembership, User
from ..services.rfq_access import RIGHTS, membership_rights
from .auth import get_current_admin, get_current_user

router = APIRouter(prefix="/api/rfq-desks", tags=["rfq"])


class DeskCreate(BaseModel):
    entity_id: int
    name: str = Field(min_length=1, max_length=100)


class MembershipPut(BaseModel):
    user_id: int
    rights: list[str] = Field(min_length=1)
    expires_at: datetime | None = None
    active: bool = True


def _desk_row(desk: RfqDesk) -> dict:
    return {"id": desk.id, "entity_id": desk.entity_id,
            "name": desk.name, "active": desk.active}


def _require_admin_scope(admin: User, entity_id: int) -> None:
    # A system administrator may set up an organization but gains no RFQ read
    # access. An organization administrator is confined to its own entity.
    if admin.entity_id is not None and admin.entity_id != entity_id:
        raise HTTPException(404, "Organisation introuvable")


def _utc_naive(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


@router.get("")
def my_desks(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if current.entity_id is None:
        return []
    desks = session.exec(select(RfqDesk).where(
        RfqDesk.entity_id == current.entity_id, RfqDesk.active == True,  # noqa: E712
    ).order_by(RfqDesk.name)).all()
    return [{**_desk_row(desk), "rights": sorted(membership_rights(session, desk.id, current))}
            for desk in desks if membership_rights(session, desk.id, current)]


@router.get("/organization")
def organization_desks(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if current.entity_id is None:
        return []
    return [_desk_row(desk) for desk in session.exec(select(RfqDesk).where(
        RfqDesk.entity_id == current.entity_id, RfqDesk.active == True,  # noqa: E712
    ).order_by(RfqDesk.name)).all()]


@router.get("/{desk_id}/members")
def desk_members(
    desk_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    desk = session.get(RfqDesk, desk_id)
    if not desk or desk.entity_id != current.entity_id:
        raise HTTPException(404, "Desk introuvable")
    own_desks = session.exec(select(RfqDesk).where(
        RfqDesk.entity_id == current.entity_id)).all()
    if not any("organize" in membership_rights(session, d.id, current) for d in own_desks):
        raise HTTPException(403, "L'organisation des dossiers exige une habilitation de desk")
    members = session.exec(select(User).join(
        RfqDeskMembership, RfqDeskMembership.user_id == User.id).where(
            RfqDeskMembership.desk_id == desk_id)).all()
    return [{"id": u.id, "username": u.username} for u in members
            if "read" in membership_rights(session, desk_id, u)]


@router.get("/admin")
def admin_desks(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    query = select(RfqDesk).order_by(RfqDesk.entity_id, RfqDesk.name)
    if admin.entity_id is not None:
        query = query.where(RfqDesk.entity_id == admin.entity_id)
    desks = session.exec(query).all()
    memberships = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id.in_([desk.id for desk in desks])
    )).all() if desks else []
    return [{**_desk_row(desk), "members": [
        {"user_id": m.user_id, "rights": json.loads(m.rights_json),
         "active": m.active, "expires_at": m.expires_at.isoformat() if m.expires_at else None}
        for m in memberships if m.desk_id == desk.id
    ]} for desk in desks]


@router.post("/admin", status_code=201)
def create_desk(
    body: DeskCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    _require_admin_scope(admin, body.entity_id)
    if not session.get(Entity, body.entity_id):
        raise HTTPException(404, "Organisation introuvable")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Le nom du desk est requis")
    existing = session.exec(select(RfqDesk).where(
        RfqDesk.entity_id == body.entity_id, RfqDesk.name == name)).first()
    if existing:
        raise HTTPException(409, "Ce desk existe déjà dans l'organisation")
    desk = RfqDesk(entity_id=body.entity_id, name=name)
    session.add(desk)
    session.flush()
    record_audit_event(session, action="RFQ_DESK_CREATED", object_type="RFQ_DESK",
                       object_id=desk.id, actor_user_id=admin.id, result="SUCCESS",
                       after=_desk_row(desk))
    session.commit()
    return _desk_row(desk)


@router.put("/admin/{desk_id}/members/{user_id}")
def put_membership(
    desk_id: int,
    user_id: int,
    body: MembershipPut,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    desk = session.get(RfqDesk, desk_id)
    if not desk:
        raise HTTPException(404, "Desk introuvable")
    _require_admin_scope(admin, desk.entity_id)
    user = session.get(User, user_id)
    if not user or user.entity_id != desk.entity_id or body.user_id != user_id:
        raise HTTPException(422, "Le collaborateur n'appartient pas à ce desk")
    if user_id == admin.id:
        raise HTTPException(403, "L'auto-attribution de droits RFQ est interdite")
    rights = set(body.rights)
    if not rights <= RIGHTS or "read" not in rights:
        raise HTTPException(422, "Droits RFQ invalides ou lecture manquante")
    expiry = _utc_naive(body.expires_at)
    if expiry and expiry <= datetime.utcnow():
        raise HTTPException(422, "L'échéance doit être future")
    member = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id == desk_id,
        RfqDeskMembership.user_id == user_id)).first()
    before = ({"rights": json.loads(member.rights_json), "active": member.active}
              if member else None)
    if member is None:
        member = RfqDeskMembership(desk_id=desk_id, user_id=user_id)
    member.rights_json = json.dumps(sorted(rights))
    member.active = body.active
    member.expires_at = expiry
    member.updated_at = datetime.utcnow()
    session.add(member)
    session.flush()
    after = {"desk_id": desk_id, "user_id": user_id, "rights": sorted(rights),
             "active": member.active, "expires_at": str(member.expires_at) if member.expires_at else None}
    record_audit_event(session, action="RFQ_MEMBERSHIP_SET", object_type="RFQ_DESK_MEMBERSHIP",
                       object_id=member.id, actor_user_id=admin.id, result="SUCCESS",
                       before=before, after=after)
    session.commit()
    return after
