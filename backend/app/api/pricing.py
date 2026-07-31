import itertools
import math
import numpy as np
from fastapi import APIRouter, HTTPException
from ..core.schemas import (
    PricingRequest, PricingResponse, ParseRequest, ParseResponse,
    ProfileRequest, PathsRequest, ProbaRequest, BacktestRequest, BacktestCompareRequest,
    MtfRequest,
)
from ..core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ..core.payscript.engine import (
    run_mc, compute_greeks,
    run_payoff_profile, run_mc_paths, run_mc_proba,
    eval_script_on_history, compute_irr,
    run_mark_to_future,
)
from ..services.market_data import load_hist_prices

router = APIRouter(prefix="/api", tags=["pricing"])


def _clean_flux(flux_map: dict) -> dict:
    """Return per-expression flux entries with rounded values for JSON.
    df = implied discount factor = pv/sum (exact under deterministic rates,
    conditional expectation E[B(0,t)|CF fires] under stochastic rates)."""
    result = {}
    for k, v in flux_map.items():
        sm = round(v["sum"], 6)
        pv = round(v.get("pv", v["sum"]), 6)
        df = round(pv / sm, 6) if abs(sm) > 1e-10 else 1.0
        result[k] = {
            "t":   round(v["t"], 6),
            "lbl": v["lbl"],
            "n":   v["n"],
            "sum": sm,
            "pv":  pv,
            "df":  df,
        }
    return result


@router.post("/parse", response_model=ParseResponse)
def parse_endpoint(req: ParseRequest):
    try:
        compiled = parse_script(req.script)
        return ParseResponse(
            ok=True,
            params=[{
                "name": p.name,
                "raw_default": p.raw_default,
                "display_default": p.raw_default,
                "stored_val": p.stored_val,
                "is_pct": p.is_pct,
                "desc": p.desc,
                "kind": p.kind,
            } for p in compiled.params],
            constats=[{"name": c.name, "kind": c.kind} for c in compiled.constats],
            events_count=len(compiled.events),
            has_stop=compiled.has_stop,
            monitors=compiled.monitors or [],
        )
    except ValueError as e:
        return ParseResponse(ok=False, params=[], constats=[], events_count=0, has_stop=False, errors=str(e))


