"""Versioned server-to-server FRN and CLN Research interface for QISTRA."""
from __future__ import annotations

import json
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BeforeValidator, Field, model_validator
from sqlalchemy import func
from sqlmodel import Session, select

from ..core.compute.pricers.research_rates_credit import execute_research_rates_credit
from ..core.compute.queue_store import enqueue_batch
from ..core.product.models import CLNTerms, FRNTerms, FrozenModel, TradeIntent, product_terms_schema
from ..core.structured_indices.rates_credit import (
    RatesCreditJob, RatesCreditPrepared, RatesCreditPrepareRequest, RatesCreditResult,
    prepare_rates_credit, price_rates_credit,
)
from ..core.structured_indices.rates_credit_evidence import (
    Digest, Operation, PreparationProof, RESEARCH_RATES_ISSUE, RESEARCH_RATES_JOB_KINDS, RESEARCH_RATES_MTM,
    RESEARCH_RATES_PROFILE, ResearchReceipt, research_rates_access, research_rates_engine_fingerprint,
    sign_admission, sign_preparation, verify_preparation, verify_research_receipt,
)
from ..core.structured_indices.schemas import Reference
from ..core.valuation_context import json_transport_fingerprint
from ..db.database import get_session
from ..db.models import ComputeBatch, User
from ..services.product_repository import ProductError, load_product, owned_record
from .auth import get_current_pricer, receipt_signing_secret


router = APIRouter(prefix="/api/v1/structured-indices/rates-credit", tags=["structured-indices"])
_MAX_JOBS = 128
_MAX_WORKERS = 4
Database = Annotated[Session, Depends(get_session)]


def _strict_native_terms(terms):
    if not isinstance(terms, (FRNTerms, CLNTerms)) and product_terms_schema(terms) != 2:
        raise ValueError("La préparation Research exige des termes de schéma 2.")
    return terms


Terms = Annotated[FRNTerms | CLNTerms, Field(discriminator="instrument_type"), BeforeValidator(_strict_native_terms)]


def _fail(code: str, message: str, status: int = 422):
    raise HTTPException(status, {"code": code, "message": message})


def _research_user(current: Annotated[User, Depends(get_current_pricer)]) -> User:
    if not research_rates_access(current):
        _fail("RESEARCH_ACCESS_DENIED", "Ce compte n’a pas accès à la recette Research taux et crédit.", 403)
    return current


ResearchUser = Annotated[User, Depends(_research_user)]


class ResearchPrepare(FrozenModel):
    millesime_id: Reference
    terms_version: int | None = Field(default=None, ge=1, strict=True)
    terms: Terms | None = None
    intent: TradeIntent | None = None
    product_id: int | None = Field(default=None, ge=1, strict=True)
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    expected_engine_fingerprint: Digest | None = None

    @model_validator(mode="after")
    def exactly_one_origin(self) -> Self:
        if self.product_id is None:
            if self.terms is None or self.intent is None or self.expected_revision is not None:
                raise ValueError("Le millésime Research requiert des termes et une intention, ou un Product conservé.")
        elif self.terms is not None or self.intent is not None:
            raise ValueError("Les termes et l’intention d’un Product conservé sont lus côté serveur.")
        return self


class PreparedResearch(FrozenModel):
    millesime: RatesCreditPrepared
    preparation_proof: PreparationProof


class ResearchJob(RatesCreditJob):
    preparation_proof: PreparationProof

    def compute_job(self) -> RatesCreditJob:
        return RatesCreditJob.model_validate(self.model_dump(mode="json", exclude={"preparation_proof"}))


