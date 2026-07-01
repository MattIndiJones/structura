"""Deal booking and lifecycle management."""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, DealEvent, Entity, User
from .auth import get_current_user
from ..services.market_data import load_hist_prices

router = APIRouter(prefix="/api/deals", tags=["deals"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class DealCreate(BaseModel):
    sens: str = "vente"
    contrepartie: str
    devise: str = "EUR"
    nominal: float
    fair_value: float
    price_traded: float
    trade_date: str
    strike_date: str
    value_date: str
    maturity_date: str
    T: float
    underlyings: List[dict]          # [{name, ticker, s0_abs}]
    observation_times: List[float]   # unique AT times in years from value_date
    script_snapshot: str
    script_id: Optional[int] = None
    market_snapshot: dict = {}


class DealUpdate(BaseModel):
    status: Optional[str] = None
    contrepartie: Optional[str] = None
    price_traded: Optional[float] = None
    nominal: Optional[float] = None


class EventUpdate(BaseModel):
    spots: dict
    source: str = "manuel"
    status: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────

def _date_plus_years(d: str, years: float) -> str:
    return (date.fromisoformat(d) + timedelta(days=round(years * 365.25))).isoformat()


def _gen_ref(entity_name: str | None, session: Session) -> str:
    prefix = ((entity_name or "DEAL")[:4].upper().replace(" ", "").ljust(4, "X"))
    today_str = date.today().strftime("%Y%m%d")
    existing = session.exec(
        select(Deal).where(Deal.reference.startswith(f"{prefix}-{today_str}-"))
    ).all()
    return f"{prefix}-{today_str}-{len(existing) + 1:03d}"


def _deal_row(d: Deal, events: list | None = None) -> dict:
    row = {
        "id": d.id,
        "reference": d.reference,
        "entity_id": d.entity_id,
        "user_id": d.user_id,
        "sens": d.sens,
        "contrepartie": d.contrepartie,
        "devise": d.devise,
        "nominal": d.nominal,
        "fair_value": d.fair_value,
        "price_traded": d.price_traded,
        "margin": round(d.price_traded - d.fair_value, 4),
        "trade_date": d.trade_date,
        "strike_date": d.strike_date,
        "value_date": d.value_date,
        "maturity_date": d.maturity_date,
        "T": d.T,
        "underlyings": json.loads(d.underlyings_json),
        "market_snapshot": json.loads(d.market_snapshot_json),
        "status": d.status,
        "script_id": d.script_id,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
    if events is not None:
        row["events"] = [_event_row(e) for e in events]
    return row


def _event_row(e: DealEvent) -> dict:
    return {
        "id": e.id,
        "deal_id": e.deal_id,
        "event_index": e.event_index,
        "event_date": e.event_date,
        "t_years": e.t_years,
        "spots": json.loads(e.spots_json),
        "source": e.source,
        "status": e.status,
        "label": e.label,
    }


def _get_events(deal_id: int, session: Session) -> list:
    return session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal_id)
        .order_by(DealEvent.event_index)
    ).all()


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/next-ref")
def next_ref(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    return {"reference": _gen_ref(entity.name if entity else None, session)}


@router.post("", status_code=201)
def book_deal(
    body: DealCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    reference = _gen_ref(entity.name if entity else None, session)

    deal = Deal(
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        script_snapshot=body.script_snapshot,
        script_id=body.script_id,
        sens=body.sens,
        contrepartie=body.contrepartie,
        devise=body.devise,
        nominal=body.nominal,
        fair_value=body.fair_value,
        price_traded=body.price_traded,
        trade_date=body.trade_date,
        strike_date=body.strike_date,
        value_date=body.value_date,
        maturity_date=body.maturity_date,
        T=body.T,
        underlyings_json=json.dumps(body.underlyings),
        market_snapshot_json=json.dumps(body.market_snapshot),
    )
    session.add(deal)
    session.flush()

    today = date.today().isoformat()

    # First event is always the strike date (t=0) — S₀ to be filled in Events tab
    session.add(DealEvent(
        deal_id=deal.id,
        event_index=0,
        event_date=body.strike_date,
        t_years=0.0,
        spots_json="{}",
        source="pending",
        status="observé" if body.strike_date <= today else "futur",
        label="Strike / Fixing S₀",
    ))

    # Subsequent observation events (indexed from 1)
    times = sorted(set(body.observation_times))
    for idx, t in enumerate(times):
        ev_date = _date_plus_years(body.value_date, t)
        is_maturity = (idx == len(times) - 1)
        label = "Maturité" if is_maturity else f"Obs. {idx + 1} ({t:.2f}Y)"
        session.add(DealEvent(
            deal_id=deal.id,
            event_index=idx + 1,
            event_date=ev_date,
            t_years=round(t, 4),
            spots_json="{}",
            source="pending",
            status="observé" if ev_date <= today else "futur",
            label=label,
        ))

    session.commit()
    session.refresh(deal)
    return _deal_row(deal, _get_events(deal.id, session))


@router.get("")
def list_deals(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id)
        .order_by(Deal.created_at.desc())
    ).all()
    return [_deal_row(d) for d in deals]


@router.get("/{deal_id}")
def get_deal(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    return _deal_row(deal, _get_events(deal_id, session))


@router.patch("/{deal_id}")
def update_deal(
    deal_id: int,
    body: DealUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(deal, field, value)
    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return _deal_row(deal)


@router.patch("/{deal_id}/events/{event_id}")
def update_event(
    deal_id: int,
    event_id: int,
    body: EventUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    ev = session.get(DealEvent, event_id)
    if not ev or ev.deal_id != deal_id:
        raise HTTPException(404, "Événement introuvable")

    ev.spots_json = json.dumps(body.spots)
    ev.source = body.source
    if body.status:
        ev.status = body.status
    elif ev.status == "futur":
        ev.status = "observé"
    session.add(ev)

    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return _event_row(ev)


@router.post("/{deal_id}/events/refresh")
def refresh_events(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Auto-fetch historical spots from Yahoo Finance for past events."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")

    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")

    today = date.today().isoformat()
    events = _get_events(deal_id, session)
    past_events = [e for e in events if e.event_date <= today]
    if not past_events:
        return {"updated": 0, "message": "Aucun événement passé"}

    px_data = load_hist_prices(tickers, deal.strike_date, today)
    if "error" in px_data:
        raise HTTPException(422, px_data["error"])

    dates_list = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    if not dates_list:
        raise HTTPException(422, "Données historiques vides")

    # Build a {date: idx} map for fast lookup
    date_idx = {d: i for i, d in enumerate(dates_list)}

    def _closest_price(ticker: str, target_date: str) -> float | None:
        if ticker not in prices:
            return None
        available = [d for d in dates_list if d <= target_date]
        if not available:
            return None
        idx = date_idx[available[-1]]
        val = prices[ticker][idx]
        return round(float(val), 4) if val is not None else None

    updated = 0
    for ev in past_events:
        spots = {}
        for u in underlyings:
            tk = u.get("ticker", "")
            name = u["name"]
            spot = _closest_price(tk, ev.event_date) if tk else None
            if spot is not None:
                spots[name] = spot
        if spots:
            ev.spots_json = json.dumps(spots)
            ev.source = "auto"
            if ev.status == "futur":
                ev.status = "observé"
            session.add(ev)
            updated += 1

    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return {"updated": updated, "message": f"{updated} événement(s) mis à jour"}


@router.get("/{deal_id}/reprice")
def reprice_inputs(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Return normalized inputs for re-pricing the deal at current market conditions."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")

    today = date.today()
    maturity = date.fromisoformat(deal.maturity_date)
    value_d = date.fromisoformat(deal.value_date)

    T_remaining = max(0.0, (maturity - today).days / 365.25)
    T_elapsed = max(0.0, (today - value_d).days / 365.25)

    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]

    # S₀ comes from the t=0 event (Strike / Fixing S₀), filled in by the user in Events tab
    events = _get_events(deal_id, session)
    strike_event = next((e for e in events if e.t_years == 0.0), None)
    s0_map: dict = json.loads(strike_event.spots_json) if strike_event else {}

    normalized_spots: dict = {}
    current_spots: dict = {}

    if tickers:
        px_data = load_hist_prices(tickers, today.isoformat(), today.isoformat())
        if "error" not in px_data:
            prices = px_data.get("prices", {})
            for u in underlyings:
                tk = u.get("ticker", "")
                name = u["name"]
                s0 = s0_map.get(name, 0.0)
                if tk and tk in prices and prices[tk]:
                    s_current = float(prices[tk][-1])
                    current_spots[name] = round(s_current, 4)
                    if s0 > 0:
                        normalized_spots[name] = round(s_current / s0, 6)

    realized = [
        {
            "event_date": e.event_date,
            "t_years": e.t_years,
            "spots": json.loads(e.spots_json),
            "label": e.label,
        }
        for e in events
        if e.status in ("observé", "callé", "ki") and json.loads(e.spots_json)
    ]

    return {
        "deal_id": deal_id,
        "reference": deal.reference,
        "T_remaining": round(T_remaining, 4),
        "T_elapsed": round(T_elapsed, 4),
        "maturity_date": deal.maturity_date,
        "value_date": deal.value_date,
        "normalized_spots": normalized_spots,
        "current_spots": current_spots,
        "realized_events": realized,
        "script_snapshot": deal.script_snapshot,
        "market_snapshot": json.loads(deal.market_snapshot_json),
    }
