"""Canonical workflow states introduced by the Phase-0 safety tranche.

Legacy RFQ status values remain stored for compatibility.  ``rfq_business_status``
is the single documented bridge to the target vocabulary; no controller may
invent a second mapping.
"""
from __future__ import annotations

import os
from enum import Enum


def amendment_four_eyes_enabled() -> bool:
    """Whether approving and applying an amendment needs a SECOND person.

    Off by default. On a tactical, single-operator desk there is nobody to
    separate duties with, and the requirement turned the only available
    correction path for a booked trade (nominal, contrepartie, price_traded,
    payment_date) into a dead end: the maker could open a request and then
    nothing could ever close it.

    What this flag governs is deliberately narrow — the identity of the second
    signatory, and nothing else. The request/approve/apply state machine, the
    contract versioning, the stale-base-version refusals and the audit trail
    are unconditional, so re-arming the control is one environment variable
    rather than a rewrite. Read through this function (never captured into a
    module constant) so a deployment or a test can flip it without import-order
    surprises.
    """
    return os.getenv(
        "STRUCTURA_AMENDMENT_FOUR_EYES", "0").strip().lower() in {"1", "true", "yes", "on"}


class WorkflowValue(str, Enum):
    def __str__(self) -> str:
        return self.value


class DataCategory(WorkflowValue):
    INDICATIVE = "INDICATIVE"
    PRICING = "PRICING"
    FIXING_CANDIDATE = "FIXING_CANDIDATE"
    FIXING_OFFICIAL = "FIXING_OFFICIAL"
    SETTLEMENT = "SETTLEMENT"
    UNKNOWN = "UNKNOWN"


class QuoteFirmness(WorkflowValue):
    UNKNOWN = "UNKNOWN"
    INDICATIVE = "INDICATIVE"
    FIRM = "FIRM"


class FixingStatus(WorkflowValue):
    EXPECTED = "EXPECTED"
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    APPLIED = "APPLIED"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CONTESTED = "CONTESTED"
    SUPERSEDED = "SUPERSEDED"
    OVERRIDDEN = "OVERRIDDEN"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class FixingPolicy(WorkflowValue):
    """How contractual fixings become official for a booked deal.

    The policy is frozen on the deal at booking time.  ``AUTO_YAHOO`` makes
    the unadjusted Yahoo close the operational reference source when the
    automated quality gates pass.  ``FOUR_EYES`` preserves the governed
    Maker/Checker workflow for controlled products.
    """

    AUTO_YAHOO = "AUTO_YAHOO"
    FOUR_EYES = "FOUR_EYES"


class LifecycleStatus(WorkflowValue):
    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    APPLIED = "APPLIED"
    STALE = "STALE"
    REJECTED = "REJECTED"
    CONTESTED = "CONTESTED"
    ERROR = "ERROR"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class AmendmentStatus(WorkflowValue):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class RfqBusinessStatus(WorkflowValue):
    DRAFT = "DRAFT"
    READY = "READY"
    SENT = "SENT"
    QUOTING = "QUOTING"
    SELECTED = "SELECTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"
    EXPIRED = "EXPIRED"


_LEGACY_RFQ_STATUS_MAP = {
    "draft": RfqBusinessStatus.DRAFT,
    "envoye": RfqBusinessStatus.SENT,
    "quote": RfqBusinessStatus.QUOTING,
    "retenue": RfqBusinessStatus.SELECTED,
    "clos": RfqBusinessStatus.EXECUTED,
    "sans_suite": RfqBusinessStatus.LOST,
}


def rfq_business_status(legacy_status: str, *, ready: bool = False) -> str:
    """Return the target status without rewriting a legacy database row."""
    if legacy_status == "draft" and ready:
        return RfqBusinessStatus.READY.value
    return _LEGACY_RFQ_STATUS_MAP.get(
        legacy_status, RfqBusinessStatus.DRAFT).value
