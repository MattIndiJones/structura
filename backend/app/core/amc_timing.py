"""Block H — Timing Score.

Measures the quality of the manager's entry and exit points by positioning
each executed price within the local price range observed over the 30 days
before and after each trade.

Entry Score = (max_window - price_buy)  / (max_window - min_window)
Exit  Score = (price_sell - min_window) / (max_window - min_window)

Score = 1  → perfect timing (bought at absolute low / sold at absolute high)
Score = 0  → worst timing  (bought at absolute high / sold at absolute low)
Score = 0.5 → random baseline

Prices are sourced from the persistent parquet store populated by the VAG
module (amc_prices.py).  Trades for ISINs without stored prices are skipped
and accounted for in the coverage metric.
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

import numpy as np
import pandas as pd

from .amc_prices import load_prices

_WINDOW_DAYS = 30          # calendar days on each side of the trade
_LABEL_THRESHOLDS = {      # score → qualitative label
    0.75: "Excellent",
    0.60: "Bon",
    0.40: "Neutre",
    0.25: "Faible",
}


# ── helpers ───────────────────────────────────────────────────────────────

def _label(score: float) -> str:
    for threshold, lbl in sorted(_LABEL_THRESHOLDS.items(), reverse=True):
        if score >= threshold:
            return lbl
    return "Très faible"


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


def _score_trade(series: pd.Series, trade_date: datetime.datetime,
                 price_local: float) -> Optional[dict]:
    """Compute timing score for one trade using the window around trade_date."""
    if price_local is None or price_local <= 0:
        return None

    t = pd.Timestamp(trade_date).tz_localize(None)
    lo = t - pd.Timedelta(days=_WINDOW_DAYS)
    hi = t + pd.Timedelta(days=_WINDOW_DAYS)

    window = series.loc[(series.index >= lo) & (series.index <= hi)]
    if len(window) < 5:          # too sparse — can happen at fund inception or end
        return None

    w_min = float(window.min())
    w_max = float(window.max())
    if w_max <= w_min:
        return None

    return {
        "price_min_window": round(w_min, 4),
        "price_max_window": round(w_max, 4),
        "n_points": len(window),
    }


def _tstat_pvalue(scores: list[float]) -> tuple[float, float]:
    """One-sample t-test against µ0 = 0.5.  Returns (t, p_two_tailed)."""
    n = len(scores)
    if n < 3:
        return 0.0, 1.0
    arr = np.array(scores, dtype=float)
    mean = arr.mean()
    std  = arr.std(ddof=1)
    if std == 0:
        return 0.0, 1.0
    t = (mean - 0.5) / (std / math.sqrt(n))
    # approximate two-tailed p-value via normal (valid for n > 20)
    try:
        from scipy import stats as _st
        p = float(_st.ttest_1samp(arr, 0.5).pvalue)
    except ImportError:
        # fallback: normal approximation (reasonable for n > 20)
        from math import erfc, sqrt
        p = float(erfc(abs(t) / sqrt(2)))
    return round(t, 3), round(p, 4)


def _distribution(scores: list[float], n_bins: int = 10) -> dict:
    if not scores:
        return {"edges": [], "counts": [], "bin_centers": []}
    edges = [i / n_bins for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for s in scores:
        idx = min(int(s * n_bins), n_bins - 1)
        counts[idx] += 1
    centers = [round((edges[i] + edges[i + 1]) / 2, 2) for i in range(n_bins)]
    return {"edges": edges, "counts": counts, "bin_centers": centers}


def _interpret(entry_mean: float, exit_mean: float, global_mean: float,
               tstat: float, n: int, coverage_pct: float) -> str:
    parts = []
    if coverage_pct < 30:
        parts.append(
            f"Couverture faible ({coverage_pct:.0f}% des ordres analysés) — "
            "configurez les prix dans le module VAG pour améliorer la précision."
        )
    if n < 15:
        parts.append(
            f"Échantillon limité ({n} trades) : les scores sont indicatifs, "
            "la significativité statistique est insuffisante."
        )

    if abs(tstat) >= 1.96:
        direction = "supérieur" if global_mean > 0.5 else "inférieur"
        parts.append(
            f"Score global de {global_mean:.2f} statistiquement {direction} "
            f"au hasard (t = {tstat:+.2f}, p < 0.05)."
        )
    elif abs(tstat) >= 1.28:
        parts.append(
            f"Score global de {global_mean:.2f} légèrement {'au-dessus' if global_mean > 0.5 else 'en-dessous'} "
            f"du hasard (t = {tstat:+.2f}, tendance non significative)."
        )
    else:
        parts.append(
            f"Score global de {global_mean:.2f} indiscernable du hasard (t = {tstat:+.2f}) — "
            "aucune compétence ni biais systématique de timing détecté."
        )

    # Entry vs exit split
    if abs(entry_mean - exit_mean) >= 0.1:
        better  = "entrées" if entry_mean >= exit_mean else "sorties"
        weaker  = "sorties" if entry_mean >= exit_mean else "entrées"
        better_v = entry_mean if entry_mean >= exit_mean else exit_mean
        weaker_v = exit_mean  if entry_mean >= exit_mean else entry_mean
        parts.append(
            f"Les {better} sont mieux timées ({better_v:.2f}) que les {weaker} ({weaker_v:.2f}) — "
            "suggère un déséquilibre entre la qualité d'achat et de vente."
        )

    if global_mean >= 0.65 and tstat >= 1.28:
        parts.append("Conclusion : compétence de timing réelle, avantage comportemental documenté.")
    elif global_mean <= 0.35 and tstat <= -1.28:
        parts.append(
            "Conclusion : biais négatif documenté — le gérant tend à acheter haut et/ou vendre bas. "
            "Point de due diligence à approfondir."
        )
    else:
        parts.append("Conclusion : timing proche de l'aléatoire, cohérent avec un processus fondamental.")

    return "  ".join(parts)


# ── public entry point ─────────────────────────────────────────────────────

def compute_timing_score(orders: list[dict]) -> dict:
    """Compute Block H — Timing Score from executed orders.

    Args:
        orders: normalised order list from amc_orderbook.load_orders()

    Returns:
        Rich result dict ready for the frontend and PDF renderer.
    """
    executed = [o for o in orders if o.get("state") == "Done"
                and o.get("price_local") is not None
                and o.get("date") is not None]

    if not executed:
        return {"available": False, "error": "Aucun ordre exécuté disponible."}

    # pre-load unique series
    series_cache: dict[str, Optional[pd.Series]] = {}
    for o in executed:
        isin = o.get("isin", "")
        name = o.get("name", "")
        key  = isin or name
        if key not in series_cache:
            series_cache[key] = _load_series(isin, name)

    trades = []
    entry_scores: list[float] = []
    exit_scores:  list[float] = []

    for o in executed:
        isin = o.get("isin", "")
        name = o.get("name", "")
        key  = isin or name
        side = o.get("side", "BUY")
        date = o.get("date")
        price_local = o.get("price_local")

        base = {
            "date":        date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
            "side":        side,
            "name":        name,
            "isin":        isin,
            "price_local": round(price_local, 4) if price_local else None,
        }

        series = series_cache.get(key)
        if series is None:
            trades.append({**base, "available": False, "reason": "Prix non disponibles"})
            continue

        info = _score_trade(series, date, price_local)
        if info is None:
            trades.append({**base, "available": False, "reason": "Fenêtre de prix insuffisante"})
            continue

        w_min = info["price_min_window"]
        w_max = info["price_max_window"]
        span  = w_max - w_min

        # Outlier guard: exec price more than 3× outside the window range
        # → probable split-adjusted store vs as-traded order, or bad data entry.
        # Exclude the trade rather than produce a spurious 0.0 or 1.0 score.
        ratio = price_local / w_max if price_local > w_max else w_min / price_local if price_local < w_min else 1.0
        if ratio > 3.0:
            trades.append({**base, "available": False,
                           "reason": f"Prix suspect (exec={price_local:.2f}, range={w_min:.2f}–{w_max:.2f}, ratio=×{ratio:.1f})"})
            continue

        if side == "BUY":
            score = (w_max - price_local) / span
        else:
            score = (price_local - w_min) / span

        score = max(0.0, min(1.0, round(score, 4)))

        trade_rec = {
            **base,
            "available":        True,
            "score":            score,
            "label":            _label(score),
            "price_min_window": w_min,
            "price_max_window": w_max,
            "n_points":         info["n_points"],
        }
        trades.append(trade_rec)

        if side == "BUY":
            entry_scores.append(score)
        else:
            exit_scores.append(score)

    all_scores = entry_scores + exit_scores
    n_analyzed = len(all_scores)
    n_total    = len(executed)
    coverage   = round(n_analyzed / n_total * 100, 1) if n_total else 0.0

    if n_analyzed == 0:
        return {
            "available": False,
            "error": "Aucun prix disponible. Chargez les séries de prix dans le module VAG.",
            "n_trades_total": n_total,
            "trades": trades,
        }

    def _safe_mean(lst): return round(float(np.mean(lst)), 4) if lst else None

    entry_mean  = _safe_mean(entry_scores)
    exit_mean   = _safe_mean(exit_scores)
    global_mean = _safe_mean(all_scores)

    t_entry, p_entry   = _tstat_pvalue(entry_scores)  if entry_scores  else (0.0, 1.0)
    t_exit,  p_exit    = _tstat_pvalue(exit_scores)   if exit_scores   else (0.0, 1.0)
    t_global, p_global = _tstat_pvalue(all_scores)

    # top/worst for each side
    def _top(lst, side_filter, n=3, reverse=True):
        filtered = [t for t in trades if t.get("available") and t["side"] == side_filter]
        return sorted(filtered, key=lambda x: x["score"], reverse=reverse)[:n]

    def _quadrant(lst, lo, hi):
        return [t for t in trades if t.get("available")
                and lo <= t["score"] < hi]

    near_lows_buys  = [t for t in trades if t.get("available") and t["side"] == "BUY"  and t["score"] >= 0.70]
    near_highs_buys = [t for t in trades if t.get("available") and t["side"] == "BUY"  and t["score"] <= 0.25]
    near_highs_sells = [t for t in trades if t.get("available") and t["side"] == "SELL" and t["score"] >= 0.70]
    early_sells      = [t for t in trades if t.get("available") and t["side"] == "SELL" and t["score"] <= 0.30]

    interpretation = _interpret(
        entry_mean or 0.5, exit_mean or 0.5, global_mean or 0.5,
        t_global, n_analyzed, coverage,
    )

    return {
        "available":          True,
        "n_trades_analyzed":  n_analyzed,
        "n_trades_total":     n_total,
        "n_buy":              len(entry_scores),
        "n_sell":             len(exit_scores),
        "coverage_pct":       coverage,
        "entry_score_mean":   entry_mean,
        "exit_score_mean":    exit_mean,
        "global_score_mean":  global_mean,
        "tstat_entry":        t_entry,
        "tstat_exit":         t_exit,
        "tstat_global":       t_global,
        "pvalue_global":      p_global,
        "interpretation":     interpretation,
        # distributions
        "dist_entry":    _distribution(entry_scores),
        "dist_exit":     _distribution(exit_scores),
        "dist_global":   _distribution(all_scores),
        # patterns
        "near_lows_buys":    near_lows_buys,
        "near_highs_buys":   near_highs_buys,
        "near_highs_sells":  near_highs_sells,
        "early_sells":       early_sells,
        # all trades (for table)
        "trades": sorted(trades, key=lambda t: t.get("date", ""), reverse=True),
        # warnings
        "warning": (
            f"Échantillon limité ({n_analyzed} trades analysés sur {n_total}) — "
            "résultats indicatifs uniquement."
            if n_analyzed < 15 else None
        ),
    }
