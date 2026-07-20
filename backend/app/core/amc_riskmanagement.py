"""Block J — Risk Management Score.

Evaluates whether the manager properly managed the risk they took.
Five sub-scores, each 0-100, weighted into a global score.

Weights:
  risk_adjusted  30%  — Sharpe, Calmar, capture ratios, IR
  drawdown       25%  — Max DD, Ulcer Index, episode count/duration
  downside_risk  20%  — Semi-deviation, Sortino, VaR 95%, ES 95%
  concentration  15%  — Max weight, HHI, effective N
  factor_risk    10%  — R², market beta, alpha t-stat (from Block A)

Reliability cap: n_obs < 30 → cap 50; 30-60 → cap 70; 60-120 → cap 85; 120+ → 100.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

_WEIGHTS = {
    "risk_adjusted": 0.30,
    "drawdown":      0.25,
    "downside_risk": 0.20,
    "concentration": 0.15,
    "factor_risk":   0.10,
}

_bench_cache: dict[str, pd.Series] = {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ── Benchmark series ────────────────────────────────────────────────────────

def _blend_composite(components: list[dict]) -> Optional[pd.Series]:
    try:
        import yfinance as yf
        parts, weights = [], []
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
    if benchmark_ticker in _bench_cache:
        return _bench_cache[benchmark_ticker]
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


# ── NAV → returns ───────────────────────────────────────────────────────────

def _nav_to_returns(nav: list[dict]) -> pd.Series:
    if not nav:
        return pd.Series(dtype=float)
    dates = []
    vals  = []
    for r in nav:
        d = r.get("date")
        v = r.get("nav")
        if d is None or v is None:
            continue
        if hasattr(d, "strftime"):
            dates.append(pd.Timestamp(d))
        else:
            dates.append(pd.Timestamp(str(d)[:10]))
        vals.append(float(v))
    if len(vals) < 2:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()
    return s.pct_change().dropna()


# ── Sub-score 1: Drawdown ────────────────────────────────────────────────────

def _drawdown_series(returns: pd.Series) -> pd.Series:
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    return cum / peak - 1


def _compute_drawdown_episodes(dd: pd.Series) -> list[dict]:
    episodes = []
    in_dd = False
    start_idx = 0
    peak_dd = 0.0
    for i, v in enumerate(dd.values):
        if v < 0 and not in_dd:
            in_dd = True
            start_idx = i
            peak_dd = v
        elif v < 0 and in_dd:
            if v < peak_dd:
                peak_dd = v
        elif v >= -0.001 and in_dd:
            episodes.append({
                "depth_pct": round(peak_dd * 100, 2),
                "duration_days": i - start_idx,
            })
            in_dd = False
            peak_dd = 0.0
    if in_dd:
        episodes.append({
            "depth_pct": round(peak_dd * 100, 2),
            "duration_days": len(dd) - start_idx,
        })
    return sorted(episodes, key=lambda e: e["depth_pct"])[:5]


def _score_drawdown(returns: pd.Series, bench_series: Optional[pd.Series],
                    bench_available: bool) -> dict:
    dd = _drawdown_series(returns)
    max_dd = float(dd.min())  # negative number
    max_dd_pct = round(max_dd * 100, 2)
    ulcer_pct = round(math.sqrt(float((dd ** 2).mean())) * 100, 2)

    # episodes
    episodes = _compute_drawdown_episodes(dd)
    n_ep = len(episodes)
    avg_dur = (sum(e["duration_days"] for e in episodes) / n_ep) if n_ep > 0 else 0

    # bench max DD
    bench_max_dd_pct = None
    if bench_available and bench_series is not None:
        try:
            idx0 = bench_series.index.searchsorted(returns.index[0])
            idx1 = bench_series.index.searchsorted(returns.index[-1], side="right")
            b_sub = bench_series.iloc[max(0, idx0): idx1]
            if len(b_sub) > 2:
                b_ret = b_sub.pct_change().dropna()
                b_dd = _drawdown_series(b_ret)
                bench_max_dd_pct = round(float(b_dd.min()) * 100, 2)
        except Exception:
            pass

    # scoring
    max_dd_score = _clamp(100 - abs(max_dd_pct) * 1.6)
    ulcer_score  = _clamp(100 - ulcer_pct * 3.0)
    ep_score     = 0.6 * _clamp(100 - avg_dur * 0.8) + 0.4 * _clamp(100 - n_ep * 8)
    if bench_max_dd_pct is not None:
        # Both figures are negative (e.g. -10%). A shallower (less negative)
        # drawdown than the benchmark means max_dd_pct - bench_max_dd_pct > 0
        # and must INCREASE the score, not decrease it.
        bench_score = _clamp(50 + (max_dd_pct - bench_max_dd_pct) * 2.5)
    else:
        bench_score = 50.0
    score = round(_clamp(0.35 * max_dd_score + 0.30 * ulcer_score +
                         0.20 * ep_score + 0.15 * bench_score))

    return {
        "score": score,
        "max_drawdown_pct":        max_dd_pct,
        "ulcer_index_pct":         ulcer_pct,
        "n_drawdown_episodes":     n_ep,
        "avg_episode_duration_days": round(avg_dur, 1),
        "bench_max_drawdown_pct":  bench_max_dd_pct,
        "worst_episodes":          episodes,
    }


# ── Sub-score 2: Downside Risk ───────────────────────────────────────────────

def _score_downside_risk(returns: pd.Series) -> dict:
    arr = returns.values.astype(float)
    neg = arr[arr < 0]
    semi_dev_ann = (neg.std(ddof=1) * math.sqrt(252) * 100) if len(neg) > 1 else 0.0

    mean_r = arr.mean()
    sortino = (mean_r * 252) / (neg.std(ddof=1) * math.sqrt(252)) if len(neg) > 1 and neg.std() > 0 else 0.0

    var_95 = round(float(np.percentile(arr, 5)) * 100, 2)
    tail   = arr[arr <= np.percentile(arr, 5)]
    es_95  = round(float(tail.mean()) * 100, 2) if len(tail) > 0 else var_95

    worst_day = round(float(arr.min()) * 100, 2)

    rolling5 = pd.Series(arr).rolling(5).sum()
    worst_week = round(float(rolling5.min()) * 100, 2) if len(rolling5.dropna()) > 0 else 0.0

    rolling21 = pd.Series(arr).rolling(21).sum()
    worst_month = round(float(rolling21.min()) * 100, 2) if len(rolling21.dropna()) > 0 else 0.0

    n_neg = int((arr < 0).sum())
    pct_neg = round(n_neg / len(arr) * 100, 1) if len(arr) > 0 else 0.0

    sd_score      = _clamp(100 - semi_dev_ann * 2.5)
    sortino_score = _clamp(40 + 50 * math.tanh(sortino / 1.5))
    es_score      = _clamp(100 - abs(es_95) * 11)
    score = round(_clamp(0.35 * sd_score + 0.40 * sortino_score + 0.25 * es_score))

    return {
        "score":                score,
        "semi_deviation_ann_pct": round(semi_dev_ann, 2),
        "sortino_ratio":          round(sortino, 3),
        "var_95_pct":             var_95,
        "es_95_pct":              es_95,
        "worst_day_pct":          worst_day,
        "worst_week_pct":         worst_week,
        "worst_month_pct":        worst_month,
        "n_negative_days":        n_neg,
        "pct_negative_days":      pct_neg,
    }


# ── Sub-score 3: Risk-Adjusted Performance ───────────────────────────────────

def _score_risk_adjusted(returns: pd.Series, bench_series: Optional[pd.Series],
                         bench_available: bool, max_dd_pct: float,
                         sortino: float) -> dict:
    arr = returns.values.astype(float)
    ann_ret = arr.mean() * 252
    ann_vol = arr.std(ddof=1) * math.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    calmar  = ann_ret / abs(max_dd_pct / 100) if max_dd_pct < 0 else 0.0

    up_capture = down_capture = None
    ir = tracking_error = None

    if bench_available and bench_series is not None:
        try:
            # align returns
            b_sub = bench_series.reindex(returns.index, method="ffill").pct_change().dropna()
            aligned = returns.reindex(b_sub.index).dropna()
            b_aligned = b_sub.reindex(aligned.index).dropna()
            aligned = aligned.reindex(b_aligned.index)

            if len(aligned) > 20:
                b_arr = b_aligned.values.astype(float)
                f_arr = aligned.values.astype(float)

                up_mask   = b_arr > 0
                down_mask = b_arr < 0
                if up_mask.sum() > 3:
                    up_capture = round(f_arr[up_mask].mean() / b_arr[up_mask].mean() * 100, 1)
                if down_mask.sum() > 3:
                    down_capture = round(f_arr[down_mask].mean() / b_arr[down_mask].mean() * 100, 1)

                excess = f_arr - b_arr
                te = excess.std(ddof=1) * math.sqrt(252)
                tracking_error = round(te * 100, 2)
                ir = round(excess.mean() * 252 / te, 3) if te > 0 else 0.0
        except Exception:
            pass

    # scoring
    sharpe_score = _clamp(40 + 50 * math.tanh(sharpe / 1.5))
    calmar_score = _clamp(40 + 50 * math.tanh(calmar / 2.0))
    if up_capture is not None and down_capture is not None and down_capture != 0:
        ratio = up_capture / down_capture
        capture_score = _clamp(40 + 50 * math.tanh((ratio - 1) * 2))
    else:
        capture_score = 50.0
    ir_score = _clamp(40 + 50 * math.tanh((ir or 0) / 0.8)) if ir is not None else 50.0
    score = round(_clamp(0.35 * sharpe_score + 0.25 * calmar_score +
                         0.25 * capture_score + 0.15 * ir_score))

    return {
        "score":              score,
        "sharpe_ratio":       round(sharpe, 3),
        "sortino_ratio":      round(sortino, 3),
        "calmar_ratio":       round(calmar, 3),
        "information_ratio":  ir,
        "tracking_error_pct": tracking_error,
        "upside_capture_pct": up_capture,
        "downside_capture_pct": down_capture,
    }


# ── Sub-score 4: Concentration ───────────────────────────────────────────────

def _score_concentration(composition: dict) -> dict:
    components = composition.get("components", [])
    if not components:
        return {
            "score": 50, "n_holdings": 0,
            "max_weight_pct": None, "top3_weight_pct": None,
            "top5_weight_pct": None, "top10_weight_pct": None,
            "hhi": None, "effective_n": None, "top5_holdings": [],
        }

    weights = []
    names   = []
    for c in components:
        w = c.get("weight") or 0.0
        weights.append(float(w))
        names.append(c.get("name", ""))

    total_w = sum(weights)
    if total_w <= 0:
        return {
            "score": 50, "n_holdings": len(components),
            "max_weight_pct": None, "top3_weight_pct": None,
            "top5_weight_pct": None, "top10_weight_pct": None,
            "hhi": None, "effective_n": None, "top5_holdings": [],
        }

    nw = [w / total_w for w in weights]
    sorted_idx = sorted(range(len(nw)), key=lambda i: -nw[i])
    nw_sorted = [nw[i] for i in sorted_idx]

    n_holdings      = len(nw)
    max_weight_pct  = round(nw_sorted[0] * 100, 2) if nw_sorted else 0.0
    top3_weight_pct = round(sum(nw_sorted[:3]) * 100, 2)
    top5_weight_pct = round(sum(nw_sorted[:5]) * 100, 2)
    top10_weight_pct = round(sum(nw_sorted[:10]) * 100, 2)
    hhi = round(sum(w ** 2 for w in nw), 4)
    effective_n = round(1 / hhi, 2) if hhi > 0 else n_holdings

    top5 = [{"name": names[sorted_idx[i]], "weight_pct": round(nw_sorted[i] * 100, 2)}
            for i in range(min(5, n_holdings))]

    mw_score = _clamp(100 - max_weight_pct * 1.1)
    en_score = _clamp(100 * (1 - math.exp(-effective_n / 8)))
    t5_score = _clamp(100 - top5_weight_pct * 0.9)
    score = round(_clamp(0.40 * mw_score + 0.35 * en_score + 0.25 * t5_score))

    return {
        "score":            score,
        "n_holdings":       n_holdings,
        "max_weight_pct":   max_weight_pct,
        "top3_weight_pct":  top3_weight_pct,
        "top5_weight_pct":  top5_weight_pct,
        "top10_weight_pct": top10_weight_pct,
        "hhi":              hhi,
        "effective_n":      effective_n,
        "top5_holdings":    top5,
    }


# ── Sub-score 5: Factor Risk ─────────────────────────────────────────────────

def _score_factor_risk(block_a: Optional[dict]) -> dict:
    base = {"score": 50, "available": False,
            "r2_pct": None, "market_beta": None,
            "alpha_ann_pct": None, "alpha_tstat": None,
            "n_factors": 0, "significant_factors": []}

    if not block_a or not block_a.get("available"):
        return base

    net = (block_a.get("net") or {})
    reg = net.get("regression") or {}
    if not reg:
        return base

    r2_pct       = round((reg.get("r2") or 0) * 100, 1)
    alpha_ann_pct = reg.get("alpha_ann_pct") or 0.0
    alpha_tstat   = reg.get("alpha_tstat") or 0.0
    factors       = reg.get("factors") or []
    n_factors     = len(factors)

    market_beta = None
    for f in factors:
        name = (f.get("name") or "").upper()
        if "MKT" in name or "MKT-RF" in name:
            market_beta = round(f.get("beta") or 0.0, 3)
            break

    sig_factors = [f["name"] for f in factors
                   if abs(f.get("tstat") or 0) >= 1.96]

    # r2 scoring
    if r2_pct < 20:
        r2_score = 45.0
    elif r2_pct <= 70:
        r2_score = 70.0
    else:
        r2_score = _clamp(70 - (r2_pct - 70) * 2)

    # beta scoring
    if market_beta is None:
        beta_score = 60.0
    elif 0.5 <= market_beta <= 1.2:
        beta_score = 80.0
    elif market_beta > 1.2:
        beta_score = _clamp(80 - (market_beta - 1.2) * 60)
    elif market_beta < 0:
        beta_score = 30.0
    else:
        beta_score = _clamp(40 + market_beta * 80)

    # alpha t-stat scoring
    at = abs(alpha_tstat)
    if alpha_tstat > 2:
        alpha_score = _clamp(70 + at * 5)
    elif alpha_tstat > 0:
        alpha_score = _clamp(55 + at * 7)
    elif alpha_tstat > -2:
        alpha_score = _clamp(40 + alpha_tstat * 5)
    else:
        alpha_score = _clamp(30 + alpha_tstat * 3)

    score = round(_clamp(0.30 * r2_score + 0.40 * beta_score + 0.30 * alpha_score))

    return {
        "score":              score,
        "available":          True,
        "r2_pct":             r2_pct,
        "market_beta":        market_beta,
        "alpha_ann_pct":      round(alpha_ann_pct, 3),
        "alpha_tstat":        round(alpha_tstat, 3),
        "n_factors":          n_factors,
        "significant_factors": sig_factors,
    }


# ── Reliability cap ──────────────────────────────────────────────────────────

def _reliability_cap(n_obs: int) -> int:
    if n_obs < 30:  return 50
    if n_obs < 60:  return 70
    if n_obs < 120: return 85
    return 100


# ── Score label ──────────────────────────────────────────────────────────────

def _score_label(score: int) -> str:
    if score >= 80: return "Excellent"
    if score >= 65: return "Bon"
    if score >= 50: return "Neutre"
    if score >= 35: return "Faible"
    return "Très faible"


# ── Interpretation ───────────────────────────────────────────────────────────

def _interpret(score: int, sub: dict, cap: int, bench_ticker: str,
               bench_ok: bool, n_obs: int) -> str:
    parts = []

    if n_obs < 60:
        parts.append(
            f"Fiabilité limitée ({n_obs} observations) — le score est plafonné à {cap}/100 "
            "pour refléter l'incertitude statistique."
        )

    label = _score_label(score)
    parts.append(
        f"Score de gestion du risque de {score}/100 ({label}) — "
        f"synthèse de 5 dimensions : performance ajustée ({sub['risk_adjusted']['score']}/100), "
        f"drawdown ({sub['drawdown']['score']}/100), "
        f"risque baissier ({sub['downside_risk']['score']}/100), "
        f"concentration ({sub['concentration']['score']}/100), "
        f"facteurs ({sub['factor_risk']['score']}/100)."
    )

    dd = sub["drawdown"]
    if dd["max_drawdown_pct"] is not None:
        parts.append(
            f"Drawdown maximum de {dd['max_drawdown_pct']:.1f}% "
            f"avec un Ulcer Index de {dd['ulcer_index_pct']:.1f}% — "
            + (
                "profil de perte gérable." if dd["score"] >= 65
                else "perte maximale préoccupante, à surveiller."
            )
        )

    ra = sub["risk_adjusted"]
    parts.append(
        f"Sharpe de {ra['sharpe_ratio']:.2f}, Calmar de {ra['calmar_ratio']:.2f}."
    )
    if ra.get("upside_capture_pct") is not None and ra.get("downside_capture_pct") is not None:
        parts.append(
            f"Capture ratios : hausse {ra['upside_capture_pct']:.0f}% / baisse {ra['downside_capture_pct']:.0f}% vs {bench_ticker} — "
            + (
                "profil asymétrique favorable (capte plus la hausse que la baisse)."
                if ra["upside_capture_pct"] > ra["downside_capture_pct"]
                else "exposition symétrique ou défavorable."
            )
        )

    conc = sub["concentration"]
    if conc.get("effective_n") is not None:
        parts.append(
            f"Portefeuille avec {conc['n_holdings']} positions, "
            f"N effectif de {conc['effective_n']:.1f} titres (top-5 = {conc['top5_weight_pct']:.0f}% du portefeuille)."
        )

    return "  ".join(parts)


# ── Public entry point ───────────────────────────────────────────────────────

def compute_risk_management_score(
    nav: list[dict],
    composition: dict,
    block_a: Optional[dict] = None,
    benchmark_ticker: str = "ACWI",
) -> dict:
    """Compute Block J — Risk Management Score.

    Args:
        nav:              list of {date, nav, ...} records
        composition:      {components: [{name, weight, ...}, ...], ...}
        block_a:          result of Block A (for factor risk sub-score)
        benchmark_ticker: yfinance ticker or composite UTI id

    Returns:
        Rich result dict ready for the frontend and PDF renderer.
    """
    if not nav or len(nav) < 10:
        return {
            "available": False,
            "error": "Historique NAV insuffisant (< 10 observations).",
        }

    returns = _nav_to_returns(nav)
    n_obs   = len(returns)

    if n_obs < 5:
        return {
            "available": False,
            "error": f"Séries de rendements insuffisantes ({n_obs} obs).",
        }

    bench_series   = _get_benchmark_series(benchmark_ticker)
    bench_available = bench_series is not None

    # Sub-scores
    sub_dd   = _score_drawdown(returns, bench_series, bench_available)
    sub_dr   = _score_downside_risk(returns)
    sub_ra   = _score_risk_adjusted(returns, bench_series, bench_available,
                                    sub_dd["max_drawdown_pct"], sub_dr["sortino_ratio"])
    sub_conc = _score_concentration(composition)
    sub_fac  = _score_factor_risk(block_a)

    sub = {
        "drawdown":      sub_dd,
        "downside_risk": sub_dr,
        "risk_adjusted": sub_ra,
        "concentration": sub_conc,
        "factor_risk":   sub_fac,
    }

    raw_score = (
        _WEIGHTS["risk_adjusted"] * sub_ra["score"]
        + _WEIGHTS["drawdown"]      * sub_dd["score"]
        + _WEIGHTS["downside_risk"] * sub_dr["score"]
        + _WEIGHTS["concentration"] * sub_conc["score"]
        + _WEIGHTS["factor_risk"]   * sub_fac["score"]
    )
    score_raw = round(_clamp(raw_score))
    cap       = _reliability_cap(n_obs)
    score     = min(score_raw, cap)
    label     = _score_label(score)

    interp = _interpret(score, sub, cap, benchmark_ticker, bench_available, n_obs)

    warning = None
    if cap < 100:
        warning = f"Score plafonné à {cap}/100 — historique de {n_obs} observations (minimum recommandé : 120)."

    return {
        "available":        True,
        "score":            score,
        "score_raw":        score_raw,
        "score_label":      label,
        "reliability_cap":  cap,
        "n_obs":            n_obs,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_available": bench_available,
        "interpretation":   interp,
        "sub_scores":       sub,
        "weights":          _WEIGHTS,
        "warning":          warning,
    }
