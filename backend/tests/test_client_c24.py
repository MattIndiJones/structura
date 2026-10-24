"""CRM attribution, dated observations and currency units on isolated data."""
from datetime import date
import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import opportunities, client_intelligence as intelligence, client_import
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import (Affiliation, Client, ClientMandate, ClientTradeHistory, Entity,
    Opportunity, OpportunityParticipant, Person, User)
from backend.app.core.client_cycle import compute_cycle


@pytest.fixture
def crm():
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def foreign_keys(conn,_):conn.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Entity(id=1,name='Owner'),Entity(id=2,name='Other')]);s.flush()
        s.add_all([User(id=1,username='owner',email='owner@example.test',password_hash='x',role='user',entity_id=1),
                   User(id=2,username='foreign',email='foreign@example.test',password_hash='x',role='user',entity_id=2)])
        s.add_all([Client(id=1,entity_id=1,name='A',data_origin='native'),
                   Client(id=2,entity_id=1,name='B',data_origin='native'),
                   Client(id=3,entity_id=2,name='Foreign',data_origin='native')]);s.flush()
        s.add_all([ClientMandate(id=1,entity_id=1,client_id=1,name='Real',data_origin='native'),
                   ClientMandate(id=2,entity_id=1,client_id=2,name='Real B',data_origin='native'),
                   ClientMandate(id=3,entity_id=1,client_id=1,name='Demo',data_origin='demo')])
        s.add_all([Person(id=1,entity_id=1,first_name='A',last_name='Contact'),
                   Person(id=2,entity_id=1,first_name='B',last_name='Contact')]);s.flush()
        s.add_all([Affiliation(id=1,person_id=1,client_id=1,start_date='2020-01-01'),
                   Affiliation(id=2,person_id=2,client_id=2,start_date='2020-01-01')]);s.commit()
        app=FastAPI()
        for router in [opportunities.router,intelligence.router,client_import.router]:app.include_router(router)
        app.dependency_overrides[get_session]=lambda:s
        app.dependency_overrides[get_current_user]=lambda:s.get(User,1)
        with TestClient(app) as http:
            yield s,http
    engine.dispose()


def opportunity(http,**extra):
    response=http.post('/api/opportunities',json={'client_id':1,'mandate_id':1,'title':'Need',
        'description':'Documented client investment need','transaction_format':'EMTN','instrument_family':'Note',
        'payoff_family':'Autocall',**extra})
    assert response.status_code==201,response.text
    return response.json()


def history(s,trade_date='2026-01-15',currency='EUR',notional=1_000_000,**extra):
    row=ClientTradeHistory(entity_id=1,client_id=1,mandate_id=1,affiliation_id=1,
        trade_date=trade_date,currency=currency,notional=notional,product_type='Autocall',**extra)
    s.add(row);s.commit();return row


def test_client_move_revalidates_persisted_participants_when_patch_omits_them(crm):
    s,http=crm
    row=opportunity(http,participants=[{'affiliation_id':1,'role':'decision_maker'}])
    response=http.patch(f"/api/opportunities/{row['id']}",json={'client_id':2,'mandate_id':2})
    assert response.status_code==409,response.text
    assert s.get(Opportunity,row['id']).client_id==1
    assert s.exec(select(OpportunityParticipant)).one().affiliation_id==1


def test_historical_profile_excludes_future_transactions_from_every_observation(crm):
    s,http=crm
    history(s);future=history(s,trade_date='2027-01-15',notional=100_000_000,currency='JPY')
    response=http.get('/api/client-intelligence/clients/1?asof=2026-02-01')
    assert response.status_code==200,response.text
    profile=response.json()
    assert profile['behaviour']['n_trades']==1
    assert profile['cycle']['days_since_last']==17
    assert profile['excluded_future_count']==1
    assert all(row['source_id']!=future.id for row in profile['transactions'])
    assert profile['behaviour']['currencies']==[['EUR',1]]


