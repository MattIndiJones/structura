"""Valorisation en cours de vie : rejouer le passé, pricer le reliquat.

Ce code vivait dans la couche « deal » et lisait des colonnes de deal. Il est
ici pour que le Pricer puisse valoriser un produit à une date quelconque sans
avoir à le booker — un produit du marché secondaire n'est pas un deal qu'on a
traité, et le booker pour l'évaluer serait un détournement.

Le principe : sur un produit à mémoire ou à barrière, une valorisation repartie
de zéro avec le bon spot serait fausse. Il faut reconstituer l'ÉTAT — coupons
déjà versés, mémoire accumulée, extrema franchis, compteur d'observations — en
rejouant le script sur les cours réellement constatés, puis simuler la seule
vie restante à partir de là.

Le module ne connaît ni FastAPI ni la base : il prend des paramètres, il rend
un état, et il signale ses refus par ValuationError.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .market_snapshot import snapshot_rate
from .payscript.engine import eval_script_on_history, _shift_events_for_mtf
from .payscript.parser import CompiledScript, parse_script, resolve_constats


class ValuationError(ValueError):
    """Refus métier : le produit ne peut pas être valorisé en l'état.

    Distincte d'une erreur technique — l'appelant la traduit en message
    utilisateur, jamais en trace."""


@dataclass
class InLifeProduct:
    """Ce qu'il faut savoir d'un produit pour le valoriser en cours de vie.

    Volontairement indépendant du modèle Deal : le Pricer remplit ces champs
    depuis son formulaire, le Booking depuis ses colonnes."""
    script_snapshot: str
    # Sous-jacents dans leur identité contractuelle : [{name, ticker, ...}].
    underlyings: list[dict]
    # Niveau initial constaté par sous-jacent, en absolu — c'est le strike du
    # term sheet, pas une performance.
    strike_levels: dict[str, float]
    strike_date: date
    value_date: date
    tenor: float
    currency: str = ""
    payment_date: Optional[date] = None
    # Snapshot de marché : constats, user_params, r, paramètres par sous-jacent.
    market: dict = field(default_factory=dict)


@dataclass
class VariantTerms:
    """Les termes qui remplacent ceux du parent À PARTIR de la valorisation.

    Une variante ne réécrit pas l'histoire. Le passé s'est produit sous les
    termes du parent — les coupons versés l'ont été, la mémoire accumulée l'a
    été, le produit n'a pas été rappelé. Ces termes-là ne décrivent donc que la
    vie restante, et le rejeu ne les voit jamais.

    C'est ce qui désamorce le piège central de l'exercice : une variante dont
    le seuil de rappel descend à 50 % ne peut PAS rappeler dans le passé, parce
    que le passé n'est jamais rejoué avec elle. Ce n'est pas un contrôle qu'on
    pourrait oublier d'écrire, c'est une impossibilité de structure.

    Tout champ laissé à None est hérité du parent. Un objet vide vaut donc
    exactement « pas de variante », et `build_residual` se comporte comme
    avant : c'est la propriété qui garantit qu'aucune valorisation ordinaire ne
    change de prix en introduisant cette notion.
    """
    script: Optional[str] = None
    user_params: Optional[dict] = None
    # Calendrier de la variante — porte la prolongation de maturité. Ses dates
    # passées doivent rester identiques à celles du parent (cf. _refuser_si_le_passe_diverge).
    constats: Optional[dict] = None

    def est_vide(self) -> bool:
        return self.script is None and self.user_params is None and self.constats is None


@dataclass
class Residual:
    """Le produit ramené à sa vie restante, prêt pour le Monte Carlo."""
    early_recall: bool = False
    T_actual: Optional[float] = None
    compiled: Optional[CompiledScript] = None
    residual_script: Optional[CompiledScript] = None
    state: dict = field(default_factory=dict)
    realized_flows: list = field(default_factory=list)
    norm_spots: list = field(default_factory=list)
    engine_uls: list = field(default_factory=list)
    T_elapsed: float = 0.0
    r_frac: float = 0.0
    # Le produit n'a pas encore commencé : la date de valorisation précède la
    # constatation initiale. Il n'y a alors pas de passé à rejouer et S₀ n'est
    # pas connu — voir la branche du même nom dans build_residual.
    pre_strike: bool = False
    # Années d'ici la constatation initiale, sur l'axe résiduel. None dès que le
    # strike est connu. Se transmet tel quel à run_mc, qui en tire le pas où
    # chaque trajectoire fixe son propre niveau de référence.
    strike_set_t: Optional[float] = None
    # L'historique effectivement utilisé, rendu à l'appelant : la note de
    # valorisation et l'explication de P&L le réaffichent.
    prices: dict = field(default_factory=dict)
    dates_list: list = field(default_factory=list)
    # Le detail du rejeu, dont la note de valorisation et l explication de P&L
    # ont besoin : parametres du produit, sortie brute du replay, index du
    # premier jour cote et niveaux initiaux par sous-jacent.
    user_params: dict = field(default_factory=dict)
    replay: dict = field(default_factory=dict)
    start_idx: int = 0
    s0_map: dict = field(default_factory=dict)
    # ── Variante ────────────────────────────────────────────────────
    # Les PARAM que le Monte Carlo résiduel doit employer. Distincts de
    # `user_params`, qui sont ceux du rejeu : sur un avenant les deux diffèrent,
    # et les confondre ferait pricer la vie restante aux conditions d'origine.
    residual_user_params: dict = field(default_factory=dict)
    # Le TEXTE et le calendrier qui pricent — ceux de la variante s'il y en a
    # une. Les analytiques qui repricent dans un processus séparé (grille de
    # scénarios, VaR) reçoivent le script en texte et le recompilent : sans ces
    # deux champs, elles n'ont que ceux de la requête, c'est-à-dire ceux de
    # l'ORIGINE, et décrivent le produit d'origine sous une étiquette de
    # variante.
    pricing_script_text: str = ""
    pricing_constats: dict = field(default_factory=dict)
    # Fin de la vie restante SOUS LES TERMES QUI PRICENT, sur l'axe résiduel.
    # None hors variante : la maturité de la requête fait alors foi, et rien ne
    # change. Une variante qui prolonge doit au contraire déplacer l'horizon —
    # sans quoi ses constatations tombent hors du Monte Carlo et le
    # remboursement final n'est jamais versé (mesuré : 46,16 % → 12,23 %, et
    # deux variantes de protection différentes rendaient le même prix, ce qui
    # était le seul signe visible).
    T_residual_max: Optional[float] = None
    # Ce que la variante fait de l'état repris du passé. Vide hors variante.
    # Voir `_etat_repris_par_la_variante` : ce n'est pas un refus, c'est un fait
    # que l'utilisateur doit voir.
    variant_state_check: dict = field(default_factory=dict)


def _engine_underlyings(market: dict, underlyings_json: list) -> list[dict]:
    """Engine-unit underlyings from the booking snapshot: display units
    (σ=20 → 0.20) with neutral defaults for anything a partial snapshot
    (old / API-booked deal) doesn't carry — same fallbacks the Pricer UI
    applies when reopening such a deal (see pricing.js loadFromDeal)."""
    snap_by_name = {u.get("name"): u for u in market.get("underlyings", []) or []}
    out = []
    for u_ref in underlyings_json:
        u = snap_by_name.get(u_ref.get("name"), {})
        def g(key, default, scale=100.0):
            v = u.get(key)
            return default if v is None else v / scale
        dividend_curve = []
        for node in u.get("dividendCurve") or []:
            if isinstance(node, dict):
                maturity, rate = node.get("T"), node.get("rate")
            else:
                maturity, rate = node
            dividend_curve.append([float(maturity), float(rate) / 100.0])
        out.append({
            "name": u_ref.get("name", ""), "ticker": u_ref.get("ticker", ""),
            "ccy": u.get("ccy", "EUR"),
            "sigma": g("sigma", 0.20), "q": g("q", 0.02),
            "dividend_curve": dividend_curve,
            "dividend_decay": g("dividendDecay", 0.0),
            "sigma_fx": g("sigma_fx", 0.0), "rho_sfx": g("rho_sfx", 0.0),
            "ccyh": g("ccyh", 0.0, 10000.0),
            "v0": g("v0", 0.04), "kappa": u.get("kappa") or 2.0,
            "theta": g("theta", 0.04), "xi": g("xi", 0.35),
            "rho_h": g("rho_h", -0.70), "rho_rS": g("rho_rS", 0.40),
            "alpha": g("alpha", 0.20), "beta": g("beta", 0.50),
            "rho": g("rho", -0.30), "nu": g("nu", 0.40),
            "skew": g("skew", -0.10), "curvature": g("curvature", 0.05),
        })
    return out


def _shift_dividend_curve(underlying: dict, elapsed: float) -> None:
    """Condition a booked dividend curve on a residual valuation date.

    Original nodes are bucket ends measured from the deal value date. A
    residual Monte Carlo starts at zero again, so every surviving end date is
    shifted by elapsed time and q is reset to the currently active bucket.
    """
    curve = underlying.get("dividend_curve") or []
    if not curve or elapsed <= 0.0:
        return
    eps = 1e-9
    remaining = [
        [float(end) - elapsed, float(rate)]
        for end, rate in curve
        if float(end) > elapsed + eps
    ]
    if remaining:
        underlying["q"] = remaining[0][1]
        underlying["dividend_curve"] = remaining
    else:
        # Beyond the final stored node the convention is a flat extension of
        # the last bucket. Clearing the curve restores exactly that scalar path.
        underlying["q"] = float(curve[-1][1])
        underlying["dividend_curve"] = []


# ── Réinvestissement (module solution d'investissement) ────────────────
# Flow A (ce fichier, "roll") : côté client, dans la vue MtM — reconduire la
# MÊME structure sur le MÊME sous-jacent, value date/strike date à aujourd'hui,
# tenor plein d'origine. Ce n'est PAS un MtM résiduel (pas d'historique à
# rejouer, pas d'état à porter) : juste le même script pricé à neuf.
# Flow B (ce fichier, "scan") : côté desk, onglet Life Cycle dédié — swap du
# sous-jacent sur un pool de candidats, coupon résolu par bissection (réutilise
# solve_for_param, le même moteur que le Solveur existant), classement filtré
# par seuils de proba. Jamais montré au client tel quel.
# Voir MEMORY investment-solution-module pour le cadrage complet.


def _dates_passees(compiled: CompiledScript, T_elapsed: float) -> list[float]:
    """Les constatations déjà tombées, en fractions d'année depuis le strike."""
    return sorted({round(d, 6)
                   for e in compiled.events for d in (e.dates or [])
                   if d <= T_elapsed + 1e-9})


