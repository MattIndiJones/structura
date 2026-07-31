"""Phase 2 controls: official replay, semantic outcome and maker-checker."""
from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.core.lifecycle_controls import (
    replay_official_fixings, semantic_maturity_outcome,
)
from backend.app.core.payscript.parser import parse_script
from backend.app.core.workflow import DataCategory, FixingStatus
from backend.app.db.models import (
    AuditEvent, Deal, DealContractVersion, DealEvent, LifecycleProposal,
    TradeAmendmentRequest,
)


MAKER = SimpleNamespace(id=1, entity_id=7, role="user")
CHECKER = SimpleNamespace(id=2, entity_id=7, role="checker")
OTHER_CHECKER = SimpleNamespace(id=3, entity_id=8, role="checker")


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _deal(session: Session, script: str = "AT MATURITY\n  PAY 0.25") -> Deal:
    today = date.today()
    deal = Deal(
        reference="DEAL-PHASE2-001",
        entity_id=7,
        user_id=1,
        script_snapshot=script,
        sens="vente",
        contrepartie="Bank",
        devise="EUR",
        nominal=1_000_000,
        fair_value=99.0,
        price_traded=99.1,
        trade_date=(today - timedelta(days=2)).isoformat(),
        strike_date=(today - timedelta(days=1)).isoformat(),
        value_date=(today - timedelta(days=1)).isoformat(),
        maturity_date=today.isoformat(),
        payment_date=(today + timedelta(days=2)).isoformat(),
        T=1 / 252,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1"}]),
        market_snapshot_json=json.dumps({"r": 3.0, "user_params": {}, "constats": {}}),
        status="actif",
        contract_version=1,
    )
    session.add(deal)
    session.flush()
    for index, (event_date, t_years, spot) in enumerate([
        (deal.strike_date, 0.0, 100.0),
        (deal.maturity_date, deal.T, 100.0),
    ]):
        session.add(DealEvent(
            deal_id=deal.id,
            event_index=index,
            event_date=event_date,
            t_years=t_years,
            spots_json=json.dumps({"UL1": spot}),
            fixing_status=FixingStatus.VALIDATED,
            data_category=DataCategory.FIXING_OFFICIAL,
            source="manuel",
            status="observé",
            label="Strike" if index == 0 else "Maturité",
        ))
    session.commit()
    session.refresh(deal)
    return deal


def _events(session: Session, deal: Deal) -> list[DealEvent]:
    return session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id).order_by(DealEvent.event_index)).all()


def _proposal(session: Session, deal: Deal, outcome: str = "final") -> LifecycleProposal:
    maturity = _events(session, deal)[-1]
    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=maturity.id,
        dedup_key=f"phase2:{deal.id}:{outcome}",
        status="PROPOSED",
        proposed_outcome=outcome,
        result_json=json.dumps({
            "outcome": outcome,
            "event_id": maturity.id,
            "event_date": maturity.event_date,
            "realized_payout": 1.0,
        }),
        data_source=DataCategory.INDICATIVE,
    )
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


def test_maturity_label_is_semantic_not_a_payout_threshold():
    compiled = parse_script("AT MATURITY\n  PAY 0.25")
    outcome, basis = semantic_maturity_outcome(compiled, {"state": {"memo": {}}})
    assert outcome == "final"
    assert basis == "MATURITY_NO_EXPLICIT_KI_STATE"


def test_explicit_script_ki_state_drives_the_label():
    compiled = parse_script(
        "PARAM M_KI_BAR = 60%\nAT MATURITY\n"
        "  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY WOF")
    outcome, basis = semantic_maturity_outcome(
        compiled, {"state": {"memo": {"M_KI_BAR": 0.6, "KI": 1.0}}})
    assert outcome == "ki"
    assert "KI" in basis


def test_path_dependent_official_replay_fails_closed():
    session = _session()
    deal = _deal(session, "PARAM B = 60%\nAT MATURITY\n  PAY INDIC(WOF_MIN < B)")
    result, failures = replay_official_fixings(deal, _events(session, deal))
    assert result is None
    assert failures[0]["code"] == "OFFICIAL_PATH_REQUIRED"


