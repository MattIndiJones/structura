"""Entrées invalides : échouer bruyamment plutôt que rendre un nombre plausible.

Le fil rouge de l'audit quantitatif n'a jamais été le plantage, c'est le
résultat crédible et faux. Un modèle mal orthographié retombait sur le GBM, une
corrélation de −1,5 produisait un prix fini, `S[0]` désignait le dernier
sous-jacent, `BASKET(0,5 ; 0,5)` sur un actif unique divisait le panier par
deux, et une matrice de corrélation non admissible était réparée en silence.
Aucun de ces cas ne levait quoi que ce soit : ils sortaient un prix.

Ces tests vérifient qu'ils lèvent désormais, et — pour les rares cas où
corriger est légitime — que la correction est reportée à l'appelant.
"""
import math

import numpy as np
import pytest

from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import (
    run_mc, run_mark_to_future, compute_greeks, cholesky, CORR_REPAIR_TOL,
)


def _ul(**kw):
    d = dict(name="S1", ticker="", ccy="EUR", sigma=0.20, q=0.0,
             v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
             alpha=0.20, beta=1.0, rho=-0.30, nu=0.40,
             sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
    d.update(kw)
    return [d]


C1 = [[1.0]]
CALL = 'PARAM K = 1.0\nAT MATURITY\n  PAY MAX(S[1] - K, 0) "call"'


def _price(script, uls=None, corr=None, **kw):
    kw.setdefault("model", "constant"); kw.setdefault("seed", 42)
    kw.setdefault("antithetic", True); kw.setdefault("user_params", {})
    kw.setdefault("r", 0.03); kw.setdefault("T_max", 1.0); kw.setdefault("N", 2000)
    return run_mc(parse_script(script), uls or _ul(), corr or C1, **kw)


# ── Modèle et paramètres de diffusion ──────────────────────────────────────

def test_un_modele_inconnu_est_refuse():
    """Un nom de modèle non reconnu retombait sur le GBM : le prix ne portait
    pas sur le modèle demandé, et rien ne consignait la substitution."""
    with pytest.raises(ValueError, match="Modèle inconnu"):
        _price(CALL, model="heaston", user_params={"K": 1.0})


@pytest.mark.parametrize("champ,valeur", [
    ("xi", 0.0),          # divisait par zéro dans le terme d'Andersen
    ("kappa", -1.0),      # retour à la moyenne inversé
    ("v0", -0.04),        # variance initiale négative
    ("theta", 0.0),       # variance long terme nulle
    ("rho_h", -1.5),      # hors [-1, 1] : ce n'est plus une corrélation
])
def test_parametres_heston_hors_domaine_refuses(champ, valeur):
    """Tous ces cas produisaient un prix fini — le pire résultat possible,
    parce qu'il a l'air utilisable."""
    with pytest.raises(ValueError, match=f"Paramètre {champ} invalide"):
        _price(CALL, _ul(**{champ: valeur}), model="heston", user_params={"K": 1.0})


@pytest.mark.parametrize("champ,valeur", [("alpha", 0.0), ("beta", 1.5), ("rho", -2.0)])
def test_parametres_sabr_hors_domaine_refuses(champ, valeur):
    with pytest.raises(ValueError, match=f"Paramètre {champ} invalide"):
        _price(CALL, _ul(**{champ: valeur}), model="sabr", user_params={"K": 1.0})


# ── Indexation et paniers ──────────────────────────────────────────────────

def test_indice_zero_est_refuse_au_lieu_de_designer_le_dernier_actif():
    """`S[0]` valait `spots[-1]` par indexation négative Python : sur un panier
    de trois, il pricait le troisième sous-jacent. Le seul indice faux du
    langage était aussi le seul à ne rien lever."""
    u3 = [dict(_ul()[0], name=f"S{i}") for i in (1, 2, 3)]
    c3 = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    with pytest.raises(ValueError, match=r"S\[0\] : indice hors bornes"):
        _price('AT MATURITY\n  PAY S[0] "s0"', u3, c3)
    with pytest.raises(ValueError, match=r"S\[4\] : indice hors bornes"):
        _price('AT MATURITY\n  PAY S[4] "s4"', u3, c3)
    # L'indexation légitime reste intacte.
    assert _price('AT MATURITY\n  PAY S[3] "s3"', u3, c3)["price"] > 0


def test_poids_de_panier_en_exces_refuses():
    """`zip` tronquait au plus court tandis que `sum(weights)` les comptait
    tous : le dénominateur incluait des poids qu'aucun actif ne portait, et
    BASKET(0,5 ; 0,5) sur un actif unique renvoyait la moitié de son niveau —
    une erreur de prix de 50 %, sans erreur nulle part."""
    with pytest.raises(ValueError, match="BASKET : 2 poids pour 1 sous-jacent"):
        _price('AT MATURITY\n  PAY BASKET(0.5, 0.5) "b"')


def test_pay_d_un_param_tableau_fonctionne():
    """`PAY` était la seule instruction du langage à ne pas recevoir
    `array_params` : un PARAM() par observation s'y résolvait en la liste
    entière, et le flux explosait sur `fl["v"] * disc` — hors du try/except de
    l'évaluateur, donc en TypeError brute et non en erreur PayScript."""
    r = 0.03
    res = _price('PARAM() CPN = 5%\nAT 0.5, 1\n  PAY CPN "coupon"',
                 user_params={"CPN": [0.01, 0.02]})
    attendu = math.exp(-r * 0.5) * 0.01 + math.exp(-r * 1.0) * 0.02
    assert res["price"] == pytest.approx(attendu, abs=1e-6)


# ── Matrices de corrélation ────────────────────────────────────────────────

def test_matrice_psd_singuliere_ne_leve_plus_d_erreur_brute():
    """[[1,1],[1,1]] a une valeur propre nulle, donc le test `< 0` la laissait
    passer sans jitter et numpy levait un LinAlgError non rattrapé."""
    L = cholesky([[1.0, 1.0], [1.0, 1.0]], 2)
    assert np.allclose(L @ L.T, [[1.0, 1.0], [1.0, 1.0]], atol=1e-6)


def test_reparation_negligeable_est_reportee_et_non_silencieuse():
    rapport: dict = {}
    cholesky([[1.0, 1.0], [1.0, 1.0]], 2, repair_report=rapport)
    assert rapport["max_shift"] < CORR_REPAIR_TOL
    assert rapport["matrix_used"][0][1] == pytest.approx(1.0, abs=1e-6)


def test_reparation_materielle_est_refusee():
    """Trois actifs à ρ = −0,9 : la matrice n'est pas définie positive et la
    projection la plus proche ramène le coefficient à −0,5. Pricer un worst-of
    là-dessus revient à répondre à une question que personne n'a posée."""
    M = [[1.0, -0.9, -0.9], [-0.9, 1.0, -0.9], [-0.9, -0.9, 1.0]]
    with pytest.raises(ValueError, match="non définie positive"):
        cholesky(M, 3)


# ── Garde-fous d'usage ─────────────────────────────────────────────────────

def test_mtf_ne_marque_plus_un_produit_deja_rappele():
    """Un autocall rappelé n'a plus de valeur résiduelle à marquer.

    Les scénarios outer ne rejouaient aucun événement antérieur à la date de
    valorisation : le produit, rappelé avec quasi-certitude à sa première
    observation, restait marqué autour de 107 % du nominal pendant le reste de
    sa vie initiale — sur une distribution si dégénérée que son minimum et son
    maximum coïncidaient sur les 2 000 scénarios. Les percentiles lus dessus
    avaient l'air précis et ne voulaient rien dire.

    Le cash déjà versé est réel mais n'est plus le deal : il est reporté à part
    et capitalisé, au lieu d'être confondu avec la valeur du produit."""
    ac = parse_script("""
PARAM CPN = 8%
PARAM AC = 90%
AT 0.5, 1, 1.5
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP
AT MATURITY
  PAY WOF "final"
""")
    r = 0.03
    res = run_mark_to_future(ac, _ul(sigma=0.01), C1, r=r, T_max=2.0,
                             main_price=1.0639, model="constant", n_outer=400,
                             n_inner=50, n_dates=5, seed=42, user_params={})
    avant, apres = res["results"][0], res["results"][-1]

    # Avant la première observation, le produit est vivant et vaut son prix.
    assert avant["t"] < 0.5
    assert avant["terminated_pct"] == 0.0
    assert np.mean(avant["pvs"]) > 100.0

    # Après, il est mort : plus rien à marquer.
    assert apres["t"] > 0.5
    assert apres["terminated_pct"] == 100.0
    assert max(apres["pvs"]) == 0.0

    # Plus aucune série « cash encaissé » n'est publiée ici : elle ne décrivait
    # que les trajectoires rappelées, lesquelles sortent désormais de
    # l'échantillon. L'écran ne porte qu'une grandeur, le mark actualisé des
    # contrats encore vivants.
    assert "realized_pvs" not in apres
    # Tout étant rappelé à la dernière date, il n'y a plus rien à marquer.
    assert apres["n_alive"] == 0
    assert apres["stats"] is None
    # Les flux datés restent disponibles pour les horizons PRIIPs, qui en ont
    # besoin pour calculer un TRI — question différente, écran différent.
    assert any(len(fl) > 0 for fl in apres["realized_flows"])


def test_le_vega_heston_declare_sa_couverture():
    """Le bump de vol n'atteint que la jambe indépendante de la variance : la
    sensibilité rendue couvre (1 − ρ_h²) de la volatilité, soit la moitié au
    skew actions usuel. C'est une vraie sensibilité, mais pas celle que le mot
    « vega » laisse entendre, et un agrégat de livre qui la mélange à des vegas
    GBM additionne des grandeurs de portées différentes."""
    g = compute_greeks(parse_script(CALL), _ul(rho_h=-0.7), C1, r=0.0, T=1.0,
                       N=4000, model="heston", seed=42, user_params={"K": 1.0},
                       selected=["vega"])
    assert g["vega_scope"]["type"] == "leg_independante"
    assert g["vega_scope"]["coverage"]["S1"] == pytest.approx(0.51, abs=1e-6)

    g_gbm = compute_greeks(parse_script(CALL), _ul(), C1, r=0.0, T=1.0, N=4000,
                           model="constant", seed=42, user_params={"K": 1.0},
                           selected=["vega"])
    assert g_gbm["vega_scope"]["type"] == "total"


def test_le_monitoring_continu_est_signale_comme_approche():
    """Le pont brownien price une barrière proche 14 % sous sa valeur exacte,
    alors que le mode hebdomadaire est juste. Tant que le pont n'est pas refait,
    le résultat doit au moins le dire."""
    barriere = ('PARAM B = 95%\nAT MATURITY\n'
                '  SET OUT = INDIC(S_MIN[1] < B)\n  PAY (1 - OUT) * 1 "do"')
    res = _price(barriere, barrier_monitoring="continuous", user_params={"B": 0.95})
    assert res["barrier_monitoring"] == "continuous"
    assert "pont brownien" in res["barrier_monitoring_note"]
    assert _price(barriere, user_params={"B": 0.95})["barrier_monitoring_note"] is None
