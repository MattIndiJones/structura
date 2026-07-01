"""
Monte Carlo engine — vectorized path simulation + per-path PayScript evaluation.

Models: constant (GBM), heston (QE), sabr (ATM vol), localvol (Dupire).
Variance reduction: antithetic variates.
Greeks: CRN bump-and-reprice.
Analytics: payoff profile, MC paths visualization, probability analysis, historical backtest.
"""
from __future__ import annotations
import math
import time
import numpy as np
from numpy.random import default_rng
from .parser import CompiledScript, CompiledEvent

SY = 52       # weekly steps per year
PSI_C = 1.5   # Heston QE switching threshold
MTF_MAX_BATCH = 20_000   # cap simulated paths per inner Mark-to-Future chunk (memory bound)


# ── Cholesky decomposition ──────────────────────────────────────────

def cholesky(corr: list[list[float]], n: int) -> np.ndarray:
    C = np.array(corr, dtype=np.float64)
    eigvals = np.linalg.eigvalsh(C)
    if eigvals.min() < 0:
        C += (-eigvals.min() + 1e-8) * np.eye(n)
    return np.linalg.cholesky(C)


# ── SABR vol ────────────────────────────────────────────────────────

def sabr_vol(K: float, T: float, F: float, alpha: float, beta: float,
             rho: float, nu: float) -> float:
    if T < 1e-6 or K <= 0 or F <= 0:
        return alpha
    logFK = math.log(F / K)
    FK_b = (F * K) ** ((1 - beta) / 2)
    z = (nu / alpha) * FK_b * logFK if abs(logFK) > 1e-8 else 0.0
    if abs(z) < 1e-8:
        x_z = 1.0
    else:
        inner = math.sqrt(max(0, 1 - 2*rho*z + z*z)) + z - rho
        denom = math.log(max(1e-14, inner / (1 - rho)))
        x_z = z / denom if abs(denom) > 1e-10 else 1.0
    A = alpha / (FK_b * (1 + (1-beta)**2/24 * logFK**2 + (1-beta)**4/1920 * logFK**4))
    B = 1 + ((1-beta)**2/24 * alpha**2/(FK_b**2)
             + rho*beta*nu*alpha/(4*FK_b)
             + (2 - 3*rho**2)/24 * nu**2) * T
    return max(0.001, A * x_z * B)


# ── Heston QE step ──────────────────────────────────────────────────

def _heston_qe_scalar(Vi: float, kappa: float, theta: float, xi: float,
                      dt: float, zv: float) -> float:
    ek = math.exp(-kappa * dt)
    xi2 = xi * xi
    m_v = theta + (Vi - theta) * ek
    s2 = Vi * xi2 * ek / kappa * (1 - ek) + theta * xi2 / (2 * kappa) * (1 - ek) ** 2
    s2 = max(s2, 0.0)
    psi = s2 / (m_v * m_v) if m_v > 1e-10 else 2.0
    if psi <= PSI_C:
        inv = 2.0 / psi
        b2 = inv - 1 + math.sqrt(max(0.0, inv * (inv - 1)))
        a = m_v / (1 + b2)
        return max(0.0, a * (math.sqrt(b2) + zv) ** 2)
    else:
        U = 0.5 * math.erfc(-zv / math.sqrt(2))   # exact Φ(zv); old approximation had ~10% error
        p_exp = (psi - 1) / (psi + 1)
        beta = (1 - p_exp) / m_v if m_v > 1e-10 else 1.0
        if U <= p_exp:
            return 0.0
        return max(0.0, math.log(max(1e-14, (1 - p_exp) / max(1e-14, 1 - U))) / beta)


# ── Dupire local vol ────────────────────────────────────────────────

def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _smile_vol(logK: float, sigma0: float, skew: float, curvature: float) -> float:
    """Parametric implied vol surface: sigma(K) = sigma0 + skew*logK + curv*logK^2 (additive)."""
    v = sigma0 + skew * logK + curvature * logK**2
    return max(0.005, min(v, 2.0))


def _bs_call_n(K: float, r: float, q: float, sigma: float, T: float) -> float:
    """Black-Scholes call price with S0=1 normalized."""
    if T < 1e-6 or sigma < 1e-6 or K <= 0:
        return max(0.0, math.exp(-q*T) - K*math.exp(-r*T))
    sqT = math.sqrt(T)
    d1 = (math.log(1.0 / max(K, 1e-12)) + (r - q + 0.5*sigma**2)*T) / (sigma*sqT)
    d2 = d1 - sigma*sqT
    return max(0.0, math.exp(-q*T)*_ncdf(d1) - K*math.exp(-r*T)*_ncdf(d2))


def _dupire_vol(K: float, T: float, sigma0: float, skew: float, curvature: float,
                r: float, q: float) -> float:
    """Dupire local vol via 2nd-order FD on parametric smile."""
    fb = _smile_vol(math.log(max(K, 1e-8)), sigma0, skew, curvature)
    if T < 3/52 or K <= 0:
        return fb
    h = K * 0.012
    dT = max(3/52, T * 0.06)

    def getC(Kv: float, Tv: float) -> float:
        if Kv <= 0 or Tv <= 0:
            return 0.0
        sig = _smile_vol(math.log(max(Kv, 1e-8)), sigma0, skew, curvature)
        c = _bs_call_n(Kv, r, q, sig, Tv)
        return c if math.isfinite(c) else 0.0

    C, CT = getC(K, T), getC(K, T + dT)
    Ku, Kd = getC(K+h, T), getC(K-h, T)
    dCdT   = (CT - C) / dT
    dCdK   = (Ku - Kd) / (2*h)
    d2CdK2 = (Ku - 2*C + Kd) / (h*h)
    num = dCdT + (r - q)*K*dCdK + q*C
    den = 0.5 * K * K * d2CdK2
    if not (math.isfinite(num) and math.isfinite(den)) or den < 1e-9 or num <= 0:
        return fb
    v = num / den
    if not math.isfinite(v) or v <= 0:
        return fb
    sig = math.sqrt(v)
    return max(0.005, min(sig, 1.5)) if math.isfinite(sig) else fb


def _build_lv_grid(underlyings, r_eff: float, ts: int, dt: float, nK: int = 50):
    """Precompute local vol grid (ts, nK) for each underlying asset."""
    logKmin, logKmax = math.log(0.20), math.log(3.0)
    Ks = [math.exp(logKmin + i/(nK-1)*(logKmax-logKmin)) for i in range(nK)]
    grids = []
    for u in underlyings:
        sig0 = u.get("sigma", 0.20)
        skew = u.get("skew", 0.0)
        curv = u.get("curvature", 0.0)
        q = u.get("q", 0.02)
        g = np.zeros((ts, nK), dtype=np.float32)
        for step in range(ts):
            T_s = (step + 1) * dt
            for ki, K in enumerate(Ks):
                lv = _dupire_vol(K, T_s, sig0, skew, curv, r_eff, q)
                g[step, ki] = lv if math.isfinite(lv) and lv > 0 else sig0
        grids.append(g)
    return grids, nK, logKmin, logKmax


# ── Simulation engines ──────────────────────────────────────────────

