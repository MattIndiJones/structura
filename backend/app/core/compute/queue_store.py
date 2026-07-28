"""DB-backed job queue for the generic compute module. Same queued -> running
-> terminal lifecycle as a typical background-job table, with an atomic
claim so a single worker daemon (scripts/run_compute_worker.py) stays safe
even if accidentally started twice, and a stale-claim requeue so a worker
that crashed mid-batch doesn't strand it forever.

Not a distributed queue (no Celery/Redis) — deliberately: this module's
actual target is one family office's/small broker's own machine running one
worker process, not a trading floor's compute grid. SQLite is already this
app's only datastore (see CLAUDE.md/database.py) and that's fine here too,
with the same single-writer caveat that already applies to the rest of the
app."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import Optional
from sqlmodel import Session, select, delete
from ...db.models import ComputeBatch, ComputeJob


def enqueue_batch(
    session: Session,
    user_id: int,
    kind: str,
    label: str,
    job_payloads: list[dict],
    job_labels: Optional[list[str]] = None,
    params: Optional[dict] = None,
) -> ComputeBatch:
    """Creates a batch and every one of its jobs in `queued` state. Nothing
    starts executing here — a worker daemon picks it up via
    claim_next_batch()."""
    batch = ComputeBatch(
        user_id=user_id, kind=kind, label=label, status="queued",
        total_jobs=len(job_payloads), params_json=json.dumps(params or {}),
    )
    session.add(batch)
    session.flush()

    labels = job_labels or [str(i) for i in range(len(job_payloads))]
    for i, (payload, lbl) in enumerate(zip(job_payloads, labels)):
        session.add(ComputeJob(
            batch_id=batch.id, job_index=i, label=lbl,
            payload_json=json.dumps(payload), status="queued",
        ))
    session.commit()
    session.refresh(batch)
    return batch


def claim_next_batch(session: Session, worker_name: str, stale_after_seconds: int = 900) -> Optional[ComputeBatch]:
    """Atomically claims the oldest queued batch — or a 'running' one whose
    claim has gone stale (the worker that had it presumably crashed) — so a
    dead worker never permanently strands a batch. Returns None if nothing
    is claimable."""
    stale_before = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
    candidates = session.exec(
        select(ComputeBatch)
        .where(ComputeBatch.status.in_(["queued", "running"]))
        .order_by(ComputeBatch.created_at)
    ).all()
    batch = next(
        (b for b in candidates if b.status == "queued"
         or (b.status == "running" and b.claimed_at and b.claimed_at < stale_before)),
        None,
    )
    if not batch:
        return None
    batch.status = "running"
    batch.worker_name = worker_name
    batch.claimed_at = datetime.utcnow()
    batch.started_at = batch.started_at or datetime.utcnow()
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def pending_jobs(session: Session, batch_id: int) -> list[ComputeJob]:
    """Jobs still queued for this batch — excludes ones a previous, crashed
    worker had already marked done/failed before dying, so a requeued batch
    doesn't redo finished work."""
    return session.exec(
        select(ComputeJob)
        .where(ComputeJob.batch_id == batch_id, ComputeJob.status == "queued")
        .order_by(ComputeJob.job_index)
    ).all()


def record_job_result(session: Session, job_id: int, ok: bool,
                       result: Optional[dict], error: Optional[str]) -> None:
    """Also bumps the PARENT batch's completed_jobs/failed_jobs counters —
    these are what a caller polls mid-run for a progress bar (see
    api/var.py, api/compute.py), so they must move as jobs land, not just
    once at finalize_batch(). One session/commit per call, from the
    worker's single-threaded result-collection loop (as_completed() only
    yields one future at a time) — no concurrent writer to race against."""
    job = session.get(ComputeJob, job_id)
    if not job:
        return
    job.status = "done" if ok else "failed"
    job.result_json = json.dumps(result or {})
    job.error = error
    job.finished_at = datetime.utcnow()
    session.add(job)

    batch = session.get(ComputeBatch, job.batch_id)
    if batch:
        if ok:
            batch.completed_jobs += 1
        else:
            batch.failed_jobs += 1
        session.add(batch)

    session.commit()


