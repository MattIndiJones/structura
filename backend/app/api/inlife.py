"""Valorisation en cours de vie depuis le Pricer.

Le Pricer ne savait valoriser qu'à l'émission : toute trajectoire démarrait à
100 % du strike. Impossible d'y répondre à « combien vaut cette note qui a
deux ans de vie ». La seule voie était de booker le produit et de lire son
MtM — un détournement quand il s'agit d'une opportunité de marché secondaire
qu'on ne détient pas.

Ce module ouvre la même machinerie que le MtM des deals (core/inlife_valuation)
à un produit décrit par un formulaire. Le mode ne se choisit pas : il se déduit
de la date de valorisation. Égale à la date de strike, on price à l'émission ;
postérieure, on rejoue le passé sur cours réels et on ne simule que la vie
restante.

Ce qui rend le rejeu indispensable plutôt que confortable : sur un produit à
mémoire ou à barrière déjà touchée, une valorisation repartie de zéro avec le
bon spot serait fausse. Le solde de coupons accumulés et les extrema franchis
FONT partie de la valeur, et aucune simulation ne les reconstitue.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.inlife_valuation import (
    InLifeProduct, ValuationError, build_residual,
)
from ..core.lifecycle_controls import path_dependency_reasons
from ..core.payscript.engine import compute_greeks, run_mc
from ..core.schemas import UnderlyingParams
from ..db.models import User
from ..services.market_data import load_hist_prices
from .auth import get_current_user
from .pricing import _clean_flux

router = APIRouter(prefix="/api", tags=["pricing"])


class InLifePricingRequest(BaseModel):
    """Un produit et la date à laquelle on veut le valoriser."""
    script: str
    underlyings: list[UnderlyingParams]
    corr_matrix: list[list[float]]
    r: float = 0.03
    N: int = Field(default=20000, ge=1000, le=200000)
    model: str = "constant"
    user_params: dict = Field(default_factory=dict)
    constats: dict = Field(default_factory=dict)
    seed: int = 42
    antithetic: bool = True
    # Mêmes leviers de marché que /api/price. Ils manquaient ici : une courbe
    # de taux ou un modèle de taux stochastique saisis à l'écran ne partaient
    # pas, et le prix ne bougeait pas d'un iota quand on les changeait.
    yield_curve: list[list[float]] = Field(default_factory=list)
    # Spread emetteur, actualisation seule. La courbe par piliers l'emporte
    # sur le niveau plat. Sur une valorisation de marche secondaire c'est le
    # levier qui manquait le plus : il explique l'essentiel de l'ecart entre
    # un prix modele sans risque de credit et une fourchette de marche.
    funding_curve: list[list[float]] = Field(default_factory=list)
    funding_spread: float = 0.0
    sigma_r: float = 0.0
    a_r: float = 0.0
    barrier_monitoring: str = "weekly"
    # Sensibilités du MtM. Elles se calculent sur la jambe RÉSIDUELLE, avec
    # l'état du passé injecté : le delta d'un produit dont la barrière est
    # déjà franchie n'a rien à voir avec celui du même produit neuf.
    compute_greeks: bool = False
    selected_greeks: list[str] = Field(default_factory=list)

    strike_date: date
    value_date: date
    maturity_date: date
    payment_date: Optional[date] = None
    # Défaut : la date de strike, c'est-à-dire un pricing à l'émission.
    valuation_date: Optional[date] = None
    settlement_ccy: str = "EUR"

    # Niveau initial constaté par sous-jacent, en absolu. Vide, on prend la
    # clôture NUE à la date de strike — ce que le term sheet appelle le strike.
    strike_levels: dict[str, float] = Field(default_factory=dict)


def _snapshot_underlying(u: UnderlyingParams) -> dict:
    """Un sous-jacent de la requête, rendu dans les unités d'affichage.

    La requête arrive en unités moteur (σ = 0,3427) ; le rejeu reconstruit ses
    sous-jacents depuis un instantané de booking, qui lui est en unités
    d'écran (σ = 34,27). Ce n'est pas élégant, mais c'est le format que
    `_engine_underlyings` sait relire, et il vaut mieux s'y conformer que
    dupliquer sa logique de repli."""
    return {
        "name": u.name, "ticker": u.ticker, "ccy": u.ccy,
        "sigma": u.sigma * 100, "q": u.q * 100,
        "dividendCurve": [{"T": t, "rate": taux * 100} for t, taux in u.dividend_curve],
        "dividendDecay": u.dividend_decay * 100,
        "sigma_fx": u.sigma_fx * 100, "rho_sfx": u.rho_sfx * 100,
        "ccyh": u.ccyh * 10000,
        "v0": u.v0 * 100, "kappa": u.kappa, "theta": u.theta * 100, "xi": u.xi * 100,
        "rho_h": u.rho_h * 100, "rho_rS": u.rho_rS * 100,
        "alpha": u.alpha * 100, "beta": u.beta * 100,
        "rho": u.rho * 100, "nu": u.nu * 100,
        "skew": u.skew * 100, "curvature": u.curvature * 100,
    }


def _closes_at(prices: dict, dates_list: list, jour: str) -> dict:
    """Dernière clôture connue à `jour` pour chaque ticker."""
    idx = -1
    for i, d in enumerate(dates_list):
        if d <= jour:
            idx = i
        else:
            break
    if idx < 0:
        return {}
    return {tk: float(serie[idx]) for tk, serie in prices.items()
            if idx < len(serie) and serie[idx]}


class ResidualContext:
    """Le produit ramené à sa vie restante, prêt pour N'IMPORTE quelle analytique.

    Extrait de `price_in_life` pour que le profil de payoff, les chemins, les
    probabilités, le Mark-to-Future, le solveur et les scénarios voient le même
    produit que le prix. Sans ça chacun price le produit NEUF : sur une note
    dont le worst-of est à 34 % du strike, l'onglet Probabilités annonçait
    39 % de chance de rappel et 2,12 ans de durée espérée pour une vie
    restante de 1,10 an — des chiffres qui décrivent une autre note.

    `mc_kwargs` porte l'état que le rejeu a reconstitué : mémoire de coupons,
    extrema franchis, compteur de constatations. Ce sont des faits ; ils ne
    bougent ni avec un choc ni avec un bump.
    """

    def __init__(self, residuel, valuation, T_elapsed, T_remaining, niveaux,
                 corr_matrix, payment_t, produit=None):
        self.residuel = residuel
        # Le produit d'origine : ses `underlyings` gardent nom et ticker, que la
        # jambe résiduelle ne porte plus.
        self.produit = produit
        self.valuation = valuation
        self.T_elapsed = T_elapsed
        self.T_remaining = T_remaining
        self.niveaux = niveaux
        self.corr_matrix = corr_matrix
        self.payment_t = payment_t

    @property
    def script(self):
        return self.residuel.residual_script

    @property
    def underlyings(self):
        return self.residuel.engine_uls

    @property
    def r(self):
        return self.residuel.r_frac

    @property
    def mc_kwargs(self) -> dict:
        """Les arguments d'état à passer à run_mc pour repartir du bon produit."""
        etat = self.residuel.state
        spots = self.residuel.norm_spots
        return dict(
            spot_mult=spots, spot_base=spots,
            wof_min_init=etat["wof_min"], bof_max_init=etat["bof_max"],
            index_offset=etat["index"], memo_init=etat["memo"],
            accum_init=etat["accum"],
            s_min_init=etat["s_min"], s_max_init=etat["s_max"],
            s_prev_init=etat["s_prev"],
            wof0_init=min(spots) if spots else 1.0,
            realvol_state_init=etat["realvol_state"],
            fix_state_init=etat["fix_state"],
        )

    def sur_axe_residuel(self, courbe):
        """Décale les piliers d'une courbe sur l'axe du MC résiduel."""
        return [[max(0.0, t - self.T_elapsed), niveau]
                for t, niveau in (courbe or []) if t > self.T_elapsed]