def _seed_spot(spot_mult) -> np.ndarray:
    """Build the t=0 spot slice from spot_mult.
    Accepts either a per-asset scalar vector of shape (n,) — the same initial spot
    broadcast to every path, used by Greeks bump-and-reprice — or a per-asset,
    per-path matrix of shape (n, N), used by Mark-to-Future to seed each inner path
    at its own outer scenario's spot level."""
    arr = np.asarray(spot_mult, dtype=np.float64)
    return arr if arr.ndim == 2 else arr[:, None]


def _simulate_gbm(ts: int, n: int, N: int, dt: float, sq_dt: float,
                  underlyings, r_eff: float, L: np.ndarray,
                  Z: np.ndarray, spot_mult=None, vol_add=None,
                  r_path=None, Z_r=None) -> np.ndarray:
    """Vectorized GBM — all paths at once via cumsum. Returns (ts+1, n, N).

    r_path (ts, N) and Z_r (ts, N) are the optional stochastic-rate level and raw
    shock from _stochastic_rate_paths — both None (default) reproduces the exact
    flat/curve-rate behavior. r_path overrides r_eff in the drift; Z_r re-blends
    each asset's own correlated Brownian via its rho_rS (_blend_rate_factor)."""
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts * N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    r_term = r_eff if r_path is None else r_path
    for i, u in enumerate(underlyings):
        sig = u.get("sigma", 0.20)
        if vol_add is not None:
            sig = max(0.005, sig + vol_add[i])
        z_i = _blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0)) if Z_r is not None else Zc[:, i, :]
        q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
        drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5 * sig * sig
        log_ret = drift * dt + sig * sq_dt * z_i
        S[1:, i, :] = S[0, i] * np.exp(np.cumsum(log_ret, axis=0))

    return S


def _simulate_heston(ts: int, n: int, N: int, dt: float, sq_dt: float,
                     underlyings, r_eff: float, L: np.ndarray,
                     Z: np.ndarray, Zv: np.ndarray,
                     spot_mult=None, vol_add=None, r_path=None, Z_r=None) -> np.ndarray:
    """Per-path Heston QE simulation (Andersen 2007).

    r_path/Z_r: see _simulate_gbm. The rho_rS blend is applied to cZ[i] (the
    asset's inter-asset-correlated Brownian) before it feeds into both the
    variance process (zv) and the spot's own perp component (z_S_perp) — the
    rate shock therefore propagates into variance too via that shared factor,
    same ordering as the simpler models."""
    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    for path in range(N):
        V = np.array([u.get("v0", 0.04) for u in underlyings], dtype=np.float64)
        for step in range(ts):
            z_raw = Z[step, :, path]
            cZ = L @ z_raw
            r_term = r_eff if r_path is None else r_path[step, path]
            for i, u in enumerate(underlyings):
                rh  = u.get("rho_h", -0.70)
                kap = u.get("kappa", 2.0)
                th  = u.get("theta", 0.04)
                xi  = u.get("xi", 0.35)
                rhop = math.sqrt(max(0.0, 1.0 - rh*rh))

                cz_i = _blend_rate_factor(cZ[i], Z_r[step, path], u.get("rho_rS", 0.0)) if Z_r is not None else cZ[i]

                # Variance BM: correlated with spot via rho_h
                z_perp_var = Zv[step, i, path]          # independent component
                zv = rh * cz_i + rhop * z_perp_var      # full variance Brownian W_V

                V_old  = float(V[i])
                V_next = _heston_qe_scalar(V_old, kap, th, xi, dt, zv)
                V_bar  = (V_old + V_next) / 2
                V[i]   = V_next

                sig_add = vol_add[i] if vol_add is not None else 0.0
                sv = math.sqrt(max(0.0, V_bar)) + sig_add

                q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sv
                drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5 * V_bar

                # Andersen (2007) spot update.
                # Decompose: sqrt(V)*dW_S = rho/xi*(dV-drift_V) + rhop*sqrt(V)*dZ_perp
                # z_S_perp ⊥ W_V  => E[exp(rhop*sv*z_S_perp*√dt) | V_bar] = exp(0.5*rhop²*sv²*dt)
                # Combined with corr_term variance ≈ rho²*V_bar*dt => total = V_bar*dt ✓ (martingale)
                z_S_perp  = rhop * cz_i - rh * z_perp_var
                corr_term = rh / xi * (V_next - V_old - kap * (th - V_bar) * dt)
                S[step+1, i, path] = S[step, i, path] * math.exp(
                    drift*dt + corr_term + rhop * sv * sq_dt * z_S_perp
                )

    return S


def _simulate_sabr(ts: int, n: int, N: int, dt: float, sq_dt: float,
                   underlyings, r_eff: float, L: np.ndarray,
                   Z: np.ndarray, Za: np.ndarray,
                   spot_mult=None, vol_add=None, r_path=None, Z_r=None) -> np.ndarray:
    """SABR SDE simulation (Euler-Maruyama).
    dF = α*F^β*dW,  dα = ν*α*dZ,  corr(dW,dZ)=ρ per underlying.
    Za: (ts, n, N) independent noise for vol Brownians.
    r_path/Z_r: see _simulate_gbm — rho_rS blend applied to cZ[i] before it
    feeds into both the spot driver z_S and the vol-of-vol correlation z_a.
    """
    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    for path in range(N):
        alpha = np.array([u.get("alpha", 0.20) for u in underlyings], dtype=np.float64)

        for step in range(ts):
            z_raw  = Z[step, :, path]
            za_raw = Za[step, :, path]
            cZ = L @ z_raw                          # correlated spot Brownians
            r_term = r_eff if r_path is None else r_path[step, path]

            for i, u in enumerate(underlyings):
                rho_s = u.get("rho", -0.30)         # SABR rho (spot–vol corr)
                nu    = u.get("nu", 0.40)
                beta  = u.get("beta", 0.50)

                z_S = _blend_rate_factor(cZ[i], Z_r[step, path], u.get("rho_rS", 0.0)) if Z_r is not None else cZ[i]
                # Vol Brownian correlated with spot via SABR rho
                z_a = rho_s * z_S + math.sqrt(max(0.0, 1.0 - rho_s**2)) * za_raw[i]

                # Lognormal SDE for stochastic vol α
                alpha_new = alpha[i] * math.exp(nu * sq_dt * z_a - 0.5 * nu**2 * dt)
                alpha_bar = 0.5 * (alpha[i] + alpha_new)

                # CEV effective vol: σ = α_old * S^(β−1)
                # Use alpha_old (not alpha_bar) to avoid correlation bias with z_S.
                # alpha_bar = f(z_a) = f(rho*z_S + ...) is correlated with z_S,
                # which would break E[exp(sig*z_S*√dt)] = exp(½sig²dt) martingale property.
                S_c = max(S[step, i, path], 1e-8)
                alpha_old = alpha[i]
                if abs(beta - 1.0) < 1e-4:
                    sig = alpha_old
                else:
                    sig = alpha_old * (S_c ** (beta - 1.0))

                if vol_add is not None:
                    sig = max(0.001, sig + vol_add[i])
                else:
                    sig = max(0.001, min(sig, 3.0))

                q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
                drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5 * sig**2
                S[step + 1, i, path] = S_c * math.exp(drift * dt + sig * sq_dt * z_S)
                alpha[i] = alpha_new

    return S


