"""Offline checks of isolation, privacy, bilateral contracts and real bookings."""
from copy import deepcopy
from datetime import date, timedelta
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select
from backend.app.api import trading, pricing
from backend.app.api import deals as deals_api
from backend.app.core.workflow import FixingStatus, DataCategory
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import Entity, User, Counterparty, Deal
from backend.app.services.agent_workshop.store import Store, CampaignConfig
from backend.app.services.agent_workshop.engine import observation, check_books, Manager
from backend.app.services.agent_workshop.brain import action_schema
from backend.app.services.agent_workshop.lease import CampaignLease
from backend.app.services.scenario_market import create_market, history
from backend.app.runtime import business_today, data_path


@pytest.fixture
def client():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Entity(id=1,name='Banque'));s.add(Entity(id=2,name='Autre'))
        s.add(User(id=1,username='agent',email='a@example.invalid',password_hash='unused',entity_id=1,role='user'))
        s.add(Counterparty(id=1,name='Client'));s.commit()
    identity=SimpleNamespace(id=1,entity_id=1,role='user')
    app=FastAPI();app.include_router(trading.router);app.include_router(pricing.router)
    def session():
        with Session(engine) as s: yield s
    app.dependency_overrides[get_session]=session
    app.dependency_overrides[get_current_user]=lambda:identity
    with TestClient(app) as c: yield c,identity,engine
    engine.dispose()


def relationship(c,**over):
    data={'counterparty_id':1,'reference':'REL-COMMON','status':'ACTIVE','effective_date':date.today().isoformat(),
        'note_distribution_allowed':True,'documentation_reference':'Programme fictif','gross_notional_limit':10000000}
    data.update(over)
    response=c.post('/api/trading/relationships',json=data)
    assert response.status_code==201,response.text
    return response.json()


def priced_booking(c, relation, side='SELL',issuer='Banque',reference='TRADE-0001',coupon=.08):
    start=date.today();maturity=start+timedelta(days=183);payment=maturity+timedelta(days=4)
    script='UNDERLYING AAA\nPARAM COUPON\nCONSTAT StartDate\nCONSTAT MaturityDate\nAT StartDate:\n  AAA.spot0 = AAA.spot@StartDate\nAT MaturityDate:\n  PAY 1 "Capital"\n  PAY COUPON "Coupon"'
    payload={'script':script,'underlyings':[{'name':'AAA','ticker':'AAA','ccy':'EUR','spot0':100,'sigma':.2,'q':.02}],
        'corr_matrix':[[1]],'r':.025,'T':183/365.25,'N':1000,'user_params':{'COUPON':coupon},
        'strike_date':str(start),'value_date':str(start),'maturity_date':str(maturity),'payment_date':str(payment),'settlement_ccy':'EUR',
        'constats':{'STARTDATE':{'date':str(start)},'MATURITYDATE':str(maturity)}}
    priced=c.post('/api/price',json=payload);assert priced.status_code==200,priced.text
    result=priced.json()
    return {'trade_reference':reference,'relationship_id':relation['id'],'issuer':issuer,'our_side':side,'instrument_reference':'NOTE-COMMON',
        'deal':{'sens':'achat' if side=='SELL' else 'vente','contrepartie':'Client','devise':'EUR','nominal':1000000,
        'product_type':'Coupon note','fair_value':result['price']*100,'price_traded':105,'trade_date':str(start),
        **{k:payload[k] for k in ['strike_date','value_date','maturity_date','payment_date','T']},
        'underlyings':[{'name':'AAA','ticker':'AAA','ccy':'EUR','s0_abs':100}], 'script_snapshot':script,
        'observation_times':[], 'market_snapshot':{},'pricing_receipt':result['pricing_receipt'],'transaction_format':'EMTN','instrument_family':'NOTE','documentation_reference':'Programme fictif'}}


def test_real_pricing_booking_idempotence_and_contract_identity(client):
    c,_,engine=client;r=relationship(c);payload=priced_booking(c,r)
    a=c.post('/api/trading/book-note',json=payload);assert a.status_code==201,a.text
    b=c.post('/api/trading/book-note',json=payload);assert b.status_code==201,b.text
    assert a.json()['deal_id']==b.json()['deal_id']
    changed=deepcopy(payload);changed['deal']['price_traded']=104
    assert c.post('/api/trading/book-note',json=changed).status_code==409
    with Session(engine) as s: assert len(s.exec(select(Deal)).all())==1
    changed=priced_booking(c,r,reference='TRADE-0002',coupon=.09)
    assert c.post('/api/trading/book-note',json=changed).status_code==409
    proof=c.post(f"/api/trading/executions/{a.json()['id']}/settle",json={'reference':'DVP-TEST'})
    assert proof.status_code==200 and proof.json()['settlement_status']=='SETTLED'


