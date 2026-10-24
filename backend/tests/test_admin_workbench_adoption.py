"""Offline historical adoption preserves identity guards, accounts and data."""
import json
import socket
import sqlite3

import bcrypt
import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.db import database
from backend.app.db.models import Entity, User, Underlying
from backend.app.hybrid import admin_workbench
from backend.app.hybrid.admin_adoption import adopt, fingerprint, inspect_adoption
from backend.app.hybrid.config import credentials
from backend.app.hybrid.control_services import prepare_controls
from backend.app.hybrid.deployment import prepare
from backend.app.services.agent_workshop.lease import CampaignLease


@pytest.fixture
def legacy(tmp_path):
    config = prepare_controls(prepare(tmp_path / "hybrid")[0])["admin-workbench"]
    # A free ephemeral port keeps this fixture independent of the user's launcher.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        config = config.model_copy(update={"port": sock.getsockname()[1]})
    manifest = config.data_dir / "installation.json"
    manifest.write_text(config.model_dump_json(), encoding="utf-8")
    path = config.data_dir / "structura.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Entity(id=1, name="Structura — développement Admin"))
        session.add(User(id=1, username="admin", email="admin@structura.local", role="admin", entity_id=1,
                         password_hash=bcrypt.hashpw(credentials(config)["admin"].encode(), bcrypt.gensalt()).decode()))
        session.add(Underlying(ticker="HISTORICAL", label="Référence conservée"))
        session.commit()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE admin_workbench_identity")
        connection.execute("ALTER TABLE users DROP COLUMN auth_version")
        connection.execute("ALTER TABLE users DROP COLUMN password_change_required")
    return config, manifest, path


def apply(legacy, **kwargs):
    config, manifest, path = legacy
    return adopt(manifest, **{"expected_installation_id": str(config.installation_id),
                             "expected_sha256": fingerprint(path),
                             "reason": "Reprise explicite du workspace historique", **kwargs})


