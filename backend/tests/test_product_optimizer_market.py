"""Desk market traceability and the issuer/investor budget distinction."""
import json

import pytest
from pydantic import ValidationError

from backend.app.core.product_optimizer import service, validation
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.market import freeze_market, market_values, market_engine_kwargs
from backend.app.core.payscript.engine import run_mc
from backend.tests.test_product_optimizer import payload, request, api_client


def imported_payload():
    data=payload()
    m=data['market']
    m.update(source='PRICER_SESSION',reference_currency='EUR',reference_tickers=['TEST'],captured_at='2026-10-08T12:00:00+00:00',
             yield_curve=[[1,.03],[3,.05]],funding_spread=.01,funding_curve=[])
    m['underlyings'][0]['dividend_curve']=[[1,.02],[2,.018],[3,.0162]]
    for field in ('yield_curve','funding_curve','funding_spread'): m.setdefault(field, [] if field.endswith('curve') else 0.)
    # Construct the complete source references before enabling the strict import.
    raw={**m,'source':'USER_ASSUMPTION'}
    parsed=OptimizationRequest.model_validate({**data,'market':raw}).market
    m['provenance']={key:{'source':'PRICER_ASSUMPTION','as_of':m['as_of'],
                          'reference_value':value,'method':'Hypothèse copiée du Pricer'}
                     for key,value in market_values(parsed).items()}
    return data


@pytest.mark.parametrize('patch', [
    {'yield_curve':[[2,.03],[1,.02]]}, {'yield_curve':[[1,float('nan')]]},
    {'funding_curve':[[1,.01]],'funding_spread':.01}, {'funding_curve':[[1,.6]]},
    {'captured_at':'2026-10-08T12:00:00'},
])
def test_market_contract_refuses_ambiguous_or_invalid_terms(patch):
    data=payload(); data['market'].update(patch)
    with pytest.raises(ValidationError): OptimizationRequest.model_validate(data)


@pytest.mark.parametrize('curve', [[[1,.03]],[[2,.02]],[[1,.02],[2,.03]],[[1,.02],[2,.6]]])
def test_dividend_curve_requires_matching_first_year_and_declining_buckets(curve):
    data=payload();data['market']['underlyings'][0]['dividend_curve']=curve
    with pytest.raises(ValidationError): OptimizationRequest.model_validate(data)


def test_snapshot_keeps_reference_override_date_and_hash():
    data=imported_payload();data['market']['underlyings'][0]['sigma']=.3
    data['market']['provenance']['rate']['as_of']='2026-10-04'
    req=OptimizationRequest.model_validate(data)
    snapshot=freeze_market(req.market)
    vol=snapshot['fields']['underlyings.TEST.sigma']
    assert vol['reference_value']==.2 and vol['used_value']==.3 and vol['overridden']
    assert snapshot['warnings'] and len(snapshot['hash'])==64
    assert freeze_market(req.market)['hash']==snapshot['hash']
    req.market.underlyings[0].sigma=.31
    assert freeze_market(req.market)['hash']!=snapshot['hash']
    assert snapshot['fields']['underlyings.TEST.sigma']['used_value']==.3
    assert not snapshot['fields']['rate']['active']
    req.market.yield_curve[0][1]=.12
    req.market.provenance['yield_curve'].reference_value[0][1]=.13
    assert snapshot['fields']['yield_curve']['used_value'][0][1]==.03
    assert snapshot['fields']['yield_curve']['reference_value'][0][1]==.03


def test_reference_contract_rejects_future_unknown_and_incomplete_import():
    for kind in ('future','unknown','incomplete'):
        data=imported_payload()
        if kind=='future': data['market']['provenance']['rate']['as_of']='2026-10-06'
        if kind=='unknown': data['market']['provenance']['other']=data['market']['provenance']['rate']
        if kind=='incomplete': del data['market']['provenance']['correlation']
        with pytest.raises(ValidationError): OptimizationRequest.model_validate(data)


def test_currency_change_does_not_relabel_imported_rates_as_another_currency():
    data=imported_payload();data['currency']='USD';data['market']['underlyings'][0]['currency']='USD'
    with pytest.raises(ValidationError,match='devise'):
        OptimizationRequest.model_validate(data)


@pytest.mark.parametrize('field,value', [('yield_curve',.03),('rate',[[1,.03]]),('correlation',[[1,0],[0,1]])])
def test_reference_shapes_match_the_financial_field(field,value):
    data=imported_payload();data['market']['provenance'][field]['reference_value']=value
    with pytest.raises(ValidationError): OptimizationRequest.model_validate(data)


def fixed_price(req, coupon=.02):
    candidate=next(service.generate_candidates(req))
    script,inputs=service.build_candidate(req,candidate)
    return run_mc(script,inputs['underlyings'],inputs['corr_matrix'],inputs['r'],inputs['T'],1000,'constant',42,
                  user_params={**inputs['user_params'],'COUPON':coupon},per_path_flows=True,**market_engine_kwargs(inputs))


