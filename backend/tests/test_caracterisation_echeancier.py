"""Caractérisation du contrat d'exécution d'un échéancier — AVANT refonte.

Ce fichier ne teste pas une fonctionnalité : il **fige le comportement actuel**
du moteur sur les points que la refonte de l'échéancier va toucher, pour que
toute modification ultérieure ait à s'expliquer. C'est le point 1 de l'ordre de
réalisation (CONSTATATIONS_PERIODE_DESIGN.md §14), et la règle qui l'accompagne :
le moteur Monte-Carlo reste hors périmètre tant qu'un test ne démontre pas un
défaut précis.

Les réductions elles-mêmes — MIN/MAX/AVG, fenêtre de longueur ou de période,
réduction par sous-jacent avant l'agrégation — sont couvertes par
`test_constatations_periode.py`. Ici on caractérise ce qui reste : **quel niveau
chaque événement lit**, **dans quel ordre les blocs s'exécutent**, et **quel rang
d'observation ils voient**.

Trois de ces tests ont d'abord été écrits en `xfail(strict=True)` : ils
énonçaient le comportement voulu et échouaient, chiffrant l'écart. La correction
du §13 les a rendus verts, et `strict` a fait échouer la suite jusqu'à ce que
les marqueurs soient retirés — c'est ce qui a rendu la correction visible plutôt
qu'implicite.

Tous les cas sont déterministes : σ = 1 %, r = 0, deux chemins. Les niveaux
valent ~1,0, donc un `PAY INDEX` se lit directement dans la table de flux.
"""
from datetime import date

import pytest

from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import run_mc

TODAY = date(2026, 9, 10)

# Calendrier annuel sur 3 ans, relevé trimestriellement : 3 constatations de
# 4 relevés. C'est le cas de référence de toute la refonte.
CAL_ANNUEL = {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                      "roll_date": "2029-09-10", "frequency": "1Y",
                      "stub": "short_last", "window_frequency": "3M"}}

# Deux calendriers dans un même script — le cas qui révèle le rang partagé.
CAL_DEUX = {
    "COUPONS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                "roll_date": "2029-09-10", "frequency": "1Y", "stub": "short_last"},
    "SEMESTRES": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                  "roll_date": "2029-09-10", "frequency": "6M", "stub": "short_last"},
}


def _ul():
    """Sous-jacent quasi déterministe : le niveau reste à 1,0 à 1 % près."""
    return dict(name="A", ticker="", ccy="EUR", sigma=0.01, q=0.0,
                v0=0.0001, kappa=2.0, theta=0.0001, xi=0.05, rho_h=-0.7,
                alpha=0.01, beta=0.5, rho=-0.3, nu=0.1,
                sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)


def _flux(src, constats=None, user_params=None, T=3.0):
    """{(t arrondi, libellé): montant moyen} — la table de flux, lisible."""
    compiled = resolve_constats(parse_script(src), constats or CAL_ANNUEL,
                                anchor=TODAY, currency="EUR")
    res = run_mc(compiled, [_ul()], [[1.0]], r=0.0, T_max=T, N=2, model="constant",
                 seed=1, antithetic=False, user_params=user_params or {})
    return {(round(v["t"], 3), v["lbl"]): round(v["sum"] / 2, 4)
            for v in res["flux_table"].values()}


def _dates(src, constats=None):
    """Dates et réduction de chaque événement, après résolution."""
    compiled = resolve_constats(parse_script(src), constats or CAL_ANNUEL,
                                anchor=TODAY, currency="EUR")
    return [([round(d, 4) for d in e.dates], e.reduction) for e in compiled.events]


# ── A. Quel niveau chaque événement lit ────────────────────────────────

def test_un_evenement_principal_lit_l_agregat_de_sa_fenetre():
    """`AT OBS:` sur un CONSTAT réduit lit la RÉDUCTION de la fenêtre, pas le
    cours du jour. Le niveau étant ~1,0 partout ici, ce qu'on vérifie est le
    câblage : l'événement porte bien une réduction et une fenêtre de 4 relevés."""
    evs = _dates("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF\n")
    dates, reduction = evs[0]
    assert len(dates) == 3, dates
    assert reduction == "AVG"


def test_un_evenement_sur_releve_lit_le_cours_brut():
    """Un second niveau de qualificateur désigne un RELEVÉ : l'événement perd
    la réduction et lit le cours de ce jour-là. C'est ce qui permet à un PDI sur
    clôture de cohabiter avec un coupon sur moyenne."""
    evs = _dates("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY 0\n"
                 "AT OBS.last.last:\n  PAY WOF\n")
    (_, red_principal), (dates_releve, red_releve) = evs
    assert red_principal == "AVG"
    assert red_releve is None, "un relevé ne porte aucune réduction"
    assert len(dates_releve) == 1


