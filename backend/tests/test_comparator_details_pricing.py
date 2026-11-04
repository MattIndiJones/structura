"""Exact comparator detail replay and exchange-qualified indicative inputs."""
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from backend.app.api import pricing
from backend.app.core.calibration import calibration_history_start
from backend.app.core.fixing_finality import session_calendar
from backend.app.core.schemas import BacktestCompareRequest, BacktestCompareDetailRequest, PricingRequest
from backend.app.services import market_data, market_history

T = 1/365.25


@pytest.fixture(autouse=True)
def isolated_market(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('STRUCTURA_SCENARIO_MARKET', raising=False)
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    monkeypatch.setattr(market_data, 'dividend_profile', lambda *args, **kwargs: dict(ok=True, yield_declared=.02))
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def comparison():
    a = pd.Series([100.,101.,103.,104.,106.], index=pd.to_datetime(['2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-08']))
    b = a.drop(pd.Timestamp('2024-01-03'))*2
    for ticker, values in [('A',a), ('B',b)]:
        market_history.store_history(ticker, values, False, '2024-01-02', '2024-01-08', full_history=True)
    req = BacktestCompareRequest(script=f'AT {T}:\n  PAY WOF\n  STOP', T=T, freq=252,
        candidates=[dict(name='A',ticker='A'),dict(name='B',ticker='B')], end_date='2024-01-08')
    return pricing.backtest_compare_endpoint(req)


def detail_request(result, **changes):
    context = result['comparison_context']
    return BacktestCompareDetailRequest(**{**dict(comparison=context['request'], tickers=['A'], history_hash=context['history_hash']), **changes})


def test_detail_reuses_the_comparison_universe_and_reproduces_its_ranked_statistics():
    result = comparison()
    detail = pricing.backtest_comparison_detail(detail_request(result))
    row = next(row for row in result['results'] if row['tickers'] == ['A'])
    assert detail['selected_tickers'] == ['A']
    assert detail['rows'][0]['date'] == '2024-01-02' and detail['n_windows'] == row['n_windows']
    assert detail['mean_irr'] == row['mean_irr'] and detail['median_irr'] == row['median_irr']
    assert detail['p10'] == row['p10_irr'] and detail['early_recall_pct'] == row['early_recall_pct']
    # A has a quote on Jan 3. It must still follow the universe's common date Jan 4.
    shift = detail['history_policy']['adjustments'][0]
    assert shift['effective_date'] == '2024-01-04' and shift['reason'] == 'COMMON_BASKET_DATE'
    assert detail['history_policy']['comparison_basis'] == 'COMMON_USABLE_UNIVERSE_OBSERVATIONS'


def test_detail_rejects_a_changed_history_even_if_the_selected_asset_is_unchanged():
    result = comparison()
    market_history.store_history('B', pd.Series([333.], index=pd.to_datetime(['2024-01-04'])), False, '2024-01-04', '2024-01-04')
    with pytest.raises(HTTPException) as failure:
        pricing.backtest_comparison_detail(detail_request(result))
    assert failure.value.status_code == 409 and 'Relancez la comparaison' in failure.value.detail


def test_comparison_freezes_implicit_cutoff_and_origin_for_a_later_detail(monkeypatch):
    from backend.app import runtime
    from backend.app.core.payscript.parser import analysis_origin
    initial = comparison()
    req = BacktestCompareRequest.model_validate({**initial['comparison_context']['request'], 'end_date': None, 'anchor': None})
    monkeypatch.setattr(runtime, 'business_today', lambda: date(2024,1,8))
    result = pricing.backtest_compare_endpoint(req)
    assert result['comparison_context']['request']['end_date'] == '2024-01-08'
    assert result['comparison_context']['request']['anchor'] == analysis_origin(req).isoformat()
    monkeypatch.setattr(runtime, 'business_today', lambda: date(2024,1,9))
    detail = pricing.backtest_comparison_detail(detail_request(result))
    assert detail['history_hash'] == result['comparison_context']['history_hash']


@pytest.mark.parametrize('tickers', [['C'], ['A','A'], ['A','B']])
def test_detail_rejects_an_unrelated_or_wrong_size_selection(tickers):
    result = comparison()
    with pytest.raises(HTTPException) as failure:
        pricing.backtest_comparison_detail(detail_request(result, tickers=tickers))
    assert failure.value.status_code == 422


def session_history(asof='2026-04-14', omitted=None, ticker='CS.PA'):
    day = date.fromisoformat(asof)
    start = calibration_history_start(day)
    calendar = session_calendar('XPAR', day.year-1)
    index = calendar.sessions_in_range(start.isoformat(), asof)
    values = pd.Series(100*np.exp(.0002*np.arange(len(index))+.007*np.sin(np.arange(len(index)))), index=index)
    if omitted:
        values = values.drop(pd.Timestamp(omitted))
    market_history.store_history(ticker, values, True, start.isoformat(), asof)
    return values


def test_realized_reference_accepts_easter_closures_without_filling_or_changing_its_estimator():
    values = session_history()
    assert 'UNBOUNDED_HISTORY_GAP' in market_data.load_hist_vol(['CS.PA'], asof='2026-04-14')['error']
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-14', session_aware=True)
    assert not data.get('error'), data
    returns = np.diff(np.log(values.to_numpy()))[-252:]
    assert data['vols']['CS.PA'] == pytest.approx(math.sqrt(252*np.mean(returns**2)))
    assert data['session_qualification']['price_substitutions'] == 0
    assert data['session_qualification']['calendars'] == {'CS.PA':'XPAR'}
    assert data['price_type'] == 'ADJUSTED_CLOSE' and data['n_obs'] == 252


def test_missing_open_session_remains_an_error_for_pricing_inputs():
    session_history(omitted='2026-03-30')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-14', session_aware=True)
    assert 'séance ouverte' in data['error'] and '2026-03-30' in data['error']
    assert 'Aucun cours remplacé' in data['error']


def test_market_reload_http_qualifies_bnp_exchange_closures():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api import market_data as api
    from backend.app.api.auth import get_current_user

    values = session_history(ticker='BNP.PA')
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as client:
        response = client.get('/api/finance/hist_vol', params={
            'tickers': 'BNP.PA', 'asof': '2026-04-14', 'window_days': 252, 'session_aware': True})
    assert response.status_code == 200
    data = response.json()
    assert not data.get('error'), data
    returns = np.diff(np.log(values.to_numpy()))[-252:]
    assert data['vols']['BNP.PA'] == pytest.approx(math.sqrt(252*np.mean(returns**2)))
    assert data['session_qualification']['price_substitutions'] == 0


@pytest.mark.parametrize('intraday_bar', [False, True])
def test_current_open_session_is_not_a_missing_or_completed_close(monkeypatch, intraday_bar):
    from backend.app import runtime
    monkeypatch.setattr(runtime, 'business_now', lambda: datetime(2026, 4, 14, 12, tzinfo=timezone.utc))
    values = session_history(asof='2026-04-13')
    if intraday_bar:
        partial = pd.concat([values, pd.Series([999.], index=pd.to_datetime(['2026-04-14']))])
        market_history.store_history('CS.PA', partial, True, values.index[0].date().isoformat(), '2026-04-14')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-14', session_aware=True)
    assert not data.get('error'), data
    returns = np.diff(np.log(values.to_numpy()))[-252:]
    assert data['vols']['CS.PA'] == pytest.approx(math.sqrt(252*np.mean(returns**2)))
    assert data['asof_effective'] == '2026-04-13'
    assert data['session_qualification']['pending_sessions'] == {'CS.PA': ['2026-04-14']}
    assert data['session_qualification']['excluded_non_session_bars'] == {'CS.PA': 0}


def test_current_session_close_is_required_after_exchange_close(monkeypatch):
    from backend.app import runtime
    monkeypatch.setattr(runtime, 'business_now', lambda: datetime(2026, 4, 14, 18, tzinfo=timezone.utc))
    session_history(asof='2026-04-13')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-14', session_aware=True)
    assert 'séance ouverte' in data['error'] and '2026-04-14' in data['error']


def test_reload_sources_the_venue_of_an_unsuffixed_ticker_without_inventing_its_calendar(monkeypatch):
    from types import SimpleNamespace

    day = date(2026, 4, 14)
    start = calibration_history_start(day)
    index = session_calendar('XNAS', day.year-1).sessions_in_range(start.isoformat(), day.isoformat())
    values = pd.Series(100*np.exp(.0002*np.arange(len(index))+.007*np.sin(np.arange(len(index)))), index=index)
    market_history.store_history('AAPL', values, True, start.isoformat(), day.isoformat())
    calls = []
    def metadata():
        calls.append('venue')
        return {'exchangeName': 'NMS', 'exchangeTimezoneName': 'America/New_York'}
    monkeypatch.setattr(market_data, '_HAS_YF', True)
    monkeypatch.setattr(market_data, 'yf', SimpleNamespace(Ticker=lambda tk: SimpleNamespace(get_history_metadata=metadata)))
    data = market_data.load_hist_vol(['AAPL'], asof=day.isoformat(), session_aware=True)
    assert not data.get('error'), data
    assert calls == ['venue']
    assert data['session_qualification']['calendars'] == {'AAPL': 'XNAS'}
    assert data['sources']['AAPL']['calendar_reference_provider'] == 'YAHOO_FINANCE'


def test_reload_refuses_an_unknown_listing_instead_of_assuming_a_us_calendar():
    session_history(ticker='UNKNOWN')
    data = market_data.load_hist_vol(['UNKNOWN'], asof='2026-04-14', session_aware=True)
    assert 'place de cotation inconnue' in data['error']


def test_weekend_cutoff_is_accepted_but_missing_latest_open_session_is_not():
    session_history(asof='2026-04-10')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-12', session_aware=True)
    assert not data.get('error')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-13', session_aware=True)
    assert '2026-04-13' in data['error']


def test_non_session_provider_bars_are_excluded_and_not_reported_as_effective_closes():
    values = session_history(asof='2026-04-10')
    values.loc[pd.Timestamp('2026-04-11')] = 999.
    market_history.store_history('CS.PA', values, True, values.index[0].date().isoformat(), '2026-04-11')
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-12', session_aware=True)
    assert not data.get('error'), data
    assert data['effective_dates']['CS.PA'] == data['asof_effective'] == '2026-04-10'
    assert data['session_qualification']['excluded_non_session_bars']['CS.PA'] == 1


def test_qualified_reference_prices_a_payoff_using_the_explicit_payment_date():
    session_history()
    data = market_data.load_hist_vol(['CS.PA'], asof='2026-04-14', session_aware=True)
    strike, maturity, payment = date(2026,4,14), date(2027,4,14), date(2027,4,19)
    req = PricingRequest(script='AT MATURITY:\n  PAY 1', T=(maturity-strike).days/365.25,
        underlyings=[dict(name='AXA',ticker='CS.PA',ccy='EUR',sigma=data['vols']['CS.PA'],q=data['div_yields']['CS.PA'])],
        corr_matrix=[[1.]], r=.03, N=1000, strike_date=strike, value_date=strike,
        maturity_date=maturity, payment_date=payment, settlement_ccy='EUR')
    result = pricing.price_endpoint(req)
    assert result.price == pytest.approx(math.exp(-.03*(payment-strike).days/365.25), abs=2e-6)
