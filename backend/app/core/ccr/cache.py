"""Reuse frozen CCR base valuations, never a client-supplied risk decision."""
from copy import deepcopy
import json
from sqlalchemy import func
from sqlmodel import select

from ...db.models import CCRExposureCalculation, DealEvent, ProductRecord, ProductTermsVersion
from ...services.market_data import market_data_provider_for_deal
from ..valuation_context import canonical_fingerprint


def preparation_key(session, entity_id, deals, request, fingerprint):
    params = request.model_dump(mode="json")
    # Scenario changes do not alter the unstressed base valuation. Permission
    # to fetch data is likewise not an economic market assumption.
    for key in ("stress", "credit_spread_multiplier", "wwr", "n_outer", "n_inner", "n_dates",
                "mode", "allow_market_fetch", "refresh_mtm", "common_rate_source"):
        params.pop(key, None)
    evidence = []
    for deal in deals:
        product = session.get(ProductRecord, deal.product_id) if deal.product_id else None
        terms = session.exec(select(ProductTermsVersion).where(
            ProductTermsVersion.product_id == deal.product_id,
            ProductTermsVersion.version == deal.product_terms_version)).first() if product else None
        events = session.exec(select(DealEvent).where(DealEvent.deal_id == deal.id).order_by(DealEvent.id)).all()
        evidence.append({"deal": deal.model_dump(mode="json"),
            "product": product.model_dump(mode="json") if product else None,
            "terms": terms.model_dump(mode="json") if terms else None,
            "events": [event.model_dump(mode="json") for event in events],
            "provider": market_data_provider_for_deal(deal, session)})
    return canonical_fingerprint({"entity_id": entity_id, "request": params, "deals": evidence,
                                  "implementation": fingerprint})


def find_prepared_base(session, entity_id, request, key):
    if request.refresh_mtm or request.proposed:
        return None
    rows = session.exec(select(CCRExposureCalculation).where(
        CCRExposureCalculation.entity_id == entity_id,
        CCRExposureCalculation.counterparty_id == request.counterparty_id,
        CCRExposureCalculation.as_of_date == str(request.as_of_date),
        func.json_extract(CCRExposureCalculation.inputs_json, "$.preparation_cache.key") == key,
    ).order_by(CCRExposureCalculation.id.desc()))
    for row in rows:
        inputs = json.loads(row.inputs_json)
        if inputs.get("common_market", {}).get("error"):
            continue
        trades = inputs["trades"]
        if not trades or any(t.get("missing") or t.get("mtm_fraction") is None or not t.get("replay") for t in trades):
            continue
        return row.id, deepcopy(inputs)
    return None


def archived_histories(session, entity_id, request):
    """Older runs can supply prices even without the new validity fingerprint.

    Rebuild their MtMs once under current terms/events; do not assume old
    valuations are still valid. Manual histories must have the same origin.
    """
    if request.refresh_mtm:
        return []
    rows = session.exec(select(CCRExposureCalculation.id, CCRExposureCalculation.inputs_json).where(
        CCRExposureCalculation.entity_id == entity_id,
        CCRExposureCalculation.counterparty_id == request.counterparty_id,
        CCRExposureCalculation.as_of_date == str(request.as_of_date),
    ).order_by(CCRExposureCalculation.id.desc()).limit(50))
    found, seen = [], set()
    manual = request.model_dump(mode="json")["price_histories"]
    for run_id, raw in rows:
        inputs = json.loads(raw)
        previous = inputs["request"]
        if previous.get("data_scope", "PRODUCTION") != request.data_scope or previous.get("price_histories", {}) != manual:
            continue
        for data in inputs.get("market_histories", {}).values():
            key = canonical_fingerprint(data)
            if key not in seen:
                found.append({**data, "reused_from_run_id": run_id})
                seen.add(key)
    return found