def test_incomplete_contract_and_external_resale_are_refused(client):
    c,_,_=client;r=relationship(c,status='PENDING',documentation_reference='')
    response=c.post('/api/trading/book-note',json=priced_booking(c,r));assert response.status_code==422
    edited={k:v for k,v in r.items() if k not in {'id','version'}}
    edited.update(status='ACTIVE',documentation_reference='Programme fictif',expected_version=1)
    assert c.put('/api/trading/relationships/'+str(r['id']),json=edited).status_code==200
    response=c.post('/api/trading/book-note',json=priced_booking(c,r,issuer='Banque externe'))
    assert response.status_code==422 and 'insuffisante' in response.text


def test_scope_version_and_otc_without_master(client):
    c,identity,_=client;r=relationship(c)
    identity.entity_id=2
    assert c.get('/api/trading/relationships').json()==[]
    identity.entity_id=1
    data={k:v for k,v in r.items() if k not in {'id','version'}};data['expected_version']=2
    assert c.put('/api/trading/relationships/'+str(r['id']),json=data).status_code==409
    data.pop('expected_version');data.update(reference='REL-OTC',otc_allowed=True,csa_required=True)
    assert c.post('/api/trading/relationships',json=data).status_code==422


def test_store_and_private_agent_observations(tmp_path):
    store=Store(tmp_path);state=store.create(CampaignConfig(months=1),1)
    state['messages']=[{'id':'secret','from':'bnp','to':'hector','case_id':'','body':'Private bank reply'},
        {'id':'public','from':'hector','to':'client','case_id':'','body':'Client offer'}]
    obs=observation(state,'sg',SimpleNamespace(tokens={}))
    assert obs['messages']==[] and obs['quotes']==[]
    assert store.list(2)==[]
    with pytest.raises(ValueError):store.path('../not-a-campaign')


def test_synthetic_history_cannot_look_ahead(tmp_path,monkeypatch):
    path=tmp_path/'scenario.json';create_market(path,'2025-10-08',42,12)
    result=history(['AIR.PA'],'2025-10-01','2025-10-08',path=path,as_of=date(2025,10,8))
    assert result['provider']=='SYNTHETIC_SCENARIO' and result['dates'][-1]=='2025-10-08'
    assert 'error' in history(['AIR.PA'],'2025-10-01','2025-10-09',path=path,as_of=date(2025,10,8))
    clock=tmp_path/'clock.json';clock.write_text(json.dumps({'now':'2025-10-08T09:00:00'}))
    monkeypatch.setenv('STRUCTURA_BUSINESS_CLOCK',str(clock));assert business_today()==date(2025,10,8)
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(tmp_path));assert data_path('structura.db')==tmp_path/'structura.db'


def test_note_rejects_otc_netting_and_changed_issuer_or_documentation(client):
    c,_,_=client;r=relationship(c)
    payload=priced_booking(c,r)
    payload['deal']['ccr_netting_set_id']=123
    assert c.post('/api/trading/book-note',json=payload).status_code==422
    payload['deal']['ccr_netting_set_id']=None
    payload['deal']['documentation_reference']='Other agreement'
    assert c.post('/api/trading/book-note',json=payload).status_code==422
    payload['deal']['documentation_reference']='Programme fictif'
    assert c.post('/api/trading/book-note',json=payload).status_code==201
    changed=priced_booking(c,r,reference='TRADE-0002',issuer='Other issuer',side='BUY')
    assert c.post('/api/trading/book-note',json=changed).status_code==409


