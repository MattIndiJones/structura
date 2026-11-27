"""Admission and origin proofs for the isolated FRN/CLN Research namespace."""
from __future__ import annotations

import hashlib
import hmac
import os
import platform
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from ..access import has_capability
from ..product.models import FrozenModel
from ..valuation_context import json_transport_fingerprint, json_transport_json
from ...runtime import consultation_mode


RESEARCH_RATES_ISSUE = "research_rates_credit_issue"
RESEARCH_RATES_MTM = "research_rates_credit_mtm"
RESEARCH_RATES_JOB_KINDS = frozenset({RESEARCH_RATES_ISSUE, RESEARCH_RATES_MTM})
RESEARCH_RATES_PROFILE = "research-rates-credit-v1"
Operation = Literal["issue", "mtm", "lifecycle"]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
_ENGINE_FILES = (
    "calendar_budget.py", "calendars.py", "schedule.py", "valuation_context.py",
    "product/models.py", "product/native_schedule_models.py", "product/native_schedule.py",
    "product/rates_schedule.py", "product/cln_schedule.py", "product/rates_market.py", "product/native_market.py",
    "product/rates_pricing.py", "product/credit_facts.py", "product/credit_default.py", "product/credit_pricing.py",
    "structured_indices/rates_credit.py", "structured_indices/rates_credit_evidence.py",
    "compute/pricers/research_rates_credit.py",
)


def research_rates_access(user) -> bool:
    allowed = {item.strip() for item in os.getenv("STRUCTURA_RESEARCH_RATES_CREDIT_USERS", "").split(",") if item.strip()}
    return (
        not consultation_mode() and user.id is not None and user.username in allowed
        and has_capability(user, "business.price")
    )


@cache
def research_rates_engine_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    evidence = {
        name: hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in _ENGINE_FILES
    }
    dependencies = {name: version(name) for name in (
        "pydantic", "pydantic-core", "holidays", "python-dateutil", "numpy", "scipy",
    )}
    try:
        dependencies["tzdata"] = version("tzdata")
    except PackageNotFoundError:
        # POSIX deployments can use the system time-zone database.
        pass
    return json_transport_fingerprint({
        "profile": RESEARCH_RATES_PROFILE,
        "runtime": (platform.python_implementation(), platform.python_version(), platform.system(), platform.machine()),
        "dependencies": dependencies,
        "sources": evidence,
    })


def _signature(domain: str, claims: dict, secret: str) -> str:
    data = f"{RESEARCH_RATES_PROFILE}:{domain}:" + json_transport_json(claims)
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


class PreparationProof(FrozenModel):
    schema_version: Literal[1] = 1
    owner_user_id: int = Field(ge=1)
    prepared_fingerprint: Digest
    server_signature: Digest


class ResearchAdmission(FrozenModel):
    schema_version: Literal[1] = 1
    owner_user_id: int = Field(ge=1)
    run_id: str
    operation: Operation
    engine_fingerprint: Digest
    job_fingerprint: Digest
    server_signature: Digest


class ResearchReceipt(FrozenModel):
    schema_version: Literal[1] = 1
    owner_user_id: int = Field(ge=1)
    run_id: str
    job_id: str
    millesime_id: str
    operation: Operation
    engine_version: str
    engine_fingerprint: Digest
    prepared_fingerprint: Digest
    job_fingerprint: Digest
    request_fingerprint: Digest
    result_fingerprint: Digest
    server_signature: Digest


def sign_preparation(prepared_fingerprint: str, user_id: int, secret: str) -> PreparationProof:
    claims = {"schema_version": 1, "owner_user_id": user_id, "prepared_fingerprint": prepared_fingerprint}
    return PreparationProof(**claims, server_signature=_signature("preparation", claims, secret))


def verify_preparation(proof: PreparationProof, prepared_fingerprint: str, user_id: int, secret: str) -> bool:
    return (proof.owner_user_id, proof.prepared_fingerprint) == (user_id, prepared_fingerprint) and hmac.compare_digest(
        proof.server_signature, _signature("preparation", proof.model_dump(exclude={"server_signature"}), secret),
    )


def sign_admission(job: dict, *, run_id: str, user_id: int, operation: Operation, secret: str) -> ResearchAdmission:
    claims = {
        "schema_version": 1, "owner_user_id": user_id, "run_id": run_id, "operation": operation,
        "engine_fingerprint": research_rates_engine_fingerprint(), "job_fingerprint": json_transport_fingerprint(job),
    }
    return ResearchAdmission(**claims, server_signature=_signature("admission", claims, secret))


def verify_admission(admission: ResearchAdmission, job: dict, operation: Operation, secret: str) -> bool:
    claims = admission.model_dump(exclude={"server_signature"})
    return (
        admission.operation == operation and admission.job_fingerprint == json_transport_fingerprint(job)
        and hmac.compare_digest(admission.server_signature, _signature("admission", claims, secret))
    )


def sign_research_receipt(admission: ResearchAdmission, result: dict, secret: str) -> ResearchReceipt:
    claims = {
        "schema_version": 1, "owner_user_id": admission.owner_user_id, "run_id": admission.run_id,
        "operation": admission.operation, "engine_fingerprint": admission.engine_fingerprint,
        "job_fingerprint": admission.job_fingerprint, "result_fingerprint": json_transport_fingerprint(result),
        **{field: result[field] for field in (
            "job_id", "millesime_id", "engine_version", "prepared_fingerprint", "request_fingerprint",
        )},
    }
    return ResearchReceipt(**claims, server_signature=_signature("result", claims, secret))


def verify_research_receipt(receipt: ResearchReceipt, job: dict, result: dict, user_id: int, secret: str) -> bool:
    claims = receipt.model_dump(exclude={"server_signature"})
    return (
        receipt.owner_user_id == user_id
        and receipt.job_fingerprint == json_transport_fingerprint(job)
        and receipt.result_fingerprint == json_transport_fingerprint(result)
        and hmac.compare_digest(receipt.server_signature, _signature("result", claims, secret))
    )
