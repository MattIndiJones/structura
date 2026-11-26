"""Mark-to-Future: outer scenarios, inner revaluations and dated statistics.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
import time
from dataclasses import replace
from numpy.random import default_rng
from ..compute_budget import ABSOLUTE_WORK_LIMIT, WORKER_MEMORY_LIMIT_BYTES, count_compiled_dates, ensure_budget, estimate_mc_batch
from ..simulation_grid import grid_frequency, with_simulation_grid
from .parser import CompiledEvent, CompiledScript
from .time_grid import durations as _durations, step_at as _step_at, time_at as _time_at
from .diffusion import _atm_step_vols, _simulate_gbm, _simulate_heston, _simulate_lsv, _simulate_lv, _simulate_sabr, cholesky, validate_model
from .evaluation import _basket_references, _constater, _eval_paths, _fusionner_realise, _rangs_observation, cle_de_fenetre
from .local_vol import _build_lv_grid
from .mc_axis import SY, _event_schedule, _simulation_axis
from .rates import _build_rate_term


MTF_MAX_BATCH = 20_000   # cap simulated paths per inner Mark-to-Future chunk (memory bound)
# Below this many surviving contracts a Mark-to-Future date is flagged `thin`:
# on a highly callable product the late dates can be left with a handful of
# paths, and a 5th percentile read off them is noise wearing the clothes of a
# risk figure. The figures are still returned — suppressing them belongs to the
# display, not to the engine, or a caller running a small deliberate batch gets
# empty results with no explanation.
MTF_MIN_ALIVE = 50


@with_simulation_grid
def build_mtf_dates(T_max: float, n_dates: int) -> list[float]:
    """Evenly-spaced MTM date grid. The last date is T_max minus one week, which
    avoids re-pricing a degenerate near-zero-maturity residual product. Dates are
    floored at one weekly step: the replay of the realized past indexes a path
    tensor of `round(t0 * grid_frequency())` steps, and that tensor is empty below half a
    step — a mark "3 days from now" has no grid to stand on."""
    if T_max <= 1 / grid_frequency():
        return [T_max * (i+1)/(n_dates+1) for i in range(n_dates)]
    t_last = round(T_max - 1 / grid_frequency(), 6)
    floor = round(1 / grid_frequency(), 6)
    out: list[float] = []
    for i in range(n_dates):
        d = max(floor, round(t_last * (i + 1) / n_dates, 4))
        # Two marks landing on the same weekly step are the same mark: identical
        # replay, identical spot, identical inherited state. Only a product too
        # short to carry n_dates distinct steps gets here, and it gets fewer
        # dates rather than a row repeated under two labels.
        if out and _mtf_step(d) <= _mtf_step(out[-1]):
            continue
        out.append(d)
    return out


def _mtf_step(t0: float) -> int:
    """The weekly step a Mark-to-Future date snaps to. Single source of truth:
    the outer replay, the past/future split of the event calendar and the
    residual horizon must all agree on it, or an event lands on both sides."""
    return round(t0 * grid_frequency())


def _shift_events_for_mtf(events: list[CompiledEvent], t0: float,
                          passe_jusqu_a: float | None = None, *, exact=False) -> list[CompiledEvent]:
    """Re-anchor a script's events at t0 for residual pricing: AT event dates already
    resolved by the outer scenario are dropped; remaining dates are shifted by -t0.
    AT_MATURITY is left untouched — it always fires at the end of the residual
    horizon, whatever that horizon is.

    The past/future split is made on the SNAPPED WEEKLY STEP, not on the raw date.
    The outer replay resolves every event whose step is <= step_k; testing `d > t0`
    here instead made the two criteria non-complementary, and an observation falling
    between t0 and its own step boundary (up to half a week, i.e. any date in
    (t0, (step_k + 0.5) / grid_frequency()]) was replayed by the outer scenario AND repriced by
    the inner one. A phoenix coupon was then paid twice — once into `realized_flows`,
    once into the mark — and the autocall barrier was tested twice a week apart.
    On a realistic CONSTAT calendar (year-fractions in ACT/365.25, so almost never
    exactly on the weekly lattice) this hit ~17% of MTM dates and moved the mark by
    several hundred basis points.

    `passe_jusqu_a` : quand le passé a été rejoué sur un HISTORIQUE et non simulé
    par un scénario extérieur, la coupe suit ce rejeu, qui lit une date dès que
    sa clôture existe (`_LectureParDate`). C'est la dernière date qu'il a lue, en
    années depuis le strike : ce qui tombe après reste à simuler, même dans la
    semaine de la valorisation. Le pas hebdomadaire est le complément exact d'un
    scénario extérieur, pas celui d'un historique : une constatation du lendemain
    de la valorisation, sans clôture encore, n'était ni rejouée ni simulée."""
    step_k = _mtf_step(t0)

    def _a_venir(d: float) -> bool:
        if passe_jusqu_a is not None:
            return d > passe_jusqu_a + 1e-6
        if exact:
            return d > t0 + 1e-12
        return max(1, round(d * grid_frequency())) > step_k

    shifted = []
    for ev in events:
        if ev.type != "AT":
            shifted.append(ev)
            continue
        keep = [i for i, d in enumerate(ev.dates) if _a_venir(d)]
        future_dates = [(ev.dates[i] - t0 if exact else round(ev.dates[i] - t0, 6)) for i in keep]
        if future_dates:
            # Les dates de paiement suivent leur constatation dans le decalage :
            # les perdre ici ferait actualiser au fixing tout le residuel, donc
            # un MtM incoherent avec le prix d origine du meme produit.
            pays = ev.payment_dates
            wins = (ev.window_dates
                    if ev.window_dates and len(ev.window_dates) == len(ev.dates) else None)
            deja = (ev.releves_passes
                    if ev.releves_passes and len(ev.releves_passes) == len(ev.dates) else None)
            # La fenetre d'une constatation la suit, mais seulement par ses
            # relevés À VENIR. Ceux qui sont derrière la coupe sont constatés :
            # leur réduction voyage à part (`CompiledScript.releves_realises`),
            # et on retient combien il y en avait. Décalés avec les autres, ils
            # tombaient à un temps négatif, que la grille ramène au premier pas :
            # trois cours réalisés remplacés par un seul point simulé une
            # semaine plus tard.
            fenetres = passes = None
            if wins:
                fenetres, passes = [], []
                for i in keep:
                    a_venir = [d for d in wins[i] if _a_venir(d)]
                    fenetres.append([(d - t0 if exact else round(d - t0, 6)) for d in a_venir])
                    passes.append((deja[i] if deja else 0) + len(wins[i]) - len(a_venir))
            shifted.append(CompiledEvent(
                type=ev.type, dates=future_dates, fn=ev.fn,
                # Le calendrier nomme la fenêtre, avec le rang : c'est la clé de
                # sa part réalisée.
                constat_ref=ev.constat_ref,
                payment_dates=([(pays[i] - t0 if exact else round(pays[i] - t0, 6)) for i in keep]
                               if pays and len(pays) == len(ev.dates) else None),
                window_dates=fenetres,
                reduction=ev.reduction,
                # Le rang suit sa date dans le décalage — c'est tout l'intérêt
                # de le porter par la date : la troisième constatation reste la
                # troisième quand on la reprice à mi-vie, sans qu'aucun compteur
                # n'ait à être réamorcé.
                ranks=([ev.ranks[i] for i in keep]
                       if ev.ranks and len(ev.ranks) == len(ev.dates) else None),
                releves_passes=passes if passes and any(passes) else None))
    return shifted


