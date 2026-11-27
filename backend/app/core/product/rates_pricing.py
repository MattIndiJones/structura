"""Deterministic EUR FRN and IRS valuation on frozen contractual and market inputs."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from math import exp, expm1, fsum, log
from typing import Annotated, Literal

from pydantic import Field

from .models import FRNTerms, FrozenModel, IRSTerms, Product
from .native_market import NativeValuationContext
from .native_schedule_models import NativeSchedule, SchedulePeriod
from .rates_market import RatesMarketSelection


_BP = 0.0001
_ENGINE_VERSION = "eur-rates-deterministic-v1"

Instrument = Literal["FRN", "IRS"]
FlowKind = Literal["floating_coupon", "fixed_coupon", "principal"]
RateOrigin = Literal["projected", "fixing", "contractual"]
FixingState = Literal["projected", "fixed"]


class RatesPricingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RatesPayoffInput(FrozenModel):
    instrument_type: Instrument
    flow_id: str
    leg_id: str
    kind: FlowKind
    period_id: str | None = None
    rank: int | None = None
    payment_date: date
    nominal_eur: float
    accrual_fraction: float | None = None
    day_count_days: int | None = None
    rate: float | None = None
    margin_bps: float | None = None
    redemption_fraction: float | None = None
    fixing_state: FixingState | None = None
    rate_origin: RateOrigin | None = None
    is_fixed: bool = False
    is_accrual: bool = False


class RatesPayoffAmount(FrozenModel):
    """Amount in the leg's receive direction, before the position sign."""

    amount_eur: float
    label: str | None = None


RatesPayoff = Callable[[RatesPayoffInput], RatesPayoffAmount]


class RatesPriceFlow(FrozenModel):
    flow_id: str
    leg_id: str
    kind: FlowKind
    period_id: str | None = None
    rank: int | None = None
    payment_date: date
    accrual_start: date | None = None
    accrual_end: date | None = None
    accrual_fraction: float | None = None
    day_count: Literal["ACT/360", "30E/360"] | None = None
    day_count_days: int | None = None
    fixing_date: date | None = None
    fixing_state: FixingState | None = None
    rate_origin: RateOrigin | None = None
    rate: float | None = None
    margin_bps: float | None = None
    state: Literal["future", "due_open", "paid"]
    bucket: Literal["attached", "detached", "cash"]
    amount_eur: float
    pv_eur: float
    discount_factor: float | None = None
    fixing_id: str | None = None
    fixing_version: int | None = None
    payment_fact_id: str | None = None
    payment_version: int | None = None
    paid_date: date | None = None
    label: str | None = None


class RatesMeasure(FrozenModel):
    kind: Literal["frn_clean_price", "irs_net_pv"]
    unit: Literal["per_100_notional", "EUR"]
    value: float


class RatesSensitivities(FrozenModel):
    bump_bp: Literal[1] = 1
    discount_eur: float
    projection_eur: float


class _RatesResult(FrozenModel):
    schema_version: Literal[1] = 1
    engine_version: Literal["eur-rates-deterministic-v1"] = _ENGINE_VERSION
    payoff_mode: Literal["native", "scripted"]
    qualification: Literal["deterministic_reference", "deterministic_scenario"]
    market_quality: Literal["synthetic"] = "synthetic"
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float
    position_side: Literal["BUY", "SELL"]
    valuation_date: date
    value_date: date
    cutoff: datetime
    product_id: int | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    context_fingerprint: str
    market_id: str
    market_version: int
    market_fingerprint: str
    measure: RatesMeasure
    sensitivities: RatesSensitivities
    flows: tuple[RatesPriceFlow, ...]
    detached_pv_eur: float
    economic_pv_eur: float
    realized_cash_eur: float
    cash_on_value_date_eur: float
    cum_value_eur: float


class FRNPriceResult(_RatesResult):
    instrument_type: Literal["FRN"] = "FRN"
    perspective: Literal["long", "short"]
    funding_spread_bps: float
    clean_price_per_100: float
    dirty_pv_eur: float
    clean_pv_eur: float
    accrued_eur: float
    coupon_pv_eur: float
    principal_pv_eur: float


class IRSPriceResult(_RatesResult):
    instrument_type: Literal["IRS"] = "IRS"
    perspective: Literal["receive_fixed", "pay_fixed"]
    net_pv_eur: float
    fixed_pv_eur: float
    floating_pv_eur: float
    fixed_coupon_rate: float
    par_rate: float | None
    fixed_annuity_eur: float | None


