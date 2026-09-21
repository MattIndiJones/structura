"""Block G — Brinson-Fachler Attribution (single-period).

Decomposes the portfolio's active return vs benchmark into three effects
(Brinson-Fachler, 1985):
  - Allocation   : did we overweight the right sectors?
  - Selection    : did we pick better stocks within each sector?
  - Interaction  : did we overweight exactly where we over-selected?

Portfolio weights = inception-window BUY orders (first 60 days, same as VAG).
Benchmark sector weights = ETF snapshot via yfinance, or static MSCI World fallback.
Benchmark sector returns = SPDR Select Sector ETF proxies (US bias noted).

The module also handles brinson_prices.json — a lightweight cache in the study
folder so Block G re-runs without re-fetching sector data from Yahoo Finance.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf


# ── Sector normalisation ──────────────────────────────────────────────

_SECTOR_NORMALIZE: Dict[str, str] = {
    # yfinance individual stock sectors
    "Technology":             "Technology",
    "Financial Services":     "Financials",
    "Financials":             "Financials",
    "Healthcare":             "Healthcare",
    "Health Care":            "Healthcare",
    "Industrials":            "Industrials",
    "Consumer Cyclical":      "Consumer Discret.",
    "Consumer Discretionary": "Consumer Discret.",
    "Consumer Defensive":     "Consumer Staples",
    "Consumer Staples":       "Consumer Staples",
    "Communication Services": "Communication",
    "Communication":          "Communication",
    "Energy":                 "Energy",
    "Basic Materials":        "Materials",
    "Materials":              "Materials",
    "Real Estate":            "Real Estate",
    "Utilities":              "Utilities",
    # yfinance ETF sectorWeightings keys (lowercase/underscore)
    "technology":             "Technology",
    "financial_services":     "Financials",
    "healthcare":             "Healthcare",
    "industrials":            "Industrials",
    "consumer_cyclical":      "Consumer Discret.",
    "consumer_defensive":     "Consumer Staples",
    "communication_services": "Communication",
    "energy":                 "Energy",
    "basic_materials":        "Materials",
    "realestate":             "Real Estate",
    "utilities":              "Utilities",
}

# SPDR Select Sector ETFs — US-market proxies for benchmark sector returns
_SECTOR_ETF_PROXIES: Dict[str, str] = {
    "Technology":       "XLK",
    "Financials":       "XLF",
    "Healthcare":       "XLV",
    "Energy":           "XLE",
    "Industrials":      "XLI",
    "Consumer Discret.":"XLY",
    "Consumer Staples": "XLP",
    "Communication":    "XLC",
    "Materials":        "XLB",
    "Real Estate":      "XLRE",
    "Utilities":        "XLU",
}

# Static benchmark sector weights (fallback when yfinance ETF data unavailable)
_STATIC_WEIGHTS: Dict[str, Dict[str, float]] = {
    "_default": {           # MSCI World ~2024-Q4
        "Technology":        0.232,
        "Financials":        0.161,
        "Healthcare":        0.118,
        "Industrials":       0.110,
        "Consumer Discret.": 0.108,
        "Consumer Staples":  0.071,
        "Communication":     0.068,
        "Energy":            0.052,
        "Materials":         0.038,
        "Real Estate":       0.024,
        "Utilities":         0.018,
    },
    "SPY": {                # S&P 500 ~2024-Q4
        "Technology":        0.319,
        "Financials":        0.131,
        "Healthcare":        0.124,
        "Consumer Discret.": 0.102,
        "Industrials":       0.087,
        "Communication":     0.086,
        "Consumer Staples":  0.057,
        "Energy":            0.038,
        "Real Estate":       0.025,
        "Materials":         0.023,
        "Utilities":         0.023,
    },
    "IVV": {                # S&P 500 (iShares)
        "Technology":        0.319,
        "Financials":        0.131,
        "Healthcare":        0.124,
        "Consumer Discret.": 0.102,
        "Industrials":       0.087,
        "Communication":     0.086,
        "Consumer Staples":  0.057,
        "Energy":            0.038,
        "Real Estate":       0.025,
        "Materials":         0.023,
        "Utilities":         0.023,
    },
}


# ── Price cache (brinson_prices.json) ─────────────────────────────────

def save_price_cache(folder: str, price_keys: List[str], amc_currency: str,
                     benchmark_ticker: str,
                     sector_map: Optional[Dict[str, str]] = None) -> None:
    """Persist price metadata + sector map to study folder."""
    if not folder:
        return
    cache = {
        "price_keys":       price_keys,
        "amc_currency":     amc_currency,
        "benchmark_ticker": benchmark_ticker,
        "sector_map":       sector_map or {},
        "saved_at":         datetime.utcnow().isoformat(),
    }
    try:
        Path(folder, "brinson_prices.json").write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def load_price_cache(folder: str) -> Optional[dict]:
    """Load brinson_prices.json from the study folder."""
    try:
        p = Path(folder, "brinson_prices.json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


# ── Main entry point ───────────────────────────────────────────────────

def compute_brinson(
    study_result: dict,
    prices: Dict[str, "pd.DataFrame"],
    benchmark_ticker: str,
    amc_currency: str = "CHF",
    folder: str = "",
    cached_sectors: Optional[Dict[str, str]] = None,
) -> dict:
    """Compute Brinson-Fachler single-period attribution.

    Parameters
    ----------
    study_result     : run_study() output (needs block_b.per_name + meta)
    prices           : {slug → DataFrame(close)} from load_prices()
    benchmark_ticker : benchmark ETF ticker (e.g. 'IWDA', 'SPY', 'ACWI')
    amc_currency     : base currency of the AMC NAV
    folder           : study folder — used to reconstruct inception weights
    cached_sectors   : precomputed {name: sector} to skip yfinance fetches
    """
    from .amc_prices import _slug as slug_fn, get_fx_series, get_currency

    meta    = study_result.get("meta", {})
    block_b = study_result.get("block_b", {})
    per_name = block_b.get("per_name", [])

    if not per_name:
        return {"available": False,
                "error": "Bloc B (per_name) requis pour l'attribution Brinson."}
    if not prices:
        return {"available": False,
                "error": "Aucun prix disponible — importez les séries dans l'onglet E."}

    _amc_ccy = (amc_currency or meta.get("currency") or "CHF").upper()

    # ── 1. Build aligned price matrix (mirrors VAG logic) ─────────────
    price_frames: Dict[str, pd.Series] = {}
    for row in per_name:
        isin = row.get("isin", "")
        name = row.get("name", "")
        key  = slug_fn(isin or name)
        if key not in prices:
            continue
        df = prices[key]
        if not (isinstance(df, pd.DataFrame) and "close" in df.columns):
            continue
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        s = s.loc[meta.get("nav_start_date"):meta.get("as_of") or meta.get("nav_current_date")]
        asset_ccy = (df.attrs.get("currency") or get_currency(key) or "").upper()
        from .amc_controls import price_at
        if not asset_ccy:
            return {"available": False, "error": f"Devise inconnue : {name}"}
        if asset_ccy != _amc_ccy:
            try:
                fx = get_fx_series(asset_ccy, _amc_ccy)
                s = s * pd.Series([price_at(fx, d) for d in s.index], index=s.index)
            except ValueError as exc:
                return {"available": False, "error": str(exc)}
        price_frames[name] = s

    if len(price_frames) < 2:
        return {"available": False,
                "error": "Moins de 2 séries de prix disponibles pour le Brinson."}

    _nav_start = meta.get("nav_start_date")
    _nav_end = meta.get("as_of") or meta.get("nav_current_date")
    if not _nav_start or not _nav_end:
        return {"available": False, "error": "Dates NAV requises."}
    price_df = pd.DataFrame(price_frames).sort_index().loc[_nav_start:_nav_end].dropna()
    if price_df.empty or (price_df.index[0] - pd.Timestamp(_nav_start)).days > 7 or (pd.Timestamp(_nav_end) - price_df.index[-1]).days > 7:
        return {"available": False, "error": "Prix incomplets aux bornes de la période NAV."}
    if len(price_df) < 20:
        return {"available": False,
                "error": f"Période trop courte ({len(price_df)} observations)."}

    available_names = list(price_df.columns)
    period_start = price_df.index[0].strftime("%Y-%m-%d")
    period_end   = price_df.index[-1].strftime("%Y-%m-%d")
    n_obs = len(price_df)

    # ── 2. Inception weights ──────────────────────────────────────────
    termsheet_positions = study_result.get("termsheet_basket") or []
    weights, weights_method = _build_inception_weights(
        available_names, per_name, "", termsheet_positions
    )

    cash_weight = 1.0 - float(weights.sum())
    if cash_weight > 1e-6:
        price_df["Liquidités"] = 1.0
        available_names.append("Liquidités")
        weights["Liquidités"] = cash_weight

    # ── 3. Per-holding returns (full period) ──────────────────────────
    first_px = price_df.iloc[0]
    last_px  = price_df.iloc[-1]
    holding_returns = (last_px / first_px - 1.0)
    port_return = float((weights * holding_returns).sum())

    # ── 4. Sector classification ──────────────────────────────────────
    from .amc_prices import _load_ticker_map
    from .amc_market_bundle import active_bundle
    local_bundle = active_bundle()
    ticker_map = {} if local_bundle is not None else _load_ticker_map()
    if local_bundle is not None:
        cached_sectors = local_bundle.sectors
        if any(n not in cached_sectors for n in available_names):
            raise ValueError("Classification sectorielle locale incomplète")
    if cached_sectors and len(cached_sectors) >= len(available_names) // 2:
        sector_map = dict(cached_sectors)
        # Fill missing names that may have been added since last cache
        missing_names = [n for n in available_names if n not in sector_map]
        if missing_names:
            new_sectors = _fetch_sectors(missing_names, per_name, ticker_map)
            sector_map.update(new_sectors)
    else:
        sector_map = _fetch_sectors(available_names, per_name, ticker_map)

    if cash_weight > 1e-6:
        sector_map["Liquidités"] = "Liquidités"

    # ── 5. Benchmark total return + sector data ───────────────────────
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        if benchmark_ticker != bundle.benchmark_key:
            raise ValueError("Benchmark absent du dossier de marché")
        sector_inputs = bundle.sector_data(period_start, period_end)
        bench_weights = dict(sector_inputs["weights"])
        bench_sector_returns = dict(sector_inputs["returns"])
        bench_return_raw = sum(bench_weights[s] * bench_sector_returns[s] for s in bench_weights)
        bench_weight_method = "Dossier local — poids au début de la période de référence"
    else:
        bench_return_raw = _series_total_return(benchmark_ticker, period_start, period_end)
        bench_weights, bench_weight_method = _get_benchmark_sector_weights(benchmark_ticker)
        bench_sector_returns = _get_sector_etf_returns(period_start, period_end)

    missing_sectors = [s for s, w in bench_weights.items() if w > 0 and s not in bench_sector_returns]
    if missing_sectors:
        return {"available": False, "error": "Proxies sectoriels manquants : " + ", ".join(missing_sectors)}
    if _amc_ccy != "USD":
        try:
            fx = get_fx_series("USD", _amc_ccy)
            change = price_at(fx, period_end) / price_at(fx, period_start)
            bench_sector_returns = {s: (1 + r) * change - 1 for s, r in bench_sector_returns.items()}
            if bench_return_raw is not None:
                bench_return_raw = (1 + bench_return_raw) * change - 1
        except ValueError as exc:
            return {"available": False, "error": str(exc)}
    # The sector benchmark must reconcile exactly with its own weighted returns.
    bench_return_total = sum(w * bench_sector_returns[s] for s, w in bench_weights.items() if w)
    _bench_return_estimated = bundle is None
    # ── 6. Aggregate portfolio by sector ─────────────────────────────
    all_sectors = set(sector_map.values()) | set(bench_weights.keys())
    sector_data: Dict[str, dict] = {
        s: {"w_p": 0.0, "sum_wr": 0.0, "holdings": []} for s in all_sectors
    }

    for name in available_names:
        sector = sector_map.get(name, "Non classifié")
        if sector not in sector_data:
            sector_data[sector] = {"w_p": 0.0, "sum_wr": 0.0, "holdings": []}
        w = float(weights.get(name, 0.0))
        r = float(holding_returns.get(name, 0.0))
        sector_data[sector]["w_p"]    += w
        sector_data[sector]["sum_wr"] += w * r
        sector_data[sector]["holdings"].append(name)

    for d in sector_data.values():
        d["r_p"] = (d["sum_wr"] / d["w_p"]) if d["w_p"] > 1e-9 else 0.0

    # ── 7. Brinson-Fachler by sector ──────────────────────────────────
    R_b = bench_return_total  # total benchmark return (Fachler correction)
    sector_rows = []
    eff_alloc = eff_selec = eff_inter = 0.0

    for s, d in sector_data.items():
        w_p = d["w_p"]
        r_p = d["r_p"]
        w_b = bench_weights.get(s, 0.0)
        r_b = 0.0 if s == "Liquidités" else bench_sector_returns.get(s, R_b)  # fallback to total bench return

        # Brinson-Fachler formulas
        allocation  = (w_p - w_b) * (r_b - R_b)
        selection   = w_b          * (r_p - r_b)
        interaction = (w_p - w_b)  * (r_p - r_b)
        total_eff   = allocation + selection + interaction

        eff_alloc += allocation
        eff_selec += selection
        eff_inter += interaction

        sector_rows.append({
            "sector":      s,
            "w_p":         round(w_p * 100, 2),
            "w_b":         round(w_b * 100, 2),
            "active_w":    round((w_p - w_b) * 100, 2),
            "r_p":         round(r_p * 100, 2),
            "r_b":         round(r_b * 100, 2),
            "r_diff":      round((r_p - r_b) * 100, 2),
            "allocation":  round(allocation * 100, 2),
            "selection":   round(selection * 100, 2),
            "interaction": round(interaction * 100, 2),
            "total":       round(total_eff * 100, 2),
            "n_holdings":  len(d["holdings"]),
            "holdings":    d["holdings"],
        })

    sector_rows.sort(key=lambda x: abs(x["total"]), reverse=True)
    active_return = port_return - R_b

    # ── 8. Per-title contributions ────────────────────────────────────
    title_contribs = [
        {
            "name":             name,
            "sector":           sector_map.get(name, "Non classifié"),
            "weight_pct":       round(float(weights.get(name, 0.0)) * 100, 2),
            "return_pct":       round(float(holding_returns.get(name, 0.0)) * 100, 2),
            "contribution_pct": round(
                float(weights.get(name, 0.0)) *
                float(holding_returns.get(name, 0.0)) * 100, 2
            ),
        }
        for name in available_names
    ]
    title_contribs.sort(key=lambda x: x["contribution_pct"], reverse=True)

    # ── NAV reconciliation ───────────────────────────────────────────
    nav_s = meta.get("nav_start_value")
    nav_c = meta.get("nav_current_value")
    nav_return_pct = None
    if nav_s and nav_c and float(nav_s) > 0:
        nav_return_pct = round((float(nav_c) / float(nav_s) - 1.0) * 100.0, 2)
    recon_gap_pct = (
        round(nav_return_pct - port_return * 100.0, 2)
        if nav_return_pct is not None else None
    )
    n_total_holdings = len(per_name)

    return {
        "available":          True,
        # ── Summary ───────────────────────────────────────────────────
        "port_return_pct":    round(port_return * 100, 2),
        "bench_return_pct":   round(R_b * 100, 2),
        "active_return_pct":  round(active_return * 100, 2),
        # ── NAV reconciliation ────────────────────────────────────────
        "nav_return_pct":     nav_return_pct,
        "recon_gap_pct":      recon_gap_pct,
        "n_total_holdings":   n_total_holdings,
        # ── Brinson effects ───────────────────────────────────────────
        "allocation_pct":     round(eff_alloc * 100, 2),
        "selection_pct":      round(eff_selec * 100, 2),
        "interaction_pct":    round(eff_inter * 100, 2),
        "check_pct":          round((eff_alloc + eff_selec + eff_inter) * 100, 2),
        # ── Detail ────────────────────────────────────────────────────
        "sector_rows":        sector_rows,
        "title_contributions": title_contribs,
        "top5":    title_contribs[:5],
        "bottom5": sorted(title_contribs,
                          key=lambda x: x["contribution_pct"])[:5],
        # ── Metadata ──────────────────────────────────────────────────
        "period_start":        period_start,
        "period_end":          period_end,
        "n_obs":               n_obs,
        "n_holdings":          len(available_names),
        "benchmark_ticker":           benchmark_ticker,
        "bench_weight_method":        bench_weight_method,
        "weights_method":             weights_method,
        "sector_map":                 sector_map,
        "bench_return_estimated":     _bench_return_estimated,
        "actual_benchmark_return_pct": None if bench_return_raw is None else round(100 * bench_return_raw, 4),
        "benchmark_proxy_gap_pct": None if bench_return_raw is None else round(100 * (R_b - bench_return_raw), 4),
        "analysis_type": "static_proxy",
        "methodology_note": ("Attribution statique du panier de référence ; rendements totaux, change et secteurs du dossier local. Benchmark équipondéré au début de cette période puis conservé. Cette comparaison brute ne mesure pas l’attribution dynamique du fonds géré." if bundle is not None else (
            "Simulation statique sur proxies ; elle ne mesure pas l’attribution du portefeuille réellement géré. Le benchmark affiché est reconstruit à partir des secteurs ; son écart au benchmark coté est conservé séparément. "
            "Brinson-Fachler single-période. "
            + (
                "Poids portefeuille : term sheet (poids exacts au fixing). "
                if weights_method == "termsheet" else
                "Poids portefeuille : composition d'émission (ordres BUY, fenêtre 60j). "
                if weights_method == "inception_orders" else
                "Poids portefeuille : composition actuelle (fallback — poids au fixing indisponibles). "
            )
            + "Poids benchmark : snapshot iShares actuel (supposé stable sur la période — "
            "raccourci méthodologique). "
            "Rendements sectoriels benchmark : ETFs SPDR (XLK/XLF/XLV…) — biais US/USD "
            "pour AMC hors US marché."
            + (" ⚠ Retour total benchmark non disponible via yfinance (benchmark composite ou "
               "ticker non coté) — estimé à partir des retours sectoriels ETF pondérés."
               if _bench_return_estimated else "")
        )),

    }


# ── Private helpers ────────────────────────────────────────────────────

def _build_inception_weights(
    available_names: List[str],
    per_name: List[dict],
    folder: str,
    termsheet_positions: Optional[List[dict]] = None,
) -> tuple:
    """Use documented initial weights, otherwise disclose current-weight approximation."""
    isin_to_name = {r.get("isin"): r.get("name") for r in per_name}
    if termsheet_positions:
        weight_map = {}
        for row in termsheet_positions:
            name = isin_to_name.get(row.get("isin")) or row.get("name", "")
            weight = float(row.get("weight_pct", 0)) / 100
            if weight < 0 or (weight > 0 and name not in available_names):
                raise ValueError("Panier initial incomplet ou poids invalides pour Brinson")
            weight_map[name] = weight_map.get(name, 0) + weight
        method = "termsheet"
    else:
        weight_map = {}
        for row in per_name:
            name = row.get("name", "")
            weight = float(row.get("weight") or 0)
            if name.upper() in {"CASH", "USD", "EUR", "CHF", "GBP", "JPY"}:
                continue
            if weight < 0 or (weight > 0 and name not in available_names):
                raise ValueError("Composition incomplète pour Brinson")
            weight_map[name] = weight_map.get(name, 0) + weight
        method = "current_composition"
    total = sum(weight_map.values())
    if not 0 < total <= 1.0001:
        raise ValueError("Poids documentés requis pour Brinson (somme comprise entre 0 et 100 %)")
    # Keep the residual cash allocation; do not inflate securities to 100%.
    return pd.Series({n: weight_map.get(n, 0.0) for n in available_names}), method


def _fetch_sectors(
    names: List[str],
    per_name: List[dict],
    ticker_map: dict,
) -> Dict[str, str]:
    """Fetch GICS sector for each holding via yfinance Ticker.info."""
    from .amc_prices import _slug as slug_fn

    # Build name → Yahoo ticker from the persisted ticker map
    name_to_ticker: Dict[str, str] = {}
    for row in per_name:
        isin = row.get("isin", "")
        name = row.get("name", "")
        key  = slug_fn(isin or name)
        ticker = ticker_map.get(key, "")
        if isinstance(ticker, dict):
            ticker = ticker.get("ticker", "")
        if ticker and name:
            name_to_ticker[name] = str(ticker)

    sector_map: Dict[str, str] = {}
    for name in names:
        ticker = name_to_ticker.get(name, "")
        if not ticker:
            sector_map[name] = "Non classifié"
            continue
        try:
            info = yf.Ticker(ticker).info
            raw = (info.get("sector") or
                   info.get("fundFamily") or
                   info.get("categoryName") or "")
            sector_map[name] = _SECTOR_NORMALIZE.get(raw, raw or "Non classifié")
        except Exception:
            sector_map[name] = "Non classifié"

    return sector_map


def _series_total_return(ticker: str, start: str, end: str) -> Optional[float]:
    """Total return of a single ticker over the period (0.05 = +5%).

    Returns None when the ticker cannot be fetched (composite IDs, network
    failure, no data) so callers can distinguish "0%" from "unknown".
    """
    # Composite UTI benchmark — blend component returns
    try:
        from .amc_benchmarks import COMPOSITE_BENCHMARKS
        comps = {b["id"]: b for b in COMPOSITE_BENCHMARKS}
        if ticker in comps:
            total = 0.0
            w_sum = 0.0
            for c in comps[ticker]["components"]:
                r = _series_total_return(c["ticker"], start, end)
                if r is None:
                    return None
                total += c["weight"] * r
                w_sum += c["weight"]
            return total / w_sum if w_sum > 0 else None
    except ImportError:
        pass

    try:
        raw = yf.download(ticker, start=start, end=(pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                          auto_adjust=True, progress=False)
        if raw.empty or len(raw) < 2:
            return None
        close = raw["Close"]
        if hasattr(close, "squeeze"):
            close = close.squeeze()
        close = close.dropna()
        if len(close) < 2:
            return None
        return float(close.iloc[-1] / close.iloc[0] - 1.0)
    except Exception:
        return None


def _get_benchmark_sector_weights(ticker: str) -> tuple:
    """Return (sector→weight dict, method string).
    Tries yfinance ETF sectorWeightings first, falls back to static table.
    """
    try:
        info = yf.Ticker(ticker).info
        sw = info.get("sectorWeightings") or []
        if isinstance(sw, list) and sw:
            result: Dict[str, float] = {}
            for item in sw:
                if isinstance(item, dict):
                    for raw_key, w in item.items():
                        normalized = _SECTOR_NORMALIZE.get(
                            raw_key, _SECTOR_NORMALIZE.get(
                                raw_key.lower(), raw_key
                            )
                        )
                        result[normalized] = result.get(normalized, 0.0) + float(w or 0.0)
            total = sum(result.values())
            if result and total > 0.01:
                return {k: v / total for k, v in result.items()}, f"yfinance ({ticker})"
        elif isinstance(sw, dict) and sw:
            result = {}
            for raw_key, w in sw.items():
                normalized = _SECTOR_NORMALIZE.get(raw_key, raw_key)
                result[normalized] = result.get(normalized, 0.0) + float(w or 0.0)
            total = sum(result.values())
            if result and total > 0.01:
                return {k: v / total for k, v in result.items()}, f"yfinance ({ticker})"
    except Exception:
        pass

    weights = _STATIC_WEIGHTS.get(
        ticker.upper(),
        _STATIC_WEIGHTS["_default"],
    )
    return dict(weights), f"Statique MSCI World 2024 ({ticker} non décomposé via yfinance)"


def _get_sector_etf_returns(start: str, end: str) -> Dict[str, float]:
    """Download SPDR sector ETF returns for the period in one batch call."""
    results: Dict[str, float] = {}
    etf_list = list(_SECTOR_ETF_PROXIES.values())

    try:
        df = yf.download(
            etf_list, start=start, end=(pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True, progress=False, group_by="ticker",
        )
        if df.empty:
            return results

        for sector, etf in _SECTOR_ETF_PROXIES.items():
            try:
                # Handle multi-level columns (group_by="ticker" produces (ticker, field))
                if isinstance(df.columns, pd.MultiIndex):
                    col = df[etf]["Close"].dropna()
                else:
                    col = df["Close"][etf].dropna() if etf in df.get("Close", df) else pd.Series()
                if len(col) >= 2:
                    results[sector] = float(col.iloc[-1] / col.iloc[0] - 1.0)
            except Exception:
                pass
    except Exception:
        pass

    return results
