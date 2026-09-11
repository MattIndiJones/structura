"""La fenêtre de départ dans la vie résiduelle — §22.

`CONSTAT STRIKE_FIX AVG` fixe S0 par sous-jacent sur une fenêtre de relevés ; le
cours du jour de strike n'en est que le premier. Une fois la fenêtre close, le
rejeu historique exprime tout son état — plus-bas réalisés, spots de la
dernière constatation — en unités de CE niveau.

Le MtM résiduel, lui, mesurait le spot du jour contre `strike_levels`, le seul
fixing du jour de strike. Les trajectoires partaient donc d'un niveau exprimé
dans d'autres unités que l'état qu'elles héritent, et chaque barrière se lisait
à la distance du cours du strike, pas de S0.

Aucun Monte-Carlo ici : `build_residual` rejoue l'historique et assemble le
produit résiduel, rien de plus.
"""
from datetime import date, timedelta

import pytest

from backend.app.core.inlife_valuation import InLifeProduct, build_residual

STRIKE = date(2026, 9, 14)            # un lundi
MATURITE = date(2027, 9, 14)
VALO = STRIKE + timedelta(days=42)

SCRIPT = """PARAM STRIKE = 100%
CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE

AT MATURITE:
  PAY MAX(WOF - STRIKE, 0) "call"
"""

CONSTATS = {"STRIKE_FIX": {"date": STRIKE.isoformat(), "window_length": "10D",
                           "window_frequency": "1D"},
            "MATURITE": MATURITE.isoformat()}


def _historique():
    """Cours à 100 avant le strike, puis 100, 101 … 109 sur les dix séances de
    la fenêtre — S0 contractuel = 104,5 —, puis 110 jusqu'à la valorisation."""
    dates, serie = [], []
    jour, k = STRIKE - timedelta(days=7), 0
    while jour <= VALO:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            if jour < STRIKE:
                serie.append(100.0)
            elif k < 10:
                serie.append(100.0 + k)
                k += 1
            else:
                serie.append(110.0)
        jour += timedelta(days=1)
    return {"^STOXX50E": serie}, dates


def _residuel():
    prices, dates = _historique()
    produit = InLifeProduct(
        script_snapshot=SCRIPT,
        underlyings=[{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}],
        # Le fixing du jour de strike, tel que l'événement booké le porte :
        # le relevé 1/10 de la fenêtre, pas S0.
        strike_levels={"SX5E": 100.0},
        strike_date=STRIKE, value_date=STRIKE + timedelta(days=2),
        tenor=(MATURITE - STRIKE).days / 365.25, currency="EUR",
        payment_date=MATURITE + timedelta(days=3),
        market={"constats": CONSTATS, "r": 3.0, "model": "constant"},
    )
    return build_residual(produit, prices, dates, (VALO - STRIKE).days / 365.25, VALO)


def test_le_spot_du_jour_se_mesure_contre_le_s0_du_rejeu():
    """Les trajectoires et l'état hérité doivent parler les mêmes unités. Avec
    un seul sous-jacent, `wof_last` est exactement le spot du jour sur le S0 du
    rejeu : le point de départ des trajectoires doit lui être égal."""
    res = _residuel()
    assert res.pre_strike is False
    assert res.state["fix_state"] is None          # fenêtre entièrement close
    assert res.norm_spots[0] == pytest.approx(res.state["wof_last"])


def test_le_niveau_initial_rendu_est_celui_de_la_fenetre():
    """`s0_map` repart vers la note de valorisation, qui normalise l'historique
    affiché avec : il doit être le niveau contre lequel le MtM a mesuré."""
    res = _residuel()
    assert res.s0_map["SX5E"] == pytest.approx(110.0 / res.state["wof_last"])
    assert res.s0_map["SX5E"] != pytest.approx(100.0)


def test_la_fenetre_de_depart_lit_chaque_releve_a_sa_date():
    """Le S0 contractuel est la moyenne des dix clôtures de la fenêtre : 104,5.
    Le rejeu lisait ses relevés à `round(t × 252)` séances du strike : dix jours
    ouvrés tombaient sur les pas 0, 1, 1, 2, 3, 5, 6, 6, 7, 8, le 15/09 était lu
    deux fois, le 25/09 jamais, et S0 ressortait à 103,9. Chaque relevé se lit
    désormais à sa date (§23)."""
    res = _residuel()
    assert 110.0 / res.state["wof_last"] == pytest.approx(104.5)
