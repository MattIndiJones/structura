"""C01: real authentication, action permissions and cross-module confidentiality."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import auth, trading, rfq, products, client_intelligence, opportunities
from backend.app.api import pricing, inlife, product_optimizer, simulation, scenarios, compute
from backend.app.api import deals, alerts, documents, portfolios, amc_studies, valuation_notes
from backend.app.db.database import get_session
from backend.app.db.models import (
    Entity, User, Counterparty, Deal, AuditEvent, RfqDesk, RfqDeskMembership,
    Client, Person, Affiliation, RfqRequest, RfqBookingEvidence, RfqProvider, Alert,
)
from backend.app.db.trading_models import TradingRelationship, TradingExecution
from backend.app.hybrid.business import HybridBootstrap
from backend.tests.test_rfq import _rfq_params


@pytest.fixture(params=[False, True], ids=["standalone", "organization"])
def access_case(request, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _record):
        conn.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([Entity(id=1, name="Client organization"), Entity(id=2, name="Other organization")])
    session.commit()
    roles = {"front": "user", "colleague": "user", "ops": "ops_maker", "checker": "checker",
             "superuser": "organization_admin", "admin": "admin", "outsider": "user", "foreign": "user"}
    users = {name: User(username=name, email=f"{name}@example.test", role=role, password_hash="x",
                        entity_id=2 if name == "foreign" else 1) for name, role in roles.items()}
    session.add_all(users.values()); session.commit()
    if request.param:
        config = SimpleNamespace(kind="organization", installation_id=uuid4(), organization_id=uuid4())
        session.add(HybridBootstrap(installation_id=str(config.installation_id),
            organization_id=str(config.organization_id), entity_id=1, baseline_json="{}")); session.commit()
        monkeypatch.setattr(auth, "current_config", lambda: config)
        monkeypatch.setattr("backend.app.hybrid.config.current_config", lambda: config)
    session.add_all([RfqDesk(id=11, entity_id=1, name="Sales"), RfqDesk(id=12, entity_id=1, name="Restricted")])
    session.commit()
    for name, rights in {"front": ["read", "prepare", "price", "select", "organize", "book"],
                         "colleague": ["read", "prepare", "price"], "ops": ["read", "book"],
                         "checker": ["read"], "superuser": ["read", "prepare", "price", "book"]}.items():
        session.add(RfqDeskMembership(desk_id=11, user_id=users[name].id, rights_json=json.dumps(rights)))
    session.add(Counterparty(id=1, name="BNP Paribas")); session.commit()
    session.add(RfqProvider(label="BNP Paribas", counterparty_id=1)); session.commit()
    monkeypatch.setattr(inlife, "load_hist_prices", lambda tickers, start, end:
        {"dates": [date.today().isoformat()], "prices": {ticker: [100.0] for ticker in tickers}})
    app = FastAPI()
    for module in [auth, trading, rfq, products, pricing, inlife, product_optimizer, simulation,
                   scenarios, compute, deals, alerts, client_intelligence, opportunities,
                   documents, portfolios, amc_studies, valuation_notes]:
        app.include_router(module.router)
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    def login(name):
        user = users[name]
        client.headers["Authorization"] = "Bearer " + auth._make_token(user.id, user.role, user.entity_id)
        return client
    yield session, users, login, request.param
    client.close(); session.close(); engine.dispose()


def _deal(session, user, **changes):
    row = Deal(reference=f"C01-{uuid4().hex[:12]}", entity_id=user.entity_id, user_id=user.id,
        contrepartie="BNP Paribas", nominal=1_000_000, fair_value=99, price_traded=98,
        trade_date=date.today().isoformat(), strike_date=date.today().isoformat(),
        value_date=date.today().isoformat(), maturity_date=(date.today()+timedelta(days=365)).isoformat(),
        payment_date=(date.today()+timedelta(days=370)).isoformat(), T=1,
        underlyings_json='[{"name":"UL1","ticker":"SECRET_TICKER","ccy":"EUR"}]', **changes)
    session.add(row); session.commit(); return row


def test_agreement_permission_matrix_and_audited_denials(access_case):
    session, users, login, managed = access_case
    body = dict(counterparty_id=1, reference="C01-LIMITS", effective_date=date.today().isoformat())
    for name in ["front", "checker", "ops"]:
        response = login(name).post("/api/trading/relationships", json=body)
        assert response.status_code == 403, response.text
    assert not session.exec(select(TradingRelationship)).all()
    accepted = login("superuser").post("/api/trading/relationships", json=body)
    assert accepted.status_code == 201, accepted.text
    row = accepted.json()
    for name in ["front", "checker", "ops"]:
        response = login(name).put(f"/api/trading/relationships/{row['id']}",
            json={**body, "expected_version": 1, "status": "SUSPENDED", "gross_notional_limit": 1})
        assert response.status_code == 403
    session.expire_all()
    assert session.get(TradingRelationship, row["id"]).version == 1
    rejected = session.exec(select(AuditEvent).where(AuditEvent.result == "REJECTED")).all()
    assert len(rejected) == 6
    response = login("admin").post("/api/trading/relationships", json={**body, "reference": "C01-TECH-ADMIN"})
    assert response.status_code == (401 if managed else 201)


def test_settlement_is_operations_only_idempotent_and_dates_are_distinct(access_case):
    session, users, login, _ = access_case
    d = _deal(session, users["front"])
    relation = TradingRelationship(entity_id=1, counterparty_id=1, reference="C01", terms_json="{}", updated_by=users["superuser"].id)
    session.add(relation); session.commit()
    row = TradingExecution(entity_id=1, user_id=users["front"].id, deal_id=d.id, relationship_id=relation.id,
        trade_reference="C01-TRADE", request_hash="x", issuer="BNP", our_side="BUY", instrument_reference="NOTE-1")
    session.add(row); session.commit()
    path = f"/api/trading/executions/{row.id}/settle"
    for name in ["front", "checker"]:
        assert login(name).post(path, json={"reference": "CASH-123"}).status_code == 403
    assert session.get(TradingExecution, row.id).settlement_status == "PENDING"
    accepted = login("ops").post(path, json={"reference": "CASH-123"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["settled_at"] and accepted.json()["value_date"] == d.value_date
    assert login("ops").post(path, json={"reference": "CASH-123"}).json()["settled_at"] == accepted.json()["settled_at"]
    assert login("ops").post(path, json={"reference": "DIFFERENT"}).status_code == 409
    assert len(session.exec(select(AuditEvent).where(AuditEvent.action == "NOTE_SETTLEMENT_RECORDED")).all()) == 1


@pytest.mark.parametrize("path", ["/api/price", "/api/price/in-life", "/api/price/implied-funding",
    "/api/solve", "/api/grid", "/api/scenarios", "/api/product-optimizer/run", "/api/compute/batches"])
def test_secondary_profiles_cannot_compute_through_alternate_endpoints(access_case, path):
    session, users, login, _ = access_case
    for name in ["ops", "checker"]:
        response = login(name).post(path, json={})
        assert response.status_code == 403, (path, response.text)
    assert login("front").post(path, json={}).status_code == 422


def _rfq_with_evidence(session, user):
    from backend.app.core.calendars import adjust
    maturity = adjust(date.today() + timedelta(days=1096), "EUR")
    params = _rfq_params(r=0.02, N=2000, T=round((maturity-date.today()).days / 365.25, 6),
        maturity_date=maturity.isoformat(), corr_matrix=[[1.0]],
        constats={"OBS": {"start_date": date.today().isoformat(), "end_date": maturity.isoformat(),
                          "roll_date": maturity.isoformat(), "frequency": "1Y", "stub": "short_last"}},
        underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "sigma": 0.2, "q": 0.0, "spot0": 100.0}])
    created = rfq.create_rfq(rfq.RfqCreate(pilot_desk_id=11, kind="to_trade", name="C01 handoff",
        transaction_format="EMTN", instrument_family="Note",
        script_snapshot="CONSTAT() OBS\nAT OBS:\n  PAY 0\nAT MATURITY:\n  PAY 1", params=params), user, session)
    composed = rfq.compose_rfq_pricing_input(created["id"], rfq.RfqPricingInput(expected_terms_version=1), user, session)
    calculated = inlife.price_in_life(inlife.InLifePricingRequest(**composed["pricing_input"]), user)
    receipt = calculated["pricing_receipt"]
    rfq.update_rfq(created["id"], rfq.RfqUpdate(model_price=receipt["price_pct"], pricing_receipt=receipt,
        expected_model_input_hash=composed["input_hash"]), user, session)
    from backend.app.services.product_repository import load_product
    product = load_product(session, created["product_id"])
    products.update_product(product.product_id, products.ProductUpdate(expected_revision=product.revision,
        listed=True, reason="Dossier partagé en bibliothèque"), user, session)
    quote = rfq.add_quote(created["id"], rfq.QuoteCreate(provider="BNP Paribas"), user, session)
    rfq.update_quote(created["id"], quote["id"], rfq.QuoteUpdate(price=98, status="recu", firmness="FIRM",
        valid_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()), user, session)
    rfq.update_rfq(created["id"], rfq.RfqUpdate(selected_quote_id=quote["id"]), user, session)
    return created


def test_front_colleague_operations_controller_handoff_and_revocation(access_case):
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    product_id, rfq_id = created["product_id"], created["id"]
    resumed = login("colleague").get(f"/api/products/{product_id}")
    assert resumed.status_code == 200
    assert login("colleague").patch(f"/api/products/{product_id}", json={
        "expected_revision": resumed.json()["revision"], "name": "Reprise du dossier",
        "reason": "Relais du collègue habilité"}).status_code == 200
    assert product_id in [p["id"] for p in login("superuser").get("/api/products").json()]
    for name, status in [("ops", 403), ("checker", 403), ("outsider", 404)]:
        assert login(name).get(f"/api/products/{product_id}").status_code == status
    review = login("ops").get(f"/api/rfq/{rfq_id}/booking-review")
    assert review.status_code == 200, review.text
    for secret in ['"sigma"', '"corr_matrix"', '"pricing_input"', '"market_snapshot"', '"server_signature"']:
        assert secret not in review.text
    assert login("checker").get(f"/api/rfq/{rfq_id}/booking-review").status_code == 403
    history = login("ops").get("/api/rfq/history").json()
    assert history == []
    command = {"review_token": review.json()["review_token"]}
    booked = login("ops").post(f"/api/rfq/{rfq_id}/book", json=command)
    assert booked.status_code == 201, booked.text
    deal_id = booked.json()["id"]
    for name in ["front", "colleague", "checker"]:
        assert login(name).get(f"/api/deals/{deal_id}").status_code == 200
        assert deal_id in [d["id"] for d in login(name).get("/api/deals").json()]
    assert login("outsider").get(f"/api/deals/{deal_id}").status_code == 404
    assert login("ops").post(f"/api/rfq/{rfq_id}/book", json=command).status_code == 409
    assert len(session.exec(select(Deal)).all()) == 1
    grant = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == users["colleague"].id)).one()
    grant.active = False; session.add(grant); session.commit()
    assert login("colleague").get(f"/api/products/{product_id}").status_code == 404
    assert login("colleague").get(f"/api/deals/{deal_id}").status_code == 404


def test_manual_refresh_only_processes_the_shared_visible_book(access_case, monkeypatch):
    from backend.app.services import lifecycle_alerts
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    shared = _deal(session, users["front"], rfq_id=created["id"])
    _deal(session, users["foreign"])
    processed = []
    monkeypatch.setattr(lifecycle_alerts, "_refresh_deal_handler", lambda d, s: processed.append(d.id) or {})
    monkeypatch.setattr(lifecycle_alerts, "_watchlist_handler", lambda *args: {"barriers": []})
    response = login("ops").post("/api/alerts/refresh-book")
    assert response.status_code == 200 and response.json()["deals"] == 1
    assert processed == [shared.id]
    processed.clear()
    assert login("outsider").post("/api/alerts/refresh-book").json()["deals"] == 0
    assert processed == []


def test_booking_review_refuses_stale_or_missing_evidence(access_case):
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    path = f"/api/rfq/{created['id']}"
    review = login("ops").get(path + "/booking-review").json()
    source = session.get(RfqRequest, created["id"])
    saved_price = source.model_price
    saved_evidence = session.get(RfqBookingEvidence, source.id).receipt_json
    altered = json.loads(saved_evidence)
    altered["price_pct"] += 1
    refused = login("front").patch(path, json={"model_price": altered["price_pct"], "pricing_receipt": altered})
    assert refused.status_code == 422
    session.expire_all()
    assert session.get(RfqRequest, source.id).model_price == saved_price
    assert session.get(RfqBookingEvidence, source.id).receipt_json == saved_evidence
    source.name = "Changed after review"; session.add(source); session.commit()
    assert login("ops").post(path + "/book", json={"review_token": review["review_token"]}).status_code == 409
    session.delete(session.get(RfqBookingEvidence, source.id)); session.commit()
    assert login("ops").get(path + "/booking-review").status_code == 409
    assert session.exec(select(Deal)).all() == []


def test_historical_rfq_without_desk_keeps_personal_access(access_case):
    from backend.app.db.models import RfqOwnership
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    session.delete(session.get(RfqOwnership, created["id"])); session.commit()
    d = _deal(session, users["front"], rfq_id=created["id"])
    assert login("front").get(f"/api/products/{created['product_id']}").status_code == 200
    assert login("colleague").get(f"/api/products/{created['product_id']}").status_code == 404
    assert login("colleague").get(f"/api/rfq/{created['id']}").status_code == 404
    assert login("colleague").get(f"/api/deals/{d.id}").status_code == 404
    assert login("ops").get(f"/api/deals/{d.id}").status_code == 200


def test_operational_valuation_keeps_contract_scope(access_case, monkeypatch):
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    d = _deal(session, users["front"], rfq_id=created["id"])
    # Isolate authorization from the numerical engine, covered by its own tests.
    monkeypatch.setattr(deals, "_mtm_core", lambda *args: ({"price": .95}, None))
    assert login("ops").post(f"/api/deals/{d.id}/mtm").status_code == 200
    assert login("checker").post(f"/api/deals/{d.id}/mtm").status_code == 200
    assert login("outsider").post(f"/api/deals/{d.id}/mtm").status_code == 404


def test_shared_collections_and_documents_keep_contract_authorization(access_case, tmp_path, monkeypatch):
    from backend.app.db.models import Document, ValuationNote, Portfolio, AmcStudy
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    review = login("ops").get(f"/api/rfq/{created['id']}/booking-review").json()
    booked = login("ops").post(f"/api/rfq/{created['id']}/book", json={"review_token": review["review_token"]}).json()
    deal_id = booked["id"]
    monkeypatch.setattr(documents, "_DOCS_DIR", tmp_path)
    (tmp_path / "contract.pdf").write_bytes(b"contract")
    doc = Document(user_id=users["front"].id, product_id=created["product_id"], deal_id=deal_id,
                   title="Contract", doc_type="termsheet_final", filename="contract.pdf", file_path="contract.pdf")
    note = ValuationNote(user_id=users["front"].id, deal_id=deal_id, request_key=str(uuid4()),
                         title="Explain", kind="MTM", evidence_json="{}", draft_json="{}")
    session.add_all([doc, note]); session.commit()
    portfolio = login("front").post("/api/portfolios", json={"name": "Shared EUR book"}).json()
    assignment = login("ops").put(f"/api/deals/{deal_id}/portfolios", json={"portfolio_ids": [portfolio["id"]]})
    assert assignment.status_code == 200, assignment.text
    study = login("front").post("/api/amc/studies", json={"isin": "C01", "label": "Shared study", "result": {}}).json()
    for name in ["colleague", "ops", "checker"]:
        http = login(name)
        assert doc.id in [row["id"] for row in http.get("/api/documents").json()]
        assert http.get(f"/api/documents/{doc.id}/download").content == b"contract"
        assert note.id in [row["id"] for row in http.get("/api/valuation-notes").json()]
        assert http.get(f"/api/valuation-notes/{note.id}").status_code == 200
        assert next(row for row in http.get("/api/portfolios").json() if row["id"] == portfolio["id"])["deal_count"] == 1
        assert http.get(f"/api/amc/studies/{study['id']}").status_code == 200
    outsider = login("outsider")
    assert outsider.get("/api/documents").json() == []
    assert outsider.get(f"/api/documents/{doc.id}/download").status_code == 404
    assert outsider.get("/api/valuation-notes").json() == []
    assert outsider.get(f"/api/valuation-notes/{note.id}").status_code == 404
    assert next(row for row in outsider.get("/api/portfolios").json() if row["id"] == portfolio["id"])["deal_count"] == 0
    # Collection ownership is frozen even if the author later leaves the organization.
    author = users["front"]; author.entity_id = 2; session.add(author); session.commit()
    assert login("colleague").get(f"/api/amc/studies/{study['id']}").status_code == 200
    assert session.get(AmcStudy, study["id"]).entity_id == session.get(Portfolio, portfolio["id"]).entity_id == 1


def test_crm_details_aggregates_signals_and_alerts_follow_deal_scope(access_case):
    from backend.app.db.models import Opportunity
    session, users, login, _ = access_case
    created = _rfq_with_evidence(session, users["front"])
    client = Client(name="Commercial client", entity_id=1, data_origin="native")
    person = Person(first_name="C01", last_name="Contact", entity_id=1)
    session.add_all([client, person]); session.commit()
    affiliation = Affiliation(person_id=person.id, client_id=client.id)
    session.add(affiliation); session.commit()
    opportunity = Opportunity(reference="C01-OPPORTUNITY", entity_id=1,
        owner_user_id=users["front"].id, client_id=client.id, title="Shared commercial need", data_origin="native")
    session.add(opportunity); session.commit()
    source = session.get(RfqRequest, created["id"])
    source.client_id = client.id
    source.opportunity_id = opportunity.id
    session.add(source); session.commit()
    d = _deal(session, users["ops"], rfq_id=created["id"], client_id=client.id,
              primary_affiliation_id=affiliation.id, opportunity_id=opportunity.id)
    session.add(Alert(user_id=users["ops"].id, deal_id=d.id, deal_reference=d.reference, kind="barrier", message="Contract event")); session.commit()
    for name, visible in [("front", True), ("checker", True), ("outsider", False)]:
        http = login(name)
        assert http.get(f"/api/deals/{d.id}").status_code == (200 if visible else 404)
        data = http.get(f"/api/client-intelligence/clients/{client.id}")
        assert data.status_code == 200, data.text
        assert (d.reference in data.text) is visible
        assert (created["reference"] in data.text) is visible
        if not visible:
            assert data.json()["transactions"] == []
        linked = http.get(f"/api/opportunities/{opportunity.id}").json()
        assert (d.id in [row["id"] for row in linked["deals"]]) is visible
        assert (source.id in [row["id"] for row in linked["rfqs"]]) is visible
        for path in [f"/api/client-intelligence/persons/{person.id}", f"/api/client-intelligence/affiliations/{affiliation.id}",
                     "/api/client-intelligence/analytics", "/api/client-intelligence/signals?mine_only=false",
                     "/api/client-intelligence/overview"]:
            response = http.get(path)
            assert response.status_code == 200, response.text
            if not visible:
                assert d.reference not in response.text and "SECRET_TICKER" not in response.text
        alert_data = http.get("/api/alerts").json()
        assert (d.id in [a["deal_id"] for a in alert_data["alerts"]]) is visible
    # Reading a collective alert remains a personal acknowledgement.
    alert_id = login("front").get("/api/alerts").json()["alerts"][0]["id"]
    assert login("front").post(f"/api/alerts/{alert_id}/read").json()["read"] is True
    assert login("front").get("/api/alerts?unread_only=true").json()["unread"] == 0
    assert login("checker").get("/api/alerts?unread_only=true").json()["unread"] == 1
    assert login("ops").get("/api/alerts?unread_only=true").json()["unread"] == 1


def test_scope_migration_freezes_owner_and_keeps_unknown_settlement_dates():
    from backend.app.db.organization_scope_migrations import migrate_organization_scopes
    from backend.app.db.trading_migrations import migrate_settlement_evidence
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for statement in ["CREATE TABLE entities(id INTEGER PRIMARY KEY)", "INSERT INTO entities VALUES(1),(2)",
            "CREATE TABLE users(id INTEGER PRIMARY KEY, entity_id INTEGER)", "INSERT INTO users VALUES(1,1)",
            "CREATE TABLE portfolios(id INTEGER PRIMARY KEY, user_id INTEGER)", "INSERT INTO portfolios VALUES(1,1)",
            "CREATE TABLE trading_executions(id INTEGER PRIMARY KEY)", "INSERT INTO trading_executions VALUES(1)"]:
            conn.execute(text(statement))
        migrate_organization_scopes(conn); migrate_settlement_evidence(conn)
        conn.execute(text("UPDATE users SET entity_id=2 WHERE id=1"))
        migrate_organization_scopes(conn); migrate_settlement_evidence(conn)
        assert conn.execute(text("SELECT entity_id FROM portfolios")).scalar() == 1
        assert conn.execute(text("SELECT settled_at FROM trading_executions")).scalar() is None
