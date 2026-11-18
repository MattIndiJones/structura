"""Historical backtest of a script on real closes, and the IRR of its flows.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import bisect
import math
from datetime import date, timedelta
from .bindings import effective_parameters
from .parser import CompiledScript
from .evaluation import cle_de_fenetre


# ── Historical backtest ─────────────────────────────────────────────

def _historical_running_extrema(prices_by_ticker: dict, tickers: list[str], ref: dict,
                                 lo_hi: int, hi_hi: int) -> tuple[float, float]:
    """Worst-of-min / best-of-max across EVERY trading day in (lo_hi, hi_hi] —
    not just the window's endpoint — using the real daily closes already
    loaded for the backtest. A barrier breached and recovered BETWEEN two AT
    observation dates would otherwise be invisible: eval_script_on_history
    used to only look at prices ON the script's own observation dates, even
    though the daily history in between is sitting right there in
    prices_by_ticker. (Unlike the Monte Carlo engine's weekly grid, which has
    no finer data at all and needs a Brownian-bridge reconstruction instead —
    see barrier_monitoring="continuous" — this is real data, not a model.)

    Returns (math.inf, -math.inf) if the window is empty or no ticker has
    data for any day in it — neutral for the caller's running min()/max(),
    so an empty/missing window never falsely narrows or widens the extrema."""
    wmin, bmax = math.inf, -math.inf
    for hi in range(lo_hi + 1, hi_hi + 1):
        spots = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            if r0 > 0 and hi < len(px) and px[hi] > 0:
                spots.append(px[hi] / r0)
        if not spots:
            continue
        wmin = min(wmin, min(spots))
        bmax = max(bmax, max(spots))
    return wmin, bmax


def _historical_per_asset_extrema(prices_by_ticker: dict, tickers: list[str], ref: dict,
                                   lo_hi: int, hi_hi: int) -> tuple[list, list]:
    """Per-asset running min/max (normalized by ref) across every trading day in
    (lo_hi, hi_hi] — the S_MIN[i]/S_MAX[i] counterpart of
    _historical_running_extrema. Assets with no data in the window return
    (inf, -inf), neutral for the caller's running fold."""
    mins = [math.inf] * len(tickers)
    maxs = [-math.inf] * len(tickers)
    for i, tk in enumerate(tickers):
        px = prices_by_ticker.get(tk, [])
        r0 = ref.get(tk, 0)
        if r0 <= 0:
            continue
        for hi in range(lo_hi + 1, min(hi_hi + 1, len(px))):
            if px[hi] > 0:
                v = px[hi] / r0
                if v < mins[i]:
                    mins[i] = v
                if v > maxs[i]:
                    maxs[i] = v
    return mins, maxs


def _jours_de_semaine_entre(debut: date, fin: date) -> int:
    """Jours du lundi au vendredi dans ]debut, fin] — négatif si `fin` précède."""
    if fin < debut:
        return -_jours_de_semaine_entre(fin, debut)
    semaines, reste = divmod((fin - debut).days, 7)
    jour = debut.weekday()
    return semaines * 5 + sum(1 for k in range(1, reste + 1) if (jour + k) % 7 < 5)


def _ajouter_jours_de_semaine(jour: date, n: int) -> date:
    """Le jour atteint en avançant (n > 0) ou en reculant (n < 0) de n jours de
    semaine — l'inverse de `_jours_de_semaine_entre`. Un samedi ou un dimanche
    part du vendredi qui le précède."""
    if n == 0:
        return jour
    semaine = jour.weekday()
    if semaine > 4:
        jour -= timedelta(days=semaine - 4)
        semaine = 4
    semaines, reste = divmod(abs(n), 5)
    if n > 0:
        return jour + timedelta(days=semaines * 7 + reste + (2 if semaine + reste > 4 else 0))
    return jour - timedelta(days=semaines * 7 + reste + (2 if semaine - reste < 0 else 0))


