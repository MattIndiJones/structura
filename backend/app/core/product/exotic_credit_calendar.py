"""Explicit civil ACT/365F dates for a EUR credit Monte Carlo contract."""
from __future__ import annotations

from datetime import date, timedelta
from math import exp, isclose
from typing import Literal, TYPE_CHECKING

from pydantic import Field

from .models import FrozenModel

if TYPE_CHECKING:
    from .exotic_credit_mc import CreditMcRequest, CreditMcResult


class CreditCouponDates(FrozenModel):
    accrual_start_date: date
    accrual_end_date: date
    observation_date: date
    payment_date: date


class CreditCalendar(FrozenModel):
    convention: Literal["civil_unadjusted_act365f"]
    protection_start_date: date
    protection_end_date: date
    default_settlement_lag_days: int = Field(ge=0, le=730, strict=True)
    principal_payment_date: date | None = None
    coupons: tuple[CreditCouponDates, ...] = Field(max_length=360)


class CreditDatedFlow(FrozenModel):
    flow_id: str
    kind: Literal["premium", "coupon", "principal"]
    accrual_start_date: date | None = None
    accrual_end_date: date | None = None
    observation_date: date
    payment_date: date
    year_fraction: float | None = None
    amount_if_payable_eur: float
    expected_amount_eur: float
    pv_eur: float
    payable_probability: float


class CreditContingentFlow(FrozenModel):
    kind: Literal["protection", "accrual_on_default", "default_redemption"]
    trigger_rank: int
    earliest_payment_date: date
    latest_payment_date: date
    pv_eur: float


class CreditContractSchedule(FrozenModel):
    convention: Literal["civil_unadjusted_act365f"]
    origin_date: date
    protection_start_date: date
    protection_end_date: date
    default_settlement_lag_days: int
    flows: tuple[CreditDatedFlow, ...]
    contingent_flows: tuple[CreditContingentFlow, ...]


def _act365f(origin: date, day: date) -> float:
    return (day - origin).days / 365


def validate_credit_calendar(calendar: CreditCalendar, request: CreditMcRequest, origin: date) -> None:
    """Require the supplied civil dates to be the same contract the engine prices."""
    contract = request.contract
    if request.realized is not None:
        raise ValueError("Le scénario de défaut réalisé porte son propre échéancier Lot 3.")
    if calendar.protection_end_date > date.max - timedelta(days=calendar.default_settlement_lag_days):
        raise ValueError("Le dernier règlement du défaut dépasse l’horizon calendaire.")
    if (contract.protected_from, contract.maturity_years, contract.default_settlement_delay_years) != (
        _act365f(origin, calendar.protection_start_date), _act365f(origin, calendar.protection_end_date),
        calendar.default_settlement_lag_days / 365,
    ):
        raise ValueError("La protection ou le délai de règlement du défaut contredit les dates civiles ACT/365F.")
    if len(calendar.coupons) != len(contract.coupons):
        raise ValueError("Chaque coupon du moteur doit porter ses dates contractuelles.")
    if contract.kind == "cln":
        principal_day = calendar.principal_payment_date or calendar.protection_end_date
        if (contract.principal_payment_years or contract.maturity_years) != _act365f(origin, principal_day):
            raise ValueError("La date de remboursement de la CLN contredit l’échéancier du moteur.")
    elif calendar.principal_payment_date is not None:
        raise ValueError("Seule une CLN porte une date de remboursement du nominal.")

    for index, (coupon, dates) in enumerate(zip(contract.coupons, calendar.coupons, strict=True), start=1):
        expected = tuple(_act365f(origin, day) for day in (
            dates.accrual_start_date, dates.accrual_end_date, dates.observation_date, dates.payment_date,
        ))
        expected_fraction = _act365f(dates.accrual_start_date, dates.accrual_end_date)
        if ((coupon.start, coupon.end, coupon.survival_time, coupon.payment) != expected
                or not isclose(coupon.year_fraction, expected_fraction, rel_tol=0, abs_tol=1e-12)
                or dates.payment_date < dates.accrual_end_date or dates.accrual_end_date > calendar.protection_end_date):
            raise ValueError(f"Le coupon {index} contredit les dates ou le prorata ACT/365F du contrat.")


def project_credit_flows(calendar: CreditCalendar, request: CreditMcRequest, origin: date,
                         result: CreditMcResult) -> CreditContractSchedule:
    """Keep the date witness and use the very same MC observations and leg amounts."""
    assert result.estimate is not None
    contract, market = request.contract, request.market
    estimate = result.estimate
    sign = 1 if contract.side == "BUY" else -1
    is_note = contract.kind == "cln"
    discount = market.discount_rate + market.funding_bps / 10_000
    survival = {item.time_years: item.estimate.mean for item in result.survival}
    annual_rate = (result.payscript_metadata.effective_coupon_rate if result.payscript_metadata is not None
                   else contract.coupon_bps / 10_000)
    flows = []
    for index, (coupon, dates) in enumerate(zip(contract.coupons, calendar.coupons, strict=True), start=1):
        full = sign * (1 if is_note else -1) * contract.nominal_eur * annual_rate * coupon.year_fraction
        probability = survival[coupon.survival_time]
        expected = full * probability
        flows.append(CreditDatedFlow(
            flow_id=f"credit-coupon-{index}", kind="coupon" if is_note else "premium",
            **dates.model_dump(), year_fraction=coupon.year_fraction, amount_if_payable_eur=full,
            expected_amount_eur=expected, pv_eur=expected * exp(-discount * coupon.payment),
            payable_probability=probability,
        ))
    if is_note:
        full = sign * contract.nominal_eur
        probability = survival[contract.maturity_years]
        expected = full * probability
        payment_time = contract.principal_payment_years or contract.maturity_years
        flows.append(CreditDatedFlow(
            flow_id="principal", kind="principal", observation_date=calendar.protection_end_date,
            payment_date=calendar.principal_payment_date or calendar.protection_end_date,
            amount_if_payable_eur=full, expected_amount_eur=expected, pv_eur=expected * exp(-discount * payment_time),
            payable_probability=probability,
        ))
    lag = timedelta(days=calendar.default_settlement_lag_days)
    start, end = calendar.protection_start_date, calendar.protection_end_date
    leg_values = ([("default_redemption", sign, estimate.default_redemption_pv_eur, start, end)] if is_note else
                  [("protection", sign, estimate.protection_pv_eur, start, end)])
    if not is_note:
        accrued = [(max(start, period.accrual_start_date), min(end, period.accrual_end_date))
                   for period in calendar.coupons if period.accrual_start_date < end and period.accrual_end_date > start]
        if accrued:
            leg_values.append(("accrual_on_default", -sign, estimate.accrual_on_default_pv_eur,
                               min(begin for begin, _ in accrued), max(finish for _, finish in accrued)))
    contingent = tuple(CreditContingentFlow(
        kind=kind, trigger_rank=contract.trigger_rank or 1,
        earliest_payment_date=begin + lag, latest_payment_date=finish + lag, pv_eur=factor * value.mean,
    ) for kind, factor, value, begin, finish in leg_values if value is not None)
    return CreditContractSchedule(
        convention=calendar.convention, origin_date=origin, protection_start_date=calendar.protection_start_date,
        protection_end_date=calendar.protection_end_date, default_settlement_lag_days=calendar.default_settlement_lag_days,
        flows=tuple(flows), contingent_flows=contingent,
    )
