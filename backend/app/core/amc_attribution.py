"""VAG Phase 2 — Attribution : timing des achats / sélection des sorties.

Principe
--------
Pour chaque ordre EXÉCUTÉ du carnet d'ordres, on mesure la contribution
de cette décision de trading par rapport au fait de ne rien avoir fait :

    contribution_i = qty_signée_i × (P_terminal_j − P_exécution_i)  [en devise AMC]

  • BUY  (qty > 0) : positif si P_terminal > P_exécution  (acheté avant une hausse)
  • SELL (qty < 0) : positif si P_terminal < P_exécution  (vendu avant une baisse)

Normalisation : on divise par l'AUM du portefeuille (meta.total_aum).

Décomposition
--------------
  timing  → contributions des ordres BUY
  exits   → contributions des ordres SELL
  vag     → timing + exits  (valeur ajoutée de gestion totale par le trading)
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .amc_orderbook import load_orders, apply_split_corrections
from .amc_prices import load_prices, get_fx_series, _slug


# ── prix terminal en devise AMC ───────────────────────────────────────

def _terminal_price(isin: str, name: str, amc_currency: str,
                    hint_ccy: str = "") -> float | None:
    """Retourne le dernier prix connu en devise AMC.

    hint_ccy : devise de l'actif tirée des ordres (fallback si absente du parquet).
    """
    key = _slug(isin or name)
    try:
        df = load_prices(key)
        if df.empty or "close" not in df.columns:
            return None
        s = df["close"].dropna()
        if s.empty:
            return None
        price_local = float(s.iloc[-1])
        # Priorité: attribut du parquet, puis hint depuis les ordres
        asset_ccy = (df.attrs.get("currency") or hint_ccy or "").upper()
        if asset_ccy and asset_ccy != amc_currency:
            fx = get_fx_series(asset_ccy, amc_currency)
            if not fx.empty:
                return price_local * float(fx.iloc[-1])
        return price_local
    except Exception:
        return None


def _pct(value: float, aum: float) -> float:
    if aum == 0:
        return 0.0
    return round(value / aum * 100, 4)


# ── point d'entrée public ─────────────────────────────────────────────

def compute_attribution(
    folder: str,
    study_result: dict,
    amc_currency: str = "CHF",
) -> dict:
    """Décompose le VAG en effets timing (achats) et sélection des sorties (ventes).

    Paramètres
    ----------
    folder        : chemin vers le dossier de l'étude (contient les JSON d'ordres)
    study_result  : résultat complet de run_study() — fournit l'AUM de référence
    amc_currency  : devise du produit (ex: "CHF")

    Retour
    ------
    {timing_pct, exits_pct, vag_pct, per_underlying[], top_trades[], waterfall[]}
    """
    amc_currency = (amc_currency or "CHF").upper()

    # ── 1. Charger les ordres depuis le dossier ───────────────────────
    base = Path(folder)
    paths: list[str] = []
    seen: set[str] = set()
    for p in list(base.glob("* Data*.json")) + list(base.glob("*Data*.json")) + list(base.glob("merged-*.json")):
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            paths.append(str(p))

    if not paths:
        return {"error": f"Aucun fichier d'ordres JSON trouvé dans {folder}"}

    all_orders = load_orders(paths)
    orders = [o for o in all_orders if o.get("state") == "Done"]
    if orders:
        as_of = max(o["date"] for o in orders if o.get("date") is not None)
        orders = apply_split_corrections(orders, as_of)
    if not orders:
        return {"error": "Aucun ordre exécuté trouvé."}

    # ── 2. AUM de référence (dénominateur des %) ─────────────────────
    # Priorité : meta.total_aum > nav × outstanding > somme buy notionals
    meta = study_result.get("meta", {}) or {}
    aum = float(meta.get("total_aum") or 0)
    if aum <= 0:
        nav_val     = float(meta.get("nav_current_value") or 0)
        outstanding = float(meta.get("outstanding") or 0)
        if nav_val > 0 and outstanding > 0:
            aum = nav_val * outstanding
    if aum <= 0:
        # Fallback : somme brute des notionals BUY
        aum = sum(
            float(o.get("notional_prod") or 0)
            for o in orders
            if (o.get("side") or "BUY") == "BUY"
        )
    if aum <= 0:
        return {"error": "Impossible de déterminer l'AUM du portefeuille."}

    # ── 3. Regrouper par sous-jacent ──────────────────────────────────
    # executed_qty est SIGNÉ dans le carnet d'ordres :
    # positif = achat, négatif = vente. On utilise directement ce signe.
    from collections import defaultdict
    trades_by_key: dict[str, list[dict]] = defaultdict(list)

    for o in orders:
        isin  = o.get("isin", "") or ""
        name  = o.get("name", "") or ""
        key   = isin or name
        if not key:
            continue
        qty_signed = float(o.get("executed_qty") or 0)   # déjà signé (+BUY, −SELL)
        if qty_signed == 0:
            continue
        side = "BUY" if qty_signed > 0 else "SELL"
        price_prod = float(o.get("price_prod") or 0)
        if price_prod <= 0:
            continue
        asset_ccy = (o.get("ccy") or "").upper()   # devise de l'actif depuis l'ordre

        dt = o.get("date")
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]

        trades_by_key[key].append({
            "date":       date_str,
            "isin":       isin,
            "name":       name,
            "side":       side,
            "qty":        qty_signed,
            "price_prod": price_prod,
            "asset_ccy":  asset_ccy,   # ← pour la conversion FX du prix terminal
        })

    # ── 4. Attribution par sous-jacent ────────────────────────────────
    per_underlying: list[dict] = []
    all_contrib: list[dict] = []
    total_timing = 0.0
    total_exits  = 0.0

    for key, trades in trades_by_key.items():
        isin      = trades[0]["isin"]
        name      = trades[0]["name"]
        hint_ccy  = trades[0].get("asset_ccy", "")
        pt        = _terminal_price(isin, name, amc_currency, hint_ccy=hint_ccy)
        has_price = pt is not None

        timing_val = 0.0
        exits_val  = 0.0

        for t in trades:
            if not has_price:
                continue
            qty  = t["qty"]        # signé (+BUY, −SELL)
            pi   = t["price_prod"] # prix d'exécution en devise AMC
            contribution = qty * (pt - pi)

            rec = {
                "date":             t["date"],
                "name":             name,
                "isin":             isin,
                "side":             t["side"],
                "qty":              round(qty, 4),
                "price_exec":       round(pi, 4),
                "price_terminal":   round(pt, 4),
                "contribution_pct": _pct(contribution, aum),
            }

            if t["side"] == "BUY":
                timing_val += contribution
                rec["bucket"] = "timing"
            else:
                exits_val += contribution
                rec["bucket"] = "exits"

            all_contrib.append(rec)

        timing_pct = _pct(timing_val, aum)
        exits_pct  = _pct(exits_val,  aum)

        total_timing += timing_val
        total_exits  += exits_val

        per_underlying.append({
            "name":       name,
            "isin":       isin,
            "timing_pct": timing_pct,
            "exits_pct":  exits_pct,
            "vag_pct":    round(timing_pct + exits_pct, 4),
            "has_price":  has_price,
        })

    per_underlying.sort(key=lambda x: abs(x["vag_pct"]), reverse=True)

    top_trades = sorted(all_contrib, key=lambda x: abs(x["contribution_pct"]), reverse=True)[:15]

    timing_pct_total = _pct(total_timing, aum)
    exits_pct_total  = _pct(total_exits,  aum)
    vag_pct_total    = round(timing_pct_total + exits_pct_total, 4)

    # ── 5. Waterfall ──────────────────────────────────────────────────
    waterfall = [
        {
            "label": "Timing achats",
            "description": "Valeur ajoutée par le moment choisi pour acheter",
            "value": round(timing_pct_total, 4),
            "type": "timing",
        },
        {
            "label": "Sélection sorties",
            "description": "Valeur ajoutée par le moment choisi pour vendre",
            "value": round(exits_pct_total, 4),
            "type": "exits",
        },
        {
            "label": "Valeur Ajoutée de Gestion (VAG)",
            "description": "Somme des deux effets (timing achats + sélection sorties)",
            "value": vag_pct_total,
            "type": "total",
        },
    ]

    dates = [t["date"] for trades in trades_by_key.values() for t in trades]
    t_min = min(dates) if dates else ""
    t_max = max(dates) if dates else ""

    return {
        "amc_currency":    amc_currency,
        "aum":             round(aum, 0),
        "period_start":    t_min,
        "period_end":      t_max,
        "n_orders":        len(orders),
        "n_underlyings":   len(per_underlying),
        "timing_pct":      round(timing_pct_total, 4),
        "exits_pct":       round(exits_pct_total, 4),
        "vag_pct":         vag_pct_total,
        "per_underlying":  per_underlying,
        "top_trades":      top_trades,
        "waterfall":       waterfall,
    }