def test_client_book_is_required_and_price_mismatch_is_detected():
    fields=dict(case_id='CASE-001',trade_reference='BANK',instrument_reference='NOTE',issuer='BNP',nominal=10e6,
        currency='EUR',price_traded=100,value_date='2025-10-08',contract_hash='terms')
    state={'cases':{'CASE-001':{'id':'CASE-001'}},'actors':{
        'hector':{'deals':[dict(fields,leg='HECTOR_BUY',our_side='BUY'),dict(fields,trade_reference='CLIENT',price_traded=101,leg='HECTOR_SELL',our_side='SELL')]},
        'bnp':{'deals':[dict(fields,leg='BANK_SELL',our_side='SELL')]},'client':{'deals':[]}}}
    assert check_books(state)[0]['status']=='MATCHED'
    state['actors']['client']['deals'].append(dict(fields,trade_reference='CLIENT',price_traded=101,leg='CLIENT_BUY',our_side='BUY'))
    assert check_books(state)[0]['status']=='COMPLETE'
    state['actors']['client']['deals'][0]['price_traded']=99
    assert check_books(state)[0]['status']=='MISMATCH'
    assert check_books(state)[0]['client_volume']==0


def test_lease_and_published_snapshot_are_independent(tmp_path,monkeypatch):
    lease=CampaignLease(tmp_path)
    with pytest.raises(ValueError): CampaignLease(tmp_path)
    lease.close()
    second=CampaignLease(tmp_path);second.close()
    from backend.app.services.agent_workshop import engine as engine_module
    local_store=Store(tmp_path/'campaigns')
    monkeypatch.setattr(engine_module,'store',local_store)
    state=local_store.create(CampaignConfig(months=1),1)
    manager=Manager();manager.key=state['id'];manager.published=deepcopy(state);manager.live=state
    state['actors']['hector']['status']='Unpublished mutation'
    snap=manager.snapshot(state['id'])
    assert snap['actors']['hector']['status']=='À préparer'
    snap['actors']['hector']['status']='Consumer mutation'
    assert manager.published['actors']['hector']['status']=='À préparer'


def test_official_user_fixing_survives_missing_provider(monkeypatch):
    event=SimpleNamespace(current_fixing_version_id=12,fixing_status=FixingStatus.VALIDATED.value,
        spots_json='{"AAA":100}',data_category=DataCategory.FIXING_OFFICIAL.value)
    version=SimpleNamespace(capture_actor_type='USER')
    session=SimpleNamespace(get=lambda model,key:version)
    monkeypatch.setattr(deals_api,'_auto_yahoo_event_values',lambda *args:({}, {}, [{'code':'MISSING'}],False))
    monkeypatch.setattr(deals_api,'_auto_yahoo_exception',lambda *args,**kw:pytest.fail('An official fixing must not reopen'))
    assert deals_api._auto_validate_yahoo_event(SimpleNamespace(),event,[],{},session,1)==(False,None)
    assert event.fixing_status==FixingStatus.VALIDATED.value


def test_manual_maturity_uses_contract_date_not_rounded_time(monkeypatch):
    event=SimpleNamespace(id=1,event_date='2026-04-08',t_years=.4983,fixing_status=FixingStatus.VALIDATED.value,data_category=DataCategory.FIXING_OFFICIAL.value)
    monkeypatch.setattr(deals_api,'business_today',lambda:date(2026,4,8))
    monkeypatch.setattr(deals_api,'_get_events',lambda *args:[event])
    monkeypatch.setattr(deals_api,'replay_official_fixings',lambda *args:({'outcome':'final'},[]))
    result,failures=deals_api._user_exception_lifecycle_evaluation(SimpleNamespace(id=1,T=182/365.25,maturity_date='2026-04-08'),None)
    assert result['outcome']=='final' and not failures


def test_pending_booking_choices_do_not_repeat_the_completed_buy(tmp_path):
    state=Store(tmp_path).create(CampaignConfig(months=1),1)
    state['cases']['CASE-001']={'id':'CASE-001','month':0,'rfq_sent':True,'declines':[]}
    state['quotes']=[{'id':'q1','bank':'bnp','case_id':'CASE-001'}]
    state['accepted']['CASE-001']='q1';state['client_offers']['CASE-001']={'quote_id':'q1'};state['client_acceptances']=['CASE-001']
    state['actors']['hector']['deals']=[dict(id=1,case_id='CASE-001',leg='HECTOR_BUY',issuer='BNP',our_side='BUY',nominal=1e6,price_traded=100,settlement_status='SETTLED')]
    state['actors']['hector']['history']=[{'tool':'mail','status':'SUCCESS','result':{}},{'tool':'wait','status':'SUCCESS','result':{}}]
    obs=observation(state,'hector',SimpleNamespace(tokens={'hector':'private'}))
    assert obs['book_tasks']=={'CASE-001':['HECTOR_SELL']}
    assert obs['cases'][0]['client_accepted'] is True and obs['cases'][0]['accepted_quote_id']=='q1'
    assert 'wait' not in obs['available_tools'] and 'mail' not in obs['available_tools']
    schema=action_schema(state['actors']['hector'],obs)
    branch=next(b for b in schema['anyOf'] if b['properties']['tool']['const']=='book')
    assert branch['properties']['args']['properties']['leg']['enum']==['HECTOR_SELL']


