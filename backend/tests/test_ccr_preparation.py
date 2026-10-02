"""Automatic CCR MtM preparation: offline integration, evidence and progress."""
from copy import deepcopy
from datetime import date, timedelta
import json
import math

import pandas as pd
import pytest
from sqlmodel import select

from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import ValuationRun, DealEvent
from backend.app.core.ccr.contracts import CalculationRequest, PriceHistory
from backend.app.core.ccr.preparation import MarketHistory, adjust_context
from backend.app.core import amc_prices
from backend.app.services import market_data
from backend.tests.test_ccr_scope import scope_client


def test_stream_prepares_settlement_and_archives_without_changing_booking(scope_client):
    client, cpty, batches, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    session.refresh(deals[0])
    original = deals[0].model_dump()
    existing = len(session.exec(select(ValuationRun)).all())
    response = client.post('/api/ccr/calculate?stream=true', json=dict(counterparty_id=cpty,
        prepare_mtm=True, common_rate=.03, n_outer=32, n_inner=32, n_dates=3, mtm_paths=1000))
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'result', response.text
    phases = [e['phase'] for e in events if e['type'] == 'progress']
    assert [e['stage'] for e in phases][0] == 'scope'
    assert {'mtm','projection','aggregation','saving','completed'} <= {e['stage'] for e in phases}
    result = events[-1]['data']
    assert result['errors'] == []
    expected = 1_000_000 * math.exp(-.03 * 90 / 365.25)
    assert result['after']['current_exposure'] == pytest.approx(expected)
    assert result['valuation_assumptions'][0]['effective_context']['r'] == .03
    session.refresh(deals[0])
    assert deals[0].model_dump() == original
    assert len(session.exec(select(ValuationRun)).all()) == existing
    assert client.post(f"/api/ccr/runs/{result['run_id']}/replay").json()['identical']


def test_missing_mtm_is_built_with_actual_residual_engine_and_manual_history(scope_client, monkeypatch):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    today = date.today()
    d = deals[0]
    # New contract with no archived valuation at this contract version.
    d.contract_version += 1
    d.status = 'actif'
    d.strike_date = str(today - timedelta(days=30))
    d.value_date = d.strike_date
    d.maturity_date = str(today + timedelta(days=330))
    d.payment_date = str(today + timedelta(days=334))
    d.script_snapshot = 'AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"'
    d.market_snapshot_json = json.dumps({'r': 1, 'model':'constant', 'corrMatrix':[[1]],
        'underlyings':[{'name':'Synthetic','ticker':'S','sigma':20,'q':0}],
        'funding':{'enabled':True,'mode':'flat','level':5}})
    from backend.tests.product_helpers import attach_product_to_deal
    attach_product_to_deal(session,d)
    session.add(d)
    session.add(DealEvent(deal_id=d.id, event_index=0, event_date=d.strike_date, t_years=0, spots_json='{"Synthetic":100}', source="manuel", status="observé"))
    session.commit(); session.refresh(d)
    original = d.model_dump()
    before = len(session.exec(select(ValuationRun)).all())
    dates = pd.bdate_range(today-timedelta(days=37), today)
    history = {'S':{'dates':[str(day.date()) for day in dates], 'closes':[100+i*.2 for i in range(len(dates))]}}
    monkeypatch.setattr(market_data,'load_hist_prices',lambda *a,**kw: pytest.fail('No provider call expected'))
    response = client.post('/api/ccr/calculate?stream=true', json=dict(counterparty_id=cpty,
        prepare_mtm=True, common_rate=.03, n_outer=32, n_inner=32, n_dates=3, mtm_paths=1000,
        price_histories=history, market_overrides={'S':{'sigma':.25, 'q':.01}}))
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'result', response.text
    result = events[-1]['data']
    assert result['errors'] == [], result
    assert result['after']['current_exposure'] > 0
    assert result['after']['pfe95'] > 0
    prepared = result['valuation_assumptions'][0]
    assert prepared['source'] == 'CCR_RESIDUAL_MTM'
    assert prepared['effective_context']['funding_spread'] == 0
    assert prepared['effective_context']['underlyings'][0]['sigma'] == .25
    progress = [e['phase'] for e in events if e['type']=='progress']
    assert any(p.get('horizon') == p.get('horizons') and p.get('horizons') for p in progress)
    saved = client.get(f"/api/ccr/runs/{result['run_id']}").json()
    assert saved['inputs']['market_histories']
    assert client.post(f"/api/ccr/runs/{result['run_id']}/replay").json()['identical']
    session.refresh(d)
    assert d.model_dump() == original
    assert len(session.exec(select(ValuationRun)).all()) == before

    # An identical saved clean valuation is reused with no MtM provider or MC call.
    from backend.app.core.valuation_runs import engine_identity
    from backend.app.core.ccr import preparation
    trade = saved['inputs']['trades'][0]
    session.add(ValuationRun(deal_id=d.id, user_id=d.user_id, contract_version=d.contract_version,
        context_hash='compatible', engine_fingerprint=engine_identity()[1],
        context_json=json.dumps(trade['replay']), result_json=json.dumps({
            'valuation_date':str(today), 'mtm':trade['mtm_fraction'],
            'unsettled_cash_flows':trade['unsettled_flows'], 'market_used':trade['settlement_valuation_market']})))
    session.commit()
    monkeypatch.setattr(preparation,'mtm_core',lambda *a,**kw: pytest.fail('Compatible context should be reused'))
    monkeypatch.setattr(preparation,'run_valuation',lambda *a,**kw: pytest.fail('Compatible MtM should be reused'))
    reused=client.post('/api/ccr/calculate',json=dict(counterparty_id=cpty,prepare_mtm=True,
        common_rate=.03,mtm_paths=1000,n_outer=32,n_inner=32,n_dates=3,
        market_overrides={'S':{'sigma':.25,'q':.01}})).json()
    assert reused['valuation_assumptions'][0]['source'] == 'SAVED_MTM_REUSED'
    assert reused['after'] == result['after']


