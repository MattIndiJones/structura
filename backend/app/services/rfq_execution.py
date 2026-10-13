"""Explicit external treatment evidence and idempotent local booking (RFQ V1)."""
from __future__ import annotations

import json
import math
from typing import Literal
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..core.audit import record_audit_event
from ..db.models import (Counterparty, Deal, Entity, RfqExecutionAgreement, RfqExecutionBooking,
    RfqQuote, RfqQuotePublication, RfqRequest, RfqSolicitation, RfqRelationship)
from ..runtime import business_now, consultation_mode
from .product_repository import ProductError, load_product, owned_record
from .rfq_access import lock_rfq_organization, require_rfq_access
from . import rfq_exchange as exchange, rfq_publication as publication, rfq_relationships as relationships


class TreatmentRequest(BaseModel):
    quote_id: int
    expected_terms_version: int
    expected_terms_fingerprint: str = Field(min_length=64, max_length=64)
    command_key: str = Field(min_length=16, max_length=100)
    source: Literal['EMAIL', 'PHONE', 'DOCUMENT']
    reference: str = Field(min_length=3, max_length=500)
    bank_contact: str = Field(min_length=3, max_length=200)


class TreatmentConfirmation(BaseModel):
    expected_snapshot_hash: str = Field(min_length=64, max_length=64)
    execution_reference: str = Field(min_length=3, max_length=100)
    acceptance_received_at: datetime
    acceptance_evidence: str = Field(min_length=3, max_length=1000)
    confirmed_at: datetime
    source: Literal['BANK_CONFIRMATION', 'PHONE_DECLARATION']
    evidence: str = Field(min_length=3, max_length=1000)
    bank_contact: str = Field(min_length=3, max_length=200)


def active_agreement(session, rfq_id):
    return session.exec(select(RfqExecutionAgreement).where(
        RfqExecutionAgreement.rfq_id == rfq_id, RfqExecutionAgreement.state != 'CANCELLED'
    ).order_by(RfqExecutionAgreement.id.desc())).first()


def row(session, agreement):
    booked = session.get(RfqExecutionBooking, agreement.id)
    deal = session.get(Deal, booked.deal_id) if booked else None
    return {'id': agreement.id, 'rfq_id': agreement.rfq_id, 'quote_id': agreement.quote_id,
        'state': 'BOOKED_LOCALLY' if booked else agreement.state,
        'snapshot': json.loads(agreement.snapshot_json), 'snapshot_hash': agreement.snapshot_hash,
        'requested_at': exchange.iso(agreement.requested_at), 'request_source': agreement.request_source,
        'request_reference': agreement.request_reference, 'bank_contact': agreement.bank_contact,
        'execution_reference': agreement.execution_reference,
        'acceptance_received_at': exchange.iso(agreement.acceptance_received_at),
        'acceptance_evidence': agreement.acceptance_evidence,
        'confirmed_at': exchange.iso(agreement.confirmed_at), 'confirmation_source': agreement.confirmation_source,
        'confirmation_evidence': agreement.confirmation_evidence,
        'written_confirmation_pending': agreement.written_confirmation_pending,
        'cancellation_reason': agreement.cancellation_reason,
        'booking_block_reason': agreement.booking_block_reason,
        'booking_blocked_at': exchange.iso(agreement.booking_blocked_at),
        'review_required_reason': agreement.review_required_reason,
        'booked_deal': {'id': deal.id, 'reference': deal.reference} if deal else None}


def workspace(session, rfq_id):
    if consultation_mode() and not inspect(session.get_bind()).has_table('rfq_execution_agreements'):
        return []
    return [row(session, item) for item in session.exec(select(RfqExecutionAgreement).where(
        RfqExecutionAgreement.rfq_id == rfq_id).order_by(RfqExecutionAgreement.id.desc())).all()]


def protect_mutation(session, rfq_id, fields, quote_id=None):
    agreement = active_agreement(session, rfq_id)
    if agreement and (quote_id is None or agreement.quote_id == quote_id) and fields:
        raise HTTPException(409, 'Un traitement est consigné. Annulez la demande non confirmée avant de modifier la réponse ; un accord confirmé reste figé.')


