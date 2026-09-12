import json
import ast
from datetime import datetime, timedelta
from threading import Barrier, Thread
import time

from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.compute.queue_store import (
    claim_next_batch, enqueue_batch, pending_jobs, record_job_result,
)
from backend.app.core.compute.executor import run_batch
from backend.app.core.compute_budget import estimate_var_portfolio
from backend.app.core.valuation_runs import (
    replay_valuation_run, stage_valuation_run,
)
from backend.app.db.models import (
    ComputeJob, Deal, SchedulerRun, User, ValuationRun,
)
from backend.app.services import lifecycle_alerts
from backend.scripts.rebuild_database_schema import rebuild


def _engine(url="sqlite://"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _user(session):
    user = User(username="lot7", email="lot7@example.test", password_hash="x")
    session.add(user); session.commit(); session.refresh(user)
    return user


def test_bail_refuse_un_result_ancien_et_limite_la_fenetre():
    engine = _engine()
    with Session(engine) as session:
        user = _user(session)
        batch = enqueue_batch(session, user.id, "x", "lease", [{}, {}, {}])
        claimed = claim_next_batch(session, "worker-a")
        jobs = pending_jobs(session, batch.id, limit=2,
                            lease_token=claimed.lease_token)
        assert len(jobs) == 2
        assert all(job.status == "running" for job in jobs)
        assert record_job_result(
            session, jobs[0].id, True, {"x": 1}, None,
            lease_token="ancien-bail") is False
        assert session.get(ComputeJob, jobs[0].id).status == "running"
        assert record_job_result(
            session, jobs[0].id, True, {"x": 1}, None,
            lease_token=claimed.lease_token) is True
        assert record_job_result(
            session, jobs[0].id, True, {"x": 2}, None,
            lease_token=claimed.lease_token) is False


def test_deux_workers_ne_peuvent_pas_claim_le_meme_batch(tmp_path):
    engine = _engine(f"sqlite:///{tmp_path / 'queue.db'}")
    with Session(engine) as session:
        user = _user(session)
        batch = enqueue_batch(session, user.id, "x", "race", [{}])
        batch_id = batch.id
    barrier = Barrier(2)
    claimed = []

    def worker(name):
        with Session(engine) as session:
            barrier.wait()
            row = claim_next_batch(session, name)
            claimed.append(row.id if row else None)

    threads = [Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert claimed.count(batch_id) == 1
    assert claimed.count(None) == 1


def test_annulation_executor_termine_les_processus_actifs_rapidement():
    payload = {
        "script_text": "AT MATURITY\n  PAY MAX(0, S[1] - 1)\n",
        "underlyings": [{"name": "S1", "sigma": 0.2, "q": 0.0}],
        "corr": [[1.0]], "r": 0.03, "T": 10.0,
        "n_paths": 200_000, "model": "constant", "seed": 42,
    }
    started = time.monotonic()
    results = run_batch(
        "payscript_reprice", [(1, payload), (2, payload)],
        max_workers=2, use_processes=True, should_cancel=lambda: True,
    )
    assert time.monotonic() - started < 5.0
    assert len(results) == 2
    assert all("annulé" in result.error for result in results)


def test_estimation_var_agrege_les_deals_et_scenarios():
    def base(model="constant", assets=1):
        return {"base": {"valuation_context": {
            "T": 3.0, "N": 3000, "model": model, "antithetic": True,
            "underlyings": [{}] * assets, "barrier_monitoring": "weekly",
            "sigma_r": 0.0,
        }}}
    one = estimate_var_portfolio([base()], 100, 1)
    two = estimate_var_portfolio([base(), base("heston", 2)], 100, 2)
    assert one["cells"] == 100
    assert two["cells"] == 200
    assert two["work_units"] > 2 * one["work_units"]
    assert two["estimated_peak_bytes"] > one["estimated_peak_bytes"]


def test_runs_de_valorisation_sont_append_only_et_rejouables(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        user = _user(session)
        deal = Deal(
            reference="D-RUN", user_id=user.id, contract_version=3,
            script_snapshot="AT MATURITY\n  PAY 1\n", strike_date="2026-01-01",
            value_date="2026-01-03", devise="EUR",
        )
        session.add(deal); session.commit(); session.refresh(deal)
        ctx = {
            "valuation_context": {"constats": {}, "underlyings": [{}]},
            "T_elapsed": 0.5, "passe_jusqu_a": 0.5, "state": {},
            "norm_spots": [1.0], "corr": [[1.0]], "N_used": 2000,
            "underlyings_json": [{"name": "S1", "ticker": "ABC"}],
            "s0_map": {"S1": 100.0},
        }
        first, _ = stage_valuation_run(
            session, deal, user.id, "MTM", ctx, {"mtm": 0.98})
        second, _ = stage_valuation_run(
            session, deal, user.id, "MTM", ctx, {"mtm": 1.01})
        session.commit()
        assert first.id != second.id
        assert deal.latest_valuation_run_id == second.id
        assert json.loads(session.get(ValuationRun, first.id).result_json)["mtm"] == 0.98

        monkeypatch.setattr(
            "backend.app.core.compute.pricers.var_scenario.price_var_scenario_job",
            lambda payload: {"price": 0.98},
        )
        replay = replay_valuation_run(first)
        assert replay["identical"] is True

        greek, _ = stage_valuation_run(
            session, deal, user.id, "GREEKS", ctx,
            {"mtm_reference": 0.98, "scalar": {"rho": 0.01}},
        )
        session.commit()
        assert replay_valuation_run(greek)["identical"] is True


def test_scheduler_un_seul_passage_par_creneau(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(lifecycle_alerts, "engine", engine)
    lifecycle_alerts.configure_lifecycle_handlers(
        lambda *_a, **_k: {}, lambda *_a, **_k: {})
    slot = datetime(2026, 9, 12, 21, 0)
    first = lifecycle_alerts.run_scheduled_refresh(slot, "CATCH_UP")
    second = lifecycle_alerts.run_scheduled_refresh(slot, "SCHEDULED")
    assert first["status"] == "SUCCESS"
    assert second["status"] == "SKIPPED"
    with Session(engine) as session:
        rows = session.exec(select(SchedulerRun)).all()
        assert len(rows) == 1
        assert rows[0].trigger == "CATCH_UP"


def test_reconstruction_schema_en_mode_validation_ne_touche_pas_la_source(tmp_path):
    source = tmp_path / "legacy.db"
    engine = _engine(f"sqlite:///{source}")
    with Session(engine) as session:
        _user(session)
    engine.dispose()
    before = source.read_bytes()
    result = rebuild(source, apply=False)
    assert result["validated"] is True
    assert result["applied"] is False
    assert source.read_bytes() == before


def test_les_couches_metier_n_importent_aucune_route_api():
    root = __import__("pathlib").Path(__file__).resolve().parents[2] / "backend" / "app"
    violations = []
    for layer in ("core", "services", "db"):
        for path in (root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "api":
                    violations.append(str(path.relative_to(root)))
                if isinstance(node, ast.ImportFrom) and node.level and node.module:
                    if node.module.startswith("api"):
                        violations.append(str(path.relative_to(root)))
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("backend.app.api"):
                            violations.append(str(path.relative_to(root)))
    assert violations == []
