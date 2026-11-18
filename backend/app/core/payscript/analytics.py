"""Analytics on the pricing engine: payoff profile, displayed paths and
probability analysis.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import numpy as np
from ..compute_budget import validate_compiled_dates, validate_problem_dimensions
from ..simulation_grid import with_simulation_grid
from .parser import CompiledScript
from .time_grid import metadata as _axis_metadata
from .evaluation import _basket_references, _eval_paths, _rangs_observation, _strike_fix_steps
from .mc_axis import TIME_AXIS_POLICY, _event_schedule, _simulation_axis
from .monte_carlo import run_mc


# ── Analytics: Payoff Profile ───────────────────────────────────────

@with_simulation_grid
def run_payoff_profile(script: CompiledScript, underlyings, corr_matrix,
                        r: float, T_max: float, user_params=None, n_pts: int = 151,
                        state: dict | None = None) -> dict:
    """Sweep spot levels 0%–150% and evaluate payoff on a FLAT path — the
    underlying PINNED at that exact level at every observation date, for the
    product's whole life (no drift, no vol, nothing to simulate). This is
    the standard reading of a payoff/scenario diagram ("if the underlying
    stayed at X%, here's what you get"), and the only one that makes a
    barrier/autocall step function unambiguous: a level below the barrier
    never crosses it, period.

    (An earlier version instead simulated a near-zero-vol GBM path and
    rescaled it — which still carried the real risk-neutral (r-q) drift even
    at ~0 vol, so a sub-barrier level could quietly drift up and cross an
    autocall barrier on a LATER observation date. For a memory-coupon script
    (PAY CALL * COUPON * INDEX, paying every accrued coupon at once on the
    date it finally triggers) that produced a payoff spike — e.g. 124% at a
    98% starting level vs 108% at 100% — that read as a jump in value but
    was really just the same coupon rate paid over more accrued periods
    because the "98%" level didn't actually stay at 98%. Pinning the level
    removes the ambiguity at the source instead of explaining it away after
    the fact — annualized_coupons below is a still-useful secondary view for
    memory-coupon structures, independent of this fix.)

    Concentrated on the downside (0-150% rather than 40-200%) and sampled
    densely (151 pts, ~1% spacing) so genuine payoff discontinuities (autocall/KO
    barriers) render as near-vertical jumps instead of a slanted chord between
    two widely-spaced points — cheaper than detecting each script's barriers
    symbolically, and it generalizes to every PayScript, not just gear puts."""
    user_params = user_params or {}
    n = len(underlyings)
    validate_problem_dimensions(T_max, n)
    validate_compiled_dates(script)
    levels = [0.0 + i * 1.50 / (n_pts - 1) for i in range(n_pts)]

    ts, dt = _simulation_axis(T_max, script)
    step_map, mat_events, pay_map = _event_schedule(script.events, ts, dt, horizon=T_max)

    # A single deterministic path per level — no noise to average over, the
    # level IS the whole path (post-fixing).
    N_p = 1
    S_neutral = np.ones((ts + 1, n, N_p), dtype=np.float64)
    fix_steps = _strike_fix_steps(script, ts, dt)
    fix_end_step = max(fix_steps) if fix_steps else 0

    # Realization time per level, alongside the payoff itself — lets a
    # memory-coupon payoff (see docstring above) also be read as an
    # annualized rate, which stays flat across levels even though the raw
    # payoff still legitimately steps up at each barrier a pinned level sits
    # exactly on. stop_times_out collects one entry per path that actually
    # STOPs (autocalled); a level whose path runs to maturity without
    # stopping gets none, and falls back to T_max below.
    payoffs = []
    annualized_coupons = []
    realization_times = []
    # La fenêtre de départ réalisée ne s'applique pas ici : le balayage épingle
    # le niveau lui-même, en pourcentage de S0, et un S0 recomposé depuis les
    # relevés passés redéfinirait l'axe qu'on dessine. Elle ne va pas non plus à
    # l'évaluateur, qui ne la prend plus — la lui passer faisait tomber le profil
    # de tout produit en cours de vie.
    etat_evaluateur = {k: v for k, v in (state or {}).items() if k != "fix_state_init"}
    for x in levels:
        S = S_neutral.copy()
        S[fix_end_step + 1:] = x
        stop_times: list[float] = []
        # `state` porte ce que le passé a déjà écrit sur un produit en cours de
        # vie : coupons en mémoire, extrema franchis, compteur de constatations.
        # Sans lui, le profil dessine la courbe du produit NEUF — il oublie les
        # coupons accumulés et redessine des barrières déjà franchies.
        _, pfs_raw = _eval_paths(script, S, ts, n, N_p, dt, r, user_params,
                                  step_map, mat_events, {}, record=False,
                                  rank_map=_rangs_observation(step_map, dt),
                                  stop_times_out=stop_times, **etat_evaluateur, reference_spots=_basket_references(underlyings))
        payoff = round(sum(pfs_raw) / N_p * 100, 3)
        t_realized = (sum(stop_times) / len(stop_times)) if stop_times else T_max
        payoffs.append(payoff)
        realization_times.append(round(t_realized, 10))
        annualized_coupons.append(round((payoff - 100.0) / max(t_realized, 1e-12), 3))

    return {
        "time_axis": _axis_metadata(TIME_AXIS_POLICY, T_max, ts, dt),
        "levels": [round(x * 100, 1) for x in levels],
        "payoffs": payoffs,
        "realization_times": realization_times,
        "annualized_coupons": annualized_coupons,
    }


# ── Analytics: MC Sample Paths ──────────────────────────────────────

def _run_analysis(script, underlyings, corr_matrix, r, T_max, N, model, seed,
                  user_params, barrier_monitoring, state, display_limit, **market):
    details = {'display_limit': display_limit}
    result = run_mc(script, underlyings, corr_matrix, r, T_max, N, model, seed,
                    user_params=user_params, barrier_monitoring=barrier_monitoring,
                    analysis_out=details, **market, **dict(state or {}))
    rows = details['rows']
    counts = {key: sum(row['outcome'] == key for row in rows)
              for key in ('autocall', 'ki', 'normal')}
    total = len(rows)
    event_counts = {}
    for row in rows:
        if row['stop_time'] is not None:
            t = round(row['stop_time'], 4)
            event_counts[t] = event_counts.get(t, 0)+1
    result.update(path_data=details['path_data'], rows=rows,
                  autocall_count=counts['autocall'], ki_count=counts['ki'], normal_count=counts['normal'],
                  has_autocall=counts['autocall'] > 0, total=total,
                  obs_times=sorted({round(t, 4) for event in script.events
                                    for t in event.dates or []}), event_counts=event_counts,
                  expected_life=round(sum(row['stop_time'] if row['stop_time'] is not None else T_max
                                          for row in rows)/total, 10),
                  estimator={'engine': 'run_mc', 'independent_draws': N,
                             'simulated_paths': total, 'antithetic': market.get('antithetic', True)},
                  classification={'ki': 'Below-par nominal payoff without STOP; not contractual KI',
                                  'normal': 'At-or-above-par nominal payoff without STOP',
                                  'autocall': 'Explicit PayScript STOP',
                                  'percentiles': 'Discounted total cash flows at valuation value date'})
    if display_limit and model == 'localvol' and len(underlyings) == 1:
        result['local_vol_trace'] = details.get('local_vol_trace')
    return result


@with_simulation_grid
def run_mc_paths(script: CompiledScript, underlyings, corr_matrix,
                 r: float, T_max: float, N_display: int = 50, N_stat: int = 500,
                 model: str = 'constant', seed: int = 42, user_params=None,
                 barrier_monitoring: str = 'weekly', state: dict | None = None,
                 yield_curve=None, funding_curve=None, funding_spread=0., sigma_r=0., a_r=0.,
                 antithetic=False, maturity_payment_t=None, value_date_t=0., strike_set_t=None, local_vol_anchor=None):
    result = _run_analysis(script, underlyings, corr_matrix, r, T_max, N_stat, model, seed,
                           user_params, barrier_monitoring, state, N_display,
                           yield_curve=yield_curve, funding_curve=funding_curve, funding_spread=funding_spread,
                           sigma_r=sigma_r, a_r=a_r, antithetic=antithetic,
                           maturity_payment_t=maturity_payment_t, value_date_t=value_date_t, strike_set_t=strike_set_t, local_vol_anchor=local_vol_anchor)
    result.pop('rows')
    result.update(T_max=T_max, user_params=user_params or {})
    return result


@with_simulation_grid
def run_mc_proba(script: CompiledScript, underlyings, corr_matrix,
                 r: float, T_max: float, N: int = 5000, model: str = 'constant', seed: int = 42,
                 user_params=None, yield_curve=None, barrier_monitoring: str = 'weekly',
                 capital_ref: float | None = None, state: dict | None = None,
                 funding_curve=None, funding_spread=0., sigma_r=0., a_r=0., antithetic=False,
                 maturity_payment_t=None, value_date_t=0., strike_set_t=None, local_vol_anchor=None):
    # The cap is explicit in the estimator metadata; no financial input is dropped.
    count = min(10000, max(2000, N))
    result = _run_analysis(script, underlyings, corr_matrix, r, T_max, count, model, seed,
                           user_params, barrier_monitoring, state, 0,
                           yield_curve=yield_curve, funding_curve=funding_curve, funding_spread=funding_spread,
                           sigma_r=sigma_r, a_r=a_r, antithetic=antithetic,
                           maturity_payment_t=maturity_payment_t, value_date_t=value_date_t, strike_set_t=strike_set_t, local_vol_anchor=local_vol_anchor)
    rows = result.pop('rows')
    raw = sorted(row['raw'] for row in rows)
    pv = sorted(row['pv'] for row in rows)
    total = len(rows)
    maximum = max(raw)
    result.update(
        percentiles={f'p{p}': round(pv[min(total-1, int(total*p/100))]*100, 2) for p in (5,25,75,95)},
        final_wofs=[round(row['final_wof']*100, 2) for row in rows],
        ki_pct=round(result['ki_count']/total*100, 1),
        autocall_pct=round(result['autocall_count']/total*100, 1),
        capital_loss_pct=round(sum(x < 1 for x in raw)/total*100, 1),
        net_loss_pct=round(sum(x < capital_ref for x in pv)/total*100, 1) if capital_ref is not None else None,
        full_coupon_pct=round(sum(maximum > 0 and x >= maximum*.995 for x in raw)/total*100, 1),
        positive_payoff_pct=round(sum(x > 0 for x in raw)/total*100, 1),
        zero_payoff_pct=round(sum(x == 0 for x in raw)/total*100, 1),
        positive_payoff_count=sum(x > 0 for x in raw),
        zero_payoff_count=sum(x == 0 for x in raw),
        negative_payoff_count=sum(x < 0 for x in raw),
        max_payoff=round(maximum*100, 2), capital_ref=capital_ref)
    result['estimator']['requested_draws'] = N
    return result
