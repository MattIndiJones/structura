"""PayScript evaluation on simulated paths: observation windows, initial
level, running state and the per-path interpreter.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
from typing import NamedTuple
from .bindings import effective_parameters
from .parser import CompiledScript
from .time_grid import step_at as _step_at, times as _times
from .mc_axis import SY, _event_times


# ── PayScript evaluation ────────────────────────────────────────────

def _strike_fix_steps(script: CompiledScript, ts_n: int,
                      dt: float = 1.0 / SY) -> list[int]:
    """Steps of the starting window — the dates that fix S0.
    run_payoff_profile needs the LAST of them to know where to stop sweeping the
    neutral level, and _apply_delayed_bump needs it to know where a Greeks bump
    may start biting; both must quantise exactly like the reduction itself, or a
    short window desyncs them and the sweep-cancels-fixing bug comes back."""
    return _window_steps(script.strike_fix_dates, ts_n, dt)


def _window_steps(dates, ts: int, dt: float = 1.0 / SY) -> list[int]:
    """Year-fractions of a constatation window -> distinct grid steps.

    Production grids contain each contractual date. Distinct dates therefore
    retain distinct weights; scalar grids remain supported for direct helper
    clients using a deliberately synthetic clock.

    Step 0 is a real row of S (t=0, the diffusion origin). The former floor at
    step 1 dated from the weekly grid, where a short window collapsed onto
    step 0; on exact contract dates it only folded a fixing ON the strike date
    into the next one, and the duplicate was dropped: a 10-day averaging-in
    kept 9 closes."""
    if not dates:
        return []
    return sorted({min(max(_step_at(dt, d), 0), ts) for d in dates})


def _reduce_window(S: np.ndarray, steps: list[int], reduction: str) -> np.ndarray:
    """Reduce a window to one level PER UNDERLYING, per path: (n, N).

    This is the whole point of the design. `min` and `mean` do not commute, so
    reducing the aggregate (the worst-of of the day) instead of each underlying
    separately gives a systematically different — and wrong — level: on a
    2-asset worst-of with a 3-month averaging window the call came out 60 to
    122 bps too dear and the put as much too cheap, because
    mean(min) <= min(mean) always. Every underlying is reduced over its own
    window; only then do WOF/BOF/BASKET aggregate.
    See CONSTATATIONS_PERIODE_DESIGN.md §1.

    `steps` indexe S DIRECTEMENT : S a ts+1 rangées, S[0] étant t=0, si bien
    que le pas k est la rangée k. L'ancienne réduction travaillait sur WOF, qui
    part du pas 1 et se lit donc en k-1 ; reprendre ce décalage ici faisait lire
    toute fenêtre une semaine trop tôt — assez pour qu'une fenêtre d'un seul
    point cesse de reproduire la constatation ponctuelle qu'elle est."""
    w = S[steps, :, :]                         # (len(steps), n, N)
    if reduction == "MIN":
        return w.min(axis=0)
    if reduction == "MAX":
        return w.max(axis=0)
    if reduction == "AVG":
        return w.mean(axis=0)
    raise ValueError(
        f"Réduction de constatation inconnue : {reduction!r} — "
        f"valeurs admises : MIN, MAX, AVG.")


def _combine_reduction(window: np.ndarray | None, reduction: str,
                        state: dict | None, n: int, N: int) -> np.ndarray:
    """Fold an already-realized part of a window into the simulated part.

    `state` ({"n", "sum", "min", "max"}, each per-asset — (n,) shared by every
    path for a single deal's residual MtM, (n, N) for Mark-to-Future where each
    outer scenario fixed its own level) comes from replaying the fixing dates
    already behind us on real closes. MIN/MAX combine by min/max; AVG is
    count-weighted so a past and a future fixing date each carry exactly one
    observation's weight. The residual script must then hold ONLY the still-
    future dates, or the past would be counted twice."""
    def _row(v) -> np.ndarray:
        return np.broadcast_to(np.asarray(v, dtype=float).reshape(n, -1),
                               (n, N)).astype(float, copy=True)

    if state is None:
        if window is None:
            return np.ones((n, N))
        return window
    p_n = state["n"]
    if window is None:          # window fully realized — nothing left to combine
        if reduction == "MIN":
            return _row(state["min"])
        if reduction == "MAX":
            return _row(state["max"])
        return _row(np.asarray(state["sum"], dtype=float) / p_n)
    if reduction == "MIN":
        return np.minimum(window, _row(state["min"]))
    if reduction == "MAX":
        return np.maximum(window, _row(state["max"]))
    n_fut = state.get("n_future", 1)
    return (window * n_fut + _row(state["sum"])) / (n_fut + p_n)


def cle_de_fenetre(calendrier: str | None, rang: int | None) -> str:
    """L'identifiant d'une fenêtre de constatation : son calendrier et son rang.
    `AT OBS:` et `AT OBS.last:` visent la même constatation à la dernière date,
    donc la même fenêtre — et la même part déjà constatée."""
    return f"{calendrier}#{rang}"


def _fusionner_realise(a: dict | None, b: dict | None) -> dict | None:
    """Deux parts déjà constatées d'une même fenêtre, en une seule.

    En Mark-to-Future sur un produit vivant, une fenêtre a pu commencer dans
    l'historique — une part commune à tous les scénarios, par sous-jacent (n,) —
    puis continuer sur chaque scénario extérieur jusqu'à la date de marque — une
    part par scénario (n, N). Les deux ne se recouvrent pas : la date de
    valorisation les sépare."""
    if not a:
        return b
    if not b:
        return a

    def _col(v) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        return v.reshape(v.shape[0], -1)

    return {"n": a["n"] + b["n"],
            "sum": _col(a["sum"]) + _col(b["sum"]),
            "min": np.minimum(_col(a["min"]), _col(b["min"])),
            "max": np.maximum(_col(a["max"]), _col(b["max"]))}


