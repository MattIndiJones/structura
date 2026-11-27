"""Frozen EUR Monte Carlo scenarios for the Structura pricing laboratory."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from functools import cache
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from platform import python_version
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, TypeAdapter, field_validator, model_validator

from ..core.product.exotic_credit_calendar import CreditCalendar, project_credit_flows, validate_credit_calendar
from ..core.product.exotic_credit_mc import CreditMcRequest, simulate_credit_mc
from ..core.product.exotic_rates_calibration import HullWhiteCalibrationRequest
from ..core.product.exotic_rates_mc import (
    ExoticRatesTerms, HwMarket, RangeAccrualCoupon, RateCoupon, RatesMCSettings, SwapRate, price_exotic_rates,
)
from ..core.product.models import FrozenModel, FrozenObject
from ..core.valuation_context import json_transport_fingerprint


PROFILE = "eur-exotic-mc-research-v1"
CALIBRATION_PROFILE = "eur-hw1f-swaption-calibration-research-v1"
MAX_PATHS = 250_000
MAX_WORK = 4_000_000
_PARIS = ZoneInfo("Europe/Paris")
Reference = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[\w.:-]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ExoticValuationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.status = code, status


class ExoticMarketSource(FrozenModel):
    kind: Literal["synthetic"] = "synthetic"
    source_id: Reference
    version: int = Field(ge=1, strict=True)
    available_at: AwareDatetime
    validated_at: AwareDatetime

    @field_validator("available_at", "validated_at")
    @classmethod
    def utc(cls, value: datetime):
        return value.astimezone(timezone.utc)


class _DatedSyntheticMarket(FrozenModel):
    valuation_date: date
    cutoff: AwareDatetime
    market_source: ExoticMarketSource

    @field_validator("cutoff")
    @classmethod
    def utc(cls, value: datetime):
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def check_market_cutoff(self):
        if self.cutoff.astimezone(_PARIS).date() != self.valuation_date:
            raise ValueError("La date du cut-off à Paris doit correspondre à la date de valorisation.")
        if max(self.market_source.available_at, self.market_source.validated_at) > self.cutoff:
            raise ValueError("Les données du modèle doivent être disponibles et validées à l’arrêté.")
        return self


class ExoticCalibrationCall(_DatedSyntheticMarket):
    calibration: HullWhiteCalibrationRequest


class _ExoticScenario(_DatedSyntheticMarket):
    schema_version: Literal[1] = 1
    position_id: Reference
    terms_version: int = Field(default=1, ge=1, strict=True)
    value_date_convention: Literal["valuation_date_act365f"] = "valuation_date_act365f"
    expected_engine_fingerprint: Digest | None = None


class ExoticRatesScenario(_ExoticScenario):
    family: Literal["rates"]
    terms: ExoticRatesTerms
    market: HwMarket
    settings: RatesMCSettings
    calibration_receipt: FrozenObject | None = None

    @model_validator(mode="after")
    def check_contract_time_origin(self):
        if self.terms.contract_dates is not None and self.terms.contract_dates.time_origin != self.valuation_date:
            raise ValueError("L’origine du calendrier doit coïncider avec la date de valorisation ACT/365F.")
        return self


class ExoticCreditScenario(_ExoticScenario):
    family: Literal["credit"]
    credit: CreditMcRequest
    credit_calendar: CreditCalendar | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def check_realized_cutoff(self):
        if self.credit.realized is not None:
            context = self.credit.realized.context
            if (context.valuation_date, context.cutoff) != (self.valuation_date, self.cutoff):
                raise ValueError("Le contexte de défaut doit être figé au cut-off du calcul.")
        if self.credit_calendar is not None:
            validate_credit_calendar(self.credit_calendar, self.credit, self.valuation_date)
        return self


ExoticScenario = Annotated[ExoticRatesScenario | ExoticCreditScenario, Field(discriminator="family")]
_SCENARIO = TypeAdapter(ExoticScenario)


def read_scenario(data: dict) -> ExoticScenario:
    return _SCENARIO.validate_python(data)


@cache
def exotic_engine_fingerprint() -> str:
    core = Path(__file__).resolve().parents[1] / "core"
    source_files = (
        "product/exotic_rates_mc.py", "product/exotic_credit_mc.py", "product/exotic_credit_calendar.py",
        "product/exotic_credit_payscript.py", "product/credit_pricing.py",
        "product/credit_default.py", "product/credit_facts.py", "product/models.py",
        "product/exotic_rates_calendar.py", "product/exotic_rates_calibration.py", "product/exotic_rates_payscript.py", "product/rates_payscript.py",
        "payscript/rates.py", "payscript/parser.py", "payscript/bindings.py", "compute_budget.py", "valuation_context.py",
    )
    return json_transport_fingerprint({
        "profile": PROFILE,
        "python": python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "pydantic")},
        "core": {name: sha256((core / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                 for name in source_files},
        "scenario": sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
    })


def _check_work(scenario: ExoticScenario):
    if isinstance(scenario, ExoticRatesScenario):
        settings = scenario.settings
        paths = settings.paths
        if scenario.terms.exercises:
            paths += settings.training_paths or settings.paths
        weight = len(scenario.terms.cashflows) + 2 * len(scenario.terms.exercises)
        for flow in scenario.terms.cashflows:
            if isinstance(flow, RateCoupon):
                indices = (flow.index, flow.spread_index)
            elif isinstance(flow, RangeAccrualCoupon):
                indices = tuple(observation.index for observation in flow.observations)
            else:
                continue
            weight += sum(
                len(index.fixed_periods) + 2 * len(index.floating_periods) if isinstance(index, SwapRate) else 2
                for index in indices if index is not None
            )
    else:
        request = scenario.credit
        paths = request.settings.paths
        weight = len(request.contract.coupons) + len(request.market.marginals)
    if paths > MAX_PATHS or paths * max(1, weight) > MAX_WORK:
        raise ExoticValuationError("EXOTIC_WORK_LIMIT", "Le budget dépasse le plafond de calcul synchrone. Réduisez le nombre de trajectoires ou la grille.")


def price_exotic_scenario(scenario: ExoticScenario, *, retain_samples: bool = False):
    _check_work(scenario)
    if scenario.expected_engine_fingerprint not in (None, exotic_engine_fingerprint()):
        raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur attendu n’est pas disponible.", 409)
    if isinstance(scenario, ExoticRatesScenario):
        return price_exotic_rates(scenario.terms, scenario.market, scenario.settings)
    calendar = scenario.credit_calendar
    if calendar is not None:
        validate_credit_calendar(calendar, scenario.credit, scenario.valuation_date)
    calculation = simulate_credit_mc(scenario.credit, retain_samples=retain_samples)
    if calendar is None:
        return calculation
    schedule = project_credit_flows(calendar, scenario.credit, scenario.valuation_date, calculation.result)
    return replace(calculation, result=calculation.result.model_copy(update={"contract_schedule": schedule}))


def result_payload(calculation) -> dict:
    return calculation.result.model_dump(mode="json")
