"""Deal reads: list, counterparties, watchlist, detail, audit trail, editable fields."""
from __future__ import annotations
import json
import re
from datetime import date, timedelta
from typing import Annotated, Optional, List
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...core.access import has_business_role
from ...db.models import AuditEvent, Deal, User, Counterparty, OfficialFixingVersion, RfqRequest, Script, TradeAmendmentRequest
from ..auth import get_current_user
from ...services.market_data import load_hist_prices
from ...core.payscript.parser import parse_script
from ...core.audit import commit_rejection
from ...core.watchlist_observations import watchlist_observations
from ...core.payoff_terms import classify_param_barrier
from ...core.workflow import AmendmentStatus
from ...services.product_repository import ProductError, load_product, owned_record
from ...services.exotic_product_booking import is_native_exotic_deal, is_native_template_deal
from ...services.business_access import deal_entity_id as _deal_entity_id, can_read_deal as _can_access_deal
from ._router import router
from .common import _niveau_initial_constate
from .serializers import _amendment_row, _audit_row, _deal_row, _fixing_version_row, _get_events, _get_lifecycle_proposals, _market_snapshot_for_read, _proposal_row
from ..contracts import returns
from ..responses import DealDetail, DealRow, EligibleCounterparty

# ── Pydantic schemas ──────────────────────────────────────────────────





class DealUpdate(BaseModel):
    # This endpoint is a refusal boundary, not an edit form. Preserve every
    # supplied field (including a future/unknown one) so an attempted direct
    # mutation is audited instead of being silently discarded by Pydantic.
    model_config = ConfigDict(extra="allow")
    status: Optional[str] = None
    contrepartie: Optional[str] = None
    price_traded: Optional[float] = None
    nominal: Optional[float] = None
    devise: Optional[str] = None
    fair_value: Optional[float] = None
    sens: Optional[str] = None
    trade_date: Optional[str] = None
    strike_date: Optional[str] = None
    value_date: Optional[str] = None
    maturity_date: Optional[str] = None
    payment_date: Optional[str] = None
    T: Optional[float] = None
    underlyings: Optional[List[dict]] = None
    observation_times: Optional[List[float]] = None
    script_snapshot: Optional[str] = None
    market_snapshot: Optional[dict] = None
    rfq_id: Optional[int] = None
    selected_quote_id: Optional[int] = None


@router.get("", responses=returns(list[DealRow]))
def list_deals(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    statement = select(Deal).order_by(Deal.created_at.desc())
    deals = [deal for deal in session.exec(statement).all()
             if _can_access_deal(deal, current, session)]
    from ...core.risk_lifecycle import terminal_dates_by_deal
    terminal_dates = terminal_dates_by_deal(
        session, [deal.id for deal in deals if deal.id is not None])
    return [
        _deal_row(
            d,
            session=session,
            risk_terminal_date=terminal_dates.get(d.id),
        )
        for d in deals
    ]


# Eligible counterparties for the booking form — any authenticated user (the
# admin CRUD lives in api/admin.py). Only active ones: eligibility is the
# whole point of the list.
# NOTE: declared before GET /{deal_id} on purpose — FastAPI matches routes in
# declaration order, and a literal path segment must not be captured as a
# deal_id (same reason as /watchlist below).
@router.get("/counterparties", responses=returns(list[EligibleCounterparty]))
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
    client_id: int | None = None,
    mandate_id: int | None = None,
):
    """Barrier-proximity watchlist over the accessible ACTIVE deals: for each,
    the next observation date, the current worst-of performance vs S₀, and
    the gap (in points of S₀) to every barrier-looking PARAM in the booked
    script. Sorted most-urgent first (smallest barrier gap, then nearest
    observation). Uses the script's PARAM defaults — user overrides typed in
    the UI at pricing time are not persisted on the deal (known limitation)."""
    statement = select(Deal).where(Deal.status == "actif")
    # Commercial context is an optional projection over the lifecycle book,
    # never a prerequisite for it.  These filters let Client Intelligence
    # open the existing watchlist without maintaining a second event list.
    if client_id is not None:
        statement = statement.where(Deal.client_id == client_id)
    if mandate_id is not None:
        statement = statement.where(Deal.mandate_id == mandate_id)
    deals = [deal for deal in session.exec(statement).all()
             if _can_access_deal(deal, current, session)]
    today = business_today()
    rows = [build_watchlist_row(deal, session, today) for deal in deals]

    rows.sort(key=lambda r: (
        r["min_gap"] if r["min_gap"] is not None else 1e9,
        r["days_to_next"] if r["days_to_next"] is not None else 1e9,
    ))
    return rows


