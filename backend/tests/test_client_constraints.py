"""Client Intelligence — les contraintes institutionnelles et leur verrou.

Le partage entre utilisateurs a décidé la forme de ce modèle. Un blob JSON
unique se lit, se modifie et se réécrit en entier : deux commerciaux qui
éditent la même fiche font tous deux un aller-retour complet, et le second
écrase le premier **sans erreur ni trace**. C'est la perte qu'on ne découvre
que le jour où une contrainte absente laisse passer un produit qu'elle aurait
dû bloquer.

D'où la coupure : les sept scalaires sont des colonnes — deux UPDATE sur deux
colonnes différentes survivent tous les deux — et les listes restent en JSON
sous un compteur de version, sur le modèle de Deal.contract_version.

Le reste tient sur un principe simple : une contrainte mal saisie qui ne
s'applique jamais est pire qu'une contrainte absente, parce qu'on croit
qu'elle protège.
"""
import json

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.core.client_controls import (
    ClientRuleError, apply_constraints, rating_rank, read_constraints,
    require_constraints_version, validate_constraints, validate_rating,
    validate_scalar_constraints, RATING_SCALE,
)
from backend.app.db.models import Client


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _client(session: Session) -> Client:
    client = Client(name="XYZ Asset Management", entity_id=1)
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


# ── Le verrou optimiste, raison d'être du modèle ─────────────────────

def test_deux_editions_concurrentes_la_seconde_est_refusee_pas_perdue():
    """Le scénario exact qui a décidé la forme du modèle : A et B chargent la
    même fiche, A enregistre, puis B enregistre à son tour. B doit être REFUSÉ
    avec un message, pas écraser silencieusement le travail de A."""
    session = _session()
    client = _client(session)

    version_vue_par_a = client.constraints_version
    version_vue_par_b = client.constraints_version      # même point de départ

    apply_constraints(client, {"currencies": ["EUR", "USD"]}, version_vue_par_a)
    session.commit()

    with pytest.raises(ClientRuleError) as capture:
        apply_constraints(client, {"asset_classes": ["equity"]}, version_vue_par_b)
    assert capture.value.code == "CONSTRAINTS_VERSION_STALE"
    assert "modifiées entre-temps" in capture.value.message

    # Et le travail de A est intact.
    assert read_constraints(client)["currencies"] == ["EUR", "USD"]


def test_une_ecriture_sur_la_version_a_jour_passe():
    session = _session()
    client = _client(session)
    apply_constraints(client, {"currencies": ["EUR"]}, client.constraints_version)
    session.commit()
    apply_constraints(client, {"currencies": ["EUR", "CHF"]},
                      client.constraints_version)
    session.commit()
    assert read_constraints(client)["currencies"] == ["EUR", "CHF"]


def test_la_version_avance_a_chaque_ecriture():
    session = _session()
    client = _client(session)
    assert client.constraints_version == 1
    apply_constraints(client, {"currencies": ["EUR"]}, 1)
    assert client.constraints_version == 2
    apply_constraints(client, {"currencies": ["USD"]}, 2)
    assert client.constraints_version == 3


def test_une_ecriture_sans_version_est_refusee():
    """Un appelant qui n'envoie pas de version contourne le verrou : refusé,
    plutôt que d'accepter et de rouvrir la fenêtre de perte."""
    session = _session()
    client = _client(session)
    with pytest.raises(ClientRuleError) as capture:
        apply_constraints(client, {"currencies": ["EUR"]}, None)
    assert capture.value.code == "CONSTRAINTS_VERSION_REQUIRED"


def test_les_scalaires_se_modifient_sans_toucher_au_verrou():
    """C'est tout l'intérêt de les avoir sortis du blob : deux personnes qui
    modifient l'une le ticket, l'autre le rating, ne se gênent pas."""
    session = _session()
    client = _client(session)
    version = client.constraints_version
    client.ticket_min = 500_000.0
    client.min_rating = "A-"
    session.add(client)
    session.commit()
    assert client.constraints_version == version   # le verrou n'a pas bougé


# ── Le schéma strict ─────────────────────────────────────────────────

def test_une_cle_inconnue_est_refusee():
    """« minRating » rangé à côté de min_rating serait une contrainte qui ne
    s'applique jamais — et rien ne le signalerait."""
    with pytest.raises(ClientRuleError) as capture:
        validate_constraints({"minRating": "A-"})
    assert capture.value.code == "CONSTRAINTS_UNKNOWN_KEY"
    assert "minRating" in capture.value.message


def test_un_vocabulaire_hors_liste_est_refuse():
    with pytest.raises(ClientRuleError) as capture:
        validate_constraints({"asset_classes": ["equity", "crypto"]})
    assert capture.value.code == "CONSTRAINTS_VOCABULARY_INVALID"
    assert "crypto" in capture.value.message


def test_une_liste_attendue_qui_n_en_est_pas_une_est_refusee():
    with pytest.raises(ClientRuleError) as capture:
        validate_constraints({"currencies": "EUR"})
    assert capture.value.code == "CONSTRAINTS_SHAPE_INVALID"


def test_un_issuer_se_stocke_avec_son_identifiant_et_son_libelle():
    """Le pointeur pour résoudre, le libellé pour rester lisible si la ligne
    disparaît du catalogue — même motif que rfq_provenance_json."""
    propre = validate_constraints({
        "excluded_issuers": [{"id": 12, "label": "Marex"},
                             {"id": None, "label": "Banque inconnue"}]})
    assert propre["excluded_issuers"][0]["label"] == "Marex"