def test_un_releve_isole_tombe_a_sa_propre_date():
    """`AT OBS[2][1]` vise le premier relevé de la deuxième fenêtre — une date
    qui n'est AUCUNE constatation. Le moteur doit donc l'évaluer à un pas qui
    lui est propre, et non replier l'événement sur une constatation voisine."""
    evs = _dates("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY 0\n"
                 "AT OBS[2][1]:\n  PAY 1\n")
    constatations = evs[0][0]
    (releve,), reduction = evs[1]
    assert reduction is None
    assert releve not in constatations, (releve, constatations)
    assert constatations[0] < releve < constatations[1]


def test_une_fenetre_d_un_seul_point_vaut_la_constatation_ponctuelle():
    """Le comportement historique est le cas dégénéré de la règle, pas un
    régime à part. Garde-fou : sans lui, un décalage d'indice dans la réduction
    passerait inaperçu — c'est exactement ce qui est arrivé."""
    ponctuel = _flux("CONSTAT MAT\nAT MAT:\n  PAY WOF\n",
                     constats={"MAT": "2029-09-10"})
    fenetre = _flux("CONSTAT MAT AVG\nAT MAT:\n  PAY WOF\n",
                    constats={"MAT": {"date": "2029-09-10", "window_length": "1D",
                                      "window_frequency": "1D"}})
    assert list(ponctuel.values()) == list(fenetre.values())


# ── B. Ordre d'exécution et STOP ───────────────────────────────────────

STOP_DABORD = """CONSTAT() OBS AVG PERIOD
AT OBS.last:
  PAY 1 "bloc avec STOP"
  STOP
AT OBS.last.last:
  PAY 99 "bloc suivant, meme jour"
"""

STOP_ENSUITE = """CONSTAT() OBS AVG PERIOD
AT OBS.last.last:
  PAY 99 "bloc suivant, meme jour"
AT OBS.last:
  PAY 1 "bloc avec STOP"
  STOP
"""


def test_un_stop_interrompt_les_blocs_suivants_du_meme_jour():
    """Deux blocs à la même date : le `STOP` du premier annule le second. C'est
    le comportement voulu — si un autocall rappelle, sa protection finale ne
    s'évalue pas."""
    f = _flux(STOP_DABORD)
    assert (3.0, "bloc avec STOP") in f
    assert (3.0, "bloc suivant, meme jour") not in f, (
        "le bloc postérieur au STOP a été évalué")


def test_l_ordre_du_script_fait_foi_a_date_egale():
    """Le même couple de blocs, écrit dans l'ordre inverse : les DEUX
    s'exécutent, puisque le `STOP` vient en dernier. L'ordre d'écriture est donc
    contractuel, pas cosmétique."""
    f = _flux(STOP_ENSUITE)
    assert f[(3.0, "bloc avec STOP")] == 1.0
    assert f[(3.0, "bloc suivant, meme jour")] == 99.0


# ── C. Rang d'observation — les défauts mesurés ────────────────────────
#
# `INDEX` s'incrémente aujourd'hui une fois par PAS DE GRILLE portant un
# événement, et non par constatation du calendrier que le bloc nomme. Les trois
# tests qui suivent énoncent la règle retenue (§13) et échouent donc, chacun sur
# un écart chiffré.

def test_index_compte_les_constatations_du_calendrier():
    """Cas sain, sans piège : un seul calendrier, aucun bloc sur une sous-date.
    `INDEX` vaut bien 1, 2, 3 — c'est la référence dont les deux cas suivants
    s'écartent."""
    f = _flux("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY INDEX\n")
    assert sorted(f.values()) == [1.0, 2.0, 3.0]


def test_index_est_independant_par_calendrier():
    """Deux calendriers dans un même script. `AT COUPONS:` doit voir le rang
    dans COUPONS — 1, 2, 3 — sans que le calendrier semestriel n'y touche.

    Le compteur global valait 2, 4, 6 : le calendrier semestriel doublait celui
    des coupons, et un `COUPON * INDEX` payait le double en silence."""
    f = _flux("CONSTAT() COUPONS\nCONSTAT() SEMESTRES\n"
              "AT COUPONS:\n  PAY INDEX\nAT SEMESTRES:\n  PAY 0 \"semestre\"\n",
              constats=CAL_DEUX)
    rangs = sorted(v for (t, lbl), v in f.items() if lbl != "semestre")
    assert rangs == [1.0, 2.0, 3.0]


def test_un_bloc_sur_une_sous_date_ne_decale_pas_les_constatations():
    """Ajouter `AT OBS[2][1]` ne doit rien changer au rang des constatations :
    une sous-date est un relevé, pas une observation.

    Le compteur global valait 1, 3, 4 : le bloc occupait son propre pas et
    décalait tout ce qui suivait."""
    f = _flux("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY INDEX\n"
              "AT OBS[2][1]:\n  PAY 0 \"releve\"\n")
    rangs = sorted(v for (t, lbl), v in f.items() if lbl != "releve")
    assert rangs == [1.0, 2.0, 3.0]


