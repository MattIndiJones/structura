"""Frozen leverage on a Dupire target, trained independently of pricing paths."""
from functools import lru_cache
import hashlib
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.special import ndtr


TRAINING_PATHS = 65_536
CONTROL_PATHS = 262_144
CONTROL_SEEDS = (19213, 48017)
LEVERAGE_VERSION = "frozen-lsv-v1"
EFFECTIVE_VOL_CAP = 3.
LEVERAGE_MIN = .2
LEVERAGE_MAX = 5.
VARIANCE_DEFAULTS = (("v0", .04), ("kappa", 2.), ("theta", .04), ("xi", .35), ("rho_h", -.7))


def _variance_parameters(u):
    return tuple(float(u.get(key, default)) for key, default in VARIANCE_DEFAULTS)


def supports_frozen_lsv(underlyings, *, yield_curve=None, sigma_r=0.,
                        barrier_monitoring="weekly", strike_set_t=None, residual=False):
    return (not yield_curve and not sigma_r and barrier_monitoring == "weekly"
            and not strike_set_t and not residual and bool(underlyings)
            and all(u.get("vol_surface") and not u.get("dividend_curve")
                    and not u.get("ccyh") and not u.get("sigma_fx", 0.) * u.get("rho_sfx", 0.)
                    for u in underlyings))


def _conditional_mean(indices, values, counts):
    sums = np.bincount(indices, weights=values, minlength=len(counts))
    return gaussian_filter1d(sums, 1., mode="constant") / np.maximum(counts, 1e-12)


@lru_cache(maxsize=8)
def _fit_marginal(intervals, r, q, params, lo, hi, nodes, target_bytes):
    from .engine import _heston_qe_vectorized

    v0, kappa, theta, xi, rho = params
    if not (math.isfinite(v0 + kappa + theta + xi + rho) and v0 > 0
            and kappa > 0 and theta > 0 and xi >= 0 and abs(rho) <= 1):
        raise ValueError("Paramètres de variance invalides pour le levier LSV.")
    target = np.frombuffer(target_bytes, dtype=np.float64).reshape(len(intervals), nodes)
    log_nodes = np.linspace(lo, hi, nodes)
    position_scale = (nodes - 1) / (hi - lo)
    rng = np.random.default_rng(94607)
    spots = np.zeros(TRAINING_PATHS)
    variance = np.full(TRAINING_PATHS, v0)
    grid = np.empty_like(target)
    limited = []
    rho_independent = math.sqrt(max(0., 1 - rho**2))
    time = 0.
    for step, dt in enumerate(intervals):
        bins = np.clip(np.rint((spots - lo) * position_scale).astype(int), 0, nodes - 1)
        counts = gaussian_filter1d(np.bincount(bins, minlength=nodes).astype(float), 1., mode="constant")
        enough = counts >= 24
        if not np.any(enough):
            raise ValueError("Échantillon insuffisant pour estimer le levier LSV.")
        conditional = _conditional_mean(bins, variance, counts)
        # Local linear intercept reduces the bias from uneven spot density in
        # the smoothing window, particularly along the steep downside wing.
        x_mean = _conditional_mean(bins, spots, counts)
        x_var = _conditional_mean(bins, spots**2, counts) - x_mean**2
        cov = _conditional_mean(bins, spots*variance, counts) - x_mean*conditional
        slope = np.divide(cov, x_var, out=np.zeros_like(cov), where=x_var > 1e-8)
        conditional += slope * (log_nodes - x_mean)
        enough &= conditional > 1e-8
        if not np.any(enough):
            raise ValueError("Variance conditionnelle insuffisante pour estimer le levier LSV.")
        mean = np.interp(log_nodes, log_nodes[enough], conditional[enough])
        leverage = np.clip(target[step] / np.sqrt(np.maximum(mean, 1e-8)),
                           LEVERAGE_MIN, LEVERAGE_MAX)
        # Correct the second moment in bins where the effective-vol cap binds.
        root_variance = np.sqrt(np.maximum(variance, 0.))
        attainable = _conditional_mean(
            bins, np.minimum(LEVERAGE_MAX * root_variance, EFFECTIVE_VOL_CAP)**2, counts)
        insufficient = enough & (attainable + 1e-4 < target[step]**2)
        if np.any(insufficient):
            spot_range = np.exp(log_nodes[insufficient])
            limited.append((time + dt / 2, float(spot_range.min()), float(spot_range.max())))
        clipped = root_variance * leverage[bins] > EFFECTIVE_VOL_CAP
        active = enough & (target[step] < EFFECTIVE_VOL_CAP)
        if np.any(clipped) and np.any(active):
            low, high = leverage.copy(), np.full(nodes, LEVERAGE_MAX)
            for _ in range(9):
                trial = (low + high) / 2
                effective = np.clip(trial[bins] * root_variance, .001, EFFECTIVE_VOL_CAP)
                moment = _conditional_mean(bins, effective**2, counts)
                below = moment < target[step]**2
                low = np.where(below, trial, low)
                high = np.where(below, high, trial)
            leverage[active] = ((low + high) / 2)[active]
        grid[step] = leverage
        effective = np.clip(np.interp(spots, log_nodes, leverage) * root_variance, .001, EFFECTIVE_VOL_CAP)
        z_s, z_v = rng.standard_normal((2, TRAINING_PATHS))
        spots += (r - q - .5 * effective**2) * dt + effective * math.sqrt(dt) * z_s
        variance = _heston_qe_vectorized(variance, kappa, theta, xi, dt, rho*z_s + rho_independent*z_v)
        time += dt
    grid.setflags(write=False)
    return grid, tuple(limited)