def _refuser_si_le_passe_diverge(parent: CompiledScript, variante: CompiledScript,
                                 T_elapsed: float) -> None:
    """Le calendrier passé de la variante doit être celui du parent, à l'identique.

    Prolonger la maturité est permis — les dates passées restent un préfixe du
    nouveau calendrier. Changer la FRÉQUENCE ne l'est pas : les constatations
    déjà tombées ne s'alignent plus, et `INDEX` — que la variante hérite du
    rejeu — désigne alors une autre observation que celle qu'il compte. Un
    recalage silencieux donnerait un prix plausible pour un produit qui
    n'existe pas.
    """
    avant, apres = _dates_passees(parent, T_elapsed), _dates_passees(variante, T_elapsed)
    if avant == apres:
        return
    raise ValuationError(
        f"Le calendrier passé de la variante diffère de celui du deal d'origine "
        f"({len(avant)} constatation(s) écoulée(s) contre {len(apres)}). Un avenant "
        f"ne réécrit pas le passé : la prolongation de maturité est possible, le "
        f"changement de fréquence ou de date initiale ne l'est pas — passez en "
        f"mode nouvelle note.")


def _sans_les_param_semes(memo: dict, compiled: CompiledScript, texte: str) -> dict:
    """Retire de la mémoire du rejeu les PARAM qui n'y sont que par mécanique.

    Le moteur range les PARAM dans `ctx["memo"]`, aux côtés des variables du
    script. À la fin du rejeu, la mémoire contient donc les barrières et le
    coupon EN VIGUEUR PENDANT LE PASSÉ. Or cette mémoire est réinjectée dans le
    Monte Carlo résiduel *après* la fusion des PARAM — elle écrasait donc les
    valeurs saisies à l'écran, et toute valorisation en cours de vie priçait aux
    termes du rejeu quoi qu'on saisisse. Mesuré sur un Phoenix : changer le
    coupon de 2 % à 10 % ne déplaçait le prix d'aucun centième, là où la même
    modification vaut +27 points à l'émission.

    C'est fatal pour une variante, dont l'objet même est de changer un PARAM.

    Un PARAM que le script RÉÉCRIT (`SET COUPON = ...`) est une vraie variable
    d'état et doit, lui, survivre au rejeu. Seuls les PARAM jamais réécrits sont
    des termes du contrat, et un terme ne s'hérite pas du passé : il se saisit.
    """
    ecrits = _variables_ecrites(texte)
    termes = {p.name for p in compiled.params} - ecrits
    return {nom: valeur for nom, valeur in (memo or {}).items() if nom not in termes}


