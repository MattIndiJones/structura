"""KID PRIIPs — Key Information Document analytical computation.

Runs 3 Monte Carlo simulations (T_full, T_half, T_1Y) and returns:
  - SRI (Synthetic Risk Indicator 1-7) from VEV / MRM / CRM
  - 4 PRIIPs scenarios (stress/défavorable/modéré/favorable) × 3 horizons
  - Annualized net returns after costs for a 10 000€ investment
"""
from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import json
from sqlmodel import Session, select

from ..core.schemas import PricingRequest
from ..core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ..core.payscript.engine import run_mc
from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, KidRecord, Indicative, Deal

router = APIRouter(prefix="/api/kid", tags=["kid"])

# ── PRIIPs SRI lookup table [MRM-1][CRM-1] ───────────────────────────
_SRI_TABLE = [
    [1, 1, 2, 3, 4, 5],  # MRM 1
    [1, 2, 2, 3, 4, 5],  # MRM 2
    [2, 2, 3, 4, 4, 5],  # MRM 3
    [3, 3, 4, 4, 5, 6],  # MRM 4
    [4, 4, 4, 5, 6, 6],  # MRM 5
    [5, 5, 5, 5, 6, 7],  # MRM 6
    [6, 7, 7, 7, 7, 7],  # MRM 7
]

_VEV_THRESHOLDS = [0.005, 0.05, 0.12, 0.20, 0.30, 0.80]


def _mrm_from_vev(vev: float) -> int:
    for i, thr in enumerate(_VEV_THRESHOLDS):
        if vev < thr:
            return i + 1
    return 7


def _sri(mrm: int, crm: int) -> int:
    return _SRI_TABLE[max(0, min(mrm - 1, 6))][max(0, min(crm - 1, 5))]


# ── Single MC run ─────────────────────────────────────────────────────

def _mc_percentiles(compiled, uls, corr, r, T_run, T_cap, N, model, seed,
                    antithetic, user_params, yield_curve, sigma_r, a_r,
                    floor_price: float = 0.0) -> dict:
    """Run MC capped at T_cap.
    Paths that don't terminate (payoff≈0) are floored at floor_price
    to approximate mark-to-market for intermediate horizons.
    """
    T_eff = min(effective_T_max(compiled, T_run), T_cap)
    res = run_mc(
        script=compiled, underlyings=uls, corr_matrix=corr, r=r,
        T_max=T_eff, N=N, model=model, seed=seed, antithetic=antithetic,
        user_params=user_params, yield_curve=yield_curve or [],
        sigma_r=sigma_r, a_r=a_r,
    )
    px = np.array(res["payoffs"], dtype=np.float64)

    # Floor near-zero payoffs (surviving paths at intermediate horizon)
    if floor_price > 0.01:
        px = np.where(px < 0.01, floor_price, px)

    return {
        "price": float(res["price"]),
        "p1":  float(np.percentile(px, 1)),
        "p10": float(np.percentile(px, 10)),
        "p50": float(np.percentile(px, 50)),
        "p90": float(np.percentile(px, 90)),
        "T_eff": round(T_eff, 4),
    }


# ── Cost-adjusted scenario row ────────────────────────────────────────

def _scenario_row(sc: dict, T_h: float, cost_entry: float,
                  cost_exit: float, cost_ongoing: float) -> dict:
    """Convert raw payoff percentiles to KID display (10 000€ invested)."""
    notional = 10_000.0
    invested = notional * (1 - cost_entry / 100)

    def _fmt(payoff: float) -> dict:
        gross = invested * payoff
        net = gross * ((1 - cost_exit / 100) * (1 - cost_ongoing / 100) ** T_h)
        net = round(net, 2)
        # Annualized return on initial 10 000€
        if T_h > 0 and net > 0:
            ann = ((net / notional) ** (1.0 / T_h) - 1.0) * 100.0
        else:
            ann = -100.0
        return {"amount": net, "ann_return": round(ann, 2)}

    return {
        "T": round(T_h, 4),
        "stress":      _fmt(sc["p1"]),
        "defavorable": _fmt(sc["p10"]),
        "modere":      _fmt(sc["p50"]),
        "favorable":   _fmt(sc["p90"]),
    }


# ── Request schema ────────────────────────────────────────────────────