def test_inspection_is_read_only_and_adoption_backs_up_every_original_row(legacy):
    config, manifest, path = legacy
    before = path.read_bytes()
    report = inspect_adoption(manifest)
    assert report["bootstrap_verified"] and not report["applied"]
    assert path.read_bytes() == before
    with pytest.raises(RuntimeError, match="sans identité"):
        engine = create_engine(f"sqlite:///{path}")
        try:
            admin_workbench.preflight(engine, config)
        finally:
            engine.dispose()
    result = apply(legacy)
    from pathlib import Path
    assert Path(result["backup"]).read_bytes() == before
    with sqlite3.connect(path) as current, sqlite3.connect(result["backup"]) as original:
        for (table,) in original.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            original_rows = original.execute(f'SELECT * FROM "{table}"').fetchall()
            current_rows = current.execute(f'SELECT * FROM "{table}"').fetchall()
            assert current_rows[:len(original_rows)] == original_rows
            if table != "audit_events":
                assert len(current_rows) == len(original_rows)
        assert current.execute("SELECT installation_id, entity_id FROM admin_workbench_identity").fetchone() \
            == (str(config.installation_id), 1)
        audit = current.execute("SELECT action, actor_type, reason, metadata_json FROM audit_events").fetchone()
        assert audit[:3] == ("ADMIN_WORKBENCH_ADOPTED", "PROCESS", "Reprise explicite du workspace historique")
        assert json.loads(audit[3])["database_sha256"] == report["database_sha256"]
        assert not current.execute("PRAGMA foreign_key_check").fetchall()
    engine = create_engine(f"sqlite:///{path}")
    try:
        admin_workbench.preflight(engine, config)
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutation", [
    "wrong-password", "disabled", "wrong-role", "wrong-entity", "second-user", "unknown-schema",
    "business-marker", "foreign-admin-marker", "broken-fk", "journal", "wrong-manifest",
])
def test_refused_adoption_never_changes_existing_database(legacy, mutation):
    config, manifest, path = legacy
    with sqlite3.connect(path) as connection:
        if mutation == "wrong-password":
            connection.execute("UPDATE users SET password_hash='invalid'")
        elif mutation == "disabled":
            connection.execute("UPDATE users SET is_active=0")
        elif mutation == "wrong-role":
            connection.execute("UPDATE users SET role='user'")
        elif mutation == "wrong-entity":
            connection.execute("UPDATE entities SET name='Foreign'")
        elif mutation == "second-user":
            connection.execute("INSERT INTO users SELECT 2,'other','other@test',password_hash,'user',1,1,created_at FROM users")
        elif mutation == "unknown-schema":
            connection.execute("CREATE TABLE foreign_data(id INTEGER)")
        elif mutation == "business-marker":
            connection.execute("INSERT INTO hybrid_bootstrap VALUES (1,'other','other',1,1,'{}')")
        elif mutation == "foreign-admin-marker":
            connection.execute("CREATE TABLE admin_workbench_identity(id INTEGER, installation_id TEXT, entity_id INTEGER)")
            connection.execute("INSERT INTO admin_workbench_identity VALUES (1,'foreign',1)")
        elif mutation == "broken-fk":
            connection.execute("UPDATE users SET entity_id=999")
        elif mutation == "journal":
            from pathlib import Path
            Path(str(path) + "-wal").write_bytes(b"unrecovered")
        elif mutation == "wrong-manifest":
            manifest.write_text(config.model_copy(update={"service": "application"}).model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        apply(legacy)
    assert path.read_bytes() == before
    assert not (config.data_dir / "backups").exists()


@pytest.mark.parametrize("argument,value", [("expected_installation_id", "foreign"),
                                           ("expected_sha256", "outdated"), ("reason", "")])
def test_explicit_attestation_is_required(legacy, argument, value):
    before = legacy[2].read_bytes()
    with pytest.raises((RuntimeError, ValueError)):
        apply(legacy, **{argument: value})
    assert legacy[2].read_bytes() == before


def test_active_workspace_and_foreign_port_are_refused(legacy):
    config, manifest, path = legacy
    before = path.read_bytes()
    lease = CampaignLease(config.data_dir)
    try:
        with pytest.raises(RuntimeError, match="actif"):
            apply(legacy)
    finally:
        lease.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", config.port))
        sock.listen()
        with pytest.raises(RuntimeError, match="Port occupé"):
            apply(legacy)
    assert path.read_bytes() == before


def test_audit_failure_rolls_back_identity_but_keeps_backup(legacy):
    config, manifest, path = legacy
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER reject_adoption BEFORE INSERT ON audit_events
                              BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END""")
    before = path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
        apply(legacy)
    assert path.read_bytes() == before
    assert len(list((config.data_dir / "backups").glob("*.db"))) == 1


def test_normal_migration_and_restarts_preserve_existing_account(legacy, monkeypatch):
    config, manifest, path = legacy
    apply(legacy)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT id,username,password_hash,role,entity_id,is_active FROM users").fetchall()
    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_DB_PATH", path)
    monkeypatch.setenv("STRUCTURA_BOOTSTRAP_PROFILE", "admin_workbench")
    monkeypatch.setenv("STRUCTURA_ADMIN_WORKBENCH_CONFIG", str(manifest))
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(config.data_dir))
    monkeypatch.delenv("STRUCTURA_INSTALLATION_CONFIG", raising=False)
    try:
        database.init_db()
        database.init_db()
    finally:
        engine.dispose()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT id,username,password_hash,role,entity_id,is_active FROM users").fetchall() == before
        assert connection.execute("SELECT auth_version,password_change_required FROM users").fetchone() == (0, 0)
        assert connection.execute("SELECT count(*) FROM admin_workbench_identity").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM audit_events WHERE action='ADMIN_WORKBENCH_ADOPTED'").fetchone()[0] == 1
    # A retry cannot duplicate the attestation or reset a provisioned account.
    after = path.read_bytes()
    with pytest.raises(RuntimeError, match="déjà attestée"):
        apply(legacy)
    assert path.read_bytes() == after
