"""Row serializers and contract snapshots returned by the deals API."""
from __future__ import annotations
import json
from datetime import date
from sqlmodel import Session, select
from ...runtime import business_today
from ...db.models import AuditEvent, Deal, DealEvent, DealPortfolioMembership, LifecycleProposal, OfficialFixingVersion, TradeAmendmentRequest
from ...services.market_data import DEFAULT_MARKET_DATA_PROVIDER, market_data_provider_for_deal
from ...core.references import next_reference

def _gen_ref(entity_name: str | None, session: Session) -> str:
    prefix = ((entity_name or "DEAL")[:4].upper().replace(" ", "").ljust(4, "X"))
    return next_reference(session, Deal, f"{prefix}-{business_today().strftime('%Y%m%d')}-")


def _market_snapshot_for_read(deal: Deal) -> dict:
    try:
        market = json.loads(deal.market_snapshot_json or "{}")
    except (TypeError, ValueError):
        return {}
    return market if isinstance(market, dict) else {}


def _deal_row(
    d: Deal,
    events: list | None = None,
    session: Session | None = None,
    risk_terminal_date: date | None = None,
) -> dict:
    market = _market_snapshot_for_read(d)
    portfolio_ids = []
    if session is not None:
        portfolio_ids = list(session.exec(
            select(DealPortfolioMembership.portfolio_id).where(
                DealPortfolioMembership.deal_id == d.id)
        ).all())
        # Compatibility while a database has not yet run the membership
        # migration. New bookings never write the legacy pointer.
        if not portfolio_ids and d.portfolio_id is not None:
            portfolio_ids = [d.portfolio_id]
    margin = d.fair_value - d.price_traded if d.sens == "vente" else d.price_traded - d.fair_value
    if (market.get("kind") == "native_template_booking_v1" and d.product_type == "CDS" and d.nominal
            and "initial_settlement_pv_eur" in market):
        margin = 100 * (market["economic_dirty_pv_eur"] + market["initial_settlement_pv_eur"]) / d.nominal
    row = {
        "id": d.id,
        "product_id": d.product_id,
        "product_terms_version": d.product_terms_version,
        "reference": d.reference,
        "entity_id": d.entity_id,
        "user_id": d.user_id,
        "counterparty_id": d.counterparty_id,
        "legal_identity_exception": json.loads(d.legal_identity_exception_json) if d.legal_identity_exception_json else None,
        "ccr_netting_set_id": d.ccr_netting_set_id,
        "uat_batch_id": d.uat_batch_id,
        "indicative_id": d.indicative_id,
        "rfq_id": d.rfq_id,
        # Frozen best-execution record — see _rfq_provenance. None outside
        # the tender path.
        "rfq_provenance": json.loads(d.rfq_provenance_json) if d.rfq_provenance_json else None,
        # Rattachement commercial — à qui le produit a été vendu. None sur un
        # deal booké hors parcours client, ce qui reste valide.
        "client_id": d.client_id,
        "market_data_provider": (
            "synthetic" if market.get("kind") in ("native_exotic_booking_v1", "native_template_booking_v1")
            else market_data_provider_for_deal(d, session) if session is not None else DEFAULT_MARKET_DATA_PROVIDER
        ),
        "opportunity_id": d.opportunity_id,
        "primary_affiliation_id": d.primary_affiliation_id,
        "mandate_id": d.mandate_id,
        # Cliché figé au booking, même rôle que rfq_provenance juste au-dessus :
        # il dit ce qui était vrai le jour du trade, même si la fiche a bougé.
        "client_provenance": (json.loads(d.client_provenance_json)
                               if d.client_provenance_json else None),
        "client_attribution_current": (
            json.loads(d.client_attribution_json)
            if d.client_attribution_json else (
                json.loads(d.client_provenance_json)
                if d.client_provenance_json else None)),
        "transaction_format": d.transaction_format,
        "instrument_family": d.instrument_family,
        "payoff_family": d.payoff_family,
        "payoff_description": d.payoff_description,
        "documentation_reference": d.documentation_reference,
        "commercial_reason": d.commercial_reason,
        "portfolio_ids": portfolio_ids,
        "portfolio_id": portfolio_ids[0] if len(portfolio_ids) == 1 else None,
        "sens": d.sens,
        "contrepartie": d.contrepartie,
        "devise": d.devise,
        "product_type": d.product_type,
        "fixing_policy": d.fixing_policy,
        "nominal": d.nominal,
        "fair_value": d.fair_value,
        "price_traded": d.price_traded,
        # NOTRE marge, dans notre sens. `sens` décrit la CONTREPARTIE
        # (« la banque vend »), donc nous sommes de l'autre côté : quand elle
        # vend, nous achetons, et payer 98 un produit qui en vaut 100 nous fait
        # gagner 2. La soustraction nue rendait −2 sur ce cas, et l'infobulle de
        # l'écran décrivait pourtant le bon comportement.
        "margin": round(margin, 4),
        "trade_date": d.trade_date,
        "strike_date": d.strike_date,
        "value_date": d.value_date,
        "maturity_date": d.maturity_date,
        "payment_date": d.payment_date,
        "risk_terminal_date": (
            risk_terminal_date.isoformat() if risk_terminal_date else None
        ),
        "T": d.T,
        "realized_payout": d.realized_payout,
        "settlement_amount": d.settlement_amount,
        "settlement_date": d.settlement_date,
        "resolution_outcome": d.resolution_outcome,
        "underlyings": json.loads(d.underlyings_json),
        "market_snapshot": market,
        "greeks": json.loads(d.greeks_json) if d.greeks_json else {},
        "greeks_computed_at": d.greeks_computed_at.isoformat() if d.greeks_computed_at else None,
        "latest_valuation_run_id": d.latest_valuation_run_id,
        "status": d.status,
        "contract_version": d.contract_version,
        "script_id": d.script_id,
        "script_snapshot": d.script_snapshot,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
    if events is not None:
        row["events"] = [_event_row(e) for e in events]
    return row


def _event_row(e: DealEvent) -> dict:
    return {
        "id": e.id,
        "deal_id": e.deal_id,
        "event_index": e.event_index,
        "event_date": e.event_date,
        "t_years": e.t_years,
        # Un relevé de fenêtre pointe la constatation qu'il alimente. L'écran
        # doit le distinguer : ce n'est pas une observation, il ne paie rien et
        # ne compte pas dans la numérotation — mais il porte bien un fixing
        # officiel, puisque c'est de lui que l'agrégat se calcule.
        "parent_event_id": e.parent_event_id,
        "reduction": e.reduction or None,
        "spots": json.loads(e.spots_json),
        "indicative_spots": json.loads(e.indicative_spots_json or "{}"),
        "source": e.source,
        "status": e.status,
        "fixing_status": e.fixing_status,
        "data_category": e.data_category,
        "current_fixing_version_id": e.current_fixing_version_id,
        "fixing_version": e.fixing_version,
        "fixing_entered_by": e.fixing_entered_by,
        "fixing_entered_at": (
            e.fixing_entered_at.isoformat() if e.fixing_entered_at else None),
        "fixing_provider": e.fixing_provider,
        "fixing_source_type": e.fixing_source_type,
        "fixing_external_reference": e.fixing_external_reference,
        "fixing_observed_at": (
            e.fixing_observed_at.isoformat() if e.fixing_observed_at else None),
        "fixing_venue": e.fixing_venue,
        "fixing_calendar": e.fixing_calendar,
        "fixing_timezone": e.fixing_timezone,
        "fixing_evidence_sha256": e.fixing_evidence_sha256,
        "fixing_record_sha256": e.fixing_record_sha256,
        "fixing_reason": e.fixing_reason,
        "validated_by": e.validated_by,
        "validated_at": e.validated_at.isoformat() if e.validated_at else None,
        "applied_at": e.applied_at.isoformat() if e.applied_at else None,
        "label": e.label,
    }


def _get_events(deal_id: int, session: Session) -> list:
    return session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal_id)
        .order_by(DealEvent.event_index)
    ).all()


