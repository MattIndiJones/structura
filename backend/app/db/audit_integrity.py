"""The business audit trail is append-only and hash-chained (P1-8, finding S6).

`audit_events` was written in the transaction of each action, which is
right, but nothing stopped a later UPDATE or DELETE, while RFQ evidence and
archives already had triggers. Two protections now:

- triggers refuse any UPDATE or DELETE on `audit_events` and on its chain;
- each event gets a link in `audit_chain`: the SHA-256 of its content and of
  the previous link. Editing or removing a past event, even with the
  triggers dropped, breaks every link after it, and `verify_chain` names the
  first one.

The chain lives in its own table on purpose: the `AuditEvent` model is
unchanged, so a database consulted read-only before its migration still
reads its history. Links are written in the same flush as their event, under
the writer lock SQLite already holds for that insert, so two transactions
cannot chain onto the same predecessor.
"""
from __future__ import annotations

import hashlib
import json
import weakref
from datetime import datetime

from sqlalchemy import DDL, event, text
from sqlalchemy.orm import Session

CHAIN_VERSION = "audit-chain-v1"
FIELDS = ("action", "object_type", "object_id", "actor_user_id", "actor_type", "result",
          "before_json", "after_json", "reason", "data_source", "correlation_id",
          "metadata_json", "created_at")


def _stamp(value):
    # SQLAlchemy stores SQLite datetimes as text; a raw insert may store ISO.
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%Y-%m-%d %H:%M:%S.%f") if value is not None else None


def link_hash(previous: str | None, values) -> str:
    content = {name: (_stamp(values[name]) if name == "created_at" else values[name]) for name in FIELDS}
    payload = json.dumps([CHAIN_VERSION, previous, content], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Triggers ───────────────────────────────────────────────────────

def statements() -> list[str]:
    commands = []
    for table, label in (("audit_events", "Le journal d''audit"), ("audit_chain", "Le chaînage du journal d''audit")):
        for action in ("UPDATE", "DELETE"):
            commands.append(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
            BEFORE {action} ON {table} BEGIN
            SELECT RAISE(ABORT, '{label} est en ajout seul.'); END""")
    return commands


def register(events_table, chain_table) -> None:
    for sql in statements():
        target = events_table if " ON audit_events " in sql else chain_table
        event.listen(target, "after_create", DDL(sql).execute_if(dialect="sqlite"))


# ── Chaining new events ────────────────────────────────────────────

_chained_binds: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _has_chain(connection) -> bool:
    # A test may create only some tables: no chain table, nothing to chain.
    engine = connection.engine
    known = _chained_binds.get(engine)
    if not known:
        known = connection.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_chain'")).first() is not None
        if known:
            _chained_binds[engine] = True
    return known


def _chain_new_events(session: Session, _context) -> None:
    from .models import AuditEvent
    events = sorted((obj for obj in session.new if isinstance(obj, AuditEvent)), key=lambda e: e.id)
    if not events:
        return
    connection = session.connection()
    if connection.dialect.name != "sqlite" or not _has_chain(connection):
        return
    previous = connection.execute(text(
        "SELECT row_hash FROM audit_chain ORDER BY event_id DESC LIMIT 1")).scalar()
    now = datetime.utcnow()
    for item in events:
        digest = link_hash(previous, {name: getattr(item, name) for name in FIELDS})
        connection.execute(text("INSERT INTO audit_chain (event_id, prev_hash, row_hash, sealed_at) "
                                "VALUES (:id, :prev, :hash, :at)"),
                           dict(id=item.id, prev=previous, hash=digest, at=now))
        previous = digest


event.listen(Session, "after_flush", _chain_new_events)


# ── Upgrade and verification ───────────────────────────────────────

_ROWS = ("SELECT e.id, " + ", ".join(f"e.{name}" for name in FIELDS)
         + ", c.prev_hash, c.row_hash FROM audit_events e "
           "LEFT JOIN audit_chain c ON c.event_id = e.id ORDER BY e.id")


def _rows(conn):
    for row in conn.execute(text(_ROWS)).mappings():
        yield row


def seal(conn) -> int:
    """Chain every event that has no link yet: the history before this
    version, or an event a raw SQL insert wrote. Returns how many."""
    previous, sealed = None, 0
    now = datetime.utcnow()
    for row in list(_rows(conn)):
        if row["row_hash"] is not None:
            previous = row["row_hash"]
            continue
        digest = link_hash(previous, row)
        conn.execute(text("INSERT INTO audit_chain (event_id, prev_hash, row_hash, sealed_at) "
                          "VALUES (:id, :prev, :hash, :at)"),
                     dict(id=row["id"], prev=previous, hash=digest, at=now))
        previous, sealed = digest, sealed + 1
    return sealed


def migrate(conn) -> int:
    """Triggers and links for a database created before this version."""
    tables = {row[0] for row in conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('audit_events','audit_chain')"))}
    if tables != {"audit_events", "audit_chain"}:
        return 0
    for sql in statements():
        conn.execute(text(sql))
    return seal(conn)


def verify_chain(conn) -> dict:
    """Recompute the chain. `ok` is false at the first link that does not
    match its event and predecessor, or when an event has no link."""
    previous, checked, unchained = None, 0, []
    for row in _rows(conn):
        if row["row_hash"] is None:
            unchained.append(row["id"])
            continue
        checked += 1
        if row["prev_hash"] != previous or row["row_hash"] != link_hash(previous, row):
            return dict(ok=False, checked=checked, first_broken_event_id=row["id"],
                        unchained_event_ids=unchained[:20], version=CHAIN_VERSION)
        previous = row["row_hash"]
    return dict(ok=not unchained, checked=checked, first_broken_event_id=None,
                unchained_event_ids=unchained[:20], version=CHAIN_VERSION)
