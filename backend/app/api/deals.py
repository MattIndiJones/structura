"""Deal booking and lifecycle management."""
from __future__ import annotations
import base64
import binascii
import json
import hashlib
import math
import re
from datetime import datetime, date, timedelta, timezone
from typing import Annotated, Literal, Optional, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import (Alert, AuditEvent, Deal, DealContractVersion, DealEvent,
                          Entity, User, Counterparty, Portfolio, LifecycleProposal,
                          OfficialFixingVersion, RfqQuote, RfqRequest, Script,
                          TradeAmendmentRequest)
from .auth import get_current_user
from ..services.market_data import load_hist_prices, load_yahoo_reference_closes
from ..core.payscript.parser import parse_script, resolve_constats, CompiledScript, effective_T_max
from ..core.payscript.engine import eval_script_on_history
from ..core.inlife_valuation import (
    InLifeProduct, ValuationError, build_residual,
    _engine_underlyings, _shift_dividend_curve,
)
from ..core.calibration import realized_market
from ..core.references import next_reference
from ..core.audit import commit_rejection, record_audit_event
from ..core.lifecycle_controls import (
    official_input_hash, replay_official_fixings, semantic_maturity_outcome,
)
from ..core.market_snapshot import snapshot_rate, snapshot_rate_is_default
from ..core.rfq_controls import (
    booking_gate_failures, failures_payload, product_terms, product_terms_hash,
)
from ..core.workflow import (
    AmendmentStatus, DataCategory, FixingPolicy, FixingStatus, LifecycleStatus,
    amendment_four_eyes_enabled,
)
from ..core.schemas import ReinvestScanRequest, ReinvestProposalRequest