RatesPriceResult = Annotated[FRNPriceResult | IRSPriceResult, Field(discriminator="instrument_type")]


@dataclass(frozen=True)
class _Valuation:
    flows: tuple[RatesPriceFlow, ...]
    accrued_eur: float
    fixed_annuity_eur: float

    @property
    def attached_pv_eur(self) -> float:
        return fsum(flow.pv_eur for flow in self.flows if flow.bucket == "attached")

    def attached_leg_pv(self, kind: FlowKind) -> float:
        return fsum(flow.pv_eur for flow in self.flows if flow.bucket == "attached" and flow.kind == kind)


def price_rates(
    product: Product,
    context: NativeValuationContext,
    *,
    payoff: RatesPayoff | None = None,
    equivalent_payoff: bool = False,
) -> FRNPriceResult | IRSPriceResult:
    """Price the attached contract, separately reconciling detached rights and paid cash.

    A payoff callback computes an undiscounted amount in the receive direction of
    one leg. The same callback is evaluated for projected shocks and the FRN's
    partial coupon period. The caller certifies vanilla equivalence when it
    supplies a callback and requests the reference pricing and swap par formula.
    """
    terms, schedule, market = _check_binding(product, context)
    if terms.payoff_mode == "scripted" and payoff is None:
        raise RatesPricingError("RATES_PRICE_PAYOFF_REQUIRED", "Le payoff PayScript du dossier doit être fourni pour la valorisation.")
    direction = 1 if context.side == "BUY" else -1
    equivalent = payoff is None or equivalent_payoff
    amount_for = payoff if payoff is not None else _template_amount
    base = _value(terms, schedule, market, context.nominal, direction, amount_for)
    ois = _value(terms, schedule, market, context.nominal, direction, amount_for, discount_bump=_BP)
    projection = _value(terms, schedule, market, context.nominal, direction, amount_for, projection_bump=_BP)
    attached = base.attached_pv_eur
    detached = fsum(flow.pv_eur for flow in base.flows if flow.bucket == "detached")
    cash = fsum(flow.amount_eur for flow in base.flows if flow.bucket == "cash")
    same_day_cash = fsum(flow.amount_eur for flow in base.flows if flow.paid_date == context.value_date)
    common = {
        "payoff_mode": "native" if payoff is None else "scripted",
        "qualification": "deterministic_reference" if equivalent else "deterministic_scenario",
        "nominal_eur": context.nominal, "position_side": context.side,
        "valuation_date": context.valuation_date, "value_date": context.value_date, "cutoff": context.cutoff,
        "product_id": context.product_id, "terms_version": context.terms_version,
        "terms_fingerprint": context.terms_fingerprint, "schedule_fingerprint": context.schedule_fingerprint,
        "context_fingerprint": context.fingerprint, "market_id": market.market_id,
        "market_version": market.market_version, "market_fingerprint": market.market_fingerprint,
        "sensitivities": RatesSensitivities(
            discount_eur=ois.attached_pv_eur - attached, projection_eur=projection.attached_pv_eur - attached,
        ),
        "flows": base.flows, "detached_pv_eur": detached, "economic_pv_eur": attached + detached,
        "realized_cash_eur": cash, "cash_on_value_date_eur": same_day_cash,
        "cum_value_eur": attached + detached + same_day_cash,
    }
    if isinstance(terms, FRNTerms):
        clean = attached - base.accrued_eur
        price = 100 * clean / context.nominal
        return FRNPriceResult(
            **common, perspective="long" if direction == 1 else "short",
            funding_spread_bps=market.frn_funding_bps,
            measure=RatesMeasure(kind="frn_clean_price", unit="per_100_notional", value=price),
            clean_price_per_100=price, dirty_pv_eur=attached, clean_pv_eur=clean, accrued_eur=base.accrued_eur,
            coupon_pv_eur=base.attached_leg_pv("floating_coupon"), principal_pv_eur=base.attached_leg_pv("principal"),
        )

    fixed, floating = base.attached_leg_pv("fixed_coupon"), base.attached_leg_pv("floating_coupon")
    annuity = base.fixed_annuity_eur if equivalent else None
    return IRSPriceResult(
        **common, perspective="receive_fixed" if direction == 1 else "pay_fixed",
        measure=RatesMeasure(kind="irs_net_pv", unit="EUR", value=attached),
        fixed_pv_eur=fixed, floating_pv_eur=floating, net_pv_eur=attached,
        fixed_coupon_rate=terms.fixed_leg.coupon_rate, fixed_annuity_eur=annuity,
        par_rate=-direction * floating / annuity if annuity else None,
    )


