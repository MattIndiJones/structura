"""Référentiel Inertiel — Buy & Hold depuis la date d'émission.

compute_bh() compare la NAV réelle à un portefeuille de référence passif maintenu
sans aucun trade depuis le lancement.

Source de la composition initiale (par ordre de priorité) :
  1. termsheet_positions  — poids et quantités issus de la term sheet (source de vérité).
     → Immune aux problèmes de splits (utilise le poids %, pas le prix × qty).
  2. Identité comptable   — qty_initiale = position_actuelle + ventes − achats réels
     → Fallback quand la TS n'est pas renseignée dans le manifeste.

VAG = performance réelle − performance Référentiel Inertiel
  > 0 → le gérant a créé de la valeur
  < 0 → l'inertie aurait été préférable

n_certs : nombre de certificats à l'émission (variable configurable, défaut 75 000).
          N'affecte que les valeurs absolues affichées — les % sont indépendants.
"""
from __future__ import annotations

import datetime as _dt
import math
from collections import defaultdict
from typing import Optional

import yfinance as yf

from .amc_orderbook import _fetch_t0_price
from .amc_prices import yf_symbol as _yf_symbol, load_prices, get_fx_series


def _order_date_key(o: dict) -> str:
    d = o.get("date")
    if d is None:
        return "9999-99-99"
    if hasattr(d, "strftime"):
        try:
            return d.strftime("%Y-%m-%d")
        except Exception:
            return str(d)[:10]
    return str(d)[:10]


def compute_bh(
    nav: list[dict],
    prod_ccy: str = "",
    termsheet_positions: list[dict] | None = None,
    n_certs: int = 75_000,
    orders: list[dict] | None = None,
    composition: dict | None = None,
) -> dict:
    """Référentiel Inertiel (Buy & Hold depuis l'émission).

    Returns:
        available, source, bh_nav, bh_perf_pct, actual_nav, actual_perf_pct,
        value_added_pct, nav_t0, n_positions, positions, methodology,
        [n_certs, total_aum_t0]  ← ajoutés quand source=termsheet
    """
    if not nav:
        return {"available": False, "error": "Aucune série NAV disponible"}

    t0_str     = str(nav[0]["date"])[:10]
    t0_dt      = _dt.datetime.strptime(t0_str, "%Y-%m-%d")
    nav_t0     = float(nav[0]["nav"])
    actual_nav = float(nav[-1]["nav"])
    now_str    = _dt.datetime.now().strftime("%Y-%m-%d")

    if termsheet_positions:
        return _bh_from_termsheet(
            termsheet_positions, n_certs,
            nav_t0, actual_nav, t0_str, now_str, prod_ccy,
        )
    if orders is not None and composition is not None:
        return _bh_accounting_identity(
            orders, composition,
            nav_t0, actual_nav, t0_str, t0_dt, now_str, prod_ccy,
        )
    return {"available": False, "error": "Aucune source disponible (renseignez params.termsheet_positions)"}


# ── Méthode 1 : Term sheet (méthode primaire) ─────────────────────────────────

