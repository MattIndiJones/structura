"""Holdout selection, independent seeds, paired variance and confidence control."""
from copy import deepcopy
import math

import numpy as np
import pytest

from backend.app.core.product_optimizer import service, validation
from backend.app.core.product_optimizer.contracts import OptimizationRequest, VALIDATION_SEEDS
from backend.app.core.product_optimizer.statistics import bounded_interval, summarize_paths
from backend.tests.test_product_optimizer import payload, request, evaluated


def test_antithetic_metrics_use_both_legs_and_pair_variance():
    # Every pair has one early call and one terminal loss, hence its mean is
    # constant. Treating the 2N paths as independent would invent a variance.
    result = {"price":1., "ic95":[1.,1.],
              "path_flows":[[(.25,1.1)]]*10 + [[(1.,.5)]]*10}
    summary = summarize_paths(result, 10, 1., 1.)
    assert summary["means"]["probability_loss"] == .5
    assert summary["means"]["probability_autocall"] == .5
    assert summary["means"]["expected_maturity"] == .625
    assert summary["standard_errors"]["probability_loss"] == 0
    assert summary["standard_errors"]["expected_maturity"] == 0


def test_bounded_intervals_do_not_claim_zero_risk_after_no_observed_loss():
    interval = bounded_interval(np.zeros(2000), 0., 1., .001)
    assert interval[0] == 0 and 0 < interval[1] < .02
    broad = bounded_interval(np.tile([0., .5, 1.], 1000), 0., 1., .001)
    narrow = bounded_interval(np.tile([0., .5, 1.], 1000), 0., 1., .05)
    assert broad[0] < narrow[0] and broad[1] > narrow[1]
    with pytest.raises(ValueError):
        bounded_interval([0.,2.], 0.,1., .05)


def fake_result(pairs, price=1.):
    return {"price":price, "ic95":[price-.001,price+.001],
            "path_flows":[[(.25,1.02)]]*(2*pairs)}


def test_holdout_keeps_coupon_uses_new_seeds_and_final_sample(monkeypatch):
    calls = []
    def mc(*args, **kw):
        calls.append((args[5], args[7], deepcopy(kw["user_params"])))
        return fake_result(args[5])
    monkeypatch.setattr(validation, "run_mc", mc)
    candidate = evaluated(request())
    old_coupon = candidate.coupon
    result = validation.validate_candidate(request(), candidate, 3)
    assert [(n,seed) for n,seed,_ in calls] == [(1000,VALIDATION_SEEDS[0]),(2000,VALIDATION_SEEDS[1])]
    assert all(params["COUPON"] == old_coupon/4 for _,_,params in calls)
    assert result.coupon == old_coupon and result.validation_status == "PASSED"
    assert result.pricing_input["N"] == 2000 and result.pricing_input["seed"] == VALIDATION_SEEDS[1]
    assert result.validation["per_check_alpha"] == .05/27
    assert result.validation["exploration"]["fair_value"] == 1.
    assert result.probability_loss_ic95[1] > 0


def test_holdout_can_reject_an_exploration_winner_without_resolving_coupon(monkeypatch):
    monkeypatch.setattr(validation, "run_mc", lambda *a, **kw: fake_result(a[5], 1.05))
    result = validation.validate_candidate(request(), evaluated(request()), 1)
    assert result.validation_status == "REJECTED"
    assert any("prix" in reason for reason in result.rejection_reasons)
    assert result.validation["compatibility"]["fair_value"]["compatible"]


def test_incompatible_independent_samples_prevent_confirmation(monkeypatch):
    monkeypatch.setattr(validation, "run_mc", lambda *a, **kw: fake_result(a[5], 1.02 if a[5] == 1000 else 1.))
    result = validation.validate_candidate(request(), evaluated(request()), 1)
    assert result.validation_status == "REJECTED"
    assert not result.validation["compatibility"]["fair_value"]["compatible"]
    assert any("N/2N" in reason for reason in result.rejection_reasons)


def test_zero_observed_loss_still_fails_a_zero_risk_cap(monkeypatch):
    monkeypatch.setattr(validation, "run_mc", lambda *a, **kw: fake_result(a[5]))
    req = request(constraints={"max_probability_loss":0, "price_tolerance":.03})
    result = validation.validate_candidate(req, evaluated(req), 1)
    assert result.probability_loss == 0 and result.validation_status == "REJECTED"


