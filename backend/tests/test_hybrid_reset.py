"""Reset boundaries, stable inventory and preservation of unrelated work."""
import json
from contextlib import closing
from pathlib import Path
import socket
import sqlite3
import subprocess

import pytest
from backend.app.hybrid.deployment import prepare
from backend.app.hybrid import reset


def database(path, managed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        for table in ("users", "entities", "deals", "products", "rfq_requests", "amc_studies", "portfolios"):
            connection.execute(f'CREATE TABLE "{table}"(id INTEGER PRIMARY KEY)')
        connection.commit()


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git","init","--quiet"],cwd=root,check=True,capture_output=True)
    runtime = root / "tmp" / "manual"
    configs = prepare(runtime)
    for config in configs:
        if config.kind == "organization":
            database(config.data_dir / "structura.db")
        else:
            with closing(sqlite3.connect(config.data_dir / "platform.db")) as connection:
                connection.execute("CREATE TABLE platform_identity(id INTEGER)")
                connection.execute("CREATE TABLE platform_users(id INTEGER)")
                connection.commit()
    database(root / "backend" / "data" / "structura.db")
    (root / "backend" / "data" / ".jwt_secret").write_text("old-token-key")
    (root / "tmp" / "unrelated.txt").write_text("keep")
    with closing(sqlite3.connect(root / "tmp" / "other.db")) as connection:
        connection.execute("CREATE TABLE another_project(id INTEGER)")
    return root, runtime


def test_reset_only_identified_data_preserves_manual_and_unrelated_work(layout, monkeypatch):
    root, runtime = layout
    monkeypatch.setattr(reset,"require_inactive",lambda *_:None)
    plan = reset.inventory(root,runtime)
    assert len(plan["databases"]) == 1
    result = reset.apply_inventory(plan,root,runtime)
    assert result["deleted_databases"] == 1
    assert not (root / "backend" / "data" / "structura.db").exists()
    assert not (root / "backend" / "data" / ".jwt_secret").exists()
    assert (root / "tmp" / "other.db").exists()
    assert (runtime / "bnp-paribas" / "structura.db").exists()
    assert (root / "tmp" / "unrelated.txt").read_text() == "keep"


def test_changed_inventory_and_tracked_file_are_refused(layout, monkeypatch):
    root, runtime = layout
    monkeypatch.setattr(reset,"require_inactive",lambda *_:None)
    plan = reset.inventory(root,runtime)
    (root / "backend" / "data" / ".jwt_secret").write_text("changed")
    with pytest.raises(ValueError,match="changé"):
        reset.apply_inventory(plan,root,runtime)
    subprocess.run(["git","add","backend/data/.jwt_secret"],cwd=root,check=True,capture_output=True)
    with pytest.raises(ValueError,match="versionné"):
        reset.inventory(root,runtime)


def test_reset_requires_empty_initialized_manual_runtime(layout):
    root, runtime = layout
    with closing(sqlite3.connect(runtime / "bnp-paribas" / "structura.db")) as connection:
        connection.execute("INSERT INTO products VALUES(1)")
        connection.commit()
    with pytest.raises(ValueError,match="dossiers"):
        reset.inventory(root,runtime)


def test_another_checkout_inside_tmp_is_preserved(layout):
    root, runtime = layout
    another = root / "tmp" / "hybrid-other-work"
    another.mkdir()
    subprocess.run(["git","init","--quiet"],cwd=another,check=True,capture_output=True)
    database(another / "structura.db")
    plan = reset.inventory(root,runtime)
    assert str(another / "structura.db") in plan["unidentified_databases_preserved"]
    assert not any(entry["path"].startswith(str(another)) for entry in plan["files"])


def test_reset_cannot_leave_repo_or_ignore_an_active_service(layout):
    root, runtime = layout
    with pytest.raises(ValueError,match="sort"):
        reset.safe_path(root.parent / "other",root)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0))
        listener.listen()
        # Add only an explicit occupied port through the existing layout.
        port = listener.getsockname()[1]
        path = runtime / "platform" / "installation.json"
        payload = json.loads(path.read_text()); payload["port"] = port
        path.write_text(json.dumps(payload))
        from backend.app.hybrid.config import read_config
        read_config.cache_clear()
        with pytest.raises(ValueError,match="actif"):
            reset.require_inactive(root,runtime)
