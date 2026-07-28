"""Tests for the Monte Carlo engine — BS analytical validation."""
import math
import numpy as np
import pytest
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import (
    run_mc, sabr_vol, run_mark_to_future, _eval_paths, _stochastic_rate_paths,
    _heston_qe_scalar, _heston_qe_vectorized, _dupire_vol, run_payoff_profile,
    _simulate_heston, _simulate_sabr, cholesky, _blend_rate_factor,
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


def test_param_default_used_when_user_params_omits_it():
    """A PARAM not present in user_params must fall back to its script
    default, not silently price as 0 — regression for a bug where
    _eval_paths/_eval_paths_detailed seeded ctx["memo"] from user_params
    alone, so any PARAM the caller didn't explicitly pass (e.g. a fixed
    coupon leg) resolved to the SET-variable fallback of 0."""
    script = """
PARAM COUPON = 10%

AT MATURITY
  PAY COUPON
"""
    cs = parse_script(script)
    res = run_mc(cs, CALL_PARAMS, CORR, r=0.03, T_max=1.0, N=2000,
                 model='constant', seed=42, antithetic=True, user_params={})
    ref = 0.10 * math.exp(-0.03)
    assert abs(res['price'] - ref) < 1e-6, f"MC={res['price']:.6f} expected={ref:.6f}"


def test_runtime_error_in_script_raises_instead_of_silently_pricing_zero():
    """A script referencing S[3] with only 2 underlyings configured hits an
    IndexError while evaluating the payoff — regression for a bug where
    _eval_paths swallowed any Exception during event evaluation, so a script
    bug (bad index, typo-triggered TypeError, etc.) silently priced that leg
    as 0 with status "ok" and no error reported."""
    cs = parse_script("AT MATURITY\n  PAY S[3] - 1\n")
    two_underlyings = [CALL_PARAMS[0], CALL_PARAMS[0]]
    corr = [[1.0, 0.0], [0.0, 1.0]]
    with pytest.raises(ValueError):
        run_mc(cs, two_underlyings, corr, r=0.03, T_max=1.0, N=100, model='constant', user_params={})


def test_bare_basket_keyword_prices_without_nameerror():
    """Regression: bare BASKET() (equal-weighted, as opposed to the weighted
    BASKET(w1, w2, ...) form) used to raise 'name sum is not defined' at
    EVAL time — _transpile_expr emits it as raw inline Python
    ("(sum(_c['spots'])/max(1,len(_c['spots'])))", see parser.py), but the
    sandboxed exec namespace (_SAFE_MATH) didn't list sum/len among its
    whitelisted names (__builtins__ is deliberately {} there, no fallback).
    parse_script() never executes the body, only compiles it, so this was
    invisible until a script using bare BASKET() actually priced — found
    while writing the cross-gamma test below, on a 2-underlying basket call."""
    cs = parse_script("PARAM K = 1.0\n\nAT MATURITY\n  PAY MAX(0, BASKET() - K)\n")
    two = [CALL_PARAMS[0], CALL_PARAMS[0]]
    corr = [[1.0, 0.3], [0.3, 1.0]]
    res = run_mc(cs, two, corr, r=0.03, T_max=1.0, N=2000, model='constant',
                 seed=42, user_params={'K': 1.0})
    assert res['price'] > 0


def test_bare_n_keyword_prices_without_nameerror():
    """Same root cause as the BASKET() regression above — the N keyword
    (number of underlyings) transpiles to the equally bare 'len(_c["spots"])'
    (see the BV table in _transpile_expr), broken by the same missing
    sum/len whitelist entry."""
    cs = parse_script("AT MATURITY\n  PAY N\n")
    two = [CALL_PARAMS[0], CALL_PARAMS[0]]
    corr = [[1.0, 0.0], [0.0, 1.0]]
    res = run_mc(cs, two, corr, r=0.03, T_max=1.0, N=100, model='constant', user_params={})
    ref = 2 * math.exp(-0.03)   # PAY N=2 at every path, discounted
    assert abs(res['price'] - ref) < 1e-5


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


def test_sabr_mc_matches_hagan_formula():
    """Cross-check _simulate_sabr's actual MC output against Hagan's closed-form
    SABR formula (sabr_vol, validated on its own in test_sabr_vol_atm above) —
    closes a coverage gap flagged by a code audit: the MC simulator previously
    had no correctness check against any reference, only a smoke test."""
    from scipy.optimize import brentq
    r, q, T = 0.03, 0.0, 1.0
    alpha, beta, rho, nu = 0.20, 0.50, -0.30, 0.40
    forward = math.exp(r * T)   # S0 = 1, driftless-forward reference for Hagan's formula

    params = [dict(CALL_PARAMS[0], alpha=alpha, beta=beta, rho=rho, nu=nu, q=q)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=r, T_max=T, N=20000, model='sabr',
                 seed=7, antithetic=True, user_params={'K': forward})
    mc_price = res['price']

    implied = brentq(lambda s: bs_call(1.0, forward, r, q, s, T) - mc_price, 0.01, 2.0)
    expected = sabr_vol(K=forward, T=T, F=forward, alpha=alpha, beta=beta, rho=rho, nu=nu)
    assert abs(implied - expected) < 0.02, f"MC implied vol={implied:.4f} Hagan={expected:.4f}"


def test_local_vol_collapses_to_gbm_when_flat():
    """skew=curvature=0 (the parametric smile's flat case) must reduce Dupire
    local vol to plain constant vol — cross-checks _simulate_lv against the
    same Black-Scholes reference GBM already uses, closing the same kind of
    coverage gap as the SABR test above."""
    params = [dict(CALL_PARAMS[0], sigma=0.20, skew=0.0, curvature=0.0)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=0.03, T_max=1.0, N=40000, model='localvol',
                 seed=42, antithetic=True, user_params={'K': 1.0})
    ref = bs_call(1.0, 1.0, 0.03, 0.0, 0.20, 1.0)
    assert abs(res['price'] - ref) < 0.005, f"MC={res['price']:.4f} BS={ref:.4f}"


def test_heston_spot_process_is_martingale():
    """E[S_T] under the risk-neutral measure must equal the prepaid forward
    S0*exp(-q*T) — here q=0 so the expected price of "PAY S[1]" is exactly
    S0=1.0, independent of r (it cancels: E[S_T]=S0*exp(rT), discount
    exp(-rT)). This is the empirical check for a code-audit finding that
    _simulate_heston's spot update uses an averaged-variance approximation
    rather than Andersen's full QE-M martingale correction — if that
    approximation introduced a material bias, it would show up here."""
    script = "AT MATURITY\n  PAY S[1]"
    cs = parse_script(script)
    params = [dict(CALL_PARAMS[0], q=0.0)]
    res = run_mc(cs, params, CORR, r=0.03, T_max=1.0, N=20000, model='heston',
                 seed=42, antithetic=True, user_params={})
    assert abs(res['price'] - 1.0) < 0.01, f"E[S_T] price={res['price']:.5f}, expected≈1.0"


# ── Local-Stochastic Vol (LSV) ──────────────────────────────────────

def test_heston_qe_vectorized_matches_scalar():
    """_heston_qe_vectorized (used by both _simulate_heston and _simulate_lsv,
    which need the whole cross-section of paths at once) must be
    algorithmically identical to _heston_qe_scalar (the original per-path
    formula, kept as the reference) — same draws in, same variance out,
    elementwise, for both the quadratic and the exponential QE regime."""
    rng = np.random.default_rng(7)
    N = 5000
    kappa, theta, xi, dt = 2.0, 0.04, 0.6, 1 / 52  # high xi to hit both psi regimes
    V = rng.uniform(0.001, 0.5, N)
    Zv = rng.standard_normal(N)

    vec = _heston_qe_vectorized(V, kappa, theta, xi, dt, Zv)
    scalar = np.array([_heston_qe_scalar(float(v), kappa, theta, xi, dt, float(z))
                        for v, z in zip(V, Zv)])
    assert np.allclose(vec, scalar, atol=1e-9), \
        f"max abs diff={np.max(np.abs(vec - scalar)):.2e}"


def test_lsv_marginal_matches_local_vol_target():
    """The defining property of LSV: its leverage function recalibrates the
    stochastic-vol dynamics every step so the MARGINAL distribution of the
    spot matches the Dupire local vol target exactly (same lv_grids
    _simulate_lv itself calibrates to) — even though the PATH dynamics
    differ (that's the whole point, see test below). Prices a few strikes,
    inverts implied vol via Black-Scholes, and compares to _dupire_vol at
    the same strikes."""
    from scipy.optimize import brentq
    r, q, T = 0.03, 0.0, 1.0
    sigma0, skew, curvature = 0.20, -0.05, 0.02
    forward = math.exp(r * T)

    params = [dict(CALL_PARAMS[0], sigma=sigma0, skew=skew, curvature=curvature, q=q)]

    for K in (0.85, 1.0, 1.15):
        script = f"PARAM K = {K}\nAT MATURITY\n  PAY MAX(S[1] - K, 0)"
        cs = parse_script(script)
        res = run_mc(cs, params, CORR, r=r, T_max=T, N=20000, model='lsv',
                     seed=11, antithetic=True, user_params={'K': K})
        implied = brentq(lambda s: bs_call(1.0, K, r, q, s, T) - res['price'], 0.01, 2.0)
        target = _dupire_vol(K, T, sigma0, skew, curvature, r, q)
        assert abs(implied - target) < 0.03, \
            f"K={K}: MC implied vol={implied:.4f} local vol target={target:.4f}"


def test_lsv_differs_from_pure_local_vol_on_autocall():
    """LSV must NOT silently degenerate into pure local vol on a genuinely
    path-dependent payoff. A payoff observed ONLY at maturity (e.g. a plain
    KI check) is NOT a good test for this: LSV and local vol are calibrated
    to the exact same terminal marginal (see test_lsv_marginal_matches_
    local_vol_target above), so they necessarily agree on anything that only
    depends on S_T. The forward-skew dynamics LSV and local vol genuinely
    disagree on only show up across MULTIPLE observation dates — an
    autocall with early-exercise dates plus a maturity KI check, same
    structure already confirmed by hand to diverge materially between these
    two models (~0.92 vs ~0.97) during manual testing."""
    script = """PARAM COUPON = 8%
PARAM AC_BAR = 100%
PARAM KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""
    cs = parse_script(script)
    # Fairly aggressive vol-of-vol/correlation (xi, rho_h, slow mean-reversion
    # kappa) — makes the forward-skew divergence from local vol clear and
    # stable across seeds (checked manually at ~0.008-0.009 across 4 seeds),
    # comfortably above both MC noise and the assertion threshold below.
    params = [dict(CALL_PARAMS[0], sigma=0.20, skew=-0.08, curvature=0.03,
                    xi=0.6, rho_h=-0.85, kappa=1.0)]
    kw = dict(r=0.03, T_max=3.0, N=20000, seed=5, antithetic=True, user_params={})
    price_lv  = run_mc(cs, params, CORR, model='localvol', **kw)['price']
    price_lsv = run_mc(cs, params, CORR, model='lsv', **kw)['price']
    assert abs(price_lsv - price_lv) > 0.005, \
        f"localvol={price_lv:.4f} lsv={price_lsv:.4f} — too close, LSV may be degenerating to local vol"


# ── Payoff profile (deterministic sweep) ────────────────────────────

def test_payoff_profile_pins_level_no_drift_spike():
    """Regression for a bug where the payoff-profile sweep simulated a
    near-zero-vol GBM path (which still carried the real (r-q) drift) and
    rescaled it, instead of genuinely pinning the underlying at each swept
    level. On a memory-coupon autocall (PAY CALL * COUPON * INDEX, paying
    every accrued coupon on the date it triggers) that let a sub-barrier
    level quietly drift up and autocall late, producing a payoff spike
    (124%/116% at 98%/99%) instead of the flat 100% a level that never
    reaches the barrier should show. r-q is deliberately large here (3% vs
    0%) so any residual drift would be obvious."""
    script = """PARAM COUPON = 8%
PARAM AC_BAR = 100%
PARAM KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""
    cs = parse_script(script)
    uls = [dict(CALL_PARAMS[0], q=0.0)]
    res = run_payoff_profile(cs, uls, CORR, r=0.03, T_max=3.0,
                              user_params={"COUPON": 0.08, "AC_BAR": 1.0, "KI_BAR": 0.6})
    by_level = dict(zip(res["levels"], res["payoffs"]))
    for lv in (90.0, 95.0, 98.0, 99.0):
        assert by_level[lv] == pytest.approx(100.0), \
            f"level={lv}%: payoff={by_level[lv]}% — expected flat 100% (no drift-induced late autocall)"
    assert by_level[100.0] == pytest.approx(108.0)


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


# ── Audit 2026-07: greeks correctness, KI classification, corr validation ──

from backend.app.core.payscript.engine import compute_greeks, run_mc_proba


def bs_greeks_call(S0, K, r, q, sigma, T):
    """Analytic BS delta/gamma/theta (theta per calendar day) for the call."""
    from scipy.stats import norm
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    delta = math.exp(-q * T) * norm.cdf(d1)
    gamma = math.exp(-q * T) * norm.pdf(d1) / (S0 * sigma * math.sqrt(T))
    theta_year = (-S0 * math.exp(-q * T) * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                  - r * K * math.exp(-r * T) * norm.cdf(d2)
                  + q * S0 * math.exp(-q * T) * norm.cdf(d1))
    return delta, gamma, theta_year / 365.0


def test_greeks_delta_gamma_theta_match_bs():
    """CRN bump-and-reprice greeks vs Black-Scholes analytics on the ATM call.

    Regression for two bugs: (1) theta used dt_add=+1/365, which never crossed
    the weekly round(T*SY) grid boundary — the 'bumped' run was bit-for-bit
    identical to the base, so theta was pure sampling noise between two path
    counts; (2) gamma's central term reused the main run's full-N price — a
    different estimator whose noise doesn't cancel and gets divided by 9e-4."""
    cs = parse_script(CALL_SCRIPT)
    greeks = compute_greeks(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, N=40000,
                            model='constant', seed=42, user_params={'K': 1.0},
                            selected=["delta", "gamma", "theta"])
    d_bs, g_bs, th_bs = bs_greeks_call(1.0, 1.0, 0.03, 0.0, 0.20, 1.0)

    assert abs(greeks["delta_1"] - d_bs) < 0.04, f"delta MC={greeks['delta_1']} BS={d_bs:.4f}"
    assert abs(greeks["gamma_1"] - g_bs) < 0.6, f"gamma MC={greeks['gamma_1']} BS={g_bs:.4f}"
    # Theta: weekly-grid aging scaled to per-day; BS daily theta ≈ -1.5e-4.
    assert greeks["theta"] is not None and greeks["theta"] < 0, \
        f"theta must be negative for a long ATM call, got {greeks['theta']}"
    assert abs(greeks["theta"] - th_bs) < 1.5e-4, \
        f"theta MC={greeks['theta']} BS={th_bs:.6f}"


def test_greeks_accept_yield_curve():
    """A flat curve at the same level as r must reproduce the flat-r greeks —
    regression for compute_greeks silently ignoring the curve (base price on
    the curve, bumped prices on flat r: the gap blew up gamma/theta)."""
    cs = parse_script(CALL_SCRIPT)
    flat = compute_greeks(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, N=8000,
                          model='constant', seed=42, user_params={'K': 1.0},
                          selected=["delta", "gamma"])
    curve = compute_greeks(cs, CALL_PARAMS, CORR, r=0.03, T=1.0, N=8000,
                           model='constant', seed=42, user_params={'K': 1.0},
                           selected=["delta", "gamma"],
                           yield_curve=[[1.0, 0.03], [3.0, 0.03]])
    assert abs(flat["delta_1"] - curve["delta_1"]) < 1e-9
    assert abs(flat["gamma_1"] - curve["gamma_1"]) < 1e-9


def test_corr_greek_positive_for_basket_call():
    """Cross-gamma (correlation sensitivity) sign check — none of the
    existing greeks tests exercise it (all single-underlying), and it's
    about to be turned on by default for every multi-underlying deal (see
    api/deals.py:deal_greeks), so its sign/direction needs an independent
    check before that, not just "doesn't crash".

    Standard basket-option fact, not script-specific: for an equally-
    weighted basket average with fixed per-leg vols, Var(basket) =
    (σ1² + σ2² + 2·ρ·σ1·σ2) / 4 — strictly increasing in ρ. More basket
    variance means more optionality for a call, so a basket call's price
    (and compute_greeks' one-sided corr_1_2 finite difference) must be
    POSITIVE in ρ. (The opposite holds for a spread option — this is a
    basket/average payoff specifically.)"""
    script = """
PARAM K = 1.0

AT MATURITY
  PAY MAX(0, (S[1] + S[2]) / 2 - K)
"""
    cs = parse_script(script)
    two = [CALL_PARAMS[0], CALL_PARAMS[0]]
    corr = [[1.0, 0.3], [0.3, 1.0]]
    greeks = compute_greeks(cs, two, corr, r=0.03, T=1.0, N=40000, model='constant',
                            seed=42, user_params={'K': 1.0}, selected=["corr"])
    assert greeks["corr_1_2"] > 0, \
        f"basket call must gain value as correlation rises, got {greeks['corr_1_2']}"


def test_proba_ki_classification_is_discount_independent():
    """A product that always redeems par at maturity must classify 100% of
    paths as 'normal' — regression for _eval_paths_detailed classifying on the
    DISCOUNTED total (par at 3y, r=5% -> PV 0.86 < 0.999 -> mislabeled 'ki')."""
    cs = parse_script("AT MATURITY\n  PAY 1.0 \"par redemption\"\n")
    res = run_mc_proba(cs, CALL_PARAMS, CORR, r=0.05, T_max=3.0, N=2000,
                       model='constant', seed=42, user_params={})
    assert res["ki_count"] == 0, f"{res['ki_count']} paths mislabeled KI"
    assert res["normal_count"] == res["total"]


def test_corr_matrix_validation_raises():
    """Out-of-range or asymmetric correlation inputs must raise, not silently
    reprice on a repaired matrix with an inflated diagonal."""
    cs = parse_script(CALL_SCRIPT)
    two = [CALL_PARAMS[0], CALL_PARAMS[0]]
    kw = dict(r=0.03, T_max=1.0, N=500, model='constant', seed=42,
              antithetic=True, user_params={'K': 1.0})
    with pytest.raises(ValueError):
        run_mc(cs, two, [[1.0, 1.5], [1.5, 1.0]], **kw)
    with pytest.raises(ValueError):
        run_mc(cs, two, [[1.0, 0.2], [0.5, 1.0]], **kw)
    with pytest.raises(ValueError):
        run_mc(cs, two, [[0.9, 0.2], [0.2, 0.9]], **kw)
    # A valid (near-degenerate) matrix must still price.
    res = run_mc(cs, two, [[1.0, 0.999], [0.999, 1.0]], **kw)
    assert math.isfinite(res['price'])


def test_heston_collapses_to_bs_when_xi_tiny():
    """xi -> 0 with v0 = theta pins the variance at v0: Heston must reproduce
    Black-Scholes(sqrt(v0)). Guards the variance-process wiring (kappa/theta/
    QE branches) beyond what the martingale test can see."""
    params = [dict(CALL_PARAMS[0], v0=0.04, theta=0.04, kappa=2.0, xi=1e-4, rho_h=-0.7)]
    cs = parse_script(CALL_SCRIPT)
    res = run_mc(cs, params, CORR, r=0.03, T_max=1.0, N=20000, model='heston',
                 seed=42, antithetic=True, user_params={'K': 1.0})
    ref = bs_call(1.0, 1.0, 0.03, 0.0, 0.20, 1.0)
    assert abs(res['price'] - ref) < 0.003, f"Heston xi~0={res['price']:.4f} BS={ref:.4f}"


def test_heston_skew_direction_follows_rho():
    """With negative spot-vol correlation an OTM put must be worth MORE than
    with positive correlation (all else equal) — the skew direction. Catches a
    sign error in the rho_h wiring that leaves the martingale test green."""
    cs = parse_script(PUT_SCRIPT)
    kw = dict(r=0.03, T_max=1.0, N=20000, model='heston', seed=42,
              antithetic=True, user_params={'K': 0.8})
    p_neg = run_mc(cs, [dict(CALL_PARAMS[0], rho_h=-0.7, xi=0.6)], CORR, **kw)['price']
    p_pos = run_mc(cs, [dict(CALL_PARAMS[0], rho_h=+0.7, xi=0.6)], CORR, **kw)['price']
    assert p_neg > p_pos, f"OTM put: rho=-0.7 -> {p_neg:.5f} must exceed rho=+0.7 -> {p_pos:.5f}"


# ── Continuous barrier monitoring (Brownian bridge) ─────────────────

HIT_PROBA_SCRIPT = """
PARAM B = 0.8

AT MATURITY
  PAY INDIC(WOF_MIN < B) "hit indicator"
"""


def test_continuous_barrier_matches_first_passage_analytic():
    """GBM first-passage probability P(min S < B) has a closed form; the
    Brownian-bridge extremum law is EXACT under GBM, so the continuous-mode MC
    must reproduce it — while weekly monitoring must undershoot it (extrema
    sampled at 52 points miss intra-week breaches). r=0 so the discounted
    indicator IS the probability."""
    cs = parse_script(HIT_PROBA_SCRIPT)
    kw = dict(r=0.0, T_max=1.0, N=20000, model='constant', seed=42,
              antithetic=True, user_params={'B': 0.8})
    p_weekly = run_mc(cs, CALL_PARAMS, CORR, barrier_monitoring="weekly", **kw)['price']
    p_cont = run_mc(cs, CALL_PARAMS, CORR, barrier_monitoring="continuous", **kw)['price']

    # P(min <= b) = N((b-vT)/(s*sqrt(T))) + exp(2vb/s^2)*N((b+vT)/(s*sqrt(T)))
    from scipy.stats import norm
    sigma, T, B = 0.20, 1.0, 0.8
    v = 0.0 - 0.5 * sigma ** 2
    b = math.log(B)
    p_ref = (norm.cdf((b - v * T) / (sigma * math.sqrt(T)))
             + math.exp(2 * v * b / sigma ** 2) * norm.cdf((b + v * T) / (sigma * math.sqrt(T))))

    assert abs(p_cont - p_ref) < 0.012, f"continu MC={p_cont:.4f} analytique={p_ref:.4f}"
    assert p_weekly < p_cont - 0.01, \
        f"hebdo ({p_weekly:.4f}) doit sous-estimer le continu ({p_cont:.4f})"


@pytest.mark.parametrize("model", ["constant", "heston", "sabr", "localvol", "lsv"])
def test_continuous_barrier_monitoring_runs_on_every_model(model):
    """Continuous mode must run on every model (vol_out wired everywhere) and
    never DECREASE the hit probability vs weekly (up to MC noise)."""
    params = [dict(CALL_PARAMS[0], skew=-0.05, curvature=0.02)]
    cs = parse_script(HIT_PROBA_SCRIPT)
    kw = dict(r=0.0, T_max=1.0, N=4000, model=model, seed=42,
              antithetic=True, user_params={'B': 0.8})
    p_weekly = run_mc(cs, params, CORR, barrier_monitoring="weekly", **kw)['price']
    p_cont = run_mc(cs, params, CORR, barrier_monitoring="continuous", **kw)['price']
    assert math.isfinite(p_cont) and 0.0 <= p_cont <= 1.0
    assert p_cont >= p_weekly - 0.02, f"{model}: continu {p_cont:.4f} < hebdo {p_weekly:.4f}"


def test_barrier_monitoring_invalid_value_raises():
    cs = parse_script(HIT_PROBA_SCRIPT)
    with pytest.raises(ValueError, match="barrier_monitoring"):
        run_mc(cs, CALL_PARAMS, CORR, r=0.0, T_max=1.0, N=500, model='constant',
               seed=42, antithetic=True, user_params={'B': 0.8},
               barrier_monitoring="daily")


# ── Audit 2026-07 (2nd pass): Heston/SABR vectorization ─────────────
#
# _simulate_heston and _simulate_sabr were per-path Python loops (N inner
# iterations of pure-Python scalar math) — 30-40s at N=20000, vs milliseconds
# for GBM/LV/LSV. Rewritten step-major/vectorized (same pattern as
# _simulate_lv/_simulate_lsv). The two reference loops below are literal
# copies of the ORIGINAL per-path formulas (pre-refactor), kept only as a
# correctness oracle: same random draws in, same spot paths out.

def _heston_reference_loop(ts, n, N, dt, sq_dt, underlyings, r_eff, L, Z, Zv):
    S = np.ones((ts + 1, n, N), dtype=np.float64)
    for path in range(N):
        V = np.array([u.get("v0", 0.04) for u in underlyings], dtype=np.float64)
        for step in range(ts):
            cZ = L @ Z[step, :, path]
            for i, u in enumerate(underlyings):
                rh, kap, th, xi = u.get("rho_h", -0.70), u.get("kappa", 2.0), u.get("theta", 0.04), u.get("xi", 0.35)
                rhop = math.sqrt(max(0.0, 1.0 - rh * rh))
                z_perp_var = Zv[step, i, path]
                zv = rh * cZ[i] + rhop * z_perp_var
                V_old = float(V[i])
                V_next = _heston_qe_scalar(V_old, kap, th, xi, dt, zv)
                V_bar = (V_old + V_next) / 2
                V[i] = V_next
                sv = math.sqrt(max(0.0, V_bar))
                drift = r_eff + u.get("ccyh", 0.0) - u.get("q", 0.02) - 0.5 * V_bar
                z_S_perp = rhop * cZ[i] - rh * z_perp_var
                corr_term = rh / xi * (V_next - V_old - kap * (th - V_bar) * dt)
                S[step + 1, i, path] = S[step, i, path] * math.exp(
                    drift * dt + corr_term + rhop * sv * sq_dt * z_S_perp)
    return S


def test_heston_vectorized_matches_reference_loop():
    """The vectorized _simulate_heston must reproduce the original per-path
    scalar loop (same math, elementwise over paths instead of a Python loop)
    to float precision — guards the performance refactor against silently
    changing prices. 2 correlated underlyings to exercise the cholesky blend."""
    n, N, ts = 2, 300, 20
    dt, sq_dt = 1/52, math.sqrt(1/52)
    rng = np.random.default_rng(3)
    Z = rng.standard_normal((ts, n, N))
    Zv = rng.standard_normal((ts, n, N))
    underlyings = [
        dict(sigma=0.20, q=0.02, v0=0.04, kappa=2.0, theta=0.04, xi=0.5, rho_h=-0.7, ccyh=0.0),
        dict(sigma=0.25, q=0.01, v0=0.05, kappa=1.5, theta=0.05, xi=0.4, rho_h=-0.5, ccyh=0.0),
    ]
    L = cholesky([[1.0, 0.3], [0.3, 1.0]], n)

    S_ref = _heston_reference_loop(ts, n, N, dt, sq_dt, underlyings, 0.03, L, Z, Zv)
    S_vec = _simulate_heston(ts, n, N, dt, sq_dt, underlyings, 0.03, L, Z, Zv)
    assert np.allclose(S_ref, S_vec, atol=1e-8, rtol=1e-8), \
        f"max abs diff={np.max(np.abs(S_ref - S_vec)):.2e}"


def _sabr_reference_loop(ts, n, N, dt, sq_dt, underlyings, r_eff, L, Z, Za):
    S = np.ones((ts + 1, n, N), dtype=np.float64)
    for path in range(N):
        alpha = np.array([u.get("alpha", 0.20) for u in underlyings], dtype=np.float64)
        for step in range(ts):
            cZ = L @ Z[step, :, path]
            za_raw = Za[step, :, path]
            for i, u in enumerate(underlyings):
                rho_s, nu, beta = u.get("rho", -0.30), u.get("nu", 0.40), u.get("beta", 0.50)
                z_S = cZ[i]
                z_a = rho_s * z_S + math.sqrt(max(0.0, 1.0 - rho_s ** 2)) * za_raw[i]
                alpha_old = alpha[i]
                alpha_new = alpha_old * math.exp(nu * sq_dt * z_a - 0.5 * nu ** 2 * dt)
                S_c = max(S[step, i, path], 1e-8)
                sig = alpha_old if abs(beta - 1.0) < 1e-4 else alpha_old * (S_c ** (beta - 1.0))
                sig = max(0.001, min(sig, 3.0))
                drift = r_eff + u.get("ccyh", 0.0) - u.get("q", 0.02) - 0.5 * sig ** 2
                S[step + 1, i, path] = S_c * math.exp(drift * dt + sig * sq_dt * z_S)
                alpha[i] = alpha_new
    return S


def test_sabr_vectorized_matches_reference_loop():
    """Same guard as above for _simulate_sabr, including the alpha_old (not
    alpha_bar) martingale-preserving choice — a regression here would mean
    the vectorized CEV vol picked up the wrong (correlated) alpha."""
    n, N, ts = 2, 300, 20
    dt, sq_dt = 1/52, math.sqrt(1/52)
    rng = np.random.default_rng(5)
    Z = rng.standard_normal((ts, n, N))
    Za = rng.standard_normal((ts, n, N))
    underlyings = [
        dict(sigma=0.20, q=0.02, alpha=0.20, beta=0.6, rho=-0.3, nu=0.4, ccyh=0.0),
        dict(sigma=0.25, q=0.01, alpha=0.25, beta=0.4, rho=-0.5, nu=0.6, ccyh=0.0),
    ]
    L = cholesky([[1.0, -0.2], [-0.2, 1.0]], n)

    S_ref = _sabr_reference_loop(ts, n, N, dt, sq_dt, underlyings, 0.03, L, Z, Za)
    S_vec = _simulate_sabr(ts, n, N, dt, sq_dt, underlyings, 0.03, L, Z, Za)
    assert np.allclose(S_ref, S_vec, atol=1e-8, rtol=1e-8), \
        f"max abs diff={np.max(np.abs(S_ref - S_vec)):.2e}"


# ── Audit 2026-07 (4th pass): backtest scans daily closes between AT dates ──

from backend.app.core.payscript.engine import eval_script_on_history, _historical_running_extrema


def test_historical_running_extrema_finds_mid_window_dip():
    """A one-day dip strictly between lo_hi and hi_hi must be picked up, not
    just the window's endpoint — this is the primitive the backtest fix below
    relies on."""
    prices = {"TK1": [100.0] * 10}
    prices["TK1"][5] = 40.0   # dip on day 5, flat elsewhere
    ref = {"TK1": 100.0}
    wmin, bmax = _historical_running_extrema(prices, ["TK1"], ref, lo_hi=0, hi_hi=9)
    assert wmin == pytest.approx(0.40)
    assert bmax == pytest.approx(1.0)


def test_historical_running_extrema_empty_window_is_neutral():
    """No days in (lo_hi, hi_hi] -> (inf, -inf), a no-op for the caller's
    running min()/max() — must never falsely narrow or widen the extrema."""
    prices = {"TK1": [100.0] * 5}
    ref = {"TK1": 100.0}
    wmin, bmax = _historical_running_extrema(prices, ["TK1"], ref, lo_hi=3, hi_hi=3)
    assert wmin == math.inf and bmax == -math.inf


BACKTEST_KI_SCRIPT = """
PARAM B = 0.7

AT 0.5:
  SET DUMMY = 1

AT MATURITY:
  PAY INDIC(WOF_MIN < B) "hit"
"""


def test_backtest_replay_captures_intra_period_barrier_breach():
    """A barrier breached on a day strictly between two AT dates, then
    recovered, must still register — regression for eval_script_on_history
    only sampling WOF on the script's own observation dates (here 0.5y and
    AT MATURITY at 1y), silently skipping every daily close in between even
    though the daily history is already loaded in prices_by_ticker.

    Price path: flat at the reference level (spot=1.0) on every day EXCEPT
    day 100 (roughly 5 months in, strictly between the two AT dates), which
    dips to 50% before recovering the next day. Neither AT date's own spot
    (both exactly 1.0) shows the breach — only scanning the days in between
    does. Barrier B=70% -> WOF_MIN must dip to 0.50 < 0.70 -> hit=1.0."""
    n_days = 260
    px = [100.0] * n_days
    px[100] = 50.0
    prices_by_ticker = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]   # placeholder labels, content unused

    cs = parse_script(BACKTEST_KI_SCRIPT)
    res = eval_script_on_history(cs, dates, prices_by_ticker, start_idx=0, T_max=1.0,
                                 user_params={'B': 0.7}, tickers=["TK1"], r=0.03)
    assert res is not None
    hit_cfs = [cf['cf'] for cf in res['cash_flows']]
    assert hit_cfs == [1.0], f"expected the KI indicator to fire (1.0), got {hit_cfs}"