def test_control_from_another_controller_is_acknowledged(tmp_path,monkeypatch):
    from backend.app.services.agent_workshop import engine as engine_module
    local_store=Store(tmp_path);state=local_store.create(CampaignConfig(months=1),1)
    state['status']='RUNNING';local_store.save(state)
    monkeypatch.setattr(engine_module,'store',local_store)
    reader=Manager();reader.control(state['id'],'pause')
    assert reader.snapshot(state['id'])['status']=='PAUSING'
    runner=Manager();runner.key=state['id'];runner.live=state
    assert runner.consume_command() is False and runner.pause.is_set()
    reader.control(state['id'],'resume');runner.consume_command()
    assert not runner.pause.is_set()
    reader.control(state['id'],'stop');assert runner.consume_command() is True


def test_contract_draw_and_current_quote_choices(tmp_path):
    from backend.app.services.agent_workshop.store import contract_mandate
    state=Store(tmp_path).create(CampaignConfig(contract_scenario='random',seed=17),1)
    assert contract_mandate(state)==contract_mandate(deepcopy(state))
    state['config']['contract_scenario']='all_complete'
    assert all(v['note_ready'] and v['otc_ready'] for k,v in contract_mandate(state).items() if k!='client')
    observation_data={'connected':True,'available_tools':['offer'],'cases':[
        {'id':'CASE-001','client_accepted':True},{'id':'CASE-002','client_accepted':False}],
        'quotes':[{'id':'old','case_id':'CASE-001'},{'id':'new-cheap','case_id':'CASE-002'},{'id':'new-expensive','case_id':'CASE-002'}]}
    schema=action_schema(state['actors']['hector'],observation_data)
    assert schema['anyOf'][0]['properties']['args']['properties']['quote_id']['enum']==['new-cheap','new-expensive']


def test_normal_instance_keeps_its_local_calendar_day(monkeypatch):
    from backend.app import runtime
    class LocalDate(date):
        @classmethod
        def today(cls):return cls(2026,10,9)
    monkeypatch.delenv('STRUCTURA_BUSINESS_CLOCK',raising=False)
    monkeypatch.setattr(runtime,'date',LocalDate)
    assert runtime.business_today()==date(2026,10,9)


def test_all_documentation_refusals_close_the_need_without_a_fake_trade(tmp_path,monkeypatch):
    from backend.app.services.agent_workshop.tools import Tools
    state=Store(tmp_path).create(CampaignConfig(include_sg=False),1)
    state['cases']['CASE-001']={'id':'CASE-001','declines':[]}
    tools=Tools(tmp_path,state,None)
    def refuse(*args):raise ValueError('EXPECTED_REFUSAL : missing contracts')
    monkeypatch.setattr(tools,'eligible',refuse)
    try:
        for bank in ('bnp','ca'):
            state['messages'].append({'to':bank,'case_id':'CASE-001'})
            with pytest.raises(ValueError,match='EXPECTED_REFUSAL'):tools.quote(bank,'CASE-001')
        assert state['cases']['CASE-001']['outcome']=='NO_QUOTE'
        assert check_books(state)[0]['status']=='NO_TRADE'
        assert not state['quotes'] and not any(a['deals'] for a in state['actors'].values())
        result=tools.execute('achille','report',{'kind':'USAGE','description':'Proposition commerciale à corriger'})
        assert result['source']=='AGENT'
        with pytest.raises(ValueError,match='register'):tools.execute('achille','api',{'path':'/api/deals'})
    finally:tools.close()


def test_atomic_save_retries_a_brief_windows_reader_lock(tmp_path,monkeypatch):
    from pathlib import Path
    from backend.app.services.agent_workshop.persistence import atomic_write
    real_replace=Path.replace;attempts=[]
    def locked_then_available(self,target):
        attempts.append(target)
        if len(attempts)<3:raise PermissionError('Transient Windows read lock')
        return real_replace(self,target)
    monkeypatch.setattr(Path,'replace',locked_then_available)
    target=tmp_path/'state.json';target.write_text('old')
    atomic_write(target,'new')
    assert target.read_text()=='new' and len(attempts)==3
    assert not list(tmp_path.glob('*.next'))


