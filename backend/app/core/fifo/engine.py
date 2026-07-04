"""FIFO reconstruction engine.

Pure logic — no I/O, no Yahoo Finance calls.  Marks and T0 prices are injected
by the caller (see reconstruct() signature).

Modes
-----
qty_mode="shares"
    Quantities are real share counts.  Mark = current stock price × FX.

qty_mode="cert_units"
    Quantities are cert-unit counts.  The cert-unit price at each trade is in
    price_prod (already prod-ccy).  Mark = stock_price_current × scaling_factor,
    where scaling_factor is derived from the earliest lot per ISIN.

recon_mode="strict"
    Excess sells (sell before any matching buy) are left as negative open positions.
    Signals a data quality issue — do not inject synthetic lots.

recon_mode="t0_synthetic"
    Excess sells trigger a synthetic BUY at t0_date with the T0 price sourced from
    t0_prices_prod {isin: price_in_prod_ccy}.
"""
from __future__ import annotations

import collections
import datetime
import math
from typing import Optional

from .schema import (
    Lot, OpenPosition, Order, ReconResult, RoundTrip, SyntheticInjection,
)


def _weighted_avg(lots: list[Lot]) -> float:
    total_qty = sum(l.qty for l in lots)
    if total_qty == 0:
        return 0.0
    return sum(l.qty * l.price_prod for l in lots) / total_qty


