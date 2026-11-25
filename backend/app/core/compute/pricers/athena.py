"""Rebuild the validated Athena request in the pricing worker process."""
from __future__ import annotations


ATHENA_ISSUE_KIND = "athena_issue"
ATHENA_MTM_KIND = "athena_mtm"
ATHENA_JOB_KINDS = frozenset({ATHENA_ISSUE_KIND, ATHENA_MTM_KIND})


def price_athena_issue_job(payload: dict) -> dict:
    from ...structured_indices.athena import price_athena_issue
    from ...structured_indices.schemas import AthenaIssueRequest

    return price_athena_issue(AthenaIssueRequest.model_validate(payload))


def price_athena_mark_job(payload: dict) -> dict:
    from ...structured_indices.athena import price_athena_mark
    from ...structured_indices.schemas import AthenaMarkRequest

    return price_athena_mark(AthenaMarkRequest.model_validate(payload))
