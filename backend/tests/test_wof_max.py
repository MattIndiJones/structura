"""WOF_MAX: running maximum of the worst-of, and the worst-of Shark note built on it.

The highest worst-of is the max over time of the min across assets. It cannot
be read from BOF_MAX or S_MAX, which is why the Shark note used to knock out
on the best-of while paying on the worst-of.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from dateutil.relativedelta import relativedelta
from scipy.integrate import quad
from scipy.stats import norm

from backend.app.core.payscript.backtest import _historical_running_extrema
from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.evaluation import _running_state
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.watchlist_observations import _joint_wof_max

STRIKE = date(2026, 9, 14)
R, Q, SIG = 0.03, 0.02, 0.22
UL = dict(name="S1", ticker="", ccy="EUR", sigma=SIG, q=Q, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
SHARK = {"PART": 1.0, "STRIKE": 1.0, "M_KO_BAR": 1.3, "REBATE": 0.03}


def _compiled(script: str, years: int = 3):
    maturity = STRIKE + relativedelta(years=years)
    values = {"STARTDATE": {"date": STRIKE.isoformat(), "window_length": None, "window_frequency": "1D"},
              "MATURITYDATE": maturity.isoformat()}
    compiled = resolve_constats(parse_script(script), values, anchor=STRIKE, currency="EUR")
    return compiled, max(d for e in compiled.events for d in e.dates)


def _price(script, n=1, rho=0.0, N=20000, monitoring="weekly"):
    compiled, T = _compiled(script)
    corr = [[1.0 if i == j else rho for j in range(n)] for i in range(n)]
    res = run_mc(compiled, [dict(UL, name=f"S{i + 1}") for i in range(n)], corr, r=R, T_max=T, N=N,
                 model="constant", seed=11, user_params=SHARK, barrier_monitoring=monitoring)
    return res["price"], (res["ic95"][1] - res["ic95"][0]) / 3.92, T


def test_wof_max_is_the_running_max_of_the_worst_of_not_of_any_asset():
    # Two assets, one path, four steps. The worst-of peaks at 1.10 on step 2;
    # each asset alone peaks higher (1.40 and 1.25) on different steps.
    path = np.array([[1.00, 1.00], [1.40, 0.95], [1.10, 1.15], [0.90, 1.25], [1.05, 1.00]])
    S = path[:, :, None]
    state = _running_state(None, S, 2, 1, None, None)
    assert state.WOF_max[:, 0].tolist() == pytest.approx([0.95, 1.10, 1.10, 1.10])
    assert state.BOF_max[-1, 0] == pytest.approx(1.40)
    inherited = _running_state(None, S, 2, 1, None, None, wof_max_init=1.20)
    assert inherited.WOF_max[-1, 0] == pytest.approx(1.20)


def test_shark_catalogue_knocks_out_on_the_worst_of():
    script = PRODUCTS["shark_note"]["script"]
    assert "WOF_MAX >= M_KO_BAR" in script and "BOF_MAX" not in script


def test_mono_shark_matches_the_up_and_out_closed_form_under_continuous_monitoring():
    price, se, T = _price(PRODUCTS["shark_note"]["script"], monitoring="continuous", N=40000)
    mu, s, h = R - Q - SIG**2 / 2, SIG * math.sqrt(T), math.log(1.3)

    def no_touch(x):
        if x >= h:
            return 0.0
        return (norm.pdf((x - mu * T) / s) - math.exp(2 * mu * h / SIG**2)
                * norm.pdf((x - 2 * h - mu * T) / s)) / s
    lo = mu * T - 9 * s
    p_nt, _ = quad(no_touch, lo, h, limit=200)
    call_nt, _ = quad(lambda x: max(math.exp(x) - 1, 0) * no_touch(x), 0.0, h, limit=200)
    ref = math.exp(-R * T) * (1 + call_nt + 0.03 * (1 - p_nt))
    assert price == pytest.approx(ref, abs=4 * se + 5e-4)


def test_worst_of_shark_differs_from_the_former_best_of_knock_out():
    new = PRODUCTS["shark_note"]["script"]
    old = new.replace("WOF_MAX >= M_KO_BAR", "BOF_MAX >= M_KO_BAR")
    p_new = _price(new, n=2, rho=0.5)[0]
    p_old = _price(old, n=2, rho=0.5)[0]
    # The best-of touches 130 % far more often. On those paths the former note
    # swapped a worst-of call that was mostly small for the 3 % rebate, which
    # made it worth more than the standard worst-of shark (93.13 vs 92.95 here).
    assert p_old - p_new > 0.001


def test_historical_wof_max_ignores_days_where_an_asset_does_not_quote():
    prices = {"A": [100, 120, 130, 110], "B": [100, 125, 0, 105]}
    ref = {"A": 100, "B": 100}
    wmin, bmax, wmax = _historical_running_extrema(prices, ["A", "B"], ref, 0, 3)
    # Day 2: B has no close. Its partial minimum (1.30) must not count.
    assert wmax == pytest.approx(1.20)
    assert wmin == pytest.approx(1.05) and bmax == pytest.approx(1.30)


def test_watchlist_wof_max_reads_common_dates_only():
    paths = [{1: 1.20, 2: 1.30, 3: 1.10}, {1: 1.25, 3: 1.05}]
    assert _joint_wof_max(paths) == pytest.approx(1.20)
    assert _joint_wof_max([{1: 0.9}, {1: 0.8}]) == pytest.approx(1.0)


def test_monitor_analysis_reads_wof_max_as_the_observable():
    compiled = parse_script(PRODUCTS["shark_note"]["script"])
    monitor = next(m for m in compiled.monitors if m["name"] == "M_KO_BAR")
    assert monitor["observable"] == "WOF_MAX" and monitor["direction"] == "up"