def reconstruct(
    orders: list[Order],
    marks: dict[str, float],            # {isin: mark_in_prod_ccy}
    as_of: datetime.date,
    prod_ccy: str,
    qty_mode: str = "shares",           # "shares" | "cert_units"
    recon_mode: str = "t0_synthetic",   # "strict" | "t0_synthetic"
    t0_date: Optional[datetime.date] = None,
    t0_prices_prod: Optional[dict[str, float]] = None,  # {isin: price} for synthetic BUYs
) -> ReconResult:
    """Run FIFO matching on a list of Orders and return a ReconResult.

    Parameters
    ----------
    orders:
        List of Order objects, pre-sorted by date (loader guarantees this).
    marks:
        Current mark per ISIN in prod_ccy.  For cert_units mode, pass
        marks computed by marks.get_marks_cert_units().
    as_of:
        Valuation date for unrealised P&L.
    prod_ccy:
        Product / fund currency (USD, CHF, EUR …).
    qty_mode:
        "shares" or "cert_units".
    recon_mode:
        "strict" — excess sells are not covered (open qty can go negative).
        "t0_synthetic" — excess sells trigger a synthetic T0 BUY.
    t0_date:
        Inception date for synthetic BUYs.  Required when recon_mode="t0_synthetic".
    t0_prices_prod:
        Pre-fetched T0 prices per ISIN in prod_ccy.  Required for t0_synthetic.
    """
    t0_prices_prod = t0_prices_prod or {}

    # ── Per-ISIN state ─────────────────────────────────────────────────
    lot_queues: dict[str, collections.deque[Lot]] = collections.defaultdict(collections.deque)
    round_trips: list[RoundTrip] = []
    synthetic_report: list[SyntheticInjection] = []
    # Earliest lot seen per ISIN (for scaling factor computation on closed positions)
    earliest_lots: dict[str, Lot] = {}

    # Group orders by ISIN, keep date sort
    by_isin: dict[str, list[Order]] = collections.defaultdict(list)
    for o in orders:
        by_isin[o.isin].append(o)

    for isin, isin_orders in by_isin.items():
        name = isin_orders[0].name
        queue: collections.deque[Lot] = lot_queues[isin]

        for order in isin_orders:
            if order.qty > 0:
                # ── BUY ────────────────────────────────────────────────
                lot = Lot(
                    order_id=order.id,
                    date=order.date,
                    isin=isin,
                    name=order.name,
                    qty=order.qty,
                    price_prod=order.price_prod,
                    source="carnet",
                    price_local=getattr(order, "price_local", order.price_prod),
                    fx=getattr(order, "fx", 1.0),
                    ccy=getattr(order, "price_ccy", ""),
                )
                queue.append(lot)
                if isin not in earliest_lots:
                    earliest_lots[isin] = lot

            elif order.qty < 0:
                # ── SELL ───────────────────────────────────────────────
                sell_qty = abs(order.qty)
                sell_price = order.price_prod
                sell_price_local = getattr(order, "price_local", order.price_prod)
                sell_fx = getattr(order, "fx", 1.0)
                sell_ccy = getattr(order, "price_ccy", "")

                # Check excess before consuming
                available = sum(l.qty for l in queue)
                if available < sell_qty and recon_mode == "t0_synthetic":
                    excess = sell_qty - available
                    _inject_synthetic(
                        isin=isin,
                        name=name,
                        excess_qty=excess,
                        t0_date=t0_date or order.date,
                        t0_prices_prod=t0_prices_prod,
                        queue=queue,
                        synthetic_report=synthetic_report,
                        prod_ccy=prod_ccy,
                    )

                # Consume lots (FIFO)
                remaining = sell_qty
                while remaining > 0 and queue:
                    lot = queue[0]
                    matched = min(lot.qty, remaining)
                    round_trips.append(RoundTrip(
                        isin=isin,
                        name=name,
                        buy_date=lot.date,
                        sell_date=order.date,
                        qty=matched,
                        buy_price_prod=lot.price_prod,
                        sell_price_prod=sell_price,
                        pnl_prod=matched * (sell_price - lot.price_prod),
                        buy_source=lot.source,
                        buy_price_local=lot.price_local,
                        buy_fx=lot.fx,
                        sell_price_local=sell_price_local,
                        sell_fx=sell_fx,
                        ccy=lot.ccy,
                    ))
                    lot.qty -= matched
                    remaining -= matched
                    if lot.qty == 0:
                        queue.popleft()

                if remaining > 0 and recon_mode == "strict":
                    # Log unmatched sell as negative open lot (data quality issue)
                    queue.appendleft(Lot(
                        order_id=order.id,
                        date=order.date,
                        isin=isin,
                        name=name,
                        qty=-remaining,
                        price_prod=sell_price,
                        source="carnet",
                    ))

    # ── Build open positions ────────────────────────────────────────────
    open_positions: list[OpenPosition] = []
    for isin, queue in lot_queues.items():
        open_lots = [l for l in queue if l.qty != 0]
        if not open_lots:
            continue

        open_qty = sum(l.qty for l in open_lots)
        cost_prod = sum(l.qty * l.price_prod for l in open_lots)
        avg_cost = cost_prod / open_qty if open_qty else 0.0

        mark = marks.get(isin)
        if mark is not None and math.isfinite(mark) and mark > 0:
            unreal = open_qty * mark - cost_prod
        else:
            unreal = None

        open_positions.append(OpenPosition(
            isin=isin,
            name=open_lots[0].name,
            open_qty=open_qty,
            avg_cost_prod=avg_cost,
            cost_prod=cost_prod,
            mark_prod=mark,
            unreal_pnl_prod=unreal,
            lots=open_lots,
            ccy=open_lots[0].ccy if open_lots else "",
        ))

    # ── Totals ─────────────────────────────────────────────────────────
    total_realized = sum(rt.pnl_prod for rt in round_trips)
    latent_values = [p.unreal_pnl_prod for p in open_positions if p.unreal_pnl_prod is not None]
    total_latent = sum(latent_values) if latent_values else None
    total_pnl = (total_realized + total_latent) if total_latent is not None else None

    return ReconResult(
        open_positions=open_positions,
        round_trips=round_trips,
        synthetic_report=synthetic_report,
        earliest_lots=earliest_lots,
        qty_mode=qty_mode,
        recon_mode=recon_mode,
        prod_ccy=prod_ccy,
        as_of=as_of,
        total_realized=total_realized,
        total_latent=total_latent,
        total_pnl=total_pnl,
    )


def _inject_synthetic(
    isin: str,
    name: str,
    excess_qty: float,
    t0_date: datetime.date,
    t0_prices_prod: dict[str, float],
    queue: collections.deque[Lot],
    synthetic_report: list[SyntheticInjection],
    prod_ccy: str,
) -> None:
    """Inject a synthetic T0 BUY lot for an excess SELL, and record it."""
    price_prod = t0_prices_prod.get(isin)
    source = "unavailable"
    injected = False

    if price_prod is not None and price_prod > 0:
        source = "t0_price"
        injected = True
        queue.appendleft(Lot(
            order_id=f"synthetic_{isin}_{t0_date}",
            date=t0_date,
            isin=isin,
            name=name,
            qty=excess_qty,
            price_prod=price_prod,
            source="synthetic_t0",
            price_local=price_prod,  # synthetic is already in prod_ccy
            fx=1.0,
            ccy=prod_ccy,
        ))

    synthetic_report.append(SyntheticInjection(
        isin=isin,
        name=name,
        excess_qty=excess_qty,
        t0_date=t0_date,
        price_prod=price_prod or 0.0,
        price_local=None,
        price_ccy=prod_ccy,
        fx=1.0,
        source=source,
        injected=injected,
    ))