def _bh_from_termsheet(
    ts_positions: list[dict],
    n_certs: int,
    nav_t0: float,
    actual_nav: float,
    t0_str: str,
    now_str: str,
    prod_ccy: str,
) -> dict:
    """B&H basé sur les poids de la term sheet.

    Utilise weight_pct directement → immunisé contre les divergences de prix
    liées aux splits entre la date de fixing TS et les données yfinance.
    n_certs ne sert qu'à l'affichage des valeurs absolues.
    """
    positions: list[dict] = []
    weighted_return = 0.0   # Σ(w_i × TR_i)
    total_weight    = 0.0   # Σ(w_i) — permet de normaliser si cash exclu

    for pos in ts_positions:
        isin = pos.get("isin", "")
        if not isin:
            continue
        name   = pos.get("name", isin)
        ccy    = (pos.get("ccy") or prod_ccy or "USD").upper()
        weight = float(pos.get("weight_pct", 0)) / 100.0
        if weight <= 0:
            continue
        qty_per_cert = float(pos.get("qty_per_cert", 0))

        # Total return — prix source : store centralisé puis yfinance en fallback
        tr_local: float = 1.0
        tr_source       = "unavailable"

        # 1. Price store (parquet — même source que Blocs H et I)
        for _key in [isin, name]:
            if not _key:
                continue
            try:
                import pandas as _pd
                df_store = load_prices(_key)
                df_store.index = _pd.to_datetime(df_store.index).tz_localize(None)
                t0_ts  = _pd.Timestamp(t0_str)
                now_ts = _pd.Timestamp(now_str)
                before_t0  = df_store[df_store.index <= t0_ts]["close"]
                before_now = df_store[df_store.index <= now_ts]["close"]
                if not before_t0.empty and not before_now.empty:
                    p_t0  = float(before_t0.iloc[-1])
                    p_now = float(before_now.iloc[-1])
                    if p_t0 > 0 and math.isfinite(p_t0) and math.isfinite(p_now):
                        tr_local  = p_now / p_t0
                        tr_source = "price_store"
                        break
            except Exception:
                continue

        # 2. Fallback yfinance
        if tr_source == "unavailable":
            sym = _yf_symbol(isin, name)
            try:
                hist = yf.Ticker(sym).history(start=t0_str, end=now_str, auto_adjust=True)
                close = hist["Close"].dropna() if len(hist) >= 2 else hist["Close"]
                if len(close) >= 2:
                    p_t0  = float(close.iloc[0])
                    p_now = float(close.iloc[-1])
                    if p_t0 > 0 and math.isfinite(p_t0) and math.isfinite(p_now):
                        tr_local  = p_now / p_t0
                        tr_source = "yfinance" if sym == isin else f"yfinance_search({sym})"
            except Exception:
                pass

        # Correction FX — get_fx_series (même source que build_marks)
        tr_prod  = tr_local
        pc_upper = (prod_ccy or "").upper()
        if ccy != pc_upper and pc_upper and tr_source != "unavailable":
            try:
                import pandas as _pd
                fx_s = get_fx_series(ccy, pc_upper)
                if not fx_s.empty:
                    t0_ts  = _pd.Timestamp(t0_str)
                    now_ts = _pd.Timestamp(now_str)
                    fx_t0_val = float(fx_s[fx_s.index <= t0_ts].iloc[-1]) if not fx_s[fx_s.index <= t0_ts].empty else None
                    fx_now    = float(fx_s[fx_s.index <= now_ts].iloc[-1]) if not fx_s[fx_s.index <= now_ts].empty else None
                    if fx_t0_val and fx_now and fx_t0_val > 0:
                        tr_prod = tr_local * (fx_now / fx_t0_val)
            except Exception:
                pass

        weighted_return += weight * tr_prod
        total_weight    += weight

        # Sanitize tr_prod: replace NaN/Inf with 1.0 (no-return placeholder)
        if not math.isfinite(tr_prod):
            tr_prod   = 1.0
            tr_source = "unavailable"

        positions.append({
            "isin":                isin,
            "name":                name,
            "currency":            ccy,
            "initial_weight_pct":  round(weight * 100, 4),
            "qty_per_cert":        round(qty_per_cert, 6),
            "initial_qty_total":   round(qty_per_cert * n_certs, 4),
            "ts_fixing_price":     round(float(pos.get("fixing_price", 0)), 4),
            "total_return_pct":    round((tr_prod - 1) * 100, 2),
            "tr_ratio":            round(tr_prod, 6),
            "tr_source":           tr_source,
            "bh_contribution_pts": round(weight * nav_t0 * (tr_prod - 1), 4),
        })

    if not positions or total_weight <= 0:
        return {"available": False, "error": "Données de prix insuffisantes (term sheet)"}

    # Normalisation sur le poids equity (exclut le cash s'il n'est pas dans la liste)
    bh_perf_raw     = weighted_return / total_weight   # ratio total return normalisé
    # Guard against NaN/Inf (e.g. yfinance returned NaN close for some positions)
    if not math.isfinite(bh_perf_raw):
        bh_perf_raw = 1.0
    bh_perf_pct     = round((bh_perf_raw - 1) * 100, 2)
    bh_nav          = round(nav_t0 * bh_perf_raw, 2)

    actual_perf_pct = round((actual_nav / nav_t0 - 1) * 100, 2)
    value_added_pct = round(actual_perf_pct - bh_perf_pct, 2)

    positions.sort(key=lambda x: x.get("bh_contribution_pts", 0), reverse=True)

    return {
        "available":           True,
        "source":              "termsheet",
        "n_certs":             n_certs,
        "total_aum_t0":        round(nav_t0 * n_certs, 0),
        "bh_nav":              bh_nav,
        "bh_perf_pct":         bh_perf_pct,
        "actual_nav":          round(actual_nav, 2),
        "actual_perf_pct":     actual_perf_pct,
        "value_added_pct":     value_added_pct,
        "nav_t0":              round(nav_t0, 2),
        "n_positions":         len(positions),
        "n_price_warnings":    sum(1 for p in positions if p.get("tr_source") == "unavailable"),
        "positions":           positions,
        "methodology": (
            f"Référentiel Inertiel basé sur la term sheet ({len(positions)} sous-jacents, "
            f"{n_certs:,} certificats à l'émission). "
            "Performance = Σ(poids_TS × retour_total_yfinance) / Σ(poids_TS). "
            "Prix ajustés dividendes inclus (total return). "
            "FX intégré pour les actifs hors devise produit. "
            "VAG = performance AMC réelle − performance Référentiel Inertiel."
        ),
    }