def _counterparty(session, rfq, quote):
    published = publication.publication_for_quote(session, quote.id)
    if published:
        name = json.loads(published.payload_json)['counterparty_name']
    else:
        from ..api.rfq import _counterparty_by_provider
        name = _counterparty_by_provider(session).get(quote.provider)
    counterparty = session.exec(select(Counterparty).where(Counterparty.name == name,
        Counterparty.active == True)).first() if name else None
    if not counterparty:
        raise HTTPException(422, 'Rapprochez la contrepartie juridique avec une contrepartie active avant traitement')
    return counterparty


def _check_relation(session, rfq, published, snapshot):
    if not published:
        return
    item = session.get(RfqSolicitation, published.solicitation_id)
    relation = session.get(RfqRelationship, item.relationship_id)
    request = json.loads(item.request_json)
    if relation.version != request['recipient']['relationship_version']:
        raise HTTPException(409, 'La relation reconnue a changé ; ouvrez un nouveau tour')
    issues = relationships.eligibility(session, relation, rfq, currency=snapshot['currency'],
        nominal=snapshot['nominal'], purpose='treat')
    if issues:
        raise HTTPException(422, {'message': 'Traitement non autorisé par la relation RFQ', 'failures': issues})


def _snapshot(session, rfq, quote):
    product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
    try:
        product.terms.require_complete()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    counterparty = _counterparty(session, rfq, quote)
    published = publication.publication_for_quote(session, quote.id)
    response = json.loads(published.payload_json) if published else None
    params = json.loads(rfq.params_json)
    snapshot = {'rfq_id': rfq.id, 'rfq_reference': rfq.reference, 'quote_id': quote.id,
        'product_id': product.product_id, 'terms_version': product.terms_version,
        'terms_fingerprint': product.terms_fingerprint,
        'terms': product.terms.model_dump(mode='json', exclude={'schedule_error'}),
        'requester': session.get(Entity, rfq.entity_id).name,
        'counterparty_id': counterparty.id, 'counterparty_name': counterparty.name,
        'side': 'BUY' if rfq.sens == 'achat' else 'SELL', 'nominal': params.get('notional'),
        'currency': product.terms.settlement_ccy, 'price': quote.price,
        'price_unit': 'PERCENT_OF_NOTIONAL', 'price_convention': 'ALL_IN',
        'quote_valid_until': exchange.iso(quote.valid_until), 'quote_received_at': exchange.iso(quote.quoted_at),
        'quote_firmness': quote.firmness, 'origin': 'NETWORK' if published else 'MANUAL',
        'publication': response, 'transaction_format': rfq.transaction_format,
        'instrument_family': rfq.instrument_family,
        'documentation_reference': (response or {}).get('documentation_reference') or rfq.documentation_reference}
    if response and (response['conditions_type'] != 'NONE' or response['terms_fingerprint'] != product.terms_fingerprint):
        raise HTTPException(422, 'La réponse doit être conforme, sans condition supplémentaire à négocier')
    if not quote.price or quote.price <= 0 or not math.isfinite(quote.price) or not snapshot['nominal'] \
            or snapshot['nominal'] <= 0 or not math.isfinite(snapshot['nominal']) or not quote.valid_until:
        raise HTTPException(422, 'Prix, nominal et validité explicites requis avant traitement')
    if quote.currency and quote.currency != snapshot['currency']:
        raise HTTPException(422, 'La devise de la réponse diffère de celle du Product')
    if rfq.kind != 'to_trade' or any(not snapshot['terms'].get(key) for key in
            ('strike_date', 'value_date', 'maturity_date', 'payment_date')):
        raise HTTPException(422, 'Une RFQ to trade avec ses quatre dates est requise')
    _check_relation(session, rfq, published, snapshot)
    return snapshot


