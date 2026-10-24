"""C20: saved modes, financed structures and explicit wall-time overruns."""
from copy import deepcopy

import pytest

from backend.tests.test_optimizer_researches import setup, body, finished
from backend.tests.test_product_optimizer import payload, evaluated
from backend.app.core.product_optimizer import service
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.families import ADAPTERS, family_schema


MODES=[(key,objective['value']) for key in ADAPTERS for objective in family_schema(key)['objectives']]


def mode_request(key, objective):
    schema=family_schema(key,objective)
    data=payload();data.update(product_family=key,objective=objective)
    data['ranges']={field['key']:{'minimum':12 if field['key']=='maturity_months' else field['initial'],
        'maximum':12 if field['key']=='maturity_months' else field['initial'],'step':field['step']}
        for field in schema['range_fields']}
    if schema['has_autocall']:data['ranges']['observation_months']=[3]
    data['payoff_settings']={field['key']:field['initial'] for field in schema['fixed_fields']}
    if objective=='target_coupon':data['constraints']['target_coupon']=.08
    return data


@pytest.mark.parametrize('key,objective',MODES)
def test_every_offered_mode_is_saved_started_and_retained(setup,key,objective):
    client,_,_,_=setup
    request=body(optimization=mode_request(key,objective))
    created=client.post('/api/product-optimizer/researches',json=request)
    assert created.status_code==200,created.text
    saved=finished(client,created.json()['id'])
    assert saved['status']=='COMPLETED'
    assert saved['request']['objective']==objective
    assert saved['request']['payoff_settings']==request['optimization']['payoff_settings']
    for field in family_schema(key,objective)['fixed_fields']:
        assert field['label'] in saved['summary']
        assert f"{request['optimization']['payoff_settings'][field['key']]*(100 if field['unit']=='fraction' else 1):g}" in saved['summary']
    repeated=client.post('/api/product-optimizer/researches',json=request)
    assert repeated.status_code==200 and repeated.json()['id']==saved['id']


def rc_request():
    data=mode_request('reverse_convertible','maximize_coupon')
    data['ranges']['maturity_months'].update(minimum=48,maximum=48)
    return OptimizationRequest.model_validate(data)


def test_financeable_rc_four_years_is_resolved_and_independently_confirmed():
    from backend.app.core.product_optimizer.validation import evaluate_validation
    req=rc_request();candidate=next(service.generate_candidates(req))
    candidate=service.price_candidate(req,candidate)
    assert candidate.pricing_status=='PRICED',candidate.rejection_reasons
    settings=candidate.solver_diagnostics['settings']
    assert settings['max_iter']>18 and settings['tol']==1e-6
    assert candidate.solver_diagnostics['result']['iterations']<=settings['max_iter']
    assert service.estimate_search(req)['solver']['max_iterations_per_candidate']==settings['max_iter']
    assert abs(candidate.fair_value-req.pricing_target)<=req.constraints.price_tolerance
    service.filter_candidate(req,candidate)
    assert candidate.constraint_status=='PASS',candidate.rejection_reasons
    confirmed=evaluate_validation(req,candidate,1)
    assert confirmed.validation_status=='PASSED',confirmed.rejection_reasons


@pytest.mark.parametrize('phase',['exploration','validation'])
@pytest.mark.parametrize('parallel',[False,True])
def test_last_calculation_overrun_is_always_explicit_partial(monkeypatch,phase,parallel):
    clock={'time':0.}
    monkeypatch.setattr(service.time,'monotonic',lambda:clock['time'])
    data=payload();data['search'].update(max_seconds=30,parallel_workers=1)
    req=OptimizationRequest.model_validate(data)
    def exploration(req,candidate):
        if phase=='exploration':
            clock['time']=60.
            candidate.pricing_status='SKIPPED'
            return candidate
        return evaluated(req)
    def validation(req,candidate,size):
        clock['time']=60.
        candidate.validation_status='PASSED'
        return candidate
    if parallel:
        estimate=service.estimate_search(req);estimate['execution']['workers']=2
        monkeypatch.setattr(service,'estimate_search',lambda req:deepcopy(estimate))
        def worker(req,candidates,workers,deadline,phase='exploration',**kwargs):
            for candidate in candidates:
                yield validation(req,candidate,1) if phase=='validation' else exploration(req,candidate)
        monkeypatch.setattr(service,'iter_parallel_candidates',worker)
        result=list(service.run_events(req))[-1]['result']
    else:
        result=list(service.run_events(req,adapter=exploration,validation_adapter=validation))[-1]['result']
    assert result['complete'] is False
    assert result['interruption']=='TIME_BUDGET'
    assert result['elapsed_seconds']==60.
    assert result['statistics']['evaluated']==1
    assert result['time_budget']['limit_seconds']==30
    assert result['time_budget']['exceeded_seconds']==30.
    if phase=='validation':assert result['validation']['passed']==1


def test_rounded_parameter_is_repriced_without_trusting_solver_success(monkeypatch):
    req=rc_request()
    monkeypatch.setattr(service,'solve_for_param',lambda *a,**k:{
        'converged':True,'param_value':1.2,'trace':[],'iterations':1,'achieved_price':1.})
    candidate=service.price_candidate(req,next(service.generate_candidates(req)))
    service.filter_candidate(req,candidate)
    assert candidate.constraint_status=='REJECTED'
    assert abs(candidate.solver_diagnostics['repriced_residual'])>req.constraints.price_tolerance
    assert any(d.get('metric')=='rounded_price' and d['category']=='NUMERICAL_SOLVER'
               for d in candidate.rejection_details)


def test_budget_overrun_is_retained_as_partial_by_background_research(setup,monkeypatch):
    from backend.app.api import product_optimizer as api
    client,_,_,runner=setup
    def overrun(req,**kwargs):
        for item in runner(req,**kwargs):
            if item['type']=='result':
                item['result'].update(complete=False,interruption='TIME_BUDGET',elapsed_seconds=60.,
                                      time_budget={'limit_seconds':30,'exceeded_seconds':30.,'policy':'between_calculations'})
            yield item
    monkeypatch.setattr(api,'run_events',overrun)
    request=body()
    request['optimization']['market']['underlyings'][0]['q']=.02001
    created=client.post('/api/product-optimizer/researches',json=request).json()
    stored=finished(client,created['id'])
    assert stored['status']=='PARTIAL'
    assert stored['result']['interruption']=='TIME_BUDGET'
    assert stored['result']['time_budget']['exceeded_seconds']==30.
    assert stored['result']['candidates'][0]['fair_value']==1.
    assert stored['request']['market']['underlyings'][0]['q']==.02001


def test_coupon_entitlement_uses_the_contractual_stop_date_between_grid_nodes():
    from backend.app.core.product_optimizer.statistics import summarize_paths
    req=OptimizationRequest.model_validate(mode_request('phoenix','maximize_coupon'))
    candidate=next(service.generate_candidates(req));candidate.coupon=.08
    when=.249
    result={'price':1.02,'ic95':[1.02,1.02],
            'path_flows':[[(when,.02),(when,1.)] for _ in range(4)],
            'path_flow_labels':[['Coupon conditionnel','Capital au rappel'] for _ in range(4)],
            'path_stop_times':[when]*4}
    summary=summarize_paths(result,2,1.,1.,candidate=candidate,observation_times=[when,.5,.75,1.])
    assert summary['means']['expected_coupon_paid']==pytest.approx(.02)
    assert summary['means']['expected_coupon_unpaid']==0.
