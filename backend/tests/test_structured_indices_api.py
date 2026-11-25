"""Exercise Athena's HTTP contract and durable worker with private market inputs."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from math import exp
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import auth, compute, structured_indices
from backend.app.core.compute.pricers.athena import ATHENA_ISSUE_KIND
from backend.app.core.compute.queue_store import enqueue_batch
from backend.app.core.valuation_context import json_transport_fingerprint
from backend.app.db.database import get_session
from backend.app.db.models import Entity, User
from backend.scripts import run_compute_worker


ATHENA = "/api/v1/structured-indices/athena"
ISSUE_BATCHES = f"{ATHENA}/issue-batches"
MTM_BATCHES = f"{ATHENA}/mtm-batches"
LIFECYCLE = f"{ATHENA}/lifecycle"
PRICING_MODELS = f"{ATHENA}/pricing-models"
PRICING = {"n_paths": 1_000, "seed": 42, "steps_per_year": 52}


@pytest.fixture
def athena_api(tmp_path, monkeypatch):
    db_path = tmp_path / "athena.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(run_compute_worker, "engine", engine)

    with Session(engine) as session:
        session.add(Entity(id=1, name="Athena test organization"))
        session.flush()
        users = [
            User(username=name, email=f"{name}@example.test", password_hash="test-only",
                 role=role, entity_id=1)
            for name, role in [("research", "user"), ("other", "user"), ("controller", "checker")]
        ]
        session.add_all(users)
        session.commit()
        headers = {
            user.username: {"Authorization": "Bearer " + auth._make_token(
                user.id, user.role, user.entity_id, auth_version=user.auth_version,
            )}
            for user in users
        }

    def sessions():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(structured_indices.router)
    app.include_router(compute.router)
    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            yield client, headers
    finally:
        engine.dispose()


def _market(as_of, spot):
    return {
        "as_of": as_of,
        "reference": f"synthetic-sx5e-close:{as_of}",
        "spot": spot,
        "rate": .02,
        "volatility": .20,
        "dividend_yield": .02,
        "funding_spread": .01,
    }


def _issue_request():
    return {
        "note_id": "athena-sx5e-2023-01-17",
        "terms": {
            "strike_date": "2023-01-17",
            "observations": [
                {"observation_date": "2024-01-17", "payment_date": "2024-01-19"},
                {"observation_date": "2025-01-17", "payment_date": "2025-01-21"},
            ],
            "observation_months": 12,
            "call_barrier": 1.,
            "protection_barrier": .60,
            "underlying": "SX5E",
            "currency": "EUR",
            "settlement_lag": 2,
            "calendar_reference": "athena-sx5e-target-test-v1",
        },
        "initial_fixing": 4_000.,
        "initial_fixing_reference": "official-sx5e:2023-01-17",
        "market": _market("2023-01-17", 4_000.),
        "pricing": PRICING,
        "coupon": {"mode": "fixed", "fixed_coupon": .06},
    }


def _submit(client, headers, path, request_key, jobs):
    response = client.post(path, headers=headers, json={
        "request_key": request_key, "max_workers": 2, "jobs": jobs,
    })
    assert response.status_code == 202, response.text
    return response.json()


def _poll(client, headers, batch):
    response = client.get(batch["results_path"], headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_pricing_catalogue_publishes_the_inputs_accepted_by_athena(athena_api):
    client, headers = athena_api
    assert client.get(PRICING_MODELS).status_code == 401
    assert client.get(PRICING_MODELS, headers=headers["controller"]).status_code == 403
    response = client.get(PRICING_MODELS, headers=headers["research"])
    assert response.status_code == 200, response.text
    catalogue = response.json()
    assert catalogue["version"] == "athena-pricing-v1"
    models = {model["id"]: model for model in catalogue["models"]}
    assert set(models) == {"constant", "heston", "sabr", "localvol"}
    model = models["constant"]
    assert catalogue["default_model"] == model["id"] == "constant"
    fields = {field["name"]: field for field in model["fields"]}
    assert {name: field["default"] for name, field in fields.items()} == {
        "n_paths": 20_000, "seed": 42, "steps_per_year": 52, "antithetic": True,
    }
    assert fields["steps_per_year"]["choices"] == [52, 104, 208]
    assert fields["n_paths"]["maximum"] == 50_000
    assert {field["name"]: field["default"] for field in model["market_fields"]} == {
        "volatility": .20, "dividend_yield": .02, "rate": .03, "funding_spread": 0.,
    }
    assert all(field["scale"] == 100 for field in model["market_fields"])
    assert model["market_curves"] == ["dividend_curve", "yield_curve", "funding_curve"]
    assert {field["name"] for field in models["heston"]["fields"]} - set(fields) == {
        "v0", "kappa", "theta", "xi", "rho_h",
    }
    assert {field["name"] for field in models["sabr"]["fields"]} - set(fields) == {"alpha", "beta", "rho", "nu"}
    assert models["localvol"]["supports_vol_surface"] is True
    assert all(not item["supports_vol_surface"] for name, item in models.items() if name != "localvol")
    assert all(item["reference_volatility"] == .20 for item in models.values())

    job = _issue_request()
    job["pricing"] = {**job["pricing"], "model": "lsv"}
    refused = client.post(ISSUE_BATCHES, headers=headers["research"],
                          json={"request_key": "unsupported-model", "jobs": [job]})
    assert refused.status_code == 422, refused.text


def test_legacy_retry_preserves_previously_admitted_pricing_defaults(athena_api):
    client, headers = athena_api
    job = _issue_request()
    job["pricing"] = {"steps_per_year": 52}
    submission = {"request_key": "previous-batch", "max_workers": 2, "jobs": [job]}
    previous = structured_indices.AthenaIssueBatch.model_validate(submission).model_dump(mode="json")
    previous["jobs"][0]["pricing"] = {"n_paths": 4096, "seed": 42, "steps_per_year": 52}
    with Session(run_compute_worker.engine) as session:
        owner = session.exec(select(User).where(User.username == "research")).one()
        batch = enqueue_batch(session, owner.id, ATHENA_ISSUE_KIND, "", previous["jobs"], params={
            "contract_version": 1, "request_key": submission["request_key"],
            "request_sha256": json_transport_fingerprint(previous),
        })
        previous_id = batch.id

    retry = _submit(client, headers["research"], ISSUE_BATCHES, submission["request_key"], [job])
    assert retry["id"] == previous_id
    job["pricing"]["antithetic"] = False
    conflict = client.post(ISSUE_BATCHES, headers=headers["research"], json=submission)
    assert conflict.status_code == 409, conflict.text


def test_batch_is_private_idempotent_and_queued_until_worker(athena_api):
    client, headers = athena_api
    job = _issue_request()
    body = {"request_key": "private-issue", "jobs": [job]}
    assert client.post(ISSUE_BATCHES, json=body).status_code == 401
    assert client.post(ISSUE_BATCHES, headers=headers["controller"], json=body).status_code == 403

    owner = headers["research"]
    batch = _submit(client, owner, ISSUE_BATCHES, "private-issue", [job])
    assert batch["request_key"] == "private-issue"
    assert batch["total_jobs"] == 1
    assert batch["results_path"] == f"/api/compute/batches/{batch['id']}"
    queued = _poll(client, owner, batch)
    assert queued["status"] == "queued"
    assert queued["jobs"][0]["status"] == "queued"
    assert queued["jobs"][0]["result"] == {}
    assert client.get(batch["results_path"], headers=headers["other"]).status_code == 404

    retry = _submit(client, owner, ISSUE_BATCHES, "private-issue", [job])
    assert retry["id"] == batch["id"]
    amended = deepcopy(job)
    amended["coupon"]["fixed_coupon"] = .07
    conflict = client.post(ISSUE_BATCHES, headers=owner, json={
        "request_key": "private-issue", "max_workers": 2, "jobs": [amended],
    })
    assert conflict.status_code == 409, conflict.text
    other = _submit(client, headers["other"], ISSUE_BATCHES, "private-issue", [amended])
    assert other["id"] != batch["id"]


def test_concurrent_retry_creates_one_durable_batch(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    ready = Barrier(2, timeout=10)
    job = _issue_request()

    def send():
        ready.wait()
        return _submit(client, owner, ISSUE_BATCHES, "concurrent-retry", [job])

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(send) for _ in range(2)]
        first, retry = [request.result() for request in requests]

    assert first["id"] == retry["id"]
    batches = client.get("/api/compute/batches", headers=owner)
    assert batches.status_code == 200, batches.text
    assert [batch["id"] for batch in batches.json()] == [first["id"]]
    assert len(_poll(client, owner, first)["jobs"]) == 1


def test_athena_issue_lifecycle_and_mtm_through_real_worker(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    custom_pricing = {"model": "constant", "n_paths": 512, "seed": 65, "steps_per_year": 104, "antithetic": False}
    issue = _submit(client, owner, ISSUE_BATCHES, "issue-2023-01-17", [{**_issue_request(), "pricing": custom_pricing}])
    assert run_compute_worker.process_next_batch("athena-issue-test", 2, use_processes=True)
    issue_results = _poll(client, owner, issue)
    assert issue_results["status"] == "completed", issue_results["jobs"]
    quote = issue_results["jobs"][0]["result"]
    assert quote["status"] == "issued"
    assert quote["price"] > 0.
    assert quote["coupon_rate"] == pytest.approx(.06)
    assert quote["pricing"] == custom_pricing
    vintage = quote["vintage"]
    fixing = {"day": "2024-01-17", "spot": 4_000., "reference": "official-sx5e:2024-01-17"}

    lifecycle_request = {"vintage": vintage, "as_of": fixing["day"], "fixings": []}
    missing = client.post(LIFECYCLE, headers=owner, json=lifecycle_request)
    assert missing.status_code == 422, missing.text
    lifecycle = client.post(LIFECYCLE, headers=owner, json={**lifecycle_request, "fixings": [fixing]})
    assert lifecycle.status_code == 200, lifecycle.text
    checked = lifecycle.json()
    assert checked["terminated"] is True
    assert "coupon_claims" not in checked and "kind" not in checked["redemption"]
    assert checked["terms_reference"] == quote["terms_reference"]
    assert checked["barriers"] == [{
        "kind": "call", "observation_date": "2024-01-17", "fixing": 4_000.,
        "initial_fixing": 4_000., "ratio": 1., "threshold": 1., "condition_met": True,
    }]

    # The market spot is deliberately below the contractual fixing on the call date.
    observation_days = ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-22"]
    marks = [{
        "vintage": vintage, "market": _market(day, 3_960.), "pricing": custom_pricing,
        "fixings": [fixing] if day >= fixing["day"] else [],
    } for day in observation_days]
    mtm = _submit(client, owner, MTM_BATCHES, "mtm-2024-01", marks)
    assert run_compute_worker.process_next_batch("athena-mtm-test", 2, use_processes=True)
    results = _poll(client, owner, mtm)
    assert results["status"] == "completed", results["jobs"]
    assert results["completed_jobs"] == len(marks)
    by_day = {job["result"]["day"]: job["result"] for job in results["jobs"]}
    assert list(by_day) == observation_days
    assert all(mark["terms_reference"] == quote["terms_reference"] for mark in by_day.values())
    assert all(mark["pricing"] == custom_pricing for mark in by_day.values())
    assert len({mark["receipt_id"] for mark in by_day.values()}) == len(marks)
    active = by_day["2024-01-16"]
    assert active["terminated"] is False
    assert active["residual_pv"] > 0.
    assert active["claims"] == []
    called = by_day["2024-01-17"]
    assert called["terminated"] is True
    assert called["residual_pv"] == 0.
    assert called["barriers"] == checked["barriers"]
    (claim,) = called["claims"]
    assert claim["observed_date"] == "2024-01-17"
    assert claim["payment_date"] == "2024-01-19"
    assert claim["amount"] == pytest.approx(106.)
    assert claim["pv"] == pytest.approx(106. * exp(-.03 * 2 / 365.25), abs=1e-10)
    (day_after_claim,) = by_day["2024-01-18"]["claims"]
    assert day_after_claim["event_id"] == claim["event_id"]
    assert day_after_claim["pv"] == pytest.approx(106. * exp(-.03 / 365.25), abs=1e-10)
    assert by_day["2024-01-22"]["claims"] == []


def test_phoenix_lifecycle_round_trips_active_and_terminal_cashflows_over_http(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    issue = _issue_request()
    vintage = {
        "note_id": "phoenix-sx5e-2023-01-17", "terms": {**issue["terms"], "coupon_barrier": .70},
        "initial_fixing": issue["initial_fixing"], "initial_fixing_reference": issue["initial_fixing_reference"],
        "annual_coupon": .06,
    }
    witness = {"vintage": vintage, "as_of": "2023-01-17", "fixings": []}
    before = client.post(LIFECYCLE, headers=owner, json=witness)
    assert before.status_code == 200, before.text
    assert before.json()["coupon_claims"] == []

    first = {"day": "2024-01-17", "spot": 2800., "reference": "official-sx5e:2024-01-17"}
    live = client.post(LIFECYCLE, headers=owner, json={**witness, "as_of": first["day"], "fixings": [first]})
    assert live.status_code == 200, live.text
    active = live.json()
    assert active["status"] == "active" and active["redemption"] is None
    assert [(b["kind"], b["condition_met"]) for b in active["barriers"]] == [("call", False), ("coupon", True)]
    [first_coupon] = active["coupon_claims"]
    assert first_coupon["kind"] == "coupon" and first_coupon["amount"] == 6.
    assert first_coupon["payment_date"] == "2024-01-19"

    final = {"day": "2025-01-17", "spot": 3600., "reference": "official-sx5e:2025-01-17"}
    closed = client.post(LIFECYCLE, headers=owner, json={**witness, "as_of": final["day"], "fixings": [first, final]})
    assert closed.status_code == 200, closed.text
    terminal = closed.json()
    assert terminal["status"] == "matured" and terminal["terminated"] is True
    assert terminal["coupon_claims"][0] == first_coupon
    second_coupon = terminal["coupon_claims"][1]
    principal = terminal["redemption"]
    assert (second_coupon["kind"], second_coupon["amount"]) == ("coupon", 6.)
    assert (principal["kind"], principal["amount"]) == ("redemption", 100.)
    assert second_coupon["event_id"] != principal["event_id"]
    assert second_coupon["payment_date"] == principal["payment_date"] == "2025-01-21"
    assert {b["kind"] for b in terminal["barriers"] if b["observation_date"] == final["day"]} == {"call", "coupon", "capital"}


def test_step_down_capability_and_vintage_survive_the_real_worker(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    supported = {payoff["id"]: payoff for payoff in client.get(PRICING_MODELS, headers=owner).json()["payoffs"]}
    assert supported["athena-step-down-sx5e"] == {
        "id": "athena-step-down-sx5e", "version": "athena-step-down-sx5e-v1",
        "issue_models": ["constant"], "mtm_models": ["constant"],
    }
    issue = _issue_request()
    issue["terms"]["call_barriers"] = [1., .95]
    issue["market"].update(spot=3900., volatility=0.)
    issue["pricing"] = {**PRICING, "n_paths": 32}
    issue["coupon"] = {"mode": "solve_to_target", "target_price": 100., "min_coupon": 0., "max_coupon": .20}
    batch = _submit(client, owner, ISSUE_BATCHES, "step-down-solve", [issue])
    assert run_compute_worker.process_next_batch("step-down-issue-test", 2, use_processes=True)
    results = _poll(client, owner, batch)
    assert results["status"] == "completed", results["jobs"]
    quote = results["jobs"][0]["result"]
    assert quote["price"] == pytest.approx(100., abs=.01)
    vintage = quote["vintage"]
    assert vintage["terms"]["call_barriers"] == [1., .95]

    fixing = {"day": "2024-01-17", "spot": 3900., "reference": "official-sx5e:2024-01-17"}
    final = {"day": "2025-01-17", "spot": 3800., "reference": "official-sx5e:2025-01-17"}
    marks = [
        {"vintage": vintage, "market": {**_market(day, 3900.), "volatility": 0.},
         "pricing": issue["pricing"], "fixings": fixings}
        for day, fixings in [(fixing["day"], [fixing]), (final["day"], [fixing, final])]
    ]
    batch = _submit(client, owner, MTM_BATCHES, "step-down-marks", marks)
    assert run_compute_worker.process_next_batch("step-down-mtm-test", 2, use_processes=True)
    results = _poll(client, owner, batch)
    assert results["status"] == "completed", results["jobs"]
    live, called = (job["result"] for job in results["jobs"])
    assert live["next_call"]["threshold"] == .95
    assert live["next_call"]["probability"] == 1.
    assert called["status"] == "called"
    assert called["barriers"][0]["threshold"] == .95
    assert called["claims"][0]["amount"] == pytest.approx(100 * (1 + 2 * quote["coupon_rate"]))


def test_solved_coupon_and_explicit_non_issuance_are_successful_jobs(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    solve = {
        **_issue_request(),
        "coupon": {"mode": "solve_to_target", "target_price": 100., "min_coupon": 0., "max_coupon": .20},
    }
    no_coupon = {
        **solve,
        "note_id": "athena-sx5e-outside-coupon-bounds",
        "coupon": {**solve["coupon"], "target_price": 200.},
    }
    issue = _submit(client, owner, ISSUE_BATCHES, "solved-and-skipped-issue", [solve, no_coupon])
    assert run_compute_worker.process_next_batch("athena-solve-test", 2, use_processes=True)
    results = _poll(client, owner, issue)
    assert results["status"] == "completed", results["jobs"]
    quote, skipped = [job["result"] for job in results["jobs"]]
    assert quote["status"] == "issued"
    assert quote["price"] == pytest.approx(100., abs=.01)
    assert 0. < quote["coupon_rate"] < .20
    assert quote["vintage"]["annual_coupon"] == quote["coupon_rate"]
    assert skipped["status"] == "no_coupon_in_bounds"
    assert skipped["market_snapshot_id"] == quote["market_snapshot_id"]
    assert skipped["receipt_id"] != quote["receipt_id"]
    assert skipped["vintage"] is None
    assert skipped["price"] is None


def test_phoenix_memory_issue_lifecycle_and_mark_through_http_and_worker(athena_api):
    client, headers = athena_api
    owner = headers['research']
    job = _issue_request()
    job['note_id'] = 'phoenix-memory-sx5e-2023-01-17'
    job['terms'].update(coupon_barrier=.70, coupon_memory=True)
    job['market']['volatility'] = 0.
    job['pricing'] = {**PRICING, 'n_paths': 32}
    batch = _submit(client, owner, ISSUE_BATCHES, 'phoenix-memory-issue-v1', [job])
    assert run_compute_worker.process_next_batch('phoenix-memory-issue-test', 2, use_processes=True)
    issue_batch = _poll(client, owner, batch)
    assert issue_batch['status'] == 'completed', issue_batch
    vintage = issue_batch['jobs'][0]['result']['vintage']
    assert vintage['terms']['coupon_memory'] is True

    missed = {'day': '2024-01-17', 'spot': 2600., 'reference': 'official-before-threshold'}
    called = {'day': '2025-01-17', 'spot': 4000., 'reference': 'official-at-call'}
    for fixing, expected in (([missed], []), ([missed, called], [('coupon', 12., 1)])):
        response = client.post(LIFECYCLE, headers=owner, json={
            'vintage': vintage, 'as_of': fixing[-1]['day'], 'fixings': fixing,
        })
        assert response.status_code == 200, response.text
        witness = response.json()
        assert [(flow['kind'], flow['amount'], flow['memory_periods']) for flow in witness['coupon_claims']] == expected
    assert witness['redemption']['amount'] == 100.
    assert witness['coupon_claims'][0]['event_id'] != witness['redemption']['event_id']

    jobs = []
    for day, fixings in (('2025-01-16', [missed]), (called['day'], [missed, called])):
        market = {**_market(day, 4200.), 'volatility': 0.}
        jobs.append({'vintage': vintage, 'market': market, 'pricing': job['pricing'], 'fixings': fixings})
    batch = _submit(client, owner, MTM_BATCHES, 'phoenix-memory-mtm-v1', jobs)
    assert run_compute_worker.process_next_batch('phoenix-memory-mtm-test', 2, use_processes=True)
    result = _poll(client, owner, batch)
    assert result['status'] == 'completed', result
    by_day = {row['result']['day']: row['result'] for row in result['jobs']}
    prior = by_day['2025-01-16']
    assert prior['next_call']['memory_periods'] == 1
    assert prior['next_call']['redemption_amount'] == pytest.approx(112.)
    assert prior['next_call']['probability'] == 1.
    claim, principal = by_day[called['day']]['claims']
    assert (claim['amount'], claim['memory_periods']) == (12., 1)
    assert principal['amount'] == 100.
    assert claim['event_id'] == witness['coupon_claims'][0]['event_id']



def test_reverse_convertible_through_http_and_worker(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    catalogue = client.get(PRICING_MODELS, headers=owner)
    assert catalogue.status_code == 200, catalogue.text
    capability = next(row for row in catalogue.json()["payoffs"] if row["id"] == "reverse-convertible-sx5e")
    assert capability == {
        "id": "reverse-convertible-sx5e", "version": "reverse-convertible-sx5e-v1",
        "issue_models": ["constant"], "mtm_models": ["constant"],
    }

    job = _issue_request()
    job["note_id"] = "reverse-convertible-sx5e-2023-01-17"
    terms = job["terms"]
    terms.update(reverse_convertible=True, maturity_years=2, observations=terms["observations"][-1:])
    job["market"]["volatility"] = 0.
    job["pricing"] = {**PRICING, "n_paths": 32}
    batch = _submit(client, owner, ISSUE_BATCHES, "reverse-convertible-issue-v1", [job])
    assert run_compute_worker.process_next_batch("reverse-convertible-issue-test", 2, use_processes=True)
    issue_batch = _poll(client, owner, batch)
    assert issue_batch["status"] == "completed", issue_batch
    issue = issue_batch["jobs"][0]["result"]
    vintage = issue["vintage"]
    assert vintage["terms"]["reverse_convertible"] is True
    assert vintage["terms"]["maturity_years"] == 2
    assert issue["coupon_rate"] == .06

    fixing = {"day": "2025-01-17", "spot": 0., "reference": "official-at-maturity"}
    for day, fixings in (("2025-01-16", []), (fixing["day"], [fixing])):
        response = client.post(LIFECYCLE, headers=owner, json={"vintage": vintage, "as_of": day, "fixings": fixings})
        assert response.status_code == 200, response.text
        witness = response.json()
        if not fixings:
            assert witness["status"] == "active" and witness["coupon_claims"] == [] and witness["redemption"] is None
    assert witness["status"] == "matured" and witness["terminated"]
    assert witness["terms_reference"] == issue["terms_reference"]
    assert [(barrier["kind"], barrier["condition_met"]) for barrier in witness["barriers"]] == [("capital", False)]
    coupon, = witness["coupon_claims"]
    assert coupon["kind"] == "coupon" and coupon["amount"] == 12.
    assert witness["redemption"]["kind"] == "redemption" and witness["redemption"]["amount"] == 0.

    jobs = []
    for day, fixings in (("2025-01-16", []), (fixing["day"], [fixing]), ("2025-01-21", [fixing])):
        market = {**_market(day, 4200.), "volatility": 0.}
        jobs.append({"vintage": vintage, "market": market, "pricing": job["pricing"], "fixings": fixings})
    batch = _submit(client, owner, MTM_BATCHES, "reverse-convertible-mtm-v1", jobs)
    assert run_compute_worker.process_next_batch("reverse-convertible-mtm-test", 2, use_processes=True)
    marks = _poll(client, owner, batch)
    assert marks["status"] == "completed", marks
    before, maturity, settled = [entry["result"] for entry in marks["jobs"]]
    assert all("next_call" not in mark for mark in (before, maturity, settled))
    assert before["status"] == "active" and before["residual_pv"] > 100 and before["claims"] == []
    assert maturity["status"] == "matured" and maturity["residual_pv"] == 0.
    assert [(flow["event_id"], flow["amount"]) for flow in maturity["claims"]] == [
        (coupon["event_id"], 12.), (witness["redemption"]["event_id"], 0.),
    ]
    assert maturity["claims"][0]["payment_date"] == "2025-01-21"
    assert 0 < maturity["claims"][0]["pv"] < 12.
    assert settled["status"] == "matured" and settled["claims"] == []



def test_quoted_payoffs_through_http_and_worker(athena_api):
    client, headers = athena_api
    owner = headers["research"]
    catalogue = client.get(PRICING_MODELS, headers=owner)
    assert catalogue.status_code == 200, catalogue.text
    capability = {row["id"]: row for row in catalogue.json()["payoffs"]}
    witnesses = [
        ({"id": "capital-guaranteed-sx5e", "participation_strike": 1.}, 4800., "participation", 100.),
        ({"id": "booster-sx5e", "participation": 1.5, "redemption_cap": 1.3}, 5000., "participation", 100.),
        ({"id": "autocall-gear-put-sx5e", "put_strike": .6, "gearing": 2.,
          "single_coupon": .075}, 4000., "coupon", 100.),
    ]
    jobs = []
    for payoff, _, _, _ in witnesses:
        payoff_id = payoff["id"]
        assert capability[payoff_id] == {"id": payoff_id, "version": f"{payoff_id}-v1",
                                          "issue_models": ["constant"], "mtm_models": ["constant"]}
        job = _issue_request()
        job["note_id"] = payoff_id
        terms = job["terms"]
        terms["payoff"] = payoff
        if payoff_id != "autocall-gear-put-sx5e":
            terms["observations"] = terms["observations"][-1:]
        del job["coupon"]
        job["quote"] = {"mode": "fixed"}
        if payoff_id == "capital-guaranteed-sx5e":
            job["quote"] = {"mode": "solve_to_target", "quantity": "participation", "target_price": 102.,
                            "minimum": 0., "maximum": 5.}
        job["market"].update(spot=4400., volatility=0.)
        job["pricing"] = {**PRICING, "n_paths": 32}
        jobs.append(job)

    batch = _submit(client, owner, ISSUE_BATCHES, "quoted-issue-v1", jobs)
    assert run_compute_worker.process_next_batch("quoted-issue-test", 2, use_processes=True)
    issues = _poll(client, owner, batch)
    assert issues["status"] == "completed", issues
    results = [row["result"] for row in issues["jobs"]]
    assert results[0]["quote_result"]["quantity"] == "participation"
    assert results[0]["price"] == pytest.approx(102., abs=.01)

    marks, cashflows = [], []
    for result, (payoff, final_spot, gain, principal) in zip(results, witnesses, strict=True):
        vintage = result["vintage"]
        assert result["status"] == "issued"
        assert "annual_coupon" not in vintage and "coupon_rate" not in result
        assert vintage["terms"]["payoff"]["id"] == payoff["id"]
        fixings = [{"day": "2025-01-17", "spot": final_spot, "reference": "maturity"}]
        past = [] if gain == "participation" else [{"day": "2024-01-17", "spot": 3500., "reference": "past"}]
        response = client.post(LIFECYCLE, headers=owner, json={
            "vintage": vintage, "as_of": "2025-01-17", "fixings": past + fixings,
        })
        assert response.status_code == 200, response.text
        life = response.json()
        assert life["status"] == ("matured" if gain == "participation" else "called")
        assert life["redemption"]["amount"] == principal
        assert life["terms_reference"] == result["terms_reference"]
        if gain == "participation":
            assert life["barriers"] == [] and "coupon_claims" not in life
        else:
            assert "participation_claims" not in life
            assert [row["kind"] for row in life["barriers"]] == ["call", "call"]
        [claim] = life[f"{gain}_claims"]
        assert claim["kind"] == gain and claim["amount"] > 0
        cashflows.append((claim, life["redemption"]))
        for day, real_fixings in (("2025-01-16", past), ("2025-01-17", past + fixings)):
            marks.append({"vintage": vintage, "market": {**_market(day, 4400.), "volatility": 0.},
                          "pricing": {**PRICING, "n_paths": 32}, "fixings": real_fixings})

    batch = _submit(client, owner, MTM_BATCHES, "quoted-mtm-v1", marks)
    assert run_compute_worker.process_next_batch("quoted-mtm-test", 2, use_processes=True)
    response = _poll(client, owner, batch)
    assert response["status"] == "completed", response
    results = [job["result"] for job in response["jobs"]]
    for index, flows in enumerate(cashflows):
        live, settled = results[2 * index:2 * index + 2]
        assert live["status"] == "active" and live["claims"] == []
        assert ("next_call" in live) == (index == 2)
        assert settled["residual_pv"] == 0. and "next_call" not in settled
        assert [{k: row[k] for k in cash} for row, cash in zip(settled["claims"], flows, strict=True)] == list(flows)



@pytest.mark.parametrize("option,strike,fixing_spot", [("put", .95, 3500.), ("call", 1.05, 4500.)])
def test_european_option_through_http_and_worker(athena_api, option, strike, fixing_spot):
    client, headers = athena_api
    owner = headers["research"]
    payoff_id = f"european-{option}-sx5e"
    capability = next(row for row in client.get(PRICING_MODELS, headers=owner).json()["payoffs"]
                      if row["id"] == payoff_id)
    assert capability == {"id": payoff_id, "version": f"{payoff_id}-v1",
                          "issue_models": ["constant"], "mtm_models": ["constant"]}
    job = _issue_request()
    job["note_id"] = capability["id"]
    job["terms"]["payoff"] = {"id": capability["id"], "strike_ratio": strike}
    job["terms"]["observations"] = job["terms"]["observations"][-1:]
    del job["coupon"]
    job["quote"] = {"mode": "fixed"}
    job["market"]["volatility"] = 0.
    job["pricing"] = {**PRICING, "n_paths": 32}
    batch = _submit(client, owner, ISSUE_BATCHES, f"{payoff_id}-issue-v1", [job])
    assert run_compute_worker.process_next_batch(f"{payoff_id}-issue-test", 2, use_processes=True)
    issue_result = _poll(client, owner, batch)
    assert issue_result["status"] == "completed", issue_result
    issue = issue_result["jobs"][0]["result"]
    assert issue["status"] == "issued" and issue["price"] == 0.
    vintage = issue["vintage"]
    assert vintage["terms"]["payoff"] == job["terms"]["payoff"]

    initial = client.post(LIFECYCLE, headers=owner, json={
        "vintage": vintage, "as_of": "2025-01-16", "fixings": [],
    })
    assert initial.status_code == 200, initial.text
    assert initial.json().get("option_settlement") is None and initial.json()["redemption"] is None

    fixing = {"day": "2025-01-17", "spot": fixing_spot, "reference": f"{option}-fixing"}
    life = client.post(LIFECYCLE, headers=owner, json={"vintage": vintage, "as_of": fixing["day"], "fixings": [fixing]})
    assert life.status_code == 200, life.text
    receipt = life.json()
    assert receipt["status"] == "matured" and receipt["redemption"] is None
    assert receipt["terms_reference"] == issue["terms_reference"]
    expected = receipt["option_settlement"]
    assert expected["amount"] == pytest.approx(7.5)
    assert expected["kind"] == "option_payoff"

    jobs = [{"vintage": vintage, "market": {**_market(day, fixing_spot), "volatility": 0.},
             "pricing": job["pricing"], "fixings": fixings} for day, fixings in
            (("2025-01-16", []), (fixing["day"], [fixing]), ("2025-01-21", [fixing]))]
    batch = _submit(client, owner, MTM_BATCHES, f"{payoff_id}-mtm-v1", jobs)
    assert run_compute_worker.process_next_batch(f"{payoff_id}-mtm-test", 2, use_processes=True)
    mark_result = _poll(client, owner, batch)
    assert mark_result["status"] == "completed", mark_result
    live, matured, paid = [row["result"] for row in mark_result["jobs"]]
    assert live["residual_pv"] > 0. and live["claims"] == []
    assert matured["residual_pv"] == 0.
    [claim] = matured["claims"]
    assert {key: claim[key] for key in expected} == expected
    assert 0. < claim["pv"] < claim["amount"]
    assert paid["claims"] == []
    assert all("next_call" not in mark and mark["barriers"] == [] for mark in (live, matured, paid))