router = APIRouter(prefix="/api/deals", tags=["deals"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class DealCreate(BaseModel):
    sens: Literal["achat", "vente"] = "vente"
    contrepartie: str
    devise: str = "EUR"
    product_type: str = ""
    fixing_policy: Literal["AUTO_YAHOO", "FOUR_EYES"] = "AUTO_YAHOO"
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
    # Winning RFQ response this deal was booked from, if any — see
    # db/models.py:Deal.rfq_id.
    rfq_id: Optional[int] = None


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


class EventUpdate(BaseModel):
    spots: dict
    source: Literal["manuel"] = "manuel"
    status: Optional[str] = None
    provider: str = ""
    source_type: str = ""
    external_reference: str = ""
    observed_at: str = ""
    venue: str = ""
    calendar: str = ""
    timezone: str = ""
    evidence_sha256: str = ""
    evidence_filename: str = ""
    evidence_content_type: str = "application/octet-stream"
    evidence_payload_b64: str = ""
    reason: str = ""
    supersedes_version: Optional[int] = None


class FixingValidationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AutoFixingExceptionResolutionRequest(BaseModel):
    """One-person decision for an AUTO_YAHOO fixing exception.

    The expected version is an optimistic lock: the UI must resolve exactly
    the version it displayed.  A concurrent capture or provider revision
    therefore fails closed instead of being silently overwritten.
    """
    action: Literal["USE_YAHOO", "CONFIRM_CURRENT", "REPLACE_MANUAL"]
    expected_version_id: Optional[int] = None
    spots: Optional[dict] = None
    source_reference: str = Field(default="", max_length=500)
    # Taking the automatic source is not a deviation, so it carries no written
    # justification: the signature exists to record *departures* from Yahoo,
    # and demanding a motive to accept the default inverted that — an operator
    # had to write ten characters to agree with the machine. The actor, the
    # action and its timestamp are audited either way. The two actions that do
    # override the automatic source keep the requirement, and so does a
    # USE_YAHOO that overrides a soft control (enforced in the handler, where
    # the control outcome is known).
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _motive_required_when_overriding(self):
        if self.action != "USE_YAHOO" and len(self.reason.strip()) < 10:
            raise ValueError(
                "Le motif est obligatoire (10 caractères minimum) pour toute "
                "décision qui écarte la source automatique.")
        return self


class LifecycleValidationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    confirmed_outcome: Optional[Literal["callé", "ki", "final"]] = None


class AmendmentRequestCreate(BaseModel):
    field_name: Literal[
        "nominal", "devise", "contrepartie", "price_traded", "status",
        "trade_date", "strike_date", "value_date", "maturity_date",
        "payment_date", "script_snapshot", "market_snapshot",
    ]
    new_value: object
    reason: str = Field(min_length=10, max_length=2000)


class AmendmentDecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


# ── Helpers ───────────────────────────────────────────────────────────

def _date_plus_years(d: str, years: float) -> str:
    return (date.fromisoformat(d) + timedelta(days=round(years * 365.25))).isoformat()


def _years_between(start: str, end: str) -> float:
    """Inverse of _date_plus_years, same 365.25-day year."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days / 365.25


def _validate_economics(body) -> None:
    """Refuse what is not a trade. The booking form checks part of this, but
    the form is not the boundary — the API is, and it accepted a deal with a
    negative nominal (which then SUBTRACTS from counterparty exposure in
    api/portfolios.py), a fair value of zero (every later MtM is measured
    against it), a settlement before its own strike, or a maturity in 2020.

    Deliberately NOT checked: a counterparty outside the catalog (the field is
    a free string on purpose — see models.py:Counterparty, booked history must
    stay readable after a rename), and a strike far in the past (booking an
    old trade after the fact is legitimate)."""
    errors = []
    if not body.contrepartie or not body.contrepartie.strip():
        errors.append("la contrepartie est obligatoire")
    if body.nominal is None or body.nominal <= 0:
        errors.append(f"le nominal doit être strictement positif (reçu : {body.nominal})")
    if not body.fair_value:
        errors.append("la fair value est nulle — le P&L du deal se mesurerait contre zéro "
                      "(lancez ▶ Pricer, ou saisissez-la)")
    elif body.fair_value < 0:
        errors.append(f"la fair value ne peut pas être négative (reçu : {body.fair_value})")
    if not body.price_traded or body.price_traded <= 0:
        errors.append(f"le prix traité doit être strictement positif (reçu : {body.price_traded})")

    if body.T is None or body.T <= 0:
        errors.append(f"la maturité en années T doit être strictement positive (reçu : {body.T})")
    if not body.script_snapshot or not body.script_snapshot.strip():
        errors.append("le script contractuel est obligatoire")
    if not body.underlyings:
        errors.append("au moins un sous-jacent est obligatoire")
    if len(body.devise or "") != 3 or not body.devise.isalpha():
        errors.append(f"la devise doit être un code ISO à trois lettres (reçu : {body.devise!r})")
    body_ul_ids = [
        (str(u.get("name") or "").strip(), str(u.get("ticker") or "").strip(),
         str(u.get("ccy") or body.devise).strip().upper())
        for u in body.underlyings
    ]
    if len(set(body_ul_ids)) != len(body_ul_ids):
        errors.append("la liste des sous-jacents contient des doublons")
    market_uls = (body.market_snapshot or {}).get("underlyings") or []
    if market_uls:
        market_ul_ids = [
            (str(u.get("name") or "").strip(), str(u.get("ticker") or "").strip(),
             str(u.get("ccy") or body.devise).strip().upper())
            for u in market_uls
        ]
        if market_ul_ids != body_ul_ids:
            errors.append("les sous-jacents du deal et du snapshot de marché divergent")

    parsed_dates = {}
    for label, raw in (("trade", body.trade_date), ("strike", body.strike_date),
                       ("valeur", body.value_date), ("maturité", body.maturity_date),
                       ("règlement", body.payment_date)):
        if not raw and label == "règlement":
            continue
        try:
            parsed_dates[label] = date.fromisoformat(raw)
        except (TypeError, ValueError):
            errors.append(f"la date de {label} est invalide ({raw!r})")

    if body.strike_date and body.value_date and body.value_date < body.strike_date:
        errors.append(f"la date de valeur ({body.value_date}) précède la date de strike "
                      f"({body.strike_date})")
    if body.maturity_date and body.value_date and body.maturity_date <= body.value_date:
        errors.append(f"la maturité ({body.maturity_date}) n'est pas postérieure à la date "
                      f"de valeur ({body.value_date})")
    if body.payment_date and body.maturity_date and body.payment_date < body.maturity_date:
        errors.append(f"le règlement ({body.payment_date}) précède la maturité "
                      f"({body.maturity_date})")
    if errors:
        raise HTTPException(422, "Booking impossible : " + " ; ".join(errors) + ".")


def _deal_product_terms(body: DealCreate) -> dict:
    """Canonical contractual identity presented by a deal booking request."""
    market = body.market_snapshot or {}
    params = {
        "underlyings": market.get("underlyings") or body.underlyings,
        "user_params": market.get("user_params") or {},
        "constats": market.get("constats") or {},
        "notional": body.nominal,
        "currency": body.devise,
        "strike_date": body.strike_date,
        "value_date": body.value_date,
        # La date de reglement final fait partie de l identite du produit : deux
        # deals identiques regles a deux dates differentes ne valent pas le meme
        # prix, l ecart se compte en points de base.
        "payment_date": body.payment_date,
        "T": body.T,
    }
    return product_terms(body.script_snapshot, params)


def _validate_rfq_booking_identity(rfq: RfqRequest, body: DealCreate,
                                   session: Session) -> None:
    """Refuse a deal that merely points at an RFQ but is not its product."""
    from .rfq import _counterparty_by_provider, superseded_quote_ids

    quotes = session.exec(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id)).all()
    selected = next((q for q in quotes if q.id == rfq.selected_quote_id), None)
    if not selected or selected.price is None:
        raise HTTPException(422, "La réponse retenue doit porter un prix final avant booking.")
    if selected.status in {"decline", "expire"}:
        raise HTTPException(422, "La réponse retenue n'est plus exécutable.")
    if selected.id in superseded_quote_ids(quotes):
        raise HTTPException(422, "La réponse retenue a été remplacée par un last look final.")
    if rfq.status == "sans_suite":
        raise HTTPException(409, "Une RFQ classée sans suite doit être rouverte avant booking.")

    expected_sens = "vente" if rfq.sens == "achat" else "achat"
    if body.sens != expected_sens:
        raise HTTPException(
            422, f"Le sens du deal ({body.sens}) ne correspond pas au sens de la RFQ "
                 f"({rfq.sens}, donc deal attendu : {expected_sens}).")

    expected_counterparty = _counterparty_by_provider(session).get(selected.provider)
    if expected_counterparty and body.contrepartie != expected_counterparty:
        raise HTTPException(
            422, f"La contrepartie du deal ({body.contrepartie}) ne correspond pas au "
                 f"fournisseur retenu ({selected.provider} → {expected_counterparty}).")

    expected = product_terms(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
    actual_all = _deal_product_terms(body)
    actual = {key: actual_all.get(key) for key in expected}
    if actual != expected:
        changed = sorted(key for key in expected if actual.get(key) != expected.get(key))
        raise HTTPException(
            422, "Le deal ne correspond pas aux termes contractuels figés de la RFQ : "
                 + ", ".join(changed) + ". Rechargez le booking depuis la RFQ ; "
                 "pour un autre produit, créez une nouvelle RFQ.")


def _derive_observation_times(body) -> List[float]:
    """The deal's observation schedule, read off the product itself rather than
    off a pricing run.

    The client derives it from the last Monte Carlo's flux table, which fails
    in two ways. It is EMPTY when nothing was priced in the session — booking
    straight from an RFQ prefill (which clears results on purpose) produced a
    deal whose only event was the strike, so no barrier watchlist, no residual
    MtM and no automatic resolution, silently. And when it is filled, its times
    are the simulation's WEEKLY GRID steps (0.9808 = 51/52), not the calendar's
    (0.9884): a 3-day drift on every observation date the lifecycle then works
    from.

    Resolving the script's own calendar gives both — the true contractual
    dates, and no dependency on having clicked ▶ Pricer."""
    compiled = parse_script(body.script_snapshot)
    market = body.market_snapshot or {}
    # Ancré sur la constatation initiale, pas sur le règlement : le produit
    # commence quand son niveau de référence est fixé. Repli sur la value date
    # pour les bookings qui n'ont pas encore de date de strike.
    origin = body.strike_date or body.value_date
    compiled = resolve_constats(
        compiled, market.get("constats") or {},
        anchor=date.fromisoformat(origin) if origin else None,
        currency=(body.devise or "").strip().upper() or None,
    )
    # AT_MATURITY carries no date of its own: it fires at the end of the
    # horizon. Which end? The deal's OWN maturity date, not the tenor typed in
    # the pricing form — the two diverge as soon as a CONSTAT calendar is in
    # play, since the form keeps a round 3.0 while the calendar ends at 2.9897.
    # Reading the horizon off body.T put the redemption 4 days AFTER the
    # maturity the deal itself declares, and added a fifth observation line to
    # a product that has four. A coupon calendar shorter than the note (2Y of
    # coupons on a 3Y maturity) stays correct: its maturity date is the 3Y one.
    horizon = body.T
    # Mesure depuis la MEME origine que les constatations resolues ci-dessus :
    # la date de strike. Compter l horizon depuis la value date alors que les
    # observations partent du strike decalerait le remboursement de l ecart
    # entre les deux dates.
    if body.maturity_date and origin:
        from_maturity = _years_between(origin, body.maturity_date)
        if from_maturity > 0:
            horizon = from_maturity
    T_eff = effective_T_max(compiled, horizon)
    times = set()
    for ev in compiled.events:
        if ev.type == "AT_MATURITY":
            times.add(round(T_eff, 4))
        for d in (ev.dates or []):
            times.add(round(d, 4))
    # t=0 is the strike/fixing line, added separately by book_deal.
    return sorted(t for t in times if t > 0)


def _rfq_provenance(rfq, price_traded: float, session: Session) -> str:
    """Freeze the tender's competitive picture onto the deal: the retained
    response, every rival price it beat, and our own model price at the time.
    Stored as JSON on the deal (Deal.rfq_provenance_json) rather than looked
    up through rfq_id on demand, because the RFQ keeps living afterwards —
    a price corrected or a quote deleted would silently rewrite the
    justification of a trade already done.

    price_traded is carried alongside the retained quote's price rather than
    validated against it: the two legitimately differ (last-minute
    negotiation, fees, rounding). Recording the gap documents it; refusing it
    would block real bookings."""
    from .rfq import superseded_quote_ids

    quotes = session.exec(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id)).all()
    superseded = superseded_quote_ids(quotes)
    won = next((q for q in quotes if q.id == rfq.selected_quote_id), None)
    frozen_terms = product_terms(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
    return json.dumps({
        "rfq_id": rfq.id,
        "reference": rfq.reference,
        "sens": rfq.sens,
        "kind": rfq.kind,
        "model_price": rfq.model_price,
        "model_price_at": rfq.model_price_at.isoformat() if rfq.model_price_at else None,
        "booked_at": datetime.utcnow().isoformat(),
        "price_traded": price_traded,
        "product_terms": frozen_terms,
        "product_terms_sha256": product_terms_hash(frozen_terms),
        "retained": {
            "provider": won.provider, "price": won.price,
            "is_last_look": won.parent_quote_id is not None,
            "quoted_at": won.quoted_at.isoformat() if won.quoted_at else None,
        } if won else None,
        # Only final answers: a superseded quote is the same bank's earlier
        # price, not a competitor (see rfq.py:superseded_quote_ids).
        "competition": sorted(
            [{"provider": q.provider, "price": q.price}
             for q in quotes
             if q.id not in superseded and q.id != rfq.selected_quote_id and q.price is not None],
            key=lambda x: x["price"],
        ),
    }, ensure_ascii=False)


def _gen_ref(entity_name: str | None, session: Session) -> str:
    prefix = ((entity_name or "DEAL")[:4].upper().replace(" ", "").ljust(4, "X"))
    return next_reference(session, Deal, f"{prefix}-{date.today().strftime('%Y%m%d')}-")


def _deal_row(d: Deal, events: list | None = None) -> dict:
    row = {
        "id": d.id,
        "reference": d.reference,
        "entity_id": d.entity_id,
        "user_id": d.user_id,
        "indicative_id": d.indicative_id,
        "rfq_id": d.rfq_id,
        # Frozen best-execution record — see _rfq_provenance. None outside
        # the tender path.
        "rfq_provenance": json.loads(d.rfq_provenance_json) if d.rfq_provenance_json else None,
        "portfolio_id": d.portfolio_id,
        "sens": d.sens,
        "contrepartie": d.contrepartie,
        "devise": d.devise,
        "product_type": d.product_type,
        "fixing_policy": d.fixing_policy,
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
        "greeks": json.loads(d.greeks_json) if d.greeks_json else {},
        "greeks_computed_at": d.greeks_computed_at.isoformat() if d.greeks_computed_at else None,
        "status": d.status,
        "contract_version": d.contract_version,
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
        "indicative_spots": json.loads(e.indicative_spots_json or "{}"),
        "source": e.source,
        "status": e.status,
        "fixing_status": e.fixing_status,
        "data_category": e.data_category,
        "current_fixing_version_id": e.current_fixing_version_id,
        "fixing_version": e.fixing_version,
        "fixing_entered_by": e.fixing_entered_by,
        "fixing_entered_at": (
            e.fixing_entered_at.isoformat() if e.fixing_entered_at else None),
        "fixing_provider": e.fixing_provider,
        "fixing_source_type": e.fixing_source_type,
        "fixing_external_reference": e.fixing_external_reference,
        "fixing_observed_at": (
            e.fixing_observed_at.isoformat() if e.fixing_observed_at else None),
        "fixing_venue": e.fixing_venue,
        "fixing_calendar": e.fixing_calendar,
        "fixing_timezone": e.fixing_timezone,
        "fixing_evidence_sha256": e.fixing_evidence_sha256,
        "fixing_record_sha256": e.fixing_record_sha256,
        "fixing_reason": e.fixing_reason,
        "validated_by": e.validated_by,
        "validated_at": e.validated_at.isoformat() if e.validated_at else None,
        "applied_at": e.applied_at.isoformat() if e.applied_at else None,
        "label": e.label,
    }


def _get_events(deal_id: int, session: Session) -> list:
    return session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal_id)
        .order_by(DealEvent.event_index)
    ).all()


def _fixing_version_row(version: OfficialFixingVersion) -> dict:
    return {
        "id": version.id,
        "deal_event_id": version.deal_event_id,
        "version": version.version,
        "supersedes_id": version.supersedes_id,
        "status": version.status,
        "spots": json.loads(version.spots_json or "{}"),
        "provider": version.provider,
        "source_type": version.source_type,
        "external_reference": version.external_reference,
        "observed_at": version.observed_at.isoformat(),
        "received_at": version.received_at.isoformat(),
        "venue": version.venue,
        "calendar": version.calendar,
        "timezone": version.timezone,
        "evidence_sha256": version.evidence_sha256,
        "evidence_filename": version.evidence_filename,
        "evidence_content_type": version.evidence_content_type,
        "evidence_size_bytes": version.evidence_size_bytes,
        "record_sha256": version.record_sha256,
        "capture_reason": version.capture_reason,
        "capture_actor_type": version.capture_actor_type,
        "entered_by": version.entered_by,
        "validated_by": version.validated_by,
        "validation_reason": version.validation_reason,
        "validated_at": (
            version.validated_at.isoformat() if version.validated_at else None),
        "rejected_by": version.rejected_by,
        "rejection_reason": version.rejection_reason,
        "rejected_at": version.rejected_at.isoformat() if version.rejected_at else None,
        "applied_at": version.applied_at.isoformat() if version.applied_at else None,
        "created_at": version.created_at.isoformat(),
    }


def _proposal_row(proposal: LifecycleProposal) -> dict:
    return {
        "id": proposal.id,
        "deal_id": proposal.deal_id,
        "event_id": proposal.event_id,
        "status": proposal.status,
        "proposed_outcome": proposal.proposed_outcome,
        "result": json.loads(proposal.result_json or "{}"),
        "data_source": proposal.data_source,
        "official_result": (
            json.loads(proposal.official_result_json)
            if proposal.official_result_json else None),
        "official_input_hash": proposal.official_input_hash,
        "official_replayed_at": (
            proposal.official_replayed_at.isoformat()
            if proposal.official_replayed_at else None),
        "comparison_status": proposal.comparison_status,
        "validated_by": proposal.validated_by,
        "validation_reason": proposal.validation_reason,
        "validated_at": proposal.validated_at.isoformat() if proposal.validated_at else None,
        "applied_by": proposal.applied_by,
        "applied_at": proposal.applied_at.isoformat() if proposal.applied_at else None,
        "error_message": proposal.error_message,
        "correlation_id": proposal.correlation_id,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }


def _get_lifecycle_proposals(deal_id: int, session: Session) -> list[LifecycleProposal]:
    return session.exec(
        select(LifecycleProposal).where(LifecycleProposal.deal_id == deal_id)
        .order_by(LifecycleProposal.created_at.desc())
    ).all()


def _amendment_row(request: TradeAmendmentRequest) -> dict:
    return {
        "id": request.id,
        "deal_id": request.deal_id,
        "field_name": request.field_name,
        "old_value": json.loads(request.old_value_json),
        "new_value": json.loads(request.new_value_json),
        "reason": request.reason,
        "requested_by": request.requested_by,
        "status": request.status,
        "base_contract_version": request.base_contract_version,
        "validated_by": request.validated_by,
        "validated_at": request.validated_at.isoformat() if request.validated_at else None,
        "decision_reason": request.decision_reason,
        "rejected_by": request.rejected_by,
        "rejected_at": request.rejected_at.isoformat() if request.rejected_at else None,
        "applied_by": request.applied_by,
        "applied_at": request.applied_at.isoformat() if request.applied_at else None,
        "applied_contract_version": request.applied_contract_version,
        "created_at": request.created_at.isoformat(),
    }


def _audit_row(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "actor_user_id": event.actor_user_id,
        "actor_type": event.actor_type,
        "result": event.result,
        "before": json.loads(event.before_json or "{}"),
        "after": json.loads(event.after_json or "{}"),
        "reason": event.reason,
        "data_source": event.data_source,
        "correlation_id": event.correlation_id,
        "metadata": json.loads(event.metadata_json or "{}"),
        "created_at": event.created_at.isoformat(),
    }


def _contract_snapshot(deal: Deal) -> dict:
    """Contractual fields only; valuation state is deliberately excluded."""
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "contract_version": deal.contract_version,
        "sens": deal.sens,
        "contrepartie": deal.contrepartie,
        "devise": deal.devise,
        "nominal": deal.nominal,
        "fair_value": deal.fair_value,
        "price_traded": deal.price_traded,
        "product_type": deal.product_type,
        "fixing_policy": deal.fixing_policy,
        "trade_date": deal.trade_date,
        "strike_date": deal.strike_date,
        "value_date": deal.value_date,
        "maturity_date": deal.maturity_date,
        "payment_date": deal.payment_date,
        "T": deal.T,
        "underlyings": json.loads(deal.underlyings_json or "[]"),
        "script_snapshot": deal.script_snapshot,
        "market_snapshot": json.loads(deal.market_snapshot_json or "{}"),
        "status": deal.status,
    }


_IN_PLACE_AMENDMENT_FIELDS = {
    "nominal", "contrepartie", "price_traded", "payment_date",
}


def _validated_amendment_value(deal: Deal, request: TradeAmendmentRequest):
    field = request.field_name
    value = json.loads(request.new_value_json)
    if field not in _IN_PLACE_AMENDMENT_FIELDS:
        raise HTTPException(422, {
            "code": "AMENDMENT_REBOOK_REQUIRED",
            "message": (
                "Ce changement affecte le contrat, le pricing ou le calendrier. "
                "Il doit être traité par annulation/remplacement contrôlé, pas "
                "par modification en place."
            ),
            "field": field,
        })
    if field in {"nominal", "price_traded"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "La nouvelle valeur doit être strictement positive.",
            })
        return float(value)
    if field == "contrepartie":
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "La contrepartie ne peut pas être vide.",
            })
        return value.strip()
    if field == "payment_date":
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "La date de paiement doit être au format ISO YYYY-MM-DD.",
            })
        if parsed < date.fromisoformat(deal.maturity_date):
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "La date de paiement ne peut pas précéder la maturité.",
            })
        return value
    raise HTTPException(422, {"code": "AMENDMENT_VALUE_INVALID", "field": field})


def _deal_entity_id(deal: Deal, session: Session) -> int | None:
    if deal.entity_id is not None:
        return deal.entity_id
    owner = session.get(User, deal.user_id)
    return owner.entity_id if owner else None


def _can_access_deal(deal: Deal, current: User, session: Session) -> bool:
    if deal.user_id == current.id or getattr(current, "role", None) == "admin":
        return True
    return (
        getattr(current, "role", None) in {"ops_maker", "checker"} and
        current.entity_id is not None and
        current.entity_id == _deal_entity_id(deal, session)
    )


def _workflow_failure(
    code: str,
    field: str,
    message: str,
    *,
    expected: str | None = None,
    action: str | None = None,
    received=None,
) -> dict:
    row = {"code": code, "field": field, "message": message, "blocking": True}
    if expected is not None:
        row["expected"] = expected
    if action is not None:
        row["action"] = action
    if received is not None:
        row["received"] = received
    return row


def _reject_workflow_action(
    session: Session,
    *,
    action: str,
    object_type: str,
    object_id: int | None,
    current: User,
    message: str,
    failures: list[dict],
    status_code: int = 422,
    before: dict | None = None,
) -> None:
    detail = {
        "code": action,
        "message": message,
        "failures": failures,
    }
    commit_rejection(
        session,
        action=action,
        object_type=object_type,
        object_id=object_id,
        actor_user_id=current.id,
        before=before,
        reason=message,
        metadata={"failures": failures},
    )
    raise HTTPException(status_code, detail)


def _ops_deal(
    deal_id: int,
    current: User,
    session: Session,
    *,
    allowed_roles: set[str],
    action: str,
) -> Deal:
    deal = session.get(Deal, deal_id)
    if not deal:
        raise HTTPException(404, "Deal introuvable")
    entity_id = _deal_entity_id(deal, session)
    if current.entity_id is None or current.entity_id != entity_id:
        raise HTTPException(404, "Deal introuvable")
    if getattr(current, "role", None) not in allowed_roles:
        role_label = "Ops Maker" if allowed_roles == {"ops_maker"} else "Ops Checker"
        _reject_workflow_action(
            session,
            action=action,
            object_type="DEAL",
            object_id=deal.id,
            current=current,
            message="Votre rôle ne permet pas cette action lifecycle.",
            failures=[_workflow_failure(
                "WORKFLOW_ROLE_REQUIRED",
                "user.role",
                f"Cette action est réservée au rôle {role_label} de l’entité du deal.",
                expected=role_label,
                received=getattr(current, "role", None),
                action=f"Demandez à un {role_label} habilité de traiter cette étape.",
            )],
            status_code=403,
        )
    return deal


_FIXING_SOURCE_TYPES = {
    "API", "MESSAGE", "FILE", "PLATFORM", "CALCULATION_AGENT", "OTHER",
}
_FIXING_PROVIDERS = {
    "BLOOMBERG",
    "REFINITIV",
    "OFFICIAL_EXCHANGE",
    "CALCULATION_AGENT",
    "ISSUER_AGENT",
    "CUSTODIAN",
}
_MAX_FIXING_EVIDENCE_BYTES = 5 * 1024 * 1024


def _decode_fixing_evidence(body: EventUpdate) -> tuple[bytes | None, list[dict]]:
    failures: list[dict] = []
    filename = str(body.evidence_filename or "").strip()
    if not filename or len(filename) > 255 or "/" in filename or "\\" in filename:
        failures.append(_workflow_failure(
            "FIXING_EVIDENCE_FILENAME_INVALID",
            "evidence_filename",
            "Le nom de la pièce source est absent ou invalide.",
            expected="Un nom de fichier simple de 1 à 255 caractères.",
            action="Sélectionnez à nouveau la pièce source officielle.",
            received=filename or None,
        ))
    content_type = str(body.evidence_content_type or "").strip()
    if not re.fullmatch(
        r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type
    ):
        failures.append(_workflow_failure(
            "FIXING_EVIDENCE_CONTENT_TYPE_INVALID",
            "evidence_content_type",
            "Le type de contenu de la pièce source est absent ou invalide.",
            expected="Un type MIME, par exemple application/pdf ou text/csv.",
            action="Sélectionnez à nouveau la pièce source officielle.",
            received=content_type or None,
        ))
    try:
        payload = base64.b64decode(
            str(body.evidence_payload_b64 or ""), validate=True)
    except (binascii.Error, ValueError):
        payload = None
        failures.append(_workflow_failure(
            "FIXING_EVIDENCE_PAYLOAD_INVALID",
            "evidence_payload_b64",
            "La pièce source n’est pas un payload Base64 valide.",
            expected="Le contenu intégral de la pièce source encodé en Base64.",
            action="Sélectionnez à nouveau la pièce ; ne saisissez pas le hash manuellement.",
        ))
    if payload is not None:
        if not payload:
            failures.append(_workflow_failure(
                "FIXING_EVIDENCE_PAYLOAD_EMPTY",
                "evidence_payload_b64",
                "La pièce source archivée est vide.",
                expected="Une pièce non vide.",
                action="Sélectionnez le message, fichier ou export officiel reçu.",
            ))
        elif len(payload) > _MAX_FIXING_EVIDENCE_BYTES:
            failures.append(_workflow_failure(
                "FIXING_EVIDENCE_PAYLOAD_TOO_LARGE",
                "evidence_payload_b64",
                "La pièce source dépasse la taille autorisée.",
                expected=f"Au maximum {_MAX_FIXING_EVIDENCE_BYTES // (1024 * 1024)} Mo.",
                action="Archivez un export plus compact ou fractionnez la preuve.",
                received=len(payload),
            ))
        calculated = hashlib.sha256(payload).hexdigest()
        declared = str(body.evidence_sha256 or "").strip().lower()
        if declared != calculated:
            failures.append(_workflow_failure(
                "FIXING_EVIDENCE_HASH_MISMATCH",
                "evidence_sha256",
                "Le hash déclaré ne correspond pas à la pièce source archivée.",
                expected="Le SHA-256 recalculé automatiquement depuis la pièce archivée.",
                action="Sélectionnez à nouveau la pièce et laissez l’interface recalculer le hash.",
                received=("SHA-256 déclaré (64 caractères)" if declared else None),
            ))
    return payload, failures


def _parse_official_observed_at(raw: str, timezone_name: str) -> tuple[datetime | None, list[dict]]:
    failures: list[dict] = []
    try:
        observed = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None, [_workflow_failure(
            "FIXING_OBSERVED_AT_INVALID",
            "observed_at",
            "La date/heure d’observation est absente ou invalide.",
            expected="Date-heure ISO avec timezone, par exemple 2026-07-31T17:30:00+02:00.",
            action="Renseignez le timestamp publié par la source officielle.",
            received=raw or None,
        )]
    if observed.utcoffset() is None:
        failures.append(_workflow_failure(
            "FIXING_OBSERVED_AT_TIMEZONE_MISSING",
            "observed_at",
            "Le timestamp d’observation ne précise pas son décalage horaire.",
            expected="Date-heure ISO avec offset UTC.",
            action="Ajoutez l’offset, par exemple +02:00 ou Z.",
            received=raw,
        ))
    try:
        market_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        failures.append(_workflow_failure(
            "FIXING_TIMEZONE_INVALID",
            "timezone",
            "La timezone de marché est absente ou inconnue.",
            expected="Timezone IANA, par exemple Europe/Zurich.",
            action="Sélectionnez la timezone contractuelle du fixing.",
            received=timezone_name or None,
        ))
    else:
        if observed.utcoffset() is not None:
            market_offset = observed.astimezone(market_timezone).utcoffset()
            if observed.utcoffset() != market_offset:
                failures.append(_workflow_failure(
                    "FIXING_TIMEZONE_OFFSET_MISMATCH",
                    "observed_at",
                    "L’offset du timestamp ne correspond pas à la timezone de marché à cette date.",
                    expected=(
                        f"Offset {market_offset} pour la timezone {timezone_name}."),
                    action="Corrigez l’offset du timestamp ou sélectionnez la timezone contractuelle correcte.",
                    received=str(observed.utcoffset()),
                ))
    return observed, failures


def _fixing_submission_failures(
    deal: Deal,
    event: DealEvent,
    body: EventUpdate,
) -> tuple[list[dict], datetime | None]:
    # A partial candidate may be captured and remains explicitly PARTIAL, but
    # it can never pass Checker validation.  Provenance, however, is mandatory
    # from the first submitted version.
    failures: list[dict] = []
    required_text = (
        ("external_reference", body.external_reference, "la référence externe", "Saisissez l’identifiant du message, fichier ou batch."),
        ("venue", body.venue, "la place ou convention de marché", "Renseignez la place ou convention contractuelle."),
        ("calendar", body.calendar, "le calendrier contractuel", "Renseignez le calendrier utilisé."),
    )
    for field, value, label, action in required_text:
        if not str(value or "").strip():
            failures.append(_workflow_failure(
                f"FIXING_{field.upper()}_MISSING",
                field,
                f"{label.capitalize()} est absent.",
                expected=f"Une valeur non vide pour {label}.",
                action=action,
            ))
    provider = str(body.provider or "").strip().upper()
    if provider not in _FIXING_PROVIDERS:
        failures.append(_workflow_failure(
            "FIXING_PROVIDER_NOT_AUTHORIZED",
            "provider",
            "Le fournisseur n’appartient pas au référentiel de sources officielles autorisées.",
            expected=", ".join(sorted(_FIXING_PROVIDERS)),
            action="Sélectionnez un fournisseur autorisé ou faites mettre à jour le référentiel.",
            received=body.provider or None,
        ))
    source_type = str(body.source_type or "").strip().upper()
    if source_type not in _FIXING_SOURCE_TYPES:
        failures.append(_workflow_failure(
            "FIXING_SOURCE_TYPE_INVALID",
            "source_type",
            "Le type de source officielle est absent ou non autorisé.",
            expected=", ".join(sorted(_FIXING_SOURCE_TYPES)),
            action="Sélectionnez le type correspondant à la preuve reçue.",
            received=body.source_type or None,
        ))
    evidence = str(body.evidence_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", evidence):
        failures.append(_workflow_failure(
            "FIXING_EVIDENCE_HASH_INVALID",
            "evidence_sha256",
            "Le hash de la preuve est absent ou invalide.",
            expected="SHA-256 hexadécimal de 64 caractères.",
            action="Joignez la preuve ou recalculez son hash SHA-256.",
            received=evidence or None,
        ))
    _, evidence_failures = _decode_fixing_evidence(body)
    failures.extend(evidence_failures)
    if len(str(body.reason or "").strip()) < 10:
        failures.append(_workflow_failure(
            "FIXING_REASON_TOO_SHORT",
            "reason",
            "Le motif de capture est insuffisant.",
            expected="Au moins 10 caractères.",
            action="Décrivez l’origine et le contexte de la saisie.",
            received=body.reason or None,
        ))
    observed, observed_failures = _parse_official_observed_at(
        body.observed_at, str(body.timezone or "").strip())
    failures.extend(observed_failures)
    if observed and observed.utcoffset() is not None:
        observed_utc = observed.astimezone(timezone.utc)
        if observed_utc > datetime.now(timezone.utc) + timedelta(minutes=5):
            failures.append(_workflow_failure(
                "FIXING_OBSERVED_AT_FUTURE",
                "observed_at",
                "Le timestamp d’observation est dans le futur.",
                expected="Une date/heure déjà atteinte.",
                action="Corrigez le timestamp fourni par la source.",
                received=body.observed_at,
            ))
        try:
            market_date = observed.astimezone(ZoneInfo(body.timezone)).date()
            if market_date.isoformat() != event.event_date:
                failures.append(_workflow_failure(
                    "FIXING_EVENT_DATE_MISMATCH",
                    "observed_at",
                    "La date locale du fixing ne correspond pas à la date contractuelle de l’événement.",
                    expected=event.event_date,
                    action="Sélectionnez l’événement correct ou corrigez le timestamp/timezone.",
                    received=market_date.isoformat(),
                ))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    if event.event_date > date.today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_EVENT_IN_FUTURE",
            "event_date",
            "L’événement contractuel est encore futur.",
            expected="Une date d’événement atteinte.",
            action="Attendez la date de constatation officielle.",
            received=event.event_date,
        ))
    return failures, observed


def _fixing_record_payload(
    deal: Deal,
    event: DealEvent,
    body: EventUpdate,
    *,
    version: int,
    supersedes_id: int | None,
) -> dict:
    observed = datetime.fromisoformat(body.observed_at.replace("Z", "+00:00"))
    return {
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "event_index": event.event_index,
        "version": version,
        "supersedes_id": supersedes_id,
        "underlyings": json.loads(deal.underlyings_json or "[]"),
        "spots": body.spots,
        "provider": body.provider.strip().upper(),
        "source_type": body.source_type.strip().upper(),
        "external_reference": body.external_reference.strip(),
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "venue": body.venue.strip(),
        "calendar": body.calendar.strip(),
        "timezone": body.timezone.strip(),
        "evidence_sha256": body.evidence_sha256.strip().lower(),
        "evidence_filename": body.evidence_filename.strip(),
        "evidence_content_type": body.evidence_content_type.strip(),
        "evidence_size_bytes": len(base64.b64decode(body.evidence_payload_b64)),
        "capture_reason": body.reason.strip(),
    }


def _fixing_record_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checker_request(
    deal_id: int,
    request_id: int,
    current: User,
    session: Session,
) -> tuple[Deal, TradeAmendmentRequest]:
    deal = session.get(Deal, deal_id)
    request = session.get(TradeAmendmentRequest, request_id)
    if not deal or not request or request.deal_id != deal_id:
        raise HTTPException(404, "Demande d'amendement introuvable")

    if not amendment_four_eyes_enabled():
        # Single-signature mode: whoever may act on the deal may decide on its
        # amendments, including the maker. Every other guarantee still applies.
        if not _can_access_deal(deal, current, session):
            raise HTTPException(404, "Demande d'amendement introuvable")
        return deal, request

    if getattr(current, "role", None) not in {"checker", "admin"}:
        raise HTTPException(403, {
            "code": "CHECKER_ROLE_REQUIRED",
            "message": "Cette action est réservée à un checker ou administrateur.",
        })
    if current.role != "admin" and (
        current.entity_id is None or current.entity_id != _deal_entity_id(deal, session)
    ):
        raise HTTPException(404, "Demande d'amendement introuvable")
    if request.requested_by == current.id:
        commit_rejection(
            session,
            action="AMENDMENT_FOUR_EYES_REJECTED",
            object_type="TRADE_AMENDMENT_REQUEST",
            object_id=request.id,
            actor_user_id=current.id,
            before=_amendment_row(request),
            reason="Le maker ne peut ni approuver ni appliquer sa propre demande.",
            metadata={"deal_id": deal.id},
        )
        raise HTTPException(409, {
            "code": "FOUR_EYES_VIOLATION",
            "message": "Le checker doit être distinct du maker.",
        })
    return deal, request


def _booking_request_summary(body: DealCreate) -> dict:
    return {
        "rfq_id": body.rfq_id,
        "sens": body.sens,
        "contrepartie": body.contrepartie,
        "devise": body.devise,
        "nominal": body.nominal,
        "fair_value": body.fair_value,
        "price_traded": body.price_traded,
        "trade_date": body.trade_date,
        "strike_date": body.strike_date,
        "value_date": body.value_date,
        "maturity_date": body.maturity_date,
        "payment_date": body.payment_date,
        "T": body.T,
        "fixing_policy": body.fixing_policy,
    }


def _reject_booking(session: Session, current: User, body: DealCreate,
                    status_code: int, detail) -> None:
    """Persist the refusal before returning it; audit failure fails closed."""
    reason = (json.dumps(detail, ensure_ascii=False, sort_keys=True)
              if isinstance(detail, (dict, list)) else str(detail))
    commit_rejection(
        session,
        action="BOOKING_REJECTED",
        object_type="RFQ" if body.rfq_id else "DEAL",
        object_id=body.rfq_id,
        actor_user_id=current.id,
        after=_booking_request_summary(body),
        reason=reason,
        metadata={"http_status": status_code},
    )
    raise HTTPException(status_code, detail)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/next-ref")
def next_ref(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    return {"reference": _gen_ref(entity.name if entity else None, session)}


def _book_deal(
    body: DealCreate,
    current: User,
    session: Session,
    *,
    reference_prefix: str | None = None,
    uat_batch_id: int | None = None,
):
    from .portfolios import get_or_create_default_portfolio

    try:
        _validate_economics(body)
    except HTTPException as exc:
        _reject_booking(session, current, body, exc.status_code, exc.detail)

    # Validate the RFQ link BEFORE the deal exists: rfq_id is a best-execution
    # trail (which tender this trade came out of), so a stale or foreign id
    # must be refused outright rather than persisted on the deal and merely
    # skipped when closing the RFQ below.
    source_rfq = None
    rfq_provenance = None
    if body.rfq_id:
        source_rfq = session.get(RfqRequest, body.rfq_id)
        if not source_rfq or source_rfq.user_id != current.id:
            _reject_booking(session, current, body, 404, "RFQ introuvable")
        # Booking a tender closes it as "Bookée" — doing that without a
        # retained response would record a trade won by nobody, and leave the
        # analysis unable to tell who actually won (see api/rfq.py:/history).
        # One tender, one trade. Booking the same RFQ twice would produce two
        # deals both claiming to be THE execution of that competition, and
        # would double-count the winning bank's hit ratio (api/rfq.py:/history).
        already = session.exec(select(Deal).where(Deal.rfq_id == source_rfq.id)).first()
        if already:
            _reject_booking(
                session, current, body, 409,
                f"Cette RFQ a déjà été bookée — deal {already.reference}. "
                "Ouvrez-le depuis le Booking plutôt que d'en créer un second.")

        selected = session.get(RfqQuote, source_rfq.selected_quote_id) \
            if source_rfq.selected_quote_id else None
        from .rfq import _counterparty_by_provider
        expected_counterparty = (
            _counterparty_by_provider(session).get(selected.provider) if selected else None)
        gate_failures = booking_gate_failures(
            source_rfq, selected,
            expected_counterparty=expected_counterparty,
            requested_counterparty=body.contrepartie,
        )
        if gate_failures:
            _reject_booking(
                session, current, body, 422, failures_payload(gate_failures))
        try:
            _validate_rfq_booking_identity(source_rfq, body, session)
        except HTTPException as exc:
            _reject_booking(session, current, body, exc.status_code, exc.detail)
        rfq_provenance = _rfq_provenance(source_rfq, body.price_traded, session)

    # A new deal's script and frozen CONSTAT values are the contract.  Client
    # Monte-Carlo grid points are never a safe booking fallback.
    try:
        times = _derive_observation_times(body)
    except (ValueError, KeyError, TypeError) as e:
        _reject_booking(
            session, current, body, 422,
            f"Le calendrier contractuel du script est inexploitable : {e}. "
            "Corrigez les CONSTAT avant de booker.")
    if not times:
        # A deal with no observation has no life: no barrier watchlist, no
        # residual MtM, no automatic resolution. It used to be booked anyway
        # and stayed silently inert — an incoherent calendar (end before
        # start) reaches exactly this state.
        _reject_booking(
            session, current, body, 422,
            "Ce deal n'a aucune constatation — il ne pourrait être ni surveillé, "
            "ni valorisé, ni dénoué. Vérifiez le calendrier CONSTAT du script.")

    maturity = date.fromisoformat(body.maturity_date)
    # Les temps d observation se comptent depuis la MEME origine que celle qui
    # les a resolus (_derive_observation_times) : la date de strike. Les
    # reconvertir depuis la value date les decalerait de l ecart entre les deux.
    _obs_origin = body.strike_date or body.value_date
    event_dates = [_date_plus_years(_obs_origin, t) for t in times]
    after_maturity = [d for d in event_dates if date.fromisoformat(d) > maturity]
    if after_maturity:
        _reject_booking(
            session, current, body, 422,
            "Le calendrier contractuel dépasse la maturité du deal "
            f"({body.maturity_date}) : {', '.join(after_maturity)}.")

    # Allocate persistent objects only after every rejection-prone validation.
    # A rejected booking can then commit its audit row without also consuming a
    # reference or creating a default portfolio as a side effect.
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    reference = (next_reference(session, Deal, reference_prefix)
                 if reference_prefix else _gen_ref(entity.name if entity else None, session))
    default_portfolio = get_or_create_default_portfolio(session, current.id)

    deal = Deal(
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        uat_batch_id=uat_batch_id,
        portfolio_id=default_portfolio.id,
        indicative_id=body.indicative_id,
        rfq_id=body.rfq_id,
        rfq_provenance_json=rfq_provenance,
        script_snapshot=body.script_snapshot,
        script_id=body.script_id,
        sens=body.sens,
        contrepartie=body.contrepartie,
        devise=body.devise,
        product_type=body.product_type,
        fixing_policy=body.fixing_policy,
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

    if source_rfq:
        source_rfq.status = "clos"
        source_rfq.updated_at = datetime.utcnow()
        session.add(source_rfq)

    # First event is always the strike date (t=0) — S₀ to be filled in Events tab
    session.add(DealEvent(
        deal_id=deal.id,
        event_index=0,
        event_date=body.strike_date,
        t_years=0.0,
        spots_json="{}",
        source="pending",
        status="futur",
        fixing_status=FixingStatus.EXPECTED.value,
        data_category=DataCategory.UNKNOWN.value,
        label="Strike / Fixing S₀",
    ))

    for idx, t in enumerate(times):
        ev_date = _date_plus_years(_obs_origin, t)
        is_maturity = (idx == len(times) - 1)
        label = "Maturité" if is_maturity else f"Obs. {idx + 1} ({t:.2f}Y)"
        session.add(DealEvent(
            deal_id=deal.id,
            event_index=idx + 1,
            event_date=ev_date,
            t_years=round(t, 4),
            spots_json="{}",
            source="pending",
            status="futur",
            fixing_status=FixingStatus.EXPECTED.value,
            data_category=DataCategory.UNKNOWN.value,
            label=label,
        ))

    try:
        record_audit_event(
            session,
            action="BOOKING_ACCEPTED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=current.id,
            after={**_booking_request_summary(body), "reference": deal.reference},
            result="SUCCESS",
            metadata={"rfq_id": body.rfq_id},
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        if body.rfq_id:
            existing = session.exec(
                select(Deal).where(Deal.rfq_id == body.rfq_id)).first()
            if existing:
                _reject_booking(
                    session, current, body, 409,
                    f"Cette RFQ a déjà été bookée — deal {existing.reference}.")
        _reject_booking(
            session, current, body, 409,
            "Conflit d'unicité pendant le booking. Rechargez les données et réessayez.")
    session.refresh(deal)
    return _deal_row(deal, _get_events(deal.id, session))


@router.post("", status_code=201)
def book_deal(
    body: DealCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _book_deal(body, current, session)


class DealPortfolioAssign(BaseModel):
    # Required — a deal always belongs to a portfolio (at minimum the user's
    # default one); there is no "unassign", only "move to another portfolio".
    portfolio_id: int


@router.patch("/{deal_id}/portfolio")
def assign_deal_portfolio(
    deal_id: int,
    body: DealPortfolioAssign,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    portfolio = session.get(Portfolio, body.portfolio_id)
    if not portfolio or portfolio.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    deal.portfolio_id = body.portfolio_id
    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return {"id": deal.id, "portfolio_id": deal.portfolio_id}


@router.get("")
def list_deals(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    statement = select(Deal).order_by(Deal.created_at.desc())
    current_role = getattr(current, "role", "user")
    if current_role not in {"ops_maker", "checker", "admin"}:
        statement = statement.where(Deal.user_id == current.id)
    deals = session.exec(statement).all()
    if current_role in {"ops_maker", "checker"}:
        deals = [deal for deal in deals if _can_access_deal(deal, current, session)]
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
    """Barrier-proximity watchlist over the accessible ACTIVE deals: for each,
    the next observation date, the current worst-of performance vs S₀, and
    the gap (in points of S₀) to every barrier-looking PARAM in the booked
    script. Sorted most-urgent first (smallest barrier gap, then nearest
    observation). Uses the script's PARAM defaults — user overrides typed in
    the UI at pricing time are not persisted on the deal (known limitation)."""
    statement = select(Deal).where(Deal.status == "actif")
    current_role = getattr(current, "role", "user")
    if current_role not in {"ops_maker", "checker", "admin"}:
        statement = statement.where(Deal.user_id == current.id)
    deals = session.exec(statement).all()
    if current_role in {"ops_maker", "checker"}:
        deals = [deal for deal in deals if _can_access_deal(deal, current, session)]
    today = date.today()
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
    # Which underlyings the deal is on is known from the deal itself — it must
    # not depend on having prices. A deal whose strike is still in the future
    # has no S₀ fixed and no performance yet, and used to display "—" in the
    # Sous-jacent column as if the product had none.
    spots_out = [{"name": u["name"], "ticker": u.get("ticker", ""),
                  "s0": s0_map.get(u["name"]), "spot": None, "perf": None}
                 for u in underlyings]
    by_name = {row["name"]: row for row in spots_out}
    if tickers and s0_map:
        # yfinance's `end` is exclusive — fetching [strike_date, today] when
        # the deal was booked TODAY (strike_date == today_str) requests a
        # zero-width window and comes back empty, same failure mode
        # refresh_deal_core already guards against by starting a week early.
        fetch_start = (date.fromisoformat(deal.strike_date) - timedelta(days=7)).isoformat()
        px = load_hist_prices(tickers, fetch_start, today_str)
        if "error" not in px:
            dates = px.get("dates", [])
            prices = px.get("prices", {})
            # Since-strike window: wof_min/bof_max must only see closes from
            # t=0 onward. The wider fetch above is purely to survive a
            # same-day/weekend strike with no close of its own — the CURRENT
            # spot still falls back to the latest known price even when that
            # window is empty (a deal struck today, before the market's
            # closed, genuinely has no post-strike close yet; the extrema
            # then degrade to just that one spot, same as "nothing has
            # happened since inception").
            since_strike = [i for i, d in enumerate(dates) if d >= deal.strike_date]
            min_perfs, max_perfs = [], []
            for u in underlyings:
                tk = u.get("ticker", "")
                name = u["name"]
                s0 = s0_map.get(name, 0.0)
                raw = prices.get(tk, [])
                all_series = [float(p) for p in raw if p]
                extrema_series = [float(raw[i]) for i in since_strike if i < len(raw) and raw[i]] or all_series[-1:]
                if tk and all_series and s0 > 0:
                    spot = all_series[-1]
                    perfs.append(spot / s0)
                    min_perfs.append(min(extrema_series) / s0)
                    max_perfs.append(max(extrema_series) / s0)
                    by_name[name].update({
                        "s0": s0, "spot": round(spot, 4), "perf": round(spot / s0, 4),
                    })
            if perfs:
                wof, bof = min(perfs), max(perfs)
                wof_min, bof_max = min(min_perfs), max(max_perfs)

    # The next observation's 1-based index — a PARAM() barrier schedule
    # is read at THAT row (a degressive autocall must show the barrier
    # the next fixing will actually use, not row 1).
    next_obs_index = next_ev.event_index if next_ev else None

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
                if level is None:
                    continue
                obs_val = _observable_value(mon["observable"])
                kind = {"up": "autocall", "down": "ki"}.get(mon["direction"], "neutral")
                barriers.append({
                    "name": mon["name"],
                    "kind": kind,
                    "observable": mon["observable"] or "WOF",
                    "level": round(level, 4),
                    # None = the observable isn't computable yet (strike not
                    # fixed, prices unavailable). Every consumer must read it
                    # as "no gap yet", never as zero — see utils/barriers.js
                    # and portfolios.py:_barrier_severity.
                    "gap_pts": round((obs_val - level) * 100, 1) if obs_val is not None else None,
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
                        "gap_pts": round((wof - p.stored_val) * 100, 1) if wof is not None else None,
                    })
    except ValueError:
        pass   # unparseable snapshot — leave barriers empty, keep the row

    min_gap = min((abs(b["gap_pts"]) for b in barriers
                   if b["gap_pts"] is not None), default=None)
    return {
        "deal_id": deal.id,
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


@router.get("/amendment-requests/pending")
def pending_amendment_requests(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Checker work queue, restricted to the same legal entity."""
    if current.role not in {"checker", "admin"}:
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
        if not deal:
            continue
        if current.role != "admin" and _deal_entity_id(deal, session) != current.entity_id:
            continue
        row = _amendment_row(request)
        row.update({"deal_reference": deal.reference,
                    "contract_version": deal.contract_version})
        rows.append(row)
    return rows


@router.get("/{deal_id}")
def get_deal(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    row = _deal_row(deal, _get_events(deal_id, session))
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
    row["terms"] = _deal_terms(deal)
    row["flags"] = _script_flags(deal)
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
    clauses = [
        (AuditEvent.object_type == "DEAL") & (AuditEvent.object_id == deal_id),
    ]
    if deal.rfq_id:
        clauses.append(
            (AuditEvent.object_type == "RFQ") & (AuditEvent.object_id == deal.rfq_id))
    if events:
        clauses.append(
            (AuditEvent.object_type == "DEAL_EVENT") &
            (AuditEvent.object_id.in_([row.id for row in events])))
    if proposals:
        clauses.append(
            (AuditEvent.object_type == "LIFECYCLE_PROPOSAL") &
            (AuditEvent.object_id.in_([row.id for row in proposals])))
    if amendments:
        clauses.append(
            (AuditEvent.object_type == "TRADE_AMENDMENT_REQUEST") &
            (AuditEvent.object_id.in_([row.id for row in amendments])))
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
                return [event.t_years for event in _get_events(deal.id, session)
                        if event.t_years > 0]
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


@router.post("/{deal_id}/amendment-requests", status_code=201)
def request_amendment(
    deal_id: int,
    body: AmendmentRequestCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Record a maker request without changing the booked trade."""
    deal = session.get(Deal, deal_id)
    if not deal or deal.user_id != current.id:
        raise HTTPException(404, "Deal introuvable")
    if body.field_name == "market_snapshot":
        old_value = json.loads(deal.market_snapshot_json or "{}")
    else:
        old_value = getattr(deal, body.field_name)
    if old_value == body.new_value:
        commit_rejection(
            session,
            action="AMENDMENT_REQUEST_REJECTED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=current.id,
            before={body.field_name: old_value},
            after={body.field_name: body.new_value},
            reason="La valeur demandée est identique à la valeur bookée.",
        )
        raise HTTPException(422, {
            "code": "AMENDMENT_NO_CHANGE",
            "message": "La demande d'amendement ne contient aucun changement.",
        })
    duplicate = session.exec(
        select(TradeAmendmentRequest).where(
            TradeAmendmentRequest.deal_id == deal.id,
            TradeAmendmentRequest.field_name == body.field_name,
            TradeAmendmentRequest.status.in_([
                AmendmentStatus.PENDING.value, AmendmentStatus.APPROVED.value]),
        )
    ).first()
    if duplicate:
        commit_rejection(
            session,
            action="AMENDMENT_REQUEST_REJECTED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=current.id,
            before={body.field_name: old_value},
            after={body.field_name: body.new_value},
            reason="Une demande active existe déjà pour ce champ.",
            metadata={"existing_request_id": duplicate.id},
        )
        raise HTTPException(409, {
            "code": "AMENDMENT_ALREADY_PENDING",
            "request_id": duplicate.id,
        })
    request = TradeAmendmentRequest(
        deal_id=deal.id,
        field_name=body.field_name,
        old_value_json=json.dumps(old_value, ensure_ascii=False, sort_keys=True),
        new_value_json=json.dumps(body.new_value, ensure_ascii=False, sort_keys=True),
        reason=body.reason,
        requested_by=current.id,
        status=AmendmentStatus.PENDING,
        base_contract_version=deal.contract_version,
    )
    session.add(request)
    session.flush()
    record_audit_event(
        session,
        action="AMENDMENT_REQUESTED",
        object_type="TRADE_AMENDMENT_REQUEST",
        object_id=request.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before={body.field_name: old_value},
        after={body.field_name: body.new_value},
        reason=body.reason,
        metadata={"deal_id": deal.id, "status": "PENDING",
                  "base_contract_version": deal.contract_version},
    )
    session.commit()
    session.refresh(request)
    return _amendment_row(request)


def _amendment_action_rejection(
    session: Session,
    request: TradeAmendmentRequest,
    current: User,
    action: str,
    detail: dict,
) -> None:
    commit_rejection(
        session,
        action=action,
        object_type="TRADE_AMENDMENT_REQUEST",
        object_id=request.id,
        actor_user_id=current.id,
        before=_amendment_row(request),
        reason=str(detail.get("message") or detail.get("code")),
        metadata={"failure": detail, "deal_id": request.deal_id},
    )
    raise HTTPException(409, detail)


@router.post("/{deal_id}/amendment-requests/{request_id}/approve")
def approve_amendment(
    deal_id: int,
    request_id: int,
    body: AmendmentDecisionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal, request = _checker_request(deal_id, request_id, current, session)
    if request.status != AmendmentStatus.PENDING:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPROVAL_REJECTED", {
                "code": "AMENDMENT_STATUS_INVALID", "status": request.status,
                "message": "Seule une demande PENDING peut être approuvée.",
            })
    if deal.contract_version != request.base_contract_version:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPROVAL_REJECTED", {
                "code": "AMENDMENT_VERSION_STALE",
                "message": "Le contrat a changé depuis la demande.",
                "base_version": request.base_contract_version,
                "current_version": deal.contract_version,
            })
    old_value = json.loads(request.old_value_json)
    if getattr(deal, request.field_name, None) != old_value:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPROVAL_REJECTED", {
                "code": "AMENDMENT_BASE_VALUE_CHANGED",
                "message": "La valeur contractuelle de départ a changé.",
            })
    try:
        normalized = _validated_amendment_value(deal, request)
    except HTTPException as exc:
        commit_rejection(
            session,
            action="AMENDMENT_APPROVAL_REJECTED",
            object_type="TRADE_AMENDMENT_REQUEST",
            object_id=request.id,
            actor_user_id=current.id,
            before=_amendment_row(request),
            reason=exc.detail.get("message", "Amendement non applicable en place"),
            metadata={"failure": exc.detail, "deal_id": deal.id},
        )
        raise
    before = _amendment_row(request)
    request.new_value_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    request.status = AmendmentStatus.APPROVED
    request.validated_by = current.id
    request.validated_at = datetime.utcnow()
    request.decision_reason = body.reason
    session.add(request)
    record_audit_event(
        session,
        action="AMENDMENT_APPROVED",
        object_type="TRADE_AMENDMENT_REQUEST",
        object_id=request.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_amendment_row(request),
        reason=body.reason,
        metadata={"deal_id": deal.id, "base_contract_version": deal.contract_version},
    )
    session.commit()
    session.refresh(request)
    return _amendment_row(request)


@router.post("/{deal_id}/amendment-requests/{request_id}/reject")
def reject_amendment(
    deal_id: int,
    request_id: int,
    body: AmendmentDecisionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal, request = _checker_request(deal_id, request_id, current, session)
    if request.status != AmendmentStatus.PENDING:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_REJECTION_REJECTED", {
                "code": "AMENDMENT_STATUS_INVALID", "status": request.status,
                "message": "Seule une demande PENDING peut être rejetée.",
            })
    before = _amendment_row(request)
    request.status = AmendmentStatus.REJECTED
    request.rejected_by = current.id
    request.rejected_at = datetime.utcnow()
    request.decision_reason = body.reason
    session.add(request)
    record_audit_event(
        session,
        action="AMENDMENT_REJECTED",
        object_type="TRADE_AMENDMENT_REQUEST",
        object_id=request.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_amendment_row(request),
        reason=body.reason,
        metadata={"deal_id": deal.id},
    )
    session.commit()
    session.refresh(request)
    return _amendment_row(request)


@router.post("/{deal_id}/amendment-requests/{request_id}/apply")
def apply_amendment(
    deal_id: int,
    request_id: int,
    body: AmendmentDecisionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal, request = _checker_request(deal_id, request_id, current, session)
    if request.status != AmendmentStatus.APPROVED:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_STATUS_INVALID", "status": request.status,
                "message": "Seule une demande APPROVED peut être appliquée.",
            })
    if deal.contract_version != request.base_contract_version:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_VERSION_STALE",
                "message": "Le contrat a changé depuis l'approbation.",
                "base_version": request.base_contract_version,
                "current_version": deal.contract_version,
            })
    old_value = json.loads(request.old_value_json)
    if getattr(deal, request.field_name, None) != old_value:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_BASE_VALUE_CHANGED",
                "message": "La valeur contractuelle de départ a changé.",
            })
    normalized = _validated_amendment_value(deal, request)
    before_contract = _contract_snapshot(deal)
    current_version = deal.contract_version
    if not session.exec(select(DealContractVersion).where(
        DealContractVersion.dedup_key == f"{deal.id}:{current_version}")) .first():
        session.add(DealContractVersion(
            deal_id=deal.id,
            version=current_version,
            dedup_key=f"{deal.id}:{current_version}",
            snapshot_json=json.dumps(before_contract, ensure_ascii=False, sort_keys=True),
            amendment_request_id=request.id,
            created_by=current.id,
        ))
        session.flush()
    applied_at = datetime.utcnow()
    deal_cas = session.exec(
        update(Deal).where(
            Deal.id == deal.id,
            Deal.contract_version == current_version,
        ).values(**{
            request.field_name: normalized,
            "contract_version": current_version + 1,
            "updated_at": applied_at,
        }).execution_options(synchronize_session=False)
    )
    if deal_cas.rowcount != 1:
        session.rollback()
        request = session.get(TradeAmendmentRequest, request_id)
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_CONCURRENT_APPLICATION",
                "message": "Le contrat a été modifié par une autre transaction.",
            })
    request_cas = session.exec(
        update(TradeAmendmentRequest).where(
            TradeAmendmentRequest.id == request.id,
            TradeAmendmentRequest.status == AmendmentStatus.APPROVED.value,
        ).values(
            status=AmendmentStatus.APPLIED.value,
            applied_by=current.id,
            applied_at=applied_at,
            applied_contract_version=current_version + 1,
        ).execution_options(synchronize_session=False)
    )
    if request_cas.rowcount != 1:
        session.rollback()
        request = session.get(TradeAmendmentRequest, request_id)
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_CONCURRENT_APPLICATION",
                "message": "La demande a été traitée par une autre transaction.",
            })
    session.expire_all()
    deal = session.get(Deal, deal_id)
    request = session.get(TradeAmendmentRequest, request_id)
    after_contract = _contract_snapshot(deal)
    session.add(DealContractVersion(
        deal_id=deal.id,
        version=deal.contract_version,
        dedup_key=f"{deal.id}:{deal.contract_version}",
        snapshot_json=json.dumps(after_contract, ensure_ascii=False, sort_keys=True),
        amendment_request_id=request.id,
        created_by=current.id,
    ))
    _ensure_alert(
        session,
        deal,
        "amendment_applied",
        (
            f"Amendement {request.field_name!r} appliqué sur {deal.reference} "
            f"(v{current_version} → v{deal.contract_version}) : contrôler les "
            "documents, la valorisation, la comptabilité et le reporting."
        ),
        f"amendment-applied:{request.id}",
    )
    record_audit_event(
        session,
        action="AMENDMENT_APPLIED",
        object_type="TRADE_AMENDMENT_REQUEST",
        object_id=request.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before_contract,
        after=after_contract,
        reason=body.reason,
        metadata={"deal_id": deal.id, "field": request.field_name,
                  "from_version": current_version,
                  "to_version": deal.contract_version,
                  "required_follow_up": [
                      "DOCUMENTS", "VALUATION", "ACCOUNTING", "REPORTING"]},
    )
    session.commit()
    session.refresh(deal)
    session.refresh(request)
    return {"deal": _deal_row(deal), "amendment": _amendment_row(request)}


@router.patch("/{deal_id}/events/{event_id}")
def update_event(
    deal_id: int,
    event_id: int,
    body: EventUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = _ops_deal(
        deal_id, current, session,
        allowed_roles={"ops_maker"},
        action="FIXING_CAPTURE_ROLE_REJECTED",
    )
    if deal.user_id == current.id:
        _reject_workflow_action(
            session,
            action="FIXING_CAPTURE_OWNER_REJECTED",
            object_type="DEAL",
            object_id=deal.id,
            current=current,
            message="Le propriétaire économique du deal ne peut pas saisir ses fixings officiels.",
            failures=[_workflow_failure(
                "DEAL_OWNER_CANNOT_CAPTURE_FIXING",
                "entered_by",
                "Le Deal Owner et l’Ops Maker doivent être deux utilisateurs distincts.",
                expected="Un Ops Maker indépendant du propriétaire du deal.",
                action="Transmettez l’événement à un autre Ops Maker de l’entité.",
                received=current.id,
            )],
            status_code=409,
        )
    ev = session.get(DealEvent, event_id)
    if not ev or ev.deal_id != deal_id:
        raise HTTPException(404, "Événement introuvable")

    if body.status:
        commit_rejection(
            session,
            action="EVENT_STATUS_MODIFICATION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            actor_user_id=current.id,
            before={"status": ev.status},
            after={"status": body.status},
            reason="Le statut économique d'un événement ne peut être modifié que "
                   "par le workflow de résolution validé.",
        )
        raise HTTPException(409, {
            "code": "EVENT_STATUS_IMMUTABLE",
            "message": "Modification directe du statut de l'événement refusée.",
        })

    before = _event_row(ev)
    current_version = (
        session.get(OfficialFixingVersion, ev.current_fixing_version_id)
        if ev.current_fixing_version_id else None
    )
    version_failures: list[dict] = []
    if ev.fixing_status == FixingStatus.APPLIED or (
        current_version and current_version.status == FixingStatus.APPLIED
    ):
        version_failures.append(_workflow_failure(
            "APPLIED_FIXING_CORRECTION_REQUIRES_CANCEL_REPLACE",
            "supersedes_version",
            "Le fixing a déjà été consommé par une résolution appliquée.",
            expected="Une procédure d’annulation/remplacement ou un événement compensatoire.",
            action="Ouvrez une demande de correction post-résolution auprès des Opérations.",
            received=body.supersedes_version,
        ))
    elif current_version:
        if current_version.supersedes_id and current_version.status in {
            FixingStatus.RECEIVED, FixingStatus.PARTIAL,
        }:
            version_failures.append(_workflow_failure(
                "FIXING_CORRECTION_DECISION_PENDING",
                "fixing_version.status",
                "Une correction est déjà en attente de décision Checker.",
                expected="Validation ou rejet de la version candidate courante.",
                action="Demandez au Checker de traiter la correction avant d’en soumettre une autre.",
                received=current_version.status,
            ))
        elif body.supersedes_version != current_version.version:
            version_failures.append(_workflow_failure(
                "FIXING_SUPERSEDES_VERSION_REQUIRED",
                "supersedes_version",
                "Une version de fixing existe déjà pour cet événement.",
                expected=str(current_version.version),
                action="Confirmez explicitement la version à corriger ; l’ancienne preuve sera conservée.",
                received=body.supersedes_version,
            ))
    elif body.supersedes_version is not None:
        version_failures.append(_workflow_failure(
            "FIXING_SUPERSEDES_VERSION_UNKNOWN",
            "supersedes_version",
            "Aucune version précédente ne peut être corrigée sur cet événement.",
            expected="Champ vide pour une première saisie.",
            action="Retirez la référence de correction.",
            received=body.supersedes_version,
        ))

    submission_failures, observed = _fixing_submission_failures(deal, ev, body)
    failures = version_failures + submission_failures
    if failures:
        if version_failures and current_version:
            _ensure_alert(
                session,
                deal,
                "fixing_overwrite_rejected",
                f"Correction non gouvernée refusée du fixing {ev.event_date} v{current_version.version}.",
                f"fixing-overwrite:{deal.id}:{ev.id}:{current_version.version}",
            )
        _reject_workflow_action(
            session,
            action="FIXING_CAPTURE_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message=f"Fixing non enregistré — {len(failures)} élément(s) à corriger.",
            failures=failures,
            status_code=409 if version_failures else 422,
            before=before,
        )

    latest = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_event_id == ev.id)
        .order_by(OfficialFixingVersion.version.desc())
    ).first()
    next_version = (latest.version if latest else 0) + 1
    supersedes_id = current_version.id if current_version else None
    payload = _fixing_record_payload(
        deal, ev, body, version=next_version, supersedes_id=supersedes_id)
    record_hash = _fixing_record_hash(payload)
    evidence_payload = base64.b64decode(body.evidence_payload_b64, validate=True)
    spot_failures = _spot_failures(deal, body.spots)
    status = FixingStatus.PARTIAL if spot_failures else FixingStatus.RECEIVED
    received_at = datetime.utcnow()
    version = OfficialFixingVersion(
        deal_id=deal.id,
        deal_event_id=ev.id,
        version=next_version,
        supersedes_id=supersedes_id,
        status=status,
        spots_json=json.dumps(body.spots, ensure_ascii=False, sort_keys=True),
        provider=body.provider.strip().upper(),
        source_type=body.source_type.strip().upper(),
        external_reference=body.external_reference.strip(),
        observed_at=observed.astimezone(timezone.utc).replace(tzinfo=None),
        received_at=received_at,
        venue=body.venue.strip(),
        calendar=body.calendar.strip(),
        timezone=body.timezone.strip(),
        evidence_sha256=body.evidence_sha256.strip().lower(),
        evidence_filename=body.evidence_filename.strip(),
        evidence_content_type=body.evidence_content_type.strip(),
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=body.evidence_payload_b64,
        record_sha256=record_hash,
        capture_reason=body.reason.strip(),
        entered_by=current.id,
    )
    session.add(version)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        _reject_workflow_action(
            session,
            action="FIXING_CONCURRENT_SUBMISSION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message="Fixing non enregistré — une autre version a été soumise simultanément.",
            failures=[_workflow_failure(
                "FIXING_VERSION_CONFLICT",
                "supersedes_version",
                "La version de départ n’est plus la version courante.",
                expected="La dernière version affichée après actualisation.",
                action="Actualisez l’événement, contrôlez la nouvelle version puis recommencez si nécessaire.",
                received=body.supersedes_version,
            )],
            status_code=409,
        )

    if current_version:
        current_version.status = (
            FixingStatus.CONTESTED
            if current_version.status == FixingStatus.VALIDATED
            else FixingStatus.SUPERSEDED
        )
        session.add(current_version)

    ev.spots_json = version.spots_json
    ev.source = body.source
    ev.data_category = DataCategory.FIXING_CANDIDATE
    ev.fixing_status = status
    ev.current_fixing_version_id = version.id
    ev.fixing_version = version.version
    ev.fixing_entered_by = current.id
    ev.fixing_entered_at = received_at
    ev.fixing_provider = version.provider
    ev.fixing_source_type = version.source_type
    ev.fixing_external_reference = version.external_reference
    ev.fixing_observed_at = version.observed_at
    ev.fixing_venue = version.venue
    ev.fixing_calendar = version.calendar
    ev.fixing_timezone = version.timezone
    ev.fixing_evidence_sha256 = version.evidence_sha256
    ev.fixing_record_sha256 = version.record_sha256
    ev.fixing_reason = version.capture_reason
    ev.validated_by = None
    ev.validated_at = None
    ev.applied_at = None
    session.add(ev)

    deal.updated_at = received_at
    session.add(deal)
    record_audit_event(
        session,
        action="FIXING_CORRECTION_RECEIVED" if supersedes_id else "FIXING_RECEIVED",
        object_type="DEAL_EVENT",
        object_id=ev.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_event_row(ev),
        reason=version.capture_reason,
        data_source=DataCategory.FIXING_CANDIDATE,
        metadata={
            "fixing_version_id": version.id,
            "fixing_version": version.version,
            "supersedes_id": supersedes_id,
            "record_sha256": version.record_sha256,
            "evidence_sha256": version.evidence_sha256,
            "provider": version.provider,
            "source_type": version.source_type,
            "external_reference": version.external_reference,
        },
    )
    session.commit()
    session.refresh(ev)
    return _event_row(ev)


def _required_underlying_names(deal: Deal) -> list[str]:
    underlyings = json.loads(deal.underlyings_json or "[]")
    return [str(u.get("name") or "").strip() for u in underlyings if str(u.get("name") or "").strip()]


def _spot_failures(deal: Deal, spots: dict) -> list[dict]:
    failures: list[dict] = []
    required = _required_underlying_names(deal)
    missing = [name for name in required if name not in spots]
    extra = [name for name in spots if name not in required]
    if missing:
        failures.append({"code": "FIXING_MISSING_UNDERLYING", "underlyings": missing})
    if extra:
        failures.append({"code": "FIXING_UNKNOWN_UNDERLYING", "underlyings": extra})
    for name in required:
        value = spots.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)) or float(value) <= 0:
            failures.append({
                "code": "FIXING_INVALID_VALUE",
                "underlying": name,
                "value": value,
            })
    return failures


@router.post("/{deal_id}/events/{event_id}/validate")
def validate_fixing(
    deal_id: int,
    event_id: int,
    body: FixingValidationRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = _ops_deal(
        deal_id, current, session,
        allowed_roles={"checker"},
        action="FIXING_VALIDATION_ROLE_REJECTED",
    )
    ev = session.get(DealEvent, event_id)
    if not ev or ev.deal_id != deal_id:
        raise HTTPException(404, "Événement introuvable")

    version = (
        session.get(OfficialFixingVersion, ev.current_fixing_version_id)
        if ev.current_fixing_version_id else None
    )
    failures: list[dict] = []
    if not version:
        failures.append(_workflow_failure(
            "FIXING_PROVENANCE_MISSING",
            "current_fixing_version_id",
            "Aucune preuve versionnée n’est liée au fixing candidat.",
            expected="Une soumission par un Ops Maker avec provenance complète.",
            action="Demandez à un Ops Maker de saisir le fixing et sa preuve officielle.",
        ))
    elif version.entered_by == current.id:
        failures.append(_workflow_failure(
            "FOUR_EYES_VIOLATION",
            "validated_by",
            "Le Checker est également le Maker de cette version de fixing.",
            expected="Deux utilisateurs distincts.",
            action="Faites contrôler le fixing par un autre Ops Checker habilité.",
            received=current.id,
        ))
    if deal.user_id == current.id:
        failures.append(_workflow_failure(
            "DEAL_OWNER_CANNOT_VALIDATE_LIFECYCLE",
            "validated_by",
            "Le propriétaire économique du deal ne peut pas valider son lifecycle.",
            expected="Un Ops Checker indépendant du Deal Owner.",
            action="Transmettez la validation à un autre Ops Checker de l’entité.",
            received=current.id,
        ))

    for spot_failure in _spot_failures(deal, json.loads(ev.spots_json or "{}")):
        failures.append(_workflow_failure(
            spot_failure["code"],
            f"spots.{spot_failure.get('underlying', '')}".rstrip("."),
            "Le fixing candidat est incomplet ou contient une valeur invalide.",
            expected="Une valeur numérique strictement positive par sous-jacent du deal.",
            action="Demandez au Maker de soumettre une nouvelle version complète.",
            received=spot_failure.get("value"),
        ))
    if ev.event_date > date.today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_DATE_IN_FUTURE",
            "event_date",
            "La date contractuelle du fixing est encore future.",
            expected="Une date d’événement atteinte.",
            action="Attendez la date officielle de constatation.",
            received=ev.event_date,
        ))
    if ev.data_category != DataCategory.FIXING_CANDIDATE:
        failures.append(_workflow_failure(
            "FIXING_NOT_CANDIDATE",
            "data_category",
            "L’événement n’est pas un fixing candidat soumis au contrôle.",
            expected=DataCategory.FIXING_CANDIDATE.value,
            action="Demandez une nouvelle soumission Ops Maker avec preuve.",
            received=ev.data_category,
        ))
    if ev.fixing_status not in (
        FixingStatus.RECEIVED, FixingStatus.PARTIAL,
        FixingStatus.MANUAL_REVIEW_REQUIRED,
    ):
        failures.append(_workflow_failure(
            "FIXING_STATUS_INVALID",
            "fixing_status",
            "Le statut courant n’autorise pas la validation.",
            expected="RECEIVED après soumission complète.",
            action="Actualisez l’événement et vérifiez son historique de versions.",
            received=ev.fixing_status,
        ))
    if version:
        if version.status not in {FixingStatus.RECEIVED, FixingStatus.PARTIAL}:
            failures.append(_workflow_failure(
                "FIXING_VERSION_STATUS_INVALID",
                "fixing_version.status",
                "La version de preuve n’est plus validable.",
                expected="RECEIVED ou PARTIAL.",
                action="Actualisez l’événement et sélectionnez la version courante.",
                received=version.status,
            ))
        payload = {
            "deal_id": deal.id,
            "contract_version": deal.contract_version,
            "event_id": ev.id,
            "event_date": ev.event_date,
            "event_index": ev.event_index,
            "version": version.version,
            "supersedes_id": version.supersedes_id,
            "underlyings": json.loads(deal.underlyings_json or "[]"),
            "spots": json.loads(version.spots_json or "{}"),
            "provider": version.provider,
            "source_type": version.source_type,
            "external_reference": version.external_reference,
            "observed_at": version.observed_at.replace(tzinfo=timezone.utc).isoformat(),
            "venue": version.venue,
            "calendar": version.calendar,
            "timezone": version.timezone,
            "evidence_sha256": version.evidence_sha256,
            "evidence_filename": version.evidence_filename,
            "evidence_content_type": version.evidence_content_type,
            "evidence_size_bytes": version.evidence_size_bytes,
            "capture_reason": version.capture_reason,
        }
        try:
            evidence_payload = base64.b64decode(
                version.evidence_payload_b64 or "", validate=True)
        except (binascii.Error, ValueError):
            evidence_payload = b""
        if (
            not evidence_payload
            or len(evidence_payload) != version.evidence_size_bytes
            or hashlib.sha256(evidence_payload).hexdigest() != version.evidence_sha256
        ):
            failures.append(_workflow_failure(
                "FIXING_EVIDENCE_ARCHIVE_MISMATCH",
                "evidence_payload_b64",
                "La pièce source archivée est absente ou ne correspond plus à son hash.",
                expected=(
                    f"Pièce {version.evidence_filename!r}, "
                    f"{version.evidence_size_bytes} octets, hash vérifié."),
                action="Rejetez cette version et demandez une nouvelle soumission avec la pièce source.",
            ))
        if _fixing_record_hash(payload) != version.record_sha256:
            failures.append(_workflow_failure(
                "FIXING_RECORD_HASH_MISMATCH",
                "fixing_record_sha256",
                "La preuve ou ses métadonnées ont changé depuis la soumission.",
                expected="Le hash immuable calculé lors de la soumission.",
                action="Rejetez cette version et demandez une nouvelle soumission au Maker.",
            ))
    if failures:
        _reject_workflow_action(
            session,
            action="FIXING_VALIDATION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message=f"Fixing non validé — {len(failures)} contrôle(s) bloquant(s).",
            failures=failures,
            before={"fixing_status": ev.fixing_status, "spots": json.loads(ev.spots_json or "{}")},
        )

    before = _event_row(ev)
    validated_at = datetime.utcnow()
    version_cas = session.exec(
        update(OfficialFixingVersion)
        .where(
            OfficialFixingVersion.id == version.id,
            OfficialFixingVersion.status == FixingStatus.RECEIVED.value,
            OfficialFixingVersion.validated_by == None,  # noqa: E711
        )
        .values(
            status=FixingStatus.VALIDATED.value,
            validated_by=current.id,
            validation_reason=body.reason,
            validated_at=validated_at,
        )
        .execution_options(synchronize_session=False)
    )
    if version_cas.rowcount != 1:
        session.rollback()
        _reject_workflow_action(
            session,
            action="FIXING_CONCURRENT_VALIDATION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message="Fixing non validé — cette version a déjà été traitée par une autre session.",
            failures=[_workflow_failure(
                "FIXING_VERSION_ALREADY_DECIDED",
                "fixing_version.status",
                "La transition attendue RECEIVED → VALIDATED n’est plus disponible.",
                expected="Une version courante au statut RECEIVED.",
                action="Actualisez l’événement et consultez la décision déjà enregistrée.",
            )],
            status_code=409,
        )
    session.expire(version)
    version = session.get(OfficialFixingVersion, version.id)
    if version.supersedes_id:
        superseded = session.get(OfficialFixingVersion, version.supersedes_id)
        if superseded:
            superseded.status = FixingStatus.SUPERSEDED
            session.add(superseded)
        stale = session.exec(select(LifecycleProposal).where(
            LifecycleProposal.deal_id == deal.id,
            LifecycleProposal.status.in_([
                LifecycleStatus.PROPOSED.value, LifecycleStatus.VALIDATED.value]),
        )).all()
        for proposal in stale:
            proposal.status = LifecycleStatus.STALE
            proposal.error_message = (
                f"Fixing {ev.event_date} remplacé par la version {version.version}."
            )
            proposal.updated_at = datetime.utcnow()
            session.add(proposal)
    ev.fixing_status = FixingStatus.VALIDATED
    ev.data_category = DataCategory.FIXING_OFFICIAL
    ev.status = "observé"
    ev.validated_by = current.id
    ev.validated_at = validated_at
    session.add(ev)
    record_audit_event(
        session,
        action="FIXING_VALIDATED",
        object_type="DEAL_EVENT",
        object_id=ev.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_event_row(ev),
        reason=body.reason,
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "fixing_version_id": version.id,
            "fixing_version": version.version,
            "maker_user_id": version.entered_by,
            "checker_user_id": current.id,
            "provider": version.provider,
            "source_type": version.source_type,
            "external_reference": version.external_reference,
            "evidence_sha256": version.evidence_sha256,
            "record_sha256": version.record_sha256,
        },
    )
    session.commit()
    session.refresh(ev)
    return _event_row(ev)


@router.get("/{deal_id}/events/{event_id}/fixing-versions/{version_id}/evidence")
def download_fixing_evidence(
    deal_id: int,
    event_id: int,
    version_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = _ops_deal(
        deal_id, current, session,
        allowed_roles={"ops_maker", "checker"},
        action="FIXING_EVIDENCE_ACCESS_REJECTED",
    )
    ev = session.get(DealEvent, event_id)
    version = session.get(OfficialFixingVersion, version_id)
    if (
        not ev or ev.deal_id != deal.id or not version
        or version.deal_event_id != ev.id or version.deal_id != deal.id
    ):
        raise HTTPException(404, "Preuve de fixing introuvable")
    try:
        payload = base64.b64decode(version.evidence_payload_b64 or "", validate=True)
    except (binascii.Error, ValueError):
        payload = b""
    if (
        not payload
        or len(payload) != version.evidence_size_bytes
        or hashlib.sha256(payload).hexdigest() != version.evidence_sha256
    ):
        _reject_workflow_action(
            session,
            action="FIXING_EVIDENCE_INTEGRITY_REJECTED",
            object_type="OFFICIAL_FIXING_VERSION",
            object_id=version.id,
            current=current,
            message="Preuve indisponible — l’archive ne correspond pas à son empreinte cryptographique.",
            failures=[_workflow_failure(
                "FIXING_EVIDENCE_ARCHIVE_MISMATCH",
                "evidence_payload_b64",
                "La pièce archivée est absente, tronquée ou altérée.",
                expected=f"{version.evidence_size_bytes} octets avec le hash enregistré.",
                action="Bloquez la décision et demandez une nouvelle version au Maker.",
            )],
            status_code=409,
        )
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", version.evidence_filename)
    return Response(
        content=payload,
        media_type=version.evidence_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{deal_id}/events/{event_id}/reject")
def reject_fixing(
    deal_id: int,
    event_id: int,
    body: FixingValidationRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = _ops_deal(
        deal_id, current, session,
        allowed_roles={"checker"},
        action="FIXING_REJECTION_ROLE_REJECTED",
    )
    ev = session.get(DealEvent, event_id)
    if not ev or ev.deal_id != deal_id:
        raise HTTPException(404, "Événement introuvable")

    version = (
        session.get(OfficialFixingVersion, ev.current_fixing_version_id)
        if ev.current_fixing_version_id else None
    )
    failures: list[dict] = []
    if not version:
        failures.append(_workflow_failure(
            "FIXING_PROVENANCE_MISSING",
            "current_fixing_version_id",
            "Aucune version candidate n’est disponible pour décision.",
            expected="Une version courante RECEIVED ou PARTIAL.",
            action="Actualisez l’événement ou demandez une soumission à l’Ops Maker.",
        ))
    elif version.entered_by == current.id:
        failures.append(_workflow_failure(
            "FOUR_EYES_VIOLATION",
            "rejected_by",
            "Le Checker est également le Maker de cette version de fixing.",
            expected="Deux utilisateurs distincts.",
            action="Faites décider la version par un autre Ops Checker habilité.",
            received=current.id,
        ))
    if deal.user_id == current.id:
        failures.append(_workflow_failure(
            "DEAL_OWNER_CANNOT_VALIDATE_LIFECYCLE",
            "rejected_by",
            "Le propriétaire économique du deal ne peut pas décider son lifecycle.",
            expected="Un Ops Checker indépendant du Deal Owner.",
            action="Transmettez la décision à un autre Ops Checker de l’entité.",
            received=current.id,
        ))
    if version and version.status not in {
        FixingStatus.RECEIVED, FixingStatus.PARTIAL,
    }:
        failures.append(_workflow_failure(
            "FIXING_VERSION_STATUS_INVALID",
            "fixing_version.status",
            "La version courante a déjà fait l’objet d’une décision.",
            expected="RECEIVED ou PARTIAL.",
            action="Actualisez l’événement et consultez la décision enregistrée.",
            received=version.status,
        ))
    if ev.data_category != DataCategory.FIXING_CANDIDATE:
        failures.append(_workflow_failure(
            "FIXING_NOT_CANDIDATE",
            "data_category",
            "L’événement n’est pas un fixing candidat soumis au contrôle.",
            expected=DataCategory.FIXING_CANDIDATE.value,
            action="Actualisez l’événement et sélectionnez une version candidate.",
            received=ev.data_category,
        ))
    if failures:
        _reject_workflow_action(
            session,
            action="FIXING_REJECTION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message=f"Rejet impossible — {len(failures)} contrôle(s) bloquant(s).",
            failures=failures,
            status_code=409,
            before=_event_row(ev),
        )

    before = _event_row(ev)
    rejected_at = datetime.utcnow()
    version_cas = session.exec(
        update(OfficialFixingVersion)
        .where(
            OfficialFixingVersion.id == version.id,
            OfficialFixingVersion.status.in_([
                FixingStatus.RECEIVED.value, FixingStatus.PARTIAL.value]),
            OfficialFixingVersion.rejected_by == None,  # noqa: E711
            OfficialFixingVersion.validated_by == None,  # noqa: E711
        )
        .values(
            status=FixingStatus.REJECTED.value,
            rejected_by=current.id,
            rejection_reason=body.reason,
            rejected_at=rejected_at,
        )
        .execution_options(synchronize_session=False)
    )
    if version_cas.rowcount != 1:
        session.rollback()
        _reject_workflow_action(
            session,
            action="FIXING_CONCURRENT_REJECTION_REJECTED",
            object_type="DEAL_EVENT",
            object_id=ev.id,
            current=current,
            message="Rejet non enregistré — cette version a déjà été traitée par une autre session.",
            failures=[_workflow_failure(
                "FIXING_VERSION_ALREADY_DECIDED",
                "fixing_version.status",
                "La transition attendue RECEIVED/PARTIAL → REJECTED n’est plus disponible.",
                expected="Une version courante au statut RECEIVED ou PARTIAL.",
                action="Actualisez l’événement et consultez la décision déjà enregistrée.",
            )],
            status_code=409,
        )

    session.expire(version)
    version = session.get(OfficialFixingVersion, version.id)
    restored = None
    if version.supersedes_id:
        restored = session.get(OfficialFixingVersion, version.supersedes_id)
        if not restored or restored.status != FixingStatus.CONTESTED:
            session.rollback()
            _reject_workflow_action(
                session,
                action="FIXING_REJECTION_RESTORE_REJECTED",
                object_type="DEAL_EVENT",
                object_id=ev.id,
                current=current,
                message="Rejet non appliqué — la version officielle précédente ne peut pas être restaurée sûrement.",
                failures=[_workflow_failure(
                    "PREVIOUS_FIXING_VERSION_NOT_RESTORABLE",
                    "supersedes_id",
                    "La version remplacée est absente ou n’est plus au statut CONTESTED.",
                    expected="Une version précédente CONTESTED et inchangée.",
                    action="Bloquez le traitement et faites contrôler l’historique des versions.",
                    received=version.supersedes_id,
                )],
                status_code=409,
            )
        restored.status = FixingStatus.VALIDATED
        session.add(restored)
        ev.spots_json = restored.spots_json
        ev.source = "manuel"
        ev.data_category = DataCategory.FIXING_OFFICIAL
        ev.fixing_status = FixingStatus.VALIDATED
        ev.current_fixing_version_id = restored.id
        ev.fixing_version = restored.version
        ev.fixing_entered_by = restored.entered_by
        ev.fixing_entered_at = restored.received_at
        ev.fixing_provider = restored.provider
        ev.fixing_source_type = restored.source_type
        ev.fixing_external_reference = restored.external_reference
        ev.fixing_observed_at = restored.observed_at
        ev.fixing_venue = restored.venue
        ev.fixing_calendar = restored.calendar
        ev.fixing_timezone = restored.timezone
        ev.fixing_evidence_sha256 = restored.evidence_sha256
        ev.fixing_record_sha256 = restored.record_sha256
        ev.fixing_reason = restored.capture_reason
        ev.validated_by = restored.validated_by
        ev.validated_at = restored.validated_at
        ev.applied_at = restored.applied_at
        ev.status = "observé"
    else:
        ev.fixing_status = FixingStatus.REJECTED
        ev.data_category = DataCategory.FIXING_CANDIDATE
        ev.validated_by = None
        ev.validated_at = None
        ev.applied_at = None
    session.add(ev)
    record_audit_event(
        session,
        action="FIXING_CORRECTION_REJECTED" if restored else "FIXING_REJECTED",
        object_type="DEAL_EVENT",
        object_id=ev.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_event_row(ev),
        reason=body.reason,
        data_source=(
            DataCategory.FIXING_OFFICIAL if restored
            else DataCategory.FIXING_CANDIDATE
        ),
        metadata={
            "rejected_fixing_version_id": version.id,
            "rejected_fixing_version": version.version,
            "restored_fixing_version_id": restored.id if restored else None,
            "restored_fixing_version": restored.version if restored else None,
            "maker_user_id": version.entered_by,
            "checker_user_id": current.id,
        },
    )
    session.commit()
    session.refresh(ev)
    return _event_row(ev)


def _ensure_alert(
    session: Session,
    deal: Deal,
    kind: str,
    message: str,
    dedup_key: str,
) -> Alert:
    existing = session.exec(
        select(Alert).where(Alert.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    alert = Alert(
        user_id=deal.user_id,
        deal_id=deal.id,
        deal_reference=deal.reference,
        kind=kind,
        message=message,
        dedup_key=dedup_key,
    )
    session.add(alert)
    return alert


def _evaluate_lifecycle(deal: Deal, events: list, dates_list: list, prices: dict,
                         tickers: list) -> dict | None:
    """Replay the booked script against the historical prices already loaded
    for events/refresh, to find out whether the product has actually called
    early or reached maturity — vs. just knowing raw spot values without
    ever checking them against the payoff condition. Returns a small summary
    dict for the API response, or None if evaluation couldn't run (e.g. a
    CONSTAT-based script whose calendar overrides aren't persisted on the
    deal — a known gap, not fatal to the spot refresh above).

    This function is deliberately pure with respect to persistence: indicative
    market data may propose a result, but it may never apply it."""
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    compiled = parse_script(deal.script_snapshot)
    # Expert-mode deals: CONSTAT calendars frozen at booking (market.constats,
    # persisted since 2026-07-19) — resolved relative to the deal's value_date,
    # not today. Deals booked before that persistence still raise ValueError
    # here, which callers already treat as "replay unavailable".
    _origin = deal.strike_date or deal.value_date
    compiled = resolve_constats(
        compiled, market.get("constats") or {},
        anchor=date.fromisoformat(_origin) if _origin else None,
        currency=(deal.devise or "").strip().upper() or None,
    )
    r_frac = snapshot_rate(market)
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
    # Keep the same precision as the authoritative fixing replay.  Rounding
    # the monitoring leg to four decimals created false payout mismatches on
    # large notionals even when both calculations were economically identical.
    realized_payout = round(sum(cf["cf"] for cf in res["cash_flows"]), 8)

    if res["early_recall"]:
        T_actual = res["T_actual"]
        triggering = min(non_strike, key=lambda e: abs(e.t_years - T_actual))
        return {"outcome": "callé", "event_id": triggering.id,
                "event_date": triggering.event_date, "t_years": triggering.t_years,
                "realized_payout": realized_payout}

    # No early recall — only conclude "matured" if today has actually
    # reached the maturity date. T_actual == T_max on its own is ambiguous:
    # eval_script_on_history also returns that when the price history simply
    # doesn't extend far enough yet to know (see its mat_events branch).
    if today_str >= deal.maturity_date:
        maturity_payout = sum(cf["cf"] for cf in res["cash_flows"] if abs(cf["t"] - deal.T) < 1e-6)
        maturity_event = max(events, key=lambda e: e.t_years)
        # The label comes from explicit script state (KI/BREACHED variables),
        # never from the amount paid. A capital-protected or option payoff can
        # be below par without being a knock-in.
        outcome, outcome_basis = semantic_maturity_outcome(compiled, res)
        return {"outcome": outcome, "event_id": maturity_event.id,
                "event_date": maturity_event.event_date,
                "outcome_basis": outcome_basis,
                "maturity_payout": round(maturity_payout, 8),
                "realized_payout": realized_payout}

    return {"outcome": "en_cours"}


@router.post("/{deal_id}/events/refresh")
def refresh_events(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Load non-binding monitoring data and, when relevant, propose a result."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    try:
        return refresh_deal_core(deal, session, actor_user_id=current.id)
    except ValueError as e:
        raise HTTPException(422, {
            "code": "LIFECYCLE_REFRESH_ERROR",
            "message": str(e),
        })


def _create_lifecycle_proposal(
    deal: Deal,
    evaluation: dict | None,
    session: Session,
    actor_user_id: int | None,
) -> LifecycleProposal | None:
    if not evaluation or evaluation.get("outcome") == "en_cours":
        return None
    outcome = str(evaluation["outcome"])
    event_id = evaluation.get("event_id")
    dedup_key = f"lifecycle:{deal.id}:{event_id}:{outcome}"
    existing = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing

    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=event_id,
        dedup_key=dedup_key,
        status=LifecycleStatus.PROPOSED,
        proposed_outcome=outcome,
        result_json=json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        data_source=DataCategory.INDICATIVE,
        proposed_by=actor_user_id,
    )
    session.add(proposal)
    session.flush()
    _ensure_alert(
        session,
        deal,
        "resolution_proposed",
        f"Résolution {outcome!r} proposée pour {deal.reference}; validation humaine requise.",
        f"proposal:{proposal.dedup_key}",
    )
    record_audit_event(
        session,
        action="RESOLUTION_PROPOSED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="SUCCESS",
        after=_proposal_row(proposal),
        reason="Résultat proposé par le monitoring; aucune application automatique.",
        data_source=DataCategory.INDICATIVE,
    )
    return proposal


def refresh_deal_core(
    deal: Deal,
    session: Session,
    actor_user_id: int | None = None,
) -> dict:
    """Refresh indicative data with persistent, visible error reporting."""
    deal_id = deal.id
    reference = deal.reference
    user_id = deal.user_id
    try:
        return _refresh_deal_core(deal, session, actor_user_id)
    except Exception as exc:
        session.rollback()
        current_deal = session.get(Deal, deal_id)
        if current_deal:
            _ensure_alert(
                session,
                current_deal,
                "lifecycle_error",
                f"Erreur de monitoring lifecycle sur {reference}: {exc}",
                f"lifecycle-error:{deal_id}:{date.today().isoformat()}:{type(exc).__name__}",
            )
        record_audit_event(
            session,
            action="LIFECYCLE_REFRESH_ERROR",
            object_type="DEAL",
            object_id=deal_id,
            actor_user_id=actor_user_id,
            actor_type="USER" if actor_user_id else "PROCESS",
            result="ERROR",
            reason=str(exc),
            data_source=DataCategory.INDICATIVE,
            metadata={"deal_reference": reference, "user_id": user_id,
                      "exception_type": type(exc).__name__},
        )
        session.commit()
        raise ValueError(str(exc)) from exc


def _refresh_deal_core(
    deal: Deal,
    session: Session,
    actor_user_id: int | None,
) -> dict:
    """Internal transactional body; callers use ``refresh_deal_core``."""
    underlyings = json.loads(deal.underlyings_json)
    missing_tickers = [u.get("name", "?") for u in underlyings if not u.get("ticker")]
    if missing_tickers:
        raise ValueError(
            "Ticker manquant pour: " + ", ".join(str(name) for name in missing_tickers))
    tickers = [u["ticker"] for u in underlyings]
    if not tickers:
        raise ValueError("Aucun sous-jacent défini sur ce deal")

    if deal.fixing_policy == FixingPolicy.AUTO_YAHOO.value:
        return _refresh_auto_yahoo_deal_core(
            deal, session, actor_user_id, underlyings, tickers)

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

    def _closest_price(ticker: str, target_date: str) -> tuple[float | None, str | None]:
        if ticker not in prices:
            return None, None
        available = [d for d in dates_list if d <= target_date]
        if not available:
            return None, None
        used_date = available[-1]
        idx = date_idx[used_date]
        val = prices[ticker][idx]
        return (round(float(val), 4), used_date) if val is not None else (None, used_date)

    updated = 0
    for ev in past_events:
        spots = {}
        used_dates = {}
        for u in underlyings:
            tk = u.get("ticker", "")
            name = u["name"]
            spot, used_date = _closest_price(tk, ev.event_date)
            if spot is not None:
                spots[name] = spot
                used_dates[name] = used_date
        if len(spots) != len(underlyings):
            missing = [u["name"] for u in underlyings if u["name"] not in spots]
            raise ValueError(
                f"Données indicatives partielles au {ev.event_date}; manquantes: {', '.join(missing)}")
        if spots:
            before = json.loads(ev.indicative_spots_json or "{}")
            if before == spots:
                continue
            ev.indicative_spots_json = json.dumps(spots, sort_keys=True)
            session.add(ev)
            updated += 1
            fallbacks = {
                name: used for name, used in used_dates.items() if used != ev.event_date}
            record_audit_event(
                session,
                action="INDICATIVE_DATA_USED",
                object_type="DEAL_EVENT",
                object_id=ev.id,
                actor_user_id=actor_user_id,
                actor_type="USER" if actor_user_id else "PROCESS",
                result="SUCCESS",
                before={"indicative_spots": before},
                after={"indicative_spots": spots},
                reason="Mise à jour de données de monitoring non opposables.",
                data_source=DataCategory.INDICATIVE,
                metadata={"provider": "Yahoo Finance", "price_dates": used_dates,
                          "fallback_dates": fallbacks},
            )
            if fallbacks:
                _ensure_alert(
                    session,
                    deal,
                    "data_fallback",
                    f"Fallback de date de marché au {ev.event_date}: {fallbacks}",
                    f"data-fallback:{deal.id}:{ev.id}:{json.dumps(fallbacks, sort_keys=True)}",
                )
                record_audit_event(
                    session,
                    action="DATA_FALLBACK_USED",
                    object_type="DEAL_EVENT",
                    object_id=ev.id,
                    actor_user_id=actor_user_id,
                    actor_type="USER" if actor_user_id else "PROCESS",
                    result="SUCCESS",
                    reason="Dernière clôture disponible antérieure à la date contractuelle.",
                    data_source=DataCategory.INDICATIVE,
                    metadata={"fallback_dates": fallbacks},
                )

    evaluation = _evaluate_lifecycle(deal, events, dates_list, prices, tickers)
    proposal = _create_lifecycle_proposal(
        deal, evaluation, session, actor_user_id)

    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return {
        "updated": updated,
        "message": f"{updated} événement(s) indicatif(s) mis à jour",
        "evaluation": evaluation,
        "proposal": _proposal_row(proposal) if proposal else None,
    }


_AUTO_YAHOO_MAX_FALLBACK_DAYS = 4
_AUTO_YAHOO_MAX_DAILY_MOVE = 0.50


def _reference_history_arrays(
    reference_data: dict, tickers: list[str],
) -> tuple[list[str], dict[str, list[float]]]:
    """Align independent raw-close series without backfilling the past."""
    series = reference_data.get("series") or {}
    union_dates = sorted({
        market_date
        for ticker in tickers
        for market_date in (series.get(ticker) or {})
    })
    last_values: dict[str, float] = {}
    dates: list[str] = []
    prices = {ticker: [] for ticker in tickers}
    for market_date in union_dates:
        for ticker in tickers:
            value = (series.get(ticker) or {}).get(market_date)
            if value is not None:
                last_values[ticker] = float(value)
        # Forward-fill only after every ticker has published at least one
        # close.  A future close is never backfilled into an earlier date.
        if any(ticker not in last_values for ticker in tickers):
            continue
        dates.append(market_date)
        for ticker in tickers:
            prices[ticker].append(last_values[ticker])
    return dates, prices


def _auto_yahoo_event_values(
    event: DealEvent,
    underlyings: list[dict],
    reference_data: dict,
) -> tuple[dict, dict, list[dict], bool]:
    """Resolve and quality-check one contractual Yahoo close.

    Returns ``(spots, used_dates, failures, waiting_for_close)``.  The policy
    is explicit: exact close for an event dated today; otherwise the last
    unadjusted close on or before the date, no more than four calendar days
    old.  Splits and daily moves above 50% are escalated instead of silently
    becoming contractual facts.
    """
    series = reference_data.get("series") or {}
    splits = reference_data.get("splits") or {}
    currencies = reference_data.get("currencies") or {}
    spots: dict[str, float] = {}
    used_dates: dict[str, str] = {}
    failures: list[dict] = []
    waiting_for_close = False
    today = date.today().isoformat()
    target = date.fromisoformat(event.event_date)
    for underlying in underlyings:
        name = str(underlying.get("name") or "").strip()
        ticker = str(underlying.get("ticker") or "").strip()
        ticker_series = series.get(ticker) or {}
        available = sorted(d for d in ticker_series if d <= event.event_date)
        if not available:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_MISSING", f"spots.{name}",
                "Aucune clôture Yahoo n'est disponible à la date contractuelle.",
                expected=f"Une clôture non ajustée pour {ticker} au plus tard le {event.event_date}.",
                action="Vérifiez le ticker Yahoo ou traitez cette constatation en exception contrôlée.",
                received=None,
            ))
            continue
        used_date = available[-1]
        if event.event_date == today and used_date != event.event_date:
            waiting_for_close = True
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_NOT_PUBLISHED", f"spots.{name}",
                "La clôture Yahoo du jour n'est pas encore publiée.",
                expected=f"La clôture non ajustée du {event.event_date} pour {ticker}.",
                action="Relancez l'actualisation après la clôture du marché.",
                received=used_date,
            ))
            continue
        value = float(ticker_series[used_date])
        if not math.isfinite(value) or value <= 0:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_INVALID", f"spots.{name}",
                "La clôture Yahoo n'est pas une valeur strictement positive.",
                expected="Une valeur numérique finie et strictement positive.",
                action="Contrôlez la publication Yahoo ou utilisez le workflow d'exception.",
                received=value,
            ))
            continue
        # Keep the provider value visible even when a quality control below
        # escalates it.  A human cannot make an informed decision if the UI
        # only says "outlier" without showing the value under review.
        spots[name] = round(value, 8)
        used_dates[name] = used_date
        lag_days = (target - date.fromisoformat(used_date)).days
        if lag_days > _AUTO_YAHOO_MAX_FALLBACK_DAYS:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_STALE", f"spots.{name}",
                "La dernière clôture Yahoo est trop ancienne pour faire foi automatiquement.",
                expected=f"Un écart de 0 à {_AUTO_YAHOO_MAX_FALLBACK_DAYS} jours calendaires.",
                action="Vérifiez le calendrier, le ticker et la source avant validation manuelle.",
                received={"market_date": used_date, "lag_days": lag_days, "close": value},
            ))
        expected_currency = str(underlying.get("ccy") or "").strip().upper()
        provider_currency = str(currencies.get(ticker) or "").strip().upper()
        if (expected_currency and provider_currency and
                expected_currency != provider_currency):
            failures.append(_workflow_failure(
                "YAHOO_CURRENCY_MISMATCH", f"underlyings.{name}.ccy",
                "La devise publiée par Yahoo ne correspond pas à la devise contractuelle du sous-jacent.",
                expected=expected_currency,
                action="Corrigez le ticker ou la devise contractuelle avant toute application.",
                received=provider_currency,
            ))
        if abs(float((splits.get(ticker) or {}).get(used_date, 0) or 0)) > 1e-12:
            failures.append(_workflow_failure(
                "YAHOO_CORPORATE_ACTION", f"spots.{name}",
                "Yahoo signale un split à la date du fixing.",
                expected="Aucune corporate action non réconciliée.",
                action="Contrôlez le ratio du split et les termes contractuels avant application.",
                received={"market_date": used_date, "split": splits[ticker][used_date]},
            ))
        previous_dates = [d for d in sorted(ticker_series) if d < used_date]
        if previous_dates:
            previous = float(ticker_series[previous_dates[-1]])
            if previous > 0 and abs(value / previous - 1.0) > _AUTO_YAHOO_MAX_DAILY_MOVE:
                failures.append(_workflow_failure(
                    "YAHOO_CLOSE_OUTLIER", f"spots.{name}",
                    "La variation quotidienne Yahoo dépasse le seuil de contrôle automatique.",
                    expected=f"Une variation absolue inférieure ou égale à {_AUTO_YAHOO_MAX_DAILY_MOVE:.0%}.",
                    action="Contrôlez une éventuelle corporate action ou une erreur de ticker.",
                    received={
                        "previous_market_date": previous_dates[-1],
                        "previous_close": previous,
                        "market_date": used_date,
                        "close": value,
                    },
                ))
    return spots, used_dates, failures, waiting_for_close


def _auto_yahoo_evidence(
    deal: Deal,
    event: DealEvent,
    underlyings: list[dict],
    spots: dict,
    used_dates: dict,
    fetched_at: str,
    provider_currencies: dict,
) -> tuple[dict, bytes, str]:
    inputs = []
    for underlying in underlyings:
        name = underlying["name"]
        inputs.append({
            "name": name,
            "ticker": underlying["ticker"],
            "market_date": used_dates[name],
            "unadjusted_close": spots[name],
            "currency": underlying.get("ccy") or deal.devise,
            "provider_currency": provider_currencies.get(underlying["ticker"]),
        })
    evidence = {
        "provider": "YAHOO_FINANCE",
        "price_type": "UNADJUSTED_CLOSE",
        "policy": FixingPolicy.AUTO_YAHOO.value,
        "fallback_rule": f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "fetched_at": fetched_at,
        "inputs": inputs,
    }
    payload = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return evidence, payload, hashlib.sha256(payload).hexdigest()


def _auto_exception_manual_evidence(
    deal: Deal,
    event: DealEvent,
    *,
    action: str,
    spots: dict,
    source_reference: str,
    reason: str,
    actor_user_id: int,
    previous_version: OfficialFixingVersion | None,
) -> tuple[dict, bytes, str]:
    evidence = {
        "evidence_type": "AUTO_YAHOO_USER_EXCEPTION_DECISION",
        "policy": FixingPolicy.AUTO_YAHOO.value,
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "action": action,
        "actor_user_id": actor_user_id,
        "source_reference": source_reference,
        "reason": reason,
        "spots": spots,
        "previous_version_id": previous_version.id if previous_version else None,
        "previous_version": previous_version.version if previous_version else None,
        "previous_spots": json.loads(event.spots_json or "{}"),
        "last_yahoo_spots": json.loads(event.indicative_spots_json or "{}"),
        "decided_at": datetime.utcnow().isoformat(),
    }
    payload = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return evidence, payload, hashlib.sha256(payload).hexdigest()


def _user_exception_lifecycle_evaluation(
    deal: Deal,
    session: Session,
) -> tuple[dict | None, list[dict]]:
    """Derive a terminal fact only from all reached official observations."""
    today = date.today().isoformat()
    reached = [event for event in _get_events(deal.id, session)
               if event.event_date <= today]
    pending = [event for event in reached if (
        event.fixing_status not in {
            FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
        }
        or event.data_category != DataCategory.FIXING_OFFICIAL.value
    )]
    if pending:
        return None, [_workflow_failure(
            "AUTO_USER_EXCEPTION_STILL_PENDING",
            "events",
            "Toutes les constatations déjà atteintes ne sont pas encore officielles.",
            expected="Une décision utilisateur sur chaque exception atteinte.",
            action="Traitez les autres lignes signalées en exception.",
            received=[event.id for event in pending],
        )]
    if not reached:
        return {"outcome": "en_cours"}, []
    official_result, failures = replay_official_fixings(deal, reached)
    if failures or not official_result:
        return None, failures
    if official_result.get("outcome") == "callé":
        return official_result, []
    if today >= deal.maturity_date:
        maturity = max(reached, key=lambda row: row.t_years)
        if abs(maturity.t_years - deal.T) <= 1e-6:
            return official_result, []
    return {"outcome": "en_cours"}, []


def _pending_auto_fixing_exceptions(deal: Deal, session: Session) -> list[DealEvent]:
    today = date.today().isoformat()
    return [event for event in _get_events(deal.id, session) if (
        event.event_date <= today and event.fixing_status in {
            FixingStatus.RECEIVED.value,
            FixingStatus.PARTIAL.value,
            FixingStatus.MISSING.value,
            FixingStatus.REJECTED.value,
            FixingStatus.CONTESTED.value,
            FixingStatus.MANUAL_REVIEW_REQUIRED.value,
        }
    )]


@router.post("/{deal_id}/events/{event_id}/resolve-auto-exception")
def resolve_auto_fixing_exception(
    deal_id: int,
    event_id: int,
    body: AutoFixingExceptionResolutionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Make the authenticated deal user accountable for an AUTO exception.

    This is deliberately not the FOUR_EYES endpoint.  It creates a new,
    immutable, user-signed official version and then replays the product from
    official fixings.  The provider feed or a concurrent human version can
    never be overwritten in place.
    """
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    if current.id != deal.user_id and getattr(current, "role", None) != "admin":
        raise HTTPException(403, {
            "code": "AUTO_EXCEPTION_USER_RESPONSIBILITY_REQUIRED",
            "message": "Cette exception doit être décidée par le propriétaire du deal.",
        })
    event = session.get(DealEvent, event_id)
    if not event or event.deal_id != deal.id:
        raise HTTPException(404, "Événement introuvable")

    failures: list[dict] = []
    if deal.fixing_policy != FixingPolicy.AUTO_YAHOO.value:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_POLICY_REQUIRED", "fixing_policy",
            "La validation mono-utilisateur est réservée aux produits Yahoo automatiques.",
            expected=FixingPolicy.AUTO_YAHOO.value,
            action="Utilisez le workflow Maker/Checker du produit contrôlé.",
            received=deal.fixing_policy,
        ))
    if event.event_date > date.today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_EVENT_IN_FUTURE", "event_date",
            "La constatation contractuelle n'est pas encore atteinte.",
            expected="Une date atteinte.",
            action="Attendez la date de constatation.", received=event.event_date,
        ))
    if event.fixing_status not in {
        FixingStatus.RECEIVED.value, FixingStatus.PARTIAL.value,
        FixingStatus.MISSING.value, FixingStatus.REJECTED.value,
        FixingStatus.CONTESTED.value, FixingStatus.MANUAL_REVIEW_REQUIRED.value,
    }:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_STATUS_INVALID", "fixing_status",
            "Cette constatation n'est plus dans un état d'exception traitable.",
            expected="Une exception ouverte et non appliquée.",
            action="Actualisez le deal et consultez son dernier statut.",
            received=event.fixing_status,
        ))
    current_version = (
        session.get(OfficialFixingVersion, event.current_fixing_version_id)
        if event.current_fixing_version_id else None
    )
    if body.expected_version_id != event.current_fixing_version_id:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_VERSION_CONFLICT", "expected_version_id",
            "La version affichée n'est plus la version courante.",
            expected=str(event.current_fixing_version_id),
            action="Actualisez la fiche puis contrôlez la nouvelle version.",
            received=body.expected_version_id,
        ))
    if current_version and current_version.status == FixingStatus.APPLIED.value:
        failures.append(_workflow_failure(
            "APPLIED_FIXING_CORRECTION_REQUIRES_CANCEL_REPLACE", "fixing_version.status",
            "Le fixing a déjà été consommé par une résolution appliquée.",
            expected="Un fixing non appliqué.",
            action="Utilisez une procédure d'annulation/remplacement.",
            received=current_version.status,
        ))
    if failures:
        _reject_workflow_action(
            session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
            object_type="DEAL_EVENT", object_id=event.id, current=current,
            message=f"Exception non traitée — {len(failures)} contrôle(s) bloquant(s).",
            failures=failures, status_code=409, before=_event_row(event),
        )

    before = _event_row(event)
    underlyings = json.loads(deal.underlyings_json or "[]")
    spots: dict
    provider: str
    source_type: str
    external_reference: str
    venue: str
    calendar: str
    observed_at: datetime
    evidence_payload: bytes
    evidence_hash: str
    review_failures: list[dict] = []
    if body.action == "USE_YAHOO":
        tickers = [str(row.get("ticker") or "").strip() for row in underlyings]
        if not tickers or any(not ticker for ticker in tickers):
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Valeur Yahoo indisponible — ticker contractuel manquant.",
                failures=[_workflow_failure(
                    "YAHOO_TICKER_MISSING", "underlyings.ticker",
                    "Un ticker Yahoo est absent.", expected="Un ticker par sous-jacent.",
                    action="Corrigez le référentiel ou saisissez une valeur manuelle.")],
                before=before,
            )
        fetch_start = (date.fromisoformat(event.event_date) - timedelta(days=7)).isoformat()
        reference_data = load_yahoo_reference_closes(
            tickers, fetch_start, date.today().isoformat())
        if "error" in reference_data:
            raise HTTPException(422, {
                "code": "YAHOO_PROVIDER_ERROR",
                "message": f"Yahoo indisponible : {reference_data['error']}",
                "action": "Réessayez ou choisissez une décision manuelle.",
            })
        spots, used_dates, review_failures, waiting = _auto_yahoo_event_values(
            event, underlyings, reference_data)
        hard_codes = {
            "YAHOO_CLOSE_MISSING", "YAHOO_CLOSE_INVALID",
            "YAHOO_CLOSE_NOT_PUBLISHED", "YAHOO_CURRENCY_MISMATCH",
        }
        hard_failures = [failure for failure in review_failures
                         if failure["code"] in hard_codes]
        spot_failures = _spot_failures(deal, spots)
        if waiting or hard_failures or spot_failures:
            normalized = hard_failures + [
                _workflow_failure(
                    failure["code"],
                    f"spots.{failure.get('underlying', '')}".rstrip("."),
                    "La valeur Yahoo n'est pas exploitable pour tous les sous-jacents.",
                    expected="Une clôture complète, positive et dans la devise contractuelle.",
                    action="Corrigez le ticker ou choisissez une saisie manuelle.",
                    received=failure.get("value"),
                ) for failure in spot_failures
            ]
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Valeur Yahoo non adoptée — la donnée reste inexploitable.",
                failures=normalized, before=before,
            )
        # Accepting a clean Yahoo close needs no motive — see the schema. But a
        # USE_YAHOO that survives a soft control is the operator overruling that
        # control, and an overrule with no stated reason leaves nothing in the
        # ledger to review later.
        if review_failures and len(body.reason.strip()) < 10:
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Motif requis — cette reprise Yahoo écarte un contrôle.",
                failures=[_workflow_failure(
                    "AUTO_EXCEPTION_REASON_REQUIRED", "reason",
                    "Reprendre la clôture Yahoo malgré un contrôle en échec "
                    "doit être motivé.",
                    expected="Un motif de 10 caractères minimum.",
                    action="Décrivez le contrôle effectué avant d'officialiser.",
                    received=body.reason or None,
                )],
                before=before,
            )
        evidence, evidence_payload, evidence_hash = _auto_yahoo_evidence(
            deal, event, underlyings, spots, used_dates,
            str(reference_data.get("fetched_at") or datetime.utcnow().isoformat()),
            reference_data.get("currencies") or {},
        )
        if review_failures:
            evidence["user_reviewed_failures"] = review_failures
            evidence["user_decision_reason"] = body.reason
            evidence_payload = json.dumps(
                evidence, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")
            evidence_hash = hashlib.sha256(evidence_payload).hexdigest()
        provider, source_type = "YAHOO_FINANCE", "API"
        external_reference = (
            f"YAHOO-USER:{event.event_date}:{','.join(used_dates.values())}")
        venue = "Yahoo Finance"
        calendar = f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D"
        observed_at = datetime.fromisoformat(f"{max(used_dates.values())}T00:00:00")
    else:
        spots = (
            json.loads(event.spots_json or "{}")
            if body.action == "CONFIRM_CURRENT" else dict(body.spots or {})
        )
        decision_failures = _spot_failures(deal, spots)
        if body.action == "REPLACE_MANUAL" and len(body.source_reference.strip()) < 3:
            decision_failures.append({
                "code": "MANUAL_SOURCE_REFERENCE_MISSING",
                "underlying": "source_reference", "value": body.source_reference,
            })
        if decision_failures:
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Décision non enregistrée — valeur ou source incomplète.",
                failures=[_workflow_failure(
                    failure["code"],
                    ("source_reference" if failure.get("underlying") == "source_reference"
                     else f"spots.{failure.get('underlying', '')}".rstrip(".")),
                    ("La référence de la source manuelle est obligatoire."
                     if failure.get("underlying") == "source_reference" else
                     "Le fixing doit contenir une valeur strictement positive par sous-jacent."),
                    expected=("Au moins 3 caractères."
                              if failure.get("underlying") == "source_reference" else
                              "Une valeur numérique strictement positive."),
                    action=("Indiquez le message, document ou source contrôlée."
                            if failure.get("underlying") == "source_reference" else
                            "Complétez ou corrigez la valeur."),
                    received=failure.get("value"),
                ) for failure in decision_failures],
                before=before,
            )
        source_reference = body.source_reference.strip()
        if body.action == "CONFIRM_CURRENT" and not source_reference:
            source_reference = (
                current_version.external_reference if current_version else
                f"EVENT:{event.id}:CURRENT_VALUE")
        _, evidence_payload, evidence_hash = _auto_exception_manual_evidence(
            deal, event, action=body.action, spots=spots,
            source_reference=source_reference, reason=body.reason,
            actor_user_id=current.id, previous_version=current_version,
        )
        provider = (
            current_version.provider
            if body.action == "CONFIRM_CURRENT" and current_version else
            "USER_DECLARED_SOURCE")
        source_type = "USER_DECISION"
        external_reference = source_reference
        venue = current_version.venue if current_version else "User exception decision"
        calendar = current_version.calendar if current_version else "CONTRACTUAL_EVENT_DATE"
        observed_at = (
            current_version.observed_at if current_version else
            datetime.fromisoformat(f"{event.event_date}T12:00:00"))

    latest = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version.desc())
    ).first()
    next_version = (latest.version if latest else 0) + 1
    supersedes_id = current_version.id if current_version else None
    decided_at = datetime.utcnow()
    evidence_filename = f"user-decision-{deal.reference}-{event.event_date}.json"
    capture_reason = (
        "Adoption explicite de la clôture Yahoo par l'utilisateur."
        if body.action == "USE_YAHOO" else
        "Confirmation utilisateur de la valeur courante."
        if body.action == "CONFIRM_CURRENT" else
        "Correction manuelle décidée par l'utilisateur."
    )
    record_payload = {
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "event_index": event.event_index,
        "version": next_version,
        "supersedes_id": supersedes_id,
        "underlyings": underlyings,
        "spots": spots,
        "provider": provider,
        "source_type": source_type,
        "external_reference": external_reference,
        "observed_at": observed_at.replace(tzinfo=timezone.utc).isoformat(),
        "venue": venue,
        "calendar": calendar,
        "timezone": "MARKET_LOCAL_DATE" if body.action == "USE_YAHOO" else "UTC",
        "evidence_sha256": evidence_hash,
        "evidence_filename": evidence_filename,
        "evidence_content_type": "application/json",
        "evidence_size_bytes": len(evidence_payload),
        "capture_reason": capture_reason,
    }
    version = OfficialFixingVersion(
        deal_id=deal.id, deal_event_id=event.id, version=next_version,
        supersedes_id=supersedes_id, status=FixingStatus.VALIDATED.value,
        spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
        provider=provider, source_type=source_type,
        external_reference=external_reference, observed_at=observed_at,
        received_at=decided_at, venue=venue, calendar=calendar,
        timezone=record_payload["timezone"], evidence_sha256=evidence_hash,
        evidence_filename=evidence_filename,
        evidence_content_type="application/json",
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        record_sha256=_fixing_record_hash(record_payload),
        capture_reason=capture_reason, entered_by=current.id,
        capture_actor_type="USER", validated_by=current.id,
        validation_reason=body.reason, validated_at=decided_at,
    )
    if current_version:
        current_version.status = FixingStatus.SUPERSEDED.value
        session.add(current_version)
    session.add(version)
    session.flush()
    event.spots_json = version.spots_json
    event.source = "auto" if body.action == "USE_YAHOO" else "manuel"
    event.status = "observé"
    event.fixing_status = FixingStatus.VALIDATED.value
    event.data_category = DataCategory.FIXING_OFFICIAL.value
    event.current_fixing_version_id = version.id
    event.fixing_version = version.version
    event.fixing_entered_by = current.id
    event.fixing_entered_at = decided_at
    event.fixing_provider = version.provider
    event.fixing_source_type = version.source_type
    event.fixing_external_reference = version.external_reference
    event.fixing_observed_at = version.observed_at
    event.fixing_venue = version.venue
    event.fixing_calendar = version.calendar
    event.fixing_timezone = version.timezone
    event.fixing_evidence_sha256 = version.evidence_sha256
    event.fixing_record_sha256 = version.record_sha256
    event.fixing_reason = version.capture_reason
    event.validated_by = current.id
    event.validated_at = decided_at
    session.add(event)
    for proposal in session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == deal.id,
        LifecycleProposal.status.in_([
            LifecycleStatus.PROPOSED.value,
            LifecycleStatus.VALIDATED.value,
            LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        ]),
    )).all():
        proposal.status = LifecycleStatus.STALE.value
        proposal.error_message = (
            f"Fixing {event.event_date} décidé par l'utilisateur en version {version.version}.")
        proposal.updated_at = decided_at
        session.add(proposal)
    for alert in session.exec(select(Alert).where(
        Alert.deal_id == deal.id,
        Alert.read == False,  # noqa: E712
        Alert.dedup_key.startswith(
            f"auto-fixing-exception:{deal.id}:{event.id}:"),
    )).all():
        alert.read = True
        session.add(alert)
    record_audit_event(
        session,
        action=f"AUTO_FIXING_EXCEPTION_{body.action}",
        object_type="DEAL_EVENT", object_id=event.id,
        actor_user_id=current.id, actor_type="USER", result="SUCCESS",
        before=before, after=_event_row(event), reason=body.reason,
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "policy": deal.fixing_policy,
            "decision_action": body.action,
            "previous_version_id": supersedes_id,
            "fixing_version_id": version.id,
            "reviewed_failures": review_failures,
            "source_reference": body.source_reference,
        },
    )
    deal.updated_at = decided_at
    session.add(deal)
    session.commit()
    session.refresh(event)

    evaluation, replay_failures = _user_exception_lifecycle_evaluation(deal, session)
    proposal = None
    if evaluation and evaluation.get("outcome") != "en_cours":
        proposal = _auto_apply_lifecycle(
            deal, evaluation, session, actor_user_id=current.id)
        session.commit()
    remaining = _pending_auto_fixing_exceptions(deal, session)
    actor_label = getattr(current, "username", None) or f"utilisateur #{current.id}"
    if proposal and proposal.status == LifecycleStatus.APPLIED.value:
        message = (
            f"Fixing v{version.version} officialisé par {actor_label}; "
            f"résolution {proposal.proposed_outcome} appliquée automatiquement.")
    elif remaining:
        message = (
            f"Fixing v{version.version} officialisé par {actor_label}; "
            f"{len(remaining)} exception(s) reste(nt) à traiter.")
    elif replay_failures:
        message = (
            f"Fixing v{version.version} officialisé; le lifecycle reste bloqué : "
            f"{replay_failures[0].get('message', replay_failures[0].get('code'))}")
    else:
        message = (
            f"Fixing v{version.version} officialisé par {actor_label}; "
            "le produit reste en vie.")
    return {
        "event": _event_row(session.get(DealEvent, event.id)),
        "decision_action": body.action,
        "remaining_exceptions": len(remaining),
        "lifecycle_proposal": _proposal_row(proposal) if proposal else None,
        "replay_failures": replay_failures,
        "message": message,
    }


