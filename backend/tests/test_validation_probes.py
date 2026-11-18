"""Engine validation against references written outside the engine.

The audit of 16/11/2026 checked the Monte Carlo engine with independent
probes (A to F). They were one-off scripts; these tests keep them. Every
reference below is a closed form or a quadrature from
`backend/scripts/vol_model_references.py` or this file, and none of them
borrows anything from the engine.

The check is statistical: the engine price must fall within three standard
errors of the reference, plus a small fixed allowance for the
time-discretisation error, stated per test. They are instance measurements on
these parameters and this seed, not a general tolerance.
"""
import functools
import math

import pytest
from scipy.special import ndtr

from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script
from backend.scripts.vol_model_references import black_scholes, heston_vanillas

RATE, DIVIDEND = 0.03, 0.02
BP = 1e-4

UL = dict(name="S1", ticker="", ccy="EUR", sigma=0.20, q=DIVIDEND,
          v0=0.04, kappa=2.0, theta=0.04, xi=0.5, rho_h=-0.8,
          alpha=0.20, beta=0.5, rho=-0.6, nu=0.5, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)

CALL = """
PARAM K = 1.0 "strike"

AT MATURITY
  PAY MAX(S[1] - K, 0) "call"
"""

DOWN_AND_IN_PUT = """
PARAM K = 100% "strike"
PARAM B = 70%  "barriere"

AT MATURITY
  SET HIT = INDIC(S_MIN[1] < B)
  PAY HIT * MAX(K - S[1], 0) "put down-and-in"
"""

FORWARD = """
AT MATURITY
  PAY S[1] "forward"
"""


def _run(script, *, underlyings=None, corr=None, T=1.0, N=100_000, seed=42, **kw):
    result = run_mc(parse_script(script), underlyings or [dict(UL)], corr or [[1.0]],
                    r=RATE, T_max=T, N=N, seed=seed, antithetic=True, **kw)
    low, high = result["ic95"]
    return result["price"], (high - low) / (2 * 1.96)


# ── A. European call under GBM against Black-Scholes ───────────────────────

@pytest.mark.parametrize("strike", [0.8, 1.0, 1.2])
def test_a_gbm_call_matches_black_scholes(strike):
    price, se = _run(CALL, model="constant", user_params={"K": strike})
    reference = black_scholes(strike, 1.0, 0.20, RATE, DIVIDEND)[0]
    # GBM is simulated exactly on its grid: no discretisation allowance.
    assert abs(price - reference) < 3 * se + 0.1 * BP, (price, reference, se)


# ── B. Reproducibility ─────────────────────────────────────────────────────

def test_b_same_seed_same_price_other_seed_other_draw():
    first = _run(CALL, model="constant", N=20_000, user_params={"K": 1.0})[0]
    again = _run(CALL, model="constant", N=20_000, user_params={"K": 1.0})[0]
    other = _run(CALL, model="constant", N=20_000, seed=7, user_params={"K": 1.0})[0]
    assert first == again
    assert first != other


# ── C. Heston (QE scheme, weekly grid) against Fourier inversion ───────────

@pytest.mark.parametrize("strike", [0.9, 1.0, 1.1])
def test_c_heston_call_matches_fourier(strike):
    price, se = _run(CALL, model="heston", user_params={"K": strike})
    reference = heston_vanillas(strike, 1.0, UL, RATE, DIVIDEND)[0]
    # QE on 52 steps a year: the audit measured about +1 bp of bias.
    assert abs(price - reference) < 3 * se + 2 * BP, (price, reference, se)


# ── D. Down-and-in put against the continuous closed form ──────────────────

def _down_and_in_put(spot, strike, barrier, expiry, vol, rate, dividend):
    """Reiner-Rubinstein, barrier below the strike, no rebate (Haug, B - C + D)."""
    root = vol * math.sqrt(expiry)
    mu = (rate - dividend - vol * vol / 2) / (vol * vol)
    lam = (1 + mu) * root
    x2 = math.log(spot / barrier) / root + lam
    y1 = math.log(barrier * barrier / (spot * strike)) / root + lam
    y2 = math.log(barrier / spot) / root + lam
    fwd_df, df = math.exp(-dividend * expiry), math.exp(-rate * expiry)
    ratio = barrier / spot
    b = -spot * fwd_df * ndtr(-x2) + strike * df * ndtr(-x2 + root)
    c = (-spot * fwd_df * ratio ** (2 * (mu + 1)) * ndtr(y1)
         + strike * df * ratio ** (2 * mu) * ndtr(y1 - root))
    d = (-spot * fwd_df * ratio ** (2 * (mu + 1)) * ndtr(y2)
         + strike * df * ratio ** (2 * mu) * ndtr(y2 - root))
    return b - c + d


