"""Residual cash and survival for the synthetic single-name CLN contract."""

from datetime import date, timedelta
from decimal import Decimal
from math import exp, fsum

from ..core.product.credit_default import _round_cash
from ..core.product.credit_pricing import SurvivalCurve
from ..core.product.exotic_credit_mc import CreditMcContract, simulate_credit_mc
from ..core.product.models import ExoticTerms, Product
from .exotic_deal_result import ExoticResidual, ResidualFlow
from .product_repository import ProductError


DEFAULT_EVENT = "credit:default"
RECOVERY_EVENT = "credit:recovery"
SETTLEMENT_EVENT = "credit:settlement"


def cln_contract(product: Product) -> CreditMcContract:
    terms = product.terms
    if (not isinstance(terms, ExoticTerms) or terms.instrument_type != "EXOTIC_CREDIT"
            or terms.contract.to_dict().get("kind") != "cln" or len(terms.reference_entities) != 1):
        raise ProductError("EXOTIC_CLN_TERMS", "Le parcours crédit couvre les CLN synthétiques single-name.", 422)
    return CreditMcContract.model_validate(
        {**terms.contract.to_dict(), "side": product.intent.side, "nominal_eur": product.intent.nominal},
    )


def cln_civil_date(product: Product, time: float) -> date:
    days = round(time * 365)
    if abs(time * 365 - days) > 1e-8:
        raise ProductError("EXOTIC_CLN_CALENDAR", "La date de crédit doit être entière sur l’axe civil ACT/365F.", 422)
    return product.terms.time_origin + timedelta(days=days)


def cln_settlement_date(product: Product, default_date: date) -> date:
    lag = cln_civil_date(product, cln_contract(product).default_settlement_delay_years) - product.terms.time_origin
    return default_date + lag


def cln_redemption_amount(contract: CreditMcContract, recovery: float) -> float:
    side = 1 if contract.side == "BUY" else -1
    return _round_cash(side * Decimal(str(contract.nominal_eur)) * Decimal(str(recovery)))


def cln_coupon_amount(contract: CreditMcContract, index: int) -> float:
    side = 1 if contract.side == "BUY" else -1
    coupon = contract.coupons[index]
    return _round_cash(side * Decimal(str(contract.nominal_eur)) * Decimal(str(contract.coupon_bps)) *
                       Decimal(str(coupon.year_fraction)) / 10_000)


def _claim(flow_id, event_id, payment, amount, valuation_date, discount, confirmation=None) -> ResidualFlow:
    elapsed = (payment - valuation_date).days
    state = "receivable" if elapsed > 0 else "due" if elapsed == 0 else "overdue"
    return ResidualFlow(flow_id=flow_id, payment_event_id=event_id, payment_date=payment,
                        state="paid" if confirmation else state,
                        amount_eur=confirmation.fact.amount_eur if confirmation else amount,
                        pv_eur=0 if confirmation else amount * exp(-discount * max(elapsed, 0) / 365),
                        payment_fact_id=confirmation.id if confirmation else None)


def _rolled_cln(request, elapsed, future):
    contract = request.contract
    prior = request.market.marginals[0]
    knots = tuple((time - elapsed, hazard)
                  for time, hazard in zip(prior.curve.maturities, prior.curve.hazards, strict=True) if time > elapsed)
    curve = SurvivalCurve(maturities=tuple(knot[0] for knot in knots), hazards=tuple(knot[1] for knot in knots))
    market = request.market.model_copy(update={"marginals": (prior.model_copy(update={"curve": curve}),)})
    remaining = contract.model_copy(update={
        "maturity_years": contract.maturity_years - elapsed,
        "protected_from": max(0.0, contract.protected_from - elapsed),
        "principal_payment_years": (contract.principal_payment_years or contract.maturity_years) - elapsed,
        "coupons": tuple(coupon.model_copy(update={
            "start": coupon.start - elapsed, "end": coupon.end - elapsed, "payment": coupon.payment - elapsed,
            "observation": coupon.survival_time - elapsed,
        }) for coupon in future),
        "initial_accrued_fraction": 0.0,
    })
    return request.model_copy(update={"contract": remaining, "market": market})


def price_booked_cln(product: Product, *, valuation_date: date, request, facts) -> ExoticResidual:
    contract = cln_contract(product)
    if request.contract != contract or len(request.market.marginals) != 1 or (
            request.market.marginals[0].reference_entity_id != product.terms.reference_entities[0]
            or request.realized is not None):
        raise ProductError("EXOTIC_CLN_MARKET_BINDING", "La CLN et son marché de booking sont incohérents.", 422)
    eligible = {row.event_id: row for row in facts if row.status == "validated"}
    default = eligible.get(DEFAULT_EVENT)
    recovery = eligible.get(RECOVERY_EVENT)
    settled = eligible.get(SETTLEMENT_EVENT)
    default_day = default.fact.effect_date if default is not None else None
    rate = request.market.discount_rate + request.market.funding_bps * 1e-4
    rows, future = [], []
    for index, coupon in enumerate(contract.coupons):
        observation = cln_civil_date(product, coupon.survival_time)
        if default_day is not None and observation >= default_day:
            continue
        if observation > valuation_date:
            future.append(coupon)
            continue
        flow_id = f"credit-coupon-{index + 1}"
        event_id = f"{flow_id}:payment"
        rows.append(_claim(flow_id, event_id, cln_civil_date(product, coupon.payment), cln_coupon_amount(contract, index),
                           valuation_date, rate, eligible.get(event_id)))
    if default_day is not None:
        if recovery is None:
            return ExoticResidual("recovery_pending", None, None, fsum(row.pv_eur for row in rows), None, tuple(rows))
        rows.append(_claim("cln-default-redemption", SETTLEMENT_EVENT, cln_settlement_date(product, default_day),
                           cln_redemption_amount(contract, recovery.fact.recovery_fraction), valuation_date, rate, settled))
        pv = fsum(row.pv_eur for row in rows)
        state = "settled" if all(row.state == "paid" for row in rows) else "settlement_pending"
        return ExoticResidual(state, pv, 0.0, pv, (pv, pv), tuple(rows))

    maturity = cln_civil_date(product, contract.maturity_years)
    if valuation_date >= maturity:
        payment = eligible.get("principal:payment")
        if payment is None:
            raise ProductError("EXOTIC_CLN_SURVIVAL_MISSING", "Le règlement du principal à maturité doit être validé.", 422)
        rows.append(_claim("cln-principal", "principal:payment", payment.event_date,
                           cln_redemption_amount(contract, 1.0), valuation_date, rate, payment))
        pv = fsum(row.pv_eur for row in rows)
        return ExoticResidual("settled" if all(row.state == "paid" for row in rows) else "settlement_pending",
                              pv, 0.0, pv, (pv, pv), tuple(rows))
    elapsed = (valuation_date - product.terms.time_origin).days / 365
    priced = simulate_credit_mc(request if elapsed == 0 else _rolled_cln(request, elapsed, future)).result.estimate.dirty_pv_eur
    claim_pv = fsum(row.pv_eur for row in rows)
    pv = fsum((priced.mean, claim_pv))
    return ExoticResidual("alive", pv, priced.mean, claim_pv,
                          (pv - priced.ci95_half_width, pv + priced.ci95_half_width), tuple(rows))
