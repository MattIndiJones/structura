"""Analytics et signaux vus depuis l'API.

Un seul principe traverse ces tests : **une métrique sans matière rend `null`,
jamais zéro**. Un taux de conversion à 0 % sur un portefeuille où aucun dossier
n'a encore été tranché est un mensonge — il se lit « on perd tout » alors qu'il
faudrait lire « on ne sait pas encore ».

Le second point vérifié est le dénominateur de ce taux : les dossiers ouverts en
sont exclus. Les inclure ferait baisser le chiffre à mesure qu'on prospecte,
c'est-à-dire punirait exactement le bon comportement.
"""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import (
    Affiliation, Client, Deal, Interaction, Opportunity, Person, User,
)


@pytest.fixture
def app_client(monkeypatch):
    import backend.app.db.database as db
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)

    from backend.app.main import app

    session = Session(engine)
    alice = User(id=1, username="alice", email="a@d.com", password_hash="x",
                 role="user", entity_id=1)
    carol = User(id=2, username="carol", email="c@d.com", password_hash="x",
                 role="user", entity_id=99)
    session.add_all([alice, carol])
    session.commit()

    courant = {"user": alice}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: courant["user"]
    client = TestClient(app)
    client.session = session
    client.courant = courant
    client.utilisateurs = {"alice": alice, "carol": carol}
    yield client
    app.dependency_overrides.clear()
    session.close()


def _monde(session, *, gagnees=0, perdues=0, ouvertes=0):
    client = Client(name="ABC AM", entity_id=1, status="active")
    session.add(client); session.commit(); session.refresh(client)
    personne = Person(first_name="Jean", last_name="Dupont", entity_id=1)
    session.add(personne); session.commit(); session.refresh(personne)
    affiliation = Affiliation(person_id=personne.id, client_id=client.id,
                              start_date="2024-01-01")
    session.add(affiliation); session.commit(); session.refresh(affiliation)

    n = 0
    for _ in range(gagnees):
        n += 1
        session.add(Opportunity(reference=f"OPP-W{n}", entity_id=1,
                                owner_user_id=1, client_id=client.id,
                                title="G", status="won", amount=1_000_000))
    for i in range(perdues):
        n += 1
        session.add(Opportunity(reference=f"OPP-L{n}", entity_id=1,
                                owner_user_id=1, client_id=client.id,
                                title="P", status="lost",
                                lost_reason="coupon_too_low" if i % 2 else "timing",
                                amount=1_000_000))
    for _ in range(ouvertes):
        n += 1
        session.add(Opportunity(reference=f"OPP-O{n}", entity_id=1,
                                owner_user_id=1, client_id=client.id,
                                title="O", status="client_interest",
                                amount=2_000_000,
                                last_activity_at=datetime(2026, 8, 30)))
    session.commit()
    return client, personne, affiliation


# ── Le taux de conversion ────────────────────────────────────────────

def test_sans_dossier_tranche_le_taux_de_conversion_est_nul_pas_zero(app_client):
    """Zéro pour cent se lit « on perd tout ». Le bon message est « on ne sait
    pas encore », et cela s'écrit null."""
    _monde(app_client.session, ouvertes=3)
    corps = app_client.get("/api/client-intelligence/analytics").json()
    assert corps["opportunities"]["conversion_rate"] is None
    assert corps["opportunities"]["decided"] == 0
    assert corps["opportunities"]["open"] == 3


def test_les_dossiers_ouverts_ne_pesent_pas_sur_le_taux(app_client):
    """Sinon prospecter ferait baisser le chiffre — on punirait le bon
    comportement."""
    _monde(app_client.session, gagnees=3, perdues=1, ouvertes=20)
    corps = app_client.get("/api/client-intelligence/analytics").json()
    assert corps["opportunities"]["decided"] == 4
    assert corps["opportunities"]["conversion_rate"] == pytest.approx(0.75)


def test_le_pipeline_ne_compte_que_les_dossiers_ouverts(app_client):
    _monde(app_client.session, gagnees=2, perdues=2, ouvertes=3)
    corps = app_client.get("/api/client-intelligence/analytics").json()
    assert corps["opportunities"]["pipeline_amount"] == 6_000_000


def test_les_motifs_de_perte_sortent_du_plus_frequent_au_moins(app_client):
    _monde(app_client.session, perdues=5)
    motifs = app_client.get("/api/client-intelligence/analytics").json()["lost_reasons"]
    comptes = [c for _, c in motifs]
    assert comptes == sorted(comptes, reverse=True)
    assert sum(comptes) == 5


