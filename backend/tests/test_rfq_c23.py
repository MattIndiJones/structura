"""C23 quote revisions and irreversible rounds on isolated FK-enforced databases."""
from datetime import datetime, timedelta
import json

import pytest
from fastapi import HTTPException
from sqlmodel import select

from backend.app.api import rfq as api
from backend.app.db.models import AuditEvent, RfqChannel, RfqDeskMembership, RfqExchangeRound, RfqQuote, RfqQuotePublication, RfqRequest, RfqTransportOutbox
from backend.app.services import rfq_exchange as exchange, rfq_transport as transport
from backend.tests.test_rfq_relationships import network_case
from backend.tests.test_rfq_transport import paired, published, flush
from backend.tests.test_rfq_network_delivery import send_body


@pytest.fixture(autouse=True)
def explicit_selection_right(network_case):
    session, users, _ = network_case
    member = session.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.desk_id == 11, RfqDeskMembership.user_id == users[3].id)).one()
    member.rights_json = json.dumps(sorted(set(json.loads(member.rights_json)) | {'select', 'book'}))
    session.add(member)
    session.commit()


def manual(case, **values):
    session, users, rfq = case
    q = api.add_quote(rfq['id'], api.QuoteCreate(provider='Manual bank'), users[3], session)
    return api.update_quote(rfq['id'], q['id'], api.QuoteUpdate(price=99, **values), users[3], session)


def select_quote(case, quote):
    session, users, rfq = case
    return api.update_rfq(rfq['id'], api.RfqUpdate(selected_quote_id=quote['id'],
        selection_reason_code='price', selection_reason_note='Décision explicite'), users[3], session)


def test_price_revision_invalidates_decision_and_preserves_audit(network_case):
    s, users, r = network_case
    q = manual(network_case)
    selected = select_quote(network_case, q)
    changed = api.update_quote(r['id'], q['id'], api.QuoteUpdate(price=98), users[3], s)
    current = api.get_rfq(r['id'], users[3], s)
    assert current['selected_quote_id'] is None
    assert current['selection_reason_code'] is None and current['selection_reason_note'] is None
    assert changed['revision'] == q['revision'] + 1
    assert selected['selected_quote_revision'] == q['revision']
    audit = s.exec(select(AuditEvent).where(AuditEvent.action == 'QUOTE_UPDATED')).all()[-1]
    assert json.loads(audit.before_json)['price'] == 99
    assert json.loads(audit.after_json)['price'] == 98


@pytest.mark.parametrize('currency', [None, '', ' eur ', 'USD'])
def test_currency_is_explicit_and_mismatch_cannot_be_selected(network_case, currency):
    s, users, r = network_case
    q = manual(network_case, currency=currency)
    assert q['currency'] == ('USD' if currency == 'USD' else 'EUR')
    assert q['comparable'] == (currency != 'USD')
    if currency == 'USD':
        with pytest.raises(HTTPException) as failure:
            select_quote(network_case, q)
        assert failure.value.status_code == 422
    else:
        assert select_quote(network_case, q)['selected_quote_id'] == q['id']


def test_quoted_at_only_patch_validates_merged_times(network_case):
    s, users, r = network_case
    now = datetime.utcnow()
    q = manual(network_case, quoted_at=now.isoformat(), valid_until=(now+timedelta(hours=1)).isoformat())
    with pytest.raises(HTTPException) as failure:
        api.update_quote(r['id'], q['id'], api.QuoteUpdate(quoted_at=(now+timedelta(hours=2)).isoformat()), users[3], s)
    assert failure.value.status_code == 422
    s.rollback()
    assert s.get(RfqQuote, q['id']).quoted_at == now


