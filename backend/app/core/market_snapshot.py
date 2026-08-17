"""Readers for the market snapshot frozen on a booked deal.

A deal carries its pricing assumptions as a JSON blob (``Deal.market_snapshot_json``),
written once at booking and never re-keyed. Every consumer — residual MtM, Greeks,
shocks, P&L explain, lifecycle replay, reinvestment — reads it back, and they must
all read it the same way: two consumers disagreeing on what a missing or zero field
means is how the same deal ends up with two different values.

The rate is the field that made this module necessary. It used to be read as
``(market.get("r", 3.0) or 3.0) / 100.0`` at five call sites, one of which is the
*official* lifecycle replay. In Python ``0 or 3.0`` is ``3.0``: a deal deliberately
booked at a zero rate was discounted at 3% instead, silently, everywhere. The
``or`` was redundant — ``get(key, default)`` already covered the absent key — and it
swallowed a perfectly legitimate value along the way.
"""
from __future__ import annotations

import os

# Only used when a snapshot carries no rate at all, which no current booking path
# produces: both the Pricer (DealTab.vue) and the UAT generator always write `r`.
# It exists for rows predating that field, so that an old deal stays valuable
# rather than becoming unreadable. Overridable rather than hard-coded, same
# convention as STRUCTURA_RFQ_MODEL_PRICE_MAX_AGE_MINUTES in core/rfq_controls.py.
DEFAULT_RATE_PCT = float(os.getenv("STRUCTURA_DEFAULT_RATE_PCT", "3.0"))


def snapshot_rate_is_default(market: dict | None) -> bool:
    """True when the rate below is our fallback rather than the deal's own.

    Callers that publish the market they priced with (see ``market_used`` in
    api/deals.py) should surface this: a substituted rate must never be
    indistinguishable from a booked one.
    """
    return (market or {}).get("r") is None


def snapshot_rate(market: dict | None) -> float:
    """Risk-free rate of a booked snapshot, as a fraction (0.03 = 3%).

    Zero and negative rates are values, not absences: only a missing key falls
    back on ``DEFAULT_RATE_PCT``.
    """
    raw = (market or {}).get("r")
    if raw is None:
        return DEFAULT_RATE_PCT / 100.0
    try:
        return float(raw) / 100.0
    except (TypeError, ValueError):
        raise ValueError(
            f"Taux du snapshot de marché illisible : {raw!r}. Un taux se stocke en "
            f"pourcentage numérique (3.0 pour 3 %)."
        )
