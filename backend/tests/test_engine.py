"""Tests for the Monte Carlo engine — BS analytical validation."""
import math
import numpy as np
import pytest
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import (
    run_mc, sabr_vol, run_mark_to_future, _eval_paths, _stochastic_rate_paths,
)


def bs_call(S0, K, r, q, sigma, T):
    if T <= 0 or sigma <= 0:
        return max(0.0, S0 * math.exp(-q * T) - K * math.exp(-r * T))
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    from scipy.stats import norm
    return S0 * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


CALL_SCRIPT = """
PARAM K = 1.0 "strike"

AT MATURITY
  PAY MAX(S[1] - K, 0) "call payoff"
"""

PUT_SCRIPT = """
PARAM K = 1.0 "strike"

AT MATURITY
  PAY MAX(K - S[1], 0) "put payoff"
"""

CALL_PARAMS = [
    dict(name="S1", ticker="", ccy="EUR",
         sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
         alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0),
]
CORR = [[1.0]]


def price_call(r=0.03, T=1.0, sigma=0.20, N=40000, antithetic=True):
    params = [dict(CALL_PARAMS[0], sigma=sigma)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=r, T_max=T, N=N, model='constant',
                 seed=42, antithetic=antithetic, user_params={'K': 1.0})
    return res['price']


def test_call_atm_1y():
    """ATM call, 1Y, σ=20%, r=3% — tolerance 20bp."""
    mc = price_call(r=0.03, T=1.0, sigma=0.20)
    ref = bs_call(1.0, 1.0, 0.03, 0.0, 0.20, 1.0)
    assert abs(mc - ref) < 0.002, f"MC={mc:.4f} BS={ref:.4f}"


def test_call_otm_2y():
    """OTM call K=1.1, 2Y."""
    params = [dict(CALL_PARAMS[0], sigma=0.25)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=0.03, T_max=2.0, N=40000, model='constant',
                 seed=7, antithetic=True, user_params={'K': 1.1})
    mc = res['price']
    ref = bs_call(1.0, 1.1, 0.03, 0.0, 0.25, 2.0)
    assert abs(mc - ref) < 0.003, f"MC={mc:.4f} BS={ref:.4f}"


def test_put_call_parity():
    """Put-call parity: C - P = S·e^{-qT} - K·e^{-rT}."""
    cs_c = parse_script(CALL_SCRIPT)
    cs_p = parse_script(PUT_SCRIPT)
    kw = dict(r=0.03, T_max=1.0, N=40000, model='constant', seed=42,
              antithetic=True, user_params={'K': 1.0})
    c = run_mc(cs_c, CALL_PARAMS, CORR, **kw)['price']
    p = run_mc(cs_p, CALL_PARAMS, CORR, **kw)['price']
    theory = 1.0 - 1.0 * math.exp(-0.03)
    assert abs((c - p) - theory) < 0.002, f"C-P={c-p:.4f} theory={theory:.4f}"


def test_antithetic_reduces_variance():
    """Antithetic variates should produce tighter IC than plain MC."""
    kw = dict(r=0.03, T_max=1.0, N=10000, model='constant', seed=42)
    cs = parse_script(CALL_SCRIPT)
    res_a = run_mc(cs, CALL_PARAMS, CORR, antithetic=True, user_params={'K': 1.0}, **kw)
    res_b = run_mc(cs, CALL_PARAMS, CORR, antithetic=False, user_params={'K': 1.0}, **kw)
    w_a = res_a['ic95'][1] - res_a['ic95'][0]
    w_b = res_b['ic95'][1] - res_b['ic95'][0]
    assert w_a < w_b, f"antithetic IC width={w_a:.4f} plain IC width={w_b:.4f}"


def test_sabr_vol_atm():
    """SABR ATM with β=1 and ν=0 reduces to α."""
    vol = sabr_vol(K=100, T=1.0, F=100, alpha=0.20, beta=1.0, rho=0.0, nu=0.0)
    assert abs(vol - 0.20) < 0.001


def test_n_eff_antithetic():
    """n_eff should equal N when antithetic=True (N = number of independent pairs)."""
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=1000,
                 model='constant', seed=1, antithetic=True, user_params={'K': 1.0})
    assert res['n_eff'] == 1000
    assert res['n_paths'] == 1000


def test_n_eff_plain():
    """n_eff should equal N when antithetic=False."""
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=1000,
                 model='constant', seed=1, antithetic=False, user_params={'K': 1.0})
    assert res['n_eff'] == 1000


def test_flux_table_populated():
    """Flux table should have at least one entry after pricing."""
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000,
                 model='constant', seed=42, antithetic=True, user_params={'K': 1.0})
    assert isinstance(res['flux_table'], dict)
    assert len(res['flux_table']) >= 1


