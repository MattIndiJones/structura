"""Qualify realized-calibration samples against known exchange sessions.

No Following or price filling is applied to calibration returns. The optional
consumer keeps genuine simultaneous closes and requires every expected quote.
"""
from datetime import date

from ..core.fixing_finality import VENUES, session_calendar

SUFFIX_CALENDARS = {'PA': 'XPAR', 'MI': 'XMIL', 'AS': 'XAMS', 'BR': 'XBRU', 'DE': 'XETR',
                    'L': 'XLON', 'SW': 'XSWX', 'T': 'XTKS', 'HK': 'XHKG', 'SI': 'XSES',
                    'MC': 'XMAD', 'TO': 'XTSE', 'AX': 'XASX'}


def qualify_calibration_sessions(history, tickers, asof):
    """Require complete known sessions from each security's first actual quote."""
    expected_by_ticker, calendars, omitted = {}, {}, {}
    for ticker in tickers:
        source = history.get('sources', {}).get(ticker, {})
        name = VENUES.get(source.get('exchange')) or SUFFIX_CALENDARS.get(ticker.rsplit('.', 1)[-1])
        if not name:
            raise ValueError(f'{ticker} : place de cotation inconnue ; précisez ses hypothèses dans le Pricer.')
        actual = set(history.get('observation_dates', {}).get(ticker, history['dates']))
        first = date.fromisoformat(min(actual))
        expected = set()
        for year in range(first.year, asof.year+1):
            lower, upper = max(first, date(year, 1, 1)), min(asof, date(year, 12, 31))
            calendar = session_calendar(name, year)
            expected.update(day.date().isoformat() for day in calendar.sessions_in_range(lower.isoformat(), upper.isoformat()))
        missing = sorted(expected-actual)
        if missing:
            raise ValueError(f'{ticker} : {len(missing)} clôture(s) manquante(s) sur une séance ouverte '
                             f'({name}), première le {missing[0]}. Aucun cours remplacé pour estimer la volatilité.')
        calendars[ticker], expected_by_ticker[ticker] = name, expected
        omitted[ticker] = len(actual-expected)
    common = set.intersection(*(expected_by_ticker[ticker] for ticker in tickers))
    indices = [index for index, day in enumerate(history['dates']) if day in common]
    dates = [history['dates'][i] for i in indices]
    return {**history, 'dates': dates,
        'prices': {tk: [history['prices'][tk][i] for i in indices] for tk in tickers},
        'effective_dates': {tk: max(set(history.get('observation_dates', {}).get(tk, history['dates'])) & expected_by_ticker[tk], default=None) for tk in tickers},
        'start_effective': dates[0] if dates else None, 'end_effective': dates[-1] if dates else None,
        'asof_effective': dates[-1] if dates else None,
        'session_qualification': {'method': 'COMPLETE_EXCHANGE_SESSIONS', 'calendars': calendars,
            'excluded_non_session_bars': omitted, 'price_substitutions': 0},
        'warnings': [*history.get('warnings', []), {'code': 'EXCHANGE_SESSION_SAMPLE',
            'message': 'Volatilité réalisée sur clôtures communes réelles ; fermetures de bourse exclues, aucun cours remplacé.'}]}
