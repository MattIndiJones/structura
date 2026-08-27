"""Chantier 1 — le calendrier CONSTAT porte son règlement.

Les dates d'observation sont roulées sur des dates non ajustées puis déplacées
sur un jour ouvré ; chaque observation porte la date à laquelle son cash bouge.
"""
from datetime import date

import pytest

from backend.app.core.calendars import BusinessDayConvention
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.schedule import StubConvention, generate_schedule, parse_tenor

TRIM = parse_tenor("3M")


def _schedule(**kwargs):
    return generate_schedule(
        date(2026, 2, 28), date(2027, 2, 28), date(2026, 2, 28),
        TRIM, StubConvention.SHORT_LAST, **kwargs)


def test_sans_devise_les_dates_restent_calendaires():
    # Le comportement historique : aucun ajustement, le cash bouge le jour de
    # la constatation. C'est ce que voient tous les appelants pas encore câblés.
    res = _schedule()
    assert date(2026, 2, 28) in res["dates"]      # un samedi, constaté un samedi
    assert date(2027, 2, 28) in res["dates"]      # un dimanche, idem
    assert res["payment_dates"] == res["dates"]


def test_avec_devise_les_observations_tombent_un_jour_ouvre():
    res = _schedule(currency="EUR")
    assert all(d.weekday() < 5 for d in res["dates"])
    # Les deux sens de Modified Following, sur le même calendrier :
    #  - 28/02/2026 (samedi) : avancer mènerait au 2 mars, donc on recule au 27.
    #  - 28/11/2026 (samedi) : le lundi 30 reste en novembre, on avance.
    #  - 28/02/2027 (dimanche) : même bascule de mois que février 2026.
    assert date(2026, 2, 27) in res["dates"]
    assert date(2026, 11, 30) in res["dates"]
    assert date(2027, 2, 26) in res["dates"]


def test_le_roll_se_fait_avant_ajustement():
    # Un trimestriel ajusté reste trimestriel : si l'on ajustait avant de
    # rouler, chaque décalage se propagerait à la période suivante et le
    # calendrier dériverait. Les dates restent ancrées sur le 28/29 du mois.
    res = _schedule(currency="EUR")
    jours = {d.day for d in res["dates"]}
    assert jours <= {26, 27, 28, 29, 30, 31, 1}, jours


def test_le_decalage_de_reglement_produit_les_dates_de_paiement():
    res = _schedule(currency="EUR", settlement_lag=5)
    for observation, paiement in zip(res["dates"], res["payment_dates"]):
        assert paiement > observation
        assert paiement.weekday() < 5


def test_un_decalage_sans_calendrier_est_refuse():
    # Compter un décalage en jours calendaires derrière le dos de l'appelant
    # serait faux d'un à trois jours selon l'endroit du calendrier.
    with pytest.raises(ValueError, match="décalage de règlement"):
        _schedule(settlement_lag=5)


def test_deux_dates_ajustees_sur_le_meme_jour_fusionnent():
    # Un quotidien à cheval sur un week-end : samedi et dimanche tombent tous
    # deux sur le lundi. Constater trois fois le même fixing le compterait
    # trois fois.
    res = generate_schedule(date(2026, 5, 28), date(2026, 6, 3), date(2026, 5, 28),
                            parse_tenor("1D"), StubConvention.SHORT_LAST,
                            currency="EUR")
    assert len(res["dates"]) == len(set(res["dates"]))


def test_convention_none_laisse_le_calendrier_brut():
    res = _schedule(currency="EUR", convention=BusinessDayConvention.NONE)
    assert date(2026, 2, 28) in res["dates"]


SCRIPT = """PARAM COUPON = 5%
CONSTAT() OBS

AT OBS:
  PAY COUPON
"""

CONSTAT_VALUES = {
    "OBS": {
        "start_date": "2026-02-28", "end_date": "2027-02-28",
        "roll_date": "2026-02-28", "frequency": "3M", "stub": "short_last",
    }
}


