"""Les incohérences trouvées à la relecture du module — et refermées.

Six défauts, tous découverts par sondes après que le module a été déclaré fini,
et aucun par relecture. Ils ont en commun de n'apparaître qu'en confrontant
DEUX chemins qui auraient dû dire la même chose : la fiche client et l'écran
d'analytiques, le premier import et le second, le contrôle de cohérence et le
contrôle d'appartenance.

Ces tests existent pour qu'ils ne reviennent pas.
"""
import io
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api.auth import get_current_user
from backend.app.core.client_cycle import compute_cycle
from backend.app.core.client_intelligence import (
    _dates_de_trade, deals_of_client, observed_behaviour,
    transactions_of_entity,
)
from backend.app.db.database import get_session
from backend.app.db.models import (
    Affiliation, Client, ClientTradeHistory, Interaction, Person, User,
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
    client.engine = engine
    yield client
    app.dependency_overrides.clear()
    session.close()


FICHIER = {
    "clients": [{"name": "Bank A", "client_type": "private_bank"}],
    "contacts": [{"first_name": "Jean", "last_name": "Dupont",
                  "email": "j@a.com"}],
    "affiliations": [{"person_email_or_name": "j@a.com",
                      "client_name": "Bank A", "start_date": "2022-01-01"}],
    "transactions": [
        {"client_name": "Bank A", "person_email_or_name": "j@a.com",
         "trade_date": "2024-01-15", "product_type": "Autocall",
         "notional": 1000000, "external_ref": "XS1"},
        {"client_name": "Bank A", "person_email_or_name": "j@a.com",
         "trade_date": "2024-04-15", "product_type": "Autocall",
         "notional": 1000000, "external_ref": "XS2"},
    ],
    "interactions": [
        {"client_name": "Bank A", "interaction_date": "2024-01-10",
         "interaction_type": "meeting", "summary": "Revue"},
    ],
}


def _importer(app_client, charge=None):
    contenu = json.dumps(charge or FICHIER).encode()
    return app_client.post(
        "/api/client-import/apply",
        files={"file": ("h.json", io.BytesIO(contenu), "application/json")})


def _corps_deal(**extra):
    corps = {
        "sens": "vente", "contrepartie": "Marex", "devise": "EUR",
        "nominal": 1_000_000.0, "fair_value": 98.5, "price_traded": 98.5,
        "trade_date": "2026-01-15", "strike_date": "2026-01-15",
        "value_date": "2026-01-19", "maturity_date": "2027-01-15",
        "payment_date": "2027-01-20", "T": 1.0,
        "underlyings": [{"name": "GLE.PA", "ticker": "GLE.PA", "s0_abs": 22.15}],
        "observation_times": [1.0],
        "script_snapshot": "AT MATURITY\n  PAY 1\n",
        "market_snapshot": {"r": 2.5},
    }
    corps.update(extra)
    return corps


# ── 1. Deux écrans, un seul portefeuille ─────────────────────────────

def test_les_analytiques_comptent_l_historique_importe(app_client):
    """L'écran disait « 0 transaction » pendant que la fiche client en affichait
    deux. Deux vérités pour un même portefeuille, et personne pour savoir
    laquelle croire."""
    _importer(app_client)
    session = app_client.session
    bank_a = session.exec(select(Client).where(Client.name == "Bank A")).first()

    fiche = app_client.get(
        f"/api/client-intelligence/clients/{bank_a.id}").json()
    analytics = app_client.get("/api/client-intelligence/analytics").json()

    assert fiche["behaviour"]["n_trades"] == 2
    assert analytics["trades"]["total"] == 2
    assert analytics["trades"]["imported"] == 2
    assert analytics["trades"]["by_product"] == [["Autocall", 2]]


# ── 2. Le second import ──────────────────────────────────────────────

def test_reimporter_ne_double_pas_les_interactions(app_client):
    """Le module promettait « verser deux fois ne double rien » — c'était vrai
    de tout sauf des interactions."""
    _importer(app_client)
    avant = len(app_client.session.exec(select(Interaction)).all())
    second = _importer(app_client).json()
    apres = len(app_client.session.exec(select(Interaction)).all())

    assert avant == 1
    assert apres == 1
    assert second["skipped"]["interactions"] == 1
    assert second["total_created"] == 0


# ── 3 et 4. Cohérence ne vaut pas appartenance ───────────────────────

def test_on_ne_booke_pas_sur_le_client_d_une_autre_entite(app_client):
    """Le contrôle vérifiait que le contact appartient au client, jamais que le
    client appartient à l'entité. Un rattachement peut être parfaitement
    cohérent et parfaitement indu — et le cliché figé recopiait au passage le
    nom d'un client qu'on n'a pas le droit de lire."""
    _importer(app_client)
    bank_a = app_client.session.exec(
        select(Client).where(Client.name == "Bank A")).first()

    app_client.courant["user"] = app_client.utilisateurs["carol"]
    reponse = app_client.post("/api/deals",
                              json=_corps_deal(client_id=bank_a.id))
    assert reponse.status_code == 422
    assert "introuvable" in reponse.text


def test_on_ne_booke_pas_sur_l_opportunite_d_une_autre_entite(app_client):
    _importer(app_client)
    bank_a = app_client.session.exec(
        select(Client).where(Client.name == "Bank A")).first()
    opportunite = app_client.post(
        "/api/opportunities",
        json={"client_id": bank_a.id, "title": "X"}).json()

    app_client.courant["user"] = app_client.utilisateurs["carol"]
    reponse = app_client.post(
        "/api/deals", json=_corps_deal(opportunity_id=opportunite["id"]))
    assert reponse.status_code == 422


def test_un_rattachement_legitime_passe_toujours(app_client):
    """Le contrôle ajouté ne doit pas fermer le chemin normal."""
    _importer(app_client)
    session = app_client.session
    bank_a = session.exec(select(Client).where(Client.name == "Bank A")).first()
    affiliation = session.exec(
        select(Affiliation).where(Affiliation.client_id == bank_a.id)).first()
    mandate = app_client.post(f"/api/clients/{bank_a.id}/mandates", json={
        "name": "Compte principal", "mandate_type": "account",
    }).json()

    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=bank_a.id, mandate_id=mandate["id"],
        primary_affiliation_id=affiliation.id,
        commercial_reason="Rattachement direct contrôlé"))
    assert reponse.status_code in (200, 201), reponse.text
    assert reponse.json()["client_id"] == bank_a.id


