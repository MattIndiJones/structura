"""Contractual coupon and principal dates for the native EUR rates pilots."""

from datetime import date
from itertools import pairwise
from typing import Literal

from dateutil.relativedelta import relativedelta

from ..calendar_budget import check_schedule
from ..calendars import OBSERVATION_CODES, SETTLEMENT_CODES, add_business_days, adjust
from ..schedule import StubConvention, Tenor, generate_main_schedule
from .models import EuriborLegTerms, FixedLegTerms, FRNTerms, IRSTerms
from .native_schedule_models import ScheduleEvent, ScheduleLeg, SchedulePeriod


def resolve_rates_schedule(terms: FRNTerms | IRSTerms) -> tuple[ScheduleLeg, ...]:
    """Resolve the dates independently of coupon amounts or market state."""
    start, end = terms.effective_date, terms.maturity_date
    if start is None or end is None:
        raise ValueError("Les dates d’effet et de maturité sont requises pour l’échéancier.")
    if start >= end:
        raise ValueError("La maturité doit suivre la date d’effet.")

    floating = _coupon_leg(start, end, terms.floating_leg, terms.instrument_type)
    if isinstance(terms, IRSTerms):
        return floating, _coupon_leg(start, end, terms.fixed_leg, terms.instrument_type)

    # The bullet principal uses the same payment rule as the final coupon.
    principal = ScheduleEvent(
        event_id="principal-01", kind="principal", date=floating.periods[-1].payment_date,
        flow_id="frn-principal",
    )
    return floating, ScheduleLeg(
        leg_id="principal", kind="principal", events=(principal,),
        calendar=floating.calendar, business_day_convention=floating.business_day_convention,
        payment_lag_business_days=floating.payment_lag_business_days, roll_rule="last_coupon_payment",
    )


def _coupon_leg(
    effective: date,
    maturity: date,
    terms: EuriborLegTerms | FixedLegTerms,
    instrument: Literal["FRN", "IRS"],
) -> ScheduleLeg:
    floating = terms if isinstance(terms, EuriborLegTerms) else None
    leg_id = "floating" if floating is not None else "fixed"
    if terms.calendar.upper() not in SETTLEMENT_CODES:
        raise ValueError(f"Jambe {leg_id} : calendrier de règlement inconnu « {terms.calendar} ».")
    if floating is not None:
        if floating.fixing_calendar.upper() not in OBSERVATION_CODES:
            raise ValueError(f"Jambe {leg_id} : calendrier de fixing inconnu « {floating.fixing_calendar} ».")
        if floating.frequency_months != 3:
            raise ValueError(f"Jambe {leg_id} : la projection Euribor 3M requiert une fréquence trimestrielle.")

    # The pilot rolls from the original effective day of month and accepts a
    # regular maturity only. The shared generator cannot add a stub here.
    months = (maturity.year - effective.year) * 12 + maturity.month - effective.month
    if months % terms.frequency_months or effective + relativedelta(months=months) != maturity:
        raise ValueError(f"Jambe {leg_id} : maturité hors de la grille régulière, stub non pris en charge.")
    frequency = Tenor(terms.frequency_months, "M")
    check_schedule(effective, maturity, effective, frequency)
    nominal = generate_main_schedule(effective, maturity, effective, frequency, StubConvention.SHORT_LAST)
    adjusted = [adjust(day, terms.calendar, terms.business_day_convention) for day in nominal]

    flow_role = "frn-coupon" if instrument == "FRN" else f"irs-{leg_id}"
    period_role = "float" if floating is not None else "fixed"
    periods = []
    for rank, (accrual_start, accrual_end) in enumerate(pairwise(adjusted), start=1):
        period_id = f"{period_role}-{rank:02d}"
        if accrual_start >= accrual_end:
            raise ValueError(f"Période {period_id} : bornes de couru ajustées vides ou inversées.")
        days = (
            (accrual_end - accrual_start).days
            if floating is not None else _days_30e_360(accrual_start, accrual_end)
        )
        if days <= 0:
            raise ValueError(f"Période {period_id} : numérateur de couru non positif.")

        fixing = None
        if floating is not None:
            fixing = add_business_days(accrual_start, -floating.fixing_lag_business_days, floating.fixing_calendar)
            if fixing > accrual_start:
                raise ValueError(f"Période {period_id} : fixing à J+0 impossible sur un jour fermé.")

        periods.append(SchedulePeriod(
            period_id=period_id, rank=rank, flow_id=f"{flow_role}-{rank:02d}",
            unadjusted_start=nominal[rank - 1], unadjusted_end=nominal[rank],
            accrual_start=accrual_start, accrual_end=accrual_end,
            day_count=terms.day_count, day_count_days=days,
            fixing_date=fixing,
            payment_date=add_business_days(accrual_end, terms.payment_lag_business_days, terms.calendar),
            projection_start=accrual_start if floating is not None else None,
            projection_end=accrual_end if floating is not None else None,
        ))

    return ScheduleLeg(
        leg_id=leg_id, kind="floating_coupon" if floating is not None else "fixed_coupon",
        periods=tuple(periods),
        calendar=terms.calendar, business_day_convention=terms.business_day_convention,
        fixing_calendar=floating.fixing_calendar if floating is not None else None,
        fixing_lag_business_days=floating.fixing_lag_business_days if floating is not None else None,
        payment_lag_business_days=terms.payment_lag_business_days, roll_rule="effective_day_of_month",
    )


def _days_30e_360(start: date, end: date) -> int:
    """Eurobond day count, with a day-31 cap and no special February rule."""
    return (
        360 * (end.year - start.year)
        + 30 * (end.month - start.month)
        + min(end.day, 30) - min(start.day, 30)
    )