def request_treatment(session, rfq_id, user, body):
    rfq = lock_rfq_organization(session, rfq_id, user, 'book')
    # Also serialize legacy creator-owned RFQs, which have no ownership row.
    session.execute(update(RfqRequest).where(RfqRequest.id == rfq.id).values(id=rfq.id))
    request_hash = exchange.digest(body.model_dump(mode='json'))
    previous = session.exec(select(RfqExecutionAgreement).where(
        RfqExecutionAgreement.rfq_id == rfq_id, RfqExecutionAgreement.command_key == body.command_key)).first()
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, 'La même commande contient une autre demande de traitement')
        return row(session, previous)
    if active_agreement(session, rfq_id) or session.exec(select(Deal).where(Deal.rfq_id == rfq_id)).first():
        raise HTTPException(409, 'Un traitement ou booking existe déjà pour cette RFQ')
    quote = session.get(RfqQuote, body.quote_id)
    if not quote or quote.rfq_id != rfq_id or rfq.selected_quote_id != quote.id:
        raise HTTPException(409, 'Retenez cette réponse exacte avant de déclarer le traitement demandé')
    from ..api.rfq import _get_quotes, _quote_row, superseded_quote_ids
    superseded = quote.id in superseded_quote_ids(_get_quotes(rfq_id, session))
    if rfq.status != 'retenue' or quote.status != 'recu' or not _quote_row(quote, superseded=superseded, session=session)['comparable']:
        raise HTTPException(409, 'La réponse retenue doit être active et non remplacée')
    snapshot = _snapshot(session, rfq, quote)
    if snapshot['terms_version'] != body.expected_terms_version or snapshot['terms_fingerprint'] != body.expected_terms_fingerprint:
        raise HTTPException(409, 'Les termes Product ont changé ; rechargez la RFQ')
    if any(not value.strip() for value in (body.reference, body.bank_contact)):
        raise HTTPException(422, 'Référence externe et interlocuteur bancaire requis')
    agreement = RfqExecutionAgreement(rfq_id=rfq_id, entity_id=rfq.entity_id, quote_id=quote.id,
        command_key=body.command_key, request_hash=request_hash, snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        snapshot_hash=exchange.digest(snapshot), requested_by=user.id, requested_at=business_now(),
        request_source=body.source, request_reference=body.reference.strip(), bank_contact=body.bank_contact.strip())
    session.add(agreement); session.flush()
    _record(session, rfq, user, agreement, 'RFQ_TREATMENT_REQUEST_DECLARED')
    session.commit()
    return row(session, agreement)


def confirm_treatment(session, rfq_id, agreement_id, user, body):
    rfq = lock_rfq_organization(session, rfq_id, user, 'book')
    agreement = _require(session, rfq_id, agreement_id)
    session.execute(update(RfqExecutionAgreement).where(RfqExecutionAgreement.id == agreement_id).values(state=agreement.state))
    session.refresh(agreement)
    payload = body.model_dump(mode='json')
    payload['execution_reference'] = body.execution_reference.strip().upper()
    confirmation_hash = exchange.digest(payload)
    if agreement.confirmation_hash:
        if agreement.confirmation_hash != confirmation_hash:
            raise HTTPException(409, 'La confirmation déjà consignée contient un autre accord')
        return row(session, agreement)
    if agreement.state != 'REQUESTED' or agreement.snapshot_hash != body.expected_snapshot_hash:
        raise HTTPException(409, 'La demande de traitement a changé ou a été annulée')
    snapshot = json.loads(agreement.snapshot_json)
    quote = session.get(RfqQuote, agreement.quote_id)
    current_snapshot = _snapshot(session, rfq, quote)
    if exchange.digest(current_snapshot) != agreement.snapshot_hash or rfq.selected_quote_id != quote.id:
        raise HTTPException(409, 'La réponse ou les termes ont changé depuis la demande de traitement')
    published = publication.publication_for_quote(session, quote.id)
    if published and publication.publication_state(session, published) not in {'ACTIVE', 'EXPIRED'}:
        raise HTTPException(409, 'Retrait, remplacement ou clôture : ordre externe à revoir, aucune priorité déduite de l’heure saisie')
    if not published and quote.status != 'recu':
        raise HTTPException(409, 'La réponse manuelle n’est plus reçue')
    accepted, confirmed = publication.utc(body.acceptance_received_at), publication.utc(body.confirmed_at)
    earliest = publication.utc(snapshot['quote_received_at']) if snapshot['quote_received_at'] else agreement.requested_at
    if not earliest <= accepted <= confirmed <= business_now():
        raise HTTPException(422, 'Chronologie invalide : réception après émission de la réponse, puis confirmation, sans date future')
    if accepted >= publication.utc(snapshot['quote_valid_until']):
        raise HTTPException(422, 'La cotation avait expiré à la réception déclarée de l’acceptation')
    if any(len(value.strip()) < 3 for value in (body.execution_reference, body.acceptance_evidence, body.evidence, body.bank_contact)):
        raise HTTPException(422, 'Référence d’exécution, interlocuteur et preuves de réception/confirmation requis')
    duplicate = session.exec(select(RfqExecutionAgreement).where(
        RfqExecutionAgreement.entity_id == agreement.entity_id,
        RfqExecutionAgreement.execution_reference == payload['execution_reference'])).first()
    if duplicate:
        raise HTTPException(409, 'Cette référence d’exécution est déjà consignée dans l’organisation')
    agreement.state = 'CONFIRMED'
    agreement.execution_reference = payload['execution_reference']
    agreement.acceptance_received_at, agreement.confirmed_at = accepted, confirmed
    agreement.acceptance_evidence = body.acceptance_evidence.strip()
    agreement.confirmed_by = user.id
    agreement.confirmation_source, agreement.confirmation_evidence = body.source, body.evidence.strip()
    agreement.bank_contact = body.bank_contact.strip()
    agreement.written_confirmation_pending = body.source == 'PHONE_DECLARATION'
    agreement.confirmation_hash = confirmation_hash
    if published:
        # A locally declared external fact, never sent as a native bank receipt.
        published.acceptance_received_at = accepted
        session.add(published)
    session.add(agreement)
    _record(session, rfq, user, agreement, 'RFQ_TREATMENT_CONFIRMED_EXTERNALLY')
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Cette référence d’exécution a été consignée simultanément')
    return row(session, agreement)


