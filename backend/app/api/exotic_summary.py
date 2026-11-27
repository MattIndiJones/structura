"""Signed calculation summaries and the shared AI workbench for rates/credit."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from .auth import get_current_pricer, receipt_signing_secret
from ..core.ai_contract import AiOptions
from ..core.valuation_context import json_transport_fingerprint
from ..db.database import get_session
from ..db.models import User
from ..services.exotic_product import read_exotic_calculation, read_exotic_price
from ..services.exotic_valuation import ExoticCreditScenario, read_scenario
from ..services.llm.exotic_analysis import exotic_analysis_prompt, exotic_summary, native_summary
from ..services.llm.providers import LlmError
from ..services.llm.workbench import generate_text
from ..services.native_calculation_archive import CREDIT_CALCULATION_KIND, RATES_CALCULATION_KIND, read_native_calculation
from ..services.product_receipts import verify_credit_receipt, verify_rates_receipt
from ..services.product_repository import ProductError, owned_record


router = APIRouter(prefix="/api/products/exotics/summary", tags=["rates-credit-summary"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
Database = Annotated[Session, Depends(get_session)]
_KINDS = {"rates": RATES_CALCULATION_KIND, "credit": CREDIT_CALCULATION_KIND}
_VERIFY = {"rates": verify_rates_receipt, "credit": verify_credit_receipt}


class SummarySource(BaseModel):
    pricing_mode: Literal["monte_carlo", "native"] = "monte_carlo"
    family: Literal["rates", "credit"] | None = None
    receipt: dict | None = Field(default=None, min_length=1)
    product_id: int | None = Field(default=None, gt=0, strict=True)
    calculation_id: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def check_source(self):
        source = (self.receipt is not None, self.product_id is not None, self.calculation_id is not None)
        if source not in ((True, False, False), (False, True, True)):
            raise ValueError("Fournissez un reçu signé ou la référence d’un calcul conservé.")
        if self.pricing_mode == "native" and self.family is None:
            raise ValueError("Sélectionnez la famille du calcul natif.")
        return self


class SummaryTurn(BaseModel):
    question: str = Field(min_length=1, max_length=2400)
    answer: str = Field(min_length=1, max_length=12000)


class SummaryAnalysisRequest(AiOptions, SummarySource):
    intention: Literal["analyse", "restructuration", "argumentaire", "critique", "libre"] = "analyse"
    question: str = Field(default="", max_length=2000)
    history: tuple[SummaryTurn, ...] = Field(default=(), max_length=4)


class SummaryResponse(BaseModel):
    resume: str
    result_fingerprint: str


def _describe(body: SummarySource, current: User, session: Session) -> SummaryResponse:
    secret = receipt_signing_secret()
    if body.receipt is not None and body.receipt.get("user_id") != current.id:
        raise ProductError("SUMMARY_RECEIPT_NOT_FOUND", "Reçu de valorisation introuvable.", 404)

    if body.pricing_mode == "native":
        family = body.family
        claims = (_VERIFY[family](body.receipt, secret=secret) if body.receipt is not None else
                  read_native_calculation(session, body.product_id, body.calculation_id, current, kind=_KINDS[family]))
        if claims["context"]["product_id"] is not None:
            record = owned_record(session, claims["context"]["product_id"], current)
            if record.reference != claims.get("product_reference"):
                raise ProductError("SUMMARY_RECEIPT_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
        fingerprint = json_transport_fingerprint(claims["result"])
        return SummaryResponse(resume=native_summary(claims, family, fingerprint), result_fingerprint=fingerprint)

    receipt = body.receipt
    if receipt is None:
        archived = read_exotic_calculation(session, body.product_id, body.calculation_id, current, secret=secret)
        receipt = archived.receipt
    claims, result = read_exotic_price(receipt, secret=secret)
    scenario = read_scenario(claims["request"])
    if body.family is not None and body.family != scenario.family:
        raise ValueError("La famille ne correspond pas au reçu signé.")
    if isinstance(scenario, ExoticCreditScenario) and scenario.credit.realized:
        product_id = scenario.credit.realized.product.product_id
        if product_id is not None:
            owned_record(session, product_id, current)
    fingerprint = claims["result_fingerprint"]
    return SummaryResponse(resume=exotic_summary(scenario, result, fingerprint), result_fingerprint=fingerprint)


def _summary_or_error(body: SummarySource, current: User, session: Session) -> SummaryResponse:
    try:
        return _describe(body, current, session)
    except ProductError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(422, "Le reçu ne porte pas un calcul vérifiable pour ce résumé.") from exc


def _prompt(body: SummaryAnalysisRequest, current: User, session: Session) -> dict:
    summary = _summary_or_error(body, current, session)
    return exotic_analysis_prompt(summary.resume, body.intention, body.question,
                                  tuple((turn.question, turn.answer) for turn in body.history))


@router.post("")
def summarize(body: SummarySource, current: PricerUser, session: Database) -> SummaryResponse:
    return _summary_or_error(body, current, session)


@router.post("/analyse/prompt")
def summarize_prompt(body: SummaryAnalysisRequest, current: PricerUser, session: Database):
    try:
        return _prompt(body, current, session)
    except LlmError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analyse")
def ask_about_summary(body: SummaryAnalysisRequest, current: PricerUser, session: Database):
    try:
        prompt = _prompt(body, current, session)
        result = generate_text(prompt, body, temperature=.4, max_tokens=2500)
        return {**result, "texte": result["text"].strip(),
                "intention": prompt["intention"], "intention_label": prompt["intention_label"]}
    except LlmError as exc:
        raise HTTPException(422, str(exc)) from exc
