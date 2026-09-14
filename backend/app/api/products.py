"""Persisted Product dossiers shared by pricing and downstream modules."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from .auth import get_current_user, receipt_signing_secret
from ..core.product.inputs import describe_product, pricing_input, terms_from_input
from ..core.product.models import CommercialContext, Product, TradeIntent
from ..core.schemas import PricingRequest
from ..core.valuation_context import (
    json_transport_fingerprint, pricing_input_payload, verify_pricing_receipt,
)
from ..db.database import get_session
from ..db.models import ProductCalculationRun, ProductRecord, User
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
    intent: TradeIntent = Field(default_factory=TradeIntent)
    commercial: CommercialContext = Field(default_factory=CommercialContext)


class ProductUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    intent: TradeIntent | None = None
    commercial: CommercialContext | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def has_change(self):
        if self.name is None and self.intent is None and self.commercial is None:
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


def _fail(exc: ProductError):
    raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)})


def _validated_pricing_input(payload: dict) -> dict:
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
    stage = "BOOKED" if product.execution else ("RFQ" if product.rfqs else "SAVED")
    return {
        "id": row.id,
        "reference": row.reference,
        "name": row.name,
        "revision": row.revision,
        "terms_version": row.terms_version,
        "archived": row.archived,
        "data_origin": row.data_origin,
        "stage": stage,
        "underlyings": [u.model_dump(mode="json") for u in product.terms.underlyings],
        "maturity_date": (product.terms.maturity_date.isoformat()
                          if product.terms.maturity_date else None),
        "latest_price": (product.calculations[-1].price if product.calculations else None),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("", status_code=201)
def create_product(
    body: ProductCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            return prior.to_dict()

        validated = _validated_pricing_input(body.pricing_input)
        product = Product(
            name=(body.name.strip() or _default_name(validated)),
            terms=terms_from_input(validated, allow_unresolved=True),
            intent=body.intent,
            commercial=body.commercial,
        )
        product = stage_new_product(session, product, user=current)

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


@router.get("")
def list_products(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    archived: bool = Query(default=False),
):
    query = select(ProductRecord).where(ProductRecord.archived == archived)
    if current.role != "admin":
        query = query.where(ProductRecord.user_id == current.id)
    rows = session.exec(query.order_by(ProductRecord.updated_at.desc())).all()
    return [_row_summary(row, load_product(session, row.id)) for row in rows]


@router.get("/{product_id}")
def get_product(
    product_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    revision: int | None = None,
):
    try:
        owned_record(session, product_id, current)
        product = load_product(session, product_id, revision=revision)
        return {**product.to_dict(), "description": describe_product(product)}
    except ProductError as exc:
        _fail(exc)


@router.patch("/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
        product = load_product(session, product_id)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")
        changes = {}
        if body.name is not None:
            changes["name"] = body.name.strip() or product.name
        if body.intent is not None:
            changes["intent"] = body.intent
        if body.commercial is not None:
            changes["commercial"] = body.commercial
        product = stage_revision(
            session, product.model_copy(update=changes),
            expected_revision=body.expected_revision, actor_id=current.id,
            action="PRODUCT_CONTEXT_UPDATED", reason=body.reason)
        session.commit()
        return product.to_dict()
    except ProductError as exc:
        session.rollback()
        _fail(exc)


@router.post("/{product_id}/terms")
def revise_product_terms(
    product_id: int,
    body: ProductTermsUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            if prior.product_id != product_id:
                raise ProductError("PRODUCT_COMMAND_CONFLICT", "La commande désigne un autre produit.")
            return prior.to_dict()
        owned_record(session, product_id, current)
        product = load_product(session, product_id)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")
        validated = _validated_pricing_input(body.pricing_input)
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


@router.post("/{product_id}/archive")
def archive_product(
    product_id: int,
    body: ProductArchive,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
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
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
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
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Append one server-produced calculation without changing product terms."""
    command_payload = body.model_dump(mode="json", exclude={"command_key"})
    try:
        prior = previous_command(session, current, body.command_key, command_payload)
        if prior is not None:
            if prior.product_id != product_id:
                raise ProductError(
                    "PRODUCT_COMMAND_CONFLICT",
                    "La commande désigne un autre produit.")
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


@router.get("/{product_id}/calculations/{calculation_id}")
def get_product_calculation(
    product_id: int,
    calculation_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        owned_record(session, product_id, current)
    except ProductError as exc:
        _fail(exc)
    row = session.get(ProductCalculationRun, calculation_id)
    if row is None or row.product_id != product_id:
        raise HTTPException(status_code=404, detail="Calcul produit introuvable.")
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
        "input": json.loads(row.input_json),
        "result": json.loads(row.result_json),
    }
