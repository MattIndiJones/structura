"""Research HTTP contract, real queue dispatch, and batch recovery in SQLite isolation."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import auth, compute, research_rates_credit
from backend.app.core.compute.pricers import PRICERS
from backend.app.core.compute.queue_store import claim_next_batch, pending_jobs, record_job_result
from backend.app.core.product.models import Product
from backend.app.db.database import get_session
from backend.app.db.models import ComputeBatch, Entity, User
from backend.app.services.product_repository import stage_new_product, stage_revision, stage_terms
from backend.scripts import run_compute_worker
from backend.tests.rates_credit_roll import RollReplayError, replay_roll
from backend.tests.rates_credit_roll_fixture import (
    CLN_LEVELS, CLN_NAVS, FRN_LEVELS, FRN_NAVS, build_roll_plan, cln_market, frn_market, product_for, terms_for,
)


RESEARCH = "/api/v1/structured-indices/rates-credit"


@pytest.fixture
def research_rates_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'research-rates.db').as_posix()}",
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(run_compute_worker, "engine", engine)
    monkeypatch.setenv("STRUCTURA_RESEARCH_RATES_CREDIT_USERS", "research,other,checker")
    with Session(engine) as db:
        db.add(Entity(id=1, name="Research test entity"))
        db.flush()
        users = [User(username=name, email=f"{name}@example.test", password_hash="test-only",
                      role=role, entity_id=1) for name, role in (
            ("research", "user"), ("other", "user"), ("unlisted", "user"), ("checker", "checker"),
        )]
        db.add_all(users)
        db.commit()
        headers = {user.username: {"Authorization": "Bearer " + auth._make_token(
            user.id, user.role, user.entity_id, auth_version=user.auth_version,
        )} for user in users}

    def sessions():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(research_rates_credit.router)
    app.include_router(compute.router)
    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            yield client, headers, engine
    finally:
        engine.dispose()


def json_response(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def _prepare(client, headers, vintage):
    terms = terms_for(vintage)
    prepared = json_response(client.post(f"{RESEARCH}/prepare", headers=headers, json={
        "millesime_id": vintage, "terms_version": 1, "terms": terms.model_dump(mode="json"),
        "intent": {"nominal": 1_000_000.0, "side": "BUY"},
    }))
    return prepared, product_for(terms, prepared["millesime"]["native_schedule"])


def _job(prepared, *, job_id, market, cutoff):
    return {**prepared, "job_id": job_id, "valuation_date": cutoff[:10], "value_date": cutoff[:10],
            "cutoff": cutoff, "market": market}


def _work():
    return run_compute_worker.process_next_batch("rates-credit-test", max_workers=2, use_processes=False)


def test_research_authority_and_request_key_are_enforced(research_rates_api, monkeypatch):
    client, members, _ = research_rates_api
    owner = members["research"]
    assert client.get(f"{RESEARCH}/capabilities").status_code == 401
    assert client.get(f"{RESEARCH}/capabilities", headers=members["unlisted"]).status_code == 403
    assert client.get(f"{RESEARCH}/capabilities", headers=members["checker"]).status_code == 403
    capability = json_response(client.get(f"{RESEARCH}/capabilities", headers=owner))
    assert "FRN" in json.dumps(capability) and "CLN" in json.dumps(capability)
    prepared, product = _prepare(client, owner, "frn-first")
    market, cutoff = frn_market("A", product)
    job = _job(prepared, job_id="initial-frn", market=market, cutoff=cutoff)
    body = {"run_id": "test-research-auth", "request_key": "issue-frn-initial", "jobs": [job]}
    bypass = {"kind": "research_rates_credit_issue", "jobs": [{"payload": job}]}
    assert client.post("/api/compute/batches", headers=owner, json=bypass).status_code == 422
    assert client.post(f"{RESEARCH}/issue-batches", headers=members["other"], json=body).status_code == 404
    tampered = deepcopy(body)
    tampered["jobs"][0]["millesime"]["intent"]["nominal"] *= 2
    assert client.post(f"{RESEARCH}/issue-batches", headers=owner, json=tampered).status_code == 422
    stale = {**body, "expected_engine_fingerprint": "0" * 64}
    assert client.post(f"{RESEARCH}/issue-batches", headers=owner, json=stale).status_code == 409
    body["expected_engine_fingerprint"] = capability["engine_fingerprint"]

    barrier = Barrier(2, timeout=10)

    def submit():
        barrier.wait()
        return json_response(client.post(f"{RESEARCH}/issue-batches", headers=owner, json=body), 202)

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = [pool.submit(submit) for _ in range(2)]
        first, retry = [future.result() for future in replies]
    assert first["id"] == retry["id"]
    assert first["results_path"] == f"/api/compute/batches/{first['id']}"
    assert json_response(client.get(first["results_path"], headers=owner))["status"] == "queued"
    assert client.get(first["results_path"], headers=members["other"]).status_code == 404
    conflict = {**body, "run_id": "different-run"}
    assert client.post(f"{RESEARCH}/issue-batches", headers=owner, json=conflict).status_code == 409

    assert _work()
    done = json_response(client.get(first["results_path"], headers=owner))
    assert done["status"] == "completed", done
    result = done["jobs"][0]["result"]["result"]
    assert result["unit"] == "EUR_per_100"
    assert result["dirty_per_100"] == pytest.approx(102.94189618, abs=1e-8)
    monkeypatch.setenv("STRUCTURA_RESEARCH_RATES_CREDIT_USERS", "other,checker")
    assert client.get(first["results_path"], headers=owner).status_code == 404
    assert json_response(client.get("/api/compute/batches", headers=owner)) == []


def test_prepare_uses_the_historical_product_terms_and_schedule(research_rates_api):
    client, members, engine = research_rates_api
    owner = members["research"]
    with Session(engine) as db:
        actor = db.exec(select(User).where(User.username == "research")).one()
        product = Product(terms=terms_for("frn-first"), intent={"nominal": 1_000_000.0, "side": "BUY"})
        first = stage_new_product(db, product, user=actor)
        amended = stage_terms(db, first, terms_for("frn-next"), actor_id=actor.id, reason="Test")
        current = stage_revision(db, amended, expected_revision=first.revision, actor_id=actor.id,
                                 action="PRODUCT_TERMS_REVISED")
        db.commit()

    source = {"millesime_id": "historical-frn", "product_id": first.product_id}
    historical = json_response(client.post(f"{RESEARCH}/prepare", headers=owner, json={
        **source, "expected_revision": first.revision, "terms_version": 1,
    }))["millesime"]
    latest = json_response(client.post(f"{RESEARCH}/prepare", headers=owner, json=source))["millesime"]
    assert historical["product_reference"] == latest["product_reference"] == first.reference
    assert historical["terms_version"] == 1 and latest["terms_version"] == 2
    assert historical["schedule_fingerprint"] == first.native_schedule.fingerprint
    assert latest["schedule_fingerprint"] == current.native_schedule.fingerprint
    assert historical["fingerprint"] != latest["fingerprint"]
    assert client.post(f"{RESEARCH}/prepare", headers=owner, json={
        **source, "expected_revision": first.revision, "terms_version": 2,
    }).status_code == 409


def test_worker_resumes_missing_jobs_and_replays_signed_results(research_rates_api):
    client, members, engine = research_rates_api
    owner = members["research"]
    prepared, product = _prepare(client, owner, "frn-first")
    jobs = []
    for cut in ("B", "C-open", "C"):
        market, cutoff = frn_market(cut, product)
        jobs.append(_job(prepared, job_id=f"frn-{cut}", market=market, cutoff=cutoff))
    ticket = json_response(client.post(f"{RESEARCH}/mtm-batches", headers=owner, json={
        "run_id": "test-research-resume", "request_key": "test-frn-marks", "jobs": jobs,
    }), 202)
    with Session(engine) as db:
        batch = claim_next_batch(db, "interrupted-worker")
        assert batch.id == ticket["id"]
        lease = batch.lease_token
        taken = pending_jobs(db, batch.id, lease_token=lease)
        latest = taken[-1]
        completed = PRICERS[batch.kind](json.loads(latest.payload_json))
        assert record_job_result(db, latest.id, True, completed, None, lease_token=lease)
        batch = db.get(ComputeBatch, ticket["id"])
        batch.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.add(batch)
        db.commit()

    assert _work()
    done = json_response(client.get(ticket["results_path"], headers=owner))
    assert done["status"] == "completed", done
    assert [row["attempt"] for row in done["jobs"]] == [2, 2, 1]
    assert done["jobs"][-1]["result"] == completed
    marks = {row["result"]["result"]["job_id"]: row["result"]["result"] for row in reversed(done["jobs"])}
    opened, paid = marks["frn-C-open"], marks["frn-C"]
    due = next(row for row in opened["flows"] if row["state"] in ("due", "due_open"))
    settled = next(row for row in paid["flows"] if row["state"] == "paid")
    assert due["flow_id"] == settled["flow_id"]
    assert due["pv_per_100"] == pytest.approx(1.03638889, abs=1e-8)
    assert settled["amount_per_100"] == pytest.approx(1.036389, abs=1e-9)
    assert paid["receivable_pv_per_100"] == 0 and settled["fact_id"]
    assert opened["residual_pv_per_100"] == paid["residual_pv_per_100"]

    for job, row in zip(jobs, done["jobs"], strict=True):
        evidence = {"job": job, **row["result"]}
        json_response(client.post(f"{RESEARCH}/verify-receipt", headers=owner, json=evidence))
        replayed = json_response(client.post(f"{RESEARCH}/replay", headers=owner, json=evidence))
        assert replayed["matched"] is True
        assert replayed["result_fingerprint"] == evidence["receipt"]["result_fingerprint"]
        assert replayed["result"] == evidence["result"]
        assert client.post(f"{RESEARCH}/verify-receipt", headers=members["other"], json=evidence).status_code in (403, 404)
        tampered = deepcopy(evidence)
        tampered["result"]["dirty_per_100"] += 1
        assert client.post(f"{RESEARCH}/verify-receipt", headers=owner, json=tampered).status_code in (409, 422)


def test_mtm_batch_keeps_the_identity_of_a_failed_job(research_rates_api):
    client, members, _ = research_rates_api
    owner = members["research"]
    prepared, product = _prepare(client, owner, "frn-first")
    market_a, cut_a = frn_market("A", product)
    market_b, cut_b = frn_market("B", product)
    market_b["fixings"] = []
    ticket = json_response(client.post(f"{RESEARCH}/mtm-batches", headers=owner, json={
        "run_id": "test-partial-fixing", "request_key": "test-partial-fixing-mtm",
        "jobs": [_job(prepared, job_id="valid-a", market=market_a, cutoff=cut_a),
                 _job(prepared, job_id="missing-b-fixing", market=market_b, cutoff=cut_b)],
    }), 202)

    assert _work()
    done = json_response(client.get(ticket["results_path"], headers=owner))
    assert done["status"] == "completed_with_failures"
    rows = {row["job_id"]: row for row in done["jobs"]}
    assert rows["valid-a"]["result"]["receipt"]["job_id"] == "valid-a"
    failure = rows["missing-b-fixing"]
    assert failure["millesime_id"] == "frn-first"
    assert failure["valuation_date"] == cut_b[:10]
    assert failure["status"] == "failed" and failure["result"] == {}
    assert "RATES_FIXING_UNAVAILABLE" in failure["error"]


def test_lifecycle_observes_pending_and_late_known_credit_facts(research_rates_api):
    client, members, _ = research_rates_api
    owner = members["research"]
    prepared, product = _prepare(client, owner, "cln-first")

    def resolve(day, case="normal"):
        market, cutoff = cln_market(day, product, case=case)
        job = _job(prepared, job_id=f"cln-state-{day}-{case}", market=market, cutoff=cutoff)
        response = json_response(client.post(f"{RESEARCH}/lifecycle", headers=owner, json={
            "run_id": "test-cln-lifecycle", "job": job,
        }))
        return response["result"]

    assert resolve(15, "late_notice")["state"] == "alive"
    pending = resolve(15)
    assert pending["state"] == "recovery_pending" and pending["receivable_pv_per_100"] is None
    due = resolve(20, "late_payment")
    paid = resolve(21, "late_payment")
    assert due["state"] == "settlement_pending" and paid["state"] == "settled"
    assert due["receivable_pv_per_100"] == pytest.approx(35)
    assert paid["receivable_pv_per_100"] == 0
    recovery = next(row for row in paid["flows"] if row["paid_date"] == "2021-07-20")
    assert recovery["amount_per_100"] == 35
    assert datetime.fromisoformat(recovery["available_at"]).date().isoformat() == "2021-07-21"
    zero = resolve(20, "zero")
    assert zero["state"] == "settled"
    assert any(row["paid_date"] == "2021-07-20" and row["amount_per_100"] == 0 for row in zero["flows"])


def _archive_roll(client, owner, plan):
    capability = json_response(client.get(f"{RESEARCH}/capabilities", headers=owner))
    engine = {"expected_engine_fingerprint": capability["engine_fingerprint"]}
    prepared = {
        vintage["millesime_id"]: json_response(
            client.post(f"{RESEARCH}/prepare", headers=owner, json={**vintage, **engine}),
        )
        for vintage in plan["millesimes"]
    }
    requests = {"issue": {}, "mtm": {}}
    for session in plan["sessions"]:
        for job in session["jobs"]:
            requests[job["operation"]][job["job_id"]] = _job(
                prepared[job["millesime_id"]], job_id=job["job_id"], market=job["market"], cutoff=session["cutoff"],
            )

    tickets = {}
    for operation, jobs in requests.items():
        tickets[operation] = json_response(client.post(f"{RESEARCH}/{operation}-batches", headers=owner, json={
            "run_id": plan["run_id"], "request_key": f"{plan['run_id']}:{operation}", "jobs": list(jobs.values()),
            **engine,
        }), 202)
    assert all(_work() for _ in tickets)
    assert not _work()

    evidence = {}
    for operation, ticket in reversed(tuple(tickets.items())):
        batch = json_response(client.get(ticket["results_path"], headers=owner))
        assert batch["status"] == "completed", batch
        for row in reversed(batch["jobs"]):
            signed = row["result"]
            job_id = signed["receipt"]["job_id"]
            assert job_id not in evidence
            body = {"job": requests[operation][job_id], **signed}
            replay = json_response(client.post(f"{RESEARCH}/replay", headers=owner, json=body))
            assert replay["matched"] and replay["job_id"] == job_id
            evidence[job_id] = signed
    return {"plan": plan, "capability": capability, "requests": requests, "evidence": evidence}


@pytest.mark.parametrize(("instrument", "daily"), [("FRN", False), ("CLN", False), ("CLN", True)])
def test_roll_from_archived_http_results(research_rates_api, tmp_path, monkeypatch, instrument, daily):
    client, members, _ = research_rates_api
    plan = build_roll_plan(instrument, daily=daily)
    archive = _archive_roll(client, members["research"], plan)
    expected = replay_roll(archive["plan"], archive["evidence"])

    def offline(*args, **kwargs):
        pytest.fail("An already archived roll must replay without HTTP")

    monkeypatch.setattr(client, "request", offline)
    path = tmp_path / "roll.json"
    path.write_text(json.dumps(archive, sort_keys=True), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    actual = replay_roll(restored["plan"], restored["evidence"])
    assert actual == expected
    rows = actual["rows"]
    if daily:
        assert actual["state"] == "blocked"
        assert actual["blocked"]["day"] == "2021-07-15"
        assert actual["blocked"]["reason"] == "recovery_pending"
        assert [row["day"] for row in rows] == ["2021-07-14"]
        return

    assert actual["state"] == "completed"
    levels, navs = (FRN_LEVELS, FRN_NAVS) if instrument == "FRN" else (CLN_LEVELS, CLN_NAVS)
    assert [row["level"] for row in rows] == pytest.approx(levels, abs=1e-6)
    assert [row["nav_eur"] for row in rows] == pytest.approx(navs, abs=0.01)
    for previous, current in zip(rows, rows[1:]):
        assert current["explain"]["residual_eur"] == pytest.approx(0.0, abs=0.01)
        assert sum(current["explain"]["contributions_index_points"].values()) == pytest.approx(
            current["level"] - previous["level"], abs=1e-6,
        )

    settlements = [(row["day"], event) for row in rows for event in row["events"] if event["event"] == "settlement"]
    assert len(settlements) == 1
    paid_day, paid = settlements[0]
    if instrument == "FRN":
        assert rows[1]["cash_eur"] == 0
        assert paid_day == "2026-12-21"
        assert paid["amount_eur"] == pytest.approx(10_363.89, abs=0.01)
        roll = rows[2]
        assert roll["millesime_id"] == "frn-next"
        assert roll["pre_roll"]["cash_eur"] == pytest.approx(10_363.89, abs=0.01)
        assert roll["pre_roll"]["receivables_pv_eur"] == 0
        assert roll["quantity"] == pytest.approx(10_065.3163206153, abs=1e-6)
    else:
        assert rows[1]["receivables_pv_eur"] == pytest.approx(349_980.82, abs=0.01)
        assert rows[1]["cash_eur"] == 0
        assert paid_day == "2021-07-20"
        assert paid["amount_eur"] == rows[2]["cash_eur"] == 350_000
        assert any(event["event"] == "roll_deferred" for event in rows[2]["events"])
        roll = rows[3]
        assert roll["millesime_id"] == "cln-next"
        assert roll["quantity"] == pytest.approx(3_471.5813550215, abs=1e-6)
    assert roll["pre_roll"]["nav_eur"] == pytest.approx(roll["nav_eur"], abs=0.01)
    assert roll["cash_eur"] == pytest.approx(0, abs=0.01)

    missing = dict(archive["evidence"])
    missing.pop(plan["sessions"][-1]["jobs"][-1]["job_id"])
    with pytest.raises(RollReplayError):
        replay_roll(plan, missing)
    foreign = deepcopy(archive["evidence"])
    foreign[plan["sessions"][-1]["jobs"][0]["job_id"]]["receipt"]["run_id"] = "other-run"
    with pytest.raises(RollReplayError):
        replay_roll(plan, foreign)