# ── 5. Un mot, un seul sens ──────────────────────────────────────────

def test_plusieurs_lignes_le_meme_jour_ne_contredisent_pas_les_deux_ecrans():
    """Un panier alloué en trois lignes le même jour est UN épisode
    d'investissement pour la cadence, mais bien trois transactions.

    Les deux chiffres sont justes ; les appeler tous deux « n_trades » faisait
    afficher 5 d'un côté et 3 de l'autre sur le même écran."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    client = Client(name="Bank A", entity_id=1)
    session.add(client); session.commit(); session.refresh(client)
    for i, jour in enumerate(["2024-01-15", "2024-01-15", "2024-01-15",
                              "2024-04-15", "2024-07-15"]):
        session.add(ClientTradeHistory(
            entity_id=1, client_id=client.id, trade_date=jour,
            product_type="Autocall", notional=1e6, external_ref=f"XS{i}"))
    session.commit()

    transactions = deals_of_client(session, client.id)
    cycle = compute_cycle(_dates_de_trade(transactions), asof=date(2024, 10, 1))
    comportement = observed_behaviour(transactions)

    assert comportement["n_trades"] == 5
    assert cycle.n_trades == 5              # le même mot, le même chiffre
    assert cycle.n_trading_days == 3        # ce sur quoi la cadence se compte
    assert cycle.n_intervals == 2
    assert "5 transactions réparties sur 3 journées" in cycle.explanation[0]


def test_tout_le_meme_jour_reste_un_historique_insuffisant():
    """Cinq lignes le même jour ne donnent aucun intervalle : le moteur doit
    dire qu'il ne sait pas, et non prétendre à cinq observations."""
    cycle = compute_cycle([date(2024, 1, 15)] * 5, asof=date(2024, 6, 1))
    assert cycle.confidence == "insufficient_history"
    assert cycle.n_trades == 5
    assert cycle.n_trading_days == 1
    assert cycle.expected_window_start is None
    assert "toutes le même jour" in cycle.explanation[0]


# ── 6. Le coût qui grandit avec le portefeuille ──────────────────────

def test_les_analytiques_ne_font_pas_de_n_plus_un(app_client):
    """62 requêtes pour 31 clients, mesuré. Un N+1 grandit exactement avec le
    portefeuille, donc il ne se voit jamais avant la mise en service."""
    session = app_client.session
    for n in range(30):
        session.add(Client(name=f"Client {n}", entity_id=1, status="active"))
    session.commit()

    compteur = {"n": 0}

    def _compter(conn, cur, stmt, params, ctx, many):
        compteur["n"] += 1

    event.listen(app_client.engine, "before_cursor_execute", _compter)
    try:
        transactions = transactions_of_entity(session, 1)
    finally:
        event.remove(app_client.engine, "before_cursor_execute", _compter)

    assert compteur["n"] == 2, (
        f"{compteur['n']} requêtes pour 30 clients — le coût doit rester "
        f"constant, pas proportionnel au portefeuille.")
    assert isinstance(transactions, list)


def test_les_signaux_ne_font_pas_de_n_plus_un_non_plus(app_client):
    """Le même défaut vivait en second exemplaire dans les signaux, qui
    parcourent chaque client pour comparer sa cadence à son propre historique.
    Un N+1 corrigé à un endroit et laissé à l'autre n'est pas corrigé."""
    from backend.app.core.client_signals import build_signals

    session = app_client.session
    for n in range(30):
        session.add(Client(name=f"Client {n}", entity_id=1, status="active"))
    session.commit()

    compteur = {"n": 0}

    def _compter(conn, cur, stmt, params, ctx, many):
        compteur["n"] += 1

    event.listen(app_client.engine, "before_cursor_execute", _compter)
    try:
        build_signals(session, entity_id=1, user_id=1, asof=date(2026, 8, 31))
    finally:
        event.remove(app_client.engine, "before_cursor_execute", _compter)

    # Un plancher fixe (clients, interactions, opportunités, deals, historique,
    # maturités) et non un multiple du nombre de clients.
    assert compteur["n"] < 15, (
        f"{compteur['n']} requêtes pour 31 clients — le coût grandit avec le "
        f"portefeuille.")
