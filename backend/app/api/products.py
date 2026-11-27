"""Persisted Product dossiers shared by pricing and downstream modules."""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator
from sqlalchemy import func, or_, update
from sqlmodel import Session, select

from .auth import get_current_pricer, receipt_signing_secret
from ..core.product import native_schedule
from ..core.product.asset_class import ProductAsset, product_terms_asset_class
from ..core.product.inputs import describe_product, pricing_input, terms_from_input
from ..core.product.models import (
    CLNTerms, CommercialContext, ExoticTerms, NativeProductTerms, NativeTerms, Product, ProductTerms,
    TradeIntent, product_terms_schema,
)
from ..core.product.native_market import NativeMarket, NativeValuationContext, prepare_native_context
from ..core.product.native_schedule_models import SchedulePreparation
from ..core.schemas import PricingRequest
from ..core.valuation_context import (
    json_transport_fingerprint, market_snapshot_from_pricing_input,
    pricing_input_payload, verify_pricing_receipt,
)
from ..db.database import get_session
from ..db.models import ProductCalculationRun, ProductRecord, ProductRevision, ProductTermsVersion, User
from ..services.native_context_repository import (
    list_native_contexts, load_native_context, prior_native_context, store_native_context,
)
from ..services.native_calculation_archive import CREDIT_CALCULATION_KIND, RATES_CALCULATION_KIND
from ..services.exotic_product import EXOTIC_CALCULATION_KIND
from ..services.native_write_policy import native_writes_enabled
from ..services.product_receipts import verify_server_receipt
from ..services.product_repository import (
    ProductError, load_product, owned_record, previous_command,
    stage_calculation, stage_command, stage_new_product, stage_revision, stage_terms,
)


router = APIRouter(prefix="/api/products", tags=["products"])
ProductView = Annotated[Literal["payscript", "mixed"], Query(
    description="Vue PayScript historique ou lecture de tous les dossiers de pricing.",
)]

_NATIVE_POSITIONS = {
    "FRN": {"BUY": "long", "SELL": "short"},
    "IRS": {"BUY": "receive_fixed", "SELL": "pay_fixed"},
    "CDS": {"BUY": "buy_protection", "SELL": "sell_protection"},
    "CLN": {"BUY": "long", "SELL": "short"},
    "EXOTIC_RATES": {"BUY": "long", "SELL": "short"},
    "EXOTIC_CREDIT": {"BUY": "long", "SELL": "short"},
}


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


class NativeSchedulePreview(BaseModel):
    terms: dict


class NativeTermsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_key: str = Field(min_length=8, max_length=100)
    terms: NativeTerms

    @field_validator("terms", mode="before")
    @classmethod
    def check_terms_schema(cls, value):
        if not isinstance(value, NativeProductTerms) and product_terms_schema(value) != 2:
            raise ValueError("Les écritures natives exigent des termes de schéma 2.")
        return value


class NativeProductCreate(NativeTermsCommand):
    name: str = Field(default="", max_length=200)
    intent: TradeIntent = Field(default_factory=TradeIntent)


class NativeProductRevision(NativeTermsCommand):
    expected_revision: int = Field(ge=1)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    intent: TradeIntent | None = None


class NativeContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_key: str = Field(min_length=8, max_length=100)
    terms_version: int = Field(ge=1)
    valuation_date: date
    value_date: date | None = None
    cutoff: AwareDatetime
    market: NativeMarket


class NativeContextResult(BaseModel):
    context_id: int
    context: NativeValuationContext


class NativeContextReference(BaseModel):
    context_id: int
    terms_version: int
    valuation_date: date
    fingerprint: str
    readiness: Literal["ready_for_pricing", "ready_for_curve_construction_and_conversion"]


class NativeContextPage(BaseModel):
    items: list[NativeContextReference]
    limit: int
    offset: int
    has_more: bool


def _fail(exc: ProductError):
    raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)})


def _validated_pricing_input(payload: dict, *, draft: bool = False) -> dict:
    try:
        schema = product_terms_schema(payload)
    except ValueError as exc:
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Cette opération est réservée aux produits PayScript.") from exc
    if schema != 1:
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Cette opération est réservée aux produits PayScript.")
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


