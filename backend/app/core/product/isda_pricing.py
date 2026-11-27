"""EUR RFR ISDA historical CDS converter, version 1.8.3 conventions."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from math import exp, expm1, factorial, fsum, log
from typing import Literal

from dateutil.relativedelta import relativedelta
from pydantic import Field, model_validator
from scipy.optimize import brentq

from ..schedule import parse_tenor
from .cds_schedule import _following_weekday
from .isda_market import IsdaMarketSelection, _OisQuotes
from .models import CDSTerms, FrozenModel, Product
from .native_market import NativeValuationContext
from .native_schedule_models import SchedulePeriod


_BASIS_POINT = 0.0001
_ONE_DAY = timedelta(days=1)
_ENGINE_VERSION = "isda-eur-rfr-converter-v1"


class IsdaPricingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class IsdaOisPillar(FrozenModel):
    maturity_date: date
    tenor: str
    source_cells: str
    input_rate_fraction: float
    discount_factor: float = Field(gt=0)
    repriced_rate_fraction: float
    residual_rate_fraction: float


class IsdaDiscountCurve(FrozenModel):
    """Rebased EUR €STR factors with the original swap-pillar repricing."""

    profile: Literal["isda_eur_rfr_2021-04-07"] = "isda_eur_rfr_2021-04-07"
    currency: Literal["EUR"] = "EUR"
    index: Literal["ESTR"] = "ESTR"
    interpolation: Literal["log_linear_discount_factors"] = "log_linear_discount_factors"
    anchor_date: date
    spot_date: date
    pillars: tuple[IsdaOisPillar, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def chronological_pillars(self):
        dates = (self.anchor_date, *(pillar.maturity_date for pillar in self.pillars))
        if not self.anchor_date < self.spot_date < dates[1] or any(left >= right for left, right in pairwise(dates)):
            raise ValueError("Ancrage, spot ou échéances de la courbe ISDA incohérents.")
        return self

    def log_factor_at(self, day: date) -> float:
        if not self.anchor_date <= day <= self.pillars[-1].maturity_date:
            raise IsdaPricingError("ISDA_CURVE_COVERAGE", f"La courbe OIS ISDA ne couvre pas le {day:%d/%m/%Y}.")
        nodes = ((self.anchor_date, 0.0), *((node.maturity_date, log(node.discount_factor)) for node in self.pillars))
        return _log_interpolate(day, nodes)

    def factor_at(self, day: date) -> float:
        return exp(self.log_factor_at(day))


class IsdaPremiumFlow(FrozenModel):
    leg_id: str
    period_id: str
    flow_id: str
    rank: int
    accrual_start: date
    accrual_end_exclusive: date
    credit_observation_date: date
    payment_date: date
    act360_days: int
    discount_factor: float = Field(gt=0)
    survival_fraction: float = Field(ge=0, le=1)
    amount_eur_if_survives: float
    scheduled_pv_eur: float
    accrual_on_default_pv_eur: float


class IsdaCdsPriceResult(FrozenModel):
    schema_version: Literal[1] = 1
    engine_version: Literal["isda-eur-rfr-converter-v1"] = _ENGINE_VERSION
    instrument_type: Literal["CDS"] = "CDS"
    market_quality: Literal["historical_benchmark"] = "historical_benchmark"
    currency: Literal["EUR"] = "EUR"
    position_side: Literal["BUY", "SELL"]
    perspective: Literal["buy_protection", "sell_protection"]
    product_id: int | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    context_fingerprint: str
    nominal_eur: float = Field(gt=0)
    valuation_date: date
    cutoff: datetime
    step_in_date: date
    protection_end_inclusive_date: date
    final_premium_payment_date: date
    initial_cash_settlement_date: date
    initial_settlement_flow_id: str
    initial_settlement_discount_factor: float = Field(gt=0)
    benchmark_id: str
    scenario_id: str
    scenario_source_cells: str
    quoted_spread_bps: float
    coupon_bps: float
    calibration_recovery_fraction: float
    pricing_recovery_fraction: float
    constant_hazard_rate: float = Field(ge=0)
    terminal_survival_fraction: float = Field(ge=0, le=1)
    calibration_residual_fraction: float
    clean_annuity_years: float = Field(gt=0)
    par_spread_bps: float
    clean_upfront_fraction: float
    clean_price_per_100: float
    accrued_days: int = Field(ge=0)
    accrued_premium_eur: float = Field(ge=0)
    cash_settlement_eur_buyer_to_seller: float
    position_settlement_cash_eur: float
    protection_pv_eur: float
    scheduled_premium_pv_eur: float
    accrual_on_default_pv_eur: float
    dirty_pv_eur: float
    clean_pv_eur: float
    cs01_eur: float
    premium_flows: tuple[IsdaPremiumFlow, ...]
    ois_curve: IsdaDiscountCurve


def _log_interpolate(day: date, nodes: tuple[tuple[date, float], ...]) -> float:
    right = bisect_left(nodes, day, key=lambda node: node[0])
    if nodes[right][0] == day:
        return nodes[right][1]
    # When called before spot during rebase only, use the first OIS forward
    # from spot to the first quoted maturity. The rebased curve has no extrapolation.
    right = max(right, 1)
    start, start_log = nodes[right - 1]
    end, end_log = nodes[right]
    weight = (day - start).days / (end - start).days
    return start_log + (end_log - start_log) * weight


def _modified_following_weekday(day: date) -> date:
    following = _following_weekday(day)
    return following if following.month == day.month else day - timedelta(days=day.weekday() - 4)


@dataclass(frozen=True)
class _OisSwap:
    tenor: str
    source_cells: str
    rate: float
    coupons: tuple[tuple[date, float], ...]

    @property
    def maturity(self) -> date:
        return self.coupons[-1][0]


def _swap_coupons(spot: date, tenor: str) -> tuple[tuple[date, float], ...]:
    interval = parse_tenor(tenor)
    if interval.unit not in {"M", "Y"}:
        raise IsdaPricingError("ISDA_OIS_TENOR", f"Tenor OIS ISDA incompatible : {tenor}.")
    months = interval.value * (12 if interval.unit == "Y" else 1)
    rolls = (*range(12, months, 12), months)
    dates = (spot, *(_modified_following_weekday(spot + relativedelta(months=roll)) for roll in rolls))
    return tuple((end, (end - start).days / 360) for start, end in pairwise(dates))


def build_isda_ois_curve(quotes: _OisQuotes) -> IsdaDiscountCurve:
    """Bootstrap the 17 swaps at spot, then rebase the factors to trade date."""
    spot, anchor = quotes.chronology.spot_date, quotes.chronology.anchor_date
    swaps = tuple(_OisSwap(quote.tenor, quote.source_cells, quote.rate, _swap_coupons(spot, quote.tenor))
                  for quote in quotes.rows)
    nodes = ((spot, 0.0),)
    for swap in swaps:
        if swap.maturity <= nodes[-1][0]:
            raise IsdaPricingError("ISDA_OIS_ORDER", "Les échéances des swaps OIS doivent être strictement croissantes.")

        def bootstrap_residual(last_log_factor: float) -> float:
            candidate = (*nodes, (swap.maturity, last_log_factor))
            annuity = fsum(fraction * exp(_log_interpolate(day, candidate)) for day, fraction in swap.coupons)
            return exp(last_log_factor) + swap.rate * annuity - 1

        try:
            # This fixed historical grid has rates between -60 and +34 bp.
            # The log-factor bracket is deliberately wide and preserves positivity.
            log_factor = brentq(bootstrap_residual, -8.0, 8.0, xtol=1e-15)
        except ValueError as exc:
            raise IsdaPricingError("ISDA_OIS_CALIBRATION", f"Aucun facteur OIS admissible au tenor {swap.tenor}.") from exc
        nodes = (*nodes, (swap.maturity, log_factor))

    anchor_log = _log_interpolate(anchor, nodes)
    pillars = []
    for swap, (maturity, spot_log_factor) in zip(swaps, nodes[1:], strict=True):
        annuity = fsum(fraction * exp(_log_interpolate(day, nodes)) for day, fraction in swap.coupons)
        repriced = -expm1(spot_log_factor) / annuity
        pillars.append(IsdaOisPillar(
            maturity_date=maturity, tenor=swap.tenor, source_cells=swap.source_cells,
            input_rate_fraction=swap.rate, discount_factor=exp(spot_log_factor - anchor_log),
            repriced_rate_fraction=repriced, residual_rate_fraction=repriced - swap.rate,
        ))
    return IsdaDiscountCurve(anchor_date=anchor, spot_date=spot, pillars=tuple(pillars))


def _exponential_moments(total_hazard_and_forward: float) -> tuple[float, float]:
    """Integrals of exp(-x*u) and u*exp(-x*u) on [0, 1]."""
    x = total_hazard_and_forward
    if abs(x) < 0.02:
        series = tuple((-x) ** term / factorial(term) for term in range(8))
        zero = fsum(value / (term + 1) for term, value in enumerate(series))
        first = fsum(value / (term + 2) for term, value in enumerate(series))
        return zero, first
    minus_delta = -expm1(-x)
    return minus_delta / x, (minus_delta - x * exp(-x)) / (x * x)


@dataclass(frozen=True)
class _Segment:
    start_years: float
    length_years: float
    log_discount_start: float
    integrated_forward: float
    accrued_intercept: float
    accrued_change: float

    def integrate(self, hazard: float) -> float:
        integrated_hazard = hazard * self.length_years
        moment_zero, moment_one = _exponential_moments(integrated_hazard + self.integrated_forward)
        risk_discount = exp(self.log_discount_start - hazard * self.start_years)
        return integrated_hazard * risk_discount * (
            self.accrued_intercept * moment_zero + self.accrued_change * moment_one
        )


def _segments(curve: IsdaDiscountCurve, start: date, end: date, *,
              accrual_origin: date | None = None) -> tuple[_Segment, ...]:
    if end <= start:
        return ()
    cuts = (start, *(node.maturity_date for node in curve.pillars if start < node.maturity_date < end), end)
    segments = []
    for left, right in pairwise(cuts):
        left_log, right_log = curve.log_factor_at(left), curve.log_factor_at(right)
        days = (right - left).days
        # The historical ISDA integration credits a half-day on default, with
        # accrual time measured from the start-of-day observation boundary.
        intercept = ((left - accrual_origin).days + 0.5) / 360 if accrual_origin is not None else 1.0
        change = days / 360 if accrual_origin is not None else 0.0
        segments.append(_Segment(
            (left - curve.anchor_date).days / 365, days / 365, left_log, left_log - right_log, intercept, change,
        ))
    return tuple(segments)


@dataclass(frozen=True)
class _PeriodInputs:
    period: SchedulePeriod
    observation_date: date
    observation_years: float
    discount: float
    default_segments: tuple[_Segment, ...]

    def scheduled_annuity(self, hazard: float) -> float:
        return self.period.year_fraction * self.discount * exp(-hazard * self.observation_years)

    def default_annuity(self, hazard: float) -> float:
        return fsum(segment.integrate(hazard) for segment in self.default_segments)


@dataclass(frozen=True)
class _Conversion:
    protection: tuple[_Segment, ...]
    periods: tuple[_PeriodInputs, ...]
    recovery: float
    accrued_fraction: float
    settlement_discount: float

    def default_leg(self, hazard: float) -> float:
        return (1 - self.recovery) * fsum(segment.integrate(hazard) for segment in self.protection)

    def clean_annuity(self, hazard: float) -> float:
        return fsum(item.scheduled_annuity(hazard) + item.default_annuity(hazard) for item in self.periods) - (
            self.accrued_fraction * self.settlement_discount
        )

    def fit(self, spread: float) -> float:
        def objective(hazard: float) -> float:
            return self.default_leg(hazard) - spread * self.clean_annuity(hazard)

        ceiling = max(0.05, 2 * spread / (1 - self.recovery))
        while objective(ceiling) < 0 and ceiling < 16:
            ceiling *= 2
        try:
            return brentq(objective, 0.0, ceiling, xtol=1e-15)
        except ValueError as exc:
            raise IsdaPricingError("ISDA_HAZARD_CALIBRATION", "Aucune intensité constante admissible ne réplique la cote CDS.") from exc


def _check_binding(product: Product, context: NativeValuationContext) -> IsdaMarketSelection:
    terms, schedule, market = product.terms, product.native_schedule, context.market
    if not isinstance(terms, CDSTerms) or not isinstance(market, IsdaMarketSelection):
        raise IsdaPricingError("ISDA_PRODUCT_INCOMPATIBLE", "Le convertisseur requiert le contexte historique d’un CDS EUR.")
    version = product.terms_version if product.product_id is not None else None
    if schedule is None or (
        product.product_id, version, terms.fingerprint, schedule.fingerprint,
    ) != (
        context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
    ) or (schedule.product_id, schedule.terms_version, schedule.terms_fingerprint, schedule.instrument_type) != (
        context.product_id, context.terms_version, context.terms_fingerprint, "CDS",
    ):
        raise IsdaPricingError("ISDA_CONTEXT_MISMATCH", "Le contexte ISDA ne correspond pas aux termes et à l’échéancier figés.")
    if (context.valuation_date, context.value_date, terms.premium_leg.coupon_bps, context.nominal) != (
        market.cds_chronology.trade_date, market.cds_chronology.trade_date,
        market.contract_terms.coupon_bp, market.contract_terms.notional_eur,
    ):
        raise IsdaPricingError("ISDA_CONTEXT_MISMATCH", "Arrêté, nominal ou coupon incompatibles avec le témoin ISDA.")
    return market


def price_isda_cds(product: Product, context: NativeValuationContext) -> IsdaCdsPriceResult:
    """Convert one historical quoted spread at one maturity, using inputs only."""
    market = _check_binding(product, context)
    schedule = product.native_schedule
    if tuple(leg.kind for leg in schedule.legs) != ("premium", "protection", "initial_settlement"):
        raise IsdaPricingError("ISDA_SCHEDULE_INCOMPATIBLE", "Les jambes du convertisseur CDS sont incomplètes.")
    premium, protection, settlement = schedule.legs
    chronology = market.cds_chronology
    if tuple((event.kind, event.date) for event in protection.events) != (
        ("step_in", chronology.step_in_date), ("protection_end", chronology.protection_end_inclusive_date),
    ) or len(settlement.events) != 1 or not premium.periods:
        raise IsdaPricingError("ISDA_SCHEDULE_INCOMPATIBLE", "Les bornes de protection et de règlement du CDS sont incomplètes.")
    initial, = settlement.events
    if (initial.kind != "initial_settlement" or initial.date != chronology.initial_cash_settlement_date
            or initial.flow_id is None or initial.accrued_days is None):
        raise IsdaPricingError("ISDA_SCHEDULE_INCOMPATIBLE", "Le règlement initial n’est pas résolu dans l’échéancier CDS.")

    curve = build_isda_ois_curve(market.ois_quotes)
    protection_start = chronology.step_in_date - _ONE_DAY
    protection_end = chronology.protection_end_inclusive_date
    periods = []
    for period in premium.periods:
        observation = period.credit_observation_date
        if (
            observation != period.accrual_end - _ONE_DAY or period.day_count != "ACT/360"
            or period.day_count_days != (period.accrual_end - period.accrual_start).days
        ):
            raise IsdaPricingError("ISDA_SCHEDULE_INCOMPATIBLE", f"Couru ou observation incompatible pour {period.period_id}.")
        accrual_origin = period.accrual_start - _ONE_DAY
        periods.append(_PeriodInputs(
            period, observation, (observation - curve.anchor_date).days / 365, curve.factor_at(period.payment_date),
            _segments(curve, max(protection_start, accrual_origin), observation, accrual_origin=accrual_origin),
        ))
    scenario = market.scenario
    recovery = scenario.market_inputs.calibration_recovery_fraction
    quoted_spread_bps = scenario.market_inputs.quoted_spread_bp
    quoted_spread = quoted_spread_bps * _BASIS_POINT
    coupon_bps = market.contract_terms.coupon_bp
    coupon = coupon_bps * _BASIS_POINT
    model = _Conversion(
        _segments(curve, protection_start, protection_end), tuple(periods),
        recovery, initial.accrued_days / 360, curve.factor_at(initial.date),
    )
    hazard = model.fit(quoted_spread)
    bumped_hazard = model.fit(quoted_spread + _BASIS_POINT)
    protection_unit = model.default_leg(hazard)
    annuity = model.clean_annuity(hazard)
    if annuity <= 0:
        raise IsdaPricingError("ISDA_ANNUITY_INVALID", "L’annuité clean du CDS doit être strictement positive.")
    clean_unit = protection_unit - coupon * annuity
    accrued_unit = coupon * model.accrued_fraction
    dirty_unit = clean_unit - accrued_unit * model.settlement_discount
    upfront = clean_unit / model.settlement_discount
    multiplier = context.nominal if context.side == "BUY" else -context.nominal
    flows = tuple(IsdaPremiumFlow(
        leg_id=premium.leg_id, period_id=item.period.period_id, flow_id=item.period.flow_id, rank=item.period.rank,
        accrual_start=item.period.accrual_start, accrual_end_exclusive=item.period.accrual_end,
        credit_observation_date=item.observation_date, payment_date=item.period.payment_date,
        act360_days=item.period.day_count_days, discount_factor=item.discount,
        survival_fraction=exp(-hazard * item.observation_years),
        amount_eur_if_survives=-multiplier * coupon * item.period.year_fraction,
        scheduled_pv_eur=-multiplier * coupon * item.scheduled_annuity(hazard),
        accrual_on_default_pv_eur=-multiplier * coupon * item.default_annuity(hazard),
    ) for item in periods)
    settlement_amount = context.nominal * (upfront - accrued_unit)
    bumped_clean_unit = model.default_leg(bumped_hazard) - coupon * model.clean_annuity(bumped_hazard)

    return IsdaCdsPriceResult(
        product_id=context.product_id, terms_version=context.terms_version, terms_fingerprint=context.terms_fingerprint,
        schedule_fingerprint=context.schedule_fingerprint, context_fingerprint=context.fingerprint,
        position_side=context.side, perspective="buy_protection" if context.side == "BUY" else "sell_protection",
        nominal_eur=context.nominal, valuation_date=context.valuation_date, cutoff=context.cutoff,
        step_in_date=chronology.step_in_date, protection_end_inclusive_date=protection_end,
        final_premium_payment_date=chronology.final_premium_payment_date, initial_cash_settlement_date=initial.date,
        initial_settlement_flow_id=initial.flow_id, initial_settlement_discount_factor=model.settlement_discount,
        benchmark_id=market.benchmark_id, scenario_id=scenario.id, scenario_source_cells=scenario.source_cells,
        quoted_spread_bps=quoted_spread_bps, coupon_bps=coupon_bps,
        calibration_recovery_fraction=recovery, pricing_recovery_fraction=recovery, constant_hazard_rate=hazard,
        terminal_survival_fraction=exp(-hazard * (protection_end - curve.anchor_date).days / 365),
        calibration_residual_fraction=protection_unit - quoted_spread * annuity,
        clean_annuity_years=annuity, par_spread_bps=protection_unit / annuity / _BASIS_POINT,
        clean_upfront_fraction=upfront, clean_price_per_100=100 * (1 - upfront),
        accrued_days=initial.accrued_days, accrued_premium_eur=context.nominal * accrued_unit,
        cash_settlement_eur_buyer_to_seller=settlement_amount,
        position_settlement_cash_eur=-settlement_amount if context.side == "BUY" else settlement_amount,
        protection_pv_eur=multiplier * protection_unit,
        scheduled_premium_pv_eur=fsum(flow.scheduled_pv_eur for flow in flows),
        accrual_on_default_pv_eur=fsum(flow.accrual_on_default_pv_eur for flow in flows),
        dirty_pv_eur=multiplier * dirty_unit, clean_pv_eur=multiplier * clean_unit,
        cs01_eur=multiplier * (bumped_clean_unit - clean_unit),
        premium_flows=flows, ois_curve=curve,
    )
