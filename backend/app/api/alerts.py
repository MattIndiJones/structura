"""Lifecycle/barrier alerts raised by the daily refresh — list, mark read,
and manual whole-book refresh (the UI's 'Rafraîchir le book' button)."""
from __future__ import annotations
import json
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Alert, AlertRead, Deal, SchedulerRun, User
from .auth import get_current_admin, get_current_user
from ..services.lifecycle_alerts import refresh_book
from ..services.business_access import can_read_deal

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _admin(current: User) -> bool:
    return getattr(current, "role", None) == "admin"


def _visible_alerts(current: User, session: Session):
    ids = [d.id for d in session.exec(select(Deal)).all() if can_read_deal(d, current, session)]
    return select(Alert).where(Alert.deal_id.in_(ids) | (
        Alert.deal_id.is_(None) & (Alert.user_id == current.id)))


def _unread(current):
    acknowledged = select(AlertRead.alert_id).where(
        AlertRead.alert_id == Alert.id, AlertRead.user_id == current.id).exists()
    return ((Alert.user_id == current.id) & (Alert.read == False)) | (  # noqa: E712
        (Alert.user_id != current.id) & ~acknowledged)


def _mark_read(alert, current, session):
    if alert.user_id == current.id:
        alert.read = True
        session.add(alert)
    elif session.get(AlertRead, (alert.id, current.id)) is None:
        session.add(AlertRead(alert_id=alert.id, user_id=current.id))


def _alert_row(a: Alert, current: User, session: Session) -> dict:
    return {
        "id": a.id,
        "deal_id": a.deal_id,
        "deal_reference": a.deal_reference,
        "kind": a.kind,
        "message": a.message,
        "read": a.read if a.user_id == current.id else session.get(AlertRead, (a.id, current.id)) is not None,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/scheduler-runs")
def list_scheduler_runs(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = 30,
):
    rows = session.exec(
        select(SchedulerRun).order_by(SchedulerRun.scheduled_for.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return [{
        "id": row.id, "job_key": row.job_key,
        "scheduled_for": row.scheduled_for.isoformat(),
        "timezone": row.timezone, "status": row.status,
        "trigger": row.trigger, "error": row.error,
        "result": json.loads(row.result_json or "{}"),
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    } for row in rows]


@router.get("")
def list_alerts(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    unread_only: bool = False,
    limit: int = 100,
):
    q = _visible_alerts(current, session)
    if unread_only:
        q = q.where(_unread(current))
    rows = session.exec(q.order_by(Alert.created_at.desc()).limit(limit)).all()
    unread = len(session.exec(
        _visible_alerts(current, session).where(_unread(current))
    ).all())
    return {"unread": unread, "alerts": [_alert_row(a, current, session) for a in rows]}


@router.post("/{alert_id}/read")
def mark_read(
    alert_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    alert = session.get(Alert, alert_id)
    if not alert or (alert.deal_id is None and alert.user_id != current.id) or (
            alert.deal_id is not None and not can_read_deal(session.get(Deal, alert.deal_id), current, session)):
        raise HTTPException(404, "Alerte introuvable")
    _mark_read(alert, current, session)
    session.commit()
    return _alert_row(alert, current, session)


@router.post("/read-all")
def mark_all_read(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.exec(
        _visible_alerts(current, session).where(_unread(current))
    ).all()
    for a in rows:
        _mark_read(a, current, session)
    session.commit()
    return {"marked": len(rows)}


@router.post("/refresh-book")
def refresh_whole_book(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Refresh only contracts visible to the effective identity."""
    return refresh_book(session, current=current)
