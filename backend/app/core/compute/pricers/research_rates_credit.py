"""Queue worker entry points for the FRN/CLN Research pricer."""
from ...structured_indices.rates_credit_evidence import (
    Operation, ResearchAdmission, research_rates_engine_fingerprint, sign_research_receipt, verify_admission,
)


def execute_research_rates_credit(payload: dict, operation: Operation) -> dict:
    from ...instance_signing import receipt_signing_secret
    from ...structured_indices.rates_credit import RatesCreditJob, price_rates_credit

    job = RatesCreditJob.model_validate(payload["job"])
    admission = ResearchAdmission.model_validate(payload["admission"])
    secret = receipt_signing_secret()
    if not verify_admission(admission, job.model_dump(mode="json"), operation, secret):
        raise ValueError("RESEARCH_ADMISSION_INVALID : le job ne correspond pas à la demande admise.")
    if admission.engine_fingerprint != research_rates_engine_fingerprint():
        raise ValueError("RESEARCH_ENGINE_UNAVAILABLE : la version de moteur du lot n’est plus disponible.")
    result = price_rates_credit(job, operation=operation).model_dump(mode="json")
    receipt = sign_research_receipt(admission, result, secret)
    return {"result": result, "receipt": receipt.model_dump(mode="json")}


def _execute_queued_job(payload: dict, operation: Operation) -> dict:
    try:
        return execute_research_rates_credit(payload, operation)
    except ValueError as exc:
        # A process-pool worker must return an exception that can be unpickled.
        code = getattr(exc, "code", None)
        message = f"{code} : {exc}" if code else str(exc)
        raise ValueError(message) from None


def research_rates_credit_issue_job(payload: dict) -> dict:
    return _execute_queued_job(payload, "issue")


def research_rates_credit_mtm_job(payload: dict) -> dict:
    return _execute_queued_job(payload, "mtm")
