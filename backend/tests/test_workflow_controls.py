"""Phase 0/1 safety controls for RFQ -> booking -> lifecycle.

These tests deliberately exercise domain functions directly.  The invariant
must hold without relying on a Vue form or HTTP client behaviour.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api, rfq as rfq_api
from backend.app.core.rfq_controls import booking_gate_failures, pricing_input_hash
from backend.app.core.workflow import (
    DataCategory, FixingPolicy, FixingStatus, LifecycleStatus,
)
from backend.app.db.models import (
    Alert, AuditEvent, Deal, DealEvent, LifecycleProposal, OfficialFixingVersion,
    RfqQuote, RfqRequest, TradeAmendmentRequest,
)
from backend.app.db import database as database_api


USER = SimpleNamespace(id=1, entity_id=7, role="user")
OPS_MAKER = SimpleNamespace(id=2, entity_id=7, role="ops_maker")
CHECKER = SimpleNamespace(id=3, entity_id=7, role="checker")
OTHER_CHECKER = SimpleNamespace(id=4, entity_id=8, role="checker")


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
        "payment_date": (date.today() + timedelta(days=370)).isoformat(),
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
        reference="DEAL-SAFE-001", entity_id=7, user_id=1,
        script_snapshot="AT MATURITY\n  PAY 1",
        sens="vente", contrepartie="Bank", devise="EUR", nominal=1_000_000,
        fair_value=99.0, price_traded=99.1, trade_date=today.isoformat(),
        strike_date=(today - timedelta(days=1)).isoformat(),
        value_date=(today - timedelta(days=1)).isoformat(),
        maturity_date=today.isoformat(), T=1 / 365.25,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}]),
        market_snapshot_json=json.dumps({"r": 3.0, "user_params": {}, "constats": {}}),
        fixing_policy=FixingPolicy.FOUR_EYES.value,
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


def _fixing_submission(
    event: DealEvent,
    spots: dict,
    *,
    supersedes_version: int | None = None,
) -> deals_api.EventUpdate:
    evidence_payload = (
        f"Preuve officielle événement {event.id}, version "
        f"{(supersedes_version or 0) + 1}"
    ).encode("utf-8")
    observed_at = datetime.now(timezone.utc)
    if event.event_date != observed_at.date().isoformat():
        observed_at = datetime.fromisoformat(f"{event.event_date}T12:00:00+00:00")
    return deals_api.EventUpdate(
        spots=spots,
        provider="BLOOMBERG",
        source_type="MESSAGE",
        external_reference=f"MSG-{event.id}-{supersedes_version or 1}",
        observed_at=observed_at.isoformat(),
        venue="Official close",
        calendar="TARGET",
        timezone="UTC",
        evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
        evidence_filename=f"fixing-{event.id}.txt",
        evidence_content_type="text/plain",
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        reason="Capture officielle documentée",
        supersedes_version=supersedes_version,
    )


def test_manual_fixing_is_received_but_not_automatically_validated():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    row = deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}), OPS_MAKER, session)
    assert row["fixing_status"] == "RECEIVED"
    assert row["data_category"] == "FIXING_CANDIDATE"
    assert row["fixing_entered_by"] == OPS_MAKER.id
    assert row["status"] == "futur"


def test_partial_manual_fixing_is_explicit():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    row = deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {}), OPS_MAKER, session)
    assert row["fixing_status"] == "PARTIAL"


def test_incomplete_fixing_validation_is_rejected_and_audited():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {}), OPS_MAKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_fixing(
            deal.id, event.id, deals_api.FixingValidationRequest(reason="contrôle ops"),
            CHECKER, session)
    assert exc.value.status_code == 422
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "FIXING_VALIDATION_REJECTED")).first()


def test_complete_official_fixing_can_be_validated():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}), OPS_MAKER, session)
    row = deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"),
        CHECKER, session)
    assert row["fixing_status"] == "VALIDATED"
    assert row["data_category"] == "FIXING_OFFICIAL"


def test_fixing_validation_requires_an_intact_archived_evidence_payload():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    version = session.exec(select(OfficialFixingVersion)).one()
    version.evidence_payload_b64 = base64.b64encode(
        "preuve altérée".encode("utf-8")).decode("ascii")
    session.add(version); session.commit()
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_fixing(
            deal.id, event.id,
            deals_api.FixingValidationRequest(reason="Contrôle de la pièce source"),
            CHECKER, session)
    assert any(failure["code"] == "FIXING_EVIDENCE_ARCHIVE_MISMATCH"
               for failure in exc.value.detail["failures"])


def test_checker_can_download_the_verified_archived_evidence():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    version = session.exec(select(OfficialFixingVersion)).one()
    response = deals_api.download_fixing_evidence(
        deal.id, event.id, version.id, CHECKER, session)
    assert hashlib.sha256(response.body).hexdigest() == version.evidence_sha256
    assert response.headers["cache-control"] == "no-store"


def test_user_role_cannot_capture_an_official_fixing_candidate():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
            USER, session)
    assert exc.value.status_code == 403
    assert exc.value.detail["failures"][0]["field"] == "user.role"
    assert not session.exec(select(OfficialFixingVersion)).first()


def test_deal_owner_cannot_capture_even_when_role_is_ops_maker():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deal.user_id = OPS_MAKER.id
    session.add(deal); session.commit()
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
            OPS_MAKER, session)
    assert exc.value.status_code == 409
    assert exc.value.detail["failures"][0]["code"] == \
        "DEAL_OWNER_CANNOT_CAPTURE_FIXING"
    assert not session.exec(select(OfficialFixingVersion)).first()


def test_fixing_capture_requires_complete_actionable_provenance():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id, deals_api.EventUpdate(spots={"UL1": 100.0}),
            OPS_MAKER, session)
    fields = {failure["field"] for failure in exc.value.detail["failures"]}
    assert {"provider", "external_reference", "observed_at", "evidence_sha256"} <= fields
    assert all(failure.get("action") for failure in exc.value.detail["failures"])
    assert not session.exec(select(OfficialFixingVersion)).first()


def test_fixing_provider_must_belong_to_the_controlled_registry():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    submission = _fixing_submission(event, {"UL1": 100.0})
    submission.provider = "Source libre non homologuée"
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(deal.id, event.id, submission, OPS_MAKER, session)
    failure = next(row for row in exc.value.detail["failures"]
                   if row["code"] == "FIXING_PROVIDER_NOT_AUTHORIZED")
    assert failure["field"] == "provider"
    assert "référentiel" in failure["message"]


def test_fixing_timestamp_offset_must_match_the_market_timezone():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    submission = _fixing_submission(event, {"UL1": 100.0})
    submission.observed_at = f"{event.event_date}T12:00:00+01:00"
    submission.timezone = "UTC"
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(deal.id, event.id, submission, OPS_MAKER, session)
    failure = next(row for row in exc.value.detail["failures"]
                   if row["code"] == "FIXING_TIMEZONE_OFFSET_MISMATCH")
    assert failure["field"] == "observed_at"
    assert failure["action"]


def test_fixing_maker_cannot_validate_own_submission():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    same_person_checker = SimpleNamespace(id=OPS_MAKER.id, entity_id=7, role="checker")
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_fixing(
            deal.id, event.id,
            deals_api.FixingValidationRequest(reason="Auto-validation interdite"),
            same_person_checker, session)
    assert any(failure["code"] == "FOUR_EYES_VIOLATION"
               for failure in exc.value.detail["failures"])
    assert session.get(DealEvent, event.id).fixing_status == "RECEIVED"


def test_fixing_checker_is_scoped_to_the_deal_entity():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_fixing(
            deal.id, event.id,
            deals_api.FixingValidationRequest(reason="Mauvaise entité juridique"),
            OTHER_CHECKER, session)
    assert exc.value.status_code == 404


def test_fixing_correction_creates_a_new_immutable_version():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    deals_api.validate_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="Validation version initiale"),
        CHECKER, session)
    corrected = deals_api.update_event(
        deal.id, event.id,
        _fixing_submission(event, {"UL1": 101.0}, supersedes_version=1),
        OPS_MAKER, session)
    assert corrected["fixing_version"] == 2
    assert corrected["fixing_status"] == "RECEIVED"
    assert corrected["data_category"] == "FIXING_CANDIDATE"
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version)).all()
    assert [row.status for row in versions] == ["CONTESTED", "RECEIVED"]

    deals_api.validate_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="Validation correction officielle"),
        CHECKER, session)
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version)).all()
    assert [row.status for row in versions] == ["SUPERSEDED", "VALIDATED"]
    assert json.loads(versions[0].spots_json) == {"UL1": 100.0}
    assert json.loads(versions[1].spots_json) == {"UL1": 101.0}
    deal_row = deals_api.get_deal(deal.id, USER, session)
    history = deal_row["events"][0]["fixing_versions"]
    assert [row["version"] for row in history] == [2, 1]
    assert history[1]["status"] == "SUPERSEDED"


def test_checker_can_reject_an_initial_fixing_candidate():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    row = deals_api.reject_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="La pièce ne correspond pas au contrat"),
        CHECKER, session)
    version = session.exec(select(OfficialFixingVersion)).one()
    assert row["fixing_status"] == "REJECTED"
    assert version.status == "REJECTED"
    assert version.rejected_by == CHECKER.id
    assert version.rejection_reason == "La pièce ne correspond pas au contrat"


def test_rejecting_a_correction_restores_the_previous_official_version():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    deals_api.validate_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="Validation version initiale"),
        CHECKER, session)
    deals_api.update_event(
        deal.id, event.id,
        _fixing_submission(event, {"UL1": 101.0}, supersedes_version=1),
        OPS_MAKER, session)
    row = deals_api.reject_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="Correction non justifiée par la pièce"),
        CHECKER, session)
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version)).all()
    assert [version.status for version in versions] == ["VALIDATED", "REJECTED"]
    assert row["fixing_version"] == 1
    assert row["fixing_status"] == "VALIDATED"
    assert row["data_category"] == "FIXING_OFFICIAL"
    assert row["spots"] == {"UL1": 100.0}


def test_a_second_correction_waits_for_the_checker_decision():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
        OPS_MAKER, session)
    deals_api.validate_fixing(
        deal.id, event.id,
        deals_api.FixingValidationRequest(reason="Validation version initiale"),
        CHECKER, session)
    deals_api.update_event(
        deal.id, event.id,
        _fixing_submission(event, {"UL1": 101.0}, supersedes_version=1),
        OPS_MAKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id,
            _fixing_submission(event, {"UL1": 102.0}, supersedes_version=2),
            OPS_MAKER, session)
    assert any(failure["code"] == "FIXING_CORRECTION_DECISION_PENDING"
               for failure in exc.value.detail["failures"])
    assert session.exec(select(OfficialFixingVersion)).all().__len__() == 2


def test_fixing_audit_contains_before_after_reason_and_source():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}), OPS_MAKER, session)
    deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"),
        CHECKER, session)
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
            deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
            OPS_MAKER, session)
    session.rollback()
    persisted = session.get(DealEvent, event.id)
    assert persisted.spots_json == "{}"
    assert persisted.fixing_status == "EXPECTED"


def test_validated_fixing_cannot_be_overwritten_and_creates_alert():
    session = _session(); deal = _deal(session); event = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}), OPS_MAKER, session)
    deals_api.validate_fixing(
        deal.id, event.id, deals_api.FixingValidationRequest(reason="source officielle"),
        CHECKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.update_event(
            deal.id, event.id, _fixing_submission(event, {"UL1": 101.0}),
            OPS_MAKER, session)
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


def _enable_auto_yahoo(session: Session, deal: Deal) -> Deal:
    deal.fixing_policy = FixingPolicy.AUTO_YAHOO.value
    session.add(deal); session.commit(); session.refresh(deal)
    return deal


def _yahoo_closes(deal: Deal, *, maturity_close: float | None = 100.0) -> dict:
    series = {deal.strike_date: 100.0}
    if maturity_close is not None:
        series[deal.maturity_date] = maturity_close
    return {
        "provider": "YAHOO_FINANCE",
        "price_type": "UNADJUSTED_CLOSE",
        "fetched_at": datetime.utcnow().isoformat(),
        "series": {"TK1": series},
        "splits": {"TK1": {}},
        "missing": [],
    }


def test_auto_yahoo_officializes_fixings_and_applies_terminal_lifecycle(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    maturity = _events(session, deal)[-1]
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes",
        lambda *args: _yahoo_closes(deal))
    monkeypatch.setattr(deals_api, "_evaluate_lifecycle", lambda *args: {
        "outcome": "final", "event_id": maturity.id,
        "event_date": maturity.event_date, "realized_payout": 1.0,
    })

    result = deals_api.refresh_deal_core(deal, session, actor_user_id=USER.id)

    refreshed = session.get(Deal, deal.id)
    events = _events(session, deal)
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_id == deal.id)).all()
    assert result["policy"] == "AUTO_YAHOO"
    assert result["officialized"] == 2
    assert result["proposal"]["status"] == "APPLIED"
    assert refreshed.status == "échu"
    assert refreshed.realized_payout == 1.0
    assert all(event.fixing_status == "APPLIED" for event in events)
    assert all(version.provider == "YAHOO_FINANCE" for version in versions)
    assert all(version.capture_actor_type == "PROCESS" for version in versions)
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "RESOLUTION_AUTO_APPLIED")).first()


def test_auto_yahoo_waits_for_same_day_close_without_manual_exception(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes",
        lambda *args: _yahoo_closes(deal, maturity_close=None))
    monkeypatch.setattr(
        deals_api, "_evaluate_lifecycle", lambda *args: {"outcome": "en_cours"})

    result = deals_api.refresh_deal_core(deal, session)

    strike, maturity = _events(session, deal)
    assert strike.fixing_status == "VALIDATED"
    assert maturity.fixing_status == "EXPECTED"
    assert result["exceptions"][0]["waiting_for_close"] is True
    assert result["exceptions"][0]["failures"][0]["code"] == "YAHOO_CLOSE_NOT_PUBLISHED"
    assert not session.exec(select(Alert).where(
        Alert.kind == "auto_fixing_exception")).first()


def test_auto_yahoo_revision_never_overwrites_an_official_fixing(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    _, maturity = _events(session, deal)
    maturity.event_date = (date.today() + timedelta(days=30)).isoformat()
    deal.maturity_date = maturity.event_date
    session.add(maturity); session.add(deal); session.commit()
    monkeypatch.setattr(
        deals_api, "_evaluate_lifecycle", lambda *args: {"outcome": "en_cours"})
    first_data = _yahoo_closes(deal, maturity_close=None)
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes", lambda *args: first_data)
    deals_api.refresh_deal_core(deal, session)
    strike = _events(session, deal)[0]
    assert json.loads(strike.spots_json) == {"UL1": 100.0}

    revised_data = _yahoo_closes(deal, maturity_close=None)
    revised_data["series"]["TK1"][deal.strike_date] = 101.0
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes", lambda *args: revised_data)
    result = deals_api.refresh_deal_core(deal, session)

    strike = _events(session, deal)[0]
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == strike.id)
        .order_by(OfficialFixingVersion.version)).all()
    assert json.loads(strike.spots_json) == {"UL1": 100.0}
    assert strike.fixing_status == "MANUAL_REVIEW_REQUIRED"
    assert [version.status for version in versions] == [
        "VALIDATED", "MANUAL_REVIEW_REQUIRED"]
    assert result["exceptions"][0]["failures"][0]["code"] == \
        "YAHOO_OFFICIAL_REVISION_DETECTED"


def test_auto_yahoo_never_bypasses_a_pending_human_exception(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    strike, maturity = _events(session, deal)
    maturity.event_date = (date.today() + timedelta(days=30)).isoformat()
    deal.maturity_date = maturity.event_date
    session.add(maturity); session.add(deal); session.commit()
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 100.0}),
        OPS_MAKER, session)
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes",
        lambda *args: _yahoo_closes(deal, maturity_close=None))
    monkeypatch.setattr(
        deals_api, "_evaluate_lifecycle", lambda *args: {"outcome": "en_cours"})

    result = deals_api.refresh_deal_core(deal, session)

    strike = _events(session, deal)[0]
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == strike.id)).all()
    assert len(versions) == 1
    assert versions[0].capture_actor_type == "USER"
    assert versions[0].status == "RECEIVED"
    assert strike.fixing_status == "MANUAL_REVIEW_REQUIRED"
    assert result["exceptions"][0]["failures"][0]["code"] == \
        "CONTROLLED_FIXING_PENDING"


def _resolve_auto_exception(
    session: Session,
    deal: Deal,
    event: DealEvent,
    *,
    action: str = "CONFIRM_CURRENT",
    spots: dict | None = None,
    source_reference: str = "UAT source contrôlée",
) -> dict:
    return deals_api.resolve_auto_fixing_exception(
        deal.id,
        event.id,
        deals_api.AutoFixingExceptionResolutionRequest(
            action=action,
            expected_version_id=event.current_fixing_version_id,
            spots=spots,
            source_reference=source_reference,
            reason="Décision utilisateur documentée pour le test",
        ),
        USER,
        session,
    )


def test_auto_exception_owner_can_confirm_pending_human_value():
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    strike, maturity = _events(session, deal)
    maturity.event_date = (date.today() + timedelta(days=30)).isoformat()
    deal.maturity_date = maturity.event_date
    session.add(maturity); session.add(deal); session.commit()
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 100.0}),
        OPS_MAKER, session)
    strike = session.get(DealEvent, strike.id)

    result = _resolve_auto_exception(session, deal, strike)

    strike = session.get(DealEvent, strike.id)
    versions = session.exec(select(OfficialFixingVersion).where(
        OfficialFixingVersion.deal_event_id == strike.id)
        .order_by(OfficialFixingVersion.version)).all()
    assert result["remaining_exceptions"] == 0
    assert strike.fixing_status == "VALIDATED"
    assert strike.data_category == "FIXING_OFFICIAL"
    assert strike.validated_by == USER.id
    assert [version.status for version in versions] == ["SUPERSEDED", "VALIDATED"]
    assert versions[-1].capture_actor_type == "USER"
    assert versions[-1].validated_by == USER.id
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "AUTO_FIXING_EXCEPTION_CONFIRM_CURRENT")).first()


def test_auto_exception_owner_can_explicitly_adopt_yahoo(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    strike, maturity = _events(session, deal)
    maturity.event_date = (date.today() + timedelta(days=30)).isoformat()
    deal.maturity_date = maturity.event_date
    session.add(maturity); session.add(deal); session.commit()
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 99.0}),
        OPS_MAKER, session)
    strike = session.get(DealEvent, strike.id)
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes",
        lambda *args: _yahoo_closes(deal, maturity_close=None))

    _resolve_auto_exception(session, deal, strike, action="USE_YAHOO")

    strike = session.get(DealEvent, strike.id)
    version = session.get(OfficialFixingVersion, strike.current_fixing_version_id)
    assert json.loads(strike.spots_json) == {"UL1": 100.0}
    assert version.provider == "YAHOO_FINANCE"
    assert version.capture_actor_type == "USER"
    assert version.validation_reason.startswith("Décision utilisateur")


def test_user_confirmed_non_yahoo_exception_is_not_reopened(monkeypatch):
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    strike, maturity = _events(session, deal)
    maturity.event_date = (date.today() + timedelta(days=30)).isoformat()
    deal.maturity_date = maturity.event_date
    session.add(maturity); session.add(deal); session.commit()
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 100.0}),
        OPS_MAKER, session)
    strike = session.get(DealEvent, strike.id)
    _resolve_auto_exception(session, deal, strike)
    revised = _yahoo_closes(deal, maturity_close=None)
    revised["series"]["TK1"][deal.strike_date] = 101.0
    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes", lambda *args: revised)
    monkeypatch.setattr(
        deals_api, "_evaluate_lifecycle", lambda *args: {"outcome": "en_cours"})

    result = deals_api.refresh_deal_core(deal, session, actor_user_id=USER.id)

    strike = session.get(DealEvent, strike.id)
    assert json.loads(strike.spots_json) == {"UL1": 100.0}
    assert json.loads(strike.indicative_spots_json) == {"UL1": 101.0}
    assert strike.fixing_status == "VALIDATED"
    assert result["exceptions"] == []


def test_auto_exception_resolution_is_refused_for_four_eyes_deal():
    session = _session(); deal = _deal(session); strike = _events(session, deal)[0]
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 100.0}),
        OPS_MAKER, session)
    strike = session.get(DealEvent, strike.id)

    with pytest.raises(HTTPException) as exc:
        _resolve_auto_exception(session, deal, strike)

    assert exc.value.status_code == 409
    assert exc.value.detail["failures"][0]["code"] == \
        "AUTO_EXCEPTION_POLICY_REQUIRED"


def test_last_user_exception_replays_and_applies_terminal_lifecycle():
    session = _session(); deal = _enable_auto_yahoo(session, _deal(session))
    strike, maturity = _events(session, deal)
    deals_api.update_event(
        deal.id, strike.id, _fixing_submission(strike, {"UL1": 100.0}),
        OPS_MAKER, session)
    deals_api.update_event(
        deal.id, maturity.id, _fixing_submission(maturity, {"UL1": 100.0}),
        OPS_MAKER, session)
    strike = session.get(DealEvent, strike.id)
    maturity = session.get(DealEvent, maturity.id)

    first = _resolve_auto_exception(session, deal, strike)
    second = _resolve_auto_exception(session, deal, maturity)

    refreshed = session.get(Deal, deal.id)
    assert first["remaining_exceptions"] == 1
    assert second["remaining_exceptions"] == 0
    assert second["lifecycle_proposal"]["status"] == "APPLIED"
    assert refreshed.status == "échu"
    assert all(event.fixing_status == "APPLIED" for event in _events(session, deal))


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
                reason="revue ops", confirmed_outcome="final"), CHECKER, session)
    assert exc.value.status_code == 422


def _validate_all_fixings(session: Session, deal: Deal) -> None:
    for event in _events(session, deal):
        deals_api.update_event(
            deal.id, event.id, _fixing_submission(event, {"UL1": 100.0}),
            OPS_MAKER, session)
        deals_api.validate_fixing(
            deal.id, event.id,
            deals_api.FixingValidationRequest(reason="source officielle"),
            CHECKER, session)


def test_resolution_validation_requires_explicit_outcome_confirmation():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(reason="revue payoff"), CHECKER, session)
    failures = exc.value.detail["failures"]
    assert any(failure["code"] == "OUTCOME_CONFIRMATION_REQUIRED" for failure in failures)


def test_resolution_authorization_and_application_are_atomic():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    validated = deals_api.validate_lifecycle_proposal(
        deal.id, proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="revue payoff", confirmed_outcome="final"), CHECKER, session)
    session.refresh(deal)
    assert validated["proposal"]["status"] == "APPLIED"
    assert validated["deal"]["status"] == "échu"
    assert deal.status == "échu"
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "RESOLUTION_VALIDATED")).first()
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "RESOLUTION_APPLIED")).first()


def test_resolution_application_is_exactly_once():
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    deals_api.validate_lifecycle_proposal(
        deal.id, proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="revue payoff", confirmed_outcome="final"), CHECKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.apply_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(reason="seconde application"),
            CHECKER, session)
    assert exc.value.status_code == 409
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "RESOLUTION_APPLICATION_REJECTED")).first()


def test_resolution_rolls_back_authorization_and_application_if_audit_fails(monkeypatch):
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    original_record_audit = deals_api.record_audit_event

    def fail_on_resolution_applied(*args, **kwargs):
        if kwargs.get("action") == "RESOLUTION_APPLIED":
            raise RuntimeError("audit unavailable")
        return original_record_audit(*args, **kwargs)

    monkeypatch.setattr(deals_api, "record_audit_event", fail_on_resolution_applied)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        deals_api.validate_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="autorisation avec audit obligatoire",
                confirmed_outcome="final"),
            CHECKER, session)
    session.rollback()
    assert session.get(Deal, deal.id).status == "actif"
    assert session.get(LifecycleProposal, proposal.id).status == "PROPOSED"
    assert all(event.fixing_status == "VALIDATED" for event in _events(session, deal))


def test_resolution_rejection_rolls_back_the_intermediate_authorization(monkeypatch):
    session = _session(); deal = _deal(session); proposal = _proposal(session, deal)
    _validate_all_fixings(session, deal)
    original_hash = deals_api.official_input_hash
    hash_calls = 0

    def changing_hash(*args, **kwargs):
        nonlocal hash_calls
        hash_calls += 1
        if hash_calls == 1:
            return original_hash(*args, **kwargs)
        return "inputs-modifiés-entre-autorisation-et-application"

    monkeypatch.setattr(deals_api, "official_input_hash", changing_hash)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id, proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="autorisation soumise au contrôle de staleness",
                confirmed_outcome="final"),
            CHECKER, session)
    assert exc.value.detail["code"] == "RESOLUTION_APPLICATION_REJECTED"
    assert session.get(Deal, deal.id).status == "actif"
    assert session.get(LifecycleProposal, proposal.id).status == "PROPOSED"
    assert all(event.fixing_status == "VALIDATED" for event in _events(session, deal))
    actions = [audit.action for audit in session.exec(select(AuditEvent)).all()]
    assert "RESOLUTION_VALIDATED" not in actions
    assert actions.count("RESOLUTION_APPLICATION_REJECTED") == 1


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
