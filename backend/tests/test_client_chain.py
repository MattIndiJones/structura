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
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import auth, clients, persons, opportunities, rfq, deals, products, pricing, inlife, client_intelligence
from backend.app.db.database import get_session
from backend.app.db.models import (Affiliation, Counterparty, Deal, Entity, Opportunity,
    AuditEvent, BookingCommand, ProductRecord, RfqDesk, RfqDeskMembership, RfqProvider, RfqRequest, User)
from backend.app.db.product_migrations import migrate_product_links
from backend.app.services.product_repository import load_product
from backend.tests.product_helpers import add_pricing_receipt


# Une RFQ « to trade » exige un script en mode Expert : un CONSTAT déclaré ET
# référencé par un événement (api/rfq.py:_is_expert_script). Même forme que
# celle des tests RFQ existants.
SCRIPT_EXPERT = "CONSTAT() CAL\nAT CAL:\n  PAY 0\nAT MATURITY\n  PAY 1"

RFQ_PARAMS = {
    "underlyings": [{"name": "Euro Stoxx 50", "ticker": "^STOXX50E", "ccy": "EUR"}],
    "notional": 2_000_000.0,
    "currency": "EUR",
    "T": 3.0,
    "strike_date": "2026-09-15",
    "value_date": "2026-09-17",
    "payment_date": "2029-09-20",
    "constats": {
        "CAL": {
            "start_date": "2026-09-15",
            "end_date": "2029-09-15",
            "roll_date": "2029-09-15",
            "frequency": "1Y",
        },
    },
}