def _auto_yahoo_exception(
    deal: Deal,
    event: DealEvent,
    failures: list[dict],
    session: Session,
    actor_user_id: int | None,
    *,
    waiting_for_close: bool = False,
) -> dict:
    if not waiting_for_close:
        event.fixing_status = FixingStatus.MANUAL_REVIEW_REQUIRED.value
        event.source = "auto"
        session.add(event)
        _ensure_alert(
            session,
            deal,
            "auto_fixing_exception",
            f"Constatation Yahoo à contrôler pour {deal.reference} au {event.event_date}.",
            f"auto-fixing-exception:{deal.id}:{event.id}:"
            + hashlib.sha256(json.dumps(failures, sort_keys=True).encode()).hexdigest()[:16],
        )
    record_audit_event(
        session,
        action=("AUTO_FIXING_WAITING" if waiting_for_close else "AUTO_FIXING_REVIEW_REQUIRED"),
        object_type="DEAL_EVENT",
        object_id=event.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="REJECTED" if not waiting_for_close else "PENDING",
        before={"fixing_status": event.fixing_status},
        after={"failures": failures},
        reason=(
            "Clôture du jour non encore publiée."
            if waiting_for_close else
            "Les contrôles automatiques Yahoo n'autorisent pas ce fixing."
        ),
        data_source=DataCategory.INDICATIVE,
        metadata={"policy": deal.fixing_policy, "failures": failures},
    )
    return {
        "event_id": event.id,
        "event_date": event.event_date,
        "waiting_for_close": waiting_for_close,
        "failures": failures,
    }


