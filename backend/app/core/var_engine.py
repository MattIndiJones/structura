"""VaR/ES engine — the business logic layer on top of core/compute/. Owns
everything specific to "what is a market scenario" and "what does a VaR
study's results mean"; core/compute/ itself stays product-agnostic (see its
own docstring) and never imports anything from this module.

Three responsibilities:
  1. build_deal_scenario_base() — extracts the pure-data equivalent of
     api/deals.py:_mtm_core's ctx for one active deal, ONCE, so every
     scenario job for that deal can share it (the replay itself is cheap —
     no Monte Carlo — recomputing it per scenario would be wasted work, and
     more importantly the compiled objects in _mtm_core's ctx can't cross a
     process boundary anyway — see pricers/var_scenario.py).
  2. Scenario generators — historical (real day-over-day moves replayed) and
     parametric (correlated draws calibrated on the same historical data),
     per the VaR chantier discussion: both run in the same study, side by
     side, never blended into one number.
  3. aggregate_var() — turns a list of per-scenario book ΔMtM (EUR) into
     VaR/ES/percentiles/worst-scenarios.

Both scenario methods deliberately return the SAME shape (spot_pct per
ticker, vol_pts per ticker, a single global corr_delta) so
apply_scenario_to_deal_base() and the compute job payload never need to know
which method produced a given scenario.

Data contract this whole module leans on: `prices` is always
market_data.load_hist_prices()'s own {ticker: [close, ...]} shape, where
EVERY requested ticker's list is exactly as long as the shared `dates` list
(load_hist_prices already reindexes/ffills/bfills to one common DataFrame) —
so no per-ticker ragged-length handling is needed, only "this ticker
couldn't be fetched at all" needs a guard."""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sqlmodel import Session

from .calibration import realized_market


# ── 1. Pure-data deal context (residual leg) ─────────────────────────

def build_deal_scenario_base(deal, session: Session, n_paths: int = 3000) -> dict:
    """Wraps api/deals.py:_mtm_core to get the residual ctx once, then
    strips it down to plain JSON-safe data — see pricers/var_scenario.py's
    docstring for exactly which fields and why.

    Returns {"skipped": True, "reason": ...} instead of raising whenever the
    deal can't be repriced right now (resolved_pending, maturity reached,
    missing market data...) — same 'skip, don't abort the whole book'
    contract as api/shocks.py's _run_shock_on_book, one level up (a VaR
    study over 40 deals must not fail entirely because one of them needs its
    lifecycle refreshed first)."""
    from ..api.deals import _mtm_core, MtmRequest
    from fastapi import HTTPException

    try:
        mtm_payload, ctx = _mtm_core(deal, session, n_paths, MtmRequest())
    except HTTPException as e:
        return {"skipped": True, "reason": e.detail}
    if ctx is None:
        return {"skipped": True, "reason": mtm_payload.get("message", "résolution en attente")}

    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}

    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "devise": deal.devise,
        "nominal": deal.nominal,
        "mtm_before": mtm_payload["mtm"],
        "tickers": ctx["tickers"],
        "base": {
            "script_text": deal.script_snapshot,
            "constat_values": market.get("constats"),
            "value_date": deal.value_date,
            "T_elapsed": ctx["T_elapsed"],
            "state": ctx["state"],
            "norm_spots": list(ctx["norm_spots"]),
            "engine_uls": ctx["engine_uls"],
            "corr": ctx["corr"],
            "r_frac": ctx["r_frac"],
            "T_remaining": ctx["T_remaining"],
            "model_used": ctx["model_used"],
            "yc": ctx["yc"],
            "sigma_r": ctx["sigma_r"],
            "a_r": ctx["a_r"],
            "antithetic": ctx["antithetic"],
            "user_params": ctx["user_params"],
            "barrier_monitoring": market.get("barrierMonitoring", "weekly"),
            "n_paths": n_paths,
        },
    }


# ── Shock application (mirrors api/shocks.py's conventions exactly, kept
#    independent to avoid a core -> api dependency) ────────────────────

