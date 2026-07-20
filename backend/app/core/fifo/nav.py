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

    split_factors, yf_prices = _compute_split_factors(
        termsheet, fixing_date, nav_initial, prod_ccy, isin_aliases)

    orders: list[Order] = []
    for e in termsheet:
        ts_isin = e["isin"]
        fifo_isin = isin_aliases.get(ts_isin, ts_isin)   # carnet ISIN (may equal ts_isin)
        name = e["name"]
        qty_per_cert: float = e["qty_per_cert"]
        weight_pct: float = e["weight_pct"]

        if qty_per_cert <= 0:
            continue

        split_factor = split_factors.get(fifo_isin)
        if split_factor is None:
            continue
        yf_price = yf_prices.get(fifo_isin)

        if yf_price is None:
            # yfinance unavailable (e.g. delisted/IL ISIN): trust termsheet-implied price.
            expected_price_usd = (weight_pct / 100.0 * nav_initial) / qty_per_cert
            orders.append(Order(
                id=f"T0_INIT_{fifo_isin}",
                date=fixing_date,
                isin=fifo_isin,
                name=name,
                qty=n_certs * qty_per_cert,
                price_local=expected_price_usd,
                price_ccy=prod_ccy,
                fx=1.0,
                price_prod=expected_price_usd,
            ))
            continue

        orders.append(Order(
            id=f"T0_INIT_{fifo_isin}",
            date=fixing_date,
            isin=fifo_isin,
            name=name,
            qty=n_certs * qty_per_cert * split_factor,        # positive = BUY
            price_local=yf_price,
            price_ccy=prod_ccy,
            fx=1.0,
            price_prod=yf_price,
        ))

    # Sort by ISIN for determinism
    orders.sort(key=lambda o: o.isin)
    return orders


