"""Canonical inputs shared by pricing, MtM, Greeks, shocks and VaR.

The booked deal stores a market snapshot for two distinct reasons: reopen the
original assumptions in the Pricer, and explain which inputs produced the
initial fair value.  This module is the single unit boundary between the API
schemas (engine units) and that persisted display snapshot.

``ValuationContext`` itself is deliberately plain JSON data.  It contains no
database row, closure or compiled PayScript and can therefore cross the worker
process boundary used by VaR. ``run_valuation`` prices this context and
``run_analysis`` derives bounded analytics through the same ``run_mc`` engine;
scenario bumps override only the requested fields.
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


def _json_transport_value(value: Any) -> Any:
    """Return the value shape preserved by a browser JSON round-trip.

    JavaScript serializes ``0.0`` as ``0`` (and does the same for every
    integral float).  Python's JSON encoder preserves the decimal suffix, so a
    fingerprint taken before the response left the API could otherwise differ
    from the fingerprint of the exact same numeric inputs posted back by Vue.
    """
    if isinstance(value, dict):
        return {key: _json_transport_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_transport_value(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def json_transport_json(value: Any) -> str:
    """Canonical JSON without distinguishing ``1`` from ``1.0``."""
    return canonical_json(_json_transport_value(value))


def json_transport_fingerprint(value: Any) -> str:
    """Fingerprint JSON data after browser-stable number normalization."""
    return hashlib.sha256(json_transport_json(value).encode("utf-8")).hexdigest()


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


def valuation_context_from_request(req, compiled, *, residual=None, paths=None):
    """One dated input boundary for the price and its derived analyses."""
    from .payscript.parser import analysis_origin, effective_T_max
    origin = residual.valuation if residual is not None else analysis_origin(req)
    year_fraction = lambda day: ((day-origin).days/365.25 if residual is not None else
                                round((day-origin).days/365.25, 6)) if day is not None else None
    curve = lambda values: (residual.sur_axe_residuel(values) if residual is not None else deepcopy(values or []))
    return ValuationContext(
        underlyings=deepcopy(residual.underlyings) if residual is not None else [u.model_dump() for u in req.underlyings],
        corr_matrix=deepcopy(req.corr_matrix), r=residual.r if residual is not None else req.r,
        T=residual.T_remaining if residual is not None else effective_T_max(compiled, req.T),
        N=paths if paths is not None else req.N, model=req.model, seed=42,
        antithetic=req.antithetic, user_params=deepcopy(residual.user_params if residual is not None else req.user_params),
        yield_curve=curve(req.yield_curve), funding_curve=curve(req.funding_curve),
        funding_spread=req.funding_spread, sigma_r=req.sigma_r, a_r=req.a_r,
        barrier_monitoring=req.barrier_monitoring, maturity_payment_t=year_fraction(req.payment_date),
        value_date_t=0. if residual is not None else (year_fraction(req.value_date) or 0.),
        strike_set_t=residual.residuel.strike_set_t if residual is not None else None,
        state=deepcopy(residual.mc_kwargs) if residual is not None else {},
        script_text=residual.script_text if residual is not None else req.script,
        constats=deepcopy(residual.constats if residual is not None else req.constats))


def run_analysis(script, context: ValuationContext, kind: str, **options):
    from .payscript.engine import run_mc_paths, run_mc_proba
    if kind not in ('paths', 'proba'):
        raise ValueError('Analytique inconnue.')
    kwargs = {key: deepcopy(getattr(context, key)) for key in (
        'underlyings', 'corr_matrix', 'r', 'model', 'seed', 'antithetic', 'user_params',
        'yield_curve', 'funding_curve', 'funding_spread', 'sigma_r', 'a_r',
        'barrier_monitoring', 'maturity_payment_t', 'value_date_t', 'strike_set_t')}
    kwargs.update(T_max=context.T, state=deepcopy(context.state), **options)
    kwargs['N_stat' if kind == 'paths' else 'N'] = context.N
    result = (run_mc_paths if kind == 'paths' else run_mc_proba)(script, **kwargs)
    result['valuation_context_fingerprint'] = json_transport_fingerprint(context.to_dict())
    result['calibration_role'] = 'Frozen input evidence; no new calibration qualification'
    return result


def validate_mtf_context(script, context: ValuationContext, *, payment_aware=False):
    """Refuse inputs the nested replay cannot preserve, before any MC work."""
    from .payscript.engine import _mtf_reject_unsupported

    _mtf_reject_unsupported(context.model, context.barrier_monitoring,
                            context.yield_curve, context.sigma_r,
                            context.underlyings)
    if context.funding_curve or context.funding_spread:
        raise ValueError(
            "Le funding (spread ou courbe) n'est pas encore supporté en "
            "Mark-to-Future et dans les horizons intermédiaires KID. "
            "Cette analyse est indisponible avec ces hypothèses ; "
            "le prix conserve son funding.")
    if context.value_date_t or context.strike_set_t is not None:
        raise ValueError(
            "La value date décalée et le strike différé ne sont pas encore "
            "supportés en Mark-to-Future et dans les horizons intermédiaires KID.")
    if not payment_aware:
        delayed = (context.maturity_payment_t is not None
                   and abs(context.maturity_payment_t - context.T) > 1e-6)
        delayed = delayed or any(
            abs(p - d) > 1e-6 for ev in script.events
            for d, p in zip(ev.dates, ev.payment_dates or []))
        if delayed:
            raise ValueError(
                "Les paiements différés ne sont pas encore supportés dans "
                "l'éventail Mark-to-Future et son drill-down. "
                "Les horizons KID utilisent le rejeu distinct des créances.")


def run_valuation(script, context: ValuationContext | dict, *,
                  per_path_flows=False, flows_at_payment=False, **overrides):
    """Run one valuation; ``overrides`` contains scenario/Greek bumps only."""
    from .payscript.engine import run_mc

    allowed_bumps = {
        "spot_mult", "spot_base", "vol_add", "dr", "ds", "corr_delta",
        "corr_matrix", "wof0_init", "underlying_overrides",
    }
    unexpected = sorted(set(overrides) - allowed_bumps)
    if unexpected:
        raise ValueError(
            "Le scénario tente de remplacer un élément du contexte de valorisation : "
            + ", ".join(unexpected))

    ctx = (context if isinstance(context, ValuationContext)
           else valuation_context_from_dict(context))
    scenario_underlyings = deepcopy(ctx.underlyings)
    underlying_overrides = overrides.pop("underlying_overrides", {})
    allowed_underlying_fields = {
        "sigma", "skew", "curvature",
        "v0", "theta", "xi", "rho_h",
        "alpha", "rho", "nu",
    }
    by_key = {
        str(u.get("ticker") or u.get("name") or index): u
        for index, u in enumerate(scenario_underlyings)
    }
    by_key.update({
        str(u.get("name")): u for u in scenario_underlyings if u.get("name")
    })
    for key, changes in underlying_overrides.items():
        underlying = by_key.get(str(key))
        if underlying is None:
            raise ValueError(f"Sous-jacent inconnu dans le scénario : {key}")
        unexpected_fields = sorted(set(changes) - allowed_underlying_fields)
        if unexpected_fields:
            raise ValueError(
                f"Paramètre de modèle non autorisé pour {key} : "
                + ", ".join(unexpected_fields))
        for field_name, value in changes.items():
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"Valeur non finie pour {key}.{field_name}")
            if (underlying.get("vol_surface") and ctx.model in {"localvol", "lsv"}
                    and field_name in {"skew", "curvature"}
                    and numeric != underlying.get(field_name)):
                raise ValueError(
                    f"{key} : ce scénario utilise les anciens paramètres de smile ; "
                    "la surface SSVI exige un choc de ses propres paramètres.")
            underlying[field_name] = numeric

    kwargs = {
        "script": script,
        "underlyings": scenario_underlyings,
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
    if per_path_flows:
        kwargs.update(per_path_flows=True, flows_at_payment=flows_at_payment)
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
    fingerprint = json_transport_fingerprint(pricing_input)
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
    expected = json_transport_fingerprint(pricing_input)
    supplied = receipt.get("input_fingerprint")
    accepted = {expected, canonical_fingerprint(pricing_input)}
    if supplied not in accepted:
        # Receipts issued before transport-stable fingerprints were introduced
        # hashed Pydantic's typed floats (0.0/1.0).  Rebuild that typed request
        # so a calculation already visible in the browser remains retainable.
        try:
            from .schemas import PricingRequest
            legacy_input = pricing_input_payload(
                PricingRequest.model_validate(pricing_input))
            accepted.add(canonical_fingerprint(legacy_input))
        except (TypeError, ValueError):
            pass
    if supplied not in accepted:
        raise ValueError("L'empreinte de la preuve de pricing est invalide.")
    rebuilt = market_snapshot_from_pricing_input(pricing_input)
    rebuilt["pricing_input_fingerprint"] = supplied
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


def unsettled_cashflows_pv(context: dict, *, dr=0., ds=0.):
    """Reprice detached receivables at their actual payment times."""
    flows = context.get('unsettled_cash_flows')
    if flows is None:
        if (dr or ds) and context.get('unsettled_pv'):
            raise ValueError('Dates de paiement des créances absentes : réactualisation impossible.')
        return float(context.get('unsettled_pv', 0.))
    return sum(deterministic_cashflow_pv(
        row['cf'], row['time_to_payment'], r=context['r_frac']+dr,
        yield_curve=[[t, rate+dr] for t, rate in context.get('yc', [])],
        funding_curve=[[t, spread+ds] for t, spread in context.get('funding_curve', [])],
        funding_spread=context.get('funding_spread', 0.)+ds) for row in flows)
