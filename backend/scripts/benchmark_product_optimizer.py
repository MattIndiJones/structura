"""Offline direct-pricing benchmark; no server, database, or market download."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.service import run_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {
        "strike_date": "2026-10-08", "convention": "modified_following", "currency": "EUR",
        "market": {"as_of": "2026-10-08", "source": "USER_ASSUMPTION", "rate": .03,
                   "underlyings": [{"ticker": "SYNTHETIC", "name": "Hypothèse synthétique",
                                    "currency": "EUR", "sigma": .20, "q": .02}],
                   "correlation": [[1.]]},
        "ranges": {"maturity_months": {"minimum": 36, "maximum": 36, "step": 12},
                   "protection_barrier": {"minimum": .55, "maximum": .70, "step": .05},
                   "autocall_trigger": {"minimum": 1, "maximum": 1, "step": .05},
                   "observation_months": [3]},
        "constraints": {"price_tolerance": .03},
        "search": {"simulations": args.simulations, "max_candidates": 4, "parallel_workers": 1},
    }
    initial_children = {p.pid for p in multiprocessing.active_children()}
    results = []
    for workers in (1, args.workers):
        configuration = deepcopy(data)
        configuration["search"]["parallel_workers"] = workers
        request = OptimizationRequest.model_validate(configuration)
        start = time.perf_counter()
        final = None
        for event in run_events(request):
            if event["type"] == "progress":
                print(f"workers={workers} completed={event['completed']}/{event['total']}", flush=True)
            if event["type"] == "result":
                final = event["result"]
        elapsed = time.perf_counter() - start
        if final is None or not final["complete"] or final["statistics"]["failed"]:
            raise RuntimeError("Benchmark incomplet ou candidat en échec.")
        results.append({"workers": workers, "elapsed_seconds": elapsed, "result": final})
        print(f"workers={workers} elapsed_seconds={elapsed:.3f}", flush=True)
    serial, parallel = results
    identical = (serial["result"]["candidates"] == parallel["result"]["candidates"]
                 and serial["result"]["recommended_id"] == parallel["result"]["recommended_id"])
    remaining_children = [p.pid for p in multiprocessing.active_children() if p.pid not in initial_children]
    report = {"cpu_count": os.cpu_count(), "python_version": sys.version,
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "identical_economics_and_ranking": identical,
              "remaining_owned_children": remaining_children,
              "speedup": serial["elapsed_seconds"] / parallel["elapsed_seconds"], "runs": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not identical or remaining_children:
        raise RuntimeError("Écart séquentiel/parallèle ou processus de calcul encore actif.")
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