def _simulate_lv(ts: int, n: int, N: int, dt: float, sq_dt: float,
                  underlyings, r_eff: float, L: np.ndarray, Z: np.ndarray,
                  lv_grids, nK: int, logKmin: float, logKmax: float,
                  spot_mult=None, vol_add=None, r_path=None, Z_r=None) -> np.ndarray:
    """Vectorized Dupire local vol simulation using precomputed grid.

    r_path/Z_r: see _simulate_gbm — optional stochastic-rate level/shock, no-op
    when both None (default)."""
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts*N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z

    S = np.ones((ts+1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    dlogK = (logKmax - logKmin) / (nK - 1)

    for step in range(ts):
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            S_c = S[step, i, :]
            logS = np.log(np.maximum(S_c, 1e-8))
            kif = (logS - logKmin) / dlogK
            k0 = np.clip(kif.astype(int), 0, nK-2)
            frac = np.clip(kif - k0, 0.0, 1.0)
            g = lv_grids[i]
            lvs = g[step, k0] * (1.0-frac) + g[step, k0+1] * frac
            if vol_add is not None:
                lvs = np.maximum(lvs + vol_add[i], 0.001)
            else:
                lvs = np.maximum(lvs, 0.001)
            z_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * lvs
            drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5*lvs**2
            S[step+1, i, :] = S_c * np.exp(drift*dt + lvs*sq_dt*z_i)

    return S


# ── Yield-curve discount factors ────────────────────────────────────

def _build_df_arr(yield_curve: list, ts: int, dt: float, r_eff: float) -> np.ndarray:
    """Pre-compute discount factor P(0,t) for each MC time step from zero-rate pillars.
    yield_curve: list of [T_years, zero_rate] pairs (rates as decimals).
    Falls back to flat r_eff if empty.
    """
    df = np.empty(ts + 1, dtype=np.float64)
    if not yield_curve:
        for s in range(ts + 1):
            df[s] = math.exp(-r_eff * s * dt)
        return df

    yc = sorted(yield_curve, key=lambda p: p[0])
    Ts = [p[0] for p in yc]
    Rs = [p[1] for p in yc]

    for s in range(ts + 1):
        t = s * dt
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

def _forward_rate_arr(df_arr: np.ndarray, dt: float) -> np.ndarray:
    """Instantaneous forward rate over each weekly sub-interval [s-1, s], derived
    from a deterministic discount curve: f[s-1] = -(log df[s] - log df[s-1]) / dt.
    Shape (ts,) — index k is the forward rate applied during weekly step k+1."""
    log_df = np.log(np.maximum(df_arr, 1e-300))
    return -(log_df[1:] - log_df[:-1]) / dt


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
    ts, N = Z_r.shape
    if a_r <= 0.0:
        x = sigma_r * sq_dt * np.cumsum(Z_r, axis=0)
    else:
        phi = math.exp(-a_r * dt)
        step_sd = sigma_r * math.sqrt(max(0.0, (1.0 - phi * phi) / (2.0 * a_r)))
        x = np.empty((ts, N), dtype=np.float64)
        x_prev = np.zeros(N, dtype=np.float64)
        for k in range(ts):
            x_prev = phi * x_prev + step_sd * Z_r[k]
            x[k] = x_prev

    r_path = fwd[:, None] + x                                 # (ts, N)
    cum_integral = np.cumsum(r_path, axis=0) * dt             # (ts, N)
    df = np.vstack([np.ones((1, N)), np.exp(-cum_integral)])
    return r_path, df


def _blend_rate_factor(z_i, Z_r_val, rho_rS: float):
    """Re-blend an asset's own (already inter-asset-correlated) Brownian z_i with
    the shared rate factor Z_r_val via that asset's rho_rS:
    z_i_final = rho_rS*Z_r_val + sqrt(1-rho_rS^2)*z_i. No-op when rho_rS == 0."""
    if rho_rS == 0.0:
        return z_i
    return rho_rS * Z_r_val + math.sqrt(max(0.0, 1.0 - rho_rS * rho_rS)) * z_i


# ── PayScript evaluation ────────────────────────────────────────────

def _eval_paths(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                dt: float, r_eff: float, user_params: dict,
                step_map: dict, mat_events: list, flux_map: dict,
                record: bool, df_arr: np.ndarray | None = None,
                wof_min_init=None, bof_max_init=None,
                stop_times_out: list | None = None) -> list[float]:
    """Evaluate PayScript on pre-computed spot paths. Observation-only loop.

    wof_min_init / bof_max_init (None, or array of shape (N,)) seed the running
    worst-of-min / best-of-max state inherited from before t=0 of this path tensor.
    Used by Mark-to-Future to carry over each outer scenario's pre-t0 barrier state
    into its inner residual-pricing paths; left at None (no-op) for normal pricing.

    NOTE: s_min/s_max/s_prev/realvol (below) always reset to their day-0 defaults
    at the start of this path tensor — unlike wof_min/bof_max they have no _init
    parameter, so a script using S_MIN/S_MAX/S_PREV/REALVOL will NOT correctly
    inherit pre-t0 state when priced through Mark-to-Future's residual repricing,
    or through the historical backtest evaluator (eval_script_on_history), which
    doesn't compute these arrays at all. Known gap, not addressed here."""
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    WOF_min = np.minimum.accumulate(WOF, axis=0)
    BOF_max = np.maximum.accumulate(BOF, axis=0)
    if wof_min_init is not None:
        WOF_min = np.minimum(WOF_min, wof_min_init)
    if bof_max_init is not None:
        BOF_max = np.maximum(BOF_max, bof_max_init)

    # Per-asset running min/max (S_MIN[i]/S_MAX[i] — distinct from WOF_min/BOF_max,
    # which are basket-level). Realized vol of the WOF index, annualized from
    # weekly log-returns accumulated since inception (REALVOL).
    S_min = np.minimum.accumulate(S[1:], axis=0)   # (ts, n, N)
    S_max = np.maximum.accumulate(S[1:], axis=0)   # (ts, n, N)
    WOF_full = np.vstack([np.ones((1, N)), WOF])    # (ts+1, N) — WOF(t=0) = 1.0
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)   # (ts, N)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)    # (ts, N)

    obs_steps = sorted(step_map.keys())
    payoffs: list[float] = []
    payoffs_raw: list[float] = []   # undiscounted total cash flow per path

    for path in range(N):
        ctx = {
            "spots": [1.0] * n, "accum": 0.0, "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
            "s_min": [1.0] * n, "s_max": [1.0] * n, "s_prev": [1.0] * n, "realvol": 0.0,
            "done": False, "memo": {**user_params}, "total_cf": 0.0, "total_cf_raw": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)

        done = False
        obs_idx = 0

        for step in obs_steps:
            if done:
                break
            if df_arr is None:
                disc = math.exp(-r_eff * step * dt)
            else:
                disc = df_arr[step, path] if df_arr.ndim == 2 else df_arr[step]
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[step, :, path])
            ctx["s_min"] = list(S_min[step - 1, :, path])
            ctx["s_max"] = list(S_max[step - 1, :, path])
            ctx["realvol"] = math.sqrt(SY * cum_sq_ret[step - 1, path] / step)
            ctx["t"] = step * dt
            ctx["wof_min"] = float(WOF_min[step - 1, path])
            ctx["bof_max"] = float(BOF_max[step - 1, path])
            obs_idx += 1
            ctx["index"] = obs_idx

            for ev in step_map[step]:
                if done:
                    break
                st: dict = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception:
                    pass
                for fl in st["flows"]:
                    cf = fl["v"] * disc
                    ctx["total_cf"] += cf
                    ctx["total_cf_raw"] += fl["v"]
                    if record and fl["v"] != 0:
                        key = f"{ctx['t']:.6f}|{fl['lbl']}"
                        if key not in flux_map:
                            flux_map[key] = {"t": ctx["t"], "lbl": fl["lbl"], "n": 0, "sum": 0.0, "pv": 0.0}
                        flux_map[key]["n"] += 1
                        flux_map[key]["sum"] += fl["v"]
                        flux_map[key]["pv"] += cf
                if st["done"]:
                    done = True
                    ctx["done"] = True
                    if stop_times_out is not None:
                        stop_times_out.append(ctx["t"])

        if not done and mat_events:
            if df_arr is None:
                disc = math.exp(-r_eff * ts * dt)
            else:
                disc = df_arr[ts, path] if df_arr.ndim == 2 else df_arr[ts]
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[ts, :, path])
            ctx["s_min"] = list(S_min[ts - 1, :, path])
            ctx["s_max"] = list(S_max[ts - 1, :, path])
            ctx["realvol"] = math.sqrt(SY * cum_sq_ret[ts - 1, path] / ts)
            ctx["t"] = ts * dt
            ctx["wof_min"] = float(WOF_min[ts - 1, path])
            ctx["bof_max"] = float(BOF_max[ts - 1, path])
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception:
                    pass
                for fl in st["flows"]:
                    cf = fl["v"] * disc
                    ctx["total_cf"] += cf
                    ctx["total_cf_raw"] += fl["v"]
                    if record and fl["v"] != 0:
                        key = f"{ctx['t']:.6f}|{fl['lbl']}"
                        if key not in flux_map:
                            flux_map[key] = {"t": ctx["t"], "lbl": fl["lbl"], "n": 0, "sum": 0.0, "pv": 0.0}
                        flux_map[key]["n"] += 1
                        flux_map[key]["sum"] += fl["v"]
                        flux_map[key]["pv"] += cf
                if st["done"]:
                    done = True

        payoffs.append(ctx["total_cf"])
        payoffs_raw.append(ctx["total_cf_raw"])
        if stop_times_out is not None and not ctx["done"]:
            stop_times_out.append(ts * dt)

    return payoffs, payoffs_raw


