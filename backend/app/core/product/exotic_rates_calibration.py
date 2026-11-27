"""Synthetic Hull–White 1F calibration to physical European EUR swaptions."""

from dataclasses import dataclass
from functools import lru_cache
from math import exp, fsum, log, pi, sqrt
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import ndtr

from ..payscript.rates import _ou_transition
from ..valuation_context import canonical_fingerprint
from .exotic_rates_mc import HwCurve, HwMarket, RatesMCError, SwapRate, _bond_loading
from .models import FrozenModel


_CALIBRATION_VERSION = "eur-hw1f-synthetic-physical-swaption-v1"
_NORMALIZER = sqrt(2 * pi)
_TAIL = 12.0
_FIT_GRID_SIZE = 17
Identifier = Annotated[str, Field(min_length=1, max_length=160)]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]


class HullWhiteCalibrationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NormalSwaptionQuote(FrozenModel):
    kind: Literal["normal"] = "normal"
    volatility: Nonnegative


class ShiftedBlackSwaptionQuote(FrozenModel):
    kind: Literal["shifted_lognormal"] = "shifted_lognormal"
    volatility: Nonnegative
    shift: float


class PVSwaptionQuote(FrozenModel):
    kind: Literal["pv"] = "pv"
    pv_eur: Nonnegative


SwaptionQuote = Annotated[NormalSwaptionQuote | ShiftedBlackSwaptionQuote | PVSwaptionQuote, Field(discriminator="kind")]


class SwaptionCalibrationPoint(FrozenModel):
    quote_id: Identifier
    expiry: Positive
    swap: SwapRate
    side: Literal["payer", "receiver"]
    settlement: Literal["physical"] = "physical"
    strike: float
    nominal_eur: Positive
    role: Literal["calibration", "validation"]
    weight: Positive = 1.0
    quote: SwaptionQuote

    @model_validator(mode="after")
    def verify_swap_start(self):
        if self.swap.floating_periods[0].start < self.expiry:
            raise ValueError("Le swap d’une swaption physique ne peut démarrer avant l’exercice.")
        return self


