"""Pre-trade pricing opportunities — the stage before a Deal exists.

An Indicative is what KID/EMT attach to while a product is still being
discussed with a client (no trade yet, so no Deal row). If it converts,
the resulting Deal keeps a permanent pointer back via Deal.indicative_id —
the Indicative's own id never changes and its KID/EMT records are never
re-keyed. See db/models.py:Indicative for the full rationale.
"""
from __future__ import annotations
import json
from datetime import datetime, date
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Indicative, Entity, User, Deal
from .auth import get_current_user

router = APIRouter(prefix="/api/indicatives", tags=["indicatives"])


class IndicativeCreate(BaseModel):
    contrepartie: str = ""
    devise: str = "EUR"
    nominal: float = 0.0
    underlyings: List[dict] = []
    script_snapshot: str
    script_id: Optional[int] = None
    market_snapshot: dict = {}


class IndicativeUpdate(BaseModel):
    status: Optional[str] = None
    contrepartie: Optional[str] = None
    nominal: Optional[float] = None
    script_snapshot: Optional[str] = None
    underlyings: Optional[List[dict]] = None
    market_snapshot: Optional[dict] = None


def _gen_ref(entity_name: str | None, session: Session) -> str:
    prefix = ((entity_name or "IND")[:4].upper().replace(" ", "").ljust(4, "X"))
    today_str = date.today().strftime("%Y%m%d")
    existing = session.exec(
        select(Indicative).where(Indicative.reference.startswith(f"{prefix}-IND-{today_str}-"))
    ).all()
    return f"{prefix}-IND-{today_str}-{len(existing) + 1:03d}"


def _row(i: Indicative) -> dict:
    return {
        "id": i.id,
        "reference": i.reference,
        "entity_id": i.entity_id,
        "user_id": i.user_id,
        "contrepartie": i.contrepartie,
        "devise": i.devise,
        "nominal": i.nominal,
        "underlyings": json.loads(i.underlyings_json),
        "market_snapshot": json.loads(i.market_snapshot_json),
        "script_snapshot": i.script_snapshot,
        "script_id": i.script_id,
        "status": i.status,
        "created_at": i.created_at.isoformat(),
        "updated_at": i.updated_at.isoformat(),
    }


@router.post("", status_code=201)
def create_indicative(
    body: IndicativeCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    reference = _gen_ref(entity.name if entity else None, session)

    ind = Indicative(
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        script_snapshot=body.script_snapshot,
        script_id=body.script_id,
        contrepartie=body.contrepartie,
        devise=body.devise,
        nominal=body.nominal,
        underlyings_json=json.dumps(body.underlyings),
        market_snapshot_json=json.dumps(body.market_snapshot),
    )
    session.add(ind)
    session.commit()
    session.refresh(ind)
    return _row(ind)


@router.get("")
def list_indicatives(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.exec(
        select(Indicative).where(Indicative.user_id == current.id)
        .order_by(Indicative.created_at.desc())
    ).all()
    return [_row(i) for i in rows]


@router.get("/{indicative_id}")
def get_indicative(
    indicative_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")
    return _row(ind)


@router.patch("/{indicative_id}")
def update_indicative(
    indicative_id: int,
    body: IndicativeUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")

    data = body.model_dump(exclude_unset=True)
    if "underlyings" in data:
        ind.underlyings_json = json.dumps(data.pop("underlyings"))
    if "market_snapshot" in data:
        ind.market_snapshot_json = json.dumps(data.pop("market_snapshot"))
    for field, value in data.items():
        if value is not None:
            setattr(ind, field, value)

    ind.updated_at = datetime.utcnow()
    session.add(ind)
    session.commit()
    return _row(ind)


@router.get("/{indicative_id}/deal")
def get_linked_deal(
    indicative_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """The Deal this indicative converted into, if any — null while still open."""
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")
    deal = session.exec(select(Deal).where(Deal.indicative_id == indicative_id)).first()
    return {"deal_id": deal.id if deal else None, "reference": deal.reference if deal else None}
