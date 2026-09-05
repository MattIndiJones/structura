"""Client Intelligence — l'API, ses refus et son cloisonnement.

Ces tests passent par HTTP, pas par les fonctions de contrôle : c'est la seule
façon de vérifier ce que §61 demande vraiment — qu'un appel direct se heurte au
même refus que l'écran. Un contrôle qui n'existe que dans le frontend se
contourne avec curl.

Trois familles :
  • le cloisonnement — une autre entité ne voit rien, et l'apprend par un 404 ;
  • les refus métier — suppression avec historique, contact d'un autre client,
    perte sans motif, écriture concurrente sur les contraintes ;
  • la piste d'audit — un refus laisse une trace, pas seulement un succès.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import AuditEvent, Client, Deal, User


@pytest.fixture
def app_client(monkeypatch):
    """Une application sur base mémoire, avec trois utilisateurs — deux de la
    même entité, un d'une autre — pour pouvoir éprouver le cloisonnement.

    `StaticPool` est indispensable : sans lui, chaque connexion à `sqlite://`
    ouvre sa PROPRE base mémoire, et TestClient servant les requêtes depuis un
    autre thread, l'application repartirait sur une base vide. Même montage que
    test_variantes_filiation.
    """
    import backend.app.db.database as db
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)

    from backend.app.main import app

    session = Session(engine)

    alice = User(id=1, username="alice", email="alice@desk.com",
                 password_hash="x", role="user", entity_id=1)
    bob = User(id=2, username="bob", email="bob@desk.com",
               password_hash="x", role="user", entity_id=1)
    etranger = User(id=3, username="carol", email="carol@autre.com",
                    password_hash="x", role="user", entity_id=99)
    session.add_all([alice, bob, etranger])
    session.commit()

    courant = {"user": alice}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: courant["user"]
    client = TestClient(app)
    client.session = session
    client.courant = courant
    client.utilisateurs = {"alice": alice, "bob": bob, "carol": etranger}
    yield client
    app.dependency_overrides.clear()
    session.close()


def _creer_client(app_client, nom="ABC Asset Management", **kwargs):
    corps = {"name": nom, "client_type": "asset_manager", **kwargs}
    reponse = app_client.post("/api/clients", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def _creer_personne(app_client, prenom="Jean", nom="Dupont", **kwargs):
    corps = {"first_name": prenom, "last_name": nom, **kwargs}
    reponse = app_client.post("/api/persons", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


# ── Cloisonnement ─────────────────────────────────────────────────────

def test_une_autre_entite_ne_voit_pas_le_client(app_client):
    """§61 — un GET direct sur un id connu ne doit rien rendre. Et 404 plutôt
    que 403 : « interdit » confirmerait que la fiche existe."""
    fiche = _creer_client(app_client)
    app_client.courant["user"] = app_client.utilisateurs["carol"]

    assert app_client.get(f"/api/clients/{fiche['id']}").status_code == 404
    assert app_client.get("/api/clients").json() == []


def test_une_autre_entite_ne_peut_pas_modifier_ni_supprimer(app_client):
    fiche = _creer_client(app_client)
    app_client.courant["user"] = app_client.utilisateurs["carol"]

    assert app_client.patch(f"/api/clients/{fiche['id']}",
                            json={"name": "Détourné"}).status_code == 404
    assert app_client.delete(f"/api/clients/{fiche['id']}").status_code == 404
    assert app_client.post(f"/api/clients/{fiche['id']}/archive").status_code == 404


def test_un_collegue_de_la_meme_entite_voit_la_fiche(app_client):
    """Le client est une identité partagée : Bob doit voir ce qu'Alice a créé,
    sinon on aurait deux sociétés là où il n'y en a qu'une."""
    fiche = _creer_client(app_client)
    app_client.courant["user"] = app_client.utilisateurs["bob"]
    assert app_client.get(f"/api/clients/{fiche['id']}").status_code == 200


def test_le_createur_couvre_ce_qu_il_cree(app_client):
    fiche = _creer_client(app_client)
    couverture = fiche["coverage"]
    assert [c["username"] for c in couverture] == ["alice"]
    assert couverture[0]["coverage_role"] == "primary"

    app_client.courant["user"] = app_client.utilisateurs["bob"]
    assert app_client.get("/api/clients", params={"mine": True}).json() == []


def test_la_provenance_fictive_est_le_defaut_et_reste_explicitement_modifiable(app_client):
    fiche = _creer_client(app_client)
    assert fiche["data_origin"] == "demo"

    modifiee = app_client.patch(
        f"/api/clients/{fiche['id']}", json={"data_origin": "imported"})
    assert modifiee.status_code == 200
    assert modifiee.json()["data_origin"] == "imported"

    refusee = app_client.patch(
        f"/api/clients/{fiche['id']}", json={"data_origin": "supposee_reelle"})
    assert refusee.status_code == 422


# ── Doublons : on avertit, on ne bloque pas ──────────────────────────

def test_un_doublon_probable_suspend_la_creation_avec_de_quoi_decider(app_client):
    _creer_client(app_client, "ABC Asset Management")
    reponse = app_client.post("/api/clients",
                              json={"name": "ABC Asset Management"})
    assert reponse.status_code == 409
    detail = reponse.json()["detail"]
    assert detail["code"] == "CLIENT_DUPLICATE_SUSPECTED"
    assert detail["duplicates"][0]["signal"] == "name"


def test_la_confirmation_debloque_la_creation(app_client):
    _creer_client(app_client, "ABC Asset Management")
    reponse = app_client.post(
        "/api/clients",
        json={"name": "ABC Asset Management", "confirm_duplicate": True})
    assert reponse.status_code == 201


def test_une_personne_deja_connue_est_signalee_avant_creation(app_client):
    """Le cas §20 : Jean Dupont qui rejoint une nouvelle société doit se voir
    proposer son propre dossier, pas un second."""
    _creer_personne(app_client, email="jean.dupont@bank-a.com")
    reponse = app_client.get("/api/persons/duplicates",
                             params={"first_name": "Jean", "last_name": "Dupont"})
    assert reponse.status_code == 200
    assert reponse.json()[0]["signal"] == "name"

    creation = app_client.post("/api/persons",
                               json={"first_name": "Jean", "last_name": "Dupont"})
    assert creation.status_code == 409
    assert creation.json()["detail"]["code"] == "PERSON_DUPLICATE_SUSPECTED"


# ── Suppression : ce qui porte un historique s'archive ───────────────

def test_un_client_avec_historique_refuse_la_suppression_et_dit_pourquoi(app_client):
    fiche = _creer_client(app_client)
    _creer_personne(app_client, client_id=fiche["id"], start_date="2024-01-01")

    reponse = app_client.delete(f"/api/clients/{fiche['id']}")
    assert reponse.status_code == 409
    detail = reponse.json()["detail"]
    assert detail["code"] == "CLIENT_HAS_HISTORY"
    # §82 — le message doit être actionnable, pas une erreur de contrainte.
    assert "Archivez-le" in detail["message"]
    assert "contact(s)" in detail["message"]


def test_un_client_vierge_se_supprime(app_client):
    fiche = _creer_client(app_client, "Prospect sans suite")
    assert app_client.delete(f"/api/clients/{fiche['id']}").status_code == 204


def test_le_refus_de_suppression_laisse_une_trace(app_client):
    """Un refus est un fait à conserver : c'est ce qui permet de comprendre
    plus tard pourquoi une fiche est restée en base."""
    fiche = _creer_client(app_client)
    _creer_personne(app_client, client_id=fiche["id"], start_date="2024-01-01")
    app_client.delete(f"/api/clients/{fiche['id']}")

    evenements = app_client.session.exec(
        select(AuditEvent).where(AuditEvent.action == "CLIENT_DELETE_REJECTED")
    ).all()
    assert len(evenements) == 1
    assert evenements[0].result == "REJECTED"
    assert evenements[0].actor_user_id == 1


def test_archiver_puis_reactiver(app_client):
    fiche = _creer_client(app_client)
    archive = app_client.post(f"/api/clients/{fiche['id']}/archive").json()
    assert archive["status"] == "archived"
    assert app_client.get("/api/clients").json() == []      # sorti des listes
    assert len(app_client.get("/api/clients",
                              params={"include_archived": True}).json()) == 1

    reactive = app_client.post(f"/api/clients/{fiche['id']}/reactivate").json()
    assert reactive["status"] == "active"


# ── Contraintes et verrou optimiste, de bout en bout ─────────────────

def test_deux_ecritures_concurrentes_la_seconde_recoit_un_409(app_client):
    """Le scénario qui a décidé la forme du modèle, vu depuis l'API."""
    fiche = _creer_client(app_client)
    version = fiche["constraints_version"]

    premiere = app_client.put(
        f"/api/clients/{fiche['id']}/constraints",
        json={"constraints": {"currencies": ["EUR"]},
              "constraints_version": version})
    assert premiere.status_code == 200

    seconde = app_client.put(
        f"/api/clients/{fiche['id']}/constraints",
        json={"constraints": {"asset_classes": ["equity"]},
              "constraints_version": version})       # version périmée
    assert seconde.status_code == 409
    assert seconde.json()["detail"]["code"] == "CONSTRAINTS_VERSION_STALE"

    # Le travail du premier est intact.
    apres = app_client.get(f"/api/clients/{fiche['id']}").json()
    assert apres["constraints"]["currencies"] == ["EUR"]


