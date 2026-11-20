"""Interactive pricing as cancellable jobs with a deadline (P1-4).

Same calculations as POST /api/price, /api/price/in-life and
/api/price/implied-funding, run by core/compute/interactive.py in a worker
process: the request is validated here, the job id comes back at once, the
screen polls it and can cancel it. The synchronous routes stay for the other
callers (booking, AO, scripts, tests).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..core.compute.interactive import QueueFull, get_runner
from ..core.schemas import PricingRequest
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
