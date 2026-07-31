"""
Monte Carlo engine — vectorized path simulation + per-path PayScript evaluation.

Models: constant (GBM), heston (QE), sabr (ATM vol), localvol (Dupire),
lsv (Local-Stochastic Vol — Dupire local vol target + Heston-QE stochastic
variance, recalibrated each step via a leverage function; see _simulate_lsv).
Variance reduction: antithetic variates.
Greeks: CRN bump-and-reprice.
Analytics: payoff profile, MC paths visualization, probability analysis, historical backtest.
"""
from __future__ import annotations
import bisect
import math
import time
from typing import NamedTuple
import numpy as np
from numpy.random import default_rng
from scipy.special import erfc
from .parser import CompiledScript, CompiledEvent

SY = 52       # weekly steps per year
PSI_C = 1.5   # Heston QE switching threshold
MTF_MAX_BATCH = 20_000   # cap simulated paths per inner Mark-to-Future chunk (memory bound)


# ── Cholesky decomposition ──────────────────────────────────────────

def cholesky(corr: list[list[float]], n: int) -> np.ndarray:
    C = np.array(corr, dtype=np.float64)
    if not np.allclose(np.diag(C), 1.0, atol=1e-6):
        raise ValueError("Matrice de corrélation invalide : la diagonale doit valoir 1.")
    if not np.allclose(C, C.T, atol=1e-6):
        raise ValueError("Matrice de corrélation invalide : elle doit être symétrique.")
    if np.abs(C).max() > 1.0 + 1e-9:
        raise ValueError("Matrice de corrélation invalide : les coefficients doivent rester dans [-1, 1].")
    eigvals = np.linalg.eigvalsh(C)
    if eigvals.min() < 0:
        C += (-eigvals.min() + 1e-8) * np.eye(n)
        # The jitter pushes the diagonal above 1 (silently inflating every vol
        # by sqrt(1+eps)) — renormalize back to a unit-diagonal correlation.
        d = np.sqrt(np.diag(C))
        C = C / np.outer(d, d)
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


def _heston_qe_vectorized(V: np.ndarray, kappa: float, theta: float, xi: float,
                           dt: float, Zv: np.ndarray) -> np.ndarray:
    """Vectorized (across paths) equivalent of _heston_qe_scalar above — the
    exact same Andersen (2007) QE algorithm (quadratic branch when psi<=PSI_C,
    exponential branch otherwise), just elementwise over V/Zv arrays instead
    of a per-path Python loop. Used by both _simulate_heston and _simulate_lsv
    (which need the whole cross-section of variance at once — see their
    docstrings) instead of one path at a time.

    Must stay algorithmically identical to _heston_qe_scalar — any change to
    one should be mirrored in the other. test_heston_qe_vectorized_matches_scalar
    cross-checks the two against each other on shared random draws.

    Both branches are computed for every path unconditionally (the numpy way
    to vectorize an if/else), then selected via the final np.where — the
    unselected branch can harmlessly divide by ~0 for some paths (RuntimeWarning,
    not a bug: that value is never used), hence the errstate suppression."""
    with np.errstate(divide='ignore', invalid='ignore'):
        ek = math.exp(-kappa * dt)
        xi2 = xi * xi
        m_v = theta + (V - theta) * ek
        s2 = V * xi2 * ek / kappa * (1 - ek) + theta * xi2 / (2 * kappa) * (1 - ek) ** 2
        s2 = np.maximum(s2, 0.0)
        m_v_safe = np.where(m_v > 1e-10, m_v, 1.0)
        psi = np.where(m_v > 1e-10, s2 / (m_v_safe * m_v_safe), 2.0)

        # Quadratic branch (psi <= PSI_C)
        inv = 2.0 / np.maximum(psi, 1e-12)
        b2 = inv - 1 + np.sqrt(np.maximum(0.0, inv * (inv - 1)))
        a = m_v / (1 + b2)
        quad = np.maximum(0.0, a * (np.sqrt(b2) + Zv) ** 2)

        # Exponential branch (psi > PSI_C)
        U = 0.5 * erfc(-Zv / math.sqrt(2))
        p_exp = (psi - 1) / (psi + 1)
        beta = np.where(m_v > 1e-10, (1 - p_exp) / m_v_safe, 1.0)
        exp_branch = np.where(
            U <= p_exp,
            0.0,
            np.maximum(0.0, np.log(np.maximum(1e-14, (1 - p_exp) / np.maximum(1e-14, 1 - U))) / beta),
        )

        return np.where(psi <= PSI_C, quad, exp_branch)


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


def _build_lv_grid(underlyings, rates: "_RateTerm", ts: int, dt: float, nK: int = 50):
    """Precompute local vol grid (ts, nK) for each underlying asset.

    Takes the run's rate term rather than a scalar so the Black-Scholes prices
    the Dupire inversion is built on are discounted at the same curve that
    discounts the payoff — the calibration is the third place a rate enters a
    pricing run, and it used to be the one nobody wired to the curve."""
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
            # Zero rate to this maturity — the right discount for a call
            # expiring at T_s. Falls back to the scalar when there is no curve.
            r_s = rates.r_flat if rates.zero is None else float(rates.zero[step + 1])
            for ki, K in enumerate(Ks):
                lv = _dupire_vol(K, T_s, sig0, skew, curv, r_s, q)
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
                  r_path=None, Z_r=None, vol_out=None) -> np.ndarray:
    """Vectorized GBM — all paths at once via cumsum. Returns (ts+1, n, N).

    r_path (ts, N) and Z_r (ts, N) are the optional stochastic-rate level and raw
    shock from _stochastic_rate_paths — both None (default) reproduces the exact
    flat/curve-rate behavior. r_path overrides r_eff in the drift; Z_r re-blends
    each asset's own correlated Brownian via its rho_rS (_blend_rate_factor).

    vol_out (ts, n, N), when provided, is filled with the effective diffusion
    vol applied on each step — consumed by _bridge_extrema for continuous
    barrier monitoring. Same contract on every simulator below."""
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
        if vol_out is not None:
            vol_out[:, i, :] = sig
        z_i = _blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0)) if Z_r is not None else Zc[:, i, :]
        q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
        drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5 * sig * sig
        log_ret = drift * dt + sig * sq_dt * z_i
        S[1:, i, :] = S[0, i] * np.exp(np.cumsum(log_ret, axis=0))

    return S


def _simulate_heston(ts: int, n: int, N: int, dt: float, sq_dt: float,
                     underlyings, r_eff: float, L: np.ndarray,
                     Z: np.ndarray, Zv: np.ndarray,
                     spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                     vol_out=None) -> np.ndarray:
    """Vectorized Heston QE simulation (Andersen 2007) — step-major, every
    path advanced together per step via numpy array ops (same structure as
    _simulate_lv/_simulate_lsv), using _heston_qe_vectorized for the QE draw
    instead of a per-path Python loop calling _heston_qe_scalar N times.

    Formulas are UNCHANGED from the original per-path implementation — this
    is a vectorization of the same math, not a new model. In particular the
    martingale-preserving construction is preserved verbatim: V_bar (not
    V_next) feeds the drift/vol, and the Andersen correlation correction term
    `corr_term = rho/xi * (V_next - V_old - kappa*(theta-V_bar)*dt)` supplies
    the rho*dW_V leg of the spot's diffusion so that, combined with the
    independent rhop*sv*dZ_perp leg, E[exp(...)] integrates to the correct
    V_bar*dt total variance (see the original per-path code, preserved in
    git history, for the full derivation). Regression-tested against a literal
    per-path reference loop in test_heston_vectorized_matches_reference_loop.

    r_path/Z_r: see _simulate_gbm. The rho_rS blend is applied to cZ[i] (the
    asset's inter-asset-correlated Brownian) before it feeds into both the
    variance process (zv) and the spot's own perp component (z_S_perp) — the
    rate shock therefore propagates into variance too via that shared factor,
    same ordering as the simpler models."""
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts * N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    V = [np.full(N, u.get("v0", 0.04), dtype=np.float64) for u in underlyings]

    for step in range(ts):
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            rh  = u.get("rho_h", -0.70)
            kap = u.get("kappa", 2.0)
            th  = u.get("theta", 0.04)
            xi  = u.get("xi", 0.35)
            rhop = math.sqrt(max(0.0, 1.0 - rh*rh))

            cz_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]

            # Variance BM: correlated with spot via rho_h
            z_perp_var = Zv[step, i, :]             # independent component
            zv = rh * cz_i + rhop * z_perp_var      # full variance Brownian W_V

            V_old  = V[i]
            V_next = _heston_qe_vectorized(V_old, kap, th, xi, dt, zv)
            V_bar  = (V_old + V_next) / 2
            V[i]   = V_next

            sig_add = vol_add[i] if vol_add is not None else 0.0
            sv = np.sqrt(np.maximum(0.0, V_bar)) + sig_add
            if vol_out is not None:
                vol_out[step, i, :] = sv

            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sv
            # `vol_add` bumps only the independent spot-volatility leg.  The
            # correlated Heston leg remains driven by sqrt(V_bar), so the
            # matching quadratic variation is rho^2*V_bar +
            # (1-rho^2)*sv^2.  Using -0.5*V_bar after changing `sv` breaks the
            # discounted-spot martingale and creates vega on PAY S[1].
            bumped_variance = rh*rh * V_bar + rhop*rhop * sv*sv
            drift = (r_term + u.get("ccyh", 0.0) - u.get("q", 0.02)
                     - q_adj - 0.5 * bumped_variance)

            # Andersen (2007) spot update — see docstring for the martingale
            # derivation, unchanged from the original per-path formula.
            z_S_perp  = rhop * cz_i - rh * z_perp_var
            corr_term = rh / xi * (V_next - V_old - kap * (th - V_bar) * dt)
            S[step+1, i, :] = S[step, i, :] * np.exp(
                drift*dt + corr_term + rhop * sv * sq_dt * z_S_perp
            )

    return S


