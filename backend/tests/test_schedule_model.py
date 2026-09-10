"""L'échéancier résolu comme structure unique — point 3 du §14.

Jusqu'ici, « ce que le produit observe » n'existait nulle part comme objet :
l'information se dispersait entre `CompiledEvent.dates`, `.window_dates`,
`.ranks`, `.payment_dates`, puis se reconstituait différemment dans chaque
consommateur. Ces tests vérifient qu'elle est désormais dite **une fois**, et
qu'elle dit tout ce dont le booking, le cycle de vie et l'écran Events auront
besoin : les dates calendaires, les rôles, les rangs, les blocs rattachés.

Le moteur n'est pas concerné : il garde ses propres tables. La structure existe
pour que les AUTRES chemins cessent de reconstruire la leur.
"""
from datetime import date

import pytest

from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.schedule_model import Echeancier

TODAY = date(2026, 9, 10)

CAL = {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
               "roll_date": "2029-09-10", "frequency": "1Y", "stub": "short_last",
               "window_frequency": "3M"}}

AUTOCALL = """PARAM COUPON = 8%
CONSTAT() OBS AVG PERIOD
AT OBS:
  PAY COUPON * INDEX "coupon"
AT OBS.last.last:
  PAY 1 "PDI sur cloture"
AT MATURITY:
  PAY 0 "rien"
"""


def _echeancier(src=AUTOCALL, constats=None, currency="EUR"):
    compiled = resolve_constats(parse_script(src), constats or CAL,
                                anchor=TODAY, currency=currency)
    return compiled.echeancier


def test_l_echeancier_est_construit_a_la_resolution():
    e = _echeancier()
    assert isinstance(e, Echeancier)
    assert len(e.constatations) == 3


def test_chaque_constatation_porte_sa_date_calendaire():
    """La year-fraction sert au moteur ; la date calendaire est la seule
    opposable — c'est elle qu'un term sheet porte et qu'un deal booké fige. Les
    deux doivent voyager ensemble : reconstruire l'une depuis l'autre après coup
    suppose de re-choisir une origine, et c'est l'erreur d'ancrage qui est
    revenue cinq fois en une session."""
    jours = [c.jour for c in _echeancier().constatations]
    assert jours == [date(2027, 9, 10), date(2028, 9, 10), date(2029, 9, 10)]


def test_les_releves_sont_rattaches_a_leur_constatation():
    """Quatre relevés trimestriels par constatation annuelle, datés, et le
    dernier de chaque fenêtre est la constatation elle-même."""
    for c in _echeancier().constatations:
        assert len(c.releves) == 4
        assert c.releves[-1].jour == c.jour
        assert all(r.jour is not None for r in c.releves)


def test_un_releve_vise_par_un_bloc_porte_les_deux_roles():
    """`AT OBS.last.last` vise le dernier relevé de la dernière fenêtre : ce
    relevé alimente la moyenne ET déclenche un bloc. La structure doit dire les
    deux — c'est ce qui permettra au cycle de vie de n'enregistrer qu'un seul
    fixing officiel pour les deux usages."""
    e = _echeancier()
    marques = [(c.rang, r.jour) for c in e.constatations
               for r in c.releves if r.est_evenement]
    assert marques == [(3, date(2029, 9, 10))]


def test_les_blocs_sont_rattaches_dans_l_ordre_du_script():
    """L'ordre est contractuel, pas cosmétique : un `STOP` annule les suivants.
    La dernière constatation porte les deux blocs, dans l'ordre d'écriture."""
    e = _echeancier()
    assert [c.blocs for c in e.constatations] == [(0,), (0,), (0, 1)]
    # `AT MATURITY` ne relève d'aucun échéancier : il est listé à part.
    assert e.blocs_maturite == (2,)


def test_deux_blocs_du_meme_calendrier_ne_font_qu_une_constatation():
    """`AT OBS:` et `AT OBS.last:` visent la même date : une seule constatation,
    qui porte les deux blocs. Les dédoubler donnerait deux rangs pour un seul
    événement contractuel."""
    e = _echeancier("CONSTAT() OBS\nAT OBS:\n  PAY 1\nAT OBS.last:\n  PAY 2\n")
    assert len(e.constatations) == 3
    assert e.constatations[-1].blocs == (0, 1)


def test_la_fenetre_de_depart_n_est_pas_une_constatation():
    """`STRIKE_FIX` fixe S0 : rien ne s'y déclenche, elle n'a pas de rang et ne
    doit pas apparaître parmi les constatations."""
    e = _echeancier(
        "CONSTAT STRIKE_FIX AVG\nCONSTAT MAT\nAT MAT:\n  PAY WOF\n",
        constats={"STRIKE_FIX": {"date": "2026-09-10", "window_length": "10D",
                                 "window_frequency": "1D"},
                  "MAT": "2029-09-10"})
    assert e.depart is not None and e.depart.reduction == "AVG"
    assert len(e.depart.releves) == 10
    assert len(e.constatations) == 1 and e.constatations[0].reduction is None


def test_les_dates_de_releve_listent_tous_les_fixings_a_collecter():
    """La question que posera le cycle de vie : quels cours faut-il relever ?
    Constatations ponctuelles comprises, fenêtre de départ comprise, sans
    doublon — un fixing servant deux usages n'apparaît qu'une fois."""
    e = _echeancier()
    dates = e.dates_de_releve
    assert len(dates) == 12                       # 3 fenêtres de 4 relevés
    assert len(set(dates)) == len(dates)
    assert list(dates) == sorted(dates)


def test_plusieurs_constatations_peuvent_tomber_le_meme_jour():
    """Deux calendriers peuvent partager une date, chacun gardant son rang et sa
    réduction. Une structure indexée par la seule date ne saurait pas le
    représenter — d'où la recherche explicite."""
    cal = {"A": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                 "roll_date": "2029-09-10", "frequency": "1Y", "stub": "short_last"},
           "B": {"date": "2029-09-10"}}
    e = _echeancier("CONSTAT() A\nCONSTAT B\nAT A:\n  PAY 1\nAT B:\n  PAY 2\n",
                    constats=cal)
    fin = e.constatations[-1].t
    ensemble = e.a_la_date(fin)
    assert len(ensemble) == 2, [c.calendrier for c in ensemble]
    # Chacune garde SON rang : la troisième de A, la première de B.
    assert sorted((c.calendrier, c.rang) for c in ensemble) == [("A", 3), ("B", 1)]


def test_la_structure_se_serialise_pour_le_booking():
    """Le booking figera cette structure : elle doit sortir en JSON simple, avec
    les dates en ISO."""
    d = _echeancier().to_dict()
    assert [c["rang"] for c in d["constatations"]] == [1, 2, 3]
    assert d["constatations"][0]["date"] == "2027-09-10"
    assert d["constatations"][0]["releves"][0]["date"] == "2026-12-10"
    assert d["constatations"][-1]["releves"][-1]["evenement"] is True
    assert d["blocs_maturite"] == [2]


def test_un_script_a_dates_litterales_a_aussi_son_echeancier():
    """Le mode normal n'a pas de CONSTAT, mais il a un échéancier : sa liste de
    dates. La structure ne doit pas être réservée au mode expert."""
    e = _echeancier("AT 1, 2, 3:\n  PAY INDEX\n", constats={}, currency=None)
    assert [c.rang for c in e.constatations] == [1, 2, 3]
    assert all(c.calendrier is None and c.jour is None for c in e.constatations)