def _eval_paths_detailed(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                          dt: float, r_eff: float, user_params: dict,
                          step_map: dict, mat_events: list) -> dict:
    """Like _eval_paths but returns per-path outcome classification."""
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    WOF_min = np.minimum.accumulate(WOF, axis=0)
    BOF_max = np.maximum.accumulate(BOF, axis=0)
    S_min = np.minimum.accumulate(S[1:], axis=0)
    S_max = np.maximum.accumulate(S[1:], axis=0)
    WOF_full = np.vstack([np.ones((1, N)), WOF])
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)

    obs_steps = sorted(step_map.keys())
    obs_times = sorted({step * dt for step in obs_steps})

    payoffs: list[float] = []
    outcomes: list[str] = []
    stop_times: list[float | None] = []
    final_wofs: list[float] = []
    event_step_counts: dict[int, int] = {}

    for path in range(N):
        ctx = {
            "spots": [1.0]*n, "accum": 0.0, "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
            "s_min": [1.0]*n, "s_max": [1.0]*n, "s_prev": [1.0]*n, "realvol": 0.0,
            "done": False, "memo": {**user_params}, "total_cf": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)

        done = False
        obs_idx = 0
        stop_t: float | None = None

        for step in obs_steps:
            if done:
                break
            r_intg = r_eff * step * dt
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[step, :, path])
            ctx["s_min"] = list(S_min[step-1, :, path])
            ctx["s_max"] = list(S_max[step-1, :, path])
            ctx["realvol"] = math.sqrt(SY * cum_sq_ret[step-1, path] / step)
            ctx["t"] = step * dt
            ctx["wof_min"] = float(WOF_min[step-1, path])
            ctx["bof_max"] = float(BOF_max[step-1, path])
            obs_idx += 1
            ctx["index"] = obs_idx
            for ev in step_map[step]:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception:
                    pass
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * math.exp(-r_intg)
                if st["done"]:
                    done = True
                    ctx["done"] = True
                    stop_t = ctx["t"]
                    event_step_counts[step] = event_step_counts.get(step, 0) + 1

        if not done and mat_events:
            r_intg = r_eff * ts * dt
            ctx["s_prev"] = list(ctx["spots"])
            ctx["spots"] = list(S[ts, :, path])
            ctx["s_min"] = list(S_min[ts-1, :, path])
            ctx["s_max"] = list(S_max[ts-1, :, path])
            ctx["realvol"] = math.sqrt(SY * cum_sq_ret[ts-1, path] / ts)
            ctx["t"] = ts * dt
            ctx["wof_min"] = float(WOF_min[ts-1, path])
            ctx["bof_max"] = float(BOF_max[ts-1, path])
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception:
                    pass
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * math.exp(-r_intg)
                if st["done"]:
                    done = True

        pf = ctx["total_cf"]
        payoffs.append(pf)
        stop_times.append(stop_t)
        final_wofs.append(float(WOF[ts-1, path]) if ts > 0 else 1.0)

        if stop_t is not None:
            outcomes.append("autocall")
        elif pf < 0.999:
            outcomes.append("ki")
        else:
            outcomes.append("normal")

    return {
        "payoffs": payoffs,
        "outcomes": outcomes,
        "stop_times": stop_times,
        "final_wofs": final_wofs,
        "has_autocall": any(o == "autocall" for o in outcomes),
        "event_step_counts": event_step_counts,
        "obs_times": obs_times,
    }


# ── Main Monte Carlo entry point ────────────────────────────────────

