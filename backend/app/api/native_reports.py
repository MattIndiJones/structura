"""Prepare and retain signed reporting drafts for native deterministic prices."""
from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlmodel import Session

from ..core.product.models import FrozenModel, FrozenObject, Product
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.database import get_session
from ..db.models import Document, User
from ..runtime import data_path
from ..services.native_calculation_archive import CREDIT_CALCULATION_KIND, RATES_CALCULATION_KIND, read_native_calculation
from ..services.native_reports import PROFILE, NativeReport, NativeReportCall, prepare_native_report
from ..services.native_write_policy import native_writes_enabled
from ..services.product_receipts import signed_exotic_receipt, verify_credit_receipt, verify_exotic_receipt, verify_rates_receipt
from ..services.product_repository import ProductError, load_product, owned_record, previous_command, stage_command, stage_revision
from .auth import get_current_pricer, receipt_signing_secret


router = APIRouter(prefix="/api/products/native-reports", tags=["native-reports"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
Database = Annotated[Session, Depends(get_session)]
_KINDS = {"rates": RATES_CALCULATION_KIND, "credit": CREDIT_CALCULATION_KIND}
_VERIFY = {"rates": verify_rates_receipt, "credit": verify_credit_receipt}


class NativeReportResponse(FrozenModel):
    report: NativeReport
    pricing_fingerprint: str
    receipt: dict


class RetainNativeReport(FrozenModel):
    product_id: int = Field(strict=True, gt=0)
    calculation_id: int = Field(strict=True, gt=0)
    expected_revision: int = Field(strict=True, gt=0)
    command_key: str = Field(min_length=8, max_length=100)
    receipt: dict = Field(min_length=1)


class RetainedNativeReport(FrozenModel):
    product: Product
    document_id: int


def _fail(exc: ValueError):
    raise HTTPException(status_code=getattr(exc, "status", 422),
                        detail={"code": getattr(exc, "code", "NATIVE_REPORT_INVALID"), "message": str(exc)}) from exc


def _read_pricing(body: NativeReportCall, session: Session, current: User, *, secret: str) -> tuple[dict, dict]:
    receipt = body.receipt
    if receipt is None:
        # The archive reads the server-owned integrity-checked record and does not
        # depend on the current signing key for a historical price receipt.
        receipt = read_native_calculation(session, body.product_id, body.calculation_id, current, kind=_KINDS[body.family])
        return receipt, receipt
    if receipt.get("user_id") != current.id:
        raise ProductError("NATIVE_REPORT_PRICING_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
    claims = _VERIFY[body.family](receipt, secret=secret)
    context = claims.get("context")
    if not isinstance(context, dict):
        raise ProductError("NATIVE_REPORT_PRICING_INVALID", "Le contexte du reçu de valorisation est manquant.", 422)
    if context.get("product_id") is not None:
        record = owned_record(session, context["product_id"], current)
        if record.reference != claims.get("product_reference"):
            raise ProductError("NATIVE_REPORT_PRICING_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
    return claims, receipt


@router.post("")
def native_report(body: NativeReportCall, current: PricerUser, session: Database) -> NativeReportResponse:
    try:
        secret = receipt_signing_secret()
        claims, pricing_receipt = _read_pricing(body, session, current, secret=secret)
        report = prepare_native_report(claims, body)
        pricing = json_transport_fingerprint(pricing_receipt)
        result = {**report.model_dump(mode="json"), "pricing_fingerprint": pricing}
        receipt = signed_exotic_receipt({
            "profile": PROFILE, "user_id": current.id,
            "request": body.model_dump(mode="json", exclude={"receipt"}), "result": result,
            "result_fingerprint": json_transport_fingerprint(result),
        }, secret=secret)
        return NativeReportResponse(report=report, pricing_fingerprint=pricing, receipt=receipt)
    except ValueError as exc:
        _fail(exc)


@router.post("/retain", status_code=201)
def retain_native_report(body: RetainNativeReport, current: PricerUser, session: Database) -> RetainedNativeReport:
    destination = None
    try:
        if not native_writes_enabled(current, session):
            raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation des brouillons natifs est fermée.", 403)
        owned_record(session, body.product_id, current, right="prepare")
        if body.receipt.get("user_id") != current.id:
            raise ProductError("NATIVE_REPORT_NOT_FOUND", "Brouillon de rapport introuvable.", 404)
        claims = verify_exotic_receipt(body.receipt, secret=receipt_signing_secret())
        request, result = claims.get("request", {}), claims.get("result", {})
        family, report = request.get("family"), result.get("report")
        if (claims.get("profile") != PROFILE or family not in _KINDS or report not in {"kid", "emt"}
                or claims.get("result_fingerprint") != json_transport_fingerprint(result)):
            raise ProductError("NATIVE_REPORT_INVALID", "Le reçu ne correspond pas à un brouillon réglementaire natif.", 422)
        archived = read_native_calculation(session, body.product_id, body.calculation_id, current, kind=_KINDS[family])
        pricing = json_transport_fingerprint(archived)
        context = archived["context"]
        if (result.get("pricing_fingerprint"), result.get("product_id"), result.get("terms_version")) != (
                pricing, body.product_id, context["terms_version"]):
            raise ProductError("NATIVE_REPORT_CALCULATION_MISMATCH", "Le brouillon ne correspond pas au calcul conservé.", 422)
        if request.get("calculation_id") not in (None, body.calculation_id):
            raise ProductError("NATIVE_REPORT_CALCULATION_MISMATCH", "La référence du calcul du brouillon a changé.", 422)

        proof = json_transport_fingerprint(body.receipt)
        metadata = {"pricing_fingerprint": pricing, "proof": proof, "calculation_id": body.calculation_id}
        command = {"operation": "retain_native_report", "product_id": body.product_id,
                   "expected_revision": body.expected_revision, **metadata}
        previous = previous_command(session, current, body.command_key, command, allow_native=True)
        product = load_product(session, body.product_id, allow_native=True)
        if previous is not None:
            snapshot = next(item.to_dict() for item in previous.documents if item.to_dict().get("proof") == proof)
            session.rollback()
            return RetainedNativeReport(product=product, document_id=snapshot["record_id"])
        if product.archived or product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Rechargez le dossier courant avant de conserver le brouillon.")

        title = "Brouillon " + report.upper() + " " + result["instrument_type"]
        filename = f"brouillon-natif-{report}-{uuid4().hex}.json"
        relative_path = f"{current.id}/{filename}"
        destination = data_path("documents") / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(canonical_json({"report": result, "receipt": body.receipt}), encoding="utf-8")
        doc = Document(product_id=product.product_id, product_terms_version=context["terms_version"], user_id=current.id,
                       doc_type=f"native_{report}_draft", title=title, filename=filename, file_path=relative_path,
                       metadata_json=canonical_json(metadata))
        session.add(doc)
        session.flush()
        snapshot = FrozenObject({"kind": "DOCUMENT", "record_id": doc.id, "doc_type": doc.doc_type,
                                 "title": title, "filename": filename, "terms_version": context["terms_version"],
                                 "created_at": doc.created_at.isoformat(), "proof": proof})
        saved = stage_revision(session, product.model_copy(update={"documents": (*product.documents, snapshot)}),
                               expected_revision=product.revision, actor_id=current.id,
                               action="PRODUCT_DOCUMENT_RETAINED", reason=title)
        stage_command(session, current, body.command_key, command, saved)
        response = RetainedNativeReport(product=saved, document_id=doc.id)
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        if destination is not None:
            destination.unlink(missing_ok=True)
        if isinstance(exc, ValueError):
            _fail(exc)
        raise