def _resolved(**kwargs):
    compiled = parse_script(SCRIPT)
    return resolve_constats(compiled, CONSTAT_VALUES, anchor=date(2026, 2, 28), **kwargs)


def test_sans_devise_les_flux_sont_payes_a_la_constatation():
    ev = _resolved().events[0]
    assert ev.payment_dates is None   # « payé à l'observation »


def test_avec_devise_chaque_observation_porte_sa_date_de_paiement():
    values = {"OBS": dict(CONSTAT_VALUES["OBS"],
                          settlement_lag=5, convention="following")}
    compiled = resolve_constats(parse_script(SCRIPT), values,
                                anchor=date(2026, 2, 28), currency="EUR")
    ev = compiled.events[0]
    assert len(ev.payment_dates) == len(ev.dates)
    # Constatation ramenée sur un jour ouvré, puis cinq jours ouvrés de
    # règlement : entre 7 et 11 jours calendaires selon les fériés traversés.
    for t_obs, t_pay in zip(ev.dates, ev.payment_dates):
        ecart_jours = (t_pay - t_obs) * 365.25
        assert 6.5 <= ecart_jours <= 11.5, ecart_jours


def test_sans_convention_la_date_du_term_sheet_ne_bouge_pas():
    # Pas de défaut global : une constatation fixée un samedi par le term
    # sheet reste ce samedi tant qu'aucune convention n'est choisie.
    values = {"OBS": dict(CONSTAT_VALUES["OBS"], settlement_lag=5)}
    compiled = resolve_constats(parse_script(SCRIPT), values,
                                anchor=date(2026, 2, 28), currency="EUR")
    ev = compiled.events[0]
    # 28/11/2026 est un samedi : sans convention, il reste le 28.
    assert any(abs(t - 0.747433) < 1e-3 for t in ev.dates), ev.dates


DEUX_CALENDRIERS = """PARAM COUPON = 5%
CONSTAT() OBS
CONSTAT() COUPONS

AT OBS:
  PAY COUPON

AT COUPONS:
  PAY COUPON
"""


def test_chaque_calendrier_porte_sa_propre_convention():
    values = {
        "OBS": dict(CONSTAT_VALUES["OBS"], convention="following"),
        "COUPONS": dict(CONSTAT_VALUES["OBS"], convention="modified_following"),
    }
    compiled = resolve_constats(parse_script(DEUX_CALENDRIERS), values,
                                anchor=date(2026, 2, 28), currency="EUR")
    obs, coupons = compiled.events[0].dates, compiled.events[1].dates
    # Même grille, deux conventions : la dernière constatation (dimanche
    # 28/02/2027) avance au 1er mars d'un côté, recule au 26 février de l'autre.
    assert obs[-1] > coupons[-1]


def test_convention_inconnue_est_refusee():
    values = {"OBS": dict(CONSTAT_VALUES["OBS"], convention="modified_thursday")}
    with pytest.raises(ValueError, match="convention de jour ouvré inconnue"):
        resolve_constats(parse_script(SCRIPT), values,
                         anchor=date(2026, 2, 28), currency="EUR")


def test_un_decalage_sans_devise_est_refuse_aussi_au_niveau_du_script():
    values = {"OBS": dict(CONSTAT_VALUES["OBS"], settlement_lag=5)}
    with pytest.raises(ValueError, match="décalage de règlement"):
        resolve_constats(parse_script(SCRIPT), values, anchor=date(2026, 2, 28))


def test_le_qualificatif_selectionne_la_meme_ligne_des_deux_cotes():
    script = SCRIPT.replace("AT OBS:", "AT OBS.last:")
    values = {"OBS": dict(CONSTAT_VALUES["OBS"], settlement_lag=5)}
    compiled = resolve_constats(parse_script(script), values,
                                anchor=date(2026, 2, 28), currency="EUR")
    ev = compiled.events[0]
    assert len(ev.dates) == 1 and len(ev.payment_dates) == 1
    assert ev.payment_dates[0] > ev.dates[0]