def run_mc(script: CompiledScript,
           underlyings,
           corr_matrix,
           r: float,
           T_max: float,
           N: int,
           model: str = "constant",
           seed: int = 42,
           antithetic: bool = True,
           user_params=None,
           spot_mult=None,
           vol_add=None,
           dr: float = 0.0,
           dt_add: float = 0.0,
           corr_delta=None,
           yield_curve=None,
           sigma_r: float = 0.0,
           a_r: float = 0.0):

    t0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    T = T_max + dt_add
    r_eff = r + dr
    ts = max(1, round(T * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)

    step_map: dict[int, list] = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step = round(d * SY)
                step_map.setdefault(step, []).append(ev)

    # Drop steps beyond the simulation horizon — happens when T_max is capped
    # below the script's event dates (e.g. PRIIPs intermediate-horizon MC).
    step_map = {k: v for k, v in step_map.items() if k <= ts}

    corr = [row[:] for row in corr_matrix]
    if corr_delta:
        ci, cj, delta = corr_delta["ci"], corr_delta["cj"], corr_delta["delta"]
        v = max(-0.999, min(0.999, corr[ci][cj] + delta))
        corr[ci][cj] = corr[cj][ci] = v
    L = cholesky(corr, n)

    use_heston = model == "heston"
    use_lv     = model == "localvol"
    use_sabr   = model == "sabr"

    rng = default_rng(seed)
    # N = number of independent observations (pairs when antithetic, standalone paths otherwise).
    # Antithetic simulates 2*N total paths (N base + N antithetic) and averages each pair;
    # variance reduction comes from the negative correlation between legs, not from fewer draws.
    N_pairs = N

    Z  = rng.standard_normal((ts, n, N_pairs))
    Zv = rng.standard_normal((ts, n, N_pairs)) if use_heston else None
    Za = rng.standard_normal((ts, n, N_pairs)) if use_sabr   else None

    lv_data = None
    if use_lv:
        lv_data = _build_lv_grid(underlyings, r_eff, ts, dt)

    # Discount factor array: yield curve or flat rate
    df_arr = _build_df_arr(yield_curve or [], ts, dt, r_eff)

    # Optional stochastic short rate: a single shared Gaussian factor (ABM when
    # a_r=0, Hull-White when a_r>0 — see _stochastic_rate_paths). sigma_r=0 is
    # the default and skips this entirely — discounting/drift then use the
    # deterministic df_arr/r_eff exactly as before. Each leg (base/anti) gets
    # its own rate path from Z_r/-Z_r, paired the same way as Z/Zv/Za.
    use_stoch_rate = sigma_r > 0
    Z_r = rng.standard_normal((ts, N_pairs)) if use_stoch_rate else None
    if use_stoch_rate:
        fwd = _forward_rate_arr(df_arr, dt)
        r_path_base, df_base = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, Z_r)
        r_path_anti, df_anti = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, -Z_r)
    else:
        r_path_base = r_path_anti = None
        df_base = df_anti = df_arr

    flux_map: dict[str, dict] = {}

    if use_heston:
        S_base = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, Z, Zv, spot_mult, vol_add, r_path_base, Z_r)
    elif use_lv:
        lv_grids, nK, lkm, lkx = lv_data
        S_base = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                               r_eff, L, Z, lv_grids, nK, lkm, lkx, spot_mult, vol_add,
                               r_path_base, Z_r)
    elif use_sabr:
        S_base = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                 r_eff, L, Z, Za, spot_mult, vol_add, r_path_base, Z_r)
    else:
        S_base = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                r_eff, L, Z, spot_mult, vol_add, r_path_base, Z_r)

    stop_times_base: list[float] | None = [] if script.has_stop else None
    payoffs_base, raw_base = _eval_paths(script, S_base, ts, n, N_pairs, dt, r_eff,
                                          user_params, step_map, mat_events, flux_map,
                                          record=True, df_arr=df_base,
                                          stop_times_out=stop_times_base)

    payoffs_anti: list[float] = []
    raw_anti:     list[float] = []
    if antithetic:
        Z_r_anti = -Z_r if use_stoch_rate else None
        if use_heston:
            S_anti = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                       r_eff, L, -Z, -Zv, spot_mult, vol_add, r_path_anti, Z_r_anti)
        elif use_lv:
            S_anti = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, -Z, lv_grids, nK, lkm, lkx, spot_mult, vol_add,
                                   r_path_anti, Z_r_anti)
        elif use_sabr:
            S_anti = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                     r_eff, L, -Z, -Za, spot_mult, vol_add, r_path_anti, Z_r_anti)
        else:
            S_anti = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, -Z, spot_mult, vol_add, r_path_anti, Z_r_anti)
        stop_times_anti: list[float] | None = [] if script.has_stop else None
        payoffs_anti, raw_anti = _eval_paths(script, S_anti, ts, n, N_pairs, dt, r_eff,
                                              user_params, step_map, mat_events, {},
                                              record=False, df_arr=df_anti,
                                              stop_times_out=stop_times_anti)

    # Price: antithetic average of paired paths (lower variance).
    payoffs_avg = [(p1 + p2) / 2 for p1, p2 in zip(payoffs_base, payoffs_anti)] \
                  if payoffs_anti else payoffs_base

    # Individual undiscounted payoffs (both legs) for the distribution histogram.
    raw_all = sorted(raw_base + raw_anti) if raw_anti else sorted(raw_base)

    # Discounted payoffs for statistical quantities (VaR5, median, IC95).
    pv_all  = sorted(payoffs_base + payoffs_anti) if payoffs_anti else sorted(payoffs_base)

    N_eff  = len(payoffs_avg)
    N_hist = len(raw_all)
    price  = sum(payoffs_avg) / N_eff
    payoffs_arr = np.array(payoffs_avg)
    se = math.sqrt(float(np.var(payoffs_arr, ddof=1)) / N_eff)
    mid    = N_hist // 2
    median = (pv_all[mid-1] + pv_all[mid]) / 2 if N_hist % 2 == 0 else pv_all[mid]
    var5   = pv_all[int(N_hist * 0.05)]
    prob_gt100 = sum(1 for p in raw_all if p > 1.0) / N_hist

    # Scale flux PV contributions (base paths) to match antithetically-averaged price.
    base_price = sum(payoffs_base) / N_pairs
    if antithetic and base_price != 0:
        scale = price / base_price
        for d in flux_map.values():
            d["pv"] *= scale

    # Fugit = E[τ] — probability-weighted expected life of the product.
    # Averaged over base + antithetic legs for more stable estimate.
    fugit: float | None = None
    if script.has_stop and stop_times_base:
        all_stop = stop_times_base + (stop_times_anti if antithetic and stop_times_anti else [])
        fugit = round(sum(all_stop) / len(all_stop), 4)

    elapsed = (time.perf_counter() - t0) * 1000

    return {
        "price": round(price, 6),
        "ic95": [round(price - 1.96*se, 6), round(price + 1.96*se, 6)],
        "median": round(median, 6),
        "var5": round(var5, 6),
        "prob_gt100": round(prob_gt100, 6),
        "payoffs": [round(p, 4) for p in raw_all],   # undiscounted, for histogram
        "flux_table": flux_map,
        "elapsed_ms": round(elapsed, 1),
        "n_paths": N,
        "n_eff": N_eff,
        "fugit": fugit,
    }


# ── Greeks ──────────────────────────────────────────────────────────

