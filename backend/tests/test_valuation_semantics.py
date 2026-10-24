"""C18 economic identities across analyses, Greeks, scans and receivables."""
from copy import deepcopy
from datetime import date
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.schemas import PricingRequest, ProbaRequest, ReinvestScanRequest
from backend.app.core.valuation_context import (
    ValuationContext, run_analysis, run_valuation, valuation_context_from_request,
    unsettled_cashflows_pv, deterministic_cashflow_pv,
)


def context(model='constant', antithetic=True):
    return ValuationContext(underlyings=[dict(name='S1', sigma=.2,q=.01, rho_rS=.3,
        v0=.04,theta=.04,kappa=2.,xi=.2,rho_h=-.6,alpha=.2,beta=1.,rho=-.3,nu=.2)],
        corr_matrix=[[1]],r=.03,T=.25,N=2000,model=model,antithetic=antithetic,
        yield_curve=[[.1,.02],[.5,.04]],funding_curve=[[.5,.015]],
        funding_spread=.01,sigma_r=.005,a_r=.1,maturity_payment_t=.3,value_date_t=.01,
        state={'spot_mult':[.9],'spot_base':[.9],'s_min_init':[.6],'index_offset':2})


@pytest.mark.parametrize('model',['constant','heston','sabr','localvol','lsv'])
@pytest.mark.parametrize('antithetic',[True,False])
def test_price_paths_and_probabilities_use_identical_financial_context(model,antithetic):
    c=context(model,antithetic); previous=deepcopy(c.to_dict())
    script=parse_script('AT MATURITY:\n  PAY MAX(S[1]-.9,0)')
    price=run_valuation(script,c)
    proba=run_analysis(script,c,'proba')
    paths=run_analysis(script,c,'paths',N_display=10)
    assert price['price']==proba['price']==paths['price']
    assert price['time_axis']==proba['time_axis']==paths['time_axis']
    assert proba['estimator']['antithetic'] is antithetic
    assert proba['total']==2000*(2 if antithetic else 1)
    assert len(paths['path_data'])==10
    assert c.to_dict()==previous


def test_deterministic_payments_include_funding_and_value_date_once():
    c=context();c.sigma_r=0;c.yield_curve=[];c.funding_curve=[];c.r=0;c.funding_spread=.1
    c.T=3;c.maturity_payment_t=3.;c.value_date_t=0
    script=parse_script('AT MATURITY:\n  PAY 1')
    p=run_analysis(script,c,'proba')
    assert p['price']==pytest.approx(math.exp(-.3),abs=1e-6)
    assert p['capital_loss_pct']==0


def test_positive_ten_percent_payment_is_not_zero_or_otm():
    c=context();c.sigma_r=0
    p=run_analysis(parse_script('AT MATURITY:\n  PAY .1'),c,'proba')
    assert p['positive_payoff_pct']==100 and p['zero_payoff_pct']==0
    assert p['capital_loss_pct']==100  # nominal pair is a different metric
    assert p['positive_payoff_count']==p['total']


def test_continuous_bridge_scope_is_preserved_in_all_consumers():
    c=context();c.sigma_r=0;c.barrier_monitoring='continuous'
    c.underlyings*=2;c.corr_matrix=[[1,1],[1,1]]
    c.state={'spot_mult':[.9,.9],'spot_base':[.9,.9]}
    script=parse_script('AT MATURITY:\n  PAY INDIC(WOF_MIN < .8)')
    result=run_valuation(script,c)
    assert run_analysis(script,c,'proba')['price']==result['price']
    assert run_analysis(script,c,'paths',N_display=10)['price']==result['price']
    c.model='heston'
    with pytest.raises(ValueError):run_analysis(script,c,'proba')


def test_request_factory_keeps_dates_rates_and_antithetic_convention():
    payload=dict(script='AT MATURITY:\n  PAY 1',underlyings=[dict(sigma=.2,q=.02)],
        corr_matrix=[[1]],r=.03,T=1,N=2000,seed=123,antithetic=False,
        strike_date='2026-01-02',value_date='2026-01-06',payment_date='2027-01-08',
        funding_spread=.02,sigma_r=.01,a_r=.1)
    price=PricingRequest(**payload);proba=ProbaRequest(**payload)
    compiled=parse_script(price.script)
    assert valuation_context_from_request(price,compiled).to_dict()==valuation_context_from_request(proba,compiled).to_dict()
    assert proba.seed==42 and proba.antithetic is False


