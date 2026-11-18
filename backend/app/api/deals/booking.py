"""Deal booking: pricing receipts, legal and RFQ controls, execution, portfolios."""
from __future__ import annotations
import json
import hashlib
import math
from datetime import datetime, date
from typing import Annotated, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_now
from ...db.models import Deal, DealEvent, DealPortfolioMembership, Entity, User, Portfolio, Indicative, Opportunity, ProductRecord, RfqQuote, RfqRequest
from ..auth import get_current_user, receipt_signing_secret
from ...core.references import next_audited_id, next_reference
from ...core.audit import commit_rejection, record_audit_event
from ...core.client_controls import ClientRuleError, client_provenance_snapshot, require_deal_attribution_coherent
from ...core.payoff_families import canonical_payoff_family, normalize_new_payoff_family
from ...core.rfq_controls import booking_gate_failures, failures_payload
from ...core.workflow import DataCategory, FixingPolicy, FixingStatus, QuoteFirmness
from ...core.valuation_context import verify_pricing_receipt
from ...core.product.inputs import terms_from_input
from ...core.product.models import CommercialContext, FrozenObject, TradeIntent
from ...services.product_repository import ProductError, load_product, owned_record, stage_calculation, stage_internal_product, stage_revision
from ...services.product_lifecycle import lifecycle_snapshot
from ...services.product_receipts import verify_server_receipt
from ...core.booking_contract import DealCreate
from ...services.business_access import deal_entity_id as _deal_entity_id, can_read_deal as _can_access_deal
from ._router import router
from .common import _date_plus_years, _derive_observation_times, _fenetre_de_depart, _fenetres_par_date, _figer_echeancier, _rfq_provenance, _validate_economics, _validate_rfq_booking_identity
from .serializers import _contract_snapshot, _deal_row, _gen_ref, _get_events

def _booking_request_summary(body: DealCreate) -> dict:
    return _safe_booking_numbers({
        "command_key": body.command_key,
        "counterparty_id": body.counterparty_id,
        "legal_identity_exception": body.legal_identity_exception.model_dump() if body.legal_identity_exception else None,
        "rfq_id": body.rfq_id,
        "execution_agreement_id": body.execution_agreement_id,
        "sens": body.sens,
        "contrepartie": body.contrepartie,
        "devise": body.devise,
        "nominal": body.nominal,
        "fair_value": body.fair_value,
        "price_traded": body.price_traded,
        "trade_date": body.trade_date,
        "strike_date": body.strike_date,
        "value_date": body.value_date,
        "maturity_date": body.maturity_date,
        "payment_date": body.payment_date,
        "T": body.T,
        "fixing_policy": body.fixing_policy,
        "pricing_input_fingerprint": (
            (body.pricing_receipt or {}).get("input_fingerprint")),
        "client_id": body.client_id,
        "mandate_id": body.mandate_id,
        "opportunity_id": body.opportunity_id,
        "primary_affiliation_id": body.primary_affiliation_id,
        "transaction_format": body.transaction_format,
        "instrument_family": body.instrument_family,
        "payoff_family": body.payoff_family,
    })