def _niveau_initial(script: CompiledScript, S: np.ndarray, ts: int, n: int,
                     N: int, fix_state_init: dict | None,
                     dt: float = 1.0 / SY) -> np.ndarray | None:
    """S0_i — the initial level each underlying is measured against, (n, N).

    None when the product has no starting window: S0 is then the strike-date
    close, the tensor is already expressed against it, and nothing is rescaled.
    """
    if not script.strike_fix_reduction:
        return None
    steps = _window_steps(script.strike_fix_dates, ts, dt)
    window = _reduce_window(S, steps, script.strike_fix_reduction) if steps else None
    if window is None and fix_state_init is None:
        return None
    state = dict(fix_state_init) if fix_state_init else None
    if state is not None and steps:
        state["n_future"] = len(steps)
    return _combine_reduction(window, script.strike_fix_reduction, state, n, N)


def _rebaser_sur_le_niveau_initial(S: np.ndarray, ref: np.ndarray, end_step: int,
                                    bridge_min=None, bridge_max=None) -> tuple:
    """Express the whole tensor as a percentage of S0_i, one reference per
    underlying AND per path, then flatten everything up to the end of the
    starting window.

    The flattening is what makes an American observation impossible before S0
    exists — Philippe's own ruling, and the only coherent one: with no initial
    level there is nothing for a barrier to be a percentage OF. Running extrema
    and the Brownian bridge would otherwise book excursions that have no
    contractual existence. It is the same operation
    _fixer_le_strike_sur_les_trajectoires performs for a forward start, which
    is the degenerate one-point case of this window."""
    S = S / ref[None, :, :]
    if end_step:
        S[:end_step + 1] = 1.0
    if bridge_min is not None:
        bridge_min = bridge_min / ref[None, :, :]
        bridge_max = bridge_max / ref[None, :, :]
        # Index j du pont = pas j+1 : les pas 1..k sont les indices 0..k-1.
        if end_step:
            bridge_min[:end_step] = 1.0
            bridge_max[:end_step] = 1.0
    return S, bridge_min, bridge_max


def _constater(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                bridge_min, bridge_max, fix_state_init: dict | None,
                step_map: dict, releves_realises: dict | None = None,
                dt: float = 1.0 / SY) -> tuple:
    """Toute la chaîne de constatation d'un jeu de trajectoires.

    1. réduire la fenêtre de départ en S0_i, par sous-jacent ;
    2. réexprimer le tenseur (et les ponts) en pourcentage de ce niveau, puis
       aplatir ce qui précède — sans S0, rien n'est observable ;
    3. produire le niveau constaté de chaque événement à fenêtre.

    Rendu comme un tout parce que les deux jambes — base et antithétique — et
    les autres analyses (chemins, probabilités, Mark-to-Future) doivent
    appliquer exactement la même suite, dans le même ordre. C'est la divergence
    entre deux chemins d'évaluation qui avait déjà fait analyser un produit
    neuf alors qu'il était en cours de vie."""
    ref = _niveau_initial(script, S, ts, n, N, fix_state_init, dt)
    if ref is not None:
        steps = _strike_fix_steps(script, ts, dt)
        S, bridge_min, bridge_max = _rebaser_sur_le_niveau_initial(
            S, ref, max(steps) if steps else 0, bridge_min, bridge_max)
    levels = _niveaux_constates(script, S, ts, step_map, releves_realises, dt)
    if ref is not None:
        levels['__initial_ratio'] = ref
    return S, bridge_min, bridge_max, levels


def _rangs_observation(step_map: dict, dt: float = 1.0 / SY) -> dict:
    """Rang que chaque événement lit sous le nom `INDEX`, aligné index par index
    sur `step_map` — même patron que `pay_map` et les niveaux constatés.

    Le rang vient de la DATE, pas d'un compteur : chaque bloc lit sa position
    dans l'échéancier qu'il nomme. Deux calendriers ne s'additionnent donc plus
    (c'était 2/4/6 au lieu de 1/2/3), un bloc posé sur une sous-date ne décale
    plus les constatations (1/3/4), et rien n'est à réamorcer en vie résiduelle
    puisque la troisième date porte 3 où qu'on la price.

    None à une entrée : l'événement n'a pas de rang — un script qui y lit
    `INDEX` est refusé à la compilation, jamais servi par un nombre inventé."""
    out: dict[int, list] = {}
    for step, evs in step_map.items():
        rangs = []
        for ev in evs:
            k = next((j for j, d in enumerate(ev.dates)
                      if max(1, _step_at(dt, d)) == step), None)
            rangs.append(ev.ranks[k] if ev.ranks and k is not None
                         and k < len(ev.ranks) else None)
        out[step] = rangs
    return out


