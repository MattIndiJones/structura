"""Le moteur de cycles — et surtout ce qu'il refuse de dire.

Un moteur de prédiction se juge autant sur ses silences que sur ses réponses.
La moitié de ces tests vérifient qu'il ne produit RIEN : pas de fenêtre sur un
trade unique, pas de cadence nommée quand la dispersion l'interdit, pas de
recommandation de contact sans cadence connue.

L'autre moitié vérifie les trois choix de méthode :
  • la médiane décide, la moyenne informe ;
  • la fenêtre s'élargit quand le passé est irrégulier ;
  • le retard se mesure contre SA propre cadence, jamais contre un seuil absolu.

Toutes les dates sont explicites et `asof` est toujours passé : un test qui
dépend du jour où il tourne finit par échouer un lundi sans que personne ne
sache pourquoi.
"""
from datetime import date, timedelta

import pytest

from backend.app.core.client_cycle import (
    CONFIANCE_BASSE, CONFIANCE_HAUTE, CONFIANCE_MOYENNE, HISTORIQUE_INSUFFISANT,
    Cycle, compare_cycles, compute_cycle, default_lead_days, observed_lead_days,
    recommend_contact_window,
)


def _serie(depart: str, intervalles: list[int]) -> list[date]:
    """Une série de dates espacées des intervalles donnés."""
    courante = date.fromisoformat(depart)
    dates = [courante]
    for jours in intervalles:
        courante = courante + timedelta(days=jours)
        dates.append(courante)
    return dates


# ── Ce que le moteur refuse de dire ──────────────────────────────────

def test_aucune_transaction_ne_produit_aucune_prediction():
    cycle = compute_cycle([], asof=date(2026, 8, 31))
    assert cycle.confidence == HISTORIQUE_INSUFFISANT
    assert cycle.expected_window_start is None
    assert cycle.median_interval_days is None
    assert cycle.explanation


def test_une_seule_transaction_ne_produit_aucune_fenetre():
    """Un point unique ne porte aucun intervalle. Extrapoler dessus donnerait
    un chiffre que personne ne pourrait ni vérifier ni contredire."""
    cycle = compute_cycle([date(2026, 3, 1)], asof=date(2026, 8, 31))
    assert cycle.n_trades == 1
    assert cycle.confidence == HISTORIQUE_INSUFFISANT
    assert cycle.expected_window_start is None
    assert "aucun intervalle mesurable" in " ".join(cycle.explanation)
    # Le fait brut, lui, reste disponible : il est observé, pas déduit.
    assert cycle.days_since_last == 183


def test_deux_transactions_donnent_un_intervalle_mais_peu_de_confiance():
    cycle = compute_cycle(_serie("2026-01-01", [90]), asof=date(2026, 4, 15))
    assert cycle.n_intervals == 1
    assert cycle.median_interval_days == 90.0
    assert cycle.confidence == CONFIANCE_BASSE
    # Une fenêtre existe, mais élargie et annoncée comme telle.
    assert cycle.expected_window_start is not None
    assert "élargie par défaut" in " ".join(cycle.explanation)


def test_une_cadence_trop_dispersee_n_est_pas_nommee():
    """L'appeler « trimestrielle » alors qu'elle varie du simple au quintuple
    serait une étiquette fausse."""
    cycle = compute_cycle(_serie("2024-01-01", [20, 200, 15, 300, 25]),
                          asof=date(2026, 1, 1))
    assert cycle.cadence == "irreguliere"
    assert cycle.confidence == CONFIANCE_BASSE


def test_aucune_fenetre_de_contact_sans_cadence_connue():
    """Recommander une date d'appel sur un client dont on ignore le rythme
    serait une recommandation inventée."""
    fenetre = recommend_contact_window(compute_cycle([], asof=date(2026, 8, 31)))
    assert fenetre.start is None
    assert fenetre.lead_source == "none"
    assert "Cadence inconnue" in " ".join(fenetre.explanation)


# ── La médiane décide, la moyenne informe ────────────────────────────

def test_une_pause_exceptionnelle_ne_deforme_pas_la_cadence():
    """Le cœur du choix de méthode. Cinq trimestres réguliers et une pause d'un
    an : la moyenne ment, la médiane tient."""
    cycle = compute_cycle(_serie("2023-01-01", [90, 92, 88, 365, 91, 89]),
                          asof=date(2025, 6, 1))
    assert cycle.median_interval_days == 90.5
    # La moyenne, elle, est tirée vers le haut de plus de trente jours.
    assert cycle.mean_interval_days > 130
    assert cycle.cadence == "trimestrielle"


def test_la_moyenne_reste_rendue_pour_qui_veut_la_lire():
    cycle = compute_cycle(_serie("2026-01-01", [30, 30, 30]),
                          asof=date(2026, 4, 1))
    assert cycle.median_interval_days == 30.0
    assert cycle.mean_interval_days == 30.0


