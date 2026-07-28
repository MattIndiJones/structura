"""Reprices ONE cell of the Pricer's stress grid (spot shock x vol shock,
see core/payscript/scenarios.py) — a fresh full-life price, not a residual
leg (contrast with pricers/var_scenario.py, which reprices an already-live
deal's remaining cash flows). Same "ship pure data, rebuild the compiled
script fresh in the worker" discipline as pricers/payscript.py.

Payload mirrors compute_scenario_grid()'s own call into run_mc — every knob
that function already threads through (yield_curve/sigma_r/a_r included,
see AUDIT_PRICING_2026-07.md #1.6) is carried here unchanged, so a
parallelized cell prices identically to the sequential loop it replaces.

Payload shape:
    script_text: str
    constat_values: dict | None      — only if the script declares CONSTAT() calendars
    underlyings: list[dict]
    corr: list[list[float]]
    r: float
    T: float
    n_paths: int
    model: str
    seed: int
    user_params: dict
    spot_shock: float                — multiplicative, e.g. -0.10 (this cell's column)
    vol_shock: float                 — additive, e.g. 0.05 (this cell's row)
    rate_shock: float = 0.0
    yield_curve: list | None
    sigma_r: float = 0.0
    a_r: float = 0.0
    barrier_monitoring: str = "weekly"
"""
from __future__ import annotations


def price_scenario_grid_job(payload: dict) -> dict:
    from ...payscript.parser import parse_script, resolve_constats
    from ...payscript.engine import run_mc

    compiled = parse_script(payload["script_text"])
    if payload.get("constat_values"):
        compiled = resolve_constats(compiled, payload["constat_values"])

    n = len(payload["underlyings"])
    result = run_mc(
        compiled, payload["underlyings"], payload["corr"],
        payload["r"], payload["T"], payload["n_paths"], payload["model"],
        seed=payload["seed"], antithetic=True,
        user_params=payload.get("user_params") or {},
        spot_mult=[1.0 + payload.get("spot_shock", 0.0)] * n,
        vol_add=[payload.get("vol_shock", 0.0)] * n,
        dr=payload.get("rate_shock", 0.0),
        yield_curve=payload.get("yield_curve") or [],
        sigma_r=payload.get("sigma_r", 0.0), a_r=payload.get("a_r", 0.0),
        barrier_monitoring=payload.get("barrier_monitoring", "weekly"),
    )
    return {"price": result["price"]}