def test_improved_parent_retires_last_look_and_its_decision(network_case):
    s, users, r = network_case
    parent = manual(network_case)
    api.update_quote(r['id'], parent['id'], api.QuoteUpdate(last_look=True), users[3], s)
    child = next(q for q in api.get_rfq(r['id'], users[3], s)['quotes'] if q['parent_quote_id'])
    child = api.update_quote(r['id'], child['id'], api.QuoteUpdate(price=98), users[3], s)
    select_quote(network_case, child)
    api.update_quote(r['id'], parent['id'], api.QuoteUpdate(price=97), users[3], s)
    current = api.get_rfq(r['id'], users[3], s)
    assert current['selected_quote_id'] is None
    old = next(q for q in current['quotes'] if q['id'] == child['id'])
    assert old['status'] == 'expire' and old['price'] == 98
    assert not next(q for q in current['quotes'] if q['id'] == parent['id'])['superseded']


def test_closed_round_cannot_reopen_and_new_round_is_explicit(paired):
    a, b, users, banker, rfq, cid, client = paired
    item_id, reply = published(paired)
    flush(paired, b, reply['response']['message_id'])
    old = exchange.round_for(a, rfq['id'])
    api.update_rfq(rfq['id'], api.RfqUpdate(status='sans_suite'), users[3], a)
    transport.reconcile_closures(a)
    close = a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'CLOSE')).one()
    flush(paired, a, close.id)
    with pytest.raises(HTTPException) as failure:
        api.update_rfq(rfq['id'], api.RfqUpdate(status='auto'), users[3], a)
    assert failure.value.status_code == 409
    a.rollback()
    assert exchange.round_for(a, rfq['id']).state == 'CLOSED'
    assert not api.get_rfq(rfq['id'], users[3], a)['quotes'][0]['comparable']
    new = api.create_rfq(api.RfqCreate(previous_round_id=old.id, pilot_desk_id=11,
        name='Explicit second round', script_snapshot=rfq['script_snapshot'], params=rfq['params'],
        transaction_format='EMTN', instrument_family='Note', payoff_family='Autocall'), users[3], a)
    relation = a.get(RfqChannel, cid).relationship_id
    sent = api.send_rfq_exchange(new['id'], send_body(a, users, new, {'id':relation}), users[3], a)
    mid = sent['tracking']['deliveries'][0]['message_id']
    flush(paired, a, mid)
    assert sent['tracking']['round']['number'] == 2
    assert api.get_rfq(new['id'], users[3], a)['quotes'] == []
    assert exchange.round_for(a, rfq['id']).state == 'CLOSED'
    b.expire_all()
    rounds = b.exec(select(RfqExchangeRound)).all()
    assert sorted(row.state for row in rounds) == ['CLOSED', 'OPEN']
    assert a.get(RfqTransportOutbox, close.id).state == 'DELIVERED'
    # Re-delivery and reconciliation preserve the same closure and both dossiers.
    flush(paired, a, close.id)
    transport.reconcile_closures(a)
    assert len(a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind == 'CLOSE')).all()) == 1


@pytest.mark.parametrize('patch', [
    {'price':98}, {'currency':'USD'}, {'status':'decline'}, {'firmness':'FIRM'},
    {'quoted_at':'2026-10-21T10:00:00Z'}, {'valid_until':'2030-10-22T10:00:00Z'},
])
def test_material_revision_revokes_selection_with_reason_and_product_projection(network_case, patch):
    from backend.app.services.product_repository import load_product
    s, users, r = network_case
    q = manual(network_case)
    select_quote(network_case, q)
    before = load_product(s, r['product_id'])
    changed = api.update_quote(r['id'], q['id'], api.QuoteUpdate(**patch), users[3], s)
    assert changed['revision'] == q['revision'] + 1
    assert changed['rfq_state']['selected_quote_id'] is None
    assert changed['rfq_state']['selected_quote_revision'] is None
    assert changed['rfq_state']['selection_reason_note'] is None
    assert changed['rfq_state']['business_status'] != 'SELECTED'
    after = load_product(s, r['product_id'])
    assert after.product_id == before.product_id and after.terms_version == before.terms_version
    assert after.terms_fingerprint == before.terms_fingerprint
    assert after.rfqs[-1].to_dict()['selected_quote_id'] is None
    assert len(s.exec(select(AuditEvent).where(AuditEvent.action == 'QUOTE_SELECTION_INVALIDATED')).all()) == 1


