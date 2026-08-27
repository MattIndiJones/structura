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


def build_residual(p: InLifeProduct, prices: dict, dates_list: list,
                   T_elapsed: float, asof: date) -> Residual:
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

    if not dates_list:
        raise ValuationError("Données historiques vides")

    start_idx = 0
    for i_d, d_str in enumerate(dates_list):
        if d_str <= p.strike_date.isoformat():
            start_idx = i_d
        else:
            break

    user_params = market.get("user_params", {}) or {}
    r_frac = snapshot_rate(market)

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
    realized_cfs = replay["cash_flows"]

    residual_events = _shift_events_for_mtf(compiled.events, T_elapsed)
    if not residual_events:
        raise ValuationError("Aucun événement résiduel — vérifier le calendrier du deal")
    # STRIKE_FIX window split at today: past dates (d <= T_elapsed) were replayed
    # on real closes (state["fix_state"]), only strictly-future dates stay on the
    # residual script — no fixing date is ever counted twice.
    residual_fix = [round(d - T_elapsed, 6) for d in (compiled.strike_fix_dates or [])
                    if d > T_elapsed + 1e-9]
    residual_script = CompiledScript(
        events=residual_events, init_fn=compiled.init_fn,
        params=compiled.params, constats=compiled.constats,
        has_stop=compiled.has_stop, monitors=compiled.monitors,
        strike_fix_dates=residual_fix or None,
    )

    # Paths start at today's spot in % of strike — the barriers written in %
    # of strike then bite at the right distance without any rescaling.
    s0_map: dict = p.strike_levels
    norm_spots = []
    for u in underlyings_json:
        tk, name = u.get("ticker", ""), u["name"]
        s0 = s0_map.get(name, 0.0)
        series = [float(p) for p in prices.get(tk, []) if p]
        if not (tk and series and s0 > 0):
            raise ValuationError(f"Spot/S₀ manquant pour {name} — compléter l'event Strike")
        norm_spots.append(series[-1] / s0)

    engine_uls = _engine_underlyings(market, underlyings_json)
    for underlying in engine_uls:
        _shift_dividend_curve(underlying, T_elapsed)

    return Residual(
        compiled=compiled, residual_script=residual_script,
        state=state, realized_flows=realized_cfs,
        norm_spots=norm_spots, engine_uls=engine_uls,
        T_elapsed=T_elapsed, r_frac=r_frac,
        prices=prices, dates_list=dates_list,
        user_params=user_params, replay=replay, start_idx=start_idx, s0_map=s0_map,
    )
