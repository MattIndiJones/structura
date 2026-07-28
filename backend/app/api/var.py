"""VaR/ES study endpoints — launches an async ComputeBatch (kind=
'var_scenario') covering every active deal in scope × every generated market
scenario (historical and/or parametric — both run side by side in the same
study, never blended, per the VaR chantier discussion), and lets the caller
poll it. Nothing here executes synchronously: a batch sits `queued` until
the worker daemon (backend/scripts/run_compute_worker.py, started
separately by Philippe) drains it — see core/compute/'s own docstring for
why this whole feature exists as an async module rather than a blocking
endpoint like /shock.

Aggregation (VaR/ES/percentiles per method) happens lazily on first poll
after the batch reaches a terminal state, then gets cached onto the batch
row (result_summary_json) — the worker itself stays completely
VaR-agnostic, it only knows about generic jobs (see queue_store.py)."""
from __future__ import annotations
import json
from datetime import date, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, Portfolio, ComputeBatch, ComputeJob, User
from .auth import get_current_user
from ..services.market_data import load_hist_prices
from ..core.amc_prices import get_fx_series
from ..core.compute.queue_store import enqueue_batch
from ..core.var_engine import (
    build_deal_scenario_base, apply_scenario_to_deal_base,
    generate_historical_scenarios, generate_parametric_scenarios, aggregate_var,
)

router = APIRouter(prefix="/api/portfolios", tags=["var"])


class VarRequest(BaseModel):
    method: Literal["historical", "parametric", "both"] = "both"
    confidence: float = 0.95
    horizon_days: int = 1
    lookback_years: float = 5.0
    n_parametric: int = 2000
    n_paths_per_scenario: int = 3000
    max_workers: int = 4


def _launch_var_study(deals: list[Deal], session: Session, user_id: int,
                       label: str, body: VarRequest) -> dict:
    bases = []
    skipped = []
    tickers: set[str] = set()
    for d in deals:
        base = build_deal_scenario_base(d, session, body.n_paths_per_scenario)
        if base.get("skipped"):
            skipped.append({"deal_id": d.id, "reference": d.reference, "reason": base["reason"]})
            continue
        fx = get_fx_series(d.devise, "EUR")
        base["fx_rate"] = float(fx.iloc[-1]) if not fx.empty else 1.0
        bases.append(base)
        tickers.update(base["tickers"])

    if not bases:
        raise HTTPException(422, f"Aucun deal repriçable dans cette sélection "
                                 f"({len(skipped)} ignoré(s) — voir le détail)")

    ticker_list = sorted(tickers)
    # Buffer past the requested lookback for the rolling vol/corr window
    # (generate_historical_scenarios/calibrate_comovement need ~1 month of
    # history before the window they actually use starts).
    start = (date.today() - timedelta(days=round(body.lookback_years * 365.25) + 60)).isoformat()
    px_data = load_hist_prices(ticker_list, start, date.today().isoformat())
    if "error" in px_data:
        raise HTTPException(422, px_data["error"])
    dates_list, prices = px_data["dates"], px_data["prices"]

    scenarios = []
    if body.method in ("historical", "both"):
        scenarios += generate_historical_scenarios(
            prices, dates_list, ticker_list, lookback_years=body.lookback_years,
            horizon_days=body.horizon_days)
    if body.method in ("parametric", "both"):
        scenarios += generate_parametric_scenarios(
            prices, dates_list, ticker_list, n_scenarios=body.n_parametric,
            horizon_days=body.horizon_days)
    if not scenarios:
        raise HTTPException(422, "Historique de prix insuffisant pour générer des scénarios "
                                 f"(lookback demandé : {body.lookback_years} an(s))")

    job_payloads, job_labels = [], []
    for scenario in scenarios:
        for base in bases:
            payload = apply_scenario_to_deal_base(base, scenario)
            payload["_meta"] = {
                "scenario_key": scenario.key, "method": scenario.method,
                "deal_id": base["deal_id"], "mtm_before": base["mtm_before"],
                "nominal": base["nominal"], "fx_rate": base["fx_rate"],
            }
            job_payloads.append(payload)
            job_labels.append(f"{scenario.label} / {base['reference']}")

    batch = enqueue_batch(
        session, user_id, "var_scenario", label,
        job_payloads=job_payloads, job_labels=job_labels,
        params={
            "method": body.method, "confidence": body.confidence,
            "horizon_days": body.horizon_days, "lookback_years": body.lookback_years,
            "n_scenarios_historical": sum(1 for s in scenarios if s.method == "historical"),
            "n_scenarios_parametric": sum(1 for s in scenarios if s.method == "parametric"),
            "n_deals": len(bases), "max_workers": body.max_workers,
        },
    )
    return {
        "batch_id": batch.id, "status": batch.status, "total_jobs": batch.total_jobs,
        "deals_included": len(bases), "deals_skipped": skipped,
        "n_scenarios": len(scenarios),
    }