def _native_read_projection(product: Product, *, write_allowed: bool = False) -> dict:
    terms = product.terms
    exotic = isinstance(terms, ExoticTerms)
    ready = product.native_schedule is not None and not native_schedule.native_draft_diagnostics(product)
    applicable = next((ref for ref in reversed(product.calculations)
                       if (ref.terms_version, ref.nominal, ref.side) == (
                           product.terms_version, product.intent.nominal, product.intent.side,
                       )), None)
    historical = product.calculations[-1] if product.calculations else None
    return {
        "instrument_type": terms.instrument_type,
        "payoff_mode": terms.payoff_mode,
        "currency": terms.currency,
        "position": {"side": _NATIVE_POSITIONS[terms.instrument_type][product.intent.side],
                     "nominal": product.intent.nominal},
        "capabilities": {"prepare": write_allowed and ready and not isinstance(terms, (CLNTerms, ExoticTerms)),
                         "price": ready and not exotic, "write": write_allowed and not exotic},
        "price": applicable.price if applicable else None,
        "latest_price": applicable.price if applicable else None,
        "latest_price_measure": applicable.measure if applicable else None,
        "latest_price_unit": applicable.price_unit if applicable else None,
        "latest_price_terms_version": applicable.terms_version if applicable else None,
        "historical_price": historical.price if historical and not applicable else None,
        "historical_price_terms_version": historical.terms_version if historical and not applicable else None,
    }


def _native_dossier(product: Product, *, write_allowed: bool, data: dict | None = None) -> dict:
    if data is None:
        data = product.to_dict()
    data.pop("native_schedule", None)
    prepared = native_schedule.read_native_schedule(product)
    return {**data, **_native_read_projection(product, write_allowed=write_allowed),
            "terms_fingerprint": product.terms_fingerprint,
            "description": prepared.model_dump(mode="json")}


def _can_revise_native(session: Session, user: User, product: Product) -> bool:
    if product.archived or product.execution is not None:
        return False
    try:
        owned_record(session, product.product_id, user, right="prepare")
    except ProductError:
        return False
    return True


def _require_native_writes(session: Session, user: User) -> None:
    if not native_writes_enabled(user, session):
        raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "Les écritures de produits natifs sont fermées pour ce compte ou cette installation.", 403)


