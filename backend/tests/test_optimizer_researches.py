"""Persistent owned research jobs: isolated SQLite, detached clients and immutable evidence."""
import json
import threading
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import text, event
from sqlalchemy.exc import IntegrityError

from backend.app.api import product_optimizer as api
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import User, Underlying, OptimizerResearch
from backend.app.services import optimizer_research as service
from backend.tests.test_product_optimizer import payload

@pytest.fixture
def setup(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path / 'research.db'}",connect_args={"check_same_thread":False})
    @event.listens_for(engine,'connect')
    def pragmas(conn,_): conn.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for ident in (1,2): session.add(User(id=ident,username=f'u{ident}',email=f'{ident}@test',password_hash='x'))
        session.add(Underlying(ticker='TEST',label='Test',ccy='EUR'));session.commit()
    current={'id':1}
    app=FastAPI();app.include_router(api.router)
    def sessions():
        with Session(engine) as session: yield session
    app.dependency_overrides[get_session]=sessions
    app.dependency_overrides[get_current_user]=lambda:User(id=current['id'],username='test',email='test',password_hash='x')
    def runner(req,**kwargs):
        context={'payoff':service.family_schema(req.product_family,req.objective),'market_snapshot':service.freeze_market(req.market)}
        yield {'type':'started','estimate':{'candidate_count':3}}
        c={'candidate_id':'C1','coupon':.1,'fair_value':1,'pricing_status':'PRICED','constraint_status':'REJECTED','validation_status':'NOT_SELECTED'}
        yield {'type':'progress','completed':1,'total':3,'candidate_id':'C1','candidate':c}
        result=service.partial_result(req,context,{'C1':c},{'candidate_total':3})
        result.update(complete=not kwargs['should_cancel'](),interruption='USER_STOP' if kwargs['should_cancel']() else None)
        yield {'type':'result','result':result}
    monkeypatch.setattr(api,'run_events',runner)
    client=TestClient(app)
    yield client,engine,current,runner
    service.shutdown();client.close();engine.dispose()

def body(**kwargs):
    return {'optimization':payload(),'title':'Essai Athena','intention':'Privilégier la protection','command_key':str(uuid4()),**kwargs}