@router.post("/var-global", status_code=202)
def launch_var_global(
    body: VarRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    result = _launch_var_study(list(deals), session, current.id, "VaR — tous portefeuilles", body)
    result["scope"] = "global"
    return result


@router.post("/{portfolio_id}/var", status_code=202)
def launch_var_portfolio(
    portfolio_id: int,
    body: VarRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    deals = session.exec(
        select(Deal).where(Deal.portfolio_id == portfolio_id, Deal.status == "actif")
    ).all()
    result = _launch_var_study(list(deals), session, current.id, f"VaR — {p.name}", body)
    result["scope"] = "portfolio"
    result["portfolio_id"] = portfolio_id
    return result


@router.get("/var/{batch_id}")
def get_var_result(
    batch_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    batch = session.get(ComputeBatch, batch_id)
    if not batch or batch.user_id != current.id or batch.kind != "var_scenario":
        raise HTTPException(404, "Étude VaR introuvable")

    row = {
        "batch_id": batch.id, "label": batch.label, "status": batch.status,
        "total_jobs": batch.total_jobs, "completed_jobs": batch.completed_jobs,
        "failed_jobs": batch.failed_jobs, "created_at": batch.created_at.isoformat(),
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        "params": json.loads(batch.params_json) if batch.params_json else {},
        "result": None,
    }
    if batch.status in ("queued", "running"):
        return row

    if batch.result_summary_json and batch.result_summary_json != "{}":
        row["result"] = json.loads(batch.result_summary_json)
        return row

    # Terminal state, never aggregated yet — group every job's ΔMtM (EUR) by
    # scenario (summed across every deal of the book that entered this
    # study), then compute VaR/ES separately per method.
    jobs = session.exec(select(ComputeJob).where(ComputeJob.batch_id == batch_id)).all()
    by_scenario: dict[str, dict] = {}
    job_errors = []
    for j in jobs:
        payload = json.loads(j.payload_json)
        meta = payload.get("_meta", {})
        key, method = meta.get("scenario_key"), meta.get("method")
        bucket = by_scenario.setdefault(key, {"method": method, "delta_eur": 0.0,
                                               "n_deals": 0, "n_errors": 0})
        if j.status != "done":
            bucket["n_errors"] += 1
            if j.error:
                job_errors.append({"job_id": j.id, "label": j.label, "error": j.error})
            continue
        result = json.loads(j.result_json)
        delta_pts = result["price"] - meta["mtm_before"]
        bucket["delta_eur"] += delta_pts * meta["nominal"] * meta["fx_rate"]
        bucket["n_deals"] += 1

    hist_deltas = [b["delta_eur"] for b in by_scenario.values() if b["method"] == "historical"]
    param_deltas = [b["delta_eur"] for b in by_scenario.values() if b["method"] == "parametric"]
    confidence = row["params"].get("confidence", 0.95)

    result_summary = {
        "historical": aggregate_var(hist_deltas, confidence) if hist_deltas else None,
        "parametric": aggregate_var(param_deltas, confidence) if param_deltas else None,
        "worst_scenarios": sorted(
            [{"scenario_key": k, "method": b["method"], "delta_eur": round(b["delta_eur"], 2)}
             for k, b in by_scenario.items()],
            key=lambda x: x["delta_eur"],
        )[:10],
        "job_errors": job_errors[:20],
    }
    batch.result_summary_json = json.dumps(result_summary)
    session.add(batch)
    session.commit()

    row["result"] = result_summary
    return row
