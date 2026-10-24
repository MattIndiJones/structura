"""Meaningful scenario, privacy, valuation and configuration invariants."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from backend.app.services.agent_workshop.configuration import preview, schedule, funding_at
from backend.app.services.agent_workshop.diagnostic import diagnostic_defaults, observation, ready_action
from backend.app.services.agent_workshop.store import CampaignConfig, Store
from backend.app.services.agent_workshop.brain import action_schema


def config():
    return CampaignConfig(**diagnostic_defaults()).model_dump()


def test_calendar_zero_multiple_requests_and_distinct_requesters():
    c=config()
    c['calendar']=[{'month':1,'count':0,'slots':[]},{'month':2,'count':3,'slots':[]}]
    tasks=schedule(c)
    assert len(tasks)==3 and len({t['id'] for t in tasks})==3
    assert all(t['month']==1 for t in tasks)
    assert {t['requester'] for t in tasks}=={'hector','leonteq'}
    assert {t['template'] for t in tasks}=={'reverse_convertible','phoenix','autocall_athena'}
    assert all(t['requester'] not in t['recipients'] for t in tasks)


def test_self_response_and_unavailable_requester_are_rejected():
    c=config()
    c['calendar'][0]['slots'][0]['recipients']=['leonteq']
    with pytest.raises(ValueError,match='propre RFQ'):
        CampaignConfig(**c)
    c=config();c['participants'][0]['request_rfq']=False
    with pytest.raises(ValueError,match='Demandeur'):
        CampaignConfig(**c)


def test_funding_bound_variation_and_interpolation():
    c=config();curve,policy=funding_at(c,'bnp',12)
    assert curve==[[1, .00825],[3,.01125],[5,.01325]]
    c['participants'][2]['economy']['funding'][1]['pillars'][0][1]=9999
    with pytest.raises(ValueError,match='bornes'):
        CampaignConfig(**c)


def test_forecast_is_free_and_changes_with_workload_model_and_cadence(monkeypatch):
    monkeypatch.setattr('httpx.Client.request',lambda *a,**k:pytest.fail('Forecast attempted network'))
    c=config();original=preview(c)
    c['calendar'][0]['count']=10
    more=preview(c)
    assert more['rfqs']==13 and more['cost_usd']['central']>original['cost_usd']['central']
    c['cadences']['mtm_months']=1
    assert preview(c)['mtms_high']>more['mtms_high']
    c['cadences']['pricing_paths']=20000
    assert preview(c)['duration_minutes']['central']>more['duration_minutes']['central']
    c['model']='gpt-6-sol'
    assert preview(c)['cost_usd']['central']>more['cost_usd']['central']


def test_pricing_paths_respect_native_pricer_minimum():
    c=config()
    c['cadences']['pricing_paths']=500
    with pytest.raises(ValueError,match='pricing_paths'):
        CampaignConfig(**c)
    c['cadences']['pricing_paths']=1000
    assert CampaignConfig(**c).cadences.pricing_paths==1000


def test_accepted_client_offer_uses_native_accept_quote_argument():
    state={'cases':{'CASE-0001':{}},'client_offers':{'CASE-0001':{'quote_id':'quote-1'}}}
    current={'ready_steps':[{'tool':'accept_quote','case_id':'CASE-0001'}]}
    tool,args,solicitation=ready_action(state,'leonteq',current)
    assert tool=='accept_quote' and solicitation is None
    assert args=={'quote_id':'quote-1','justification':'Offre explicitement acceptée par le client.'}


def test_config_can_be_edited_only_before_first_run(tmp_path):
    store=Store(tmp_path);c=CampaignConfig(**config());state=store.create(c,1)
    c.name='Réglages corrigés';updated=store.configure(state['id'],1,c)
    assert updated['config']['name']==c.name
    updated['config_frozen_at']='2026-10-14T10:00:00Z';store.save(updated)
    with pytest.raises(ValueError,match='figée'):
        store.configure(state['id'],1,c)


def test_private_observation_and_dual_role_signatures(tmp_path):
    state=Store(tmp_path).initial_state(CampaignConfig(**config()),1)
    for actor in state['actors'].values():actor['registered']=True
    state['cases']={'CASE-0001':{'id':'CASE-0001','month':0,'template':'phoenix','nominal':1e6,
        'requester':'leonteq','recipients':['bnp','sg'],'rfq_sent':True,'declines':[],
        'pricing':{'user_params':{'COUPON':.08,'M_KI_BAR':.6},'maturity_date':'2029-01-01'}}}
    state['quotes']=[{'id':'quote-sg','bank':'sg','case_id':'CASE-0001','price':99}]
    tools=Mock(tokens={'bnp':'secret','leonteq':'secret'})
    bank=observation(state,'bnp',tools)
    assert bank['quotes']==[] and 'quote' in bank['available_tools']
    requester=observation(state,'leonteq',tools)
    assert requester['quotes']==state['quotes']
    state['actors']['bnp']['role']='issuer'
    schema=action_schema(state['actors']['bnp'],bank)
    assert 'quote' in [r['properties']['tool']['const'] for r in schema['anyOf']]


def test_three_native_payoffs_really_price_with_funding():
    from backend.app.core.payscript.parser import parse_script, resolve_constats
    from backend.app.core.payscript.engine import run_mc
    from backend.app.core.payscript.templates import TEMPLATES
    for template in ('reverse_convertible','phoenix','autocall_athena'):
        constats={'STARTDATE':{'date':'2025-01-15'},'MATURITYDATE':'2026-01-15',
                  'OBSERVATIONDATES':{'first_observation_date':'2026-01-15','end_date':'2026-01-15','roll_date':'2026-01-15',
                                      'frequency':'1Y','business_day_convention':'MODIFIED_FOLLOWING'}}
        from datetime import date
        compiled=resolve_constats(parse_script(TEMPLATES[template]['script']),constats,anchor=date(2025,1,15),currency='EUR')
        kwargs=dict(N=1000,model='constant',seed=42,user_params={'COUPON':.08,'M_KI_BAR':.6,'M_AC_BAR':1,'M_CPN_BAR':.7})
        inputs=(compiled,[{'name':'S1','ticker':'AIR.PA','spot0':100,'sigma':.23,'q':.02}],[[1]],.025,1)
        clean=run_mc(*inputs,**kwargs)
        funded=run_mc(*inputs,**kwargs,funding_curve=[[1,.02],[5,.03]])
        assert funded['price']<clean['price'],template


def test_contract_event_does_not_open_the_next_month_early():
    from datetime import date
    from backend.app.services.agent_workshop.diagnostic import calendar_month
    origin=date(2025,1,31)
    assert calendar_month(origin,date(2025,2,12))==0
    assert calendar_month(origin,date(2025,2,28))==1
    assert calendar_month(origin,date(2025,3,15))==1


def test_current_valuation_funding_preserves_booked_terms_and_units():
    from backend.app.core.deal_valuation import MtmRequest, valuation_funding
    from backend.app.core.valuation_context import deterministic_cashflow_pv
    market={'funding_curve':[[1,.01],[3,.015]],'funding_spread':.004}
    original=deepcopy(market)
    historical=valuation_funding(MtmRequest(),market,1)
    current=valuation_funding(MtmRequest(funding_curve=[[1,.05],[3,.06]],funding_source_reference='SCENARIO:dated'),market,1)
    assert current==([[1,.05],[3,.06]],0)
    assert market==original
    assert deterministic_cashflow_pv(1,1,r=.02,funding_curve=current[0]) < deterministic_cashflow_pv(1,1,r=.02,funding_curve=historical[0])
    with pytest.raises(ValueError,match='croissantes'):
        MtmRequest(funding_curve=[[3,.02],[1,.01]])


@pytest.mark.parametrize('operational', [False,True])
def test_blocking_action_stops_and_preserves_evidence_without_repair(tmp_path,operational):
    from backend.app.services.agent_workshop.diagnostic import checked_action
    from backend.app.services.agent_workshop.openai_model import BudgetReached
    state=Store(tmp_path).initial_state(CampaignConfig(**config()),1)
    manager=Mock(live=state)
    manager.consume_command.return_value=False
    manager.cancel.is_set.return_value=False
    manager.incident.return_value={'id':'incident-1'}
    tools=Mock(calls=[])
    tools.execute.side_effect=BudgetReached('cap') if operational else ValueError('duplicate booking')
    assert not checked_action(manager,tools,'hector','book',{'case_id':'CASE-0001','leg':'HECTOR_BUY'},'Test')
    assert state['status']=='ATTENTION'
    assert state['stop_reason']['kind']==('BUDGET' if operational else 'BLOCKING_ERROR')
    assert state['actions'][-1]['status']=='FAILED'
    assert state['checkpoint']['completed_tasks']==[]
    assert manager.incident.return_value['severity']==('OPERATIONAL_STOP' if operational else 'BLOCKING')


def test_roles_must_be_consistent_before_any_model_call():
    c=config()
    for p in c['participants']:p['request_rfq']=False
    with pytest.raises(ValueError,match='demandeur actif'):
        CampaignConfig(**c)


def test_recover_committed_quote_and_confirmation_without_repeating_writes():
    from backend.app.services.agent_workshop.tools import Tools
    case={'id':'CASE-0001','rfq_id':8,'requester':'leonteq','recipients':['bnp'],'native_terms_version':1,'nominal':10e6}
    state={'cases':{case['id']:case},'quotes':[],'accepted':{},'client_acceptances':[case['id']],
           'actors':{'bnp':{'entity':'BNP Paribas'}}}
    tools=object.__new__(Tools);tools.state=state
    tools.api=Mock(return_value={'product_terms_version':1,'quotes':[{'id':5,'provider':'BNP Paribas','price':99,
        'currency':'EUR','valid_until':'2026-01-15T17:00:00Z','firmness':'FIRM'}],
        'execution_agreements':[{'id':2,'state':'CONFIRMED','quote_id':5,'confirmed_at':'2026-01-15T10:00:00Z'}]})
    assert tools.recover_workflow()['writes']==0
    assert case['trade_confirmed'] and state['accepted'][case['id']]==state['quotes'][0]['id']
    tools.recover_workflow()
    assert len(state['quotes'])==1
    assert all(call.args[1]=='GET' for call in tools.api.call_args_list)


def test_reference_baseline_reuses_identities_without_copying_signing_keys(tmp_path):
    import json,sqlite3
    from backend.app.services.agent_workshop.instances import Instances
    c=config();state=Store(tmp_path).initial_state(CampaignConfig(**c),1)
    source=tmp_path/state['id'];instances=Instances(source,state)
    for key in state['actors']:
        if key=='achille':continue
        directory=source/'instances'/key;directory.mkdir(parents=True)
        with sqlite3.connect(directory/'structura.db') as db:
            db.executescript('CREATE TABLE identities(name TEXT); INSERT INTO identities VALUES("existing"); CREATE TABLE deals(id INTEGER);')
        (directory/'agent_credentials.json').write_text(json.dumps({'username':'existing'}),encoding='utf-8')
        (directory/'.jwt_secret').write_text('private-signing-key',encoding='utf-8')
    instances.capture_baseline()
    next_directory=tmp_path/('f'*32)/'instances'/'bnp';next_directory.mkdir(parents=True)
    fresh=Instances(tmp_path/('f'*32),state);fresh.restore_baseline(next_directory,'bnp')
    with sqlite3.connect(next_directory/'structura.db') as db:
        assert db.execute('SELECT name FROM identities').fetchone()[0]=='existing'
        assert db.execute('SELECT COUNT(*) FROM deals').fetchone()[0]==0
    assert not (next_directory/'.jwt_secret').exists()


def test_cancelled_request_is_not_reported_as_a_structura_bug(tmp_path):
    from backend.app.services.agent_workshop.diagnostic import checked_action
    state=Store(tmp_path).initial_state(CampaignConfig(**config()),1)
    manager=Mock(live=state);manager.consume_command.return_value=False;manager.cancel.is_set.return_value=True
    tools=Mock(calls=[]);tools.execute.side_effect=RuntimeError('stop')
    assert not checked_action(manager,tools,'hector','book',{},'Test')
    assert state['stop_reason']['kind']=='USER' and state['status']=='STOPPED'
    manager.incident.assert_not_called()


def test_controller_advances_empty_months_and_schedules_each_request_once(tmp_path,monkeypatch):
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from backend.app.services.agent_workshop import diagnostic,store as storage,instances,tools,brain
    c=config();c.update(start_date='2025-10-14',horizon_months=4)
    c['calendar']=[{'month':1,'count':0,'slots':[]},{'month':2,'count':2,'slots':[]},{'month':3,'count':1,'slots':[]}]
    repository=Store(tmp_path);state=repository.create(CampaignConfig(**c),1)
    monkeypatch.setattr(storage,'store',repository)
    workers=Mock();monkeypatch.setattr(instances,'Instances',Mock(return_value=workers))
    class CalendarTools:
        tokens={}
        def __init__(self,*a):self.started=[]
        def connect(self,*a):pass
        def recover_workflow(self):pass
        def relationship(self,key,peer,**k):state['actors'][key]['relations'][peer]={}
        def crm(self,*a):pass
        def close(self):pass
        def request(self,key,template,coupon,barrier,_task):
            self.started.append((state['month'],state['business_date'],_task['id']))
            state['cases'][_task['id']]={**_task,'pricing':{'value_date':(date.fromisoformat(state['business_date'])+relativedelta(days=4)).isoformat(),
                'maturity_date':'2027-01-15','payment_date':'2027-01-19'}}
    fake=CalendarTools();monkeypatch.setattr(tools,'Tools',lambda *a:fake)
    monkeypatch.setattr(brain,'prepare_model',lambda *a:None)
    monkeypatch.setattr(brain,'decide',lambda *a:pytest.fail('No ready decision; model must stay idle'))
    monkeypatch.setattr(diagnostic,'observation',lambda *a:{'available_tools':[]})
    monkeypatch.setattr(diagnostic,'check_books',lambda s:[{'case_id':c,'status':'COMPLETE'} for c in s['cases']])
    playwright=Mock();playwright.__enter__=Mock(return_value=playwright);playwright.__exit__=Mock(return_value=False)
    monkeypatch.setattr('playwright.sync_api.sync_playwright',lambda:playwright)
    manager=Mock(live=state,lease=None);manager.consume_command.return_value=False
    manager.pause.is_set.return_value=False;manager.cancel.is_set.return_value=False
    diagnostic.run(manager)
    assert state['status']=='COMPLETED'
    # The December anniversary is a Sunday; the RFQ opens on Monday.
    assert fake.started==[(1,'2025-11-14','CASE-0001'),(1,'2025-11-14','CASE-0002'),(2,'2025-12-15','CASE-0003')]
    assert state['usage']['model_calls']==0
    workers.stop.assert_called_once()
