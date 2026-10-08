"""Deterministic orchestration; all payoff evaluation stays in PayScript."""
import hashlib
import itertools
import logging
import math
import os
import time
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from ..compute_budget import estimate_mc_batch
from ..payscript.catalogue import PRODUCTS
from ..payscript.engine import run_mc
from ..payscript.parser import parse_script, resolve_constats
from ..payscript.simulation import solve_for_param
from .capabilities import capabilities
from .contracts import (OptimizationRequest, OptimizationCandidate, MAX_SECONDS,
                        MAX_WORK, SOLVER_ITERATIONS, MAX_PARALLEL_MEMORY_BYTES, VALIDATION_CANDIDATES)
from .parallel import iter_parallel_candidates
from .statistics import apply_summary, summarize_paths
from .validation import evaluate_validation
from .market import freeze_market, market_engine_kwargs
from .families import family_schema, autocall_levels, solution_definition, solution_scale, solved_value

logger = logging.getLogger(__name__)


def estimate_search(req: OptimizationRequest):
    r = req.ranges
    family = family_schema(req.product_family, req.objective)
    count = math.prod(getattr(r,field["key"]).count for field in family["range_fields"])
    count *= len(r.observation_months) if family["has_autocall"] else 1
    date_count = math.ceil(r.maturity_months.maximum / min(r.observation_months)) if family["has_autocall"] else 1
    budget_args = dict(
        operation="product_optimizer", maturity_years=r.maturity_months.maximum / 12 + .02,
        underlyings=len(req.market.underlyings), paths_per_run=req.search.simulations,
        total_runs=count * (SOLVER_ITERATIONS + 3) + 3*min(count, VALIDATION_CANDIDATES), model="constant", antithetic=True,
        expanded_dates=3 * date_count)
    # Holdout uses up to 2N pairs. Count all runs in N equivalents for work,
    # while reserving memory for the largest individual (2N) computation.
    peak_args = {**budget_args, "paths_per_run": 2*req.search.simulations}
    single_budget = estimate_mc_batch(**peak_args)
    # Labeled Python cash-flow lists and paired-analytics buffers survive the
    # base tensor. Reserve them explicitly in addition to engine array memory.
    max_flows = date_count+2 if family["coupon_analytics"] else 3
    flow_memory = 4*req.search.simulations*(160*max_flows+256)
    single_peak = single_budget.estimated_peak_bytes+flow_memory
    cpu_limit = max(1, (os.cpu_count() or 1) - 1)
    memory_limit = max(1, MAX_PARALLEL_MEMORY_BYTES // single_peak)
    workers = min(req.search.parallel_workers, count, cpu_limit, memory_limit)
    budget = estimate_mc_batch(**budget_args, concurrent_runs=workers)
    peak_budget = estimate_mc_batch(**peak_args, concurrent_runs=workers)
    reasons = []
    if count > req.search.max_candidates:
        reasons.append(f"{count} structures, plafond {req.search.max_candidates} : augmentez le plafond (256 maximum) ou ajustez explicitement la grille.")
    combined_peak = peak_budget.estimated_peak_bytes+workers*flow_memory
    # Total work is advisory: it cannot predict wall time across machines.
    # Admission is bounded by grid size, individual memory and a hard deadline;
    # the executor queues at most one window of workers at a time.
    work_warning = (["Volume de calcul important : la grille est conservée. Ajustez le budget temps ; un dépassement rendra la couverture partielle."]
                    if budget.work_units > MAX_WORK else [])
    if combined_peak > MAX_PARALLEL_MEMORY_BYTES:
        reasons.append("Mémoire insuffisante pour un calcul individuel, même séquentiel : réduisez les trajectoires ou le panier.")
    budget_data = budget.to_dict()
    peak_data = {"estimated_peak_bytes":combined_peak, "estimated_peak_mb":round(combined_peak/1024**2,1)}
    for name in ("estimated_peak_bytes", "estimated_peak_mb"):
        budget_data[name] = peak_data[name]
    pruned = sum(bool(c.rejection_reasons) for c in generate_candidates(req)) if count <= 256 else None
    return {"candidate_count": count, "contractually_excluded": pruned,
            "pricing_count": count-pruned if pruned is not None else None, "allowed": not reasons, "reasons": reasons,
            "budget": budget_data, "max_seconds": req.search.max_seconds, "warnings":work_warning,
            "validation": {"max_candidates": min(count, VALIDATION_CANDIDATES),
                           "pairs": [req.search.simulations, 2*req.search.simulations]},
            "execution": {"mode": "processes" if workers > 1 else "sequential",
                          "requested_workers": req.search.parallel_workers,
                          "workers": workers, "cpu_limit": cpu_limit,
                          "memory_limit": memory_limit, "queue_window":workers}}


def generate_candidates(req):
    r = req.ranges
    family = family_schema(req.product_family, req.objective)
    keys = ["maturity_months", "protection_barrier", "autocall_trigger", "observation_months", "coupon_barrier", "strike", "redemption_cap", "put_strike", "gearing"]
    axes = [sorted(r.observation_months) if key == "observation_months" and r.observation_months
            else getattr(r,key).values() if key != "observation_months" and getattr(r,key) is not None
            else [None] for key in keys]
    for index, values in enumerate(itertools.product(*axes), 1):
        fields = dict(zip(keys,values))
        months, frequency = int(fields["maturity_months"]), fields["observation_months"]
        fields.update(maturity_months=months, observation_months=frequency or months)
        if "participation" in req.payoff_settings: fields["participation"] = req.payoff_settings["participation"]
        candidate = OptimizationCandidate(
            candidate_id=f"C{index:04d}", product_family=req.product_family, **fields, issue_price=req.constraints.target_price,
            pricing_target=req.pricing_target)
        if frequency and int(months) % frequency:
            candidate.rejection_reasons.append("Maturité non multiple de la fréquence : stubs non pris en charge.")
        levels = autocall_levels(candidate, req.payoff_settings) if family["has_autocall"] else None
        if isinstance(levels, list): candidate.autocall_schedule = levels
        low_trigger = min(levels) if isinstance(levels, list) else levels
        barrier = candidate.protection_barrier if candidate.protection_barrier is not None else candidate.put_strike
        if low_trigger is not None and barrier is not None and barrier > low_trigger:
            candidate.rejection_reasons.append("La barrière de protection dépasse le seuil de rappel.")
        if candidate.coupon_barrier is not None and candidate.coupon_barrier > low_trigger:
            candidate.rejection_reasons.append("La barrière coupon dépasse le seuil de rappel : coupon au rappel non garanti par cette recherche.")
        yield candidate


def build_candidate(req, candidate):
    family = family_schema(req.product_family, req.objective)
    source = PRODUCTS[req.product_family]["script"]
    end = req.strike_date + relativedelta(months=candidate.maturity_months)
    constats = {"STARTDATE": req.strike_date.isoformat(), "OBSERVATIONDATES": {
        "first_observation_date": (req.strike_date + relativedelta(months=candidate.observation_months)).isoformat(), "end_date": end.isoformat(),
        "roll_date": req.strike_date.isoformat(), "frequency": f"{candidate.observation_months}M",
        "stub": "short_last", "convention": req.convention.value,
        "settlement_lag": req.settlement_lag,
    }}
    if not family["has_autocall"]:
        constats = {"STARTDATE":req.strike_date.isoformat(), "MATURITYDATE":{
            "date":end.isoformat(), "convention":req.convention.value, "settlement_lag":req.settlement_lag}}
    script = resolve_constats(parse_script(source), constats, anchor=req.strike_date, currency=req.currency)
    times = sorted({d for event in script.events for d in event.dates})
    if len(times) != candidate.maturity_months // candidate.observation_months or not times or times[0] <= 0:
        raise ValueError("Calendrier inattendu : nombre ou origine des constatations invalide.")
    payments = [p for event in script.events for p in (event.payment_dates or []) if p is not None]
    maturity = req.strike_date + timedelta(days=round(times[-1] * 365.25))
    payment = req.strike_date + timedelta(days=round(max(payments or times) * 365.25))
    inputs = {
        "script": source, "constats": constats, "model": "constant", "N": req.search.simulations,
        "seed": req.search.seed, "antithetic": True, "compute_greeks": False,
        "T": times[-1], "r": req.market.rate,
        "yield_curve": req.market.yield_curve, "funding_curve": req.market.funding_curve,
        "funding_spread": req.market.funding_spread,
        "underlyings": [{"name": u.name, "ticker": u.ticker, "ccy": u.currency, "sigma": u.sigma, "q": u.q,
                         "dividend_curve": u.dividend_curve}
                        for u in req.market.underlyings],
        "corr_matrix": req.market.correlation, "settlement_ccy": req.currency,
        "strike_date": req.strike_date.isoformat(), "value_date": req.strike_date.isoformat(),
        "anchor": req.strike_date.isoformat(), "maturity_date": maturity.isoformat(), "payment_date": payment.isoformat(),
        "user_params": {},
    }
    for parameter in family["script_parameters"]:
        if parameter["role"] == "solved": continue
        inputs["user_params"][parameter["name"]] = (autocall_levels(candidate, req.payoff_settings)
            if parameter["name"] == "M_AC_BAR" else getattr(candidate,parameter["binding"]))
    return script, inputs


def price_candidate(req, candidate):
    script, inputs = build_candidate(req, candidate)
    fraction = solution_scale(candidate)
    c = req.constraints
    definition = solution_definition(req)
    low, high = (getattr(c,definition[key])*fraction for key in ("minimum_key", "maximum_key"))
    solved = solve_for_param(
        script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
        "constant", req.search.seed, inputs["user_params"], definition["script_param"], req.pricing_target, low, high,
        N=req.search.simulations, tol=min(1e-6, c.price_tolerance/10), max_iter=SOLVER_ITERATIONS,
        **market_engine_kwargs(inputs))
    if not solved["converged"]:
        candidate.pricing_status = "SKIPPED"
        candidate.rejection_reasons.append(solved["message"] or "Paramètre non résolu.")
        endpoints = solved.get("trace", [])[:2]
        endpoint_prices = [point.get("price") for point in endpoints]
        bracketed = len(endpoint_prices)==2 and min(endpoint_prices)<=req.pricing_target<=max(endpoint_prices)
        candidate.rejection_details.append({"category":"NUMERICAL_SOLVER" if bracketed else "PRICE_TARGET", "label":"Prix cible inaccessible ou paramètre non résolu dans les bornes", "target":req.pricing_target, "endpoint_prices":endpoint_prices})
        return candidate
    value = solved["param_value"]
    # A capped payoff may be flat: select the largest allowed parameter when
    # the upper endpoint also matches the target on the exploration sample.
    if definition["key"] != "coupon":
        endpoint = solved["trace"][1]
        if abs(endpoint["price"]-req.pricing_target) <= min(1e-6,c.price_tolerance/10):
            value = high
            candidate.warnings.append("Borne haute retenue sur un plateau de prix ; maximum limité aux bornes de recherche.")
    setattr(candidate,definition["key"],value/fraction)
    inputs["user_params"][definition["script_param"]] = value
    # Reprice the rounded solved coupon, without trusting the solver's
    # interval-based convergence flag. The engine's antithetic path-flow output
    # is supported; its non-antithetic output currently raises UnboundLocalError.
    result = run_mc(script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
                    req.search.simulations, "constant", req.search.seed, antithetic=True,
                    user_params=inputs["user_params"], per_path_flows=True, per_path_flow_labels=True, **market_engine_kwargs(inputs))
    candidate.pricing_status = "PRICED"
    candidate.pricing_input = inputs
    summary = summarize_paths(result, req.search.simulations, inputs["T"], c.target_price, candidate=candidate,
                              observation_times=sorted({t for event in script.events for t in event.dates}))
    apply_summary(candidate, summary)
    candidate.analytics_status = "AVAILABLE"
    candidate.warnings.append("Exploration : probabilités Q et IC95 normaux ponctuels sur N paires indépendantes ; validation indépendante requise.")
    return candidate


def filter_candidate(req, candidate):
    c = req.constraints
    reasons = candidate.rejection_reasons
    if candidate.pricing_status != "PRICED" or candidate.analytics_status != "AVAILABLE":
        candidate.constraint_status = "REJECTED"
        return
    definition = solution_definition(req)
    if not getattr(c,definition["minimum_key"]) - 1e-8 <= solved_value(req,candidate) <= getattr(c,definition["maximum_key"]) + 1e-8:
        reasons.append("Paramètre résolu hors bornes.")
    if candidate.price_ic95[0] < req.pricing_target-c.price_tolerance or candidate.price_ic95[1] > req.pricing_target+c.price_tolerance:
        reasons.append("IC95 du prix hors tolérance du prix cible.")
    if req.objective == "target_coupon" and abs(candidate.coupon-c.target_coupon) > c.coupon_tolerance:
        reasons.append("Coupon hors tolérance du coupon cible.")
    if c.max_probability_loss is not None and candidate.probability_loss_ic95[1] > c.max_probability_loss:
        reasons.append("Borne haute IC95 de la probabilité de perte supérieure au plafond.")
    if c.min_probability_autocall is not None and candidate.probability_autocall_ic95[0] < c.min_probability_autocall:
        reasons.append("Borne basse IC95 de la probabilité de rappel inférieure au minimum.")
    if c.max_expected_maturity is not None and candidate.expected_maturity_upper95 > c.max_expected_maturity:
        reasons.append("Borne haute de durée moyenne supérieure au plafond.")
    if c.max_expected_capital_loss is not None and candidate.expected_capital_loss_ic95[1] > c.max_expected_capital_loss:
        reasons.append("Borne haute de perte en capital moyenne supérieure au plafond.")
    candidate.constraint_status = "REJECTED" if reasons else "PASS"
    candidate.rejection_details = [d for d in candidate.rejection_details if d.get("metric") is None]
    if req.objective == "target_coupon" and abs(candidate.coupon-c.target_coupon) > c.coupon_tolerance:
        candidate.rejection_details.append({"category":"CONTRACT_OR_BOUNDS","metric":"coupon","label":"Coupon hors tolérance du coupon cible", "estimate":candidate.coupon,"target":c.target_coupon,"tolerance":c.coupon_tolerance,"unit":"fraction"})
    for metric, mean, bound, limit, relation, label in (
        ("probability_loss",candidate.probability_loss,candidate.probability_loss_ic95[1],c.max_probability_loss,"max","Probabilité de perte Q"),
        ("probability_autocall",candidate.probability_autocall,(candidate.probability_autocall_ic95 or [None,None])[0],c.min_probability_autocall,"min","Rappel anticipé Q"),
        ("expected_maturity",candidate.expected_maturity,candidate.expected_maturity_upper95,c.max_expected_maturity,"max","Durée moyenne"),
        ("expected_capital_loss",candidate.expected_capital_loss,(candidate.expected_capital_loss_ic95 or [None,None])[1],c.max_expected_capital_loss,"max","Perte en capital moyenne Q"),
    ):
        if limit is None or bound is None: continue
        gap = bound-limit if relation == "max" else limit-bound
        if gap > 0:
            central_pass = mean <= limit if relation == "max" else mean >= limit
            candidate.rejection_details.append({"category":"MC_UNCERTAINTY" if central_pass else "HARD_CONSTRAINT", "metric":metric,"label":label,"estimate":mean,"bound":bound,"limit":limit,"gap":gap,"unit":"years" if metric=="expected_maturity" else "fraction"})
    if candidate.price_ic95[0] < req.pricing_target-c.price_tolerance or candidate.price_ic95[1] > req.pricing_target+c.price_tolerance:
        candidate.rejection_details.append({"category":"MC_UNCERTAINTY" if abs(candidate.fair_value-req.pricing_target)<=c.price_tolerance else "PRICE_TARGET", "metric":"fair_value","label":"Intervalle de prix hors tolérance", "estimate":candidate.fair_value,"interval":candidate.price_ic95,"target":req.pricing_target,"tolerance":c.price_tolerance,"unit":"fraction"})


def rank_candidates(req, candidates, confirmed_only=False):
    valid = [c for c in candidates if c.constraint_status == "PASS"
             and (not confirmed_only or c.validation_status == "PASSED")]
    def key(c):
        if req.product_family == "autocall_gear_put":
            risk = (c.expected_capital_loss, c.put_strike, c.gearing)
            return ((-c.coupon,*risk) if req.objective == "maximize_coupon" else (*risk,-c.coupon)) + (c.candidate_id,)
        if req.objective in ("maximize_participation", "maximize_cap"):
            x = family_schema(req.product_family,req.objective)["frontier"]["x"]
            axis = getattr(c,x["key"])
            return (-solved_value(req,c),c.probability_loss,axis if x["preference"] == "min" else -axis,c.candidate_id)
        if req.objective == "maximize_coupon":
            return (-c.coupon, c.probability_loss, c.protection_barrier, abs(c.fair_value-req.pricing_target), c.candidate_id)
        return (c.protection_barrier, c.probability_loss, -c.coupon, abs(c.fair_value-req.pricing_target), c.candidate_id)
    valid.sort(key=key)
    frontier = family_schema(req.product_family,req.objective)["frontier"]
    def axes(c):
        return tuple(getattr(c,frontier[k]["key"])*(1 if frontier[k]["preference"] == "max" else -1) for k in ("x","y"))
    for rank, candidate in enumerate(valid, 1):
        candidate.rank = rank
        a = axes(candidate)
        candidate.pareto_efficient = not any(all(x >= y for x,y in zip(axes(other),a)) and axes(other) != a for other in valid)
    return valid


def evaluate_candidate(req, candidate, adapter=None):
    if candidate.rejection_reasons:
        candidate.pricing_status = "SKIPPED"
    else:
        try:
            candidate = (adapter or price_candidate)(req, candidate)
        except Exception:
            logger.exception("Product Optimizer candidate %s failed", candidate.candidate_id)
            candidate.pricing_status = "FAILED"
            candidate.analytics_status = "FAILED"
            candidate.errors.append("Calcul impossible pour ce candidat ; consulter les journaux serveur.")
    return candidate


def run_events(req: OptimizationRequest, adapter=None, validation_adapter=None, should_cancel=None, include_candidate_events=False):
    req = req.model_copy(deep=True)
    market_snapshot = freeze_market(req.market)
    estimate = estimate_search(req)
    if not estimate["allowed"]:
        raise ValueError(" ".join(estimate["reasons"]))
    start = time.monotonic()
    # Keep the historical default overridable by deterministic test clocks.
    seconds = MAX_SECONDS if req.search.max_seconds == 120 else req.search.max_seconds
    deadline = start + seconds
    def stopped():
        return bool(should_cancel and should_cancel()) or time.monotonic() > deadline
    candidates = []
    yield {"type": "started", "estimate": estimate, "market_hash": market_snapshot["hash"]}
    complete = True
    workers = estimate["execution"]["workers"]
    if adapter is not None or workers == 1:
        # Injected adapters need not be picklable. Production uses the same direct
        # evaluator both here and in the registered process-worker pricer.
        for candidate in generate_candidates(req):
            if stopped():
                complete = False
                break
            computation_performed = not candidate.rejection_reasons
            candidate = evaluate_candidate(req, candidate, adapter)
            filter_candidate(req, candidate)
            candidates.append(candidate)
            yield {"type": "progress", "completed": len(candidates), "total": estimate["candidate_count"],
                   "candidate_id": candidate.candidate_id, "status": candidate.constraint_status,
                   "computation_performed":computation_performed, **({"candidate":candidate.model_dump(mode="json")} if include_candidate_events else {})}
    else:
        pending = []
        for candidate in generate_candidates(req):
            if candidate.rejection_reasons:
                candidate = evaluate_candidate(req, candidate)
                filter_candidate(req, candidate)
                candidates.append(candidate)
                yield {"type": "progress", "completed": len(candidates), "total": estimate["candidate_count"],
                       "candidate_id": candidate.candidate_id, "status": candidate.constraint_status,
                       "computation_performed":False, **({"candidate":candidate.model_dump(mode="json")} if include_candidate_events else {})}
            else:
                pending.append(candidate)
        iterator = iter_parallel_candidates(req, pending, workers, deadline, external_cancel=should_cancel)
        try:
            for candidate in iterator:
                if candidate is None:
                    # Keeps the HTTP stream cancellable while a process is busy.
                    yield {"type": "heartbeat"}
                    continue
                filter_candidate(req, candidate)
                candidates.append(candidate)
                yield {"type": "progress", "completed": len(candidates), "total": estimate["candidate_count"],
                       "candidate_id": candidate.candidate_id, "status": candidate.constraint_status,
                       "computation_performed":True, **({"candidate":candidate.model_dump(mode="json")} if include_candidate_events else {})}
        finally:
            iterator.close()
        complete = len(candidates) == estimate["candidate_count"]
    candidates.sort(key=lambda c: c.candidate_id)
    exploration_valid = rank_candidates(req, candidates)
    shortlist = exploration_valid[:VALIDATION_CANDIDATES]
    for candidate in candidates:
        candidate.rank = None
        candidate.pareto_efficient = False
    for candidate in shortlist:
        candidate.validation_status = "PENDING"
    validated = {}
    if shortlist and not (should_cancel and should_cancel()):
        yield {"type": "validation_started", "total": len(shortlist),
               "candidate_ids": [c.candidate_id for c in shortlist]}
        if workers > 1 and adapter is None and validation_adapter is None:
            iterator = iter_parallel_candidates(req, shortlist, workers, deadline,
                                                phase="validation", shortlist_size=len(shortlist), external_cancel=should_cancel)
            try:
                for candidate in iterator:
                    if candidate is None:
                        yield {"type": "heartbeat"}
                        continue
                    validated[candidate.candidate_id] = candidate
                    yield {"type": "validation_progress", "completed": len(validated), "total": len(shortlist),
                           "candidate_id": candidate.candidate_id, "status": candidate.validation_status, **({"candidate":candidate.model_dump(mode="json")} if include_candidate_events else {})}
            finally:
                iterator.close()
        else:
            for candidate in shortlist:
                if stopped():
                    break
                candidate = (validation_adapter or evaluate_validation)(req, candidate, len(shortlist))
                validated[candidate.candidate_id] = candidate
                yield {"type": "validation_progress", "completed": len(validated), "total": len(shortlist),
                       "candidate_id": candidate.candidate_id, "status": candidate.validation_status, **({"candidate":candidate.model_dump(mode="json")} if include_candidate_events else {})}
    candidates = [validated.get(c.candidate_id, c) for c in candidates]
    validation_complete = len(validated) == len(shortlist)
    # No adaptive refill of the shortlist after observing holdout failures.
    valid = rank_candidates(req, candidates, confirmed_only=True)
    ranking_stability = "INSUFFICIENT_COMPARISON"
    if len(valid) > 1 and req.objective in ("maximize_coupon","maximize_participation","maximize_cap"):
        diagnostics = [c.validation["runs"][-1].get("parameter_diagnostic",c.validation["runs"][-1].get("coupon_diagnostic",{})) if c.validation else {}
                       for c in valid]
        if all(d.get("status") == "AVAILABLE" and not d.get("local_only",False) for d in diagnostics):
            ranking_stability = ("SEPARATED" if diagnostics[0]["interval"][0] >
                                 max(d["interval"][1] for d in diagnostics[1:]) else "OVERLAPPING")
        else:
            ranking_stability = "UNAVAILABLE"
    elif req.objective not in ("maximize_coupon","maximize_participation","maximize_cap"):
        ranking_stability = "STRUCTURAL_OBJECTIVE"
    explanation = None
    if valid:
        explanation = ({"maximize_coupon":"Coupon le plus élevé", "maximize_participation":"Participation la plus élevée", "maximize_cap":"Cap de remboursement le plus élevé", "maximize_protection":"Barrière de protection la plus basse", "target_coupon":"Protection privilégiée au coupon cible"}[req.objective])
        if req.product_family == "autocall_gear_put" and req.objective == "target_coupon": explanation = "Perte en capital moyenne la plus faible au coupon cible"
        explanation += " parmi la sélection figée satisfaisant les contraintes sur tirages indépendants et les contrôles N/2N."
    request_json = req.model_dump_json()
    interruption = "USER_STOP" if should_cancel and should_cancel() else "TIME_BUDGET" if not complete or not validation_complete else None
    categories = {}
    for candidate in candidates:
        labels = {d["category"] for d in candidate.rejection_details}
        if candidate.errors: labels.add("CALCULATION_ERROR")
        if candidate.rejection_reasons and not labels: labels.add("MC_UNCERTAINTY" if candidate.validation_status=="REJECTED" else "CONTRACT_OR_BOUNDS")
        for label in labels: categories[label] = categories.get(label,0)+1
    yield {"type": "result", "result": {
        "schema_version": 1, "engine_version": "optimizer-v1-market-search", "complete": complete and validation_complete and interruption is None,
        "interruption":interruption, "rejection_categories":categories,
        "request": req.model_dump(mode="json"), "request_hash": hashlib.sha256(request_json.encode()).hexdigest(),
        "model": "constant", "method": "grid", "seed": req.search.seed,
        "market_source": req.market.source, "market_date": str(req.market.as_of),
        "market_snapshot": market_snapshot,
        "payoff": family_schema(req.product_family,req.objective),
        "economics": {"issue_price":req.constraints.target_price, **req.economics.model_dump(),
                      "pricing_target":req.pricing_target, "convention":"upfront fractions of nominal"},
        "simulations": req.search.simulations, "estimate": estimate,
        "statistics": {"generated": estimate["candidate_count"], "evaluated": len(candidates),
                       "priced": sum(c.pricing_status == "PRICED" for c in candidates),
                       "failed": sum(c.pricing_status == "FAILED" for c in candidates),
                       "valid": len(valid), "rejected": sum(c.constraint_status == "REJECTED" for c in candidates),
                       "not_evaluated": estimate["candidate_count"]-len(candidates)},
        "recommended_id": valid[0].candidate_id if valid else None, "explanation": explanation,
        "validation": {"selected": len(shortlist), "evaluated": len(validated), "complete": validation_complete,
                       "passed": len(valid), "selection_frozen": True,
                       "failed": sum(c.validation_status == "FAILED" for c in candidates),
                       "rejected": sum(c.validation_status == "REJECTED" for c in candidates),
                       "not_evaluated": len(shortlist)-len(validated),
                       "exploration_admissible": len(exploration_valid),
                       "ranking_stability": ranking_stability},
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "warnings": capabilities()["limitations"] + market_snapshot["warnings"] + ([] if interruption is None else [("Arrêt demandé" if interruption=="USER_STOP" else "Budget temps atteint") + " ; recherche ou validation partielle. Seuls les candidats confirmés sont recommandables."]),
        "elapsed_seconds": round(time.monotonic()-start, 3),
    }}
