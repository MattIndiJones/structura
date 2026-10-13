"""Lot 3: real persistent delivery, frozen terms and desk-only bank access."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import select

from backend.app.api import rfq as api, rfq_inbox as inbox
from backend.app.db.models import RfqDeskMembership, RfqSendCommand, RfqSolicitation, AuditEvent
from backend.app.services import rfq_exchange as exchange, rfq_relationships as relationships
from backend.tests.test_rfq_relationships import network_case, active, preview, terms


def send_body(session, users, rfq, relation):
    body = preview(rfq, [relation['id']])
    packet = api.preview_rfq_exchange(rfq['id'], body, users[3], session)
    return api.RfqExchangeSend(**body.model_dump(), command_key=str(uuid4()), expected_preview_hash=packet['preview_hash'])


def bank_member(session, users):
    session.add(RfqDeskMembership(desk_id=21, user_id=users[1].id, rights_json='["read"]'))
    session.commit()


def test_actual_delivery_read_receipt_and_same_command_replay(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    bank_member(session, users)
    body = send_body(session, users, rfq, relation)
    sent = api.send_rfq_exchange(rfq['id'], body, users[3], session)
    assert len(sent['solicitation_ids']) == 1
    assert api.get_rfq(rfq['id'], users[3], session)['status'] == 'envoye'
    row = inbox.list_received(users[1], session)[0]
    assert row['delivery_status'] == 'DELIVERED' and row['read_at'] is None
    request = inbox.received_request(row['id'], users[1], session)['request']
    assert request['terms_fingerprint'] == sent['tracking']['round']['terms_fingerprint']
    assert request['requester']['organization'] == 'ClientTech'
    assert request['recipient']['organization'] == 'BNP'
    assert request['message_id'] and request['published_at'].endswith('Z')
    assert 'model_price' not in json.dumps(request) and 'corr_matrix' not in json.dumps(request)
    assert 'sigma' not in json.dumps(request) and 'client_id' not in json.dumps(request)
    assert inbox.received_request(row['id'], users[1], session)['read_at'] is None
    first = inbox.acknowledge_read(row['id'], users[1], session)
    assert first['delivery_status'] == 'READ'
    assert inbox.acknowledge_read(row['id'], users[1], session)['read_at'] == first['read_at']
    replay = api.send_rfq_exchange(rfq['id'], body, users[3], session)
    assert replay['replayed'] and replay['solicitation_ids'] == sent['solicitation_ids']
    assert len(session.exec(select(RfqSolicitation)).all()) == 1
    assert len(session.exec(select(AuditEvent).where(AuditEvent.action == 'RFQ_REQUEST_READ')).all()) == 1


def test_admin_without_desk_and_foreign_org_cannot_read_inbox(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    sent = api.send_rfq_exchange(rfq['id'], send_body(session, users, rfq, relation), users[3], session)
    for user in users:
        assert inbox.list_received(user, session) == []
        with pytest.raises(HTTPException) as err:
            inbox.received_request(sent['solicitation_ids'][0], user, session)
        assert err.value.status_code == 404


def test_send_rechecks_relation_and_preview_after_preparation(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    body = send_body(session, users, rfq, relation)
    relationships.suspend_relation(session, relation['id'], users[1], relationships.RelationshipSuspension(
        expected_version=relation['version'], suspended=True, reason='Suspension de contrôle'))
    with pytest.raises(HTTPException) as err:
        api.send_rfq_exchange(rfq['id'], body, users[3], session)
    assert err.value.status_code == 422
    session.rollback()
    assert exchange.round_for(session, rfq['id']) is None
    assert session.exec(select(RfqSolicitation)).all() == []


def test_stale_request_cannot_be_sent_and_key_cannot_change_content(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    body = send_body(session, users, rfq, relation)
    stale = body.model_copy(update={'shared_title': 'Contenu modifié après aperçu'})
    with pytest.raises(HTTPException) as err:
        api.send_rfq_exchange(rfq['id'], stale, users[3], session)
    assert err.value.status_code == 409
    session.rollback()
    api.send_rfq_exchange(rfq['id'], body, users[3], session)
    with pytest.raises(HTTPException) as err:
        api.send_rfq_exchange(rfq['id'], stale, users[3], session)
    assert err.value.status_code == 409
    assert len(session.exec(select(RfqSendCommand)).all()) == 1


def test_network_freeze_blocks_material_edits_but_allows_private_pricing(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    api.send_rfq_exchange(rfq['id'], send_body(session, users, rfq, relation), users[3], session)
    for body in [api.RfqUpdate(sens='vente'), api.RfqUpdate(transaction_format='OTC'),
                 api.RfqUpdate(params={**rfq['params'], 'notional': 2_000_000})]:
        with pytest.raises(HTTPException) as err:
            api.update_rfq(rfq['id'], body, users[3], session)
        assert err.value.status_code == 409
        session.rollback()
    before = exchange.tracking(session, rfq['id'])['round']['request']
    api.update_rfq(rfq['id'], api.RfqUpdate(pricing_params={'r': 0.08}), users[3], session)
    assert exchange.tracking(session, rfq['id'])['round']['request'] == before


def test_new_round_links_previous_without_moving_quotes_or_messages(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    sent = api.send_rfq_exchange(rfq['id'], send_body(session, users, rfq, relation), users[3], session)
    api.add_quote(rfq['id'], api.QuoteCreate(provider='Banque manuelle'), users[3], session)
    new = api.create_rfq(api.RfqCreate(previous_round_id=sent['round_id'], pilot_desk_id=11,
        name='Nouveau tour', script_snapshot=rfq['script_snapshot'], params={**rfq['params'], 'notional': 2_000_000},
        transaction_format='EMTN', instrument_family='Note', payoff_family='Autocall'), users[3], session)
    result = api.send_rfq_exchange(new['id'], send_body(session, users, new, relation), users[3], session)
    assert result['tracking']['round']['number'] == 2
    assert result['tracking']['round']['previous_round_id'] == sent['round_id']
    assert exchange.round_for(session, rfq['id']).state == 'SUPERSEDED'
    assert api.get_rfq(new['id'], users[3], session)['quotes'] == []
    assert len(exchange.tracking(session, rfq['id'])['deliveries']) == 1
    with pytest.raises(HTTPException):
        api.send_rfq_exchange(rfq['id'], send_body(session, users, rfq, relation), users[3], session)


def test_manual_solicitation_freezes_terms_even_after_quote_deletion(network_case):
    session, users, rfq = network_case
    q = api.add_quote(rfq['id'], api.QuoteCreate(provider='Banque manuelle'), users[3], session)
    assert exchange.round_for(session, rfq['id'])
    api.delete_quote(rfq['id'], q['id'], users[3], session)
    assert api.get_rfq(rfq['id'], users[3], session)['status'] == 'envoye'
    with pytest.raises(HTTPException) as err:
        api.update_rfq(rfq['id'], api.RfqUpdate(sens='vente'), users[3], session)
    assert err.value.status_code == 409


def test_duplicate_organization_not_resent_under_fresh_key(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    body = send_body(session, users, rfq, relation)
    api.send_rfq_exchange(rfq['id'], body, users[3], session)
    with pytest.raises(HTTPException) as err:
        api.send_rfq_exchange(rfq['id'], body.model_copy(update={'command_key': str(uuid4())}), users[3], session)
    assert err.value.status_code == 409
    session.rollback()
    assert len(session.exec(select(RfqSolicitation)).all()) == 1


def test_extra_recipient_gets_same_frozen_request_without_competitor_identity(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    body = send_body(session, users, rfq, relation)
    first = api.send_rfq_exchange(rfq['id'], body, users[3], session)
    other = relationships.create_relation(session, users[0], relationships.RelationshipCreate(
        partner_entity_id=3, receiver_desk_id=31, reference='CLIENT-CITI', counterparty_id=1,
        terms=terms(), reason='Deuxième partenaire fictif'))
    other = relationships.update_relation(session, other['id'], users[2], relationships.RelationshipUpdate(
        expected_version=other['version'], receiver_desk_id=31, counterparty_id=2,
        terms=terms(), reason='Mapping de recette fictif'))
    for user in [users[0], users[2]]:
        relationships.recognize_relation(session, other['id'], user, relationships.RelationshipDecision(
            expected_version=other['version'], reason='Reconnaissance fictive'))
    prepared = api.RfqExchangePreview(**{**body.model_dump(), 'relationship_ids': [other['id']]})
    packet = api.preview_rfq_exchange(rfq['id'], prepared, users[3], session)
    result = api.send_rfq_exchange(rfq['id'], api.RfqExchangeSend(**prepared.model_dump(),
        command_key=str(uuid4()), expected_preview_hash=packet['preview_hash']), users[3], session)
    assert result['round_id'] == first['round_id'] and len(result['tracking']['deliveries']) == 2
    messages = session.exec(select(RfqSolicitation).order_by(RfqSolicitation.id)).all()
    requests = [json.loads(item.request_json) for item in messages]
    common = [{key: value for key, value in item.items() if key not in {'recipient', 'message_id', 'published_at'}} for item in requests]
    assert common[0] == common[1]
    assert 'Citi' not in json.dumps(requests[0]) and 'BNP' not in json.dumps(requests[1])
