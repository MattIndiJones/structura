"""KID computed by the PRIIPs Category 3 historical bootstrap, end to end.

The history is injected (no network): each test changes ONE market input and
requires the published figure to move the way the regulation says — a figure
that does not move when its input changes is a disconnected wire.
"""
from datetime import date, timedelta

import numpy as np
import pytest

from backend.app.api import kid
from backend.app.core import priips_bootstrap

UL = [{"name": "S1", "ticker": "TK1", "ccy": "EUR", "sigma": .2, "q": 0.}]


def history(daily_mean, daily_vol, n_days=1260, seed=11):
    draws = np.random.default_rng(seed).standard_normal(n_days)
    draws = (draws - draws.mean()) / draws.std()
    returns = daily_mean + daily_vol * draws
    levels = 100 * np.exp(np.r_[0., np.cumsum(returns)])
    dates = [(date(2021, 1, 1) + timedelta(days=int(i * 365.25 / 252))).isoformat()
             for i in range(len(levels))]
    return priips_bootstrap.historical_returns(dates, {"TK1": list(levels)}, ["TK1"])


def compute(client, monkeypatch, hist, script="AT MATURITY:\n  PAY S[1]\n", T=2.):
    monkeypatch.setattr(kid, "_bootstrap_history", lambda req, uls: hist)
    response = client.post("/api/kid/compute", json=dict(
        script=script, underlyings=UL, corr_matrix=[[1.]], r=.03, T=T, N=1000))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def client(authenticated_client):
    authenticated_client.app.include_router(kid.router)
    return authenticated_client


def test_the_kid_says_it_bootstrapped_and_ran_ten_thousand_simulations(client, monkeypatch):
    result = compute(client, monkeypatch, history(0.0, 0.01))
    assert result["simulation"]["method"] == "historical_bootstrap"
    assert result["simulation"]["simulations"] == 10_000          # Annex II point 19
    assert result["simulation"]["observations"] == 1260
    # Annex IV point 32: a two-year RHP shows the one-year period and the RHP.
    assert [h["T"] for h in result["horizons"]] == [1.0, 2.0]


def test_the_observed_drift_moves_the_scenarios_and_never_the_var(client, monkeypatch):
    """Annex IV point 25 keeps the observed return for the scenarios; Annex II
    point 22(c) removes it for the VaR. A strongly rising history must lift
    the moderate scenario and leave the VaR where the volatility puts it."""
    flat = compute(client, monkeypatch, history(0.0, 0.01))
    rising = compute(client, monkeypatch, history(0.0008, 0.01))
    assert rising["horizons"][-1]["modere"]["value"] > flat["horizons"][-1]["modere"]["value"] + 1000
    assert rising["var_975"] == pytest.approx(flat["var_975"], abs=0.01)


def test_a_more_volatile_history_raises_the_market_risk_class(client, monkeypatch):
    calm = compute(client, monkeypatch, history(0.0, 0.004))
    wild = compute(client, monkeypatch, history(0.0, 0.025))
    assert wild["var_975"] < calm["var_975"]
    assert wild["vev"] > calm["vev"]
    assert wild["mrm"] > calm["mrm"]


def test_missing_ticker_is_refused_rather_than_silently_simulated(client):
    response = client.post("/api/kid/compute", json=dict(
        script="AT MATURITY:\n  PAY 1\n", underlyings=[{**UL[0], "ticker": ""}],
        corr_matrix=[[1.]], r=.03, T=1., N=1000))
    assert response.status_code == 422
    assert "risque-neutre" in response.json()["detail"]


def history_with_crisis(crisis_vol, seed=11):
    calm = np.random.default_rng(seed).standard_normal(1230) * 0.008
    crisis = np.random.default_rng(seed + 1).standard_normal(30) * crisis_vol
    returns = np.r_[calm[:600], crisis, calm[600:]]
    levels = 100 * np.exp(np.r_[0., np.cumsum(returns)])
    dates = [(date(2021, 1, 1) + timedelta(days=int(i * 365.25 / 252))).isoformat()
             for i in range(len(levels))]
    return priips_bootstrap.historical_returns(dates, {"TK1": list(levels)}, ["TK1"])


def test_stress_uses_its_own_percentile_per_period_and_a_crisis_lowers_it(client, monkeypatch):
    """Annex IV points 26-27: stressed bootstrap, 1st percentile for the
    one-year period, 5th for the two-year RHP; point 20: never better than the
    unfavourable scenario. A month of crisis in the history must lower it."""
    mild = compute(client, monkeypatch, history_with_crisis(0.012))
    severe = compute(client, monkeypatch, history_with_crisis(0.05))
    one_year, rhp = severe["horizons"]
    assert one_year["stress"]["percentile"] == 1
    assert rhp["stress"]["percentile"] == 5
    for h in (*mild["horizons"], *severe["horizons"]):
        assert h["stress"]["value"] <= h["defavorable"]["value"]
    assert severe["horizons"][-1]["stress"]["value"] < mild["horizons"][-1]["stress"]["value"]


def test_a_stress_better_than_the_unfavourable_scenario_is_capped():
    """Annex IV point 20, on the arithmetic alone."""
    def dist(amount):
        cell = {"amount": amount, "life": 2.0, "flows": [{"t": 2.0, "cf": amount}]}
        keys = ("p1", "p5", "p10", "p50", "p90")
        return {**{k: amount for k in keys}, "scenarios": {k: dict(cell) for k in keys}}
    row = kid._scenario_row(dist(0.90), 2.0, 0., 0., 0., stress=dist(0.95))
    assert row["stress"]["value"] == row["defavorable"]["value"]
    assert row["stress"]["capped_at_unfavourable"] is True


def test_costs_reach_the_published_cost_impact(client, monkeypatch):
    """A cost entered on screen must move the published cost table."""
    monkeypatch.setattr(kid, "_bootstrap_history", lambda req, uls: history(0.0, 0.01))
    base = dict(script="AT MATURITY:\n  PAY S[1]\n", underlyings=UL, corr_matrix=[[1.]], r=.03, T=2., N=1000)
    free = client.post("/api/kid/compute", json=base).json()
    charged = client.post("/api/kid/compute", json={**base, "cost_entry": 2.0, "cost_ongoing": 1.0}).json()
    assert free["horizons"][-1]["costs_over_time"]["total_costs"] == 0
    assert charged["horizons"][-1]["costs_over_time"]["total_costs"] > 300
    assert charged["horizons"][-1]["costs_over_time"]["annual_cost_impact_pct"] > 1.0
    assert charged["costs"]["composition"]["entry"]["amount"] == 200