def test_probability_sampling_cap_is_visible():
    c=context();c.T=.01;c.N=12000;c.sigma_r=0
    p=run_analysis(parse_script('AT MATURITY:\n  PAY 1'),c,'proba')
    assert p['estimator']['requested_draws']==12000
    assert p['estimator']['independent_draws']==10000


@pytest.mark.parametrize('rho',[.5,.99,1.,-.999])
def test_correlation_greek_uses_signed_admissible_denominator_and_base_antithetic(monkeypatch,rho):
    calls=[]
    def linear(script,uls,corr,r,T,N,model,seed,**kw):
        calls.append(kw)
        delta=(kw.get('corr_delta') or {}).get('delta',0)
        return {'price':2*(corr[0][1]+delta)}
    monkeypatch.setattr(engine,'run_mc',linear)
    g=engine.compute_greeks(parse_script('AT MATURITY:\n  PAY 1'),[{},{}],[[1,rho],[rho,1]],
        .03,1,2000,'constant',42,{},selected=['corr'],antithetic=False)
    assert g['corr_1_2']==2
    assert all(kw['antithetic'] is False for kw in calls)
    assert abs(g['corr_bumps']['corr_1_2']['effective'])<=.05+1e-12
    if rho>=.99:assert g['corr_bumps']['corr_1_2']['effective']<0


def test_nonperturbable_one_factor_correlation_is_unavailable(monkeypatch):
    monkeypatch.setattr(engine,'run_mc',lambda *a,**kw:{'price':1.})
    g=engine.compute_greeks(parse_script('AT MATURITY:\n  PAY 1'),[{}, {}, {}],
        [[1,1,1],[1,1,1],[1,1,1]],.03,1,2000,'constant',42,{},selected=['corr'])
    assert g['corr_1_2'] is None
    assert g['corr_bumps']['corr_1_2']['scheme']=='unavailable'


def test_lsv_vega_metadata_describes_actual_bump(monkeypatch):
    monkeypatch.setattr(engine,'run_mc',lambda *a,**kw:{'price':1.+sum(kw.get('vol_add') or [])})
    g=engine.compute_greeks(parse_script('AT MATURITY:\n  PAY 1'),[{'name':'S1','rho_h':-.9}],
        [[1]],.03,1,2000,'lsv',42,{},selected=['vega'])
    assert g['vega_1']==1
    assert g['vega_scope']['type']=='effective_local_vol'
    assert g['vega_scope']['coverage'] is None


def test_detached_coupon_rate_shock_uses_actual_payment_and_keeps_baseline():
    time=6/365.25;amount=.1
    ctx=dict(r_frac=.03,yc=[],funding_curve=[],funding_spread=.02,
             unsettled_cash_flows=[dict(cf=amount,time_to_payment=time)])
    before=unsettled_cashflows_pv(ctx);after=unsettled_cashflows_pv(ctx,dr=.01)
    assert before==pytest.approx(amount*math.exp(-.05*time))
    assert after-before==pytest.approx(amount*math.exp(-.06*time)-before,abs=1e-16)
    assert (after-before)*1_000_000 < 0


def test_reinvestment_solver_and_proba_share_inherited_funding_and_model(monkeypatch):
    from backend.app.api.deals import _price_reinvest_candidate,_reinvest_valuation_context
    monkeypatch.setattr('backend.app.services.market_data.load_hist_vol',lambda *a,**k:
        dict(vols={'A':.2},div_yields={'A':.02}))
    deal=SimpleNamespace(payment_date='2029-01-01',maturity_date='2029-01-01',
        value_date='2026-01-01',strike_date='2026-01-01',script_snapshot='PARAM C=100%\nAT MATURITY:\n  PAY C')
    c=_reinvest_valuation_context(deal,{'model':'constant','funding_spread':.1,'antithetic':False},
        {},0,3,2000,None,{})
    script=parse_script(deal.script_snapshot)
    result=_price_reinvest_candidate(script,{},0,3,[[1]],{},'A','A','C',math.exp(-.3),.9,1.1,2000,c.model,'1y',valuation_context=c)
    assert 'error' not in result,result
    assert result['price']==pytest.approx(math.exp(-.3),abs=1e-6)
    assert result['solved_param']==pytest.approx(1,abs=1e-4)
    assert result['valuation_context']['funding_spread']==.1
    assert not result['estimator']['antithetic']
    assert ReinvestScanRequest(candidates=[{'ticker':'A'}],param_name='C',target_price=1,lo=0,hi=2).model is None


