"""Generic compute module (core/compute/) — executor parallelism/isolation
and the DB-backed queue lifecycle. Offline: in-memory SQLite, same fixture
style as test_portfolio_pnl.py/test_shocks.py.

Process-pool tests are the ones that actually prove the point (threads would
pass just as well on a toy payload and prove nothing about the GIL problem
this module exists to solve) — kept deliberately small (N=500-2000 paths)
so the suite stays fast despite the per-process spawn overhead on Windows."""
import math
import time
from datetime import datetime, timedelta

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.compute.executor import run_batch
from backend.app.core.compute.pricers.payscript import price_payscript_job
from backend.app.core.compute.queue_store import (
    enqueue_batch, claim_next_batch, pending_jobs, record_job_result, finalize_batch,
    cancel_batch, relaunch_batch, delete_batch,
)
from backend.app.db.models import ComputeBatch, ComputeJob, User
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import run_mc


CALL_SCRIPT = "PARAM K = 1.0\n\nAT MATURITY\n  PAY MAX(0, S[1] - K)\n"
UL = dict(name="S1", ticker="", ccy="EUR", sigma=0.20, q=0.0, v0=0.04, kappa=2.0,
          theta=0.04, xi=0.35, rho_h=-0.70, alpha=0.20, beta=0.5, rho=-0.30, nu=0.40,
          sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
CORR = [[1.0]]


def _payload(spot_mult=None):
    return {
        "script_text": CALL_SCRIPT, "underlyings": [UL], "corr": CORR,
        "r": 0.03, "T": 1.0, "n_paths": 2000, "model": "constant", "seed": 42,
        "user_params": {"K": 1.0}, "spot_mult": spot_mult,
    }


# ── executor.run_batch ───────────────────────────────────────────────

def test_run_batch_process_pool_matches_direct_run_mc():
    """A batch of one job, run through the real ProcessPoolExecutor path,
    must reprice to the same number a direct in-process run_mc call gives —
    proves the payload round-trips through pickling/a fresh worker process
    without silently changing the answer."""
    jobs = [(1, _payload())]
    results = run_batch("payscript_reprice", jobs, max_workers=1, use_processes=True)
    assert len(results) == 1
    assert results[0].ok, results[0].error

    direct = price_payscript_job(_payload())
    assert results[0].result["price"] == pytest.approx(direct["price"], abs=1e-9)


def test_run_batch_parallelizes_multiple_scenarios():
    """Several spot-shocked scenarios (the exact shape a VaR study will
    submit) all come back with distinct, monotonically increasing call
    prices as the spot shock rises — sanity-checks that each job actually
    received ITS OWN payload (not e.g. all workers silently sharing job #1's
    payload, which pickling-by-reference bugs can cause)."""
    shocks = [0.8, 0.9, 1.0, 1.1, 1.2]
    jobs = [(i, _payload(spot_mult=[s])) for i, s in enumerate(shocks)]
    results = run_batch("payscript_reprice", jobs, max_workers=4, use_processes=True)
    assert all(r.ok for r in results), [r.error for r in results if not r.ok]

    by_id = {r.job_id: r.result["price"] for r in results}
    prices = [by_id[i] for i in range(len(shocks))]
    assert prices == sorted(prices), f"call price must rise with spot: {prices}"


def test_run_batch_isolates_per_job_failure():
    """One job referencing an unknown kind must fail without preventing the
    other, valid jobs in the same batch from completing — same per-job
    isolation contract as api/shocks.py's _run_shock_on_book, one level up."""
    jobs = [(1, _payload()), (2, {"not": "a valid payscript payload"})]
    # job 2 goes through a bogus kind to force a clean, deterministic failure
    # (ValueError from _run_one's registry lookup) rather than relying on a
    # payscript-specific KeyError's exact message.
    results = run_batch("payscript_reprice", jobs, max_workers=2, use_processes=True)
    assert len(results) == 2
    by_id = {r.job_id: r for r in results}
    assert by_id[1].ok
    assert not by_id[2].ok
    assert by_id[2].error   # KeyError on the missing payload keys, surfaced as a message


def test_run_batch_unknown_kind_raises_per_job():
    results = run_batch("not_a_registered_kind", [(1, {})], max_workers=1, use_processes=True)
    assert len(results) == 1
    assert not results[0].ok
    assert "not_a_registered_kind" in results[0].error


def test_run_batch_empty_jobs_returns_empty():
    assert run_batch("payscript_reprice", [], max_workers=4) == []


# ── queue_store lifecycle ────────────────────────────────────────────

def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _make_user(s: Session) -> User:
    u = User(username="t", email="t@t.local", password_hash="x")
    s.add(u); s.commit(); s.refresh(u)
    return u


def test_enqueue_then_claim_then_complete():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "VaR test",
                          job_payloads=[_payload(), _payload()],
                          job_labels=["scenario A", "scenario B"])
    assert batch.status == "queued"
    assert batch.total_jobs == 2

    claimed = claim_next_batch(s, "worker-1")
    assert claimed.id == batch.id
    assert claimed.status == "running"
    assert claimed.worker_name == "worker-1"

    jobs = pending_jobs(s, batch.id)
    assert len(jobs) == 2
    assert [j.label for j in jobs] == ["scenario A", "scenario B"]

    for j in jobs:
        record_job_result(s, j.id, True, {"price": 0.08}, None)

    final = finalize_batch(s, batch.id, result_summary={"var_eur": 12345.0})
    assert final.status == "completed"
    assert final.completed_jobs == 2
    assert final.failed_jobs == 0
    assert final.finished_at is not None
    import json
    assert json.loads(final.result_summary_json)["var_eur"] == 12345.0


