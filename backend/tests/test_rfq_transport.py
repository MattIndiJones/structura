"""Two independent installations, authenticated HTTP, recovery and business isolation."""
import json
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import rfq as api, rfq_inbox as inbox, rfq_transport as transport_api, products as products_api
from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import (Counterparty, Entity, ProductRecord, RfqChannel, RfqDesk, RfqDeskMembership,
    RfqExchangeRound, RfqInstallation, RfqQuote, RfqQuotePublication, RfqRelationship, RfqRelationshipSide, RfqBankPublicationPolicy,
    RfqRemoteLink, RfqRequest, RfqSolicitation, RfqTransportInbox, RfqTransportOutbox, User)
from backend.app.services import rfq_exchange as exchange, rfq_transport as transport, rfq_publication as publication
from backend.app.services.product_repository import load_product, owned_record, ProductError
from backend.tests.test_rfq_relationships import network_case, active, terms
from backend.tests.test_rfq_network_delivery import send_body
from backend.tests.test_rfq_bank_pricing import context
from backend.tests.test_rfq_bank_publication import policy, prepare, decision


@pytest.fixture
def paired(network_case):
    requester, users, rfq = network_case
    relation = active(requester, users)
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as bank:
        bank.add_all([Entity(id=101, name='ClientTech'), Entity(id=202, name='BNP')]); bank.flush()
        banker = User(id=502, username='bank-local', email='bank@example.test', password_hash='x', entity_id=202, role='admin')
        bank.add(banker); bank.flush()
        bank.add(RfqDesk(id=721, entity_id=202, name='Pricing'))
        bank.add_all([Counterparty(id=611, name='BNP juridique'), Counterparty(id=612, name='ClientTech juridique')])
        bank.flush()
        bank.add(RfqDeskMembership(desk_id=721, user_id=502,
            rights_json='["read","prepare","price","organize","validate_quote","publish_quote"]'))
        bank.add(RfqRelationship(id=700, requester_entity_id=101, partner_entity_id=202, receiver_desk_id=721,
            reference='LOCAL-BANK-CLIENT', version=4, terms_json=terms().model_dump_json(), created_by=502)); bank.flush()
        bank.add_all([RfqRelationshipSide(relationship_id=700, entity_id=101, counterparty_id=611, updated_by=502),
            RfqRelationshipSide(relationship_id=700, entity_id=202, counterparty_id=612, recognized_version=4, updated_by=502)])
        bank.commit()
        local_id = transport.identity(requester); requester.commit()
        remote_id = transport.identity(bank); bank.commit()
        a = transport_api.configure(transport_api.ChannelCreate(relationship_id=relation['id'], expected_version=2,
            role='REQUESTER', peer_installation_id=remote_id, peer_url='https://bank.test', peer_counterparty_id=2,
            reason='Appairage de recette'), users[0], requester)
        b = transport_api.configure(transport_api.ChannelCreate(relationship_id=700, expected_version=4,
            role='BANK', peer_installation_id=local_id, peer_url='https://requester.test', peer_counterparty_id=611,
            channel_id=a['id'], secret=a['pairing']['secret'], reason='Appairage de recette'), banker, bank)
        def handler(request):
            target = bank if request.url.host == 'bank.test' else requester
            try:
                value = transport.receive(target, json.loads(request.content))
                return httpx.Response(200, json=value)
            except HTTPException as exc:
                target.rollback()
                return httpx.Response(exc.status_code, json={'detail': exc.detail})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            transport.probe(requester, requester.get(RfqChannel, a['id']), client)
            yield requester, bank, users, banker, rfq, a['id'], client
    engine.dispose()


def send(case):
    requester, bank, users, banker, rfq, channel_id, client = case
    relation = requester.get(RfqChannel, channel_id).relationship_id
    sent = api.send_rfq_exchange(rfq['id'], send_body(requester, users, rfq, {'id': relation}), users[3], requester)
    item = requester.get(RfqSolicitation, sent['solicitation_ids'][0])
    return item.message_id, item.id


