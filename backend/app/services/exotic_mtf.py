"""Conditional Mark to Future on the frozen EUR exotic research scenarios."""

from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from math import exp, pi, sqrt
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.optimize import brentq
from scipy.special import ndtr, roots_hermitenorm

from ..core.payscript.rates import _ou_transition
from ..core.product.credit_pricing import CreditCoupon, SurvivalCurve
from ..core.product.exotic_credit_mc import CreditMcMarginal, CreditMcRequest, _HazardSegments, _reference, resolve_credit_payoff
from ..core.product.exotic_rates_mc import (
    FixedCashflow, ForwardPeriod, RangeAccrualCoupon, RateCoupon, RatesExercisePolicy, SwapRate,
    _bond_loading, _cashflow_amount, _check_curve_coverage, _compile_coupon_scripts,
    _conditional_amount, _event_times, _reference_continuation, _should_exercise,
    conditional_forward, conditional_swap_rate, simulate_hull_white,
)
from ..core.product.models import FrozenModel
from .exotic_valuation import ExoticCreditScenario, ExoticRatesScenario, ExoticScenario


class ExoticMtfError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


Horizon = Annotated[float, Field(gt=0, le=100)]
PathCount = Annotated[int, Field(strict=True, ge=64, le=4096)]
_MAX_LIVE_STATES = 128
_MAX_WORK = 45_000_000
_MAX_CREDIT_REFERENCE_WORK = 220_000


class ExoticMtfCall(FrozenModel):
    receipt: dict = Field(min_length=1)
    horizons_years: tuple[Horizon, ...] = Field(min_length=1, max_length=12)
    paths: PathCount = 1024

    @model_validator(mode="after")
    def increasing_horizons(self):
        if any(left >= right for left, right in zip(self.horizons_years, self.horizons_years[1:])):
            raise ValueError("Les horizons de Mark to Future doivent être distincts et croissants.")
        return self


class ExoticMtfHistogramBin(FrozenModel):
    low_eur: float
    high_eur: float
    count: int


class ExoticMtfHorizon(FrozenModel):
    horizon_years: Horizon
    mean_pv_eur: float
    standard_deviation_eur: float
    p05_pv_eur: float
    p50_pv_eur: float
    p95_pv_eur: float
    active_probability: float
    claim_probability: float
    settled_probability: float
    mean_cash_paid_eur: float
    quadrature_refinement_eur: float | None
    histogram: tuple[ExoticMtfHistogramBin, ...]