def test_cycle_rejects_future_dates_as_observed_history():
    cycle=compute_cycle([date(2026,1,15),date(2027,1,15)],asof=date(2026,2,1))
    assert cycle.n_trades==1 and cycle.days_since_last==17


def test_pipeline_and_ticket_never_sum_or_median_different_currency_units(crm):
    s,http=crm
    opportunity(http,amount=1_000_000,currency='EUR')
    opportunity(http,amount=100_000_000,currency='JPY')
    history(s);history(s,currency='JPY',notional=100_000_000)
    metrics=http.get('/api/client-intelligence/analytics').json()['opportunities']
    assert metrics['pipeline_amount'] is None
    assert metrics['pipeline_by_currency']=={'EUR':1_000_000,'JPY':100_000_000}
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['behaviour']['median_ticket'] is None
    assert profile['behaviour']['median_ticket_by_currency']=={'EUR':1_000_000,'JPY':100_000_000}
    assert profile['ranges']['ticket']['median'] is None
    assert set(profile['ranges']['ticket_by_currency'])=={'EUR','JPY'}


def test_real_import_engine_excludes_demo_mandate_from_real_profile(crm):
    s,http=crm
    payload={'transactions':[{'client_name':'A','mandate_name':'Demo','trade_date':'2026-01-15',
        'product_type':'Autocall','currency':'EUR','notional':1_000_000}]}
    response=http.post('/api/client-import/apply',files={'file':('history.json',
        io.BytesIO(json.dumps(payload).encode()),'application/json')})
    assert response.status_code==200,response.text
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['behaviour']['n_trades']==0
    assert profile['excluded_demo_count']==1
    diagnostic=http.get('/api/client-intelligence/clients/1?asof=2026-02-01&include_demo=true').json()
    assert diagnostic['transactions'][0]['data_origin']=='demo'


@pytest.mark.parametrize('participants', [[],[{'affiliation_id':2,'role':'decision_maker'}]])
def test_unlinked_client_move_requires_explicit_coherent_replacement(crm,participants):
    s,http=crm
    row=opportunity(http,participants=[{'affiliation_id':1,'role':'decision_maker'}])
    response=http.patch(f"/api/opportunities/{row['id']}",json={'client_id':2,'mandate_id':2,
        'primary_affiliation_id':None,'participants':participants})
    assert response.status_code==200,response.text
    assert response.json()['client_id']==2
    assert {p.affiliation_id for p in s.exec(select(OpportunityParticipant)).all()}=={p['affiliation_id'] for p in participants}


