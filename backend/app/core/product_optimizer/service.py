"""Deterministic orchestration; all payoff evaluation stays in PayScript."""
import hashlib
import itertools
import logging
import math
import time
from datetime import timedelta

import numpy as np
from dateutil.relativedelta import relativedelta

from ..compute_budget import estimate_mc_batch
from ..payscript.catalogue import PRODUCTS
from ..payscript.engine import run_mc
from ..payscript.parser import parse_script, resolve_constats
from ..payscript.simulation import solve_for_param
from .capabilities import capabilities
from .contracts import (OptimizationRequest, OptimizationCandidate, MAX_SECONDS,
                        MAX_WORK, SOLVER_ITERATIONS)

logger = logging.getLogger(__name__)


def estimate_search(req: OptimizationRequest):
    r = req.ranges
    count = r.maturity_months.count * r.protection_barrier.count * r.autocall_trigger.count * len(r.observation_months)
    budget = estimate_mc_batch(
        operation="product_optimizer", maturity_years=r.maturity_months.maximum / 12 + .02,
        underlyings=len(req.market.underlyings), paths_per_run=req.search.simulations,
        total_runs=count * (SOLVER_ITERATIONS + 3), model="constant", antithetic=True,
        expanded_dates=2 * math.ceil(r.maturity_months.maximum / min(r.observation_months)))
    reasons = []
    if count > req.search.max_candidates:
        reasons.append(f"{count} structures, plafond {req.search.max_candidates} : resserrez les plages ou augmentez les pas.")
    if budget.work_units > MAX_WORK or budget.estimated_peak_bytes > 256 * 1024**2:
        reasons.append("Budget de calcul dépassé : réduisez la grille, les trajectoires ou le panier.")
    return {"candidate_count": count, "allowed": not reasons, "reasons": reasons,
            "budget": budget.to_dict(), "max_seconds": MAX_SECONDS}


def generate_candidates(req):
    r = req.ranges
    for index, (months, barrier, trigger, frequency) in enumerate(itertools.product(
            r.maturity_months.values(), r.protection_barrier.values(),
            r.autocall_trigger.values(), sorted(r.observation_months)), 1):
        candidate = OptimizationCandidate(
            candidate_id=f"C{index:04d}", maturity_months=int(months),
            observation_months=frequency, protection_barrier=barrier,
            autocall_trigger=trigger, issue_price=req.constraints.target_price)
        if int(months) % frequency:
            candidate.rejection_reasons.append("Maturité non multiple de la fréquence : stubs non pris en charge.")
        if barrier > trigger:
            candidate.rejection_reasons.append("La barrière de protection dépasse le seuil de rappel.")
        yield candidate


def build_candidate(req, candidate):
    source = PRODUCTS[req.product_family]["script"]
    end = req.strike_date + relativedelta(months=candidate.maturity_months)
    constats = {"OBSERVATIONS": {
        "start_date": req.strike_date.isoformat(), "end_date": end.isoformat(),
        "roll_date": req.strike_date.isoformat(), "frequency": f"{candidate.observation_months}M",
        "stub": "short_last", "convention": req.convention.value,
        "settlement_lag": req.settlement_lag,
    }}
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
        "underlyings": [{"name": u.name, "ticker": u.ticker, "ccy": u.currency, "sigma": u.sigma, "q": u.q}
                        for u in req.market.underlyings],
        "corr_matrix": req.market.correlation, "settlement_ccy": req.currency,
        "strike_date": req.strike_date.isoformat(), "value_date": req.strike_date.isoformat(),
        "anchor": req.strike_date.isoformat(), "maturity_date": maturity.isoformat(), "payment_date": payment.isoformat(),
        "user_params": {"M_AC_BAR": candidate.autocall_trigger, "M_KI_BAR": candidate.protection_barrier},
    }
    return script, inputs


def wilson(successes, total):
    p, z = successes / total, 1.96
    den = 1 + z*z/total
    mid = (p + z*z/(2*total)) / den
    width = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / den
    return [max(0., mid-width), min(1., mid+width)]