def test_failed_deal_remains_in_scope_and_exposure_is_incomplete(scope_client, monkeypatch):
    client,cpty,_,deals,_=scope_client
    from backend.app.core.ccr import preparation
    original = preparation.prepare_trade
    def fail_one(session, deal, *args):
        if deal.id == deals[1].id:
            raise ValueError('Fixing indisponible')
        return original(session, deal, *args)
    monkeypatch.setattr(preparation,'prepare_trade',fail_one)
    result=client.post('/api/ccr/calculate',json=dict(counterparty_id=cpty,data_scope='UAT',
        prepare_mtm=True,common_rate=.03,n_outer=32,n_inner=32,n_dates=3)).json()
    assert result['after']['gross_notional'] == 2_000_000
    assert result['after']['current_exposure'] is None
    assert result['after']['pfe95'] is None
    assert len(result['valuation_assumptions']) == 2
    assert 'Fixing indisponible' in result['valuation_assumptions'][0]['error']


def test_local_raw_history_has_priority_and_cannot_use_adjusted_close(monkeypatch):
    frame=pd.DataFrame({'price_close':[100.,101.,102.],'close':[50.,51.,52.]},index=pd.to_datetime(['2026-09-14','2026-09-15','2026-09-16']))
    monkeypatch.setattr(amc_prices,'_load_ticker_map',lambda:{})
    monkeypatch.setattr(amc_prices,'load_prices',lambda _:frame)
    monkeypatch.setattr(market_data,'_cache_prix',{})
    monkeypatch.setattr(market_data,'load_hist_prices',lambda *a,**kw: pytest.fail('No provider call expected'))
    history=MarketHistory(CalculationRequest())
    got=history(['S'],'2026-09-09','2026-09-16')
    assert got['prices']['S'] == [100,101,102]
    got['prices']['S'][0]=999
    assert history(['S'],'2026-09-09','2026-09-16')['prices']['S'][0] == 100
    frame.drop(columns='price_close',inplace=True)
    with pytest.raises(ValueError,match='local insuffisant'):
        MarketHistory(CalculationRequest())(['S'],'2026-09-09','2026-09-16')


