"""Stateless server evidence for optionally retained exploratory prices."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from ..core.valuation_context import canonical_fingerprint, canonical_json


_SIGNATURE_VERSION = 2
_DOMAIN = "product-pricing-v2:"


def _signature(secret: str, claims: dict, *, domain: str = _DOMAIN) -> str:
    return hmac.new(
        secret.encode(), (domain + canonical_json(claims)).encode(), hashlib.sha256,
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
        "result_fingerprint": canonical_fingerprint(result_payload),
    }
    signature = _signature(secret, _claims(evidence))
    return {**evidence, "server_signature": signature}


def verify_server_receipt(receipt: dict, *, secret: str) -> dict:
    evidence = {k: v for k, v in receipt.items() if k != "server_signature"}
    if evidence.get("signature_version") == _SIGNATURE_VERSION:
        if evidence.get("result_fingerprint") != canonical_fingerprint(
                evidence.get("result")):
            raise ValueError(
                "Le résultat de pricing a été modifié. Relancez le pricing.")
        expected = _signature(secret, _claims(evidence))
    elif "signature_version" not in evidence:
        # Compatibility for receipts issued during the first implementation.
        expected = _signature(secret, evidence, domain="product-pricing-v1:")
    else:
        raise ValueError(
            "La version de la preuve serveur est inconnue. Relancez le pricing.")
    if not hmac.compare_digest(expected, str(receipt.get("server_signature") or "")):
        raise ValueError(
            "Le résultat de pricing ne porte pas une preuve serveur valide. "
            "Relancez le pricing avant de le conserver.")
    return evidence
