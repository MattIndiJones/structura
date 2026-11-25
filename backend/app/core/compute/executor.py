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
import logging
from contextvars import ContextVar
from concurrent.futures import (
    FIRST_COMPLETED, BrokenExecutor, ThreadPoolExecutor, ProcessPoolExecutor, wait,
)
from itertools import chain
import time
from typing import Callable, Optional

from .job import JobResult
from .pricers import PRICERS

logger = logging.getLogger(__name__)

# Cancellation handed down by whoever runs a calculation on behalf of a
# cancellable job (core/compute/interactive.py, the stress scenarios and the
# MtF comparison), without threading a callback through every endpoint that
# happens to call run_batch. An explicit should_cancel takes precedence.
ambient_cancel: ContextVar[Optional[Callable[[], bool]]] = ContextVar("structura_ambient_cancel", default=None)


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
    should_cancel: Optional[Callable[[], bool]] = None,
    on_tick: Optional[Callable[[], None]] = None,
    job_timeout_seconds: float = 300.0,
    window_size: int | None = None,
    more_jobs: Optional[Callable[[int], list[tuple[int, dict]]]] = None,
) -> list[JobResult]:
    """Runs every (job_id, payload) pair independently and in parallel,
    isolating failures per job — one bad scenario/deal must never abort the
    rest of the batch, same contract api/shocks.py's _run_shock_on_book
    already has one level down (per deal within a single shock); this is the
    same idea one level up (per job within a batch of anything).

    on_result, if given, fires synchronously as each job completes (not
    necessarily in job_index order — as_completed yields whichever finishes
    first) — this is how queue_store.py persists partial progress without
    waiting for the whole batch to drain.

    A durable caller can supply more_jobs(limit) to claim up to limit jobs
    when active work falls below worker capacity. This keeps one warm pool
    while bounding the number of claimed jobs. An empty refill ends the
    source, and a timeout or cancelled lease ends the pool as usual.
    """
    if not jobs:
        return []
    if should_cancel is None:
        should_cancel = ambient_cancel.get()
    Executor = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    results: list[JobResult] = []
    workers = max(1, min(max_workers, len(jobs)))
    window = max(workers, min(window_size or workers * 2, len(jobs)))
    ex = Executor(max_workers=workers)
    remaining = iter(jobs)
    active = {}
    stopped = False

    def emit(jr: JobResult) -> None:
        results.append(jr)
        if on_result is not None:
            on_result(jr.job_id, jr)

    def stop_processes() -> None:
        nonlocal stopped
        # Python 3.11 has no public terminate_workers().  Cancellation must
        # nevertheless stop CPU-bound PayScript work on Windows, so terminate
        # the executor's owned child processes before a non-waiting shutdown.
        if use_processes:
            for process in list(getattr(ex, "_processes", {}).values()):
                if process.is_alive():
                    process.terminate()
            for process in list(getattr(ex, "_processes", {}).values()):
                process.join(timeout=1.0)
        ex.shutdown(wait=False, cancel_futures=True)
        stopped = True

    def fill() -> None:
        nonlocal remaining, more_jobs
        while len(active) < window:
            job = next(remaining, None)
            if job is None:
                if more_jobs is None or len(active) >= workers:
                    return
                refill = more_jobs(window - len(active))
                if not refill:
                    more_jobs = None
                    return
                remaining = iter(refill)
                continue
            job_id, payload = job
            try:
                future = ex.submit(_run_one, kind, payload)
            except BrokenExecutor:
                remaining = chain((job,), remaining)
                raise
            active[future] = (job_id, time.monotonic())

    try:
        fill()
        while active:
            if on_tick is not None:
                on_tick()
            if should_cancel is not None and should_cancel():
                ids = [job_id for job_id, _started in active.values()]
                stop_processes()
                for job_id in ids:
                    emit(JobResult(job_id=job_id, ok=False,
                                   error="Calcul annulé par l'utilisateur."))
                return results

            done, _ = wait(active, timeout=0.25, return_when=FIRST_COMPLETED)
            now = time.monotonic()
            expired = [future for future, (_job_id, started) in active.items()
                       if now - started > job_timeout_seconds]
            if expired:
                timed_out = {active[future][0] for future in expired}
                interrupted = [job_id for job_id, _started in active.values()]
                stop_processes()
                for job_id in interrupted:
                    reason = (f"Timeout de calcul après {job_timeout_seconds:g} s."
                              if job_id in timed_out else
                              "Calcul interrompu après le timeout d'un autre job.")
                    emit(JobResult(job_id=job_id, ok=False, error=reason))
                return results

            pool_failure = None
            for future in done:
                job_id, _started = active.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    # A process pool attaches the worker's traceback as the cause.
                    logger.warning("Calcul %s en échec", job_id, exc_info=exc)
                    emit(JobResult(job_id=job_id, ok=False, error=str(exc)))
                    if isinstance(exc, BrokenExecutor):
                        pool_failure = exc
                else:
                    emit(JobResult(job_id=job_id, ok=True, result=result))
            if pool_failure is not None:
                raise pool_failure
            fill()
    except BrokenExecutor as exc:
        # All these jobs were already handed to the executor or claimed by
        # the caller's refill. Leave unclaimed jobs for a fresh pool.
        for job_id, _started in active.values():
            emit(JobResult(job_id=job_id, ok=False, error=str(exc)))
        for job_id, _payload in remaining:
            emit(JobResult(job_id=job_id, ok=False, error=str(exc)))
    finally:
        if not stopped:
            ex.shutdown(wait=True, cancel_futures=False)
    return results