def _mtf_past_step_map(script: CompiledScript, step_k: int, dt=1.0 / SY, *, at_maturity=False) -> dict[int, list]:
    """AT events the outer scenario has already resolved by the mark date, keyed
    by weekly step. Complement of _shift_events_for_mtf by construction — same
    `max(1, round(d * grid_frequency())) <= step_k` test on both sides, one written once."""
    # The in-life calendar is rounded to six decimals, while its horizon is
    # exact. Only at maturity use the same tolerance as the initial pricer.
    tolerance = 1e-6 if at_maturity else 1e-12
    past, _, _ = _event_schedule(script.events, step_k, dt, horizon=_time_at(dt, step_k), date_tolerance=tolerance)
    return past


def _mtf_residual_script(script: CompiledScript, t0: float, T_max: float) -> tuple:
    """Residual contract seen from the mark date: (script, step_map, mat_events,
    ts_eff). Shared by the fan and the drill-down — the panel that explains a
    mark must reprice the very same residual product the fan marked."""
    residual_events = _shift_events_for_mtf(script.events, t0)
    step_k = _mtf_step(t0)
    residual_fix = [round(d - t0, 6) for d in (script.strike_fix_dates or [])
                    if max(1, round(d * grid_frequency())) > step_k]
    residual = CompiledScript(events=residual_events, init_fn=script.init_fn,
                              params=script.params, constats=script.constats,
                              has_stop=script.has_stop, monitors=script.monitors,
                              strike_fix_dates=residual_fix or None,
                              strike_fix_reduction=script.strike_fix_reduction)
    ts_eff = max(1, round(max(1 / grid_frequency(), round(T_max - t0, 6)) * grid_frequency()))
    step_map, mat_events, _ = _event_schedule(residual_events, ts_eff, 1.0 / grid_frequency())
    return residual, step_map, mat_events, ts_eff


def _exact_mtf_residual(script, t0, horizon, intervals=None):
    residual = replace(script, events=_shift_events_for_mtf(script.events, t0, exact=True),
                       strike_fix_dates=[d-t0 for d in (script.strike_fix_dates or []) if d > t0+1e-12] or None)
    ts, dt = (_simulation_axis(horizon-t0, residual) if intervals is None
              else (len(intervals), intervals))
    schedule, maturity, _ = _event_schedule(residual.events, ts, dt, horizon=horizon-t0)
    return residual, schedule, maturity, ts, dt


def _mtf_realized_fix(script: CompiledScript, S_outer: np.ndarray,
                      step_k: int, dt=1.0 / SY) -> tuple[dict | None, list[int]]:
    """Split a `CONSTAT() STRIKE_FIX` window at the mark date.

    Returns (realized reduction over the fixing dates already behind t0, PER
    UNDERLYING and per outer scenario — shape (n, N_outer), which is what
    _niveau_initial consumes —, and the list of past steps). Without it the residual repricing saw only the
    still-future fixing dates: a window half elapsed averaged the wrong subset, and
    a window fully elapsed fell back on the neutral 1.0, i.e. an Asian-strike
    product was marked as if its strike had never been fixed."""
    if not script.strike_fix_dates:
        return None, []
    past = sorted({max(1, _step_at(dt, d)) for d in script.strike_fix_dates
                   if d <= _time_at(dt, step_k)+1e-12})
    if not past:
        return None, []
    w = S_outer[1:step_k + 1][[s - 1 for s in past], :, :]   # (len(past), n, N_outer)
    return ({"n": len(past), "sum": w.sum(axis=0),
             "min": w.min(axis=0), "max": w.max(axis=0)}, past)


