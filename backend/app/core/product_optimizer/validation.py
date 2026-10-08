"""Hold out two reproducible samples after fixing the shortlist and its coupons."""
import logging
import math
from statistics import NormalDist

import numpy as np

from ..payscript.engine import run_mc, _build_rate_term, _funding_df_arr, _df_at_time
from .contracts import VALIDATION_SEEDS
from .statistics import apply_summary, summarize_paths, normal_interval
from .market import market_engine_kwargs
from .families import family_schema, coupon_labels, solution_definition, solution_scale, solved_value

logger = logging.getLogger(__name__)


def parameter_diagnostic(result, script, inputs, candidate, pairs, alpha, definition):
    """Local delta-method uncertainty; never change the proposed parameter."""
    quantity = getattr(candidate,definition["key"])
    if quantity <= 1e-10:
        return {"status": "UNAVAILABLE_ZERO_COUPON" if definition["key"] == "coupon" else "UNAVAILABLE_ZERO_PARAMETER"}
    dt = inputs["T"]/max(1, round(inputs["T"]*52))
    steps = max(1, round(inputs["T"]*52))
    df = _build_rate_term(inputs.get("yield_curve") or [], steps, dt, inputs["r"]).df
    funding = _funding_df_arr(inputs.get("funding_curve") or [], inputs.get("funding_spread", 0.), steps, dt)
    if funding is not None:
        df = df*funding
    payments = {}
    for event in script.events:
        for observation, payment in zip(event.dates, event.payment_dates or event.dates):
            payments[round(observation/dt)] = payment if payment is not None else observation
    pv, slopes = [], []
    labels = result.get("path_flow_labels")
    for index,path in enumerate(result["path_flows"]):
        if labels is not None:
            if len(labels[index]) != len(path): raise ValueError("Libellés des flux incohérents.")
            total, slope = 0., 0.
            for (time,amount),label in zip(path,labels[index]):
                payment = payments[round(time/dt)]
                discount = float(_df_at_time(df,payment,dt,steps,inputs["r"]))
                total += amount*discount
                if label in coupon_labels(candidate.product_family):
                    derivative = amount/quantity
                    if candidate.product_family == "booster":
                        capped = abs(amount-(candidate.redemption_cap-1)) <= 1e-9
                        derivative = float(capped) if definition["key"] == "redemption_cap" else (0. if capped else derivative)
                    slope += derivative*discount
            pv.append(total); slopes.append(slope)
        elif candidate.product_family == "autocall_athena":
            life = max(t for t, _ in path)
            discount = float(_df_at_time(df,payments[round(life/dt)],dt,steps,inputs["r"]))
            raw = sum(amount for _, amount in path)
            pv.append(raw*discount); slopes.append(max(0.,raw-1.)/quantity*discount)
        else:
            return {"status":"UNAVAILABLE_FLOW_LABELS"}
    paired_pv = (np.asarray(pv[:pairs])+np.asarray(pv[pairs:]))/2
    paired_slope = (np.asarray(slopes[:pairs])+np.asarray(slopes[pairs:]))/2
    mean_pv, slope = float(paired_pv.mean()), float(paired_slope.mean())
    if abs(mean_pv-result["price"]) > 1e-6:
        return {"status":"UNAVAILABLE_FLOW_PV_MISMATCH"}
    if slope <= 1e-12:
        return {"status":"UNAVAILABLE_NO_COUPON_EXPOSURE" if definition["key"] == "coupon" else "UNAVAILABLE_NO_PARAMETER_EXPOSURE"}
    target = candidate.pricing_target if candidate.pricing_target is not None else candidate.issue_price
    fair_coupon = quantity+(target-mean_pv)/slope
    residual = (paired_pv+(fair_coupon-quantity)*paired_slope-target)/slope
    error = float(residual.std(ddof=1)/math.sqrt(pairs))
    return {"status":"AVAILABLE", "fair_parameter_estimate":fair_coupon, "parameter":definition["key"],
            **({"fair_coupon_estimate":fair_coupon} if definition["key"] == "coupon" else {}),
            "local_only":candidate.product_family == "booster", "standard_error":error,
            "interval":normal_interval(fair_coupon, error, alpha), "method":"normal delta method; diagnostic only"}


