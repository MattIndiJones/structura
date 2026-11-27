"""Contractual dates for the EUR CDS converter benchmark."""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from ..calendar_budget import check_schedule
from ..calendars import BusinessDayConvention
from ..schedule import StubConvention, Tenor, generate_main_schedule
from .models import CDSTerms
from .native_schedule_models import ScheduleEvent, ScheduleLeg, SchedulePeriod


_ONE_DAY = timedelta(days=1)
_PREMIUM_FREQUENCY_MONTHS = 3
_ROLL_DAY = 20


def _following_weekday(day: date) -> date:
    # The converter uses weekends only, independent of the TARGET calendar.
    while day.weekday() >= 5:
        day += _ONE_DAY
    return day


def _add_weekdays(day: date, count: int) -> date:
    for _ in range(count):
        day = _following_weekday(day + _ONE_DAY)
    return day


def _first_unadjusted_coupon_date(step_in: date) -> date:
    month = ((step_in.month - 1) // _PREMIUM_FREQUENCY_MONTHS + 1) * _PREMIUM_FREQUENCY_MONTHS
    roll = date(step_in.year, month, _ROLL_DAY)
    if _following_weekday(roll) > step_in:
        roll -= relativedelta(months=_PREMIUM_FREQUENCY_MONTHS)
    return roll


def _premium_periods(step_in: date, maturity: date) -> tuple[SchedulePeriod, ...]:
    first_roll = _first_unadjusted_coupon_date(step_in)
    frequency = Tenor(_PREMIUM_FREQUENCY_MONTHS, "M")
    check_schedule(first_roll, maturity, first_roll, frequency)
    rolls = generate_main_schedule(first_roll, maturity, first_roll, frequency, StubConvention.SHORT_LAST)
    periods = []
    for rank, (start, end) in enumerate(zip(rolls, rolls[1:]), start=1):
        accrual_start = _following_weekday(start)
        payment_date = _following_weekday(end)
        # Final accrual includes unadjusted maturity. Payment is adjusted independently.
        accrual_end = end + _ONE_DAY if end == maturity else payment_date
        accrual_days = (accrual_end - accrual_start).days
        if accrual_days <= 0:
            raise ValueError("La période de prime CDS doit contenir au moins un jour de couru.")
        periods.append(SchedulePeriod(
            period_id=f"cds-premium-period-{rank}",
            rank=rank,
            unadjusted_start=start,
            unadjusted_end=end,
            accrual_start=accrual_start,
            accrual_end=accrual_end,
            day_count="ACT/360",
            day_count_days=accrual_days,
            payment_date=payment_date,
            flow_id=f"cds-premium-cash-{rank}",
            credit_observation_date=accrual_end - _ONE_DAY,
        ))
    return tuple(periods)


def cds_default_accrued_days(period: SchedulePeriod, default_date: date) -> int:
    """Count ACT/360 days up to, and excluding, a supplied default date."""
    if period.credit_observation_date is None or not period.accrual_start <= default_date < period.accrual_end:
        raise ValueError("La date de défaut doit appartenir à la période de prime CDS.")
    return (default_date - period.accrual_start).days


def resolve_cds_schedule(terms: CDSTerms) -> tuple[ScheduleLeg, ...]:
    """Resolve the premium schedule, protection boundaries and upfront cash date."""
    trade_date, effective_date, maturity = terms.trade_date, terms.effective_date, terms.maturity_date
    premium = terms.premium_leg
    if trade_date is None or effective_date is None or maturity is None:
        raise ValueError("CDS incomplet : les dates de transaction, d’effet et de maturité sont requises.")
    if premium.calendar != "weekdays_only":
        raise ValueError("Le profil historique du convertisseur CDS requiert le calendrier weekdays_only.")
    if (
        premium.business_day_convention != BusinessDayConvention.FOLLOWING
        or premium.frequency_months != _PREMIUM_FREQUENCY_MONTHS
        or premium.day_count != "ACT/360"
        or premium.payment_lag_business_days != 0
    ):
        raise ValueError("Le profil CDS requiert des primes trimestrielles Following, ACT/360, sans délai de paiement.")
    if (terms.step_in_lag_calendar_days, terms.cash_settlement_lag_business_days) != (1, 3):
        raise ValueError("Le profil CDS requiert un step-in à T+1 calendaire et un règlement à T+3 ouvrés.")
    if not terms.accrued_on_default:
        raise ValueError("Le profil CDS requiert le couru de prime au défaut.")
    if trade_date.weekday() >= 5:
        raise ValueError("La date de transaction doit être ouvrée selon le profil CDS.")
    if maturity.day != _ROLL_DAY or maturity.month % _PREMIUM_FREQUENCY_MONTHS:
        raise ValueError("La maturité CDS doit tomber le 20 de mars, juin, septembre ou décembre.")
    if maturity <= trade_date:
        raise ValueError("La maturité CDS doit suivre la date de transaction.")

    step_in = trade_date + _ONE_DAY
    if effective_date != step_in or maturity <= step_in:
        raise ValueError("La prise d’effet du convertisseur CDS doit coïncider avec le step-in et précéder la maturité.")
    periods = _premium_periods(step_in, maturity)
    return (
        ScheduleLeg(
            leg_id="cds-premium",
            kind="premium",
            periods=periods,
            calendar=premium.calendar,
            business_day_convention=premium.business_day_convention,
            payment_lag_business_days=premium.payment_lag_business_days,
            roll_rule="quarterly_20th",
        ),
        ScheduleLeg(
            leg_id="cds-protection",
            kind="protection",
            step_in_lag_calendar_days=terms.step_in_lag_calendar_days,
            events=(
                ScheduleEvent(event_id="cds-step-in", kind="step_in", date=step_in),
                ScheduleEvent(event_id="cds-protection-end", kind="protection_end", date=maturity),
            ),
        ),
        ScheduleLeg(
            leg_id="cds-initial-settlement",
            kind="initial_settlement",
            calendar=premium.calendar,
            business_day_convention=premium.business_day_convention,
            payment_lag_business_days=terms.cash_settlement_lag_business_days,
            events=(
                ScheduleEvent(
                    event_id="cds-initial-settlement",
                    kind="initial_settlement",
                    date=_add_weekdays(trade_date, terms.cash_settlement_lag_business_days),
                    flow_id="cds-initial-settlement-cash",
                    accrued_days=(step_in - periods[0].accrual_start).days,
                ),
            ),
        ),
    )
