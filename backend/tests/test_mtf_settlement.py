"""Payment-date oracles and identical fan/detail marks, including after STOP."""
import math
from datetime import date

import numpy as np
import pytest

from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import run_mark_to_future, run_mtf_drilldown, run_mc
from backend.app.core.calendars import add_business_days
from backend.app.api import pricing
from backend.app.core.schemas import MtfRequest, MtfDrilldownRequest
from backend.tests.test_review_fixes_2026_10_24 import payload

UL = [dict(name='Test',sigma=.2,q=0.)]


@pytest.mark.parametrize('lag',[0,3,10])
@pytest.mark.parametrize('rate',[0.,.03])
def test_recalled_claim_survives_until_arbitrary_business_day_payment(lag,rate):
    origin=date(2026,11,3); observation=date(2027,11,3)
    payment=add_business_days(observation,lag,'EUR')
    observed=(observation-origin).days/365.25
    paid=(payment-origin).days/365.25
    script=parse_script(f'AT {observed}:\n  PAY 1.08\n  STOP\nAT MATURITY:\n  PAY 0')
    script.events[0].payment_dates=[paid]
    dates=sorted(set([observed-.02,observed,(observed+paid)/2,paid,paid+.01]))
    options=dict(n_outer=4,n_inner=8,n_dates=2,mtm_dates=dates)
    fan=run_mark_to_future(script,UL,[[1.]],rate,2.,100.,**options)
    for row in fan['results']:
        t=row['t']; expected=108*math.exp(-rate*(paid-t)) if t < paid-1e-9 else 0.
        assert row['pvs']==pytest.approx([expected]*4,abs=5.1e-5)
        assert row['n_outstanding']==(4 if t < paid-1e-9 else 0)
        assert row['n_pending_settlement']==(4 if observed <= t < paid-1e-9 else 0)
        detail=run_mtf_drilldown(script,UL,[[1.]],rate,2.,100.,t,[0,3],**options)
        for scenario in detail['scenarios']:
            assert scenario['mtf']==pytest.approx(expected,abs=5.1e-7)
            assert scenario['sum_pv']==pytest.approx(scenario['mtf'],abs=1e-5)
            assert scenario['mtf']==pytest.approx(row['pvs'][scenario['id']],abs=5.1e-5)
            assert scenario['realized_cash']==(108 if t>=paid-1e-9 else 0.)
            assert sum(f['pv'] for f in scenario['future_flows'])==pytest.approx(expected,abs=1e-5)
            assert scenario['final']['pv_at_0']==pytest.approx(108*math.exp(-rate*paid),abs=5.1e-7)
    initial=run_mc(script,UL,[[1.]],rate,2.,16)
    assert initial['price']==pytest.approx(1.08*math.exp(-rate*paid))


def test_paid_coupon_pending_coupon_and_continuation_never_count_twice():
    script=parse_script('AT 0.1:\n  PAY 0.1\nAT 0.25:\n  PAY 0.2\nAT MATURITY:\n  PAY 1')
    script.events[0].payment_dates=[.2];script.events[1].payment_dates=[.7]
    dates=[.5,1.,1.1,1.2]
    options=dict(n_outer=4,n_inner=8,n_dates=2,mtm_dates=dates,maturity_payment_t=1.2)
    fan=run_mark_to_future(script,UL,[[1.]],.03,1.,100.,**options)
    expected=20*math.exp(-.03*.2)+100*math.exp(-.03*.7)
    assert fan['results'][0]['pvs']==pytest.approx([expected]*4,abs=5.1e-5)
    assert fan['results'][1]['pending_pvs']==pytest.approx([100*math.exp(-.03*.2)]*4)
    detail=run_mtf_drilldown(script,UL,[[1.]],.03,1.,100.,.5,[0],**options)['scenarios'][0]
    assert detail['realized_cash']==10.
    assert detail['mtf']==pytest.approx(expected,abs=5.1e-7)
    assert sorted(f['status'] for f in detail['future_flows'])==['ACQUIRED_UNPAID','CONDITIONAL']
    assert sorted(f['payment_t'] for f in detail['future_flows'])==[.7,1.2]
    assert fan['results'][-1]['n_settled']==4
    price_at_origin = 10*math.exp(-.03*.2)+20*math.exp(-.03*.7)+100*math.exp(-.03*1.2)
    for row in fan['results']:
        discounted_cash = sum(f['amount']*100*math.exp(-.03*f['payment_t']) for f in row['settled_flows'][0])
        assert row['stats_all']['mean']*math.exp(-.03*row['t'])+discounted_cash==pytest.approx(price_at_origin,abs=1e-9)
    last=run_mtf_drilldown(script,UL,[[1.]],.03,1.,100.,1.2,[0],**options)['scenarios'][0]
    assert last['realized_cash']==130. and last['mtf']==0. and last['status']=='SETTLED'