def compute_greeks(script: CompiledScript, underlyings, corr_matrix,
                   r: float, T: float, N: int, model: str, seed: int,
                   base_price: float, user_params,
                   selected: list | None = None, sigma_r: float = 0.0, a_r: float = 0.0):
    if selected is None:
        selected = ["delta", "gamma", "vega", "theta", "rho"]
    sel = set(selected)
    N_g = max(1000, N // 4)
    greeks: dict = {}

    def price(**kwargs) -> float:
        res = run_mc(script, underlyings, corr_matrix, r, T, N_g, model, seed,
                     antithetic=True, user_params=user_params, sigma_r=sigma_r, a_r=a_r, **kwargs)
        return res["price"]

    n = len(underlyings)

    for i in range(n):
        if "delta" in sel or "gamma" in sel:
            sm_up = [1.0]*n; sm_up[i] = 1.01
            sm_dn = [1.0]*n; sm_dn[i] = 0.99
            pu = price(spot_mult=sm_up)
            pd = price(spot_mult=sm_dn)
            if "delta" in sel:
                greeks[f"delta_{i+1}"] = round((pu - pd) / 0.02, 4)
            if "gamma" in sel:
                sm_gu = [1.0]*n; sm_gu[i] = 1.03
                sm_gd = [1.0]*n; sm_gd[i] = 0.97
                greeks[f"gamma_{i+1}"] = round((price(spot_mult=sm_gu) - 2*base_price + price(spot_mult=sm_gd)) / 0.0009, 4)

    if "vega" in sel:
        for i in range(n):
            va_up = [0.0]*n; va_up[i] = 0.01
            va_dn = [0.0]*n; va_dn[i] = -0.01
            greeks[f"vega_{i+1}"] = round((price(vol_add=va_up) - price(vol_add=va_dn)) / 0.02, 4)

    if "theta" in sel:
        greeks["theta"] = round(price(dt_add=1/365) - base_price, 4)

    if "rho" in sel:
        greeks["rho"] = round((price(dr=0.01) - price(dr=-0.01)) / 0.02, 4)

    if "corr" in sel and n > 1:
        for ci in range(n):
            for cj in range(ci+1, n):
                cd = {"ci": ci, "cj": cj, "delta": 0.05}
                greeks[f"corr_{ci+1}_{cj+1}"] = round((price(corr_delta=cd) - base_price) / 0.05, 4)

    return greeks


# ── Analytics: Payoff Profile ───────────────────────────────────────

def run_payoff_profile(script: CompiledScript, underlyings, corr_matrix,
                        r: float, T_max: float, user_params=None, n_pts: int = 61) -> dict:
    """Sweep spot levels 40%–200% and evaluate payoff quasi-deterministically."""
    user_params = user_params or {}
    n = len(underlyings)
    # Near-zero vol → near-deterministic paths
    min_uls = [{**u, "sigma": 0.001, "alpha": 0.001, "v0": 1e-6, "xi": 0.001}
               for u in underlyings]
    no_corr = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    levels = [0.40 + i * 1.60 / (n_pts - 1) for i in range(n_pts)]

    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    L = cholesky(no_corr, n)

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(round(d*SY), []).append(ev)

    N_p = 10
    rng = default_rng(42)
    Z = rng.standard_normal((ts, n, N_p)) * 0.0001  # near-zero noise

    payoffs = []
    for x in levels:
        S = _simulate_gbm(ts, n, N_p, dt, sq_dt, min_uls, r, L, Z, spot_mult=[x]*n)
        pfs, _ = _eval_paths(script, S, ts, n, N_p, dt, r, user_params,
                              step_map, mat_events, {}, record=False)
        payoffs.append(round(sum(pfs) / N_p * 100, 3))

    return {
        "levels": [round(x * 100, 1) for x in levels],
        "payoffs": payoffs,
    }


# ── Analytics: MC Sample Paths ──────────────────────────────────────

def run_mc_paths(script: CompiledScript, underlyings, corr_matrix,
                  r: float, T_max: float, N_display: int = 50,
                  N_stat: int = 500, model: str = "constant",
                  seed: int = 42, user_params=None) -> dict:
    """Run MC and return 50 sample paths colored by outcome."""
    user_params = user_params or {}
    n = len(underlyings)
    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(round(d*SY), []).append(ev)

    L = cholesky(corr_matrix, n)
    rng = default_rng(seed)
    Z = rng.standard_normal((ts, n, N_stat))

    if model == "heston":
        Zv = rng.standard_normal((ts, n, N_stat))
        S = _simulate_heston(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, Zv)
    elif model == "localvol":
        lv_data = _build_lv_grid(underlyings, r, ts, dt)
        lv_grids, nK, lkm, lkx = lv_data
        S = _simulate_lv(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, lv_grids, nK, lkm, lkx)
    elif model == "sabr":
        Za = rng.standard_normal((ts, n, N_stat))
        S = _simulate_sabr(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, Za)
    else:
        S = _simulate_gbm(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z)

    det = _eval_paths_detailed(script, S, ts, n, N_stat, dt, r, user_params, step_map, mat_events)

    # Downsample time steps: take every 2 weeks for display
    stride = max(1, ts // 60)
    disp_steps = list(range(0, ts + 1, stride))
    if ts not in disp_steps:
        disp_steps.append(ts)
    full_times = [round(s * dt, 4) for s in disp_steps]

    path_data = []
    for pi in range(min(N_display, N_stat)):
        stop_t = det["stop_times"][pi]
        if stop_t is not None:
            # Truncate at recall date
            stop_step = round(stop_t * SY)
            cut = [s for s in disp_steps if s <= stop_step]
            if not cut or cut[-1] != stop_step:
                cut.append(stop_step)
            p_times = [round(s * dt, 4) for s in cut]
            p_wof   = [round(float(S[min(s, ts), :, pi].min()), 4) for s in cut]
        else:
            p_times = full_times
            p_wof   = [round(float(S[s, :, pi].min()), 4) for s in disp_steps]
        path_data.append({
            "times": p_times,
            "wof":   p_wof,
            "outcome": det["outcomes"][pi],
        })

    return {
        "path_data": path_data,
        "autocall_count": sum(1 for o in det["outcomes"] if o == "autocall"),
        "ki_count": sum(1 for o in det["outcomes"] if o == "ki"),
        "normal_count": sum(1 for o in det["outcomes"] if o == "normal"),
        "total": N_stat,
        "has_autocall": det["has_autocall"],
        "T_max": T_max,
        "user_params": user_params,
    }


# ── Analytics: Probability Analysis ────────────────────────────────

def run_mc_proba(script: CompiledScript, underlyings, corr_matrix,
                  r: float, T_max: float, N: int = 5000,
                  model: str = "constant", seed: int = 42, user_params=None) -> dict:
    """Full MC run returning probability breakdown."""
    user_params = user_params or {}
    n = len(underlyings)
    N_p = min(10000, max(2000, N))
    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(round(d*SY), []).append(ev)

    L = cholesky(corr_matrix, n)
    rng = default_rng(seed)
    Z = rng.standard_normal((ts, n, N_p))

    if model == "heston":
        Zv = rng.standard_normal((ts, n, N_p))
        S = _simulate_heston(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, Zv)
    elif model == "localvol":
        lv_data = _build_lv_grid(underlyings, r, ts, dt)
        lv_grids, nK, lkm, lkx = lv_data
        S = _simulate_lv(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, lv_grids, nK, lkm, lkx)
    elif model == "sabr":
        Za = rng.standard_normal((ts, n, N_p))
        S = _simulate_sabr(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, Za)
    else:
        S = _simulate_gbm(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z)

    det = _eval_paths_detailed(script, S, ts, n, N_p, dt, r, user_params, step_map, mat_events)

    ac = sum(1 for o in det["outcomes"] if o == "autocall")
    ki = sum(1 for o in det["outcomes"] if o == "ki")
    nm = sum(1 for o in det["outcomes"] if o == "normal")

    event_counts = {round(step * dt, 4): cnt for step, cnt in det["event_step_counts"].items()}

    stop_ts = [st for st in det["stop_times"] if st is not None]
    expected_life = (sum(stop_ts) + (ki + nm) * T_max) / N_p

    ps = sorted(det["payoffs"])

    def perc(p: float) -> float:
        return round(ps[int(N_p * p)] * 100, 2)

    return {
        "has_autocall": det["has_autocall"],
        "autocall_count": ac,
        "ki_count": ki,
        "normal_count": nm,
        "total": N_p,
        "obs_times": sorted(det["obs_times"]),
        "event_counts": event_counts,
        "expected_life": round(expected_life, 3),
        "final_wofs": [round(w * 100, 2) for w in det["final_wofs"]],
        "price": round(sum(det["payoffs"]) / N_p, 6),
        "percentiles": {
            "p5":  perc(0.05),
            "p25": perc(0.25),
            "p75": perc(0.75),
            "p95": perc(0.95),
        },
    }


# ── Analytics: Mark-to-Future (nested Monte Carlo) ──────────────────
#
# Mark-to-Future answers: "what is the model-implied distribution of mark-to-model
# values of this product at some future date t0, consistent with no-arbitrage pricing
# today?" It is NOT an economic forecast: market parameters stay frozen at their
# current (t=0) values, and the whole exercise runs under the risk-neutral measure.
#
# For each MTM date t0, in two nested steps:
#   1. Outer step — N_outer risk-neutral GBM scenarios are simulated from t=0 to t0.
#      The outer step always uses plain GBM regardless of the inner pricing model:
#      its only job is to propose plausible future market states; the inner step
#      re-prices under the calibrated dynamics.
#   2. Inner step — for each outer scenario, the *residual* product (the script
#      re-anchored at t0, with remaining maturity T_max - t0) is re-priced with
#      N_inner inner Monte Carlo paths under the selected model, starting from the
#      outer scenario's spot levels and inheriting its running worst-of/best-of state
#      (needed because barriers such as knock-in monitor continuously from t=0, not
#      just from t0 onward).
#   3. The outer scenario's mark-to-future value = mean of its N_inner inner PVs.
# The distribution of these N_outer values at t0 is the MTF "fan" at that date.

def build_mtf_dates(T_max: float, n_dates: int) -> list[float]:
    """Evenly-spaced MTM date grid. The last date is T_max minus one week, which
    avoids re-pricing a degenerate near-zero-maturity residual product."""
    t_last = round(T_max - 1 / SY, 6)
    return [round(t_last * (i + 1) / n_dates, 4) for i in range(n_dates)]


def _shift_events_for_mtf(events: list[CompiledEvent], t0: float) -> list[CompiledEvent]:
    """Re-anchor a script's events at t0 for residual pricing: AT event dates at or
    before t0 are already resolved by the outer scenario and dropped; remaining dates
    are shifted by -t0. AT_MATURITY is left untouched — it always fires at the end of
    the residual horizon, whatever that horizon is."""
    eps = 1e-9
    shifted = []
    for ev in events:
        if ev.type != "AT":
            shifted.append(ev)
            continue
        future_dates = [round(d - t0, 6) for d in ev.dates if d > t0 + eps]
        if future_dates:
            shifted.append(CompiledEvent(type=ev.type, dates=future_dates, fn=ev.fn))
    return shifted


def _simulate_mtf_outer(underlyings, corr_matrix, r: float, mtm_dates: list[float],
                         N: int, seed: int):
    """Outer scenario generator: N correlated GBM paths from t=0 to the last MTM date.
    Returns the full spot tensor plus the running worst-of-min / best-of-max series
    (needed to seed continuously-monitored barriers in the inner re-pricing)."""
    n = len(underlyings)
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    ts = max(1, round(mtm_dates[-1] * SY))
    L = cholesky(corr_matrix, n)
    Z = default_rng(seed).standard_normal((ts, n, N))
    S = _simulate_gbm(ts, n, N, dt, sq_dt, underlyings, r, L, Z)
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    wof_min_run = np.minimum.accumulate(WOF, axis=0)
    bof_max_run = np.maximum.accumulate(BOF, axis=0)
    return S, wof_min_run, bof_max_run


def _mtf_date_stats(pvs: np.ndarray, p0: float) -> dict:
    """Distribution diagnostics for one MTM date (pvs in % of notional)."""
    srt = np.sort(pvs)
    n = len(srt)

    def q(p: float) -> float:
        return float(srt[min(n - 1, max(0, int(p * n)))])

    mean = float(pvs.mean())
    return {
        "mean": mean, "std": float(pvs.std(ddof=0)),
        "p01": q(0.01), "p05": q(0.05), "p25": q(0.25), "p50": q(0.50),
        "p75": q(0.75), "p95": q(0.95), "p99": q(0.99),
        "p_above_100": float((pvs > 100).mean() * 100),
        "p_above_p0":  float((pvs >= p0).mean() * 100),
        "e_mtm": mean,
        "e_upside": float(np.maximum(pvs - 100, 0).mean()),
    }


def run_mark_to_future(script: CompiledScript,
                        underlyings,
                        corr_matrix,
                        r: float,
                        T_max: float,
                        main_price: float,
                        model: str = "constant",
                        n_outer: int = 200,
                        n_inner: int = 500,
                        n_dates: int = 5,
                        seed: int = 42,
                        user_params=None) -> dict:
    """Run the full nested Monte Carlo Mark-to-Future analysis (see module section
    docstring above). main_price is the t=0 fair price (% of notional); it is only
    used as the threshold for the P(MTM >= P0) diagnostic.

    Inner simulation is processed in chunks of outer scenarios (MTF_MAX_BATCH paths
    at a time) to bound peak memory regardless of how large n_outer * n_inner gets."""
    t_run0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    mtm_dates = build_mtf_dates(T_max, n_dates)

    S_outer, wof_min_run, bof_max_run = _simulate_mtf_outer(
        underlyings, corr_matrix, r, mtm_dates, n_outer, seed
    )

    use_heston = model == "heston"
    use_lv     = model == "localvol"
    use_sabr   = model == "sabr"
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    L = cholesky(corr_matrix, n)
    outer_per_chunk = max(1, MTF_MAX_BATCH // n_inner)

    results = []
    for k, t0 in enumerate(mtm_dates):
        step_k = round(t0 * SY)
        spot_k    = S_outer[step_k]            # (n, N_outer) — spot at this MTM date
        wof_min_k = wof_min_run[step_k - 1]     # (N_outer,)   — running min up to t0
        bof_max_k = bof_max_run[step_k - 1]     # (N_outer,)   — running max up to t0

        residual_events = _shift_events_for_mtf(script.events, t0)
        residual_script = CompiledScript(events=residual_events, init_fn=script.init_fn,
                                          params=script.params, constats=script.constats)
        T_eff = max(1 / SY, round(T_max - t0, 6))
        ts_eff = max(1, round(T_eff * SY))

        step_map: dict[int, list] = {}
        mat_events = []
        for ev in residual_events:
            if ev.type == "AT_MATURITY":
                mat_events.append(ev)
            else:
                for d in ev.dates:
                    step_map.setdefault(round(d * SY), []).append(ev)

        lv_grids = nK = lkm = lkx = None
        if use_lv:
            lv_grids, nK, lkm, lkx = _build_lv_grid(underlyings, r, ts_eff, dt)

        scenario_pvs = np.empty(n_outer, dtype=np.float64)

        # Chunked inner MC: bounds memory while still batching many outer scenarios
        # into one vectorized simulate() call per chunk.
        for start in range(0, n_outer, outer_per_chunk):
            end = min(n_outer, start + outer_per_chunk)
            n_chunk = end - start
            N_chunk = n_chunk * n_inner

            spot_chunk    = np.repeat(spot_k[:, start:end], n_inner, axis=1)   # (n, N_chunk)
            wof_min_chunk = np.repeat(wof_min_k[start:end], n_inner)           # (N_chunk,)
            bof_max_chunk = np.repeat(bof_max_k[start:end], n_inner)           # (N_chunk,)

            rng = default_rng(seed + 1_000_003 * (k + 1) + start)
            Z = rng.standard_normal((ts_eff, n, N_chunk))

            if use_heston:
                Zv = rng.standard_normal((ts_eff, n, N_chunk))
                S_in = _simulate_heston(ts_eff, n, N_chunk, dt, sq_dt, underlyings, r, L,
                                         Z, Zv, spot_chunk)
            elif use_lv:
                S_in = _simulate_lv(ts_eff, n, N_chunk, dt, sq_dt, underlyings, r, L, Z,
                                     lv_grids, nK, lkm, lkx, spot_chunk)
            elif use_sabr:
                Za = rng.standard_normal((ts_eff, n, N_chunk))
                S_in = _simulate_sabr(ts_eff, n, N_chunk, dt, sq_dt, underlyings, r, L,
                                       Z, Za, spot_chunk)
            else:
                S_in = _simulate_gbm(ts_eff, n, N_chunk, dt, sq_dt, underlyings, r, L,
                                      Z, spot_chunk)

            payoffs, _ = _eval_paths(
                residual_script, S_in, ts_eff, n, N_chunk, dt, r, user_params,
                step_map, mat_events, {}, record=False,
                wof_min_init=wof_min_chunk, bof_max_init=bof_max_chunk,
            )

            # Each outer scenario's MTF value = mean of its N_inner inner PVs (% notional).
            scenario_pvs[start:end] = np.array(payoffs).reshape(n_chunk, n_inner).mean(axis=1) * 100

        results.append({
            "t": t0,
            "pvs": [round(float(v), 4) for v in scenario_pvs],
            "stats": _mtf_date_stats(scenario_pvs, main_price),
        })

    return {
        "main_price": round(main_price, 4),
        "n_outer": n_outer,
        "n_inner": n_inner,
        "n_dates": n_dates,
        "results": results,
        "elapsed_ms": round((time.perf_counter() - t_run0) * 1000, 1),
    }


# ── Historical backtest ─────────────────────────────────────────────

def eval_script_on_history(compiled: CompiledScript, dates: list[str],
                            prices_by_ticker: dict, start_idx: int,
                            T_max: float, user_params: dict,
                            tickers: list[str], r: float = 0.03) -> dict | None:
    """Replay PayScript using actual historical close prices."""
    SY_H = 252
    n = len(tickers)

    step_map: dict = {}
    mat_events = []
    for ev in compiled.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(round(d * SY_H), []).append(ev)

    ref: dict = {}
    for tk in tickers:
        px = prices_by_ticker.get(tk, [])
        if px and start_idx < len(px) and px[start_idx] > 0:
            ref[tk] = px[start_idx]
    if not ref:
        return None

    full_params = {p.name: p.stored_val for p in compiled.params}
    full_params.update(user_params)

    ctx = {
        "spots": [1.0]*n, "accum": 0.0, "index": 0,
        "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
        "done": False, "memo": full_params, "total_cf": 0.0,
    }
    if compiled.init_fn:
        compiled.init_fn(ctx)

    cfs: list[dict] = []
    done = False
    obs_idx = 0
    wof_run = 1.0
    T_actual = T_max

    for step in sorted(step_map.keys()):
        hi = start_idx + step
        if hi >= len(dates):
            break
        spots = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            spots.append(px[hi] / r0 if r0 > 0 and hi < len(px) else 1.0)
        wof_run = min(wof_run, min(spots))
        t_y = step / SY_H
        ctx.update({"spots": spots, "t": t_y, "wof_min": wof_run,
                    "bof_max": max(spots), "index": obs_idx + 1})
        obs_idx += 1
        for ev in step_map[step]:
            if done:
                break
            st = {"flows": [], "done": False}
            try:
                ev.fn(ctx, st)
            except Exception:
                pass
            for fl in st["flows"]:
                cfs.append({"t": t_y, "cf": fl["v"]})
            if st["done"]:
                done = True
                ctx["done"] = True
                T_actual = t_y

    if not done and mat_events:
        ms = round(T_max * SY_H)
        mhi = start_idx + ms
        if mhi < len(dates):
            spots = []
            for tk in tickers:
                px = prices_by_ticker.get(tk, [])
                r0 = ref.get(tk, 0)
                spots.append(px[mhi] / r0 if r0 > 0 and mhi < len(px) else 1.0)
            wof_run = min(wof_run, min(spots) if spots else 1.0)
            ctx.update({"spots": spots or [1.0]*n, "t": T_max,
                        "wof_min": wof_run, "bof_max": max(spots) if spots else 1.0})
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception:
                    pass
                for fl in st["flows"]:
                    cfs.append({"t": T_max, "cf": fl["v"]})
                if st["done"]:
                    done = True

    return {
        "cash_flows": cfs,
        "early_recall": T_actual < T_max,
        "T_actual": T_actual,
    }


def compute_irr(cash_flows: list[dict], guess: float = 0.1,
                tol: float = 1e-6, max_iter: int = 60) -> float | None:
    """Newton-Raphson IRR solver. cash_flows = list of {t: years, cf: amount}."""
    def npv(r_: float) -> float:
        return sum(cf["cf"] / (1 + r_)**cf["t"] for cf in cash_flows)

    def dnpv(r_: float) -> float:
        return -sum(cf["t"] * cf["cf"] / (1 + r_)**(cf["t"] + 1) for cf in cash_flows)

    r = guess
    for _ in range(max_iter):
        f, df = npv(r), dnpv(r)
        if abs(df) < 1e-12:
            break
        r_new = max(-0.99, min(r - f/df, 10.0))
        if abs(r_new - r) < tol:
            r = r_new
            break
        r = r_new

    return r if math.isfinite(r) and abs(npv(r)) < 1e-3 else None