def test_backtest_replay_no_breach_when_price_stays_above_barrier():
    """Sanity counterpart: if the price never dips below the barrier (not even
    intra-period), the indicator must correctly stay at 0 — guards against a
    trivial always-fire bug in the fix above."""
    n_days = 260
    px = [100.0] * n_days
    px[100] = 80.0   # dips, but stays above the 70% barrier
    prices_by_ticker = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]

    cs = parse_script(BACKTEST_KI_SCRIPT)
    res = eval_script_on_history(cs, dates, prices_by_ticker, start_idx=0, T_max=1.0,
                                 user_params={'B': 0.7}, tickers=["TK1"], r=0.03)
    assert res is not None
    hit_cfs = [cf['cf'] for cf in res['cash_flows']]
    assert hit_cfs == [0.0], f"expected no breach (0.0), got {hit_cfs}"


BACKTEST_CAP_SCRIPT = """
AT 0.5:
  SET DUMMY = 1

AT MATURITY:
  PAY BOF_MAX "running max"
"""


def test_backtest_bof_max_accumulates_across_observations():
    """bof_max must be a genuine RUNNING max since inception, like wof_min —
    regression for a second bug found alongside the intra-period one: the old
    code recomputed bof_max fresh from just the CURRENT step's spot every
    time, discarding whatever high was reached on a previous observation."""
    n_days = 260
    px = [100.0] * n_days
    px[50] = 150.0    # a spike well before the first AT date (day 126 = 0.5y)
    prices_by_ticker = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]

    cs = parse_script(BACKTEST_CAP_SCRIPT)
    res = eval_script_on_history(cs, dates, prices_by_ticker, start_idx=0, T_max=1.0,
                                 user_params={}, tickers=["TK1"], r=0.03)
    assert res is not None
    cf = res['cash_flows'][0]['cf']
    assert cf == pytest.approx(1.5), \
        f"expected the running max (1.50, from day 50's spike) to survive to maturity, got {cf}"


