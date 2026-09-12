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
import uuid
from sqlalchemy import or_, update
from sqlmodel import Session, select, delete
from ...db.models import ComputeBatch, ComputeJob


DEFAULT_LEASE_SECONDS = 60


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
        cost_estimate_json=json.dumps((params or {}).get("cost_estimate") or {}),
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


def claim_next_batch(session: Session, worker_name: str,
                     stale_after_seconds: int = DEFAULT_LEASE_SECONDS) -> Optional[ComputeBatch]:
    """Atomically claims the oldest queued batch — or a 'running' one whose
    claim has gone stale (the worker that had it presumably crashed) — so a
    dead worker never permanently strands a batch. Returns None if nothing
    is claimable."""
    stale_before = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
    candidates = session.exec(
        select(ComputeBatch.id, ComputeBatch.status, ComputeBatch.claimed_at,
               ComputeBatch.lease_expires_at)
        .where(ComputeBatch.status.in_(["queued", "running"]))
        .order_by(ComputeBatch.created_at)
    ).all()
    now = datetime.utcnow()
    for batch_id, status, claimed_at, lease_expires_at in candidates:
        stale = status == "running" and (
            (lease_expires_at is not None and lease_expires_at < now)
            or (lease_expires_at is None and claimed_at is not None
                and claimed_at < stale_before)
        )
        if status != "queued" and not stale:
            continue
        token = uuid.uuid4().hex
        if status == "queued":
            guard = ComputeBatch.status == "queued"
        else:
            guard = (
                (ComputeBatch.status == "running")
                & or_(
                    ComputeBatch.lease_expires_at < now,
                    (ComputeBatch.lease_expires_at == None)  # noqa: E711
                    & (ComputeBatch.claimed_at < stale_before),
                )
            )
        claimed = session.exec(
            update(ComputeBatch)
            .where(ComputeBatch.id == batch_id, guard)
            .values(
                status="running", worker_name=worker_name,
                claimed_at=now, heartbeat_at=now, lease_token=token,
                lease_expires_at=now + timedelta(seconds=stale_after_seconds),
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.rollback()
            continue
        # A reclaimed batch may contain jobs left in `running` by its dead
        # owner.  Their old lease can no longer write a result.
        session.exec(
            update(ComputeJob)
            .where(ComputeJob.batch_id == batch_id, ComputeJob.status == "running")
            .values(status="queued", lease_token=None, started_at=None)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        batch = session.get(ComputeBatch, batch_id)
        if batch.started_at is None:
            batch.started_at = now
            session.add(batch)
            session.commit()
            session.refresh(batch)
        return batch
    return None


def renew_lease(session: Session, batch_id: int, lease_token: str,
                lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
    now = datetime.utcnow()
    result = session.exec(
        update(ComputeBatch)
        .where(ComputeBatch.id == batch_id, ComputeBatch.status == "running",
               ComputeBatch.lease_token == lease_token,
               ComputeBatch.lease_expires_at >= now)
        .values(heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds))
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount == 1


def lease_is_active(session: Session, batch_id: int, lease_token: str) -> bool:
    now = datetime.utcnow()
    return session.exec(
        select(ComputeBatch.id).where(
            ComputeBatch.id == batch_id, ComputeBatch.status == "running",
            ComputeBatch.lease_token == lease_token,
            ComputeBatch.lease_expires_at >= now,
        )
    ).first() is not None


def pending_jobs(session: Session, batch_id: int, limit: int | None = None,
                 lease_token: str | None = None) -> list[ComputeJob]:
    """Jobs still queued for this batch — excludes ones a previous, crashed
    worker had already marked done/failed before dying, so a requeued batch
    doesn't redo finished work."""
    query = (
        select(ComputeJob)
        .where(ComputeJob.batch_id == batch_id, ComputeJob.status == "queued")
        .order_by(ComputeJob.job_index)
    )
    if limit is not None:
        query = query.limit(max(1, limit))
    jobs = session.exec(query).all()
    if lease_token:
        now = datetime.utcnow()
        claimed_jobs = []
        for job in jobs:
            claimed = session.exec(
                update(ComputeJob)
                .where(ComputeJob.id == job.id, ComputeJob.status == "queued")
                .values(status="running", lease_token=lease_token,
                        attempt=ComputeJob.attempt + 1, started_at=now)
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount == 1:
                claimed_jobs.append(job.id)
        session.commit()
        return [session.get(ComputeJob, job_id) for job_id in claimed_jobs]
    return jobs


def record_job_result(session: Session, job_id: int, ok: bool,
                       result: Optional[dict], error: Optional[str],
                       lease_token: str | None = None) -> bool:
    """Also bumps the PARENT batch's completed_jobs/failed_jobs counters —
    these are what a caller polls mid-run for a progress bar (see
    api/var.py, api/compute.py), so they must move as jobs land, not just
    once at finalize_batch(). One session/commit per call, from the
    worker's single-threaded result-collection loop (as_completed() only
    yields one future at a time) — no concurrent writer to race against."""
    job = session.get(ComputeJob, job_id)
    if not job:
        return False
    batch = session.get(ComputeBatch, job.batch_id)
    if not batch:
        return False
    if lease_token is not None:
        if (batch.status != "running" or batch.lease_token != lease_token
                or batch.lease_expires_at is None
                or batch.lease_expires_at < datetime.utcnow()
                or job.status != "running" or job.lease_token != lease_token):
            session.rollback()
            return False
    elif job.status in ("done", "failed", "cancelled"):
        return False
    job.status = "done" if ok else "failed"
    job.result_json = json.dumps(result or {})
    job.error = error
    job.finished_at = datetime.utcnow()
    session.add(job)

    if ok:
        batch.completed_jobs += 1
    else:
        batch.failed_jobs += 1
    session.add(batch)

    session.commit()
    return True


def finalize_batch(session: Session, batch_id: int, result_summary: Optional[dict] = None,
                   lease_token: str | None = None) -> Optional[ComputeBatch]:
    """Rolls every job's terminal status up into the batch's own status —
    call once every job of the batch has been dispatched (not necessarily
    completed successfully; failed jobs are still terminal). result_summary,
    if given, is whatever kind-specific aggregation the caller computed
    (e.g. VaR/ES percentiles across scenario jobs) — this module has no
    opinion on what a batch's jobs mean, only on their lifecycle.

    A batch an admin cancelled mid-run (api/compute.py's admin_stop_batch)
    is left untouched here. The executor stops its owned child processes as
    soon as the worker observes the cancellation; any late callback is also
    rejected by the lease token, so the admin's decision cannot be silently
    overwritten back to completed/failed."""
    batch = session.get(ComputeBatch, batch_id)
    if not batch:
        return None
    if batch.status == "cancelled":
        return batch
    if lease_token is not None and (
            batch.lease_token != lease_token or batch.lease_expires_at is None
            or batch.lease_expires_at < datetime.utcnow()):
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
    batch.lease_expires_at = None
    if result_summary is not None:
        batch.result_summary_json = json.dumps(result_summary)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


# ── Admin-triggered lifecycle overrides (api/compute.py's admin_* routes,
# AdminComputeView.vue) — every user's batches, not just the caller's own. ──

def cancel_batch(session: Session, batch_id: int) -> Optional[ComputeBatch]:
    """Requests cancellation of any non-terminal batch.

    A live worker observes the lost lease on its next polling tick and stops
    its active executor processes. finalize_batch() and late result writes
    no-op as a second line of defence. Returns None if the batch doesn't
    exist or is already terminal.
    """
    batch = session.get(ComputeBatch, batch_id)
    if not batch or batch.status not in ("queued", "running"):
        return None
    batch.status = "cancelled"
    batch.cancel_requested_at = datetime.utcnow()
    batch.lease_expires_at = None
    batch.finished_at = datetime.utcnow()
    session.exec(
        update(ComputeJob)
        .where(ComputeJob.batch_id == batch_id,
               ComputeJob.status.in_(["queued", "running"]))
        .values(status="cancelled", finished_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
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
    failed_jobs = session.exec(
        select(ComputeJob).where(ComputeJob.batch_id == batch_id,
                                 ComputeJob.status.in_(["failed", "cancelled"]))
    ).all()
    # A VaR can be failed because its requested scope contained preflight
    # exclusions even though every submitted job succeeded.  There is then
    # nothing for the worker to retry; re-queuing it would only loop back to the
    # same incomplete publication state.
    if not failed_jobs:
        return None
    for j in failed_jobs:
        j.status = "queued"
        j.error = None
        j.result_json = "{}"
        j.started_at = None
        j.finished_at = None
        session.add(j)
    batch.status = "queued"
    batch.failed_jobs = 0
    batch.claimed_at = None
    batch.heartbeat_at = None
    batch.lease_token = None
    batch.lease_expires_at = None
    batch.cancel_requested_at = None
    batch.worker_name = None
    batch.finished_at = None
    # The previous summary describes the failed attempt.  It must be rebuilt
    # after the retried jobs land, otherwise callers keep seeing stale VaR/ES.
    batch.result_summary_json = "{}"
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
