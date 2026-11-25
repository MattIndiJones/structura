"""Research interface for external index portfolios backed by Structura."""

import json
from datetime import date
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import func
from sqlmodel import Session, select

from ..core.calibration import realized_market
from ..core.compute.pricers.athena import ATHENA_ISSUE_KIND, ATHENA_MTM_KIND
from ..core.compute.queue_store import enqueue_batch
from ..core.structured_indices.athena import check_athena_lifecycle
from ..core.structured_indices.pricing_catalogue import AthenaPricingCatalogue, athena_pricing_catalogue
from ..core.structured_indices.schemas import (
    AthenaContract, AthenaIssueRequest, AthenaLifecycleRequest, AthenaMarkRequest, Level, Reference,
)
from ..core.valuation_context import json_transport_fingerprint
from ..db.database import get_session
from ..db.models import ComputeBatch, User
from .auth import get_current_pricer


router = APIRouter(prefix="/api/v1/structured-indices/athena", tags=["structured-indices"])
Pricer = Annotated[User, Depends(get_current_pricer)]
Database = Annotated[Session, Depends(get_session)]
_VOLATILITY_WINDOW = 252
_MAX_VOLATILITY_SESSIONS = 3_000


class AthenaBatchRequest(AthenaContract):
    request_key: Reference
    label: str = Field("", max_length=160)
    max_workers: int = Field(4, strict=True, ge=1, le=4)


