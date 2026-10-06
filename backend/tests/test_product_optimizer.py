"""Optimizer contracts, economic cases and authenticated orchestration."""
from copy import deepcopy
import json
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from backend.app.core.product_optimizer.contracts import OptimizationRequest, ParameterRange
from backend.app.core.product_optimizer.capabilities import capabilities
from backend.app.core.product_optimizer import service
from backend.app.core.payscript.engine import run_mc
from backend.app.core.schemas import PricingRequest


def payload():
    return {
        "strike_date": "2026-10-05", "convention": "modified_following", "currency": "EUR",
        "market": {"as_of": "2026-10-05", "rate": .03, "source": "USER_ASSUMPTION",
                   "underlyings": [{"ticker": "TEST", "name": "Indice test", "currency": "EUR", "sigma": .2, "q": .02}],
                   "correlation": [[1.]]},
        "ranges": {"maturity_months": {"minimum": 12, "maximum": 12, "step": 12},
                   "protection_barrier": {"minimum": .6, "maximum": .6, "step": .05},
                   "autocall_trigger": {"minimum": 1, "maximum": 1, "step": .05},
                   "observation_months": [3]},
        "search": {"simulations": 1000, "max_candidates": 32},
        "constraints": {"price_tolerance": .03},
    }


def request(**changes):
    p = payload()
    p.update(changes)
    return OptimizationRequest.model_validate(p)


@pytest.mark.parametrize("patch", [
    {"model": "heston"}, {"product_family": "phoenix"}, {"objective": "opaque_ai"},
    {"convention": "unknown"}, {"currency": "XXX"}, {"funding_spread": .01},
    {"search": {"simulations": 20001}}, {"search": {"seed": 43}},
    {"objective": "target_coupon"},
    {"constraints": {"coupon_minimum": .3, "coupon_maximum": .1}},
])
def test_unsupported_inputs_are_rejected(patch):
    with pytest.raises(ValidationError):
        request(**patch)


@pytest.mark.parametrize("bounds", [(-1, 1, .1), (2, 1, .1), (1, 2, 0), (1, 2, math.nan), (0, 1e200, .1)])
def test_ranges_are_bounded_finite_ordered(bounds):
    with pytest.raises(ValidationError):
        ParameterRange(minimum=bounds[0], maximum=bounds[1], step=bounds[2])


def test_decimal_grid_and_count_have_same_endpoints():
    r = ParameterRange(minimum=.5, maximum=.7, step=.05)
    assert r.values() == [.5, .55, .6, .65, .7]
    assert r.count == 5
    assert ParameterRange(minimum=.5, maximum=.69, step=.05).values() == [.5, .55, .6, .65]


def test_market_date_currency_duplicates_and_correlation_are_not_guessed():
    for kind in ["date", "currency", "duplicates", "correlation"]:
        p = payload()
        if kind == "date":
            p["market"]["as_of"] = "2026-10-04"
        elif kind == "currency":
            p["market"]["underlyings"][0]["currency"] = "USD"
        elif kind == "duplicates":
            p["market"]["underlyings"] *= 2
            p["market"]["correlation"] = [[1, .5], [.5, 1]]
        else:
            p["market"]["correlation"] = [[.5]]
        with pytest.raises(ValidationError):
            OptimizationRequest.model_validate(p)


def test_registry_is_explicit_and_not_shared_mutable_state():
    caps = capabilities()
    assert caps["families"][0]["models"] == ["constant"]
    assert caps["families"][1]["status"] == "UNSUPPORTED"
    caps["families"][0]["models"].append("heston")
    assert capabilities()["families"][0]["models"] == ["constant"]


def test_estimate_caps_work_before_generation_or_pricing():
    p = payload()
    p["ranges"]["maturity_months"] = {"minimum":12,"maximum":60,"step":1}
    p["ranges"]["protection_barrier"] = {"minimum":.3,"maximum":.8,"step":.01}
    req = OptimizationRequest.model_validate(p)
    estimate = service.estimate_search(req)
    assert estimate["candidate_count"] == 49*51
    assert not estimate["allowed"]
    with pytest.raises(ValueError):
        next(service.run_events(req))


def test_generator_prunes_invalid_economics_and_stub():
    p = payload()
    p["ranges"]["maturity_months"] = {"minimum":13,"maximum":13,"step":1}
    req = OptimizationRequest.model_validate(p)
    c = next(service.generate_candidates(req))
    assert c.rejection_reasons and "stubs" in c.rejection_reasons[0]


def test_calendar_and_coupon_unit_reuse_catalogue():
    req = request()
    c = next(service.generate_candidates(req))
    script, inputs = service.build_candidate(req, c)
    dates = script.events[0].dates
    assert len(dates) == 4 and dates[0] > 0
    assert script.events[0].ranks == [1, 2, 3, 4]
    assert all(p > t for t, p in zip(dates, script.events[0].payment_dates))
    assert PricingRequest.model_validate(inputs).strike_date == req.strike_date
    assert inputs["script"] == service.PRODUCTS["autocall_athena"]["script"]