def _compute_split_factors(
    termsheet: list[dict],
    fixing_date: datetime.date,
    nav_initial: float,
    prod_ccy: str,
    isin_aliases: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Per-ISIN split_factor (termsheet-unit → real post-split shares) and the
    yfinance fixing-date price used to derive it. Shared by build_initial_orders
    (the one-off T0 lump sum) and build_subscription_topups (the same formula
    re-applied incrementally whenever outstanding certificates grow) so both
    stay on the exact same real-share basis.

    Returns ({fifo_isin: split_factor}, {fifo_isin: yfinance_price_at_fixing}).
    An ISIN absent from the price dict means yfinance was unavailable for it
    (caller falls back to the termsheet-implied price, split_factor=1 assumed).
    """
    from ..amc_prices import build_marks

    # Use FIFO ISIN (= carnet ISIN if aliased) for the yfinance price lookup.
    # For ISINs that changed after a corporate action (e.g. Swissquote 10:1 split),
    # the termsheet ISIN may map to a stale or wrong price in yfinance, while the
    # carnet ISIN correctly reflects the current trading price.
    components = [
        {
            "isin": isin_aliases.get(e["isin"], e["isin"]),
            "name": e["name"],
            "currency": e.get("ccy", ""),
        }
        for e in termsheet
    ]
    yf_prices = build_marks(components, as_of_date=fixing_date.isoformat(), prod_ccy=prod_ccy)

    split_factors: dict[str, float] = {}
    for e in termsheet:
        ts_isin = e["isin"]
        fifo_isin = isin_aliases.get(ts_isin, ts_isin)
        qty_per_cert: float = e["qty_per_cert"]
        weight_pct: float = e["weight_pct"]
        if qty_per_cert <= 0:
            continue

        yf_price = yf_prices.get(fifo_isin)
        if not yf_price or yf_price <= 0:
            split_factors[fifo_isin] = 1.0
            yf_prices.pop(fifo_isin, None)  # signal "unavailable" to callers
            continue

        # Split detection: integer ratio expected_price / yfinance_adjusted.
        # yfinance uses auto_adjust=True so historical prices are split-adjusted
        # backward. split_factor ≈ 10 for Nvidia (10:1 split after fixing), 1 for
        # others.
        expected_price_usd = (weight_pct / 100.0 * nav_initial) / qty_per_cert
        raw_factor = expected_price_usd / yf_price
        nearest_int = round(raw_factor)
        split_factor = (float(nearest_int)
                        if nearest_int >= 1 and abs(raw_factor - nearest_int) / raw_factor < 0.15
                        else raw_factor)
        if split_factor > 0:
            split_factors[fifo_isin] = split_factor

    return split_factors, yf_prices


def build_growth_topups(
    orders: list,
    nav_rows: list[tuple],
    fixing_date: datetime.date,
    n_certs_fixing: int,
    prod_ccy: str,
    seed_deficits: Optional[dict[str, float]] = None,
) -> list:
    """Extra BUY orders for certificate growth after the fixing date, applied
    to EVERY currently open position — not just the original termsheet names.

    An AMC's outstanding certificates grow through creation: new subscriptions
    are backed by buying a pro-rata slice of whatever the fund holds AT THAT
    MOMENT, not a replay of the day-1 termsheet. So when outstanding certs grow
    from n to n' on some date, every position open on that date should grow
    by the same ratio (n'/n) — whether that position originated from the T0
    basket or was built up later through active management. Confirmed on
    CH1352587724: Cleanspark (never in the termsheet) accumulated to 14'223
    shares by Dec 2024, then a single sell of 17'568 on 2025-02-19 pushed it
    to -3'345 — a deficit of the same order as 14'223 × (34'500/26'932 - 1)
    ≈ 3'980, the fund's cert growth ratio over that period, not a data gap.

    Walks `orders` (T0 basket + real carnet, already split-corrected,
    chronological) alongside NAV growth events. At each event, every ISIN
    with a positive running net quantity as of that date gets a top-up sized
    `open_qty × (ratio - 1)`, priced at that date's market price. The top-up
    itself compounds into the running quantity, so a later growth event scales
    the already-topped-up size. Redemptions (certs decreasing) are not
    modelled — the manager's real sell orders in the carnet already cover
    raising that cash. ISINs that are flat or short (net qty <= 0) at an event
    date are left alone — a name the manager has already exited is not
    revived just because AUM grew elsewhere.

    seed_deficits: {isin: qty}, added to that isin's running quantity at its
    own first order — before it can be excluded as "flat or short". Without
    this, a name whose real carnet trading happens to dip negative BEFORE most
    of the fund's growth occurred (e.g. Amazon on CH1352587724, negative from
    Nov 2024 while the bulk of subscription growth landed afterwards) gets
    silently skipped for every later growth event, even though it demonstrably
    needed one — the deficit just surfaces later as a big single sell instead
    of being distributed proportionally across growth events. Callers should
    pass the total excess_qty a synthetic-injection pre-pass (T0 basket + real
    carnet, no top-ups) found for each isin: that is the size of the "hidden"
    true position this isin's own first order failed to fully capture.
    """
    import collections
    from .schema import Order
    from ..amc_prices import build_marks

    growth_events: list[tuple[datetime.date, float]] = []
    prev_certs = n_certs_fixing
    for date, _price, certs in nav_rows:
        if certs is None or date <= fixing_date:
            continue
        if certs > prev_certs:
            growth_events.append((date, certs / prev_certs))
        prev_certs = certs
    if not growth_events:
        return []

    seed_deficits = seed_deficits or {}
    seeded: set[str] = set()
    ordered = sorted(orders, key=lambda o: o.date)
    net_qty: dict[str, float] = collections.defaultdict(float)
    isin_names: dict[str, str] = {}
    topups: list = []

    event_idx = 0
    n_events = len(growth_events)

    def apply_events_up_to(cutoff: Optional[datetime.date]) -> None:
        nonlocal event_idx
        while event_idx < n_events and (cutoff is None or growth_events[event_idx][0] <= cutoff):
            date, ratio = growth_events[event_idx]
            event_idx += 1
            targets = [isin for isin, q in net_qty.items() if q > 1e-9]
            if not targets:
                continue
            components = [
                {"isin": isin, "name": isin_names[isin], "currency": ""}
                for isin in targets
            ]
            prices = build_marks(components, as_of_date=date.isoformat(), prod_ccy=prod_ccy)
            for isin in targets:
                price = prices.get(isin)
                if not price or price <= 0:
                    continue
                qty = net_qty[isin] * (ratio - 1)
                if qty <= 0:
                    continue
                topups.append(Order(
                    id=f"GROWTH_TOPUP_{isin}_{date.isoformat()}",
                    date=date,
                    isin=isin,
                    name=isin_names[isin],
                    qty=qty,
                    price_local=price,
                    price_ccy=prod_ccy,
                    fx=1.0,
                    price_prod=price,
                ))
                net_qty[isin] += qty

    for o in ordered:
        apply_events_up_to(o.date)
        if o.isin not in seeded:
            seeded.add(o.isin)
            net_qty[o.isin] += seed_deficits.get(o.isin, 0.0)
        net_qty[o.isin] += o.qty
        isin_names[o.isin] = o.name

    apply_events_up_to(None)  # any growth events after the last order
    return topups