def build_request_residual(req) -> ResidualContext:
    """Rejoue le passé d'une requête et rend le contexte résiduel.

    Lève HTTPException(422) avec un motif lisible plutôt que de rendre un
    nombre plausible et faux : valorisation hors de la vie du produit, ticker
    manquant, historique absent sur un payoff dépendant du chemin.
    """
    valuation = req.valuation_date or req.strike_date
    if valuation < req.strike_date:
        raise HTTPException(
            422, f"La date de valorisation ({valuation}) précède la constatation "
                 f"initiale ({req.strike_date}) : il n'y a pas encore de produit.")
    if valuation >= req.maturity_date:
        raise HTTPException(
            422, f"La date de valorisation ({valuation}) atteint la maturité "
                 f"({req.maturity_date}) : il n'y a plus d'optionnalité à valoriser.")

    tickers = [u.ticker for u in req.underlyings if u.ticker]
    if not tickers:
        raise HTTPException(422, "Chaque sous-jacent doit porter un ticker pour "
                                  "qu'on puisse aller chercher son historique.")

    # Fenêtre J-7 avant le strike : une constatation initiale un week-end ou un
    # férié a besoin de la clôture qui la précède.
    debut = (req.strike_date - timedelta(days=7)).isoformat()
    px = load_hist_prices(tickers, debut, valuation.isoformat())
    if "error" in px:
        raise HTTPException(422, px["error"])
    dates_list, prices = px.get("dates", []), px.get("prices", {})
    if not dates_list:
        raise HTTPException(
            422, "Aucun historique sur la période — vérifiez les tickers et la date "
                 "de constatation initiale.")

    # Un payoff qui dépend du chemin ne se reconstitue pas sans historique :
    # mieux vaut refuser que rendre un nombre plausible et faux.
    manquants = [tk for tk in tickers if not prices.get(tk)]
    if manquants:
        chemin = path_dependency_reasons(req.script)
        detail = (f"Historique absent pour {', '.join(manquants)}.")
        if chemin:
            detail += (f" Ce produit dépend du chemin ({', '.join(chemin)}) : sans les "
                       f"cours passés, sa valeur ne peut pas être reconstituée.")
        raise HTTPException(422, detail)

    niveaux = dict(getattr(req, "strike_levels", None) or {})
    if not niveaux:
        au_strike = _closes_at(prices, dates_list, req.strike_date.isoformat())
        for u in req.underlyings:
            niveau = au_strike.get(u.ticker)
            if not niveau:
                raise HTTPException(
                    422, f"Pas de clôture au {req.strike_date} pour {u.ticker} : "
                         f"saisissez le niveau initial du term sheet.")
            niveaux[u.name] = niveau

    market = {
        "constats": req.constats,
        "user_params": req.user_params,
        "r": req.r * 100,
        "model": req.model,
        "antithetic": getattr(req, "antithetic", True),
        # L'instantané complet, en unités d'affichage — c'est ce que
        # _engine_underlyings attend. Ne passer que name/sigma/q laissait
        # retomber sur les défauts la courbe de dividende ET toute la
        # calibration Heston / SABR / Dupire : changer l'une ou l'autre à
        # l'écran ne changeait rien au prix, sans aucun signe.
        "underlyings": [_snapshot_underlying(u) for u in req.underlyings],
    }
    produit = InLifeProduct(
        script_snapshot=req.script,
        underlyings=[{"name": u.name, "ticker": u.ticker, "ccy": u.ccy}
                     for u in req.underlyings],
        strike_levels=niveaux,
        strike_date=req.strike_date,
        value_date=req.value_date,
        tenor=round((req.maturity_date - req.strike_date).days / 365.25, 6),
        currency=(req.settlement_ccy or "").strip().upper(),
        payment_date=req.payment_date,
        market=market,
    )

    T_elapsed = max(0.0, (valuation - req.strike_date).days / 365.25)
    try:
        residuel = build_residual(produit, prices, dates_list, T_elapsed, valuation)
    except ValuationError as exc:
        raise HTTPException(422, str(exc))


    T_remaining = max(1 / 52, (req.maturity_date - valuation).days / 365.25)
    paiement = ((req.payment_date - valuation).days / 365.25
                if req.payment_date else None)
    return ResidualContext(residuel, valuation, T_elapsed, T_remaining, niveaux,
                            getattr(req, "corr_matrix", None), paiement, produit)


