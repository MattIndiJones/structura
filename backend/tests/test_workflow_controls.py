"""Phase 0/1 safety controls for RFQ -> booking -> lifecycle.

These tests deliberately exercise domain functions directly.  The invariant
must hold without relying on a Vue form or HTTP client behaviour.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api, rfq as rfq_api
from backend.app.core.rfq_controls import booking_gate_failures, pricing_input_hash
from backend.app.core.workflow import DataCategory, FixingStatus, LifecycleStatus
from backend.app.db.models import (
    Alert, AuditEvent, Deal, DealEvent, LifecycleProposal, RfqQuote, RfqRequest,
    TradeAmendmentRequest,
)
from backend.app.db import database as database_api


USER = SimpleNamespace(id=1, entity_id=None)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _params() -> dict:
    today = date.today().isoformat()
    return {
        "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}],
        "user_params": {}, "constats": {}, "notional": 1_000_000.0,
        "currency": "EUR", "strike_date": today, "value_date": today,
        "T": 1.0, "model": "constant", "r": 0.03,
    }


def _executable_pair() -> tuple[RfqRequest, RfqQuote]:
    params = _params()
    script = "AT MATURITY\n  PAY 1"
    rfq = RfqRequest(
        id=1, reference="RFQ-SAFE-001", user_id=1, kind="to_trade",
        script_snapshot=script, params_json=json.dumps(params), status="retenue",
        selected_quote_id=1, model_price=99.0, model_price_at=datetime.utcnow(),
        model_input_hash=pricing_input_hash(script, params),
    )
    quote = RfqQuote(
        id=1, rfq_id=1, provider="Bank", price=99.1, status="recu",
        firmness="FIRM", quoted_at=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(minutes=30),
    )
    return rfq, quote


def _failure_codes(rfq, quote, expected="Bank", requested="Bank") -> set[str]:
    return {failure.code for failure in booking_gate_failures(
        rfq, quote, expected_counterparty=expected,
        requested_counterparty=requested, now=datetime.utcnow())}


@pytest.mark.parametrize("mutation, expected", [
    (lambda r, q: setattr(r, "kind", "indicatif"), "RFQ_NOT_EXECUTABLE"),
    (lambda r, q: setattr(r, "status", "quote"), "RFQ_STATUS_INVALID"),
    (lambda r, q: setattr(q, "price", None), "QUOTE_PRICE_MISSING"),
    (lambda r, q: setattr(q, "status", "decline"), "QUOTE_STATUS_INVALID"),
    (lambda r, q: setattr(q, "firmness", "INDICATIVE"), "QUOTE_NOT_FIRM"),
    (lambda r, q: setattr(q, "valid_until", None), "QUOTE_VALIDITY_UNKNOWN"),
    (lambda r, q: setattr(q, "valid_until", datetime.utcnow() - timedelta(seconds=1)), "QUOTE_EXPIRED"),
    (lambda r, q: setattr(r, "model_price", None), "MODEL_PRICE_MISSING"),
    (lambda r, q: setattr(r, "model_price_at", None), "MODEL_PRICE_TIMESTAMP_MISSING"),
    (lambda r, q: setattr(r, "model_price_at", datetime.utcnow() - timedelta(hours=2)), "MODEL_PRICE_STALE"),
    (lambda r, q: setattr(r, "model_input_hash", None), "MODEL_INPUT_HASH_MISSING"),
    (lambda r, q: setattr(r, "model_input_hash", "changed"), "MODEL_INPUTS_CHANGED"),
])
def test_booking_gate_rejects_independent_failures(mutation, expected):
    rfq, quote = _executable_pair()
    mutation(rfq, quote)
    assert expected in _failure_codes(rfq, quote)


def test_booking_gate_rejects_no_selected_quote():
    rfq, _ = _executable_pair()
    assert "QUOTE_NOT_SELECTED" in _failure_codes(rfq, None)


def test_booking_gate_rejects_unmapped_provider():
    rfq, quote = _executable_pair()
    assert "PROVIDER_COUNTERPARTY_UNMAPPED" in _failure_codes(
        rfq, quote, expected=None)


def test_booking_gate_rejects_counterparty_mismatch():
    rfq, quote = _executable_pair()
    assert "COUNTERPARTY_MISMATCH" in _failure_codes(
        rfq, quote, expected="Bank", requested="Other")


@pytest.mark.parametrize("field, value, expected", [
    ("notional", 0, "NOTIONAL_INVALID"),
    ("currency", "EU", "CURRENCY_INVALID"),
    ("underlyings", [], "UNDERLYINGS_MISSING"),
    ("strike_date", "", "STRIKE_DATE_INVALID"),
    ("T", 0, "TENOR_INVALID"),
])
def test_booking_gate_rejects_incomplete_terms(field, value, expected):
    rfq, quote = _executable_pair()
    params = json.loads(rfq.params_json)
    params[field] = value
    rfq.params_json = json.dumps(params)
    rfq.model_input_hash = pricing_input_hash(rfq.script_snapshot, params)
    assert expected in _failure_codes(rfq, quote)


def test_booking_gate_accepts_complete_firm_fresh_request():
    rfq, quote = _executable_pair()
    assert _failure_codes(rfq, quote) == set()


def test_expired_selected_quote_is_visible_in_business_status():
    rfq, quote = _executable_pair()
    quote.valid_until = datetime.utcnow() - timedelta(seconds=1)
    assert rfq_api._rfq_row(rfq, [quote])["business_status"] == "EXPIRED"


def _deal(session: Session) -> Deal:
    today = date.today()
    deal = Deal(
        reference="DEAL-SAFE-001", user_id=1, script_snapshot="AT MATURITY\n  PAY 1",
        sens="vente", contrepartie="Bank", devise="EUR", nominal=1_000_000,
        fair_value=99.0, price_traded=99.1, trade_date=today.isoformat(),
        strike_date=(today - timedelta(days=1)).isoformat(),
        value_date=(today - timedelta(days=1)).isoformat(),
        maturity_date=today.isoformat(), T=1 / 365.25,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}]),
        market_snapshot_json=json.dumps({"r": 3.0, "user_params": {}, "constats": {}}),
        status="actif",
    )
    session.add(deal)
    session.flush()
    for idx, (event_date, t_years, label) in enumerate([
        (deal.strike_date, 0.0, "Strike"), (deal.maturity_date, deal.T, "Maturité")]):
        session.add(DealEvent(
            deal_id=deal.id, event_index=idx, event_date=event_date,
            t_years=t_years, label=label, status="futur",
            spots_json="{}", indicative_spots_json="{}",
            fixing_status=FixingStatus.EXPECTED, data_category=DataCategory.UNKNOWN,
        ))
    session.commit()
    session.refresh(deal)
    return deal


def _events(session: Session, deal: Deal) -> list[DealEvent]:
    return session.exec(select(DealEvent).where(DealEvent.deal_id == deal.id)
                        .order_by(DealEvent.event_index)).all()


def test_manual_fixing_is_received_but_not_automatically_validated():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    row = deals_api.update_event(
        deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
    assert row["fixing_status"] == "RECEIVED"
    assert row["status"] == "futur"


def test_partial_manual_fixing_is_explicit():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    row = deals_api.update_event(
        deal.id, event.id, deals_api.EventUpdate(spots={}), USER, session)
    assert row["fixing_status"] == "PARTIAL"


def test_incomplete_fixing_validation_is_rejected_and_audited():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(deal.id, event.id, deals_api.EventUpdate(spots={}), USER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_fixing(
            deal.id, event.id, deals_api.FixingValidationRequest(reason="contrôle ops"), USER, session)
    assert exc.value.status_code == 422
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "FIXING_VALIDATION_REJECTED")).first()


def test_complete_official_fixing_can_be_validated():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
    row = deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"), USER, session)
    assert row["fixing_status"] == "VALIDATED"
    assert row["data_category"] == "FIXING_OFFICIAL"


def test_fixing_audit_contains_before_after_reason_and_source():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
    deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"), USER, session)
    audit = session.exec(select(AuditEvent).where(
        AuditEvent.action == "FIXING_VALIDATED")).one()
    assert json.loads(audit.before_json)["fixing_status"] == "RECEIVED"
    assert json.loads(audit.after_json)["fixing_status"] == "VALIDATED"
    assert audit.reason == "source officielle"
    assert audit.data_source == "FIXING_OFFICIAL"


def test_audit_failure_prevents_fixing_persistence(monkeypatch):
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    monkeypatch.setattr(
        deals_api, "record_audit_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        deals_api.update_event(
            deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
    session.rollback()
    persisted = session.get(DealEvent, event.id)
    assert persisted.spots_json == "{}"
    assert persisted.fixing_status == "EXPECTED"


def test_validated_fixing_cannot_be_overwritten_and_creates_alert():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
    deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"), USER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 101.0}), USER, session)
    assert exc.value.status_code == 409
    assert session.get(DealEvent, event.id).spots_json == json.dumps({"UL1": 100.0}, sort_keys=True)
    assert session.exec(select(Alert).where(Alert.kind == "fixing_overwrite_rejected")).first()


def test_indicative_refresh_neither_overwrites_official_nor_resolves(monkeypatch):
    session = _session(); deal = _deal(session); strike, maturity = _events(session, deal)
    strike.spots_json = json.dumps({"UL1": 95.0})
    strike.fixing_status = FixingStatus.VALIDATED
    strike.data_category = DataCategory.FIXING_OFFICIAL
    session.add(strike); session.commit()

    monkeypatch.setattr(deals_api, "load_hist_prices", lambda *args: {
        "dates": [deal.strike_date, deal.maturity_date],
        "prices": {"TK1": [100.0, 100.0]},
    })
    monkeypatch.setattr(deals_api, "_evaluate_lifecycle", lambda *args: {
        "outcome": "final", "event_id": maturity.id,
        "event_date": maturity.event_date, "realized_payout": 1.0,
    })
    result = deals_api.refresh_deal_core(deal, session, actor_user_id=1)
    session.refresh(deal); session.refresh(strike)
    assert json.loads(strike.spots_json) == {"UL1": 95.0}
    assert json.loads(strike.indicative_spots_json) == {"UL1": 100.0}
    assert deal.status == "actif"
    assert result["proposal"]["status"] == "PROPOSED"


def test_repeated_monitoring_deduplicates_the_same_proposal(monkeypatch):
    session = _session(); deal = _deal(session); maturity = _events(session, deal)[-1]
    monkeypatch.setattr(deals_api, "load_hist_prices", lambda *args: {
        "dates": [deal.strike_date, deal.maturity_date],
        "prices": {"TK1": [100.0, 100.0]},
    })
    monkeypatch.setattr(deals_api, "_evaluate_lifecycle", lambda *args: {
        "outcome": "final", "event_id": maturity.id,
        "event_date": maturity.event_date, "realized_payout": 1.0,
    })
    first = deals_api.refresh_deal_core(deal, session)
    session.refresh(deal)
    second = deals_api.refresh_deal_core(deal, session)
    proposals = session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == deal.id)).all()
    assert first["proposal"]["id"] == second["proposal"]["id"]
    assert len(proposals) == 1


def test_refresh_error_is_visible_audited_and_alerted(monkeypatch):
    session = _session(); deal = _deal(session)
    monkeypatch.setattr(deals_api, "load_hist_prices", lambda *args: {"error": "provider down"})
    with pytest.raises(ValueError, match="provider down"):
        deals_api.refresh_deal_core(deal, session)
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "LIFECYCLE_REFRESH_ERROR")).first()
    assert session.exec(select(Alert).where(Alert.kind == "lifecycle_error")).first()


def _proposal(session: Session, deal: Deal) -> LifecycleProposal:
    event = _events(session, deal)[-1]
    proposal = LifecycleProposal(
        deal_id=deal.id, event_id=event.id, dedup_key=f"p:{deal.id}",
        status=LifecycleStatus.PROPOSED, proposed_outcome="final",
        result_json=json.dumps({"outcome": "final", "event_id": event.id,
                                "event_date": event.event_date, "realized_payout": 1.0}),
        data_source=DataCategory.INDICATIVE,
    )
    session.add(proposal); session.commit(); session.refresh(proposal)
    return proposal


def test_resolution_validation_requires_all_official_validated_fixings():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="revue ops", confirmed_outcome="final"), USER, session)
    assert exc.value.status_code == 422


def _validate_all_fixings(session: Session, deal: Deal) -> None:
    for event in _events(session, deal):
        deals_api.update_event(
            deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}), USER, session)
        deals_api.validate_fixing(
            deal.id, event.id,
            deals_api.FixingValidationRequest(reason="source officielle"), USER, session)


def test_resolution_validation_requires_explicit_outcome_confirmation():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(reason="revue payoff"), USER, session)
    failures = exc.value.detail["failures"]
    assert any(failure["code"] == "OUTCOME_CONFIRMATION_REQUIRED" for failure in failures)


def test_resolution_has_separate_validate_and_apply_transitions():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    validated = deals_api.validate_lifecycle_proposal(
        deal.id, proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="revue payoff", confirmed_outcome="final"), USER, session)
    session.refresh(deal)
    assert validated["status"] == "VALIDATED"
    assert deal.status == "actif"
    applied = deals_api.apply_lifecycle_proposal(
        deal.id, proposal.id,
        deals_api.LifecycleValidationRequest(reason="application ops"), USER, session)
    assert applied["proposal"]["status"] == "APPLIED"
    assert applied["deal"]["status"] == "échu"


def test_resolution_application_is_exactly_once():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    deals_api.validate_lifecycle_proposal(
        deal.id, proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="revue payoff", confirmed_outcome="final"), USER, session)
    deals_api.apply_lifecycle_proposal(
        deal.id, proposal.id, deals_api.LifecycleValidationRequest(reason="application ops"), USER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.apply_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(reason="seconde application"), USER, session)
    assert exc.value.status_code == 409
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "RESOLUTION_APPLICATION_REJECTED")).first()


@pytest.mark.parametrize("patch", [
    {"nominal": 2_000_000},
    {"devise": "USD"},
    {"contrepartie": "Other Bank"},
    {"price_traded": 101.0},
    {"status": "échu"},
    {"maturity_date": "2035-01-01"},
    {"script_snapshot": "AT MATURITY\n  PAY 0"},
    {"observation_times": [0.5]},
    {"selected_quote_id": 99},
    {"future_contract_field": "changed"},
])
def test_direct_post_booking_change_is_rejected_and_audited(patch):
    session = _session(); deal = _deal(session)
    with pytest.raises(HTTPException) as exc:
        deals_api.update_deal(deal.id, deals_api.DealUpdate(**patch), USER, session)
    assert exc.value.status_code == 409
    assert session.get(Deal, deal.id).nominal == 1_000_000
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "POST_BOOKING_MODIFICATION_REJECTED")).first()


def test_amendment_request_is_persistent_but_does_not_change_deal():
    session = _session(); deal = _deal(session)
    row = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal", new_value=2_000_000,
            reason="Correction contractuelle documentée"),
        USER, session)
    assert row["status"] == "PENDING"
    assert session.get(Deal, deal.id).nominal == 1_000_000
    assert session.get(TradeAmendmentRequest, row["id"])


def test_legacy_migration_marks_ambiguous_rows_for_manual_review(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE deals (id INTEGER PRIMARY KEY, reference TEXT, rfq_id INTEGER)"))
        conn.execute(text(
            "CREATE TABLE rfq_requests (id INTEGER PRIMARY KEY, reference TEXT, "
            "selected_quote_id INTEGER)"))
        conn.execute(text(
            "CREATE TABLE rfq_quotes (id INTEGER PRIMARY KEY, rfq_id INTEGER)"))
        conn.execute(text(
            "CREATE TABLE deal_events (id INTEGER PRIMARY KEY, spots_json TEXT)"))
        conn.execute(text("INSERT INTO rfq_requests(id, reference) VALUES (1, 'RFQ-OLD')"))
        conn.execute(text("INSERT INTO rfq_quotes(id, rfq_id) VALUES (1, 1)"))
        conn.execute(text("INSERT INTO deal_events(id, spots_json) VALUES (1, '{\"UL1\": 100}')"))
    monkeypatch.setattr(database_api, "engine", engine)
    database_api._migrate()
    database_api._migrate()  # additive and idempotent
    with engine.connect() as conn:
        quote = conn.execute(text(
            "SELECT firmness, valid_until FROM rfq_quotes WHERE id=1")).one()
        event = conn.execute(text(
            "SELECT fixing_status, data_category, indicative_spots_json "
            "FROM deal_events WHERE id=1")).one()
    assert quote.firmness == "UNKNOWN" and quote.valid_until is None
    assert event.fixing_status == "MANUAL_REVIEW_REQUIRED"
    assert event.data_category == "UNKNOWN"
    assert event.indicative_spots_json == "{}"
