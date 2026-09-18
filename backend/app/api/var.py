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
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, Portfolio, ComputeBatch, ComputeJob, User, position_sign
from .auth import get_current_user
from ..services.market_data import load_hist_prices
from ..core.amc_prices import fx_rate_to
from ..core.compute.queue_store import enqueue_batch
from ..core.var_engine import (
    MarketScenario, build_deal_scenario_base, apply_scenario_to_deal_base,
    generate_historical_scenarios, generate_parametric_scenarios, aggregate_var,
)
from ..core.compute_budget import estimate_var_portfolio
from ..core.valuation_context import canonical_fingerprint

router = APIRouter(prefix="/api/portfolios", tags=["var"])


class VarRequest(BaseModel):
    method: Literal["historical", "parametric", "both"] = "both"
    confidence: float = 0.95
    horizon_days: int = Field(default=1, ge=1, le=20)
    lookback_years: float = Field(default=5.0, ge=0.5, le=10.0)
    n_parametric: int = Field(default=2000, ge=100, le=5000)
    # deal_valuation enforces the same 1,000-path numerical floor. Exposing
    # 500 here made the accepted request differ silently from the run and its
    # budget estimate.
    n_paths_per_scenario: int = Field(default=3000, ge=1000, le=20000)
    max_workers: int = Field(default=4, ge=1, le=4)
    confirmation_token: str | None = None


def _deal_descriptor(deal: Deal) -> dict:
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "nominal": deal.nominal,
        "currency": deal.devise,
    }


