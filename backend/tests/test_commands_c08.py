"""C08: durable command retries and explicit execution lineage, with real FK checks."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import event, text
from fastapi import HTTPException

from backend.app.api import deals, products, rfq_inbox
from backend.app.db import models
from backend.app.db.product_migrations import migrate_product_links
from backend.app.services.product_repository import load_product
from backend.tests.test_business_permissions import access_case
from backend.tests.test_booking_legal_exception import exception_body
from backend.tests.test_products import _pricing_input
from backend.tests.test_rfq_bank_pricing import received_case
from backend.tests.test_rfq_relationships import network_case
from backend.tests.test_rfq_execution import execution_case, execution_context, request, confirm, booking_body


def direct_payload(**changes):
    body = exception_body().model_dump(mode='json')
    body.update(counterparty_id=1, contrepartie='BNP Paribas', legal_identity_exception=None)
    return {**body, **changes}


def test_lost_direct_booking_response_reuses_one_product_and_deal(access_case):
    session, users, login, _ = access_case
    payload = direct_payload(command_key='c08-direct-lost-response')
    first = login('superuser').post('/api/deals', json=payload)
    second = login('superuser').post('/api/deals', json=deepcopy(payload))
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert second.json()['id'] == first.json()['id']
    assert len(session.exec(select(models.Deal)).all()) == 1
    assert len(session.exec(select(models.ProductRecord)).all()) == 1


def test_other_trade_forks_a_clean_product_without_changing_source(access_case):
    session, users, login, _ = access_case
    booked = login('superuser').post('/api/deals', json=direct_payload())
    assert booked.status_code == 201, booked.text
    parent = load_product(session, booked.json()['product_id']).to_dict()
    payload = dict(command_key='c08-other-trade-explicit', expected_revision=parent['revision'],
        expected_terms_version=parent['terms_version'], reason='Autre opération depuis ce pricing')
    response = login('superuser').post(f"/api/products/{parent['product_id']}/booking-forks", json=payload)
    assert response.status_code == 201, response.text
    child = response.json()
    assert child['product_id'] != parent['product_id']
    assert child['origin_product_id'] == parent['product_id']
    assert child['terms'] == parent['terms']
    assert child['execution'] is None and child['lifecycle'] is None
    assert child['rfqs'] == child['indicatives'] == child['calculations'] == child['documents'] == []
    assert all(value is None for value in child['commercial'].values())
    assert load_product(session, parent['product_id']).to_dict() == parent
    replay = login('superuser').post(f"/api/products/{parent['product_id']}/booking-forks", json=payload)
    assert replay.status_code == 201 and replay.json() == child


@pytest.mark.parametrize('change', [{'nominal': 2_000_000}, {'price_traded': 97},
    {'contrepartie': 'Autre banque'}, {'market_snapshot': {'r': 99}}])
def test_same_booking_key_with_changed_content_is_an_audited_conflict(access_case, change):
    session, users, login, _ = access_case
    payload = direct_payload(command_key='c08-conflicting-command')
    first = login('superuser').post('/api/deals', json=payload)
    assert first.status_code == 201, first.text
    rejected = login('superuser').post('/api/deals', json={**payload, **change})
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'BOOKING_COMMAND_CONFLICT'
    assert len(session.exec(select(models.Deal)).all()) == 1
    assert session.exec(select(models.AuditEvent).where(models.AuditEvent.action == 'BOOKING_REJECTED')).all()


def test_legacy_exact_retry_is_safe_but_two_explicit_intentions_are_distinct(access_case):
    session, users, login, _ = access_case
    payload = direct_payload()
    ids = []
    for change in [{}, {}, {'command_key': 'c08-distinct-intent-one'}, {'command_key': 'c08-distinct-intent-two'}]:
        response = login('superuser').post('/api/deals', json={**payload, **change})
        assert response.status_code == 201, response.text
        ids.append(response.json()['id'])
    assert ids[0] == ids[1] and len(set(ids)) == 3
    assert len(session.exec(select(models.ProductRecord)).all()) == 3
    assert len(session.exec(select(models.BookingCommand)).all()) == 3


def test_retry_does_not_consume_limits_or_repeat_initial_audit_and_events(access_case, monkeypatch):
    session, users, login, _ = access_case
    payload = direct_payload(command_key='c08-retry-without-side-effects')
    first = login('superuser').post('/api/deals', json=payload)
    assert first.status_code == 201, first.text
    counts = {model: len(session.exec(select(model)).all()) for model in
        [models.Deal, models.ProductRecord, models.ProductRevision, models.ProductCalculationRun,
         models.DealContractVersion, models.DealEvent, models.AuditEvent]}
    from backend.app.core.ccr.service import enforce_booking
    def forbidden(*args, **kwargs): raise AssertionError('A replay must not run credit limits again')
    monkeypatch.setattr('backend.app.core.ccr.service.enforce_booking', forbidden)
    replay = login('superuser').post('/api/deals', json=deepcopy(payload))
    assert replay.status_code == 201 and replay.json()['id'] == first.json()['id']
    assert all(len(session.exec(select(model)).all()) == count for model, count in counts.items())
    monkeypatch.setattr('backend.app.core.ccr.service.enforce_booking', enforce_booking)
    # Permission is checked again before any lookup, including a known valid key.
    assert login('checker').post('/api/deals', json=payload).status_code == 403
    outsider = login('foreign').post('/api/deals', json=payload)
    assert outsider.status_code in [201, 401]
    if outsider.status_code == 201:
        assert outsider.json()['id'] != first.json()['id']


def test_failed_command_rolls_back_every_business_row_and_can_be_retried(access_case, monkeypatch):
    session, users, login, _ = access_case
    import backend.app.services.booking_commands as commands
    original = commands.stage_booking_command
    def fail(*args): raise RuntimeError('Simulated failure after all booking stages')
    monkeypatch.setattr(commands, 'stage_booking_command', fail)
    payload = direct_payload(command_key='c08-atomic-retry-after-failure')
    with pytest.raises(RuntimeError, match='Simulated failure'):
        login('superuser').post('/api/deals', json=payload)
    for model in [models.BookingCommand, models.Deal, models.ProductRecord,
                  models.ProductRevision, models.DealEvent, models.DealContractVersion]:
        assert not session.exec(select(model)).all()
    monkeypatch.setattr(commands, 'stage_booking_command', original)
    assert login('superuser').post('/api/deals', json=payload).status_code == 201


def test_fork_keeps_old_rfq_terms_pinned_and_cannot_declassify_its_source(access_case):
    session, users, login, _ = access_case
    made = login('front').post('/api/products', json={'command_key': 'c08-rfq-origin-creation',
        'pricing_input': _pricing_input()})
    assert made.status_code == 201, made.text
    parent_id = made.json()['product_id']
    tender = login('front').post('/api/rfq', json={'pilot_desk_id': 11,
        'product_id': parent_id, 'product_terms_version': 1, 'name': 'Pinned RFQ', 'kind': 'indicatif',
        'script_snapshot': 'Ignored: canonical Product terms are authoritative'})
    assert tender.status_code == 201, tender.text
    before = login('front').get(f'/api/products/{parent_id}').json()
    revised = login('front').post(f'/api/products/{parent_id}/terms', json={
        'command_key': 'c08-rfq-explicit-revision', 'expected_revision': before['revision'],
        'pricing_input': _pricing_input(script='AT MATURITY\n  PAY 0.8'), 'reason': 'Explicit v2 for this dossier'})
    assert revised.status_code == 200, revised.text
    retried_creation = login('front').post('/api/products', json={'command_key': 'c08-rfq-origin-creation',
        'pricing_input': _pricing_input()})
    assert retried_creation.status_code == 201 and retried_creation.json()['product_id'] == parent_id
    assert load_product(session, parent_id).terms_version == 2
    body = {'command_key': 'c08-fork-pinned-version-one', 'expected_revision': revised.json()['revision'],
        'expected_terms_version': 1, 'reason': 'Autre opération sur termes v1'}
    response = login('front').post(f'/api/products/{parent_id}/booking-forks', json=body)
    assert response.status_code == 201, response.text
    child = response.json()
    assert child['terms'] == before['terms'] and child['terms_version'] == 1 and child['rfqs'] == []
    assert load_product(session, parent_id).terms_version == 2
    assert session.get(models.RfqRequest, tender.json()['id']).product_terms_version == 1
    # A reader outside the source desk must not discover the copied script.
    assert login('outsider').get(f"/api/products/{child['product_id']}").status_code == 404
    assert login('outsider').post(f'/api/products/{parent_id}/booking-forks', json=body).status_code == 404
    event = session.exec(select(models.AuditEvent).where(
        models.AuditEvent.action == 'PRODUCT_BOOKING_LINEAGE_RECORDED')).one()
    assert json.loads(event.after_json)['origin_terms_version'] == 1
    assert json.loads(event.after_json)['detached_rfq_ids'] == [tender.json()['id']]
    position = models.Deal(reference='C08 inherited access', user_id=users['front'].id,
        entity_id=1, product_id=child['product_id'], product_terms_version=1,
        contrepartie='BNP Paribas', script_snapshot=child['terms']['script'])
    session.add(position); session.commit(); position_id = position.id
    assert login('outsider').get(f'/api/deals/{position_id}').status_code == 404
    assert login('ops').get(f'/api/deals/{position_id}').status_code == 200


def test_fork_refuses_stale_or_missing_terms_without_creating_a_dossier(access_case):
    session, users, login, _ = access_case
    response = login('front').post('/api/products', json={'command_key': 'c08-source-before-stale',
        'pricing_input': _pricing_input()})
    source = response.json()
    for changes in [{'expected_revision': 99}, {'expected_terms_version': 99}]:
        rejected = login('front').post(f"/api/products/{source['product_id']}/booking-forks", json={
            'command_key': uuid4().hex, 'expected_revision': source['revision'],
            'expected_terms_version': 1, 'reason': 'Autre opération explicitement voulue', **changes})
        assert rejected.status_code in [404, 409], rejected.text
    assert len(session.exec(select(models.ProductRecord)).all()) == 1


def test_a_fork_can_book_a_second_trade_and_preserves_the_original_archive(access_case):
    session, users, login, _ = access_case
    payload = direct_payload(command_key='c08-original-booking')
    original = login('superuser').post('/api/deals', json=payload).json()
    parent = load_product(session, original['product_id']).to_dict()
    child = login('superuser').post(f"/api/products/{parent['product_id']}/booking-forks", json={
        'command_key': 'c08-separate-new-trade', 'expected_revision': parent['revision'],
        'expected_terms_version': parent['terms_version'], 'reason': 'Seconde opération explicitement voulue'}).json()
    booked = login('superuser').post('/api/deals', json={**payload, 'command_key': 'c08-forked-booking',
        'product_id': child['product_id'], 'product_terms_version': 1})
    assert booked.status_code == 201, booked.text
    assert booked.json()['id'] != original['id'] and booked.json()['product_id'] == child['product_id']
    assert load_product(session, parent['product_id']).to_dict() == parent
    assert load_product(session, child['product_id']).origin_product_id == parent['product_id']
    assert len(session.exec(select(models.Deal)).all()) == 2


@pytest.fixture
def concurrent_db(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "commands.db"}',
        connect_args={'check_same_thread': False, 'timeout': 20})
    @event.listens_for(engine, 'connect')
    def fk(connection, record): connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        migrate_product_links(session.connection())
        session.add(models.Entity(id=1, name='C08 isolated entity')); session.flush()
        session.add_all([models.User(id=1, entity_id=1, role='organization_admin', username='c08',
            email='c08@example.test', password_hash='x'), models.Counterparty(id=1, name='BNP Paribas')])
        session.commit()
    monkeypatch.setattr('backend.app.hybrid.config.current_config', lambda: None)
    yield engine
    engine.dispose()


@pytest.mark.parametrize('operation', ['product', 'direct_booking'])
def test_concurrent_retries_commit_exactly_one_result(concurrent_db, operation):
    engine = concurrent_db
    barrier = Barrier(2)
    payload = direct_payload(command_key='c08-concurrent-intent') if operation == 'direct_booking' else {
        'command_key': 'c08-concurrent-intent', 'pricing_input': _pricing_input()}
    def run():
        with Session(engine) as session:
            user = session.get(models.User, 1)
            barrier.wait(timeout=10)
            if operation == 'direct_booking':
                return deals._book_deal(deals.DealCreate(**deepcopy(payload)), user, session)['id']
            return products.create_product(products.ProductCreate(**deepcopy(payload)), user, session)['product_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        ids = [future.result(timeout=30) for future in futures]
    assert ids[0] == ids[1]
    with Session(engine) as session:
        assert len(session.exec(select(models.ProductRecord)).all()) == 1
        if operation == 'direct_booking':
            assert len(session.exec(select(models.Deal)).all()) == 1
            assert len(session.exec(select(models.BookingCommand)).all()) == 1


def test_private_bank_calculation_cannot_be_forked_into_an_ordinary_product(received_case):
    session, users, _, item_id = received_case
    case = rfq_inbox.claim_request(item_id, users[1], session)['case']
    parent = load_product(session, case['product_id'])
    with pytest.raises(HTTPException) as error:
        products.fork_product_for_booking(parent.product_id, products.ProductBookingFork(
            command_key='c08-private-fork-refusal', expected_revision=parent.revision,
            expected_terms_version=1, reason='Autre opération depuis un calcul privé'), users[1], session)
    assert error.value.detail['code'] == 'PRODUCT_PRIVATE_FORK_FORBIDDEN'
    assert not session.exec(select(models.ProductRecord).where(
        models.ProductRecord.origin_product_id == parent.product_id)).all()


def test_agreement_replay_with_another_key_is_still_bound_to_the_same_result(execution_case):
    engine, tender, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session, tender, quote_id)
        agreement = confirm(session, tender, agreement, clock)
        payload = booking_body(tender, agreement).model_dump(mode='json')
        first = deals._book_deal(deals.DealCreate(**{**payload, 'command_key': 'c08-network-original'}),
            session.get(models.User, 1), session)
        replay = deals._book_deal(deals.DealCreate(**{**payload, 'command_key': 'c08-network-other-key'}),
            session.get(models.User, 1), session)
        assert replay['id'] == first['id']
        assert len(session.exec(select(models.BookingCommand)).all()) == 2
        with pytest.raises(HTTPException) as error:
            deals._book_deal(deals.DealCreate(**{**payload, 'command_key': 'c08-network-other-key',
                'price_traded': 97}), session.get(models.User, 1), session)
        assert error.value.detail['code'] == 'BOOKING_COMMAND_CONFLICT'


def test_uat_cleanup_keeps_filiation_in_batch_and_tombstones_successful_commands(concurrent_db):
    from backend.app.services.uat_generation import delete_batch
    with Session(concurrent_db) as session:
        session.add(models.UatGenerationBatch(id=42, batch_key='C08-isolated', created_by=1,
            target_user_id=1, mode='BOOKED_ONLY', seed=1, requested_count=1, status='COMPLETED'))
        session.commit()
        body = deals.DealCreate(**direct_payload(command_key='c08-deleted-uat-command'))
        parent_deal = deals._book_deal(body, session.get(models.User, 1), session, uat_batch_id=42)
        parent = load_product(session, parent_deal['product_id'])
        child = products.fork_product_for_booking(parent.product_id, products.ProductBookingFork(
            command_key='c08-uat-fork', expected_revision=parent.revision,
            expected_terms_version=1, reason='Autre opération de recette isolée'), session.get(models.User, 1), session)
        assert child['data_origin'] == 'uat'
        assert session.get(models.ProductRecord, child['product_id']).uat_batch_id == 42
        result = delete_batch(42, session.get(models.User, 1), session)
        assert result['deleted_products'] == 2 and result['deleted_deals'] == 1
        assert session.exec(select(models.BookingCommand)).one().deal_id is None
        with pytest.raises(HTTPException) as error:
            deals._book_deal(body, session.get(models.User, 1), session, uat_batch_id=42)
        assert error.value.detail['code'] == 'BOOKING_COMMAND_RESULT_MISSING'
        assert not session.exec(select(models.Deal)).all()


def test_failed_product_command_is_atomic_and_retryable(access_case, monkeypatch):
    session, users, login, _ = access_case
    original = products.stage_command
    def fail(*args): raise RuntimeError('Simulated command persistence failure')
    monkeypatch.setattr(products, 'stage_command', fail)
    payload = {'command_key': 'c08-product-atomic-failure', 'pricing_input': _pricing_input()}
    with pytest.raises(RuntimeError, match='persistence failure'):
        login('front').post('/api/products', json=payload)
    assert not session.exec(select(models.ProductRecord)).all()
    assert not session.exec(select(models.ProductCommand)).all()
    monkeypatch.setattr(products, 'stage_command', original)
    assert login('front').post('/api/products', json=payload).status_code == 201
