"""Explicit risk-book origin and immutable calculation-universe metadata."""
from typing import Literal

DataScope = Literal["PRODUCTION", "UAT"]
HistoryDataScope = Literal["PRODUCTION", "UAT", "LEGACY_UNQUALIFIED"]


def deal_data_scope(deal) -> DataScope:
    return "UAT" if deal.uat_batch_id is not None else "PRODUCTION"


def select_risk_deals(deals, data_scope: DataScope):
    if data_scope not in {"PRODUCTION", "UAT"}:
        raise ValueError("Périmètre de risque invalide.")
    return [deal for deal in deals if deal_data_scope(deal) == data_scope]


def risk_scope_metadata(deals, data_scope: DataScope):
    return dict(data_scope=data_scope, is_test=data_scope == "UAT", scope_version=1,
        requested_deals=[dict(deal_id=d.id, reference=d.reference, uat_batch_id=d.uat_batch_id,
            nominal=d.nominal, currency=d.devise, product_id=d.product_id,
            product_terms_version=d.product_terms_version, contract_version=d.contract_version) for d in deals])


def archived_data_scope(params, *, require_view=False) -> HistoryDataScope:
    """Never infer old aggregate provenance from today's deals or memberships."""
    scope = params.get("data_scope")
    if scope not in {"PRODUCTION", "UAT"}:
        return "LEGACY_UNQUALIFIED"
    if require_view and params.get("scope") not in {"global", "portfolio"}:
        return "LEGACY_UNQUALIFIED"
    return scope