# ── Méthode 2 : Identité comptable (fallback) ─────────────────────────────────

def _bh_accounting_identity(
    orders: list[dict],
    composition: dict,
    nav_t0: float,
    actual_nav: float,
    t0_str: str,
    t0_dt: _dt.datetime,
    now_str: str,
    prod_ccy: str,
) -> dict:
    """Fallback : reconstruction via identité comptable.

    qty_initiale = position_actuelle + Σ(ventes) − Σ(achats réels)

    Moins fiable après 2+ ans de gestion active car les positions ajoutées
    par rebalancing apparaissent aussi comme des ventes en excès.
    Renseignez params.termsheet_positions pour une reconstruction exacte.
    """
    real_buys:  dict[str, float] = defaultdict(float)
    real_sells: dict[str, float] = defaultdict(float)
    stock_meta: dict[str, dict]  = {}

    for o in orders:
        if o.get("state") != "Done":
            continue
        if (o.get("id") or "").startswith("__synthetic_"):
            continue
        isin = o.get("isin", "")
        if not isin:
            continue
        stock_meta.setdefault(isin, {
            "name": o.get("name", ""),
            "ccy":  o.get("currency", prod_ccy),
        })
        qty = float(o.get("executed_qty") or o.get("qty", 0) or 0)
        if o.get("side") == "BUY":
            real_buys[isin] += qty
        else:
            real_sells[isin] += qty

    current_qty: dict[str, float] = {}
    marks: dict[str, float] = composition.get("marks", {})

    for c in composition.get("components", []):
        isin = c.get("isin", "")
        if not isin:
            continue
        current_qty[isin] = float(c.get("position", 0) or 0)
        meta = stock_meta.setdefault(isin, {})
        if not meta.get("name"):
            meta["name"] = c.get("name", "")
        if not meta.get("ccy"):
            meta["ccy"] = c.get("currency", prod_ccy)

    all_isins = set(real_buys) | set(real_sells) | set(current_qty)
    initial_qtys: dict[str, float] = {}
    for isin in all_isins:
        init = current_qty.get(isin, 0.0) + real_sells.get(isin, 0.0) - real_buys.get(isin, 0.0)
        if init > 0:
            initial_qtys[isin] = init

    if not initial_qtys:
        return {
            "available": False,
            "error": (
                "Impossible de reconstruire le portefeuille initial via l'identité comptable. "
                "Renseignez params.termsheet_positions dans le manifeste pour une reconstruction exacte."
            ),
        }

    positions: list[dict] = []
    total_initial_value   = 0.0

    for isin, init_qty in initial_qtys.items():
        m    = stock_meta.get(isin, {})
        name = m.get("name", isin)
        ccy  = m.get("ccy", prod_ccy) or prod_ccy

        real_orders = sorted(
            [o for o in orders
             if o.get("isin") == isin
             and not (o.get("id") or "").startswith("__synthetic_")
             and o.get("state") == "Done"],
            key=_order_date_key,
        )
        fb_price = float(real_orders[0].get("price", 0)) if real_orders else None
        fb_fx    = float(real_orders[0].get("fx", 1.0))  if real_orders else None
        fb_date  = real_orders[0].get("date")             if real_orders else None

        price_t0_local, fx_t0, source_t0 = _fetch_t0_price(
            isin, ccy, prod_ccy, t0_dt, fb_price, fb_fx,
            proxy_order_date=fb_date,
        )
        if source_t0 == "pre_ipo":
            continue
        if not price_t0_local or price_t0_local <= 0:
            continue
        fx_t0 = fx_t0 or 1.0

        initial_value_prod   = init_qty * price_t0_local * fx_t0
        total_initial_value += initial_value_prod

        tr_local: Optional[float] = None
        tr_source = "unavailable"
        try:
            hist = yf.Ticker(isin).history(start=t0_str, end=now_str, auto_adjust=True)
            close = hist["Close"].dropna() if len(hist) >= 2 else hist["Close"]
            if len(close) >= 2:
                p_t0_adj  = float(close.iloc[0])
                p_now_adj = float(close.iloc[-1])
                if p_t0_adj > 0 and math.isfinite(p_t0_adj) and math.isfinite(p_now_adj):
                    tr_local  = p_now_adj / p_t0_adj
                    tr_source = "yfinance_adjusted"
        except Exception:
            pass

        if tr_local is None:
            mark_prod = marks.get(isin)
            if mark_prod and mark_prod > 0:
                price_t0_prod = price_t0_local * fx_t0
                if price_t0_prod > 0:
                    tr_local  = mark_prod / price_t0_prod
                    tr_source = "mark_ratio"
        if tr_local is None:
            tr_local  = 1.0
            tr_source = "flat_fallback"

        tr_prod = tr_local
        if ccy.upper() != prod_ccy.upper() and tr_source == "yfinance_adjusted":
            try:
                pair    = f"{ccy.upper()}{prod_ccy.upper()}=X"
                fx_hist = yf.Ticker(pair).history(start=t0_str, end=now_str, auto_adjust=False)
                fx_close = fx_hist["Close"].dropna() if len(fx_hist) >= 2 else fx_hist["Close"]
                if len(fx_close) >= 2:
                    fx_t0_chk = float(fx_close.iloc[0])
                    fx_now    = float(fx_close.iloc[-1])
                    if fx_t0_chk > 0 and math.isfinite(fx_t0_chk) and math.isfinite(fx_now):
                        tr_prod = tr_local * (fx_now / fx_t0_chk)
            except Exception:
                tr_prod = tr_local

        coherence_warning: Optional[str] = None
        mark_now = marks.get(isin)
        if (
            fb_price and fb_fx and fb_price > 0
            and mark_now and mark_now > 0
            and tr_source == "yfinance_adjusted"
        ):
            fb_price_prod = float(fb_price) * float(fb_fx)
            if fb_price_prod > 0:
                tr_independent = float(mark_now) / fb_price_prod
                ratio = max(tr_prod, tr_independent) / max(min(tr_prod, tr_independent), 1e-9)
                if ratio > 7.0:
                    coherence_warning = (
                        f"Retour yfinance ({(tr_prod-1)*100:+.0f}%) vs "
                        f"estimation carnet ({(tr_independent-1)*100:+.0f}%) "
                        f"— ratio {ratio:.1f}× (prix yfinance T0 potentiellement incorrect)"
                    )

        pos: dict = {
            "isin":                 isin,
            "name":                 name,
            "currency":             ccy,
            "initial_weight_pct":   0.0,   # calculé plus bas
            "initial_qty":          round(init_qty, 4),
            "initial_price_t0":     round(price_t0_local, 4),
            "initial_price_source": source_t0,
            "fx_t0":                round(fx_t0, 6),
            "initial_value_prod":   round(initial_value_prod, 2),
            "total_return_pct":     round((tr_prod - 1) * 100, 2),
            "tr_ratio":             round(tr_prod, 6),
            "tr_source":            tr_source,
            "bh_contribution_pts":  0.0,   # calculé plus bas
        }
        if coherence_warning:
            pos["coherence_warning"] = coherence_warning
        positions.append(pos)

    if not positions or total_initial_value <= 0:
        return {"available": False, "error": "Données de prix insuffisantes pour le B&H (identité comptable)"}

    bh_nav = 0.0
    for p in positions:
        weight = p["initial_value_prod"] / total_initial_value
        p["initial_weight_pct"]  = round(weight * 100, 2)
        contrib = weight * nav_t0 * (p["tr_ratio"] - 1)
        p["bh_contribution_pts"] = round(contrib, 2)
        bh_nav += weight * nav_t0 * p["tr_ratio"]

    bh_perf_pct     = round((bh_nav    / nav_t0 - 1) * 100, 2)
    actual_perf_pct = round((actual_nav / nav_t0 - 1) * 100, 2)
    value_added_pct = round(actual_perf_pct - bh_perf_pct, 2)

    positions.sort(key=lambda x: x.get("bh_contribution_pts", 0), reverse=True)

    return {
        "available":           True,
        "source":              "accounting_identity",
        "bh_nav":              round(bh_nav, 2),
        "bh_perf_pct":         bh_perf_pct,
        "actual_nav":          round(actual_nav, 2),
        "actual_perf_pct":     actual_perf_pct,
        "value_added_pct":     value_added_pct,
        "nav_t0":              round(nav_t0, 2),
        "n_positions":         len(positions),
        "n_price_warnings":    sum(1 for p in positions if p.get("coherence_warning")),
        "total_initial_value": round(total_initial_value, 2),
        "positions":           positions,
        "methodology": (
            "⚠ Portefeuille initial reconstitué via l'identité comptable (term sheet non renseignée) : "
            "qty_initiale = position_actuelle + ventes − achats réels. "
            "Après 2+ ans de gestion active, peut inclure des positions absentes du panier initial. "
            "Renseignez params.termsheet_positions dans le manifeste pour une reconstruction exacte. "
            "Performance en prix ajustés yfinance (dividendes inclus). "
            "VAG = performance AMC réelle − performance Référentiel Inertiel."
        ),
    }