def _check_binding(
    product: Product, context: NativeValuationContext,
) -> tuple[FRNTerms | IRSTerms, NativeSchedule, RatesMarketSelection]:
    terms, market, schedule = product.terms, context.market, product.native_schedule
    if not isinstance(terms, (FRNTerms, IRSTerms)) or not isinstance(market, RatesMarketSelection):
        raise RatesPricingError("RATES_PRICE_UNSUPPORTED", "La valorisation de taux requiert un FRN ou un IRS EUR.")
    terms_version = product.terms_version if product.product_id is not None else None
    if schedule is None or (
        product.product_id, terms_version, terms.instrument_type, terms.fingerprint, schedule.fingerprint,
    ) != (
        context.product_id, context.terms_version, context.instrument_type, context.terms_fingerprint,
        context.schedule_fingerprint,
    ) or (
        schedule.product_id, schedule.terms_version, schedule.instrument_type, schedule.terms_fingerprint,
    ) != (
        context.product_id, context.terms_version, context.instrument_type, context.terms_fingerprint,
    ):
        raise RatesPricingError("RATES_PRICE_CONTEXT_MISMATCH", "Le contexte ne correspond pas aux termes et à l’échéancier figés.")
    if context.valuation_date != context.value_date:
        raise RatesPricingError("RATES_PRICE_VALUE_DATE", "La date de valeur doit être la date de valorisation pour ce profil.")
    if terms.floating_leg.margin_bps is None or (isinstance(terms, IRSTerms) and terms.fixed_leg.coupon_rate is None):
        raise RatesPricingError("RATES_PRICE_TERMS_INCOMPLETE", "Renseignez les paramètres contractuels des coupons.")
    return terms, schedule, market


def _template_amount(inputs: RatesPayoffInput) -> RatesPayoffAmount:
    if inputs.kind == "principal":
        return RatesPayoffAmount(amount_eur=inputs.nominal_eur * inputs.redemption_fraction)
    rate = inputs.rate
    if inputs.margin_bps is not None:
        rate += inputs.margin_bps * _BP
    return RatesPayoffAmount(amount_eur=inputs.nominal_eur * inputs.accrual_fraction * rate)


def _project_rate(period: SchedulePeriod, market: RatesMarketSelection, bump: float) -> float:
    start, end = period.projection_start, period.projection_end
    if start is None or end is None or start >= end:
        raise RatesPricingError("RATES_PRICE_CONTEXT_MISMATCH", f"Bornes de projection invalides pour {period.period_id}.")
    curve = market.projection
    # A parallel continuous-zero shock adds bump * (T_end - T_start) to
    # log(P_start / P_end); the contractual ACT/360 denominator stays fixed.
    log_ratio = log(curve.factor_at(start)) - log(curve.factor_at(end))
    return expm1(log_ratio + bump * (end - start).days / 365) / period.year_fraction


