"""Prepare and value settled and unsettled claims of the synthetic credit pilot."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import exp, fsum, isfinite
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..valuation_context import canonical_fingerprint
from .cds_schedule import cds_default_accrued_days
from .credit_facts import (
    SyntheticCreditFact, SyntheticCreditSelection, SyntheticDefaultFact, SyntheticRecoveryFact,
    SyntheticSettlementFact, select_synthetic_credit_facts,
)
from .models import CDSTerms, CLNTerms, FrozenModel, Product
from .native_schedule_models import NativeSchedule, SchedulePeriod
from .rates_market import PaymentConfirmation, SelectedPaymentConfirmation, _latest_eligible


_PARIS = ZoneInfo("Europe/Paris")
_CENT = Decimal("0.01")
CreditDefaultState = Literal["alive", "recovery_pending", "settlement_pending", "settled"]


class CreditDefaultError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CreditDefaultDiscount(FrozenModel):
    ois_rate: float = Field(strict=True)
    cln_funding_bps: float = Field(strict=True)
    convention: Literal["flat_continuous_ACT/365F"] = "flat_continuous_ACT/365F"
    overdue_treatment: Literal["face_at_valuation_date"] = "face_at_valuation_date"


class CreditDefaultPaidBasis(FrozenModel):
    default: SyntheticDefaultFact
    recovery: SyntheticRecoveryFact


class _CreditDefaultInputs(FrozenModel):
    schema_version: Literal[1] = 1
    kind: Literal["credit_default"] = "credit_default"
    policy: Literal["synthetic_credit_recipe_v1"] = "synthetic_credit_recipe_v1"
    instrument_type: Literal["CDS", "CLN"]
    reference_entity_id: str
    product_id: int | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float = Field(gt=0)
    position_side: Literal["BUY", "SELL"]
    valuation_date: date
    value_date: date
    cutoff: AwareDatetime
    discount: CreditDefaultDiscount
    facts: SyntheticCreditSelection
    planned_settlement_date: date | None
    paid_basis: CreditDefaultPaidBasis | None = None
    prior_coupon_payments: tuple[SelectedPaymentConfirmation, ...] = ()

    @field_validator("cutoff")
    @classmethod
    def normalize_cutoff(cls, cutoff: datetime) -> datetime:
        return cutoff.astimezone(timezone.utc)


class CreditDefaultContext(_CreditDefaultInputs):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self):
        if canonical_fingerprint(self.model_dump(mode="json", exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("L’empreinte du contexte de défaut crédit est incohérente.")
        return self


class CreditDefaultFlow(FrozenModel):
    flow_id: str
    kind: Literal["protection", "accrued_premium", "recovery_redemption", "default_settlement", "earned_coupon"]
    state: Literal["due", "past_due", "paid"]
    scheduled_date: date
    paid_date: date | None = None
    amount_eur: float
    pv_eur: float
    payment_fact_id: str | None = None
    payment_version: int | None = None


class CreditDefaultMeasure(FrozenModel):
    kind: Literal["credit_pv"] = "credit_pv"
    unit: Literal["EUR"] = "EUR"
    value: float | None


class CreditDefaultResult(FrozenModel):
    schema_version: Literal[1] = 1
    engine_version: Literal["synthetic-credit-default-v1"] = "synthetic-credit-default-v1"
    market_quality: Literal["synthetic"] = "synthetic"
    product_id: int | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    context_fingerprint: str
    instrument_type: Literal["CDS", "CLN"]
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float
    position_side: Literal["BUY", "SELL"]
    valuation_date: date
    value_date: date
    cutoff: AwareDatetime
    state: CreditDefaultState
    default_date: date | None = None
    default_known_at: AwareDatetime | None = None
    recovery_fraction: float | None = None
    accrued_days_at_default: int | None = None
    contingent_pv_eur: float | None
    claim_pv_eur: float
    economic_pv_eur: float | None
    net_due_eur: float | None
    realized_cash_eur: float
    cash_on_value_date_eur: float
    settlement_flow: CreditDefaultFlow | None = None
    components: tuple[CreditDefaultFlow, ...] = ()
    earned_coupon_flows: tuple[CreditDefaultFlow, ...] = ()
    measure: CreditDefaultMeasure


def _contract(product: Product) -> tuple[CDSTerms | CLNTerms, NativeSchedule, tuple[SchedulePeriod, ...]]:
    terms, schedule = product.terms, product.native_schedule
    if not isinstance(terms, (CDSTerms, CLNTerms)):
        raise CreditDefaultError("CREDIT_DEFAULT_TERMS", "Le scénario défaut concerne un CDS ou une CLN EUR.")
    coupon = terms.premium_leg.coupon_bps if isinstance(terms, CDSTerms) else terms.fixed_leg.coupon_rate
    if coupon is None or product.intent.nominal is None:
        raise CreditDefaultError("CREDIT_DEFAULT_TERMS", "Le nominal et le coupon contractuel sont requis.")
    version = product.terms_version if product.product_id is not None else None
    if schedule is None or (
        schedule.product_id, schedule.terms_version, schedule.instrument_type, schedule.terms_fingerprint,
    ) != (product.product_id, version, terms.instrument_type, terms.fingerprint) or (
        canonical_fingerprint(schedule.model_dump(mode="json", exclude={"fingerprint"})) != schedule.fingerprint
    ):
        raise CreditDefaultError("CREDIT_DEFAULT_SCHEDULE", "L’échéancier figé doit correspondre aux termes du produit.")
    kind = "premium" if isinstance(terms, CDSTerms) else "fixed_coupon"
    periods = next((leg.periods for leg in schedule.legs if leg.kind == kind), ())
    if not periods or any(period.credit_observation_date is None for period in periods):
        raise CreditDefaultError("CREDIT_DEFAULT_SCHEDULE", "La jambe de coupons ne porte pas les dates de référence crédit.")
    return terms, schedule, periods


def _settled_basis(facts: Sequence[SyntheticCreditFact], settlement: SyntheticSettlementFact) -> CreditDefaultPaidBasis:
    if settlement.default_version is None or settlement.recovery_version is None:
        raise CreditDefaultError("CREDIT_SETTLEMENT_BINDING", "Le règlement doit référencer les deux versions employées.")
    candidates = [
        fact for fact in facts if (
            (fact.kind, fact.version) == ("default", settlement.default_version)
            or (fact.kind, fact.version) == ("recovery_final", settlement.recovery_version)
        )
    ]
    confirmation_time = max(settlement.available_at, settlement.validated_at)
    selection = select_synthetic_credit_facts(settlement.default_id, candidates, confirmation_time)
    if selection.default is None or selection.recovery is None or settlement.effect_date < selection.recovery.effect_date:
        raise CreditDefaultError("CREDIT_SETTLEMENT_BINDING", "Versions du défaut ou du recouvrement incompatibles avec le paiement.")
    if any(max(item.available_at, item.validated_at).astimezone(_PARIS).date() > settlement.effect_date
           for item in (selection.default, selection.recovery)):
        raise CreditDefaultError("CREDIT_SETTLEMENT_BINDING", "Une version retenue est postérieure au règlement effectif.")
    return CreditDefaultPaidBasis(default=selection.default, recovery=selection.recovery)


def _coupon_payments(
    payments: Sequence[PaymentConfirmation], schedule: NativeSchedule, periods: tuple[SchedulePeriod, ...],
    default: SyntheticDefaultFact, valuation_date: date, cutoff: datetime,
) -> tuple[SelectedPaymentConfirmation, ...]:
    by_flow = {}
    for fact in payments:
        if fact.schedule_fingerprint == schedule.fingerprint and fact.effect_date <= valuation_date and fact.eligible_at(cutoff):
            by_flow.setdefault(fact.flow_id, []).append(fact)
    selected = []
    for period in periods:
        if period.credit_observation_date >= default.effect_date:
            continue
        fact = _latest_eligible(by_flow.get(period.flow_id, []), f"le coupon {period.flow_id}")
        if fact is not None:
            if fact.effect_date < period.credit_observation_date:
                raise CreditDefaultError("CREDIT_COUPON_SETTLEMENT", "Un paiement précède l’acquisition du coupon.")
            selected.append(SelectedPaymentConfirmation.model_validate(fact.model_dump(exclude={"ingested_at"})))
    return tuple(selected)


def prepare_credit_default(
    product: Product, *, valuation_date: date, cutoff: datetime, default_id: str,
    facts: Sequence[SyntheticCreditFact], settlement_date: date, discount: CreditDefaultDiscount,
    reference_entity_id: str, prior_payments: Sequence[PaymentConfirmation] = (),
) -> CreditDefaultContext:
    """Freeze eligible facts and the authorised synthetic settlement date."""
    terms, schedule, periods = _contract(product)
    if reference_entity_id != terms.reference_entity_id:
        raise CreditDefaultError("CREDIT_DEFAULT_REFERENCE", "Le fait de défaut concerne une autre entité de référence.")
    if isinstance(terms, CDSTerms) and discount.cln_funding_bps != 0:
        raise CreditDefaultError("CREDIT_DEFAULT_FUNDING", "Le funding émetteur CLN ne s’applique pas au CDS.")
    if cutoff.utcoffset() is None or cutoff.astimezone(_PARIS).date() != valuation_date:
        raise CreditDefaultError("CREDIT_DEFAULT_CUTOFF", "Le cut-off doit porter le jour de valorisation en Europe/Paris.")
    selection = select_synthetic_credit_facts(default_id, facts, cutoff)
    basis = _settled_basis(facts, selection.settlement) if selection.settlement is not None else None
    default = basis.default if basis is not None else selection.default
    coupon_payments = ()
    if default is not None:
        first_day = terms.effective_date if isinstance(terms, CDSTerms) else periods[0].accrual_start
        if not first_day <= default.effect_date <= periods[-1].credit_observation_date:
            raise CreditDefaultError("CREDIT_DEFAULT_OUTSIDE_COVERAGE", "Le défaut sort des dates de couverture du contrat.")
        minimum_lag = terms.default_settlement_lag_calendar_days if isinstance(terms, CLNTerms) else 0
        earliest = default.effect_date + timedelta(days=minimum_lag)
        if settlement_date < earliest or (basis and selection.settlement.effect_date < earliest):
            raise CreditDefaultError("CREDIT_SETTLEMENT_DATE", "La date de règlement précède le délai contractuel de défaut.")
        coupon_payments = _coupon_payments(prior_payments, schedule, periods, default, valuation_date, cutoff)
    inputs = _CreditDefaultInputs(
        instrument_type=terms.instrument_type, reference_entity_id=reference_entity_id,
        product_id=product.product_id, terms_version=schedule.terms_version,
        terms_fingerprint=terms.fingerprint, schedule_fingerprint=schedule.fingerprint,
        nominal_eur=product.intent.nominal, position_side=product.intent.side,
        valuation_date=valuation_date, value_date=valuation_date, cutoff=cutoff, discount=discount,
        facts=selection, planned_settlement_date=settlement_date if default else None,
        paid_basis=basis, prior_coupon_payments=coupon_payments,
    )
    # Normalise nested proof values as they will appear on archive reloading.
    payload = _CreditDefaultInputs.model_validate(inputs.model_dump(mode="json")).model_dump(mode="json")
    return CreditDefaultContext.model_validate({**payload, "fingerprint": canonical_fingerprint(payload)})


def _round_cash(amount: Decimal) -> float:
    try:
        rounded = float(amount.quantize(_CENT, rounding=ROUND_HALF_UP))
    except ArithmeticError as exc:
        raise CreditDefaultError("CREDIT_DEFAULT_AMOUNT", "Le montant de règlement est hors limites.") from exc
    if not isfinite(rounded):
        raise CreditDefaultError("CREDIT_DEFAULT_AMOUNT", "Le montant de règlement est hors limites.")
    return rounded


def _flow(
    context: CreditDefaultContext, flow_id: str, kind: str, amount: float, scheduled_date: date,
    payment: SyntheticSettlementFact | SelectedPaymentConfirmation | None = None,
) -> CreditDefaultFlow:
    if payment is not None:
        return CreditDefaultFlow(
            flow_id=flow_id, kind=kind, state="paid", scheduled_date=scheduled_date, paid_date=payment.effect_date,
            amount_eur=amount, pv_eur=0, payment_fact_id=payment.fact_id, payment_version=payment.version,
        )
    rate = context.discount.ois_rate + context.discount.cln_funding_bps / 10_000
    days = (scheduled_date - context.value_date).days
    try:
        pv = amount * exp(-rate * max(0, days) / 365)
    except OverflowError as exc:
        raise CreditDefaultError("CREDIT_DEFAULT_DISCOUNT", "La valeur actualisée du règlement est hors limites.") from exc
    if not isfinite(pv):
        raise CreditDefaultError("CREDIT_DEFAULT_DISCOUNT", "La valeur actualisée du règlement est hors limites.")
    return CreditDefaultFlow(
        flow_id=flow_id, kind=kind, state="past_due" if days < 0 else "due",
        scheduled_date=scheduled_date, amount_eur=amount, pv_eur=pv,
    )


def _earned_coupon_flows(
    terms: CDSTerms | CLNTerms, periods: tuple[SchedulePeriod, ...],
    context: CreditDefaultContext, default_date: date,
) -> tuple[CreditDefaultFlow, ...]:
    payments = {fact.flow_id: fact for fact in context.prior_coupon_payments}
    is_cds = isinstance(terms, CDSTerms)
    coupon_rate = (
        Decimal(str(terms.premium_leg.coupon_bps)) / 10_000 if is_cds else Decimal(str(terms.fixed_leg.coupon_rate))
    )
    nominal = Decimal(str(context.nominal_eur))
    receive_sign = -1 if is_cds else 1
    direction = 1 if context.position_side == "BUY" else -1
    earned = []
    for period in periods:
        if period.credit_observation_date >= default_date:
            continue
        fact = payments.get(period.flow_id)
        amount = _round_cash(
            direction * receive_sign * nominal * coupon_rate * period.day_count_days / period.day_count_denominator,
        )
        if fact is not None and abs(fact.amount_eur - amount) > 0.01:
            raise CreditDefaultError("CREDIT_COUPON_SETTLEMENT", "Le coupon payé ne correspond pas au nominal ou au sens du témoin.")
        earned.append(_flow(context, period.flow_id, "earned_coupon", fact.amount_eur if fact else amount,
                            period.payment_date, fact))
    return tuple(earned)


def _default_components(
    terms: CDSTerms | CLNTerms, context: CreditDefaultContext, accrued_days: int, recovery: SyntheticRecoveryFact,
) -> tuple[tuple[CreditDefaultFlow, ...], CreditDefaultFlow]:
    direction = 1 if context.position_side == "BUY" else -1
    nominal = direction * Decimal(str(context.nominal_eur))
    recovery_rate = Decimal(str(recovery.recovery_fraction))
    identifier = canonical_fingerprint([context.schedule_fingerprint, context.facts.default_id])
    date_due, paid = context.planned_settlement_date, context.facts.settlement
    if isinstance(terms, CDSTerms):
        coupon_rate = Decimal(str(terms.premium_leg.coupon_bps)) / 10_000
        amounts = (
            ("protection", nominal * (1 - recovery_rate)),
            ("accrued_premium", -nominal * coupon_rate * accrued_days / 360),
        )
    else:
        amounts = (("recovery_redemption", nominal * recovery_rate),)
    components = tuple(
        _flow(context, f"{identifier}-{kind}", kind, _round_cash(amount), date_due, paid)
        for kind, amount in amounts
    )
    settled_amount = _round_cash(sum(Decimal(str(flow.amount_eur)) for flow in components))
    net = _flow(context, f"{identifier}-default-settlement", "default_settlement", settled_amount, date_due, paid)
    return components, net


def price_credit_default(product: Product, context: CreditDefaultContext) -> CreditDefaultResult:
    """Price only known claims; the live credit engine owns contingent valuation."""
    terms, schedule, periods = _contract(product)
    if (
        context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
        context.instrument_type, context.reference_entity_id, context.nominal_eur, context.position_side,
    ) != (
        product.product_id, schedule.terms_version, terms.fingerprint, schedule.fingerprint,
        terms.instrument_type, terms.reference_entity_id, product.intent.nominal, product.intent.side,
    ) or canonical_fingerprint(context.model_dump(mode="json", exclude={"fingerprint"})) != context.fingerprint:
        raise CreditDefaultError("CREDIT_DEFAULT_CONTEXT", "Le contexte de défaut ne correspond pas au produit figé.")

    facts = context.facts
    default = context.paid_basis.default if context.paid_basis else facts.default
    recovery = context.paid_basis.recovery if context.paid_basis else facts.recovery
    settlement, components, earned, accrued_days = None, (), (), None
    if default is not None:
        earned = _earned_coupon_flows(terms, periods, context, default.effect_date)
        accrued_days = 0
        if isinstance(terms, CDSTerms):
            period = next(period for period in periods if period.accrual_start <= default.effect_date < period.accrual_end)
            accrued_days = cds_default_accrued_days(period, default.effect_date)
        if recovery is not None:
            components, settlement = _default_components(terms, context, accrued_days, recovery)
    claims = (*earned, settlement) if settlement is not None else earned
    claim_pv = fsum(flow.pv_eur for flow in claims)
    economic_pv = claim_pv if settlement is not None else None
    due = None if settlement is None else fsum(flow.amount_eur for flow in claims if flow.state != "paid")
    cash = settlement.amount_eur if settlement is not None and settlement.state == "paid" else 0
    same_day_cash = fsum(flow.amount_eur for flow in claims if flow.paid_date == context.value_date)
    return CreditDefaultResult(
        product_id=context.product_id, terms_version=context.terms_version,
        terms_fingerprint=context.terms_fingerprint, schedule_fingerprint=context.schedule_fingerprint,
        context_fingerprint=context.fingerprint, instrument_type=context.instrument_type,
        nominal_eur=context.nominal_eur, position_side=context.position_side,
        valuation_date=context.valuation_date, value_date=context.value_date, cutoff=context.cutoff, state=facts.state,
        default_date=default.effect_date if default else None,
        default_known_at=max(default.available_at, default.validated_at) if default else None,
        recovery_fraction=recovery.recovery_fraction if recovery else None, accrued_days_at_default=accrued_days,
        contingent_pv_eur=0 if default else None, claim_pv_eur=claim_pv, economic_pv_eur=economic_pv,
        net_due_eur=due, realized_cash_eur=cash, cash_on_value_date_eur=same_day_cash,
        settlement_flow=settlement, components=components, earned_coupon_flows=earned,
        measure=CreditDefaultMeasure(value=economic_pv),
    )
