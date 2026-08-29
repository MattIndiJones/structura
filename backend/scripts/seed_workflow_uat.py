#!/usr/bin/env python3
"""Create a deterministic UAT dataset for RFQ -> booking -> lifecycle.

The dataset covers both fixing policies: a classic AUTO_YAHOO deal with
user-resolvable exceptions, and controlled FOUR_EYES deals for Maker/Checker
tests.  Every synthetic scenario is clearly identified by a UAT label or
reference.

Without an option, the script is non-destructive and only runs on an empty
database. ``--reset-test-db`` explicitly drops and recreates the one local
SQLite test schema at ``backend/data/structura.db`` before seeding.

Usage from the repository root:
    .venv\Scripts\python.exe backend\scripts\seed_workflow_uat.py --reset-test-db
    .venv\Scripts\python.exe backend\scripts\seed_workflow_uat.py --reset-test-db --generated-count 10
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session, select

from backend.app.api import deals as deals_api
from backend.app.api import rfq as rfq_api
from backend.app.api.portfolios import get_or_create_default_portfolio
from backend.app.core.audit import record_audit_event
from backend.app.core.lifecycle_controls import official_input_hash
from backend.app.core.rfq_controls import booking_gate_failures
from backend.app.core.workflow import (
    DataCategory, FixingPolicy, FixingStatus, LifecycleStatus,
)
from backend.app.db.database import _hash_pw, engine, init_db
from backend.app.db.models import (
    Alert, AuditEvent, Deal, DealEvent, LifecycleProposal, OfficialFixingVersion,
    RfqQuote, RfqRequest, TradeAmendmentRequest, User,
)
from backend.app.services.uat_generation import (
    LIFECYCLE_PROFILE_KEYS, UatGenerationRequest, generate_batch,
)


EXPERT_SCRIPT = """PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
CONSTAT() OBSERVATIONS
AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP
AT MATURITY:
  PAY WOF