class ResearchBatch(FrozenModel):
    run_id: Reference
    request_key: Reference
    label: str = Field(default="", max_length=160)
    max_workers: int = Field(default=_MAX_WORKERS, strict=True, ge=1, le=_MAX_WORKERS)
    expected_engine_fingerprint: Digest | None = None
    jobs: tuple[ResearchJob, ...] = Field(min_length=1, max_length=_MAX_JOBS)

    @model_validator(mode="after")
    def distinct_jobs_and_terms(self) -> Self:
        if len({job.job_id for job in self.jobs}) != len(self.jobs):
            raise ValueError("Les identifiants de job doivent être uniques dans le lot.")
        if len({(job.millesime.millesime_id, job.cutoff) for job in self.jobs}) != len(self.jobs):
            raise ValueError("Un millésime et un arrêté ne peuvent apparaître qu’une fois dans le lot.")
        frozen_terms = {}
        for job in self.jobs:
            millesime = job.millesime
            if frozen_terms.setdefault(millesime.millesime_id, millesime.fingerprint) != millesime.fingerprint:
                raise ValueError("Les termes figés d’un millésime doivent rester identiques dans le lot.")
        return self


class ResearchBatchTicket(FrozenModel):
    id: int
    status: Literal["queued", "running", "completed", "completed_with_failures", "failed", "cancelled"]
    total_jobs: int
    request_key: str
    results_path: str
    run_id: str
    kind: Literal["research_rates_credit_issue", "research_rates_credit_mtm"]


class ResearchLifecycle(FrozenModel):
    run_id: Reference
    job: ResearchJob
    expected_engine_fingerprint: Digest | None = None


class ResearchResult(FrozenModel):
    result: RatesCreditResult
    receipt: ResearchReceipt


class ResearchReceiptRequest(ResearchResult):
    job: ResearchJob


class ResearchVerification(FrozenModel):
    valid: Literal[True] = True
    run_id: Reference
    job_id: str
    result_fingerprint: Digest


class ResearchReplay(ResearchVerification):
    matched: Literal[True] = True
    result: RatesCreditResult


def _raise_known(exc: ValueError):
    _fail(
        getattr(exc, "code", "RESEARCH_INPUT_INVALID"),
        str(exc), getattr(exc, "status", 422),
    )


def _require_engine(expected: str | None) -> str:
    actual = research_rates_engine_fingerprint()
    if expected is not None and expected != actual:
        _fail("RESEARCH_ENGINE_UNAVAILABLE", "Le moteur prévu pour la recette n’est plus disponible.", 409)
    return actual


def _product_binding(session: Session, current: User, product_id: int, reference: str):
    try:
        record = owned_record(session, product_id, current)
        if record.reference != reference:
            _fail("RESEARCH_PRODUCT_NOT_FOUND", "Product source introuvable.", 404)
    except ProductError as exc:
        _raise_known(exc)


def research_batch_readable(session: Session, batch: ComputeBatch, current: User) -> bool:
    """Keep the common batch reader scoped to both owner and Product access."""
    if batch.kind not in RESEARCH_RATES_JOB_KINDS:
        return True
    if batch.user_id != current.id or not research_rates_access(current):
        return False
    try:
        params = json.loads(batch.params_json)
        bindings = params["product_bindings"]
        if params["profile"] != RESEARCH_RATES_PROFILE or not isinstance(bindings, list):
            return False
        for binding in bindings:
            _product_binding(session, current, binding["product_id"], binding["product_reference"])
    except (HTTPException, KeyError, TypeError, ValueError):
        return False
    return True


def _verify_job(session: Session, current: User, job: ResearchJob, secret: str) -> dict:
    millesime = job.millesime
    if job.preparation_proof.owner_user_id != current.id:
        _fail("RESEARCH_PREPARATION_NOT_FOUND", "Préparation Research introuvable.", 404)
    if not verify_preparation(job.preparation_proof, millesime.fingerprint, current.id, secret):
        _fail("RESEARCH_PREPARATION_INVALID", "La préparation signée ne correspond pas au millésime ou au compte.")
    if millesime.product_id is not None:
        _product_binding(session, current, millesime.product_id, millesime.product_reference)
    return job.compute_job().model_dump(mode="json")


