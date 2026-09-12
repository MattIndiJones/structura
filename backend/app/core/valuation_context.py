"""Canonical inputs shared by pricing, MtM, Greeks, shocks and VaR.

The booked deal stores a market snapshot for two distinct reasons: reopen the
original assumptions in the Pricer, and explain which inputs produced the
initial fair value.  This module is the single unit boundary between the API
schemas (engine units) and that persisted display snapshot.

``ValuationContext`` itself is deliberately plain JSON data.  It contains no
database row, closure or compiled PayScript and can therefore cross the worker
process boundary used by VaR.  ``run_valuation`` is the only adapter to
``run_mc``; scenario bumps override only the requested fields.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
import hashlib
import json
import math
from typing import Any


SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass
class ValuationContext:
    underlyings: list[dict]
    corr_matrix: list[list[float]]
    r: float
    T: float
    N: int
    model: str
    seed: int = 42
    antithetic: bool = True
    user_params: dict = field(default_factory=dict)
    yield_curve: list = field(default_factory=list)
    funding_curve: list = field(default_factory=list)
    funding_spread: float = 0.0
    sigma_r: float = 0.0
    a_r: float = 0.0
    barrier_monitoring: str = "weekly"
    maturity_payment_t: float | None = None
    value_date_t: float = 0.0
    strike_set_t: float | None = None
    state: dict = field(default_factory=dict)
    # Raw contractual inputs travel with the serializable context for audit and
    # worker reconstruction; the compiled script remains the run-time argument.
    script_text: str = ""
    constats: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        payload = asdict(self)
        # Fail here, close to construction, rather than much later when a VaR
        # worker or JSON column tries to serialize a live object.
        canonical_json(payload)
        return payload


def valuation_context_from_dict(payload: dict) -> ValuationContext:
    known = {name for name in ValuationContext.__dataclass_fields__}
    return ValuationContext(**{key: deepcopy(value) for key, value in payload.items()
                               if key in known})


def run_valuation(script, context: ValuationContext | dict, **overrides):
    """Run one valuation; ``overrides`` contains scenario/Greek bumps only."""
    from .payscript.engine import run_mc

    allowed_bumps = {
        "spot_mult", "spot_base", "vol_add", "dr", "ds", "corr_delta",
        "corr_matrix", "wof0_init",
    }
    unexpected = sorted(set(overrides) - allowed_bumps)
    if unexpected:
        raise ValueError(
            "Le scénario tente de remplacer un élément du contexte de valorisation : "
            + ", ".join(unexpected))

    ctx = (context if isinstance(context, ValuationContext)
           else valuation_context_from_dict(context))
    kwargs = {
        "script": script,
        "underlyings": deepcopy(ctx.underlyings),
        "corr_matrix": deepcopy(ctx.corr_matrix),
        "r": ctx.r,
        "T_max": ctx.T,
        "N": ctx.N,
        "model": ctx.model,
        "seed": ctx.seed,
        "antithetic": ctx.antithetic,
        "user_params": deepcopy(ctx.user_params),
        "yield_curve": deepcopy(ctx.yield_curve),
        "funding_curve": deepcopy(ctx.funding_curve),
        "funding_spread": ctx.funding_spread,
        "sigma_r": ctx.sigma_r,
        "a_r": ctx.a_r,
        "barrier_monitoring": ctx.barrier_monitoring,
        "maturity_payment_t": ctx.maturity_payment_t,
        "value_date_t": ctx.value_date_t,
        "strike_set_t": ctx.strike_set_t,
        **deepcopy(ctx.state),
    }
    kwargs.update(overrides)
    return run_mc(**kwargs)


_PCT_FIELDS = {
    "sigma", "q", "dividend_decay", "sigma_fx", "rho_sfx", "v0",
    "theta", "xi", "rho_h", "rho_rS", "alpha", "beta", "rho", "nu",
    "skew", "curvature",
}


def _display_underlying(raw: dict) -> dict:
    out = {}
    for key, value in raw.items():
        if key == "dividend_curve":
            out["dividendCurve"] = [
                {"T": float(node[0]), "rate": float(node[1]) * 100.0}
                for node in (value or [])
            ]
            out["dividendCurveEnabled"] = bool(value)
        elif key == "dividend_decay":
            out["dividendDecay"] = float(value or 0.0) * 100.0
        elif key == "ccyh":
            out[key] = float(value or 0.0) * 10_000.0
        elif key in _PCT_FIELDS:
            out[key] = float(value or 0.0) * 100.0
        else:
            out[key] = value
    out.setdefault("dividendCurve", [])
    out.setdefault("dividendCurveEnabled", False)
    out.setdefault("dividendDecay", 0.0)
    return out


def _pillar_label(maturity: float) -> str:
    months = round(maturity * 12)
    if months < 12 and abs(months / 12 - maturity) < 1e-8:
        return f"{months}M"
    return f"{maturity:g}Y"


def pricing_input_payload(request) -> dict:
    """Freeze the validated request in engine units, excluding output choices."""
    if hasattr(request, "model_dump"):
        payload = request.model_dump(mode="json")
    else:
        payload = deepcopy(dict(request))
    payload.pop("compute_greeks", None)
    payload.pop("selected_greeks", None)
    payload["seed"] = 42
    return payload


def market_snapshot_from_pricing_input(payload: dict) -> dict:
    """Convert one validated pricing request to the deal snapshot format."""
    funding_curve = payload.get("funding_curve") or []
    funding_spread = float(payload.get("funding_spread") or 0.0)
    funding_pillars = [
        {"label": _pillar_label(float(t)), "T": float(t),
         "spread": float(spread) * 100.0}
        for t, spread in funding_curve
    ]
    if funding_curve:
        funding = {
            "enabled": True,
            "mode": "pillars",
            "level": funding_pillars[0]["spread"],
            "pillars": funding_pillars,
        }
    else:
        funding = {
            "enabled": funding_spread != 0.0,
            "mode": "flat",
            "level": funding_spread * 100.0,
            "pillars": [],
        }

    sigma_r = float(payload.get("sigma_r") or 0.0)
    a_r = float(payload.get("a_r") or 0.0)
    rate_model = "deterministic" if sigma_r == 0.0 else (
        "hull_white" if a_r != 0.0 else "abm")
    strike = payload.get("strike_date")
    maturity = payload.get("maturity_date")
    tenor = payload.get("T")
    if tenor is None and strike and maturity:
        tenor = ((date.fromisoformat(maturity) - date.fromisoformat(strike)).days
                 / 365.25)

    return {
        "snapshot_version": SCHEMA_VERSION,
        "r": float(payload.get("r") or 0.0) * 100.0,
        "T": tenor,
        "N": int(payload.get("N") or 20_000),
        "seed": int(payload.get("seed") or 42),
        "model": payload.get("model") or "constant",
        "antithetic": bool(payload.get("antithetic", True)),
        "deal_ccy": payload.get("settlement_ccy") or "EUR",
        "rateModel": rate_model,
        "sigma_r": sigma_r * 100.0,
        "a_r": a_r,
        "barrierMonitoring": payload.get("barrier_monitoring") or "weekly",
        "yieldCurve": [
            {"label": _pillar_label(float(t)), "T": float(t),
             "rate": float(rate) * 100.0}
            for t, rate in (payload.get("yield_curve") or [])
        ],
        "funding": funding,
        # Flat engine-unit aliases make older Python consumers easy to migrate
        # and remove any ambiguity about whether 1.5 means 1.5% or 150%.
        "funding_curve": deepcopy(funding_curve),
        "funding_spread": funding_spread,
        "underlyings": [_display_underlying(u)
                        for u in (payload.get("underlyings") or [])],
        "corrMatrix": deepcopy(payload.get("corr_matrix") or []),
        "user_params": deepcopy(payload.get("user_params") or {}),
        "constats": deepcopy(payload.get("constats") or {}),
    }


def build_pricing_receipt(request, price: float) -> dict:
    pricing_input = pricing_input_payload(request)
    fingerprint = canonical_fingerprint(pricing_input)
    market_snapshot = market_snapshot_from_pricing_input(pricing_input)
    market_snapshot["pricing_input_fingerprint"] = fingerprint
    return {
        "version": SCHEMA_VERSION,
        "input_fingerprint": fingerprint,
        "price_pct": round(float(price) * 100.0, 10),
        "pricing_input": pricing_input,
        "market_snapshot": market_snapshot,
    }


def verify_pricing_receipt(receipt: dict) -> dict:
    if not isinstance(receipt, dict) or receipt.get("version") != SCHEMA_VERSION:
        raise ValueError("Preuve de pricing absente ou de version inconnue.")
    pricing_input = receipt.get("pricing_input")
    if not isinstance(pricing_input, dict):
        raise ValueError("La preuve de pricing ne contient pas ses entrées.")
    expected = canonical_fingerprint(pricing_input)
    if receipt.get("input_fingerprint") != expected:
        raise ValueError("L'empreinte de la preuve de pricing est invalide.")
    rebuilt = market_snapshot_from_pricing_input(pricing_input)
    rebuilt["pricing_input_fingerprint"] = expected
    return {**receipt, "market_snapshot": rebuilt}


def funding_from_market_snapshot(market: dict, elapsed: float = 0.0) -> tuple[list, float]:
    """Engine-unit funding from new or legacy deal snapshots.

    Missing funding is a real legacy state requested by the desk: it means a
    visible flat zero, not an inherited value from the previously opened deal.
    """
    if market.get("funding_curve"):
        curve = [[float(t), float(level)] for t, level in market["funding_curve"]]
        residual = [[max(0.0, t - elapsed), level] for t, level in curve
                    if t > elapsed]
        return (residual, 0.0) if residual else ([], curve[-1][1])
    if market.get("funding_spread") is not None:
        return [], float(market.get("funding_spread") or 0.0)

    saved = market.get("funding") or {}
    if saved.get("enabled") and saved.get("mode") == "pillars":
        curve = [[float(node["T"]), float(node["spread"]) / 100.0]
                 for node in (saved.get("pillars") or [])]
        residual = [[max(0.0, t - elapsed), level] for t, level in curve
                    if t > elapsed]
        return ((residual, 0.0) if residual else
                ([], curve[-1][1] if curve else 0.0))
    if saved.get("enabled"):
        return [], float(saved.get("level") or 0.0) / 100.0
    return [], 0.0


def deterministic_cashflow_pv(
    amount: float,
    time_to_payment: float,
    *,
    r: float,
    yield_curve: list | None = None,
    funding_curve: list | None = None,
    funding_spread: float = 0.0,
) -> float:
    """Present-value a known receivable on the engine's curve convention."""
    t = max(0.0, float(time_to_payment))

    def zero_at(curve: list | None, fallback: float) -> float:
        points = sorted(
            (float(point[0]), float(point[1])) for point in (curve or [])
            if len(point) >= 2 and float(point[0]) >= 0.0)
        if not points:
            return fallback
        if t <= points[0][0]:
            return points[0][1]
        if t >= points[-1][0]:
            return points[-1][1]
        for (left_t, left_r), (right_t, right_r) in zip(points, points[1:]):
            if left_t <= t <= right_t:
                weight = (t - left_t) / (right_t - left_t)
                return left_r + weight * (right_r - left_r)
        return points[-1][1]

    risk_free = zero_at(yield_curve, float(r))
    credit = zero_at(funding_curve, float(funding_spread))
    return float(amount) * math.exp(-(risk_free + credit) * t)
