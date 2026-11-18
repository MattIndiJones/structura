"""Tests for the simulation tools — PARAM solver and 2D price grid."""
import math
import pytest
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.simulation import solve_for_param, compute_price_grid

CALL_SCRIPT = """
PARAM K = 1.0 "strike"

AT MATURITY:
  PAY MAX(S[1] - K, 0) "call payoff"
"""

CALL_PARAMS = [
    dict(name="S1", ticker="", ccy="EUR",
         sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
         alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0),
]
CORR = [[1.0]]


def test_solve_for_param_converges_on_strike():
    """Solving for K such that the call price hits a target should land close to
    the value found by directly pricing at that K (cross-check against run_mc)."""
    cs = parse_script(CALL_SCRIPT)
    target = 0.08

    res = solve_for_param(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=42,
                           base_user_params={}, param_name='K', target_price=target,
                           lo=0.5, hi=1.5, N=8000, tol=1e-4, max_iter=40)

    assert res['converged']
    assert abs(res['achieved_price'] - target) < 5e-4

    # Cross-check: pricing directly at the solved K (same seed/N) should reproduce
    # the achieved price almost exactly (up to the 6-decimal rounding in the result).
    direct = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=8000, model='constant',
                     seed=42, antithetic=True, user_params={'K': res['param_value']})
    assert abs(direct['price'] - res['achieved_price']) < 2e-6


def test_solve_for_param_non_bracketing_reports_unconverged():
    """If [lo, hi] doesn't bracket the target, the solver should say so instead of
    silently returning a wrong answer."""
    cs = parse_script(CALL_SCRIPT)
    # A call's price at K in [10, 20] (deep OTM) is ~0 — can never reach target=0.5.
    res = solve_for_param(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=42,
                           base_user_params={}, param_name='K', target_price=0.5,
                           lo=10.0, hi=20.0, N=2000, tol=1e-4, max_iter=20)
    assert not res['converged']
    assert res['message'] is not None


def test_solve_for_param_exact_bound_short_circuits():
    """If price(lo) already matches the target within tol, the solver should return
    immediately at 0 iterations rather than bisecting."""
    cs = parse_script(CALL_SCRIPT)
    direct = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=8000, model='constant',
                     seed=42, antithetic=True, user_params={'K': 1.0})
    res = solve_for_param(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=42,
                           base_user_params={}, param_name='K', target_price=direct['price'],
                           lo=1.0, hi=2.0, N=8000, tol=1e-4, max_iter=40)
    assert res['converged']
    assert res['iterations'] == 0


def test_price_grid_shape_and_axes():
    cs = parse_script(CALL_SCRIPT)
    grid = compute_price_grid(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=7,
                               base_user_params={}, param_x='K', x_min=0.8, x_max=1.2, x_steps=5,
                               param_y='K', y_min=0.8, y_max=1.2, y_steps=3, N=2000)
    assert grid['x_values'] == [0.8, 0.9, 1.0, 1.1, 1.2]
    assert grid['y_values'] == [0.8, 1.0, 1.2]
    assert len(grid['prices']) == 3          # one row per y value
    assert all(len(row) == 5 for row in grid['prices'])  # one column per x value


def test_price_grid_matches_direct_pricing_at_corner():
    """Spot-check one grid cell against a direct run_mc call with the same overrides."""
    cs = parse_script(CALL_SCRIPT)
    grid = compute_price_grid(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=7,
                               base_user_params={}, param_x='K', x_min=0.8, x_max=1.2, x_steps=3,
                               param_y='K', y_min=0.8, y_max=1.2, y_steps=3, N=2000)
    # Last override wins when param_x == param_y, so the cell equals price at param_y.
    direct = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000, model='constant',
                     seed=7, antithetic=True, user_params={'K': 0.8})
    assert grid['prices'][0][0] == round(direct['price'], 6)


def test_price_grid_call_decreasing_in_strike():
    """Sanity check on a known monotonicity: a call's price strictly decreases as
    strike K increases. param_y is a name unused by CALL_SCRIPT (harmless no-op
    override, same as any extra key in user_params) — only the K axis matters here."""
    cs = parse_script(CALL_SCRIPT)
    grid = compute_price_grid(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, model='constant', seed=7,
                               base_user_params={}, param_x='K', x_min=0.7, x_max=1.3, x_steps=7,
                               param_y='UNUSED', y_min=0.0, y_max=0.0, y_steps=2, N=4000)
    row = grid['prices'][0]
    assert all(row[i] > row[i + 1] for i in range(len(row) - 1))


PDI_SCRIPT = """
PARAM KI = 70% "barriere"

AT MATURITY:
  IF WOF_MIN <= KI:
    PAY MAX(1 - S[1], 0) "pdi"
"""


@pytest.mark.parametrize("steps", [104, 208])
def test_solver_and_grid_use_the_requested_diffusion_grid(steps):
    """`steps_per_year` used to raise TypeError in solve_for_param, so every
    Product Optimizer candidate failed. The grid must also REACH the engine: a
    barrier observed on a finer grid is hit more often, so the price moves."""
    cs = parse_script(PDI_SCRIPT)
    kw = dict(r=0.03, T=1.0, model='constant', seed=42, base_user_params={})
    coarse = compute_price_grid(cs, CALL_PARAMS, CORR, **kw, param_x='KI', x_min=0.7, x_max=0.7, x_steps=1,
                                param_y='KI', y_min=0.7, y_max=0.7, y_steps=1, N=4000)
    fine = compute_price_grid(cs, CALL_PARAMS, CORR, **kw, param_x='KI', x_min=0.7, x_max=0.7, x_steps=1,
                              param_y='KI', y_min=0.7, y_max=0.7, y_steps=1, N=4000, steps_per_year=steps)
    assert fine['prices'][0][0] > coarse['prices'][0][0]

    res = solve_for_param(cs, CALL_PARAMS, CORR, **kw, param_name='KI', target_price=fine['prices'][0][0],
                          lo=0.5, hi=0.9, N=4000, tol=1e-5, max_iter=40, steps_per_year=steps)
    direct = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=4000, model='constant', seed=42,
                    antithetic=True, user_params={'KI': res['param_value']}, steps_per_year=steps)
    assert abs(direct['price'] - res['achieved_price']) < 2e-6