def _auto_validate_yahoo_event(
    deal: Deal,
    event: DealEvent,
    underlyings: list[dict],
    reference_data: dict,
    session: Session,
    actor_user_id: int | None,
) -> tuple[bool, dict | None]:
    spots, used_dates, failures, waiting = _auto_yahoo_event_values(
        event, underlyings, reference_data)
    if spots:
        event.indicative_spots_json = json.dumps(
            spots, ensure_ascii=False, sort_keys=True)
        session.add(event)
    if failures:
        return False, _auto_yahoo_exception(
            deal, event, failures, session, actor_user_id,
            waiting_for_close=waiting and all(
                failure["code"] == "YAHOO_CLOSE_NOT_PUBLISHED"
                for failure in failures),
        )

    before = _event_row(event)
    current_version = (
        session.get(OfficialFixingVersion, event.current_fixing_version_id)
        if event.current_fixing_version_id else None
    )
    current_spots = json.loads(event.spots_json or "{}")
    if (current_version and current_spots == spots and
            event.fixing_status in {
                FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
            }):
        session.add(event)
        return False, None
    # A user-confirmed non-Yahoo exception is now the official fact for this
    # event.  Keep displaying the latest Yahoo value as indicative, but do
    # not reopen the same exception at every scheduled refresh.
    if (current_version and
            current_version.capture_actor_type == "USER" and
            current_version.provider != "YAHOO_FINANCE" and
            event.fixing_status in {
                FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
            }):
        session.add(event)
        return False, None
    if current_version and event.fixing_status not in {
        FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
    }:
        failure = _workflow_failure(
            "CONTROLLED_FIXING_PENDING", "fixing_status",
            "Une version de fixing est déjà en cours de traitement humain.",
            expected="Validation ou rejet explicite de la version courante.",
            action="Terminez le workflow d'exception affiché ; l'automatisation ne remplacera pas une saisie humaine.",
            received=event.fixing_status,
        )
        return False, _auto_yahoo_exception(
            deal, event, [failure], session, actor_user_id)

    evidence, evidence_payload, evidence_hash = _auto_yahoo_evidence(
        deal, event, underlyings, spots, used_dates,
        str(reference_data.get("fetched_at") or datetime.utcnow().isoformat()),
        reference_data.get("currencies") or {},
    )
    latest = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version.desc())
    ).first()
    next_version = (latest.version if latest else 0) + 1
    supersedes_id = current_version.id if current_version else None
    observed_date = max(used_dates.values())
    record_payload = {
        **evidence,
        "version": next_version,
        "supersedes_id": supersedes_id,
        "spots": spots,
        "evidence_sha256": evidence_hash,
        "capture_actor_type": "PROCESS",
    }
    record_hash = _fixing_record_hash(record_payload)

    # A changed Yahoo value is never allowed to overwrite an already official
    # fact silently.  Archive the new provider record and escalate the event.
    if current_version and current_spots != spots:
        revision = OfficialFixingVersion(
            deal_id=deal.id,
            deal_event_id=event.id,
            version=next_version,
            supersedes_id=current_version.id,
            status=FixingStatus.MANUAL_REVIEW_REQUIRED.value,
            spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
            provider="YAHOO_FINANCE",
            source_type="API",
            external_reference=f"YAHOO:{event.event_date}:{','.join(used_dates.values())}",
            observed_at=datetime.fromisoformat(f"{observed_date}T00:00:00"),
            received_at=datetime.utcnow(),
            venue="Yahoo Finance",
            calendar=f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
            timezone="MARKET_LOCAL_DATE",
            evidence_sha256=evidence_hash,
            evidence_filename=f"yahoo-{deal.reference}-{event.event_date}.json",
            evidence_content_type="application/json",
            evidence_size_bytes=len(evidence_payload),
            evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
            record_sha256=record_hash,
            capture_reason="Correction Yahoo détectée après validation automatique.",
            entered_by=deal.user_id,
            capture_actor_type="PROCESS",
        )
        session.add(revision)
        event.fixing_status = FixingStatus.CONTESTED.value
        session.add(event)
        failure = _workflow_failure(
            "YAHOO_OFFICIAL_REVISION_DETECTED", "spots",
            "Yahoo publie une valeur différente du fixing déjà officialisé.",
            expected=current_spots,
            action="Comparez les deux versions et décidez explicitement si le lifecycle doit être rejoué.",
            received=spots,
        )
        return False, _auto_yahoo_exception(
            deal, event, [failure], session, actor_user_id)

    validated_at = datetime.utcnow()
    version = OfficialFixingVersion(
        deal_id=deal.id,
        deal_event_id=event.id,
        version=next_version,
        supersedes_id=supersedes_id,
        status=FixingStatus.VALIDATED.value,
        spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
        provider="YAHOO_FINANCE",
        source_type="API",
        external_reference=f"YAHOO:{event.event_date}:{','.join(used_dates.values())}",
        observed_at=datetime.fromisoformat(f"{observed_date}T00:00:00"),
        received_at=validated_at,
        venue="Yahoo Finance",
        calendar=f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
        timezone="MARKET_LOCAL_DATE",
        evidence_sha256=evidence_hash,
        evidence_filename=f"yahoo-{deal.reference}-{event.event_date}.json",
        evidence_content_type="application/json",
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        record_sha256=record_hash,
        capture_reason="Validation automatique de la clôture Yahoo non ajustée.",
        entered_by=deal.user_id,
        capture_actor_type="PROCESS",
        validation_reason="Contrôles AUTO_YAHOO passés.",
        validated_at=validated_at,
    )
    session.add(version)
    session.flush()
    event.spots_json = json.dumps(spots, ensure_ascii=False, sort_keys=True)
    event.source = "auto"
    event.status = "observé"
    event.fixing_status = FixingStatus.VALIDATED.value
    event.data_category = DataCategory.FIXING_OFFICIAL.value
    event.current_fixing_version_id = version.id
    event.fixing_version = version.version
    event.fixing_entered_by = deal.user_id
    event.fixing_entered_at = validated_at
    event.fixing_provider = version.provider
    event.fixing_source_type = version.source_type
    event.fixing_external_reference = version.external_reference
    event.fixing_observed_at = version.observed_at
    event.fixing_venue = version.venue
    event.fixing_calendar = version.calendar
    event.fixing_timezone = version.timezone
    event.fixing_evidence_sha256 = version.evidence_sha256
    event.fixing_record_sha256 = version.record_sha256
    event.fixing_reason = version.capture_reason
    event.validated_by = None
    event.validated_at = validated_at
    session.add(event)
    record_audit_event(
        session,
        action="FIXING_AUTO_VALIDATED",
        object_type="DEAL_EVENT",
        object_id=event.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="SUCCESS",
        before=before,
        after=_event_row(event),
        reason="Clôture Yahoo non ajustée validée par les contrôles automatiques.",
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "policy": FixingPolicy.AUTO_YAHOO.value,
            "provider": "YAHOO_FINANCE",
            "price_type": "UNADJUSTED_CLOSE",
            "price_dates": used_dates,
            "provider_currencies": reference_data.get("currencies") or {},
            "fixing_version_id": version.id,
        },
    )
    return True, None


