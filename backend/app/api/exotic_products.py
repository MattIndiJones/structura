"""Explicit retention, reopening and booking for native exotic Products."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .auth import get_current_pricer, get_current_user, receipt_signing_secret
from .exotic_pricer import _verify
from ..core.access import can_book
from ..core.product.exotic_credit_mc import CreditMcResult
from ..core.product.exotic_rates_mc import RatesMCResult
from ..core.product.exotic_valuation_explain import ValuationExplain
from ..core.product.models import Product
from ..db.database import get_session
from ..db.models import User
from ..services.exotic_deal_valuation import (
    ExoticDealExplainRequest, ExoticDealMtm, ExoticDealMtmRequest, ExoticDealReplay,
    exotic_mtm_history, explain_exotic_mtm, replay_exotic_mtm, stage_exotic_mtm,
)
from ..services.exotic_product import ExoticProductCalculation, booking_diagnostics, read_exotic_calculation, retain_exotic_price
from ..services.exotic_product_booking import ExoticBookingRequest, exotic_transaction_format, stage_exotic_booking
from ..services.exotic_product_lifecycle import FactDecision, FactLedger, FactProposal, FactRow, decide_exotic_fact, propose_exotic_fact, read_exotic_ledger
from ..services.native_write_policy import native_writes_enabled
from ..services.product_repository import ProductError


router = APIRouter(prefix="/api/products", tags=["exotic-products"])
lifecycle_router = APIRouter(prefix="/api/deals", tags=["exotic-lifecycle"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_session)]


class RetainExoticPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=200)
    command_key: str = Field(min_length=8, max_length=100)
    receipt: dict


class ExoticProductResponse(BaseModel):
    product: Product
    calculation_id: int
    receipt: dict
    result: RatesMCResult | CreditMcResult
    booking_eligible: bool
    booking_diagnostics: tuple[str, ...] = ()
    transaction_format: str


class ExoticBookedResponse(BaseModel):
    product: Product
    deal_id: int
    deal_reference: str


def _response(calculation: ExoticProductCalculation, current: User, session: Session) -> ExoticProductResponse:
    issues = booking_diagnostics(calculation)
    if not native_writes_enabled(current, session):
        issues += ("Le booking exotique est fermé sur cette installation.",)
    elif not can_book(current):
        issues += ("Votre profil peut conserver le calcul. Le booking exige un compte habilité.",)
    return ExoticProductResponse(product=calculation.product, calculation_id=calculation.calculation_id,
                                 receipt=calculation.receipt, result=calculation.result,
                                 booking_eligible=not issues, booking_diagnostics=issues,
                                 transaction_format=exotic_transaction_format(calculation.product.terms))


def _fail(exc: ValueError):
    raise HTTPException(status_code=getattr(exc, "status", 422),
                        detail={"code": getattr(exc, "code", "EXOTIC_PRODUCT_INVALID"), "message": str(exc)}) from exc


@router.post("/exotics/conserve", status_code=201)
def conserve_exotic(body: RetainExoticPrice, current: PricerUser, session: Database) -> ExoticProductResponse:
    try:
        if not native_writes_enabled(current, session):
            raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation des exotiques est fermée.", 403)
        _verify(body.receipt, current, session)
        calculation = retain_exotic_price(session, current, name=body.name.strip() or "Produit exotique",
                                         receipt=body.receipt, command_key=body.command_key, secret=receipt_signing_secret())
        response = _response(calculation, current, session)
        session.commit()
        return response
    except ValueError as exc:
        session.rollback()
        _fail(exc)


@router.get("/{product_id}/exotics/calculations/{calculation_id}")
def reopen_exotic(product_id: int, calculation_id: int, current: PricerUser, session: Database) -> ExoticProductResponse:
    try:
        calculation = read_exotic_calculation(session, product_id, calculation_id, current, secret=receipt_signing_secret())
        return _response(calculation, current, session)
    except ValueError as exc:
        _fail(exc)


@router.post("/{product_id}/exotics/book", status_code=201)
def book_exotic(product_id: int, body: ExoticBookingRequest, current: PricerUser, session: Database) -> ExoticBookedResponse:
    try:
        product, deal = stage_exotic_booking(session, current, product_id, body, secret=receipt_signing_secret())
        response = ExoticBookedResponse(product=product, deal_id=deal.id, deal_reference=deal.reference)
        session.commit()
        return response
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail={"code": "EXOTIC_BOOKING_CONFLICT",
                            "message": "Conflit pendant le booking. Rechargez le dossier."}) from exc
    except ValueError as exc:
        session.rollback()
        _fail(exc)
    except HTTPException:
        session.rollback()
        raise


@lifecycle_router.get("/{deal_id}/exotics/facts")
def exotic_facts(deal_id: int, current: CurrentUser, session: Database, cutoff: AwareDatetime | None = None) -> FactLedger:
    try:
        return read_exotic_ledger(session, deal_id, current, cutoff=cutoff)
    except ValueError as exc:
        _fail(exc)


@lifecycle_router.post("/{deal_id}/exotics/facts", status_code=201)
def add_exotic_fact(deal_id: int, body: FactProposal, current: CurrentUser, session: Database) -> FactRow:
    try:
        result = propose_exotic_fact(session, deal_id, current, body)
        session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        _fail(exc)


@lifecycle_router.post("/{deal_id}/exotics/facts/{fact_id}/decision")
def decide_fact(deal_id: int, fact_id: int, body: FactDecision, current: CurrentUser, session: Database) -> FactRow:
    try:
        result = decide_exotic_fact(session, deal_id, fact_id, current, body)
        session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        _fail(exc)


@lifecycle_router.post("/{deal_id}/exotics/valuations", status_code=201)
def value_exotic_deal(deal_id: int, body: ExoticDealMtmRequest, current: PricerUser, session: Database) -> ExoticDealMtm:
    try:
        result = stage_exotic_mtm(session, deal_id, current, body, secret=receipt_signing_secret())
        session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        _fail(exc)


@lifecycle_router.get("/{deal_id}/exotics/valuations")
def list_exotic_mtm(deal_id: int, current: CurrentUser, session: Database) -> tuple[ExoticDealMtm, ...]:
    try:
        return exotic_mtm_history(session, deal_id, current)
    except ValueError as exc:
        _fail(exc)


@lifecycle_router.post("/{deal_id}/exotics/valuations/{run_id}/replay")
def replay_exotic_deal(deal_id: int, run_id: int, current: CurrentUser, session: Database) -> ExoticDealReplay:
    try:
        return replay_exotic_mtm(session, deal_id, run_id, current)
    except ValueError as exc:
        _fail(exc)


@lifecycle_router.post("/{deal_id}/exotics/explain")
def explain_exotic_deal(deal_id: int, body: ExoticDealExplainRequest, current: CurrentUser, session: Database) -> ValuationExplain:
    try:
        return explain_exotic_mtm(session, deal_id, current, body)
    except ValueError as exc:
        _fail(exc)
