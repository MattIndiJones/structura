"""Bump-and-reprice Greeks against closed forms, units included.

`compute_greeks` reports derivatives per unit of the bumped quantity: delta
and gamma per unit of spot (the spot is 1), vega per unit of volatility (a
100-point move), rho and credit per unit of rate or spread. A mistake of scale
is the classic one (it was found on rho), so each Greek is compared with the
analytic derivative itself, not with a stored figure.

Tolerances come from three seeds (42, 17, 93) at 40,000 paths, with margin;
the tests run on seed 42. They are instance measurements. The gamma of the
barrier is deliberately not tested against its formula: by a 3 % spot bump
on 40,000 paths it moved by +23 % on seed 93, so the figure is not reliable
at that budget.
"""
import math

import pytest
from scipy.special import ndtr
from scipy.stats import norm

from backend.app.core.payscript.engine import compute_greeks
from backend.app.core.payscript.parser import parse_script
from backend.tests.test_validation_probes import (
    CALL, DIVIDEND, DOWN_AND_IN_PUT, FORWARD, RATE, UL, _down_and_in_put)

SELECTED = ["delta", "gamma", "vega", "rho"]


def _black_scholes_greeks(strike, expiry, vol):
    root = vol * math.sqrt(expiry)
    d1 = (-math.log(strike) + (RATE - DIVIDEND + vol * vol / 2) * expiry) / root
    d2 = d1 - root
    prepaid = math.exp(-DIVIDEND * expiry)
    return {"delta": prepaid * ndtr(d1),
            "gamma": prepaid * norm.pdf(d1) / root,
            "vega": prepaid * norm.pdf(d1) * math.sqrt(expiry),
            "rho": strike * expiry * math.exp(-RATE * expiry) * ndtr(d2)}


def _greeks(script, underlyings, selected=SELECTED, T=1.0, N=40_000, **kw):
    result = compute_greeks(parse_script(script), underlyings, [[1.0]], r=RATE, T=T, N=N,
                            model="constant", seed=42, selected=selected, **kw)
    return {key: result.get(f"{key}_1", result.get(key)) for key in selected}


@pytest.fixture(scope="module", params=[1.0, 1.1], ids=["atm", "call_110"])
def call_greeks(request):
    strike = request.param
    return (_greeks(CALL, [dict(UL)], user_params={"K": strike}),
            _black_scholes_greeks(strike, 1.0, 0.20))


# Relative tolerance per Greek, from the three-seed spread on the call.
CALL_TOLERANCE = {"delta": 0.01, "gamma": 0.06, "vega": 0.025, "rho": 0.01}


@pytest.mark.parametrize("greek", SELECTED)
def test_vanilla_greeks_match_black_scholes(call_greeks, greek):
    engine, analytic = call_greeks
    assert engine[greek] == pytest.approx(analytic[greek], rel=CALL_TOLERANCE[greek]), (engine, analytic)


@pytest.fixture(scope="module")
def barrier_greeks():
    engine = _greeks(DOWN_AND_IN_PUT, [dict(UL, sigma=0.25)], user_params={},
                     barrier_monitoring="continuous")

    def closed(spot=1.0, vol=0.25, rate=RATE):
        return _down_and_in_put(spot, 1.0, 0.70, 1.0, vol, rate, DIVIDEND)

    # The closed form is bumped exactly as the engine bumps: same steps, same
    # central differences, so only the Monte Carlo error is left to compare.
    analytic = {"delta": (closed(spot=1.01) - closed(spot=0.99)) / 0.02,
                "vega": (closed(vol=0.26) - closed(vol=0.24)) / 0.02,
                "rho": (closed(rate=RATE + 0.01) - closed(rate=RATE - 0.01)) / 0.02}
    return engine, analytic


BARRIER_TOLERANCE = {"delta": 0.06, "vega": 0.03, "rho": 0.03}


@pytest.mark.parametrize("greek", sorted(BARRIER_TOLERANCE))
def test_barrier_greeks_match_the_closed_form(barrier_greeks, greek):
    engine, analytic = barrier_greeks
    assert engine[greek] == pytest.approx(analytic[greek], rel=BARRIER_TOLERANCE[greek]), (engine, analytic)


def test_barrier_greeks_have_the_desk_signs(barrier_greeks):
    # A down-and-in put gains as the spot falls and as volatility rises, and
    # loses as rates rise (lower forward, more discounting of the strike).
    engine, _ = barrier_greeks
    assert engine["delta"] < 0 < engine["vega"]
    assert engine["rho"] < 0


def test_forward_rho_is_zero_and_credit_is_minus_duration():
    """The funding rule seen through the Greeks: a rate move is compensated by
    the drift on a forward, a spread move is not. Credit is dPV/ds, so
    -T x PV for a single payment at T."""
    greeks = _greeks(FORWARD, [dict(UL)], selected=["rho", "credit"], T=2.0, N=20_000,
                     user_params={})
    assert greeks["rho"] == pytest.approx(0.0, abs=1e-3)
    prepaid = math.exp(-DIVIDEND * 2.0)
    central = (math.exp(-0.02) - math.exp(0.02)) / 0.02 * prepaid
    assert greeks["credit"] == pytest.approx(central, rel=0.003)
