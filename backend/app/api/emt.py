"""EMT / Target Market — MiFID II product governance summary.

Derives an indicative European MiFID Template (EMT) profile for the priced
product: knowledge & experience required, capacity to bear losses, risk
tolerance and recommended holding period.

SRI/MRM/CRM and the stress-scenario payoff are NOT recomputed here — they
are passed in from the already-computed /api/kid result, so the KID and the
EMT always show the same risk indicator for the same product instead of two
independent Monte Carlo runs that could drift apart (different CRM entry,
different seed noise). The frontend (EmtPanel.vue) refuses to call this
endpoint until a KID has been computed. Only the script-complexity read
(autocall / worst-of / leverage / barrier) is done here, from a plain parse
— no simulation.

This is a desk aid to speed up drafting, not a FinDatEx-compliant export —
client type, negative target market and distribution strategy are business
calls left to the user (see EmtPanel.vue manual fields).
"""
from __future__ import annotations
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..core.schemas import PricingRequest
from ..core.payscript.parser import parse_script, resolve_constats
from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, EmtRecord, Indicative, Deal

router = APIRouter(prefix="/api/emt", tags=["emt"])

_LEVERAGE_NAMES = {"GEARING", "LEVERAGE"}


class EmtRequest(PricingRequest):
    sri: int = Field(..., ge=1, le=7)
    mrm: int = Field(..., ge=1, le=7)
    crm: int = Field(..., ge=1, le=6)
    # Net stress-scenario (P1) payoff at maturity, as a fraction of notional,
    # after costs — from the last entry of the KID's `horizons` list
    # (horizons[-1].stress.amount / 10000).
    stress_payoff_fraction: float = Field(..., ge=0)


def _detect_features(compiled, n_underlyings: int) -> dict:
    has_leverage = any(
        p.name in _LEVERAGE_NAMES and p.is_pct and p.stored_val > 1.0
        for p in compiled.params
    )
    has_barrier = any(
        ('BAR' in p.name or p.name.startswith('KI') or p.name.startswith('KO'))
        for p in compiled.params
    )
    has_worst_of = n_underlyings > 1
    has_autocall = compiled.has_stop

    return {
        "has_leverage": has_leverage,
        "has_barrier": has_barrier,
        "has_worst_of": has_worst_of,
        "has_autocall": has_autocall,
        "n_underlyings": n_underlyings,
        "complexity_score": sum([has_leverage, has_barrier, has_worst_of, has_autocall]),
    }


def _capital_tier(stress_payoff: float) -> dict:
    """Bucket the KID's net stress-scenario payoff into a capital-loss tier."""
    if stress_payoff >= 0.97:
        return {"tier": "garanti", "label": "Capital garanti à l'échéance"}
    if stress_payoff >= 0.75:
        return {"tier": "partiel", "label": "Perte en capital possible mais limitée"}
    if stress_payoff > 0.0:
        return {"tier": "risque", "label": "Perte en capital significative possible"}
    return {"tier": "total", "label": "Perte en capital totale possible"}


def _knowledge_tier(complexity_score: int, capital_tier: str) -> dict:
    if complexity_score == 0 and capital_tier == "garanti":
        return {"tier": "base", "label": "Client non averti / de base"}
    if complexity_score <= 1 and capital_tier in ("garanti", "partiel"):
        return {"tier": "informe", "label": "Client informé"}
    return {"tier": "avance", "label": "Client expérimenté / averti"}


def _risk_tolerance(sri: int) -> str:
    if sri <= 2:
        return "Aucune tolérance particulière au risque requise"
    if sri <= 4:
        return "Tolérance limitée à la perte en capital"
    if sri == 5:
        return "Tolérance à une perte en capital significative"
    return "Tolérance élevée — peut supporter une perte en capital totale"


