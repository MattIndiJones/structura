"""Persisted Product dossiers shared by pricing and downstream modules."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, update
from sqlmodel import Session, select

from .auth import get_current_pricer, receipt_signing_secret
from ..core.product.inputs import describe_product, pricing_input, terms_from_input
from ..core.product.models import CommercialContext, Product, TradeIntent
from ..core.schemas import PricingRequest
from ..core.valuation_context import (
    json_transport_fingerprint, market_snapshot_from_pricing_input,
    pricing_input_payload, verify_pricing_receipt,
)
from ..db.database import get_session
from ..db.models import ProductCalculationRun, ProductRecord, ProductRevision, User
from ..services.product_receipts import verify_server_receipt
from ..services.product_repository import (
    ProductError, load_product, owned_record, previous_command,
    stage_calculation, stage_command, stage_new_product, stage_revision, stage_terms,
)


router = APIRouter(prefix="/api/products", tags=["products"])


class ProductCreate(BaseModel):
    command_key: str = Field(min_length=8, max_length=100)
    name: str = Field(default="", max_length=200)
    pricing_input: dict
    pricing_receipt: dict | None = None
    listed: bool = True
    intent: TradeIntent = Field(default_factory=TradeIntent)
    commercial: CommercialContext = Field(default_factory=CommercialContext)


class ProductUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    intent: TradeIntent | None = None
    commercial: CommercialContext | None = None
    listed: bool | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def has_change(self):
        if (self.name is None and self.intent is None and self.commercial is None
                and self.listed is None):
            raise ValueError("Aucune modification demandée.")
        return self


class ProductTermsUpdate(BaseModel):
    command_key: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=1)
    pricing_input: dict
    reason: str = Field(min_length=3, max_length=1000)


class ProductArchive(BaseModel):
    expected_revision: int = Field(ge=1)
    archived: bool
    reason: str = Field(min_length=3, max_length=1000)


class ProductPricingInput(BaseModel):
    expected_terms_version: int = Field(ge=1)
    context: dict


class ProductCalculationCreate(BaseModel):
    command_key: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=1)
    pricing_receipt: dict


class ProductBookingFork(BaseModel):
    command_key: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=1)
    expected_terms_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=1000)


class RetainedDraftInput(PricingRequest):
    # Retaining work is allowed before its contractual horizon is known.
    T: float | None = Field(default=None, gt=0, le=30)


def _fail(exc: ProductError):
    raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)})


def _validated_pricing_input(payload: dict, *, draft: bool = False) -> dict:
    if draft:
        payload = {k: (None if v == '' and k in {
            'strike_date', 'value_date', 'maturity_date', 'payment_date', 'anchor'} else v)
            for k, v in payload.items()}
        return pricing_input_payload(RetainedDraftInput.model_validate(payload))
    if "valuation_date" in payload or "strike_levels" in payload:
        from .inlife import InLifePricingRequest
        return pricing_input_payload(InLifePricingRequest.model_validate(payload))
    return pricing_input_payload(PricingRequest.model_validate(payload))


def _default_name(pricing_payload: dict) -> str:
    for line in pricing_payload.get("script", "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and stripped[1:].strip():
            return stripped[1:].strip()[:200]
    return "Produit structuré"


def _row_summary(row: ProductRecord, product: Product) -> dict:
    stage = (
        "BOOKED" if product.execution else
        "RFQ" if product.rfqs else
        "INDICATIVE" if product.indicatives else
        "SAVED"
    )
    return {
        "id": row.id,
        "reference": row.reference,
        "name": row.name,
        "revision": row.revision,
        "terms_version": row.terms_version,
        "archived": row.archived,
        "listed": row.listed,
        "data_origin": row.data_origin,
        "stage": stage,
        "underlyings": [u.model_dump(mode="json") for u in product.terms.underlyings],
        "maturity_date": (product.terms.maturity_date.isoformat()
                          if product.terms.maturity_date else None),
        "latest_price": next((c.price for c in reversed(product.calculations) if c.terms_version == product.terms_version), None),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("", status_code=201)
def create_product(
    body: ProductCreate,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    return _create_product(body, current, session)


def _create_product(
    body: ProductCreate,
    current: User,
    session: Session,
    *,
    data_origin: Literal["native", "demo", "uat", "imported"] = "native",
    uat_batch_id: int | None = None,
):
    """Shared creation path used by the Pricer and explicit UAT batches."""
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            session.rollback()
            return prior.to_dict()

        validated = _validated_pricing_input(body.pricing_input, draft=body.pricing_receipt is None)
        product = Product(
            name=(body.name.strip() or _default_name(validated)),
            terms=terms_from_input(validated, allow_unresolved=True),
            intent=body.intent,
            commercial=body.commercial,
            data_origin=data_origin,
            listed=body.listed,
        )
        product = stage_new_product(
            session, product, user=current, uat_batch_id=uat_batch_id,
            reason=("Conservation volontaire du produit." if body.listed else
                    "Création interne avant transfert vers un module."),
            action=("PRODUCT_SAVED" if body.listed else
                    "PRODUCT_CREATED_INTERNAL"),
        )

        if body.pricing_receipt is not None:
            receipt = verify_server_receipt(
                body.pricing_receipt, secret=receipt_signing_secret())
            receipt = verify_pricing_receipt(receipt)
            if json_transport_fingerprint(
                    receipt["pricing_input"]) != json_transport_fingerprint(validated):
                raise ProductError(
                    "PRODUCT_RECEIPT_MISMATCH",
                    "Le prix conservé ne correspond pas aux entrées du produit.", 422)
            enriched = stage_calculation(session, product, user=current, receipt=receipt)
            product = stage_revision(
                session, enriched, expected_revision=product.revision,
                actor_id=current.id, action="PRODUCT_CALCULATION_RETAINED",
                reason="Conservation du calcul courant avec le produit.")

        stage_command(session, current, body.command_key, command_payload, product)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        session.rollback()
        raise


@router.post("/{product_id}/booking-forks", status_code=201)
def fork_product_for_booking(
    product_id: int, body: ProductBookingFork,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    """A new trade gets its own dossier, with explicit restricted lineage."""
    payload = {'operation': 'booking_fork', 'source_product_id': product_id,
               **body.model_dump(mode='json', exclude={'command_key'})}
    try:
        prior = previous_command(session, current, body.command_key, payload)
        if prior is not None:
            owned_record(session, product_id, current, right='prepare')
            session.rollback()
            return prior.to_dict()
        row = owned_record(session, product_id, current, right='prepare')
        from ..services.rfq_bank import case_for_product
        if case_for_product(session, product_id):
            raise ProductError('PRODUCT_PRIVATE_FORK_FORBIDDEN',
                'Un calcul privé bancaire doit rester dans son parcours RFQ.')
        session.execute(update(ProductRecord).where(ProductRecord.id == product_id)
                        .values(id=product_id).execution_options(synchronize_session=False))
        session.refresh(row)
        if row.revision != body.expected_revision:
            raise ProductError('PRODUCT_REVISION_STALE',
                'Le dossier source a changé ; rechargez-le avant de créer une autre opération.')
        source = load_product(session, product_id, terms_version=body.expected_terms_version)
        child = Product(name=source.name, terms=source.terms,
            origin_product_id=product_id, data_origin=source.data_origin, listed=False,
            intent=source.intent.model_copy(update={'counterparty_id': None}))
        child = stage_new_product(session, child, user=current, uat_batch_id=row.uat_batch_id,
            action='PRODUCT_FORKED_FOR_BOOKING', reason=body.reason)
        from ..core.audit import record_audit_event
        record_audit_event(session, action='PRODUCT_BOOKING_LINEAGE_RECORDED',
            object_type='PRODUCT', object_id=child.product_id, actor_user_id=current.id,
            result='SUCCESS', reason=body.reason,
            after={'origin_product_id': product_id, 'origin_revision': source.revision,
                   'origin_terms_version': source.terms_version,
                   'origin_terms_fingerprint': source.terms_fingerprint,
                   'detached_rfq_ids': [item.to_dict().get('id') for item in source.rfqs],
                   'detached_indicative_ids': [item.to_dict().get('id') for item in source.indicatives],
                   'detached_deal_id': source.execution.to_dict().get('deal_id') if source.execution else None})
        stage_command(session, current, body.command_key, payload, child)
        session.commit()
        return child.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except Exception:
        session.rollback()
        raise


@router.get("")
def list_products(
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
    archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    paged: bool = False,
):
    query = select(ProductRecord).where(
        ProductRecord.archived == archived,
        ProductRecord.listed == True,  # noqa: E712
    )
    if current.role != 'admin':
        query = query.where(or_(ProductRecord.entity_id == current.entity_id if current.entity_id is not None else False,
            (ProductRecord.entity_id.is_(None)) & (ProductRecord.user_id == current.id)))
    rows = session.exec(query.order_by(ProductRecord.updated_at.desc(), ProductRecord.id.desc())).yield_per(100)
    visible = []
    skipped = 0
    for row in rows:
        try:
            owned_record(session, row.id, current)
        except ProductError:
            continue
        if skipped < offset:
            skipped += 1
            continue
        if len(visible) == limit:
            return {'items': visible, 'offset': offset, 'limit': limit, 'has_more': True} if paged else visible
        product = load_product(session, row.id, calculation_page=(0, 0))
        summary = _row_summary(row, product)
        latest = session.exec(select(ProductCalculationRun.terms_version,
            (func.json_extract(ProductCalculationRun.result_json, '$.price') * 100).label('price'))
            .where(ProductCalculationRun.product_id == row.id, ProductCalculationRun.terms_version == row.terms_version)
            .order_by(ProductCalculationRun.id.desc()).limit(1)).first()
        historical = session.exec(select(ProductCalculationRun.terms_version,
            (func.json_extract(ProductCalculationRun.result_json, '$.price') * 100).label('price'))
            .where(ProductCalculationRun.product_id == row.id).order_by(ProductCalculationRun.id.desc()).limit(1)).first()
        summary.update(latest_price=latest.price if latest else None,
            latest_price_terms_version=latest.terms_version if latest else None,
            historical_price=historical.price if historical and not latest else None,
            historical_price_terms_version=historical.terms_version if historical and not latest else None)
        visible.append(summary)
    return {'items': visible, 'offset': offset, 'limit': limit, 'has_more': False} if paged else visible


@router.get("/{product_id}")
def get_product(
    product_id: int,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
    revision: int | None = None,
    terms_version: int | None = None,
    calculations_limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    calculations_offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        owned_record(session, product_id, current)
        product = load_product(session, product_id, revision=revision, terms_version=terms_version,
            calculation_page=None if calculations_limit is None else (calculations_offset, calculations_limit + 1))
        data = product.to_dict()
        if calculations_limit is not None:
            calculations = data['calculations']
            data['calculations'] = calculations[-calculations_limit:]
            data['calculation_page'] = {'offset': calculations_offset, 'limit': calculations_limit,
                'has_more': len(calculations) > calculations_limit}
        return {**data, "description": describe_product(product)}
    except ProductError as exc:
        _fail(exc)


@router.get('/{product_id}/history')
def product_history(product_id: int, current: Annotated[User, Depends(get_current_pricer)],
                    session: Annotated[Session, Depends(get_session)],
                    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    try:
        owned_record(session, product_id, current)
    except ProductError as exc:
        _fail(exc)
    rows = session.exec(select(ProductRevision.revision, ProductRevision.terms_version,
        ProductRevision.action, ProductRevision.reason, ProductRevision.created_at)
        .where(ProductRevision.product_id == product_id).order_by(ProductRevision.revision.desc())
        .offset(offset).limit(limit + 1)).all()
    return {'items': [dict(row._mapping) for row in rows[:limit]], 'offset': offset,
            'limit': limit, 'has_more': len(rows) > limit}


@router.patch("/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current, right="prepare")
        from ..services.rfq_bank import case_for_product
        if case_for_product(session, product_id) and (body.intent is not None or body.commercial is not None):
            raise ProductError("RFQ_BANK_INTENT_LOCKED", "Le nominal, le sens et la demande reçue sont figés.")
        product = load_product(session, product_id)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")
        if product.execution and (body.intent is not None or body.commercial is not None):
            raise ProductError('PRODUCT_BOOKED_CONTEXT_LOCKED',
                               'Le nominal, le sens et le contexte commercial sont bookés. Utilisez une rectification gouvernée.')
        changes = {}
        if body.name is not None:
            changes["name"] = body.name.strip() or product.name
        if body.intent is not None:
            changes["intent"] = body.intent
        if body.commercial is not None:
            changes["commercial"] = body.commercial
        if body.listed is not None:
            changes["listed"] = body.listed
        action = "PRODUCT_CONTEXT_UPDATED"
        if body.listed is not None and body.listed != product.listed:
            action = "PRODUCT_LISTED" if body.listed else "PRODUCT_UNLISTED"
        product = stage_revision(
            session, product.model_copy(update=changes),
            expected_revision=body.expected_revision, actor_id=current.id,
            action=action, reason=body.reason)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)


@router.post("/{product_id}/terms")
def revise_product_terms(
    product_id: int,
    body: ProductTermsUpdate,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            if prior.product_id != product_id:
                raise ProductError("PRODUCT_COMMAND_CONFLICT", "La commande désigne un autre produit.")
            session.rollback()
            return prior.to_dict()
        owned_record(session, product_id, current, right="prepare")
        product = load_product(session, product_id)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")
        validated = _validated_pricing_input(body.pricing_input, draft=True)
        changed = stage_terms(
            session, product, terms_from_input(validated, allow_unresolved=True),
            actor_id=current.id, reason=body.reason)
        if changed is product:
            stage_command(session, current, body.command_key, command_payload, product)
            session.commit()
            return product.to_dict()
        product = stage_revision(
            session, changed, expected_revision=body.expected_revision,
            actor_id=current.id, action="PRODUCT_TERMS_REVISED", reason=body.reason)
        stage_command(session, current, body.command_key, command_payload, product)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        session.rollback()
        raise


@router.post("/{product_id}/archive")
def archive_product(
    product_id: int,
    body: ProductArchive,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current, right="prepare")
        product = load_product(session, product_id)
        product = stage_revision(
            session, product.model_copy(update={"archived": body.archived}),
            expected_revision=body.expected_revision, actor_id=current.id,
            action="PRODUCT_ARCHIVED" if body.archived else "PRODUCT_RESTORED",
            reason=body.reason)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)


@router.post("/{product_id}/pricing-input")
def compose_product_pricing_input(
    product_id: int,
    body: ProductPricingInput,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
        from ..services.rfq_bank import case_for_product, require_pricing
        bank_case = case_for_product(session, product_id)
        if bank_case:
            require_pricing(session, bank_case, current)
        product = load_product(session, product_id)
        if product.terms_version != body.expected_terms_version:
            raise ProductError(
                "PRODUCT_TERMS_STALE",
                "Les termes du produit ont changé. Rechargez le dossier.")
        return pricing_input(product, body.context)
    except ProductError as exc:
        _fail(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{product_id}/calculations")
def retain_product_calculation(
    product_id: int,
    body: ProductCalculationCreate,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    """Append one server-produced calculation without changing product terms."""
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        owned_record(session, product_id, current)
        from ..services.rfq_bank import case_for_product, require_pricing
        bank_case = case_for_product(session, product_id)
        if bank_case:
            require_pricing(session, bank_case, current)
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            if prior.product_id != product_id:
                raise ProductError(
                    "PRODUCT_COMMAND_CONFLICT",
                    "La commande désigne un autre produit.")
            session.rollback()
            return prior.to_dict()

        owned_record(session, product_id, current)
        product = load_product(session, product_id)
        if product.revision != body.expected_revision:
            raise ProductError(
                "PRODUCT_REVISION_STALE",
                "Le produit a changé. Rechargez le dossier.")

        receipt = verify_server_receipt(
            body.pricing_receipt, secret=receipt_signing_secret())
        receipt = verify_pricing_receipt(receipt)
        validated = _validated_pricing_input(receipt["pricing_input"])
        if json_transport_fingerprint(
                receipt["pricing_input"]) != json_transport_fingerprint(validated):
            raise ProductError(
                "PRODUCT_RECEIPT_MISMATCH",
                "Le reçu de calcul ne correspond pas à ses entrées.", 422)
        calculated_terms = terms_from_input(validated, allow_unresolved=True)
        if calculated_terms.fingerprint != product.terms_fingerprint:
            raise ProductError(
                "PRODUCT_CALCULATION_TERMS_MISMATCH",
                "Ce calcul porte sur d’autres termes que la version courante du produit.",
                422)

        enriched = stage_calculation(
            session, product, user=current, receipt=receipt)
        product = stage_revision(
            session, enriched, expected_revision=body.expected_revision,
            actor_id=current.id, action="PRODUCT_CALCULATION_RETAINED",
            reason="Conservation volontaire d’un nouveau calcul daté.")
        stage_command(session, current, body.command_key, command_payload, product)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        session.rollback()
        raise


@router.get("/{product_id}/calculations/{calculation_id}")
def get_product_calculation(
    product_id: int,
    calculation_id: int,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
    except ProductError as exc:
        _fail(exc)
    row = session.get(ProductCalculationRun, calculation_id)
    if row is None or row.product_id != product_id:
        raise HTTPException(status_code=404, detail="Calcul produit introuvable.")
    pricing_input = json.loads(row.input_json)
    previous = session.exec(select(ProductCalculationRun.id).where(
        ProductCalculationRun.product_id == product_id, ProductCalculationRun.terms_version == row.terms_version,
        ProductCalculationRun.id < row.id).order_by(ProductCalculationRun.id.desc()).limit(1)).first()
    return {
        "id": row.id,
        "product_id": row.product_id,
        "terms_version": row.terms_version,
        "input_revision": row.input_revision,
        "kind": row.kind,
        "calculated_at": row.calculated_at.isoformat(),
        "valuation_date": row.valuation_date,
        "source": row.source,
        "input_hash": row.input_hash,
        "input": pricing_input,
        "previous_calculation_id": previous,
        # The Product keeps contractual terms only. Market assumptions belong
        # to each dated calculation and are reconstructed from its immutable,
        # fingerprinted engine input, including for calculations retained
        # before this field was exposed by the API.
        "market_snapshot": market_snapshot_from_pricing_input(pricing_input),
        "result": json.loads(row.result_json),
        "calculation_identity": json.loads(row.result_json).get("calculation_identity"),
        "archive_warnings": ([] if json.loads(row.result_json).get("calculation_identity") else
                             ["Ancien calcul sans identité de moteur : résultat conservé, rejeu non qualifié."]),
    }
