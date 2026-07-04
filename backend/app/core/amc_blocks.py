"""AMC analysis blocks B / C / D — built on the order-book reconstruction.

  • Bloc B — attribution by underlying & period (realised + latent P&L, price vs FX)
  • Bloc C — trading quality / turnover (round-trips, hit ratio, trading vs hold)
  • Bloc D — manager behaviour (conviction vs uncertainty, 2×2 matrix)

All amounts are in the product (NAV) currency. These blocks are fully offline:
they need only the raw order book + composition snapshot.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional

from .amc_orderbook import ReconResult


def _safe_div(a: float, b: float) -> Optional[float]:
    return (a / b) if b else None


# ── NAV/fee reconciliation — ground truth for the FIFO gross P&L ───────

def _performance_fee_drag(rows: List[dict], filled_outstanding: List[Optional[float]],
                          perf_fee_pct: Optional[float]) -> tuple:
    """High-water-mark performance fee, crystallised daily on NEW highs only.

    On any day the (net, published) NAV sets a new all-time high, that day's
    net gain over the previous HWM is 90% of the day's gross gain (10% —or
    whatever perf_fee_pct is— having already been skimmed before publication).
    So the fee for that day, in NAV-per-unit terms, is:

        fee_per_unit = net_gain_over_hwm × perf_fee_pct / (100 − perf_fee_pct)

    Summed across every new-high day and multiplied by that day's outstanding
    units. Days where the NAV is below its historical HWM incur no fee — this
    is what distinguishes it from the flat daily management-fee accrual.
    """
    if not perf_fee_pct or not rows:
        return 0.0, {}
    frac = (perf_fee_pct / 100.0) / (1.0 - perf_fee_pct / 100.0)
    hwm = rows[0]["nav"]
    total_fee = 0.0
    n_events = 0
    for r, out in zip(rows, filled_outstanding):
        if r["nav"] > hwm:
            fee_per_unit = (r["nav"] - hwm) * frac
            total_fee += fee_per_unit * (out or 0.0)
            hwm = r["nav"]
            n_events += 1
    return total_fee, {"n_events": n_events, "hwm_final": round(hwm, 4)}


def _transaction_cost_drag(carnet_orders: Optional[list], txn_cost_pct: Optional[float]) -> float:
    """Rebalancing cost: txn_cost_pct of the notional on every carnet trade."""
    if not txn_cost_pct or not carnet_orders:
        return 0.0
    total_notional = sum(abs(o.qty * o.price_prod) for o in carnet_orders)
    return total_notional * (txn_cost_pct / 100.0)


def _nav_reconciliation(nav: List[dict], management_fee_pct: Optional[float],
                        as_of: Optional[str],
                        perf_fee_pct: Optional[float] = None,
                        txn_cost_pct: Optional[float] = None,
                        carnet_orders: Optional[list] = None) -> Optional[dict]:
    """Compute the exact NAV-implied fund P&L and estimated fee drag, as of
    the same date the FIFO reconstruction used (not "today").

    net_subscriptions is derived purely from the daily NAV CSV: every date
    where `Outstanding quantity` changes is a subscription/redemption event,
    valued at that day's NAV — no external/assumed subscription figure needed.

        nav_implied_pnl = (outstanding_asof × NAV_asof) − net_subscriptions

    fee_drag has three components, each optional (only computed when the
    corresponding rate is supplied), used to bring the FIFO gross P&L down to
    a NAV-comparable "net of fees" figure:
      - management: daily accrual on AUM (fee_pct/100/252)
      - performance: high-water-mark, crystallised daily on new highs only
      - transaction: per-trade cost on carnet notional
    """
    if not nav or not as_of:
        return None
    rows = [r for r in nav if r["date"] <= as_of]
    if not rows:
        return None

    # Forward-filled outstanding — AUM base for the management/perf fee accruals.
    filled: List[Optional[float]] = []
    cur: Optional[float] = None
    for r in rows:
        if r.get("outstanding"):
            cur = r["outstanding"]
        filled.append(cur)
    first_known = next((x for x in filled if x), None)
    if first_known is None:
        return None
    filled = [x if x else first_known for x in filled]

    management_fee_drag = 0.0
    if management_fee_pct:
        fee_daily = (management_fee_pct / 100.0) / 252.0
        for r, out in zip(rows, filled):
            management_fee_drag += r["nav"] * out * fee_daily

    performance_fee_drag, perf_meta = _performance_fee_drag(rows, filled, perf_fee_pct)
    transaction_cost_drag = _transaction_cost_drag(carnet_orders, txn_cost_pct)

    total_fee_drag = management_fee_drag + performance_fee_drag + transaction_cost_drag

    # Raw (non-forward-filled) outstanding changes = actual sub/red events.
    net_flow_prod = 0.0
    prev_out: Optional[float] = None
    for r in rows:
        out = r.get("outstanding")
        if out is None:
            continue
        net_flow_prod += (out - prev_out) * r["nav"] if prev_out is not None else out * r["nav"]
        prev_out = out

    last_row = rows[-1]
    nav_value_prod = last_row["nav"] * filled[-1]
    nav_implied_pnl_prod = nav_value_prod - net_flow_prod

    return {
        "as_of": last_row["date"],
        "nav_value_prod": round(nav_value_prod, 2),
        "net_subscriptions_prod": round(net_flow_prod, 2),
        "nav_implied_pnl_prod": round(nav_implied_pnl_prod, 2),
        "fee_drag_prod": round(-total_fee_drag, 2) if total_fee_drag else None,
        "fee_breakdown": {
            "management_fee_pct": management_fee_pct,
            "management_fee_prod": round(-management_fee_drag, 2) if management_fee_pct else None,
            "performance_fee_pct": perf_fee_pct,
            "performance_fee_prod": round(-performance_fee_drag, 2) if perf_fee_pct else None,
            "performance_fee_events": perf_meta.get("n_events"),
            "performance_fee_hwm_final": perf_meta.get("hwm_final"),
            "transaction_cost_pct": txn_cost_pct,
            "transaction_cost_prod": round(-transaction_cost_drag, 2) if txn_cost_pct else None,
        },
    }


# ── Bloc B — Attribution by underlying & period ────────────────────────

def block_b_attribution(recon: ReconResult, composition: dict,
                        nav: Optional[List[dict]] = None,
                        management_fee_pct: Optional[float] = None,
                        fifo_as_of: Optional[str] = None,
                        perf_fee_pct: Optional[float] = None,
                        txn_cost_pct: Optional[float] = None,
                        carnet_orders: Optional[list] = None) -> dict:
    """P&L contribution per underlying (realised + latent), price vs FX split,
    and a temporal (quarterly) breakdown of realised P&L."""
    weight_by_isin = {c["isin"]: c["weight"] for c in composition.get("components", [])}

    per_name: dict[str, dict] = {}

    def _slot(isin, name, ccy):
        if isin not in per_name:
            per_name[isin] = {
                "isin": isin, "name": name, "ccy": ccy,
                "realized_pnl": 0.0, "price_pnl": 0.0, "fx_pnl": 0.0,
                "unreal_pnl": 0.0, "n_round_trips": 0,
                "weight": weight_by_isin.get(isin, 0.0),
            }
        return per_name[isin]

    for rt in recon.round_trips:
        s = _slot(rt["isin"], rt["name"], rt["ccy"])
        s["realized_pnl"] += rt["pnl_prod"]
        s["price_pnl"] += rt["price_pnl"]
        s["fx_pnl"] += rt["fx_pnl"]
        s["n_round_trips"] += 1

    for op in recon.open_positions:
        s = _slot(op["isin"], op["name"], op["ccy"])
        if op["unreal_pnl_prod"] is not None:
            s["unreal_pnl"] += op["unreal_pnl_prod"]

    rows = []
    for s in per_name.values():
        total = s["realized_pnl"] + s["unreal_pnl"]
        rows.append({
            **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()},
            "total_pnl": round(total, 2),
        })
    rows.sort(key=lambda r: r["total_pnl"], reverse=True)

    # Temporal: realised P&L by exit quarter
    by_quarter: dict[str, float] = {}
    for rt in recon.round_trips:
        q = rt["exit_quarter"]
        if q:
            by_quarter[q] = by_quarter.get(q, 0.0) + rt["pnl_prod"]
    quarterly = [{"quarter": q, "realized_pnl": round(v, 2)}
                 for q, v in sorted(by_quarter.items())]

    tot_real = sum(s["realized_pnl"] for s in per_name.values())
    tot_unreal = sum(s["unreal_pnl"] for s in per_name.values())
    tot_price = sum(s["price_pnl"] for s in per_name.values())
    tot_fx = sum(s["fx_pnl"] for s in per_name.values())
    total_pnl_gross = tot_real + tot_unreal

    totals = {
        "realized_pnl": round(tot_real, 2),
        "unreal_pnl": round(tot_unreal, 2),
        "total_pnl": round(total_pnl_gross, 2),
        "realized_price_pnl": round(tot_price, 2),
        "realized_fx_pnl": round(tot_fx, 2),
        "fx_share_of_realized_pct": round(_safe_div(abs(tot_fx), abs(tot_price) + abs(tot_fx)) * 100, 1)
                                    if (abs(tot_price) + abs(tot_fx)) else None,
    }

    # ── NAV reconciliation — validates the FIFO gross P&L against the ──
    # ── fund's actual subscription-flow-implied P&L, net of est. fees ──
    nav_recon = _nav_reconciliation(
        nav, management_fee_pct, fifo_as_of,
        perf_fee_pct=perf_fee_pct, txn_cost_pct=txn_cost_pct, carnet_orders=carnet_orders,
    ) if nav else None
    if nav_recon:
        fee_drag = nav_recon["fee_drag_prod"] or 0.0
        total_pnl_net = total_pnl_gross + fee_drag
        nav_pnl = nav_recon["nav_implied_pnl_prod"]
        gap = total_pnl_net - nav_pnl
        totals["fee_drag_prod"] = round(fee_drag, 2)
        totals["total_pnl_net_of_fees"] = round(total_pnl_net, 2)
        totals["reconciliation"] = {
            **nav_recon,
            "total_pnl_net_of_fees": round(total_pnl_net, 2),
            "gap_prod": round(gap, 2),
            "gap_pct": round(gap / nav_pnl * 100, 1) if nav_pnl else None,
        }

    return {
        "per_name": rows,
        "top5": rows[:5],
        "flop5": rows[-5:][::-1],
        "quarterly_realized": quarterly,
        "totals": totals,
        "note": "P&L latent des positions ouvertes non décomposé prix/FX (un seul mark "
                "courant, pas de série de prix continue par constituant).",
    }


# ── Bloc C — Trading quality / turnover ────────────────────────────────

def block_c_trading(recon: ReconResult, orders: list[dict], nav: list[dict],
                    composition: dict) -> dict:
    rts = recon.round_trips
    pnls = [rt["pnl_prod"] for rt in rts]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    holds = [rt["holding_days"] for rt in rts if rt["holding_days"] is not None]

    n = len(rts)
    win_rate = _safe_div(len(wins), n)
    profit_factor = _safe_div(sum(wins), abs(sum(losses)))

    # Turnover — gross executed notional vs average AUM
    gross_traded = sum(o["notional_prod"] for o in orders
                       if o["state"] == "Done" and o["executed_qty"])
    avg_aum = _avg_aum(nav, composition)
    period_days = _period_days(orders)
    turnover_rate = _safe_div(gross_traded, avg_aum)
    turnover_ann = (turnover_rate * 365.0 / period_days) if (turnover_rate and period_days) else None

    # Timing at execution points — per name avg buy vs avg sell (local ccy)
    timing: dict[str, dict] = {}
    for o in orders:
        if o["state"] != "Done" or not o["executed_qty"] or o["price_local"] is None:
            continue
        t = timing.setdefault(o["isin"], {"name": o["name"], "buy_q": 0.0, "buy_v": 0.0,
                                          "sell_q": 0.0, "sell_v": 0.0})
        if o["executed_qty"] > 0:
            t["buy_q"] += o["executed_qty"]; t["buy_v"] += o["executed_qty"] * o["price_local"]
        else:
            t["sell_q"] += -o["executed_qty"]; t["sell_v"] += -o["executed_qty"] * o["price_local"]
    timing_rows = []
    for isin, t in timing.items():
        avg_buy = _safe_div(t["buy_v"], t["buy_q"])
        avg_sell = _safe_div(t["sell_v"], t["sell_q"])
        spread = (round((avg_sell / avg_buy - 1) * 100, 2)
                  if (avg_buy and avg_sell) else None)
        timing_rows.append({"isin": isin, "name": t["name"],
                            "avg_buy_local": round(avg_buy, 4) if avg_buy else None,
                            "avg_sell_local": round(avg_sell, 4) if avg_sell else None,
                            "sell_vs_buy_pct": spread})

    realized_total = sum(pnls)
    unreal_total = sum(op["unreal_pnl_prod"] or 0.0 for op in recon.open_positions)

    return {
        "round_trips": {
            "count": n,
            "win_rate_pct": round(win_rate * 100, 1) if win_rate is not None else None,
            "avg_win": round(statistics.mean(wins), 2) if wins else 0.0,
            "avg_loss": round(statistics.mean(losses), 2) if losses else 0.0,
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "avg_holding_days": round(statistics.mean(holds), 1) if holds else None,
            "median_holding_days": round(statistics.median(holds), 1) if holds else None,
            "realized_pnl": round(realized_total, 2),
        },
        "turnover": {
            "gross_traded_prod": round(gross_traded, 0),
            "avg_aum_prod": round(avg_aum, 0) if avg_aum else None,
            "turnover_rate": round(turnover_rate, 3) if turnover_rate is not None else None,
            "turnover_annualized": round(turnover_ann, 3) if turnover_ann is not None else None,
            "period_days": period_days,
        },
        "trading_vs_hold": {
            "realized_pnl_closed": round(realized_total, 2),
            "unreal_pnl_open": round(unreal_total, 2),
            "note": "Décomposition complète trading-vs-portage (buy-&-hold de la compo "
                    "initiale) nécessite l'historique de prix par constituant — non "
                    "disponible. On rapporte ici P&L clôturé vs P&L latent comme proxy.",
        },
        "timing": sorted(timing_rows, key=lambda r: (r["sell_vs_buy_pct"] is None, r["sell_vs_buy_pct"] or 0)),
    }


def _avg_aum(nav: list[dict], composition: dict) -> float:
    if nav:
        vals = []
        last_out = composition.get("outstanding") or 0.0
        # walk backwards filling outstanding forward
        outs = [r.get("outstanding") for r in nav]
        # forward-fill
        filled = []
        cur = None
        for o in outs:
            if o:
                cur = o
            filled.append(cur)
        # back-fill leading None with first known
        firstknown = next((x for x in filled if x), last_out)
        filled = [x if x else firstknown for x in filled]
        for r, out in zip(nav, filled):
            vals.append(r["nav"] * (out or 0.0))
        if vals:
            return statistics.mean(vals)
    return composition.get("total_aum") or 0.0


def _period_days(orders: list[dict]) -> Optional[int]:
    dates = [o["date"] for o in orders if o["date"]]
    if len(dates) < 2:
        return None
    return (max(dates) - min(dates)).days or None


# ── Bloc D — Behaviour: conviction vs uncertainty ──────────────────────

def block_d_behaviour(recon: ReconResult, orders: list[dict], composition: dict,
                      long_term_days: int, conviction_weight_pct: float) -> dict:
    # Holding-period distribution (closed round-trips + open positions)
    closed_holds = [rt["holding_days"] for rt in recon.round_trips if rt["holding_days"] is not None]
    open_holds = [op["holding_days"] for op in recon.open_positions if op["holding_days"] is not None]
    all_holds = closed_holds + open_holds
    long_term = sum(1 for h in all_holds if h >= long_term_days)
    tactical = sum(1 for h in all_holds if h < long_term_days)

    # Order hygiene — discarded & partial fills
    done = [o for o in orders if o["state"] == "Done"]
    discarded = [o for o in orders if o["state"] == "Discarded"]
    partial = [o for o in done if o["executed_qty"] and o["ordered_qty"]
               and abs(o["executed_qty"]) < abs(o["ordered_qty"]) - 1e-9]
    disc_by_name: dict[str, int] = {}
    for o in discarded:
        disc_by_name[o["name"]] = disc_by_name.get(o["name"], 0) + 1
    discarded_top = sorted(
        [{"name": k, "discarded": v} for k, v in disc_by_name.items()],
        key=lambda r: r["discarded"], reverse=True)[:10]

    # Flip-flop / re-entry — names traded in multiple round-trips or with side flips
    rt_count: dict[str, int] = {}
    for rt in recon.round_trips:
        rt_count[rt["isin"]] = rt_count.get(rt["isin"], 0) + 1
    flips_by_isin = {op["isin"]: op.get("flips", 0) for op in recon.open_positions}
    reentry_names = sorted(
        [{"isin": k, "round_trips": v} for k, v in rt_count.items() if v >= 2],
        key=lambda r: r["round_trips"], reverse=True)[:10]

    # Conviction × result matrix
    universe: dict[str, dict] = {}
    weight_by_isin = {c["isin"]: c["weight"] for c in composition.get("components", [])}
    name_by_isin = {c["isin"]: c["name"] for c in composition.get("components", [])}

    # realised + unreal per name
    pnl_by_isin: dict[str, float] = {}
    for rt in recon.round_trips:
        pnl_by_isin[rt["isin"]] = pnl_by_isin.get(rt["isin"], 0.0) + rt["pnl_prod"]
    for op in recon.open_positions:
        pnl_by_isin[op["isin"]] = pnl_by_isin.get(op["isin"], 0.0) + (op["unreal_pnl_prod"] or 0.0)

    max_hold_by_isin: dict[str, int] = {}
    for rt in recon.round_trips:
        if rt["holding_days"] is not None:
            max_hold_by_isin[rt["isin"]] = max(max_hold_by_isin.get(rt["isin"], 0), rt["holding_days"])
    for op in recon.open_positions:
        if op["holding_days"] is not None:
            max_hold_by_isin[op["isin"]] = max(max_hold_by_isin.get(op["isin"], 0), op["holding_days"])

    all_isins = set(pnl_by_isin) | set(weight_by_isin)
    matrix = {"conviction_winners": [], "stubborn_losers": [],
              "tactical_winners": [], "uncertainty": []}
    quadrant_pnl = {k: 0.0 for k in matrix}

    for isin in all_isins:
        if isin is None:  # skip cash/fx positions (no ISIN)
            continue
        weight_pct = (weight_by_isin.get(isin, 0.0)) * 100
        max_hold = max_hold_by_isin.get(isin, 0)
        churn = rt_count.get(isin, 0) + flips_by_isin.get(isin, 0)
        total_pnl = pnl_by_isin.get(isin, 0.0)
        high_conviction = (weight_pct >= conviction_weight_pct) or (max_hold >= long_term_days and weight_pct > 0)
        positive = total_pnl > 0
        rec = {
            "isin": isin,
            "name": name_by_isin.get(isin) or isin,
            "weight_pct": round(weight_pct, 2),
            "max_hold_days": max_hold,
            "churn": churn,
            "total_pnl": round(total_pnl, 2),
        }
        if high_conviction and positive:
            q = "conviction_winners"
        elif high_conviction and not positive:
            q = "stubborn_losers"
        elif not high_conviction and positive:
            q = "tactical_winners"
        else:
            q = "uncertainty"
        rec["quadrant"] = q
        matrix[q].append(rec)
        quadrant_pnl[q] += total_pnl

    for q in matrix:
        matrix[q].sort(key=lambda r: abs(r["total_pnl"]), reverse=True)

    return {
        "holding_distribution": {
            "long_term_count": long_term,
            "tactical_count": tactical,
            "long_term_days_cutoff": long_term_days,
            "avg_holding_days": round(statistics.mean(all_holds), 1) if all_holds else None,
            "closed_count": len(closed_holds),
            "open_count": len(open_holds),
        },
        "order_hygiene": {
            "n_done": len(done),
            "n_discarded": len(discarded),
            "discarded_ratio_pct": round(len(discarded) / (len(done) + len(discarded)) * 100, 1)
                                   if (len(done) + len(discarded)) else None,
            "n_partial_fills": len(partial),
            "discarded_top": discarded_top,
        },
        "reentry": {
            "names_multiple_round_trips": reentry_names,
        },
        "conviction_matrix": {
            "quadrants": matrix,
            "counts": {k: len(v) for k, v in matrix.items()},
            "pnl": {k: round(v, 2) for k, v in quadrant_pnl.items()},
            "labels": {
                "conviction_winners": "Paris gagnants assumés (forte conviction, +)",
                "stubborn_losers": "Entêtements coûteux (forte conviction, −)",
                "tactical_winners": "Coups tactiques réussis (faible conviction, +)",
                "uncertainty": "Positions d'incertitude (faible conviction, −)",
            },
            "params": {"long_term_days": long_term_days,
                       "conviction_weight_pct": conviction_weight_pct},
        },
    }
