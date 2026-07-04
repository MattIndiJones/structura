"""Adapter: converts fifo.ReconResult → legacy dict format expected by amc_blocks.

The FIFO module is intentionally lean (no AMC-specific concepts). This adapter
adds the fields that Block B/C/D need without polluting the FIFO module:

  - FX decomposition (price_pnl / fx_pnl) from raw price_local + fx fields
  - exit_quarter, holding_days, ret_pct  (derived from dates)
  - ccy, value_prod, unreal_ret_pct      (trivially computable)
  - first_entry_date, last_entry_date, n_buys  (from OpenPosition.lots)
  - flips (direction changes per ISIN, computed from carnet orders)
  - synthetic_report converted to list[dict]
  - warnings synthesised from synthetic_report
"""
from __future__ import annotations

import datetime
import math
from types import SimpleNamespace
from typing import Optional

from .fifo.schema import ReconResult


def _quarter(d: datetime.date) -> Optional[str]:
    if d is None:
        return None
    return f"{d.year}-T{(d.month - 1) // 3 + 1}"


def _compute_flips(carnet_orders: list) -> dict[str, int]:
    """Count direction changes (BUY→SELL or SELL→BUY) per ISIN."""
    from collections import defaultdict
    by_isin: dict = defaultdict(list)
    for o in carnet_orders:
        by_isin[o.isin].append(o)
    result = {}
    for isin, orders in by_isin.items():
        sorted_orders = sorted(orders, key=lambda o: o.date)
        n_flips = 0
        prev_sign = None
        for o in sorted_orders:
            sign = 1 if o.qty > 0 else -1
            if prev_sign is not None and sign != prev_sign:
                n_flips += 1
            prev_sign = sign
        result[isin] = n_flips
    return result


def fifo_to_legacy_recon(
    fifo_result: ReconResult,
    carnet_orders: list,
    as_of,
    prod_ccy: str,
) -> SimpleNamespace:
    """Convert a fifo.ReconResult into the dict-based format consumed by amc_blocks.

    Parameters
    ----------
    fifo_result   : the ReconResult from core/fifo/pipeline.run_fifo_recon()
    carnet_orders : the corrected carnet Order list (without T0 initial orders)
                    — needed to compute flips per ISIN
    as_of         : valuation date (datetime.date or datetime.datetime)
    prod_ccy      : product currency string
    """
    if as_of is None:
        as_of_date = datetime.date.today()
    elif hasattr(as_of, "date"):
        as_of_date = as_of.date()
    else:
        as_of_date = as_of

    flips_by_isin = _compute_flips(carnet_orders)

    # ── Round trips ───────────────────────────────────────────────────
    round_trips: list[dict] = []
    for rt in fifo_result.round_trips:
        cost = rt.qty * rt.buy_price_prod
        holding = (rt.sell_date - rt.buy_date).days if (rt.sell_date and rt.buy_date) else None
        # FX decomposition:
        #   price_pnl = qty × sell_fx × (sell_price_local − buy_price_local)
        #   fx_pnl    = qty × buy_price_local × (sell_fx − buy_fx)
        #   sum = qty × (sell_price_local×sell_fx − buy_price_local×buy_fx) = pnl_prod ✓
        price_pnl = rt.qty * rt.sell_fx * (rt.sell_price_local - rt.buy_price_local)
        fx_pnl = rt.qty * rt.buy_price_local * (rt.sell_fx - rt.buy_fx)

        round_trips.append({
            "isin": rt.isin,
            "name": rt.name,
            "ccy": rt.ccy,
            "qty": round(rt.qty, 4),
            "entry_date": rt.buy_date.isoformat() if rt.buy_date else None,
            "exit_date": rt.sell_date.isoformat() if rt.sell_date else None,
            "holding_days": holding,
            "entry_px_local": round(rt.buy_price_local, 6),
            "exit_px_local": round(rt.sell_price_local, 6),
            "entry_fx": round(rt.buy_fx, 6),
            "exit_fx": round(rt.sell_fx, 6),
            "pnl_prod": round(rt.pnl_prod, 2),
            "price_pnl": round(price_pnl, 2),
            "fx_pnl": round(fx_pnl, 2),
            "ret_pct": round((rt.pnl_prod / cost) * 100, 3) if cost else None,
            "exit_quarter": _quarter(rt.sell_date),
            "synthetic_entry": rt.buy_source == "synthetic_t0",
            "synthetic_source": rt.buy_source if rt.buy_source == "synthetic_t0" else None,
        })

    # ── Open positions ────────────────────────────────────────────────
    open_positions: list[dict] = []
    for op in fifo_result.open_positions:
        mark = op.mark_prod
        unreal = op.unreal_pnl_prod
        value = round(op.open_qty * mark, 2) if mark is not None else None

        first_entry = None
        last_entry = None
        n_buys = 0
        if op.lots:
            dates = [l.date for l in op.lots if l.date]
            if dates:
                first_entry = min(dates).isoformat()
                last_entry = max(dates).isoformat()
            n_buys = len(op.lots)

        hold_days = None
        if first_entry:
            first_d = datetime.date.fromisoformat(first_entry)
            hold_days = (as_of_date - first_d).days

        unreal_ret = None
        if unreal is not None and op.cost_prod and math.isfinite(unreal / op.cost_prod):
            unreal_ret = round((unreal / op.cost_prod) * 100, 3)

        has_synthetic = any(l.source == "synthetic_t0" for l in op.lots)

        open_positions.append({
            "isin": op.isin,
            "name": op.name,
            "ccy": op.ccy,
            "open_qty": round(op.open_qty, 4),
            "avg_cost_prod": round(op.avg_cost_prod, 4),
            "mark_prod": round(mark, 4) if mark is not None else None,
            "cost_prod": round(op.cost_prod, 2),
            "value_prod": value,
            "unreal_pnl_prod": round(unreal, 2) if unreal is not None else None,
            "unreal_ret_pct": unreal_ret,
            "first_entry_date": first_entry,
            "last_entry_date": last_entry,
            "holding_days": hold_days,
            "n_buys": n_buys,
            "flips": flips_by_isin.get(op.isin, 0),
            "marked": mark is not None,
            "synthetic_entry": has_synthetic,
        })

    # ── Synthetic report → list[dict] ─────────────────────────────────
    synthetic_report: list[dict] = []
    for s in fifo_result.synthetic_report:
        synthetic_report.append({
            "isin": s.isin,
            "name": s.name,
            "excess_qty": round(s.excess_qty, 4),
            "price_local": round(s.price_local, 4) if s.price_local else None,
            "fx": round(s.fx, 6),
            "price_prod": round(s.price_prod, 4),
            "source": s.source,
            "injected": s.injected,
            "t0": fifo_result.as_of.isoformat() if fifo_result.as_of else None,
        })

    # ── Warnings from synthetic report ────────────────────────────────
    warnings: list[str] = []
    injected = [s for s in fifo_result.synthetic_report if s.injected]
    failed = [s for s in fifo_result.synthetic_report if not s.injected]
    if injected:
        warnings.append(
            f"[Mode T0 synthétique] {len(injected)} BUY(s) synthétique(s) injectés "
            f"à la date de fixing."
        )
    if failed:
        names = ", ".join(s.name for s in failed[:5])
        warnings.append(
            f"{len(failed)} titre(s) non résolus (prix indisponible, P&L clampé) : {names}."
        )

    return SimpleNamespace(
        round_trips=round_trips,
        open_positions=open_positions,
        warnings=warnings,
        as_of=as_of,
        synthetic_report=synthetic_report,
    )
