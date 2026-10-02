"""Coherent dated CCR market, calibrated once and replayable offline."""
from copy import deepcopy
import json
from datetime import date
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from backend.app.core.ccr import common_market
from backend.app.core.ccr.contracts import CalculationRequest
from backend.app.core.ccr.service import evaluate_inputs
from backend.app.core.valuation_context import ValuationContext


def fixture_book():
    trades=[]
    for i,(ticker,sigma,q) in enumerate([('AAPL',.231,.006),('AAPL',.242,.007),('MSFT',.21,.009)],1):
        context=ValuationContext(underlyings=[{'name':ticker,'ticker':ticker,'sigma':sigma,'q':q}],
            corr_matrix=[[1.]],r=.03,T=1,N=1000,model='constant',seed=42,maturity_payment_t=1).to_dict()
        trades.append(dict(key=str(i),deal_id=i,reference=f'DEAL-{i}',currency='EUR',nominal=1e6,sens='vente',product_type='Option',
            netting_set_id=None,mtm_fraction=.1,preparation={'effective_context':deepcopy(context)},
            replay={'script_text':'AT MATURITY\n  PAY MAX(S[1]-1,0)', 'T_elapsed':0,'value_date':'2026-09-28',
                'strike_date':'2026-09-28','settlement_ccy':'EUR','state':{},'norm_spots':[1.], 'valuation_context':context}))
    deals=[SimpleNamespace(id=i,trade_date=f'2026-09-0{i}') for i in range(1,4)]
    rng=np.random.default_rng(21)
    shocks=rng.normal(0,.01,(252,2))
    shocks[:,1]=.6*shocks[:,0]+.8*shocks[:,1]
    prices=100*np.exp(np.vstack([np.zeros(2),np.cumsum(shocks,axis=0)]))
    data={'prices':{'AAPL':prices[:,0].tolist(),'MSFT':prices[:,1].tolist()},
        'dates':[str(d.date()) for d in pd.bdate_range(end='2026-09-28',periods=253)],
        'provider':'SYNTHETIC','price_type':'ADJUSTED_CLOSE','adjusted':True}
    return trades,deals,data


def test_harmonization_prices_every_trade_then_computes_pfes_offline(monkeypatch):
    trades,deals,data=fixture_book()
    original=deepcopy(trades)
    deals[1].market_snapshot_json=json.dumps({'underlyings':[{'name':'AAPL','ticker':'AAPL','q':.7}]})
    monkeypatch.setattr(common_market,'market_data_provider_for_deal',lambda *a:'SYNTHETIC')
    calls=[]
    def history(tickers,start,end,**kw):
        calls.append((tickers,start,end,kw))
        assert kw['adjusted'] is True
        return deepcopy(data)
    request=CalculationRequest(as_of_date=date(2026,9,28),prepare_mtm=True,common_market=True,common_rate=.03,mtm_paths=1000,n_outer=32,n_inner=32,n_dates=3)
    harmonized,market=common_market.harmonize_market(trades,deals,None,request,history)
    assert len(calls)==1
    assert trades==original
    assert market['factors']['AAPL']['q']==pytest.approx(.007)
    assert market['factors']['AAPL']['q_deal_id']==2
    assert market['factors']['AAPL']['q_source']=='LATEST_BOOKING_ASSUMPTION'
    assert market['n_returns']==252
    first,second=[t['replay']['valuation_context']['underlyings'][0] for t in harmonized[:2]]
    assert first==second
    assert harmonized[0]['mtm_fraction']==harmonized[1]['mtm_fraction']
    inputs={'request':request.model_dump(mode='json'),'configuration':{},'trades':harmonized,'common_market':market}
    result=evaluate_inputs(inputs)
    assert result['errors']==[]
    assert result['after']['pfe95']>0
    assert result['after']['pfe99']>=result['after']['pfe95']
    monkeypatch.setattr(common_market,'harmonize_market',lambda *a,**kw:pytest.fail('Replay cannot recalibrate'))
    assert evaluate_inputs(deepcopy(inputs))==result


def test_manual_overrides_win_and_selection_is_order_independent(monkeypatch):
    trades,deals,data=fixture_book()
    monkeypatch.setattr(common_market,'market_data_provider_for_deal',lambda *a:'SYNTHETIC')
    request=CalculationRequest(common_market=True,market_overrides={'AAPL':{'sigma':.3,'q':0}},correlations={'AAPL|MSFT':.25})
    first,market=common_market.harmonize_market(trades,deals,None,request,lambda *a,**kw:data)
    second,other=common_market.harmonize_market(list(reversed(trades)),list(reversed(deals)),None,request,lambda *a,**kw:data)
    assert market==other
    assert market['factors']['AAPL']['sigma']==.3
    assert market['factors']['AAPL']['q']==0
    assert market['factors']['AAPL']['q_source']=='USER_OVERRIDE'
    assert market['correlation']==[[1,.25],[.25,1]]
    assert first==list(reversed(second))


def test_failed_common_market_does_not_report_partial_pfe(monkeypatch):
    trades,deals,data=fixture_book()
    request=CalculationRequest(common_market=True)
    inputs={'request':request.model_dump(mode='json'),'configuration':{},'trades':trades,
        'common_market':{'error':'Historique manquant'}}
    result=evaluate_inputs(inputs)
    assert result['methodology']=='NESTED_MONTE_CARLO_INCOMPLETE'
    assert result['after']['pfe95'] is None
    assert 'Historique manquant' in result['errors']


def test_adjusted_local_history_never_uses_contractual_manual_series(monkeypatch):
    from backend.app.core.ccr.preparation import MarketHistory
    from backend.app.core import amc_prices
    from backend.app.services import market_data
    monkeypatch.setattr(amc_prices,'_load_ticker_map',lambda:{})
    frame=pd.DataFrame({'close':[50.,51.,52.],'price_close':[100.,101.,102.]},index=pd.to_datetime(['2026-09-14','2026-09-15','2026-09-16']))
    monkeypatch.setattr(amc_prices,'load_prices',lambda _:frame)
    monkeypatch.setattr(market_data,'load_hist_prices',lambda *a,**kw:pytest.fail('Prefer local'))
    request=CalculationRequest(price_histories={'S':{'dates':['2026-09-14','2026-09-15','2026-09-16'],'closes':[200,201,202]}})
    history=MarketHistory(request)
    assert history(['S'],'2026-09-09','2026-09-16',adjusted=True)['prices']['S']==[50,51,52]
    assert history(['S'],'2026-09-09','2026-09-16')['prices']['S']==[200,201,202]

def test_common_correlation_stress_also_changes_cross_product_pairs(monkeypatch):
    from backend.app.core.ccr import service
    trades,deals,data=fixture_book()
    monkeypatch.setattr(common_market,'market_data_provider_for_deal',lambda *a:'SYNTHETIC')
    request=CalculationRequest(common_market=True,n_outer=32,n_inner=32,n_dates=3,stress={'correlation_points':10},correlations={'AAPL|MSFT':.25})
    book,market=common_market.harmonize_market(trades,deals,None,request,lambda *a,**kw:data)
    seen=[]
    original=service.joint_scenarios
    def capture(runtimes,req,times):
        seen.append(req.correlations['AAPL|MSFT'])
        return original(runtimes,req,times)
    monkeypatch.setattr(service,'joint_scenarios',capture)
    result=evaluate_inputs({'request':request.model_dump(mode='json'),'configuration':{},'trades':book,'common_market':market})
    assert result['errors']==[] and result['stress']['errors']==[]
    assert seen==[.25,.35]
