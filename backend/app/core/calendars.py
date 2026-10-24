"""Named observation calendars, payment centres and business-day conventions.

Observation venues and payment centres are separate contractual choices.
Multiple calendars require a product-specific all-open or any-open rule.
Historical currency-only configurations retain their original bank mapping.

The euro has no country calendar — EUR settlement follows TARGET, the payment
system, which is why it is mapped to the ECB financial calendar rather than to
any member state. Elsewhere the country's bank calendar applies, with the
subdivision that matters for settlement (Zurich for the CHF: 2 January and
1 August are not holidays everywhere in Switzerland).
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from functools import lru_cache
from dataclasses import dataclass

import holidays

# (kind, code, subdivision) — "financial" reaches a payment-system calendar,
# "country" a national bank calendar.
_SPECS: dict[str, tuple[str, str, str | None]] = {
    "EUR": ("financial", "ECB", None),      # TARGET
    "USD": ("country", "US", None),
    "GBP": ("country", "GB", "England"),
    "CHF": ("country", "CH", "ZH"),         # Zurich
    "JPY": ("country", "JP", None),
    "SGD": ("country", "SG", None),
}

SUPPORTED_CURRENCIES = tuple(sorted(_SPECS))

# Named observation venues and payment centres. Currency aliases retain the
# historical bank-calendar mapping for existing Economics configurations.
_NAMED = {
    'TARGET': ('financial', 'ECB', None),
    'NYSE': ('financial', 'NYSE', None),
    'NASDAQ': ('financial', 'XNAS', None),
    'XETR': ('financial', 'XETR', None),
    'JPX': ('financial', 'JPX', None),
    'HKEX': ('financial', 'HKEX', None),
    'SGX': ('financial', 'SGX', None),
    'SIX': ('financial', 'SIX', None),
}
CALENDAR_CODES = tuple(sorted({*_SPECS, *_NAMED}))
OBSERVATION_CODES = CALENDAR_CODES
SETTLEMENT_CODES = tuple(sorted({*_SPECS, 'TARGET'}))


@dataclass(frozen=True)
class CalendarSelection:
    codes: tuple[str, ...]
    join: str


CalendarInput = str | CalendarSelection


def validate_settlement_lag(value) -> int:
    """Contractual settlement lags are integers, never coerced or truncated."""
    if type(value) is not int or not 0 <= value <= 30:
        raise ValueError('Le délai de règlement doit être un entier entre 0 et 30 jours ouvrés.')
    return value


def calendar_selection(config: dict, purpose: str, currency=None):
    """Resolve an explicit policy, or retain the historical currency mapping.

    Multiple calendars require an explicit product-level combination choice.
    An empty explicit selection is an error, not a fallback to the currency.
    """
    field = f'{purpose}_calendars'
    if field not in config:
        if config.get(f'{purpose}_join'):
            raise ValueError(f'{field} : sélection de calendriers manquante.')
        return currency
    codes = config[field]
    allowed = SETTLEMENT_CODES if purpose == 'settlement' else OBSERVATION_CODES
    if not isinstance(codes, (list, tuple)) or not codes or any(
            not isinstance(code, str) or code not in allowed for code in codes):
        raise ValueError(f'{field} : choisir au moins un calendrier reconnu ({", ".join(allowed)}).')
    codes = tuple(dict.fromkeys(codes))
    join = config.get(f'{purpose}_join')
    if join is None and len(codes) == 1:
        join = 'all_open'
    if join not in ('all_open', 'any_open'):
        raise ValueError(f'{field} : choisir explicitement « toutes ouvertes » ou « au moins une ouverte ».')
    return CalendarSelection(codes, join)


def calendar_context(config, currency=None):
    config = config if isinstance(config, dict) else {}
    return (calendar_selection(config, 'observation', currency),
            calendar_selection(config, 'settlement', currency))


class BusinessDayConvention(str, Enum):
    """How a date that is not a business day is moved onto one."""

    FOLLOWING = "following"
    MODIFIED_FOLLOWING = "modified_following"
    PRECEDING = "preceding"
    MODIFIED_PRECEDING = "modified_preceding"
    NONE = "none"


DEFAULT_CONVENTION = BusinessDayConvention.MODIFIED_FOLLOWING


class UnsupportedCurrency(ValueError):
    """Raised rather than silently falling back to a weekday-only calendar.

    A wrong calendar shifts settlement by a day or two without any visible
    symptom — it must fail loudly, not be guessed."""


@lru_cache(maxsize=None)
def _calendar(currency: str):
    spec = {**_SPECS, **_NAMED}.get((currency or "").upper())
    if spec is None:
        raise UnsupportedCurrency(
            f"Devise « {currency} » sans calendrier de jours ouvrés. "
            f"Devises couvertes : {', '.join(SUPPORTED_CURRENCIES)}.")
    kind, code, subdiv = spec
    # python-holidays fills years lazily on lookup, so one instance serves
    # every year a schedule may reach — no need to bound it up front.
    if kind == "financial":
        return holidays.financial_holidays(code)
    return holidays.country_holidays(code, subdiv=subdiv)


def is_business_day(day: date, currency: CalendarInput) -> bool:
    """Whether a named calendar or explicit calendar combination is open."""
    if isinstance(currency, CalendarSelection):
        opened = [is_business_day(day, code) for code in currency.codes]
        return all(opened) if currency.join == 'all_open' else any(opened)
    if day.weekday() >= 5:
        return False
    return day not in _calendar(currency)


def adjust(day: date, currency: CalendarInput,
           convention: BusinessDayConvention = DEFAULT_CONVENTION) -> date:
    """Move `day` onto a business day according to `convention`.

    Modified Following is the market default on structured notes: roll forward,
    unless that crosses into the next month — a quarter-end observation must
    not drift into the next quarter, so it rolls back instead."""
    if convention == BusinessDayConvention.NONE or is_business_day(day, currency):
        return day

    if convention in (BusinessDayConvention.FOLLOWING,
                      BusinessDayConvention.MODIFIED_FOLLOWING):
        rolled = _roll(day, +1, currency)
        if convention == BusinessDayConvention.MODIFIED_FOLLOWING and rolled.month != day.month:
            return _roll(day, -1, currency)
        return rolled

    rolled = _roll(day, -1, currency)
    if convention == BusinessDayConvention.MODIFIED_PRECEDING and rolled.month != day.month:
        return _roll(day, +1, currency)
    return rolled


def add_business_days(day: date, n: int, currency: CalendarInput) -> date:
    """Settlement lag: `n` business days after `day` (T+n).

    n = 0 means "same day if it is a business day, else the next one" — the
    lag never lands cash on a closed day."""
    if n == 0:
        return adjust(day, currency, BusinessDayConvention.FOLLOWING)
    step = 1 if n > 0 else -1
    current = day
    for _ in range(abs(n)):
        current = _roll(current, step, currency)
    return current


def business_days_between(start: date, end: date, currency: CalendarInput) -> int:
    """Business days strictly after `start` up to and including `end`.

    Negative when `end` precedes `start`, so it inverts add_business_days."""
    if end == start:
        return 0
    step = 1 if end > start else -1
    count = 0
    current = start
    while current != end:
        current += timedelta(days=step)
        if is_business_day(current, currency):
            count += step
    return count


def _roll(day: date, step: int, currency: CalendarInput) -> date:
    current = day + timedelta(days=step)
    while not is_business_day(current, currency):
        current += timedelta(days=step)
    return current
