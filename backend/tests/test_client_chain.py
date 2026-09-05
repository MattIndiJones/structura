"""La chaîne Opportunity → RFQ → Trade, et sa non-régression.

Deux exigences opposées se rencontrent ici.

D'un côté, la chaîne doit se reconstruire : depuis un trade, on doit pouvoir
remonter à l'appel d'offres, au besoin commercial, au client et à la personne
qui l'a porté — avec le CLIENT DE L'ÉPOQUE, pas celui d'aujourd'hui.

De l'autre, tout le module d'appel d'offres existait avant celui-ci et doit
continuer de fonctionner à l'identique. Une RFQ sans opportunité, un deal sans
client : ce sont les cas courants, et aucun des deux ne doit rien exiger de
neuf. C'est ce que vérifient les tests « non-régression » de la fin.
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import Affiliation, Deal, Opportunity, RfqRequest, User


# Une RFQ « to trade » exige un script en mode Expert : un CONSTAT déclaré ET
# référencé par un événement (api/rfq.py:_is_expert_script). Même forme que
# celle des tests RFQ existants.
SCRIPT_EXPERT = "CONSTAT() Cal\nAT Cal:\n  PAY 0\nAT MATURITY\n  PAY 1"


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
    alice = User(id=1, username="alice", email="alice@desk.com",
                 password_hash="x", role="user", entity_id=1)
    carol = User(id=2, username="carol", email="carol@autre.com",
                 password_hash="x", role="user", entity_id=99)
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


def _contexte(app_client, nom_client="Bank A"):
    """Un client, son mandat actif, une personne et une opportunité ouverte."""
    fiche = app_client.post("/api/clients", json={
        "name": nom_client, "client_type": "private_bank"}).json()
    personne = app_client.post("/api/persons", json={
        "first_name": "Jean", "last_name": "Dupont",
        "client_id": fiche["id"], "start_date": "2022-01-01",
        "commercial_role": "portfolio_manager"}).json()
    affiliation = personne["current_affiliation"]["id"]
    mandat = app_client.post(f"/api/clients/{fiche['id']}/mandates", json={
        "name": "Mandat principal", "mandate_type": "mandate",
    }).json()
    opportunite = app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "primary_affiliation_id": affiliation,
        "mandate_id": mandat["id"],
        "title": "Phoenix 3Y", "amount": 2_000_000, "currency": "EUR"}).json()
    return fiche, personne, affiliation, opportunite


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


# ── §78 — la RFQ créée depuis une opportunité ────────────────────────

def test_une_rfq_creee_depuis_une_opportunite_garde_le_lien(app_client):
    _, _, _, opportunite = _contexte(app_client)

    reponse = app_client.post("/api/rfq", json={
        "name": "AO Phoenix 3Y", "kind": "to_trade", "sens": "achat",
        "script_snapshot": SCRIPT_EXPERT, "params": {},
        "transaction_format": "EMTN", "instrument_family": "Note",
        "payoff_family": "Phoenix",
        "opportunity_id": opportunite["id"]})
    assert reponse.status_code in (200, 201), reponse.text
    rfq = reponse.json()
    assert rfq["opportunity_id"] == opportunite["id"]
    assert rfq["client_id"] == opportunite["client_id"]
    assert rfq["mandate_id"] == opportunite["mandate_id"]
    assert rfq["commercial_context"]["mandate"]["name"] == "Mandat principal"
    assert rfq["transaction_format"] == "EMTN"
    assert rfq["instrument_family"] == "Note"

    # Et l'opportunité voit sa RFQ : le lien se lit dans les deux sens.
    relue = app_client.get(f"/api/opportunities/{opportunite['id']}").json()
    assert [r["id"] for r in relue["rfqs"]] == [rfq["id"]]


def test_une_opportunite_d_une_autre_entite_est_refusee(app_client):
    """Un appel direct ne doit pas pouvoir rattacher une RFQ à un dossier qu'on
    ne voit pas — le lien sert ensuite à reconstruire jusqu'au client."""
    _, _, _, opportunite = _contexte(app_client)
    app_client.courant["user"] = app_client.utilisateurs["carol"]

    reponse = app_client.post("/api/rfq", json={
        "name": "Tentative", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": {},
        "opportunity_id": opportunite["id"]})
    assert reponse.status_code == 404


# ── §37/§38 — le trade porte son client ──────────────────────────────

