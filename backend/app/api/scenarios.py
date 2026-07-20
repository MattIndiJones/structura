"""Scenario API endpoint — stress grid: price under combined spot x vol shocks."""
from fastapi import APIRouter, HTTPException
from ..core.schemas import ScenarioRequest
from ..core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ..core.payscript.scenarios import compute_scenario_grid

router = APIRouter(prefix="/api", tags=["scenarios"])


@router.post("/scenarios")
def scenarios_endpoint(req: ScenarioRequest):
    """2D stress grid — price(spot_shock, vol_shock) plus the unshocked base price."""
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
    try:
        return compute_scenario_grid(
            compiled, uls, corr, req.r, T_eff, req.model, req.seed, req.user_params,
            req.spot_shocks, req.vol_shocks, N=req.N,
            yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