def finalize_batch(session: Session, batch_id: int, result_summary: Optional[dict] = None) -> ComputeBatch:
    """Rolls every job's terminal status up into the batch's own status —
    call once every job of the batch has been dispatched (not necessarily
    completed successfully; failed jobs are still terminal). result_summary,
    if given, is whatever kind-specific aggregation the caller computed
    (e.g. VaR/ES percentiles across scenario jobs) — this module has no
    opinion on what a batch's jobs mean, only on their lifecycle.

    A batch an admin cancelled mid-run (api/compute.py's admin_stop_batch)
    is left untouched here: the worker's already-dispatched jobs keep
    running to completion (no cross-process cancel on Windows), but the
    admin's decision must win once they land, not get silently overwritten
    back to completed/failed."""
    batch = session.get(ComputeBatch, batch_id)
    if batch.status == "cancelled":
        return batch
    jobs = session.exec(select(ComputeJob).where(ComputeJob.batch_id == batch_id)).all()
    completed = sum(1 for j in jobs if j.status == "done")
    failed = sum(1 for j in jobs if j.status == "failed")
    batch.completed_jobs = completed
    batch.failed_jobs = failed
    if failed == 0 and completed == len(jobs) and jobs:
        batch.status = "completed"
    elif completed == 0:
        batch.status = "failed"
    else:
        batch.status = "completed_with_failures"
    batch.finished_at = datetime.utcnow()
    if result_summary is not None:
        batch.result_summary_json = json.dumps(result_summary)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


# ── Admin-triggered lifecycle overrides (api/compute.py's admin_* routes,
# AdminComputeView.vue) — every user's batches, not just the caller's own. ──

def cancel_batch(session: Session, batch_id: int) -> Optional[ComputeBatch]:
    """Stops a batch that hasn't reached a terminal state yet. Only takes
    effect immediately if the batch is still `queued` (never claimed) or a
    stale `running` one (its worker already died) — a batch a LIVE worker
    is mid-way through keeps running until that worker's current
    run_batch() call drains (no cross-process job-cancel on Windows), but
    finalize_batch() will no-op instead of overwriting the cancellation
    once that happens. Returns None if the batch doesn't exist or is
    already terminal."""
    batch = session.get(ComputeBatch, batch_id)
    if not batch or batch.status not in ("queued", "running"):
        return None
    batch.status = "cancelled"
    batch.finished_at = datetime.utcnow()
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


RELAUNCHABLE_STATUSES = {"failed", "completed_with_failures", "cancelled"}


def relaunch_batch(session: Session, batch_id: int) -> Optional[ComputeBatch]:
    """Re-queues a batch's FAILED jobs for a retry — done jobs are never
    redone, same resume contract claim_next_batch already gives a
    crash-abandoned batch. Refused (returns None) on anything not in
    RELAUNCHABLE_STATUSES: a fully `completed` batch has nothing left to
    redo, and `queued`/`running` are already live."""
    batch = session.get(ComputeBatch, batch_id)
    if not batch or batch.status not in RELAUNCHABLE_STATUSES:
        return None
    for j in session.exec(
        select(ComputeJob).where(ComputeJob.batch_id == batch_id, ComputeJob.status == "failed")
    ).all():
        j.status = "queued"
        j.error = None
        j.result_json = "{}"
        j.started_at = None
        j.finished_at = None
        session.add(j)
    batch.status = "queued"
    batch.failed_jobs = 0
    batch.claimed_at = None
    batch.worker_name = None
    batch.finished_at = None
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def delete_batch(session: Session, batch_id: int) -> bool:
    """Deletes a batch and every one of its jobs, regardless of status —
    if a live worker is still mid-run on it, record_job_result()/
    finalize_batch() already no-op gracefully on a missing job/batch row
    (see their `if not job/batch` guards), so this is safe even then."""
    batch = session.get(ComputeBatch, batch_id)
    if not batch:
        return False
    session.exec(delete(ComputeJob).where(ComputeJob.batch_id == batch_id))
    session.delete(batch)
    session.commit()
    return True
