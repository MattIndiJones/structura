"""Preparation and execution of a deterministic Product from its retained price."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .auth import get_current_pricer, receipt_signing_secret
from .exotic_products import ExoticBookedResponse
from ..db.database import get_session
from ..db.models import User
from ..services.exotic_product_booking import ExoticBookingRequest
from ..services.native_template_booking import NativeBookingPreview, stage_template_booking, template_booking_preview
from ..services.product_repository import load_product, owned_record


router = APIRouter(prefix="/api/products", tags=["native-template-booking"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
Database = Annotated[Session, Depends(get_session)]


def _fail(exc: ValueError):
    raise HTTPException(status_code=getattr(exc, "status", 422), detail={
        "code": getattr(exc, "code", "NATIVE_BOOKING_INVALID"), "message": str(exc),
    }) from exc


@router.get("/{product_id}/native/booking")
def prepare_booking(product_id: int, current: PricerUser, session: Database,
                    calculation_id: Annotated[int, Query(gt=0)]) -> NativeBookingPreview:
    try:
        owned_record(session, product_id, current)
        product = load_product(session, product_id, allow_native=True)
        return template_booking_preview(session, current, product, calculation_id, secret=receipt_signing_secret())
    except ValueError as exc:
        _fail(exc)


@router.post("/{product_id}/native/book", status_code=201)
def book_template(product_id: int, body: ExoticBookingRequest, current: PricerUser, session: Database) -> ExoticBookedResponse:
    try:
        product, deal = stage_template_booking(session, current, product_id, body, secret=receipt_signing_secret())
        result = ExoticBookedResponse(product=product, deal_id=deal.id, deal_reference=deal.reference)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, detail={"code": "NATIVE_BOOKING_CONFLICT",
            "message": "Conflit pendant le booking. Rechargez le dossier."}) from exc
    except (ValueError, HTTPException) as exc:
        session.rollback()
        if isinstance(exc, HTTPException):
            raise
        _fail(exc)
