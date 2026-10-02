"""End-to-end HTTP contracts against an isolated database (no real app startup)."""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api.ccr import router
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import User, Entity, Counterparty, CCRExposureCalculation
from backend.tests.test_ccr import proposed


def test_http_configuration_calculation_replay_and_scope():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        entity = Entity(name="CCR QA")
        session.add(entity); session.flush()
        user = User(username="risk", email="risk@test.invalid", password_hash="test", role="admin", entity_id=entity.id)
        cpty = Counterparty(name="Synthetic counterparty")
        session.add_all([user, cpty]); session.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = lambda: session
        client = TestClient(app)
        assert client.get("/api/ccr/schemas").status_code == 200
        profile = client.post(f"/api/ccr/counterparties/{cpty.id}/profiles", json={"data": {
            "recovery": .4, "recovery_source": "USER_ASSUMPTION", "curve_source": "MANUAL",
            "pd_measure": "RISK_NEUTRAL", "pd_curve": [[2, .03]], "has_isda": False, "has_csa": False,
        }})
        assert profile.status_code == 200, profile.text
        assert profile.json()["data"]["recovery"] == .4
        trade = proposed()
        trade["pricing"]["strike_date"] = date.today().isoformat()
        response = client.post("/api/ccr/calculate", json={"counterparty_id": cpty.id, "n_outer": 32,
            "n_inner": 32, "n_dates": 2, "proposed": {k: trade[k] for k in ("pricing", "nominal", "currency", "sens", "product_type")}})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["after"]["cva"] > 0
        assert result["limits"][0]["status"] == "NO_LIMIT"
        assert client.post(f"/api/ccr/runs/{result['run_id']}/replay").json()["identical"]
        assert len(session.exec(select(CCRExposureCalculation)).all()) == 1
        user.entity_id = None
        assert client.get(f"/api/ccr/runs/{result['run_id']}").status_code == 409


def test_anonymous_ccr_is_not_accessible():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/api/ccr/counterparties").status_code == 401


def test_rfq_uses_explicit_provider_mapping_and_frozen_engine_units():
    import pytest
    from fastapi import HTTPException
    from backend.tests.test_rfq import _make_session, _new_rfq, _add_quote, USER
    from backend.app.api.ccr import rfq_check, rfq_credit_context
    from backend.app.core.ccr.contracts import CalculationRequest
    from backend.app.db.models import RfqProvider
    with _make_session() as session:
        rfq = _new_rfq(session)
        quote = _add_quote(session, rfq["id"], "RFQ LABEL")
        with pytest.raises(HTTPException) as exc:
            rfq_credit_context(rfq["id"], quote["id"], USER, session)
        assert exc.value.status_code == 422
        cpty = Counterparty(name="Separate legal name")
        session.add(cpty); session.flush()
        session.add(RfqProvider(label="RFQ LABEL", counterparty_id=cpty.id))
        session.commit()
        assert rfq_credit_context(rfq["id"], quote["id"], USER, session)["counterparty_id"] == cpty.id
        result = rfq_check(rfq["id"], quote["id"], CalculationRequest(mode="FAST"), USER, session)
        assert result["counterparty_id"] == cpty.id
        assert result["after"]["gross_notional"] == 1_000_000
        assert result["after"]["current_exposure"] > 0
