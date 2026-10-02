"""Frozen CCR bases are reused only with compatible contracts and assumptions."""
from copy import deepcopy
from datetime import date, timedelta
import json
import math

import pandas as pd
import pytest
from sqlmodel import select

from backend.app.db.database import get_session
from backend.app.db.models import DealEvent, ProductRecord, CCRExposureCalculation
from backend.app.db.ccr_models import CCRCreditLimit
from backend.app.core.ccr import preparation, service, common_market
from backend.app.core.ccr.cache import preparation_key, find_prepared_base
from backend.app.core.ccr.contracts import CalculationRequest
from backend.app.core import amc_prices
from backend.app.services import market_data
from backend.tests.test_ccr_scope import scope_client
from backend.tests.product_helpers import attach_product_to_deal


def test_cached_base_keeps_fresh_limits_and_credit_stress(scope_client, monkeypatch):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    body = dict(counterparty_id=cpty, prepare_mtm=True, common_rate=.03,
                n_outer=32, n_inner=32, n_dates=3, mtm_paths=1000)
    first = client.post('/api/ccr/calculate', json=body).json()
    assert not first['errors'] and not first['preparation_cache']['reused']
    limit = session.exec(select(CCRCreditLimit)).one()
    payload = json.loads(limit.payload_json)
    payload['amount'] = 500_000
    limit.payload_json = json.dumps(payload)
    session.add(limit); session.commit()
    original = preparation.prepare_trade
    monkeypatch.setattr(preparation, 'prepare_trade', lambda *a, **kw: pytest.fail('Base must be reused'))
    response = client.post('/api/ccr/calculate?stream=true', json={**body,
        'credit_spread_multiplier':2, 'stress':{'spot_pct':0}, 'allow_market_fetch':True})
    events = [json.loads(line) for line in response.text.splitlines()]
    second = events[-1]['data']
    assert any(e.get('phase', {}).get('stage') == 'reuse' for e in events)
    assert second['preparation_cache']['source_run_id'] == first['run_id']
    assert second['preparation_cache']['snapshot_at'] == first['preparation_cache']['snapshot_at']
    assert second['after']['net_mtm'] == first['after']['net_mtm']
    assert second['stress']['after']['net_mtm'] == first['after']['net_mtm']
    assert second['stress']['errors'] == []
    assert not second['decision']['booking_allowed']
    assert client.post(f"/api/ccr/runs/{second['run_id']}/replay").json()['identical']
    monkeypatch.setattr(preparation, 'prepare_trade', original)
    refreshed = client.post('/api/ccr/calculate', json={**body, 'refresh_mtm':True}).json()
    assert not refreshed['preparation_cache']['reused'] and not refreshed['errors']


def test_cache_invalidates_contract_events_market_scope_and_engine(scope_client):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    request = CalculationRequest(counterparty_id=cpty, prepare_mtm=True, common_rate=.03)
    deal = deals[0]
    base = preparation_key(session, 1, [deal], request, 'engine-1')
    for override in ({'common_rate':.04}, {'mtm_paths':2000}, {'seed':7},
                     {'common_market':True}, {'as_of_date':date.today()-timedelta(days=1)},
                     {'data_scope':'UAT'}, {'correlations':{'S|S':1.}},
                     {'market_overrides':{'S':{'sigma':.3}}}):
        changed = CalculationRequest.model_validate({**request.model_dump(), **override})
        assert preparation_key(session, 1, [deal], changed, 'engine-1') != base
    scenario = request.model_copy(update={'stress':{'spot_pct':-20}, 'credit_spread_multiplier':2,
                                         'n_outer':64, 'n_inner':64, 'n_dates':4, 'refresh_mtm':True})
    assert preparation_key(session, 1, [deal], scenario, 'engine-1') == base
    assert preparation_key(session, 2, [deal], request, 'engine-1') != base
    assert preparation_key(session, 1, [deal], request, 'engine-2') != base
    deal.nominal += 1
    assert preparation_key(session, 1, [deal], request, 'engine-1') != base
    deal.nominal -= 1
    event = DealEvent(deal_id=deal.id, event_index=0, event_date=deal.strike_date,
                      t_years=0, spots_json='{"Synthetic":100}', source='manuel', status='observé')
    session.add(event); session.flush()
    with_event = preparation_key(session, 1, [deal], request, 'engine-1')
    assert with_event != base
    event.spots_json = '{"Synthetic":101}'
    assert preparation_key(session, 1, [deal], request, 'engine-1') != with_event
    session.delete(event); session.flush()
    product = session.get(ProductRecord, deal.product_id)
    product.name += ' revised'
    assert preparation_key(session, 1, [deal], request, 'engine-1') != base


def test_incomplete_or_foreign_base_cannot_be_reused(scope_client):
    client, cpty, _, _, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    req = CalculationRequest(counterparty_id=cpty, prepare_mtm=True)
    result = client.post('/api/ccr/calculate', json=req.model_dump(mode='json')).json()
    key = result['preparation_cache']['key']
    assert find_prepared_base(session, 2, req, key) is None
    row = session.get(CCRExposureCalculation, result['run_id'])
    inputs = json.loads(row.inputs_json)
    for failure in ('missing', 'market'):
        changed = deepcopy(inputs)
        if failure == 'missing':
            changed['trades'][0]['missing'] = 'Fixing absent'
        else:
            changed['common_market']['error'] = 'Calibration impossible'
        row.inputs_json = json.dumps(changed)
        session.add(row); session.flush()
        assert find_prepared_base(session, 1, req, key) is None


