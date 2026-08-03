"""Une seule courbe pour le drift, l'actualisation et la calibration du smile.

Un taux entre dans un pricing à trois endroits sans rapport : la dérive de
chaque actif simulé, le facteur d'actualisation de chaque flux, et les prix
Black-Scholes que l'inversion de Dupire retourne. Quand chacun lit sa propre
source, le résultat n'est plus arbitrage-free — et il n'y a aucun signal, juste
un prix plausible.

Le moteur faisait exactement ça : dérive au taux plat, actualisation sur la
courbe. Un forward prépayé sous courbe plate à 1 % valait 1,009859 au lieu de
exp(-qT) = 0,990050, soit deux points de nominal. Ces tests verrouillent
l'identité qui rend ça impossible.
"""
import math

import numpy as np
import pytest

from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import (
    run_mc, run_mc_proba, compute_greeks, _build_rate_term, _build_lv_grid, SY,
)


def _ul(sigma=0.20, q=0.01):
    return [dict(name="S1", ticker="", ccy="EUR",
                 sigma=sigma, q=q, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
                 alpha=0.20, beta=0.5, rho=-0.30, nu=0.40,
                 sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]


CORR = [[1.0]]
# ts != N partout : un tableau de taux mal formé — (ts,) au lieu de (ts,1) —
# lève alors une erreur de broadcast plutôt que de se propager sur le mauvais
# axe en donnant un résultat plausible.
N = 20000

FORWARD = 'AT MATURITY\n  PAY S[1] "forward prepaye"'
ZERO_COUPON = 'AT MATURITY\n  PAY 1 "nominal"'
CALL = 'PARAM K = 1.0 "strike"\n\nAT MATURITY\n  PAY MAX(S[1] - K, 0) "call"'
PUT = 'PARAM K = 1.0 "strike"\n\nAT MATURITY\n  PAY MAX(K - S[1], 0) "put"'

PENTUE = [[0.5, 0.01], [1.0, 0.03], [3.0, 0.05]]


def _price(script, *, r=0.03, T=1.0, curve=None, model="constant", sigma=0.20,
           q=0.01, user_params=None, **kw):
    return run_mc(parse_script(script), _ul(sigma, q), CORR, r=r, T_max=T, N=N,
                  model=model, seed=42, antithetic=True,
                  user_params=user_params or {}, yield_curve=curve or [], **kw)["price"]


# ── Le forward prépayé : la sonde qui ne passe que si tout est cohérent ─────

def test_forward_prepaye_vaut_exp_moins_qt_sous_courbe_plate():
    """Un forward prépayé — on paie aujourd'hui, on reçoit l'actif à maturité —
    vaut exp(-qT), quel que soit le taux : la dérive au taux `r` et
    l'actualisation au taux `r` se simplifient exactement.

    C'est la sonde la plus discriminante du moteur : elle ne passe que si la
    dérive, l'actualisation et le shift de courbe sont simultanément corrects.
    Elle valait 1,009859 quand la dérive tournait à 3 % pendant que
    l'actualisation suivait la courbe à 1 %."""
    prix = _price(FORWARD, r=0.03, curve=[[1.0, 0.01]], sigma=0.01, q=0.01)
    assert prix == pytest.approx(math.exp(-0.01), abs=5e-4), f"{prix:.6f}"


def test_forward_prepaye_vaut_exp_moins_qt_sous_courbe_pentue():
    """L'identité tient aussi hors courbe plate — c'est même là que dérive
    plate et actualisation par piliers divergeaient le plus."""
    prix = _price(FORWARD, r=0.03, T=2.0, curve=PENTUE, sigma=0.01, q=0.02)
    assert prix == pytest.approx(math.exp(-0.02 * 2.0), abs=1e-3), f"{prix:.6f}"


@pytest.mark.parametrize("model", ["localvol", "lsv"])
def test_forward_prepaye_sous_modeles_a_vol_locale(model):
    """Les modèles à vol locale font entrer le taux une troisième fois, dans la
    calibration de Dupire. L'identité du forward doit tenir pour eux aussi."""
    prix = _price(FORWARD, r=0.03, curve=[[1.0, 0.01]], model=model,
                  sigma=0.05, q=0.01)
    assert prix == pytest.approx(math.exp(-0.01), abs=5e-3), f"{model}: {prix:.6f}"


def test_courbe_plate_au_niveau_r_equivaut_au_taux_plat():
    """Une courbe plate au niveau `r` EST le taux plat `r`. L'égalité n'est pas
    stricte au bit près : le cas courbe passe par les forwards reconstruits,
    le cas plat garde sa représentation scalaire exacte."""
    plat = _price(CALL, r=0.03, user_params={"K": 1.0})
    courbe = _price(CALL, r=0.03, curve=[[1.0, 0.03]], user_params={"K": 1.0})
    assert courbe == pytest.approx(plat, abs=1e-6)


def test_parite_call_put_sous_courbe():
    """C − P = S·exp(-qT) − K·DF(T). Identité sans modèle : elle ne peut tenir
    que si le forward et l'actualisation sortent de la même courbe."""
    T, q, K = 2.0, 0.02, 1.0
    c = _price(CALL, T=T, curve=PENTUE, q=q, user_params={"K": K})
    p = _price(PUT, T=T, curve=PENTUE, q=q, user_params={"K": K})
    df = _price(ZERO_COUPON, T=T, curve=PENTUE, q=q)
    assert c - p == pytest.approx(math.exp(-q * T) - K * df, abs=2e-3)


# ── Rho : dr est un shift parallèle de la courbe ───────────────────────────

def test_rho_du_zero_coupon_vaut_moins_t_fois_le_df():
    """Pour un flux certain, dP/dr = −T·DF(T). Le payoff est déterministe, donc
    les deux jambes du bump sont identiques trajectoire par trajectoire et le
    bruit Monte Carlo est nul : c'est le test le plus discriminant sur `dr`.

    Un `dr` compté deux fois — dans le scalaire ET dans la courbe — donnerait
    exactement le double."""
    T, r = 2.0, 0.03
    for curve in (None, [[3.0, r]]):
        g = compute_greeks(parse_script(ZERO_COUPON), _ul(q=0.0), CORR, r=r, T=T,
                           N=4000, model="constant", seed=42, user_params={},
                           selected=["rho"], yield_curve=curve or [])
        attendu = -T * math.exp(-r * T)
        assert g["rho"] == pytest.approx(attendu, abs=2e-3), (
            f"courbe={curve}: rho={g['rho']:.5f}, attendu {attendu:.5f}")


@pytest.mark.parametrize("a_r", [0.0, 0.3])
def test_le_taux_stochastique_reprice_sa_propre_courbe(a_r):
    """Propriété qui définit Hull-White : quelle que soit la volatilité de
    taux, un zéro-coupon doit valoir le facteur d'actualisation de la courbe
    d'entrée, à chaque pilier.

    Elle ne tenait pas. Le facteur de taux était écrit centré, ce qui semble
    ajuster la courbe gratuitement — mais l'actualisation étant exp(-∫r),
    Jensen donne E[exp(-∫x)] = exp(+Var/2) > 1 et toutes les obligations
    ressortaient trop chères : +164 bp sur un zéro-coupon 5 ans à 3 % de vol de
    taux, soit un arbitrage contre la courbe fournie par l'utilisateur."""
    # Les piliers de PENTUE eux-mêmes : 0,5 an à 1 %, 1 an à 3 %, 3 ans à 5 %.
    for T, z in ((0.5, 0.01), (1.0, 0.03), (3.0, 0.05)):
        prix = _price(ZERO_COUPON, T=T, curve=PENTUE, q=0.0,
                      sigma_r=0.02, a_r=a_r)
        assert prix == pytest.approx(math.exp(-z * T), abs=3e-4), (
            f"a_r={a_r} T={T} : {prix:.6f} vs {math.exp(-z * T):.6f}")


def test_rho_non_nul_sous_courbe_et_taux_stochastiques():
    """Cas dégénéré : quand la dérive suivait le facteur de taux simulé, le
    scalaire `dr` n'atteignait plus rien du tout. Les deux jambes du bump
    étaient bit-identiques sous nombres aléatoires communs et le rho ressortait
    exactement à 0,0 — un risque de taux invisible dans l'agrégation du livre."""
    g = compute_greeks(parse_script(ZERO_COUPON), _ul(q=0.0), CORR, r=0.03, T=2.0,
                       N=4000, model="constant", seed=42, user_params={},
                       selected=["rho"], yield_curve=PENTUE, sigma_r=0.015)
    assert abs(g["rho"]) > 1e-3, f"rho={g['rho']}"


# ── L'objet marché lui-même ────────────────────────────────────────────────

def test_les_forwards_reconstituent_exactement_les_facteurs_d_actualisation():
    """L'identité qui verrouille tout le chantier : les forwards sont dérivés
    des facteurs d'actualisation, donc leur somme cumulée les reconstitue à la
    précision machine. Dérive et actualisation ne peuvent plus s'écarter d'un
    résidu d'interpolation, parce qu'elles ne sont plus deux calculs."""
    ts, dt = 104, 1.0 / SY
    rt = _build_rate_term(PENTUE, ts, dt, r=0.03)
    reconstitue = np.exp(-np.cumsum(rt.step_fwd) * dt)
    assert np.allclose(reconstitue, rt.df[1:], rtol=0, atol=1e-14)


def test_dr_decale_la_courbe_entiere_en_parallele():
    """`dr` doit déplacer les facteurs d'actualisation ET les forwards du même
    montant — c'est ce qui fait du rho une vraie dérivée et non une dérivée
    partielle qui ignorerait la moitié de son effet."""
    ts, dt = 52, 1.0 / SY
    t = np.arange(ts + 1) * dt
    ref = _build_rate_term(PENTUE, ts, dt, r=0.03)
    choque = _build_rate_term(PENTUE, ts, dt, r=0.03, dr=0.01)
    assert np.allclose(choque.df, ref.df * np.exp(-0.01 * t), rtol=0, atol=1e-12)
    assert np.allclose(choque.step_fwd, ref.step_fwd + 0.01, rtol=0, atol=1e-10)


def test_absence_de_courbe_se_reconnait_a_step_fwd_none():
    """Le contrat qui porte toute la bit-identité : sans courbe, les champs
    dérivés sont None et les appelants retombent sur le scalaire exact. Router
    le cas plat par les forwards serait juste mathématiquement, mais
    déplacerait tous les prix du chemin dominant de quelques ulps."""
    plat = _build_rate_term([], 52, 1.0 / SY, r=0.03)
    assert plat.step_fwd is None and plat.zero is None
    assert plat.r_flat == 0.03
    avec = _build_rate_term([[1.0, 0.02]], 52, 1.0 / SY, r=0.03)
    assert avec.step_fwd is not None and avec.zero is not None


def test_la_grille_de_vol_locale_suit_la_courbe():
    """La calibration de Dupire est le troisième point d'entrée du taux. Sous
    courbe plate au niveau `r` elle doit reproduire le cas sans courbe ; sous
    courbe pentue elle doit s'en écarter."""
    ts, dt = 52, 1.0 / SY
    uls = _ul(sigma=0.25, q=0.02)
    uls[0]["skew"] = -0.10
    sans, *_ = _build_lv_grid(uls, _build_rate_term([], ts, dt, 0.03), ts, dt)
    plate, *_ = _build_lv_grid(uls, _build_rate_term([[3.0, 0.03]], ts, dt, 0.03), ts, dt)
    pentue, *_ = _build_lv_grid(uls, _build_rate_term(PENTUE, ts, dt, 0.03), ts, dt)
    assert np.allclose(sans[0], plate[0], rtol=0, atol=1e-6)
    assert not np.allclose(sans[0], pentue[0], rtol=0, atol=1e-4)


# ── L'onglet Proba doit décrire le même produit que le prix affiché ────────

def test_les_probabilites_utilisent_la_courbe_pour_la_derive():
    """Les probabilités d'autocall s'affichent à côté du prix : elles doivent
    être calculées sous la même mesure. Une courbe à 1 % doit donc donner la
    même probabilité qu'un taux plat à 1 %, pas qu'un taux plat à 3 %."""
    script = parse_script("""
PARAM AC = 100%  "barriere autocall"

AT 0.5, 1
  IF WOF >= AC
    PAY 1 "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
""")
    commun = dict(underlyings=_ul(q=0.0), corr_matrix=CORR, T_max=1.0, N=8000,
                  model="constant", seed=42, user_params={})
    sous_courbe = run_mc_proba(script, r=0.03, yield_curve=[[1.0, 0.01]], **commun)
    taux_plat = run_mc_proba(script, r=0.01, yield_curve=[], **commun)
    assert sous_courbe["autocall_pct"] == pytest.approx(taux_plat["autocall_pct"], abs=0.5)