class ExoticMtfResult(FrozenModel):
    schema_version: Literal[1] = 1
    family: Literal["rates", "credit"]
    position_id: str
    valuation_date: date
    cutoff: datetime
    unit: Literal["EUR"] = "EUR"
    method: Literal["conditional_hull_white_1f", "conditional_independent_credit"]
    seed: int
    paths: int
    horizons: tuple[ExoticMtfHorizon, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Population:
    values: np.ndarray
    states: np.ndarray
    cash_paid: np.ndarray
    refinement: float | None = None


def _summarize(horizon: float, population: _Population) -> ExoticMtfHorizon:
    values, states = population.values, population.states
    if not np.isfinite(values).all() or not np.isfinite(population.cash_paid).all():
        raise ExoticMtfError("EXOTIC_MTF_NUMERICAL", "La valeur conditionnelle sort du domaine numérique.")
    q05, q50, q95 = np.quantile(values, (.05, .50, .95))
    lower, upper = values.min(), values.max()
    if lower == upper:
        bins = (ExoticMtfHistogramBin(low_eur=lower, high_eur=upper, count=len(values)),)
    else:
        counts, borders = np.histogram(values, bins=20)
        bins = tuple(ExoticMtfHistogramBin(low_eur=left, high_eur=right, count=count)
                     for left, right, count in zip(borders[:-1], borders[1:], counts, strict=True))
    return ExoticMtfHorizon(
        horizon_years=horizon, mean_pv_eur=values.mean(), standard_deviation_eur=values.std(ddof=1),
        p05_pv_eur=q05, p50_pv_eur=q50, p95_pv_eur=q95, active_probability=np.mean(states == 0),
        claim_probability=np.mean(states == 1), settled_probability=np.mean(states == 2),
        mean_cash_paid_eur=population.cash_paid.mean(), quadrature_refinement_eur=population.refinement,
        histogram=bins,
    )


@lru_cache(maxsize=8)
def _normal_quadrature(order: int) -> tuple[np.ndarray, np.ndarray]:
    nodes, weights = roots_hermitenorm(order)
    return nodes, weights / sqrt(2 * pi)


def _payment_state(market, start: float, fixing: float, payment: float,
                   state: np.ndarray) -> tuple[np.ndarray, float]:
    """Law of x_fixing under the payment numeraire, given x_start."""
    dt = fixing - start
    phi, sd = _ou_transition(market.volatility, market.mean_reversion, dt)
    cov = .5 * (market.volatility * _bond_loading(market.mean_reversion, dt))**2
    cov += sd**2 * _bond_loading(market.mean_reversion, payment - fixing)
    return phi * state - cov, sd


def _conditional_expectation(market, start, fixing, payment, state, payoff, order):
    mean, sd = _payment_state(market, start, fixing, payment, state)
    if sd == 0:
        return payoff(mean)
    nodes, weights = _normal_quadrature(order)
    sampled_states = mean[:, None] + sd * nodes
    return np.asarray(payoff(sampled_states.ravel())).reshape(sampled_states.shape) @ weights


def _band_probability(market, horizon, flow, observation, states):
    index, time = observation.index, observation.time

    def index_rate(factor):
        if isinstance(index, ForwardPeriod):
            return conditional_forward(market, time, index, factor)
        return conditional_swap_rate(market, time, index, factor)

    def in_band(rate):
        left = rate >= flow.lower if flow.lower_inclusive else rate > flow.lower
        right = rate <= flow.upper if flow.upper_inclusive else rate < flow.upper
        return left & right

    if observation.realized_rate is not None:
        return float(in_band(observation.realized_rate))
    mean, sd = _payment_state(market, horizon, time, flow.payment, states)
    if sd == 0:
        return in_band(index_rate(mean))

    # On the supported monotone range indices, integrate the digital by its
    # thresholds. The interval contains at least eleven conditional deviations.
    low, high = float(mean.min() - 11 * sd), float(mean.max() + 11 * sd)
    grid = np.linspace(low, high, 257)
    levels = index_rate(grid)
    if not np.isfinite(levels).all() or np.any(np.diff(levels) <= 0):
        raise ExoticMtfError("EXOTIC_MTF_RANGE_INDEX", "Le fixing de range requiert une référence croissante sur le domaine conditionnel.")

    def crossing(rate):
        if rate <= levels[0]:
            return -np.inf
        if rate >= levels[-1]:
            return np.inf
        return brentq(lambda x: float(index_rate(np.asarray(x))) - rate, low, high, xtol=1e-14)

    return ndtr((crossing(flow.upper) - mean) / sd) - ndtr((crossing(flow.lower) - mean) / sd)


def _coupon_value(terms, market, horizon, flow, states, script, order):
    if isinstance(flow, FixedCashflow):
        expected = flow.amount_eur
    elif isinstance(flow, RangeAccrualCoupon):
        if script is not None and any(obs.realized_rate is None for obs in flow.observations):
            raise ExoticMtfError("EXOTIC_MTF_RANGE_SCRIPT", "Le range PayScript nécessite une loi jointe conditionnelle de l’occupation.")
        if script is not None:
            expected = _cashflow_amount(terms, flow, market, {0: states}, script)
        else:
            full = terms.nominal_eur * flow.year_fraction * flow.annual_rate
            weighted = sum(obs.weight * _band_probability(market, horizon, flow, obs, states) for obs in flow.observations)
            expected = full * weighted / sum(obs.weight for obs in flow.observations)
    elif flow.realized_rate is not None:
        expected = _cashflow_amount(terms, flow, market, {0: states}, script)
    else:
        expected = _conditional_expectation(
            market, horizon, flow.fixing, flow.payment, states,
            lambda x: np.broadcast_to(_cashflow_amount(terms, flow, market, {0: x, flow.fixing: x}, script), x.shape),
            order,
        )
    return _conditional_amount(market, horizon, flow.payment, states, expected)


def _fixed_cash_between(market, terms, start, end, states):
    result = np.zeros_like(states)
    for flow in terms.cashflows:
        if start < flow.payment < end:
            result += _conditional_amount(market, start, flow.payment, states, flow.amount_eur)
    return result


def _policy_functions(scenario: ExoticRatesScenario, archived_result: dict | None, order: int, grid_size: int):
    terms, market = scenario.terms, scenario.market
    right_values = tuple(RatesExercisePolicy.model_validate(item) for item in (archived_result or {}).get("exercise_policy", ()))
    if len(right_values) != len(terms.exercises) or any(
        (right.exercise_id, right.decision, right.settlement, right.owner, right.coupon_priority)
        != (policy.exercise_id, policy.decision, policy.settlement, policy.owner, policy.coupon_priority)
        for right, policy in zip(terms.exercises, right_values)
    ):
        raise ExoticMtfError("EXOTIC_MTF_EXERCISE_PROOF", "La politique d’exercice du prix de référence est indisponible.")
    next_decision, next_policy = None, None
    for right, policy in reversed(tuple(zip(terms.exercises, right_values))):
        decision = right.decision
        bounds = 13 * (policy.state_scale or .01)
        x = np.linspace(-bounds, bounds, grid_size)
        continuation = _fixed_cash_between(market, terms, decision, next_decision or np.inf, x)
        if next_decision is not None:
            expected = _conditional_expectation(market, decision, next_decision, next_decision, x, next_policy, order)
            continuation += _conditional_amount(market, decision, next_decision, x, expected)
        coupon = sum(flow.amount_eur for flow in terms.cashflows if flow.payment == decision)
        correction = (np.polynomial.polynomial.polyval(x / policy.state_scale, policy.coefficients)
                      if policy.state_scale else policy.coefficients[0])
        archived_continuation = _reference_continuation(terms, right, market, x) + correction
        exercise = _should_exercise(right, market, archived_continuation, x)
        redemption = _conditional_amount(market, decision, right.settlement, x, right.redemption_eur)
        cash_on_exercise = coupon if right.coupon_priority == "before" else 0.0
        values = np.where(exercise, redemption + cash_on_exercise, continuation + coupon)

        def evaluate(states, *, points=x, marks=values):
            return np.interp(states, points, marks)

        next_decision, next_policy = decision, evaluate
    return next_decision, next_policy


def _rates_populations(scenario, horizons, count, archived_result):
    terms, market = scenario.terms, scenario.market
    event_times = _event_times(terms)
    first_change = min((
        *(flow.fixing for flow in terms.cashflows if isinstance(flow, RateCoupon) and flow.realized_rate is None),
        *(observation.time for flow in terms.cashflows if isinstance(flow, RangeAccrualCoupon)
          for observation in flow.observations if observation.realized_rate is None),
        *(right.decision for right in terms.exercises),
    ), default=np.inf)
    if horizons[-1] >= first_change:
        raise ExoticMtfError("EXOTIC_MTF_UNREALIZED_STATE",
                             f"Les horizons doivent précéder le premier fixing ou exercice simulé ({first_change:.8g} ans).")
    if horizons[-1] > max(flow.payment for flow in terms.cashflows):
        raise ExoticMtfError("EXOTIC_MTF_HORIZON", "Un horizon dépasse le dernier règlement du produit.")
    if len(terms.exercises) > 4:
        raise ExoticMtfError("EXOTIC_MTF_EXERCISE_LIMIT", "Le Mark to Future traite jusqu’à quatre décisions d’exercice.")
    complexity = len(terms.cashflows) + len(terms.exercises)
    for flow in terms.cashflows:
        indices = ((flow.index, flow.spread_index) if isinstance(flow, RateCoupon) else
                   (obs.index for obs in flow.observations) if isinstance(flow, RangeAccrualCoupon) else ())
        complexity += sum(len(index.fixed_periods) + 2 * len(index.floating_periods) if isinstance(index, SwapRate) else 1
                          for index in indices if index is not None)
    if count * len(horizons) * 64 * complexity > _MAX_WORK:
        raise ExoticMtfError("EXOTIC_MTF_WORK_LIMIT", "Réduisez les horizons ou les trajectoires pour la grille de taux demandée.")
    _check_curve_coverage(terms, market, event_times[-1])
    scripts = _compile_coupon_scripts(terms)
    sign = 1 if terms.side == "BUY" else -1
    scenarios = simulate_hull_white(market, (0., *horizons), paths=count, seed=scenario.settings.seed, antithetic=False)
    if terms.exercises:
        coarse_policy = _policy_functions(scenario, archived_result, 32, 401)
        fine_policy = _policy_functions(scenario, archived_result, 64, 801)

    for horizon, state in zip(horizons, scenarios.state[1:], strict=True):
        if terms.exercises:
            refinements = []
            for order, (decision, policy) in ((32, coarse_policy), (64, fine_policy)):
                expected = _conditional_expectation(market, horizon, decision, decision, state, policy, order)
                refinements.append(_fixed_cash_between(market, terms, horizon, decision, state)
                                   + _conditional_amount(market, horizon, decision, state, expected))
            coarse, fine = refinements
        else:
            coarse, fine = np.zeros_like(state), np.zeros_like(state)
            for flow in terms.cashflows:
                if flow.payment > horizon:
                    coarse += _coupon_value(terms, market, horizon, flow, state, scripts.get(flow.flow_id), 32)
                    fine += _coupon_value(terms, market, horizon, flow, state, scripts.get(flow.flow_id), 64)
        cash_paid = np.zeros_like(state)
        for flow in terms.cashflows:
            if flow.payment <= horizon:
                cash_paid += _cashflow_amount(terms, flow, market, {0: state}, scripts.get(flow.flow_id))
        active = any(flow.payment > horizon for flow in terms.cashflows)
        yield _Population(sign * fine, np.full(count, 0 if active else 2), sign * cash_paid, float(np.max(abs(fine - coarse))))


def _rolled_name(member: CreditMcMarginal, horizon: float) -> CreditMcMarginal:
    remaining = [(end - horizon, hazard) for end, hazard in zip(member.curve.maturities, member.curve.hazards, strict=True)
                 if end > horizon]
    return member.model_copy(update={"curve": SurvivalCurve(
        maturities=tuple(end for end, _ in remaining), hazards=tuple(hazard for _, hazard in remaining),
    )})


def _live_credit_mark(request: CreditMcRequest, remaining: tuple[CreditMcMarginal, ...], horizon: float):
    old = request.contract
    coupons = tuple(CreditCoupon(start=p.start - horizon, end=p.end - horizon, payment=p.payment - horizon,
                                 observation=p.survival_time - horizon, year_fraction=p.year_fraction)
                    for p in old.coupons if p.survival_time > horizon)
    rank = old.trigger_rank
    residual_rank = None if rank is None else rank - (len(request.market.marginals) - len(remaining))
    principal = old.principal_payment_years
    contract = old.model_copy(update={
        "maturity_years": old.maturity_years - horizon, "coupons": coupons, "trigger_rank": residual_rank,
        "protected_from": max(old.protected_from - horizon, 0.0), "initial_accrued_fraction": 0.0,
        "principal_payment_years": principal - horizon if principal is not None else None,
    })
    members = tuple(_rolled_name(name, horizon) for name in remaining)
    market = request.market.model_copy(update={"marginals": members})
    shifted = request.model_copy(update={"contract": contract, "market": market})
    segments = tuple(_HazardSegments.from_curve(member.curve, contract.maturity_years) for member in members)
    times = tuple(sorted({*(p.survival_time for p in coupons), contract.maturity_years}))
    return _reference(shifted, segments, members, times)[0].dirty_pv_eur


def _credit_populations(scenario: ExoticCreditScenario, horizons: tuple[float, ...], count: int):
    request = scenario.credit
    market, contract = request.market, request.contract
    if request.realized is not None:
        raise ExoticMtfError("EXOTIC_MTF_DEFAULT_REALISED", "Le suivi du règlement réalisé est disponible dans le dossier du défaut.")
    if market.dependence_model != "independence":
        raise ExoticMtfError("EXOTIC_MTF_DEPENDENCE", "La copule requiert une loi postérieure conditionnelle aux défauts observés.")
    if any(p.survival_time != p.end for p in contract.coupons):
        raise ExoticMtfError("EXOTIC_MTF_CREDIT_SCHEDULE", "La recette crédit observe la survie à la fin de la période de coupon.")
    request, _ = resolve_credit_payoff(request)
    market, contract = request.market, request.contract
    maturity = contract.maturity_years
    principal_payment = contract.principal_payment_years or maturity
    last = max(maturity + contract.default_settlement_delay_years, principal_payment,
               *(period.payment for period in contract.coupons))
    if horizons[-1] > last:
        raise ExoticMtfError("EXOTIC_MTF_HORIZON", "Un horizon dépasse le dernier règlement possible du produit.")
    names = tuple(sorted(market.marginals, key=lambda name: name.reference_entity_id))
    generator = np.random.Generator(np.random.PCG64(request.settings.seed))
    thresholds = generator.standard_exponential((count, len(names)))
    defaults = np.column_stack([
        _HazardSegments.from_curve(name.curve, maturity).inverse(thresholds[:, index])
        for index, name in enumerate(names)
    ])
    nth = (contract.trigger_rank or 1) - 1
    order = np.argsort(defaults, axis=1, kind="stable")[:, nth]
    trigger = defaults[np.arange(count), order]
    recoveries = np.asarray([name.recovery_fraction for name in names])[order]
    sign = 1 if contract.side == "BUY" else -1
    cln = contract.kind == "cln"
    rate = market.discount_rate + market.funding_bps / 10_000
    reference_work = 0

    for horizon in horizons:
        pv, paid = np.zeros(count), np.zeros(count)
        live = (trigger > horizon) & (horizon < maturity)
        states = np.where(live, 0, 2)

        def book(eligible, due, amount):
            outstanding = eligible & (due > horizon)
            payment_days = np.maximum(due - horizon, 0.0)
            pv[:] += np.where(outstanding, amount * np.exp(-rate * payment_days), 0.0)
            paid[:] += np.where(eligible & (due <= horizon), amount, 0.0)
            states[outstanding & ~live] = 1

        coupon_rate = contract.nominal_eur * contract.coupon_bps / 10_000
        for coupon in contract.coupons:
            if coupon.survival_time <= horizon:
                amount = coupon_rate * coupon.year_fraction * (1 if cln else -1)
                book(trigger > coupon.survival_time, coupon.payment, amount)

        known_trigger = (trigger <= horizon) & (trigger >= contract.protected_from) & (trigger <= maturity)
        due = np.where(known_trigger, trigger + contract.default_settlement_delay_years, 0.0)
        recovery = contract.nominal_eur * (recoveries if cln else 1.0 - recoveries)
        if not cln:
            for coupon in contract.coupons:
                accrues = known_trigger & (trigger >= coupon.start) & (trigger < coupon.end)
                elapsed = np.where(accrues, trigger, coupon.start) - coupon.start
                recovery -= coupon_rate * coupon.year_fraction * elapsed / (coupon.end - coupon.start)
        book(known_trigger, due, recovery)
        if cln and maturity <= horizon:
            book(trigger > maturity, principal_payment, contract.nominal_eur)

        # Continuing paths are grouped on the set alive at the horizon. They
        # receive the same conditional value regardless of later sampled defaults.
        if live.any():
            masks, inverse = np.unique(defaults[live] > horizon, axis=0, return_inverse=True)
            if len(masks) > _MAX_LIVE_STATES:
                raise ExoticMtfError("EXOTIC_MTF_CREDIT_STATES", "La population des états survivants dépasse la limite du pilote.")
            survivors = [tuple(name for name, alive in zip(names, mask, strict=True) if alive) for mask in masks]
            reference_work += sum(len(members)**2 * (len(contract.coupons) + sum(len(name.curve.hazards) for name in members))
                                  for members in survivors)
            if reference_work > _MAX_CREDIT_REFERENCE_WORK:
                raise ExoticMtfError("EXOTIC_MTF_WORK_LIMIT", "Réduisez les horizons, le nombre de noms ou les trajectoires.")
            marks = np.array([_live_credit_mark(request, members, horizon) for members in survivors])
            pv[live] += marks[inverse]
        yield _Population(sign * pv, states, sign * paid)


def mark_exotic_to_future(
    scenario: ExoticScenario, *, horizons_years: tuple[float, ...], paths: int = 1024,
    archived_result: dict | None = None,
) -> ExoticMtfResult:
    """Mark the remaining contract at each horizon in that date's EUR."""
    if not 64 <= paths <= 4096 or not 1 <= len(horizons_years) <= 12 or not all(
        np.isfinite(horizon) and 0 < horizon <= 100 for horizon in horizons_years
    ) or any(left >= right for left, right in zip(horizons_years, horizons_years[1:])):
        raise ExoticMtfError("EXOTIC_MTF_GRID", "Choisissez des horizons positifs et croissants et 64 à 4 096 trajectoires.")
    is_rates = isinstance(scenario, ExoticRatesScenario)
    parameters = scenario.settings if is_rates else scenario.credit.settings
    warnings = ("La PV à l’horizon exclut les flux à cette date et les flux antérieurs. Le cash cumulé est présenté séparément.",)
    if is_rates:
        method = "conditional_hull_white_1f"
        populations = _rates_populations(scenario, horizons_years, paths, archived_result)
        if scenario.terms.exercises:
            warnings += ("Politique d’exercice du reçu figée. Quadrature arrière et interpolation de la valeur conditionnelle.",)
    else:
        method = "conditional_independent_credit"
        populations = _credit_populations(scenario, horizons_years, paths)
        warnings += ("Les intensités restantes sont conditionnées sur les noms vivants. Aucun nouveau spread de marché n’est simulé.",)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            summaries = tuple(_summarize(horizon, values)
                              for horizon, values in zip(horizons_years, populations, strict=True))
    except ArithmeticError as exc:
        raise ExoticMtfError("EXOTIC_MTF_NUMERICAL", "Le calcul conditionnel sort du domaine numérique.") from exc
    return ExoticMtfResult(
        family=scenario.family, position_id=scenario.position_id, cutoff=scenario.cutoff,
        valuation_date=scenario.valuation_date, method=method, seed=parameters.seed, paths=paths,
        horizons=summaries, warnings=warnings,
    )