def flush(case, source, message_id):
    transport.deliver_one(source.get_bind(), message_id, case[-1])
    source.expire_all()


def delivered(case):
    message_id, item_id = send(case)
    flush(case, case[0], message_id)
    bank = case[1]
    bank.expire_all()
    remote = bank.exec(select(RfqSolicitation).where(RfqSolicitation.message_id == message_id)).one()
    return message_id, item_id, remote.id


def published(case):
    requester, bank, users, banker, rfq, channel_id, client = case
    _, _, item_id = delivered(case)
    inbox.acknowledge_read(item_id, banker, bank)
    read = bank.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'READ')).one()
    flush(case, bank, read.id)
    product_id = inbox.claim_request(item_id, banker, bank)['case']['product_id']
    product = load_product(bank, product_id)
    pricing_input = products_api.compose_product_pricing_input(product_id, products_api.ProductPricingInput(
        expected_terms_version=1, context=context()), banker, bank)
    computed = price_endpoint(PricingRequest(**pricing_input))
    saved = products_api.retain_product_calculation(product_id, products_api.ProductCalculationCreate(
        command_key=str(uuid4()), expected_revision=product.revision, pricing_receipt=computed.pricing_receipt), banker, bank)
    policy(bank, banker, item_id)
    draft = prepare(bank, banker, item_id, saved['calculations'][-1]['id'])
    approved = inbox.validate_quote(item_id, decision(draft), banker, bank)
    result = inbox.publish_quote(item_id, decision(approved), banker, bank)
    return item_id, result['publications'][0]


def test_pairing_recognizes_exact_agreement_without_leaking_key(paired):
    a, b, users, banker, _, cid, _ = paired
    assert a.get(RfqChannel, cid).confirmed_at and b.get(RfqChannel, cid).confirmed_at
    assert b.get(RfqRelationshipSide, (700, 101)).recognized_version == 4
    public = transport_api.channels(users[0], a)
    assert 'secret' not in json.dumps(public) and 'password' not in json.dumps(public)


def test_remote_delivery_uses_local_ids_and_private_projection(paired):
    a, b, users, banker, rfq, cid, _ = paired
    mid, local_id = send(paired)
    assert api.rfq_exchange_tracking(rfq['id'], users[3], a)['deliveries'][0]['delivered_at'] is None
    assert inbox.list_received(users[1], a) == []  # outbound remote peer is not a local inbox
    flush(paired, a, mid)
    remote = b.exec(select(RfqSolicitation)).one()
    assert remote.recipient_entity_id == 202 and remote.recipient_desk_id == 721 and remote.relationship_id == 700
    request = json.loads(remote.request_json)
    assert request['requester']['organization_id'] == 101
    assert request['terms_fingerprint'] == json.loads(a.get(RfqSolicitation, local_id).request_json)['terms_fingerprint']
    assert api.list_rfqs(banker, b) == []
    projection = b.get(ProductRecord, b.get(RfqExchangeRound, remote.round_id).product_id)
    with pytest.raises(ProductError): owned_record(b, projection.id, banker)
    assert not b.get(User, projection.user_id).is_active
    from backend.app.db.database import _verify_pw
    assert not _verify_pw('any-public-password', b.get(User, projection.user_id).password_hash)
    assert api.rfq_exchange_tracking(rfq['id'], users[3], a)['deliveries'][0]['delivery_status'] == 'DELIVERED'


