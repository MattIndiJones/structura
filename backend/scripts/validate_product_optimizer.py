"""Offline Athena GBM reference, sample-size ladder and observation-grid study."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.payscript import engine
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.core.product_optimizer.service import build_candidate, generate_candidates, price_candidate
from backend.app.core.product_optimizer.statistics import summarize_paths


def exact_date_reference(request, candidate, pairs=80000, seed=314159):
    """Independent vectorized GBM/payoff at contractual dates; no PayScript MC."""
    script, inputs = build_candidate(request, candidate)
    event = next(e for e in script.events if e.dates and e.dates[0] > 0
                 and len(e.dates) == candidate.maturity_months//candidate.observation_months)
    times = np.array(event.dates, dtype=float)
    payments = np.array(event.payment_dates, dtype=float)
    dt = np.diff(np.r_[0., times])
    sigma = np.array([u.sigma for u in request.market.underlyings])
    q = np.array([u.q for u in request.market.underlyings])
    normals = np.random.default_rng(seed).normal(size=(len(times), len(sigma), pairs))
    normals = np.einsum('ij,tjp->tip', np.linalg.cholesky(request.market.correlation), normals)
    outputs = []
    for sign in (1., -1.):
        increments = ((request.market.rate-q-.5*sigma**2)[None,:,None]*dt[:,None,None]
                      +sign*sigma[None,:,None]*np.sqrt(dt[:,None,None])*normals)
        worst = np.exp(np.cumsum(increments, axis=0)).min(axis=1)
        recalled = worst >= candidate.autocall_trigger
        any_recall = recalled.any(axis=0)
        first = np.where(any_recall, recalled.argmax(axis=0), len(times)-1)
        coupon_period = candidate.coupon*candidate.observation_months/12
        raw = np.where(any_recall, 1.+coupon_period*(first+1),
                       np.where(worst[-1] < candidate.protection_barrier, worst[-1], 1.))
        pv = raw*np.exp(-request.market.rate*payments[first])
        outputs.append({"fair_value":pv, "probability_loss":(raw < candidate.issue_price-1e-10).astype(float),
                        "probability_autocall":(first < len(times)-1).astype(float),
                        "expected_maturity":times[first]})
    summary = {}
    for name in outputs[0]:
        sample = (outputs[0][name]+outputs[1][name])/2
        summary[name] = {"mean":float(sample.mean()), "standard_error":float(sample.std(ddof=1)/math.sqrt(pairs))}
    return {"pairs":pairs, "seed":seed, "metrics":summary}


def scenario(name, months, frequency, sigma, worst_of=False):
    underlyings = [{"ticker":"SYNTHETIC", "name":"Indice synthétique", "currency":"EUR", "sigma":sigma, "q":.02}]
    if worst_of:
        underlyings.append({**underlyings[0], "ticker":"SYNTHETIC2", "sigma":sigma+.05})
    return name, OptimizationRequest.model_validate({
        "strike_date":"2026-10-08", "convention":"modified_following", "currency":"EUR",
        "market":{"as_of":"2026-10-08", "rate":.03, "underlyings":underlyings,
                  "correlation":[[1,.4],[.4,1]] if worst_of else [[1]]},
        "ranges":{"maturity_months":{"minimum":months,"maximum":months,"step":12},
                  "protection_barrier":{"minimum":.6,"maximum":.6,"step":.05},
                  "autocall_trigger":{"minimum":1,"maximum":1,"step":.05}, "observation_months":[frequency]},
        "constraints":{"price_tolerance":.03,"coupon_maximum":.5}, "search":{"simulations":1000,"parallel_workers":1}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenarios = [scenario("mono_3y_quarterly_20vol",36,3,.2),
                 scenario("worst2_3y_quarterly_25_30vol",36,3,.25,True),
                 scenario("mono_1y_monthly_40vol",12,1,.4)]
    report = {"source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "scenarios":[]}
    start = time.perf_counter()
    original_steps = engine.SY
    try:
        for name, request in scenarios:
            engine.SY = original_steps
            candidate = price_candidate(request, next(generate_candidates(request)))
            if candidate.coupon is None:
                raise RuntimeError("Coupon non résolu.")
            reference = exact_date_reference(request, candidate)
            script, inputs = build_candidate(request, candidate)
            params = {**inputs["user_params"], "COUPON":candidate.coupon*candidate.observation_months/12}
            observations = []
            for steps, pairs, seed in ((52,1000,400001),(52,4000,400002),(52,12000,400003),
                                       (104,4000,400004),(208,4000,400005)):
                engine.SY = steps  # Offline process only; restored in finally.
                result = engine.run_mc(script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"], inputs["T"],
                                       pairs, "constant", seed, user_params=params, per_path_flows=True)
                summary = summarize_paths(result, pairs, inputs["T"], candidate.issue_price)
                comparisons = {}
                for metric, ref in reference["metrics"].items():
                    gap = summary["means"][metric]-ref["mean"]
                    sampling = 4*math.hypot(summary["standard_errors"][metric],ref["standard_error"])
                    # These predefined tolerances allow grid-date approximation;
                    # they describe this validation panel, never a global bound.
                    grid_allowance = .001 if metric == "fair_value" else .01
                    comparisons[metric] = {"difference":gap, "threshold":sampling+grid_allowance,
                                           "compatible":abs(gap) <= sampling+grid_allowance}
                observations.append({"steps_per_year":steps,"seed":seed, **summary,"reference_comparisons":comparisons})
                print(f"{name}: steps={steps} pairs={pairs} price={summary['means']['fair_value']:.6f}", flush=True)
            report["scenarios"].append({"name":name,"request":request.model_dump(mode="json"),
                                        "fixed_coupon":candidate.coupon,"reference":reference,"observations":observations})
    finally:
        engine.SY = original_steps
    report["all_reference_checks_passed"] = all(c["compatible"] for s in report["scenarios"]
        for o in s["observations"] for c in o["reference_comparisons"].values())
    report["elapsed_seconds"] = time.perf_counter()-start
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"all_reference_checks_passed={report['all_reference_checks_passed']} elapsed={report['elapsed_seconds']:.2f}s",flush=True)
    if not report["all_reference_checks_passed"]:
        raise RuntimeError("Écart à la référence au-delà des seuils déclarés.")


if __name__ == "__main__":
    main()