# ── Mark-to-Future (nested Monte Carlo) ─────────────────────────────

ZCB_SCRIPT = """
AT MATURITY:
  PAY 1
"""


def test_mtf_shape_and_stat_keys():
    """Result shape should match the requested n_outer/n_inner/n_dates, dates should
    be increasing, and every per-date stats dict should expose the full diagnostic set."""
    cs = parse_script(CALL_SCRIPT)
    res0 = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000, model='constant',
                  seed=1, user_params={'K': 1.0})
    p0 = res0['price'] * 100

    mtf = run_mark_to_future(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, main_price=p0,
                              model='constant', n_outer=10, n_inner=20, n_dates=4, seed=1,
                              user_params={'K': 1.0})

    assert (mtf['n_outer'], mtf['n_inner'], mtf['n_dates']) == (10, 20, 4)
    assert len(mtf['results']) == 4
    expected_keys = {'mean', 'std', 'p01', 'p05', 'p25', 'p50', 'p75', 'p95', 'p99',
                      'p_above_100', 'p_above_p0', 'e_mtm', 'e_upside'}
    dates = [row['t'] for row in mtf['results']]
    assert dates == sorted(dates)
    assert dates[-1] < 1.0   # last MTM date stays strictly before maturity
    for row in mtf['results']:
        assert len(row['pvs']) == 10
        assert set(row['stats'].keys()) == expected_keys


def test_mtf_zcb_is_deterministic():
    """A zero-coupon bond's mark-to-future value doesn't depend on the spot path at
    all, so every outer scenario must collapse to the exact same discounted value —
    a clean way to validate the date-shifting and discounting math with zero MC noise."""
    cs = parse_script(ZCB_SCRIPT)
    r, T_max = 0.04, 2.0
    res0 = run_mc(cs, CALL_PARAMS, CORR, r=r, T_max=T_max, N=2000, model='constant', seed=1)
    p0 = res0['price'] * 100

    mtf = run_mark_to_future(cs, CALL_PARAMS, CORR, r=r, T_max=T_max, main_price=p0,
                              model='constant', n_outer=5, n_inner=10, n_dates=3, seed=1)

    for row in mtf['results']:
        ts_eff = max(1, round((T_max - row['t']) * 52))
        expected = math.exp(-r * ts_eff / 52) * 100
        assert abs(row['stats']['mean'] - expected) < 1e-6
        assert row['stats']['std'] < 1e-9


def test_mtf_call_tracks_forward_martingale():
    """Risk-neutral consistency check: since the outer scenario generator and the
    inner pricer share the same GBM dynamics, E[V(t0)] must track V(0)*e^{r*t0}
    (the discounted price process is a martingale) within a few standard errors."""
    cs = parse_script(CALL_SCRIPT)
    r, T_max = 0.03, 1.0
    res0 = run_mc(cs, CALL_PARAMS, CORR, r=r, T_max=T_max, N=40000, model='constant',
                  seed=42, antithetic=True, user_params={'K': 1.0})
    p0 = res0['price'] * 100

    n_outer = 400
    mtf = run_mark_to_future(cs, CALL_PARAMS, CORR, r=r, T_max=T_max, main_price=p0,
                              model='constant', n_outer=n_outer, n_inner=300, n_dates=2,
                              seed=7, user_params={'K': 1.0})

    for row in mtf['results']:
        expected = p0 * math.exp(r * row['t'])
        se = row['stats']['std'] / math.sqrt(n_outer)
        assert abs(row['stats']['mean'] - expected) < 6 * se, (
            f"t0={row['t']}: mean={row['stats']['mean']:.3f} expected~{expected:.3f} se={se:.3f}"
        )


# ── New vocabulary: S_MIN[i] / S_MAX[i] / S_PREV[i] / REALVOL ───────

def test_s_min_s_max_bound_current_spot():
    """S_MIN[i]/S_MAX[i] include the current observation by construction, so the
    invariant S_MIN[i] <= S[i] <= S_MAX[i] must hold at every date, on every path."""
    script = """
AT 1, 2, 3:
  PAY 0
AT MATURITY:
  PAY INDIC(S_MIN[1] <= S[1]) * INDIC(S[1] <= S_MAX[1])
"""
    cs = parse_script(script)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=3.0, N=5000, model='constant',
                 seed=42, antithetic=True, user_params={})
    assert res['price'] == pytest.approx(math.exp(-0.03 * 3.0), abs=1e-6)


def test_s_prev_equals_inception_at_first_observation():
    """S_PREV[i] must read exactly 1.0 (the inception spot) at the first observation
    of any path — zero MC noise, this should hold exactly regardless of N/seed/model."""
    script = """
AT 1:
  PAY S_PREV[1]
"""
    cs = parse_script(script)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.0, T_max=1.0, N=2000, model='constant',
                 seed=7, antithetic=True, user_params={})
    assert res['price'] == pytest.approx(1.0, abs=1e-9)


