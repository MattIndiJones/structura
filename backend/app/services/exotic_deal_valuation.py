"""Frozen MtM and P&L records for booked native EUR exotics."""

from datetime import date, datetime, timezone
from functools import cache
from hashlib import sha256
import json
from math import fsum
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator
from sqlmodel import select

from ..core.audit import record_audit_event
from ..core.product.exotic_valuation_explain import (
    ExplainCash, ExplainIdentity, ExplainMarket, ExplainPrice, ExplainScenario, ExplainSnapshot, ValuationExplain,
    explain_valuations,
)
from ..core.product.models import FrozenModel, FrozenObject, Product
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.models import ValuationRun
from ..runtime import business_now
from .exotic_cln_lifecycle import price_booked_cln
from .exotic_deal_result import ResidualFlow
from .exotic_product import read_exotic_calculation
from .exotic_product_lifecycle import CreditSettlement, FactRow, load_exotic_deal_scope, read_exotic_ledger
from .exotic_rates_residual import price_exotic_rates_residual, roll_rates_market
from .exotic_valuation import ExoticRatesScenario, exotic_engine_fingerprint, read_scenario
from .native_write_policy import native_writes_enabled
from .product_repository import ProductError, lock_command_actor


RUN_TYPE = "EXOTIC_MTM"
ENGINE = "native-exotic-deal-mtm-v1"
MARKET_MODE = "frozen_booking_roll"
_PARIS = ZoneInfo("Europe/Paris")


class ExoticDealMtmRequest(FrozenModel):
    cutoff: AwareDatetime | None = None
    market_mode: Literal["frozen_booking_roll"]

    @field_validator("cutoff")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None


class ExoticDealExplainRequest(FrozenModel):
    start_run_id: int = Field(gt=0)
    end_run_id: int = Field(gt=0)


class _FrozenMtm(FrozenModel):
    deal_id: int
    contract_version: int
    product: Product
    booking_calculation_id: int
    booking_receipt_fingerprint: str
    engine_fingerprint: str
    booking_scenario: FrozenObject
    cutoff: AwareDatetime
    facts: tuple[FactRow, ...]


class _MtmResult(FrozenModel):
    valuation_date: date
    state: Literal["alive", "recovery_pending", "settlement_pending", "settled"]
    economic_dirty_pv_eur: float | None
    residual_pv_eur: float | None
    receivables_pv_eur: float
    cash_confirmed_eur: float
    ci95_eur: tuple[float, float] | None
    flows: tuple[ResidualFlow, ...]


class ExoticDealMtm(FrozenModel):
    valuation_run_id: int
    deal_id: int
    contract_version: int
    cutoff: AwareDatetime
    market_mode: Literal["frozen_booking_roll"] = MARKET_MODE
    market_source_id: str
    market_source_version: int
    market_origin: date
    context_fingerprint: str
    replay_compatible: bool
    result: _MtmResult


class ExoticDealReplay(FrozenModel):
    matched: Literal[True] = True
    valuation: ExoticDealMtm


