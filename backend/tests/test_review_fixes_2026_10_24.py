"""Regression oracles for the four established counter-review defects."""
import math

import pytest

from backend.app.api import kid, pricing, simulation
from backend.app.api.emt import _detect_features
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script, resolve_analysis_constats
from backend.app.core.payscript.simulation import solve_for_param
from backend.app.core.product.calendar import freeze_calendar
from backend.app.core.valuation_context import ValuationContext


UL = [{"name": "S1", "ticker": "", "ccy": "EUR", "sigma": .2, "q": 0.}]
CORR = [[1.]]


def payload(**changes):
    return dict(script="AT MATURITY:\n  PAY 1\n", underlyings=UL,
                corr_matrix=CORR, r=.03, T=.25, N=1000, **changes)


@pytest.mark.parametrize("funding", [0., .02])
def test_http_kid_full_price_preserves_funding(authenticated_client, funding):
    authenticated_client.app.include_router(kid.router)
    response = authenticated_client.post("/api/kid/compute", json=payload(funding_spread=funding))
    assert response.status_code == 200, response.text
    assert response.json()["full_price"] == pytest.approx(math.exp(-(.03 + funding) * .25), abs=5.1e-5)


def test_http_kid_full_price_preserves_payment_value_dates_and_curve(authenticated_client):
    authenticated_client.app.include_router(kid.router)
    data = payload(strike_date="2026-01-01", value_date="2026-01-05",
                   payment_date="2026-04-10", funding_curve=[[1., .02]])
    response = authenticated_client.post("/api/kid/compute", json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    value_t = round(4 / 365.25, 6)
    payment_t = round(99 / 365.25, 6)
    assert result["full_price"] == pytest.approx(math.exp(-.05 * (payment_t - value_t)), abs=5.1e-5)
    cell = result["horizons"][-1]["modere"]
    assert cell["net_flows"] == [{"t": round(payment_t - value_t, 6), "cf": 10000.}]


@pytest.mark.parametrize("hypothesis", [
    {"funding_spread": .02}, {"funding_curve": [[1., .02]]},
    {"barrier_monitoring": "continuous"},
    {"strike_date": "2026-01-01", "value_date": "2026-01-05"},
])
def test_http_intermediate_kid_refuses_unsupported_context_before_mc(authenticated_client, monkeypatch, hypothesis):
    authenticated_client.app.include_router(kid.router)
    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported context must be refused before any pricing run")
    monkeypatch.setattr(kid, "run_valuation", forbidden)
    data = payload(**hypothesis)
    data["T"] = 1.
    response = authenticated_client.post("/api/kid/compute", json=data)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("route", ["/api/mtf", "/api/mtf/drilldown"])
@pytest.mark.parametrize("hypothesis", [
    {"funding_spread": .02}, {"funding_curve": [[1., .02]]},
    {"strike_date": "2026-01-01", "payment_date": "2027-02-01"},
])
def test_http_mtf_and_detail_refuse_unsupported_context(authenticated_client, route, hypothesis):
    authenticated_client.app.include_router(pricing.router)
    data = payload(**hypothesis)
    data.update(T=1., main_price=100., n_outer=20, n_inner=50, n_dates=2,
                t=.25, scenario_ids=[0])
    response = authenticated_client.post(route, json=data)
    assert response.status_code == 422, response.text
    assert any(word in response.json()["detail"] for word in ("funding", "paiements différés"))


def test_kid_full_honors_continuous_barrier_monitoring():
    # Same draws: bridge extrema are below the sampled weekly extrema.
    script = parse_script("AT MATURITY:\n  PAY WOF_MIN\n")
    context = ValuationContext(UL, CORR, .03, .25, 1000, "constant", barrier_monitoring="continuous")
    row = kid._mc_percentiles(script, UL, CORR, .03, .25, .25, 1000,
                              "constant", 42, True, {}, [], 0., 0., valuation_context=context)
    direct = run_mc(script, UL, CORR, .03, .25, 1000, "constant", 42,
                    barrier_monitoring="continuous")
    weekly = run_mc(script, UL, CORR, .03, .25, 1000, "constant", 42)
    assert row["pv"] == direct["price"]
    assert direct["price"] < weekly["price"]


@pytest.mark.parametrize("r", [0., .03])
@pytest.mark.parametrize("stop", [False, True])
@pytest.mark.parametrize("horizon", [.125, .25, .5, .75, .875])
def test_kid_cash_and_receivable_are_distinct_around_payment(stop, horizon, r):
    script = parse_script("AT 0.25:\n  PAY 1\n" + ("  STOP\n" if stop else "") + "AT MATURITY:\n  PAY 0\n")
    script.events[0].payment_dates = [.75]
    row = kid._horizon_percentiles(script, UL, CORR, r, 1., horizon, 1000,
                                   "constant", 42, True, {}, [], 0., 0., n_outer=4, n_inner=8)
    # Before observation the deterministic future payment is already in the
    # continuation; after observation it is a claim, including after STOP.
    expected = math.exp(-r * (.75 - horizon)) if horizon < .75 else 1.
    assert row["p50"] == pytest.approx(expected, abs=5.1e-7)
    flows = [flow for flow in row["scenarios"]["p50"]["flows"] if flow["cf"]]
    expected_date = min(horizon, .75)
    assert flows == [{"t": expected_date, "cf": pytest.approx(expected, abs=5.1e-7)}]


def test_http_kid_frozen_calendar_keeps_claim_after_stop(authenticated_client, monkeypatch):
    authenticated_client.app.include_router(kid.router)
    source = "AT 0.25:\n  PAY 1\n  STOP\nAT MATURITY:\n  PAY 0\n"
    request = kid.KidRequest(**{**payload(), "script": source, "T": 1.})
    script = resolve_analysis_constats(parse_script(source), request)
    script.events[0].payment_dates = [.75]
    real_replay = kid.run_mark_to_future
    def bounded_replay(*args, **kwargs):
        kwargs.update(n_outer=4, n_inner=8)
        return real_replay(*args, **kwargs)
    monkeypatch.setattr(kid, "run_mark_to_future", bounded_replay)
    data = payload(frozen_schedule=freeze_calendar(script))
    data.update(script=source, T=1.)
    response = authenticated_client.post("/api/kid/compute", json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    half, full = result["horizons"]
    assert half["modere"]["amount"] == round(10000 * math.exp(-.03 * .25), 2)
    assert half["modere"]["net_flows"] == [{"t": .5, "cf": half["modere"]["amount"]}]
    assert full["modere"]["net_flows"] == [{"t": .75, "cf": 10000.}]
    assert result["full_price"] == pytest.approx(math.exp(-.03 * .75), abs=5.1e-5)


@pytest.mark.parametrize("name", ["GEARING", "LEVERAGE"])
@pytest.mark.parametrize("notation", ["2", "200%"])
@pytest.mark.parametrize("declaration", ["PARAM", "PARAM()"])
def test_emt_leverage_depends_on_economic_value(name, notation, declaration):
    text = f"{declaration} {name} = {notation}\nAT MATURITY:\n  PAY 1 + MAX({name} * (S[1] - 1), 0)\n"
    compiled = parse_script(text)
    assert _detect_features(compiled, 1, text)["has_leverage"]
    assert _detect_features(compiled, 1, text, {name: [1., 2.]})["has_leverage"]
    assert not _detect_features(compiled, 1, text, {name: [1., .5]})["has_leverage"]


@pytest.mark.parametrize("payoff, bounds, target, reason", [
    ("IF K >= 1:\n    PAY 1\n  ELSE:\n    PAY 0", (0., 2.), .5, "parameter_tolerance"),
    ("PAY 1000000 * K", (0., 1.), .123456, "parameter_rounding"),
])
def test_solver_does_not_claim_price_convergence_from_axis_or_rounding(payoff, bounds, target, reason):
    script = parse_script(f"PARAM K = 0\nAT MATURITY:\n  {payoff}\n")
    result = solve_for_param(script, UL, CORR, 0., .25, "constant", 42,
                             {}, "K", target, *bounds, N=16, tol=1e-4, max_iter=60,
                             param_tol=1e-12 if reason == "parameter_rounding" else 5e-7)
    direct = run_mc(script, UL, CORR, 0., .25, 16, "constant", 42,
                    user_params={"K": result["param_value"]})
    assert result["achieved_price"] == direct["price"]
    assert not result["converged"]
    assert not result["price_converged"]
    assert abs(result["residual"]) > result["price_tolerance"]
    assert result["stop_reason"] == reason
    assert result["published_parameter_repriced"]


def test_solver_affine_price_root_is_confirmed_at_published_parameter():
    script = parse_script("PARAM K = 0\nAT MATURITY:\n  PAY 2 * K\n")
    result = solve_for_param(script, UL, CORR, 0., .25, "constant", 42,
                             {}, "K", .6, 0., 1., N=16, tol=1e-5)
    assert result["converged"] and result["price_converged"]
    assert result["stop_reason"] == "price_tolerance"
    assert abs(2 * result["param_value"] - .6) <= 1e-5


def test_http_solver_reports_price_failure_and_separate_tolerances(authenticated_client):
    authenticated_client.app.include_router(simulation.router)
    data = payload()
    data.update(script="PARAM K = 0\nAT MATURITY:\n  IF K >= 1:\n    PAY 1\n  ELSE:\n    PAY 0\n",
                r=0., param_name="K", target_price=.5, lo=0., hi=2.,
                tol=.0001, param_tol=.00001, max_iter=40)
    response = authenticated_client.post("/api/solve", json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result["converged"]
    assert result["stop_reason"] == "parameter_tolerance"
    assert result["residual"] == result["achieved_price"] - .5
    assert result["parameter_tolerance"] == .00001


def test_kid_intermediate_preserves_final_payment_override():
    script = parse_script("AT MATURITY:\n  PAY 1\n")
    context = ValuationContext(UL, CORR, .03, 1., 1000, "constant", maturity_payment_t=1.25)
    result = kid._horizon_percentiles(script, UL, CORR, .03, 1., .5, 1000,
                                      "constant", 42, True, {}, [], 0., 0.,
                                      n_outer=4, n_inner=8, valuation_context=context)
    assert result["p50"] == pytest.approx(math.exp(-.03 * .75), abs=5.1e-7)


def test_kid_does_not_double_count_paid_coupon_and_unpaid_claim():
    script = parse_script("AT 0.10:\n  PAY 0.2\nAT 0.25:\n  PAY 0.3\n  STOP\nAT MATURITY:\n  PAY 0\n")
    script.events[0].payment_dates = [.2]
    script.events[1].payment_dates = [.75]
    result = kid._horizon_percentiles(script, UL, CORR, .03, 1., .5, 1000,
                                      "constant", 42, True, {}, [], 0., 0.,
                                      n_outer=4, n_inner=8)
    expected_claim = .3 * math.exp(-.03 * .25)
    assert result["p50"] == pytest.approx(.2 + expected_claim, abs=5.1e-7)
    assert result["scenarios"]["p50"]["flows"] == [
        {"t": .2, "cf": .2}, {"t": .5, "cf": pytest.approx(expected_claim, abs=5.1e-7)}]


def test_http_plain_mtf_and_detail_still_agree(authenticated_client):
    authenticated_client.app.include_router(pricing.router)
    data = payload()
    data.update(T=1., main_price=100., n_outer=20, n_inner=50, n_dates=2)
    fan = authenticated_client.post("/api/mtf", json=data)
    assert fan.status_code == 200, fan.text
    row = fan.json()["results"][0]
    detail = authenticated_client.post("/api/mtf/drilldown", json={**data, "t": row["t"], "scenario_ids": [0]})
    assert detail.status_code == 200, detail.text
    assert detail.json()["scenarios"][0]["mtf"] == pytest.approx(row["pvs"][0], abs=1e-4)