@pytest.mark.parametrize('source',['deal','rfq','product'])
def test_linked_opportunity_cannot_move_client_or_mandate(crm,source):
    from backend.app.api import rfq, products
    from backend.app.db.models import Deal,RfqDesk,RfqDeskMembership,ProductRevision
    from backend.tests.test_rfq import _rfq_params
    from backend.tests.test_products import _pricing_input
    from uuid import uuid4
    s,http=crm
    row=opportunity(http,participants=[{'affiliation_id':1,'role':'decision_maker'}])
    if source=='deal':
        # Existing booked observation, independent of a live RFQ.
        s.add(Deal(reference='C24 frozen booking',user_id=1,entity_id=1,client_id=1,mandate_id=1,
            opportunity_id=row['id'],trade_date='2026-01-15',script_snapshot='AT MATURITY\n  PAY 1',
            nominal=1_000_000,client_provenance_json='{"client":{"id":1}}'))
        s.commit()
    elif source=='rfq':
        s.add(RfqDesk(id=11,entity_id=1,name='Sales'));s.flush()
        s.add(RfqDeskMembership(desk_id=11,user_id=1,rights_json='["read","prepare","price","solicit"]'));s.commit()
        rfq.create_rfq(rfq.RfqCreate(pilot_desk_id=11,opportunity_id=row['id'],kind='indicatif',
            name='C24 consultation',script_snapshot='AT MATURITY\n  PAY 1',params=_rfq_params()),s.get(User,1),s)
    else:
        products.create_product(products.ProductCreate(command_key=uuid4().hex,name='C24 canonical product',
            pricing_input=_pricing_input(),commercial={'client_id':1,'mandate_id':1,'opportunity_id':row['id']}),s.get(User,1),s)
    before=[record.snapshot_json for record in s.exec(select(ProductRevision)).all()]
    booked_before=s.exec(select(Deal)).first().model_dump(mode='json') if source=='deal' else None
    for body in [{'client_id':2,'mandate_id':2,'participants':[]},{'mandate_id':3}]:
        response=http.patch(f"/api/opportunities/{row['id']}",json=body)
        assert response.status_code==409,response.text
        assert response.json()['detail']['code']=='OPPORTUNITY_ATTRIBUTION_FROZEN'
    assert (s.get(Opportunity,row['id']).client_id,s.get(Opportunity,row['id']).mandate_id)==(1,1)
    assert s.exec(select(OpportunityParticipant)).one().affiliation_id==1
    assert [record.snapshot_json for record in s.exec(select(ProductRevision)).all()]==before
    if booked_before is not None:
        assert s.exec(select(Deal)).one().model_dump(mode='json')==booked_before


@pytest.mark.parametrize('path',['/api/client-intelligence/analytics',
    '/api/client-intelligence/persons/1','/api/client-intelligence/affiliations/1'])
def test_all_dated_entrypoints_exclude_future_observations(crm,path):
    s,http=crm
    history(s);history(s,trade_date='2027-01-15')
    response=http.get(path,params={'asof':'2026-02-01'})
    assert response.status_code==200,response.text
    data=response.json()
    if 'analytics' in path:assert data['trades']['total']==1
    elif 'persons' in path:assert data['behaviour']['personal']['n_trades']==1
    else:assert data['behaviour']['n_trades']==1


def test_pipeline_current_state_is_distinct_from_dated_transactions(crm):
    s,http=crm
    row=opportunity(http,amount=1_000_000,currency='EUR')
    history(s);history(s,trade_date='2027-01-15')
    response=http.get('/api/client-intelligence/analytics?asof=2026-02-01').json()
    assert response['trades']['total']==1
    assert response['opportunities']['state_basis']=='CURRENT_STATE'
    assert response['opportunities']['state_asof']==date.today().isoformat()
    assert response['temporal_basis']['historical_opportunity_state_reconstructed'] is False
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['conversion']['state_basis']=='CURRENT_STATE'


def test_same_currency_medians_and_declared_bounds_keep_their_unit(crm):
    s,http=crm
    client=s.get(Client,1);client.ticket_min=500_000;client.ticket_max=2_000_000;client.ticket_currency='EUR'
    s.add(client);s.commit()
    history(s,notional=1_000_000);history(s,notional=3_000_000)
    before=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert before['behaviour']['median_ticket']==2_000_000
    assert before['behaviour']['median_ticket_currency']=='EUR'
    history(s,currency='JPY',notional=100_000_000)
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    ranges=profile['ranges']['ticket_by_currency']
    assert ranges['EUR']['declared_min']==500_000
    assert ranges['JPY']['declared_min'] is None and ranges['JPY']['declared_max'] is None
    assert ranges['JPY']['median']==100_000_000


@pytest.mark.parametrize('currency',['','??',' usd '])
def test_missing_currency_never_inherits_eur_in_analytics(crm,currency):
    s,http=crm
    opportunity(http,amount=100_000_000,currency=currency)
    metrics=http.get('/api/client-intelligence/analytics').json()['opportunities']
    if currency.strip().upper()=='USD':
        assert metrics['pipeline_by_currency']=={'USD':100_000_000}
    else:
        assert metrics['pipeline_amount'] is None
        assert metrics['pipeline_by_currency']=={}
        assert metrics['pipeline_unqualified_count']==1