@router.get("/capabilities")
def capabilities(current: ResearchUser):
    return {
        "schema_version": 1, "profile": RESEARCH_RATES_PROFILE,
        "engine_fingerprint": research_rates_engine_fingerprint(),
        "result_schema_version": 1, "receipt_schema_version": 1,
        "instruments": [
            {"instrument_type": "FRN", "payoff_mode": "native", "terms_schema_version": 2,
             "operations": ["prepare", "issue", "lifecycle", "mtm"], "market_kind": "rates"},
            {"instrument_type": "CLN", "payoff_mode": "native", "terms_schema_version": 2,
             "operations": ["prepare", "issue", "lifecycle", "mtm"], "market_kind": "cln_research"},
        ],
        "methods": ["deterministic"], "market_quality": "synthetic",
        "currency": "EUR", "unit": "EUR_per_100", "position_sides": ["BUY"],
        "cutoff_timezone": "Europe/Paris", "value_date_policy": "valuation_date",
        "max_jobs": _MAX_JOBS, "max_workers": _MAX_WORKERS,
        "supports_receipt_verification": True, "supports_numerical_replay": True,
    }


@router.post("/prepare")
def prepare(body: ResearchPrepare, current: ResearchUser, session: Database) -> PreparedResearch:
    try:
        _require_engine(body.expected_engine_fingerprint)
        intent = body.intent
        request = {
            "millesime_id": body.millesime_id, "terms_version": body.terms_version or 1,
            "terms": body.terms,
        }
        source = {}
        if body.product_id is not None:
            owned_record(session, body.product_id, current)
            product = load_product(session, body.product_id, revision=body.expected_revision,
                                   terms_version=body.terms_version, allow_native=True)
            if not isinstance(product.terms, (FRNTerms, CLNTerms)):
                _fail("RESEARCH_TERMS_UNSUPPORTED", "Le Product source doit être un FRN ou une CLN.")
            if product.native_schedule is None:
                _fail("RESEARCH_SCHEDULE_REQUIRED", "Le Product source doit porter un échéancier figé.")
            request.update(terms_version=product.terms_version, terms=product.terms)
            intent = product.intent
            source.update(schedule=product.native_schedule, product_id=product.product_id, product_reference=product.reference)
        # The Research position only needs the economic sizing and direction.
        request["intent"] = TradeIntent(nominal=intent.nominal, side=intent.side)
        prepared = prepare_rates_credit(RatesCreditPrepareRequest.model_validate(request), **source)
        return PreparedResearch(
            millesime=prepared,
            preparation_proof=sign_preparation(prepared.fingerprint, current.id, receipt_signing_secret()),
        )
    except ValueError as exc:
        _raise_known(exc)


def _job_envelope(job: dict, *, run_id: str, user_id: int, operation: Operation, secret: str) -> dict:
    admission = sign_admission(job, run_id=run_id, user_id=user_id, operation=operation, secret=secret)
    return {"job": job, "admission": admission.model_dump(mode="json")}


def _submit(session: Session, current: User, body: ResearchBatch, operation: Operation) -> ResearchBatchTicket:
    kind = RESEARCH_RATES_ISSUE if operation == "issue" else RESEARCH_RATES_MTM
    if operation == "issue" and len({job.millesime.millesime_id for job in body.jobs}) != len(body.jobs):
        _fail("RESEARCH_BATCH_DUPLICATE_ISSUE", "Un millésime doit être unique dans un lot d’émission.")
    secret = receipt_signing_secret()
    jobs = [_verify_job(session, current, job, secret) for job in body.jobs]
    digest = json_transport_fingerprint(body.model_dump(mode="json"))
    bindings = sorted({
        (job.millesime.product_id, job.millesime.product_reference) for job in body.jobs
        if job.millesime.product_id is not None
    })
    try:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        batch = session.exec(select(ComputeBatch).where(
            ComputeBatch.user_id == current.id,
            ComputeBatch.kind.in_(RESEARCH_RATES_JOB_KINDS),
            func.json_extract(ComputeBatch.params_json, "$.request_key") == body.request_key,
        )).first()
        if batch is None:
            engine_fingerprint = _require_engine(body.expected_engine_fingerprint)
            envelopes = [
                _job_envelope(job, run_id=body.run_id, user_id=current.id, operation=operation, secret=secret)
                for job in jobs
            ]
            labels = [f"{job.millesime.millesime_id} · {job.valuation_date}" for job in body.jobs]
            batch = enqueue_batch(session, current.id, kind, body.label, envelopes, labels, params={
                "contract_version": 1, "profile": RESEARCH_RATES_PROFILE, "run_id": body.run_id,
                "request_key": body.request_key, "request_sha256": digest,
                "engine_fingerprint": engine_fingerprint,
                "max_workers": body.max_workers, "use_processes": True,
                "product_bindings": [
                    {"product_id": product_id, "product_reference": reference} for product_id, reference in bindings
                ],
            })
        elif batch.kind != kind or json.loads(batch.params_json)["request_sha256"] != digest:
            _fail("RESEARCH_BATCH_CONFLICT", "Cette clé désigne déjà une autre soumission Research.", 409)
        ticket = ResearchBatchTicket(
            id=batch.id, status=batch.status, total_jobs=batch.total_jobs, run_id=body.run_id, kind=kind,
            request_key=body.request_key, results_path=f"/api/compute/batches/{batch.id}",
        )
        session.commit()
        return ticket
    except Exception:
        session.rollback()
        raise


