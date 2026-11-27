"""Resolve the contractual coupon and survivor principal dates of a fixed CLN."""
from __future__ import annotations

from itertools import pairwise

from ..calendar_budget import check_schedule
from ..calendars import SETTLEMENT_CODES, add_business_days, adjust
from ..schedule import StubConvention, Tenor, generate_main_schedule
from .models import CLNTerms
from .native_schedule_models import ScheduleEvent, ScheduleLeg, SchedulePeriod
from .rates_schedule import _days_30e_360


def resolve_cln_schedule(terms: CLNTerms) -> tuple[ScheduleLeg, ...]:
    start, end = terms.effective_date, terms.maturity_date
    if start is None or end is None or start >= end:
        raise ValueError("La CLN requiert une date d’effet précédant sa maturité.")
    fixed = terms.fixed_leg
    if fixed.calendar.upper() not in SETTLEMENT_CODES:
        raise ValueError(f"Calendrier de règlement CLN inconnu « {fixed.calendar} ».")
    frequency = Tenor(fixed.frequency_months, "M")
    check_schedule(start, end, end, frequency)
    raw_dates = generate_main_schedule(start, end, end, frequency, StubConvention.SHORT_FIRST)
    adjusted = [adjust(day, fixed.calendar, fixed.business_day_convention) for day in raw_dates]
    periods = []
    for rank, (accrual_start, accrual_end) in enumerate(pairwise(adjusted), start=1):
        days = (
            (accrual_end - accrual_start).days if fixed.day_count == "ACT/360"
            else _days_30e_360(accrual_start, accrual_end)
        )
        if accrual_end <= accrual_start or days <= 0:
            raise ValueError(f"Période CLN {rank} : bornes de couru vides ou inversées.")
        periods.append(SchedulePeriod(
            period_id=f"cln-fixed-period-{rank:02d}",
            rank=rank,
            unadjusted_start=raw_dates[rank - 1],
            unadjusted_end=raw_dates[rank],
            accrual_start=accrual_start,
            accrual_end=accrual_end,
            day_count=fixed.day_count,
            day_count_days=days,
            payment_date=add_business_days(accrual_end, fixed.payment_lag_business_days, fixed.calendar),
            credit_observation_date=accrual_end,
            flow_id=f"cln-fixed-coupon-{rank:02d}",
        ))
    principal = ScheduleEvent(
        event_id="cln-principal-at-maturity", kind="principal",
        date=periods[-1].payment_date, flow_id="cln-principal",
    )
    return (
        ScheduleLeg(
            leg_id="cln-fixed", kind="fixed_coupon", periods=tuple(periods), calendar=fixed.calendar,
            business_day_convention=fixed.business_day_convention,
            payment_lag_business_days=fixed.payment_lag_business_days, roll_rule="maturity_day_short_first",
        ),
        ScheduleLeg(
            leg_id="cln-survivor-principal", kind="principal", events=(principal,), calendar=fixed.calendar,
            business_day_convention=fixed.business_day_convention,
            payment_lag_business_days=fixed.payment_lag_business_days, roll_rule="last_coupon_payment",
        ),
    )
