"""Historical bootstrap of PRIIPs Category 3 (Annex II points 19-22, Annex IV 25-26).

Synthetic histories with a known answer: each test states what the
regulation's construction must produce, independently of the implementation.
"""
import math
from datetime import date, timedelta

import numpy as np
import pytest

from backend.app.core import priips_bootstrap as boot
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script

UL = dict(name="S1", ticker="TK1", ccy="EUR", sigma=0.20, q=0.0)


def _history(returns, start=date(2020, 1, 1), tickers=("TK1",)):
    returns = np.asarray(returns, dtype=float).reshape(len(returns), -1)
    levels = np.vstack([np.ones((1, returns.shape[1])), np.exp(np.cumsum(returns, axis=0))])
    dates = [(start + timedelta(days=int(i * 365.25 / 252))).isoformat() for i in range(len(levels))]
    prices = {t: list(levels[:, j] * 100) for j, t in enumerate(tickers)}
    return boot.historical_returns(dates, prices, list(tickers))


def _normal_returns(n_days, daily_mean, daily_vol, seed=1):
    draws = np.random.default_rng(seed).standard_normal(n_days)
    draws = (draws - draws.mean()) / draws.std()        # exact sample moments
    return daily_mean + daily_vol * draws


def test_risk_neutral_regime_makes_the_discounted_forward_a_martingale():
    """Point 22(c): after removing the measured mean and 0.5 sigma^2 and adding
    the risk-free forward, E[DF(T) S_T] = S_0 up to Monte Carlo noise."""
    history = _history(_normal_returns(1260, 0.0008, 0.0125))     # strong measured drift
    r = 0.03
    simulator = boot.BootstrapSimulator(history, "risk_neutral",
                                        discount_factor=lambda t: math.exp(-r * t))
    script = parse_script("AT MATURITY\n  PAY S[1]\n")
    res = run_mc(script, [UL], [[1.0]], r=r, T_max=3.0, N=20_000, model="constant",
                 seed=7, antithetic=False, path_simulator=simulator)
    half_width = (res["ic95"][1] - res["ic95"][0]) / 2
    assert abs(res["price"] - 1.0) <= max(half_width, 0.004)


def test_one_drawn_date_moves_every_underlying_together():
    """Point 22(b): a simulated day draws one historical date for all
    underlyings — identical histories give identical simulated paths."""
    one = _normal_returns(800, 0.0, 0.01)
    history = _history(np.column_stack([one, one]), tickers=("A", "B"))
    simulator = boot.BootstrapSimulator(history, "historical")
    S = simulator(52, 1 / 52, 2, 500, np.random.default_rng(3))
    assert np.array_equal(S[:, 0, :], S[:, 1, :])


def test_historical_regime_keeps_the_observed_drift():
    """Annex IV point 25: no correction — the mean log-return over one year is
    the observed daily mean times 252 trading days."""
    mean = 0.0004
    history = _history(_normal_returns(1260, mean, 0.01))
    S = boot.BootstrapSimulator(history, "historical")(52, 1 / 52, 1, 20_000, np.random.default_rng(5))
    assert np.log(S[-1, 0, :]).mean() == pytest.approx(mean * 252, abs=0.004)


def test_stress_regime_is_recentred_on_minus_half_stressed_variance():
    """Annex IV point 26(d): E*[r] = -0.5 sigma_S^2 N over the holding period."""
    history = _history(_normal_returns(1260, 0.0006, 0.01))
    simulator = boot.BootstrapSimulator(history, "stress", stress_years=2.0)
    sigma_s = simulator.stressed_volatility[0]
    S = simulator(104, 1 / 52, 1, 20_000, np.random.default_rng(9))
    expected = -0.5 * sigma_s ** 2 * 504
    assert np.log(S[-1, 0, :]).mean() == pytest.approx(expected, abs=0.006)


def test_stressed_volatility_takes_the_regulatory_window_and_percentile():
    """Annex IV point 18: 21-day windows and the 99th percentile for one year,
    63-day windows and the 95th percentile beyond. A calm history with one
    turbulent month must come out between the two regimes' volatilities."""
    calm = _normal_returns(1000, 0.0, 0.005, seed=2)
    storm = _normal_returns(30, 0.0, 0.04, seed=4)
    returns = np.r_[calm[:500], storm, calm[500:]]
    one_year = boot.stressed_volatility(returns, 1.0)
    longer = boot.stressed_volatility(returns, 3.0)
    assert 0.005 < longer < one_year <= 0.045


def test_dates_missing_for_one_underlying_are_dropped_for_all():
    history = _history(np.column_stack([_normal_returns(700, 0, .01), _normal_returns(700, 0, .01, 2)]),
                       tickers=("A", "B"))
    dates = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(800)]
    prices = {"A": [100.0] * 800, "B": [100.0] * 800}
    prices["B"][10] = None
    filtered = boot.historical_returns(dates, prices, ["A", "B"])
    assert filtered.dropped_dates == 1
    assert history.observations == 700


def test_less_than_two_years_of_common_history_is_refused():
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(400)]
    with pytest.raises(ValueError, match="au moins 2 ans"):
        boot.historical_returns(dates, {"A": [100.0] * 400}, ["A"])


def test_supplied_paths_refuse_antithetic_and_continuous_monitoring():
    history = _history(_normal_returns(800, 0, .01))
    simulator = boot.BootstrapSimulator(history, "historical")
    script = parse_script("AT MATURITY\n  PAY S[1]\n")
    with pytest.raises(ValueError, match="antithétiques"):
        run_mc(script, [UL], [[1.0]], r=0.0, T_max=1.0, N=1000, model="constant",
               seed=1, antithetic=True, path_simulator=simulator)