def test_duplicate_request_and_conflicting_payload(paired):
    a, b, _, _, _, cid, _ = paired
    mid, _, _ = delivered(paired)
    row = a.get(RfqTransportOutbox, mid)
    msg = transport.wire_message(row)
    packet = transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', msg)
    first = transport.receive(b, packet)
    second = transport.receive(b, packet)
    assert first['body']['message'] == second['body']['message']
    assert len(b.exec(select(RfqSolicitation)).all()) == 1
    msg['payload']['nominal'] += 1
    msg['payload_hash'] = exchange.digest(msg['payload'])
    with pytest.raises(HTTPException) as error:
        transport.receive(b, transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', msg))
    assert error.value.status_code == 409
    b.rollback()


def test_signature_address_and_stale_envelope_rejected(paired):
    a, b, _, _, _, cid, _ = paired
    channel = a.get(RfqChannel, cid)
    for key, value in [('sender', str(uuid4())), ('receiver', str(uuid4())), ('issued_at', '2000-01-01T00:00:00Z')]:
        packet = transport.envelope(a, channel, 'STATUS', {'id': str(uuid4()), 'payload_hash': 'x'})
        packet['body'][key] = value; packet['signature'] = transport.signature(channel, packet['body'])
        with pytest.raises(HTTPException) as error: transport.receive(b, packet)
        assert error.value.status_code == 401
        b.rollback()
    packet['signature'] = '0' * 64
    with pytest.raises(HTTPException): transport.receive(b, packet)


def test_lost_receipt_recovered_after_worker_restart_without_second_request(paired):
    a, b, _, _, _, cid, client = paired
    mid, _ = send(paired)
    def lost_ack(request):
        receipt = client.post(str(request.url), json=json.loads(request.content))
        receipt.raise_for_status()
        raise httpx.ReadError('receipt lost', request=request)
    with httpx.Client(transport=httpx.MockTransport(lost_ack)) as interrupted:
        transport.deliver_one(a.get_bind(), mid, interrupted)
    a.expire_all()
    assert a.get(RfqTransportOutbox, mid).state == 'RETRY'
    assert len(b.exec(select(RfqSolicitation)).all()) == 1
    # Revocation after actual reception must not erase an existing receipt or repeat the action.
    membership = a.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == paired[2][3].id)).one()
    membership.rights_json = '["read"]'; a.add(membership); a.commit()
    row = a.get(RfqTransportOutbox, mid); row.next_attempt_at = datetime.utcnow()-timedelta(seconds=1); a.add(row); a.commit()
    flush(paired, a, mid)
    assert a.get(RfqTransportOutbox, mid).state == 'DELIVERED'
    assert a.get(RfqTransportOutbox, mid).attempts == 2
    assert len(b.exec(select(RfqSolicitation)).all()) == 1


def test_revoked_sender_rights_prevent_first_delivery(paired):
    a, b, users, _, _, _, _ = paired
    mid, _ = send(paired)
    membership = a.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == users[3].id)).one()
    membership.rights_json = '["read"]'; a.add(membership); a.commit()
    flush(paired, a, mid)
    assert a.get(RfqTransportOutbox, mid).state == 'BLOCKED'
    assert b.exec(select(RfqSolicitation)).all() == []


def test_closed_unsent_request_is_cancelled_without_disclosing_terms(paired):
    a, b, _, _, rfq, _, _ = paired
    mid, _ = send(paired)
    row = a.get(RfqRequest, rfq['id']); row.status = 'sans_suite'; a.add(row); a.commit()
    flush(paired, a, mid)
    assert a.get(RfqTransportOutbox, mid).state == 'CANCELLED'
    assert b.exec(select(RfqSolicitation)).all() == []
    receipt = b.get(RfqTransportInbox, mid)
    assert json.loads(receipt.payload_json)['payload'] is None
    transport.reconcile_closures(a)
    close = a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'CLOSE')).one()
    flush(paired, a, close.id)
    assert a.get(RfqTransportOutbox, close.id).state == 'CANCELLED'


def test_out_of_order_messages_are_not_applied(paired):
    a, b, _, _, _, cid, _ = paired
    mid, _, _ = delivered(paired)
    msg = {'id': str(uuid4()), 'request_id': mid, 'sequence': 3, 'kind': 'CLOSE',
        'payload': {'state': 'CLOSED'}, 'payload_hash': exchange.digest({'state': 'CLOSED'})}
    with pytest.raises(HTTPException) as error:
        transport.receive(b, transport.envelope(a, a.get(RfqChannel, cid), 'DELIVER', msg))
    assert error.value.status_code == 409
    b.rollback()
    assert b.exec(select(RfqExchangeRound)).one().state == 'OPEN'


