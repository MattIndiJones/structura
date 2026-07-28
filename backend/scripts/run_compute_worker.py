#!/usr/bin/env python3
"""Daemon worker for the generic compute module (backend/app/core/compute/).

Polls compute_batches for queued (or stale-running, i.e. abandoned by a
crashed worker) work, executes every job of a claimed batch in parallel
(ProcessPoolExecutor by default — see core/compute/executor.py for why
threads don't help the PayScript engine), and persists each job's result as
soon as it completes so a caller can poll progress without waiting for the
whole batch to drain.

NEVER started automatically by an assistant session — exactly like
backend/run.py (see CLAUDE.md), this is Philippe's own long-running process:
start it, stop it, restart it after a code change, on his own machine.

Usage (from the repo root):
    .venv\\Scripts\\python.exe backend\\scripts\\run_compute_worker.py
    .venv\\Scripts\\python.exe backend\\scripts\\run_compute_worker.py --once
    .venv\\Scripts\\python.exe backend\\scripts\\run_compute_worker.py --poll-seconds 5 --max-workers 4
    .venv\\Scripts\\python.exe backend\\scripts\\run_compute_worker.py --threads   # only for an I/O-bound pricer, see executor.py
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session
from backend.app.db.database import engine, init_db
from backend.app.core.compute.queue_store import (
    claim_next_batch, pending_jobs, record_job_result, finalize_batch,
)
from backend.app.core.compute.executor import run_batch


def process_next_batch(worker_name: str, max_workers: int, use_processes: bool) -> bool:
    """Claims and fully drains one batch (blocking until every job is
    dispatched). Returns False if nothing was queued/claimable, so the
    caller's poll loop knows whether to sleep."""
    with Session(engine) as session:
        batch = claim_next_batch(session, worker_name)
        if not batch:
            return False
        batch_id, kind, label = batch.id, batch.kind, batch.label
        jobs = pending_jobs(session, batch_id)
        job_payloads = [(j.id, json.loads(j.payload_json)) for j in jobs]

    print(f"[{worker_name}] batch #{batch_id} ({kind!r}, {label!r}) — {len(job_payloads)} job(s)")

    def _on_result(job_id, jr):
        with Session(engine) as s:
            record_job_result(s, job_id, jr.ok, jr.result, jr.error)

    run_batch(kind, job_payloads, max_workers=max_workers, use_processes=use_processes,
              on_result=_on_result)

    with Session(engine) as session:
        final = finalize_batch(session, batch_id)
    print(f"[{worker_name}] batch #{batch_id} -> {final.status} "
          f"({final.completed_jobs} ok / {final.failed_jobs} failed)")
    return True


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--once", action="store_true",
                   help="Traite au plus un batch puis quitte (pas de boucle de poll)")
    p.add_argument("--poll-seconds", type=float, default=2.0,
                   help="Intervalle entre deux vérifications de la file quand elle est vide (défaut: 2s)")
    p.add_argument("--max-workers", type=int, default=4,
                   help="Nombre de jobs traités en parallèle par batch (défaut: 4)")
    p.add_argument("--threads", action="store_true",
                   help="Utilise des threads au lieu de processus — déconseillé pour du repricing "
                        "PayScript (voir core/compute/executor.py), réservé à un pricer externe I/O-bound")
    args = p.parse_args()

    init_db()
    worker_name = f"{socket.gethostname()}-{os.getpid()}"
    print(f"Compute worker '{worker_name}' démarré "
          f"(max_workers={args.max_workers}, {'threads' if args.threads else 'processus'}) "
          f"— Ctrl+C pour arrêter.")

    while True:
        did_work = process_next_batch(worker_name, args.max_workers, use_processes=not args.threads)
        if args.once:
            break
        if not did_work:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    # Required on Windows: multiprocessing uses spawn (no fork), which
    # re-imports this module in every worker process — without this guard,
    # each spawned worker would re-run main() itself instead of just
    # importing run_batch's target function.
    main()
