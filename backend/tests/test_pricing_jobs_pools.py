"""P1-4, last step: the analyses that start their own process pool.

The stress scenarios and the MtF comparison run in a server thread; their
cancellation, deadline and abandonment reach run_batch through
executor.ambient_cancel, which terminates the pool's processes."""
from __future__ import annotations

import multiprocessing
import threading
import time

import pytest
from fastapi.encoders import jsonable_encoder

from backend.app.api.scenarios import scenarios_endpoint
from backend.app.core.compute import executor, interactive
from backend.app.core.compute.interactive import InteractiveRunner
from backend.app.core.schemas import ScenarioRequest

SCRIPT = "PARAM K\nAT MATURITY:\n  PAY MAX(S[1] - K, 0)"


def _grid(n=1000, spots=(-0.1, 0.0, 0.1), vols=(0.0,)):
    return ScenarioRequest(script=SCRIPT, underlyings=[dict(name="S1", sigma=.2, q=.01)], corr_matrix=[[1]],
                           r=.03, T=1.0, user_params={"K": .95}, N=n, spot_shocks=list(spots), vol_shocks=list(vols))


def _pool_children():
    return [p for p in multiprocessing.active_children() if p.name != "structura-pricing"]


def _wait(condition, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _without_timing(value):
    if isinstance(value, dict):
        return {k: _without_timing(v) for k, v in value.items() if k != "elapsed_ms"}
    if isinstance(value, list):
        return [_without_timing(v) for v in value]
    return value


@pytest.fixture
def runner():
    instance = InteractiveRunner(workers=1, warm_modules=()).start()
    yield instance
    instance.shutdown()


def test_les_scenarios_en_file_rendent_le_resultat_de_la_route_synchrone(runner):
    request = _grid()
    state = runner.wait(runner.submit("scenarios", request, user_id=41)["job_id"], 41, timeout=180)
    assert state["status"] == "done", state
    assert _without_timing(state["result"]) == _without_timing(jsonable_encoder(scenarios_endpoint(request)))


def test_annuler_des_scenarios_arrete_les_processus_de_leur_pool(runner):
    heavy = _grid(n=20_000, spots=[x / 100 for x in range(-35, 40, 5)], vols=[-.1, -.05, 0, .05, .1])
    job = runner.submit("scenarios", heavy, user_id=42)
    assert _wait(lambda: len(_pool_children()) > 0), "le pool n'a jamais démarré"
    runner.cancel(job["job_id"], 42)
    assert runner.wait(job["job_id"], 42, timeout=30)["status"] == "cancelled"
    assert _wait(lambda: not _pool_children(), timeout=30), f"processus du pool encore vivants : {_pool_children()}"


def test_des_scenarios_au_dela_de_leur_delai_sont_arretes_avec_leur_pool():
    runner = InteractiveRunner(workers=1, warm_modules=(), timeout=1.5).start()
    try:
        heavy = _grid(n=20_000, spots=[x / 100 for x in range(-35, 40, 5)], vols=[-.1, -.05, 0, .05, .1])
        state = runner.wait(runner.submit("scenarios", heavy, user_id=43)["job_id"], 43, timeout=60)
        assert state["status"] == "timeout" and state["status_code"] == 504
        assert _wait(lambda: not _pool_children(), timeout=30)
    finally:
        runner.shutdown()


def test_un_seul_calcul_a_pool_tourne_a_la_fois():
    release = threading.Event()
    started = []

    def pool_target(kind, request):
        started.append(request)
        release.wait(10)
        return dict(ok=True, result=dict(request=request))

    runner = InteractiveRunner(workers=1, warm_modules=(), pool_target=pool_target).start()
    try:
        first = runner.submit("scenarios", "A", user_id=44)
        second = runner.submit("mtf_compare", "B", user_id=44)
        assert _wait(lambda: runner.status(first["job_id"], 44)["status"] == "running")
        time.sleep(0.3)
        assert runner.status(second["job_id"], 44)["status"] == "queued" and started == ["A"]
        release.set()
        assert runner.wait(second["job_id"], 44, timeout=10)["result"] == {"request": "B"}
    finally:
        release.set()
        runner.shutdown()


def test_un_calcul_a_pool_ne_retient_pas_les_prix():
    # A thread-run analysis uses no worker process: a price queued behind it runs.
    from backend.tests import pricing_job_targets
    release = threading.Event()
    runner = InteractiveRunner(workers=1, warm_modules=(), target=pricing_job_targets.run,
                               pool_target=lambda kind, request: release.wait(10) and dict(ok=True, result=None)).start()
    try:
        scenarios = runner.submit("scenarios", "S", user_id=45)
        assert _wait(lambda: runner.status(scenarios["job_id"], 45)["status"] == "running")
        price = runner.submit("echo", "prix", user_id=45)
        assert runner.wait(price["job_id"], 45, timeout=60)["result"]["request"] == "prix"
        assert runner.status(scenarios["job_id"], 45)["status"] == "running"
    finally:
        release.set()
        runner.shutdown()


def test_run_batch_entend_l_annulation_transmise():
    calls = []

    def slow(payload):
        calls.append(payload)
        time.sleep(0.5)
        return payload

    executor.PRICERS["essai_lent"] = slow
    token = executor.ambient_cancel.set(lambda: True)
    try:
        results = executor.run_batch("essai_lent", [(i, i) for i in range(6)], max_workers=2, use_processes=False)
    finally:
        executor.ambient_cancel.reset(token)
        del executor.PRICERS["essai_lent"]
    assert results and all(not r.ok and "annulé" in r.error for r in results)
    assert len(calls) <= 2


def test_une_annulation_explicite_prime_sur_l_annulation_transmise():
    executor.PRICERS["essai_rapide"] = lambda payload: payload
    token = executor.ambient_cancel.set(lambda: True)
    try:
        results = executor.run_batch("essai_rapide", [(1, 1)], use_processes=False, should_cancel=lambda: False)
    finally:
        executor.ambient_cancel.reset(token)
        del executor.PRICERS["essai_rapide"]
    assert [r.ok for r in results] == [True]


def test_les_calculs_a_pool_sont_declares_hors_des_processus_de_calcul():
    assert set(interactive.POOL_ANALYSES) == {"scenarios", "mtf_compare"}
    assert not set(interactive.POOL_ANALYSES) & set(interactive.ANALYSES)
