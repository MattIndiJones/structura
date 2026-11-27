"""Deterministic credit integration and sequential survival calibration."""
from __future__ import annotations

from bisect import bisect_left
from math import ceil, exp, expm1, fsum
from typing import Literal

from pydantic import Field, model_validator
from scipy.optimize import brentq

from .models import FrozenModel


class CreditPricingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CreditQuote(FrozenModel):
    maturity_years: float = Field(gt=0, le=30)
    kind: Literal["par_spread", "clean_upfront", "quoted_spread"]
    value: float
    standard_coupon_bps: float = Field(default=100.0, ge=0)

    @model_validator(mode="after")
    def check_units(self):
        if self.kind == "clean_upfront" and not -1 < self.value < 1:
            raise ValueError("L’upfront clean doit être exprimé en fraction du nominal.")
        if self.kind != "clean_upfront" and not 0 <= self.value <= 10_000:
            raise ValueError("Le spread du CDS doit être exprimé en points de base.")
        return self


class SurvivalPillar(FrozenModel):
    maturity_years: float
    source_quote: float
    source_unit: Literal["bp", "fraction"]
    source_kind: Literal["par_spread", "clean_upfront", "quoted_spread"]
    normalized_coupon_bps: float
    normalized_upfront_fraction: float
    hazard_rate: float = Field(ge=0)
    survival: float = Field(ge=0, le=1)
    reprice_error_eur: float


class SurvivalCurve(FrozenModel):
    maturities: tuple[float, ...] = Field(min_length=1)
    hazards: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_grid(self):
        if (len(self.maturities) != len(self.hazards) or self.maturities[0] <= 0
                or any(a >= b for a, b in zip(self.maturities, self.maturities[1:]))
                or any(hazard < 0 for hazard in self.hazards)):
            raise CreditPricingError("CREDIT_CURVE_INVALID", "Les échéances doivent être croissantes et les intensités positives ou nulles.")
        return self

    def survival_at(self, year: float) -> float:
        if not 0 <= year <= self.maturities[-1] + 1e-12:
            raise CreditPricingError("CREDIT_CURVE_COVERAGE", "La courbe de survie ne couvre pas la durée du produit.")
        previous = 0.0
        terms = []
        for end, hazard in zip(self.maturities, self.hazards):
            terms.append((min(year, end) - previous) * hazard)
            if year <= end:
                break
            previous = end
        return exp(-fsum(terms))


class CreditCalibration(FrozenModel):
    discount_rate: float
    calibration_recovery_fraction: float
    curve: SurvivalCurve
    pillars: tuple[SurvivalPillar, ...]


class CreditCoupon(FrozenModel):
    start: float
    end: float
    payment: float
    year_fraction: float = Field(gt=0)
    observation: float | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if not self.start < self.end or self.end <= 0 or not 0 <= self.survival_time <= self.payment:
            raise ValueError("Les bornes de la prime doivent précéder sa date de paiement.")
        return self

    @property
    def survival_time(self) -> float:
        return self.end if self.observation is None else self.observation


def quarterly_coupons(maturity: float) -> tuple[CreditCoupon, ...]:
    return tuple(CreditCoupon(start=start, end=end, payment=end, year_fraction=end - start)
                 for i in range(ceil(maturity * 4))
                 for start, end in ((i / 4, min((i + 1) / 4, maturity)),))


def _moments(k: float, width: float) -> tuple[float, float]:
    """Integrals of exp(-kx) and x exp(-kx), stable for a zero combined rate."""
    x = k * width
    if abs(x) < 1e-4:
        return (width * (1 - x / 2 + x*x / 6 - x**3 / 24 + x**4 / 120),
                width * width * (1 / 2 - x / 3 + x*x / 8 - x**3 / 30 + x**4 / 144))
    return -expm1(-x) / k, (-expm1(-x) - x * exp(-x)) / (k*k)


