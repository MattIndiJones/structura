"""L'échéancier contractuel figé au booking — point 5 du §14.

Les dates d'un deal booké se reconstruisaient jusqu'ici à chaque valorisation,
depuis ses CONSTAT et son ancrage. Une convention de jour ouvré modifiée, un
référentiel de fériés mis à jour, ou simplement un changement dans la génération
de calendrier déplaçaient donc **rétroactivement** les constatations d'un contrat
déjà signé. Ce que le term sheet dit ne doit dépendre d'aucun code exécuté plus
tard : le booking fige.

Ces tests ne touchent à aucune base : ils appellent la fonction de figement
directement, avec un corps de requête minimal.
"""
import json

import pytest

from backend.app.api.deals import _figer_echeancier

SCRIPT = """PARAM COUPON = 8%
CONSTAT() OBS AVG PERIOD
AT OBS:
  PAY COUPON * INDEX "coupon"
AT OBS.last.last:
  PAY 1 "PDI sur cloture"
"""

CAL = {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
               "roll_date": "2029-09-10", "frequency": "1Y",
               "stub": "short_last", "window_frequency": "3M"}}


class _Body:
    """Le minimum que `_figer_echeancier` lit d'un DealCreate."""

    def __init__(self, script=SCRIPT, constats=None, strike="2026-09-10",
                 devise="EUR"):
        self.script_snapshot = script
        self.market_snapshot = {"constats": constats if constats is not None else CAL}
        self.strike_date = strike
        self.value_date = "2026-09-14"
        self.devise = devise


def _fige(**kw):
    return json.loads(_figer_echeancier(_Body(**kw)))


def test_le_booking_fige_les_dates_calendaires():
    """C'est la raison d'être du champ : des dates opposables, pas des
    year-fractions à re-convertir."""
    d = _fige()
    assert [c["date"] for c in d["constatations"]] == [
        "2027-09-10", "2028-09-10", "2029-09-10"]


def test_il_fige_les_releves_de_chaque_constatation():
    """Sans eux, un cycle de vie ne saurait pas quels cours collecter pour
    reconstituer la moyenne d'une constatation."""
    d = _fige()
    for c in d["constatations"]:
        assert len(c["releves"]) == 4
        assert c["releves"][-1]["date"] == c["date"]
        assert all(r["date"] for r in c["releves"])


def test_il_fige_le_rang_la_reduction_et_les_blocs():
    """Le rang décide de la ligne de `PARAM()` lue et du coupon versé ; la
    réduction, de ce qui est constaté ; les blocs, de l'ordre contractuel
    d'exécution. Les trois doivent survivre au booking."""
    d = _fige()
    assert [c["rang"] for c in d["constatations"]] == [1, 2, 3]
    assert {c["reduction"] for c in d["constatations"]} == {"AVG"}
    assert [c["blocs"] for c in d["constatations"]] == [[0], [0], [0, 1]]


def test_il_marque_le_releve_qui_declenche_aussi_un_evenement():
    """`AT OBS.last.last` : un même cours alimente la moyenne ET déclenche la
    protection. Le figer permettra de n'enregistrer qu'un seul fixing officiel
    pour les deux usages."""
    d = _fige()
    marques = [(c["rang"], r["date"]) for c in d["constatations"]
               for r in c["releves"] if r["evenement"]]
    assert marques == [(3, "2029-09-10")]


def test_un_ancrage_different_donne_un_echeancier_different():
    """Garde-fou : le figement doit dépendre de la date de strike, sinon il ne
    fige rien d'utile. Deux deals du même script à deux strikes différents n'ont
    pas le même échéancier."""
    a = _fige()
    b = _fige(strike="2027-03-10")
    assert a["constatations"][0]["t"] != b["constatations"][0]["t"]
    # Les dates calendaires, elles, viennent du calendrier saisi : c'est
    # l'origine de l'axe des temps qui bouge, pas les constatations.
    assert a["constatations"][0]["date"] == b["constatations"][0]["date"]


def test_un_script_non_resoluble_ne_bloque_pas_le_booking():
    """Un échéancier qu'on ne sait pas résoudre laisse le champ vide — ce qui se
    lit comme « pas d'échéancier figé », la vérité — plutôt que de faire échouer
    le booking ou, pire, d'enregistrer un calendrier partiel."""
    assert _fige(constats={}) == {}
    assert _fige(script="ceci n'est pas un script") == {}


def test_un_produit_en_mode_normal_est_fige_aussi():
    """Dates écrites en dur, aucun CONSTAT : le produit se booke comme les
    autres et son échéancier doit l'être aussi — sans dates calendaires, que le
    script ne porte pas."""
    d = _fige(script="AT 1, 2, 3:\n  PAY INDEX\n", constats={})
    assert [c["rang"] for c in d["constatations"]] == [1, 2, 3]
    assert all(c["date"] is None for c in d["constatations"])


def test_la_fenetre_de_depart_est_figee_a_part():
    """`STRIKE_FIX` fixe S0 : ses relevés doivent être collectés comme les
    autres, mais elle n'est pas une constatation et rien ne s'y déclenche."""
    d = _fige(script="CONSTAT STRIKE_FIX AVG\nCONSTAT MAT\nAT MAT:\n  PAY WOF\n",
              constats={"STRIKE_FIX": {"date": "2026-09-10", "window_length": "10D",
                                       "window_frequency": "1D"},
                        "MAT": "2029-09-10"})
    assert d["depart"]["reduction"] == "AVG"
    assert len(d["depart"]["releves"]) == 10
    assert len(d["constatations"]) == 1


def test_le_json_fige_est_stable():
    """Deux figements du même corps donnent le même JSON : sans quoi comparer
    un deal à son propre échéancier ne voudrait rien dire."""
    assert _figer_echeancier(_Body()) == _figer_echeancier(_Body())
