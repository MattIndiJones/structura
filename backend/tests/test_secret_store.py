"""P1-8 / S5: secrets at rest sealed by the system, receipts key left readable."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from backend.app.api import auth
from backend.app.core import secret_store, session_key
from backend.app.core.instance_signing import receipt_signing_secret
from backend.app.db.rfq_transport_integrity import seal_channel_secrets
from backend.app.services import rfq_transport
from backend.app.services.llm import keys

windows = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI n'existe que sous Windows")


@windows
def test_a_sealed_secret_is_not_readable_in_the_file_and_reads_back(tmp_path):
    path = tmp_path / ".openai_key"
    secret_store.write_secret(path, "sk-desk-structura-123")
    raw = path.read_bytes()
    assert raw.startswith(secret_store.MARKER) and b"sk-desk" not in raw
    assert secret_store.read_secret(path) == "sk-desk-structura-123"


@windows
def test_a_plain_file_from_before_is_read_then_sealed_in_place(tmp_path):
    path = tmp_path / ".anthropic_key"
    path.write_text("sk-ant-ancienne-cle", encoding="utf-8")
    assert secret_store.read_secret(path) == "sk-ant-ancienne-cle"
    assert secret_store.is_sealed(path)
    assert secret_store.read_secret(path) == "sk-ant-ancienne-cle"


@windows
def test_a_blob_this_account_cannot_open_is_refused(tmp_path):
    path = tmp_path / ".openai_key"
    secret_store.write_secret(path, "sk-desk")
    raw = bytearray(path.read_bytes())
    raw[-8:-4] = b"AAAA"                                 # another machine's blob, as far as DPAPI can tell
    path.write_bytes(bytes(raw))
    with pytest.raises(secret_store.SecretUnavailable, match="autre compte Windows"):
        secret_store.read_secret(path)


def test_without_dpapi_the_file_stays_plain_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(secret_store, "available", lambda: False)
    path = tmp_path / ".openai_key"
    secret_store.write_secret(path, "sk-desk")
    assert path.read_text(encoding="utf-8") == "sk-desk"
    assert secret_store.read_secret(path) == "sk-desk"
    assert secret_store.protection_status() == "FILE_PERMISSIONS"


@windows
def test_provider_keys_are_read_through_the_seal(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(keys, "_KEY_DIR", tmp_path)
    (tmp_path / ".openai_key").write_text("sk-desk\n", encoding="utf-8")
    assert keys.load_key("openai") == "sk-desk"
    assert secret_store.is_sealed(tmp_path / ".openai_key")
    (tmp_path / ".openai_key").write_bytes(secret_store.MARKER + b"pas-un-blob")
    assert keys.load_key("openai") is None              # unreadable: provider shown as unavailable


# ── Session key apart from the receipt key ─────────────────────────

def test_sessions_and_receipts_no_longer_share_a_key():
    assert auth._SECRET != receipt_signing_secret()


def test_the_session_key_is_created_sealed_and_kept(tmp_path):
    first = session_key.session_secret_at(tmp_path)
    assert len(first) >= session_key.MINIMUM_LENGTH
    assert session_key.session_secret_at(tmp_path) == first
    if sys.platform == "win32":
        assert secret_store.is_sealed(tmp_path / session_key.SESSION_FILE)


@windows
def test_an_unreadable_session_key_costs_a_login_not_a_start(tmp_path):
    (tmp_path / session_key.SESSION_FILE).write_bytes(secret_store.MARKER + b"autre-machine")
    fresh = session_key.session_secret_at(tmp_path)
    assert len(fresh) >= session_key.MINIMUM_LENGTH
    assert secret_store.read_secret(tmp_path / session_key.SESSION_FILE) == fresh


def test_the_receipt_key_file_is_left_readable(tmp_path):
    from backend.app.runtime import data_path
    receipt_file = data_path(".jwt_secret")
    if receipt_file.exists():
        assert not secret_store.is_sealed(receipt_file)


@windows
def test_bootstrap_credentials_are_written_sealed_and_read_back(tmp_path):
    from backend.app.hybrid.config import credentials
    names = {"superuser", "front", "operations", "controller"}
    secret_store.write_secret(tmp_path / ".bootstrap_credentials.json",
                              json.dumps({name: "x" * 32 for name in names}))
    config = SimpleNamespace(data_dir=tmp_path, kind="organization")
    assert set(credentials(config)) == names
    assert b"superuser" not in (tmp_path / ".bootstrap_credentials.json").read_bytes()


# ── RFQ channel keys in the database ───────────────────────────────

def test_a_channel_signs_with_the_same_key_once_sealed():
    plain = "ab" * 32
    sealed = rfq_transport.seal_channel_secret(plain)
    channel = SimpleNamespace(secret=sealed)
    expected = hmac.new(bytes.fromhex(plain), rfq_transport.canonical({"q": 1}).encode(), hashlib.sha256).hexdigest()
    assert rfq_transport.signature(channel, {"q": 1}) == expected
    if sys.platform == "win32":
        assert sealed.startswith(rfq_transport.SEALED_CHANNEL_PREFIX) and plain not in sealed


@windows
def test_channel_keys_stored_in_clear_are_sealed_on_upgrade():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rfq_channels (id TEXT PRIMARY KEY, secret TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO rfq_channels VALUES ('c1', :s)"), {"s": "cd" * 32})
        assert seal_channel_secrets(conn) == 1
        assert seal_channel_secrets(conn) == 0
        stored = conn.execute(text("SELECT secret FROM rfq_channels")).scalar()
    assert rfq_transport.channel_key(SimpleNamespace(secret=stored)) == bytes.fromhex("cd" * 32)
