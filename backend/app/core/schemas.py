import math

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import date


class UnderlyingParams(BaseModel):
    name: str = "Underlying"
    ticker: str = ""
    ccy: str = "EUR"
    sigma: float = 0.20
    q: float = 0.02
    # Optional piecewise-constant annual dividend-yield curve. Each node is
    # [bucket_end_years, annual_yield] in engine units (0.02 = 2%). The scalar
    # q remains the first-year / legacy flat assumption; an empty curve keeps
    # the historical pricing path exactly unchanged.
    dividend_curve: List[List[float]] = Field(default_factory=list)
    dividend_decay: float = Field(default=0.0, ge=0.0, le=1.0)
    sigma_fx: float = 0.0
    rho_sfx: float = 0.0
    ccyh: float = 0.0
    # Heston
    v0: float = 0.04
    kappa: float = 2.0
    theta: float = 0.04
    xi: float = 0.35
    rho_h: float = -0.70
    rho_rS: float = 0.0
    # SABR
    alpha: float = 0.20
    beta: float = 0.50
    rho: float = -0.30
    nu: float = 0.40
    # Dupire local vol
    skew: float = 0.0
    curvature: float = 0.0

    @field_validator("dividend_curve")
    @classmethod
    def validate_dividend_curve(cls, curve: List[List[float]]) -> List[List[float]]:
        previous_q = math.inf
        normalized: List[List[float]] = []
        for index, node in enumerate(curve, start=1):
            if len(node) != 2:
                raise ValueError("Chaque nœud de dividende doit contenir [maturité, taux].")
            maturity, rate = float(node[0]), float(node[1])
            if not (math.isfinite(maturity) and math.isfinite(rate)):
                raise ValueError("La courbe de dividende contient une valeur non finie.")
            if abs(maturity - index) > 1e-9:
                raise ValueError(
                    "La courbe de dividende doit utiliser des buckets annuels consécutifs "
                    "1A, 2A, 3A, etc."
                )
            if rate < 0.0:
                raise ValueError("Un rendement de dividende ne peut pas être négatif.")
            if rate > previous_q + 1e-12:
                raise ValueError("La courbe de dividende dégressive doit être non croissante.")
            normalized.append([maturity, rate])
            previous_q = rate
        return normalized


class PricingRequest(BaseModel):
    script: str
    underlyings: List[UnderlyingParams]
    corr_matrix: List[List[float]]
    r: float = 0.03
    T: float = 3.0
    N: int = Field(default=20000, ge=1000, le=200000)
    seed: int = 42
    model: str = "constant"
    antithetic: bool = True
    user_params: Dict[str, Any] = {}
    compute_greeks: bool = False
    selected_greeks: List[str] = ["delta", "gamma", "vega", "theta", "rho"]
    yield_curve: List[List[float]] = []
    # Spread emetteur : il n'entre QUE dans l'actualisation, jamais dans le
    # drift. La courbe par piliers l'emporte sur le niveau plat quand elle est
    # fournie. Voir engine._funding_df_arr.
    funding_curve: List[List[float]] = []
    funding_spread: float = Field(default=0.0, ge=-0.05, le=0.50)
    sigma_r: float = Field(default=0.0, ge=0.0, le=0.10)
    a_r: float = Field(default=0.0, ge=0.0, le=2.0)
    # Barrier monitoring: "weekly" (extrema at the weekly grid steps, historic
    # behaviour) or "continuous" (Brownian-bridge within-step extrema — WOF_MIN/
    # S_MIN/BOF_MAX then reflect the continuous path, raising KI probability).
    barrier_monitoring: str = Field(default="weekly", pattern="^(weekly|continuous)$")
    # CONSTAT values, keyed by name — see core/payscript/parser.resolve_constats.
    # Empty dict is a no-op (the common/simple-mode case: no AT<ConstatName>:).
    constats: Dict[str, Any] = {}
    # Date the calendar's year-fractions are measured from — the product's own
    # t=0, i.e. its value date. None keeps the historic default (today), which
    # is only right for a same-day settlement. Callers that know the value date
    # must send it: api/deals.py already anchors a booked deal's replay on
    # deal.value_date, so a pre-trade price left on today's anchor resolves the
    # same calendar into different year fractions than the very same deal once
    # booked — the two prices then differ for no economic reason.
    anchor: Optional[date] = None
    # Settlement currency: names the business-day calendar the CONSTAT dates are
    # rolled onto and the settlement lags counted in. None leaves every date raw
    # and every flow paid at its observation.
    settlement_ccy: Optional[str] = None
    # The product's own payment date — when the final redemption's cash moves.
    # From the term sheet, never derived from a fixing. None pays at maturity.
    payment_date: Optional[date] = None
    # Where the initial level is fixed, and therefore where the diffusion
    # starts. When given it becomes the time axis' origin, in place of `anchor`.
    strike_date: Optional[date] = None
    # When the cash is exchanged between counterparties. The quoted price is the
    # amount that moves on that date, so it is the date the PV is expressed at.
    value_date: Optional[date] = None


