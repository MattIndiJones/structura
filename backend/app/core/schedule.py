"""
Schedule generation shared by preview, PayScript and contractual Products.

Three levels, mirroring the spec:
  CONSTAT      — a single date.
  CONSTAT()    — a schedule: start date, end date, roll date (anchor), roll
                 frequency (a tenor, e.g. "3M"), and a stub convention.
  CONSTAT()()  — CONSTAT() plus a sub-frequency that subdivides every interval
                 of the main schedule (no stub logic of its own — it just fills
                 each already-resolved interval evenly).

Stub convention (ISDA-style):
  *_LAST  — the regular grid is generated FORWARD, anchored on roll_date, and
            the irregular boundary period (if any) falls at the END, between
            the last regular date and end_date.
  *_FIRST — the regular grid is generated BACKWARD, anchored on roll_date, and
            the irregular boundary period falls at the START, between
            start_date and the first regular date.
  SHORT_* — that boundary period is left as-is (shorter than a regular period).
  LONG_*  — that boundary period is merged into its regular neighbor (dropping
            the adjoining grid point) whenever the boundary is irregular.
start_date and end_date are always part of the resulting schedule.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from dateutil.relativedelta import relativedelta

from .calendars import BusinessDayConvention, add_business_days, adjust, validate_settlement_lag

DAYS_PER_YEAR = 365.25   # simple ACT/365.25 day count for the year-fraction preview


class StubConvention(str, Enum):
    SHORT_FIRST = "short_first"
    SHORT_LAST = "short_last"
    LONG_FIRST = "long_first"
    LONG_LAST = "long_last"


@dataclass
class Tenor:
    """A step size like "3M", "1W", "1Y", "1D" — value + unit."""
    value: int
    unit: str   # 'D' | 'W' | 'M' | 'Y'

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError("Le tenor doit être strictement positif.")
        if self.unit not in ("D", "W", "M", "Y"):
            raise ValueError(f"Unité de tenor inconnue: {self.unit!r} (attendu D/W/M/Y).")


_TENOR_RE = re.compile(r"^(\d+)\s*([DWMYdwmy])$")


def parse_tenor(s: str) -> Tenor:
    """Parse a tenor string like "3M", "1W", "1Y", "1D"."""
    m = _TENOR_RE.match(s.strip())
    if not m:
        raise ValueError(f"Tenor invalide: {s!r} (format attendu: ex. '3M', '1W', '1Y', '1D').")
    return Tenor(value=int(m.group(1)), unit=m.group(2).upper())


def _step(d: date, tenor: Tenor, n: int = 1) -> date:
    """Move d forward (n>0) or backward (n<0) by n steps of tenor."""
    amount = tenor.value * n
    if tenor.unit == "D":
        return d + timedelta(days=amount)
    if tenor.unit == "W":
        return d + timedelta(weeks=amount)
    if tenor.unit == "M":
        return d + relativedelta(months=amount)
    return d + relativedelta(years=amount)   # 'Y'


def generate_main_schedule(start: date, end: date, roll_date: date,
                            frequency: Tenor, stub: StubConvention) -> list[date]:
    """Generate the CONSTAT() date list. start and end are always included."""
    if end <= start:
        raise ValueError("end_date doit être strictement après start_date.")

    # Every point is computed from the ORIGINAL anchor. Iteratively stepping
    # from 28 February would permanently lose a 31st-of-month roll.
    def index_near(day):
        if frequency.unit in ('M', 'Y'):
            months = (day.year-roll_date.year)*12 + day.month-roll_date.month
            return months // (frequency.value * (12 if frequency.unit == 'Y' else 1))
        return (day-roll_date).days // (frequency.value * (7 if frequency.unit == 'W' else 1))

    forward = stub in (StubConvention.SHORT_LAST, StubConvention.LONG_LAST)
    n = index_near(start if forward else end)
    if forward:
        while _step(roll_date, frequency, n) <= start:
            n += 1
        dates = [start]
        d = _step(roll_date, frequency, n)
        while d < end:
            dates.append(d)
            n += 1
            d = _step(roll_date, frequency, n)
        irregular = d != end
        dates.append(end)
        if stub == StubConvention.LONG_LAST and irregular and len(dates) >= 3:
            dates.pop(-2)
    else:
        while _step(roll_date, frequency, n) >= end:
            n -= 1
        dates = [end]
        d = _step(roll_date, frequency, n)
        while d > start:
            dates.append(d)
            n -= 1
            d = _step(roll_date, frequency, n)
        irregular = d != start
        dates.append(start)
        dates.reverse()
        if stub == StubConvention.LONG_FIRST and irregular and len(dates) >= 3:
            dates.pop(1)
    return dates


def _fill_interval(lo: date, hi: date, sub_frequency: Tenor) -> list[date]:
    """Sub-divide (lo, hi) evenly by sub_frequency, stepping forward from lo.
    No stub handling at this level — the last sub-step before hi simply closes
    out at hi, by construction (see module docstring)."""
    out = [lo]
    n = 1
    d = _step(lo, sub_frequency, n)
    while d < hi:
        out.append(d)
        n += 1
        d = _step(lo, sub_frequency, n)
    return out


def generate_schedule(start: date, end: date, roll_date: date, frequency: Tenor,
                       stub: StubConvention, sub_frequency: Tenor | None = None,
                       currency: str | None = None,
                       convention: BusinessDayConvention = BusinessDayConvention.NONE,
                       settlement_lag: int = 0, *,
                       observation_calendar=None, settlement_calendar=None) -> dict:
    """Build a full CONSTAT() or CONSTAT()() schedule.

    The grid is rolled on unadjusted dates first, then each resulting date is
    moved onto a business day — the market order, and the only one that keeps
    a quarterly schedule quarterly: adjusting before rolling would compound
    each shift into the next period.

    Explicit observation and settlement calendars override the historical
    currency mapping independently. Missing convention means no observation
    adjustment. A settlement lag without a payment calendar is refused.

    Returns a dict with:
      main_dates — the CONSTAT() roll schedule (always includes start/end).
      dates      — the fully expanded schedule (== main_dates when no
                   sub_frequency; otherwise every main interval subdivided).
      payment_dates — when each observation's cash actually moves: the date
                   itself at T+0, later once a settlement lag applies. Same
                   length as `dates`, and equal to it when no currency is given.
      year_fractions — each date's ACT/365.25 offset from start, for preview
                   purposes (this is what a future phase would feed to AT).
    """
    settlement_lag = validate_settlement_lag(settlement_lag)
    observed_calendar = observation_calendar or currency
    paid_calendar = settlement_calendar or currency
    if settlement_lag and not paid_calendar:
        raise ValueError(
            "Un décalage de règlement suppose un calendrier : précisez la devise "
            "de règlement du calendrier CONSTAT.")

    main_dates = generate_main_schedule(start, end, roll_date, frequency, stub)

    if sub_frequency is None:
        dates = main_dates
    else:
        dates = []
        for lo, hi in zip(main_dates[:-1], main_dates[1:]):
            dates.extend(_fill_interval(lo, hi, sub_frequency))
        dates.append(main_dates[-1])

    raw_dates = list(dates)
    if observed_calendar:
        main_dates = _dedupe([adjust(d, observed_calendar, convention) for d in main_dates])
        # Les deux listes restent appariées : on déduplique sur la date ajustée
        # en gardant la première date brute qui y mène, pour pouvoir dire d'où
        # chaque constatation vient.
        pairs = [(adjust(d, observed_calendar, convention), d) for d in dates]
        seen: set[date] = set()
        kept = []
        for adjusted, original in pairs:
            if adjusted not in seen:
                seen.add(adjusted)
                kept.append((adjusted, original))
        dates = [a for a, _ in kept]
        raw_dates = [o for _, o in kept]
    payment_dates = ([add_business_days(d, settlement_lag, paid_calendar) for d in dates]
                     if paid_calendar else list(dates))

    year_fractions = [round((d - start).days / DAYS_PER_YEAR, 6) for d in dates]

    return {
        "main_dates": main_dates,
        "dates": dates,
        # La grille avant ajustement, appariée à `dates`. Égale à elle quand
        # aucune convention ne s'applique — ce qui rend l'écart lisible sans
        # avoir à le recalculer.
        "raw_dates": raw_dates,
        "payment_dates": payment_dates,
        "year_fractions": year_fractions,
    }


def generate_observation_schedule(first: date, end: date, roll_date: date,
                                  frequency: Tenor, stub: StubConvention,
                                  sub_frequency: Tenor | None = None, *,
                                  currency: str | None = None,
                                  convention=BusinessDayConvention.NONE,
                                  settlement_lag: int = 0,
                                  observation_calendar=None, settlement_calendar=None) -> dict:
    """An inclusive observation calendar, including the one-observation case."""
    if end != first:
        return generate_schedule(first, end, roll_date, frequency, stub, sub_frequency,
                                 currency=currency, convention=convention,
                                 settlement_lag=settlement_lag, observation_calendar=observation_calendar,
                                 settlement_calendar=settlement_calendar)
    settlement_lag = validate_settlement_lag(settlement_lag)
    observation_calendar = observation_calendar or currency
    settlement_calendar = settlement_calendar or currency
    if settlement_lag and not settlement_calendar:
        raise ValueError('Un décalage de règlement exige une devise.')
    observed = adjust(first, observation_calendar, convention) if observation_calendar else first
    paid = add_business_days(observed, settlement_lag, settlement_calendar) if settlement_calendar else observed
    return dict(main_dates=[observed], dates=[observed], raw_dates=[first],
                payment_dates=[paid], year_fractions=[(observed-first).days / DAYS_PER_YEAR])


def period_windows(start: date, end: date, roll_date: date, frequency: Tenor,
                    stub: StubConvention, sample: Tenor, *,
                    currency: str | None = None,
                    convention: BusinessDayConvention = BusinessDayConvention.NONE,
                    first_observation_date: date | None = None,
                    ) -> tuple[list[date], list[list[date]]]:
    """Constatations d'un calendrier, et les relevés que chacune moyenne.

    Une fenêtre de PÉRIODE n'a pas de longueur : elle court d'une constatation
    à la suivante. On ne peut donc pas la construire en remontant pas à pas
    depuis la date de constatation — celle-ci est déjà roulée sur un jour
    ouvré, et remonter de 3M depuis un lundi qui était un dimanche décale
    toute la fenêtre, définitivement. On la bâtit sur la grille du calendrier
    lui-même : `generate_schedule` roule d'abord sur les dates brutes puis
    ajuste, ce qui est l'ordre du marché et le seul qui garde un trimestriel
    trimestriel.

    C'est exactement la grille qu'un `CONSTAT()()` produirait avec `sample`
    comme sous-fréquence — la même, à ceci près que ces dates ne sont pas des
    observations mais les relevés d'une constatation.

    Retourne (constatations, fenêtres) : une fenêtre par constatation, chacune
    ouverte à gauche et fermée à droite, si bien qu'une date de roll partagée
    par deux périodes n'est comptée qu'une fois.
    """
    if first_observation_date is not None:
        if start >= first_observation_date:
            raise ValueError('Le début de période doit précéder la première observation.')
        obs = generate_observation_schedule(first_observation_date, end, roll_date,
            frequency, stub, currency=currency, convention=convention)['dates']
        boundaries = [start, *obs]
        windows = [generate_schedule(lo, hi, hi, sample, StubConvention.SHORT_FIRST,
                     currency=currency, convention=convention)['dates'][1:] or [hi]
                   for lo, hi in zip(boundaries[:-1], boundaries[1:])]
        return obs, windows
    full = generate_schedule(start, end, roll_date, frequency, stub,
                             sub_frequency=sample, currency=currency,
                             convention=convention)
    mains = full["main_dates"]
    alls = full["dates"]
    obs = list(mains[1:])            # le start ouvre la 1re période, il n'est pas constaté
    windows = []
    for lo, hi in zip(mains[:-1], mains[1:]):
        windows.append([d for d in alls if lo < d <= hi] or [hi])
    return obs, windows


def observation_window(anchor: date, length: Tenor, frequency: Tenor, *,
                        forward: bool = False, currency: str | None = None,
                        convention: BusinessDayConvention = BusinessDayConvention.NONE,
                        ) -> list[date]:
    """The dates a single constatation reduces over — an averaging-in or
    averaging-out window, sorted ascending, `anchor` always included.

    `forward=False` (the usual case) walks BACKWARD from the observation date:
    the window ARRIVES at its date. `forward=True` is the initial fixing
    window, which DEPARTS from the strike date and walks forward. See
    CONSTATATIONS_PERIODE_DESIGN.md — one looks ahead at the start, back at
    the finish.

    Length semantics differ by unit, deliberately, because term sheets do:
      'D'  — a COUNT of observations, anchor included. "30D" at a 1D frequency
             is 30 fixings, not 31, and they are BUSINESS days whenever a
             currency is supplied (a calendar-day reading would silently drop
             weekends and return ~21).
      W/M/Y — a calendar span: the window is the interval [anchor - length,
             anchor], both bounds included.
    Sampling always starts AT the anchor and steps away from it, so the
    observation date itself is a fixing — never an off-by-one that quietly
    shifts the whole window by one period.

    A window whose extent is a PERIOD rather than a duration is built by
    `period_windows` instead — it must ride the calendar's own grid, not step
    back from an already-adjusted date.
    """
    if length.unit == "D":
        span = length.value - 1          # anchor already counts as one point
        limit = anchor if span == 0 else (add_business_days(anchor, span if forward else -span, currency)
                 if currency else
                 anchor + timedelta(days=span if forward else -span))
    else:
        limit = _step(anchor, length, 1 if forward else -1)

    out: list[date] = []
    k = 0
    while True:
        if k == 0:
            # A zero business-day shift rolls a closed day forward. Sampling
            # must retain its anchor until the explicit convention is applied.
            d = anchor
        elif frequency.unit == "D" and currency:
            step = frequency.value * k
            d = add_business_days(anchor, step if forward else -step, currency)
        else:
            d = _step(anchor, frequency, k if forward else -k)
        if (d > limit) if forward else (d < limit):
            break
        out.append(d)
        k += 1
        if k > 10_000:                   # a mis-typed length must not hang the parse
            raise ValueError(
                f"Fenêtre de constatation trop longue : plus de 10 000 points à la "
                f"fréquence {frequency.value}{frequency.unit}. Vérifiez la longueur "
                f"de fenêtre, ou la fréquence de relevé si la fenêtre est une période.")
    if not out:
        out = [anchor]
    if currency:
        out = [adjust(d, currency, convention) for d in out]
    return _dedupe(sorted(out))


def _dedupe(dates: list[date]) -> list[date]:
    """Two calendar dates can adjust onto the same business day — a daily
    schedule spanning a weekend lands Saturday, Sunday and Monday all on the
    Monday. Observing one fixing three times would triple-count it, so the
    duplicates collapse: the schedule keeps one observation per business day."""
    seen: set[date] = set()
    out: list[date] = []
    for d in dates:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out
