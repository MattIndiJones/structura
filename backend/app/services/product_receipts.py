"""Stateless server evidence for optionally retained exploratory prices."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from ..core.valuation_context import (
    canonical_fingerprint, canonical_json, json_transport_fingerprint,
    json_transport_json,
)


_SIGNATURE_VERSION = 2
_DOMAIN = "product-pricing-v2:"


def _signature(secret: str, claims: dict, *, domain: str = _DOMAIN,
               transport_stable: bool = True) -> str:
    serialized = (json_transport_json(claims) if transport_stable
                  else canonical_json(claims))
    return hmac.new(
        secret.encode(), (domain + serialized).encode(), hashlib.sha256,
    ).hexdigest()


def _claims(evidence: dict) -> dict:
    return {
        "signature_version": _SIGNATURE_VERSION,
        "receipt_version": evidence.get("version"),
        "input_fingerprint": evidence.get("input_fingerprint"),
        "price_pct": evidence.get("price_pct"),
        "calculated_at": evidence.get("calculated_at"),
        "result_fingerprint": evidence.get("result_fingerprint"),
    }


def signed_receipt(receipt: dict, *, secret: str, result: dict | None = None) -> dict:
    result_payload = result or {"price": receipt["price_pct"] / 100.0}
    evidence = {
        **receipt,
        "signature_version": _SIGNATURE_VERSION,
        "calculated_at": datetime.utcnow().isoformat(),
        "result": result_payload,
        "result_fingerprint": json_transport_fingerprint(result_payload),
    }
    signature = _signature(secret, _claims(evidence))
    return {**evidence, "server_signature": signature}


def verify_server_receipt(receipt: dict, *, secret: str) -> dict:
    evidence = {k: v for k, v in receipt.items() if k != "server_signature"}
    if evidence.get("signature_version") == _SIGNATURE_VERSION:
        result = evidence.get("result")
        supplied_fingerprint = evidence.get("result_fingerprint")
        accepted_fingerprints = {
            json_transport_fingerprint(result), canonical_fingerprint(result),
        }
        if isinstance(result, dict):
            # Compatibility with v2 receipts that fingerprinted typed pricing
            # outputs before they crossed the JavaScript JSON boundary.
            legacy_result = {
                key: ([float(item) for item in value]
                      if isinstance(value, list)
                      else float(value) if isinstance(value, (int, float))
                      and not isinstance(value, bool) else value)
                for key, value in result.items()
            }
            accepted_fingerprints.add(canonical_fingerprint(legacy_result))
        if supplied_fingerprint not in accepted_fingerprints:
            raise ValueError(
                "Le résultat de pricing a été modifié. Relancez le pricing.")
        expected = _signature(secret, _claims(evidence))
    elif "signature_version" not in evidence:
        # Compatibility for receipts issued during the first implementation.
        expected = _signature(
            secret, evidence, domain="product-pricing-v1:",
            transport_stable=False)
    else:
        raise ValueError(
            "La version de la preuve serveur est inconnue. Relancez le pricing.")
    actual = str(receipt.get("server_signature") or "")
    valid_signature = hmac.compare_digest(expected, actual)
    if not valid_signature and evidence.get("signature_version") == _SIGNATURE_VERSION:
        legacy_claims = _claims(evidence)
        if isinstance(legacy_claims.get("price_pct"), (int, float)):
            legacy_claims["price_pct"] = float(legacy_claims["price_pct"])
        legacy_expected = _signature(
            secret, legacy_claims, transport_stable=False)
        valid_signature = hmac.compare_digest(legacy_expected, actual)
    if not valid_signature:
        raise ValueError(
            "Le résultat de pricing ne porte pas une preuve serveur valide. "
            "Relancez le pricing avant de le conserver.")
    return evidence
