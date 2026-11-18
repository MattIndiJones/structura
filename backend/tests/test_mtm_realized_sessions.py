"""Le MtM « marché actuel » qualifie son historique sur les séances de la place.

Constaté le 18/11/2026 sur un autocall GLE.PA : « Historique incomplet ou hors
politique : GLE.PA (UNBOUNDED_HISTORY_GAP) ». La politique générique de
continuité tient tout intervalle de plus de trois jours calendaires pour une
lacune ; Pâques (vendredi saint et lundi de Pâques fermés sur Euronext) en fait
quatre, et toute fenêtre d'un an d'une action européenne était refusée. Le
Pricer et le comparateur en avaient été corrigés le 01/11 et le 03/11
(`session_aware`) ; le MtM du deal lisait encore le chemin générique.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.app.core import deal_valuation
from backend.app.core.calibration import calibration_history_start
from backend.app.core.fixing_finality import session_calendar
from backend.app.services import market_data, market_history
from backend.tests.test_calibration_window import _deal, _loader, _session

ASOF = date(2026, 4, 14)   # fenêtre d'un an : Noël 2025 et Pâques 2026 dedans


@pytest.fixture(autouse=True)
def isolated_market(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('STRUCTURA_SCENARIO_MARKET', raising=False)
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    # amc_prices binds its store directory at first import, which another
    # collected test module may trigger before this fixture: the real GLE.PA
    # series would then fill the omitted session. No AMC series here.
    from backend.app.core import amc_prices
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda: {})
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def _store_xpar(ticker='GLE.PA', omitted=None):
    start = calibration_history_start(ASOF)
    index = session_calendar('XPAR', ASOF.year - 1).sessions_in_range(start.isoformat(), ASOF.isoformat())
    values = pd.Series(60 * np.exp(.0003 * np.arange(len(index)) + .01 * np.sin(np.arange(len(index)))),
                       index=index)
    if omitted:
        values = values.drop(pd.Timestamp(omitted))
    market_history.store_history(ticker, values, True, start.isoformat(), ASOF.isoformat())
    return start.isoformat(), values


def test_easter_closure_is_not_a_gap_on_the_calibration_path():
    start, values = _store_xpar()
    history = market_data.load_session_calibration_history(['GLE.PA'], start, ASOF)
    assert not history.get('error'), history
    assert history['session_qualification']['calendars'] == {'GLE.PA': 'XPAR'}
    assert history['session_qualification']['price_substitutions'] == 0
    assert history['prices']['GLE.PA'] == pytest.approx(list(values))


def test_a_missing_close_on_an_open_session_is_still_refused():
    start, _ = _store_xpar(omitted='2026-03-10')
    with pytest.raises(ValueError, match='clôture\\(s\\) manquante\\(s\\) sur une séance ouverte'):
        market_data.load_session_calibration_history(['GLE.PA'], start, ASOF)


def _qualified_recorder(qualified):
    def session_history(tickers, start, asof, provider=None):
        qualified.append((tuple(tickers), start, asof))
        return _loader([])(tickers, start, asof.isoformat(), True)
    return session_history


@pytest.mark.parametrize('entry', ['route', 'core'])
def test_current_market_mtm_reads_the_session_qualified_history(monkeypatch, entry):
    """The realized recalibration must go through the session-qualified loader.

    'route' is the path the deal screen calls: it injects load_hist_prices
    explicitly. The first version of the fix only covered the core called
    without injection, and the screen kept the generic refusal."""
    from backend.app.api.deals import valuation
    session = _session()
    today = date.today()
    deal = _deal(session, today.replace(day=1), today.replace(year=today.year + 2), with_strike_event=True)
    calls, qualified = [], []
    replay = _loader(calls)

    def replay_loader(tickers, start, end=None, adjusted=False, provider=None, **kw):
        assert not adjusted, 'la calibration ne doit plus lire le chemin générique'
        return replay(tickers, start, end, adjusted)

    request = deal_valuation.MtmRequest(recalibrate='realized')
    monkeypatch.setattr(deal_valuation, 'dividend_profile', lambda *_a, **_k: {'ok': False})
    if entry == 'route':
        monkeypatch.setattr(valuation, 'load_hist_prices', replay_loader)
        monkeypatch.setattr(valuation, 'dividend_profile', lambda *_a, **_k: {'ok': False})
        monkeypatch.setattr(valuation, 'load_session_calibration_history', _qualified_recorder(qualified))
        payload, _ = valuation._mtm_core(deal, session, 1000, request)
    else:
        monkeypatch.setattr(deal_valuation, 'load_hist_prices', replay_loader)
        monkeypatch.setattr(deal_valuation, 'load_session_calibration_history', _qualified_recorder(qualified))
        payload, _ = deal_valuation.mtm_core(deal, session, 1000, request)
    assert qualified == [(('TK1', 'TK2'), calibration_history_start(today, 252).isoformat(), today)]
    assert payload['market_used']['source'] == 'realized'
    # The replay of the lifecycle keeps the raw, unadjusted closes.
    assert calls


def test_an_unqualified_history_is_a_422_with_the_reason(monkeypatch):
    session = _session()
    today = date.today()
    deal = _deal(session, today.replace(day=1), today.replace(year=today.year + 2), with_strike_event=True)
    replay = _loader([])
    monkeypatch.setattr(deal_valuation, 'load_hist_prices',
                        lambda tickers, start, end=None, adjusted=False, provider=None, **kw:
                        replay(tickers, start, end, adjusted))

    def missing(*_args, **_kwargs):
        raise ValueError('TK1 : 1 clôture(s) manquante(s) sur une séance ouverte (XPAR), première le 2026-03-10.')

    monkeypatch.setattr(deal_valuation, 'load_session_calibration_history', missing)
    with pytest.raises(deal_valuation.HTTPException) as failure:
        deal_valuation.mtm_core(deal, session, 1000, deal_valuation.MtmRequest(recalibrate='realized'),
                                dividend_loader=lambda *_: {'ok': False})
    assert failure.value.status_code == 422
    assert 'séance ouverte' in failure.value.detail
