"""Simulation API endpoints — PARAM solver (target price) and 2D price grid/heatmap.

Both endpoints share the same validation shape: parse the script, check the
requested PARAM name(s) actually exist in it, check the correlation matrix
dimensions, then delegate to core/payscript/simulation.py for the math.
"""
from fastapi import APIRouter, HTTPException
from ..core.schemas import SolverRequest, GridRequest
from ..core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ..core.payscript.simulation import solve_for_param, compute_price_grid

router = APIRouter(prefix="/api", tags=["simulation"])


def _parse_and_validate(req) -> tuple:
    """Common setup: parse the script, build underlyings/corr, check dimensions.
    Returns (compiled, uls, corr, T_eff) — T_eff is req.T extended to cover
    every (possibly CONSTAT-resolved) event date, see effective_T_max."""
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

    return compiled, uls, corr, effective_T_max(compiled, req.T)


def _check_param_exists(compiled, param_name: str):
    if param_name not in {p.name for p in compiled.params}:
        raise HTTPException(status_code=422,
                             detail=f"Paramètre inconnu dans le script: {param_name}")


@router.post("/solve")
def solve_endpoint(req: SolverRequest):
    """Bisection solve: find the PARAM value that hits a target price."""
    compiled, uls, corr, T_eff = _parse_and_validate(req)
    _check_param_exists(compiled, req.param_name)

    try:
        return solve_for_param(
            compiled, uls, corr, req.r, T_eff, req.model, req.seed, req.user_params,
            req.param_name, req.target_price, req.lo, req.hi,
            N=req.N, tol=req.tol, max_iter=req.max_iter,
            yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/grid")
def grid_endpoint(req: GridRequest):
    """2D price heatmap over two PARAM ranges."""
    compiled, uls, corr, T_eff = _parse_and_validate(req)
    _check_param_exists(compiled, req.param_x)
    _check_param_exists(compiled, req.param_y)
    if req.param_x == req.param_y:
        raise HTTPException(status_code=422,
                             detail="Les deux axes doivent porter sur des paramètres différents.")

    try:
        return compute_price_grid(
            compiled, uls, corr, req.r, T_eff, req.model, req.seed, req.user_params,
            req.param_x, req.x_min, req.x_max, req.x_steps,
            req.param_y, req.y_min, req.y_max, req.y_steps,
            N=req.N,
            yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