def _auto_review_proposal(
    deal: Deal,
    evaluation: dict,
    failures: list[dict],
    session: Session,
    actor_user_id: int | None,
) -> LifecycleProposal:
    fingerprint = hashlib.sha256(
        json.dumps(failures, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    dedup_key = (
        f"auto-lifecycle-review:{deal.id}:{evaluation.get('event_id')}:"
        f"{evaluation.get('outcome')}:{fingerprint}"
    )
    existing = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=evaluation.get("event_id"),
        dedup_key=dedup_key,
        status=LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        proposed_outcome=str(evaluation.get("outcome")),
        result_json=json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        data_source=DataCategory.FIXING_OFFICIAL.value,
        proposed_by=actor_user_id,
        error_message=json.dumps(failures, ensure_ascii=False, sort_keys=True),
    )
    session.add(proposal)
    session.flush()
    _ensure_alert(
        session,
        deal,
        "auto_lifecycle_exception",
        f"Résolution automatique bloquée pour {deal.reference}; contrôle requis.",
        f"auto-lifecycle-review:{proposal.dedup_key}",
    )
    record_audit_event(
        session,
        action="RESOLUTION_AUTO_REVIEW_REQUIRED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="REJECTED",
        after=_proposal_row(proposal),
        reason="Le replay automatique ne satisfait pas tous les contrôles.",
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={"failures": failures, "policy": deal.fixing_policy},
    )
    return proposal


def _auto_apply_lifecycle(
    deal: Deal,
    evaluation: dict | None,
    session: Session,
    actor_user_id: int | None,
) -> LifecycleProposal | None:
    if not evaluation or evaluation.get("outcome") == "en_cours":
        return None
    outcome = str(evaluation.get("outcome"))
    if outcome not in {"callé", "ki", "final"}:
        return _auto_review_proposal(
            deal, evaluation,
            [_workflow_failure(
                "AUTO_OUTCOME_UNSUPPORTED", "evaluation.outcome",
                "Le moteur automatique a produit un résultat terminal non supporté.",
                expected="callé, ki ou final",
                action="Contrôlez le script et la proposition lifecycle.",
                received=outcome,
            )],
            session, actor_user_id,
        )
    events = _get_events(deal.id, session)
    trigger = next(
        (event for event in events if event.id == evaluation.get("event_id")), None)
    required_events = (
        [event for event in events if event.t_years <= trigger.t_years + 1e-6]
        if trigger else []
    )
    failures: list[dict] = []
    if not trigger or not required_events:
        failures.append(_workflow_failure(
            "LIFECYCLE_TRIGGER_EVENT_MISSING", "evaluation.event_id",
            "Le résultat Yahoo ne référence pas une constatation contractuelle.",
            expected="Un identifiant d'événement du deal.",
            action="Rejouez le monitoring depuis le calendrier contractuel gelé.",
            received=evaluation.get("event_id"),
        ))
    for event in required_events:
        if (event.fixing_status != FixingStatus.VALIDATED.value or
                event.data_category != DataCategory.FIXING_OFFICIAL.value):
            failures.append(_workflow_failure(
                "AUTO_FIXING_NOT_OFFICIAL", f"event.{event.id}.fixing_status",
                "Une constatation requise n'a pas passé les contrôles Yahoo.",
                expected=FixingStatus.VALIDATED.value,
                action="Traitez l'exception affichée sur cette constatation.",
                received=event.fixing_status,
            ))
    official_result = None
    if not failures:
        official_result, replay_failures = replay_official_fixings(
            deal, required_events)
        failures.extend(replay_failures)
    if official_result and official_result.get("outcome") != outcome:
        failures.append(_workflow_failure(
            "AUTO_REPLAY_OUTCOME_MISMATCH", "evaluation.outcome",
            "Le replay des fixings Yahoo diverge du monitoring historique.",
            expected=official_result.get("outcome"),
            action="Contrôlez le produit et les fixings avant toute application.",
            received=outcome,
        ))
    if official_result:
        expected_payout = official_result.get("realized_payout")
        monitored_payout = evaluation.get("realized_payout")
        if expected_payout is not None and monitored_payout is not None:
            difference = abs(float(expected_payout) - float(monitored_payout))
            tolerance, monetary_tolerance = _payout_reconciliation_tolerance(deal)
            if difference > tolerance:
                failures.append(_workflow_failure(
                    "AUTO_REPLAY_PAYOUT_MISMATCH", "evaluation.realized_payout",
                    "Le payout Yahoo diverge du replay officiel au-delà de la tolérance monétaire.",
                    expected=f"Écart ≤ {tolerance:.12g} ({monetary_tolerance:.6g} {deal.devise}).",
                    action="Contrôlez le script et les fixings avant application.",
                    received={
                        "monitoring": monitored_payout,
                        "official": expected_payout,
                        "difference": difference,
                    },
                ))
    if failures:
        return _auto_review_proposal(
            deal, evaluation, failures, session, actor_user_id)

    input_hash = official_input_hash(deal, required_events)
    dedup_key = (
        f"auto-lifecycle:{deal.id}:{trigger.id}:{outcome}:{input_hash[:16]}"
    )
    existing = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    now = datetime.utcnow()
    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=trigger.id,
        dedup_key=dedup_key,
        status=LifecycleStatus.APPLIED.value,
        proposed_outcome=outcome,
        result_json=json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        data_source=DataCategory.FIXING_OFFICIAL.value,
        official_result_json=json.dumps(
            official_result, ensure_ascii=False, sort_keys=True),
        official_input_hash=input_hash,
        official_replayed_at=now,
        comparison_status="MATCH",
        validated_at=now,
        validation_reason="Contrôles automatiques AUTO_YAHOO passés.",
        applied_at=now,
        correlation_id=f"auto-yahoo:{deal.id}:{trigger.id}:{input_hash[:16]}",
        updated_at=now,
    )
    session.add(proposal)
    session.flush()
    before_deal = _deal_row(deal)
    trigger.status = outcome
    deal.status = "callé" if outcome == "callé" else "échu"
    deal.realized_payout = official_result.get("realized_payout")
    deal.resolution_outcome = outcome
    deal.updated_at = now
    session.add(deal)
    if outcome == "callé":
        for event in events:
            if event.t_years > trigger.t_years + 1e-6:
                event.status = "annulé"
                session.add(event)
    for event in required_events:
        event.fixing_status = FixingStatus.APPLIED.value
        event.applied_at = now
        session.add(event)
        version = (
            session.get(OfficialFixingVersion, event.current_fixing_version_id)
            if event.current_fixing_version_id else None
        )
        if version:
            version.status = FixingStatus.APPLIED.value
            version.applied_at = now
            session.add(version)
        record_audit_event(
            session,
            action="FIXING_AUTO_APPLIED",
            object_type="DEAL_EVENT",
            object_id=event.id,
            actor_user_id=actor_user_id,
            actor_type="USER" if actor_user_id else "PROCESS",
            result="SUCCESS",
            after=_event_row(event),
            reason="Fixing Yahoo consommé par la résolution automatique.",
            data_source=DataCategory.FIXING_OFFICIAL,
            metadata={"proposal_id": proposal.id, "policy": deal.fixing_policy},
        )
    for stale in session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == deal.id,
        LifecycleProposal.id != proposal.id,
        LifecycleProposal.status.in_([
            LifecycleStatus.PROPOSED.value,
            LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        ]),
    )).all():
        stale.status = LifecycleStatus.STALE.value
        stale.error_message = "Remplacée par la résolution automatique AUTO_YAHOO."
        stale.updated_at = now
        session.add(stale)
    # A former reconciliation exception is no longer actionable once the same
    # deal has been resolved successfully from authoritative fixings.
    for alert in session.exec(select(Alert).where(
        Alert.deal_id == deal.id,
        Alert.kind == "auto_lifecycle_exception",
        Alert.read == False,  # noqa: E712
    )).all():
        alert.read = True
        session.add(alert)
    record_audit_event(
        session,
        action="RESOLUTION_AUTO_APPLIED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="SUCCESS",
        before={"deal": before_deal},
        after={"deal": _deal_row(deal), "proposal": _proposal_row(proposal)},
        reason="Résolution appliquée automatiquement depuis les fixings Yahoo officiels.",
        data_source=DataCategory.FIXING_OFFICIAL,
        correlation_id=proposal.correlation_id,
        metadata={"policy": deal.fixing_policy, "official_result": official_result},
    )
    _ensure_alert(
        session,
        deal,
        "resolution_auto_applied",
        f"Résolution {outcome!r} appliquée automatiquement pour {deal.reference}.",
        f"resolution-auto:{proposal.dedup_key}",
    )
    return proposal


