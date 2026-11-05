import itertools
import hashlib
import json
from dataclasses import replace
from datetime import date
import math
import os
from pathlib import Path
import tempfile
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from ..core.simulation_grid import with_request_grid
from ..core.payscript.engine import _simulation_axis
from pydantic import BaseModel
from ..core.schemas import (
    PricingRequest, PricingResponse, ParseRequest, ParseResponse,
    ProfileRequest, PathsRequest, ProbaRequest, BacktestRequest, BacktestCompareRequest, BacktestCompareDetailRequest,
    MtfRequest, MtfComparisonRequest, MtfDrilldownRequest, ScriptGenerateRequest,
)
from ..core.payscript.parser import analysis_origin, parse_script, resolve_analysis_constats, effective_T_max
from ..core.payscript.engine import (
    run_mc, compute_greeks,
    run_payoff_profile, run_mc_paths, run_mc_proba,
    eval_script_on_history, compute_irr, derniere_fenetre, seances_jusqu_a,
    run_mark_to_future, run_mtf_drilldown, MTF_MAX_BATCH, mtf_date_grid, mtf_simulation_axis,
)
from ..services.market_data import load_hist_prices
from ..core.calendars import UnsupportedCurrency
from ..core.compute_budget import (
    ABSOLUTE_WORK_LIMIT, WORKER_MEMORY_LIMIT_BYTES, estimate_mc,
    count_compiled_dates,
    ensure_budget,
    estimate_mc_batch,
    estimate_pricing_request,
    validate_compiled_dates,
    validate_problem_dimensions,
)
from ..core.valuation_context import (
    ValuationContext, build_pricing_receipt, run_valuation, run_analysis,
    valuation_context_from_request, validate_mtf_context,
)
from ..services.product_receipts import signed_receipt
from ..services.calibration_evidence import validate_pricing_calibrations
from .auth import get_current_pricer, receipt_signing_secret

router = APIRouter(
    prefix="/api", tags=["pricing"],
    dependencies=[Depends(get_current_pricer)],
)


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
            # When the cash actually moves. Equal to t when nothing settles
            # later, which is what makes df readable as exp(-r·t).
            "t_pay": round(v.get("t_pay", v["t"]), 6),
            "lbl": v["lbl"],
            "n":   v["n"],
            "sum": sm,
            "pv":  pv,
            "df":  df,
        }
    return result


@router.post("/parse", response_model=ParseResponse)
@with_request_grid
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
                "required": p.required,
                "observation_calendar": p.observation_calendar,
            } for p in compiled.params],
            constats=[{"name": c.name, "kind": c.kind, "reduction": c.reduction,
                       "window_scope": c.window_scope, "role": c.role} for c in compiled.constats],
            underlying=compiled.underlying_name,
            initial_fixing=compiled.initial_fixing_name,
            events_count=len(compiled.events),
            has_stop=compiled.has_stop,
            has_maturity_event=any(
                event.type == "AT_MATURITY" for event in compiled.events),
            # The years written in `AT 1, 2, 3:` — known at parse time, unlike
            # CONSTAT dates. The Pricer dates them from the strike to keep the
            # maturity on or after the last observation the script declares.
            at_dates=sorted({round(float(d), 6)
                             for event in compiled.events for d in (event.dates or [])}),
            monitors=compiled.monitors or [],
        )
    except ValueError as e:
        return ParseResponse(ok=False, params=[], constats=[], events_count=0,
                             has_stop=False, has_maturity_event=False,
                             errors=str(e))


@router.post("/price", response_model=PricingResponse)
@with_request_grid
def price_endpoint(req: PricingRequest):
    # Sync (threadpool) on purpose: run_mc is CPU-bound for seconds — an
    # `async def` here would hold the event loop and freeze the whole API
    # for every other request while a pricing runs. Same for every other
    # MC-driven endpoint in this file.
    # L'axe du temps s'ancre sur la date de strike : c'est là que le niveau
    # initial est constaté, donc là que la diffusion démarre. Sans elle, on
    # retombe sur `anchor` — la value date, comme avant.
    try:
        origin = analysis_origin(req)
        compiled = parse_script(req.script)
        # Meme resolveur que toutes les analytiques : c'est ce qui garantit que
        # le profil, les probas ou la grille decrivent le produit qu'on price.
        compiled = resolve_analysis_constats(compiled, req)
    except (ValueError, UnsupportedCurrency) as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    # La date de paiement finale se compte sur le même axe que les
    # constatations : celui ancré sur `anchor`.
    maturity_payment_t = None
    if req.payment_date is not None:
        maturity_payment_t = round((req.payment_date - origin).days / 365.25, 6)
    value_date_t = (round((req.value_date - origin).days / 365.25, 6)
                    if req.value_date is not None else 0.0)

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)

    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)

    try:
        from ..core.payscript.lsv_leverage import supports_frozen_lsv
        frozen_lsv = req.model == "lsv" and supports_frozen_lsv(
            uls, yield_curve=req.yield_curve, sigma_r=req.sigma_r,
            barrier_monitoring=req.barrier_monitoring)
        if not frozen_lsv:
            validate_pricing_calibrations(req, T_eff, secret=receipt_signing_secret())
        validate_compiled_dates(compiled)
        calculation_budget = estimate_pricing_request(
            corr_matrix=corr,
            maturity_years=T_eff,
            underlyings=n,
            paths=req.N,
            model=req.model,
            antithetic=req.antithetic,
            continuous_monitoring=req.barrier_monitoring == "continuous",
            stochastic_rates=req.sigma_r > 0,
            selected_greeks=(req.selected_greeks
                             if req.compute_greeks else None),
            expanded_dates=count_compiled_dates(compiled),
            steps_per_year=req.steps_per_year,
            simulation_steps=_simulation_axis(T_eff,compiled, steps_per_year=req.steps_per_year)[0])
        if frozen_lsv:
            from ..core.payscript.lsv_leverage import TRAINING_PATHS
            calculation_budget = replace(
                calculation_budget,
                work_units=calculation_budget.work_units + calculation_budget.steps * n * TRAINING_PATHS,
                estimated_peak_bytes=max(calculation_budget.estimated_peak_bytes, 96 * TRAINING_PATHS))
        ensure_budget(calculation_budget)
        valuation_context = valuation_context_from_request(req, compiled)
        result = run_valuation(compiled, valuation_context)

        greeks: dict = {}
        if req.compute_greeks and req.selected_greeks:
            greeks = compute_greeks(
                compiled, uls, corr, req.r, T_eff,
                req.N, req.model, req.seed, req.user_params,
                selected=req.selected_greeks, sigma_r=req.sigma_r, a_r=req.a_r,
                antithetic=req.antithetic,
                yield_curve=req.yield_curve or [],
                funding_curve=req.funding_curve or [],
                funding_spread=req.funding_spread,
                barrier_monitoring=req.barrier_monitoring,
                maturity_payment_t=maturity_payment_t,
                value_date_t=value_date_t,
            steps_per_year=req.steps_per_year)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return PricingResponse(
        steps_per_year=req.steps_per_year, time_axis=result.get("time_axis"),
        surface_context=result.get('surface_context'), lsv_calibration=result.get('lsv_calibration'),
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
        constatation_windows=result.get("constatation_windows"),
        schedule=(compiled.echeancier.to_dict()
                  if getattr(compiled, "echeancier", None) else None),
        calculation_budget=calculation_budget.to_dict(),
        pricing_receipt=signed_receipt(
            build_pricing_receipt(req, result["price"]),
            secret=receipt_signing_secret(),
            result={
                "price": result["price"],
                "ic95": result["ic95"],
                "median": result["median"],
                "var5": result["var5"],
                "prob_gt100": result["prob_gt100"],
            },
        ),
        corr_repair=result.get("corr_repair"),
        barrier_monitoring=result.get("barrier_monitoring", req.barrier_monitoring),
        barrier_monitoring_note=result.get("barrier_monitoring_note"),
        barrier_monitoring_details=result.get("barrier_monitoring_details"),
        local_vol_wings=result.get("local_vol_wings"),
        lsv_frozen_leverage=result.get("lsv_frozen_leverage"),
        lsv_limits=result.get("lsv_limits"),
    )