def _mtf_releves_realises(script: CompiledScript, S_past: np.ndarray,
                          step_k: int, dt=1.0 / SY) -> dict:
    """La part déjà constatée, par scénario extérieur, des fenêtres de
    constatation à cheval sur la date de marque.

    Chaque scénario extérieur a relevé les cours de ses dates passées ; le
    résiduel ne simule que les relevés à venir (_shift_events_for_mtf). Il faut
    donc lui transmettre ceux-là, réduits par sous-jacent, une valeur par
    scénario (n, N_outer), lus sur `S_past` — la trajectoire extérieure déjà
    exprimée contre S0. Les pas se comptent DISTINCTS, comme dans la fenêtre
    entière : parts passée et à venir partitionnent le même ensemble de pas.

    La part que le script porte déjà — l'historique d'un produit vivant —
    s'y ajoute."""
    realises = dict(getattr(script, "releves_realises", None) or {})
    vus: set[str] = set()
    for ev in script.events:
        if ev.type != "AT" or not ev.reduction or not ev.window_dates:
            continue
        for i, d in enumerate(ev.dates[:len(ev.window_dates)]):
            if d <= _time_at(dt, step_k)+1e-12:
                continue            # constatation passée : rejouée à l'extérieur
            cle = cle_de_fenetre(ev.constat_ref,
                                 ev.ranks[i] if ev.ranks and i < len(ev.ranks) else None)
            if cle in vus:
                continue
            vus.add(cle)
            pas = sorted({max(1, _step_at(dt, t)) for t in ev.window_dates[i]
                          if t <= _time_at(dt, step_k)+1e-12})
            if not pas:
                continue
            w = S_past[pas, :, :]                         # (len(pas), n, N_outer)
            realises[cle] = _fusionner_realise(
                realises.get(cle),
                {"n": len(pas), "sum": w.sum(axis=0),
                 "min": w.min(axis=0), "max": w.max(axis=0)})
    return realises


def _tranche_realise(etat: dict | None, sl: slice, repeat: int) -> dict | None:
    """Une part réalisée restreinte à un lot de scénarios extérieurs, chacun
    répété sur ses chemins intérieurs. Une part commune à tous les scénarios —
    (n,) ou (n, 1) — se diffuse telle quelle."""
    if etat is None:
        return None

    def _t(v) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        v = v.reshape(v.shape[0], -1)
        return v if v.shape[1] == 1 else np.repeat(v[:, sl], repeat, axis=1)

    return {"n": etat["n"], "sum": _t(etat["sum"]),
            "min": _t(etat["min"]), "max": _t(etat["max"])}


def _scenario_realise(etat: dict | None, i: int) -> dict | None:
    """La part réalisée d'UN scénario extérieur, par sous-jacent (n,)."""
    if etat is None:
        return None

    def _t(v) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        v = v.reshape(v.shape[0], -1)
        return v[:, 0] if v.shape[1] == 1 else v[:, i]

    return {"n": etat["n"], "sum": _t(etat["sum"]),
            "min": _t(etat["min"]), "max": _t(etat["max"])}


def _simulate_mtf_outer(underlyings, corr_matrix, r: float, mtm_dates: list[float],
                         N: int, seed: int, spot_mult=None, *, time_steps=None, step_vols=None) -> np.ndarray:
    """Outer scenario generator: N correlated GBM paths from t=0 to the last MTM date.

    Returns the spot tensor only. It used to also return running worst-of-min /
    best-of-max series, which no caller read — run_mark_to_future takes those from
    the per-scenario replay instead, because the replay's extrema are the ones that
    stop at each mark date and carry the same path history as the rest of the state.
    Building them here allocated two more (ts, N) arrays per run for nothing."""
    n = len(underlyings)
    dt = 1.0 / grid_frequency() if time_steps is None else time_steps
    ts = max(1, round(mtm_dates[-1] * grid_frequency())) if time_steps is None else len(time_steps)
    sq_dt = np.sqrt(dt)
    L = cholesky(corr_matrix, n)
    Z = default_rng(seed).standard_normal((ts, n, N))
    return _simulate_gbm(ts, n, N, dt, sq_dt, underlyings, r, L, Z,
                         spot_mult=spot_mult, step_vols=step_vols)


MTF_PRICER_MODELS = frozenset(('constant', 'heston', 'sabr', 'localvol', 'lsv'))


@with_simulation_grid
def mtf_simulation_axis(script, maturity, marks, aligned_grid):
    horizon = maturity if aligned_grid else max(maturity, marks[-1])
    return _simulation_axis(horizon, script, [maturity, *marks])


def _mtf_model_paths(model, underlyings, r, L, intervals, count, rng, spot,
                     local_grid=None, factor_init=None, factor_out=None, step_vols=None):
    steps, assets = len(intervals), len(underlyings)
    sqrt_dt = np.sqrt(intervals)
    shocks = rng.standard_normal((steps, assets, count))
    args = (steps, assets, count, intervals, sqrt_dt, underlyings, r, L, shocks)
    if model in ('heston', 'sabr'):
        simulate = _simulate_heston if model == 'heston' else _simulate_sabr
        return simulate(*args, rng.standard_normal(shocks.shape), spot,
                        factor_init=factor_init, factor_out=factor_out)
    if model == 'localvol':
        return _simulate_lv(*args, *local_grid[:4], spot,
                            local_vol_anchor=local_grid[4] if len(local_grid)>4 else None)
    if model == 'lsv':
        return _simulate_lsv(*args, rng.standard_normal(shocks.shape), *local_grid[:4], spot,
                             leverage_grids=local_grid[4], factor_init=factor_init, factor_out=factor_out,
                             local_vol_anchor=local_grid[5] if len(local_grid)>5 else None)
    return _simulate_gbm(*args, spot, step_vols=step_vols)


def _mtf_outer_state(model, underlyings, corr, r, marks, count, seed, spot, intervals, step_vols=None,
                     *, wing_diagnostics=None, lsv_leverage=None, local_vol_anchor=None):
    if model == 'constant':
        return (_simulate_mtf_outer(underlyings, corr, r, marks, count, seed,
                                    spot_mult=spot, time_steps=intervals, step_vols=step_vols), None, None)
    steps, assets = len(intervals), len(underlyings)
    factors = None
    local_grid = None
    if model in ('heston', 'sabr', 'lsv'):
        factors = np.empty((steps + 1, assets, count))
    if model in ('localvol', 'lsv'):
        local_grid = _build_lv_grid(underlyings, _build_rate_term([], steps, intervals, r), steps, intervals,
                                    allow_ssvi_wings=True, wing_diagnostics=wing_diagnostics)
    if model == 'lsv':
        if lsv_leverage is None or any(grid.shape != (steps, local_grid[1]) for grid in lsv_leverage):
            raise ValueError("Le levier LSV doit être qualifié sur la grille du Mark to Future.")
        local_grid += (lsv_leverage,)
    if local_grid is not None and local_vol_anchor is not None:
        local_grid += (local_vol_anchor,)
    spots = _mtf_model_paths(model, underlyings, r, cholesky(corr, assets), intervals,
                             count, default_rng(seed), spot, local_grid, factor_out=factors)
    return spots, factors, local_grid


