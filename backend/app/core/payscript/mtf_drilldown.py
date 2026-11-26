"""Mark-to-Future drill-down on one date: flows, observations and barriers.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
import time
from ..compute_budget import ABSOLUTE_WORK_LIMIT, WORKER_MEMORY_LIMIT_BYTES, count_compiled_dates, ensure_budget, estimate_mc_batch
from ..simulation_grid import grid_frequency, with_simulation_grid
from .parser import CompiledScript
from .time_grid import durations as _durations, step_at as _step_at, time_at as _time_at, times as _times
from .diffusion import _atm_step_vols, cholesky, validate_model
from .evaluation import _basket_references, _constater, _eval_paths, _fusionner_realise, _rangs_observation
from .mark_to_future import MTF_MAX_BATCH, _exact_mtf_residual, _mtf_claim_rows, _mtf_inner_paths, _mtf_known_only_row, _mtf_outer_state, _mtf_payment_args, _mtf_realized_fix, _mtf_reject_unsupported, _mtf_releves_realises, _mtf_replay, _scenario_realise, mtf_date_grid, mtf_simulation_axis
from .mc_axis import SY, _event_schedule


# ── Analytics: Mark-to-Future drill-down ────────────────────────────
#
# "Why is P05 at 47%?" is not answerable from a fan chart. This reopens one
# mark date and hands back, for a handful of named scenarios, everything that
# produced their number: the market path that got there, what the contract had
# already paid, what it is expected to pay next and with what probability, the
# discount factor on each of those flows, and — for comparison — what that same
# trajectory actually ends up paying if you let it run to maturity.
#
# The whole thing rests on one property: the fan's outer scenarios are
# REPRODUCIBLE. _simulate_mtf_outer draws (ts, n, N) in C order, so extending
# the horizon leaves every earlier step bit-identical; and the inner draws are
# keyed on (seed, date index k, chunk start). Replaying the same k and the same
# chunk therefore reproduces the fan's inner paths exactly, which is why the
# `mtf` reported here equals `pvs[i]` from the fan to the last decimal instead
# of merely being close to it. An explain panel that did not tie out would be
# worse than none.

def _mtf_flux_rows(flux_map: dict, n_paths: int, t0: float) -> list[dict]:
    """Turn a flux_map (aggregated over the inner paths of ONE outer scenario)
    into the expected-cash-flow table behind a mark.

    Per (date, label): probability of firing, expected amount, implied discount
    factor and present value. Summing `pv` reconstructs the mark — that identity
    is returned as a check rather than asserted, so a caller can display the
    residual instead of the engine hiding it."""
    rows = []
    for v in flux_map.values():
        n_fire, tot, pv = v["n"], v["sum"], v["pv"]
        rows.append({
            "t": round(v.get('t_pay',v['t']),6),
            "t_abs": round(t0+v.get('t_pay',v['t']),6),
            "observation_t": t0+v['t'], "payment_t": t0+v.get('t_pay',v['t']),
            "status": 'CONDITIONAL',
            "lbl": v["lbl"],
            "proba": round(n_fire / n_paths * 100, 3),   # % des chemins internes
            "e_amount": round(tot / n_paths * 100, 6),   # espérance, % du nominal
            "amount_if_fires": round(tot / n_fire * 100, 6) if n_fire else 0.0,
            "df": round(pv / tot, 6) if abs(tot) > 1e-12 else 1.0,
            "pv": round(pv / n_paths * 100, 6),          # contribution au mark
        })
    rows.sort(key=lambda x: (x["t"], x["lbl"]))
    return rows


def _mtf_observations(script: CompiledScript, wof_path: np.ndarray, ts_full: int,
                      step_k: int, stop_step: int | None,
                      fired: dict[int, list], dt=1.0 / SY) -> list[dict]:
    """Observation calendar of one trajectory, with its status at each date.

    `vivant` before the stop, `rappelé` at the stop itself, `éteint` after it —
    an observation the contract never reached is not a missing row, it is a row
    that says the product was already gone."""
    steps = sorted({max(1, _step_at(dt, d))
                    for ev in script.events if ev.type == "AT" for d in ev.dates})
    if any(ev.type == "AT_MATURITY" for ev in script.events) and ts_full not in steps:
        steps.append(ts_full)
    out = []
    for s in steps:
        if stop_step is None or s < stop_step:
            status = "vivant"
        elif s == stop_step:
            status = "rappelé" if s < ts_full else "maturité"
        else:
            status = "éteint"
        out.append({
            "step": int(s),
            "t": round(_time_at(dt, s), 6),
            "wof": round(float(wof_path[s - 1]), 6),
            "past": bool(s <= step_k),
            "status": status,
            "flows": fired.get(s, []),
        })
    return out


def _mtf_barriers(script: CompiledScript, source: str, user_params: dict) -> list[dict]:
    """Levels the script actually COMPARES an observable against.

    Derived from the script text by the same static analysis the M_ watchlist
    uses (_analyze_monitors), applied to every PARAM rather than only the
    M_-prefixed ones. A PARAM that is never compared to WOF/BOF/S[i] — a coupon
    rate, a participation — comes back with observable None and is dropped:
    guessing "which PARAM is a barrier" from its value would put CPN = 8% next
    to PDI = 60% and call both barriers."""
    from .parser import _analyze_monitors
    names = [p.name for p in script.params]
    if not names:
        return []
    out = []
    for mon in _analyze_monitors(source, names):
        if not mon["observable"]:
            continue
        p = next(p for p in script.params if p.name == mon["name"])
        lvl = user_params.get(p.name, p.stored_val)
        try:
            lvl = float(lvl)
        except (TypeError, ValueError):
            continue          # PARAM() en tableau : pas un niveau unique
        out.append({"name": p.name, "level": round(lvl, 6), "is_pct": bool(p.is_pct),
                    "observable": mon["observable"], "direction": mon["direction"],
                    "desc": p.desc})
    return out


@with_simulation_grid
def run_mtf_drilldown(script: CompiledScript,
                      underlyings,
                      corr_matrix,
                      r: float,
                      T_max: float,
                      main_price: float,
                      t0: float,
                      scenario_ids: list[int],
                      labels: list[str] | None = None,
                      script_source: str = "",
                      model: str = "constant",
                      n_outer: int = 200,
                      n_inner: int = 500,
                      n_dates: int = 5,
                      seed: int = 42,
                      user_params=None,
                      barrier_monitoring: str = "weekly",
                      mtm_dates: list[float] | None = None,
                      yield_curve=None,
                      sigma_r: float = 0.0,
                      max_scenarios: int = 12, state=None, maturity_payment_t=None,
                      initial_flows=None, initial_terminated=False, aligned_grid=False,
                      gbm_atm_curve=False, lsv_leverage=None, local_vol_anchor=None) -> dict:
    """Full explain of a handful of outer scenarios at one Mark-to-Future date.

    `scenario_ids` are indices into the fan's `pvs` / `alive` arrays. The date
    grid arguments (n_dates / mtm_dates) must match the run being explained:
    they fix the date index k, which keys the inner random draws. Get them wrong
    and the marks come back plausible and slightly different — the one failure
    mode this whole design exists to prevent, so the grid is echoed back in the
    response for the caller to check against the fan it came from."""
    _mtf_reject_unsupported(model, barrier_monitoring, yield_curve, sigma_r,
                            underlyings, aligned_grid=aligned_grid)
    if aligned_grid:
        validate_model(model, underlyings)
    t_run0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    dt = 1.0 / grid_frequency()

    grid = mtf_date_grid(script,T_max,n_dates,maturity_payment_t,mtm_dates)
    t0 = float(t0)
    k = next((i for i, d in enumerate(grid) if abs(d - t0) < 1e-6), None)
    if k is None:
        raise ValueError(
            f"La date {t0} ne figure pas dans la grille de l'éventail {grid}. "
            f"Le tirage interne dépend du rang de la date : l'expliquer depuis "
            f"une autre grille produirait un mark voisin mais différent de celui "
            f"affiché. Relancez le Mark-to-Future ou demandez une date de la grille."
        )
    ids = []
    for i in scenario_ids:
        i = int(i)
        if not 0 <= i < n_outer:
            raise ValueError(f"Scénario {i} hors bornes (0..{n_outer - 1}).")
        if i not in ids:
            ids.append(i)
    if not ids:
        raise ValueError("Aucun scénario demandé.")
    if len(ids) > max_scenarios:
        raise ValueError(
            f"{len(ids)} scénarios demandés, {max_scenarios} au maximum — chacun "
            f"rejoue {n_inner} chemins internes et renvoie sa trajectoire complète.")
    if initial_terminated:
        row = _mtf_known_only_row(initial_flows or [],t0,r,n_outer,main_price)
        claims = row['unsettled_flows'][0]
        settled = row['settled_flows'][0]
        scenarios = []
        for i in ids:
            scenarios.append(dict(id=i,label=(labels[scenario_ids.index(i)] if labels and scenario_ids.index(i)<len(labels) else None),
                alive=False,outstanding=bool(claims),status='PENDING_SETTLEMENT' if claims else 'SETTLED',
                mtf=row['pvs'][i],pending_pv=row['pvs'][i],residual_mark=0.,sum_pv=row['pvs'][i],pv_residual=0.,
                future_flows=claims,unsettled_flows=claims,
                realized_flows=[dict(t=f['payment_t'],observation_t=f['observation_t'],v=f['amount']*100,lbl=f['lbl']) for f in settled],
                realized_cash=sum(f['amount']*100 for f in settled),recall_proba=None,expected_life=None,
                wof_t0=None,spots_t0=[],path=dict(t=[],wof=[],assets=[[] for _ in underlyings]),observations=[],
                final=dict(stop_t=0.,recalled=True,total_undiscounted=sum(f['amount']*100 for f in initial_flows or []),
                    pv_at_0=sum(f['amount']*100*math.exp(-r*f['payment_t']) for f in initial_flows or [] if f['payment_t']>0),
                    flows=[dict(t=f['payment_t'],v=f['amount']*100) for f in initial_flows or []])))
        return dict(t=t0,k=k,step_k=0,mtm_dates=grid,main_price=main_price,n_outer=n_outer,n_inner=n_inner,
            T_max=T_max,r=r,n_assets=n,asset_names=[u.get('name','Sous-jacent') for u in underlyings],
            barriers=[],scenarios=scenarios,terminated_at_origin=True,elapsed_ms=(time.perf_counter()-t_run0)*1000)
    t0 = grid[k]
    ts_full, full_dt = mtf_simulation_axis(script, T_max, grid, aligned_grid)
    full_dt = _durations(full_dt, ts_full)
    step_k = _step_at(full_dt, min(t0,T_max))
    past_dt = full_dt[:step_k]
    if step_k < 1:
        raise ValueError(f"Date de valorisation trop proche de t=0 : {t0}.")

    _outer_per_chunk = max(1, MTF_MAX_BATCH // n_inner)
    _chunk_starts = {(i // _outer_per_chunk) * _outer_per_chunk for i in ids}
    _chunk_paths = [
        (min(n_outer, start + _outer_per_chunk) - start) * n_inner
        for start in _chunk_starts
    ]
    _peak_paths = max([n_outer, *_chunk_paths])
    _total_paths = n_outer + sum(_chunk_paths)
    ensure_budget(
        estimate_mc_batch(
            operation="mark_to_future_drilldown",
            simulation_steps=ts_full,
            maturity_years=T_max,
            underlyings=n,
            paths_per_run=_peak_paths,
            total_runs=_total_paths / _peak_paths,
            model=model,
            antithetic=False,
            expanded_dates=count_compiled_dates(script),
        ),
        memory_limit_bytes=WORKER_MEMORY_LIMIT_BYTES,
        work_limit=ABSOLUTE_WORK_LIMIT,
    )
    lab = {i: (labels[j] if labels and j < len(labels) else None)
           for j, i in enumerate(ids)}

    # ── Outer paths, extended to MATURITY ───────────────────────────
    # The fan stops at its last mark date; the drill-down needs the rest of the
    # trajectory to show what this scenario actually ends up paying. Extending
    # the horizon is safe precisely because the prefix is bit-identical.
    step_vols = _atm_step_vols(underlyings, full_dt, ts_full) if gbm_atm_curve else None
    local_vol_wings = []
    S_full, factors, local_grid = _mtf_outer_state(
        model, underlyings, corr_matrix, r, grid, n_outer, seed,
        (state or {}).get('spot_mult'), full_dt, step_vols, wing_diagnostics=local_vol_wings,
        lsv_leverage=lsv_leverage, local_vol_anchor=local_vol_anchor)
    S_outer = S_full[:step_k + 1]

    # ── Replay to the mark date (same call as the fan) ──────────────
    _S_past, outer_states, outer_flows, ledger, alive = _mtf_replay(
        script,S_full,step_k,past_dt,T_max,maturity_payment_t,r,user_params,underlyings,state,initial_flows)
    fix_state_k = _fusionner_realise((state or {}).get('fix_state_init'),
                                    _mtf_realized_fix(script,S_full,step_k,full_dt)[0])
    releves_k = _mtf_releves_realises(script,_S_past,step_k,full_dt)
    matured = t0 >= T_max-1e-9
    if not matured:
        residual_script, step_map, mat_events, ts_eff, dt = _exact_mtf_residual(
            script, t0, T_max, full_dt[step_k:] if aligned_grid else None)
        dt = _durations(dt, ts_eff)
        final_pay = (maturity_payment_t if maturity_payment_t is not None else T_max)-t0
        inner_payment_args = _mtf_payment_args(residual_script,step_map,T_max-t0,final_pay,dt,r)
    else:
        ts_eff, dt = 0, np.array([])
        inner_payment_args = {}

    L = cholesky(corr_matrix, n)
    outer_per_chunk = max(1, MTF_MAX_BATCH // n_inner)

    # ── Full-script evaluation of each trajectory, out to maturity ──
    # One path, the real script (maturity block included): what this scenario
    # ends up being worth. This is a single realization along an outer path,
    # NOT a price — it is the number the mark is an expectation of, and showing
    # the two side by side is the point of the panel.
    contract_steps = _step_at(full_dt,T_max)
    contract_dt = full_dt[:contract_steps]
    full_step_map, full_mat, _ = _event_schedule(script.events,contract_steps,contract_dt,horizon=T_max)
    full_payment_args = _mtf_payment_args(script,full_step_map,T_max,maturity_payment_t,contract_dt,r,collect=True)
    inherited = dict(state or {})
    inherited.pop('spot_mult',None); inherited.pop('spot_base',None)
    inherited_fix = inherited.pop('fix_state_init',None)

    out_scen: list[dict] = []
    for i in ids:
        path_i = np.ascontiguousarray(S_full[:contract_steps+1, :, i:i + 1])          # (ts_full+1, n, 1)
        wof_i = path_i[1:].min(axis=1)[:, 0]                          # (ts_full,)
        flux_full: dict = {}
        stops: list = []
        flows_full: list = []
        _p_i, _, _, _p_lvl = _constater(script,path_i,contract_steps,n,1,None,None,
                                        inherited_fix,full_step_map,dt=contract_dt)
        pay_full, pay_raw = _eval_paths(
            script,_p_i,contract_steps,n,1,contract_dt,r,user_params,
            full_step_map,full_mat,flux_full,record=True,
            stop_times_out=stops,flows_out=flows_full,lvl_map=_p_lvl,
            rank_map=_rangs_observation(full_step_map,contract_dt),
            **full_payment_args,**inherited,reference_spots=_basket_references(underlyings))
        stop_t = float(stops[0]) if stops else T_max
        stop_step = _step_at(full_dt, stop_t)
        fired: dict[int, list] = {}
        for v in flux_full.values():
            s = max(1, _step_at(full_dt, v["t"]))
            fired.setdefault(s, []).append(
                {"lbl": v["lbl"], "v": round(v["sum"] * 100, 6)})

        acquired = _mtf_claim_rows(ledger[i],t0,r)
        settled = [f for f in ledger[i] if f['payment_t'] <= t0+1e-9]
        outstanding = bool(alive[i]) or bool(acquired)
        out_scen.append({
            "id": i,
            "label": lab[i],
            "alive": bool(alive[i]),
            "outstanding": outstanding,
            "status": 'PAYOFF_ACTIVE' if alive[i] else 'PENDING_SETTLEMENT' if acquired else 'SETTLED',
            "unsettled_flows": acquired, "pending_pv": sum(f['pv'] for f in acquired),

            "wof_t0": round(float(S_full[_step_at(full_dt,t0), :, i].min()), 6),
            "spots_t0": [round(float(v), 6) for v in S_full[_step_at(full_dt,t0), :, i]],
            # Trajectoire complète (hebdomadaire), t=0 inclus.
            "path": {
                "t": _times(full_dt, ts_full).tolist(),
                "wof": [1.0] + [round(float(v), 6) for v in wof_i],
                "assets": [[round(float(v), 6) for v in S_full[:, a, i]] for a in range(n)],
            },
            "observations": _mtf_observations(script, wof_i, contract_steps, step_k,
                                              stop_step, fired, full_dt),
            # Ce qui a DÉJÀ été encaissé avant la date de valorisation.
            "realized_flows": [dict(t=f['payment_t'],observation_t=f['observation_t'],v=f['amount']*100,
                                     lbl=f['lbl']) for f in settled],
            "realized_cash": sum(f['amount']*100 for f in settled),
            # Payoff RÉEL de cette trajectoire si on la laisse courir.
            "final": {
                "stop_t": round(stop_t, 6),
                "recalled": bool(stop_step < contract_steps),
                "total_undiscounted": round(float(pay_raw[0]) * 100, 6),
                "pv_at_0": round(float(pay_full[0]) * 100, 6),
                "flows": [{"t": round(t, 6), "v": round(v * 100, 6)}
                          for t, v in flows_full[0]],
            },
        })

    # ── Inner repricing, chunk by chunk, exactly as the fan drew it ──
    by_chunk: dict[int, list[int]] = {}
    for i in ids:
        by_chunk.setdefault((i // outer_per_chunk) * outer_per_chunk, []).append(i)

    marks: dict[int, dict] = {}
    for start, members in by_chunk.items():
        if matured:
            for i in members:
                marks[i] = dict(mtf=0.,future_flows=[],sum_pv=0.,recall_proba=None,expected_life=None)
            continue

        end = min(n_outer, start + outer_per_chunk)
        n_chunk = end - start
        N_chunk = n_chunk * n_inner
        sl = slice(start, end)
        S_in = _mtf_inner_paths(model, underlyings, r, L, dt, n_inner, seed, k,
                               start, end, S_full[step_k], factors, local_grid, step_k, step_vols)

        for i in members:
            j = i - start
            cols = slice(j * n_inner, (j + 1) * n_inner)
            flux: dict = {}
            stops_in: list = []
            _S_i = np.ascontiguousarray(S_in[:, :, cols])
            _S_i, _, _, _lvl_i = _constater(
                residual_script, _S_i, ts_eff, n, n_inner, None, None,
                _scenario_realise(fix_state_k, i),
                step_map,
                {cle: _scenario_realise(etat, i) for cle, etat in releves_k.items()}, dt=dt)
            payoffs, _ = _eval_paths(
                residual_script, _S_i, ts_eff, n,
                n_inner, dt, r, user_params, step_map, mat_events, flux, record=True,
                stop_times_out=stops_in,
                wof_min_init=float(outer_states[i]["wof_min"]),
                bof_max_init=float(outer_states[i]["bof_max"]),
                wof_max_init=float(outer_states[i].get("wof_max", 1.0)),
                index_offset=int(outer_states[i]["index"]),
                memo_init=outer_states[i]["memo"],
                accum_init=float(outer_states[i]["accum"]),
                s_min_init=np.asarray(outer_states[i]["s_min"], dtype=float),
                s_max_init=np.asarray(outer_states[i]["s_max"], dtype=float),
                s_prev_init=np.asarray(outer_states[i]["s_prev"], dtype=float),
                # Même point de départ que l'éventail : contre S0, pas le spot brut.
                wof0_init=float(_S_past[step_k, :, i].min()),
                realvol_state_init={"sumsq": float(outer_states[i]["realvol_sumsq"]),
                                    "t": float(outer_states[i]["realvol_t"])},
                lvl_map=_lvl_i,
                rank_map=_rangs_observation(step_map, dt),
             **inner_payment_args, reference_spots=_basket_references(underlyings))
            mtf_i = float(np.mean(payoffs)) * 100
            rows = _mtf_flux_rows(flux, n_inner, t0)
            mat_t = T_max-t0
            recalled = sum(1 for s in stops_in if s < mat_t - 1e-9)
            marks[i] = {
                "mtf": round(mtf_i, 6),
                "future_flows": rows,
                "sum_pv": round(sum(x["pv"] for x in rows), 6),
                "recall_proba": round(recalled / n_inner * 100, 3),
                "expected_life": round(float(np.mean(stops_in)) + t0, 6),
            }

    for sc in out_scen:
        m = marks[sc["id"]]
        conditional = m['future_flows'] if sc['alive'] else []
        sc['mtf'] = (m['mtf'] if sc['alive'] else 0.) + sc['pending_pv']
        sc['residual_mark'] = m['mtf']
        sc['future_flows'] = sc['unsettled_flows'] + conditional
        sc['sum_pv'] = sum(f['pv'] for f in sc['future_flows'])
        sc['recall_proba'] = m['recall_proba'] if sc['alive'] else None
        sc['expected_life'] = m['expected_life'] if sc['alive'] else None
        # Écart de reconstitution : somme des VA des flux futurs - mark. Nul par
        # construction, publié pour que le tableau soit vérifiable à l'écran.
        sc["pv_residual"] = round(sc["sum_pv"] - sc["mtf"], 9)

    return {
        "t": t0,
        "k": k,
        "step_k": _step_at(full_dt,t0),
        "mtm_dates": grid,
        "main_price": round(main_price, 4),
        "steps_per_year": grid_frequency(),
        "n_outer": n_outer,
        "n_inner": n_inner,
        "T_max": round(T_max, 6),
        "r": r,
        "n_assets": n,
        "asset_names": [u.get("name") or f"S{a + 1}" for a, u in enumerate(underlyings)],
        "barriers": _mtf_barriers(script, script_source, user_params),
        "scenarios": out_scen,
        **({"local_vol_wings": local_vol_wings} if local_vol_wings else {}),
        "elapsed_ms": round((time.perf_counter() - t_run0) * 1000, 1),
    }
