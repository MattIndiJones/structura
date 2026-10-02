"""Production/UAT isolation and preflight using the same CCR calculation engine."""
import json
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api.auth import get_current_user
from backend.app.api.ccr import router
from backend.app.db.database import get_session
from backend.app.db.models import (Counterparty, Deal, DealEvent, Entity, User, UatGenerationBatch,
                                   ValuationRun, Portfolio, DealPortfolioMembership)
from backend.tests.product_helpers import attach_product_to_deal
from backend.app.db.ccr_models import CCRCreditLimit
from backend.app.core.ccr.contracts import CreditLimit


@pytest.fixture
def scope_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        entity = Entity(name="CCR test")
        other = Entity(name="Other")
        session.add_all([entity, other]); session.flush()
        user = User(username="risk", email="risk@test.invalid", password_hash="x", entity_id=entity.id)
        cpty = Counterparty(name="BNP synthetic")
        session.add_all([user, cpty]); session.flush()
        session.add(CCRCreditLimit(entity_id=entity.id, counterparty_id=cpty.id, updated_by=user.id,
            payload_json=CreditLimit(metric="gross_notional", amount=1_500_000, action="HARD_BLOCK",
                                     effective_date=date.today()).model_dump_json()))
        batches = [UatGenerationBatch(batch_key=f"batch-{i}", label=f"Lot {i}", created_by=user.id,
                    target_user_id=user.id, mode="BOOKED_ONLY", seed=i, requested_count=1) for i in (1, 2, 3)]
        session.add_all(batches); session.flush()
        today = date.today()
        deals = []
        for i, batch in enumerate([None, batches[0].id, batches[1].id, batches[2].id]):
            d = Deal(reference=f"SCOPE-{i}", user_id=user.id, entity_id=entity.id if i < 3 else other.id,
                counterparty_id=cpty.id, contrepartie=cpty.name, nominal=1_000_000, status="en_reglement",
                script_snapshot="AT MATURITY\n  PAY 1", product_type="Note", T=1,
                underlyings_json='[{"name":"Synthetic", "ticker":"S", "ccy":"EUR"}]',
                strike_date=str(today-timedelta(days=365)), maturity_date=str(today),
                payment_date=str(today+timedelta(days=90)), settlement_amount=1., uat_batch_id=batch)
            attach_product_to_deal(session, d)
            session.add(d); session.flush(); deals.append(d)
            session.add(ValuationRun(deal_id=d.id, user_id=user.id, context_hash=f"fixture-{i}",
                context_json=json.dumps({"settlement_claim": True, "fixed_price": 1.}),
                result_json=json.dumps({"valuation_date": str(today), "mtm": 1.})))
        portfolio = Portfolio(user_id=user.id, name="Mixed portfolio")
        session.add(portfolio); session.flush()
        for d in deals[:2]:
            session.add(DealPortfolioMembership(deal_id=d.id, portfolio_id=portfolio.id))
        session.commit()
        app = FastAPI(); app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = lambda: session
        yield TestClient(app), cpty.id, batches, deals, portfolio.id


def test_scopes_batch_portfolio_and_entity_are_intersected(scope_client):
    client, cpty, batches, deals, portfolio = scope_client
    from backend.app.api.deals import _deal_row
    reopened = _deal_row(deals[1])
    assert reopened['counterparty_id'] == cpty
    assert reopened['uat_batch_id'] == batches[0].id
    assert reopened['ccr_netting_set_id'] is None
    assert [d["id"] for d in client.get("/api/ccr/deals").json()] == [deals[0].id]
    assert {d["id"] for d in client.get("/api/ccr/deals?data_scope=UAT").json()} == {deals[1].id, deals[2].id}
    assert {b["id"] for b in client.get("/api/ccr/uat-batches").json()} == {batches[0].id, batches[1].id}
    body = dict(counterparty_id=cpty, data_scope="UAT", uat_batch_id=batches[0].id, portfolio_id=portfolio)
    diag = client.post("/api/ccr/diagnostic", json=body).json()
    assert diag["selected_count"] == 1
    assert diag["deals"][0]["deal_id"] == deals[1].id
    assert diag["excluded_other_scope_count"] == 1
    assert diag["common_valuation_dates"] == [str(date.today())]
    assert diag["missing_valuation_count"] == 0
    foreign = client.post("/api/ccr/calculate", json={**body, "deal_id": deals[3].id})
    assert foreign.status_code == 404
    assert client.post("/api/ccr/calculate", json={**body, "data_scope": "PRODUCTION"}).status_code == 422


