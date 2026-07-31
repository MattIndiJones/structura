"""Canonical workflow states introduced by the Phase-0 safety tranche.

Legacy RFQ status values remain stored for compatibility.  ``rfq_business_status``
is the single documented bridge to the target vocabulary; no controller may
invent a second mapping.
"""
from __future__ import annotations

from enum import Enum


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