def _refresh_auto_yahoo_deal_core(
    deal: Deal,
    session: Session,
    actor_user_id: int | None,
    underlyings: list[dict],
    tickers: list[str],
) -> dict:
    if deal.status != "actif":
        return {
            "updated": 0,
            "officialized": 0,
            "exceptions": [],
            "message": "Deal déjà résolu : aucune constatation à actualiser.",
            "evaluation": None,
            "proposal": None,
        }
    today = date.today().isoformat()
    events = _get_events(deal.id, session)
    past_events = [event for event in events if event.event_date <= today]
    if not past_events:
        return {
            "updated": 0,
            "officialized": 0,
            "exceptions": [],
            "message": "Aucun événement contractuel atteint.",
            "evaluation": None,
            "proposal": None,
        }
    fetch_start = (
        min(date.fromisoformat(event.event_date) for event in past_events)
        - timedelta(days=7)
    ).isoformat()
    reference_data = load_yahoo_reference_closes(tickers, fetch_start, today)
    if "error" in reference_data:
        raise ValueError(reference_data["error"])
    officialized = 0
    exceptions: list[dict] = []
    for event in past_events:
        changed, exception = _auto_validate_yahoo_event(
            deal, event, underlyings, reference_data, session, actor_user_id)
        officialized += int(changed)
        if exception:
            exceptions.append(exception)
    dates, prices = _reference_history_arrays(reference_data, tickers)
    if not dates:
        raise ValueError("Les clôtures Yahoo ne permettent pas de construire un historique commun")

    # Lifecycle truth comes from the longest contiguous prefix of validated
    # contractual fixings.  The dense Yahoo history remains useful monitoring
    # data and a governed fallback for scripts whose path dependence cannot be
    # established from event fixings alone, but it must not decide an otherwise
    # replayable terminal outcome on dates that differ from the booked calendar.
    official_prefix: list[DealEvent] = []
    for event in sorted(past_events, key=lambda row: (row.t_years, row.event_index)):
        if (event.fixing_status != FixingStatus.VALIDATED.value or
                event.data_category != DataCategory.FIXING_OFFICIAL.value):
            break
        official_prefix.append(event)
    official_evaluation = None
    replay_failures: list[dict] = []
    if official_prefix:
        official_evaluation, replay_failures = replay_official_fixings(
            deal, official_prefix)
    evaluation = official_evaluation
    if evaluation is None:
        evaluation = _evaluate_lifecycle(deal, events, dates, prices, tickers)
    proposal = _auto_apply_lifecycle(deal, evaluation, session, actor_user_id)
    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    if exceptions:
        first_failure = exceptions[0]["failures"][0]
        message = (
            f"⚠ {len(exceptions)} constatation(s) non appliquée(s) : "
            f"{first_failure.get('message', first_failure.get('code'))} "
            f"{first_failure.get('action', '')}"
        ).strip()
    elif proposal and proposal.status == LifecycleStatus.APPLIED.value:
        message = (
            f"✓ {officialized} constatation(s) Yahoo officialisée(s) ; "
            f"résolution {proposal.proposed_outcome} appliquée automatiquement."
        )
    elif proposal and proposal.status == LifecycleStatus.MANUAL_REVIEW_REQUIRED.value:
        message = (
            f"⚠ {officialized} constatation(s) Yahoo officialisée(s), "
            "mais la résolution requiert un contrôle manuel."
        )
    else:
        message = (
            f"✓ {officialized} constatation(s) Yahoo officialisée(s) ; "
            "le produit reste en vie."
        )
    return {
        "updated": officialized,
        "officialized": officialized,
        "exceptions": exceptions,
        "message": message,
        "evaluation": evaluation,
        "proposal": _proposal_row(proposal) if proposal else None,
        "official_replay_failures": replay_failures,
        "policy": FixingPolicy.AUTO_YAHOO.value,
    }


