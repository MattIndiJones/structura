"""AMC order-book parser — the shared foundation for blocks B / C / D.

Loads the raw LUKB exports (composition `Def.txt`, NAV timeseries CSV, order-book
JSON) and reconstructs, using only the order book:
  • normalised order flow (signed quantities, local price, FX, product-ccy price)
  • FIFO position reconstruction → completed round-trips + open lots
  • current marks per name (from the composition snapshot) → latent P&L

Everything is in the *product* (NAV) currency. P&L on closed trades is split
into a price effect and an FX effect; open positions are marked to the
issuer's composition snapshot (single current mark — no continuous constituent
price series available, see the confidence module).
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import pandas as pd


# ── Raw data loading ───────────────────────────────────────────────────

def _parse_dt(s: str) -> Optional[_dt.datetime]:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(s)
    except ValueError:
        # fall back to date-only
        try:
            return _dt.datetime.fromisoformat(s[:10])
        except ValueError:
            return None


def _f(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def load_composition(path: str) -> dict:
    """Parse a `* Def.txt` snapshot → product meta + components with current marks."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    prod = d["data"]["products"]["items"][0]
    nav = prod.get("netAssetValue") or {}
    nav_value = _f(nav.get("value")) or 0.0
    outstanding = _f(prod.get("outstandingQuantity")) or 0.0
    total_aum = nav_value * outstanding  # product ccy

    components = []
    for c in prod.get("components", []):
        u = c.get("underlying") or {}
        qty = _f(c.get("position")) or 0.0
        weight = _f(c.get("weight")) or 0.0
        value_prod = weight * total_aum
        isin = u.get("isin", "")
        components.append({
            "isin": isin,
            "name": u.get("name", ""),
            "currency": u.get("currency", ""),
            "position": qty,
            "weight": weight,
            "value_prod": value_prod,
        })

    return {
        "isin": prod.get("isin", ""),
        "name": prod.get("name", ""),
        "currency": prod.get("currency", ""),
        "nav_value": nav_value,
        "nav_date": _parse_dt(nav.get("date", "")),
        "outstanding": outstanding,
        "total_aum": total_aum,
        "components": components,
        "marks": {},   # populated by build_marks() in load_study_data
    }


def load_nav(path: str) -> list[dict]:
    """Parse the timeseries CSV → [{date, nav, outstanding}] sorted by date."""
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        # normalise header keys
        for raw in reader:
            row = { (k or "").strip(): v for k, v in raw.items() }
            d = row.get("Date", "").strip()
            price = _f(row.get("Price"))
            # dd.mm.yyyy
            dt = None
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    dt = _dt.datetime.strptime(d, fmt)
                    break
                except ValueError:
                    continue
            if dt is None or price is None:
                continue
            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "nav": price,
                "outstanding": _f(row.get("Outstanding quantity")),
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def load_orders(paths: list[str]) -> list[dict]:
    """Parse order-book JSON files → normalised, de-duplicated order list.

    Each normalised order (product ccy):
      id, date(datetime), state, name, isin, ccy,
      ordered_qty, executed_qty (signed), side ('BUY'/'SELL'),
      price_local, fx, price_prod, notional_prod (abs)
    """
    seen: set[str] = set()
    out: List[dict] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        items = (((d.get("data") or {}).get("orders") or {}).get("items")) or []
        for o in items:
            oid = o.get("id", "")
            if oid and oid in seen:
                continue
            if oid:
                seen.add(oid)
            u = o.get("underlying") or {}
            ep = o.get("executionPrice") or {}
            executed = _f(o.get("executedQuantity")) or 0.0
            ordered = _f(o.get("orderedQuantity")) or 0.0
            price_local = _f(ep.get("amount"))
            fx = _f(o.get("usedFxRate"))
            price_prod = (price_local * fx) if (price_local is not None and fx is not None) else None
            out.append({
                "id": oid,
                "date": _parse_dt(o.get("creationDateTime", "")),
                "state": o.get("state", ""),
                "name": u.get("name", ""),
                "isin": u.get("isin", ""),
                "ccy": u.get("currency", ""),
                "ordered_qty": ordered,
                "executed_qty": executed,
                "side": "BUY" if ordered >= 0 else "SELL",
                "price_local": price_local,
                "fx": fx,
                "price_prod": price_prod,
                "notional_prod": abs(executed * price_prod) if price_prod is not None else 0.0,
            })
    out.sort(key=lambda r: (r["date"] or _dt.datetime.min))
    return out


