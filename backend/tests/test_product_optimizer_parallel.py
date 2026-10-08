"""Process equivalence, resource admission and streaming cancellation."""
from copy import deepcopy
import multiprocessing
import json
from threading import Event, enumerate as active_threads

import pytest
from pydantic import ValidationError

from backend.app.core.compute.job import JobResult
from backend.app.core.product_optimizer import parallel, service
from backend.app.core.product_optimizer.contracts import OptimizationRequest, MAX_PARALLEL_MEMORY_BYTES
from backend.tests.test_product_optimizer import payload, api_client


def multi_request(workers=2, worst_of=False):
    data = payload()
    data["ranges"]["protection_barrier"]["maximum"] = .7
    data["search"]["parallel_workers"] = workers
    if worst_of:
        other = deepcopy(data["market"]["underlyings"][0])
        other.update(ticker="TEST2", sigma=.25)
        data["market"]["underlyings"].append(other)
        data["market"]["correlation"] = [[1, .4], [.4, 1]]
    return OptimizationRequest.model_validate(data)


@pytest.mark.parametrize("workers", [0, 5])
def test_parallel_worker_count_is_bounded(workers):
    with pytest.raises(ValidationError):
        multi_request(workers)


def test_estimate_accounts_for_concurrent_memory_and_cpu(monkeypatch):
    monkeypatch.setattr(service.os, "cpu_count", lambda: 8)
    one = service.estimate_search(multi_request(1))
    two = service.estimate_search(multi_request(2))
    assert one["allowed"] and two["allowed"]
    assert two["execution"]["workers"] == 2
    assert two["budget"]["work_units"] == one["budget"]["work_units"]
    assert two["budget"]["estimated_peak_bytes"] == 2 * one["budget"]["estimated_peak_bytes"]
    monkeypatch.setattr(service.os, "cpu_count", lambda: 1)
    limited = service.estimate_search(multi_request(4))
    assert limited["execution"]["workers"] == 1
    assert limited["execution"]["mode"] == "sequential"


def test_parallelism_is_reduced_before_memory_budget_refusal(monkeypatch):
    monkeypatch.setattr(service.os, "cpu_count", lambda: 8)
    request = multi_request(4, worst_of=True)
    request.ranges.maturity_months.minimum = 60
    request.ranges.maturity_months.maximum = 60
    request.search.simulations = 10000
    one = service.estimate_search(request)
    assert one["execution"]["workers"] < 4
    assert one["budget"]["estimated_peak_bytes"] <= MAX_PARALLEL_MEMORY_BYTES


def test_holdout_peak_exceeding_memory_cap_is_refused_even_sequentially():
    request = multi_request(1, worst_of=True)
    request.ranges.maturity_months.minimum = 60
    request.ranges.maturity_months.maximum = 60
    request.search.simulations = 15000
    estimate = service.estimate_search(request)
    assert estimate["budget"]["estimated_peak_bytes"] > MAX_PARALLEL_MEMORY_BYTES
    assert not estimate["allowed"]


@pytest.mark.parametrize("worst_of", [False, True])
def test_spawned_optimizer_matches_sequential_economics_and_ranking(worst_of):
    serial = list(service.run_events(multi_request(1, worst_of)))[-1]["result"]
    parallel_result = list(service.run_events(multi_request(2, worst_of)))[-1]["result"]
    assert parallel_result["estimate"]["execution"]["workers"] == 2
    assert parallel_result["complete"]
    assert parallel_result["candidates"] == serial["candidates"]
    assert parallel_result["recommended_id"] == serial["recommended_id"]
    assert parallel_result["statistics"] == serial["statistics"]


def test_out_of_order_process_failure_is_sanitized_and_results_are_sorted(monkeypatch):
    def batch(_kind, jobs, **options):
        for job_id, _data in reversed(jobs):
            options["on_result"](job_id, JobResult(job_id, False, error="private worker detail"))
        return []
    monkeypatch.setattr(parallel, "run_batch", batch)
    result = list(service.run_events(multi_request()))[-1]["result"]
    assert result["complete"]
    assert result["statistics"]["failed"] == 3
    assert [c["candidate_id"] for c in result["candidates"]] == ["C0001", "C0002", "C0003"]
    assert "private worker detail" not in str(result)


def test_closing_stream_signals_cancellation_and_joins_coordinator(monkeypatch):
    cancelled = Event()
    def batch(_kind, jobs, **options):
        while not options["should_cancel"]():
            cancelled.wait(.01)
        cancelled.set()
        for job_id, _data in jobs:
            options["on_result"](job_id, JobResult(job_id, False, error="Calcul annulé par l'utilisateur."))
        return []
    monkeypatch.setattr(parallel, "run_batch", batch)
    iterator = service.run_events(multi_request())
    assert next(iterator)["type"] == "started"
    assert next(iterator)["type"] == "heartbeat"
    iterator.close()
    assert cancelled.is_set()
    assert not any(t.name == "product-optimizer-batch" for t in active_threads())


def test_expired_parallel_search_has_no_false_failed_candidates(monkeypatch):
    def batch(_kind, jobs, **options):
        # Simulate admission overhead consuming the complete wall-clock budget.
        monkeypatch.setattr(parallel.time, "monotonic", lambda: 10**12)
        assert options["should_cancel"]()
        for job_id, _data in jobs:
            options["on_result"](job_id, JobResult(job_id, False, error="Calcul annulé par l'utilisateur."))
        return []
    monkeypatch.setattr(parallel, "run_batch", batch)
    result = list(service.run_events(multi_request()))[-1]["result"]
    assert not result["complete"]
    assert result["statistics"]["not_evaluated"] == 3
    assert result["statistics"]["failed"] == 0
    assert result["recommended_id"] is None


def test_cancelling_real_process_pool_leaves_no_owned_children():
    baseline = {p.pid for p in multiprocessing.active_children()}
    iterator = service.run_events(multi_request())
    assert next(iterator)["type"] == "started"
    assert next(iterator)["type"] == "heartbeat"
    assert any(p.pid not in baseline for p in multiprocessing.active_children())
    iterator.close()
    assert not any(p.pid not in baseline for p in multiprocessing.active_children())


def test_cancelling_real_holdout_process_pool_leaves_no_owned_children():
    baseline = {p.pid for p in multiprocessing.active_children()}
    iterator = service.run_events(multi_request())
    for event in iterator:
        if event["type"] == "validation_started":
            break
    else:
        pytest.fail("No holdout phase was started.")
    assert next(iterator)["type"] == "heartbeat"
    assert any(p.pid not in baseline for p in multiprocessing.active_children())
    iterator.close()
    assert not any(p.pid not in baseline for p in multiprocessing.active_children())


def test_api_parallel_stream_exposes_budget_and_releases_capacity(api_client):
    from backend.app.api import product_optimizer as api
    client, _, _ = api_client
    response = client.post("/api/product-optimizer/run", json=multi_request().model_dump(mode="json"))
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "run_registered"
    assert events[1]["estimate"]["execution"]["workers"] == 2
    assert events[-1]["type"] == "result"
    assert events[-1]["result"]["complete"]
    assert api._capacity.acquire(blocking=False)
    api._capacity.release()
