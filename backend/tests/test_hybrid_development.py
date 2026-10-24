"""Development tickets are scoped, short lived, audited and single use."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt
from sqlmodel import Session, select

from backend.tests.test_hybrid_bootstrap import managed
from backend.app.hybrid.development import issue
from backend.app.hybrid.deployment import prepare
from backend.app.hybrid.platform import create_app
from backend.app.db.models import AuditEvent, User

HEADERS = {"X-Structura-Development":"1"}


def test_development_access_is_disabled_by_default(tmp_path, monkeypatch):
    platform = prepare(tmp_path / "hybrid")[0]
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(platform.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(platform.data_dir))
    monkeypatch.delenv("STRUCTURA_DEVELOPER_ACCESS", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/api/platform/development/access").json() == {"enabled":False,"installations":[]}
        assert client.post("/api/platform/development/session", json={"installation_id":str(platform.installation_id),"username":"admin"}, headers=HEADERS).status_code == 404


def test_central_catalog_and_grants_have_no_private_data(tmp_path, monkeypatch):
    configs = prepare(tmp_path / "hybrid")
    platform = configs[0]
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(platform.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(platform.data_dir))
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "1")
    with TestClient(create_app()) as client:
        catalog = client.get("/api/platform/development/access").json()
        assert len(catalog["installations"]) == 7
        assert "password" not in json.dumps(catalog) and "data_dir" not in json.dumps(catalog)
        body = {"installation_id":str(configs[1].installation_id),"username":"front"}
        assert client.post("/api/platform/development/session",json=body).status_code == 403
        assert client.post("/api/platform/development/session",json=body,headers={**HEADERS,"Origin":"https://evil.test"}).status_code == 403
        response = client.post("/api/platform/development/session",json=body,headers=HEADERS)
        assert response.status_code == 200 and "ticket" in response.json() and "access_token" not in response.json()
        # localhost -> 127.0.0.1 is cross-site to the browser, but these exact
        # development origins are explicitly allowed (no wildcard).
        assert client.post("/api/platform/development/session",json=body,
            headers={**HEADERS,"Origin":"http://localhost:5173","Sec-Fetch-Site":"cross-site"}).status_code == 200
        assert client.post("/api/platform/development/session",json={**body,"username":"admin"},headers=HEADERS).status_code == 403
        assert client.get("/api/deals").status_code == 404


def test_redemption_is_local_audited_and_replay_safe(managed, monkeypatch):
    config, engine, client, configs = managed
    platform = configs[0]
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "1")
    origin = {"kind":"CENTRAL_ADMIN","platform_installation_id":str(platform.installation_id),"actor_id":1}
    ticket, ticket_id = issue(platform,str(config.installation_id),str(config.organization_id),"front",origin)
    result = client.post("/api/auth/development-session",json={"ticket":ticket},headers=HEADERS)
    assert result.status_code == 200
    headers = {"Authorization":"Bearer " + result.json()["access_token"]}
    me = client.get("/api/auth/me",headers=headers).json()
    assert me["username"] == "front" and me["role"] == "user" and me["developer_origin"] == origin
    assert client.post("/api/auth/development-session",json={"ticket":ticket},headers=HEADERS).status_code == 409
    with Session(engine) as session:
        events = session.exec(select(AuditEvent).where(AuditEvent.action == "DEVELOPMENT_LOGIN")).all()
        assert len(events) == 1 and events[0].correlation_id == ticket_id
        assert json.loads(events[0].metadata_json)["developer_origin"] == origin
    assert client.get("/api/agent-workshop",headers=headers).status_code == 403


def test_grants_reject_wrong_scope_expiry_and_disabled_account(managed, monkeypatch):
    config, engine, client, configs = managed
    platform = configs[0]
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS","1")
    other, _ = issue(platform,str(configs[2].installation_id),str(configs[2].organization_id),"front",{"kind":"DEVELOPMENT_PORTAL"})
    assert client.post("/api/auth/development-session",json={"ticket":other},headers=HEADERS).status_code == 401
    ticket, _ = issue(platform,str(config.installation_id),str(config.organization_id),"front",{"kind":"DEVELOPMENT_PORTAL"})
    payload = jwt.get_unverified_claims(ticket)
    payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = jwt.encode(payload,(platform.data_dir / ".developer_private.pem").read_text(),algorithm="RS256")
    assert client.post("/api/auth/development-session",json={"ticket":expired},headers=HEADERS).status_code == 401
    with Session(engine) as session:
        front = session.exec(select(User).where(User.username == "front")).one()
        front.is_active = False; session.add(front); session.commit()
    assert client.post("/api/auth/development-session",json={"ticket":ticket},headers=HEADERS).status_code == 403
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS","0")
    assert client.post("/api/auth/development-session",json={"ticket":ticket},headers=HEADERS).status_code == 404
