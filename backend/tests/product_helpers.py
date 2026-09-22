"""Builders that keep legacy test scenarios on the canonical Product path."""
from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.api.auth import receipt_signing_secret
from backend.app.core.product.inputs import terms_from_input
from backend.app.core.schemas import PricingRequest
from backend.app.core.valuation_context import build_pricing_receipt
from backend.app.services.product_receipts import signed_receipt
from backend.app.services.product_repository import stage_internal_product


def pricing_receipt_for_deal_payload(payload: dict) -> dict:
    """Return the signed calculation evidence expected by the booking API."""
    market = payload.get("market_snapshot") or {}
    identities = payload.get("underlyings") or []
    market_underlyings = market.get("underlyings") or []
    underlyings = []
    for index, identity in enumerate(identities):
        quote = market_underlyings[index] if index < len(market_underlyings) else {}
        underlyings.append({
            "name": identity.get("name") or quote.get("name") or "Underlying",
            "ticker": identity.get("ticker") or quote.get("ticker") or "",
            "ccy": identity.get("ccy") or quote.get("ccy") or payload.get("devise", "EUR"),
            "sigma": float(quote.get("sigma", 20.0)) / 100.0,
            "q": float(quote.get("q", 0.0)) / 100.0,
        })
    count = len(underlyings)
    request = PricingRequest.model_validate({
        "script": payload["script_snapshot"],
        "underlyings": underlyings,
        "corr_matrix": market.get("corrMatrix") or market.get("corr_matrix") or [
            [1.0 if i == j else 0.0 for j in range(count)] for i in range(count)
        ],
        "r": float(market.get("r", 3.0)) / 100.0,
        "T": payload["T"],
        "N": 2000,
        "model": market.get("model") or "constant",
        "antithetic": market.get("antithetic", True),
        "user_params": market.get("user_params") or {},
        "constats": market.get("constats") or {},
        "strike_date": payload["strike_date"],
        "value_date": payload["value_date"],
        "maturity_date": payload["maturity_date"],
        "payment_date": payload.get("payment_date") or payload["maturity_date"],
        "settlement_ccy": payload.get("devise") or "EUR",
    })
    price = float(payload.get("fair_value", 100.0)) / 100.0
    return signed_receipt(
        build_pricing_receipt(request, price),
        secret=receipt_signing_secret(),
        result={"price": price},
    )


def add_pricing_receipt(payload: dict) -> dict:
    payload["pricing_receipt"] = pricing_receipt_for_deal_payload(payload)
    return payload


def attach_product_to_deal(session, deal, *, entity_id=None):
    """Persist canonical terms and attach their stable identity to ``deal``."""
    market = json.loads(deal.market_snapshot_json or "{}")
    identities = json.loads(deal.underlyings_json or "[]")
    terms = terms_from_input({
        "script": deal.script_snapshot,
        "underlyings": [{
            "name": item.get("name") or "Underlying",
            "ticker": item.get("ticker") or "",
            "ccy": item.get("ccy") or deal.devise or "EUR",
        } for item in identities],
        "user_params": market.get("user_params") or {},
        "constats": market.get("constats") or {},
        "T": deal.T,
        "strike_date": deal.strike_date,
        "value_date": deal.value_date or deal.strike_date,
        "maturity_date": deal.maturity_date,
        "payment_date": deal.payment_date or deal.maturity_date,
        "settlement_ccy": deal.devise or "EUR",
    })
    product = stage_internal_product(
        session,
        user=SimpleNamespace(
            id=deal.user_id,
            entity_id=entity_id if entity_id is not None else getattr(deal, "entity_id", None),
        ),
        name=f"Produit {deal.reference}",
        terms=terms,
        reason="Fixture reliée au Product canonique.",
    )
    deal.product_id = product.product_id
    deal.product_terms_version = product.terms_version
    return product