def _mtf_inner_paths(model, underlyings, r, L, dt, n_inner, seed, k, start, end,
                     spot, factors, local_grid, step, step_vols=None):
    chunk = slice(start, end)
    initial_spot = np.repeat(spot[:, chunk], n_inner, axis=1)
    initial_factor = None if factors is None else np.repeat(factors[step, :, chunk], n_inner, axis=1)
    if local_grid is not None:
        grids, nK, lo, hi = local_grid[:4]
        leverage = local_grid[4] if model == 'lsv' else None
        anchor_index = 5 if model == 'lsv' else 4
        anchor = local_grid[anchor_index] if len(local_grid)>anchor_index else None
        local_grid = ([grid[step:] for grid in grids], nK, lo, hi)
        if leverage is not None:
            local_grid += (tuple(grid[step:] for grid in leverage),)
        if anchor is not None:
            local_grid += (anchor,)
    rng = default_rng(seed + 1_000_003 * (k + 1) + start)
    return _mtf_model_paths(model, underlyings, r, L, dt, (end-start)*n_inner, rng,
                            initial_spot, local_grid, initial_factor,
                            step_vols=None if step_vols is None else step_vols[step:step+len(dt)])


def _mtf_reject_unsupported(model: str, barrier_monitoring: str,
                            yield_curve, sigma_r: float,
                            underlyings=None, *, aligned_grid=False) -> None:
    """Capabilities Mark-to-Future does not carry. Shared by the fan and the
    drill-down so the two can never disagree on what they accept — a drill-down
    that priced a scenario the fan refuses would explain a number nobody sees."""
    if yield_curve:
        raise ValueError(
            "La courbe de taux n'est pas encore supportée en Mark-to-Future : "
            "l'analyse est à taux plat de bout en bout (dérive outer, dérive "
            "inner et actualisation). La conserver silencieusement comparerait "
            "un éventail actualisé à plat à un P₀ actualisé sur la courbe. "
            "Repassez en taux plat pour cette analyse."
        )
    if sigma_r:
        raise ValueError(
            "Les taux stochastiques ne sont pas encore supportés en "
            "Mark-to-Future : la revalorisation résiduelle ne porte pas le "
            "facteur de taux. Générez l'analyse avec sigma_r = 0."
        )
    if any(u.get("dividend_curve") for u in (underlyings or [])):
        raise ValueError(
            "La courbe de dividende n'est pas encore supportée en "
            "Mark-to-Future : chaque revalorisation future devrait décaler les "
            "buckets de dividende à sa propre date. La réappliquer depuis "
            "l'année 1 donnerait un éventail cohérent en apparence mais faux. "
            "Repassez en dividende plat pour cette analyse."
        )
    # The outer and inner generators diffuse here, outside run_mc: they do not
    # lay the compo FX leg, and an inner run restarts its step count at each
    # mark, so it would read a foreign curve at the wrong date. A flat quanto
    # goes through the simulators' drift and stays exact.
    for u in underlyings or []:
        if u.get("fx_mode") == "compo":
            raise ValueError(
                "Le compo n'est pas encore supporté en Mark-to-Future : les scénarios "
                "extérieurs et intérieurs ne portent pas la trajectoire de change. "
                "Passez le sous-jacent en quanto ou en historique pour cette analyse.")
        if u.get("fx_mode") and u.get("ccy_curve"):
            raise ValueError(
                "La courbe de taux de la devise du sous-jacent n'est pas encore supportée en "
                "Mark-to-Future. Repassez en taux plat de devise pour cette analyse.")
    supported = MTF_PRICER_MODELS if aligned_grid else {'constant'}
    if model not in supported:
        if aligned_grid:
            raise ValueError("Modèle indisponible en Mark-to-Future. Le levier LSV doit être qualifié avant activation.")
        raise ValueError(
            "Le Mark-to-Future et son drill-down sont disponibles uniquement en "
            "Constant (GBM). Les scénarios extérieurs et le repricing intérieur "
            "doivent utiliser la même dynamique ; Heston, SABR, Local Vol et LSV "
            "ne sont pas encore pris en charge de bout en bout."
        )
    if barrier_monitoring == "continuous":
        raise ValueError(
            "Le monitoring continu des barrières n'est pas encore supporté en "
            "Mark-to-Future (l'héritage d'état outer→inner reste sur extrema "
            "sur grille MC). Repassez en monitoring sur grille MC pour cette analyse."
        )