def _require(session, rfq_id, agreement_id):
    agreement = session.get(RfqExecutionAgreement, agreement_id)
    if not agreement or agreement.rfq_id != rfq_id:
        raise HTTPException(404, 'Accord de traitement introuvable')
    return agreement


def cancel_request(session, rfq_id, agreement_id, user, reason):
    rfq = lock_rfq_organization(session, rfq_id, user, 'book')
    agreement = _require(session, rfq_id, agreement_id)
    session.execute(update(RfqExecutionAgreement).where(RfqExecutionAgreement.id == agreement_id).values(state=agreement.state))
    session.refresh(agreement)
    if agreement.state != 'REQUESTED' or len(reason.strip()) < 3:
        raise HTTPException(409, 'Seule une demande non confirmée peut être annulée, avec motif')
    agreement.state, agreement.cancellation_reason = 'CANCELLED', reason.strip()
    session.add(agreement)
    _record(session, rfq, user, agreement, 'RFQ_TREATMENT_REQUEST_CANCELLED')
    session.commit()
    return row(session, agreement)


def _record(session, rfq, user, agreement, action):
    session.flush()
    record_audit_event(session, action=action, object_type='RFQ', object_id=rfq.id,
        actor_user_id=user.id, result='SUCCESS', after=row(session, agreement))
    from ..api.rfq import _sync_product_rfq
    _sync_product_rfq(session, rfq, user, action='PRODUCT_' + action)


def booking_request_hash(body):
    return exchange.digest(body.model_dump(mode='json', exclude={'execution_agreement_id'}))