def frozen_leverage(underlyings, r, intervals, local_grid, *, diagnostics=None):
    grids, nodes, lo, hi = local_grid
    fits = tuple(_fit_marginal(
        tuple(float(t) for t in intervals), float(r), float(u.get("q", .02)),
        _variance_parameters(u),
        lo, hi, nodes, grid.tobytes(),
    ) for u, grid in zip(underlyings, grids))
    if diagnostics is not None:
        for i, (u, (_, limited)) in enumerate(zip(underlyings, fits)):
            if limited:
                diagnostics.append(dict(underlying=u.get("name") or f"S{i+1}",
                                        steps=[dict(t=t, min_spot=lo, max_spot=hi)
                                               for t, lo, hi in limited]))
    return tuple(grid for grid, _ in fits)


def leverage_controls(u, r, intervals, target, leverage, lo, hi, checkpoints,
                      paths=CONTROL_PATHS, seeds=CONTROL_SEEDS):
    """Out-of-sample paired premiums against the Dupire grid used in pricing."""
    from .engine import _heston_qe_vectorized

    q = float(u.get("q", .02))
    v0, kappa, theta, xi, rho = _variance_parameters(u)
    orthogonal = math.sqrt(max(0., 1. - rho**2))
    nodes = np.linspace(lo, hi, target.shape[1])
    strikes = np.array([.60, 1., 1.20])
    log_strikes = np.log(strikes)
    times = np.cumsum(intervals)
    sums = np.zeros((len(checkpoints), 2, len(strikes)))
    squares = np.zeros_like(sums)
    checkpoint_index = {step: i for i, step in enumerate(checkpoints)}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        s_lsv, s_lv = np.zeros(paths), np.zeros(paths)
        variance = np.full(paths, v0)
        for step, dt in enumerate(intervals):
            lv = np.interp(s_lv, nodes, target[step])
            lsv = np.clip(np.interp(s_lsv, nodes, leverage[step]) *
                          np.sqrt(np.maximum(variance, 0.)), .001, EFFECTIVE_VOL_CAP)
            mu_lsv = s_lsv + (r-q-.5*lsv**2)*dt
            mu_lv = s_lv + (r-q-.5*lv**2)*dt
            if step in checkpoint_index:
                # Integrate the final Gaussian exactly, reducing digital noise.
                def values(mu, vol):
                    sd = vol[:, None] * math.sqrt(dt)
                    d2 = (mu[:, None] - log_strikes) / sd
                    put = strikes*ndtr(-d2) - np.exp(mu[:, None]+.5*sd**2)*ndtr(-d2-sd)
                    return np.stack((put, ndtr(-d2)))
                diff = (values(mu_lsv, lsv)-values(mu_lv, lv))*math.exp(-r*times[step])
                i = checkpoint_index[step]
                sums[i] += diff.sum(axis=1)
                squares[i] += np.square(diff).sum(axis=1)
            if step == checkpoints[-1]:
                break
            z_s, z_v = rng.standard_normal((2, paths))
            s_lsv = mu_lsv + lsv*math.sqrt(dt)*z_s
            s_lv = mu_lv + lv*math.sqrt(dt)*z_s
            variance = _heston_qe_vectorized(variance, kappa, theta, xi, dt, rho*z_s + orthogonal*z_v)
    n = paths * len(seeds)
    mean = sums/n
    half = 1.96*np.sqrt(np.maximum(squares/n-mean**2, 0.)/(n-1))
    return [dict(expiry=float(times[step]), kind=kind, strike=float(strike),
                 error_bp=float(1e4*mean[i, j, k]), half_ci95_bp=float(1e4*half[i, j, k]),
                 limit_bp=limit)
            for i, step in enumerate(checkpoints)
            for j, (kind, limit) in enumerate((("vanille", 5.), ("digitale", 10.)))
            for k, strike in enumerate(strikes)]


