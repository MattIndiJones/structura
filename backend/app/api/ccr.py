"""Authenticated CCR configuration, saved analyses and pre-trade checks."""
from typing import Annotated, Literal
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, Counterparty, CCRExposureCalculation, Deal, Portfolio, RfqRequest, RfqQuote, RfqProvider, UatGenerationBatch
from ..core.ccr.contracts import CalculationRequest
from ..core.ccr.service import (records, save_record, calculate, organization, evaluate_inputs, legal_assignment, scope_diagnostic)
from ..core.audit import record_audit_event

router = APIRouter(prefix="/api/ccr", tags=["CCR"])
Current = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_session)]


@router.get("/schemas")
def schemas(current: Current):
    from ..core.ccr.contracts import SCHEMAS
    return {kind: schema.model_json_schema() for kind, schema in SCHEMAS.items()}


class ConfigurationWrite(BaseModel):
    data: dict
    expected_version: int | None = None


@router.get("/counterparties")
def counterparties(current: Current, session: Database):
    organization(current)
    return [{"id": c.id, "name": c.name, "country": c.country, "active": c.active,
             "legacy_nominal_limit_eur": c.limit_eur} for c in session.exec(select(Counterparty).order_by(Counterparty.name)).all()]


@router.get("/counterparties/{cpty_id}/configuration")
def configuration(cpty_id: int, current: Current, session: Database):
    return records(session, current, cpty_id)


@router.post("/counterparties/{cpty_id}/{kind}")
def create_configuration(cpty_id: int, kind: str, body: ConfigurationWrite, current: Current, session: Database):
    try:
        return save_record(session, current, cpty_id, kind, body.data)
    except ValidationError as exc:
        raise HTTPException(422, str(exc))


@router.put("/counterparties/{cpty_id}/{kind}/{row_id}")
def update_configuration(cpty_id: int, kind: str, row_id: int, body: ConfigurationWrite, current: Current, session: Database):
    try:
        return save_record(session, current, cpty_id, kind, body.data, row_id, body.expected_version)
    except ValidationError as exc:
        raise HTTPException(422, str(exc))


@router.get("/deals")
def deals(current: Current, session: Database, data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION",
          uat_batch_id: int | None = None):
    if uat_batch_id is not None and data_scope != "UAT":
        raise HTTPException(422, "Un lot UAT nécessite le périmètre Recette UAT")
    query = select(Deal).where(Deal.entity_id == organization(current), Deal.status.in_(["actif", "en_reglement"]))
    query = query.where(Deal.uat_batch_id != None if data_scope == "UAT" else Deal.uat_batch_id == None)
    if uat_batch_id is not None:
        query = query.where(Deal.uat_batch_id == uat_batch_id)
    return [{"id": d.id, "reference": d.reference, "counterparty_id": d.counterparty_id,
             "uat_batch_id": d.uat_batch_id,
             "netting_set_id": d.ccr_netting_set_id, "product_type": d.product_type,
             "currency": d.devise, "nominal": d.nominal} for d in session.exec(query).all()]


@router.get("/uat-batches")
def uat_batches(current: Current, session: Database):
    rows = session.exec(select(UatGenerationBatch).join(Deal, Deal.uat_batch_id == UatGenerationBatch.id)
                        .where(Deal.entity_id == organization(current)).distinct()).all()
    return [{"id": r.id, "label": r.label or r.batch_key} for r in rows]


@router.post("/diagnostic")
def diagnostic(body: CalculationRequest, current: Current, session: Database):
    return scope_diagnostic(session, current, body)


@router.get("/portfolios")
def portfolios(current: Current, session: Database):
    rows = session.exec(select(Portfolio).join(User, Portfolio.user_id == User.id).where(
        User.entity_id == organization(current))).all()
    return [{"id": row.id, "name": row.name} for row in rows]


class Assignment(BaseModel):
    netting_set_id: int | None = None
    reason: str


@router.put("/deals/{deal_id}/assignment")
def assign_deal(deal_id: int, body: Assignment, current: Current, session: Database):
    if current.role != "admin":
        raise HTTPException(403, "Rattachement juridique réservé aux administrateurs")
    deal = session.get(Deal, deal_id)
    if not deal or deal.entity_id != organization(current):
        raise HTTPException(404, "Deal introuvable")
    if not body.reason.strip():
        raise HTTPException(422, "Motif de rattachement requis")
    legal_assignment(session, current, deal.counterparty_id, body.netting_set_id, deal.devise, deal.product_type)
    old = deal.ccr_netting_set_id
    deal.ccr_netting_set_id = body.netting_set_id
    session.add(deal)
    record_audit_event(session, action="CCR_LEGAL_ASSIGNMENT", object_type="DEAL", object_id=deal.id,
                      actor_user_id=current.id, result="SUCCESS", before={"netting_set_id": old},
                      after={"netting_set_id": body.netting_set_id}, reason=body.reason)
    session.commit()
    return {"deal_id": deal.id, "netting_set_id": deal.ccr_netting_set_id}


