"""Owned persistent research jobs and the compatible ephemeral streaming API."""
import json
import logging
import threading
import secrets
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
from ..services.optimizer_market import MarketReferenceRequest, load_optimizer_references
from ..db.underlyings_seed import seeded_asset_class
from ..services import optimizer_research as research
from sqlalchemy import func, or_

router = APIRouter(prefix="/api/product-optimizer", tags=["product-optimizer"],
                   dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)
# Resource admission only: never contains user input, candidates or results.
_capacity = threading.BoundedSemaphore(1)
_cancellations = {}
_cancellation_lock = threading.Lock()


class _Lease:
    def __init__(self, run_id, stopping):
        self.lock = threading.Lock()
        self.released = False
        self.run_id = run_id
        self.stopping = stopping

    def release(self):
        with self.lock:
            if not self.released:
                self.released = True
                self.stopping.set()
                with _cancellation_lock:
                    _cancellations.pop(self.run_id, None)
                _capacity.release()


def validate_catalogue(body, session):
    for underlying in body.market.underlyings:
        rows = session.exec(select(Underlying).where(
            Underlying.ticker == underlying.ticker, Underlying.active == True)).all()
        if not rows or {row.ccy for row in rows} != {underlying.currency}:
            raise HTTPException(422, f"Sous-jacent absent, inactif ou devise ambiguë : {underlying.ticker}.")
        kinds = {row.asset_class if row.asset_class != "unknown" else seeded_asset_class(row.ticker) for row in rows} - {"unknown"}
        if kinds and kinds != {underlying.asset_type}:
            raise HTTPException(422, f"Type action/indice incompatible avec le référentiel : {underlying.ticker}.")


@router.post("/market-reference")
def market_reference(body: MarketReferenceRequest, session: Annotated[Session, Depends(get_session)]):
    metadata = {}
    for ticker in body.tickers:
        rows = session.exec(select(Underlying).where(Underlying.ticker == ticker, Underlying.active == True)).all()
        if not rows or {row.ccy for row in rows} != {body.currency}:
            raise HTTPException(422, f"Sous-jacent absent, inactif ou devise ambiguë : {ticker}.")
        kinds = {row.asset_class if row.asset_class != "unknown" else seeded_asset_class(ticker) for row in rows} - {"unknown"}
        if len(kinds) > 1:
            raise HTTPException(422, f"Classification ambiguë dans le référentiel : {ticker}.")
        metadata[ticker] = {"asset_type": next(iter(kinds), None), "name": rows[0].label, "currency": body.currency}
    data = load_optimizer_references(body.tickers, body.pricing_date.isoformat())
    for asset in data["underlyings"]:
        asset.update(metadata[asset["ticker"]])
    return data


@router.post("/cancel/{run_id}")
def cancel_run(run_id: str, current: Annotated[User, Depends(get_current_user)]):
    with _cancellation_lock:
        owned = _cancellations.get(run_id)
        if owned is None or owned[0] != current.id:
            raise HTTPException(404, "Recherche absente ou terminée.")
        owned[1].set()
    return {"stopping": True}


@router.get("/capabilities")
def get_capabilities():
    return capabilities()


@router.post("/researches")
def create_research(body: research.ResearchCreate, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    previous=research.existing(session,body,current.id)
    if previous: return research.projection(previous)
    validate_catalogue(body.optimization,session)
    estimate=estimate_search(body.optimization)
    if not estimate["allowed"]: raise HTTPException(422," ".join(estimate["reasons"]))
    if not _capacity.acquire(blocking=False):
        raise HTTPException(429,"Un calcul Optimizer est déjà en cours. Retrouvez-le dans Recherches & pricings.")
    row=None
    try:
        row=research.create(session,body,current.id)
        response=research.projection(row)
        research.start(session.get_bind(),row,run_events,_capacity.release)
        return response
    except Exception:
        _capacity.release()
        if row:
            row.status="FAILED";row.error="Le calcul n’a pas pu démarrer. Reprenez la demande pour relancer."
            session.add(row);session.commit()
        raise


@router.get("/researches")
def list_researches(current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)], archived: bool=False,
                    q: str="", family: str="", status: str="", offset: int=0, limit: int=30):
    if offset<0 or not 1<=limit<=100: raise HTTPException(422,"Pagination invalide.")
    filters=[research.OptimizerResearch.user_id==current.id,research.OptimizerResearch.archived==archived]
    if family: filters.append(research.OptimizerResearch.product_family==family)
    if status:
        if status not in research.TERMINAL | {"RUNNING"}: raise HTTPException(422,"État inconnu.")
        filters.append(research.OptimizerResearch.status==status)
    if q.strip(): filters.append(or_(research.OptimizerResearch.title.contains(q.strip(),autoescape=True),
        research.OptimizerResearch.summary.contains(q.strip(),autoescape=True),research.OptimizerResearch.intention.contains(q.strip(),autoescape=True)))
    count=session.exec(select(func.count()).select_from(research.OptimizerResearch).where(*filters)).one()
    rows=session.exec(select(research.OptimizerResearch).where(*filters).order_by(research.OptimizerResearch.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items":[research.projection(row) for row in rows],"total":count,"offset":offset,"limit":limit}


@router.get("/researches/{research_id}")
def read_research(research_id: str, current: Annotated[User, Depends(get_current_user)],
                  session: Annotated[Session, Depends(get_session)]):
    return research.projection(research.owned(session,research_id,current.id),True)


@router.patch("/researches/{research_id}")
def archive_research(research_id: str, body: research.ArchiveChange,
                     current: Annotated[User, Depends(get_current_user)],session: Annotated[Session, Depends(get_session)]):
    row=research.owned(session,research_id,current.id)
    row.archived=body.archived;session.add(row);session.commit();session.refresh(row)
    return research.projection(row)


@router.post("/researches/{research_id}/cancel")
def cancel_research(research_id: str, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    row=research.owned(session,research_id,current.id)
    return {"stopping":research.cancel(row.id),"status":row.status}


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
    actor = current.id
    run_id = secrets.token_urlsafe(24)
    stopping = threading.Event()
    lease = _Lease(run_id, stopping)
    with _cancellation_lock:
        _cancellations[run_id] = (actor, stopping)
    logger.info("Product Optimizer started user=%s candidates=%s", actor, estimate["candidate_count"])

    async def stream():
        iterator = None
        sentinel = object()
        try:
            iterator = run_events(body, should_cancel=stopping.is_set)
            yield json.dumps({"type": "run_registered", "run_id": run_id}) + "\n"
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
            stopping.set()
            with _cancellation_lock:
                _cancellations.pop(run_id, None)
            try:
                close = getattr(iterator, "close", None)
                if close:
                    # Process cleanup may wait briefly for the owned worker pool.
                    # Finish it even when the HTTP task has already been cancelled.
                    with anyio.CancelScope(shield=True):
                        await anyio.to_thread.run_sync(close)
            finally:
                lease.release()
            logger.info("Product Optimizer finished user=%s", actor)

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
                             background=BackgroundTask(lease.release))