def test_le_conflit_d_ecriture_est_audite(app_client):
    fiche = _creer_client(app_client)
    version = fiche["constraints_version"]
    app_client.put(f"/api/clients/{fiche['id']}/constraints",
                   json={"constraints": {"currencies": ["EUR"]},
                         "constraints_version": version})
    app_client.put(f"/api/clients/{fiche['id']}/constraints",
                   json={"constraints": {"currencies": ["USD"]},
                         "constraints_version": version})
    evenements = app_client.session.exec(
        select(AuditEvent).where(
            AuditEvent.action == "CLIENT_CONSTRAINTS_CONFLICT")).all()
    assert len(evenements) == 1


def test_une_cle_de_contrainte_inconnue_est_refusee(app_client):
    fiche = _creer_client(app_client)
    reponse = app_client.put(
        f"/api/clients/{fiche['id']}/constraints",
        json={"constraints": {"minRating": "A-"},
              "constraints_version": fiche["constraints_version"]})
    assert reponse.status_code == 422


def test_les_scalaires_se_modifient_hors_verrou(app_client):
    fiche = _creer_client(app_client)
    reponse = app_client.patch(
        f"/api/clients/{fiche['id']}/scalar-constraints",
        json={"ticket_min": 500000, "ticket_max": 5000000, "min_rating": "A-",
              "maturity_min_months": 18, "maturity_max_months": 60})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["ticket_min"] == 500000
    assert corps["min_rating"] == "A-"
    # Le verrou du blob n'a pas bougé : les deux écritures sont indépendantes.
    assert corps["constraints_version"] == fiche["constraints_version"]