def price_candidate(req, candidate):
    script, inputs = build_candidate(req, candidate)
    fraction = candidate.observation_months / 12
    c = req.constraints
    solved = solve_for_param(
        script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
        "constant", req.search.seed, inputs["user_params"], "COUPON", c.target_price,
        c.coupon_minimum * fraction, c.coupon_maximum * fraction,
        N=req.search.simulations, tol=min(1e-6, c.price_tolerance/10), max_iter=SOLVER_ITERATIONS)
    if not solved["converged"]:
        candidate.pricing_status = "SKIPPED"
        candidate.rejection_reasons.append(solved["message"] or "Coupon non résolu.")
        return candidate
    candidate.coupon = solved["param_value"] / fraction
    inputs["user_params"]["COUPON"] = solved["param_value"]
    # Reprice the rounded solved coupon, without trusting the solver's
    # interval-based convergence flag. The engine's antithetic path-flow output
    # is supported; its non-antithetic output currently raises UnboundLocalError.
    result = run_mc(script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
                    req.search.simulations, "constant", req.search.seed, antithetic=True,
                    user_params=inputs["user_params"], per_path_flows=True)
    candidate.fair_value = float(result["price"])
    candidate.price_ic95 = [float(v) for v in result["ic95"]]
    candidate.pricing_status = "PRICED"
    candidate.pricing_input = inputs
    paths = result.get("path_flows")
    if not paths or len(paths) != 2 * req.search.simulations:
        raise ValueError("Flux par trajectoire indisponibles ou nombre incohérent.")
    # Only independent base legs enter binomial intervals. Their antithetic
    # partners are correlated observations, not an extra N independent samples.
    paths = paths[:req.search.simulations]
    totals, lives = [], []
    for path in paths:
        if not path or any(not math.isfinite(float(x)) for flow in path for x in flow):
            raise ValueError("Flux de trajectoire absents ou non finis.")
        totals.append(sum(float(amount) for _, amount in path))
        lives.append(max(float(t) for t, _ in path))
    # The existing engine returns flow times on its observation grid here.
    # run_mc uses dt=T/round(T*SY), so its final grid node is exactly T.
    terminal = inputs["T"]
    losses = sum(amount < c.target_price - 1e-10 for amount in totals)
    early = sum(life < terminal - 1e-8 for life in lives)
    n = len(paths)
    candidate.probability_loss = losses/n
    candidate.probability_loss_ic95 = wilson(losses, n)
    candidate.probability_autocall = early/n
    candidate.probability_autocall_ic95 = wilson(early, n)
    candidate.expected_maturity = float(np.mean(lives))
    candidate.expected_maturity_upper95 = float(np.mean(lives) + 1.96*np.std(lives, ddof=1)/math.sqrt(n))
    values = [candidate.fair_value, *candidate.price_ic95, candidate.expected_maturity_upper95]
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Résultat numérique non fini.")
    if result.get("corr_repair"):
        raise ValueError("Corrélation réparée par le moteur : résultat non admissible en V1.")
    candidate.analytics_status = "AVAILABLE"
    candidate.warnings.append("Probabilités Q ; IC95 ponctuels, non simultanés sur la grille ; hypothèses manuelles.")
    return candidate


def filter_candidate(req, candidate):
    c = req.constraints
    reasons = candidate.rejection_reasons
    if candidate.pricing_status != "PRICED" or candidate.analytics_status != "AVAILABLE":
        candidate.constraint_status = "REJECTED"
        return
    if not c.coupon_minimum - 1e-8 <= candidate.coupon <= c.coupon_maximum + 1e-8:
        reasons.append("Coupon hors bornes.")
    if candidate.price_ic95[0] < c.target_price-c.price_tolerance or candidate.price_ic95[1] > c.target_price+c.price_tolerance:
        reasons.append("IC95 du prix hors tolérance du prix cible.")
    if req.objective == "target_coupon" and abs(candidate.coupon-c.target_coupon) > c.coupon_tolerance:
        reasons.append("Coupon hors tolérance du coupon cible.")
    if c.max_probability_loss is not None and candidate.probability_loss_ic95[1] > c.max_probability_loss:
        reasons.append("Borne haute IC95 de la probabilité de perte supérieure au plafond.")
    if c.min_probability_autocall is not None and candidate.probability_autocall_ic95[0] < c.min_probability_autocall:
        reasons.append("Borne basse IC95 de la probabilité de rappel inférieure au minimum.")
    if c.max_expected_maturity is not None and candidate.expected_maturity_upper95 > c.max_expected_maturity:
        reasons.append("Borne haute de durée moyenne supérieure au plafond.")
    candidate.constraint_status = "REJECTED" if reasons else "PASS"