def test_s_prev_telescoping_sum_matches_terminal_payoff():
    """Sum_t (S[1]_t - S_PREV[1]_t) telescopes to S[1]_T - 1. With r=0 (no
    discounting to distort the sum) and identical seed/N/model, this must match a
    script that directly pays S[1] - 1 at maturity — exactly, path by path."""
    telescoped = parse_script("""
AT 1, 2, 3:
  PAY S[1] - S_PREV[1]
""")
    direct = parse_script("""
AT MATURITY:
  PAY S[1] - 1
""")
    kw = dict(r=0.0, T_max=3.0, N=4000, model='constant', seed=99, antithetic=True, user_params={})
    res_t = run_mc(telescoped, CALL_PARAMS, CORR, **kw)
    res_d = run_mc(direct, CALL_PARAMS, CORR, **kw)
    assert res_t['price'] == pytest.approx(res_d['price'], abs=1e-9)


def test_realvol_converges_to_input_sigma():
    """REALVOL at maturity should converge (in expectation, discounted) to the
    underlying's own sigma for a constant-vol GBM with a single underlying
    (WOF == S[1] when n=1, so realized vol of WOF == realized vol of S[1])."""
    script = """
AT MATURITY:
  PAY REALVOL
"""
    cs = parse_script(script)
    r, T, sigma = 0.03, 3.0, 0.20
    res = run_mc(cs, CALL_PARAMS, CORR, r=r, T_max=T, N=20000, model='constant',
                 seed=42, antithetic=False, user_params={})
    implied_realvol = res['price'] / math.exp(-r * T)
    assert abs(implied_realvol - sigma) < 0.01


# ── Stochastic short rate (sigma_r / rho_rS) ────────────────────────

ZCB_SIMPLE = "AT MATURITY:\n  PAY 1"


def test_sigma_r_zero_matches_deterministic_rate():
    """sigma_r=0 (the default) must reproduce the exact flat-rate price — the
    stochastic-rate code path is skipped entirely (Z_r stays None)."""
    cs = parse_script(ZCB_SIMPLE)
    kw = dict(r=0.03, T_max=3.0, N=5000, model='constant', seed=42, antithetic=True)
    with_default = run_mc(cs, CALL_PARAMS, CORR, **kw)
    explicit_zero = run_mc(cs, CALL_PARAMS, CORR, sigma_r=0.0, **kw)
    assert with_default['price'] == explicit_zero['price']


def test_sigma_r_jensen_convexity_on_zcb():
    """A driftless Gaussian short rate makes discounting convex: E[exp(-∫r dt)] >=
    exp(-E[∫r dt]) (Jensen). So a ZCB's price must (a) increase monotonically with
    sigma_r, and (b) exactly match the deterministic price at sigma_r=0."""
    cs = parse_script(ZCB_SIMPLE)
    r, T = 0.03, 3.0
    kw = dict(r=r, T_max=T, N=40000, model='constant', seed=42, antithetic=True)
    deterministic = math.exp(-r * T)

    prices = []
    for sr in (0.0, 0.005, 0.01, 0.02):
        res = run_mc(cs, CALL_PARAMS, CORR, sigma_r=sr, **kw)
        prices.append(res['price'])

    assert prices[0] == pytest.approx(deterministic, abs=1e-6)
    assert all(prices[i] < prices[i + 1] for i in range(len(prices) - 1)), prices


@pytest.mark.parametrize("model", ["constant", "heston", "sabr", "localvol"])
def test_sigma_r_runs_on_every_model(model):
    """No crash and a sane (positive, finite) price for every model with both
    sigma_r and a nonzero rho_rS active."""
    params = [dict(CALL_PARAMS[0], rho_rS=0.3, skew=-0.1, curvature=0.05)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=0.03, T_max=2.0, N=2000, model=model, seed=42,
                 antithetic=True, sigma_r=0.015, user_params={'K': 1.0})
    assert math.isfinite(res['price']) and res['price'] > 0


def test_rho_rS_inert_when_sigma_r_zero():
    """rho_rS must have zero effect when sigma_r=0 — Z_r is None, so the
    rate-factor blend is skipped regardless of rho_rS."""
    cs = parse_script(CALL_SCRIPT)
    kw = dict(r=0.03, T_max=2.0, N=4000, model='constant', seed=42, antithetic=True,
              user_params={'K': 1.0})
    p_no_rho = run_mc(cs, [dict(CALL_PARAMS[0], rho_rS=0.0)], CORR, **kw)['price']
    p_with_rho = run_mc(cs, [dict(CALL_PARAMS[0], rho_rS=0.7)], CORR, **kw)['price']
    assert p_no_rho == p_with_rho


