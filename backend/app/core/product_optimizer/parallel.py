"""Ephemeral streaming bridge to Structura's shared process-batch executor."""
import logging
from queue import Empty, SimpleQueue
from threading import Event, Thread
import time

from ..compute.executor import run_batch
from .contracts import OptimizationCandidate

logger = logging.getLogger(__name__)


def iter_parallel_candidates(request, candidates, workers, deadline, phase="exploration", shortlist_size=0, external_cancel=None):
    """Yield completed candidates or None while waiting; own all worker cleanup.

    Only JSON data crosses the process boundary. Closing this iterator stops the
    shared executor before returning, so its caller can safely release admission.
    """
    messages = SimpleQueue()
    cancel = Event()
    expired = Event()
    request_data = request.model_dump(mode="json")
    by_id = {index: candidate for index, candidate in enumerate(candidates)}
    jobs = [(index, {"request": request_data, "candidate": candidate.model_dump(mode="json"),
                     "phase": phase, "shortlist_size": shortlist_size})
            for index, candidate in by_id.items()]

    def should_cancel():
        if time.monotonic() >= deadline:
            expired.set()
        return cancel.is_set() or expired.is_set() or bool(external_cancel and external_cancel())

    def on_result(_job_id, outcome):
        # Executor-generated cancellation errors are unfinished work, not failed
        # pricing candidates. Already received genuine outcomes remain usable.
        if not outcome.ok and should_cancel():
            return
        messages.put(("candidate", outcome))

    def execute():
        try:
            if not should_cancel():
                run_batch("product_optimizer_candidate", jobs, max_workers=workers,
                          use_processes=True, window_size=workers,
                          on_result=on_result, should_cancel=should_cancel)
        except Exception as exc:
            messages.put(("error", exc))
        finally:
            messages.put(("finished", None))

    coordinator = Thread(target=execute, name="product-optimizer-batch")
    coordinator.start()
    try:
        while True:
            try:
                kind, outcome = messages.get(timeout=.25)
            except Empty:
                yield None
                continue
            if kind == "finished":
                break
            if kind == "error":
                raise outcome
            if outcome.ok:
                yield OptimizationCandidate.model_validate(outcome.result)
            else:
                logger.error("Product Optimizer worker failed candidate=%s: %s",
                             by_id[outcome.job_id].candidate_id, outcome.error)
                candidate = by_id[outcome.job_id]
                if phase == "validation":
                    candidate.validation_status = "FAILED"
                    candidate.constraint_status = "REJECTED"
                else:
                    candidate.pricing_status = "FAILED"
                    candidate.analytics_status = "FAILED"
                candidate.errors.append("Calcul impossible pour ce candidat ; consulter les journaux serveur.")
                yield candidate
    finally:
        cancel.set()
        coordinator.join()