def test_offsetting_unpaid_claims_are_still_outstanding_even_when_net_mark_is_zero():
    script=parse_script('AT 0.25:\n  PAY 0.2\n  PAY -0.2\n  STOP\nAT MATURITY:\n  PAY 0')
    script.events[0].payment_dates=[.75]
    result=run_mark_to_future(script,UL,[[1.]],.03,1.,100.,n_outer=4,n_inner=8,mtm_dates=[.5,.75])
    assert result['results'][0]['pvs']==[0.]*4
    assert result['results'][0]['n_outstanding']==4
    assert result['results'][1]['n_outstanding']==0


def test_all_scenarios_and_outstanding_statistics_use_distinct_populations():
    script=parse_script('AT 0.25:\n  IF WOF >= 1:\n    PAY 1.08\n    STOP\nAT MATURITY:\n  PAY WOF')
    script.events[0].payment_dates=[.3]
    result=run_mark_to_future(script,UL,[[1.]],.03,1.,100.,n_outer=100,n_inner=50,mtm_dates=[.26,.5])
    pending,settled=result['results']
    assert pending['n_pending_settlement']>0 and pending['n_settled']==0
    assert 0<settled['n_outstanding']<100
    assert settled['stats_all']['mean']==pytest.approx(np.mean(settled['pvs']),abs=5.1e-5)
    assert settled['stats_outstanding']['mean']==pytest.approx(np.mean(settled['pvs_outstanding']))
    assert settled['stats_all']['mean']==pytest.approx(settled['stats_outstanding']['mean']*settled['n_outstanding']/100)


def test_context_already_recalled_at_origin_is_valued_analytically():
    script=parse_script('AT MATURITY:\n  PAY 999')
    flows=[dict(observation_t=-.1,payment_t=.1,amount=1.08,lbl='Remboursement'),
           dict(observation_t=-.3,payment_t=-.2,amount=.08,lbl='Coupon')]
    options=dict(n_outer=4,n_inner=8,mtm_dates=[.05,.1,.2],initial_flows=flows,initial_terminated=True)
    fan=run_mark_to_future(script,UL,[[1.]],.03,-.01,100.,**options)
    detail=run_mtf_drilldown(script,UL,[[1.]],.03,-.01,100.,.05,[0],**options)['scenarios'][0]
    assert detail['mtf']==pytest.approx(108*math.exp(-.03*.05))
    assert detail['realized_cash']==8.
    assert fan['results'][-1]['pvs']==[0.]*4


def test_stochastic_detail_reuses_inherited_state_and_unpaid_coupon():
    script=parse_script('SET MEMORY = 0\nAT MATURITY:\n  PAY WOF + MEMORY')
    state=dict(spot_mult=[.8],spot_base=[.8],memo_init={'MEMORY':.2},index_offset=3,
               wof_min_init=.7,bof_max_init=1.1)
    options=dict(n_outer=10,n_inner=50,mtm_dates=[.25,.5],state=state,maturity_payment_t=1.1,
                 initial_flows=[dict(observation_t=-.1,payment_t=.4,amount=.08,lbl='Coupon acquis')])
    fan=run_mark_to_future(script,UL,[[1.]],.03,1.,100.,**options)
    detail=run_mtf_drilldown(script,UL,[[1.]],.03,1.,100.,.25,[0,9],**options)
    for row in detail['scenarios']:
        assert row['mtf']==pytest.approx(fan['results'][0]['pvs'][row['id']],abs=5.1e-5)
        assert row['sum_pv']==pytest.approx(row['mtf'],abs=1e-5)
        assert row['pending_pv']==pytest.approx(8*math.exp(-.03*.15))


