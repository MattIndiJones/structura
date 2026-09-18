"""EMT / Target Market — MiFID II product governance summary.

Derives an indicative European MiFID Template (EMT) profile for the priced
product: knowledge & experience required, capacity to bear losses, risk
tolerance and recommended holding period.

SRI/MRM/CRM are NOT recomputed here — they are passed in from the already
computed /api/kid result, so the KID and EMT keep one risk indicator instead
of two Monte Carlo runs that could drift apart.  Capital protection is a
separate contractual input: the KID stress scenario can measure a loss but
never establish a guarantee.  The frontend (EmtPanel.vue) refuses to call
this endpoint until a KID has been computed. Only the script-complexity read
(autocall / worst-of / leverage / barrier) is done here, from a plain parse.

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
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..core.schemas import PricingRequest
from ..core.payscript.parser import parse_script, resolve_analysis_constats, resolve_constats
from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, EmtRecord, Indicative, Deal
from ..core.product.models import FrozenObject
from ..core.product.inputs import calculation_context, pricing_input
from ..services.product_repository import ProductError, load_product, owned_record, stage_revision

router = APIRouter(prefix="/api/emt", tags=["emt"])

_LEVERAGE_NAMES = {"GEARING", "LEVERAGE"}


class EmtRequest(PricingRequest):
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    sri: int = Field(..., ge=1, le=7)
    mrm: int = Field(..., ge=1, le=7)
    crm: int = Field(..., ge=1, le=6)
    # Contractual truth entered from the term sheet.  A market scenario can
    # measure a loss but can never establish a legal capital guarantee.
    capital_protection_level_pct: Optional[float] = Field(default=None, ge=0, le=1000)
    capital_protection_condition: Literal[
        "unknown", "unconditional", "conditional"
    ] = "unknown"


def _script_without_comments(script_text: str) -> str:
    lines = []
    for line in script_text.splitlines():
        code = line.split("#", 1)[0]
        # PAY labels describe a flow for humans and are not observables used by
        # the payoff.  "coupon worst-of" must not turn a basket into a WOF.
        lines.append(re.sub(r'"[^"]*"', '""', code))
    return "\n".join(lines)


def _detect_features(compiled, n_underlyings: int, script_text: str = "") -> dict:
    source = _script_without_comments(script_text).upper()
    has_leverage = any(
        p.name in _LEVERAGE_NAMES and p.is_pct and p.stored_val > 1.0
        for p in compiled.params
    )
    has_barrier = any(
        ('BAR' in p.name or p.name.startswith('KI') or p.name.startswith('KO'))
        for p in compiled.params
    )
    # A multi-asset average and a worst-of are different risks.  Read the
    # observable actually used by the payoff rather than guessing from the
    # number of underlyings.
    has_worst_of = bool(re.search(r"\bWOF(?:_MIN)?\b", source))
    is_multi_asset = n_underlyings > 1
    has_autocall = compiled.has_stop

    return {
        "has_leverage": has_leverage,
        "has_barrier": has_barrier,
        "has_worst_of": has_worst_of,
        "is_multi_asset": is_multi_asset,
        "has_autocall": has_autocall,
        "n_underlyings": n_underlyings,
        "complexity_score": sum([has_leverage, has_barrier, has_worst_of, has_autocall]),
    }


def _capital_tier(level_pct: float | None, condition: str) -> dict:
    """Classify only an explicit, unconditional contractual protection."""
    details = {
        "level_pct": level_pct,
        "condition": condition,
        "source": "contract",
    }
    if level_pct is not None and level_pct >= 100.0 and condition == "unconditional":
        return {
            **details,
            "tier": "garanti",
            "label": f"Capital garanti contractuellement à {level_pct:g} % à l'échéance",
        }
    if level_pct is None:
        reason = "niveau contractuel non renseigné"
    elif condition == "conditional":
        reason = f"protection contractuelle de {level_pct:g} % conditionnelle"
    elif condition == "unknown":
        reason = f"condition de la protection de {level_pct:g} % non renseignée"
    else:
        reason = f"protection contractuelle limitée à {level_pct:g} %"
    return {
        **details,
        "tier": "indetermine",
        "label": f"Protection du capital indéterminée — {reason}",
    }


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
    session: Annotated[Session, Depends(get_session)],
):
    """Compute an indicative EMT / target-market profile from a KID already run."""
    if req.product_id is not None:
        try:
            owned_record(session, req.product_id, current)
            product = load_product(session, req.product_id)
            if (req.product_terms_version is not None
                    and req.product_terms_version != product.terms_version):
                raise ProductError(
                    "PRODUCT_TERMS_STALE",
                    "La version des termes du Product a changé.")
            req = EmtRequest.model_validate(pricing_input(
                product, calculation_context(req.model_dump(mode="json"))))
        except ProductError as exc:
            raise HTTPException(
                exc.status, detail={"code": exc.code, "message": str(exc)})
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not compiled.events:
        raise HTTPException(422, "Aucun événement AT défini dans le script.")

    n = len(req.underlyings)
    if len(req.corr_matrix) != n or any(len(row) != n for row in req.corr_matrix):
        raise HTTPException(422, "Matrice de corrélation invalide.")

    features = _detect_features(compiled, n, req.script)
    cap = _capital_tier(
        req.capital_protection_level_pct,
        req.capital_protection_condition,
    )
    # `features` is already persisted by /api/emt/save.  Keeping the explicit
    # contract input there makes a saved EMT reconstructable without a schema
    # migration and avoids reducing the audit trail to a human-readable label.
    features["capital_protection_contract"] = {
        "level_pct": req.capital_protection_level_pct,
        "condition": req.capital_protection_condition,
        "source": "contract",
    }
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

from ..core.ai_contract import AiOptions
from ..services.llm.workbench import prompt_preview, generate_text
from ..services.llm.providers import LlmError


class EmtSynthesizeRequest(AiOptions):
    product_title: str
    emt_result: dict
    script_params: list = []
    underlyings: list = []
    ollama_model: str | None = None
    claude_key: str = ""
    claude_model: str | None = None
    openai_key: str = ""
    openai_model: str | None = None


@router.post("/synthesize/payload")
def get_emt_synthesis_payload(
    req: EmtSynthesizeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Return the human-readable payload (+ persona/charter copy block) — no AI call."""
    from ..core.emt_synthesize import build_emt_payload, build_copy_block
    payload = build_emt_payload(req.product_title, req.emt_result, req.script_params, req.underlyings)
    return {"payload": payload, "copy_block": build_copy_block(payload)}


