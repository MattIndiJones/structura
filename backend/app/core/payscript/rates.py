"""Rates in the engine: yield-curve discount factors, stochastic short rate,
rate term (drift and discount together) and funding (discount only).

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
from typing import NamedTuple
from .bridge import semidefinite_factor
from .time_grid import durations as _durations, time_at as _time_at, times as _times


# ── Yield-curve discount factors ────────────────────────────────────

def _build_df_arr(yield_curve: list, ts: int, dt: float, r_eff: float) -> np.ndarray:
    """Pre-compute discount factor P(0,t) for each MC time step from zero-rate pillars.
    yield_curve: list of [T_years, zero_rate] pairs (rates as decimals).
    Falls back to flat r_eff if empty.
    """
    df = np.empty(ts + 1, dtype=np.float64)
    if not yield_curve:
        for s in range(ts + 1):
            df[s] = math.exp(-r_eff * _time_at(dt, s))
        return df

    yc = sorted(yield_curve, key=lambda p: p[0])
    Ts = [p[0] for p in yc]
    Rs = [p[1] for p in yc]

    for s in range(ts + 1):
        t = _time_at(dt, s)
        if t <= 0.0:
            df[s] = 1.0
        elif t <= Ts[0]:
            df[s] = math.exp(-Rs[0] * t)
        elif t >= Ts[-1]:
            df[s] = math.exp(-Rs[-1] * t)
        else:
            r_t = Rs[-1]
            for k in range(len(Ts) - 1):
                if Ts[k] <= t <= Ts[k + 1]:
                    frac = (t - Ts[k]) / (Ts[k + 1] - Ts[k])
                    r_t = Rs[k] + frac * (Rs[k + 1] - Rs[k])
                    break
            df[s] = math.exp(-r_t * t)
    return df


# ── Stochastic short rate (optional, driftless Gaussian perturbation) ──
#
# When sigma_r > 0, a single shared rate factor x(t) = r(t) - f(0,t) is added on
# top of the deterministic forward curve f(0,t). x is an Ornstein-Uhlenbeck
# process: dx = -a_r*x*dt + sigma_r*dW_r. This reparametrization (standard for
# Hull-White) means the model fits the input curve exactly by construction — no
# separate theta(t) drift calibration needed, the curve fit is automatic.
#   a_r = 0  -> x is a pure driftless Brownian motion (no mean reversion): the
#               same simplified "ABM" model as italian_app's stochastic-rate mode.
#   a_r > 0  -> x mean-reverts to 0: a proper Hull-White short rate.
# Each underlying picks up the shock in its own drift via its rho_rS, and
# discounting becomes path-dependent (the numeraire is now stochastic).
# Disabled by default (sigma_r=0) — every call site below is then a no-op and
# reproduces the exact prior deterministic-rate behavior.

def _df_at_time(df_arr: np.ndarray | None, t: float, dt: float, ts: int,
                r_eff: float):
    """Discount factor at an arbitrary time, off a curve defined on grid steps.

    A payment date almost never lands on a simulation step: a coupon observed
    on a weekly grid and settled five business days later falls between two
    steps, and a redemption settled after the last fixing falls beyond the grid
    entirely. Log-linear in the discount factor — linear in the zero rate over
    each interval — and, past the last point, extension at the curve's own
    final forward rate rather than at the flat r.

    Returns a scalar for a deterministic curve, one factor per path for a
    stochastic one."""
    if t == 0:
        return 1.0
    if df_arr is None:
        # Vaut aussi pour t < 0 : exp(+r|t|) > 1, on capitalise en arriere.
        return math.exp(-r_eff * t)

    log_df = np.log(np.maximum(df_arr, 1e-300))
    axis = _times(dt, ts)
    lengths = _durations(dt, ts)
    k = int(np.searchsorted(axis, t, side="right")) - 1
    if t < 0:
        fwd = (log_df[0] - log_df[1]) / lengths[0]
        return np.exp(log_df[0] - fwd * t)
    if k >= ts:
        fwd = (log_df[ts - 1] - log_df[ts]) / lengths[-1]
        return np.exp(log_df[ts] - fwd * (t - axis[-1]))
    fraction = (t - axis[k]) / lengths[k]
    return np.exp(log_df[k] + (log_df[k + 1] - log_df[k]) * fraction)


def _forward_rate_arr(df_arr: np.ndarray, dt: float) -> np.ndarray:
    """Instantaneous forward rate over each weekly sub-interval [s-1, s], derived
    from a deterministic discount curve: f[s-1] = -(log df[s] - log df[s-1]) / dt.
    Shape (ts,) — index k is the forward rate applied during weekly step k+1."""
    log_df = np.log(np.maximum(df_arr, 1e-300))
    return -(log_df[1:] - log_df[:-1]) / dt


def _validate_short_rate_parameters(sigma_r: float, a_r: float) -> None:
    if not math.isfinite(sigma_r) or sigma_r < 0.0:
        raise ValueError("La volatilité des taux doit être finie et positive ou nulle.")
    if not math.isfinite(a_r) or a_r < 0.0:
        raise ValueError("Le retour à la moyenne des taux doit être fini et positif ou nul.")


def _ou_transition(sigma_r: float, a_r: float, dt: float) -> tuple[float, float]:
    """Exact OU transition, continuous at a_r=0 without subtractive cancellation."""
    exponent = 2.0 * a_r * dt
    variance_ratio = -math.expm1(-exponent) / exponent if exponent else 1.0
    return math.exp(-a_r * dt), sigma_r * math.sqrt(dt * variance_ratio)


def _hw_convexity(sigma_r: float, a_r: float, dt: float, ts: int,
                  phi: float | None = None, step_sd: float | None = None) -> np.ndarray:
    """Deterministic drift that makes the simulated short rate reprice its own
    input curve — the property that defines Hull-White and that this model was
    missing.

    Writing r = f(0,t) + x with x centred looks like it fits the curve for
    free, but the discount factor is exp(-integral r), and Jensen makes
    E[exp(-integral x)] = exp(+Var/2) > 1: every bond came out too EXPENSIVE,
    by 164bp on a 5-year zero at 3% vol. The fix is the classic phi(t): add
    back exactly the term that cancels that variance.

    The correction is computed on the DISCRETE integral the simulator actually
    forms — dt * sum of x over steps — rather than on its continuous limit, so
    the curve is reproduced to machine precision on the grid in use instead of
    to a discretisation residual.

    For I_k = dt*sum_{j=1}^k x_j, psi_k = (Var(I_k)-Var(I_{k-1}))/(2*dt).
    The OU branch propagates Var(x_k) and Cov(I_k,x_k) directly, avoiding the
    cancellation of geometric sums as a_r tends to zero.
    """
    variance_x = covariance_I_x = 0.0
    psi = np.empty(ts, dtype=np.float64)
    for k, length in enumerate(_durations(dt, ts)):
        phi_k, sd_k = _ou_transition(sigma_r, a_r, float(length))
        variance_x = phi_k * phi_k * variance_x + sd_k * sd_k
        previous_covariance = phi_k * covariance_I_x
        psi[k] = previous_covariance + 0.5 * length * variance_x
        covariance_I_x = previous_covariance + length * variance_x
    return psi


def _stochastic_rate_paths(fwd: np.ndarray, sigma_r: float, a_r: float, sq_dt: float,
                           dt: float, Z_r: np.ndarray):
    """Build the per-path instantaneous rate and discount factor from a forward
    curve fwd (ts,) and a raw standard-normal shock Z_r (ts, N).

    a_r == 0: x is a pure Brownian motion — closed-form cumsum (fast path, exact
    same formula as before a_r existed).
    a_r > 0: x is an Ornstein-Uhlenbeck process — simulated via its EXACT one-step
    transition (not an Euler approximation), via a loop over ts steps since each
    step depends on the previous one (an AR(1) recursion).

    Returns r_path (ts, N) and df (ts+1, N), df[0] = 1."""
    _validate_short_rate_parameters(sigma_r, a_r)
    if (Z_r.ndim != 2 or min(Z_r.shape) <= 0 or fwd.shape != (Z_r.shape[0],)
            or not np.isfinite(Z_r).all() or not np.isfinite(fwd).all()):
        raise ValueError("Axe temporel, courbe ou chocs de taux stochastiques invalides.")
    ts, N = Z_r.shape
    lengths = _durations(dt, ts)
    try:
        with np.errstate(over="raise", invalid="raise"):
            x = np.empty((ts, N), dtype=np.float64)
            x_prev = np.zeros(N, dtype=np.float64)
            for k, length in enumerate(lengths):
                phi_k, sd_k = _ou_transition(sigma_r, a_r, float(length))
                x_prev = phi_k * x_prev + sd_k * Z_r[k]
                x[k] = x_prev
            psi = _hw_convexity(sigma_r, a_r, dt, ts)
            r_path = fwd[:, None] + x + psi[:, None]
            cum_integral = np.cumsum(r_path * lengths[:, None], axis=0)
            df = np.vstack([np.ones((1, N)), np.exp(-cum_integral)])
    except (FloatingPointError, OverflowError) as exc:
        raise ValueError("Les taux stochastiques produisent des facteurs hors du domaine numérique.") from exc
    if not np.isfinite(r_path).all() or not np.isfinite(df).all() or (df <= 0.0).any():
        raise ValueError("Les taux stochastiques produisent des facteurs non finis ou nuls.")
    return r_path, df


class _RateTerm(NamedTuple):
    """Every rate-derived quantity a pricing run needs, all from one curve.

    A pricing run consumes the rate in three unrelated places — the drift of
    each simulated asset, the discount factor of each cash flow, and the
    Black-Scholes prices the Dupire calibration inverts. When each place reads
    its own source, the run is no longer arbitrage-free: a prepaid forward under
    a flat 1% curve priced 1.0099 instead of exp(-qT)=0.9901, two points of
    nominal, because the drift used the flat r while the discounting used the
    curve. Deriving all three from this one object is what makes that
    impossible rather than merely unlikely.

    df       (ts+1,)  discount factor P(0, s*dt), curve shift included
    r_flat            r + dr — the scalar short rate, only meaningful flat
    step_fwd (ts,)    instantaneous forward over step k, or None
    zero     (ts+1,)  continuously-compounded zero rate, or None

    `step_fwd` and `zero` are None exactly when the caller passed no curve.
    That is the invariant to branch on — never `not yield_curve` — so the flat
    case keeps its exact scalar representation. Re-deriving a flat rate through
    the forward machinery would agree mathematically but differ in the last
    ulps, and every price on the dominant code path would shift.
    """
    df: np.ndarray
    r_flat: float
    step_fwd: np.ndarray | None
    zero: np.ndarray | None


def _build_rate_term(yield_curve, ts: int, dt: float, r: float,
                     dr: float = 0.0) -> _RateTerm:
    """Assemble the run's rate term. `dr` is a parallel shift of the whole zero
    curve — it moves discounting, drift and smile calibration together, which is
    what makes Rho a true derivative rather than a partial one."""
    r_flat = r + dr
    if not yield_curve:
        return _RateTerm(df=_build_df_arr([], ts, dt, r_flat), r_flat=r_flat,
                         step_fwd=None, zero=None)

    t = _times(dt, ts)
    df = _build_df_arr(yield_curve, ts, dt, r_flat)
    if dr != 0.0:
        df = df * np.exp(-dr * t)

    # Deriving the forwards FROM df (rather than re-reading the pillars) makes
    # exp(-cumsum(step_fwd)*dt) == df an identity of construction: the cumsum of
    # the logs telescopes exactly. Drift and discounting then cannot drift apart
    # by an interpolation residual.
    step_fwd = _forward_rate_arr(df, dt)
    zero = np.empty(ts + 1, dtype=np.float64)
    zero[1:] = -np.log(np.maximum(df[1:], 1e-300)) / t[1:]
    zero[0] = step_fwd[0]
    return _RateTerm(df=df, r_flat=r_flat, step_fwd=step_fwd, zero=zero)


def _funding_df_arr(funding_curve, funding_spread: float,
                    ts: int, dt: float) -> np.ndarray | None:
    """Facteur d'actualisation du seul spread émetteur, ou None s'il n'y en a pas.

    DÉLIBÉRÉMENT séparé de `_RateTerm`, qui unifie drift, actualisation et
    calibration du smile pour qu'ils ne puissent pas diverger. Un spread de
    funding n'est pas un taux : il dit la qualité de crédit de celui qui doit
    payer, pas le coût de portage du sous-jacent. Le crédit de l'émetteur ne
    déplace pas le forward de l'action.

    Le router dans la courbe de taux donnerait le SIGNE INVERSE — sur une note
    la hausse du forward l'emporte sur l'actualisation, et le produit vaudrait
    plus cher à mesure que son émetteur se dégrade. C'est pour ça qu'il entre
    ici, sur `df` seul, et jamais dans `step_fwd`.

    `funding_curve` (piliers [T, spread]) l'emporte sur `funding_spread`
    (niveau plat). Interpolation et extrapolation identiques à celles de la
    courbe de taux — même fonction, avec un taux de repli nul."""
    if funding_curve:
        return _build_df_arr(funding_curve, ts, dt, 0.0)
    if funding_spread:
        t = _times(dt, ts)
        return np.exp(-funding_spread * t)
    return None


def _blend_rate_factor(z_i, Z_r_val, rho_rS: float):
    """Couple an asset's Brownian to the shared rate factor: z_i_final =
    rho_rS*Z_r_val + z_i, where z_i already carries variance 1 - rho_rS^2
    because it comes out of the factor built by `_rate_coupled_factor`.

    It used to read rho_rS*Z_r + sqrt(1-rho_rS^2)*z_i, with z_i a unit-variance
    draw from chol(R). That gives the right asset/rate correlation, but it
    injects a component every asset shares, so the realized asset/asset
    correlation came out at rho_i*rho_j + sqrt((1-rho_i^2)(1-rho_j^2))*R_ij
    instead of R_ij. With three assets entered at 0.30 and rho_rS = 0.9 the
    effective figure was 0.867, and the worst-of moved 7.6 points of notional
    on a parameter the user was told described the rate, not the basket.

    Splitting the factorisation instead — chol(R - a a') for the diffusion,
    a_i*Z_r for the rate leg — reproduces the joint correlation matrix
    [[1, a'], [a, R]] exactly: unit variance, rho_rS against the rate, and R
    between assets, all three at once. No-op when rho_rS == 0."""
    if rho_rS == 0.0:
        return z_i
    return rho_rS * Z_r_val + z_i


def _rate_coupled_factor(corr: list[list[float]], rho_vec, n: int) -> np.ndarray:
    """Cholesky factor of R - a·a', the diffusion block of the joint
    (rate, assets) correlation matrix [[1, a'], [a, R]].

    Its positive-definiteness IS the consistency condition between the
    correlation matrix and the rate correlations: asking for three assets
    correlated at 0.30 that are each 0.90 correlated to the same rate factor
    describes a matrix that does not exist, because going through the rate
    already forces them to about 0.81 with each other. The old code accepted
    it and quietly priced the basket it implied. Refusing is the same choice
    made for a non-PSD correlation matrix a few lines up — the alternative is
    a plausible price for a product nobody specified."""
    R = np.array(corr, dtype=np.float64)
    a = np.array(rho_vec, dtype=np.float64)
    M = R - np.outer(a, a)
    eig = np.linalg.eigvalsh(M)
    if eig.min() < -1e-10:
        worst = int(np.argmax(np.abs(a)))
        raise ValueError(
            f"Corrélations incompatibles : avec la matrice actions fournie, les "
            f"corrélations taux/action demandées (rho_rS, la plus forte étant "
            f"{a[worst]:+.2f} sur le sous-jacent {worst + 1}) ne définissent pas "
            f"une structure de dépendance valide — passer par le facteur de taux "
            f"imposerait déjà aux actions une corrélation supérieure à celle "
            f"saisie. Réduisez rho_rS ou augmentez la corrélation actions.")
    if eig.min() >= -1e-12 and eig.min() < 1e-12:
        return semidefinite_factor(M)
    if eig.min() < 1e-12:
        M = M + (max(0.0, -eig.min()) + 1e-12) * np.eye(n)
    return np.linalg.cholesky(M)
