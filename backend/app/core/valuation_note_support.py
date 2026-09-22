"""Pure domain helpers shared by valuation-note assembly and API delivery."""
from __future__ import annotations

import json

from .payoff_terms import classify_param_barrier

_REDUCTION_LABEL = {"AVG": "moyenne", "MIN": "plus bas", "MAX": "plus haut"}


def events_for_note(events: list, schedule_json: str) -> tuple[list[dict], str | None]:
    """Project contractual observations into client-note rows."""
    try:
        schedule = json.loads(schedule_json or "{}")
    except (TypeError, ValueError):
        schedule = {}
    windows = {
        round(item["t"], 4): {
            "reduction": item["reduction"], "readings": item["releves"],
        }
        for item in schedule.get("constatations") or []
        if item.get("reduction") and item.get("releves")
    }
    observations = [event for event in events if event.parent_event_id is None]
    rows = []
    for event in observations:
        label = event.label
        window = windows.get(round(event.t_years, 4))
        if window:
            reduction = _REDUCTION_LABEL.get(
                window["reduction"], window["reduction"])
            label = f"{label} — {reduction} de {len(window['readings'])} relevés"
        rows.append({
            "date": event.event_date, "label": label, "status": event.status,
            "t_years": event.t_years,
        })
    next_date = next((
        event.event_date
        for event in sorted(observations, key=lambda item: item.t_years or 0.0)
        if event.status == "futur"
    ), None)
    return rows, next_date


def monitor_levels(compiled, user_params: dict, next_row: int) -> list[dict]:
    """Resolve the next effective level of each monitored script parameter."""
    full = {param.name: param.stored_val for param in compiled.params}
    full.update(user_params or {})

    def resolve(name):
        value = full.get(name)
        if isinstance(value, list):
            value = value[min(next_row, len(value) - 1)] if value else None
        return float(value) if isinstance(value, (int, float)) else None

    out = []
    for monitor in compiled.monitors or []:
        level = resolve(monitor["name"])
        if level is not None:
            out.append({
                "name": monitor["name"],
                "observable": monitor.get("observable"),
                "direction": monitor.get("direction"),
                "level": level,
            })
    if out:
        return out
    for param in compiled.params:
        level = resolve(param.name)
        if level is None:
            continue
        kind = classify_param_barrier(param.name, level)
        if kind and kind != "neutral":
            out.append({
                "name": param.name, "observable": None,
                "direction": "down" if kind == "ki" else "up",
                "level": level,
            })
    return out


def _greeks_state(ctx: dict) -> dict:
    state = ctx["state"]
    return {
        "spot_base": ctx["norm_spots"],
        "wof_min": state["wof_min"], "bof_max": state["bof_max"],
        "index": state["index"], "memo": state["memo"],
        "accum": state["accum"], "s_min": state["s_min"],
        "s_max": state["s_max"], "s_prev": state["s_prev"],
        "realvol_state": state["realvol_state"],
        "fix_state": state["fix_state"],
    }


def residual_greeks(ctx: dict, n_paths: int) -> list[dict]:
    """Return the client-facing residual sensitivity rows for a note."""
    from .payscript.engine import compute_greeks

    raw = compute_greeks(
        ctx["residual_script"], ctx["engine_uls"], ctx["corr"],
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=ctx.get("seed", 42), user_params=ctx["user_params"],
        selected=["delta", "gamma", "vega"],
        sigma_r=ctx["sigma_r"], a_r=ctx["a_r"], yield_curve=ctx["yc"],
        funding_curve=ctx.get("funding_curve", []),
        funding_spread=ctx.get("funding_spread", 0.0),
        barrier_monitoring=ctx["barrier_monitoring"],
        antithetic=ctx["antithetic"], state=_greeks_state(ctx),
        strike_set_t=ctx.get("strike_set_t"),
        maturity_payment_t=ctx.get("residual_payment_t"),
    )
    rows = []
    for index, underlying in enumerate(ctx["underlyings_json"]):
        delta = raw.get(f"delta_{index + 1}")
        gamma = raw.get(f"gamma_{index + 1}")
        vega = raw.get(f"vega_{index + 1}")
        rows.append({
            "name": underlying["name"],
            "delta_pts": None if delta is None else round(delta, 2),
            "gamma_pts": None if gamma is None else round(gamma * 0.01, 3),
            "vega_pts": None if vega is None else round(vega, 2),
        })
    return rows