@router.post("/price", response_model=PricingResponse)
def price_endpoint(req: PricingRequest):
    # Sync (threadpool) on purpose: run_mc is CPU-bound for seconds — an
    # `async def` here would hold the event loop and freeze the whole API
    # for every other request while a pricing runs. Same for every other
    # MC-driven endpoint in this file.
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)

    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)

    try:
        result = run_mc(
            script=compiled,
            underlyings=uls,
            corr_matrix=corr,
            r=req.r,
            T_max=T_eff,
            N=req.N,
            model=req.model,
            seed=req.seed,
            antithetic=req.antithetic,
            user_params=req.user_params,
            yield_curve=req.yield_curve or [],
            sigma_r=req.sigma_r,
            a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
        )

        greeks: dict = {}
        if req.compute_greeks and req.selected_greeks:
            greeks = compute_greeks(
                compiled, uls, corr, req.r, T_eff,
                req.N, req.model, req.seed, req.user_params,
                selected=req.selected_greeks, sigma_r=req.sigma_r, a_r=req.a_r,
                yield_curve=req.yield_curve or [],
                barrier_monitoring=req.barrier_monitoring,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return PricingResponse(
        price=result["price"],
        ic95=result["ic95"],
        median=result["median"],
        var5=result["var5"],
        prob_gt100=result["prob_gt100"],
        payoffs=result["payoffs"],
        flux_table=_clean_flux(result["flux_table"]),
        greeks=greeks,
        elapsed_ms=result["elapsed_ms"],
        n_paths=result["n_paths"],
        n_eff=result["n_eff"],
        t_max_effective=round(T_eff, 4),
        fugit=result.get("fugit"),
    )


@router.post("/profile")
def profile_endpoint(req: ProfileRequest):
    """Payoff profile — sweep spot 40%–200%, quasi-deterministic."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        return run_payoff_profile(compiled, uls, corr, req.r, T_eff, req.user_params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/paths")
def paths_endpoint(req: PathsRequest):
    """Monte Carlo sample paths for visualization."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        return run_mc_paths(
            compiled, uls, corr, req.r, T_eff,
            N_display=req.N_display,
            N_stat=req.N_stat,
            model=req.model,
            seed=req.seed,
            user_params=req.user_params,
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/proba")
def proba_endpoint(req: ProbaRequest):
    """Probability analysis — P(autocall), P(KI), expected life, percentiles."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        return run_mc_proba(
            compiled, uls, corr, req.r, T_eff,
            N=req.N,
            model=req.model,
            seed=req.seed,
            user_params=req.user_params,
            yield_curve=req.yield_curve or [],
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/mtf")
def mtf_endpoint(req: MtfRequest):
    """Mark-to-Future — nested Monte Carlo: distribution of future mark-to-model
    values of the product, under the risk-neutral measure with frozen market params."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        return run_mark_to_future(
            compiled, uls, corr, req.r, T_eff,
            main_price=req.main_price,
            model=req.model,
            n_outer=req.n_outer,
            n_inner=req.n_inner,
            n_dates=req.n_dates,
            seed=req.seed,
            user_params=req.user_params,
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/backtest")
def backtest_endpoint(req: BacktestRequest):
    """Historical backtest — replay script on actual Yahoo Finance price history."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers = [u.ticker for u in req.underlyings if u.ticker.strip()]
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun ticker défini dans les sous-jacents.")

    # Load historical prices
    px_data = load_hist_prices(tickers, req.start_date, req.end_date)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])

    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    missing = [tk for tk in tickers if tk not in prices]
    if missing:
        raise HTTPException(status_code=422, detail=f"Tickers manquants dans l'historique: {missing}")

    T_eff = effective_T_max(compiled, req.T)
    SY_H = 252
    days_T = round(T_eff * SY_H)
    max_start = len(dates) - days_T - 1
    if max_start < 1:
        raise HTTPException(status_code=422, detail="Historique trop court pour la maturité du produit.")

    windows = list(range(0, max_start + 1, req.freq))
    results = []
    invest_dec = req.invest_pct / 100.0

    try:
        for si in windows:
            res = eval_script_on_history(
                compiled, dates, prices, si, T_eff, req.user_params, tickers, req.r
            )
            if res is None:
                continue
            cfs = [{"t": 0.0, "cf": -invest_dec}] + res["cash_flows"]
            irr = compute_irr(cfs)
            if irr is not None:
                results.append({
                    "date": dates[si],
                    "irr": round(irr, 4),
                    "T_actual": round(res["T_actual"], 3),
                    "early_recall": res["early_recall"],
                })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not results:
        raise HTTPException(status_code=422, detail="Aucun résultat de backtest (données insuffisantes ou script incompatible).")

    irrs = [r["irr"] for r in results]
    n = len(irrs)
    sorted_irrs = sorted(irrs)
    mean_irr = sum(irrs) / n
    median_irr = sorted_irrs[n // 2]
    p10 = sorted_irrs[int(n * 0.10)]
    p90 = sorted_irrs[int(n * 0.90)]
    positive = sum(1 for v in irrs if v > 0)
    early_recalls = sum(1 for r in results if r["early_recall"])
    rf = req.rf_rate / 100.0
    excess = [v - rf for v in irrs]
    ex_mean = sum(excess) / n
    ex_std = (sum((v - ex_mean)**2 for v in excess) / n) ** 0.5
    sharpe = round(ex_mean / ex_std, 3) if ex_std > 1e-6 else None

    # Consecutive rolling windows spaced `freq` days apart, each covering
    # `days_T` days, share `days_T - freq` days of the same price history
    # when freq < days_T — the closer freq is to 0, the more their outcomes
    # are the same realization replayed, not independent draws. That
    # inflates this cross-window Sharpe (shrinks its denominator) without
    # reflecting genuine risk-adjusted return — see BacktestTab.vue caveat.
    overlap_pct = round(100 * max(0, days_T - req.freq) / days_T, 1) if days_T else 0.0

    return {
        "rows": results,
        "n_windows": n,
        "mean_irr": round(mean_irr, 4),
        "median_irr": round(median_irr, 4),
        "p10": round(p10, 4),
        "p90": round(p90, 4),
        "pct_positive": round(positive / n * 100, 1),
        "early_recall_pct": round(early_recalls / n * 100, 1),
        "sharpe": sharpe,
        "overlap_pct": overlap_pct,
    }


# ── Underlying comparator ──────────────────────────────────────────────
# Same script, same params, swap the underlying(s) and see which ones would
# have backtested best. See BacktestCompareRequest docstring for the
# two-stage funnel (individual screen, then combinations only within the
# shortlist) — an exhaustive combinatorial scan is not feasible.

def _windowed_backtest(compiled, dates, prices, tickers, T_eff, freq, r, invest_pct, user_params,
                        return_windows=False):
    """Sliding-window historical replay for a fixed set of tickers — the
    core loop shared by /backtest, /backtest/compare and the reinvestment
    proposal (api/deals.py). Returns summary stats only by default (the
    comparator only needs the ranking) — return_windows=True additionally
    attaches a per-window {start_date, irr, early_recall} list, used by the
    proposal to plot the product's realized outcome against the underlying's
    price history (opt-in: keeps /backtest/compare's response light across
    its up-to-20-candidate pool)."""
    SY_H = 252
    days_T = round(T_eff * SY_H)
    max_start = len(dates) - days_T - 1
    if max_start < 1:
        return None

    windows = range(0, max_start + 1, freq)
    invest_dec = invest_pct / 100.0
    irrs, early_recalls = [], 0
    window_rows = [] if return_windows else None
    for si in windows:
        res = eval_script_on_history(compiled, dates, prices, si, T_eff, user_params, tickers, r)
        if res is None:
            continue
        cfs = [{"t": 0.0, "cf": -invest_dec}] + res["cash_flows"]
        irr = compute_irr(cfs)
        if irr is None:
            continue
        irrs.append(irr)
        if res["early_recall"]:
            early_recalls += 1
        if return_windows:
            window_rows.append({"start_date": dates[si], "irr": round(irr, 4),
                                 "early_recall": res["early_recall"]})

    if not irrs:
        return None
    n = len(irrs)
    sorted_irrs = sorted(irrs)
    result = {
        "n_windows": n,
        "mean_irr": round(sum(irrs) / n, 4),
        "median_irr": round(sorted_irrs[n // 2], 4),
        # A good median/mean can still hide a real loss tail (worst-of
        # payoffs are asymmetric: mostly clustered near the coupon, with a
        # thin but real chance of a sharp capital loss) — surface it here
        # rather than only in the full single-underlying Backtest tab.
        "p10_irr": round(sorted_irrs[int(n * 0.10)], 4),
        "worst_irr": round(sorted_irrs[0], 4),
        "pct_positive": round(sum(1 for v in irrs if v > 0) / n * 100, 1),
        "early_recall_pct": round(early_recalls / n * 100, 1),
    }
    if return_windows:
        result["windows"] = window_rows
    return result


def _realized_corr(prices: dict, tickers: list) -> list:
    """Pairwise correlation of daily log returns — the actual historical
    joint behaviour of this basket, not an assumed/default matrix, since
    the price history needed is already in hand from the backtest."""
    n = len(tickers)
    if n == 1:
        return [[1.0]]
    min_len = min(len(prices[tk]) for tk in tickers)
    series = []
    for tk in tickers:
        px = np.array(prices[tk][-min_len:], dtype=np.float64)
        px = np.where(px > 0, px, np.nan)
        series.append(np.diff(np.log(px)))
    mat = np.array(series)
    valid = ~np.isnan(mat).any(axis=0)
    mat = mat[:, valid]
    if mat.shape[1] < 10:
        return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    corr = np.corrcoef(mat)
    return [[round(float(corr[i][j]), 4) for j in range(n)] for i in range(n)]


@router.post("/backtest/compare")
def backtest_compare_endpoint(req: BacktestCompareRequest):
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers, ticker_name = [], {}
    for c in req.candidates:
        tk = c.ticker.strip()
        if tk and tk not in ticker_name:
            tickers.append(tk)
            ticker_name[tk] = c.name or tk
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun ticker dans la liste des sous-jacents (Marché & Paramètres).")
    if len(tickers) < req.basket_size:
        raise HTTPException(status_code=422,
            detail=f"Il faut au moins {req.basket_size} sous-jacent(s) distinct(s) pour un panier de taille {req.basket_size}.")

    px_data = load_hist_prices(tickers, req.start_date, req.end_date)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])
    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    tickers = [tk for tk in tickers if tk in prices]
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun historique trouvé pour ces tickers.")

    T_eff = effective_T_max(compiled, req.T)

    # Stage 1 — every candidate alone, cheap (O(N) backtests)
    stage1 = []
    for tk in tickers:
        summary = _windowed_backtest(compiled, dates, prices, [tk], T_eff, req.freq, req.r, req.invest_pct, req.user_params)
        if summary is not None:
            stage1.append({"tickers": [tk], "names": [ticker_name[tk]], "corr_matrix": [[1.0]], **summary})
    if not stage1:
        raise HTTPException(status_code=422, detail="Aucun résultat de backtest (historique insuffisant pour tous les candidats).")
    stage1.sort(key=lambda r_: r_["median_irr"], reverse=True)

    if req.basket_size == 1:
        return {"stage": "individual", "results": stage1, "shortlist": [r_["tickers"][0] for r_ in stage1]}

    # Stage 2 — combinations, but only within the top performers of stage 1
    shortlist = [r_["tickers"][0] for r_ in stage1[:req.shortlist_n]]
    if len(shortlist) < req.basket_size:
        raise HTTPException(status_code=422,
            detail=f"Seulement {len(shortlist)} candidat(s) exploitable(s) pour un panier de {req.basket_size}.")

    n_combos = math.comb(len(shortlist), req.basket_size)
    MAX_COMBOS = 3000
    if n_combos > MAX_COMBOS:
        raise HTTPException(status_code=422,
            detail=f"{n_combos} combinaisons à tester (top {len(shortlist)} candidats, panier de {req.basket_size}) "
                   f"— trop pour rester rapide (max {MAX_COMBOS}). Réduisez la shortlist ou la taille du panier.")

    combos = []
    for combo in itertools.combinations(shortlist, req.basket_size):
        combo = list(combo)
        summary = _windowed_backtest(compiled, dates, prices, combo, T_eff, req.freq, req.r, req.invest_pct, req.user_params)
        if summary is not None:
            combos.append({
                "tickers": combo, "names": [ticker_name[tk] for tk in combo],
                "corr_matrix": _realized_corr(prices, combo), **summary,
            })
    if not combos:
        raise HTTPException(status_code=422, detail="Aucune combinaison exploitable (historique insuffisant).")
    combos.sort(key=lambda r_: r_["median_irr"], reverse=True)

    return {"stage": "combinations", "results": combos, "shortlist": shortlist, "individual": stage1}
