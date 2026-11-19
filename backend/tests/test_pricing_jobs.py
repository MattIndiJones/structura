"""P1-4: interactive pricing in a worker process, with a deadline and
cancellation. These tests start real spawned processes."""
from __future__ import annotations

import logging
import os
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import pricing_jobs
from backend.app.api.auth import get_current_pricer
from backend.app.api.pricing import price_endpoint
from backend.app.core.compute import interactive
from backend.app.core.compute.interactive import InteractiveRunner, QueueFull
from backend.app.core.schemas import PricingRequest
from backend.tests import pricing_job_targets

SLOW = 30.0          # a calculation that would outlive every test


def _runner(**options):
    options.setdefault("target", pricing_job_targets.run)
    options.setdefault("warm_modules", ())
    return InteractiveRunner(**options).start()


@pytest.fixture(scope="module")
def runner():
    instance = _runner(workers=2)
    yield instance
    instance.shutdown()


def _running(runner, job_id, user, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runner.status(job_id, user)
        if state["status"] != "queued":
            return state
        time.sleep(0.05)
    raise AssertionError("le calcul n'a jamais démarré")


def test_a_job_runs_in_another_process_and_returns_its_result(runner):
    job = runner.submit("echo", {"N": 2000}, user_id=1)
    assert job["status"] == "queued" and job["job_id"]
    state = runner.wait(job["job_id"], 1, timeout=60)
    assert state["status"] == "done"
    assert state["result"]["request"] == {"N": 2000}
    assert state["result"]["pid"] != os.getpid()


def test_a_refusal_keeps_its_http_status(runner):
    job = runner.submit("refuse", None, user_id=2)
    state = runner.wait(job["job_id"], 2, timeout=60)
    assert (state["status"], state["status_code"], state["detail"]) == ("failed", 422, "Script invalide.")


def test_an_unexpected_error_is_a_500_and_its_traceback_is_logged(runner, caplog):
    with caplog.at_level(logging.ERROR, logger=interactive.__name__):
        job = runner.submit("boom", None, user_id=3)
        state = runner.wait(job["job_id"], 3, timeout=60)
    assert state["status"] == "failed" and state["status_code"] == 500
    assert "traceback" not in state                    # not sent to the screen
    assert any("calcul cassé" in r.getMessage() for r in caplog.records)


def test_cancelling_a_running_job_kills_its_worker_and_replaces_it(runner):
    job = runner.submit("sleep", SLOW, user_id=4)
    _running(runner, job["job_id"], 4)
    started = time.monotonic()
    runner.cancel(job["job_id"], 4)
    state = runner.wait(job["job_id"], 4, timeout=10)
    assert state["status"] == "cancelled" and state["status_code"] == 499
    assert time.monotonic() - started < 5
    # The pool is whole again: the next calculation runs.
    after = runner.submit("echo", "suite", user_id=4)
    assert runner.wait(after["job_id"], 4, timeout=60)["status"] == "done"


def test_a_job_past_its_deadline_is_stopped():
    runner = _runner(workers=1, timeout=1.0)
    try:
        job = runner.submit("sleep", SLOW, user_id=5)
        state = runner.wait(job["job_id"], 5, timeout=60)
        assert state["status"] == "timeout" and state["status_code"] == 504
        assert "1 s" in state["detail"]
    finally:
        runner.shutdown()


def test_a_job_nobody_follows_any_more_is_stopped():
    runner = _runner(workers=1, abandon_after=0.5)
    try:
        job = runner.submit("sleep", SLOW, user_id=6)
        while runner._jobs[job["job_id"]].status == "queued":     # not polled: no status()
            time.sleep(0.05)
        time.sleep(1.5)
        state = runner.status(job["job_id"], 6)
        assert state["status"] == "abandoned"
    finally:
        runner.shutdown()


def test_a_worker_that_dies_fails_its_job_and_is_replaced(runner):
    job = runner.submit("crash", None, user_id=7)
    state = runner.wait(job["job_id"], 7, timeout=60)
    assert state["status"] == "failed" and "processus de calcul" in state["detail"]
    after = runner.submit("echo", "suite", user_id=7)
    assert runner.wait(after["job_id"], 7, timeout=60)["status"] == "done"


def test_jobs_wait_for_a_free_worker_and_a_queued_job_can_be_cancelled():
    runner = _runner(workers=1)
    try:
        first = runner.submit("sleep", SLOW, user_id=8)
        second = runner.submit("echo", "deux", user_id=8)
        _running(runner, first["job_id"], 8)
        assert runner.status(second["job_id"], 8)["queue_position"] == 1
        assert runner.cancel(second["job_id"], 8)["status"] == "cancelled"
        runner.cancel(first["job_id"], 8)
        assert runner.wait(first["job_id"], 8, timeout=10)["status"] == "cancelled"
    finally:
        runner.shutdown()


def test_a_job_belongs_to_its_user_and_each_user_is_capped():
    runner = InteractiveRunner(workers=1, target=pricing_job_targets.run, warm_modules=(),
                               max_active_per_user=2)
    runner.start = lambda: runner           # bookkeeping only: no process
    first = runner.submit("echo", 1, user_id=9)
    runner.submit("echo", 2, user_id=9)
    assert runner.status(first["job_id"], 10) is None
    assert runner.cancel(first["job_id"], 10) is None
    with pytest.raises(QueueFull):
        runner.submit("echo", 3, user_id=9)
    runner.submit("echo", 1, user_id=10)    # another user is not blocked


def test_shutdown_ends_the_workers():
    runner = _runner(workers=1)
    job = runner.submit("sleep", SLOW, user_id=11)
    _running(runner, job["job_id"], 11)
    processes = [slot.process for slot in runner._slots]
    runner.shutdown()
    assert all(not process.is_alive() for process in processes)
    assert runner.status(job["job_id"], 11)["status"] == "cancelled"


# ── The real calculation ───────────────────────────────────────────

def test_the_queued_price_is_the_synchronous_price():
    request = PricingRequest(script="AT MATURITY:\n  PAY MAX(S[1]-.9,0)",
                             underlyings=[dict(name="S1", sigma=.2, q=.02)], corr_matrix=[[1]],
                             r=.03, T=.5, N=2000, seed=7, antithetic=False)
    runner = InteractiveRunner(workers=1).start()          # the production target, warmed
    try:
        job = runner.submit("price", request, user_id=12)
        state = runner.wait(job["job_id"], 12, timeout=120)
    finally:
        runner.shutdown()
    assert state["status"] == "done", state
    direct = price_endpoint(request)
    assert state["result"]["price"] == pytest.approx(direct.price, abs=1e-12)
    assert state["result"]["ic95"] == pytest.approx(list(direct.ic95), abs=1e-12)


def test_a_bad_script_comes_back_as_the_routes_422():
    runner = InteractiveRunner(workers=1).start()
    try:
        bad = PricingRequest(script="AT MATURITY:\n  PAY (", underlyings=[dict(name="S1", sigma=.2)],
                             corr_matrix=[[1]], r=.03, T=.5, N=2000)
        state = runner.wait(runner.submit("price", bad, user_id=13)["job_id"], 13, timeout=120)
    finally:
        runner.shutdown()
    assert state["status"] == "failed" and state["status_code"] == 422


# ── Routes ─────────────────────────────────────────────────────────

def _client(monkeypatch, runner, user_id):
    app = FastAPI()
    app.include_router(pricing_jobs.router)
    app.dependency_overrides[get_current_pricer] = lambda: SimpleNamespace(id=user_id)
    monkeypatch.setattr(pricing_jobs, "get_runner", lambda: runner)
    return TestClient(app)


BODY = dict(script="AT MATURITY:\n  PAY 1", underlyings=[dict(name="S1", sigma=.2)],
            corr_matrix=[[1]], r=.03, T=.5, N=2000)


def test_routes_submit_poll_and_cancel(monkeypatch, runner):
    client = _client(monkeypatch, runner, 20)
    submitted = client.post("/api/price/jobs/price", json=BODY)
    assert submitted.status_code == 202
    job_id = submitted.json()["job_id"]
    runner.wait(job_id, 20, timeout=60)
    state = client.get(f"/api/price/jobs/{job_id}").json()
    assert state["status"] == "done" and state["result"]["script"] == BODY["script"]
    assert client.delete(f"/api/price/jobs/{job_id}").json()["status"] == "done"   # nothing to stop
    assert _client(monkeypatch, runner, 21).get(f"/api/price/jobs/{job_id}").status_code == 404


def test_routes_validate_the_request_before_queueing(monkeypatch, runner):
    client = _client(monkeypatch, runner, 22)
    assert client.post("/api/price/jobs/price", json={**BODY, "N": "beaucoup"}).status_code == 422
    assert client.post("/api/price/jobs/in-life", json={"script": "x"}).status_code == 422


def test_routes_answer_429_beyond_the_per_user_cap(monkeypatch):
    runner = InteractiveRunner(workers=1, target=pricing_job_targets.run, warm_modules=(),
                               max_active_per_user=1)
    runner.start = lambda: runner
    client = _client(monkeypatch, runner, 23)
    assert client.post("/api/price/jobs/price", json=BODY).status_code == 202
    response = client.post("/api/price/jobs/price", json=BODY)
    assert response.status_code == 429 and "en cours" in response.json()["detail"]
