"""RFQ (request-for-quote) tracker: collect and compare bank quotes for a
structured product against Structura's own model price."""
from __future__ import annotations
import json
from datetime import date, datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import RfqRequest, RfqQuote, RfqProvider, User
from .auth import get_current_user

router = APIRouter(prefix="/api/rfq", tags=["rfq"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class RfqCreate(BaseModel):
    name: str
    ao_date: Optional[str] = None  # ISO date; defaults to today if omitted
    template_type: str = ""
    script_id: Optional[int] = None
    script_snapshot: str
    params: dict = {}


class RfqUpdate(BaseModel):
    name: Optional[str] = None
    ao_date: Optional[str] = None
    params: Optional[dict] = None
    status: Optional[str] = None
    model_price: Optional[float] = None


class QuoteCreate(BaseModel):
    provider: str = "manuel"
    contact: Optional[str] = None
    note: Optional[str] = None


class QuoteUpdate(BaseModel):
    price: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None
    quoted_at: Optional[str] = None  # ISO datetime string


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_ref(session: Session) -> str:
    today_str = date.today().strftime("%Y%m%d")
    existing = session.exec(
        select(RfqRequest).where(RfqRequest.reference.startswith(f"RFQ-{today_str}-"))
    ).all()
    return f"RFQ-{today_str}-{len(existing) + 1:03d}"


def _rfq_row(r: RfqRequest, quotes: list | None = None) -> dict:
    row = {
        "id": r.id,
        "reference": r.reference,
        "entity_id": r.entity_id,
        "user_id": r.user_id,
        "name": r.name,
        "ao_date": r.ao_date,
        "template_type": r.template_type,
        "script_id": r.script_id,
        "script_snapshot": r.script_snapshot,
        "params": json.loads(r.params_json),
        "model_price": r.model_price,
        "model_price_at": r.model_price_at.isoformat() if r.model_price_at else None,
        "status": r.status,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
    if quotes is not None:
        row["quotes"] = [_quote_row(q) for q in quotes]
    return row


def _quote_row(q: RfqQuote) -> dict:
    return {
        "id": q.id,
        "rfq_id": q.rfq_id,
        "provider": q.provider,
        "contact": q.contact,
        "price": q.price,
        "currency": q.currency,
        "status": q.status,
        "note": q.note,
        "quoted_at": q.quoted_at.isoformat() if q.quoted_at else None,
        "created_at": q.created_at.isoformat(),
    }


def _get_quotes(rfq_id: int, session: Session) -> list:
    return session.exec(
        select(RfqQuote).where(RfqQuote.rfq_id == rfq_id)
        .order_by(RfqQuote.created_at)
    ).all()


def _get_owned(rfq_id: int, current: User, session: Session) -> RfqRequest:
    r = session.get(RfqRequest, rfq_id)
    if not r or r.user_id != current.id:
        raise HTTPException(404, "RFQ introuvable")
    return r


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/providers")
def list_providers(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    providers = session.exec(
        select(RfqProvider).where(RfqProvider.active == True)  # noqa: E712
        .order_by(RfqProvider.label)
    ).all()
    return [{"id": p.id, "label": p.label, "mode": p.mode} for p in providers]


@router.post("", status_code=201)
def create_rfq(
    body: RfqCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    reference = _gen_ref(session)
    rfq = RfqRequest(
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        name=body.name.strip(),
        ao_date=body.ao_date or date.today().isoformat(),
        template_type=body.template_type,
        script_id=body.script_id,
        script_snapshot=body.script_snapshot,
        params_json=json.dumps(body.params),
    )
    session.add(rfq)
    session.commit()
    session.refresh(rfq)
    return _rfq_row(rfq, [])


@router.get("")
def list_rfqs(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfqs = session.exec(
        select(RfqRequest).where(RfqRequest.user_id == current.id)
        .order_by(RfqRequest.created_at.desc())
    ).all()
    return [_rfq_row(r) for r in rfqs]


@router.get("/history")
def rfq_history(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Flat list of priced quotes joined with their RFQ, for the counterparty
    analysis view. No server-side aggregation — volumes are small, the
    frontend filters/groups by provider and product type."""
    rows = session.exec(
        select(RfqQuote, RfqRequest)
        .join(RfqRequest, RfqQuote.rfq_id == RfqRequest.id)
        .where(RfqRequest.user_id == current.id)
        .where(RfqQuote.price.is_not(None))
    ).all()
    return [
        {
            "quote_id": q.id,
            "rfq_id": rfq.id,
            "reference": rfq.reference,
            "template_type": rfq.template_type,
            "provider": q.provider,
            "price": q.price,
            "model_price": rfq.model_price,
            "spread_bps": round((q.price - rfq.model_price) / rfq.model_price * 10000, 1)
                          if rfq.model_price else None,
            "date": (q.quoted_at or q.created_at).isoformat(),
            "status": q.status,
        }
        for q, rfq in rows
    ]


@router.get("/{rfq_id}")
def get_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    return _rfq_row(rfq, _get_quotes(rfq_id, session))


@router.patch("/{rfq_id}")
def update_rfq(
    rfq_id: int,
    body: RfqUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    data = body.model_dump(exclude_unset=True)
    if "params" in data:
        rfq.params_json = json.dumps(data.pop("params"))
    if "model_price" in data:
        rfq.model_price = data.pop("model_price")
        rfq.model_price_at = datetime.utcnow()
    for field, value in data.items():
        if value is not None:
            setattr(rfq, field, value)
    rfq.updated_at = datetime.utcnow()
    session.add(rfq)
    session.commit()
    return _rfq_row(rfq, _get_quotes(rfq_id, session))


@router.delete("/{rfq_id}", status_code=204)
def delete_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    for q in _get_quotes(rfq_id, session):
        session.delete(q)
    session.delete(rfq)
    session.commit()


@router.post("/{rfq_id}/quotes", status_code=201)
def add_quote(
    rfq_id: int,
    body: QuoteCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    _get_owned(rfq_id, current, session)
    q = RfqQuote(
        rfq_id=rfq_id,
        provider=body.provider,
        contact=body.contact,
        note=body.note,
    )
    session.add(q)
    session.commit()
    session.refresh(q)
    return _quote_row(q)


@router.patch("/{rfq_id}/quotes/{quote_id}")
def update_quote(
    rfq_id: int,
    quote_id: int,
    body: QuoteUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    _get_owned(rfq_id, current, session)
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    data = body.model_dump(exclude_unset=True)
    if "quoted_at" in data and data["quoted_at"]:
        data["quoted_at"] = datetime.fromisoformat(data["quoted_at"])
    for field, value in data.items():
        setattr(q, field, value)
    session.add(q)
    session.commit()
    return _quote_row(q)


@router.delete("/{rfq_id}/quotes/{quote_id}", status_code=204)
def delete_quote(
    rfq_id: int,
    quote_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    _get_owned(rfq_id, current, session)
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    session.delete(q)
    session.commit()
