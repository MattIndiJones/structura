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
    constat_anchor: str | None       — ISO date the calendar's year-fractions run from
                                       (the product's value date); None = today
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
    from datetime import date
    from ...payscript.parser import parse_script, resolve_constats, CompiledScript
    from ...payscript.engine import run_mc, _shift_events_for_mtf

    compiled = parse_script(payload["script_text"])
    if payload.get("constat_values"):
        anchor = payload.get("constat_anchor")
        # Chaque cellule est repricee dans son propre processus, qui re-parse
        # le script depuis cette charge : la devise doit voyager avec, sinon un
        # CONSTAT portant un decalage de reglement fait echouer toute la grille
        # alors que le prix simple, lui, passe.
        compiled = resolve_constats(
            compiled, payload["constat_values"],
            anchor=date.fromisoformat(anchor) if anchor else None,
            currency=payload.get("constat_currency"),
        )

    # Jambe residuelle : le worker recoit le script en TEXTE et le re-parse, or
    # un CompiledScript residuel n'a pas de forme textuelle. On le reconstruit
    # donc ici a partir du temps ecoule, exactement comme le fait le worker de
    # VaR — decaler les dates d'evenement et couper la fenetre de strike fix
    # deja consommee.
    _elapsed = payload.get("residual_elapsed")
    if _elapsed:
        compiled = CompiledScript(
            events=_shift_events_for_mtf(compiled.events, _elapsed),
            init_fn=compiled.init_fn, params=compiled.params,
            constats=compiled.constats, has_stop=compiled.has_stop,
            monitors=compiled.monitors,
            strike_fix_dates=[round(d - _elapsed, 6)
                              for d in (compiled.strike_fix_dates or [])
                              if d > _elapsed + 1e-9] or None,
        )

    n = len(payload["underlyings"])
    result = run_mc(
        compiled, payload["underlyings"], payload["corr"],
        payload["r"], payload["T"], payload["n_paths"], payload["model"],
        seed=payload["seed"], antithetic=True,
        user_params=payload.get("user_params") or {},
        # Le choc de spot est MULTIPLICATIF autour du niveau du jour : un
        # sous-jacent a 34 % de son strike est choque de 10 % de la ou il
        # traite, pas de son niveau d'emission.
        spot_mult=[b * (1.0 + payload.get("spot_shock", 0.0))
                   for b in (payload.get("state_spots") or [1.0] * n)],
        vol_add=[payload.get("vol_shock", 0.0)] * n,
        dr=payload.get("rate_shock", 0.0),
        yield_curve=payload.get("yield_curve") or [],
        sigma_r=payload.get("sigma_r", 0.0), a_r=payload.get("a_r", 0.0),
        barrier_monitoring=payload.get("barrier_monitoring", "weekly"),
        # L'etat contractuel deja realise, serialise avec le reste : sans lui
        # chaque cellule de la grille reprice un produit neuf.
        **(payload.get("residual_state") or {}),
    )
    return {"price": result["price"]}