def test_funding_changes_pv_without_changing_diffusion_or_cash_flows():
    req=request()
    before=fixed_price(req)
    req.market.funding_spread=.02
    funded=fixed_price(req)
    assert funded['price'] < before['price']-.005
    assert funded['path_flows']==before['path_flows']
    req.market.funding_curve=[[1,.02],[3,.02]];req.market.funding_spread=0
    assert fixed_price(req)['price']==pytest.approx(funded['price'],abs=1e-6)


def test_curves_reach_solver_reprice_and_independent_holdout():
    req=OptimizationRequest.model_validate(imported_payload())
    c=service.price_candidate(req,next(service.generate_candidates(req)))
    assert c.coupon is not None and abs(c.fair_value-req.pricing_target)<1e-5
    assert c.pricing_input['yield_curve']==req.market.yield_curve
    assert c.pricing_input['underlyings'][0]['dividend_curve']==req.market.underlyings[0].dividend_curve
    confirmed=validation.validate_candidate(req,c,1)
    assert confirmed.validation['runs'][-1]['coupon_diagnostic']['status']=='AVAILABLE'
    assert confirmed.pricing_input['funding_spread']==.01


def test_rate_curve_changes_the_engine_result_not_only_the_payload():
    req=request();before=fixed_price(req)
    req.market.yield_curve=[[1,.12],[3,.12]]
    after=fixed_price(req)
    assert abs(after['price']-before['price'])>.001
    assert after['path_flows']!=before['path_flows']


def test_dividend_curve_changes_terminal_redemption():
    req=request()
    req.ranges.maturity_months.minimum=req.ranges.maturity_months.maximum=36
    req.ranges.observation_months=[12]
    req.ranges.protection_barrier.minimum=req.ranges.protection_barrier.maximum=1.
    req.ranges.autocall_trigger.minimum=req.ranges.autocall_trigger.maximum=1.2
    req.market.rate=0.;u=req.market.underlyings[0];u.sigma=0.;u.q=.1
    flat=fixed_price(req)
    u.dividend_curve=[[1,.1],[2,.05],[3,.025]]
    declining=fixed_price(req)
    assert declining['price']>flat['price']+.05


def test_costs_reduce_resolved_coupon_but_loss_is_measured_against_gross_issue():
    req=request()
    base=service.price_candidate(req,next(service.generate_candidates(req)))
    req.economics.upfront_fees=.005;req.economics.structuring_margin=.005
    net=service.price_candidate(req,next(service.generate_candidates(req)))
    assert net.issue_price==1. and net.pricing_target==.99
    assert net.coupon < base.coupon and net.fair_value==pytest.approx(.99,abs=1e-5)
    service.filter_candidate(req,net)
    assert net.constraint_status=='PASS'
    script,inputs=service.build_candidate(req,net)
    result=run_mc(script,inputs['underlyings'],inputs['corr_matrix'],inputs['r'],inputs['T'],1000,'constant',42,
                  user_params={**inputs['user_params'],'COUPON':net.coupon/4},per_path_flows=True)
    losses=[float(sum(amount for _,amount in path)<1.-1e-10) for path in result['path_flows']]
    assert net.probability_loss==pytest.approx(sum(losses)/2000)
    assert net.probability_loss>0


def test_zero_cost_defaults_reproduce_legacy_resolution():
    a=request();data=payload();data['economics']={'upfront_fees':0.,'structuring_margin':0.}
    b=OptimizationRequest.model_validate(data)
    assert service.price_candidate(a,next(service.generate_candidates(a))).model_dump()==service.price_candidate(b,next(service.generate_candidates(b))).model_dump()


def test_snapshot_is_isolated_after_started_event():
    from backend.tests.test_product_optimizer import evaluated
    req=request()
    def holdout(req,c,size): c.validation_status='PASSED';return c
    iterator=service.run_events(req,adapter=lambda req,c:evaluated(req),validation_adapter=holdout)
    started=next(iterator)
    req.market.rate=.2
    out=list(iterator)[-1]['result']
    assert out['request']['market']['rate']==.03
    assert out['market_snapshot']['hash']==started['market_hash']
    assert out['economics']['pricing_target']==1.


def test_api_exports_pricer_origin_net_budget_and_full_snapshot(api_client):
    client,_,_=api_client
    data=imported_payload();data['economics']={'upfront_fees':.005,'structuring_margin':.005}
    response=client.post('/api/product-optimizer/run',json=data)
    assert response.status_code==200
    out=json.loads(response.text.splitlines()[-1])['result']
    assert out['market_source']=='PRICER_SESSION'
    assert out['economics']['pricing_target']==.99
    assert out['market_snapshot']['fields']['funding_spread']['used_value']==.01


def test_spawned_workers_preserve_curves_references_and_net_budget():
    data=imported_payload();data['economics']={'upfront_fees':.005,'structuring_margin':.005}
    data['ranges']['protection_barrier']['maximum']=.65
    data['search']['parallel_workers']=1
    sequential=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    data['search']['parallel_workers']=2
    parallel=list(service.run_events(OptimizationRequest.model_validate(data)))[-1]['result']
    assert sequential['complete'] and parallel['complete']
    assert sequential['candidates']==parallel['candidates']
    assert sequential['recommended_id']==parallel['recommended_id']
    assert sequential['market_snapshot']['hash']==parallel['market_snapshot']['hash']
    assert parallel['economics']['pricing_target']==.99