def test_validation_failure_is_private_and_never_recommended(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private market detail")
    monkeypatch.setattr(validation, "run_mc", fail)
    result = validation.evaluate_validation(request(), evaluated(request()), 1)
    assert result.validation_status == "FAILED" and result.constraint_status == "REJECTED"
    assert "private market detail" not in result.model_dump_json()


def test_coupon_diagnostic_is_independent_uncertainty_and_does_not_change_quote():
    req = request()
    req.market.rate = 0.
    candidate = evaluated(req, coupon=.08)
    script, inputs = service.build_candidate(req, candidate)
    first = script.events[1].dates[0]
    dt = inputs["T"]/round(inputs["T"]*52)
    grid_first = round(first/dt)*dt
    # Half of each pair receives its coupon; the other half loses 2%.
    # The proposed .08 balances the expectation exactly at par.
    result = {"price":1., "path_flows":[[(grid_first,.02),(grid_first,1.)]]*1000
              + [[(inputs["T"],1.),(inputs["T"],-.02)]]*1000}
    diagnostic = validation.coupon_diagnostic(result,script,inputs,candidate,1000,.001)
    assert diagnostic["status"] == "AVAILABLE"
    assert diagnostic["fair_coupon_estimate"] == pytest.approx(.08)
    assert diagnostic["standard_error"] == pytest.approx(0.,abs=1e-14)
    assert candidate.coupon == .08


@pytest.mark.parametrize("separated", [False, True])
def test_coupon_rank_diagnostic_reports_separation_or_overlap(separated):
    def adapter(req, c):
        return evaluated(req, candidate_id=c.candidate_id,coupon=.2-int(c.candidate_id[1:])*.01)
    def holdout(req,c,size):
        c.validation_status = "PASSED"
        width = .0001 if separated else .1
        c.validation = {"runs":[{"coupon_diagnostic":{"status":"AVAILABLE","interval":[c.coupon-width,c.coupon+width]}}]}
        return c
    result = list(service.run_events(six_request(),adapter=adapter,validation_adapter=holdout))[-1]["result"]
    assert result["validation"]["ranking_stability"] == ("SEPARATED" if separated else "OVERLAPPING")
    assert result["recommended_id"] == "C0001"


def six_request():
    data = payload()
    data["search"]["parallel_workers"] = 1
    data["ranges"]["protection_barrier"] = {"minimum":.5,"maximum":.75,"step":.05}
    return OptimizationRequest.model_validate(data)


def test_shortlist_is_frozen_no_refill_and_unvalidated_candidates_are_unranked():
    seen = []
    def holdout(req, c, size):
        seen.append((c.candidate_id, size))
        c.validation_status = "REJECTED" if c.candidate_id == "C0001" else "PASSED"
        c.constraint_status = "REJECTED" if c.candidate_id == "C0001" else "PASS"
        return c
    # Preserve structural axes while returning synthetic test economics.
    def adapter(req, c):
        out = evaluated(req, candidate_id=c.candidate_id, coupon=.2-int(c.candidate_id[1:])*.01,
                        protection_barrier=c.protection_barrier)
        return out
    out = list(service.run_events(six_request(), adapter=adapter, validation_adapter=holdout))[-1]["result"]
    assert seen == [(f"C{i:04d}",5) for i in range(1,6)]
    assert out["recommended_id"] == "C0002"
    sixth = out["candidates"][-1]
    assert sixth["constraint_status"] == "PASS" and sixth["validation_status"] == "NOT_SELECTED"
    assert sixth["rank"] is None and not sixth["pareto_efficient"]
    assert out["statistics"]["valid"] == 4 and out["validation"]["exploration_admissible"] == 6


def test_deadline_between_phases_never_recommends_pending_candidates(monkeypatch):
    clock = {"time":0.}
    monkeypatch.setattr(service.time, "monotonic", lambda: clock["time"])
    def exploration(req, c):
        clock["time"] = 121.
        return evaluated(req)
    out = list(service.run_events(request(), adapter=exploration))[-1]["result"]
    assert not out["complete"] and not out["validation"]["complete"]
    assert out["recommended_id"] is None and out["statistics"]["valid"] == 0
    assert out["candidates"][0]["validation_status"] == "PENDING"


@pytest.mark.parametrize("worst_of", [False, True])
def test_real_independent_holdout_is_finite_reproducible_and_uses_pairs(worst_of):
    data = payload()
    if worst_of:
        data["market"]["underlyings"].append({**data["market"]["underlyings"][0], "ticker":"TEST2", "sigma":.3})
        data["market"]["correlation"] = [[1,.4],[.4,1]]
    req = OptimizationRequest.model_validate(data)
    candidate = service.price_candidate(req, next(service.generate_candidates(req)))
    a = validation.validate_candidate(req, candidate.model_copy(deep=True), 1)
    b = validation.validate_candidate(req, candidate.model_copy(deep=True), 1)
    assert a.model_dump() == b.model_dump()
    assert [s["pairs"] for s in a.validation["runs"]] == [1000,2000]
    assert all(math.isfinite(v) for s in a.validation["runs"] for v in s["means"].values())
    assert a.validation_status in ("PASSED", "REJECTED")
    assert a.validation["runs"][-1]["coupon_diagnostic"]["status"] == "AVAILABLE"


def test_exact_date_reference_reproduces_closed_form_single_observation():
    from statistics import NormalDist
    from backend.scripts.validate_product_optimizer import exact_date_reference
    req = request()
    req.ranges.observation_months = [12]
    candidate = next(service.generate_candidates(req))
    candidate.coupon = .1
    script, _ = service.build_candidate(req, candidate)
    event = next(e for e in script.events if e.dates and e.dates[0] > 0)
    t, pay = event.dates[0], event.payment_dates[0]
    sigma, q, r = .2, .02, .03
    norm = NormalDist()
    def d2(k):
        return (-math.log(k)+(r-q-.5*sigma**2)*t)/(sigma*math.sqrt(t))
    loss = norm.cdf(-d2(.6))-math.exp((r-q)*t)*norm.cdf(-d2(.6)-sigma*math.sqrt(t))
    analytic = math.exp(-r*pay)*(1.+.1*norm.cdf(d2(1.))-loss)
    ref = exact_date_reference(req, candidate, pairs=100000)
    price = ref["metrics"]["fair_value"]
    assert abs(price["mean"]-analytic) < 4*price["standard_error"]+1e-6
    assert ref["metrics"]["probability_autocall"]["mean"] == 0