class HullWhiteCalibrationRequest(FrozenModel):
    discount: HwCurve
    projection: HwCurve
    mean_reversion: Nonnegative
    volatility_upper_bound: Annotated[float, Field(gt=0, le=.25)] = .05
    dataset_id: Identifier
    quality: Literal["synthetic"] = "synthetic"
    quotes: tuple[SwaptionCalibrationPoint, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def verify_quotes(self):
        if len({point.quote_id for point in self.quotes}) != len(self.quotes):
            raise ValueError("Les identifiants des cotes de swaption doivent être uniques.")
        if not any(point.role == "calibration" for point in self.quotes):
            raise ValueError("Au moins une cote d’ajustement est requise.")
        return self


class SwaptionCalibrationResidual(FrozenModel):
    quote_id: str
    role: Literal["calibration", "validation"]
    quote: SwaptionQuote
    settlement: Literal["physical"] = "physical"
    side: Literal["payer", "receiver"]
    expiry: float
    underlier_start: float
    underlier_maturity: float
    strike: float
    nominal_eur: float
    weight: float
    forward_swap_rate: float
    annuity_per_eur: Positive
    market_pv_eur: Nonnegative
    model_pv_eur: Nonnegative
    residual_eur: float
    residual_eur_per_100: float


class HullWhiteCalibrationResult(FrozenModel):
    schema_version: Literal[1] = 1
    engine_version: Literal["eur-hw1f-synthetic-physical-swaption-v1"] = _CALIBRATION_VERSION
    method: Literal["fixed_mean_reversion_weighted_pv"] = "fixed_mean_reversion_weighted_pv"
    quality: Literal["synthetic"] = "synthetic"
    volatility_unit: Literal["decimal_per_sqrt_year"] = "decimal_per_sqrt_year"
    time_basis: Literal["ACT/365F"] = "ACT/365F"
    currency: Literal["EUR"] = "EUR"
    dataset_id: str
    request_fingerprint: str
    market: HwMarket
    volatility_upper_bound: float
    volatility_at_bound: Literal["lower", "upper"] | None
    calibration_rmse_eur_per_100: Nonnegative
    validation_rmse_eur_per_100: Nonnegative | None
    residuals: tuple[SwaptionCalibrationResidual, ...]


@dataclass(frozen=True)
class _SwaptionBasis:
    point: SwaptionCalibrationPoint
    annuity: float
    forward: float
    market_pv: float
    signed_discounted_amounts: np.ndarray
    loadings: np.ndarray


def _quote_pv(point: SwaptionCalibrationPoint, forward: float, annuity: float) -> float:
    quote = point.quote
    direction = 1 if point.side == "payer" else -1
    moneyness = direction * (forward - point.strike)
    intrinsic = max(moneyness, 0.0) * point.nominal_eur * annuity
    if isinstance(quote, PVSwaptionQuote):
        if quote.pv_eur < intrinsic - max(1e-8, 1e-12 * intrinsic):
            raise HullWhiteCalibrationError(
                "MC_CALIBRATION_BELOW_INTRINSIC", f"La cote {point.quote_id} est sous sa valeur intrinsèque.",
            )
        return quote.pv_eur
    total_volatility = quote.volatility * sqrt(point.expiry)
    if isinstance(quote, NormalSwaptionQuote):
        if total_volatility == 0:
            return intrinsic
        d = moneyness / total_volatility
        value = moneyness * ndtr(d) + total_volatility * exp(-.5 * d*d) / _NORMALIZER
    else:
        shifted_forward, shifted_strike = forward + quote.shift, point.strike + quote.shift
        if min(shifted_forward, shifted_strike) <= 0:
            raise HullWhiteCalibrationError(
                "MC_CALIBRATION_BLACK_DOMAIN",
                f"Le forward et le strike décalés de la cote {point.quote_id} doivent être strictement positifs.",
            )
        if total_volatility == 0:
            return intrinsic
        d1 = (log(shifted_forward) - log(shifted_strike)) / total_volatility + .5 * total_volatility
        d2 = d1 - total_volatility
        value = direction * (shifted_forward * ndtr(direction * d1) - shifted_strike * ndtr(direction * d2))
    return max(0.0, point.nominal_eur * annuity * value)


def _build_basis(request: HullWhiteCalibrationRequest, point: SwaptionCalibrationPoint) -> _SwaptionBasis:
    discount, projection = request.discount, request.projection
    amounts: dict[float, list[float]] = {}
    annuity_terms = []
    floating_terms = []
    try:
        for period in point.swap.floating_periods:
            start, end = period.start, period.end
            start_ois, end_ois = discount.log_factor(start), discount.log_factor(end)
            projected_ratio = projection.log_factor(start) - projection.log_factor(end)
            # Delta cancels: P_d(t,end) * delta * L_p(t;start,end)
            # = basis(start)/basis(end) * P_d(t,start) - P_d(t,end).
            discounted_start = exp(projected_ratio + end_ois)
            discounted_end = exp(end_ois)
            floating_terms.append(discounted_start - discounted_end)
            amounts.setdefault(start, []).append(discounted_start)
            amounts.setdefault(end, []).append(-discounted_end)
        for period in point.swap.fixed_periods:
            fixed = period.year_fraction * exp(discount.log_factor(period.payment))
            annuity_terms.append(fixed)
            amounts.setdefault(period.payment, []).append(-point.strike * fixed)
        discount.log_factor(point.expiry)
    except RatesMCError as exc:
        raise HullWhiteCalibrationError(
            "MC_CALIBRATION_CURVE_COVERAGE", f"La cote {point.quote_id} exige une couverture jusqu’au dernier flux. {exc}",
        ) from exc
    annuity, floating = fsum(annuity_terms), fsum(floating_terms)
    if annuity <= 0:
        raise HullWhiteCalibrationError("MC_CALIBRATION_NUMERICAL_DOMAIN", f"L’annuité de {point.quote_id} est hors domaine.")
    direction = 1 if point.side == "payer" else -1
    times = sorted(amounts)
    discounted = np.array([direction * fsum(amounts[time]) for time in times])
    loadings = np.array([_bond_loading(request.mean_reversion, time - point.expiry) for time in times])
    forward = floating / annuity
    return _SwaptionBasis(point, annuity, forward, _quote_pv(point, forward, annuity), discounted, loadings)


def _hull_white_pv(basis: _SwaptionBasis, a: float, sigma: float) -> float:
    _, state_sd = _ou_transition(sigma, a, basis.point.expiry)
    amounts = basis.signed_discounted_amounts
    if state_sd == 0:
        return basis.point.nominal_eur * max(0.0, fsum(amounts))

    # Under the expiry-forward measure, the normalized moments of each OIS zero
    # are exp(-loading * Z - loading**2/2). Absorb the normal density directly,
    # so the quadrature uses shifted density kernels and retains the Gaussian tails.
    loadings = basis.loadings * state_sd
    max_loading = loadings[-1]
    if not np.isfinite(max_loading) or max_loading > 50:
        raise HullWhiteCalibrationError(
            "MC_CALIBRATION_NUMERICAL_DOMAIN", f"La volatilité et le tenor de {basis.point.quote_id} excèdent le domaine de quadrature.",
        )

    def density_weighted_payoff(z: float) -> float:
        return max(0.0, float(amounts @ np.exp(-.5 * (z + loadings)**2))) / _NORMALIZER

    # Split the initial partition near the Gaussian mass to resolve narrow tails
    # as well as the kink in the positive part, with no monotonic payoff assumption.
    breaks = np.linspace(-_TAIL - max_loading, _TAIL, 17)
    value, error = quad(
        density_weighted_payoff, breaks[0], breaks[-1], points=breaks[1:-1],
        epsabs=1e-13, epsrel=1e-10, limit=160,
    )
    if error > max(1e-12, abs(value) * 1e-8):
        raise HullWhiteCalibrationError(
            "MC_CALIBRATION_QUADRATURE", f"La quadrature de la cote {basis.point.quote_id} manque de précision.",
        )
    return value * basis.point.nominal_eur


def _weighted_rmse(residuals: tuple[SwaptionCalibrationResidual, ...], role: str) -> float | None:
    selected = [point for point in residuals if point.role == role]
    if not selected:
        return None
    return sqrt(fsum(row.weight * row.residual_eur_per_100**2 for row in selected) /
                fsum(row.weight for row in selected))


def calibrate_hull_white(request: HullWhiteCalibrationRequest) -> HullWhiteCalibrationResult:
    """Fit a constant short-rate volatility in PV per 100 with fixed mean reversion."""
    a, cap = request.mean_reversion, request.volatility_upper_bound
    try:
        bases = tuple(_build_basis(request, quote) for quote in request.quotes)
        calibration = tuple(basis for basis in bases if basis.point.role == "calibration")
        normalizations = [100 / basis.point.nominal_eur for basis in calibration]

        @lru_cache(maxsize=256)
        def prices(volatility: float) -> tuple[float, ...]:
            return tuple(_hull_white_pv(basis, a, volatility) for basis in calibration)

        if not any(abs(top - bottom) * scale > 1e-10
                   for top, bottom, scale in zip(prices(cap), prices(0.), normalizations, strict=True)):
            raise HullWhiteCalibrationError("MC_CALIBRATION_UNIDENTIFIED", "Les cotes d’ajustement n’identifient pas la volatilité.")

        def objective(volatility: float) -> float:
            return fsum(basis.point.weight * ((pv - basis.market_pv) * scale)**2
                        for basis, pv, scale in zip(calibration, prices(volatility), normalizations, strict=True))

        grid = np.linspace(0, cap, _FIT_GRID_SIZE).tolist()
        scores = [objective(volatility) for volatility in grid]
        candidates = [(scores[0], grid[0]), (scores[-1], grid[-1])]
        for i in range(1, len(grid) - 1):
            if scores[i] <= min(scores[i - 1], scores[i + 1]) and scores[i] < max(scores[i - 1], scores[i + 1]):
                fit = minimize_scalar(objective, method="bounded", bounds=(grid[i - 1], grid[i + 1]),
                                      options={"xatol": 1e-11, "maxiter": 80})
                if not fit.success:
                    raise HullWhiteCalibrationError("MC_CALIBRATION_FIT", "La recherche de volatilité n’a pas convergé.")
                candidates.append((fit.fun, fit.x))
        # Search edge intervals too: a minimum close to either bound can lie before the first grid point.
        for first, last in ((0, 1), (-2, -1)):
            fit = minimize_scalar(objective, method="bounded", bounds=(grid[first], grid[last]),
                                  options={"xatol": 1e-11, "maxiter": 80})
            if not fit.success:
                raise HullWhiteCalibrationError("MC_CALIBRATION_FIT", "La recherche de volatilité n’a pas convergé.")
            candidates.append((fit.fun, fit.x))
        _, volatility = min(candidates)

        residuals = []
        for basis in bases:
            point = basis.point
            model_pv = _hull_white_pv(basis, a, volatility)
            mismatch = model_pv - basis.market_pv
            residuals.append(SwaptionCalibrationResidual(
                quote_id=point.quote_id, role=point.role, quote=point.quote, side=point.side, expiry=point.expiry,
                underlier_start=point.swap.floating_periods[0].start, underlier_maturity=point.swap.floating_periods[-1].end,
                strike=point.strike, nominal_eur=point.nominal_eur, weight=point.weight, forward_swap_rate=basis.forward,
                annuity_per_eur=basis.annuity, market_pv_eur=basis.market_pv, model_pv_eur=model_pv,
                residual_eur=mismatch, residual_eur_per_100=mismatch / point.nominal_eur * 100,
            ))
        rows = tuple(residuals)
        return HullWhiteCalibrationResult(
            dataset_id=request.dataset_id, request_fingerprint=canonical_fingerprint(request.model_dump(mode="json")),
            market=HwMarket(discount=request.discount, projection=request.projection, mean_reversion=a,
                            volatility=volatility, funding_bps=0.0),
            volatility_upper_bound=cap, volatility_at_bound="lower" if volatility == 0 else "upper" if volatility == cap else None,
            calibration_rmse_eur_per_100=_weighted_rmse(rows, "calibration"),
            validation_rmse_eur_per_100=_weighted_rmse(rows, "validation"), residuals=rows,
        )
    except ArithmeticError as exc:
        raise HullWhiteCalibrationError("MC_CALIBRATION_NUMERICAL_DOMAIN", "La calibration sort du domaine numérique.") from exc