def _variables_ecrites(texte: str) -> set:
    """Les variables qu'un script définit — `SET NOM = ...`.

    Lu sur le texte plutôt que sur la forme compilée : `init_fn` et les `fn`
    d'événement sont des callables, leurs noms de variables n'y survivent pas.
    Dans ce DSL, `SET` en tête de ligne est sans ambiguïté."""
    return set(re.findall(r"^\s*SET\s+([A-Za-z_]\w*)", texte or "", re.M))


def _etat_repris_par_la_variante(memo: dict, script_variante: str) -> dict:
    """Ce que la variante fait de l'état accumulé sous les termes d'origine.

    Un avenant qui renomme une variable de mémoire fait disparaître sans un mot
    ce que le client a accumulé — cinq coupons en mémoire, par exemple. Ce n'est
    pas forcément une erreur : abandonner la mémoire est une restructuration
    parfaitement légitime, et fréquente. Impossible de distinguer l'intention
    de l'étourderie ici, donc on ne refuse pas — on RAPPORTE, et l'écran le
    montre à côté du prix. Un fait tu vaut moins qu'un fait affiché."""
    ecrites = _variables_ecrites(script_variante)
    return {nom: {"valeur": valeur, "lu_par_la_variante": nom in ecrites}
            for nom, valeur in (memo or {}).items()}


