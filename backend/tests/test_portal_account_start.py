"""Explicit cold account access through the loopback development portal."""
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.auth import router as auth_router
from backend.app.hybrid.control_services import prepare_controls
from backend.app.hybrid.deployment import prepare
from backend.app.hybrid import deployment
from backend.app.hybrid.platform import create_app, connect
from backend.app.services.agent_workshop.lease import CampaignLease


@pytest.fixture
def portal(tmp_path, monkeypatch):
    configs = prepare(tmp_path / "hybrid")
    platform = configs[0]
    controls = prepare_controls(platform)
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(platform.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(platform.data_dir))
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "1")
    starts = []
    def start(config, **kwargs):
        reused = config.key in [item[0].key for item in starts]
        starts.append((config, kwargs))
        return {"started": not reused}
    monkeypatch.setattr(deployment, "start", start)
    with TestClient(create_app()) as client:
        yield client, configs, controls, starts


def body(config, **kwargs):
    return {"installation_id": str(config.installation_id), "username": "front", "start_if_needed": True, **kwargs}


def test_explicit_open_starts_only_the_selected_installation_before_grant(portal):
    client, configs, controls, starts = portal
    for _ in range(2):
        response = client.post("/api/platform/development/session", json=body(configs[1]), headers={"X-Structura-Development": "1"})
        assert response.status_code == 200 and "ticket" in response.json()
    assert [c.key for c, _ in starts] == ["bnp-paribas", "bnp-paribas"]
    assert all(options == {"developer_access": True} for _, options in starts)
    with connect(configs[0]) as db:
        actions = [json.loads(r[0]) for r in db.execute("SELECT action FROM platform_audit WHERE action LIKE '{%'")]
    events = [event for event in actions if event["action"] == "DEVELOPMENT_INSTALLATION_START"]
    assert [event["started"] for event in events] == [True, False]
    # Anonymous development access keeps its original audit origin.
    grant = next(event for event in actions if event["action"] == "DEVELOPMENT_GRANT")
    assert grant["origin"]["kind"] == "DEVELOPMENT_PORTAL"


def test_grant_without_explicit_start_keeps_existing_non_starting_contract(portal):
    client, configs, _, starts = portal
    response = client.post("/api/platform/development/session", json=body(configs[1], start_if_needed=False), headers={"X-Structura-Development": "1"})
    assert response.status_code == 200 and starts == []


@pytest.mark.parametrize("headers,username,status", [
    ({}, "front", 403),
    ({"X-Structura-Development": "1", "Origin": "https://foreign.invalid"}, "front", 403),
    ({"X-Structura-Development": "1"}, "admin", 403),
])
def test_no_service_start_before_access_and_profile_checks(portal, headers, username, status):
    client, configs, _, starts = portal
    assert client.post("/api/platform/development/session", json=body(configs[1], username=username), headers=headers).status_code == status
    assert not starts


def test_unavailable_service_returns_french_error_without_grant(portal, monkeypatch):
    client, configs, _, starts = portal
    def fail(*args, **kwargs):
        raise RuntimeError("private process detail")
    monkeypatch.setattr(deployment, "start", fail)
    response = client.post("/api/platform/development/session", json=body(configs[1]), headers={"X-Structura-Development": "1"})
    assert response.status_code == 503
    assert "Structura Admin" in response.json()["detail"] and "private" not in response.text
    assert "ticket" not in response.json()
    with connect(configs[0]) as db:
        assert not db.execute("SELECT 1 FROM platform_audit WHERE action LIKE '%DEVELOPMENT_GRANT%'").fetchone()


def test_directory_divergence_cannot_start_a_different_local_manifest(portal):
    client, configs, _, starts = portal
    with connect(configs[0]) as db:
        descriptor = configs[1].public_descriptor()
        descriptor["url"] = "http://127.0.0.1:19999"
        db.execute("UPDATE platform_installations SET descriptor_json=? WHERE installation_id=?", (json.dumps(descriptor), str(configs[1].installation_id)))
    assert client.post("/api/platform/development/session", json=body(configs[1]), headers={"X-Structura-Development": "1"}).status_code == 503
    assert not starts


def test_return_url_is_public_and_only_advertised_in_development(portal, monkeypatch):
    client, configs, controls, _ = portal
    assert client.get("/api/auth/options").json()["admin_workbench_url"] == controls["admin-workbench"].public_descriptor()["url"]
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "0")
    assert "admin_workbench_url" not in client.get("/api/auth/options").json()
    assert client.post("/api/platform/development/session", json=body(configs[1]), headers={"X-Structura-Development": "1"}).status_code == 404


