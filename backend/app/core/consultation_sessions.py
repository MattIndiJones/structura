"""Session state beside the viewer lock, never inside an archived business book."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


@contextmanager
def connect():
    directory = os.environ.get("STRUCTURA_CONSULTATION_LOCK_DIR")
    if not directory or not Path(directory).is_absolute() or not Path(directory).is_dir():
        raise RuntimeError("Dossier de session de consultation absent.")
    connection = sqlite3.connect(Path(directory) / "sessions.db", timeout=5)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0)")
            connection.execute("CREATE TABLE IF NOT EXISTS revoked(token_digest TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, received_at TEXT NOT NULL, metadata_json TEXT NOT NULL)")
            yield connection
    finally:
        connection.close()


def version(user_id):
    with connect() as connection:
        row = connection.execute("SELECT version FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else 0


def revoked(digest):
    with connect() as connection:
        return connection.execute("SELECT 1 FROM revoked WHERE token_digest=?", (digest,)).fetchone() is not None


def audit(metadata, *, digest=None, expires_at=None, revoke_user_id=None):
    with connect() as connection:
        if digest:
            connection.execute("INSERT OR IGNORE INTO revoked VALUES(?,?)", (digest, expires_at))
        if revoke_user_id is not None:
            connection.execute("INSERT INTO users(user_id,version) VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET version=version+1", (revoke_user_id,))
        connection.execute("INSERT INTO audit(received_at,metadata_json) VALUES(?,?)",
                           (datetime.now(timezone.utc).isoformat(), json.dumps(metadata)))


def load_user(session, *, user_id=None, username=None):
    """Legacy books need no ALTER TABLE to authenticate a protected viewer."""
    from sqlmodel import select
    from ..db.models import User
    fields = (User.id, User.username, User.email, User.password_hash, User.role, User.entity_id, User.is_active, User.created_at)
    query = select(*fields).where(User.id == user_id) if user_id is not None else select(*fields).where(User.username == username)
    row = session.exec(query).first()
    if not row:
        return None
    user = User(**dict(row._mapping))
    user.auth_version = version(user.id)
    return user