# ── La fenêtre s'élargit avec l'irrégularité ─────────────────────────

def test_une_cadence_reguliere_donne_une_fenetre_etroite():
    cycle = compute_cycle(_serie("2025-01-01", [90, 91, 89, 90, 92, 88]),
                          asof=date(2026, 8, 1))
    debut = date.fromisoformat(cycle.expected_window_start)
    fin = date.fromisoformat(cycle.expected_window_end)
    assert (fin - debut).days <= 8
    assert cycle.confidence == CONFIANCE_HAUTE


def test_une_cadence_irreguliere_donne_une_fenetre_large():
    regulier = compute_cycle(_serie("2025-01-01", [90, 91, 89, 90, 92]),
                             asof=date(2026, 8, 1))
    irregulier = compute_cycle(_serie("2025-01-01", [40, 140, 60, 130, 50]),
                               asof=date(2026, 8, 1))
    largeur = lambda c: (date.fromisoformat(c.expected_window_end)
                         - date.fromisoformat(c.expected_window_start)).days
    assert largeur(irregulier) > largeur(regulier)


def test_la_fenetre_n_est_jamais_reduite_a_un_jour():
    """Même sur une cadence parfaite, personne ne traite au jour près."""
    cycle = compute_cycle(_serie("2026-01-01", [30, 30, 30, 30, 30]),
                          asof=date(2026, 6, 1))
    debut = date.fromisoformat(cycle.expected_window_start)
    fin = date.fromisoformat(cycle.expected_window_end)
    assert (fin - debut).days >= 6


# ── La confiance exige les deux : du volume ET de la régularité ──────

def test_beaucoup_d_observations_regulieres_donnent_une_confiance_haute():
    cycle = compute_cycle(_serie("2025-01-01", [30, 31, 29, 30, 30, 31]),
                          asof=date(2025, 7, 1))
    assert cycle.confidence == CONFIANCE_HAUTE


def test_beaucoup_d_observations_irregulieres_ne_suffisent_pas():
    """Douze trades erratiques n'autorisent pas plus de certitude que trois."""
    cycle = compute_cycle(_serie("2024-01-01", [10, 120, 15, 200, 20, 180]),
                          asof=date(2026, 1, 1))
    assert cycle.confidence == CONFIANCE_BASSE


def test_peu_d_observations_regulieres_donnent_une_confiance_moyenne():
    cycle = compute_cycle(_serie("2026-01-01", [60, 62, 58]),
                          asof=date(2026, 6, 1))
    assert cycle.confidence == CONFIANCE_MOYENNE


def test_chaque_resultat_porte_ses_observations_en_clair():
    """§47 — une confiance doit toujours pouvoir s'expliquer."""
    cycle = compute_cycle(_serie("2025-01-01", [92, 90, 91, 89, 93]),
                          asof=date(2026, 3, 1))
    texte = " ".join(cycle.explanation)
    assert "6 transactions observées" in texte
    assert "Intervalle médian" in texte
    assert "Dernière transaction" in texte


# ── Le retard est relatif à SA cadence ───────────────────────────────

def test_un_trimestriel_muet_depuis_cent_jours_n_est_pas_en_retard():
    cycle = compute_cycle(_serie("2025-06-01", [90, 91, 89]),
                          asof=date(2025, 6, 1) + timedelta(days=270 + 100))
    assert cycle.overdue is False


def test_un_mensuel_muet_depuis_cent_jours_est_en_retard():
    """Même délai absolu, verdict opposé : c'est tout l'objet du §51."""
    cycle = compute_cycle(_serie("2025-06-01", [30, 31, 29]),
                          asof=date(2025, 6, 1) + timedelta(days=90 + 100))
    assert cycle.overdue is True
    assert cycle.overdue_by_days > 0
    assert "Au-delà du délai habituel" in " ".join(cycle.explanation)


def test_un_client_dans_les_temps_n_est_pas_signale():
    depart = date(2026, 1, 1)
    dates = _serie(depart.isoformat(), [90, 90, 90])
    cycle = compute_cycle(dates, asof=dates[-1] + timedelta(days=30))
    assert cycle.overdue is False


# ── Fenêtre de contact ───────────────────────────────────────────────

def test_la_fenetre_de_contact_recule_du_delai_observe():
    """§49 — si le client traite fin novembre et que les discussions
    commencent deux semaines avant, il faut appeler début novembre."""
    cycle = compute_cycle(_serie("2025-01-01", [90, 91, 89, 90]),
                          asof=date(2026, 1, 1))
    fenetre = recommend_contact_window(cycle, lead_days=14)
    assert fenetre.lead_source == "observed"
    assert fenetre.lead_days == 14
    ecart = (date.fromisoformat(cycle.expected_window_start)
             - date.fromisoformat(fenetre.start)).days
    assert ecart == 14