@router.post("/calculate")
def run_calculation(body: CalculationRequest, current: Current, session: Database, stream: bool = False):
    if stream:
        from .valuation_progress import valuation_progress_response
        bind, user_id = session.get_bind(), current.id
        def compute(progress):
            with Session(bind) as worker:
                user = worker.get(User, user_id)
                if user is None:
                    raise HTTPException(401, "Utilisateur introuvable")
                try:
                    return calculate(worker, user, body, progress=progress)
                except ValueError as exc:
                    raise HTTPException(422, str(exc))
        return valuation_progress_response(compute, error_message="Calcul CCR interrompu. Consulter le diagnostic et les journaux serveur.")
    try:
        return calculate(session, current, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/runs/{run_id}")
def get_run(run_id: int, current: Current, session: Database):
    row = session.get(CCRExposureCalculation, run_id)
    if not row or row.entity_id != organization(current):
        raise HTTPException(404, "Calcul introuvable")
    return {"id": row.id, "input_hash": row.input_hash, "calculation_timestamp": row.calculation_timestamp.isoformat(),
            "inputs": json.loads(row.inputs_json), "result": json.loads(row.results_json)}


@router.post("/runs/{run_id}/replay")
def replay(run_id: int, current: Current, session: Database):
    archive = get_run(run_id, current, session)
    result = evaluate_inputs(archive["inputs"])
    return {"run_id": run_id, "result": result, "identical": result == archive["result"]}


@router.get("/monitor")
def monitor(current: Current, session: Database, data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION"):
    rows = []
    for cpty in session.exec(select(Counterparty).order_by(Counterparty.name)).all():
        runs = session.exec(select(CCRExposureCalculation).where(
            CCRExposureCalculation.entity_id == organization(current), CCRExposureCalculation.counterparty_id == cpty.id)
            .order_by(CCRExposureCalculation.id.desc())).all()
        def matches(run):
            request = json.loads(run.inputs_json)["request"]
            return request.get("data_scope", "PRODUCTION") == data_scope and not any(request.get(k)
                for k in ("proposed", "deal_id", "portfolio_id", "netting_set_id", "uat_batch_id"))
        row = next((r for r in runs if matches(r)), None)
        from datetime import date
        stale = row is None or row.as_of_date != date.today().isoformat()
        if row:
            saved = json.loads(row.inputs_json)
            stale = stale or saved["configuration"] != records(session, current, cpty.id)
            from ..core.ccr.service import portfolio_deals
            scope = portfolio_deals(session, current, CalculationRequest(counterparty_id=cpty.id, data_scope=data_scope))
            now_scope = {(d.id, d.contract_version, d.ccr_netting_set_id) for d in scope}
            old_scope = {(t["deal_id"], t.get("contract_version"), t.get("netting_set_id")) for t in saved["trades"]}
            stale = stale or now_scope != old_scope or not saved["trades"]
        rows.append({"counterparty_id": cpty.id, "name": cpty.name, "data_scope": data_scope, "stale": stale, "as_of_date": row.as_of_date if row else None,
                     "run_id": row.id if row else None, "result": json.loads(row.results_json) if row else None})
    return rows


def rfq_context(rfq_id, quote_id, current, session):
    rfq = session.get(RfqRequest, rfq_id)
    quote = session.get(RfqQuote, quote_id)
    if not rfq or rfq.entity_id != organization(current) or not quote or quote.rfq_id != rfq.id:
        raise HTTPException(404, "RFQ ou réponse introuvable")
    provider = session.exec(select(RfqProvider).where(RfqProvider.label == quote.provider)).first()
    cpty_id = provider.counterparty_id if provider else None
    if cpty_id is None:
        raise HTTPException(422, "MISSING_DATA : rattachement explicite fournisseur → contrepartie requis")
    return rfq, cpty_id


@router.get("/rfq/{rfq_id}/quotes/{quote_id}/context")
def rfq_credit_context(rfq_id: int, quote_id: int, current: Current, session: Database):
    _, cpty_id = rfq_context(rfq_id, quote_id, current, session)
    return {"counterparty_id": cpty_id, "configuration": records(session, current, cpty_id)}


@router.post("/rfq/{rfq_id}/quotes/{quote_id}/check")
def rfq_check(rfq_id: int, quote_id: int, body: CalculationRequest, current: Current, session: Database):
    if body.data_scope != "PRODUCTION":
        raise HTTPException(422, "Le contrôle RFQ de production ne peut pas utiliser un périmètre de recette")
    rfq, cpty_id = rfq_context(rfq_id, quote_id, current, session)
    params = json.loads(rfq.params_json)
    # RFQ params are already engine units; use the frozen contract.
    pricing = {**params, "script": rfq.script_snapshot}
    if len(pricing.get("underlyings", [])) == 1 and not pricing.get("corr_matrix"):
        pricing["corr_matrix"] = [[1.0]]
    pricing["settlement_ccy"] = params.get("currency") or params.get("settlement_ccy")
    try:
        request = body.model_copy(update={"counterparty_id": cpty_id, "deal_id": None,
            "netting_set_id": None, "portfolio_id": None})
        from ..core.ccr.contracts import ProposedTrade
        request.proposed = ProposedTrade(pricing=pricing, nominal=params.get("notional", params.get("nominal", 0)),
            currency=params.get("currency") or params.get("settlement_ccy") or params.get("devise", "EUR"),
            sens="vente" if rfq.sens == "achat" else "achat", product_type=rfq.template_type,
            netting_set_id=body.netting_set_id)
        request.currency = request.proposed.currency
        return calculate(session, current, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