def _compiler_variante(variant: VariantTerms, p: InLifeProduct,
                       parent: CompiledScript) -> CompiledScript:
    """Le script de la variante, résolu sur le MÊME axe des temps que le parent.

    L'ancrage au strike est non négociable : c'est l'origine de l'axe, et l'état
    repris du rejeu — index, extrema, mémoire — y est exprimé. Résoudre la
    variante sur la date de valorisation décalerait tout son calendrier d'un an
    et neuf mois sans rien signaler."""
    texte = variant.script if variant.script is not None else p.script_snapshot
    calendrier = (variant.constats if variant.constats is not None
                  else (p.market.get("constats") or {}))
    try:
        compile_ = parse_script(texte)
        return resolve_constats(compile_, calendrier, anchor=p.strike_date,
                                currency=p.currency or None)
    except ValueError as e:
        raise ValuationError(f"Script ou calendrier de la variante non exploitables : {e}")
    except (AttributeError, TypeError, KeyError) as e:
        # Un calendrier dans la mauvaise FORME — fréquence en objet plutôt qu'en
        # chaîne, par exemple — ne lève pas ValueError mais AttributeError, et
        # remontait donc en 500 « Internal Server Error » en texte brut. L'écran
        # ne savait même pas le lire : « Unexpected token 'I' ». Un refus doit
        # se lire, surtout celui-là, qui désigne un défaut de l'appelant.
        raise ValuationError(
            f"Calendrier de la variante mal formé ({type(e).__name__}: {e}). "
            f"Attendu une fréquence en chaîne (« 1M »), des dates en YYYY-MM-DD.")