# ── MtM résiduel — héritage d'état (spot_mult, index_offset, memo_init,
#    wof_min_init) + shift des events + ancre resolve_constats ─────────

from datetime import date as _date, timedelta as _timedelta
from backend.app.core.payscript.engine import _shift_events_for_mtf
from backend.app.core.payscript.parser import CompiledScript, resolve_constats

RESIDUAL_AUTOCALL = """
PARAM AC_BAR = 100%  "barriere de rappel"
PARAM CPN = 5%  "coupon"

AT 1, 2, 3
  IF WOF >= AC_BAR
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
"""

RESIDUAL_DEGRESSIVE = """
PARAM CPN = 5%  "coupon"
PARAM() M_AC_BAR = 110%  "barriere degressive"

AT 1, 2, 3
  IF WOF >= M_AC_BAR
    PAY 1 + CPN "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
"""

RESIDUAL_MEMORY = """
PARAM CPN = 5%  "coupon"
PARAM AC_BAR = 100%  "barriere de coupon"

SET MISSED = 0

AT 1, 2, 3
  IF WOF >= AC_BAR
    PAY CPN * (1 + MISSED) "coupons rattrapes"
    SET MISSED = 0
  IF WOF < AC_BAR
    SET MISSED = MISSED + 1

AT MATURITY
  PAY 1 "capital"
"""