def coupon_diagnostic(result, script, inputs, candidate, pairs, alpha):
    return parameter_diagnostic(result,script,inputs,candidate,pairs,alpha,{"key":"coupon"})


def validate_candidate(req, candidate, shortlist_size):
    from .service import build_candidate, filter_candidate

    script, inputs = build_candidate(req, candidate)
    definition = solution_definition(req)
    inputs["user_params"][definition["script_param"]] = solved_value(req,candidate)*solution_scale(candidate)
    # Four final metrics, four N/2N diagnostics and one fair-coupon interval.
    family = family_schema(req.product_family,req.objective)
    checks = 13 if family["coupon_analytics"] or family["risk_severity"] else 9
    alpha = .05/(checks*shortlist_size)
    exploration = candidate.model_dump(mode="json", exclude={"validation"})
    runs = []
    for multiplier, seed in zip((1, 2), VALIDATION_SEEDS):
        pairs = multiplier*req.search.simulations
        result = run_mc(script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
                        pairs, "constant", seed, antithetic=True,
                        user_params=inputs["user_params"], per_path_flows=True, per_path_flow_labels=True, **market_engine_kwargs(inputs))
        summary = summarize_paths(result, pairs, inputs["T"], candidate.issue_price, alpha, simultaneous=True,
                                  candidate=candidate, observation_times=sorted({t for event in script.events for t in event.dates}))
        diagnostic = parameter_diagnostic(result, script, inputs, candidate, pairs, alpha, definition)
        runs.append({"seed": seed, **summary, "parameter_diagnostic":diagnostic,
                     **({"coupon_diagnostic":diagnostic} if definition["key"] == "coupon" else {})})
    comparisons = {}
    z = NormalDist().inv_cdf(1-alpha/2)
    for name in runs[0]["means"]:
        difference = abs(runs[1]["means"][name]-runs[0]["means"][name])
        error = math.hypot(runs[0]["standard_errors"][name], runs[1]["standard_errors"][name])
        # Rounded engine prices require a small numerical allowance.
        allowance = 1e-6 if name == "fair_value" else 1e-10
        comparisons[name] = {"absolute_difference": difference, "threshold": z*error+allowance,
                             "compatible": difference <= z*error+allowance}
    candidate.validation = {"exploration": exploration, "shortlist_size": shortlist_size,
                            "family_confidence": .95, "per_check_alpha": alpha,
                            "interval_method": "Bonferroni; normal price, empirical Bernstein bounded analytics",
                            "runs": runs, "compatibility": comparisons,
                            "time_steps_per_year": 52, "parameter_frozen":definition["key"],
                            "coupon_frozen": definition["key"] == "coupon"}
    apply_summary(candidate, runs[-1])
    inputs.update(N=2*req.search.simulations, seed=VALIDATION_SEEDS[-1])
    candidate.pricing_input = inputs
    candidate.rank = None
    candidate.pareto_efficient = False
    candidate.rejection_reasons = []
    candidate.rejection_details = []
    if not all(c["compatible"] for c in comparisons.values()):
        candidate.rejection_reasons.append("Échantillons indépendants N/2N incompatibles : validation Monte-Carlo non concluante.")
        candidate.rejection_details.append({"category":"MC_UNCERTAINTY","label":"Échantillons N/2N incompatibles sur le paramètre conservé"})
    filter_candidate(req, candidate)
    candidate.validation_status = "PASSED" if candidate.constraint_status == "PASS" else "REJECTED"
    candidate.warnings = ["Contrôles simultanés sur la sélection figée ; prix et compatibilité par approximation normale ; analytics bornées par Bernstein.",
                          "Compatibilité N/2N : diagnostic Monte-Carlo, pas une preuve de convergence temporelle ni d'optimalité du coupon."]
    return candidate


def evaluate_validation(req, candidate, shortlist_size):
    try:
        return validate_candidate(req, candidate, shortlist_size)
    except Exception:
        logger.exception("Optimizer holdout failed candidate=%s", candidate.candidate_id)
        candidate.validation_status = "FAILED"
        candidate.constraint_status = "REJECTED"
        candidate.rank = None
        candidate.pareto_efficient = False
        candidate.errors.append("Validation indépendante impossible ; consulter les journaux serveur.")
        return candidate