def test_api_price_proba_and_paths_share_context():
    from backend.app.api import pricing
    from backend.app.api.auth import get_current_pricer
    app=FastAPI();app.include_router(pricing.router)
    app.dependency_overrides[get_current_pricer]=lambda:object()
    body=dict(script='AT MATURITY:\n  PAY MAX(S[1]-.9,0)',underlyings=[dict(sigma=.2,q=.02)],
        corr_matrix=[[1]],r=.03,T=.25,N=2000,N_stat=2000,N_display=10,antithetic=False,
        yield_curve=[[1,.04]],funding_spread=.03,sigma_r=.01,a_r=.1)
    with TestClient(app) as client:
        responses=[client.post('/api/'+kind,json=body) for kind in ['price','proba','paths']]
    assert all(r.status_code==200 for r in responses),[r.text[:300] for r in responses]
    assert len({r.json()['price'] for r in responses})==1


def test_lsv_vega_is_kept_separate_in_portfolio_totals(monkeypatch):
    from backend.tests.test_portfolio_corr_greek import _make_session,_add_deal,USER
    from backend.app.api import portfolios
    from backend.app.db.models import Portfolio
    monkeypatch.setattr(portfolios,'_TICKER_TO_KEY',{})
    monkeypatch.setattr(portfolios,'_TICKER_TO_LABEL',{})
    with _make_session() as session:
        p=Portfolio(name='C18 Vega',user_id=1);session.add(p);session.commit();session.refresh(p)
        for model,scope in [('GBM','total'),('LSV','effective_local_vol')]:
            _add_deal(session,model,[('Action','ACT')],{},nominal=1_000_000,portfolio_id=p.id,
                per_underlying={'Action':{'vega':.2}},vega_scope={'type':scope})
        bucket=portfolios.portfolio_risk(p.id,USER,session)['per_underlying']['ACT']
        assert bucket['vega_eur'] is None
        assert bucket['vega_by_scope_eur']['effective_local_vol']==pytest.approx(200_000)
        assert bucket['vega_by_scope_eur']['total']==pytest.approx(200_000)


def test_prestrike_and_inherited_barrier_state_match_price_for_both_analyses():
    c=context();c.sigma_r=0;c.strike_set_t=.03
    script=parse_script('AT MATURITY:\n  PAY MAX(S[1]-1,0)')
    price=run_valuation(script,c)['price']
    assert run_analysis(script,c,'proba')['price']==price
    assert run_analysis(script,c,'paths',N_display=10)['price']==price


def test_prestrike_api_analyses_share_the_residual_price_without_history_fetch():
    from backend.app.api import pricing,inlife
    from backend.app.api.auth import get_current_pricer,get_current_user
    app=FastAPI();app.include_router(pricing.router);app.include_router(inlife.router)
    app.dependency_overrides[get_current_pricer]=lambda:object()
    app.dependency_overrides[get_current_user]=lambda:object()
    body=dict(script='AT MATURITY:\n  PAY MAX(S[1]-1,0)',underlyings=[dict(name='S1',sigma=.2,q=.02)],
        corr_matrix=[[1]],r=.03,T=.25,N=2000,N_stat=2000,N_display=10,antithetic=False,
        funding_spread=.02,sigma_r=.01,a_r=.1,seed=123,
        strike_date='2026-01-15',value_date='2026-01-19',maturity_date='2026-04-15',
        payment_date='2026-04-20',valuation_date='2026-01-01',settlement_ccy='EUR')
    with TestClient(app) as client:
        replies=[client.post('/api/'+path,json=body) for path in ['price/in-life','proba','paths']]
    assert all(r.status_code==200 for r in replies),[r.text[:300] for r in replies]
    assert len({r.json()['price'] for r in replies})==1
    assert all(r.json()['in_life'] for r in replies[1:])