def booking_context(session, body, user):
    if not body.rfq_id:
        if body.execution_agreement_id is not None:
            raise HTTPException(422, 'Un accord de traitement exige sa RFQ source')
        if body.product_id is not None:
            try:
                owned_record(session, body.product_id, user)
            except ProductError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
            bound = session.exec(select(RfqRequest).where(RfqRequest.product_id == body.product_id)).all()
            for rfq in bound:
                if active_agreement(session, rfq.id) or session.exec(select(RfqQuotePublication.id).join(
                        RfqQuote, RfqQuote.id == RfqQuotePublication.quote_id).where(RfqQuote.rfq_id == rfq.id)).first():
                    raise HTTPException(409, 'Ce Product porte un parcours RFQ réseau ou un accord de traitement ; conservez le lien RFQ au booking')
        return None, None
    rfq = lock_rfq_organization(session, body.rfq_id, user, 'book')
    session.execute(update(RfqRequest).where(RfqRequest.id == rfq.id).values(id=rfq.id))
    agreement = active_agreement(session, rfq.id)
    if body.execution_agreement_id is not None and (not agreement or agreement.id != body.execution_agreement_id):
        raise HTTPException(409, 'Le booking ne vise pas l’accord actif de cette RFQ')
    if agreement:
        if agreement.state != 'CONFIRMED':
            raise HTTPException(409, 'Le traitement est demandé ; sa confirmation est encore attendue')
        booked = session.get(RfqExecutionBooking, agreement.id)
        if booked:
            if booked.request_hash != booking_request_hash(body):
                raise HTTPException(409, 'Cette exécution a déjà été bookée avec un autre contenu')
            return agreement, session.get(Deal, booked.deal_id)
        if agreement.review_required_reason:
            raise HTTPException(409, agreement.review_required_reason)
        snapshot = json.loads(agreement.snapshot_json)
        product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
        if exchange.digest(snapshot) != agreement.snapshot_hash or product.terms_fingerprint != snapshot['terms_fingerprint']:
            raise HTTPException(409, 'Les termes de l’accord confirmé diffèrent du Product')
        expected = {'price_traded': snapshot['price'], 'nominal': snapshot['nominal'], 'devise': snapshot['currency'],
            'contrepartie': snapshot['counterparty_name'], 'sens': 'vente' if snapshot['side'] == 'BUY' else 'achat'}
        if any(getattr(body, key) != value for key, value in expected.items()) or rfq.selected_quote_id != agreement.quote_id:
            raise HTTPException(409, 'Le prix, le nominal, les parties ou le sens diffèrent de l’accord confirmé')
        published = publication.publication_for_quote(session, agreement.quote_id)
        if published and publication.publication_state(session, published) != 'RESERVED':
            raise HTTPException(409, 'La cotation confirmée fait l’objet d’un conflit ; revue requise')
    elif rfq.selected_quote_id and publication.publication_for_quote(session, rfq.selected_quote_id):
        raise HTTPException(409, 'Consignez la confirmation du traitement avant de booker une réponse réseau')
    return agreement, None


def attach_booking(session, agreement, deal, user, request_hash):
    if not agreement:
        return
    session.add(RfqExecutionBooking(agreement_id=agreement.id, entity_id=agreement.entity_id,
        execution_reference=agreement.execution_reference, rfq_id=agreement.rfq_id, deal_id=deal.id,
        request_hash=request_hash, booked_by=user.id, booked_at=business_now()))
    agreement.booking_block_reason = None
    agreement.booking_blocked_at = None
    session.add(agreement)
    record_audit_event(session, action='RFQ_EXECUTION_BOOKED_LOCALLY', object_type='RFQ', object_id=agreement.rfq_id,
        actor_user_id=user.id, result='SUCCESS', after={'agreement_id':agreement.id,
            'execution_reference':agreement.execution_reference, 'deal_id':deal.id, 'snapshot_hash':agreement.snapshot_hash})


def flag_external_conflict(session, quote_id, message_id, reason):
    quote = session.get(RfqQuote, quote_id)
    agreement = active_agreement(session, quote.rfq_id)
    if agreement and agreement.quote_id == quote_id and agreement.state == 'CONFIRMED':
        agreement.review_required_reason = reason
        session.add(agreement)
        record_audit_event(session, action='RFQ_CONFIRMED_EXECUTION_EXTERNAL_CONFLICT', object_type='RFQ',
            object_id=agreement.rfq_id, actor_user_id=None, result='ERROR', correlation_id=message_id,
            reason=reason, after={'agreement_id':agreement.id, 'snapshot_hash':agreement.snapshot_hash})


def record_booking_block(session, body, user, reason):
    if not body.rfq_id:
        return
    try:
        require_rfq_access(session, body.rfq_id, user, 'book')
    except HTTPException:
        return
    agreement = active_agreement(session, body.rfq_id)
    if agreement and agreement.state == 'CONFIRMED' and not session.get(RfqExecutionBooking, agreement.id):
        agreement.booking_block_reason = reason
        agreement.booking_blocked_at = business_now()
        session.add(agreement)
        from ..api.rfq import _sync_product_rfq
        rfq = session.get(RfqRequest, body.rfq_id)
        _sync_product_rfq(session, rfq, user, action='PRODUCT_RFQ_CONFIRMED_BOOKING_BLOCKED')
        session.commit()
