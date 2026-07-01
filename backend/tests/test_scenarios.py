"""Tests for the scenario stress grid (spot x vol shocks)."""
import pytest
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.scenarios import compute_scenario_grid

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


def test_grid_shape_and_base_price():
    grid = compute_scenario_grid(parse_script(CALL_SCRIPT), CALL_PARAMS, CORR,
                                  r=0.03, T=1.0, model='constant', seed=42,
                                  user_params={'K': 1.0},
                                  spot_shocks=[-0.1, 0.0, 0.1], vol_shocks=[0.05, 0.0, -0.05],
                                  N=2000)
    assert grid['spot_shocks'] == [-0.1, 0.0, 0.1]
    assert grid['vol_shocks'] == [0.05, 0.0, -0.05]
    assert len(grid['prices']) == 3
    assert all(len(row) == 3 for row in grid['prices'])

    direct = run_mc(parse_script(CALL_SCRIPT), CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000,
                     model='constant', seed=42, antithetic=True, user_params={'K': 1.0},
                     spot_mult=[1.0], vol_add=[0.0])
    assert grid['base_price'] == round(direct['price'], 6)
    # Center cell (spot_shock=0, vol_shock=0) must equal the base price exactly.
    assert grid['prices'][1][1] == grid['base_price']


def test_base_price_independent_of_shock_lists():
    """base_price should be computed even if 0.0 isn't in either shock list."""
    grid = compute_scenario_grid(parse_script(CALL_SCRIPT), CALL_PARAMS, CORR,
                                  r=0.03, T=1.0, model='constant', seed=42,
                                  user_params={'K': 1.0},
                                  spot_shocks=[-0.2, -0.1], vol_shocks=[0.1, 0.2], N=2000)
    direct = run_mc(parse_script(CALL_SCRIPT), CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000,
                     model='constant', seed=42, antithetic=True, user_params={'K': 1.0},
                     spot_mult=[1.0], vol_add=[0.0])
    assert grid['base_price'] == round(direct['price'], 6)


def test_call_price_increases_with_spot_and_vol_shocks():
    """Sanity check on known monotonicity: a call's price increases with spot
    (each row left-to-right) and increases with vol (rows ordered by decreasing
    vol_shock, so price should decrease top-to-bottom for a fixed column)."""
    grid = compute_scenario_grid(parse_script(CALL_SCRIPT), CALL_PARAMS, CORR,
                                  r=0.03, T=1.0, model='constant', seed=42,
                                  user_params={'K': 1.0},
                                  spot_shocks=[-0.2, -0.1, 0.0, 0.1, 0.2],
                                  vol_shocks=[0.1, 0.05, 0.0, -0.05, -0.1], N=4000)
    for row in grid['prices']:
        assert all(row[i] < row[i + 1] for i in range(len(row) - 1)), "not increasing in spot"
    for col in range(5):
        column = [row[col] for row in grid['prices']]
        assert all(column[i] > column[i + 1] for i in range(len(column) - 1)), "not decreasing in vol_shock order"


@pytest.mark.parametrize("model", ["heston", "sabr", "localvol"])
def test_grid_runs_on_every_model(model):
    """vol_add (and spot_mult) is wired into every model's simulate function —
    no crash, and the grid stays internally consistent (base price matches a
    direct run_mc call) for heston/sabr/localvol too, not just constant."""
    params = [dict(CALL_PARAMS[0], skew=-0.1, curvature=0.05)]
    grid = compute_scenario_grid(parse_script(CALL_SCRIPT), params, CORR,
                                  r=0.03, T=1.0, model=model, seed=42,
                                  user_params={'K': 1.0},
                                  spot_shocks=[-0.1, 0.0, 0.1], vol_shocks=[0.05, 0.0, -0.05],
                                  N=1500)
    direct = run_mc(parse_script(CALL_SCRIPT), params, CORR, r=0.03, T_max=1.0, N=1500,
                     model=model, seed=42, antithetic=True, user_params={'K': 1.0},
                     spot_mult=[1.0], vol_add=[0.0])
    assert grid['base_price'] == round(direct['price'], 6)