class _LectureParDate:
    """Où chaque temps du script se lit dans un historique de clôtures : à sa DATE.

    Le rejeu lisait une date à `round(t × 252)` séances de son départ. C'était
    une transposition, pas une date : une constatation à trois ans tombait une
    dizaine de séances avant son jour, et une fenêtre quotidienne voyait deux
    relevés partager une séance — le même cours compté deux fois, un autre
    jamais (CONSTATATIONS_PERIODE_DESIGN.md §22, §23).

    Chaque `t` redevient la date dont il vient — l'ancre de résolution plus
    `round(t × 365,25)` jours, l'inverse exact de la conversion faite par
    `resolve_constats` — et se lit sur la dernière clôture à cette date ou
    avant, la convention de `_closest_price`.

    Deux régimes, une seule règle :
      - le rejeu d'UN contrat (vie d'un deal, rejeu officiel) part de l'ancre
        elle-même : chaque date se lit telle quelle ;
      - un backtest glissant translate le même calendrier sur chaque jour de
        départ. La translation se fait en jours de semaine : une fenêtre de dix
        jours ouvrés reste dix séances consécutives quel que soit le jour où
        elle démarre, là où une translation calendaire la poserait sur des
        week-ends et lirait trois fois le même vendredi.
    """

    def __init__(self, dates: list[str], start_idx: int, ancre=None, origine=None):
        self._dates = dates
        if isinstance(origine, str):
            origine = date.fromisoformat(origine)
        self._origine = origine or date.fromisoformat(dates[start_idx])
        self._ancre = ancre or self._origine
        self._indices: dict[float, int | None] = {}

    def jour(self, t: float) -> date:
        """La date à laquelle `t` se lit."""
        contrat = self._ancre + timedelta(days=round(t * 365.25))
        if self._ancre == self._origine:
            return contrat
        return _ajouter_jours_de_semaine(
            self._origine, _jours_de_semaine_entre(self._ancre, contrat))

    def indice(self, t: float) -> int | None:
        """La dernière séance à la date de `t` ou avant, -1 si cette date précède
        tout l'historique. None si elle lui est postérieure : un cours qui
        n'existe pas encore ne se lit pas, et ne se reporte pas non plus."""
        if t not in self._indices:
            iso = self.jour(t).isoformat()
            self._indices[t] = (None if iso > self._dates[-1]
                                else bisect.bisect_right(self._dates, iso) - 1)
        return self._indices[t]

    def a_sa_date(self, t: float, k: int) -> bool:
        """La séance `k` est-elle celle du jour de `t` ? Faux quand l'historique
        n'a pas coté ce jour-là — férié de la place, trou de données : le cours
        lu est alors celui d'une séance antérieure, donc reporté."""
        return self._dates[k] == self.jour(t).isoformat()

    def passe_jusqu_a(self) -> float | None:
        """La dernière date lisible, en années depuis l'origine du contrat : tout
        `t` dont la date tombe après reste à venir. None pour un calendrier
        translaté — une fenêtre de backtest —, dont le passé n'a pas de date
        propre."""
        if self._ancre != self._origine:
            return None
        return (date.fromisoformat(self._dates[-1]) - self._origine).days / 365.25


def derniere_fenetre(compiled: CompiledScript, dates: list[str], horizon: float) -> int:
    """Le dernier départ d'un backtest glissant dont tout l'horizon se lit dans
    l'historique, -1 s'il n'y en a aucun.

    L'horizon se compte comme le rejeu le lit, à sa date. Compté à 252 séances
    par an, il laissait les dernières fenêtres finir au-delà de l'historique :
    un rendement sans remboursement, dans les statistiques comme les autres."""
    ancre = getattr(compiled, "origine", None)
    bas, haut, trouve = 0, len(dates) - 1, -1
    while bas <= haut:
        milieu = (bas + haut) // 2
        if _LectureParDate(dates, milieu, ancre).indice(horizon) is not None:
            trouve, bas = milieu, milieu + 1
        else:
            haut = milieu - 1
    return trouve


def seances_jusqu_a(compiled: CompiledScript, dates: list[str], start_idx: int,
                    t: float) -> int | None:
    """Séances entre un départ et la date de `t`, lue comme le rejeu la lit —
    None au-delà de l'historique."""
    k = _LectureParDate(dates, start_idx, getattr(compiled, "origine", None)).indice(t)
    return None if k is None else k - start_idx


