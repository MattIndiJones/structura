"""Le cycle de vie face aux constatations sur période — point 7 du §14.

Le rejeu officiel reconstitue une série à 252 pas, **constante par morceaux
entre les événements fixés**. Un relevé sans fixing hérite donc du dernier cours
connu : la constatation porte en partie sur une valeur reportée.

**Le report est assumé** — décision de Philippe : bloquer ferait qu'on n'aurait
jamais rien. Ce qui ne l'est pas, c'est le silence. Le rejeu aboutit toujours,
et il dit lesquelles de ses dates ont été reportées.

L'avertissement n'est pas générique, parce que le report ne coûte pas la même
chose partout : sur `AVG` un cours reporté pèse 1/N, sur `MIN`/`MAX` il peut
RENVERSER la décision — si le cours manquant était l'extrême de la fenêtre, le
niveau constaté ressort faux dans le sens favorable.
"""
import json

import pytest

from backend.app.core.lifecycle_controls import (
    path_dependency_reasons, releves_sans_fixing,
)


class _Deal:
    def __init__(self, schedule):
        self.schedule_json = json.dumps(schedule) if schedule is not None else ""


class _Event:
    def __init__(self, event_date, spots=None):
        self.event_date = event_date
        self.spots_json = json.dumps(spots or {})


def _echeancier(reduction="AVG", releves=("2026-12-10", "2027-03-10",
                                          "2027-06-10", "2027-09-10")):
    return {"constatations": [{
        "calendrier": "OBS", "rang": 1, "t": 1.0, "date": "2027-09-10",
        "reduction": reduction,
        "releves": [{"t": 0.0, "date": d, "evenement": False} for d in releves],
        "blocs": [0],
    }], "depart": None, "blocs_maturite": []}


# ── Le vocabulaire mort a disparu, la détection reste juste ────────────

def test_une_constatation_moyennee_n_est_plus_reputee_dependante_du_chemin():
    """`FIX_MIN/MAX/AVG` bloquaient le rejeu officiel : ils n'existent plus, et
    une constatation sur période se prouve désormais depuis les fixings de ses
    relevés. La bloquer serait refuser un produit parfaitement rejouable."""
    assert path_dependency_reasons(
        "CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF\n") == []


def test_une_barriere_americaine_reste_bloquee():
    """Garde-fou du précédent : `WOF_MIN` lit le chemin ENTRE les constatations,
    qu'aucun fixing événementiel ne prouve. Le refus doit tenir."""
    assert path_dependency_reasons(
        "AT MATURITY:\n  PAY INDIC(WOF_MIN < 0.6)\n") == ["WOF_MIN"]


# ── Une fenêtre incomplète ne se rejoue pas ────────────────────────────

def test_une_fenetre_sans_fixings_est_signalee():
    """Les dates reportées sont nommées, pas seulement comptées : c'est ce qui
    permet d'aller chercher les cours qui manquent."""
    manquants = releves_sans_fixing(_Deal(_echeancier()), [])
    assert manquants == ["2026-12-10", "2027-03-10", "2027-06-10", "2027-09-10"]


def test_une_fenetre_partiellement_fixee_est_signalee_aussi():
    """Le cas dangereux : trois relevés sur quatre. Le rejeu rend un nombre
    plausible — d'où l'obligation de dire lequel des quatre a été reporté."""
    events = [_Event(d, {"A": 100.0}) for d in
              ("2026-12-10", "2027-03-10", "2027-06-10")]
    assert releves_sans_fixing(_Deal(_echeancier()), events) == ["2027-09-10"]


def test_une_fenetre_complete_ne_bloque_rien():
    events = [_Event(d, {"A": 100.0}) for d in
              ("2026-12-10", "2027-03-10", "2027-06-10", "2027-09-10")]
    assert releves_sans_fixing(_Deal(_echeancier()), events) == []


def test_un_cours_nul_ne_compte_pas_comme_un_fixing():
    """Un événement créé au booking porte `{}` ou des zéros tant que le cours
    n'est pas saisi : il ne prouve rien."""
    events = [_Event("2026-12-10", {"A": 0.0}), _Event("2027-03-10", {})]
    manquants = releves_sans_fixing(_Deal(_echeancier()), events)
    assert "2026-12-10" in manquants and "2027-03-10" in manquants


# ── Ce qui ne déclare aucune fenêtre n'est pas concerné ─────────────────

def test_un_produit_ponctuel_n_est_pas_concerne():
    """L'immense majorité des produits : aucune fenêtre, donc rien à vérifier."""
    ponctuel = {"constatations": [{"calendrier": "OBS", "rang": 1, "t": 1.0,
                                   "date": "2027-09-10", "reduction": None,
                                   "releves": [], "blocs": [0]}],
                "depart": None, "blocs_maturite": []}
    assert releves_sans_fixing(_Deal(ponctuel), []) == []


def test_un_deal_sans_echeancier_fige_n_est_pas_bloque():
    """Un deal booké avant ce champ n'en déclare aucun : il continue de vivre
    comme avant plutôt que de se bloquer sur une information qu'il n'a pas."""
    assert releves_sans_fixing(_Deal(None), []) == []
    assert releves_sans_fixing(_Deal({}), []) == []


def test_un_echeancier_illisible_ne_leve_pas():
    """Un JSON corrompu ne doit pas faire tomber le cycle de vie d'un deal."""
    class _Casse:
        schedule_json = "{ceci n'est pas du json"
    assert releves_sans_fixing(_Casse(), []) == []


# ── L'avertissement dit ce que le report coûte ─────────────────────────

def test_l_avertissement_nomme_les_dates_reportees():
    from backend.app.core.lifecycle_controls import _avertissement_report
    a = _avertissement_report(_Deal(_echeancier()), ["2027-03-10", "2027-06-10"])
    assert a["code"] == "OFFICIAL_WINDOW_CARRIED_FORWARD"
    assert a["dates"] == ["2027-03-10", "2027-06-10"]
    assert "reporté" in a["message"]


def test_sur_une_moyenne_le_report_ne_renverse_pas_la_decision():
    """Un cours reporté pèse 1/N : l'erreur est bornée. L'avertissement le dit
    sans dramatiser."""
    from backend.app.core.lifecycle_controls import _avertissement_report
    a = _avertissement_report(_Deal(_echeancier("AVG")), ["2027-03-10"])
    assert a["peut_renverser_la_decision"] is False
    assert "RENVERSER" not in a["message"]


@pytest.mark.parametrize("reduction", ["MIN", "MAX"])
def test_sur_un_extreme_le_report_peut_renverser_la_decision(reduction):
    """Si le cours manquant était le plus bas de la fenêtre, le minimum reporté
    ressort trop haut et le produit ne knock-in pas. Ce n'est plus une
    imprécision : l'avertissement doit distinguer ce cas."""
    from backend.app.core.lifecycle_controls import _avertissement_report
    a = _avertissement_report(_Deal(_echeancier(reduction)), ["2027-03-10"])
    assert a["peut_renverser_la_decision"] is True
    assert "RENVERSER" in a["message"]
    assert reduction in a["message"]
