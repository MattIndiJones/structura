"""Operational booking from retained evidence; private inputs stay server-side."""
import json

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import select

from ..core.access import require_booking_permission
from ..core.audit import record_audit_event
from ..core.product.inputs import terms_from_input
from ..core.rfq_controls import pricing_input_hash
from ..core.valuation_context import json_transport_fingerprint, pricing_input_payload
from ..db.models import RfqBookingEvidence, RfqQuote, RfqExecutionAgreement
from ..runtime import business_today
from .product_receipts import verify_server_receipt
from .product_repository import load_product
from .rfq_access import require_rfq_access


class ReviewBooking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(min_length=64, max_length=64)
    ccr_netting_set_id: int | None = None


def retain_evidence(session, rfq, user, receipt):
    from ..core.instance_signing import receipt_signing_secret
    from .rfq_state import compose_rfq_pricing_input, RfqPricingInput
    try:
        verified = verify_server_receipt(receipt, secret=receipt_signing_secret())
        expected = compose_rfq_pricing_input(rfq.id, RfqPricingInput(
            expected_terms_version=rfq.product_terms_version), user, session)["pricing_input"]
        expected = pricing_input_payload(expected)
        actual = verified["pricing_input"]
        actual_terms = terms_from_input(actual)
        # In-life receipts express the horizon through dated terms, without T.
        compared = {**actual, "T": actual.get("T", actual_terms.T)}
        # The inception route prices at strike and has no valuation_date field.
        # Compare that date explicitly; later dates still require in-life proof.
        compared["valuation_date"] = actual.get("valuation_date") or actual.get("strike_date")
        mismatches = [key for key, value in expected.items()
                      if json_transport_fingerprint(compared.get(key)) != json_transport_fingerprint(value)]
        if mismatches:
            raise ValueError("Le calcul ne correspond pas aux hypothèses courantes de la RFQ : " + ", ".join(mismatches))
        product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
        if actual_terms.fingerprint != product.terms_fingerprint:
            raise ValueError("Les termes du calcul diffèrent du contrat RFQ.")
        if rfq.model_price is None or abs(verified["price_pct"] - rfq.model_price) > 1e-7:
            raise ValueError("Le prix modèle diffère du calcul conservé.")
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    row = session.get(RfqBookingEvidence, rfq.id) or RfqBookingEvidence(
        rfq_id=rfq.id, terms_version=rfq.product_terms_version, input_hash=rfq.model_input_hash,
        receipt_json="", retained_by=user.id)
    row.terms_version, row.input_hash = rfq.product_terms_version, rfq.model_input_hash
    row.receipt_json, row.retained_by = json.dumps(receipt), user.id
    from ..runtime import business_now
    row.retained_at = business_now()
    session.add(row)
    record_audit_event(session, action="RFQ_BOOKING_EVIDENCE_RETAINED", object_type="RFQ",
                       object_id=rfq.id, actor_user_id=user.id, result="SUCCESS",
                       after={"input_hash": row.input_hash, "terms_version": row.terms_version})


def _context(session, rfq_id, user):
    require_booking_permission(user)
    rfq = require_rfq_access(session, rfq_id, user, "book")
    evidence = session.get(RfqBookingEvidence, rfq_id)
    params = json.loads(rfq.params_json)
    if not evidence or evidence.input_hash != pricing_input_hash(rfq.script_snapshot, params) \
            or evidence.terms_version != rfq.product_terms_version:
        raise HTTPException(409, "Un structureur doit conserver un calcul à jour de cette RFQ avant le booking.")
    from ..core.instance_signing import receipt_signing_secret
    try:
        receipt = verify_server_receipt(json.loads(evidence.receipt_json), secret=receipt_signing_secret())
    except ValueError as exc:
        raise HTTPException(409, "La preuve de calcul conservée est invalide.") from exc
    if rfq.model_input_hash != evidence.input_hash or rfq.model_price is None \
            or abs(rfq.model_price - receipt["price_pct"]) > 1e-7:
        raise HTTPException(409, "Le prix modèle ne correspond plus à la preuve conservée.")
    quote = session.get(RfqQuote, rfq.selected_quote_id) if rfq.selected_quote_id else None
    if not quote or quote.rfq_id != rfq.id:
        raise HTTPException(409, "Une réponse doit être retenue avant le booking.")
    from .rfq_quote_integrity import same_currency, selection_matches
    if not same_currency(session, rfq, quote) or not selection_matches(rfq, quote):
        raise HTTPException(409, "Requalifiez cette révision et sa devise avant le booking.")
    agreements = session.exec(select(RfqExecutionAgreement).where(
        RfqExecutionAgreement.rfq_id == rfq_id, RfqExecutionAgreement.state == "CONFIRMED")).all()
    agreement = agreements[-1] if agreements else None
    from .rfq_execution import _counterparty
    from .legal_identity import active_counterparty
    legal = (active_counterparty(session, json.loads(agreement.snapshot_json)["counterparty_id"]) if agreement
             else _counterparty(session, rfq, quote))
    counterparty = legal.name
    token = json_transport_fingerprint({"rfq": rfq.model_dump(mode="json"),
        "quote": quote.model_dump(mode="json"), "evidence": evidence.receipt_json,
        "agreement": agreement.model_dump(mode="json") if agreement else None,
        "counterparty": counterparty, "trade_date": business_today().isoformat()})
    return rfq, evidence, receipt, quote, agreement, counterparty, token