def eval_script_on_history(compiled: CompiledScript, dates: list[str],
                            prices_by_ticker: dict, start_idx: int,
                            T_max: float, user_params: dict,
                            tickers: list[str], r: float = 0.03,
                            origine: date | str | None = None,
                            reference_levels: dict[str, float] | None = None,
                            history_policy: dict | None = None) -> dict | None:
    """Replay PayScript using actual historical close prices.

    Chaque date de l'échéancier se lit à sa DATE — voir `_LectureParDate`.
    `origine` est la date calendaire de t = 0 quand on rejoue UN contrat : son
    strike, qui peut être un jour sans cotation. Absente — une fenêtre de
    backtest glissant —, le départ est la séance `start_idx` elle-même."""
    SY_H = 252
    n = len(tickers)
    if not dates or not 0 <= start_idx < len(dates):
        return None
    binding = next((c for c in compiled.constats if c.role == 'initial_fixing'), None)
    if origine is None and binding and binding.source and binding.calendar_values and compiled.origine:
        from .bindings import shift_calendars
        from .parser import parse_script, resolve_constats, effective_T_max
        shifted_origin = date.fromisoformat(dates[start_idx])
        compiled = resolve_constats(parse_script(binding.source),
            shift_calendars(binding.calendar_values, compiled.origine, shifted_origin),
            anchor=shifted_origin, currency=binding.calendar_currency)
        T_max = effective_T_max(compiled, T_max)
    lecture = _LectureParDate(dates, start_idx, getattr(compiled, "origine", None), origine)
    if history_policy is not None:
        if origine is not None:
            raise ValueError("La convention Following/strict est réservée au backtest glissant.")
        from ..backtest_history import BacktestObservationReader
        lecture = BacktestObservationReader(lecture, dates, tickers, **history_policy)

    # Les blocs d'une même DATE s'exécutent ensemble, dans l'ordre du script —
    # le regroupement du `step_map` du moteur, par date et non par pas : deux
    # dates distinctes ne partagent plus rien, même un jour d'écart.
    step_map: dict = {}
    # Fenetre de constatation de chaque EVENEMENT, alignee index par index sur
    # step_map — meme regle que dans le moteur MC : deux blocs au meme jour
    # peuvent constater differemment.
    win_map: dict = {}
    rank_map: dict = {}
    payment_map: dict = {}
    mat_events = []
    for ev in compiled.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for i, d in enumerate(ev.dates):
                cle = round(d, 9)
                step_map.setdefault(cle, []).append(ev)
                win_map.setdefault(cle, []).append(
                    (ev.reduction, ev.window_dates[i])
                    if ev.reduction and ev.window_dates and i < len(ev.window_dates)
                    else None)
                # Le rang que CET evenement lit, comme dans le moteur MC : sa
                # position dans l'echeancier qu'il nomme. Le rejeu comptait ses
                # propres passages, si bien qu'un second calendrier lui faisait
                # lire 2/4/6 la ou le pricing lisait 1/2/3 — le meme produit se
                # decidait donc autrement selon qu'on le pricait ou qu'on le
                # rejouait. Voir test_backtest_oracle.py.
                rank_map.setdefault(cle, []).append(
                    ev.ranks[i] if ev.ranks and i < len(ev.ranks) else None)
                pays = ev.payment_dates
                payment_map.setdefault(cle, []).append(
                    pays[i] if pays and i < len(pays) else None)

    reportes: set = set()

    def _closes_on(tk: str, ds: list[float]) -> list[float]:
        """Closes of `tk` at a window's dates — "last close <= date", the same
        convention as _closest_price by default. An explicit backtest policy
        instead resolves each fixing to its genuine common following date.

        Un cours absent est REPORTÉ depuis la dernière séance connue, jamais
        sauté : sauter réduisait la fenêtre en silence, et une moyenne sur trois
        relevés au lieu de quatre se présentait comme une moyenne. Le report est
        la convention de place pour un jour sans cotation ; ce qu'il faut, c'est
        qu'il se dise — d'où `reportes`, remonté dans le résultat. Un jour où
        l'historique n'a pas coté du tout est un report au même titre qu'un
        cours nul.

        Les dates encore dans le futur restent hors de la fenêtre : il n'y a
        rien à reporter d'un cours qui n'existe pas encore."""
        px = prices_by_ticker.get(tk, [])
        out = []
        for d in ds:
            hi = lecture.indice(d)
            if hi is None or hi < start_idx or hi >= len(px):
                continue
            # Remonter jusqu'au dernier cours coté à cette date ou avant.
            k = hi
            while k >= start_idx and not px[k] > 0:
                k -= 1
            if k < start_idx:
                continue
            out.append(px[k])
            if k != hi or not lecture.a_sa_date(d, hi):
                reportes.add(round(d, 6))
        return out

    def _reduce(vals: list[float], reduction: str) -> float:
        if reduction == "MIN":
            return min(vals)
        if reduction == "MAX":
            return max(vals)
        return sum(vals) / len(vals)

    # S0 par sous-jacent. Sans fenetre de depart c'est le cours du jour de
    # strike ; avec une fenetre ENTIEREMENT passee c'est sa reduction, et le
    # rejeu comme le MtM residuel se lisent alors directement dans les bonnes
    # unites. Une fenetre encore ouverte garde le cours du strike comme
    # reference provisoire : les fixings deja tombes partent dans fix_state, et
    # c'est le moteur qui les combinera avec ceux qui restent a simuler.
    _fix_dates = compiled.strike_fix_dates or []
    _fix_red = compiled.strike_fix_reduction
    _fix_all_past = bool(_fix_red and _fix_dates
                          and lecture.indice(max(_fix_dates)) is not None)
    ref: dict = {}
    reference_levels = reference_levels or {}
    for tk in tickers:
        px = prices_by_ticker.get(tk, [])
        if not (px and start_idx < len(px) and px[start_idx] > 0):
            continue
        if _fix_all_past:
            closes = _closes_on(tk, _fix_dates)
            ref[tk] = _reduce(closes, _fix_red) if closes else px[start_idx]
        else:
            explicit = float(reference_levels.get(tk, 0.0) or 0.0)
            ref[tk] = explicit if explicit > 0 else px[start_idx]
    if not ref:
        return None

    full_params = effective_parameters(compiled.params, user_params)

    end_idx = len(dates) - 1

    # Daily worst-of series (normalized by ref) over [start_idx, end_idx] and
    # its cumulative squared log-returns — the realized leg of REALVOL. The
    # engine's REALVOL is a quadratic-variation estimator (Σr²/t, no centering),
    # which is sampling-frequency independent: this daily past combines exactly
    # with the simulated weekly future by summing sumsq and times.
    wof_days: list[int] = []
    wof_vals: list[float] = []
    for hi in range(start_idx, end_idx + 1):
        vals = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            if r0 > 0 and hi < len(px) and px[hi] > 0:
                vals.append(px[hi] / r0)
        if vals:
            wof_days.append(hi)
            wof_vals.append(min(vals))
    rv_cum = [0.0] * len(wof_vals)
    _acc = 0.0
    for k in range(1, len(wof_vals)):
        lr = math.log(max(wof_vals[k], 1e-12) / max(wof_vals[k - 1], 1e-12))
        _acc += lr * lr
        rv_cum[k] = _acc

    def _rv_at(hi: int) -> float:
        """Annualized realized vol of the WOF series up to day hi included."""
        k = bisect.bisect_right(wof_days, hi) - 1
        t_y = ((date.fromisoformat(dates[hi])-date.fromisoformat(dates[start_idx])).days / 365.25
               if history_policy is not None else (hi - start_idx) / SY_H)
        return math.sqrt(rv_cum[k] / t_y) if k >= 0 and t_y > 0 else 0.0

    # Partie deja realisee de la fenetre de depart, PAR SOUS-JACENT et en
    # unites de `ref`. Ne sert que si la fenetre est encore ouverte : une
    # fenetre close est deja dans `ref` ci-dessus, et la compter deux fois
    # ramenerait le niveau initial a 1,0.
    fix_state = None
    if _fix_red and _fix_dates and not _fix_all_past:
        past = [d for d in _fix_dates if lecture.indice(d) is not None]
        if past:
            sums, mins, maxs, ok = [], [], [], True
            for tk in tickers:
                r0 = ref.get(tk, 0)
                vals = [v / r0 for v in _closes_on(tk, past)] if r0 > 0 else []
                if not vals:
                    ok = False
                    break
                sums.append(sum(vals)); mins.append(min(vals)); maxs.append(max(vals))
            if ok:
                fix_state = {"n": len(past), "sum": sums, "min": mins, "max": maxs}

    # Les fenêtres de constatation À CHEVAL sur la fin de l'historique : la part
    # déjà cotée, réduite par sous-jacent en unités de `ref`. Le script résiduel
    # n'en gardera que les relevés à venir (_shift_events_for_mtf) et la
    # recombinera avec celle-ci. Sans elle, le résiduel ramenait les relevés
    # passés au premier pas simulé. Rien pour une fenêtre de backtest glissant,
    # dont le calendrier est translaté et le passé sans date propre.
    releves_realises: dict = {}
    if lecture.passe_jusqu_a() is not None:
        for ev in compiled.events:
            if ev.type == "AT_MATURITY" or not ev.reduction or not ev.window_dates:
                continue
            for i, fenetre in enumerate(ev.window_dates[:len(ev.dates)]):
                lus = [d for d in fenetre if lecture.indice(d) is not None]
                if not lus or len(lus) == len(fenetre):
                    continue
                cle = cle_de_fenetre(ev.constat_ref,
                                     ev.ranks[i] if ev.ranks and i < len(ev.ranks) else None)
                if cle in releves_realises:
                    continue
                par_actif = []
                for tk in tickers:
                    r0 = ref.get(tk, 0)
                    par_actif.append([v / r0 for v in _closes_on(tk, lus)] if r0 > 0 else [])
                # Un sous-jacent sans cours sur un relevé laisserait les autres
                # se réduire sur plus de points que lui : pas de part réalisée,
                # et le résiduel le refusera en le disant.
                if any(len(v) != len(lus) for v in par_actif):
                    continue
                releves_realises[cle] = {
                    "n": len(lus),
                    "sum": [sum(v) for v in par_actif],
                    "min": [min(v) for v in par_actif],
                    "max": [max(v) for v in par_actif],
                }

    ctx = {
        "spots": [1.0]*n, "reference_spots": [ref[tk] for tk in tickers], "accum": 0.0, "index": 0,
        "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
        "s_min": [1.0]*n, "s_max": [1.0]*n, "s_prev": [1.0]*n, "realvol": 0.0,
        "done": False, "memo": full_params, "total_cf": 0.0,
    }
    if compiled.init_fn:
        compiled.init_fn(ctx)

    cfs: list[dict] = []
    done = False
    obs_idx = 0
    wof_run = 1.0
    bof_run = 1.0
    s_min_run = [1.0] * n
    s_max_run = [1.0] * n
    T_actual = T_max
    prev_hi = start_idx   # last day scanned for running extrema (inception = spot 1.0, already the seed)

    for t_obs in sorted(step_map.keys()):
        if done and history_policy is not None:
            break
        hi = lecture.indice(t_obs)
        if hi is None:
            break                   # cette date n'est pas encore dans l'historique
        if hi < 0:
            continue                # antérieure à tout l'historique
        # Fold in every trading day since the last observation (or inception)
        # before evaluating the script's condition at this date — see
        # _historical_running_extrema.
        w_win, b_win = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, hi)
        wof_run = min(wof_run, w_win)
        bof_run = max(bof_run, b_win)
        pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, hi)
        s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
        s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]
        prev_hi = hi

        # Niveau constate : la reduction de sa fenetre quand il y en a une,
        # par sous-jacent, en quotidien ici (le passe est connu jour par jour).
        # Une fenetre a cheval sur aujourd'hui n'a que ses closes deja tombes —
        # le rejeu ne va pas plus loin que l'historique.
        def _levels(win):
            out = []
            for tk in tickers:
                px = prices_by_ticker.get(tk, [])
                r0 = ref.get(tk, 0)
                if r0 <= 0:
                    out.append(1.0)
                    continue
                brut = px[hi] / r0 if hi < len(px) else 1.0
                if win:
                    closes = _closes_on(tk, win[1])
                    out.append(_reduce([v / r0 for v in closes], win[0]) if closes else brut)
                else:
                    out.append(brut)
            return out

        spots = _levels(None)
        # Official replay keeps contractual time. The explicit backtest policy
        # uses the actual observation date without backdating future quotes.
        t_y = lecture.effective_time(t_obs) if history_policy is not None else t_obs
        if history_policy is not None and abs(t_obs-T_max) <= 1e-6:
            T_actual = t_y
        ctx.update({"spots": spots, "s_prev": list(ctx["spots"]),
                    "s_min": list(s_min_run), "s_max": list(s_max_run),
                    "realvol": _rv_at(hi),
                    "t": t_y, "wof_min": wof_run,
                    "bof_max": bof_run, "index": obs_idx + 1})
        obs_idx += 1
        for ev_i, ev in enumerate(step_map[t_obs]):
            if done:
                break
            _w = win_map.get(t_obs, [])
            ctx["spots"] = _levels(_w[ev_i] if ev_i < len(_w) else None)
            _r = rank_map.get(t_obs, [])
            _rg = _r[ev_i] if ev_i < len(_r) else None
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
                # La séance lue voyage avec le flux : un écran qui la
                # recalculerait depuis `t` referait la transposition.
                _payments = payment_map.get(t_obs, [])
                payment_t = (_payments[ev_i]
                             if ev_i < len(_payments) and _payments[ev_i] is not None
                             else t_y)
                payment_date = lecture.jour(payment_t).isoformat()
                historical_dates = {}
                if history_policy is not None:
                    contractual_payment = (_payments[ev_i]
                        if ev_i < len(_payments) and _payments[ev_i] is not None else t_obs)
                    payment_t, payment_date, requested_payment = lecture.payment(t_obs, contractual_payment)
                    historical_dates = {"requested_date": lecture.jour(t_obs).isoformat(),
                                        "requested_payment_date": requested_payment}
                cfs.append({
                    "t": t_y, "cf": fl["v"], "date": dates[hi],
                    "payment_t": payment_t,
                    "payment_date": payment_date, **historical_dates,
                })
            if st["done"]:
                done = True
                ctx["done"] = True
                T_actual = t_y

    if not done and mat_events:
        mhi = lecture.indice(T_max)
        if mhi is not None and mhi >= 0:
            maturity_t = lecture.effective_time(T_max) if history_policy is not None else T_max
            if history_policy is not None:
                T_actual = maturity_t
            w_win, b_win = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, mhi)
            wof_run = min(wof_run, w_win)
            bof_run = max(bof_run, b_win)
            pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, mhi)
            s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
            s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]
            spots = []
            for tk in tickers:
                px = prices_by_ticker.get(tk, [])
                r0 = ref.get(tk, 0)
                spots.append(px[mhi] / r0 if r0 > 0 and mhi < len(px) else 1.0)
            ctx.update({"spots": spots or [1.0]*n, "s_prev": list(ctx["spots"]),
                        "s_min": list(s_min_run), "s_max": list(s_max_run),
                        "realvol": _rv_at(mhi),
                        "t": maturity_t,
                        "wof_min": wof_run, "bof_max": bof_run})
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
                    payment_t, payment_date = T_max, lecture.jour(T_max).isoformat()
                    historical_dates = {}
                    if history_policy is not None:
                        due = lecture.maturity_payment_t if lecture.maturity_payment_t is not None else T_max
                        payment_t, payment_date, requested_payment = lecture.payment(T_max, due)
                        historical_dates = {"requested_date": lecture.jour(T_max).isoformat(),
                                            "requested_payment_date": requested_payment}
                    cfs.append({
                        "t": maturity_t, "cf": fl["v"], "date": dates[mhi],
                        "payment_t": payment_t, "payment_date": payment_date, **historical_dates,
                    })
                if st["done"]:
                    done = True

    # Fold the days between the last replayed observation and the end of the
    # available history into the extrema: a continuously-monitored KI touched
    # BETWEEN two observation dates must show in the inherited state (min/max
    # folding is idempotent, re-folding an already-scanned window is harmless).
    if end_idx > prev_hi:
        w_tail, b_tail = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, end_idx)
        wof_run = min(wof_run, w_tail)
        bof_run = max(bof_run, b_tail)
        pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, end_idx)
        s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
        s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]

    return {
        "cash_flows": cfs,
        "early_recall": T_actual < T_max,
        "T_actual": T_actual,
        # Daily worst-of trajectory over the replayed window — already
        # computed above for the REALVOL leg, just exposed here so a caller
        # can chart the PRODUCT's actual path (not just the raw underlying),
        # e.g. the reinvestment proposal backtest (api/deals.py).
        "wof_series": {"dates": [dates[d] for d in wof_days], "values": [round(v, 4) for v in wof_vals]},
        # Relevés dont le cours a été reporté faute de cotation ce jour-là. Le
        # rejeu aboutit, mais la constatation porte en partie sur une valeur
        # reportée : une liste vide est la seule qui autorise à n'en rien dire.
        "releves_reportes": sorted(reportes),
        **({"history_adjustments": lecture.report()} if history_policy is not None else {}),
        # S₀ par ticker, en cours, quand la fenêtre de départ est CLOSE : la
        # réduction de ses relevés. Tout l'état ci-dessous est exprimé dans ces
        # unités — un MtM résiduel qui mesurerait le spot du jour contre le seul
        # fixing du strike partirait d'un autre niveau que son propre passé.
        # Vide sans fenêtre de départ, ou tant qu'elle est ouverte.
        "niveaux_initiaux": dict(ref) if _fix_all_past else {},
        # La dernière date que ce rejeu a pu lire, en années depuis l'origine du
        # contrat : la coupe entre passé et vie restante (_shift_events_for_mtf).
        # None pour une fenêtre de backtest, dont le calendrier est translaté.
        "passe_jusqu_a": lecture.passe_jusqu_a(),
        # Final replayed state — what a residual-MtM Monte Carlo must inherit
        # to continue this product's life instead of restarting it: script
        # variables (SET / memory coupons live in memo), the observation
        # counter (PARAM() arrays read their row from it), the realized
        # running extrema (basket AND per-asset), the accumulator, the spots
        # at the last past observation (S_PREV of the first residual one), the
        # realized quadratic variation of the WOF series (REALVOL leg) and the
        # realized part of the STRIKE_FIX window. See api/deals.py:deal_mtm.
        "state": {
            "memo": {**ctx["memo"], "__REFERENCE_SPOTS": [ref[tk] for tk in tickers]},
            "index": obs_idx,
            "wof_min": wof_run,
            "bof_max": bof_run,
            "accum": ctx.get("accum", 0.0),
            "s_min": list(s_min_run),
            "s_max": list(s_max_run),
            "s_prev": list(ctx["spots"]),
            "wof_last": wof_vals[-1] if wof_vals else 1.0,
            "realvol_state": {"sumsq": rv_cum[-1] if rv_cum else 0.0,
                              "t": max(0.0, (end_idx - start_idx) / SY_H)},
            "fix_state": fix_state,
            # La part déjà cotée des fenêtres à cheval sur la fin de
            # l'historique, par fenêtre (`calendrier#rang`) — voir plus haut.
            "releves_realises": releves_realises,
        },
    }


