"""Scenario API endpoint — stress grid: price under combined spot x vol shocks."""
from fastapi import APIRouter, HTTPException
from ..core.schemas import ScenarioRequest
from ..core.payscript.parser import analysis_origin, parse_script, resolve_analysis_constats, effective_T_max
from ..core.payscript.scenarios import compute_scenario_grid
from ..core.compute_budget import (
    count_compiled_dates,
    ensure_budget,
    estimate_mc_batch,
    validate_compiled_dates,
)

router = APIRouter(prefix="/api", tags=["scenarios"])


@router.post("/scenarios")
def scenarios_endpoint(req: ScenarioRequest):
    """2D stress grid — price(spot_shock, vol_shock) plus the unshocked base price."""
    from .pricing import analysis_user_params, residual_context_or_none
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
        strike_set_t = ctx.residuel.strike_set_t
        maturity_payment_t = ctx.payment_t
        value_date_t = 0.0
    else:
        etat, spots, r_eff, yc = None, None, req.r, (req.yield_curve or [])
        T_eff = effective_T_max(compiled, req.T)
        origin = analysis_origin(req)
        strike_set_t = None
        maturity_payment_t = (
            round((req.payment_date - origin).days / 365.25, 6)
            if req.payment_date else None)
        value_date_t = (
            round((req.value_date - origin).days / 365.25, 6)
            if req.value_date else 0.0)

    try:
        validate_compiled_dates(compiled)
        calculation_budget = estimate_mc_batch(
            operation="scenario_grid",
            maturity_years=T_eff,
            underlyings=n,
            paths_per_run=req.N,
            total_runs=1 + len(req.spot_shocks) * len(req.vol_shocks),
            model=req.model,
            antithetic=True,
            continuous_monitoring=req.barrier_monitoring == "continuous",
            stochastic_rates=req.sigma_r > 0,
            concurrent_runs=4,
            expanded_dates=count_compiled_dates(compiled),
        )
        ensure_budget(calculation_budget)
        # Le TEXTE, les PARAM et le calendrier QUI PRICENT — ceux de la variante
        # s'il y en a une. `compiled` ci-dessus les portait déjà, mais un
        # CompiledScript ne traverse pas une frontière de processus : le worker
        # reçoit du texte et recompile. Passer `req.*` ici revenait donc à
        # calculer le script de la variante, le valider, puis le jeter — la
        # grille décrivait le produit d'ORIGINE sous une étiquette de variante,
        # au dernier chiffre près. C'est la seule des cinq analytiques qui le
        # faisait ; la grille 2D, de forme identique, passe `compiled`.
        res = compute_scenario_grid(
            ctx.script_text if ctx is not None else req.script,
            uls, corr, r_eff, T_eff, req.model, req.seed,
            analysis_user_params(req, ctx),
            req.spot_shocks, req.vol_shocks, N=req.N,
            yield_curve=yc, sigma_r=req.sigma_r, a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
            constat_values=(ctx.constats if ctx is not None else req.constats) or None,
            constat_anchor=analysis_origin(req).isoformat(),
            constat_currency=req.settlement_ccy,
            residual_state=etat, state_spots=spots,
            residual_elapsed=ctx.T_elapsed if ctx is not None else None,
            residual_passe=ctx.residuel.passe_jusqu_a if ctx is not None else None,
            residual_releves=(ctx.residuel.state.get("releves_realises")
                              if ctx is not None else None),
            strike_set_t=strike_set_t,
            maturity_payment_t=maturity_payment_t,
            value_date_t=value_date_t,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(res, dict):
        res["in_life"] = bool(ctx is not None and ctx.T_elapsed > 0)
        res["pre_strike"] = bool(ctx is not None and ctx.residuel.pre_strike)
        if ctx is not None:
            res["valuation_date"] = ctx.valuation.isoformat()
            res["years_remaining"] = round(ctx.T_remaining, 4)
        res["calculation_budget"] = calculation_budget.to_dict()
    return res