"""


NOM_INDICATIVE_BOOKABLE = "UAT 03 — Quote indicative, bookable quand même"


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _terms() -> tuple[dict, dict]:
    today = date.today()
    first = today + timedelta(days=365)
    maturity = today + timedelta(days=3 * 365)
    underlyings = [{
        "name": "Euro Stoxx 50", "ticker": "^STOXX50E", "ccy": "EUR",
        "s0": 5200.0, "sigma": 0.18, "q": 0.025,
    }]
    constats = {"OBSERVATIONS": {
        "start_date": first.isoformat(),
        "end_date": maturity.isoformat(),
        "roll_date": first.isoformat(),
        "frequency": "1Y",
        "stub": "short_last",
    }}
    tenor = round((maturity - today).days / 365.25, 6)
    params = {
        "underlyings": underlyings,
        "user_params": {"COUPON": 0.08},
        "constats": constats,
        "notional": 1_000_000.0,
        "currency": "EUR",
        "strike_date": today.isoformat(),
        "value_date": today.isoformat(),
        "T": tenor,
        "model": "constant",
        "r": 0.03,
        "corr_matrix": [[1.0]],
    }
    dates = {
        "today": today,
        "maturity": maturity,
        "payment": maturity + timedelta(days=5),
        "T": tenor,
    }
    return params, dates


def _create_executable_rfq(
    session: Session,
    user: User,
    *,
    name: str,
    provider: str,
    price: float,
    firmness: str,
    quoted_at: datetime,
    valid_until: datetime | None,
    select_quote: bool,
) -> tuple[dict, dict]:
    params, _ = _terms()
    rfq = rfq_api.create_rfq(
        rfq_api.RfqCreate(
            name=name,
            kind="to_trade",
            sens="achat",
            script_snapshot=EXPERT_SCRIPT,
            params=params,
        ),
        user,
        session,
    )
    quote = rfq_api.add_quote(
        rfq["id"], rfq_api.QuoteCreate(provider=provider), user, session)
    quote = rfq_api.update_quote(
        rfq["id"],
        quote["id"],
        rfq_api.QuoteUpdate(
            price=price,
            quoted_at=_iso(quoted_at),
            firmness=firmness,
            valid_until=_iso(valid_until) if valid_until else None,
        ),
        user,
        session,
    )
    rfq = rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(model_price=99.0), user, session)
    if select_quote:
        rfq = rfq_api.update_rfq(
            rfq["id"], rfq_api.RfqUpdate(selected_quote_id=quote["id"]),
            user, session)
    return rfq, quote


def _book_valid_rfq(session: Session, user: User) -> dict:
    now = datetime.utcnow()
    rfq, quote = _create_executable_rfq(
        session,
        user,
        name="UAT 01 — RFQ ferme bookable",
        provider="UBS",
        price=99.20,
        firmness="FIRM",
        quoted_at=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=25),
        select_quote=True,
    )
    params, dates = _terms()
    market = {
        "underlyings": params["underlyings"],
        "user_params": params["user_params"],
        "constats": params["constats"],
        "r": params["r"],
        "model": params["model"],
        "corrMatrix": params["corr_matrix"],
    }
    return deals_api.book_deal(
        deals_api.DealCreate(
            sens="vente",
            contrepartie="UBS",
            devise="EUR",
            product_type="Autocall UAT",
            nominal=params["notional"],
            fair_value=99.0,
            price_traded=quote["price"],
            trade_date=dates["today"].isoformat(),
            strike_date=dates["today"].isoformat(),
            value_date=dates["today"].isoformat(),
            maturity_date=dates["maturity"].isoformat(),
            payment_date=dates["payment"].isoformat(),
            T=dates["T"],
            underlyings=params["underlyings"],
            observation_times=[],
            script_snapshot=EXPERT_SCRIPT,
            market_snapshot=market,
            rfq_id=rfq["id"],
        ),
        user,
        session,
    )


def _create_rfq_scenarios(session: Session, user: User) -> None:
    now = datetime.utcnow()
    _create_executable_rfq(
        session, user,
        name="UAT 02 — Quote expirée",
        provider="BNP Paribas", price=98.90, firmness="FIRM",
        quoted_at=now - timedelta(hours=2),
        valid_until=now - timedelta(hours=1), select_quote=True,
    )
    _create_executable_rfq(
        session, user,
        name=NOM_INDICATIVE_BOOKABLE,
        provider="Société Générale", price=99.10, firmness="INDICATIVE",
        quoted_at=now - timedelta(minutes=10),
        valid_until=now + timedelta(minutes=20), select_quote=True,
    )
    _create_executable_rfq(
        session, user,
        name="UAT 04 — Validité inconnue",
        provider="UBS", price=99.05, firmness="FIRM",
        quoted_at=now - timedelta(minutes=10),
        valid_until=None, select_quote=True,
    )
    _create_executable_rfq(
        session, user,
        name="UAT 05 — Quote reçue non sélectionnée",
        provider="BNP Paribas", price=99.30, firmness="FIRM",
        quoted_at=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=25), select_quote=False,
    )
    rfq_api.create_rfq(
        rfq_api.RfqCreate(
            name="UAT 06 — Exploration indicative",
            kind="indicatif",
            script_snapshot="AT MATURITY\n  PAY 1",
            params={},
        ),
        user,
        session,
    )


def _base_lifecycle_deal(
    session: Session,
    user: User,
    *,
    reference: str,
    status: str = "actif",
    outcome: str | None = None,
    payout: float | None = None,
    fixing_policy: str = FixingPolicy.FOUR_EYES.value,
) -> Deal:
    today = date.today()
    portfolio = get_or_create_default_portfolio(session, user.id)
    underlyings = [{
        "name": "Euro Stoxx 50", "ticker": "^STOXX50E", "ccy": "EUR",
        "s0_abs": 5000.0,
    }]
    deal = Deal(
        reference=reference,
        entity_id=user.entity_id,
        user_id=user.id,
        portfolio_id=portfolio.id,
        script_snapshot=(
            "PARAM COUPON = 8%\nPARAM M_AC = 100%\n"
            "AT 1:\n  SET CALL = INDIC(WOF >= M_AC)\n  PAY CALL * (1 + COUPON)\n"
            "  IF CALL = 1:\n    STOP\nAT MATURITY:\n  PAY WOF"
        ),
        sens="vente",
        contrepartie="UBS",
        devise="EUR",
        nominal=1_000_000.0,
        fair_value=99.0,
        price_traded=99.2,
        product_type="Autocall UAT lifecycle",
        fixing_policy=fixing_policy,
        trade_date=(today - timedelta(days=400)).isoformat(),
        strike_date=(today - timedelta(days=400)).isoformat(),
        value_date=(today - timedelta(days=400)).isoformat(),
        maturity_date=(today + timedelta(days=330)).isoformat(),
        payment_date=(today + timedelta(days=335)).isoformat(),
        T=2.0,
        realized_payout=payout,
        resolution_outcome=outcome,
        underlyings_json=json.dumps(underlyings),
        market_snapshot_json=json.dumps({
            "underlyings": underlyings, "user_params": {"COUPON": 0.08},
            "constats": {}, "r": 3.0,
        }),
        status=status,
    )
    session.add(deal)
    session.flush()
    return deal


def _attach_fixing_version(
    session: Session,
    deal: Deal,
    event: DealEvent,
    *,
    entered_by: User,
    status: str,
    validated_by: User | None = None,
) -> OfficialFixingVersion:
    observed_at = f"{event.event_date}T12:00:00+00:00"
    evidence_payload = (
        f"UAT evidence deal={deal.id} event={event.event_index} version=1"
    ).encode("utf-8")
    body = deals_api.EventUpdate(
        spots=json.loads(event.spots_json or "{}"),
        provider="BLOOMBERG",
        source_type="MESSAGE",
        external_reference=f"UAT-FIX-{deal.id}-{event.event_index}-V1",
        observed_at=observed_at,
        venue="Official close UAT",
        calendar="TARGET",
        timezone="UTC",
        evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
        evidence_filename=f"uat-fixing-{deal.id}-{event.event_index}.txt",
        evidence_content_type="text/plain",
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        reason="Fixture UAT de provenance officielle",
    )
    payload = deals_api._fixing_record_payload(
        deal, event, body, version=1, supersedes_id=None)
    now = datetime.utcnow()
    version = OfficialFixingVersion(
        deal_id=deal.id,
        deal_event_id=event.id,
        version=1,
        status=status,
        spots_json=event.spots_json,
        provider=body.provider,
        source_type=body.source_type,
        external_reference=body.external_reference,
        observed_at=datetime.fromisoformat(observed_at).replace(tzinfo=None),
        venue=body.venue,
        calendar=body.calendar,
        timezone=body.timezone,
        evidence_sha256=body.evidence_sha256,
        evidence_filename=body.evidence_filename,
        evidence_content_type=body.evidence_content_type,
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=body.evidence_payload_b64,
        record_sha256=deals_api._fixing_record_hash(payload),
        capture_reason=body.reason,
        entered_by=entered_by.id,
        validated_by=validated_by.id if validated_by else None,
        validation_reason="Validation UAT indépendante" if validated_by else None,
        validated_at=now if validated_by else None,
        applied_at=now if status == FixingStatus.APPLIED else None,
    )
    session.add(version)
    session.flush()
    event.current_fixing_version_id = version.id
    event.fixing_version = version.version
    event.fixing_entered_by = entered_by.id
    event.fixing_entered_at = now
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
    event.data_category = (
        DataCategory.FIXING_OFFICIAL
        if status in {FixingStatus.VALIDATED, FixingStatus.APPLIED}
        else DataCategory.FIXING_CANDIDATE
    )
    event.validated_by = validated_by.id if validated_by else None
    event.validated_at = now if validated_by else None
    session.add(event)
    return version


def _create_lifecycle_scenarios(
    session: Session,
    user: User,
    ops_maker: User,
    checker: User,
) -> None:
    today = date.today()

    proposed = _base_lifecycle_deal(
        session, user, reference="UAT-LC-001-PROPOSITION",
        fixing_policy=FixingPolicy.AUTO_YAHOO.value)
    strike = DealEvent(
        deal_id=proposed.id, event_index=0,
        event_date=(today - timedelta(days=400)).isoformat(), t_years=0.0,
        spots_json=json.dumps({"Euro Stoxx 50": 5000.0}),
        indicative_spots_json=json.dumps({"Euro Stoxx 50": 5012.0}),
        source="manuel", status="futur", fixing_status=FixingStatus.RECEIVED,
        data_category=DataCategory.FIXING_CANDIDATE, label="Strike / Fixing S₀",
    )
    observation = DealEvent(
        deal_id=proposed.id, event_index=1,
        event_date=(today - timedelta(days=35)).isoformat(), t_years=1.0,
        spots_json=json.dumps({"Euro Stoxx 50": 5150.0}),
        indicative_spots_json=json.dumps({"Euro Stoxx 50": 5165.0}),
        source="manuel", status="futur", fixing_status=FixingStatus.RECEIVED,
        data_category=DataCategory.FIXING_CANDIDATE, label="Observation 1Y",
    )
    maturity = DealEvent(
        deal_id=proposed.id, event_index=2,
        event_date=(today + timedelta(days=330)).isoformat(), t_years=2.0,
        source="pending", status="futur", fixing_status=FixingStatus.EXPECTED,
        data_category=DataCategory.UNKNOWN, label="Maturité",
    )
    session.add(strike); session.add(observation); session.add(maturity)
    session.flush()
    _attach_fixing_version(
        session, proposed, strike, entered_by=ops_maker,
        status=FixingStatus.RECEIVED)
    _attach_fixing_version(
        session, proposed, observation, entered_by=ops_maker,
        status=FixingStatus.RECEIVED)
    proposal = LifecycleProposal(
        deal_id=proposed.id,
        event_id=observation.id,
        dedup_key=f"uat:lifecycle:{proposed.id}:called",
        status=LifecycleStatus.PROPOSED,
        proposed_outcome="callé",
        result_json=json.dumps({
            "outcome": "callé", "event_id": observation.id,
            "event_date": observation.event_date, "t_years": 1.0,
            "realized_payout": 1.08,
        }),
        data_source=DataCategory.INDICATIVE,
    )
    session.add(proposal)
    session.flush()
    session.add(Alert(
        user_id=user.id, deal_id=proposed.id,
        deal_reference=proposed.reference, kind="resolution_proposed",
        message="UAT : rappel anticipé proposé, validation humaine requise.",
        dedup_key=f"uat:proposal:{proposal.id}",
    ))
    for exception_event in (strike, observation):
        session.add(Alert(
            user_id=user.id, deal_id=proposed.id,
            deal_reference=proposed.reference, kind="auto_fixing_exception",
            message=(
                f"UAT : {exception_event.label} doit être décidé par "
                "l'utilisateur du deal."),
            dedup_key=(
                f"auto-fixing-exception:{proposed.id}:"
                f"{exception_event.id}:uat"),
        ))
    record_audit_event(
        session,
        action="RESOLUTION_PROPOSED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=None,
        actor_type="PROCESS",
        result="SUCCESS",
        after={"outcome": "callé", "event_id": observation.id},
        reason="Jeu UAT : proposition issue du monitoring indicatif.",
        data_source=DataCategory.INDICATIVE,
    )

    partial = _base_lifecycle_deal(
        session, user, reference="UAT-LC-002-FIXING-PARTIEL")
    partial_event = DealEvent(
        deal_id=partial.id, event_index=0,
        event_date=(today - timedelta(days=30)).isoformat(), t_years=0.0,
        spots_json="{}",
        indicative_spots_json=json.dumps({"Euro Stoxx 50": 5080.0}),
        source="manuel", status="futur", fixing_status=FixingStatus.PARTIAL,
        data_category=DataCategory.FIXING_CANDIDATE, label="Strike incomplet",
    )
    session.add(partial_event)
    session.add(DealEvent(
        deal_id=partial.id, event_index=1,
        event_date=(today + timedelta(days=335)).isoformat(), t_years=1.0,
        source="pending", status="futur", fixing_status=FixingStatus.EXPECTED,
        data_category=DataCategory.UNKNOWN, label="Maturité",
    ))
    session.flush()
    _attach_fixing_version(
        session, partial, partial_event, entered_by=ops_maker,
        status=FixingStatus.PARTIAL)

    applied = _base_lifecycle_deal(
        session, user, reference="UAT-LC-003-APPLIQUE",
        status="callé", outcome="callé", payout=1.08)
    applied_strike = DealEvent(
        deal_id=applied.id, event_index=0,
        event_date=(today - timedelta(days=400)).isoformat(), t_years=0.0,
        spots_json=json.dumps({"Euro Stoxx 50": 5000.0}), source="manuel",
        status="observé", fixing_status=FixingStatus.APPLIED,
        data_category=DataCategory.FIXING_OFFICIAL,
        validated_by=checker.id, validated_at=datetime.utcnow(),
        applied_at=datetime.utcnow(), label="Strike / Fixing S₀",
    )
    applied_call = DealEvent(
        deal_id=applied.id, event_index=1,
        event_date=(today - timedelta(days=35)).isoformat(), t_years=1.0,
        spots_json=json.dumps({"Euro Stoxx 50": 5200.0}), source="manuel",
        status="callé", fixing_status=FixingStatus.APPLIED,
        data_category=DataCategory.FIXING_OFFICIAL,
        validated_by=checker.id, validated_at=datetime.utcnow(),
        applied_at=datetime.utcnow(), label="Observation 1Y",
    )
    applied_future = DealEvent(
        deal_id=applied.id, event_index=2,
        event_date=(today + timedelta(days=330)).isoformat(), t_years=2.0,
        status="annulé", fixing_status=FixingStatus.EXPECTED,
        data_category=DataCategory.UNKNOWN, label="Maturité annulée",
    )
    session.add(applied_strike); session.add(applied_call); session.add(applied_future)
    session.flush()
    _attach_fixing_version(
        session, applied, applied_strike, entered_by=ops_maker,
        validated_by=checker, status=FixingStatus.APPLIED)
    _attach_fixing_version(
        session, applied, applied_call, entered_by=ops_maker,
        validated_by=checker, status=FixingStatus.APPLIED)
    applied_proposal = LifecycleProposal(
        deal_id=applied.id,
        event_id=applied_call.id,
        dedup_key=f"uat:lifecycle:{applied.id}:applied",
        status=LifecycleStatus.APPLIED,
        proposed_outcome="callé",
        result_json=json.dumps({
            "outcome": "callé", "event_id": applied_call.id,
            "event_date": applied_call.event_date, "realized_payout": 1.08,
        }),
        data_source=DataCategory.INDICATIVE,
        official_result_json=json.dumps({
            "outcome": "callé", "outcome_basis": "SCRIPT_STOP",
            "event_id": applied_call.id, "event_date": applied_call.event_date,
            "realized_payout": 1.08, "input_kind": "VALIDATED_EVENT_FIXINGS",
        }),
        official_input_hash=official_input_hash(
            applied, [applied_strike, applied_call]),
        official_replayed_at=datetime.utcnow(),
        comparison_status="MATCH",
        validated_by=checker.id,
        validation_reason="UAT : fixings officiels contrôlés.",
        validated_at=datetime.utcnow(),
        applied_by=checker.id,
        applied_at=datetime.utcnow(),
    )
    session.add(applied_proposal)
    session.flush()
    record_audit_event(
        session,
        action="RESOLUTION_APPLIED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=applied_proposal.id,
        actor_user_id=checker.id,
        result="SUCCESS",
        before={"status": "VALIDATED"},
        after={"status": "APPLIED", "deal_status": "callé"},
        reason="Jeu UAT : exemple de résolution appliquée.",
        data_source=DataCategory.FIXING_OFFICIAL,
    )
    session.commit()
    deals_api.request_amendment(
        partial.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal",
            new_value=1_100_000.0,
            reason="UAT : demande de correction contrôlée sans mutation du deal.",
        ),
        user,
        session,
    )


def _summary(session: Session) -> dict:
    return {
        "users": len(session.exec(select(User)).all()),
        "rfqs": len(session.exec(select(RfqRequest)).all()),
        "quotes": len(session.exec(select(RfqQuote)).all()),
        "deals": len(session.exec(select(Deal)).all()),
        "events": len(session.exec(select(DealEvent)).all()),
        "fixing_versions": len(session.exec(select(OfficialFixingVersion)).all()),
        "lifecycle_proposals": len(session.exec(select(LifecycleProposal)).all()),
        "audit_events": len(session.exec(select(AuditEvent)).all()),
        "amendment_requests": len(session.exec(select(TradeAmendmentRequest)).all()),
    }


def _verify_uat_dataset(session: Session) -> list[str]:
    checks: list[str] = []
    rfqs = {rfq.name: rfq for rfq in session.exec(select(RfqRequest)).all()}
    deals = {deal.reference: deal for deal in session.exec(select(Deal)).all()}
    if len(rfqs) != 6 or len(deals) != 4:
        raise RuntimeError(f"Jeu UAT incomplet : {len(rfqs)} RFQ, {len(deals)} deals")
    checks.append("cardinalités RFQ/deals")

    booked = rfqs["UAT 01 — RFQ ferme bookable"]
    if booked.status != "clos" or not session.exec(
            select(Deal).where(Deal.rfq_id == booked.id)).first():
        raise RuntimeError("Le scénario UAT bookable n'est pas exécuté correctement.")
    checks.append("RFQ ferme exécutée")

    cpty_map = rfq_api._counterparty_by_provider(session)

    def failure_codes(name: str) -> set[str]:
        rfq = rfqs[name]
        selected = session.get(RfqQuote, rfq.selected_quote_id) \
            if rfq.selected_quote_id else None
        expected = cpty_map.get(selected.provider) if selected else None
        return {failure.code for failure in booking_gate_failures(
            rfq,
            selected,
            expected_counterparty=expected,
            requested_counterparty=expected or "",
        )}

    expected_failures = {
        "UAT 02 — Quote expirée": "QUOTE_EXPIRED",
        "UAT 04 — Validité inconnue": "QUOTE_VALIDITY_UNKNOWN",
        "UAT 05 — Quote reçue non sélectionnée": "QUOTE_NOT_SELECTED",
        "UAT 06 — Exploration indicative": "RFQ_NOT_EXECUTABLE",
    }
    for name, code in expected_failures.items():
        codes = failure_codes(name)
        if code not in codes:
            raise RuntimeError(f"{name}: blocage {code} absent ({sorted(codes)})")
    checks.append("quatre scénarios de refus booking")

    # UAT 03 a changé de camp le 29/08/2026. Une cotation marquée indicative se
    # booke désormais : retenir puis booker EST l'affirmation qu'elle engage la
    # contrepartie, et l'étiquette n'apprenait rien à personne. Ce qu'elle
    # valait avant reste dans la provenance du deal.
    #
    # Le scénario est gardé, pas supprimé : c'est un état de donnée réel, et il
    # vérifie maintenant que rien ne bloque.
    codes = failure_codes(NOM_INDICATIVE_BOOKABLE)
    if codes:
        raise RuntimeError(
            f"{NOM_INDICATIVE_BOOKABLE} : ne devrait plus rien bloquer ({sorted(codes)})")
    checks.append("quote indicative bookable")

    proposed = deals["UAT-LC-001-PROPOSITION"]
    proposed_row = session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == proposed.id)).one()
    proposed_events = session.exec(select(DealEvent).where(
        DealEvent.deal_id == proposed.id)).all()
    if proposed.status != "actif" or proposed_row.status != "PROPOSED" \
            or proposed.fixing_policy != FixingPolicy.AUTO_YAHOO.value \
            or sum(event.fixing_status == "RECEIVED" for event in proposed_events) != 2:
        raise RuntimeError("Le scénario lifecycle proposé est incohérent.")
    checks.append("deux exceptions AUTO_YAHOO résolubles par l'utilisateur")

    partial = deals["UAT-LC-002-FIXING-PARTIEL"]
    if partial.fixing_policy != FixingPolicy.FOUR_EYES.value:
        raise RuntimeError("Le scénario de contrôle Maker/Checker n'est plus FOUR_EYES.")
    if not session.exec(select(DealEvent).where(
            DealEvent.deal_id == partial.id,
            DealEvent.fixing_status == "PARTIAL")).first():
        raise RuntimeError("Le scénario de fixing partiel est absent.")
    amendment = session.exec(select(TradeAmendmentRequest).where(
        TradeAmendmentRequest.deal_id == partial.id)).one()
    if amendment.status != "PENDING" or partial.nominal != 1_000_000.0:
        raise RuntimeError("La demande d'amendement a modifié le deal ou son statut.")
    checks.append("fixing partiel et amendement sans mutation")

    applied = deals["UAT-LC-003-APPLIQUE"]
    applied_proposal = session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == applied.id)).one()
    if applied.status != "callé" or applied_proposal.status != "APPLIED":
        raise RuntimeError("Le scénario lifecycle appliqué est incohérent.")
    if (not applied_proposal.official_result_json or
            not applied_proposal.official_input_hash or
            applied_proposal.comparison_status != "MATCH"):
        raise RuntimeError("Le rejeu officiel du scénario appliqué est absent.")
    checks.append("résolution appliquée depuis un rejeu officiel hashé")

    if len(session.exec(select(AuditEvent)).all()) < 25:
        raise RuntimeError("La piste d'audit UAT est insuffisante.")
    checks.append("piste d'audit persistante")
    unproven = [event for event in session.exec(select(DealEvent)).all()
                if event.fixing_status in {"RECEIVED", "PARTIAL", "VALIDATED", "APPLIED"}
                and not event.current_fixing_version_id]
    if unproven:
        raise RuntimeError("Le jeu UAT contient des fixings sans preuve versionnée.")
    versions = session.exec(select(OfficialFixingVersion)).all()
    corrupt_evidence = []
    for version in versions:
        try:
            payload = base64.b64decode(version.evidence_payload_b64, validate=True)
        except (ValueError, binascii.Error):
            payload = b""
        if (
            not payload
            or len(payload) != version.evidence_size_bytes
            or hashlib.sha256(payload).hexdigest() != version.evidence_sha256
        ):
            corrupt_evidence.append(version.id)
    if corrupt_evidence:
        raise RuntimeError(
            f"Pièces UAT absentes ou incohérentes : {corrupt_evidence}")
    checks.append("provenance versionnée et pièces archivées vérifiées")
    return checks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crée le jeu UAT RFQ -> booking -> lifecycle.")
    parser.add_argument(
        "--reset-test-db",
        action="store_true",
        help="Supprime et recrée explicitement le schéma de la base SQLite locale de test.",
    )
    parser.add_argument(
        "--generated-count",
        type=int,
        default=0,
        choices=range(0, 101),
        metavar="0..100",
        help=("Ajoute un lot reproductible via le même moteur que l'écran Admin "
              "(0 : fixtures de contrôle uniquement)."),
    )
    parser.add_argument(
        "--generated-seed",
        type=int,
        default=42,
        help="Graine du lot Admin optionnel (défaut : 42).",
    )
    parser.add_argument(
        "--generated-lifecycle-profile",
        choices=(*LIFECYCLE_PROFILE_KEYS, "COMPLETE_MIX"),
        default="COMPLETE_MIX",
        help=("Profil temporel du lot optionnel (défaut : COMPLETE_MIX, qui "
              "parcourt les huit cas avec au moins huit objets)."),
    )
    return parser.parse_args()


def _reset_local_test_schema() -> None:
    expected = (
        Path(__file__).resolve().parents[1] / "data" / "structura.db"
    ).resolve()
    actual = Path(str(engine.url.database)).resolve()
    if engine.url.drivername != "sqlite" or actual != expected:
        raise SystemExit(
            f"Reset refusé : moteur inattendu ({engine.url}) ; cible autorisée : {expected}")
    # RFQ requests and quotes form a deliberate FK cycle (selected quote ↔
    # owning RFQ). SQLite cannot topologically sort that cycle for drop_all,
    # so disable FK enforcement only on this verified local connection while
    # dropping every user table, then restore it before closing.
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        tables = [row[0] for row in cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        for table_name in tables:
            quoted = table_name.replace('"', '""')
            cursor.execute(f'DROP TABLE IF EXISTS "{quoted}"')
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    finally:
        raw.close()


def main() -> None:
    args = _parse_args()
    if args.reset_test_db:
        _reset_local_test_schema()
    init_db()
    with Session(engine) as session:
        if session.exec(select(RfqRequest)).first() or session.exec(select(Deal)).first():
            raise SystemExit(
                "Refus : la base contient déjà des RFQ ou des deals. "
                "Utilisez uniquement ce script après un reset explicite de la base de test.")
        user = session.exec(select(User).where(User.username == "test")).first()
        if not user:
            raise SystemExit("Utilisateur de test introuvable après init_db().")
        ops_maker = User(
            username="uat.ops.maker",
            email="uat.ops.maker@structura.local",
            password_hash=_hash_pw("uatmaker123"),
            role="ops_maker",
            entity_id=user.entity_id,
        )
        checker = User(
            username="uat.ops.checker",
            email="uat.ops.checker@structura.local",
            password_hash=_hash_pw("uatchecker123"),
            role="checker",
            entity_id=user.entity_id,
        )
        session.add(ops_maker); session.add(checker); session.commit()
        session.refresh(ops_maker); session.refresh(checker)

        booked = _book_valid_rfq(session, user)
        _create_rfq_scenarios(session, user)
        _create_lifecycle_scenarios(session, user, ops_maker, checker)
        checks = _verify_uat_dataset(session)
        generated_batch = None
        if args.generated_count:
            admin = session.exec(select(User).where(User.username == "admin")).one()
            generated_batch = generate_batch(
                UatGenerationRequest(
                    target_user_id=user.id,
                    mode="FULL_CHAIN",
                    count=args.generated_count,
                    seed=args.generated_seed,
                    label="Lot CLI partagé avec le générateur Admin",
                    lifecycle_profile=args.generated_lifecycle_profile,
                ),
                admin,
                session,
            )
        print(json.dumps({
            "status": "ok",
            "logins": {
                "deal_owner": "test / test123",
                "ops_maker": "uat.ops.maker / uatmaker123",
                "ops_checker": "uat.ops.checker / uatchecker123",
            },
            "booked_reference": booked["reference"],
            "summary": _summary(session),
            "checks": checks,
            "generated_batch": generated_batch,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