def test_note_and_identical_retry_preserve_revision_and_decision(network_case):
    from backend.app.services.product_repository import load_product
    s, users, r = network_case
    q = manual(network_case)
    select_quote(network_case, q)
    before = load_product(s, r['product_id']).revision
    same = api.update_quote(r['id'], q['id'], api.QuoteUpdate(price=99), users[3], s)
    assert same['revision'] == q['revision']
    assert load_product(s, r['product_id']).revision == before
    annotated = api.update_quote(r['id'], q['id'], api.QuoteUpdate(note='Commentaire métier'), users[3], s)
    assert annotated['revision'] == q['revision']
    assert annotated['rfq_state']['selected_quote_id'] == q['id']
    assert annotated['created_at'] == q['created_at'] and annotated['quoted_at'] == q['quoted_at']


def test_stale_edit_and_stale_selection_are_rejected(network_case):
    s, users, r = network_case
    q = manual(network_case)
    changed = api.update_quote(r['id'], q['id'], api.QuoteUpdate(price=98, expected_revision=q['revision']), users[3], s)
    for action in [
        lambda: api.update_quote(r['id'], q['id'], api.QuoteUpdate(price=97, expected_revision=q['revision']), users[3], s),
        lambda: api.update_rfq(r['id'], api.RfqUpdate(selected_quote_id=q['id'], expected_quote_revision=q['revision']), users[3], s),
    ]:
        with pytest.raises(HTTPException) as failure:
            action()
        assert failure.value.status_code == 409
        s.rollback()
    assert s.get(RfqQuote, q['id']).revision == changed['revision']
    assert s.get(RfqQuote, q['id']).price == 98
    assert s.get(RfqRequest, r['id']).selected_quote_id is None


@pytest.mark.parametrize('currency', ['EU', '123', 'EURO', 'ÉUR'])
def test_malformed_currency_refused_without_partial_price_change(network_case, currency):
    s, users, r = network_case
    q = manual(network_case)
    with pytest.raises(HTTPException) as failure:
        api.update_quote(r['id'], q['id'], api.QuoteUpdate(currency=currency, price=98), users[3], s)
    assert failure.value.status_code == 422
    s.rollback()
    assert s.get(RfqQuote, q['id']).price == 99


def test_merged_times_normalize_offsets_and_preserve_entry_time(network_case):
    s, users, r = network_case
    q = manual(network_case, quoted_at='2026-10-21T12:00:00+02:00', valid_until='2026-10-21T11:00:00Z')
    assert q['quoted_at'] == '2026-10-21T10:00:00Z'
    changed = api.update_quote(r['id'], q['id'], api.QuoteUpdate(
        quoted_at='2026-10-21T12:00:00Z', valid_until='2026-10-21T13:00:00Z'), users[3], s)
    assert changed['created_at'] == q['created_at']
    assert changed['quoted_at'] == '2026-10-21T12:00:00Z'


def test_invalidated_last_look_requires_new_improvement_before_reactivation(network_case):
    s, users, r = network_case
    parent = manual(network_case)
    api.update_quote(r['id'], parent['id'], api.QuoteUpdate(last_look=True), users[3], s)
    child = s.exec(select(RfqQuote).where(RfqQuote.parent_quote_id == parent['id'])).one()
    api.update_quote(r['id'], child.id, api.QuoteUpdate(price=98), users[3], s)
    api.update_quote(r['id'], parent['id'], api.QuoteUpdate(price=97), users[3], s)
    with pytest.raises(HTTPException):
        api.update_quote(r['id'], child.id, api.QuoteUpdate(status='recu'), users[3], s)
    s.rollback()
    improved = api.update_quote(r['id'], child.id, api.QuoteUpdate(price=96), users[3], s)
    assert improved['status'] == 'recu'
    assert parent['id'] in api.superseded_quote_ids(api._get_quotes(r['id'], s))


