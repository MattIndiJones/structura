"""Immutable contractual dates and identities for native Product schedules."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..calendars import BusinessDayConvention
from ..valuation_context import canonical_fingerprint


class ScheduleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SchedulePeriod(ScheduleModel):
    period_id: str
    rank: int = Field(ge=1)
    unadjusted_start: Date
    unadjusted_end: Date
    accrual_start: Date
    accrual_end: Date  # Exclusive, including for the CDS terminal period.
    day_count: Literal["ACT/360", "30E/360"]
    day_count_days: int = Field(gt=0)
    day_count_denominator: Literal[360] = 360
    fixing_date: Date | None = None
    payment_date: Date
    flow_id: str
    projection_start: Date | None = None
    projection_end: Date | None = None
    credit_observation_date: Date | None = None

    @property
    def year_fraction(self) -> float:
        return self.day_count_days / self.day_count_denominator


class ScheduleEvent(ScheduleModel):
    event_id: str
    kind: Literal["principal", "initial_settlement", "step_in", "protection_end", "default_settlement",
                  "cashflow", "observation", "exercise", "exercise_settlement", "accrual_start", "accrual_end"]
    date: Date | None = None
    flow_id: str | None = None
    accrued_days: int | None = Field(default=None, ge=0)
    model_time_years: float | None = Field(default=None, exclude_if=lambda value: value is None)
    date_projection: Literal["exact", "nearest_calendar_day"] | None = Field(default=None, exclude_if=lambda value: value is None)


class ScheduleLeg(ScheduleModel):
    leg_id: str
    kind: Literal["floating_coupon", "fixed_coupon", "principal", "premium", "protection", "initial_settlement", "exotic_contract"]
    calendar: str | None = None
    business_day_convention: BusinessDayConvention | None = None
    fixing_calendar: str | None = None
    fixing_lag_business_days: int | None = None
    payment_lag_business_days: int | None = None
    step_in_lag_calendar_days: int | None = None
    roll_rule: str | None = None
    periods: tuple[SchedulePeriod, ...] = ()
    events: tuple[ScheduleEvent, ...] = ()


class ScheduleCalendarVersion(ScheduleModel):
    calendar_id: str
    version: str


class ScheduleContent(ScheduleModel):
    schema_version: Literal[1] = 1
    resolver_version: str
    instrument_type: Literal["FRN", "IRS", "CDS", "CLN", "EXOTIC_RATES", "EXOTIC_CREDIT"]
    terms_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: int | None = Field(default=None, ge=1)
    terms_version: int | None = Field(default=None, ge=1)
    calendar_versions: tuple[ScheduleCalendarVersion, ...]
    legs: tuple[ScheduleLeg, ...]

    @model_validator(mode="after")
    def validate_binding(self):
        if (self.product_id is None) != (self.terms_version is None):
            raise ValueError("La référence du produit et sa version de termes doivent être fournies ensemble.")
        return self


class NativeSchedule(ScheduleContent):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self):
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("L’empreinte de l’échéancier est incohérente.")
        return self

    @classmethod
    def seal(cls, content: ScheduleContent) -> NativeSchedule:
        payload = content.model_dump(mode="json")
        return cls.model_validate({**payload, "fingerprint": canonical_fingerprint(payload)})


class SchedulePreparation(ScheduleModel):
    status: Literal["ready", "incomplete", "not_prepared"]
    schedule: NativeSchedule | None = None
    diagnostics: tuple[str, ...] = ()
