"""Phase 2 controls: official replay, semantic outcome and maker-checker."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import alerts as alerts_api
from backend.app.api import deals as deals_api
from backend.app.core.lifecycle_controls import (
    replay_official_fixings, semantic_maturity_outcome,
)
from backend.app.core.payscript.parser import parse_script
from backend.app.core.workflow import DataCategory, FixingStatus
from backend.app.db.models import (
    Alert, AuditEvent, Client, ClientMandate, Deal, DealContractVersion,
    DealEvent, LifecycleProposal, OfficialFixingVersion, TradeAmendmentRequest,
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
        evidence_payload = f"Preuve officielle {index}".encode("utf-8")
        evidence_sha256 = hashlib.sha256(evidence_payload).hexdigest()
        event = DealEvent(
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
            fixing_version=1,
            fixing_entered_by=4,
            fixing_entered_at=datetime.utcnow(),
            fixing_provider="BLOOMBERG",
            fixing_source_type="MESSAGE",
            fixing_external_reference=f"MSG-{index}",
            fixing_observed_at=datetime.utcnow(),
            fixing_venue="Official close",
            fixing_calendar="TARGET",
            fixing_timezone="UTC",
            fixing_evidence_sha256=evidence_sha256,
            fixing_record_sha256="b" * 64,
            fixing_reason="Capture officielle documentée",
            validated_by=2,
            validated_at=datetime.utcnow(),
        )
        session.add(event)
        session.flush()
        version = OfficialFixingVersion(
            deal_id=deal.id,
            deal_event_id=event.id,
            version=1,
            status=FixingStatus.VALIDATED,
            spots_json=json.dumps({"UL1": spot}),
            provider="BLOOMBERG",
            source_type="MESSAGE",
            external_reference=f"MSG-{index}",
            observed_at=datetime.utcnow(),
            venue="Official close",
            calendar="TARGET",
            timezone="UTC",
            evidence_sha256=evidence_sha256,
            evidence_filename=f"fixing-{index}.txt",
            evidence_content_type="text/plain",
            evidence_size_bytes=len(evidence_payload),
            evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
            record_sha256="b" * 64,
            capture_reason="Capture officielle documentée",
            entered_by=4,
            validated_by=2,
            validated_at=datetime.utcnow(),
        )
        session.add(version)
        session.flush()
        event.current_fixing_version_id = version.id
        session.add(event)
    session.commit()
    session.refresh(deal)
    return deal


def _events(session: Session, deal: Deal) -> list[DealEvent]:
    return session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id).order_by(DealEvent.event_index)).all()


def _proposal(
    session: Session,
    deal: Deal,
    outcome: str = "final",
    payout: float = 1.0,
) -> LifecycleProposal:
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
            "realized_payout": payout,
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


def test_partial_official_fixing_prefix_cannot_manufacture_maturity():
    session = _session()
    deal = _deal(session)

    result, failures = replay_official_fixings(deal, _events(session, deal)[:1])

    assert failures == []
    assert result["outcome"] == "en_cours"
    assert result["event_date"] == deal.strike_date
    assert result["realized_payout"] == 0.0


def test_auto_yahoo_refresh_uses_official_replay_as_lifecycle_truth(monkeypatch):
    session = _session()
    deal = _deal(session)
    captured = {}

    monkeypatch.setattr(
        deals_api, "load_yahoo_reference_closes",
        lambda *_args, **_kwargs: {"provider": "test"},
    )
    monkeypatch.setattr(
        deals_api, "_auto_validate_yahoo_event",
        lambda *_args, **_kwargs: (False, None),
    )
    monkeypatch.setattr(
        deals_api, "_reference_history_arrays",
        lambda *_args, **_kwargs: ([deal.strike_date], {"TK1": [100.0]}),
    )
    monkeypatch.setattr(
        deals_api, "replay_official_fixings",
        lambda _deal, events: ({
            "outcome": "en_cours",
            "event_id": events[-1].id,
            "event_date": events[-1].event_date,
            "realized_payout": 0.0,
        }, []),
    )
    monkeypatch.setattr(
        deals_api, "_evaluate_lifecycle",
        lambda *_args, **_kwargs: {"outcome": "final", "realized_payout": 0.25},
    )

    def capture_apply(_deal, evaluation, _session, _actor_user_id):
        captured["evaluation"] = evaluation
        return None

    monkeypatch.setattr(deals_api, "_auto_apply_lifecycle", capture_apply)

    response = deals_api._refresh_auto_yahoo_deal_core(
        deal, session, actor_user_id=99,
        underlyings=[{"name": "UL1", "ticker": "TK1"}],
        tickers=["TK1"],
    )

    assert captured["evaluation"]["outcome"] == "en_cours"
    assert response["evaluation"]["outcome"] == "en_cours"


def test_admin_can_run_mtm_and_greeks_on_a_foreign_uat_deal(monkeypatch):
    session = _session()
    deal = _deal(session)
    admin = SimpleNamespace(id=99, entity_id=None, role="admin")
    payload = {"resolved_pending": True, "message": "fixture"}
    monkeypatch.setattr(
        deals_api, "_mtm_core",
        lambda *_args, **_kwargs: (payload, None),
    )

    assert deals_api.deal_mtm(deal.id, admin, session) == payload
    assert deals_api.deal_greeks(deal.id, admin, session) == payload


def test_admin_book_refresh_and_alerts_cover_uat_target_users(monkeypatch):
    session = _session()
    session.add(Alert(
        user_id=1, deal_id=None, deal_reference="UAT-TARGET",
        kind="test", message="foreign alert", dedup_key="foreign-alert",
    ))
    session.commit()
    admin = SimpleNamespace(id=99, entity_id=None, role="admin")
    captured = {}

    def fake_refresh(_session, user_id):
        captured["user_id"] = user_id
        return {"deals": 1}

    monkeypatch.setattr(alerts_api, "refresh_book", fake_refresh)

    assert alerts_api.refresh_whole_book(admin, session) == {"deals": 1}
    assert captured["user_id"] is None
    assert alerts_api.list_alerts(admin, session)["alerts"][0]["deal_reference"] \
        == "UAT-TARGET"


def test_admin_watchlist_includes_foreign_uat_deals(monkeypatch):
    session = _session()
    deal = _deal(session)
    admin = SimpleNamespace(id=99, entity_id=None, role="admin")
    regular_user = SimpleNamespace(id=99, entity_id=None, role="user")
    monkeypatch.setattr(
        deals_api, "build_watchlist_row",
        lambda row, _session, _today: {
            "id": row.id, "min_gap": None, "days_to_next": None,
        },
    )

    assert [row["id"] for row in deals_api.watchlist(admin, session)] == [deal.id]
    assert [row["id"] for row in deals_api.watchlist(MAKER, session)] == [deal.id]
    assert deals_api.watchlist(regular_user, session) == []


def test_watchlist_filters_on_commercial_ids_without_requiring_them(monkeypatch):
    """Clients narrows the existing lifecycle view; an unfiltered call keeps
    the product-only behaviour unchanged."""
    session = _session()
    client = Client(name="ABC AM", entity_id=7, status="active")
    session.add(client); session.flush()
    mandate = ClientMandate(
        client_id=client.id, name="Fonds Rendement", status="active")
    session.add(mandate); session.flush()
    deal = _deal(session)
    deal.client_id = client.id
    deal.mandate_id = mandate.id
    session.add(deal); session.commit()
    admin = SimpleNamespace(id=99, entity_id=None, role="admin")
    monkeypatch.setattr(
        deals_api, "build_watchlist_row",
        lambda row, _session, _today: {
            "id": row.id, "min_gap": None, "days_to_next": None,
        },
    )

    assert [row["id"] for row in deals_api.watchlist(admin, session)] == [deal.id]
    assert [row["id"] for row in deals_api.watchlist(
        admin, session, client_id=client.id)] == [deal.id]
    assert deals_api.watchlist(admin, session, client_id=client.id + 999) == []
    assert [row["id"] for row in deals_api.watchlist(
        admin, session, client_id=client.id, mandate_id=mandate.id)] == [deal.id]
    assert deals_api.watchlist(
        admin, session, client_id=client.id, mandate_id=mandate.id + 999) == []


def test_watchlist_row_exposes_commercial_ids_without_changing_counterparty():
    session = _session()
    deal = Deal(
        reference="DEAL-COMMERCIAL-PROJECTION", entity_id=7, user_id=1,
        client_id=12, mandate_id=34, status="actif", contrepartie="Issuer SA",
        underlyings_json="[]", script_snapshot="")
    session.add(deal); session.commit(); session.refresh(deal)

    row = deals_api.build_watchlist_row(deal, session, date.today())

    assert row["client_id"] == 12
    assert row["mandate_id"] == 34
    assert row["contrepartie"] == "Issuer SA"


def test_validation_freezes_official_replay_and_application_uses_it():
    session = _session()
    deal = _deal(session)
    proposal = _proposal(session, deal, payout=0.25)
    validated = deals_api.validate_lifecycle_proposal(
        deal.id,
        proposal.id,
        deals_api.LifecycleValidationRequest(
            reason="Rejeu officiel contrôlé", confirmed_outcome="final"),
        CHECKER,
        session,
    )
    assert validated["proposal"]["comparison_status"] == "MATCH"
    assert validated["proposal"]["official_result"]["realized_payout"] == 0.25
    assert validated["proposal"]["official_input_hash"]
    assert validated["proposal"]["status"] == "APPLIED"
    assert validated["deal"]["realized_payout"] == 0.25
    assert validated["deal"]["resolution_outcome"] == "final"


def test_payout_difference_above_currency_tolerance_blocks_authorization():
    session = _session()
    deal = _deal(session)
    proposal = _proposal(session, deal, payout=1.0)
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id,
            proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="Réconciliation payout officielle",
                confirmed_outcome="final"),
            CHECKER,
            session,
        )
    failure = next(row for row in exc.value.detail["failures"]
                   if row["code"] == "OFFICIAL_INDICATIVE_PAYOUT_MISMATCH")
    assert failure["field"] == "proposal.result.realized_payout"
    assert "EUR" in failure["expected"]
    assert failure["action"]


def test_deal_owner_cannot_authorize_own_lifecycle_resolution():
    session = _session()
    deal = _deal(session)
    proposal = _proposal(session, deal)
    owner_as_checker = SimpleNamespace(id=deal.user_id, entity_id=7, role="checker")
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id,
            proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="Auto-validation propriétaire interdite",
                confirmed_outcome="final"),
            owner_as_checker,
            session,
        )
    assert exc.value.detail["failures"][0]["code"] == \
        "DEAL_OWNER_CANNOT_VALIDATE_LIFECYCLE"


def test_fixing_maker_cannot_authorize_resolution_that_consumes_own_fixing():
    session = _session()
    deal = _deal(session)
    proposal = _proposal(session, deal)
    fixing_maker_as_checker = SimpleNamespace(id=4, entity_id=7, role="checker")
    with pytest.raises(HTTPException) as exc:
        deals_api.validate_lifecycle_proposal(
            deal.id,
            proposal.id,
            deals_api.LifecycleValidationRequest(
                reason="Contrôle indépendant obligatoire",
                confirmed_outcome="final"),
            fixing_maker_as_checker,
            session,
        )
    nested = [child for failure in exc.value.detail["failures"]
              for child in failure.get("failures", [])]
    assert any(row["code"] == "FOUR_EYES_VIOLATION" for row in nested)


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
                CHECKER,
            session,
        )
    assert any(row["code"] == "OFFICIAL_INDICATIVE_OUTCOME_MISMATCH"
               for row in exc.value.detail["failures"])


@pytest.fixture
def four_eyes_armed(monkeypatch):
    """Réarme la deuxième signature sur les amendements.

    Depuis le 07/08/2026 le contrôle est désactivé par défaut (poste
    mono-opérateur : voir core/workflow.py:amendment_four_eyes_enabled). Le
    mécanisme reste entièrement en place et doit rester testé, sinon il pourrira
    en silence et ne sera plus réarmable le jour où le desk se dédouble.
    """
    monkeypatch.setenv("STRUCTURA_AMENDMENT_FOUR_EYES", "1")


def test_amendment_requires_four_eyes_and_applies_exactly_once(four_eyes_armed):
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


def test_commercial_attribution_always_requires_four_eyes(monkeypatch):
    """Commercial rectification keeps the initial booking snapshot immutable.

    This control stays armed even on a mono-operator deployment where ordinary
    amendments may be self-carried.
    """
    monkeypatch.delenv("STRUCTURA_AMENDMENT_FOUR_EYES", raising=False)
    session = _session()
    deal = _deal(session)
    client = Client(name="Client rectifié", entity_id=7, data_origin="native")
    session.add(client)
    session.flush()
    mandate = ClientMandate(
        entity_id=7, client_id=client.id, mandate_type="account",
        name="Compte principal", status="active", data_origin="native",
        created_by_user_id=1,
    )
    session.add(mandate)
    session.commit()

    requested = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="commercial_attribution",
            new_value={
                "client_id": client.id,
                "mandate_id": mandate.id,
                "opportunity_id": None,
                "primary_affiliation_id": None,
            },
            reason="Correction de l'attribution commerciale documentée",
        ),
        MAKER,
        session,
    )
    self_checker = SimpleNamespace(id=1, entity_id=7, role="checker")
    with pytest.raises(HTTPException) as exc:
        deals_api.approve_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Auto-validation interdite"),
            self_checker, session,
        )
    assert exc.value.detail["code"] == "FOUR_EYES_VIOLATION"

    deals_api.approve_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Attribution contrôlée indépendamment"),
        CHECKER, session,
    )
    result = deals_api.apply_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Application de la correction contrôlée"),
        CHECKER, session,
    )
    assert result["deal"]["client_id"] == client.id
    assert result["deal"]["mandate_id"] == mandate.id
    assert result["deal"]["client_provenance"] is None
    assert result["deal"]["client_attribution_current"]["client"]["name"] == "Client rectifié"


def test_amendment_is_carried_through_by_its_own_maker_by_default():
    """Mode par défaut : une seule signature, mais toutes les autres garanties.

    Le maker ouvre, approuve et applique. Ce qui ne bouge pas : la machine à
    états (une demande APPLIED ne se rejoue pas), le versionnement contractuel,
    et la piste d'audit.
    """
    session = _session()
    deal = _deal(session)
    requested = deals_api.request_amendment(
        deal.id,
        deals_api.AmendmentRequestCreate(
            field_name="nominal", new_value=2_000_000,
            reason="Correction contractuelle documentée"),
        MAKER, session)

    approved = deals_api.approve_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Décision du propriétaire du deal"),
        MAKER, session)
    assert approved["status"] == "APPROVED"

    result = deals_api.apply_amendment(
        deal.id, requested["id"],
        deals_api.AmendmentDecisionRequest(reason="Application par le propriétaire"),
        MAKER, session)
    assert result["deal"]["nominal"] == 2_000_000
    assert result["deal"]["contract_version"] == 2
    assert result["amendment"]["status"] == "APPLIED"
    assert len(session.exec(select(DealContractVersion)).all()) == 2

    # L'idempotence ne dépendait pas de la deuxième signature.
    with pytest.raises(HTTPException) as duplicate:
        deals_api.apply_amendment(
            deal.id, requested["id"],
            deals_api.AmendmentDecisionRequest(reason="Deuxième application interdite"),
            MAKER, session)
    assert duplicate.value.detail["code"] == "AMENDMENT_STATUS_INVALID"

    # Et la trace reste écrite, motif compris.
    applied = session.exec(select(AuditEvent).where(
        AuditEvent.action == "AMENDMENT_APPLIED")).first()
    assert applied is not None
    assert applied.actor_user_id == MAKER.id


def test_single_signature_mode_still_refuses_a_foreign_user():
    """Retirer la deuxième signature n'ouvre pas le deal à un tiers."""
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
            deals_api.AmendmentDecisionRequest(reason="Utilisateur d'une autre entité"),
            OTHER_CHECKER, session)
    assert exc.value.status_code == 404


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
