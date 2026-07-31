"""Persistent business audit helpers.

Accepted critical actions call ``record_audit_event`` before their normal
transaction commit.  Rejected actions call ``commit_rejection`` before raising
the HTTP/domain error.  If the audit insert itself fails, the critical action
must fail as well: there is deliberately no best-effort logging path here.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlmodel import Session

from ..db.models import AuditEvent


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _dump(value: Any) -> str:
    if value is None:
        value = {}
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=_json_default)


def record_audit_event(
    session: Session,
    *,
    action: str,
    object_type: str,
    object_id: int | None,
    actor_user_id: int | None,
    result: str,
    actor_type: str = "USER",
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
    data_source: str | None = None,
    correlation_id: str | None = None,
    metadata: Any = None,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        object_type=object_type,
        object_id=object_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        result=result,
        before_json=_dump(before),
        after_json=_dump(after),
        reason=reason,
        data_source=data_source,
        correlation_id=correlation_id,
        metadata_json=_dump(metadata),
    )
    session.add(event)
    return event

def commit_rejection(session: Session, **kwargs) -> AuditEvent:
    """Persist a refusal before the caller returns/raises it."""
    event = record_audit_event(session, result="REJECTED", **kwargs)
    session.commit()
    session.refresh(event)
    return event
