"""Pricing, offline replay and valuation attribution of frozen exotic scenarios."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, RootModel, model_validator
from sqlmodel import Session

from .auth import get_current_pricer, receipt_signing_secret
from ..core.product.exotic_credit_mc import CreditMcResult
from ..core.product.exotic_rates_calibration import HullWhiteCalibrationResult, calibrate_hull_white
from ..core.product.exotic_rates_mc import HwMarket, RatesMCResult
from ..core.product.exotic_rates_payscript import PROFILE as EXOTIC_RATES_SCRIPT_PROFILE
from ..core.product.exotic_valuation_explain import ValuationExplain
from ..core.product.models import FrozenModel, FrozenObject, Product, TradeIntent
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.database import get_session
from ..db.models import Document, User
from ..runtime import data_path
from ..services.exotic_valuation import (
    CALIBRATION_PROFILE, MAX_PATHS, MAX_WORK, PROFILE, ExoticCalibrationCall, ExoticCreditScenario, ExoticRatesScenario,
    ExoticScenario, ExoticValuationError, exotic_engine_fingerprint, price_exotic_scenario, read_scenario, result_payload,
)
from ..services.native_calculation_archive import (
    CREDIT_CALCULATION_KIND, RATES_CALCULATION_KIND, read_native_calculation,
)
from ..services.product_receipts import (
    signed_exotic_receipt, verify_credit_receipt, verify_exotic_receipt, verify_rates_receipt,
)
from ..services.product_repository import ProductError, load_product, owned_record, previous_command, stage_command, stage_revision
from ..services.exotic_product import read_exotic_calculation
from ..services.exotic_paths import ExoticPaths, preview_exotic_paths
from ..services.exotic_contract_profile import ExoticContractProfileCall, ExoticContractProfileResult, exotic_contract_profile
from ..services.exotic_backtest import ExoticBacktestRequest, ExoticBacktestResult, backtest_exotic_claims
from ..services.exotic_reports import ExoticEmtPreview, ExoticKidPreview, ReportCall, prepare_exotic_report
from ..services.exotic_mtf import ExoticMtfCall, ExoticMtfResult, mark_exotic_to_future
from ..services.native_write_policy import native_writes_enabled
from ..core.access import can_book


router = APIRouter(prefix="/api/products/exotics", tags=["exotic-pricer"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
Database = Annotated[Session, Depends(get_session)]
REPORT_PROFILE = "eur-exotic-indicative-report-v1"


class ExoticPriceBody(RootModel[ExoticScenario]):
    @model_validator(mode="before")
    @classmethod
    def read_frozen_json(cls, value):
        # Use the same JSON reader as replay, including nested Product snapshots.
        return read_scenario(value)


class ExoticPriceResponse(FrozenModel):
    result: RatesMCResult | CreditMcResult
    receipt: dict


class ExoticCalibrationResponse(FrozenModel):
    result: HullWhiteCalibrationResult
    receipt: dict


class ExoticReportResponse(FrozenModel):
    report: ExoticKidPreview | ExoticEmtPreview
    pricing_fingerprint: str
    receipt: dict


class RetainReportCall(FrozenModel):
    product_id: int = Field(gt=0)
    calculation_id: int = Field(gt=0)
    expected_revision: int = Field(gt=0)
    command_key: str = Field(min_length=8, max_length=100)
    receipt: dict = Field(min_length=1)


class RetainedReport(FrozenModel):
    product: Product
    document_id: int


class ReplayRequest(FrozenModel):
    receipt: dict = Field(min_length=1)


class ReplayResponse(FrozenModel):
    matched: Literal[True]
    result_fingerprint: str
    result: RatesMCResult | CreditMcResult


class CompareRequest(FrozenModel):
    start_receipt: dict = Field(min_length=1)
    end_receipt: dict = Field(min_length=1)


class NativeCompareReceipts(CompareRequest):
    mode: Literal["receipts"]
    family: Literal["rates", "credit"]


class NativeCompareArchives(FrozenModel):
    mode: Literal["archive"]
    family: Literal["rates", "credit"]
    product_id: int = Field(ge=1, strict=True)
    start_calculation_id: int = Field(ge=1, strict=True)
    end_calculation_id: int = Field(ge=1, strict=True)


NativeCompareRequest = Annotated[NativeCompareReceipts | NativeCompareArchives, Field(discriminator="mode")]


def _fail(exc: ValueError):
    raise HTTPException(
        status_code=getattr(exc, "status", 422),
        detail={"code": getattr(exc, "code", "EXOTIC_INPUT_INVALID"), "message": str(exc)},
    ) from exc


def _receipt(body: FrozenModel, result: dict, user: User, *, profile: str = PROFILE) -> dict:
    return signed_exotic_receipt({
        "profile": profile, "user_id": user.id, "engine_fingerprint": exotic_engine_fingerprint(),
        "request": body.model_dump(mode="json"), "result": result,
        "result_fingerprint": json_transport_fingerprint(result),
    }, secret=receipt_signing_secret())


def _verified_claims(receipt: dict, user: User, *, profile: str = PROFILE) -> dict:
    if receipt.get("user_id") != user.id:
        raise ExoticValuationError("EXOTIC_RECEIPT_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
    claims = verify_exotic_receipt(receipt, secret=receipt_signing_secret())
    if claims["profile"] != profile or claims["result_fingerprint"] != json_transport_fingerprint(claims["result"]):
        raise ExoticValuationError("EXOTIC_RECEIPT_INVALID", "L’empreinte du résultat est incohérente.")
    return claims


def _verify(receipt: dict, user: User, session: Session) -> dict:
    claims = _verified_claims(receipt, user)
    realized = claims["request"].get("credit", {}).get("realized")
    if realized is not None and realized["product"]["product_id"] is not None:
        owned_record(session, realized["product"]["product_id"], user)
    return claims


def _check_calibration(body: ExoticScenario, user: User):
    if not isinstance(body, ExoticRatesScenario) or body.calibration_receipt is None:
        return
    claims = _verified_claims(body.calibration_receipt.to_dict(), user, profile=CALIBRATION_PROFILE)
    request = claims["request"]
    calibrated = HwMarket.model_validate(claims["result"]["market"])
    if (
        body.valuation_date.isoformat() != request["valuation_date"] or datetime.fromisoformat(request["cutoff"]) > body.cutoff
        or body.market.model_dump(exclude={"funding_bps"}) != calibrated.model_dump(exclude={"funding_bps"})
    ):
        raise ExoticValuationError("EXOTIC_CALIBRATION_MISMATCH", "Le marché ou l’arrêté de pricing diffère de la calibration signée.", 409)


def _bind_realized_product(body: ExoticScenario, user: User, session: Session) -> ExoticScenario:
    if not isinstance(body, ExoticCreditScenario) or body.credit.realized is None:
        return body
    realized = body.credit.realized
    supplied = realized.product
    product = supplied
    if supplied.product_id is not None:
        owned_record(session, supplied.product_id, user)
        product = load_product(session, supplied.product_id, revision=supplied.revision,
                               terms_version=supplied.terms_version, allow_native=True)
        if product.terms_version != body.terms_version:
            raise ExoticValuationError("EXOTIC_PRODUCT_TERMS_VERSION", "La version de termes ne correspond pas au Product lié.", 409)
    economic = Product(
        product_id=product.product_id, reference=product.reference if product.product_id else None,
        revision=product.revision if product.product_id else 0, terms_version=product.terms_version,
        terms=product.terms, native_schedule=product.native_schedule,
        intent=TradeIntent(nominal=product.intent.nominal, side=product.intent.side),
    )
    return body.model_copy(update={"credit": body.credit.model_copy(update={
        "realized": realized.model_copy(update={"product": economic}),
    })})


@router.get("/capabilities")
def capabilities(current: PricerUser, session: Database):
    can_write = native_writes_enabled(current, session)
    return {
        "profile": PROFILE, "engine_fingerprint": exotic_engine_fingerprint(),
        "market_quality": "synthetic", "currency": "EUR", "primary_unit": "EUR",
        "time_axis": "years_from_value_date_act365f", "value_date_equals_valuation_date": True,
        "market_timezone": "Europe/Paris",
        "rates": {
            "model": "hull_white_1f", "instruments": ["cms", "cms_cap_floor", "cms_steepener", "range_accrual",
                                                       "callable", "bermudan"],
            "calibration": ["normal", "shifted_lognormal", "pv"], "mean_reversion": "fixed_input",
            "payscript_profile": EXOTIC_RATES_SCRIPT_PROFILE,
        },
        "credit": {
            "models": ["independence", "gaussian_one_factor"],
            "instruments": ["cds_control", "cln_control", "first_to_default", "nth_to_default"],
        },
        "limits": {"paths": MAX_PATHS, "paths_times_events": MAX_WORK},
        "supports_replay": True, "supports_explain": True, "supports_paths": True,
        "supports_product_writes": can_write, "supports_booking": can_write and can_book(current),
    }


@router.post("/price")
def price(body: ExoticPriceBody, current: PricerUser, session: Database) -> ExoticPriceResponse:
    try:
        scenario = _bind_realized_product(body.root, current, session)
        _check_calibration(scenario, current)
        result = result_payload(price_exotic_scenario(scenario))
        return ExoticPriceResponse(result=result, receipt=_receipt(scenario, result, current))
    except ValueError as exc:
        _fail(exc)


@router.post("/rates/calibration")
def rates_calibration(body: ExoticCalibrationCall, current: PricerUser) -> ExoticCalibrationResponse:
    try:
        result = calibrate_hull_white(body.calibration)
        receipt = _receipt(body, result.model_dump(mode="json"), current, profile=CALIBRATION_PROFILE)
        return ExoticCalibrationResponse(result=result, receipt=receipt)
    except ValueError as exc:
        _fail(exc)


@router.post("/replay")
def replay(body: ReplayRequest, current: PricerUser, session: Database) -> ReplayResponse:
    try:
        claims = _verify(body.receipt, current, session)
        if claims["engine_fingerprint"] != exotic_engine_fingerprint():
            raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur du reçu n’est plus disponible.", 409)
        result = result_payload(price_exotic_scenario(read_scenario(claims["request"])))
        digest = json_transport_fingerprint(result)
        if digest != claims["result_fingerprint"]:
            raise ExoticValuationError("EXOTIC_REPLAY_MISMATCH", "Le calcul reproduit diffère du résultat archivé.", 409)
        return ReplayResponse(matched=True, result_fingerprint=digest, result=result)
    except ValueError as exc:
        _fail(exc)


@router.post("/paths")
def preview_paths(body: ReplayRequest, current: PricerUser, session: Database) -> ExoticPaths:
    try:
        claims = _verify(body.receipt, current, session)
        if claims["engine_fingerprint"] != exotic_engine_fingerprint():
            raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur du reçu n’est plus disponible.", 409)
        return preview_exotic_paths(read_scenario(claims["request"]), claims["result_fingerprint"])
    except ValueError as exc:
        _fail(exc)


@router.post("/contract-profile")
def contract_profile(body: ExoticContractProfileCall, current: PricerUser, session: Database) -> ExoticContractProfileResult:
    try:
        claims = _verify(body.receipt, current, session)
        if claims["engine_fingerprint"] != exotic_engine_fingerprint():
            raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur du reçu n’est plus disponible.", 409)
        return exotic_contract_profile(read_scenario(claims["request"]), flow_id=body.flow_id, points=body.points)
    except ValueError as exc:
        _fail(exc)


@router.post("/backtest")
def backtest(body: ExoticBacktestRequest, current: PricerUser, session: Database) -> ExoticBacktestResult:
    try:
        claims = [_verify(item.to_dict(), current, session) for item in body.receipts]
        return backtest_exotic_claims(body.tape_id, claims)
    except ValueError as exc:
        _fail(exc)


@router.post("/mtf")
def mark_to_future(body: ExoticMtfCall, current: PricerUser, session: Database) -> ExoticMtfResult:
    try:
        claims = _verify(body.receipt, current, session)
        if claims["engine_fingerprint"] != exotic_engine_fingerprint():
            raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur du reçu n’est plus disponible.", 409)
        return mark_exotic_to_future(read_scenario(claims["request"]), horizons_years=body.horizons_years,
                                     paths=body.paths, archived_result=claims["result"])
    except ValueError as exc:
        _fail(exc)


@router.post("/reports")
def prepare_report(body: ReportCall, current: PricerUser, session: Database) -> ExoticReportResponse:
    try:
        claims = _verify(body.receipt, current, session)
        if claims["engine_fingerprint"] != exotic_engine_fingerprint():
            raise ExoticValuationError("EXOTIC_ENGINE_UNAVAILABLE", "Le moteur du reçu n’est plus disponible.", 409)
        report = prepare_exotic_report(read_scenario(claims["request"]), body)
        pricing_digest = claims["result_fingerprint"]
        result = {**report.model_dump(mode="json"), "pricing_fingerprint": pricing_digest}
        return ExoticReportResponse(
            report=report, pricing_fingerprint=pricing_digest, receipt=_receipt(
                body, result, current, profile=REPORT_PROFILE,
            ),
        )
    except ValueError as exc:
        _fail(exc)


@router.post("/reports/retain", status_code=201)
def retain_report(body: RetainReportCall, current: PricerUser, session: Database) -> RetainedReport:
    destination = None
    try:
        if not native_writes_enabled(current, session):
            raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation du brouillon est fermée.", 403)
        owned_record(session, body.product_id, current, right="prepare")
        claims = _verified_claims(body.receipt, current, profile=REPORT_PROFILE)
        archived = read_exotic_calculation(
            session, body.product_id, body.calculation_id, current, secret=receipt_signing_secret(),
        )
        metadata = {"pricing_fingerprint": archived.receipt["result_fingerprint"],
                    "calculation_id": body.calculation_id, "proof": json_transport_fingerprint(body.receipt)}
        if (claims["request"]["receipt"] != archived.receipt
                or claims["result"]["pricing_fingerprint"] != metadata["pricing_fingerprint"]):
            raise ProductError("EXOTIC_REPORT_MISMATCH", "Le brouillon ne correspond pas au calcul conservé.", 422)
        command = {"operation": "retain_exotic_report", "product_id": body.product_id, **metadata}
        previous = previous_command(session, current, body.command_key, command, allow_native=True)
        product = load_product(session, body.product_id, allow_native=True)
        if previous is not None:
            document = next(item for item in previous.documents if item.to_dict().get("proof") == metadata["proof"])
            return RetainedReport(product=product, document_id=document.to_dict()["record_id"])
        if product.archived or product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Rechargez le dossier courant avant de conserver le brouillon.")
        report = claims["result"]["report"]
        title = "Brouillon KID taux/crédit" if report == "kid" else "Brouillon EMT taux/crédit"
        filename = f"brouillon-{report}-{uuid4().hex}.json"
        relative_path = f"{current.id}/{filename}"
        destination = data_path("documents") / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(canonical_json({"report": claims["result"], "receipt": body.receipt}), encoding="utf-8")
        doc = Document(product_id=product.product_id, product_terms_version=product.terms_version,
                       user_id=current.id, doc_type=f"exotic_{report}_draft", title=title,
                       filename=filename, file_path=relative_path, metadata_json=canonical_json(metadata))
        session.add(doc)
        session.flush()
        snapshot = FrozenObject({"kind": "DOCUMENT", "record_id": doc.id, "doc_type": doc.doc_type,
                                 "title": title, "filename": filename, "terms_version": product.terms_version,
                                 "created_at": doc.created_at.isoformat(), "proof": metadata["proof"]})
        saved = stage_revision(session, product.model_copy(update={"documents": (*product.documents, snapshot)}),
                               expected_revision=product.revision, actor_id=current.id,
                               action="PRODUCT_DOCUMENT_RETAINED", reason=title)
        stage_command(session, current, body.command_key, command, saved)
        response = RetainedReport(product=saved, document_id=doc.id)
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        if destination is not None:
            destination.unlink(missing_ok=True)
        if isinstance(exc, ValueError):
            _fail(exc)
        raise


@router.post("/explain")
def compare(body: CompareRequest, current: PricerUser, session: Database) -> ValuationExplain:
    from ..services.exotic_explain import explain_exotic_receipts

    try:
        start = _verify(body.start_receipt, current, session)
        end = _verify(body.end_receipt, current, session)
        return explain_exotic_receipts(start, end)
    except ValueError as exc:
        _fail(exc)


@router.post("/explain-native")
def compare_native(body: NativeCompareRequest, current: PricerUser, session: Database) -> ValuationExplain:
    from ..services.native_valuation_explain import explain_native_calculations

    kind, verify = ((RATES_CALCULATION_KIND, verify_rates_receipt) if body.family == "rates"
                    else (CREDIT_CALCULATION_KIND, verify_credit_receipt))
    try:
        if isinstance(body, NativeCompareArchives):
            ids = (body.start_calculation_id, body.end_calculation_id)
            claims = tuple(read_native_calculation(session, body.product_id, item, current, kind=kind) for item in ids)
        else:
            receipts = (body.start_receipt, body.end_receipt)
            ids = tuple(json_transport_fingerprint(receipt) for receipt in receipts)
            if any(receipt.get("user_id") != current.id for receipt in receipts):
                raise ExoticValuationError("EXOTIC_RECEIPT_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
            claims = tuple(verify(receipt, secret=receipt_signing_secret()) for receipt in receipts)
            for claim in claims:
                if claim["context"]["product_id"] is not None:
                    owned_record(session, claim["context"]["product_id"], current)
        return explain_native_calculations(*claims, start_archive_id=ids[0], end_archive_id=ids[1])
    except ValueError as exc:
        _fail(exc)
