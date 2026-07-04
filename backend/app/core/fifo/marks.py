"""Mark computation for open-position valuation.

Two modes:

  "shares" mode
    mark = current stock price in prod_ccy, sourced from amc_prices (parquet store
    or live yfinance fallback).  Standard for funds where executedQuantity = shares.

  "cert_units" mode
    The carnet records cert-unit quantities at cert-unit prices (≈ NAV fraction per
    underlying at execution time).  The true current value per cert-unit is:

        mark = current_stock_price × scaling_factor

    where scaling_factor k = cert_unit_price_at_T0 / stock_price_at_T0 (split-adjusted).

    When a termsheet_positions.json is available, k is derived from:
        t0_cert  = fixing_price × qty_per_cert          (from termsheet)
        t0_stock = build_marks(t0_date, auto_adjust=True) (split-adjusted, yfinance)
        k        = t0_cert / t0_stock

    This handles stock splits correctly because the yfinance store uses auto_adjust=True
    throughout, so t0_stock and current_stock are on the same (split-adjusted) basis.

    When no termsheet is available, k falls back to the earliest carnet BUY lot.
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

import pandas as pd


def get_marks_shares(
    components: list[dict],
    as_of_date: str,
    prod_ccy: str,
) -> dict[str, float]:
    """Delegate to existing amc_prices.build_marks — no duplication."""
    from ..amc_prices import build_marks
    return build_marks(components, as_of_date=as_of_date, prod_ccy=prod_ccy)


def get_marks_cert_units(
    components: list[dict],
    scaling_factors: dict[str, float],
    as_of_date: str,
    prod_ccy: str,
) -> dict[str, float]:
    """Return {isin: mark_per_cert_unit} for cert_units mode.

    mark_per_cert_unit[isin] = stock_price_current × scaling_factors[isin]

    scaling_factors must be pre-computed by the engine from the earliest lot per ISIN:
        k = avg_cost_per_cert_unit_at_T0 / stock_price_at_T0
    """
    from ..amc_prices import build_marks, get_fx_series

    # Get raw stock prices (in prod_ccy) via the existing price store
    raw_marks = build_marks(components, as_of_date=as_of_date, prod_ccy=prod_ccy)

    cert_marks: dict[str, float] = {}
    for c in components:
        isin = (c.get("isin") or "").strip()
        if not isin:
            continue
        stock_mark = raw_marks.get(isin)
        k = scaling_factors.get(isin)
        if stock_mark is None or k is None or not math.isfinite(k) or k <= 0:
            continue
        cert_marks[isin] = stock_mark * k

    return cert_marks


def compute_scaling_factors(
    open_lots_by_isin: dict[str, list],   # {isin: [Lot, ...]}
    synthetic_report: list,               # list[SyntheticInjection]
    t0_stock_prices: dict[str, float],    # {isin: stock_price_at_T0}
) -> dict[str, float]:
    """Compute per-ISIN scaling factor k = cert_unit_price_T0 / stock_price_T0.

    Uses the earliest lot (synthetic or real) as T0 reference.
    ISINs with no T0 stock price are skipped (mark will be None).
    """
    factors: dict[str, float] = {}

    # Collect earliest cert-unit price per ISIN from open lots
    all_lots: dict[str, list] = {}
    for isin, lots in open_lots_by_isin.items():
        all_lots[isin] = lots

    for isin, lots in all_lots.items():
        if not lots:
            continue
        # Use earliest lot price as the T0 cert-unit reference
        earliest = min(lots, key=lambda l: l.date)
        cert_price_t0 = earliest.price_prod   # cost per cert-unit at T0 (in prod_ccy)
        stock_price_t0 = t0_stock_prices.get(isin)
        if stock_price_t0 and stock_price_t0 > 0 and cert_price_t0 > 0:
            factors[isin] = cert_price_t0 / stock_price_t0

    return factors


def fetch_t0_stock_prices(
    isins: list[str],
    names: list[str],
    t0_date: datetime.date,
    prod_ccy: str,
) -> dict[str, float]:
    """Fetch stock prices at T0 date for scaling factor computation."""
    components = [
        {"isin": isin, "name": name, "currency": ""}
        for isin, name in zip(isins, names)
    ]
    t0_str = t0_date.isoformat()
    from ..amc_prices import build_marks
    return build_marks(components, as_of_date=t0_str, prod_ccy=prod_ccy)


def fetch_t0_prices_from_earliest_lots(
    earliest_lots: dict,    # {isin: Lot} — from ReconResult.earliest_lots
    prod_ccy: str,
) -> dict[str, float]:
    """Fetch T0 stock prices for ALL ISINs (open + closed) using earliest lot dates.

    This is the correct source for scaling factors in cert_units mode because it
    covers ISINs that have been fully closed and are no longer in open_positions.
    """
    from ..amc_prices import build_marks
    from collections import defaultdict

    by_date: dict = defaultdict(list)
    for isin, lot in earliest_lots.items():
        by_date[lot.date].append((isin, lot.name))

    t0_prices: dict[str, float] = {}
    for date, isin_name_list in by_date.items():
        components = [{"isin": isin, "name": name, "currency": ""} for isin, name in isin_name_list]
        prices = build_marks(components, as_of_date=date.isoformat(), prod_ccy=prod_ccy)
        t0_prices.update(prices)

    return t0_prices


def fetch_t0_prices_from_lots(
    open_positions: list,   # list[OpenPosition]
    prod_ccy: str,
) -> dict[str, float]:
    """Fetch the stock price at the date of the earliest lot for each ISIN.

    For cert_units mode, each ISIN has its own T0 reference date (the date of
    the first carnet lot), not a single global T0.  This gives the most accurate
    per-ISIN scaling factor.
    """
    from ..amc_prices import build_marks

    # Group: for each ISIN, find the date of its earliest lot
    isin_t0: dict[str, tuple[str, datetime.date]] = {}  # isin → (name, date)
    for pos in open_positions:
        if not pos.lots:
            continue
        earliest = min(pos.lots, key=lambda l: l.date)
        isin_t0[pos.isin] = (pos.name, earliest.date)

    if not isin_t0:
        return {}

    # Fetch all at once, one call per unique date
    from collections import defaultdict
    by_date: dict[datetime.date, list[tuple[str, str]]] = defaultdict(list)
    for isin, (name, date) in isin_t0.items():
        by_date[date].append((isin, name))

    t0_prices: dict[str, float] = {}
    for date, isin_name_list in by_date.items():
        components = [{"isin": isin, "name": name, "currency": ""} for isin, name in isin_name_list]
        prices = build_marks(components, as_of_date=date.isoformat(), prod_ccy=prod_ccy)
        t0_prices.update(prices)

    return t0_prices


def compute_scaling_factors(
    earliest_lots: dict,            # {isin: Lot} — ReconResult.earliest_lots
    t0_stock_prices: dict[str, float],  # {isin: stock_price at T0 in prod_ccy}
) -> dict[str, float]:
    """Compute k = cert_unit_cost_T0 / stock_price_T0 per ISIN.

    Uses earliest_lots (covers ALL ISINs including closed positions) so that
    T0 prices for synthetic BUYs can be computed for round trips too.
    """
    factors: dict[str, float] = {}
    for isin, lot in earliest_lots.items():
        cert_price_t0 = lot.price_prod
        stock_price_t0 = t0_stock_prices.get(isin)
        if stock_price_t0 and stock_price_t0 > 0 and cert_price_t0 > 0:
            factors[isin] = cert_price_t0 / stock_price_t0
    return factors


def compute_scaling_factors_from_positions(
    open_positions: list,           # list[OpenPosition] — kept for backward compat
    t0_stock_prices: dict[str, float],
) -> dict[str, float]:
    factors: dict[str, float] = {}
    for pos in open_positions:
        if not pos.lots:
            continue
        earliest = min(pos.lots, key=lambda l: l.date)
        cert_price_t0 = earliest.price_prod
        stock_price_t0 = t0_stock_prices.get(pos.isin)
        if stock_price_t0 and stock_price_t0 > 0 and cert_price_t0 > 0:
            factors[pos.isin] = cert_price_t0 / stock_price_t0
    return factors


def build_scaling_factors_from_termsheet(
    termsheet: list[dict],   # [{isin, name, qty_per_cert, fixing_price, ccy, weight_pct}]
    earliest_lots: dict,     # {isin: Lot} — ReconResult.earliest_lots (fallback)
    t0_date: datetime.date,  # inception date (first order date or explicit fixing date)
    prod_ccy: str,
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute (scaling_factors, t0_cert_prices) using termsheet as source of truth.

    For termsheet ISINs:
        t0_cert  = fixing_price                        [price per ONE accounting unit — same
                                                          per-unit convention as Order/Lot.price_prod
                                                          everywhere else in the FIFO engine]
        t0_stock = build_marks(t0_date, auto_adj=True) [split-adjusted stock price]
        k        = t0_cert / t0_stock                  [handles splits correctly]
        → t0_cert_prices[isin] = t0_cert  (used as price for synthetic T0 BUYs)

    For non-termsheet ISINs (positions added after inception):
        k        = earliest_lot.price_prod / t0_stock_at_lot_date  [carnet fallback]
        → t0_cert_prices[isin] = earliest_lot.price_prod

    Returns
    -------
    scaling_factors : {isin: k}
    t0_cert_prices  : {isin: cert-unit price at T0}  — injected as synthetic BUY price
    """
    from ..amc_prices import build_marks

    ts_map = {e["isin"]: e for e in termsheet}
    ts_isins = list(ts_map.keys())

    scaling_factors: dict[str, float] = {}
    t0_cert_prices: dict[str, float] = {}

    # ── Termsheet ISINs ───────────────────────────────────────────────────
    if ts_isins:
        components = [
            {"isin": isin, "name": ts_map[isin]["name"], "currency": ts_map[isin].get("ccy", "")}
            for isin in ts_isins
        ]
        t0_stock_prices_ts = build_marks(components, as_of_date=t0_date.isoformat(), prod_ccy=prod_ccy)

        for isin in ts_isins:
            e = ts_map[isin]
            t0_cert = float(e.get("fixing_price") or 0)
            t0_stock = t0_stock_prices_ts.get(isin)
            if t0_stock and t0_stock > 0 and t0_cert > 0:
                scaling_factors[isin] = t0_cert / t0_stock
                t0_cert_prices[isin] = t0_cert

    # ── Non-termsheet ISINs (fallback: earliest carnet BUY) ───────────────
    fallback_lots = {isin: lot for isin, lot in earliest_lots.items() if isin not in ts_map}
    if fallback_lots:
        fallback_t0_stock = fetch_t0_prices_from_earliest_lots(fallback_lots, prod_ccy)
        for isin, lot in fallback_lots.items():
            stock_t0 = fallback_t0_stock.get(isin)
            cert_t0 = lot.price_prod
            if stock_t0 and stock_t0 > 0 and cert_t0 > 0:
                scaling_factors[isin] = cert_t0 / stock_t0
                t0_cert_prices[isin] = cert_t0

    return scaling_factors, t0_cert_prices