def build_residual(p: InLifeProduct, prices: dict, dates_list: list,
                   T_elapsed: float, asof: date,
                   variant: Optional[VariantTerms] = None) -> Residual:
    """Rejoue le passé sur cours réels et construit le produit résiduel.

    L'historique arrive de l'appelant, en cours NUS : un payoff ne se lit pas
    sur une série ajustée des dividendes. Le cœur ne fait aucune entrée-sortie,
    ce qui le rend testable sans réseau et réutilisable avec un historique
    fourni autrement que par Yahoo.

    Rend un Residual ; lève ValuationError si le produit n'est pas rejouable.
    """
    today = asof
    value_d = p.value_date
    market = p.market
    underlyings_json = list(p.underlyings)
    tickers = [u["ticker"] for u in underlyings_json if u.get("ticker")]
    if not tickers:
        raise ValuationError("Aucun ticker défini sur ce deal")

    try:
        compiled = parse_script(p.script_snapshot)
        # Même origine qu'au booking : un MtM qui recalerait le calendrier
        # sur une autre date ne vaudrait plus le même produit.
        _origin = p.strike_date
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=_origin,
                                    currency=p.currency or None)
    except ValueError as e:
        raise ValuationError(f"Script/calendriers non exploitables pour le MtM résiduel "
                                 f"(deal booké avant la persistance des CONSTAT ?) : {e}")

    # ── Avant le strike : il n'y a pas de passé, et pas encore de S₀ ───
    #
    # Le produit n'a pas commencé. Aucune constatation n'a eu lieu, aucun coupon
    # n'a été versé, aucune barrière n'a pu être franchie — et le niveau initial
    # n'existe pas : il sera constaté à la date de strike.
    #
    # L'axe des temps commence donc à la date de VALORISATION, et le fixing est
    # simulé comme le reste : `T_elapsed` est négatif, ce qui décale les
    # constatations vers l'avenir de l'écart au strike, et `strike_set_t` dit au
    # moteur à quel pas chaque trajectoire fixe SON strike. Le payoff, écrit en
    # pourcentage du strike, se lit ensuite sans rien savoir de tout cela.
    #
    # Cette diffusion-là n'est pas une élégance : elle porte la dispersion du
    # fixing (donc la convexité sous vol locale), l'état de variance atteint à
    # la date de strike sous Heston, et le départ de la courbe de taux
    # d'aujourd'hui plutôt que du strike. Elle donne aussi le delta juste, sans
    # mécanisme dédié — bumper le spot met le fixing à l'échelle avec le reste.
    #
    # L'état rendu est l'état neutre du jour 0, valeur par valeur celui que
    # run_mc prend quand aucun état n'est injecté.
    pre_strike = asof < p.strike_date

    if not dates_list and not pre_strike:
        raise ValuationError("Données historiques vides")

    start_idx = 0
    for i_d, d_str in enumerate(dates_list):
        if d_str <= p.strike_date.isoformat():
            start_idx = i_d
        else:
            break

    user_params = market.get("user_params", {}) or {}
    r_frac = snapshot_rate(market)

    if pre_strike:
        replay = {}
        realized_cfs = []
        start_idx = 0
        state = {
            "memo": {}, "index": 0, "accum": 0.0, "wof_last": 1.0,
            # None = comportement jour 0 de run_mc, cf. _eval_paths : rien
            # d'hérité, rien de neutralisé à la main.
            "wof_min": None, "bof_max": None,
            "s_min": None, "s_max": None, "s_prev": None,
            "realvol_state": None, "fix_state": None,
        }
        return _assembler_residuel(
            p, market, underlyings_json, compiled, variant, T_elapsed, state,
            realized_cfs, [1.0] * len(underlyings_json), {}, prices, dates_list,
            user_params, replay, start_idx, r_frac, pre_strike=True,
            strike_set_t=-T_elapsed)

    replay = eval_script_on_history(
        compiled, dates_list, prices, start_idx, p.tenor, user_params, tickers, r_frac
    )
    if replay is None:
        raise ValuationError("Replay impossible — S₀ introuvable dans l'historique")
    if replay["early_recall"]:
        # The old wording pointed at "refresh the lifecycle", which stopped
        # being actionable when fixings became governed: a refresh only updates
        # INDICATIVE monitoring data and raises a proposal — resolving the deal
        # now requires an official fixing validated by an independent Checker.
        # Telling the user to press a button that cannot unblock them wastes
        # their time and makes the control look broken rather than deliberate.
        # Rappel anticipé détecté : le cœur le signale, l'appelant décide du
        # message et du code HTTP.
        return Residual(early_recall=True, T_actual=replay["T_actual"])
    state = replay["state"]
    # Les termes du contrat ne s'héritent pas du passé, ils se saisissent.
    state["memo"] = _sans_les_param_semes(state.get("memo"), compiled, p.script_snapshot)
    realized_cfs = replay["cash_flows"]

    # Paths start at today's spot in % of strike — the barriers written in %
    # of strike then bite at the right distance without any rescaling.
    s0_map: dict = p.strike_levels
    norm_spots = []
    for u in underlyings_json:
        tk, name = u.get("ticker", ""), u["name"]
        s0 = s0_map.get(name, 0.0)
        series = [float(px) for px in prices.get(tk, []) if px]
        if not (tk and series and s0 > 0):
            raise ValuationError(f"Spot/S₀ manquant pour {name} — compléter l'event Strike")
        norm_spots.append(series[-1] / s0)

    return _assembler_residuel(
        p, market, underlyings_json, compiled, variant, T_elapsed, state,
        realized_cfs, norm_spots, s0_map, prices, dates_list,
        user_params, replay, start_idx, r_frac, pre_strike=False)