def test_un_deal_booke_depuis_une_opportunite_porte_son_rattachement(app_client):
    fiche, personne, affiliation, opportunite = _contexte(app_client)

    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation))
    assert reponse.status_code in (200, 201), reponse.text
    deal = reponse.json()

    assert deal["client_id"] == fiche["id"]
    assert deal["opportunity_id"] == opportunite["id"]
    assert deal["mandate_id"] == opportunite["mandate_id"]
    assert deal["primary_affiliation_id"] == affiliation

    # Le cliché doit porter ce qui était vrai au moment du trade.
    cliche = deal["client_provenance"]
    assert cliche["client"]["name"] == "Bank A"
    assert cliche["contact"]["name"] == "Jean Dupont"
    assert cliche["opportunity"]["reference"] == opportunite["reference"]
    assert cliche["mandate"]["name"] == "Mandat principal"

    relue = app_client.get(f"/api/opportunities/{opportunite['id']}").json()
    assert relue["status"] == "partially_won"


def test_un_trade_ne_peut_pas_melanger_deux_clients(app_client):
    """Le refus le plus important de la chaîne : « client B, contact chez A »
    corromprait toute statistique par affiliation sans jamais se signaler."""
    _, _, affiliation_a, _ = _contexte(app_client, "Bank A")
    fiche_b = app_client.post("/api/clients", json={"name": "Bank B"}).json()
    mandat_b = app_client.post(f"/api/clients/{fiche_b['id']}/mandates", json={
        "name": "Mandat B", "mandate_type": "mandate",
    }).json()

    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], mandate_id=mandat_b["id"],
        primary_affiliation_id=affiliation_a, commercial_reason="Rattachement test"))
    assert reponse.status_code == 422
    assert "Bank B" in reponse.text


def test_une_opportunite_d_un_autre_client_est_refusee_au_booking(app_client):
    fiche_a, _, affiliation_a, opportunite_a = _contexte(app_client, "Bank A")
    fiche_b = app_client.post("/api/clients", json={"name": "Bank B"}).json()

    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], mandate_id=opportunite_a["mandate_id"],
        opportunity_id=opportunite_a["id"]))
    assert reponse.status_code == 422


def test_un_contact_sans_client_est_refuse(app_client):
    _, _, affiliation, _ = _contexte(app_client)
    reponse = app_client.post("/api/deals", json=_corps_deal(
        primary_affiliation_id=affiliation))
    assert reponse.status_code == 422


# ── La chaîne se reconstruit, avec le client de l'ÉPOQUE ─────────────

def test_la_chaine_se_remonte_du_trade_jusqu_a_la_personne(app_client):
    fiche, personne, affiliation, opportunite = _contexte(app_client)
    rfq = app_client.post("/api/rfq", json={
        "name": "AO", "kind": "to_trade", "sens": "achat",
        "script_snapshot": SCRIPT_EXPERT, "params": {},
        "opportunity_id": opportunite["id"]}).json()
    deal = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation)).json()

    # Trade → Opportunity → Client → Affiliation → Person
    assert deal["opportunity_id"] == opportunite["id"]
    relue = app_client.get(f"/api/opportunities/{deal['opportunity_id']}").json()
    assert relue["client_id"] == fiche["id"]
    assert relue["primary_contact"]["person_id"] == personne["id"]
    assert rfq["opportunity_id"] == relue["id"]
    assert [d["id"] for d in relue["deals"]] == [deal["id"]]


def test_le_trade_reste_chez_l_ancien_employeur_apres_un_depart(app_client):
    """Le cœur du §30 et du §8 réunis, vu depuis la chaîne complète.

    Jean traite chez Bank A, puis rejoint Bank B. Le trade ne suit pas, et le
    cliché figé continue de nommer Bank A — même si la fiche de Jean, elle,
    affiche désormais Bank B.
    """
    fiche_a, personne, affiliation_a, opportunite = _contexte(app_client, "Bank A")
    deal = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_a["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation_a)).json()

    fiche_b = app_client.post("/api/clients", json={"name": "Bank B"}).json()
    app_client.post(f"/api/persons/{personne['id']}/change-company", json={
        "new_client_id": fiche_b["id"], "start_date": "2026-09-01",
        "commercial_role": "cio"})

    relu = app_client.get(f"/api/deals/{deal['id']}").json()
    assert relu["client_id"] == fiche_a["id"]
    assert relu["primary_affiliation_id"] == affiliation_a
    assert relu["client_provenance"]["client"]["name"] == "Bank A"

    # Et la personne, elle, est bien chez Bank B aujourd'hui.
    fiche_personne = app_client.get(f"/api/persons/{personne['id']}").json()
    assert fiche_personne["current_affiliation"]["client_name"] == "Bank B"


def test_l_opportunite_liee_a_un_trade_refuse_la_suppression(app_client):
    """Supprimer l'opportunité briserait le maillon central de la chaîne."""
    fiche, _, affiliation, opportunite = _contexte(app_client)
    app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation))

    reponse = app_client.delete(f"/api/opportunities/{opportunite['id']}")
    assert reponse.status_code == 409
    assert reponse.json()["detail"]["code"] == "OPPORTUNITY_HAS_HISTORY"


