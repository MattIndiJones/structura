"""Organization pairing administration and authenticated installation endpoint."""
import json
import secrets
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..db.database import get_session
from ..db.models import Counterparty, RfqChannel, RfqRelationship, RfqRelationshipSide, User
from ..services import rfq_transport as transport, rfq_relationships as relationships
from .auth import get_current_admin, get_current_user

router = APIRouter(prefix="/api/rfq-transport", tags=["rfq"])
Admin = Annotated[User, Depends(get_current_admin)]
Database = Annotated[Session, Depends(get_session)]


@router.post("/messages/{message_id}/retry")
def retry(message_id: str, current: Annotated[User, Depends(get_current_user)], session: Database):
    from datetime import datetime
    from ..db.models import RfqRemoteLink, RfqTransportOutbox, RfqSolicitation, RfqExchangeRound
    from ..services.rfq_access import require_rfq_access
    from ..services.rfq_bank import require_action
    row = session.get(RfqTransportOutbox, message_id)
    if not row:
        raise HTTPException(404, "Message RFQ introuvable")
    item = session.get(RfqSolicitation, row.solicitation_id)
    link = session.get(RfqRemoteLink, item.id)
    if link.inbound:
        require_action(session, item.id, current, "read" if row.kind == "READ" else "publish_quote", lock=True)
    else:
        require_rfq_access(session, session.get(RfqExchangeRound, item.round_id).rfq_id, current, "solicit")
    if row.state not in {"DELIVERED", "CANCELLED"}:
        row.next_attempt_at = datetime.utcnow()
        session.add(row)
        record_audit_event(session, result="SUCCESS", action="RFQ_MESSAGE_RETRY_REQUESTED", object_type="RFQ_SOLICITATION",
            object_id=item.id, actor_user_id=current.id, correlation_id=row.id)
        session.commit()
    return transport.transport_row(session, row.id)


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationship_id: int
    expected_version: int = Field(ge=1)
    role: Literal["REQUESTER", "BANK"]
    peer_installation_id: UUID
    peer_url: str = Field(max_length=500)
    channel_id: UUID | None = None
    secret: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    peer_counterparty_id: int
    reason: str = Field(min_length=3, max_length=500)


class ChannelState(BaseModel):
    active: bool
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


def row(channel):
    return {"id": channel.id, "relationship_id": channel.relationship_id,
        "relationship_version": channel.relationship_version, "role": channel.role,
        "peer_installation_id": channel.peer_installation_id, "peer_url": channel.peer_url,
        "agreement_hash": channel.agreement_hash, "active": channel.active,
        "confirmed_at": transport.exchange.iso(channel.confirmed_at)}


def owned(session, channel_id, admin):
    entity_id = relationships.organization_admin(admin)
    channel = session.get(RfqChannel, channel_id)
    if not channel or channel.entity_id != entity_id:
        raise HTTPException(404, "Canal RFQ introuvable")
    return channel


@router.get("/channels")
def channels(admin: Admin, session: Database):
    entity_id = relationships.organization_admin(admin)
    installation_id = transport.identity(session)
    session.commit()
    return {"installation_id": installation_id, "channels": [row(c) for c in session.exec(
        select(RfqChannel).where(RfqChannel.entity_id == entity_id)).all()]}


@router.post("/channels")
def configure(body: ChannelCreate, admin: Admin, session: Database):
    entity_id = relationships.organization_admin(admin)
    relation = relationships.require_relation(session, body.relationship_id, entity_id)
    if relation.version != body.expected_version or entity_id != (
            relation.requester_entity_id if body.role == "REQUESTER" else relation.partner_entity_id):
        raise HTTPException(409, "Direction ou version de relation incorrecte")
    if transport.channel_for_relation(session, relation.id):
        raise HTTPException(409, "Cette relation possède déjà un canal ; utilisez sa suspension ou sa reconnaissance")
    local_id = transport.identity(session)
    if str(body.peer_installation_id) == local_id:
        raise HTTPException(422, "Choisissez une autre installation")
    if body.role == "BANK" and (not body.channel_id or not body.secret):
        raise HTTPException(422, "Importez l'identifiant de canal et la clé communiqués par le demandeur")
    channel = RfqChannel(id=str(body.channel_id or uuid4()), relationship_id=relation.id,
        relationship_version=relation.version, entity_id=entity_id, role=body.role,
        peer_installation_id=str(body.peer_installation_id), peer_url=transport.endpoint(body.peer_url),
        secret=body.secret or secrets.token_hex(32), agreement_hash=transport.agreement(session, relation), configured_by=admin.id)
    cp = session.get(Counterparty, body.peer_counterparty_id)
    if not cp or not cp.active:
        raise HTTPException(422, "Rapprochement juridique local de votre organisation requis")
    peer_entity = relation.partner_entity_id if body.role == "REQUESTER" else relation.requester_entity_id
    peer_side = session.get(RfqRelationshipSide, (relation.id, peer_entity))
    peer_side.counterparty_id = cp.id
    session.add(peer_side)
    transport.channel_current(session, channel, confirmed=False)
    session.add(channel)
    record_audit_event(session, result="SUCCESS", action="RFQ_CHANNEL_CONFIGURED", object_type="RFQ_RELATIONSHIP",
        object_id=relation.id, actor_user_id=admin.id, reason=body.reason, correlation_id=channel.id,
        after={"peer_installation_id": channel.peer_installation_id, "agreement_hash": channel.agreement_hash})
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Identifiant de canal ou relation déjà appairé")
    # Key shown once, to the administrator creating/importing this pairing only.
    return {**row(channel), "pairing": {"channel_id": channel.id, "secret": channel.secret,
        "installation_id": local_id, "agreement_hash": channel.agreement_hash}}


@router.put("/channels/{channel_id}")
def state(channel_id: str, body: ChannelState, admin: Admin, session: Database):
    channel = owned(session, channel_id, admin)
    relation = session.get(RfqRelationship, channel.relationship_id)
    if relation.version != body.expected_version:
        raise HTTPException(409, "La relation a changé")
    channel.active = body.active
    if channel.relationship_version != relation.version or channel.agreement_hash != transport.agreement(session, relation):
        channel.relationship_version = relation.version
        channel.agreement_hash = transport.agreement(session, relation)
        channel.confirmed_at = None
    session.add(channel)
    record_audit_event(session, result="SUCCESS", action="RFQ_CHANNEL_STATE_CHANGED", object_type="RFQ_RELATIONSHIP",
        object_id=relation.id, actor_user_id=admin.id, reason=body.reason, correlation_id=channel.id,
        after={"active": channel.active, "agreement_hash": channel.agreement_hash})
    session.commit()
    return row(channel)


@router.post("/channels/{channel_id}/probe")
def probe(channel_id: str, admin: Admin, session: Database):
    channel = owned(session, channel_id, admin)
    try:
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            transport.probe(session, channel, client)
    except httpx.HTTPError:
        raise HTTPException(409, "Reconnaissance distante indisponible ou refusée ; vérifiez le canal sur les deux installations")
    return row(channel)


@router.post("/receive")
async def receive(request: Request, session: Database):
    # Check streamed size before parsing; no public identity or key discovery endpoint.
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2_000_000:
            raise HTTPException(413, "Message RFQ trop volumineux")
        chunks.append(chunk)
    try:
        packet = json.loads(b"".join(chunks))
        if not isinstance(packet, dict) or set(packet) != {"body", "signature"}:
            raise ValueError("envelope")
        return transport.receive(session, packet)
    except (ValueError, KeyError, TypeError, AttributeError):
        session.rollback()
        raise HTTPException(422, "Format du message RFQ invalide")
