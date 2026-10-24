"""Simulation delegation has no business credentials and never opens manual books."""
from contextlib import closing
import json
import sqlite3

from fastapi.testclient import TestClient
from backend.app.hybrid.control_services import prepare_controls
from backend.app.hybrid.deployment import prepare
from backend.app.hybrid.simulation import create_app, request_signature
from backend.app.hybrid.platform import create_app as platform_app
from backend.app.hybrid.config import credentials
import pytest


@pytest.fixture
def controller(tmp_path, monkeypatch):
    platform = prepare(tmp_path / "manual",8240)[0]
    config = prepare_controls(platform)["simulation"]
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG",str(config.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR",str(config.data_dir))
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS","1")
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD","0")
    from backend.app.services.agent_workshop.store import store
    previous = store.root
    with TestClient(create_app(config)) as client:
        yield platform,config,client
    store.root = previous


def authorization(platform,config,method,path,body=b"",actor=1):
    return {"Authorization":"Bearer " + request_signature(platform,config,actor,method,path,body)}


def test_controller_rejects_direct_sessions_wrong_request_and_replay(controller):
    platform,config,client = controller
    path = "/api/agent-workshop"
    assert client.get(path).status_code == 401
    headers = authorization(platform,config,"GET",path)
    assert client.get(path,headers=headers).status_code == 200
    assert client.get(path,headers=headers).status_code == 409
    assert client.post(path,json={"name":"wrong body"},headers=authorization(platform,config,"POST",path)).status_code == 401
    assert client.get(path+"/models",headers=authorization(platform,config,"GET",path)).status_code == 401
    assert not (config.data_dir / "structura.db").exists()


def test_campaign_is_private_to_delegated_admin_and_legacy_alias_works(controller):
    platform,config,client = controller
    path = "/api/agent-workshop"
    body = json.dumps({"name":"QA centrale","months":1,"max_turns":10}).encode()
    created = client.post(path,content=body,headers={**authorization(platform,config,"POST",path,body),"Content-Type":"application/json"})
    assert created.status_code == 201
    key = created.json()["id"]
    assert created.json()["status"] == "DRAFT"
    detail = path + "/" + key
    assert client.get(detail,headers=authorization(platform,config,"GET",detail,actor=2)).status_code == 404
    alias = "/api/admin/agent-workshop/" + key
    assert client.get(alias,headers=authorization(platform,config,"GET",alias)).status_code == 200
    exported = detail + "/export"
    assert client.get(exported,headers=authorization(platform,config,"GET",exported)).status_code == 200
    with closing(sqlite3.connect(config.data_dir / "controller.db")) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"controller_identity","request_receipts"}


def test_central_admin_controls_are_explicit_and_business_tokens_are_rejected(tmp_path,monkeypatch):
    configs = prepare(tmp_path / "manual",8250)
    platform = configs[0]
    prepare_controls(platform)
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG",str(platform.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR",str(platform.data_dir))
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS","0")
    with TestClient(platform_app()) as client:
        reply = client.post("/api/auth/login",data={"username":"admin","password":credentials(platform)["admin"]})
        headers = {"Authorization":"Bearer " + reply.json()["access_token"]}
        assert client.post("/api/platform/simulation/start",headers=headers).status_code == 403
        assert client.get("/api/agent-workshop",headers=headers).status_code == 403
        monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS","1")
        assert "simulation.manage" in client.get("/api/auth/me",headers=headers).json()["capabilities"]
        assert client.post("/api/platform/installations/unknown/start",headers=headers).status_code == 404
        assert client.get("/api/agent-workshop",headers={"Authorization":"Bearer fictitious-business-token"}).status_code == 401
        assert client.get("/api/deals",headers=headers).status_code == 404
