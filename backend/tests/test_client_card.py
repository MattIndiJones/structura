"""La fiche visuelle — l'espace négatif, les bornes, et l'honnêteté du vide.

Deux exigences, opposées et également importantes.

**Sur un client établi**, l'écran doit dire ce qui n'est PAS traité : les
émetteurs autorisés jamais sollicités, ceux traités hors politique. C'est
l'information que personne ne demande et qui vaut le plus cher.

**Sur un client à deux transactions**, il doit refuser de parler : pas de
cadence nommée, pas de part sur deux lignes, pas de médiane là où deux points
sont plus honnêtes. Un écran qui invente sur un historique pauvre discrédite
tout ce qu'il affiche ailleurs.

Un troisième point est vérifié : le module ne prétend PAS savoir quand une
exclusion a été posée. Cette date n'est pas en base — `constraints_version`
avance sans conserver l'historique du blob. Distinguer « traité avant
l'exclusion » de « traité malgré elle » serait une invention.
"""
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.core.client_cycle import compute_cycle
from backend.app.core.client_intelligence import (
    _dates_de_trade, client_intelligence, deals_of_client, negative_space,
    next_thresholds, observed_ranges,
)
from backend.app.db.models import (
    Affiliation, Client, ClientTradeHistory, Opportunity, Person,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


CONTRAINTES = {
    "allowed_issuers": [{"id": 1, "label": "BNP Paribas"},
                        {"id": 2, "label": "Société Générale"},
                        {"id": 3, "label": "UBS"},
                        {"id": 4, "label": "Vontobel"}],
    "excluded_issuers": [{"id": 5, "label": "Marex"}],
    "currencies": ["EUR", "CHF", "USD"],
    "product_types": ["autocall", "phoenix", "capital_protected"],
}


def _client(session, *, contraintes=None, ticket=(500_000, 5_000_000),
            maturite=(12, 60)):
    import json
    client = Client(name="Rhône AM", entity_id=1, status="active",
                    constraints_json=json.dumps(contraintes or CONTRAINTES),
                    ticket_min=ticket[0], ticket_max=ticket[1],
                    maturity_min_months=maturite[0],
                    maturity_max_months=maturite[1])
    session.add(client); session.commit(); session.refresh(client)
    return client


def _trade(session, client, jour, *, emetteur="BNP Paribas", produit="Autocall",
           nominal=1_500_000.0, devise="EUR", maturite=None, ref=None):
    ligne = ClientTradeHistory(
        entity_id=1, client_id=client.id, trade_date=jour,
        maturity_date=maturite, product_type=produit, issuer=emetteur,
        currency=devise, notional=nominal, underlying="SX5E",
        external_ref=ref or f"X{jour}{emetteur}{nominal}")
    session.add(ligne); session.commit()
    return ligne


# ── L'espace négatif ─────────────────────────────────────────────────

def test_les_emetteurs_autorises_jamais_sollicites_sont_rendus():
    """L'ouverture commerciale : proposables dès demain."""
    session = _session()
    client = _client(session)
    _trade(session, client, "2024-01-15", emetteur="BNP Paribas")
    _trade(session, client, "2024-04-15", emetteur="UBS")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    utilises = {e["label"] for e in espace["issuers"]["used"]}
    jamais = {e["label"] for e in espace["issuers"]["never_used"]}

    assert utilises == {"BNP Paribas", "UBS"}
    assert jamais == {"Société Générale", "Vontobel"}
    assert espace["issuers"]["has_policy"] is True


def test_un_emetteur_traite_hors_liste_est_signale_avec_ses_dates():
    """Soit la liste est périmée, soit le contrôle a été contourné. Les deux
    méritent un appel — et les dates permettent de trancher."""
    session = _session()
    client = _client(session)
    _trade(session, client, "2025-10-21", emetteur="Natixis")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    a_verifier = espace["issuers"]["to_check"]
    assert len(a_verifier) == 1
    assert a_verifier[0]["label"] == "Natixis"
    assert a_verifier[0]["reason"] == "off_list"
    assert a_verifier[0]["first_date"] == "2025-10-21"


def test_un_emetteur_traite_bien_qu_exclu_est_signale_a_part():
    session = _session()
    client = _client(session)
    _trade(session, client, "2023-05-31", emetteur="Marex")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    a_verifier = espace["issuers"]["to_check"]
    assert a_verifier[0]["reason"] == "excluded"
    assert a_verifier[0]["declared_label"] == "Marex"
    # Et il ne figure pas dans « exclus, jamais traités ».
    assert espace["issuers"]["excluded"] == []


def test_le_module_ne_pretend_pas_savoir_quand_une_exclusion_a_ete_posee():
    """La date d'une exclusion n'est pas en base : `constraints_version` avance
    sans conserver l'historique du blob. Distinguer « traité avant » de
    « traité malgré » serait une invention — l'écran rend les dates et laisse
    juger."""
    session = _session()
    client = _client(session)
    _trade(session, client, "2023-05-31", emetteur="Marex")
    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    assert espace["exclusion_dates_unknown"] is True


def test_sans_politique_declaree_rien_n_est_hors_politique():
    """Signaler « hors politique » à un client qui n'en a déclaré aucune serait
    un faux positif garanti, et un signal faux se fait ignorer avec les vrais."""
    session = _session()
    client = _client(session, contraintes={})
    _trade(session, client, "2024-01-15", emetteur="Natixis")

    espace = negative_space(deals_of_client(session, client.id), {})
    assert espace["issuers"]["to_check"] == []
    assert espace["issuers"]["has_policy"] is False
    assert [e["label"] for e in espace["issuers"]["used"]] == ["Natixis"]


def test_le_rapprochement_ignore_la_casse_mais_affiche_la_saisie():
    session = _session()
    client = _client(session)
    _trade(session, client, "2024-01-15", emetteur="bnp paribas")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    # Rapproché malgré la casse — donc ni « hors liste », ni compté deux fois.
    assert espace["issuers"]["to_check"] == []
    # Mais affiché tel qu'il a été saisi.
    assert espace["issuers"]["used"][0]["label"] == "bnp paribas"


def test_un_nom_commercial_se_range_sous_sa_famille():
    """Le faux signal le plus visible du module.

    Un produit se saisit en texte libre — « Phoenix Memory », « Autocall
    Athena » — alors que la politique se déclare dans un vocabulaire fermé —
    `phoenix`, `autocall`. Comparés directement, ils ne correspondent jamais :
    l'écran signalait « Phoenix Memory, 8 transactions, absent de la liste
    autorisée » chez un client qui autorise explicitement les phoenix.

    Un signal faux se fait ignorer avec les vrais.
    """
    session = _session()
    client = _client(session)
    for jour in ("2024-01-15", "2024-04-15"):
        _trade(session, client, jour, produit="Phoenix Memory")
    _trade(session, client, "2024-07-15", produit="Autocall Athena")
    _trade(session, client, "2024-10-15", produit="Capital garanti")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    produits = espace["product_types"]

    assert produits["to_check"] == [], (
        "aucun de ces produits ne sort de la politique : phoenix, autocall et "
        "capital_protected y figurent tous")
    traites = {e["label"] for e in produits["used"]}
    assert traites == {"Phoenix Memory", "Autocall Athena", "Capital garanti"}
    # Les trois familles déclarées sont toutes couvertes par ces libellés :
    # aucune ne doit se proposer comme ouverture. Sans le rattachement à la
    # famille, les trois y figureraient — l'écran aurait annoncé « autocall,
    # phoenix, capital_protected jamais traités » à un client qui ne fait que ça.
    assert produits["never_used"] == []


def test_une_famille_declaree_et_jamais_traitee_reste_une_ouverture():
    """Le rattachement ne doit pas tout absorber : ce qui n'a réellement jamais
    été traité doit continuer de ressortir."""
    session = _session()
    contraintes = dict(CONTRAINTES,
                       product_types=["autocall", "phoenix", "twin_win"])
    client = _client(session, contraintes=contraintes)
    _trade(session, client, "2024-01-15", produit="Phoenix Memory")

    produits = negative_space(deals_of_client(session, client.id),
                              contraintes)["product_types"]
    jamais = {e["label"] for e in produits["never_used"]}
    assert jamais == {"autocall", "twin_win"}


def test_un_produit_inclassable_n_est_pas_une_anomalie():
    """« Je ne sais pas ranger ce nom » et « ce produit viole la politique »
    sont deux affirmations différentes. Les confondre fabrique exactement le
    faux positif que le module refuse partout ailleurs."""
    session = _session()
    client = _client(session)
    _trade(session, client, "2024-01-15", produit="Note structurée sur mesure")

    produits = negative_space(deals_of_client(session, client.id),
                              CONTRAINTES)["product_types"]
    assert produits["to_check"] == []
    entree = produits["used"][0]
    assert entree["label"] == "Note structurée sur mesure"
    assert entree["unclassified"] is True


def test_la_famille_se_deduit_du_libelle():
    from backend.app.core.client_intelligence import famille_de_produit
    assert famille_de_produit("Phoenix Memory") == "phoenix"
    assert famille_de_produit("Autocall Athena") == "autocall"
    assert famille_de_produit("Athena 3Y") == "autocall"
    assert famille_de_produit("Reverse Convertible") == "reverse_convertible"
    assert famille_de_produit("Capital garanti 5 ans") == "capital_protected"
    assert famille_de_produit("Twin Win") == "twin_win"
    # L'ordre des motifs compte : « reverse convertible » ne doit pas se faire
    # capturer par un motif plus court.
    assert famille_de_produit("Reverse convertible worst-of") == "reverse_convertible"
    assert famille_de_produit("Quelque chose d'inconnu") is None
    assert famille_de_produit(None) is None


def test_l_espace_negatif_couvre_devises_produits_et_sous_jacents():
    session = _session()
    client = _client(session)
    _trade(session, client, "2024-01-15", devise="EUR", produit="autocall")

    espace = negative_space(deals_of_client(session, client.id), CONTRAINTES)
    assert {e["label"] for e in espace["currencies"]["never_used"]} == {"CHF", "USD"}
    assert {e["label"] for e in espace["product_types"]["never_used"]} == {
        "phoenix", "capital_protected"}


# ── Les bornes : une bande, ou des points ────────────────────────────

def test_au_dela_du_seuil_les_bornes_rendent_une_bande():
    session = _session()
    client = _client(session)
    for i, montant in enumerate([1.0e6, 1.2e6, 1.5e6, 2.0e6, 2.4e6, 3.0e6]):
        _trade(session, client, f"2024-0{i + 1}-15", nominal=montant)

    bornes = observed_ranges(deals_of_client(session, client.id), client)
    ticket = bornes["ticket"]
    assert ticket["n"] == 6
    assert ticket["band"] is not None and len(ticket["band"]) == 2
    assert ticket["points"] == []
    assert ticket["declared_min"] == 500_000


def test_en_dessous_du_seuil_les_bornes_rendent_les_points():
    """Une moitié centrale calculée sur deux observations invente une
    distribution. Les deux montants sont plus honnêtes que leur milieu."""
    session = _session()
    client = _client(session)
    _trade(session, client, "2026-02-12", nominal=2_000_000.0)
    _trade(session, client, "2026-05-20", nominal=1_800_000.0)

    ticket = observed_ranges(deals_of_client(session, client.id), client)["ticket"]
    assert ticket["n"] == 2
    assert ticket["band"] is None
    assert ticket["points"] == [1_800_000.0, 2_000_000.0]


def test_sans_transaction_les_bornes_restent_vides_sans_planter():
    session = _session()
    client = _client(session)
    bornes = observed_ranges([], client)
    assert bornes["ticket"]["n"] == 0
    assert bornes["ticket"]["median"] is None
    assert bornes["ticket"]["declared_max"] == 5_000_000
    # La politique reste lisible même sans historique : c'est elle qui porte
    # toute la valeur de l'écran sur un client neuf.


# ── Les seuils : rendre l'absence actionnable ────────────────────────

def test_les_seuils_disent_ce_qui_manque_et_a_partir_de_combien():
    session = _session()
    client = _client(session)
    _trade(session, client, "2026-02-12")
    _trade(session, client, "2026-05-20")

    cycle = compute_cycle(_dates_de_trade(deals_of_client(session, client.id)),
                          asof=date(2026, 8, 31))
    seuils = next_thresholds(cycle)

    faits = next(s for s in seuils if s["what"] == "faits_observes")
    dispersion = next(s for s in seuils if s["what"] == "dispersion")
    haute = next(s for s in seuils if s["what"] == "confiance_haute")

    assert faits["reached"] is True          # ne dépend d'aucun historique
    assert dispersion["reached"] is False
    assert dispersion["at"] == 1             # une transaction de plus
    assert haute["reached"] is False
    assert haute["at"] == 5
    # L'import est toujours proposé : c'est le raccourci prévu pour ce cas.
    assert any(s["what"] == "import" for s in seuils)


def test_sur_un_client_etabli_les_seuils_sont_atteints():
    session = _session()
    client = _client(session)
    for jour in ("2025-01-15", "2025-04-15", "2025-07-15", "2025-10-14",
                 "2026-01-13", "2026-04-14", "2026-07-14"):
        _trade(session, client, jour)

    cycle = compute_cycle(_dates_de_trade(deals_of_client(session, client.id)),
                          asof=date(2026, 8, 31))
    seuils = next_thresholds(cycle)
    assert cycle.confidence == "high"
    assert all(s["reached"] for s in seuils
               if s["what"] in ("faits_observes", "dispersion",
                                "confiance_moyenne", "confiance_haute"))


# ── L'assemblage complet ─────────────────────────────────────────────

def test_la_fiche_complete_porte_tout_ce_que_l_ecran_affiche():
    session = _session()
    client = _client(session)
    personne = Person(first_name="Jean", last_name="Dupont", entity_id=1)
    session.add(personne); session.commit(); session.refresh(personne)
    affiliation = Affiliation(person_id=personne.id, client_id=client.id,
                              start_date="2022-01-01")
    session.add(affiliation); session.commit()
    for jour in ("2025-01-15", "2025-04-15", "2025-07-15", "2025-10-14"):
        _trade(session, client, jour, maturite="2028-01-15")
    session.add_all([
        Opportunity(reference="O1", entity_id=1, owner_user_id=1,
                    client_id=client.id, title="A", status="won"),
        Opportunity(reference="O2", entity_id=1, owner_user_id=1,
                    client_id=client.id, title="B", status="lost",
                    lost_reason="coupon_too_low"),
    ])
    session.commit()

    fiche = client_intelligence(session, client.id, asof=date(2026, 1, 1))
    for cle in ("cycle", "behaviour", "declared", "negative_space", "ranges",
                "thresholds", "conversion", "transactions", "contact_window",
                "lost_reasons", "per_contact"):
        assert cle in fiche, f"« {cle} » manque à la fiche"

    assert fiche["conversion"]["rate"] == pytest.approx(0.5)
    assert fiche["conversion"]["decided"] == 2
    assert len(fiche["transactions"]) == 4
    # Les transactions sortent de la plus récente à la plus ancienne — c'est
    # l'ordre dans lequel on lit une fiche.
    assert fiche["transactions"][0]["trade_date"] == "2025-10-14"


def test_sans_dossier_tranche_le_taux_reste_vide_pas_zero():
    session = _session()
    client = _client(session)
    session.add(Opportunity(reference="O1", entity_id=1, owner_user_id=1,
                            client_id=client.id, title="A",
                            status="client_interest"))
    session.commit()

    fiche = client_intelligence(session, client.id, asof=date(2026, 1, 1))
    assert fiche["conversion"]["rate"] is None
    assert fiche["conversion"]["decided"] == 0


def test_un_client_sans_transaction_rend_une_fiche_complete_et_muette():
    """L'écran doit se construire entièrement : c'est la politique déclarée qui
    porte la valeur, pas l'historique absent."""
    session = _session()
    client = _client(session)
    fiche = client_intelligence(session, client.id, asof=date(2026, 8, 31))

    assert fiche["cycle"]["confidence"] == "insufficient_history"
    assert fiche["cycle"]["expected_window_start"] is None
    assert fiche["contact_window"]["start"] is None
    assert fiche["transactions"] == []
    # Mais l'espace négatif, lui, est entier : quatre émetteurs à proposer.
    assert len(fiche["negative_space"]["issuers"]["never_used"]) == 4
    assert fiche["ranges"]["ticket"]["declared_max"] == 5_000_000
