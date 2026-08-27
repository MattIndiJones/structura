"""Chantier 2 — un flux vaut sa valeur actualisée à sa date de PAIEMENT.

Jusqu'ici le moteur actualisait chaque flux au pas où il était constaté. Un
remboursement réglé cinq jours ouvrés après la maturité était donc surévalué
de l'actualisation de ces cinq jours — quelques points de base sur 100 % du
nominal, systématiquement dans le même sens.
"""
import math
from datetime import date

from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script, resolve_constats

UL = [dict(name="S1", ticker="", ccy="EUR",
           sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
           alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]
CORR = [[1.0]]
R = 0.03

ZERO_COUPON = """
AT MATURITY
  PAY 1 "remboursement"
"""


def _price(script, T, **kwargs):
    return run_mc(script, UL, CORR, r=R, T_max=T, N=2000, model="constant",
                  seed=42, antithetic=True, **kwargs)


def test_un_remboursement_sans_date_de_paiement_est_actualise_a_la_maturite():
    # Flux certain : le prix Monte Carlo est exact, pas bruité.
    res = _price(parse_script(ZERO_COUPON), 1.0)
    # run_mc arrondit le prix a 6 decimales.
    assert abs(res["price"] - math.exp(-R)) < 1e-6


def test_la_date_de_paiement_finale_actualise_davantage():
    sept_jours = 7 / 365.25
    sans = _price(parse_script(ZERO_COUPON), 1.0)["price"]
    avec = _price(parse_script(ZERO_COUPON), 1.0,
                  maturity_payment_t=1.0 + sept_jours)["price"]

    assert avec < sans
    # L'écart est exactement l'actualisation des sept jours supplémentaires.
    assert abs(avec - math.exp(-R * (1.0 + sept_jours))) < 1e-6
    # Soit ~5,7 points de base sur 100 % du nominal — l'ordre de grandeur qui
    # justifiait le chantier.
    ecart_bps = (sans - avec) / sans * 10000
    assert 5.0 < ecart_bps < 6.5, ecart_bps


def test_le_flux_table_porte_la_date_de_paiement():
    res = _price(parse_script(ZERO_COUPON), 1.0, maturity_payment_t=1.02)
    ligne = next(iter(res["flux_table"].values()))
    assert ligne["t"] == 1.0            # constaté à maturité
    assert abs(ligne["t_pay"] - 1.02) < 1e-9   # payé après


COUPONS = """PARAM COUPON = 5%
CONSTAT() OBS

AT OBS:
  PAY COUPON "coupon"
"""

CALENDRIER = {
    "OBS": {
        "start_date": "2026-02-28", "end_date": "2027-02-28",
        "roll_date": "2026-02-28", "frequency": "3M", "stub": "short_last",
        "convention": "following",
    }
}


def _coupons(lag):
    values = {"OBS": dict(CALENDRIER["OBS"], settlement_lag=lag)}
    compiled = resolve_constats(parse_script(COUPONS), values,
                                anchor=date(2026, 2, 28), currency="EUR")
    return _price(compiled, 1.0)


def test_le_decalage_de_reglement_des_coupons_coute_de_l_actualisation():
    sans = _coupons(0)["price"]
    avec = _coupons(5)["price"]
    assert avec < sans
    # Tous les coupons glissent d'une semaine : l'écart relatif est le même
    # que sur un remboursement unique — l'actualisation ne dépend pas du
    # nombre de flux, seulement du décalage.
    ecart_bps = (sans - avec) / sans * 10000
    assert 4.0 < ecart_bps < 7.0, ecart_bps


def test_chaque_coupon_est_actualise_a_sa_propre_date_de_paiement():
    flux = _coupons(5)["flux_table"]
    assert flux, "aucun flux enregistré"
    for ligne in flux.values():
        assert ligne["t_pay"] > ligne["t"], ligne
        # Le facteur implicite doit correspondre à la date de PAIEMENT, pas à
        # celle de la constatation : c'est tout l'objet du chantier.
        df_attendu = math.exp(-R * ligne["t_pay"])
        assert abs(ligne["pv"] / ligne["sum"] - df_attendu) < 5e-4, ligne


def test_sans_calendrier_de_reglement_rien_ne_change():
    # La non-régression qui compte : un script sans devise de règlement doit
    # rendre exactement le prix d'avant le chantier.
    compiled = resolve_constats(parse_script(COUPONS), CALENDRIER,
                                anchor=date(2026, 2, 28))
    res = _price(compiled, 1.0)
    for ligne in res["flux_table"].values():
        assert ligne["t_pay"] == ligne["t"]
