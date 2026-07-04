"""NAV timeseries utilities for FIFO reconstruction.

Reads the fund NAV CSV (Date, Price, Outstanding quantity) to determine:
  - fixing_date    : first NAV date = fund inception / fixing date
  - n_certs        : number of certificates outstanding at inception
  - nav_initial    : NAV per certificate at inception (usually 100.00)

These are used by build_initial_orders() to inject the fund's starting basket
as real T0 BUY orders, eliminating the need for heuristic synthetic injections
on termsheet ISINs.
"""
from __future__ import annotations

import csv
import datetime
import glob
import os
from typing import Optional


def load_nav_csv(path: str) -> list[tuple[datetime.date, float, Optional[int]]]:
    """Parse NAV timeseries CSV.

    Expected columns: Date (DD.MM.YYYY), Price (float), Outstanding quantity (int, optional)
    Returns list of (date, nav_per_cert, outstanding_qty) sorted ascending by date.
    """
    rows: list[tuple[datetime.date, float, Optional[int]]] = []

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = (row.get("Date") or "").strip()
            price_str = (row.get("Price") or "").strip()
            qty_str = (row.get("Outstanding quantity") or "").strip()

            if not date_str or not price_str:
                continue
            try:
                date = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
                price = float(price_str)
            except ValueError:
                continue

            qty: Optional[int] = None
            if qty_str:
                try:
                    qty = int(float(qty_str))
                except ValueError:
                    pass

            rows.append((date, price, qty))

    rows.sort(key=lambda r: r[0])
    return rows


def get_fixing_info(nav_rows: list[tuple]) -> tuple[datetime.date, int, float]:
    """Return (fixing_date, n_certs_initial, nav_initial) from NAV rows.

    fixing_date  = date of first row
    nav_initial  = NAV per cert on fixing_date
    n_certs      = Outstanding quantity on fixing_date (or nearest later row that has it)
    """
    if not nav_rows:
        raise ValueError("NAV CSV is empty")

    fixing_date, nav_initial, n_certs_first = nav_rows[0]

    if n_certs_first is not None:
        return fixing_date, n_certs_first, nav_initial

    # Outstanding qty sometimes appears only on subscription dates, not daily
    for _date, _price, qty in nav_rows:
        if qty is not None:
            return fixing_date, qty, nav_initial

    raise ValueError("Outstanding quantity not found in NAV CSV")


def detect_nav_csv(folder: str) -> Optional[str]:
    """Find the NAV timeseries CSV in folder (matches *timeseries*.csv)."""
    candidates = sorted(glob.glob(os.path.join(folder, "*timeseries*.csv")))
    return candidates[0] if candidates else None