@router.post("/compute")
def emt_compute(
    req: EmtRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute an indicative EMT / target-market profile from a KID already run."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not compiled.events:
        raise HTTPException(422, "Aucun événement AT défini dans le script.")

    n = len(req.underlyings)
    if len(req.corr_matrix) != n or any(len(row) != n for row in req.corr_matrix):
        raise HTTPException(422, "Matrice de corrélation invalide.")

    features = _detect_features(compiled, n)
    cap = _capital_tier(req.stress_payoff_fraction)
    knowledge = _knowledge_tier(features["complexity_score"], cap["tier"])

    return {
        "sri": req.sri,
        "mrm": req.mrm,
        "crm": req.crm,
        "T_rhp": round(req.T, 4),
        "features": features,
        "capital_protection": cap,
        "knowledge_experience": knowledge,
        "risk_tolerance": _risk_tolerance(req.sri),
        "objective": (
            "Recherche de rendement (coupon conditionnel avec rappel anticipé)"
            if features["has_autocall"]
            else "Recherche de performance liée au(x) sous-jacent(s)"
        ),
    }


# ── AI-assisted payoff description ────────────────────────────────────────

class EmtSynthesizeRequest(BaseModel):
    product_title: str
    emt_result: dict
    script_params: list = []
    underlyings: list = []
    provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.3:70b"
    claude_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    openai_key: str = ""
    openai_model: str = "gpt-4o"


@router.post("/synthesize/payload")
def get_emt_synthesis_payload(
    req: EmtSynthesizeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Return the human-readable payload (+ persona/charter copy block) — no AI call."""
    from ..core.emt_synthesize import build_emt_payload, build_copy_block
    payload = build_emt_payload(req.product_title, req.emt_result, req.script_params, req.underlyings)
    return {"payload": payload, "copy_block": build_copy_block(payload)}


@router.post("/synthesize")
def synthesize_emt(
    req: EmtSynthesizeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Generate an AI payoff description using the configured LLM provider."""
    from ..core.emt_synthesize import (
        build_emt_payload, build_copy_block, EMT_SYSTEM_PROMPT_FR,
        call_ollama, call_claude, call_openai,
    )
    payload = build_emt_payload(req.product_title, req.emt_result, req.script_params, req.underlyings)

    try:
        if req.provider == "ollama":
            text = call_ollama(payload, EMT_SYSTEM_PROMPT_FR, req.ollama_url, req.ollama_model)
        elif req.provider == "claude":
            if not req.claude_key:
                raise ValueError("Clé API Claude requise.")
            text = call_claude(payload, EMT_SYSTEM_PROMPT_FR, req.claude_key, req.claude_model)
        elif req.provider == "openai":
            if not req.openai_key:
                raise ValueError("Clé API OpenAI requise.")
            text = call_openai(payload, EMT_SYSTEM_PROMPT_FR, req.openai_key, req.openai_model)
        else:
            raise ValueError(f"Provider inconnu : {req.provider}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur LLM ({req.provider}) : {e}")

    return {"synthesis": text, "payload": payload, "copy_block": build_copy_block(payload)}


# ── Persistence — append-only, one row per generation ────────────────────

class EmtSaveRequest(BaseModel):
    indicative_id: Optional[int] = None
    deal_id: Optional[int] = None
    product_title: str = "Produit structuré"
    sri: int
    mrm: int
    crm: int
    T_rhp: float
    capital_tier: str
    capital_label: str
    knowledge_tier: str
    knowledge_label: str
    risk_tolerance: str
    objective: str
    features: dict = {}
    client_type: str = "retail"
    distribution: str = "advice"
    negative_target_market: str = ""
    description: str = ""


def _emt_record_row(e: EmtRecord) -> dict:
    return {
        "id": e.id,
        "indicative_id": e.indicative_id,
        "deal_id": e.deal_id,
        "product_title": e.product_title,
        "sri": e.sri, "mrm": e.mrm, "crm": e.crm, "T_rhp": e.t_rhp,
        "capital_tier": e.capital_tier, "capital_label": e.capital_label,
        "knowledge_tier": e.knowledge_tier, "knowledge_label": e.knowledge_label,
        "risk_tolerance": e.risk_tolerance, "objective": e.objective,
        "features": json.loads(e.features_json),
        "client_type": e.client_type, "distribution": e.distribution,
        "negative_target_market": e.negative_target_market,
        "description": e.description,
        "created_at": e.created_at.isoformat(),
    }


@router.post("/save", status_code=201)
def save_emt(
    req: EmtSaveRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if not req.indicative_id and not req.deal_id:
        raise HTTPException(422, "indicative_id ou deal_id requis.")
    if req.indicative_id:
        ind = session.get(Indicative, req.indicative_id)
        if not ind or ind.user_id != current.id:
            raise HTTPException(404, "Indicatif introuvable")
    if req.deal_id:
        deal = session.get(Deal, req.deal_id)
        if not deal or deal.user_id != current.id:
            raise HTTPException(404, "Deal introuvable")

    rec = EmtRecord(
        indicative_id=req.indicative_id, deal_id=req.deal_id, user_id=current.id,
        product_title=req.product_title,
        sri=req.sri, mrm=req.mrm, crm=req.crm, t_rhp=req.T_rhp,
        capital_tier=req.capital_tier, capital_label=req.capital_label,
        knowledge_tier=req.knowledge_tier, knowledge_label=req.knowledge_label,
        risk_tolerance=req.risk_tolerance, objective=req.objective,
        features_json=json.dumps(req.features),
        client_type=req.client_type, distribution=req.distribution,
        negative_target_market=req.negative_target_market, description=req.description,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _emt_record_row(rec)


@router.get("/records")
def list_emt_records(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    indicative_id: Optional[int] = None,
    deal_id: Optional[int] = None,
):
    if not indicative_id and not deal_id:
        raise HTTPException(422, "indicative_id ou deal_id requis.")
    q = select(EmtRecord).where(EmtRecord.user_id == current.id)
    if indicative_id:
        q = q.where(EmtRecord.indicative_id == indicative_id)
    if deal_id:
        q = q.where(EmtRecord.deal_id == deal_id)
    rows = session.exec(q.order_by(EmtRecord.created_at.desc())).all()
    return [_emt_record_row(r) for r in rows]
