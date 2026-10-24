"""Read and explicitly acknowledge requests addressed to the user's bank desk."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..db.database import get_session
from ..db.models import RfqSolicitation, RfqExchangeRound, User
from ..runtime import business_now
from ..services import rfq_exchange as exchange, rfq_bank as bank, rfq_publication as publication
from ..services import rfq_electronic
from .auth import get_current_user

router = APIRouter(prefix="/api/rfq-inbox", tags=["rfq"])


@router.get("")
def list_received(current: Annotated[User, Depends(get_current_user)],
                  session: Annotated[Session, Depends(get_session)], before_id: int | None = None):
    # Permission filtering before pagination keeps inaccessible desk rows private.
    rows = session.exec(select(RfqSolicitation).where(
        RfqSolicitation.recipient_entity_id == current.entity_id).order_by(RfqSolicitation.id.desc())).all()
    output = []
    for item in rows:
        if (before_id is None or item.id < before_id) and exchange.can_receive(session, item, current):
            row = session.get(RfqExchangeRound, item.round_id)
            request = json.loads(item.request_json)
            electronic = rfq_electronic.workspace(session,item.id)
            reconciliation = electronic.get('reconciliation') if electronic else None
            output.append({**exchange.delivery_row(item, row, session), "title": request["title"],
                "requester": request["requester"], "nominal": request["nominal"], "currency": request["currency"],
                "reconciliation_state": reconciliation['state'] if reconciliation else None,
                "response_deadline": request["response_deadline"], **bank.work_row(session, item, current)})
            if len(output) == 100:
                break
    return output


@router.get("/{item_id}")
def received_request(item_id: int, current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    item = exchange.require_received(session, item_id, current)
    row = session.get(RfqExchangeRound, item.round_id)
    return {**exchange.delivery_row(item, row, session), "request": json.loads(item.request_json),
            **bank.work_row(session, item, current), **publication.workspace(session, item, current),
            'electronic_execution': rfq_electronic.workspace(session, item.id)}


@router.post('/{item_id}/electronic-execution/{execution_id}/decision')
def decide_electronic_execution(item_id: int, execution_id: str, body: rfq_electronic.BankDecision,
                               current: Annotated[User, Depends(get_current_user)],
                               session: Annotated[Session, Depends(get_session)]):
    rfq_electronic.decide(session, item_id, execution_id, current, body)
    return received_request(item_id, current, session)


@router.put("/{item_id}/publication-policy")
def set_publication_policy(item_id: int, body: publication.PolicyPut, current: Annotated[User, Depends(get_current_user)],
                            session: Annotated[Session, Depends(get_session)]):
    publication.put_policy(session, item_id, current, body)
    return received_request(item_id, current, session)


@router.put("/{item_id}/quote-draft")
def prepare_quote(item_id: int, body: publication.DraftPut, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    publication.save_draft(session, item_id, current, body)
    return received_request(item_id, current, session)


@router.post("/{item_id}/validate")
def validate_quote(item_id: int, body: publication.Decision, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    publication.validate(session, item_id, current, body)
    return received_request(item_id, current, session)


@router.post("/{item_id}/publish")
def publish_quote(item_id: int, body: publication.Decision, current: Annotated[User, Depends(get_current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    publication.publish(session, item_id, current, body)
    return received_request(item_id, current, session)


class Withdrawal(BaseModel):
    publication_id: int
    reason: str = Field(min_length=3, max_length=500)


@router.post("/{item_id}/withdraw")
def withdraw_quote(item_id: int, body: Withdrawal, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    publication.withdraw(session, item_id, body.publication_id, current, body.reason)
    return received_request(item_id, current, session)


class BankAssignment(BaseModel):
    responsible_user_id: int
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/{item_id}/claim")
def claim_request(item_id: int, current: Annotated[User, Depends(get_current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    bank.claim(session, item_id, current)
    return received_request(item_id, current, session)


@router.put("/{item_id}/assignment")
def assign_request(item_id: int, body: BankAssignment, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    bank.assign(session, item_id, current, body.responsible_user_id, body.expected_revision, body.reason.strip())
    return received_request(item_id, current, session)


@router.get("/{item_id}/members")
def pricing_members(item_id: int, current: Annotated[User, Depends(get_current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    item = bank.require_action(session, item_id, current)
    users = session.exec(select(User).where(User.entity_id == current.entity_id, User.is_active == True)).all()
    return [{"id": user.id, "name": user.username} for user in users
            if {"read", "prepare", "price"} <= bank.membership_rights(session, item.recipient_desk_id, user)]


@router.post("/{item_id}/read")
def acknowledge_read(item_id: int, current: Annotated[User, Depends(get_current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    exchange.require_received(session, item_id, current)
    result = session.execute(update(RfqSolicitation).where(RfqSolicitation.id == item_id,
        RfqSolicitation.read_at.is_(None)).values(read_at=business_now(), read_by=current.id)
        .execution_options(synchronize_session=False))
    session.expire_all()
    item = exchange.require_received(session, item_id, current)
    if result.rowcount:
        from ..services.rfq_transport import queue
        queue(session, item, "READ", {"read_at": exchange.iso(item.read_at)}, current.id)
        record_audit_event(session, result="SUCCESS", action="RFQ_REQUEST_READ", object_type="RFQ_SOLICITATION", object_id=item.id,
            actor_user_id=current.id, correlation_id=item.message_id, after={"read_at": exchange.iso(item.read_at)})
    session.commit()
    return received_request(item_id, current, session)