def test_real_mode_does_not_implicitly_include_a_demo_only_dataset(crm):
    s,http=crm
    row=history(s);row.mandate_id=3;s.add(row);s.commit()
    opportunity(http,amount=1_000_000,currency='EUR',mandate_id=3)
    real=http.get('/api/client-intelligence/analytics').json()
    assert real['trades']['total']==0 and real['opportunities']['open']==0
    demo=http.get('/api/client-intelligence/analytics?include_demo=true').json()
    assert demo['analysis_mode']=='demo_included' and demo['trades']['total']==1
    assert demo['opportunities']['pipeline_by_currency']=={'EUR':1_000_000}


def test_future_and_undated_rows_are_separately_explained(crm):
    s,http=crm
    history(s);history(s,trade_date='2027-01-15');history(s,trade_date='')
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['behaviour']['n_trades']==1
    assert profile['excluded_future_count']==1 and profile['excluded_undated_count']==1


def test_other_entity_context_is_not_disclosed_or_accepted(crm):
    s,http=crm
    row=opportunity(http)
    assert http.get('/api/client-intelligence/clients/3?asof=2026-02-01').status_code==404
    assert http.patch(f"/api/opportunities/{row['id']}",json={'client_id':3,'mandate_id':None}).status_code==404
    assert s.get(Opportunity,row['id']).client_id==1


def test_only_future_dates_give_no_cycle_and_no_negative_duration():
    cycle=compute_cycle([date(2027,1,15)],asof=date(2026,2,1))
    assert cycle.n_trades==0 and cycle.last_trade_date is None and cycle.days_since_last is None


def test_asof_boundary_and_unknown_dates_are_explicit(crm):
    s,http=crm
    history(s,trade_date='2026-02-01');history(s,trade_date='2026-02-02');history(s,trade_date='unknown')
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['cycle']['days_since_last']==0 and profile['behaviour']['n_trades']==1
    assert profile['excluded_future_count']==1 and profile['excluded_undated_count']==1


def test_person_profile_uses_affiliation_effective_on_requested_date(crm):
    s,http=crm
    current=s.get(Affiliation,1);current.end_date='2026-12-31';s.add(current)
    s.add(Affiliation(id=3,person_id=1,client_id=2,start_date='2027-01-01'));s.commit()
    history(s)
    profile=http.get('/api/client-intelligence/persons/1?asof=2026-02-01').json()
    assert profile['current_affiliation_id']==1
    assert profile['behaviour']['current_affiliation']['n_trades']==1


def test_persisted_primary_contact_also_requires_explicit_replacement(crm):
    s,http=crm
    row=opportunity(http,primary_affiliation_id=1)
    response=http.patch(f"/api/opportunities/{row['id']}",json={'client_id':2,'mandate_id':2,'participants':[]})
    assert response.status_code==409
    assert s.get(Opportunity,row['id']).primary_affiliation_id==1


def test_declared_ticket_range_is_visible_without_observations(crm):
    s,http=crm
    client=s.get(Client,1);client.ticket_min=500_000;client.ticket_currency='EUR';s.add(client);s.commit()
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['ranges']['ticket_by_currency']['EUR']['declared_min']==500_000
    assert profile['ranges']['ticket_by_currency']['EUR']['n']==0


def test_imported_future_trade_cannot_create_a_lifecycle_signal(crm):
    s,http=crm
    history(s,trade_date='2026-02-10',maturity_date='2026-02-15')
    signals=http.get('/api/client-intelligence/signals?asof=2026-02-01').json()
    assert not any(signal['kind']=='upcoming_lifecycle_event' for signal in signals['signals'])
    assert signals['temporal_basis']['historical_opportunity_state_reconstructed'] is False