class KidRequest(PricingRequest):
    crm: int = Field(default=3, ge=1, le=6)
    cost_entry: float = Field(default=0.0, ge=0, le=10)    # % one-shot
    cost_exit: float = Field(default=0.0, ge=0, le=10)     # % one-shot
    cost_ongoing: float = Field(default=0.0, ge=0, le=5)   # % per year


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/compute")
def kid_compute(
    req: KidRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute PRIIPs KID scenarios and SRI."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not compiled.events:
        raise HTTPException(422, "Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(422, "Matrice de corrélation invalide.")

    T_full = req.T
    T_half = T_full / 2.0
    T_1y   = min(1.0, T_full)

    common = dict(
        compiled=compiled, uls=uls, corr=corr, r=req.r,
        T_run=T_full, N=req.N, model=req.model, seed=req.seed,
        antithetic=req.antithetic, user_params=req.user_params,
        yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
    )

    try:
        # Step 1 — run full simulation first to get floor_price
        sc_full = _mc_percentiles(**common, T_cap=T_full, floor_price=0.0)
        floor   = sc_full["price"]

        # Step 2 — intermediate horizons in parallel (use floor_price for surviving paths)
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_half = ex.submit(_mc_percentiles, **common, T_cap=T_half, floor_price=floor)
            fut_1y   = ex.submit(_mc_percentiles, **common, T_cap=T_1y,   floor_price=floor)
            sc_half = fut_half.result()
            sc_1y   = fut_1y.result()
    except ValueError as e:
        raise HTTPException(422, str(e))

    # VEV from 1st-percentile payoff at maturity (PRIIPs Annex II)
    p1 = sc_full["p1"]
    if p1 > 0.0 and p1 < 1.0:
        vev = math.sqrt(-2.0 * math.log(p1) / T_full)
    else:
        vev = 0.0

    mrm = _mrm_from_vev(vev)
    sri = _sri(mrm, req.crm)

    # Build horizons list (ascending T)
    cost = (req.cost_entry, req.cost_exit, req.cost_ongoing)
    horizons = []
    if T_full > 1.0:
        horizons.append(_scenario_row(sc_1y,   T_1y,   *cost))
    if T_full > 0.5:
        horizons.append(_scenario_row(sc_half, T_half, *cost))
    horizons.append(_scenario_row(sc_full, T_full, *cost))

    return {
        "sri":  sri,
        "mrm":  mrm,
        "crm":  req.crm,
        "vev":  round(vev * 100, 2),   # expressed in %
        "T_rhp": round(T_full, 4),
        "horizons": horizons,
        "full_price": round(sc_full["price"], 4),
        "costs": {
            "entry":   req.cost_entry,
            "exit":    req.cost_exit,
            "ongoing": req.cost_ongoing,
        },
    }


# ── Persistence — append-only, one row per generation ──────────────────

class KidSaveRequest(BaseModel):
    indicative_id: Optional[int] = None
    deal_id: Optional[int] = None
    product_title: str = "Produit structuré"
    sri: int
    mrm: int
    crm: int
    vev: float
    T_rhp: float
    horizons: list = []
    costs: dict = {}


def _kid_record_row(k: KidRecord) -> dict:
    return {
        "id": k.id,
        "indicative_id": k.indicative_id,
        "deal_id": k.deal_id,
        "product_title": k.product_title,
        "sri": k.sri, "mrm": k.mrm, "crm": k.crm, "vev": k.vev, "T_rhp": k.t_rhp,
        "horizons": json.loads(k.horizons_json),
        "costs": json.loads(k.costs_json),
        "created_at": k.created_at.isoformat(),
    }


@router.post("/save", status_code=201)
def save_kid(
    req: KidSaveRequest,
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

    rec = KidRecord(
        indicative_id=req.indicative_id, deal_id=req.deal_id, user_id=current.id,
        product_title=req.product_title,
        sri=req.sri, mrm=req.mrm, crm=req.crm, vev=req.vev, t_rhp=req.T_rhp,
        horizons_json=json.dumps(req.horizons), costs_json=json.dumps(req.costs),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _kid_record_row(rec)


@router.get("/records")
def list_kid_records(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    indicative_id: Optional[int] = None,
    deal_id: Optional[int] = None,
):
    if not indicative_id and not deal_id:
        raise HTTPException(422, "indicative_id ou deal_id requis.")
    q = select(KidRecord).where(KidRecord.user_id == current.id)
    if indicative_id:
        q = q.where(KidRecord.indicative_id == indicative_id)
    if deal_id:
        q = q.where(KidRecord.deal_id == deal_id)
    rows = session.exec(q.order_by(KidRecord.created_at.desc())).all()
    return [_kid_record_row(r) for r in rows]
