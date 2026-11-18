"""Smile models against references written outside the engine.

What each model must do by construction, checked on the production
simulators:

- SABR: its own law. Hagan's expansion where it is reliable (short expiry, no
  drift), and the independent spot PDE of 07/10/2026 elsewhere.
- Local Vol: the vanillas of the surface it was built from. The target is an
  arbitrage-free SSVI, priced here from its own total-variance formula, not
  through the application's surface object.
- LSV: the same vanillas whatever the variance dynamics, and Local Vol again
  when the variance stops moving.

The tolerance is three standard errors plus a stated fixed allowance. The
grids are fine enough for the discretisation error to sit inside that
allowance; at 52 steps a year it does not (see the validation note of
18/11/2026). These are instance measurements on these parameters and seeds.
"""
import math

import numpy as np
import pytest
from scipy.optimize import brentq

from backend.app.core.compute_budget import ensure_budget, estimate_mc
from backend.app.core.payscript import engine
from backend.app.core.volatility_surface import SSVISurface
from backend.scripts.vol_model_references import black_scholes

RATE, DIVIDEND = 0.03, 0.02
BP = 1e-4


def _pairs(simulate, ts, n, seed, *, variance=False):
    """Antithetic legs of a simulator, with the Brownian draws it needs."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((ts, 1, n))
    zv = rng.standard_normal(z.shape) if variance else None
    legs = []
    for sign in (1.0, -1.0):
        legs.append(simulate(sign * z, sign * zv if variance else None))
    return legs


def _option(legs, index, strike, expiry, rate, kind):
    a, b = legs[0][index, 0], legs[1][index, 0]
    payoff = (lambda x: np.maximum(x - strike, 0)) if kind == "call" else (lambda x: np.maximum(strike - x, 0))
    paired = math.exp(-rate * expiry) * (payoff(a) + payoff(b)) / 2
    return float(paired.mean()), float(paired.std(ddof=1) / math.sqrt(paired.size))


# ── SABR ────────────────────────────────────────────────────────────────────

def _hagan_lognormal(forward, strike, expiry, alpha, beta, rho, nu):
    """Hagan et al. (2002), lognormal implied volatility, written from the paper."""
    one_b = 1.0 - beta
    if abs(forward - strike) < 1e-12:
        fb = forward ** one_b
        return alpha / fb * (1 + (one_b ** 2 / 24 * alpha ** 2 / fb ** 2
                                  + rho * beta * nu * alpha / (4 * fb)
                                  + (2 - 3 * rho ** 2) / 24 * nu ** 2) * expiry)
    log_fk = math.log(forward / strike)
    fk_b = (forward * strike) ** (one_b / 2)
    z = nu / alpha * fk_b * log_fk
    x = math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    denominator = fk_b * (1 + one_b ** 2 / 24 * log_fk ** 2 + one_b ** 4 / 1920 * log_fk ** 4)
    correction = 1 + (one_b ** 2 / 24 * alpha ** 2 / fk_b ** 2
                      + rho * beta * nu * alpha / (4 * fk_b)
                      + (2 - 3 * rho ** 2) / 24 * nu ** 2) * expiry
    return alpha / denominator * z / x * correction


SABR = dict(alpha=0.2, beta=0.5, rho=-0.6, nu=0.5)


@pytest.mark.parametrize("strike", [0.9, 1.0, 1.1])
def test_sabr_short_expiry_smile_matches_hagan(strike):
    """No drift (r = q), so the simulated spot is the SABR forward Hagan
    describes; three months, where the expansion's error is far below the
    Monte Carlo noise. 416 steps a year: at 52, the simulated skew is
    flattened by 0.1 to 0.2 vol point at these strikes."""
    rate = dividend = 0.03
    expiry, steps, n = 0.25, 104, 100_000
    dt = expiry / steps
    params = [dict(SABR, q=dividend)]
    legs = _pairs(lambda z, zv: engine._simulate_sabr(steps, 1, n, dt, math.sqrt(dt), params, rate,
                                                      np.eye(1), z, zv)[[-1]],
                  steps, n, 42, variance=True)
    price, se = _option(legs, 0, strike, expiry, rate, "call")

    def call_at(vol):
        return black_scholes(strike, expiry, vol, rate, dividend)[0]

    implied = brentq(lambda v: call_at(v) - price, 1e-4, 3.0)
    vega = (call_at(implied + 1e-4) - call_at(implied - 1e-4)) / 2e-4
    hagan = _hagan_lognormal(1.0, strike, expiry, **SABR)
    assert abs(implied - hagan) < 3 * se / vega + 0.0005, (implied, hagan, se / vega)


# Fine mesh of the independent spot PDE, 07/10/2026 (backend/scripts/
# vol_model_references.sabr_spot_pde; output/vol-model-validation-20261007).
# Same convention as the simulator: alpha on the unit spot, r 3 %, q 2 %.
# The last figure is the gap between the fine and the coarse meshes, in bp:
# what the reference itself is not sure of.
SABR_PDE_CALLS = [
    (1.0, 0.8, 0.22397727613836022, 0.469),
    (1.0, 1.0, 0.08330108931831376, 1.295),
    (1.0, 1.2, 0.01491141982687975, 0.170),
    (4.0, 1.0, 0.16412406846563266, 0.899),
    (4.0, 1.2, 0.07716059429362938, 0.569),
]


@pytest.fixture(scope="module")
def sabr_paths():
    steps_per_year, n = 104, 40_000
    ts = 4 * steps_per_year
    dt = 1.0 / steps_per_year
    ensure_budget(estimate_mc(operation="sabr_validation", maturity_years=4.0,
                              underlyings=1, paths=n, model="sabr"))
    params = [dict(SABR, q=DIVIDEND)]
    return steps_per_year, _pairs(
        lambda z, zv: engine._simulate_sabr(ts, 1, n, dt, math.sqrt(dt), params, RATE,
                                            np.eye(1), z, zv)[[steps_per_year, ts]],
        ts, n, 42, variance=True)


@pytest.mark.parametrize("expiry,strike,reference,mesh_bp", SABR_PDE_CALLS)
def test_sabr_calls_match_the_independent_pde(sabr_paths, expiry, strike, reference, mesh_bp):
    _spy, legs = sabr_paths
    price, se = _option(legs, 0 if expiry == 1.0 else 1, strike, expiry, RATE, "call")
    assert abs(price - reference) < 3 * se + (1.0 + mesh_bp) * BP, (price, reference, se)


# ── Local Vol and LSV on an arbitrage-free SSVI ────────────────────────────

SSVI = dict(atm_vol=0.20, rho=-0.75, eta=0.85, shape_scale=0.04)


def _ssvi_vol(strike, expiry):
    """Gatheral-Jacquier SSVI, total variance in log-forward moneyness."""
    k = math.log(strike) - (RATE - DIVIDEND) * expiry
    theta = SSVI["atm_vol"] ** 2 * expiry
    phi = SSVI["eta"] / math.sqrt(SSVI["shape_scale"] + theta)
    rho = SSVI["rho"]
    w = theta / 2 * (1 + rho * phi * k + math.sqrt((phi * k + rho) ** 2 + 1 - rho ** 2))
    return math.sqrt(w / expiry)


def _ssvi_otm(strike, expiry):
    """Reference price of the out-of-the-money option, and its kind."""
    kind = "put" if strike < math.exp((RATE - DIVIDEND) * expiry) else "call"
    call, put, _ = black_scholes(strike, expiry, _ssvi_vol(strike, expiry), RATE, DIVIDEND)
    return (put if kind == "put" else call), kind


def test_the_target_surface_is_the_one_the_application_builds():
    surface = SSVISurface(**SSVI)
    for expiry in (0.5, 1.0, 2.0):
        for strike in (0.6, 0.8, 1.0, 1.2, 1.5):
            mine = black_scholes(strike, expiry, _ssvi_vol(strike, expiry), RATE, DIVIDEND)[0]
            assert surface.vanillas([strike], expiry, RATE, DIVIDEND)[0][0] == pytest.approx(mine, abs=1e-12)


LSV_VARIANCE = dict(v0=0.04, theta=0.04, kappa=2.0, xi=0.5, rho_h=-0.8)
SSVI_POINTS = [(t, k) for t in (1.0, 2.0) for k in (0.8, 1.0, 1.2)]
STEPS_PER_YEAR = 208


def _ssvi_simulation(model, n, seed=42, variance=LSV_VARIANCE):
    ts = 2 * STEPS_PER_YEAR
    dt = 1.0 / STEPS_PER_YEAR
    ensure_budget(estimate_mc(operation="smile_validation", maturity_years=2.0,
                              underlyings=1, paths=n, model=model))
    params = [dict(sigma=0.2, q=DIVIDEND, skew=0.0, curvature=0.0, **variance)]
    # Local volatility at mid-step, as the common-surface study does.
    grid = SSVISurface(**SSVI).local_grid((np.arange(ts) + 0.5) * dt, RATE, DIVIDEND)
    grid = ([grid[0]], *grid[1:])

    def simulate(z, zv):
        args = (ts, 1, n, dt, math.sqrt(dt), params, RATE, np.eye(1), z)
        paths = (engine._simulate_lv(*args, *grid) if model == "localvol"
                 else engine._simulate_lsv(*args, zv, *grid))
        return paths[[STEPS_PER_YEAR, ts]]

    return _pairs(simulate, ts, n, seed, variance=model == "lsv")


@pytest.fixture(scope="module")
def local_vol_paths():
    return _ssvi_simulation("localvol", 100_000)


@pytest.fixture(scope="module")
def lsv_paths():
    return _ssvi_simulation("lsv", 50_000)


@pytest.mark.parametrize("expiry,strike", SSVI_POINTS)
def test_local_vol_reprices_the_ssvi_vanillas(local_vol_paths, expiry, strike):
    reference, kind = _ssvi_otm(strike, expiry)
    price, se = _option(local_vol_paths, 0 if expiry == 1.0 else 1, strike, expiry, RATE, kind)
    assert abs(price - reference) < 3 * se + 1 * BP, (kind, price, reference, se)


@pytest.mark.parametrize("expiry,strike", SSVI_POINTS)
def test_lsv_reprices_the_ssvi_vanillas_despite_stochastic_variance(lsv_paths, expiry, strike):
    """The leverage function exists for this: whatever the variance process
    (here xi 50 %, rho -0.8, unrelated to the surface), the marginals are the
    target's. Interacting particles make the standard error slightly
    optimistic; the 07/10 note checked three seeds for that reason."""
    reference, kind = _ssvi_otm(strike, expiry)
    price, se = _option(lsv_paths, 0 if expiry == 1.0 else 1, strike, expiry, RATE, kind)
    assert abs(price - reference) < 3 * se + 1.5 * BP, (kind, price, reference, se)


def test_lsv_without_vol_of_vol_is_local_vol():
    """Variance frozen at v0: the leverage is sigma_LV / sqrt(v0) and LSV must
    rebuild the Local Vol paths from the same Brownian draws."""
    ts, n = 52, 4_000
    dt = 1.0 / ts
    frozen = dict(LSV_VARIANCE, xi=1e-12)
    params = [dict(sigma=0.2, q=DIVIDEND, skew=0.0, curvature=0.0, **frozen)]
    grid = SSVISurface(**SSVI).local_grid((np.arange(ts) + 0.5) * dt, RATE, DIVIDEND)
    grid = ([grid[0]], *grid[1:])
    rng = np.random.default_rng(5)
    z = rng.standard_normal((ts, 1, n))
    zv = rng.standard_normal(z.shape)
    args = (ts, 1, n, dt, math.sqrt(dt), params, RATE, np.eye(1), z)
    local = engine._simulate_lv(*args, *grid)
    lsv = engine._simulate_lsv(*args, zv, *grid)
    assert float(np.max(np.abs(lsv / local - 1))) < 1e-5