RESIDUAL_KI = """
PARAM KI_BAR = 60%  "barriere KI"

AT MATURITY
  SET KI = INDIC(WOF_MIN < KI_BAR)
  PAY (1 - KI) * 1 + KI * WOF "remboursement"
"""


def _residual_script(cs, t0):
    """Shift a compiled script to a valuation date t0 — same construction as
    api/deals.py:deal_mtm."""
    return CompiledScript(events=_shift_events_for_mtf(cs.events, t0),
                          init_fn=cs.init_fn, params=cs.params,
                          constats=cs.constats, has_stop=cs.has_stop)


def _run_residual(script_text, t0, spot, sigma=0.05, r=0.03, T_res=0.5, **kw):
    cs = parse_script(script_text)
    rs = _residual_script(cs, t0)
    params = [dict(CALL_PARAMS[0], sigma=sigma, q=0.0)]
    return run_mc(rs, params, CORR, r=r, T_max=T_res, N=20000, model='constant',
                  seed=42, antithetic=True, spot_mult=[spot], **kw)['price']


def test_residual_autocall_certain_recall_and_index():
    """3Y annual autocall vu à 2.5 ans, spot à 130% du strike, σ=5% : le rappel
    à l'obs résiduelle (t=0.5) est quasi certain. Avec index_offset=2 l'INDEX
    vaut 3 → coupon 15% : MtM ≈ df(0.5)·1.15. Sans héritage d'index le produit
    croit en être à sa 1ère obs et paie 5%."""
    r = 0.03
    with_idx = _run_residual(RESIDUAL_AUTOCALL, 2.5, 1.3, index_offset=2)
    assert abs(with_idx - math.exp(-r * 0.5) * 1.15) < 0.005, f"{with_idx:.4f}"
    without = _run_residual(RESIDUAL_AUTOCALL, 2.5, 1.3)
    assert abs(without - math.exp(-r * 0.5) * 1.05) < 0.005, f"{without:.4f}"