def evaluated(req, **updates):
    c = next(service.generate_candidates(req))
    defaults = dict(coupon=.08, fair_value=1., price_ic95=[.999, 1.001],
                    pricing_status="PRICED", analytics_status="AVAILABLE",
                    probability_loss=.1, probability_loss_ic95=[.08,.12],
                    probability_autocall=.7, probability_autocall_ic95=[.67,.73],
                    expected_maturity=.6, expected_maturity_upper95=.65)
    for k, v in {**defaults, **updates}.items():
        setattr(c, k, v)
    return c


@pytest.mark.parametrize("constraint", [
    {"max_probability_loss": .11}, {"min_probability_autocall": .68},
    {"max_expected_maturity": .62}, {"price_tolerance": .0005},
])
def test_filter_uses_uncertainty_bounds_not_only_point_estimates(constraint):
    req = request(constraints=constraint)
    c = evaluated(req)
    service.filter_candidate(req, c)
    assert c.constraint_status == "REJECTED" and c.rejection_reasons


def test_missing_analytics_never_pass_and_target_coupon_is_enforced():
    req = request(objective="target_coupon", constraints={"target_coupon": .1, "coupon_tolerance": .005})
    c = evaluated(req)
    service.filter_candidate(req, c)
    assert c.constraint_status == "REJECTED"
    missing = evaluated(req, coupon=.1, analytics_status="UNAVAILABLE")
    service.filter_candidate(req, missing)
    assert missing.constraint_status == "REJECTED"


def test_ranking_and_pareto_are_deterministic():
    req = request()
    a = evaluated(req, candidate_id="A", coupon=.10, protection_barrier=.6, constraint_status="PASS")
    b = evaluated(req, candidate_id="B", coupon=.09, protection_barrier=.5, constraint_status="PASS")
    c = evaluated(req, candidate_id="C", coupon=.08, protection_barrier=.7, constraint_status="PASS")
    assert [x.candidate_id for x in service.rank_candidates(req, [c,b,a])] == ["A","B","C"]
    assert a.pareto_efficient and b.pareto_efficient and not c.pareto_efficient
    req.objective = "maximize_protection"
    assert service.rank_candidates(req, [a,b,c])[0].candidate_id == "B"


def test_one_failure_does_not_stop_search_or_leak_exception(monkeypatch):
    p = payload()
    p["ranges"]["protection_barrier"]["maximum"] = .65
    req = OptimizationRequest.model_validate(p)
    def adapter(req, candidate):
        if candidate.candidate_id == "C0001":
            raise RuntimeError("secret internal detail")
        return evaluated(req, candidate_id=candidate.candidate_id)
    events = list(service.run_events(req, adapter=adapter))
    out = events[-1]["result"]
    assert out["statistics"]["failed"] == 1 and out["statistics"]["valid"] == 1
    assert out["recommended_id"] == "C0002"
    assert "secret internal detail" not in json.dumps(out)


def test_time_budget_returns_explicit_partial_scope(monkeypatch):
    values = iter([0,121,122])
    monkeypatch.setattr(service.time, "monotonic", lambda: next(values))
    result = list(service.run_events(request()))[-1]["result"]
    assert not result["complete"] and result["statistics"]["not_evaluated"] == 1
    assert result["recommended_id"] is None


def test_real_coupon_solver_and_reprice_are_deterministic():
    req = request()
    a = service.price_candidate(req, next(service.generate_candidates(req)))
    b = service.price_candidate(req, next(service.generate_candidates(req)))
    assert a.model_dump() == b.model_dump()
    assert a.pricing_status == "PRICED" and a.analytics_status == "AVAILABLE"
    assert abs(a.fair_value-1) < .0001
    assert a.pricing_input["user_params"]["COUPON"] == pytest.approx(a.coupon/4)
    assert 0 <= a.probability_loss <= 1 and 0 <= a.probability_autocall <= 1


def test_athena_flat_path_early_call_and_final_call_are_distinct():
    p = payload()
    p["market"]["rate"] = .03
    p["market"]["underlyings"][0].update(sigma=0, q=0)
    req = OptimizationRequest.model_validate(p)
    early = service.price_candidate(req, next(service.generate_candidates(req)))
    assert early.probability_autocall == 1 and early.probability_loss == 0
    assert early.expected_maturity == pytest.approx(.25, abs=.015)
    req.ranges.observation_months = [12]
    final = service.price_candidate(req, next(service.generate_candidates(req)))
    assert final.probability_autocall == 0
    assert final.probability_loss == 0
    assert final.expected_maturity == pytest.approx(1, abs=.015)


