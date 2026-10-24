"""Historical replay, single solicitations and contractual cash settlement."""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock, MagicMock

import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

from backend.app.services.agent_workshop.configuration import preview
from backend.app.services.agent_workshop.diagnostic import diagnostic_defaults, checked_action, review_due
from backend.app.services.agent_workshop.historical_market import freeze_market, historical_history, market_path
from backend.app.services.agent_workshop.store import CampaignConfig, Store


def test_existing_cache_last_close_without_future_data_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr('httpx.Client.request',lambda *a,**k:pytest.fail('Historical replay attempted network'))
    frame=pd.DataFrame({'close':[10.,11.,999.], 'price_close':[12.,13.,888.]},index=pd.to_datetime(['2021-10-13','2021-10-15','2026-10-15']))
    frame.attrs={'source':'existing-cache','currency':'EUR'}
    frame.to_parquet(tmp_path/'AIR.parquet')
    (tmp_path/'_ticker_map.json').write_text(json.dumps({'AIR':'AIR.PA'}))
    c=diagnostic_defaults();c.update(start_date='2021-10-14',end_date='2026-10-14')
    p=tmp_path/'historical.json';freeze_market(p,c,[tmp_path])
    data=json.loads(p.read_text(encoding='utf-8'))
    result=historical_history(data,['AIR.PA'],'2021-10-14','2021-10-14')
    assert set(result['prices']['AIR.PA'])=={12.}
    assert result['dates'][-1]=='2021-10-14'
    assert result['effective_dates']['AIR.PA']=='2021-10-13'
    assert result['provenance']['AIR.PA']['price_basis']=='RAW_CLOSE'
    later=historical_history(data,['AIR.PA'],'2026-10-01','2026-10-14')
    assert set(later['prices']['AIR.PA'])=={13.}
    assert '2026-10-15' not in data['series']['AIR.PA']
    assert pd.read_parquet(tmp_path/'AIR.parquet').equals(frame)


def test_defaults_historical_cutoff_and_no_repeated_decision_budget():
    c=diagnostic_defaults()
    assert c['start_date']==(date.today()-relativedelta(years=5)).isoformat()
    assert c['end_date']==date.today().isoformat()
    forecast=preview(c)
    assert forecast['end_month']==60
    assert forecast['model_calls']['central']==forecast['model_calls']['high']==16
    assert forecast['quotes']==8
    assert forecast['risk_reports_high']==366
    c['end_date']=(date.today()+relativedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='fenêtre historique'):
        CampaignConfig(**c)


def test_one_model_response_is_saved_before_execution_and_reused(tmp_path,monkeypatch):
    from backend.app.services.agent_workshop.brain import Decision
    c=CampaignConfig(**diagnostic_defaults());state=Store(tmp_path).initial_state(c,1)
    cid='CASE-0001';state['cases'][cid]={'id':cid,'native_terms_version':1}
    current={'ready_steps':[{'tool':'quote','case_id':cid}],'possible_actions':['Coter'], 'available_tools':['quote','decline']}
    decide=Mock(return_value=(Decision(tool='quote',args={'case_id':cid,'margin_bps':35},reason='Marge cible'),{'cost_usd':0,'input_tokens':0,'output_tokens':0}))
    monkeypatch.setattr('backend.app.services.agent_workshop.brain.decide',decide)
    manager=Mock(live=state);manager.consume_command.return_value=False;manager.cancel.is_set.return_value=False
    tools=Mock(calls=[]);tools.execute.side_effect=[ValueError('transport interrupted'),{'published':True}]
    manager.incident.return_value={'id':'test'}
    assert not checked_action(manager,tools,'bnp','quote',{'case_id':cid},'Test',model=True,current=current)
    assert next(iter(state['decisions'].values()))['status']=='READY'
    assert checked_action(manager,tools,'bnp','quote',{'case_id':cid},'Test',model=True,current=current)
    for _ in range(10):
        assert checked_action(manager,tools,'bnp','quote',{'case_id':cid},'Test',model=True,current=current)
    assert state['usage']['model_calls']==1
    assert decide.call_count==1 and tools.execute.call_count==2