def test_residual_degressive_param_reads_right_row():
    """Barrière dégressive [110%, 100%, 90%] : à la 3ème obs (index_offset=2),
    WOF=95% doit rappeler (barrière 90%) ; sans l'offset la ligne lue est la
    1ère (110%) et le produit court jusqu'à maturité."""
    r = 0.03
    up = {"M_AC_BAR": [1.10, 1.00, 0.90]}
    called = _run_residual(RESIDUAL_DEGRESSIVE, 2.5, 0.95, sigma=0.01,
                           index_offset=2, user_params=up)
    assert abs(called - math.exp(-r * 0.5) * 1.05) < 0.005, f"{called:.4f}"
    not_called = _run_residual(RESIDUAL_DEGRESSIVE, 2.5, 0.95, sigma=0.01,
                               user_params=up)
    assert abs(not_called - math.exp(-r * 0.5) * 1.00) < 0.005, f"{not_called:.4f}"


def test_residual_memory_coupons_inherited():
    """Phoenix mémoire : 2 coupons manqués hérités via memo_init → l'obs
    résiduelle (spot 120%, σ=1%) paie CPN·(1+2)=15% puis capital à maturité.
    Sans héritage, seul le coupon courant (5%) est payé."""
    r = 0.03
    df = math.exp(-r * 0.5)
    with_mem = _run_residual(RESIDUAL_MEMORY, 2.5, 1.2, sigma=0.01,
                             index_offset=2, memo_init={"MISSED": 2})
    assert abs(with_mem - df * 1.15) < 0.005, f"{with_mem:.4f}"
    without = _run_residual(RESIDUAL_MEMORY, 2.5, 1.2, sigma=0.01, index_offset=2)
    assert abs(without - df * 1.05) < 0.005, f"{without:.4f}"