def synthesis_prompt(req):
    from ..core.emt_synthesize import build_emt_payload, EMT_SYSTEM_PROMPT_FR
    payload = build_emt_payload(req.product_title, req.emt_result, req.script_params, req.underlyings)
    return prompt_preview(EMT_SYSTEM_PROMPT_FR, payload, "emt-description-v1")


@router.post("/synthesize/prompt")
def preview_synthesis(req: EmtSynthesizeRequest, current: Annotated[User, Depends(get_current_user)]):
    return synthesis_prompt(req)


@router.post("/synthesize")
def synthesize_emt(req: EmtSynthesizeRequest, current: Annotated[User, Depends(get_current_user)]):
    from ..core.emt_synthesize import build_copy_block
    try:
        result = generate_text(synthesis_prompt(req), req)
        prompt = result["prompt"]
        return {**result, "synthesis": result["text"], "payload": prompt["user"],
                "copy_block": build_copy_block(prompt["user"], prompt["system"])}
    except LlmError as e:
        raise HTTPException(422, str(e))


# ── Persistence — append-only, one row per generation ────────────────────

class EmtSaveRequest(BaseModel):
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
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
    features: dict = Field(default_factory=dict)
    client_type: str = "retail"
    distribution: str = "advice"
    negative_target_market: str = ""
    description: str = ""


def _emt_record_row(e: EmtRecord) -> dict:
    return {
        "id": e.id,
        "indicative_id": e.indicative_id,
        "deal_id": e.deal_id,
        "product_id": e.product_id,
        "product_terms_version": e.product_terms_version,
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
    if not req.indicative_id and not req.deal_id and not req.product_id:
        raise HTTPException(422, "product_id, indicative_id ou deal_id requis.")
    linked_product_id = req.product_id
    if req.indicative_id:
        ind = session.get(Indicative, req.indicative_id)
        if not ind or ind.user_id != current.id:
            raise HTTPException(404, "Indicatif introuvable")
        if linked_product_id is not None and ind.product_id != linked_product_id:
            raise HTTPException(422, "L’indicatif ne correspond pas au Product demandé.")
        linked_product_id = linked_product_id or ind.product_id
    if req.deal_id:
        deal = session.get(Deal, req.deal_id)
        if not deal or deal.user_id != current.id:
            raise HTTPException(404, "Deal introuvable")
        if deal.product_id is None:
            raise HTTPException(409, detail={
                "code": "DEAL_PRODUCT_MISSING",
                "message": "Le deal ne possède pas de Product canonique.",
            })
        if linked_product_id is not None and deal.product_id != linked_product_id:
            raise HTTPException(422, "Le deal ne correspond pas au Product demandé.")
        linked_product_id = linked_product_id or deal.product_id

    if linked_product_id is None:
        raise HTTPException(409, detail={
            "code": "DOCUMENT_PRODUCT_MISSING",
            "message": "L’EMT doit être rattaché au Product canonique.",
        })

    product = None
    if linked_product_id is not None:
        try:
            owned_record(session, linked_product_id, current)
            product = load_product(session, linked_product_id)
        except ProductError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)})
        if req.product_terms_version is not None and req.product_terms_version != product.terms_version:
            raise HTTPException(409, "La version des termes du Product a changé.")

    rec = EmtRecord(
        product_id=linked_product_id,
        product_terms_version=product.terms_version if product else None,
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
    session.flush()
    if product is not None:
        document = FrozenObject({"kind": "EMT", "record_id": rec.id,
                                 "terms_version": product.terms_version,
                                 "created_at": rec.created_at.isoformat()})
        product = product.model_copy(update={"documents": (*product.documents, document)})
        stage_revision(session, product, expected_revision=product.revision,
                       actor_id=current.id, action="PRODUCT_EMT_RETAINED",
                       reason="Conservation d’un EMT sur le Product.")
    session.commit()
    session.refresh(rec)
    return _emt_record_row(rec)


@router.get("/records")
def list_emt_records(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    indicative_id: Optional[int] = None,
    deal_id: Optional[int] = None,
    product_id: Optional[int] = None,
):
    if not indicative_id and not deal_id and not product_id:
        raise HTTPException(422, "product_id, indicative_id ou deal_id requis.")
    q = select(EmtRecord).where(EmtRecord.user_id == current.id)
    if indicative_id:
        q = q.where(EmtRecord.indicative_id == indicative_id)
    if deal_id:
        q = q.where(EmtRecord.deal_id == deal_id)
    if product_id:
        q = q.where(EmtRecord.product_id == product_id)
    rows = session.exec(q.order_by(EmtRecord.created_at.desc())).all()
    return [_emt_record_row(r) for r in rows]
