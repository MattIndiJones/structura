"""P1-8 / S6: the business audit trail is append-only and hash-chained."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import admin as admin_api
from backend.app.api.auth import get_current_admin
from backend.app.core.audit import record_audit_event
from backend.app.db import audit_integrity
from backend.app.db.database import get_session
from backend.app.db.models import AuditChainLink, AuditEvent


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


def _record(session, action, **extra):
    return record_audit_event(session, action=action, object_type="DEAL", object_id=extra.pop("object_id", 1),
                              actor_user_id=None, result="SUCCESS", after={"prix": 99.5}, **extra)


def _verify(engine):
    with engine.connect() as conn:
        return audit_integrity.verify_chain(conn)


def _drop_triggers(conn):
    for name in [row[0] for row in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'audit_%'"))]:
        conn.execute(text(f"DROP TRIGGER {name}"))


def test_each_event_is_linked_to_the_previous_one(engine):
    with Session(engine) as session:
        _record(session, "BOOKING")
        _record(session, "AMENDMENT")             # same flush: chained in id order
        session.commit()
        _record(session, "FIXING")
        session.commit()
        links = session.exec(select(AuditChainLink).order_by(AuditChainLink.event_id)).all()
    assert [link.event_id for link in links] == [1, 2, 3]
    assert links[0].prev_hash is None
    assert [link.prev_hash for link in links[1:]] == [link.row_hash for link in links[:-1]]
    assert _verify(engine) == dict(ok=True, checked=3, first_broken_event_id=None,
                                   unchained_event_ids=[], version=audit_integrity.CHAIN_VERSION)


def test_a_rolled_back_action_leaves_neither_event_nor_link(engine):
    with Session(engine) as session:
        _record(session, "BOOKING")
        session.flush()
        session.rollback()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_chain")).scalar() == 0
    assert _verify(engine)["ok"]


@pytest.mark.parametrize("statement", [
    "UPDATE audit_events SET action='EFFACE' WHERE id=1",
    "DELETE FROM audit_events WHERE id=1",
    "UPDATE audit_chain SET row_hash='x' WHERE event_id=1",
    "DELETE FROM audit_chain WHERE event_id=1",
])
def test_the_trail_refuses_changes_and_deletions(engine, statement):
    with Session(engine) as session:
        _record(session, "BOOKING")
        session.commit()
    with engine.connect() as conn, pytest.raises(DatabaseError, match="ajout seul"):
        conn.execute(text(statement))


def test_an_edited_event_breaks_the_chain_at_that_event(engine):
    with Session(engine) as session:
        for action in ("BOOKING", "AMENDMENT", "FIXING"):
            _record(session, action)
        session.commit()
    with engine.begin() as conn:
        _drop_triggers(conn)                       # what a direct edit of the file can do
        conn.execute(text("UPDATE audit_events SET after_json='{\"prix\": 101}' WHERE id=2"))
    result = _verify(engine)
    assert result["ok"] is False and result["first_broken_event_id"] == 2


def test_a_removed_event_breaks_the_chain_at_the_next_one(engine):
    with Session(engine) as session:
        for action in ("BOOKING", "AMENDMENT", "FIXING"):
            _record(session, action)
        session.commit()
    with engine.begin() as conn:
        _drop_triggers(conn)
        conn.execute(text("DELETE FROM audit_chain WHERE event_id=2"))
        conn.execute(text("DELETE FROM audit_events WHERE id=2"))
    assert _verify(engine)["first_broken_event_id"] == 3


def test_an_event_inserted_by_raw_sql_is_reported_then_sealed(engine):
    with Session(engine) as session:
        _record(session, "BOOKING")
        session.commit()
    with engine.begin() as conn:                   # as hybrid/admin_adoption.py does
        conn.execute(text("""INSERT INTO audit_events (action, object_type, object_id, actor_type, result,
            before_json, after_json, metadata_json, created_at)
            VALUES ('ADMIN_WORKBENCH_ADOPTED', 'INSTALLATION', 1, 'PROCESS', 'SUCCESS', '{}', '{}', '{}',
                    '2026-11-19T10:00:00+00:00')"""))
    assert _verify(engine)["unchained_event_ids"] == [2] and not _verify(engine)["ok"]
    with engine.begin() as conn:
        assert audit_integrity.seal(conn) == 1
    assert _verify(engine)["ok"]
    with Session(engine) as session:               # the next event chains onto the sealed one
        _record(session, "FIXING")
        session.commit()
    assert _verify(engine) == {**_verify(engine), "ok": True, "checked": 3}


def test_an_existing_database_is_protected_and_its_history_sealed_on_upgrade(engine):
    with Session(engine) as session:
        for action in ("BOOKING", "AMENDMENT"):
            _record(session, action)
        session.commit()
    with engine.begin() as conn:                   # the schema before this version
        _drop_triggers(conn)
        conn.execute(text("DROP TABLE audit_chain"))
    SQLModel.metadata.create_all(engine)           # what init_db does first
    with engine.begin() as conn:
        assert audit_integrity.migrate(conn) == 2
        assert audit_integrity.migrate(conn) == 0  # idempotent
    assert _verify(engine)["ok"] and _verify(engine)["checked"] == 2
    with engine.connect() as conn, pytest.raises(DatabaseError, match="ajout seul"):
        conn.execute(text("DELETE FROM audit_events WHERE id=1"))


def test_a_schema_without_the_chain_table_still_records_events():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AuditEvent.__table__.metadata.tables["entities"],
                                                 AuditEvent.__table__.metadata.tables["users"],
                                                 AuditEvent.__table__])
    with Session(engine) as session:
        _record(session, "BOOKING")
        session.commit()
        assert session.exec(select(AuditEvent)).one().action == "BOOKING"


def test_the_admin_route_reports_the_chain(engine):
    app = FastAPI()
    app.include_router(admin_api.router)
    app.dependency_overrides[get_current_admin] = lambda: object()

    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with Session(engine) as session:
        _record(session, "BOOKING")
        session.commit()
    body = TestClient(app).get("/api/admin/audit/integrity").json()
    assert body["ok"] is True and body["checked"] == 1
