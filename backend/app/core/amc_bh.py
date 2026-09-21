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
    as_of: str | None = None,
) -> dict:
    """Référentiel Inertiel (Buy & Hold depuis l'émission).

    Returns:
        available, source, bh_nav, bh_perf_pct, actual_nav, actual_perf_pct,
        value_added_pct, nav_t0, n_positions, positions, methodology,
        [n_certs, total_aum_t0]  ← ajoutés quand source=termsheet
    """
    from .amc_controls import validate_nav
    nav = validate_nav(nav)
    if as_of:
        nav = [r for r in nav if r["date"] <= as_of]
    if not nav:
        return {"available": False, "error": "Aucune série NAV disponible"}

    t0_str     = str(nav[0]["date"])[:10]
    t0_dt      = _dt.datetime.strptime(t0_str, "%Y-%m-%d")
    nav_t0     = float(nav[0]["nav"])
    actual_nav = float(nav[-1]["nav"])
    now_str = str(nav[-1]["date"])[:10]

    if termsheet_positions:
        return _bh_from_termsheet(
            termsheet_positions, n_certs,
            nav_t0, actual_nav, t0_str, now_str, prod_ccy,
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
    from .amc_controls import price_at
    import pandas as pd
    positions, missing = [], []
    weight_sum = sum(float(p.get("weight_pct", 0)) / 100 for p in ts_positions)
    if not 0 < weight_sum <= 1.0001:
        raise ValueError("Le poids initial des actions doit être entre 0 et 100 %")
    cash_weight = max(0.0, 1.0 - weight_sum)
    weighted_return = cash_weight
    for pos in ts_positions:
        isin, name = pos.get("isin", ""), pos.get("name", "")
        weight = float(pos.get("weight_pct", 0)) / 100
        ccy = (pos.get("ccy") or prod_ccy).upper()
        if not isin or weight <= 0:
            continue
        series = None
        for key in (isin, name):
            try:
                frame = load_prices(key)
                price_at(frame["close"], t0_str)
                price_at(frame["close"], now_str)
                ccy = (frame.attrs.get("currency") or ccy).upper()
                series, source = frame["close"], "price_store"
                break
            except (ValueError, KeyError, OSError):
                continue
        if series is None:
            try:
                start = (pd.Timestamp(t0_str) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
                end = (pd.Timestamp(now_str) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                frame = yf.Ticker(_yf_symbol(isin, name)).history(start=start, end=end, auto_adjust=True)
                series, source = frame["Close"], "yfinance"
            except Exception:
                missing.append(isin)
                continue
        try:
            ratio = price_at(series, now_str) / price_at(series, t0_str)
            if not ccy or not prod_ccy:
                raise ValueError("Devise inconnue")
            if ccy != prod_ccy.upper():
                fx = get_fx_series(ccy, prod_ccy.upper())
                ratio *= price_at(fx, now_str) / price_at(fx, t0_str)
        except ValueError:
            missing.append(isin)
            continue
        weighted_return += weight * ratio
        positions.append({"isin": isin, "name": name, "currency": ccy,
            "initial_weight_pct": weight * 100, "qty_per_cert": pos.get("qty_per_cert", 0),
            "initial_qty_total": float(pos.get("qty_per_cert", 0)) * n_certs,
            "ts_fixing_price": pos.get("fixing_price", 0), "tr_source": source,
            "total_return_pct": round((ratio - 1) * 100, 2), "tr_ratio": ratio,
            "bh_contribution_pts": round(weight * nav_t0 * (ratio - 1), 4)})
    if missing:
        return {"available": False, "error": "Prix ou FX absents/périmés : " + ", ".join(missing),
                "missing_isins": missing, "positions": positions, "as_of": now_str}
    actual = (actual_nav / nav_t0 - 1) * 100
    passive = (weighted_return - 1) * 100
    return {"available": True, "source": "termsheet", "as_of": now_str,
        "period_start": t0_str, "period_end": now_str,
        "n_certs": n_certs, "total_aum_t0": nav_t0 * n_certs,
        "bh_nav": round(nav_t0 * weighted_return, 2), "bh_perf_pct": round(passive, 2),
        "actual_nav": actual_nav, "actual_perf_pct": round(actual, 2),
        "value_added_pct": round(actual - passive, 2), "nav_t0": nav_t0,
        "n_positions": len(positions), "n_price_warnings": 0, "positions": positions,
        "cash_weight_pct": round(cash_weight * 100, 4), "comparable_costs": False,
        "comparison_basis": "NAV nette / panier passif brut ; cash conservé sans rémunération",
        "methodology": "Même arrêté pour la NAV et le panier initial. Rendements totaux et FX à date. "
                       "Cash initial conservé. L'écart inclut les frais du gérant : ce n'est pas une mesure pure de talent."}
