"""Reprices ONE active deal's residual leg under ONE shocked market scenario
— the job kind a VaR/ES study (core/var_engine.py) submits, one job per
(deal × scenario) pair, through the generic compute module.

Same "ship pure data, rebuild the compiled objects fresh in the worker"
discipline as pricers/payscript.py, but for the RESIDUAL (mark-to-future)
leg rather than a fresh full-life price — the residual script and the
replayed state (memory coupons, running extrema, observation index...) are
what api/deals.py:_mtm_core builds today for a single synchronous MtM/shock
call; var_engine.build_deal_scenario_base() extracts the pure-data
equivalent of that same ctx ONCE per deal (replay is cheap, no Monte Carlo —
redoing it per scenario would be wasteful) so N scenarios can share it.

Payload shape (produced by var_engine.apply_scenario_to_deal_base):
    script_text: str            — deal.script_snapshot, unmodified
    constat_values: dict | None — market_snapshot.constats, for expert-mode calendars
    value_date: str             — ISO date, resolve_constats' anchor
    T_elapsed: float            — years since value_date, to shift events for MTF
    state: dict                 — eval_script_on_history's replayed state (pure data)
    norm_spots: list[float]     — today's spot / strike, per underlying (deal's own order)
    engine_uls: list[dict]      — engine-ready underlyings (post recalibration if any)
    corr: list[list[float]]     — baseline correlation (pre-scenario-shock)
    r_frac: float
    T_remaining: float
    model_used: str
    yc: list | None
    sigma_r: float
    a_r: float
    antithetic: bool
    user_params: dict
    barrier_monitoring: str
    n_paths: int
    # scenario shock, already resolved to THIS deal's underlying order:
    spot_mult: list[float] | None    — multiplicative shock per underlying (1.10 = +10%)
    vol_add: list[float] | None      — additive vol shock per underlying, as a fraction (0.05 = +5pts)
    dr: float                        — additive rate shock, as a fraction
    corr_shocked: list[list[float]] | None  — pre-shifted corr matrix (see var_engine._shock_corr_scalar)
"""
from __future__ import annotations
from datetime import date


def price_var_scenario_job(payload: dict) -> dict:
    from ...payscript.parser import parse_script, resolve_constats, CompiledScript
    from ...payscript.engine import run_mc, _shift_events_for_mtf

    compiled = parse_script(payload["script_text"])
    if payload.get("constat_values"):
        compiled = resolve_constats(
            compiled, payload["constat_values"],
            anchor=date.fromisoformat(payload["value_date"]),
        )

    T_elapsed = payload["T_elapsed"]
    residual_events = _shift_events_for_mtf(compiled.events, T_elapsed)
    residual_fix = [round(d - T_elapsed, 6) for d in (compiled.strike_fix_dates or [])
                    if d > T_elapsed + 1e-9]
    residual_script = CompiledScript(
        events=residual_events, init_fn=compiled.init_fn, params=compiled.params,
        constats=compiled.constats, has_stop=compiled.has_stop, monitors=compiled.monitors,
        strike_fix_dates=residual_fix or None,
    )

    norm_spots = payload["norm_spots"]
    spot_shock = payload.get("spot_mult") or [1.0] * len(norm_spots)
    effective_spots = [ns * sm for ns, sm in zip(norm_spots, spot_shock)]

    state = payload["state"]
    corr = payload.get("corr_shocked") or payload["corr"]

    result = run_mc(
        residual_script, payload["engine_uls"], corr,
        payload["r_frac"], payload["T_remaining"],
        payload.get("n_paths", 3000), payload.get("model_used", "constant"),
        seed=42, antithetic=payload.get("antithetic", True),
        user_params=payload.get("user_params") or {},
        spot_mult=effective_spots, vol_add=payload.get("vol_add"),
        dr=payload.get("dr", 0.0),
        yield_curve=payload.get("yc") or [], sigma_r=payload.get("sigma_r", 0.0),
        a_r=payload.get("a_r", 0.0),
        barrier_monitoring=payload.get("barrier_monitoring", "weekly"),
        wof_min_init=state["wof_min"], bof_max_init=state["bof_max"],
        index_offset=state["index"], memo_init=state["memo"], accum_init=state["accum"],
        s_min_init=state["s_min"], s_max_init=state["s_max"], s_prev_init=state["s_prev"],
        wof0_init=min(effective_spots),
        realvol_state_init=state["realvol_state"], fix_state_init=state["fix_state"],
    )
    return {"price": result["price"]}