# ── T0 price fetcher (for synthetic inception BUYs) ───────────────────

def _fetch_t0_price(isin: str, ccy: str, prod_ccy: str,
                    t0: _dt.date, fallback_price_local: Optional[float],
                    fallback_fx: Optional[float],
                    proxy_order_date=None,
                    ts_fixing_price: Optional[float] = None) -> Tuple[Optional[float], Optional[float], str]:
    """Return (price_local, fx_rate, source_label) at T0 for a synthetic inception BUY.

    Strategy:
      1. yfinance direct ISIN lookup — split-adjusted, consistent with post-split carnet qtys.
      2. Fallback: use the weighted-average price from known carnet orders (proxy).
      3. Term sheet fixing_price — last resort if yfinance has no data (pre-IPO, delisted, etc.)
         NOT used as Priority 0 because TS prices are pre-split and would mismatch
         post-split carnet quantities (e.g. Nvidia 10:1 split 4 days after fund inception).
      4. If all fail: return (None, None, 'unavailable').

    Pre-IPO guard: if yfinance has no data at T0 AND the proxy order date is
    more than 180 days after T0, the security almost certainly did not exist at
    T0 (post-IPO injection). Returns (None, None, 'pre_ipo') to skip injection.

    The FX rate is fetched from yfinance for the pair {ccy}/{prod_ccy} at T0.
    If ccy == prod_ccy the FX is always 1.0.
    """
    t0_str = t0.strftime("%Y-%m-%d")
    # Add 5 calendar days of buffer to handle weekends / holidays
    t1_str = (t0 + _dt.timedelta(days=7)).strftime("%Y-%m-%d")

    price_local: Optional[float] = None
    fx: Optional[float] = None
    source = "unavailable"

    # ── 1. yfinance ISIN lookup (split-adjusted — consistent with carnet quantities) ──
    try:
        hist = yf.Ticker(isin).history(start=t0_str, end=t1_str, auto_adjust=False)
        if not hist.empty:
            price_local = float(hist["Close"].iloc[0])
            source = "yfinance_isin"
    except Exception:
        pass

    # ── 2. Fallback: use proxy price from known orders ─────────────────
    if price_local is None and fallback_price_local is not None:
        # Pre-IPO guard: if the earliest known order is >180 days after T0,
        # the security did not exist at T0 — skip synthetic injection entirely.
        if proxy_order_date is not None:
            try:
                if hasattr(proxy_order_date, "date"):
                    proxy_d = proxy_order_date.date()
                elif hasattr(proxy_order_date, "year"):
                    proxy_d = proxy_order_date
                else:
                    proxy_d = _dt.date.fromisoformat(str(proxy_order_date)[:10])
                if (proxy_d - t0).days > 180:
                    return None, None, "pre_ipo"
            except Exception:
                pass
        price_local = fallback_price_local
        source = "order_proxy"

    # ── 3. Term sheet fixing_price — last resort (yfinance and proxy both failed) ──
    if price_local is None and ts_fixing_price and ts_fixing_price > 0:
        price_local = ts_fixing_price
        source = "termsheet_fixing"

    if price_local is None:
        return None, None, "unavailable"

    # ── 4. FX at T0 ───────────────────────────────────────────────────
    if ccy.upper() == prod_ccy.upper():
        fx = 1.0
    else:
        if fallback_fx is not None and source == "order_proxy":
            # Use the fallback FX from the proxy order (same vintage)
            fx = fallback_fx
        else:
            try:
                pair = f"{ccy.upper()}{prod_ccy.upper()}=X"
                # FX rates are not split-adjusted, but keep consistent with price call
                fx_hist = yf.Ticker(pair).history(start=t0_str, end=t1_str, auto_adjust=False)
                if not fx_hist.empty:
                    fx = float(fx_hist["Close"].iloc[0])
            except Exception:
                pass
        if fx is None and fallback_fx is not None:
            fx = fallback_fx
            source += "+fx_proxy"
        if fx is None:
            fx = 1.0
            source += "+fx_missing"

    return price_local, fx, source


