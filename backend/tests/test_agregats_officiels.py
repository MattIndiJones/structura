"""L'agrégat officiel d'une constatation moyennée — point 6 du §14.

Deux invariants du plan se jouent ici : **aucune moyenne partielle silencieuse**,
et **la réduction est par sous-jacent avant toute agrégation panier**. Les tests
vérifient surtout ce que le calcul REFUSE de faire.
"""
import pytest

from backend.app.core.agregats_officiels import (
    Agregat, Neutralisation, calculer, est_perime,
)

DATES = ["2026-12-10", "2027-03-10", "2027-06-10", "2027-09-10"]


def _fixings(par_date, version=1):
    return {d: {"spots": s, "version": version} for d, s in par_date.items()}


COMPLET = _fixings({
    "2026-12-10": {"A": 100.0, "B": 90.0},
    "2027-03-10": {"A": 110.0, "B": 80.0},
    "2027-06-10": {"A": 120.0, "B": 70.0},
    "2027-09-10": {"A": 130.0, "B": 60.0},
})


# ── La réduction est par sous-jacent ───────────────────────────────────

def test_avg_moyenne_chaque_sous_jacent_separement():
    a = calculer("AVG", DATES, COMPLET)
    assert a.calculable
    assert a.niveaux == {"A": 115.0, "B": 75.0}


def test_min_et_max_prennent_l_extreme_de_chaque_sous_jacent():
    assert calculer("MIN", DATES, COMPLET).niveaux == {"A": 100.0, "B": 60.0}
    assert calculer("MAX", DATES, COMPLET).niveaux == {"A": 130.0, "B": 90.0}


def test_la_reduction_ne_prend_jamais_l_agregat_panier():
    """Le worst-of se calcule APRÈS, dans le payoff. Ici, `B` est le plus bas à
    chaque date : réduire l'agrégat donnerait la moyenne des worst-of (75), qui
    se trouve coïncider avec la moyenne de B — le vrai test est que `A` garde sa
    propre moyenne au lieu de disparaître."""
    a = calculer("AVG", DATES, COMPLET)
    assert set(a.niveaux) == {"A", "B"}
    assert a.niveaux["A"] == 115.0, "le sous-jacent A a été absorbé par l'agrégat"


# ── Une fenêtre incomplète ne rend pas d'agrégat ───────────────────────

def test_une_fenetre_incomplete_est_refusee_et_dit_ce_qui_manque():
    """Pas de moyenne sur ce qui est disponible : une moyenne partielle qui se
    présente comme une moyenne est un chiffre faux qui ne se signale pas."""
    partiel = {d: COMPLET[d] for d in DATES[:2]}
    a = calculer("AVG", DATES, partiel)
    assert not a.calculable and not a.niveaux
    assert a.manquants == ("2027-06-10", "2027-09-10")
    assert "moyenne partielle" in a.motif


def test_un_sous_jacent_sans_cours_sur_toute_la_fenetre_bloque():
    """Réduire un actif sur les seules dates où il a un cours le comparerait à
    ses pairs sur une base différente, dans le calcul même du worst-of."""
    boiteux = _fixings({
        "2026-12-10": {"A": 100.0, "B": 90.0},
        "2027-03-10": {"A": 110.0},          # B absent
        "2027-06-10": {"A": 120.0, "B": 70.0},
        "2027-09-10": {"A": 130.0, "B": 60.0},
    })
    a = calculer("AVG", DATES, boiteux)
    assert not a.calculable
    assert a.incomplets == ("B",)


def test_une_reduction_inconnue_est_refusee():
    assert not calculer("MEDIANE", DATES, COMPLET).calculable


# ── La neutralisation, seule issue au blocage ──────────────────────────

def test_un_releve_neutralise_sort_du_calcul_avec_sa_trace():
    """Un férié imprévu, une source indisponible, un titre suspendu : sans
    échappement, le produit se bloque sans recours. Avec, le motif et l'auteur
    voyagent avec le calcul."""
    partiel = {d: COMPLET[d] for d in DATES if d != "2027-03-10"}
    n = Neutralisation("2027-03-10", "bourse fermée — férié non calendaire", "philippe")
    a = calculer("AVG", DATES, partiel, neutralises=(n,))
    assert a.calculable
    assert a.niveaux == {"A": (100 + 120 + 130) / 3, "B": (90 + 70 + 60) / 3}
    assert a.neutralises[0].motif.startswith("bourse fermée")
    assert a.to_dict()["neutralises"] == [
        {"date": "2027-03-10", "motif": "bourse fermée — férié non calendaire",
         "par": "philippe"}]


def test_neutraliser_toute_la_fenetre_ne_donne_pas_un_agregat_vide():
    """Il resterait zéro relevé : rendre un niveau serait l'inventer."""
    n = tuple(Neutralisation(d, "test", "u") for d in DATES)
    a = calculer("AVG", DATES, {}, neutralises=n)
    assert not a.calculable and "neutralisés" in a.motif


# ── Périmé après correction d'un fixing ────────────────────────────────

def test_un_agregat_est_perime_quand_un_fixing_est_corrige():
    """Une correction crée une nouvelle version : tout ce qui a été décidé sur
    l'ancienne doit cesser d'être applicable."""
    a = calculer("AVG", DATES, COMPLET)
    assert a.versions == (1,)
    assert not est_perime(a, {}, DATES, COMPLET)
    corrige = {**{d: 1 for d in DATES}, "2027-06-10": 2}
    assert est_perime(a, corrige, DATES, COMPLET)


def test_une_correction_rendant_la_meme_valeur_perime_quand_meme():
    """Comparer les versions, pas les valeurs : une correction qui rend le même
    cours reste une correction, et l'auditeur doit voir qu'elle a eu lieu."""
    a = calculer("AVG", DATES, COMPLET)
    identique = _fixings({d: COMPLET[d]["spots"] for d in DATES}, version=2)
    assert est_perime(a, {d: 2 for d in DATES}, DATES, identique)


def test_un_agregat_non_calculable_n_est_pas_perimable():
    """Rien n'a été décidé sur lui : il n'y a rien à périmer."""
    a = calculer("AVG", DATES, {})
    assert not a.calculable and not est_perime(a, {}, DATES, {})