# ── Les délais ───────────────────────────────────────────────────────

def test_sans_historique_les_delais_sont_nuls_pas_zero(app_client):
    _monde(app_client.session, ouvertes=1)
    timing = app_client.get("/api/client-intelligence/analytics").json()["timing"]
    assert timing["median_opportunity_to_trade_days"] is None
    assert timing["median_discussion_lead_days"] is None


def test_le_delai_dossier_vers_trade_se_calcule_quand_la_chaine_existe(app_client):
    session = app_client.session
    client, personne, affiliation = _monde(session)
    opportunite = Opportunity(reference="OPP-1", entity_id=1, owner_user_id=1,
                              client_id=client.id, title="X", status="won",
                              created_at=datetime(2026, 1, 1))
    session.add(opportunite); session.commit(); session.refresh(opportunite)
    session.add(Deal(reference="D-1", user_id=1, entity_id=1,
                     client_id=client.id, primary_affiliation_id=affiliation.id,
                     opportunity_id=opportunite.id, trade_date="2026-02-01",
                     maturity_date="2028-02-01", nominal=1.0, status="actif"))
    session.commit()

    timing = app_client.get("/api/client-intelligence/analytics").json()["timing"]
    assert timing["median_opportunity_to_trade_days"] == 31.0


# ── Cloisonnement ────────────────────────────────────────────────────

def test_les_analytiques_s_arretent_a_l_entite(app_client):
    _monde(app_client.session, gagnees=3, ouvertes=2)
    app_client.courant["user"] = app_client.utilisateurs["carol"]
    corps = app_client.get("/api/client-intelligence/analytics").json()
    assert corps["clients"]["total"] == 0
    assert corps["opportunities"]["open"] == 0


def test_une_lecture_client_d_une_autre_entite_est_refusee(app_client):
    client, _, _ = _monde(app_client.session)
    app_client.courant["user"] = app_client.utilisateurs["carol"]
    reponse = app_client.get(f"/api/client-intelligence/clients/{client.id}")
    assert reponse.status_code == 404


# ── Signaux et seuils ────────────────────────────────────────────────

def test_les_seuils_sont_rendus_avec_les_signaux(app_client):
    """Un utilisateur qui voit « en sommeil » doit pouvoir savoir depuis quand
    on considère qu'un dossier dort, sans aller lire le code."""
    _monde(app_client.session, ouvertes=1)
    corps = app_client.get("/api/client-intelligence/signals").json()
    seuils = corps["thresholds"]
    assert seuils["opportunity_stale_days"] > 0
    assert seuils["maturity_horizon_days"] > 0
    assert seuils["lifecycle_event_horizon_days"] == seuils["maturity_horizon_days"]
    assert seuils["default_contact_lead_days"] > 0


def test_asof_permet_de_rejouer_une_analyse_a_une_date_passee(app_client):
    """La seule façon de vérifier qu'un signal levé la semaine dernière l'était
    à raison."""
    session = app_client.session
    client, _, _ = _monde(session)
    session.add(Interaction(entity_id=1, user_id=1, client_id=client.id,
                            interaction_date="2026-08-01", interaction_type="call",
                            summary="X", next_action="Rappeler",
                            next_action_date="2026-08-20"))
    session.commit()

    avant = app_client.get("/api/client-intelligence/signals",
                           params={"asof": "2026-08-10"}).json()
    apres = app_client.get("/api/client-intelligence/signals",
                           params={"asof": "2026-08-31"}).json()
    relances = lambda c: [s for s in c["signals"] if s["kind"] == "follow_up_due"]
    assert relances(avant) == []          # pas encore échue le 10
    assert len(relances(apres)) == 1      # échue le 31


def test_une_date_asof_illisible_est_refusee(app_client):
    reponse = app_client.get("/api/client-intelligence/signals",
                             params={"asof": "pas-une-date"})
    assert reponse.status_code == 422


def test_l_apercu_groupe_les_signaux_par_nature(app_client):
    session = app_client.session
    client, _, _ = _monde(session)
    session.add(Interaction(entity_id=1, user_id=1, client_id=client.id,
                            interaction_date="2026-08-01", interaction_type="call",
                            summary="X", next_action="Rappeler",
                            next_action_date="2026-08-20"))
    session.commit()

    corps = app_client.get("/api/client-intelligence/overview",
                           params={"asof": "2026-08-31"}).json()
    assert corps["asof"] == "2026-08-31"
    assert corps["counts"]["follow_up_due"] == 1
    assert corps["total"] >= 1