@router.post("/issue-batches", status_code=202)
def issue_batch(body: ResearchBatch, current: ResearchUser, session: Database) -> ResearchBatchTicket:
    return _submit(session, current, body, "issue")


@router.post("/mtm-batches", status_code=202)
def mtm_batch(body: ResearchBatch, current: ResearchUser, session: Database) -> ResearchBatchTicket:
    return _submit(session, current, body, "mtm")


@router.post("/lifecycle")
def lifecycle(body: ResearchLifecycle, current: ResearchUser, session: Database) -> ResearchResult:
    try:
        _require_engine(body.expected_engine_fingerprint)
        secret = receipt_signing_secret()
        job = _verify_job(session, current, body.job, secret)
        envelope = _job_envelope(job, run_id=body.run_id, user_id=current.id, operation="lifecycle", secret=secret)
        return ResearchResult.model_validate(execute_research_rates_credit(envelope, "lifecycle"))
    except ValueError as exc:
        _raise_known(exc)


def _verify_archived_job(body: ResearchReceiptRequest, current: User, session: Session) -> RatesCreditJob:
    if body.receipt.owner_user_id != current.id:
        _fail("RESEARCH_RECEIPT_NOT_FOUND", "Reçu Research introuvable.", 404)
    secret = receipt_signing_secret()
    job = _verify_job(session, current, body.job, secret)
    if not verify_research_receipt(body.receipt, job, body.result.model_dump(mode="json"), current.id, secret):
        _fail("RESEARCH_RECEIPT_INVALID", "Le reçu, les entrées ou le résultat Research ne concordent pas.")
    return RatesCreditJob.model_validate(job)


@router.post("/verify-receipt")
def verify_receipt(body: ResearchReceiptRequest, current: ResearchUser, session: Database) -> ResearchVerification:
    _verify_archived_job(body, current, session)
    return ResearchVerification(run_id=body.receipt.run_id, job_id=body.receipt.job_id,
                                result_fingerprint=body.receipt.result_fingerprint)


@router.post("/replay")
def replay(body: ResearchReceiptRequest, current: ResearchUser, session: Database) -> ResearchReplay:
    try:
        job = _verify_archived_job(body, current, session)
        if body.receipt.engine_fingerprint != research_rates_engine_fingerprint():
            _fail("RESEARCH_ENGINE_UNAVAILABLE", "Le moteur d’origine du reçu n’est plus disponible.", 409)
        result = price_rates_credit(job, operation=body.receipt.operation)
        actual = json_transport_fingerprint(result.model_dump(mode="json"))
        if actual != body.receipt.result_fingerprint:
            _fail("RESEARCH_REPLAY_MISMATCH", "Le résultat numérique diffère du reçu conservé.", 409)
        return ResearchReplay(run_id=body.receipt.run_id, job_id=body.receipt.job_id,
                              result_fingerprint=actual, result=result)
    except ValueError as exc:
        _raise_known(exc)