def _value(
    terms: FRNTerms | IRSTerms,
    schedule: NativeSchedule,
    market: RatesMarketSelection,
    nominal: float,
    direction: int,
    amount_for: RatesPayoff,
    *,
    discount_bump: float = 0.0,
    projection_bump: float = 0.0,
) -> _Valuation:
    is_frn = isinstance(terms, FRNTerms)
    funding = market.frn_funding_bps * _BP if is_frn else 0.0
    states = {item.flow_id: item for item in market.flows}
    fixings = {(item.fixing_id, item.version): item for item in market.fixings}
    payments = {(item.fact_id, item.version, item.flow_id): item for item in market.payments}
    flows = []
    accrued = []
    fixed_annuity = []
    for leg in schedule.legs:
        if leg.kind not in {"floating_coupon", "fixed_coupon", "principal"}:
            raise RatesPricingError("RATES_PRICE_CONTEXT_MISMATCH", f"Jambe de taux inattendue : {leg.leg_id}.")
        leg_sign = -direction if not is_frn and leg.kind == "floating_coupon" else direction
        for item in (*leg.periods, *leg.events):
            period = item if isinstance(item, SchedulePeriod) else None
            payment_date = period.payment_date if period is not None else item.date
            period_id = period.period_id if period is not None else None
            state = states.pop(item.flow_id, None)
            if state is None or (state.leg_id, state.period_id, state.payment_date) != (leg.leg_id, period_id, payment_date):
                raise RatesPricingError("RATES_PRICE_CONTEXT_MISMATCH", f"État de flux incompatible : {item.flow_id}.")

            rate, margin, redemption, origin = None, None, None, None
            if leg.kind == "floating_coupon":
                margin = terms.floating_leg.margin_bps
                if state.fixing_state == "fixed":
                    fixing = fixings.get((state.fixing_id, state.fixing_version))
                    if fixing is None or fixing.observation_date != period.fixing_date:
                        raise RatesPricingError("RATES_PRICE_FIXING_REQUIRED", f"Fixing acquis introuvable pour {period_id}.")
                    rate, origin = fixing.rate, "fixing"
                elif state.fixing_state == "projected" and state.state != "paid":
                    rate, origin = _project_rate(period, market, projection_bump), "projected"
                else:
                    raise RatesPricingError("RATES_PRICE_FIXING_REQUIRED", f"État du fixing manquant pour {period_id}.")
            elif not is_frn and leg.kind == "fixed_coupon":
                rate, origin = terms.fixed_leg.coupon_rate, "contractual"
            elif is_frn and leg.kind == "principal":
                redemption = terms.redemption_fraction

            request = RatesPayoffInput(
                instrument_type=terms.instrument_type, flow_id=item.flow_id, leg_id=leg.leg_id, kind=leg.kind,
                period_id=period_id, rank=period.rank if period is not None else None, payment_date=payment_date,
                nominal_eur=nominal, accrual_fraction=period.year_fraction if period is not None else None,
                day_count_days=period.day_count_days if period is not None else None,
                rate=rate, margin_bps=margin, redemption_fraction=redemption, fixing_state=state.fixing_state,
                rate_origin=origin, is_fixed=origin in {"fixing", "contractual"},
            )
            paid_date, discount_factor, label = None, None, None
            if state.state == "paid":
                payment = payments.get((state.payment_fact_id, state.payment_version, request.flow_id))
                if payment is None:
                    raise RatesPricingError("RATES_PRICE_PAYMENT_REQUIRED", f"Confirmation introuvable pour {request.flow_id}.")
                paid_date, amount, pv, bucket = payment.effect_date, payment.amount_eur, 0.0, "cash"
            else:
                discount_date = request.payment_date
                if state.state == "due_open" and market.overdue_treatment == "face_at_valuation_date":
                    discount_date = max(discount_date, market.valuation_date)
                years = (discount_date - market.valuation_date).days / 365
                discount_factor = market.discount.factor_at(discount_date) * exp(-(discount_bump + funding) * years)
                calculated = amount_for(request)
                amount, label = leg_sign * calculated.amount_eur, calculated.label
                pv, bucket = amount * discount_factor, "attached" if state.state == "future" else "detached"
                if bucket == "attached" and leg.kind == "fixed_coupon":
                    fixed_annuity.append(nominal * period.year_fraction * discount_factor)
                if (is_frn and bucket == "attached" and leg.kind == "floating_coupon"
                        and period.accrual_start < market.settlement_date < period.accrual_end):
                    days = (market.settlement_date - period.accrual_start).days
                    accrual_request = request.model_copy(update={
                        "day_count_days": days, "accrual_fraction": days / period.day_count_denominator, "is_accrual": True,
                    })
                    accrued.append(leg_sign * amount_for(accrual_request).amount_eur)

            flows.append(RatesPriceFlow(
                flow_id=request.flow_id, leg_id=leg.leg_id, kind=request.kind, period_id=period_id, rank=request.rank,
                payment_date=request.payment_date, accrual_start=period.accrual_start if period is not None else None,
                accrual_end=period.accrual_end if period is not None else None, accrual_fraction=request.accrual_fraction,
                day_count=period.day_count if period is not None else None, day_count_days=request.day_count_days,
                fixing_date=period.fixing_date if period is not None else None, fixing_state=state.fixing_state,
                rate_origin=origin, rate=rate, margin_bps=margin, state=state.state, bucket=bucket,
                amount_eur=amount, pv_eur=pv, discount_factor=discount_factor, fixing_id=state.fixing_id,
                fixing_version=state.fixing_version, payment_fact_id=state.payment_fact_id,
                payment_version=state.payment_version, paid_date=paid_date, label=label,
            ))
    if states:
        raise RatesPricingError("RATES_PRICE_CONTEXT_MISMATCH", "Des flux du contexte sont absents de l’échéancier.")
    return _Valuation(tuple(flows), fsum(accrued), fsum(fixed_annuity))