@cache
def engine_fingerprint():
    files = ("exotic_deal_valuation.py", "exotic_rates_residual.py", "exotic_cln_lifecycle.py",
             "exotic_deal_result.py", "exotic_product_lifecycle.py")
    return json_transport_fingerprint({
        "core": exotic_engine_fingerprint(),
        "services": {name: sha256(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                     for name in files},
    })


def _calculation(inputs: _FrozenMtm) -> tuple[_MtmResult, int]:
    scenario = read_scenario(inputs.booking_scenario.to_dict())
    valuation_date = inputs.cutoff.astimezone(_PARIS).date()
    product = inputs.product
    if isinstance(scenario, ExoticRatesScenario):
        events = tuple(event for leg in product.native_schedule.legs for event in leg.events)
        latest = max(event.date for event in events)
        elapsed = (valuation_date - scenario.valuation_date).days / 365
        needs_projection = any(event.kind == "observation" and event.date > valuation_date for event in events)
        market = (roll_rates_market(scenario.market, elapsed, needs_projection=needs_projection)
                  if valuation_date < latest else scenario.market)
        result = price_exotic_rates_residual(
            product, valuation_date=valuation_date, market=market, settings=scenario.settings, facts=inputs.facts,
        )
        paths = scenario.settings.paths
    else:
        result = price_booked_cln(product, valuation_date=valuation_date, request=scenario.credit, facts=inputs.facts)
        paths = scenario.credit.settings.paths
    return _MtmResult(
        valuation_date=valuation_date, state=result.state, economic_dirty_pv_eur=result.dirty_pv_eur,
        residual_pv_eur=result.residual_pv_eur, receivables_pv_eur=result.receivables_pv_eur,
        cash_confirmed_eur=fsum(flow.amount_eur for flow in result.flows if flow.state == "paid"),
        ci95_eur=result.ci95_eur, flows=result.flows,
    ), paths if result.state == "alive" else 0


def _present(run, inputs, result) -> ExoticDealMtm:
    scenario = read_scenario(inputs.booking_scenario.to_dict())
    return ExoticDealMtm(
        valuation_run_id=run.id, deal_id=run.deal_id, contract_version=run.contract_version, cutoff=inputs.cutoff,
        market_source_id=scenario.market_source.source_id, market_source_version=scenario.market_source.version,
        market_origin=scenario.valuation_date, context_fingerprint=run.context_hash,
        replay_compatible=run.engine_fingerprint == engine_fingerprint(), result=result,
    )


def _read(run):
    try:
        data = json.loads(run.context_json)
        result_data = json.loads(run.result_json)
        proof = json.loads(run.diagnostics_json)
        inputs = _FrozenMtm.model_validate(data)
        result = _MtmResult.model_validate(result_data)
        if (json_transport_fingerprint(data) != run.context_hash
                or json_transport_fingerprint(result_data) != proof["result_fingerprint"]
                or (inputs.deal_id, inputs.contract_version, inputs.engine_fingerprint)
                != (run.deal_id, run.contract_version, run.engine_fingerprint)):
            raise ValueError("archive fingerprints")
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductError("EXOTIC_MTM_ARCHIVE_INVALID", "L’archive de MtM exotique est incohérente.") from exc
    return inputs, result


def stage_exotic_mtm(session, deal_id, user, body: ExoticDealMtmRequest, *, secret: str) -> ExoticDealMtm:
    load_exotic_deal_scope(session, deal_id, user)
    if not native_writes_enabled(user, session):
        raise ProductError("EXOTIC_MTM_RECIPE_ONLY", "Le calcul conservé exige un compte habilité de recette.", 403)
    lock_command_actor(session, user)
    deal, product, schedule = load_exotic_deal_scope(session, deal_id, user)
    saved = json.loads(deal.market_snapshot_json)
    archive = read_exotic_calculation(session, product.product_id, saved["calculation_id"], user, secret=secret)
    receipt = archive.receipt
    if (json_transport_fingerprint(receipt) != saved["receipt_fingerprint"]
            or product.terms_fingerprint != saved["terms_fingerprint"]
            or receipt["engine_fingerprint"] != exotic_engine_fingerprint()):
        raise ProductError("EXOTIC_MTM_BOOKING_PROOF", "Le pricing de booking ou son moteur d’origine est indisponible.")
    scenario = read_scenario(receipt["request"])
    clock = business_now()
    now = clock.astimezone(timezone.utc) if clock.tzinfo else clock.replace(tzinfo=timezone.utc)
    cutoff = body.cutoff if body.cutoff is not None else now
    if not scenario.cutoff <= cutoff <= now:
        raise ProductError("EXOTIC_MTM_CUTOFF", "L’arrêté doit être compris entre celui du booking et l’horloge de recette.", 422)
    ledger = read_exotic_ledger(session, deal_id, user, cutoff=cutoff)
    inputs = _FrozenMtm(
        deal_id=deal.id, contract_version=deal.contract_version, booking_calculation_id=archive.calculation_id,
        booking_receipt_fingerprint=saved["receipt_fingerprint"], engine_fingerprint=engine_fingerprint(),
        product=Product(product_id=product.product_id, terms_version=product.terms_version, terms=product.terms,
                        native_schedule=schedule, intent={"nominal": product.intent.nominal, "side": product.intent.side}),
        booking_scenario=FrozenObject(receipt["request"]), cutoff=cutoff, facts=ledger.eligible,
    )
    data = inputs.model_dump(mode="json")
    digest = json_transport_fingerprint(data)
    existing = session.exec(select(ValuationRun).where(
        ValuationRun.deal_id == deal.id, ValuationRun.run_type == RUN_TYPE, ValuationRun.context_hash == digest,
    )).first()
    if existing is not None:
        return _present(existing, *_read(existing))
    result, paths = _calculation(inputs)
    result_data = result.model_dump(mode="json")
    result_digest = json_transport_fingerprint(result_data)
    run = ValuationRun(
        deal_id=deal.id, user_id=user.id, run_type=RUN_TYPE, contract_version=deal.contract_version,
        engine_version=ENGINE, engine_fingerprint=inputs.engine_fingerprint, n_paths=paths,
        context_json=canonical_json(data), context_hash=digest, result_json=canonical_json(result_data),
        market_data_json=canonical_json({"mode": MARKET_MODE, "booking_source": scenario.market_source.model_dump(mode="json")}),
        data_versions_json=canonical_json({"fact_ids": [fact.id for fact in inputs.facts]}),
        diagnostics_json=canonical_json({"result_fingerprint": result_digest}),
    )
    session.add(run)
    session.flush()
    record_audit_event(session, action="EXOTIC_DEAL_MTM_ARCHIVED", object_type="DEAL", object_id=deal.id,
                       actor_user_id=user.id, result="SUCCESS",
                       after={"run_id": run.id, "context_fingerprint": digest, "result_fingerprint": result_digest})
    return _present(run, inputs, result)


def exotic_mtm_history(session, deal_id, user) -> tuple[ExoticDealMtm, ...]:
    load_exotic_deal_scope(session, deal_id, user)
    rows = session.exec(select(ValuationRun).where(ValuationRun.deal_id == deal_id, ValuationRun.run_type == RUN_TYPE)
                        .order_by(ValuationRun.id.desc()).limit(50)).all()
    return tuple(_present(row, *_read(row)) for row in rows)


def _run(session, deal_id, run_id):
    row = session.get(ValuationRun, run_id)
    if row is None or (row.deal_id, row.run_type) != (deal_id, RUN_TYPE):
        raise ProductError("EXOTIC_MTM_NOT_FOUND", "Valorisation exotique introuvable.", 404)
    return row


def _replay(inputs, archived):
    if inputs.engine_fingerprint != engine_fingerprint():
        raise ProductError("EXOTIC_MTM_ENGINE", "Le moteur de la valorisation archivée est indisponible.")
    result, _ = _calculation(inputs)
    if result != archived:
        raise ProductError("EXOTIC_MTM_REPLAY", "Le résultat rejoué diffère du résultat conservé.")
    return result


def replay_exotic_mtm(session, deal_id, run_id, user) -> ExoticDealReplay:
    load_exotic_deal_scope(session, deal_id, user)
    row = _run(session, deal_id, run_id)
    inputs, result = _read(row)
    return ExoticDealReplay(valuation=_present(row, inputs, _replay(inputs, result)))


def _snapshot(row, inputs, result) -> ExplainSnapshot:
    product = inputs.product
    identity = ExplainIdentity(
        position_id=f"deal:{inputs.deal_id}:v{inputs.contract_version}", terms_version=product.terms_version,
        terms_fingerprint=product.terms_fingerprint, schedule_fingerprint=product.native_schedule.fingerprint,
        nominal_eur=product.intent.nominal, side=product.intent.side, value_date_convention="valuation_date_act365f",
        model=product.terms.instrument_type, engine_version=row.engine_version, engine_fingerprint=row.engine_fingerprint,
    )
    evidence = {fact.id: fact for fact in inputs.facts}
    payments = []
    for flow in result.flows:
        if flow.state != "paid":
            continue
        fact = evidence[flow.payment_fact_id]
        credit = isinstance(fact.fact, CreditSettlement)
        payments.append(ExplainCash(
            flow_id=flow.flow_id, fact_id=str(fact.id), version=1, amount_eur=flow.amount_eur,
            effect_date=fact.fact.effect_date if credit else fact.observed_at.astimezone(_PARIS).date(),
            paid_at=None if credit else fact.observed_at, available_at=fact.available_at, validated_at=fact.validated_at,
        ))
    return ExplainSnapshot(
        archive_id=row.id, identity=identity,
        scenario=ExplainScenario(cutoff=inputs.cutoff, value_date=result.valuation_date, market=ExplainMarket(),
                                 state=FrozenObject({"facts": [fact.id for fact in inputs.facts]}), cash=tuple(payments)),
        price=ExplainPrice(economic_dirty_pv_eur=result.economic_dirty_pv_eur,
                           state="recovery_pending" if result.state == "recovery_pending" else "available"),
    )


def explain_exotic_mtm(session, deal_id, user, body: ExoticDealExplainRequest) -> ValuationExplain:
    load_exotic_deal_scope(session, deal_id, user)
    start_row, end_row = (_run(session, deal_id, run_id) for run_id in (body.start_run_id, body.end_run_id))
    start_inputs, start_result = _read(start_row)
    end_inputs, end_result = _read(end_row)
    if start_inputs.cutoff == end_inputs.cutoff:
        raise ProductError("EXOTIC_MTM_EXPLAIN_CUTOFF", "Sélectionnez deux arrêtés distincts.", 422)
    start, end = _snapshot(start_row, start_inputs, start_result), _snapshot(end_row, end_inputs, end_result)
    by_cutoff = {start_inputs.cutoff: (start_row, start_inputs, start_result),
                 end_inputs.cutoff: (end_row, end_inputs, end_result)}

    def price(scenario):
        row, inputs, result = by_cutoff[scenario.cutoff]
        return _snapshot(row, inputs, _replay(inputs, result)).price

    return explain_valuations(start, end, price=price, roll_market=lambda first, _: first.market,
                              roll_convention=MARKET_MODE, current_engine_fingerprint=engine_fingerprint())