class PricingResponse(BaseModel):
    price: float
    ic95: List[float]
    median: float
    var5: float
    prob_gt100: float
    payoffs: List[float]
    flux_table: Dict[str, Any]
    greeks: Dict[str, Any]
    elapsed_ms: float
    n_paths: int
    n_eff: int
    status: str = "ok"
    errors: Optional[str] = None
    # Actual simulation horizon used — may exceed the requested T if the
    # script's (possibly CONSTAT-resolved) event dates run past it.
    # See core/payscript/parser.effective_T_max.
    t_max_effective: float = 0.0
    fugit: Optional[float] = None
    # Ce qu'une fenêtre de constatation a réellement pesé : points de grille
    # retenus contre points demandés, par constatation. Une alerte générique se
    # clique sans lire ; un décompte se lit — et c'est la seule façon de voir
    # qu'une fenêtre trop courte pour la grille hebdomadaire n'a pas moyenné.
    constatation_windows: Optional[List[Dict[str, Any]]] = None


class ParseRequest(BaseModel):
    script: str


class ParseResponse(BaseModel):
    ok: bool
    params: List[Dict[str, Any]]
    constats: List[Dict[str, Any]] = []
    events_count: int
    has_stop: bool = False
    # M_-prefixed PARAMs and how the script compares them — see
    # payscript/parser._analyze_monitors. [{name, observable, direction}].
    monitors: List[Dict[str, Any]] = []
    errors: Optional[str] = None


# ── Analytics request/response models ──────────────────────────────

class VariantOverrides(BaseModel):
    """Les termes d'un avenant — ce qui remplace le parent à partir d'aujourd'hui.

    Déclaré ici plutôt que dans l'API pour que le prix ET les analytiques
    puissent le porter : une variante que seul le prix connaîtrait ferait
    décrire au profil de payoff et aux probabilités le produit d'ORIGINE, sous
    un prix d'avenant. C'est précisément l'écart qu'on a passé la session à
    fermer partout ailleurs."""
    script: Optional[str] = None
    user_params: Optional[Dict[str, Any]] = None
    constats: Optional[Dict[str, Any]] = None
    mode: str = "avenant"