def test_move_and_product_creation_cannot_commit_conflicting_attributions(crm,tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from fastapi import HTTPException
    from backend.app.api import products
    from backend.app.db.models import ProductRecord,ProductRevision
    from backend.tests.test_products import _pricing_input
    s,http=crm
    row=opportunity(http)
    target=tmp_path/'crm.db'
    with s.get_bind().connect() as connection,sqlite3.connect(target) as disk:
        connection.connection.driver_connection.backup(disk)
    engine=create_engine(f'sqlite:///{target}',connect_args={'check_same_thread':False,'timeout':10})
    @event.listens_for(engine,'connect')
    def foreign_keys(conn,_):conn.execute('PRAGMA foreign_keys=ON')
    barrier=Barrier(2)
    def run(kind):
        with Session(engine) as session:
            user=session.get(User,1)
            barrier.wait(timeout=10)
            try:
                if kind=='move':
                    opportunities.update_opportunity(row['id'],opportunities.OpportunityUpdate(
                        client_id=2,mandate_id=2,participants=[]),user,session)
                else:
                    products.create_product(products.ProductCreate(command_key=uuid4().hex,name='Concurrent product',
                        pricing_input=_pricing_input(),commercial={'client_id':1,'mandate_id':1,'opportunity_id':row['id']}),user,session)
                return 200
            except HTTPException as exc:
                session.rollback()
                assert exc.status_code in (409,422)
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,['move','product']))
    assert results.count(200)==1
    with Session(engine) as session:
        opportunity_row=session.get(Opportunity,row['id'])
        records=session.exec(select(ProductRecord)).all()
        if opportunity_row.client_id==2:assert records==[]
        else:
            assert opportunity_row.client_id==1 and len(records)==1
            snapshot=json.loads(session.exec(select(ProductRevision)).one().snapshot_json)
            assert snapshot['commercial']['client_id']==1 and snapshot['commercial']['mandate_id']==1
    engine.dispose()


def test_t14_attribution_dates_currencies_and_imported_demo_interact_coherently(crm):
    from backend.app.db.models import Deal
    s,http=crm
    row=opportunity(http,status='won',participants=[{'affiliation_id':1,'role':'decision_maker'}])
    s.add(Deal(reference='T14 existing contract',user_id=1,entity_id=1,client_id=1,mandate_id=1,
        opportunity_id=row['id'],trade_date='2026-01-10',nominal=1_000_000,devise='EUR',
        script_snapshot='AT MATURITY\n  PAY 1',client_provenance_json='{"client":{"id":1}}'))
    s.commit()
    moved=http.patch(f"/api/opportunities/{row['id']}",json={'client_id':2,'mandate_id':2,'participants':[]})
    assert moved.status_code==409
    history(s,currency='JPY',notional=100_000_000)
    history(s,trade_date='2027-01-15',notional=999_000_000)
    payload={'transactions':[{'client_name':'A','mandate_name':'Demo','trade_date':'2026-01-20',
        'product_type':'Autocall','currency':'EUR','notional':2_000_000}]}
    imported=http.post('/api/client-import/apply',files={'file':('demo.json',
        io.BytesIO(json.dumps(payload).encode()),'application/json')})
    assert imported.status_code==200,imported.text
    profile=http.get('/api/client-intelligence/clients/1?asof=2026-02-01').json()
    assert profile['behaviour']['n_trades']==2
    assert profile['behaviour']['median_ticket'] is None
    assert profile['behaviour']['median_ticket_by_currency']=={'EUR':1_000_000,'JPY':100_000_000}
    assert profile['excluded_future_count']==1 and profile['excluded_demo_count']==1
    assert profile['cycle']['days_since_last']==17
    assert s.get(Opportunity,row['id']).client_id==1
    assert s.exec(select(OpportunityParticipant)).one().affiliation_id==1
    assert s.exec(select(Deal)).one().client_id==1
    assert http.get('/api/client-intelligence/clients/3?asof=2026-02-01').status_code==404
