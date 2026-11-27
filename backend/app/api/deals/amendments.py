"""Contract amendments: request, four-eyes approval, rejection and application."""
from __future__ import annotations
import json
import math
from datetime import datetime, date
from typing import Annotated, Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, select
from ...db.database import get_session
from ...db.models import Deal, DealContractVersion, User, TradeAmendmentRequest
from ..auth import get_current_user
from ...core.audit import commit_rejection, record_audit_event
from ...core.client_controls import ClientRuleError, client_provenance_snapshot, require_deal_attribution_coherent
from ...core.workflow import AmendmentStatus
from ...core.product.models import CommercialContext, FrozenObject, TradeIntent
from ...services.product_repository import ProductError, load_product, stage_booked_terms_amendment, stage_revision
from ...services.business_access import can_read_deal as _can_access_deal
from ._router import router
from .common import _ensure_alert
from .serializers import _amendment_row, _contract_snapshot, _deal_row
from .fixing_controls import _checker_request

class AmendmentRequestCreate(BaseModel):
    field_name: Literal[
        "nominal", "devise", "contrepartie", "price_traded", "status",
        "trade_date", "strike_date", "value_date", "maturity_date",
        "payment_date", "script_snapshot", "market_snapshot",
        "commercial_attribution",
    ]
    new_value: object
    reason: str = Field(min_length=10, max_length=2000)


class AmendmentDecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


_IN_PLACE_AMENDMENT_FIELDS = {
    "nominal", "contrepartie", "price_traded", "payment_date",
    "commercial_attribution",
}


def _commercial_attribution_ids(deal: Deal) -> dict:
    return {
        "client_id": deal.client_id,
        "mandate_id": deal.mandate_id,
        "opportunity_id": deal.opportunity_id,
        "primary_affiliation_id": deal.primary_affiliation_id,
    }


def _amendment_current_value(deal: Deal, field: str):
    if field == "commercial_attribution":
        return _commercial_attribution_ids(deal)
    if field == "market_snapshot":
        return json.loads(deal.market_snapshot_json or "{}")
    return getattr(deal, field, None)


