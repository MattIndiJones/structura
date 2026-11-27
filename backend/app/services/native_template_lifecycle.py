"""Contractual fact targets for deterministic Deals on a frozen native schedule."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import isclose
from typing import Literal
from zoneinfo import ZoneInfo

from ..core.product.cds_schedule import cds_default_accrued_days
from ..core.product.credit_default import _round_cash
from ..core.product.models import CDSTerms, CLNTerms, FRNTerms, IRSTerms, FrozenModel, Product
from ..core.product.native_schedule_models import SchedulePeriod
from ..core.product.rates_payscript import rates_payoff
from ..core.product.rates_pricing import RatesPayoffInput, _template_amount
from .product_repository import ProductError


TEMPLATE_TERMS = (FRNTerms, IRSTerms, CDSTerms, CLNTerms)
_PARIS = ZoneInfo("Europe/Paris")
_CREDIT_EVENT_KINDS = {"default": "credit_default", "recovery": "credit_recovery", "settlement": "credit_settlement"}
_PAYMENTS = {"cashflow", "principal", "initial_settlement"}


@dataclass(frozen=True)
class TemplateEvent:
    event_id: str
    kind: str
    date: date
    flow_id: str | None = None
    leg_id: str | None = None
    leg_kind: str | None = None
    period: SchedulePeriod | None = None


class TemplateEventState(FrozenModel):
    event_id: str
    kind: Literal["observation", "cashflow", "principal", "initial_settlement", "credit_settlement"]
    date: date
    flow_id: str | None
    leg_id: str | None
    accrual_start: date | None = None
    accrual_end: date | None = None
    credit_observation_date: date | None = None
    expected_amount_eur: float | None = None
    paid_amount_eur: float | None = None
    fixing_rate_fraction: float | None = None
    state: Literal["scheduled", "fixing_pending", "fixed", "due", "paid", "cancelled"]
    fact_kind: Literal["rate_fixing", "payment_confirmed"] | None = None


def _events(product: Product) -> tuple[TemplateEvent, ...]:
    rows = []
    for leg in product.native_schedule.legs:
        for period in leg.periods:
            if period.fixing_date:
                rows.append(TemplateEvent(f"{period.flow_id}:fixing", "observation", period.fixing_date,
                                          period.flow_id, leg.leg_id, leg.kind, period))
            rows.append(TemplateEvent(f"{period.flow_id}:payment", "cashflow", period.payment_date,
                                      period.flow_id, leg.leg_id, leg.kind, period))
        rows.extend(TemplateEvent(event.event_id, event.kind, event.date, event.flow_id, leg.leg_id, leg.kind)
                    for event in leg.events if event.kind in _PAYMENTS and event.date is not None)
    return tuple(sorted(rows, key=lambda event: (event.date, event.event_id)))


def _credit_ids(product: Product) -> dict[str, str]:
    return {kind: f"{product.terms.instrument_type.lower()}:{name}" for name, kind in _CREDIT_EVENT_KINDS.items()}


def template_event(product: Product, event_id: str, fact) -> TemplateEvent:
    terms = product.terms
    if isinstance(terms, (CDSTerms, CLNTerms)) and _credit_ids(product).get(fact.kind) == event_id:
        return TemplateEvent(event_id, fact.kind, fact.effect_date)
    event = next((item for item in _events(product) if item.event_id == event_id), None)
    if event is None:
        raise ProductError("NATIVE_FACT_EVENT_INVALID", "Sélectionnez un événement du calendrier contractuel figé.", 422)
    return event


def _direction(product: Product) -> int:
    return 1 if product.intent.side == "BUY" else -1


def _rates_amount(product: Product, event: TemplateEvent, rate: float | None, payoff) -> float | None:
    terms, period = product.terms, event.period
    floating = event.leg_kind == "floating_coupon"
    if floating and rate is None:
        return None
    fixed = event.leg_kind == "fixed_coupon"
    sign = -_direction(product) if floating and isinstance(terms, IRSTerms) else _direction(product)
    request = RatesPayoffInput(
        instrument_type=terms.instrument_type, flow_id=event.flow_id, leg_id=event.leg_id, kind=event.leg_kind,
        period_id=period.period_id if period else None, rank=period.rank if period else None, payment_date=event.date,
        nominal_eur=product.intent.nominal, accrual_fraction=period.year_fraction if period else None,
        day_count_days=period.day_count_days if period else None, rate=terms.fixed_leg.coupon_rate if fixed else rate,
        margin_bps=terms.floating_leg.margin_bps if floating else None,
        redemption_fraction=terms.redemption_fraction if event.kind == "principal" else None,
        fixing_state="fixed" if floating else None, rate_origin="fixing" if floating else "contractual" if fixed else None,
        is_fixed=floating or fixed,
    )
    return sign * payoff(request).amount_eur


def _credit_amount(product: Product, event: TemplateEvent, booking: dict) -> float:
    terms, period = product.terms, event.period
    nominal = _direction(product) * Decimal(str(product.intent.nominal))
    if event.kind == "initial_settlement":
        amount = booking.get("initial_settlement_eur")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ProductError("NATIVE_FACT_PAYMENT_BASIS", "Le règlement initial signé est absent de la preuve de booking.", 422)
        return float(amount)
    if event.kind == "principal":
        return _round_cash(nominal * Decimal(str(terms.redemption_fraction)))
    rate = (-Decimal(str(terms.premium_leg.coupon_bps)) / 10_000 if isinstance(terms, CDSTerms)
            else Decimal(str(terms.fixed_leg.coupon_rate)))
    return _round_cash(nominal * rate * period.day_count_days / period.day_count_denominator)


def _credit_periods(product: Product) -> tuple[SchedulePeriod, ...]:
    return next(leg.periods for leg in product.native_schedule.legs if leg.kind in {"premium", "fixed_coupon"})


def _credit_settlement_amount(product: Product, default_date: date, recovery: float) -> float:
    terms = product.terms
    nominal = _direction(product) * Decimal(str(product.intent.nominal))
    recovery_rate = Decimal(str(recovery))
    if isinstance(terms, CLNTerms):
        return _round_cash(nominal * recovery_rate)
    protection = _round_cash(nominal * (1 - recovery_rate))
    period = next(item for item in _credit_periods(product) if item.accrual_start <= default_date < item.accrual_end)
    days = cds_default_accrued_days(period, default_date)
    accrued = _round_cash(-nominal * Decimal(str(terms.premium_leg.coupon_bps)) / 10_000 * days / 360)
    return _round_cash(Decimal(str(protection)) + Decimal(str(accrued)))


def _earliest_settlement(terms, default, recovery) -> date:
    lag = terms.default_settlement_lag_calendar_days if isinstance(terms, CLNTerms) else 0
    return max(default.fact.effect_date + timedelta(days=lag), recovery.fact.effect_date)


def _cancelled(event: TemplateEvent, default) -> bool:
    if not default or event.kind == "initial_settlement":
        return False
    return event.kind == "principal" or event.period.credit_observation_date >= default.fact.effect_date


def template_event_states(product: Product, booking: dict, eligible, cutoff: datetime) -> tuple[TemplateEventState, ...]:
    terms = product.terms
    credit = isinstance(terms, (CDSTerms, CLNTerms))
    today = cutoff.astimezone(_PARIS).date()
    evidence = {row.event_id: row for row in eligible}
    default = evidence.get(_credit_ids(product)["credit_default"]) if credit else None
    payoff = rates_payoff(product)[0] if not credit and terms.rates_script else _template_amount
    states = []
    for event in _events(product):
        period = event.period
        fact = evidence.get(event.event_id)
        rate = None
        amount = None
        action = None
        status = "scheduled"
        if event.kind == "observation":
            if fact is not None:
                rate, status = fact.fact.rate_fraction, "fixed"
            elif event.date <= today:
                status, action = "fixing_pending", "rate_fixing"
        elif credit and _cancelled(event, default):
            status = "cancelled"
        else:
            fixing = evidence.get(f"{event.flow_id}:fixing")
            rate = fixing.fact.rate_fraction if fixing else None
            amount = _credit_amount(product, event, booking) if credit else _rates_amount(product, event, rate, payoff)
            if fact:
                status = "paid"
            elif event.date <= today:
                if amount is None:
                    status = "fixing_pending"
                else:
                    status, action = "due", "payment_confirmed"
        states.append(TemplateEventState(
            event_id=event.event_id, kind=event.kind, date=event.date, flow_id=event.flow_id, leg_id=event.leg_id,
            accrual_start=period.accrual_start if period else None, accrual_end=period.accrual_end if period else None,
            credit_observation_date=period.credit_observation_date if period else None,
            expected_amount_eur=amount, paid_amount_eur=fact.fact.amount_eur if status == "paid" else None,
            fixing_rate_fraction=rate, state=status, fact_kind=action,
        ))
    if credit and default is not None:
        ids = _credit_ids(product)
        recovery, settlement = evidence.get(ids["credit_recovery"]), evidence.get(ids["credit_settlement"])
        if recovery is not None:
            earliest = _earliest_settlement(terms, default, recovery)
            states.append(TemplateEventState(
                event_id=ids["credit_settlement"], kind="credit_settlement", date=settlement.fact.effect_date if settlement else earliest,
                flow_id=None, leg_id=None,
                expected_amount_eur=_credit_settlement_amount(product, default.fact.effect_date, recovery.fact.recovery_fraction),
                paid_amount_eur=settlement.fact.amount_eur if settlement else None,
                state="paid" if settlement else "due" if earliest <= today else "scheduled",
            ))
    return tuple(sorted(states, key=lambda state: (state.date, state.event_id)))


def template_credit_targets(product: Product, eligible) -> tuple[dict, ...]:
    terms = product.terms
    if not isinstance(terms, (CDSTerms, CLNTerms)):
        return ()
    ids = _credit_ids(product)
    evidence = {row.event_id: row for row in eligible}
    default = evidence.get(ids["credit_default"])
    recovery = evidence.get(ids["credit_recovery"])
    if ids["credit_settlement"] in evidence or any(
        event.kind == "principal" and event.event_id in evidence for event in _events(product)
    ):
        return ()
    amount = None
    if default is None:
        kind, earliest = "credit_default", terms.effective_date
    elif recovery is None:
        kind, earliest = "credit_recovery", default.fact.effect_date
    else:
        kind, earliest = "credit_settlement", _earliest_settlement(terms, default, recovery)
        amount = _credit_settlement_amount(product, default.fact.effect_date, recovery.fact.recovery_fraction)
    return ({"event_id": ids[kind], "kind": kind, "reference_entity_id": terms.reference_entity_id,
             "earliest_effect_date": earliest, "expected_amount_eur": amount},)


def _validate_credit_fact(product: Product, fact, observed: date, eligible):
    terms = product.terms
    if not isinstance(terms, (CDSTerms, CLNTerms)) or fact.reference_entity_id != terms.reference_entity_id:
        raise ProductError("NATIVE_CREDIT_REFERENCE", "La preuve porte une autre entité de référence.", 422)
    if fact.effect_date > observed:
        raise ProductError("NATIVE_CREDIT_DATE", "La date d’effet doit être acquise à la date d’observation.", 422)
    ids = _credit_ids(product)
    evidence = {row.event_id: row for row in eligible}
    if fact.kind == "credit_default":
        protection_end = _credit_periods(product)[-1].credit_observation_date
        if not terms.effective_date <= fact.effect_date <= protection_end:
            raise ProductError("NATIVE_CREDIT_DEFAULT_DATE", "Le défaut doit relever de la période de protection.", 422)
        for event in _events(product):
            if event.event_id in evidence and (event.kind == "principal" or (
                event.period and event.period.credit_observation_date >= fact.effect_date
            )):
                raise ProductError("NATIVE_CREDIT_DEFAULT_CONFLICT", "Le défaut contredit un paiement déjà validé.", 422)
        return
    default = evidence.get(ids["credit_default"])
    if default is None or fact.effect_date < default.fact.effect_date:
        raise ProductError("NATIVE_CREDIT_DEFAULT_REQUIRED", "Un défaut validé est requis avant ce fait.", 422)
    if fact.kind == "credit_settlement":
        recovery = evidence.get(ids["credit_recovery"])
        if recovery is None or fact.effect_date < _earliest_settlement(terms, default, recovery):
            raise ProductError("NATIVE_CREDIT_SETTLEMENT_DATE", "Le règlement exige un recouvrement validé et le respect du délai contractuel.", 422)
        amount = _credit_settlement_amount(product, default.fact.effect_date, recovery.fact.recovery_fraction)
        if not isclose(fact.amount_eur, amount, rel_tol=0, abs_tol=.005):
            raise ProductError("NATIVE_FACT_PAYMENT_AMOUNT", "Le règlement du défaut contredit le montant contractuel signé.", 422)


def validate_template_fact(product: Product, booking: dict, event: TemplateEvent, proposal, eligible, now: datetime):
    fact, observed = proposal.fact, proposal.observed_at.astimezone(_PARIS).date()
    if proposal.available_at > now:
        raise ProductError("NATIVE_FACT_DATE_OR_KIND", "Cette preuve doit être disponible à cet arrêté.", 422)
    if event.kind in _CREDIT_EVENT_KINDS.values():
        _validate_credit_fact(product, fact, observed, eligible)
        return
    if (event.kind == "observation" and fact.kind == "rate_fixing" and event.date == observed):
        return
    if event.kind not in _PAYMENTS or fact.kind != "payment_confirmed" or observed < event.date:
        raise ProductError("NATIVE_FACT_DATE_OR_KIND", "Le type ou l’horodatage contredit la date contractuelle de ce fait.", 422)

    row = next(item for item in template_event_states(product, booking, eligible, now) if item.event_id == event.event_id)
    if row.state == "cancelled":
        raise ProductError("NATIVE_FACT_PAYMENT_CANCELLED", "Ce flux est annulé à la suite du défaut validé.", 422)
    amount = row.expected_amount_eur
    if amount is None:
        raise ProductError("NATIVE_FACT_FIXING_REQUIRED", "Le fixing de la période doit être validé avant le règlement.", 422)
    if not isclose(fact.amount_eur, amount, rel_tol=0, abs_tol=.005):
        raise ProductError("NATIVE_FACT_PAYMENT_AMOUNT", "Le montant réglé contredit le flux contractuel signé.", 422)


def template_resolution(product: Product, rows: tuple[TemplateEventState, ...], eligible, cutoff: datetime):
    """Resolve only with actual evidence of the last payable cash, never by date alone."""
    evidence = {row.event_id: row for row in eligible}
    ids = _credit_ids(product)
    default, settlement = evidence.get(ids["credit_default"]), evidence.get(ids["credit_settlement"])
    if default is not None and settlement is None:
        return None
    if default is None and cutoff.astimezone(_PARIS).date() < product.terms.maturity_date:
        return None
    cash_states = tuple(row for row in rows if row.kind in _PAYMENTS and row.state != "cancelled")
    if any(row.state != "paid" and row.expected_amount_eur != 0 for row in cash_states):
        return None
    payments = [evidence[row.event_id] for row in cash_states if row.state == "paid"]
    if settlement is not None:
        payments.append(settlement)
    if not payments:
        return None
    last_cash = max(row.observed_at.astimezone(_PARIS).date() for row in payments)
    amount = sum(Decimal(str(row.fact.amount_eur)) for row in payments)
    payout = float(_direction(product) * amount / Decimal(str(product.intent.nominal)))
    date_closed = last_cash if settlement is not None else max(last_cash, product.terms.maturity_date)
    return ("défaut" if default else "final", date_closed, payout)
