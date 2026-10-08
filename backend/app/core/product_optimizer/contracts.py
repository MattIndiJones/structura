"""Optimizer inputs use fractions, calendar months, and explicit assumptions."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from ..calendars import BusinessDayConvention, SUPPORTED_CURRENCIES
from ..schemas import validate_correlation_matrix, validate_term_curve, UnderlyingParams
from .families import family_schema

MAX_CANDIDATES = 256
MAX_WORK = 250_000_000
MAX_SECONDS = 120
SOLVER_ITERATIONS = 18
MAX_PARALLEL_WORKERS = 4
MAX_PARALLEL_MEMORY_BYTES = 256 * 1024**2
VALIDATION_CANDIDATES = 5
VALIDATION_SEEDS = (100042, 200042)


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
    dividend_curve: list[list[float]] = Field(default_factory=list, max_length=30)

    @field_validator("dividend_curve")
    @classmethod
    def dividend_nodes(cls, curve):
        return UnderlyingParams.validate_dividend_curve(curve)

    @model_validator(mode="after")
    def dividend_first_bucket(self):
        if self.dividend_curve and (abs(self.dividend_curve[0][1]-self.q) > 1e-10
                                    or any(node[1] > .5 for node in self.dividend_curve)):
            raise ValueError("La courbe de dividende doit commencer à q, avec des rendements de 0 à 50 %.")
        return self


class FieldProvenance(StrictModel):
    source: Literal["USER_ASSUMPTION", "PRICER_ASSUMPTION", "HISTORICAL_ESTIMATE"] = "USER_ASSUMPTION"
    as_of: date
    reference_value: float | list[list[float]]
    method: str = Field(default="Hypothèse utilisateur", min_length=1, max_length=160)
    provider: str | None = Field(default=None, max_length=40)
    fetched_at: str | None = Field(default=None, max_length=50)
    window_days: int | None = Field(default=None, ge=1, le=2520)
    n_observations: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class IssuanceEconomics(StrictModel):
    upfront_fees: float = Field(default=0, ge=0, le=.1)
    structuring_margin: float = Field(default=0, ge=0, le=.1)


class MarketAssumptions(StrictModel):
    as_of: date
    source: Literal["USER_ASSUMPTION", "PRICER_SESSION", "AUTO_MARKET"] = "USER_ASSUMPTION"
    rate: float = Field(ge=-.1, le=.3)
    yield_curve: list[list[float]] = Field(default_factory=list, max_length=30)
    funding_spread: float = Field(default=0, ge=-.05, le=.5)
    funding_curve: list[list[float]] = Field(default_factory=list, max_length=30)
    captured_at: datetime | None = None
    reference_currency: str | None = Field(default=None, min_length=3, max_length=3)
    reference_tickers: list[str] = Field(default_factory=list, max_length=3)
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict, max_length=32)
    underlyings: list[MarketUnderlying] = Field(min_length=1, max_length=3)
    correlation: list[list[float]]

    @field_validator("yield_curve", "funding_curve")
    @classmethod
    def term_nodes(cls, curve, info):
        curve = validate_term_curve(curve, "courbe de taux" if info.field_name == "yield_curve" else "courbe de funding")
        low, high = (-.1, .3) if info.field_name == "yield_curve" else (-.05, .5)
        if any(not low <= node[1] <= high for node in curve):
            raise ValueError(f"Courbe hors périmètre Optimizer [{low:.0%}, {high:.0%}].")
        return curve

    @model_validator(mode="after")
    def matrix(self):
        if self.funding_curve and self.funding_spread != 0:
            raise ValueError("Saisissez une courbe de funding ou un spread plat, jamais les deux.")
        if self.captured_at is not None and self.captured_at.utcoffset() is None:
            raise ValueError("Le timestamp du snapshot doit préciser son fuseau horaire.")
        tickers = [u.ticker for u in self.underlyings]
        if len(set(tickers)) != len(tickers):
            raise ValueError("Un sous-jacent ne peut pas être sélectionné deux fois.")
        self.correlation = validate_correlation_matrix(self.correlation, len(tickers))
        if np.linalg.eigvalsh(self.correlation).min() < 1e-8:
            raise ValueError("Matrice de corrélation non définie positive ; aucune réparation implicite en V1.")
        allowed = {"rate", "yield_curve", "funding_spread", "funding_curve", "correlation"}
        allowed.update(f"underlyings.{u.ticker}.{field}" for u in self.underlyings
                       for field in ("sigma", "q", "dividend_curve"))
        for key, provenance in self.provenance.items():
            if key not in allowed:
                raise ValueError(f"Champ de provenance inconnu : {key}.")
            if provenance.as_of > self.as_of:
                raise ValueError(f"Référence future par rapport à la date d'hypothèses : {key}.")
            value = provenance.reference_value
            if key == "correlation":
                size = len(self.reference_tickers) or len(tickers)
                if not isinstance(value, list) or len(value) != size or any(len(row) != size for row in value):
                    raise ValueError("La corrélation de référence doit correspondre au panier de référence.")
                validate_correlation_matrix(value, size)
            elif key.endswith("curve"):
                if not isinstance(value, list) or len(value) > 30 or any(len(node) != 2 for node in value):
                    raise ValueError(f"Courbe de référence invalide : {key}.")
            elif isinstance(value, list):
                raise ValueError(f"Une référence scalaire est requise : {key}.")
        if self.source in {"PRICER_SESSION", "AUTO_MARKET"} and not allowed.issubset(self.provenance):
            raise ValueError("Un import Pricer doit conserver la référence de chaque champ de marché.")
        if self.source in {"PRICER_SESSION", "AUTO_MARKET"} and (self.captured_at is None or self.reference_currency is None):
            raise ValueError("Un import Pricer doit conserver sa devise et son timestamp de copie.")
        if self.source in {"PRICER_SESSION", "AUTO_MARKET"} and (not self.reference_tickers
                or len(set(self.reference_tickers)) != len(self.reference_tickers)
                or any(not ticker or len(ticker) > 40 for ticker in self.reference_tickers)):
            raise ValueError("Un import Pricer doit conserver l'ordre et les tickers du panier de référence.")
        return self


class StructuralRanges(StrictModel):
    maturity_months: ParameterRange
    protection_barrier: ParameterRange | None = None
    strike: ParameterRange | None = None
    redemption_cap: ParameterRange | None = None
    put_strike: ParameterRange | None = None
    gearing: ParameterRange | None = None
    autocall_trigger: ParameterRange | None = None
    coupon_barrier: ParameterRange | None = None
    observation_months: list[Literal[1, 3, 6, 12]] | None = Field(default=None, min_length=1, max_length=4)

    @model_validator(mode="after")
    def supported_ranges(self):
        for field, low, high in ((self.maturity_months, 12, 60),
                                 (self.protection_barrier, .3, 1),
                                 (self.autocall_trigger, .8, 1.2),
                                 (self.coupon_barrier, .3, 1.), (self.strike, .5, 1.5),
                                 (self.redemption_cap, 1., 3.), (self.put_strike, .3, 1.2), (self.gearing, 1., 5.)):
            if field is None:
                continue
            if field.minimum < low or field.maximum > high:
                raise ValueError(f"Plage hors périmètre V1 [{low}, {high}].")
        if any(x != int(x) for x in (self.maturity_months.minimum, self.maturity_months.maximum, self.maturity_months.step)):
            raise ValueError("Les maturités et leur pas sont exprimés en mois entiers.")
        if self.observation_months and len(set(self.observation_months)) != len(self.observation_months):
            raise ValueError("Fréquences dupliquées.")
        return self


class HardConstraints(StrictModel):
    target_price: float = Field(default=1, ge=.8, le=1.2)
    price_tolerance: float = Field(default=.005, ge=.0001, le=.03)
    coupon_minimum: float = Field(default=0, ge=0, le=.5)
    coupon_maximum: float = Field(default=.3, gt=0, le=.5)
    target_coupon: float | None = Field(default=None, ge=0, le=.5)
    coupon_tolerance: float = Field(default=.005, gt=0, le=.1)
    participation_minimum: float = Field(default=0, ge=0, le=5)
    participation_maximum: float = Field(default=3, gt=0, le=5)
    cap_minimum: float = Field(default=1.01, ge=1., le=3)
    cap_maximum: float = Field(default=2, gt=1., le=3)
    max_expected_capital_loss: float | None = Field(default=None, ge=0, le=1)
    max_probability_loss: float | None = Field(default=None, ge=0, le=1)
    min_probability_autocall: float | None = Field(default=None, ge=0, le=1)
    max_expected_maturity: float | None = Field(default=None, gt=0, le=6)

    @model_validator(mode="after")
    def coupon_bounds(self):
        if self.coupon_minimum >= self.coupon_maximum:
            raise ValueError("La borne haute du coupon doit dépasser la borne basse.")
        if self.participation_minimum >= self.participation_maximum or self.cap_minimum >= self.cap_maximum:
            raise ValueError("La borne haute de résolution doit dépasser la borne basse.")
        if self.target_coupon is not None and not self.coupon_minimum <= self.target_coupon <= self.coupon_maximum:
            raise ValueError("Le coupon cible doit appartenir à l'intervalle de résolution.")
        return self


class SearchConfiguration(StrictModel):
    strategy: Literal["grid"] = "grid"
    simulations: int = Field(default=4000, ge=1000, le=20000)
    max_candidates: int = Field(default=32, ge=1, le=MAX_CANDIDATES)
    seed: Literal[42] = 42
    parallel_workers: int = Field(default=2, ge=1, le=MAX_PARALLEL_WORKERS)
    max_seconds: int = Field(default=120, ge=30, le=3600)


class OptimizationRequest(StrictModel):
    schema_version: Literal[1] = 1
    objective: Literal["maximize_coupon", "maximize_protection", "target_coupon", "maximize_participation", "maximize_cap"] = "maximize_coupon"
    product_family: Literal["autocall_athena", "phoenix", "phoenix_memoire", "autocall_barriere_degressive", "reverse_convertible", "capital_garanti", "booster", "autocall_gear_put"] = "autocall_athena"
    model: Literal["auto", "constant"] = "auto"
    currency: str = "EUR"
    strike_date: date
    pricing_date: date | None = None
    convention: BusinessDayConvention
    settlement_lag: int = Field(default=3, ge=0, le=10)
    market: MarketAssumptions
    economics: IssuanceEconomics = Field(default_factory=IssuanceEconomics)
    ranges: StructuralRanges
    payoff_settings: dict[str, float] = Field(default_factory=dict, max_length=3)
    constraints: HardConstraints = Field(default_factory=HardConstraints)
    search: SearchConfiguration = Field(default_factory=SearchConfiguration)

    @model_validator(mode="after")
    def capability(self):
        family = family_schema(self.product_family, self.objective)
        allowed = {f["key"] for f in family["range_fields"]}
        for key in ("protection_barrier", "autocall_trigger", "coupon_barrier", "strike", "redemption_cap", "put_strike", "gearing"):
            value = getattr(self.ranges, key)
            if (key in allowed) != (value is not None):
                raise ValueError(f"Champ {key} {'requis' if key in allowed else 'non applicable'} pour ce script.")
        if family["has_autocall"] != (self.ranges.observation_months is not None):
            raise ValueError("Fréquences requises uniquement pour les scripts avec autocall.")
        solution = family["solved_field"]
        active_bounds = {solution["minimum_key"], solution["maximum_key"]}
        quantity_fields = {"coupon_minimum", "coupon_maximum", "participation_minimum", "participation_maximum", "cap_minimum", "cap_maximum"}
        inactive = (self.constraints.model_fields_set & quantity_fields) - active_bounds
        if any(getattr(self.constraints, name) != HardConstraints.model_fields[name].default for name in inactive):
            raise ValueError("Bornes de résolution non applicables au paramètre optimisé.")
        if solution["key"] != "coupon" and (self.constraints.target_coupon is not None or self.constraints.coupon_tolerance != .005):
            raise ValueError("Contrainte de coupon non applicable à ce script.")
        if self.constraints.max_expected_capital_loss is not None and not family["risk_severity"]:
            raise ValueError("Plafond de perte en capital réservé au booster et au gear put.")
        if not family["has_autocall"] and self.constraints.min_probability_autocall is not None:
            raise ValueError("Contrainte de rappel non applicable à ce script sans autocall.")
        settings = {f["key"]:f for f in family["fixed_fields"]}
        if set(self.payoff_settings) != set(settings):
            raise ValueError("Réglages de payoff manquants ou non applicables au script sélectionné.")
        for key, value in self.payoff_settings.items():
            field = settings[key]
            if not field["minimum"] <= value <= field["maximum"] or (field["unit"] == "rank" and value != int(value)):
                raise ValueError(f"Réglage de payoff invalide : {key}.")
        if "floor" in settings and self.payoff_settings["floor"] > self.ranges.autocall_trigger.minimum:
            raise ValueError("Le plancher de rappel dépasse le seuil initial minimal.")
        if self.market.reference_currency is not None and self.market.reference_currency != self.currency:
            raise ValueError("La devise a changé depuis l'import Pricer ; reprenez un marché dans la devise de la recherche.")
        if self.pricing_target <= 0:
            raise ValueError("Le budget du payoff après frais et marge doit être positif.")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError("Devise sans calendrier pris en charge.")
        if any(u.currency != self.currency for u in self.market.underlyings):
            raise ValueError("V1 : actifs et règlement dans la même devise ; aucun quanto/FX implicite.")
        if self.pricing_date is None:
            self.pricing_date = self.strike_date
        if self.market.as_of != self.pricing_date or self.pricing_date != self.strike_date:
            raise ValueError("V1 à l'émission : date d'hypothèses = date de strike = date de valeur.")
        if not 2000 <= self.strike_date.year <= 2100:
            raise ValueError("Date hors périmètre 2000–2100.")
        if self.objective == "target_coupon" and self.constraints.target_coupon is None:
            raise ValueError("Un coupon cible est requis pour cet objectif.")
        return self

    @property
    def pricing_target(self):
        return self.constraints.target_price-self.economics.upfront_fees-self.economics.structuring_margin


class OptimizationCandidate(StrictModel):
    candidate_id: str
    product_family: str = "autocall_athena"
    model: str = "constant"
    maturity_months: int
    observation_months: int
    protection_barrier: float | None = None
    strike: float | None = None
    participation: float | None = None
    redemption_cap: float | None = None
    put_strike: float | None = None
    gearing: float | None = None
    autocall_trigger: float | None = None
    coupon_barrier: float | None = None
    autocall_schedule: list[float] | None = None
    coupon: float | None = None
    issue_price: float
    pricing_target: float | None = None
    fair_value: float | None = None
    price_ic95: list[float] | None = None
    probability_loss: float | None = None
    probability_loss_ic95: list[float] | None = None
    probability_capital_loss: float | None = None
    probability_capital_loss_ic95: list[float] | None = None
    expected_capital_loss: float | None = None
    expected_capital_loss_ic95: list[float] | None = None
    conditional_capital_loss: float | None = None
    conditional_capital_loss_ic95: list[float] | None = None
    probability_autocall: float | None = None
    probability_autocall_ic95: list[float] | None = None
    expected_maturity: float | None = None
    expected_maturity_upper95: float | None = None
    expected_coupon_paid: float | None = None
    expected_coupon_paid_ic95: list[float] | None = None
    expected_coupon_unpaid: float | None = None
    expected_coupon_unpaid_ic95: list[float] | None = None
    pricing_status: Literal["PENDING", "PRICED", "FAILED", "SKIPPED"] = "PENDING"
    analytics_status: Literal["UNAVAILABLE", "AVAILABLE", "FAILED"] = "UNAVAILABLE"
    constraint_status: Literal["PENDING", "PASS", "REJECTED"] = "PENDING"
    rank: int | None = None
    pareto_efficient: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    rejection_details: list[dict] = Field(default_factory=list)
    pricing_input: dict | None = None
    validation_status: Literal["NOT_SELECTED", "PENDING", "PASSED", "REJECTED", "FAILED"] = "NOT_SELECTED"
    validation: dict | None = None
