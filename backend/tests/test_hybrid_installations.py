"""Installation boundary tests use private temporary roots, never backend/data."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jose import jwt
import pytest

from backend.app.hybrid.config import current_config, credentials, signing_secret
from backend.app.hybrid.deployment import environment, load_layout, prepare
from backend.app.hybrid.platform import create_app
from backend.app.runtime import data_path


def test_preparation_is_repeatable_and_private(tmp_path, monkeypatch):
    configs = prepare(tmp_path / "hybrid")
    first = [(str(c.installation_id), signing_secret(c), credentials(c)) for c in configs]
    repeated = prepare(tmp_path / "hybrid")
    assert first == [(str(c.installation_id), signing_secret(c), credentials(c)) for c in repeated]
    assert len({value[1] for value in first}) == 7
    assert sum(len(value[2]) for value in first) == 25
    for config in configs:
        monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(config.data_dir / "installation.json"))
        monkeypatch.setenv("STRUCTURA_DATA_DIR", str(config.data_dir))
        assert data_path("documents").parent == config.data_dir
        assert current_config().registry_state == "NOT_CONFIGURED"


def test_managed_environment_does_not_inherit_other_installation(tmp_path, monkeypatch):
    config = prepare(tmp_path / "hybrid")[1]
    monkeypatch.setenv("STRUCTURA_JWT_SECRET", "other installation secret")
    monkeypatch.setenv("STRUCTURA_CONSULTATION", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "other installation provider key")
    env = environment(config)
    assert "STRUCTURA_JWT_SECRET" not in env and "STRUCTURA_CONSULTATION" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["TEMP"] == str(config.data_dir / "tmp")


def test_openai_key_is_only_forwarded_to_central_campaign_controller(tmp_path, monkeypatch):
    from backend.app.hybrid.control_services import prepare_controls

    configs = prepare(tmp_path / "hybrid")
    controls = prepare_controls(configs[0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    assert environment(controls["admin-workbench"])["OPENAI_API_KEY"] == "test-provider-key"
    assert environment(controls["simulation"])["OPENAI_API_KEY"] == "test-provider-key"
    assert "OPENAI_API_KEY" not in environment(configs[0])
    assert "OPENAI_API_KEY" not in environment(configs[1])
    assert "ANTHROPIC_API_KEY" not in environment(controls["admin-workbench"])


def test_prepare_refuses_unidentified_or_protected_data(tmp_path):
    (tmp_path / "other-work.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="non identifiées"):
        prepare(tmp_path)
    assert (tmp_path / "other-work.txt").read_text() == "keep"
    from backend.app.hybrid.deployment import ROOT
    with pytest.raises(ValueError):
        prepare(ROOT / "backend" / "data")


def test_partial_layout_resumes_and_lost_secret_is_not_replaced(tmp_path):
    root = tmp_path / "hybrid"
    configs = prepare(root)
    identity = configs[1].installation_id
    (root / "layout.json").unlink()
    assert prepare(root)[1].installation_id == identity
    (configs[1].data_dir / "structura.db").touch()
    (configs[1].data_dir / ".jwt_secret").unlink()
    with pytest.raises(ValueError, match="perdu sa clé"):
        prepare(root)


def test_layout_cannot_redirect_to_other_private_directory(tmp_path):
    root = tmp_path / "hybrid"
    prepare(root)
    layout = json.loads((root / "layout.json").read_text(encoding="utf-8"))
    layout["installations"]["citi"] = layout["installations"]["ubs"]
    (root / "layout.json").write_text(json.dumps(layout), encoding="utf-8")
    with pytest.raises(ValueError, match="sort du périmètre"):
        load_layout(root)


def test_central_service_has_no_business_schema_or_routes(tmp_path, monkeypatch):
    import sqlite3
    config = prepare(tmp_path / "hybrid")[0]
    monkeypatch.setenv("STRUCTURA_INSTALLATION_CONFIG", str(config.data_dir / "installation.json"))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(config.data_dir))
    with TestClient(create_app()) as client:
        assert client.get("/api/platform/installations").status_code == 401
        reply = client.post("/api/auth/login", data={"username": "admin", "password": credentials(config)["admin"]})
        assert reply.status_code == 200
        token = reply.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        result = client.get("/api/platform/installations", headers=headers).json()
        assert len(result["installations"]) == 6 and result["registry_state"] == "NOT_CONFIGURED"
        assert result["billing_enabled"] is False
        assert "data_dir" not in json.dumps(result)
        assert client.get("/api/deals", headers=headers).status_code == 404
        wrong = jwt.decode(token, signing_secret(config), algorithms=["HS256"], audience=str(config.installation_id))
        wrong["aud"] = "other-installation"
        bad_token = jwt.encode(wrong, signing_secret(config), algorithm="HS256")
        assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + bad_token}).status_code == 401
    assert not (config.data_dir / "structura.db").exists()
    with sqlite3.connect(config.data_dir / "platform.db") as connection:
        names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert names == {"platform_identity", "platform_users", "platform_installations", "platform_audit", "platform_revoked_sessions"}
        assert connection.execute("SELECT count(*) FROM platform_audit WHERE action='DIRECTORY_READ'").fetchone()[0] == 1


def test_directory_rejects_private_business_contents(tmp_path):
    from backend.app.hybrid.platform import initialize
    from pydantic import ValidationError
    config = prepare(tmp_path / "hybrid")[0]
    path = config.data_dir / "directory.json"
    directory = json.loads(path.read_text(encoding="utf-8"))
    directory[0]["private_book"] = {"example": "never collect"}
    path.write_text(json.dumps(directory), encoding="utf-8")
    with pytest.raises(ValidationError):
        initialize(config)


def test_central_bootstrap_refuses_an_unidentified_business_database(tmp_path):
    import sqlite3
    from backend.app.hybrid.platform import initialize
    config = prepare(tmp_path / "hybrid")[0]
    with sqlite3.connect(config.data_dir / "platform.db") as connection:
        connection.execute("CREATE TABLE private_book(id INTEGER PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="schéma métier"):
        initialize(config)
    with sqlite3.connect(config.data_dir / "platform.db") as connection:
        assert connection.execute("SELECT count(*) FROM sqlite_master WHERE name='platform_users'").fetchone()[0] == 0
