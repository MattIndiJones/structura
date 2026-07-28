"""Generic parallel batch dispatch — thread pool vs process pool, and per-job
error isolation, in exactly one place so no caller (a VaR study, a bulk KID
regen, a portfolio-wide shock re-run...) reimplements concurrency itself.

Why ProcessPoolExecutor is the real default, not a tuning knob: the
PayScript engine's _eval_paths evaluates a script's AT/PAY/IF body
path-by-path in pure Python (see core/payscript/engine.py) — the GIL
serializes that completely under threads, so a ThreadPoolExecutor would
barely parallelize a batch of PayScript reprices at all. Threads stay
available (use_processes=False) for a pricer that's genuinely I/O-bound
(e.g. an external pricer that mostly waits on a network call), where
spawning a whole OS process per job would be wasted overhead.

Windows note: multiprocessing here uses spawn (no fork on Windows), which
re-imports this whole module (and whatever a pricer lazily imports) in every
worker process — a few hundred ms of one-time cost per worker, amortized
over every job that worker picks up within the same `run_batch()` call, not
paid per job. This is also why a job's payload must be plain, picklable data
(see pricers/payscript.py's docstring) — a worker process has never seen the
caller's live Python objects."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Callable, Optional

from .job import JobResult
from .pricers import PRICERS


def _run_one(kind: str, payload: dict) -> dict:
    """Module-level (picklable) dispatch target — the actual function
    shipped to a worker process/thread. Looks up the pricer by `kind` and
    calls it with the raw payload; never touches the DB (queue bookkeeping —
    ComputeJob/ComputeBatch — is the caller's responsibility, run in the
    process that owns the Session, via queue_store.py's on_result callback)."""
    pricer = PRICERS.get(kind)
    if pricer is None:
        raise ValueError(f"Type de job de calcul inconnu: {kind!r} "
                         f"(types enregistrés: {sorted(PRICERS)})")
    return pricer(payload)


def run_batch(
    kind: str,
    jobs: list[tuple[int, dict]],
    max_workers: int = 4,
    use_processes: bool = True,
    on_result: Optional[Callable[[int, JobResult], None]] = None,
) -> list[JobResult]:
    """Runs every (job_id, payload) pair independently and in parallel,
    isolating failures per job — one bad scenario/deal must never abort the
    rest of the batch, same contract api/shocks.py's _run_shock_on_book
    already has one level down (per deal within a single shock); this is the
    same idea one level up (per job within a batch of anything).

    on_result, if given, fires synchronously as each job completes (not
    necessarily in job_index order — as_completed yields whichever finishes
    first) — this is how queue_store.py persists partial progress without
    waiting for the whole batch to drain."""
    if not jobs:
        return []
    Executor = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    results: list[JobResult] = []
    with Executor(max_workers=max(1, min(max_workers, len(jobs)))) as ex:
        future_map = {ex.submit(_run_one, kind, payload): job_id for job_id, payload in jobs}
        for future in as_completed(future_map):
            job_id = future_map[future]
            try:
                jr = JobResult(job_id=job_id, ok=True, result=future.result())
            except Exception as exc:
                jr = JobResult(job_id=job_id, ok=False, error=str(exc))
            results.append(jr)
            if on_result is not None:
                on_result(job_id, jr)
    return results