def _mtf_date_stats(pvs: np.ndarray, p0: float) -> dict:
    """Distribution diagnostics for one MTM date (pvs in % of notional).

    Percentiles use the standard linear-interpolation estimator (numpy's default,
    the same one every risk system and spreadsheet reports). The previous
    `sorted[int(p * n)]` returned the (floor(p*n) + 1)-th order statistic, whose
    expected rank is (floor(p*n) + 1) / (n + 1) — badly off in the tails on the
    small samples this function actually sees. Mark-to-Future conditions on
    survival, so a callable product leaves a few dozen contracts alive at the late
    dates: at n = 60 the published "P01" was literally the sample MINIMUM (9 points
    of notional below the true 1st percentile) and "P99" the sample MAXIMUM. Those
    two rows are the tail-risk rows of the fan chart."""
    n = len(pvs)

    def q(p: float) -> float:
        return float(np.quantile(pvs, p))

    mean = float(pvs.mean())
    # ── Décomposition gagnants / perdants ───────────────────────────
    # Espérances CONDITIONNELLES au signe du résultat, à ne pas confondre avec
    # e_upside : celle-ci moyenne max(MTM-100, 0) sur TOUT l'échantillon (elle
    # compte les perdants comme des zéros et répond « combien de potentiel
    # au-dessus du pair ce produit porte-t-il en moyenne »), tandis que
    # avg_gain moyenne le seul sous-échantillon gagnant (« quand ça marche, ça
    # rapporte combien »). Les deux sont utiles et ne disent pas la même chose ;
    # les mélanger est l'erreur de lecture classique sur ce type de tuile.
    #
    # Le seuil est 100 % du nominal, pas P0 : c'est la question « le produit
    # vaut-il plus que le pair », indépendante du prix d'entrée. La probabilité
    # correspondante vis-à-vis du prix payé reste p_above_p0.
    win, lose = pvs[pvs > 100], pvs[pvs < 100]
    nw, nl = int(win.size), int(lose.size)
    return {
        "mean": mean, "std": float(pvs.std(ddof=0)),
        "p01": q(0.01), "p05": q(0.05), "p25": q(0.25), "p50": q(0.50),
        "p75": q(0.75), "p95": q(0.95), "p99": q(0.99),
        "p_above_100": float((pvs > 100).mean() * 100),
        "p_above_p0":  float((pvs >= p0).mean() * 100),
        "e_mtm": mean,
        "e_upside": float(np.maximum(pvs - 100, 0).mean()),
        # None plutôt que 0 quand le sous-échantillon est vide : une moyenne de
        # rien n'est pas zéro, et un « gain moyen des gagnants : 0,00 % » affiché
        # alors qu'il n'y a aucun gagnant se lit comme une information.
        "n_win": nw, "n_lose": nl,
        "e_mtm_win":  float(win.mean()) if nw else None,
        "e_mtm_lose": float(lose.mean()) if nl else None,
        "avg_gain": float((win - 100).mean()) if nw else None,
        "avg_loss": float((100 - lose).mean()) if nl else None,   # magnitude, > 0
        "max_gain": float(win.max() - 100) if nw else None,
        "max_loss": float(100 - lose.min()) if nl else None,      # magnitude, > 0
        "mtm_min": float(pvs.min()), "mtm_max": float(pvs.max()),
    }


def _mtf_payment_args(script, event_map, maturity, payment, intervals, r, *, collect=False):
    """The same flat-rate payment convention for outer replay, inner PV and detail."""
    pay_map = {}
    for step, occurrences in event_map.items():
        dates = []
        for occurrence in occurrences:
            # _event_schedule emits single-date occurrences, preserving payment dates.
            observed = occurrence.dates[0]
            paid = occurrence.payment_dates[0] if occurrence.payment_dates else observed
            if payment is not None and abs(observed - maturity) < 1e-6:
                paid = payment
            if not math.isfinite(paid) or paid < observed - 1e-6:
                raise ValueError('Date de paiement invalide ou antérieure à la constatation.')
            dates.append(paid)
        pay_map[step] = dates
    final = payment if payment is not None else maturity
    if not math.isfinite(final) or final < maturity - 1e-6:
        raise ValueError('Le paiement final doit être à la maturité ou après.')
    return dict(pay_map=pay_map, pay_df={p: math.exp(-r*p) for row in pay_map.values() for p in row},
                mat_pay_t=final, mat_pay_df=math.exp(-r*final), flows_at_payment=collect)


@with_simulation_grid
def mtf_date_grid(script, maturity, n_dates, payment=None, dates=None):
    """Keep the legacy base grid and expose the final settlement tail when needed."""
    if dates is not None:
        grid = [float(d) for d in dates]
    else:
        grid = build_mtf_dates(maturity, n_dates)
        last = max([maturity, payment if payment is not None else maturity,
                    *[p for ev in script.events for p in (ev.payment_dates or [])]])
        if last > maturity + 1e-6:
            grid = sorted(set([*grid, maturity, (maturity+last)/2, last]))
    if (not grid or any(not math.isfinite(d) or d <= 0 for d in grid)
            or any(a >= b for a,b in zip(grid,grid[1:])) or len(grid) > 400):
        raise ValueError('Dates de valorisation positives, finies et strictement croissantes requises (400 maximum).')
    return grid


def _mtf_replay(script, paths, step, intervals, maturity, payment, r, user_params,
                underlyings, state=None, initial_flows=None):
    """Replay observations once; a STOP stops optionality, never its unpaid claims."""
    inherited = dict(state or {})
    inherited.pop('spot_mult', None)
    inherited.pop('spot_base', None)
    fix = inherited.pop('fix_state_init', None)
    matured = _time_at(intervals, step) >= maturity-1e-9
    event_map = _mtf_past_step_map(script, step, intervals, at_maturity=matured)
    observed, _, _, levels = _constater(script, paths[:step+1], step, len(underlyings), paths.shape[2],
                                       None, None, fix, event_map, dt=intervals)
    states, flows, labels, observations = [], [], [], []
    _eval_paths(script, observed, step, len(underlyings), paths.shape[2], intervals, r, user_params,
        event_map, [ev for ev in script.events if ev.type == 'AT_MATURITY'] if matured else [], {},
        record=False, state_out=states, flows_out=flows, flow_labels_out=labels,
        flow_observations_out=observations, lvl_map=levels,
        rank_map=_rangs_observation(event_map,intervals),
        **_mtf_payment_args(script,event_map,maturity,payment,intervals,r,collect=True),
        **inherited, reference_spots=_basket_references(underlyings))
    ledger = [[dict(observation_t=o, payment_t=p, amount=v, lbl=label)
               for (p,v),o,label in zip(row,obs,ls)] for row,obs,ls in zip(flows,observations,labels)]
    for row, dated in zip(ledger,flows):
        for original in initial_flows or []:
            row.append(dict(original))
            dated.append((original['payment_t'], original['amount']))
    alive = np.array([not s['done'] and not matured for s in states])
    return observed, states, flows, ledger, alive