IRR_FLOOR = -1.0 + 1e-6     # -99.9999% — below this everything is "total loss"
IRR_CAP = 10.0              # +1000%, past which the figure is an artefact


def compute_irr(cash_flows: list[dict], guess: float = 0.1,
                tol: float = 1e-10, max_iter: int = 200) -> float | None:
    """IRR by bracketing then bisection. cash_flows = list of {t: years, cf: amount}.

    The previous solver was a bare Newton-Raphson started at 10% and clamped
    to [-0.99, 10]. It answered correctly on ordinary windows and returned
    None on the ones that matter most:

      * a total loss (-100 at t=0, nothing back) has its IRR at exactly -100%,
        which a clamp at -99% can never reach;
      * a near-total loss (-100, +0.01) sits at -99.99%, outside the clamp too;
      * an overshoot into the clamp stalls the iteration on the flat region.

    Those Nones were then dropped by the callers, so the worst windows of a
    backtest vanished from its statistics — a selection bias pointing one way,
    in favour of the product. A performance measure that quietly discards its
    own left tail is worse than no measure.

    Bisection needs no derivative, cannot overshoot, and converges on every
    bracketed root. Newton is kept only as a final polish. The cases that
    genuinely have no single IRR (no outflow, no inflow, several sign changes)
    still return None — but they are now the only ones, and they are honest."""
    if not cash_flows:
        return None

    def npv(r_: float) -> float:
        total = 0.0
        base = 1.0 + r_
        for cf in cash_flows:
            t = cf["t"]
            try:
                total += cf["cf"] / (base ** t) if t else cf["cf"]
            except (ZeroDivisionError, OverflowError):
                return math.inf if cf["cf"] > 0 else -math.inf
        return total

    inflow = sum(cf["cf"] for cf in cash_flows if cf["cf"] > 0)
    outflow = sum(cf["cf"] for cf in cash_flows if cf["cf"] < 0)
    if inflow == 0.0 and outflow == 0.0:
        return None                     # nothing happened
    if outflow == 0.0:
        return None                     # no money ever invested: no rate of return
    if inflow == 0.0:
        # Everything paid in, nothing back. The rate of return is -100%, and
        # saying so is the entire point of this rewrite.
        return -1.0

    # A conventional window — money out, then money in — has exactly one sign
    # change, so NPV is strictly decreasing in r and the root is unique. That
    # is every real product window: you pay at inception and receive coupons
    # and redemption afterwards. Anything else can carry several mathematical
    # IRRs, and picking one of them (which the old Newton did, silently) is
    # not a measure of anything.
    ordered = sorted(cash_flows, key=lambda c: c["t"])
    signs = [1 if cf["cf"] > 0 else -1 for cf in ordered if cf["cf"] != 0]
    conventional = sum(1 for a, b in zip(signs, signs[1:]) if a != b) == 1

    f_lo, f_hi = npv(IRR_FLOOR), npv(IRR_CAP)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)):
        return None
    if f_lo == 0.0:
        return IRR_FLOOR
    if f_hi == 0.0:
        return IRR_CAP
    if f_lo > 0.0 and f_hi > 0.0:
        # Conventional: NPV decreases, so still positive at +1000% means the
        # root is beyond it — report the cap rather than drop the window.
        return IRR_CAP if conventional else None
    if f_lo < 0.0:
        # Impossible for a conventional window with any inflow: as r → -100%
        # the discounted inflows dominate and NPV → +∞. Reaching here means a
        # late negative flow outweighs them, i.e. a non-conventional profile.
        return None

    lo, hi = IRR_FLOOR, IRR_CAP
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if f_mid == 0.0 or (hi - lo) < tol:
            lo = hi = mid
            break
        if (f_lo < 0.0) == (f_mid < 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    r = 0.5 * (lo + hi)

    # Newton polish — accepted only if it stays inside the bracket and does
    # not worsen the residual, so it can never undo the bisection.
    def dnpv(r_: float) -> float:
        try:
            return -sum(cf["t"] * cf["cf"] / (1.0 + r_) ** (cf["t"] + 1)
                        for cf in cash_flows)
        except (ZeroDivisionError, OverflowError):
            return 0.0

    d = dnpv(r)
    if abs(d) > 1e-12:
        cand = r - npv(r) / d
        if IRR_FLOOR <= cand <= IRR_CAP and abs(npv(cand)) < abs(npv(r)):
            r = cand

    return r if math.isfinite(r) else None