@pytest.mark.parametrize('reserved', [False, True], ids=['closed', 'reserved'])
def test_historical_network_quote_survives_closure_without_becoming_selectable(paired, reserved):
    a, b, users, banker, r, _, _ = paired
    _, reply = published(paired)
    flush(paired, b, reply['response']['message_id'])
    q = api.get_rfq(r['id'], users[3], a)['quotes'][0]
    select_quote((a, users, r), q)
    publication = a.exec(select(RfqQuotePublication).where(RfqQuotePublication.quote_id == q['id'])).one()
    if reserved:
        publication.acceptance_received_at = datetime.utcnow()
        a.add(publication)
    rfq = a.get(RfqRequest, r['id'])
    rfq.status = 'clos'
    a.add(rfq); a.commit()
    row = next(h for h in api.rfq_history(users[3], a) if h['quote_id'] == q['id'])
    assert row['won'] and row['history_eligible'] and not row['comparable']
    assert api._quote_row(a.get(RfqQuote,q['id']),session=a)['publication']['state'] == ('RESERVED' if reserved else 'ROUND_CLOSED')


def test_quote_revision_migration_is_additive_idempotent_and_does_not_certify_legacy_decisions():
    from sqlalchemy import text
    from sqlmodel import create_engine
    from backend.app.db.rfq_quote_migrations import migrate_quote_revisions
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE rfq_quotes (id INTEGER PRIMARY KEY, price FLOAT)'))
        conn.execute(text('CREATE TABLE rfq_requests (id INTEGER PRIMARY KEY, selected_quote_id INTEGER)'))
        conn.execute(text('INSERT INTO rfq_quotes VALUES (1, 99)'))
        conn.execute(text('INSERT INTO rfq_requests VALUES (1, 1)'))
        migrate_quote_revisions(conn); migrate_quote_revisions(conn)
        assert tuple(conn.execute(text('SELECT price, revision FROM rfq_quotes')).one()) == (99, 1)
        assert tuple(conn.execute(text('SELECT selected_quote_id, selected_quote_revision FROM rfq_requests')).one()) == (1, None)
    engine.dispose()


def test_two_concurrent_edits_of_same_revision_cannot_both_win(network_case, tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlmodel import create_engine, Session
    from backend.app.db.models import User
    s, users, r = network_case
    q = manual(network_case)
    target = tmp_path/'quotes.db'
    user_id = users[3].id
    with s.get_bind().connect() as connection, sqlite3.connect(target) as disk:
        connection.connection.driver_connection.backup(disk)
    engine = create_engine(f'sqlite:///{target}', connect_args={'check_same_thread': False, 'timeout':10})
    barrier = Barrier(2)
    def edit(price):
        with Session(engine) as session:
            user = session.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                result = api.update_quote(r['id'], q['id'], api.QuoteUpdate(
                    price=price, expected_revision=q['revision']), user, session)
                return result['revision']
            except HTTPException as exc:
                session.rollback()
                assert exc.status_code == 409
                return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, [98, 97]))
    assert results.count('CONFLICT') == 1
    with Session(engine) as session:
        assert session.get(RfqQuote,q['id']).revision == q['revision']+1
        assert len(session.exec(select(AuditEvent).where(AuditEvent.action == 'QUOTE_UPDATED')).all()) == 2
    engine.dispose()


def test_no_selection_right_cannot_use_revision_metadata_to_select(network_case):
    s, users, r = network_case
    q = manual(network_case)
    member = s.exec(select(RfqDeskMembership).where(
        RfqDeskMembership.user_id == users[3].id, RfqDeskMembership.desk_id == 11)).one()
    member.rights_json = '["read","prepare","price"]'
    s.add(member); s.commit()
    with pytest.raises(HTTPException) as failure:
        api.update_rfq(r['id'], api.RfqUpdate(selected_quote_id=q['id'], expected_quote_revision=q['revision']), users[3], s)
    assert failure.value.status_code == 403
    assert s.get(RfqRequest,r['id']).selected_quote_id is None