def _shock_corr_scalar(corr: list, corr_shock_pts: float) -> list:
    if not corr_shock_pts:
        return corr
    delta = corr_shock_pts / 100.0
    n = len(corr)
    return [[1.0 if i == j else max(-0.99, min(0.99, corr[i][j] + delta))
             for j in range(n)] for i in range(n)]


@dataclass
class MarketScenario:
    key: str
    label: str
    method: str                          # "historical" | "parametric"
    spot_pct: dict = field(default_factory=dict)   # ticker -> % move
    vol_pts: dict = field(default_factory=dict)    # ticker -> vol shock, in points
    corr_delta: float = 0.0              # single global corr shock, in points (same convention as ShockRequest)
    dr_frac: float = 0.0                 # additive rate shock, as a fraction


def apply_scenario_to_deal_base(deal_base: dict, scenario: MarketScenario) -> dict:
    """Resolves a ticker-keyed market scenario onto one deal's own
    underlying order — a ticker the scenario doesn't mention (deal holds
    something the book-wide scenario grid didn't cover) gets a neutral
    (no-op) shock rather than erroring, same 'best effort, not all-or-
    nothing' spirit as the rest of this feature."""
    tickers = deal_base["tickers"]
    spot_mult = [1.0 + scenario.spot_pct.get(tk, 0.0) / 100.0 for tk in tickers]
    vol_add = [scenario.vol_pts.get(tk, 0.0) / 100.0 for tk in tickers]
    corr_shocked = _shock_corr_scalar(deal_base["base"]["corr"], scenario.corr_delta)

    payload = dict(deal_base["base"])
    payload["spot_mult"] = spot_mult
    payload["vol_add"] = vol_add
    payload["dr"] = scenario.dr_frac
    payload["corr_shocked"] = corr_shocked
    return payload


# ── 2. Scenario generation ────────────────────────────────────────────

def _usable_tickers(prices: dict, dates: list[str], tickers: list[str]) -> list[str]:
    """load_hist_prices returns every requested ticker's series reindexed to
    the SAME shared `dates` grid (ffill/bfill) — so a ticker is usable here
    iff it's present at all and has that exact length; anything else means
    the fetch failed for it entirely, not a partial-history case to patch
    around."""
    return [tk for tk in tickers if len(prices.get(tk, [])) == len(dates)]


def _horizon_returns(prices: list[float], horizon_days: int) -> np.ndarray:
    """returns[k] = the horizon_days move ENDING at raw index k+horizon_days
    — index k of the result lines up with dates[k + horizon_days]."""
    px = np.asarray(prices, dtype=float)
    if len(px) <= horizon_days or np.any(px <= 0):
        return np.array([])
    return np.log(px[horizon_days:] / px[:-horizon_days])


def _rolling_vol(returns: np.ndarray, window: int, horizon_days: int) -> np.ndarray:
    """Annualized realized vol, RMS convention (matches calibration.py /
    the engine's REALVOL) — one value per return, NaN until `window` returns
    have accumulated."""
    out = np.full(len(returns), np.nan)
    if len(returns) < window:
        return out
    ann = 252.0 / horizon_days
    for i in range(window - 1, len(returns)):
        seg = returns[i - window + 1: i + 1]
        out[i] = math.sqrt(ann * float(np.mean(seg ** 2)))
    return out


def _rolling_avg_corr(returns_matrix: np.ndarray, window: int) -> np.ndarray:
    """Book-wide average pairwise correlation, rolling — returns_matrix is
    (n_tickers, n_returns). Needs >= 2 tickers; caller guards that."""
    n_tk, n_ret = returns_matrix.shape
    out = np.full(n_ret, np.nan)
    iu = np.triu_indices(n_tk, k=1)
    for i in range(window - 1, n_ret):
        seg = returns_matrix[:, i - window + 1: i + 1]
        with np.errstate(invalid="ignore"):
            C = np.corrcoef(seg)
        vals = C[iu]
        vals = vals[~np.isnan(vals)]
        out[i] = float(np.mean(vals)) if len(vals) else np.nan
    return out