class AnalysisBase(BaseModel):
    """Shared fields for profile / paths / proba / backtest / mtf requests."""
    script: str
    underlyings: List[UnderlyingParams]
    corr_matrix: List[List[float]]
    r: float = 0.03
    T: float = 3.0
    seed: int = 42
    model: str = "constant"
    user_params: Dict[str, Any] = {}
    yield_curve: List[List[float]] = []
    sigma_r: float = Field(default=0.0, ge=0.0, le=0.10)
    a_r: float = Field(default=0.0, ge=0.0, le=2.0)
    barrier_monitoring: str = Field(default="weekly", pattern="^(weekly|continuous)$")
    constats: Dict[str, Any] = {}
    # See PricingRequest.anchor — every analytic derived from a script must
    # resolve its calendar the same way the price did, or the profile/probas/
    # stress grid describe a product on a different schedule than the one priced.
    anchor: Optional[date] = None
    # Le reste du contexte de marché, pour la meme raison. Il manquait ici : un
    # CONSTAT portant un decalage de reglement faisait echouer TOUTES les
    # analytiques (profil, chemins, probas, MtF, backtest, solveur, grille,
    # scenarios) avec « un decalage de reglement suppose un calendrier », alors
    # que le prix, lui, passait. Sans devise, resolve_constats n'a aucun
    # calendrier de jours ouvres sur lequel compter le decalage.
    settlement_ccy: Optional[str] = None
    # Avenant : les termes qui ne valent que pour la vie restante. Portés ici
    # pour que le profil, les chemins, les probabilités et le MtF décrivent la
    # MÊME variante que le prix.
    variant: Optional[VariantOverrides] = None
    strike_date: Optional[date] = None
    value_date: Optional[date] = None
    payment_date: Optional[date] = None
    # Postérieure au strike, l'analytique se calcule sur la VIE RESTANTE, avec
    # l'état du passé injecté — comme le prix. Sans elle, une note dont le
    # worst-of est à 34 % du strike était analysée comme si on l'émettait
    # aujourd'hui à 100 %.
    valuation_date: Optional[date] = None
    maturity_date: Optional[date] = None
    # Spread emetteur : une analytique qui l'ignore décrit un produit moins
    # risque que celui qu'on price.
    funding_curve: List[List[float]] = []
    funding_spread: float = Field(default=0.0, ge=-0.05, le=0.50)


class ProfileRequest(AnalysisBase):
    pass


class PathsRequest(AnalysisBase):
    N_stat: int = Field(default=500, ge=50, le=5000)
    N_display: int = Field(default=50, ge=10, le=200)


class ProbaRequest(AnalysisBase):
    N: int = Field(default=5000, ge=1000, le=20000)


class BacktestRequest(AnalysisBase):
    start_date: str = "2010-01-01"
    end_date: Optional[str] = None
    freq: int = Field(default=21, ge=1, le=252)
    invest_pct: float = Field(default=100.0, gt=0, le=200)
    rf_rate: float = 2.0


class BacktestCompareRequest(BaseModel):
    """Underlying comparator — backtest the same script against a pool of
    candidate underlyings, one at a time, then (if basket_size > 1) against
    combinations drawn from the best `shortlist_n` single performers only —
    testing every C(N, basket_size) combination is combinatorially
    infeasible for any non-trivial candidate pool."""
    script: str
    candidates: List[UnderlyingParams]
    r: float = 0.03
    T: float = 3.0
    model: str = "constant"
    user_params: Dict[str, Any] = {}
    constats: Dict[str, Any] = {}
    anchor: Optional[date] = None   # see PricingRequest.anchor
    basket_size: int = Field(default=1, ge=1, le=5)
    shortlist_n: int = Field(default=8, ge=2, le=20)
    start_date: str = "2010-01-01"
    end_date: Optional[str] = None
    freq: int = Field(default=21, ge=1, le=252)
    invest_pct: float = Field(default=100.0, gt=0, le=200)
    rf_rate: float = 2.0


class MtfRequest(AnalysisBase):
    """Mark-to-Future — nested Monte Carlo. main_price is the t=0 fair price
    (% of notional, from a prior /price call), used as the P(MTM >= P0) threshold."""
    main_price: float
    n_outer: int = Field(default=200, ge=20, le=2000)
    n_inner: int = Field(default=500, ge=50, le=5000)
    n_dates: int = Field(default=5, ge=2, le=12)


class ScriptGenerateRequest(BaseModel):
    """Assistant de scripting : une description en français -> un script PayScript.

    Le modèle écrit une STRUCTURE. Il ne price pas et ne fixe aucun niveau que
    l'utilisateur n'a pas donné — le moteur Monte-Carlo reste seul juge du prix.
    `underlyings` / `r` / `T` ne servent qu'au contexte du prompt et au pricing
    de contrôle qui vérifie que le script produit tourne vraiment."""
    description: str = Field(min_length=3, max_length=4000)
    provider: str = "ollama"
    model: Optional[str] = None
    underlyings: List[UnderlyingParams] = []
    corr_matrix: List[List[float]] = []
    r: float = 0.03
    T: float = 3.0
    user_params: Dict[str, Any] = {}
    # Affinage : repart du script courant au lieu de tout réécrire.
    current_script: str = ""
    refine: bool = False


