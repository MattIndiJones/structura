"""Max acquisition, durable reuse and reference-wide coverage without a network."""
import pandas as pd
import pytest
from sqlmodel import Session, create_engine

from backend.app.core import amc_prices
from backend.app.services import market_data, market_history


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('STRUCTURA_INSTALLATION_CONFIG', raising=False)
    monkeypatch.delenv('STRUCTURA_SCENARIO_MARKET', raising=False)
    monkeypatch.setattr(amc_prices, '_PRICE_STORE', tmp_path/'underlying_prices')
    monkeypatch.setattr(amc_prices, '_TICKER_MAP_FILE', tmp_path/'underlying_prices'/'_ticker_map.json')
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def values(dates=('1993-10-18', '2024-01-02', '2024-01-03'), scale=1):
    return pd.Series([scale*(100+i) for i in range(len(dates))], index=pd.to_datetime(dates))


def provider(monkeypatch, histories):
    calls = []
    class Ticker:
        fast_info = {'currency': 'EUR'}
        def __init__(self, ticker):
            self.ticker = ticker
        def history(self, **kwargs):
            calls.append((self.ticker, kwargs))
            result = histories[self.ticker]
            if isinstance(result, Exception):
                raise result
            return result.to_frame('Close')
    fake = type('Provider', (), {'Ticker': Ticker})
    monkeypatch.setattr(market_data, 'yf', fake)
    monkeypatch.setattr(amc_prices, 'yf', fake)
    monkeypatch.setattr(market_data, '_HAS_YF', True)
    return calls


@pytest.mark.parametrize('start', [None, '2024-01-02'])
def test_short_cache_expands_to_max_and_reuses_disk_after_memory_clear(monkeypatch, start):
    market_history.store_history('A', values().iloc[1:], False, '2024-01-02', '2024-01-03')
    calls = provider(monkeypatch, {'A': values()})
    result = market_data.load_hist_prices(['A'], start, '2024-01-03', raw_history=True, full_history=True)
    assert not result.get('error')
    assert result['dates'][0] == (start or '1993-10-18')
    assert calls == [('A', dict(period='max', end='2024-01-04', auto_adjust=False))]
    disk, source = market_history.local_history('A', '1900-01-01', '2024-01-03', False)
    assert disk.index[0] == pd.Timestamp('1993-10-18')
    assert source['history_scope'] == 'MAX_AVAILABLE_REQUESTED'
    assert source['full_history_requested_end'] == '2024-01-03'
    market_data.vider_cache_prix()
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    reloaded = market_data.load_hist_prices(['A'], None, '2024-01-03', raw_history=True)
    assert reloaded['prices']['A'] == list(values())
    assert reloaded['sources']['A']['storage'] == 'MARKET_HISTORY'
    assert len(calls) == 1


def test_all_tickers_are_attempted_and_short_cache_is_not_a_silent_fallback(monkeypatch):
    market_history.store_history('B', values().iloc[1:], False, '2024-01-02', '2024-01-03')
    calls = provider(monkeypatch, {'A': values(), 'B': RuntimeError('offline'), 'C': values(scale=3)})
    result = market_data.load_hist_prices(['A', 'B', 'C', 'A'], None, '2024-01-03', raw_history=True, allow_partial=True)
    assert [ticker for ticker, _ in calls] == ['A', 'B', 'C']
    assert result['coverage']['included'] == ['A', 'C']
    assert result['missing_reasons']['B']['reason'] == 'PROVIDER_UNAVAILABLE: RuntimeError'
    disk, source = market_history.local_history('B', '1900-01-01', '2024-01-03', False)
    assert len(disk) == 2 and 'history_scope' not in source
    assert market_history.local_history('C', '1900-01-01', '2024-01-03', False)[1]['history_scope'] == 'MAX_AVAILABLE_REQUESTED'


