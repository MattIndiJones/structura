from fastapi import APIRouter, HTTPException
from ..core.schemas import (
    PricingRequest, PricingResponse, ParseRequest, ParseResponse,
    ProfileRequest, PathsRequest, ProbaRequest, BacktestRequest, MtfRequest,
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
async def parse_endpoint(req: ParseRequest):
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
            } for p in compiled.params],
            constats=[{"name": c.name, "kind": c.kind} for c in compiled.constats],
            events_count=len(compiled.events),
            has_stop=compiled.has_stop,
        )
    except ValueError as e:
        return ParseResponse(ok=False, params=[], constats=[], events_count=0, has_stop=False, errors=str(e))


@router.post("/price", response_model=PricingResponse)
async def price_endpoint(req: PricingRequest):
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
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
    )

    greeks: dict = {}
    if req.compute_greeks and req.selected_greeks:
        greeks = compute_greeks(
            compiled, uls, corr, req.r, T_eff,
            req.N, req.model, req.seed, result["price"], req.user_params,
            selected=req.selected_greeks, sigma_r=req.sigma_r, a_r=req.a_r,
        )

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
async def profile_endpoint(req: ProfileRequest):
    """Payoff profile — sweep spot 40%–200%, quasi-deterministic."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    return run_payoff_profile(compiled, uls, corr, req.r, T_eff, req.user_params)


@router.post("/paths")
async def paths_endpoint(req: PathsRequest):
    """Monte Carlo sample paths for visualization."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    return run_mc_paths(
        compiled, uls, corr, req.r, T_eff,
        N_display=req.N_display,
        N_stat=req.N_stat,
        model=req.model,
        seed=req.seed,
        user_params=req.user_params,
    )


@router.post("/proba")
async def proba_endpoint(req: ProbaRequest):
    """Probability analysis — P(autocall), P(KI), expected life, percentiles."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    return run_mc_proba(
        compiled, uls, corr, req.r, T_eff,
        N=req.N,
        model=req.model,
        seed=req.seed,
        user_params=req.user_params,
    )


@router.post("/mtf")
async def mtf_endpoint(req: MtfRequest):
    """Mark-to-Future — nested Monte Carlo: distribution of future mark-to-model
    values of the product, under the risk-neutral measure with frozen market params."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
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
    return run_mark_to_future(
        compiled, uls, corr, req.r, T_eff,
        main_price=req.main_price,
        model=req.model,
        n_outer=req.n_outer,
        n_inner=req.n_inner,
        n_dates=req.n_dates,
        seed=req.seed,
        user_params=req.user_params,
    )


@router.post("/backtest")
async def backtest_endpoint(req: BacktestRequest):
    """Historical backtest — replay script on actual Yahoo Finance price history."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats)
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
    }