def _validated_amendment_value(
    deal: Deal,
    request: TradeAmendmentRequest,
    session: Session,
):
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
        try:
            numeric = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else float("nan")
        except (OverflowError, ValueError):
            numeric = float("nan")
        if not math.isfinite(numeric) or numeric <= 0:
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "La nouvelle valeur doit être finie et strictement positive.",
            })
        return numeric
    if field == "contrepartie":
        from ...services.legal_identity import active_counterparty
        if not isinstance(value, dict) or type(value.get("counterparty_id")) is not int:
            raise HTTPException(422, "L'amendement doit désigner un counterparty_id juridique explicite.")
        legal = active_counterparty(session, value["counterparty_id"])
        if legal.id == deal.counterparty_id:
            raise HTTPException(422, "La contrepartie juridique est inchangée ; le renommage du catalogue ne nécessite aucun transfert de contrat.")
        return {"counterparty_id": legal.id, "contrepartie": legal.name,
                "ccr_netting_set_id": value.get("ccr_netting_set_id", deal.ccr_netting_set_id if legal.id == deal.counterparty_id else None)}
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
    if field == "commercial_attribution":
        if not isinstance(value, dict):
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "L'attribution commerciale doit être un objet structuré.",
            })
        allowed = {
            "client_id", "mandate_id", "opportunity_id", "primary_affiliation_id",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            raise HTTPException(422, {
                "code": "AMENDMENT_VALUE_INVALID", "field": field,
                "message": "L'attribution contient des champs non autorisés.",
                "unexpected_fields": unexpected,
            })
        normalized = {key: value.get(key) for key in allowed}
        for key, item in normalized.items():
            if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
                raise HTTPException(422, {
                    "code": "AMENDMENT_VALUE_INVALID", "field": key,
                    "message": f"Le champ {key} doit être un identifiant entier ou null.",
                })
        try:
            require_deal_attribution_coherent(
                session,
                client_id=normalized["client_id"],
                mandate_id=normalized["mandate_id"],
                affiliation_id=normalized["primary_affiliation_id"],
                opportunity_id=normalized["opportunity_id"],
                entity_id=deal.entity_id,
            )
        except ClientRuleError as error:
            raise HTTPException(422, error.as_dict()) from error
        return normalized
    raise HTTPException(422, {"code": "AMENDMENT_VALUE_INVALID", "field": field})


@router.post("/{deal_id}/amendment-requests", status_code=201)
def request_amendment(
    deal_id: int,
    body: AmendmentRequestCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Record a maker request without changing the booked trade."""
    deal = session.get(Deal, deal_id)
    from ...core.access import require_managed_capability
    from ...hybrid.config import current_config
    require_managed_capability(current, "operations.prepare")
    if (not deal or not _can_access_deal(deal, current, session)
            or (current_config() is None and deal.user_id != current.id)):
        raise HTTPException(404, "Deal introuvable")
    from ...services.exotic_product_booking import is_native_scheduled_deal
    if is_native_scheduled_deal(deal):
        raise HTTPException(409, {"code": "EXOTIC_AMENDMENT_UNQUALIFIED",
                                 "message": "L’amendement officiel de ce Deal natif reste à qualifier."})
    old_value = _amendment_current_value(deal, body.field_name)
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
    if _amendment_current_value(deal, request.field_name) != old_value:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPROVAL_REJECTED", {
                "code": "AMENDMENT_BASE_VALUE_CHANGED",
                "message": "La valeur contractuelle de départ a changé.",
            })
    try:
        normalized = _validated_amendment_value(deal, request, session)
    except HTTPException as exc:
        commit_rejection(
            session,
            action="AMENDMENT_APPROVAL_REJECTED",
            object_type="TRADE_AMENDMENT_REQUEST",
            object_id=request.id,
            actor_user_id=current.id,
            before=_amendment_row(request),
            reason=exc.detail.get("message", "Amendement non applicable en place") if isinstance(exc.detail, dict) else str(exc.detail),
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
    if _amendment_current_value(deal, request.field_name) != old_value:
        _amendment_action_rejection(session, request, current,
            "AMENDMENT_APPLICATION_REJECTED", {
                "code": "AMENDMENT_BASE_VALUE_CHANGED",
                "message": "La valeur contractuelle de départ a changé.",
            })
    try:
        normalized = _validated_amendment_value(deal, request, session)
    except HTTPException as exc:
        _amendment_action_rejection(session, request, current, "AMENDMENT_APPLICATION_REJECTED", exc.detail)
    credit_check = None
    if request.field_name in {"contrepartie", "nominal", "payment_date"}:
        from ...core.ccr.service import enforce_amendment
        changes = normalized if request.field_name == "contrepartie" else {request.field_name: normalized}
        try:
            credit_check = enforce_amendment(session, current, deal, changes)
        except HTTPException as exc:
            session.rollback()
            request = session.get(TradeAmendmentRequest, request_id)
            _amendment_action_rejection(session, request, current, "AMENDMENT_APPLICATION_REJECTED",
                                        {"code": "AMENDMENT_LEGAL_OR_CREDIT_BLOCK", "message": str(exc.detail),
                                         "credit_check": exc.detail.get("credit_check") if isinstance(exc.detail, dict) else None})
    before_contract = _contract_snapshot(deal)
    current_version = deal.contract_version
    product = None
    if deal.product_id is not None:
        try:
            product = load_product(session, deal.product_id)
            if deal.product_terms_version != product.terms_version:
                raise ProductError(
                    "PRODUCT_DEAL_TERMS_MISMATCH",
                    "Le deal et le Product ne désignent pas la même version des termes.",
                )
            if request.field_name == "payment_date":
                amended_terms = product.terms.model_copy(update={
                    "payment_date": date.fromisoformat(normalized),
                })
                product = stage_booked_terms_amendment(
                    session, product, amended_terms,
                    reason=f"Amendement {request.id} du deal {deal.reference}.",
                )
        except ProductError as exc:
            session.rollback()
            raise HTTPException(
                exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
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
    update_values = {
        "contract_version": current_version + 1,
        "updated_at": applied_at,
        # Every persisted sensitivity belongs to the previous contract
        # version.  Keep immutable runs for audit, clear only current pointers.
        "greeks_json": "{}",
        "greeks_computed_at": None,
        "latest_valuation_run_id": None,
    }
    if product is not None:
        update_values["product_terms_version"] = product.terms_version
    if request.field_name == "commercial_attribution":
        current_attribution = client_provenance_snapshot(
            session,
            client_id=normalized["client_id"],
            mandate_id=normalized["mandate_id"],
            affiliation_id=normalized["primary_affiliation_id"],
            opportunity_id=normalized["opportunity_id"],
        )
        update_values.update({
            **normalized,
            "client_attribution_json": current_attribution,
        })
    elif request.field_name == "contrepartie":
        update_values.update(normalized)
    else:
        update_values[request.field_name] = normalized
    deal_cas = session.exec(
        update(Deal).where(
            Deal.id == deal.id,
            Deal.contract_version == current_version,
        ).values(**update_values).execution_options(synchronize_session=False)
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
            credit_check_json=json.dumps(credit_check, ensure_ascii=False, sort_keys=True) if credit_check else None,
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
    if product is not None:
        product = product.model_copy(update={
            "intent": TradeIntent(
                **{
                    **product.intent.model_dump(mode="json"),
                    "nominal": deal.nominal,
                    "counterparty_id": deal.counterparty_id,
                    "counterparty_name": deal.contrepartie,
                }
            ),
            "commercial": CommercialContext(
                client_id=deal.client_id,
                mandate_id=deal.mandate_id,
                opportunity_id=deal.opportunity_id,
                primary_affiliation_id=deal.primary_affiliation_id,
            ),
            "execution": FrozenObject({**_contract_snapshot(deal), "amendment_credit_check": credit_check}),
        })
        try:
            stage_revision(
                session, product, expected_revision=product.revision,
                actor_id=current.id, action="PRODUCT_CONTRACT_AMENDED",
                reason=body.reason,
            )
        except ProductError as exc:
            session.rollback()
            raise HTTPException(
                exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    after_contract = _contract_snapshot(deal)
    after_contract["amendment_credit_check"] = credit_check
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
                  "credit_check": credit_check,
                  "from_version": current_version,
                  "to_version": deal.contract_version,
                  "required_follow_up": [
                      "DOCUMENTS", "VALUATION", "ACCOUNTING", "REPORTING"]},
    )
    session.commit()
    session.refresh(deal)
    session.refresh(request)
    return {"deal": _deal_row(deal), "amendment": _amendment_row(request)}