def test_network_price_revision_preserves_old_response_and_clears_exact_decision(paired):
    from backend.app.api import rfq_inbox as inbox
    from backend.app.db.models import RfqBankQuoteDraft
    from backend.tests.test_rfq_bank_publication import prepare, decision
    a, b, users, banker, r, _, _ = paired
    item_id, first = published(paired)
    flush(paired, b, first['response']['message_id'])
    quote = api.get_rfq(r['id'], users[3], a)['quotes'][0]
    select_quote((a,users,r),quote)
    draft = b.get(RfqBankQuoteDraft,item_id)
    revised = prepare(b,banker,item_id,draft.calculation_id,revision=draft.revision,price=98.8)
    inbox.validate_quote(item_id,decision(revised),banker,b)
    result = inbox.publish_quote(item_id,decision(revised),banker,b)
    second = result['publications'][0]
    flush(paired,b,second['response']['message_id'])
    current = api.get_rfq(r['id'],users[3],a)
    assert current['selected_quote_id'] is None and current['selected_quote_revision'] is None
    assert current['selection_reason_code'] is None and current['selection_reason_note'] is None
    assert len(current['quotes']) == 2
    old, new = sorted(current['quotes'],key=lambda q:q['revision'])
    assert (old['price'],old['revision'],old['comparable']) == (98.5,1,False)
    assert (new['price'],new['revision'],new['comparable']) == (98.8,2,True)
    assert old['counterparty_id'] == new['counterparty_id']
    history = {h['quote_id']:h for h in api.rfq_history(users[3],a)}
    assert not history[old['id']]['history_eligible'] and history[new['id']]['history_eligible']
    assert history[old['id']]['revision'] == 1


@pytest.mark.parametrize('invalid', ['legacy_revision', 'wrong_currency'])
def test_booking_gate_refuses_unqualified_revision_or_currency_even_if_selection_is_forged(network_case, invalid):
    from backend.app.api.deals import _validate_rfq_booking_identity
    s, users, r = network_case
    quote = manual(network_case)
    rfq = s.get(RfqRequest,r['id'])
    q = s.get(RfqQuote,quote['id'])
    rfq.selected_quote_id = q.id
    rfq.selected_quote_revision = None if invalid == 'legacy_revision' else q.revision
    if invalid == 'wrong_currency':
        q.currency = 'USD'
    s.add(q);s.add(rfq);s.commit()
    with pytest.raises(HTTPException) as failure:
        _validate_rfq_booking_identity(rfq,None,s)
    assert failure.value.status_code == 409


def test_closed_manual_round_keeps_history_but_refuses_economic_edits(network_case):
    s, users, r = network_case
    quote = manual(network_case)
    api.update_rfq(r['id'],api.RfqUpdate(status='sans_suite'),users[3],s)
    current = api.get_rfq(r['id'],users[3],s)
    assert current['quotes'][0]['history_eligible'] and not current['quotes'][0]['comparable']
    with pytest.raises(HTTPException) as failure:
        api.update_quote(r['id'],quote['id'],api.QuoteUpdate(price=98),users[3],s)
    assert failure.value.status_code == 409
    s.rollback()
    assert s.get(RfqQuote,quote['id']).price == 99
    annotated = api.update_quote(r['id'],quote['id'],api.QuoteUpdate(note='Revue du dossier clos'),users[3],s)
    assert annotated['note'] == 'Revue du dossier clos'


def test_successor_of_legacy_abandoned_round_preserves_closed_state(network_case):
    from backend.app.services.product_repository import load_product
    s, users, r = network_case
    manual(network_case)
    old = exchange.round_for(s,r['id'])
    # Pre-C23 rows could carry a terminal RFQ while the frozen round stayed OPEN.
    rfq = s.get(RfqRequest,r['id']);rfq.status = 'sans_suite';s.add(rfq);s.commit()
    new = api.create_rfq(api.RfqCreate(previous_round_id=old.id,pilot_desk_id=11,
        name='Successor of legacy closure',script_snapshot=r['script_snapshot'],params=r['params'],
        transaction_format='EMTN',instrument_family='Note',payoff_family='Autocall'),users[3],s)
    assert new['previous_round_id'] == old.id
    assert exchange.round_for(s,r['id']).state == 'CLOSED'
    old_product = load_product(s,r['product_id'])
    old_projection = next(item.to_dict() for item in old_product.rfqs if item.to_dict()['id'] == r['id'])
    assert old_projection['exchange_round']['state'] == 'CLOSED'
