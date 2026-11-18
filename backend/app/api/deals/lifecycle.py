"""Lifecycle evaluation, refresh and proposals (validation, application)."""
from __future__ import annotations
import json
from datetime import datetime
from typing import Annotated, Literal, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...db.models import Deal, DealEvent, User, LifecycleProposal, OfficialFixingVersion
from ..auth import get_current_user
from ...core.audit import commit_rejection, record_audit_event
from ...core.lifecycle_controls import official_input_hash, replay_official_fixings
from ...core.workflow import DataCategory, FixingPolicy, FixingStatus, LifecycleStatus
from ...services.product_lifecycle import stage_product_lifecycle
from ...services.business_access import can_read_deal as _can_access_deal
from ._router import router
from .common import _ensure_alert, _ops_deal, _reject_workflow_action, _workflow_failure
from .serializers import _deal_row, _event_row, _get_events, _proposal_row
from .fixing_controls import _spot_failures
from .lifecycle_rules import _payout_reconciliation_tolerance, _terminal_deal_state
from .auto_fixings import _refresh_auto_yahoo_deal_core

class LifecycleValidationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    confirmed_outcome: Optional[Literal["callé", "ki", "final"]] = None


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
                f"lifecycle-error:{deal_id}:{business_today().isoformat()}:{type(exc).__name__}",
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

    if deal.fixing_policy != FixingPolicy.AUTO_YAHOO.value:
        previous_policy = deal.fixing_policy
        deal.fixing_policy = FixingPolicy.AUTO_YAHOO.value
        session.add(deal)
        record_audit_event(
            session,
            action="FIXING_POLICY_AUTOMATED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=actor_user_id,
            actor_type="USER" if actor_user_id else "PROCESS",
            result="SUCCESS",
            before={"fixing_policy": previous_policy},
            after={"fixing_policy": FixingPolicy.AUTO_YAHOO.value},
            reason="Retrait du workflow Maker/Checker ; les clôtures fournisseur contrôlées deviennent officielles automatiquement.",
            data_source=DataCategory.FIXING_OFFICIAL,
        )
    return _refresh_auto_yahoo_deal_core(
        deal, session, actor_user_id, underlyings, tickers)


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
            expected="L’identifiant de l’événement où le rejeu des observations validées s’arrête.",
            action="Recalculez la proposition depuis le calendrier contractuel gelé.",
            received=proposal.event_id,
        ))
        return required_events, failures
    for event in required_events:
        event_failures = [
            _workflow_failure(
                spot_failure["code"],
                f"spots.{spot_failure.get('underlying', '')}".rstrip("."),
                "L’observation validée est incomplète ou contient une valeur invalide.",
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
                "La donnée requise est encore indicative ou candidate, et n’a pas été validée.",
                expected=DataCategory.FIXING_OFFICIAL.value,
                action="Soumettez une pièce source puis faites valider l’observation.",
                received=event.data_category,
            ))
        version = (
            session.get(OfficialFixingVersion, event.current_fixing_version_id)
            if event.current_fixing_version_id else None
        )
        if not version:
            event_failures.append(_workflow_failure(
                "FIXING_PROVENANCE_MISSING", "current_fixing_version_id",
                "L’observation ne possède pas de pièce source versionnée.",
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
                    "Le résultat validé diverge de la proposition indicative.",
                    expected=official_result.get("outcome"),
                    action="Rejetez la proposition indicative et générez une proposition réconciliée depuis les observations validées.",
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
                            "Le payout indicatif diverge du payout validé au-delà de la tolérance monétaire.",
                            expected=(
                                f"Écart ≤ {normalized_tolerance:.12g} du nominal "
                                f"(soit {monetary_tolerance:.6g} {deal.devise})."),
                            action="Rejetez la proposition indicative et générez une proposition réconciliée depuis les observations validées.",
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
            "Aucun rejeu validé gelé n’est attaché à l’autorisation.",
            expected="Un résultat validé et son hash d’inputs.",
            action="Reprenez l’autorisation Checker depuis une proposition PROPOSED.",
        ))
    elif not fixing_failures:
        current_official_hash = official_input_hash(deal, required_events)
        if current_official_hash != proposal.official_input_hash:
            failures.append(_workflow_failure(
                "OFFICIAL_REPLAY_STALE", "official_input_hash",
                "Les observations validées ont changé depuis l’autorisation.",
                expected="Le hash d’inputs gelé lors de l’autorisation.",
                action="Marquez cette proposition STALE et produisez un nouveau rejeu validé.",
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
                "Le rejeu validé ne produit pas un événement économique terminal supporté.",
                expected="callé, ki ou final",
                action="Corrigez le script ou attendez un événement contractuel terminal.",
                received=outcome,
            )], 422)
    trigger = next(event for event in required_events if event.id == proposal.event_id)
    all_events = _get_events(deal.id, session)
    trigger.status = outcome
    target_deal_status, settlement_amount = _terminal_deal_state(
        deal, outcome, result, business_today())
    deal_cas = session.exec(
        update(Deal)
        .where(Deal.id == deal.id, Deal.status == "actif")
        .values(
            status=target_deal_status,
            realized_payout=result.get("realized_payout"),
            settlement_amount=settlement_amount,
            resolution_outcome=outcome,
            settlement_date=result.get('settlement_date'),
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
    stage_product_lifecycle(
        session, deal, actor_user_id=current.id,
        action="PRODUCT_LIFECYCLE_RESOLUTION_APPLIED",
        reason=body.reason,
    )
    session.commit()
    session.refresh(deal)
    session.refresh(proposal)
    return {"deal": _deal_row(deal, _get_events(deal.id, session), session),
            "proposal": _proposal_row(proposal)}
