"""Client Intelligence — l'historisation professionnelle et ses garanties.

Ces tests portent sur le seul invariant qui ne se rattrape pas après coup :
**un historique commercial ne suit pas une personne qui change d'employeur**.

Le modèle y répond par la structure plutôt que par la discipline. Les objets
commerciaux — interaction, opportunité, trade — pointent sur l'AFFILIATION,
qui lie une personne à une société sur une période et ne se réaffecte jamais.
Créer l'affiliation suivante n'écrit rien sur la précédente : il n'existe
aucun chemin de code capable de déplacer un passé.

Le scénario du §76 de la mission est ici en entier — c'est celui qui dirait,
s'il tombait, que le module est inutilisable.
"""
import json

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.client_controls import (
    ClientRuleError, change_company, close_affiliation, current_affiliation,
    affiliations_of_client, find_client_duplicates, find_person_duplicates,
    require_affiliation_of_client, require_client_deletable,
    require_person_deletable, validate_opportunity_contacts,
    validate_status_transition, client_provenance_snapshot,
    require_deal_attribution_coherent,
)
from backend.app.db.models import (
    Affiliation, Client, Deal, Interaction, Opportunity, OpportunityParticipant,
    Person,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _client(session: Session, nom: str) -> Client:
    client = Client(name=nom, entity_id=1, client_type="asset_manager",
                    status="active")
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


def _person(session: Session, prenom: str, nom: str, email: str = None) -> Person:
    personne = Person(first_name=prenom, last_name=nom, email=email, entity_id=1)
    session.add(personne)
    session.commit()
    session.refresh(personne)
    return personne


def _affilie(session: Session, personne: Person, client: Client,
             debut: str, fin: str = None, role: str = "portfolio_manager") -> Affiliation:
    affiliation = Affiliation(person_id=personne.id, client_id=client.id,
                              job_title="Gérant", commercial_role=role,
                              start_date=debut, end_date=fin)
    session.add(affiliation)
    session.commit()
    session.refresh(affiliation)
    return affiliation


# ── §76 — le scénario obligatoire, en entier ─────────────────────────

def test_un_changement_de_societe_ne_deplace_aucun_historique():
    """Jean travaille chez Bank A, y laisse des interactions, une opportunité
    et un trade, puis rejoint Bank B. Rien de ce qu'il a fait chez A ne doit
    porter le nom de B — ni le jour du changement, ni jamais."""
    session = _session()
    bank_a = _client(session, "Bank A")
    bank_b = _client(session, "Bank B")
    jean = _person(session, "Jean", "Dupont", "jean.dupont@bank-a.com")

    chez_a = _affilie(session, jean, bank_a, "2022-01-01")

    interaction = Interaction(entity_id=1, user_id=1, client_id=bank_a.id,
                              interaction_date="2024-03-15",
                              interaction_type="meeting", summary="Revue de book")
    opportunite = Opportunity(reference="OPP-20240401-001", entity_id=1,
                              owner_user_id=1, client_id=bank_a.id,
                              primary_affiliation_id=chez_a.id,
                              title="Autocall 3Y", status="won")
    trade = Deal(reference="DEAL-2024-001", user_id=1, entity_id=1,
                 client_id=bank_a.id, primary_affiliation_id=chez_a.id,
                 nominal=1_000_000.0)
    session.add_all([interaction, opportunite, trade])
    session.commit()

    # Le changement de société lui-même.
    ancienne, nouvelle = change_company(
        session, person_id=jean.id, new_client_id=bank_b.id,
        start_date="2026-09-01", job_title="CIO", commercial_role="cio")
    session.commit()

    # L'ancienne affiliation est close, pas réaffectée.
    assert ancienne.id == chez_a.id
    assert ancienne.client_id == bank_a.id
    assert ancienne.end_date == "2026-09-01"

    # La nouvelle est ouverte chez B, et c'est elle que l'écran montrera.
    assert nouvelle.client_id == bank_b.id
    assert nouvelle.end_date is None
    assert current_affiliation(session, jean.id).id == nouvelle.id

    # Et surtout : l'historique de 2024 n'a pas bougé d'un pouce.
    session.refresh(opportunite)
    session.refresh(trade)
    session.refresh(interaction)
    assert opportunite.client_id == bank_a.id
    assert opportunite.primary_affiliation_id == chez_a.id
    assert trade.client_id == bank_a.id
    assert trade.primary_affiliation_id == chez_a.id
    assert interaction.client_id == bank_a.id


def test_les_deux_periodes_restent_lisibles_separement():
    """Le comportement personnel agrège les deux sociétés ; le comportement par
    affiliation les sépare. C'est ce qui permettra plus tard de dire si une
    personne garde ses habitudes ou épouse celles de sa maison (§12)."""
    session = _session()
    bank_a, bank_b = _client(session, "Bank A"), _client(session, "Bank B")
    jean = _person(session, "Jean", "Dupont")
    chez_a = _affilie(session, jean, bank_a, "2022-01-01")
    change_company(session, person_id=jean.id, new_client_id=bank_b.id,
                   start_date="2026-09-01")
    session.commit()
    chez_b = current_affiliation(session, jean.id)

    session.add_all([
        Deal(reference="D-A-1", user_id=1, client_id=bank_a.id,
             primary_affiliation_id=chez_a.id, nominal=1.0),
        Deal(reference="D-A-2", user_id=1, client_id=bank_a.id,
             primary_affiliation_id=chez_a.id, nominal=1.0),
        Deal(reference="D-B-1", user_id=1, client_id=bank_b.id,
             primary_affiliation_id=chez_b.id, nominal=1.0),
    ])
    session.commit()

    toutes = [a.id for a in session.exec(
        select(Affiliation).where(Affiliation.person_id == jean.id)).all()]
    personnel = session.exec(
        select(Deal).where(Deal.primary_affiliation_id.in_(toutes))).all()
    par_affiliation_a = session.exec(
        select(Deal).where(Deal.primary_affiliation_id == chez_a.id)).all()
    par_affiliation_b = session.exec(
        select(Deal).where(Deal.primary_affiliation_id == chez_b.id)).all()

    assert len(personnel) == 3          # tout l'historique de la personne
    assert len(par_affiliation_a) == 2  # ce qu'elle faisait chez A
    assert len(par_affiliation_b) == 1  # ce qu'elle fait chez B


# ── L'affiliation courante se déduit, elle ne se stocke pas ──────────

def test_l_affiliation_courante_se_deduit_de_la_date_de_fin():
    session = _session()
    client = _client(session, "ABC AM")
    personne = _person(session, "Sophie", "Martin")
    assert current_affiliation(session, personne.id) is None

    ouverte = _affilie(session, personne, client, "2024-01-01")
    assert current_affiliation(session, personne.id).id == ouverte.id

    close_affiliation(session, ouverte.id, "2026-06-30")
    session.commit()
    assert current_affiliation(session, personne.id) is None


def test_une_affiliation_close_ne_se_propose_plus_a_la_creation():
    """Les anciens contacts restent dans l'historique mais sortent des
    sélecteurs : on n'ouvre pas une opportunité avec quelqu'un qui est parti."""
    session = _session()
    client = _client(session, "ABC AM")
    partie = _person(session, "Ancien", "Contact")
    presente = _person(session, "Actuel", "Contact")
    _affilie(session, partie, client, "2020-01-01", fin="2025-12-31")
    encore = _affilie(session, presente, client, "2026-01-01")

    courants = affiliations_of_client(session, client.id)
    assert [a.id for a in courants] == [encore.id]
    assert len(affiliations_of_client(session, client.id, only_current=False)) == 2


def test_rejoindre_deux_fois_la_meme_societe_est_refuse():
    session = _session()
    client = _client(session, "ABC AM")
    personne = _person(session, "Jean", "Dupont")
    _affilie(session, personne, client, "2024-01-01")

    with pytest.raises(ClientRuleError) as capture:
        change_company(session, person_id=personne.id, new_client_id=client.id,
                       start_date="2026-01-01")
    assert capture.value.code == "AFFILIATION_SAME_CLIENT"


def test_une_fin_anterieure_au_debut_est_refusee():
    session = _session()
    client = _client(session, "ABC AM")
    personne = _person(session, "Jean", "Dupont")
    affiliation = _affilie(session, personne, client, "2024-01-01")
    with pytest.raises(ClientRuleError) as capture:
        close_affiliation(session, affiliation.id, "2023-06-01")
    assert capture.value.code == "AFFILIATION_END_BEFORE_START"


def test_le_changement_de_societe_ne_laisse_pas_d_etat_intermediaire():
    """§65 — si la seconde écriture échoue, la première ne doit pas subsister.
    Les deux partagent la session, donc un rollback les emporte ensemble : la
    personne ne se retrouve jamais sans employeur."""
    session = _session()
    bank_a = _client(session, "Bank A")
    jean = _person(session, "Jean", "Dupont")
    chez_a = _affilie(session, jean, bank_a, "2022-01-01")

    with pytest.raises(ClientRuleError):
        change_company(session, person_id=jean.id, new_client_id=999_999,
                       start_date="2026-09-01")
    session.rollback()

    session.refresh(chez_a)
    assert chez_a.end_date is None
    assert current_affiliation(session, jean.id).id == chez_a.id


# ── §29 — un contact appartient au client de son opportunité ─────────

def test_un_contact_d_un_autre_client_est_refuse():
    session = _session()
    bank_a, bank_b = _client(session, "Bank A"), _client(session, "Bank B")
    jean = _person(session, "Jean", "Dupont")
    chez_a = _affilie(session, jean, bank_a, "2022-01-01")

    with pytest.raises(ClientRuleError) as capture:
        require_affiliation_of_client(session, chez_a.id, bank_b.id)
    assert capture.value.code == "AFFILIATION_CLIENT_MISMATCH"
    assert "Bank B" in capture.value.message


def test_le_contact_principal_ne_se_repete_pas_dans_les_participants():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    chez = _affilie(session, jean, client, "2022-01-01")

    with pytest.raises(ClientRuleError) as capture:
        validate_opportunity_contacts(session, client.id, chez.id, [chez.id])
    assert capture.value.code == "PARTICIPANT_IS_PRIMARY"


def test_un_participant_ne_figure_pas_deux_fois():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    sophie = _person(session, "Sophie", "Martin")
    principal = _affilie(session, jean, client, "2022-01-01")
    autre = _affilie(session, sophie, client, "2022-01-01")

    with pytest.raises(ClientRuleError) as capture:
        validate_opportunity_contacts(session, client.id, principal.id,
                                      [autre.id, autre.id])
    assert capture.value.code == "PARTICIPANT_DUPLICATE"


def test_une_selection_coherente_passe():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    sophie = _person(session, "Sophie", "Martin")
    principal = _affilie(session, jean, client, "2022-01-01")
    autre = _affilie(session, sophie, client, "2022-01-01")
    validate_opportunity_contacts(session, client.id, principal.id, [autre.id])


# ── Rattachement d'un trade ──────────────────────────────────────────

def test_un_trade_ne_peut_pas_melanger_deux_clients():
    session = _session()
    bank_a, bank_b = _client(session, "Bank A"), _client(session, "Bank B")
    jean = _person(session, "Jean", "Dupont")
    chez_a = _affilie(session, jean, bank_a, "2022-01-01")

    with pytest.raises(ClientRuleError) as capture:
        require_deal_attribution_coherent(
            session, client_id=bank_b.id, affiliation_id=chez_a.id,
            opportunity_id=None)
    assert capture.value.code == "AFFILIATION_CLIENT_MISMATCH"


def test_un_contact_sans_client_est_refuse_sur_un_trade():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    chez = _affilie(session, jean, client, "2022-01-01")
    with pytest.raises(ClientRuleError) as capture:
        require_deal_attribution_coherent(session, client_id=None,
                                          affiliation_id=chez.id,
                                          opportunity_id=None)
    assert capture.value.code == "DEAL_CONTACT_WITHOUT_CLIENT"


def test_un_trade_non_rattache_reste_valide():
    """Un deal booké hors parcours client — le cas de tout l'historique
    existant — ne doit déclencher aucun refus."""
    session = _session()
    require_deal_attribution_coherent(session, client_id=None,
                                      affiliation_id=None, opportunity_id=None)
    assert client_provenance_snapshot(session, client_id=None,
                                      affiliation_id=None,
                                      opportunity_id=None) is None


def test_le_cliche_commercial_fige_ce_qui_etait_vrai_au_booking():
    """Le pointeur garantit la justesse, le cliché garantit la preuve : renommer
    la personne ensuite ne change pas ce que le trade raconte."""
    session = _session()
    client = _client(session, "Bank A")
    jean = _person(session, "Jean", "Dupont")
    chez = _affilie(session, jean, client, "2022-01-01", role="cio")

    brut = client_provenance_snapshot(session, client_id=client.id,
                                      affiliation_id=chez.id, opportunity_id=None)
    cliche = json.loads(brut)
    assert cliche["client"]["name"] == "Bank A"
    assert cliche["contact"]["name"] == "Jean Dupont"
    assert cliche["contact"]["commercial_role"] == "cio"

    jean.last_name = "Durand"
    client.name = "Bank A (ex)"
    session.add_all([jean, client])
    session.commit()

    assert json.loads(brut)["contact"]["name"] == "Jean Dupont"
    assert json.loads(brut)["client"]["name"] == "Bank A"


# ── §21 — les doublons avertissent, ils ne bloquent pas ──────────────

def test_un_email_identique_est_un_signal_fort():
    session = _session()
    _person(session, "Jean", "Dupont", "jean.dupont@bank.com")
    trouves = find_person_duplicates(session, first_name="Jean",
                                     last_name="Dupond",
                                     email="Jean.Dupont@Bank.com", entity_id=1)
    assert len(trouves) == 1
    assert trouves[0]["signal"] == "email"
    assert trouves[0]["confidence"] == "high"


def test_un_homonyme_est_un_signal_faible_mais_signale():
    """C'est le cas §20 : Jean Dupont qui rejoint Bank B après Bank A ne doit
    pas devenir un second Jean Dupont sans que personne ne pose la question."""
    session = _session()
    _person(session, "Jean", "Dupont", "j.dupont@bank-a.com")
    trouves = find_person_duplicates(session, first_name="Jean",
                                     last_name="Dupont",
                                     email="j.dupont@bank-b.com", entity_id=1)
    assert trouves and trouves[0]["signal"] == "name"
    assert trouves[0]["confidence"] == "medium"


def test_la_detection_de_doublon_n_empeche_pas_l_ecriture():
    """Aucune contrainte d'unicité sur l'email : deux homonymes réels doivent
    pouvoir coexister une fois l'utilisateur averti."""
    session = _session()
    _person(session, "Jean", "Dupont", "contact@desk.com")
    second = _person(session, "Jean", "Dupont", "contact@desk.com")
    assert second.id is not None


def test_un_identifiant_externe_identique_signale_un_client_en_double():
    session = _session()
    client = Client(name="ABC Asset Management", external_ref="LEI-123",
                    entity_id=1)
    session.add(client)
    session.commit()
    trouves = find_client_duplicates(session, name="ABC AM",
                                     external_ref="lei-123", entity_id=1)
    assert trouves and trouves[0]["signal"] == "external_ref"


# ── §17 / §63 — ce qui porte un historique s'archive ─────────────────

def test_un_client_vierge_se_supprime():
    session = _session()
    client = _client(session, "Prospect sans suite")
    require_client_deletable(session, client.id)


def test_un_client_avec_historique_refuse_la_suppression():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    _affilie(session, jean, client, "2022-01-01")
    session.add(Deal(reference="D-1", user_id=1, client_id=client.id, nominal=1.0))
    session.commit()

    with pytest.raises(ClientRuleError) as capture:
        require_client_deletable(session, client.id)
    assert capture.value.code == "CLIENT_HAS_HISTORY"
    # Le message doit être actionnable, pas une erreur de contrainte SQL.
    assert "contact(s)" in capture.value.message
    assert "trade(s)" in capture.value.message
    assert "Archivez-le" in capture.value.message


def test_une_personne_avec_historique_refuse_la_suppression():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    _affilie(session, jean, client, "2022-01-01")
    with pytest.raises(ClientRuleError) as capture:
        require_person_deletable(session, jean.id)
    assert capture.value.code == "PERSON_HAS_HISTORY"
    assert "Désactivez-la" in capture.value.message


# ── §33 — perdre une opportunité exige de dire pourquoi ──────────────

def test_perdre_une_opportunite_sans_motif_est_refuse():
    with pytest.raises(ClientRuleError) as capture:
        validate_status_transition("negotiation", "lost", None)
    assert capture.value.code == "LOST_REASON_REQUIRED"


def test_un_motif_de_perte_hors_vocabulaire_est_refuse():
    with pytest.raises(ClientRuleError) as capture:
        validate_status_transition("negotiation", "lost", "pas_envie")
    assert capture.value.code == "LOST_REASON_INVALID"


def test_un_motif_connu_passe():
    validate_status_transition("negotiation", "lost", "coupon_too_low")


def test_aucun_ordre_n_est_impose_entre_les_etapes():
    """Un client peut arriver avec son idée toute faite : forcer une
    progression linéaire ferait mentir la saisie."""
    validate_status_transition("lead", "rfq", None)
    validate_status_transition("won", "archived", None)


# ── §64 — unicité en base, pas seulement en applicatif ───────────────

def test_un_participant_en_double_est_refuse_par_la_base():
    from sqlalchemy.exc import IntegrityError
    session = _session()
    client = _client(session, "ABC AM")
    jean = _person(session, "Jean", "Dupont")
    chez = _affilie(session, jean, client, "2022-01-01")
    opportunite = Opportunity(reference="OPP-1", owner_user_id=1,
                              client_id=client.id, title="Test")
    session.add(opportunite)
    session.commit()

    session.add(OpportunityParticipant(opportunity_id=opportunite.id,
                                       affiliation_id=chez.id))
    session.commit()
    session.add(OpportunityParticipant(opportunity_id=opportunite.id,
                                       affiliation_id=chez.id))
    with pytest.raises(IntegrityError):
        session.commit()
