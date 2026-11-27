"""Residual EUR valuation of a booked rates Product against validated facts."""

from datetime import date
from math import exp, fsum
from typing import TYPE_CHECKING

import numpy as np

from ..core.product.exotic_rates_mc import (
    ExoticRatesTerms, FixedCashflow, ForwardPeriod, HwCurve, HwMarket, RateCoupon,
    RangeAccrualCoupon, RatesMCSettings, _cashflow_amount, _compile_coupon_scripts, price_exotic_rates,
)
from ..core.product.models import ExoticTerms, Product
from .exotic_deal_result import ExoticResidual, ResidualFlow
from .product_repository import ProductError

if TYPE_CHECKING:
    from .exotic_product_lifecycle import FactRow


def _contract(product: Product) -> ExoticRatesTerms:
    if not isinstance(product.terms, ExoticTerms) or product.terms.instrument_type != "EXOTIC_RATES":
        raise ProductError("EXOTIC_RATES_TERMS", "Le dossier ne porte pas de termes exotiques de taux.", 422)
    return ExoticRatesTerms.model_validate({
        **product.terms.contract.to_dict(), "side": product.intent.side, "nominal_eur": product.intent.nominal,
    })


def _events(product: Product):
    return {event.event_id: event for leg in product.native_schedule.legs for event in leg.events}


def _fact_index(facts):
    return {row.event_id: row for row in facts if row.status == "validated"}


def _missing_fixing(event_id):
    raise ProductError("EXOTIC_FIXING_MISSING", f"Fixing validé requis pour {event_id} à cet arrêté.", 422)


def _coupon_fixings(flow, valuation_date, events, facts):
    if isinstance(flow, FixedCashflow):
        return flow, ()
    if isinstance(flow, RateCoupon):
        event_id = f"{flow.flow_id}:fixing"
        row = facts.get(event_id)
        if events[event_id].date <= valuation_date and row is None:
            _missing_fixing(event_id)
        return (flow, ()) if row is None else (
            flow.model_copy(update={"realized_rate": row.fact.rate_fraction}), (row.id,),
        )
    observations = []
    identifiers = []
    for index, observation in enumerate(flow.observations, 1):
        event_id = f"{flow.flow_id}:observation:{index}"
        row = facts.get(event_id)
        if events[event_id].date <= valuation_date and row is None:
            _missing_fixing(event_id)
        if row is not None:
            identifiers.append(row.id)
            observation = observation.model_copy(update={"realized_rate": row.fact.rate_fraction})
        observations.append(observation)
    return flow.model_copy(update={"observations": tuple(observations)}), tuple(identifiers)


def _amount(terms, flow, market=None) -> float:
    compiled = _compile_coupon_scripts(terms).get(flow.flow_id)
    value = _cashflow_amount(terms, flow, market, {0.0: np.zeros(1)}, compiled)
    side = 1 if terms.side == "BUY" else -1
    return side * float(np.asarray(value).item())


def signed_rates_payment(product: Product, event_id: str, facts: "tuple[FactRow, ...]") -> float:
    """Resolve a due variable coupon from the same payoff used in pricing."""
    terms = _contract(product)
    events = _events(product)
    event = events[event_id]
    flow = next((flow for flow in terms.cashflows if flow.flow_id == event.flow_id), None)
    if not isinstance(flow, (RateCoupon, RangeAccrualCoupon)) or terms.exercises:
        raise ProductError("EXOTIC_FACT_PAYMENT_UNQUALIFIED", "Ce paiement variable reste à qualifier.", 422)
    fixed, _ = _coupon_fixings(flow, event.date, events, _fact_index(facts))
    return _amount(terms, fixed)


def roll_rates_market(market: HwMarket, elapsed: float, *, needs_projection: bool = True) -> HwMarket:
    """Rebase the two frozen curves without deriving a new market observation."""
    if elapsed == 0:
        return market

    def roll(curve):
        if elapsed >= curve.pillars[-1].time:
            raise ProductError("EXOTIC_ROLL_COVERAGE", "La courbe figée ne couvre plus la vie résiduelle.", 422)
        base = curve.log_factor(elapsed)
        return HwCurve.model_validate({"pillars": [{"time": 0.0, "factor": 1.0}, *(
            {"time": node.time - elapsed, "factor": exp(curve.log_factor(node.time) - base)}
            for node in curve.pillars if node.time > elapsed
        )]})

    return market.model_copy(update={
        "discount": roll(market.discount),
        "projection": roll(market.projection) if needs_projection else market.projection,
    })


def _shift_index(index, elapsed):
    if isinstance(index, ForwardPeriod):
        return index.model_copy(update={"start": index.start - elapsed, "end": index.end - elapsed})
    return index.model_copy(update={
        "fixed_periods": tuple(period.model_copy(update={"payment": period.payment - elapsed}) for period in index.fixed_periods),
        "floating_periods": tuple(_shift_index(period, elapsed) for period in index.floating_periods),
    })


