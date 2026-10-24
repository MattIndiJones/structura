"""Explicit, offline adoption of the original single-admin development workspace.

Never called by startup: an occupied unmarked database still fails preflight.
The private bootstrap credential is corroborating evidence, not a replacement
for the operator's explicit manifest identity and database fingerprint.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
from uuid import uuid4

import bcrypt
from sqlmodel import SQLModel

from .config import credentials, read_config, signing_secret
from ..services.agent_workshop.lease import CampaignLease


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _offline(config):
    if CampaignLease.is_held(config.data_dir) is not False:
        raise RuntimeError("Workspace actif ou verrou invérifiable ; adoption refusée.")
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", config.port))
        except OSError as exc:
            raise RuntimeError("Port occupé ; arrêter le service avant adoption.") from exc
    path = config.data_dir / "structura.db"
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Base locale existante requise ; aucun fichier créé.")
    for suffix in ("-wal", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise RuntimeError("Journal SQLite présent ; reprise hors ligne requise.")
    return path


def _inspect(connection, config):
    # Register the same business schema as normal startup, without opening its DB.
    from ..db import models, trading_models  # noqa: F401
    from . import admin_workbench, business  # noqa: F401

    tables = {r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'")}
    if tables - (set(SQLModel.metadata.tables) | {"app_migrations"}):
        raise RuntimeError("Schéma inconnu ; adoption refusée.")
    if not {"users", "entities", "audit_events"} <= tables:
        raise RuntimeError("Schéma Admin historique incomplet ; adoption refusée.")
    for table in ("admin_workbench_identity", "hybrid_bootstrap", "rfq_installations"):
        if table in tables and connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
            raise RuntimeError("Identité déjà attestée ou identité métier présente ; adoption refusée.")
    if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)] \
            or connection.execute("PRAGMA foreign_key_check").fetchone():
        raise RuntimeError("Intégrité SQLite invalide ; adoption refusée.")
    entities = connection.execute("SELECT id, name FROM entities").fetchall()
    users = connection.execute(
        "SELECT id, username, role, entity_id, is_active, password_hash FROM users").fetchall()
    if len(entities) != 1 or entities[0][1] != "Structura — développement Admin" \
            or len(users) != 1 or users[0][1:5] != ("admin", "admin", entities[0][0], 1):
        raise RuntimeError("Le workspace ne correspond pas au bootstrap Admin historique ; expertise manuelle requise.")
    try:
        matches = bcrypt.checkpw(credentials(config)["admin"].encode(), users[0][5].encode())
    except (ValueError, TypeError):
        matches = False
    if not matches:
        raise RuntimeError("Le secret privé de bootstrap ne correspond pas au compte existant ; adoption refusée.")
    return {"entity_id": entities[0][0], "admin_user_id": users[0][0],
            "installation_id": str(config.installation_id), "bootstrap_verified": True}


def _config(manifest):
    # Provisioning must read the current manifest, not the application's cached
    # startup configuration (the operator may have just reviewed its contents).
    config = read_config.__wrapped__(str(manifest))
    if config.service != "admin_workbench" or config.kind != "platform" or config.key != "admin-workbench":
        raise RuntimeError("Un manifeste du workspace Admin est requis.")
    signing_secret(config)
    return config


def inspect_adoption(manifest):
    config = _config(manifest)
    path = _offline(config)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        result = _inspect(connection, config)
    return {**result, "database_sha256": fingerprint(path), "applied": False}


def adopt(manifest, *, expected_installation_id, expected_sha256, reason):
    config = _config(manifest)
    if str(config.installation_id) != str(expected_installation_id):
        raise RuntimeError("Identité du manifeste différente de l'identité attestée.")
    if not reason or len(reason.strip()) < 10:
        raise ValueError("Un motif de provisionnement explicite est requis.")
    path = _offline(config)
    lease = CampaignLease(config.data_dir)
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                # Recheck after acquiring the OS lease and SQLite writer lock.
                if fingerprint(path) != expected_sha256:
                    raise RuntimeError("La base a changé depuis son inventaire ; adoption refusée.")
                result = _inspect(connection, config)
                backup_dir = config.data_dir / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / ("pre-admin-adoption-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                                       + "-" + uuid4().hex[:8] + ".db")
                # No WAL/hot journal and a reserved writer lock: the original
                # bytes are stable, including the pre-migration schema.
                with backup.open("xb") as target, path.open("rb") as source:
                    shutil.copyfileobj(source, target)
                if fingerprint(backup) != expected_sha256:
                    raise RuntimeError("Empreinte de sauvegarde incohérente ; adoption annulée.")
                connection.execute("""CREATE TABLE IF NOT EXISTS admin_workbench_identity (
                    id INTEGER PRIMARY KEY, installation_id VARCHAR NOT NULL UNIQUE,
                    entity_id INTEGER NOT NULL REFERENCES entities(id))""")
                connection.execute("INSERT INTO admin_workbench_identity VALUES (1, ?, ?)",
                                   (str(config.installation_id), result["entity_id"]))
                connection.execute("""INSERT INTO audit_events
                    (action, object_type, object_id, actor_user_id, actor_type, result,
                     before_json, after_json, reason, metadata_json, created_at)
                    VALUES (?, ?, 1, ?, 'PROCESS', 'SUCCESS', '{}', ?, ?, ?, ?)""",
                    ("ADMIN_WORKBENCH_ADOPTED", "INSTALLATION", result["admin_user_id"],
                     json.dumps(result), reason.strip(),
                     json.dumps({"database_sha256": expected_sha256, "backup": backup.name}),
                     datetime.now(timezone.utc).isoformat()))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return {**result, "applied": True, "backup": str(backup), "backup_sha256": expected_sha256}
    finally:
        lease.close()