def _aggregate_var_jobs(jobs: list[ComputeJob], params: dict) -> dict:
    """Build a publishable VaR result only on a scenario-complete scope.

    The requested book and the automatically reduced book are two separate
    statements.  The first never publishes a number after any exclusion or
    failed job.  The second removes the UNION of failed deals from every
    scenario, then publishes only if that fixed reduced universe is complete.
    """
    confidence = params.get("confidence", 0.95)
    preflight = [dict(item, phase="preflight")
                 for item in params.get("preflight_exclusions", [])]
    included = list(params.get("included_deals", []))
    requested = list(params.get("requested_deals", []))
    scenarios = list(params.get("scenarios", []))

    parsed_jobs = []
    job_errors = []
    for job in jobs:
        try:
            payload = json.loads(job.payload_json or "{}")
            meta = payload.get("_meta", {})
        except (TypeError, ValueError, json.JSONDecodeError):
            meta = {}
        parsed_jobs.append((job, meta))

    # Compatibility for batches launched before the scope metadata existed.
    if not included:
        seen = {}
        for _job, meta in parsed_jobs:
            deal_id = meta.get("deal_id")
            if deal_id is not None:
                seen.setdefault(deal_id, {
                    "deal_id": deal_id,
                    "reference": meta.get("reference") or str(deal_id),
                    "nominal": meta.get("nominal"),
                    "currency": meta.get("currency"),
                })
        included = list(seen.values())
    if not requested:
        requested = included + [{k: v for k, v in item.items() if k != "phase"}
                                for item in preflight]
    if not scenarios:
        seen_scenarios = set()
        for _job, meta in parsed_jobs:
            key = meta.get("scenario_key")
            if key is not None and key not in seen_scenarios:
                scenarios.append({"key": key, "method": meta.get("method")})
                seen_scenarios.add(key)

    included_by_id = {item.get("deal_id"): item for item in included
                      if item.get("deal_id") is not None}
    records = {}
    failures_by_deal: dict[int, list[dict]] = {}
    unattributed_errors = []

    def fail(deal_id, scenario_key, reason, job=None):
        item = {"scenario_key": scenario_key, "reason": reason}
        if job is not None:
            item.update({"job_id": job.id, "label": job.label})
            job_errors.append({
                "job_id": job.id, "label": job.label,
                "deal_id": deal_id, "scenario_key": scenario_key,
                "error": reason,
            })
        if deal_id is None:
            unattributed_errors.append(item)
        else:
            failures_by_deal.setdefault(deal_id, []).append(item)

    for job, meta in parsed_jobs:
        deal_id = meta.get("deal_id")
        scenario_key = meta.get("scenario_key")
        if deal_id is None or scenario_key is None:
            fail(deal_id, scenario_key, "Métadonnées de job VaR incomplètes.", job)
            continue
        pair = (scenario_key, deal_id)
        if pair in records:
            fail(deal_id, scenario_key, "Job VaR dupliqué pour ce deal et ce scénario.", job)
            continue
        if job.status != "done":
            fail(deal_id, scenario_key, job.error or "Valorisation non terminée.", job)
            records[pair] = None
            continue
        try:
            result = json.loads(job.result_json or "{}")
            delta_pts = float(result["price"]) - float(meta["mtm_before"])
            delta_eur = (delta_pts * float(meta["nominal"]) * float(meta["fx_rate"])
                         * float(meta.get("position_sign", 1.0)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            fail(deal_id, scenario_key, f"Résultat de job VaR inexploitable : {exc}", job)
            records[pair] = None
            continue
        records[pair] = delta_eur

    # A missing matrix cell is just as incomplete as an explicitly failed job.
    for scenario in scenarios:
        key = scenario.get("key")
        for deal_id in included_by_id:
            if (key, deal_id) not in records:
                fail(deal_id, key, "Valorisation absente pour ce scénario.")

    runtime_exclusions = []
    for deal_id, failures in failures_by_deal.items():
        deal = included_by_id.get(deal_id, {"deal_id": deal_id, "reference": str(deal_id)})
        runtime_exclusions.append({
            **deal,
            "phase": "calculation",
            "reason": f"{len(failures)} valorisation(s) échouée(s) ou absente(s).",
            "failures": failures,
        })
    exclusions = preflight + runtime_exclusions
    failed_ids = set(failures_by_deal)
    effective_ids = [deal_id for deal_id in included_by_id if deal_id not in failed_ids]

    def scope_result(deal_ids: list[int]) -> dict | None:
        if not deal_ids or not scenarios:
            return None
        buckets = []
        for scenario in scenarios:
            key = scenario.get("key")
            values = [records.get((key, deal_id)) for deal_id in deal_ids]
            if any(value is None for value in values):
                return None
            buckets.append({
                "scenario_key": key,
                "method": scenario.get("method"),
                "delta_eur": sum(values),
            })
        hist = [b["delta_eur"] for b in buckets if b["method"] == "historical"]
        param = [b["delta_eur"] for b in buckets if b["method"] == "parametric"]
        return {
            "historical": aggregate_var(hist, confidence) if hist else None,
            "parametric": aggregate_var(param, confidence) if param else None,
            "worst_scenarios": sorted(
                [{**b, "delta_eur": round(b["delta_eur"], 2)} for b in buckets],
                key=lambda item: item["delta_eur"],
            )[:10],
        }

    global_complete = not exclusions and not unattributed_errors
    global_scope = scope_result(effective_ids) if global_complete else None
    if global_scope is None:
        global_complete = False

    reduced_scope = None
    if not global_complete and effective_ids and not unattributed_errors:
        reduced = scope_result(effective_ids)
        if reduced is not None:
            reduced_scope = {
                "label": "VaR du périmètre calculable — hors exclusions",
                "status": "complete",
                "included_deals": [included_by_id[deal_id] for deal_id in effective_ids],
                "excluded_deals": exclusions,
                **reduced,
            }

    requested_count = len(requested)
    effective_count = len(effective_ids)
    coverage = {
        "requested_deals": requested_count,
        "included_deals": effective_count,
        "excluded_deals": len(exclusions),
        "deal_coverage_pct": (
            round(100.0 * effective_count / requested_count, 2)
            if requested_count else None
        ),
    }
    return {
        "publication_status": "complete" if global_complete else "incomplete",
        "global_status": "complete" if global_complete else "incomplete",
        # Backwards-compatible locations intentionally stay empty when the
        # requested portfolio is incomplete.  An older UI therefore cannot
        # accidentally display the reduced scope as the global VaR.
        "historical": global_scope["historical"] if global_scope else None,
        "parametric": global_scope["parametric"] if global_scope else None,
        "worst_scenarios": global_scope["worst_scenarios"] if global_scope else [],
        "reduced_scope": reduced_scope,
        "coverage": coverage,
        "excluded_deals": exclusions,
        "job_errors": job_errors[:20],
        "unattributed_errors": unattributed_errors,
    }


def _launch_var_study(deals: list[Deal], session: Session, user_id: int,
                       label: str, body: VarRequest) -> dict:
    if not deals:
        raise HTTPException(422, "Aucun deal actif dans cette sélection.")
    requested_deals = [_deal_descriptor(deal) for deal in deals]
    bases = []
    skipped = []
    tickers: set[str] = set()
    for d in deals:
        base = build_deal_scenario_base(d, session, body.n_paths_per_scenario)
        if base.get("skipped"):
            skipped.append({**_deal_descriptor(d), "reason": base["reason"]})
            continue
        fx_rate = fx_rate_to(d.devise, "EUR")
        if fx_rate is None:
            # A VaR is a loss expressed in euros. Converting at parity because
            # the rate was missing understates the tail by whatever the real
            # rate happens to be — silently, and precisely on the figure a
            # limit is checked against. Skipped and named, like any other
            # deal this run cannot value.
            skipped.append({**_deal_descriptor(d),
                            "reason": f"Taux de change {d.devise}/EUR indisponible."})
            continue
        base["fx_rate"] = fx_rate
        base["currency"] = d.devise
        # Carried into each job's _meta so the aggregation, which runs long
        # after the deal rows are out of scope, still knows which way the
        # position points. A book of offsetting longs and shorts otherwise
        # reports the sum of their risks instead of the net.
        base["position_sign"] = position_sign(d)
        bases.append(base)
        tickers.update(base["tickers"])

    included_deals = [{
        "deal_id": base["deal_id"], "reference": base["reference"],
        "nominal": base["nominal"], "currency": base.get("currency"),
    } for base in bases]
    common_params = {
        "method": body.method, "confidence": body.confidence,
        "horizon_days": body.horizon_days, "lookback_years": body.lookback_years,
        "n_deals": len(bases), "max_workers": body.max_workers,
        "requested_deals": requested_deals,
        "included_deals": included_deals,
        "preflight_exclusions": skipped,
        "data_providers": sorted({
            base.get("data_provider") for base in bases
            if base.get("data_provider")
        }),
    }
    if not bases:
        common_params.update({
            "n_scenarios_historical": 0,
            "n_scenarios_parametric": 0,
            "scenarios": [],
        })
        batch = enqueue_batch(
            session, user_id, "var_scenario", label,
            job_payloads=[], job_labels=[], params=common_params,
        )
        result_summary = _aggregate_var_jobs([], common_params)
        batch.status = "failed"
        batch.finished_at = datetime.utcnow()
        batch.result_summary_json = json.dumps(result_summary)
        session.add(batch)
        session.commit()
        return {
            "batch_id": batch.id, "status": batch.status, "total_jobs": 0,
            "deals_included": 0, "deals_skipped": skipped, "n_scenarios": 0,
        }

    ticker_list = sorted(tickers)
    # Buffer past the requested lookback for the rolling vol/corr window
    # (generate_historical_scenarios/calibrate_comovement need ~1 month of
    # history before the window they actually use starts).
    start = (date.today() - timedelta(days=round(body.lookback_years * 365.25) + 60)).isoformat()
    scenarios = []
    if ticker_list:
        px_data = load_hist_prices(
            ticker_list, start, date.today().isoformat(), adjusted=True)
        if "error" in px_data:
            raise HTTPException(422, px_data["error"])
        dates_list, prices = px_data["dates"], px_data["prices"]
        common_params["market_data"] = {
            key: px_data.get(key) for key in (
                "provider", "price_type", "adjusted", "requested_start",
                "requested_end", "asof_effective", "effective_dates",
                "age_sessions", "warnings", "fetched_at",
            ) if key in px_data
        }
        if body.method in ("historical", "both"):
            scenarios += generate_historical_scenarios(
                prices, dates_list, ticker_list, lookback_years=body.lookback_years,
                horizon_days=body.horizon_days)
        if body.method in ("parametric", "both"):
            scenarios += generate_parametric_scenarios(
                prices, dates_list, ticker_list, n_scenarios=body.n_parametric,
                horizon_days=body.horizon_days)
    else:
        # A book made only of fixed receivables has exactly zero market VaR.
        # Materialize one scenario per requested method so the usual complete
        # aggregation path publishes that zero with full coverage.
        if body.method in ("historical", "both"):
            scenarios.append(MarketScenario(
                key="fixed-historical", label="Créances à régler",
                method="historical"))
        if body.method in ("parametric", "both"):
            scenarios.append(MarketScenario(
                key="fixed-parametric", label="Créances à régler",
                method="parametric"))
    if not scenarios:
        raise HTTPException(422, "Historique de prix insuffisant pour générer des scénarios "
                                 f"(lookback demandé : {body.lookback_years} an(s))")

    estimate = estimate_var_portfolio(bases, len(scenarios), body.max_workers)
    confirmation_payload = {
        "deal_ids": [base["deal_id"] for base in bases],
        "method": body.method, "confidence": body.confidence,
        "horizon_days": body.horizon_days, "lookback_years": body.lookback_years,
        "n_parametric": body.n_parametric,
        "n_paths_per_scenario": body.n_paths_per_scenario,
        "max_workers": body.max_workers, "estimate": estimate,
    }
    confirmation_token = canonical_fingerprint(confirmation_payload)
    if estimate["hard_refusal"]:
        raise HTTPException(422, detail={
            "code": "COMPUTE_BUDGET_EXCEEDED",
            "message": "VaR refusée avant soumission : plafond de calcul dépassé.",
            "estimate": estimate,
        })
    if (estimate["confirmation_required"]
            and body.confirmation_token != confirmation_token):
        raise HTTPException(409, detail={
            "code": "COMPUTE_CONFIRMATION_REQUIRED",
            "message": "Cette VaR est lourde et requiert une confirmation explicite.",
            "confirmation_token": confirmation_token,
            "estimate": estimate,
        })

    job_payloads, job_labels = [], []
    for scenario in scenarios:
        for base in bases:
            payload = apply_scenario_to_deal_base(base, scenario)
            payload["_meta"] = {
                "scenario_key": scenario.key, "method": scenario.method,
                "deal_id": base["deal_id"], "reference": base["reference"],
                "mtm_before": base["mtm_before"],
                "nominal": base["nominal"], "fx_rate": base["fx_rate"],
                "currency": base.get("currency"),
                "position_sign": base["position_sign"],
            }
            job_payloads.append(payload)
            job_labels.append(f"{scenario.label} / {base['reference']}")

    batch = enqueue_batch(
        session, user_id, "var_scenario", label,
        job_payloads=job_payloads, job_labels=job_labels,
        params={
            **common_params,
            "cost_estimate": estimate,
            "job_timeout_seconds": 300.0,
            "n_scenarios_historical": sum(1 for s in scenarios if s.method == "historical"),
            "n_scenarios_parametric": sum(1 for s in scenarios if s.method == "parametric"),
            "scenarios": [
                {"key": s.key, "method": s.method, "label": s.label}
                for s in scenarios
            ],
        },
    )
    return {
        "batch_id": batch.id, "status": batch.status, "total_jobs": batch.total_jobs,
        "deals_included": len(bases), "deals_skipped": skipped,
        "n_scenarios": len(scenarios), "cost_estimate": estimate,
    }


@router.post("/var-global", status_code=202)
def launch_var_global(
    body: VarRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    statement = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    if getattr(current, "role", "user") != "admin":
        statement = statement.where(Deal.user_id == current.id)
    deals = session.exec(statement).all()
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
    if not p or (getattr(current, "role", "user") != "admin" and p.user_id != current.id):
        raise HTTPException(404, "Portefeuille introuvable")
    from .portfolios import _portfolio_deals
    deals = _portfolio_deals(session, portfolio_id, ("actif", "en_reglement"))
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
        cached = json.loads(batch.result_summary_json)
        # A legacy partial summary has no publication status.  Rebuild it when
        # failures are known so it can no longer leak a partial portfolio VaR.
        if cached.get("publication_status") or batch.failed_jobs == 0:
            row["result"] = cached
            return row

    jobs = session.exec(select(ComputeJob).where(ComputeJob.batch_id == batch_id)).all()
    result_summary = _aggregate_var_jobs(jobs, row["params"])
    if result_summary["publication_status"] == "incomplete" and batch.status != "cancelled":
        batch.status = "failed"
    batch.result_summary_json = json.dumps(result_summary)
    session.add(batch)
    session.commit()

    row["status"] = batch.status
    row["result"] = result_summary
    return row
