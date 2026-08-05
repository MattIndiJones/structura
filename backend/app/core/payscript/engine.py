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
# Largest coefficient move a nearest-PSD repair may make before the matrix is
# rejected outright rather than silently used (see cholesky).
CORR_REPAIR_TOL = 0.02
MODELS = ("constant", "heston", "sabr", "localvol", "lsv")
PSI_C = 1.5   # Heston QE switching threshold
MTF_MAX_BATCH = 20_000   # cap simulated paths per inner Mark-to-Future chunk (memory bound)
# Below this many surviving contracts a Mark-to-Future date is flagged `thin`:
# on a highly callable product the late dates can be left with a handful of
# paths, and a 5th percentile read off them is noise wearing the clothes of a
# risk figure. The figures are still returned — suppressing them belongs to the
# display, not to the engine, or a caller running a small deliberate batch gets
# empty results with no explanation.
MTF_MIN_ALIVE = 50


# ── Cholesky decomposition ──────────────────────────────────────────

def validate_model(model: str, underlyings) -> None:
    """Reject an unknown model and out-of-domain diffusion parameters.

    Both used to pass. An unrecognised model name fell through to the GBM
    branch, so the price was computed under a model nobody asked for and
    nothing recorded the substitution. And the Heston/SABR parameters were
    taken at face value: xi=0 divided by zero, while a negative variance or a
    correlation of -1.5 produced perfectly finite, perfectly meaningless
    prices — the worst kind, because they look usable."""
    if model not in MODELS:
        raise ValueError(
            f"Modèle inconnu : {model!r} — valeurs admises : {', '.join(MODELS)}.")

    def _check(cond: bool, name: str, got, expected: str) -> None:
        if not cond:
            raise ValueError(
                f"Paramètre {name} invalide pour le modèle {model} "
                f"sur {u.get('name', '?')} : {got} — attendu {expected}.")

    for u in underlyings:
        if model in ("heston", "lsv"):
            _check(u.get("v0", 0.04) > 0, "v0", u.get("v0"), "> 0 (variance initiale)")
            _check(u.get("theta", 0.04) > 0, "theta", u.get("theta"), "> 0 (variance long terme)")
            _check(u.get("kappa", 2.0) > 0, "kappa", u.get("kappa"), "> 0 (retour à la moyenne)")
            _check(u.get("xi", 0.35) > 0, "xi", u.get("xi"), "> 0 (vol de la variance)")
            _check(abs(u.get("rho_h", 0.0)) <= 1.0, "rho_h", u.get("rho_h"), "dans [-1, 1]")
        if model == "sabr":
            _check(u.get("alpha", 0.20) > 0, "alpha", u.get("alpha"), "> 0")
            _check(0.0 <= u.get("beta", 1.0) <= 1.0, "beta", u.get("beta"), "dans [0, 1]")
            _check(abs(u.get("rho", 0.0)) <= 1.0, "rho", u.get("rho"), "dans [-1, 1]")
            _check(u.get("nu", 0.40) >= 0, "nu", u.get("nu"), ">= 0")


def cholesky(corr: list[list[float]], n: int,
             repair_report: dict | None = None) -> np.ndarray:
    C = np.array(corr, dtype=np.float64)
    if not np.allclose(np.diag(C), 1.0, atol=1e-6):
        raise ValueError("Matrice de corrélation invalide : la diagonale doit valoir 1.")
    if not np.allclose(C, C.T, atol=1e-6):
        raise ValueError("Matrice de corrélation invalide : elle doit être symétrique.")
    if np.abs(C).max() > 1.0 + 1e-9:
        raise ValueError("Matrice de corrélation invalide : les coefficients doivent rester dans [-1, 1].")
    eigvals = np.linalg.eigvalsh(C)
    # `< 0` missed the exactly-singular case: a PSD matrix such as [[1,1],[1,1]]
    # has a zero eigenvalue, skipped the jitter, and then blew up inside
    # np.linalg.cholesky as a raw LinAlgError. Jitter on "not comfortably
    # positive" instead.
    if eigvals.min() < 1e-10:
        C_fixed = C + (max(0.0, -eigvals.min()) + 1e-8) * np.eye(n)
        # The jitter pushes the diagonal above 1 (silently inflating every vol
        # by sqrt(1+eps)) — renormalize back to a unit-diagonal correlation.
        d = np.sqrt(np.diag(C_fixed))
        C_fixed = C_fixed / np.outer(d, d)
        shift = float(np.abs(C_fixed - C).max())
        # Repairing a badly non-PSD matrix is not a rounding fix: a 3-asset
        # book entered at rho=-0.9 projects to rho=-0.5, and the worst-of that
        # comes out is priced on a dependence nobody asked for. Below the
        # tolerance the move is numerical noise and is merely reported; above
        # it, refuse rather than quietly price a different product.
        if shift > CORR_REPAIR_TOL:
            raise ValueError(
                f"Matrice de corrélation non définie positive : la projection la "
                f"plus proche déplace un coefficient de {shift:.3f} (tolérance "
                f"{CORR_REPAIR_TOL:.2f}). Le prix porterait sur une structure de "
                f"dépendance différente de celle saisie — corrigez la matrice.")
        if repair_report is not None:
            repair_report["max_shift"] = round(shift, 8)
            repair_report["matrix_used"] = [[round(float(v), 8) for v in row]
                                            for row in C_fixed]
        C = C_fixed
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


def _validate_dividend_curve(curve: list, q_first_year: float) -> list[list[float]]:
    """Validate the annual, declining yield-curve contract used by Structura.

    The HTTP schema catches malformed requests, but lifecycle and compute
    workflows also call the engine directly with dictionaries. Validation
    therefore lives at the consumption boundary as well: a malformed frozen
    snapshot must fail visibly rather than produce a plausible price.
    """
    normalized: list[list[float]] = []
    previous_q = math.inf
    previous_maturity = 0.0
    for node in curve:
        if not isinstance(node, (list, tuple)) or len(node) != 2:
            raise ValueError("Chaque nœud de dividende doit contenir [maturité, taux].")
        maturity, rate = float(node[0]), float(node[1])
        if not (math.isfinite(maturity) and math.isfinite(rate)):
            raise ValueError("La courbe de dividende contient une valeur non finie.")
        if maturity <= previous_maturity + 1e-12:
            raise ValueError(
                "Les maturités de la courbe de dividende doivent être "
                "strictement croissantes et positives."
            )
        if rate < 0.0:
            raise ValueError("Un rendement de dividende ne peut pas être négatif.")
        if rate > previous_q + 1e-12:
            raise ValueError("La courbe de dividende dégressive doit être non croissante.")
        normalized.append([maturity, rate])
        previous_maturity = maturity
        previous_q = rate

    if normalized and abs(normalized[0][1] - float(q_first_year)) > 1e-12:
        raise ValueError(
            "Le premier bucket de la courbe de dividende doit être égal à q "
            "(hypothèse de première année)."
        )
    return normalized


def _build_dividend_step_matrix(underlyings, ts: int, dt: float) -> np.ndarray | None:
    """Piecewise-constant q applied to each simulation step and underlying.

    Nodes are bucket END dates: [1, q1] means q1 on (0, 1Y], [2, q2]
    means q2 on (1Y, 2Y], and the last node is extended if the simulation
    horizon is longer. Returning None when every curve is empty is deliberate:
    all legacy simulations then keep their scalar-q arithmetic bit for bit.
    """
    raw_curves = [u.get("dividend_curve") or [] for u in underlyings]
    if not any(raw_curves):
        return None

    times = (np.arange(ts, dtype=np.float64) + 1.0) * dt
    q_steps = np.empty((ts, len(underlyings)), dtype=np.float64)
    for asset_index, (u, raw_curve) in enumerate(zip(underlyings, raw_curves)):
        q_flat = float(u.get("q", 0.02))
        if not raw_curve:
            q_steps[:, asset_index] = q_flat
            continue
        curve = _validate_dividend_curve(raw_curve, q_flat)
        ends = np.asarray([node[0] for node in curve], dtype=np.float64)
        rates = np.asarray([node[1] for node in curve], dtype=np.float64)
        bucket_index = np.searchsorted(ends, times, side="left")
        q_steps[:, asset_index] = rates[np.minimum(bucket_index, len(rates) - 1)]
    return q_steps