def default_integral(curve: SurvivalCurve, discount: float, start: float, end: float,
                     *, accrual_start: float | None = None) -> float:
    if not 0 <= start <= end:
        raise CreditPricingError("CREDIT_DATES_INVALID", "L’intégration du défaut exige des bornes de protection ordonnées.")
    curve.survival_at(end)
    grid = [start, *(t for t in curve.maturities if start < t < end), end]
    contributions = []
    for left, right in zip(grid, grid[1:]):
        if right <= left:
            continue
        hazard = curve.hazards[bisect_left(curve.maturities, (left + right) / 2)]
        zeroth, first = _moments(discount + hazard, right - left)
        weight = hazard * curve.survival_at(left) * exp(-discount * left)
        contributions.append(weight * (zeroth if accrual_start is None else (left - accrual_start) * zeroth + first))
    return fsum(contributions)


class CdsLegs(FrozenModel):
    protection_pv_eur: float
    scheduled_premium_pv_eur: float
    accrual_on_default_pv_eur: float
    clean_pv_eur: float
    dirty_pv_eur: float
    par_spread_bps: float | None
    coupon_pvs_eur: tuple[float, ...]


def value_cds(curve: SurvivalCurve, discount: float, maturity: float, *, nominal: float,
              coupon_bps: float, recovery: float, coupons: tuple[CreditCoupon, ...] | None = None,
              protected_from: float = 0.0, initial_accrued_fraction: float = 0.0) -> CdsLegs:
    coupons = quarterly_coupons(maturity) if coupons is None else coupons
    premiums = tuple(p.year_fraction * curve.survival_at(p.survival_time) * exp(-discount * p.payment) for p in coupons)
    accrual = fsum((p.year_fraction / (p.end - p.start)) * default_integral(
        curve, discount, max(p.start, protected_from), min(p.end, maturity), accrual_start=p.start,
    ) for p in coupons if min(p.end, maturity) > max(p.start, protected_from))
    protection = (1 - recovery) * default_integral(curve, discount, protected_from, maturity)
    coupon = coupon_bps / 10_000
    clean_annuity = fsum(premiums) + accrual - initial_accrued_fraction
    clean = protection - coupon * clean_annuity
    return CdsLegs(protection_pv_eur=protection * nominal,
                   scheduled_premium_pv_eur=fsum(premiums) * coupon * nominal,
                   accrual_on_default_pv_eur=accrual * coupon * nominal,
                   clean_pv_eur=clean * nominal, dirty_pv_eur=(clean - coupon * initial_accrued_fraction) * nominal,
                   par_spread_bps=10_000 * protection / clean_annuity if clean_annuity > 0 else None,
                   coupon_pvs_eur=tuple(nominal * coupon * pv for pv in premiums))


def _solve_interval(maturities: tuple[float, ...], previous: tuple[float, ...], *, discount: float,
                    recovery: float, coupon_bps: float, upfront: float) -> float:
    def residual(hazard: float) -> float:
        legs = value_cds(SurvivalCurve(maturities=maturities, hazards=(*previous, hazard)),
                         discount, maturities[-1], nominal=1, coupon_bps=coupon_bps, recovery=recovery)
        return legs.clean_pv_eur - upfront

    low = residual(0.0)
    if abs(low) <= 1e-14:
        return 0.0
    high = 1.0
    while high < 1024 and residual(high) * low > 0:
        high *= 2
    if residual(high) * low > 0:
        raise CreditPricingError("CREDIT_NO_ADMISSIBLE_ROOT", "La cote ne permet pas une intensité positive ou nulle sur cet intervalle.")
    return brentq(residual, 0, high, xtol=1e-14)