def test_un_ticket_minimum_au_dessus_du_maximum_est_refuse(app_client):
    fiche = _creer_client(app_client)
    reponse = app_client.patch(
        f"/api/clients/{fiche['id']}/scalar-constraints",
        json={"ticket_min": 5000000, "ticket_max": 1000000})
    assert reponse.status_code == 422


def test_une_preference_datee_reste_rejouable_et_garde_sa_source(app_client):
    fiche = _creer_client(app_client, data_origin="native")
    jean = _creer_personne(
        app_client, client_id=fiche["id"], start_date="2025-01-01")
    affiliation_id = jean["affiliations"][0]["id"]

    premiere = app_client.put(
        f"/api/clients/{fiche['id']}/constraints", json={
            "constraints": {"currencies": ["EUR"]},
            "constraints_version": fiche["constraints_version"],
            "evidence": {
                "statement_kind": "client_declared",
                "statement_date": "2026-01-15",
                "source_affiliation_id": affiliation_id,
                "channel": "meeting",
                "note": "Préférence exprimée en comité d'investissement.",
            },
        })
    assert premiere.status_code == 200, premiere.text

    seconde = app_client.put(
        f"/api/clients/{fiche['id']}/constraints", json={
            "constraints": {"currencies": ["USD"]},
            "constraints_version": premiere.json()["constraints_version"],
            "evidence": {
                "statement_kind": "client_contradicted",
                "statement_date": "2026-03-10",
                "source_affiliation_id": affiliation_id,
                "channel": "phone",
                "note": "Le client souhaite désormais travailler en USD.",
            },
        })
    assert seconde.status_code == 200, seconde.text

    history = app_client.get(
        f"/api/clients/{fiche['id']}/preference-history").json()
    currency_rows = [row for row in history
                     if row["preference_key"] == "currencies"]
    assert [row["statement_kind"] for row in currency_rows] == [
        "client_contradicted", "client_declared"]
    assert currency_rows[0]["is_current"] is True
    assert currency_rows[1]["is_current"] is False
    assert currency_rows[0]["source_name"] == "Jean Dupont"

    january = app_client.get(
        f"/api/client-intelligence/clients/{fiche['id']}",
        params={"asof": "2026-01-31"})
    assert january.status_code == 200, january.text
    assert january.json()["declared"]["client"]["currencies"] == ["EUR"]


