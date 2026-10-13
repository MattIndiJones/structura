"""Organization administration of explicit bilateral RFQ relationships."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import AuditEvent, Counterparty, Entity, RfqDesk, RfqRelationship, User
from ..db.trading_models import TradingRelationship
from ..services import rfq_relationships as service
from .auth import get_current_admin

router = APIRouter(prefix="/api/rfq-relations", tags=["rfq"])
Admin = Annotated[User, Depends(get_current_admin)]
Database = Annotated[Session, Depends(get_session)]


@router.get("/catalog")
def relation_catalog(admin: Admin, session: Database):
    entity_id = service.organization_admin(admin)
    organizations = session.exec(select(Entity).order_by(Entity.name)).all()
    desks = session.exec(select(RfqDesk).where(RfqDesk.active == True).order_by(RfqDesk.name)).all()  # noqa: E712
    counterparties = session.exec(select(Counterparty).where(Counterparty.active == True).order_by(Counterparty.name)).all()  # noqa: E712
    trading = session.exec(select(TradingRelationship).where(TradingRelationship.entity_id == entity_id)).all()
    return {"entity_id": entity_id, "organization_name": session.get(Entity, entity_id).name,
            "organizations": [{"id": e.id, "name": e.name} for e in organizations],
            "desks": [{"id": d.id, "entity_id": d.entity_id, "name": d.name} for d in desks],
            "counterparties": [{"id": c.id, "name": c.name} for c in counterparties],
            "trading_relationships": [{"id": r.id, "reference": r.reference, "counterparty_id": r.counterparty_id,
                                       "status": json.loads(r.terms_json).get("status")} for r in trading]}


@router.get("")
def list_relations(admin: Admin, session: Database):
    entity_id = service.organization_admin(admin)
    rows = session.exec(select(RfqRelationship).where(
        (RfqRelationship.requester_entity_id == entity_id) | (RfqRelationship.partner_entity_id == entity_id)
    ).order_by(RfqRelationship.updated_at.desc())).all()
    return [service.row_for(session, row, entity_id) for row in rows]


@router.get("/{relation_id}")
def get_relation(relation_id: int, admin: Admin, session: Database):
    entity_id = service.organization_admin(admin)
    return service.row_for(session, service.require_relation(session, relation_id, entity_id), entity_id)


@router.post("", status_code=201)
def create_relation(body: service.RelationshipCreate, admin: Admin, session: Database):
    return service.create_relation(session, admin, body)


@router.put("/{relation_id}")
def update_relation(relation_id: int, body: service.RelationshipUpdate, admin: Admin, session: Database):
    return service.update_relation(session, relation_id, admin, body)


@router.post("/{relation_id}/recognize")
def recognize_relation(relation_id: int, body: service.RelationshipDecision, admin: Admin, session: Database):
    return service.recognize_relation(session, relation_id, admin, body)


@router.post("/{relation_id}/suspension")
def suspend_relation(relation_id: int, body: service.RelationshipSuspension, admin: Admin, session: Database):
    return service.suspend_relation(session, relation_id, admin, body)


@router.get("/{relation_id}/history")
def relation_history(relation_id: int, admin: Admin, session: Database,
                     before_id: int | None = None, limit: int = Query(default=100, ge=1, le=200)):
    entity_id = service.organization_admin(admin)
    service.require_relation(session, relation_id, entity_id)
    query = select(AuditEvent).where(AuditEvent.object_type == "RFQ_RELATIONSHIP", AuditEvent.object_id == relation_id)
    if before_id is not None:
        query = query.where(AuditEvent.id < before_id)
    rows = session.exec(query.order_by(AuditEvent.id.desc()).limit(limit + 1)).all()
    entries = rows[:limit]
    return {"entries": [{"id": event.id, "action": event.action, "reason": event.reason,
                         "at": event.created_at.isoformat() + "Z", "after": json.loads(event.after_json),
                         "actor": session.get(User, event.actor_user_id).username if event.actor_user_id else None}
                        for event in entries],
            "next_before_id": entries[-1].id if len(rows) > limit else None}
