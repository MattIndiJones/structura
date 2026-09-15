"""Per-day sequential business references (RFQ-20260730-001, DEMO-20260730-002…).

Shared by the three tables that hand out such references — deals, indicatives
and RFQs — because they had three copies of the same routine and all three
carried the same defect: numbering by COUNTING the existing rows. Create 001
and 002, delete 001, create again → count is 1, so the new row is handed 002 a
second time. On an RFQ that reference is the best-execution trail of a tender;
on a deal it is what the client sees on a valuation note. Numbering off the
highest suffix already handed out never reuses one, whatever gets deleted.

Allocation is persisted in a dedicated counter row and incremented through a
single SQLite UPSERT, so concurrent writers serialize on that row. Unique
indexes remain the final structural guard.
"""
from __future__ import annotations
from sqlalchemy import func, text
from sqlmodel import Session, select

from ..db.models import AuditEvent


def next_reference(session: Session, model, prefix: str) -> str:
    """`prefix` carries everything up to the counter, trailing dash included
    (e.g. "RFQ-20260730-"). Returns prefix + the next free 3-digit suffix."""
    rows = session.exec(
        select(model.reference).where(model.reference.startswith(prefix))
    ).all()
    highest = 0
    for ref in rows:
        suffix = (ref or "")[len(prefix):]
        # Anything that isn't a plain counter (a manually edited reference,
        # a legacy format) is ignored rather than crashing the booking.
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    initial = highest + 1
    allocated = session.execute(text("""
        INSERT INTO reference_counters(prefix, last_value)
        VALUES (:prefix, :initial)
        ON CONFLICT(prefix) DO UPDATE SET last_value =
            CASE
                WHEN reference_counters.last_value < :highest THEN :initial
                ELSE reference_counters.last_value + 1
            END
        RETURNING last_value
    """), {"prefix": prefix, "initial": initial, "highest": highest}).scalar_one()
    return f"{prefix}{int(allocated):03d}"


def next_audited_id(session: Session, model, object_type: str) -> int:
    """Allocate a durable numeric identity for an audited business object.

    SQLite normally reuses an INTEGER PRIMARY KEY after physical deletion.
    Audit rows are append-only and refer to that key, so reuse would attach an
    old RFQ's history to a new RFQ.  The shared counter starts above both the
    live table and the append-only audit trail and never moves backwards.
    """
    table_highest = session.exec(select(func.max(model.id))).one() or 0
    audit_highest = session.exec(
        select(func.max(AuditEvent.object_id)).where(
            AuditEvent.object_type == object_type)
    ).one() or 0
    highest = max(int(table_highest), int(audit_highest))
    counter_key = f"pk:{model.__tablename__}:{object_type}"
    return int(session.execute(text("""
        INSERT INTO reference_counters(prefix, last_value)
        VALUES (:prefix, :initial)
        ON CONFLICT(prefix) DO UPDATE SET last_value =
            CASE
                WHEN reference_counters.last_value < :highest THEN :initial
                ELSE reference_counters.last_value + 1
            END
        RETURNING last_value
    """), {
        "prefix": counter_key,
        "initial": highest + 1,
        "highest": highest,
    }).scalar_one())
