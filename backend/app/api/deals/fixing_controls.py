"""Fixing evidence, official observation checks and spot controls."""
from __future__ import annotations
import base64
import binascii
import json
import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from ...runtime import business_today
from ...core.access import has_business_role
from ...db.models import Deal, DealEvent, User, TradeAmendmentRequest
from ...core.audit import commit_rejection
from ...core.workflow import amendment_four_eyes_enabled
from ...services.business_access import deal_entity_id as _deal_entity_id, can_read_deal as _can_access_deal
from .common import _workflow_failure
from .serializers import _amendment_row

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


_FIXING_SOURCE_TYPES = {
    "API", "MESSAGE", "FILE", "PLATFORM", "CALCULATION_AGENT", "OTHER",
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
            action="Sélectionnez à nouveau la pièce source.",
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
            action="Sélectionnez à nouveau la pièce source.",
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
                action="Sélectionnez le message, fichier ou export reçu de la source.",
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
            action="Renseignez le timestamp publié par la source de données.",
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
    expected_provider: str,
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
    if provider != expected_provider:
        failures.append(_workflow_failure(
            "FIXING_PROVIDER_NOT_AUTHORIZED",
            "provider",
            "Le fournisseur ne correspond pas à la source de données du compte client.",
            expected=expected_provider,
            action="Utilisez la source configurée sur le compte client.",
            received=body.provider or None,
        ))
    source_type = str(body.source_type or "").strip().upper()
    if source_type not in _FIXING_SOURCE_TYPES:
        failures.append(_workflow_failure(
            "FIXING_SOURCE_TYPE_INVALID",
            "source_type",
            "Le type de source est absent ou non autorisé.",
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
    if event.event_date > business_today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_EVENT_IN_FUTURE",
            "event_date",
            "L’événement contractuel est encore futur.",
            expected="Une date d’événement atteinte.",
            action="Attendez la date contractuelle de constatation.",
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

    strict_four_eyes = (
        amendment_four_eyes_enabled()
        or request.field_name == "commercial_attribution"
    )
    from ...core.access import require_managed_capability
    require_managed_capability(current, "operations.validate" if strict_four_eyes else "operations.prepare")
    if not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Demande d'amendement introuvable")
    if not strict_four_eyes:
        # Single-signature mode: whoever may act on the deal may decide on its
        # amendments, including the maker. Every other guarantee still applies.
        return deal, request

    if not has_business_role(current, {"checker", "admin"}):
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
