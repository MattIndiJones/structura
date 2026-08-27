"""Chantier 2b — la diffusion démarre au strike, le prix s'exprime à la value date.

Le moteur n'avait qu'une origine, la value date : le sous-jacent commençait à
diffuser le jour du règlement, deux jours ouvrés après avoir été constaté.
"""
import math

from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script

UL = [dict(name="S1", ticker="", ccy="EUR",
           sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
           alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]
CORR = [[1.0]]
R = 0.03
DEUX_JOURS = 2 / 365.25

ZERO_COUPON = """
AT MATURITY
  PAY 1 "remboursement"
"""

CALL = """
PARAM K = 1.0 "strike"

AT MATURITY
  PAY MAX(S[1] - K, 0) "call"
"""


def _price(src, T, N=40000, **kwargs):
    return run_mc(parse_script(src), UL, CORR, r=R, T_max=T, N=N, model="constant",
                  seed=42, antithetic=True, user_params={"K": 1.0}, **kwargs)["price"]


def test_sur_un_flux_certain_l_actualisation_ne_bouge_pas():
    # Le point le moins intuitif du chantier : ancrer au strike allonge les
    # temps de deux jours ouvrés, mais exprimer la PV à la value date les
    # raccourcit d'autant. Sous taux plats, les deux effets se compensent
    # EXACTEMENT — un zéro-coupon vaut le même prix qu'avant.
    sans = _price(ZERO_COUPON, 1.0, N=2000)
    avec = _price(ZERO_COUPON, 1.0 + DEUX_JOURS, N=2000, value_date_t=DEUX_JOURS)
    assert abs(avec - sans) < 1e-6, (sans, avec)


def test_le_remboursement_est_actualise_a_l_horizon_reel():
    # Le flux de maturite etait actualise au pas de grille le plus proche :
    # sur une maturite non ronde, jusqu a 3,5 jours d ecart, dans un sens ou
    # dans l autre. Il suit desormais l horizon exact.
    import math as _m
    for T in (1.0, 1.005, 1.01, 1.02):
        prix = _price(ZERO_COUPON, T, N=500)
        assert abs(prix - _m.exp(-R * T)) < 1e-6, (T, prix)


def test_a_resolution_hebdomadaire_la_bascule_est_neutre_sur_le_prix():
    # Constat important : la grille de simulation est hebdomadaire (SY = 52).
    # Deux jours ouvres tombent SOUS sa resolution — ts = round(T * 52) rend le
    # meme nombre de pas avec ou sans la bascule, donc les memes trajectoires.
    # Cote actualisation, les deux effets se compensent exactement. La bascule
    # est donc juste sur le fond et neutre sur le chiffre tant que la grille
    # reste hebdomadaire : elle ne prendra une valeur numerique que sur une
    # grille assez fine pour representer l ecart strike/value.
    sans = _price(CALL, 1.0)
    avec = _price(CALL, 1.0 + DEUX_JOURS, value_date_t=DEUX_JOURS)
    assert avec == sans, (sans, avec)


def test_un_ecart_superieur_au_pas_de_grille_se_voit():
    # Des que l ecart depasse le pas hebdomadaire, la diffusion supplementaire
    # devient representable et le call vaut plus cher : c est bien du temps de
    # volatilite en plus, pas un artefact d actualisation.
    un_mois = 1 / 12
    sans = _price(CALL, 1.0)
    avec = _price(CALL, 1.0 + un_mois, value_date_t=un_mois)
    assert avec > sans, (sans, avec)


def test_value_date_nulle_reproduit_le_comportement_historique():
    # La non-régression : sans value date, le prix doit être bit-identique à
    # celui d'avant le chantier.
    assert _price(ZERO_COUPON, 1.0, N=2000) == _price(ZERO_COUPON, 1.0, N=2000,
                                                      value_date_t=0.0)


def test_le_recalage_s_applique_aussi_a_la_date_de_paiement():
    # Les deux mécanismes se composent : le flux est actualisé de sa date de
    # paiement jusqu'à la value date, et pas jusqu'à l'origine de la diffusion.
    sept_jours = 7 / 365.25
    prix = _price(ZERO_COUPON, 1.0 + DEUX_JOURS, N=2000,
                  value_date_t=DEUX_JOURS,
                  maturity_payment_t=1.0 + DEUX_JOURS + sept_jours)
    # Actualisation nette = de la date de paiement à la value date.
    assert abs(prix - math.exp(-R * (1.0 + sept_jours))) < 1e-6, prix