def _niveaux_constates(script: CompiledScript, S: np.ndarray, ts: int,
                        step_map: dict, releves_realises: dict | None = None,
                        dt: float = 1.0 / SY) -> dict:
    """Niveau constaté de chaque ÉVÉNEMENT, aligné index par index sur
    `step_map` — exactement comme `pay_map` l'est déjà.

    Porté par l'événement et non par le pas de temps, parce que deux blocs `AT`
    peuvent tomber le même jour et lire deux choses différentes : un coupon sur
    la moyenne de la période, une protection sur le cours de clôture. Les
    attacher au pas obligeait à en refuser un des deux, alors que le produit
    est parfaitement ordinaire.

    `None` à une entrée veut dire « le cours du jour » — le cas de l'écrasante
    majorité des événements, et celui qui ne coûte rien. Seules les entrées à
    fenêtre matérialisent un tableau (n, N), et il y en a une poignée : on ne
    recopie jamais le tenseur entier.

    Une fenêtre À CHEVAL sur l'origine d'un script résiduel n'a plus dans
    `window_dates` que ses relevés à venir ; les autres ont été constatés — sur
    l'historique, ou sur le scénario extérieur d'un Mark-to-Future — et leur
    réduction arrive par `releves_realises` (à défaut, celle que le script
    porte). Les deux parts se combinent comme pour la fenêtre de départ : par
    min/max, ou en moyenne pondérée par le nombre de relevés. Une fenêtre dont
    la part réalisée manque est refusée : réduite sur ses seuls relevés à
    venir, elle rendrait une moyenne partielle présentée comme la moyenne."""
    realises = (releves_realises if releves_realises is not None
                else getattr(script, "releves_realises", None)) or {}
    n, N = S.shape[1], S.shape[2]
    lvl: dict[int, list] = {step: [None] * len(evs) for step, evs in step_map.items()}
    cache: dict[tuple, np.ndarray] = {}
    for step, evs in step_map.items():
        for i, ev in enumerate(evs):
            if not ev.reduction or not ev.window_dates:
                continue
            # Quelle occurrence de CET événement tombe à CE pas ? Un même bloc
            # `AT Nom:` porte toutes les dates du calendrier, chacune avec sa
            # fenêtre — il faut retrouver la bonne.
            k = next((j for j, d in enumerate(ev.dates)
                      if max(1, _step_at(dt, d)) == step), None)
            if k is None or k >= len(ev.window_dates):
                continue
            w = tuple(_window_steps(ev.window_dates[k], ts, dt))
            passes = (ev.releves_passes[k] if ev.releves_passes
                      and k < len(ev.releves_passes) else 0)
            cle = None
            if passes:
                cle = cle_de_fenetre(ev.constat_ref,
                                     ev.ranks[k] if ev.ranks and k < len(ev.ranks) else None)
                if cle not in realises:
                    raise ValueError(
                        f"Constatation {cle} : {passes} relevé(s) de sa fenêtre sont "
                        f"déjà constatés, mais leurs cours ne sont pas transmis. La "
                        f"réduire sur ses seuls relevés à venir rendrait une moyenne "
                        f"partielle présentée comme la moyenne.")
            if not w and cle is None:
                continue
            key = (ev.reduction, w, cle)
            if key not in cache:
                fenetre = _reduce_window(S, list(w), ev.reduction) if w else None
                if cle is None:
                    cache[key] = fenetre
                else:
                    etat = dict(realises[cle])
                    etat["n_future"] = len(w)
                    cache[key] = _combine_reduction(fenetre, ev.reduction, etat, n, N)
            lvl[step][i] = cache[key]
    return lvl


def _state_by_asset(v, n: int, N: int) -> np.ndarray:
    """Realized per-asset state, shared by every path (n,) or one per path (n, N)."""
    a = np.asarray(v, dtype=float)
    return a.reshape(1, n, 1) if a.ndim == 1 else a.reshape(1, n, N)


class _RunningState(NamedTuple):
    """Les tenseurs d'etat d'un jeu de trajectoires, historique realise inclus.

    Factorise parce que les DEUX evaluateurs en ont besoin et qu'ils l'avaient
    diverge : `_eval_paths` savait heriter d'un passe realise, `_eval_paths_
    detailed` non. Consequence, l'onglet Probabilites analysait le produit NEUF
    meme sur une note deja en cours de vie — 39 % de chance de rappel et 2,12
    ans de duree esperee pour une vie restante de 1,10 an.

    Chaque *_init accepte soit UNE valeur partagee par tous les chemins (le MtM
    residuel d'un deal), soit une valeur PAR chemin (le Mark-to-Future, ou
    chaque scenario exterieur arrive a la date de marque avec sa propre
    histoire contractuelle).
    """
    WOF: np.ndarray
    BOF: np.ndarray
    WOF_min: np.ndarray
    BOF_max: np.ndarray
    S_min: np.ndarray
    S_max: np.ndarray
    cum_sq_ret: np.ndarray
    rv_sumsq0: object
    rv_t0: object
    # Plus haut courant du worst-of (WOF_MAX) : le max dans le temps du min
    # entre actifs, qui ne se deduit ni de S_MAX ni de BOF_MAX.
    WOF_max: np.ndarray | None = None


def _fixer_le_strike_sur_les_trajectoires(S: np.ndarray, k: int, bridge_min=None,
                                          bridge_max=None) -> tuple:
    """Le niveau initial n'est pas connu : chaque trajectoire porte le sien.

    Jusqu'au pas `k` on diffuse depuis le spot du jour ; c'est là que le fixing
    est constaté, et il vaut ce que CETTE trajectoire a atteint. On ramène donc
    tout le tenseur en pourcentage de ce niveau-là, une référence par chemin :
    le payoff, écrit en pourcentage du strike, se lit ensuite sans rien savoir
    de tout cela.

    L'opération vient APRÈS la simulation, jamais pendant. Les vols locales ont
    déjà été lues aux vrais niveaux — c'est ce qui laisse subsister le delta de
    smile, seul canal par lequel un forward-start en a un. Normaliser avant
    aurait fait voyager toutes les trajectoires dans la même région de la nappe
    et l'aurait effacé.

    Le segment antérieur au fixing est ensuite aplati à 1,0. Le contrat ne
    regarde rien avant sa constatation initiale : sans cet aplatissement, les
    extrema courants et le pont brownien compteraient des excursions qui n'ont
    aucune existence contractuelle — une barrière franchie avant que le produit
    existe."""
    if not k:
        return S, bridge_min, bridge_max
    ref = S[k, :, :].copy()              # (n, N) — une référence par chemin
    S = S / ref[None, :, :]
    S[:k + 1] = 1.0
    if bridge_min is not None:
        bridge_min = bridge_min / ref[None, :, :]
        bridge_max = bridge_max / ref[None, :, :]
        # Index j du pont = pas j+1 : les pas 1..k sont les indices 0..k-1.
        bridge_min[:k] = 1.0
        bridge_max[:k] = 1.0
    return S, bridge_min, bridge_max