class MtfDrilldownRequest(AnalysisBase):
    """Explication détaillée de quelques scénarios à UNE date de l'éventail MTF.

    n_outer / n_inner / n_dates / seed doivent reprendre ceux du run à expliquer :
    ils fixent les tirages (le rang de la date indexe le RNG interne), donc c'est
    ce qui garantit que le mark du panneau est exactement celui du graphique.
    scenario_ids sont des indices dans les tableaux `pvs` / `alive` de la réponse
    /api/mtf — le client sélectionne lui-même ses quantiles, ce qui évite de
    recalculer tout l'éventail pour en expliquer cinq trajectoires."""
    main_price: float
    t: float
    scenario_ids: List[int] = Field(min_length=1, max_length=12)
    labels: List[str] = []
    n_outer: int = Field(default=200, ge=20, le=2000)
    n_inner: int = Field(default=500, ge=50, le=5000)
    n_dates: int = Field(default=5, ge=2, le=12)


class SolverRequest(AnalysisBase):
    """Solve for the script PARAM value that hits a target price (bisection).
    target_price/lo/hi are in the PARAM's stored units (fraction for % params)."""
    param_name: str
    target_price: float
    lo: float
    hi: float
    N: int = Field(default=8000, ge=1000, le=50000)
    tol: float = Field(default=1e-4, gt=0, le=0.01)
    max_iter: int = Field(default=40, ge=5, le=100)


class ReinvestCandidate(BaseModel):
    ticker: str
    name: str = ""


class ReinvestMetricFilter(BaseModel):
    """One risk guardrail on the candidate scan — a hard cutoff, not a
    weight: candidates violating it are dropped before the coupon ranking,
    never just penalized. metric is one of ki/autocall/capital_loss/full_coupon
    (the *_pct fields returned by /pricing/proba). direction "max" means the
    metric must not exceed threshold; "min" means it must not fall below it."""
    metric: str = Field(pattern="^(ki|autocall|capital_loss|full_coupon)$")
    threshold: float = Field(ge=0, le=100)
    direction: str = Field(pattern="^(max|min)$")


class ReinvestScanRequest(BaseModel):
    """Flow B — scan a pool of candidate underlyings for the deal's own script:
    solve each candidate's coupon (or whichever PARAM) to par, price its risk
    profile, keep only those passing every filter, rank the rest by coupon.
    target_price/lo/hi are in the PARAM's stored units, same convention as
    SolverRequest (the frontend converts display % to stored units before
    calling, exactly like the existing Solver panel does)."""
    candidates: List[ReinvestCandidate]
    param_name: str
    target_price: float
    lo: float
    hi: float
    filters: List[ReinvestMetricFilter] = []
    N: int = Field(default=6000, ge=1000, le=20000)
    model: str = "constant"
    vol_period: str = "1y"
    # Maturité du scan — None = tenor d'origine du deal (deal.T). Bissection
    # tenue sur param_name uniquement ; param_overrides (mode avancé) fixe
    # tout autre PARAM à une valeur choisie plutôt qu'à celle du booking,
    # en unités stockées (même convention que lo/hi/target_price).
    T: Optional[float] = None
    param_overrides: Dict[str, Any] = {}


class ReinvestProposalRequest(BaseModel):
    """A single scanned candidate turned into a proposal: same conventions
    as ReinvestScanRequest (one candidate instead of a pool), plus a backtest
    window. Re-derives price/proba server-side rather than trusting
    client-echoed scan-result figures for a document."""
    ticker: str
    name: str = ""
    param_name: str
    target_price: float
    lo: float
    hi: float
    T: Optional[float] = None
    param_overrides: Dict[str, Any] = {}
    N: int = Field(default=8000, ge=1000, le=20000)
    model: str = "constant"
    vol_period: str = "1y"
    backtest_start: str = "2015-01-01"
    backtest_freq: int = Field(default=21, ge=1, le=252)
    backtest_invest_pct: float = Field(default=100.0, gt=0, le=200)


