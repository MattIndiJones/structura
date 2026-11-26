"""Greeks by common-random-number bump and reprice, and theta by ageing.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import numpy as np
from dataclasses import replace
from ..simulation_grid import grid_frequency, with_simulation_grid
from .bridge import resolve_bridge_substeps, validate_bridge_domain
from .parser import CompiledScript
from .monte_carlo import run_mc


# ── Greeks ──────────────────────────────────────────────────────────

def _correlation_bump(matrix, ci, cj, continuous=False):
    """Return a signed admissible one-factor bump, without PSD projection."""
    rho = matrix[ci][cj]
    bound = .99 if continuous else .999
    directions = (1., -1.) if rho+.05 <= bound else (-1., 1.)
    for scale in range(12):
        for sign in directions:
            candidate = [list(row) for row in matrix]
            value = rho+sign*.05/(2**scale)
            if not -bound <= value <= bound:
                continue
            candidate[ci][cj] = candidate[cj][ci] = value
            if np.linalg.eigvalsh(candidate).min() >= -1e-12:
                return value-rho
    return None


@with_simulation_grid
def compute_greeks(script: CompiledScript, underlyings, corr_matrix,
                   r: float, T: float, N: int, model: str, seed: int,
                   user_params,
                   selected: list | None = None, sigma_r: float = 0.0, a_r: float = 0.0,
                   yield_curve=None, barrier_monitoring: str = "weekly",
                   antithetic: bool = True, state: dict | None = None,
                   funding_curve=None, funding_spread: float = 0.0,
                   strike_set_t: float | None = None,
                   maturity_payment_t: float | None = None,
                   value_date_t: float = 0.0, local_vol_anchor=None):
    """CRN bump-and-reprice greeks.

    Every term of every finite difference — including the CENTER of gamma/
    theta/corr — is repriced here at N_g paths with the same seed, so the
    common Monte Carlo noise cancels. (An earlier version reused the main
    run's full-N price as the center: a different estimator whose sampling
    error does NOT cancel against the bumped legs, and gets amplified by the
    tiny FD denominators — gamma divides by 9e-4.)

    `state` carries a live deal's lifecycle position: spot in % of strike
    (`spot_base`), realized extrema, observation counter, memory coupons,
    accumulator, last fixings and realized variance — the same bundle
    api/deals.py:_mtm_core feeds to run_mc. Without it every bumped leg
    reprices a BRAND NEW product, so the sensitivities of a deal whose
    knock-in has already triggered, or whose coupon memory has accrued, have
    nothing to do with the ones reported. `state=None` is the pre-trade case
    and reproduces the previous behaviour exactly.

    How a bump interacts with that state, deliberately:
      - the spot vector is bumped MULTIPLICATIVELY around `spot_base`, so a
        deal 30% above its strike is shocked by 1% of where it actually is;
      - `wof0` is derived from the bumped vector rather than passed in, which
        is what makes it impossible to forget — leaving it at the unbumped
        level books a phantom first log-return into REALVOL;
      - realized extrema, memory and fixings do NOT move. They are facts, not
        model outputs. (And the running extrema accumulate over S[1:], so the
        bumped t=0 slice never enters them in the first place.)

    Avant la constatation initiale (`strike_set_t` passé dans `bumps` par
    l'appelant), le bump de spot garde exactement le même sens et ne demande
    aucun traitement particulier : il met à l'échelle toute la trajectoire, le
    fixing simulé compris, si bien que le payoff — écrit en pourcentage de ce
    fixing — est rigoureusement inchangé. Le delta tombe donc de lui-même à
    zéro sous un modèle invariant d'échelle, et ne garde sous vol locale que le
    déplacement de la trajectoire dans une nappe cotée en strikes absolus,
    c'est-à-dire le delta de SMILE. C'est l'homogénéité qui fait le travail,
    pas un cas particulier.
    """
    if selected is None:
        selected = ["delta", "gamma", "vega", "theta", "rho"]
    sel = set(selected)
    N_g = max(1000, N // 4)
    greeks: dict = {}
    n = len(underlyings)

    st = state or {}
    correlation_bumps = {(ci, cj): _correlation_bump(corr_matrix, ci, cj, barrier_monitoring=='continuous')
                         for ci in range(n) for cj in range(ci+1, n)} if 'corr' in sel else {}
    bridge_refinement = None
    if barrier_monitoring == "continuous" and n > 1:
        bridge_refinement = resolve_bridge_substeps(corr_matrix)
        if "corr" in sel:
            for ci in range(n):
                for cj in range(ci+1, n):
                    bumped = [row[:] for row in corr_matrix]
                    delta = correlation_bumps[(ci, cj)]
                    if delta is None:
                        continue
                    bumped[ci][cj] = bumped[cj][ci] = corr_matrix[ci][cj]+delta
                    validate_bridge_domain(underlyings, bumped, model, sigma_r > 0)
                    bridge_refinement = max(bridge_refinement, resolve_bridge_substeps(bumped))
    base_spots = list(st.get("spot_base") or [1.0] * n)

    def reprice(spot_vec=None, script_=None, T_=None, index_=None,
                maturity_payment_t_=None, **bumps) -> dict:
        sv = list(spot_vec) if spot_vec is not None else base_spots
        return run_mc(
            script if script_ is None else script_,
            underlyings, corr_matrix, r, T if T_ is None else T_, N_g, model, seed,
            antithetic=antithetic, user_params=user_params, sigma_r=sigma_r, a_r=a_r,
            yield_curve=yield_curve or [], barrier_monitoring=barrier_monitoring,
            bridge_substeps=bridge_refinement,
            funding_curve=funding_curve or [], funding_spread=funding_spread,
            strike_set_t=strike_set_t,
            maturity_payment_t=(maturity_payment_t if maturity_payment_t_ is None
                                else maturity_payment_t_),
            value_date_t=value_date_t,
            spot_mult=sv, spot_base=base_spots, local_vol_anchor=local_vol_anchor, qualify_lsv=False,
            wof_min_init=st.get("wof_min"), bof_max_init=st.get("bof_max"), wof_max_init=st.get("wof_max"),
            index_offset=st.get("index", 0) if index_ is None else index_,
            memo_init=st.get("memo"), accum_init=st.get("accum", 0.0),
            s_min_init=st.get("s_min"), s_max_init=st.get("s_max"),
            s_prev_init=st.get("s_prev"), wof0_init=min(sv),
            realvol_state_init=st.get("realvol_state"),
            fix_state_init=st.get("fix_state"),
            **bumps,
        )

    def price(**kw) -> float:
        return reprice(**kw)["price"]

    def _bumped(i: int, mult: float) -> list:
        v = list(base_spots)
        v[i] = base_spots[i] * mult
        return v

    base_res = reprice() if sel & {"gamma", "theta", "corr"} else None
    base_g = base_res["price"] if base_res is not None else None

    for i in range(n):
        if "delta" in sel or "gamma" in sel:
            pu = price(spot_vec=_bumped(i, 1.01))
            pd = price(spot_vec=_bumped(i, 0.99))
            if "delta" in sel:
                greeks[f"delta_{i+1}"] = round((pu - pd) / 0.02, 4)
            if "gamma" in sel:
                greeks[f"gamma_{i+1}"] = round(
                    (price(spot_vec=_bumped(i, 1.03)) - 2*base_g
                     + price(spot_vec=_bumped(i, 0.97))) / 0.0009, 4)

    if "vega" in sel:
        for i in range(n):
            va_up = [0.0]*n; va_up[i] = 0.01
            va_dn = [0.0]*n; va_dn[i] = -0.01
            greeks[f"vega_{i+1}"] = round((price(vol_add=va_up) - price(vol_add=va_dn)) / 0.02, 4)
        # Under Heston the vol
        # bump reaches only the leg independent of the variance Brownian, so
        # the figure above covers a fraction (1-rho_h^2) of the true volatility
        # sensitivity — half of it at the usual equity skew, a fifth at -0.9.
        # It is a real sensitivity, just not the one the bare word "vega"
        # implies, and a book aggregate that mixes it with GBM vegas is adding
        # quantities of different scope. Say so rather than let the label pass.
        if model == "heston":
            greeks["vega_scope"] = {
                "type": "leg_independante",
                "coverage": {u.get("name", f"S{i+1}"):
                             round(1.0 - float(u.get("rho_h", 0.0))**2, 4)
                             for i, u in enumerate(underlyings)},
            }
        elif model == "lsv":
            greeks['vega_scope'] = {'type': 'effective_local_vol', 'coverage': None,
                'definition': 'Additive bump of effective local volatility; variance process fixed, no recalibration',
                'unit': 'price per unit of volatility'}
        else:
            greeks["vega_scope"] = {"type": "total", "coverage": None}

    if "theta" in sel:
        theta, theta_event = _theta_and_event(
            script, T, st, base_g, base_res, reprice,
            maturity_payment_t=maturity_payment_t)
        greeks["theta"] = theta
        greeks["theta_event"] = theta_event

    if "rho" in sel:
        greeks["rho"] = round((price(dr=0.01) - price(dr=-0.01)) / 0.02, 4)

    # Sensibilite au spread emetteur. Meme echelle que le rho — derivee par
    # unite de spread — mais son signe est structurellement l'oppose : un
    # spread qui s'ecarte n'actualise que les flux, il ne remonte aucun
    # forward. Le desk lit plutot le DV01, un centieme de ce chiffre.
    if "credit" in sel:
        greeks["credit"] = round((price(ds=0.01) - price(ds=-0.01)) / 0.02, 4)

    if "corr" in sel and n > 1:
        for ci in range(n):
            for cj in range(ci+1, n):
                delta = correlation_bumps[(ci, cj)]
                key = f"corr_{ci+1}_{cj+1}"
                greeks.setdefault('corr_bumps', {})[key] = {
                    'requested': .05, 'effective': delta, 'scheme': 'forward' if delta and delta > 0 else 'backward' if delta else 'unavailable',
                    'reason': None if delta else 'No admissible one-factor PSD bump'}
                greeks[key] = (round((price(corr_delta={"ci":ci,"cj":cj,"delta":delta})-base_g)/delta, 4)
                               if delta is not None else None)

    return greeks


def _age_compiled_script(script: CompiledScript, shift: float) -> CompiledScript:
    """Move the unresolved contractual timeline while preserving its metadata."""
    eps = 1e-9
    aged_events = []
    for ev in script.events:
        if ev.type != "AT":
            aged_events.append(ev)
            continue

        kept = [index for index, event_t in enumerate(ev.dates)
                if event_t > shift + eps]
        if not kept:
            continue

        def _aligned(values, transform):
            if values is None:
                return None
            return [transform(values[index]) for index in kept]

        aged_events.append(replace(
            ev,
            dates=[round(ev.dates[index] - shift, 6) for index in kept],
            payment_dates=_aligned(
                ev.payment_dates,
                lambda value: None if value is None else round(value - shift, 6),
            ),
            window_dates=_aligned(
                ev.window_dates,
                lambda dates: [round(value - shift, 6) for value in dates
                               if value > shift + eps],
            ),
            ranks=_aligned(ev.ranks, lambda value: value),
            releves_passes=_aligned(ev.releves_passes, lambda value: value),
        ))

    strike_fix_dates = None
    if script.strike_fix_dates is not None:
        strike_fix_dates = [round(value - shift, 6)
                            for value in script.strike_fix_dates
                            if value > shift + eps]

    return replace(script, events=aged_events, strike_fix_dates=strike_fix_dates)


def _theta_and_event(script: CompiledScript, T: float, st: dict,
                     base_g: float | None, base_res: dict | None,
                     reprice, *,
                     maturity_payment_t: float | None = None
                     ) -> tuple[float | None, dict | None]:
    """Time decay over one grid step when no contractual event is crossed.

    Aging the product by a week is the finest decay this weekly grid can
    represent, but an observation falling inside that week detaches its cash
    flow, and a raw price difference then books that detachment as "decay": a
    5% coupon over 7 days reads as -0.7/day. True at the deal level, useless
    once summed over a book, where it swamps every genuine theta.

    Crossing an observation requires executing its full state transition. The
    generic bump-and-reprice layer cannot safely invent that realized outcome,
    so it returns an explicit reason instead of a misleading scalar theta.

    Returns (theta per calendar day, event descriptor or None). theta is None
    when rolling the state forward would take a guess: a strike-fixing date
    inside the window (the fixing would be silently dropped from the average
    rather than folded into fix_state), or a REALVOL script (the week's
    realized variance is simulated on one leg and would have to be invented on
    the other).
    """
    eps = 1e-9
    dt_step = 1.0 / grid_frequency()
    if T <= 2 * dt_step:
        return None, None

    if script.strike_fix_dates and any(d <= dt_step + eps for d in script.strike_fix_dates):
        return None, {"reason": "fenetre_strike_fix"}
    if st.get("realvol_state"):
        return None, {"reason": "realvol"}

    crossed_window_points = sorted({
        round(value, 6)
        for ev in script.events
        for dates in (ev.window_dates or [])
        for value in dates
        if 0 < value <= dt_step + eps
    })
    if crossed_window_points:
        return None, {
            "reason": "constatation_window_transition_required",
            "t_years": crossed_window_points[-1],
        }

    crossed = sorted({round(d, 6) for ev in script.events if ev.type == "AT"
                      for d in ev.dates if 0 < d <= dt_step + eps})

    if crossed:
        # Crossing an observation is a state transition, not a mere removal
        # of one event from the future script.  The event may update coupon
        # memory, accumulators, fixings, extrema or terminate the product.  A
        # stripped-script comparison cannot reconstruct that path-dependent
        # post-event state, so publishing a scalar theta (or a synthetic event
        # PV) is more dangerous than explicitly declaring it unavailable.
        return None, {
            "reason": "observation_transition_required",
            "t_years": crossed[-1],
            "terminates": bool(script.has_stop),
        }

    aged_payment_t = (None if maturity_payment_t is None
                      else max(0.0, maturity_payment_t - dt_step))
    aged = reprice(script_=_age_compiled_script(script, dt_step),
                   T_=T - dt_step,
                   maturity_payment_t_=aged_payment_t)["price"]
    # Per calendar day: the product was aged by dt_step YEARS, which is
    # 365.25*dt_step days on the engine's own day-count — 7.02 on the weekly
    # grid, not 7. Hard-coding 7 was right only by coincidence of SY=52, and
    # would have silently rescaled every theta by SY/52 the day the grid
    # changed: at 252 steps the product ages 1.45 days while the result would
    # still be divided by 7, understating decay almost fivefold.
    per_day = 365.25 * dt_step
    # Daily theta on a unit-notional product is commonly below 1bp. Four
    # decimals rounded a 3% zero-coupon from 0.0000797 to 0.0001, a 25% display
    # error that then propagated into nominal-weighted portfolio risk.
    return round((aged - base_g) / per_day, 8), None