def _mtf_claim_rows(ledger, mark, r):
    """Known unpaid cash flows are deterministic conditional on the outer history."""
    return [dict(t=f['payment_t']-mark, t_abs=f['payment_t'], observation_t=f['observation_t'],
                 payment_t=f['payment_t'], lbl=f['lbl'], status='ACQUIRED_UNPAID', proba=100.,
                 e_amount=f['amount']*100, amount_if_fires=f['amount']*100,
                 df=math.exp(-r*(f['payment_t']-mark)),
                 pv=f['amount']*100*math.exp(-r*(f['payment_t']-mark)))
            for f in ledger if f['payment_t'] > mark+1e-9 and f['amount'] != 0]


def _mtf_known_only_row(flows,mark,r,n_outer,main_price):
    claims = _mtf_claim_rows(flows,mark,r)
    pv = sum(f['pv'] for f in claims)
    values = np.full(n_outer,pv)
    pending = bool(claims)
    return dict(t=mark,pvs=values.tolist(),pvs_alive=[],alive=[False]*n_outer,n_alive=0,
        outstanding=[pending]*n_outer,pending_settlement=[pending]*n_outer,
        n_outstanding=n_outer if pending else 0,n_pending_settlement=n_outer if pending else 0,
        n_settled=0 if pending else n_outer,terminated_pct=100.,n_outer=n_outer,
        pending_pvs=values.tolist(),pvs_outstanding=values.tolist() if pending else [],
        stats_all=_mtf_date_stats(values,main_price),
        stats_outstanding=_mtf_date_stats(values,main_price) if pending else None,
        stats=None,thin=True,thin_all=n_outer<MTF_MIN_ALIVE,
        thin_outstanding=n_outer<MTF_MIN_ALIVE or not pending,
        realized_flows=[[(f['payment_t'],f['amount']) for f in flows] for _ in range(n_outer)],
        settled_flows=[[f for f in flows if f['payment_t'] <= mark+1e-9] for _ in range(n_outer)],
        unsettled_flows=[claims for _ in range(n_outer)])