def _running_state(script, S, n: int, N: int, bridge_min, bridge_max,
                   wof_min_init=None, bof_max_init=None,
                   s_min_init=None, s_max_init=None, wof0_init=None,
                   realvol_state_init=None, wof_max_init=None) -> _RunningState:
    """Extrema courants et variance realisee cumulee.

    Tout se lit ici sur la TRAJECTOIRE, jamais sur les niveaux constates : une
    barriere americaine regarde des cours et non des moyennes, et une vol
    realisee calculee sur une serie lissee sortirait artificiellement basse.
    Les niveaux constates, eux, sont poses evenement par evenement — voir
    _niveaux_constates."""
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    WOF_path = WOF
    WOF_min = np.minimum.accumulate(
        bridge_min.min(axis=1) if bridge_min is not None else WOF_path, axis=0)
    BOF_max = np.maximum.accumulate(
        bridge_max.max(axis=1) if bridge_max is not None else S[1:].max(axis=1), axis=0)
    if wof_min_init is not None:
        WOF_min = np.minimum(WOF_min, wof_min_init)
    if bof_max_init is not None:
        BOF_max = np.maximum(BOF_max, bof_max_init)
    # Le pont brownien donne un extremum PAR actif : le plus haut du worst-of
    # n'en est l'exact qu'en mono sous-jacent. En panier, il se lit sur la
    # grille, ce que dit la note de monitoring.
    WOF_max = np.maximum.accumulate(
        bridge_max[:, 0, :] if bridge_max is not None and n == 1 else WOF_path, axis=0)
    if wof_max_init is not None:
        WOF_max = np.maximum(WOF_max, wof_max_init)

    # Min/max par actif (S_MIN[i]/S_MAX[i]) — distincts de WOF_min/BOF_max qui
    # sont au niveau du panier. Puis vol realisee de l'indice WOF, annualisee
    # depuis les log-rendements hebdomadaires accumules depuis l'emission.
    S_min = np.minimum.accumulate(bridge_min if bridge_min is not None else S[1:], axis=0)
    S_max = np.maximum.accumulate(bridge_max if bridge_max is not None else S[1:], axis=0)
    if s_min_init is not None:
        S_min = np.minimum(S_min, _state_by_asset(s_min_init, n, N))
    if s_max_init is not None:
        S_max = np.maximum(S_max, _state_by_asset(s_max_init, n, N))
    if wof0_init is None:
        wof0_row = np.full((1, N), 1.0)
    else:
        wof0_row = np.asarray(wof0_init, dtype=float).reshape(1, -1) * np.ones((1, N))
    # REALVOL suit le CHEMIN, pas les niveaux constates : une fenetre de
    # moyennage lisse la serie et rendrait une vol realisee artificiellement
    # basse, alors que le sous-jacent a bel et bien bouge.
    WOF_full = np.vstack([wof0_row, WOF_path])
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)
    return _RunningState(
        WOF, BOF, WOF_min, BOF_max, S_min, S_max, cum_sq_ret,
        realvol_state_init["sumsq"] if realvol_state_init else 0.0,
        realvol_state_init["t"] if realvol_state_init else 0.0,
        WOF_max,
    )


def _basket_references(underlyings):
    values = [u.get("spot0") for u in underlyings]
    return values if values and all(v is not None for v in values) else None


def _path_references(values, levels, path):
    if values is None:
        return None
    references = np.asarray(values, dtype=float)
    references = references[:, path] if references.ndim == 2 else references
    ratio = (levels or {}).get('__initial_ratio')
    if ratio is not None:
        references = references * ratio[:, path]
    return references.tolist()