def review(session, rfq_id, user):
    rfq, evidence, receipt, quote, agreement, counterparty, token = _context(session, rfq_id, user)
    product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
    return {"rfq_id": rfq.id, "reference": rfq.reference, "name": rfq.name,
            "terms": product.terms.model_dump(mode="json"), "terms_version": rfq.product_terms_version,
            "nominal": json.loads(rfq.params_json).get("notional"),
            "side": "vente" if rfq.sens == "achat" else "achat",
            "counterparty": counterparty, "counterparty_id": (json.loads(agreement.snapshot_json)["counterparty_id"] if agreement else quote.counterparty_id), "price_traded": quote.price,
            "trade_date": business_today().isoformat(), "review_token": token,
            "legal_context": {key: getattr(rfq, key) for key in
                ("transaction_format", "instrument_family", "documentation_reference")},
            "calculation": {"calculated_at": receipt["calculated_at"], "input_hash": evidence.input_hash,
                            "retained_by": evidence.retained_by},
            "execution_agreement_id": agreement.id if agreement else None}


def book(session, rfq_id, user, command, *, book_deal):
    require_booking_permission(user)
    from sqlalchemy import update
    from ..db.models import RfqRequest
    from .rfq_access import lock_rfq_organization
    lock_rfq_organization(session, rfq_id, user, "book")
    session.execute(update(RfqRequest).where(RfqRequest.id == rfq_id).values(id=rfq_id))
    session.expire_all()
    rfq, evidence, receipt, quote, agreement, counterparty, token = _context(session, rfq_id, user)
    if token != command.review_token:
        raise HTTPException(409, "Le dossier a changé depuis la revue. Rechargez-le avant de booker.")
    if not counterparty:
        raise HTTPException(422, "La réponse retenue doit désigner une contrepartie éligible.")
    from ..core.booking_contract import DealCreate
    priced = receipt["pricing_input"]
    params = json.loads(rfq.params_json)
    body = DealCreate(
        counterparty_id=(json.loads(agreement.snapshot_json)["counterparty_id"] if agreement else quote.counterparty_id),
        product_id=rfq.product_id, product_terms_version=rfq.product_terms_version,
        rfq_id=rfq.id, execution_agreement_id=agreement.id if agreement else None,
        ccr_netting_set_id=command.ccr_netting_set_id,
        sens="vente" if rfq.sens == "achat" else "achat", contrepartie=counterparty,
        devise=params["currency"], product_type=rfq.template_type, nominal=params["notional"],
        fair_value=receipt["price_pct"], price_traded=quote.price,
        trade_date=business_today().isoformat(), strike_date=priced["strike_date"],
        value_date=priced["value_date"], maturity_date=priced["maturity_date"], payment_date=priced["payment_date"],
        T=terms_from_input(priced).T, underlyings=priced["underlyings"], observation_times=[],
        script_snapshot=rfq.script_snapshot, script_id=rfq.script_id,
        market_snapshot=receipt["market_snapshot"], pricing_receipt=json.loads(evidence.receipt_json),
        **{key: getattr(rfq, key) for key in ("client_id", "mandate_id", "opportunity_id", "primary_affiliation_id",
            "transaction_format", "instrument_family", "payoff_family", "payoff_description", "documentation_reference")})
    result = book_deal(body, user, session)
    return {"id": result["id"], "reference": result["reference"]}