# ── §78 / §79 — non-régression du module existant ────────────────────

def test_une_rfq_sans_opportunite_fonctionne_comme_avant(app_client):
    """Le cas courant, et celui de tout l'existant : rien ne doit être exigé."""
    reponse = app_client.post("/api/rfq", json={
        "name": "AO indépendant", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": {}})
    assert reponse.status_code in (200, 201), reponse.text
    assert reponse.json()["opportunity_id"] is None


def test_une_rfq_directe_peut_etre_rattachee_au_client_et_au_mandat(app_client):
    fiche, _, affiliation, opportunite = _contexte(app_client)
    reponse = app_client.post("/api/rfq", json={
        "name": "AO direct Client", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": {},
        "client_id": fiche["id"], "mandate_id": opportunite["mandate_id"],
        "primary_affiliation_id": affiliation,
    })
    assert reponse.status_code in (200, 201), reponse.text
    rfq = reponse.json()
    assert rfq["client_id"] == fiche["id"]
    assert rfq["mandate_id"] == opportunite["mandate_id"]
    assert rfq["opportunity_id"] is None
    assert rfq["commercial_context"]["client"]["name"] == "Bank A"


def test_une_rfq_client_sans_mandat_est_refusee(app_client):
    fiche = app_client.post("/api/clients", json={"name": "Client sans mandat"}).json()
    opportunite = app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "title": "Besoin encore à qualifier",
    }).json()
    reponse = app_client.post("/api/rfq", json={
        "name": "AO prématuré", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": {},
        "opportunity_id": opportunite["id"],
    })
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "OPPORTUNITY_MANDATE_REQUIRED"


def test_un_deal_sans_client_se_booke_comme_avant(app_client):
    reponse = app_client.post("/api/deals", json=_corps_deal())
    assert reponse.status_code in (200, 201), reponse.text
    deal = reponse.json()
    assert deal["client_id"] is None
    assert deal["opportunity_id"] is None
    # Et surtout : pas de cliché vide. Un deal non rattaché n'en porte pas.
    assert deal["client_provenance"] is None


def test_un_deal_produit_peut_porter_une_structure_juridique_sans_client(app_client):
    reponse = app_client.post("/api/deals", json=_corps_deal(
        transaction_format="OTC", instrument_family="Swap",
        payoff_family="Swap", documentation_reference="ISDA-2026-17"))
    assert reponse.status_code in (200, 201), reponse.text
    deal = reponse.json()
    assert deal["client_id"] is None
    assert deal["transaction_format"] == "OTC"
    assert deal["instrument_family"] == "Swap"


def test_un_deal_direct_client_exige_un_motif(app_client):
    fiche, _, _, opportunite = _contexte(app_client)
    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche["id"], mandate_id=opportunite["mandate_id"]))
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "DIRECT_CLIENT_LINK_REASON_REQUIRED"


def test_le_refus_de_rattachement_n_alloue_pas_de_reference(app_client):
    """Les contrôles de rattachement sont posés AVANT l'allocation, avec les
    autres refus : un booking refusé ne doit pas consommer un numéro de deal."""
    _, _, affiliation_a, _ = _contexte(app_client, "Bank A")
    fiche_b = app_client.post("/api/clients", json={"name": "Bank B"}).json()

    app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], primary_affiliation_id=affiliation_a))

    premier = app_client.post("/api/deals", json=_corps_deal()).json()
    # Le refus n'a laissé aucun trou : le premier deal réellement booké prend
    # bien le numéro 001.
    assert premier["reference"].endswith("-001")