@lru_cache(maxsize=8)
def _qualification_rows(intervals, r, q, params, lo, hi, nodes, target_bytes, checkpoints):
    leverage, _ = _fit_marginal(intervals, r, q, params, lo, hi, nodes, target_bytes)
    target = np.frombuffer(target_bytes, dtype=np.float64).reshape(len(intervals), nodes)
    u = dict(zip((key for key, _ in VARIANCE_DEFAULTS), params), q=q)
    return leverage_controls(u, r, intervals, target, leverage, lo, hi, checkpoints)


def leverage_digest(grids):
    digest = hashlib.sha256(LEVERAGE_VERSION.encode())
    for grid in grids:
        digest.update(grid.tobytes())
    return digest.hexdigest()


def prepare_mtf_leverage(script, context, dates, *, qualify):
    from .engine import (_build_lv_grid, _build_rate_term, _durations, _step_at,
                         mtf_simulation_axis, validate_model)

    validate_model("lsv", context.underlyings)
    steps, dt = mtf_simulation_axis(script, context.T, dates, True)
    intervals = tuple(float(t) for t in _durations(dt, steps))
    grids, nodes, lo, hi = _build_lv_grid(
        context.underlyings, _build_rate_term([], steps, dt, context.r), steps, dt,
        allow_ssvi_wings=True)
    leverage = frozen_leverage(context.underlyings, context.r, intervals, (grids, nodes, lo, hi))
    if not qualify:
        return leverage
    times = np.cumsum(intervals)
    # The MTF grid may not contain exactly six months. Use the nearest
    # simulation date and publish its actual expiry in the control.
    required = {steps - 1, int(np.argmin(abs(times - .5)))}
    required.update(_step_at(dt, t)-1 for event in script.events
                    for t in (event.dates or []) if 0 < t <= context.T)
    checkpoints = tuple(sorted(i for i in required if 0 <= i < steps))
    failures = []
    for i, (u, target) in enumerate(zip(context.underlyings, grids)):
        params = _variance_parameters(u)
        args = intervals, float(context.r), float(u.get("q", .02)), params, lo, hi, nodes, target.tobytes()
        rows = _qualification_rows(*args, checkpoints)
        worst = max(rows, key=lambda row: (abs(row["error_bp"])+row["half_ci95_bp"])/row["limit_bp"])
        if abs(worst["error_bp"])+worst["half_ci95_bp"] > worst["limit_bp"]:
            failures.append((u.get("name") or f"S{i+1}", worst))
    if failures:
        name, worst = max(failures, key=lambda item:
            (abs(item[1]["error_bp"])+item[1]["half_ci95_bp"])/item[1]["limit_bp"])
        raise ValueError(
            f"Levier LSV non qualifié pour {name} · {worst['kind']} à {worst['expiry']:.3f} an, "
            f"strike {100*worst['strike']:.0f} % du spot. Écart {worst['error_bp']:+.2f} pb "
            f"± {worst['half_ci95_bp']:.2f} pb (IC 95 %), seuil ± {worst['limit_bp']:.0f} pb.")
    return leverage