@router.post("/profile")
@with_request_grid
def profile_endpoint(req: ProfileRequest):
    """Payoff profile — sweep spot 40%–200%, quasi-deterministic.

    En cours de vie, le profil se dessine sur la jambe RÉSIDUELLE : mêmes
    niveaux balayés, mais avec les coupons déjà accumulés et les barrières
    déjà franchies. Sans ça la courbe est celle du produit neuf, ce qui sur
    une note en difficulté raconte une autre histoire que la sienne.
    """
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff = ctx.r, ctx.T_remaining
            etat = ctx.mc_kwargs
            # Le balayage pince le spot lui-même : le multiplicateur de spot du
            # rejeu n'a pas lieu d'être ici, il ferait double emploi.
            etat.pop("spot_mult", None)
            etat.pop("spot_base", None)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat = None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    try:
        validate_compiled_dates(compiled)
        validate_problem_dimensions(T_eff, n)
        res = run_payoff_profile(compiled, uls, corr, r_eff, T_eff,
                                  analysis_user_params(req, ctx), state=etat, steps_per_year=req.steps_per_year)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 12)
    return res


@with_request_grid
def analysis_user_params(req, ctx):
    """Les PARAM que l'analytique doit employer.

    Sur une jambe résiduelle d'avenant, ce sont ceux de la VARIANTE : la
    requête, elle, porte les termes d'origine, qui n'ont servi qu'à rejouer le
    passé. Hors variante les deux coïncident, donc rien ne bouge sur une
    analytique ordinaire."""
    return ctx.user_params if ctx is not None else req.user_params


@with_request_grid
def residual_context_or_none(req, *, retain_terminated=False):
    """Contexte résiduel quand la requête est en cours de vie, sinon None.

    Import différé : inlife.py importe déjà ce module, un import au sommet
    créerait un cycle."""
    valuation = getattr(req, "valuation_date", None)
    strike = getattr(req, "strike_date", None)
    maturity = getattr(req, "maturity_date", None)
    if not (valuation and strike and maturity) or valuation == strike:
        return None
    from .inlife import build_request_residual, variant_terms_or_none
    # La variante suit le prix jusque dans les analytiques : sans ça l'onglet
    # Probabilités décrirait le produit d'origine sous un prix d'avenant, ce
    # qui est exactement l'écart qu'on vient de fermer partout ailleurs.
    ctx = build_request_residual(req, variant_terms_or_none(req), **({"retain_terminated":True} if retain_terminated else {}))
    if ctx.residuel.early_recall and not retain_terminated:
        raise HTTPException(422, 'Produit rappelé : aucune optionalité résiduelle à analyser.')
    return ctx


@router.post("/paths")
@with_request_grid
def paths_endpoint(req: PathsRequest):
    """Monte Carlo sample paths for visualization."""
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
            yc = ctx.sur_axe_residuel(req.yield_curve)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat, yc = None, (req.yield_curve or [])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")
    try:
        validate_compiled_dates(compiled)
        calculation_budget = estimate_mc_batch(
            operation="path_visualisation",
            maturity_years=T_eff,
            underlyings=n,
            paths_per_run=req.N_stat,
            total_runs=1,
            model=req.model,
            antithetic=req.antithetic,
            stochastic_rates=req.sigma_r > 0,
            continuous_monitoring=req.barrier_monitoring == "continuous",
            expanded_dates=count_compiled_dates(compiled),
        )
        ensure_budget(calculation_budget)
        calculation_context = valuation_context_from_request(req, compiled, residual=ctx, paths=req.N_stat)
        if ctx is None:
            validate_pricing_calibrations(req, T_eff, secret=receipt_signing_secret())
        res = run_analysis(compiled, calculation_context, 'paths', N_display=req.N_display)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 12)
    res["calculation_budget"] = calculation_budget.to_dict()
    return res


@router.post("/proba")
@with_request_grid
def proba_endpoint(req: ProbaRequest):
    """Probability analysis — P(autocall), P(KI), expected life, percentiles."""
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
            yc = ctx.sur_axe_residuel(req.yield_curve)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat, yc = None, (req.yield_curve or [])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")
    try:
        validate_compiled_dates(compiled)
        paths_used = min(10_000, max(2_000, req.N))
        calculation_budget = estimate_mc_batch(
            operation="probability_analysis",
            maturity_years=T_eff,
            underlyings=n,
            paths_per_run=paths_used,
            total_runs=1,
            model=req.model,
            antithetic=req.antithetic,
            stochastic_rates=req.sigma_r > 0,
            continuous_monitoring=req.barrier_monitoring == "continuous",
            expanded_dates=count_compiled_dates(compiled),
        )
        ensure_budget(calculation_budget)
        calculation_context = valuation_context_from_request(req, compiled, residual=ctx, paths=req.N)
        if ctx is None:
            validate_pricing_calibrations(req, T_eff, secret=receipt_signing_secret())
        res = run_analysis(compiled, calculation_context, 'proba')
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 12)
    res["calculation_budget"] = calculation_budget.to_dict()
    return res


