"""FIFO pipeline — orchestration pure sans FastAPI.

Utilisé à la fois par l'endpoint REST (api/fifo.py) et l'étude AMC (amc_study.py).
"""
from __future__ import annotations

import collections
import datetime
import glob
import json
import os
from pathlib import Path
from typing import Optional

from .loader import load_orders
from .engine import reconstruct
from .marks import (
    get_marks_shares, get_marks_cert_units,
    fetch_t0_prices_from_earliest_lots, build_scaling_factors_from_termsheet,
)
from .nav import load_nav_csv, get_fixing_info, detect_nav_csv, build_initial_orders
from .schema import Order, ReconResult


# ── File detection ─────────────────────────────────────────────────────

def detect_order_files(folder: str) -> list[str]:
    """Find merged*.json first, then *Data*.json."""
    p = Path(folder)
    merged = sorted(glob.glob(str(p / "merged*.json")))
    if merged:
        return merged
    return sorted(glob.glob(str(p / "*Data*.json")))


def load_termsheet(folder: str, termsheet_path: str | None = None) -> list[dict] | None:
    """Load termsheet_positions.json — from explicit path or auto-detect in folder."""
    candidates = []
    if termsheet_path:
        candidates.append(termsheet_path)
    auto = os.path.join(folder, "termsheet_positions.json")
    if auto not in candidates:
        candidates.append(auto)
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


# ── Split-price correction ─────────────────────────────────────────────

def fix_carnet_splits(
    carnet_orders: list[Order],
    carnet_name_to_all_isins: dict,
    as_of: datetime.date,
) -> list[Order]:
    """Rescale carnet orders so the whole order history for each name is
    expressed in consistent, as-of-date share terms — driven entirely by
    yfinance's real corporate-action calendar (not price-ratio guessing,
    which breaks down when ticker resolution is imperfect: see Swissquote).

    Two patterns:
      1. Dual-ISIN reissue (e.g. SMCI Oct 2024): the same company name is held
         under 2+ ISINs with disjoint date ranges — the security's ISIN changed
         at the same time as a split. The older ISIN's orders are relabelled
         onto the newer one so the FIFO engine sees one continuous position.
      2. Same-ISIN split: for every order (after step 1's relabelling), every
         real split strictly after the order's own date and on/before `as_of`
         is multiplied in — qty × factor, price ÷ factor.

    `as_of` (not "today") bounds which splits apply: a split that happens
    after the carnet's last order must not be applied, because the marks
    fetched for valuation are themselves fetched as-of that same date.
    """
    import dataclasses
    from ..amc_prices import yf_symbol
    import yfinance as yf

    by_isin: dict[str, list[Order]] = collections.defaultdict(list)
    for o in carnet_orders:
        by_isin[o.isin].append(o)

    # ── Step 1: dual-ISIN reissue detection ────────────────────────────
    isin_aliases: dict[str, str] = {}
    for isins in carnet_name_to_all_isins.values():
        if len(isins) < 2:
            continue
        ranges = {
            isin: (min(o.date for o in by_isin[isin]), max(o.date for o in by_isin[isin]))
            for isin in isins if by_isin.get(isin)
        }
        if len(ranges) < 2:
            continue
        newest_isin = max(ranges, key=lambda i: ranges[i][0])
        for isin, (isin_min, isin_max) in ranges.items():
            if isin != newest_isin and isin_max < ranges[newest_isin][0]:
                isin_aliases[isin] = newest_isin

    relabelled = [
        dataclasses.replace(o, isin=isin_aliases[o.isin]) if o.isin in isin_aliases else o
        for o in carnet_orders
    ]

    # ── Step 2: per-order split correction (real yfinance calendar) ────
    symbol_cache: dict[str, str] = {}
    split_cache: dict[str, dict] = {}

    def _splits(symbol: str) -> dict:
        if symbol not in split_cache:
            try:
                actions = yf.Ticker(symbol).actions
                if actions is None or actions.empty or "Stock Splits" not in actions.columns:
                    split_cache[symbol] = {}
                else:
                    s = actions["Stock Splits"]
                    split_cache[symbol] = {d.date(): float(r) for d, r in s[s != 0].items()}
            except Exception:
                split_cache[symbol] = {}
        return split_cache[symbol]

    corrected = []
    for o in relabelled:
        if o.isin not in symbol_cache:
            symbol_cache[o.isin] = yf_symbol(o.isin, o.name)
        factor = 1.0
        for split_date, ratio in _splits(symbol_cache[o.isin]).items():
            if o.date < split_date <= as_of:
                factor *= ratio
        if factor != 1.0:
            corrected.append(dataclasses.replace(
                o, qty=o.qty * factor,
                price_local=o.price_local / factor,
                price_prod=o.price_prod / factor,
            ))
        else:
            corrected.append(o)
    return corrected


# ── Main pipeline ──────────────────────────────────────────────────────

