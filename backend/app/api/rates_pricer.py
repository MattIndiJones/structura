"""Deterministic FRN/IRS pricing and explicit Product calculation retention."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from sqlmodel import Session

from .auth import get_current_pricer, receipt_signing_secret
from ..core.product.models import (
    FRNTerms, IRSTerms, Product, RatesScriptTerms, TradeIntent, product_terms_schema,
)
from ..core.product.native_market import NativeValuationContext, prepare_native_context
from ..core.product.native_schedule import native_draft_diagnostics, resolve_native_schedule
from ..core.product.rates_pilot import RatesCase, pilot_cases, pilot_market, pilot_payment, pilot_terms
from ..core.product.rates_pricing import RatesPriceResult, price_rates
from ..core.valuation_context import json_transport_fingerprint
from ..db.database import get_session
from ..db.models import User
from ..services.native_calculation_archive import (
    RATES_CALCULATION_KIND, read_native_calculation, stage_native_calculation,
)
from ..services.native_template_booking import native_booking_capability
from ..services.native_context_repository import load_native_context
from ..services.native_write_policy import native_writes_enabled
from ..services.native_valuation_explain import native_explain_engine_fingerprint
from ..services.product_receipts import signed_rates_receipt, verify_rates_receipt
from ..services.product_repository import (
    ProductError, load_product, owned_record, previous_command, stage_command,
)


router = APIRouter(prefix="/api/products", tags=["rates-pricer"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
ProductSession = Annotated[Session, Depends(get_session)]
_SCRIPT_PROFILE = "rates-deterministic-v1"


def _check_terms_schema(terms):
    if not isinstance(terms, (FRNTerms, IRSTerms)) and product_terms_schema(terms) != 2:
        raise ValueError("Le Pricer de taux exige des termes de schéma 2.")
    return terms


RatesTerms = Annotated[
    FRNTerms | IRSTerms, Field(discriminator="instrument_type"), BeforeValidator(_check_terms_schema),
]


class RatesPriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: RatesCase | None = None
    context_id: int | None = Field(default=None, ge=1)
    terms: RatesTerms | None = None
    intent: TradeIntent | None = None
    product_id: int | None = Field(default=None, ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    expected_terms_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_target(self):
        if (self.case is None) == (self.context_id is None):
            raise ValueError("Choisissez un arrêté de recette ou un contexte archivé.")
        if self.product_id is None:
            if self.terms is None or self.intent is None or self.context_id is not None or any(
                value is not None for value in (self.expected_revision, self.expected_terms_version)
            ):
                raise ValueError("Un brouillon requiert les termes, le nominal et un arrêté de recette.")
        elif self.terms is not None or self.intent is not None or any(
            value is None for value in (self.expected_revision, self.expected_terms_version)
        ):
            raise ValueError("Un Product conservé requiert sa révision et sa version de termes attendues.")
        return self


class RatesScriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: RatesTerms


class RatesPriceResponse(BaseModel):
    result: RatesPriceResult
    context: NativeValuationContext
    script: dict | None = None
    warnings: tuple[str, ...] = ()
    receipt: dict


class RatesCalculationResponse(RatesPriceResponse):
    calculation_id: int


class RatesRetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_key: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=1)
    receipt: dict


class RatesRetentionResponse(BaseModel):
    calculation_id: int
    product: Product


def _fail(exc: ValueError, *, code: str = "RATES_INPUT_INVALID", status: int = 422):
    raise HTTPException(status_code=getattr(exc, "status", status),
                        detail={"code": getattr(exc, "code", code), "message": str(exc)}) from exc


def _require_rates_product(product: Product):
    if not isinstance(product.terms, (FRNTerms, IRSTerms)):
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "La valorisation de taux concerne le FRN et l’IRS.")


def _resolve_product(body: RatesPriceRequest, session: Session, user: User) -> Product:
    if body.product_id is not None:
        owned_record(session, body.product_id, user)
        product = load_product(session, body.product_id, allow_native=True)
        if (product.revision, product.terms_version) != (body.expected_revision, body.expected_terms_version):
            raise ProductError("PRODUCT_REVISION_STALE", "Le dossier a changé. Rechargez le produit.")
        _require_rates_product(product)
    else:
        product = Product(terms=body.terms, intent=body.intent)
    diagnostics = native_draft_diagnostics(product)
    if diagnostics:
        raise ProductError("PRODUCT_DRAFT_INCOMPLETE", " ".join(diagnostics), 422)
    if product.product_id is None:
        product = product.model_copy(update={"native_schedule": resolve_native_schedule(product.terms).schedule})
    return product


def _payoff(product: Product):
    if product.terms.payoff_mode == "native":
        return None, False, None
    from ..core.product.rates_payscript import rates_payoff

    payoff, equivalent, metadata = rates_payoff(product)
    return payoff, equivalent, metadata.model_dump(mode="json")


def _synthetic_context(product: Product, case: RatesCase, equivalent: bool) -> NativeValuationContext:
    market, cutoff = pilot_market(case)
    if case == "C" and (payment := pilot_payment(product, equivalent_payoff=equivalent)) is not None:
        market = market.model_copy(update={"payments": (payment,)})
    return prepare_native_context(product, valuation_date=market.market_date, cutoff=cutoff, market=market, allow_draft=True)


@router.get("/rates/pilots")
def list_rates_pilots(current: PricerUser, session: ProductSession):
    from ..core.product.rates_payscript import FRN_RATES_PAYSCRIPT, IRS_RATES_PAYSCRIPT

    entries = zip(pilot_terms(), ("FRN Euribor 3M", "IRS fixe contre Euribor 3M"),
                  (FRN_RATES_PAYSCRIPT, IRS_RATES_PAYSCRIPT))
    return {"market_quality": "synthetic", "can_retain": native_writes_enabled(current, session), "cases": pilot_cases(),
            "booking": native_booking_capability(session, current),
            "products": [{"instrument_type": terms.instrument_type, "name": name, "terms": terms,
                          "intent": {"nominal": 1_000_000, "side": "BUY"},
                          "script": RatesScriptTerms(profile=_SCRIPT_PROFILE, source=source)}
                         for terms, name, source in entries]}


@router.post("/rates/validate-script")
def validate_rates_script(body: RatesScriptRequest, current: PricerUser):
    try:
        if body.terms.rates_script is None:
            raise ProductError("RATES_SCRIPT_REQUIRED", "Ajoutez un PayScript de taux à valider.", 422)
        _, _, metadata = _payoff(Product(terms=body.terms))
        return {"valid": True, **metadata}
    except ValueError as exc:
        _fail(exc)


@router.post("/rates/price")
def calculate_rates(body: RatesPriceRequest, current: PricerUser, session: ProductSession) -> RatesPriceResponse:
    try:
        product = _resolve_product(body, session, current)
        payoff, equivalent, script = _payoff(product)
        context = (load_native_context(session, product.product_id, body.context_id, user=current)
                   if body.context_id is not None else _synthetic_context(product, body.case, equivalent))
        if (context.nominal, context.side) != (product.intent.nominal, product.intent.side):
            raise ProductError("RATES_CONTEXT_STALE", "Le contexte porte un autre nominal ou sens. Préparez un nouvel arrêté.")
        result = price_rates(product, context, payoff=payoff, equivalent_payoff=equivalent)
        warnings = ()
        if body.case == "C" and any(flow.state == "due_open" for flow in result.flows):
            warnings = ("Le règlement du témoin C ne couvre pas ce flux. Il reste dû jusqu’à confirmation.",)
        receipt = signed_rates_receipt({
            "user_id": current.id, "product_reference": product.reference,
            "input_revision": product.revision, "context_id": body.context_id, "case": body.case,
            "terms": product.terms.model_dump(mode="json"), "schedule": product.native_schedule.model_dump(mode="json"),
            "context": context.model_dump(mode="json"), "script": script, "warnings": warnings,
            "calculation_identity": {"engine_version": result.engine_version,
                                     "engine_fingerprint": native_explain_engine_fingerprint("rates")},
            "result": result.model_dump(mode="json"),
        }, secret=receipt_signing_secret())
        return RatesPriceResponse(result=result, context=context, script=script, warnings=warnings, receipt=receipt)
    except ValueError as exc:
        _fail(exc)


def _require_retention(session: Session, user: User) -> None:
    if not native_writes_enabled(user, session):
        raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation des calculs de taux est fermée dans cette installation.", 403)


def _check_pricing_receipt(verified: dict, product: Product, user: User) -> NativeValuationContext:
    context = NativeValuationContext.model_validate(verified["context"])
    references = (context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
                  context.nominal, context.side, verified["product_reference"], verified["input_revision"], verified["user_id"])
    schedule = product.native_schedule
    if schedule is None or references != (product.product_id, product.terms_version, product.terms_fingerprint,
                                           schedule.fingerprint, product.intent.nominal, product.intent.side,
                                           product.reference, product.revision, user.id):
        raise ProductError("RATES_RECEIPT_MISMATCH", "Le reçu ne correspond plus aux termes, au sens ou à la révision du dossier.")
    return context


@router.post("/{product_id}/rates/calculations", status_code=201)
def retain_rates_calculation(product_id: int, body: RatesRetentionRequest, current: PricerUser,
                             session: ProductSession) -> RatesRetentionResponse:
    try:
        _require_retention(session, current)
        owned_record(session, product_id, current, right="prepare")
        receipt_hash = json_transport_fingerprint(body.receipt)
        payload = {"operation": "retain_rates_calculation", "product_id": product_id,
                   "expected_revision": body.expected_revision, "receipt_fingerprint": receipt_hash}
        previous = previous_command(session, current, body.command_key, payload, allow_native=True)
        _require_retention(session, current)
        if previous is not None:
            session.rollback()
            return RatesRetentionResponse(calculation_id=previous.calculations[-1].id, product=previous)

        verified = verify_rates_receipt(body.receipt, secret=receipt_signing_secret())
        product = load_product(session, product_id, allow_native=True)
        _require_rates_product(product)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le dossier a changé. Rechargez le produit.")
        context = _check_pricing_receipt(verified, product, current)
        context_id = verified["context_id"]
        if context_id is not None and load_native_context(session, product_id, context_id, user=current) != context:
            raise ProductError("RATES_RECEIPT_MISMATCH", "Le contexte archivé ne correspond pas au reçu.")

        saved, calculation_id = stage_native_calculation(session, product, current, body.receipt, kind=RATES_CALCULATION_KIND,
                                                         reason="Conservation du calcul de taux.")
        stage_command(session, current, body.command_key, payload, saved)
        session.commit()
        return RatesRetentionResponse(calculation_id=calculation_id, product=saved)
    except ValueError as exc:
        session.rollback()
        _fail(exc, code="RATES_RECEIPT_INVALID")
    except Exception:
        session.rollback()
        raise


@router.get("/{product_id}/rates/calculations/{calculation_id}")
def reopen_rates_calculation(product_id: int, calculation_id: int, current: PricerUser,
                             session: ProductSession) -> RatesCalculationResponse:
    try:
        receipt = read_native_calculation(session, product_id, calculation_id, current, kind=RATES_CALCULATION_KIND)
        return RatesCalculationResponse(calculation_id=calculation_id, result=receipt["result"],
                                        context=receipt["context"], script=receipt["script"],
                                        warnings=receipt["warnings"], receipt=receipt)
    except ValueError as exc:
        _fail(exc, code="RATES_ARCHIVE_INVALID")
