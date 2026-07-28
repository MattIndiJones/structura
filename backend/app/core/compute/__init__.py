"""Generic parallel compute module — the one place in the codebase that
decides HOW an independent batch of jobs gets executed (thread pool vs
process pool) and tracked (queued/running/terminal, per-job error
isolation), so callers never reimplement concurrency primitives.

Not specific to any one feature: a VaR/ES study (many market scenarios), a
bulk KID regeneration, a portfolio-wide shock re-run, or a client's own
pricing model plugged in via pricers/external.py all submit through the
same job/executor/queue_store trio. See PLAN squishy-baking-sedgewick and
the VaR chantier discussion for the design rationale (in particular: why
ProcessPoolExecutor, not threads, is the real default here — the PayScript
engine evaluates scripts path-by-path in pure Python, which the GIL
serializes completely under threads).

Layout:
  job.py         — JobResult, the in-memory result shape run_batch() returns
  executor.py    — run_batch(): the actual thread/process dispatch
  queue_store.py — DB-backed queue (ComputeBatch/ComputeJob) a worker daemon
                   polls — see backend/scripts/run_compute_worker.py
  pricers/       — one function per job `kind`, registered in PRICERS;
                   payscript.py wraps the existing PayScript engine,
                   external.py documents the contract for a non-PayScript
                   product (a client's own model) without importing that
                   client's code into this process.
"""