@with_request_grid
def _mtf_context_fingerprint(script,valuation,dates,flows,req,*,reference_price=None):
    from ..core.product.calendar import EVENT_FIELDS
    calendar = dict(events=[dict(type=event.type,**{key:getattr(event,key) for key in EVENT_FIELDS})
                            for event in script.events],strike_fix_dates=script.strike_fix_dates,
                    strike_fix_reduction=script.strike_fix_reduction,releves_realises=script.releves_realises)
    payload = dict(version='mtf-settlement-v1',calendar=calendar,script=valuation.script_text,
        underlyings=valuation.underlyings,corr=valuation.corr_matrix,r=valuation.r,T=valuation.T,
        model=valuation.model,state=valuation.state,user_params=valuation.user_params,
        payment=valuation.maturity_payment_t,dates=dates,flows=flows,
        n_outer=req.n_outer,n_inner=req.n_inner,seed=req.seed,steps_per_year=req.steps_per_year)
    if valuation.local_vol_anchor is not None:
        payload['local_vol_anchor'] = valuation.local_vol_anchor
    if req.reference_paths is not None:
        payload.update(version='mtf-aligned-model-v1', reference_paths=req.reference_paths,
                       reference_price=req.main_price if reference_price is None else reference_price,
                       antithetic=valuation.antithetic, barrier_monitoring=valuation.barrier_monitoring)
    if req.gbm_atm_curve or req.indicative_heston:
        payload.update(gbm_atm_curve=req.gbm_atm_curve, indicative_heston=req.indicative_heston)
    if req.model == 'lsv':
        from ..core.payscript.lsv_leverage import LEVERAGE_VERSION
        payload['leverage_version'] = LEVERAGE_VERSION
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False,
        default=lambda value:value.tolist() if hasattr(value,'tolist') else value.isoformat())
    if req.gbm_atm_curve or req.indicative_heston or req.model == 'lsv':
        from ..core.valuation_context import json_transport_fingerprint
        return json_transport_fingerprint(json.loads(encoded))
    return hashlib.sha256(encoded.encode()).hexdigest()


@with_request_grid
def _mtf_initial_flows(ctx, req):
    if ctx is None:
        return []
    flows = []
    for flow in ctx.residuel.realized_flows:
        observed = float(flow['t'])-ctx.T_elapsed
        payment = float(flow.get('payment_t',flow['t']))-ctx.T_elapsed
        if flow.get('payment_date'):
            payment = (date.fromisoformat(flow['payment_date'])-ctx.valuation).days/365.25
        if req.payment_date is not None and abs(float(flow['t'])-ctx.produit.tenor) < 1e-6:
            payment = ctx.payment_t
        flows.append(dict(observation_t=observed,payment_t=payment,amount=float(flow['cf']),
                          lbl=flow.get('lbl',flow.get('label','Flux constaté'))))
    return flows


@with_request_grid
def _mtf_request_dates(req,script,horizon,payment,ctx,flows):
    if ctx is not None and ctx.residuel.early_recall:
        last = max([f['payment_t'] for f in flows if f['payment_t'] > 0] or [1/365.25])
        return mtf_date_grid(script,max(last,1/365.25),req.n_dates,
            dates=req.mtm_dates if req.mtm_dates is not None else
                [last*(i+1)/req.n_dates for i in range(req.n_dates)], steps_per_year=req.steps_per_year)
    return mtf_date_grid(script,horizon,req.n_dates,payment,req.mtm_dates, steps_per_year=req.steps_per_year)


_MTF_MODEL_FIELDS = frozenset(('v0', 'kappa', 'theta', 'xi', 'rho_h', 'alpha', 'beta',
                               'rho', 'nu', 'skew', 'curvature', 'smile_parameter_mode',
                               'calibration_evidence'))


@with_request_grid
def _mtf_comparison_key(req):
    shared = req.model_dump(mode='json', exclude={'model', 'main_price', 'gbm_atm_curve', 'indicative_heston'})
    for underlying in shared['underlyings']:
        for field in _MTF_MODEL_FIELDS:
            underlying.pop(field, None)
    return shared


@with_request_grid
def _resolve_pricer_mtf(req):
    ctx = residual_context_or_none(req, retain_terminated=True)
    script = ctx.script if ctx is not None else resolve_analysis_constats(parse_script(req.script), req)
    if not script.events and ctx is None:
        raise ValueError('Aucun événement AT défini dans le script.')
    validate_compiled_dates(script)
    valuation = valuation_context_from_request(req, script, residual=ctx, paths=req.reference_paths)
    flows = _mtf_initial_flows(ctx, req)
    dates = _mtf_request_dates(req, script, valuation.T, valuation.maturity_payment_t, ctx, flows)
    return ctx, script, valuation, flows, dates


@with_request_grid
def _validate_atm_mtf_options(req, valuation, residual):
    if not (req.gbm_atm_curve or req.indicative_heston):
        return
    if (req.reference_paths is None or residual is not None or valuation.T > 10. + 1e-9
            or any(u.get('ccyh') or u.get('sigma_fx')*u.get('rho_sfx')
                   for u in valuation.underlyings)):
        raise ValueError('L’étude ATM est disponible à l’émission, jusqu’à 10 ans et sans quanto.')
    if req.gbm_atm_curve and (req.model != 'constant' or any(
        not (u.get('vol_surface') or {}).get('atm_scenario') for u in valuation.underlyings
    )):
        raise ValueError('Le GBM sur courbe ATM exige une courbe par scénario pour chaque sous-jacent.')
    if req.indicative_heston and req.model != 'heston':
        raise ValueError('L’option de calibration indicative est réservée à Heston.')


@with_request_grid
def _pricer_mtf_job(req, resolved):
    from ..core.compute.pricers.mtf import freeze_mtf_script

    ctx, script, shared, flows, dates = resolved
    # Replay and market fixing happen once. Only model inputs can differ.
    underlyings = [dict(u, **v.model_dump(include=_MTF_MODEL_FIELDS))
                   for u, v in zip(shared.underlyings, req.underlyings)]
    if len(underlyings) != len(shared.underlyings) or len(underlyings) != len(req.underlyings):
        raise ValueError('Panier incompatible avec le contexte du Mark to Future.')
    valuation = replace(shared, model=req.model, underlyings=underlyings, gbm_atm_curve=req.gbm_atm_curve)
    _validate_atm_mtf_options(req, valuation, ctx)
    _validate_lsv_mtf_scope(req, valuation, ctx)
    validate_mtf_context(script, valuation, payment_aware=True, aligned_grid=True)
    terminated = bool(ctx and ctx.residuel.early_recall)
    if not terminated and req.model != 'lsv':
        validate_pricing_calibrations(req, valuation.T, secret=receipt_signing_secret(),
                                      allow_indicative_heston=req.indicative_heston)
    budget = dict(work_units=0, estimated_peak_bytes=0)
    if not terminated:
        steps, _ = mtf_simulation_axis(script, valuation.T, dates, True, steps_per_year=req.steps_per_year)
        common = dict(maturity_years=valuation.T, simulation_steps=steps, model=req.model,
                      underlyings=len(underlyings), expanded_dates=count_compiled_dates(script))
        peak = min(MTF_MAX_BATCH, req.n_outer * req.n_inner)
        inner_runs = sum(t < valuation.T - 1e-9 for t in dates)
        fan = estimate_mc_batch(operation='mark_to_future', paths_per_run=max(peak, req.n_outer),
                                total_runs=(req.n_outer + req.n_outer * req.n_inner * inner_runs)
                                / max(peak, req.n_outer), antithetic=False, **common)
        outer = estimate_mc(operation='mark_to_future_outer', paths=req.n_outer, antithetic=False, **common)
        reference = estimate_mc(operation='mark_to_future_reference', paths=req.reference_paths,
                                antithetic=req.antithetic, **common)
        budget = fan.to_dict()
        budget['work_units'] = fan.work_units + reference.work_units
        if req.model == 'lsv':
            budget['work_units'] += _lsv_qualification_work(steps, len(underlyings), residual=valuation.local_vol_anchor is not None)
        budget['estimated_peak_bytes'] = max(reference.estimated_peak_bytes,
                                             fan.estimated_peak_bytes + outer.estimated_peak_bytes)
        if req.model == 'lsv':
            from ..core.payscript.lsv_leverage import CONTROL_PATHS
            budget['estimated_peak_bytes'] = max(budget['estimated_peak_bytes'], 1536 * CONTROL_PATHS)
        budget['estimated_peak_mb'] = round(budget['estimated_peak_bytes'] / 1024**2, 1)
    settings = dict(mtm_dates=dates, n_outer=req.n_outer, n_inner=req.n_inner, n_dates=req.n_dates,
                    initial_flows=flows, initial_terminated=terminated)
    job = dict(context=valuation.to_dict(), script=freeze_mtf_script(script, valuation.script_text),
               settings=settings)
    return job, valuation, budget