def test_risk_choices_exclude_a_counterparty_already_reviewed_today(tmp_path):
    state=Store(tmp_path).create(CampaignConfig(months=1),1)
    actor=state['actors']['hector']
    actor['otc_sets']={'bnp':1,'sg':2}
    actor['risk_runs']=[{'date':state['business_date'],'party':'bnp'}]
    state['cases']['CASE-001']={'id':'CASE-001','month':0,'rfq_sent':False,'declines':[]}
    obs=observation(state,'hector',SimpleNamespace(tokens={'hector':'private'}))
    assert obs['risk_parties']==['sg']
    schema=action_schema(actor,obs)
    risk=next(b for b in schema['anyOf'] if b['properties']['tool']['const']=='risk')
    assert risk['properties']['args']['properties']['party']['enum']==['sg']


@pytest.mark.parametrize('prefix',['/api/agent-workshop','/api/admin/agent-workshop'])
def test_actor_installation_cannot_inspect_or_control_parent_campaigns(monkeypatch,prefix):
    from backend.app.api import agent_workshop
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD','1')
    monkeypatch.setattr(agent_workshop.manager,'snapshot',lambda *a:pytest.fail('Parent state must remain inaccessible'))
    app=FastAPI();app.include_router(agent_workshop.router);app.include_router(agent_workshop.admin_router)
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=1,role='admin')
    with TestClient(app) as c:
        for path in ('','/models','/'+'a'*32,'/'+'a'*32+'/export'):
            assert c.get(prefix+path).status_code==403
        assert c.post(prefix+'/'+'a'*32+'/start').status_code==403
        assert c.post(prefix,json={}).status_code==403


def test_regular_user_can_run_private_recipes_without_admin_rights(tmp_path,monkeypatch):
    from backend.app.api import agent_workshop
    local_store=Store(tmp_path)
    monkeypatch.delenv('STRUCTURA_WORKSHOP_CHILD',raising=False)
    monkeypatch.setattr(agent_workshop,'store',local_store)
    monkeypatch.setattr(agent_workshop.manager,'snapshot',local_store.load)
    app=FastAPI();app.include_router(agent_workshop.router);app.include_router(agent_workshop.admin_router)
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=3,role='user')
    other=local_store.create(CampaignConfig(months=1),1)
    with TestClient(app) as c:
        created=c.post('/api/agent-workshop',json={'months':1})
        assert created.status_code==201 and created.json()['owner']==3
        key=created.json()['id']
        assert c.get('/api/agent-workshop/'+key).status_code==200
        assert c.get('/api/agent-workshop/'+other['id']).status_code==404
        assert [r['id'] for r in c.get('/api/agent-workshop').json()]==[key]
        assert c.get('/api/admin/agent-workshop').status_code==403


def test_native_request_is_visible_before_response_and_refusals_are_retained(tmp_path,monkeypatch):
    import httpx
    from backend.app.services.agent_workshop import engine as controller
    from backend.app.services.agent_workshop.brain import Decision
    from backend.app.services.agent_workshop.tools import Tools
    local_store=Store(tmp_path);state=local_store.create(CampaignConfig(),1)
    monkeypatch.setattr(controller,'store',local_store)
    runner=Manager();runner.key=state['id'];runner.live=state
    decision=Decision(tool='api',args={'path':'/api/trading/book-note','password':'secret'},reason='Booker dans mon installation')
    runner.begin_activity('hector','THINKING',tasks=['Booker la vente au client'])
    thinking=runner.snapshot(state['id'])
    runner.begin_activity('hector','EXECUTING',decision)
    assert thinking['activity']['phase']=='THINKING'
    assert thinking['activity']['tool'] is None
    assert runner.snapshot(state['id'])['activity']['args']['password']=='[REDACTED]'
    state['actors']['hector']['url']='http://private.invalid'
    tools=Tools(tmp_path,state,None,on_activity=runner.request_activity)
    tools.http.close()
    def reject(request):
        pending=runner.snapshot(state['id'])['activity']
        assert pending['request']=={'method':'POST','path':'/api/trading/book-note','status':'PENDING'}
        assert pending['http_calls']==[]
        assert state['actions']==[]
        return httpx.Response(422,json={'detail':'Documentation absente'})
    tools.http=httpx.Client(transport=httpx.MockTransport(reject))
    try:
        with pytest.raises(ValueError,match='Documentation absente'):
            tools.api('hector','POST','/api/trading/book-note',{})
        finished=runner.snapshot(state['id'])['activity']
        assert finished['request']['status']==422
        assert finished['http_calls']==[{'method':'POST','path':'/api/trading/book-note','status':422}]
        runner.request_activity('bnp',{'path':'/api/price'},[])
        assert runner.snapshot(state['id'])['activity']==finished
    finally:tools.close()


