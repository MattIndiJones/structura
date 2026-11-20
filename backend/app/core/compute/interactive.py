"""Interactive pricing off the request thread: warm processes, a deadline,
cancellation (P1-4).

The Pricer used to run its Monte Carlo inside the HTTP request, on a server
thread: no deadline, no way to stop it, and a script that loops held the
thread until the server was restarted. Closing the browser changed nothing.

Here each calculation runs in a separate worker process that the server can
kill. Workers are started ahead of time: a fresh process on Windows spends 4
to 7 seconds importing the application before it can price anything
(measured 19/11/2026), against about a millisecond for a warm one. A worker
that is killed — cancellation, deadline, client gone — is replaced in the
background; the others keep running.

Not the DB queue of queue_store.py: that one waits for a worker daemon
started separately, which is right for a VaR study and wrong for a price the
user is waiting for on screen. Jobs live in memory and die with the server,
like the HTTP request they replace.
"""
from __future__ import annotations

import collections
import logging
import multiprocessing
import os
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from importlib import import_module
from multiprocessing.connection import wait as wait_for_connections
from typing import Any, Callable

logger = logging.getLogger(__name__)

# "app" under run.py, "backend.app" under pytest: the worker imports the
# same package as the server.
_PACKAGE = __name__.rsplit(".core.", 1)[0]

DEFAULT_WORKERS = 2
DEFAULT_TIMEOUT_SECONDS = 600.0
# A job nobody has asked about for this long is stopped: the Pricer polls
# about twice a second, and a background tab is throttled to once a minute.
DEFAULT_ABANDON_SECONDS = 120.0
# Terminal jobs stay readable this long, then are forgotten.
RETENTION_SECONDS = 600.0
MAX_ACTIVE_PER_USER = 4

TERMINAL = frozenset({"done", "failed", "cancelled", "timeout", "abandoned"})


def _env_number(name: str, default: float, cast=float, minimum=None):
    try:
        value = cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, value) if minimum is not None else value


# ── What runs inside a worker ──────────────────────────────────────

# The Pricer's analyses, run like the price (P1-4, second step). Each takes
# only its validated request. Not here: the stress scenarios and the MtF
# comparison, which start their own process pool — a worker is a daemon
# process, forbidden to have children, and killing it on cancellation would
# leave its pool running.
ANALYSES = {
    "profile": ("api.pricing", "profile_endpoint"),
    "paths": ("api.pricing", "paths_endpoint"),
    "proba": ("api.pricing", "proba_endpoint"),
    "backtest": ("api.pricing", "backtest_endpoint"),
    "backtest_compare": ("api.pricing", "backtest_compare_endpoint"),
    "mtf": ("api.pricing", "mtf_endpoint"),
    "mtf_drilldown": ("api.pricing", "mtf_drilldown_endpoint"),
    "solve": ("api.simulation", "solve_endpoint"),
    "grid": ("api.simulation", "grid_endpoint"),
}
# A backtest over years of history, a candidate comparison, a solver or a
# grid can legitimately run longer than a price: their deadline is longer.
LONG_RUNNING = frozenset({"backtest", "backtest_compare", "solve", "grid", "mtf"})
LONG_TIMEOUT_SECONDS = 1800.0


def execute(kind: str, request: Any) -> dict:
    """Run one interactive calculation through its HTTP endpoint function,
    so the queued path returns exactly what the synchronous route returns."""
    from fastapi import HTTPException
    from fastapi.encoders import jsonable_encoder

    if kind == "price":
        endpoint = import_module(f"{_PACKAGE}.api.pricing").price_endpoint
        call = lambda: endpoint(request)                          # noqa: E731
    elif kind in ANALYSES:
        module, name = ANALYSES[kind]
        endpoint = getattr(import_module(f"{_PACKAGE}.{module}"), name)
        call = lambda: endpoint(request)                          # noqa: E731
    elif kind in ("in_life", "implied_funding"):
        module = import_module(f"{_PACKAGE}.api.inlife")
        endpoint = module.price_in_life if kind == "in_life" else module.implied_funding
        # The user only gates the route (get_current_pricer), checked by the
        # server before the job was accepted; the calculation never reads it.
        call = lambda: endpoint(request, None)                    # noqa: E731
    else:
        return dict(ok=False, status_code=400, detail=f"Calcul inconnu : {kind!r}.")
    try:
        return dict(ok=True, result=jsonable_encoder(call()))
    except HTTPException as error:
        return dict(ok=False, status_code=error.status_code, detail=error.detail)
    except Exception as error:                                     # noqa: BLE001
        return dict(ok=False, status_code=500,
                    detail=f"Erreur interne du calcul ({type(error).__name__}).",
                    traceback=traceback.format_exc())


WARM_MODULES = ("api.pricing", "api.inlife", "api.simulation")