def _fixing_version_row(version: OfficialFixingVersion) -> dict:
    return {
        "id": version.id,
        "deal_event_id": version.deal_event_id,
        "version": version.version,
        "supersedes_id": version.supersedes_id,
        "status": version.status,
        "spots": json.loads(version.spots_json or "{}"),
        "provider": version.provider,
        "source_type": version.source_type,
        "external_reference": version.external_reference,
        "observed_at": version.observed_at.isoformat(),
        "received_at": version.received_at.isoformat(),
        "venue": version.venue,
        "calendar": version.calendar,
        "timezone": version.timezone,
        "evidence_sha256": version.evidence_sha256,
        "evidence_filename": version.evidence_filename,
        "evidence_content_type": version.evidence_content_type,
        "evidence_size_bytes": version.evidence_size_bytes,
        "record_sha256": version.record_sha256,
        "capture_reason": version.capture_reason,
        "capture_actor_type": version.capture_actor_type,
        "entered_by": version.entered_by,
        "validated_by": version.validated_by,
        "validation_reason": version.validation_reason,
        "validated_at": (
            version.validated_at.isoformat() if version.validated_at else None),
        "rejected_by": version.rejected_by,
        "rejection_reason": version.rejection_reason,
        "rejected_at": version.rejected_at.isoformat() if version.rejected_at else None,
        "applied_at": version.applied_at.isoformat() if version.applied_at else None,
        "created_at": version.created_at.isoformat(),
    }