@pytest.fixture
def admin_portal(tmp_path, monkeypatch):
    platform = prepare(tmp_path / "hybrid")[0]
    admin = prepare_controls(platform)["admin-workbench"]
    monkeypatch.delenv("STRUCTURA_INSTALLATION_CONFIG", raising=False)
    monkeypatch.setenv("STRUCTURA_ADMIN_WORKBENCH_CONFIG", str(admin.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(admin.data_dir))
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "admin_workbench")
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "1")
    monkeypatch.setenv("STRUCTURA_LAUNCH_ID", "admin-launch")
    process_record = admin.data_dir / ".process.json"
    deployment.atomic_json(process_record, {
        "installation_id": str(admin.installation_id), "launch_id": "admin-launch",
        "server_pid": os.getpid(), "pid": os.getpid(), "launcher_id": "react-window",
    })
    starts = []

    def start(config, **kwargs):
        reused = bool(starts)
        starts.append((config, kwargs))
        return {"key": config.key, "started": not reused, "reused": reused}

    monkeypatch.setattr(deployment, "start", start)
    app = FastAPI()
    app.include_router(auth_router)
    url = admin.public_descriptor()["url"]
    with TestClient(app, base_url=url, client=("127.0.0.1", 50000)) as client:
        yield client, platform, process_record, starts


DEVELOPMENT_PORTAL = "/api/auth/development-portal"
DEVELOPMENT_HEADER = {"X-Structura-Development": "1"}


def test_admin_does_not_need_the_portal_until_explicit_browser_intent(admin_portal):
    client, platform, _, starts = admin_portal
    platform_url = platform.public_descriptor()["url"]
    assert client.get("/api/auth/options").json()["platform_url"] == platform_url
    assert client.get(DEVELOPMENT_PORTAL).status_code == 405
    assert not starts
    for _ in range(2):
        response = client.post(DEVELOPMENT_PORTAL, headers={
            **DEVELOPMENT_HEADER, "Origin": str(client.base_url).rstrip("/"),
        })
        assert response.status_code == 200
        assert response.json() == {"url": platform_url}
    assert starts == [(platform, {"developer_access": True, "launcher_id": "react-window"})] * 2


@pytest.mark.parametrize("headers", [
    {},
    {**DEVELOPMENT_HEADER, "Origin": "https://foreign.invalid"},
    {**DEVELOPMENT_HEADER, "Sec-Fetch-Site": "cross-site"},
])
def test_admin_portal_rejects_requests_outside_the_local_development_boundary(admin_portal, headers):
    client, _, _, starts = admin_portal
    assert client.post(DEVELOPMENT_PORTAL, headers=headers).status_code == 403
    assert not starts


def test_admin_portal_is_disabled_outside_development(admin_portal, monkeypatch):
    client, _, _, starts = admin_portal
    monkeypatch.setenv("STRUCTURA_DEVELOPER_ACCESS", "0")
    assert client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER).status_code == 404
    assert not starts


@pytest.mark.parametrize("field,value", [
    ("installation_id", "foreign-installation"),
    ("launch_id", "stale-launch"),
    ("server_pid", -1),
    ("launcher_id", ""),
])
def test_admin_portal_requires_the_current_launchers_process_record(admin_portal, field, value):
    client, _, process_record, starts = admin_portal
    record = json.loads(process_record.read_text(encoding="utf-8"))
    deployment.atomic_json(process_record, {**record, field: value})
    assert client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER).status_code == 503
    assert not starts


def test_admin_portal_refuses_a_descriptor_outside_its_runtime(admin_portal):
    client, _, process_record, starts = admin_portal
    descriptor_path = process_record.with_name("platform.json")
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    deployment.atomic_json(descriptor_path, {**descriptor, "url": "http://127.0.0.1:19876"})
    assert client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER).status_code == 503
    assert not starts


def test_admin_portal_uses_the_same_lease_as_the_launcher(admin_portal):
    client, platform, _, starts = admin_portal
    directory = platform.data_dir.parent / "launcher-lock"
    directory.mkdir()
    lease = CampaignLease(directory)
    try:
        assert client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER).status_code == 503
        assert not starts
    finally:
        lease.close()
    assert client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER).status_code == 200
    assert len(starts) == 1


def test_admin_portal_start_failure_keeps_admin_available(admin_portal, monkeypatch):
    client, platform, _, starts = admin_portal

    def fail(config, **kwargs):
        assert config == platform
        raise RuntimeError("private process detail")

    monkeypatch.setattr(deployment, "start", fail)
    response = client.post(DEVELOPMENT_PORTAL, headers=DEVELOPMENT_HEADER)
    assert response.status_code == 503
    assert "portail" in response.json()["detail"].lower()
    assert "private" not in response.text
    assert client.get("/api/auth/options").status_code == 200
    assert not starts
