"""Project governed Deal lifecycle state into the shared Product dossier."""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..core.product.models import FrozenObject, Product
from ..db.models import Deal, DealEvent, LifecycleProposal
from .product_repository import ProductError, load_product, stage_revision


def _json_object(value: str | None) -> dict:
    return json.loads(value or "{}")


def _iso(value):
    return value.isoformat() if value else None


def lifecycle_snapshot(session: Session, deal: Deal) -> FrozenObject:
    """Return current governed state; indicative market observations stay out."""
    events = session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal.id)
        .order_by(DealEvent.event_index, DealEvent.id)
    ).all()
    proposals = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.deal_id == deal.id)
        .order_by(LifecycleProposal.created_at, LifecycleProposal.id)
    ).all()
    return FrozenObject({
        "deal_id": deal.id,
        "deal_reference": deal.reference,
        "deal_status": deal.status,
        "resolution_outcome": deal.resolution_outcome,
        "realized_payout": deal.realized_payout,
        "settlement_amount": deal.settlement_amount,
        "events": [{
            "id": event.id,
            "event_index": event.event_index,
            "event_date": event.event_date,
            "t_years": event.t_years,
            "label": event.label,
            "parent_event_id": event.parent_event_id,
            "reduction": event.reduction,
            "status": event.status,
            "fixing_status": event.fixing_status,
            "data_category": event.data_category,
            "fixing_spots": _json_object(event.spots_json),
            "current_fixing_version_id": event.current_fixing_version_id,
            "fixing_version": event.fixing_version,
            "fixing_provider": event.fixing_provider,
            "fixing_source_type": event.fixing_source_type,
            "fixing_external_reference": event.fixing_external_reference,
            "fixing_observed_at": _iso(event.fixing_observed_at),
            "fixing_record_sha256": event.fixing_record_sha256,
            "validated_by": event.validated_by,
            "validated_at": _iso(event.validated_at),
            "applied_at": _iso(event.applied_at),
        } for event in events],
        "proposals": [{
            "id": proposal.id,
            "event_id": proposal.event_id,
            "status": proposal.status,
            "proposed_outcome": proposal.proposed_outcome,
            "proposed_result": _json_object(proposal.result_json),
            "data_source": proposal.data_source,
            "official_result": (
                _json_object(proposal.official_result_json)
                if proposal.official_result_json else None),
            "official_input_hash": proposal.official_input_hash,
            "official_replayed_at": _iso(proposal.official_replayed_at),
            "comparison_status": proposal.comparison_status,
            "proposed_by": proposal.proposed_by,
            "validated_by": proposal.validated_by,
            "validation_reason": proposal.validation_reason,
            "validated_at": _iso(proposal.validated_at),
            "applied_by": proposal.applied_by,
            "applied_at": _iso(proposal.applied_at),
            "error_message": proposal.error_message,
            "correlation_id": proposal.correlation_id,
            "created_at": _iso(proposal.created_at),
            "updated_at": _iso(proposal.updated_at),
        } for proposal in proposals],
    })


def stage_product_lifecycle(
    session: Session,
    deal: Deal,
    *,
    actor_user_id: int | None,
    action: str,
    reason: str,
) -> Product:
    """Append a Product revision in the caller's existing transaction."""
    if deal.product_id is None:
        raise ProductError(
            "DEAL_PRODUCT_MISSING",
            "Le deal ne possède pas de Product canonique.",
            409,
        )
    product = load_product(session, deal.product_id)
    if deal.product_terms_version != product.terms_version:
        raise ProductError(
            "PRODUCT_DEAL_TERMS_MISMATCH",
            "Le deal et le Product ne désignent pas la même version des termes.")
    lifecycle = lifecycle_snapshot(session, deal)
    if product.lifecycle == lifecycle:
        return product
    return stage_revision(
        session,
        product.model_copy(update={"lifecycle": lifecycle}),
        expected_revision=product.revision,
        actor_id=actor_user_id,
        action=action,
        reason=reason,
    )
