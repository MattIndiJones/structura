"""Scenario API endpoint — stress grid: price under combined spot x vol shocks."""
from fastapi import APIRouter, HTTPException
from ..core.schemas import ScenarioRequest
from ..core.payscript.parser import analysis_origin, parse_script, resolve_analysis_constats, effective_T_max
from ..core.payscript.scenarios import compute_scenario_grid

router = APIRouter(prefix="/api", tags=["scenarios"])


@router.post("/scenarios")
def scenarios_endpoint(req: ScenarioRequest):
    """2D stress grid — price(spot_shock, vol_shock) plus the unshocked base price."""
    from .pricing import residual_context_or_none
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled = ctx.script
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    if ctx is not None:
        # La grille reprice chaque cellule dans un processus separe : l'etat du
        # passe voyage donc en donnees. Les sous-jacents du rejeu remplacent
        # ceux de la requete (calibration effective), et le choc de spot se
        # compose multiplicativement sur le niveau du jour.
        uls = ctx.underlyings
        etat = ctx.mc_kwargs
        spots = etat.pop("spot_mult", None)
        etat.pop("spot_base", None)
        r_eff, T_eff = ctx.r, ctx.T_remaining
        yc = ctx.sur_axe_residuel(req.yield_curve)
    else:
        etat, spots, r_eff, yc = None, None, req.r, (req.yield_curve or [])
        T_eff = effective_T_max(compiled, req.T)

    try:
        res = compute_scenario_grid(
            req.script, uls, corr, r_eff, T_eff, req.model, req.seed, req.user_params,
            req.spot_shocks, req.vol_shocks, N=req.N,
            yield_curve=yc, sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
            constat_values=req.constats or None,
            constat_anchor=analysis_origin(req).isoformat(),
            constat_currency=req.settlement_ccy,
            residual_state=etat, state_spots=spots,
            residual_elapsed=ctx.T_elapsed if ctx is not None else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(res, dict):
        res["in_life"] = ctx is not None
        if ctx is not None:
            res["valuation_date"] = ctx.valuation.isoformat()
            res["years_remaining"] = round(ctx.T_remaining, 4)
    return res
