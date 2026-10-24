"""Dated peer statements, discrepancies and recovery without copying a private book."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import text, event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select
from backend.app.api import deals, rfq as api, rfq_inbox as inbox
from backend.app.api.rfq_reconciliation import list_reconciliation
from backend.app.db.models import (Deal, RfqElectronicExecution, RfqReconciliationStatement,
    RfqDeskMembership, RfqTransportInbox, RfqTransportOutbox, RfqSolicitation, RfqExchangeRound, User)
from backend.app.services import rfq_reconciliation as service, rfq_transport as transport, rfq_bank as bank
from backend.app.db.rfq_execution_integrity import install_execution_guards
from backend.tests import test_rfq_electronic_execution as electronic_tests
from backend.tests.test_rfq_electronic_execution import (received, decide, native_booking)
from backend.tests.test_rfq_transport import paired, flush
from backend.tests.test_rfq_relationships import network_case


@pytest.fixture
def electronic_case(paired,monkeypatch):
    original=electronic_tests.prepare
    def aligned_documentation(*args,**changes):
        return original(*args,**{**changes,'documentation_reference':'EMTN de recette électronique'})
    monkeypatch.setattr(electronic_tests,'prepare',aligned_documentation)
    return electronic_tests.electronic_case.__wrapped__(paired,monkeypatch)


def confirmed(case):
    request,_=received(case)
    response=decide(case,request)
    flush(case[0],case[0][1],response['transport']['message_id'])
    return request


def drain(case):
    for _ in range(20):
        pending=[]
        for db in case[0][:2]:
            transport.reconcile_closures(db)
            db.expire_all()
            pending.extend((db,r.id) for r in db.exec(select(RfqTransportOutbox).where(
                RfqTransportOutbox.state.notin_(['DELIVERED','CANCELLED'])).order_by(RfqTransportOutbox.sequence)).all())
        if not pending:return
        for db,identifier in pending:flush(case[0],db,identifier)
    raise AssertionError('Unbounded reconciliation reply loop')


def workspace(db,identifier):
    db.expire_all()
    return service.workspace(db,db.get(RfqElectronicExecution,identifier))


def test_confirmation_alone_never_implies_a_booking_or_a_matched_book(electronic_case):
    case=electronic_case;request=confirmed(case);a,b=case[0][:2]
    assert workspace(a,request['id'])['state']=='PEER_UNKNOWN'
    drain(case)
    for db in (a,b):
        state=workspace(db,request['id'])
        assert state['state']=='BOTH_BOOKINGS_MISSING' and not state['differences']
        assert state['peer_version'] and state['peer_received_at']
        assert not db.exec(select(Deal)).all()


@pytest.mark.parametrize('first_bank',[False,True])
def test_incomplete_local_leg_resumes_after_remote_close_and_both_books_match(electronic_case,first_bank):
    case=electronic_case;request=confirmed(case);a,b,users,banker,rfq,_,_=case[0]
    drain(case)
    first_db,first_actor=(b,banker) if first_bank else (a,users[3])
    second_db,second_actor=(a,users[3]) if first_bank else (b,banker)
    body=native_booking(case,first_bank).model_dump(mode='json')
    first=deals.book_deal(deals.DealCreate(**body),first_actor,first_db)
    drain(case)
    assert workspace(first_db,request['id'])['state']=='PEER_BOOKING_MISSING',workspace(first_db,request['id'])['differences']
    assert workspace(second_db,request['id'])['state']=='LOCAL_BOOKING_MISSING'
    if not first_bank:
        item_id=case[1]
        assert not bank.work_row(b,b.get(RfqSolicitation,item_id),banker)['open_for_work']
        assert bank.work_row(b,b.get(RfqSolicitation,item_id),banker)['booking_recovery_available']
        bank.require_pricing(b,bank.case_for_product(b,b.get(RfqElectronicExecution,request['id']).product_id),banker)
    other=native_booking(case,not first_bank).model_dump(mode='json')
    second=deals.book_deal(deals.DealCreate(**other),second_actor,second_db)
    assert deals.book_deal(deals.DealCreate(**other),second_actor,second_db)['id']==second['id']
    drain(case)
    for db in (a,b):
        assert workspace(db,request['id'])['state']=='MATCHED'
        assert len(db.exec(select(Deal)).all())==1


def test_refresh_reuses_command_and_never_creates_or_repairs_a_deal(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0]
    drain(case)
    cmd=service.RefreshCommand(command_key=str(uuid4()))
    service.refresh(a,request['id'],users[3],cmd)
    count=len(a.exec(select(RfqTransportOutbox)).all())
    service.refresh(a,request['id'],users[3],cmd)
    assert len(a.exec(select(RfqTransportOutbox)).all())==count
    drain(case)
    assert not a.exec(select(Deal)).all() and not b.exec(select(Deal)).all()
    assert workspace(a,request['id'])['state']=='BOTH_BOOKINGS_MISSING'


@pytest.mark.parametrize('field,value',[
    ('price',99.0),('nominal',2000000),('currency','USD'),('side','BUY'),
    ('terms_fingerprint','0'*64),('documentation_reference','Other programme'),
    ('strike_date','2099-01-01'),('value_date','2099-01-01'),('maturity_date','2099-01-01'),
    ('payment_date','2099-01-01'),('legal_mapping_matches',False),
    ('transaction_format','OTC'),('instrument_family','SWAP'),('payoff_family','VANILLA')])
def test_authenticated_peer_economic_discrepancies_are_visible_not_auto_repaired(electronic_case,field,value):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    body=native_booking(case,True)
    deals.book_deal(body,banker,b);drain(case)
    entry=b.get(RfqElectronicExecution,request['id'])
    row=service.stage_current(b,entry,banker.id,request_reply=False);b.commit()
    message=transport.wire_message(row);message['payload']['booking'][field]=value
    message['payload_hash']=service.exchange.digest(message['payload'])
    channel=b.get(transport.RfqChannel,row.channel_id)
    transport.receive(a,transport.envelope(b,channel,'DELIVER',message))
    state=workspace(a,request['id'])
    assert state['state']=='MISMATCH'
    assert any(d['side']=='PEER' and d['field']==field for d in state['differences'])
    assert not a.exec(select(Deal)).all()
    assert len(b.exec(select(Deal)).all())==1


@pytest.mark.parametrize('change',[{'role':'REQUESTER'},{'request_hash':'0'*64},
    {'execution_id':str(uuid4())},{'version':1},{'observed_at':'2099-01-01T00:00:00Z'},
    {'observed_at':'2000-01-01T00:00:00Z'},
    {'private_fair_value':96.7}])
def test_unbound_old_future_or_private_status_cannot_replace_the_peer_state(electronic_case,change):
    from pydantic import ValidationError
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    previous=workspace(a,request['id'])['peer_version']
    row=service.stage_current(b,b.get(RfqElectronicExecution,request['id']),banker.id,request_reply=False);b.commit()
    message=transport.wire_message(row);message['payload'].update(change)
    message['payload_hash']=service.exchange.digest(message['payload'])
    with pytest.raises((HTTPException,ValidationError)):
        transport.receive(a,transport.envelope(b,b.get(transport.RfqChannel,row.channel_id),'DELIVER',message))
    a.rollback()
    assert workspace(a,request['id'])['peer_version']==previous
    assert not a.get(RfqTransportInbox,row.id)


@pytest.mark.parametrize('bank_side',[False,True])
def test_lost_status_ack_and_restarts_recover_without_duplicate_statement_or_reply(electronic_case,bank_side):
    case=electronic_case;request=confirmed(case);a,b,users,banker,_,_,native=case[0];drain(case)
    source,actor=(b,banker) if bank_side else (a,users[3])
    target=a if bank_side else b
    result=service.refresh(source,request['id'],actor,service.RefreshCommand(command_key=str(uuid4())))
    identifier=result['transport']['message_id']
    def lose_ack(http_request):
        native.post(str(http_request.url),json=json.loads(http_request.content)).raise_for_status()
        raise httpx.ReadError('ack lost after commit',request=http_request)
    with httpx.Client(transport=httpx.MockTransport(lose_ack)) as broken:
        row=source.get(RfqTransportOutbox,identifier)
        with pytest.raises(httpx.ReadError):
            transport.call_peer(source,source.get(transport.RfqChannel,row.channel_id),'DELIVER',transport.wire_message(row),broken)
    before=len(target.exec(select(RfqReconciliationStatement)).all())
    flush(case[0],source,identifier)
    assert len(target.exec(select(RfqReconciliationStatement)).all())==before
    assert source.get(RfqTransportOutbox,identifier).state=='DELIVERED'
    drain(case)


def test_statements_and_proofs_are_immutable(electronic_case):
    case=electronic_case;request=confirmed(case);a=case[0][0];drain(case)
    row=a.exec(select(RfqReconciliationStatement)).first()
    for query in ('UPDATE rfq_reconciliation_statements SET payload_hash=:value WHERE message_id=:id',
                  'DELETE FROM rfq_reconciliation_statements WHERE message_id=:id'):
        with pytest.raises(IntegrityError):
            a.execute(text(query),{'value':'0'*64,'id':row.message_id});a.commit()
        a.rollback()


@pytest.mark.parametrize('bank_side',[False,True])
def test_read_access_does_not_grant_resume_and_revocation_is_rechecked(electronic_case,bank_side):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    db,actor=(b,banker) if bank_side else (a,users[3])
    assert service.authorize(db,request['id'],actor).id==request['id']
    membership=db.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id==actor.id)).first()
    membership.rights_json='["read","price"]';db.add(membership);db.commit()
    assert service.authorize(db,request['id'],actor).id==request['id']
    before=len(db.exec(select(RfqTransportOutbox)).all())
    with pytest.raises(HTTPException):
        service.refresh(db,request['id'],actor,service.RefreshCommand(command_key=str(uuid4())))
    db.rollback()
    assert len(db.exec(select(RfqTransportOutbox)).all())==before


def test_failed_booking_rolls_back_the_booking_statement_then_same_command_recovers(electronic_case,monkeypatch):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    body=native_booking(case,True).model_dump(mode='json')
    original=service.stage_current
    def crash(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('failure after status staged before local commit')
    count=len(b.exec(select(RfqReconciliationStatement)).all())
    monkeypatch.setattr(service,'stage_current',crash)
    with pytest.raises(RuntimeError):deals.book_deal(deals.DealCreate(**body),banker,b)
    b.rollback()
    assert not b.exec(select(Deal)).all()
    assert len(b.exec(select(RfqReconciliationStatement)).all())==count
    monkeypatch.setattr(service,'stage_current',original)
    deals.book_deal(deals.DealCreate(**body),banker,b);drain(case)
    assert workspace(a,request['id'])['state']=='LOCAL_BOOKING_MISSING'


def test_closed_or_expired_unconfirmed_rfq_does_not_gain_pricing_recovery(electronic_case):
    case=electronic_case;request,_=received(case);b=case[0][1];banker=case[0][3]
    item=b.get(RfqSolicitation,case[1]);row=b.get(RfqExchangeRound,item.round_id)
    row.state='CLOSED';b.add(row);b.commit()
    assert not bank.work_row(b,item,banker)['booking_recovery_available']
    with pytest.raises(HTTPException):bank.require_pricing(b,bank.case_for_product(b,b.get(RfqElectronicExecution,request['id']).product_id),banker)


def test_concurrent_same_resume_command_queues_one_snapshot(electronic_case,tmp_path):
    case=electronic_case;request=confirmed(case);a,_,users,*_=case[0];drain(case)
    target=tmp_path/'requester.db';a.commit()
    with sqlite3.connect(target) as copied:a.connection().connection.driver_connection.backup(copied)
    a.rollback()
    engine=create_engine('sqlite:///'+str(target),connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def pragmas(connection,_):
        connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA busy_timeout=5000')
    barrier=Barrier(2);key=str(uuid4());actor_id=users[3].id
    def resume(_):
        with Session(engine) as db:
            actor=db.get(User,actor_id);barrier.wait()
            return service.refresh(db,request['id'],actor,service.RefreshCommand(command_key=key))['transport']['message_id']
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(resume,range(2)))
        assert ids[0]==ids[1]
        with Session(engine) as db:
            assert len(db.exec(select(RfqReconciliationStatement).where(RfqReconciliationStatement.command_key==key)).all())==1
            assert not db.exec(select(Deal)).all()
    finally:engine.dispose()


def test_peer_booking_disappearance_is_a_discrepancy_kept_in_history(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    deals.book_deal(native_booking(case,True),banker,b);drain(case)
    row=service.stage_current(b,b.get(RfqElectronicExecution,request['id']),banker.id,request_reply=False);b.commit()
    message=transport.wire_message(row);message['payload']['booking']=None
    message['payload_hash']=service.exchange.digest(message['payload'])
    transport.receive(a,transport.envelope(b,b.get(transport.RfqChannel,row.channel_id),'DELIVER',message))
    state=workspace(a,request['id'])
    assert state['state']=='MISMATCH'
    assert any(d['field']=='booking_regression' and d['side']=='PEER' for d in state['differences'])
    assert len(a.exec(select(RfqReconciliationStatement).where(RfqReconciliationStatement.is_local==False)).all())>1


def test_resume_also_reschedules_a_closure_that_blocks_later_status_messages(electronic_case):
    case=electronic_case;request=confirmed(case);a,_,users,*_=case[0];drain(case)
    deals.book_deal(native_booking(case),users[3],a)
    transport.reconcile_closures(a)
    close=a.exec(select(RfqTransportOutbox).where(RfqTransportOutbox.kind=='CLOSE')).one()
    close.next_attempt_at=service.business_now()+timedelta(days=1);a.add(close);a.commit()
    service.refresh(a,request['id'],users[3],service.RefreshCommand(command_key=str(uuid4())))
    a.refresh(close)
    assert close.next_attempt_at < service.business_now()+timedelta(seconds=5)
    drain(case)
    assert workspace(a,request['id'])['state']=='PEER_BOOKING_MISSING'


def test_existing_confirmed_bookings_gain_no_peer_certificate_until_refresh(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    for db,actor,is_bank in ((b,banker,True),(a,users[3],False)):
        deals.book_deal(native_booking(case,is_bank),actor,db)
    drain(case)
    for db in (a,b):
        preserved=db.get(RfqElectronicExecution,request['id']).decision_json
        db.commit()
        # Disposable fixture: simulate adding the new table to an installation with existing business facts.
        with db.get_bind().begin() as connection:
            connection.execute(text('DROP TABLE rfq_reconciliation_statements'))
        SQLModel.metadata.create_all(db.get_bind(),tables=[RfqReconciliationStatement.__table__])
        install_execution_guards(db.get_bind());db.expire_all()
        assert workspace(db,request['id'])['state']=='PEER_UNKNOWN'
        assert db.get(RfqElectronicExecution,request['id']).decision_json==preserved
        assert len(db.exec(select(Deal)).all())==1
    for db,actor in ((a,users[3]),(b,banker)):
        service.refresh(db,request['id'],actor,service.RefreshCommand(command_key=str(uuid4())))
    drain(case)
    assert all(workspace(db,request['id'])['state']=='MATCHED' for db in (a,b))


@pytest.mark.parametrize('bank_side',[False,True])
def test_foreign_organization_cannot_read_or_resume(electronic_case,bank_side):
    case=electronic_case;request=confirmed(case);a,b,users,*_=case[0];drain(case)
    db=b if bank_side else a
    outsider=users[2]
    for write in (False,True):
        with pytest.raises(HTTPException):service.authorize(db,request['id'],outsider,write=write)
        db.rollback()


def test_bank_refusal_is_reconciled_without_inventing_bookings(electronic_case):
    case=electronic_case;request,_=received(case)
    response=decide(case,request,'REJECTED','Refus motivé de recette')
    flush(case[0],case[0][1],response['transport']['message_id']);drain(case)
    for db in case[0][:2]:
        assert workspace(db,request['id'])['state']=='REJECTED'
        assert not db.exec(select(Deal)).all()


def test_different_booked_trade_dates_are_reported_without_choosing_a_date(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    for db,actor,is_bank in ((b,banker,True),(a,users[3],False)):
        deals.book_deal(native_booking(case,is_bank),actor,db)
    drain(case)
    row=service.stage_current(b,b.get(RfqElectronicExecution,request['id']),banker.id,request_reply=False);b.commit()
    message=transport.wire_message(row);message['payload']['booking']['trade_date']='2099-01-01'
    message['payload_hash']=service.exchange.digest(message['payload'])
    transport.receive(a,transport.envelope(b,b.get(transport.RfqChannel,row.channel_id),'DELIVER',message))
    state=workspace(a,request['id'])
    assert state['state']=='MISMATCH'
    assert any(d['field']=='trade_date' for d in state['differences'])


def test_confirmed_incomplete_bank_leg_can_be_explicitly_reassigned_after_close(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    deals.book_deal(native_booking(case),users[3],a);drain(case)
    target=User(username='replacement',email='replacement@example.test',password_hash='x',entity_id=banker.entity_id,role='admin')
    b.add(target);b.flush()
    b.add(RfqDeskMembership(desk_id=721,user_id=target.id,rights_json='["read","prepare","price","book"]'));b.commit()
    current_case=bank.case_for_product(b,b.get(RfqElectronicExecution,request['id']).product_id)
    bank.assign(b,case[1],banker,target.id,current_case.revision,'Reprise explicite du booking confirmé')
    bank.require_pricing(b,current_case,target)
    with pytest.raises(HTTPException):bank.require_pricing(b,current_case,banker)
    assert workspace(b,request['id'])['state']=='LOCAL_BOOKING_MISSING'


def test_operational_inventory_and_bank_queue_are_scoped_and_surface_incomplete_legs(electronic_case):
    case=electronic_case;request=confirmed(case);a,b,users,banker,*_=case[0];drain(case)
    deals.book_deal(native_booking(case),users[3],a);drain(case)
    for db,actor in ((a,users[3]),(b,banker)):
        listing=list_reconciliation(actor,db)
        assert len(listing['items'])==1 and listing['items'][0]['execution_id']==request['id']
        assert list_reconciliation(users[2],db)['items']==[]
        assert list_reconciliation(actor,db,before_id=1)['items']==[]
    assert inbox.list_received(banker,b)[0]['reconciliation_state']=='LOCAL_BOOKING_MISSING'
