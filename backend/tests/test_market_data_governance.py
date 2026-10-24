"""C11: deterministic dated coverage, local replay and retained assumptions."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from backend.app.core import amc_prices, market_policy
from backend.app.core.schemas import UnderlyingParams, PricingRequest
from backend.app.core.valuation_context import build_pricing_receipt, verify_pricing_receipt
from backend.app.services import market_data, market_history
from backend.tests.test_products import product_client, _pricing_input, _create


@pytest.fixture(autouse=True)
def isolated_market(monkeypatch, tmp_path):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(amc_prices, '_PRICE_STORE', tmp_path/'prices')
    monkeypatch.setattr(amc_prices, '_FX_STORE', tmp_path/'fx')
    amc_prices._PRICE_STORE.mkdir(); amc_prices._FX_STORE.mkdir()
    monkeypatch.setattr(amc_prices, '_TICKER_MAP_FILE', amc_prices._PRICE_STORE/'_ticker_map.json')
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda **kwargs: {})
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def prices(start='2026-01-01', end='2026-08-27', scale=1):
    index = pd.bdate_range(start, end)
    return pd.Series(100*np.exp(scale*.01*(np.arange(len(index)) % 2)), index=index)


def fake_provider(monkeypatch, values):
    calls = []
    class Instrument:
        fast_info = {'currency':'EUR'}
        def __init__(self, ticker): self.ticker = ticker
        def history(self, start, end, auto_adjust=True, **kwargs):
            calls.append((self.ticker, start, end, auto_adjust))
            series = values.get(self.ticker, pd.Series(dtype=float, index=pd.DatetimeIndex([])))
            series = series.loc[(series.index >= pd.Timestamp(start)) & (series.index < pd.Timestamp(end))]
            return series.to_frame('Close')
        @property
        def dividends(self): return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    monkeypatch.setattr(market_data, '_HAS_YF', True)
    monkeypatch.setattr(market_data, 'yf', SimpleNamespace(Ticker=Instrument))
    return calls


def test_pending_policy_does_not_qualify_carried_prices_or_fx(monkeypatch):
    monkeypatch.setattr(market_policy, 'HISTORY_MAX_AGE_DAYS', None)
    monkeypatch.setattr(market_policy, 'REPORTING_FX_MAX_AGE_DAYS', None)
    for usage in ('history', 'reporting_fx'):
        assert market_policy.freshness('2026-08-27', '2026-08-27', usage)['qualified']
        q = market_policy.freshness('2026-08-26', '2026-08-27', usage)
        assert not q['qualified'] and q['status'] == 'POLICY_NOT_CONFIGURED'


@pytest.mark.parametrize('usage', ['history','reporting_fx'])
def test_approved_policy_accepts_day_three_and_excludes_day_four(usage):
    accepted = market_policy.freshness('2026-08-24','2026-08-27',usage)
    excluded = market_policy.freshness('2026-08-24','2026-08-28',usage)
    assert accepted['qualified'] and accepted['status'] == 'CARRIED'
    assert accepted['max_age_days'] == 3 and accepted['age_days'] == 3
    assert not excluded['qualified'] and excluded['status'] == 'STALE'
    assert excluded['max_age_days'] == 3 and excluded['age_days'] == 4
    assert accepted['policy_version'] == 'D03-C11-2026-10-21-3D'


def test_sixty_day_suspension_is_excluded_instead_of_zero_returns(monkeypatch):
    fake_provider(monkeypatch, {'A':prices(end='2026-06-01'), 'B':prices()})
    result = market_data.load_hist_prices(['A','B'], '2026-01-01', '2026-08-27')
    assert result['error'] and result['prices'] == {}
    assert result['missing'] == ['A']
    assert result['freshness']['A']['age_days'] == 87
    assert not result['coverage']['complete']


@pytest.mark.parametrize('with_other', [False, True])
def test_long_interior_halt_cannot_be_compressed_into_daily_return(monkeypatch, with_other):
    series = prices(); series = series.drop(series.loc['2026-03-01':'2026-05-01'].index)
    values = {'A':series, **({'B':prices()} if with_other else {})}
    fake_provider(monkeypatch, values)
    result = market_data.load_hist_prices(list(values), '2026-01-01', '2026-08-27')
    assert result['error'] and result['missing_reasons']['A']['reason'] == 'UNBOUNDED_HISTORY_GAP'


def test_closed_market_carry_is_bounded_and_source_dates_are_visible(monkeypatch):
    a = pd.Series([100.,102.], index=pd.to_datetime(['2026-08-21','2026-08-24']))
    b = pd.Series([80.,81.,82.], index=pd.to_datetime(['2026-08-21','2026-08-22','2026-08-24']))
    fake_provider(monkeypatch, {'A':a, 'B':b})
    result = market_data.load_hist_prices(['A','B'], '2026-08-21', '2026-08-24')
    assert not result.get('error')
    assert result['prices']['A'] == [100.,100.,102.]
    assert result['carry_age_days']['A'] == [0,1,0]
    assert result['source_observation_dates']['A'][1] == '2026-08-21'
    assert result['warnings'][0]['code'] == 'BOUNDED_CARRY'


def test_leading_missing_prices_are_trimmed_without_backfill(monkeypatch):
    fake_provider(monkeypatch, {'A':prices(), 'B':prices(start='2026-03-02')})
    result = market_data.load_hist_prices(['A','B'], '2026-01-01', '2026-08-27')
    assert result['start_effective'] == '2026-03-02'
    assert result['coverage']['complete']
    assert all(d >= '2026-03-02' for d in result['dates'])


def test_missing_asset_requires_explicit_exploratory_reduction(monkeypatch):
    fake_provider(monkeypatch, {'A':prices()})
    strict = market_data.load_hist_prices(['A','B'], '2026-01-01', '2026-08-27')
    reduced = market_data.load_hist_prices(['A','B'], '2026-01-01', '2026-08-27', allow_partial=True)
    assert strict['error'] and not strict['prices']
    assert not reduced.get('error') and set(reduced['prices']) == {'A'}
    assert reduced['coverage']['excluded'] == [{'ticker':'B','reason':'NO_OBSERVATIONS'}]
    assert reduced['coverage']['allow_partial'] and not reduced['coverage']['complete']


def test_durable_local_replay_needs_no_network_and_caches_are_defensive(monkeypatch):
    calls = fake_provider(monkeypatch, {'A':prices()})
    result = market_data.load_hist_prices(['A'], '2026-01-01', '2026-08-27')
    result['prices']['A'][0] = -1
    result['coverage']['included'].clear()
    cached = market_data.load_hist_prices(['A'], '2026-01-01', '2026-08-27')
    assert cached['prices']['A'][0] == 100 and cached['coverage']['included'] == ['A']
    market_data.vider_cache_prix(); calls.clear()
    replay = market_data.load_hist_prices(['A'], '2026-01-01', '2026-08-27')
    assert not calls and replay['sources']['A']['storage'] == 'MARKET_HISTORY'
    assert replay['prices'] == cached['prices']


def test_amc_storage_supplies_the_correct_raw_and_adjusted_basis_offline(monkeypatch):
    frame = pd.DataFrame({'close':[90.,91.], 'price_close':[100.,101.]}, index=pd.to_datetime(['2026-08-26','2026-08-27']))
    frame.attrs.update(source='yahoo:A', requested_start='2026-08-26', requested_end='2026-08-27')
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda:{'A':'A'})
    monkeypatch.setattr(amc_prices, 'load_prices', lambda key:frame)
    raw = market_data.load_hist_prices(['A'], '2026-08-26', '2026-08-27')
    adjusted = market_data.load_hist_prices(['A'], '2026-08-26', '2026-08-27', adjusted=True)
    assert raw['prices']['A'] == [100.,101.] and adjusted['prices']['A'] == [90.,91.]
    status = market_history.storage_status('A', '2026-08-27')
    assert status['consumer_available'] and status['cache_status'] == 'ok'


def test_adjusted_only_storage_is_not_reported_usable_for_contract_replay():
    market_history.store_history('A', prices(), True, '2026-01-01', '2026-08-27')
    status = market_history.storage_status('A', '2026-08-27')
    assert status['available'] and not status['consumer_available']
    assert status['cache_status'] == 'unqualified'
    assert status['bases']['unadjusted']['status'] == 'MISSING'


def test_dated_and_current_vol_use_the_same_declared_common_sample(monkeypatch):
    from backend.app import runtime
    monkeypatch.setattr(runtime, 'business_today', lambda:date(2026,8,27))
    fake_provider(monkeypatch, {'A':prices(start='2025-01-01'), 'B':prices(start='2025-02-01', scale=1.5)})
    monkeypatch.setattr(market_data, 'dividend_profile', lambda tk,*args: {'ok':tk=='A', 'yield_declared':0.} if tk=='A' else {'ok':False,'error':'feed absent'})
    current = market_data.load_hist_vol(['A','B'])
    dated = market_data.load_hist_vol(['A','B'], asof='2026-08-27')
    assert current['vols'] == dated['vols']
    assert current['vols']['A'] == pytest.approx(np.sqrt(252)*.01, abs=1e-12)
    assert current['n_obs'] == 252 and current['estimator']['volatility'] == 'RMS_LOG_RETURNS'
    assert current['div_yields'] == {'A':0.} and current['missing_dividends'] == ['B']
    matrix = np.array([[current['corr'][a][b] for b in ['A','B']] for a in ['A','B']])
    assert np.linalg.eigvalsh(matrix).min() >= -1e-8


@pytest.mark.parametrize('day,status,qualified,age', [('2026-08-27','FRESH',True,0),('2026-08-24','CARRIED',True,3),('2026-08-23','STALE',False,4),('2024-01-01','STALE',False,969),('2026-08-28','MISSING',False,None)])
def test_fx_quote_retains_date_and_age_but_excludes_old_or_future_rate(monkeypatch, day,status,qualified,age):
    monkeypatch.setattr(amc_prices, 'get_fx_series', lambda *args,**kw:pd.Series([.9], index=pd.to_datetime([day])))
    quote = amc_prices.fx_quote_to('USD', 'EUR', '2026-08-27')
    assert quote['qualified'] is qualified and quote['status'] == status and quote['age_days'] == age
    assert amc_prices.fx_rate_to('USD','EUR','2026-08-27') == (.9 if qualified else None)


def metadata():
    return {'references':{'sigma':{'unit':'fraction','value':.2,'applied_value':.2,'ticker':'A','provider':'YAHOO_FINANCE','asof_effective':'2026-08-27'},
                          'q':{'unit':'fraction','value':.01,'applied_value':.01,'ticker':'A'}},
            'effective':{'sigma':99,'q':99}, 'overrides':{}}


@pytest.mark.parametrize('field,value', [('sigma',.23456789),('q',.0200123)])
def test_provenance_cannot_replace_the_actual_validated_engine_values(field,value):
    row = UnderlyingParams(name='A',ticker='A',sigma=.2,q=.01,market_data=metadata(), **{})
    payload = row.model_dump(); payload[field] = value
    result = UnderlyingParams.model_validate(payload).model_dump()['market_data']
    assert result['effective'][field] == value and result['overrides'][field] == value
    assert result['references'][field]['value'] != value
    assert result['source_attestation'] == 'CLIENT_DECLARED_REFERENCE'


@pytest.mark.parametrize('bad', [float('nan'), True, '20%'])
def test_invalid_provenance_is_rejected(bad):
    data = metadata(); data['references']['sigma']['value'] = bad
    with pytest.raises(ValidationError): UnderlyingParams(name='A',ticker='A',market_data=data)


def test_legacy_underlying_does_not_gain_a_null_provenance_key():
    assert 'market_data' not in UnderlyingParams(name='A').model_dump(mode='json')


def test_reference_override_and_exact_value_survive_receipt_product_and_reopen(product_client):
    from backend.app.api.auth import receipt_signing_secret
    from backend.app.services.product_receipts import signed_receipt
    payload = _pricing_input(underlyings=[{'name':'A','ticker':'A','sigma':.23456789,'q':.0200123,'market_data':metadata()}])
    receipt = signed_receipt(build_pricing_receipt(PricingRequest.model_validate(payload), .98), secret=receipt_signing_secret(), result={'price':.98})
    verified = verify_pricing_receipt(receipt)
    snapshot = verified['market_snapshot']['underlyings'][0]
    assert snapshot['sigma'] == pytest.approx(23.456789) and snapshot['q'] == pytest.approx(2.00123)
    assert snapshot['market_data']['effective']['q'] == .0200123
    product = _create(product_client, pricing_input=payload, receipt=receipt)
    reopened = product_client.get(f"/api/products/{product['product_id']}").json()
    calculation = reopened['calculations'][0]
    detail = product_client.get(f"/api/products/{product['product_id']}/calculations/{calculation['id']}").json()
    market = detail['market_snapshot']['underlyings'][0]['market_data']
    assert market['references']['q']['value'] == .01 and market['overrides']['q'] == .0200123
    booked = product_client.post('/api/deals', json={
        'product_id':product['product_id'], 'product_terms_version':product['terms_version'],
        'sens':'vente','contrepartie':'Banque Test','counterparty_id':1,'devise':'EUR',
        'nominal':1_000_000,'fair_value':98.,'price_traded':98.,'trade_date':'2026-09-14',
        'strike_date':'2026-09-14','value_date':'2026-09-16','maturity_date':'2027-09-14',
        'payment_date':'2027-09-16','T':1.,'underlyings':[{'name':'A','ticker':'A','ccy':'EUR'}],
        'observation_times':[1.], 'script_snapshot':payload['script'],'market_snapshot':{},'pricing_receipt':receipt})
    assert booked.status_code == 201, booked.text
    assert booked.json()['market_snapshot']['underlyings'][0]['market_data'] == market


def test_reinvest_unknown_dividend_does_not_call_solver(monkeypatch):
    from backend.app.api.deals import _price_reinvest_candidate
    from backend.app.core.payscript import simulation
    monkeypatch.setattr(market_data, 'load_hist_vol', lambda *a,**kw:{'vols':{'A':.2},'div_yields':{},'dividend_profiles':{'A':{'ok':False,'error':'offline'}}})
    monkeypatch.setattr(simulation, 'solve_for_param', lambda *a,**kw:pytest.fail('Unknown dividend reached solver'))
    result = _price_reinvest_candidate(None, {}, .03, 1, [[1]], {}, 'A','A','C',1,0,.2,1000,'constant','1y')
    assert 'Dividende inconnu' in result['error'] and result['dividend_diagnostic']['error'] == 'offline'


def test_admin_fetch_populates_the_stores_consumers_replay_offline(monkeypatch):
    from backend.app.api import admin
    from backend.app import runtime
    calls = fake_provider(monkeypatch, {'A':prices()})
    monkeypatch.setattr(amc_prices, 'yf', market_data.yf)
    monkeypatch.setattr(runtime, 'business_today', lambda:date(2026,8,27))
    monkeypatch.setattr(admin, '_fetch_prices', lambda key,ticker:amc_prices.fetch_prices(key,ticker,start='2026-01-01',end='2026-08-28'))
    fetched = admin.market_data_fetch(admin.MarketDataFetchRequest(key='A',ticker='A'), None)
    assert fetched['consumer_available'] and fetched['cache_status'] == 'ok'
    assert all(row['available'] for row in fetched['bases'].values())
    calls.clear()
    for adjusted in (False,True):
        result = market_data.load_hist_prices(['A'], '2026-01-01', '2026-08-27', adjusted=adjusted)
        assert not result.get('error') and result['sources']['A']['storage'] == 'MARKET_HISTORY'
    assert not calls


def test_old_fx_excludes_exposure_and_does_not_clear_a_counterparty_limit(monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine
    from backend.app.api.portfolios import _aggregate_exposure_by_counterparty
    from backend.app.db.models import Counterparty, Deal
    from backend.app import runtime
    monkeypatch.setattr(runtime, 'business_today', lambda:date(2026,8,27))
    monkeypatch.setattr(amc_prices, 'get_fx_series', lambda *a,**kw:pd.Series([.9],index=pd.to_datetime(['2024-01-01'])))
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Counterparty(id=1,name='Bank',active=True,limit_eur=2_000_000)); session.commit()
        deal = Deal(id=1,reference='USD-OLD-FX',user_id=1,status='actif',nominal=1_000_000,devise='USD',counterparty_id=1,contrepartie='Bank')
        result = _aggregate_exposure_by_counterparty([deal],session)
    assert result['nominal_total_eur'] == 0
    assert result['by_counterparty'][0]['limit_status'] == 'INCOMPLETE'
    assert result['by_counterparty'][0]['limit_breached'] is None
    assert result['fx_coverage'][0]['status'] == 'STALE' and result['fx_coverage'][0]['age_days'] == 969


def test_dividend_profile_reuses_saved_observations_before_requesting_cash_events(monkeypatch):
    calls = fake_provider(monkeypatch, {'A':prices(start='2025-01-01')})
    for adjusted in (False,True):
        market_history.store_history('A',prices(start='2025-01-01'),adjusted,'2025-01-01','2026-08-27')
    result = market_data.dividend_profile('A','2026-08-27')
    assert result['ok'] and result['yield_declared'] == 0 and not calls
    monkeypatch.setattr(market_data,'_HAS_YF',False)
    replay = market_data.dividend_profile('A','2026-08-27')
    assert replay['ok'] and replay['storage'] == 'MARKET_HISTORY'


def test_full_backtest_refuses_missing_asset_but_comparison_records_reduction(monkeypatch):
    from fastapi import HTTPException
    from backend.app.api.pricing import backtest_endpoint, backtest_compare_endpoint
    from backend.app.core.schemas import BacktestRequest, BacktestCompareRequest
    fake_provider(monkeypatch, {'A':prices(start='2025-01-01')})
    common = dict(script='AT MATURITY\n  PAY 1\n',T=.1,start_date='2026-01-01',end_date='2026-08-27')
    assets = [{'name':'A','ticker':'A'},{'name':'B','ticker':'B'}]
    with pytest.raises(HTTPException) as error:
        backtest_endpoint(BacktestRequest(underlyings=assets,corr_matrix=[[1,0],[0,1]],**common))
    assert error.value.status_code == 422 and 'B' in error.value.detail
    result = backtest_compare_endpoint(BacktestCompareRequest(candidates=assets,**common))
    assert result['requested_tickers'] == ['A','B'] and result['shortlist'] == ['A']
    assert result['excluded_universe']['B']['reason'] == 'NO_OBSERVATIONS'
    assert not result['market_coverage']['complete']


def test_backtest_correlation_uses_common_estimator_without_rounding():
    from backend.app.api.pricing import _realized_corr
    from backend.app.core.calibration import realized_market
    values = {'A':prices().to_list(),'B':prices(scale=1.5).to_list()}
    expected = realized_market(values,['A','B'],window_days=len(values['A'])-1)['corr']
    assert _realized_corr(values,['A','B']) == expected


@pytest.mark.parametrize('shared_end,shared_start', [('2026-06-01','2026-01-01'),('2026-08-27','2026-07-01')])
def test_more_complete_amc_stock_precedes_refetch_when_shared_copy_is_partial(monkeypatch, shared_end, shared_start):
    market_history.store_history('A',prices(start=shared_start,end=shared_end),True,shared_start,shared_end)
    frame = prices().to_frame('close')
    frame.attrs.update(source='yahoo:A',requested_start='2026-01-01',requested_end='2026-08-27')
    monkeypatch.setattr(amc_prices,'_load_ticker_map',lambda:{'A':'A'})
    monkeypatch.setattr(amc_prices,'load_prices',lambda key:frame)
    calls = fake_provider(monkeypatch, {})
    result = market_data.load_hist_prices(['A'],'2026-01-01','2026-08-27',adjusted=True)
    assert not calls and not result.get('error')
    assert result['sources']['A']['storage'] == 'AMC_PRICES'
    assert result['dates'][0] == '2026-01-01'