def _proposal_row(proposal: LifecycleProposal) -> dict:
    return {
        "id": proposal.id,
        "deal_id": proposal.deal_id,
        "event_id": proposal.event_id,
        "status": proposal.status,
        "proposed_outcome": proposal.proposed_outcome,
        "result": json.loads(proposal.result_json or "{}"),
        "data_source": proposal.data_source,
        "official_result": (
            json.loads(proposal.official_result_json)
            if proposal.official_result_json else None),
        "official_input_hash": proposal.official_input_hash,
        "official_replayed_at": (
            proposal.official_replayed_at.isoformat()
            if proposal.official_replayed_at else None),
        "comparison_status": proposal.comparison_status,
        "validated_by": proposal.validated_by,
        "validation_reason": proposal.validation_reason,
        "validated_at": proposal.validated_at.isoformat() if proposal.validated_at else None,
        "applied_by": proposal.applied_by,
        "applied_at": proposal.applied_at.isoformat() if proposal.applied_at else None,
        "error_message": proposal.error_message,
        "correlation_id": proposal.correlation_id,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }


def _get_lifecycle_proposals(deal_id: int, session: Session) -> list[LifecycleProposal]:
    return session.exec(
        select(LifecycleProposal).where(LifecycleProposal.deal_id == deal_id)
        .order_by(LifecycleProposal.created_at.desc())
    ).all()


def _amendment_row(request: TradeAmendmentRequest) -> dict:
    return {
        "id": request.id,
        "deal_id": request.deal_id,
        "field_name": request.field_name,
        "old_value": json.loads(request.old_value_json),
        "new_value": json.loads(request.new_value_json),
        "reason": request.reason,
        "requested_by": request.requested_by,
        "status": request.status,
        "base_contract_version": request.base_contract_version,
        "validated_by": request.validated_by,
        "validated_at": request.validated_at.isoformat() if request.validated_at else None,
        "decision_reason": request.decision_reason,
        "rejected_by": request.rejected_by,
        "rejected_at": request.rejected_at.isoformat() if request.rejected_at else None,
        "applied_by": request.applied_by,
        "applied_at": request.applied_at.isoformat() if request.applied_at else None,
        "applied_contract_version": request.applied_contract_version,
        "credit_check": json.loads(request.credit_check_json) if request.credit_check_json else None,
        "created_at": request.created_at.isoformat(),
    }


def _audit_row(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "actor_user_id": event.actor_user_id,
        "actor_type": event.actor_type,
        "result": event.result,
        "before": json.loads(event.before_json or "{}"),
        "after": json.loads(event.after_json or "{}"),
        "reason": event.reason,
        "data_source": event.data_source,
        "correlation_id": event.correlation_id,
        "metadata": json.loads(event.metadata_json or "{}"),
        "created_at": event.created_at.isoformat(),
    }


def _contract_snapshot(deal: Deal) -> dict:
    """Contractual fields only; valuation state is deliberately excluded."""
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "product_id": deal.product_id,
        "product_terms_version": deal.product_terms_version,
        "contract_version": deal.contract_version,
        "sens": deal.sens,
        "contrepartie": deal.contrepartie,
        "counterparty_id": deal.counterparty_id,
        "legal_identity_exception": json.loads(deal.legal_identity_exception_json) if deal.legal_identity_exception_json else None,
        "ccr_netting_set_id": deal.ccr_netting_set_id,
        "devise": deal.devise,
        "nominal": deal.nominal,
        "fair_value": deal.fair_value,
        "price_traded": deal.price_traded,
        "product_type": deal.product_type,
        "fixing_policy": deal.fixing_policy,
        "trade_date": deal.trade_date,
        "strike_date": deal.strike_date,
        "value_date": deal.value_date,
        "maturity_date": deal.maturity_date,
        "payment_date": deal.payment_date,
        "T": deal.T,
        "underlyings": json.loads(deal.underlyings_json or "[]"),
        "script_snapshot": deal.script_snapshot,
        "market_snapshot": json.loads(deal.market_snapshot_json or "{}"),
        # L'échéancier contractuel figé au booking. Vide — donc `None` ici —
        # sur un deal antérieur à ce champ : l'écran doit le dire plutôt que
        # d'en afficher un reconstruit, qui pourrait différer du term sheet.
        "schedule": json.loads(deal.schedule_json or "{}") or None,
        "status": deal.status,
        "commercial_attribution_initial": (
            json.loads(deal.client_provenance_json)
            if deal.client_provenance_json else None),
        "commercial_attribution_current": (
            json.loads(deal.client_attribution_json)
            if deal.client_attribution_json else None),
        "client_id": deal.client_id,
        "mandate_id": deal.mandate_id,
        "opportunity_id": deal.opportunity_id,
        "primary_affiliation_id": deal.primary_affiliation_id,
        "transaction_format": deal.transaction_format,
        "instrument_family": deal.instrument_family,
        "payoff_family": deal.payoff_family,
        "payoff_description": deal.payoff_description,
        "documentation_reference": deal.documentation_reference,
    }
