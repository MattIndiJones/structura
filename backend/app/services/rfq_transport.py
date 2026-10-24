"""Authenticated bilateral RFQ transport with transactional outbox and receipts.

HMAC keys belong to one explicitly paired channel. HTTPS supplies confidentiality;
no JWT, private calculation or local database key is part of the protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.product.models import ProductTerms, TradeIntent
from ..core.references import next_audited_id
from ..db.models import (Entity, RfqBankCase, RfqBankPublicationPolicy, RfqBankQuoteDraft,
    RfqChannel, RfqDesk, RfqExchangeRound, RfqInstallation, RfqQuote, RfqQuotePublication,
    RfqRelationship, RfqRelationshipSide, RfqRemoteLink, RfqRequest, RfqSolicitation,
    RfqTransportAttempt, RfqTransportInbox, RfqTransportOutbox, User)
from ..runtime import business_now
from . import rfq_exchange as exchange, rfq_relationships as relationships

PROTOCOL = "STRUCTURA_RFQ_1"
KINDS = {"REQUEST", "QUOTE", "WITHDRAW", "READ", "CLOSE", "EXECUTION_REQUEST", "EXECUTION_CONFIRMATION", "EXECUTION_STATUS"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(session):
    row = session.get(RfqInstallation, 1)
    if not row:
        from ..runtime import consultation_mode
        if consultation_mode():
            raise HTTPException(409, "Identité de transport non initialisée dans cette consultation")
        row = RfqInstallation(installation_id=str(uuid4()))
        session.add(row)
        session.flush()
    return row.installation_id


def endpoint(value):
    try:
        url = urlsplit(value)
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("port")
    except ValueError:
        raise HTTPException(422, "Adresse d'installation ou port invalide") from None
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = False
    if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"} or not url.hostname:
        raise HTTPException(422, "Adresse d'installation invalide : origine HTTPS seule requise")
    if url.scheme != "https" and not (url.scheme == "http" and loopback
            and os.getenv("STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP") == "1"):
        raise HTTPException(422, "HTTPS requis ; HTTP local est réservé à la recette explicitement activée")
    return value.rstrip("/")


def agreement(session, relation):
    # Public commercial addresses and perimeter, never local IDs or booking data.
    return exchange.digest({"terms": json.loads(relation.terms_json),
        "requester": session.get(Entity, relation.requester_entity_id).name,
        "bank": session.get(Entity, relation.partner_entity_id).name,
        "desk": session.get(RfqDesk, relation.receiver_desk_id).name})


def channel_current(session, channel, *, confirmed=True, protective=False):
    relation = session.get(RfqRelationship, channel.relationship_id)
    if protective and channel.active and relation:
        return relation
    if not channel.active or not relation or relation.version != channel.relationship_version \
            or agreement(session, relation) != channel.agreement_hash:
        raise HTTPException(409, "Canal suspendu ou accord modifié : reconfigurez la reconnaissance du canal")
    own = session.get(RfqRelationshipSide, (relation.id, channel.entity_id))
    if not own or own.suspended or own.recognized_version != relation.version:
        raise HTTPException(409, "Votre organisation doit reconnaître l'accord courant")
    if confirmed and not channel.confirmed_at:
        raise HTTPException(409, "Appairage distant en attente")
    return relation


def signature(channel, value):
    return hmac.new(bytes.fromhex(channel.secret), canonical(value).encode(), hashlib.sha256).hexdigest()


def envelope(session, channel, operation, message):
    body = {"protocol": PROTOCOL, "channel_id": channel.id, "sender": identity(session),
        "receiver": channel.peer_installation_id, "issued_at": exchange.iso(datetime.utcnow()),
        "operation": operation, "message": message}
    return {"body": body, "signature": signature(channel, body)}


def verify(session, packet):
    body = packet.get("body", {})
    channel = session.get(RfqChannel, body.get("channel_id"))
    if not channel or not channel.active or not hmac.compare_digest(
            str(packet.get("signature", "")), signature(channel, body)):
        raise HTTPException(401, "Authentification du canal RFQ refusée")
    if set(body) != {"protocol", "channel_id", "sender", "receiver", "issued_at", "operation", "message"} \
            or body["protocol"] != PROTOCOL or body["sender"] != channel.peer_installation_id \
            or body["receiver"] != identity(session):
        raise HTTPException(401, "Installation ou protocole RFQ incorrect")
    from .rfq_publication import utc
    try:
        age = abs((datetime.utcnow() - utc(body["issued_at"])).total_seconds())
    except (ValueError, TypeError):
        raise HTTPException(401, "Horodatage du transport invalide")
    if age > 300:
        raise HTTPException(401, "Enveloppe de transport expirée")
    return channel, body


def confirm(session, channel, expected_hash):
    session.execute(update(RfqChannel).where(RfqChannel.id == channel.id).values(active=RfqChannel.active))
    session.expire_all()
    relation = channel_current(session, channel, confirmed=False)
    if expected_hash != channel.agreement_hash:
        raise HTTPException(409, "L'accord a changé pendant sa reconnaissance distante")
    peer_entity = relation.partner_entity_id if channel.role == "REQUESTER" else relation.requester_entity_id
    side = session.get(RfqRelationshipSide, (relation.id, peer_entity))
    if not side or side.suspended:
        raise HTTPException(409, "Reconnaissance distante suspendue localement")
    if channel.confirmed_at and side.recognized_version == relation.version:
        return
    side.recognized_version = relation.version
    channel.confirmed_at = business_now()
    session.add(side); session.add(channel)
    record_audit_event(session, result="SUCCESS", action="RFQ_CHANNEL_CONFIRMED", object_type="RFQ_RELATIONSHIP",
        object_id=relation.id, actor_user_id=None, correlation_id=channel.id, after={"peer_installation_id": channel.peer_installation_id,
            "agreement_hash": channel.agreement_hash, "version": relation.version})


def channel_for_relation(session, relation_id):
    return session.exec(select(RfqChannel).where(RfqChannel.relationship_id == relation_id)).first()


def link_for(session, item_id):
    return session.get(RfqRemoteLink, item_id)


def queue(session, item, kind, payload, actor_id, *, message_id=None):
    link = link_for(session, item.id)
    if not link:
        return None
    last = session.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.channel_id == link.channel_id,
        RfqTransportOutbox.request_message_id == link.request_message_id)
        .order_by(RfqTransportOutbox.sequence.desc())).first()
    row = RfqTransportOutbox(id=message_id or str(uuid4()), channel_id=link.channel_id,
        solicitation_id=item.id, request_message_id=link.request_message_id,
        sequence=last.sequence + 1 if last else 1, kind=kind, payload_json=canonical(payload),
        payload_hash=exchange.digest(payload), actor_user_id=actor_id, next_attempt_at=datetime.utcnow())
    session.add(row); session.flush()
    record_audit_event(session, result="SUCCESS", action="RFQ_MESSAGE_QUEUED", object_type="RFQ_SOLICITATION",
        object_id=item.id, actor_user_id=actor_id, correlation_id=row.id,
        after={"kind": kind, "sequence": row.sequence, "payload_hash": row.payload_hash})
    return row


def wire_message(row):
    return {"id": row.id, "request_id": row.request_message_id, "sequence": row.sequence,
        "kind": row.kind, "payload": json.loads(row.payload_json), "payload_hash": row.payload_hash}


def shared_request(request):
    """Strip local directory keys; the paired channel is the only routing address."""
    return {key: value for key, value in request.items() if key not in {"previous_round_id", "requester", "recipient"}} | {
        "requester": {key: value for key, value in request["requester"].items() if key not in {"organization_id", "desk_id"}},
        "recipient": {key: value for key, value in request["recipient"].items()
            if key not in {"organization_id", "desk_id", "relationship_id", "relationship_version", "relationship_reference"}}}


def transport_row(session, message_id):
    row = session.get(RfqTransportOutbox, message_id)
    if not row:
        return None
    attempts = session.exec(select(RfqTransportAttempt).where(RfqTransportAttempt.message_id == row.id)
        .order_by(RfqTransportAttempt.id.desc()).limit(10)).all()
    return {"message_id": row.id, "kind": row.kind, "sequence": row.sequence, "state": row.state,
        "attempts": row.attempts, "received_at": exchange.iso(row.received_at),
        "next_attempt_at": exchange.iso(row.next_attempt_at) if row.state not in {"DELIVERED", "CANCELLED"} else None,
        "last_error": row.last_error, "history": [{"at": exchange.iso(a.attempted_at),
            "outcome": a.outcome, "detail": a.detail} for a in attempts]}


def remote_source(session):
    row = session.exec(select(User).where(User.username == "__rfq_transport__")).first()
    if not row:
        from ..db.database import _hash_pw
        row = User(username="__rfq_transport__", email=f"{identity(session)}@transport.invalid",
            password_hash=_hash_pw(secrets.token_hex(32)), is_active=False)
        session.add(row); session.flush()
    if row.is_active or row.role != "user" or row.entity_id is not None:
        raise HTTPException(409, "Le compte de projection technique doit rester désactivé et sans organisation")
    return row


def receive_request(session, channel, message):
    if channel.role != "BANK" or message["id"] != message["request_id"]:
        raise HTTPException(422, "Direction de demande invalide")
    request = message["payload"]
    allowed = {"format_version", "exchange_reference", "round_number", "product_reference", "product_model", "rfq_reference",
        "title", "kind", "requester", "recipient", "side", "nominal", "currency", "requested_metric", "price_unit",
        "price_convention", "response_deadline", "transaction_format", "instrument_family", "payoff_family",
        "documentation_reference", "terms_version", "terms_fingerprint", "terms", "message_id", "message_type", "published_at"}
    if set(request) != allowed or request["message_id"] != message["id"] or request["message_type"] != "RFQ_REQUEST" \
            or request["requested_metric"] != "PRICE" or len(request["title"]) > 200:
        raise HTTPException(422, "Projection partagée de la demande invalide")
    terms = ProductTerms.model_validate(request["terms"])
    terms.require_complete()
    if request["format_version"] != 1 or request["product_model"]["payscript_semantics_version"] != 1 \
            or request["terms_fingerprint"] != terms.fingerprint or request["currency"] != terms.settlement_ccy \
            or request["side"] not in {"BUY", "SELL"} or request["kind"] not in {"indicatif", "to_trade"} \
            or request["price_unit"] != "PERCENT_OF_NOTIONAL" or request["price_convention"] != "ALL_IN" \
            or type(request["terms_version"]) is not int or type(request["round_number"]) is not int \
            or request["terms_version"] < 1 or request["round_number"] < 1:
        raise HTTPException(422, "Termes ou conventions de la demande incohérents")
    relation = channel_current(session, channel)
    if request["requester"]["organization"] != session.get(Entity, relation.requester_entity_id).name \
            or request["recipient"] != {"organization": session.get(Entity, relation.partner_entity_id).name,
                "desk": session.get(RfqDesk, relation.receiver_desk_id).name}:
        raise HTTPException(422, "Les adresses commerciales ne correspondent pas au canal reconnu")
    from .product_repository import stage_internal_product
    actor = remote_source(session)
    product = stage_internal_product(session, user=actor, name=request["title"], terms=terms,
        intent=TradeIntent(nominal=request["nominal"], side=request["side"]),
        data_origin="imported", reason="Projection contractuelle reçue par canal authentifié.")
    rfq = RfqRequest(id=next_audited_id(session, RfqRequest, "RFQ"),
        reference=f"IN-{message['id']}", entity_id=relation.requester_entity_id, user_id=actor.id,
        product_id=product.product_id, product_terms_version=product.terms_version,
        name=request["title"], kind=request["kind"], sens="achat" if request["side"] == "BUY" else "vente",
        transaction_format=request["transaction_format"], instrument_family=request["instrument_family"],
        payoff_family=request["payoff_family"], documentation_reference=request.get("documentation_reference"),
        script_snapshot=terms.script, params_json=canonical({"notional": request["nominal"], "currency": request["currency"]}))
    failures = relationships.eligibility(session, relation, rfq, currency=request["currency"], nominal=request["nominal"])
    if failures:
        raise HTTPException(409, "Demande hors accord reconnu : " + "; ".join(failures))
    session.add(rfq); session.flush()
    local_request = {**request, "requester": {**request["requester"], "organization_id": relation.requester_entity_id},
        "recipient": {**request["recipient"], "organization_id": relation.partner_entity_id,
            "desk_id": relation.receiver_desk_id, "relationship_id": relation.id, "relationship_version": relation.version}}
    round_row = RfqExchangeRound(rfq_id=rfq.id, product_id=product.product_id,
        exchange_reference=f"{channel.id}:{request['exchange_reference']}", number=request["round_number"],
        terms_version=request["terms_version"], terms_fingerprint=terms.fingerprint,
        request_json=canonical(local_request), frozen_by=actor.id)
    # A new round closes older received rounds even when the close message travels later.
    for previous in session.exec(select(RfqExchangeRound).where(
            RfqExchangeRound.exchange_reference == round_row.exchange_reference)).all():
        if previous.number >= round_row.number:
            raise HTTPException(409, "Tour ancien ou déjà reçu sous une autre identité de message")
        if previous.state == 'OPEN':
            previous.state = "SUPERSEDED"
            session.add(previous)
        if round_row.previous_round_id is None or previous.number > session.get(
                RfqExchangeRound, round_row.previous_round_id).number:
            round_row.previous_round_id = previous.id
    session.add(round_row); session.flush()
    from .rfq_publication import utc
    if utc(request["response_deadline"]) <= business_now():
        round_row.state = "CLOSED"; session.add(round_row)
    item = RfqSolicitation(round_id=round_row.id, relationship_id=relation.id,
        recipient_entity_id=relation.partner_entity_id, recipient_desk_id=relation.receiver_desk_id,
        message_id=message["id"], request_json=canonical(local_request), sent_by=actor.id,
        sent_at=utc(request["published_at"]), delivered_at=business_now())
    session.add(item); session.flush()
    session.add(RfqRemoteLink(solicitation_id=item.id, channel_id=channel.id,
        request_message_id=message["id"], inbound=True))
    return item


def receive_event(session, channel, message):
    link = session.exec(select(RfqRemoteLink).where(RfqRemoteLink.channel_id == channel.id,
        RfqRemoteLink.request_message_id == message["request_id"])).first()
    if not link:
        raise HTTPException(409, "La demande d'origine n'a pas été reçue")
    item = session.get(RfqSolicitation, link.solicitation_id)
    row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, row.rfq_id)
    payload, kind = message["payload"], message["kind"]
    if kind == 'EXECUTION_STATUS':
        from .rfq_reconciliation import receive as receive_statement
        receive_statement(session, item, message)
        return item
    if kind in {'EXECUTION_REQUEST', 'EXECUTION_CONFIRMATION'}:
        from . import rfq_electronic
        if kind == 'EXECUTION_REQUEST' and link.inbound:
            rfq_electronic.receive_request(session, item, message)
        elif kind == 'EXECUTION_CONFIRMATION' and not link.inbound:
            rfq_electronic.receive_decision(session, item, message)
        else:
            raise HTTPException(422, 'Direction du message d’exécution invalide')
        return item
    if kind == "CLOSE" and link.inbound:
        if payload.get("state") not in {"CLOSED", "SUPERSEDED"}:
            raise HTTPException(422, "Clôture invalide")
        row.state = payload["state"]; session.add(row)
        return item
    if kind == "READ" and not link.inbound:
        from .rfq_publication import utc
        if not item.read_at:
            item.read_at = utc(payload["read_at"]); session.add(item)
        return item
    if link.inbound or kind not in {"QUOTE", "WITHDRAW"}:
        raise HTTPException(422, "Direction du message métier invalide")
    from . import rfq_publication as publication
    if kind == "WITHDRAW":
        quote_row = session.exec(select(RfqQuotePublication).where(
            RfqQuotePublication.solicitation_id == item.id, RfqQuotePublication.message_id == payload["publication_message_id"])).first()
        if not quote_row:
            raise HTTPException(409, "Cotation introuvable")
        if not quote_row.withdrawn_at:
            reason = payload["reason"].strip()
            if not 3 <= len(reason) <= 500:
                raise HTTPException(422, "Motif de retrait requis")
            quote_row.withdrawn_at = publication.utc(payload["withdrawn_at"])
            quote_row.withdrawal_reason = reason
            session.add(quote_row)
            quote = session.get(RfqQuote, quote_row.quote_id)
            if quote_row.acceptance_received_at:
                from .rfq_execution import flag_external_conflict
                flag_external_conflict(session, quote.id, message['id'],
                    'Retrait bancaire après confirmation externe : ordre contesté, revue requise avant inscription locale.')
            else:
                quote.status = "expire"
                session.add(quote)
            if rfq.selected_quote_id == quote.id and not quote_row.acceptance_received_at:
                from .rfq_quote_integrity import clear_selection
                clear_selection(rfq)
    else:
        request = json.loads(item.request_json)
        allowed = {"format_version", "nature", "exchange_reference", "round_number", "terms_version", "terms_fingerprint",
            "requester", "organization", "desk", "price", "price_unit", "price_convention", "nominal", "currency", "side",
            "firmness", "valid_until", "conditions_type", "conditions", "counterparty_name", "issuer_name", "guarantor_name",
            "documentation_reference", "comment", "response_reference", "revision", "message_id", "message_type", "published_at", "publisher"}
        if set(payload) != allowed or payload["message_type"] != "RFQ_QUOTE" \
                or payload["organization"] != request["recipient"]["organization"] \
                or payload["desk"] != request["recipient"]["desk"] or payload["requester"] != request["requester"]["organization"]:
            raise HTTPException(422, "Projection commerciale de réponse invalide")
        matching = ("exchange_reference", "round_number", "terms_version", "terms_fingerprint", "currency",
            "nominal", "side", "price_unit", "price_convention")
        if any(payload.get(key) != request.get(key) for key in matching) or payload.get("nature") != "COMPLIANT" \
                or payload.get("message_id") != message["id"] or payload.get("format_version") != 1:
            raise HTTPException(422, "La réponse ne porte pas sur la demande figée")
        # Reuse the commercial schema; never accept a remote private calculation reference.
        publication.DraftPut(expected_revision=0, calculation_id=1, **{key: payload[key] for key in (
            "price", "firmness", "valid_until", "conditions_type", "conditions", "issuer_name", "guarantor_name",
            "documentation_reference", "comment")})
        older = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == item.id)
            .order_by(RfqQuotePublication.revision.desc())).first()
        if type(payload["price"]) not in {int, float} or type(payload["revision"]) is not int or payload["revision"] < 1 or (older and (
                payload["revision"] <= older.revision or payload["response_reference"] != json.loads(older.payload_json)["response_reference"])):
            raise HTTPException(409, "Révision de cotation incohérente ou déjà réservée")
        if publication.utc(payload["published_at"]) > publication.utc(request["response_deadline"]):
            raise HTTPException(422, "Publication après le délai de réponse")
        from .legal_identity import relation_counterparty
        legal = relation_counterparty(session, rfq, item)
        quote = RfqQuote(id=next_audited_id(session, RfqQuote, "RFQ_QUOTE"), rfq_id=rfq.id,
            revision=payload['revision'],
            counterparty_id=legal.id, counterparty_name=legal.name, identity_frozen=True,
            provider=request["recipient"]["organization"], contact=payload["publisher"]["email"], price=payload["price"],
            currency=payload["currency"], status="recu", firmness=payload["firmness"],
            valid_until=publication.utc(payload["valid_until"]), quoted_at=publication.utc(payload["published_at"]))
        from .rfq_model_reference import snapshot
        quote.model_reference_json = snapshot(session, rfq)
        session.add(quote); session.flush()
        session.add(RfqQuotePublication(solicitation_id=item.id, revision=payload["revision"], quote_id=quote.id,
            message_id=message["id"], payload_json=canonical(payload), published_by=remote_source(session).id,
            published_at=publication.utc(payload["published_at"]), delivered_at=business_now()))
        if older:
            old = session.get(RfqQuote, older.quote_id)
            if older.acceptance_received_at:
                from .rfq_execution import flag_external_conflict
                flag_external_conflict(session, old.id, message['id'],
                    'Révision bancaire après confirmation externe : accord conservé, revue requise avant inscription locale.')
                quote.status = 'expire'
                session.add(quote)
            else:
                old.status = "expire"
                session.add(old)
            if rfq.selected_quote_id == old.id and not older.acceptance_received_at:
                from .rfq_quote_integrity import clear_selection
                clear_selection(rfq)
    session.flush()
    from .rfq_state import _sync_status, _sync_product_rfq
    _sync_status(rfq, session)
    _sync_product_rfq(session, rfq, remote_source(session), action="PRODUCT_RFQ_REMOTE_RESPONSE_RECEIVED")
    return item


def receive(session, packet):
    channel, body = verify(session, packet)
    message, operation = body["message"], body["operation"]
    if operation == "HELLO":
        channel_current(session, channel, confirmed=False)
        if message != {"agreement_hash": channel.agreement_hash, "role": "BANK" if channel.role == "REQUESTER" else "REQUESTER"}:
            raise HTTPException(409, "Les accords des deux installations ne correspondent pas")
        confirm(session, channel, message["agreement_hash"])
        receipt = {"agreement_hash": channel.agreement_hash, "role": channel.role}
    elif operation == "STATUS":
        stored = session.get(RfqTransportInbox, message.get("id"))
        if stored and (stored.channel_id != channel.id or stored.payload_hash != message.get("payload_hash")):
            raise HTTPException(409, "Identité de message réutilisée avec un autre contenu")
        receipt = json.loads(stored.receipt_json) if stored else {"found": False, "message_id": message.get("id"),
            "payload_hash": message.get("payload_hash")}
    elif operation in {"DELIVER", "HISTORY", "CANCEL"}:
        if set(message) != {"id", "request_id", "sequence", "kind", "payload", "payload_hash"} \
                or message["kind"] not in KINDS or (operation != "CANCEL" and message["payload_hash"] != exchange.digest(message["payload"])) \
                or (operation == "CANCEL" and message["payload"] is not None):
            raise HTTPException(422, "Message RFQ invalide")
        allowed = {"REQUEST", "CLOSE", "EXECUTION_REQUEST", "EXECUTION_STATUS"} if channel.role == "BANK" else {"READ", "QUOTE", "WITHDRAW", "EXECUTION_CONFIRMATION", "EXECUTION_STATUS"}
        if message["kind"] not in allowed or (message["kind"] == "REQUEST" and message["id"] != message["request_id"]):
            raise HTTPException(422, "Direction du canal RFQ invalide")
        UUID(message["id"]); UUID(message["request_id"])
        # Serialize all receipts on this channel before checking duplicates/sequence.
        session.execute(update(RfqChannel).where(RfqChannel.id == channel.id).values(active=RfqChannel.active))
        session.expire_all()
        if not channel.active:
            raise HTTPException(401, "Canal RFQ désactivé pendant la réception")
        stored = session.get(RfqTransportInbox, message["id"])
        if stored:
            if stored.channel_id != channel.id or stored.payload_json != canonical(message):
                raise HTTPException(409, "Identité de message réutilisée avec un autre contenu")
            receipt = json.loads(stored.receipt_json)
        else:
            channel_current(session, channel, protective=operation == "CANCEL" or message["kind"] in {"CLOSE", "WITHDRAW", "EXECUTION_CONFIRMATION", "EXECUTION_REQUEST", "EXECUTION_STATUS"})
            last = session.exec(select(RfqTransportInbox).where(RfqTransportInbox.channel_id == channel.id,
                RfqTransportInbox.request_message_id == message["request_id"])
                .order_by(RfqTransportInbox.sequence.desc())).first()
            if type(message["sequence"]) is not int or message["sequence"] != (last.sequence + 1 if last else 1):
                raise HTTPException(409, "Séquence RFQ incomplète : livraison précédente requise")
            if operation == "HISTORY" and message["kind"] != "QUOTE":
                raise HTTPException(422, "Seule une cotation peut être reçue comme historique")
            if operation == 'CANCEL' and message['kind'] in {'EXECUTION_REQUEST', 'EXECUTION_CONFIRMATION', 'EXECUTION_STATUS'}:
                raise HTTPException(422, 'Une exécution électronique ne s’annule pas par un accusé de transport.')
            item = None if operation == "CANCEL" else (receive_request(session, channel, message)
                if message["kind"] == "REQUEST" else receive_event(session, channel, message))
            receipt = {"found": True, "message_id": message["id"], "payload_hash": message["payload_hash"],
                "sequence": message["sequence"], "received_at": exchange.iso(business_now()),
                "result": "CANCELLED" if operation == "CANCEL" else "HISTORY" if operation == "HISTORY" else "RECORDED"}
            session.add(RfqTransportInbox(id=message["id"], channel_id=channel.id, request_message_id=message["request_id"],
                sequence=message["sequence"], payload_hash=message["payload_hash"], payload_json=canonical(message),
                receipt_json=canonical(receipt), received_at=business_now()))
            if message['kind'] in {'EXECUTION_REQUEST', 'EXECUTION_CONFIRMATION', 'EXECUTION_STATUS'}:
                from ..db.models import RfqElectronicEvidence
                # Persist the inbox parent before its evidence FK, within this same transaction.
                session.flush()
                session.add(RfqElectronicEvidence(message_id=message['id'], envelope_json=canonical(packet),
                    received_at=business_now()))
            record_audit_event(session, result="SUCCESS", action="RFQ_REMOTE_MESSAGE_RECEIVED", object_type="RFQ_SOLICITATION",
                object_id=item.id if item else None, actor_user_id=None, correlation_id=message["id"],
                after={"kind": message["kind"], "payload_hash": message["payload_hash"], "result": receipt["result"]})
    else:
        raise HTTPException(422, "Opération de transport inconnue")
    signed = envelope(session, channel, "RECEIPT", receipt)
    session.commit()
    return signed


def call_peer(session, channel, operation, message, client):
    packet = envelope(session, channel, operation, message)
    response = client.post(endpoint(channel.peer_url) + "/api/rfq-transport/receive", json=packet)
    response.raise_for_status()
    signed = response.json()
    paired, body = verify(session, signed)
    if paired.id != channel.id or body["operation"] != "RECEIPT":
        raise HTTPException(401, "Accusé RFQ invalide")
    session.info["rfq_signed_receipt"] = signed
    return body["message"]


def probe(session, channel, client):
    channel_current(session, channel, confirmed=False)
    expected_hash = channel.agreement_hash
    receipt = call_peer(session, channel, "HELLO", {"agreement_hash": expected_hash, "role": channel.role}, client)
    if receipt != {"agreement_hash": expected_hash, "role": "BANK" if channel.role == "REQUESTER" else "REQUESTER"}:
        raise HTTPException(401, "Reconnaissance distante incorrecte")
    confirm(session, channel, expected_hash); session.commit()


def retry_checks(session, row):
    from .rfq_access import require_rfq_access, membership_rights
    from . import rfq_bank, rfq_publication
    channel = session.get(RfqChannel, row.channel_id)
    item = session.get(RfqSolicitation, row.solicitation_id)
    round_row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, round_row.rfq_id)
    actor = session.get(User, row.actor_user_id)
    payload = json.loads(row.payload_json)
    from .rfq_publication import utc
    retired_request = row.kind == "REQUEST" and (round_row.state != "OPEN" or rfq.status in {"clos", "sans_suite"}
        or utc(payload["response_deadline"]) <= business_now())
    retired = False
    if row.kind == "QUOTE":
        published = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.message_id == row.id)).first()
        later = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == item.id,
            RfqQuotePublication.revision > payload["revision"])).first()
        retired = bool((published and published.withdrawn_at) or later or round_row.state != "OPEN")
    relation = channel_current(session, channel, protective=row.kind in {"CLOSE", "WITHDRAW", "READ", "EXECUTION_CONFIRMATION", "EXECUTION_STATUS"} or retired or retired_request)
    if retired or retired_request:
        return "CANCEL"
    if row.kind == "WITHDRAW":
        original = session.get(RfqTransportOutbox, payload["publication_message_id"])
        if original and original.state == "CANCELLED":
            return "CANCEL"
    if row.kind in {"REQUEST", "QUOTE"} and relation.version != json.loads(item.request_json)["recipient"]["relationship_version"]:
        raise HTTPException(409, "L'accord du tour a changé ; ouvrez un nouveau tour")
    if row.kind == "REQUEST":
        require_rfq_access(session, rfq.id, actor, "solicit")
        rfq_bank.require_open(session, item)
        if round_row.terms_fingerprint != payload["terms_fingerprint"]:
            raise HTTPException(409, "Les termes figés ne correspondent plus")
        failures = relationships.eligibility(session, relation, rfq, currency=payload["currency"], nominal=payload["nominal"])
        if failures:
            raise HTTPException(409, "; ".join(failures))
    elif row.kind == 'EXECUTION_REQUEST':
        from ..core.access import require_booking_permission
        require_booking_permission(actor)
        require_rfq_access(session, rfq.id, actor, 'book')
    elif row.kind == "QUOTE":
        rfq_bank.require_action(session, item.id, actor, "publish_quote")
        draft = session.get(RfqBankQuoteDraft, item.id)
        if not draft or draft.revision != payload["revision"]:
            return "HISTORY"
        policy = session.get(RfqBankPublicationPolicy, item.recipient_desk_id)
        try:
            rfq_publication.commercial_checks(session, item, session.get(RfqBankCase, item.id), draft, policy)
        except HTTPException:
            return "HISTORY"
        validator = session.get(User, draft.validated_by) if draft.validated_by else None
        if draft.validated_hash != draft.payload_hash or draft.validated_policy_version != policy.version or not validator \
                or "validate_quote" not in membership_rights(session, item.recipient_desk_id, validator):
            return "HISTORY"
    elif row.kind == "READ":
        try:
            rfq_bank.require_action(session, item.id, actor, "read")
        except HTTPException:
            return "CANCEL"
    # Withdrawal and closure are protective facts; an expired quote/deadline must not prevent their delivery.
    return "DELIVER"


def reconcile_closures(session):
    already_queued = select(RfqTransportOutbox.id).where(
        RfqTransportOutbox.solicitation_id == RfqRemoteLink.solicitation_id, RfqTransportOutbox.kind == "CLOSE").exists()
    candidates = session.exec(select(RfqRemoteLink).join(RfqSolicitation,
        RfqSolicitation.id == RfqRemoteLink.solicitation_id).join(RfqExchangeRound,
        RfqExchangeRound.id == RfqSolicitation.round_id).join(RfqRequest,
        RfqRequest.id == RfqExchangeRound.rfq_id).where(RfqRemoteLink.inbound == False,
        (RfqExchangeRound.state != "OPEN") | RfqRequest.status.in_(["clos", "sans_suite"]),
        ~already_queued).limit(100)).all()
    for link in candidates:
        session.execute(update(RfqSolicitation).where(RfqSolicitation.id == link.solicitation_id)
            .values(message_id=RfqSolicitation.message_id))
        session.expire_all()
        item = session.get(RfqSolicitation, link.solicitation_id)
        round_row = session.get(RfqExchangeRound, item.round_id)
        rfq = session.get(RfqRequest, round_row.rfq_id)
        if round_row.state == "OPEN" and rfq.status not in {"clos", "sans_suite"}:
            continue
        if round_row.state == 'OPEN':
            round_row.state = 'CLOSED'
            session.add(round_row)
        prior = session.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.solicitation_id == item.id,
            RfqTransportOutbox.kind == "CLOSE")).first()
        if not prior:
            queue(session, item, "CLOSE", {"state": "SUPERSEDED" if round_row.state == "SUPERSEDED" else "CLOSED"}, item.sent_by)
    session.commit()


def deliver_one(engine, message_id, client=None):
    """Short DB transactions around I/O; a durable lease fences concurrent workers."""
    now, token = datetime.utcnow(), str(uuid4())
    with Session(engine) as session:
        result = session.execute(update(RfqTransportOutbox).where(RfqTransportOutbox.id == message_id,
            RfqTransportOutbox.state.notin_(["DELIVERED", "CANCELLED"]), RfqTransportOutbox.next_attempt_at <= now,
            (RfqTransportOutbox.lease_until.is_(None)) | (RfqTransportOutbox.lease_until < now))
            .values(lease_token=token, lease_until=now+timedelta(seconds=45)))
        if result.rowcount != 1:
            session.rollback(); return
        row = session.get(RfqTransportOutbox, message_id)
        earlier = session.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.channel_id == row.channel_id,
            RfqTransportOutbox.request_message_id == row.request_message_id, RfqTransportOutbox.sequence < row.sequence,
            RfqTransportOutbox.state.notin_(["DELIVERED", "CANCELLED"]))).first()
        if earlier:
            session.rollback(); return
        row.attempts += 1; session.add(row); session.commit()
    own_client = client is None
    client = client or httpx.Client(timeout=10, trust_env=False, follow_redirects=False)
    receipt, signed_receipt, state, error = None, None, "RETRY", None
    try:
        with Session(engine) as session:
            row = session.get(RfqTransportOutbox, message_id)
            channel = session.get(RfqChannel, row.channel_id)
            if row.attempts > 1:
                receipt = call_peer(session, channel, "STATUS", {"id": row.id, "payload_hash": row.payload_hash}, client)
            if not receipt or not receipt.get("found"):
                operation = retry_checks(session, row)
                if row.kind == "CLOSE":
                    root = session.get(RfqTransportOutbox, row.request_message_id)
                    if root and root.state == "CANCELLED":
                        operation = "CANCEL"
                message = wire_message(row)
                if operation == "CANCEL":
                    message["payload"] = None
                receipt = call_peer(session, channel, operation, message, client)
            if not receipt.get("found") or receipt.get("message_id") != row.id or receipt.get("payload_hash") != row.payload_hash \
                    or receipt.get("sequence") != row.sequence or receipt.get("result") not in {"RECORDED", "HISTORY", "CANCELLED"}:
                raise HTTPException(401, "Accusé non lié au contenu envoyé")
            from .rfq_publication import utc
            utc(receipt["received_at"])
            signed_receipt = session.info["rfq_signed_receipt"]
            state = "CANCELLED" if receipt["result"] == "CANCELLED" else "DELIVERED"
    except HTTPException as exc:
        state = "BLOCKED"
        error = "Authentification ou signature d'accusé refusée" if exc.status_code == 401 else (
            str(exc.detail)[:250] if isinstance(exc.detail, str) else "Droits, accord, termes ou validité à vérifier avant reprise")
    except httpx.HTTPStatusError as exc:
        state = "BLOCKED" if exc.response.status_code in {401, 403, 409, 422} else "RETRY"
        error = f"Installation distante : HTTP {exc.response.status_code}"
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        error = "Installation indisponible ou accusé invalide ; réception non confirmée"
    finally:
        if own_client:
            client.close()
    with Session(engine) as session:
        row = session.get(RfqTransportOutbox, message_id)
        if row.lease_token != token:
            return
        row.state, row.last_error = state, error
        row.lease_until = row.lease_token = None
        row.next_attempt_at = datetime.utcnow()+timedelta(seconds=min(300, 5 * 2**min(row.attempts-1, 6)))
        if state in {"DELIVERED", "CANCELLED"}:
            from .rfq_publication import utc
            row.received_at = utc(receipt["received_at"])
            row.receipt_json = canonical(receipt)
            row.signed_receipt_json = canonical(signed_receipt)
        session.add(row)
        session.add(RfqTransportAttempt(message_id=row.id, outcome=state, detail=error))
        session.commit()


def process_pending(engine, should_stop=lambda: False):
    with Session(engine) as session:
        reconcile_closures(session)
        ids = session.exec(select(RfqTransportOutbox.id).where(RfqTransportOutbox.state.in_(["PENDING", "RETRY", "BLOCKED"]),
            RfqTransportOutbox.next_attempt_at <= datetime.utcnow()).order_by(RfqTransportOutbox.created_at).limit(20)).all()
    for message_id in ids:
        if should_stop():
            break
        deliver_one(engine, message_id)
