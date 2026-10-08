"""Contract branches, script-driven fields and genuine multi-flow pricing."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.product_optimizer import service, validation
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.families import ADAPTERS, family_schema
from backend.app.core.product_optimizer.capabilities import capabilities
from backend.app.core.product_optimizer.statistics import summarize_paths
from backend.app.core.payscript.engine import run_mc, _eval_paths
from backend.app.core.payscript.parser import parse_script
from backend.app.core.schemas import PricingRequest
from backend.tests.test_product_optimizer import payload, api_client


def test_frontend_schema_fixture_tracks_current_server_scripts():
    fixture=Path(__file__).resolve().parents[2]/'frontend/src/utils/__fixtures__/optimizerFamilies.json'
    assert json.loads(fixture.read_text(encoding='utf-8'))==capabilities()['families']


def family_payload(key):
    data=payload();data['product_family']=key
    if key in ('phoenix','phoenix_memoire'):
        data['ranges']['coupon_barrier']={'minimum':.7,'maximum':.7,'step':.05}
    if key=='autocall_barriere_degressive':
        data['payoff_settings']={'decrement':.05,'floor':.8,'first_decrease_rank':2}
    if key=='reverse_convertible':
        del data['ranges']['autocall_trigger'];del data['ranges']['observation_months']
    if key in ('capital_garanti','booster','autocall_gear_put'):
        family=family_schema(key);data['objective']=family['objective']
        data['ranges']={f['key']:{'minimum':12 if f['key']=='maturity_months' else f['initial'],
                                 'maximum':12 if f['key']=='maturity_months' else f['initial'], 'step':f['step']} for f in family['range_fields']}
        if family['has_autocall']:data['ranges']['observation_months']=[3]
        data['constraints']={'price_tolerance':.03}
    return data


@pytest.mark.parametrize('key',ADAPTERS)
def test_schema_matches_exact_script_and_pricing_parameters(key):
    schema=family_schema(key)
    declarations=parse_script(schema['script']).params
    assert {(p['name'],p['kind'],p['required']) for p in schema['script_parameters']}=={(p.name,p.kind,p.required) for p in declarations}
    req=OptimizationRequest.model_validate(family_payload(key))
    c=next(service.generate_candidates(req));_,inputs=service.build_candidate(req,c)
    assert c.product_family==key
    PricingRequest.model_validate(inputs)
    assert set(inputs['user_params'])=={p.name for p in declarations}-{schema['solved_field']['script_param']}
    assert len(schema['script_hash'])==64


def test_script_changes_require_qualification_instead_of_hidden_unbound_fields(monkeypatch):
    changed=deepcopy(service.PRODUCTS['phoenix']);changed['script']+='\nPARAM EXTRA'
    monkeypatch.setitem(service.PRODUCTS,'phoenix',changed)
    assert next(f for f in capabilities()['families'] if f['product_family']=='phoenix')['status']=='UNSUPPORTED'
    with pytest.raises(ValidationError,match='qualification'):
        OptimizationRequest.model_validate(family_payload('phoenix'))


def test_coupon_label_changes_do_not_silently_produce_zero_coupon_analytics(monkeypatch):
    changed=deepcopy(service.PRODUCTS['phoenix']);changed['script']=changed['script'].replace('"Coupon conditionnel"','"Autre libellé"')
    monkeypatch.setitem(service.PRODUCTS,'phoenix',changed)
    with pytest.raises(ValidationError,match='analytics'):
        OptimizationRequest.model_validate(family_payload('phoenix'))


@pytest.mark.parametrize('key,change',[
    ('autocall_athena','coupon'),('phoenix','missing_coupon'),('reverse_convertible','recall'),
    ('reverse_convertible','recall_risk'),('phoenix','settings'),('autocall_barriere_degressive','missing_settings'),
    ('autocall_barriere_degressive','noninteger_rank'),('autocall_barriere_degressive','floor'),
])
def test_inapplicable_or_missing_fields_are_rejected_by_api_contract(key,change):
    data=family_payload(key)
    if change=='coupon':data['ranges']['coupon_barrier']={'minimum':.7,'maximum':.7,'step':.05}
    if change=='missing_coupon':del data['ranges']['coupon_barrier']
    if change=='recall':data['ranges']['autocall_trigger']={'minimum':1.,'maximum':1.,'step':.05}
    if change=='recall_risk':data['constraints']['min_probability_autocall']=.5
    if change=='settings':data['payoff_settings']={'decrement':.02}
    if change=='missing_settings':del data['payoff_settings']
    if change=='noninteger_rank':data['payoff_settings']['first_decrease_rank']=2.5
    if change=='floor':data['payoff_settings']['floor']=1.1
    with pytest.raises(ValidationError):OptimizationRequest.model_validate(data)


def deterministic(key,levels,coupon=.02,barrier=.7,trigger=1.):
    req=OptimizationRequest.model_validate(family_payload(key))
    c=next(service.generate_candidates(req));c.coupon_barrier=barrier if 'phoenix' in key else None
    if c.autocall_trigger is not None:c.autocall_trigger=trigger
    script,inputs=service.build_candidate(req,c)
    dates=sorted({t for event in script.events for t in event.dates})
    assert len(dates)==len(levels)
    dt=1/len(levels)
    paths=np.asarray([1.,*levels]).reshape(len(levels)+1,1,1)
    steps={i+1:[event for event in script.events if date in event.dates] for i,date in enumerate(dates)}
    params={**inputs['user_params'],'COUPON':coupon}
    flows,labels,stops=[],[],[]
    pv,_=_eval_paths(script,paths,len(levels),1,1,dt,0.,params,steps,[],{},False,
                     flows_out=flows,flow_labels_out=labels,stop_times_out=stops)
    coupons=[amount for (_,amount),label in zip(flows[0],labels[0]) if label in ADAPTERS[key]['coupon_labels']]
    return pv[0],coupons,flows[0],stops[0]


@pytest.mark.parametrize('key', ['phoenix','phoenix_memoire'])
def test_coupon_before_simultaneous_recall_and_stop_prevent_later_flows(key):
    price,coupons,flows,stop=deterministic(key,[1.,.5,.5,.5])
    assert price==pytest.approx(1.02) and coupons==pytest.approx([.02])
    assert stop==.25 and all(t==.25 for t,_ in flows)


def test_memory_catchup_reset_and_remaining_unpaid_at_maturity():
    plain=deterministic('phoenix',[.6,.8,.6,.8])
    memory=deterministic('phoenix_memoire',[.6,.8,.6,.8])
    assert plain[1]==pytest.approx([.02,.02]) and memory[1]==pytest.approx([.04,.04])
    assert memory[0]-plain[0]==pytest.approx(.04)
    unpaid=deterministic('phoenix_memoire',[.8,.6,.6,.6])
    assert unpaid[1]==pytest.approx([.02]) and unpaid[0]==pytest.approx(1.02)
    # Equality at protection holds; just below pays the terminal level.
    loss=deterministic('phoenix_memoire',[.6,.6,.6,.5999])
    assert loss[0]==pytest.approx(.5999)


@pytest.mark.parametrize('level,coupon_paid',[(.6999,False),(.7,True),(.7001,True)])
def test_coupon_barrier_boundary_and_no_automatic_call(level,coupon_paid):
    price,coupons,_,stop=deterministic('phoenix',[level]*4)
    assert bool(coupons)==coupon_paid and stop==1.
    assert price==pytest.approx(1.+(.08 if coupon_paid else 0))


def test_step_down_schedule_is_generated_and_changes_recall():
    req=OptimizationRequest.model_validate(family_payload('autocall_barriere_degressive'))
    c=next(service.generate_candidates(req));assert c.autocall_schedule==pytest.approx([1.,.95,.9,.85])
    _,inputs=service.build_candidate(req,c);assert inputs['user_params']['M_AC_BAR']==c.autocall_schedule
    price,coupons,_,stop=deterministic('autocall_barriere_degressive',[.96]*4)
    assert stop==.5 and price==pytest.approx(1.04) and coupons==pytest.approx([.04])
    data=family_payload('autocall_barriere_degressive');data['ranges']['protection_barrier']['minimum']=data['ranges']['protection_barrier']['maximum']=.9
    assert next(service.generate_candidates(OptimizationRequest.model_validate(data))).rejection_reasons


def test_reverse_convertible_has_single_coupon_protection_and_loss():
    assert deterministic('reverse_convertible',[.6],coupon=.08)[0]==pytest.approx(1.08)
    assert deterministic('reverse_convertible',[.5999],coupon=.08)[0]==pytest.approx(.6799)
    data=family_payload('reverse_convertible');data['ranges']['maturity_months'].update(minimum=36,maximum=36)
    req=OptimizationRequest.model_validate(data);c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.pricing_input['user_params']['COUPON']==pytest.approx(c.coupon*3)
    assert c.probability_autocall is None and c.autocall_trigger is None


@pytest.mark.parametrize('key', ['phoenix','phoenix_memoire','autocall_barriere_degressive','reverse_convertible'])
def test_real_solver_holdout_and_coupon_diagnostic_under_curves_and_costs(key):
    data=family_payload(key);data['market'].update(yield_curve=[[1,.03],[3,.04]],funding_spread=.01)
    data['economics']={'upfront_fees':.005,'structuring_margin':.005}
    req=OptimizationRequest.model_validate(data);c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.pricing_status=='PRICED' and c.fair_value==pytest.approx(.99,abs=1e-5)
    quoted=c.coupon;confirmed=validation.validate_candidate(req,c,1)
    assert confirmed.coupon==quoted and confirmed.validation_status=='PASSED'
    assert confirmed.validation['runs'][-1]['coupon_diagnostic']['status']=='AVAILABLE'
    if 'phoenix' in key:
        assert confirmed.expected_coupon_paid is not None and confirmed.expected_coupon_unpaid is not None
        assert confirmed.validation['per_check_alpha']==pytest.approx(.05/13)


def test_coupon_barrier_and_memory_have_real_price_effects_on_common_paths():
    def price(key,barrier):
        req=OptimizationRequest.model_validate(family_payload(key));req.market.underlyings[0].sigma=.45
        c=next(service.generate_candidates(req));c.coupon_barrier=barrier
        script,inputs=service.build_candidate(req,c)
        return run_mc(script,inputs['underlyings'],inputs['corr_matrix'],inputs['r'],inputs['T'],1000,'constant',42,
                      user_params={**inputs['user_params'],'COUPON':.02})['price']
    assert price('phoenix',.95)<price('phoenix',.7)-.001
    assert price('phoenix_memoire',.95)>price('phoenix',.95)+.001


@pytest.mark.parametrize('key',['phoenix','phoenix_memoire','autocall_barriere_degressive','reverse_convertible'])
def test_two_asset_worst_of_resolves_with_all_fields_effectively_bound(key):
    data=family_payload(key)
    other=deepcopy(data['market']['underlyings'][0]);other.update(ticker='TEST2',sigma=.3)
    data['market']['underlyings'].append(other);data['market']['correlation']=[[1.,.4],[.4,1.]]
    req=OptimizationRequest.model_validate(data)
    c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.pricing_status=='PRICED' and c.fair_value==pytest.approx(1.,abs=1e-5)
    assert len(c.pricing_input['underlyings'])==2


def test_multi_date_coupons_and_contract_stop_drive_analytics():
    req=OptimizationRequest.model_validate(family_payload('phoenix_memoire'))
    c=next(service.generate_candidates(req));c.coupon=.08
    result={'price':1.,'ic95':[1.,1.],
            'path_flows':[[(.5,.04),(.5,1.)]]*10+ [[(.25,.02),(1.,1.)]]*10,
            'path_flow_labels':[['Coupon et rattrapage','Remboursement anticipé']]*10+[['Coupon et rattrapage','Capital']]*10,
            'path_stop_times':[.5]*10+[1.]*10}
    summary=summarize_paths(result,10,1.,1.,candidate=c,observation_times=[.25,.5,.75,1.])
    assert summary['means']['expected_coupon_paid']==pytest.approx(.03)
    assert summary['means']['expected_coupon_unpaid']==pytest.approx(.03)
    assert summary['means']['probability_autocall']==.5
    result['path_stop_times'][0]=1.01
    with pytest.raises(ValueError):summarize_paths(result,10,1.,1.,candidate=c,observation_times=[.25,.5,.75,1.])


@pytest.mark.parametrize('antithetic',[True,False])
def test_optional_flow_labels_preserve_shared_engine_price_and_pair_order(antithetic):
    req=OptimizationRequest.model_validate(family_payload('phoenix'));c=next(service.generate_candidates(req))
    script,inputs=service.build_candidate(req,c);args=(script,inputs['underlyings'],inputs['corr_matrix'],inputs['r'],inputs['T'],100,'constant',42)
    params={**inputs['user_params'],'COUPON':.02}
    base=run_mc(*args,antithetic=antithetic,user_params=params)
    labeled=run_mc(*args,antithetic=antithetic,user_params=params,per_path_flows=True,per_path_flow_labels=True)
    assert base['price']==labeled['price'] and base['ic95']==labeled['ic95']
    assert len(labeled['path_stop_times'])==len(labeled['path_flows'])==100*(2 if antithetic else 1)
    assert all(len(path)==len(labels) for path,labels in zip(labeled['path_flows'],labeled['path_flow_labels']))


def test_phoenix_grid_count_includes_coupon_barrier_and_api_exposes_script(api_client):
    client,_,_=api_client;data=family_payload('phoenix')
    data['ranges']['coupon_barrier']['maximum']=.8
    assert client.post('/api/product-optimizer/estimate-search',json=data).json()['candidate_count']==3
    family=next(f for f in client.get('/api/product-optimizer/capabilities').json()['families'] if f['product_family']=='phoenix')
    assert any(p['name']=='M_CPN_BAR' for p in family['script_parameters'])


@pytest.mark.parametrize('key',['phoenix_memoire','autocall_barriere_degressive','reverse_convertible'])
def test_new_families_match_real_spawned_process_results(key):
    data=family_payload(key);data['ranges']['protection_barrier']['maximum']=.65;data['search']['parallel_workers']=1
    serial=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    data['search']['parallel_workers']=2
    parallel=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    assert serial['complete'] and parallel['complete']
    assert serial['candidates']==parallel['candidates'] and serial['recommended_id']==parallel['recommended_id']
    assert parallel['payoff']['product_family']==key