def test_validation_freezes_official_replay_and_application_uses_it():
    session = _session()
    deal = _deal(session)
    proposal = _proposal(session, deal)
    validated = deals_api.validate_lifecycle_proposal(
        deal.id,
        proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="Rejeu officiel contrôlé", confirmed_outcome="final"),
        MAKER,
        session,
    )
    assert validated["comparison_status"] == "OUTCOME_MATCH_PAYOUT_DIFFERENCE"
    assert validated["official_result"]["realized_payout"] == 0.25
    assert validated["official_input_hash"]

    applied = deals_api.apply_lifecycle_proposal(
        deal.id,
        proposal.id,
        deals_api.LifecycleValidationRequest(reason="Application officielle"),
        MAKER,
        session,
    )
    assert applied["deal"]["realized_payout"] == 0.25
    assert applied["deal"]["resolution_outcome"] == "final"


def test_official_indicative_outcome_mismatch_blocks_validation():
    session = _session()
    script = (
        "PARAM M_KI_BAR = 60%\nAT MATURITY\n"
        "  SET KI = INDIC(WOF < M_KI_BAR)\n"
        "  PAY (1 - KI) * 1\n  PAY KI * WOF")
    deal = _deal(session, script)
    maturity = _events(session, deal)[-1]
    maturity.spots_json = json.dumps({"UL1": 50.0})
    session.add(maturity)
    session.commit()
    proposal = _proposal(session, deal, "final")
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id,
            proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="Contrôle divergence", confirmed_outcome="final"),
            MAKER,
            session,
        )
    assert any(row["code"] == "OFFICIAL_INDICATIVE_OUTCOME_MISMATCH"
               for row in exc.value.detail["failures"])


def test_amendment_requires_four_eyes_and_applies_exactly_once():
    session = _session()
    deal = _deal(session)
    requested = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal",
            new_value=2_000_000,
            reason="Correction contractuelle documentée"),
        MAKER,
        session,
    )
    self_checker = SimpleNamespace(id=1, entity_id=7, role="checker")
    with pytest.raises(HTTPException) as exc:
        deals_api.approve_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Auto-validation interdite"),
            self_checker, session)
    assert exc.value.detail["code"] == "FOUR_EYES_VIOLATION"

    approved = deals_api.approve_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Contrôle quatre yeux effectué"),
        CHECKER, session)
    assert approved["status"] == "APPROVED"
    result = deals_api.apply_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Application après approbation"),
        CHECKER, session)
    assert result["deal"]["nominal"] == 2_000_000
    assert result["deal"]["contract_version"] == 2
    assert result["amendment"]["status"] == "APPLIED"
    assert len(session.exec(select(DealContractVersion)).all()) == 2

    with pytest.raises(HTTPException) as duplicate:
        deals_api.apply_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Deuxième application interdite"),
            CHECKER, session)
    assert duplicate.value.detail["code"] == "AMENDMENT_STATUS_INVALID"


def test_amendment_checker_is_entity_scoped():
    session = _session()
    deal = _deal(session)
    requested = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal", new_value=2_000_000,
            reason="Correction contractuelle documentée"),
        MAKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.approve_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Mauvaise entité juridique"),
            OTHER_CHECKER, session)
    assert exc.value.status_code == 404


def test_pricing_or_calendar_amendment_requires_rebooking():
    session = _session()
    deal = _deal(session)
    requested = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="script_snapshot", new_value="AT MATURITY\n  PAY 1",
            reason="Modification économique documentée"),
        MAKER, session)
    with pytest.raises(HTTPException) as exc:
        deals_api.approve_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Revue changement économique"),
            CHECKER, session)
    assert exc.value.detail["code"] == "AMENDMENT_REBOOK_REQUIRED"
    assert session.get(TradeAmendmentRequest, requested["id"]).status == "PENDING"
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "AMENDMENT_APPROVAL_REJECTED")).first()


def test_deal_audit_timeline_is_owner_scoped_and_filterable():
    session = _session()
    deal = _deal(session)
    deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal", new_value=2_000_000,
            reason="Correction contractuelle documentée"),
        MAKER, session)
    timeline = deals_api.get_deal_audit(
        deal.id, MAKER, session, action="AMENDMENT_REQUESTED", limit=10)
    assert timeline["count"] == 1
    assert timeline["items"][0]["action"] == "AMENDMENT_REQUESTED"
    with pytest.raises(HTTPException):
        deals_api.get_deal_audit(deal.id, OTHER_CHECKER, session)
