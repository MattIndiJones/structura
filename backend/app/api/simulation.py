"""Simulation API endpoints — PARAM solver (target price) and 2D price grid/heatmap.

Both endpoints share the same validation shape: parse the script, check the
requested PARAM name(s) actually exist in it, check the correlation matrix
dimensions, then delegate to core/payscript/simulation.py for the math.
"""
from fastapi import APIRouter, HTTPException
from ..core.schemas import SolverRequest, GridRequest
from ..core.payscript.parser import parse_script, resolve_analysis_constats, resolve_constats, effective_T_max
from ..core.payscript.simulation import solve_for_param, compute_price_grid

router = APIRouter(prefix="/api", tags=["simulation"])


def _parse_and_validate(req) -> tuple:
    """Common setup: parse the script, build underlyings/corr, check dimensions.
    Returns (compiled, uls, corr, T_eff) — T_eff is req.T extended to cover
    every (possibly CONSTAT-resolved) event date, see effective_T_max."""
    from .pricing import residual_context_or_none
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            # Solveur et grille portent sur la VIE RESTANTE quand une date de
            # valorisation est saisie : chercher le coupon qui met la note au
            # pair a l'emission n'a rien a voir avec le chercher sur ce qu'il
            # reste a courir, coupons deja accumules compris.
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
            yc = ctx.sur_axe_residuel(req.yield_curve)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, None
            etat, yc = None, (req.yield_curve or [])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    if T_eff is None:
        T_eff = effective_T_max(compiled, req.T)
    return compiled, uls, corr, T_eff, r_eff, etat, yc, ctx


def _check_param_exists(compiled, param_name: str):
    if param_name not in {p.name for p in compiled.params}:
        raise HTTPException(status_code=422,
                             detail=f"Paramètre inconnu dans le script: {param_name}")


@router.post("/solve")
def solve_endpoint(req: SolverRequest):
    """Bisection solve: find the PARAM value that hits a target price."""
    from .pricing import analysis_user_params
    compiled, uls, corr, T_eff, r_eff, etat, yc, ctx = _parse_and_validate(req)
    _check_param_exists(compiled, req.param_name)

    try:
        res = solve_for_param(
            compiled, uls, corr, r_eff, T_eff, req.model, req.seed,
            # Les PARAM de la vie restante. `compiled` porte ceux de la
            # variante quand elle change le SCRIPT ; un delta qui ne change
            # qu'un PARAM ne passait par aucun des deux, et le solveur
            # comme la grille repriçaient l'origine sous étiquette de
            # variante.
            analysis_user_params(req, ctx),
            req.param_name, req.target_price, req.lo, req.hi,
            N=req.N, tol=req.tol, max_iter=req.max_iter,
            yield_curve=yc, sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring, state=etat,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res


@router.post("/grid")
def grid_endpoint(req: GridRequest):
    """2D price heatmap over two PARAM ranges."""
    from .pricing import analysis_user_params
    compiled, uls, corr, T_eff, r_eff, etat, yc, ctx = _parse_and_validate(req)
    _check_param_exists(compiled, req.param_x)
    _check_param_exists(compiled, req.param_y)
    if req.param_x == req.param_y:
        raise HTTPException(status_code=422,
                             detail="Les deux axes doivent porter sur des paramètres différents.")

    try:
        res = compute_price_grid(
            compiled, uls, corr, r_eff, T_eff, req.model, req.seed,
            # Les PARAM de la vie restante. `compiled` porte ceux de la
            # variante quand elle change le SCRIPT ; un delta qui ne change
            # qu'un PARAM ne passait par aucun des deux, et le solveur
            # comme la grille repriçaient l'origine sous étiquette de
            # variante.
            analysis_user_params(req, ctx),
            req.param_x, req.x_min, req.x_max, req.x_steps,
            req.param_y, req.y_min, req.y_max, req.y_steps,
            N=req.N,
            yield_curve=yc, sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring, state=etat,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res