def test_real_worst_of_basket_is_supported():
    p = payload()
    other = deepcopy(p["market"]["underlyings"][0])
    other.update(ticker="TEST2", name="Second indice", sigma=.25)
    p["market"]["underlyings"].append(other)
    p["market"]["correlation"] = [[1,.4],[.4,1]]
    req = OptimizationRequest.model_validate(p)
    c = service.price_candidate(req, next(service.generate_candidates(req)))
    assert c.pricing_status == "PRICED" and math.isfinite(c.coupon)


def test_manual_dividend_assumption_reaches_pricing_and_changes_value():
    req = request()
    c = next(service.generate_candidates(req))
    script, inputs = service.build_candidate(req, c)
    def price():
        return run_mc(script, inputs["underlyings"], inputs["corr_matrix"], inputs["r"],
                      inputs["T"], 1000, "constant", 42,
                      user_params={**inputs["user_params"], "COUPON": .02})["price"]
    before = price()
    req.market.underlyings[0].q = .2
    script, inputs = service.build_candidate(req, c)
    assert before - price() > .01


def test_catalogue_payoff_capital_loss_and_protection_branches():
    req = request()
    c = next(service.generate_candidates(req))
    c.autocall_trigger = 1.2
    script, inputs = service.build_candidate(req, c)
    for dividend, protected in [(.2, True), (.8, False)]:
        ul = [{"name":"Test","sigma":0,"q":dividend}]
        priced = run_mc(script, ul, [[1]], 0, inputs["T"], 1000, "constant", 42,
                        user_params={"COUPON":.02,"M_AC_BAR":1.2,"M_KI_BAR":.6})
        assert priced["price"] == pytest.approx(1 if protected else math.exp(-dividend*round(inputs["T"]*52)/52), abs=.001)


@pytest.fixture
def api_client():
    from backend.app.api import product_optimizer as api
    from backend.app.api.auth import get_current_user
    from backend.app.db.database import get_session
    from backend.app.db.models import Underlying, User
    db = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread":False})
    SQLModel.metadata.create_all(db)
    session = Session(db)
    session.add(Underlying(ticker="TEST", label="Test", ccy="EUR", group_name="Indices"))
    session.commit()
    app = FastAPI()
    app.include_router(api.router)
    current = {"user":User(id=1,username="alice",email="a@test",password_hash="x")}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client, app, current
    session.close()
    db.dispose()


def test_api_authentication_validation_and_catalogue(api_client):
    from backend.app.api.auth import get_current_user
    client, app, _ = api_client
    assert client.get('/api/product-optimizer/capabilities').status_code == 200
    assert client.post('/api/product-optimizer/estimate-search',json=payload()).json()["allowed"]
    p = payload(); p["model"] = "heston"
    assert client.post('/api/product-optimizer/run',json=p).status_code == 422
    p = payload(); p["market"]["underlyings"][0]["ticker"] = "UNKNOWN"
    assert client.post('/api/product-optimizer/estimate-search',json=p).status_code == 422
    del app.dependency_overrides[get_current_user]
    assert client.get('/api/product-optimizer/capabilities').status_code == 401
    assert client.post('/api/product-optimizer/run',json=payload()).status_code == 401


def test_api_runs_are_ephemeral_user_isolated_and_capacity_is_released(api_client, monkeypatch):
    from backend.app.api import product_optimizer as api
    from backend.app.db.models import User
    client, _, current = api_client
    monkeypatch.setattr(api, "run_events", lambda req: iter([{"type":"result","result":{"rate":req.market.rate}}]))
    a = client.post('/api/product-optimizer/run',json=payload())
    assert a.status_code == 200 and a.headers['cache-control'] == 'no-store'
    current['user'] = User(id=2,username="bob",email="b@test",password_hash="x")
    p = payload(); p['market']['rate'] = .04
    b = client.post('/api/product-optimizer/run',json=p)
    assert json.loads(a.text)['result']['rate'] == .03
    assert json.loads(b.text)['result']['rate'] == .04
    assert client.get('/api/product-optimizer/result/1').status_code == 404
    assert api._capacity.acquire(blocking=False)
    try:
        assert client.post('/api/product-optimizer/run',json=p).status_code == 429
    finally:
        api._capacity.release()


def test_api_stream_error_releases_capacity(api_client, monkeypatch):
    from backend.app.api import product_optimizer as api
    client, _, _ = api_client
    def broken(_req):
        yield {'type':'started'}
        raise RuntimeError('private traceback')
    monkeypatch.setattr(api, 'run_events', broken)
    response = client.post('/api/product-optimizer/run',json=payload())
    assert json.loads(response.text.splitlines()[-1])['type'] == 'error'
    assert 'private traceback' not in response.text
    assert api._capacity.acquire(blocking=False)
    api._capacity.release()
