"""F01 registration acceptance with real sessions and isolated persistence."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import auth
from backend.app.db.database import get_session
from backend.app.db.models import Entity, User
from backend.tests.test_hybrid_bootstrap import managed


def _payload(password="Registration-2026"):
    return {"username": "registration-user", "email": "registration@example.test",
            "password": password, "entity_name": "Registration test organization"}


@pytest.fixture
def registration_case(monkeypatch):
    for name in ("STRUCTURA_INSTALLATION_CONFIG", "STRUCTURA_ALLOW_REGISTRATION",
                 "STRUCTURA_BOOTSTRAP_PROFILE", "STRUCTURA_WORKSHOP_CHILD"):
        monkeypatch.delenv(name, raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(auth.router)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            yield engine, client
    finally:
        engine.dispose()


@pytest.mark.parametrize("flag", [None, "0", "false", "enabled"],
                         ids=["absent", "zero", "false", "unrecognized"])
def test_disabled_registration_rejects_valid_payload_without_writes(registration_case, monkeypatch, flag):
    engine, client = registration_case
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    if flag is not None:
        monkeypatch.setenv("STRUCTURA_ALLOW_REGISTRATION", flag)
    assert client.get("/api/auth/options").json()["registration_enabled"] is False
    response = client.post("/api/auth/register", json=_payload())
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Inscription publique désactivée. Contactez un administrateur."
    with Session(engine) as session:
        assert session.exec(select(User)).all() == []
        assert session.exec(select(Entity)).all() == []


@pytest.mark.parametrize("flag", ["1", "true", "yes"])
def test_enabled_registration_persists_regular_user_and_issues_usable_session(registration_case, monkeypatch, flag):
    engine, client = registration_case
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    monkeypatch.setenv("STRUCTURA_ALLOW_REGISTRATION", flag)
    assert client.get("/api/auth/options").json()["registration_enabled"] is True
    body = _payload()
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    identity = client.get("/api/auth/me", headers=headers)
    assert identity.status_code == 200, identity.text
    assert identity.json()["role"] == "user"
    with Session(engine) as session:
        user = session.exec(select(User)).one()
        entity = session.exec(select(Entity)).one()
        assert user.username == body["username"] and user.email == body["email"]
        assert user.role == "user" and user.entity_id == entity.id == identity.json()["entity_id"]
        assert entity.name == body["entity_name"]
        assert user.password_hash != body["password"]
        assert user.is_active and not user.password_change_required
        assert session.exec(text("PRAGMA foreign_key_check")).all() == []
        version = user.auth_version
    claims = jwt.get_unverified_claims(token)
    assert claims["jti"] and claims["session_version"] == version
    login = client.post("/api/auth/login", data={"username": body["username"], "password": body["password"]})
    assert login.status_code == 200, login.text
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    fresh = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.post("/api/auth/register", json=body).status_code == 400
    assert client.post("/api/auth/register", json={**body, "username": "other-user"}).status_code == 400
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 1
        assert len(session.exec(select(Entity)).all()) == 1


@pytest.mark.parametrize("password,accepted", [
    pytest.param("password123", False, id="minimum-minus-one"),
    pytest.param("password1234", True, id="minimum"),
    pytest.param("x" * 72, True, id="ascii-limit"),
    pytest.param("x" * 73, False, id="ascii-over-limit"),
    pytest.param("é" * 36, True, id="utf8-limit"),
    pytest.param("é" * 37, False, id="utf8-over-limit"),
])
def test_registration_enforces_password_bounds_before_persistence(registration_case, monkeypatch, password, accepted):
    engine, client = registration_case
    monkeypatch.setenv("STRUCTURA_ALLOW_REGISTRATION", "1")
    body = _payload(password)
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == (201 if accepted else 422), response.text
    if accepted:
        login = client.post("/api/auth/login", data={"username": body["username"], "password": password})
        assert login.status_code == 200, login.text
    else:
        assert any(error["loc"] == ["body", "password"] for error in response.json()["detail"])
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == int(accepted)
        assert len(session.exec(select(Entity)).all()) == int(accepted)


def test_managed_registration_ignores_public_opt_in(managed, monkeypatch):
    _, engine, client, _ = managed
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    monkeypatch.setenv("STRUCTURA_ALLOW_REGISTRATION", "1")
    with Session(engine) as session:
        before_users = [user.model_dump() for user in session.exec(select(User).order_by(User.id))]
        before_entities = [entity.model_dump() for entity in session.exec(select(Entity).order_by(Entity.id))]
    assert client.get("/api/auth/options").json()["registration_enabled"] is False
    response = client.post("/api/auth/register", json=_payload())
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Admission locale par un administrateur de l'organisation requise."
    with Session(engine) as session:
        assert [user.model_dump() for user in session.exec(select(User).order_by(User.id))] == before_users
        assert [entity.model_dump() for entity in session.exec(select(Entity).order_by(Entity.id))] == before_entities