def test_un_issuer_sans_libelle_est_refuse():
    with pytest.raises(ClientRuleError) as capture:
        validate_constraints({"excluded_issuers": [{"id": 12}]})
    assert capture.value.code == "CONSTRAINTS_SHAPE_INVALID"


def test_un_blob_complet_et_valide_passe():
    propre = validate_constraints({
        "currencies": ["EUR", "CHF"],
        "asset_classes": ["equity", "credit"],
        "underlying_universe": ["EuroStoxx 50", "CAC 40"],
        "product_types": ["autocall", "phoenix"],
        "allowed_issuers": [{"id": 3, "label": "BNP Paribas"}],
        "excluded_issuers": [{"id": 12, "label": "Marex"}],
        "internal_constraints": "Comité produit mensuel",
        "commercial_notes": "Sensible au niveau de barrière",
    })
    assert len(propre) == 8


# ── Le rating se compare par rang, jamais alphabétiquement ───────────

def test_le_rang_suit_la_qualite_de_credit_pas_l_alphabet():
    """Piège : trier des notations comme des chaînes inverse leur sens.

    AA- vaut mieux que A+ — c'est un cran au-dessus. Mais l'alphabet place
    « A+ » AVANT « AA- », donc un tri naïf ferait passer A+ pour le meilleur
    des deux, et une contrainte « au minimum AA- » accepterait A+.
    """
    assert rating_rank("AAA") < rating_rank("A-") < rating_rank("BBB")
    assert rating_rank("AA-") < rating_rank("A+")   # la réalité du crédit
    assert "A+" < "AA-"                             # l'alphabet, lui, ment
    assert rating_rank("A") < rating_rank("BBB+")


def test_un_client_exigeant_A_moins_refuse_BBB_accepte_AA():
    """La requête d'éligibilité, réduite à sa comparaison."""
    minimum = rating_rank("A-")
    assert rating_rank("AA") <= minimum        # accepté
    assert rating_rank("A-") <= minimum        # accepté, à la limite
    assert not rating_rank("BBB+") <= minimum  # refusé


def test_la_casse_et_les_espaces_ne_font_pas_echouer_une_notation():
    assert rating_rank(" a- ") == rating_rank("A-")


def test_une_notation_inventee_est_refusee():
    with pytest.raises(ClientRuleError) as capture:
        validate_rating("AAA+")
    assert capture.value.code == "RATING_INVALID"


def test_l_echelle_est_ordonnee_du_meilleur_au_pire():
    assert RATING_SCALE[0] == "AAA"
    assert RATING_SCALE[-1] == "D"
    assert list(RATING_SCALE) == sorted(RATING_SCALE, key=rating_rank)


# ── Bornes scalaires cohérentes ──────────────────────────────────────

def test_un_ticket_minimum_superieur_au_maximum_est_refuse():
    """Ce n'est pas « presque rien ne passe » : c'est RIEN qui passe, et
    silencieusement."""
    with pytest.raises(ClientRuleError) as capture:
        validate_scalar_constraints(ticket_min=5_000_000.0, ticket_max=1_000_000.0,
                                    maturity_min_months=None, maturity_max_months=None,
                                    min_rating=None, max_concentration_pct=None)
    assert capture.value.code == "CONSTRAINT_RANGE_INVALID"


def test_une_maturite_minimale_superieure_au_maximum_est_refusee():
    with pytest.raises(ClientRuleError):
        validate_scalar_constraints(ticket_min=None, ticket_max=None,
                                    maturity_min_months=60, maturity_max_months=36,
                                    min_rating=None, max_concentration_pct=None)


def test_une_concentration_au_dela_de_cent_pourcent_est_refusee():
    with pytest.raises(ClientRuleError) as capture:
        validate_scalar_constraints(ticket_min=None, ticket_max=None,
                                    maturity_min_months=None, maturity_max_months=None,
                                    min_rating=None, max_concentration_pct=150.0)
    assert "pourcentage" in capture.value.message


def test_une_maturite_de_dix_huit_mois_est_exprimable():
    """La raison d'être des mois plutôt que des années."""
    validate_scalar_constraints(ticket_min=None, ticket_max=None,
                                maturity_min_months=18, maturity_max_months=36,
                                min_rating="A-", max_concentration_pct=10.0)


def test_des_bornes_absentes_ne_bloquent_rien():
    """Un client sans contrainte saisie ne doit rien refuser."""
    validate_scalar_constraints(ticket_min=None, ticket_max=None,
                                maturity_min_months=None, maturity_max_months=None,
                                min_rating=None, max_concentration_pct=None)


# ── Relecture tolérante ──────────────────────────────────────────────

def test_une_fiche_sans_contrainte_se_relit_en_objet_vide():
    session = _session()
    client = _client(session)
    assert read_constraints(client) == {}


def test_un_blob_illisible_ne_fait_pas_tomber_l_ecran():
    """Une ligne écrite avant ce schéma, ou corrompue à la main, doit rendre
    un objet vide plutôt que casser la fiche client."""
    session = _session()
    client = _client(session)
    client.constraints_json = "pas du json"
    assert read_constraints(client) == {}
    client.constraints_json = json.dumps(["une", "liste"])
    assert read_constraints(client) == {}