def generate_historical_scenarios(
    prices: dict, dates: list[str], tickers: list[str], lookback_years: float = 5.0,
    horizon_days: int = 1, vol_window: int = 20,
) -> list[MarketScenario]:
    """One scenario per historical trading day in the lookback window — the
    REAL day-over-day (or horizon_days-over-horizon_days, overlapping) move
    actually observed for each ticker. vol_pts/corr_delta are a PROXY (see
    module docstring and the VaR chantier discussion): realized vol/corr
    over a short rolling window at that historical date, relative to the
    same rolling window ending today — not a true implied-vol replay, which
    would need a vendor feed most family offices/small brokers don't have."""
    usable = _usable_tickers(prices, dates, tickers)
    if not usable:
        return []

    returns = {tk: _horizon_returns(prices[tk], horizon_days) for tk in usable}
    n_ret = min(len(r) for r in returns.values())
    if n_ret < vol_window + 2:
        return []

    vols = {tk: _rolling_vol(returns[tk][:n_ret], vol_window, horizon_days) for tk in usable}

    corr_roll = None
    if len(usable) >= 2:
        mat = np.array([returns[tk][:n_ret] for tk in usable])
        corr_roll = _rolling_avg_corr(mat, vol_window)

    lookback_n = min(n_ret, round(lookback_years * 252 / horizon_days))
    start = max(vol_window - 1, n_ret - lookback_n)
    baseline_corr = corr_roll[-1] if corr_roll is not None and not np.isnan(corr_roll[-1]) else None

    scenarios = []
    for i in range(start, n_ret):
        spot_pct = {tk: float((math.exp(returns[tk][i]) - 1.0) * 100.0) for tk in usable}
        vol_pts = {}
        for tk in usable:
            v = vols[tk]
            if not np.isnan(v[i]) and not np.isnan(v[-1]):
                vol_pts[tk] = float((v[i] - v[-1]) * 100.0)
        corr_delta = 0.0
        if corr_roll is not None and baseline_corr is not None and not np.isnan(corr_roll[i]):
            corr_delta = float((corr_roll[i] - baseline_corr) * 100.0)

        date_label = dates[i + horizon_days] if i + horizon_days < len(dates) else f"j-{n_ret - 1 - i}"
        scenarios.append(MarketScenario(
            key=f"hist:{date_label}", label=date_label, method="historical",
            spot_pct=spot_pct, vol_pts=vol_pts, corr_delta=corr_delta,
        ))
    return scenarios


def calibrate_comovement(prices: dict, dates: list[str], tickers: list[str],
                          vol_window: int = 20, horizon_days: int = 1) -> dict:
    """Single-factor calibration of how vol/corr respond to a market move —
    regresses (rolling vol change, rolling avg-corr change) against an
    equal-weighted 'market factor' return, on the SAME historical series the
    historical scenarios use, so the two methods share one consistent view
    of the world rather than the parametric leg inventing its own arbitrary
    multipliers (see the VaR chantier discussion)."""
    usable = _usable_tickers(prices, dates, tickers)
    if not usable:
        return {"vol_beta": 0.0, "corr_beta": 0.0}

    returns = {tk: _horizon_returns(prices[tk], horizon_days) for tk in usable}
    n_ret = min(len(r) for r in returns.values())
    if n_ret < vol_window + 5:
        return {"vol_beta": 0.0, "corr_beta": 0.0}

    mat = np.array([returns[tk][:n_ret] for tk in usable])
    market_factor = mat.mean(axis=0)

    vol_beta = 0.0
    vols = _rolling_vol(market_factor, vol_window, horizon_days)
    valid = ~np.isnan(vols)
    if valid.sum() >= 5 and np.std(market_factor[valid]) > 1e-12:
        # Contemporaneous fit: a crisis's vol spike happens the SAME day as
        # its drawdown, not with a lag.
        y = vols[valid] - vols[valid][-1]
        vol_beta = float(np.polyfit(market_factor[valid], y, 1)[0])

    corr_beta = 0.0
    if len(usable) >= 2:
        corr_roll = _rolling_avg_corr(mat, vol_window)
        valid_c = ~np.isnan(corr_roll)
        if valid_c.sum() >= 5 and np.std(market_factor[valid_c]) > 1e-12:
            y = corr_roll[valid_c] - corr_roll[valid_c][-1]
            corr_beta = float(np.polyfit(market_factor[valid_c], y, 1)[0])

    return {"vol_beta": vol_beta, "corr_beta": corr_beta}