def _row_summary(row: ProductRecord, product: Product, *, write_allowed: bool = False) -> dict:
    stage = (
        "BOOKED" if product.execution else
        "RFQ" if product.rfqs else
        "INDICATIVE" if product.indicatives else
        "SAVED"
    )
    summary = {
        "id": row.id,
        "reference": row.reference,
        "name": row.name,
        "revision": row.revision,
        "terms_version": row.terms_version,
        "archived": row.archived,
        "listed": row.listed,
        "data_origin": row.data_origin,
        "stage": stage,
        "maturity_date": (product.terms.maturity_date.isoformat()
                          if product.terms.maturity_date else None),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
    if isinstance(product.terms, ProductTerms):
        return {**summary, "underlyings": [u.model_dump(mode="json") for u in product.terms.underlyings]}
    return {**summary, **_native_read_projection(product, write_allowed=write_allowed)}


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


@router.post("/native", status_code=201)
def create_native_product(
    body: NativeProductCreate,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    name = body.name.strip() or f"Produit {body.terms.instrument_type}"
    payload = {**body.model_dump(mode="json", exclude={"command_key"}), "name": name, "operation": "native_create"}
    try:
        _require_native_writes(session, current)
        if isinstance(body.terms, ExoticTerms):
            raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Conservez un reçu depuis le Pricer exotique.", 422)
        prior = previous_command(session, current, body.command_key, payload, allow_native=True)
        _require_native_writes(session, current)
        if prior is not None:
            session.rollback()
            return _native_dossier(prior, write_allowed=True)

        draft = Product(name=name, terms=body.terms, intent=body.intent)
        product = stage_new_product(session, draft, user=current)
        stage_command(session, current, body.command_key, payload, product)
        result = _native_dossier(product, write_allowed=True)
        session.commit()
        return result
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except Exception:
        session.rollback()
        raise


@router.post("/{product_id}/native/terms")
def revise_native_product_terms(
    product_id: int,
    body: NativeProductRevision,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
):
    payload = {**body.model_dump(mode="json", exclude={"command_key"}),
               "operation": "native_revise_terms", "product_id": product_id}
    try:
        _require_native_writes(session, current)
        if isinstance(body.terms, ExoticTerms):
            raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Les termes exotiques sont figés par leur reçu.", 422)
        prior = previous_command(session, current, body.command_key, payload, allow_native=True)
        _require_native_writes(session, current)
        if prior is not None:
            session.rollback()
            return _native_dossier(prior, write_allowed=True)

        owned_record(session, product_id, current, right="prepare")
        product = load_product(session, product_id, allow_native=True)
        if isinstance(product.terms, ProductTerms) or product.terms.instrument_type != body.terms.instrument_type:
            raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Le type contractuel du dossier doit être conservé.")
        if product.archived:
            raise ProductError("PRODUCT_ARCHIVED", "Le dossier est archivé.")
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")

        changed = stage_terms(session, product, body.terms, actor_id=current.id, reason=body.reason)
        if body.intent is not None and changed.intent != body.intent:
            changed = changed.model_copy(update={"intent": body.intent})
        if changed is not product:
            action = "PRODUCT_TERMS_REVISED" if changed.terms_version != product.terms_version else "PRODUCT_CONTEXT_UPDATED"
            product = stage_revision(session, changed, expected_revision=body.expected_revision,
                                     actor_id=current.id, action=action, reason=body.reason)
        stage_command(session, current, body.command_key, payload, product)
        result = _native_dossier(product, write_allowed=True)
        session.commit()
        return result
    except ProductError as exc:
        session.rollback()
        _fail(exc)
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
    view: ProductView = "payscript",
    asset: Annotated[ProductAsset | None, Query(description="Classe du pricer du dossier.")] = None,
):
    query = select(ProductRecord, ProductTermsVersion.terms_json).join(
        ProductTermsVersion, (ProductTermsVersion.product_id == ProductRecord.id)
        & (ProductTermsVersion.version == ProductRecord.terms_version),
    ).where(
        ProductRecord.archived == archived,
        ProductRecord.listed == True,  # noqa: E712
    )
    if current.role != 'admin':
        query = query.where(or_(ProductRecord.entity_id == current.entity_id if current.entity_id is not None else False,
            (ProductRecord.entity_id.is_(None)) & (ProductRecord.user_id == current.id)))
    rows = session.exec(query.order_by(ProductRecord.updated_at.desc(), ProductRecord.id.desc())).yield_per(100)
    native_write_access = view == "mixed" and native_writes_enabled(current, session)
    visible = []
    skipped = 0
    for row, terms_json in rows:
        try:
            owned_record(session, row.id, current)
        except ProductError:
            continue
        try:
            schema = product_terms_schema(json.loads(terms_json))
        except ValueError:
            # Invalid stored markers are diagnosed on authorized detail reads.
            continue
        if schema == 2 and view != "mixed":
            continue
        product = None
        if schema == 2:
            try:
                product = load_product(session, row.id, revision=row.revision, terms_version=row.terms_version,
                                       allow_native=True)
            except ProductError:
                # Keep corrupt native terms out of both the page and its continuation count.
                continue
        if asset is not None:
            asset_class = "equity" if product is None else product_terms_asset_class(product.terms)
            if asset_class != asset:
                continue
        if skipped < offset:
            skipped += 1
            continue
        if len(visible) == limit:
            return {'items': visible, 'offset': offset, 'limit': limit, 'has_more': True} if paged else visible
        if product is None:
            try:
                product = load_product(session, row.id, calculation_page=(0, 0))
            except ProductError as exc:
                _fail(exc)
        can_write = schema == 2 and native_write_access and _can_revise_native(session, current, product)
        summary = _row_summary(row, product, write_allowed=can_write)
        if not isinstance(product.terms, ProductTerms):
            visible.append(summary)
            continue
        if view == "mixed":
            summary.update(instrument_type="PAYSCRIPT", payoff_mode="scripted")
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


@router.post("/schedule/preview")
def preview_native_schedule(
    body: NativeSchedulePreview,
    current: Annotated[User, Depends(get_current_pricer)],
) -> SchedulePreparation:
    try:
        if product_terms_schema(body.terms) != 2:
            raise ValueError("L’aperçu natif exige des termes de schéma 2.")
        terms = Product.model_validate({"terms": body.terms}).terms
    except ValidationError as exc:
        errors = exc.errors(include_input=False)
        if all(error["type"] == "missing" for error in errors):
            missing = (".".join(map(str, error["loc"][1:])) for error in errors)
            return SchedulePreparation(status="incomplete", diagnostics=tuple(f"À préciser : {path}." for path in missing))
        _fail(ProductError("PRODUCT_TERMS_INVALID", "Les termes de l’échéancier natif sont invalides.", 422))
    except ValueError as exc:
        _fail(ProductError("PRODUCT_TERMS_INVALID", str(exc), 422))
    try:
        return native_schedule.resolve_native_schedule(terms)
    except ValueError as exc:
        _fail(ProductError("PRODUCT_SCHEDULE_INVALID", str(exc), 422))


@router.post("/{product_id}/valuation-contexts", status_code=201)
def retain_native_valuation_context(
    product_id: int,
    body: NativeContextRequest,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
) -> NativeContextResult:
    try:
        _require_native_writes(session, current)
        record = owned_record(session, product_id, current, right="prepare")
        prior = prior_native_context(session, record, user=current, command_key=body.command_key,
                                     terms_version=body.terms_version)
        product = load_product(session, product_id, terms_version=body.terms_version, allow_native=True)
        if prior is not None:
            intent = product.intent.model_copy(update={"nominal": prior.nominal, "side": prior.side})
            product = product.model_copy(update={"intent": intent})
        diagnostics = native_schedule.native_draft_diagnostics(product)
        if diagnostics:
            raise ProductError("PRODUCT_DRAFT_INCOMPLETE", " ".join(diagnostics), 422)
        if body.market.kind == "rates":
            for curve in (body.market.discount, body.market.projection):
                if curve.override is not None and curve.override.author != current.username:
                    raise ProductError("MARKET_OVERRIDE_AUTHOR_MISMATCH", "L’auteur de la surcharge doit être le demandeur.", 403)
        context = prepare_native_context(product, valuation_date=body.valuation_date, value_date=body.value_date,
                                         cutoff=body.cutoff, market=body.market)
        _require_native_writes(session, current)
        context_id = store_native_context(session, user=current, command_key=body.command_key,
                                          context=context, received_market=body.market)
        session.commit()
        return NativeContextResult(context_id=context_id, context=context)
    except ProductError as exc:
        session.rollback()
        _fail(exc)
    except ValueError as exc:
        session.rollback()
        _fail(ProductError(getattr(exc, "code", "MARKET_INPUT_INVALID"), str(exc), 422))
    except Exception:
        session.rollback()
        raise


@router.get("/{product_id}/valuation-contexts")
def list_native_valuation_contexts(
    product_id: int,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
    terms_version: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NativeContextPage:
    try:
        record = owned_record(session, product_id, current)
        product = load_product(session, product_id, terms_version=terms_version, allow_native=True)
        if isinstance(product.terms, ProductTerms):
            raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Cette lecture est réservée aux produits natifs.")
        rows = list_native_contexts(session, record, terms_version=product.terms_version, limit=limit + 1, offset=offset)
        items = [NativeContextReference(context_id=context_id, terms_version=context.terms_version,
                                        valuation_date=context.valuation_date, fingerprint=context.fingerprint,
                                        readiness=context.readiness) for context_id, context in rows[:limit]]
        return NativeContextPage(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)
    except ProductError as exc:
        _fail(exc)


@router.get("/{product_id}/valuation-contexts/{context_id}")
def reopen_native_valuation_context(
    product_id: int,
    context_id: int,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
) -> NativeContextResult:
    try:
        context = load_native_context(session, product_id, context_id, user=current)
        return NativeContextResult(context_id=context_id, context=context)
    except ProductError as exc:
        _fail(exc)


@router.get("/{product_id}")
def get_product(
    product_id: int,
    current: Annotated[User, Depends(get_current_pricer)],
    session: Annotated[Session, Depends(get_session)],
    revision: int | None = None,
    terms_version: int | None = None,
    calculations_limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    calculations_offset: Annotated[int, Query(ge=0)] = 0,
    view: ProductView = "payscript",
):
    try:
        owned_record(session, product_id, current)
        product = load_product(session, product_id, revision=revision, terms_version=terms_version,
            calculation_page=None if calculations_limit is None else (calculations_offset, calculations_limit + 1),
            allow_native=view == "mixed")
        data = product.to_dict()
        if calculations_limit is not None:
            calculations = data['calculations']
            if not isinstance(product.terms, ProductTerms):
                end = max(0, len(calculations) - calculations_offset)
                calculations = calculations[max(0, end - calculations_limit - 1):end]
            data['calculations'] = calculations[-calculations_limit:]
            data['calculation_page'] = {'offset': calculations_offset, 'limit': calculations_limit,
                'has_more': len(calculations) > calculations_limit}
        if not isinstance(product.terms, ProductTerms):
            can_write = native_writes_enabled(current, session) and _can_revise_native(session, current, product)
            return _native_dossier(product, write_allowed=can_write, data=data)
        if view == "mixed":
            data.update(instrument_type="PAYSCRIPT", payoff_mode="scripted")
        return {**data, "description": describe_product(product)}
    except ProductError as exc:
        _fail(exc)


@router.get('/{product_id}/history')
def product_history(product_id: int, current: Annotated[User, Depends(get_current_pricer)],
                    session: Annotated[Session, Depends(get_session)],
                    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0,
                    view: ProductView = "payscript"):
    try:
        owned_record(session, product_id, current)
        load_product(session, product_id, calculation_page=(0, 0), allow_native=view == "mixed")
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
    if row.kind in (RATES_CALCULATION_KIND, CREDIT_CALCULATION_KIND, EXOTIC_CALCULATION_KIND):
        _fail(ProductError("PRODUCT_TERMS_UNSUPPORTED", "Cette opération est réservée aux produits PayScript."))
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