def _proposal_required_events(
    deal: Deal,
    proposal: LifecycleProposal,
    session: Session,
) -> list[DealEvent]:
    events = _get_events(deal.id, session)
    trigger = next((event for event in events if event.id == proposal.event_id), None)
    if not trigger:
        return []
    return [event for event in events if event.t_years <= trigger.t_years + 1e-6]


def _proposal_fixing_failures(
    deal: Deal,
    proposal: LifecycleProposal,
    session: Session,
    checker_user_id: int | None = None,
) -> tuple[list[DealEvent], list[dict]]:
    required_events = _proposal_required_events(deal, proposal, session)
    failures: list[dict] = []
    if not required_events or not proposal.event_id:
        failures.append(_workflow_failure(
            "LIFECYCLE_TRIGGER_EVENT_MISSING",
            "proposal.event_id",
            "La proposition ne référence aucun événement contractuel exact.",
            expected="L’identifiant de l’événement où le replay officiel s’arrête.",
            action="Recalculez la proposition depuis le calendrier contractuel gelé.",
            received=proposal.event_id,
        ))
        return required_events, failures
    for event in required_events:
        event_failures = [
            _workflow_failure(
                spot_failure["code"],
                f"spots.{spot_failure.get('underlying', '')}".rstrip("."),
                "Le fixing officiel est incomplet ou contient une valeur invalide.",
                expected="Une valeur numérique strictement positive par sous-jacent contractuel.",
                action="Soumettez une nouvelle version complète puis faites-la valider.",
                received=(
                    spot_failure.get("value")
                    if "value" in spot_failure
                    else spot_failure.get("underlyings")),
            )
            for spot_failure in _spot_failures(
                deal, json.loads(event.spots_json or "{}"))
        ]
        if event.fixing_status != FixingStatus.VALIDATED:
            event_failures.append(_workflow_failure(
                "FIXING_NOT_VALIDATED",
                "fixing_status",
                "Le fixing requis n’a pas été validé par un Checker indépendant.",
                expected=FixingStatus.VALIDATED.value,
                action="Faites traiter la version candidate dans la file Checker.",
                received=event.fixing_status,
            ))
        if event.data_category != DataCategory.FIXING_OFFICIAL:
            event_failures.append(_workflow_failure(
                "FIXING_NOT_OFFICIAL",
                "data_category",
                "La donnée requise est indicative ou candidate, pas officielle.",
                expected=DataCategory.FIXING_OFFICIAL.value,
                action="Soumettez une preuve officielle puis faites valider le fixing.",
                received=event.data_category,
            ))
        version = (
            session.get(OfficialFixingVersion, event.current_fixing_version_id)
            if event.current_fixing_version_id else None
        )
        if not version:
            event_failures.append(_workflow_failure(
                "FIXING_PROVENANCE_MISSING", "current_fixing_version_id",
                "Le fixing ne possède pas de preuve officielle versionnée.",
                expected="Une version avec pièce archivée et hash vérifié.",
                action="Demandez une soumission Ops Maker puis une validation Checker.",
            ))
        elif version.status != FixingStatus.VALIDATED:
            event_failures.append(_workflow_failure(
                "FIXING_VERSION_NOT_VALIDATED", "fixing_version.status",
                "La version de preuve n’est pas validée.",
                expected=FixingStatus.VALIDATED.value,
                action="Faites valider la version courante par un Ops Checker indépendant.",
                received=version.status,
            ))
        elif checker_user_id is not None and version.entered_by == checker_user_id:
            event_failures.append(_workflow_failure(
                "FOUR_EYES_VIOLATION", "validated_by",
                "Le Checker lifecycle a saisi un fixing consommé par la résolution.",
                expected="Un Checker distinct de tous les Makers des fixings consommés.",
                action="Transmettez la résolution à un autre Ops Checker.",
                received=checker_user_id,
            ))
        if event_failures:
            failures.append({
                "event_id": event.id,
                "event_date": event.event_date,
                "failures": event_failures,
            })
    return required_events, failures


def _payout_reconciliation_tolerance(deal: Deal) -> tuple[float, float]:
    """Return (normalised payout tolerance, monetary tolerance).

    PayScript cash flows are expressed as a fraction of notional.  The
    accepted difference is therefore half of the smallest currency unit,
    converted back to a fraction of the booked notional.
    """
    decimals = 0 if deal.devise in {"JPY", "KRW", "CLP", "VND"} else (
        3 if deal.devise in {"BHD", "KWD", "OMR", "JOD", "TND"} else 2)
    monetary_tolerance = 0.5 * (10 ** -decimals)
    if not deal.nominal or deal.nominal <= 0:
        return 0.0, monetary_tolerance
    return monetary_tolerance / float(deal.nominal), monetary_tolerance


def _owned_proposal(
    deal_id: int,
    proposal_id: int,
    current: User,
    session: Session,
) -> tuple[Deal, LifecycleProposal]:
    deal = _ops_deal(
        deal_id, current, session,
        allowed_roles={"checker"},
        action="LIFECYCLE_CHECKER_ROLE_REJECTED",
    )
    proposal = session.get(LifecycleProposal, proposal_id)
    if not proposal or proposal.deal_id != deal_id:
        raise HTTPException(404, "Proposition lifecycle introuvable")
    if deal.user_id == current.id:
        _reject_workflow_action(
            session,
            action="LIFECYCLE_FOUR_EYES_REJECTED",
            object_type="LIFECYCLE_PROPOSAL",
            object_id=proposal.id,
            current=current,
            message="Le propriétaire économique du deal ne peut pas autoriser sa résolution.",
            failures=[_workflow_failure(
                "DEAL_OWNER_CANNOT_VALIDATE_LIFECYCLE",
                "validated_by",
                "Le Deal Owner et le Checker lifecycle doivent être distincts.",
                expected="Un Ops Checker indépendant.",
                action="Transmettez la proposition à un autre Checker de l’entité.",
                received=current.id,
            )],
            status_code=409,
        )
    return deal, proposal


def _reject_lifecycle(
    session: Session,
    proposal: LifecycleProposal,
    current: User,
    action: str,
    reason: str,
    failures: list[dict],
    status_code: int = 409,
) -> None:
    # A rejection may occur after an authorization CAS and after audit rows
    # have been staged in the same transaction.  Persisting the rejection
    # must never commit those intermediate business mutations.  Roll back to
    # the last durable state first, then write the rejection in its own
    # fail-closed transaction.
    session.rollback()
    commit_rejection(
        session,
        action=action,
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=current.id,
        before=_proposal_row(proposal),
        reason=reason,
        data_source=proposal.data_source,
        metadata={"failures": failures},
    )
    raise HTTPException(status_code, {
        "code": action,
        "message": reason,
        "failures": failures,
    })


@router.post("/{deal_id}/lifecycle-proposals/{proposal_id}/validate")
def validate_lifecycle_proposal(
    deal_id: int,
    proposal_id: int,
    body: LifecycleValidationRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal, proposal = _owned_proposal(deal_id, proposal_id, current, session)
    failures: list[dict] = []
    if deal.status != "actif":
        failures.append(_workflow_failure(
            "DEAL_NOT_ACTIVE", "deal.status",
            "Le deal n’est plus actif et ne peut pas recevoir une nouvelle résolution.",
            expected="actif",
            action="Actualisez le deal et consultez la résolution déjà appliquée.",
            received=deal.status,
        ))
    if proposal.status != LifecycleStatus.PROPOSED:
        failures.append(_workflow_failure(
            "PROPOSAL_STATUS_INVALID", "proposal.status",
            "La proposition n’est plus en attente d’autorisation.",
            expected=LifecycleStatus.PROPOSED.value,
            action="Actualisez la proposition et consultez sa dernière décision.",
            received=proposal.status,
        ))
    if body.confirmed_outcome != proposal.proposed_outcome:
        failures.append(_workflow_failure(
            "OUTCOME_CONFIRMATION_REQUIRED", "confirmed_outcome",
            "Le résultat saisi par le Checker ne correspond pas à la proposition.",
            expected=proposal.proposed_outcome,
            action="Contrôlez le replay puis saisissez exactement le résultat confirmé.",
            received=body.confirmed_outcome,
        ))
    conflict = session.exec(
        select(LifecycleProposal).where(
            LifecycleProposal.deal_id == deal_id,
            LifecycleProposal.id != proposal_id,
            LifecycleProposal.status.in_([
                LifecycleStatus.VALIDATED.value, LifecycleStatus.APPLIED.value]),
        )
    ).first()
    if conflict:
        failures.append(_workflow_failure(
            "CONFLICTING_RESOLUTION", "proposal.status",
            "Une autre proposition a déjà été autorisée ou appliquée sur ce deal.",
            expected="Aucune autre résolution VALIDATED ou APPLIED.",
            action="Actualisez le deal et contrôlez la proposition déjà retenue.",
            received={"proposal_id": conflict.id, "status": conflict.status},
        ))
    required_events, fixing_failures = _proposal_fixing_failures(
        deal, proposal, session, checker_user_id=current.id)
    failures.extend(fixing_failures)
    official_result = None
    current_official_hash = None
    comparison_status = None
    if not fixing_failures:
        official_result, replay_failures = replay_official_fixings(deal, required_events)
        failures.extend(replay_failures)
        if official_result:
            current_official_hash = official_input_hash(deal, required_events)
            if official_result.get("outcome") != proposal.proposed_outcome:
                failures.append(_workflow_failure(
                    "OFFICIAL_INDICATIVE_OUTCOME_MISMATCH",
                    "proposal.proposed_outcome",
                    "Le résultat officiel diverge de la proposition indicative.",
                    expected=official_result.get("outcome"),
                    action="Rejetez la proposition indicative et générez une proposition réconciliée depuis le replay officiel.",
                    received=proposal.proposed_outcome,
                ))
            else:
                indicative_result = json.loads(proposal.result_json or "{}")
                indicative_payout = indicative_result.get("realized_payout")
                official_payout = official_result.get("realized_payout")
                if (indicative_payout is not None and official_payout is not None and
                        abs(float(indicative_payout) - float(official_payout)) > 0):
                    payout_difference = abs(
                        float(indicative_payout) - float(official_payout))
                    normalized_tolerance, monetary_tolerance = \
                        _payout_reconciliation_tolerance(deal)
                    if payout_difference > normalized_tolerance:
                        failures.append(_workflow_failure(
                            "OFFICIAL_INDICATIVE_PAYOUT_MISMATCH",
                            "proposal.result.realized_payout",
                            "Le payout indicatif diverge du payout officiel au-delà de la tolérance monétaire.",
                            expected=(
                                f"Écart ≤ {normalized_tolerance:.12g} du nominal "
                                f"(soit {monetary_tolerance:.6g} {deal.devise})."),
                            action="Rejetez la proposition indicative et générez une proposition réconciliée depuis le replay officiel.",
                            received={
                                "indicative": indicative_payout,
                                "official": official_payout,
                                "difference": payout_difference,
                            },
                        ))
                        comparison_status = "PAYOUT_MISMATCH_BLOCKING"
                    else:
                        comparison_status = "MATCH_WITHIN_MONETARY_TOLERANCE"
                else:
                    comparison_status = "MATCH"
    if failures:
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_VALIDATION_REJECTED",
            "La résolution proposée ne peut pas être validée.", failures, 422)

    before = _proposal_row(proposal)
    authorized_at = datetime.utcnow()
    authorization_cas = session.exec(
        update(LifecycleProposal)
        .where(
            LifecycleProposal.id == proposal.id,
            LifecycleProposal.status == LifecycleStatus.PROPOSED.value,
        )
        .values(
            status=LifecycleStatus.VALIDATED.value,
            validated_by=current.id,
            validated_at=authorized_at,
            validation_reason=body.reason,
            official_result_json=json.dumps(
                official_result, ensure_ascii=False, sort_keys=True),
            official_input_hash=current_official_hash,
            official_replayed_at=authorized_at,
            comparison_status=comparison_status,
            updated_at=authorized_at,
        )
        .execution_options(synchronize_session=False)
    )
    if authorization_cas.rowcount != 1:
        session.rollback()
        proposal = session.get(LifecycleProposal, proposal_id)
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_VALIDATION_REJECTED",
            "Autorisation non enregistrée — la proposition a déjà été traitée par une autre session.",
            [_workflow_failure(
                "PROPOSAL_ALREADY_DECIDED",
                "proposal.status",
                "La transition attendue PROPOSED → VALIDATED n’est plus disponible.",
                expected=LifecycleStatus.PROPOSED.value,
                action="Actualisez le deal et consultez la décision déjà enregistrée.",
                received=proposal.status if proposal else "MISSING",
            )],
        )
    session.expire(proposal)
    proposal = session.get(LifecycleProposal, proposal_id)
    record_audit_event(
        session,
        action="RESOLUTION_VALIDATED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before,
        after=_proposal_row(proposal),
        reason=body.reason,
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "comparison_status": comparison_status,
            "official_result": official_result,
            "official_fixings": [
                {"event_id": event.id, "event_date": event.event_date,
                 "spots": json.loads(event.spots_json or "{}")}
                for event in required_events
            ],
        },
    )
    # The Checker authorizes an economic result; the system applies that exact
    # frozen result in the same database transaction.  No separate Applier
    # button or intermediate actionable state is exposed.
    return apply_lifecycle_proposal(
        deal_id, proposal_id,
        LifecycleValidationRequest(reason=body.reason),
        current, session,
    )


