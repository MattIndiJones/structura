"""Replay a bounded tape of verified, point-in-time exotic price receipts."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from math import fsum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field

from ..core.product.exotic_rates_mc import RangeAccrualCoupon, RateCoupon
from ..core.product.exotic_valuation_explain import ExplainCash, credit_default_explain_observation
from ..core.product.models import FrozenModel, FrozenObject
from ..core.valuation_context import json_transport_fingerprint
from .exotic_valuation import (
    ExoticCreditScenario, ExoticMarketSource, ExoticRatesScenario, ExoticScenario, ExoticValuationError, Reference,
    exotic_engine_fingerprint, price_exotic_scenario, read_scenario, result_payload,
)


MAX_BACKTEST_POINTS = 16
MAX_BACKTEST_PATHS = 1_000_000
_PARIS = ZoneInfo("Europe/Paris")
_CREDIT_STATE = {"alive": 0, "recovery_pending": 1, "settlement_pending": 2, "settled": 3}


class ExoticBacktestRequest(FrozenModel):
    tape_id: Reference
    receipts: tuple[FrozenObject, ...] = Field(min_length=2, max_length=MAX_BACKTEST_POINTS)


class ExoticReplayPayment(FrozenModel):
    confirmation: ExplainCash
    recognized_at: AwareDatetime
    first_supplied_at: AwareDatetime
    within_tape: bool


class ExoticReplayPoint(FrozenModel):
    valuation_date: date
    cutoff: AwareDatetime
    request_fingerprint: str
    result_fingerprint: str
    market_source: ExoticMarketSource
    state: Literal["alive", "recovery_pending", "settlement_pending", "settled"]
    dirty_pv_eur: float | None
    clean_pv_eur: float | None
    pv_interval_95_eur: tuple[float, float] | None
    pricing_independent_samples: int = Field(ge=0)
    available_fixings: int = Field(ge=0)
    payments_newly_supplied: tuple[ExoticReplayPayment, ...] = ()


class ExoticBacktestResult(FrozenModel):
    schema_version: Literal[1] = 1
    method: Literal["signed_point_in_time_replay"] = "signed_point_in_time_replay"
    coverage: Literal["supplied_cutoffs_only"] = "supplied_cutoffs_only"
    market_quality: Literal["synthetic"] = "synthetic"
    currency: Literal["EUR"] = "EUR"
    cash_coverage: Literal["confirmed_facts_only"] = "confirmed_facts_only"
    performance_status: Literal["historical_trade_and_cash_coverage_unavailable"] = "historical_trade_and_cash_coverage_unavailable"
    family: Literal["rates", "credit"]
    tape_id: Reference
    tape_fingerprint: str
    engine_fingerprint: str
    position_id: Reference
    terms_version: int
    point_count: int
    confirmed_cash_within_tape_eur: float | None
    points: tuple[ExoticReplayPoint, ...]


@dataclass(frozen=True)
class _Flow:
    payment_axis: float
    structure: str


@dataclass(frozen=True)
class _Contract:
    identity: tuple
    flows: dict[str, _Flow]
    exercises: dict[str, tuple[float, str]]
    fixings: dict[tuple[str, int], float]
    protection_start: float | None = None


def _error(code: str, text: str, *, status: int = 422):
    raise ExoticValuationError("EXOTIC_BACKTEST_" + code, text, status)


def _absolute(origin: date, years: float) -> float:
    # Identity only. The supplied ACT/365F times are never modified for replay.
    return round(origin.toordinal() + years * 365.0, 8)


def _move_times(payload: dict, origin: date, fields: tuple[str, ...]) -> dict:
    return {**payload, **{name: _absolute(origin, payload[name]) for name in fields}}


def _absolute_rate_index(index: dict, origin: date) -> dict:
    if index["kind"] == "forward":
        return _move_times(index, origin, ("start", "end"))
    return {
        **index,
        "fixed_periods": [_move_times(period, origin, ("payment",)) for period in index["fixed_periods"]],
        "floating_periods": [_move_times(period, origin, ("start", "end")) for period in index["floating_periods"]],
    }


def _rates_contract(scenario: ExoticRatesScenario) -> _Contract:
    terms, origin = scenario.terms, scenario.valuation_date
    dates = terms.contract_dates
    accrual = {} if dates is None else {period.flow_id: period for period in dates.accrual_periods}
    flows, fixings = {}, {}
    for flow in terms.cashflows:
        payload = _move_times(flow.model_dump(mode="json"), origin, ("payment",))
        if isinstance(flow, RateCoupon):
            payload = _move_times(payload, origin, ("fixing",))
            acquired = payload.pop("realized_rate")
            if acquired is not None:
                fixings[flow.flow_id, 0] = acquired
            payload["index"] = _absolute_rate_index(payload["index"], origin)
            if payload["spread_index"] is not None:
                payload["spread_index"] = _absolute_rate_index(payload["spread_index"], origin)
        elif isinstance(flow, RangeAccrualCoupon):
            resolved = []
            for rank, observation in enumerate(payload["observations"], 1):
                item = _move_times(observation, origin, ("time",))
                acquired = item.pop("realized_rate")
                if acquired is not None:
                    fixings[flow.flow_id, rank] = acquired
                item["index"] = _absolute_rate_index(item["index"], origin)
                resolved.append(item)
            payload["observations"] = resolved
        if period := accrual.get(flow.flow_id):
            payload["accrual_period"] = period.model_dump(mode="json")
        flows[flow.flow_id] = _Flow(payload["payment"], json_transport_fingerprint(payload))
    exercises = {}
    for right in terms.exercises:
        absolute = _move_times(right.model_dump(mode="json"), origin, ("decision", "settlement"))
        exercises[right.exercise_id] = (absolute["decision"], json_transport_fingerprint(absolute))
    last_payment = max(flow.payment_axis for flow in flows.values())
    identity = (terms.nominal_eur, terms.side, last_payment)
    if dates is not None:
        identity += (dates.start_date, dates.end_date)
    return _Contract(identity, flows, exercises, fixings)


def _credit_contract(scenario: ExoticCreditScenario) -> _Contract:
    request, origin = scenario.credit, scenario.valuation_date
    terms = request.contract
    flows = {}
    for period in terms.coupons:
        payload = _move_times(period.model_dump(mode="json", exclude={"observation"}), origin, ("start", "end", "payment"))
        payload["observation"] = _absolute(origin, period.survival_time)
        flows[str(payload["end"])] = _Flow(payload["payment"], json_transport_fingerprint(payload))
    identity = (terms.kind, terms.nominal_eur, terms.side, terms.coupon_bps, terms.trigger_rank, terms.tie_break,
                _absolute(origin, terms.maturity_years), _absolute(origin, terms.principal_payment_years or terms.maturity_years),
                terms.default_settlement_delay_years,
                tuple(sorted(name.reference_entity_id for name in request.market.marginals)))
    return _Contract(identity, flows, {}, {}, _absolute(origin, terms.protected_from) if terms.protected_from else None)


def _check_contracts(scenarios: Sequence[ExoticScenario]) -> tuple[_Contract, ...]:
    first = scenarios[0]
    identity = first.family, first.position_id, first.terms_version, first.value_date_convention
    previous_cutoff = None
    initial, prior = None, None
    details = []
    for scenario in scenarios:
        if previous_cutoff is not None and scenario.cutoff <= previous_cutoff:
            _error("CUTOFF_ORDER", "Les arrêtés du tape doivent être strictement croissants et distincts.")
        previous_cutoff = scenario.cutoff
        if (scenario.family, scenario.position_id, scenario.terms_version, scenario.value_date_convention) != identity:
            _error("POSITION_MISMATCH", "Le tape doit garder une famille, une position et une version de termes uniques.")
        if isinstance(scenario, ExoticCreditScenario) and scenario.credit.contract.kind == "basket_cds" and (
                scenario.valuation_date != first.valuation_date):
            _error("BASKET_STATE_REQUIRED", "Le panier multi-date exige des états de défaut et une survie conditionnelle qualifiée.")
        detail = _rates_contract(scenario) if isinstance(scenario, ExoticRatesScenario) else _credit_contract(scenario)
        details.append(detail)
        if initial is None:
            initial = prior = detail
            continue
        if detail.identity != initial.identity:
            _error("TERMS_MISMATCH", "L’échéance absolue ou les termes économiques de la position ont changé.")
        start = initial.protection_start
        expected_start = start if start is not None and start > scenario.valuation_date.toordinal() else None
        if detail.protection_start != expected_start:
            _error("TERMS_MISMATCH", "La date absolue de prise d’effet de la protection a changé.")
        if any(decision <= scenario.valuation_date.toordinal() for decision, _ in initial.exercises.values()):
            _error("EXERCISE_STATE_REQUIRED", "Le tape franchit une date d’exercice qui exige une décision historique confirmée.")
        if detail.exercises != initial.exercises:
            _error("TERMS_MISMATCH", "Les décisions d’exercice doivent conserver leurs dates et termes absolus.")
        if any(key not in prior.flows or prior.flows[key] != flow for key, flow in detail.flows.items()):
            _error("TERMS_MISMATCH", "Un flux ou ses dates absolues changent entre deux arrêtés du tape.")
        if any(key not in detail.flows and flow.payment_axis >= scenario.valuation_date.toordinal()
               for key, flow in prior.flows.items()):
            _error("TERM_REMOVED", "Un flux non échu disparaît sans fait contractuel validé.")
        for key, value in prior.fixings.items():
            if key[0] in detail.flows and detail.fixings.get(key) != value:
                _error("FIXING_CHANGED", "Un fixing acquis a été modifié ou supprimé sans version de correction.")
        prior = detail
    return tuple(details)


def _paths_used(scenario: ExoticScenario) -> int:
    if isinstance(scenario, ExoticRatesScenario):
        return scenario.settings.paths + (scenario.settings.training_paths or 0)
    return 0 if scenario.credit.realized else scenario.credit.settings.paths


def _evidence(scenario: ExoticScenario, calculation):
    result = calculation.result
    if isinstance(scenario, ExoticRatesScenario):
        return "alive", result.pv_eur, None, result.ci95_eur, result.independent_paths, ()
    if result.realized is not None:
        observation, cash = credit_default_explain_observation(result.realized, scenario.credit.realized.context)
        return result.state, observation.economic_dirty_pv_eur, observation.clean_pv_eur, None, 0, cash
    dirty = result.estimate.dirty_pv_eur
    return (result.state, dirty.mean, result.estimate.clean_pv_eur.mean,
            (dirty.mean - dirty.ci95_half_width, dirty.mean + dirty.ci95_half_width),
            result.provenance.independent_samples, ())


def _realized_identity(scenario: ExoticScenario) -> tuple | None:
    if not isinstance(scenario, ExoticCreditScenario) or scenario.credit.realized is None:
        return None
    realized = scenario.credit.realized
    default = realized.context.facts.default
    if default is None:
        _error("DEFAULT_STATE", "L’état de défaut du tape ne contient pas de fait validé.")
    return (realized.product.product_id, realized.product.terms_fingerprint, realized.context.schedule_fingerprint,
            default.default_id, default.effect_date)


def _new_payments(evidence: tuple[ExplainCash, ...], recorded: dict[str, ExplainCash],
                  cutoff: datetime, first_cutoff: datetime) -> tuple[ExoticReplayPayment, ...]:
    current = {fact.flow_id: fact for fact in evidence}
    if len(current) != len(evidence) or not recorded.keys() <= current.keys():
        _error("CASH_EVIDENCE", "La preuve d’un flux payé est dupliquée ou disparaît au fil du tape.")
    payments = []
    for key, fact in current.items():
        recognized = fact.recognized_at(_PARIS)
        if recognized > cutoff:
            _error("CASH_CUTOFF", "Un flux payé est indisponible à l’arrêté du snapshot.")
        previous = recorded.get(key)
        if previous is not None:
            if (previous.fact_id, previous.effect_date, previous.amount_eur) != (fact.fact_id, fact.effect_date, fact.amount_eur) or fact.version < previous.version:
                _error("CASH_REVISION", "Le cash confirmé a changé. Un ajustement exige un flux distinct.")
        else:
            payments.append(ExoticReplayPayment(confirmation=fact, recognized_at=recognized,
                                                 first_supplied_at=cutoff, within_tape=recognized > first_cutoff))
        recorded[key] = fact
    return tuple(sorted(payments, key=lambda row: (row.recognized_at, row.confirmation.flow_id)))


def backtest_exotic_claims(tape_id: str, claims: Sequence[dict]) -> ExoticBacktestResult:
    """Replay claims authenticated by the API boundary, with no market carry or I/O."""
    if not 2 <= len(claims) <= MAX_BACKTEST_POINTS:
        _error("SIZE", f"Le tape doit contenir de 2 à {MAX_BACKTEST_POINTS} arrêtés.")
    engine = exotic_engine_fingerprint()
    if any(row["engine_fingerprint"] != engine for row in claims):
        _error("ENGINE_UNAVAILABLE", "Au moins un reçu porte une version de moteur indisponible.", status=409)
    scenarios = tuple(read_scenario(row["request"]) for row in claims)
    if sum(_paths_used(scenario) for scenario in scenarios) > MAX_BACKTEST_PATHS:
        _error("WORK_LIMIT", "Le tape dépasse le budget cumulé d’un million de trajectoires.")
    contracts = _check_contracts(scenarios)
    first = scenarios[0]
    points, payments = [], {}
    realized_identity, previous_state = None, "alive"
    for scenario, row, contract in zip(scenarios, claims, contracts, strict=True):
        calculation = price_exotic_scenario(scenario)
        digest = json_transport_fingerprint(result_payload(calculation))
        if digest != row["result_fingerprint"]:
            _error("REPLAY_MISMATCH", "Le résultat reproduit diffère du reçu de l’arrêté.", status=409)
        state, dirty, clean, interval, units, cash = _evidence(scenario, calculation)
        resolved = _realized_identity(scenario)
        if (realized_identity is not None and resolved != realized_identity) or _CREDIT_STATE[state] < _CREDIT_STATE[previous_state]:
            _error("DEFAULT_STATE", "Le fait de défaut ou l’état acquis est incohérent avec les arrêtés précédents.")
        realized_identity, previous_state = resolved, state
        new = _new_payments(cash, payments, scenario.cutoff, first.cutoff)
        points.append(ExoticReplayPoint(
            valuation_date=scenario.valuation_date, cutoff=scenario.cutoff, market_source=scenario.market_source,
            request_fingerprint=json_transport_fingerprint(row["request"]), result_fingerprint=digest, state=state,
            dirty_pv_eur=dirty, clean_pv_eur=clean, pv_interval_95_eur=interval, pricing_independent_samples=units,
            available_fixings=len(contract.fixings), payments_newly_supplied=new,
        ))
    dated_cash = [row.confirmation.amount_eur for point in points for row in point.payments_newly_supplied if row.within_tape]
    fingerprint = json_transport_fingerprint({
        "tape_id": tape_id, "engine_fingerprint": engine,
        "receipts": [(point.request_fingerprint, point.result_fingerprint) for point in points],
    })
    return ExoticBacktestResult(
        family=first.family, tape_id=tape_id, tape_fingerprint=fingerprint, engine_fingerprint=engine,
        position_id=first.position_id, terms_version=first.terms_version, point_count=len(points),
        confirmed_cash_within_tape_eur=fsum(dated_cash) if dated_cash else None, points=tuple(points),
    )