@with_simulation_grid
def run_mark_to_future(script: CompiledScript,
                        underlyings,
                        corr_matrix,
                        r: float,
                        T_max: float,
                        main_price: float,
                        model: str = "constant",
                        n_outer: int = 200,
                        n_inner: int = 500,
                        n_dates: int = 5,
                        seed: int = 42,
                        user_params=None,
                        barrier_monitoring: str = "weekly",
                        # Etat d'un produit deja en cours de vie. Le Mark-to-
                        # Future compose deux histoires : celle deja realisee,
                        # partagee par tous les scenarios, et celle que chaque
                        # scenario exterieur ecrit ensuite. La premiere amorce
                        # le rejeu, la seconde s'y ajoute.
                        state: dict | None = None,
                        mtm_dates: list[float] | None = None,
                        yield_curve=None,
                        sigma_r: float = 0.0,
                        outer_paths: np.ndarray | None = None,
                        outer_times: list[float] | None = None,
                        credit_exposure: bool = False,
                        maturity_payment_t: float | None = None,
                        progress=None, initial_flows=None, initial_terminated=False,
                        aligned_grid=False, gbm_atm_curve=False, lsv_leverage=None, local_vol_anchor=None) -> dict:
    """Run the full nested Monte Carlo Mark-to-Future analysis (see module section
    docstring above). main_price is the t=0 fair price (% of notional); it is only
    used as the threshold for the P(MTM >= P0) diagnostic.

    Inner simulation is processed in chunks of outer scenarios (MTF_MAX_BATCH paths
    at a time) to bound peak memory regardless of how large n_outer * n_inner gets.

    yield_curve / sigma_r are accepted only to be REFUSED: this analysis is
    flat-rate throughout (outer drift, inner drift and discounting all read the
    scalar r). They are in the signature because every caller builds one request
    body for every analytic and would otherwise drop them silently — the price
    would carry the curve and the whole fan would not, including the P0 threshold
    the fan is compared against."""
    _mtf_reject_unsupported(model, barrier_monitoring, yield_curve, sigma_r,
                            underlyings, aligned_grid=aligned_grid)
    if aligned_grid:
        validate_model(model, underlyings)
        if outer_paths is not None or outer_times is not None:
            raise ValueError("La grille du Pricer exige ses propres scénarios extérieurs.")
    t_run0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    # `mtm_dates` lets a caller ask for the exact dates it needs instead of the
    # evenly-spaced grid. The PRIIPs intermediate horizons use it: they need
    # the value at 1 year and at RHP/2 specifically, and that value is what
    # this function already computes correctly for a recallable product.
    mtm_dates = mtf_date_grid(script,T_max,n_dates,maturity_payment_t,mtm_dates)
    if initial_terminated:
        return dict(main_price=main_price,n_outer=n_outer,n_inner=n_inner,n_dates=len(mtm_dates),
            mtm_dates=mtm_dates,settlement_convention='AFTER_PAYMENTS_DUE_ON_MARK_DATE',
            terminated_at_origin=True,elapsed_ms=(time.perf_counter()-t_run0)*1000,
            results=[_mtf_known_only_row(initial_flows or [],t,r,n_outer,main_price) for t in mtm_dates])
    outer_horizon = max(T_max, mtm_dates[-1])
    budget_steps, _ = mtf_simulation_axis(script, T_max, mtm_dates, aligned_grid)
    if outer_times is not None:
        budget_steps = max(budget_steps, len(outer_times)-1)
    _peak_paths = max(n_outer, min(MTF_MAX_BATCH, n_outer * n_inner))
    repriced_dates = (sum(t < T_max - 1e-9 for t in mtm_dates) if aligned_grid else len(mtm_dates))
    _total_paths = n_outer + n_outer * n_inner * repriced_dates
    ensure_budget(
        estimate_mc_batch(
            operation="mark_to_future",
            simulation_steps=budget_steps,
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
    # A nonpositive mark has no past interval to replay: the replay would
    # then index an empty path tensor and die on `WOF_min[-1]` with an IndexError
    # about axis 0 having size 0 — a stack trace no caller can act on.
    too_early = [d for d in mtm_dates if not math.isfinite(d) or d <= 0]
    if too_early:
        raise ValueError(
            f"Date(s) de valorisation trop proche(s) de t=0 : {too_early} — le "
            f"moteur exige une date finie strictement positive."
        )

    _state = dict(state or {})
    _spot0 = _state.pop("spot_mult", None)
    _state.pop("spot_base", None)
    # La part de fenêtre de départ déjà constatée dans l'historique d'un produit
    # vivant va à la CONSTATATION, pas à l'évaluateur : transmise telle quelle au
    # rejeu extérieur, elle faisait tomber tout Mark-to-Future en cours de vie.
    fix_hist = _state.pop("fix_state_init", None)
    outer_horizon = max(T_max, mtm_dates[-1])
    if outer_times is None:
        # Maturity is contractual even when the requested marks omit it.
        # Replay must execute its payoff before carrying the settlement claim.
        outer_ts, outer_dt = mtf_simulation_axis(script, T_max, mtm_dates, aligned_grid)
        outer_dt = _durations(outer_dt, outer_ts)
    else:
        outer_dt = np.diff(outer_times)
        outer_ts = len(outer_dt)
        for d in [T_max, *mtm_dates, *[d for ev in script.events for d in ev.dates if d <= outer_horizon]]:
            if abs(_time_at(outer_dt, _step_at(outer_dt, d))-d) > 1e-8:
                raise ValueError("Scénarios extérieurs sans date contractuelle exacte.")
    step_vols = _atm_step_vols(underlyings, outer_dt, outer_ts) if gbm_atm_curve else None
    local_vol_wings = []
    if outer_paths is None:
        S_outer, factors, local_grid = _mtf_outer_state(
            model, underlyings, corr_matrix, r, mtm_dates, n_outer, seed, _spot0, outer_dt, step_vols,
            wing_diagnostics=local_vol_wings, lsv_leverage=lsv_leverage, local_vol_anchor=local_vol_anchor)
    else:
        S_outer, factors, local_grid = outer_paths, None, None
    if S_outer.shape != (outer_ts+1, n, n_outer):
        raise ValueError("Dimensions des scénarios extérieurs incohérentes")

    L = cholesky(corr_matrix, n)
    outer_per_chunk = max(1, MTF_MAX_BATCH // n_inner)

    results = []
    for k, t0 in enumerate(mtm_dates):
        if progress:
            progress(k, len(mtm_dates))
        step_k = _step_at(outer_dt, min(t0, T_max))
        past_dt = outer_dt[:step_k]
        matured = t0 >= T_max-1e-9
        spot_k = S_outer[step_k]
        _S_past, outer_states, outer_flows, ledger, alive = _mtf_replay(
            script,S_outer,step_k,past_dt,T_max,maturity_payment_t,r,user_params,
            underlyings,state,initial_flows)
        claim_rows = [_mtf_claim_rows(row,t0,r) for row in ledger]
        pending_pvs = np.array([sum(f['pv'] for f in row) for row in claim_rows])
        pending = np.array([bool(row) for row in claim_rows])
        wof_min_k = np.array([st["wof_min"] for st in outer_states])
        bof_max_k = np.array([st["bof_max"] for st in outer_states])
        wof_max_k = np.array([st.get("wof_max", 1.0) for st in outer_states])
        index_k = np.array([st["index"] for st in outer_states], dtype=np.int64)
        accum_k = np.array([st["accum"] for st in outer_states], dtype=float)
        memo_k = [st["memo"] for st in outer_states]
        s_min_k = np.asarray([st["s_min"] for st in outer_states], dtype=float).T   # (n, N_outer)
        s_max_k = np.asarray([st["s_max"] for st in outer_states], dtype=float).T
        s_prev_k = np.asarray([st["s_prev"] for st in outer_states], dtype=float).T
        rv_sumsq_k = np.array([st["realvol_sumsq"] for st in outer_states])
        rv_t_k = np.array([st["realvol_t"] for st in outer_states])
        # Le worst-of à la date de marque, dans les unités des chemins intérieurs :
        # contre S0, et 1,0 tant que la fenêtre de départ n'est pas close — les
        # chemins y sont rebasés puis aplatis. Pris sur le spot brut, il faisait
        # partir la vol réalisée intérieure d'un rendement fantôme de -log(S0).
        wof0_k = _S_past[step_k].min(axis=0)    # (N_outer,)

        if matured:
            scenario_pvs = np.zeros(n_outer)
        else:
            # has_stop and the fixing window used to be dropped when rebuilding the
            # residual script, which silently lost its early-redemption flag and its
            # STRIKE_FIX dates. Both now live in _mtf_residual_script, alongside the
            # snapped-step past/future split — a fixing date already averaged into
            # fix_state_k below must not also be re-simulated, or it counts twice.
            # La fenêtre de départ : la part de l'historique d'un produit vivant, puis
            # celle que chaque scénario extérieur a constatée jusqu'au mark.
            fix_state_k = _fusionner_realise(
                fix_hist, _mtf_realized_fix(script, S_outer, step_k, outer_dt)[0])
            # Et les fenêtres de constatation à cheval sur la date de marque, dont le
            # résiduel ne simule que les relevés à venir.
            releves_k = _mtf_releves_realises(script, _S_past, step_k, outer_dt)
            residual_script, step_map, mat_events, ts_eff, dt = _exact_mtf_residual(
                script, t0, T_max, outer_dt[step_k:] if aligned_grid else None)
            dt = _durations(dt, ts_eff)
            final_pay = (maturity_payment_t if maturity_payment_t is not None else T_max)-t0
            credit_inner_args = _mtf_payment_args(residual_script,step_map,T_max-t0,final_pay,dt,r)

            scenario_pvs = np.empty(n_outer, dtype=np.float64)

            # Chunked inner MC: bounds memory while still batching many outer scenarios
            # into one vectorized simulate() call per chunk.
            for start in range(0, n_outer, outer_per_chunk):
                end = min(n_outer, start + outer_per_chunk)
                n_chunk = end - start
                N_chunk = n_chunk * n_inner

                sl = slice(start, end)
                S_in = _mtf_inner_paths(model, underlyings, r, L, dt, n_inner, seed, k,
                                       start, end, spot_k, factors, local_grid, step_k, step_vols)

                # Chaque scenario exterieur arrive au mark avec SA part de fenetre
                # de depart deja fixee, et SES releves deja constates des fenetres a
                # cheval : les reductions se combinent par scenario, d'ou ces parts
                # decoupees et repetees comme tous les autres etats.
                S_in, _, _, lvl_in = _constater(
                    residual_script, S_in, ts_eff, n, N_chunk, None, None,
                    _tranche_realise(fix_state_k, sl, n_inner),
                    step_map,
                    {cle: _tranche_realise(etat, sl, n_inner)
                     for cle, etat in releves_k.items()}, dt=dt)
                payoffs, _ = _eval_paths(
                    residual_script, S_in, ts_eff, n, N_chunk, dt, r, user_params,
                    step_map, mat_events, {}, record=False,
                    wof_min_init=np.repeat(wof_min_k[sl], n_inner),
                    bof_max_init=np.repeat(bof_max_k[sl], n_inner),
                    wof_max_init=np.repeat(wof_max_k[sl], n_inner),
                    index_offset=np.repeat(index_k[sl], n_inner),
                    memo_init=[memo_k[i] for i in range(start, end) for _ in range(n_inner)],
                    accum_init=np.repeat(accum_k[sl], n_inner),
                    s_min_init=np.repeat(s_min_k[:, sl], n_inner, axis=1),
                    s_max_init=np.repeat(s_max_k[:, sl], n_inner, axis=1),
                    s_prev_init=np.repeat(s_prev_k[:, sl], n_inner, axis=1),
                    wof0_init=np.repeat(wof0_k[sl], n_inner),
                    realvol_state_init={"sumsq": np.repeat(rv_sumsq_k[sl], n_inner),
                                        "t": np.repeat(rv_t_k[sl], n_inner)},
                    lvl_map=lvl_in,
                    rank_map=_rangs_observation(step_map, dt),
                    **credit_inner_args,
                 reference_spots=_basket_references(underlyings))

                # Each outer scenario's MTF value = mean of its N_inner inner PVs (% notional).
                scenario_pvs[start:end] = np.array(payoffs).reshape(n_chunk, n_inner).mean(axis=1) * 100

        scenario_pvs = np.where(alive,scenario_pvs,0.) + pending_pvs
        outstanding = alive | pending
        outstanding_pvs = scenario_pvs[outstanding]
        alive_pvs = scenario_pvs[alive]
        n_alive = int(alive.sum())

        results.append({
            "t": t0,
            # Economic mark in every original scenario, including unpaid claims.
            # Legacy `stats`/`alive` describe optionality; new views use explicit
            # stats_all/stats_outstanding and their matching population masks.
            "pvs": [round(float(v), 4) for v in scenario_pvs],
            "pvs_alive": [round(float(v), 4) for v in alive_pvs],
            "terminated_pct": round(float((~alive).mean() * 100), 2),
            "n_alive": n_alive,
            "n_outer": int(n_outer),
            "outstanding": outstanding.tolist(), "pending_settlement": ((~alive)&pending).tolist(),
            "n_outstanding": int(outstanding.sum()), "n_pending_settlement": int(((~alive)&pending).sum()),
            "n_settled": int((~outstanding).sum()), "pending_pvs": pending_pvs.tolist(),
            "pvs_outstanding": outstanding_pvs.tolist(),
            "stats_all": _mtf_date_stats(scenario_pvs, main_price),
            "stats_outstanding": _mtf_date_stats(outstanding_pvs,main_price) if outstanding.any() else None,
            "thin_all": n_outer < MTF_MIN_ALIVE, "thin_outstanding": int(outstanding.sum()) < MTF_MIN_ALIVE,
            "settled_flows": [[f for f in row if f['payment_t'] <= t0+1e-9] for row in ledger],
            "unsettled_flows": claim_rows,

            # Fixed flows with payment dates, including future payments. KID/CCR
            # keep this contract; the UI uses settled_flows/unsettled_flows.
            "realized_flows": outer_flows,
            "alive": [bool(a) for a in alive],
            # Conditional on survival. None only when nothing survives at all —
            # there is then no distribution to describe. `thin` marks the case
            # where a percentile rests on too few contracts to mean much; the
            # display refuses to plot it, but the engine still returns the
            # number rather than surprising a caller who asked for a small run.
            "thin": n_alive < MTF_MIN_ALIVE,
            "stats": (_mtf_date_stats(alive_pvs, main_price)
                      if n_alive > 0 else None),
        })

    if progress:
        progress(len(mtm_dates), len(mtm_dates))
    return {
        "main_price": round(main_price, 4),
        "steps_per_year": grid_frequency(),
        "n_outer": n_outer,
        "n_inner": n_inner,
        "n_dates": len(mtm_dates), "mtm_dates": mtm_dates,
        "settlement_convention": "AFTER_PAYMENTS_DUE_ON_MARK_DATE",
        "results": results,
        **({"local_vol_wings": local_vol_wings} if local_vol_wings else {}),
        "elapsed_ms": round((time.perf_counter() - t_run0) * 1000, 1),
    }
