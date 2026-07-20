"""Deal booking and lifecycle management."""
from __future__ import annotations
import json
import re
from datetime import datetime, date, timedelta
from typing import Annotated, Literal, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, DealEvent, Entity, User, Counterparty
from .auth import get_current_user
from ..services.market_data import load_hist_prices
from ..core.payscript.parser import parse_script, resolve_constats, CompiledScript, effective_T_max
from ..core.payscript.engine import eval_script_on_history
from ..core.calibration import realized_market
from ..core.schemas import ReinvestScanRequest, ReinvestProposalRequest

router = APIRouter(prefix="/api/deals", tags=["deals"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class DealCreate(BaseModel):
    sens: str = "vente"
    contrepartie: str
    devise: str = "EUR"
    product_type: str = ""
    nominal: float
    fair_value: float
    price_traded: float
    trade_date: str
    strike_date: str
    value_date: str
    maturity_date: str
    payment_date: str = ""
    T: float
    underlyings: List[dict]          # [{name, ticker, s0_abs}]
    observation_times: List[float]   # unique AT times in years from value_date
    script_snapshot: str
    script_id: Optional[int] = None
    market_snapshot: dict = {}
    # Pre-trade opportunity this deal converts from, if any — see
    # db/models.py:Deal.indicative_id.
    indicative_id: Optional[int] = None


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
        "indicative_id": d.indicative_id,
        "sens": d.sens,
        "contrepartie": d.contrepartie,
        "devise": d.devise,
        "product_type": d.product_type,
        "nominal": d.nominal,
        "fair_value": d.fair_value,
        "price_traded": d.price_traded,
        "margin": round(d.price_traded - d.fair_value, 4),
        "trade_date": d.trade_date,
        "strike_date": d.strike_date,
        "value_date": d.value_date,
        "maturity_date": d.maturity_date,
        "payment_date": d.payment_date,
        "T": d.T,
        "realized_payout": d.realized_payout,
        "resolution_outcome": d.resolution_outcome,
        "underlyings": json.loads(d.underlyings_json),
        "market_snapshot": json.loads(d.market_snapshot_json),
        "status": d.status,
        "script_id": d.script_id,
        "script_snapshot": d.script_snapshot,
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
        indicative_id=body.indicative_id,
        script_snapshot=body.script_snapshot,
        script_id=body.script_id,
        sens=body.sens,
        contrepartie=body.contrepartie,
        devise=body.devise,
        product_type=body.product_type,
        nominal=body.nominal,
        fair_value=body.fair_value,
        price_traded=body.price_traded,
        trade_date=body.trade_date,
        strike_date=body.strike_date,
        value_date=body.value_date,
        maturity_date=body.maturity_date,
        payment_date=body.payment_date,
        T=body.T,
        underlyings_json=json.dumps(body.underlyings),
        market_snapshot_json=json.dumps(body.market_snapshot),
    )
    session.add(deal)
    session.flush()

    if body.indicative_id:
        from ..db.models import Indicative
        ind = session.get(Indicative, body.indicative_id)
        if ind and ind.user_id == current.id:
            ind.status = "converti"
            ind.updated_at = datetime.utcnow()
            session.add(ind)

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


def _classify_param_barrier(name: str, val: float) -> str | None:
    """Heuristic barrier detection on PARAM names. PayScript has no formal
    'this is a barrier' concept — AC_BAR/KI_BAR are naming conventions from
    our templates, nothing more. Name matching + a plausibility range on the
    stored value (fraction of S₀) is the honest best effort: it covers the
    standard templates, an unusually-named script slips through silently.
    KI is checked first so 'KI_BAR' lands on ki, not autocall."""
    if not (0.2 <= val <= 3.0):
        return None
    n = name.upper()
    if "KI" in n or "KNOCK" in n:
        return "ki"
    if "AC" in n or "CALL" in n or "BAR" in n:
        return "autocall"
    return None


# Eligible counterparties for the booking form — any authenticated user (the
# admin CRUD lives in api/admin.py). Only active ones: eligibility is the
# whole point of the list.
# NOTE: declared before GET /{deal_id} on purpose — FastAPI matches routes in
# declaration order, and a literal path segment must not be captured as a
# deal_id (same reason as /watchlist below).
@router.get("/counterparties")
def eligible_counterparties(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    cptys = session.exec(
        select(Counterparty).where(Counterparty.active == True)   # noqa: E712
        .order_by(Counterparty.name)
    ).all()
    return [{"id": c.id, "name": c.name, "country": c.country} for c in cptys]


# NOTE: declared before GET /{deal_id} on purpose — FastAPI matches routes in
# declaration order, and "watchlist" must not be captured as a deal_id.
@router.get("/watchlist")
def watchlist(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Barrier-proximity watchlist over the user's ACTIVE deals: for each,
    the next observation date, the current worst-of performance vs S₀, and
    the gap (in points of S₀) to every barrier-looking PARAM in the booked
    script. Sorted most-urgent first (smallest barrier gap, then nearest
    observation). Uses the script's PARAM defaults — user overrides typed in
    the UI at pricing time are not persisted on the deal (known limitation)."""
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    today = date.today()
    rows = [build_watchlist_row(deal, session, today) for deal in deals]

    rows.sort(key=lambda r: (
        r["min_gap"] if r["min_gap"] is not None else 1e9,
        r["days_to_next"] if r["days_to_next"] is not None else 1e9,
    ))
    return rows


def build_watchlist_row(deal: Deal, session: Session, today: date) -> dict:
    """One watchlist entry for an active deal — shared by GET /watchlist and
    the daily scheduler (services/lifecycle_alerts.py), which reads the same
    barrier gaps to raise crossing alerts."""
    today_str = today.isoformat()
    events = _get_events(deal.id, session)
    future = [e for e in events if e.event_date > today_str]
    next_ev = min(future, key=lambda e: e.event_date) if future else None
    days_to_next = (date.fromisoformat(next_ev.event_date) - today).days if next_ev else None

    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]
    strike_event = next((e for e in events if e.t_years == 0.0), None)
    s0_map: dict = json.loads(strike_event.spots_json) if strike_event else {}

    # Current perfs + running extrema since strike. The running min is
    # what a continuously-monitored KI actually compares against; the
    # current perfs are what the next discrete observation will see.
    wof = None
    wof_min = None
    bof = None
    bof_max = None
    perfs = []
    spots_out = []
    if tickers and s0_map:
        px = load_hist_prices(tickers, deal.strike_date, today_str)
        if "error" not in px:
            prices = px.get("prices", {})
            min_perfs, max_perfs = [], []
            for u in underlyings:
                tk = u.get("ticker", "")
                name = u["name"]
                s0 = s0_map.get(name, 0.0)
                series = [float(p) for p in prices.get(tk, []) if p]
                if tk and series and s0 > 0:
                    spot = series[-1]
                    perfs.append(spot / s0)
                    min_perfs.append(min(series) / s0)
                    max_perfs.append(max(series) / s0)
                    spots_out.append({
                        "name": name, "ticker": tk, "s0": s0,
                        "spot": round(spot, 4), "perf": round(spot / s0, 4),
                    })
            if perfs:
                wof, bof = min(perfs), max(perfs)
                wof_min, bof_max = min(min_perfs), max(max_perfs)

    # The next observation's 1-based index — a PARAM() barrier schedule
    # is read at THAT row (a degressive autocall must show the barrier
    # the next fixing will actually use, not row 1).
    next_obs_index = next_ev.event_index if next_ev else None

    barriers = []
    if wof is not None:
        try:
            compiled = parse_script(deal.script_snapshot)
            market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
            user_params = market.get("user_params", {}) or {}
            params_by_name = {p.name: p for p in compiled.params}

            def _observable_value(obs: str | None) -> float | None:
                if obs is None or obs == "WOF":
                    return wof
                if obs == "BOF":
                    return bof
                if obs == "WOF_MIN":
                    return wof_min
                if obs == "BOF_MAX":
                    return bof_max
                if obs == "BASKET":
                    return sum(perfs) / len(perfs) if perfs else None
                m_s = re.match(r"^S(?:_MIN|_MAX)?\[(\d+)\]$", obs)
                if m_s:
                    i_u = int(m_s.group(1)) - 1
                    return perfs[i_u] if 0 <= i_u < len(perfs) else None
                return None

            def _level_for(name: str) -> float | None:
                v = user_params.get(name, params_by_name[name].stored_val)
                if isinstance(v, list):
                    if not v:
                        return None
                    idx = (next_obs_index or len(v)) - 1
                    idx = max(0, idx)
                    return float(v[idx]) if idx < len(v) else float(v[-1])
                return float(v)

            monitors = compiled.monitors or []
            if monitors:
                # Explicit M_ contract — trust it exclusively. Direction
                # and observable come from how the script compares the
                # param (see parser._analyze_monitors); ambiguous usage
                # degrades to a neutral, uncolored gap.
                for mon in monitors:
                    level = _level_for(mon["name"])
                    obs_val = _observable_value(mon["observable"])
                    if level is None or obs_val is None:
                        continue
                    kind = {"up": "autocall", "down": "ki"}.get(mon["direction"], "neutral")
                    barriers.append({
                        "name": mon["name"],
                        "kind": kind,
                        "observable": mon["observable"] or "WOF",
                        "level": round(level, 4),
                        "gap_pts": round((obs_val - level) * 100, 1),
                    })
            else:
                # Legacy scripts with no M_ params — name heuristic vs WOF.
                for p in compiled.params:
                    kind = _classify_param_barrier(p.name, p.stored_val)
                    if kind:
                        barriers.append({
                            "name": p.name,
                            "kind": kind,
                            "observable": "WOF",
                            "level": p.stored_val,
                            "gap_pts": round((wof - p.stored_val) * 100, 1),
                        })
        except ValueError:
            pass   # unparseable snapshot — leave barriers empty, keep the row

    min_gap = min((abs(b["gap_pts"]) for b in barriers), default=None)
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "contrepartie": deal.contrepartie,
        "product_type": deal.product_type,
        "next_event": {"date": next_ev.event_date, "label": next_ev.label} if next_ev else None,
        "days_to_next": days_to_next,
        "underlyings": spots_out,
        "wof": round(wof, 4) if wof is not None else None,
        "wof_min": round(wof_min, 4) if wof_min is not None else None,
        "barriers": barriers,
        "min_gap": min_gap,
    }


def _deal_terms(deal: Deal) -> list[dict]:
    """The deal's economic terms: every PARAM of the frozen script, with the
    value actually booked (user_params override when frozen at booking,
    script default otherwise). Values stay in stored units (fractions) with
    is_pct alongside — the UI formats. Array params (PARAM()) keep the full
    per-observation list."""
    try:
        compiled = parse_script(deal.script_snapshot)
    except ValueError:
        return []
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    up = market.get("user_params", {}) or {}
    terms = []
    for p in compiled.params:
        v = up.get(p.name, p.stored_val)
        terms.append({
            "name": p.name,
            "desc": p.desc if p.desc != p.name else "",
            "is_pct": p.is_pct,
            "kind": p.kind,
            "value": list(v) if isinstance(v, (list, tuple)) else v,
        })
    return terms


def _script_flags(deal: Deal) -> dict:
    """Which generic risk mechanisms this script actually has — lets the
    reinvestment scan UI (ReinvestView.vue) hide metrics that make no sense
    for the product (e.g. no autocall filter on a vanilla option). Reuses the
    same barrier-name heuristic as the watchlist (_classify_param_barrier) —
    PayScript has no formal 'this PARAM is a KI barrier' concept, so this is
    a best-effort read, not a guarantee."""
    try:
        compiled = parse_script(deal.script_snapshot)
    except ValueError:
        return {"has_stop": False, "has_ki_param": False, "has_autocall_param": False}
    scalar_params = [p for p in compiled.params if p.kind == "scalar"]
    kinds = {_classify_param_barrier(p.name, p.stored_val) for p in scalar_params}
    return {
        "has_stop": compiled.has_stop,
        "has_ki_param": "ki" in kinds,
        "has_autocall_param": "autocall" in kinds,
    }


@router.get("/{deal_id}")
def get_deal(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    row = _deal_row(deal, _get_events(deal_id, session))
    row["terms"] = _deal_terms(deal)
    row["flags"] = _script_flags(deal)
    return row


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


def _evaluate_lifecycle(deal: Deal, events: list, dates_list: list, prices: dict,
                         tickers: list, session: Session) -> dict | None:
    """Replay the booked script against the historical prices already loaded
    for events/refresh, to find out whether the product has actually called
    early or reached maturity — vs. just knowing raw spot values without
    ever checking them against the payoff condition. Returns a small summary
    dict for the API response, or None if evaluation couldn't run (e.g. a
    CONSTAT-based script whose calendar overrides aren't persisted on the
    deal — a known gap, not fatal to the spot refresh above).

    Best-effort: a script that fails to parse/evaluate must not break the
    spot refresh that already succeeded, so callers should catch ValueError."""
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    compiled = parse_script(deal.script_snapshot)
    # Expert-mode deals: CONSTAT calendars frozen at booking (market.constats,
    # persisted since 2026-07-19) — resolved relative to the deal's value_date,
    # not today. Deals booked before that persistence still raise ValueError
    # here, which callers already treat as "replay unavailable".
    compiled = resolve_constats(
        compiled, market.get("constats") or {},
        anchor=date.fromisoformat(deal.value_date) if deal.value_date else None,
    )
    r_frac = (market.get("r", 3.0) or 3.0) / 100.0
    # PARAM overrides frozen at booking (stored units) — without them the
    # replay would use the script's seed defaults, wrong for any deal whose
    # terms were tuned in the UI (degressive barriers, negotiated coupon…).
    user_params = market.get("user_params", {}) or {}

    # Reference index = last trading day <= strike_date (the same "closest
    # price at or before the event" convention _closest_price uses for the
    # displayed S₀). The fetched window starts BEFORE the strike (see
    # refresh_events) precisely so a weekend/holiday strike date still has a
    # preceding close to anchor on — index 0 would otherwise be a week early.
    start_idx = 0
    for i_d, d_str in enumerate(dates_list):
        if d_str <= deal.strike_date:
            start_idx = i_d
        else:
            break

    res = eval_script_on_history(
        compiled, dates_list, prices, start_idx, deal.T, user_params, tickers, r_frac
    )
    if res is None:
        return None

    today_str = date.today().isoformat()
    non_strike = [e for e in events if e.t_years > 0]

    # Total of every cash flow that actually fired, in both branches below —
    # what the client actually received in total, as a fraction of nominal.
    # eval_script_on_history only ever appends flows that fired, so summing
    # the whole list (not just the terminal one) is correct in either case.
    realized_payout = round(sum(cf["cf"] for cf in res["cash_flows"]), 4)

    if res["early_recall"]:
        T_actual = res["T_actual"]
        triggering = min(non_strike, key=lambda e: abs(e.t_years - T_actual))
        triggering.status = "callé"
        session.add(triggering)
        for e in non_strike:
            if e.t_years > triggering.t_years + 1e-6:
                e.status = "annulé"
                session.add(e)
        deal.status = "callé"
        deal.realized_payout = realized_payout
        deal.resolution_outcome = "callé"
        session.add(deal)
        return {"outcome": "callé", "event_date": triggering.event_date, "t_years": triggering.t_years,
                "realized_payout": realized_payout}

    # No early recall — only conclude "matured" if today has actually
    # reached the maturity date. T_actual == T_max on its own is ambiguous:
    # eval_script_on_history also returns that when the price history simply
    # doesn't extend far enough yet to know (see its mat_events branch).
    if today_str >= deal.maturity_date:
        maturity_payout = sum(cf["cf"] for cf in res["cash_flows"] if abs(cf["t"] - deal.T) < 1e-6)
        maturity_event = max(events, key=lambda e: e.t_years)
        # Heuristic, not a semantic read of the script: a payout materially
        # below par (nominal = 1.0) is treated as a knock-in. Flags an
        # unusual script as "ki" incorrectly in principle — the actual
        # amount is always kept alongside the label so a human can check.
        maturity_event.status = "ki" if maturity_payout < 0.995 else "final"
        session.add(maturity_event)
        deal.status = "échu"
        deal.realized_payout = realized_payout
        deal.resolution_outcome = maturity_event.status
        session.add(deal)
        return {"outcome": maturity_event.status, "event_date": maturity_event.event_date,
                "maturity_payout": round(maturity_payout, 4), "realized_payout": realized_payout}

    return {"outcome": "en_cours"}


@router.post("/{deal_id}/events/refresh")
def refresh_events(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Auto-fetch historical spots from Yahoo Finance for past events, then
    replay the script against that same history to detect an early recall
    or maturity outcome and propagate it to event/deal status."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    try:
        return refresh_deal_core(deal, session)
    except ValueError as e:
        raise HTTPException(422, str(e))


def refresh_deal_core(deal: Deal, session: Session) -> dict:
    """Body of POST /events/refresh without the HTTP layer — also called
    per-deal by the daily scheduler (services/lifecycle_alerts.py). Raises
    ValueError on data problems; commits on success."""
    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]
    if not tickers:
        raise ValueError("Aucun ticker défini sur ce deal")

    today = date.today().isoformat()
    events = _get_events(deal.id, session)
    past_events = [e for e in events if e.event_date <= today]
    if not past_events:
        return {"updated": 0, "message": "Aucun événement passé", "evaluation": None}

    # Fetch from a week BEFORE the strike: a strike date falling on a
    # weekend/holiday has no close of its own, and _closest_price's
    # "last close <= date" convention needs the preceding trading day to
    # exist in the window — otherwise S₀ silently stays empty.
    fetch_start = (date.fromisoformat(deal.strike_date) - timedelta(days=7)).isoformat()
    px_data = load_hist_prices(tickers, fetch_start, today)
    if "error" in px_data:
        raise ValueError(px_data["error"])

    dates_list = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    if not dates_list:
        raise ValueError("Données historiques vides")

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

    evaluation = None
    try:
        evaluation = _evaluate_lifecycle(deal, events, dates_list, prices, tickers, session)
    except ValueError:
        pass   # script couldn't be replayed (e.g. unpersisted CONSTAT calendar) — spots still refreshed above

    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return {"updated": updated, "message": f"{updated} événement(s) mis à jour", "evaluation": evaluation}


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

    if deal.status in ("callé", "échu"):
        # Already resolved (see _evaluate_lifecycle) — there is no more
        # optionality to run a Monte Carlo on. Re-simulating from today with
        # a fresh script would price it as if it restarted now, which is
        # wrong. Report the realized outcome instead.
        events = _get_events(deal_id, session)
        resolved_event = next((e for e in events if e.status in ("callé", "ki", "final")), None)
        return {
            "deal_id": deal_id,
            "reference": deal.reference,
            "resolved": True,
            "status": deal.status,
            "realized_payout": deal.realized_payout,
            "resolution_date": resolved_event.event_date if resolved_event else None,
        }

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

    market_snapshot = json.loads(deal.market_snapshot_json)
    return {
        "deal_id": deal_id,
        "reference": deal.reference,
        "resolved": False,
        "T_remaining": round(T_remaining, 4),
        "T_elapsed": round(T_elapsed, 4),
        "maturity_date": deal.maturity_date,
        "value_date": deal.value_date,
        "normalized_spots": normalized_spots,
        "current_spots": current_spots,
        "realized_events": realized,
        "script_snapshot": deal.script_snapshot,
        "market_snapshot": market_snapshot,
        "underlyings": market_snapshot.get("underlyings", []),
        "corr_matrix": market_snapshot.get("corrMatrix", []),
    }


# ── MtM résiduel ──────────────────────────────────────────────────────

def _engine_underlyings(market: dict, underlyings_json: list) -> list[dict]:
    """Engine-unit underlyings from the booking snapshot: display units
    (σ=20 → 0.20) with neutral defaults for anything a partial snapshot
    (old / API-booked deal) doesn't carry — same fallbacks the Pricer UI
    applies when reopening such a deal (see pricing.js loadFromDeal)."""
    snap_by_name = {u.get("name"): u for u in market.get("underlyings", []) or []}
    out = []
    for u_ref in underlyings_json:
        u = snap_by_name.get(u_ref.get("name"), {})
        def g(key, default, scale=100.0):
            v = u.get(key)
            return default if v is None else v / scale
        out.append({
            "name": u_ref.get("name", ""), "ticker": u_ref.get("ticker", ""),
            "ccy": u.get("ccy", "EUR"),
            "sigma": g("sigma", 0.20), "q": g("q", 0.02),
            "sigma_fx": g("sigma_fx", 0.0), "rho_sfx": g("rho_sfx", 0.0),
            "ccyh": g("ccyh", 0.0, 10000.0),
            "v0": g("v0", 0.04), "kappa": u.get("kappa") or 2.0,
            "theta": g("theta", 0.04), "xi": g("xi", 0.35),
            "rho_h": g("rho_h", -0.70), "rho_rS": g("rho_rS", 0.40),
            "alpha": g("alpha", 0.20), "beta": g("beta", 0.50),
            "rho": g("rho", -0.30), "nu": g("nu", 0.40),
            "skew": g("skew", -0.10), "curvature": g("curvature", 0.05),
        })
    return out


# ── Réinvestissement (module solution d'investissement) ────────────────
# Flow A (ce fichier, "roll") : côté client, dans la vue MtM — reconduire la
# MÊME structure sur le MÊME sous-jacent, value date/strike date à aujourd'hui,
# tenor plein d'origine. Ce n'est PAS un MtM résiduel (pas d'historique à
# rejouer, pas d'état à porter) : juste le même script pricé à neuf.
# Flow B (ce fichier, "scan") : côté desk, onglet Life Cycle dédié — swap du
# sous-jacent sur un pool de candidats, coupon résolu par bissection (réutilise
# solve_for_param, le même moteur que le Solveur existant), classement filtré
# par seuils de proba. Jamais montré au client tel quel.
# Voir MEMORY investment-solution-module pour le cadrage complet.

@router.post("/{deal_id}/reinvest/roll")
def reinvest_roll_endpoint(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    from ..core.payscript.engine import run_mc
    from ..services.market_data import load_hist_vol

    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    if deal.status != "actif":
        raise HTTPException(422, f"Deal {deal.status} — rien à reconduire")

    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    underlyings_json = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings_json if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")

    try:
        compiled = parse_script(deal.script_snapshot)
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=date.today())
    except ValueError as e:
        raise HTTPException(422, f"Script non exploitable pour la reconduction : {e}")

    engine_uls = _engine_underlyings(market, underlyings_json)
    n_u = len(engine_uls)
    corr = market.get("corrMatrix") or [[1.0 if i == j else 0.0 for j in range(n_u)] for i in range(n_u)]

    # Vol/div rafraîchies depuis Yahoo (pas de source de vol implicite — voir
    # MEMORY) ; en cas d'échec on retombe sur les valeurs du snapshot de
    # booking plutôt que d'échouer toute la reconduction.
    vol_data = load_hist_vol(tickers)
    vol_refreshed = "error" not in vol_data
    if vol_refreshed:
        for u, tk in zip(engine_uls, tickers):
            if tk in vol_data["vols"]:
                u["sigma"] = vol_data["vols"][tk]
            if tk in vol_data["div_yields"]:
                u["q"] = vol_data["div_yields"][tk]
        if n_u > 1 and all(tk in vol_data["corr"] for tk in tickers):
            corr = [[vol_data["corr"][t1].get(t2, 0.0) for t2 in tickers] for t1 in tickers]

    current_spots: dict = {}
    px_data = load_hist_prices(tickers, date.today().isoformat(), date.today().isoformat())
    if "error" not in px_data:
        prices = px_data.get("prices", {})
        for tk in tickers:
            if tk in prices and prices[tk]:
                current_spots[tk] = round(float(prices[tk][-1]), 4)

    r_frac = (market.get("r", 3.0) or 3.0) / 100.0
    user_params = market.get("user_params", {}) or {}
    rate_model = market.get("rateModel", "deterministic")
    sigma_r = (market.get("sigma_r", 0.0) or 0.0) / 100.0 if rate_model != "deterministic" else 0.0
    a_r = (market.get("a_r", 0.0) or 0.0) if rate_model == "hull_white" else 0.0
    yc = [[p["T"], p["rate"] / 100.0] for p in market.get("yieldCurve") or []]

    T_new = deal.T
    value_date_new = date.today()
    maturity_date_new = value_date_new + timedelta(days=round(T_new * 365.25))

    try:
        result = run_mc(
            compiled, engine_uls, corr, r_frac, T_new,
            N=20000, model=market.get("model", "constant"), seed=42,
            antithetic=bool(market.get("antithetic", True)),
            user_params=user_params,
            yield_curve=yc, sigma_r=sigma_r, a_r=a_r,
            barrier_monitoring=market.get("barrierMonitoring", "weekly"),
        )
    except ValueError as e:
        raise HTTPException(422, f"Pricing de la reconduction impossible : {e}")

    return {
        "deal_id": deal_id,
        "reference": deal.reference,
        "value_date": value_date_new.isoformat(),
        "maturity_date": maturity_date_new.isoformat(),
        "T": T_new,
        "price_new": round(result["price"], 6),
        "price_current": deal.fair_value,
        "current_spots": current_spots,
        "vol_refreshed": vol_refreshed,
        "sigma_used": {tk: round(u["sigma"], 4) for tk, u in zip(tickers, engine_uls)},
    }


def _price_reinvest_candidate(compiled, base_ul: dict, r_frac: float, T: float, corr: list,
                               user_params: dict, ticker: str, name: str,
                               param_name: str, target_price: float, lo: float, hi: float,
                               N: int, model: str, vol_period: str) -> dict:
    """Price one candidate underlying for the reinvestment scan/proposal:
    fresh vol/div from Yahoo, solve param_name to target_price, then price
    the risk profile. Shared by the scan (looped over the pool) and the
    proposal endpoint (single candidate, re-derives rather than trusting
    client-echoed figures for a document)."""
    from ..core.payscript.simulation import solve_for_param
    from ..core.payscript.engine import run_mc_proba
    from ..services.market_data import load_hist_vol

    vol_data = load_hist_vol([ticker], period=vol_period)
    if "error" in vol_data or ticker not in vol_data.get("vols", {}):
        return {"ticker": ticker, "name": name,
                "error": vol_data.get("error", "Vol Yahoo indisponible pour ce ticker")}

    ul = dict(base_ul)
    ul["name"], ul["ticker"] = name, ticker
    ul["sigma"] = vol_data["vols"][ticker]
    ul["q"] = vol_data["div_yields"].get(ticker, 0.0)

    try:
        solved = solve_for_param(
            compiled, [ul], corr, r_frac, T,
            model=model, seed=42, base_user_params=user_params,
            param_name=param_name, target_price=target_price,
            lo=lo, hi=hi, N=N,
        )
    except ValueError as e:
        return {"ticker": ticker, "name": name, "error": str(e)}
    if not solved["converged"]:
        return {"ticker": ticker, "name": name, "sigma": ul["sigma"], "q": ul["q"],
                "error": "Coupon non bracketé — élargir les bornes du solveur."}

    up = {**user_params, param_name: solved["param_value"]}
    try:
        proba = run_mc_proba(compiled, [ul], corr, r_frac, T,
                              N=N, model=model, seed=42, user_params=up,
                              capital_ref=target_price)
    except ValueError as e:
        return {"ticker": ticker, "name": name, "error": str(e)}

    return {
        "ticker": ticker, "name": name,
        "sigma": round(ul["sigma"], 4), "q": round(ul["q"], 4),
        "param_name": param_name, "solved_param": solved["param_value"],
        "price": proba["price"],
        "ki_pct": proba["ki_pct"], "autocall_pct": proba["autocall_pct"],
        "capital_loss_pct": proba["capital_loss_pct"], "full_coupon_pct": proba["full_coupon_pct"],
    }


def _reinvest_context(deal: Deal, req_T: float | None):
    """Common setup for the scan/proposal endpoints: compiled script, base
    underlying, discounting rate, effective maturity. Raises HTTPException on
    an unusable deal/script — same checks either endpoint needs."""
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    underlyings_json = json.loads(deal.underlyings_json)
    if len(underlyings_json) != 1:
        raise HTTPException(422, "Le scan d'alternatives ne gère pour l'instant que les "
                                  "produits mono-sous-jacent (limitation v1).")
    try:
        compiled = parse_script(deal.script_snapshot)
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=date.today())
    except ValueError as e:
        raise HTTPException(422, f"Script non exploitable : {e}")

    base_ul = _engine_underlyings(market, underlyings_json)[0]
    r_frac = (market.get("r", 3.0) or 3.0) / 100.0
    T = effective_T_max(compiled, req_T if req_T else deal.T)
    return compiled, market, base_ul, r_frac, T


@router.post("/{deal_id}/reinvest/scan")
def reinvest_scan_endpoint(
    deal_id: int,
    req: ReinvestScanRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")

    compiled, market, base_ul, r_frac, T = _reinvest_context(deal, req.T)
    # Mode avancé (param_overrides) : les valeurs bookées restent la base,
    # les overrides du structureur gagnent pour tout PARAM autre que celui
    # résolu par bissection (qui gagne toujours, dans _price_reinvest_candidate).
    user_params = {**(market.get("user_params", {}) or {}), **(req.param_overrides or {})}
    corr = [[1.0]]

    def pct(res: dict, metric: str) -> float:
        return {"ki": res["ki_pct"], "autocall": res["autocall_pct"],
                "capital_loss": res["capital_loss_pct"], "full_coupon": res["full_coupon_pct"]}[metric]

    kept, excluded = [], []
    for cand in req.candidates:
        tk = cand.ticker.strip()
        if not tk:
            continue
        row = _price_reinvest_candidate(
            compiled, base_ul, r_frac, T, corr, user_params,
            tk, cand.name or tk, req.param_name, req.target_price, req.lo, req.hi,
            req.N, req.model, req.vol_period,
        )
        if "error" in row:
            excluded.append(row)
            continue

        failed = next((f for f in req.filters
                        if (pct(row, f.metric) > f.threshold if f.direction == "max"
                            else pct(row, f.metric) < f.threshold)), None)
        if failed:
            row["error"] = f"Filtre '{failed.metric}' non respecté ({pct(row, failed.metric)}%)"
            excluded.append(row)
        else:
            kept.append(row)

    kept.sort(key=lambda r: r["solved_param"], reverse=True)
    return {"results": kept, "excluded": excluded}


def _reinvest_proposal_data(deal: Deal, req: ReinvestProposalRequest) -> dict:
    """Shared by the JSON proposal (screen) and the PDF proposal (download) —
    same body recomputes the same figures, exactly like /mtm and /mtm/report
    share _mtm_core. Price/proba come from _price_reinvest_candidate (single
    candidate); backtest replays the SAME solved param over history via the
    existing _windowed_backtest (pricing.py, shared with /backtest/compare)."""
    from .pricing import _windowed_backtest
    from ..core.payscript.engine import eval_script_on_history

    compiled, market, base_ul, r_frac, T = _reinvest_context(deal, req.T)
    user_params = {**(market.get("user_params", {}) or {}), **(req.param_overrides or {})}
    corr = [[1.0]]

    row = _price_reinvest_candidate(
        compiled, base_ul, r_frac, T, corr, user_params,
        req.ticker, req.name or req.ticker, req.param_name, req.target_price, req.lo, req.hi,
        req.N, req.model, req.vol_period,
    )
    if "error" in row:
        raise HTTPException(422, row["error"])

    px_data = load_hist_prices([req.ticker], req.backtest_start, date.today().isoformat())
    if "error" in px_data:
        backtest = {"error": px_data["error"]}
    else:
        dates = px_data.get("dates", [])
        prices = px_data.get("prices", {})
        series = prices.get(req.ticker, [])
        up = {**user_params, req.param_name: row["solved_param"]}
        stats = _windowed_backtest(compiled, dates, prices, [req.ticker], T,
                                    req.backtest_freq, r_frac, req.backtest_invest_pct, up,
                                    return_windows=True)
        history = None
        if series and series[0]:
            s0 = series[0]
            history = {"dates": dates, "normalized": [round(p / s0, 4) if p else None for p in series]}
        backtest = {"stats": stats, "history": history}
        if stats is None:
            backtest["error"] = "Historique trop court pour la maturité du produit."
        else:
            # Barrières + dates de flux réels de la fenêtre de replay la plus
            # récente, PAS un second graphique séparé : en mono-sous-jacent le
            # worst-of EST le sous-jacent, une courbe "produit" à part ne
            # ferait que redupliquer la queue de la courbe sous-jacent à un
            # autre point de rebasage (voir MEMORY investment-solution-module,
            # le worst-of ne redevient une info distincte qu'avec un panier).
            # Donc : on annote LE graphique du sous-jacent — barrières
            # recalées sur SA base 100 (celle de tout l'historique récupéré,
            # pas celle de la fenêtre), flux positionnés à leur vraie date
            # dans cet historique.
            days_T = round(T * 252)
            max_start = len(dates) - days_T - 1
            if max_start >= 0 and history:
                replay = eval_script_on_history(compiled, dates, prices, max_start, T, up, [req.ticker], r_frac)
                base_at_window_start = history["normalized"][max_start] if max_start < len(history["normalized"]) else None
                if replay and base_at_window_start is not None:
                    barriers = []
                    for b in _monitor_levels(compiled, up, 0):
                        lvl = b.get("level")
                        if lvl is None:
                            continue
                        barriers.append({"name": b["name"], "direction": b.get("direction"),
                                          "level": round(lvl * base_at_window_start, 4)})
                    cash_flows = []
                    for cf in replay["cash_flows"]:
                        idx = max_start + round(cf["t"] * 252)
                        if 0 <= idx < len(dates):
                            cash_flows.append({"date": dates[idx], "amount": cf["cf"]})
                    backtest["product"] = {
                        "window_start": dates[max_start],
                        "early_recall": replay["early_recall"],
                        "T_actual": replay["T_actual"],
                        "barriers": barriers,
                        "cash_flows": cash_flows,
                    }

    value_date_new = date.today()
    maturity_date_new = value_date_new + timedelta(days=round(T * 365.25))
    param_term = next((p for p in compiled.params if p.name == req.param_name), None)

    return {
        "deal": {"reference": deal.reference, "product_type": deal.product_type,
                 "sens": deal.sens, "devise": deal.devise, "nominal": deal.nominal},
        "candidate": row,
        "param_desc": (param_term.desc if param_term and param_term.desc else req.param_name),
        "param_is_pct": param_term.is_pct if param_term else True,
        "T": T,
        "value_date": value_date_new.isoformat(),
        "maturity_date": maturity_date_new.isoformat(),
        "backtest": backtest,
    }


@router.post("/{deal_id}/reinvest/proposal")
def reinvest_proposal_endpoint(
    deal_id: int,
    req: ReinvestProposalRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    return _reinvest_proposal_data(deal, req)


@router.post("/{deal_id}/reinvest/proposal/pdf")
def reinvest_proposal_pdf_endpoint(
    deal_id: int,
    req: ReinvestProposalRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    import io as _io
    from fastapi.responses import StreamingResponse
    from ..core.reinvest_proposal_pdf import generate_reinvest_proposal_pdf

    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    data = _reinvest_proposal_data(deal, req)
    try:
        pdf_bytes = generate_reinvest_proposal_pdf(data)
    except Exception as e:
        raise HTTPException(500, f"Erreur génération de la note de proposition : {e}")
    filename = f"Proposition_{deal.reference}_{data['candidate']['ticker']}_{date.today().isoformat()}.pdf"
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Early-exit signal threshold: MtM capturing this share of the best possible
# discounted outcome on a capped payoff → "consider exiting" flag on the note.
_EXIT_CAPTURE = 0.97


class MtmOverrideUL(BaseModel):
    """Manual per-underlying market override for the residual MtM — display
    units, same as the booking snapshot (sigma=20 → 20%)."""
    sigma: Optional[float] = None
    q: Optional[float] = None


class MtmRequest(BaseModel):
    """Optional body of POST /{deal_id}/mtm. Absent body (current frontend,
    bare curl) → recalibrate="none" → booking snapshot, bit-identical to the
    historical behavior. Priority: manual overrides > realized > booking."""
    recalibrate: Literal["none", "realized"] = "none"
    overrides: Optional[dict[str, MtmOverrideUL]] = None   # key = underlying name
    r: Optional[float] = None        # flat rate override, in % (curve dropped)
    window_days: int = 252


def _mtm_core(
    deal: Deal,
    session: Session,
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
    asof: Optional[date] = None,
) -> tuple[dict, Optional[dict]]:
    """Residual mark-to-market of an ACTIVE deal: replay the frozen script on
    realized history (state: memory coupons, observation index, running
    extrema), then Monte Carlo the REMAINING life only — observation dates at
    their true residual times, paths seeded at today's spot/strike levels,
    replayed state injected. This is the desk MtM, as opposed to '→ Ouvrir'
    re-pricing which restarts the product as new. Design:
    MTM_RESIDUEL_DESIGN.md.

    Returns (payload, ctx): payload is the /mtm response; ctx carries the
    intermediates the valuation note (PDF) and the P&L explain need — price
    history, replayed state, compiled script (monitors), effective underlyings,
    residual script — or None on the resolved_pending short-circuit. Ownership
    is the caller's concern.

    asof (default today) values the deal AS OF a past date: the price history
    is truncated there, so the replayed state, the seeding spots, the residual
    calendar and the realized-vol window all follow — this is what the P&L
    explain uses to build its two photos (EXPLICATION_VALO_DESIGN.md)."""
    from ..core.payscript.engine import run_mc, _shift_events_for_mtf

    deal_id = deal.id
    if deal.status != "actif":
        raise HTTPException(422, f"Deal {deal.status} — plus d'optionnalité à valoriser "
                                 f"(remboursement réalisé: {deal.realized_payout})")

    today = asof or date.today()
    maturity = date.fromisoformat(deal.maturity_date)
    value_d = date.fromisoformat(deal.value_date)
    if today >= maturity:
        raise HTTPException(422, "Échéance atteinte — lancer le refresh du cycle de vie "
                                 "pour résoudre le deal plutôt que le valoriser")
    T_elapsed = max(0.0, (today - value_d).days / 365.25)
    T_remaining = max(1 / 52, (maturity - today).days / 365.25)

    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    underlyings_json = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings_json if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")

    try:
        compiled = parse_script(deal.script_snapshot)
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=value_d)
    except ValueError as e:
        raise HTTPException(422, f"Script/calendriers non exploitables pour le MtM résiduel "
                                 f"(deal booké avant la persistance des CONSTAT ?) : {e}")

    # Realized history from strike (same J-7 window convention as the
    # lifecycle refresh — a weekend/holiday strike needs the preceding close).
    fetch_start = (date.fromisoformat(deal.strike_date) - timedelta(days=7)).isoformat()
    px_data = load_hist_prices(tickers, fetch_start, today.isoformat())
    if "error" in px_data:
        raise HTTPException(422, px_data["error"])
    dates_list = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    if not dates_list:
        raise HTTPException(422, "Données historiques vides")

    start_idx = 0
    for i_d, d_str in enumerate(dates_list):
        if d_str <= deal.strike_date:
            start_idx = i_d
        else:
            break

    user_params = market.get("user_params", {}) or {}
    r_frac = (market.get("r", 3.0) or 3.0) / 100.0

    replay = eval_script_on_history(
        compiled, dates_list, prices, start_idx, deal.T, user_params, tickers, r_frac
    )
    if replay is None:
        raise HTTPException(422, "Replay impossible — S₀ introuvable dans l'historique")
    if replay["early_recall"]:
        return {
            "resolved_pending": True,
            "message": "Le replay détecte un rappel anticipé — lancer le refresh du cycle "
                       "de vie : ce deal ne devrait plus être actif",
            "T_actual": replay["T_actual"],
        }, None
    state = replay["state"]
    realized_cfs = replay["cash_flows"]

    residual_events = _shift_events_for_mtf(compiled.events, T_elapsed)
    if not residual_events:
        raise HTTPException(422, "Aucun événement résiduel — vérifier le calendrier du deal")
    # STRIKE_FIX window split at today: past dates (d <= T_elapsed) were replayed
    # on real closes (state["fix_state"]), only strictly-future dates stay on the
    # residual script — no fixing date is ever counted twice.
    residual_fix = [round(d - T_elapsed, 6) for d in (compiled.strike_fix_dates or [])
                    if d > T_elapsed + 1e-9]
    residual_script = CompiledScript(
        events=residual_events, init_fn=compiled.init_fn,
        params=compiled.params, constats=compiled.constats,
        has_stop=compiled.has_stop, monitors=compiled.monitors,
        strike_fix_dates=residual_fix or None,
    )

    # Paths start at today's spot in % of strike — the barriers written in %
    # of strike then bite at the right distance without any rescaling.
    strike_event = next((e for e in _get_events(deal_id, session) if e.t_years == 0.0), None)
    s0_map: dict = json.loads(strike_event.spots_json) if strike_event else {}
    norm_spots = []
    for u in underlyings_json:
        tk, name = u.get("ticker", ""), u["name"]
        s0 = s0_map.get(name, 0.0)
        series = [float(p) for p in prices.get(tk, []) if p]
        if not (tk and series and s0 > 0):
            raise HTTPException(422, f"Spot/S₀ manquant pour {name} — compléter l'event Strike")
        norm_spots.append(series[-1] / s0)

    engine_uls = _engine_underlyings(market, underlyings_json)
    n_u = len(engine_uls)
    corr = market.get("corrMatrix") or [
        [1.0 if i == j else 0.0 for j in range(n_u)] for i in range(n_u)
    ]

    rate_model = market.get("rateModel", "deterministic")
    sigma_r = (market.get("sigma_r", 0.0) or 0.0) / 100.0 if rate_model != "deterministic" else 0.0
    a_r = (market.get("a_r", 0.0) or 0.0) if rate_model == "hull_white" else 0.0
    yc = [[p["T"], p["rate"] / 100.0] for p in market.get("yieldCurve") or []]

    # ── Market recalibration (opt-in) — only the FUTURE MC leg is affected,
    # the historical replay and the inherited state never depend on σ/corr.
    body = body or MtmRequest()
    model_used = market.get("model", "constant")
    source = "booking"
    n_returns = None
    if body.recalibrate == "realized":
        try:
            rm = realized_market(prices, tickers, body.window_days)
        except ValueError as e:
            raise HTTPException(422, f"Recalibration réalisée impossible : {e}")
        for u, tk in zip(engine_uls, tickers):
            u["sigma"] = rm["sigma"][tk]
        corr = rm["corr"]
        n_returns = rm["n_returns"]
        # Realized vol is a GBM-like number: keeping Heston/SABR/LV with only σ
        # swapped would be either a no-op or an incoherent mix (fresh level,
        # stale smile). Forced model is surfaced in market_used.
        model_used = "constant"
        source = "realized"
    if body.overrides:
        by_name = {u["name"]: u for u in engine_uls}
        for name, ov in body.overrides.items():
            u = by_name.get(name)
            if u is None:
                raise HTTPException(422, f"Override sur sous-jacent inconnu : {name}")
            if ov.sigma is not None:
                u["sigma"] = ov.sigma / 100.0
                model_used = "constant"   # same reasoning as the realized mode
            if ov.q is not None:
                u["q"] = ov.q / 100.0
        source += "+overrides"
    if body.r is not None:
        # A fresh flat rate with the stale booking curve would be incoherent —
        # the override replaces the whole discounting/drift term.
        r_frac = body.r / 100.0
        yc = []

    try:
        result = run_mc(
            residual_script, engine_uls, corr, r_frac, T_remaining,
            N=max(1000, min(100000, n_paths)),
            model=model_used, seed=42,
            antithetic=bool(market.get("antithetic", True)),
            user_params=user_params, spot_mult=norm_spots,
            yield_curve=yc, sigma_r=sigma_r, a_r=a_r,
            barrier_monitoring=market.get("barrierMonitoring", "weekly"),
            wof_min_init=state["wof_min"], bof_max_init=state["bof_max"],
            index_offset=state["index"], memo_init=state["memo"],
            accum_init=state["accum"],
            s_min_init=state["s_min"], s_max_init=state["s_max"],
            s_prev_init=state["s_prev"],
            # WOF at t=0 of the residual tensor = the actual path seed level,
            # not state["wof_last"] — s0 (strike event) and ref (first replay
            # close) are normally identical, but the seed is what the simulated
            # WOF series actually continues from.
            wof0_init=min(norm_spots),
            realvol_state_init=state["realvol_state"],
            fix_state_init=state["fix_state"],
        )
    except ValueError as e:
        raise HTTPException(422, f"MC résiduel impossible : {e}")

    # Residual upside vs the best possible outcome (present value). A payoff is
    # "capped" when the top of the discounted distribution is flat (best case =
    # 95th percentile within 0.5%) — autocalls, reverse convertibles… For those,
    # a MtM already capturing >= _EXIT_CAPTURE of the best case means the client
    # keeps market+credit risk for near-zero remaining upside: early-exit signal.
    # Uncapped payoffs (open upside participation): pv_max is a meaningless tail
    # quantile — expose pv_p95 as "favourable scenario", never the exit signal.
    pv_max, pv_p95 = result.get("pv_max"), result.get("pv_p95")
    best_case = None
    if pv_max is not None and pv_max > 0:
        # bool()/float() coercions: these come out of numpy reductions, and a
        # numpy.bool_ (unlike numpy.float64, a float subclass) crashes FastAPI's
        # JSON encoder.
        pv_max, pv_p95 = float(pv_max), float(pv_p95 or 0.0)
        capped = bool((pv_max - pv_p95) / pv_max < 0.005)
        horizon = max(result.get("fugit") or T_remaining, 1 / 52)
        upside = pv_max - result["price"]
        capture = result["price"] / pv_max
        best_case = {
            "pv_max": pv_max,
            "pv_p95": pv_p95,
            "capped": capped,
            "capture_ratio": round(capture, 4),
            "upside_pts": round(upside * 100, 2),
            "upside_annualized_pct": round(upside / horizon * 100, 2),
            "horizon_years": round(horizon, 2),
            "exit_signal": bool(capped and capture >= _EXIT_CAPTURE),
        }

    payload = {
        "deal_id": deal_id,
        "reference": deal.reference,
        "mtm": result["price"],
        "ic95": result["ic95"],
        "prob_gt100": result["prob_gt100"],
        "fugit": result["fugit"],
        "T_elapsed": round(T_elapsed, 4),
        "T_remaining": round(T_remaining, 4),
        "obs_passees": state["index"],
        "wof_min_realized": round(state["wof_min"], 4),
        "s_min_realized": {u["name"]: round(v, 4)
                           for u, v in zip(underlyings_json, state["s_min"])},
        "norm_spots": {u["name"]: round(s, 4) for u, s in zip(underlyings_json, norm_spots)},
        "realized_cash_flows": realized_cfs,
        "realized_total": round(sum(cf["cf"] for cf in realized_cfs), 4),
        "best_case": best_case,
        "n_paths": result["n_paths"],
        "elapsed_ms": result["elapsed_ms"],
        # Effective market parameters of the future MC leg — always present so
        # a MtM number can never be quoted without knowing what priced it.
        # q is never recalibrated (no dividend source); overrides only.
        "market_used": {
            "source": source,
            "model": model_used,
            "r": round(r_frac * 100.0, 4),
            "flat_curve": not yc,
            "window_returns": n_returns,
            "sigma": {u["name"]: round(eu["sigma"] * 100.0, 2)
                      for u, eu in zip(underlyings_json, engine_uls)},
            "q": {u["name"]: round(eu["q"] * 100.0, 2)
                  for u, eu in zip(underlyings_json, engine_uls)},
            "corr": [[round(v, 4) for v in row] for row in corr],
        },
    }
    ctx = {
        "compiled": compiled,
        "state": state,
        "user_params": user_params,
        "dates": dates_list,
        "prices": prices,
        "start_idx": start_idx,
        "s0_map": s0_map,
        "tickers": tickers,
        "underlyings_json": underlyings_json,
        "norm_spots": norm_spots,
        "T_elapsed": T_elapsed,
        "T_remaining": T_remaining,
        "n_mc": result["n_paths"],
        # Everything needed to re-run this photo's MC (or a mix of two photos)
        # for the P&L explain waterfall:
        "residual_script": residual_script,
        "engine_uls": engine_uls,
        "corr": corr,
        "model_used": model_used,
        "r_frac": r_frac,
        "yc": yc,
        "sigma_r": sigma_r,
        "a_r": a_r,
        "antithetic": bool(market.get("antithetic", True)),
        "barrier_monitoring": market.get("barrierMonitoring", "weekly"),
        "N_used": max(1000, min(100000, n_paths)),
    }
    return payload, ctx


@router.post("/{deal_id}/mtm")
def deal_mtm(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
):
    """Residual MtM endpoint — see _mtm_core."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    payload, _ctx = _mtm_core(deal, session, n_paths, body)
    return payload


class MtmExplainRequest(BaseModel):
    """Body of POST /{deal_id}/mtm/explain. date1 defaults to the deal's value
    date (booking), date2 to today. `recalibrate` sets the σ source at date 2 ;
    at date 1 the rule is fixed (booking σ when date1 = value date, realized σ
    otherwise — see EXPLICATION_VALO_DESIGN.md)."""
    date1: Optional[str] = None
    date2: Optional[str] = None
    recalibrate: Literal["none", "realized"] = "realized"
    window_days: int = 252


def _run_explain_step(cal: dict, spot: dict, uls: list, corr, model: str,
                      common: dict) -> float:
    """One waterfall revaluation: calendar bundle (residual script, T_remaining,
    observation counter — pure calendar quantities), spot bundle (seeding spots
    + path-dependent replayed state), vol bundle (σ via uls + model), corr.
    Mirrors _mtm_core's run_mc call exactly so the chain's endpoints coincide
    with the two /mtm figures. Same seed everywhere (CRN)."""
    from ..core.payscript.engine import run_mc
    st = spot["state"]
    return run_mc(
        cal["residual_script"], uls, corr, common["r_frac"], cal["T_remaining"],
        N=common["N"], model=model, seed=42, antithetic=common["antithetic"],
        user_params=common["user_params"], spot_mult=spot["norm_spots"],
        yield_curve=common["yc"], sigma_r=common["sigma_r"], a_r=common["a_r"],
        barrier_monitoring=common["bm"],
        wof_min_init=st["wof_min"], bof_max_init=st["bof_max"],
        index_offset=cal["index_offset"], memo_init=st["memo"],
        accum_init=st["accum"],
        s_min_init=st["s_min"], s_max_init=st["s_max"], s_prev_init=st["s_prev"],
        wof0_init=min(spot["norm_spots"]),
        realvol_state_init=st["realvol_state"], fix_state_init=st["fix_state"],
    )["price"]


def _residual_greeks(ctx: dict, n_paths: int) -> list[dict]:
    """Residual-deal sensitivities by CRN bump-and-reprice on the same residual
    setup (state inheritance included). Client-friendly units: MtM impact in
    points for a +1% spot move (delta), its convexity (gamma, second
    difference), and +1 vol point (vega). Vega is None on non-GBM models —
    bumping σ there would be a misleading no-op (Heston ignores it)."""
    from ..core.payscript.engine import run_mc
    N_g = max(1000, ctx["N_used"] // 4)
    st = ctx["state"]

    def price(spots=None, uls=None):
        sp = spots if spots is not None else ctx["norm_spots"]
        return run_mc(
            ctx["residual_script"], uls or ctx["engine_uls"], ctx["corr"],
            ctx["r_frac"], ctx["T_remaining"], N=N_g, model=ctx["model_used"],
            seed=42, antithetic=ctx["antithetic"], user_params=ctx["user_params"],
            spot_mult=sp, yield_curve=ctx["yc"], sigma_r=ctx["sigma_r"],
            a_r=ctx["a_r"], barrier_monitoring=ctx["barrier_monitoring"],
            wof_min_init=st["wof_min"], bof_max_init=st["bof_max"],
            index_offset=st["index"], memo_init=st["memo"], accum_init=st["accum"],
            s_min_init=st["s_min"], s_max_init=st["s_max"], s_prev_init=st["s_prev"],
            wof0_init=min(sp), realvol_state_init=st["realvol_state"],
            fix_state_init=st["fix_state"],
        )["price"]

    base = price()
    ns = ctx["norm_spots"]
    gbm = ctx["model_used"] == "constant"
    out = []
    for i, u in enumerate(ctx["underlyings_json"]):
        up = list(ns); up[i] = ns[i] * 1.01
        dn = list(ns); dn[i] = ns[i] * 0.99
        pu, pd = price(spots=up), price(spots=dn)
        vega = None
        if gbm:
            uls_v = [dict(x) for x in ctx["engine_uls"]]
            uls_v[i]["sigma"] = uls_v[i]["sigma"] + 0.01
            vega = round((price(uls=uls_v) - base) * 100, 2)
        out.append({"name": u["name"],
                    "delta_pts": round((pu - pd) / 2 * 100, 2),
                    "gamma_pts": round((pu + pd - 2 * base) * 100, 3),
                    "vega_pts": vega})
    return out


def _explain_core(deal: Deal, session: Session, n_paths: int,
                  body: MtmExplainRequest) -> tuple[dict, dict, dict]:
    """P&L explain between two dates: waterfall MtM(d1) → temps → spot → vol →
    corr → MtM(d2), sequential revaluations at identical seed (CRN), plus the
    cash flows detached in between (hors modèle). The chain telescopes exactly
    to ΔMtM; the residual line is the invariant check (≈0 — anything nonzero
    means a factor escaped the chain). Design: EXPLICATION_VALO_DESIGN.md.
    Returns (payload, ctx1, ctx2) — the ctxs feed the PDF note (greeks at d2)."""

    value_d = date.fromisoformat(deal.value_date)
    today = date.today()
    try:
        d1 = date.fromisoformat(body.date1) if body.date1 else value_d
        d2 = date.fromisoformat(body.date2) if body.date2 else today
    except ValueError as e:
        raise HTTPException(422, f"Date invalide : {e}")
    if d1 < value_d:
        d1 = value_d
    if d2 > today:
        raise HTTPException(422, "La date 2 est dans le futur — un MtM ne se calcule "
                                 "que sur des données réalisées")
    if d2 <= d1:
        raise HTTPException(422, "La date 2 doit être strictement postérieure à la date 1")

    # σ à d1 : booking si d1 = date de valeur (l'effet véga répond alors à
    # « pricé à cette vol, le marché a fait autrement »), réalisée sinon.
    body1 = MtmRequest(recalibrate="none" if d1 == value_d else "realized",
                       window_days=body.window_days)
    body2 = MtmRequest(recalibrate=body.recalibrate, window_days=body.window_days)

    p1, c1 = _mtm_core(deal, session, n_paths, body1, asof=d1)
    if p1.get("resolved_pending") or c1 is None:
        raise HTTPException(422, "Produit déjà rappelé avant la date 1 — rien à expliquer")
    p2, c2 = _mtm_core(deal, session, n_paths, body2, asof=d2)
    if p2.get("resolved_pending") or c2 is None:
        raise HTTPException(422, "Produit rappelé entre les deux dates — c'est la "
                                 "résolution qui explique le P&L, pas un MtM")

    common = {"r_frac": c1["r_frac"], "yc": c1["yc"], "sigma_r": c1["sigma_r"],
              "a_r": c1["a_r"], "antithetic": c1["antithetic"],
              "user_params": c1["user_params"], "bm": c1["barrier_monitoring"],
              "N": c1["N_used"]}
    cal1 = {"residual_script": c1["residual_script"], "T_remaining": c1["T_remaining"],
            "index_offset": c1["state"]["index"]}
    cal2 = {"residual_script": c2["residual_script"], "T_remaining": c2["T_remaining"],
            "index_offset": c2["state"]["index"]}
    spot1 = {"norm_spots": c1["norm_spots"], "state": c1["state"]}
    spot2 = {"norm_spots": c2["norm_spots"], "state": c2["state"]}

    mtm1, mtm2 = p1["mtm"], p2["mtm"]
    try:
        v_time = _run_explain_step(cal2, spot1, c1["engine_uls"], c1["corr"],
                                   c1["model_used"], common)
        v_spot = _run_explain_step(cal2, spot2, c1["engine_uls"], c1["corr"],
                                   c1["model_used"], common)
        v_vol = _run_explain_step(cal2, spot2, c2["engine_uls"], c1["corr"],
                                  c2["model_used"], common)
        if len(c1["engine_uls"]) > 1 and c2["corr"] != c1["corr"]:
            v_corr = _run_explain_step(cal2, spot2, c2["engine_uls"], c2["corr"],
                                       c2["model_used"], common)
            corr_step = True
        else:
            v_corr, corr_step = v_vol, False
    except ValueError as e:
        raise HTTPException(422, f"Réévaluation waterfall impossible : {e}")

    steps = [
        {"label": "Effet temps", "delta_pts": round((v_time - mtm1) * 100, 2),
         "mtm_after": round(v_time, 6)},
        {"label": "Effet spot", "delta_pts": round((v_spot - v_time) * 100, 2),
         "mtm_after": round(v_spot, 6)},
        {"label": "Effet volatilité", "delta_pts": round((v_vol - v_spot) * 100, 2),
         "mtm_after": round(v_vol, 6)},
    ]
    if corr_step:
        steps.append({"label": "Effet corrélation",
                      "delta_pts": round((v_corr - v_vol) * 100, 2),
                      "mtm_after": round(v_corr, 6)})
    residual = mtm2 - v_corr

    eps = 1e-9
    flows = [cf for cf in (p2.get("realized_cash_flows") or [])
             if cf["t"] > c1["T_elapsed"] + eps]
    flows_total = sum(cf["cf"] for cf in flows)

    # Rule-based sentences — one per waterfall line, auditable.
    months = (d2 - d1).days / 30.44
    delta = mtm2 - mtm1
    phrases = [
        f"Entre le {d1.isoformat()} et le {d2.isoformat()}, la valeur du produit est "
        f"passée de {mtm1 * 100:.2f}% à {mtm2 * 100:.2f}% du nominal, soit "
        f"{delta * 100:+.2f} point(s).",
        f"L'écoulement du temps ({months:.1f} mois) contribue pour "
        f"{steps[0]['delta_pts']:+.2f} point(s) — rapprochement des échéances et des "
        f"coupons (theta).",
    ]
    moves = ", ".join(
        f"{u['name']} de {s1 * 100:.1f}% à {s2 * 100:.1f}% du strike"
        for u, s1, s2 in zip(c1["underlyings_json"], c1["norm_spots"], c2["norm_spots"]))
    phrases.append(f"Le mouvement des sous-jacents ({moves}) contribue pour "
                   f"{steps[1]['delta_pts']:+.2f} point(s) (delta/gamma, barrières "
                   f"franchies sur la période comprises).")
    sig1 = p1["market_used"]["sigma"]
    sig2 = p2["market_used"]["sigma"]
    vols = ", ".join(f"{n} de {sig1.get(n, '—')}% à {sig2.get(n, '—')}%"
                     for n in sig1)
    phrases.append(f"L'évolution de la volatilité ({vols}) contribue pour "
                   f"{steps[2]['delta_pts']:+.2f} point(s) (véga).")
    if corr_step:
        phrases.append(f"L'évolution des corrélations contribue pour "
                       f"{steps[3]['delta_pts']:+.2f} point(s).")
    if flows:
        phrases.append(f"Flux détachés sur la période : {flows_total * 100:.2f}% du "
                       f"nominal — le P&L total de la période ressort à "
                       f"{(delta + flows_total) * 100:+.2f} point(s) (variation de "
                       f"valeur + flux perçus).")
    phrases.append("Le taux d'actualisation est maintenu constant entre les deux dates "
                   "(pas de source de taux historiques) — tout effet taux résiduel est "
                   "porté par la ligne « résidu ».")

    payload = {
        "deal_id": deal.id,
        "reference": deal.reference,
        "date1": d1.isoformat(),
        "date2": d2.isoformat(),
        "mtm1": mtm1,
        "mtm2": mtm2,
        "delta_pts": round(delta * 100, 2),
        "steps": steps,
        "residual_pts": round(residual * 100, 2),
        "flows_detached": flows,
        "flows_total_pts": round(flows_total * 100, 2),
        "pnl_total_pts": round((delta + flows_total) * 100, 2),
        "market1": p1["market_used"],
        "market2": p2["market_used"],
        "phrases": phrases,
    }
    return payload, c1, c2


@router.post("/{deal_id}/mtm/explain")
def deal_mtm_explain(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
):
    """P&L explain endpoint — see _explain_core."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    payload, _c1, _c2 = _explain_core(deal, session, n_paths,
                                      body or MtmExplainRequest())
    return payload


@router.post("/{deal_id}/mtm/explain/report")
def deal_mtm_explain_report(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
):
    """PDF note of the P&L explain — same body/seed as /mtm/explain, so the
    figures in the PDF are exactly the ones displayed, plus the residual
    sensitivities (Δ/Γ/véga) at date 2 in the technical annex."""
    import io as _io
    from fastapi.responses import StreamingResponse
    from ..core.deal_valuation_pdf import generate_explain_pdf

    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    payload, _c1, c2 = _explain_core(deal, session, n_paths,
                                     body or MtmExplainRequest())
    data = {
        "deal": {
            "reference": deal.reference, "product_type": deal.product_type,
            "sens": deal.sens, "contrepartie": deal.contrepartie,
            "nominal": deal.nominal, "devise": deal.devise,
            "price_traded": deal.price_traded,
            "trade_date": deal.trade_date, "strike_date": deal.strike_date,
            "value_date": deal.value_date, "maturity_date": deal.maturity_date,
        },
        "res": payload,
        "underlyings": [{"name": u["name"], "ticker": u.get("ticker", ""),
                         "spot_pct": s}
                        for u, s in zip(c2["underlyings_json"], c2["norm_spots"])],
        "greeks": _residual_greeks(c2, n_paths),
    }
    try:
        pdf_bytes = generate_explain_pdf(data)
    except Exception as e:
        raise HTTPException(500, f"Erreur génération de la note d'explication : {e}")
    filename = (f"Explication_valo_{deal.reference}_"
                f"{payload['date1']}_{payload['date2']}.pdf")
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _monitor_levels(compiled, user_params: dict, next_row: int) -> list[dict]:
    """Resolved barrier levels of the M_ monitoring contract, read at the row
    the NEXT observation will use for PARAM() arrays (same convention as the
    watchlist: obs number is 1-based, _pobs reads memo[name][index-1], so the
    next observation after `next_row` passed ones reads row `next_row`).
    Legacy scripts without any M_ param fall back to the same name heuristic
    as the watchlist (_classify_param_barrier)."""
    full = {p.name: p.stored_val for p in compiled.params}
    full.update(user_params or {})

    def resolve(name):
        v = full.get(name)
        if isinstance(v, list):
            v = v[min(next_row, len(v) - 1)] if v else None
        return float(v) if isinstance(v, (int, float)) else None

    out = []
    for m in compiled.monitors or []:
        lvl = resolve(m["name"])
        if lvl is not None:
            out.append({"name": m["name"], "observable": m.get("observable"),
                        "direction": m.get("direction"), "level": lvl})
    if out:
        return out
    for p in compiled.params:
        lvl = resolve(p.name)
        if lvl is None:
            continue
        kind = _classify_param_barrier(p.name, lvl)
        if kind:
            out.append({"name": p.name, "observable": None,
                        "direction": "down" if kind == "ki" else "up",
                        "level": lvl})
    return out


@router.post("/{deal_id}/mtm/report")
def deal_mtm_report(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
):
    """Client-facing valuation note (PDF): re-runs the residual MtM with the
    SAME body and seed as the /mtm endpoint — the figure in the PDF is exactly
    the one displayed in the Booking page. Design: NOTE_VALO_DESIGN.md."""
    import io as _io
    from fastapi.responses import StreamingResponse
    # Heavy import (matplotlib/reportlab) kept out of module load time.
    from ..core.deal_valuation_pdf import generate_valuation_pdf

    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    payload, ctx = _mtm_core(deal, session, n_paths, body)
    if payload.get("resolved_pending") or ctx is None:
        raise HTTPException(422, payload.get("message", "Deal en attente de résolution"))

    events = _get_events(deal_id, session)
    ev_rows = [{"date": e.event_date, "label": e.label, "status": e.status,
                "t_years": e.t_years} for e in events]
    next_obs = next((e.event_date for e in sorted(events, key=lambda x: x.t_years or 0.0)
                     if e.status == "futur"), None)

    start_idx = ctx["start_idx"]
    s0_map = ctx["s0_map"]
    series = {}
    for u in ctx["underlyings_json"]:
        name, tk = u["name"], u.get("ticker", "")
        s0 = s0_map.get(name, 0.0)
        px = ctx["prices"].get(tk, [])
        if s0 > 0 and px:
            series[name] = [(p / s0 if p and p > 0 else None) for p in px[start_idx:]]

    data = {
        "deal": {
            "reference": deal.reference, "product_type": deal.product_type,
            "sens": deal.sens, "contrepartie": deal.contrepartie,
            "nominal": deal.nominal, "devise": deal.devise,
            "price_traded": deal.price_traded,
            "trade_date": deal.trade_date, "strike_date": deal.strike_date,
            "value_date": deal.value_date, "maturity_date": deal.maturity_date,
        },
        "mtm": payload,
        "underlyings": [{"name": u["name"], "ticker": u.get("ticker", ""),
                         "spot_pct": s}
                        for u, s in zip(ctx["underlyings_json"], ctx["norm_spots"])],
        "monitors": _monitor_levels(ctx["compiled"], ctx["user_params"],
                                    ctx["state"]["index"]),
        "events": ev_rows,
        "next_obs_date": next_obs,
        "history": {"dates": ctx["dates"][start_idx:], "series": series},
        "greeks": _residual_greeks(ctx, n_paths),
    }
    try:
        pdf_bytes = generate_valuation_pdf(data)
    except Exception as e:
        raise HTTPException(500, f"Erreur génération de la note de valorisation : {e}")
    filename = f"Note_valo_{deal.reference}_{date.today().isoformat()}.pdf"
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
