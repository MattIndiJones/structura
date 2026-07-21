"""Market-shock scenarios (spot/vol/rate/corr) — full reprice, not a linear
Greeks approximation, because barrier payoffs (autocalls, phoenix...) are too
non-linear for that (a -20% shock isn't 20x the delta). See PLAN
squishy-baking-sedgewick.

Reuses run_mc's existing bump vocabulary (spot_mult, vol_add, dr) exactly as
compute_greeks does, but with larger, named amplitudes and a full reprice
instead of a tiny bump-and-reprice derivative. Correlation shocks bypass
run_mc's corr_delta (single-pair only, built for Greeks' cross-gamma) and pass
a directly-shifted corr_matrix instead — run_mc already accepts that as a
first-class parameter, no new engine mechanism needed.

_mtm_core (api/deals.py) already builds everything a shock needs (residual
script, effective underlyings, corr, rates, N) to reprice a deal — a shock
just calls run_mc again with that same ctx, bumped. Runs are persisted
append-only (ShockRun, never updated in place — same pattern as
KidRecord/EmtRecord) since a scenario's parameters can change on the next
run and past ones should stay reconstructable."""
from __future__ import annotations
import json
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, Portfolio, ShockRun, User
from .auth import get_current_user
from .deals import _mtm_core, MtmRequest
from ..core.amc_prices import get_fx_series

router = APIRouter(tags=["shocks"])


class ShockOverride(BaseModel):
    spot_shock_pct: Optional[float] = None
    vol_shock_pts: Optional[float] = None


class ShockRequest(MtmRequest):
    """Body of the shock endpoints. recalibrate/overrides/r/window_days are
    inherited from MtmRequest and set the pre-shock baseline market
    assumptions (same as a MtM/Greeks call) — the fields below are the shock
    itself, layered on top via run_mc's own bump kwargs. Global by default,
    shock_overrides lets one underlying deviate from the global amplitude."""
    spot_shock_pct: float = 0.0
    vol_shock_pts: float = 0.0
    rate_shock_bp: float = 0.0
    corr_shock_pts: float = 0.0
    shock_overrides: dict[str, ShockOverride] = {}
    label: str = ""


def _build_shock_arrays(underlyings_json: list, shock: ShockRequest) -> tuple[list, list]:
    spot_mult, vol_add = [], []
    for u in underlyings_json:
        ov = shock.shock_overrides.get(u.get("name", ""))
        spot_pct = ov.spot_shock_pct if (ov and ov.spot_shock_pct is not None) else shock.spot_shock_pct
        vol_pts = ov.vol_shock_pts if (ov and ov.vol_shock_pts is not None) else shock.vol_shock_pts
        spot_mult.append(1.0 + spot_pct / 100.0)
        vol_add.append(vol_pts / 100.0)
    return spot_mult, vol_add


def _shock_corr(corr: list, corr_shock_pts: float) -> list:
    if not corr_shock_pts:
        return corr
    delta = corr_shock_pts / 100.0
    n = len(corr)
    return [
        [1.0 if i == j else max(-0.99, min(0.99, corr[i][j] + delta)) for j in range(n)]
        for i in range(n)
    ]


def _describe_shock(shock: ShockRequest) -> str:
    if shock.label.strip():
        return shock.label.strip()
    parts = []
    if shock.spot_shock_pct:
        parts.append(f"Spot {shock.spot_shock_pct:+.0f}%")
    if shock.vol_shock_pts:
        parts.append(f"Vol {shock.vol_shock_pts:+.0f}pts")
    if shock.rate_shock_bp:
        parts.append(f"Taux {shock.rate_shock_bp:+.0f}bp")
    if shock.corr_shock_pts:
        parts.append(f"Corr {shock.corr_shock_pts:+.0f}pts")
    return " / ".join(parts) or "Choc nul"


def _run_shock_on_deal(deal: Deal, session: Session, n_paths: int, shock: ShockRequest) -> dict:
    """Full reprice under the shocked scenario. Never raises for a
    resolved-pending deal (returns a skip marker instead), so a
    portfolio-wide shock can keep going over the rest of the book."""
    from ..core.payscript.engine import run_mc

    mtm_payload, ctx = _mtm_core(deal, session, n_paths, shock)
    if ctx is None:
        return {"deal_id": deal.id, "reference": deal.reference, "skipped": True,
                "reason": mtm_payload.get("message", "résolution en attente")}

    spot_mult, vol_add = _build_shock_arrays(ctx["underlyings_json"], shock)
    corr_shocked = _shock_corr(ctx["corr"], shock.corr_shock_pts)
    dr = shock.rate_shock_bp / 10000.0

    result = run_mc(
        ctx["residual_script"], ctx["engine_uls"], corr_shocked,
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=42, antithetic=ctx["antithetic"], user_params=ctx["user_params"],
        spot_mult=spot_mult, vol_add=vol_add, dr=dr,
        yield_curve=ctx["yc"], sigma_r=ctx["sigma_r"], a_r=ctx["a_r"],
        barrier_monitoring=ctx["barrier_monitoring"],
    )

    fx = get_fx_series(deal.devise, "EUR")
    fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
    delta_pts = result["price"] - mtm_payload["mtm"]

    return {
        "deal_id": deal.id, "reference": deal.reference, "skipped": False,
        "mtm_before": mtm_payload["mtm"], "mtm_after": result["price"],
        "delta_pts": round(delta_pts, 4),
        "delta_eur": round(delta_pts * deal.nominal * fx_rate, 2),
        "n_paths": result["n_paths"],
    }