def build_initial_orders(
    termsheet: list[dict],
    n_certs: int,
    nav_initial: float,
    fixing_date: datetime.date,
    prod_ccy: str,
    isin_aliases: Optional[dict[str, str]] = None,
    qty_mode: str = "shares",
) -> list:
    """Create T0 BUY Order objects for each termsheet ISIN representing the initial basket.

    qty_mode="cert_units": quantities are certificate accounting units, not real shares.
    Accounting units are fixed at issuance and — unlike real shares — never split, so no
    yfinance split-factor detection is needed or wanted here:

        initial_qty = n_certs × qty_per_cert                         (no split_factor)
        T0_price    = fixing_price (termsheet), per accounting unit  (no yfinance price)
                      falls back to weight/NAV-implied price if fixing_price is unset

    qty_mode="shares" (default), for each ISIN:
      expected_price_usd = (weight_pct / 100 × nav_initial) / qty_per_cert
          → the per-share USD value at inception, derived purely from the termsheet
          → automatically accounts for FX (Swissquote CHF etc.)

      yfinance_price_usd = build_marks([isin], fixing_date, auto_adjust=True)
          → split-adjusted price; for Nvidia 10:1 split (June 10, 2024) this
            returns the post-split equivalent price on the fixing date

      split_factor = round(expected_price_usd / yfinance_price_usd)
          → ≈ 10 for Nvidia, ≈ 1 for all others with no corporate action

      initial_qty  = n_certs × qty_per_cert × split_factor   (post-split shares)
      T0_cost      = yfinance_price_usd                       (post-split, USD)

    Note: qty_per_cert cancels out of initial_qty algebraically —
    initial_qty = n_certs × (weight_pct/100 × nav_initial) / yfinance_price_usd.
    So qty_mode="shares" already produces the correct real share count regardless
    of whether the term sheet's qty_per_cert was itself expressed in real shares or
    in accounting units ("unités de compte") — confirmed on CH1352587724 by
    cross-checking against the issuer's own published factsheet. qty_mode="cert_units"
    is only needed when the carnet *itself* records accounting-unit trades (not just
    the term sheet) — not observed in any fund studied so far.

    The returned orders are prepended to the carnet order list so the FIFO engine
    sees them as regular BUY lots from the fixing date.

    isin_aliases: optional {termsheet_isin: carnet_isin} map for ISINs that changed
    (corporate actions, reissuance) between fixing_date and carnet recording.
    The yfinance lookup uses the termsheet ISIN (original), but the Order uses
    the carnet ISIN so it matches the carnet's SELL orders in the FIFO engine.
    """
    from .schema import Order

    if not termsheet:
        return []

    isin_aliases = isin_aliases or {}

    if qty_mode == "cert_units":
        orders: list[Order] = []
        for e in termsheet:
            ts_isin = e["isin"]
            fifo_isin = isin_aliases.get(ts_isin, ts_isin)
            qty_per_cert: float = e["qty_per_cert"]
            weight_pct: float = e["weight_pct"]
            if qty_per_cert <= 0:
                continue

            fixing_price = float(e.get("fixing_price") or 0)
            unit_price = fixing_price if fixing_price > 0 else (weight_pct / 100.0 * nav_initial) / qty_per_cert
            if unit_price <= 0:
                continue

            orders.append(Order(
                id=f"T0_INIT_{fifo_isin}",
                date=fixing_date,
                isin=fifo_isin,
                name=e["name"],
                qty=n_certs * qty_per_cert,
                price_local=unit_price,
                price_ccy=prod_ccy,
                fx=1.0,
                price_prod=unit_price,
            ))
        orders.sort(key=lambda o: o.isin)
        return orders

    from ..amc_prices import build_marks

    # Use FIFO ISIN (= carnet ISIN if aliased) for the yfinance price lookup.
    # For ISINs that changed after a corporate action (e.g. Swissquote 10:1 split),
    # the termsheet ISIN may map to a stale or wrong price in yfinance, while the
    # carnet ISIN correctly reflects the current trading price.
    components = [
        {
            "isin": isin_aliases.get(e["isin"], e["isin"]),   # fifo_isin for lookup
            "name": e["name"],
            "currency": e.get("ccy", ""),
        }
        for e in termsheet
    ]
    yf_prices = build_marks(components, as_of_date=fixing_date.isoformat(), prod_ccy=prod_ccy)

    orders: list[Order] = []
    for e in termsheet:
        ts_isin = e["isin"]
        fifo_isin = isin_aliases.get(ts_isin, ts_isin)   # carnet ISIN (may equal ts_isin)
        name = e["name"]
        qty_per_cert: float = e["qty_per_cert"]
        weight_pct: float = e["weight_pct"]

        if qty_per_cert <= 0:
            continue

        # USD per share at inception implied by the termsheet
        expected_price_usd = (weight_pct / 100.0 * nav_initial) / qty_per_cert

        yf_price = yf_prices.get(fifo_isin)
        if not yf_price or yf_price <= 0:
            # yfinance unavailable (e.g. delisted/IL ISIN): trust termsheet-implied price,
            # assume no post-fixing split (split_factor=1).
            initial_qty = n_certs * qty_per_cert
            orders.append(Order(
                id=f"T0_INIT_{fifo_isin}",
                date=fixing_date,
                isin=fifo_isin,
                name=name,
                qty=initial_qty,
                price_local=expected_price_usd,
                price_ccy=prod_ccy,
                fx=1.0,
                price_prod=expected_price_usd,
            ))
            continue

        # Split detection: integer ratio expected_price / yfinance_adjusted
        # yfinance uses auto_adjust=True so historical prices are split-adjusted backward.
        # split_factor ≈ 10 for Nvidia (10:1 split after fixing), 1 for others.
        raw_factor = expected_price_usd / yf_price
        nearest_int = round(raw_factor)
        # Accept integer if within 15% of raw ratio; otherwise keep float
        split_factor = float(nearest_int) if nearest_int >= 1 and abs(raw_factor - nearest_int) / raw_factor < 0.15 else raw_factor

        if split_factor <= 0:
            continue

        initial_qty = n_certs * qty_per_cert * split_factor

        orders.append(Order(
            id=f"T0_INIT_{fifo_isin}",
            date=fixing_date,
            isin=fifo_isin,
            name=name,
            qty=initial_qty,        # positive = BUY
            price_local=yf_price,
            price_ccy=prod_ccy,
            fx=1.0,
            price_prod=yf_price,
        ))

    # Sort by ISIN for determinism
    orders.sort(key=lambda o: o.isin)
    return orders