def _assembler_residuel(p: InLifeProduct, market: dict, underlyings_json: list,
                        compiled: CompiledScript, variant: Optional[VariantTerms],
                        T_elapsed: float, state: dict, realized_cfs: list,
                        norm_spots: list, s0_map: dict, prices: dict,
                        dates_list: list, user_params: dict, replay: dict,
                        start_idx: int, r_frac: float, pre_strike: bool,
                        strike_set_t: Optional[float] = None) -> Residual:
    """Monte le produit à pricer une fois le passé connu — ou une fois établi
    qu'il n'y en a pas.

    Les deux régimes se rejoignent ici parce qu'à partir de ce point ils sont
    le même exercice : substituer les termes d'une variante, décaler le
    calendrier de `T_elapsed`, conditionner la courbe de dividende. Avant le
    strike `T_elapsed` vaut zéro, donc le décalage et le conditionnement sont
    des identités et le produit à pricer est le produit d'origine."""

    # ── Le point où le passé et l'avenir cessent d'être le même produit ──
    #
    # Jusqu'ici tout a été rejoué sous `compiled`, les termes d'ORIGINE : c'est
    # sous eux que les coupons ont été versés et que le produit n'a pas été
    # rappelé. À partir d'ici on price la vie restante, et une variante peut
    # substituer ses propres termes. Les deux ne se rencontrent jamais.
    pricing = compiled
    texte_px = p.script_snapshot
    calendrier_px = market.get("constats") or {}
    if variant is not None and not variant.est_vide():
        pricing = _compiler_variante(variant, p, compiled)
        _refuser_si_le_passe_diverge(compiled, pricing, T_elapsed)
        if variant.script is not None:
            texte_px = variant.script
        if variant.constats is not None:
            calendrier_px = variant.constats

    residual_events = _shift_events_for_mtf(pricing.events, T_elapsed)
    if not residual_events:
        raise ValuationError("Aucun événement résiduel — vérifier le calendrier du deal")
    # STRIKE_FIX window split at today: past dates (d <= T_elapsed) were replayed
    # on real closes (state["fix_state"]), only strictly-future dates stay on the
    # residual script — no fixing date is ever counted twice.
    residual_fix = [round(d - T_elapsed, 6) for d in (pricing.strike_fix_dates or [])
                    if d > T_elapsed + 1e-9]
    residual_script = CompiledScript(
        events=residual_events, init_fn=pricing.init_fn,
        params=pricing.params, constats=pricing.constats,
        has_stop=pricing.has_stop, monitors=pricing.monitors,
        strike_fix_dates=residual_fix or None,
        strike_fix_reduction=pricing.strike_fix_reduction,
    )

    engine_uls = _engine_underlyings(market, underlyings_json)
    for underlying in engine_uls:
        _shift_dividend_curve(underlying, T_elapsed)

    # Les PARAM de la vie restante. Hors variante, ce sont ceux du rejeu — d'où
    # l'égalité par défaut, qui laisse toute valorisation ordinaire inchangée.
    px_params = user_params
    check, T_res = {}, None
    if pricing is not compiled:
        if variant.user_params is not None:
            px_params = variant.user_params
        check = _etat_repris_par_la_variante(
            state.get("memo"),
            variant.script if variant.script is not None else p.script_snapshot)
        dates = [d for e in residual_events for d in (e.dates or [])]
        T_res = max(dates) if dates else None

    return Residual(
        compiled=compiled, residual_script=residual_script,
        state=state, realized_flows=realized_cfs,
        norm_spots=norm_spots, engine_uls=engine_uls,
        T_elapsed=T_elapsed, r_frac=r_frac,
        prices=prices, dates_list=dates_list,
        user_params=user_params, replay=replay, start_idx=start_idx, s0_map=s0_map,
        residual_user_params=px_params, variant_state_check=check,
        T_residual_max=T_res, pre_strike=pre_strike, strike_set_t=strike_set_t,
        pricing_script_text=texte_px, pricing_constats=calendrier_px,
    )