def _safe_booking_numbers(value):
    """Keep rejected non-finite values readable in strict JSON audit records."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _safe_booking_numbers(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_booking_numbers(v) for v in value]
    return value


def _non_finite_booking_paths(value, path=''):
    if isinstance(value, float) and not math.isfinite(value):
        return [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _non_finite_booking_paths(v, f'{path}.{k}'.lstrip('.'))]
    if isinstance(value, (list, tuple)):
        return [p for i, v in enumerate(value) for p in _non_finite_booking_paths(v, f'{path}[{i}]')]
    return []


def _ai_script_provenance(body: DealCreate) -> Optional[dict]:
    provenance = (body.market_snapshot or {}).get("ai_script_provenance")
    if provenance is None:
        return None
    if not isinstance(provenance, dict):
        raise HTTPException(422, {
            "code": "AI_PROVENANCE_INVALID",
            "message": "La provenance IA du script doit être un objet."})
    adopted = provenance.get("adopted_script_text")
    if not isinstance(adopted, str) or not adopted.strip():
        raise HTTPException(422, {
            "code": "AI_PROVENANCE_INVALID",
            "message": "La provenance IA ne contient pas le script adopté."})
    expected_hash = hashlib.sha256(adopted.encode("utf-8")).hexdigest()
    if provenance.get("script_sha256") != expected_hash:
        raise HTTPException(422, {
            "code": "AI_PROVENANCE_INVALID",
            "message": "L'empreinte du script généré ne correspond pas à sa provenance."})
    if (provenance.get("checks_status") == "warning"
            and provenance.get("warnings_acknowledged") is not True):
        raise HTTPException(422, {
            "code": "AI_WARNINGS_NOT_ACKNOWLEDGED",
            "message": "Les avertissements de l'assistant IA doivent être acquittés avant le booking."})
    return {
        **provenance,
        "modified_after_adoption": body.script_snapshot != adopted,
    }


def _apply_pricing_receipt(body: DealCreate,
                           ai_provenance: Optional[dict] = None) -> None:
    """Validate a pricing result and make its server snapshot authoritative."""
    if not body.pricing_receipt:
        return
    try:
        verified = verify_pricing_receipt(body.pricing_receipt)
    except ValueError as exc:
        raise HTTPException(422, {
            "code": "PRICING_RECEIPT_INVALID",
            "message": str(exc),
        })

    priced = verified["pricing_input"]
    variant = priced.get("variant") or {}
    priced_script = variant.get("script") or priced.get("script") or ""
    if body.script_snapshot != priced_script:
        raise HTTPException(409, {
            "code": "PRICING_RESULT_STALE",
            "message": "Le script a changé depuis le pricing. Relancez le calcul avant de booker.",
        })

    expected_price = float(verified.get("price_pct"))
    if abs(float(body.fair_value) - expected_price) > 0.0001:
        raise HTTPException(409, {
            "code": "PRICING_RESULT_STALE",
            "message": "La fair value ne correspond plus au résultat de pricing identifié.",
            "expected": expected_price,
            "received": body.fair_value,
        })

    comparisons = {
        "strike_date": body.strike_date,
        "value_date": body.value_date,
        "maturity_date": body.maturity_date,
        "payment_date": body.payment_date or None,
        "settlement_ccy": body.devise,
    }
    for field, received in comparisons.items():
        expected = priced.get(field)
        if expected is not None and str(received or "") != str(expected or ""):
            raise HTTPException(409, {
                "code": "PRICING_RESULT_STALE",
                "message": f"{field} a changé depuis le pricing. Relancez le calcul avant de booker.",
                "expected": expected,
                "received": received,
            })

    priced_t = priced.get("T")
    if priced_t is not None and abs(float(body.T) - float(priced_t)) > 1e-10:
        raise HTTPException(409, {
            "code": "PRICING_RESULT_STALE",
            "message": "La maturité en années a changé depuis le pricing. Relancez le calcul avant de booker.",
            "expected": priced_t,
            "received": body.T,
        })

    expected_uls = [
        (str(u.get("name") or ""), str(u.get("ticker") or ""), str(u.get("ccy") or ""))
        for u in (priced.get("underlyings") or [])
    ]
    received_uls = [
        (str(u.get("name") or ""), str(u.get("ticker") or ""), str(u.get("ccy") or ""))
        for u in body.underlyings
    ]
    if expected_uls != received_uls:
        raise HTTPException(409, {
            "code": "PRICING_RESULT_STALE",
            "message": "Les sous-jacents ont changé depuis le pricing. Relancez le calcul avant de booker.",
        })

    snapshot = verified["market_snapshot"]
    # Keep the exact validated engine-unit request with the display snapshot.
    # The fingerprint alone proves identity but cannot reproduce or explain the
    # original price without these inputs.
    snapshot["pricing_input"] = verified["pricing_input"]
    snapshot["pricing_price_pct"] = verified["price_pct"]
    if ai_provenance:
        snapshot["ai_script_provenance"] = ai_provenance
    body.market_snapshot = snapshot


def _reject_booking(session: Session, current: User, body: DealCreate,
                    status_code: int, detail) -> None:
    """Persist the refusal before returning it; audit failure fails closed."""
    reason = (json.dumps(detail, ensure_ascii=False, sort_keys=True)
              if isinstance(detail, (dict, list)) else str(detail))
    commit_rejection(
        session,
        action="BOOKING_REJECTED",
        object_type="RFQ" if body.rfq_id else "DEAL",
        object_id=body.rfq_id,
        actor_user_id=current.id,
        after=_booking_request_summary(body),
        reason=reason,
        metadata={"http_status": status_code},
    )
    from ...services.rfq_execution import record_booking_block
    record_booking_block(session, body, current, reason)
    raise HTTPException(status_code, detail)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/next-ref")
def next_ref(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    return {"reference": _gen_ref(entity.name if entity else None, session)}


def _book_deal(body: DealCreate, current: User, session: Session, *,
               reference_prefix: str | None = None, uat_batch_id: int | None = None):
    from ...core.access import require_booking_permission
    from ...services.booking_commands import booking_intent
    require_booking_permission(current)
    body = body.model_copy(deep=True)
    if _non_finite_booking_paths(body.model_dump()):
        # Keep non-finite refusals at the existing audited validation boundary.
        return _execute_booking(body, current, session, reference_prefix=reference_prefix,
                                uat_batch_id=uat_batch_id)
    try:
        key, digest, replay = booking_intent(session, current, body,
            reference_prefix=reference_prefix, uat_batch_id=uat_batch_id)
        if replay is not None:
            if not _can_access_deal(replay, current, session):
                raise ProductError('BOOKING_NOT_FOUND', 'Booking introuvable.', 404)
            result = _deal_row(replay, _get_events(replay.id, session), session)
            session.rollback()
            return result
        return _execute_booking(body, current, session, reference_prefix=reference_prefix,
            uat_batch_id=uat_batch_id, command=(key, digest))
    except ProductError as exc:
        session.rollback()
        _reject_booking(session, current, body, exc.status, {'code': exc.code, 'message': str(exc)})
    except Exception:
        session.rollback()
        raise


def _execute_booking(
    body: DealCreate,
    current: User,
    session: Session,
    *,
    reference_prefix: str | None = None,
    uat_batch_id: int | None = None,
    command: tuple[str, str] | None = None,
):
    from ...core.access import require_booking_permission
    require_booking_permission(current)
    invalid_numbers = _non_finite_booking_paths(body.model_dump())
    if invalid_numbers:
        _reject_booking(session, current, body, 422, {
            'code': 'BOOKING_NON_FINITE',
            'message': 'Valeurs numériques finies requises avant booking.',
            'fields': invalid_numbers,
        })
    from ...services import rfq_execution
    execution_request_hash = rfq_execution.booking_request_hash(body)
    try:
        agreement, replayed = rfq_execution.booking_context(session, body, current)
        if replayed is not None:
            result = _deal_row(replayed, _get_events(replayed.id, session), session)
            if command is not None:
                from ...services.booking_commands import stage_booking_command
                stage_booking_command(session, current, *command, replayed)
                session.commit()
            else:
                session.rollback()
            return result
        from ...services.legal_identity import active_counterparty
        legal_exception = None
        if body.legal_identity_exception is not None:
            from ...services.legal_identity import booking_exception
            legal_exception = booking_exception(session, current, body)
            body.contrepartie = legal_exception["counterparty_name"]
            legal_exception.update({"actor_user_id": current.id, "actor_role": current.role,
                "entity_id": current.entity_id, "approved_at": business_now().isoformat(),
                "booking_request_hash": execution_request_hash,
                "nominal": body.nominal, "currency": body.devise})
        else:
            legal = active_counterparty(session, body.counterparty_id)
            if body.contrepartie.strip() != legal.name:
                raise HTTPException(422, "Le libellé ne correspond pas à l'identifiant juridique choisi.")
            body.contrepartie = legal.name
        _validate_economics(body)
        ai_provenance = _ai_script_provenance(body)
        _apply_pricing_receipt(body, ai_provenance)
        if ai_provenance and not body.pricing_receipt:
            body.market_snapshot["ai_script_provenance"] = ai_provenance
    except HTTPException as exc:
        _reject_booking(session, current, body, exc.status_code, exc.detail)

    # Validate the RFQ link BEFORE the deal exists: rfq_id is a best-execution
    # trail (which tender this trade came out of), so a stale or foreign id
    # must be refused outright rather than persisted on the deal and merely
    # skipped when closing the RFQ below.
    client_id = body.client_id
    mandate_id = body.mandate_id
    opportunity_id = body.opportunity_id
    primary_affiliation_id = body.primary_affiliation_id
    commercial_reason = str(body.commercial_reason or "").strip() or None
    legal_context = {
        "transaction_format": str(body.transaction_format or "").strip() or None,
        "instrument_family": str(body.instrument_family or "").strip() or None,
        "payoff_family": str(body.payoff_family or "").strip() or None,
        "payoff_description": str(body.payoff_description or "").strip() or None,
        "documentation_reference": str(body.documentation_reference or "").strip() or None,
    }

    source_rfq = None
    rfq_provenance = None
    rfq_context_to_apply = None
    quote_to_qualify = None
    if body.rfq_id:
        source_rfq = session.get(RfqRequest, body.rfq_id)
        if not source_rfq:
            _reject_booking(session, current, body, 404, "RFQ introuvable")
        from ...services.rfq_access import require_rfq_access
        from ...services.rfq_exchange import round_for
        from ...services.rfq_publication import publication_for_quote
        try:
            require_rfq_access(session, source_rfq.id, current, "book")
            exchange_round = round_for(session, source_rfq.id)
            if exchange_round and exchange_round.state != "OPEN" and agreement is None:
                raise HTTPException(409, "Le tour RFQ a été remplacé ; utilisez le nouveau dossier")
        except HTTPException as exc:
            _reject_booking(session, current, body, exc.status_code, exc.detail)
        # Booking a tender closes it as "Bookée" — doing that without a
        # retained response would record a trade won by nobody, and leave the
        # analysis unable to tell who actually won (see api/rfq.py:/history).
        # One tender, one trade. Booking the same RFQ twice would produce two
        # deals both claiming to be THE execution of that competition, and
        # would double-count the winning bank's hit ratio (api/rfq.py:/history).
        already = session.exec(select(Deal).where(Deal.rfq_id == source_rfq.id)).first()
        if already:
            _reject_booking(
                session, current, body, 409,
                f"Cette RFQ a déjà été bookée — deal {already.reference}. "
                "Ouvrez-le depuis le Booking plutôt que d'en créer un second.")

        selected = session.get(RfqQuote, source_rfq.selected_quote_id) \
            if source_rfq.selected_quote_id else None
        try:
            expected_legal = (active_counterparty(session, json.loads(agreement.snapshot_json)["counterparty_id"]) if agreement
                              else rfq_execution._counterparty(session, source_rfq, selected) if selected else None)
            expected_counterparty = expected_legal.name if expected_legal else None
            if expected_legal and body.counterparty_id != expected_legal.id:
                raise HTTPException(422, "La banque bookée diffère de l'identité juridique de la cotation.")
        except HTTPException as exc:
            _reject_booking(session, current, body, exc.status_code, exc.detail)
        gate_failures = booking_gate_failures(
            source_rfq, selected,
            now=business_now(),
            expected_counterparty=expected_counterparty,
            requested_counterparty=body.contrepartie,
            acceptance_received_at=agreement.acceptance_received_at if agreement else None,
        )
        if gate_failures:
            _reject_booking(
                session, current, body, 422, failures_payload(gate_failures))
        try:
            _validate_rfq_booking_identity(source_rfq, body, session)
        except HTTPException as exc:
            _reject_booking(session, current, body, exc.status_code, exc.detail)

        # The RFQ is the authoritative pre-trade record.  A browser cannot
        # silently replace its Client/Mandate/Opportunity while booking.  For
        # a legacy or product-only RFQ with no context at all, the desk may
        # attach a coherent context at booking; that attachment is persisted
        # on the RFQ in the same transaction so the chain remains complete.
        rfq_commercial = {
            "client_id": source_rfq.client_id,
            "mandate_id": source_rfq.mandate_id,
            "opportunity_id": source_rfq.opportunity_id,
            "primary_affiliation_id": source_rfq.primary_affiliation_id,
        }
        requested_commercial = {
            "client_id": client_id,
            "mandate_id": mandate_id,
            "opportunity_id": opportunity_id,
            "primary_affiliation_id": primary_affiliation_id,
        }
        if any(value is not None for value in rfq_commercial.values()):
            for field, expected in rfq_commercial.items():
                received = requested_commercial[field]
                if received is not None and received != expected:
                    _reject_booking(session, current, body, 422, {
                        "code": "RFQ_COMMERCIAL_CONTEXT_MISMATCH",
                        "message": (
                            f"Le champ {field} contredit le contexte commercial "
                            "figé sur la RFQ. Corrigez la RFQ avant le booking."),
                        "field": field,
                        "expected": expected,
                        "received": received,
                    })
            client_id = rfq_commercial["client_id"]
            mandate_id = rfq_commercial["mandate_id"]
            opportunity_id = rfq_commercial["opportunity_id"]
            primary_affiliation_id = rfq_commercial["primary_affiliation_id"]
        elif any(value is not None for value in requested_commercial.values()):
            from ..rfq import _resolve_commercial_context
            try:
                rfq_context_to_apply, _ = _resolve_commercial_context(
                    opportunity_id=opportunity_id,
                    client_id=client_id,
                    mandate_id=mandate_id,
                    primary_affiliation_id=primary_affiliation_id,
                    current=current,
                    session=session,
                    explicit_fields={
                        field for field, value in requested_commercial.items()
                        if value is not None
                    },
                    qualification_required=True,
                )
            except HTTPException as exc:
                _reject_booking(session, current, body, exc.status_code, exc.detail)
            client_id = rfq_context_to_apply["client_id"]
            mandate_id = rfq_context_to_apply["mandate_id"]
            opportunity_id = rfq_context_to_apply["opportunity_id"]
            primary_affiliation_id = rfq_context_to_apply["primary_affiliation_id"]

        for field in legal_context:
            rfq_value = str(getattr(source_rfq, field, None) or "").strip() or None
            requested_value = legal_context[field]
            if rfq_value is not None:
                comparable_rfq = rfq_value
                comparable_requested = requested_value
                if field == "payoff_family":
                    comparable_rfq = canonical_payoff_family(rfq_value) or rfq_value
                    comparable_requested = (
                        canonical_payoff_family(requested_value) or requested_value)
                if requested_value is not None and comparable_requested != comparable_rfq:
                    _reject_booking(session, current, body, 422, {
                        "code": "RFQ_LEGAL_CONTEXT_MISMATCH",
                        "message": (
                            f"Le champ {field} contredit la structure produit "
                            "portée par la RFQ."),
                        "field": field,
                        "expected": rfq_value,
                        "received": requested_value,
                    })
                legal_context[field] = comparable_rfq

        # Le booking qualifie la cotation retenue. Une quote encore « à
        # qualifier » qui vient d'être tradée EST ferme — c'est le trade qui le
        # dit. La laisser UNKNOWN ferait mentir l'analyse contrepartie, qui
        # continuerait de compter comme non qualifié un prix sur lequel on a
        # traité. La provenance garde d'où vient l'affirmation.
        fermete_avant = selected.firmness if selected is not None else None
        qualifiee_au_booking = (
            selected is not None
            and not publication_for_quote(session, selected.id)
            and selected.firmness != QuoteFirmness.FIRM.value)
        if qualifiee_au_booking:
            quote_to_qualify = selected

        rfq_provenance = _rfq_provenance(
            source_rfq, body.price_traded, session,
            fermete_avant=fermete_avant,
            firmness_affirmee_au_booking=qualifiee_au_booking)
        if agreement:
            provenance = json.loads(rfq_provenance)
            provenance["execution_agreement"] = rfq_execution.row(session, agreement)
            rfq_provenance = json.dumps(provenance, ensure_ascii=False)

    if legal_context["payoff_family"]:
        try:
            legal_context["payoff_family"] = normalize_new_payoff_family(
                legal_context["payoff_family"], legal_context["payoff_description"])
        except ValueError as exc:
            # Existing RFQs may carry an unclassified free-text value.
            # Preserve it only when the booking keeps that value unchanged.
            if (source_rfq is None
                    or canonical_payoff_family(source_rfq.payoff_family)
                    or legal_context["payoff_family"] != source_rfq.payoff_family):
                _reject_booking(session, current, body, 422, str(exc))

    source_product = None
    pending_product_terms = None
    source_indicative = None
    if body.indicative_id is not None:
        source_indicative = session.get(Indicative, body.indicative_id)
        if source_indicative is None or source_indicative.user_id != current.id:
            _reject_booking(session, current, body, 404, {
                "code": "INDICATIVE_NOT_FOUND",
                "message": "Fiche indicative introuvable.",
            })
        if source_indicative.product_id is None:
            _reject_booking(session, current, body, 409, {
                "code": "INDICATIVE_PRODUCT_MISSING",
                "message": "La fiche indicative ne possède pas de Product canonique.",
            })

    workflow_product_ids = {
        product_id for product_id in (
            source_rfq.product_id if source_rfq is not None else None,
            source_indicative.product_id if source_indicative is not None else None,
            body.product_id,
        ) if product_id is not None
    }
    if len(workflow_product_ids) > 1:
        _reject_booking(session, current, body, 422, {
            "code": "WORKFLOW_PRODUCT_MISMATCH",
            "message": "Le RFQ, l’indicatif et le Pricer ne désignent pas le même Product.",
        })
    source_product_id = next(iter(workflow_product_ids), None)
    if source_rfq is not None and body.product_id is not None \
            and body.product_id != source_rfq.product_id:
        _reject_booking(session, current, body, 422, {
            "code": "RFQ_PRODUCT_MISMATCH",
            "message": "Le Product demandé ne correspond pas à celui de la RFQ.",
        })
    if source_rfq is not None and source_product_id is None:
        _reject_booking(session, current, body, 409, {
            "code": "RFQ_PRODUCT_MISSING",
            "message": "La RFQ ne possède pas de Product canonique.",
        })
    if not body.pricing_receipt:
        _reject_booking(session, current, body, 422, {
            "code": "PRODUCT_REPRICE_REQUIRED",
            "message": "Lancez le Pricer avant le booking afin de produire un calcul vérifiable.",
        })
    try:
        verified_product_receipt = verify_server_receipt(
            body.pricing_receipt, secret=receipt_signing_secret())
    except (KeyError, TypeError, ValueError) as exc:
        _reject_booking(session, current, body, 422, {
            "code": "PRODUCT_PRICING_RECEIPT_INVALID",
            "message": f"Le reçu serveur du pricing est invalide : {exc}",
        })
    try:
        priced_terms = terms_from_input(
            verified_product_receipt["pricing_input"], allow_unresolved=False)
    except (KeyError, TypeError, ValueError) as exc:
        _reject_booking(session, current, body, 422, {
            "code": "PRODUCT_TERMS_INVALID",
            "message": f"Les termes portés par le pricing sont invalides : {exc}",
        })
    missing_product_terms = [
        field for field in (
            "strike_date", "value_date", "maturity_date", "payment_date",
            "settlement_ccy",
        ) if getattr(priced_terms, field) in (None, "")
    ]
    if missing_product_terms:
        _reject_booking(session, current, body, 422, {
            "code": "PRODUCT_TERMS_INCOMPLETE",
            "message": (
                "Le pricing ne porte pas tous les termes nécessaires au booking : "
                + ", ".join(missing_product_terms) + "."),
            "fields": missing_product_terms,
        })

    if source_product_id is not None:
        try:
            if source_rfq is not None:
                from ...services.rfq_access import ownership
                rfq_scope = ownership(session, source_rfq.id)
            else:
                rfq_scope = None
            if rfq_scope is None:
                owned_record(session, source_product_id, current)
            else:
                product_row = session.get(ProductRecord, source_product_id)
                if product_row is None or product_row.entity_id != rfq_scope.entity_id:
                    raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
            source_product = load_product(session, source_product_id)
        except ProductError as exc:
            _reject_booking(session, current, body, exc.status, {
                "code": exc.code, "message": str(exc),
            })
        expected_terms = (
            source_rfq.product_terms_version if source_rfq is not None
            else source_indicative.product_terms_version
            if source_indicative is not None else body.product_terms_version)
        if expected_terms is not None and expected_terms != source_product.terms_version:
            _reject_booking(session, current, body, 409, {
                "code": "PRODUCT_TERMS_STALE",
                "message": "La version du Product a changé depuis l’ouverture du dossier.",
            })
        if source_product.execution is not None:
            _reject_booking(session, current, body, 409, {
                "code": "PRODUCT_ALREADY_BOOKED",
                "message": "Ce Product est déjà rattaché à une exécution.",
            })
        if priced_terms.fingerprint != source_product.terms_fingerprint:
            _reject_booking(session, current, body, 422, {
                "code": "PRODUCT_TERMS_MISMATCH",
                "message": "Le pricing courant ne porte plus les termes du Product ouvert.",
            })
        body.product_id = source_product_id
        body.product_terms_version = source_product.terms_version
    else:
        pending_product_terms = priced_terms

    if source_product is not None:
        for field in ("transaction_format", "instrument_family", "documentation_reference"):
            expected = str(getattr(source_product.intent, field) or "").strip()
            requested = legal_context[field]
            if expected:
                if requested and requested.casefold() != expected.casefold():
                    _reject_booking(session, current, body, 422, {
                        "code": "PRODUCT_LEGAL_CONTEXT_MISMATCH",
                        "message": f"Le champ {field} contredit le Product ouvert.",
                        "field": field,
                    })
                legal_context[field] = expected

    # Legal metadata is authoritative only after the RFQ reconciliation above.
    # Every native booking route reaches this gate before any Deal is persisted.
    try:
        from ...core.ccr.service import enforce_booking
        for field, value in legal_context.items():
            setattr(body, field, value)
        enforce_booking(session, current, body)
    except HTTPException as exc:
        _reject_booking(session, current, body, exc.status_code, exc.detail)

    # A new deal's script and frozen CONSTAT values are the contract.  Client
    # Monte-Carlo grid points are never a safe booking fallback.
    try:
        times = _derive_observation_times(body)
    except (ValueError, KeyError, TypeError) as e:
        _reject_booking(
            session, current, body, 422,
            f"Le calendrier contractuel du script est inexploitable : {e}. "
            "Corrigez les CONSTAT avant de booker.")
    if not times:
        # A deal with no observation has no life: no barrier watchlist, no
        # residual MtM, no automatic resolution. It used to be booked anyway
        # and stayed silently inert — an incoherent calendar (end before
        # start) reaches exactly this state.
        _reject_booking(
            session, current, body, 422,
            "Ce deal n'a aucune constatation — il ne pourrait être ni surveillé, "
            "ni valorisé, ni dénoué. Vérifiez le calendrier CONSTAT du script.")

    maturity = date.fromisoformat(body.maturity_date)
    # Les temps d observation se comptent depuis la MEME origine que celle qui
    # les a resolus (_derive_observation_times) : la date de strike. Les
    # reconvertir depuis la value date les decalerait de l ecart entre les deux.
    _obs_origin = body.strike_date or body.value_date
    event_dates = [_date_plus_years(_obs_origin, t) for t in times]
    after_maturity = [d for d in event_dates if date.fromisoformat(d) > maturity]
    if after_maturity:
        _reject_booking(
            session, current, body, 422,
            "Le calendrier contractuel dépasse la maturité du deal "
            f"({body.maturity_date}) : {', '.join(after_maturity)}.")

    # Rattachement commercial — cohérence vérifiée AVANT toute allocation, avec
    # les autres refus : écrire « client B / contact chez A » corromprait toutes
    # les statistiques par affiliation sans jamais se signaler.
    try:
        require_deal_attribution_coherent(
            session, client_id=client_id, mandate_id=mandate_id,
            affiliation_id=primary_affiliation_id,
            opportunity_id=opportunity_id,
            entity_id=current.entity_id)
    except ClientRuleError as erreur:
        _reject_booking(session, current, body, 422, erreur.as_dict())

    opportunity = None
    if opportunity_id is not None:
        opportunity = session.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.entity_id != current.entity_id:
            _reject_booking(session, current, body, 404, "Opportunité introuvable")
        if opportunity.status in {"won", "lost", "cancelled", "archived"}:
            _reject_booking(session, current, body, 409, {
                "code": "OPPORTUNITY_CLOSED_FOR_BOOKING",
                "message": (
                    "Cette Opportunity est clôturée. Rouvrez-la avant de "
                    "booker une nouvelle tranche."),
                "status": opportunity.status,
            })

    if client_id is not None and opportunity_id is None and source_rfq is None:
        if not commercial_reason or len(commercial_reason) < 10:
            _reject_booking(session, current, body, 422, {
                "code": "DIRECT_CLIENT_LINK_REASON_REQUIRED",
                "message": (
                    "Un Deal rattaché directement à un Client, sans RFQ ni "
                    "Opportunity, exige un motif commercial de 10 caractères minimum."),
            })
    client_provenance = client_provenance_snapshot(
        session, client_id=client_id, mandate_id=mandate_id,
        affiliation_id=primary_affiliation_id,
        opportunity_id=opportunity_id)

    if pending_product_terms is not None:
        source_product = stage_internal_product(
            session,
            user=current,
            name=body.product_type or "Produit structuré",
            terms=pending_product_terms,
            intent=TradeIntent(
                nominal=body.nominal,
                side="BUY" if body.sens == "vente" else "SELL",
                product_type=body.product_type,
                transaction_format=legal_context["transaction_format"] or "",
                instrument_family=legal_context["instrument_family"] or "",
                payoff_family=legal_context["payoff_family"] or "",
                payoff_description=legal_context["payoff_description"] or "",
                documentation_reference=legal_context["documentation_reference"] or "",
            ),
            commercial=CommercialContext(
                client_id=client_id,
                mandate_id=mandate_id,
                opportunity_id=opportunity_id,
                primary_affiliation_id=primary_affiliation_id,
            ),
            data_origin="uat" if uat_batch_id is not None else "native",
            uat_batch_id=uat_batch_id,
            reason="Création interne du Product avant booking direct.",
        )
        body.product_id = source_product.product_id
        body.product_terms_version = source_product.terms_version

    # The Pricer result completes the same Product, whether it originated in
    # the Pricer itself or behind an RFQ. Reopening and booking must never
    # leave the calculation stranded only in Deal.market_snapshot_json.
    if not any(calculation.calculated_at == verified_product_receipt["calculated_at"]
               for calculation in source_product.calculations):
        enriched = stage_calculation(
            session, source_product, user=current,
            receipt=verified_product_receipt,
        )
        source_product = stage_revision(
            session, enriched, expected_revision=source_product.revision,
            actor_id=current.id, action="PRODUCT_CALCULATION_RETAINED",
            reason="Calcul du Pricer retenu lors du booking.",
        )

    # Allocate persistent objects only after every rejection-prone validation.
    # A rejected booking can then commit its audit row without also consuming a
    # reference or creating a default portfolio as a side effect.
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    reference = (next_reference(session, Deal, reference_prefix)
                 if reference_prefix else _gen_ref(entity.name if entity else None, session))
    deal = Deal(
        # AuditEvent keeps numeric object identities forever.  Letting SQLite
        # recycle a deleted Deal id would splice the previous trade's history
        # into the new one.
        id=next_audited_id(session, Deal, "DEAL"),
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        uat_batch_id=uat_batch_id,
        portfolio_id=None,
        product_id=body.product_id,
        product_terms_version=body.product_terms_version,
        indicative_id=body.indicative_id,
        rfq_id=body.rfq_id,
        rfq_provenance_json=rfq_provenance,
        client_id=client_id,
        mandate_id=mandate_id,
        opportunity_id=opportunity_id,
        primary_affiliation_id=primary_affiliation_id,
        # Le pointeur donne la justesse, le cliché donne la preuve : une fiche
        # client corrigée plus tard ne réécrit pas ce que ce trade raconte.
        client_provenance_json=client_provenance,
        client_attribution_json=client_provenance,
        transaction_format=legal_context["transaction_format"],
        instrument_family=legal_context["instrument_family"],
        payoff_family=legal_context["payoff_family"],
        payoff_description=legal_context["payoff_description"],
        documentation_reference=legal_context["documentation_reference"],
        commercial_reason=commercial_reason,
        script_snapshot=body.script_snapshot,
        script_id=body.script_id,
        sens=body.sens,
        contrepartie=body.contrepartie,
        counterparty_id=body.counterparty_id,
        legal_identity_exception_json=json.dumps(legal_exception, ensure_ascii=False) if legal_exception else None,
        ccr_netting_set_id=body.ccr_netting_set_id,
        devise=body.devise,
        product_type=body.product_type,
        fixing_policy=FixingPolicy.AUTO_YAHOO.value,
        nominal=body.nominal,
        fair_value=body.fair_value,
        price_traded=body.price_traded,
        trade_date=body.trade_date,
        strike_date=body.strike_date,
        value_date=body.value_date,
        maturity_date=body.maturity_date,
        payment_date=body.payment_date,
        T=body.T,
        underlyings_json=json.dumps(body.underlyings),
        market_snapshot_json=json.dumps(body.market_snapshot),
        schedule_json=_figer_echeancier(body),
    )
    session.add(deal)
    session.flush()
    rfq_execution.attach_booking(session, agreement, deal, current, execution_request_hash)
    from ...services.rfq_electronic import attach_booking as attach_electronic_booking
    attach_electronic_booking(session, body, deal, current, execution_request_hash)

    if quote_to_qualify is not None:
        quote_to_qualify.firmness = QuoteFirmness.FIRM.value
        session.add(quote_to_qualify)

    if source_rfq is not None and rfq_context_to_apply is not None:
        source_rfq.client_id = client_id
        source_rfq.mandate_id = mandate_id
        source_rfq.opportunity_id = opportunity_id
        source_rfq.primary_affiliation_id = primary_affiliation_id
        source_rfq.commercial_context_json = rfq_context_to_apply["commercial_context_json"]
        record_audit_event(
            session,
            action="RFQ_COMMERCIAL_CONTEXT_ATTACHED_AT_BOOKING",
            object_type="RFQ",
            object_id=source_rfq.id,
            actor_user_id=current.id,
            after={
                "client_id": client_id,
                "mandate_id": mandate_id,
                "opportunity_id": opportunity_id,
                "primary_affiliation_id": primary_affiliation_id,
            },
            result="SUCCESS",
            metadata={"deal_id": deal.id},
        )

    if source_rfq is not None:
        for field, value in legal_context.items():
            if getattr(source_rfq, field, None) is None and value is not None:
                setattr(source_rfq, field, value)

    if opportunity is not None and opportunity.status != "partially_won":
        previous_status = opportunity.status
        opportunity.status = "partially_won"
        opportunity.last_activity_at = datetime.utcnow()
        opportunity.updated_at = datetime.utcnow()
        session.add(opportunity)
        record_audit_event(
            session,
            action="OPPORTUNITY_PARTIALLY_WON",
            object_type="OPPORTUNITY",
            object_id=opportunity.id,
            actor_user_id=current.id,
            before={"status": previous_status},
            after={"status": "partially_won", "deal_id": deal.id},
            result="SUCCESS",
            metadata={"rfq_id": body.rfq_id},
        )

    if source_indicative is not None:
        source_indicative.status = "converti"
        source_indicative.updated_at = datetime.utcnow()
        session.add(source_indicative)

    if source_rfq:
        source_rfq.status = "clos"
        source_rfq.updated_at = datetime.utcnow()
        session.add(source_rfq)

    # First event is always the strike date (t=0) — S₀ to be filled in Events tab
    strike_event = DealEvent(
        deal_id=deal.id,
        event_index=0,
        event_date=body.strike_date,
        t_years=0.0,
        spots_json="{}",
        source="pending",
        status="futur",
        fixing_status=FixingStatus.EXPECTED.value,
        data_category=DataCategory.UNKNOWN.value,
        label="Strike / Fixing S₀",
    )
    session.add(strike_event)
    _index = 0

    # Une fenêtre de départ (`CONSTAT STRIKE_FIX AVG`) fixe S₀ sur ses relevés,
    # dont le fixing du jour de strike n'est que le premier. Sans lignes pour
    # les autres, le rejeu officiel reportait ce seul cours sur toute la
    # fenêtre : S₀ valait le cours du strike et non la réduction, sans que rien
    # ne le dise.
    _depart = _fenetre_de_depart(deal.schedule_json)
    if _depart:
        strike_event.reduction = _depart["reduction"]
        session.flush()
        for j, releve in enumerate(_depart["releves"], start=1):
            if releve["date"] == body.strike_date:
                # Le jour de strike EST un relevé : une seule ligne, donc un
                # seul fixing officiel pour les deux usages.
                continue
            _index += 1
            session.add(DealEvent(
                deal_id=deal.id,
                event_index=_index,
                event_date=releve["date"] or "",
                t_years=round(releve["t"], 4),
                spots_json="{}",
                source="pending",
                status="futur",
                fixing_status=FixingStatus.EXPECTED.value,
                data_category=DataCategory.UNKNOWN.value,
                parent_event_id=strike_event.id,
                label=f"Strike / Fixing S₀ · relevé {j}/{len(_depart['releves'])}",
            ))

    # L'échéancier figé dit quelles constatations sont MOYENNÉES, et sur quels
    # relevés. Sans lui, on retombe sur des constatations ponctuelles — ce que
    # sont l'immense majorité des produits.
    _fenetres = _fenetres_par_date(deal.schedule_json)

    for idx, t in enumerate(times):
        ev_date = _date_plus_years(_obs_origin, t)
        is_maturity = (idx == len(times) - 1)
        label = "Maturité" if is_maturity else f"Obs. {idx + 1} ({t:.2f}Y)"
        _index += 1
        constatation = DealEvent(
            deal_id=deal.id,
            event_index=_index,
            event_date=ev_date,
            t_years=round(t, 4),
            spots_json="{}",
            source="pending",
            status="futur",
            fixing_status=FixingStatus.EXPECTED.value,
            data_category=DataCategory.UNKNOWN.value,
            label=label,
        )
        fenetre = _fenetres.get(round(t, 4))
        if fenetre:
            constatation.reduction = fenetre["reduction"]
        session.add(constatation)
        if not fenetre:
            continue
        # Une constatation moyennée se calcule depuis les cours de sa fenêtre :
        # ces cours doivent exister comme lignes, sinon ils n'ont ni fixing
        # officiel, ni provenance, ni preuve — et l'agrégat n'a rien à lire.
        session.flush()
        for j, releve in enumerate(fenetre["releves"], start=1):
            if releve["date"] == ev_date:
                # Le dernier relevé EST la constatation : une seule ligne, donc
                # un seul fixing officiel pour les deux usages.
                continue
            _index += 1
            session.add(DealEvent(
                deal_id=deal.id,
                event_index=_index,
                event_date=releve["date"] or "",
                t_years=round(releve["t"], 4),
                spots_json="{}",
                source="pending",
                status="futur",
                fixing_status=FixingStatus.EXPECTED.value,
                data_category=DataCategory.UNKNOWN.value,
                parent_event_id=constatation.id,
                label=f"{label} · relevé {j}/{len(fenetre['releves'])}",
            ))

    if source_product is not None:
        product_indicatives = source_product.indicatives
        if source_indicative is not None:
            from ..indicatives import _indicative_snapshot
            current_indicative = _indicative_snapshot(source_indicative)
            product_indicatives = tuple(
                item for item in product_indicatives
                if item.to_dict().get("id") != source_indicative.id
            ) + (current_indicative,)
        product_rfqs = source_product.rfqs
        if source_rfq is not None:
            from ..rfq import (_booked_deals_by_rfq, _counterparty_by_provider,
                              _get_quotes, _rfq_row)
            current_rfq = FrozenObject(_rfq_row(
                source_rfq, _get_quotes(source_rfq.id, session),
                _counterparty_by_provider(session),
                _booked_deals_by_rfq(session, current.id), session=session))
            product_rfqs = tuple(
                item for item in product_rfqs
                if item.to_dict().get("id") != source_rfq.id
            ) + (current_rfq,)
        intent = TradeIntent(
            **{
                **source_product.intent.model_dump(mode="json"),
                "nominal": deal.nominal,
                "side": "BUY" if deal.sens == "vente" else "SELL",
                "counterparty_id": deal.counterparty_id,
                "counterparty_name": deal.contrepartie,
                "product_type": deal.product_type,
                "transaction_format": deal.transaction_format or "",
                "instrument_family": deal.instrument_family or "",
                "payoff_family": deal.payoff_family or "",
                "payoff_description": deal.payoff_description or "",
                "documentation_reference": deal.documentation_reference or "",
            }
        )
        commercial = CommercialContext(
            client_id=deal.client_id, mandate_id=deal.mandate_id,
            opportunity_id=deal.opportunity_id,
            primary_affiliation_id=deal.primary_affiliation_id,
        )
        source_product = source_product.model_copy(update={
            "intent": intent,
            "commercial": commercial,
            "indicatives": product_indicatives,
            "rfqs": product_rfqs,
            "execution": FrozenObject(_contract_snapshot(deal)),
            "lifecycle": lifecycle_snapshot(session, deal),
        })
        stage_revision(
            session, source_product, expected_revision=source_product.revision,
            actor_id=current.id, action="PRODUCT_BOOKED",
            reason=f"Booking du Product dans le deal {deal.reference}.")

    try:
        if legal_exception is not None:
            record_audit_event(session, action="BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED",
                object_type="DEAL", object_id=deal.id, actor_user_id=current.id,
                result="SUCCESS", reason=legal_exception["reason"], after=legal_exception,
                metadata={"product_id": deal.product_id, "contract_version": deal.contract_version})
        record_audit_event(
            session,
            action="BOOKING_ACCEPTED",
            object_type="DEAL",
            object_id=deal.id,
            actor_user_id=current.id,
            after={
                **_booking_request_summary(body),
                "reference": deal.reference,
                "client_id": client_id,
                "mandate_id": mandate_id,
                "opportunity_id": opportunity_id,
                "primary_affiliation_id": primary_affiliation_id,
                **legal_context,
            },
            result="SUCCESS",
            metadata={"rfq_id": body.rfq_id, "command_key": command[0] if command else None},
        )
        if command is not None:
            from ...services.booking_commands import stage_booking_command
            stage_booking_command(session, current, *command, deal)
        session.commit()
    except IntegrityError:
        session.rollback()
        if body.rfq_id:
            existing = session.exec(
                select(Deal).where(Deal.rfq_id == body.rfq_id)).first()
            if existing:
                _reject_booking(
                    session, current, body, 409,
                    f"Cette RFQ a déjà été bookée — deal {existing.reference}.")
        _reject_booking(
            session, current, body, 409,
            "Conflit d'unicité pendant le booking. Rechargez les données et réessayez.")
    session.refresh(deal)
    return _deal_row(deal, _get_events(deal.id, session), session)


@router.post("", status_code=201)
def book_deal(
    body: DealCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _book_deal(body, current, session)


class DealPortfolioAssign(BaseModel):
    portfolio_id: int


class DealPortfoliosSet(BaseModel):
    portfolio_ids: list[int] = Field(default_factory=list)


def _deal_for_portfolio_change(deal_id: int, current: User, session: Session) -> Deal:
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    from ...core.access import has_capability
    if not (has_capability(current, "business.prepare") or has_capability(current, "operations.prepare")):
        raise HTTPException(403, "Votre profil ne permet pas de modifier les vues de portefeuille.")
    return deal


def _validated_portfolios(
    portfolio_ids: list[int], deal: Deal, session: Session
) -> list[Portfolio]:
    unique_ids = list(dict.fromkeys(portfolio_ids))
    portfolios = [session.get(Portfolio, pid) for pid in unique_ids]
    if any(p is None for p in portfolios):
        raise HTTPException(404, "Portefeuille introuvable")
    if any((p.entity_id != _deal_entity_id(deal, session) if p.entity_id is not None
            else p.user_id != deal.user_id) for p in portfolios):
        raise HTTPException(
            422,
            "Chaque portefeuille doit appartenir à l’organisation du deal.",
        )
    return portfolios


@router.put("/{deal_id}/portfolios")
def set_deal_portfolios(
    deal_id: int,
    body: DealPortfoliosSet,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Replace the deal's portfolio memberships atomically.

    An empty list is valid and means that the position is explicitly
    unclassified. Portfolios are organizational views owned by the same
    account as the deal; administrators can perform the change for any
    account without crossing those ownership boundaries.
    """
    deal = _deal_for_portfolio_change(deal_id, current, session)
    portfolios = _validated_portfolios(body.portfolio_ids, deal, session)
    target_ids = {p.id for p in portfolios}
    current_memberships = session.exec(select(DealPortfolioMembership).where(
        DealPortfolioMembership.deal_id == deal.id)).all()
    current_ids = {m.portfolio_id for m in current_memberships}

    for membership in current_memberships:
        if membership.portfolio_id not in target_ids:
            session.delete(membership)
    for portfolio_id in target_ids - current_ids:
        session.add(DealPortfolioMembership(
            deal_id=deal.id,
            portfolio_id=portfolio_id,
            added_by_user_id=current.id,
        ))

    # The many-to-many table is authoritative. Clearing the old pointer also
    # removes the foreign-key dependency which used to block deletion.
    deal.portfolio_id = None
    deal.updated_at = datetime.utcnow()
    session.add(deal)
    session.commit()
    return {"id": deal.id, "portfolio_ids": sorted(target_ids)}


@router.patch("/{deal_id}/portfolio")
def assign_deal_portfolio(
    deal_id: int,
    body: DealPortfolioAssign,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Backward-compatible endpoint: add one membership without removing any."""
    deal = _deal_for_portfolio_change(deal_id, current, session)
    portfolio = _validated_portfolios([body.portfolio_id], deal, session)[0]
    existing = session.exec(select(DealPortfolioMembership).where(
        DealPortfolioMembership.deal_id == deal.id,
        DealPortfolioMembership.portfolio_id == portfolio.id,
    )).first()
    if not existing:
        session.add(DealPortfolioMembership(
            deal_id=deal.id,
            portfolio_id=portfolio.id,
            added_by_user_id=current.id,
        ))
    deal.portfolio_id = None
    session.add(deal)
    session.commit()
    portfolio_ids = session.exec(select(DealPortfolioMembership.portfolio_id).where(
        DealPortfolioMembership.deal_id == deal.id)).all()
    return {"id": deal.id, "portfolio_ids": sorted(portfolio_ids)}
