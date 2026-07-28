"""Thin API surface over the generic compute module (core/compute/) — enqueue
a batch, poll its status/results. Deliberately does NOT execute anything
itself: a batch sits in `queued` until the worker daemon
(backend/scripts/run_compute_worker.py, started separately by Philippe, same
convention as run.py) picks it up. See core/compute/queue_store.py for the
lifecycle this wraps.

Only `kind="payscript_reprice"` is accepted from this endpoint for now — the
only pricer safe to expose broadly to any authenticated user today (same
sandboxed PayScript execution every other pricing endpoint already runs).
An external-pricer kind (core/compute/pricers/external.py) would need its
own authorization story before being reachable here — not built yet, no
client onboarded."""
from __future__ import annotations
import json
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import ComputeBatch, ComputeJob, User
from .auth import get_current_user, get_current_admin
from ..core.compute.queue_store import enqueue_batch, cancel_batch, relaunch_batch, delete_batch

router = APIRouter(prefix="/api/compute", tags=["compute"])

_ALLOWED_KINDS = {"payscript_reprice"}


class ComputeJobIn(BaseModel):
    label: str = ""
    payload: dict


class ComputeBatchCreate(BaseModel):
    kind: str = "payscript_reprice"
    label: str = ""
    jobs: List[ComputeJobIn]
    max_workers: int = 4
    use_processes: bool = True


def _batch_row(b: ComputeBatch) -> dict:
    return {
        "id": b.id, "kind": b.kind, "label": b.label, "status": b.status,
        "total_jobs": b.total_jobs, "completed_jobs": b.completed_jobs, "failed_jobs": b.failed_jobs,
        "params": json.loads(b.params_json) if b.params_json else {},
        "result_summary": json.loads(b.result_summary_json) if b.result_summary_json else {},
        "worker_name": b.worker_name,
        "claimed_at": b.claimed_at.isoformat() if b.claimed_at else None,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
        "created_at": b.created_at.isoformat(),
    }


def _job_row(j: ComputeJob) -> dict:
    return {
        "id": j.id, "job_index": j.job_index, "label": j.label, "status": j.status,
        "result": json.loads(j.result_json) if j.result_json else {},
        "error": j.error,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.post("/batches", status_code=201)
def create_batch(
    body: ComputeBatchCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if body.kind not in _ALLOWED_KINDS:
        raise HTTPException(422, f"Type de batch non autorisé: {body.kind!r} "
                                 f"(autorisés: {sorted(_ALLOWED_KINDS)})")
    if not body.jobs:
        raise HTTPException(422, "Au moins un job est requis")

    batch = enqueue_batch(
        session, current.id, body.kind, body.label,
        job_payloads=[j.payload for j in body.jobs],
        job_labels=[j.label for j in body.jobs],
        params={"max_workers": body.max_workers, "use_processes": body.use_processes},
    )
    return _batch_row(batch)


@router.get("/batches")
def list_batches(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    batches = session.exec(
        select(ComputeBatch).where(ComputeBatch.user_id == current.id)
        .order_by(ComputeBatch.created_at.desc())
    ).all()
    return [_batch_row(b) for b in batches]


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    batch = session.get(ComputeBatch, batch_id)
    if not batch or batch.user_id != current.id:
        raise HTTPException(404, "Batch introuvable")
    jobs = session.exec(
        select(ComputeJob).where(ComputeJob.batch_id == batch_id)
        .order_by(ComputeJob.job_index)
    ).all()
    row = _batch_row(batch)
    row["jobs"] = [_job_row(j) for j in jobs]
    return row


# ── Admin: manage every batch, any owner (see AdminComputeView.vue). The
# actual lifecycle mutations live in queue_store.py (cancel_batch/
# relaunch_batch/delete_batch) — same module as the rest of the batch
# lifecycle, and testable the way the rest of this suite already tests
# queue_store directly, without going through FastAPI. ─────────────────────

@router.get("/admin/batches")
def admin_list_batches(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    batches = session.exec(select(ComputeBatch).order_by(ComputeBatch.created_at.desc())).all()
    owners: dict[int, str] = {}

    def owner_name(uid: int) -> str:
        if uid not in owners:
            u = session.get(User, uid)
            owners[uid] = u.username if u else "?"
        return owners[uid]

    return [{**_batch_row(b), "user_id": b.user_id, "owner": owner_name(b.user_id)} for b in batches]


@router.delete("/admin/batches/{batch_id}", status_code=204)
def admin_delete_batch(
    batch_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    if not delete_batch(session, batch_id):
        raise HTTPException(404, "Batch introuvable")


@router.post("/admin/batches/{batch_id}/stop")
def admin_stop_batch(
    batch_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    existing = session.get(ComputeBatch, batch_id)
    if not existing:
        raise HTTPException(404, "Batch introuvable")
    batch = cancel_batch(session, batch_id)
    if batch is None:
        raise HTTPException(400, f"Batch déjà dans un état terminal ({existing.status})")
    return {**_batch_row(batch), "user_id": batch.user_id}


@router.post("/admin/batches/{batch_id}/relaunch")
def admin_relaunch_batch(
    batch_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    existing = session.get(ComputeBatch, batch_id)
    if not existing:
        raise HTTPException(404, "Batch introuvable")
    batch = relaunch_batch(session, batch_id)
    if batch is None:
        raise HTTPException(400, f"Batch non relançable dans son état actuel ({existing.status})")
    return {**_batch_row(batch), "user_id": batch.user_id}
