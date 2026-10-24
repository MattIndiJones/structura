"""Native bank Product and desk responsibility; no commercial price publication."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.product.inputs import terms_from_input
from ..core.product.models import ProductTerms, TradeIntent
from ..db.models import RfqBankCase, RfqExchangeRound, RfqSolicitation, User
from ..runtime import business_now
from . import rfq_exchange as exchange
from .product_repository import load_product, stage_internal_product
from .rfq_access import membership_rights


def case_for_product(session, product_id):
    return session.exec(select(RfqBankCase).where(RfqBankCase.product_id == product_id)).first()


def require_action(session, item_id, user, right="prepare", *, lock=False):
    item = exchange.require_received(session, item_id, user)
    if right not in membership_rights(session, item.recipient_desk_id, user):
        raise HTTPException(403, "Habilitation bancaire insuffisante pour cette action")
    if lock:
        session.execute(update(RfqSolicitation).where(RfqSolicitation.id == item_id)
            .values(message_id=item.message_id).execution_options(synchronize_session=False))
        session.expire_all()
        item = exchange.require_received(session, item_id, user)
        if right not in membership_rights(session, item.recipient_desk_id, user):
            raise HTTPException(403, "Habilitation bancaire révoquée")
    return item


def require_open(session, item):
    row = session.get(RfqExchangeRound, item.round_id)
    request = json.loads(item.request_json)
    if row.state != "OPEN":
        raise HTTPException(409, "Le tour reçu a été remplacé ou clôturé")
    from ..db.models import RfqRequest
    rfq = session.get(RfqRequest, row.rfq_id)
    if rfq.status in {"clos", "sans_suite"}:
        raise HTTPException(409, "La consultation est clôturée")
    deadline = request.get("response_deadline")
    if deadline:
        from datetime import datetime, timezone
        end = datetime.fromisoformat(deadline.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        if end <= business_now():
            raise HTTPException(409, "Le délai de réponse de ce tour est dépassé")


def work_row(session, item, user):
    from .rfq_reconciliation import confirmed_booking_pending
    case = session.get(RfqBankCase, item.id)
    rights = membership_rights(session, item.recipient_desk_id, user)
    row = {"case": None, "rights": sorted(rights), "open_for_work": True, "block_reason": None,
           "booking_recovery_available": bool(case and case.responsible_user_id == user.id
               and {'book','price'} <= rights and confirmed_booking_pending(session,item.id))}
    try:
        require_open(session, item)
    except HTTPException as exc:
        row.update(open_for_work=False, block_reason=exc.detail)
    if case:
        person = session.get(User, case.responsible_user_id)
        row["case"] = {"responsible_user_id": case.responsible_user_id,
            "responsible_name": person.username if person else None,
            "revision": case.revision, "state": case.state,
            "private_note": case.private_note if "prepare" in rights else None}
        if "price" in rights:
            product = load_product(session, case.product_id)
            row["case"].update(product_id=case.product_id, product_reference=product.reference,
                terms_version=product.terms_version, terms_fingerprint=product.terms_fingerprint,
                calculations=[_calculation_row(entry) for entry in product.calculations])
    return row


def _calculation_row(entry):
    row = entry.model_dump(mode="json")
    # Stored pricing receipts use naive UTC. Make the instant explicit at the
    # browser boundary, including for previously retained private calculations.
    instant = datetime.fromisoformat(entry.calculated_at.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    row["calculated_at"] = instant.astimezone(timezone.utc).isoformat()
    return row


def claim(session, item_id, user):
    item = require_action(session, item_id, user, lock=True)
    require_open(session, item)
    existing = session.get(RfqBankCase, item_id)
    if existing:
        if existing.responsible_user_id != user.id:
            raise HTTPException(409, "Cette RFQ est déjà prise en charge ; utilisez une réaffectation explicite")
        if existing.state != "IN_PROGRESS":
            raise HTTPException(409, "Cette RFQ a été déclinée")
        return work_row(session, item, user)
    request = json.loads(item.request_json)
    try:
        if request.get("format_version") != 1 or request.get("product_model", {}).get("payscript_semantics_version") != 1:
            raise ValueError("Version de demande ou de PayScript non prise en charge")
        terms = ProductTerms.model_validate(request["terms"])
        terms.require_complete()
        if terms.fingerprint != request["terms_fingerprint"]:
            raise ValueError("L’empreinte des termes reçus est incohérente")
        # Validate current engine compatibility; retain the received terms verbatim.
        checked = terms_from_input(terms.pricing_fields())
        if checked.fingerprint != terms.fingerprint:
            raise ValueError("Le calendrier ou les paramètres reçus ne sont pas compatibles avec le moteur courant")
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, {"code": "RFQ_RECEIVED_TERMS_UNSUPPORTED", "message": str(exc)}) from exc
    product = stage_internal_product(session, user=user, name=request["title"], terms=terms,
        intent=TradeIntent(nominal=request["nominal"], side="SELL" if request["side"] == "BUY" else "BUY",
            transaction_format=request.get("transaction_format") or "",
            instrument_family=request.get("instrument_family") or "",
            payoff_family=request.get("payoff_family") or "",
            documentation_reference=request.get("documentation_reference") or ""),
        data_origin="imported", reason=f"Prise en charge bancaire de {request['exchange_reference']} tour {request['round_number']}.")
    case = RfqBankCase(solicitation_id=item.id, product_id=product.product_id, responsible_user_id=user.id,
                       created_at=business_now(), updated_at=business_now())
    session.add(case)
    record_audit_event(session, result="SUCCESS", action="RFQ_BANK_CLAIMED", object_type="RFQ_SOLICITATION",
        object_id=item.id, actor_user_id=user.id, correlation_id=item.message_id,
        after={"product_id": product.product_id, "terms_fingerprint": product.terms_fingerprint,
               "responsible_user_id": user.id})
    session.commit()
    return work_row(session, item, user)


def assign(session, item_id, user, target_id, expected_revision, reason):
    if len(reason.strip()) < 3:
        raise HTTPException(422, "Précisez le motif de réaffectation")
    item = require_action(session, item_id, user, lock=True)
    from .rfq_reconciliation import confirmed_booking_pending
    if not confirmed_booking_pending(session,item.id):
        require_open(session, item)
    case = session.get(RfqBankCase, item_id)
    if not case or case.state != "IN_PROGRESS":
        raise HTTPException(409, "Prenez en charge une RFQ active avant réaffectation")
    if case.responsible_user_id != user.id and "organize" not in membership_rights(session, item.recipient_desk_id, user):
        raise HTTPException(403, "Seul le responsable ou un organisateur du desk peut réaffecter")
    target = session.get(User, target_id)
    if not target or not {"read", "prepare", "price"} <= membership_rights(session, item.recipient_desk_id, target):
        raise HTTPException(422, "Choisissez un membre actif du desk habilité à prendre en charge et pricer")
    if case.revision != expected_revision:
        raise HTTPException(409, "La prise en charge a changé ; rechargez le dossier")
    before = case.responsible_user_id
    case.responsible_user_id = target_id
    case.revision += 1
    case.updated_at = business_now()
    session.add(case)
    record_audit_event(session, result="SUCCESS", action="RFQ_BANK_ASSIGNED", object_type="RFQ_SOLICITATION",
        object_id=item.id, actor_user_id=user.id, reason=reason,
        before={"responsible_user_id": before}, after={"responsible_user_id": target_id})
    session.commit()
    return work_row(session, item, user)


def private_product_access(session, case, user):
    item = exchange.require_received(session, case.solicitation_id, user)
    if "price" not in membership_rights(session, item.recipient_desk_id, user):
        raise HTTPException(404, "Produit privé bancaire introuvable")
    return item


def require_pricing(session, case, user):
    item = private_product_access(session, case, user)
    from .rfq_reconciliation import confirmed_booking_pending
    if not confirmed_booking_pending(session,item.id):
        require_open(session, item)
    if case.state != "IN_PROGRESS":
        raise HTTPException(409, "Cette RFQ a été déclinée")
    if case.responsible_user_id != user.id:
        raise HTTPException(403, "Le calcul doit être préparé par le responsable ; réaffectez explicitement le dossier")
    return item