def test_uat_uses_identical_engine_and_cannot_replace_production_monitor(scope_client):
    client, cpty, batches, _, _ = scope_client
    body = dict(counterparty_id=cpty, n_outer=32, n_inner=32, n_dates=3)
    production = client.post("/api/ccr/calculate", json=body)
    assert production.status_code == 200, production.text
    production = production.json()
    uat = client.post("/api/ccr/calculate", json={**body, "data_scope": "UAT"}).json()
    assert uat["is_test"] and uat["decision"]["simulation_only"]
    assert uat["methodology"] == production["methodology"] == "NESTED_MONTE_CARLO_GBM"
    assert uat["after"]["current_exposure"] == 2 * production["after"]["current_exposure"]
    assert uat["after"]["pfe95"] == 2 * production["after"]["pfe95"]
    assert production["decision"]["booking_allowed"]
    assert not uat["decision"]["booking_allowed"]
    assert client.get("/api/ccr/monitor").json()[0]["run_id"] == production["run_id"]
    assert client.get("/api/ccr/monitor?data_scope=UAT").json()[0]["run_id"] == uat["run_id"]
    saved = client.get(f"/api/ccr/runs/{uat['run_id']}").json()
    assert saved["inputs"]["request"]["data_scope"] == "UAT"
    assert client.post(f"/api/ccr/runs/{uat['run_id']}/replay").json()["identical"]
    limited = client.post("/api/ccr/calculate", json={**body, "data_scope": "UAT", "uat_batch_id": batches[0].id}).json()
    assert limited["after"]["profile"] == production["after"]["profile"]
    assert limited["limits"][0]["status"] == "OK"
    assert limited["decision"]["simulation_only"]
    assert client.get("/api/ccr/monitor?data_scope=UAT").json()[0]["run_id"] == uat["run_id"]


def test_empty_scope_and_missing_mtm_are_explained(scope_client):
    client, cpty, batches, _, _ = scope_client
    base = dict(counterparty_id=cpty, data_scope="UAT")
    empty = client.post("/api/ccr/calculate", json={**base, "uat_batch_id": batches[2].id})
    assert empty.status_code == 422
    assert "Aucun deal retenu" in empty.json()["detail"]
    previous = str(date.today()-timedelta(days=1))
    diagnostic = client.post("/api/ccr/diagnostic", json={**base, "as_of_date": previous}).json()
    assert diagnostic["selected_count"] == 2
    assert diagnostic["missing_valuation_count"] == 2
    assert diagnostic["deals"][0]["available_dates"] == [str(date.today())]
    assert diagnostic["deals"][0]["booking_url"].startswith("/booking?deal=")
    calculation = client.post("/api/ccr/calculate", json={**base, "as_of_date": previous}).json()
    assert calculation["status"] == "MISSING_DATA"
    assert calculation["after"]["pfe95"] is None
    assert client.post("/api/ccr/rfq/1/quotes/1/check", json=base).status_code == 422


def test_suggested_dates_account_for_historical_deal_scope(scope_client):
    client, cpty, batches, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    yesterday = str(date.today()-timedelta(days=1))
    # A now-called trade re-enters the historical scope but has no saved MtM.
    deals[2].status = "callé"
    session.add(deals[2])
    session.add(ValuationRun(deal_id=deals[1].id, user_id=deals[1].user_id, context_hash="past",
        result_json=json.dumps({"valuation_date": yesterday, "mtm": 1.}),
        context_json=json.dumps({"settlement_claim": True})))
    session.commit()
    diagnostic = client.post("/api/ccr/diagnostic", json={"counterparty_id":cpty, "data_scope":"UAT"}).json()
    assert diagnostic["selected_count"] == 1
    assert yesterday not in diagnostic["common_valuation_dates"]
    assert diagnostic["common_valuation_dates"] == [str(date.today())]


def test_historical_scope_excludes_paid_early_call_despite_original_payment_date(scope_client):
    client, cpty, batches, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    called = deals[2]
    called.status = "callé"
    called.settlement_amount = None
    call_date = date.today() - timedelta(days=3)
    session.add(called)
    session.add(DealEvent(deal_id=called.id, event_index=1,
                          event_date=str(call_date), status="callé"))
    session.commit()
    # Original contractual payment_date is still in the future, but there is
    # no outstanding claim after the call. Before the call it was live.
    recent = client.post("/api/ccr/diagnostic", json={"counterparty_id": cpty,
        "data_scope": "UAT", "as_of_date": str(date.today() - timedelta(days=1))}).json()
    assert recent["selected_count"] == 1
    older = client.post("/api/ccr/diagnostic", json={"counterparty_id": cpty,
        "data_scope": "UAT", "as_of_date": str(call_date - timedelta(days=1))}).json()
    assert older["selected_count"] == 2
