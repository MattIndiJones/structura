"""Research preparation and EUR-per-100 valuation for long FRN and CLN vintages."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import exp, fsum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..product.credit_default import CreditDefaultDiscount, prepare_credit_default, price_credit_default
from ..product.credit_facts import SyntheticCreditFact
from ..product.credit_pricing import CreditCoupon, SurvivalCurve, value_cln
from ..product.models import CLNTerms, FRNTerms, FrozenModel, FrozenObject, Product, TradeIntent
from ..product.native_market import prepare_native_context
from ..product.native_schedule import native_draft_diagnostics, resolve_native_schedule
from ..product.native_schedule_models import NativeSchedule
from ..product.rates_market import PaymentConfirmation, RatesMarket, RatesSource, SelectedPaymentConfirmation, _latest_eligible
from ..product.rates_pricing import price_rates
from ..product.rates_schedule import _days_30e_360
from ..valuation_context import canonical_fingerprint, json_transport_fingerprint


_ZONE = ZoneInfo("Europe/Paris")
ResearchOperation = Literal["issue", "mtm", "lifecycle"]
ResearchState = Literal["alive", "recovery_pending", "settlement_pending", "settled"]
FlowState = Literal["projected", "fixed", "expected", "pending", "due", "past_due", "paid"]
Identifier = Annotated[str, Field(min_length=1, max_length=144)]
Version = Annotated[int, Field(strict=True, ge=1)]
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ResearchTerms = Annotated[FRNTerms | CLNTerms, Field(discriminator="instrument_type")]
PositiveAmount = Annotated[float, Field(ge=0)]


class RatesCreditResearchError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RatesCreditPrepareRequest(FrozenModel):
    schema_version: Literal[1] = 1
    millesime_id: Identifier
    terms_version: Version = 1
    terms: ResearchTerms
    intent: TradeIntent


class RatesCreditPrepared(RatesCreditPrepareRequest):
    product_id: int | None = Field(default=None, ge=1)
    product_reference: str | None = None
    native_schedule: NativeSchedule
    terms_fingerprint: Fingerprint
    schedule_fingerprint: Fingerprint
    fingerprint: Fingerprint

    @model_validator(mode="after")
    def verify_preparation(self):
        schedule = self.native_schedule
        version = self.terms_version if self.product_id is not None else None
        if (
            (schedule.product_id, schedule.terms_version, schedule.instrument_type) !=
            (self.product_id, version, self.terms.instrument_type)
            or self.terms_fingerprint != self.terms.fingerprint
            or schedule.terms_fingerprint != self.terms.fingerprint
            or self.schedule_fingerprint != schedule.fingerprint
            or schedule.fingerprint != canonical_fingerprint(schedule.model_dump(mode="json", exclude={"fingerprint"}))
            or (self.product_id is None) != (self.product_reference is None)
        ):
            raise ValueError("Le millésime Research ne correspond pas aux termes et à l’échéancier figés.")
        if self.fingerprint != json_transport_fingerprint(self.model_dump(mode="json", exclude={"fingerprint"})):
            raise ValueError("L’empreinte de préparation du millésime Research est incohérente.")
        return self

    def as_product(self) -> Product:
        return Product(
            product_id=self.product_id, reference=self.product_reference,
            terms_version=self.terms_version if self.product_id is not None else 0,
            terms=self.terms, intent=self.intent, native_schedule=self.native_schedule,
        )


class ClnResearchMarket(FrozenModel):
    kind: Literal["cln_research"] = "cln_research"
    market_id: Identifier
    market_version: Version
    market_date: date
    reference_entity_id: Identifier
    source: RatesSource
    available_at: AwareDatetime
    validated_at: AwareDatetime
    ois_rate: float
    funding_bps: float = 0
    hazard_rate: float | None = Field(default=None, ge=0)
    pricing_recovery_fraction: float | None = Field(default=None, ge=0, le=1)
    default_id: Identifier | None = None
    credit_facts: tuple[SyntheticCreditFact, ...] = ()
    settlement_date: date | None = None
    payments: tuple[PaymentConfirmation, ...] = ()

    @field_validator("available_at", "validated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def verify_default_input(self):
        if (self.credit_facts or self.settlement_date is not None) and self.default_id is None:
            raise ValueError("Les faits de crédit requièrent l’identifiant du défaut.")
        return self


ResearchMarket = Annotated[RatesMarket | ClnResearchMarket, Field(discriminator="kind")]


class RatesCreditJob(FrozenModel):
    schema_version: Literal[1] = 1
    job_id: Identifier
    millesime: RatesCreditPrepared
    valuation_date: date
    value_date: date | None = None
    cutoff: AwareDatetime
    market: ResearchMarket

    @field_validator("cutoff")
    @classmethod
    def utc_cutoff(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def dates_and_market(self):
        if self.cutoff.astimezone(_ZONE).date() != self.valuation_date or self.market.market_date != self.valuation_date:
            raise ValueError("Les dates de valorisation, du marché et du cut-off Research doivent concorder.")
        if self.value_date is not None and self.value_date != self.valuation_date:
            raise ValueError("La date de valeur du pilote Research doit être la date de valorisation.")
        if isinstance(self.millesime.terms, FRNTerms) != isinstance(self.market, RatesMarket):
            raise ValueError("Le type de marché Research ne correspond pas au produit.")
        return self


class RatesCreditFlow(FrozenModel):
    flow_id: str
    kind: Literal["coupon", "principal", "default_settlement", "expected_default_redemption"]
    state: FlowState
    amount_per_100: PositiveAmount | None
    pv_per_100: PositiveAmount | None
    scheduled_date: date | None
    effect_date: date | None = None
    available_at: AwareDatetime | None = None
    validated_at: AwareDatetime | None = None
    paid_date: date | None = None
    fact_id: str | None = None
    version: Version | None = None


class RatesCreditResult(FrozenModel):
    schema_version: Literal[1] = 1
    job_id: Identifier
    millesime_id: Identifier
    operation: ResearchOperation
    instrument_type: Literal["FRN", "CLN"]
    product_id: int | None
    product_reference: str | None
    valuation_date: date
    value_date: date
    cutoff: AwareDatetime
    unit: Literal["EUR_per_100"] = "EUR_per_100"
    currency: Literal["EUR"] = "EUR"
    terms_version: Version
    terms_fingerprint: Fingerprint
    schedule_fingerprint: Fingerprint
    prepared_fingerprint: Fingerprint
    market_id: Identifier
    market_version: Version
    market_fingerprint: Fingerprint
    request_fingerprint: Fingerprint
    engine_version: str
    state: ResearchState
    clean_per_100: float | None
    dirty_per_100: PositiveAmount | None
    accrued_per_100: PositiveAmount | None
    residual_pv_per_100: PositiveAmount
    receivable_pv_per_100: PositiveAmount | None
    flows: tuple[RatesCreditFlow, ...]
    events: tuple[FrozenObject, ...] = ()
    effective_market: FrozenObject


def _check_terms(product: Product) -> None:
    diagnostics = native_draft_diagnostics(product)
    if diagnostics:
        raise RatesCreditResearchError("RESEARCH_TERMS_INCOMPLETE", " ".join(diagnostics))
    if product.intent.side != "BUY" or product.terms.payoff_mode != "native":
        raise RatesCreditResearchError("RESEARCH_POSITION_UNSUPPORTED", "La recette est limitée aux notes longues en mode Template.")


def _guard_confirmed_cash(job: RatesCreditJob) -> None:
    entries: dict[str, tuple[date, float]] = {}
    for payment in job.market.payments:
        if (payment.schedule_fingerprint != job.millesime.schedule_fingerprint
                or payment.effect_date > job.valuation_date or not payment.eligible_at(job.cutoff)):
            continue
        economic_cash = (payment.effect_date, payment.amount_eur)
        if entries.setdefault(payment.flow_id, economic_cash) != economic_cash:
            raise RatesCreditResearchError(
                "RESEARCH_PAID_CASH_CONFLICT",
                f"Deux confirmations changent le cash du flux {payment.flow_id}. Un ajustement requiert un flux distinct.",
            )


def prepare_rates_credit(
    request: RatesCreditPrepareRequest,
    *,
    schedule: NativeSchedule | None = None,
    product_id: int | None = None,
    product_reference: str | None = None,
) -> RatesCreditPrepared:
    """Freeze one Research vintage, or bind it to an authorized archived Product."""
    product = Product(terms=request.terms, intent=request.intent)
    _check_terms(product)
    if schedule is None:
        if product_id is not None:
            raise RatesCreditResearchError("RESEARCH_SCHEDULE_REQUIRED", "L’échéancier archivé du Product est requis.")
        schedule = resolve_native_schedule(product.terms).schedule
    # Revalidate even pre-existing typed instances reconstructed by an archive reader.
    frozen_schedule = NativeSchedule.model_validate(schedule.model_dump(mode="json"))
    payload = {
        **request.model_dump(mode="json"),
        "product_id": product_id, "product_reference": product_reference,
        "native_schedule": frozen_schedule.model_dump(mode="json"),
        "terms_fingerprint": request.terms.fingerprint, "schedule_fingerprint": frozen_schedule.fingerprint,
    }
    return RatesCreditPrepared.model_validate({**payload, "fingerprint": json_transport_fingerprint(payload)})


@dataclass(frozen=True)
class _Value:
    engine_version: str
    state: ResearchState
    clean: float | None
    dirty: float | None
    accrued: float | None
    residual: float
    receivables: float | None
    flows: tuple[RatesCreditFlow, ...]
    market_fingerprint: str
    effective_market: dict
    events: tuple[FrozenObject, ...] = ()


def _flow(
    *,
    scale: float,
    flow_id: str,
    kind: str,
    state: FlowState,
    amount: float | None,
    pv: float | None,
    scheduled_date: date | None,
    fact=None,
    paid_date: date | None = None,
) -> RatesCreditFlow:
    if any(value is not None and value < 0 for value in (amount, pv)):
        raise RatesCreditResearchError(
            "RESEARCH_SIGNED_FLOW_UNSUPPORTED", f"Le flux {flow_id} est négatif dans un pilote de notes longues.",
        )
    return RatesCreditFlow(
        flow_id=flow_id, kind=kind, state=state, scheduled_date=scheduled_date,
        amount_per_100=amount * scale if amount is not None else None, pv_per_100=pv * scale if pv is not None else None,
        effect_date=(getattr(fact, "effect_date", None) or getattr(fact, "observation_date", None)),
        available_at=fact.available_at if fact is not None else None,
        validated_at=fact.validated_at if fact is not None else None,
        paid_date=paid_date, fact_id=(getattr(fact, "fact_id", None) or getattr(fact, "fixing_id", None)),
        version=fact.version if fact is not None else None,
    )


def _frn_value(product: Product, job: RatesCreditJob, scale: float) -> _Value:
    context = prepare_native_context(
        product, valuation_date=job.valuation_date, cutoff=job.cutoff,
        market=job.market, allow_draft=True, allow_overdue_rates_payments=True,
    )
    priced = price_rates(product, context)
    market = context.market
    fixings = {(fixing.fixing_id, fixing.version): fixing for fixing in market.fixings}
    payments = {(payment.fact_id, payment.version, payment.flow_id): payment for payment in market.payments}
    flows = []
    for item in priced.flows:
        payment = payments.get((item.payment_fact_id, item.payment_version, item.flow_id))
        if item.state == "future":
            state = "projected" if item.fixing_state == "projected" else "fixed"
        elif item.state == "due_open":
            state = "past_due" if item.payment_date < job.valuation_date else "due"
        else:
            state = "paid"
        flows.append(_flow(
            scale=scale, flow_id=item.flow_id, kind="principal" if item.kind == "principal" else "coupon",
            state=state, amount=item.amount_eur, pv=item.pv_eur, scheduled_date=item.payment_date,
            fact=payment or fixings.get((item.fixing_id, item.fixing_version)), paid_date=item.paid_date,
        ))
    state = "alive" if any(flow.state in {"projected", "fixed"} for flow in flows) else (
        "settled" if all(flow.state == "paid" for flow in flows) else "settlement_pending"
    )
    return _Value(
        priced.engine_version, state, priced.clean_pv_eur * scale, priced.dirty_pv_eur * scale, priced.accrued_eur * scale,
        priced.dirty_pv_eur * scale, priced.detached_pv_eur * scale, tuple(flows), market.market_fingerprint,
        market.model_dump(mode="json"),
        tuple(FrozenObject(pay.model_dump(mode="json")) for pay in market.payments),
    )


def _coupon_claim(
    flow_id: str,
    scheduled: date,
    acquisition_date: date,
    amount: float,
    claim_kind: str,
    product: Product,
    job: RatesCreditJob,
    scale: float,
) -> tuple[RatesCreditFlow, SelectedPaymentConfirmation | None]:
    market = job.market
    eligible = [
        payment for payment in market.payments
        if payment.flow_id == flow_id and payment.schedule_fingerprint == product.native_schedule.fingerprint
        and payment.effect_date <= job.valuation_date and payment.eligible_at(job.cutoff)
    ]
    version = _latest_eligible(eligible, f"le flux {flow_id}")
    if version is not None:
        if version.effect_date < acquisition_date or abs(version.amount_eur - amount) > .01:
            raise RatesCreditResearchError("RESEARCH_PAYMENT_INCOMPATIBLE", f"La confirmation contredit la créance {flow_id}.")
        confirmation = SelectedPaymentConfirmation.model_validate(version.model_dump(exclude={"ingested_at"}))
        flow = _flow(scale=scale, flow_id=flow_id, kind=claim_kind, state="paid", amount=confirmation.amount_eur,
                     pv=0.0, scheduled_date=scheduled, fact=confirmation, paid_date=confirmation.effect_date)
        return flow, confirmation
    age = (scheduled - job.valuation_date).days
    pv = amount * exp(-(market.ois_rate + market.funding_bps / 10_000) * max(0, age) / 365)
    flow = _flow(scale=scale, flow_id=flow_id, kind=claim_kind, state="past_due" if age < 0 else "due",
                 amount=amount, pv=pv, scheduled_date=scheduled)
    return flow, None


def _live_cln(product: Product, job: RatesCreditJob, scale: float, market_inputs: dict, market_fingerprint: str) -> _Value:
    terms, market, nominal = product.terms, job.market, product.intent.nominal
    fixed, principal_leg = product.native_schedule.legs
    principal, = principal_leg.events
    contract_end = fixed.periods[-1].credit_observation_date
    remaining = []
    flows = []
    selected_payments = []

    def add_claim(flow_id, scheduled, entitlement, amount, kind):
        flow, payment = _coupon_claim(flow_id, scheduled, entitlement, amount, kind, product, job, scale)
        flows.append(flow)
        if payment is not None:
            selected_payments.append(payment.model_dump(mode="json"))

    for period in fixed.periods:
        if period.credit_observation_date <= job.valuation_date:
            amount = nominal * terms.fixed_leg.coupon_rate * period.year_fraction
            add_claim(period.flow_id, period.payment_date, period.credit_observation_date, amount, "coupon")
        else:
            remaining.append(period)

    if contract_end <= job.valuation_date:
        add_claim(principal.flow_id, principal.date, contract_end, nominal * terms.redemption_fraction, "principal")
        receivables = fsum(flow.pv_per_100 for flow in flows if flow.state in {"due", "past_due"})
        state = "settled" if all(flow.state == "paid" for flow in flows) else "settlement_pending"
        return _Value("eur-credit-research-cln-v1", state, 0, 0, 0, 0, receivables,
                      tuple(flows), market_fingerprint, {**market_inputs, "payments": selected_payments})
    if market.hazard_rate is None or market.pricing_recovery_fraction is None:
        raise RatesCreditResearchError("RESEARCH_CLN_SURVIVAL_REQUIRED", "Le mark vivant exige la survie et le recouvrement de pricing.")

    def years(day):
        return (day - job.valuation_date).days / 365

    coupons = tuple(CreditCoupon(
        start=years(period.accrual_start), end=years(period.accrual_end), payment=years(period.payment_date),
        observation=years(period.credit_observation_date), year_fraction=period.year_fraction,
    ) for period in remaining)
    first = remaining[0]
    accrued_days = 0
    if first.accrual_start < job.valuation_date:
        accrued_days = ((job.valuation_date - first.accrual_start).days if first.day_count == "ACT/360"
                        else _days_30e_360(first.accrual_start, job.valuation_date))
    maturity = years(contract_end)
    curve = SurvivalCurve(maturities=(maturity,), hazards=(market.hazard_rate,))
    result = value_cln(
        curve, market.ois_rate, maturity, nominal=nominal, coupon_rate=terms.fixed_leg.coupon_rate,
        recovery=market.pricing_recovery_fraction, settlement_delay=terms.default_settlement_lag_calendar_days / 365,
        funding_bps=market.funding_bps, coupons=coupons, principal_payment=years(principal.date),
        protected_from=max(0.0, years(fixed.periods[0].accrual_start)),
        accrued_fraction=accrued_days / first.day_count_denominator,
    )
    flows.extend(_flow(
        scale=scale, flow_id=period.flow_id, kind="coupon", state="expected",
        amount=nominal * terms.fixed_leg.coupon_rate * period.year_fraction, pv=pv, scheduled_date=period.payment_date,
    ) for period, pv in zip(remaining, result.coupon_pvs_eur, strict=True))
    flows.extend((
        _flow(scale=scale, flow_id=principal.flow_id, kind="principal", state="expected", amount=nominal,
              pv=result.survival_principal_pv_eur, scheduled_date=principal.date),
        _flow(scale=scale, flow_id="cln-default-redemption-expected", kind="expected_default_redemption", state="expected",
              amount=None, pv=result.default_redemption_pv_eur, scheduled_date=None),
    ))
    receivables = fsum(flow.pv_per_100 for flow in flows if flow.state in {"due", "past_due"})
    return _Value(
        "eur-credit-research-cln-v1", "alive", result.clean_pv_eur * scale, result.dirty_pv_eur * scale,
        result.accrued_eur * scale, result.dirty_pv_eur * scale, receivables, tuple(flows), market_fingerprint,
        {**market_inputs, "payments": selected_payments},
    )


def _cln_value(product: Product, job: RatesCreditJob, scale: float) -> _Value:
    market = job.market
    if market.source.kind != "synthetic" or market.reference_entity_id != product.terms.reference_entity_id:
        raise RatesCreditResearchError("RESEARCH_CLN_MARKET_INCOMPATIBLE", "Source ou référence du marché Research CLN incompatible.")
    if max(market.available_at, market.validated_at) > job.cutoff:
        raise RatesCreditResearchError("RESEARCH_MARKET_UNAVAILABLE", "Le marché Research CLN est indisponible à l’arrêté.")
    raw_pricing = market.model_dump(mode="json", exclude={"credit_facts", "payments", "default_id", "settlement_date"})
    market_fingerprint = json_transport_fingerprint(raw_pricing)
    if market.default_id is None:
        return _live_cln(product, job, scale, raw_pricing, market_fingerprint)
    if market.settlement_date is None:
        raise RatesCreditResearchError("RESEARCH_SETTLEMENT_DATE_REQUIRED", "Le scénario de défaut requiert une date de règlement prévue.")
    selected = prepare_credit_default(
        product, valuation_date=job.valuation_date, cutoff=job.cutoff, default_id=market.default_id,
        facts=market.credit_facts, settlement_date=market.settlement_date, reference_entity_id=market.reference_entity_id,
        prior_payments=market.payments, discount=CreditDefaultDiscount(ois_rate=market.ois_rate, cln_funding_bps=market.funding_bps),
    )
    if selected.facts.state == "alive":
        return _live_cln(product, job, scale, raw_pricing, market_fingerprint)
    priced = price_credit_default(product, selected)
    facts = selected.facts
    seen_facts = (facts.default, facts.recovery, facts.settlement)
    selected_payments = {payment.flow_id: payment for payment in selected.prior_coupon_payments}
    flows = [_flow(
        scale=scale, flow_id=item.flow_id, kind="coupon", state=item.state, amount=item.amount_eur,
        pv=item.pv_eur, scheduled_date=item.scheduled_date, paid_date=item.paid_date, fact=selected_payments.get(item.flow_id),
    ) for item in priced.earned_coupon_flows]
    if priced.settlement_flow is None:
        identifier = canonical_fingerprint([selected.schedule_fingerprint, facts.default_id])
        flows.append(_flow(
            scale=scale, flow_id=f"{identifier}-default-settlement", kind="default_settlement", state="pending",
            amount=None, pv=None, scheduled_date=selected.planned_settlement_date, fact=facts.default,
        ))
    else:
        claim = priced.settlement_flow
        flows.append(_flow(
            scale=scale, flow_id=claim.flow_id, kind="default_settlement", state=claim.state, amount=claim.amount_eur,
            pv=claim.pv_eur, scheduled_date=claim.scheduled_date, paid_date=claim.paid_date,
            fact=facts.settlement if claim.state == "paid" else facts.recovery,
        ))
    pending = priced.state == "recovery_pending"
    quote = None if pending else 0.0
    state = priced.state
    if state == "settled" and any(flow.state in {"due", "past_due"} for flow in flows):
        state = "settlement_pending"
    return _Value(
        priced.engine_version, state, quote, quote, quote, 0.0,
        None if pending else priced.claim_pv_eur * scale, tuple(flows), market_fingerprint,
        {**raw_pricing, "default_context": selected.model_dump(mode="json")},
        tuple(FrozenObject(fact.model_dump(mode="json")) for fact in seen_facts if fact is not None),
    )


def price_rates_credit(job: RatesCreditJob, *, operation: ResearchOperation = "mtm") -> RatesCreditResult:
    """Run issue, mark or lifecycle from identical frozen inputs and unit convention."""
    job.millesime.verify_preparation()
    product = job.millesime.as_product()
    _check_terms(product)
    _guard_confirmed_cash(job)
    scale = 100 / product.intent.nominal
    value = _frn_value(product, job, scale) if isinstance(product.terms, FRNTerms) else _cln_value(product, job, scale)
    if operation == "issue" and value.state != "alive":
        raise RatesCreditResearchError("RESEARCH_NOT_ISSUABLE", "Ce millésime ne porte plus de titre vivant à l’arrêté.")
    request_fingerprint = json_transport_fingerprint({"operation": operation, **job.model_dump(mode="json")})
    return RatesCreditResult(
        job_id=job.job_id, millesime_id=job.millesime.millesime_id, operation=operation,
        instrument_type=product.terms.instrument_type, product_id=product.product_id, product_reference=product.reference,
        valuation_date=job.valuation_date, value_date=job.value_date or job.valuation_date, cutoff=job.cutoff,
        terms_version=job.millesime.terms_version, terms_fingerprint=job.millesime.terms_fingerprint,
        schedule_fingerprint=job.millesime.schedule_fingerprint, prepared_fingerprint=job.millesime.fingerprint,
        market_id=job.market.market_id, market_version=job.market.market_version,
        market_fingerprint=value.market_fingerprint, request_fingerprint=request_fingerprint,
        engine_version=value.engine_version, state=value.state, clean_per_100=value.clean, dirty_per_100=value.dirty,
        accrued_per_100=value.accrued, residual_pv_per_100=value.residual, receivable_pv_per_100=value.receivables,
        flows=value.flows, events=value.events, effective_market=FrozenObject(value.effective_market),
    )
