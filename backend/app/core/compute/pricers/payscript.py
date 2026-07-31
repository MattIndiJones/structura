"""Adapter that lets the generic compute module reprice a PayScript deal —
the only PayScript-specific code in core/compute/, everything else in this
package is product-agnostic.

The payload is deliberately NOT "a Deal" (a live DB row, a CompiledScript, an
engine underlying object) — it's the plain data those things are built from,
because a ProcessPoolExecutor worker (see executor.py) gets this payload via
pickle in a fresh Python process that has never seen the caller's Session or
compiled script object. Re-parsing the script text costs a few ms; it's
cheaper than solving "how do I pickle an exec()-produced closure" (you
don't — CompiledScript.events[i].fn is a function object with no importable
name, pickle simply cannot serialize it).

Shape of `payload`, every key optional except script_text/underlyings/corr/
r/T (mirrors run_mc's own kwargs — see engine.py — plus constat_values for
expert-mode scripts):
    script_text: str
    underlyings: list[dict]      — engine-ready underlying dicts (name, sigma, q, ...)
    corr: list[list[float]]
    r: float                     — flat rate, as a fraction (0.03, not 3)
    T: float                     — horizon in years
    n_paths: int = 5000
    model: str = "GBM"
    seed: int = 42
    antithetic: bool = True
    user_params: dict = {}
    spot_mult: list[float] | None   — per-underlying multiplicative spot shock (e.g. a VaR scenario's spot move)
    vol_add: list[float] | None     — per-underlying additive vol shock
    dr: float = 0.0                 — additive rate shock
    corr_shocked: list[list[float]] | None  — pre-shifted corr matrix (caller's job — this module doesn't know shock conventions, see api/shocks.py._shock_corr)
    barrier_monitoring: str = "weekly"
    constat_values: dict | None      — only if the script declares CONSTAT() calendars
"""
from __future__ import annotations


def price_payscript_job(payload: dict) -> dict:
    # Imported lazily, inside the function: on Windows (spawn, not fork —
    # see executor.py), this module is re-imported from scratch in every
    # worker process, so keeping the heavy engine import inside the
    # function body (rather than at module level) means a worker that never
    # actually gets a payscript_reprice job doesn't pay for it either.
    from ...payscript.parser import parse_script, resolve_constats
    from ...payscript.engine import run_mc

    compiled = parse_script(payload["script_text"])
    if payload.get("constat_values"):
        from datetime import date
        anchor = date.fromisoformat(payload["value_date"]) if payload.get("value_date") else None
        compiled = resolve_constats(
            compiled, payload["constat_values"], anchor=anchor)

    corr = payload.get("corr_shocked") or payload["corr"]
    result = run_mc(
        compiled,
        payload["underlyings"],
        corr,
        payload["r"],
        payload["T"],
        payload.get("n_paths", 5000),
        payload.get("model", "GBM"),
        seed=payload.get("seed", 42),
        antithetic=payload.get("antithetic", True),
        user_params=payload.get("user_params") or {},
        spot_mult=payload.get("spot_mult"),
        vol_add=payload.get("vol_add"),
        dr=payload.get("dr", 0.0),
        barrier_monitoring=payload.get("barrier_monitoring", "weekly"),
    )
    return {"price": result["price"], "n_paths": result.get("n_paths")}