def test_un_mandat_porte_son_propre_profil_sans_modifier_le_client(app_client):
    fiche = _creer_client(app_client, data_origin="native")
    mandat = app_client.post(
        f"/api/clients/{fiche['id']}/mandates", json={
            "name": "Fonds Absolute Return", "mandate_type": "fund",
            "data_origin": "native",
        }).json()

    reponse = app_client.put(
        f"/api/clients/{fiche['id']}/scoped-preferences", json={
            "mandate_id": mandat["id"],
            "preferences_version": 0,
            "preferences": {"transaction_formats": ["OTC"],
                            "instrument_families": ["Swap"]},
            "evidence": {"statement_kind": "client_confirmed",
                         "statement_date": "2026-06-01"},
        })
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["values"]["transaction_formats"] == ["OTC"]

    client_schema = app_client.get(
        f"/api/clients/{fiche['id']}/constraints/schema").json()
    assert "transaction_formats" not in client_schema["values"]

    mandate_schema = app_client.get(
        f"/api/clients/{fiche['id']}/scoped-preferences/schema",
        params={"mandate_id": mandat["id"]})
    assert mandate_schema.status_code == 200
    assert mandate_schema.json()["values"]["instrument_families"] == ["Swap"]

    profile = app_client.get(
        f"/api/client-intelligence/clients/{fiche['id']}",
        params={"mandate_id": mandat["id"]}).json()
    assert profile["scope"]["name"] == "Fonds Absolute Return"
    assert profile["declared"]["mandate"]["transaction_formats"] == ["OTC"]

    autre = _creer_client(app_client, "Autre société", data_origin="native")
    refuse = app_client.get(
        f"/api/clients/{autre['id']}/scoped-preferences/schema",
        params={"mandate_id": mandat["id"]})
    assert refuse.status_code == 404

    stale = app_client.put(
        f"/api/clients/{fiche['id']}/scoped-preferences", json={
            "mandate_id": mandat["id"], "preferences_version": 0,
            "preferences": {"transaction_formats": ["BMTN"]},
        })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PREFERENCES_VERSION_STALE"


# ── Changement de société, par l'API ─────────────────────────────────

def test_le_changement_de_societe_conserve_l_historique(app_client):
    """§76 vu depuis l'API : l'opportunité de 2024 reste chez Bank A."""
    bank_a = _creer_client(app_client, "Bank A")
    bank_b = _creer_client(app_client, "Bank B")
    jean = _creer_personne(app_client, client_id=bank_a["id"],
                           start_date="2022-01-01", commercial_role="portfolio_manager")
    chez_a = jean["current_affiliation"]["id"]

    opportunite = app_client.post("/api/opportunities", json={
        "client_id": bank_a["id"], "primary_affiliation_id": chez_a,
        "title": "Autocall 3Y"}).json()

    reponse = app_client.post(f"/api/persons/{jean['id']}/change-company", json={
        "new_client_id": bank_b["id"], "start_date": "2026-09-01",
        "job_title": "CIO", "commercial_role": "cio"})
    assert reponse.status_code == 200
    apres = reponse.json()
    assert apres["current_affiliation"]["client_name"] == "Bank B"
    assert len(apres["affiliations"]) == 2

    relu = app_client.get(f"/api/opportunities/{opportunite['id']}").json()
    assert relu["client_name"] == "Bank A"
    assert relu["primary_contact"]["affiliation_id"] == chez_a
    # L'écran doit pouvoir signaler que ce contact a quitté la maison.
    assert relu["primary_contact"]["still_current"] is False


def test_les_contacts_actifs_seuls_sont_proposes(app_client):
    fiche = _creer_client(app_client)
    autre = _creer_client(app_client, "Autre maison")
    jean = _creer_personne(app_client, "Jean", "Dupont",
                           client_id=fiche["id"], start_date="2022-01-01")
    app_client.post(f"/api/persons/{jean['id']}/change-company",
                    json={"new_client_id": autre["id"], "start_date": "2026-01-01"})

    actifs = app_client.get(f"/api/clients/{fiche['id']}/contacts").json()
    assert actifs == []
    anciens = app_client.get(f"/api/clients/{fiche['id']}/contacts",
                             params={"include_former": True}).json()
    assert len(anciens) == 1 and anciens[0]["is_current"] is False