def _simulate_sabr(ts: int, n: int, N: int, dt: float, sq_dt: float,
                   underlyings, r_eff: float, L: np.ndarray,
                   Z: np.ndarray, Za: np.ndarray,
                   spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                   vol_out=None) -> np.ndarray:
    """Vectorized SABR SDE simulation (Euler-Maruyama) — step-major, every
    path advanced together per step via numpy array ops, same structure as
    _simulate_heston above. Formulas UNCHANGED from the original per-path
    loop, including using alpha_old (not alpha_bar) for the CEV effective vol
    to avoid the correlation-with-z_S martingale bias documented inline below
    — see test_sabr_mc_matches_hagan_formula and
    test_sabr_vectorized_matches_reference_loop for the correctness guards.

    dF = α*F^β*dW,  dα = ν*α*dZ,  corr(dW,dZ)=ρ per underlying.
    Za: (ts, n, N) independent noise for vol Brownians.
    r_path/Z_r: see _simulate_gbm — rho_rS blend applied to cZ[i] before it
    feeds into both the spot driver z_S and the vol-of-vol correlation z_a.
    """
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts * N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    alpha = [np.full(N, u.get("alpha", 0.20), dtype=np.float64) for u in underlyings]

    for step in range(ts):
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            rho_s = u.get("rho", -0.30)         # SABR rho (spot–vol corr)
            nu    = u.get("nu", 0.40)
            beta  = u.get("beta", 0.50)

            z_S = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
            # Vol Brownian correlated with spot via SABR rho
            za_raw = Za[step, i, :]
            z_a = rho_s * z_S + math.sqrt(max(0.0, 1.0 - rho_s**2)) * za_raw

            # Lognormal SDE for stochastic vol α
            alpha_old = alpha[i]
            alpha_new = alpha_old * np.exp(nu * sq_dt * z_a - 0.5 * nu**2 * dt)

            # CEV effective vol: σ = α_old * S^(β−1)
            # Use alpha_old (not alpha_bar) to avoid correlation bias with z_S.
            # alpha_bar = f(z_a) = f(rho*z_S + ...) is correlated with z_S,
            # which would break E[exp(sig*z_S*√dt)] = exp(½sig²dt) martingale property.
            S_c = np.maximum(S[step, i, :], 1e-8)
            if abs(beta - 1.0) < 1e-4:
                sig = alpha_old.copy()
            else:
                sig = alpha_old * (S_c ** (beta - 1.0))

            if vol_add is not None:
                sig = sig + vol_add[i]
            sig = np.clip(sig, 0.001, 3.0)
            if vol_out is not None:
                vol_out[step, i, :] = sig

            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
            drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5 * sig**2
            S[step + 1, i, :] = S_c * np.exp(drift * dt + sig * sq_dt * z_S)
            alpha[i] = alpha_new

    return S


def _simulate_lv(ts: int, n: int, N: int, dt: float, sq_dt: float,
                  underlyings, r_eff: float, L: np.ndarray, Z: np.ndarray,
                  lv_grids, nK: int, logKmin: float, logKmax: float,
                  spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                  vol_out=None) -> np.ndarray:
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
            if vol_out is not None:
                vol_out[step, i, :] = lvs
            z_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * lvs
            drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5*lvs**2
            S[step+1, i, :] = S_c * np.exp(drift*dt + lvs*sq_dt*z_i)

    return S


# Minimum paths a log-moneyness bucket needs before its E[V|S] estimate is
# trusted — see _simulate_lsv. Below this, the bucket average is too noisy
# (especially early time steps, before paths have dispersed), so we fall
# back to the step's unconditional mean variance instead.
_LSV_MIN_BUCKET_PATHS = 30