def _eval_paths(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                dt: float, r_eff: float, user_params: dict,
                step_map: dict, mat_events: list, flux_map: dict,
                record: bool, df_arr: np.ndarray | None = None,
                # Settlement of each flow. pay_map holds the payment time of
                # every step_map entry, aligned index by index with it; pay_df
                # the discount factor of each distinct payment time; mat_pay_*
                # the product's own final payment date. All None means "paid at
                # observation" — every caller with no settlement calendar.
                pay_map: dict | None = None,
                pay_df: dict | None = None,
                mat_pay_df=None,
                mat_pay_t: float | None = None,
                # The PV is expressed at the value date, while the time axis is
                # anchored on the strike: 1 / P(0, value date). 1.0 when the two
                # coincide, which is every caller that knows only one date.
                pv_rebase: float = 1.0,
                wof_min_init=None, bof_max_init=None,
                stop_times_out: list | None = None,
                flows_out: list | None = None,
                bridge_min=None, bridge_max=None,
                index_offset: int = 0, memo_init: dict | None = None,
                accum_init: float = 0.0,
                s_min_init=None, s_max_init=None, s_prev_init=None,
                wof0_init: float | None = None,
                realvol_state_init: dict | None = None,
                lvl_map: dict | None = None,
                rank_map: dict | None = None,
                # Pas de grille où le produit COMMENCE. Non nul seulement quand
                # la constatation initiale est encore à venir : le tenseur
                # démarre alors avant elle, et le temps antérieur ne doit
                # compter dans aucun état contractuel (REALVOL au premier chef).
                state_start_step: int = 0,
                state_out: list | None = None,
                flows_at_payment: bool = False,
                reference_spots=None,
                flow_labels_out: list | None = None,
                flow_observations_out: list | None = None,
                analysis_out: list | None = None,
                wof_max_init=None) -> list[float]:
    """Evaluate PayScript on pre-computed spot paths. Observation-only loop.

    wof_min_init / bof_max_init (None, a scalar, or array of shape (N,)) seed the
    running worst-of-min / best-of-max state inherited from before t=0 of this path
    tensor. Used by Mark-to-Future to carry over each outer scenario's pre-t0 barrier
    state into its inner residual-pricing paths; left at None (no-op) for normal
    pricing. index_offset / memo_init / accum_init extend the same inheritance for
    residual deal MtM (api/deals.py): the observation counter continues past the
    replayed observations (PARAM() arrays read the right row), and script variables
    (SET / memory coupons) resume from the replayed state — injected after init_fn
    so the script's own initializers don't reset them.

    s_min_init/s_max_init ((n,) — per-asset realized extrema), s_prev_init
    ((n,) — spots at the last PAST observation, so the first residual
    observation's S_PREV is the real previous fixing instead of 1.0),
    wof0_init (worst-of level at t=0 of this tensor — without it the REALVOL
    log-return series would book a phantom first return log(WOF₁/1.0) equal
    to the whole realized drift), realvol_state_init ({"sumsq": Σ(log-ret²)
    of the realized WOF series, "t": elapsed years} — combined with the
    simulated leg by summing quadratic variations and times, which is
    sampling-frequency-independent, so daily past + weekly future is exact)
    complete the same inheritance for residual deal MtM. All default to
    None/absent = day-0 behavior, bit-identical to before they existed.

    Mark-to-Future (run_mark_to_future) feeds all of them, one value PER PATH:
    each outer scenario reaches the mark date with its own contractual history,
    so S_MIN/S_MAX/S_PREV/REALVOL cannot share a state across the batch. The
    starting window's own realized reduction travels separately, through
    _constater, for the same reason and with the same per-scenario shape.

    bridge_min/bridge_max (ts, n, N), from _bridge_extrema: when provided, the
    RUNNING extrema (WOF_min/BOF_max/S_MIN/S_MAX — the barrier-monitoring
    quantities) accumulate over the continuous within-step extrema instead of
    the weekly endpoints. Observation-date values (spots, WOF, FIX_*, REALVOL)
    stay endpoint-based: those are discrete contractual fixings."""
    _st = _running_state(script, S, n, N, bridge_min, bridge_max,
                         wof_min_init, bof_max_init, s_min_init, s_max_init,
                         wof0_init, realvol_state_init, wof_max_init=wof_max_init)
    WOF, BOF = _st.WOF, _st.BOF
    WOF_min, BOF_max = _st.WOF_min, _st.BOF_max
    WOF_max = _st.WOF_max
    S_min, S_max = _st.S_min, _st.S_max
    cum_sq_ret = _st.cum_sq_ret
    rv_sumsq0, rv_t0 = _st.rv_sumsq0, _st.rv_t0
    _rv_by_path = np.ndim(rv_sumsq0) > 0
    _accum_by_path = np.ndim(accum_init) > 0
    _index_by_path = np.ndim(index_offset) > 0
    _memo_by_path = isinstance(memo_init, (list, tuple))
    _sprev = None if s_prev_init is None else np.asarray(s_prev_init, dtype=float)
    _sprev_by_path = _sprev is not None and _sprev.ndim == 2

    obs_steps = sorted(step_map.keys())
    event_times = _event_times(step_map, dt)
    axis = _times(dt, ts)
    payoffs: list[float] = []
    payoffs_raw: list[float] = []   # undiscounted total cash flow per path

    # PARAM defaults first, user_params (partial or full) override — a caller
    # that omits a param must fall back to its script default, not silently 0.
    full_params = effective_parameters(script.params, user_params)

    for path in range(N):
        # Dated cash flows of THIS path, when the caller asks for them.
        # `flux_map` aggregates across paths, so it cannot answer "when did
        # this particular scenario pay" — which is exactly what an internal
        # rate of return needs. Off by default: it is the only per-path
        # structure here that grows with the number of flows.
        path_flows: list | None = [] if flows_out is not None else None
        path_labels: list | None = [] if flow_labels_out is not None else None
        path_observations = [] if flow_observations_out is not None else None
        if _sprev is None:
            _spots0 = [1.0] * n
        else:
            _spots0 = list(_sprev[:, path]) if _sprev_by_path else list(_sprev)
        ctx = {
            # s_prev_init seeds "spots" (not "s_prev"): the first observation
            # copies spots -> s_prev before overwriting spots, so the real
            # previous fixing lands in S_PREV through the normal mechanics.
            "spots": _spots0,
            "reference_spots": _path_references(reference_spots, lvl_map, path),
            "accum": float(accum_init[path]) if _accum_by_path else accum_init,
            "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "wof_max": 1.0, "t": 0.0,
            "s_min": [1.0] * n, "s_max": [1.0] * n, "s_prev": [1.0] * n, "realvol": 0.0,
            "done": False, "memo": {**full_params}, "total_cf": 0.0, "total_cf_raw": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)
        # Residual-MtM state inheritance: applied AFTER init_fn on purpose —
        # the script's own SET statements must not reset memory coupons and
        # other variables the replayed past already accumulated.
        _memo = memo_init[path] if _memo_by_path else memo_init
        if _memo:
            ctx["memo"].update(_memo)

        done = False
        obs_idx = int(index_offset[path]) if _index_by_path else index_offset
        _rv_s0 = float(rv_sumsq0[path]) if _rv_by_path else rv_sumsq0
        _rv_t = float(rv_t0[path]) if _rv_by_path else rv_t0

        for step in obs_steps:
            if done:
                break
            if df_arr is None:
                disc = math.exp(-r_eff * float(axis[step]))
            else:
                disc = df_arr[step, path] if df_arr.ndim == 2 else df_arr[step]
            ctx["s_prev"] = list(ctx["spots"])
            _spot_row = list(S[step, :, path])
            ctx["spots"] = _spot_row
            ctx["s_min"] = list(S_min[step - 1, :, path])
            ctx["s_max"] = list(S_max[step - 1, :, path])
            # Combined quadratic variation past+future when a realized state is
            # inherited; the historical formula kept bit-identical otherwise.
            # Ecoule DEPUIS LA CONSTATATION INITIALE. Avant le strike les
            # rendements sont nuls par aplatissement, mais le temps, lui,
            # continuerait de courir : la vol realisee sortirait diluee.
            _vecu = max(1, step - state_start_step)
            ctx["realvol"] = (math.sqrt(cum_sq_ret[step - 1, path] / (max(1e-15, float(axis[step]) - float(axis[state_start_step]))))
                              if realvol_state_init is None else
                              math.sqrt((_rv_s0 + cum_sq_ret[step - 1, path])
                                        / (_rv_t + max(1e-15, float(axis[step]) - float(axis[state_start_step])))))
            ctx["t"] = float(axis[step])
            ctx["wof_min"] = float(WOF_min[step - 1, path])
            ctx["wof_max"] = float(WOF_max[step - 1, path])
            ctx["bof_max"] = float(BOF_max[step - 1, path])
            previous_time = None

            for ev_i, ev in enumerate(step_map[step]):
                if done:
                    break
                when = event_times[step][ev_i]
                if previous_time != when:
                    if previous_time is not None:
                        ctx["s_prev"] = list(ctx["spots"])
                    obs_idx += 1
                previous_time = when
                ctx["t"] = when
                ctx["index"] = obs_idx
                # Un flux constaté ici peut ne bouger que des jours plus tard :
                # il vaut sa valeur actualisée à la date de PAIEMENT, pas au
                # fixing. Sans calendrier de règlement, les deux coïncident.
                t_pay = pay_map[step][ev_i] if pay_map and step in pay_map else None
                if t_pay is None:
                    disc_ev = disc * pv_rebase
                else:
                    d_pay = pay_df[t_pay]
                    disc_ev = (d_pay[path] if isinstance(d_pay, np.ndarray)
                               else d_pay) * pv_rebase
                # Le niveau que CET événement constate : la réduction de sa
                # fenêtre s'il en a une, le cours du jour sinon. Deux blocs à la
                # même date peuvent donc lire deux choses différentes — coupon
                # sur moyenne, protection sur clôture.
                _lv = lvl_map[step][ev_i] if lvl_map and step in lvl_map else None
                ctx["spots"] = _spot_row if _lv is None else list(_lv[:, path])
                # Le rang que CET événement lit : sa position dans l'échéancier
                # qu'il nomme. Deux blocs du même jour rattachés à deux
                # calendriers différents voient donc deux rangs différents.
                _rg = rank_map[step][ev_i] if rank_map and step in rank_map else None
                if _rg is not None:
                    ctx["index"] = _rg
                st: dict = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    cf = fl["v"] * disc_ev
                    ctx["total_cf"] += cf
                    ctx["total_cf_raw"] += fl["v"]
                    if path_flows is not None and fl["v"] != 0:
                        path_flows.append((t_pay if flows_at_payment and t_pay is not None else ctx["t"], fl["v"]))
                        if path_observations is not None:
                            path_observations.append(ctx['t'])
                        if path_labels is not None:
                            path_labels.append(fl["lbl"])
                    if record:
                        key = f"{ctx['t']:.6f}|{fl['lbl']}|{fl.get('leg', 0)}|{t_pay}"
                        if key not in flux_map:
                            flux_map[key] = {"t": ctx["t"], "lbl": fl["lbl"], "n": 0, "sum": 0.0, "pv": 0.0,
                                             "t_pay": t_pay if t_pay is not None else ctx["t"]}
                        flux_map[key]["n"] += int(fl["v"] != 0)
                        flux_map[key]["sum"] += fl["v"]
                        flux_map[key]["pv"] += cf
                if st["done"]:
                    done = True
                    ctx["done"] = True
                    if stop_times_out is not None:
                        stop_times_out.append(ctx["t"])

        if not done and mat_events:
            if df_arr is None:
                disc = math.exp(-r_eff * float(axis[ts]))
            else:
                disc = df_arr[ts, path] if df_arr.ndim == 2 else df_arr[ts]
            # Le remboursement final est réglé à la payment date du produit —
            # celle du term sheet, saisie, jamais déduite d'un fixing.
            if mat_pay_df is None:
                disc_mat = disc * pv_rebase
            else:
                disc_mat = (mat_pay_df[path] if isinstance(mat_pay_df, np.ndarray)
                            else mat_pay_df) * pv_rebase
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[ts, :, path])
            ctx["s_min"] = list(S_min[ts - 1, :, path])
            ctx["s_max"] = list(S_max[ts - 1, :, path])
            _vecu_mat = max(1, ts - state_start_step)
            ctx["realvol"] = (math.sqrt(cum_sq_ret[ts - 1, path] / (max(1e-15, float(axis[ts]) - float(axis[state_start_step]))))
                              if realvol_state_init is None else
                              math.sqrt((_rv_s0 + cum_sq_ret[ts - 1, path])
                                        / (_rv_t + max(1e-15, float(axis[ts]) - float(axis[state_start_step])))))
            ctx["t"] = float(axis[ts])
            ctx["wof_min"] = float(WOF_min[ts - 1, path])
            ctx["wof_max"] = float(WOF_max[ts - 1, path])
            ctx["bof_max"] = float(BOF_max[ts - 1, path])
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    cf = fl["v"] * disc_mat
                    ctx["total_cf"] += cf
                    ctx["total_cf_raw"] += fl["v"]
                    if path_flows is not None and fl["v"] != 0:
                        path_flows.append((mat_pay_t if flows_at_payment and mat_pay_t is not None else ctx["t"], fl["v"]))
                        if path_observations is not None:
                            path_observations.append(ctx['t'])
                        if path_labels is not None:
                            path_labels.append(fl["lbl"])
                    if record:
                        key = f"{ctx['t']:.6f}|{fl['lbl']}|{fl.get('leg', 0)}|{mat_pay_t}"
                        if key not in flux_map:
                            flux_map[key] = {"t": ctx["t"], "lbl": fl["lbl"], "n": 0, "sum": 0.0, "pv": 0.0,
                                             "t_pay": mat_pay_t if mat_pay_t is not None else ctx["t"]}
                        flux_map[key]["n"] += int(fl["v"] != 0)
                        flux_map[key]["sum"] += fl["v"]
                        flux_map[key]["pv"] += cf
                if st["done"]:
                    done = True

        payoffs.append(ctx["total_cf"])
        payoffs_raw.append(ctx["total_cf_raw"])
        if analysis_out is not None:
            stopped = bool(ctx["done"])
            analysis_out.append({
                "pv": float(ctx["total_cf"]), "raw": float(ctx["total_cf_raw"]),
                "stop_time": float(ctx['t']) if stopped else None,
                "final_wof": float(S[ts, :, path].min()),
                # Legacy keys are retained; 'ki' means below par, never an
                # inference that a contractual barrier has been hit.
                "outcome": 'autocall' if stopped else 'ki' if ctx['total_cf_raw'] < .999 else 'normal',
            })
        if flows_out is not None:
            flows_out.append(path_flows)
        if flow_labels_out is not None:
            flow_labels_out.append(path_labels)
        if flow_observations_out is not None:
            flow_observations_out.append(path_observations)
        if stop_times_out is not None and not ctx["done"]:
            stop_times_out.append(float(axis[ts]))
        if state_out is not None:
            # The contractual position this path has reached at the end of the
            # tensor — everything a residual repricing needs to continue from
            # here rather than start over. Mark-to-Future replays each outer
            # scenario up to its mark date and feeds this straight back in.
            if ctx.get("reference_spots") is not None:
                ctx["memo"].setdefault("__REFERENCE_SPOTS", list(ctx["reference_spots"]))
            state_out.append({
                "done": done,
                "realized_cf": ctx["total_cf"],
                "index": obs_idx,
                "memo": dict(ctx["memo"]),
                "accum": ctx["accum"],
                "s_prev": list(ctx["spots"]),
                "wof_min": float(WOF_min[ts - 1, path]),
                "wof_max": float(WOF_max[ts - 1, path]),
                "bof_max": float(BOF_max[ts - 1, path]),
                "s_min": [float(v) for v in S_min[ts - 1, :, path]],
                "s_max": [float(v) for v in S_max[ts - 1, :, path]],
                "realvol_sumsq": float(_rv_s0 + cum_sq_ret[ts - 1, path]),
                "realvol_t": _rv_t + float(axis[ts]),
                "wof_last": float(WOF[ts - 1, path]),
            })

    return payoffs, payoffs_raw