def test_http_final_payment_override_reaches_both_calculations(authenticated_client):
    authenticated_client.app.include_router(pricing.router)
    data=payload(strike_date='2026-01-01',payment_date='2027-02-01')
    data.update(T=1.,main_price=100.,n_outer=20,n_inner=50,n_dates=2,mtm_dates=[.25,1.,1.1])
    response=authenticated_client.post('/api/mtf',json=data)
    assert response.status_code==200,response.text
    fan=response.json()
    payment=(date(2027,2,1)-date(2026,1,1)).days/365.25
    assert fan['results'][1]['pvs']==pytest.approx([100*math.exp(-.03*(round(payment,6)-1))]*20,abs=5.1e-5)
    detail=authenticated_client.post('/api/mtf/drilldown',json={**data,'t':1.,'scenario_ids':[0]})
    assert detail.status_code==200,detail.text
    assert detail.json()['scenarios'][0]['mtf']==pytest.approx(fan['results'][1]['pvs'][0],abs=5.1e-5)


def test_inlife_recalled_claim_is_preserved_by_both_api_paths(monkeypatch):
    from backend.app.api import inlife
    monkeypatch.setattr(inlife,'load_hist_prices',lambda *args,**kwargs:dict(
        dates=['2026-11-03','2027-11-03','2027-11-04'],prices={'A':[100.,110.,111.]}))
    common=dict(script='CONSTAT() OBS\nAT OBS:\n  PAY 0.08\n  IF WOF >= 1:\n    PAY 1\n    STOP',
        underlyings=[dict(name='S1',ticker='A',sigma=.2,q=0.)],corr_matrix=[[1.]],r=.03,T=3.,
        strike_date='2026-11-03',value_date='2026-11-03',maturity_date='2029-11-05',
        valuation_date='2027-11-04',payment_date='2029-11-08',settlement_ccy='EUR',strike_levels={'S1':100.},
        constats={'OBS':dict(start_date='2026-11-03',roll_date='2027-11-03',end_date='2029-11-05',frequency='1Y',convention='following',settlement_lag=3)},
        main_price=100.,n_outer=20,n_inner=50,n_dates=2,mtm_dates=[1/365.25,4/365.25,5/365.25])
    fan=pricing.mtf_endpoint(MtfRequest(**common))
    assert fan['terminated_at_origin'] and fan['in_life']
    expected=108*math.exp(-.03*3/365.25)
    assert fan['results'][0]['pvs']==pytest.approx([expected]*20,abs=1e-4)
    assert fan['results'][-1]['pvs']==[0.]*20
    assert fan['results'][1]['pvs']==[0.]*20
    detail=pricing.mtf_drilldown_endpoint(MtfDrilldownRequest(**common,t=1/365.25,scenario_ids=[0],
        context_fingerprint=fan['context_fingerprint']))
    scenario=detail['scenarios'][0]
    assert scenario['mtf']==pytest.approx(expected,abs=1e-4)
    assert scenario['realized_cash']==0 and scenario['status']=='PENDING_SETTLEMENT'
    assert scenario['sum_pv']==pytest.approx(scenario['mtf'])
    monkeypatch.setattr(inlife,'load_hist_prices',lambda *args,**kwargs:dict(
        dates=['2026-11-03','2027-11-03','2027-11-04'],prices={'A':[100.,110.,112.]}))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        pricing.mtf_drilldown_endpoint(MtfDrilldownRequest(**common,t=1/365.25,scenario_ids=[0],
            context_fingerprint=fan['context_fingerprint']))
    assert error.value.status_code==409


def test_valuation_origin_after_maturity_keeps_final_claim_until_settlement(monkeypatch):
    from backend.app.api import inlife
    monkeypatch.setattr(inlife,'load_hist_prices',lambda *args,**kwargs:dict(
        dates=['2026-11-03','2029-11-05','2029-11-06'],prices={'A':[100.,90.,91.]}))
    common=dict(script='AT MATURITY:\n  PAY 1',underlyings=[dict(name='S1',ticker='A',sigma=.2,q=0.)],
        corr_matrix=[[1.]],r=.03,T=3.,strike_date='2026-11-03',value_date='2026-11-03',maturity_date='2029-11-05',
        valuation_date='2029-11-06',payment_date='2029-11-08',settlement_ccy='EUR',strike_levels={'S1':100.},
        main_price=100.,n_outer=20,n_inner=50,n_dates=2,mtm_dates=[1/365.25,2/365.25,3/365.25])
    fan=pricing.mtf_endpoint(MtfRequest(**common))
    detail=pricing.mtf_drilldown_endpoint(MtfDrilldownRequest(**common,t=1/365.25,scenario_ids=[0],
        context_fingerprint=fan['context_fingerprint']))
    assert detail['scenarios'][0]['mtf']==pytest.approx(100*math.exp(-.03/365.25),abs=1e-4)
    assert fan['results'][-1]['n_settled']==20
