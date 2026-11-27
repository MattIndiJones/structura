"""Exact-time research simulation for synthetic EUR credit contracts."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, pi, sqrt
from typing import Literal

import numpy as np
import scipy
from pydantic import Field, model_validator
from scipy.integrate import quad_vec
from scipy.special import log_ndtr, ndtr, ndtri, roots_hermitenorm

from ..valuation_context import json_transport_fingerprint
from .credit_default import CreditDefaultContext, CreditDefaultResult, price_credit_default
from .credit_pricing import CreditCoupon, SurvivalCurve, value_cds, value_cln
from .exotic_credit_calendar import CreditContractSchedule
from .exotic_credit_payscript import (
    CreditPayoffEvidence, CreditScriptMemberAmount, ExoticCreditScript, credit_coupon_rate, credit_default_amounts,
)
from .models import CLNTerms, CDSTerms, FrozenModel, Product


_CHUNK = 8192
_Z95 = 1.959963984540054
ReferenceMethod = Literal["lot3_analytical", "independent_poisson_binomial", "gaussian_factor_quadrature", "perfect_dependence_limit"]


class CreditMcError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CreditMcContract(FrozenModel):
    kind: Literal["cds", "cln", "basket_cds"]
    nominal_eur: float = Field(gt=0, le=1e12)
    maturity_years: float = Field(gt=0, le=30)
    coupons: tuple[CreditCoupon, ...] = Field(max_length=360)
    coupon_bps: float = Field(ge=0, le=10_000)
    side: Literal["BUY", "SELL"]
    protected_from: float = Field(default=0.0, ge=0)
    initial_accrued_fraction: float = Field(default=0.0, ge=0, le=1)
    default_settlement_delay_years: float = Field(default=0.0, ge=0, le=2)
    principal_payment_years: float | None = Field(default=None, gt=0, le=32)
    trigger_rank: int | None = Field(default=None, strict=True, ge=1)
    tie_break: Literal["reference_entity_id"] = "reference_entity_id"
    payscript: ExoticCreditScript | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def check_contract(self):
        if self.protected_from >= self.maturity_years:
            raise ValueError("La protection doit commencer avant son échéance.")
        if (self.kind == "basket_cds") != (self.trigger_rank is not None):
            raise ValueError("Le rang de défaut est requis uniquement pour un panier.")
        if self.principal_payment_years is not None and (
                self.kind != "cln" or self.principal_payment_years < self.maturity_years):
            raise ValueError("Le remboursement de la CLN ne peut pas précéder son échéance.")
        if any(max(coupon.end, coupon.payment) > 32 or coupon.year_fraction > 2 or coupon.start < -2
               for coupon in self.coupons):
            raise ValueError("Les dates et fractions de coupon excèdent le domaine de la recette crédit.")
        if any(coupon.survival_time > self.maturity_years for coupon in self.coupons) or any(
                left.end > right.start or left.survival_time >= right.survival_time
                for left, right in zip(self.coupons, self.coupons[1:])):
            raise ValueError("Les périodes de coupon doivent être ordonnées et dans l’horizon de crédit.")
        return self


class CreditMcMarginal(FrozenModel):
    reference_entity_id: str = Field(min_length=1, max_length=128)
    curve: SurvivalCurve
    recovery_fraction: float = Field(ge=0, le=1)
    loading: float = Field(default=0.0, ge=-1, le=1)
    source_id: str = Field(min_length=1, max_length=160)
    source_version: int = Field(strict=True, ge=1)


class CreditMcMarket(FrozenModel):
    quality: Literal["synthetic"] = "synthetic"
    source_id: str = Field(min_length=1, max_length=160)
    source_version: int = Field(strict=True, ge=1)
    discount_rate: float = Field(ge=-1, le=1)
    funding_bps: float = Field(default=0.0, ge=-10_000, le=10_000)
    marginals: tuple[CreditMcMarginal, ...] = Field(min_length=1, max_length=24)
    dependence_model: Literal["independence", "gaussian_one_factor"] = "independence"
    dependence_source_id: str | None = Field(default=None, min_length=1, max_length=160)
    dependence_source_version: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode="after")
    def check_dependence(self):
        ids = {member.reference_entity_id for member in self.marginals}
        if len(ids) != len(self.marginals):
            raise ValueError("Les noms du panier doivent être uniques.")
        if self.dependence_model == "independence":
            if any(member.loading != 0 for member in self.marginals):
                raise ValueError("Les chargements non nuls exigent un modèle de dépendance déclaré.")
        elif self.dependence_source_id is None or self.dependence_source_version is None:
            raise ValueError("La dépendance gaussienne exige une source et sa version.")
        if any(abs(member.loading) == 1 for member in self.marginals) and not _perfect_dependence(self.marginals):
            raise ValueError("La limite de dépendance parfaite exige des marges identiques et des chargements unitaires de même signe.")
        return self


class CreditMcSettings(FrozenModel):
    paths: int = Field(strict=True, ge=2, le=2_000_000)
    seed: int = Field(strict=True, ge=0, lt=2**64)
    estimator: Literal["plain", "conditional_single_name"] = "plain"


class CreditMcRealized(FrozenModel):
    product: Product
    context: CreditDefaultContext


class CreditMcRequest(FrozenModel):
    schema_version: Literal[1] = 1
    contract: CreditMcContract
    market: CreditMcMarket
    settings: CreditMcSettings
    realized: CreditMcRealized | None = None

    @model_validator(mode="after")
    def check_inputs(self):
        contract, market = self.contract, self.market
        if self.realized is not None and contract.payscript is not None:
            raise ValueError("Le PayScript crédit requiert une position vivante sans défaut déjà constaté.")
        basket = contract.kind == "basket_cds"
        if basket and (contract.trigger_rank > len(market.marginals) or self.realized is not None):
            raise ValueError("Le panier exige un rang admissible et un état initial avant événement réalisé.")
        if not basket and len(market.marginals) != 1:
            raise ValueError("Un single-name exige une seule courbe de survie.")
        if len(market.marginals) > 1 and self.settings.estimator == "conditional_single_name":
            raise ValueError("L’estimateur conditionnel proposé traite un seul nom.")
        if contract.kind != "cln" and market.funding_bps != 0:
            raise ValueError("Le funding émetteur intervient uniquement dans l’actualisation d’une CLN.")
        if self.realized is None and any(member.curve.maturities[-1] < contract.maturity_years
                                         for member in market.marginals):
            raise ValueError("Chaque courbe de survie doit couvrir l’échéance de crédit.")
        return self


class CreditMcStatistic(FrozenModel):
    mean: float
    standard_error: float = Field(ge=0)
    ci95_half_width: float = Field(ge=0)


class CreditMcEstimate(FrozenModel):
    clean_pv_eur: CreditMcStatistic
    dirty_pv_eur: CreditMcStatistic
    trigger_probability: CreditMcStatistic
    protection_pv_eur: CreditMcStatistic | None = None
    scheduled_premium_pv_eur: CreditMcStatistic | None = None
    accrual_on_default_pv_eur: CreditMcStatistic | None = None
    coupon_pv_eur: CreditMcStatistic | None = None
    survival_principal_pv_eur: CreditMcStatistic | None = None
    default_redemption_pv_eur: CreditMcStatistic | None = None


class CreditMcReference(FrozenModel):
    method: ReferenceMethod
    clean_pv_eur: float
    dirty_pv_eur: float
    trigger_probability: float
    protection_pv_eur: float | None = None
    scheduled_premium_pv_eur: float | None = None
    accrual_on_default_pv_eur: float | None = None
    coupon_pv_eur: float | None = None
    survival_principal_pv_eur: float | None = None
    default_redemption_pv_eur: float | None = None
    quadrature_error_estimate_eur: float = Field(default=0.0, ge=0)
    payoff_basis: Literal["payscript_effective_amounts"] | None = Field(default=None, exclude_if=lambda value: value is None)


class CreditMcSurvival(FrozenModel):
    time_years: float
    estimate: CreditMcStatistic
    reference: float = Field(ge=0, le=1)


class CreditMcFrequency(FrozenModel):
    defaults_at_maturity: int = Field(ge=0)
    estimate: CreditMcStatistic
    reference: float = Field(ge=0, le=1)


class CreditMcProvenance(FrozenModel):
    engine_version: Literal["eur-credit-exact-default-mc-v1"] = "eur-credit-exact-default-mc-v1"
    request_fingerprint: str
    market_fingerprint: str
    state_fingerprint: str | None = None
    state_policy: Literal["initial_all_names_alive", "single_name_survivor_curve", "resolved_lot3_facts"]
    draw_fingerprint: str | None = None
    sampler: Literal["numpy.PCG64"] | None
    estimator: Literal["plain", "conditional_single_name"] | None
    seed: int | None
    numpy_version: str
    scipy_version: str
    independent_samples: int = Field(ge=0)
    stream_partition: Literal["independent_rows_names_sorted_by_reference_entity_id"]
    time_discretization_years: Literal[0] = 0
    dependence_model: Literal["independence", "gaussian_one_factor"] | None
    member_order: tuple[str, ...]
    gaussian_asset_correlation: tuple[tuple[float, ...], ...] = ()


class CreditMcResult(FrozenModel):
    schema_version: Literal[1] = 1
    state: Literal["alive", "recovery_pending", "settlement_pending", "settled"]
    payscript_metadata: CreditPayoffEvidence | None = Field(default=None, exclude_if=lambda value: value is None)
    contract_schedule: CreditContractSchedule | None = Field(default=None, exclude_if=lambda value: value is None)
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float
    estimate: CreditMcEstimate | None = None
    reference: CreditMcReference | None = None
    survival: tuple[CreditMcSurvival, ...] = ()
    default_count_at_maturity: tuple[CreditMcFrequency, ...] = ()
    realized: CreditDefaultResult | None = None
    provenance: CreditMcProvenance


def _perfect_dependence(members: tuple[CreditMcMarginal, ...]) -> bool:
    first = members[0]
    return abs(first.loading) == 1 and all(
        member.loading == first.loading and member.curve == first.curve for member in members
    )


@dataclass(frozen=True)
class _HazardSegments:
    starts: np.ndarray
    ends: np.ndarray
    hazard: np.ndarray
    cumulative: np.ndarray

    @classmethod
    def from_curve(cls, curve: SurvivalCurve, maturity: float) -> _HazardSegments:
        ends = np.asarray([*(knot for knot in curve.maturities if knot < maturity), maturity])
        starts = np.r_[0.0, ends[:-1]]
        hazard = np.asarray(curve.hazards[:len(ends)])
        return cls(starts, ends, hazard, np.cumsum((ends - starts) * hazard))

    def inverse(self, thresholds: np.ndarray) -> np.ndarray:
        index = np.searchsorted(self.cumulative, thresholds, side="left")
        index = np.where(thresholds == 0, np.searchsorted(self.cumulative, 0, side="right"), index)
        covered = index < len(self.ends)
        selected = index[covered]
        before = np.r_[0.0, self.cumulative[:-1]]
        times = np.full(len(thresholds), np.inf)
        inverted = self.starts[selected] + (thresholds[covered] - before[selected]) / self.hazard[selected]
        times[covered] = np.clip(inverted, self.starts[selected], self.ends[selected])
        return times

    def default_distribution(self, time: float) -> tuple[float, float]:
        index = min(int(np.searchsorted(self.ends, time, side="right")), len(self.ends) - 1)
        before = float(self.cumulative[index - 1]) if index else 0.0
        integrated = before + self.hazard[index] * (time - self.starts[index])
        return float(-np.expm1(-integrated)), float(self.hazard[index] * np.exp(-integrated))


def invert_default_times(curve: SurvivalCurve, exponential_thresholds: np.ndarray, maturity_years: float) -> np.ndarray:
    """Invert a piecewise-constant cumulative hazard with infinity for no default in the horizon."""
    thresholds = np.asarray(exponential_thresholds, dtype=float)
    if thresholds.ndim != 1 or np.any(~np.isfinite(thresholds)) or np.any(thresholds < 0):
        raise ValueError("Les seuils exponentiels doivent former un vecteur positif et fini.")
    if not 0 < maturity_years <= curve.maturities[-1]:
        raise ValueError("La courbe de survie doit couvrir un horizon positif.")
    return _HazardSegments.from_curve(curve, maturity_years).inverse(thresholds)


def _discount(request: CreditMcRequest) -> float:
    return request.market.discount_rate + request.market.funding_bps / 10_000


def _side(contract: CreditMcContract) -> int:
    return 1 if contract.side == "BUY" else -1


def _paths(request: CreditMcRequest, defaults: np.ndarray, recoveries: np.ndarray) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    contract = request.contract
    maturity, rate, nominal = contract.maturity_years, _discount(request), contract.nominal_eur
    rank = contract.trigger_rank or 1
    order = np.argsort(defaults, axis=1, kind="stable")[:, rank - 1]
    trigger = defaults[np.arange(len(defaults)), order]
    triggered = trigger <= maturity
    protected = triggered & (trigger >= contract.protected_from)
    trigger_payment = np.where(protected, trigger + contract.default_settlement_delay_years, 0.0)
    discounted_default = np.where(protected, np.exp(-rate * trigger_payment), 0.0)
    coupon_rate = contract.coupon_bps / 10_000
    scheduled = np.zeros(len(defaults))
    for coupon in contract.coupons:
        scheduled += (trigger > coupon.survival_time) * (nominal * coupon_rate * coupon.year_fraction * exp(-rate * coupon.payment))

    if contract.kind == "cln":
        principal = (~triggered) * (nominal * exp(-rate * (contract.principal_payment_years or maturity)))
        recovery = nominal * recoveries[order] * discounted_default
        dirty = scheduled + principal + recovery
        clean = dirty - nominal * coupon_rate * contract.initial_accrued_fraction
        metrics = dict(coupon_pv_eur=scheduled, survival_principal_pv_eur=principal, default_redemption_pv_eur=recovery)
    else:
        protection = nominal * (1 - recoveries[order]) * discounted_default
        accrued = np.zeros(len(defaults))
        for coupon in contract.coupons:
            valid = protected & (trigger >= coupon.start) & (trigger < coupon.end)
            accrued[valid] += ((trigger[valid] - coupon.start) * discounted_default[valid]
                               * nominal * coupon_rate * coupon.year_fraction / (coupon.end - coupon.start))
        dirty = protection - scheduled - accrued
        clean = dirty + nominal * coupon_rate * contract.initial_accrued_fraction
        metrics = dict(protection_pv_eur=protection, scheduled_premium_pv_eur=scheduled, accrual_on_default_pv_eur=accrued)
    metrics.update(clean_pv_eur=_side(contract) * clean, dirty_pv_eur=_side(contract) * dirty, trigger_probability=triggered)
    return metrics, trigger, np.count_nonzero(defaults <= maturity, axis=1)


def _single_name_reference(request: CreditMcRequest, member: CreditMcMarginal, method: ReferenceMethod) -> CreditMcReference:
    contract = request.contract
    rate, maturity = request.market.discount_rate, contract.maturity_years
    common = dict(nominal=contract.nominal_eur, recovery=member.recovery_fraction,
                  coupons=contract.coupons, protected_from=contract.protected_from)
    accrued, coupon_rate, side = contract.initial_accrued_fraction, contract.coupon_bps / 10_000, _side(contract)
    if contract.kind == "cln":
        legs = value_cln(member.curve, rate, maturity, **common, accrued_fraction=accrued,
                         coupon_rate=coupon_rate, settlement_delay=contract.default_settlement_delay_years,
                         funding_bps=request.market.funding_bps, principal_payment=contract.principal_payment_years)
        values = dict(coupon_pv_eur=legs.coupon_pv_eur, survival_principal_pv_eur=legs.survival_principal_pv_eur,
                      default_redemption_pv_eur=legs.default_redemption_pv_eur, dirty_pv_eur=side * legs.dirty_pv_eur,
                      clean_pv_eur=side * legs.clean_pv_eur)
    else:
        legs = value_cds(member.curve, rate, maturity, **common, coupon_bps=contract.coupon_bps)
        delay_df = exp(-rate * contract.default_settlement_delay_years)
        protection, default_accrual = legs.protection_pv_eur * delay_df, legs.accrual_on_default_pv_eur * delay_df
        dirty = protection - legs.scheduled_premium_pv_eur - default_accrual
        values = dict(protection_pv_eur=protection, scheduled_premium_pv_eur=legs.scheduled_premium_pv_eur,
                      accrual_on_default_pv_eur=default_accrual, dirty_pv_eur=side * dirty,
                      clean_pv_eur=side * (dirty + contract.nominal_eur * coupon_rate * accrued))
    return CreditMcReference(method=method, trigger_probability=1 - member.curve.survival_at(maturity), **values)


def _count_distribution(probabilities: np.ndarray) -> np.ndarray:
    """Poisson-binomial mass conditional on each common-factor quadrature node."""
    nodes, count = probabilities.shape
    mass = np.zeros((nodes, count + 1))
    mass[:, 0] = 1.0
    for index, event in enumerate(probabilities.T, start=1):
        mass[:, 1:index + 1] = mass[:, 1:index + 1] * (1 - event[:, None]) + mass[:, :index] * event[:, None]
        mass[:, 0] *= 1 - event
    return mass


@dataclass(frozen=True)
class _BasketReference:
    segments: tuple[_HazardSegments, ...]
    loadings: np.ndarray
    nodes: np.ndarray
    weights: np.ndarray

    @classmethod
    def factor_model(cls, segments: tuple[_HazardSegments, ...], loadings: np.ndarray, order: int) -> _BasketReference:
        if not np.any(loadings):
            return cls(segments, loadings, np.zeros(1), np.ones(1))
        nodes, weights = roots_hermitenorm(order)
        return cls(segments, loadings, nodes, weights / sqrt(2 * pi))

    def conditional(self, time: float) -> tuple[np.ndarray, np.ndarray]:
        distribution = np.asarray([segment.default_distribution(time) for segment in self.segments])
        probability, density = distribution.T
        scale = np.sqrt(1 - self.loadings**2)
        with np.errstate(invalid="ignore", over="ignore"):
            quantile = ndtri(probability)
            normal = (quantile - self.nodes[:, None] * self.loadings) / scale
            derivative = density / scale * np.exp((quantile**2 - normal**2) / 2)
        derivative[:, (probability == 0) | (probability == 1)] = 0
        return ndtr(normal), derivative

    def counts(self, time: float) -> np.ndarray:
        probabilities, _ = self.conditional(time)
        return self.weights @ _count_distribution(probabilities)

    def trigger_density(self, time: float, rank: int) -> np.ndarray:
        probabilities, derivative = self.conditional(time)
        nodes, names = probabilities.shape
        prefix = np.zeros((nodes, names + 1, rank))
        suffix = np.zeros_like(prefix)
        prefix[:, 0, 0] = suffix[:, -1, 0] = 1.0

        def advance(mass, event):
            next_mass = mass * (1 - event[:, None])
            next_mass[:, 1:] += mass[:, :-1] * event[:, None]
            return next_mass

        for name in range(names):
            prefix[:, name + 1] = advance(prefix[:, name], probabilities[:, name])
            tail = names - 1 - name
            suffix[:, tail] = advance(suffix[:, tail + 1], probabilities[:, tail])

        rank_before = np.sum(prefix[:, :-1] * suffix[:, 1:, ::-1], axis=2)
        return self.weights @ (rank_before * derivative)


def _basket_reference(request: CreditMcRequest, model: _BasketReference, members: tuple[CreditMcMarginal, ...],
                      times: tuple[float, ...]) -> tuple[CreditMcReference, dict[float, float], np.ndarray]:
    contract = request.contract
    rank, rate, nominal = contract.trigger_rank, _discount(request), contract.nominal_eur
    coupon_rate, maturity = contract.coupon_bps / 10_000, contract.maturity_years
    survival = {time: _probability(sum(model.counts(time)[:rank])) for time in times}
    terminal_counts = model.counts(maturity)
    regular = nominal * coupon_rate * sum(
        period.year_fraction * survival[period.survival_time] * exp(-rate * period.payment) for period in contract.coupons
    )
    grid = sorted({contract.protected_from, maturity,
                   *(knot for member in members for knot in member.curve.maturities if contract.protected_from < knot < maturity),
                   *(edge for coupon in contract.coupons for edge in (coupon.start, coupon.end)
                     if contract.protected_from < edge < maturity)})
    lgd = 1 - np.asarray([member.recovery_fraction for member in members])
    protection, accrued, error = 0.0, 0.0, 0.0
    for start, end in zip(grid, grid[1:]):
        middle = (start + end) / 2
        period = next((coupon for coupon in contract.coupons if coupon.start <= middle < coupon.end), None)

        def integrand(time):
            density = model.trigger_density(time, rank)
            df = exp(-rate * (time + contract.default_settlement_delay_years))
            fraction = 0.0 if period is None else period.year_fraction * (time - period.start) / (period.end - period.start)
            return nominal * df * np.array([density @ lgd, coupon_rate * fraction * sum(density)])

        integrals, budget = quad_vec(integrand, start, end, epsabs=1e-5, epsrel=1e-9)
        protection += integrals[0]
        accrued += integrals[1]
        error += budget
    dirty = protection - regular - accrued
    legs = CreditMcReference(
        method="gaussian_factor_quadrature" if np.any(model.loadings) else "independent_poisson_binomial",
        protection_pv_eur=protection, scheduled_premium_pv_eur=regular, accrual_on_default_pv_eur=accrued,
        clean_pv_eur=_side(contract) * (dirty + nominal * coupon_rate * contract.initial_accrued_fraction),
        dirty_pv_eur=_side(contract) * dirty, trigger_probability=_probability(1 - survival[maturity]),
        quadrature_error_estimate_eur=error,
    )
    return legs, survival, terminal_counts


def _probability(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _reference(request: CreditMcRequest, segments: tuple[_HazardSegments, ...], members: tuple[CreditMcMarginal, ...],
               times: tuple[float, ...]) -> tuple[CreditMcReference, dict[float, float], np.ndarray]:
    contract = request.contract
    perfect = _perfect_dependence(members)
    if len(members) == 1 or perfect:
        member = members[(contract.trigger_rank or 1) - 1]
        method = "perfect_dependence_limit" if perfect and len(members) > 1 else "lot3_analytical"
        reference = _single_name_reference(request, member, method)
        survival = {time: member.curve.survival_at(time) for time in times}
        terminal_counts = np.zeros(len(members) + 1)
        terminal_counts[0], terminal_counts[-1] = 1 - reference.trigger_probability, reference.trigger_probability
        return reference, survival, terminal_counts
    loadings = np.asarray([member.loading for member in members])
    model = _BasketReference.factor_model(segments, loadings, 64)
    reference, survival, terminal_counts = _basket_reference(request, model, members, times)
    if np.any(loadings):
        coarse, _, _ = _basket_reference(request, _BasketReference.factor_model(segments, loadings, 32), members, times)
        errors = [abs(reference.dirty_pv_eur - coarse.dirty_pv_eur),
                  abs(reference.protection_pv_eur - coarse.protection_pv_eur),
                  abs(reference.scheduled_premium_pv_eur - coarse.scheduled_premium_pv_eur),
                  abs(reference.accrual_on_default_pv_eur - coarse.accrual_on_default_pv_eur)]
        reference = reference.model_copy(update={"quadrature_error_estimate_eur": (
            reference.quadrature_error_estimate_eur + coarse.quadrature_error_estimate_eur + max(errors)
        )})
    return reference, survival, terminal_counts


@dataclass
class _RunningStatistic:
    size: int = 0
    mean: float = 0.0
    sum_squares: float = 0.0

    def add(self, sample: np.ndarray) -> None:
        old_size = self.size
        self.size += len(sample)
        mean = float(np.mean(sample))
        if np.all(sample == sample[0]):
            mean = float(sample[0])
        difference = mean - self.mean
        self.mean += difference * len(sample) / self.size
        self.sum_squares += float(np.sum((sample - mean)**2)) + difference**2 * old_size * len(sample) / self.size

    def finish(self) -> CreditMcStatistic:
        standard_error = sqrt(self.sum_squares / (self.size * (self.size - 1)))
        return CreditMcStatistic(mean=self.mean, standard_error=standard_error, ci95_half_width=_Z95 * standard_error)


@dataclass(frozen=True)
class CreditMcSimulation:
    result: CreditMcResult
    dirty_samples: np.ndarray | None = None
    draw_fingerprint: str | None = None


def _provenance(request: CreditMcRequest, members: tuple[CreditMcMarginal, ...]) -> CreditMcProvenance:
    active = request.realized is None
    loadings = np.asarray([member.loading for member in members])
    correlation = np.outer(loadings, loadings)
    np.fill_diagonal(correlation, 1.0)
    order = tuple(member.reference_entity_id for member in members)
    state_policy = "initial_all_names_alive" if request.contract.kind == "basket_cds" else "single_name_survivor_curve"
    return CreditMcProvenance(
        request_fingerprint=json_transport_fingerprint(request.model_dump(mode="json")),
        market_fingerprint=json_transport_fingerprint(request.market.model_dump(mode="json")),
        state_fingerprint=request.realized.context.fingerprint if not active else None,
        state_policy=state_policy if active else "resolved_lot3_facts",
        sampler="numpy.PCG64" if active else None, estimator=request.settings.estimator if active else None,
        seed=request.settings.seed if active else None, numpy_version=np.__version__, scipy_version=scipy.__version__,
        independent_samples=request.settings.paths if active else 0,
        stream_partition="independent_rows_names_sorted_by_reference_entity_id", member_order=order,
        dependence_model=request.market.dependence_model if active else None,
        gaussian_asset_correlation=tuple(tuple(row) for row in correlation) if active else (),
    )


def _realized_result(request: CreditMcRequest, provenance: CreditMcProvenance) -> CreditMcResult:
    contract, market = request.contract, request.market
    product, context = request.realized.product, request.realized.context
    terms = product.terms
    if not isinstance(terms, (CDSTerms, CLNTerms)) or terms.instrument_type.lower() != contract.kind:
        raise CreditMcError("CREDIT_MC_REALIZED_TERMS", "L’état réalisé exige le Product CDS ou CLN correspondant.")
    if isinstance(terms, CDSTerms):
        coupon_bps = terms.premium_leg.coupon_bps
    else:
        coupon = terms.fixed_leg.coupon_rate
        coupon_bps = coupon * 10_000 if coupon is not None else None
    if (context.facts.state == "alive" or terms.reference_entity_id != market.marginals[0].reference_entity_id
            or product.intent.nominal != contract.nominal_eur or product.intent.side != contract.side
            or coupon_bps is None or abs(coupon_bps - contract.coupon_bps) > 1e-9
            or context.discount.ois_rate != market.discount_rate
            or context.discount.cln_funding_bps != market.funding_bps):
        raise CreditMcError("CREDIT_MC_REALIZED_TERMS", "L’état réalisé ne correspond pas aux termes et au marché du calcul.")
    result = price_credit_default(product, context)
    return CreditMcResult(
        state=result.state, nominal_eur=contract.nominal_eur, realized=result, provenance=provenance,
    )


def _draw_default_times(generator: np.random.Generator, size: int, segments: tuple[_HazardSegments, ...],
                        loadings: np.ndarray, conditional: bool, default_probability: float) -> np.ndarray:
    if conditional:
        thresholds = -np.log1p(-default_probability * generator.random(size))
        return segments[0].inverse(thresholds)[:, None]
    normals = generator.standard_normal((size, len(segments) + 1))
    scores = normals[:, :1] * loadings + normals[:, 1:] * np.sqrt(1 - loadings**2)
    thresholds = -log_ndtr(-scores)
    return np.column_stack([segment.inverse(thresholds[:, i]) for i, segment in enumerate(segments)])


def resolve_credit_payoff(request: CreditMcRequest) -> tuple[CreditMcRequest, CreditPayoffEvidence | None]:
    """Translate the bounded script into amounts for the existing MC and references."""
    script = request.contract.payscript
    if script is None:
        return request, None
    if request.realized is not None:
        raise CreditMcError("CREDIT_MC_SCRIPT_STATE", "Le PayScript crédit n’est pas qualifié après un défaut constaté.")
    contract, market = request.contract, request.market
    cln = contract.kind == "cln"
    rate, coupon = credit_coupon_rate(script, cln=cln, native_rate=contract.coupon_bps / 10_000)
    names = tuple(sorted(market.marginals, key=lambda member: member.reference_entity_id))
    recoveries = np.asarray([name.recovery_fraction for name in names])
    amounts, default = credit_default_amounts(script, cln=cln, recovery=recoveries, rank=contract.trigger_rank or 1)
    evidence = CreditPayoffEvidence(
        coupon=coupon, default=default, effective_coupon_rate=rate,
        member_amounts=tuple(CreditScriptMemberAmount(
            reference_entity_id=name.reference_entity_id, recovery_fraction=name.recovery_fraction, payout_fraction=amount,
        ) for name, amount in zip(names, amounts, strict=True)),
    )
    # The model still draws defaults from the original survival marginals.
    # Only the payment coefficient consumed by the cashflow and reference
    # functions changes. The signed receipt retains the original market.
    effective_members = names if default is None else tuple(
        name.model_copy(update={"recovery_fraction": float(amount if cln else 1.0 - amount)})
        for name, amount in zip(names, amounts, strict=True)
    )
    effective_contract = contract.model_copy(update={
        "coupon_bps": rate * 10_000 if coupon is not None else contract.coupon_bps, "payscript": None,
    })
    return request.model_copy(update={
        "contract": effective_contract, "market": market.model_copy(update={"marginals": effective_members}),
    }), evidence


def simulate_credit_mc(request: CreditMcRequest, *, retain_samples: bool = False) -> CreditMcSimulation:
    """Run the synthetic MC or use a realized Lot 3 calculation with no sampling."""
    settings, contract = request.settings, request.contract
    members = tuple(sorted(request.market.marginals, key=lambda member: member.reference_entity_id))
    provenance = _provenance(request, members)
    request, script_evidence = resolve_credit_payoff(request)
    if request.realized is not None:
        return CreditMcSimulation(_realized_result(request, provenance))
    if script_evidence is not None:
        settings, contract, members = request.settings, request.contract, request.market.marginals

    maturity = contract.maturity_years
    segments = tuple(_HazardSegments.from_curve(member.curve, maturity) for member in members)
    loadings = np.asarray([member.loading for member in members])
    recoveries = np.asarray([member.recovery_fraction for member in members])
    times = tuple(sorted({*(coupon.survival_time for coupon in contract.coupons), maturity}))
    reference, reference_survival, reference_counts = _reference(request, segments, members, times)
    if script_evidence is not None:
        reference = reference.model_copy(update={"payoff_basis": "payscript_effective_amounts"})
    conditional = settings.estimator == "conditional_single_name"
    default_probability = segments[0].default_distribution(maturity)[0]
    base, _, _ = _paths(request, np.full((1, len(members)), np.inf), recoveries)
    generator = np.random.Generator(np.random.PCG64(settings.seed))
    estimates = {key: _RunningStatistic() for key in base}
    surviving = [_RunningStatistic() for _ in times]
    default_counts = [_RunningStatistic() for _ in range(len(members) + 1)]
    retain = np.empty(settings.paths) if retain_samples else None

    def mix(sample, survivor_value):
        if not conditional:
            return sample
        return survivor_value + default_probability * (sample.astype(float) - survivor_value)

    for start in range(0, settings.paths, _CHUNK):
        end = min(settings.paths, start + _CHUNK)
        defaults = _draw_default_times(generator, end - start, segments, loadings, conditional, default_probability)
        metrics, trigger, counts = _paths(request, defaults, recoveries)
        for key, sample in metrics.items():
            values = mix(sample, float(base[key][0]))
            estimates[key].add(values)
            if retain is not None and key == "dirty_pv_eur":
                retain[start:end] = values
        for time, stat in zip(times, surviving, strict=True):
            stat.add(mix(trigger > time, 1.0))
        for count, stat in enumerate(default_counts):
            stat.add(mix(counts == count, 1.0 if count == 0 else 0.0))

    draw_fingerprint = json_transport_fingerprint({
        "sampler": provenance.sampler, "numpy_version": provenance.numpy_version,
        "seed": settings.seed, "paths": settings.paths, "estimator": settings.estimator,
        "stream_partition": provenance.stream_partition, "member_order": provenance.member_order,
        "block_size": _CHUNK,
    })
    result = CreditMcResult(
        state="alive", nominal_eur=contract.nominal_eur,
        estimate=CreditMcEstimate(**{key: value.finish() for key, value in estimates.items()}),
        reference=reference, provenance=provenance.model_copy(update={"draw_fingerprint": draw_fingerprint}),
        payscript_metadata=script_evidence,
        survival=tuple(CreditMcSurvival(time_years=time, estimate=stat.finish(), reference=reference_survival[time])
                       for time, stat in zip(times, surviving, strict=True)),
        default_count_at_maturity=tuple(CreditMcFrequency(defaults_at_maturity=count, estimate=stat.finish(),
                                                          reference=_probability(reference_counts[count]))
                                        for count, stat in enumerate(default_counts)),
    )
    dirty_samples = np.frombuffer(retain.tobytes(), dtype=np.float64) if retain is not None else None
    return CreditMcSimulation(result, dirty_samples, draw_fingerprint)


def price_credit_mc(request: CreditMcRequest) -> CreditMcResult:
    return simulate_credit_mc(request).result