def test_d_reference_formula_is_itself_consistent():
    # A barrier far below the spot: the knock-in becomes impossible.
    assert _down_and_in_put(1.0, 1.0, 1e-6, 1.0, 0.25, RATE, DIVIDEND) == pytest.approx(0.0, abs=1e-12)
    # A barrier at the spot: knocked in from the start, the vanilla put.
    vanilla = black_scholes(1.0, 1.0, 0.25, RATE, DIVIDEND)[1]
    assert _down_and_in_put(1.0, 1.0, 1.0 - 1e-9, 1.0, 0.25, RATE, DIVIDEND) == pytest.approx(vanilla, abs=1e-7)


@functools.lru_cache(maxsize=None)
def _barrier_run(monitoring):
    ul = dict(UL, sigma=0.25)
    return _run(DOWN_AND_IN_PUT, underlyings=[ul], model="constant",
                barrier_monitoring=monitoring)


def test_d_continuous_monitoring_matches_the_closed_form():
    price, se = _barrier_run("continuous")
    reference = _down_and_in_put(1.0, 1.0, 0.70, 1.0, 0.25, RATE, DIVIDEND)
    # Brownian bridge between grid dates: exact for a GBM in continuous time.
    assert abs(price - reference) < 3 * se + 1 * BP, (price, reference, se)


def test_d_weekly_monitoring_matches_its_discrete_correction():
    """Broadie-Glasserman-Kou: a barrier watched every dt behaves like a
    continuous one moved away from the spot by exp(-0.5826 sigma sqrt(dt))."""
    price, se = _barrier_run("weekly")
    shifted = 0.70 * math.exp(-0.5826 * 0.25 * math.sqrt(1 / 52))
    reference = _down_and_in_put(1.0, 1.0, shifted, 1.0, 0.25, RATE, DIVIDEND)
    # The correction is itself an approximation, of the order of a few bp here
    # (the audit measured +5 bp). The tolerance holds the engine to it, not to
    # the exact discrete price.
    assert abs(price - reference) < 3 * se + 8 * BP, (price, reference, se)
    # And the ordering every desk relies on: watching less often knocks in less.
    continuous = _barrier_run("continuous")[0]
    assert price < continuous


# ── E. Funding discounts only; the rate also moves the forward ─────────────

def test_e_funding_spread_discounts_without_touching_the_forward():
    base = _run(FORWARD, model="constant", N=20_000, T=2.0)[0]
    spread = _run(FORWARD, model="constant", N=20_000, T=2.0, funding_spread=0.01)[0]
    rate_up = _run(FORWARD, model="constant", N=20_000, T=2.0, dr=0.01)[0]
    # Same paths: the spread only scales the discount factor.
    assert spread / base == pytest.approx(math.exp(-0.01 * 2.0), abs=2e-6)
    # The rate moves drift and discount together: the forward is unchanged,
    # E[exp(-rT) S_T] = exp(-qT) whatever r.
    forward = math.exp(-DIVIDEND * 2.0)
    assert base == pytest.approx(forward, abs=5 * BP)
    assert rate_up == pytest.approx(forward, abs=5 * BP)


AUTOCALL_WORST_OF = """
PARAM CPN = 8%   "coupon"
PARAM AC = 100%  "barriere autocall"
PARAM KI = 60%   "barriere KI"

AT 1, 2, 3
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY
  IF WOF < KI
    PAY WOF "capital a risque"
  ELSE
    PAY 1 "capital"
"""


def test_e_spread_costs_far_more_than_rate_on_an_autocall():
    """CLAUDE.md rule, on a product it was not written from: 100 bp of issuer
    spread must cost clearly more than 100 bp of rate, since the spread brings
    no drift back. Reasoned on the gap, not on the sign."""
    uls = [dict(UL, name=f"S{i}", sigma=0.25, q=0.03) for i in (1, 2, 3)]
    corr = [[1.0, 0.5, 0.5], [0.5, 1.0, 0.5], [0.5, 0.5, 1.0]]
    common = dict(underlyings=uls, corr=corr, model="constant", N=20_000, T=3.0)
    base = _run(AUTOCALL_WORST_OF, **common)[0]
    rate_effect = _run(AUTOCALL_WORST_OF, dr=0.01, **common)[0] - base
    spread_effect = _run(AUTOCALL_WORST_OF, funding_spread=0.01, **common)[0] - base
    assert spread_effect < 0
    assert spread_effect < rate_effect - 50 * BP, (rate_effect, spread_effect)
