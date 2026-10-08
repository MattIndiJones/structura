"""Direct optimizer pricing in a spawned worker; no database or live closure."""


def price_optimizer_candidate_job(payload: dict) -> dict:
    from ...product_optimizer.contracts import OptimizationRequest, OptimizationCandidate
    from ...product_optimizer.service import evaluate_candidate

    request = OptimizationRequest.model_validate(payload["request"])
    candidate = OptimizationCandidate.model_validate(payload["candidate"])
    if payload.get("phase") == "validation":
        from ...product_optimizer.validation import evaluate_validation
        return evaluate_validation(request, candidate, payload["shortlist_size"]).model_dump(mode="json")
    return evaluate_candidate(request, candidate).model_dump(mode="json")
