"""Bilateral execution decisions, exact revisions and durable retry semantics."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from backend.app.api import rfq as api, rfq_inbox as inbox, rfq_transport as transport_api, products, deals
from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import (Deal, RfqChannel, RfqDeskMembership, RfqElectronicBooking,
    RfqElectronicExecution, RfqElectronicEvidence, RfqExecutionAgreement, RfqQuotePublication, RfqRelationship,
    RfqRelationshipSide, RfqSolicitation, RfqTransportInbox, RfqTransportOutbox)
from backend.app.db.trading_models import TradingRelationship
from backend.app.db.rfq_execution_integrity import install_execution_guards
from backend.app.db.rfq_transport_integrity import install_transport_guards
from backend.app.services import rfq_electronic as service, rfq_execution as execution
from backend.app.services import rfq_publication as publication, rfq_transport as transport, rfq_state
from backend.app.services import rfq_exchange as exchange
from backend.app.services import rfq_reconciliation
from backend.app.services.product_repository import load_product
from backend.tests.test_rfq_relationships import network_case, terms
from backend.tests.test_rfq_transport import paired, published, flush
from backend.tests.test_rfq_bank_publication import decision, prepare
from backend.tests.test_rfq_bank_pricing import context


@pytest.fixture
def electronic_case(paired, monkeypatch):
    a, b, users, banker, rfq, cid, client = paired
    clock = {'now': datetime.utcnow()}
    for module in (service, execution, publication, transport, rfq_state, rfq_reconciliation):
        monkeypatch.setattr(module, 'business_now', lambda: clock['now'])
    for db, actor, relation_id, cp_id, desk in ((a, users[3], a.get(RfqChannel, cid).relationship_id, 1, 11),
                                              (b, banker, 700, 612, 721)):
        membership = db.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == actor.id,
            RfqDeskMembership.desk_id == desk)).one()
        membership.rights_json = json.dumps(sorted(set(json.loads(membership.rights_json)) | {'book', 'select'}))
        db.add(membership)
        relation = db.get(RfqRelationship, relation_id)
        relation.terms_json = terms(to_trade_allowed=True, treatment_allowed=True,
            documentation_reference='EMTN de recette électronique').model_dump_json()
        db.add(relation)
        trading = TradingRelationship(entity_id=actor.entity_id, counterparty_id=cp_id,
            reference='ELECTRONIC-TEST', updated_by=actor.id, terms_json=json.dumps({
                'status': 'ACTIVE', 'currency': 'EUR', 'documentation_reference': 'EMTN de recette électronique',
                'note_distribution_allowed': True, 'effective_date': clock['now'].date().isoformat()}))
        db.add(trading); db.flush()
        side = db.get(RfqRelationshipSide, (relation.id, actor.entity_id))
        side.trading_relationship_id = trading.id; db.add(side)
        channel = db.get(RfqChannel, cid)
        channel.agreement_hash = transport.agreement(db, relation); db.add(channel); db.commit()
        install_execution_guards(db.get_bind()); install_transport_guards(db.get_bind())
    transport.probe(a, a.get(RfqChannel, cid), client)
    params = {**rfq['params'], 'constats': {'FINAL': rfq['params']['maturity_date']}}
    created = api.create_rfq(api.RfqCreate(pilot_desk_id=11, kind='to_trade', params=params,
        name='Exécution électronique', transaction_format='EMTN', instrument_family='Note', payoff_family='Autocall',
        script_snapshot='CONSTAT FINAL\nAT FINAL:\n  PAY 1', documentation_reference='EMTN de recette électronique'), users[3], a)
    revised = json.loads(json.dumps(params))
    revised['underlyings'][0]['ticker'] = 'TK2'
    updated = api.update_rfq(created['id'], api.RfqUpdate(params=revised), users[3], a)
    rfq.clear(); rfq.update(updated)
    item_id, quote = published(paired)
    flush(paired, b, quote['response']['message_id'])
    current = inbox.received_request(item_id, banker, b)
    draft = prepare(b, banker, item_id, current['case']['calculations'][-1]['id'],
                    revision=current['quote_draft']['revision'], firmness='FIRM')
    approved = inbox.validate_quote(item_id, decision(draft), banker, b)
    firm = inbox.publish_quote(item_id, decision(approved), banker, b)
    flush(paired, b, firm['publications'][0]['response']['message_id'])
    a.expire_all()
    remote_quote = a.exec(select(RfqQuotePublication).order_by(RfqQuotePublication.revision.desc())).first()
    api.update_rfq(rfq['id'], api.RfqUpdate(selected_quote_id=remote_quote.quote_id,
        expected_quote_revision=remote_quote.revision), users[3], a)
    return paired, item_id, remote_quote.quote_id, clock


def ask(case, **changes):
    paired_case, _, quote_id, _ = case
    a, _, users, _, rfq, _, _ = paired_case
    product = load_product(a, rfq['product_id'])
    body = dict(quote_id=quote_id, expected_terms_version=product.terms_version,
        expected_terms_fingerprint=product.terms_fingerprint, command_key=str(uuid4()))
    body.update(changes)
    return api.request_electronic_execution(rfq['id'], service.ElectronicRequest(**body), users[3], a), body


def received(case):
    result, body = ask(case)
    flush(case[0], case[0][0], result['transport']['message_id'])
    case[0][1].expire_all()
    return result, body


def decide(case, request, outcome='CONFIRMED', reason='Accord de recette explicite'):
    _, b, _, banker, _, _, _ = case[0]
    return inbox.decide_electronic_execution(case[1], request['id'], service.BankDecision(
        expected_request_hash=request['request_hash'], decision=outcome, reason=reason), banker, b)['electronic_execution']


def test_exact_quote_confirmed_by_bank_not_by_delivery_ack(electronic_case):
    case = electronic_case
    a, b, _, _, _, _, _ = case[0]
    requested, _ = received(case)
    assert b.get(RfqElectronicExecution, requested['id']).state == 'RECEIVED'
    a.expire_all()
    assert a.get(RfqElectronicExecution, requested['id']).state == 'PENDING'
    assert a.exec(select(RfqExecutionAgreement)).one().state == 'REQUESTED'
    assert not a.exec(select(Deal)).all() and not b.exec(select(Deal)).all()
    decision_row = decide(case, requested)
    assert decision_row['state'] == 'CONFIRMED'
    assert a.get(RfqElectronicExecution, requested['id']).state == 'PENDING'
    flush(case[0], b, decision_row['transport']['message_id'])
    a.expire_all()
    agreement = a.exec(select(RfqExecutionAgreement)).one()
    assert agreement.state == 'CONFIRMED' and agreement.confirmation_source == 'ELECTRONIC_CONFIRMATION'
    assert not agreement.written_confirmation_pending
    assert agreement.execution_reference == decision_row['execution_reference']
    evidence = a.get(RfqElectronicEvidence, decision_row['transport']['message_id'])
    packet = json.loads(evidence.envelope_json)
    assert packet['signature'] == transport.signature(a.get(RfqChannel, case[0][5]), packet['body'])
    assert packet['body']['message']['payload']['request_hash'] == requested['request_hash']
    assert b.get(RfqElectronicExecution, requested['id']).request_hash == requested['request_hash']
    assert json.loads(b.get(RfqElectronicExecution, requested['id']).request_json)['quote'] == requested['quote']
    assert load_product(b, b.get(RfqElectronicExecution, requested['id']).product_id).terms_version == 1
    assert requested['quote']['terms_version'] > 1  # local versions are not cross-installation IDs


def test_request_retry_uses_same_intention_and_conflicts_are_rejected(electronic_case):
    result, body = ask(electronic_case)
    a, _, users, _, rfq, _, _ = electronic_case[0]
    assert api.request_electronic_execution(rfq['id'], service.ElectronicRequest(**body), users[3], a)['id'] == result['id']
    for change in ({'command_key': str(uuid4())}, {'quote_id': body['quote_id'] + 100}, {'expected_terms_version': 99}):
        with pytest.raises(HTTPException) as exc:
            api.request_electronic_execution(rfq['id'], service.ElectronicRequest(**(body | change)), users[3], a)
        assert exc.value.status_code == 409
        a.rollback()
    assert len(a.exec(select(RfqElectronicExecution)).all()) == 1
    assert len(a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'EXECUTION_REQUEST')).all()) == 1


def test_bank_decision_retry_is_idempotent_and_conflicting_decision_is_refused(electronic_case):
    request, _ = received(electronic_case)
    first = decide(electronic_case, request)
    assert decide(electronic_case, request)['transport']['message_id'] == first['transport']['message_id']
    with pytest.raises(HTTPException) as exc:
        decide(electronic_case, request, 'REJECTED', 'Autre décision')
    assert exc.value.status_code == 409
    b = electronic_case[0][1]; b.rollback()
    assert len(b.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'EXECUTION_CONFIRMATION')).all()) == 1


@pytest.mark.parametrize('leg', ['request', 'confirmation'])
def test_lost_ack_recovered_by_status_without_reapplying_decision(electronic_case, leg):
    case = electronic_case
    a, b, users, banker, _, _, native_client = case[0]
    request, _ = ask(case)
    source = a
    message_id = request['transport']['message_id']
    if leg == 'confirmation':
        flush(case[0], a, message_id)
        response = decide(case, request)
        source, message_id = b, response['transport']['message_id']
    def lose_ack(http_request):
        response = native_client.post(str(http_request.url), json=json.loads(http_request.content))
        response.raise_for_status()
        raise httpx.ReadError('receipt lost after durable receipt', request=http_request)
    with httpx.Client(transport=httpx.MockTransport(lose_ack)) as faulty:
        transport.deliver_one(source.get_bind(), message_id, faulty)
    source.expire_all()
    assert source.get(RfqTransportOutbox, message_id).state == 'RETRY'
    # Explicit retry schedules the same outbox item, then the original actor loses rights.
    transport_api.retry(message_id, users[3] if source is a else banker, source)
    actor = users[3] if source is a else banker
    actor.is_active = False; source.add(actor); source.commit()
    flush(case[0], source, message_id)
    assert source.get(RfqTransportOutbox, message_id).state == 'DELIVERED'
    assert source.get(RfqTransportOutbox, message_id).attempts == 2
    destination = b if source is a else a
    destination.expire_all()
    assert len(destination.exec(select(RfqElectronicExecution)).all()) == 1
    assert destination.get(RfqTransportInbox, message_id)


def test_first_arrival_after_expiry_is_explicitly_rejected_not_backdated(electronic_case):
    case = electronic_case
    result, _ = ask(case)
    a, b, _, _, _, _, _ = case[0]
    case[3]['now'] = publication.utc(result['quote']['valid_until']) + timedelta(seconds=1)
    flush(case[0], a, result['transport']['message_id'])
    b.expire_all()
    row = service.public_row(b, b.get(RfqElectronicExecution, result['id']))
    assert row['state'] == 'REJECTED' and 'réception bancaire' in row['decision']['reason']
    flush(case[0], b, row['transport']['message_id'])
    a.expire_all()
    assert a.get(RfqElectronicExecution, result['id']).state == 'REJECTED'
    assert a.exec(select(RfqExecutionAgreement)).one().state == 'CANCELLED'


def test_valid_arrival_can_be_decided_after_expiry_without_rewriting_receipt(electronic_case):
    case = electronic_case
    result, _ = received(case)
    b = case[0][1]
    original = b.get(RfqElectronicExecution, result['id']).received_at
    case[3]['now'] = publication.utc(result['quote']['valid_until']) + timedelta(minutes=1)
    answer = decide(case, result)
    assert publication.utc(answer['received_at']) == original
    flush(case[0], b, answer['transport']['message_id'])
    case[0][0].expire_all()
    assert case[0][0].get(RfqElectronicExecution, result['id']).state == 'CONFIRMED'


def test_pending_request_prevents_replacement_withdrawal_and_local_forged_confirmation(electronic_case):
    case = electronic_case
    request, _ = received(case)
    a, b, users, banker, rfq, _, _ = case[0]
    pub = b.exec(select(RfqQuotePublication).order_by(RfqQuotePublication.revision.desc())).first()
    with pytest.raises(HTTPException) as exc:
        publication.withdraw(b, case[1], pub.id, banker, 'Retrait concurrent')
    assert exc.value.status_code == 409; b.rollback()
    with pytest.raises(HTTPException):
        service.protect_publication(b, case[1])
    b.rollback()
    agreement = a.exec(select(RfqExecutionAgreement)).one()
    with pytest.raises(HTTPException) as exc:
        execution.cancel_request(a, rfq['id'], agreement.id, users[3], 'Annulation locale')
    assert exc.value.status_code == 409; a.rollback()
    with pytest.raises(HTTPException) as exc:
        execution.confirm_treatment(a, rfq['id'], agreement.id, users[3], None)
    assert exc.value.status_code == 409; a.rollback()


@pytest.mark.parametrize('decision_side', ['requester', 'bank'])
def test_execution_requires_desk_book_right_not_just_price_or_publish(electronic_case, decision_side):
    case = electronic_case
    a, b, users, banker, _, _, _ = case[0]
    result, _ = received(case) if decision_side == 'bank' else (None, None)
    db, actor = (a, users[3]) if decision_side == 'requester' else (b, banker)
    membership = db.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == actor.id)).one()
    membership.rights_json = '["read","prepare","price","publish_quote"]'; db.add(membership); db.commit()
    with pytest.raises(HTTPException) as exc:
        ask(case) if decision_side == 'requester' else decide(case, result)
    assert exc.value.status_code == 403
    db.rollback()


def test_immutable_execution_and_decision_survive_raw_mutation_attempts(electronic_case):
    request, _ = received(electronic_case)
    decide(electronic_case, request)
    b = electronic_case[0][1]
    for sql in ("UPDATE rfq_electronic_executions SET request_hash='changed'",
                "UPDATE rfq_electronic_executions SET state='REJECTED'",
                "DELETE FROM rfq_electronic_executions", "DELETE FROM rfq_electronic_evidence"):
        with pytest.raises(IntegrityError):
            b.execute(text(sql)); b.commit()
        b.rollback()


def test_concurrent_duplicate_transport_receipt_is_one_execution(electronic_case, tmp_path):
    case = electronic_case
    request, _ = ask(case)
    a, b, _, _, _, cid, _ = case[0]
    outbox = a.get(RfqTransportOutbox, request['transport']['message_id'])
    packet = transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', transport.wire_message(outbox))
    target = tmp_path / 'bank.db'
    b.commit()
    with sqlite3.connect(target) as copied:
        b.connection().connection.driver_connection.backup(copied)
    b.rollback()
    engine = create_engine('sqlite:///' + str(target), connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def pragmas(connection, _):
        connection.execute('PRAGMA foreign_keys=ON'); connection.execute('PRAGMA busy_timeout=5000')
    barrier = Barrier(2)
    def receive_once(_):
        with Session(engine) as db:
            barrier.wait()
            return transport.receive(db, packet)['body']['message']
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(receive_once, range(2)))
        assert first == second
        with Session(engine) as db:
            assert len(db.exec(select(RfqElectronicExecution)).all()) == 1
            assert len(db.exec(select(RfqTransportInbox).where(RfqTransportInbox.id == outbox.id)).all()) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize('field,value', [('price', 101), ('revision', 999), ('currency', 'USD'),
    ('terms_fingerprint', '0' * 64), ('nominal', 100), ('side', 'SELL')])
def test_modified_quote_is_rejected_as_business_fact(electronic_case, field, value):
    case = electronic_case
    result, _ = ask(case)
    a, b, _, _, _, cid, _ = case[0]
    row = a.get(RfqTransportOutbox, result['transport']['message_id'])
    message = transport.wire_message(row)
    message['payload']['quote'][field] = value
    message['payload_hash'] = exchange.digest(message['payload'])
    transport.receive(b, transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', message))
    entry = b.get(RfqElectronicExecution, result['id'])
    assert entry.state == 'REJECTED' and 'modifiée' in json.loads(entry.decision_json)['reason']
    assert not b.exec(select(Deal)).all()


@pytest.mark.parametrize('change', ['withdrawn', 'replaced', 'closed', 'relation'])
def test_changed_bank_context_cannot_be_confirmed_silently(electronic_case, change):
    case = electronic_case
    result, _ = ask(case)
    a, b, _, banker, _, _, _ = case[0]
    latest = b.exec(select(RfqQuotePublication).order_by(RfqQuotePublication.revision.desc())).first()
    if change == 'withdrawn':
        publication.withdraw(b, case[1], latest.id, banker, 'Retrait avant acceptation reçue')
    elif change == 'replaced':
        data = inbox.received_request(case[1], banker, b)
        draft = prepare(b, banker, case[1], data['case']['calculations'][-1]['id'],
                        revision=data['quote_draft']['revision'], firmness='FIRM', price=99)
        approved = inbox.validate_quote(case[1], decision(draft), banker, b)
        inbox.publish_quote(case[1], decision(approved), banker, b)
    elif change == 'closed':
        item = b.get(RfqSolicitation, case[1])
        round_row = b.get(transport.RfqExchangeRound, item.round_id)
        round_row.state = 'CLOSED'; b.add(round_row); b.commit()
    else:
        side = b.get(RfqRelationshipSide, (700, banker.entity_id))
        side.suspended = True; b.add(side); b.commit()
    flush(case[0], a, result['transport']['message_id'])
    b.expire_all()
    assert b.get(RfqElectronicExecution, result['id']).state == 'REJECTED'


def native_booking(case, bank_side=False):
    a, b, users, banker, rfq, _, _ = case[0]
    db, actor = (b, banker) if bank_side else (a, users[3])
    entry = db.exec(select(RfqElectronicExecution)).one()
    product = load_product(db, entry.product_id)
    if not bank_side:
        api.update_rfq(rfq['id'], api.RfqUpdate(pricing_params=context()), actor, db)
    effective = products.compose_product_pricing_input(product.product_id, products.ProductPricingInput(
        expected_terms_version=product.terms_version, context=context()), actor, db)
    priced = price_endpoint(PricingRequest(**effective))
    receipt = priced.pricing_receipt
    if not bank_side:
        api.update_rfq(rfq['id'], api.RfqUpdate(model_price=receipt['price_pct'], pricing_receipt=receipt), actor, db)
    terms = product.terms
    dates = terms.model_dump(mode='json')
    return deals.DealCreate(product_id=product.product_id, product_terms_version=product.terms_version,
        rfq_id=None if bank_side else rfq['id'], execution_agreement_id=entry.agreement_id,
        sens='achat' if bank_side else 'vente', counterparty_id=612 if bank_side else 1,
        contrepartie='ClientTech juridique' if bank_side else 'BNP juridique',
        devise='EUR', nominal=1000000, fair_value=receipt['price_pct'], price_traded=98.5,
        trade_date=dates['strike_date'], strike_date=dates['strike_date'], value_date=dates['value_date'],
        maturity_date=dates['maturity_date'], payment_date=dates['payment_date'], T=terms.T,
        underlyings=[u.model_dump(mode='json') for u in terms.underlyings], observation_times=[],
        script_snapshot=terms.script, market_snapshot=receipt['market_snapshot'], pricing_receipt=receipt,
        transaction_format=product.intent.transaction_format, instrument_family=product.intent.instrument_family,
        payoff_family=product.intent.payoff_family, documentation_reference=product.intent.documentation_reference)


def test_two_native_bookings_and_exact_replays_make_one_deal_per_local_leg(electronic_case):
    case = electronic_case
    request, _ = received(case)
    response = decide(case, request)
    flush(case[0], case[0][1], response['transport']['message_id'])
    a, b, users, banker, _, _, _ = case[0]
    for db, actor, bank_side in ((b, banker, True), (a, users[3], False)):
        body = native_booking(case, bank_side).model_dump(mode='json')
        first = deals.book_deal(deals.DealCreate(**body), actor, db)
        second = deals.book_deal(deals.DealCreate(**body), actor, db)
        assert first['id'] == second['id']
        assert len(db.exec(select(Deal)).all()) == 1
        assert len(db.exec(select(RfqElectronicBooking)).all()) == 1
        assert service.public_row(db, db.get(RfqElectronicExecution, request['id']))['booked_deal']['id'] == first['id']
    assert b.exec(select(Deal)).one().sens == 'achat' and a.exec(select(Deal)).one().sens == 'vente'


@pytest.mark.parametrize('bank_side', [True, False])
def test_pending_electronic_request_blocks_each_linked_local_booking(electronic_case, bank_side):
    case = electronic_case
    received(case)
    a, b, users, banker, _, _, _ = case[0]
    db, actor = (b, banker) if bank_side else (a, users[3])
    body = native_booking(case, bank_side)
    with pytest.raises(HTTPException) as exc:
        deals.book_deal(body, actor, db)
    assert exc.value.status_code == 409
    db.rollback()
    assert not db.exec(select(Deal)).all()


@pytest.mark.parametrize('field,value', [('price_traded', 99), ('nominal', 2000000), ('devise', 'USD'),
    ('sens', 'vente'), ('counterparty_id', 611), ('product_terms_version', 99)])
def test_bank_booking_cannot_change_the_confirmed_economics(electronic_case, field, value):
    case = electronic_case
    request, _ = received(case)
    decide(case, request)
    b = case[0][1]
    body = native_booking(case, True).model_copy(update={field: value})
    with pytest.raises(HTTPException) as exc:
        deals.book_deal(body, case[0][3], b)
    assert exc.value.status_code == 409
    b.rollback()
    assert not b.exec(select(Deal)).all()


@pytest.mark.parametrize('field,value', [('request_hash', '0' * 64), ('execution_id', str(uuid4())),
    ('received_at', '2099-01-01T00:00:00Z'), ('decided_at', '2099-01-01T00:00:00Z')])
def test_unbound_or_future_confirmation_cannot_confirm_local_agreement(electronic_case, field, value):
    case = electronic_case
    result, _ = received(case)
    answer = decide(case, result)
    a, b, _, _, _, cid, _ = case[0]
    message = transport.wire_message(b.get(RfqTransportOutbox, answer['transport']['message_id']))
    message['payload'][field] = value; message['payload_hash'] = exchange.digest(message['payload'])
    with pytest.raises(HTTPException) as exc:
        transport.receive(a, transport.envelope(b, b.get(RfqChannel, cid), 'DELIVER', message))
    assert exc.value.status_code in {409, 422}; a.rollback()
    assert a.exec(select(RfqExecutionAgreement)).one().state == 'REQUESTED'
    assert a.get(RfqElectronicExecution, result['id']).decision_json is None


def test_other_message_id_cannot_create_a_second_intention(electronic_case):
    case = electronic_case
    result, _ = received(case)
    a, b, _, _, _, cid, _ = case[0]
    original = a.get(RfqTransportOutbox, result['transport']['message_id'])
    message = transport.wire_message(original)
    message['id'] = str(uuid4()); message['sequence'] += 1
    with pytest.raises(HTTPException) as exc:
        transport.receive(b, transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', message))
    assert exc.value.status_code == 409; b.rollback()
    assert len(b.exec(select(RfqElectronicExecution)).all()) == 1


def test_revocation_before_delivery_blocks_without_inventing_a_bank_refusal(electronic_case):
    case = electronic_case
    result, _ = ask(case)
    a, b, users, _, _, _, _ = case[0]
    membership = a.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == users[3].id)).one()
    original = membership.rights_json
    membership.rights_json = '["read"]'; a.add(membership); a.commit()
    flush(case[0], a, result['transport']['message_id'])
    assert a.get(RfqTransportOutbox, result['transport']['message_id']).state == 'BLOCKED'
    b.expire_all(); assert not b.exec(select(RfqElectronicExecution)).all()
    membership.rights_json = original; a.add(membership); a.commit()
    transport_api.retry(result['transport']['message_id'], users[3], a)
    flush(case[0], a, result['transport']['message_id'])
    b.expire_all(); assert b.get(RfqElectronicExecution, result['id']).state == 'RECEIVED'


def test_bank_reception_time_cannot_be_backdated_while_decision_is_pending(electronic_case):
    result, _ = received(electronic_case)
    b = electronic_case[0][1]
    with pytest.raises(IntegrityError):
        b.execute(text("UPDATE rfq_electronic_executions SET received_at='2000-01-01'")); b.commit()
    b.rollback()
    assert b.get(RfqElectronicExecution, result['id']).state == 'RECEIVED'
