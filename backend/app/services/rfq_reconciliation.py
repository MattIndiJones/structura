"""Compare dated public execution/booking facts; never copy or repair private books."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, update
from sqlmodel import select

from ..core.access import require_booking_permission
from ..core.audit import record_audit_event
from ..db.models import (Deal, ProductTermsVersion, RfqElectronicBooking, RfqElectronicExecution,
    RfqExecutionAgreement, RfqRelationshipSide, RfqReconciliationStatement, RfqSolicitation,
    RfqTransportOutbox, RfqExchangeRound)
from ..runtime import business_now, consultation_mode
from . import rfq_bank as bank, rfq_exchange as exchange, rfq_transport as transport
from .rfq_access import lock_rfq_organization, require_rfq_access


class RefreshCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_key: str = Field(min_length=16, max_length=100)


class BookingFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    side: Literal['BUY', 'SELL']
    nominal: float = Field(gt=0, allow_inf_nan=False)
    currency: str = Field(min_length=3, max_length=3)
    price: float = Field(allow_inf_nan=False)
    terms_fingerprint: str = Field(min_length=64, max_length=64)
    trade_date: str
    strike_date: str
    value_date: str
    maturity_date: str
    payment_date: str
    documentation_reference: str
    transaction_format: str
    instrument_family: str
    payoff_family: str
    legal_mapping_matches: bool = Field(strict=True)


class WireStatement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format_version: Literal[1]
    execution_id: UUID
    request_hash: str = Field(min_length=64, max_length=64)
    role: Literal['REQUESTER', 'BANK']
    version: int = Field(gt=0, strict=True)
    execution_state: Literal['CONFIRMED', 'REJECTED']
    decision_hash: str = Field(min_length=64, max_length=64)
    observed_at: datetime
    booking: BookingFact | None
    request_reply: bool = Field(strict=True)


def available(session):
    return not consultation_mode() or inspect(session.get_bind()).has_table('rfq_reconciliation_statements')


def latest(session, entry, *, local):
    return session.exec(select(RfqReconciliationStatement).where(
        RfqReconciliationStatement.execution_id == entry.id,
        RfqReconciliationStatement.is_local == local).order_by(RfqReconciliationStatement.version.desc())).first()


def fact(session, entry):
    quote = json.loads(entry.request_json)['quote']
    bound = session.get(RfqElectronicBooking, entry.id)
    booking = None
    if bound:
        deal = session.get(Deal, bound.deal_id)
        terms = session.exec(select(ProductTermsVersion).where(ProductTermsVersion.product_id == deal.product_id,
            ProductTermsVersion.version == deal.product_terms_version)).one()
        if entry.role == 'REQUESTER':
            agreement = session.get(RfqExecutionAgreement, entry.agreement_id)
            legal_id = json.loads(agreement.snapshot_json)['counterparty_id']
        else:
            item = session.get(RfqSolicitation, entry.solicitation_id)
            link = transport.link_for(session, item.id)
            channel = session.get(transport.RfqChannel, link.channel_id)
            side = session.get(RfqRelationshipSide, (item.relationship_id, channel.entity_id))
            legal_id = side.counterparty_id if side else None
        booking = {'side': 'BUY' if deal.sens == 'vente' else 'SELL', 'nominal': deal.nominal,
            'currency': deal.devise, 'price': deal.price_traded, 'terms_fingerprint': terms.fingerprint,
            'legal_mapping_matches': legal_id is not None and legal_id == deal.counterparty_id,
            **{key: (getattr(deal,key) or '').upper() for key in ('transaction_format','instrument_family','payoff_family')},
            **{key: getattr(deal, key) for key in ('trade_date','strike_date', 'value_date', 'maturity_date', 'payment_date',
                                                  'documentation_reference')}}
    return {'execution_state': entry.state, 'decision_hash': exchange.digest(json.loads(entry.decision_json))
        if entry.decision_json else None, 'booking': booking}


def expected_booking(session, entry, role):
    quote = json.loads(entry.request_json)['quote']
    request = json.loads(session.get(RfqSolicitation, entry.solicitation_id).request_json)
    terms = request['terms']
    return {'side': quote['side'] if role == 'REQUESTER' else ('SELL' if quote['side'] == 'BUY' else 'BUY'),
        'nominal': quote['nominal'], 'currency': quote['currency'], 'price': quote['price'],
        'terms_fingerprint': quote['terms_fingerprint'], 'legal_mapping_matches': True,
        'documentation_reference': quote['documentation_reference'],
        **{key:(request.get(key) or '').upper() for key in ('transaction_format','instrument_family','payoff_family')},
        **{key: terms[key] for key in ('strike_date', 'value_date', 'maturity_date', 'payment_date')}}


def workspace(session, entry):
    if not available(session):
        return None
    local, peer, own = fact(session, entry), latest(session, entry, local=False), latest(session, entry, local=True)
    remote = json.loads(peer.payload_json) if peer else None
    current = json.loads(own.payload_json) if own else None
    differences = []
    for role, actual in ((entry.role, local), ('BANK' if entry.role == 'REQUESTER' else 'REQUESTER', remote)):
        if actual and actual['booking'] is None:
            history = session.exec(select(RfqReconciliationStatement).where(
                RfqReconciliationStatement.execution_id == entry.id,
                RfqReconciliationStatement.role == role)).all()
            if any(json.loads(row.payload_json)['booking'] is not None for row in history):
                differences.append({'side':'LOCAL' if role == entry.role else 'PEER',
                    'field':'booking_regression','expected':'BOOKED','actual':'MISSING'})
        if actual and actual['booking']:
            expected = expected_booking(session, entry, role)
            for key, value in expected.items():
                if actual['booking'].get(key) != value:
                    differences.append({'side': 'LOCAL' if role == entry.role else 'PEER', 'field': key,
                        'expected': value, 'actual': actual['booking'].get(key)})
            if actual['execution_state'] != 'CONFIRMED':
                differences.append({'side': 'LOCAL' if role == entry.role else 'PEER', 'field': 'booking_without_confirmation',
                    'expected': 'CONFIRMED', 'actual': actual['execution_state']})
    if remote and entry.state in {'CONFIRMED','REJECTED'}:
        if local['booking'] and remote['booking'] and local['booking']['trade_date'] != remote['booking'].get('trade_date'):
            differences.append({'side':'PEER','field':'trade_date','expected':local['booking']['trade_date'],
                'actual':remote['booking'].get('trade_date')})
        for key in ('execution_state','decision_hash'):
            if local[key] != remote[key]:
                differences.append({'side': 'PEER','field':key,'expected':local[key],'actual':remote[key]})
    sent = transport.transport_row(session, own.message_id) if own else None
    local_changed = bool(current and any(local[k] != current[k] for k in ('execution_state','decision_hash','booking')))
    if differences:
        state = 'MISMATCH'
    elif entry.state not in {'CONFIRMED','REJECTED'}:
        state = 'DECISION_PENDING'
    elif not remote:
        state = 'PEER_UNKNOWN'
    elif entry.state == 'REJECTED':
        state = 'REJECTED'
    elif not local['booking']:
        state = 'LOCAL_BOOKING_MISSING' if remote['booking'] else 'BOTH_BOOKINGS_MISSING'
    elif not remote['booking']:
        state = 'PEER_BOOKING_MISSING'
    elif local_changed or not sent or sent['state'] != 'DELIVERED':
        state = 'MATCHED_PENDING_DELIVERY'
    else:
        state = 'MATCHED'
    bound = session.get(RfqElectronicBooking, entry.id)
    return {'execution_id':entry.id, 'state':state, 'differences':differences,
        'local':local, 'peer':remote, 'peer_received_at':exchange.iso(peer.recorded_at) if peer else None,
        'local_changed_since_publication':local_changed, 'transport':sent,
        'local_deal_id':bound.deal_id if bound else None,
        'peer_version':peer.version if peer else None, 'local_version':own.version if own else None}


def authorize(session, identifier, user, *, write=False):
    entry = session.get(RfqElectronicExecution, identifier)
    if not entry:
        raise HTTPException(404,'Exécution électronique introuvable.')
    if write:
        require_booking_permission(user)
    item = session.get(RfqSolicitation, entry.solicitation_id)
    if entry.role == 'BANK':
        bank.require_action(session,item.id,user,'book' if write else 'read',lock=write)
    else:
        rfq_id = session.get(RfqExchangeRound,item.round_id).rfq_id
        if write:
            lock_rfq_organization(session,rfq_id,user,'book')
        else:
            require_rfq_access(session,rfq_id,user,'read')
    return entry


def stage_current(session, entry, actor_id, *, request_reply=True, command_key=None):
    if entry.state not in {'CONFIRMED','REJECTED'}:
        return None
    item = session.get(RfqSolicitation,entry.solicitation_id)
    session.execute(update(RfqSolicitation).where(RfqSolicitation.id==item.id).values(message_id=item.message_id))
    prior = latest(session,entry,local=True)
    payload = {'format_version':1,'execution_id':entry.id,'request_hash':entry.request_hash,'role':entry.role,
        'version':prior.version+1 if prior else 1,'observed_at':exchange.iso(business_now()),
        'request_reply':request_reply,**fact(session,entry)}
    message = transport.queue(session,item,'EXECUTION_STATUS',payload,actor_id)
    session.add(RfqReconciliationStatement(message_id=message.id,execution_id=entry.id,role=entry.role,
        version=payload['version'],payload_json=transport.canonical(payload),payload_hash=exchange.digest(payload),
        is_local=True,command_key=command_key,recorded_at=business_now()))
    record_audit_event(session,action='RFQ_RECONCILIATION_PUBLISHED',object_type='RFQ_SOLICITATION',
        object_id=item.id,actor_user_id=actor_id,result='SUCCESS',correlation_id=message.id,
        after={'execution_id':entry.id,'version':payload['version'],'booking_present':payload['booking'] is not None})
    return message


def refresh(session, identifier, user, body):
    entry = authorize(session,identifier,user,write=True)
    session.execute(update(RfqSolicitation).where(RfqSolicitation.id==entry.solicitation_id)
        .values(message_id=RfqSolicitation.message_id))
    prior = session.exec(select(RfqReconciliationStatement).where(
        RfqReconciliationStatement.execution_id==identifier,RfqReconciliationStatement.command_key==body.command_key)).first()
    # Reschedule the existing events; do not cancel leases or manufacture new decisions/bookings.
    pending = session.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.solicitation_id==entry.solicitation_id,
        RfqTransportOutbox.kind.in_(['EXECUTION_REQUEST','EXECUTION_CONFIRMATION','EXECUTION_STATUS','CLOSE']),
        RfqTransportOutbox.state.notin_(['DELIVERED','CANCELLED']))).all()
    for row in pending:
        row.next_attempt_at=datetime.utcnow();session.add(row)
    if not prior:
        stage_current(session,entry,user.id,command_key=body.command_key)
    record_audit_event(session,action='RFQ_RECONCILIATION_RESUME_REQUESTED',object_type='RFQ_SOLICITATION',
        object_id=entry.solicitation_id,actor_user_id=user.id,result='SUCCESS',
        after={'execution_id':entry.id,'pending_messages':len(pending),'replayed':prior is not None})
    session.commit()
    return workspace(session,entry)


def receive(session, item, message):
    payload=message['payload']; parsed=WireStatement.model_validate(payload)
    entry=session.get(RfqElectronicExecution,str(parsed.execution_id))
    if not entry or entry.solicitation_id!=item.id or entry.request_hash!=parsed.request_hash \
            or parsed.role==entry.role:
        raise HTTPException(409,'État de rapprochement étranger à cette exécution ou au rôle du pair.')
    observed=publication_time(parsed.observed_at)
    if observed>business_now() or (entry.decision_json and observed < publication_time(
            json.loads(entry.decision_json)['decided_at'])):
        raise HTTPException(422,'Chronologie de rapprochement invalide.')
    prior=latest(session,entry,local=False)
    if prior and parsed.version<=prior.version:
        raise HTTPException(409,'Révision de rapprochement ancienne ou conflictuelle.')
    if prior and observed < publication_time(json.loads(prior.payload_json)['observed_at']):
        raise HTTPException(409,'Date d’observation antérieure au dernier état reçu.')
    session.add(RfqReconciliationStatement(message_id=message['id'],execution_id=entry.id,role=parsed.role,
        version=parsed.version,payload_json=transport.canonical(payload),payload_hash=exchange.digest(payload),
        is_local=False,recorded_at=business_now()))
    session.flush()
    if parsed.request_reply:
        stage_current(session,entry,transport.remote_source(session).id,request_reply=False)
    record_audit_event(session,action='RFQ_RECONCILIATION_RECEIVED',object_type='RFQ_SOLICITATION',
        object_id=item.id,actor_user_id=None,result='SUCCESS',correlation_id=message['id'],
        after={'execution_id':entry.id,'peer_version':parsed.version,'state':workspace(session,entry)['state']})


def publication_time(value):
    from .rfq_publication import utc
    return utc(value)


def confirmed_booking_pending(session, item_id):
    from .rfq_electronic import for_item
    entry=for_item(session,item_id)
    return bool(entry and entry.role=='BANK' and entry.state=='CONFIRMED'
        and not session.get(RfqElectronicBooking,entry.id))
