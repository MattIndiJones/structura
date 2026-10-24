"""Managed accounts, desk permissions and installation-bound authentication."""
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt
import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.hybrid.business import HybridBootstrap, seed
from backend.app.hybrid.config import credentials, signing_secret
from backend.app.hybrid.deployment import prepare
from backend.app.core.access import has_business_role
from backend.app.db.models import Entity, User, RfqDesk, RfqDeskMembership, RfqBankPublicationPolicy, Deal
from backend.app.api import auth, admin, agent_workshop, rfq_desks
from backend.app.db.database import get_session


@pytest.fixture
def managed(tmp_path, monkeypatch):
    configs = prepare(tmp_path / "hybrid")
    config = configs[1]
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(config.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(config.data_dir))
    monkeypatch.setattr(auth, "_SECRET", signing_secret(config))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def integrity(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    seed(engine, config)
    app = FastAPI()
    for router in (auth.router, admin.router, rfq_desks.router, agent_workshop.router, agent_workshop.admin_router):
        app.include_router(router)
    def sessions():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield config, engine, client, configs
    engine.dispose()


def login(client, config, username):
    response = client.post("/api/auth/login", data={"username": username, "password": credentials(config)[username]})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_bootstrap_is_idempotent_and_only_seeds_configuration(managed):
    config, engine, _, _ = managed
    with Session(engine) as session:
        hashes = {u.username: u.password_hash for u in session.exec(select(User)).all()}
    report = seed(engine, config)
    assert report["accounts"] == 4 and report["desks"] == 2 and report["configuration_drift"] == []
    with Session(engine) as session:
        assert hashes == {u.username: u.password_hash for u in session.exec(select(User)).all()}
        assert len(session.exec(select(Entity)).all()) == 1
        assert len(session.exec(select(HybridBootstrap)).all()) == 1
        assert not session.exec(select(Deal)).all()
        assert {u.role for u in session.exec(select(User)).all()} == {"organization_admin", "user", "ops_maker", "checker"}
        policy = session.exec(select(RfqBankPublicationPolicy)).one()
        assert not policy.second_validation_required and policy.max_calculation_age_minutes == 60


def test_managed_login_never_offers_simulation_registration(managed, monkeypatch):
    _, _, client, _ = managed
    monkeypatch.setenv("STRUCTURA_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "simulation")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    assert client.get("/api/auth/options").json() == {
        "registration_enabled": False, "admin_workbench": False,
        "development_admin_enabled": False, "platform_url": None,
    }


def test_reinitialization_observes_revocation_without_restoring_it(managed):
    config, engine, client, _ = managed
    headers = login(client, config, "front")
    with Session(engine) as session:
        front = session.exec(select(User).where(User.username == "front")).one()
        front.is_active = False
        session.add(front)
        membership = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == front.id)).first()
        membership.active = False
        session.add(membership)
        session.commit()
    report = seed(engine, config)
    assert "account.front" in report["configuration_drift"]
    assert any(value.startswith("membership.") for value in report["configuration_drift"])
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/login", data={"username": "front", "password": credentials(config)["front"]}).status_code == 400


def test_initialization_refuses_preexisting_data_and_wrong_identity(managed):
    config, engine, _, configs = managed
    with pytest.raises(RuntimeError, match="autre installation"):
        seed(engine, configs[2])
    with Session(engine) as session:
        session.delete(session.get(HybridBootstrap, 1))
        session.commit()
    with pytest.raises(RuntimeError, match="préexistante"):
        seed(engine, config)


@pytest.mark.parametrize("username,profile_name,admin_status", [
    ("superuser", "superuser", 200), ("front", "front", 403),
    ("operations", "operations", 403), ("controller", "controller", 403)])
def test_profiles_and_local_admin_are_explicit(managed, username, profile_name, admin_status):
    config, _, client, _ = managed
    headers = login(client, config, username)
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["profile"] == profile_name
    assert me["installation"]["installation_id"] == str(config.installation_id)
    assert me["developer_access"] is False
    assert client.get("/api/admin/users", headers=headers).status_code == admin_status
    for prefix in ("/api/agent-workshop", "/api/admin/agent-workshop"):
        assert client.get(prefix, headers=headers).status_code == 403
        assert client.post(prefix, headers=headers, json={"months": 1}).status_code == 403
    assert client.get("/api/admin/browse", headers=headers).status_code in {403, 404}


def test_tokens_reject_foreign_audience_issuer_and_organization(managed):
    config, _, client, configs = managed
    headers = login(client, config, "superuser")
    token = headers["Authorization"].split()[1]
    payload = jwt.decode(token, signing_secret(config), algorithms=["HS256"], audience=str(config.installation_id))
    for field in ("aud", "iss", "organization_id"):
        modified = {**payload, field: str(configs[2].installation_id)}
        wrong = jwt.encode(modified, signing_secret(config), algorithm="HS256")
        assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + wrong}).status_code == 401
    for field in ("aud", "iss", "exp"):
        missing = dict(payload)
        missing.pop(field)
        wrong = jwt.encode(missing, signing_secret(config), algorithm="HS256")
        assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + wrong}).status_code == 401


def test_local_admin_cannot_grant_technical_role_or_reassign_organization(managed):
    config, engine, client, _ = managed
    headers = login(client, config, "superuser")
    with Session(engine) as session:
        front = session.exec(select(User).where(User.username == "front")).one()
        entity_id = front.entity_id
    assert client.patch(f"/api/admin/users/{front.id}", headers=headers, json={"role": "admin"}).status_code == 403
    assert client.patch(f"/api/admin/users/{front.id}", headers=headers, json={"entity_id": entity_id + 1}).status_code == 403
    assert client.post("/api/auth/register", json={"username": "unexpected", "email": "x@example.test", "password": "temporary-password"}).status_code == 403
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 4


