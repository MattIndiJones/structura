"""Optimizer inputs use fractions, calendar months, and explicit assumptions."""
from datetime import date
from decimal import Decimal
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..calendars import BusinessDayConvention, SUPPORTED_CURRENCIES
from ..schemas import validate_correlation_matrix

MAX_CANDIDATES = 64
MAX_WORK = 250_000_000
MAX_SECONDS = 120
SOLVER_ITERATIONS = 18


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ParameterRange(StrictModel):
    minimum: float = Field(ge=0, le=120)
    maximum: float = Field(ge=0, le=120)
    step: float = Field(ge=.000001, le=120)

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError("La borne minimale dépasse la borne maximale.")
        if self.count > 1000:
            raise ValueError("Un axe ne peut pas dépasser 1 000 valeurs ; augmentez le pas.")
        return self

    @property
    def count(self):
        low, high, step = map(lambda x: Decimal(str(x)), (self.minimum, self.maximum, self.step))
        return int((high - low) // step) + 1

    def values(self):
        low, step = Decimal(str(self.minimum)), Decimal(str(self.step))
        return [float(low + i * step) for i in range(self.count)]


class MarketUnderlying(StrictModel):
    asset_type: Literal["equity", "index"] = "index"
    ticker: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3)
    sigma: float = Field(ge=0, le=1.5)
    q: float = Field(ge=0, le=.5)


class MarketAssumptions(StrictModel):
    as_of: date
    source: Literal["USER_ASSUMPTION"] = "USER_ASSUMPTION"
    rate: float = Field(ge=-.1, le=.3)
    underlyings: list[MarketUnderlying] = Field(min_length=1, max_length=3)
    correlation: list[list[float]]

    @model_validator(mode="after")
    def matrix(self):
        tickers = [u.ticker for u in self.underlyings]
        if len(set(tickers)) != len(tickers):
            raise ValueError("Un sous-jacent ne peut pas être sélectionné deux fois.")
        self.correlation = validate_correlation_matrix(self.correlation, len(tickers))
        if np.linalg.eigvalsh(self.correlation).min() < 1e-8:
            raise ValueError("Matrice de corrélation non définie positive ; aucune réparation implicite en V1.")
        return self


class StructuralRanges(StrictModel):
    maturity_months: ParameterRange
    protection_barrier: ParameterRange
    autocall_trigger: ParameterRange
    observation_months: list[Literal[1, 3, 6, 12]] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def supported_ranges(self):
        for field, low, high in ((self.maturity_months, 12, 60),
                                 (self.protection_barrier, .3, 1),
                                 (self.autocall_trigger, .8, 1.2)):
            if field.minimum < low or field.maximum > high:
                raise ValueError(f"Plage hors périmètre V1 [{low}, {high}].")
        if any(x != int(x) for x in (self.maturity_months.minimum, self.maturity_months.maximum, self.maturity_months.step)):
            raise ValueError("Les maturités et leur pas sont exprimés en mois entiers.")
        if len(set(self.observation_months)) != len(self.observation_months):
            raise ValueError("Fréquences dupliquées.")
        return self


class HardConstraints(StrictModel):
    target_price: float = Field(default=1, ge=.8, le=1.2)
    price_tolerance: float = Field(default=.005, ge=.0001, le=.03)
    coupon_minimum: float = Field(default=0, ge=0, le=.5)
    coupon_maximum: float = Field(default=.3, gt=0, le=.5)
    target_coupon: float | None = Field(default=None, ge=0, le=.5)
    coupon_tolerance: float = Field(default=.005, gt=0, le=.1)
    max_probability_loss: float | None = Field(default=None, ge=0, le=1)
    min_probability_autocall: float | None = Field(default=None, ge=0, le=1)
    max_expected_maturity: float | None = Field(default=None, gt=0, le=6)

    @model_validator(mode="after")
    def coupon_bounds(self):
        if self.coupon_minimum >= self.coupon_maximum:
            raise ValueError("La borne haute du coupon doit dépasser la borne basse.")
        if self.target_coupon is not None and not self.coupon_minimum <= self.target_coupon <= self.coupon_maximum:
            raise ValueError("Le coupon cible doit appartenir à l'intervalle de résolution.")
        return self


class SearchConfiguration(StrictModel):
    strategy: Literal["grid"] = "grid"
    simulations: int = Field(default=4000, ge=1000, le=20000)
    max_candidates: int = Field(default=32, ge=1, le=MAX_CANDIDATES)
    seed: Literal[42] = 42


class OptimizationRequest(StrictModel):
    schema_version: Literal[1] = 1
    objective: Literal["maximize_coupon", "maximize_protection", "target_coupon"] = "maximize_coupon"
    product_family: Literal["autocall_athena"] = "autocall_athena"
    model: Literal["auto", "constant"] = "auto"
    currency: str = "EUR"
    strike_date: date
    convention: BusinessDayConvention
    settlement_lag: int = Field(default=3, ge=0, le=10)
    market: MarketAssumptions
    ranges: StructuralRanges
    constraints: HardConstraints = Field(default_factory=HardConstraints)
    search: SearchConfiguration = Field(default_factory=SearchConfiguration)

    @model_validator(mode="after")
    def capability(self):
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError("Devise sans calendrier pris en charge.")
        if any(u.currency != self.currency for u in self.market.underlyings):
            raise ValueError("V1 : actifs et règlement dans la même devise ; aucun quanto/FX implicite.")
        if self.market.as_of != self.strike_date:
            raise ValueError("V1 à l'émission : date d'hypothèses = date de strike = date de valeur.")
        if not 2000 <= self.strike_date.year <= 2100:
            raise ValueError("Date hors périmètre 2000–2100.")
        if self.objective == "target_coupon" and self.constraints.target_coupon is None:
            raise ValueError("Un coupon cible est requis pour cet objectif.")
        return self


class OptimizationCandidate(StrictModel):
    candidate_id: str
    product_family: str = "autocall_athena"
    model: str = "constant"
    maturity_months: int
    observation_months: int
    protection_barrier: float
    autocall_trigger: float
    coupon: float | None = None
    issue_price: float
    fair_value: float | None = None
    price_ic95: list[float] | None = None
    probability_loss: float | None = None
    probability_loss_ic95: list[float] | None = None
    probability_autocall: float | None = None
    probability_autocall_ic95: list[float] | None = None
    expected_maturity: float | None = None
    expected_maturity_upper95: float | None = None
    pricing_status: Literal["PENDING", "PRICED", "FAILED", "SKIPPED"] = "PENDING"
    analytics_status: Literal["UNAVAILABLE", "AVAILABLE", "FAILED"] = "UNAVAILABLE"
    constraint_status: Literal["PENDING", "PASS", "REJECTED"] = "PENDING"
    rank: int | None = None
    pareto_efficient: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    pricing_input: dict | None = None