def test_residual_ki_already_touched():
    """KI continu déjà touché (wof_min hérité 50% < barrière 60%) : le put est
    vivant sur 100% des chemins → MtM ≈ E[WOF] actualisé ≈ spot (q=0). Sans
    héritage, σ=1% depuis 80% ne touche jamais 60% → remboursement au pair."""
    r = 0.03
    touched = _run_residual(RESIDUAL_KI, 2.5, 0.8, sigma=0.01, wof_min_init=0.5)
    assert abs(touched - 0.8) < 0.005, f"{touched:.4f}"
    untouched = _run_residual(RESIDUAL_KI, 2.5, 0.8, sigma=0.01)
    assert abs(untouched - math.exp(-r * 0.5)) < 0.005, f"{untouched:.4f}"


def test_shift_events_drops_past_keeps_maturity():
    cs = parse_script(RESIDUAL_AUTOCALL)
    shifted = _shift_events_for_mtf(cs.events, 2.5)
    at = [e for e in shifted if e.type == "AT"]
    mat = [e for e in shifted if e.type == "AT_MATURITY"]
    assert len(at) == 1 and at[0].dates == [0.5]
    assert len(mat) == 1


def test_resolve_constats_anchor():
    """Un CONSTAT à date fixe rejoué sur un deal booké il y a un an : ancré à
    la value_date la date tombe à ~2 ans, ancré à aujourd'hui (défaut,
    pré-trade) à ~1 an."""
    cs = parse_script("CONSTAT Obs\nAT Obs:\n  PAY 1\nAT MATURITY:\n  PAY 0")
    value_d = _date.today() - _timedelta(days=365)
    obs_iso = (value_d + _timedelta(days=730)).isoformat()
    ev_default = next(e for e in resolve_constats(cs, {"OBS": obs_iso}).events
                      if e.type == "AT")
    ev_anchored = next(e for e in resolve_constats(cs, {"OBS": obs_iso},
                                                   anchor=value_d).events
                       if e.type == "AT")
    assert abs(ev_default.dates[0] - 1.0) < 0.01
    assert abs(ev_anchored.dates[0] - 2.0) < 0.01