@pytest.mark.parametrize('adjusted', [False, True])
def test_archived_histories_are_reused_offline_without_mixing_price_types(monkeypatch, adjusted):
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda:{})
    monkeypatch.setattr(amc_prices, 'load_prices', lambda _:pd.DataFrame())
    monkeypatch.setattr(market_data, '_cache_prix', {})
    monkeypatch.setattr(market_data, 'load_hist_prices', lambda *a, **kw:pytest.fail('No external fetch'))
    saved = dict(dates=['2026-09-14','2026-09-15','2026-09-16'], prices={'S':[100,101,102]},
        provider='LOCAL', adjusted=adjusted, requested_start='2026-09-10', requested_end='2026-09-16',
        reused_from_run_id=12)
    request = CalculationRequest()
    got = preparation.MarketHistory(request, [saved])(['S'],'2026-09-14','2026-09-16',adjusted=adjusted)
    assert got['prices']['S'] == [100,101,102] and got['reused_from_run_id'] == 12
    got['prices']['S'][0] = 0
    assert saved['prices']['S'][0] == 100
    with pytest.raises(ValueError, match='local insuffisant'):
        preparation.MarketHistory(request, [saved])(['S'],'2026-09-14','2026-09-16',adjusted=not adjusted)
    with pytest.raises(ValueError, match='local insuffisant'):
        preparation.MarketHistory(request, [saved])(['S'],'2026-09-14','2026-09-17',adjusted=adjusted)
    manual = CalculationRequest(price_histories={'S':{'dates':saved['dates'],'closes':[200,201,202]}})
    assert preparation.MarketHistory(manual, [saved])(['S'],'2026-09-14','2026-09-16')['prices']['S'] == [200,201,202]


def test_active_deal_stress_reuses_base_but_reprices_shocked_value(scope_client, monkeypatch):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    today, deal = date.today(), deals[0]
    deal.contract_version += 1
    deal.status = 'actif'
    deal.strike_date = str(today-timedelta(days=30))
    deal.value_date = deal.strike_date
    deal.maturity_date = str(today+timedelta(days=330))
    deal.payment_date = str(today+timedelta(days=334))
    deal.script_snapshot = 'AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"'
    deal.market_snapshot_json = json.dumps({'r':3,'model':'constant','corrMatrix':[[1]],
        'underlyings':[{'name':'Synthetic','ticker':'S','sigma':20,'q':0}]})
    attach_product_to_deal(session, deal)
    session.add(deal)
    session.add(DealEvent(deal_id=deal.id,event_index=0,event_date=deal.strike_date,t_years=0,
        spots_json='{"Synthetic":100}',source='manuel',status='observé'))
    session.commit()
    dates = pd.bdate_range(today-timedelta(days=37),today)
    adjusted_dates = pd.bdate_range(end=today, periods=400)
    adjusted_prices = pd.DataFrame({'close':[100*math.exp(.0002*i + .01*math.sin(i))
                                            for i in range(400)]}, index=adjusted_dates)
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda:{})
    monkeypatch.setattr(amc_prices, 'load_prices', lambda _:adjusted_prices)
    body = dict(counterparty_id=cpty, prepare_mtm=True, common_market=True, common_rate=.03, mtm_paths=1000,
        n_outer=32,n_inner=32,n_dates=3,price_histories={'S':{
            'dates':[str(d.date()) for d in dates],'closes':[100+i*.2 for i in range(len(dates))]}})
    monkeypatch.setattr(market_data,'load_hist_prices',lambda *a,**kw:pytest.fail('No external fetch'))
    first = client.post('/api/ccr/calculate',json=body).json()
    assert first['errors'] == []
    monkeypatch.setattr(preparation,'prepare_trade',lambda *a,**kw:pytest.fail('No base re-preparation'))
    monkeypatch.setattr(common_market,'harmonize_market',lambda *a,**kw:pytest.fail('No calibration of a cached base'))
    second = client.post('/api/ccr/calculate',json={**body,'stress':{'spot_pct':-20},'wwr':'STRESS'}).json()
    assert second['preparation_cache']['reused']
    assert second['after']['net_mtm'] == first['after']['net_mtm']
    assert second['stress']['errors'] == []
    assert second['stress']['after']['net_mtm'] < first['after']['net_mtm']
    assert second['stress']['after']['pfe95'] > 0
    monkeypatch.setattr(service,'run_valuation',lambda *a,**kw:pytest.fail('Credit-only shock must preserve base MtM'))
    credit = client.post('/api/ccr/calculate',json={**body,'credit_spread_multiplier':2}).json()
    assert credit['preparation_cache']['reused']
    assert credit['stress']['errors'] == []
    assert credit['stress']['after']['net_mtm'] == first['after']['net_mtm']
    assert credit['stress']['after']['pfe95'] == first['after']['pfe95']
