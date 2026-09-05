"""Harnais de bit-identité — valeurs figées, à ne jamais retoucher.

Ces prix ont été capturés sur le moteur intact (commit 4f7bffc) avant les
chantiers de fiabilisation quantitative. Ils couvrent le cas d'usage dominant :
**pas de courbe de taux, pas d'état lifecycle**. Toute correction du moteur doit
laisser ces nombres strictement inchangés — un écart, même au sixième chiffre,
signale une régression sur le chemin nominal, pas une amélioration.

Si un test de ce fichier casse, la question n'est jamais « faut-il mettre à jour
la valeur ? » mais « qu'est-ce qui a bougé et pourquoi ? ». Les seules raisons
légitimes de modifier un littéral ici sont un changement délibéré et documenté de
convention de pricing, ou un changement de version de numpy qui déplacerait le
flux de nombres aléatoires — dans les deux cas, en le disant explicitement.

L'égalité est stricte : `run_mc` renvoie déjà `round(price, 6)`, donc comparer à
six décimales est exactement ce que voient les appelants.

Les paires (T, N) sont choisies pour que `ts != N` (T=1 → ts=52, N=2000). Un
tableau de taux mal formé — (ts,) au lieu de (ts,1) — lève alors une erreur de
broadcast au lieu de se propager silencieusement sur le mauvais axe.
"""
import pytest

from backend.app.core.payscript.parser import parse_script, CompiledScript
from backend.app.core.payscript.engine import run_mc, compute_greeks, _shift_events_for_mtf