class AthenaIssueBatch(AthenaBatchRequest):
    jobs: tuple[AthenaIssueRequest, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def distinct_notes(self) -> Self:
        if len({job.note_id for job in self.jobs}) != len(self.jobs):
            raise ValueError("Un millésime doit être unique dans un lot d'émission.")
        return self


class AthenaMarkBatch(AthenaBatchRequest):
    jobs: tuple[AthenaMarkRequest, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def distinct_marks(self) -> Self:
        if len({(job.vintage.note_id, job.market.as_of) for job in self.jobs}) != len(self.jobs):
            raise ValueError("Un couple millésime et date doit être unique dans un lot de MTM.")
        terms_by_note = {}
        for job in self.jobs:
            previous = terms_by_note.setdefault(job.vintage.note_id, job.vintage)
            if job.vintage != previous:
                raise ValueError("Les termes d'un millésime doivent rester identiques dans le lot.")
        return self


class AthenaBatchTicket(AthenaContract):
    id: int
    status: Literal["queued", "running", "completed", "completed_with_failures", "failed", "cancelled"]
    total_jobs: int
    request_key: str
    results_path: str


@router.get("/pricing-models", response_model_exclude_none=True)
def pricing_models(current: Pricer) -> AthenaPricingCatalogue:
    return athena_pricing_catalogue()


class AthenaVolatilityClose(AthenaContract):
    day: date
    close: Level


class AthenaRealizedVolatilityRequest(AthenaContract):
    closes: tuple[AthenaVolatilityClose, ...] = Field(
        min_length=1, max_length=_MAX_VOLATILITY_SESSIONS + _VOLATILITY_WINDOW + 1,
    )
    sessions: tuple[date, ...] = Field(min_length=1, max_length=_MAX_VOLATILITY_SESSIONS)

    @model_validator(mode="after")
    def validate_chronology(self) -> Self:
        for days in (tuple(point.day for point in self.closes), self.sessions):
            if any(earlier >= later for earlier, later in zip(days, days[1:])):
                raise ValueError("Les dates doivent être uniques et classées par ordre croissant.")
        return self


class AthenaVolatilityObservation(AthenaContract):
    day: date
    volatility: float = Field(gt=0, allow_inf_nan=False)


class AthenaRealizedVolatility(AthenaContract):
    method: Literal["RMS_LOG_RETURNS"] = "RMS_LOG_RETURNS"
    window_sessions: Literal[252] = _VOLATILITY_WINDOW
    annualization: Literal[252] = 252
    observations: tuple[AthenaVolatilityObservation, ...]


@router.post("/realized-volatility")
def realize_volatility(body: AthenaRealizedVolatilityRequest, current: Pricer) -> AthenaRealizedVolatility:
    """Apply Structura's estimator to the caller's qualified closing series."""
    positions = {point.day: index for index, point in enumerate(body.closes)}
    closes = [point.close for point in body.closes]
    ticker = "SX5E"
    observations = []
    for day in body.sessions:
        end = positions.get(day)
        if end is None:
            raise HTTPException(422, f"Clôture SX5E absente au {day.isoformat()}.")
        if end < _VOLATILITY_WINDOW:
            raise HTTPException(422, f"Historique SX5E insuffisant au {day.isoformat()} : 253 clôtures requises.")
        window = closes[end - _VOLATILITY_WINDOW:end + 1]
        try:
            result = realized_market({ticker: window}, [ticker], _VOLATILITY_WINDOW)
            observations.append(AthenaVolatilityObservation(day=day, volatility=result["sigma"][ticker]))
        except ValueError as exc:
            raise HTTPException(422, f"Volatilité réalisée SX5E indisponible au {day.isoformat()} : {exc}") from exc
    return AthenaRealizedVolatility(observations=tuple(observations))


def _matches_previous_batch(params: dict, body: AthenaIssueBatch | AthenaMarkBatch, digest: str) -> bool:
    if params["request_sha256"] == digest:
        return True
    if params.get("contract_version") != 1 or any(
        job.pricing.model != "constant" or not job.pricing.antithetic for job in body.jobs
    ):
        return False

    # Previously the model and antithetic convention were fixed implicitly.
    # Recompute the old digest so a retry still refers to its originally admitted batch.
    previous_payload = body.model_dump(mode="json")
    for job, payload in zip(body.jobs, previous_payload["jobs"], strict=True):
        pricing = payload["pricing"]
        pricing.pop("model")
        pricing.pop("antithetic")
        if "n_paths" not in job.pricing.model_fields_set:
            pricing["n_paths"] = 4096
    return json_transport_fingerprint(previous_payload) == params["request_sha256"]


def _submit_batch(session: Session, user_id: int, kind: str, body: AthenaIssueBatch | AthenaMarkBatch,
                  labels: list[str]) -> AthenaBatchTicket:
    payloads = [job.model_dump(mode="json") for job in body.jobs]
    digest = json_transport_fingerprint(body.model_dump(mode="json"))

    # The SQLite queue has one writer. Lock before checking the caller's key so
    # a network retry concurrent with the original submit gets the same batch.
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    batch = session.exec(select(ComputeBatch).where(
        ComputeBatch.user_id == user_id,
        ComputeBatch.kind == kind,
        func.json_extract(ComputeBatch.params_json, "$.request_key") == body.request_key,
    )).first()
    if batch is None:
        batch = enqueue_batch(
            session, user_id, kind, body.label, payloads, labels,
            params={"max_workers": body.max_workers, "use_processes": True, "contract_version": 2,
                    "request_key": body.request_key, "request_sha256": digest},
        )
    elif not _matches_previous_batch(json.loads(batch.params_json), body, digest):
        session.rollback()
        raise HTTPException(409, "Cette clé de demande désigne déjà un lot différent.")

    ticket = AthenaBatchTicket(id=batch.id, status=batch.status, total_jobs=batch.total_jobs,
                               request_key=body.request_key, results_path=f"/api/compute/batches/{batch.id}")
    # Release the lock on the idempotent read path as well.
    session.commit()
    return ticket


@router.post("/issue-batches", status_code=202)
def submit_issue_batch(body: AthenaIssueBatch, current: Pricer, session: Database) -> AthenaBatchTicket:
    labels = [job.note_id for job in body.jobs]
    return _submit_batch(session, current.id, ATHENA_ISSUE_KIND, body, labels)


@router.post("/mtm-batches", status_code=202)
def submit_mark_batch(body: AthenaMarkBatch, current: Pricer, session: Database) -> AthenaBatchTicket:
    labels = [f"{job.vintage.note_id} · {job.market.as_of}" for job in body.jobs]
    return _submit_batch(session, current.id, ATHENA_MTM_KIND, body, labels)


class AthenaBarrierCheck(AthenaContract):
    kind: Literal["call", "coupon", "capital"]
    observation_date: date
    fixing: float
    initial_fixing: float
    ratio: float
    threshold: float
    condition_met: bool


class AthenaCashFlow(AthenaContract):
    event_id: str
    observed_date: date
    payment_date: date
    amount: float


class AthenaRedemption(AthenaCashFlow):
    kind: Literal["redemption"] | None = Field(default=None, exclude_if=lambda value: value is None)


class AthenaCouponClaim(AthenaCashFlow):
    kind: Literal["coupon"]
    memory_periods: int | None = Field(
        None, strict=True, ge=0, le=39, exclude_if=lambda value: value is None,
        description="Nombre de périodes antérieures rattrapées par ce flux Phoenix mémoire.",
    )


class AthenaParticipationClaim(AthenaCashFlow):
    kind: Literal["participation"]


class AthenaOptionSettlement(AthenaCashFlow):
    kind: Literal["option_payoff"]


class AthenaLifecycleResult(AthenaContract):
    day: date
    note_id: str
    terms_reference: str
    receipt_id: str
    terminated: bool
    status: Literal["active", "called", "matured"]
    redemption: AthenaRedemption | None
    coupon_claims: list[AthenaCouponClaim] | None = Field(default=None, exclude_if=lambda value: value is None)
    participation_claims: list[AthenaParticipationClaim] | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    option_settlement: AthenaOptionSettlement | None = Field(
        default=None, exclude_if=lambda value: value is None,
        description="Montant du payoff de l’option longue calculé à maturité, y compris si le montant est nul.",
    )
    barriers: list[AthenaBarrierCheck]
    fixing_references: dict[str, str]


@router.post("/lifecycle")
def check_lifecycle(body: AthenaLifecycleRequest, current: Pricer) -> AthenaLifecycleResult:
    try:
        result = check_athena_lifecycle(body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return AthenaLifecycleResult.model_validate(result)