@router.post("/price/in-life")
def price_in_life(
    req: InLifePricingRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    ctx = build_request_residual(req)
    residuel = ctx.residuel
    produit = ctx.produit
    valuation = ctx.valuation
    T_elapsed = ctx.T_elapsed
    niveaux = ctx.niveaux

    if residuel.early_recall:
        return {
            "early_recall": True,
            "message": "Le rejeu des cours détecte un rappel anticipé : le produit "
                       "n'était plus vivant à cette date.",
            "T_actual": residuel.T_actual,
            "valuation_date": valuation.isoformat(),
        }

    T_remaining = ctx.T_remaining
    paiement_residuel = ctx.payment_t
    etat = residuel.state
    # Les courbes se lisent sur l'axe du Monte Carlo résiduel, qui démarre à la
    # date de valorisation : leurs piliers sont décalés du temps déjà écoulé,
    # sinon un pilier « 2 ans » du contrat serait relu comme 2 ans après
    # aujourd'hui.
    courbe_residuelle = ctx.sur_axe_residuel(req.yield_curve)
    funding_residuel = ctx.sur_axe_residuel(req.funding_curve)
    try:
        res = run_mc(
            residuel.residual_script, residuel.engine_uls, req.corr_matrix,
            residuel.r_frac, T_remaining,
            maturity_payment_t=paiement_residuel,
            N=req.N, model=req.model, seed=req.seed, antithetic=req.antithetic,
            user_params=residuel.user_params,
            yield_curve=courbe_residuelle,
            funding_curve=funding_residuel, funding_spread=req.funding_spread,
            sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
            spot_mult=residuel.norm_spots, spot_base=residuel.norm_spots,
            wof_min_init=etat["wof_min"], bof_max_init=etat["bof_max"],
            index_offset=etat["index"], memo_init=etat["memo"],
            accum_init=etat["accum"],
            s_min_init=etat["s_min"], s_max_init=etat["s_max"],
            s_prev_init=etat["s_prev"],
            wof0_init=min(residuel.norm_spots),
            realvol_state_init=etat["realvol_state"],
            fix_state_init=etat["fix_state"],
        )
    except ValueError as exc:
        raise HTTPException(422, f"Monte Carlo résiduel impossible : {exc}")

    # Sensibilités du MtM : on bumpe la jambe RÉSIDUELLE, pas le produit neuf.
    # Le rejeu du passé n'est fait qu'une fois et son état est injecté dans
    # chaque jambe bumpée — extrema franchis, mémoire accumulée, compteur de
    # constatations sont des faits, pas des sorties de modèle, et ils ne
    # bougent pas avec le choc. Les spots, eux, sont bumpés autour de leur
    # niveau du jour : un sous-jacent à 34 % du strike est choqué de 1 % de là
    # où il traite, pas de son niveau d'émission.
    greeks: dict = {}
    if req.compute_greeks and req.selected_greeks:
        try:
            greeks = compute_greeks(
                residuel.residual_script, residuel.engine_uls, req.corr_matrix,
                residuel.r_frac, T_remaining, req.N, req.model, seed=req.seed,
                user_params=residuel.user_params, selected=req.selected_greeks,
                sigma_r=req.sigma_r, a_r=req.a_r, yield_curve=courbe_residuelle,
                funding_curve=funding_residuel, funding_spread=req.funding_spread,
                barrier_monitoring=req.barrier_monitoring,
                antithetic=req.antithetic,
                state={
                    "spot_base": residuel.norm_spots,
                    "wof_min": etat["wof_min"], "bof_max": etat["bof_max"],
                    "index": etat["index"], "memo": etat["memo"],
                    "accum": etat["accum"],
                    "s_min": etat["s_min"], "s_max": etat["s_max"],
                    "s_prev": etat["s_prev"],
                    "realvol_state": etat["realvol_state"],
                    "fix_state": etat["fix_state"],
                },
            )
        except ValueError as exc:
            raise HTTPException(422, f"Greeks résiduels impossibles : {exc}")

    perfs = {u["name"]: round(niveau, 6) for u, niveau
             in zip(produit.underlyings, residuel.norm_spots)}

    # L'environnement du moteur mêle les PARAM du script aux variables que le
    # passé a réellement écrites. Les renvoyer ensemble sous le nom de
    # « mémoire » invite à les additionner : sur un Athena, COUPON 8 % +
    # barrière 100 % + barrière 60 % faisaient un solde de 168 % de coupons
    # accumulés, sur un produit qui en vaut 75. Seules les variables écrites
    # après la constatation initiale sont un état.
    noms_params = {p.name for p in (residuel.compiled.params if residuel.compiled else [])}
    etat_repris = {k: v for k, v in etat["memo"].items() if k not in noms_params}
    return {
        "price": res["price"],
        "ic95": res["ic95"],
        # Les mêmes statistiques que /api/price. Elles ne partaient pas d'ici,
        # si bien que médiane, VaR, P(retour > 100 %), spread inter-quartile,
        # temps de calcul et distribution des payoffs restaient à « — » sur
        # toute valorisation en cours de vie.
        "median": res["median"],
        "var5": res["var5"],
        "prob_gt100": res["prob_gt100"],
        "payoffs": res["payoffs"],
        "elapsed_ms": res["elapsed_ms"],
        "greeks": greeks,
        "n_paths": res["n_paths"],
        # Horizon effectivement simulé — la vie restante, pas la maturité
        # d'origine : c'est lui qui donne son échelle à l'écran.
        "t_max_effective": round(T_remaining, 4),
        # Même mise en forme que /api/price : sans elle la table part brute,
        # sans facteur d'actualisation, et la colonne DF de l'écran reste vide
        # — on ne peut plus expliquer le prix ligne à ligne, ce qui est
        # précisément ce qu'on attend d'une valorisation en cours de vie.
        "flux_table": _clean_flux(res["flux_table"]),
        "n_eff": res["n_eff"],
        "fugit": res.get("fugit"),
        "valuation_date": valuation.isoformat(),
        "in_life": T_elapsed > 0,
        # De quoi écrire le bandeau d'état sans le recalculer côté écran.
        "past": {
            "years_elapsed": round(T_elapsed, 4),
            "years_remaining": round(T_remaining, 4),
            "observations_done": etat["index"],
            "realized_flows": residuel.realized_flows,
            "memory": etat_repris,
            "worst_of": round(min(residuel.norm_spots), 6) if residuel.norm_spots else None,
            "performances": perfs,
            "strike_levels": niveaux,
        },
    }


class ImpliedFundingRequest(InLifePricingRequest):
    """La même valorisation, mais à l'envers : on donne le prix, on cherche le
    spread émetteur qui le reproduit."""
    # Prix cible en fraction de nominal — 0.45065 pour un bid à 450,65 sur
    # 1 000. C'est le chiffre du marché, pas un pourcentage d'écran.
    target_price: float = Field(..., gt=0.0, lt=10.0)
    lo: float = Field(default=-0.02, ge=-0.10, le=0.50)
    hi: float = Field(default=0.30, ge=-0.10, le=1.00)
    tol: float = Field(default=1e-4, gt=0.0)
    max_iter: int = Field(default=30, ge=5, le=80)


@router.post("/price/implied-funding")
def implied_funding(
    req: ImpliedFundingRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Spread émetteur implicite d'un prix de marché.

    La question qu'on se pose vraiment devant une opportunité de secondaire
    n'est pas « que vaut cette note pour moi » mais « à quel spread le marché
    la traite-t-il ». C'est le même calcul dans l'autre sens : le prix décroît
    de façon monotone avec le spread — il n'entre que dans l'actualisation,
    donc chaque flux positif ne peut que baisser — ce qui rend la bissection
    sûre, sans risque de racine multiple.

    Les autres hypothèses (vol, dividendes, corrélation, courbe de taux) sont
    celles de la requête : le spread rendu absorbe donc TOUT ce que le modèle
    ne capture pas, smile en tête. C'est un spread implicite au sens propre,
    pas une mesure de crédit pure — et il faut le lire comme tel.
    """
    def prix(spread: float) -> float:
        sonde = req.model_copy(update={"funding_spread": spread,
                                        "funding_curve": [],
                                        "compute_greeks": False,
                                        "selected_greeks": []})
        res = price_in_life(InLifePricingRequest(**sonde.model_dump(
            exclude={"target_price", "lo", "hi", "tol", "max_iter"})), current)
        if res.get("early_recall"):
            raise HTTPException(422, res["message"])
        return res["price"]

    lo, hi = req.lo, req.hi
    p_lo, p_hi = prix(lo), prix(hi)
    if not (min(p_lo, p_hi) <= req.target_price <= max(p_lo, p_hi)):
        raise HTTPException(
            422,
            f"Prix cible {req.target_price:.4f} hors d'atteinte : le spread varie "
            f"de {lo:+.2%} à {hi:+.2%} pour un prix de {p_lo:.4f} à {p_hi:.4f}. "
            f"Élargissez les bornes, ou revoyez les hypothèses de marché — un "
            f"prix inatteignable par le seul crédit dit que c'est ailleurs que "
            f"le modèle s'écarte.")

    iterations = []
    for _ in range(req.max_iter):
        mid = 0.5 * (lo + hi)
        p_mid = prix(mid)
        iterations.append({"spread": round(mid, 6), "price": round(p_mid, 6)})
        if abs(p_mid - req.target_price) < req.tol:
            break
        # Monotone décroissant : au-dessus de la cible, il faut plus de spread.
        if (p_mid > req.target_price) == (p_lo > p_hi):
            lo = mid
        else:
            hi = mid

    dernier = iterations[-1]
    return {
        "funding_spread": dernier["spread"],
        "price": dernier["price"],
        "target_price": req.target_price,
        "residual": round(dernier["price"] - req.target_price, 8),
        "converged": abs(dernier["price"] - req.target_price) < req.tol,
        "iterations": iterations,
        "valuation_date": (req.valuation_date or req.strike_date).isoformat(),
    }
