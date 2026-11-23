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
from backend.app.services.calibration_sessions import qualify_calibration_sessions

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


# ── D03 at the requested date: the last known close on a closed day ──
# Decision of 19/11/2026: on a day the venue does not trade, the last known
# close is the price. Before it, a GLE.PA valuation on Easter Monday was
# refused as STALE: the Thursday close was four calendar days old.

from backend.app.core import market_policy

LAST_THURSDAY = '2026-04-02'


def _store_until_thursday(ticker, venue):
    index = session_calendar(venue, 2026).sessions_in_range(START, LAST_THURSDAY)
    values = pd.Series(50 * np.exp(.001 * np.arange(len(index))), index=index)
    for flag in (False, True):
        market_history.store_history(ticker, values, flag, START, LAST_THURSDAY)
    return values


@pytest.mark.parametrize('asof, closed, accepted', [
    (GOOD_FRIDAY, 1, True), (EASTER_MONDAY, 2, True),
    ('2026-04-07', 2, True),      # five calendar days, three once Easter is removed
    ('2026-04-08', 2, False),     # four: the D03 limit itself is unchanged
])
def test_the_last_close_before_a_closure_is_still_the_price(asof, closed, accepted):
    quality = market_policy.freshness(LAST_THURSDAY, asof, 'history', 'XPAR')
    assert quality['venue_closed_days'] == closed
    assert quality['policy_age_days'] == quality['age_days'] - closed
    assert quality['qualified'] is accepted
    assert quality['status'] == ('CARRIED' if accepted else 'STALE')


def test_without_a_venue_the_calendar_day_rule_is_kept():
    assert not market_policy.freshness(LAST_THURSDAY, EASTER_MONDAY, 'history')['qualified']
    # Reporting FX has no venue: a calendar passed by mistake changes nothing.
    assert not market_policy.freshness(LAST_THURSDAY, EASTER_MONDAY, 'reporting_fx', 'XPAR')['qualified']


def test_weekends_still_age_a_close():
    # Friday 13/03 to Wednesday 18/03, Paris open on Monday and Tuesday.
    quality = market_policy.freshness('2026-03-13', '2026-03-18', 'history', 'XPAR')
    assert quality['venue_closed_days'] == 0 and not quality['qualified']


@pytest.mark.parametrize('adjusted', [False, True])
def test_a_valuation_on_easter_monday_takes_the_thursday_close(adjusted):
    values = _store_until_thursday('GLE.PA', 'XPAR')
    history = market_data.load_hist_prices(['GLE.PA'], START, EASTER_MONDAY, adjusted=adjusted)
    assert not history.get('error'), history.get('error')
    assert history['asof_effective'] == LAST_THURSDAY
    assert history['prices']['GLE.PA'][-1] == pytest.approx(values.iloc[-1])
    quality = history['freshness']['GLE.PA']
    assert quality['status'] == 'CARRIED' and quality['venue_closed_days'] == 2


def test_an_unknown_venue_is_still_stale_on_easter_monday():
    _store_until_thursday('ZZZ', 'XPAR')
    history = market_data.load_hist_prices(['ZZZ'], START, EASTER_MONDAY, adjusted=False)
    assert 'STALE' in history['error']


def test_storage_status_qualifies_easter_monday():
    _store_until_thursday('GLE.PA', 'XPAR')
    assert market_history.storage_status('GLE.PA', EASTER_MONDAY)['consumer_available']


# ── Euro Stoxx 50: the index calendar, not the feed's ──
# Measured on 22/11/2026: Yahoo declares ^STOXX50E on ZRH and its bars follow
# the SIX calendar exactly, so Ascension, Whit Monday, 1 August and 2 January
# are absent although the index constituents trade. Those days are missing
# quotes, not closures: only the Eurex closures may leave the D03 count.

SX5E, SX5E_START, SX5E_END = '^STOXX50E', '2025-09-15', '2026-11-20'
ASCENSION, WHIT_MONDAY, BERCHTOLDSTAG = '2026-05-14', '2026-05-25', '2026-01-02'