def test_quote_publication_returns_automatically_and_withdrawal_is_ordered(paired):
    a, b, users, banker, rfq, _, _ = paired
    item_id, published_row = published(paired)
    assert published_row['state'] == 'PENDING_DELIVERY' and published_row['received_at'] is None
    assert api.get_rfq(rfq['id'], users[3], a)['quotes'] == []
    mid = published_row['response']['message_id']
    flush(paired, b, mid)
    a.expire_all()
    q = api.get_rfq(rfq['id'], users[3], a)['quotes'][0]
    assert q['origin'] == 'NETWORK' and q['price'] == 98.5 and q['comparable']
    assert 'calculation_id' not in json.dumps(transport.wire_message(b.get(RfqTransportOutbox, mid)))
    assert a.exec(select(RfqSolicitation)).one().read_at
    inbox.withdraw_quote(item_id, inbox.Withdrawal(publication_id=published_row['id'], reason='Prix retiré explicitement'), banker, b)
    withdrawal = b.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'WITHDRAW')).one()
    flush(paired, b, withdrawal.id)
    a.expire_all()
    assert api.get_rfq(rfq['id'], users[3], a)['quotes'][0]['publication']['state'] == 'WITHDRAWN'
    assert len(a.exec(select(RfqQuote)).all()) == 1


def test_stale_calculation_during_interruption_returns_history_only(paired):
    a, b, users, _, rfq, _, _ = paired
    _, published_row = published(paired)
    policy_row = b.exec(select(RfqBankPublicationPolicy)).one()
    policy_row.version += 1; b.add(policy_row); b.commit()
    flush(paired, b, published_row['response']['message_id'])
    a.expire_all()
    q = api.get_rfq(rfq['id'], users[3], a)['quotes'][0]
    assert q['publication']['state'] == 'HISTORY' and not q['comparable']


def test_closure_after_delivery_reaches_bank_and_blocks_pricing(paired):
    a, b, _, banker, rfq, _, _ = paired
    _, _, remote_id = delivered(paired)
    row = a.get(RfqRequest, rfq['id']); row.status = 'sans_suite'; a.add(row); a.commit()
    transport.reconcile_closures(a)
    close = a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'CLOSE')).one()
    flush(paired, a, close.id); b.expire_all()
    assert not inbox.received_request(remote_id, banker, b)['open_for_work']
    with pytest.raises(HTTPException): inbox.claim_request(remote_id, banker, b)


def test_https_and_redirect_policy(monkeypatch):
    for url in ['http://bank.test', 'https://user:pass@bank.test', 'https://bank.test/path', 'https://bank.test?x=1',
            'https://[', 'https://bank.test:0', 'https://bank.test:wrong']:
        with pytest.raises(HTTPException): transport.endpoint(url)
    monkeypatch.setenv('STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP', '1')
    assert transport.endpoint('http://127.0.0.1:8039') == 'http://127.0.0.1:8039'
    with pytest.raises(HTTPException): transport.endpoint('http://10.0.0.1:8039')


def test_wire_request_excludes_local_ids_and_private_fields(paired):
    mid, _ = send(paired)
    row = paired[0].get(RfqTransportOutbox, mid)
    payload = json.loads(row.payload_json)
    assert not {'organization_id', 'desk_id'} & payload['requester'].keys()
    assert set(payload['recipient']) == {'organization', 'desk'}
    assert 'previous_round_id' not in payload and 'model_price' not in payload
    message = transport.wire_message(row)
    message['payload']['model_price'] = 100
    message['payload_hash'] = exchange.digest(message['payload'])
    with pytest.raises(HTTPException) as error:
        transport.receive(paired[1], transport.envelope(paired[0], paired[0].get(RfqChannel, paired[5]), 'DELIVER', message))
    assert error.value.status_code == 422
    paired[1].rollback()
    assert paired[1].exec(select(RfqSolicitation)).all() == []