def calibrate_survival(quotes: tuple[CreditQuote, ...], *, discount: float, recovery: float,
                       reference_nominal: float = 10_000_000) -> CreditCalibration:
    maturities = tuple(quote.maturity_years for quote in quotes)
    if not quotes or any(left >= right for left, right in zip(maturities, maturities[1:])):
        raise CreditPricingError("CREDIT_QUOTE_ORDER", "Les échéances des cotes doivent être uniques et croissantes.")
    if not -1 <= discount <= 1 or not 0 <= recovery < 1 or reference_nominal <= 0:
        raise CreditPricingError("CREDIT_CALIBRATION_INPUT", "Vérifiez le taux d’actualisation, le recouvrement de calibration et le nominal de contrôle.")
    hazards = ()
    evidence = []
    for n, quote in enumerate(quotes, start=1):
        coupon_bps, upfront = quote.standard_coupon_bps, quote.value
        if quote.kind == "par_spread":
            coupon_bps, upfront = quote.value, 0.0
        elif quote.kind == "quoted_spread":
            one = (quote.maturity_years,)
            constant = _solve_interval(one, (), discount=discount, recovery=recovery,
                                       coupon_bps=quote.value, upfront=0.0)
            upfront = value_cds(SurvivalCurve(maturities=one, hazards=(constant,)), discount, one[0],
                                nominal=1, coupon_bps=coupon_bps, recovery=recovery).clean_pv_eur
        grid = maturities[:n]
        hazard = _solve_interval(grid, hazards, discount=discount, recovery=recovery,
                                 coupon_bps=coupon_bps, upfront=upfront)
        hazards = (*hazards, hazard)
        curve = SurvivalCurve(maturities=grid, hazards=hazards)
        repriced = value_cds(curve, discount, grid[-1], nominal=reference_nominal, coupon_bps=coupon_bps, recovery=recovery)
        evidence.append(SurvivalPillar(maturity_years=grid[-1], source_quote=quote.value, source_kind=quote.kind,
                                      source_unit="fraction" if quote.kind == "clean_upfront" else "bp",
                                      normalized_coupon_bps=coupon_bps, normalized_upfront_fraction=upfront,
                                      hazard_rate=hazard, survival=curve.survival_at(grid[-1]),
                                      reprice_error_eur=repriced.clean_pv_eur - upfront * reference_nominal))
    return CreditCalibration(discount_rate=discount, calibration_recovery_fraction=recovery,
                             curve=curve, pillars=tuple(evidence))


class ClnLegs(FrozenModel):
    coupon_pv_eur: float
    survival_principal_pv_eur: float
    default_redemption_pv_eur: float
    accrued_eur: float
    dirty_pv_eur: float
    clean_pv_eur: float
    par_coupon_fraction: float | None
    coupon_pvs_eur: tuple[float, ...]


def value_cln(curve: SurvivalCurve, discount: float, maturity: float, *, nominal: float, coupon_rate: float,
              recovery: float, settlement_delay: float, funding_bps: float = 0.0,
              coupons: tuple[CreditCoupon, ...] | None = None, principal_payment: float | None = None,
              protected_from: float = 0.0, accrued_fraction: float = 0.0) -> ClnLegs:
    funding_discount = discount + funding_bps / 10_000
    coupons = quarterly_coupons(maturity) if coupons is None else coupons
    payment = maturity if principal_payment is None else principal_payment
    weights = tuple(p.year_fraction * curve.survival_at(p.survival_time) * exp(-funding_discount * p.payment) for p in coupons)
    annuity = fsum(weights)
    survival_principal = curve.survival_at(maturity) * exp(-funding_discount * payment)
    recovery_principal = recovery * exp(-funding_discount * settlement_delay) * default_integral(
        curve, funding_discount, protected_from, maturity,
    )
    dirty = nominal * (annuity * coupon_rate + survival_principal + recovery_principal)
    accrued = nominal * accrued_fraction * coupon_rate
    return ClnLegs(coupon_pv_eur=nominal * annuity * coupon_rate, survival_principal_pv_eur=nominal * survival_principal,
                   default_redemption_pv_eur=nominal * recovery_principal, accrued_eur=accrued,
                   dirty_pv_eur=dirty, clean_pv_eur=dirty - accrued,
                   par_coupon_fraction=(1 - survival_principal - recovery_principal) / annuity if annuity else None,
                   coupon_pvs_eur=tuple(nominal * coupon_rate * weight for weight in weights))
