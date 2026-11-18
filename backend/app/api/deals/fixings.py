"""Manual fixings: event edits, official evidence, validation and rejection."""
from __future__ import annotations
import base64
import binascii
import json
import hashlib
import re
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...db.models import DealEvent, User, LifecycleProposal, OfficialFixingVersion
from ..auth import get_current_user
from ...services.market_data import market_data_provider_for_deal
from ...core.audit import commit_rejection, record_audit_event
from ...core.workflow import DataCategory, FixingStatus, LifecycleStatus
from ...services.product_lifecycle import stage_product_lifecycle
from ._router import router
from .common import _ensure_alert, _ops_deal, _reject_workflow_action, _workflow_failure
from .serializers import _event_row
from .fixing_controls import EventUpdate, _fixing_record_hash, _fixing_record_payload, _fixing_submission_failures, _spot_failures

class FixingValidationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


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
            message="Le propriétaire économique du deal ne peut pas saisir ses observations contractuelles.",
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

    submission_failures, observed = _fixing_submission_failures(
        deal, ev, body, market_data_provider_for_deal(deal, session))
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
    stage_product_lifecycle(
        session, deal, actor_user_id=current.id,
        action="PRODUCT_FIXING_RECEIVED",
        reason=version.capture_reason,
    )
    session.commit()
    session.refresh(ev)
    return _event_row(ev)


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
            action="Demandez à un Ops Maker de saisir l’observation et sa pièce source.",
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
    if ev.event_date > business_today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_DATE_IN_FUTURE",
            "event_date",
            "La date contractuelle du fixing est encore future.",
            expected="Une date d’événement atteinte.",
            action="Attendez la date contractuelle de constatation.",
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
    stage_product_lifecycle(
        session, deal, actor_user_id=current.id,
        action="PRODUCT_FIXING_VALIDATED",
        reason=body.reason,
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
                message="Rejet non appliqué — la version validée précédente ne peut pas être restaurée sûrement.",
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
    stage_product_lifecycle(
        session, deal, actor_user_id=current.id,
        action="PRODUCT_FIXING_REJECTED",
        reason=body.reason,
    )
    session.commit()
    session.refresh(ev)
    return _event_row(ev)