def test_invalid_model_response_is_not_requested_again(tmp_path,monkeypatch):
    state=Store(tmp_path).initial_state(CampaignConfig(**diagnostic_defaults()),1)
    state['cases']['CASE-0001']={'id':'CASE-0001'}
    current={'ready_steps':[{'tool':'quote','case_id':'CASE-0001'}],'possible_actions':['Coter'], 'available_tools':['quote']}
    decide=Mock(side_effect=ValueError('malformed model response'))
    monkeypatch.setattr('backend.app.services.agent_workshop.brain.decide',decide)
    manager=Mock(live=state);manager.consume_command.return_value=False;manager.cancel.is_set.return_value=False;manager.incident.return_value={'id':'test'}
    tools=Mock(calls=[])
    for _ in range(3):
        assert not checked_action(manager,tools,'bnp','quote',{'case_id':'CASE-0001'},'Test',model=True,current=current)
    assert decide.call_count==1 and state['usage']['model_calls']==1
    tools.execute.assert_not_called()
    assert state['stop_reason']['kind']=='PROVIDER'


def test_normal_athena_has_five_business_day_observations(tmp_path):
    from backend.app.services.agent_workshop.tools import Tools
    from backend.app.core.payscript.parser import parse_script,resolve_constats
    c=diagnostic_defaults();c.update(start_date='2025-12-15',end_date='2026-10-14')
    state=Store(tmp_path).initial_state(CampaignConfig(**c),1)
    directory=tmp_path/state['id'];directory.mkdir()
    market_path(directory,c).write_text(json.dumps({'provider':'HISTORICAL_CACHE','series':{'AIR.PA':{'2025-12-12':100}},'provenance':{'AIR.PA':{'price_basis':'RAW_CLOSE'}},'cutoff':c['end_date']}))
    tool=object.__new__(Tools);tool.state=state;tool.directory=directory;tool.mail=Mock()
    p=next(p for p in c['products'] if p['template']=='autocall_athena')
    tool.request('client','autocall_athena',8,60,_task={'id':'CASE-0001','product':p,'requester':'leonteq','recipients':['bnp']})
    pricing=state['cases']['CASE-0001']['pricing']
    script=resolve_constats(parse_script(pricing['script']),pricing['constats'],anchor=date.fromisoformat(pricing['strike_date']),currency='EUR')
    points=script.echeancier.constatations
    assert len(points)==5 and [p.rang for p in points]==[1,2,3,4,5]
    assert all(p.jour.weekday()<5 for p in points)
    assert points[-1].jour.isoformat()=='2030-12-16'
    assert points[-1].jour_paiement.isoformat()=='2030-12-19'


def test_called_note_remains_a_receivable_until_its_payment():
    from backend.app.api.deals import _terminal_deal_state
    from backend.app.db.models import Deal
    d=Deal(reference='CALL',payment_date='2028-11-17')
    result={'event_date':'2022-02-14','settlement_date':'2022-02-17','settlement_amount':1.02,'realized_payout':1.02}
    assert _terminal_deal_state(d,'callé',result,date(2022,2,14))==('en_reglement',1.02)
    assert _terminal_deal_state(d,'callé',result,date(2022,2,17))==('callé',None)
    assert d.payment_date=='2028-11-17'


def test_closed_books_do_not_generate_repetitive_reviews():
    c=diagnostic_defaults();state={'business_date':'2025-10-14','month':48,'config':c}
    actor={'deals':[{'status':'callé'}],'last_review':{'date':'2025-01-14'}}
    assert not review_due(state,actor)
    actor['deals'][0]['status']='actif';actor['risk_checkpoint']={'month':48}
    assert not review_due(state,actor)
    state['business_date']=c['end_date']
    assert review_due(state,actor)


def test_manual_replay_stops_at_first_proven_call(monkeypatch):
    from types import SimpleNamespace
    from backend.app.api import deals
    monkeypatch.setattr(deals,'business_today',lambda:date(2026,10,14))
    events=[SimpleNamespace(id=i,event_date=f'{2021+i}-12-14',t_years=i,event_index=i,
                            status='observé' if i<2 else 'futur',
                            fixing_status='VALIDATED' if i<2 else 'EXPECTED',
                            data_category='FIXING_OFFICIAL' if i<2 else 'EXPECTED') for i in range(3)]
    monkeypatch.setattr(deals,'_get_events',lambda *_:events)
    replay=Mock(side_effect=[{'outcome':'en_cours'},
                            {'outcome':'callé','event_id':1,'settlement_date':'2022-12-19'}])
    monkeypatch.setattr(deals,'replay_official_fixings',lambda d,p:(replay(d,p),[]))
    result,failures=deals._user_exception_lifecycle_evaluation(SimpleNamespace(id=1),None)
    assert result['outcome']=='callé' and not failures
    assert len(replay.call_args.args[1])==2