def finished(client,ident,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        data=client.get(f'/api/product-optimizer/researches/{ident}').json()
        if data['status']!='RUNNING': return data
        time.sleep(.01)
    raise AssertionError('Job did not finish')

def test_saved_request_summary_market_and_prices_survive_client_disconnection(setup):
    client,engine,_,_=setup
    response=client.post('/api/product-optimizer/researches',json=body())
    assert response.status_code==200
    saved=finished(client,response.json()['id'])
    assert saved['status']=='COMPLETED'
    assert saved['result']['candidates'][0]['fair_value']==1
    assert saved['request']['market']['rate']==.03
    assert saved['context']['market_snapshot']['hash']
    assert 'Athena' in saved['summary'] and 'TEST' in saved['summary']
    assert saved['intention']=='Privilégier la protection'
    assert 'résolu entre' in saved['summary'] and '1000 paires indépendantes' in saved['summary']
    assert client.get('/api/product-optimizer/researches').json()['total']==1

def test_retry_is_idempotent_and_changed_request_is_rejected(setup):
    client,_,_,_=setup
    data=body();first=client.post('/api/product-optimizer/researches',json=data).json()
    second=client.post('/api/product-optimizer/researches',json=data).json()
    assert first['id']==second['id']
    finished(client,first['id']);data['title']='Autre intention'
    assert client.post('/api/product-optimizer/researches',json=data).status_code==409
    assert client.get('/api/product-optimizer/researches').json()['total']==1

def test_ownership_archive_filters_and_linked_new_version(setup):
    client,_,current,_=setup
    ident=client.post('/api/product-optimizer/researches',json=body()).json()['id'];saved=finished(client,ident)
    assert client.patch(f'/api/product-optimizer/researches/{ident}',json={'archived':True}).status_code==200
    assert client.get('/api/product-optimizer/researches').json()['total']==0
    assert client.get('/api/product-optimizer/researches?archived=true&q=protection').json()['total']==1
    assert client.get('/api/product-optimizer/researches?archived=true&family=autocall_athena&status=COMPLETED').json()['total']==1
    assert client.get('/api/product-optimizer/researches?archived=true&family=phoenix').json()['total']==0
    assert client.get('/api/product-optimizer/researches?status=invalid').status_code==422
    assert client.patch(f'/api/product-optimizer/researches/{ident}',json={'request':{}}).status_code==422
    child=client.post('/api/product-optimizer/researches',json=body(parent_id=ident)).json()
    assert child['parent_id']==ident and child['id']!=ident
    finished(client,child['id']);current['id']=2
    assert client.get('/api/product-optimizer/researches').json()['total']==0
    assert client.get(f'/api/product-optimizer/researches/{ident}').status_code==404
    assert client.post(f'/api/product-optimizer/researches/{ident}/cancel',json={}).status_code==404
    assert client.patch(f'/api/product-optimizer/researches/{ident}',json={'archived':False}).status_code==404
    assert client.post('/api/product-optimizer/researches',json=body(parent_id=ident)).status_code==404

def test_background_cancel_keeps_partial_prices_and_shared_admission(setup,monkeypatch):
    client,_,_,base=setup
    entered=threading.Event()
    def gated(req,**kwargs):
        entered.set()
        while not kwargs['should_cancel'](): time.sleep(.01)
        yield from base(req,**kwargs)
    monkeypatch.setattr(api,'run_events',gated)
    ident=client.post('/api/product-optimizer/researches',json=body()).json()['id']
    assert entered.wait(1)
    assert client.post('/api/product-optimizer/researches',json=body()).status_code==429
    assert client.post('/api/product-optimizer/run',json=payload()).status_code==429
    assert client.post(f'/api/product-optimizer/researches/{ident}/cancel',json={}).json()['stopping']
    saved=finished(client,ident)
    assert saved['status']=='PARTIAL' and saved['result']['interruption']=='USER_STOP'
    assert saved['result']['candidates'][0]['fair_value']==1
    assert api._capacity.acquire(blocking=False);api._capacity.release()

def test_error_keeps_received_prices_and_releases_capacity(setup,monkeypatch):
    client,_,_,base=setup
    def broken(req,**kwargs):
        for item in base(req,**kwargs):
            if item['type']=='result': raise RuntimeError('private internal data')
            yield item
    monkeypatch.setattr(api,'run_events',broken)
    ident=client.post('/api/product-optimizer/researches',json=body()).json()['id']
    saved=finished(client,ident)
    assert saved['status']=='FAILED' and saved['result']['candidates'][0]['fair_value']==1
    assert 'private internal data' not in json.dumps(saved)
    assert api._capacity.acquire(blocking=False);api._capacity.release()

def test_restart_marks_unfinished_job_and_frozen_evidence_cannot_be_rewritten(setup):
    client,engine,_,_=setup
    with Session(engine) as session:
        saved=service.create(session,service.ResearchCreate(**body()),1)
        ident=saved.id
    service.recover(engine)
    with Session(engine) as session:
        saved=session.get(OptimizerResearch,ident)
        assert saved.status=='INTERRUPTED'
        saved.archived=True;session.add(saved);session.commit()
    with engine.begin() as conn:
        with pytest.raises(IntegrityError): conn.execute(text('UPDATE optimizer_researches SET request_json=:v WHERE id=:id'),{'v':'{}','id':ident})
        with pytest.raises(IntegrityError): conn.execute(text('UPDATE optimizer_researches SET result_json=:v WHERE id=:id'),{'v':'{"changed":true}','id':ident})
        with pytest.raises(IntegrityError): conn.execute(text('UPDATE optimizer_researches SET title=:v WHERE id=:id'),{'v':'Changed evidence','id':ident})


def test_real_parallel_pricings_are_saved_by_detached_background_job(setup,monkeypatch):
    from backend.app.core.product_optimizer.service import run_events
    client,_,_,_=setup
    monkeypatch.setattr(api,'run_events',run_events)
    data=body()
    data['optimization']['ranges']['autocall_trigger']={'minimum':.8,'maximum':1.,'step':.2}
    data['optimization']['search']['parallel_workers']=2
    response=client.post('/api/product-optimizer/researches',json=data)
    assert response.status_code==200
    saved=finished(client,response.json()['id'],60)
    assert saved['status']=='COMPLETED' and saved['result']['complete']
    assert saved['result']['statistics']['priced']==2 and saved['result']['statistics']['failed']==0
    assert saved['result']['estimate']['execution']['workers']==2
    assert saved['result']['market_snapshot']['hash']==saved['context']['market_snapshot']['hash']
    for candidate in saved['result']['candidates']:
        assert candidate['fair_value'] is not None and candidate['pricing_input']['N']>=1000
        assert candidate['pricing_input']['script']==saved['context']['payoff']['script']
    assert api._capacity.acquire(blocking=False);api._capacity.release()