# ── MtM résiduel — héritage d'état complet (s_min/s_max/s_prev/realvol/
#    strike_fix) : combinaison passé réel / futur simulé ────────────────

from backend.app.core.payscript.engine import _compute_strike_fix

RESIDUAL_S_MIN_KI = """
PARAM KI_BAR = 60%  "barriere KI per-asset"

AT MATURITY
  SET KI = INDIC(S_MIN[1] < KI_BAR)
  PAY (1 - KI) * 1 + KI * WOF "remboursement"
"""

RESIDUAL_REALVOL = """
AT MATURITY
  PAY REALVOL "vol realisee"
"""

RESIDUAL_ASIAN_STRIKE = """
AT MATURITY
  SET STRIKE = FIX_AVG
  PAY WOF / STRIKE "perf vs strike moyen"
"""

RESIDUAL_MOMENTUM = """
PARAM CPN = 5%  "coupon momentum"

AT 1, 2, 3
  IF S[1] >= S_PREV[1]
    PAY CPN "coupon"

AT MATURITY
  PAY 1 "capital"
"""


def test_residual_s_min_barrier_already_breached():
    """KI per-asset déjà franchi (s_min hérité 50% < barrière 60%) : le put est
    vivant sur 100% des chemins → MtM ≈ spot actualisé au forward ≈ spot.
    Sans héritage, σ=1% depuis 80% ne franchit jamais 60% → pair."""
    r = 0.03
    touched = _run_residual(RESIDUAL_S_MIN_KI, 2.5, 0.8, sigma=0.01,
                            s_min_init=[0.5])
    assert abs(touched - 0.8) < 0.005, f"{touched:.4f}"
    untouched = _run_residual(RESIDUAL_S_MIN_KI, 2.5, 0.8, sigma=0.01)
    assert abs(untouched - math.exp(-r * 0.5)) < 0.005, f"{untouched:.4f}"


def test_residual_realvol_inherited():
    """REALVOL hérité par sommation des variations quadratiques : 20% réalisés
    sur 2 ans (sumsq = 0.04·2) + 6 mois simulés à σ=1% →
    vol combinée ≈ sqrt(0.08/2.5) ≈ 17.9%. Sans héritage ≈ 1%."""
    r = 0.03
    df = math.exp(-r * 0.5)
    inherited = _run_residual(RESIDUAL_REALVOL, 2.5, 1.0, sigma=0.01,
                              realvol_state_init={"sumsq": 0.08, "t": 2.0},
                              wof0_init=1.0)
    assert abs(inherited - df * math.sqrt(0.08 / 2.5)) < 0.005, f"{inherited:.4f}"
    without = _run_residual(RESIDUAL_REALVOL, 2.5, 1.0, sigma=0.01)
    assert without < 0.02, f"{without:.4f}"