# ── FIFO position reconstruction ───────────────────────────────────────

@dataclass
class _Lot:
    qty: float
    date: _dt.datetime
    price_local: float
    fx: float


@dataclass
class ReconResult:
    round_trips: List[dict] = field(default_factory=list)
    open_positions: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    as_of: Optional[_dt.datetime] = None


def reconstruct(orders: List[dict], marks: Dict[str, float],
                comp_meta: List[dict], as_of: Optional[_dt.datetime],
                recon_mode: str = "strict",
                nav_start_date: Optional[str] = None,
                prod_ccy: str = "",
                termsheet_positions: Optional[List[dict]] = None) -> ReconResult:
    """FIFO match executed Done orders per ISIN → round-trips + open lots.

    P&L (product ccy) on a matched sell is split:
        pnl_prod  = q*(P1*F1 - P0*F0)
        price_pnl = q*F1*(P1 - P0)      (FX held at exit)
        fx_pnl    = q*P0*(F1 - F0)      (price held at entry)

    recon_mode="strict" (default): excess sells are clamped (P&L=0).
    recon_mode="t0_synthetic": synthetic BUY orders are injected at nav_start_date
        using termsheet fixing_price (priority) or yfinance prices as cost basis.
    """
    # Build ISIN → fixing_price lookup from term sheet (used in t0_synthetic mode)
    ts_fixing: Dict[str, float] = {}
    if termsheet_positions:
        for ts in termsheet_positions:
            isin_ts = (ts.get("isin") or "").strip()
            fp = float(ts.get("fixing_price") or 0)
            if isin_ts and fp > 0:
                ts_fixing[isin_ts] = fp
    res = ReconResult(as_of=as_of)
    name_by_isin = {c["isin"]: c["name"] for c in comp_meta}

    def _sort_key(r):
        d = r["date"]
        if d is None:
            return _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)
        if d.tzinfo is None:
            return d.replace(tzinfo=_dt.timezone.utc)
        return d

    # group executed Done orders per isin, chronological
    # Strip any previously-injected synthetic orders — always recalculate fresh
    by_isin: Dict[str, List[dict]] = {}
    for o in orders:
        if o["state"] != "Done" or not o["executed_qty"] or o["price_local"] is None or o["fx"] is None:
            continue
        if (o.get("id") or "").startswith("__synthetic_"):
            continue
        by_isin.setdefault(o["isin"], []).append(o)

    # ── T0 synthetic mode: first-pass to measure excess sells, then inject ──
    synthetic_report: List[dict] = []   # summary of injected synthetic orders

    if recon_mode == "t0_synthetic" and nav_start_date:
        try:
            t0_date = _dt.datetime.strptime(nav_start_date[:10], "%Y-%m-%d").date()
        except ValueError:
            t0_date = None

        if t0_date:
            # First pass: identify excess_qty per ISIN without recording round-trips
            excess_by_isin: Dict[str, dict] = {}
            for isin, ords in by_isin.items():
                ords_s = sorted(ords, key=_sort_key)
                inventory = 0.0
                for o in ords_s:
                    q = o["executed_qty"]
                    if q > 0:
                        inventory += q
                    else:
                        sell_q = -q
                        if sell_q > inventory + 1e-9:
                            excess = sell_q - max(inventory, 0.0)
                            existing = excess_by_isin.get(isin, {})
                            # For proxy date, ignore synthetic orders (they have date=T0 from a previous run)
                            real_ords_s = [o for o in ords_s if not (o.get("id") or "").startswith("__synthetic_")]
                            first_real = real_ords_s[0] if real_ords_s else ords_s[0]
                            excess_by_isin[isin] = {
                                "excess_qty": existing.get("excess_qty", 0.0) + excess,
                                "name": first_real["name"],
                                "ccy": first_real["ccy"],
                                # earliest real order for proxy price + pre-IPO guard
                                "proxy_price": first_real["price_local"],
                                "proxy_fx":    first_real["fx"],
                                "proxy_date":  first_real.get("date"),
                            }
                            inventory = 0.0
                        else:
                            inventory = max(0.0, inventory - sell_q)

            # Inject synthetic BUY orders
            t0_dt = _dt.datetime(t0_date.year, t0_date.month, t0_date.day,
                                  0, 0, 0, tzinfo=_dt.timezone.utc)
            fetched_ts = 0
            fetched_ok = 0
            fetched_proxy = 0
            fetched_fail = 0
            fetched_pre_ipo = 0

            for isin, info in excess_by_isin.items():
                price_local, fx, source = _fetch_t0_price(
                    isin=isin,
                    ccy=info["ccy"],
                    prod_ccy=prod_ccy,
                    t0=t0_date,
                    fallback_price_local=info["proxy_price"],
                    fallback_fx=info["proxy_fx"],
                    proxy_order_date=info.get("proxy_date"),
                    ts_fixing_price=ts_fixing.get(isin),
                )
                if price_local is None:
                    if source == "pre_ipo":
                        fetched_pre_ipo += 1
                        synthetic_report.append({
                            "isin": isin, "name": info["name"],
                            "excess_qty": round(info["excess_qty"], 4),
                            "source": "pre_ipo", "injected": False,
                        })
                    else:
                        fetched_fail += 1
                        synthetic_report.append({
                            "isin": isin, "name": info["name"],
                            "excess_qty": round(info["excess_qty"], 4),
                            "source": "unavailable", "injected": False,
                        })
                    continue

                price_prod = price_local * fx if fx else price_local
                synthetic_order = {
                    "id": f"__synthetic_{isin}",
                    "date": t0_dt,
                    "state": "Done",
                    "name": info["name"],
                    "isin": isin,
                    "ccy": info["ccy"],
                    "ordered_qty": info["excess_qty"],
                    "executed_qty": info["excess_qty"],   # positive = BUY
                    "side": "BUY",
                    "price_local": price_local,
                    "fx": fx,
                    "price_prod": price_prod,
                    "notional_prod": abs(info["excess_qty"] * price_prod),
                    "synthetic": True,
                    "synthetic_source": source,
                }
                by_isin[isin].insert(0, synthetic_order)
                by_isin[isin].sort(key=lambda r: (r["date"] or _dt.datetime.min))

                synthetic_report.append({
                    "isin": isin, "name": info["name"],
                    "excess_qty": round(info["excess_qty"], 4),
                    "price_local": round(price_local, 4),
                    "fx": round(fx, 6),
                    "price_prod": round(price_prod, 4),
                    "source": source, "injected": True,
                    "t0": nav_start_date[:10],
                })
                if source == "termsheet_fixing":
                    fetched_ts += 1
                elif "yfinance" in source:
                    fetched_ok += 1
                else:
                    fetched_proxy += 1

            if synthetic_report:
                injected  = [r for r in synthetic_report if r["injected"]]
                pre_ipo_r = [r for r in synthetic_report if r.get("source") == "pre_ipo"]
                failed    = [r for r in synthetic_report if not r["injected"] and r.get("source") != "pre_ipo"]
                parts = []
                if fetched_ts:
                    parts.append(f"{fetched_ts} via term sheet (prix fixing exacts)")
                if fetched_ok:
                    parts.append(f"{fetched_ok} via yfinance")
                if fetched_proxy:
                    parts.append(f"{fetched_proxy} via proxy ordre")
                msg = (
                    f"[Mode T0 synthétique] {len(injected)} BUY(s) synthétique(s) injectés à T0={nav_start_date[:10]} "
                    f"({', '.join(parts)})."
                )
                if pre_ipo_r:
                    names = ", ".join(r["name"] for r in pre_ipo_r)
                    msg += f" {len(pre_ipo_r)} titre(s) PRÉ-IPO exclus (inexistant(s) à T0) : {names}."
                if failed:
                    msg += f" {len(failed)} titre(s) non résolus (prix indisponible, P&L clampé)."
                res.warnings.append(msg)

    # ── Main FIFO loop ─────────────────────────────────────────────────
    excess_sell_isins = 0
    for isin, ords in by_isin.items():
        ords.sort(key=_sort_key)
        lots: list[_Lot] = []
        name = name_by_isin.get(isin) or (ords[0]["name"] if ords else isin)
        ccy = ords[0]["ccy"] if ords else ""
        flips = 0
        prev_side = None
        for o in ords:
            q = o["executed_qty"]
            side = "BUY" if q > 0 else "SELL"
            if prev_side and side != prev_side:
                flips += 1
            prev_side = side
            if q > 0:
                lots.append(_Lot(qty=q, date=o["date"], price_local=o["price_local"], fx=o["fx"]))
            else:
                remaining = -q
                while remaining > 1e-9 and lots:
                    lot = lots[0]
                    matched = min(remaining, lot.qty)
                    P0, F0 = lot.price_local, lot.fx
                    P1, F1 = o["price_local"], o["fx"]
                    pnl = matched * (P1 * F1 - P0 * F0)
                    price_pnl = matched * F1 * (P1 - P0)
                    fx_pnl = matched * P0 * (F1 - F0)
                    hold_days = ((o["date"] - lot.date).days
                                 if (o["date"] and lot.date) else None)
                    cost = matched * P0 * F0
                    is_synthetic = o.get("synthetic", False) or getattr(lot, "synthetic", False)
                    res.round_trips.append({
                        "isin": isin, "name": name, "ccy": ccy,
                        "qty": round(matched, 4),
                        "entry_date": lot.date.strftime("%Y-%m-%d") if lot.date else None,
                        "exit_date": o["date"].strftime("%Y-%m-%d") if o["date"] else None,
                        "holding_days": hold_days,
                        "entry_px_local": round(P0, 6), "exit_px_local": round(P1, 6),
                        "entry_fx": round(F0, 6), "exit_fx": round(F1, 6),
                        "pnl_prod": round(pnl, 2),
                        "price_pnl": round(price_pnl, 2),
                        "fx_pnl": round(fx_pnl, 2),
                        "ret_pct": round((pnl / cost) * 100, 3) if cost else None,
                        "exit_quarter": _quarter(o["date"]),
                        "synthetic_entry": o.get("synthetic", False),
                        "synthetic_source": o.get("synthetic_source"),
                    })
                    lot.qty -= matched
                    remaining -= matched
                    if lot.qty <= 1e-9:
                        lots.pop(0)
                if remaining > 1e-9:
                    excess_sell_isins += 1

        # remaining lots → open position
        if lots:
            open_qty = sum(l.qty for l in lots)
            cost_prod = sum(l.qty * l.price_local * l.fx for l in lots)
            avg_cost_prod = cost_prod / open_qty if open_qty else 0.0
            first_entry = min((l.date for l in lots if l.date), default=None)
            last_entry = max((l.date for l in lots if l.date), default=None)
            mark = marks.get(isin)
            unreal = (open_qty * mark - cost_prod) if mark is not None else None
            hold_days = ((as_of - first_entry).days
                         if (as_of and first_entry) else None)
            # check if this open position has a synthetic entry in its lots
            has_synthetic = any(o.get("synthetic", False) for o in ords if o["executed_qty"] > 0)
            res.open_positions.append({
                "isin": isin, "name": name, "ccy": ccy,
                "open_qty": round(open_qty, 4),
                "avg_cost_prod": round(avg_cost_prod, 4),
                "mark_prod": round(mark, 4) if mark is not None else None,
                "cost_prod": round(cost_prod, 2),
                "value_prod": round(open_qty * mark, 2) if mark is not None else None,
                "unreal_pnl_prod": round(unreal, 2) if unreal is not None else None,
                "unreal_ret_pct": round((unreal / cost_prod) * 100, 3) if (unreal is not None and cost_prod) else None,
                "first_entry_date": first_entry.strftime("%Y-%m-%d") if first_entry else None,
                "last_entry_date": last_entry.strftime("%Y-%m-%d") if last_entry else None,
                "holding_days": hold_days,
                "n_buys": sum(1 for o in ords if o["executed_qty"] > 0),
                "flips": flips,
                "marked": mark is not None,
                "synthetic_entry": has_synthetic,
            })

    if excess_sell_isins and recon_mode == "strict":
        res.warnings.append(
            f"{excess_sell_isins} titre(s) présentent des ventes excédant l'inventaire "
            "reconstruit (positions probablement ouvertes avant le début du carnet, ou "
            "ajustements/corporate actions). P&L réalisé clampé sur l'inventaire disponible.")
    elif excess_sell_isins and recon_mode == "t0_synthetic":
        res.warnings.append(
            f"{excess_sell_isins} titre(s) résiduels avec ventes excédantes après injection T0 "
            "(prix yfinance indisponible — P&L clampé pour ces titres).")

    res.synthetic_report = synthetic_report  # type: ignore[attr-defined]
    return res