def _remaining_flow(flow, elapsed):
    changes = {"payment": flow.payment - elapsed}
    if isinstance(flow, RateCoupon):
        changes["fixing"] = flow.fixing - elapsed
        if flow.realized_rate is None:
            changes.update(index=_shift_index(flow.index, elapsed))
            if flow.spread_index is not None:
                changes["spread_index"] = _shift_index(flow.spread_index, elapsed)
    elif isinstance(flow, RangeAccrualCoupon):
        changes["observations"] = tuple(observation.model_copy(update={
            "time": observation.time - elapsed,
            "index": (_shift_index(observation.index, elapsed) if observation.realized_rate is None else observation.index),
        }) for observation in flow.observations)
    return flow.model_copy(update=changes)


def _exercise_path(terms, events, valuation_date, facts):
    for index, right in enumerate(terms.exercises):
        event_id = f"{right.exercise_id}:decision"
        if events[event_id].date > valuation_date:
            return None, terms.exercises[index:]
        notice = facts.get(event_id)
        if notice is None:
            raise ProductError("EXOTIC_EXERCISE_MISSING", f"Avis d’exercice validé requis pour {event_id}.", 422)
        if notice.fact.exercised:
            return right, ()
    return None, ()


def price_exotic_rates_residual(
    product: Product, *, valuation_date: date, market: HwMarket,
    settings: RatesMCSettings, facts: "tuple[FactRow, ...]",
) -> ExoticResidual:
    terms = _contract(product)
    elapsed = (valuation_date - product.terms.time_origin).days / 365
    events, evidence = _events(product), _fact_index(facts)
    exercised, future_rights = _exercise_path(terms, events, valuation_date, evidence)
    cashflows = [(flow, f"{flow.flow_id}:payment") for flow in terms.cashflows if exercised is None
                 or flow.payment < exercised.decision or (flow.payment == exercised.decision and exercised.coupon_priority == "before")]
    if exercised is not None:
        redemption = FixedCashflow(flow_id=exercised.exercise_id, payment=exercised.settlement,
                                   amount_eur=exercised.redemption_eur, is_coupon=False)
        cashflows.append((redemption, f"{exercised.exercise_id}:settlement"))

    rows, future, projected = [], [], {}
    receivables = []
    for flow, event_id in cashflows:
        day = events[event_id].date
        fixed, fixing_ids = _coupon_fixings(flow, valuation_date, events, evidence)
        if confirmation := evidence.get(event_id):
            rows.append(ResidualFlow(flow_id=flow.flow_id, payment_event_id=event_id, payment_date=day, state="paid",
                                     amount_eur=confirmation.fact.amount_eur, pv_eur=0, fixing_fact_ids=fixing_ids,
                                     payment_fact_id=confirmation.id))
            continue
        acquired = day <= valuation_date or (
            isinstance(fixed, RateCoupon) and fixed.realized_rate is not None
            or isinstance(fixed, RangeAccrualCoupon) and all(item.realized_rate is not None for item in fixed.observations)
        )
        if acquired:
            amount = _amount(terms, fixed, market)
            remaining = max(0, (day - valuation_date).days) / 365
            pv = amount * exp(market.discount.log_factor(remaining) - market.funding_bps * 1e-4 * remaining)
            state = "receivable" if remaining else "due" if day == valuation_date else "overdue"
            receivables.append(pv)
            rows.append(ResidualFlow(flow_id=flow.flow_id, payment_event_id=event_id, payment_date=day, state=state,
                                     amount_eur=amount, pv_eur=pv, fixing_fact_ids=fixing_ids))
            continue
        future.append(_remaining_flow(fixed, elapsed))
        projected[flow.flow_id] = (event_id, day, fixing_ids)

    claim_pv = fsum(receivables)
    residual, bounds = 0.0, (claim_pv, claim_pv)
    if future:
        rights = tuple(right.model_copy(update={"decision": right.decision - elapsed, "settlement": right.settlement - elapsed})
                       for right in future_rights)
        remaining_terms = ExoticRatesTerms(nominal_eur=terms.nominal_eur, side=terms.side,
                                           cashflows=tuple(future), exercises=rights)
        remaining_settings = settings if rights else settings.model_copy(update={"training_paths": None})
        priced = price_exotic_rates(remaining_terms, market, remaining_settings).result
        residual = priced.pv_eur
        bounds = tuple(point + claim_pv for point in priced.ci95_eur)
        for leg in priced.flows:
            event_id, day, fixing_ids = projected.get(leg.flow_id, (f"{leg.flow_id}:settlement", None, ()))
            rows.append(ResidualFlow(flow_id=leg.flow_id, payment_event_id=event_id,
                                     payment_date=day or events[event_id].date, state="projected",
                                     amount_eur=leg.mean_amount_eur, pv_eur=leg.pv_eur, fixing_fact_ids=fixing_ids))
    state = "alive" if future else "settlement_pending" if any(row.state != "paid" for row in rows) else "settled"
    return ExoticResidual(state, fsum((residual, claim_pv)), residual, claim_pv, bounds,
                          tuple(sorted(rows, key=lambda row: (row.payment_date, row.flow_id))))