def test_incomplete_manual_data_never_silently_fetches(monkeypatch):
    monkeypatch.setattr(amc_prices,'_load_ticker_map',lambda:{})
    monkeypatch.setattr(market_data,'load_hist_prices',lambda *a,**kw: pytest.fail('No provider call expected'))
    request=CalculationRequest(allow_market_fetch=True,price_histories={'S':{'dates':['2026-09-16'],'closes':[100]}})
    with pytest.raises(ValueError,match='manuel incomplet'):
        MarketHistory(request)(['S'],'2026-08-01','2026-09-16')
    with pytest.raises(ValueError):
        PriceHistory(dates=['2026-09-16'],closes=[float('inf')])


def test_common_market_overrides_are_explicit_and_do_not_mutate_source():
    context={'model':'constant','r':.01,'funding_spread':.05,'funding_curve':[[1,.05]],'yield_curve':[[1,.02]],
        'underlyings':[{'name':'A','ticker':'A','sigma':.2,'q':.01,'dividend_curve':[[1,.01]]},
                       {'name':'B','ticker':'B','sigma':.3,'q':0}], 'corr_matrix':[[1,.2],[.2,1]]}
    frozen=deepcopy(context)
    effective=adjust_context(context,CalculationRequest(common_rate=.03,market_overrides={'A':{'q':.02,'sigma':.25}},correlations={'A|B':.5}))
    assert context == frozen
    assert effective['r'] == .03 and effective['yield_curve'] == []
    assert effective['funding_curve'] == [] and effective['funding_spread'] == 0
    assert effective['underlyings'][0]['dividend_curve'] == []
    assert effective['corr_matrix'] == [[1,.5],[.5,1]]
    with pytest.raises(ValueError,match='GBM'):
        adjust_context({**context,'model':'heston'},CalculationRequest(market_overrides={'A':{'sigma':.25}}))

@pytest.mark.parametrize('override,expected,source', [(None,.03,'TEMPORARY_ASSUMPTION'), (0.,0.,'USER_OVERRIDE'), (.04,.04,'USER_OVERRIDE')])
def test_common_rate_default_harmonizes_different_bookings_and_preserves_replay(scope_client, override, expected, source):
    client,cpty,_,deals,_=scope_client
    session=client.app.dependency_overrides[get_session]()
    originals=[]
    for deal, rate in zip(deals[1:3],[.01,.06]):
        deal.market_snapshot_json=json.dumps({'r':rate*100,'yieldCurve':[{'T':1,'rate':rate*100}]})
        row=session.exec(select(ValuationRun).where(ValuationRun.deal_id==deal.id)).one()
        row.result_json=json.dumps({'valuation_date':str(date.today()),'mtm':math.exp(-rate*90/365.25), 'market_used':{'r':rate*100}})
        session.add(deal); session.add(row)
        originals.append(deal.market_snapshot_json)
    session.commit()
    body=dict(counterparty_id=cpty,data_scope='UAT',prepare_mtm=True,n_outer=32,n_inner=32,n_dates=3,mtm_paths=1000)
    if override is not None:
        body['common_rate']=override
    response=client.post('/api/ccr/calculate',json=body)
    assert response.status_code == 200, response.text
    result=response.json()
    assert result['errors'] == []
    assert result['methodology'] == 'NESTED_MONTE_CARLO_GBM'
    assert result['after']['pfe95'] > 0 and result['after']['pfe99'] > 0
    assert result['after']['current_exposure'] == pytest.approx(2_000_000*math.exp(-expected*90/365.25))
    assert result['assumptions']['common_rate'] == expected
    assert result['assumptions']['common_rate_source'] == source
    assert all(t['effective_context']['r']==expected and not t['effective_context']['yield_curve'] for t in result['valuation_assumptions'])
    saved=client.get(f"/api/ccr/runs/{result['run_id']}").json()
    assert saved['inputs']['request']['common_rate']==expected
    assert saved['inputs']['request']['common_rate_source']==source
    assert client.post(f"/api/ccr/runs/{result['run_id']}/replay").json()['identical']
    for deal, original in zip(deals[1:3],originals):
        session.refresh(deal)
        assert deal.market_snapshot_json==original
