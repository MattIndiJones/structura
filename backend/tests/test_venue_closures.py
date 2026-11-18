"""A venue closure is not a gap in a price history.

Measured on 18/11/2026: on the generic path, GLE.PA from 05/01/2026 was
refused (UNBOUNDED_HISTORY_GAP) on raw and adjusted closes alike, as was every
European basket crossing Easter, while AAPL passed. The D03 continuity rule
counts calendar days between quotes, and Euronext closes on Good Friday and
Easter Monday: Thursday to Tuesday is four days. The lifecycle replay, the
deal MtM, the VaR and the CCR all read that path.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.app.core.fixing_finality import session_calendar
from backend.app.core.venue_closures import quote_gaps, venue_calendar, weekday_closures
from backend.app.services import market_data, market_history

START, END = '2026-03-02', '2026-04-14'
GOOD_FRIDAY, EASTER_MONDAY = '2026-04-03', '2026-04-06'


@pytest.fixture(autouse=True)
def isolated_market(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('STRUCTURA_SCENARIO_MARKET', raising=False)
    monkeypatch.setattr(market_data, '_HAS_YF', False)
    # amc_prices binds its directory at first import: keep real series out.
    from backend.app.core import amc_prices
    monkeypatch.setattr(amc_prices, '_load_ticker_map', lambda: {})
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def _store(ticker, venue, drop=(), adjusted=None):
    index = session_calendar(venue, 2026).sessions_in_range(START, END)
    values = pd.Series(50 * np.exp(.001 * np.arange(len(index))), index=index).drop(
        [pd.Timestamp(day) for day in drop])
    for flag in ((False, True) if adjusted is None else (adjusted,)):
        market_history.store_history(ticker, values, flag, START, END)
    return values


def test_euronext_easter_closures_are_known():
    closures = {str(day)[:10] for day in weekday_closures('XPAR', START, END)}
    assert closures == {GOOD_FRIDAY, EASTER_MONDAY}
    gaps = quote_gaps(session_calendar('XPAR', 2026).sessions_in_range(START, END),
                      weekday_closures('XPAR', START, END))
    assert gaps.max() == 2          # a weekend; Easter no longer counts four days


@pytest.mark.parametrize('adjusted', [False, True])
def test_a_history_across_easter_is_accepted(adjusted):
    values = _store('GLE.PA', 'XPAR')
    history = market_data.load_hist_prices(['GLE.PA'], START, END, adjusted=adjusted)
    assert not history.get('error'), history.get('error')
    assert history['prices']['GLE.PA'] == pytest.approx(list(values))
    assert history['closure_calendars'] == {'GLE.PA': 'XPAR'}


def test_missing_open_sessions_are_still_a_gap():
    # Wednesday to Friday missing: Tuesday to Monday is five days without a
    # quote and no closure among them — refused, exactly as before.
    _store('GLE.PA', 'XPAR', drop=('2026-03-11', '2026-03-12', '2026-03-13'))
    history = market_data.load_hist_prices(['GLE.PA'], START, END, adjusted=False)
    assert 'UNBOUNDED_HISTORY_GAP' in history['error']


def test_an_unknown_venue_keeps_the_calendar_day_rule():
    _store('ZZZ', 'XPAR')
    assert venue_calendar('ZZZ') is None
    history = market_data.load_hist_prices(['ZZZ'], START, END, adjusted=False)
    assert 'UNBOUNDED_HISTORY_GAP' in history['error']


def test_the_declared_exchange_wins_over_the_suffix():
    assert venue_calendar('ZZZ', {'exchange': 'PAR'}) == 'XPAR'
    assert venue_calendar('GLE.PA') == 'XPAR'


def test_a_closed_venue_is_carried_over_another_venue_session():
    """Tokyo trades on Easter Monday, Paris does not: the Paris close of
    Thursday is carried to that row, four calendar days but two closures."""
    _store('GLE.PA', 'XPAR')
    _store('7203.T', 'XTKS')
    history = market_data.load_hist_prices(['GLE.PA', '7203.T'], START, END, adjusted=False)
    assert not history.get('error'), history.get('error')
    row = history['dates'].index(EASTER_MONDAY)
    assert history['source_observation_dates']['GLE.PA'][row] == '2026-04-02'
    assert history['carry_age_days']['GLE.PA'][row] == 2


def test_storage_status_qualifies_a_history_across_easter():
    _store('GLE.PA', 'XPAR')
    status = market_history.storage_status('GLE.PA', END)
    assert all(base['long_gaps'] == 0 for base in status['bases'].values())
    assert status['consumer_available']