def test_desk_grants_do_not_allow_self_elevation(managed):
    config, engine, client, _ = managed
    headers = login(client, config, "superuser")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "superuser")).one()
        desk = session.exec(select(RfqDesk).where(RfqDesk.name == "Pricing")).one()
    assert client.put(f"/api/rfq-desks/admin/{desk.id}/members/{user.id}", headers=headers,
                      json={"user_id": user.id, "rights": ["read"]}).status_code == 403


def test_secondary_profiles_cannot_price_or_book_by_calling_functions(managed):
    from backend.app.api.deals import _book_deal
    config, engine, _, _ = managed
    with Session(engine) as session:
        users = {u.username: u for u in session.exec(select(User)).all()}
        for name in ("front", "controller"):
            with pytest.raises(HTTPException) as error:
                _book_deal(None, users[name], session)
            assert error.value.status_code == 403
        for name in ("operations", "controller"):
            with pytest.raises(HTTPException) as error:
                auth.get_current_pricer(users[name])
            assert error.value.status_code == 403
        assert auth.get_current_pricer(users["superuser"]) == users["superuser"]
        assert has_business_role(users["superuser"], {"ops_maker"})
        assert has_business_role(users["superuser"], {"checker"})


def test_distributor_seed_has_sales_desk_and_no_banking_policy(tmp_path):
    config = prepare(tmp_path / "hybrid")[5]
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    assert seed(engine, config)["accounts"] == 4
    with Session(engine) as session:
        assert {d.name for d in session.exec(select(RfqDesk)).all()} == {"Sales", "Opérations"}
        assert not session.exec(select(RfqBankPublicationPolicy)).all()
    engine.dispose()


def test_interrupted_transaction_can_be_initialized_without_duplicate_accounts(tmp_path, monkeypatch):
    from backend.app.hybrid import business
    config = prepare(tmp_path / "hybrid")[1]
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    original = business.record_audit_event
    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted bootstrap")
    monkeypatch.setattr(business, "record_audit_event", interrupted)
    with pytest.raises(RuntimeError, match="interrupted bootstrap"):
        seed(engine, config)
    with Session(engine) as session:
        assert not session.exec(select(User)).all()
        assert not session.exec(select(Entity)).all()
    monkeypatch.setattr(business, "record_audit_event", original)
    assert seed(engine, config)["accounts"] == 4
    assert seed(engine, config)["configuration_drift"] == []
    engine.dispose()


def test_managed_studies_cannot_read_another_installation(managed):
    from backend.app.api.amc_access import study_folder
    config, engine, _, configs = managed
    with Session(engine) as session:
        superuser = session.exec(select(User).where(User.username == "superuser")).one()
        assert study_folder(config.data_dir / "studies", superuser) == str(config.data_dir / "studies")
        with pytest.raises(HTTPException) as error:
            study_folder(configs[2].data_dir / "studies", superuser)
        assert error.value.status_code == 403


def test_foreign_installation_is_refused_before_migration(managed, monkeypatch):
    from backend.app.db import database
    config, engine, _, configs = managed
    with Session(engine) as session:
        marker = session.get(HybridBootstrap, 1)
        marker.installation_id = str(configs[2].installation_id)
        session.add(marker)
        session.commit()
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_DB_PATH", config.data_dir / "structura.db")
    def unexpected_migration():
        pytest.fail("Foreign database must never reach migration")
    monkeypatch.setattr(database, "_migrate", unexpected_migration)
    with pytest.raises(RuntimeError, match="autre installation"):
        database.init_db()


def test_preflight_allows_empty_interrupted_schema_but_not_private_rows(tmp_path):
    from backend.app.hybrid.business import preflight
    config = prepare(tmp_path / "hybrid")[1]
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    preflight(engine, config)
    with Session(engine) as session:
        session.add(Entity(name="Existing private organization"))
        session.commit()
    with pytest.raises(RuntimeError, match="préexistante"):
        preflight(engine, config)
    engine.dispose()


def test_managed_preflight_rejects_admin_identity_with_valid_business_bootstrap(managed):
    from backend.app.hybrid.admin_workbench import AdminWorkbenchIdentity
    from backend.app.hybrid.business import preflight
    config, engine, _, _ = managed
    with Session(engine) as session:
        entity = session.exec(select(Entity)).one()
        session.add(AdminWorkbenchIdentity(installation_id=str(config.installation_id), entity_id=entity.id))
        session.commit()
    with pytest.raises(RuntimeError, match="Identités métier et Admin incompatibles"):
        preflight(engine, config)


def test_managed_installation_reinitializes_in_a_fresh_process(tmp_path):
    import sqlite3
    from backend.app.hybrid.deployment import initialize
    config = prepare(tmp_path / "restart")[1]
    assert initialize(config)["initialized"]
    def identity_rows():
        with sqlite3.connect(f"{(config.data_dir / 'structura.db').as_uri()}?mode=ro", uri=True) as connection:
            return {
                "users": connection.execute("SELECT id, username, password_hash FROM users ORDER BY id").fetchall(),
                "identity": connection.execute("SELECT * FROM hybrid_bootstrap").fetchall(),
                "admin_identity": connection.execute("SELECT * FROM admin_workbench_identity").fetchall(),
            }
    before = identity_rows()
    assert len(before["users"]) == 4 and not before["admin_identity"]
    assert initialize(config)["initialized"]
    assert identity_rows() == before