def test_controller_publishes_decision_execution_and_clears_activity_on_stop(tmp_path,monkeypatch):
    import httpx
    import playwright.sync_api
    from backend.app.services.agent_workshop import engine as controller
    from backend.app.services.agent_workshop.brain import Decision
    from backend.app.services.agent_workshop.tools import Tools
    local_store=Store(tmp_path);state=local_store.create(CampaignConfig(coaching=False),1)
    monkeypatch.setattr(controller,'store',local_store)
    runner=Manager();runner.key=state['id'];runner.live=state
    observed=[]
    class PrivateInstances:
        def __init__(self,*args):pass
        def start(self):state['actors']['hector']['url']='http://private.invalid'
        def stop(self):
            assert runner.snapshot(state['id'])['status']=='STOPPING'
            observed.append('closed')
        def provision_owner(self,*args):pass
    class Browser:
        def close(self):pass
    class Playwright:
        def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw:Browser()))
        def __exit__(self,*args):pass
    class NativeTools(Tools):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.http.close()
            self.http=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'deals':[]})))
        def execute(self,key,tool,args):
            observed.append(runner.snapshot(state['id'])['activity']['phase'])
            result=self.api(key,'GET','/api/deals')
            runner.cancel.set()
            return result
    def decide(*args):
        observed.append(runner.snapshot(state['id'])['activity']['phase'])
        return Decision(tool='api',args={'path':'/api/deals'},reason='Lire mon book'),{'seconds':.01}
    monkeypatch.setattr(controller,'Instances',PrivateInstances)
    monkeypatch.setattr(controller,'Tools',NativeTools)
    monkeypatch.setattr(controller,'observation',lambda *args:{'messages':[],'possible_actions':['Lire mon book']})
    monkeypatch.setattr(controller,'decide',decide)
    monkeypatch.setattr(playwright.sync_api,'sync_playwright',lambda:Playwright())
    runner.run()
    final=runner.snapshot(state['id'])
    assert observed==['THINKING','EXECUTING','closed']
    assert final['status']=='STOPPED' and final['activity'] is None and final['active_actor'] is None
    assert final['actions'][0]['http_calls']==[{'method':'GET','path':'/api/deals','status':200}]
    assert final['actions'][0]['started_at'] and final['actions'][0]['completed_at']
    assert final['actions'][0]['duration_seconds']>=0


def test_snapshot_distinguishes_a_stale_running_record_from_an_external_controller(tmp_path,monkeypatch):
    from backend.app.services.agent_workshop import engine as controller
    local_store=Store(tmp_path);state=local_store.create(CampaignConfig(),1)
    state['status']='RUNNING';local_store.save(state)
    monkeypatch.setattr(controller,'store',local_store)
    reader=Manager()
    assert reader.snapshot(state['id'])['controller_active'] is False
    assert not (local_store.path(state['id'])/'run.lock').exists()
    lease=CampaignLease(local_store.path(state['id']))
    try:
        assert reader.snapshot(state['id'])['controller_active'] is True
    finally:lease.close()
    assert reader.snapshot(state['id'])['controller_active'] is False


def test_campaign_listing_uses_current_snapshot_without_exposing_other_owners(tmp_path,monkeypatch):
    from backend.app.api import agent_workshop
    local_store=Store(tmp_path)
    mine=local_store.create(CampaignConfig(),3);mine.update(status='RUNNING',turns=0);local_store.save(mine)
    local_store.create(CampaignConfig(),1)
    monkeypatch.setattr(agent_workshop,'store',local_store)
    calls=[]
    def snapshot(key):
        calls.append(key)
        return {**mine,'status':'COMPLETED','turns':47,'controller_active':False}
    monkeypatch.setattr(agent_workshop.manager,'snapshot',snapshot)
    rows=agent_workshop.listing(SimpleNamespace(id=3))
    assert calls==[mine['id']] and len(rows)==1
    assert rows[0]['status']=='COMPLETED' and rows[0]['turns']==47
