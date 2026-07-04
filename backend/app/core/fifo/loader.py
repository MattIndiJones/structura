"""Load UTI/AMC order carnet JSON files into normalized Order objects.

Supported format (from UTI platform):
  { "data": { "orders": { "items": [ <order>, ... ] } } }

Each order item:
  {
    "id": "...",
    "state": "Done",
    "creationDateTime": "2025-10-14T14:01:54+00:00",
    "orderedQuantity": "-4",
    "executedQuantity": "-4",
    "executionPrice": { "amount": "1004.69", "currency": "USD" },
    "usedFxRate": "1",
    "underlying": { "name": "KLA Corporation", "isin": "US4824801009", "currency": "USD" }
  }

Sign convention: negative executedQuantity = SELL, positive = BUY.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Union

from .schema import Order


def _f(v) -> float | None:
    """Safe float parse."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(raw[:26], fmt[:len(raw[:26])])
            return dt.date()
        except ValueError:
            pass
    # fallback: try first 10 chars as date
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _order_from_item(item: dict) -> Order | None:
    """Parse one order dict into an Order.  Returns None if data is incomplete."""
    state = (item.get("state") or "").strip()
    if state and state.lower() not in ("done", "executed", "filled", "completed"):
        return None  # skip pending / cancelled

    qty = _f(item.get("executedQuantity")) or _f(item.get("orderedQuantity"))
    if qty is None or qty == 0:
        return None

    ep = item.get("executionPrice") or {}
    price_local = _f(ep.get("amount"))
    if price_local is None or price_local <= 0:
        return None

    price_ccy = (ep.get("currency") or "").upper().strip()
    fx = _f(item.get("usedFxRate")) or 1.0
    price_prod = price_local * fx

    underlying = item.get("underlying") or {}
    isin = (underlying.get("isin") or item.get("isin") or "").strip()
    name = (underlying.get("name") or item.get("name") or isin).strip()

    # Date: prefer tradeDate, fall back to creationDateTime
    raw_date = item.get("tradeDate") or item.get("creationDateTime") or item.get("settlementDate")
    date = _parse_date(raw_date)
    if date is None:
        return None

    order_id = str(item.get("id") or f"{isin}_{date}_{qty}")

    return Order(
        id=order_id,
        date=date,
        isin=isin,
        name=name,
        qty=qty,
        price_local=price_local,
        price_ccy=price_ccy,
        fx=fx,
        price_prod=price_prod,
    )


def load_orders(paths: list[Union[str, Path]]) -> list[Order]:
    """Load one or more UTI JSON carnet files and return a sorted list of Orders.

    Duplicate order IDs are deduplicated (same order appearing in two files).
    """
    seen_ids: set[str] = set()
    orders: list[Order] = []

    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue

        items = (((d.get("data") or {}).get("orders") or {}).get("items")) or []
        for item in items:
            if not isinstance(item, dict):
                continue
            order = _order_from_item(item)
            if order is None:
                continue
            if order.id in seen_ids:
                continue
            seen_ids.add(order.id)
            orders.append(order)

    orders.sort(key=lambda o: o.date)
    return orders