def test_sans_delai_observable_le_defaut_configure_s_applique(monkeypatch):
    monkeypatch.setenv("STRUCTURA_CLIENT_DEFAULT_LEAD_DAYS", "21")
    assert default_lead_days() == 21
    cycle = compute_cycle(_serie("2025-01-01", [90, 91, 89, 90]),
                          asof=date(2026, 1, 1))
    fenetre = recommend_contact_window(cycle, lead_days=None)
    assert fenetre.lead_source == "default"
    assert fenetre.lead_days == 21
    assert "valeur par défaut" in " ".join(fenetre.explanation)


def test_le_delai_observe_est_une_mediane_pas_une_moyenne():
    """Un dossier qui a traîné six mois ne doit pas déplacer la recommandation
    faite sur tous les autres."""
    paires = [
        (date(2026, 1, 1), date(2026, 1, 15)),   # 14 jours
        (date(2026, 2, 1), date(2026, 2, 15)),   # 14 jours
        (date(2026, 3, 1), date(2026, 3, 16)),   # 15 jours
        (date(2025, 1, 1), date(2025, 7, 1)),    # 181 jours, l'exception
    ]
    assert observed_lead_days(paires) == 14.5


def test_une_paire_incoherente_est_ecartee():
    """Une discussion postérieure au trade est une saisie fausse, pas un délai
    négatif à moyenner."""
    paires = [(date(2026, 1, 1), date(2026, 1, 15)),
              (date(2026, 3, 1), date(2026, 2, 1))]
    assert observed_lead_days(paires) == 14.0


def test_aucune_paire_exploitable_rend_none():
    assert observed_lead_days([]) is None


# ── Comparaison des trois niveaux, sans causalité ────────────────────

def test_une_cadence_stable_entre_deux_societes_se_lit_comme_telle():
    """Jean traitait tous les 90 jours chez Bank A, il traite toujours tous les
    90 jours chez Bank B, où les autres traitent tous les 30."""
    personnel = compute_cycle(_serie("2024-01-01", [90, 90, 90, 90]),
                              asof=date(2026, 1, 1))
    affiliation = compute_cycle(_serie("2026-01-01", [90, 91, 89]),
                                asof=date(2026, 8, 1))
    organisation = compute_cycle(_serie("2026-01-01", [30, 30, 30, 31]),
                                 asof=date(2026, 8, 1))

    lecture = compare_cycles(personnel, affiliation, organisation)
    assert lecture["comparable"] is True
    assert lecture["closer_to"] == "personal"
    assert lecture["gap_to_personal_days"] < lecture["gap_to_organization_days"]


def test_une_cadence_qui_epouse_celle_de_la_maison_se_lit_aussi():
    personnel = compute_cycle(_serie("2024-01-01", [90, 90, 90, 90]),
                              asof=date(2026, 1, 1))
    affiliation = compute_cycle(_serie("2026-01-01", [31, 30, 29]),
                                asof=date(2026, 5, 1))
    organisation = compute_cycle(_serie("2026-01-01", [30, 30, 30, 31]),
                                 asof=date(2026, 5, 1))

    lecture = compare_cycles(personnel, affiliation, organisation)
    assert lecture["closer_to"] == "organization"


def test_la_comparaison_ne_conclut_jamais_a_une_cause():
    """§42 — le module décrit, il n'explique pas. Une personne a pu changer de
    poste, de mandat et de marché en même temps que d'employeur."""
    personnel = compute_cycle(_serie("2024-01-01", [90, 90, 90, 90]),
                              asof=date(2026, 1, 1))
    affiliation = compute_cycle(_serie("2026-01-01", [31, 30, 29]),
                                asof=date(2026, 5, 1))
    organisation = compute_cycle(_serie("2026-01-01", [30, 30, 30, 31]),
                                 asof=date(2026, 5, 1))
    texte = " ".join(compare_cycles(personnel, affiliation, organisation)["explanation"])

    assert "observation, pas explication" in texte
    for mot in ("cause", "à cause", "parce que", "explique"):
        assert mot not in texte.lower().replace("explication", "")
    # Et surtout : aucun score d'attribution du type « 73 % personnel ».
    lecture = compare_cycles(personnel, affiliation, organisation)
    assert "score" not in lecture
    assert all(not isinstance(v, float) or v == round(v, 1)
               for v in (lecture["gap_to_personal_days"],
                         lecture["gap_to_organization_days"]))


def test_sans_historique_dans_la_societe_actuelle_rien_n_est_comparable():
    personnel = compute_cycle(_serie("2024-01-01", [90, 90, 90]),
                              asof=date(2026, 1, 1))
    vide = compute_cycle([], asof=date(2026, 1, 1))
    lecture = compare_cycles(personnel, vide, vide)
    assert lecture["comparable"] is False
    assert "Trop peu de transactions" in " ".join(lecture["explanation"])