def _run_shock_on_book(deals: list[Deal], session: Session, n_paths: int, shock: ShockRequest) -> dict:
    contributions, skipped, errors = [], [], []
    total_delta_eur = 0.0
    # Nominal total (EUR) of every deal in scope — including skipped/errored
    # ones, same denominator convention as the Risque tab's "Nominal total"
    # tile — the % impact must be read against the portfolio's actual size,
    # not just the subset that happened to reprice cleanly this time.
    nominal_total_eur = 0.0
    for d in deals:
        fx = get_fx_series(d.devise, "EUR")
        fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
        nominal_total_eur += d.nominal * fx_rate

        try:
            r = _run_shock_on_deal(d, session, n_paths, shock)
        except HTTPException as e:
            errors.append({"deal_id": d.id, "reference": d.reference, "error": e.detail})
            continue
        if r.get("skipped"):
            skipped.append(r)
            continue
        contributions.append(r)
        total_delta_eur += r["delta_eur"]

    pct_impact = (total_delta_eur / nominal_total_eur * 100.0) if nominal_total_eur else None
    return {
        "total_delta_eur": round(total_delta_eur, 2),
        "nominal_total_eur": round(nominal_total_eur, 2),
        "pct_impact": round(pct_impact, 3) if pct_impact is not None else None,
        "contributions": contributions,
        "skipped": skipped,
        "errors": errors,
    }


def _persist_shock(session: Session, user_id: int, scope: str, shock: ShockRequest,
                    result: dict, deal_id: int | None = None,
                    portfolio_id: int | None = None) -> ShockRun:
    run = ShockRun(
        user_id=user_id, scope=scope, deal_id=deal_id, portfolio_id=portfolio_id,
        label=_describe_shock(shock),
        params_json=shock.model_dump_json(),
        result_json=json.dumps(result),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _shock_run_row(r: ShockRun) -> dict:
    return {
        "id": r.id, "scope": r.scope, "deal_id": r.deal_id, "portfolio_id": r.portfolio_id,
        "label": r.label, "params": json.loads(r.params_json), "result": json.loads(r.result_json),
        "created_at": r.created_at.isoformat(),
    }


@router.post("/api/deals/{deal_id}/shock")
def shock_deal(
    deal_id: int,
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    result = _run_shock_on_deal(deal, session, n_paths, body)
    run = _persist_shock(session, current.id, "deal", body, result, deal_id=deal_id)
    return {**result, "run_id": run.id, "label": run.label}


@router.post("/api/portfolios/{portfolio_id}/shock")
def shock_portfolio(
    portfolio_id: int,
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    deals = session.exec(
        select(Deal).where(Deal.portfolio_id == portfolio_id, Deal.status == "actif")
    ).all()
    result = _run_shock_on_book(list(deals), session, n_paths, body)
    run = _persist_shock(session, current.id, "portfolio", body, result, portfolio_id=portfolio_id)
    return {**result, "run_id": run.id, "label": run.label}


@router.post("/api/portfolios/shock-global")
def shock_global(
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    result = _run_shock_on_book(list(deals), session, n_paths, body)
    run = _persist_shock(session, current.id, "global", body, result)
    return {**result, "run_id": run.id, "label": run.label}


@router.get("/api/shocks")
def list_shocks(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    scope: Optional[str] = None,
    deal_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    limit: int = 20,
):
    q = select(ShockRun).where(ShockRun.user_id == current.id)
    if scope:
        q = q.where(ShockRun.scope == scope)
    if deal_id is not None:
        q = q.where(ShockRun.deal_id == deal_id)
    if portfolio_id is not None:
        q = q.where(ShockRun.portfolio_id == portfolio_id)
    q = q.order_by(ShockRun.created_at.desc()).limit(limit)
    runs = session.exec(q).all()
    return [_shock_run_row(r) for r in runs]