def test_full_history_replaces_split_rebased_values_but_partial_updates_preserve_scope(monkeypatch):
    market_history.store_history('A', values(scale=10), False, '1993-10-18', '2024-01-03')
    provider(monkeypatch, {'A': values()})
    market_data.load_hist_prices(['A'], None, '2024-01-03', raw_history=True)
    market_history.store_history('A', values().iloc[-1:], False, '2024-01-03', '2024-01-03')
    disk, source = market_history.local_history('A', '1900-01-01', '2024-01-03', False)
    assert list(disk) == list(values())
    assert source['full_history_requested_end'] == '2024-01-03'


def test_later_end_rechecks_max_and_ordinary_calibration_stays_bounded(monkeypatch):
    market_history.store_history('A', values(), False, '1900-01-01', '2024-01-02', full_history=True)
    calls = provider(monkeypatch, {'A': values()})
    market_data.load_hist_prices(['A'], None, '2024-01-03', raw_history=True)
    market_data.load_hist_prices(['A'], '2024-01-02', '2024-01-03', adjusted=True, raw_history=True)
    assert calls[0][1]['period'] == 'max'
    assert calls[1][1] == dict(start='2024-01-02', end='2024-01-04', auto_adjust=True)


def test_persistence_error_is_an_explicit_failure_and_old_cache_survives(monkeypatch):
    market_history.store_history('A', values().iloc[-1:], False, '2024-01-03', '2024-01-03')
    provider(monkeypatch, {'A': values()})
    monkeypatch.setattr(market_history, 'store_history', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('disk full')))
    result = market_data.load_hist_prices(['A'], None, '2024-01-03', raw_history=True)
    assert result.get('error') and result['missing_reasons']['A']['reason'] == 'HISTORY_PERSISTENCE_FAILED'
    assert result['sources']['A']['persisted'] is False
    assert len(market_history.local_history('A', '1900-01-01', '2024-01-03', False)[0]) == 1


def test_adjusted_calibration_refresh_preserves_max_scope_without_mixing_rebasings(monkeypatch):
    market_history.store_history('A', values(scale=2), True, '1900-01-01', '2024-01-03', full_history=True)
    calls = provider(monkeypatch, {'A': values()})
    result = market_data.load_hist_prices(['A'], '2024-01-02', '2024-01-31', adjusted=True, raw_history=True)
    assert not result.get('error') and result['dates'] == ['2024-01-02', '2024-01-03']
    assert calls[0][1] == dict(period='max', end='2024-02-01', auto_adjust=True)
    disk, source = market_history.local_history('A', '1900-01-01', '2024-01-31', True, prefer_full=True)
    assert list(disk) == list(values())
    assert source['full_history_requested_end'] == '2024-01-31'


def test_admin_max_download_persists_both_price_conventions(monkeypatch):
    calls = provider(monkeypatch, {'A': values()})
    amc_prices.fetch_prices('A', 'A', end='2024-01-04')
    assert calls == [('A', dict(period='max', end='2024-01-04', auto_adjust=True)),
                     ('A', dict(period='max', end='2024-01-04', auto_adjust=False))]
    for adjusted in (False, True):
        disk, source = market_history.local_history('A', '1900-01-01', '2024-01-03', adjusted, prefer_full=True)
        assert list(disk) == list(values()) and source['history_scope'] == 'MAX_AVAILABLE_REQUESTED'


def test_admin_catalog_uses_all_reference_tickers_including_inactive_and_custom_groups(monkeypatch):
    from backend.app.api import admin
    from backend.app.db.models import Underlying
    engine = create_engine('sqlite://')
    Underlying.__table__.create(engine)
    with Session(engine) as session:
        session.add_all([Underlying(ticker='A', label='Alpha', group_name='Personnalisé'),
                         Underlying(ticker='A', label='Alpha', group_name='Banques'),
                         Underlying(ticker='B', label='Beta', group_name='Autres', active=False)])
        session.commit()
        catalog = admin.market_data_catalog(None, session)
        assert [row['ticker'] for row in catalog] == ['A', 'B']
        assert catalog[0]['category'] == 'Personnalisé' and catalog[1]['active'] is False