def test_une_affiliation_ne_se_deplace_pas_par_patch(app_client):
    """Le champ client_id n'est pas exposé sur la modification d'affiliation —
    et ce n'est pas un oubli. Un PATCH qui le contiendrait est ignoré."""
    bank_a = _creer_client(app_client, "Bank A")
    bank_b = _creer_client(app_client, "Bank B")
    jean = _creer_personne(app_client, client_id=bank_a["id"],
                           start_date="2022-01-01")
    affiliation = jean["current_affiliation"]["id"]

    app_client.patch(f"/api/persons/{jean['id']}/affiliations/{affiliation}",
                     json={"client_id": bank_b["id"], "job_title": "Gérant senior"})
    relu = app_client.get(f"/api/persons/{jean['id']}").json()
    assert relu["current_affiliation"]["client_name"] == "Bank A"
    assert relu["current_affiliation"]["job_title"] == "Gérant senior"


# ── Opportunités : le contrôle §29 côté serveur ──────────────────────

def test_un_contact_d_un_autre_client_est_refuse_par_le_serveur(app_client):
    bank_a = _creer_client(app_client, "Bank A")
    bank_b = _creer_client(app_client, "Bank B")
    jean = _creer_personne(app_client, client_id=bank_a["id"],
                           start_date="2022-01-01")

    reponse = app_client.post("/api/opportunities", json={
        "client_id": bank_b["id"],
        "primary_affiliation_id": jean["current_affiliation"]["id"],
        "title": "Tentative"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "AFFILIATION_CLIENT_MISMATCH"


def test_changer_le_client_d_une_opportunite_invalide_les_contacts(app_client):
    """§29 — on ne migre pas les contacts en silence, on refuse et on le dit."""
    bank_a = _creer_client(app_client, "Bank A")
    bank_b = _creer_client(app_client, "Bank B")
    jean = _creer_personne(app_client, client_id=bank_a["id"],
                           start_date="2022-01-01")
    opportunite = app_client.post("/api/opportunities", json={
        "client_id": bank_a["id"],
        "primary_affiliation_id": jean["current_affiliation"]["id"],
        "title": "Autocall"}).json()

    reponse = app_client.patch(f"/api/opportunities/{opportunite['id']}",
                               json={"client_id": bank_b["id"]})
    assert reponse.status_code == 409
    assert "resélectionnez les contacts" in reponse.json()["detail"]["message"]

    evenements = app_client.session.exec(
        select(AuditEvent).where(
            AuditEvent.action == "OPPORTUNITY_CLIENT_CHANGE_REJECTED")).all()
    assert len(evenements) == 1


def test_le_contact_principal_ne_se_repete_pas_dans_les_participants(app_client):
    fiche = _creer_client(app_client)
    jean = _creer_personne(app_client, client_id=fiche["id"],
                           start_date="2022-01-01")
    affiliation = jean["current_affiliation"]["id"]
    reponse = app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "primary_affiliation_id": affiliation,
        "participants": [{"affiliation_id": affiliation}], "title": "X"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "PARTICIPANT_IS_PRIMARY"


def test_perdre_une_opportunite_sans_motif_est_refuse(app_client):
    fiche = _creer_client(app_client)
    opportunite = app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "title": "Autocall"}).json()

    reponse = app_client.post(f"/api/opportunities/{opportunite['id']}/status",
                              json={"status": "lost"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "LOST_REASON_REQUIRED"

    avec_motif = app_client.post(
        f"/api/opportunities/{opportunite['id']}/status",
        json={"status": "lost", "lost_reason": "coupon_too_low",
              "lost_comment": "5 % attendu, 3,2 % proposé"})
    assert avec_motif.status_code == 200
    assert avec_motif.json()["lost_reason"] == "coupon_too_low"


def test_l_opportunite_recoit_une_reference_serie(app_client):
    fiche = _creer_client(app_client)
    premiere = app_client.post("/api/opportunities",
                               json={"client_id": fiche["id"], "title": "A"}).json()
    seconde = app_client.post("/api/opportunities",
                              json={"client_id": fiche["id"], "title": "B"}).json()
    jour = date.today().strftime("%Y%m%d")
    assert premiere["reference"] == f"OPP-{jour}-001"
    assert seconde["reference"] == f"OPP-{jour}-002"


def test_une_opportunite_reliee_refuse_la_suppression(app_client):
    fiche = _creer_client(app_client)
    opportunite = app_client.post("/api/opportunities",
                                  json={"client_id": fiche["id"], "title": "A"}).json()
    app_client.post("/api/interactions", json={
        "client_id": fiche["id"], "opportunity_id": opportunite["id"],
        "interaction_date": "2026-08-31", "interaction_type": "call",
        "summary": "Premier contact"})

    reponse = app_client.delete(f"/api/opportunities/{opportunite['id']}")
    assert reponse.status_code == 409
    assert reponse.json()["detail"]["code"] == "OPPORTUNITY_HAS_HISTORY"


# ── Interactions ─────────────────────────────────────────────────────

def test_une_interaction_existe_sans_opportunite(app_client):
    """Une prospection initiale n'a pas de dossier derrière elle."""
    fiche = _creer_client(app_client)
    reponse = app_client.post("/api/interactions", json={
        "client_id": fiche["id"], "interaction_date": "2026-08-31",
        "interaction_type": "call", "summary": "Prise de contact"})
    assert reponse.status_code == 201
    assert reponse.json()["opportunity_id"] is None


def test_un_participant_d_un_autre_client_est_refuse(app_client):
    bank_a = _creer_client(app_client, "Bank A")
    bank_b = _creer_client(app_client, "Bank B")
    jean = _creer_personne(app_client, client_id=bank_a["id"],
                           start_date="2022-01-01")
    reponse = app_client.post("/api/interactions", json={
        "client_id": bank_b["id"], "interaction_date": "2026-08-31",
        "interaction_type": "meeting", "summary": "Réunion",
        "participants": [
            {"affiliation_id": jean["current_affiliation"]["id"]}]})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "AFFILIATION_CLIENT_MISMATCH"


def test_une_interaction_rafraichit_l_activite_de_l_opportunite(app_client):
    """Alimente le futur signal « opportunité en sommeil »."""
    fiche = _creer_client(app_client)
    opportunite = app_client.post("/api/opportunities",
                                  json={"client_id": fiche["id"], "title": "A"}).json()
    app_client.post("/api/interactions", json={
        "client_id": fiche["id"], "opportunity_id": opportunite["id"],
        "interaction_date": "2026-08-31", "interaction_type": "call",
        "summary": "Retour client"})
    relu = app_client.get(f"/api/opportunities/{opportunite['id']}").json()
    assert relu["last_activity_at"] >= opportunite["last_activity_at"]
    assert len(relu["interactions"]) == 1


def test_une_interaction_se_supprime_et_laisse_une_trace(app_client):
    fiche = _creer_client(app_client)
    interaction = app_client.post("/api/interactions", json={
        "client_id": fiche["id"], "interaction_date": "2026-08-31",
        "interaction_type": "call", "summary": "À effacer"}).json()
    assert app_client.delete(
        f"/api/interactions/{interaction['id']}").status_code == 204
    evenements = app_client.session.exec(
        select(AuditEvent).where(
            AuditEvent.action == "INTERACTION_DELETED")).all()
    assert evenements and evenements[0].result == "SUCCESS"


# ── Réattribution ────────────────────────────────────────────────────

def test_une_opportunite_se_reattribue_a_un_collegue(app_client):
    """§62 — un utilisateur qui change de rôle laisse ses dossiers derrière lui."""
    fiche = _creer_client(app_client)
    opportunite = app_client.post("/api/opportunities",
                                  json={"client_id": fiche["id"], "title": "A"}).json()
    assert opportunite["owner_user_id"] == 1

    reponse = app_client.patch(f"/api/opportunities/{opportunite['id']}",
                               json={"owner_user_id": 2})
    assert reponse.status_code == 200
    assert reponse.json()["owner_user_id"] == 2
    evenements = app_client.session.exec(
        select(AuditEvent).where(
            AuditEvent.action == "OPPORTUNITY_REASSIGNED")).all()
    assert len(evenements) == 1


def test_on_ne_reattribue_pas_a_une_autre_entite(app_client):
    fiche = _creer_client(app_client)
    opportunite = app_client.post("/api/opportunities",
                                  json={"client_id": fiche["id"], "title": "A"}).json()
    reponse = app_client.patch(f"/api/opportunities/{opportunite['id']}",
                               json={"owner_user_id": 3})
    assert reponse.status_code == 404