class GridRequest(AnalysisBase):
    """2D price heatmap over two script PARAM ranges (stored units)."""
    param_x: str
    x_min: float
    x_max: float
    x_steps: int = Field(default=9, ge=2, le=15)
    param_y: str
    y_min: float
    y_max: float
    y_steps: int = Field(default=9, ge=2, le=15)
    N: int = Field(default=4000, ge=500, le=20000)


class ScenarioRequest(AnalysisBase):
    """Stress grid — price under combined spot x vol shocks (market data, not
    script PARAMs). spot_shocks are multiplicative fractions (e.g. -0.10 = -10%
    spot), vol_shocks are additive fractions (e.g. 0.05 = +5pp vol)."""
    spot_shocks: List[float] = Field(
        default=[-0.30, -0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20, 0.30],
        min_length=1, max_length=15)
    vol_shocks: List[float] = Field(
        default=[0.10, 0.05, 0.0, -0.05, -0.10],
        min_length=1, max_length=15)
    N: int = Field(default=2000, ge=300, le=20000)


class BusinessDayRequest(BaseModel):
    """Resolve one date against a settlement calendar.

    Serves the two things a UI needs and cannot compute itself: moving a typed
    date onto a business day according to a chosen convention, and proposing a
    date N business days after another one (a settlement lag)."""
    date: str
    currency: str = "EUR"
    convention: str = Field(
        default="none",
        pattern="^(following|modified_following|preceding|modified_preceding|none)$")
    # Applied BEFORE the convention: the lag lands on a business day by
    # construction, the convention then has nothing left to move.
    business_days: int = Field(default=0, ge=0, le=60)


class ScheduleRequest(BaseModel):
    """CONSTAT()/CONSTAT()() calendar generation — "expert mode", independent
    of any script. Dates are ISO strings (YYYY-MM-DD); frequency/sub_frequency
    are tenor strings (e.g. "3M", "1W", "1Y", "1D")."""
    start_date: str
    end_date: str
    roll_date: str
    frequency: str
    stub: str = Field(default="short_last",
                       pattern="^(short_first|short_last|long_first|long_last)$")
    sub_frequency: Optional[str] = None
    # Settlement currency: names the business-day calendar the dates are rolled
    # onto. None leaves the grid on raw calendar dates — a preview of what the
    # tenor produces, not of what the product observes.
    currency: Optional[str] = None
    # Business days between an observation and the movement of its cash.
    settlement_lag: int = Field(default=0, ge=0, le=30)
    convention: str = Field(
        default="modified_following",
        pattern="^(following|modified_following|preceding|modified_preceding|none)$")


class PeriodWindowPreviewRequest(BaseModel):
    """Aperçu d'une fenêtre de PÉRIODE : combien de constatations le calendrier
    produit, et combien de relevés chacune moyenne.

    C'est la question que se pose l'utilisateur en saisissant « 1Y » et « 3M » :
    ai-je bien 3 constatations de 4 relevés, ou 12 observations ?"""
    start_date: str
    end_date: str
    roll_date: str
    frequency: str
    window_frequency: str
    stub: str = Field(default="short_last",
                       pattern="^(short_first|short_last|long_first|long_last)$")
    currency: Optional[str] = None
    convention: str = Field(
        default="none",
        pattern="^(following|modified_following|preceding|modified_preceding|none)$")


class WindowPreviewRequest(BaseModel):
    """Aperçu d'une fenêtre de constatation : les dates qu'elle retient
    vraiment, avant tout pricing.

    L'écran saisit une LONGUEUR en jours ouvrés ; un term sheet dit « du 10 au
    20 septembre ». Les deux ne tombent pas au même endroit — 10 jours ouvrés à
    partir du 10/09 vont jusqu'au 23, parce qu'ils sautent deux week-ends. Faire
    la conversion de tête est une source d'erreur silencieuse : cet aperçu la
    supprime en montrant la première date, la dernière et le compte."""
    date: str
    window_length: str
    window_frequency: str = "1D"
    # La fenêtre de départ (STRIKE_FIX) part de sa date vers l'avant ; toute
    # autre arrive à la sienne.
    forward: bool = False
    currency: Optional[str] = None
    convention: str = Field(
        default="none",
        pattern="^(following|modified_following|preceding|modified_preceding|none)$")
