"""P1-9: a running installation can be diagnosed.

Audit of 16/11/2026, section 6.3: no logging configuration anywhere, request
tracebacks lost on uvicorn's non-propagating loggers, an unbounded server.log,
and a health route that never touched the database.
"""
from __future__ import annotations

import asyncio
import logging
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from backend.app import logging_setup, main
from backend.app.db import database
from backend.tests.sqlite_engines import _create_engine


@pytest.fixture
def clean_logging():
    """configure_logging changes process-wide state: restore it."""
    root, server = logging.getLogger(), logging.getLogger("uvicorn")
    saved = (list(root.handlers), root.level, list(server.handlers))
    yield
    for logger in (root, server):
        for handler in [h for h in logger.handlers if getattr(h, logging_setup._MARK, False)]:
            logger.removeHandler(handler)
            handler.close()
    root.handlers[:], server.handlers[:] = saved[0], saved[2]
    root.setLevel(saved[1])


def _flush():
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_info_records_reach_the_installation_file(tmp_path, clean_logging):
    path = logging_setup.configure_logging(tmp_path / "logs")
    assert path == tmp_path / "logs" / "structura.log"
    logging.getLogger("structura.lifecycle").info("Refresh quotidien SUCCESS")
    logging.getLogger("httpx").info("HTTP Request: GET https://example.test")
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "INFO" in text and "structura.lifecycle : Refresh quotidien SUCCESS" in text
    assert "example.test" not in text            # libraries stay at WARNING


@pytest.mark.parametrize("configured_by_uvicorn", [True, False])
def test_a_request_traceback_logged_by_uvicorn_reaches_the_file(tmp_path, clean_logging, monkeypatch,
                                                               configured_by_uvicorn):
    # Under uvicorn.Config, "uvicorn" does not propagate to the root logger.
    monkeypatch.setattr(logging.getLogger("uvicorn"), "propagate", not configured_by_uvicorn)
    path = logging_setup.configure_logging(tmp_path)
    try:
        raise ZeroDivisionError("division du payoff")
    except ZeroDivisionError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in text and "division du payoff" in text
    assert text.count("Exception in ASGI application") == 1


def test_configuration_is_idempotent_and_keeps_the_console(tmp_path, clean_logging):
    foreign = logging.NullHandler()
    logging.getLogger().addHandler(foreign)
    logging_setup.configure_logging(tmp_path)
    logging_setup.configure_logging(tmp_path)
    own = [h for h in logging.getLogger().handlers if getattr(h, logging_setup._MARK, False)]
    assert sorted(type(h).__name__ for h in own) == ["RotatingFileHandler", "StreamHandler"]
    console = next(h for h in own if type(h) is logging.StreamHandler)
    assert console.level == logging.WARNING      # the console behaviour of before
    assert foreign in logging.getLogger().handlers
    rotating = next(h for h in own if type(h) is not logging.StreamHandler)
    assert (rotating.maxBytes, rotating.backupCount) == (5 * 1024 * 1024, 5)


def test_the_level_is_configurable(tmp_path, clean_logging, monkeypatch):
    monkeypatch.setenv("STRUCTURA_LOG_LEVEL", "WARNING")
    path = logging_setup.configure_logging(tmp_path)
    logging.getLogger("structura.lifecycle").info("silencieux")
    logging.getLogger("structura.lifecycle").warning("visible")
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "visible" in text and "silencieux" not in text


def test_consultation_writes_no_file(clean_logging):
    assert logging_setup.configure_logging(None) is None
    assert not any(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers
                   if getattr(h, logging_setup._MARK, False))


def test_a_background_task_failure_is_logged_with_its_traceback(caplog):
    async def scenario():
        async def loop():
            raise RuntimeError("calendrier introuvable")
        task = asyncio.create_task(loop())
        task.add_done_callback(logging_setup.log_task_failure(logging.getLogger("test"), "ordonnanceur"))
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)
    with caplog.at_level(logging.ERROR, logger="test"):
        asyncio.run(scenario())
    record = next(r for r in caplog.records if "ordonnanceur" in r.getMessage())
    assert record.exc_info and "calendrier introuvable" in str(record.exc_info[1])


def test_the_server_log_rotates_at_start_when_too_big(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("x" * 20, encoding="utf-8")
    assert not logging_setup.rotate_server_log(log, max_bytes=100)
    for generation in range(4):
        log.write_text(str(generation) * 200, encoding="utf-8")
        assert logging_setup.rotate_server_log(log, max_bytes=100, backups=3)
    assert not log.exists()
    kept = {p.name: p.read_text(encoding="utf-8")[0] for p in tmp_path.iterdir()}
    assert kept == {"server.log.1": "3", "server.log.2": "2", "server.log.3": "1"}


# ── /health checks the database ─────────────────────────────────────

def _memory(create=create_engine):
    # One shared in-memory database: the check runs in a worker thread.
    return create("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _client(monkeypatch, engine):
    monkeypatch.setattr(database, "engine", engine)
    return TestClient(main.app)          # no startup: only the routes


def test_health_reports_a_readable_database_with_its_constraint(monkeypatch):
    engine = _memory()                   # tests' engines enforce foreign keys
    SQLModel.metadata.create_all(engine)
    client = _client(monkeypatch, engine)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == {"ok": True, "foreign_keys": True}
    assert client.get("/health/ready").status_code == 200


def test_a_missing_schema_is_degraded_not_down(monkeypatch):
    # SQLite creates an empty database on connection: SELECT 1 would say ok.
    client = _client(monkeypatch, _memory())
    response = client.get("/health")
    assert response.status_code == 200        # launchers identify the instance on a 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"]["error"] == "SCHEMA_ABSENT"
    ready = client.get("/health/ready")
    assert ready.status_code == 503 and ready.json()["ready"] is False


def test_a_database_without_foreign_keys_is_degraded(monkeypatch):
    engine = _memory(_create_engine)          # no rule, as a misconfigured engine
    SQLModel.metadata.create_all(engine)
    body = _client(monkeypatch, engine).get("/health").json()
    assert body["status"] == "degraded" and body["database"]["error"] == "FOREIGN_KEYS_OFF"


def test_a_database_that_does_not_answer_times_out(monkeypatch):
    monkeypatch.setattr(main, "_database_check", lambda: time.sleep(1) or {"ok": True})
    assert asyncio.run(main._database_status(timeout=.05)) == {"ok": False, "error": "TIMEOUT"}


def test_an_unreachable_database_is_logged(monkeypatch, caplog):
    class Broken:
        def connect(self):
            raise OSError("disque absent")
    monkeypatch.setattr(database, "engine", Broken())
    with caplog.at_level(logging.ERROR):
        assert main._database_check() == {"ok": False, "error": "OSError"}
    assert any(r.exc_info for r in caplog.records if "base inaccessible" in r.getMessage())
