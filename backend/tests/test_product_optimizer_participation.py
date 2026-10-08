"""Independent payoff and solver checks for participation, cap and geared loss."""
import math
from copy import deepcopy
from statistics import NormalDist

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.product_optimizer import service, validation
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.families import family_schema
from backend.app.core.product_optimizer.statistics import summarize_paths, apply_summary
from backend.app.core.payscript.engine import _eval_paths, run_mc
from backend.tests.test_product_optimizer_payoffs import family_payload


def data_for(key, objective=None):
    data=family_payload(key)
    if objective=='maximize_cap':
        data['objective']=objective;data['ranges'].pop('redemption_cap');data['payoff_settings']={'participation':1.5}
    return data


def path_value(key, levels, **params):
    req=OptimizationRequest.model_validate(data_for(key));c=next(service.generate_candidates(req))
    script,inputs=service.build_candidate(req,c)
    dates=sorted({t for event in script.events for t in event.dates});assert len(dates)==len(levels)
    paths=np.asarray([1.,*levels]).reshape(len(levels)+1,1,1)
    steps={i+1:[event for event in script.events if date in event.dates] for i,date in enumerate(dates)}
    pv,_=_eval_paths(script,paths,len(levels),1,1,1/len(levels),0.,{**inputs['user_params'],**params},steps,[],{},False)
    return float(pv[0])


@pytest.mark.parametrize('level,expected',[(.2,1.),(1.,1.),(1.1,1.2),(1.5,2.)])
def test_protected_capital_and_participation_above_strike(level,expected):
    assert path_value('capital_garanti',[level],PART=2.)==pytest.approx(expected)


@pytest.mark.parametrize('level,expected',[(.2,.2),(1.,1.),(1.1,1.2),(1.15,1.3),(2.,1.3)])
def test_booster_cap_is_redemption_level_and_downside_is_one_for_one(level,expected):
    assert path_value('booster',[level],PART=2.)==pytest.approx(expected)


@pytest.mark.parametrize('level,expected',[(.6,1.),(.5999,1-2*(1-.5999/.6)),(.45,.5),(.3,0.),(.01,0.)])
def test_geared_put_is_european_and_loss_cannot_exceed_capital(level,expected):
    assert path_value('autocall_gear_put',[.5,.5,.5,level],COUPON=.08)==pytest.approx(expected)


def test_gear_coupon_is_same_at_early_and_late_recall_without_athena_cumulation():
    assert path_value('autocall_gear_put',[1.,.2,.2,.2],COUPON=.08)==pytest.approx(1.08)
    assert path_value('autocall_gear_put',[.8,.8,.8,1.],COUPON=.08)==pytest.approx(1.08)


def test_gearing_and_put_strike_affect_solved_coupon_and_loss_on_common_paths():
    data=data_for('autocall_gear_put');data['market']['underlyings'][0]['sigma']=.4
    req=OptimizationRequest.model_validate(data)
    def quote(gearing,strike):
        candidate=next(service.generate_candidates(req));candidate.gearing=gearing;candidate.put_strike=strike
        return service.price_candidate(req,candidate)
    base,levered,higher=quote(1.,.6),quote(3.,.6),quote(1.,.8)
    assert all(c.pricing_status=='PRICED' for c in (base,levered,higher))
    assert levered.coupon>base.coupon and levered.expected_capital_loss>base.expected_capital_loss
    assert higher.coupon>base.coupon and higher.expected_capital_loss>base.expected_capital_loss


@pytest.mark.parametrize('key,objective',[('capital_garanti',None),('booster',None),('booster','maximize_cap'),('autocall_gear_put',None)])
def test_real_solver_holdout_freezes_quantity_and_roundtrips_contract(key,objective):
    data=data_for(key,objective);data['market'].update(yield_curve=[[1,.03],[3,.04]],funding_spread=.01)
    data['economics']={'upfront_fees':.005,'structuring_margin':.005}
    req=OptimizationRequest.model_validate(data)
    assert OptimizationRequest.model_validate_json(req.model_dump_json())==req
    c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.pricing_status=='PRICED' and c.fair_value==pytest.approx(.99,abs=1e-5)
    definition=family_schema(key,req.objective)['solved_field'];quoted=getattr(c,definition['key'])
    confirmed=validation.validate_candidate(req,c,1)
    assert getattr(confirmed,definition['key'])==quoted
    assert confirmed.validation_status=='PASSED'
    assert confirmed.validation['parameter_frozen']==definition['key']
    assert confirmed.pricing_input['user_params'][definition['script_param']]==pytest.approx(quoted)
    if key=='autocall_gear_put':
        assert confirmed.expected_capital_loss>0 and confirmed.conditional_capital_loss<=1
        assert confirmed.validation['per_check_alpha']==pytest.approx(.05/13)