def test_withdrawal_still_delivered_after_relationship_suspension(paired):
    a, b, users, banker, rfq, _, _ = paired
    item_id, reply = published(paired)
    flush(paired, b, reply['response']['message_id'])
    a.expire_all()
    for session, entity in [(a, 1), (b, 202)]:
        channel = session.get(RfqChannel, paired[5])
        side = session.get(RfqRelationshipSide, (channel.relationship_id, entity))
        side.suspended = True; session.add(side); session.commit()
    inbox.withdraw_quote(item_id, inbox.Withdrawal(publication_id=reply['id'], reason='Retrait protecteur après suspension'), banker, b)
    withdrawal = b.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'WITHDRAW')).one()
    flush(paired, b, withdrawal.id)
    a.expire_all()
    assert api.get_rfq(rfq['id'], users[3], a)['quotes'][0]['publication']['state'] == 'WITHDRAWN'


def test_withdrawn_unsent_quote_is_cancelled_then_stream_continues(paired):
    a, b, users, banker, rfq, _, _ = paired
    item_id, reply = published(paired)
    inbox.withdraw_quote(item_id, inbox.Withdrawal(publication_id=reply['id'], reason='Retrait avant livraison'), banker, b)
    flush(paired, b, reply['response']['message_id'])
    assert b.get(RfqTransportOutbox, reply['response']['message_id']).state == 'CANCELLED'
    withdrawal = b.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'WITHDRAW')).one()
    flush(paired, b, withdrawal.id)
    a.expire_all()
    assert b.get(RfqTransportOutbox, withdrawal.id).state == 'CANCELLED'
    assert api.get_rfq(rfq['id'], users[3], a)['quotes'] == []


def test_immutable_outbox_and_receipts_allow_worker_state_updates(paired):
    from backend.app.db.rfq_transport_integrity import install_transport_guards
    a, b = paired[:2]
    install_transport_guards(a.get_bind()); install_transport_guards(b.get_bind())
    mid, _, _ = delivered(paired)
    assert a.get(RfqTransportOutbox, mid).signed_receipt_json
    for session, command in [(a, 'UPDATE rfq_transport_outbox SET payload_json = payload_json'),
            (a, 'UPDATE rfq_transport_outbox SET receipt_json = receipt_json'),
            (b, 'DELETE FROM rfq_transport_inbox')]:
        with pytest.raises(IntegrityError): session.execute(text(command))
        session.rollback()


def test_parallel_duplicate_receipts_create_one_bank_dossier(paired, tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    a, b = paired[:2]
    mid, _ = send(paired)
    target = tmp_path/'bank.db'
    with b.get_bind().connect() as connection, sqlite3.connect(target) as disk:
        connection.connection.driver_connection.backup(disk)
    disk_engine = create_engine(f'sqlite:///{target}', connect_args={'check_same_thread': False, 'timeout': 10})
    packet = transport.envelope(a, a.get(RfqChannel, paired[5]), 'DELIVER', transport.wire_message(a.get(RfqTransportOutbox, mid)))
    def receive(_):
        with Session(disk_engine) as session:
            return transport.receive(session, packet)['body']['message']
    with ThreadPoolExecutor(max_workers=4) as workers:
        receipts = list(workers.map(receive, range(4)))
    assert all(receipt == receipts[0] for receipt in receipts)
    with Session(disk_engine) as session:
        assert len(session.exec(select(RfqSolicitation)).all()) == 1
        assert len(session.exec(select(RfqTransportInbox)).all()) == 1
    disk_engine.dispose()


def test_active_lease_prevents_second_worker_and_expired_lease_resumes(paired):
    a, b = paired[:2]
    mid, _ = send(paired)
    row = a.get(RfqTransportOutbox, mid)
    row.lease_until = datetime.utcnow()+timedelta(seconds=45)
    row.lease_token = str(uuid4()); a.add(row); a.commit()
    flush(paired, a, mid)
    assert a.get(RfqTransportOutbox, mid).attempts == 0
    assert b.exec(select(RfqSolicitation)).all() == []
    row.lease_until = datetime.utcnow()-timedelta(seconds=1); a.add(row); a.commit()
    flush(paired, a, mid)
    assert a.get(RfqTransportOutbox, mid).state == 'DELIVERED'
    assert len(b.exec(select(RfqSolicitation)).all()) == 1
