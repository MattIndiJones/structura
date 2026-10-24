"""Explicit bank decisions on exact published quotes, durably delivered both ways."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, update
from sqlmodel import select

from ..core.access import require_booking_permission
from ..core.audit import record_audit_event
from ..db.models import (Counterparty, Deal, RfqBankCase, RfqElectronicBooking, RfqElectronicExecution,
    RfqExecutionAgreement, RfqExchangeRound, RfqQuote, RfqQuotePublication, RfqRelationship,
    RfqRelationshipSide, RfqRequest, RfqSolicitation)
from ..runtime import business_now, consultation_mode
from . import rfq_bank as bank, rfq_execution as execution, rfq_exchange as exchange
from . import rfq_publication as publication, rfq_transport as transport
from .product_repository import load_product


class ElectronicRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quote_id: int
    expected_terms_version: int = Field(gt=0)
    expected_terms_fingerprint: str = Field(min_length=64, max_length=64)
    command_key: str = Field(min_length=16, max_length=100)


class BankDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_request_hash: str = Field(min_length=64, max_length=64)
    decision: Literal['CONFIRMED', 'REJECTED']
    reason: str = Field(min_length=3, max_length=500)


class WireRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format_version: Literal[1]
    execution_id: UUID
    execution_reference: str = Field(min_length=3, max_length=100)
    quote: dict
    requested_at: datetime
    requester: dict[str, str]


class WireDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format_version: Literal[1]
    execution_id: UUID
    request_hash: str = Field(min_length=64, max_length=64)
    decision: Literal['CONFIRMED', 'REJECTED']
    received_at: datetime
    decided_at: datetime
    reason: str = Field(min_length=3, max_length=500)
    bank: dict[str, str]


def available(session):
    return not consultation_mode() or inspect(session.get_bind()).has_table('rfq_electronic_executions')


def for_item(session, item_id):
    if not available(session):
        return None
    return session.exec(select(RfqElectronicExecution).where(
        RfqElectronicExecution.solicitation_id == item_id)).first()


def public_row(session, entry):
    from .rfq_reconciliation import workspace as reconciliation_workspace
    payload = json.loads(entry.request_json)
    booked = session.get(RfqElectronicBooking, entry.id)
    deal = session.get(Deal, booked.deal_id) if booked else None
    return {'id': entry.id, 'state': entry.state, 'request_hash': entry.request_hash,
        'execution_reference': payload['execution_reference'], 'quote': payload['quote'],
        'requested_at': payload['requested_at'], 'received_at': exchange.iso(entry.received_at),
        'decision': json.loads(entry.decision_json) if entry.decision_json else None,
        'transport': transport.transport_row(session,
            entry.request_message_id if entry.role == 'REQUESTER' else entry.decision_message_id) if (
                entry.role == 'REQUESTER' or entry.decision_message_id) else None,
        'booked_deal': {'id': deal.id, 'reference': deal.reference} if deal else None,
        'reconciliation': reconciliation_workspace(session, entry)}


def workspace(session, item_id):
    entry = for_item(session, item_id)
    return public_row(session, entry) if entry else None


def requester_workspace(session, rfq_id):
    if not available(session):
        return None
    entry = session.exec(select(RfqElectronicExecution).join(RfqSolicitation,
        RfqSolicitation.id == RfqElectronicExecution.solicitation_id).join(RfqExchangeRound,
        RfqExchangeRound.id == RfqSolicitation.round_id).where(RfqExchangeRound.rfq_id == rfq_id,
            RfqElectronicExecution.role == 'REQUESTER')).first()
    return public_row(session, entry) if entry else None


def request(session, rfq_id, user, body):
    require_booking_permission(user)
    rfq = execution.lock_rfq_organization(session, rfq_id, user, 'book')
    session.execute(update(RfqRequest).where(RfqRequest.id == rfq.id).values(id=rfq.id))
    existing = requester_workspace(session, rfq_id)
    if existing:
        entry = session.get(RfqElectronicExecution, existing['id'])
        agreement = session.get(RfqExecutionAgreement, entry.agreement_id)
        frozen = json.loads(agreement.snapshot_json)
        if agreement.command_key == body.command_key and agreement.quote_id == body.quote_id \
                and frozen['terms_version'] == body.expected_terms_version \
                and frozen['terms_fingerprint'] == body.expected_terms_fingerprint:
            return existing
        raise HTTPException(409, 'Une intention électronique existe pour ce tour. Consultez-la ; après refus, ouvrez un nouveau tour.')
    published = publication.publication_for_quote(session, body.quote_id)
    item = session.get(RfqSolicitation, published.solicitation_id) if published else None
    link = transport.link_for(session, item.id) if item else None
    if not link or link.inbound or session.get(RfqExchangeRound, item.round_id).rfq_id != rfq_id:
        raise HTTPException(422, 'Une cotation réseau du canal demandeur est requise.')
    quote = json.loads(published.payload_json)
    if quote['firmness'] != 'FIRM' or quote['conditions_type'] != 'NONE':
        raise HTTPException(422, 'Une offre ferme sans condition supplémentaire est requise.')
    channel = transport.channel_for_relation(session, item.relationship_id)
    transport.channel_current(session, channel)
    identifier = str(uuid4())
    reference = 'EXE-' + identifier.upper()
    agreement = execution.request_treatment(session, rfq_id, user, execution.TreatmentRequest(
        **body.model_dump(), source='DOCUMENT', reference='Demande électronique ' + reference,
        bank_contact=quote['publisher']['email']), electronic=True)
    payload = {'format_version': 1, 'execution_id': identifier, 'execution_reference': reference,
        'quote': quote, 'requested_at': exchange.iso(business_now()),
        'requester': {'name': user.username, 'email': user.email}}
    pending = transport.queue(session, item, 'EXECUTION_REQUEST', payload, user.id)
    entry = RfqElectronicExecution(id=identifier, solicitation_id=item.id, product_id=rfq.product_id,
        agreement_id=agreement['id'], request_message_id=pending.id, request_json=transport.canonical(payload),
        request_hash=exchange.digest(payload), role='REQUESTER', state='PENDING', requested_by=user.id)
    session.add(entry)
    _audit(session, entry, user.id, 'RFQ_ELECTRONIC_EXECUTION_REQUESTED')
    session.commit()
    return public_row(session, entry)


def _bank_checks(session, item, payload, received_at):
    quote = payload['quote']
    published = session.exec(select(RfqQuotePublication).where(
        RfqQuotePublication.message_id == quote.get('message_id'), RfqQuotePublication.solicitation_id == item.id)).first()
    if not published or transport.canonical(json.loads(published.payload_json)) != transport.canonical(quote):
        raise HTTPException(409, 'La cotation exacte est inconnue ou modifiée.')
    if quote.get('firmness') != 'FIRM' or quote.get('conditions_type') != 'NONE':
        raise HTTPException(409, 'La cotation n’est pas ferme et sans condition.')
    # Validate against the receiving bank's clock; never backdate from the requester.
    if received_at >= publication.utc(quote['valid_until']) or received_at < publication.utc(quote['published_at']):
        raise HTTPException(409, 'La cotation n’était pas valable à sa réception bancaire.')
    if published.withdrawn_at or session.exec(select(RfqQuotePublication).where(
            RfqQuotePublication.solicitation_id == item.id, RfqQuotePublication.revision > published.revision)).first():
        raise HTTPException(409, 'La cotation a été retirée ou remplacée avant réception.')
    round_row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, round_row.rfq_id)
    if round_row.state != 'OPEN' or rfq.status in {'clos', 'sans_suite'}:
        raise HTTPException(409, 'Le tour a été clôturé avant réception.')
    case = session.get(RfqBankCase, item.id)
    if not case or case.state != 'IN_PROGRESS':
        raise HTTPException(409, 'La demande n’est pas prise en charge par la banque.')
    product = load_product(session, case.product_id)
    if product.terms_fingerprint != quote['terms_fingerprint'] or product.execution:
        raise HTTPException(409, 'Le Product bancaire ne porte pas les termes publiés.')
    relation = session.get(RfqRelationship, item.relationship_id)
    transport.channel_current(session, transport.channel_for_relation(session, relation.id))
    if relation.version != json.loads(item.request_json)['recipient']['relationship_version']:
        raise HTTPException(409, 'La relation du tour a changé.')
    failures = execution.relationships.eligibility(session, relation, rfq,
        currency=quote['currency'], nominal=quote['nominal'], purpose='treat')
    if failures:
        raise HTTPException(409, 'Traitement hors périmètre : ' + '; '.join(failures))
    return published, case


def receive_request(session, item, message):
    payload = message['payload']
    parsed = WireRequest.model_validate(payload)
    identifier = str(parsed.execution_id)
    if parsed.execution_reference != 'EXE-' + identifier.upper() or set(parsed.requester) != {'name', 'email'}:
        raise HTTPException(422, 'Référence électronique ou auteur invalide.')
    session.execute(update(RfqSolicitation).where(RfqSolicitation.id == item.id).values(message_id=item.message_id))
    session.expire_all()
    prior = for_item(session, item.id)
    if prior or session.get(RfqElectronicExecution, identifier):
        raise HTTPException(409, 'Une autre identité de message tente de répéter une intention existante.')
    case = session.get(RfqBankCase, item.id)
    now = business_now()
    entry = RfqElectronicExecution(id=identifier, solicitation_id=item.id,
        product_id=case.product_id if case else session.get(RfqExchangeRound, item.round_id).product_id,
        request_message_id=message['id'], request_json=transport.canonical(payload), request_hash=exchange.digest(payload),
        role='BANK', state='RECEIVED', requested_by=transport.remote_source(session).id, received_at=now)
    session.add(entry); session.flush()
    try:
        _bank_checks(session, item, payload, now)
    except HTTPException as exc:
        _decide(session, item, entry, 'REJECTED', str(exc.detail), transport.remote_source(session))
    _audit(session, entry, None, 'RFQ_ELECTRONIC_EXECUTION_RECEIVED')


def decide(session, item_id, identifier, user, body):
    require_booking_permission(user)
    item = bank.require_action(session, item_id, user, 'book', lock=True)
    entry = session.get(RfqElectronicExecution, identifier)
    if not entry or entry.solicitation_id != item_id or entry.role != 'BANK':
        raise HTTPException(404, 'Demande électronique introuvable.')
    if entry.request_hash != body.expected_request_hash:
        raise HTTPException(409, 'La demande affichée a changé.')
    reason = body.reason.strip()
    if len(reason) < 3:
        raise HTTPException(422, 'Motivez la décision bancaire.')
    if entry.decision_json:
        previous = json.loads(entry.decision_json)
        if previous['decision'] != body.decision or previous['reason'] != reason:
            raise HTTPException(409, 'Cette demande porte déjà une autre décision bancaire immuable.')
        return public_row(session, entry)
    if body.decision == 'CONFIRMED':
        _bank_checks(session, item, json.loads(entry.request_json), entry.received_at)
    _decide(session, item, entry, body.decision, reason, user)
    session.commit()
    return public_row(session, entry)


def _decide(session, item, entry, decision, reason, user):
    payload = {'format_version': 1, 'execution_id': entry.id, 'request_hash': entry.request_hash,
        'decision': decision, 'received_at': exchange.iso(entry.received_at), 'decided_at': exchange.iso(business_now()),
        'reason': reason, 'bank': {'name': user.username, 'email': user.email}}
    pending = transport.queue(session, item, 'EXECUTION_CONFIRMATION', payload, user.id)
    entry.state, entry.decision_json = decision, transport.canonical(payload)
    entry.decision_message_id, entry.decided_by = pending.id, user.id
    session.add(entry)
    if decision == 'CONFIRMED':
        quote = json.loads(entry.request_json)['quote']
        published = session.exec(select(RfqQuotePublication).where(
            RfqQuotePublication.message_id == quote['message_id'])).one()
        published.acceptance_received_at = entry.received_at
        session.add(published)
    _audit(session, entry, user.id, 'RFQ_ELECTRONIC_EXECUTION_' + decision)


def receive_decision(session, item, message):
    payload = message['payload']
    parsed = WireDecision.model_validate(payload)
    entry = session.get(RfqElectronicExecution, str(parsed.execution_id))
    if not entry or entry.role != 'REQUESTER' or entry.solicitation_id != item.id \
            or entry.request_hash != parsed.request_hash or set(parsed.bank) != {'name', 'email'}:
        raise HTTPException(409, 'La confirmation ne correspond pas à cette intention électronique.')
    if entry.decision_json:
        raise HTTPException(409, 'Une autre identité de message tente de remplacer la décision.')
    received, decided = publication.utc(parsed.received_at), publication.utc(parsed.decided_at)
    quote = json.loads(entry.request_json)['quote']
    if not received <= decided <= business_now():
        raise HTTPException(422, 'Chronologie de confirmation électronique invalide.')
    if parsed.decision == 'CONFIRMED' and not publication.utc(quote['published_at']) <= received < publication.utc(quote['valid_until']):
        raise HTTPException(422, 'L’acceptation a été reçue après expiration de la cotation.')
    agreement = session.get(RfqExecutionAgreement, entry.agreement_id)
    if agreement.state != 'REQUESTED' or agreement.request_source != 'ELECTRONIC_REQUEST':
        raise HTTPException(409, 'La demande locale ne permet pas cette confirmation électronique.')
    entry.state, entry.received_at = parsed.decision, received
    entry.decision_json, entry.decision_message_id = transport.canonical(payload), message['id']
    session.add(entry)
    if parsed.decision == 'CONFIRMED':
        agreement.state = 'CONFIRMED'
        agreement.execution_reference = json.loads(entry.request_json)['execution_reference']
        agreement.acceptance_received_at, agreement.confirmed_at = received, decided
        agreement.acceptance_evidence = 'Réception bancaire électronique ' + entry.request_message_id
        agreement.confirmation_source = 'ELECTRONIC_CONFIRMATION'
        agreement.confirmation_evidence = 'Décision signée ' + message['id'] + ' — ' + parsed.reason
        agreement.confirmation_hash = exchange.digest(payload)
        agreement.bank_contact = parsed.bank['email']
        agreement.written_confirmation_pending = False
        published = publication.publication_for_quote(session, agreement.quote_id)
        published.acceptance_received_at = received
        session.add(published)
    else:
        agreement.state, agreement.cancellation_reason = 'CANCELLED', 'Refus bancaire électronique : ' + parsed.reason
    session.add(agreement)
    _audit(session, entry, None, 'RFQ_ELECTRONIC_DECISION_RECEIVED')
    rfq = session.get(RfqRequest, agreement.rfq_id)
    from .rfq_state import _sync_product_rfq
    _sync_product_rfq(session, rfq, transport.remote_source(session), action='PRODUCT_RFQ_ELECTRONIC_DECISION_RECEIVED')
    from .rfq_reconciliation import stage_current
    stage_current(session, entry, transport.remote_source(session).id)


def protect_publication(session, item_id):
    entry = for_item(session, item_id)
    if entry and entry.state in {'RECEIVED', 'CONFIRMED'}:
        raise HTTPException(409, 'Une demande électronique reçue protège cette cotation. Décidez-la avant toute nouvelle opération.')


def _bank_entry(session, product_id):
    if not available(session):
        return None
    return session.exec(select(RfqElectronicExecution).where(
        RfqElectronicExecution.product_id == product_id, RfqElectronicExecution.role == 'BANK')).first()


def bank_booking_context(session, body, user):
    entry = _bank_entry(session, body.product_id)
    if not entry:
        return None, None
    bank.require_action(session, entry.solicitation_id, user, 'book', lock=True)
    session.refresh(entry)
    if entry.state != 'CONFIRMED':
        raise HTTPException(409, 'La décision électronique bancaire doit être confirmée avant booking.')
    booked = session.get(RfqElectronicBooking, entry.id)
    if booked:
        if booked.request_hash != execution.booking_request_hash(body):
            raise HTTPException(409, 'Cette exécution électronique est déjà bookée avec un autre contenu.')
        return entry, session.get(Deal, booked.deal_id)
    quote = json.loads(entry.request_json)['quote']
    item = session.get(RfqSolicitation, entry.solicitation_id)
    side = session.get(RfqRelationshipSide, (item.relationship_id, user.entity_id))
    legal = session.get(Counterparty, side.counterparty_id) if side else None
    product = load_product(session, body.product_id)
    expected = {'price_traded': quote['price'], 'nominal': quote['nominal'], 'devise': quote['currency'],
        'sens': 'achat' if quote['side'] == 'BUY' else 'vente', 'counterparty_id': legal.id if legal else None,
        'product_terms_version': product.terms_version}
    if not legal or not legal.active or any(getattr(body, key) != value for key, value in expected.items()) \
            or product.terms_fingerprint != quote['terms_fingerprint']:
        raise HTTPException(409, 'Le booking bancaire diffère de l’accord électronique : prix, nominal, sens, parties ou termes.')
    return entry, None


def attach_booking(session, body, deal, user, request_hash):
    entry = _bank_entry(session, deal.product_id)
    agreement = execution.active_agreement(session, body.rfq_id) if body.rfq_id else None
    if not entry and agreement:
        entry = session.exec(select(RfqElectronicExecution).where(
            RfqElectronicExecution.agreement_id == agreement.id)).first()
    if not entry:
        return
    session.add(RfqElectronicBooking(execution_id=entry.id, deal_id=deal.id, request_hash=request_hash,
        booked_by=user.id, booked_at=business_now()))
    _audit(session, entry, user.id, 'RFQ_ELECTRONIC_EXECUTION_BOOKED_LOCALLY')
    from .rfq_reconciliation import stage_current
    stage_current(session, entry, user.id)


def _audit(session, entry, actor_id, action):
    record_audit_event(session, action=action, object_type='RFQ_ELECTRONIC_EXECUTION', object_id=entry.solicitation_id,
        actor_user_id=actor_id, result='SUCCESS', correlation_id=entry.request_message_id,
        after={'execution_id': entry.id, 'request_hash': entry.request_hash, 'state': entry.state,
               'decision_message_id': entry.decision_message_id})