@with_request_grid
def _validate_lsv_mtf_scope(req, valuation, residual):
    if req.model != 'lsv':
        return
    from ..core.payscript.lsv_leverage import supports_frozen_lsv
    if (req.reference_paths is None or not supports_frozen_lsv(
            valuation.underlyings, yield_curve=valuation.yield_curve, sigma_r=valuation.sigma_r,
            barrier_monitoring=valuation.barrier_monitoring, strike_set_t=valuation.strike_set_t,
            residual=residual is not None and valuation.local_vol_anchor is None)):
        raise ValueError("La qualification LSV en MTF exige une surface SSVI par titre, après fixing initial, "
                         "sans quanto, avec taux et dividendes plats et monitoring hebdomadaire.")


def _lsv_qualification_work(steps, underlyings, *, residual=False):
    from ..core.payscript.lsv_leverage import (CONTROL_PATHS, CONTROL_SEEDS, TRAINING_PATHS,
        RESIDUAL_TRAINING_PATHS, RESIDUAL_CONTROL_SEEDS)
    training=RESIDUAL_TRAINING_PATHS if residual else TRAINING_PATHS
    seeds=RESIDUAL_CONTROL_SEEDS if residual else CONTROL_SEEDS
    return steps * underlyings * (training + 2 * CONTROL_PATHS * len(seeds))


def _check_mtf_budget(budgets):
    if (sum(b['work_units'] for b in budgets) > ABSOLUTE_WORK_LIMIT
            or sum(b['estimated_peak_bytes'] for b in budgets) > WORKER_MEMORY_LIMIT_BYTES):
        raise ValueError('Budget cumulé du Mark to Future dépassé. Réduisez les chemins ou le nombre de dates.')


@with_request_grid
def _finish_pricer_mtf(fan, req, resolved, valuation, budget):
    ctx, script, _, flows, dates = resolved
    origin = ctx.valuation if ctx is not None else analysis_origin(req)
    fan.update(context_fingerprint=_mtf_context_fingerprint(
        script, valuation, dates, flows, req, reference_price=fan['main_price']),
        origin_date=origin.isoformat(), in_life=ctx is not None, calculation_budget=budget)
    if req.model == 'lsv':
        fan['lsv_qualification'] = _lsv_mtf_receipt(
            fan['context_fingerprint'], fan.pop('lsv_leverage_digest'))
    if ctx is not None:
        fan.update(valuation_date=origin.isoformat(), years_remaining=round(ctx.T_remaining, 12))
    if req.gbm_atm_curve:
        fan['gbm_atm_curve'] = True
    if req.indicative_heston:
        fan['indicative_heston'] = True
        fan['calibration_diagnostics'] = [
            dict(underlying=u.name, **{key: controls[key] for key in (
                'max_atm_error_bp', 'max_wing_error_bp', 'max_barrier_digital_error_bp', 'near_bounds')})
            for u in req.underlyings for controls in [u.calibration_evidence['dossier']['controls']]
        ]
    return fan


def _lsv_mtf_receipt(fingerprint, leverage_digest):
    from ..services.product_receipts import _signature
    return _signature(receipt_signing_secret(), dict(context=fingerprint, leverage=leverage_digest),
                      domain='mtf-lsv-qualification-v1:')


@router.post('/mtf/compare')
def mtf_comparison_endpoint(request: MtfComparisonRequest):
    from ..core.compute.executor import run_batch

    a, b = request.a, request.b
    if ((a.model, a.gbm_atm_curve) == (b.model, b.gbm_atm_curve)
            or a.reference_paths is None or _mtf_comparison_key(a) != _mtf_comparison_key(b)):
        raise HTTPException(422, 'Comparez deux modèles différents sur un même produit, marché et paramétrage Monte Carlo.')
    try:
        resolved = _resolve_pricer_mtf(a)
        jobs, prepared, results = [], {}, {}
        for index, req in enumerate((a, b)):
            try:
                payload, valuation, budget = _pricer_mtf_job(req, resolved)
                prepared[index] = req, valuation, budget
                jobs.append((index, payload))
            except ValueError as error:
                results[index] = dict(model=req.model, error=str(error))
        _check_mtf_budget([budget for _, _, budget in prepared.values()])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    for job in run_batch('mark_to_future', jobs, max_workers=2):
        req, valuation, budget = prepared[job.job_id]
        results[job.job_id] = (dict(model=req.model, result=_finish_pricer_mtf(
            job.result, req, resolved, valuation, budget)) if job.ok
            else dict(model=req.model, error=job.error))
    return dict(a=results[0], b=results[1])


@router.post("/mtf")
@with_request_grid
def mtf_endpoint(req: MtfRequest):
    """Mark-to-Future — nested Monte Carlo: distribution of future mark-to-model
    values of the product, under the risk-neutral measure with frozen market params.

    En cours de vie, l'éventail part du niveau du jour et de l'état déjà réalisé :
    les scénarios extérieurs composent leur propre histoire par-dessus celle que
    le passé a écrite, au lieu de repartir d'un produit neuf."""
    if req.reference_paths is None and (req.gbm_atm_curve or req.indicative_heston):
        raise HTTPException(422, 'L’étude ATM exige un prix initial recalculé par modèle.')
    if req.reference_paths is not None:
        from ..core.compute.pricers.mtf import price_mtf_job
        try:
            resolved = _resolve_pricer_mtf(req)
            job, valuation, budget = _pricer_mtf_job(req, resolved)
            _check_mtf_budget([budget])
            return _finish_pricer_mtf(price_mtf_job(job), req, resolved, valuation, budget)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    ctx = residual_context_or_none(req,retain_terminated=True)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff, etat = req.r, None, None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events and ctx is None:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    if T_eff is None:
        T_eff = effective_T_max(compiled, req.T)
    try:
        valuation = valuation_context_from_request(req,compiled,residual=ctx,paths=req.n_inner)
        validate_mtf_context(compiled,valuation,payment_aware=True)
        dated_flows = _mtf_initial_flows(ctx,req)
        mtm_dates = _mtf_request_dates(req,compiled,T_eff,valuation.maturity_payment_t,ctx,dated_flows)
        validate_compiled_dates(compiled)
        peak_paths = max(req.n_outer, min(MTF_MAX_BATCH, req.n_outer * req.n_inner))
        total_paths = req.n_outer + req.n_outer * req.n_inner * len(mtm_dates)
        calculation_budget = estimate_mc_batch(
            operation="mark_to_future",
            maturity_years=max(T_eff,mtm_dates[-1]),
            underlyings=n,
            paths_per_run=peak_paths,
            total_runs=total_paths / peak_paths,
            model=req.model,
            antithetic=False,
            expanded_dates=count_compiled_dates(compiled),
        )
        ensure_budget(calculation_budget)
        res = run_mark_to_future(
            compiled, uls, corr, r_eff, T_eff,
            main_price=req.main_price,
            state=etat,
            initial_flows=dated_flows, initial_terminated=bool(ctx and ctx.residuel.early_recall),
            maturity_payment_t=valuation.maturity_payment_t, mtm_dates=mtm_dates,
            model=req.model,
            n_outer=req.n_outer,
            n_inner=req.n_inner,
            n_dates=req.n_dates,
            seed=req.seed,
            user_params=analysis_user_params(req, ctx),
            barrier_monitoring=req.barrier_monitoring,
            # Forwarded to be REFUSED, not honoured: the analysis is flat-rate
            # throughout. Dropping them here (which is what happened) priced the
            # fan on a different discount basis than the P0 it is plotted
            # against, with nothing on screen saying so.
            yield_curve=req.yield_curve,
            sigma_r=req.sigma_r,
        steps_per_year=req.steps_per_year, local_vol_anchor=valuation.local_vol_anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["context_fingerprint"] = _mtf_context_fingerprint(compiled,valuation,mtm_dates,dated_flows,req)
    res["origin_date"] = (ctx.valuation if ctx is not None else analysis_origin(req)).isoformat()
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 12)
    res["calculation_budget"] = calculation_budget.to_dict()
    return res