def test_residual_wof0_seed_kills_phantom_return():
    """Paths seedés à 130% du strike : sans wof0_init la série WOF démarre à
    1.0 et le premier return hebdo log(1.3) — tout le drift passé — gonfle
    REALVOL comme un rendement fictif. Avec wof0_init=1.3, REALVOL ≈ σ."""
    seeded = _run_residual(RESIDUAL_REALVOL, 2.5, 1.3, sigma=0.01, wof0_init=1.3)
    assert seeded < 0.03, f"{seeded:.4f}"
    phantom = _run_residual(RESIDUAL_REALVOL, 2.5, 1.3, sigma=0.01)
    assert phantom > 0.2, f"{phantom:.4f}"


def test_residual_strike_fix_past_window():
    """Fenêtre STRIKE_FIX entièrement réalisée (fix_state hérité, moyenne 0.8,
    aucune date résiduelle) : FIX_AVG constant à 0.8 → payoff WOF/0.8 vaut
    spot/0.8 = 1.25 actualisé au forward (martingale, q=0)."""
    past = _run_residual(RESIDUAL_ASIAN_STRIKE, 2.5, 1.0, sigma=0.01,
                         fix_state_init={"n": 2, "sum": 1.6,
                                         "min": 0.7, "max": 0.9})
    assert abs(past - 1.0 / 0.8) < 0.01, f"{past:.4f}"


def test_compute_strike_fix_combines_past_and_future():
    """Fenêtre à cheval : 2 fixings réalisés (somme 1.6) + 1 futur simulé à
    0.9 → moyenne pondérée par comptes (1.6+0.9)/3, min/max croisés. Sans état
    hérité la réduction reste celle de la fenêtre future seule."""
    cs = parse_script(RESIDUAL_ASIAN_STRIKE)
    rs = CompiledScript(events=cs.events, init_fn=cs.init_fn, params=cs.params,
                        constats=cs.constats, strike_fix_dates=[4 / 52])
    WOF = np.full((26, 8), 0.9)
    f_min, f_max, f_avg = _compute_strike_fix(
        rs, WOF, fix_state_init={"n": 2, "sum": 1.6, "min": 0.7, "max": 0.95})
    assert np.allclose(f_min, 0.7) and np.allclose(f_max, 0.95)
    assert np.allclose(f_avg, (1.6 + 0.9) / 3)
    f_min2, _f_max2, f_avg2 = _compute_strike_fix(rs, WOF)
    assert np.allclose(f_min2, 0.9) and np.allclose(f_avg2, 0.9)


def test_residual_s_prev_inherited():
    """Coupon momentum (S ≥ S_PREV) : le dernier fixing passé était à 140%,
    spot actuel 130% → pas de coupon à l'obs résiduelle. Sans héritage,
    S_PREV retombe à 1.0 et le coupon est payé à tort."""
    r = 0.03
    df = math.exp(-r * 0.5)
    flat = _run_residual(RESIDUAL_MOMENTUM, 2.5, 1.3, sigma=0.01,
                         s_prev_init=[1.4])
    assert abs(flat - df * 1.00) < 0.005, f"{flat:.4f}"
    up = _run_residual(RESIDUAL_MOMENTUM, 2.5, 1.3, sigma=0.01)
    assert abs(up - df * 1.05) < 0.005, f"{up:.4f}"


def test_history_replay_extended_state():
    """État étendu du replay sur série synthétique : 260 jours plats à 100,
    dip à 40 au jour 100, dernier close à 120 — extrema per-asset, s_prev à
    l'obs 0.5y, wof_last et variation quadratique vérifiés à la main."""
    n_days = 260
    px = [100.0] * n_days
    px[100] = 40.0
    px[-1] = 120.0
    prices = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]
    cs = parse_script(BACKTEST_KI_SCRIPT)
    res = eval_script_on_history(cs, dates, prices, start_idx=0, T_max=2.0,
                                 user_params={'B': 0.7}, tickers=["TK1"], r=0.03)
    assert res is not None and not res["early_recall"]
    st = res["state"]
    assert st["s_min"][0] == pytest.approx(0.4)
    assert st["s_max"][0] == pytest.approx(1.2)
    assert st["s_prev"][0] == pytest.approx(1.0)   # spots à l'obs 0.5y (jour 126)
    assert st["wof_last"] == pytest.approx(1.2)
    exp_sumsq = math.log(0.4)**2 + math.log(2.5)**2 + math.log(1.2)**2
    assert st["realvol_state"]["sumsq"] == pytest.approx(exp_sumsq)
    assert st["realvol_state"]["t"] == pytest.approx(259 / 252)
    assert st["fix_state"] is None


def test_history_replay_fix_window_realized():
    """Fenêtre STRIKE_FIX partiellement passée : les 2 dates dans l'historique
    (closes 90 et 110) alimentent fix_state, la date future est ignorée."""
    n_days = 260
    px = [100.0] * n_days
    px[10] = 90.0
    px[20] = 110.0
    prices = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]
    cs = parse_script(BACKTEST_KI_SCRIPT)
    cs.strike_fix_dates = [10 / 252, 20 / 252, 1.5]   # 2 passées, 1 future
    res = eval_script_on_history(cs, dates, prices, start_idx=0, T_max=2.0,
                                 user_params={'B': 0.7}, tickers=["TK1"], r=0.03)
    fs = res["state"]["fix_state"]
    assert fs is not None and fs["n"] == 2
    assert fs["sum"] == pytest.approx(2.0)
    assert fs["min"] == pytest.approx(0.9)
    assert fs["max"] == pytest.approx(1.1)


S_MIN_PAST_SCRIPT = """
AT 0.5:
  SET LOW = S_MIN[1]

AT MATURITY:
  PAY LOW "plus bas"
"""


def test_history_replay_script_using_s_min_no_crash():
    """Régression : un script lisant S_MIN[1] à une observation PASSÉE faisait
    crasher le replay (clé absente du ctx). Il doit maintenant lire le vrai
    plus-bas quotidien réalisé (dip à 40% avant l'obs 0.5y)."""
    n_days = 260
    px = [100.0] * n_days
    px[100] = 40.0
    prices = {"TK1": px}
    dates = [f"2020-01-{i:04d}" for i in range(n_days)]
    cs = parse_script(S_MIN_PAST_SCRIPT)
    res = eval_script_on_history(cs, dates, prices, start_idx=0, T_max=2.0,
                                 user_params={}, tickers=["TK1"], r=0.03)
    assert res is not None
    assert res["state"]["memo"]["LOW"] == pytest.approx(0.4)