# ── Hull-White (a_r > 0) — generalizes the ABM stochastic rate ─────

def test_a_r_zero_is_default_and_matches_abm():
    """a_r=0 (the default) must take the exact same closed-form cumsum path as
    before a_r existed — explicit a_r=0.0 and omitting it must agree."""
    cs = parse_script(ZCB_SIMPLE)
    kw = dict(r=0.03, T_max=3.0, N=8000, model='constant', seed=42, antithetic=True, sigma_r=0.01)
    omitted = run_mc(cs, CALL_PARAMS, CORR, **kw)
    explicit = run_mc(cs, CALL_PARAMS, CORR, a_r=0.0, **kw)
    assert omitted['price'] == explicit['price']


def test_hull_white_jensen_convexity_on_zcb():
    """Mean-reversion doesn't remove the Jensen convexity effect: a ZCB's price
    must still increase with sigma_r and match the deterministic price at
    sigma_r=0, even with a_r > 0."""
    cs = parse_script(ZCB_SIMPLE)
    r, T = 0.03, 5.0
    kw = dict(r=r, T_max=T, N=40000, model='constant', seed=42, antithetic=True, a_r=0.3)
    deterministic = math.exp(-r * T)

    prices = []
    for sr in (0.0, 0.01, 0.02):
        res = run_mc(cs, CALL_PARAMS, CORR, sigma_r=sr, **kw)
        prices.append(res['price'])

    assert prices[0] == pytest.approx(deterministic, abs=1e-6)
    assert all(prices[i] < prices[i + 1] for i in range(len(prices) - 1)), prices


def test_hull_white_stationary_variance():
    """The OU factor x(t) = r(t) - f(0,t) has a known stationary variance
    sigma_r^2 / (2*a_r) as t grows — validates the exact one-step transition
    formula directly (not via option prices, to isolate the rate model itself)."""
    sigma_r, a_r, dt = 0.02, 0.3, 1 / 52
    ts = 500   # ~9.6y, several mean-reversion half-lives (ln2/a_r ≈ 2.3y)
    N = 20000
    rng = np.random.default_rng(1)
    Z_r = rng.standard_normal((ts, N))
    fwd = np.full(ts, 0.03)
    r_path, _ = _stochastic_rate_paths(fwd, sigma_r, a_r, math.sqrt(dt), dt, Z_r)
    x_final = r_path[-1] - fwd[-1]
    expected_var = sigma_r ** 2 / (2 * a_r)
    assert abs(x_final.var() - expected_var) / expected_var < 0.05


@pytest.mark.parametrize("model", ["constant", "heston", "sabr", "localvol"])
def test_hull_white_runs_on_every_model(model):
    params = [dict(CALL_PARAMS[0], rho_rS=0.3, skew=-0.1, curvature=0.05)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=0.03, T_max=2.0, N=2000, model=model, seed=42,
                 antithetic=True, sigma_r=0.015, a_r=0.3, user_params={'K': 1.0})
    assert math.isfinite(res['price']) and res['price'] > 0


KI_DISCOUNT_SCRIPT = """
AT MATURITY:
  SET KI = INDIC(WOF_MIN < 0.6)
  PAY (1 - KI) * 1
  PAY KI * 0.5
"""


def test_eval_paths_inherits_wof_min_init():
    """wof_min_init must combine (via min) with the path's own running minimum, so a
    knock-in barrier already breached before t0 stays breached in the residual
    pricing — this is what makes Mark-to-Future correct for continuously-monitored
    barriers. Exercises _eval_paths directly since this is the mechanism MTF relies on."""
    cs = parse_script(KI_DISCOUNT_SCRIPT)
    n, N, ts = 1, 3, 2
    dt = 1.0
    mat_events = [e for e in cs.events if e.type == 'AT_MATURITY']
    S = np.ones((ts + 1, n, N))   # flat path: never breaches 0.6 on its own

    payoffs, _ = _eval_paths(cs, S, ts, n, N, dt, 0.0, {}, {}, mat_events, {}, record=False)
    assert all(p == pytest.approx(1.0) for p in payoffs), "no breach -> KI=0 -> payoff=1.0"

    wof_min_init = np.full(N, 0.5)   # pre-t0 breach inherited from the outer scenario
    payoffs2, _ = _eval_paths(cs, S, ts, n, N, dt, 0.0, {}, {}, mat_events, {}, record=False,
                               wof_min_init=wof_min_init)
    assert all(p == pytest.approx(0.5) for p in payoffs2), "inherited breach -> KI=1 -> payoff=0.5"
