"""Comparator parity with explicit Following and genuine common observations."""
from datetime import date
import json

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.app.api import pricing
from backend.app.api.schedule import calendar_catalog
from backend.app.core.calendars import calendar_selection, is_business_day, adjust, BusinessDayConvention
from backend.app.core.schemas import BacktestCompareRequest
from backend.app.services import market_data, market_history

T = 1/365.25


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('STRUCTURA_SCENARIO_MARKET', raising=False)
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def store(ticker, dates=None, scale=1):
    dates = dates or ['2024-01-02', '2024-01-04', '2024-01-05', '2024-01-08']
    values = pd.Series([scale*(100+i+i*i*.1) for i in range(len(dates))], index=pd.to_datetime(dates))
    market_history.store_history(ticker, values, False, dates[0], dates[-1])
    return values


def request(**changes):
    return BacktestCompareRequest(**{**dict(script=f'AT {T}:\n  PAY 1.001\n  STOP', T=T,
        candidates=[dict(name='A', ticker='A'), dict(name='B', ticker='B')],
        end_date='2024-01-08', freq=252), **changes})


def test_comparison_uses_local_history_following_and_effective_payment_irr():
    store('A'); store('B', scale=2)
    result = pricing.backtest_compare_endpoint(request())
    assert result['stage'] == 'individual'
    assert result['history_policy']['mode'] == 'following'
    assert result['history_policy']['max_delay_days'] == 10
    assert result['history_policy']['effective_start'] == '2024-01-02'
    assert result['history_policy']['adjustment_count'] == 2
    assert {row['ticker'] for row in result['history_policy']['adjustments']} == {'A', 'B'}
    assert all(row['median_irr'] == pytest.approx(1.001**(365.25/2)-1, abs=5.1e-5) for row in result['results'])
    assert result['history_policy']['disclaimer']
    assert result['market_data']['alignment'] == 'GENUINE_COMMON_OBSERVATIONS'


@pytest.mark.parametrize('mode,limit,message', [('strict', 10, 'Mode strict'), ('following', 0, 'maximum 0')])
def test_comparison_refuses_unacceptable_substitutions_without_reducing_its_windows(mode, limit, message):
    store('A'); store('B')
    with pytest.raises(HTTPException) as error:
        pricing.backtest_compare_endpoint(request(history_mode=mode, max_delay_days=limit))
    assert error.value.status_code == 422 and message in error.value.detail
    assert '2024-01-03' in error.value.detail


@pytest.mark.parametrize('delay,allowed', [(10, True), (11, False)])
def test_comparator_ten_day_limit_is_inclusive(delay, allowed):
    dates = ['2024-01-02', f'2024-01-{3+delay:02}', '2024-02-01']
    store('A', dates); store('B', dates)
    if allowed:
        result = pricing.backtest_compare_endpoint(request(end_date='2024-02-01'))
        assert {row['delay_days'] for row in result['history_policy']['adjustments']} == {10}
    else:
        with pytest.raises(HTTPException) as error:
            pricing.backtest_compare_endpoint(request(end_date='2024-02-01'))
        assert '11 jours calendaires' in error.value.detail


