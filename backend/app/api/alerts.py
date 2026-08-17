"""Lifecycle/barrier alerts raised by the daily refresh — list, mark read,
and manual whole-book refresh (the UI's 'Rafraîchir le book' button)."""
from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Alert, User
from .auth import get_current_user
from ..services.lifecycle_alerts import refresh_book

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _admin(current: User) -> bool:
    return getattr(current, "role", None) == "admin"


def _visible_alerts(current: User):
    statement = select(Alert)
    return statement if _admin(current) else statement.where(Alert.user_id == current.id)


def _alert_row(a: Alert) -> dict:
    return {
        "id": a.id,
        "deal_id": a.deal_id,
        "deal_reference": a.deal_reference,
        "kind": a.kind,
        "message": a.message,
        "read": a.read,
        "created_at": a.created_at.isoformat(),
    }


@router.get("")
def list_alerts(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    unread_only: bool = False,
    limit: int = 100,
):
    q = _visible_alerts(current)
    if unread_only:
        q = q.where(Alert.read == False)   # noqa: E712
    rows = session.exec(q.order_by(Alert.created_at.desc()).limit(limit)).all()
    unread = len(session.exec(
        _visible_alerts(current).where(Alert.read == False)   # noqa: E712
    ).all())
    return {"unread": unread, "alerts": [_alert_row(a) for a in rows]}


@router.post("/{alert_id}/read")
def mark_read(
    alert_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    alert = session.get(Alert, alert_id)
    if not alert or (not _admin(current) and alert.user_id != current.id):
        raise HTTPException(404, "Alerte introuvable")
    alert.read = True
    session.add(alert)
    session.commit()
    return _alert_row(alert)


@router.post("/read-all")
def mark_all_read(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.exec(
        _visible_alerts(current).where(Alert.read == False)   # noqa: E712
    ).all()
    for a in rows:
        a.read = True
        session.add(a)
    session.commit()
    return {"marked": len(rows)}


@router.post("/refresh-book")
def refresh_whole_book(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Same pass as the nightly scheduler.

    Administrators operate the full book they can see (including UAT deals
    owned by the selected target user); regular users keep an owner-only pass.
    """
    return refresh_book(session, user_id=None if _admin(current) else current.id)
