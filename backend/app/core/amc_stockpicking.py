"""Block I — Stock Picking Score.

Measures whether the manager selects genuinely better stocks than their
investment universe by comparing the forward return of each purchased
security against the benchmark return over 1M, 3M, 6M, and 12M horizons.

Alpha_i(h) = Return(title, h) - Return(benchmark, h)

Score 0-100 is a weighted composite of:
  40% — alpha magnitude (mean alpha across horizons)
  35% — success rate (% purchases with positive alpha)
  25% — information ratio (mean_alpha / std_alpha)

Prices are sourced from the parquet store populated by the VAG module.
Benchmark prices are fetched via yfinance with an in-memory cache.
Open positions use the last available price in the store (latent alpha).
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

import numpy as np
import pandas as pd

from .amc_prices import load_prices

_HORIZONS: dict[str, int] = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
_HORIZON_WEIGHTS: dict[str, float] = {"1M": 0.15, "3M": 0.25, "6M": 0.30, "12M": 0.30}
_MIN_TRADING_DAYS = 15   # minimum days available for a horizon to be considered valid

_bench_cache: dict[str, pd.Series] = {}


# ── helpers ────────────────────────────────────────────────────────────────

def _load_series(isin: str, name: str = "") -> Optional[pd.Series]:
    """Load stored close-price series from the centralised price store."""
    for key in [isin, name]:
        if not key:
            continue
        try:
            df = load_prices(key)
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df["close"]
        except Exception:
            continue
    return None


def _forward_return(series: pd.Series, buy_date: pd.Timestamp,
                    n_days: int) -> Optional[float]:
    """Return (price_at_n_days / price_at_buy) - 1, or None if data insufficient.

    Requires exactly n_days rows after buy_date. No fallback to current price —
    using avail.iloc[-1] as proxy for all longer horizons produces identical
    returns across 6M/12M for recent trades, inflating n per horizon artificially.
    """
    avail = series.loc[series.index >= buy_date].dropna()
    if len(avail) < n_days + 1:
        return None
    buy_price = float(avail.iloc[0])
    if buy_price <= 0 or math.isnan(buy_price):
        return None
    fwd_price = float(avail.iloc[n_days])
    if math.isnan(fwd_price):
        return None
    return fwd_price / buy_price - 1.0


def _blend_composite(components: list[dict]) -> Optional[pd.Series]:
    """Download and blend multiple tickers into a weighted composite series."""
    try:
        import yfinance as yf
        parts = []
        weights = []
        for c in components:
            raw = yf.download(c["ticker"], period="5y", auto_adjust=True, progress=False)
            if raw.empty:
                continue
            close = raw["Close"]
            if hasattr(close, "squeeze"):
                close = close.squeeze()
            close.index = pd.to_datetime(close.index).tz_localize(None)
            parts.append(close)
            weights.append(c["weight"])
        if not parts:
            return None
        df = pd.concat(parts, axis=1).dropna()
        normed = df.divide(df.iloc[0])
        w = np.array(weights[: len(parts)])
        w = w / w.sum()
        blended = normed.values @ w
        return pd.Series(blended, index=df.index)
    except Exception:
        return None


def _get_benchmark_series(benchmark_ticker: str) -> Optional[pd.Series]:
    """Return benchmark price series, using an in-memory cache."""
    if benchmark_ticker in _bench_cache:
        return _bench_cache[benchmark_ticker]

    # Composite UTI benchmark?
    try:
        from .amc_benchmarks import COMPOSITE_BENCHMARKS
        comps = {b["id"]: b for b in COMPOSITE_BENCHMARKS}
        if benchmark_ticker in comps:
            series = _blend_composite(comps[benchmark_ticker]["components"])
            if series is not None:
                _bench_cache[benchmark_ticker] = series
            return series
    except ImportError:
        pass

    # Standard yfinance ticker
    try:
        import yfinance as yf
        raw = yf.download(benchmark_ticker, period="5y", auto_adjust=True, progress=False)
        if raw.empty:
            return None
        close = raw["Close"]
        if hasattr(close, "squeeze"):
            close = close.squeeze()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        _bench_cache[benchmark_ticker] = close
        return close
    except Exception:
        return None


def _tstat_pvalue(alphas: list[float]) -> tuple[float, float]:
    """One-sample t-test vs µ₀ = 0.  Returns (t, p_two_tailed)."""
    n = len(alphas)
    if n < 3:
        return 0.0, 1.0
    arr = np.array(alphas, dtype=float)
    mean = arr.mean()
    std = arr.std(ddof=1)
    if std == 0:
        return 0.0, 1.0
    t = mean / (std / math.sqrt(n))
    try:
        from scipy import stats as _st
        p = float(_st.ttest_1samp(arr, 0.0).pvalue)
    except ImportError:
        from math import erfc, sqrt
        p = float(erfc(abs(t) / sqrt(2)))
    p_stored = p if p < 0.0001 else round(p, 4)
    return round(t, 3), p_stored


def _distribution(alphas: list[float], n_bins: int = 12) -> dict:
    if not alphas:
        return {"edges": [], "counts": [], "bin_centers": [], "pct_positive": 0}
    arr = np.array([a for a in alphas if not math.isnan(a)], dtype=float)
    if len(arr) == 0:
        return {"edges": [], "counts": [], "bin_centers": [], "pct_positive": 0}
    lo = min(arr.min(), -0.20)
    hi = max(arr.max(), 0.20)
    span = hi - lo or 1.0
    edges = [lo + i * span / n_bins for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for a in arr:
        idx = max(0, min(int((a - lo) / span * n_bins), n_bins - 1))
        counts[idx] += 1
    centers = [round((edges[i] + edges[i + 1]) / 2, 4) for i in range(n_bins)]
    pct_pos = round(float((arr > 0).mean()) * 100, 1)
    return {
        "edges": [round(e, 4) for e in edges],
        "counts": counts,
        "bin_centers": centers,
        "pct_positive": pct_pos,
    }


def _compute_score_100(alpha_mean: float, success_rate: float,
                       info_ratio: float) -> int:
    """Map three metrics to a 0-100 composite score."""
    # Alpha magnitude: sigmoid centered at 0, +10% → 76, +20% → 90
    alpha_score = 50 + 50 * math.tanh(alpha_mean / 0.10)
    # Success rate: 30% → 0, 50% → 50, 70% → 100
    sr_score = min(max((success_rate - 0.30) / 0.40, 0), 1) * 100
    # Information ratio: IR −0.5 → 0, IR 0 → 25, IR 1 → 75, IR 2 → 100
    ir_score = min(max((info_ratio + 0.5) / 2.0, 0), 1) * 100
    return max(0, min(100, round(0.40 * alpha_score + 0.35 * sr_score + 0.25 * ir_score)))


def _score_label(score: int) -> str:
    if score >= 75: return "Excellent"
    if score >= 60: return "Bon"
    if score >= 45: return "Neutre"
    if score >= 30: return "Faible"
    return "Très faible"


def _interpret(score: int, alpha_means: dict[str, float],
               success_rates: dict[str, float], n_analyzed: int,
               coverage_pct: float, benchmark_ticker: str,
               tstat: float, pvalue: float) -> str:
    parts = []

    if coverage_pct < 30:
        parts.append(
            f"Couverture faible ({coverage_pct:.0f}% des achats analysés) — "
            "configurez les prix dans le module VAG pour améliorer la précision."
        )
    if n_analyzed < 10:
        parts.append(
            f"Échantillon limité ({n_analyzed} achats) — "
            "les résultats sont indicatifs, la significativité statistique est insuffisante."
        )

    label = _score_label(score)
    if score >= 60:
        parts.append(
            f"Score de stock picking de {score}/100 ({label}) — "
            f"la sélection de titres génère un alpha positif vs {benchmark_ticker} "
            "de façon consistante."
        )
    elif score >= 45:
        parts.append(
            f"Score de stock picking de {score}/100 ({label}) — "
            f"sélection proche du benchmark {benchmark_ticker}, "
            "sans avantage informationnel documenté."
        )
    else:
        parts.append(
            f"Score de stock picking de {score}/100 ({label}) — "
            f"la sélection sous-performe le benchmark {benchmark_ticker} "
            "sur les horizons analysés."
        )

    if alpha_means:
        best_h = max(alpha_means, key=lambda h: alpha_means[h])
        worst_h = min(alpha_means, key=lambda h: alpha_means[h])
        if best_h != worst_h and (alpha_means[best_h] - alpha_means[worst_h]) > 0.02:
            parts.append(
                f"Alpha maximal à {best_h} ({alpha_means[best_h]*100:+.1f}%), "
                f"minimal à {worst_h} ({alpha_means[worst_h]*100:+.1f}%)."
            )

    if abs(tstat) >= 1.96:
        direction = "positive" if tstat > 0 else "négative"
        parts.append(
            f"Compétence de sélection statistiquement significative "
            f"(t={tstat:+.2f}, p={pvalue:.3f}) — alpha {direction}."
        )
    elif abs(tstat) >= 1.28:
        parts.append(
            f"Tendance {'favorable' if tstat > 0 else 'défavorable'} "
            f"(t={tstat:+.2f}), non significative à 5%."
        )
    else:
        parts.append(
            f"Aucune compétence de sélection statistiquement détectable "
            f"(t={tstat:+.2f}, p={pvalue:.3f})."
        )

    if success_rates:
        avg_sr = sum(success_rates.values()) / len(success_rates)
        if avg_sr >= 0.60:
            parts.append(
                f"Taux de succès moyen de {avg_sr*100:.0f}% — "
                "plus d'un achat sur deux surperforme le benchmark post-achat."
            )
        elif avg_sr < 0.45:
            parts.append(
                f"Taux de succès moyen de {avg_sr*100:.0f}% — "
                "moins d'un achat sur deux surperforme le benchmark."
            )

    return "  ".join(parts)


# ── public entry point ─────────────────────────────────────────────────────

def compute_stockpicking_score(orders: list[dict],
                               benchmark_ticker: str = "ACWI") -> dict:
    """Compute Block I — Stock Picking Score from executed BUY orders.

    Args:
        orders:           normalised order list from amc_orderbook.load_orders()
        benchmark_ticker: yfinance ticker (or composite UTI id) to compare against

    Returns:
        Rich result dict ready for the frontend and PDF renderer.
    """
    buys = [
        o for o in orders
        if o.get("state") == "Done"
        and str(o.get("side", "")).upper() == "BUY"
        and o.get("date") is not None
    ]

    if not buys:
        return {"available": False, "error": "Aucun ordre d'achat exécuté disponible."}

    bench_series = _get_benchmark_series(benchmark_ticker)
    bench_available = bench_series is not None

    # pre-load unique underlying series
    series_cache: dict[str, Optional[pd.Series]] = {}
    for o in buys:
        key = o.get("isin") or o.get("name", "")
        if key and key not in series_cache:
            series_cache[key] = _load_series(o.get("isin", ""), o.get("name", ""))

    horizon_keys = list(_HORIZONS.keys())
    all_trades: list[dict] = []
    alphas_by_horizon: dict[str, list[float]] = {h: [] for h in horizon_keys}
    all_alphas_flat: list[float] = []

    for o in buys:
        isin     = o.get("isin", "")
        name     = o.get("name", "")
        key      = isin or name
        date     = o.get("date")
        notional = float(o.get("notional_prod") or o.get("notional") or 0)

        t = pd.Timestamp(date).tz_localize(None)
        base = {
            "date":     t.strftime("%Y-%m-%d"),
            "name":     name,
            "isin":     isin,
            "notional": round(notional, 0) if notional else None,
        }

        series = series_cache.get(key)
        if series is None:
            all_trades.append({**base, "available": False,
                                "reason": "Prix non disponibles dans le Price Store"})
            continue

        horizon_data: dict[str, dict] = {}
        any_horizon = False

        for h, n_days in _HORIZONS.items():
            ret_title = _forward_return(series, t, n_days)
            if ret_title is None:
                horizon_data[h] = {"available": False}
                continue

            ret_bench = None
            alpha = None
            if bench_available:
                ret_bench = _forward_return(bench_series, t, n_days)
                if ret_bench is not None:
                    alpha = ret_title - ret_bench

            # if no benchmark, use raw return (less meaningful but not None)
            effective_alpha = alpha if alpha is not None else ret_title

            horizon_data[h] = {
                "available":    True,
                "return_title": round(ret_title, 4),
                "return_bench": round(ret_bench, 4) if ret_bench is not None else None,
                "alpha":        round(effective_alpha, 4),
            }
            alphas_by_horizon[h].append(effective_alpha)
            all_alphas_flat.append(effective_alpha)
            any_horizon = True

        if not any_horizon:
            all_trades.append({**base, "available": False,
                                "reason": "Historique de prix insuffisant"})
            continue

        w_sum = sum(_HORIZON_WEIGHTS[h] for h in horizon_data
                    if horizon_data[h].get("available"))
        wa = sum(
            _HORIZON_WEIGHTS[h] * horizon_data[h]["alpha"]
            for h in horizon_data
            if horizon_data[h].get("available")
        )
        alpha_weighted = round(wa / w_sum, 4) if w_sum > 0 else None

        all_trades.append({
            **base,
            "available":      True,
            "horizons":       horizon_data,
            "alpha_weighted": alpha_weighted,
        })

    n_analyzed = sum(1 for t in all_trades if t.get("available"))
    n_total    = len(buys)
    coverage   = round(n_analyzed / n_total * 100, 1) if n_total else 0.0

    if n_analyzed == 0:
        return {
            "available":    False,
            "error":        "Aucune donnée de prix disponible. Chargez les prix dans le module VAG.",
            "n_buys_total": n_total,
            "trades":       all_trades,
        }

    # per-horizon stats
    stats_by_horizon: dict[str, dict] = {}
    for h in horizon_keys:
        alphas = alphas_by_horizon[h]
        if not alphas:
            stats_by_horizon[h] = {"n": 0, "available": False}
            continue
        arr = np.array(alphas, dtype=float)
        stats_by_horizon[h] = {
            "available":    True,
            "n":            len(alphas),
            "alpha_mean":   round(float(arr.mean()), 4),
            "alpha_median": round(float(np.median(arr)), 4),
            "alpha_std":    round(float(arr.std(ddof=1)), 4) if len(alphas) > 1 else 0.0,
            "success_rate": round(float((arr > 0).mean()), 4),
            "distribution": _distribution(alphas),
        }

    alpha_means   = {h: stats_by_horizon[h]["alpha_mean"]
                     for h in horizon_keys if stats_by_horizon[h].get("available")}
    success_rates = {h: stats_by_horizon[h]["success_rate"]
                     for h in horizon_keys if stats_by_horizon[h].get("available")}

    w_sum = sum(_HORIZON_WEIGHTS[h] for h in alpha_means)
    global_alpha = (sum(_HORIZON_WEIGHTS[h] * alpha_means[h] for h in alpha_means) / w_sum
                    if w_sum > 0 else 0.0)
    global_sr    = (sum(_HORIZON_WEIGHTS[h] * success_rates[h] for h in success_rates) / w_sum
                    if w_sum > 0 else 0.5)

    ir = 0.0
    if all_alphas_flat:
        arr = np.array(all_alphas_flat, dtype=float)
        std = arr.std(ddof=1)
        if std > 0:
            ir = float(arr.mean() / std)

    score  = _compute_score_100(global_alpha, global_sr, ir)
    tstat, pvalue = _tstat_pvalue(all_alphas_flat)

    available_trades = [t for t in all_trades
                        if t.get("available") and t.get("alpha_weighted") is not None]
    sorted_by_alpha  = sorted(available_trades, key=lambda x: x["alpha_weighted"],
                               reverse=True)
    best_ideas  = sorted_by_alpha[:5]
    worst_ideas = list(reversed(sorted_by_alpha[-5:]))

    return {
        "available":           True,
        "benchmark_ticker":    benchmark_ticker,
        "benchmark_available": bench_available,
        "n_buys_analyzed":     n_analyzed,
        "n_buys_total":        n_total,
        "coverage_pct":        coverage,
        "score":               score,
        "score_label":         _score_label(score),
        "global_alpha_mean":   round(global_alpha, 4),
        "global_success_rate": round(global_sr, 4),
        "information_ratio":   round(ir, 3),
        "tstat_alpha":         tstat,
        "pvalue_alpha":        pvalue,
        "stats_by_horizon":    stats_by_horizon,
        "interpretation":      _interpret(score, alpha_means, success_rates, n_analyzed,
                                          coverage, benchmark_ticker, tstat, pvalue),
        "best_ideas":          best_ideas,
        "worst_ideas":         worst_ideas,
        "trades":              sorted(all_trades, key=lambda t: t.get("date", ""),
                                      reverse=True),
        "warning": (
            f"Échantillon limité ({n_analyzed} achats analysés sur {n_total}) — "
            "résultats indicatifs uniquement."
            if n_analyzed < 10 else None
        ),
    }
