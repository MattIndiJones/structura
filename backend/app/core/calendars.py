"""Business-day calendars and date-roll conventions, by settlement currency.

Which calendar applies is decided by the currency the cash moves in, not by
where the underlying trades: an Athena on the S&P 500 settled in EUR pays its
coupons on TARGET business days, not on NYSE ones. A product whose underlying
market is closed but whose settlement currency is open still pays.

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
    spec = _SPECS.get((currency or "").upper())
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


def is_business_day(day: date, currency: str) -> bool:
    """Weekend or public holiday in the settlement currency's calendar."""
    if day.weekday() >= 5:
        return False
    return day not in _calendar(currency)


def adjust(day: date, currency: str,
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


def add_business_days(day: date, n: int, currency: str) -> date:
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


def business_days_between(start: date, end: date, currency: str) -> int:
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


def _roll(day: date, step: int, currency: str) -> date:
    current = day + timedelta(days=step)
    while not is_business_day(current, currency):
        current += timedelta(days=step)
    return current