@router.get("/ai/providers")
@router.get("/script/providers")
def script_providers_endpoint(ollama_url: str | None = None):
    """Common catalog: configured cloud providers and installed Ollama models."""
    from ..services.llm import available_providers, DEFAULT_PROVIDER, LlmError
    try:
        return {"providers": available_providers(ollama_url), "default": DEFAULT_PROVIDER}
    except LlmError as e:
        raise HTTPException(422, str(e))


@router.post("/script/prompt")
@with_request_grid
def script_prompt_endpoint(req: ScriptGenerateRequest):
    """Le prompt exact qui partirait, sans appeler de modèle.

    Les exemples envoyés dépendent de la description : sans pouvoir les lire, on
    ne peut ni comprendre une génération ratée, ni ajuster sa demande autrement
    qu'à tâtons."""
    from ..services.llm import preview_prompt
    return preview_prompt(req.description, n_underlyings=len(req.underlyings) or 1,
                          maturity=req.T, refine=req.refine, current_script=req.current_script)


from ..core.ai_contract import AiOptions


class ProductAnalysisRequest(AiOptions):
    """Un résumé de produit et ce qu'on veut en faire.

    Le résumé arrive REDIGE depuis l'écran, il n'est pas reconstruit ici : ce
    que l'utilisateur a lu est exactement ce qui part au modèle. Le reconstruire
    côté serveur rouvrirait l'écart entre l'affiché et l'envoyé."""
    resume: str
    intention: str = "analyse"
    question: str = ""


@router.post("/product/analyse")
@with_request_grid
def product_analyse_endpoint(req: ProductAnalysisRequest):
    """Second avis d'un modèle sur un produit déjà pricé.

    200 dès que le modèle a répondu : son avis est un texte, pas un calcul, et
    il n'y a rien à valider côté serveur. Seule l'indisponibilité du moteur ou
    une intention inconnue est un 4xx."""
    from ..services.llm import DEFAULT_PROVIDER, LlmError
    from ..services.llm.analysis import analyse_produit

    try:
        return analyse_produit(
            req.resume, req.intention, question=req.question,
            provider=req.provider or DEFAULT_PROVIDER,
            model=req.model or None,
            options=req,
        )
    except LlmError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/product/analyse/prompt")
@with_request_grid
def product_analyse_prompt_endpoint(req: ProductAnalysisRequest):
    """Les deux messages qui PARTIRAIENT, sans appeler le modèle.

    Même constructeur que l'envoi réel (`construire_prompts`) : un aperçu
    reconstruit à part finirait par décrire autre chose que ce qui part, et
    l'utilisateur croirait relire sa demande alors qu'il lirait une fiction.
    Aucun appel réseau, aucun jeton consommé — on peut donc regarder avant de
    demander."""
    from ..services.llm import LlmError
    from ..services.llm.analysis import construire_prompts

    try:
        return construire_prompts(req.resume, req.intention, req.question)
    except LlmError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/product/analyse/intentions")
def product_intentions_endpoint():
    """Les intentions proposables, avec leur libellé d'écran."""
    from ..services.llm.analysis import INTENTIONS
    return {"intentions": [{"id": k, "label": v["label"]} for k, v in INTENTIONS.items()]}


@router.post("/script/generate")
@with_request_grid
def script_generate_endpoint(req: ScriptGenerateRequest):
    """Assistant de scripting — description en français vers script PayScript.

    Renvoie toujours 200 quand le modèle a répondu, même si son script ne
    compile pas : l'erreur du parser fait partie du résultat à afficher, pas
    d'un échec de la requête. Seule l'indisponibilité du moteur est un 4xx/5xx.
    """
    from ..services.llm import generate, LlmError

    uls = [u.model_dump() for u in req.underlyings]
    if not uls:
        # Le pricing de contrôle a besoin d'un sous-jacent ; l'assistant doit
        # rester utilisable avant que l'utilisateur en ait configuré un.
        uls = [{"name": "S1", "ticker": "", "ccy": "EUR", "sigma": 0.22, "q": 0.02,
                "v0": 0.0484, "kappa": 2.0, "theta": 0.0484, "xi": 0.35,
                "rho_h": -0.70, "alpha": 0.22, "beta": 1.0, "rho": -0.30,
                "nu": 0.40, "sigma_fx": 0.0, "rho_sfx": 0.0, "ccyh": 0.0}]
    n = len(uls)
    corr = req.corr_matrix
    if len(corr) != n or any(len(row) != n for row in corr):
        corr = [[1.0 if i == j else 0.5 for j in range(n)] for i in range(n)]

    try:
        return generate(
            req.description, provider=req.provider, model=req.model,
            underlyings=uls, corr=corr, r=req.r, T=req.T,
            user_params=req.user_params,
            current_script=req.current_script, refine=req.refine,
            prompt_override=req.prompt_override, api_key=req.api_key, ollama_url=req.ollama_url,
        )
    except LlmError as e:
        # 502 : c'est le fournisseur qui est en cause, pas la requête. Le
        # message est déjà rédigé pour l'utilisateur (Ollama éteint, clé
        # absente, modèle non installé, quota).
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/script/transcribe/engines")
def script_transcribe_engines_endpoint():
    """Le moteur de dictée est-il utilisable, et faut-il annoncer un
    téléchargement ?

    L'écran s'en sert pour griser le micro plutôt que de laisser cliquer sur un
    bouton qui échouera après coup — même raison que la sonde des modèles
    Ollama : un sélecteur doit annoncer ce qui existe."""
    from ..services.transcription import available_engines, DEFAULT_ENGINE
    return {"engines": available_engines(), "default": DEFAULT_ENGINE}


