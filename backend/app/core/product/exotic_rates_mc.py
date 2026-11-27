"""Native Hull–White 1F research pricing on a resolved, residual ACT/365F axis."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from math import exp, expm1, log, sqrt
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.special import stdtrit

from ..payscript.rates import _ou_transition
from ..valuation_context import canonical_fingerprint
from .exotic_rates_calendar import RatesContractDates
from .exotic_rates_payscript import (
    CompiledExoticRatesPayScript, ExoticRatesScript, ExoticRatesScriptMetadata, compile_exotic_rates_script,
)
from .models import FrozenModel


ENGINE_VERSION = "eur-rates-hw1f-exact-v1"
_GENERATOR = "numpy-pcg64-normal-event-major-v1"
_MAX_GRID_CELLS = 8_000_000
Nonnegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
Identifier = Annotated[str, Field(min_length=1)]


class RatesMCError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class HwCurvePillar(FrozenModel):
    time: Nonnegative
    factor: Positive


class HwCurve(FrozenModel):
    pillars: tuple[HwCurvePillar, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_pillars(self):
        if self.pillars[0].time != 0 or self.pillars[0].factor != 1:
            raise ValueError("La courbe démarre à l’arrêté avec un facteur égal à 1.")
        if any(first.time >= second.time for first, second in zip(self.pillars, self.pillars[1:])):
            raise ValueError("Les temps des piliers doivent être strictement croissants.")
        return self

    def log_factor(self, time: float) -> float:
        if not 0 <= time <= self.pillars[-1].time:
            raise RatesMCError("MC_CURVE_COVERAGE", f"La courbe ne couvre pas le temps {time:.10g} an(s).")
        index = bisect_left(self.pillars, time, key=lambda pillar: pillar.time)
        right = self.pillars[index]
        if right.time == time:
            return log(right.factor)
        left = self.pillars[index - 1]
        weight = (time - left.time) / (right.time - left.time)
        return (1 - weight) * log(left.factor) + weight * log(right.factor)


class HwMarket(FrozenModel):
    discount: HwCurve
    projection: HwCurve
    mean_reversion: Nonnegative
    volatility: Nonnegative
    funding_bps: float = 0


class FixedSwapPeriod(FrozenModel):
    payment: float
    year_fraction: Positive


class ForwardPeriod(FrozenModel):
    kind: Literal["forward"] = "forward"
    start: float
    end: float
    year_fraction: Positive

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start >= self.end:
            raise ValueError("La fin du forward doit suivre son début.")
        return self


class SwapRate(FrozenModel):
    kind: Literal["swap"] = "swap"
    fixed_periods: tuple[FixedSwapPeriod, ...] = Field(min_length=1)
    floating_periods: tuple[ForwardPeriod, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_legs(self):
        if any(left.payment >= right.payment for left, right in zip(self.fixed_periods, self.fixed_periods[1:])):
            raise ValueError("Les règlements fixes du swap de référence doivent être ordonnés et distincts.")
        if any(left.end != right.start for left, right in zip(self.floating_periods, self.floating_periods[1:])):
            raise ValueError("Les périodes flottantes du swap de référence doivent être contiguës.")
        if (self.fixed_periods[0].payment <= self.floating_periods[0].start
                or self.fixed_periods[-1].payment != self.floating_periods[-1].end):
            raise ValueError("Les deux jambes du swap de référence doivent partager la même échéance.")
        return self


RateIndex = Annotated[ForwardPeriod | SwapRate, Field(discriminator="kind")]


def _check_observation(fixing: float, payment: float, realized_rate: float | None, indices: tuple[RateIndex, ...]) -> None:
    if fixing > payment:
        raise ValueError("Le fixing ne peut suivre son paiement.")
    if (fixing <= 0) != (realized_rate is not None):
        raise ValueError("Un fixing à l’arrêté ou antérieur exige son niveau acquis, un fixing futur se simule.")
    if fixing > 0 and any(
        (index.start if isinstance(index, ForwardPeriod) else index.floating_periods[0].start) < fixing
        for index in indices
    ):
        raise ValueError("Le swap ou forward de référence ne peut démarrer avant le fixing simulé.")


class RateCoupon(FrozenModel):
    kind: Literal["rate"] = "rate"
    flow_id: Identifier
    fixing: float
    payment: Nonnegative
    index: RateIndex
    spread_index: RateIndex | None = None
    year_fraction: Positive
    gearing: float = 1
    margin: float = 0
    payoff: Literal["linear", "caplet", "floorlet"] = "linear"
    strike: float | None = None
    floor: float | None = None
    cap: float | None = None
    realized_rate: float | None = None
    payscript: ExoticRatesScript | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_payoff(self):
        indices = (self.index,) if self.spread_index is None else (self.index, self.spread_index)
        _check_observation(self.fixing, self.payment, self.realized_rate, indices)
        if self.payscript is not None and (
            not all(isinstance(index, SwapRate) for index in indices)
            or (self.payoff, self.margin, self.gearing) != ("linear", 0, 1)
            or any(value is not None for value in (self.strike, self.floor, self.cap))
        ):
            raise ValueError("Un coupon PayScript exige des indices CMS et ses propres paramètres de payoff.")
        if self.payoff == "linear":
            if self.strike is not None or (self.floor is not None and self.cap is not None and self.floor > self.cap):
                raise ValueError("Le coupon linéaire accepte un plancher et un plafond ordonnés sans strike d’option.")
        elif self.strike is None or self.floor is not None or self.cap is not None:
            raise ValueError("Le caplet ou floorlet exige un strike et un payoff sans borne additionnelle.")
        return self


class RangeObservation(FrozenModel):
    time: float
    index: RateIndex
    weight: Positive
    realized_rate: float | None = None


class RangeAccrualCoupon(FrozenModel):
    kind: Literal["range_accrual"] = "range_accrual"
    flow_id: Identifier
    payment: Nonnegative
    observations: tuple[RangeObservation, ...] = Field(min_length=1)
    year_fraction: Positive
    annual_rate: Nonnegative
    lower: float
    upper: float
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    payscript: ExoticRatesScript | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_observations(self):
        if self.lower >= self.upper:
            raise ValueError("Les bornes de la bande doivent être strictement croissantes.")
        if any(left.time > right.time for left, right in zip(self.observations, self.observations[1:])):
            raise ValueError("Les observations du range accrual doivent être ordonnées.")
        for observation in self.observations:
            _check_observation(observation.time, self.payment, observation.realized_rate, (observation.index,))
        return self


class FixedCashflow(FrozenModel):
    kind: Literal["fixed"] = "fixed"
    flow_id: Identifier
    payment: Nonnegative
    amount_eur: float
    is_coupon: bool = True


class RateExercise(FrozenModel):
    exercise_id: Identifier
    decision: Positive
    settlement: Positive
    redemption_eur: Nonnegative
    owner: Literal["issuer", "holder"]
    coupon_priority: Literal["before", "after"]

    @model_validator(mode="after")
    def validate_settlement(self):
        if self.settlement < self.decision:
            raise ValueError("Le règlement de l’exercice ne peut précéder la décision.")
        return self


Cashflow = Annotated[FixedCashflow | RateCoupon | RangeAccrualCoupon, Field(discriminator="kind")]


class ExoticRatesTerms(FrozenModel):
    nominal_eur: Positive
    side: Literal["BUY", "SELL"] = "BUY"
    cashflows: tuple[Cashflow, ...] = Field(min_length=1)
    exercises: tuple[RateExercise, ...] = ()
    contract_dates: RatesContractDates | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_exercises(self):
        identifiers = [flow.flow_id for flow in self.cashflows] + [right.exercise_id for right in self.exercises]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Les identifiants de flux et d’exercice doivent être uniques.")
        if any(left.decision >= right.decision for left, right in zip(self.exercises, self.exercises[1:])):
            raise ValueError("Les exercices doivent être ordonnés et distincts.")
        if len({right.owner for right in self.exercises}) > 1:
            raise ValueError("Le pilote traite un seul titulaire des droits d’exercice par contrat.")
        if self.exercises and any(
            isinstance(flow, (RateCoupon, RangeAccrualCoupon)) for flow in self.cashflows
        ):
            raise ValueError("Le pilote d’exercice optimal porte sur les notes à flux fixes.")
        for right in self.exercises:
            if right.decision >= max(flow.payment for flow in self.cashflows):
                raise ValueError("Chaque exercice doit précéder le dernier flux du contrat.")
            if right.settlement > max(flow.payment for flow in self.cashflows):
                raise ValueError("Un règlement d’exercice ne peut dépasser le dernier flux du contrat.")
            if any(
                right.decision < flow.payment <= right.settlement
                or (flow.payment == right.decision and not flow.is_coupon)
                for flow in self.cashflows
            ):
                raise ValueError("Les droits d’exercice avec flux intermédiaire ou principal à la décision sont hors pilote.")
        return self

    @model_validator(mode="after")
    def validate_contract_dates(self):
        dates = self.contract_dates
        if dates is None:
            return self
        payments = {flow.flow_id: dates.at(flow.payment) for flow in self.cashflows}
        if min(payments.values()) < dates.start_date or max(payments.values()) < dates.end_date:
            raise ValueError("Les paiements doivent suivre le début du contrat et couvrir son échéance.")
        coupon_ids = {flow.flow_id for flow in self.cashflows if not isinstance(flow, FixedCashflow) or flow.is_coupon}
        if any(item.flow_id not in coupon_ids or item.end_date > payments[item.flow_id] for item in dates.accrual_periods):
            raise ValueError("Une période de coupon doit désigner un coupon et finir au plus tard à son paiement.")
        for flow in self.cashflows:
            if isinstance(flow, RateCoupon):
                dates.at(flow.fixing)
                _validate_index_dates(flow.index, dates)
                if flow.spread_index is not None:
                    _validate_index_dates(flow.spread_index, dates)
            elif isinstance(flow, RangeAccrualCoupon):
                for observation in flow.observations:
                    dates.at(observation.time)
                    _validate_index_dates(observation.index, dates)
        for exercise in self.exercises:
            if not dates.start_date <= dates.at(exercise.decision) <= dates.end_date:
                raise ValueError("La décision d’exercice doit tomber pendant le contrat.")
            dates.at(exercise.settlement)
        return self


def _validate_index_dates(index: RateIndex, dates: RatesContractDates) -> None:
    if isinstance(index, SwapRate):
        for period in index.fixed_periods:
            dates.at(period.payment)
        periods = index.floating_periods
    else:
        periods = (index,)
    for period in periods:
        dates.at(period.start)
        dates.at(period.end)


class RatesMCSettings(FrozenModel):
    paths: int = Field(strict=True, ge=2, le=1_000_000)
    seed: int = Field(strict=True, ge=0, lt=2**64)
    antithetic: bool = True
    training_paths: int | None = Field(default=None, strict=True, ge=32, le=1_000_000)
    regression_degree: int = Field(default=2, strict=True, ge=1, le=4)

    @model_validator(mode="after")
    def validate_samples(self):
        counts = (self.paths,) if self.training_paths is None else (self.paths, self.training_paths)
        if self.antithetic and any(count < 4 or count % 2 for count in counts):
            raise ValueError("L’échantillonnage antithétique exige un nombre pair de trajectoires et au moins deux paires.")
        return self


class RatesMCEstimate(FrozenModel):
    pv_eur: float
    standard_error_eur: Nonnegative
    ci95_eur: tuple[float, float]


class RatesMCFlow(FrozenModel):
    flow_id: str
    kind: Literal["fixed", "rate", "range_accrual", "exercise"]
    payment: Nonnegative
    mean_amount_eur: float
    pv_eur: float
    paid_probability: Annotated[float, Field(ge=0, le=1)]
    payment_date: date | None = Field(default=None, exclude_if=lambda value: value is None)
    payment_event_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    payment_role: Literal["coupon", "principal", "exercise"] | None = Field(default=None, exclude_if=lambda value: value is None)
    state: Literal["projected", "fixed", "due", "contingent"] | None = Field(default=None, exclude_if=lambda value: value is None)
    amount_eur: float | None = Field(default=None, exclude_if=lambda value: value is None)
    accrual_start_date: date | None = Field(default=None, exclude_if=lambda value: value is None)
    accrual_end_date: date | None = Field(default=None, exclude_if=lambda value: value is None)


class RatesExercisePolicy(FrozenModel):
    exercise_id: str
    decision: Positive
    settlement: Positive
    owner: Literal["issuer", "holder"]
    coupon_priority: Literal["before", "after"]
    basis: Literal["centered_ou_power_plus_fixed_control"] = "centered_ou_power_plus_fixed_control"
    state_scale: Nonnegative
    coefficients: tuple[float, ...]


class RatesMCResult(RatesMCEstimate):
    engine_version: Literal["eur-rates-hw1f-exact-v1"] = ENGINE_VERSION
    measure: Literal["ois_money_market"] = "ois_money_market"
    unit: Literal["EUR"] = "EUR"
    currency: Literal["EUR"] = "EUR"
    pv_per_100: float
    draw_fingerprint: str
    generator: Literal["numpy-pcg64-normal-event-major-v1"] = _GENERATOR
    event_times: tuple[float, ...]
    paths: int
    independent_paths: int
    seed: int
    antithetic: bool
    training_paths: int | None
    flows: tuple[RatesMCFlow, ...]
    exercise_policy: tuple[RatesExercisePolicy, ...]
    payscript_metadata: tuple[ExoticRatesScriptMetadata, ...] = Field(default=(), exclude_if=lambda value: not value)


@dataclass(frozen=True)
class RatesMCValuation:
    result: RatesMCResult
    independent_pv_eur: np.ndarray


@dataclass(frozen=True)
class HullWhitePaths:
    times: tuple[float, ...]
    state: np.ndarray
    discount: np.ndarray


def _bond_loading(mean_reversion: float, horizon: float) -> float:
    return -expm1(-mean_reversion * horizon) / mean_reversion if mean_reversion else horizon


def _integral_variance(market: HwMarket, horizon: float) -> float:
    a, sigma = market.mean_reversion, market.volatility
    if sigma == 0 or horizon == 0:
        return 0.0
    z = a * horizon
    if z < .05:
        # Integrate the Taylor expansion of ((1 - exp(-a*u)) / a)².
        ratio = 1 / 3 + z * (-1 / 4 + z * (7 / 60 + z * (-1 / 24 + z * (31 / 2520 - z / 320))))
        return sigma**2 * horizon**3 * ratio
    return (sigma / a)**2 * (horizon - 2 * _bond_loading(a, horizon) + _bond_loading(2 * a, horizon))


def conditional_ois_bond(market: HwMarket, time: float, maturity: float, state: np.ndarray) -> np.ndarray:
    """OIS zero price conditional on the centred OU state under the money-market measure."""
    if time > maturity:
        raise RatesMCError("MC_OBSERVATION_DATES", "La maturité du zéro-coupon précède son observation.")
    horizon = maturity - time
    log_factor = market.discount.log_factor(maturity) - market.discount.log_factor(time)
    convexity = .5 * (_integral_variance(market, horizon) - _integral_variance(market, maturity)
                     + _integral_variance(market, time))
    return np.exp(log_factor + convexity - _bond_loading(market.mean_reversion, horizon) * state)


def conditional_forward(market: HwMarket, time: float, period: ForwardPeriod, state: np.ndarray) -> np.ndarray:
    """Forward coupon using a deterministic multiplicative OIS / Euribor basis."""
    if not 0 <= time <= period.start:
        raise RatesMCError("MC_OBSERVATION_DATES", "Le forward démarre avant son observation.")
    # Projection/OIS ratios are deterministic, with the same stochastic factor as OIS.
    horizon_start, horizon_end = period.start - time, period.end - time
    log_ratio = market.projection.log_factor(period.start) - market.projection.log_factor(period.end)
    variance = (_integral_variance(market, horizon_start) - _integral_variance(market, period.start)
                - _integral_variance(market, horizon_end) + _integral_variance(market, period.end))
    loading = (_bond_loading(market.mean_reversion, horizon_end) - _bond_loading(market.mean_reversion, horizon_start))
    return np.expm1(log_ratio + .5 * variance + loading * state) / period.year_fraction


def conditional_swap_rate(market: HwMarket, time: float, index: SwapRate, state: np.ndarray) -> np.ndarray:
    annuity = sum(period.year_fraction * conditional_ois_bond(market, time, period.payment, state)
                  for period in index.fixed_periods)
    floating = sum(period.year_fraction * conditional_ois_bond(market, time, period.end, state)
                   * conditional_forward(market, time, period, state) for period in index.floating_periods)
    return floating / annuity


def simulate_hull_white(
    market: HwMarket, event_times: tuple[float, ...], *, paths: int, seed: int, antithetic: bool,
    stream: Literal["valuation", "training"] = "valuation",
) -> HullWhitePaths:
    """Draw exact OU states and integrated short rates at the same contractual events."""
    if paths < 2 or (antithetic and (paths < 4 or paths % 2)):
        raise RatesMCError("MC_SAMPLE_SIZE", "Nombre de trajectoires incompatible avec l’échantillonnage.")
    if not event_times or event_times[0] != 0 or not np.isfinite(event_times).all() or any(
        not left < right for left, right in zip(event_times, event_times[1:])
    ):
        raise RatesMCError("MC_EVENT_GRID", "La grille doit partir de zéro, avec des événements strictement croissants.")
    if len(event_times) * paths > _MAX_GRID_CELLS:
        raise RatesMCError("MC_GRID_LIMIT", "Le nombre de couples événements–trajectoires dépasse la limite mémoire du pilote.")
    market.discount.log_factor(event_times[-1])
    stream_id = {"valuation": 0, "training": 1}[stream]
    random = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed, spawn_key=(stream_id,))))
    count = paths // 2 if antithetic else paths
    state = np.zeros((len(event_times), paths))
    discount = np.ones_like(state)
    integrated = np.zeros(paths)
    a, sigma = market.mean_reversion, market.volatility
    for step, (previous, time) in enumerate(zip(event_times, event_times[1:]), start=1):
        horizon = time - previous
        phi, state_sd = _ou_transition(sigma, a, horizon)
        loading = _bond_loading(a, horizon)
        covariance = .5 * (sigma * loading)**2
        linked_integral_sd = covariance / state_sd if state_sd else 0.0
        orthogonal_integral_sd = sqrt(max(0.0, _integral_variance(market, horizon) - linked_integral_sd**2))
        normal = random.standard_normal((2, count))
        if antithetic:
            normal = np.concatenate((normal, -normal), axis=1)
        integrated += loading * state[step - 1] + linked_integral_sd * normal[0] + orthogonal_integral_sd * normal[1]
        state[step] = phi * state[step - 1] + state_sd * normal[0]
        discount[step] = np.exp(market.discount.log_factor(time) - .5 * _integral_variance(market, time) - integrated)
    if not np.isfinite(state).all() or not np.isfinite(discount).all() or (discount <= 0).any():
        raise RatesMCError("MC_NUMERICAL_DOMAIN", "L’intégration Hull–White produit des facteurs d’actualisation invalides.")
    state.setflags(write=False)
    discount.setflags(write=False)
    return HullWhitePaths(event_times, state, discount)


def _event_times(terms: ExoticRatesTerms) -> tuple[float, ...]:
    times = {0.0}
    for flow in terms.cashflows:
        times.add(flow.payment)
        if isinstance(flow, RateCoupon) and flow.fixing > 0:
            times.add(flow.fixing)
        elif isinstance(flow, RangeAccrualCoupon):
            times.update(observation.time for observation in flow.observations if observation.time > 0)
    for right in terms.exercises:
        times.update((right.decision, right.settlement))
    return tuple(sorted(times))


def _check_curve_coverage(terms: ExoticRatesTerms, market: HwMarket, last_event: float) -> None:
    index_requirements = []
    for flow in terms.cashflows:
        if isinstance(flow, RateCoupon) and flow.realized_rate is None:
            index_requirements.append(flow.index)
            if flow.spread_index is not None:
                index_requirements.append(flow.spread_index)
        elif isinstance(flow, RangeAccrualCoupon):
            index_requirements.extend(obs.index for obs in flow.observations if obs.realized_rate is None)
    discount_end, projection_end = last_event, 0.0
    for index in index_requirements:
        projection_end = max(projection_end, index.end if isinstance(index, ForwardPeriod) else index.floating_periods[-1].end)
        if isinstance(index, SwapRate):
            discount_end = max(discount_end, index.fixed_periods[-1].payment)
    market.discount.log_factor(discount_end)
    market.projection.log_factor(projection_end)


def _observe(
    market: HwMarket, states: dict[float, np.ndarray], index: RateIndex, time: float, acquired: float | None,
) -> np.ndarray | float:
    if acquired is not None:
        return acquired
    state = states[time]
    if isinstance(index, SwapRate):
        return conditional_swap_rate(market, time, index, state)
    return conditional_forward(market, time, index, state)


def _cashflow_amount(terms: ExoticRatesTerms, flow: Cashflow, market: HwMarket, states: dict[float, np.ndarray],
                     script: CompiledExoticRatesPayScript | None):
    if isinstance(flow, FixedCashflow):
        return flow.amount_eur
    if isinstance(flow, RangeAccrualCoupon):
        occupation = np.zeros(states[0].shape)
        for observation in flow.observations:
            rate = _observe(market, states, observation.index, observation.time, observation.realized_rate)
            after_lower = rate >= flow.lower if flow.lower_inclusive else rate > flow.lower
            before_upper = rate <= flow.upper if flow.upper_inclusive else rate < flow.upper
            occupation += observation.weight * (after_lower & before_upper)
        total_weight = sum(obs.weight for obs in flow.observations)
        if script is not None:
            return terms.nominal_eur * script.evaluate(
                states[0].size, RANGE_FRACTION=occupation / total_weight,
                ANNUAL_RATE=flow.annual_rate, YEAR_FRACTION=flow.year_fraction,
            )
        full_coupon = terms.nominal_eur * flow.year_fraction * flow.annual_rate
        return full_coupon * occupation / total_weight

    rate = _observe(market, states, flow.index, flow.fixing, flow.realized_rate)
    if flow.realized_rate is None and flow.spread_index is not None:
        rate = rate - _observe(market, states, flow.spread_index, flow.fixing, None)
    if script is not None:
        observable = "CMS_SPREAD" if flow.spread_index is not None else "CMS_RATE"
        return terms.nominal_eur * script.evaluate(states[0].size, YEAR_FRACTION=flow.year_fraction, **{observable: rate})
    payoff_rate = flow.margin + flow.gearing * rate
    if flow.payoff == "caplet":
        payoff_rate = np.maximum(payoff_rate - flow.strike, 0)
    elif flow.payoff == "floorlet":
        payoff_rate = np.maximum(flow.strike - payoff_rate, 0)
    else:
        if flow.floor is not None:
            payoff_rate = np.maximum(payoff_rate, flow.floor)
        if flow.cap is not None:
            payoff_rate = np.minimum(payoff_rate, flow.cap)
    return terms.nominal_eur * flow.year_fraction * payoff_rate


def _discount_rows(paths: HullWhitePaths, funding: float) -> dict[float, np.ndarray]:
    return {
        time: discount * exp(-funding * time) if funding else discount
        for time, discount in zip(paths.times, paths.discount)
    }


def _continuation_cashflows(terms: ExoticRatesTerms, right: RateExercise) -> tuple[FixedCashflow, ...]:
    return tuple(
        flow for flow in terms.cashflows
        if flow.payment > right.decision or (flow.payment == right.decision and right.coupon_priority == "after")
    )


def _conditional_amount(market: HwMarket, time: float, payment: float,
                        state: np.ndarray, amount: float) -> np.ndarray:
    length = payment - time
    return amount * exp(-market.funding_bps / 10_000 * length) * conditional_ois_bond(market, time, payment, state)


def _should_exercise(right: RateExercise, market: HwMarket, fair_continuation: np.ndarray,
                     state: np.ndarray) -> np.ndarray:
    redemption = _conditional_amount(market, right.decision, right.settlement, state, right.redemption_eur)
    return redemption < fair_continuation if right.owner == "issuer" else redemption > fair_continuation


def _reference_continuation(terms: ExoticRatesTerms, right: RateExercise,
                            market: HwMarket, state: np.ndarray) -> np.ndarray:
    return sum(_conditional_amount(market, right.decision, flow.payment, state, flow.amount_eur)
               for flow in _continuation_cashflows(terms, right))


def _learn_exercise(terms: ExoticRatesTerms, market: HwMarket, paths: HullWhitePaths,
                    degree: int) -> tuple[RatesExercisePolicy, ...]:
    states = dict(zip(paths.times, paths.state))
    discounts = _discount_rows(paths, market.funding_bps / 10_000)
    adjusted_pv = np.zeros(paths.state.shape[1])
    policies = []
    for right in reversed(terms.exercises):
        state = states[right.decision]
        _, scale = _ou_transition(market.volatility, market.mean_reversion, right.decision)
        target = adjusted_pv / discounts[right.decision]
        if scale == 0.0:
            coefficients = np.array([target.mean()])
            correction = coefficients[0]
        else:
            coordinates = state / scale
            design = np.polynomial.polynomial.polyvander(coordinates, degree)
            coefficients, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
            if rank != degree + 1:
                raise RatesMCError("MC_LSM_RANK", "La base de régression d’exercice est de rang insuffisant.")
            correction = design @ coefficients
        continuation = _reference_continuation(terms, right, market, state) + correction
        exercise = _should_exercise(right, market, continuation, state)
        redemption_pv = right.redemption_eur * discounts[right.settlement]
        fixed_pv = sum(flow.amount_eur * discounts[flow.payment] for flow in _continuation_cashflows(terms, right))
        adjusted_pv = np.where(exercise, redemption_pv - fixed_pv, adjusted_pv)
        policies.append(RatesExercisePolicy(
            exercise_id=right.exercise_id, decision=right.decision, settlement=right.settlement, owner=right.owner,
            coupon_priority=right.coupon_priority, state_scale=scale, coefficients=tuple(coefficients),
        ))
    return tuple(reversed(policies))


def _rate_samples(terms: ExoticRatesTerms, market: HwMarket, paths: HullWhitePaths,
                  policies: tuple[RatesExercisePolicy, ...], scripts: dict[str, CompiledExoticRatesPayScript],
                  ) -> tuple[np.ndarray, tuple[RatesMCFlow, ...]]:
    states = dict(zip(paths.times, paths.state))
    discounts = _discount_rows(paths, market.funding_bps / 10_000)
    count = paths.state.shape[1]
    stopped_at = np.full(count, np.inf)
    keep_coupon = np.zeros(count, dtype=bool)
    total_pv = np.zeros(count)
    flow_details = []
    sign = 1 if terms.side == "BUY" else -1
    dates = terms.contract_dates
    accrual_periods = {} if dates is None else {period.flow_id: period for period in dates.accrual_periods}

    def add_flow(flow_id, kind, payment, amount, paid, *, role, known, contingent):
        signed_amount = sign * np.where(paid, amount, 0.0)
        flow_pv = signed_amount * discounts[payment]
        total_pv[:] += flow_pv
        dated = {}
        if dates is not None:
            period = accrual_periods.get(flow_id)
            suffix = "settlement" if role == "exercise" else "payment"
            dated = {
                "payment_date": dates.at(payment), "payment_event_id": f"{flow_id}:{suffix}", "payment_role": role,
                "state": "contingent" if contingent else "due" if payment == 0 else "fixed" if known else "projected",
                "amount_eur": sign * float(np.asarray(amount).flat[0]) if known and not contingent else None,
                "accrual_start_date": period.start_date if period else None,
                "accrual_end_date": period.end_date if period else None,
            }
        flow_details.append(RatesMCFlow(
            flow_id=flow_id, kind=kind, payment=payment, mean_amount_eur=signed_amount.mean(),
            pv_eur=flow_pv.mean(), paid_probability=np.mean(paid), **dated,
        ))

    for right, policy in zip(terms.exercises, policies, strict=True):
        state = states[right.decision]
        correction = (np.polynomial.polynomial.polyval(state / policy.state_scale, policy.coefficients)
                      if policy.state_scale else policy.coefficients[0])
        continuation = _reference_continuation(terms, right, market, state) + correction
        exercise = (stopped_at > right.decision) & _should_exercise(right, market, continuation, state)
        stopped_at[exercise] = right.decision
        keep_coupon[exercise] = right.coupon_priority == "before"
        add_flow(right.exercise_id, "exercise", right.settlement, right.redemption_eur, exercise,
                 role="exercise", known=False, contingent=True)

    first_right = terms.exercises[0] if terms.exercises else None
    for flow in terms.cashflows:
        paid = (flow.payment < stopped_at) | ((flow.payment == stopped_at) & keep_coupon)
        amount = _cashflow_amount(terms, flow, market, states, scripts.get(flow.flow_id))
        role = "principal" if isinstance(flow, FixedCashflow) and not flow.is_coupon else "coupon"
        known = (isinstance(flow, FixedCashflow)
                 or isinstance(flow, RateCoupon) and flow.realized_rate is not None
                 or isinstance(flow, RangeAccrualCoupon) and all(obs.realized_rate is not None for obs in flow.observations))
        contingent = first_right is not None and (flow.payment > first_right.decision or (
            flow.payment == first_right.decision and first_right.coupon_priority == "after"
        ))
        add_flow(flow.flow_id, flow.kind, flow.payment, amount, paid, role=role, known=known, contingent=contingent)
    if dates is not None:
        flow_details.sort(key=lambda row: (row.payment, row.flow_id))
    return total_pv, tuple(flow_details)


def _estimate(samples: np.ndarray) -> RatesMCEstimate:
    if np.all(samples == samples[0]):
        value = float(samples[0])
        return RatesMCEstimate(pv_eur=value, standard_error_eur=0, ci95_eur=(value, value))
    mean = samples.mean()
    error = samples.std(ddof=1) / sqrt(samples.size)
    half_width = stdtrit(samples.size - 1, .975) * error
    return RatesMCEstimate(pv_eur=mean, standard_error_eur=error, ci95_eur=(mean - half_width, mean + half_width))


def _compile_coupon_scripts(terms: ExoticRatesTerms) -> dict[str, CompiledExoticRatesPayScript]:
    scripts = {}
    for flow in terms.cashflows:
        if isinstance(flow, RateCoupon) and flow.payscript is not None:
            event = "CMS_SPREAD_COUPON" if flow.spread_index is not None else "CMS_COUPON"
        elif isinstance(flow, RangeAccrualCoupon) and flow.payscript is not None:
            event = "RANGE_COUPON"
        else:
            continue
        scripts[flow.flow_id] = compile_exotic_rates_script(flow.payscript, event=event, flow_id=flow.flow_id)
    return scripts


def price_exotic_rates(terms: ExoticRatesTerms, market: HwMarket, settings: RatesMCSettings) -> RatesMCValuation:
    """Price the holder's payoff and retain independent evaluation units for paired explain."""
    if bool(terms.exercises) != (settings.training_paths is not None):
        raise RatesMCError("MC_LSM_SAMPLE", "Un échantillon d’apprentissage distinct est requis uniquement pour l’exercice optimal.")
    scripts = _compile_coupon_scripts(terms)
    times = _event_times(terms)
    _check_curve_coverage(terms, market, times[-1])
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            policies = ()
            if settings.training_paths is not None:
                policies = _learn_exercise(terms, market, simulate_hull_white(
                    market, times, paths=settings.training_paths, seed=settings.seed,
                    antithetic=settings.antithetic, stream="training",
                ), settings.regression_degree)
            paths = simulate_hull_white(market, times, paths=settings.paths, seed=settings.seed, antithetic=settings.antithetic)
            samples, flows = _rate_samples(terms, market, paths, policies, scripts)
            if settings.antithetic:
                positive, negative = np.split(samples, 2)
                samples = .5 * (positive + negative)
            estimate = _estimate(samples)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        raise RatesMCError("MC_NUMERICAL_DOMAIN", "Le calcul sort du domaine numérique du modèle Hull–White.") from exc
    samples.setflags(write=False)
    draw_fingerprint = canonical_fingerprint({
        "generator": _GENERATOR, "stream": "valuation", "seed": settings.seed,
        "grid": times, "paths": settings.paths, "antithetic": settings.antithetic,
    })
    return RatesMCValuation(RatesMCResult(
        **estimate.model_dump(), pv_per_100=estimate.pv_eur / terms.nominal_eur * 100,
        draw_fingerprint=draw_fingerprint, event_times=times, paths=settings.paths, independent_paths=samples.size,
        seed=settings.seed, antithetic=settings.antithetic, training_paths=settings.training_paths,
        flows=flows, exercise_policy=policies,
        payscript_metadata=tuple(script.metadata for script in scripts.values()),
    ), samples)


def paired_rates_mc_difference(base: RatesMCValuation, bumped: RatesMCValuation) -> RatesMCEstimate:
    if base.result.draw_fingerprint != bumped.result.draw_fingerprint:
        raise RatesMCError("MC_DRAWS_MISMATCH", "Les grilles ou les tirages de valorisation diffèrent.")
    return _estimate(bumped.independent_pv_eur - base.independent_pv_eur)