def _quarter(dt: Optional[_dt.datetime]) -> Optional[str]:
    if not dt:
        return None
    return f"{dt.year}-T{(dt.month - 1) // 3 + 1}"


# ── Convenience loader from a manifest ─────────────────────────────────

def load_study_data(folder: str, files: Dict) -> dict:
    """Resolve manifest file roles against the study folder and load everything."""
    from .amc_prices import build_marks, auto_populate_store   # local import avoids circular dependency

    base = Path(folder)

    def _resolve(name: str) -> str:
        if not name:
            return ""
        p = base / name
        if p.exists():
            return str(p)
        hits = glob.glob(str(base / name))
        return hits[0] if hits else ""

    comp_path = _resolve(files.get("composition", ""))
    nav_path = _resolve(files.get("nav_timeseries", ""))
    order_paths = [pp for pp in (_resolve(o) for o in files.get("orders", [])) if pp]

    if not comp_path:
        raise ValueError("Fichier de composition (Def.txt) introuvable dans le dossier.")
    if not order_paths:
        raise ValueError("Carnet d'ordres introuvable dans le dossier.")

    composition = load_composition(comp_path)
    nav = load_nav(nav_path) if nav_path else []
    orders = load_orders(order_paths)
    as_of = composition.get("nav_date") or (orders[-1]["date"] if orders else None)

    # Auto-populate the price store for any component not yet cached.
    # This ensures Blocks H and I have price history on the very first study run.
    # Components already in the store are skipped (no re-download).
    auto_populate_store(composition["components"])

    # Populate marks from the centralised price store (parquet) + yfinance fallback.
    # The Def.txt has no individual stock prices — only weights and quantities.
    as_of_str = (as_of.strftime("%Y-%m-%d") if as_of else
                 _dt.date.today().isoformat())
    composition["marks"] = build_marks(
        composition["components"],
        as_of_str,
        composition.get("currency", "USD"),
    )

    return {
        "composition": composition,
        "nav": nav,
        "orders": orders,
        "as_of": as_of,
    }
