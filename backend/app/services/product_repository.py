"""Explicit product persistence. Callers own the transaction and commit."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import update
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.product.models import Product, ProductTerms
from ..core.product.models import CalculationRef
from ..core.references import next_reference
from ..core.valuation_context import canonical_fingerprint, canonical_json
from ..db.models import (
    ProductRecord, ProductTermsVersion, ProductRevision, ProductCalculationRun,
    ProductCommand, User,
)


class ProductError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


def owned_record(session: Session, product_id: int, user: User) -> ProductRecord:
    row = session.get(ProductRecord, product_id)
    if row is None or (row.user_id != user.id and user.role != "admin"):
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    return row


def load_product(session: Session, product_id: int, *, revision: int | None = None,
                 terms_version: int | None = None) -> Product:
    row = session.get(ProductRecord, product_id)
    if row is None:
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    rev = session.exec(select(ProductRevision).where(
        ProductRevision.product_id == product_id,
        ProductRevision.revision == (row.revision if revision is None else revision),
    )).first()
    if rev is None:
        raise ProductError("PRODUCT_REVISION_NOT_FOUND", "Révision produit introuvable.", 404)
    version = rev.terms_version if terms_version is None else terms_version
    terms = session.exec(select(ProductTermsVersion).where(
        ProductTermsVersion.product_id == product_id, ProductTermsVersion.version == version,
    )).first()
    if terms is None:
        raise ProductError("PRODUCT_TERMS_NOT_FOUND", "Version des termes introuvable.", 404)
    return Product.model_validate({
        **json.loads(rev.snapshot_json), "terms": json.loads(terms.terms_json),
        "terms_version": version,
    })


def stage_revision(session: Session, product: Product, *, expected_revision: int,
                   actor_id: int | None, action: str, reason: str = "") -> Product:
    """Compare-and-swap the current pointer and append one coherent snapshot."""
    revision = expected_revision + 1
    now = datetime.utcnow()
    result = session.execute(update(ProductRecord).where(
        ProductRecord.id == product.product_id,
        ProductRecord.revision == expected_revision,
    ).values(revision=revision, terms_version=product.terms_version, name=product.name,
             archived=product.archived, updated_at=now)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier avant de réessayer.")
    saved = product.model_copy(update={"revision": revision})
    payload = saved.to_dict()
    payload.pop("terms")
    session.add(ProductRevision(
        product_id=product.product_id, revision=revision, terms_version=product.terms_version,
        snapshot_json=canonical_json(payload), actor_user_id=actor_id,
        action=action, reason=reason,
    ))
    record_audit_event(session, action=action, object_type="PRODUCT", object_id=product.product_id,
                       actor_user_id=actor_id, result="SUCCESS", reason=reason,
                       before={"revision": expected_revision},
                       after={"revision": revision, "terms_version": product.terms_version,
                              "terms_fingerprint": product.terms_fingerprint})
    session.flush()
    session.expire_all()
    return saved


def stage_new_product(session: Session, product: Product, *, user: User,
                      reason: str = "Conservation volontaire du produit.") -> Product:
    if product.product_id is not None or product.execution or product.rfqs:
        raise ProductError("PRODUCT_CREATE_INVALID", "Un nouveau dossier ne peut pas hériter d’une exécution ou d’une RFQ.", 422)
    reference = next_reference(session, ProductRecord, f"PRD-{datetime.utcnow():%Y%m%d}-")
    row = ProductRecord(reference=reference, name=product.name, user_id=user.id,
                        entity_id=user.entity_id, data_origin=product.data_origin,
                        origin_product_id=product.origin_product_id)
    session.add(row)
    session.flush()
    saved = product.model_copy(update={"product_id": row.id, "reference": reference,
                                       "terms_version": 1})
    session.add(ProductTermsVersion(product_id=row.id, version=1,
                                    fingerprint=product.terms_fingerprint,
                                    terms_json=canonical_json(product.terms.model_dump(mode="json")),
                                    reason=reason))
    return stage_revision(session, saved, expected_revision=0, actor_id=user.id,
                          action="PRODUCT_SAVED", reason=reason)


def stage_terms(session: Session, product: Product, terms: ProductTerms, *,
                actor_id: int, reason: str) -> Product:
    if product.execution:
        raise ProductError("PRODUCT_BOOKED", "Les termes sont bookés. Utilisez le workflow d’amendement.")
    if terms.fingerprint == product.terms_fingerprint:
        return product
    versions = session.exec(select(ProductTermsVersion.version).where(
        ProductTermsVersion.product_id == product.product_id)).all()
    version = max(versions) + 1
    session.add(ProductTermsVersion(
        product_id=product.product_id, version=version, parent_version=product.terms_version,
        fingerprint=terms.fingerprint, terms_json=canonical_json(terms.model_dump(mode="json")),
        reason=reason,
    ))
    return product.model_copy(update={"terms": terms, "terms_version": version})


def previous_command(session: Session, user: User, key: str, payload: dict) -> Product | None:
    command = session.exec(select(ProductCommand).where(
        ProductCommand.user_id == user.id, ProductCommand.command_key == key)).first()
    if command is None:
        return None
    if command.input_hash != canonical_fingerprint(payload):
        raise ProductError("PRODUCT_COMMAND_CONFLICT", "Cette clé de commande a déjà été utilisée avec un autre contenu.")
    owned_record(session, command.product_id, user)
    return load_product(session, command.product_id, revision=command.result_revision)


def stage_command(session: Session, user: User, key: str, payload: dict, product: Product):
    session.add(ProductCommand(user_id=user.id, command_key=key,
                               input_hash=canonical_fingerprint(payload),
                               product_id=product.product_id, result_revision=product.revision))
    session.flush()


def stage_calculation(session: Session, product: Product, *, user: User,
                      receipt: dict, source: str = "PRICER") -> Product:
    """Append a completed server calculation and return the enriched snapshot."""
    calculated_at = datetime.fromisoformat(receipt["calculated_at"])
    pricing_input = receipt["pricing_input"]
    result = receipt["result"]
    valuation_date = (pricing_input.get("valuation_date")
                      or pricing_input.get("strike_date"))
    row = ProductCalculationRun(
        product_id=product.product_id,
        terms_version=product.terms_version,
        input_revision=product.revision,
        kind="PRICING",
        user_id=user.id,
        calculated_at=calculated_at,
        valuation_date=valuation_date,
        source=source,
        input_hash=receipt["input_fingerprint"],
        input_json=canonical_json(pricing_input),
        result_json=canonical_json(result),
    )
    session.add(row)
    session.flush()
    calculation = CalculationRef(
        id=row.id,
        terms_version=product.terms_version,
        kind=row.kind,
        calculated_at=calculated_at.isoformat(),
        valuation_date=valuation_date,
        price=receipt.get("price_pct"),
        source=source,
    )
    return product.model_copy(update={
        "calculations": (*product.calculations, calculation),
    })