def _worker_main(connection, target, warm_modules) -> None:
    for name in warm_modules:
        import_module(f"{_PACKAGE}.{name}")
    connection.send(("ready", None, None))
    while True:
        try:
            message = connection.recv()
        except (EOFError, OSError):          # the server is gone
            return
        if message is None:
            return
        job_id, kind, request = message
        try:
            outcome = target(kind, request)
        except BaseException as error:       # noqa: BLE001 — must answer
            outcome = dict(ok=False, status_code=500,
                           detail=f"Erreur interne du calcul ({type(error).__name__}).",
                           traceback=traceback.format_exc())
        try:
            connection.send(("result", job_id, outcome))
        except (EOFError, OSError):
            return


# ── Server side ────────────────────────────────────────────────────

@dataclass
class Job:
    id: str
    user_id: int | None
    kind: str
    request: Any
    created: float = field(default_factory=time.monotonic)
    status: str = "queued"
    started: float | None = None
    finished: float | None = None
    last_seen: float = field(default_factory=time.monotonic)
    cancel_requested: bool = False
    outcome: dict | None = None

    def snapshot(self, position: int | None = None) -> dict:
        now = time.monotonic()
        body = dict(job_id=self.id, kind=self.kind, status=self.status,
                    queue_position=position,
                    elapsed_ms=round(1000 * ((self.finished or now) - self.started))
                    if self.started else 0)
        if self.status == "done":
            body["result"] = self.outcome["result"]
        elif self.status in TERMINAL:
            body["status_code"] = (self.outcome or {}).get("status_code")
            body["detail"] = (self.outcome or {}).get("detail")
        return body


class _Slot:
    def __init__(self, context, target, warm_modules):
        parent, child = context.Pipe()
        self.connection = parent
        self.process = context.Process(target=_worker_main, args=(child, target, warm_modules),
                                       name="structura-pricing", daemon=True)
        self.process.start()
        child.close()
        self.ready = False
        self.job: Job | None = None

    def stop(self, *, kill: bool) -> None:
        try:
            if kill:
                self.process.terminate()
            else:
                self.connection.send(None)
        except (OSError, ValueError):
            pass
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2.0)
        self.connection.close()


class QueueFull(Exception):
    pass