def _simulate_lsv(ts: int, n: int, N: int, dt: float, sq_dt: float,
                   underlyings, r_eff: float, L: np.ndarray, Z: np.ndarray, Zv: np.ndarray,
                   lv_grids, nK: int, logKmin: float, logKmax: float,
                   spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                   vol_out=None) -> np.ndarray:
    """Local-Stochastic Vol (Guyon & Henry-Labordère) — a stochastic variance
    process (the same Heston QE dynamics as _simulate_heston, but vectorized
    via _heston_qe_vectorized) whose effect on the spot is rescaled at every
    time step by a "leverage" function so that the MARGINAL distribution of
    the spot always matches the Dupire local vol target (lv_grids, the exact
    same grid _simulate_lv calibrates to) — while the PATH dynamics (forward
    skew) behave like a genuine stochastic-vol model instead of local vol's
    unrealistically flat forward skew. This is the reason to prefer LSV over
    plain local vol for barrier/autocall-type payoffs, which are sensitive
    to exactly that forward skew.

    Built as an extension of _simulate_lv (step-major, vectorized across all
    N paths at once) rather than _simulate_heston (per-path Python loop),
    because the leverage function needs the WHOLE cross-section of paths at
    a given time step simultaneously — see the particle-method bucketing
    below — which only the step-major structure gives for free.

    Particle method, at each (step, underlying):
      1. Bucket the current cross-section (S, V_old) into the same nK
         log-moneyness bins as lv_grids, and average V_old within each bucket
         -> an estimate of the conditional expectation E[V|S] (the
         "particles" of the method). Buckets with fewer than
         _LSV_MIN_BUCKET_PATHS paths fall back to the step's unconditional
         mean V_old instead of a noisy per-bucket average. V_old (the
         variance already known at the start of this step), not V_next or an
         average of the two — see the inline comment where it's used for why
         that matters (martingale property).
      2. leverage(t,S) = local_vol_target(t,S) / sqrt(E[V|S]) — clipped to a
         sane range so a thin/edge bucket can't produce an exploded leverage.
      3. Effective vol = leverage * sqrt(V_old); the spot is advanced with
         THIS vol instead of either the raw local vol or the raw stochastic
         vol alone.
      4. Advance variance V for every path at once (_heston_qe_vectorized),
         to be used as V_old on the *next* step.

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

    V = [np.full(N, u.get("v0", 0.04), dtype=np.float64) for u in underlyings]

    dlogK = (logKmax - logKmin) / (nK - 1)

    for step in range(ts):
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            kappa = u.get("kappa", 2.0)
            theta = u.get("theta", 0.04)
            xi    = u.get("xi", 0.35)
            rho_h = u.get("rho_h", -0.70)
            rhop  = math.sqrt(max(0.0, 1.0 - rho_h*rho_h))

            # Variance Brownian, correlated with the spot driver via rho_h —
            # same construction as _simulate_heston's zv.
            zv_i = rho_h * Zc[step, i, :] + rhop * Zv[step, i, :]
            V_old = V[i]
            V_next = _heston_qe_vectorized(V_old, kappa, theta, xi, dt, zv_i)

            S_c = S[step, i, :]
            logS = np.log(np.maximum(S_c, 1e-8))
            kif = (logS - logKmin) / dlogK
            k0 = np.clip(kif.astype(int), 0, nK-2)
            frac = np.clip(kif - k0, 0.0, 1.0)
            g = lv_grids[i]
            lv_target = g[step, k0] * (1.0-frac) + g[step, k0+1] * frac

            # Particle-method conditional expectation E[V|S], bucketed on the
            # same log-moneyness grid as the local vol lookup above. Uses
            # V_old (not V_next/V_bar): V_next is computed from zv_i, which is
            # correlated with the SAME Brownian cZ[step,i,:] that drives the
            # spot below — feeding a look-ahead, correlated variance into
            # THIS step's effective vol would break the discounted spot's
            # martingale property (identical pitfall to alpha_old vs
            # alpha_bar in _simulate_sabr above, see its comment). V_old is
            # known at the start of the step, uncorrelated with this step's
            # own shocks, so it's safe to use in both the bucketing and the
            # spot update below. Confirmed empirically by
            # test_heston_spot_process_is_martingale-style E[S_T] check.
            bucket_sum = np.bincount(k0, weights=V_old, minlength=nK)
            bucket_cnt = np.bincount(k0, minlength=nK)
            overall_mean = max(float(V_old.mean()), 1e-6)
            bucket_mean = np.where(bucket_cnt >= _LSV_MIN_BUCKET_PATHS,
                                    bucket_sum / np.maximum(bucket_cnt, 1),
                                    overall_mean)
            E_V_given_S = bucket_mean[k0]

            leverage = np.clip(lv_target / np.sqrt(np.maximum(E_V_given_S, 1e-6)), 0.2, 5.0)
            eff_vol = leverage * np.sqrt(np.maximum(V_old, 0.0))
            if vol_add is not None:
                eff_vol = eff_vol + vol_add[i]
            eff_vol = np.clip(eff_vol, 0.001, 3.0)
            if vol_out is not None:
                vol_out[step, i, :] = eff_vol

            z_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * eff_vol
            drift = r_term + u.get("ccyh", 0.0) - u.get("q", 0.02) - q_adj - 0.5*eff_vol**2
            S[step+1, i, :] = S_c * np.exp(drift*dt + eff_vol*sq_dt*z_i)
            V[i] = V_next

    return S


# ── Continuous barrier monitoring (Brownian bridge extrema) ─────────

def _bridge_extrema(S: np.ndarray, vol_used: np.ndarray, dt: float, rng) -> tuple:
    """Per-step continuous extrema of each asset, drawn from the Brownian
    bridge conditional law given the step's endpoints:

        min = exp(0.5*(a + b - sqrt((b-a)^2 - 2*sig^2*dt*ln U)))
        max = exp(0.5*(a + b + sqrt((b-a)^2 - 2*sig^2*dt*ln V)))

    with a/b the log-spots at the step ends, U/V independent uniforms. The
    conditional law of a bridge extremum is drift-free, so the same formula
    serves every model (incl. stochastic rates); vol_used is the effective
    diffusion vol each simulator actually applied on that step (vol_out) —
    exact for GBM, a frozen-vol approximation within the step for the
    stochastic/local vol models. Min and max are drawn from independent
    uniforms: each marginal is exact, their joint law within one step is not
    (no script observed so far needs both barriers touched in the same week).

    Returns (bridge_min, bridge_max), each (ts, n, N); row k covers the
    interval (k, k+1] — the same indexing convention as S_min[step-1]."""
    logS = np.log(np.maximum(S, 1e-300))
    a, b = logS[:-1], logS[1:]
    var = np.maximum(vol_used, 1e-8) ** 2 * dt
    d2 = (b - a) ** 2
    U = rng.uniform(1e-12, 1.0, size=a.shape)
    V = rng.uniform(1e-12, 1.0, size=a.shape)
    m = 0.5 * (a + b - np.sqrt(d2 - 2.0 * var * np.log(U)))
    M = 0.5 * (a + b + np.sqrt(d2 - 2.0 * var * np.log(V)))
    return np.exp(m), np.exp(M)


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

    t = np.arange(ts + 1, dtype=np.float64) * dt
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


def _blend_rate_factor(z_i, Z_r_val, rho_rS: float):
    """Re-blend an asset's own (already inter-asset-correlated) Brownian z_i with
    the shared rate factor Z_r_val via that asset's rho_rS:
    z_i_final = rho_rS*Z_r_val + sqrt(1-rho_rS^2)*z_i. No-op when rho_rS == 0."""
    if rho_rS == 0.0:
        return z_i
    return rho_rS * Z_r_val + math.sqrt(max(0.0, 1.0 - rho_rS * rho_rS)) * z_i


# ── PayScript evaluation ────────────────────────────────────────────

def _strike_fix_steps(script: CompiledScript, ts_n: int) -> list[int]:
    """Resolved STRIKE_FIX dates -> clamped absolute step indices (>=1, <=ts_n).
    Shared by _compute_strike_fix (the reduction) and run_payoff_profile (which
    needs the LAST such step to know where to stop sweeping the neutral level) —
    both must clamp identically, or a short fixing window (e.g. 1 day, rounding
    to step 0 at the weekly grid) desyncs them and the sweep-cancels-fixing bug
    comes right back for that edge case."""
    if not script.strike_fix_dates:
        return []
    return sorted({min(max(round(d * SY), 1), ts_n) for d in script.strike_fix_dates})


def _compute_strike_fix(script: CompiledScript, WOF: np.ndarray,
                        fix_state_init: dict | None = None) -> tuple:
    """MIN/MAX/AVERAGE of WOF over the `CONSTAT() STRIKE_FIX` window (if
    declared), one scalar per path — exposed to scripts as FIX_MIN/FIX_MAX/
    FIX_AVG so a top-level `SET STRIKE = FIX_AVG` can turn the usual fixed
    STRIKE param into an Asian/min/max strike fixed once before the main
    observation calendar. Dates snap to the same weekly step grid as every
    other CONSTAT date (round(d*SY)); no declaration -> neutral 1.0 (day-0).

    fix_state_init ({"n", "sum", "min", "max"}, from the realized part of the
    window replayed on historical closes — see eval_script_on_history) folds
    the already-locked fixings into the reduction for residual MtM: MIN/MAX
    combine via min/max, AVERAGE is count-weighted so past and future fixing
    dates each carry exactly one observation's weight. The residual script's
    strike_fix_dates must then hold ONLY the still-future dates (shifted),
    or past dates would be double counted."""
    ts_n, N = WOF.shape
    steps = _strike_fix_steps(script, ts_n)
    if fix_state_init is None:
        if not steps:
            ones = np.ones(N)
            return ones, ones, ones
        window = WOF[[s - 1 for s in steps], :]   # (len(steps), N)
        return window.min(axis=0), window.max(axis=0), window.mean(axis=0)
    p_n, p_sum = fix_state_init["n"], fix_state_init["sum"]
    p_min, p_max = fix_state_init["min"], fix_state_init["max"]
    if not steps:   # window fully realized — constants across paths
        return (np.full(N, p_min), np.full(N, p_max), np.full(N, p_sum / p_n))
    window = WOF[[s - 1 for s in steps], :]
    return (np.minimum(window.min(axis=0), p_min),
            np.maximum(window.max(axis=0), p_max),
            (window.sum(axis=0) + p_sum) / (len(steps) + p_n))


def _eval_paths(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                dt: float, r_eff: float, user_params: dict,
                step_map: dict, mat_events: list, flux_map: dict,
                record: bool, df_arr: np.ndarray | None = None,
                wof_min_init=None, bof_max_init=None,
                stop_times_out: list | None = None,
                bridge_min=None, bridge_max=None,
                index_offset: int = 0, memo_init: dict | None = None,
                accum_init: float = 0.0,
                s_min_init=None, s_max_init=None, s_prev_init=None,
                wof0_init: float | None = None,
                realvol_state_init: dict | None = None,
                fix_state_init: dict | None = None) -> list[float]:
    """Evaluate PayScript on pre-computed spot paths. Observation-only loop.

    wof_min_init / bof_max_init (None, a scalar, or array of shape (N,)) seed the
    running worst-of-min / best-of-max state inherited from before t=0 of this path
    tensor. Used by Mark-to-Future to carry over each outer scenario's pre-t0 barrier
    state into its inner residual-pricing paths; left at None (no-op) for normal
    pricing. index_offset / memo_init / accum_init extend the same inheritance for
    residual deal MtM (api/deals.py): the observation counter continues past the
    replayed observations (PARAM() arrays read the right row), and script variables
    (SET / memory coupons) resume from the replayed state — injected after init_fn
    so the script's own initializers don't reset them.

    s_min_init/s_max_init ((n,) — per-asset realized extrema), s_prev_init
    ((n,) — spots at the last PAST observation, so the first residual
    observation's S_PREV is the real previous fixing instead of 1.0),
    wof0_init (worst-of level at t=0 of this tensor — without it the REALVOL
    log-return series would book a phantom first return log(WOF₁/1.0) equal
    to the whole realized drift), realvol_state_init ({"sumsq": Σ(log-ret²)
    of the realized WOF series, "t": elapsed years} — combined with the
    simulated leg by summing quadratic variations and times, which is
    sampling-frequency-independent, so daily past + weekly future is exact)
    and fix_state_init (realized STRIKE_FIX reduction, see _compute_strike_fix)
    complete the same inheritance for residual deal MtM. All default to
    None/absent = day-0 behavior, bit-identical to before they existed.

    Mark-to-Future (run_mark_to_future) does NOT feed these six — its inner
    repricing still resets S_MIN/S_MAX/S_PREV/REALVOL/FIX_* to day-0 defaults
    (extracting per-outer-scenario state would need per-chunk arrays and a
    per-scenario wof0). Known remaining gap, documented, not addressed.

    bridge_min/bridge_max (ts, n, N), from _bridge_extrema: when provided, the
    RUNNING extrema (WOF_min/BOF_max/S_MIN/S_MAX — the barrier-monitoring
    quantities) accumulate over the continuous within-step extrema instead of
    the weekly endpoints. Observation-date values (spots, WOF, FIX_*, REALVOL)
    stay endpoint-based: those are discrete contractual fixings."""
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    WOF_min = np.minimum.accumulate(bridge_min.min(axis=1) if bridge_min is not None else WOF, axis=0)
    BOF_max = np.maximum.accumulate(bridge_max.max(axis=1) if bridge_max is not None else BOF, axis=0)
    if wof_min_init is not None:
        WOF_min = np.minimum(WOF_min, wof_min_init)
    if bof_max_init is not None:
        BOF_max = np.maximum(BOF_max, bof_max_init)
    FIX_MIN, FIX_MAX, FIX_AVG = _compute_strike_fix(script, WOF, fix_state_init)

    # Per-asset running min/max (S_MIN[i]/S_MAX[i] — distinct from WOF_min/BOF_max,
    # which are basket-level). Realized vol of the WOF index, annualized from
    # weekly log-returns accumulated since inception (REALVOL).
    S_min = np.minimum.accumulate(bridge_min if bridge_min is not None else S[1:], axis=0)
    S_max = np.maximum.accumulate(bridge_max if bridge_max is not None else S[1:], axis=0)
    if s_min_init is not None:
        S_min = np.minimum(S_min, np.asarray(s_min_init, dtype=float).reshape(1, n, 1))
    if s_max_init is not None:
        S_max = np.maximum(S_max, np.asarray(s_max_init, dtype=float).reshape(1, n, 1))
    wof0 = 1.0 if wof0_init is None else float(wof0_init)
    WOF_full = np.vstack([np.full((1, N), wof0), WOF])   # (ts+1, N) — WOF(t=0)
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)   # (ts, N)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)    # (ts, N)
    rv_sumsq0 = realvol_state_init["sumsq"] if realvol_state_init else 0.0
    rv_t0 = realvol_state_init["t"] if realvol_state_init else 0.0

    obs_steps = sorted(step_map.keys())
    payoffs: list[float] = []
    payoffs_raw: list[float] = []   # undiscounted total cash flow per path

    # PARAM defaults first, user_params (partial or full) override — a caller
    # that omits a param must fall back to its script default, not silently 0.
    full_params = {p.name: p.stored_val for p in script.params}
    full_params.update(user_params)

    for path in range(N):
        ctx = {
            # s_prev_init seeds "spots" (not "s_prev"): the first observation
            # copies spots -> s_prev before overwriting spots, so the real
            # previous fixing lands in S_PREV through the normal mechanics.
            "spots": [1.0] * n if s_prev_init is None else list(s_prev_init),
            "accum": accum_init, "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
            "s_min": [1.0] * n, "s_max": [1.0] * n, "s_prev": [1.0] * n, "realvol": 0.0,
            "fix_min": float(FIX_MIN[path]), "fix_max": float(FIX_MAX[path]),
            "fix_avg": float(FIX_AVG[path]),
            "done": False, "memo": {**full_params}, "total_cf": 0.0, "total_cf_raw": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)
        # Residual-MtM state inheritance: applied AFTER init_fn on purpose —
        # the script's own SET statements must not reset memory coupons and
        # other variables the replayed past already accumulated.
        if memo_init:
            ctx["memo"].update(memo_init)

        done = False
        obs_idx = index_offset

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
            # Combined quadratic variation past+future when a realized state is
            # inherited; the historical formula kept bit-identical otherwise.
            ctx["realvol"] = (math.sqrt(SY * cum_sq_ret[step - 1, path] / step)
                              if realvol_state_init is None else
                              math.sqrt((rv_sumsq0 + cum_sq_ret[step - 1, path])
                                        / (rv_t0 + step * dt)))
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
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
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
            ctx["realvol"] = (math.sqrt(SY * cum_sq_ret[ts - 1, path] / ts)
                              if realvol_state_init is None else
                              math.sqrt((rv_sumsq0 + cum_sq_ret[ts - 1, path])
                                        / (rv_t0 + ts * dt)))
            ctx["t"] = ts * dt
            ctx["wof_min"] = float(WOF_min[ts - 1, path])
            ctx["bof_max"] = float(BOF_max[ts - 1, path])
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
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
                          step_map: dict, mat_events: list,
                          df_arr: np.ndarray | None = None,
                          bridge_min=None, bridge_max=None) -> dict:
    """Like _eval_paths but returns per-path outcome classification.

    df_arr (ts+1,) — optional deterministic discount curve; None falls back to
    flat exp(-r_eff*t), matching _eval_paths' behaviour.
    bridge_min/bridge_max: continuous-monitoring extrema, see _eval_paths."""
    WOF = S[1:].min(axis=1)
    BOF = S[1:].max(axis=1)
    WOF_min = np.minimum.accumulate(bridge_min.min(axis=1) if bridge_min is not None else WOF, axis=0)
    BOF_max = np.maximum.accumulate(bridge_max.max(axis=1) if bridge_max is not None else BOF, axis=0)
    S_min = np.minimum.accumulate(bridge_min if bridge_min is not None else S[1:], axis=0)
    S_max = np.maximum.accumulate(bridge_max if bridge_max is not None else S[1:], axis=0)
    WOF_full = np.vstack([np.ones((1, N)), WOF])
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)
    FIX_MIN, FIX_MAX, FIX_AVG = _compute_strike_fix(script, WOF)

    obs_steps = sorted(step_map.keys())
    obs_times = sorted({step * dt for step in obs_steps})

    payoffs: list[float] = []
    outcomes: list[str] = []
    stop_times: list[float | None] = []
    final_wofs: list[float] = []
    event_step_counts: dict[int, int] = {}

    # PARAM defaults first, user_params (partial or full) override — a caller
    # that omits a param must fall back to its script default, not silently 0.
    full_params = {p.name: p.stored_val for p in script.params}
    full_params.update(user_params)

    for path in range(N):
        ctx = {
            "spots": [1.0]*n, "accum": 0.0, "index": 0,
            "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
            "s_min": [1.0]*n, "s_max": [1.0]*n, "s_prev": [1.0]*n, "realvol": 0.0,
            "fix_min": float(FIX_MIN[path]), "fix_max": float(FIX_MAX[path]),
            "fix_avg": float(FIX_AVG[path]),
            "done": False, "memo": {**full_params}, "total_cf": 0.0, "total_cf_raw": 0.0,
        }
        if script.init_fn:
            script.init_fn(ctx)

        done = False
        obs_idx = 0
        stop_t: float | None = None

        for step in obs_steps:
            if done:
                break
            disc = df_arr[step] if df_arr is not None else math.exp(-r_eff * step * dt)
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
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * disc
                    ctx["total_cf_raw"] += fl["v"]
                if st["done"]:
                    done = True
                    ctx["done"] = True
                    stop_t = ctx["t"]
                    event_step_counts[step] = event_step_counts.get(step, 0) + 1

        if not done and mat_events:
            disc = df_arr[ts] if df_arr is not None else math.exp(-r_eff * ts * dt)
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
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    ctx["total_cf"] += fl["v"] * disc
                    ctx["total_cf_raw"] += fl["v"]
                if st["done"]:
                    done = True

        pf = ctx["total_cf"]
        payoffs.append(pf)
        stop_times.append(stop_t)
        final_wofs.append(float(WOF[ts-1, path]) if ts > 0 else 1.0)

        # Classify on the UNDISCOUNTED total: a path returning par (100%) at
        # maturity is "normal" regardless of r — its discounted PV is below 1
        # at any positive rate, which is not a capital loss.
        if stop_t is not None:
            outcomes.append("autocall")
        elif ctx["total_cf_raw"] < 0.999:
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
           spot_base=None,
           vol_add=None,
           dr: float = 0.0,
           dt_add: float = 0.0,
           corr_delta=None,
           yield_curve=None,
           sigma_r: float = 0.0,
           a_r: float = 0.0,
           barrier_monitoring: str = "weekly",
           wof_min_init=None,
           bof_max_init=None,
           index_offset: int = 0,
           memo_init: dict | None = None,
           accum_init: float = 0.0,
           s_min_init=None,
           s_max_init=None,
           s_prev_init=None,
           wof0_init: float | None = None,
           realvol_state_init: dict | None = None,
           fix_state_init: dict | None = None):

    t0 = time.perf_counter()
    if barrier_monitoring not in ("weekly", "continuous"):
        raise ValueError(
            f"barrier_monitoring invalide: {barrier_monitoring!r} — valeurs admises: "
            f"'weekly' (extrema aux pas hebdomadaires, défaut) ou 'continuous' "
            f"(pont brownien intra-pas)."
        )
    use_bridge = barrier_monitoring == "continuous"
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
                # Clamp to step >= 1: a date rounding to step 0 would make the
                # evaluators index S_min[-1]/WOF_min[-1] — the END of the path.
                step = max(1, round(d * SY))
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
    use_lsv    = model == "lsv"

    rng = default_rng(seed)
    # N = number of independent observations (pairs when antithetic, standalone paths otherwise).
    # Antithetic simulates 2*N total paths (N base + N antithetic) and averages each pair;
    # variance reduction comes from the negative correlation between legs, not from fewer draws.
    N_pairs = N

    Z  = rng.standard_normal((ts, n, N_pairs))
    Zv = rng.standard_normal((ts, n, N_pairs)) if (use_heston or use_lsv) else None
    Za = rng.standard_normal((ts, n, N_pairs)) if use_sabr   else None

    # One rate term for the whole run: discounting, drift and smile calibration
    # all read from it, so they cannot disagree. Built after every rng draw
    # above and before the local-vol grid below, which now consumes it — it
    # touches no random state, so the stream is unchanged.
    rates = _build_rate_term(yield_curve or [], ts, dt, r, dr)
    df_arr = rates.df

    # Deterministic drift term, shaped (ts,1): broadcasts against (ts,N) in
    # _simulate_gbm, and reduces to a scalar under the [step] indexing the four
    # step-wise simulators use. None when there is no curve, in which case the
    # simulators fall back on the scalar r_eff exactly as before.
    r_det = None if rates.step_fwd is None else rates.step_fwd[:, None]

    lv_data = None
    if use_lv or use_lsv:
        lv_data = _build_lv_grid(underlyings, rates, ts, dt)

    # Optional stochastic short rate: a single shared Gaussian factor (ABM when
    # a_r=0, Hull-White when a_r>0 — see _stochastic_rate_paths). sigma_r=0 is
    # the default and falls through to the deterministic term above. Each leg
    # (base/anti) gets its own rate path from Z_r/-Z_r, paired like Z/Zv/Za.
    use_stoch_rate = sigma_r > 0
    Z_r = rng.standard_normal((ts, N_pairs)) if use_stoch_rate else None
    if use_stoch_rate:
        fwd = _forward_rate_arr(df_arr, dt)
        r_path_base, df_base = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, Z_r)
        r_path_anti, df_anti = _stochastic_rate_paths(fwd, sigma_r, a_r, sq_dt, dt, -Z_r)
    else:
        # The drift follows the same curve that discounts the payoff. r_det is
        # None without a curve, so the simulators keep using the scalar r_eff.
        r_path_base = r_path_anti = r_det
        df_base = df_anti = df_arr

    flux_map: dict[str, dict] = {}

    # A Greeks delta/gamma bump passes a spot_mult that differs from the
    # baseline to shock one asset's spot. Feeding that straight into the
    # simulator scales the WHOLE path from t=0 — including a STRIKE_FIX window,
    # if the script has one — so REF gets shocked in lockstep with WOF and the
    # bump cancels out of PERF=WOF/REF (delta/gamma come back ~0, the bug this
    # fixes). Instead, simulate at the baseline level and apply only the bump
    # RATIO to the segment after the fixing window closes — exact for
    # GBM/Heston (their log-return dynamics don't depend on the absolute spot
    # level), an approximation for SABR (beta!=1) and Local Vol (genuinely
    # level-dependent vol), but a good one at the small bump sizes Greeks use.
    #
    # spot_base is what the caller considers "not bumped": [1]*n pre-trade, the
    # live deal's norm_spots on a residual reprice. Comparing against it rather
    # than against 1.0 is what keeps a live deal whose spot has merely moved
    # (norm_spots != 1, no bump at all) out of this branch — otherwise its MtM
    # would be simulated from 1.0 instead of from today's spot, which is the
    # bug this baseline fixes. A 2-D spot_mult is Mark-to-Future's per-scenario
    # seeding, never a bump: excluded outright.
    _base_vec = list(spot_base) if spot_base is not None else [1.0] * n
    _bump_needs_delay = (
        bool(script.strike_fix_dates) and spot_mult is not None
        and np.ndim(spot_mult) == 1
        and any(abs(m - b) > 1e-12 for m, b in zip(spot_mult, _base_vec))
    )
    _sim_spot_mult = _base_vec if _bump_needs_delay else spot_mult

    def _apply_delayed_bump(S: np.ndarray) -> np.ndarray:
        if not _bump_needs_delay:
            return S
        fix_steps = _strike_fix_steps(script, ts)
        fix_end_step = max(fix_steps) if fix_steps else 0
        S = S.copy()
        for i, (m, b) in enumerate(zip(spot_mult, _base_vec)):
            if abs(m - b) > 1e-12:
                S[fix_end_step + 1:, i, :] *= m / b
        return S

    vol_base = np.empty((ts, n, N_pairs), dtype=np.float64) if use_bridge else None

    if use_heston:
        S_base = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, Z, Zv, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                   vol_out=vol_base)
    elif use_lsv:
        lv_grids, nK, lkm, lkx = lv_data
        S_base = _simulate_lsv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                r_eff, L, Z, Zv, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                r_path_base, Z_r, vol_out=vol_base)
    elif use_lv:
        lv_grids, nK, lkm, lkx = lv_data
        S_base = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                               r_eff, L, Z, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                               r_path_base, Z_r, vol_out=vol_base)
    elif use_sabr:
        S_base = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                 r_eff, L, Z, Za, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                 vol_out=vol_base)
    else:
        S_base = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                r_eff, L, Z, _sim_spot_mult, vol_add, r_path_base, Z_r,
                                vol_out=vol_base)
    S_base = _apply_delayed_bump(S_base)
    # Bridge extrema from the (possibly bumped) paths — the bridge scales with
    # the level in log-space, so post-bump is the consistent order. Uniform
    # draws happen only in continuous mode: the weekly path consumes the exact
    # same rng stream as before this feature existed.
    br_min_b, br_max_b = _bridge_extrema(S_base, vol_base, dt, rng) if use_bridge else (None, None)

    stop_times_base: list[float] | None = [] if script.has_stop else None
    payoffs_base, raw_base = _eval_paths(script, S_base, ts, n, N_pairs, dt, r_eff,
                                          user_params, step_map, mat_events, flux_map,
                                          record=True, df_arr=df_base,
                                          stop_times_out=stop_times_base,
                                          bridge_min=br_min_b, bridge_max=br_max_b,
                                          wof_min_init=wof_min_init, bof_max_init=bof_max_init,
                                          index_offset=index_offset, memo_init=memo_init,
                                          accum_init=accum_init,
                                          s_min_init=s_min_init, s_max_init=s_max_init,
                                          s_prev_init=s_prev_init, wof0_init=wof0_init,
                                          realvol_state_init=realvol_state_init,
                                          fix_state_init=fix_state_init)

    payoffs_anti: list[float] = []
    raw_anti:     list[float] = []
    if antithetic:
        Z_r_anti = -Z_r if use_stoch_rate else None
        vol_anti = np.empty((ts, n, N_pairs), dtype=np.float64) if use_bridge else None
        if use_heston:
            S_anti = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                       r_eff, L, -Z, -Zv, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                       vol_out=vol_anti)
        elif use_lsv:
            S_anti = _simulate_lsv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, -Z, -Zv, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                    r_path_anti, Z_r_anti, vol_out=vol_anti)
        elif use_lv:
            S_anti = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, -Z, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                   r_path_anti, Z_r_anti, vol_out=vol_anti)
        elif use_sabr:
            S_anti = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                     r_eff, L, -Z, -Za, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                     vol_out=vol_anti)
        else:
            S_anti = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, -Z, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                    vol_out=vol_anti)
        S_anti = _apply_delayed_bump(S_anti)
        br_min_a, br_max_a = _bridge_extrema(S_anti, vol_anti, dt, rng) if use_bridge else (None, None)
        stop_times_anti: list[float] | None = [] if script.has_stop else None
        payoffs_anti, raw_anti = _eval_paths(script, S_anti, ts, n, N_pairs, dt, r_eff,
                                              user_params, step_map, mat_events, {},
                                              record=False, df_arr=df_anti,
                                              stop_times_out=stop_times_anti,
                                              bridge_min=br_min_a, bridge_max=br_max_a,
                                              wof_min_init=wof_min_init, bof_max_init=bof_max_init,
                                              index_offset=index_offset, memo_init=memo_init,
                                              accum_init=accum_init,
                                              s_min_init=s_min_init, s_max_init=s_max_init,
                                              s_prev_init=s_prev_init, wof0_init=wof0_init,
                                              realvol_state_init=realvol_state_init,
                                              fix_state_init=fix_state_init)

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

    # float() coercions: the per-path cash flows get contaminated by numpy
    # scalars (df_arr discounting) — round() preserves np.float64, and numpy
    # scalars leaking into API payloads break FastAPI's JSON encoder (np.bool_)
    # or just pollute downstream types (np.float64).
    return {
        "price": round(float(price), 6),
        "ic95": [round(float(price - 1.96*se), 6), round(float(price + 1.96*se), 6)],
        "median": round(float(median), 6),
        "var5": round(float(var5), 6),
        # Top of the discounted-payoff distribution: pv_max is the best possible
        # outcome in present value (for a capped product — autocall, reverse
        # convertible — it's the cap, e.g. next-call redemption); pv_p95 both
        # serves as "favourable scenario" for uncapped payoffs and, compared to
        # pv_max, detects whether the payoff IS capped (flat top). Feeds the
        # residual-upside / early-exit signal of the client valuation note.
        "pv_max": round(float(pv_all[-1]), 6),
        "pv_p95": round(float(pv_all[min(N_hist - 1, int(N_hist * 0.95))]), 6),
        "prob_gt100": round(float(prob_gt100), 6),
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
                   user_params,
                   selected: list | None = None, sigma_r: float = 0.0, a_r: float = 0.0,
                   yield_curve=None, barrier_monitoring: str = "weekly",
                   antithetic: bool = True, state: dict | None = None):
    """CRN bump-and-reprice greeks.

    Every term of every finite difference — including the CENTER of gamma/
    theta/corr — is repriced here at N_g paths with the same seed, so the
    common Monte Carlo noise cancels. (An earlier version reused the main
    run's full-N price as the center: a different estimator whose sampling
    error does NOT cancel against the bumped legs, and gets amplified by the
    tiny FD denominators — gamma divides by 9e-4.)

    `state` carries a live deal's lifecycle position: spot in % of strike
    (`spot_base`), realized extrema, observation counter, memory coupons,
    accumulator, last fixings and realized variance — the same bundle
    api/deals.py:_mtm_core feeds to run_mc. Without it every bumped leg
    reprices a BRAND NEW product, so the sensitivities of a deal whose
    knock-in has already triggered, or whose coupon memory has accrued, have
    nothing to do with the ones reported. `state=None` is the pre-trade case
    and reproduces the previous behaviour exactly.

    How a bump interacts with that state, deliberately:
      - the spot vector is bumped MULTIPLICATIVELY around `spot_base`, so a
        deal 30% above its strike is shocked by 1% of where it actually is;
      - `wof0` is derived from the bumped vector rather than passed in, which
        is what makes it impossible to forget — leaving it at the unbumped
        level books a phantom first log-return into REALVOL;
      - realized extrema, memory and fixings do NOT move. They are facts, not
        model outputs. (And the running extrema accumulate over S[1:], so the
        bumped t=0 slice never enters them in the first place.)
    """
    if selected is None:
        selected = ["delta", "gamma", "vega", "theta", "rho"]
    sel = set(selected)
    N_g = max(1000, N // 4)
    greeks: dict = {}
    n = len(underlyings)

    st = state or {}
    base_spots = list(st.get("spot_base") or [1.0] * n)

    def reprice(spot_vec=None, script_=None, T_=None, index_=None, **bumps) -> dict:
        sv = list(spot_vec) if spot_vec is not None else base_spots
        return run_mc(
            script if script_ is None else script_,
            underlyings, corr_matrix, r, T if T_ is None else T_, N_g, model, seed,
            antithetic=antithetic, user_params=user_params, sigma_r=sigma_r, a_r=a_r,
            yield_curve=yield_curve or [], barrier_monitoring=barrier_monitoring,
            spot_mult=sv, spot_base=base_spots,
            wof_min_init=st.get("wof_min"), bof_max_init=st.get("bof_max"),
            index_offset=st.get("index", 0) if index_ is None else index_,
            memo_init=st.get("memo"), accum_init=st.get("accum", 0.0),
            s_min_init=st.get("s_min"), s_max_init=st.get("s_max"),
            s_prev_init=st.get("s_prev"), wof0_init=min(sv),
            realvol_state_init=st.get("realvol_state"),
            fix_state_init=st.get("fix_state"),
            **bumps,
        )

    def price(**kw) -> float:
        return reprice(**kw)["price"]

    def _bumped(i: int, mult: float) -> list:
        v = list(base_spots)
        v[i] = base_spots[i] * mult
        return v

    base_res = reprice() if sel & {"gamma", "theta", "corr"} else None
    base_g = base_res["price"] if base_res is not None else None

    for i in range(n):
        if "delta" in sel or "gamma" in sel:
            pu = price(spot_vec=_bumped(i, 1.01))
            pd = price(spot_vec=_bumped(i, 0.99))
            if "delta" in sel:
                greeks[f"delta_{i+1}"] = round((pu - pd) / 0.02, 4)
            if "gamma" in sel:
                greeks[f"gamma_{i+1}"] = round(
                    (price(spot_vec=_bumped(i, 1.03)) - 2*base_g
                     + price(spot_vec=_bumped(i, 0.97))) / 0.0009, 4)

    if "vega" in sel:
        for i in range(n):
            va_up = [0.0]*n; va_up[i] = 0.01
            va_dn = [0.0]*n; va_dn[i] = -0.01
            greeks[f"vega_{i+1}"] = round((price(vol_add=va_up) - price(vol_add=va_dn)) / 0.02, 4)

    if "theta" in sel:
        theta, theta_event = _theta_and_event(
            script, T, st, base_g, base_res, reprice)
        greeks["theta"] = theta
        greeks["theta_event"] = theta_event

    if "rho" in sel:
        greeks["rho"] = round((price(dr=0.01) - price(dr=-0.01)) / 0.02, 4)

    if "corr" in sel and n > 1:
        for ci in range(n):
            for cj in range(ci+1, n):
                cd = {"ci": ci, "cj": cj, "delta": 0.05}
                greeks[f"corr_{ci+1}_{cj+1}"] = round((price(corr_delta=cd) - base_g) / 0.05, 4)

    return greeks


def _theta_and_event(script: CompiledScript, T: float, st: dict,
                     base_g: float | None, base_res: dict | None,
                     reprice) -> tuple[float | None, dict | None]:
    """Time decay over one grid step when no contractual event is crossed.

    Aging the product by a week is the finest decay this weekly grid can
    represent, but an observation falling inside that week detaches its cash
    flow, and a raw price difference then books that detachment as "decay": a
    5% coupon over 7 days reads as -0.7/day. True at the deal level, useless
    once summed over a book, where it swamps every genuine theta.

    Crossing an observation requires executing its full state transition. The
    generic bump-and-reprice layer cannot safely invent that realized outcome,
    so it returns an explicit reason instead of a misleading scalar theta.

    Returns (theta per calendar day, event descriptor or None). theta is None
    when rolling the state forward would take a guess: a strike-fixing date
    inside the window (the fixing would be silently dropped from the average
    rather than folded into fix_state), or a REALVOL script (the week's
    realized variance is simulated on one leg and would have to be invented on
    the other).
    """
    eps = 1e-9
    dt_step = 1.0 / SY
    if T <= 2 * dt_step:
        return None, None

    if script.strike_fix_dates and any(d <= dt_step + eps for d in script.strike_fix_dates):
        return None, {"reason": "fenetre_strike_fix"}
    if st.get("realvol_state"):
        return None, {"reason": "realvol"}

    crossed = sorted({round(d, 6) for ev in script.events if ev.type == "AT"
                      for d in ev.dates if 0 < d <= dt_step + eps})

    if crossed:
        # Crossing an observation is a state transition, not a mere removal
        # of one event from the future script.  The event may update coupon
        # memory, accumulators, fixings, extrema or terminate the product.  A
        # stripped-script comparison cannot reconstruct that path-dependent
        # post-event state, so publishing a scalar theta (or a synthetic event
        # PV) is more dangerous than explicitly declaring it unavailable.
        return None, {
            "reason": "observation_transition_required",
            "t_years": crossed[-1],
            "terminates": bool(script.has_stop),
        }

    aged_sfd = ([round(d - dt_step, 6) for d in script.strike_fix_dates
                 if d > dt_step + eps] or None) if script.strike_fix_dates else None

    def _respan(events, shift: float):
        out = []
        for ev in events:
            if ev.type != "AT":
                out.append(ev)
                continue
            keep = [round(d - shift, 6) for d in ev.dates if d > dt_step + eps]
            if keep:
                out.append(CompiledEvent(type=ev.type, dates=keep, fn=ev.fn))
        return out

    def _variant(shift: float):
        return CompiledScript(events=_respan(script.events, shift),
                              init_fn=script.init_fn, params=script.params,
                              constats=script.constats, has_stop=script.has_stop,
                              strike_fix_dates=aged_sfd)

    aged = reprice(script_=_variant(dt_step), T_=T - dt_step)["price"]
    return round((aged - base_g) / 7.0, 4), None


# ── Analytics: Payoff Profile ───────────────────────────────────────

def run_payoff_profile(script: CompiledScript, underlyings, corr_matrix,
                        r: float, T_max: float, user_params=None, n_pts: int = 151) -> dict:
    """Sweep spot levels 0%–150% and evaluate payoff on a FLAT path — the
    underlying PINNED at that exact level at every observation date, for the
    product's whole life (no drift, no vol, nothing to simulate). This is
    the standard reading of a payoff/scenario diagram ("if the underlying
    stayed at X%, here's what you get"), and the only one that makes a
    barrier/autocall step function unambiguous: a level below the barrier
    never crosses it, period.

    (An earlier version instead simulated a near-zero-vol GBM path and
    rescaled it — which still carried the real risk-neutral (r-q) drift even
    at ~0 vol, so a sub-barrier level could quietly drift up and cross an
    autocall barrier on a LATER observation date. For a memory-coupon script
    (PAY CALL * COUPON * INDEX, paying every accrued coupon at once on the
    date it finally triggers) that produced a payoff spike — e.g. 124% at a
    98% starting level vs 108% at 100% — that read as a jump in value but
    was really just the same coupon rate paid over more accrued periods
    because the "98%" level didn't actually stay at 98%. Pinning the level
    removes the ambiguity at the source instead of explaining it away after
    the fact — annualized_coupons below is a still-useful secondary view for
    memory-coupon structures, independent of this fix.)

    Concentrated on the downside (0-150% rather than 40-200%) and sampled
    densely (151 pts, ~1% spacing) so genuine payoff discontinuities (autocall/KO
    barriers) render as near-vertical jumps instead of a slanted chord between
    two widely-spaced points — cheaper than detecting each script's barriers
    symbolically, and it generalizes to every PayScript, not just gear puts."""
    user_params = user_params or {}
    n = len(underlyings)
    levels = [0.0 + i * 1.50 / (n_pts - 1) for i in range(n_pts)]

    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(max(1, round(d*SY)), []).append(ev)

    # A single deterministic path per level — no noise to average over, the
    # level IS the whole path (post-fixing).
    N_p = 1
    S_neutral = np.ones((ts + 1, n, N_p), dtype=np.float64)
    fix_steps = _strike_fix_steps(script, ts)
    fix_end_step = max(fix_steps) if fix_steps else 0

    # Realization time per level, alongside the payoff itself — lets a
    # memory-coupon payoff (see docstring above) also be read as an
    # annualized rate, which stays flat across levels even though the raw
    # payoff still legitimately steps up at each barrier a pinned level sits
    # exactly on. stop_times_out collects one entry per path that actually
    # STOPs (autocalled); a level whose path runs to maturity without
    # stopping gets none, and falls back to T_max below.
    payoffs = []
    annualized_coupons = []
    realization_times = []
    for x in levels:
        S = S_neutral.copy()
        S[fix_end_step + 1:] = x
        stop_times: list[float] = []
        _, pfs_raw = _eval_paths(script, S, ts, n, N_p, dt, r, user_params,
                                  step_map, mat_events, {}, record=False,
                                  stop_times_out=stop_times)
        payoff = round(sum(pfs_raw) / N_p * 100, 3)
        t_realized = (sum(stop_times) / len(stop_times)) if stop_times else T_max
        t_realized = max(t_realized, 1 / 365)  # guard against div-by-~0 for a same-day trigger
        payoffs.append(payoff)
        realization_times.append(round(t_realized, 4))
        annualized_coupons.append(round((payoff - 100.0) / t_realized, 3))

    return {
        "levels": [round(x * 100, 1) for x in levels],
        "payoffs": payoffs,
        "realization_times": realization_times,
        "annualized_coupons": annualized_coupons,
    }


# ── Analytics: MC Sample Paths ──────────────────────────────────────

def run_mc_paths(script: CompiledScript, underlyings, corr_matrix,
                  r: float, T_max: float, N_display: int = 50,
                  N_stat: int = 500, model: str = "constant",
                  seed: int = 42, user_params=None,
                  barrier_monitoring: str = "weekly") -> dict:
    """Run MC and return 50 sample paths colored by outcome."""
    user_params = user_params or {}
    n = len(underlyings)
    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    use_bridge = barrier_monitoring == "continuous"

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(max(1, round(d*SY)), []).append(ev)

    L = cholesky(corr_matrix, n)
    rng = default_rng(seed)
    Z = rng.standard_normal((ts, n, N_stat))
    vol_used = np.empty((ts, n, N_stat), dtype=np.float64) if use_bridge else None

    # Path visualisation takes no yield curve — the displayed trajectories and
    # their raw (undiscounted) payoffs are flat-rate by construction.
    _flat = _build_rate_term([], ts, dt, r)

    if model == "heston":
        Zv = rng.standard_normal((ts, n, N_stat))
        S = _simulate_heston(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, Zv, vol_out=vol_used)
    elif model == "lsv":
        Zv = rng.standard_normal((ts, n, N_stat))
        lv_grids, nK, lkm, lkx = _build_lv_grid(underlyings, _flat, ts, dt)
        S = _simulate_lsv(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, Zv, lv_grids, nK, lkm, lkx,
                          vol_out=vol_used)
    elif model == "localvol":
        lv_data = _build_lv_grid(underlyings, _flat, ts, dt)
        lv_grids, nK, lkm, lkx = lv_data
        S = _simulate_lv(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, lv_grids, nK, lkm, lkx,
                         vol_out=vol_used)
    elif model == "sabr":
        Za = rng.standard_normal((ts, n, N_stat))
        S = _simulate_sabr(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, Za, vol_out=vol_used)
    else:
        S = _simulate_gbm(ts, n, N_stat, dt, sq_dt, underlyings, r, L, Z, vol_out=vol_used)

    br_min, br_max = _bridge_extrema(S, vol_used, dt, rng) if use_bridge else (None, None)
    det = _eval_paths_detailed(script, S, ts, n, N_stat, dt, r, user_params, step_map, mat_events,
                                bridge_min=br_min, bridge_max=br_max)

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
                  model: str = "constant", seed: int = 42, user_params=None,
                  yield_curve=None, barrier_monitoring: str = "weekly",
                  capital_ref: float = 1.0) -> dict:
    """Full MC run returning probability breakdown.

    capital_ref: what "capital_loss_pct"/"full_coupon_pct" measure against.
    Defaults to par (1.0) — correct for autocall/phoenix-style notes designed
    to price at par. For anything priced away from par (options, certificates
    — see the reinvestment scan, api/deals.py), pass the actual price paid
    (target_price of the solve): comparing an option's payoff to 100% of
    notional is meaningless, it never gets there by design."""
    user_params = user_params or {}
    n = len(underlyings)
    N_p = min(10000, max(2000, N))
    ts = max(1, round(T_max * SY))
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    use_bridge = barrier_monitoring == "continuous"

    step_map: dict = {}
    mat_events = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(max(1, round(d*SY)), []).append(ev)

    L = cholesky(corr_matrix, n)
    rng = default_rng(seed)
    Z = rng.standard_normal((ts, n, N_p))
    vol_used = np.empty((ts, n, N_p), dtype=np.float64) if use_bridge else None

    # Same rate term as run_mc: the probabilities shown next to a price must be
    # computed under the same measure as that price, or the two panels of the
    # screen describe different products.
    rates = _build_rate_term(yield_curve or [], ts, dt, r)
    r_det = None if rates.step_fwd is None else rates.step_fwd[:, None]

    if model == "heston":
        Zv = rng.standard_normal((ts, n, N_p))
        S = _simulate_heston(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, Zv,
                             r_path=r_det, vol_out=vol_used)
    elif model == "lsv":
        Zv = rng.standard_normal((ts, n, N_p))
        lv_grids, nK, lkm, lkx = _build_lv_grid(underlyings, rates, ts, dt)
        S = _simulate_lsv(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, Zv, lv_grids, nK, lkm, lkx,
                          r_path=r_det, vol_out=vol_used)
    elif model == "localvol":
        lv_data = _build_lv_grid(underlyings, rates, ts, dt)
        lv_grids, nK, lkm, lkx = lv_data
        S = _simulate_lv(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, lv_grids, nK, lkm, lkx,
                         r_path=r_det, vol_out=vol_used)
    elif model == "sabr":
        Za = rng.standard_normal((ts, n, N_p))
        S = _simulate_sabr(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z, Za,
                           r_path=r_det, vol_out=vol_used)
    else:
        S = _simulate_gbm(ts, n, N_p, dt, sq_dt, underlyings, r, L, Z,
                          r_path=r_det, vol_out=vol_used)

    br_min, br_max = _bridge_extrema(S, vol_used, dt, rng) if use_bridge else (None, None)
    df_arr = rates.df
    det = _eval_paths_detailed(script, S, ts, n, N_p, dt, r, user_params, step_map, mat_events,
                                df_arr=df_arr, bridge_min=br_min, bridge_max=br_max)

    ac = sum(1 for o in det["outcomes"] if o == "autocall")
    ki = sum(1 for o in det["outcomes"] if o == "ki")
    nm = sum(1 for o in det["outcomes"] if o == "normal")

    event_counts = {round(step * dt, 4): cnt for step, cnt in det["event_step_counts"].items()}

    stop_ts = [st for st in det["stop_times"] if st is not None]
    expected_life = (sum(stop_ts) + (ki + nm) * T_max) / N_p

    ps = sorted(det["payoffs"])

    def perc(p: float) -> float:
        return round(ps[int(N_p * p)] * 100, 2)

    # Two generic, payoff-shape-agnostic proxies used by the reinvestment
    # candidate scan (see MEMORY investment-solution-module): capital loss =
    # discounted payoff below capital_ref (doesn't distinguish PV timing from
    # nominal loss, but needs no product-specific knowledge), full coupon =
    # payoff within 0.5% of the best path observed (the "everything went
    # right" tail).
    max_payoff = ps[-1] if ps else 0.0
    capital_loss_count = sum(1 for p in ps if p < capital_ref)
    full_coupon_count = sum(1 for p in ps if max_payoff > 0 and p >= max_payoff * 0.995)

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
        "ki_pct": round(ki / N_p * 100, 1),
        "autocall_pct": round(ac / N_p * 100, 1),
        "capital_loss_pct": round(capital_loss_count / N_p * 100, 1),
        "full_coupon_pct": round(full_coupon_count / N_p * 100, 1),
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
                        user_params=None,
                        barrier_monitoring: str = "weekly") -> dict:
    """Run the full nested Monte Carlo Mark-to-Future analysis (see module section
    docstring above). main_price is the t=0 fair price (% of notional); it is only
    used as the threshold for the P(MTM >= P0) diagnostic.

    Inner simulation is processed in chunks of outer scenarios (MTF_MAX_BATCH paths
    at a time) to bound peak memory regardless of how large n_outer * n_inner gets."""
    if model == "lsv":
        raise ValueError(
            "Local-Stochastic Vol n'est pas encore supporté en Mark-to-Future "
            "(le rebucketing par pas de temps ne s'intègre pas encore à la boucle "
            "chunkée). Choisissez un autre modèle (Heston, SABR, Local Vol, Constant)."
        )
    if barrier_monitoring == "continuous":
        raise ValueError(
            "Le monitoring continu des barrières n'est pas encore supporté en "
            "Mark-to-Future (l'héritage d'état outer→inner reste sur extrema "
            "hebdomadaires). Repassez en monitoring hebdomadaire pour cette analyse."
        )
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
                    step_map.setdefault(max(1, round(d * SY)), []).append(ev)

        lv_grids = nK = lkm = lkx = None
        if use_lv:
            # Mark-to-Future is flat-rate throughout (outer, inner and
            # discounting) — no caller passes it a curve. Wiring it to one is a
            # new capability, not a fix, and is out of this change's scope.
            lv_grids, nK, lkm, lkx = _build_lv_grid(
                underlyings, _build_rate_term([], ts_eff, dt, r), ts_eff, dt)

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

def _historical_running_extrema(prices_by_ticker: dict, tickers: list[str], ref: dict,
                                 lo_hi: int, hi_hi: int) -> tuple[float, float]:
    """Worst-of-min / best-of-max across EVERY trading day in (lo_hi, hi_hi] —
    not just the window's endpoint — using the real daily closes already
    loaded for the backtest. A barrier breached and recovered BETWEEN two AT
    observation dates would otherwise be invisible: eval_script_on_history
    used to only look at prices ON the script's own observation dates, even
    though the daily history in between is sitting right there in
    prices_by_ticker. (Unlike the Monte Carlo engine's weekly grid, which has
    no finer data at all and needs a Brownian-bridge reconstruction instead —
    see barrier_monitoring="continuous" — this is real data, not a model.)

    Returns (math.inf, -math.inf) if the window is empty or no ticker has
    data for any day in it — neutral for the caller's running min()/max(),
    so an empty/missing window never falsely narrows or widens the extrema."""
    wmin, bmax = math.inf, -math.inf
    for hi in range(lo_hi + 1, hi_hi + 1):
        spots = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            if r0 > 0 and hi < len(px) and px[hi] > 0:
                spots.append(px[hi] / r0)
        if not spots:
            continue
        wmin = min(wmin, min(spots))
        bmax = max(bmax, max(spots))
    return wmin, bmax


def _historical_per_asset_extrema(prices_by_ticker: dict, tickers: list[str], ref: dict,
                                   lo_hi: int, hi_hi: int) -> tuple[list, list]:
    """Per-asset running min/max (normalized by ref) across every trading day in
    (lo_hi, hi_hi] — the S_MIN[i]/S_MAX[i] counterpart of
    _historical_running_extrema. Assets with no data in the window return
    (inf, -inf), neutral for the caller's running fold."""
    mins = [math.inf] * len(tickers)
    maxs = [-math.inf] * len(tickers)
    for i, tk in enumerate(tickers):
        px = prices_by_ticker.get(tk, [])
        r0 = ref.get(tk, 0)
        if r0 <= 0:
            continue
        for hi in range(lo_hi + 1, min(hi_hi + 1, len(px))):
            if px[hi] > 0:
                v = px[hi] / r0
                if v < mins[i]:
                    mins[i] = v
                if v > maxs[i]:
                    maxs[i] = v
    return mins, maxs


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

    end_idx = len(dates) - 1

    # Daily worst-of series (normalized by ref) over [start_idx, end_idx] and
    # its cumulative squared log-returns — the realized leg of REALVOL. The
    # engine's REALVOL is a quadratic-variation estimator (Σr²/t, no centering),
    # which is sampling-frequency independent: this daily past combines exactly
    # with the simulated weekly future by summing sumsq and times.
    wof_days: list[int] = []
    wof_vals: list[float] = []
    for hi in range(start_idx, end_idx + 1):
        vals = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            if r0 > 0 and hi < len(px) and px[hi] > 0:
                vals.append(px[hi] / r0)
        if vals:
            wof_days.append(hi)
            wof_vals.append(min(vals))
    rv_cum = [0.0] * len(wof_vals)
    _acc = 0.0
    for k in range(1, len(wof_vals)):
        lr = math.log(max(wof_vals[k], 1e-12) / max(wof_vals[k - 1], 1e-12))
        _acc += lr * lr
        rv_cum[k] = _acc

    def _rv_at(hi: int) -> float:
        """Annualized realized vol of the WOF series up to day hi included."""
        k = bisect.bisect_right(wof_days, hi) - 1
        t_y = (hi - start_idx) / SY_H
        return math.sqrt(rv_cum[k] / t_y) if k >= 0 and t_y > 0 else 0.0

    # Realized part of the STRIKE_FIX window: reduce the daily WOF at every
    # fixing date already in the history ("last close <= date" convention,
    # same as _closest_price). Future dates stay with the MC leg.
    fix_state = None
    if compiled.strike_fix_dates:
        f_n, f_sum, f_min, f_max = 0, 0.0, math.inf, -math.inf
        for d in compiled.strike_fix_dates:
            hi = start_idx + round(d * SY_H)
            if hi > end_idx:
                continue
            k = bisect.bisect_right(wof_days, hi) - 1
            if k < 0:
                continue
            v = wof_vals[k]
            f_n += 1
            f_sum += v
            f_min = min(f_min, v)
            f_max = max(f_max, v)
        if f_n:
            fix_state = {"n": f_n, "sum": f_sum, "min": f_min, "max": f_max}

    ctx = {
        "spots": [1.0]*n, "accum": 0.0, "index": 0,
        "wof_min": 1.0, "bof_max": 1.0, "t": 0.0,
        "s_min": [1.0]*n, "s_max": [1.0]*n, "s_prev": [1.0]*n, "realvol": 0.0,
        # FIX_* from the realized window when any fixing date is already past;
        # neutral 1.0 (day-0) otherwise. Constant through the replay — same
        # per-path-constant semantics as the MC engine's _compute_strike_fix.
        "fix_min": fix_state["min"] if fix_state else 1.0,
        "fix_max": fix_state["max"] if fix_state else 1.0,
        "fix_avg": fix_state["sum"] / fix_state["n"] if fix_state else 1.0,
        "done": False, "memo": full_params, "total_cf": 0.0,
    }
    if compiled.init_fn:
        compiled.init_fn(ctx)

    cfs: list[dict] = []
    done = False
    obs_idx = 0
    wof_run = 1.0
    bof_run = 1.0
    s_min_run = [1.0] * n
    s_max_run = [1.0] * n
    T_actual = T_max
    prev_hi = start_idx   # last day scanned for running extrema (inception = spot 1.0, already the seed)

    for step in sorted(step_map.keys()):
        hi = start_idx + step
        if hi >= len(dates):
            break
        # Fold in every trading day since the last observation (or inception)
        # before evaluating the script's condition at this date — see
        # _historical_running_extrema.
        w_win, b_win = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, hi)
        wof_run = min(wof_run, w_win)
        bof_run = max(bof_run, b_win)
        pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, hi)
        s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
        s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]
        prev_hi = hi

        spots = []
        for tk in tickers:
            px = prices_by_ticker.get(tk, [])
            r0 = ref.get(tk, 0)
            spots.append(px[hi] / r0 if r0 > 0 and hi < len(px) else 1.0)
        t_y = step / SY_H
        ctx.update({"spots": spots, "s_prev": list(ctx["spots"]),
                    "s_min": list(s_min_run), "s_max": list(s_max_run),
                    "realvol": _rv_at(hi),
                    "t": t_y, "wof_min": wof_run,
                    "bof_max": bof_run, "index": obs_idx + 1})
        obs_idx += 1
        for ev in step_map[step]:
            if done:
                break
            st = {"flows": [], "done": False}
            try:
                ev.fn(ctx, st)
            except Exception as e:
                raise ValueError(
                    f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                ) from e
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
            w_win, b_win = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, mhi)
            wof_run = min(wof_run, w_win)
            bof_run = max(bof_run, b_win)
            pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, mhi)
            s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
            s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]
            spots = []
            for tk in tickers:
                px = prices_by_ticker.get(tk, [])
                r0 = ref.get(tk, 0)
                spots.append(px[mhi] / r0 if r0 > 0 and mhi < len(px) else 1.0)
            ctx.update({"spots": spots or [1.0]*n, "s_prev": list(ctx["spots"]),
                        "s_min": list(s_min_run), "s_max": list(s_max_run),
                        "realvol": _rv_at(mhi),
                        "t": T_max,
                        "wof_min": wof_run, "bof_max": bof_run})
            for ev in mat_events:
                if done:
                    break
                st = {"flows": [], "done": False}
                try:
                    ev.fn(ctx, st)
                except Exception as e:
                    raise ValueError(
                        f"Erreur d'exécution du script (événement {ev.type}, t={ctx['t']:.4f}) : {e}"
                    ) from e
                for fl in st["flows"]:
                    cfs.append({"t": T_max, "cf": fl["v"]})
                if st["done"]:
                    done = True

    # Fold the days between the last replayed observation and the end of the
    # available history into the extrema: a continuously-monitored KI touched
    # BETWEEN two observation dates must show in the inherited state (min/max
    # folding is idempotent, re-folding an already-scanned window is harmless).
    if end_idx > prev_hi:
        w_tail, b_tail = _historical_running_extrema(prices_by_ticker, tickers, ref, prev_hi, end_idx)
        wof_run = min(wof_run, w_tail)
        bof_run = max(bof_run, b_tail)
        pa_min, pa_max = _historical_per_asset_extrema(prices_by_ticker, tickers, ref, prev_hi, end_idx)
        s_min_run = [min(a, b) for a, b in zip(s_min_run, pa_min)]
        s_max_run = [max(a, b) for a, b in zip(s_max_run, pa_max)]

    return {
        "cash_flows": cfs,
        "early_recall": T_actual < T_max,
        "T_actual": T_actual,
        # Daily worst-of trajectory over the replayed window — already
        # computed above for the REALVOL leg, just exposed here so a caller
        # can chart the PRODUCT's actual path (not just the raw underlying),
        # e.g. the reinvestment proposal backtest (api/deals.py).
        "wof_series": {"dates": [dates[d] for d in wof_days], "values": [round(v, 4) for v in wof_vals]},
        # Final replayed state — what a residual-MtM Monte Carlo must inherit
        # to continue this product's life instead of restarting it: script
        # variables (SET / memory coupons live in memo), the observation
        # counter (PARAM() arrays read their row from it), the realized
        # running extrema (basket AND per-asset), the accumulator, the spots
        # at the last past observation (S_PREV of the first residual one), the
        # realized quadratic variation of the WOF series (REALVOL leg) and the
        # realized part of the STRIKE_FIX window. See api/deals.py:deal_mtm.
        "state": {
            "memo": dict(ctx["memo"]),
            "index": obs_idx,
            "wof_min": wof_run,
            "bof_max": bof_run,
            "accum": ctx.get("accum", 0.0),
            "s_min": list(s_min_run),
            "s_max": list(s_max_run),
            "s_prev": list(ctx["spots"]),
            "wof_last": wof_vals[-1] if wof_vals else 1.0,
            "realvol_state": {"sumsq": rv_cum[-1] if rv_cum else 0.0,
                              "t": max(0.0, (end_idx - start_idx) / SY_H)},
            "fix_state": fix_state,
        },
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
