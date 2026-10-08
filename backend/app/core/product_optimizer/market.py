"""Frozen user/desk assumptions; origin is not a claim of provider quality."""
import hashlib
import json
import math
from datetime import datetime, timezone


def market_values(market):
    fields = {name: getattr(market, name) for name in
              ("rate", "yield_curve", "funding_spread", "funding_curve", "correlation")}
    for u in market.underlyings:
        fields.update({f"underlyings.{u.ticker}.{name}":getattr(u,name)
                       for name in ("sigma", "q", "dividend_curve")})
    return fields


def values_equal(left, right):
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(values_equal(a,b) for a,b in zip(left,right))
    if isinstance(left, (int,float)) and isinstance(right, (int,float)):
        return math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12)
    return left == right


def freeze_market(market):
    market = market.model_copy(deep=True)
    fields = {}
    warnings = []
    for name, used in market_values(market).items():
        provenance = market.provenance.get(name)
        reference = provenance.reference_value if provenance else used
        date = provenance.as_of if provenance else market.as_of
        active = bool(used) if name.endswith("curve") else True
        if name == "rate": active = not market.yield_curve
        if name == "funding_spread": active = not market.funding_curve
        fields[name] = {"used_value": used, "unit":"years/fraction" if name.endswith("curve") else "fraction" if name != "correlation" else "coefficient",
                       "reference_value": reference, "as_of": str(date),
                       "source": provenance.source if provenance else "USER_ASSUMPTION",
                       "method":provenance.method if provenance else "Hypothèse utilisateur",
                       "overridden":not values_equal(used,reference), "active":active}
        if provenance:
            fields[name].update({key:getattr(provenance,key) for key in ("provider", "fetched_at", "window_days", "n_observations", "warnings")})
            warnings.extend(provenance.warnings)
        if name == "correlation":
            labels = [u.ticker for u in market.underlyings]
            fields[name].update(reference_labels=market.reference_tickers or labels,used_labels=labels)
            fields[name]["overridden"] |= bool(market.reference_tickers and market.reference_tickers != labels)
        if date < market.as_of:
            warnings.append(f"Référence antérieure à la date d'hypothèses : {name} ({date}).")
    data = market.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return {"as_of": str(market.as_of), "source":market.source,
            "captured_at":datetime.now(timezone.utc).isoformat(), "imported_at":data["captured_at"],
            "hash":fingerprint, "inputs":data, "fields":fields, "warnings":warnings,
            "qualification":"Hypothèses de pricing ; origine conservée, aucune cotation de marché certifiée."}


def market_engine_kwargs(inputs):
    return {name:inputs.get(name, [] if name.endswith("curve") else 0.)
            for name in ("yield_curve", "funding_curve", "funding_spread")}