def _store_sx5e_as_published(drop=()):
    index = session_calendar('XSWX', 2026).sessions_in_range(SX5E_START, SX5E_END)
    values = pd.Series(5000 * np.exp(.0005 * np.arange(len(index))), index=index).drop(
        [pd.Timestamp(day) for day in drop])
    for flag in (False, True):
        market_history.store_history(SX5E, values, flag, SX5E_START, SX5E_END)
    return values


@pytest.mark.parametrize('source', [None, {'exchange': 'ZRH'}])
def test_the_euro_stoxx_50_follows_eurex_whatever_the_feed_declares(source):
    assert venue_calendar(SX5E, source) == 'XEUR'


def test_a_swiss_holiday_is_not_a_euro_stoxx_50_closure():
    closures = {str(day)[:10] for day in weekday_closures('XEUR', SX5E_START, SX5E_END)}
    assert {GOOD_FRIDAY, EASTER_MONDAY, '2025-12-24', '2025-12-25', '2025-12-26',
            '2025-12-31', '2026-01-01'} <= closures
    assert not closures & {ASCENSION, WHIT_MONDAY, BERCHTOLDSTAG}


@pytest.mark.parametrize('adjusted', [False, True])
def test_the_euro_stoxx_50_history_is_accepted_as_published(adjusted):
    values = _store_sx5e_as_published()
    history = market_data.load_hist_prices([SX5E], SX5E_START, '2026-11-22', adjusted=adjusted)
    assert not history.get('error'), history.get('error')
    assert history['prices'][SX5E] == pytest.approx(list(values))
    assert history['closure_calendars'] == {SX5E: 'XEUR'}


def test_a_session_missing_next_to_a_swiss_holiday_is_still_refused():
    # Friday 22/05 to Wednesday 27/05: four days and no Eurex closure. Under the
    # SIX calendar Whit Monday would be forgiven and this real gap would pass.
    _store_sx5e_as_published(drop=('2026-05-26',))
    history = market_data.load_hist_prices([SX5E], SX5E_START, '2026-11-22', adjusted=False)
    assert 'UNBOUNDED_HISTORY_GAP' in history['error']


# ── The other indices quoted on a single venue ──
# Measured on 23/11/2026 from 03/01/2022: their Yahoo bars carry no off-session
# date against these calendars. Without one, Easter, Golden Week or the Lunar
# New Year were refused as gaps. ^FTSE and ^N225 are declared on FGI and OSA,
# which the venue table does not know, so the session qualification needs the
# same index table as the continuity rule.

INDICES = {'^FCHI': 'XPAR', '^GDAXI': 'XETR', '^FTSE': 'XLON', '^IBEX': 'XMAD',
           '^SSMI': 'XSWX', '^N225': 'XTKS', '^HSI': 'XHKG',
           '^GSPC': 'XNYS', '^NDX': 'XNAS', '^DJI': 'XNYS', '^RUT': 'XNYS'}
INDEX_START, INDEX_END = '2026-01-05', '2026-06-30'


def _index_history(calendar, drop=()):
    index = session_calendar(calendar, 2026).sessions_in_range(INDEX_START, INDEX_END)
    return pd.Series(5000 * np.exp(.0005 * np.arange(len(index))), index=index).drop(
        [pd.Timestamp(day) for day in drop])


@pytest.mark.parametrize('ticker, calendar', INDICES.items())
def test_an_index_history_across_its_closures_is_accepted(ticker, calendar):
    assert venue_calendar(ticker) == calendar
    values = _index_history(calendar)
    market_history.store_history(ticker, values, False, INDEX_START, INDEX_END)
    history = market_data.load_hist_prices([ticker], INDEX_START, INDEX_END, adjusted=False)
    assert not history.get('error'), history.get('error')
    assert history['prices'][ticker] == pytest.approx(list(values))
    assert history['closure_calendars'] == {ticker: calendar}


