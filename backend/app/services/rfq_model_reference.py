"""Freeze the desk benchmark when a quote is received, without backfilling history."""
import json
from ..db.models import RfqBookingEvidence
from ..runtime import business_now
from ..core.rfq_controls import pricing_input_hash


def snapshot(session, rfq):
    reference = {"price": rfq.model_price,
                 "calculated_at": rfq.model_price_at.isoformat() if rfq.model_price_at else None,
                 "input_hash": rfq.model_input_hash, "retained_at": business_now().isoformat(),
                 "qualification": "UNVERIFIED_SCALAR"}
    evidence = session.get(RfqBookingEvidence, rfq.id)
    if evidence and evidence.input_hash == rfq.model_input_hash == pricing_input_hash(rfq.script_snapshot, json.loads(rfq.params_json or "{}")):
        from .product_receipts import verify_server_receipt
        from ..core.instance_signing import receipt_signing_secret
        try:
            receipt = verify_server_receipt(json.loads(evidence.receipt_json), secret=receipt_signing_secret())
            if receipt.get("price_pct") == rfq.model_price:
                reference.update(qualification="SERVER_VERIFIED", receipt=receipt,
                                 calculated_at=receipt["calculated_at"])
        except ValueError:
            pass
    return json.dumps(reference, ensure_ascii=False, allow_nan=False)
