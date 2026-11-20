"""P1-4, second step: the Pricer's analyses through the interactive queue.

The queued result must be the synchronous route's result: the worker calls
the same endpoint function. These tests start one real warmed worker."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from backend.app.api import pricing_jobs, simulation
from backend.app.api import pricing as pricing_api
from backend.app.api.auth import get_current_pricer
from backend.app.core.compute import interactive
from backend.app.core.compute.interactive import InteractiveRunner
from backend.app.core.schemas import GridRequest, PathsRequest, ProbaRequest, ProfileRequest, SolverRequest

SCRIPT = "PARAM K\nAT MATURITY:\n  PAY MAX(S[1] - K, 0)"
BASE = dict(script=SCRIPT, underlyings=[dict(name="S1", sigma=.2, q=.01)], corr_matrix=[[1]],
            r=.03, T=1.0, user_params={"K": .95})

CASES = [
    ("profile", ProfileRequest(**BASE), pricing_api.profile_endpoint),
    ("paths", PathsRequest(**BASE, N_stat=200, N_display=20), pricing_api.paths_endpoint),
    ("proba", ProbaRequest(**BASE, N=2000), pricing_api.proba_endpoint),
    ("solve", SolverRequest(**{**BASE, "user_params": {}}, param_name="K", target_price=.1, lo=.5, hi=1.5,
                            N=2000, max_iter=20), simulation.solve_endpoint),
    ("grid", GridRequest(**{**BASE, "underlyings": [dict(name="S1", sigma=.2, q=.01)],
                            "script": "PARAM K\nPARAM L\nAT MATURITY:\n  PAY MAX(S[1] - K, 0) * L", "user_params": {}},
                         param_x="K", x_min=.9, x_max=1.1, x_steps=2, param_y="L", y_min=.5, y_max=1, y_steps=2,
                         N=1000), simulation.grid_endpoint),
]


@pytest.fixture(scope="module")
def runner():
    instance = InteractiveRunner(workers=1).start()          # production target, warmed
    yield instance
    instance.shutdown()


@pytest.mark.parametrize("kind, request_, endpoint", CASES, ids=[case[0] for case in CASES])
def test_l_analyse_en_file_rend_le_resultat_de_la_route_synchrone(runner, kind, request_, endpoint):
    state = runner.wait(runner.submit(kind, request_, user_id=31)["job_id"], 31, timeout=180)
    assert state["status"] == "done", state
    direct = jsonable_encoder(endpoint(request_))
    # Everything but the measured duration of the calculation itself.
    assert _without_timing(state["result"]) == _without_timing(direct)


def _without_timing(value):
    if isinstance(value, dict):
        return {k: _without_timing(v) for k, v in value.items() if k != "elapsed_ms"}
    if isinstance(value, list):
        return [_without_timing(v) for v in value]
    return value


def test_chaque_analyse_declaree_designe_une_fonction_de_route():
    for kind, (module, name) in interactive.ANALYSES.items():
        assert callable(getattr(importlib.import_module(f"backend.app.{module}"), name)), kind
    # The scenarios and the MtF comparison keep their own process pool.
    assert "scenarios" not in interactive.ANALYSES and "mtf_compare" not in interactive.ANALYSES


def test_les_analyses_longues_ont_un_delai_plus_long():
    short = InteractiveRunner(workers=1, timeout=600)
    assert short.timeout_for("price") == 600
    assert short.timeout_for("backtest_compare") == interactive.LONG_TIMEOUT_SECONDS
    assert InteractiveRunner(workers=1, timeout=4000).timeout_for("backtest") == 4000


def _client(monkeypatch, runner, user_id):
    app = FastAPI()
    app.include_router(pricing_jobs.router)
    app.dependency_overrides[get_current_pricer] = lambda: SimpleNamespace(id=user_id)
    monkeypatch.setattr(pricing_jobs, "get_runner", lambda: runner)
    return TestClient(app)


@pytest.mark.parametrize("path", ["profile", "paths", "proba", "backtest", "backtest-compare", "mtf",
                                  "mtf-drilldown", "solve", "grid"])
def test_les_routes_d_analyse_valident_avant_de_mettre_en_file(monkeypatch, path):
    queued = []
    fake = SimpleNamespace(submit=lambda kind, request, user: queued.append(kind) or {})
    response = _client(monkeypatch, fake, 32).post(f"/api/price/jobs/{path}", json={"script": "x"})
    assert response.status_code == 422 and queued == []


def test_une_route_d_analyse_met_le_bon_calcul_en_file(monkeypatch, runner):
    client = _client(monkeypatch, runner, 33)
    submitted = client.post("/api/price/jobs/proba", json={**BASE, "N": 2000})
    assert submitted.status_code == 202 and submitted.json()["kind"] == "proba"
    state = runner.wait(submitted.json()["job_id"], 33, timeout=180)
    assert state["status"] == "done", state
    direct = jsonable_encoder(pricing_api.proba_endpoint(ProbaRequest(**BASE, N=2000)))
    assert _without_timing(state["result"]) == _without_timing(direct)