def _eval_paths_detailed(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                          dt: float, r_eff: float, user_params: dict,
                          step_map: dict, mat_events: list,
                          df_arr: np.ndarray | None = None,
                          bridge_min=None, bridge_max=None,
                          # Settlement, exactly as in _eval_paths — see there.
                          pay_map: dict | None = None,
                          pay_df: dict | None = None,
                          mat_pay_df=None,
                          pv_rebase: float = 1.0,
                          # Etat du passe rejoue — memes parametres que
                          # _eval_paths, et pour la meme raison : sans eux
                          # l'analyse decrit le produit NEUF. Voir _RunningState.
                          wof_min_init=None, bof_max_init=None,
                          index_offset: int = 0, memo_init: dict | None = None,
                          accum_init: float = 0.0,
                          s_min_init=None, s_max_init=None, s_prev_init=None,
                          wof0_init: float | None = None,
                          realvol_state_init: dict | None = None,
                          lvl_map: dict | None = None,
                          rank_map: dict | None = None,
                          state_start_step: int = 0, reference_spots=None,
                          wof_max_init=None) -> dict:
    """Like _eval_paths but returns per-path outcome classification.

    df_arr (ts+1,) — optional deterministic discount curve; None falls back to
    flat exp(-r_eff*t), matching _eval_paths' behaviour.
    bridge_min/bridge_max: continuous-monitoring extrema, see _eval_paths."""
    _st = _running_state(script, S, n, N, bridge_min, bridge_max,
                         wof_min_init, bof_max_init, s_min_init, s_max_init,
                         wof0_init, realvol_state_init, wof_max_init=wof_max_init)
    WOF, BOF = _st.WOF, _st.BOF
    WOF_min, BOF_max = _st.WOF_min, _st.BOF_max
    WOF_max = _st.WOF_max
    S_min, S_max = _st.S_min, _st.S_max
    cum_sq_ret = _st.cum_sq_ret
    rv_sumsq0, rv_t0 = _st.rv_sumsq0, _st.rv_t0
    _rv_by_path = np.ndim(rv_sumsq0) > 0
    _accum_by_path = np.ndim(accum_init) > 0
    _index_by_path = np.ndim(index_offset) > 0
    _memo_by_path = isinstance(memo_init, (list, tuple))
    _sprev = None if s_prev_init is None else np.asarray(s_prev_init, dtype=float)
    _sprev_by_path = _sprev is not None and _sprev.ndim == 2

    obs_steps = sorted(step_map.keys())
    event_times = _event_times(step_map, dt)
    axis = _times(dt, ts)
    obs_times = sorted({t for times in event_times.values() for t in times})

    payoffs: list[float] = []
    payoffs_raw: list[float] = []
    outcomes: list[str] = []
    stop_times: list[float | None] = []
    final_wofs: list[float] = []
    event_step_counts: dict[int, int] = {}
    event_time_counts: dict[float, int] = {}

    # PARAM defaults first, user_params (partial or full) override — a caller
    # that omits a param must fall back to its script default, not silently 0.
    full_params = effective_parameters(script.params, user_params)

    for path in range(N):
        # s_prev_init amorce "spots" (pas "s_prev") : la premiere constatation
        # recopie spots -> s_prev avant d'ecraser spots, si bien que le vrai
        # fixing precedent atterrit dans S_PREV par la mecanique normale.
        if _sprev is None:
            _spots0 = [1.0] * n
        else:
            _spots0 = list(_sprev[:, path]) if _sprev_by_path else list(_sprev)
        ctx = {
            "spots": _spots0,
            "reference_spots": _path_references(reference_spots, lvl_map, path),
            "accum": float(accum_init[path]) if _accum_by_path else accum_init,
            "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "wof_max": 1.0, "t": 0.0,
            "s_min": [1.0]*n, "s_max": [1.0]*n, "s_prev": [1.0]*n, "realvol": 0.0,
            "done": False, "memo": {**full_params}, "total_cf": 0.0, "total_cf_raw": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)
        # Heritage de l'etat rejoue, APRES init_fn a dessein : les SET du script
        # ne doivent pas remettre a zero les coupons en memoire ni les autres
        # variables que le passe a deja accumulees.
        _memo = memo_init[path] if _memo_by_path else memo_init
        if _memo:
            ctx["memo"].update(_memo)

        done = False
        obs_idx = int(index_offset[path]) if _index_by_path else index_offset
        _rv_s0 = float(rv_sumsq0[path]) if _rv_by_path else rv_sumsq0
        _rv_t = float(rv_t0[path]) if _rv_by_path else rv_t0
        stop_t: float | None = None

        for step in obs_steps:
            if done:
                break
            disc = df_arr[step] if df_arr is not None else math.exp(-r_eff * float(axis[step]))
            ctx["s_prev"] = list(ctx["spots"])
            _spot_row = list(S[step, :, path])
            ctx["spots"] = _spot_row
            ctx["s_min"] = list(S_min[step-1, :, path])
            ctx["s_max"] = list(S_max[step-1, :, path])
            # Variation quadratique passe+futur combinee quand un etat realise
            # est herite ; formule historique gardee bit a bit sinon, exactement
            # comme dans _eval_paths.
            _vecu = max(1, step - state_start_step)
            ctx["realvol"] = (math.sqrt(cum_sq_ret[step-1, path] / (max(1e-15, float(axis[step]) - float(axis[state_start_step]))))
                              if realvol_state_init is None else
                              math.sqrt((_rv_s0 + cum_sq_ret[step-1, path])
                                        / (_rv_t + max(1e-15, float(axis[step]) - float(axis[state_start_step])))))
            ctx["t"] = float(axis[step])
            ctx["wof_min"] = float(WOF_min[step-1, path])
            ctx["wof_max"] = float(WOF_max[step-1, path])
            ctx["bof_max"] = float(BOF_max[step-1, path])
            previous_time = None
            for ev_i, ev in enumerate(step_map[step]):
                if done:
                    break
                when = event_times[step][ev_i]
                if previous_time != when:
                    if previous_time is not None:
                        ctx["s_prev"] = list(ctx["spots"])
                    obs_idx += 1
                previous_time = when
                ctx["t"] = when
                ctx["index"] = obs_idx
                t_pay = pay_map[step][ev_i] if pay_map and step in pay_map else None
                disc_ev = (disc if t_pay is None else pay_df[t_pay]) * pv_rebase
                # Le niveau que CET événement constate : la réduction de sa
                # fenêtre s'il en a une, le cours du jour sinon. Deux blocs à la
                # même date peuvent donc lire deux choses différentes — coupon
                # sur moyenne, protection sur clôture.
                _lv = lvl_map[step][ev_i] if lvl_map and step in lvl_map else None
                ctx["spots"] = _spot_row if _lv is None else list(_lv[:, path])
                # Le rang que CET événement lit : sa position dans l'échéancier
                # qu'il nomme. Deux blocs du même jour rattachés à deux
                # calendriers différents voient donc deux rangs différents.
                _rg = rank_map[step][ev_i] if rank_map and step in rank_map else None
                if _rg is not None:
                    ctx["index"] = _rg
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * disc_ev
                    ctx["total_cf_raw"] += fl["v"]
                if st["done"]:
                    done = True
                    ctx["done"] = True
                    stop_t = ctx["t"]
                    event_step_counts[step] = event_step_counts.get(step, 0) + 1
                    event_time_counts[when] = event_time_counts.get(when, 0) + 1

        if not done and mat_events:
            disc = df_arr[ts] if df_arr is not None else math.exp(-r_eff * float(axis[ts]))
            disc_mat = (disc if mat_pay_df is None else mat_pay_df) * pv_rebase
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[ts, :, path])
            ctx["s_min"] = list(S_min[ts-1, :, path])
            ctx["s_max"] = list(S_max[ts-1, :, path])
            _vecu_mat = max(1, ts - state_start_step)
            ctx["realvol"] = (math.sqrt(cum_sq_ret[ts-1, path] / (max(1e-15, float(axis[ts]) - float(axis[state_start_step]))))
                              if realvol_state_init is None else
                              math.sqrt((_rv_s0 + cum_sq_ret[ts-1, path])
                                        / (_rv_t + max(1e-15, float(axis[ts]) - float(axis[state_start_step])))))
            ctx["t"] = float(axis[ts])
            ctx["wof_min"] = float(WOF_min[ts-1, path])
            ctx["wof_max"] = float(WOF_max[ts-1, path])
            ctx["bof_max"] = float(BOF_max[ts-1, path])
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * disc_mat
                    ctx["total_cf_raw"] += fl["v"]
                if st["done"]:
                    done = True

        pf = ctx["total_cf"]
        payoffs.append(pf)
        payoffs_raw.append(ctx["total_cf_raw"])
        stop_times.append(stop_t)
        final_wofs.append(float(WOF[ts-1, path]) if ts > 0 else 1.0)

        # Classify on the UNDISCOUNTED total: a path returning par (100%) at
        # maturity is "normal" regardless of r — its discounted PV is below 1
        # at any positive rate, which is not a capital loss.
        if stop_t is not None:
            outcomes.append("autocall")
        elif ctx["total_cf_raw"] < 0.999:
            outcomes.append("ki")
        else:
            outcomes.append("normal")

    return {
        "payoffs": payoffs,
        # Le même flux, NON actualisé. Il servait déjà à classer les issues
        # (`total_cf_raw < 0.999` → perte) sans être rendu, si bien que les
        # mesures d'aval n'avaient que la version actualisée sous la main et
        # comparaient une valeur présente à un pair nominal.
        "payoffs_raw": payoffs_raw,
        "outcomes": outcomes,
        "stop_times": stop_times,
        "final_wofs": final_wofs,
        "has_autocall": any(o == "autocall" for o in outcomes),
        "event_step_counts": event_step_counts,
        "event_time_counts": event_time_counts,
        "obs_times": obs_times,
    }