UL = dict(name="S1", ticker="", ccy="EUR",
          sigma=0.20, q=0.01, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
          alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
CORR = [[1.0]]
T = 1.0
N = 2000

CALL = """
PARAM K = 1.0 "strike"

AT MATURITY
  PAY MAX(S[1] - K, 0) "call"
"""

AUTOCALL = """
PARAM CPN = 5%   "coupon"
PARAM AC = 100%  "barriere autocall"

AT 0.25, 0.5, 0.75, 1
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
"""

ASIAN = """
AT MATURITY
  SET STRIKE = FIX_AVG
  PAY WOF / STRIKE "perf vs strike moyen"
"""

BARRIER = """
PARAM KI = 70%  "barriere KI"

AT MATURITY
  SET T_KI = INDIC(S_MIN[1] < KI)
  PAY (1 - T_KI) * 1 + T_KI * WOF "remboursement"
"""


def _price(script_text, *, model="constant", antithetic=True, curve=None,
           sigma_r=0.0, a_r=0.0, monitoring="weekly", user_params=None,
           compiled=None):
    cs = compiled if compiled is not None else parse_script(script_text)
    return run_mc(cs, [dict(UL)], CORR, r=0.03, T_max=T, N=N, model=model,
                  seed=42, antithetic=antithetic, user_params=user_params or {},
                  yield_curve=curve or [], sigma_r=sigma_r, a_r=a_r,
                  barrier_monitoring=monitoring)["price"]


# ── G1 — les cinq modèles, avec et sans antithétique ────────────────────────

# Les quatre valeurs localvol/lsv ont été déplacées le 03/09/2026, et c'est le
# seul motif que ce fichier admet : une correction délibérée et documentée.
#
# `UL` ne porte ni skew ni curvature — la nappe implicite y est donc PLATE à
# 20 %, cas où la vol locale de Dupire vaut 20 % partout par identité, et où
# localvol doit rendre EXACTEMENT le prix de la vol constante. Il ne le rendait
# pas : 0,087306 contre 0,087814, soit −0,58 %. L'inversion par différences
# finies sur prix Black-Scholes approchait ∂C/∂T par une différence avant sur un
# pas atteignant 23 % de la maturité et divisait par un ∂²C/∂K² minuscule dans
# les ailes — jusqu'à 150 % de vol locale rendue à K = 60 %, T = 3 mois.
# Reformulée en variance totale (Gatheral 1.10), la calibration rétablit
# l'identité au dernier chiffre : localvol == constant ci-dessous, à tout N.
# Voir test_dupire_calibration.py, qui exige l'identité plutôt qu'une valeur.
#
# lsv bouge par conséquence — sa cible de vol locale a changé. Son écart à la
# vol constante reste du bruit Monte Carlo (+1,21 % à N=2000, +0,06 % à 40 000),
# pas un biais : la leverage y est bien conditionnée par E[V|S].
GOLDEN_MODELES = {
    ("constant", True):  0.087814,
    ("constant", False): 0.083430,
    ("heston",   True):  0.085594,
    ("heston",   False): 0.082602,
    ("sabr",     True):  0.090228,
    ("sabr",     False): 0.086724,
    ("localvol", True):  0.087814,   # == constant, et ce n'est pas un hasard
    ("localvol", False): 0.083430,   # == constant
    ("lsv",      True):  0.088875,
    ("lsv",      False): 0.084951,
}


@pytest.mark.parametrize("model,antithetic", sorted(GOLDEN_MODELES))
def test_prix_inchanges_sans_courbe_tous_modeles(model, antithetic):
    """Un call ATM à taux plat, pour chaque modèle de diffusion et chaque mode
    de réduction de variance. C'est le chemin qu'emprunte l'immense majorité des
    pricings : il ne doit strictement pas bouger."""
    assert _price(CALL, model=model, antithetic=antithetic,
                  user_params={"K": 1.0}) == GOLDEN_MODELES[(model, antithetic)]


# ── G2 — produits à observations (et pas seulement AT MATURITY) ─────────────

def test_prix_inchange_produit_a_barriere():
    """Une barrière KI exerce l'accumulation des extrema courants sur S[1:] et
    la lecture de S_MIN — un chemin d'évaluation distinct du simple payoff
    terminal."""
    assert _price(BARRIER) == 0.952048


def test_prix_inchange_produit_a_barriere_heston():
    """Même produit sous vol stochastique : la barrière lit les extrema d'une
    trajectoire dont la variance évolue, ce qui met en jeu le schéma QE."""
    assert _price(BARRIER, model="heston") == 0.939478


def test_prix_inchange_autocall():
    """Un autocall exerce STOP, INDEX et le drapeau `done` par trajectoire —
    toute la machinerie d'arrêt anticipé."""
    assert _price(AUTOCALL) == 1.037357


# ── G3 — taux stochastiques ────────────────────────────────────────────────
#
# Seules valeurs de ce fichier à avoir été rebasées, et pour une raison
# documentée : l'ajout du terme de convexité de Hull-White (φ(t)). Le facteur
# de taux était écrit centré, ce qui semblait ajuster la courbe gratuitement —
# mais l'actualisation étant exp(-∫r), l'inégalité de Jensen faisait sortir
# E[exp(-∫x)] = exp(+Var/2) > 1 : toutes les obligations ressortaient trop
# chères, de 164 bp sur un zéro-coupon 5 ans à 3 % de vol de taux. Le modèle
# reprice désormais sa propre courbe à moins de 0,25 bp, bruit Monte Carlo
# compris.
#
# Ces quatre nombres ne doivent plus bouger.

GOLDEN_TAUX_STOCH = {
    ("flat",  0.0): 0.087963,
    ("flat",  0.3): 0.087937,
    ("curve", 0.0): 0.083178,
    ("curve", 0.3): 0.083152,
}
COURBE = [[0.5, 0.01], [1.0, 0.02], [3.0, 0.035]]


@pytest.mark.parametrize("forme,a_r", sorted(GOLDEN_TAUX_STOCH))
def test_prix_inchanges_taux_stochastique(forme, a_r):
    """Facteur de taux gaussien, sans (a_r=0) et avec (a_r=0.3) retour à la
    moyenne, sur courbe plate puis sur courbe pentue."""
    curve = COURBE if forme == "curve" else None
    assert _price(CALL, curve=curve, sigma_r=0.015, a_r=a_r,
                  user_params={"K": 1.0}) == GOLDEN_TAUX_STOCH[(forme, a_r)]


# ── G4 — transport de l'état lifecycle ─────────────────────────────────────

def test_prix_inchange_etat_residuel_complet():
    """Les douze paramètres d'état d'un deal vivant, transmis ensemble comme le
    fait `_mtm_core` : spot courant, extrema réalisés, index d'observation,
    coupons mémoire, accumulateur, fixings précédents et variance réalisée.
    Rendre les Greeks stateful ne doit pas déplacer le MtM lui-même."""
    cs = parse_script(AUTOCALL)
    residuel = CompiledScript(events=_shift_events_for_mtf(cs.events, 0.5),
                              init_fn=cs.init_fn, params=cs.params,
                              constats=cs.constats, has_stop=cs.has_stop)
    prix = run_mc(
        residuel, [dict(UL)], CORR, r=0.03, T_max=0.5, N=N, model="constant",
        seed=42, antithetic=True, user_params={},
        spot_mult=[1.15], wof_min_init=[0.92], bof_max_init=[1.30],
        index_offset=2, memo_init={"MISSED": 1}, accum_init=0.03,
        s_min_init=[0.88], s_max_init=[1.31], s_prev_init=[1.10],
        wof0_init=1.15,
        realvol_state_init={"sumsq": 0.02, "t": 0.5},
        fix_state_init=None,
    )["price"]
    assert prix == 1.134835


# ── G5 — consommation du flux de nombres aléatoires ────────────────────────
#
# Le pont brownien tire ses uniformes APRÈS les trajectoires. Tout appel au
# générateur ajouté ou déplacé en amont décalerait tout le flux et ferait
# bouger ces trois valeurs — c'est le canari du refactoring.

def test_prix_inchange_fenetre_strike_fix():
    """Strike asiatique : la fenêtre de fixing consomme la grille temporelle et
    déclenche le mécanisme de bump différé."""
    cs = parse_script(ASIAN)
    fixe = CompiledScript(events=cs.events, init_fn=cs.init_fn, params=cs.params,
                          constats=cs.constats, strike_fix_dates=[2 / 52, 4 / 52])
    assert _price(None, compiled=fixe) == 0.988224


def test_prix_inchange_barriere_continue():
    """Monitoring continu : le pont brownien tire deux uniformes par pas et par
    trajectoire. Le décalage du flux aléatoire se verrait immédiatement ici."""
    assert _price(BARRIER, monitoring="continuous") == 0.949342


def test_prix_inchange_barriere_continue_heston():
    """Même chose avec une volatilité qui évolue : le pont consomme en plus le
    tableau de vol par pas produit par le simulateur."""
    assert _price(BARRIER, model="heston", monitoring="continuous") == 0.936203


# ── Greeks pré-trade ───────────────────────────────────────────────────────

def test_greeks_pretrade_inchanges():
    """Sensibilités d'un produit neuf, sans état lifecycle. Rendre
    `compute_greeks` capable de transporter un état ne doit rien changer quand
    aucun état n'est fourni — c'est le contrat qui protège tout le pré-trade."""
    cs = parse_script(CALL)
    g = compute_greeks(cs, [dict(UL)], CORR, r=0.03, T=T, N=20000,
                       model="constant", seed=42, user_params={"K": 1.0},
                       selected=["delta", "gamma", "vega", "theta", "rho"])
    assert g["delta_1"] == 0.5738
    assert g["gamma_1"] == 1.9378
    assert g["vega_1"] == 0.3898
    assert g["theta"] == -0.0001
    assert g["rho"] == 0.4852