def _product_name(deal: Deal, session: Session) -> str:
    """How the desk names this product, as opposed to its reference (an id) or
    its product_type (a family). A deal has no name column of its own: it
    inherits the name of what it was built from — the saved script, or the
    tender it was won on. Empty for an ad-hoc script never saved anywhere,
    which genuinely has no name to show."""
    if deal.script_id:
        script = session.get(Script, deal.script_id)
        if script:
            return script.name
    if deal.rfq_id:
        rfq = session.get(RfqRequest, deal.rfq_id)
        if rfq:
            return rfq.name
    return ""


def build_watchlist_row(deal: Deal, session: Session, today: date) -> dict:
    """One watchlist entry for an active deal — shared by GET /watchlist and
    the daily scheduler (services/lifecycle_alerts.py), which reads the same
    barrier gaps to raise crossing alerts."""
    today_str = today.isoformat()
    events = _get_events(deal.id, session)
    # A window relevé feeds a constatation, it is not one: neither the next
    # observation nor a PARAM() row. Read as one, the first relevé showed as
    # "Prochaine obs." and the call alert counted its days to it.
    constatations = [e for e in events if e.parent_event_id is None]
    future = [e for e in constatations if e.event_date > today_str]
    next_ev = min(future, key=lambda e: e.event_date) if future else None
    days_to_next = (date.fromisoformat(next_ev.event_date) - today).days if next_ev else None

    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]
    # S₀ as the contract defines it: the strike fixing, or the reduction of a
    # start window's relevés — {} while that window is incomplete, so nothing
    # is measured against a partial average.
    s0_map: dict = _niveau_initial_constate(events, deal.schedule_json)

    # Keep source positions even when a constituent has no usable observation.
    history = {}
    if tickers and s0_map and deal.strike_date <= today_str:
        fetch_start = (date.fromisoformat(deal.strike_date) - timedelta(days=7)).isoformat()
        history = load_hist_prices(tickers, fetch_start, today_str,
                                   adjusted=False, allow_partial=True)
    # C13: validate governed versions even during an outage. Provider history
    # cannot replace a pending/corrected contractual fixing or its initial level.
    if len(tickers) == len(underlyings) and tickers:
        from ...core.official_history import official_history
        old_dates = history.get("dates", [])
        old_prices = history.get("prices", {})
        padded = {tk: [(old_prices.get(tk) or [])[i] if i < len(old_prices.get(tk) or []) else None
                       for i in range(len(old_dates))] for tk in tickers}
        overlaid, combined, _, ledger = official_history(
            session, deal, events, padded, old_dates, today)
        if ledger["official_fixings"]:
            source_dates = history.get("source_observation_dates", {})
            original = {day: i for i, day in enumerate(old_dates)}
            official_dates = set(ledger["official_dates"])
            effective = dict(history.get("effective_dates", {}))
            for tk in tickers:
                if effective.get(tk):
                    effective[tk] = max(effective[tk], max(official_dates))
            history = {**history, "dates": combined, "prices": overlaid,
                       "effective_dates": effective, "fixing_registry": ledger,
                       "source_observation_dates": {tk: [day if day in official_dates else
                           source_dates[tk][original[day]] if tk in source_dates else
                           min(day, (history.get("effective_dates", {}).get(tk) or day))
                           for day in combined] for tk in tickers}}
            # An available official close remains usable, subject to C11 age.
            history.pop("error", None)
    observations_data = watchlist_observations(
        underlyings, s0_map, history, deal.strike_date, today_str)
    spots_out = observations_data["underlyings"]
    wof, bof = observations_data["wof"], observations_data["bof"]
    wof_min, bof_max = observations_data["wof_min"], observations_data["bof_max"]

    # The next observation's 1-based rank — a PARAM() barrier schedule
    # is read at THAT row (a degressive autocall must show the barrier
    # the next fixing will actually use, not row 1). A rank among
    # constatations, not event_index: a windowed constatation's index also
    # counts the relevé rows booked before it, and read row 6 for row 2.
    observations = sorted((e for e in constatations if e.t_years > 0),
                          key=lambda e: (e.t_years, e.event_index))
    next_obs_index = next((rank for rank, e in enumerate(observations, start=1)
                           if e is next_ev), None)

    # Detected whatever the deal's stage: a barrier is a term of the contract,
    # not a consequence of having a spot. Before the strike there is simply no
    # gap to show (gap_pts stays None) — "aucune détectée" used to be displayed
    # instead, sending the reader hunting for a script that parses fine.
    barriers = []
    try:
        compiled = parse_script(deal.script_snapshot)
        market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
        user_params = market.get("user_params", {}) or {}
        params_by_name = {p.name: p for p in compiled.params}

        def _observable_value(obs: str | None) -> float | None:
            if obs == "WOF":
                return wof
            if obs is None:
                return None
            if obs == "BOF":
                return bof
            if obs == "WOF_MIN":
                return wof_min
            if obs == "BOF_MAX":
                return bof_max
            if obs == "WOF_MAX":
                return observations_data.get("wof_max")
            if obs in {"BASKET", "BASKET()"}:
                return observations_data["basket"]
            m_s = re.fullmatch(r"(S|S_MIN|S_MAX)\[(\d+)\]", obs)
            if m_s:
                i_u = int(m_s.group(2)) - 1
                field = {"S": "perf", "S_MIN": "min_perf", "S_MAX": "max_perf"}[m_s.group(1)]
                return spots_out[i_u][field] if 0 <= i_u < len(spots_out) else None
            return None

        def _level_for(name: str) -> float | None:
            v = user_params.get(name, params_by_name[name].stored_val)
            if isinstance(v, list):
                if not v:
                    return None
                idx = (next_obs_index or len(v)) - 1
                idx = max(0, idx)
                return float(v[idx]) if idx < len(v) else float(v[-1])
            return float(v) if v is not None else None

        monitors = compiled.monitors or []
        if monitors:
            # Explicit M_ contract — trust it exclusively. Direction
            # and observable come from how the script compares the
            # param (see parser._analyze_monitors); ambiguous usage
            # degrades to a neutral, uncolored gap.
            for mon in monitors:
                level = _level_for(mon["name"])
                if level is None:
                    continue
                obs_val = _observable_value(mon["observable"])
                # Direction says how the observable crosses the level, not
                # what business event follows.  A coupon barrier and a recall
                # barrier are both crossed upwards, but only the latter can
                # trigger a lifecycle alert.
                kind = classify_param_barrier(mon["name"], level) or "neutral"
                barriers.append({
                    "name": mon["name"],
                    "kind": kind,
                    "observable": mon["observable"],
                    "level": round(level, 4),
                    "value_status": ("AVAILABLE" if obs_val is not None else
                                     "STRIKE_PENDING" if deal.strike_date > today_str else "UNAVAILABLE"),
                    "monitoring_basis": ("SAMPLED_CLOSES_SINCE_STRIKE" if
                        mon["observable"] and ("_MIN" in mon["observable"] or "_MAX" in mon["observable"])
                        else "LATEST_CLOSE"),
                    # None = the observable isn't computable yet (strike not
                    # fixed, prices unavailable). Every consumer must read it
                    # as "no gap yet", never as zero — see utils/barriers.js
                    # and portfolios.py:_barrier_severity.
                    "gap_pts": round((obs_val - level) * 100, 1) if obs_val is not None else None,
                })
        else:
            # Legacy scripts with no M_ params — name heuristic vs WOF.
            for p in compiled.params:
                level = _level_for(p.name)
                kind = classify_param_barrier(p.name, level)
                if kind:
                    barriers.append({
                        "name": p.name,
                        "kind": kind,
                        "observable": "WOF",
                        "level": level,
                        "value_status": ("AVAILABLE" if wof is not None else
                                         "STRIKE_PENDING" if deal.strike_date > today_str else "UNAVAILABLE"),
                        "monitoring_basis": "LATEST_CLOSE",
                        "gap_pts": round((wof - level) * 100, 1) if wof is not None else None,
                    })
    except ValueError:
        pass   # unparseable snapshot — leave barriers empty, keep the row

    min_gap = min((abs(b["gap_pts"]) for b in barriers
                   if b["gap_pts"] is not None), default=None)
    return {
        "deal_id": deal.id,
        # Stable commercial identifiers for projections and deep links.  The
        # counterparty below remains the legal trading counterparty; it must
        # not be reused as a client identity.
        "client_id": deal.client_id,
        "mandate_id": deal.mandate_id,
        "reference": deal.reference,
        "contrepartie": deal.contrepartie,
        "product_name": _product_name(deal, session),
        "product_type": deal.product_type,
        "nominal": deal.nominal,
        "devise": deal.devise,
        # Forward start: nothing to measure yet, and that's normal — distinct
        # from an S₀ that should be there and isn't (a Refresh away).
        "strike_pending": deal.strike_date > today_str,
        "next_event": {"date": next_ev.event_date, "label": next_ev.label} if next_ev else None,
        "days_to_next": days_to_next,
        "underlyings": spots_out,
        "market_coverage": observations_data["coverage"],
        "history_window": {"start": deal.strike_date, "end": today_str,
                           "basis": "UNADJUSTED_SAMPLED_CLOSES", "indicative": True},
        "fixing_registry": history.get("fixing_registry"),
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
    up = _market_snapshot_for_read(deal).get("user_params")
    if not isinstance(up, dict):
        up = {}
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
    values = _market_snapshot_for_read(deal).get("user_params")
    if not isinstance(values, dict):
        values = {}
    kinds = {classify_param_barrier(p.name, values.get(p.name, p.stored_val)) for p in scalar_params}
    return {
        "has_stop": compiled.has_stop,
        "has_ki_param": "ki" in kinds,
        "has_autocall_param": "autocall" in kinds,
    }


@router.get("/amendment-requests/pending")
def pending_amendment_requests(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Checker work queue, restricted to the same legal entity."""
    if not has_business_role(current, {"checker", "admin"}):
        raise HTTPException(403, "Réservé aux checkers")
    requests = session.exec(
        select(TradeAmendmentRequest).where(
            TradeAmendmentRequest.status.in_([
                AmendmentStatus.PENDING.value, AmendmentStatus.APPROVED.value])
        ).order_by(TradeAmendmentRequest.created_at)
    ).all()
    rows = []
    for request in requests:
        deal = session.get(Deal, request.deal_id)
        if not deal or not _can_access_deal(deal, current, session):
            continue
        if current.role != "admin" and _deal_entity_id(deal, session) != current.entity_id:
            continue
        row = _amendment_row(request)
        row.update({"deal_reference": deal.reference,
                    "contract_version": deal.contract_version})
        rows.append(row)
    return rows


@router.get("/{deal_id}", responses=returns(DealDetail))
def get_deal(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    row = _deal_row(deal, _get_events(deal_id, session), session)
    row['schedule'] = json.loads(deal.schedule_json or '{}') or None
    # The Pricer must replay the version linked to this contract, not resolve
    # old raw terms with today's calendar algorithm or read the latest terms.
    row['frozen_schedule'] = None
    row['calendar_status'] = 'UNAVAILABLE'
    exotic = is_native_exotic_deal(deal)
    template = is_native_template_deal(deal)
    native = exotic or template
    if deal.product_id is not None and deal.product_terms_version is not None:
        try:
            if not native:
                owned_record(session, deal.product_id, current)
            contract = load_product(session, deal.product_id, terms_version=deal.product_terms_version, allow_native=native)
            if native:
                profile = "native_template_v1" if template else "native_exotic_act365f"
                frozen = {"profile": profile, "schedule": contract.native_schedule.model_dump(mode="json")} if contract.native_schedule else None
            else:
                frozen = contract.terms.resolved_events.to_dict() if contract.terms.resolved_events else None
            if frozen and (frozen.get('schedule') == row['schedule'] or (not template and not row['schedule'])):
                row['frozen_schedule'] = frozen
                row['calendar_status'] = 'FROZEN'
        except (ProductError, ValueError, TypeError):
            # Read-only consultation remains possible; pricing cannot invent
            # the missing proof and will require explicit requalification.
            pass
    versions = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_id == deal_id)
        .order_by(
            OfficialFixingVersion.deal_event_id,
            OfficialFixingVersion.version.desc(),
        )
    ).all()
    versions_by_event: dict[int, list[dict]] = {}
    for version in versions:
        versions_by_event.setdefault(version.deal_event_id, []).append(
            _fixing_version_row(version))
    for event in row.get("events", []):
        event["fixing_versions"] = versions_by_event.get(event["id"], [])
    row["terms"] = ([{"label": "Contrat", "value": deal.product_type if template else "Exotique natif · ACT/365F"}]
                    if native else _deal_terms(deal))
    row["flags"] = {} if native else _script_flags(deal)
    row["lifecycle_proposals"] = [
        _proposal_row(p) for p in _get_lifecycle_proposals(deal_id, session)]
    row["amendment_requests"] = [
        _amendment_row(request) for request in session.exec(
            select(TradeAmendmentRequest)
            .where(TradeAmendmentRequest.deal_id == deal_id)
            .order_by(TradeAmendmentRequest.created_at.desc())
        ).all()
    ]
    return row


@router.get("/{deal_id}/audit")
def get_deal_audit(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    action: Optional[str] = None,
    result: Optional[str] = None,
    limit: int = 250,
):
    """Searchable business timeline for one owned deal and its child objects."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    events = _get_events(deal_id, session)
    proposals = _get_lifecycle_proposals(deal_id, session)
    amendments = session.exec(select(TradeAmendmentRequest).where(
        TradeAmendmentRequest.deal_id == deal_id)).all()
    # Legacy SQLite databases may already have recycled Deal, DealEvent or
    # proposal ids after an administrative deletion.  The current trade cannot
    # own any audit row written before it existed.  Keep this lower bound even
    # though new Deal ids are now allocated durably: it repairs the timeline of
    # databases that predate that allocator.
    since_booking = AuditEvent.created_at >= deal.created_at
    clauses = [
        (AuditEvent.object_type == "DEAL")
        & (AuditEvent.object_id == deal_id)
        & since_booking,
    ]
    if deal.rfq_id:
        linked_rfq = session.get(RfqRequest, deal.rfq_id)
        rfq_clause = (
            (AuditEvent.object_type == "RFQ") &
            (AuditEvent.object_id == deal.rfq_id)
        )
        # Legacy SQLite databases may have reused an RFQ primary key after a
        # physical deletion.  Events older than the linked RFQ cannot belong
        # to it and must not contaminate the deal timeline.
        if linked_rfq is not None:
            rfq_clause &= AuditEvent.created_at >= linked_rfq.created_at
        clauses.append(rfq_clause)
    if events:
        clauses.append(
            (AuditEvent.object_type == "DEAL_EVENT") &
            (AuditEvent.object_id.in_([row.id for row in events])) &
            since_booking)
    if proposals:
        clauses.append(
            (AuditEvent.object_type == "LIFECYCLE_PROPOSAL") &
            (AuditEvent.object_id.in_([row.id for row in proposals])) &
            since_booking)
    if amendments:
        clauses.append(
            (AuditEvent.object_type == "TRADE_AMENDMENT_REQUEST") &
            (AuditEvent.object_id.in_([row.id for row in amendments])) &
            since_booking)
    statement = select(AuditEvent).where(or_(*clauses))
    if action:
        statement = statement.where(AuditEvent.action == action)
    if result:
        statement = statement.where(AuditEvent.result == result)
    safe_limit = max(1, min(limit, 1000))
    rows = session.exec(
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(safe_limit)
    ).all()
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "count": len(rows),
        "items": [_audit_row(row) for row in rows],
    }


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
    requested = body.model_dump(exclude_unset=True)
    if requested:
        def current_value(field: str):
            if field == "underlyings":
                return json.loads(deal.underlyings_json or "[]")
            if field == "market_snapshot":
                return json.loads(deal.market_snapshot_json or "{}")
            if field == "observation_times":
                # Relevé rows are not observation times: the booked
                # observation_times never contained them.
                return [event.t_years for event in _get_events(deal.id, session)
                        if event.t_years > 0 and event.parent_event_id is None]
            if field == "selected_quote_id":
                provenance = json.loads(deal.rfq_provenance_json or "{}")
                return (provenance.get("retained") or {}).get("quote_id")
            return getattr(deal, field, None)

        before = {field: current_value(field) for field in requested}
        commit_rejection(
            session,
            action="POST_BOOKING_MODIFICATION_REJECTED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=current.id,
            before=before,
            after=requested,
            reason="Les champs contractuels d'un deal booké sont immuables ; "
                   "utilisez le futur workflow d'amendement.",
            metadata={"fields": sorted(requested)},
        )
        raise HTTPException(409, {
            "code": "POST_BOOKING_IMMUTABLE",
            "message": "Modification directe refusée : ce deal est déjà booké.",
            "fields": sorted(requested),
        })
    return _deal_row(deal)
