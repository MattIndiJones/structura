"""Explicit API preview budgets, checked before calendar construction."""
from datetime import date
from math import ceil

MAX_SPAN_DAYS = 50 * 366
MAX_OBSERVATIONS = 500
MAX_TOTAL_POINTS = 5000


def check_dates(*dates):
    if any(d.year < 1900 or d.year > 2200 for d in dates):
        raise ValueError("Les dates de prévisualisation doivent être comprises entre 1900 et 2200.")
    if (max(dates) - min(dates)).days > MAX_SPAN_DAYS:
        raise ValueError("La prévisualisation est limitée à 50 ans, ancrage compris.")


def tenor_days(tenor, *, upper=False):
    days = tenor.value * {"D": 1, "W": 7, "M": 31 if upper else 28, "Y": 366 if upper else 365}[tenor.unit]
    if days <= 0 or days > MAX_SPAN_DAYS:
        raise ValueError("Fréquence ou fenêtre hors limites de prévisualisation (50 ans).")
    return days


def check_schedule(start, end, roll, frequency, sub_frequency=None, *, period=False):
    check_dates(start, end, roll)
    span = abs((end - start).days)
    main_step = tenor_days(frequency)
    main_count = ceil(span / main_step) + 2
    # Include the roll walk: a nearby requested interval may hide an old anchor.
    roll_count = ceil(max(abs((roll - start).days), abs((roll - end).days)) / main_step) + 2
    total = main_count
    if sub_frequency:
        sub_step = tenor_days(sub_frequency)
        total = main_count * (ceil(tenor_days(frequency, upper=True) / sub_step) + 2) if period else ceil(span / sub_step) + 2 * main_count
    if main_count > MAX_OBSERVATIONS or max(total, roll_count) > MAX_TOTAL_POINTS:
        raise ValueError("Prévisualisation limitée à 500 constatations et 5 000 points calculés ; réduisez la période ou la fréquence.")


def check_window(anchor: date, length, frequency):
    check_dates(anchor)
    span = tenor_days(length, upper=True)
    if anchor.toordinal() - span < date(1900, 1, 1).toordinal() or anchor.toordinal() + span > date(2200, 12, 31).toordinal():
        raise ValueError("La fenêtre dépasse les limites de dates de prévisualisation.")
    if ceil(span / tenor_days(frequency)) + 2 > MAX_TOTAL_POINTS:
        raise ValueError("Fenêtre limitée à 5 000 points calculés.")
