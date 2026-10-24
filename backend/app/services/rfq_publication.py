"""Human approval of an exact bank response, then atomic local delivery."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from sqlmodel import select

from ..core.audit import record_audit_event
from ..core.references import next_audited_id
from ..db.models import (Counterparty, Deal, ProductCalculationRun, RfqBankCase, RfqBankPublicationPolicy,
    RfqBankQuoteDraft, RfqDesk, RfqExchangeRound, RfqQuote, RfqQuotePublication, RfqRelationship,
    RfqRelationshipSide, RfqRequest, RfqSolicitation, RfqTransportOutbox, User)
from ..runtime import business_now
from . import rfq_bank as bank, rfq_exchange as exchange, rfq_relationships as relationships
from .product_repository import load_product
from .rfq_access import membership_rights


class PolicyPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    second_validation_required: bool
    max_calculation_age_minutes: int = Field(ge=1, le=10080)
    reason: str = Field(min_length=3, max_length=500)


class QuoteCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal["DOCUMENTATION", "CREDIT_APPROVAL", "OTHER"]
    description: str = Field(min_length=3, max_length=500)


class DraftPut(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expected_revision: int = Field(ge=0)
    calculation_id: int
    price: float = Field(gt=0, le=1000)
    firmness: Literal["INDICATIVE", "FIRM"]
    valid_until: datetime
    conditions_type: Literal["NONE", "CONDITIONAL"]
    conditions: list[QuoteCondition] = Field(default_factory=list, max_length=10)
    issuer_name: str = Field(default="", max_length=200)
    guarantor_name: str = Field(default="", max_length=200)
    documentation_reference: str = Field(default="", max_length=1000)
    comment: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def explicit_conditions(self):
        if (self.conditions_type == "NONE") != (not self.conditions):
            raise ValueError("Déclarez explicitement l’absence de conditions ou leur liste structurée")
        if any(len(row.description.strip()) < 3 for row in self.conditions):
            raise ValueError("La description des conditions est obligatoire")
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_payload_hash: str = Field(min_length=64, max_length=64)


def policy_row(policy):
    return {"configured": bool(policy), "version": policy.version if policy else 0,
        "second_validation_required": policy.second_validation_required if policy else None,
        "max_calculation_age_minutes": policy.max_calculation_age_minutes if policy else None}


def put_policy(session, item_id, user, body):
    item = exchange.require_received(session, item_id, user)
    from ..core.access import is_local_admin
    if not is_local_admin(user) or user.entity_id != item.recipient_entity_id:
        raise HTTPException(403, "La politique appartient à l’administrateur de l’organisation bancaire")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Précisez le motif de modification de politique")
    session.execute(update(RfqDesk).where(RfqDesk.id == item.recipient_desk_id)
        .values(active=RfqDesk.active).execution_options(synchronize_session=False))
    session.expire_all()
    item = exchange.require_received(session, item_id, user)
    policy = session.get(RfqBankPublicationPolicy, item.recipient_desk_id)
    if body.expected_version != (policy.version if policy else 0):
        raise HTTPException(409, "La politique a changé ; rechargez-la")
    before = policy_row(policy)
    if policy is None:
        policy = RfqBankPublicationPolicy(desk_id=item.recipient_desk_id,
            second_validation_required=body.second_validation_required,
            max_calculation_age_minutes=body.max_calculation_age_minutes, updated_by=user.id)
    else:
        policy.version += 1
        policy.second_validation_required = body.second_validation_required
        policy.max_calculation_age_minutes = body.max_calculation_age_minutes
        policy.updated_by = user.id
    policy.updated_at = business_now()
    session.add(policy)
    record_audit_event(session, result="SUCCESS", action="RFQ_PUBLICATION_POLICY_CHANGED", object_type="RFQ_DESK",
        object_id=policy.desk_id, actor_user_id=user.id, reason=body.reason.strip(), before=before, after=policy_row(policy))
    session.commit()
    return policy_row(policy)


def publication_for_quote(session, quote_id):
    return session.exec(select(RfqQuotePublication).where(RfqQuotePublication.quote_id == quote_id)).first()


def publication_state(session, row):
    if row.withdrawn_at:
        return "WITHDRAWN"
    if row.acceptance_received_at:
        return "RESERVED"
    later = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == row.solicitation_id,
        RfqQuotePublication.revision > row.revision)).first()
    if later:
        return "REPLACED"
    item = session.get(RfqSolicitation, row.solicitation_id)
    round_row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, round_row.rfq_id)
    if round_row.state != "OPEN" or rfq.status in {"clos", "sans_suite"}:
        return "ROUND_CLOSED"
    from ..db.models import RfqTransportInbox
    receipt = session.get(RfqTransportInbox, row.message_id)
    if receipt and json.loads(receipt.receipt_json)["result"] == "HISTORY":
        return "HISTORY"
    if session.get(RfqQuote, row.quote_id).status == 'expire':
        return 'HISTORY'
    value = json.loads(row.payload_json)
    if utc(value["valid_until"]) <= business_now():
        return "EXPIRED"
    return "ACTIVE"


def public_row(session, row):
    result = {"id": row.id, "revision": row.revision, "quote_id": row.quote_id,
        "state": publication_state(session, row), "response": json.loads(row.payload_json),
        "published_at": exchange.iso(row.published_at), "received_at": exchange.iso(row.delivered_at),
        "withdrawn_at": exchange.iso(row.withdrawn_at), "withdrawal_reason": row.withdrawal_reason}
    from . import rfq_transport as transport
    link = transport.link_for(session, row.solicitation_id)
    if link and link.inbound:
        result["transport"] = transport.transport_row(session, row.message_id)
        result["received_at"] = result["transport"]["received_at"] if result["transport"] else None
        if result["state"] == "ACTIVE" and not result["received_at"]:
            result["state"] = "PENDING_DELIVERY"
        if result["transport"] and result["transport"]["state"] == "DELIVERED":
            sent = session.get(RfqTransportOutbox, row.message_id)
            if json.loads(sent.receipt_json)["result"] == "HISTORY" and result["state"] == "ACTIVE":
                result["state"] = "HISTORY"
        withdrawals = session.exec(select(RfqTransportOutbox).where(
            RfqTransportOutbox.solicitation_id == row.solicitation_id,
            RfqTransportOutbox.kind == "WITHDRAW")).all()
        result["withdrawal_transport"] = next((transport.transport_row(session, entry.id) for entry in withdrawals
            if json.loads(entry.payload_json)["publication_message_id"] == row.message_id), None)
    return result


def utc(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if value.tzinfo is None:
        raise HTTPException(422, "La validité doit préciser son fuseau horaire")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def commercial_checks(session, item, case, draft, policy):
    bank.require_open(session, item)
    if not policy:
        raise HTTPException(409, "Configurez la politique de publication du desk bancaire")
    if not case or case.state != "IN_PROGRESS" or case.revision != draft.case_revision:
        raise HTTPException(409, "La responsabilité du dossier a changé ; préparez à nouveau la réponse")
    request = json.loads(item.request_json)
    payload = json.loads(draft.payload_json)
    relation = session.get(RfqRelationship, item.relationship_id)
    round_row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, round_row.rfq_id)
    if not relation or relation.version != request["recipient"]["relationship_version"]:
        raise HTTPException(409, "La relation reconnue a changé ; un nouveau tour est nécessaire")
    failures = relationships.eligibility(session, relation, rfq, currency=request["currency"], nominal=request["nominal"])
    if failures:
        raise HTTPException(409, {"message": "Relation RFQ inactive ou hors périmètre", "failures": failures})
    product = load_product(session, case.product_id)
    calc = session.get(ProductCalculationRun, draft.calculation_id)
    if not calc or calc.product_id != case.product_id or calc.terms_version != product.terms_version \
            or product.terms_fingerprint != request["terms_fingerprint"]:
        raise HTTPException(409, "Le calcul ne porte pas sur les termes reçus")
    if not product.calculations or product.calculations[-1].id != calc.id:
        raise HTTPException(409, "Un calcul plus récent existe ; préparez à nouveau la réponse")
    now = business_now()
    # Pricing receipts are issued on the operational UTC clock. Accelerated
    # business dates govern contractual validity, not the age of a calculation.
    calculation_now = datetime.utcnow()
    if calc.calculated_at > calculation_now or calculation_now - calc.calculated_at > timedelta(minutes=policy.max_calculation_age_minutes):
        raise HTTPException(409, "Le calcul privé est trop ancien pour la politique du desk")
    if utc(payload["valid_until"]) <= now:
        raise HTTPException(409, "La validité proposée est dépassée")
    if payload["firmness"] == "FIRM":
        treatment_failures = relationships.eligibility(session, relation, rfq,
            currency=request["currency"], nominal=request["nominal"], purpose="treat")
        if treatment_failures:
            raise HTTPException(422, {"message": "La relation et les accords de traitement doivent autoriser une offre ferme",
                "failures": treatment_failures})
        if not payload["documentation_reference"]:
            raise HTTPException(422, "Une offre ferme exige une documentation explicite")
        if any(not request["terms"].get(field) for field in ("strike_date", "value_date", "maturity_date", "payment_date")):
            raise HTTPException(422, "Une offre ferme exige les quatre dates contractuelles")
    return product


def save_draft(session, item_id, user, body):
    item = bank.require_action(session, item_id, user, lock=True)
    from .rfq_electronic import protect_publication
    protect_publication(session, item_id)
    case = session.get(RfqBankCase, item_id)
    if not case:
        raise HTTPException(409, "Prenez en charge et calculez le produit avant de préparer la réponse")
    bank.require_pricing(session, case, user)
    old = session.get(RfqBankQuoteDraft, item_id)
    if body.expected_revision != (old.revision if old else 0):
        raise HTTPException(409, "La préparation a changé ; rechargez le dossier")
    request = json.loads(item.request_json)
    counterpart = session.get(RfqRelationshipSide, (item.relationship_id, request["requester"]["organization_id"]))
    cp = session.get(Counterparty, counterpart.counterparty_id) if counterpart else None
    if not cp or not cp.active:
        raise HTTPException(409, "La contrepartie juridique reconnue est indisponible")
    if (request.get("instrument_family") or "").upper() == "NOTE" and (
            not body.issuer_name.strip() or not body.documentation_reference.strip()):
        raise HTTPException(422, "Une note exige un émetteur et une référence documentaire explicites")
    payload = {"format_version": 1, "nature": "COMPLIANT", "exchange_reference": request["exchange_reference"],
        "round_number": request["round_number"], "terms_version": request["terms_version"],
        "terms_fingerprint": request["terms_fingerprint"], "requester": request["requester"]["organization"],
        "organization": request["recipient"]["organization"], "desk": request["recipient"]["desk"],
        "price": body.price, "price_unit": "PERCENT_OF_NOTIONAL", "price_convention": "ALL_IN",
        "nominal": request["nominal"], "currency": request["currency"], "side": request["side"],
        "firmness": body.firmness, "valid_until": exchange.iso(utc(body.valid_until)),
        "conditions_type": body.conditions_type, "conditions": [c.model_dump() for c in body.conditions],
        "counterparty_name": cp.name, "issuer_name": body.issuer_name.strip(), "guarantor_name": body.guarantor_name.strip(),
        "documentation_reference": body.documentation_reference.strip(), "comment": body.comment.strip()}
    draft = old or RfqBankQuoteDraft(solicitation_id=item_id, case_revision=case.revision,
        calculation_id=body.calculation_id, prepared_by=user.id, payload_json="{}", payload_hash="")
    if old:
        draft.revision += 1
    draft.case_revision = case.revision
    draft.calculation_id = body.calculation_id
    draft.prepared_by = user.id
    draft.prepared_at = business_now()
    draft.payload_json = json.dumps(payload, ensure_ascii=False)
    draft.payload_hash = exchange.digest({"commercial": payload, "calculation_id": body.calculation_id, "case_revision": case.revision})
    draft.validated_by = draft.validated_at = draft.validated_hash = draft.validated_policy_version = None
    commercial_checks(session, item, case, draft, session.get(RfqBankPublicationPolicy, item.recipient_desk_id))
    session.add(draft)
    record_audit_event(session, result="SUCCESS", action="RFQ_RESPONSE_PREPARED", object_type="RFQ_SOLICITATION",
        object_id=item_id, actor_user_id=user.id, after={"revision": draft.revision, "payload_hash": draft.payload_hash})
    session.commit()


def expected_draft(session, item_id, body):
    draft = session.get(RfqBankQuoteDraft, item_id)
    if not draft or draft.revision != body.expected_revision or draft.payload_hash != body.expected_payload_hash:
        raise HTTPException(409, "Le contenu de la réponse a changé ; rechargez le récapitulatif")
    actual = exchange.digest({"commercial": json.loads(draft.payload_json), "calculation_id": draft.calculation_id,
                              "case_revision": draft.case_revision})
    if actual != draft.payload_hash:
        raise HTTPException(409, "L’empreinte de la préparation ne correspond plus à son contenu")
    return draft


def validate(session, item_id, user, body):
    item = bank.require_action(session, item_id, user, "validate_quote", lock=True)
    draft = expected_draft(session, item_id, body)
    policy = session.get(RfqBankPublicationPolicy, item.recipient_desk_id)
    commercial_checks(session, item, session.get(RfqBankCase, item_id), draft, policy)
    if policy.second_validation_required and draft.prepared_by == user.id:
        raise HTTPException(403, "Un second utilisateur habilité doit valider cette réponse")
    draft.validated_by = user.id
    draft.validated_at = business_now()
    draft.validated_hash = draft.payload_hash
    draft.validated_policy_version = policy.version
    session.add(draft)
    record_audit_event(session, result="SUCCESS", action="RFQ_RESPONSE_VALIDATED", object_type="RFQ_SOLICITATION",
        object_id=item_id, actor_user_id=user.id, after={"revision": draft.revision, "payload_hash": draft.payload_hash,
            "policy_version": policy.version})
    session.commit()


def validation_current(session, item, draft, policy):
    validator = session.get(User, draft.validated_by) if draft.validated_by else None
    return bool(policy and validator and draft.validated_hash == draft.payload_hash
                and draft.validated_policy_version == policy.version
                and "validate_quote" in membership_rights(session, item.recipient_desk_id, validator)
                and (not policy.second_validation_required or validator.id != draft.prepared_by))


def publish(session, item_id, user, body):
    item = bank.require_action(session, item_id, user, "publish_quote", lock=True)
    draft = expected_draft(session, item_id, body)
    prior = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == item_id,
        RfqQuotePublication.revision == draft.revision)).first()
    if prior:
        return public_row(session, prior)
    from .rfq_electronic import protect_publication
    protect_publication(session, item_id)
    policy = session.get(RfqBankPublicationPolicy, item.recipient_desk_id)
    commercial_checks(session, item, session.get(RfqBankCase, item_id), draft, policy)
    if not validation_current(session, item, draft, policy):
        raise HTTPException(409, "Une validation actuelle du contenu exact est requise")
    older = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == item_id)
        .order_by(RfqQuotePublication.revision.desc())).first()
    round_row = session.get(RfqExchangeRound, item.round_id)
    rfq = session.get(RfqRequest, round_row.rfq_id)
    if older and (older.acceptance_received_at or session.exec(select(Deal).where(Deal.rfq_id == rfq.id)).first()):
        raise HTTPException(409, "La cotation précédente a été acceptée ; aucun remplacement silencieux")
    now = business_now()
    payload = json.loads(draft.payload_json)
    message_id = str(uuid4())
    payload.update(response_reference=json.loads(older.payload_json)["response_reference"] if older else f"RSP-{uuid4().hex[:16]}", revision=draft.revision, message_id=message_id,
        message_type="RFQ_QUOTE", published_at=exchange.iso(now), publisher={"name": user.username, "email": user.email})
    from .legal_identity import relation_counterparty
    legal = relation_counterparty(session, rfq, item)
    quote = RfqQuote(id=next_audited_id(session, RfqQuote, "RFQ_QUOTE"), rfq_id=rfq.id,
        revision=payload['revision'],
        counterparty_id=legal.id, counterparty_name=legal.name, identity_frozen=True,
        provider=payload["organization"], contact=user.email, price=payload["price"], currency=payload["currency"],
        status="recu", firmness=payload["firmness"], valid_until=utc(payload["valid_until"]),
        quoted_at=now, created_at=now, note=payload["comment"] or None)
    from .rfq_model_reference import snapshot
    quote.model_reference_json = snapshot(session, rfq)
    session.add(quote)
    session.flush()
    row = RfqQuotePublication(solicitation_id=item_id, revision=draft.revision, quote_id=quote.id, message_id=message_id,
        payload_json=json.dumps(payload, ensure_ascii=False), published_by=user.id, published_at=now, delivered_at=now)
    session.add(row)
    session.flush()
    from . import rfq_transport as transport
    pending = transport.queue(session, item, "QUOTE", payload, user.id, message_id=message_id)
    if older:
        old_quote = session.get(RfqQuote, older.quote_id)
        old_quote.status = "expire"
        session.add(old_quote)
        if rfq.selected_quote_id == older.quote_id:
            from .rfq_quote_integrity import clear_selection
            clear_selection(rfq)
            rfq.selection_reason_code = rfq.selection_reason_note = None
    from .rfq_state import _sync_status, _sync_product_rfq
    _sync_status(rfq, session)
    _sync_product_rfq(session, rfq, user, action="PRODUCT_RFQ_RESPONSE_RECEIVED")
    record_audit_event(session, result="SUCCESS", action="RFQ_RESPONSE_PUBLISHED_AND_QUEUED" if pending else "RFQ_RESPONSE_PUBLISHED_AND_DELIVERED", object_type="RFQ_SOLICITATION",
        object_id=item_id, actor_user_id=user.id, correlation_id=message_id, after={"revision": draft.revision,
            "quote_id": quote.id, "message_id": message_id, "price": payload["price"]})
    session.commit()
    return public_row(session, row)


def withdraw(session, item_id, publication_id, user, reason):
    item = bank.require_action(session, item_id, user, "publish_quote", lock=True)
    from .rfq_electronic import protect_publication
    protect_publication(session, item_id)
    row = session.get(RfqQuotePublication, publication_id)
    if not row or row.solicitation_id != item_id:
        raise HTTPException(404, "Publication introuvable")
    if len(reason.strip()) < 3:
        raise HTTPException(422, "Précisez le motif partagé du retrait")
    rfq = session.get(RfqRequest, session.get(RfqExchangeRound, item.round_id).rfq_id)
    if row.acceptance_received_at or session.exec(select(Deal).where(Deal.rfq_id == rfq.id)).first():
        raise HTTPException(409, "Un traitement reçu ou booké protège la cotation ; déclarez une contestation")
    if row.withdrawn_at:
        return public_row(session, row)
    row.withdrawn_at, row.withdrawn_by, row.withdrawal_reason = business_now(), user.id, reason.strip()
    from .rfq_transport import queue
    queue(session, item, "WITHDRAW", {"publication_message_id": row.message_id,
        "withdrawn_at": exchange.iso(row.withdrawn_at), "reason": row.withdrawal_reason}, user.id)
    quote = session.get(RfqQuote, row.quote_id)
    quote.status = "expire"
    session.add(row); session.add(quote)
    if rfq.selected_quote_id == quote.id:
        from .rfq_quote_integrity import clear_selection
        clear_selection(rfq)
        rfq.selection_reason_code = rfq.selection_reason_note = None
    from .rfq_state import _sync_status, _sync_product_rfq
    _sync_status(rfq, session)
    _sync_product_rfq(session, rfq, user, action="PRODUCT_RFQ_RESPONSE_WITHDRAWN")
    record_audit_event(session, result="SUCCESS", action="RFQ_RESPONSE_WITHDRAWN", object_type="RFQ_SOLICITATION",
        object_id=item_id, actor_user_id=user.id, reason=row.withdrawal_reason, after={"publication_id": row.id})
    session.commit()
    return public_row(session, row)


def workspace(session, item, user):
    policy = session.get(RfqBankPublicationPolicy, item.recipient_desk_id)
    rights = membership_rights(session, item.recipient_desk_id, user)
    draft = session.get(RfqBankQuoteDraft, item.id)
    result = {"publication_policy": policy_row(policy), "quote_draft": None, "publications": []}
    if draft and rights & {"prepare", "validate_quote", "publish_quote"}:
        published = session.exec(select(RfqQuotePublication).where(RfqQuotePublication.solicitation_id == item.id,
            RfqQuotePublication.revision == draft.revision)).first()
        result["quote_draft"] = {"revision": draft.revision, "payload_hash": draft.payload_hash,
            "response": json.loads(draft.payload_json), "calculation_id": draft.calculation_id if "price" in rights else None,
            "prepared_by": draft.prepared_by, "validated_by": draft.validated_by,
            "validated_at": exchange.iso(draft.validated_at), "published": bool(published),
            "validation_current": validation_current(session, item, draft, policy)}
    result["publications"] = [public_row(session, row) for row in session.exec(select(RfqQuotePublication)
        .where(RfqQuotePublication.solicitation_id == item.id).order_by(RfqQuotePublication.revision.desc())).all()]
    return result
