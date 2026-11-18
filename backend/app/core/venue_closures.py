"""Weekday exchange closures, so that a venue holiday is not read as a data gap.

The history continuity rule (D03, three calendar days) counts the days between
two quotes. Easter on Euronext (Good Friday and Easter Monday closed) leaves
four days between Thursday and Tuesday, and a Thursday Christmas does the same:
every European history crossing either was refused as UNBOUNDED_HISTORY_GAP,
the replay of a deal's lifecycle included. A day the venue does not trade
carries no missing information, so it is removed from that count. Weekends
still count as before and a missing close on an open weekday is still a gap,
so the rule only stops penalising closures; it accepts nothing it refused for
any other reason.

The venue is the provider's declared exchange, else the ticker suffix. An
unknown venue, or a calendar that cannot be built, leaves the calendar-day
rule unchanged: the check fails closed, as before.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
import logging

import numpy as np
import pandas as pd

from .fixing_finality import VENUES, session_calendar

logger = logging.getLogger(__name__)

SUFFIX_CALENDARS = {'PA': 'XPAR', 'MI': 'XMIL', 'AS': 'XAMS', 'BR': 'XBRU', 'DE': 'XETR',
                    'L': 'XLON', 'SW': 'XSWX', 'T': 'XTKS', 'HK': 'XHKG', 'SI': 'XSES',
                    'MC': 'XMAD', 'TO': 'XTSE', 'AX': 'XASX'}


def venue_calendar(ticker: str, source: dict | None = None) -> str | None:
    """Exchange calendar name of a listing, never inferred from its currency."""
    declared = VENUES.get((source or {}).get('exchange'))
    if declared:
        return declared
    if '.' in ticker:
        return SUFFIX_CALENDARS.get(ticker.rsplit('.', 1)[-1].upper())
    return None


@lru_cache(maxsize=1024)
def _year_closures(name: str, year: int) -> tuple:
    sessions = {day.date() for day in session_calendar(name, year).sessions_in_range(
        f'{year}-01-01', f'{year}-12-31')}
    first = date(year, 1, 1)
    days = (first + timedelta(n) for n in range((date(year + 1, 1, 1) - first).days))
    return tuple(day for day in days if day.weekday() < 5 and day not in sessions)


def weekday_closures(name: str | None, start, end) -> np.ndarray:
    """Sorted weekday closures of the venue between start and end, inclusive."""
    if not name:
        return np.array([], dtype='datetime64[ns]')
    start, end = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    try:
        days = [day for year in range(start.year, end.year + 1)
                for day in _year_closures(name, year) if start <= day <= end]
    except Exception:
        logger.warning('Calendrier %s indisponible ; règle calendaire conservée.', name, exc_info=True)
        return np.array([], dtype='datetime64[ns]')
    return np.array(days, dtype='datetime64[ns]')


def closures_between(closures: np.ndarray, after, upto, *, include_upto: bool) -> np.ndarray:
    """Count of closures in (after, upto] — or (after, upto) — element-wise."""
    after = np.asarray(pd.DatetimeIndex(after).values, dtype='datetime64[ns]')
    upto = np.asarray(pd.DatetimeIndex(upto).values, dtype='datetime64[ns]')
    if closures.size == 0:
        return np.zeros(len(upto), dtype=int)
    right = np.searchsorted(closures, upto, side='right' if include_upto else 'left')
    return right - np.searchsorted(closures, after, side='right')


def quote_gaps(index: pd.DatetimeIndex, closures: np.ndarray) -> pd.Series:
    """Days without a quote between consecutive observations, venue closures excluded."""
    index = pd.DatetimeIndex(index).sort_values()
    if len(index) < 2:
        return pd.Series([], dtype=float)
    calendar = (index[1:] - index[:-1]).days.to_numpy() - 1
    closed = closures_between(closures, index[:-1], index[1:], include_upto=False)
    return pd.Series(calendar - closed, index=index[1:], dtype=float)
