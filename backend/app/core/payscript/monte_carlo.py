"""Main Monte Carlo entry point: run_mc and its window report.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
import time
from numpy.random import default_rng
from ..compute_budget import ABSOLUTE_WORK_LIMIT, WORKER_MEMORY_LIMIT_BYTES, count_compiled_dates, ensure_budget, estimate_mc, validate_compiled_dates
from ..simulation_grid import grid_frequency, with_simulation_grid
from .bindings import effective_parameters
from .bridge import bridge_metadata, bridge_note, resolve_bridge_substeps, validate_bridge_domain
from .parser import CompiledScript
from .time_grid import durations as _durations, metadata as _axis_metadata, step_at as _step_at, time_at as _time_at, times as _times
from .diffusion import _atm_step_vols, _bridge_extrema, _local_vol_at_spot, _simulate_gbm, _simulate_heston, _simulate_lsv, _simulate_lv, _simulate_sabr, cholesky, validate_model
from .evaluation import _basket_references, _constater, _eval_paths, _fixer_le_strike_sur_les_trajectoires, _rangs_observation, _strike_fix_steps, _window_steps
from .local_vol import _build_lv_grid
from .mc_axis import SY, TIME_AXIS_POLICY, _event_schedule, _simulation_axis
from .rates import _build_rate_term, _df_at_time, _forward_rate_arr, _funding_df_arr, _rate_coupled_factor, _stochastic_rate_paths, _validate_short_rate_parameters


# ── Main Monte Carlo entry point ────────────────────────────────────

def _average_antithetic_flux_maps(base: dict, anti: dict) -> dict:
    """Average each dated flow across the two legs of every antithetic pair.

    The price estimator averages paired paths, so its decomposition must do the
    same entry by entry. A posteriori rescaling of the base leg can force the PV
    total to match while assigning the wrong amount to individual dates or flow
    labels whenever the two legs trigger different contractual branches.
    """
    averaged: dict = {}
    for key in base.keys() | anti.keys():
        left, right = base.get(key), anti.get(key)
        template = left or right
        averaged[key] = {
            field: template[field]
            for field in template
            if field not in {"n", "sum", "pv"}
        }
        for field in ("n", "sum", "pv"):
            averaged[key][field] = 0.5 * (
                (left.get(field, 0.0) if left else 0.0)
                + (right.get(field, 0.0) if right else 0.0)
            )
    return averaged

@with_simulation_grid
def run_mc(script: CompiledScript,
           underlyings,
           corr_matrix,
           r: float,
           T_max: float,
           N: int,
           model: str = "constant",
           seed: int = 42,
           antithetic: bool = True,
           user_params=None,
           spot_mult=None,
           spot_base=None,
           vol_add=None,
           # Annees d'ici la constatation initiale, quand elle n'a pas encore eu
           # lieu. Les trajectoires diffusent alors depuis le spot du jour et
           # chacune fixe SON strike a cette date — cf.
           # _fixer_le_strike_sur_les_trajectoires. None = strike deja connu,
           # comportement inchange.
           strike_set_t: float | None = None,
           dr: float = 0.0,
           dt_add: float = 0.0,
           corr_delta=None,
           yield_curve=None,
           # Spread emetteur. Actualisation SEULE — voir _funding_df_arr pour
           # pourquoi il ne doit surtout pas rejoindre la courbe de taux.
           funding_curve=None,
           funding_spread: float = 0.0,
           ds: float = 0.0,
           sigma_r: float = 0.0,
           a_r: float = 0.0,
           barrier_monitoring: str = "weekly",
           bridge_substeps: int | None = None,
           # Year-fraction of the product's own payment date — when the final
           # redemption's cash actually moves. None keeps it paid at maturity,
           # which is what every caller without a term sheet in hand can say.
           maturity_payment_t: float | None = None,
           # Year-fraction of the value date on the strike-anchored axis. The
           # diffusion starts where the initial level is fixed; the price is the
           # amount exchanged at settlement. 0.0 makes the two the same date,
           # which is what every caller that knows only one date says.
           value_date_t: float = 0.0,
           wof_min_init=None,
           bof_max_init=None,
           index_offset: int = 0,
           memo_init: dict | None = None,
           accum_init: float = 0.0,
           s_min_init=None,
           s_max_init=None,
           s_prev_init=None,
           wof0_init: float | None = None,
           realvol_state_init: dict | None = None,
           fix_state_init: dict | None = None,
           per_path_flows: bool = False, per_path_flow_labels: bool = False,
           analysis_out: dict | None = None, flows_at_payment: bool = False,
           additional_grid_dates=(), gbm_atm_curve=False, lsv_leverage=None,
           local_vol_anchor=None, qualify_lsv=None,
           # Callable (ts, dt, n, N, rng) -> S (ts+1, n, N) replacing the
           # model's diffusion — the PRIIPs historical bootstrap
           # (core/priips_bootstrap.py). The payoff is evaluated as usual.
           path_simulator=None):

    t0 = time.perf_counter()
    if path_simulator is not None and (antithetic or barrier_monitoring == "continuous"
                                       or sigma_r > 0 or spot_mult is not None):
        raise ValueError(
            "Trajectoires fournies : sans variables antithétiques, sans monitoring "
            "continu, sans taux stochastique et sans choc de spot.")
    _validate_short_rate_parameters(sigma_r, a_r)
    if barrier_monitoring not in ("weekly", "continuous"):
        raise ValueError(
            f"barrier_monitoring invalide: {barrier_monitoring!r} — valeurs admises: "
            f"'weekly' (extrema sur la grille MC choisie, défaut) ou 'continuous' "
            f"(pont brownien intra-pas)."
        )
    use_bridge = barrier_monitoring == "continuous"
    validate_model(model, underlyings)
    user_params = effective_parameters(script.params, user_params)
    n = len(underlyings)
    T = T_max + dt_add
    validate_compiled_dates(script)
    corr = [row[:] for row in corr_matrix]
    if corr_delta:
        ci, cj, delta = corr_delta["ci"], corr_delta["cj"], corr_delta["delta"]
        v = max(-0.999, min(0.999, corr[ci][cj] + delta))
        corr[ci][cj] = corr[cj][ci] = v
    if use_bridge:
        validate_bridge_domain(underlyings, corr, model, sigma_r > 0)
    refinement = resolve_bridge_substeps(corr, bridge_substeps) if use_bridge and n > 1 else None
    grid_dates = [strike_set_t, *additional_grid_dates]
    grid_dates.extend(node[0] for u in underlyings for node in (u.get("dividend_curve") or []))
    ts, dt = _simulation_axis(T, script, grid_dates)
    step_vols = _atm_step_vols(underlyings, dt, ts) if gbm_atm_curve else None
    ensure_budget(
        estimate_mc(
            simulation_steps=ts,
            operation="monte_carlo",
            corr_matrix=corr,
            bridge_refinement=refinement,
            maturity_years=T,
            underlyings=n,
            paths=N,
            model=model,
            antithetic=antithetic,
            continuous_monitoring=use_bridge,
            stochastic_rates=sigma_r > 0,
            expanded_dates=count_compiled_dates(script),
        ),
        memory_limit_bytes=WORKER_MEMORY_LIMIT_BYTES,
        work_limit=ABSOLUTE_WORK_LIMIT,
    )
    r_eff = r + dr
    sq_dt = np.sqrt(dt)
    step_map, mat_events, pay_map = _event_schedule(
        script.events, ts, dt, horizon=T, maturity_payment_t=maturity_payment_t)

    corr_repair: dict = {}
    L = cholesky(corr, n, repair_report=corr_repair)

    use_heston = model == "heston"
    use_lv     = model == "localvol"
    use_sabr   = model == "sabr"
    use_lsv    = model == "lsv"

    rng = default_rng(seed)
    # N = number of independent observations (pairs when antithetic, standalone paths otherwise).
    # Antithetic simulates 2*N total paths (N base + N antithetic) and averages each pair;
    # variance reduction comes from the negative correlation between legs, not from fewer draws.
    N_pairs = N

    # Supplied paths need no normal draws: their own generator consumes rng.
    Z  = rng.standard_normal((ts, n, N_pairs)) if path_simulator is None else None
    Zv = rng.standard_normal((ts, n, N_pairs)) if (use_heston or use_lsv) else None
    Za = rng.standard_normal((ts, n, N_pairs)) if use_sabr   else None

    # One rate term for the whole run: discounting, drift and smile calibration
    # all read from it, so they cannot disagree. Built after every rng draw
    # above and before the local-vol grid below, which now consumes it — it
    # touches no random state, so the stream is unchanged.
    rates = _build_rate_term(yield_curve or [], ts, dt, r, dr)
    df_arr = rates.df

    # Le spread emetteur s'applique APRES, sur l'actualisation seule : r_det
    # ci-dessous continue de porter les forwards sans risque, donc le drift des
    # sous-jacents ne bouge pas d'un iota quand le credit de l'emetteur bouge.
    # `ds` est le choc parallele du spread, ce qui fait du credit une vraie
    # derivee et non une derivee partielle — meme role que `dr` pour le rho.
    _fund_df = _funding_df_arr(funding_curve, funding_spread, ts, dt)
    if ds:
        _t_ax = _times(dt, ts)
        _shift = np.exp(-ds * _t_ax)
        _fund_df = _shift if _fund_df is None else _fund_df * _shift
    if _fund_df is not None:
        df_arr = df_arr * _fund_df

    # Deterministic drift term, shaped (ts,1): broadcasts against (ts,N) in
    # _simulate_gbm, and reduces to a scalar under the [step] indexing the four
    # step-wise simulators use. None when there is no curve, in which case the
    # simulators fall back on the scalar r_eff exactly as before.
    r_det = None if rates.step_fwd is None else rates.step_fwd[:, None]

    if local_vol_anchor is not None:
        if (len(local_vol_anchor) != n or any(not math.isfinite(float(x)) or float(x) <= 0 for x in local_vol_anchor)):
            raise ValueError('Ancrage de surface invalide : un spot positif par sous-jacent est requis.')
    lv_data = None
    lsv_calibration = None
    local_vol_wings = []
    lsv_limits = []
    if use_lsv:
        from .lsv_leverage import frozen_leverage, supports_frozen_lsv, RESIDUAL_TRAINING_PATHS, TRAINING_PATHS
        frozen_lsv = supports_frozen_lsv(
            underlyings, yield_curve=yield_curve, sigma_r=sigma_r,
            barrier_monitoring=barrier_monitoring, strike_set_t=strike_set_t,
            residual=(spot_base is not None or fix_state_init is not None) and local_vol_anchor is None)
    else:
        frozen_lsv = False
    if use_lsv and local_vol_anchor is not None and not frozen_lsv:
        raise ValueError('LSV résiduel : surface SSVI, taux et dividendes plats, sans quanto, et monitoring sur grille MC requis.')
    if use_lv or use_lsv:
        lv_data = _build_lv_grid(underlyings, rates, ts, dt, allow_ssvi_wings=use_lv or frozen_lsv,
                                 wing_diagnostics=local_vol_wings)
    if frozen_lsv and lsv_leverage is None:
        lsv_leverage = frozen_leverage(underlyings, r_eff, _durations(dt, ts), lv_data, diagnostics=lsv_limits,
            training_paths=RESIDUAL_TRAINING_PATHS if local_vol_anchor is not None else TRAINING_PATHS)
    if lsv_leverage is not None and (not frozen_lsv or len(lsv_leverage) != n
                                    or any(g.shape != (ts, lv_data[1]) for g in lsv_leverage)):
        raise ValueError("Le levier LSV ne correspond pas à la grille de pricing.")

    if frozen_lsv and local_vol_anchor is not None and qualify_lsv is not False:
        from .lsv_leverage import qualify_residual_leverage
        lsv_calibration = qualify_residual_leverage(
            script, user_params, underlyings, r_eff, _durations(dt, ts), lv_data,
            lsv_leverage, local_vol_anchor)

    # Optional stochastic short rate: a single shared Gaussian factor (ABM when
    # a_r=0, Hull-White when a_r>0 — see _stochastic_rate_paths). sigma_r=0 is
    # the default and falls through to the deterministic term above. Each leg
    # (base/anti) gets its own rate path from Z_r/-Z_r, paired like Z/Zv/Za.
    use_stoch_rate = sigma_r > 0
    Z_r = rng.standard_normal((ts, N_pairs)) if use_stoch_rate else None

    # Coupling the assets to the rate factor changes how the diffusion block
    # must be factorised — see _blend_rate_factor. Only when the factor is
    # actually live AND at least one asset is correlated to it: otherwise L
    # stays chol(R) and every existing price is reproduced to the bit.
    rho_rS_vec = [float(u.get("rho_rS", 0.0) or 0.0) for u in underlyings]
    if use_stoch_rate and any(v != 0.0 for v in rho_rS_vec):
        L = _rate_coupled_factor(corr_repair.get("matrix_used") or corr,
                                 rho_rS_vec, n)

    if use_stoch_rate:
        # The OU factor fits the risk-free curve only. Funding must neither
        # enter the asset drift nor be counted again in stochastic discounting.
        fwd = _forward_rate_arr(rates.df, dt)
        r_path_base, df_base = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, Z_r)
        r_path_anti, df_anti = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, -Z_r)
        # Apply deterministic funding once, after the risk-free rate diffusion.
        if _fund_df is not None:
            df_base = df_base * _fund_df[:, None]
            df_anti = df_anti * _fund_df[:, None]
            if (not np.isfinite(df_base).all() or not np.isfinite(df_anti).all()
                    or (df_base <= 0.0).any() or (df_anti <= 0.0).any()):
                raise ValueError("Le funding produit des facteurs d'actualisation non finis ou nuls.")
    else:
        # The drift follows the same curve that discounts the payoff. r_det is
        # None without a curve, so the simulators keep using the scalar r_eff.
        r_path_base = r_path_anti = r_det
        df_base = df_anti = df_arr

    flux_map: dict[str, dict] = {}
    def collect_analysis(paths, rows):
        if analysis_out is None:
            return
        analysis_out.setdefault('rows', []).extend(rows)
        samples = analysis_out.setdefault('path_data', [])
        stride = max(1, ts//60)
        for pi in range(min(len(rows), max(0, analysis_out.get('display_limit', 0)-len(samples)))):
            stop = rows[pi]['stop_time']
            end = min(ts, max(0, _step_at(dt, stop))) if stop is not None else ts
            steps = sorted(set(range(0, end+1, stride)) | {end})
            samples.append({'times': [round(_time_at(dt, i), 12) for i in steps],
                            'wof': [round(float(paths[i, :, pi].min()), 4) for i in steps],
                            'outcome': rows[pi]['outcome']})
        if not (use_lv and n == 1 and analysis_out.get('display_limit', 0)):
            return
        threshold = .60
        grids, nodes, lo, hi = lv_data
        log_step = (hi-lo)/(nodes-1)
        bump = vol_add[0] if vol_add is not None else 0.
        for pi, row in enumerate(rows):
            previous = analysis_out.get('local_vol_trace')
            if previous and previous['crossing_step'] < len(previous['steps']):
                break
            stop = row['stop_time']
            end = min(ts, max(0, _step_at(dt, stop))) if stop is not None else ts
            spots = paths[:end+1, 0, pi]
            crossings = np.flatnonzero((spots[:-1] >= threshold) & (spots[1:] < threshold))
            if not len(crossings):
                continue
            crossing = int(crossings[0])
            if previous and crossing == end-1:
                continue
            analysis_out['local_vol_trace'] = {
                'threshold': threshold, 'crossing_step': crossing+1,
                'steps': [{
                    'step': i+1, 'start_time': float(_time_at(dt, i)),
                    'end_time': float(_time_at(dt, i+1)),
                    'start_spot': float(spots[i]), 'end_spot': float(spots[i+1]),
                    'local_vol': float(_local_vol_at_spot(spots[i] if local_vol_anchor is None else spots[i]/local_vol_anchor[0], grids[0][i], lo, log_step, bump)),
                } for i in range(end)],
            }

    # A Greeks delta/gamma bump passes a spot_mult that differs from the
    # baseline to shock one asset's spot. Feeding that straight into the
    # simulator scales the WHOLE path from t=0 — including a STRIKE_FIX window,
    # if the script has one — so REF gets shocked in lockstep with WOF and the
    # bump cancels out of PERF=WOF/REF (delta/gamma come back ~0, the bug this
    # fixes). Instead, simulate at the baseline level and apply only the bump
    # RATIO to the segment after the fixing window closes — exact for
    # GBM/Heston (their log-return dynamics don't depend on the absolute spot
    # level), an approximation for SABR (beta!=1) and Local Vol (genuinely
    # level-dependent vol), but a good one at the small bump sizes Greeks use.
    #
    # spot_base is what the caller considers "not bumped": [1]*n pre-trade, the
    # live deal's norm_spots on a residual reprice. Comparing against it rather
    # than against 1.0 is what keeps a live deal whose spot has merely moved
    # (norm_spots != 1, no bump at all) out of this branch — otherwise its MtM
    # would be simulated from 1.0 instead of from today's spot, which is the
    # bug this baseline fixes. A 2-D spot_mult is Mark-to-Future's per-scenario
    # seeding, never a bump: excluded outright.
    _base_vec = list(spot_base) if spot_base is not None else [1.0] * n
    _bump_needs_delay = (
        bool(script.strike_fix_dates) and spot_mult is not None
        and np.ndim(spot_mult) == 1
        and any(abs(m - b) > 1e-12 for m, b in zip(spot_mult, _base_vec))
    )
    _sim_spot_mult = _base_vec if _bump_needs_delay else spot_mult

    def _apply_delayed_bump(S: np.ndarray) -> np.ndarray:
        if not _bump_needs_delay:
            return S
        fix_steps = _strike_fix_steps(script, ts, dt)
        fix_end_step = max(fix_steps) if fix_steps else 0
        S = S.copy()
        for i, (m, b) in enumerate(zip(spot_mult, _base_vec)):
            if abs(m - b) > 1e-12:
                S[fix_end_step + 1:, i, :] *= m / b
        return S

    vol_base = np.empty((ts, n, N_pairs), dtype=np.float64) if use_bridge else None

    # Pas de grille où tombe la constatation initiale. Même quantification
    # hebdomadaire que les dates d'observation : les deux doivent s'accorder,
    # sans quoi une constatation pourrait précéder le strike qui la référence.
    strike_step = (0 if not strike_set_t
                   else min(max(_step_at(dt, strike_set_t), 1), ts))

    if path_simulator is not None:
        S_base = path_simulator(ts, dt, n, N_pairs, rng)
        if S_base.shape != (ts + 1, n, N_pairs):
            raise ValueError("Trajectoires fournies aux mauvaises dimensions.")
    elif use_heston:
        S_base = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, Z, Zv, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                   vol_out=vol_base)
    elif use_lsv:
        lv_grids, nK, lkm, lkx = lv_data
        S_base = _simulate_lsv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                r_eff, L, Z, Zv, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                r_path_base, Z_r, vol_out=vol_base, leverage_grids=lsv_leverage, local_vol_anchor=local_vol_anchor)
    elif use_lv:
        lv_grids, nK, lkm, lkx = lv_data
        S_base = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                               r_eff, L, Z, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                               r_path_base, Z_r, vol_out=vol_base, local_vol_anchor=local_vol_anchor)
    elif use_sabr:
        S_base = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                 r_eff, L, Z, Za, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                 vol_out=vol_base)
    else:
        S_base = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                r_eff, L, Z, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                vol_out=vol_base, step_vols=step_vols)
    S_base = _apply_delayed_bump(S_base)
    # Bridge extrema from the (possibly bumped) paths — the bridge scales with
    # the level in log-space, so post-bump is the consistent order. Uniform
    # draws happen only in continuous mode: the weekly path consumes the exact
    # same rng stream as before this feature existed.
    bridge_details = bridge_metadata(n, corr, refinement) if use_bridge else None
    br_min_b, br_max_b = _bridge_extrema(
        S_base, vol_base, dt, rng, corr, substeps=refinement,
        diagnostics=bridge_details) if use_bridge else (None, None)
    # Puis, si le strike n'est pas encore constaté, chaque trajectoire fixe le
    # sien. Après le pont, qui se tire lui aussi aux vrais niveaux.
    raw_references_base = _basket_references(underlyings)
    if raw_references_base is not None and strike_step:
        raw_references_base = np.asarray(raw_references_base)[:, None] * S_base[strike_step]
    S_base, br_min_b, br_max_b = _fixer_le_strike_sur_les_trajectoires(
        S_base, strike_step, br_min_b, br_max_b)
    # Puis la constatation sur periode : S0 par sous-jacent, rebasage, et les
    # niveaux constates aux dates qui portent une fenetre.
    S_base, br_min_b, br_max_b, lvl_b = _constater(
        script, S_base, ts, n, N_pairs, br_min_b, br_max_b,
        fix_state_init, step_map, dt=dt)

    stop_times_base: list[float] | None = [] if script.has_stop else None
    flows_base: list | None = [] if per_path_flows else None
    labels_base = [] if per_path_flows and per_path_flow_labels else None
    # One discount factor per distinct payment date, computed once on the same
    # curve as the rest of the run. A payment date lands between two grid steps
    # (or past the last one) — see _df_at_time.
    # Le prix coté est le montant échangé à la value date, pas la PV au
    # fixing initial. P(0, value date) est le zéro-coupon d'aujourd'hui, donc
    # déterministe même sous taux stochastiques : on lit la courbe, jamais les
    # trajectoires.
    pv_rebase = (1.0 / _df_at_time(df_arr, value_date_t, dt, ts, r_eff)
                 if value_date_t else 1.0)

    pay_times = {t for entries in pay_map.values() for t in entries if t is not None}
    pay_df_base = {t: _df_at_time(df_base, t, dt, ts, r_eff) for t in pay_times}
    # Sans date de paiement explicite, le remboursement est actualise a
    # l'horizon REEL du produit et non au pas de grille le plus proche : sur
    # une grille hebdomadaire, l'arrondi valait jusqu'a 3,5 jours, soit ~3 bps.
    # Invisible sur une maturite ronde (elle tombe pile sur un pas), systematique
    # des qu'un calendrier CONSTAT fixe la fin a une date quelconque.
    mat_t = maturity_payment_t if maturity_payment_t is not None else T
    mat_pay_df_base = _df_at_time(df_base, mat_t, dt, ts, r_eff)

    payoffs_base, raw_base = _eval_paths(script, S_base, ts, n, N_pairs, dt, r_eff,
                                          user_params, step_map, mat_events, flux_map,
                                          record=True, df_arr=df_base,
                                          pay_map=pay_map, pay_df=pay_df_base,
                                          mat_pay_df=mat_pay_df_base,
                                          mat_pay_t=mat_t,
                                          pv_rebase=pv_rebase,
                                          stop_times_out=stop_times_base,
                                          flows_out=flows_base,
                                          flows_at_payment=flows_at_payment,
                                          flow_labels_out=labels_base,
                                          bridge_min=br_min_b, bridge_max=br_max_b,
                                          wof_min_init=wof_min_init, bof_max_init=bof_max_init,
                                          index_offset=index_offset, memo_init=memo_init,
                                          accum_init=accum_init,
                                          s_min_init=s_min_init, s_max_init=s_max_init,
                                          s_prev_init=s_prev_init, wof0_init=wof0_init,
                                          realvol_state_init=realvol_state_init,
                                          lvl_map=lvl_b,
                                          rank_map=_rangs_observation(step_map, dt),
                                          state_start_step=strike_step, reference_spots=raw_references_base,
                                          analysis_out=(base_details := []) if analysis_out is not None else None)
    if analysis_out is not None:
        collect_analysis(S_base, base_details)

    payoffs_anti: list[float] = []
    raw_anti:     list[float] = []
    flux_map_anti: dict = {}
    flows_anti = None
    labels_anti = None
    if antithetic:
        # The antithetic leg is the same draw with the sign flipped: it needs no
        # new randomness, and it should need no new memory either. Two
        # allocations happened anyway. `-Z` built a full copy of every normal
        # tensor, and the base leg's paths stayed alive while the antithetic
        # ones were allocated, so the peak carried two path tensors instead of
        # one. Flipping in place and releasing the base leg first removes both:
        # for a 3-year weekly run at 100k paths that is roughly 500 MB back.
        # Negation is exact in IEEE-754 and nothing below re-reads the base
        # arrays, so every price is unchanged to the bit.
        del S_base, br_min_b, br_max_b, lvl_b
        np.negative(Z, out=Z)
        if Zv is not None:
            np.negative(Zv, out=Zv)
        if Za is not None:
            np.negative(Za, out=Za)
        if Z_r is not None:
            np.negative(Z_r, out=Z_r)
        Z_r_anti = Z_r if use_stoch_rate else None
        # Same buffer as the base leg — its bridge extrema were drawn above and
        # nothing reads it any more.
        vol_anti = vol_base
        if use_heston:
            S_anti = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                       r_eff, L, Z, Zv, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                       vol_out=vol_anti)
        elif use_lsv:
            S_anti = _simulate_lsv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, Z, Zv, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                    r_path_anti, Z_r_anti, vol_out=vol_anti, leverage_grids=lsv_leverage, local_vol_anchor=local_vol_anchor)
        elif use_lv:
            S_anti = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, Z, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                   r_path_anti, Z_r_anti, vol_out=vol_anti, local_vol_anchor=local_vol_anchor)
        elif use_sabr:
            S_anti = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                     r_eff, L, Z, Za, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                     vol_out=vol_anti)
        else:
            S_anti = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, Z, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                    vol_out=vol_anti, step_vols=step_vols)
        S_anti = _apply_delayed_bump(S_anti)
        br_min_a, br_max_a = _bridge_extrema(
            S_anti, vol_anti, dt, rng, corr, substeps=refinement,
            diagnostics=bridge_details) if use_bridge else (None, None)
        raw_references_anti = _basket_references(underlyings)
        if raw_references_anti is not None and strike_step:
            raw_references_anti = np.asarray(raw_references_anti)[:, None] * S_anti[strike_step]
        S_anti, br_min_a, br_max_a = _fixer_le_strike_sur_les_trajectoires(
            S_anti, strike_step, br_min_a, br_max_a)
        S_anti, br_min_a, br_max_a, lvl_a = _constater(
            script, S_anti, ts, n, N_pairs, br_min_a, br_max_a,
            fix_state_init, step_map, dt=dt)
        stop_times_anti: list[float] | None = [] if script.has_stop else None
        flows_anti = [] if per_path_flows else None
        labels_anti = [] if per_path_flows and per_path_flow_labels else None
        payoffs_anti, raw_anti = _eval_paths(script, S_anti, ts, n, N_pairs, dt, r_eff,
                                              user_params, step_map, mat_events, flux_map_anti,
                                              record=True, df_arr=df_anti,
                                              pay_map=pay_map,
                                              pay_df={t: _df_at_time(df_anti, t, dt, ts, r_eff)
                                                      for t in pay_times},
                                              mat_pay_df=_df_at_time(df_anti, mat_t, dt, ts, r_eff),
                                              mat_pay_t=mat_t,
                                              pv_rebase=pv_rebase,
                                              stop_times_out=stop_times_anti,
                                              flows_out=flows_anti,
                                              flows_at_payment=flows_at_payment,
                                              flow_labels_out=labels_anti,
                                              bridge_min=br_min_a, bridge_max=br_max_a,
                                              wof_min_init=wof_min_init, bof_max_init=bof_max_init,
                                              index_offset=index_offset, memo_init=memo_init,
                                              accum_init=accum_init,
                                              s_min_init=s_min_init, s_max_init=s_max_init,
                                              s_prev_init=s_prev_init, wof0_init=wof0_init,
                                              realvol_state_init=realvol_state_init,
                                              lvl_map=lvl_a,
                                              rank_map=_rangs_observation(step_map, dt),
                                              state_start_step=strike_step, reference_spots=raw_references_anti,
                                              analysis_out=(anti_details := []) if analysis_out is not None else None)
        if analysis_out is not None:
            collect_analysis(S_anti, anti_details)

    # Price: antithetic average of paired paths (lower variance).
    payoffs_avg = [(p1 + p2) / 2 for p1, p2 in zip(payoffs_base, payoffs_anti)] \
                  if payoffs_anti else payoffs_base

    # Individual undiscounted payoffs (both legs) for the distribution histogram.
    raw_all = sorted(raw_base + raw_anti) if raw_anti else sorted(raw_base)

    # Discounted payoffs for statistical quantities (VaR5, median, IC95).
    pv_all  = sorted(payoffs_base + payoffs_anti) if payoffs_anti else sorted(payoffs_base)

    N_eff  = len(payoffs_avg)
    N_hist = len(raw_all)
    price  = sum(payoffs_avg) / N_eff
    payoffs_arr = np.array(payoffs_avg)
    se = math.sqrt(float(np.var(payoffs_arr, ddof=1)) / N_eff)
    mid    = N_hist // 2
    median = (pv_all[mid-1] + pv_all[mid]) / 2 if N_hist % 2 == 0 else pv_all[mid]
    var5   = pv_all[int(N_hist * 0.05)]
    prob_gt100 = sum(1 for p in raw_all if p > 1.0) / N_hist

    if antithetic:
        flux_map = _average_antithetic_flux_maps(flux_map, flux_map_anti)

    # Fugit = E[τ] — probability-weighted expected life of the product.
    # Averaged over base + antithetic legs for more stable estimate.
    fugit: float | None = None
    if script.has_stop and stop_times_base:
        all_stop = stop_times_base + (stop_times_anti if antithetic and stop_times_anti else [])
        fugit = round(sum(all_stop) / len(all_stop), 10)

    elapsed = (time.perf_counter() - t0) * 1000

    # float() coercions: the per-path cash flows get contaminated by numpy
    # scalars (df_arr discounting) — round() preserves np.float64, and numpy
    # scalars leaking into API payloads break FastAPI's JSON encoder (np.bool_)
    # or just pollute downstream types (np.float64).
    return {
        "steps_per_year": grid_frequency(),
        **({"surface_context": {"policy": "ASOF_FORWARD_MONEYNESS_V1",
             "anchor_spot_over_contract_strike": list(local_vol_anchor),
             "variance_policy": "CONTEXT_V0_ASSUMPTION" if use_lsv else None,
             "initial_variance": [u.get('v0', .04) for u in underlyings] if use_lsv else None},
             "lsv_calibration": lsv_calibration} if local_vol_anchor is not None else {}),
        "time_axis": _axis_metadata(TIME_AXIS_POLICY, T, ts, dt),
        "price": round(float(price), 6),
        "ic95": [round(float(price - 1.96*se), 6), round(float(price + 1.96*se), 6)],
        "median": round(float(median), 6),
        "var5": round(float(var5), 6),
        # Top of the discounted-payoff distribution: pv_max is the best possible
        # outcome in present value (for a capped product — autocall, reverse
        # convertible — it's the cap, e.g. next-call redemption); pv_p95 both
        # serves as "favourable scenario" for uncapped payoffs and, compared to
        # pv_max, detects whether the payoff IS capped (flat top). Feeds the
        # residual-upside / early-exit signal of the client valuation note.
        "pv_max": round(float(pv_all[-1]), 6),
        "pv_p95": round(float(pv_all[min(N_hist - 1, int(N_hist * 0.95))]), 6),
        "prob_gt100": round(float(prob_gt100), 6),
        "payoffs": [round(p, 4) for p in raw_all],   # undiscounted, for histogram
        # Dated cash flows, one list of (t, montant) per path — opt-in, since
        # this is the only output that grows with the number of flows.
        # `payoffs` above is a plain sum: it says a path paid 1.08 but not
        # that it paid it after one year, so nothing downstream can work out
        # the return the investor actually earned. `flux_table` aggregates
        # across paths and cannot answer it either. This can.
        **({"path_flows": (flows_base + flows_anti) if flows_anti else flows_base}
           if per_path_flows else {}),
        **({"path_flow_labels": labels_base + (labels_anti or []),
            "path_stop_times": (stop_times_base or [T_max]*N_pairs)
                + ((stop_times_anti or [T_max]*N_pairs) if antithetic else [])}
           if per_path_flows and per_path_flow_labels else {}),
        "flux_table": flux_map,
        "elapsed_ms": round(elapsed, 1),
        "n_paths": N,
        "n_eff": N_eff,
        "fugit": fugit,
        # Present only when the correlation matrix had to be projected onto the
        # nearest PSD one. Small moves are numerical noise, but the caller is
        # entitled to know the price used a matrix it did not supply.
        "corr_repair": corr_repair or None,
        "barrier_monitoring": barrier_monitoring,
        "barrier_monitoring_note": bridge_note(n, corr, refinement) if use_bridge else None,
        "barrier_monitoring_details": bridge_details,
        **({"local_vol_wings": local_vol_wings} if local_vol_wings else {}),
        **({"lsv_frozen_leverage": True} if frozen_lsv else {}),
        **({"lsv_limits": lsv_limits} if lsv_limits else {}),
        # Publish the actual distinct contractual fixings used by each window.
        "constatation_windows": _window_report(script, ts, dt) or None,
    }


def _window_report(script: CompiledScript, ts: int,
                   dt: float = 1.0 / SY) -> list[dict]:
    """Points de grille effectivement retenus par chaque fenêtre, vs demandés."""
    out: list[dict] = []

    seen: set = set()

    def _add(label: str, reduction: str, dates, t: float | None):
        asked = len(dates or [])
        kept = len(_window_steps(dates, ts, dt))
        if not asked:
            return
        # Deux événements qui constatent la même fenêtre au même jour — un
        # coupon et sa protection, par exemple — n'en font qu'une à l'écran.
        key = (label, reduction, None if t is None else round(t, 6), asked, kept)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "constatation": label, "reduction": reduction,
            "t": None if t is None else round(t, 6),
            "points_demandes": asked, "points_retenus": kept,
            "degeneree": kept <= 1 < asked,
        })

    if script.strike_fix_reduction:
        _add("STRIKE_FIX", script.strike_fix_reduction, script.strike_fix_dates, 0.0)
    for ev in script.events:
        if not ev.reduction or not ev.window_dates:
            continue
        for i, d in enumerate(ev.dates):
            if i < len(ev.window_dates):
                _add("observation", ev.reduction, ev.window_dates[i], d)
    return out
