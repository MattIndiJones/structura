"""Authenticated, ephemeral optimizer runs. No shared result/session storage."""
import json
import logging
import threading
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlmodel import Session, select

from .auth import get_current_user
from ..db.database import get_session
from ..db.models import Underlying, User
from ..core.product_optimizer.capabilities import capabilities
from ..core.product_optimizer.contracts import OptimizationRequest
from ..core.product_optimizer.service import estimate_search, run_events

router = APIRouter(prefix="/api/product-optimizer", tags=["product-optimizer"],
                   dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)
# Resource admission only: never contains user input, candidates or results.
_capacity = threading.BoundedSemaphore(1)


class _Lease:
    def __init__(self):
        self.lock = threading.Lock()
        self.released = False

    def release(self):
        with self.lock:
            if not self.released:
                self.released = True
                _capacity.release()


def validate_catalogue(body, session):
    for underlying in body.market.underlyings:
        rows = session.exec(select(Underlying).where(
            Underlying.ticker == underlying.ticker, Underlying.active == True)).all()
        if not rows or {row.ccy for row in rows} != {underlying.currency}:
            raise HTTPException(422, f"Sous-jacent absent, inactif ou devise ambiguë : {underlying.ticker}.")


@router.get("/capabilities")
def get_capabilities():
    return capabilities()


@router.post("/estimate-search")
def estimate(body: OptimizationRequest, session: Annotated[Session, Depends(get_session)]):
    validate_catalogue(body, session)
    return estimate_search(body)


@router.post("/run")
async def run(body: OptimizationRequest, request: Request,
              current: Annotated[User, Depends(get_current_user)],
              session: Annotated[Session, Depends(get_session)]):
    validate_catalogue(body, session)
    estimate = estimate_search(body)
    if not estimate["allowed"]:
        raise HTTPException(422, " ".join(estimate["reasons"]))
    if not _capacity.acquire(blocking=False):
        raise HTTPException(429, "Un calcul Optimizer est déjà en cours sur ce serveur. Réessayez après sa fin.")
    lease = _Lease()
    actor = current.id
    logger.info("Product Optimizer started user=%s candidates=%s", actor, estimate["candidate_count"])

    async def stream():
        iterator = run_events(body)
        sentinel = object()
        try:
            while not await request.is_disconnected():
                # A cancelled HTTP request must not release capacity while its
                # current numerical call is still using memory/CPU.
                event = await anyio.to_thread.run_sync(lambda: next(iterator, sentinel))
                if event is sentinel:
                    break
                yield json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
        except Exception:
            logger.exception("Product Optimizer stream failed user=%s", actor)
            yield json.dumps({"type": "error", "message": "Recherche interrompue par une erreur serveur ; aucun résultat final validé."}) + "\n"
        finally:
            try:
                close = getattr(iterator, "close", None)
                if close:
                    close()
            finally:
                lease.release()
            logger.info("Product Optimizer finished user=%s", actor)

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
                             background=BackgroundTask(lease.release))
