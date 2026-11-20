"""Interactive pricing as cancellable jobs with a deadline (P1-4).

Same calculations as POST /api/price, /api/price/in-life and
/api/price/implied-funding, and since 20/11 as the Pricer's analyses
(profile, paths, probabilities, backtest and comparator, Mark to Future and
its drill-down, solver, grid), run by core/compute/interactive.py in a worker
process: the request is validated here, the job id comes back at once, the
screen polls it and can cancel it. The synchronous routes stay for the other
callers (booking, AO, scripts, tests). The stress scenarios and the MtF
comparison, which run their own process pool, are queued too but run in a
server thread (see interactive.POOL_ANALYSES).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..core.compute.interactive import QueueFull, get_runner
from ..core.schemas import (BacktestCompareRequest, BacktestRequest, GridRequest, MtfDrilldownRequest,
                            MtfComparisonRequest, MtfRequest, PathsRequest, PricingRequest, ProbaRequest, ProfileRequest, ScenarioRequest,
                            SolverRequest)
from ..db.models import User
from .auth import get_current_pricer
from .inlife import ImpliedFundingRequest, InLifePricingRequest
from .contracts import ContractRoute, returns
from .responses import PricingJob

router = APIRouter(prefix="/api/price/jobs", tags=["pricing"], route_class=ContractRoute)

Pricer = Annotated[User, Depends(get_current_pricer)]


def _submit(kind, request, current):
    try:
        return get_runner().submit(kind, request, current.id)
    except QueueFull as error:
        raise HTTPException(429, str(error)) from error


@router.post("/price", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_price(req: PricingRequest, current: Pricer):
    return _submit("price", req, current)


@router.post("/in-life", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_in_life(req: InLifePricingRequest, current: Pricer):
    return _submit("in_life", req, current)


@router.post("/implied-funding", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_implied_funding(req: ImpliedFundingRequest, current: Pricer):
    return _submit("implied_funding", req, current)


@router.post("/profile", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_profile(req: ProfileRequest, current: Pricer):
    return _submit("profile", req, current)


@router.post("/paths", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_paths(req: PathsRequest, current: Pricer):
    return _submit("paths", req, current)


@router.post("/proba", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_proba(req: ProbaRequest, current: Pricer):
    return _submit("proba", req, current)


@router.post("/backtest", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_backtest(req: BacktestRequest, current: Pricer):
    return _submit("backtest", req, current)


@router.post("/backtest-compare", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_backtest_compare(req: BacktestCompareRequest, current: Pricer):
    return _submit("backtest_compare", req, current)


@router.post("/mtf", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_mtf(req: MtfRequest, current: Pricer):
    return _submit("mtf", req, current)


@router.post("/mtf-drilldown", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_mtf_drilldown(req: MtfDrilldownRequest, current: Pricer):
    return _submit("mtf_drilldown", req, current)


@router.post("/solve", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_solve(req: SolverRequest, current: Pricer):
    return _submit("solve", req, current)


@router.post("/grid", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_grid(req: GridRequest, current: Pricer):
    return _submit("grid", req, current)


@router.post("/scenarios", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_scenarios(req: ScenarioRequest, current: Pricer):
    return _submit("scenarios", req, current)


@router.post("/mtf-compare", status_code=202, responses=returns(PricingJob, status_code=202))
def submit_mtf_compare(req: MtfComparisonRequest, current: Pricer):
    return _submit("mtf_compare", req, current)


_GONE = "Calcul introuvable ou expiré."


@router.get("/{job_id}", responses=returns(PricingJob))
def job_status(job_id: str, current: Pricer):
    state = get_runner().status(job_id, current.id)
    if state is None:
        raise HTTPException(404, _GONE)
    return state


@router.delete("/{job_id}", responses=returns(PricingJob))
def cancel_job(job_id: str, current: Pricer):
    state = get_runner().cancel(job_id, current.id)
    if state is None:
        raise HTTPException(404, _GONE)
    return state