@pytest.mark.parametrize('ticker, calendar', INDICES.items())
def test_open_sessions_missing_from_an_index_are_still_a_gap(ticker, calendar):
    values = _index_history(calendar, drop=('2026-03-11', '2026-03-12', '2026-03-13'))
    market_history.store_history(ticker, values, False, INDEX_START, INDEX_END)
    history = market_data.load_hist_prices([ticker], INDEX_START, INDEX_END, adjusted=False)
    assert 'UNBOUNDED_HISTORY_GAP' in history['error']


def _session_sample(ticker, values):
    days = [day.date().isoformat() for day in values.index]
    return {'dates': days, 'prices': {ticker: [float(x) for x in values]},
            'observation_dates': {ticker: days}, 'sources': {}}


@pytest.mark.parametrize('ticker, calendar', INDICES.items())
def test_the_session_qualification_reads_the_index_calendar(ticker, calendar):
    values = _index_history(calendar)
    result = qualify_calibration_sessions(_session_sample(ticker, values), [ticker],
                                          date.fromisoformat(INDEX_END), venue_loader=lambda _: {})
    assert result['session_qualification']['calendars'] == {ticker: calendar}
    assert result['dates'] == [day.date().isoformat() for day in values.index]


@pytest.mark.parametrize('ticker, calendar', INDICES.items())
def test_the_session_qualification_still_refuses_a_missing_index_close(ticker, calendar):
    values = _index_history(calendar, drop=('2026-03-11',))
    with pytest.raises(ValueError, match=f'manquante.*{calendar}.*2026-03-11'):
        qualify_calibration_sessions(_session_sample(ticker, values), [ticker],
                                     date.fromisoformat(INDEX_END), venue_loader=lambda _: {})


def test_the_euro_stoxx_50_sessions_missing_at_yahoo_are_named():
    index = session_calendar('XSWX', 2026).sessions_in_range(INDEX_START, INDEX_END)
    values = pd.Series(5000.0, index=index)
    with pytest.raises(ValueError, match=f'manquante.*XEUR.*{ASCENSION}'):
        qualify_calibration_sessions(_session_sample(SX5E, values), [SX5E],
                                     date.fromisoformat(INDEX_END), venue_loader=lambda _: {})


# ── A bare ticker is not a listing suffix ──
# Measured on 23/11/2026: Yahoo declares T, L, DE, MC and AS on NYQ. The session
# qualification read them as the suffixes of Tokyo, London, Xetra, Madrid and
# Amsterdam, and refused AT&T for the Tokyo sessions it does not quote.

BARE_TICKERS = ['T', 'L', 'DE', 'MC', 'AS']


@pytest.mark.parametrize('ticker', BARE_TICKERS)
def test_a_bare_ticker_takes_its_sourced_venue(ticker):
    values = _index_history('XNYS')
    result = qualify_calibration_sessions(
        _session_sample(ticker, values), [ticker], date.fromisoformat(INDEX_END),
        venue_loader=lambda _: {'exchange': 'NYQ', 'timezone': 'America/New_York'})
    assert result['session_qualification']['calendars'] == {ticker: 'XNYS'}
    assert result['sources'][ticker]['calendar_reference_provider'] == 'YAHOO_FINANCE'


@pytest.mark.parametrize('ticker', BARE_TICKERS)
def test_a_bare_ticker_without_a_sourced_venue_is_still_refused(ticker):
    values = _index_history('XNYS')
    with pytest.raises(ValueError, match='place de cotation inconnue'):
        qualify_calibration_sessions(_session_sample(ticker, values), [ticker],
                                     date.fromisoformat(INDEX_END), venue_loader=lambda _: {})


def test_a_listing_suffix_is_still_read_without_asking_the_provider():
    def no_lookup(ticker):
        pytest.fail(f'{ticker} : place à lire dans le suffixe')
    result = qualify_calibration_sessions(
        _session_sample('GLE.PA', _index_history('XPAR')), ['GLE.PA'],
        date.fromisoformat(INDEX_END), venue_loader=no_lookup)
    assert result['session_qualification']['calendars'] == {'GLE.PA': 'XPAR'}