def test_protected_participation_price_matches_independent_black_scholes():
    req=OptimizationRequest.model_validate(data_for('capital_garanti'));c=next(service.generate_candidates(req))
    script,inputs=service.build_candidate(req,c);part=1.5
    result=run_mc(script,inputs['underlyings'],inputs['corr_matrix'],inputs['r'],inputs['T'],20000,'constant',123,
                  user_params={**inputs['user_params'],'PART':part})
    # Observations use the weekly grid while settlement discounting is contractual.
    t=inputs['T'];dt=t/max(1,round(t*52));obs=round(t/dt)*dt
    payment=max(p for event in script.events for p in event.payment_dates if p is not None)
    r,q,sigma=.03,.02,.2;strike=c.strike;cdf=NormalDist().cdf
    d1=(math.log(1/strike)+(r-q+.5*sigma*sigma)*obs)/(sigma*math.sqrt(obs));d2=d1-sigma*math.sqrt(obs)
    undiscounted_call=math.exp((r-q)*obs)*cdf(d1)-strike*cdf(d2)
    exact=math.exp(-r*payment)*(1+part*undiscounted_call)
    se=(result['ic95'][1]-result['ic95'][0])/3.92
    assert result['price']==pytest.approx(exact,abs=4*se+1e-6)


def test_flat_booster_price_selects_upper_bound_and_diagnostic_does_not_claim_ranking():
    data=data_for('booster');data['market']['underlyings'][0].update(sigma=0,q=0)
    data['market']['rate']=0
    req=OptimizationRequest.model_validate(data);c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.participation==req.constraints.participation_maximum and c.fair_value==1.
    assert any('plateau' in warning for warning in c.warnings)
    confirmed=validation.validate_candidate(req,c,1)
    assert confirmed.validation_status=='PASSED'
    assert confirmed.validation['runs'][-1]['parameter_diagnostic']['status'].startswith('UNAVAILABLE')


def test_unfinanceable_protected_nominal_is_skipped_without_fake_participation():
    data=data_for('capital_garanti');data['market']['rate']=-.02
    req=OptimizationRequest.model_validate(data);c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.pricing_status=='SKIPPED' and c.participation is None


def test_severity_excludes_coupon_and_respects_independent_pair_order():
    req=OptimizationRequest.model_validate(data_for('autocall_gear_put'));c=next(service.generate_candidates(req));c.coupon=.1
    result={'price':.99,'ic95':[.98,1.], 'path_flows':[[(1.,1.),(1.,-.4),(1.,.1)]]*10+ [[(1.,1.)]]*10,
            'path_flow_labels':[['Nominal','Put vendu avec levier, perte plafonnée au capital','Coupon']]*10+[['Nominal']]*10}
    summary=summarize_paths(result,10,1.,1.,candidate=c,simultaneous=True);apply_summary(c,summary)
    assert c.probability_capital_loss==.5 and c.expected_capital_loss==pytest.approx(.2)
    assert c.conditional_capital_loss==pytest.approx(.4)
    assert c.conditional_capital_loss_ic95[0]<=.4<=c.conditional_capital_loss_ic95[1]
    req.constraints.max_expected_capital_loss=.1;c.pricing_status='PRICED';c.analytics_status='AVAILABLE'
    service.filter_candidate(req,c);assert any('capital' in reason for reason in c.rejection_reasons)


def test_capital_loss_label_change_requires_adapter_requalification(monkeypatch):
    data=data_for('booster')
    changed=deepcopy(service.PRODUCTS['booster']);changed['script']=changed['script'].replace('Put vendu — perte en capital','Autre perte')
    monkeypatch.setitem(service.PRODUCTS,'booster',changed)
    with pytest.raises(ValidationError,match='analytics'):OptimizationRequest.model_validate(data)


@pytest.mark.parametrize('key,change',[('capital_garanti','coupon_objective'),('booster','put_range'),('booster','coupon_bounds'),('autocall_gear_put','protection_objective')])
def test_inapplicable_fields_and_objectives_are_rejected(key,change):
    data=data_for(key)
    if change=='coupon_objective':data['objective']='maximize_coupon'
    if change=='protection_objective':data['objective']='maximize_protection'
    if change=='put_range':data['ranges']['put_strike']={'minimum':.6,'maximum':.6,'step':.05}
    if change=='coupon_bounds':data['constraints']['coupon_maximum']=.2
    with pytest.raises(ValidationError):OptimizationRequest.model_validate(data)


@pytest.mark.parametrize('key,objective',[('capital_garanti',None),('booster','maximize_cap'),('autocall_gear_put',None)])
def test_new_quantity_and_fields_match_spawned_process_results(key,objective):
    data=data_for(key,objective);data['search']['parallel_workers']=1
    axis='put_strike' if key=='autocall_gear_put' else 'strike' if key=='capital_garanti' else 'maturity_months'
    data['ranges'][axis]['maximum']+=data['ranges'][axis]['step']
    serial=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    data['search']['parallel_workers']=2
    parallel=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    assert serial['complete'] and parallel['complete']
    assert serial['candidates']==parallel['candidates'] and serial['recommended_id']==parallel['recommended_id']
