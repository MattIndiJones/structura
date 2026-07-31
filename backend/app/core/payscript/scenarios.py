"""
Stress scenario grid — price the product under combined spot x vol shocks.

Unlike simulation.py (which shocks script PARAMs), this shocks MARKET data:
spot (multiplicative, e.g. -10% -> spot_mult=0.90) and vol (additive, e.g.
+5pp -> vol_add=0.05), applied uniformly to every underlying. Both are
already native parameters of engine.run_mc (the same mechanism compute_greeks
uses for bump-and-reprice), so this module is just the grid loop around it —
no new pricing primitive needed, and every model (constant/heston/sabr/
localvol) is supported as-is since vol_add is wired into all four.

Same seed as the main pricing run (common random numbers) keeps the grid
smooth and comparable cell-to-cell: differences between cells reflect the
shock, not Monte Carlo noise.

Every cell is an independent reprice, so the grid is dispatched across
processes via the generic compute module (core/compute/executor.py,
pricers/scenario_grid.py) instead of a sequential Python loop — the same
GIL-bound-per-path reasoning documented there applies here (run_mc's
_eval_paths walks N paths one at a time in pure Python; threads wouldn't
help). Still fully synchronous from the caller's point of view (api/
scenarios.py's endpoint blocks until run_batch returns) — a stress grid is
small enough (a few dozen cells) that it doesn't need the async queue+worker
pattern the VaR study needed for its thousands of jobs."""
from __future__ import annotations
from ..compute.executor import run_batch

# Stress cells use a reduced path count by default — the grid only needs to be
# smooth/comparable, not maximally precise, and cost scales as
# len(spot_shocks) * len(vol_shocks) * N.
DEFAULT_SCENARIO_N = 2000

# Bounded rather than "however many cells the grid has": a stress grid tops
# out at 15x15 (schema-enforced) = 225 cells, each spawning a fresh worker
# process only helps up to the machine's actual core count.
DEFAULT_MAX_WORKERS = 4


def compute_scenario_grid(script_text: str, underlyings, corr_matrix, r: float, T: float,
                           model: str, seed: int, user_params: dict,
                           spot_shocks: list[float], vol_shocks: list[float],
                           N: int = DEFAULT_SCENARIO_N,
                           yield_curve=None, sigma_r: float = 0.0, a_r: float = 0.0,
                           barrier_monitoring: str = "weekly",
                           constat_values: dict | None = None,
                           constat_anchor: str | None = None,
                           max_workers: int = DEFAULT_MAX_WORKERS) -> dict:
    """2D stress grid: price(spot_shock, vol_shock) for every combination, plus
    the unshocked base price for reference (computed independently of whether
    0.0 is actually present in the shock lists).

    Takes the script as TEXT (not a compiled CompiledScript) because every
    cell is repriced in its own worker process (see module docstring) — a
    CompiledScript's events carry exec()-produced closures with no importable
    name, which pickle cannot serialize, so each worker re-parses the text
    itself (a few ms, paid once per worker, not per cell — see
    compute/executor.py's Windows-spawn note)."""

    def _payload(spot_shock: float, vol_shock: float) -> dict:
        return dict(
            script_text=script_text, constat_values=constat_values,
            constat_anchor=constat_anchor,
            underlyings=underlyings, corr=corr_matrix, r=r, T=T,
            n_paths=N, model=model, seed=seed, user_params=user_params,
            spot_shock=spot_shock, vol_shock=vol_shock,
            yield_curve=yield_curve or [], sigma_r=sigma_r, a_r=a_r,
            barrier_monitoring=barrier_monitoring,
        )

    # job 0 = unshocked base price; jobs 1.. = grid cells in row-major order
    # (vol_shocks outer, spot_shocks inner) — matches `prices`' row/col shape.
    jobs: list[tuple[int, dict]] = [(0, _payload(0.0, 0.0))]
    cell_job_id = {}
    next_id = 1
    for vi, dV in enumerate(vol_shocks):
        for si, dS in enumerate(spot_shocks):
            jobs.append((next_id, _payload(dS, dV)))
            cell_job_id[(vi, si)] = next_id
            next_id += 1

    results = run_batch("scenario_grid", jobs, max_workers=max_workers, use_processes=True)
    by_id = {r.job_id: r for r in results}

    failed = next((r for r in by_id.values() if not r.ok), None)
    if failed is not None:
        raise ValueError(failed.error)

    base_price = by_id[0].result["price"]
    prices: list[list[float]] = [
        [round(by_id[cell_job_id[(vi, si)]].result["price"], 6) for si in range(len(spot_shocks))]
        for vi in range(len(vol_shocks))
    ]

    return {
        "spot_shocks": spot_shocks,
        "vol_shocks": vol_shocks,
        "base_price": round(base_price, 6),
        "prices": prices,
    }