class InteractiveRunner:
    """Warm worker processes and an in-memory queue of interactive jobs."""

    def __init__(self, workers: int | None = None, *, timeout: float | None = None,
                 abandon_after: float | None = None, retention: float = RETENTION_SECONDS,
                 target: Callable[[str, Any], dict] = execute,
                 warm_modules: tuple[str, ...] = WARM_MODULES,
                 max_active_per_user: int = MAX_ACTIVE_PER_USER):
        self.workers = workers or _env_number("STRUCTURA_PRICING_WORKERS", DEFAULT_WORKERS, int, 1)
        self.timeout = timeout or _env_number("STRUCTURA_PRICING_TIMEOUT_SECONDS",
                                              DEFAULT_TIMEOUT_SECONDS, float, 1.0)
        self.abandon_after = abandon_after or DEFAULT_ABANDON_SECONDS
        self.retention = retention
        self.max_active_per_user = max_active_per_user
        self._target, self._warm = target, warm_modules
        self._context = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._queue: collections.deque[str] = collections.deque()
        self._slots: list[_Slot] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def timeout_for(self, kind: str) -> float:
        return max(self.timeout, LONG_TIMEOUT_SECONDS) if kind in LONG_RUNNING else self.timeout

    # -- lifecycle --

    def start(self) -> "InteractiveRunner":
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._supervise, name="structura-pricing-supervisor",
                                                daemon=True)
                self._thread.start()
        return self

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        with self._lock:
            slots, self._slots = self._slots, []
            for job_id in list(self._queue):
                self._finish(self._jobs[job_id], "cancelled", dict(
                    status_code=503, detail="Serveur arrêté pendant le calcul."))
            self._queue.clear()
        for slot in slots:
            if slot.job is not None:
                self._finish(slot.job, "cancelled", dict(status_code=503,
                                                         detail="Serveur arrêté pendant le calcul."))
            slot.stop(kill=slot.job is not None or not slot.ready)

    # -- requests --

    def submit(self, kind: str, request: Any, user_id: int | None) -> dict:
        self.start()
        with self._lock:
            active = sum(1 for job in self._jobs.values()
                         if job.user_id == user_id and job.status in ("queued", "running"))
            if active >= self.max_active_per_user:
                raise QueueFull(f"{active} calculs déjà en cours pour cet utilisateur : "
                                "attendez leur fin ou annulez-en un.")
            job = Job(uuid.uuid4().hex, user_id, kind, request)
            self._jobs[job.id] = job
            self._queue.append(job.id)
            return job.snapshot(len(self._queue))

    def status(self, job_id: str, user_id: int | None) -> dict | None:
        with self._lock:
            job = self._owned(job_id, user_id)
            if job is None:
                return None
            job.last_seen = time.monotonic()
            position = (list(self._queue).index(job.id) + 1) if job.status == "queued" else None
            return job.snapshot(position)

    def cancel(self, job_id: str, user_id: int | None) -> dict | None:
        with self._lock:
            job = self._owned(job_id, user_id)
            if job is None:
                return None
            if job.status == "queued":
                self._queue.remove(job.id)
                self._finish(job, "cancelled", dict(status_code=499, detail="Calcul annulé."))
            elif job.status == "running":
                job.cancel_requested = True     # the supervisor kills its worker
            return job.snapshot()

    def wait(self, job_id: str, user_id: int | None, timeout: float) -> dict | None:
        """Test and script helper: poll until the job is terminal."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.status(job_id, user_id)
            if state is None or state["status"] in TERMINAL:
                return state
            time.sleep(0.05)
        return self.status(job_id, user_id)

    def _owned(self, job_id, user_id):
        job = self._jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None

    # -- supervisor --

    def _finish(self, job: Job, status: str, outcome: dict | None) -> None:
        job.status, job.outcome, job.finished = status, outcome, time.monotonic()

    def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:                                      # noqa: BLE001
                logger.exception("Superviseur du pricing interactif : cycle en échec")
                time.sleep(0.5)

    def _tick(self) -> None:
        with self._lock:
            self._slots = [slot for slot in self._slots if self._alive(slot)]
            while len(self._slots) < self.workers:
                self._slots.append(_Slot(self._context, self._target, self._warm))
            connections = [slot.connection for slot in self._slots]
        ready = wait_for_connections(connections, timeout=0.1)
        with self._lock:
            for slot in self._slots:
                if slot.connection in ready:
                    self._receive(slot)
            self._enforce_deadlines()
            self._dispatch()
            self._forget_old()

    def _alive(self, slot: _Slot) -> bool:
        if slot.process.is_alive() and not slot.connection.closed:
            return True
        if slot.job is not None and slot.job.status == "running":
            self._finish(slot.job, "failed", dict(
                status_code=500, detail="Le processus de calcul s'est arrêté pendant le pricing."))
            logger.error("Processus de pricing arrêté (code %s) pendant %s",
                         slot.process.exitcode, slot.job.kind)
        if not slot.connection.closed:
            slot.connection.close()
        return False

    def _receive(self, slot: _Slot) -> None:
        try:
            tag, job_id, outcome = slot.connection.recv()
        except (EOFError, OSError):
            slot.connection.close()            # _alive() replaces it next tick
            return
        if tag == "ready":
            slot.ready = True
            return
        job, slot.job = slot.job, None
        if job is None or job.id != job_id or job.status != "running":
            return
        if outcome.get("ok"):
            self._finish(job, "done", outcome)
            return
        if outcome.get("traceback"):
            logger.error("Pricing interactif %s en échec\n%s", job.kind, outcome["traceback"])
        self._finish(job, "failed", dict(status_code=outcome.get("status_code", 500),
                                         detail=outcome.get("detail")))

    def _enforce_deadlines(self) -> None:
        now = time.monotonic()
        for slot in self._slots:
            job = slot.job
            if job is None:
                continue
            if job.cancel_requested:
                status, outcome = "cancelled", dict(status_code=499, detail="Calcul annulé.")
            elif now - job.started > self.timeout_for(job.kind):
                status, outcome = "timeout", dict(status_code=504, detail=(
                    f"Calcul interrompu après {self.timeout_for(job.kind):g} s. Réduisez le nombre de "
                    "trajectoires ou de Greeks, ou vérifiez que le script se termine."))
                logger.warning("Pricing interactif %s interrompu après %g s", job.kind, self.timeout_for(job.kind))
            elif now - job.last_seen > self.abandon_after:
                status, outcome = "abandoned", dict(status_code=499, detail=(
                    "Calcul arrêté : plus aucun écran ne le suivait."))
            else:
                continue
            slot.job = None
            self._finish(job, status, outcome)
            slot.stop(kill=True)               # replaced on the next tick
        self._slots = [slot for slot in self._slots if slot.process.is_alive()]

    def _dispatch(self) -> None:
        idle = [slot for slot in self._slots if slot.ready and slot.job is None]
        while self._queue and idle:
            job = self._jobs[self._queue.popleft()]
            if job.status != "queued":
                continue
            slot = idle.pop()
            try:
                slot.connection.send((job.id, job.kind, job.request))
            except (OSError, ValueError) as error:
                self._finish(job, "failed", dict(status_code=500, detail=(
                    f"Envoi du calcul impossible ({type(error).__name__}).")))
                continue
            job.status, job.started, slot.job = "running", time.monotonic(), job

    def _forget_old(self) -> None:
        now = time.monotonic()
        for job_id in [job.id for job in self._jobs.values()
                       if job.status in TERMINAL and now - job.finished > self.retention]:
            del self._jobs[job_id]


_runner: InteractiveRunner | None = None
_runner_lock = threading.Lock()


def get_runner() -> InteractiveRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = InteractiveRunner()
        return _runner


def shutdown_runner() -> None:
    global _runner
    with _runner_lock:
        runner, _runner = _runner, None
    if runner is not None:
        runner.shutdown()