@pytest.mark.parametrize('kind',['solve','grid'])
def test_pricer_solver_and_grid_use_the_full_context(kind):
    from backend.app.api import simulation
    from backend.app.api.auth import get_current_pricer
    app=FastAPI();app.include_router(simulation.router)
    app.dependency_overrides[get_current_pricer]=lambda:object()
    body=dict(script='PARAM C=50%\nPARAM D=50%\nAT MATURITY:\n  PAY C+D',
        underlyings=[dict(sigma=.2,q=.02)],corr_matrix=[[1]],r=0,T=3,N=2000,
        funding_spread=.1,antithetic=False)
    if kind=='solve':body.update(param_name='C',target_price=math.exp(-.3),lo=.4,hi=.6)
    else:body.update(param_x='C',param_y='D',x_min=.4,x_max=.6,x_steps=2,y_min=.4,y_max=.6,y_steps=2)
    with TestClient(app) as client:reply=client.post('/api/'+kind,json=body)
    assert reply.status_code==200,reply.text
    result=reply.json()
    assert result['base_valuation_context']['funding_spread']==.1
    assert not result['base_valuation_context']['antithetic']
    if kind=='solve':assert result['param_value']==pytest.approx(.5,abs=1e-4)
    else:assert result['prices'][0][0]==pytest.approx(.8*math.exp(-.3),abs=1e-6)


def test_active_deal_shock_separates_optional_and_detached_coupon(monkeypatch):
    from backend.app.api import shocks
    time=6/365.25
    ctx=dict(r_frac=.03,yc=[],funding_curve=[],funding_spread=.02,
        unsettled_cash_flows=[dict(cf=.1,time_to_payment=time)],
        underlyings_json=[{'name':'S1'}],norm_spots=[1.],corr=[[1]],
        residual_script=None,valuation_context={},model_used='constant')
    base=1.+unsettled_cashflows_pv(ctx)
    monkeypatch.setattr(shocks,'_mtm_core',lambda *a:({'mtm':base},ctx))
    monkeypatch.setattr(shocks,'run_valuation',lambda *a,**k:{'price':1.,'n_paths':2000})
    monkeypatch.setattr(shocks,'fx_rate_to',lambda *a:1.)
    deal=SimpleNamespace(id=1,reference='C18',devise='EUR',nominal=1_000_000,sens='vente')
    result=shocks._run_shock_on_deal(deal,None,2000,shocks.ShockRequest(rate_shock_bp=100))
    expected=.1*(math.exp(-.06*time)-math.exp(-.05*time))
    assert result['mtm_after']-result['mtm_before']==pytest.approx(expected)
    assert result['receivables_delta']==pytest.approx(expected)


@pytest.mark.parametrize('source',['booking','booking+overrides','realized','realized+overrides','known_settlement'])
def test_effective_valuation_source_is_archived_independently_of_request(source):
    import json
    from sqlmodel import SQLModel,Session,create_engine
    from backend.tests.test_shocks import _add_deal
    from backend.app.core.valuation_runs import stage_valuation_run
    db=create_engine('sqlite://')
    SQLModel.metadata.create_all(db)
    with Session(db) as session:
        deal,_=_add_deal(session,'AT MATURITY:\n  PAY 1','C18-SOURCE')
        c=context().to_dict()
        ctx=dict(valuation_context=c,product_terms=dict(script='AT MATURITY:\n  PAY 1',
            value_date='2026-01-01',strike_date='2026-01-01',settlement_ccy='EUR'),
            T_elapsed=0,state={'index':0},norm_spots=[1.],corr=[[1]],
            compiled=resolve_constats(parse_script('AT MATURITY:\n  PAY 1'),{},
                                      anchor=date(2026,1,1),currency='EUR'),user_params={})
        row,_=stage_valuation_run(session,deal,1,'MTM',ctx,
            {'mtm':1.,'valuation_date':'2026-01-01','market_used':{'source':source}},diagnostics={'request':{}})
        session.commit();session.expire_all()
        assert json.loads(row.diagnostics_json)['effective_source']==source