def generate_parametric_scenarios(
    prices: dict, dates: list[str], tickers: list[str], n_scenarios: int = 2000,
    horizon_days: int = 1, seed: int = 42,
) -> list[MarketScenario]:
    """Correlated draws from a multivariate normal calibrated on realized
    vol/corr (calibration.py:realized_market — the same estimator the
    residual-MtM 'marché actuel' recalibration already uses elsewhere in
    this app), scaled to the VaR horizon via the standard sqrt(time) i.i.d.
    approximation. Each draw's vol/corr shock comes from calibrate_comovement
    applied to that draw's own equal-weighted market-factor move, so a big
    simulated drawdown scenario also gets a bigger simulated vol/corr
    response — not a fixed shock size regardless of draw magnitude."""
    usable = _usable_tickers(prices, dates, tickers)
    if not usable:
        return []
    try:
        rm = realized_market(prices, usable, window_days=252)
    except ValueError:
        return []
    comove = calibrate_comovement(prices, dates, usable, horizon_days=horizon_days)

    sigma = np.array([rm["sigma"][tk] for tk in usable]) / math.sqrt(252.0 / horizon_days)
    corr = np.array(rm["corr"])
    cov = np.outer(sigma, sigma) * corr

    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(mean=np.zeros(len(usable)), cov=cov, size=n_scenarios)

    scenarios = []
    for i, row in enumerate(draws):
        spot_pct = {tk: float((math.exp(row[j]) - 1.0) * 100.0) for j, tk in enumerate(usable)}
        market_move = float(row.mean())
        # comove's betas are OLS slopes of (vol/corr change) ON (return) —
        # y_hat = beta * x already carries the right sign (beta is negative
        # when a drop in returns coincides with a vol/corr rise, so
        # beta * a_negative_draw comes out positive on its own; negating
        # market_move here would flip the sign the regression already fit).
        vol_shock_pts = comove["vol_beta"] * market_move * 100.0
        corr_shock_pts = comove["corr_beta"] * market_move * 100.0
        scenarios.append(MarketScenario(
            key=f"param:{i:05d}", label=f"tirage #{i + 1}", method="parametric",
            spot_pct=spot_pct,
            vol_pts={tk: vol_shock_pts for tk in usable},
            corr_delta=corr_shock_pts,
        ))
    return scenarios


# ── 3. Aggregation ─────────────────────────────────────────────────────

def aggregate_var(deltas_eur: list[float], confidence: float = 0.95) -> dict:
    """deltas_eur: one entry per scenario — the WHOLE BOOK's ΔMtM (EUR) under
    that scenario (already summed across every deal). VaR/ES are read on the
    LOSS side (negative deltas), reported as positive numbers (a loss of
    480k€ is reported as var_eur=480000, not -480000) — the desk convention."""
    if not deltas_eur:
        return {"var_eur": None, "es_eur": None, "n_scenarios": 0, "distribution_summary": {}}
    arr = np.array(sorted(deltas_eur))   # ascending: worst losses first
    n = len(arr)
    alpha = 1.0 - confidence
    # +1e-9 guards against float noise (e.g. 1.0 - 0.90 == 0.09999999999999998
    # in binary, which would floor DOWN to the wrong bucket without this).
    cut = max(0, min(n - 1, int(math.floor(alpha * n + 1e-9))))
    var_value = -arr[cut]
    tail = arr[:cut + 1]
    es_value = -float(tail.mean())

    def pctl(p: float) -> float:
        return float(np.percentile(arr, p))

    return {
        "var_eur": round(float(var_value), 2),
        "es_eur": round(float(es_value), 2),
        "n_scenarios": n,
        "distribution_summary": {
            "p1": round(pctl(1), 2), "p5": round(pctl(5), 2), "p50": round(pctl(50), 2),
            "p95": round(pctl(95), 2), "p99": round(pctl(99), 2),
        },
    }