def rank_candidates(req, candidates):
    valid = [c for c in candidates if c.constraint_status == "PASS"]
    def key(c):
        if req.objective == "maximize_coupon":
            return (-c.coupon, c.probability_loss, c.protection_barrier, abs(c.fair_value-c.issue_price), c.candidate_id)
        return (c.protection_barrier, c.probability_loss, -c.coupon, abs(c.fair_value-c.issue_price), c.candidate_id)
    valid.sort(key=key)
    for rank, candidate in enumerate(valid, 1):
        candidate.rank = rank
        candidate.pareto_efficient = not any(
            other.coupon >= candidate.coupon and other.protection_barrier <= candidate.protection_barrier
            and (other.coupon > candidate.coupon or other.protection_barrier < candidate.protection_barrier)
            for other in valid)
    return valid


def run_events(req: OptimizationRequest, adapter=price_candidate):
    estimate = estimate_search(req)
    if not estimate["allowed"]:
        raise ValueError(" ".join(estimate["reasons"]))
    start = time.monotonic()
    candidates = []
    yield {"type": "started", "estimate": estimate}
    complete = True
    for candidate in generate_candidates(req):
        if time.monotonic()-start > MAX_SECONDS:
            complete = False
            break
        if candidate.rejection_reasons:
            candidate.pricing_status = "SKIPPED"
        else:
            try:
                candidate = adapter(req, candidate)
            except Exception:
                logger.exception("Product Optimizer candidate %s failed", candidate.candidate_id)
                candidate.pricing_status = "FAILED"
                candidate.analytics_status = "FAILED"
                candidate.errors.append("Calcul impossible pour ce candidat ; consulter les journaux serveur.")
        filter_candidate(req, candidate)
        candidates.append(candidate)
        yield {"type": "progress", "completed": len(candidates), "total": estimate["candidate_count"],
               "candidate_id": candidate.candidate_id, "status": candidate.constraint_status}
    valid = rank_candidates(req, candidates)
    explanation = None
    if valid:
        explanation = ("Coupon le plus élevé" if req.objective == "maximize_coupon" else "Barrière de protection la plus basse")
        explanation += " parmi les candidats évalués satisfaisant les contraintes et les contrôles IC95."
    request_json = req.model_dump_json()
    yield {"type": "result", "result": {
        "schema_version": 1, "engine_version": "optimizer-v1", "complete": complete,
        "request": req.model_dump(mode="json"), "request_hash": hashlib.sha256(request_json.encode()).hexdigest(),
        "model": "constant", "method": "grid", "seed": req.search.seed,
        "market_source": "USER_ASSUMPTION", "market_date": str(req.market.as_of),
        "simulations": req.search.simulations, "estimate": estimate,
        "statistics": {"generated": estimate["candidate_count"], "evaluated": len(candidates),
                       "priced": sum(c.pricing_status == "PRICED" for c in candidates),
                       "failed": sum(c.pricing_status == "FAILED" for c in candidates),
                       "valid": len(valid), "rejected": len(candidates)-len(valid),
                       "not_evaluated": estimate["candidate_count"]-len(candidates)},
        "recommended_id": valid[0].candidate_id if valid else None, "explanation": explanation,
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "warnings": capabilities()["limitations"] + ([] if complete else ["Recherche interrompue par le budget temps ; classement partiel."]),
        "elapsed_seconds": round(time.monotonic()-start, 3),
    }}