@pytest.fixture
def app_client():
    """Real JWTs, current desk permissions and Product guards on an isolated schema."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            migrate_product_links(session.connection())
            session.add_all([Entity(id=1, name="CRM test"), Entity(id=99, name="Other organization")])
            session.flush()
            users = {
                name: User(id=user_id, username=name, email=f"{name}@example.test",
                           password_hash="test-only", role=role, entity_id=entity_id)
                for name, user_id, role, entity_id in [
                    ("alice", 1, "user", 1), ("carol", 2, "user", 99),
                    ("operations", 3, "ops_maker", 1), ("controller", 4, "checker", 1),
                    ("outsider", 5, "user", 1)]
            }
            session.add_all(users.values())
            session.flush()
            session.add_all([RfqDesk(id=11, name="Sales", entity_id=1),
                             RfqDesk(id=99, name="Other sales", entity_id=99),
                             Counterparty(id=1, name="Marex", active=True)])
            session.flush()
            for name, desk, rights in [
                ("alice", 11, ["read", "prepare", "price", "select", "solicit", "book"]),
                ("carol", 99, ["read", "prepare", "price", "select", "solicit", "book"]),
                ("operations", 11, ["read", "book"]), ("controller", 11, ["read"])]:
                session.add(RfqDeskMembership(user_id=users[name].id, desk_id=desk,
                                              rights_json=json.dumps(rights)))
            session.add(RfqProvider(id=1, label="Marex", counterparty_id=1))
            session.commit()
            app = FastAPI()
            for module in [auth, clients, persons, opportunities, rfq, deals, products, pricing, inlife, client_intelligence]:
                app.include_router(module.router)
            app.dependency_overrides[get_session] = lambda: session
            with TestClient(app) as client:
                def login(name):
                    user = users[name]
                    client.headers["Authorization"] = "Bearer " + auth._make_token(
                        user.id, user.role, user.entity_id, auth_version=user.auth_version)
                    return client
                client.session = session
                client.login = login
                client.utilisateurs = users
                login("alice")
                yield client
    finally:
        engine.dispose()


def _created(response):
    """Stop at the failed creation rather than masking it with a later KeyError."""
    assert response.status_code == 201, response.text
    return response.json()


def _contexte(app_client, nom_client="Bank A"):
    """Un client, son mandat actif, une personne et une opportunité ouverte."""
    fiche = _created(app_client.post("/api/clients", json={
        "name": nom_client, "client_type": "private_bank", "data_origin": "native"}))
    personne = _created(app_client.post("/api/persons", json={
        "first_name": "Jean", "last_name": "Dupont",
        "client_id": fiche["id"], "start_date": "2022-01-01",
        "commercial_role": "portfolio_manager"}))
    affiliation = personne["current_affiliation"]["id"]
    mandat = _created(app_client.post(f"/api/clients/{fiche['id']}/mandates", json={
        "name": "Mandat principal", "mandate_type": "mandate",
    }))
    opportunite = _created(app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "primary_affiliation_id": affiliation,
        "mandate_id": mandat["id"],
        "title": "Phoenix 3Y", "amount": 2_000_000, "currency": "EUR"}))
    return fiche, personne, affiliation, opportunite


def _corps_deal(**extra):
    corps = {
        "sens": "vente", "contrepartie": "Marex", "counterparty_id": 1, "devise": "EUR",
        "nominal": 1_000_000.0, "fair_value": 98.5, "price_traded": 98.5,
        "trade_date": "2026-01-15", "strike_date": "2026-01-15",
        "value_date": "2026-01-19", "maturity_date": "2027-01-15",
        "payment_date": "2027-01-20", "T": 1.0,
        "underlyings": [{"name": "GLE.PA", "ticker": "GLE.PA", "ccy": "EUR",
                         "s0_abs": 22.15}],
        "observation_times": [1.0],
        "script_snapshot": "AT MATURITY\n  PAY 1\n",
        "market_snapshot": {"r": 2.5},
    }
    corps.update(extra)
    return add_pricing_receipt(corps)


# ── §78 — la RFQ créée depuis une opportunité ────────────────────────

def test_une_rfq_creee_depuis_une_opportunite_garde_le_lien(app_client):
    _, _, _, opportunite = _contexte(app_client)

    reponse = app_client.post("/api/rfq", json={"pilot_desk_id": 11,
        "name": "AO Phoenix 3Y", "kind": "to_trade", "sens": "achat",
        "script_snapshot": SCRIPT_EXPERT, "params": RFQ_PARAMS,
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
    app_client.login("carol")

    reponse = app_client.post("/api/rfq", json={"pilot_desk_id": 99,
        "name": "Tentative", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": RFQ_PARAMS,
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
    fiche_b = _created(app_client.post("/api/clients", json={"name": "Bank B", "data_origin": "native"}))
    mandat_b = _created(app_client.post(f"/api/clients/{fiche_b['id']}/mandates", json={
        "name": "Mandat B", "mandate_type": "mandate",
    }))

    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], mandate_id=mandat_b["id"],
        primary_affiliation_id=affiliation_a, commercial_reason="Rattachement test"))
    assert reponse.status_code == 422
    assert "Bank B" in reponse.text


def test_une_opportunite_d_un_autre_client_est_refusee_au_booking(app_client):
    fiche_a, _, affiliation_a, opportunite_a = _contexte(app_client, "Bank A")
    fiche_b = _created(app_client.post("/api/clients", json={"name": "Bank B", "data_origin": "native"}))

    mandat_b = _created(app_client.post(f"/api/clients/{fiche_b['id']}/mandates", json={
        "name": "Mandat B", "mandate_type": "mandate"}))
    reponse = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], mandate_id=mandat_b["id"],
        opportunity_id=opportunite_a["id"]))
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "OPPORTUNITY_CLIENT_MISMATCH"


def test_un_contact_sans_client_est_refuse(app_client):
    _, _, affiliation, _ = _contexte(app_client)
    reponse = app_client.post("/api/deals", json=_corps_deal(
        primary_affiliation_id=affiliation))
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "DEAL_CONTACT_WITHOUT_CLIENT"


# ── La chaîne se reconstruit, avec le client de l'ÉPOQUE ─────────────

def test_la_chaine_se_remonte_du_trade_jusqu_a_la_personne(app_client):
    fiche, personne, affiliation, opportunite = _contexte(app_client)
    rfq, payload = _prepare_rfq_booking(app_client, opportunite)
    deal = _created(app_client.post("/api/deals", json=payload))

    assert deal["rfq_id"] == rfq["id"]
    assert deal["product_id"] == rfq["product_id"]
    assert deal["product_terms_version"] == rfq["product_terms_version"]
    assert deal["opportunity_id"] == opportunite["id"]
    assert deal["client_id"] == fiche["id"]
    assert deal["primary_affiliation_id"] == affiliation
    assert deal["counterparty_id"] == 1
    relue = app_client.get(f"/api/opportunities/{deal['opportunity_id']}")
    assert relue.status_code == 200, relue.text
    assert relue.json()["client_id"] == fiche["id"]
    assert relue.json()["primary_contact"]["person_id"] == personne["id"]
    assert [r["id"] for r in relue.json()["rfqs"]] == [rfq["id"]]
    assert [d["id"] for d in relue.json()["deals"]] == [deal["id"]]
    product = load_product(app_client.session, deal["product_id"])
    assert product.execution.to_dict()["deal_id"] == deal["id"]
    assert product.commercial.client_id == fiche["id"]
    assert product.commercial.opportunity_id == opportunite["id"]
    assert len(app_client.session.exec(select(ProductRecord)).all()) == 1
    assert app_client.session.exec(text("PRAGMA foreign_key_check")).all() == []
    for actor in ["operations", "controller"]:
        app_client.login(actor)
        visible = app_client.get(f"/api/deals/{deal['id']}")
        assert visible.status_code == 200, visible.text
        assert visible.json()["client_id"] == fiche["id"]
        projection = app_client.get(f"/api/rfq/{rfq['id']}")
        assert projection.status_code == 200, projection.text
        assert projection.json()["model_price"] is None
    for actor in ["outsider", "carol"]:
        app_client.login(actor)
        for path in [f"/api/deals/{deal['id']}", f"/api/rfq/{rfq['id']}", f"/api/products/{deal['product_id']}"]:
            denied = app_client.get(path)
            assert denied.status_code == 404, denied.text
    app_client.login("alice")


def test_le_trade_reste_chez_l_ancien_employeur_apres_un_depart(app_client):
    """Le cœur du §30 et du §8 réunis, vu depuis la chaîne complète.

    Jean traite chez Bank A, puis rejoint Bank B. Le trade ne suit pas, et le
    cliché figé continue de nommer Bank A — même si la fiche de Jean, elle,
    affiche désormais Bank B.
    """
    fiche_a, personne, affiliation_a, opportunite = _contexte(app_client, "Bank A")
    deal = _created(app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_a["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation_a)))

    fiche_b = _created(app_client.post("/api/clients", json={"name": "Bank B", "data_origin": "native"}))
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
    _created(app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche["id"], opportunity_id=opportunite["id"],
        mandate_id=opportunite["mandate_id"],
        primary_affiliation_id=affiliation)))

    reponse = app_client.delete(f"/api/opportunities/{opportunite['id']}")
    assert reponse.status_code == 409
    assert reponse.json()["detail"]["code"] == "OPPORTUNITY_HAS_HISTORY"


# ── §78 / §79 — non-régression du module existant ────────────────────

def test_une_rfq_sans_opportunite_fonctionne_comme_avant(app_client):
    """Le cas courant, et celui de tout l'existant : rien ne doit être exigé."""
    reponse = app_client.post("/api/rfq", json={"pilot_desk_id": 11,
        "name": "AO indépendant", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": RFQ_PARAMS})
    assert reponse.status_code in (200, 201), reponse.text
    assert reponse.json()["opportunity_id"] is None


def test_une_rfq_directe_peut_etre_rattachee_au_client_et_au_mandat(app_client):
    fiche, _, affiliation, opportunite = _contexte(app_client)
    reponse = app_client.post("/api/rfq", json={"pilot_desk_id": 11,
        "name": "AO direct Client", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": RFQ_PARAMS,
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
    fiche = _created(app_client.post("/api/clients", json={"name": "Client sans mandat", "data_origin": "native"}))
    opportunite = _created(app_client.post("/api/opportunities", json={
        "client_id": fiche["id"], "title": "Besoin encore à qualifier",
    }))
    reponse = app_client.post("/api/rfq", json={"pilot_desk_id": 11,
        "name": "AO prématuré", "kind": "indicatif", "sens": "achat",
        "script_snapshot": "AT MATURITY\n  PAY 1\n", "params": RFQ_PARAMS,
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
    fiche_b = _created(app_client.post("/api/clients", json={"name": "Bank B", "data_origin": "native"}))

    mandate_b = _created(app_client.post(f"/api/clients/{fiche_b['id']}/mandates", json={
        "name": "Mandat B", "mandate_type": "mandate"}))
    before_counters = app_client.session.exec(text("SELECT prefix, last_value FROM reference_counters ORDER BY prefix")).all()
    rejected = app_client.post("/api/deals", json=_corps_deal(
        client_id=fiche_b["id"], mandate_id=mandate_b["id"], primary_affiliation_id=affiliation_a))

    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"]["code"] == "AFFILIATION_CLIENT_MISMATCH"
    assert app_client.session.exec(select(Deal)).all() == []
    assert app_client.session.exec(select(ProductRecord)).all() == []
    assert app_client.session.exec(text("SELECT prefix, last_value FROM reference_counters ORDER BY prefix")).all() == before_counters
    premier = _created(app_client.post("/api/deals", json=_corps_deal()))
    # Le refus n'a laissé aucun trou : le premier deal réellement booké prend
    # bien le numéro 001.
    assert premier["reference"].endswith("-001")



def _prepare_rfq_booking(client, opportunity):
    params = deepcopy(RFQ_PARAMS)
    strike = date.today() + timedelta(days=14)
    maturity = strike + timedelta(days=1096)
    params.update(strike_date=strike.isoformat(), value_date=(strike + timedelta(days=2)).isoformat(),
                  maturity_date=maturity.isoformat(), payment_date=(maturity + timedelta(days=5)).isoformat(),
                  T=round((maturity - strike).days / 365.25, 6),
                  constats={"CAL": {"start_date": strike.isoformat(), "end_date": maturity.isoformat(),
                                    "roll_date": maturity.isoformat(), "frequency": "1Y"}})
    params.update(r=0.025, N=1000, seed=42, model="constant", corr_matrix=[[1.0]],
                  valuation_date=date.today().isoformat())
    rfq = _created(client.post("/api/rfq", json={
        "pilot_desk_id": 11, "name": "Chaîne CRM exécutée", "kind": "to_trade", "sens": "achat",
        "script_snapshot": SCRIPT_EXPERT, "params": params,
        "transaction_format": "EMTN", "instrument_family": "Note", "payoff_family": "Phoenix",
        "opportunity_id": opportunity["id"]}))
    composed = client.post(f"/api/rfq/{rfq['id']}/pricing-input", json={
        "expected_terms_version": rfq["product_terms_version"]})
    assert composed.status_code == 200, composed.text
    pricing_input = composed.json()["pricing_input"]
    calculated = client.post("/api/price/in-life", json=pricing_input)
    assert calculated.status_code == 200, calculated.text
    receipt = calculated.json()["pricing_receipt"]
    priced = client.patch(f"/api/rfq/{rfq['id']}", json={
        "model_price": receipt["price_pct"], "pricing_receipt": receipt,
        "expected_model_input_hash": composed.json()["input_hash"]})
    assert priced.status_code == 200, priced.text
    quote = _created(client.post(f"/api/rfq/{rfq['id']}/quotes", json={"provider": "Marex", "provider_id": 1}))
    answered = client.patch(f"/api/rfq/{rfq['id']}/quotes/{quote['id']}", json={
        "price": 98.5, "firmness": "FIRM", "currency": "EUR",
        "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()})
    assert answered.status_code == 200, answered.text
    selected = client.patch(f"/api/rfq/{rfq['id']}", json={
        "selected_quote_id": quote["id"], "expected_quote_revision": answered.json()["revision"],
        "selection_reason_code": "price"})
    assert selected.status_code == 200, selected.text
    payload = {
        "rfq_id": rfq["id"], "product_id": rfq["product_id"],
        "product_terms_version": rfq["product_terms_version"], "command_key": "f06-crm-booking",
        "sens": "vente", "contrepartie": "Marex", "counterparty_id": 1, "devise": "EUR",
        "nominal": params["notional"], "fair_value": receipt["price_pct"], "price_traded": 98.5,
        "trade_date": date.today().isoformat(), "strike_date": pricing_input["strike_date"],
        "value_date": pricing_input["value_date"], "maturity_date": pricing_input["maturity_date"],
        "payment_date": pricing_input["payment_date"], "T": pricing_input["T"],
        "script_snapshot": pricing_input["script"], "observation_times": [],
        "underlyings": [{**u, "s0_abs": None} for u in pricing_input["underlyings"]],
        "market_snapshot": {"pricing_input": pricing_input}, "pricing_receipt": receipt,
    }
    return rfq, payload


@pytest.mark.parametrize("invalid", ["client", "bank", "notional"])
def test_rfq_booking_refusal_preserves_crm_product_and_allows_clean_retry(app_client, invalid):
    _, _, _, opportunity = _contexte(app_client)
    request, payload = _prepare_rfq_booking(app_client, opportunity)
    session = app_client.session
    rejected_payload = deepcopy(payload)
    if invalid == "client":
        other = _created(app_client.post("/api/clients", json={"name": "Other client", "data_origin": "native"}))
        mandate = _created(app_client.post(f"/api/clients/{other['id']}/mandates", json={
            "name": "Other mandate", "mandate_type": "mandate"}))
        rejected_payload.update(client_id=other["id"], mandate_id=mandate["id"])
    elif invalid == "bank":
        session.add(Counterparty(id=2, name="Other bank", active=True))
        session.commit()
        rejected_payload.update(counterparty_id=2, contrepartie="Other bank")
    else:
        rejected_payload["nominal"] = payload["nominal"] / 2
    product_before = load_product(session, request["product_id"]).to_dict()
    rfq_before = session.get(RfqRequest, request["id"]).model_dump(mode="json")
    opportunity_before = session.get(Opportunity, opportunity["id"]).model_dump(mode="json")
    counters_before = session.exec(text("SELECT prefix, last_value FROM reference_counters ORDER BY prefix")).all()
    refused = app_client.post("/api/deals", json=rejected_payload)
    assert refused.status_code == 422, refused.text
    if invalid == "client":
        assert refused.json()["detail"]["code"] == "RFQ_COMMERCIAL_CONTEXT_MISMATCH"
    elif invalid == "bank":
        assert "identité juridique de la cotation" in refused.text
    else:
        assert "notional" in refused.text
    assert session.exec(select(Deal)).all() == []
    assert session.exec(select(BookingCommand)).all() == []
    assert load_product(session, request["product_id"]).to_dict() == product_before
    assert session.get(RfqRequest, request["id"]).model_dump(mode="json") == rfq_before
    assert session.get(Opportunity, opportunity["id"]).model_dump(mode="json") == opportunity_before
    assert session.exec(text("SELECT prefix, last_value FROM reference_counters ORDER BY prefix")).all() == counters_before
    assert len(session.exec(select(AuditEvent).where(AuditEvent.action == "BOOKING_REJECTED")).all()) == 1
    booked = _created(app_client.post("/api/deals", json=payload))
    retried = _created(app_client.post("/api/deals", json=payload))
    assert booked["id"] == retried["id"]
    assert booked["client_id"] == opportunity["client_id"]
    assert booked["mandate_id"] == opportunity["mandate_id"]
    assert booked["counterparty_id"] == 1
    assert booked["product_id"] == request["product_id"]
    assert len(session.exec(select(Deal)).all()) == len(session.exec(select(BookingCommand)).all()) == 1
    assert session.exec(text("PRAGMA foreign_key_check")).all() == []