def run_fifo_recon(
    folder: str,
    qty_mode: str = "shares",
    recon_mode: str = "t0_synthetic",
    prod_ccy: str = "USD",
    order_files: Optional[list[str]] = None,
    termsheet_path: Optional[str] = None,
) -> tuple[ReconResult, list[Order], dict]:
    """Run the full FIFO pipeline and return (ReconResult, carnet_orders, meta).

    carnet_orders: the corrected carnet Order list (without T0 initial orders),
    used by the AMC adapter to compute FX attribution and flips.

    meta: informational dict (fixing_date, n_certs, aliases, etc.).
    """
    # ── Order files ───────────────────────────────────────────────────
    file_paths = order_files or detect_order_files(folder)
    if not file_paths:
        raise ValueError(f"Aucun fichier carnet trouvé dans {folder}")
    full_paths = [
        f if os.path.isabs(f) else os.path.join(folder, f)
        for f in file_paths
    ]

    carnet_orders = load_orders(full_paths)
    if not carnet_orders:
        raise ValueError("Aucun ordre valide chargé")

    # ── Termsheet ─────────────────────────────────────────────────────
    termsheet = load_termsheet(folder, termsheet_path)

    # ── NAV CSV ───────────────────────────────────────────────────────
    nav_csv_path = detect_nav_csv(folder)
    nav_info: dict = {}
    initial_orders: list[Order] = []
    fixing_date = carnet_orders[0].date
    ts_isins: set[str] = set()

    # ISIN maps (alias detection + split-price correction)
    carnet_all_isins_set = {o.isin for o in carnet_orders}
    carnet_name_to_all_isins: dict[str, set] = collections.defaultdict(set)
    for o in carnet_orders:
        carnet_name_to_all_isins[o.name.lower().strip()].add(o.isin)

    if nav_csv_path and termsheet:
        try:
            nav_rows = load_nav_csv(nav_csv_path)
            fixing_date, n_certs, nav_initial = get_fixing_info(nav_rows)

            isin_aliases: dict[str, str] = {}
            alias_log: list[str] = []
            for e in termsheet:
                ts_isin = e["isin"]
                if ts_isin in carnet_all_isins_set:
                    continue
                name_key = e["name"].lower().strip()
                all_carnet = carnet_name_to_all_isins.get(name_key, set())
                candidates = all_carnet - {ts_isin}
                if len(candidates) == 1:
                    carnet_isin = next(iter(candidates))
                    isin_aliases[ts_isin] = carnet_isin
                    alias_log.append(f"{e['name']}: {ts_isin} → {carnet_isin}")

            initial_orders = build_initial_orders(
                termsheet, n_certs, nav_initial, fixing_date, prod_ccy, isin_aliases,
                qty_mode=qty_mode,
            )
            ts_isins = {o.isin for o in initial_orders}

            nav_info = {
                "fixing_date": fixing_date.isoformat(),
                "n_certs_initial": n_certs,
                "nav_initial": nav_initial,
                "initial_orders_built": len(initial_orders),
                "isin_aliases": alias_log,
            }
        except Exception as exc:
            import traceback; traceback.print_exc()
            nav_info = {"nav_csv_error": str(exc)}

    # ── Split-price correction ────────────────────────────────────────
    # The carnet always records real share executions (confirmed across every
    # fund studied so far, regardless of whether the term sheet/composition
    # snapshot is expressed in accounting units) — so this correction always
    # applies, independent of qty_mode. Bounded by as_of: a split after the
    # carnet's last order must not be applied, since marks are also fetched
    # as-of that same date.
    as_of = max(o.date for o in carnet_orders)
    carnet_orders = fix_carnet_splits(carnet_orders, carnet_name_to_all_isins, as_of)

    # ── Combine orders ────────────────────────────────────────────────
    all_orders = sorted(initial_orders + carnet_orders, key=lambda o: o.date)

    t0_date = all_orders[0].date
    isins = list({o.isin for o in all_orders})
    names = {o.isin: o.name for o in all_orders}
    components = [{"isin": i, "name": names[i], "currency": ""} for i in isins]

    # ── Pass 1 — collect earliest lots ───────────────────────────────
    result_p1 = reconstruct(
        all_orders, {}, as_of, prod_ccy,
        qty_mode=qty_mode,
        recon_mode="strict",
        t0_date=t0_date,
        t0_prices_prod={},
    )

    # ── T0 prices + marks ────────────────────────────────────────────────
    if qty_mode == "cert_units":
        # Per-ISIN scaling factor k = cert-unit price at T0 / stock price at T0.
        # Covers termsheet ISINs (from fixing_price) and non-termsheet ISINs added
        # later (fallback: earliest carnet lot, already in cert-unit space).
        scaling_factors, t0_cert_prices = build_scaling_factors_from_termsheet(
            termsheet or [], result_p1.earliest_lots, t0_date, prod_ccy,
        )
        # initial_orders' own price takes precedence — it already applied the
        # fixing_price/weight-NAV fallback, so it never leaves a T0-injected ISIN unpriced.
        t0_prices_prod = {**t0_cert_prices, **{o.isin: o.price_prod for o in initial_orders}}
        marks = get_marks_cert_units(components, scaling_factors, as_of.isoformat(), prod_ccy)
    else:
        t0_prices_prod = {o.isin: o.price_prod for o in initial_orders}
        non_ts_lots = {
            isin: lot for isin, lot in result_p1.earliest_lots.items()
            if isin not in ts_isins
        }
        if non_ts_lots:
            t0_prices_prod.update(fetch_t0_prices_from_earliest_lots(non_ts_lots, prod_ccy))
        marks = get_marks_shares(components, as_of.isoformat(), prod_ccy)

    # ── Pass 2 — final FIFO ───────────────────────────────────────────
    result = reconstruct(
        all_orders, marks, as_of, prod_ccy,
        qty_mode=qty_mode,
        recon_mode=recon_mode,
        t0_date=t0_date,
        t0_prices_prod=t0_prices_prod,
    )

    meta = {
        "folder": folder,
        "qty_mode": qty_mode,
        "recon_mode": recon_mode,
        "prod_ccy": prod_ccy,
        "as_of": as_of.isoformat(),
        "t0_date": t0_date.isoformat(),
        "order_count": len(carnet_orders),
        "initial_orders": len(initial_orders),
        "isin_count": len(isins),
        "termsheet_loaded": termsheet is not None,
        **nav_info,
    }

    return result, carnet_orders, meta
