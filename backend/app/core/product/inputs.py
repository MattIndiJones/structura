"""The single conversion between canonical terms and calculation requests."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from .models import ContractParameter, FrozenObject, Product, ProductTerms, UnderlyingIdentity
from ..payscript.parser import parse_script, resolve_analysis_constats
from ..schemas import UnderlyingParams
from .calendar import freeze_calendar


TERM_FIELDS = frozenset({
    "script", "underlyings", "user_params", "constats", "T", "strike_date",
    "value_date", "maturity_date", "payment_date", "anchor", "settlement_ccy", "frozen_schedule",
})
IDENTITY_FIELDS = frozenset({"name", "ticker", "ccy"})


def terms_from_input(payload: dict, *, allow_unresolved: bool = False) -> ProductTerms:
    """Materialize script defaults only at the explicit input boundary.

    A saved product never goes back to template defaults. Invalid calendars
    can be saved as incomplete drafts but are not eligible for pricing/RFQ.
    """
    compiled = parse_script(payload["script"])
    supplied = payload.get("user_params") or {}
    declared = {p.name for p in compiled.params}
    unknown = set(supplied) - declared
    if unknown:
        raise ValueError("Paramètres non déclarés : " + ", ".join(sorted(unknown)))
    params = tuple(ContractParameter(
        name=p.name, value=supplied.get(p.name, p.stored_val),
        is_pct=p.is_pct, kind=p.kind, description=p.desc,
    ) for p in compiled.params)
    tenor = payload.get("T")
    if tenor is None and payload.get("strike_date") and payload.get("maturity_date"):
        start = date.fromisoformat(str(payload["strike_date"]))
        end = date.fromisoformat(str(payload["maturity_date"]))
        tenor = round((end - start).days / 365.25, 6)
    terms = ProductTerms(
        script=payload["script"], parameters=params,
        underlyings=tuple(UnderlyingIdentity(**{
            k: u[k] for k in IDENTITY_FIELDS if k in u
        }) for u in payload.get("underlyings", [])),
        constats=FrozenObject(payload.get("constats") or {}), T=tenor,
        **{k: payload.get(k) or None for k in (
            "strike_date", "value_date", "maturity_date", "payment_date", "anchor",
            "settlement_ccy",
        )},
    )
    # A dated product must never acquire a new implicit origin on reload.
    if terms.strike_date is None and terms.anchor is None:
        if not allow_unresolved:
            raise ValueError("Une date de strike ou d’ancrage explicite est requise.")
        return terms.model_copy(update={"schedule_error": "Date d’ancrage à préciser."})
    try:
        compiled = resolve_analysis_constats(compiled, SimpleNamespace(**terms.pricing_fields()))
        schedule = FrozenObject(compiled.echeancier.to_dict())
        return terms.model_copy(update={"schedule": schedule,
                                        "resolved_events": FrozenObject(freeze_calendar(compiled))})
    except ValueError as exc:
        if not allow_unresolved:
            raise
        return terms.model_copy(update={"schedule_error": str(exc)})


def split_pricing_input(payload: dict) -> tuple[Product, dict]:
    product = Product(terms=terms_from_input(payload, allow_unresolved=True))
    return product, calculation_context(payload)


def calculation_context(payload: dict) -> dict:
    """Keep calculation choices and market assumptions, never contract terms."""
    context = {k: v for k, v in payload.items() if k not in TERM_FIELDS}
    context["underlyings"] = [
        {k: v for k, v in u.items() if k not in IDENTITY_FIELDS}
        for u in payload.get("underlyings", [])
    ]
    return context


def pricing_input(product: Product, context: dict) -> dict:
    """Compose explicit external assumptions with authoritative product terms.

    Context underlying arrays are ordered exactly like the contractual basket.
    Names/tickers/currencies and other contractual overrides are rejected.
    """
    forbidden = (set(context) & TERM_FIELDS) - {"underlyings"}
    if forbidden:
        raise ValueError("Le contexte tente de modifier les termes : " + ", ".join(sorted(forbidden)))
    assumptions = context.get("underlyings")
    if not isinstance(assumptions, (list, tuple)) or len(assumptions) != len(product.terms.underlyings):
        raise ValueError("Le contexte de marché doit couvrir tout le panier, dans son ordre contractuel.")
    underlyings = []
    for identity, market in zip(product.terms.underlyings, assumptions):
        if set(market) & IDENTITY_FIELDS:
            raise ValueError("L’identité des sous-jacents appartient au produit.")
        underlyings.append(UnderlyingParams(**identity.model_dump(), **market).model_dump())
    fields = product.terms.pricing_fields()
    fields["underlyings"] = underlyings
    return {**context, **fields}


def describe_product(product: Product) -> dict:
    """Return parser-owned monitor metadata and explicit interpretation limits."""
    compiled = parse_script(product.terms.script)
    return {
        "parameters": [p.model_dump(mode="json") for p in product.terms.parameters],
        "monitors": compiled.monitors or [],
        "has_stop": compiled.has_stop,
        "schedule": product.terms.schedule.to_dict() if product.terms.schedule else None,
        "limitations": ([product.terms.schedule_error] if product.terms.schedule_error else []),
    }