def test_param_par_observation_suit_le_calendrier_de_son_bloc():
    """« Une valeur par observation » doit désigner les observations du
    calendrier que le bloc nomme. Un tableau de barrières dégressives saisi pour
    COUPONS doit être lu ligne par ligne dans l'ordre.

    `PARAM()` héritait de la dérive d'`INDEX` : 0,22 / 0,44 / 0,66 au lieu de
    0,11 / 0,22 / 0,33 — une barrière fausse à chaque constatation, sur un
    produit très courant."""
    f = _flux("CONSTAT() COUPONS\nCONSTAT() SEMESTRES\nPARAM() BARRIERE = 100%\n"
              "AT COUPONS:\n  PAY BARRIERE\nAT SEMESTRES:\n  PAY 0 \"semestre\"\n",
              constats=CAL_DEUX,
              user_params={"BARRIERE": [0.11, 0.22, 0.33, 0.44, 0.55, 0.66]})
    lues = sorted(v for (t, lbl), v in f.items() if lbl != "semestre")
    assert lues == [0.11, 0.22, 0.33]


# ── D. Les deux écritures où le rang n'est pas défini ──────────────────

def test_index_est_refuse_dans_un_bloc_sans_echeancier():
    """`AT MATURITY` ne nomme aucun calendrier : le rang d'une observation s'y
    compte par rapport à quoi ? La question n'a pas de réponse, et aucun script
    du corpus n'y lit `INDEX` — le trou est fermé plutôt que documenté."""
    with pytest.raises(ValueError, match="ne nomme aucun échéancier"):
        parse_script("CONSTAT() OBS\nAT OBS:\n  PAY 1\nAT MATURITY:\n  PAY INDEX\n")


def test_un_bloc_a_dates_litterales_garde_son_rang():
    """`AT 1, 2, 3:` n'a pas de CONSTAT, mais il a bien un échéancier : sa
    propre liste de dates. `INDEX` y vaut 1, 2, 3 — le mode normal continue de
    fonctionner tel quel."""
    cs = parse_script("AT 1, 2, 3:\n  PAY INDEX\nAT MATURITY:\n  PAY 1\n")
    assert cs.events[0].ranks == [1, 2, 3]


def test_un_param_par_observation_lu_depuis_deux_calendriers_est_refuse():
    """« Une valeur par observation » suppose de savoir DE QUEL échéancier. Lu
    depuis deux calendriers de tailles différentes, un `PARAM()` n'a plus de
    nombre de lignes défini : refusé, avec un message qui dit quoi faire."""
    with pytest.raises(ValueError, match="plusieurs calendriers"):
        parse_script("CONSTAT() A\nCONSTAT() B\nPARAM() BAR = 100%\n"
                     "AT A:\n  PAY BAR\nAT B:\n  PAY BAR\n")


def test_deux_blocs_du_meme_calendrier_partagent_leur_param():
    """Garde-fou du précédent : `AT OBS:` et `AT OBS.last:` visent le MÊME
    échéancier. Le refus ne doit pas déborder sur cet usage, qui est l'idiome
    Athena le plus courant."""
    cs = parse_script("CONSTAT() OBS\nPARAM() BAR = 100%\n"
                      "AT OBS:\n  PAY BAR\nAT OBS.last:\n  PAY BAR\n")
    assert len(cs.events) == 2


def test_le_rang_survit_au_decalage_residuel():
    """Le cœur de la règle : le rang est porté par la DATE. Un produit vu à
    mi-vie garde donc le bon rang sur ses constatations restantes, sans qu'aucun
    compteur n'ait à être réamorcé — c'est ce qui rend `index_offset` inutile."""
    from backend.app.core.payscript.engine import _shift_events_for_mtf
    cs = parse_script("AT 1, 2, 3:\n  PAY INDEX\n")
    assert cs.events[0].ranks == [1, 2, 3]

    # À 1,5 an il reste les constatations de 2 et 3 ans : elles gardent les
    # rangs 2 et 3, et leurs dates sont recomptées depuis la valorisation.
    mi_vie = _shift_events_for_mtf(cs.events, 1.5)[0]
    assert mi_vie.dates == [0.5, 1.5], mi_vie.dates
    assert mi_vie.ranks == [2, 3], mi_vie.ranks

    # À 2 ans, une seule constatation reste, et c'est toujours la troisième.
    tardif = _shift_events_for_mtf(cs.events, 2.0)[0]
    assert tardif.dates == [1.0] and tardif.ranks == [3]
