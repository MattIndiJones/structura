"""Explicit civil contract dates for exotic EUR rates on the ACT/365F model axis."""

from datetime import date, timedelta
from math import isfinite
from typing import Annotated

from pydantic import Field, model_validator

from ..calendar_budget import check_dates
from .models import FrozenModel


class RatesAccrualPeriod(FrozenModel):
    flow_id: Annotated[str, Field(min_length=1)]
    start_date: date
    end_date: date


class RatesContractDates(FrozenModel):
    time_origin: date
    start_date: date
    end_date: date
    accrual_periods: tuple[RatesAccrualPeriod, ...] = ()

    @model_validator(mode="after")
    def validate_periods(self):
        check_dates(self.time_origin, self.start_date, self.end_date)
        if self.start_date >= self.end_date:
            raise ValueError("L’échéance doit suivre la date de début du contrat.")
        if len({period.flow_id for period in self.accrual_periods}) != len(self.accrual_periods):
            raise ValueError("Un flux ne peut porter qu’une période de coupon.")
        if any(not self.start_date <= item.start_date < item.end_date <= self.end_date
               for item in self.accrual_periods):
            raise ValueError("Chaque période de coupon doit être incluse dans les dates du contrat.")
        return self

    def time(self, day: date) -> float:
        return (day - self.time_origin).days / 365

    def at(self, time: float) -> date:
        """Return the exact civil date, rejecting a rounded or sub-day model time."""
        if not isfinite(time) or abs(time) > date.max.toordinal() / 365:
            raise ValueError("Temps ACT/365F hors calendrier civil.")
        day_offset = round(time * 365)
        if time != day_offset / 365:
            raise ValueError("Chaque temps du contrat daté doit représenter un jour exact en ACT/365F.")
        try:
            return self.time_origin + timedelta(days=day_offset)
        except OverflowError as exc:
            raise ValueError("Temps ACT/365F hors calendrier civil.") from exc