def test_official_athena_replay_keeps_coupon_rank_and_payment(tmp_path):
    from types import SimpleNamespace
    from backend.app.services.agent_workshop.tools import Tools
    from backend.app.core.lifecycle_controls import replay_official_fixings
    from backend.app.api.deals import _terminal_deal_state
    c=diagnostic_defaults();c.update(start_date='2021-12-14',end_date='2026-10-14')
    state=Store(tmp_path).initial_state(CampaignConfig(**c),1)
    directory=tmp_path/state['id'];directory.mkdir()
    market_path(directory,c).write_text(json.dumps({'provider':'HISTORICAL_CACHE','series':{'AIR.PA':{'2021-12-14':100}},'provenance':{},'cutoff':c['end_date']}))
    tools=object.__new__(Tools);tools.state=state;tools.directory=directory;tools.mail=Mock()
    product=next(p for p in c['products'] if p['template']=='autocall_athena')
    tools.request('client','autocall_athena',8,60,_task={'id':'CASE-0001','product':product,'requester':'leonteq','recipients':['bnp']})
    pricing=state['cases']['CASE-0001']['pricing']
    deal=SimpleNamespace(script_snapshot=pricing['script'],market_snapshot_json=json.dumps({'constats':pricing['constats'],'user_params':pricing['user_params']}),
                         underlyings_json=json.dumps(pricing['underlyings']),strike_date=pricing['strike_date'],
                         value_date=pricing['value_date'],maturity_date=pricing['maturity_date'],
                         payment_date=pricing['payment_date'],settlement_date=None,T=5.,devise='EUR')
    name=pricing['underlyings'][0]['name']
    events=[SimpleNamespace(id=i,event_index=i,t_years=t,event_date=d,spots_json=json.dumps({name:s}))
            for i,t,d,s in [(1,0.,'2021-12-14',100),(2,365/365.25,'2022-12-14',110)]]
    result,failures=replay_official_fixings(deal,events)
    assert not failures and result['outcome']=='callé'
    assert result['settlement_date']=='2022-12-19'
    assert result['settlement_amount']==pytest.approx(1.08)
    assert _terminal_deal_state(deal,'callé',result,date(2022,12,14))==('en_reglement',1.08)


def test_controller_stops_at_cutoff_with_open_position(tmp_path,monkeypatch):
    from backend.app.services.agent_workshop import diagnostic,store as store_module,instances,tools,brain,coverage
    import playwright.sync_api
    c=diagnostic_defaults();c.update(start_date='2021-10-14',end_date='2026-10-14')
    store=Store(tmp_path);state=store.create(CampaignConfig(**c),1)
    state.update(business_date=c['end_date'],month=60)
    position={'id':1,'status':'actif','settlement_status':'SETTLED'}
    state['actors']={'leonteq':{'deals':[position],'last_review':{'date':c['end_date'],'active_deals':1}}}
    manager=Mock(live=state,lease=None)
    manager.consume_command.return_value=False;manager.cancel.is_set.return_value=False;manager.pause.is_set.return_value=False
    monkeypatch.setattr(store_module,'store',store)
    monkeypatch.setattr(store_module,'source_manifest',lambda:{'source_sha256':{}})
    monkeypatch.setattr(instances,'Instances',Mock(return_value=Mock()))
    monkeypatch.setattr(tools,'Tools',Mock(return_value=Mock()))
    monkeypatch.setattr(brain,'prepare_model',Mock())
    monkeypatch.setattr(coverage,'exercise',Mock())
    monkeypatch.setattr(diagnostic,'participants',lambda c:{})
    monkeypatch.setattr(diagnostic,'schedule',lambda c:[])
    monkeypatch.setattr(diagnostic,'check_books',lambda s:[])
    monkeypatch.setattr(diagnostic,'checked_action',Mock(return_value=True))
    monkeypatch.setattr(diagnostic,'observation',lambda *a:{'available_tools':[]})
    monkeypatch.setattr(playwright.sync_api,'sync_playwright',MagicMock())
    diagnostic.run(manager)
    assert state['status']=='COMPLETED' and state['completion_scope']=='HISTORICAL_CUTOFF'
    assert state['business_date']=='2026-10-14' and state['open_positions']['leonteq']==[position]
    assert position['status']=='actif' and state['usage']['model_calls']==0
