"""Retain and reopen signed, immutable native Product calculations."""
from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session

from ..core.product.models import CalculationRef, Product
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.models import ProductCalculationRun, User
from .product_repository import ProductError, owned_record, stage_revision


RATES_CALCULATION_KIND = "RATES_PRICING"
CREDIT_CALCULATION_KIND = "CREDIT_PRICING"


def stage_native_calculation(session: Session, product: Product, user: User, receipt: dict, *,
                             kind: str, reason: str) -> tuple[Product, int]:
    """Stage a receipt already verified against the dossier, without committing."""
    result, context = receipt["result"], receipt["context"]
    evidence = {key: value for key, value in receipt.items() if key != "result"}
    row = ProductCalculationRun(product_id=product.product_id, terms_version=product.terms_version,
                                input_revision=product.revision, kind=kind, user_id=user.id,
                                calculated_at=datetime.fromisoformat(receipt["calculated_at"]),
                                valuation_date=context["valuation_date"], source="PRICER",
                                input_hash=json_transport_fingerprint(receipt), input_json=canonical_json(evidence),
                                result_json=canonical_json(result))
    session.add(row)
    session.flush()
    measure = result["measure"]
    ref = CalculationRef(id=row.id, terms_version=product.terms_version, kind=kind, source=row.source,
                         calculated_at=receipt["calculated_at"], valuation_date=row.valuation_date,
                         price=measure["value"], measure=measure["kind"], price_unit=measure["unit"],
                         nominal=context["nominal"], side=context["side"])
    enriched = product.model_copy(update={"calculations": (*product.calculations, ref)})
    saved = stage_revision(session, enriched, expected_revision=product.revision, actor_id=user.id,
                           action="PRODUCT_CALCULATION_RETAINED", reason=reason)
    return saved, ref.id


def read_native_calculation(session: Session, product_id: int, calculation_id: int, user: User, *, kind: str) -> dict:
    record = owned_record(session, product_id, user)
    row = session.get(ProductCalculationRun, calculation_id)
    if row is None or row.product_id != product_id or row.kind != kind:
        raise ProductError("PRODUCT_CALCULATION_NOT_FOUND", "Calcul produit introuvable.", 404)
    try:
        evidence, result = json.loads(row.input_json), json.loads(row.result_json)
        receipt = {**evidence, "result": result}
        if row.input_hash != json_transport_fingerprint(receipt) or (
            receipt["context"]["product_id"], receipt["context"]["terms_version"], receipt["input_revision"], receipt["user_id"],
        ) != (product_id, row.terms_version, row.input_revision, row.user_id):
            raise ValueError("Empreinte ou références incohérentes.")
    except (ValueError, TypeError, KeyError) as exc:
        raise ProductError("NATIVE_ARCHIVE_INVALID", "Les preuves du calcul archivé sont incohérentes.") from exc
    if receipt.get("product_reference") != record.reference:
        raise ProductError("PRODUCT_CALCULATION_NOT_FOUND", "Calcul produit introuvable.", 404)
    return receipt
