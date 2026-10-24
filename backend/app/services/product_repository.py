"""Explicit product persistence. Callers own the transaction and commit."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import update, func
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.product.models import (
    CommercialContext, Product, ProductTerms, TradeIntent,
)
from ..core.product.models import CalculationRef
from ..core.references import next_reference
from ..core.valuation_context import canonical_fingerprint, canonical_json
from ..db.models import (
    ProductRecord, ProductTermsVersion, ProductRevision, ProductCalculationRun,
    ProductCommand, RfqOwnership, RfqRequest, User,
)


class ProductError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


def owned_record(session: Session, product_id: int, user: User, *, right: str = "price",
                 _lineage: frozenset[int] = frozenset()) -> ProductRecord:
    row = session.get(ProductRecord, product_id)
    if row is None:
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    owner = session.get(User, row.user_id)
    if owner and owner.username == "__rfq_transport__":
        raise ProductError("PRODUCT_NOT_FOUND", "Projection technique de réception inaccessible.", 404)
    if product_id in _lineage:
        raise ProductError("PRODUCT_NOT_FOUND", "Filiation produit invalide.", 404)
    if row.origin_product_id is not None:
        # A derivative must not declassify desk-restricted or private inputs.
        owned_record(session, row.origin_product_id, user,
                     _lineage=_lineage | {product_id})
    from ..core.access import has_capability
    if not has_capability(user, "business.price") or (right == "prepare" and not has_capability(user, "business.prepare")):
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    from .rfq_bank import case_for_product, private_product_access
    bank_case = case_for_product(session, product_id)
    if bank_case:
        from fastapi import HTTPException
        try:
            private_product_access(session, bank_case, user)
        except HTTPException as exc:
            raise ProductError("PRODUCT_NOT_FOUND", "Produit privé bancaire introuvable.", 404) from exc
        return row
    scoped_rfqs = session.exec(select(RfqRequest).join(
        RfqOwnership, RfqOwnership.rfq_id == RfqRequest.id).where(
            RfqRequest.product_id == product_id)).all()
    all_rfqs = session.exec(select(RfqRequest).where(RfqRequest.product_id == product_id)).all()
    from .rfq_access import effective_rights
    from ..hybrid.config import current_config
    for rfq in all_rfqs:
        if rfq not in scoped_rfqs and not (user.role == "admin" and current_config() is None):
            if not {"read", "price", right} <= effective_rights(session, rfq, user):
                raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    if scoped_rfqs:
        if row.entity_id != user.entity_id or any(
                not {"read", "price", right} <= effective_rights(session, rfq, user) for rfq in scoped_rfqs):
            raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    elif row.entity_id is not None:
        if row.entity_id != user.entity_id and not (user.role == "admin" and current_config() is None):
            raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    elif row.user_id != user.id and user.role != "admin":
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    return row


def load_product(session: Session, product_id: int, *, revision: int | None = None,
                 terms_version: int | None = None, calculation_page: tuple[int, int] | None = None) -> Product:
    row = session.get(ProductRecord, product_id)
    if row is None:
        raise ProductError("PRODUCT_NOT_FOUND", "Produit introuvable.", 404)
    projection = select(ProductRevision) if calculation_page is None else select(
        ProductRevision.terms_version, func.json_remove(ProductRevision.snapshot_json, '$.calculations').label('snapshot_json'))
    rev = session.exec(projection.where(
        ProductRevision.product_id == product_id,
        ProductRevision.revision == (row.revision if revision is None else revision),
    )).first()
    if rev is None:
        raise ProductError("PRODUCT_REVISION_NOT_FOUND", "Révision produit introuvable.", 404)
    if revision is None and terms_version is None and rev.terms_version != row.terms_version:
        raise ProductError('PRODUCT_REVISION_INCONSISTENT',
                           'La révision courante et sa version de termes sont incohérentes ; requalification requise.')
    version = rev.terms_version if terms_version is None else terms_version
    terms = session.exec(select(ProductTermsVersion).where(
        ProductTermsVersion.product_id == product_id, ProductTermsVersion.version == version,
    )).first()
    if terms is None:
        raise ProductError("PRODUCT_TERMS_NOT_FOUND", "Version des termes introuvable.", 404)
    snapshot = json.loads(rev.snapshot_json)
    if calculation_page is not None:
        offset, limit = calculation_page
        calculations = session.exec(select(
            ProductCalculationRun.id, ProductCalculationRun.terms_version, ProductCalculationRun.kind,
            ProductCalculationRun.calculated_at, ProductCalculationRun.valuation_date,
            ProductCalculationRun.source, (func.json_extract(ProductCalculationRun.result_json, '$.price') * 100).label('price'),
        ).where(ProductCalculationRun.product_id == product_id,
                ProductCalculationRun.input_revision < snapshot['revision'])
          .order_by(ProductCalculationRun.id.desc()).offset(offset).limit(limit)).all()
        snapshot['calculations'] = [dict(c._mapping) for c in reversed(calculations)]
        for c in snapshot['calculations']: c['calculated_at'] = c['calculated_at'].isoformat()
    return Product.model_validate({
        **snapshot, "terms": json.loads(terms.terms_json),
        "terms_version": version,
    })


def stage_revision(session: Session, product: Product, *, expected_revision: int,
                   actor_id: int | None, action: str, reason: str = "") -> Product:
    """Compare-and-swap the current pointer and append one coherent snapshot."""
    current = session.exec(select(ProductRecord.terms_version).where(
        ProductRecord.id == product.product_id)).first()
    if current is not None and product.terms_version < current:
        raise ProductError('PRODUCT_TERMS_STALE',
                           'La version des termes est historique ; elle ne peut pas remplacer la version courante.')
    version = session.exec(select(ProductTermsVersion).where(
        ProductTermsVersion.product_id == product.product_id,
        ProductTermsVersion.version == product.terms_version)).first()
    if version is None or version.fingerprint != product.terms_fingerprint:
        raise ProductError('PRODUCT_TERMS_INVALID', 'La version des termes ne correspond pas au Product.')
    revision = expected_revision + 1
    now = datetime.utcnow()
    result = session.execute(update(ProductRecord).where(
        ProductRecord.id == product.product_id,
        ProductRecord.revision == expected_revision,
    ).values(revision=revision, terms_version=product.terms_version, name=product.name,
             listed=product.listed, archived=product.archived, updated_at=now)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier avant de réessayer.")
    if product.commercial.opportunity_id is not None:
        from ..core.opportunity_integrity import lock_opportunity
        opportunity = lock_opportunity(session, product.commercial.opportunity_id)
        record = session.get(ProductRecord, product.product_id)
        if opportunity is None or opportunity.entity_id != record.entity_id or (
                opportunity.client_id, opportunity.mandate_id) != (
                    product.commercial.client_id, product.commercial.mandate_id):
            raise ProductError('PRODUCT_OPPORTUNITY_ATTRIBUTION_CHANGED',
                               'Le rattachement de cette opportunité a changé ; rechargez le contexte commercial.',422)
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
                      reason: str = "Conservation volontaire du produit.",
                      uat_batch_id: int | None = None,
                      action: str = "PRODUCT_SAVED") -> Product:
    if (product.product_id is not None or product.execution
            or product.indicatives or product.rfqs):
        raise ProductError("PRODUCT_CREATE_INVALID", "Un nouveau dossier ne peut pas hériter d’une exécution ou d’une RFQ.", 422)
    reference = next_reference(session, ProductRecord, f"PRD-{datetime.utcnow():%Y%m%d}-")
    row = ProductRecord(reference=reference, name=product.name, user_id=user.id,
                        entity_id=user.entity_id, data_origin=product.data_origin,
                        origin_product_id=product.origin_product_id,
                        uat_batch_id=uat_batch_id, listed=product.listed)
    session.add(row)
    session.flush()
    saved = product.model_copy(update={"product_id": row.id, "reference": reference,
                                       "terms_version": 1})
    session.add(ProductTermsVersion(product_id=row.id, version=1,
                                    fingerprint=product.terms_fingerprint,
                                    terms_json=canonical_json(product.terms.model_dump(mode="json")),
                                    reason=reason))
    return stage_revision(session, saved, expected_revision=0, actor_id=user.id,
                          action=action, reason=reason)


def stage_internal_product(
    session: Session,
    *,
    user: User,
    name: str,
    terms: ProductTerms,
    intent: TradeIntent | None = None,
    commercial: CommercialContext | None = None,
    data_origin: str = "native",
    uat_batch_id: int | None = None,
    reason: str,
) -> Product:
    """Persist the canonical hidden Product behind a durable workflow.

    RFQ and direct Booking call this before creating their own record. The
    Product identity therefore exists first and remains the common input for
    every downstream module; listing it in the library is a separate action.
    """
    product = Product(
        name=name.strip() or "Produit structuré",
        terms=terms,
        intent=intent or TradeIntent(),
        commercial=commercial or CommercialContext(),
        data_origin=data_origin,
        listed=False,
    )
    return stage_new_product(
        session, product, user=user, reason=reason,
        uat_batch_id=uat_batch_id,
        action="PRODUCT_CREATED_INTERNAL",
    )


def stage_terms(session: Session, product: Product, terms: ProductTerms, *,
                actor_id: int, reason: str) -> Product:
    from .rfq_bank import case_for_product
    if case_for_product(session, product.product_id):
        raise ProductError("RFQ_BANK_TERMS_LOCKED", "Les termes reçus sont figés ; demandez un nouveau tour au demandeur.")
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


def stage_booked_terms_amendment(session: Session, product: Product,
                                 terms: ProductTerms, *, reason: str) -> Product:
    """Append terms for a governed amendment of an already booked Product.

    Ordinary term editing remains forbidden after booking.  This narrow path
    is called only from the Deal amendment workflow, inside the same database
    transaction as the new Deal contract version.
    """
    if not product.execution:
        raise ProductError(
            "PRODUCT_NOT_BOOKED",
            "L’amendement contractuel exige un Product déjà booké.",
        )
    if terms.fingerprint == product.terms_fingerprint:
        return product
    versions = session.exec(select(ProductTermsVersion.version).where(
        ProductTermsVersion.product_id == product.product_id)).all()
    version = max(versions) + 1
    session.add(ProductTermsVersion(
        product_id=product.product_id,
        version=version,
        parent_version=product.terms_version,
        fingerprint=terms.fingerprint,
        terms_json=canonical_json(terms.model_dump(mode="json")),
        reason=reason,
    ))
    return product.model_copy(update={"terms": terms, "terms_version": version})


def lock_command_actor(session: Session, user: User):
    """Serialize one actor's commands before looking up a durable result."""
    session.execute(update(User).where(User.id == user.id).values(id=user.id)
                    .execution_options(synchronize_session=False))
    session.expire_all()


def previous_command(session: Session, user: User, key: str, payload: dict) -> Product | None:
    lock_command_actor(session, user)
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