def test_all_candidates_use_the_same_genuine_common_start_and_end():
    store('A', ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'])
    store('B', ['2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'])
    result = pricing.backtest_compare_endpoint(request(history_mode='strict'))
    assert result['history_policy']['effective_start'] == '2024-01-03'
    assert result['market_data']['first_dates'] == {'A': '2024-01-02', 'B': '2024-01-03'}
    assert {row['n_windows'] for row in result['results']} == {1}
    assert result['history_policy']['adjustments'] == []


def test_missing_candidate_is_reported_and_full_backtest_stays_strict():
    store('A')
    result = pricing.backtest_compare_endpoint(request())
    assert result['shortlist'] == ['A']
    assert result['excluded_universe']['B']['reason'] == 'NO_OBSERVATIONS'
    assert result['market_coverage']['complete'] is False
    assert result['history_policy']['effective_start'] == '2024-01-02'
    full = market_data.load_hist_prices(['A', 'B'], None, '2024-01-08', raw_history=True)
    assert 'B' in full['error']


def test_comparator_names_all_candidates_when_no_history_is_available():
    with pytest.raises(HTTPException) as error:
        pricing.backtest_compare_endpoint(request())
    assert error.value.status_code == 422
    assert 'A' in error.value.detail and 'B' in error.value.detail


def test_partial_scenario_keeps_its_synthetic_label_when_the_first_candidate_is_missing(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.json'
    path.write_text(json.dumps({'provider': 'SYNTHETIC_SCENARIO', 'method': 'Synthetic test only',
        'series': {'B': {'2024-01-02': 100., '2024-01-04': 101., '2024-01-05': 102., '2024-01-08': 103.}}}), encoding='utf-8')
    monkeypatch.setenv('STRUCTURA_SCENARIO_MARKET', str(path))
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD', '1')
    result = pricing.backtest_compare_endpoint(request())
    assert result['shortlist'] == ['B']
    assert result['market_data']['price_type'] == 'SYNTHETIC_RAW_CLOSE'
    assert {warning['code'] for warning in result['market_data']['warnings']} == {'INCOMPLETE_HISTORY', 'SYNTHETIC_DATA'}


@pytest.mark.parametrize('all_undefined', [False, True])
def test_undefined_irrs_are_counted_dated_or_reported_as_an_unrankable_candidate(monkeypatch, all_undefined):
    dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
    prices = {'A': [100.,90.,80.,70.] if all_undefined else [100.,90.,99.,108.], 'B': [100.,101.,102.,103.]}
    monkeypatch.setattr(pricing, 'load_hist_prices', lambda *args, **kwargs: dict(dates=dates, prices=prices))
    req = request(script=f'AT {T}:\n  PAY 1.001\nAT {2*T}:\n  IF WOF >= 1:\n    PAY 1.001\n  ELSE:\n    PAY -3\n  STOP',
        T=2*T, freq=1, history_mode='strict')
    result = pricing.backtest_compare_endpoint(req)
    if all_undefined:
        assert result['excluded_universe']['A']['reason'] == 'NO_USABLE_BACKTEST_WINDOW'
        assert result['shortlist'] == ['B']
    else:
        row = next(row for row in result['results'] if row['tickers'] == ['A'])
        assert row['n_excluded'] == 1 and row['n_windows'] == 1
        assert row['excluded_windows'] == [{'date': '2024-01-02', 'reason': 'TRI non défini'}]


def test_baskets_retain_common_quotes_and_deduplicate_adjustments_across_stages():
    dates = pd.bdate_range('2024-01-02', periods=32).strftime('%Y-%m-%d').tolist()
    dates.remove('2024-01-03')
    store('A', dates); store('B', dates, scale=2)
    result = pricing.backtest_compare_endpoint(request(end_date=dates[-1], basket_size=2))
    assert result['stage'] == 'combinations'
    assert result['results'][0]['n_adjustments'] == 2
    assert result['history_policy']['adjustment_count'] == 2
    assert len(result['individual']) == 2
    assert len(result['results'][0]['corr_matrix']) == 2


def test_comparator_preserves_settlement_context_and_final_payment_lag():
    store('A', ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-08'])
    store('B', ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-08'])
    req = request(script='AT MATURITY:\n  PAY 1.001', strike_date='2026-01-02', payment_date='2026-01-06',
        settlement_ccy='EUR', history_mode='strict')
    result = pricing.backtest_compare_endpoint(req)
    assert result['results'][0]['median_irr'] == pytest.approx(1.001**(365.25/4)-1, abs=5.1e-5)
    assert req.settlement_ccy == 'EUR'


def test_milan_and_paris_are_observation_venues_not_settlement_centres():
    catalog = calendar_catalog()
    assert {'XMIL', 'XPAR'} <= set(catalog['observation_codes'])
    assert not {'XMIL', 'XPAR'} & set(catalog['settlement_codes'])
    with pytest.raises(ValueError):
        calendar_selection({'settlement_calendars': ['XMIL']}, 'settlement')


@pytest.mark.parametrize('iso', ['2026-12-24', '2026-12-31'])
def test_milan_closure_does_not_close_paris_or_euro_settlement(iso):
    day = date.fromisoformat(iso)
    assert not is_business_day(day, 'XMIL')
    assert is_business_day(day, 'XPAR') and is_business_day(day, 'TARGET')
    assert adjust(day, 'XMIL', BusinessDayConvention.FOLLOWING) > day


def test_combined_observation_rules_remain_distinct_from_settlement():
    day = date(2026, 12, 24)
    all_open = calendar_selection({'observation_calendars': ['XMIL', 'XPAR'], 'observation_join': 'all_open'}, 'observation')
    any_open = calendar_selection({'observation_calendars': ['XMIL', 'XPAR'], 'observation_join': 'any_open'}, 'observation')
    assert not is_business_day(day, all_open)
    assert is_business_day(day, any_open)
    assert is_business_day(day, 'TARGET')