def _build_lv_grid(underlyings, rates: "_RateTerm", ts: int, dt: float, nK: int = 50):
    """Precompute local vol grid (ts, nK) for each underlying asset.

    Takes the run's rate term rather than a scalar so the Black-Scholes prices
    the Dupire inversion is built on are discounted at the same curve that
    discounts the payoff — the calibration is the third place a rate enters a
    pricing run, and it used to be the one nobody wired to the curve."""
    logKmin, logKmax = math.log(0.20), math.log(3.0)
    Ks = [math.exp(logKmin + i/(nK-1)*(logKmax-logKmin)) for i in range(nK)]
    grids = []
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)
    for asset_index, u in enumerate(underlyings):
        sig0 = u.get("sigma", 0.20)
        skew = u.get("skew", 0.0)
        curv = u.get("curvature", 0.0)
        q_flat = u.get("q", 0.02)
        g = np.zeros((ts, nK), dtype=np.float32)
        for step in range(ts):
            T_s = (step + 1) * dt
            # Zero rate to this maturity — the right discount for a call
            # expiring at T_s. Falls back to the scalar when there is no curve.
            r_s = rates.r_flat if rates.zero is None else float(rates.zero[step + 1])
            # The Dupire surface needs the same cumulative dividend carry as
            # the paths. For a term structure this is the continuously
            # compounded zero-equivalent q(0,T); for the legacy flat case the
            # scalar is retained exactly.
            q_s = (q_flat if dividend_steps is None
                   else float(dividend_steps[:step + 1, asset_index].mean()))
            for ki, K in enumerate(Ks):
                lv = _dupire_vol(K, T_s, sig0, skew, curv, r_s, q_s)
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
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)
    for i, u in enumerate(underlyings):
        sig = u.get("sigma", 0.20)
        if vol_add is not None:
            sig = max(0.005, sig + vol_add[i])
        if vol_out is not None:
            vol_out[:, i, :] = sig
        z_i = _blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0)) if Z_r is not None else Zc[:, i, :]
        q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
        q_term = (u.get("q", 0.02) if dividend_steps is None
                  else dividend_steps[:, i, None])
        drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5 * sig * sig
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
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

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
            #
            # This is deliberate and it has a price: the resulting vega covers
            # only the independent leg, so it is scaled by (1-rho_h^2) — half
            # the true sensitivity at rho_h=-0.7, a fifth at -0.9. Scaling
            # corr_term to reach the correlated leg does NOT fix it: that term
            # is Andersen's exact substitution for rho/xi*integral(dV) and
            # carries its own compensator, so rescaling it shifts E[log S] with
            # nothing to offset it (measured: +40bp on a prepaid forward at
            # rho_h=-0.7). A genuine Heston vega means bumping the calibrated
            # parameters, not the diffusion legs — hence `vega_scope` below,
            # which reports the coverage rather than pretending it is total.
            bumped_variance = rh*rh * V_bar + rhop*rhop * sv*sv
            q_term = (u.get("q", 0.02) if dividend_steps is None
                      else dividend_steps[step, i])
            drift = (r_term + u.get("ccyh", 0.0) - q_term
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
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

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
            q_term = (u.get("q", 0.02) if dividend_steps is None
                      else dividend_steps[step, i])
            drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5 * sig**2
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
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

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
            q_term = (u.get("q", 0.02) if dividend_steps is None
                      else dividend_steps[step, i])
            drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5*lvs**2
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
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

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
            q_term = (u.get("q", 0.02) if dividend_steps is None
                      else dividend_steps[step, i])
            drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5*eff_vol**2
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

    Weight of shock Z_i in I_m = dt*sum_{k=i}^{m-1} x_k gives Var(I_m) in closed
    form for both schemes; psi_k is its increment per unit of time.
    """
    m = np.arange(1, ts + 1, dtype=np.float64)
    if a_r <= 0.0:
        # x_k = sigma*sqrt(dt)*sum_{i<=k} Z_i  ->  weight of Z_i is
        # dt*sigma*sqrt(dt)*(m-i), so Var(I_m) = sigma^2 dt^3 sum_{j=1..m} j^2.
        var_I = sigma_r ** 2 * dt ** 3 * m * (m + 1.0) * (2.0 * m + 1.0) / 6.0
    else:
        one_m_phi = 1.0 - phi
        # weight of Z_i is dt*step_sd*(1-phi^(m-i))/(1-phi)
        ssum = (m
                - 2.0 * phi * (1.0 - phi ** m) / one_m_phi
                + phi * phi * (1.0 - phi ** (2.0 * m)) / (1.0 - phi * phi))
        var_I = dt * dt * step_sd ** 2 / (one_m_phi ** 2) * ssum
    half = 0.5 * var_I
    psi = np.empty(ts, dtype=np.float64)
    psi[0] = half[0] / dt
    psi[1:] = (half[1:] - half[:-1]) / dt
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
    ts, N = Z_r.shape
    if a_r <= 0.0:
        x = sigma_r * sq_dt * np.cumsum(Z_r, axis=0)
        psi = _hw_convexity(sigma_r, a_r, dt, ts)
    else:
        phi = math.exp(-a_r * dt)
        step_sd = sigma_r * math.sqrt(max(0.0, (1.0 - phi * phi) / (2.0 * a_r)))
        x = np.empty((ts, N), dtype=np.float64)
        x_prev = np.zeros(N, dtype=np.float64)
        for k in range(ts):
            x_prev = phi * x_prev + step_sd * Z_r[k]
            x[k] = x_prev
        psi = _hw_convexity(sigma_r, a_r, dt, ts, phi=phi, step_sd=step_sd)

    # phi(t) applies to the rate itself, not just to the discounting: the same
    # path feeds each asset's drift, so correcting one and not the other would
    # trade a curve-fit error for an arbitrage between forwards and bonds.
    r_path = fwd[:, None] + x + psi[:, None]                   # (ts, N)
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
    if eig.min() < 1e-12:
        M = M + (max(0.0, -eig.min()) + 1e-12) * np.eye(n)
    return np.linalg.cholesky(M)


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

    def _row(v):
        """One value per path. A single deal's residual MtM inherits ONE realized
        reduction shared by every path; Mark-to-Future inherits one PER PATH (each
        outer scenario fixed its own strike). np.full only handles the first."""
        return np.broadcast_to(np.asarray(v, dtype=float), (N,)).astype(float, copy=True)

    if not steps:   # window fully realized — no simulated fixing left to combine
        return (_row(p_min), _row(p_max), _row(np.asarray(p_sum, dtype=float) / p_n))
    window = WOF[[s - 1 for s in steps], :]
    return (np.minimum(window.min(axis=0), p_min),
            np.maximum(window.max(axis=0), p_max),
            (window.sum(axis=0) + p_sum) / (len(steps) + p_n))


def _state_by_asset(v, n: int, N: int) -> np.ndarray:
    """Realized per-asset state, shared by every path (n,) or one per path (n, N)."""
    a = np.asarray(v, dtype=float)
    return a.reshape(1, n, 1) if a.ndim == 1 else a.reshape(1, n, N)


def _eval_paths(script: CompiledScript, S: np.ndarray, ts: int, n: int, N: int,
                dt: float, r_eff: float, user_params: dict,
                step_map: dict, mat_events: list, flux_map: dict,
                record: bool, df_arr: np.ndarray | None = None,
                wof_min_init=None, bof_max_init=None,
                stop_times_out: list | None = None,
                flows_out: list | None = None,
                bridge_min=None, bridge_max=None,
                index_offset: int = 0, memo_init: dict | None = None,
                accum_init: float = 0.0,
                s_min_init=None, s_max_init=None, s_prev_init=None,
                wof0_init: float | None = None,
                realvol_state_init: dict | None = None,
                fix_state_init: dict | None = None,
                state_out: list | None = None) -> list[float]:
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

    Mark-to-Future (run_mark_to_future) feeds all of them, one value PER PATH:
    each outer scenario reaches the mark date with its own contractual history,
    so S_MIN/S_MAX/S_PREV/REALVOL/FIX_* cannot share a state across the batch.
    fix_state_init was the last one still missing there, and its absence marked
    an Asian-strike product as if its strike had never been fixed.

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
    # Every *_init below accepts either one value shared by all paths — the
    # residual MtM of a single deal — or one value per path. The latter is what
    # Mark-to-Future needs: each outer scenario reaches the mark date with its
    # own contractual history, so they cannot share a state.
    if s_min_init is not None:
        S_min = np.minimum(S_min, _state_by_asset(s_min_init, n, N))
    if s_max_init is not None:
        S_max = np.maximum(S_max, _state_by_asset(s_max_init, n, N))
    if wof0_init is None:
        wof0_row = np.full((1, N), 1.0)
    else:
        wof0_row = np.asarray(wof0_init, dtype=float).reshape(1, -1) * np.ones((1, N))
    WOF_full = np.vstack([wof0_row, WOF])   # (ts+1, N) — WOF(t=0)
    log_ret = np.diff(np.log(np.maximum(WOF_full, 1e-12)), axis=0)   # (ts, N)
    cum_sq_ret = np.cumsum(log_ret ** 2, axis=0)    # (ts, N)
    rv_sumsq0 = realvol_state_init["sumsq"] if realvol_state_init else 0.0
    rv_t0 = realvol_state_init["t"] if realvol_state_init else 0.0
    _rv_by_path = np.ndim(rv_sumsq0) > 0
    _accum_by_path = np.ndim(accum_init) > 0
    _index_by_path = np.ndim(index_offset) > 0
    _memo_by_path = isinstance(memo_init, (list, tuple))
    _sprev = None if s_prev_init is None else np.asarray(s_prev_init, dtype=float)
    _sprev_by_path = _sprev is not None and _sprev.ndim == 2

    obs_steps = sorted(step_map.keys())
    payoffs: list[float] = []
    payoffs_raw: list[float] = []   # undiscounted total cash flow per path

    # PARAM defaults first, user_params (partial or full) override — a caller
    # that omits a param must fall back to its script default, not silently 0.
    full_params = {p.name: p.stored_val for p in script.params}
    full_params.update(user_params)

    for path in range(N):
        # Dated cash flows of THIS path, when the caller asks for them.
        # `flux_map` aggregates across paths, so it cannot answer "when did
        # this particular scenario pay" — which is exactly what an internal
        # rate of return needs. Off by default: it is the only per-path
        # structure here that grows with the number of flows.
        path_flows: list | None = [] if flows_out is not None else None
        if _sprev is None:
            _spots0 = [1.0] * n
        else:
            _spots0 = list(_sprev[:, path]) if _sprev_by_path else list(_sprev)
        ctx = {
            # s_prev_init seeds "spots" (not "s_prev"): the first observation
            # copies spots -> s_prev before overwriting spots, so the real
            # previous fixing lands in S_PREV through the normal mechanics.
            "spots": _spots0,
            "accum": float(accum_init[path]) if _accum_by_path else accum_init,
            "index": 0,
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
        _memo = memo_init[path] if _memo_by_path else memo_init
        if _memo:
            ctx["memo"].update(_memo)

        done = False
        obs_idx = int(index_offset[path]) if _index_by_path else index_offset
        _rv_s0 = float(rv_sumsq0[path]) if _rv_by_path else rv_sumsq0
        _rv_t = float(rv_t0[path]) if _rv_by_path else rv_t0

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
                              math.sqrt((_rv_s0 + cum_sq_ret[step - 1, path])
                                        / (_rv_t + step * dt)))
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
                    if path_flows is not None and fl["v"] != 0:
                        path_flows.append((ctx["t"], fl["v"]))
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
                              math.sqrt((_rv_s0 + cum_sq_ret[ts - 1, path])
                                        / (_rv_t + ts * dt)))
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
                    if path_flows is not None and fl["v"] != 0:
                        path_flows.append((ctx["t"], fl["v"]))
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
        if flows_out is not None:
            flows_out.append(path_flows)
        if stop_times_out is not None and not ctx["done"]:
            stop_times_out.append(ts * dt)
        if state_out is not None:
            # The contractual position this path has reached at the end of the
            # tensor — everything a residual repricing needs to continue from
            # here rather than start over. Mark-to-Future replays each outer
            # scenario up to its mark date and feeds this straight back in.
            state_out.append({
                "done": done,
                "realized_cf": ctx["total_cf"],
                "index": obs_idx,
                "memo": dict(ctx["memo"]),
                "accum": ctx["accum"],
                "s_prev": list(ctx["spots"]),
                "wof_min": float(WOF_min[ts - 1, path]),
                "bof_max": float(BOF_max[ts - 1, path]),
                "s_min": [float(v) for v in S_min[ts - 1, :, path]],
                "s_max": [float(v) for v in S_max[ts - 1, :, path]],
                "realvol_sumsq": float(_rv_s0 + cum_sq_ret[ts - 1, path]),
                "realvol_t": _rv_t + ts * dt,
                "wof_last": float(WOF[ts - 1, path]),
            })

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
           fix_state_init: dict | None = None,
           per_path_flows: bool = False):

    t0 = time.perf_counter()
    if barrier_monitoring not in ("weekly", "continuous"):
        raise ValueError(
            f"barrier_monitoring invalide: {barrier_monitoring!r} — valeurs admises: "
            f"'weekly' (extrema aux pas hebdomadaires, défaut) ou 'continuous' "
            f"(pont brownien intra-pas)."
        )
    use_bridge = barrier_monitoring == "continuous"
    validate_model(model, underlyings)
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
    corr_repair: dict = {}
    L = cholesky(corr, n, repair_report=corr_repair)

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

    # Coupling the assets to the rate factor changes how the diffusion block
    # must be factorised — see _blend_rate_factor. Only when the factor is
    # actually live AND at least one asset is correlated to it: otherwise L
    # stays chol(R) and every existing price is reproduced to the bit.
    rho_rS_vec = [float(u.get("rho_rS", 0.0) or 0.0) for u in underlyings]
    if use_stoch_rate and any(v != 0.0 for v in rho_rS_vec):
        L = _rate_coupled_factor(corr_repair.get("matrix_used") or corr,
                                 rho_rS_vec, n)

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
    flows_base: list | None = [] if per_path_flows else None
    payoffs_base, raw_base = _eval_paths(script, S_base, ts, n, N_pairs, dt, r_eff,
                                          user_params, step_map, mat_events, flux_map,
                                          record=True, df_arr=df_base,
                                          stop_times_out=stop_times_base,
                                          flows_out=flows_base,
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
        # The antithetic leg is the same draw with the sign flipped: it needs no
        # new randomness, and it should need no new memory either. Two
        # allocations happened anyway. `-Z` built a full copy of every normal
        # tensor, and the base leg's paths stayed alive while the antithetic
        # ones were allocated, so the peak carried two path tensors instead of
        # one. Flipping in place and releasing the base leg first removes both:
        # for a 3-year weekly run at 100k paths that is roughly 500 MB back.
        # Negation is exact in IEEE-754 and nothing below re-reads the base
        # arrays, so every price is unchanged to the bit.
        del S_base, br_min_b, br_max_b
        np.negative(Z, out=Z)
        if Zv is not None:
            np.negative(Zv, out=Zv)
        if Za is not None:
            np.negative(Za, out=Za)
        if Z_r is not None:
            np.negative(Z_r, out=Z_r)
        Z_r_anti = Z_r if use_stoch_rate else None
        # Same buffer as the base leg — its bridge extrema were drawn above and
        # nothing reads it any more.
        vol_anti = vol_base
        if use_heston:
            S_anti = _simulate_heston(ts, n, N_pairs, dt, sq_dt, underlyings,
                                       r_eff, L, Z, Zv, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                       vol_out=vol_anti)
        elif use_lsv:
            S_anti = _simulate_lsv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, Z, Zv, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                    r_path_anti, Z_r_anti, vol_out=vol_anti)
        elif use_lv:
            S_anti = _simulate_lv(ts, n, N_pairs, dt, sq_dt, underlyings,
                                   r_eff, L, Z, lv_grids, nK, lkm, lkx, _sim_spot_mult, vol_add,
                                   r_path_anti, Z_r_anti, vol_out=vol_anti)
        elif use_sabr:
            S_anti = _simulate_sabr(ts, n, N_pairs, dt, sq_dt, underlyings,
                                     r_eff, L, Z, Za, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                     vol_out=vol_anti)
        else:
            S_anti = _simulate_gbm(ts, n, N_pairs, dt, sq_dt, underlyings,
                                    r_eff, L, Z, _sim_spot_mult, vol_add, r_path_anti, Z_r_anti,
                                    vol_out=vol_anti)
        S_anti = _apply_delayed_bump(S_anti)
        br_min_a, br_max_a = _bridge_extrema(S_anti, vol_anti, dt, rng) if use_bridge else (None, None)
        stop_times_anti: list[float] | None = [] if script.has_stop else None
        flows_anti = [] if per_path_flows else None
        payoffs_anti, raw_anti = _eval_paths(script, S_anti, ts, n, N_pairs, dt, r_eff,
                                              user_params, step_map, mat_events, {},
                                              record=False, df_arr=df_anti,
                                              stop_times_out=stop_times_anti,
                                              flows_out=flows_anti,
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
        # Dated cash flows, one list of (t, montant) per path — opt-in, since
        # this is the only output that grows with the number of flows.
        # `payoffs` above is a plain sum: it says a path paid 1.08 but not
        # that it paid it after one year, so nothing downstream can work out
        # the return the investor actually earned. `flux_table` aggregates
        # across paths and cannot answer it either. This can.
        **({"path_flows": (flows_base + flows_anti) if flows_anti else flows_base}
           if per_path_flows else {}),
        "flux_table": flux_map,
        "elapsed_ms": round(elapsed, 1),
        "n_paths": N,
        "n_eff": N_eff,
        "fugit": fugit,
        # Present only when the correlation matrix had to be projected onto the
        # nearest PSD one. Small moves are numerical noise, but the caller is
        # entitled to know the price used a matrix it did not supply.
        "corr_repair": corr_repair or None,
        # The bridge is an approximation of continuous monitoring, and a biased
        # one: measured against Merton's closed form on a down-and-out call
        # struck at the money with a 95% barrier, it prices 14.3% low, while
        # the weekly path matches an independent simulation to 1.5bp. It kills
        # too many paths, so every knock-out is undervalued and every knock-in
        # overvalued. Flagged rather than silently trusted.
        "barrier_monitoring": barrier_monitoring,
        "barrier_monitoring_note": (
            "Monitoring continu approché par pont brownien — biais mesuré "
            "d'environ -14% sur une barrière proche de la monnaie (référence : "
            "formule de Merton). Le mode hebdomadaire, lui, est exact."
        ) if use_bridge else None,
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
        # Under Heston (and LSV, which inherits its variance process) the vol
        # bump reaches only the leg independent of the variance Brownian, so
        # the figure above covers a fraction (1-rho_h^2) of the true volatility
        # sensitivity — half of it at the usual equity skew, a fifth at -0.9.
        # It is a real sensitivity, just not the one the bare word "vega"
        # implies, and a book aggregate that mixes it with GBM vegas is adding
        # quantities of different scope. Say so rather than let the label pass.
        if model in ("heston", "lsv"):
            greeks["vega_scope"] = {
                "type": "leg_independante",
                "coverage": {u.get("name", f"S{i+1}"):
                             round(1.0 - float(u.get("rho_h", 0.0))**2, 4)
                             for i, u in enumerate(underlyings)},
            }
        else:
            greeks["vega_scope"] = {"type": "total", "coverage": None}

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
    # Per calendar day: the product was aged by dt_step YEARS, which is
    # 365.25*dt_step days on the engine's own day-count — 7.02 on the weekly
    # grid, not 7. Hard-coding 7 was right only by coincidence of SY=52, and
    # would have silently rescaled every theta by SY/52 the day the grid
    # changed: at 252 steps the product ages 1.45 days while the result would
    # still be divided by 7, understating decay almost fivefold.
    per_day = 365.25 * dt_step
    return round((aged - base_g) / per_day, 4), None


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
    avoids re-pricing a degenerate near-zero-maturity residual product. Dates are
    floored at one weekly step: the replay of the realized past indexes a path
    tensor of `round(t0 * SY)` steps, and that tensor is empty below half a
    step — a mark "3 days from now" has no grid to stand on."""
    t_last = round(T_max - 1 / SY, 6)
    floor = round(1 / SY, 6)
    out: list[float] = []
    for i in range(n_dates):
        d = max(floor, round(t_last * (i + 1) / n_dates, 4))
        # Two marks landing on the same weekly step are the same mark: identical
        # replay, identical spot, identical inherited state. Only a product too
        # short to carry n_dates distinct steps gets here, and it gets fewer
        # dates rather than a row repeated under two labels.
        if out and _mtf_step(d) <= _mtf_step(out[-1]):
            continue
        out.append(d)
    return out


def _mtf_step(t0: float) -> int:
    """The weekly step a Mark-to-Future date snaps to. Single source of truth:
    the outer replay, the past/future split of the event calendar and the
    residual horizon must all agree on it, or an event lands on both sides."""
    return round(t0 * SY)


def _shift_events_for_mtf(events: list[CompiledEvent], t0: float) -> list[CompiledEvent]:
    """Re-anchor a script's events at t0 for residual pricing: AT event dates already
    resolved by the outer scenario are dropped; remaining dates are shifted by -t0.
    AT_MATURITY is left untouched — it always fires at the end of the residual
    horizon, whatever that horizon is.

    The past/future split is made on the SNAPPED WEEKLY STEP, not on the raw date.
    The outer replay resolves every event whose step is <= step_k; testing `d > t0`
    here instead made the two criteria non-complementary, and an observation falling
    between t0 and its own step boundary (up to half a week, i.e. any date in
    (t0, (step_k + 0.5) / SY]) was replayed by the outer scenario AND repriced by
    the inner one. A phoenix coupon was then paid twice — once into `realized_flows`,
    once into the mark — and the autocall barrier was tested twice a week apart.
    On a realistic CONSTAT calendar (year-fractions in ACT/365.25, so almost never
    exactly on the weekly lattice) this hit ~17% of MTM dates and moved the mark by
    several hundred basis points."""
    step_k = _mtf_step(t0)
    shifted = []
    for ev in events:
        if ev.type != "AT":
            shifted.append(ev)
            continue
        future_dates = [round(d - t0, 6) for d in ev.dates
                        if max(1, round(d * SY)) > step_k]
        if future_dates:
            shifted.append(CompiledEvent(type=ev.type, dates=future_dates, fn=ev.fn))
    return shifted


def _mtf_past_step_map(script: CompiledScript, step_k: int) -> dict[int, list]:
    """AT events the outer scenario has already resolved by the mark date, keyed
    by weekly step. Complement of _shift_events_for_mtf by construction — same
    `max(1, round(d * SY)) <= step_k` test on both sides, one written once."""
    past: dict[int, list] = {}
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            continue
        for d in ev.dates:
            s = max(1, round(d * SY))
            if s <= step_k:
                past.setdefault(s, []).append(ev)
    return past


def _mtf_residual_script(script: CompiledScript, t0: float, T_max: float) -> tuple:
    """Residual contract seen from the mark date: (script, step_map, mat_events,
    ts_eff). Shared by the fan and the drill-down — the panel that explains a
    mark must reprice the very same residual product the fan marked."""
    residual_events = _shift_events_for_mtf(script.events, t0)
    step_k = _mtf_step(t0)
    residual_fix = [round(d - t0, 6) for d in (script.strike_fix_dates or [])
                    if max(1, round(d * SY)) > step_k]
    residual = CompiledScript(events=residual_events, init_fn=script.init_fn,
                              params=script.params, constats=script.constats,
                              has_stop=script.has_stop, monitors=script.monitors,
                              strike_fix_dates=residual_fix or None)
    step_map: dict[int, list] = {}
    mat_events = []
    for ev in residual_events:
        if ev.type == "AT_MATURITY":
            mat_events.append(ev)
        else:
            for d in ev.dates:
                step_map.setdefault(max(1, round(d * SY)), []).append(ev)
    ts_eff = max(1, round(max(1 / SY, round(T_max - t0, 6)) * SY))
    return residual, step_map, mat_events, ts_eff


def _mtf_realized_fix(script: CompiledScript, S_outer: np.ndarray,
                      step_k: int) -> tuple[dict | None, list[int]]:
    """Split a `CONSTAT() STRIKE_FIX` window at the mark date.

    Returns (realized reduction over the fixing dates already behind t0, one entry
    per outer scenario — the shape _compute_strike_fix consumes as fix_state_init —,
    and the list of past steps). Without it the residual repricing saw only the
    still-future fixing dates: a window half elapsed averaged the wrong subset, and
    a window fully elapsed fell back on the neutral 1.0, i.e. an Asian-strike
    product was marked as if its strike had never been fixed."""
    if not script.strike_fix_dates:
        return None, []
    past = sorted({min(max(round(d * SY), 1), step_k) for d in script.strike_fix_dates
                   if max(1, round(d * SY)) <= step_k})
    if not past:
        return None, []
    WOF_out = S_outer[1:step_k + 1].min(axis=1)          # (step_k, N_outer)
    w = WOF_out[[s - 1 for s in past], :]                # (len(past), N_outer)
    return ({"n": len(past), "sum": w.sum(axis=0),
             "min": w.min(axis=0), "max": w.max(axis=0)}, past)


def _simulate_mtf_outer(underlyings, corr_matrix, r: float, mtm_dates: list[float],
                         N: int, seed: int) -> np.ndarray:
    """Outer scenario generator: N correlated GBM paths from t=0 to the last MTM date.

    Returns the spot tensor only. It used to also return running worst-of-min /
    best-of-max series, which no caller read — run_mark_to_future takes those from
    the per-scenario replay instead, because the replay's extrema are the ones that
    stop at each mark date and carry the same path history as the rest of the state.
    Building them here allocated two more (ts, N) arrays per run for nothing."""
    n = len(underlyings)
    dt = 1.0 / SY
    sq_dt = math.sqrt(dt)
    ts = max(1, round(mtm_dates[-1] * SY))
    L = cholesky(corr_matrix, n)
    Z = default_rng(seed).standard_normal((ts, n, N))
    return _simulate_gbm(ts, n, N, dt, sq_dt, underlyings, r, L, Z)


def _mtf_reject_unsupported(model: str, barrier_monitoring: str,
                            yield_curve, sigma_r: float,
                            underlyings=None) -> None:
    """Capabilities Mark-to-Future does not carry. Shared by the fan and the
    drill-down so the two can never disagree on what they accept — a drill-down
    that priced a scenario the fan refuses would explain a number nobody sees."""
    if yield_curve:
        raise ValueError(
            "La courbe de taux n'est pas encore supportée en Mark-to-Future : "
            "l'analyse est à taux plat de bout en bout (dérive outer, dérive "
            "inner et actualisation). La conserver silencieusement comparerait "
            "un éventail actualisé à plat à un P₀ actualisé sur la courbe. "
            "Repassez en taux plat pour cette analyse."
        )
    if sigma_r:
        raise ValueError(
            "Les taux stochastiques ne sont pas encore supportés en "
            "Mark-to-Future : la revalorisation résiduelle ne porte pas le "
            "facteur de taux. Générez l'analyse avec sigma_r = 0."
        )
    if any(u.get("dividend_curve") for u in (underlyings or [])):
        raise ValueError(
            "La courbe de dividende n'est pas encore supportée en "
            "Mark-to-Future : chaque revalorisation future devrait décaler les "
            "buckets de dividende à sa propre date. La réappliquer depuis "
            "l'année 1 donnerait un éventail cohérent en apparence mais faux. "
            "Repassez en dividende plat pour cette analyse."
        )
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


def _mtf_date_stats(pvs: np.ndarray, p0: float) -> dict:
    """Distribution diagnostics for one MTM date (pvs in % of notional).

    Percentiles use the standard linear-interpolation estimator (numpy's default,
    the same one every risk system and spreadsheet reports). The previous
    `sorted[int(p * n)]` returned the (floor(p*n) + 1)-th order statistic, whose
    expected rank is (floor(p*n) + 1) / (n + 1) — badly off in the tails on the
    small samples this function actually sees. Mark-to-Future conditions on
    survival, so a callable product leaves a few dozen contracts alive at the late
    dates: at n = 60 the published "P01" was literally the sample MINIMUM (9 points
    of notional below the true 1st percentile) and "P99" the sample MAXIMUM. Those
    two rows are the tail-risk rows of the fan chart."""
    n = len(pvs)

    def q(p: float) -> float:
        return float(np.quantile(pvs, p))

    mean = float(pvs.mean())
    # ── Décomposition gagnants / perdants ───────────────────────────
    # Espérances CONDITIONNELLES au signe du résultat, à ne pas confondre avec
    # e_upside : celle-ci moyenne max(MTM-100, 0) sur TOUT l'échantillon (elle
    # compte les perdants comme des zéros et répond « combien de potentiel
    # au-dessus du pair ce produit porte-t-il en moyenne »), tandis que
    # avg_gain moyenne le seul sous-échantillon gagnant (« quand ça marche, ça
    # rapporte combien »). Les deux sont utiles et ne disent pas la même chose ;
    # les mélanger est l'erreur de lecture classique sur ce type de tuile.
    #
    # Le seuil est 100 % du nominal, pas P0 : c'est la question « le produit
    # vaut-il plus que le pair », indépendante du prix d'entrée. La probabilité
    # correspondante vis-à-vis du prix payé reste p_above_p0.
    win, lose = pvs[pvs > 100], pvs[pvs < 100]
    nw, nl = int(win.size), int(lose.size)
    return {
        "mean": mean, "std": float(pvs.std(ddof=0)),
        "p01": q(0.01), "p05": q(0.05), "p25": q(0.25), "p50": q(0.50),
        "p75": q(0.75), "p95": q(0.95), "p99": q(0.99),
        "p_above_100": float((pvs > 100).mean() * 100),
        "p_above_p0":  float((pvs >= p0).mean() * 100),
        "e_mtm": mean,
        "e_upside": float(np.maximum(pvs - 100, 0).mean()),
        # None plutôt que 0 quand le sous-échantillon est vide : une moyenne de
        # rien n'est pas zéro, et un « gain moyen des gagnants : 0,00 % » affiché
        # alors qu'il n'y a aucun gagnant se lit comme une information.
        "n_win": nw, "n_lose": nl,
        "e_mtm_win":  float(win.mean()) if nw else None,
        "e_mtm_lose": float(lose.mean()) if nl else None,
        "avg_gain": float((win - 100).mean()) if nw else None,
        "avg_loss": float((100 - lose).mean()) if nl else None,   # magnitude, > 0
        "max_gain": float(win.max() - 100) if nw else None,
        "max_loss": float(100 - lose.min()) if nl else None,      # magnitude, > 0
        "mtm_min": float(pvs.min()), "mtm_max": float(pvs.max()),
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
                        barrier_monitoring: str = "weekly",
                        mtm_dates: list[float] | None = None,
                        yield_curve=None,
                        sigma_r: float = 0.0) -> dict:
    """Run the full nested Monte Carlo Mark-to-Future analysis (see module section
    docstring above). main_price is the t=0 fair price (% of notional); it is only
    used as the threshold for the P(MTM >= P0) diagnostic.

    Inner simulation is processed in chunks of outer scenarios (MTF_MAX_BATCH paths
    at a time) to bound peak memory regardless of how large n_outer * n_inner gets.

    yield_curve / sigma_r are accepted only to be REFUSED: this analysis is
    flat-rate throughout (outer drift, inner drift and discounting all read the
    scalar r). They are in the signature because every caller builds one request
    body for every analytic and would otherwise drop them silently — the price
    would carry the curve and the whole fan would not, including the P0 threshold
    the fan is compared against."""
    _mtf_reject_unsupported(model, barrier_monitoring, yield_curve, sigma_r,
                            underlyings)
    t_run0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    # `mtm_dates` lets a caller ask for the exact dates it needs instead of the
    # evenly-spaced grid. The PRIIPs intermediate horizons use it: they need
    # the value at 1 year and at RHP/2 specifically, and that value is what
    # this function already computes correctly for a recallable product.
    mtm_dates = ([round(float(d), 6) for d in mtm_dates]
                 if mtm_dates else build_mtf_dates(T_max, n_dates))
    # A mark date inside the first half-step snaps to step 0: the replay would
    # then index an empty path tensor and die on `WOF_min[-1]` with an IndexError
    # about axis 0 having size 0 — a stack trace no caller can act on.
    too_early = [d for d in mtm_dates if _mtf_step(d) < 1]
    if too_early:
        raise ValueError(
            f"Date(s) de valorisation trop proche(s) de t=0 : {too_early} — le "
            f"moteur travaille sur une grille hebdomadaire, une date en deçà d'un "
            f"demi-pas ({0.5 / SY:.4f} an, soit 3 jours) n'a aucun pas à rejouer. "
            f"Demandez au minimum {1 / SY:.4f} an (une semaine)."
        )

    S_outer = _simulate_mtf_outer(
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
        step_k = _mtf_step(t0)
        spot_k = S_outer[step_k]                # (n, N_outer) — spot at this MTM date

        # ── Replay each outer scenario from inception to the mark date ──────
        # Without this the inner repricing restarted the contract from scratch:
        # a product already recalled kept being marked as alive (an autocall
        # certain to be called at its first observation stayed near 107% of
        # notional for the rest of its original life, on a fan so degenerate
        # that min and max coincided across every scenario). Coupon memory, the
        # observation counter and realized extrema were lost the same way.
        #
        # The past events are evaluated on the outer paths themselves, with the
        # maturity block withheld — the product has not matured, it has merely
        # reached t0 — and the resulting per-scenario state is fed straight
        # into the inner simulation.
        past_step_map = _mtf_past_step_map(script, step_k)

        outer_states: list[dict] = []
        # Dated flows of what each scenario has ALREADY been paid before the
        # mark date. `realized_cf` is their present value, which is enough to
        # report cash but not to work out the return the investor earned on
        # it — that needs the dates, and a scenario recalled before this
        # horizon has a shorter life than the horizon itself.
        outer_flows: list[list] = []
        _eval_paths(script, S_outer[:step_k + 1], step_k, n, n_outer, dt, r,
                    user_params, past_step_map, [], {}, record=False,
                    state_out=outer_states, flows_out=outer_flows)

        alive = np.array([not st["done"] for st in outer_states])
        # Cash already paid out, expressed at t0 (the replay discounts to t=0).
        # There is deliberately no "cash already paid" series here any more.
        # It only ever described the RECALLED scenarios, and those now leave
        # the sample entirely — so it documented rows nobody looks at, while
        # inviting the reader to add it to a mark it does not belong to. It
        # also carried an exp(r*t0) factor, i.e. the coupon reinvested at the
        # risk-free rate, which a mark-to-future has no business assuming.
        #
        # The dated flows survive as `realized_flows` because the PRIIPs
        # horizons genuinely need them: there the question is "what did the
        # investor receive and when", and an internal rate of return cannot be
        # computed without the dates. Different question, different screen.
        wof_min_k = np.array([st["wof_min"] for st in outer_states])
        bof_max_k = np.array([st["bof_max"] for st in outer_states])
        index_k = np.array([st["index"] for st in outer_states], dtype=np.int64)
        accum_k = np.array([st["accum"] for st in outer_states], dtype=float)
        memo_k = [st["memo"] for st in outer_states]
        s_min_k = np.asarray([st["s_min"] for st in outer_states], dtype=float).T   # (n, N_outer)
        s_max_k = np.asarray([st["s_max"] for st in outer_states], dtype=float).T
        s_prev_k = np.asarray([st["s_prev"] for st in outer_states], dtype=float).T
        rv_sumsq_k = np.array([st["realvol_sumsq"] for st in outer_states])
        rv_t_k = np.array([st["realvol_t"] for st in outer_states])
        wof0_k = spot_k.min(axis=0)             # (N_outer,) — worst-of at the mark date

        # has_stop and the fixing window used to be dropped when rebuilding the
        # residual script, which silently lost its early-redemption flag and its
        # STRIKE_FIX dates. Both now live in _mtf_residual_script, alongside the
        # snapped-step past/future split — a fixing date already averaged into
        # fix_state_k below must not also be re-simulated, or it counts twice.
        fix_state_k, _past_fix = _mtf_realized_fix(script, S_outer, step_k)
        residual_script, step_map, mat_events, ts_eff = _mtf_residual_script(
            script, t0, T_max)

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

            sl = slice(start, end)
            spot_chunk = np.repeat(spot_k[:, sl], n_inner, axis=1)             # (n, N_chunk)

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
                wof_min_init=np.repeat(wof_min_k[sl], n_inner),
                bof_max_init=np.repeat(bof_max_k[sl], n_inner),
                index_offset=np.repeat(index_k[sl], n_inner),
                memo_init=[memo_k[i] for i in range(start, end) for _ in range(n_inner)],
                accum_init=np.repeat(accum_k[sl], n_inner),
                s_min_init=np.repeat(s_min_k[:, sl], n_inner, axis=1),
                s_max_init=np.repeat(s_max_k[:, sl], n_inner, axis=1),
                s_prev_init=np.repeat(s_prev_k[:, sl], n_inner, axis=1),
                wof0_init=np.repeat(wof0_k[sl], n_inner),
                realvol_state_init={"sumsq": np.repeat(rv_sumsq_k[sl], n_inner),
                                    "t": np.repeat(rv_t_k[sl], n_inner)},
                fix_state_init=(None if fix_state_k is None else {
                    "n": fix_state_k["n"],
                    "sum": np.repeat(fix_state_k["sum"][sl], n_inner),
                    "min": np.repeat(fix_state_k["min"][sl], n_inner),
                    "max": np.repeat(fix_state_k["max"][sl], n_inner),
                }),
            )

            # Each outer scenario's MTF value = mean of its N_inner inner PVs (% notional).
            scenario_pvs[start:end] = np.array(payoffs).reshape(n_chunk, n_inner).mean(axis=1) * 100

        # A terminated contract has no residual value to mark, so it LEAVES the
        # sample — it is not marked at zero and not shown at its redemption
        # value either. Zeroing it looked defensible and was not: the recalled
        # scenarios piled up at 0 and took over the bottom of the distribution,
        # so the published P05 was made of products that had just paid ~108%
        # and finished, while the genuinely worst outcome — a live product
        # deep under its barrier, worth 40-50% — sat in the middle of the fan.
        # The chart hid the risk it exists to show, and the median printed 0%
        # from the date more than half the paths had been called.
        #
        # Every figure below is therefore CONDITIONAL on the contract still
        # being alive at t0. The survival rate is published beside it: read
        # apart, a conditional percentile says nothing about the book.
        scenario_pvs = np.where(alive, scenario_pvs, 0.0)
        alive_pvs = scenario_pvs[alive]
        n_alive = int(alive.sum())

        results.append({
            "t": t0,
            # Per-scenario marks, 0 on the terminated ones — kept for callers
            # that pair them with `alive` (the PRIIPs horizons do). The chart
            # must read `pvs_alive`.
            "pvs": [round(float(v), 4) for v in scenario_pvs],
            "pvs_alive": [round(float(v), 4) for v in alive_pvs],
            "terminated_pct": round(float((~alive).mean() * 100), 2),
            "n_alive": n_alive,
            "n_outer": int(n_outer),
            # One list of (t, montant) per outer scenario: everything paid out
            # before this mark date, at the dates it was paid.
            "realized_flows": outer_flows,
            "alive": [bool(a) for a in alive],
            # Conditional on survival. None only when nothing survives at all —
            # there is then no distribution to describe. `thin` marks the case
            # where a percentile rests on too few contracts to mean much; the
            # display refuses to plot it, but the engine still returns the
            # number rather than surprising a caller who asked for a small run.
            "thin": n_alive < MTF_MIN_ALIVE,
            "stats": (_mtf_date_stats(alive_pvs, main_price)
                      if n_alive > 0 else None),
        })

    return {
        "main_price": round(main_price, 4),
        "n_outer": n_outer,
        "n_inner": n_inner,
        "n_dates": n_dates,
        "results": results,
        "elapsed_ms": round((time.perf_counter() - t_run0) * 1000, 1),
    }


# ── Analytics: Mark-to-Future drill-down ────────────────────────────
#
# "Why is P05 at 47%?" is not answerable from a fan chart. This reopens one
# mark date and hands back, for a handful of named scenarios, everything that
# produced their number: the market path that got there, what the contract had
# already paid, what it is expected to pay next and with what probability, the
# discount factor on each of those flows, and — for comparison — what that same
# trajectory actually ends up paying if you let it run to maturity.
#
# The whole thing rests on one property: the fan's outer scenarios are
# REPRODUCIBLE. _simulate_mtf_outer draws (ts, n, N) in C order, so extending
# the horizon leaves every earlier step bit-identical; and the inner draws are
# keyed on (seed, date index k, chunk start). Replaying the same k and the same
# chunk therefore reproduces the fan's inner paths exactly, which is why the
# `mtf` reported here equals `pvs[i]` from the fan to the last decimal instead
# of merely being close to it. An explain panel that did not tie out would be
# worse than none.

def _mtf_flux_rows(flux_map: dict, n_paths: int, t0: float) -> list[dict]:
    """Turn a flux_map (aggregated over the inner paths of ONE outer scenario)
    into the expected-cash-flow table behind a mark.

    Per (date, label): probability of firing, expected amount, implied discount
    factor and present value. Summing `pv` reconstructs the mark — that identity
    is returned as a check rather than asserted, so a caller can display the
    residual instead of the engine hiding it."""
    rows = []
    for v in flux_map.values():
        n_fire, tot, pv = v["n"], v["sum"], v["pv"]
        rows.append({
            "t": round(v["t"], 6),                       # années depuis t0
            "t_abs": round(t0 + v["t"], 6),              # années depuis aujourd'hui
            "lbl": v["lbl"],
            "proba": round(n_fire / n_paths * 100, 3),   # % des chemins internes
            "e_amount": round(tot / n_paths * 100, 6),   # espérance, % du nominal
            "amount_if_fires": round(tot / n_fire * 100, 6) if n_fire else 0.0,
            "df": round(pv / tot, 6) if abs(tot) > 1e-12 else 1.0,
            "pv": round(pv / n_paths * 100, 6),          # contribution au mark
        })
    rows.sort(key=lambda x: (x["t"], x["lbl"]))
    return rows


def _mtf_observations(script: CompiledScript, wof_path: np.ndarray, ts_full: int,
                      step_k: int, stop_step: int | None,
                      fired: dict[int, list]) -> list[dict]:
    """Observation calendar of one trajectory, with its status at each date.

    `vivant` before the stop, `rappelé` at the stop itself, `éteint` after it —
    an observation the contract never reached is not a missing row, it is a row
    that says the product was already gone."""
    steps = sorted({max(1, round(d * SY))
                    for ev in script.events if ev.type == "AT" for d in ev.dates})
    if any(ev.type == "AT_MATURITY" for ev in script.events) and ts_full not in steps:
        steps.append(ts_full)
    out = []
    for s in steps:
        if stop_step is None or s < stop_step:
            status = "vivant"
        elif s == stop_step:
            status = "rappelé" if s < ts_full else "maturité"
        else:
            status = "éteint"
        out.append({
            "step": int(s),
            "t": round(s / SY, 6),
            "wof": round(float(wof_path[s - 1]), 6),
            "past": bool(s <= step_k),
            "status": status,
            "flows": fired.get(s, []),
        })
    return out


def _mtf_barriers(script: CompiledScript, source: str, user_params: dict) -> list[dict]:
    """Levels the script actually COMPARES an observable against.

    Derived from the script text by the same static analysis the M_ watchlist
    uses (_analyze_monitors), applied to every PARAM rather than only the
    M_-prefixed ones. A PARAM that is never compared to WOF/BOF/S[i] — a coupon
    rate, a participation — comes back with observable None and is dropped:
    guessing "which PARAM is a barrier" from its value would put CPN = 8% next
    to PDI = 60% and call both barriers."""
    from .parser import _analyze_monitors
    names = [p.name for p in script.params]
    if not names:
        return []
    out = []
    for mon in _analyze_monitors(source, names):
        if not mon["observable"]:
            continue
        p = next(p for p in script.params if p.name == mon["name"])
        lvl = user_params.get(p.name, p.stored_val)
        try:
            lvl = float(lvl)
        except (TypeError, ValueError):
            continue          # PARAM() en tableau : pas un niveau unique
        out.append({"name": p.name, "level": round(lvl, 6), "is_pct": bool(p.is_pct),
                    "observable": mon["observable"], "direction": mon["direction"],
                    "desc": p.desc})
    return out


def run_mtf_drilldown(script: CompiledScript,
                      underlyings,
                      corr_matrix,
                      r: float,
                      T_max: float,
                      main_price: float,
                      t0: float,
                      scenario_ids: list[int],
                      labels: list[str] | None = None,
                      script_source: str = "",
                      model: str = "constant",
                      n_outer: int = 200,
                      n_inner: int = 500,
                      n_dates: int = 5,
                      seed: int = 42,
                      user_params=None,
                      barrier_monitoring: str = "weekly",
                      mtm_dates: list[float] | None = None,
                      yield_curve=None,
                      sigma_r: float = 0.0,
                      max_scenarios: int = 12) -> dict:
    """Full explain of a handful of outer scenarios at one Mark-to-Future date.

    `scenario_ids` are indices into the fan's `pvs` / `alive` arrays. The date
    grid arguments (n_dates / mtm_dates) must match the run being explained:
    they fix the date index k, which keys the inner random draws. Get them wrong
    and the marks come back plausible and slightly different — the one failure
    mode this whole design exists to prevent, so the grid is echoed back in the
    response for the caller to check against the fan it came from."""
    _mtf_reject_unsupported(model, barrier_monitoring, yield_curve, sigma_r,
                            underlyings)
    t_run0 = time.perf_counter()
    user_params = user_params or {}
    n = len(underlyings)
    dt = 1.0 / SY

    grid = ([round(float(d), 6) for d in mtm_dates] if mtm_dates
            else build_mtf_dates(T_max, n_dates))
    t0 = round(float(t0), 6)
    k = next((i for i, d in enumerate(grid) if abs(d - t0) < 1e-6), None)
    if k is None:
        raise ValueError(
            f"La date {t0} ne figure pas dans la grille de l'éventail {grid}. "
            f"Le tirage interne dépend du rang de la date : l'expliquer depuis "
            f"une autre grille produirait un mark voisin mais différent de celui "
            f"affiché. Relancez le Mark-to-Future ou demandez une date de la grille."
        )
    step_k = _mtf_step(t0)
    if step_k < 1:
        raise ValueError(f"Date de valorisation trop proche de t=0 : {t0}.")

    ids = []
    for i in scenario_ids:
        i = int(i)
        if not 0 <= i < n_outer:
            raise ValueError(f"Scénario {i} hors bornes (0..{n_outer - 1}).")
        if i not in ids:
            ids.append(i)
    if not ids:
        raise ValueError("Aucun scénario demandé.")
    if len(ids) > max_scenarios:
        raise ValueError(
            f"{len(ids)} scénarios demandés, {max_scenarios} au maximum — chacun "
            f"rejoue {n_inner} chemins internes et renvoie sa trajectoire complète.")
    lab = {i: (labels[j] if labels and j < len(labels) else None)
           for j, i in enumerate(ids)}

    # ── Outer paths, extended to MATURITY ───────────────────────────
    # The fan stops at its last mark date; the drill-down needs the rest of the
    # trajectory to show what this scenario actually ends up paying. Extending
    # the horizon is safe precisely because the prefix is bit-identical.
    ts_full = max(1, round(T_max * SY))
    S_full = _simulate_mtf_outer(underlyings, corr_matrix, r, [T_max], n_outer, seed)
    S_outer = S_full[:step_k + 1]

    # ── Replay to the mark date (same call as the fan) ──────────────
    outer_states: list[dict] = []
    outer_flows: list[list] = []
    _eval_paths(script, S_outer, step_k, n, n_outer, dt, r, user_params,
                _mtf_past_step_map(script, step_k), [], {}, record=False,
                state_out=outer_states, flows_out=outer_flows)
    alive = np.array([not st["done"] for st in outer_states])
    fix_state_k, _ = _mtf_realized_fix(script, S_outer, step_k)
    residual_script, step_map, mat_events, ts_eff = _mtf_residual_script(script, t0, T_max)

    use_heston, use_lv, use_sabr = model == "heston", model == "localvol", model == "sabr"
    sq_dt = math.sqrt(dt)
    L = cholesky(corr_matrix, n)
    outer_per_chunk = max(1, MTF_MAX_BATCH // n_inner)
    lv_grids = nK = lkm = lkx = None
    if use_lv:
        lv_grids, nK, lkm, lkx = _build_lv_grid(
            underlyings, _build_rate_term([], ts_eff, dt, r), ts_eff, dt)

    # ── Full-script evaluation of each trajectory, out to maturity ──
    # One path, the real script (maturity block included): what this scenario
    # ends up being worth. This is a single realization along a GBM outer path,
    # NOT a price — it is the number the mark is an expectation of, and showing
    # the two side by side is the point of the panel.
    full_step_map: dict[int, list] = {}
    full_mat: list = []
    for ev in script.events:
        if ev.type == "AT_MATURITY":
            full_mat.append(ev)
        else:
            for d in ev.dates:
                s = max(1, round(d * SY))
                if s <= ts_full:
                    full_step_map.setdefault(s, []).append(ev)

    out_scen: list[dict] = []
    for i in ids:
        path_i = np.ascontiguousarray(S_full[:, :, i:i + 1])          # (ts_full+1, n, 1)
        wof_i = path_i[1:].min(axis=1)[:, 0]                          # (ts_full,)
        flux_full: dict = {}
        stops: list = []
        flows_full: list = []
        pay_full, pay_raw = _eval_paths(
            script, path_i, ts_full, n, 1, dt, r, user_params,
            full_step_map, full_mat, flux_full, record=True,
            stop_times_out=stops, flows_out=flows_full)
        stop_t = float(stops[0]) if stops else float(ts_full * dt)
        stop_step = int(round(stop_t * SY))
        fired: dict[int, list] = {}
        for v in flux_full.values():
            s = max(1, round(v["t"] * SY))
            fired.setdefault(s, []).append(
                {"lbl": v["lbl"], "v": round(v["sum"] * 100, 6)})

        out_scen.append({
            "id": i,
            "label": lab[i],
            "alive": bool(alive[i]),
            "wof_t0": round(float(S_full[step_k, :, i].min()), 6),
            "spots_t0": [round(float(v), 6) for v in S_full[step_k, :, i]],
            # Trajectoire complète (hebdomadaire), t=0 inclus.
            "path": {
                "t": [round(s / SY, 6) for s in range(ts_full + 1)],
                "wof": [1.0] + [round(float(v), 6) for v in wof_i],
                "assets": [[round(float(v), 6) for v in S_full[:, a, i]] for a in range(n)],
            },
            "observations": _mtf_observations(script, wof_i, ts_full, step_k,
                                              stop_step, fired),
            # Ce qui a DÉJÀ été encaissé avant la date de valorisation.
            "realized_flows": [
                {"t": round(t, 6), "v": round(v * 100, 6),
                 "pv_t0": round(v * math.exp(-r * (t - t0)) * 100, 6)}
                for t, v in outer_flows[i]],
            "realized_cash": round(sum(v for _t, v in outer_flows[i]) * 100, 6),
            # Payoff RÉEL de cette trajectoire si on la laisse courir.
            "final": {
                "stop_t": round(stop_t, 6),
                "recalled": bool(stop_step < ts_full),
                "total_undiscounted": round(float(pay_raw[0]) * 100, 6),
                "pv_at_0": round(float(pay_full[0]) * 100, 6),
                "flows": [{"t": round(t, 6), "v": round(v * 100, 6)}
                          for t, v in flows_full[0]],
            },
        })

    # ── Inner repricing, chunk by chunk, exactly as the fan drew it ──
    by_chunk: dict[int, list[int]] = {}
    for i in ids:
        by_chunk.setdefault((i // outer_per_chunk) * outer_per_chunk, []).append(i)

    marks: dict[int, dict] = {}
    for start, members in by_chunk.items():
        end = min(n_outer, start + outer_per_chunk)
        n_chunk = end - start
        N_chunk = n_chunk * n_inner
        sl = slice(start, end)
        spot_chunk = np.repeat(S_full[step_k][:, sl], n_inner, axis=1)
        # Same key as run_mark_to_future: seed + 1_000_003*(k+1) + start.
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

        for i in members:
            j = i - start
            cols = slice(j * n_inner, (j + 1) * n_inner)
            flux: dict = {}
            stops_in: list = []
            payoffs, _ = _eval_paths(
                residual_script, np.ascontiguousarray(S_in[:, :, cols]), ts_eff, n,
                n_inner, dt, r, user_params, step_map, mat_events, flux, record=True,
                stop_times_out=stops_in,
                wof_min_init=float(outer_states[i]["wof_min"]),
                bof_max_init=float(outer_states[i]["bof_max"]),
                index_offset=int(outer_states[i]["index"]),
                memo_init=outer_states[i]["memo"],
                accum_init=float(outer_states[i]["accum"]),
                s_min_init=np.asarray(outer_states[i]["s_min"], dtype=float),
                s_max_init=np.asarray(outer_states[i]["s_max"], dtype=float),
                s_prev_init=np.asarray(outer_states[i]["s_prev"], dtype=float),
                wof0_init=float(S_full[step_k, :, i].min()),
                realvol_state_init={"sumsq": float(outer_states[i]["realvol_sumsq"]),
                                    "t": float(outer_states[i]["realvol_t"])},
                fix_state_init=(None if fix_state_k is None else {
                    "n": fix_state_k["n"], "sum": float(fix_state_k["sum"][i]),
                    "min": float(fix_state_k["min"][i]), "max": float(fix_state_k["max"][i])}),
            )
            mtf_i = float(np.mean(payoffs)) * 100
            rows = _mtf_flux_rows(flux, n_inner, t0)
            mat_t = ts_eff * dt
            recalled = sum(1 for s in stops_in if s < mat_t - 0.5 * dt)
            marks[i] = {
                "mtf": round(mtf_i, 6),
                "future_flows": rows,
                "sum_pv": round(sum(x["pv"] for x in rows), 6),
                "recall_proba": round(recalled / n_inner * 100, 3),
                "expected_life": round(float(np.mean(stops_in)) + t0, 6),
            }

    for sc in out_scen:
        m = marks[sc["id"]]
        # Un contrat éteint n'a pas de valeur résiduelle à marquer : il sort de
        # l'échantillon dans l'éventail, et le panneau doit dire la même chose
        # plutôt que d'exhiber le prix d'un produit qui n'existe plus.
        sc["mtf"] = m["mtf"] if sc["alive"] else 0.0
        sc["residual_mark"] = m["mtf"]
        sc["future_flows"] = m["future_flows"] if sc["alive"] else []
        sc["sum_pv"] = m["sum_pv"] if sc["alive"] else 0.0
        sc["recall_proba"] = m["recall_proba"] if sc["alive"] else None
        sc["expected_life"] = m["expected_life"] if sc["alive"] else None
        # Écart de reconstitution : somme des VA des flux futurs - mark. Nul par
        # construction, publié pour que le tableau soit vérifiable à l'écran.
        sc["pv_residual"] = round(sc["sum_pv"] - sc["mtf"], 9)

    return {
        "t": t0,
        "k": k,
        "step_k": step_k,
        "mtm_dates": grid,
        "main_price": round(main_price, 4),
        "n_outer": n_outer,
        "n_inner": n_inner,
        "T_max": round(T_max, 6),
        "r": r,
        "n_assets": n,
        "asset_names": [u.get("name") or f"S{a + 1}" for a, u in enumerate(underlyings)],
        "barriers": _mtf_barriers(script, script_source, user_params),
        "scenarios": out_scen,
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


IRR_FLOOR = -1.0 + 1e-6     # -99.9999% — below this everything is "total loss"
IRR_CAP = 10.0              # +1000%, past which the figure is an artefact


def compute_irr(cash_flows: list[dict], guess: float = 0.1,
                tol: float = 1e-10, max_iter: int = 200) -> float | None:
    """IRR by bracketing then bisection. cash_flows = list of {t: years, cf: amount}.

    The previous solver was a bare Newton-Raphson started at 10% and clamped
    to [-0.99, 10]. It answered correctly on ordinary windows and returned
    None on the ones that matter most:

      * a total loss (-100 at t=0, nothing back) has its IRR at exactly -100%,
        which a clamp at -99% can never reach;
      * a near-total loss (-100, +0.01) sits at -99.99%, outside the clamp too;
      * an overshoot into the clamp stalls the iteration on the flat region.

    Those Nones were then dropped by the callers, so the worst windows of a
    backtest vanished from its statistics — a selection bias pointing one way,
    in favour of the product. A performance measure that quietly discards its
    own left tail is worse than no measure.

    Bisection needs no derivative, cannot overshoot, and converges on every
    bracketed root. Newton is kept only as a final polish. The cases that
    genuinely have no single IRR (no outflow, no inflow, several sign changes)
    still return None — but they are now the only ones, and they are honest."""
    if not cash_flows:
        return None

    def npv(r_: float) -> float:
        total = 0.0
        base = 1.0 + r_
        for cf in cash_flows:
            t = cf["t"]
            try:
                total += cf["cf"] / (base ** t) if t else cf["cf"]
            except (ZeroDivisionError, OverflowError):
                return math.inf if cf["cf"] > 0 else -math.inf
        return total

    inflow = sum(cf["cf"] for cf in cash_flows if cf["cf"] > 0)
    outflow = sum(cf["cf"] for cf in cash_flows if cf["cf"] < 0)
    if inflow == 0.0 and outflow == 0.0:
        return None                     # nothing happened
    if outflow == 0.0:
        return None                     # no money ever invested: no rate of return
    if inflow == 0.0:
        # Everything paid in, nothing back. The rate of return is -100%, and
        # saying so is the entire point of this rewrite.
        return -1.0

    # A conventional window — money out, then money in — has exactly one sign
    # change, so NPV is strictly decreasing in r and the root is unique. That
    # is every real product window: you pay at inception and receive coupons
    # and redemption afterwards. Anything else can carry several mathematical
    # IRRs, and picking one of them (which the old Newton did, silently) is
    # not a measure of anything.
    ordered = sorted(cash_flows, key=lambda c: c["t"])
    signs = [1 if cf["cf"] > 0 else -1 for cf in ordered if cf["cf"] != 0]
    conventional = sum(1 for a, b in zip(signs, signs[1:]) if a != b) == 1

    f_lo, f_hi = npv(IRR_FLOOR), npv(IRR_CAP)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)):
        return None
    if f_lo == 0.0:
        return IRR_FLOOR
    if f_hi == 0.0:
        return IRR_CAP
    if f_lo > 0.0 and f_hi > 0.0:
        # Conventional: NPV decreases, so still positive at +1000% means the
        # root is beyond it — report the cap rather than drop the window.
        return IRR_CAP if conventional else None
    if f_lo < 0.0:
        # Impossible for a conventional window with any inflow: as r → -100%
        # the discounted inflows dominate and NPV → +∞. Reaching here means a
        # late negative flow outweighs them, i.e. a non-conventional profile.
        return None

    lo, hi = IRR_FLOOR, IRR_CAP
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if f_mid == 0.0 or (hi - lo) < tol:
            lo = hi = mid
            break
        if (f_lo < 0.0) == (f_mid < 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    r = 0.5 * (lo + hi)

    # Newton polish — accepted only if it stays inside the bracket and does
    # not worsen the residual, so it can never undo the bisection.
    def dnpv(r_: float) -> float:
        try:
            return -sum(cf["t"] * cf["cf"] / (1.0 + r_) ** (cf["t"] + 1)
                        for cf in cash_flows)
        except (ZeroDivisionError, OverflowError):
            return 0.0

    d = dnpv(r)
    if abs(d) > 1e-12:
        cand = r - npv(r) / d
        if IRR_FLOOR <= cand <= IRR_CAP and abs(npv(cand)) < abs(npv(r)):
            r = cand

    return r if math.isfinite(r) else None