def test_finalize_marks_completed_with_failures_when_partial():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "partial",
                          job_payloads=[_payload(), _payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)
    record_job_result(s, jobs[1].id, False, None, "boom")

    final = finalize_batch(s, batch.id)
    assert final.status == "completed_with_failures"
    assert final.completed_jobs == 1
    assert final.failed_jobs == 1


def test_record_job_result_updates_batch_counters_incrementally():
    """Regression: completed_jobs/failed_jobs on the BATCH row must move as
    each job lands, not just once at finalize_batch() — a caller polling
    mid-run (a progress bar) reads exactly these two fields, and they used
    to stay at 0 for the whole run before jumping to 100% all at once."""
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "progress test",
                          job_payloads=[_payload(), _payload(), _payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)

    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)
    mid = s.get(type(batch), batch.id)
    assert mid.completed_jobs == 1
    assert mid.failed_jobs == 0

    record_job_result(s, jobs[1].id, False, None, "boom")
    mid = s.get(type(batch), batch.id)
    assert mid.completed_jobs == 1
    assert mid.failed_jobs == 1

    record_job_result(s, jobs[2].id, True, {"price": 0.09}, None)
    mid = s.get(type(batch), batch.id)
    assert mid.completed_jobs == 2
    assert mid.failed_jobs == 1


def test_finalize_marks_failed_when_all_jobs_fail():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "all fail",
                          job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, False, None, "boom")

    final = finalize_batch(s, batch.id)
    assert final.status == "failed"
    assert final.completed_jobs == 0
    assert final.failed_jobs == 1


def test_claim_next_batch_ignores_fresh_running_batch():
    """A batch another worker is actively (recently) working on must not be
    claimable by a second worker — only queued or STALE running batches
    are fair game."""
    s = _make_session()
    user = _make_user(s)
    enqueue_batch(s, user.id, "payscript_reprice", "in progress", job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")   # now running, claimed_at = now

    second_claim = claim_next_batch(s, "worker-2", stale_after_seconds=900)
    assert second_claim is None


def test_claim_next_batch_requeues_stale_running():
    """A batch whose worker died mid-run (claimed_at old enough) must be
    reclaimable by a fresh worker, so it isn't stranded forever."""
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "abandoned", job_payloads=[_payload()])
    claimed = claim_next_batch(s, "worker-dead")
    claimed.claimed_at = datetime.utcnow() - timedelta(seconds=1000)
    s.add(claimed); s.commit()

    reclaimed = claim_next_batch(s, "worker-alive", stale_after_seconds=900)
    assert reclaimed is not None
    assert reclaimed.id == batch.id
    assert reclaimed.worker_name == "worker-alive"


def test_claim_next_batch_none_when_nothing_queued():
    s = _make_session()
    assert claim_next_batch(s, "worker-1") is None


# ── Admin lifecycle overrides (cancel/relaunch/delete) ───────────────────

def test_cancel_batch_stops_a_queued_batch():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "to cancel", job_payloads=[_payload()])

    cancelled = cancel_batch(s, batch.id)
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    # no longer claimable
    assert claim_next_batch(s, "worker-1") is None


def test_cancel_batch_refused_on_terminal_batch():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "already done", job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)
    finalize_batch(s, batch.id)

    assert cancel_batch(s, batch.id) is None


def test_cancel_batch_none_for_unknown_id():
    s = _make_session()
    assert cancel_batch(s, 9999) is None


def test_finalize_batch_does_not_overwrite_a_cancelled_batch():
    """Regression: an admin cancelling a batch a live worker already claimed
    must survive that worker's own finalize_batch() call once its
    already-dispatched jobs land — otherwise the cancellation is silently
    undone back to completed/failed (see queue_store.finalize_batch's
    docstring)."""
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "cancelled mid-run",
                          job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)

    cancel_batch(s, batch.id)   # admin steps in before the worker calls finalize_batch
    final = finalize_batch(s, batch.id)
    assert final.status == "cancelled"


def test_relaunch_batch_requeues_only_failed_jobs():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "partial failure",
                          job_payloads=[_payload(), _payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)
    record_job_result(s, jobs[1].id, False, None, "boom")
    finalize_batch(s, batch.id)

    relaunched = relaunch_batch(s, batch.id)
    assert relaunched.status == "queued"
    assert relaunched.failed_jobs == 0
    assert relaunched.claimed_at is None
    assert relaunched.worker_name is None

    # the previously-failed job is retryable, the done one is left alone
    still_pending = pending_jobs(s, batch.id)
    assert len(still_pending) == 1
    assert still_pending[0].id == jobs[1].id

    reclaimed = claim_next_batch(s, "worker-2")
    assert reclaimed.id == batch.id


def test_relaunch_batch_refused_on_fully_completed_batch():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "all ok", job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")
    jobs = pending_jobs(s, batch.id)
    record_job_result(s, jobs[0].id, True, {"price": 0.08}, None)
    finalize_batch(s, batch.id)

    assert relaunch_batch(s, batch.id) is None


def test_relaunch_batch_refused_while_still_running():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "in flight", job_payloads=[_payload()])
    claim_next_batch(s, "worker-1")
    assert relaunch_batch(s, batch.id) is None


def test_delete_batch_removes_batch_and_its_jobs():
    s = _make_session()
    user = _make_user(s)
    batch = enqueue_batch(s, user.id, "payscript_reprice", "to delete",
                          job_payloads=[_payload(), _payload()])
    batch_id = batch.id

    assert delete_batch(s, batch_id) is True
    assert s.get(ComputeBatch, batch_id) is None
    remaining = s.exec(select(ComputeJob).where(ComputeJob.batch_id == batch_id)).all()
    assert remaining == []


def test_delete_batch_false_for_unknown_id():
    s = _make_session()
    assert delete_batch(s, 9999) is False