@router.post("/{deal_id}/lifecycle-proposals/{proposal_id}/apply")
def apply_lifecycle_proposal(
    deal_id: int,
    proposal_id: int,
    body: LifecycleValidationRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal, proposal = _owned_proposal(deal_id, proposal_id, current, session)
    failures: list[dict] = []
    if deal.status != "actif":
        failures.append(_workflow_failure(
            "DEAL_NOT_ACTIVE", "deal.status",
            "Le deal n’est plus actif ; aucune nouvelle application économique n’est possible.",
            expected="actif",
            action="Actualisez le deal et consultez la résolution déjà appliquée.",
            received=deal.status,
        ))
    if proposal.status != LifecycleStatus.VALIDATED:
        failures.append(_workflow_failure(
            "PROPOSAL_STATUS_INVALID", "proposal.status",
            "La proposition n’est pas dans l’état autorisé attendu.",
            expected=LifecycleStatus.VALIDATED.value,
            action="Actualisez la proposition ; une autorisation Checker est requise avant application.",
            received=proposal.status,
        ))
    required_events, fixing_failures = _proposal_fixing_failures(
        deal, proposal, session, checker_user_id=current.id)
    failures.extend(fixing_failures)
    if not proposal.official_result_json or not proposal.official_input_hash:
        failures.append(_workflow_failure(
            "OFFICIAL_REPLAY_MISSING", "official_result_json",
            "Aucun replay officiel gelé n’est attaché à l’autorisation.",
            expected="Un résultat officiel et son hash d’inputs.",
            action="Reprenez l’autorisation Checker depuis une proposition PROPOSED.",
        ))
    elif not fixing_failures:
        current_official_hash = official_input_hash(deal, required_events)
        if current_official_hash != proposal.official_input_hash:
            failures.append(_workflow_failure(
                "OFFICIAL_REPLAY_STALE", "official_input_hash",
                "Les inputs officiels ont changé depuis l’autorisation.",
                expected="Le hash d’inputs gelé lors de l’autorisation.",
                action="Marquez cette proposition STALE et produisez un nouveau replay officiel.",
                received="Un hash courant différent du hash autorisé.",
            ))
    if failures:
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_APPLICATION_REJECTED",
            "La résolution validée ne peut pas être appliquée.", failures)

    before_deal = _deal_row(deal)
    before_proposal = _proposal_row(proposal)
    applied_at = datetime.utcnow()
    cas = session.exec(
        update(LifecycleProposal)
        .where(
            LifecycleProposal.id == proposal.id,
            LifecycleProposal.status == LifecycleStatus.VALIDATED.value,
        )
        .values(
            status=LifecycleStatus.APPLIED.value,
            applied_by=current.id,
            applied_at=applied_at,
            updated_at=applied_at,
        )
        .execution_options(synchronize_session=False)
    )
    if cas.rowcount != 1:
        session.rollback()
        proposal = session.get(LifecycleProposal, proposal_id)
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_APPLICATION_REJECTED",
            "La résolution a déjà été appliquée ou modifiée par une autre transaction.",
            [_workflow_failure(
                "CONCURRENT_OR_DUPLICATE_APPLICATION", "proposal.status",
                "La transition VALIDATED → APPLIED n’est plus disponible.",
                expected=LifecycleStatus.VALIDATED.value,
                action="Actualisez le deal et consultez l’application déjà enregistrée.",
                received=proposal.status if proposal else "MISSING",
            )],
        )

    result = json.loads(proposal.official_result_json or "{}")
    outcome = result.get("outcome")
    if outcome not in {"callé", "ki", "final"}:
        session.rollback()
        proposal = session.get(LifecycleProposal, proposal_id)
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_APPLICATION_REJECTED",
            "Le résultat autorisé n’est pas terminal.",
            [_workflow_failure(
                "UNSUPPORTED_OUTCOME", "official_result.outcome",
                "Le replay officiel ne produit pas un événement économique terminal supporté.",
                expected="callé, ki ou final",
                action="Corrigez le script ou attendez un événement officiel terminal.",
                received=outcome,
            )], 422)
    trigger = next(event for event in required_events if event.id == proposal.event_id)
    all_events = _get_events(deal.id, session)
    trigger.status = outcome
    target_deal_status = "callé" if outcome == "callé" else "échu"
    deal_cas = session.exec(
        update(Deal)
        .where(Deal.id == deal.id, Deal.status == "actif")
        .values(
            status=target_deal_status,
            realized_payout=result.get("realized_payout"),
            resolution_outcome=outcome,
            updated_at=applied_at,
        )
        .execution_options(synchronize_session=False)
    )
    if deal_cas.rowcount != 1:
        session.rollback()
        proposal = session.get(LifecycleProposal, proposal_id)
        _reject_lifecycle(
            session, proposal, current, "RESOLUTION_APPLICATION_REJECTED",
            "Application non enregistrée — une résolution concurrente a déjà consommé ce deal.",
            [_workflow_failure(
                "DEAL_RESOLUTION_ALREADY_APPLIED", "deal.status",
                "Le verrou économique actif du deal n’est plus disponible.",
                expected="actif",
                action="Actualisez le deal et consultez la résolution gagnante.",
            )],
        )
    session.expire(deal)
    deal = session.get(Deal, deal_id)
    if outcome == "callé":
        for event in all_events:
            if event.t_years > trigger.t_years + 1e-6:
                event.status = "annulé"
                session.add(event)
    for event in required_events:
        before_event = _event_row(event)
        event.fixing_status = FixingStatus.APPLIED
        event.applied_at = applied_at
        session.add(event)
        fixing_version = (
            session.get(OfficialFixingVersion, event.current_fixing_version_id)
            if event.current_fixing_version_id else None
        )
        if fixing_version:
            fixing_version.status = FixingStatus.APPLIED
            fixing_version.applied_at = applied_at
            session.add(fixing_version)
        record_audit_event(
            session,
            action="FIXING_APPLIED",
            object_type="DEAL_EVENT",
            object_id=event.id,
            actor_user_id=current.id,
            result="SUCCESS",
            before=before_event,
            after=_event_row(event),
            reason=body.reason,
            data_source=DataCategory.FIXING_OFFICIAL,
            metadata={"proposal_id": proposal_id},
        )

    session.expire(proposal)
    proposal = session.get(LifecycleProposal, proposal_id)
    record_audit_event(
        session,
        action="RESOLUTION_APPLIED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=current.id,
        result="SUCCESS",
        before=before_proposal,
        after={"proposal": _proposal_row(proposal), "deal": _deal_row(deal)},
        reason=body.reason,
        data_source=DataCategory.FIXING_OFFICIAL,
    )
    session.commit()
    session.refresh(deal)
    session.refresh(proposal)
    return {"deal": _deal_row(deal, _get_events(deal.id, session)),
            "proposal": _proposal_row(proposal)}


@router.get("/{deal_id}/reprice")
def reprice_inputs(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Return normalized inputs for re-pricing the deal at current market conditions."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
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
    # Meme origine que les temps d observation : la date de strike. Compter le
    # temps ecoule depuis la value date decalerait tout le residuel.
    _elapsed_origin = (date.fromisoformat(deal.strike_date) if deal.strike_date else value_d)
    T_elapsed = max(0.0, (today - _elapsed_origin).days / 365.25)

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

def _regenerate_dividend_curve(underlying: dict, maturity: float) -> None:
    """Rebuild a full-tenor curve after a first-year q refresh.

    Reinvestment deliberately refreshes Yahoo's q assumption. If the booked
    structure used a declining curve, changing only the scalar q would be a
    silent no-op because the path engine consumes the frozen nodes. Keep the
    booked decay convention and rebuild every explanatory/used node instead.
    """
    if not underlying.get("dividend_curve"):
        return
    q1 = float(underlying.get("q", 0.0))
    decay = float(underlying.get("dividend_decay", 0.0))
    n_years = max(1, math.ceil(float(maturity)))
    underlying["dividend_curve"] = [
        [float(year), q1 * (1.0 - decay) ** (year - 1)]
        for year in range(1, n_years + 1)
    ]


@router.post("/{deal_id}/reinvest/roll")
def reinvest_roll_endpoint(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    from ..core.payscript.engine import run_mc
    from ..services.market_data import load_hist_vol

    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
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
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=date.today(),
                                    currency=(deal.devise or "").strip().upper() or None)
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
                _regenerate_dividend_curve(u, deal.T)
        if n_u > 1 and all(tk in vol_data["corr"] for tk in tickers):
            corr = [[vol_data["corr"][t1].get(t2, 0.0) for t2 in tickers] for t1 in tickers]

    current_spots: dict = {}
    px_data = load_hist_prices(tickers, date.today().isoformat(), date.today().isoformat())
    if "error" not in px_data:
        prices = px_data.get("prices", {})
        for tk in tickers:
            if tk in prices and prices[tk]:
                current_spots[tk] = round(float(prices[tk][-1]), 4)

    r_frac = snapshot_rate(market)
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
    _regenerate_dividend_curve(ul, T)

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
        compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=date.today(),
                                    currency=(deal.devise or "").strip().upper() or None)
    except ValueError as e:
        raise HTTPException(422, f"Script non exploitable : {e}")

    base_ul = _engine_underlyings(market, underlyings_json)[0]
    r_frac = snapshot_rate(market)
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
    if not deal or not _can_access_deal(deal, current, session):
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
    if not deal or not _can_access_deal(deal, current, session):
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
    if not deal or not _can_access_deal(deal, current, session):
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


class DealGreeksRequest(MtmRequest):
    """Body of POST /{deal_id}/greeks — same market-assumption knobs as the
    MtM (recalibrate/overrides/r), plus which sensitivities to compute. corr
    (cross-gamma) is supported by compute_greeks but left out of the default
    selection — not something a future portfolio aggregation can simply sum
    across deals with different baskets."""
    selected: List[str] = ["delta", "gamma", "vega", "theta", "rho"]


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
    # Meme origine que les temps d observation : la date de strike. Compter le
    # temps ecoule depuis la value date decalerait tout le residuel.
    _elapsed_origin = (date.fromisoformat(deal.strike_date) if deal.strike_date else value_d)
    T_elapsed = max(0.0, (today - _elapsed_origin).days / 365.25)
    T_remaining = max(1 / 52, (maturity - today).days / 365.25)
    residual_payment_t = (
        (date.fromisoformat(deal.payment_date) - today).days / 365.25
        if deal.payment_date else None)

    # Le rejeu du passé et la construction du résiduel vivent dans le cœur
    # (core/inlife_valuation) : le Pricer doit pouvoir les appeler sans qu'un
    # deal existe. Ici on ne fait que traduire un deal en paramètres.
    strike_event = next((e for e in _get_events(deal_id, session) if e.t_years == 0.0), None)
    produit = InLifeProduct(
        script_snapshot=deal.script_snapshot,
        underlyings=json.loads(deal.underlyings_json),
        strike_levels=json.loads(strike_event.spots_json) if strike_event else {},
        strike_date=(date.fromisoformat(deal.strike_date) if deal.strike_date else value_d),
        value_date=value_d,
        tenor=deal.T,
        currency=(deal.devise or "").strip().upper(),
        payment_date=(date.fromisoformat(deal.payment_date) if deal.payment_date else None),
        market=json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {},
    )
    # Historique réalisé depuis le strike (même fenêtre J-7 que le refresh du
    # cycle de vie : un strike un week-end ou un férié a besoin de la clôture
    # qui précède). Le chargement reste ici, le cœur ne fait pas d'I/O.
    tickers = [u["ticker"] for u in produit.underlyings if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")
    fetch_start = (produit.strike_date - timedelta(days=7)).isoformat()
    px_data = load_hist_prices(tickers, fetch_start, today.isoformat())
    if "error" in px_data:
        raise HTTPException(422, px_data["error"])
    try:
        residuel = build_residual(produit, px_data.get("prices", {}),
                                  px_data.get("dates", []), T_elapsed, today)
    except ValuationError as exc:
        raise HTTPException(422, str(exc))

    if residuel.early_recall:
        # The old wording pointed at "refresh the lifecycle", which stopped
        # being actionable when fixings became governed: a refresh only updates
        # INDICATIVE monitoring data and raises a proposal — resolving the deal
        # now requires an official fixing validated by an independent Checker.
        return {
            "resolved_pending": True,
            "message": "Le replay indicatif détecte un rappel anticipé : ce deal ne "
                       "devrait plus être actif. La résolution passe par un fixing "
                       "officiel validé — soumettez la version candidate puis faites-la "
                       "traiter dans la file Checker. Un refresh ne met à jour que les "
                       "données indicatives et ne résoudra pas le deal.",
            "T_actual": residuel.T_actual,
        }, None

    # Noms locaux conservés : toute la suite de la fonction les utilise tels
    # quels, ce qui garde le déplacement mécanique et vérifiable.
    market = produit.market
    underlyings_json = produit.underlyings
    compiled = residuel.compiled
    residual_script = residuel.residual_script
    state = residuel.state
    realized_cfs = residuel.realized_flows
    norm_spots = residuel.norm_spots
    engine_uls = residuel.engine_uls
    r_frac = residuel.r_frac
    prices = residuel.prices
    dates_list = residuel.dates_list
    user_params = residuel.user_params
    replay = residuel.replay
    start_idx = residuel.start_idx
    s0_map = residuel.s0_map
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
                # A flat manual override replaces the complete booked curve;
                # keeping the nodes would make the visible override a no-op.
                u["dividend_curve"] = []
        source += "+overrides"
    if body.r is not None:
        # A fresh flat rate with the stale booking curve would be incoherent —
        # the override replaces the whole discounting/drift term.
        r_frac = body.r / 100.0
        yc = []

    try:
        result = run_mc(
            residual_script, engine_uls, corr, r_frac, T_remaining,
            maturity_payment_t=residual_payment_t,
            N=max(1000, min(100000, n_paths)),
            model=model_used, seed=42,
            antithetic=bool(market.get("antithetic", True)),
            user_params=user_params, spot_mult=norm_spots, spot_base=norm_spots,
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
            # True only for a legacy snapshot carrying no rate at all: the
            # figure above is then our fallback, not this deal's own term.
            # A zero or negative booked rate is honoured and reads False.
            "r_is_default": snapshot_rate_is_default(market) and body.r is None,
            "flat_curve": not yc,
            "window_returns": n_returns,
            "sigma": {u["name"]: round(eu["sigma"] * 100.0, 2)
                      for u, eu in zip(underlyings_json, engine_uls)},
            "q": {u["name"]: round(eu["q"] * 100.0, 2)
                  for u, eu in zip(underlyings_json, engine_uls)},
            "dividend_curve": {
                u["name"]: [[round(t, 6), round(q * 100.0, 6)] for t, q in
                            (eu.get("dividend_curve") or [])]
                for u, eu in zip(underlyings_json, engine_uls)
            },
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
        "residual_payment_t": residual_payment_t,
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
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    payload, _ctx = _mtm_core(deal, session, n_paths, body)
    return payload


@router.post("/{deal_id}/greeks")
def deal_greeks(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[DealGreeksRequest] = None,
):
    """Bump-and-reprice Greeks on the residual MtM leg — reuses _mtm_core's
    ctx (residual script, effective underlyings, corr, rates) exactly as
    compute_greeks needs it, so the sensitivities are consistent with
    whatever MtM number the same market assumptions would produce. Last
    result is persisted on the deal (greeks_json/greeks_computed_at),
    overwritten at each call — see PLAN squishy-baking-sedgewick."""
    from ..core.payscript.engine import compute_greeks

    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")

    body = body or DealGreeksRequest()
    mtm_payload, ctx = _mtm_core(deal, session, n_paths, body)
    if ctx is None:
        return mtm_payload   # resolved_pending short-circuit — nothing to bump

    names = [u["name"] for u in ctx["underlyings_json"]]
    # Cross-gamma (correlation sensitivity) is meaningless for a single
    # underlying and left out of DealGreeksRequest's default selection (it
    # doesn't sum across deals with different baskets — see the class
    # docstring) — but for a worst-of/basket deal it's exactly the risk a
    # family-office user won't intuit on their own, so force it on here
    # rather than requiring an explicit opt-in every time.
    selected = list(body.selected)
    if len(names) >= 2 and "corr" not in selected:
        selected.append("corr")

    raw = compute_greeks(
        ctx["residual_script"], ctx["engine_uls"], ctx["corr"],
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=42, user_params=ctx["user_params"], selected=selected,
        sigma_r=ctx["sigma_r"], a_r=ctx["a_r"], yield_curve=ctx["yc"],
        barrier_monitoring=ctx["barrier_monitoring"],
        # A live deal's sensitivities are those of what it has BECOME — spot
        # where it stands today, knock-in already touched or not, coupons
        # already accrued. Repricing it as a brand new product, which is what
        # omitting this does, answers a question nobody asked.
        antithetic=ctx["antithetic"], state=_greeks_state(ctx),
    )

    per_underlying: dict[str, dict] = {}
    scalar: dict[str, float | None] = {}
    # Keyed by the underlying pair's own names ("AAPL / MSFT"), not the raw
    # corr_1_2 index form compute_greeks returns — readable directly in the
    # UI without the caller having to re-resolve indices against names.
    corr_pairs: dict[str, float] = {}
    # Not a sensitivity: the observation the theta window steps over, and the
    # cash it detaches. Kept out of `scalar`, which is summed across the book.
    theta_event = raw.pop("theta_event", None)
    # Not a sensitivity either: what fraction of the volatility the vega bump
    # actually reaches (see compute_greeks). Kept out of `scalar`, which is
    # summed across the book.
    vega_scope = raw.pop("vega_scope", None)
    for key, val in raw.items():
        m = re.match(r"^(delta|gamma|vega)_(\d+)$", key)
        if m:
            greek, idx = m.group(1), int(m.group(2)) - 1
            per_underlying.setdefault(names[idx], {})[greek] = val
            continue
        m = re.match(r"^corr_(\d+)_(\d+)$", key)
        if m:
            i1, i2 = int(m.group(1)) - 1, int(m.group(2)) - 1
            corr_pairs[f"{names[i1]} / {names[i2]}"] = val
        else:
            scalar[key] = val   # theta, rho

    payload = {
        "deal_id": deal_id,
        "reference": deal.reference,
        "computed_at": datetime.utcnow().isoformat(),
        "mtm_reference": mtm_payload["mtm"],
        "per_underlying": per_underlying,
        "scalar": scalar,
        "theta_event": theta_event,
        "vega_scope": vega_scope,
        "corr_pairs": corr_pairs,
        "market_used": mtm_payload["market_used"],
    }

    deal.greeks_json = json.dumps(payload)
    deal.greeks_computed_at = datetime.utcnow()
    session.add(deal)
    session.commit()

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
        maturity_payment_t=cal.get("residual_payment_t"),
        N=common["N"], model=model, seed=42, antithetic=common["antithetic"],
        user_params=common["user_params"], spot_mult=spot["norm_spots"],
        spot_base=spot["norm_spots"],
        yield_curve=common["yc"], sigma_r=common["sigma_r"], a_r=common["a_r"],
        barrier_monitoring=common["bm"],
        wof_min_init=st["wof_min"], bof_max_init=st["bof_max"],
        index_offset=cal["index_offset"], memo_init=st["memo"],
        accum_init=st["accum"],
        s_min_init=st["s_min"], s_max_init=st["s_max"], s_prev_init=st["s_prev"],
        wof0_init=min(spot["norm_spots"]),
        realvol_state_init=st["realvol_state"], fix_state_init=st["fix_state"],
    )["price"]


def _greeks_state(ctx: dict) -> dict:
    """The lifecycle bundle compute_greeks needs, assembled from _mtm_core's ctx.

    `spot_base` is what "not bumped" means for this deal — today's spot in % of
    strike. Every bump is taken relative to it, so a deal 30% above its strike
    is shocked by 1% of where it actually trades, not of its issue level."""
    st = ctx["state"]
    return {
        "spot_base": ctx["norm_spots"],
        "wof_min": st["wof_min"], "bof_max": st["bof_max"],
        "index": st["index"], "memo": st["memo"], "accum": st["accum"],
        "s_min": st["s_min"], "s_max": st["s_max"], "s_prev": st["s_prev"],
        "realvol_state": st["realvol_state"], "fix_state": st["fix_state"],
    }


def _residual_greeks(ctx: dict, n_paths: int) -> list[dict]:
    """Client-facing presentation of the residual sensitivities, for the PDF
    valuation notes: MtM impact in points for a +1% spot move (delta), its
    convexity (gamma) and +1 vol point (vega).

    The maths lives in compute_greeks — this only rescales. Two consequences of
    that convergence, both improvements: gamma now comes from a ±3% bump rather
    than ±1% (a second difference over a tiny denominator is dominated by Monte
    Carlo noise), and vega is no longer None outside GBM, because it bumps the
    diffusion's vol input rather than a `sigma` field that Heston ignores."""
    from ..core.payscript.engine import compute_greeks

    raw = compute_greeks(
        ctx["residual_script"], ctx["engine_uls"], ctx["corr"],
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=42, user_params=ctx["user_params"],
        selected=["delta", "gamma", "vega"],
        sigma_r=ctx["sigma_r"], a_r=ctx["a_r"], yield_curve=ctx["yc"],
        barrier_monitoring=ctx["barrier_monitoring"],
        antithetic=ctx["antithetic"], state=_greeks_state(ctx),
    )
    out = []
    for i, u in enumerate(ctx["underlyings_json"]):
        delta = raw.get(f"delta_{i+1}")
        gamma = raw.get(f"gamma_{i+1}")
        vega = raw.get(f"vega_{i+1}")
        out.append({
            "name": u["name"],
            # delta is already "price move per 100% of spot", i.e. points per
            # 1% — the two conventions coincide.
            "delta_pts": None if delta is None else round(delta, 2),
            "gamma_pts": None if gamma is None else round(gamma * 0.01, 3),
            "vega_pts": None if vega is None else round(vega, 2),
        })
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
    if not deal or not _can_access_deal(deal, current, session):
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
    if not deal or not _can_access_deal(deal, current, session):
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
    if not deal or not _can_access_deal(deal, current, session):
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