@router.post("/script/transcribe/prepare")
def script_transcribe_prepare_endpoint():
    """Charge le moteur — et télécharge ses poids si besoin — HORS dictée.

    Sans cette route, les ~480 Mo du premier usage partaient à l'intérieur de la
    requête de transcription : elle pendait plusieurs minutes et le navigateur
    lâchait la connexion (« Failed to fetch ») pendant que le téléchargement,
    lui, allait à son terme. L'utilisateur voyait une dictée en échec alors que
    rien n'était cassé.

    Idempotent : une fois les poids là et le modèle en mémoire, l'appel est
    instantané."""
    from ..services.transcription import TranscriptionError, warmup

    try:
        return warmup()
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/script/transcribe")
def script_transcribe_endpoint(audio: UploadFile = File(...)):
    """Un enregistrement de dictée vers du texte brut.

    Endpoint SYNCHRONE volontairement : la transcription est du calcul CPU de
    plusieurs secondes. En `async def` elle bloquerait la boucle d'événements et
    figerait tout le serveur pendant la dictée ; en `def`, FastAPI l'exécute
    dans son pool de threads.

    Le texte remonte tel quel, ni reformulé ni relu par un modèle de langage :
    il atterrit dans le champ de description où l'utilisateur le corrige. Une
    dictée qui avale « à tout moment » décrit un autre produit — c'est à l'écran
    de le montrer, pas au serveur de le deviner.
    """
    from ..services.transcription import (MAX_UPLOAD_MB, TranscriptionError,
                                          transcribe)

    data = audio.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Enregistrement vide.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Enregistrement trop long (limite {MAX_UPLOAD_MB} Mo).")

    # Fichier temporaire plutôt qu'un flux mémoire : le décodage de l'Opus passe
    # par ffmpeg, qui veut un chemin. `delete=False` puis suppression explicite —
    # sous Windows un NamedTemporaryFile encore ouvert ne peut pas être rouvert
    # par un autre processus.
    suffix = Path(audio.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return transcribe(tmp.name)
    except TranscriptionError as e:
        # 502 comme pour l'assistant : c'est le moteur qui est en cause, pas la
        # requête, et le message est déjà rédigé pour l'utilisateur.
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/mtf/drilldown")
@with_request_grid
def mtf_drilldown_endpoint(req: MtfDrilldownRequest):
    """Mark-to-Future — explication détaillée de scénarios choisis à une date.

    Rejoue les mêmes tirages que /api/mtf (mêmes graine, grille de dates et
    découpage en lots) : le mark renvoyé ici est celui de l'éventail, pas une
    ré-estimation voisine."""
    ctx = residual_context_or_none(req,retain_terminated=True)
    try:
        compiled = ctx.script if ctx is not None else resolve_analysis_constats(parse_script(req.script),req)
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    uls = ctx.underlyings if ctx is not None else [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = ctx.T_remaining if ctx is not None else effective_T_max(compiled,req.T)
    aligned = req.reference_paths is not None
    try:
        valuation = valuation_context_from_request(req,compiled,residual=ctx,paths=req.n_inner)
        _validate_atm_mtf_options(req, valuation, ctx)
        if aligned:
            valuation = replace(valuation, underlyings=[dict(u, **v.model_dump(include=_MTF_MODEL_FIELDS))
                                for u, v in zip(valuation.underlyings, req.underlyings)])
        _validate_lsv_mtf_scope(req, valuation, ctx)
        validate_mtf_context(compiled,valuation,payment_aware=True,aligned_grid=aligned)
        if req.indicative_heston:
            validate_pricing_calibrations(req, valuation.T, secret=receipt_signing_secret(),
                                          allow_indicative_heston=True)
        dated_flows = _mtf_initial_flows(ctx,req)
        mtm_dates = _mtf_request_dates(req,compiled,T_eff,valuation.maturity_payment_t,ctx,dated_flows)
        fingerprint = _mtf_context_fingerprint(compiled,valuation,mtm_dates,dated_flows,req)
        if (aligned or req.context_fingerprint is not None) and req.context_fingerprint != fingerprint:
            raise HTTPException(409,'Le contexte réalisé a changé depuis l’éventail. Relancez le Mark to Future avant d’ouvrir le détail.')
        validate_compiled_dates(compiled)
        outer_per_chunk = max(1, MTF_MAX_BATCH // req.n_inner)
        chunk_starts = {
            (int(i) // outer_per_chunk) * outer_per_chunk
            for i in req.scenario_ids
            if 0 <= int(i) < req.n_outer
        }
        chunk_paths = [
            (min(req.n_outer, start + outer_per_chunk) - start) * req.n_inner
            for start in chunk_starts
        ]
        peak_paths = max([req.n_outer, *chunk_paths])
        total_paths = req.n_outer + sum(chunk_paths)
        calculation_budget = estimate_mc_batch(
            operation="mark_to_future_drilldown",
            maturity_years=T_eff if aligned and T_eff > 0 else max(T_eff,mtm_dates[-1]),
            underlyings=n,
            paths_per_run=peak_paths,
            total_runs=total_paths / peak_paths,
            model=req.model,
            antithetic=False,
            expanded_dates=count_compiled_dates(compiled),
        )
        ensure_budget(calculation_budget)
        leverage = None
        if req.model == 'lsv':
            import hmac
            from ..core.payscript.lsv_leverage import leverage_digest, prepare_mtf_leverage
            if not req.lsv_qualification:
                raise HTTPException(409, "La qualification LSV est absente. Relancez le Mark to Future.")
            leverage = prepare_mtf_leverage(compiled, valuation, mtm_dates, qualify=False)
            if not hmac.compare_digest(req.lsv_qualification, _lsv_mtf_receipt(fingerprint, leverage_digest(leverage))):
                raise HTTPException(409, "Le levier LSV a changé. Relancez le Mark to Future.")
        result = run_mtf_drilldown(
            compiled, valuation.underlyings, corr, valuation.r, T_eff,
            state=ctx.mc_kwargs if ctx is not None else None,
            initial_flows=dated_flows, initial_terminated=bool(ctx and ctx.residuel.early_recall),
            maturity_payment_t=valuation.maturity_payment_t, mtm_dates=mtm_dates,
            main_price=req.main_price,
            t0=req.t,
            scenario_ids=req.scenario_ids,
            labels=req.labels,
            # Le texte du script sert à retrouver statiquement quels PARAM sont
            # comparés à une observable — c'est ce qui distingue une barrière
            # d'un taux de coupon sans avoir à le deviner sur la valeur.
            script_source=req.script,
            model=req.model,
            n_outer=req.n_outer,
            n_inner=req.n_inner,
            n_dates=req.n_dates,
            seed=req.seed,
            user_params=analysis_user_params(req,ctx),
            barrier_monitoring=req.barrier_monitoring,
            yield_curve=req.yield_curve,
            sigma_r=req.sigma_r,
            aligned_grid=aligned,
            gbm_atm_curve=req.gbm_atm_curve,
            lsv_leverage=leverage,
        steps_per_year=req.steps_per_year, local_vol_anchor=valuation.local_vol_anchor)
        result["context_fingerprint"] = fingerprint
        result["model"] = req.model
        result["origin_date"] = (ctx.valuation if ctx is not None else analysis_origin(req)).isoformat()
        result["in_life"] = ctx is not None
        result["calculation_budget"] = calculation_budget.to_dict()
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/backtest/history-bounds")
def backtest_history_bounds_endpoint(tickers: str, end_date: str | None = None):
    """Suggest a common start using existing observations, without provider I/O."""
    from ..runtime import business_today
    from ..services.market_history import backtest_history_bounds
    names = list(dict.fromkeys(value.strip().upper() for value in tickers.split(",") if value.strip()))
    if not 1 <= len(names) <= 12:
        raise HTTPException(422, "Précisez de un à douze sous-jacents.")
    try:
        end = date.fromisoformat(end_date).isoformat() if end_date else business_today().isoformat()
    except ValueError:
        raise HTTPException(422, "Date de fin invalide.") from None
    return backtest_history_bounds(names, end)


@router.post("/backtest")
@with_request_grid
def backtest_endpoint(req: BacktestRequest):
    return _run_historical_backtest(req)


@with_request_grid
def _run_historical_backtest(req: BacktestRequest, history_data=None):
    """Historical backtest — replay script on actual Yahoo Finance price history."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers = [u.ticker.strip().upper() for u in req.underlyings]
    if not tickers or not all(tickers):
        raise HTTPException(status_code=422, detail="Renseignez un ticker pour chaque sous-jacent du panier.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        validate_compiled_dates(compiled)
        validate_problem_dimensions(T_eff, len(req.underlyings))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Load historical prices
    px_data = history_data if history_data is not None else load_hist_prices(tickers, req.start_date, req.end_date, raw_history=True, full_history=True)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])

    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    missing = [tk for tk in tickers if tk not in prices]
    if missing:
        raise HTTPException(status_code=422, detail=f"Tickers manquants dans l'historique: {missing}")

    # Chaque fenêtre lit ses dates à leur date, calendrier du contrat translaté
    # sur son jour de départ. Trois ans couvrent donc ~765 séances et non 756 :
    # compter l'horizon à 252 par an laisserait les dernières fenêtres finir
    # au-delà de l'historique, sans remboursement, avec un rendement faux.
    max_start = derniere_fenetre(compiled, dates, T_eff)
    if max_start < 0:
        raise HTTPException(status_code=422, detail="Historique trop court pour la maturité du produit.")
    days_T = seances_jusqu_a(compiled, dates, 0, T_eff) or 0

    windows = list(range(0, max_start + 1, req.freq))
    results, raw_irrs = [], []
    excluded: list[dict] = []
    invest_dec = req.invest_pct / 100.0
    history_policy = _backtest_replay_policy(req, px_data)
    adjustments = []

    try:
        for si in windows:
            res = eval_script_on_history(
                compiled, dates, prices, si, T_eff, req.user_params, tickers, req.r,
                history_policy=history_policy,
            )
            if res is None:
                continue
            adjustments.extend(res.get("history_adjustments", []))
            cfs = [{"t": 0.0, "cf": -invest_dec}] + [
                {**flow, "t": flow.get("payment_t", flow["t"])} for flow in res["cash_flows"]]
            irr = compute_irr(cfs)
            if irr is None:
                # A window whose IRR cannot be defined is dropped — but it is
                # counted and dated, because a silent drop is how a backtest
                # loses its worst cases without anyone noticing.
                excluded.append({"date": dates[si], "reason": "IRR non défini"})
                continue
            raw_irrs.append(irr)
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

    irrs = raw_irrs
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
        "market_data": {key:px_data.get(key) for key in (
            "coverage","freshness","warnings","first_dates","effective_dates","sources",
            "start_effective","end_effective","alignment","price_type")},
        "history_policy": _backtest_result_policy(req, px_data, adjustments),
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
        # Windows the statistics above do NOT cover. Every figure on this
        # screen is computed over n_windows, not over len(windows); the
        # difference belongs on screen, not in a log nobody reads.
        "excluded_windows": excluded,
        "n_excluded": len(excluded),
    }


# ── Underlying comparator ──────────────────────────────────────────────
# Same script, same params, swap the underlying(s) and see which ones would
# have backtested best. See BacktestCompareRequest docstring for the
# two-stage funnel (individual screen, then combinations only within the
# shortlist) — an exhaustive combinatorial scan is not feasible.

@with_request_grid
def _backtest_replay_policy(req, px_data):
    policy = dict(mode=req.history_mode, max_delay_days=req.max_delay_days,
                  observation_dates=px_data.get('observation_dates'))
    if req.payment_date:
        policy['maturity_payment_t'] = (req.payment_date-analysis_origin(req)).days/365.25
    return policy


def _comparison_history_hash(history):
    payload = {key: history.get(key) for key in ('dates', 'prices', 'observation_dates', 'price_type')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@router.post('/backtest/compare/detail')
@with_request_grid
def backtest_comparison_detail(req: BacktestCompareDetailRequest):
    comparison = req.comparison
    candidates = {candidate.ticker.strip().upper(): candidate for candidate in comparison.candidates if candidate.ticker.strip()}
    names = [ticker.strip().upper() for ticker in req.tickers]
    if len(set(names)) != comparison.basket_size or len(names) != comparison.basket_size or any(tk not in candidates for tk in names):
        raise HTTPException(422, 'Panier sélectionné incohérent avec la comparaison.')
    history = load_hist_prices(list(candidates), comparison.start_date, comparison.end_date,
                               allow_partial=True, raw_history=True, full_history=True)
    if history.get('error'):
        raise HTTPException(422, history['error'])
    if _comparison_history_hash(history) != req.history_hash:
        raise HTTPException(409, 'L’historique a changé depuis ce classement. Relancez la comparaison pour consulter un détail cohérent.')
    backtest = BacktestRequest(**{**comparison.model_dump(),
        'underlyings': [candidates[tk] for tk in names],
        'corr_matrix': [[float(i == j) for j in range(len(names))] for i in range(len(names))]})
    result = _run_historical_backtest(backtest, history)
    result['history_policy']['comparison_basis'] = 'COMMON_USABLE_UNIVERSE_OBSERVATIONS'
    return {**result, 'selected_tickers': names, 'history_hash': req.history_hash}


@with_request_grid
def _backtest_result_policy(req, px_data, adjustments):
    from ..core.backtest_history import BACKTEST_HISTORY_VERSION, BACKTEST_HISTORY_DISCLAIMER
    dates = px_data['dates']
    return {"version": BACKTEST_HISTORY_VERSION, "mode": req.history_mode,
        "max_delay_days": req.max_delay_days, "requested_start": req.start_date,
        "requested_end": req.end_date, "effective_start": dates[0], "effective_end": dates[-1],
        "adjustments": adjustments, "adjustment_count": len(adjustments),
        "adjusted_underlyings": sorted({row["ticker"] for row in adjustments}),
        "disclaimer": BACKTEST_HISTORY_DISCLAIMER if adjustments else "",
        "payment_convention": "CONTRACTUAL_PAYMENT_DATE_PLUS_OBSERVATION_CALENDAR_DELAY",
        "monitoring": "AVAILABLE_DAILY_CLOSES_ONLY"}


def _windowed_backtest(compiled, dates, prices, tickers, T_eff, freq, r, invest_pct, user_params,
                        return_windows=False, *, history_policy=None, history_adjustments=None):
    """Sliding-window historical replay for a fixed set of tickers — the
    core loop shared by /backtest/compare and the reinvestment
    proposal (api/deals.py). Returns summary stats only by default (the
    comparator only needs the ranking) — return_windows=True additionally
    attaches a per-window {start_date, irr, early_recall} list, used by the
    proposal to plot the product's realized outcome against the underlying's
    price history (opt-in: keeps /backtest/compare's response light across
    its up-to-20-candidate pool)."""
    max_start = derniere_fenetre(compiled, dates, T_eff)
    if max_start < (0 if history_policy is not None else 1):
        return None

    windows = range(0, max_start + 1, freq)
    invest_dec = invest_pct / 100.0
    irrs, early_recalls = [], 0
    n_excluded, n_adjustments = 0, 0
    excluded_windows = []
    window_rows = [] if return_windows else None
    for si in windows:
        res = eval_script_on_history(compiled, dates, prices, si, T_eff, user_params, tickers, r,
            **({'history_policy': history_policy} if history_policy is not None else {}))
        if res is None:
            n_excluded += 1
            excluded_windows.append({'date': dates[si], 'reason': 'Rejeu indisponible'})
            continue
        for row in res.get('history_adjustments', []):
            n_adjustments += 1
            if history_adjustments is not None:
                history_adjustments[(row['window_start'], row['ticker'], row['requested_date'])] = row
        flows = ([{**flow, 't': flow.get('payment_t', flow['t'])} for flow in res['cash_flows']]
                 if history_policy is not None else res['cash_flows'])
        cfs = [{"t": 0.0, "cf": -invest_dec}] + flows
        irr = compute_irr(cfs)
        if irr is None:
            # Counted, not merely skipped: this comparator ranks candidates
            # against each other, so two of them dropping a different number
            # of windows are not being compared on the same basis.
            n_excluded += 1
            excluded_windows.append({'date': dates[si], 'reason': 'TRI non défini'})
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
        "n_excluded": n_excluded,
    }
    if return_windows:
        result["windows"] = window_rows
    if history_policy is not None:
        result['n_adjustments'] = n_adjustments
        result['excluded_windows'] = excluded_windows
    return result


def _realized_corr(prices: dict, tickers: list) -> list:
    """Common full-backtest sample, checked by the shared realized estimator."""
    from ..core.calibration import realized_market
    window = min((len(prices.get(tk, [])) for tk in tickers), default=0)-1
    try:
        return realized_market(prices, tickers, window_days=window)["corr"]
    except ValueError as exc:
        raise HTTPException(422, f"Corrélation de backtest non qualifiée : {exc}") from exc


@router.post("/backtest/compare")
@with_request_grid
def backtest_compare_endpoint(req: BacktestCompareRequest):
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers, ticker_name = [], {}
    for c in req.candidates:
        tk = c.ticker.strip().upper()
        if tk and tk not in ticker_name:
            tickers.append(tk)
            ticker_name[tk] = c.name or tk
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun ticker dans la liste des sous-jacents (Marché & Paramètres).")
    if len(tickers) < req.basket_size:
        raise HTTPException(status_code=422,
            detail=f"Il faut au moins {req.basket_size} sous-jacent(s) distinct(s) pour un panier de taille {req.basket_size}.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        validate_compiled_dates(compiled)
        validate_problem_dimensions(T_eff, req.basket_size)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    px_data = load_hist_prices(tickers, req.start_date, req.end_date, allow_partial=True, raw_history=True, full_history=True)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])
    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    requested_tickers = list(tickers)
    excluded_universe = px_data.get("missing_reasons", {tk:{"ticker":tk,"reason":"NO_OBSERVATIONS"} for tk in tickers if tk not in prices})
    tickers = [tk for tk in tickers if tk in prices]
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun historique trouvé pour ces tickers.")

    adjustments = {}
    history_policy = _backtest_replay_policy(req, px_data)

    def evaluate(names):
        try:
            return _windowed_backtest(compiled, dates, prices, names, T_eff, req.freq, req.r,
                req.invest_pct, req.user_params, history_policy=history_policy,
                history_adjustments=adjustments)
        except ValueError as exc:
            raise HTTPException(422, f"Comparaison ({', '.join(names)}), dates communes à l’univers : {exc}") from exc

    def response(stage, results, shortlist, **extra):
        policy = _backtest_result_policy(req, px_data, sorted(adjustments.values(),
            key=lambda row: (row['window_start'], row['requested_date'], row['ticker'])))
        policy['comparison_basis'] = 'COMMON_USABLE_UNIVERSE_OBSERVATIONS'
        context = req.model_dump(mode='json')
        if not req.anchor and not req.strike_date:
            context['anchor'] = analysis_origin(req).isoformat()
        if not req.end_date:
            from ..runtime import business_today
            context['end_date'] = px_data.get('requested_end') or business_today().isoformat()
        return {"requested_tickers": requested_tickers, "excluded_universe": excluded_universe,
            "comparison_context": {'request': context, 'history_hash': _comparison_history_hash(px_data)},
            "market_coverage": px_data.get('coverage'),
            "market_data": {key: px_data.get(key) for key in ('sources', 'first_dates', 'effective_dates',
                'warnings', 'alignment', 'price_type', 'coverage')},
            "history_policy": policy, "stage": stage, "results": results, "shortlist": shortlist, **extra}

    # Stage 1 — every candidate alone, cheap (O(N) backtests)
    stage1 = []
    for tk in tickers:
        summary = evaluate([tk])
        if summary is not None:
            stage1.append({"tickers": [tk], "names": [ticker_name[tk]], "corr_matrix": [[1.0]], **summary})
        else:
            excluded_universe[tk] = {'ticker': tk, 'reason': 'NO_USABLE_BACKTEST_WINDOW'}
    if not stage1:
        raise HTTPException(status_code=422, detail="Aucun résultat de backtest (historique insuffisant pour tous les candidats).")
    stage1.sort(key=lambda r_: r_["median_irr"], reverse=True)

    if req.basket_size == 1:
        return response('individual', stage1, [row['tickers'][0] for row in stage1])

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
        summary = evaluate(combo)
        if summary is not None:
            combos.append({
                "tickers": combo, "names": [ticker_name[tk] for tk in combo],
                "corr_matrix": _realized_corr(prices, combo), **summary,
            })
    if not combos:
        raise HTTPException(status_code=422, detail="Aucune combinaison exploitable (historique insuffisant).")
    combos.sort(key=lambda r_: r_["median_irr"], reverse=True)

    return response('combinations', combos, shortlist, individual=stage1)
