"""Atomic local delivery of immutable Product projections, with no pricing side effects."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..db.models import Deal, RfqExchangeRound, RfqRoundLink, RfqSolicitation, RfqSendCommand
from ..runtime import business_now
from .rfq_access import membership_rights


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def iso(value):
    return value.isoformat() + "Z" if value else None


def round_for(session: Session, rfq_id: int):
    return session.exec(select(RfqExchangeRound).where(RfqExchangeRound.rfq_id == rfq_id)).first()


def identity(session: Session, rfq) -> dict:
    existing = round_for(session, rfq.id)
    link = session.get(RfqRoundLink, rfq.id)
    previous = session.get(RfqExchangeRound, link.previous_round_id) if link else None
    return {"exchange_reference": existing.exchange_reference if existing else (
                previous.exchange_reference if previous else f"RFQX-{rfq.entity_id}-{rfq.reference}"),
            "round_number": existing.number if existing else (previous.number + 1 if previous else 1),
            "previous_round_id": existing.previous_round_id if existing else (previous.id if previous else None)}


def freeze(session: Session, rfq, request: dict, actor) -> RfqExchangeRound:
    existing = round_for(session, rfq.id)
    if existing:
        if existing.state != "OPEN":
            raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié")
        return existing
    round_identity = identity(session, rfq)
    previous = session.get(RfqExchangeRound, round_identity["previous_round_id"]) if round_identity["previous_round_id"] else None
    if previous:
        if previous.state != "OPEN":
            raise HTTPException(409, "Le tour précédent est déjà clôturé")
        if session.exec(select(Deal).where(Deal.rfq_id == previous.rfq_id)).first():
            raise HTTPException(409, "Le tour précédent a été booké")
        previous.state = "SUPERSEDED"
        session.add(previous)
        record_audit_event(session, result="SUCCESS", action="RFQ_ROUND_SUPERSEDED", object_type="RFQ_ROUND",
                           object_id=previous.id, actor_user_id=actor.id, after={"state": previous.state})
    row = RfqExchangeRound(rfq_id=rfq.id, exchange_reference=round_identity["exchange_reference"],
        number=round_identity["round_number"], previous_round_id=round_identity["previous_round_id"],
        product_id=rfq.product_id, terms_version=request["terms_version"],
        terms_fingerprint=request["terms_fingerprint"], request_json=json.dumps(request, ensure_ascii=False),
        frozen_by=actor.id, frozen_at=business_now())
    session.add(row)
    session.flush()
    record_audit_event(session, result="SUCCESS", action="RFQ_ROUND_FROZEN", object_type="RFQ_ROUND", object_id=row.id,
        actor_user_id=actor.id, after={**round_identity, "rfq_id": rfq.id,
            "product_id": rfq.product_id, "terms_fingerprint": row.terms_fingerprint})
    return row


def delivery_row(row: RfqSolicitation, round_row: RfqExchangeRound, session=None) -> dict:
    request = json.loads(row.request_json)
    result = {"id": row.id, "message_id": row.message_id, "round_id": row.round_id,
        "exchange_reference": request["exchange_reference"], "round_number": round_row.number,
        "recipient": request["recipient"], "delivery_status": "READ" if row.read_at else "DELIVERED",
        "business_status": "AWAITING_RESPONSE" if round_row.state == "OPEN" else "ROUND_CLOSED",
        "sent_at": iso(row.sent_at), "delivered_at": iso(row.delivered_at), "read_at": iso(row.read_at)}
    if session:
        from . import rfq_transport as transport
        link = transport.link_for(session, row.id)
        if link:
            result["transport"] = transport.transport_row(session, row.message_id) if not link.inbound else None
            result["installation_delivery"] = "REMOTE"
            if not link.inbound:
                receipt = result["transport"]
                result["delivered_at"] = receipt["received_at"] if receipt and receipt["state"] == "DELIVERED" else None
                result["delivery_status"] = "READ" if row.read_at else (receipt["state"] if receipt else "PENDING")
    return result


def tracking(session: Session, rfq_id: int) -> dict:
    row = round_for(session, rfq_id)
    link = session.get(RfqRoundLink, rfq_id)
    if not row:
        return {"round": None, "deliveries": [], "previous_round_id": link.previous_round_id if link else None}
    deliveries = session.exec(select(RfqSolicitation).where(RfqSolicitation.round_id == row.id)
        .order_by(RfqSolicitation.id)).all()
    from ..db.models import RfqRequest
    rfq = session.get(RfqRequest, rfq_id)
    effective_state = "CLOSED" if row.state == "OPEN" and rfq.status in {"clos", "sans_suite"} else row.state
    return {"round": {"id": row.id, "exchange_reference": row.exchange_reference, "number": row.number,
        "previous_round_id": row.previous_round_id, "state": effective_state, "frozen_at": iso(row.frozen_at),
        "product_id": row.product_id, "terms_version": row.terms_version,
        "terms_fingerprint": row.terms_fingerprint, "request": json.loads(row.request_json)},
        "deliveries": [delivery_with_responses(session, item, row) for item in deliveries]}


def delivery_with_responses(session, item, row):
    from ..db.models import RfqQuotePublication
    from .rfq_publication import public_row
    publications = session.exec(select(RfqQuotePublication).where(
        RfqQuotePublication.solicitation_id == item.id).order_by(RfqQuotePublication.revision.desc())).all()
    result = delivery_row(item, row, session)
    result["responses"] = [public_row(session, reply) for reply in publications]
    if publications and row.state == "OPEN":
        result["business_status"] = "QUOTE_RECEIVED"
    from ..db.models import RfqRequest
    if session.get(RfqRequest, row.rfq_id).status in {"clos", "sans_suite"}:
        result["business_status"] = "ROUND_CLOSED"
    return result


def replay(session: Session, rfq_id: int, key: str, payload_hash: str):
    command = session.exec(select(RfqSendCommand).where(RfqSendCommand.rfq_id == rfq_id,
        RfqSendCommand.command_key == key)).first()
    if command:
        if command.payload_hash != payload_hash:
            raise HTTPException(409, "Cette clé d’envoi a déjà servi pour un autre contenu")
        return json.loads(command.result_json)
    return None


def deliver(session: Session, rfq, packet: dict, actor, key: str, payload_hash: str) -> dict:
    if packet["issues"]:
        raise HTTPException(422, {"message": "La demande est incomplète", "failures": packet["issues"]})
    network = [item for item in packet["messages"] if item["recipient_type"] == "NETWORK"]
    if not network:
        raise HTTPException(422, "Choisissez au moins un partenaire réseau")
    row = freeze(session, rfq, packet["request"], actor)
    existing = session.exec(select(RfqSolicitation).where(RfqSolicitation.round_id == row.id)).all()
    # Identity is the organization, not its local supplier label or relationship reference.
    if {item.recipient_entity_id for item in existing} & {item["request"]["recipient"]["organization_id"] for item in network}:
        raise HTTPException(409, "Une organisation sélectionnée a déjà reçu ce tour")
    now = business_now()
    sent = []
    for message in network:
        recipient = message["request"]["recipient"]
        message_id = str(uuid4())
        request = {**message["request"], "message_id": message_id, "message_type": "RFQ_REQUEST",
                   "published_at": iso(now)}
        item = RfqSolicitation(round_id=row.id, relationship_id=message["recipient_id"],
            recipient_entity_id=recipient["organization_id"], recipient_desk_id=recipient["desk_id"],
            message_id=message_id, request_json=json.dumps(request, ensure_ascii=False),
            sent_by=actor.id, sent_at=now, delivered_at=now)
        session.add(item)
        session.flush()
        from . import rfq_transport as transport
        channel = transport.channel_for_relation(session, item.relationship_id)
        if channel:
            transport.channel_current(session, channel)
            if channel.role != "REQUESTER":
                raise HTTPException(409, "Le canal doit appartenir à l'organisation demandeuse")
            from ..db.models import RfqRemoteLink
            session.add(RfqRemoteLink(solicitation_id=item.id, channel_id=channel.id,
                request_message_id=message_id, inbound=False))
            session.flush()
            transport.queue(session, item, "REQUEST", transport.shared_request(request), actor.id, message_id=message_id)
        sent.append(item.id)
        record_audit_event(session, result="SUCCESS", action="RFQ_REQUEST_QUEUED" if channel else "RFQ_REQUEST_DELIVERED", object_type="RFQ_SOLICITATION",
            object_id=item.id, actor_user_id=actor.id, correlation_id=message_id,
            after={"round_id": row.id, "recipient_entity_id": item.recipient_entity_id,
                   "recipient_desk_id": item.recipient_desk_id, "delivery_status": "PENDING" if channel else "DELIVERED"})
    result = {"round_id": row.id, "solicitation_ids": sent}
    session.add(RfqSendCommand(rfq_id=rfq.id, command_key=key, payload_hash=payload_hash,
                              result_json=json.dumps(result)))
    return result


def can_receive(session: Session, item: RfqSolicitation, user) -> bool:
    from .rfq_transport import link_for
    link = link_for(session, item.id)
    if link and not link.inbound:
        return False
    return user.entity_id == item.recipient_entity_id and "read" in membership_rights(session, item.recipient_desk_id, user)


def require_received(session: Session, item_id: int, user) -> RfqSolicitation:
    item = session.get(RfqSolicitation, item_id)
    if not item or not can_receive(session, item, user):
        raise HTTPException(404, "Demande reçue introuvable")
    return item
