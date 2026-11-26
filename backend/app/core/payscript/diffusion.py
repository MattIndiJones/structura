"""Path simulators: correlation factor, Heston QE, SABR, GBM, Local Vol, LSV,
and the Brownian-bridge extrema used for continuous barrier monitoring.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.special import erfc
from .bridge import bridge_extrema, semidefinite_factor
from .models import MODELS
from .time_grid import durations as _durations
from .local_vol import _build_dividend_step_matrix
from .rates import _blend_rate_factor
from .fx_overlay import asset_carry_rate, heston_effective_theta, heston_variance_shift, sabr_alpha_drift


# Largest coefficient move a nearest-PSD repair may make before the matrix is
# rejected outright rather than silently used (see cholesky).
CORR_REPAIR_TOL = 0.02
PSI_C = 1.5   # Heston QE switching threshold


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
    if -1e-12 <= eigvals.min() < 1e-10:
        # Perfect factors must remain perfect; diagonal jitter invents another
        # risk factor and makes copies disagree at barrier crossings.
        return semidefinite_factor(C)
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


# ── Simulation engines ──────────────────────────────────────────────

def _seed_spot(spot_mult) -> np.ndarray:
    """Build the t=0 spot slice from spot_mult.
    Accepts either a per-asset scalar vector of shape (n,) — the same initial spot
    broadcast to every path, used by Greeks bump-and-reprice — or a per-asset,
    per-path matrix of shape (n, N), used by Mark-to-Future to seed each inner path
    at its own outer scenario's spot level."""
    arr = np.asarray(spot_mult, dtype=np.float64)
    return arr if arr.ndim == 2 else arr[:, None]


def _atm_step_vols(underlyings, dt, ts):
    """Integrate ATM total variance over the original simulation grid."""
    lengths = _durations(dt, ts)
    times = np.r_[0., np.cumsum(lengths)]
    columns = []
    for underlying in underlyings:
        surface = underlying.get("vol_surface")
        if not surface or times[-1] > surface["max_expiry"] + 1e-8:
            raise ValueError("La courbe ATM doit couvrir tout l’horizon du GBM.")
        nodes = np.asarray(surface["atm_nodes"], dtype=float)
        vols = nodes[:, 1]
        if np.all(vols == vols[0]):
            columns.append(np.full(ts, vols[0]))
            continue
        knots = np.r_[0., nodes[:, 0]]
        variances = np.r_[0., nodes[:, 0]*vols**2]
        total = np.interp(times, knots, variances) + np.maximum(times-knots[-1], 0.)*vols[-1]**2
        columns.append(np.sqrt(np.diff(total)/lengths))
    return np.column_stack(columns)


def _simulate_gbm(ts: int, n: int, N: int, dt: float, sq_dt: float,
                  underlyings, r_eff: float, L: np.ndarray,
                  Z: np.ndarray, spot_mult=None, vol_add=None,
                  r_path=None, Z_r=None, vol_out=None, *, step_vols=None) -> np.ndarray:
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
        # The mono factor is sqrt(1-rho_rS^2) when coupled to a live rate.
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    r_term = r_eff if r_path is None else r_path
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)
    for i, u in enumerate(underlyings):
        sig = u.get("sigma", 0.20) if step_vols is None else step_vols[:, i, None]
        if vol_add is not None:
            sig = np.maximum(0.005, sig + vol_add[i])
        if vol_out is not None:
            vol_out[:, i, :] = sig
        z_i = _blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0)) if Z_r is not None else Zc[:, i, :]
        q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
        q_term = (u.get("q", 0.02) if dividend_steps is None
                  else dividend_steps[:, i, None])
        drift = asset_carry_rate(u, r_term) - q_term - q_adj - 0.5 * sig * sig
        lengths = _durations(dt, ts)[:, None]
        log_ret = drift * lengths + sig * np.sqrt(lengths) * z_i
        S[1:, i, :] = S[0, i] * np.exp(np.cumsum(log_ret, axis=0))

    return S


def _simulate_heston(ts: int, n: int, N: int, dt: float, sq_dt: float,
                     underlyings, r_eff: float, L: np.ndarray,
                     Z: np.ndarray, Zv: np.ndarray,
                     spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                     vol_out=None, *, factor_init=None, factor_out=None) -> np.ndarray:
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
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    V = [np.full(N, u.get("v0", 0.04), dtype=np.float64) for u in underlyings]
    if factor_init is not None:
        V = list(factor_init)
    if factor_out is not None:
        factor_out[0] = V
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

    lengths = _durations(dt, ts)
    for step in range(ts):
        dt = float(lengths[step])
        sq_dt = math.sqrt(dt)
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            rh  = u.get("rho_h", -0.70)
            kap = u.get("kappa", 2.0)
            th  = u.get("theta", 0.04)
            xi  = u.get("xi", 0.35)
            c_fx = heston_variance_shift(u)
            rhop = math.sqrt(max(0.0, 1.0 - rh*rh))

            cz_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]

            # Variance BM: correlated with spot via rho_h
            z_perp_var = Zv[step, i, :]             # independent component
            zv = rh * cz_i + rhop * z_perp_var      # full variance Brownian W_V

            V_old  = V[i]
            th_eff = heston_effective_theta(th, kap, c_fx, V_old)
            V_next = _heston_qe_vectorized(V_old, kap, th_eff, xi, dt, zv)
            V_bar  = (V_old + V_next) / 2
            V[i]   = V_next
            if factor_out is not None:
                factor_out[step + 1, i] = V_next

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
            drift = (asset_carry_rate(u, r_term, step) - q_term
                     - q_adj - 0.5 * bumped_variance)

            # Andersen (2007) spot update — see docstring for the martingale
            # derivation, unchanged from the original per-path formula.
            z_S_perp  = rhop * cz_i - rh * z_perp_var
            corr_term = rh / xi * (V_next - V_old - kap * (th_eff - V_bar) * dt)
            S[step+1, i, :] = S[step, i, :] * np.exp(
                drift*dt + corr_term + rhop * sv * sq_dt * z_S_perp
            )

    return S


def _simulate_sabr(ts: int, n: int, N: int, dt: float, sq_dt: float,
                   underlyings, r_eff: float, L: np.ndarray,
                   Z: np.ndarray, Za: np.ndarray,
                   spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                   vol_out=None, *, factor_init=None, factor_out=None) -> np.ndarray:
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
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z

    S = np.ones((ts + 1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    alpha = [np.full(N, u.get("alpha", 0.20), dtype=np.float64) for u in underlyings]
    if factor_init is not None:
        alpha = list(factor_init)
    if factor_out is not None:
        factor_out[0] = alpha
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

    lengths = _durations(dt, ts)
    for step in range(ts):
        dt = float(lengths[step])
        sq_dt = math.sqrt(dt)
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
            alpha_new = alpha_old * np.exp(nu * sq_dt * z_a - 0.5 * nu**2 * dt
                                           + sabr_alpha_drift(u) * dt)

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
            drift = asset_carry_rate(u, r_term, step) - q_term - q_adj - 0.5 * sig**2
            S[step + 1, i, :] = S_c * np.exp(drift * dt + sig * sq_dt * z_S)
            alpha[i] = alpha_new
            if factor_out is not None:
                factor_out[step + 1, i] = alpha_new

    return S


def _local_vol_at_spot(spot, row, log_min, log_step, bump=0.):
    position = (np.log(np.maximum(spot, 1e-8)) - log_min) / log_step
    node = np.clip(position.astype(int), 0, len(row)-2)
    weight = np.clip(position-node, 0., 1.)
    return np.maximum(row[node]*(1.-weight) + row[node+1]*weight + bump, .001)


def _simulate_lv(ts: int, n: int, N: int, dt: float, sq_dt: float,
                  underlyings, r_eff: float, L: np.ndarray, Z: np.ndarray,
                  lv_grids, nK: int, logKmin: float, logKmax: float,
                  spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                  vol_out=None, local_vol_anchor=None) -> np.ndarray:
    """Vectorized Dupire local vol simulation using precomputed grid.

    r_path/Z_r: see _simulate_gbm — optional stochastic-rate level/shock, no-op
    when both None (default).
"""
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts*N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z

    S = np.ones((ts+1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    dlogK = (logKmax - logKmin) / (nK - 1)
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

    lengths = _durations(dt, ts)
    for step in range(ts):
        dt = float(lengths[step])
        sq_dt = math.sqrt(dt)
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            S_c = S[step, i, :]
            bump = vol_add[i] if vol_add is not None else 0.
            lvs = _local_vol_at_spot(S_c if local_vol_anchor is None else S_c / local_vol_anchor[i],
                                     lv_grids[i][step], logKmin, dlogK, bump)
            if vol_out is not None:
                vol_out[step, i, :] = lvs
            z_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
            q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * lvs
            q_term = (u.get("q", 0.02) if dividend_steps is None
                      else dividend_steps[step, i])
            drift = asset_carry_rate(u, r_term, step) - q_term - q_adj - 0.5*lvs**2
            S[step+1, i, :] = S_c * np.exp(drift*dt + lvs*sq_dt*z_i)

    return S


# Minimum paths a log-moneyness bucket needs before its E[V|S] estimate is
# trusted — see _simulate_lsv. Below this, the bucket average is too noisy
# (especially early time steps, before paths have dispersed), so we borrow
# neighbouring spot buckets instead of the unconditional variance.
_LSV_MIN_BUCKET_PATHS = 30
# Conditional variance needs finer spot resolution than the local-vol lookup,
# particularly for short-dated digitals. Keep these two grids independent.
_LSV_CONDITIONAL_BUCKETS = 200


def _lsv_conditional_grid(logKmin: float, logKmax: float) -> tuple[int, float]:
    """Buckets of the particle estimator: the historical [.2, 3] grid keeps
    exactly 200, a wider offline domain keeps the same resolution."""
    buckets = max(_LSV_CONDITIONAL_BUCKETS,
                  round((logKmax-logKmin)/math.log(15)*(_LSV_CONDITIONAL_BUCKETS-1))+1)
    return buckets, (logKmax-logKmin)/(buckets-1)


def _lsv_conditional_variance(bucket_indices: np.ndarray, variance: np.ndarray,
                              n_buckets: int, bucket_means_out: list | None = None) -> np.ndarray:
    """Estimate E[V|S], widening only thin spot buckets to local neighbours.

    Substituting E[V] in a thin tail erases the spot/variance dependence and
    creates excess downside variance even with a flat local-vol target.
    Symmetric windows retain that dependence while keeping at least 30
    particles (or the whole sample when fewer are available). Dense buckets
    retain their own conditional mean. Only start-of-step variance is used.
    """
    sums = np.bincount(bucket_indices, weights=variance, minlength=n_buckets)
    counts = np.bincount(bucket_indices, minlength=n_buckets)
    cumulative_sum = np.concatenate(([0.], np.cumsum(sums)))
    cumulative_count = np.concatenate(([0], np.cumsum(counts)))
    occupied = np.flatnonzero(counts)
    lo = occupied.copy()
    hi = lo + 1
    count = cumulative_count[hi] - cumulative_count[lo]
    minimum = min(_LSV_MIN_BUCKET_PATHS, variance.size)
    while np.any(count < minimum):
        thin = count < minimum
        lo[thin] = np.maximum(lo[thin]-1, 0)
        hi[thin] = np.minimum(hi[thin]+1, n_buckets)
        count = cumulative_count[hi] - cumulative_count[lo]
    means = np.zeros(n_buckets)
    means[occupied] = np.maximum(cumulative_sum[hi]-cumulative_sum[lo], 0.) / np.maximum(count, 1)
    if bucket_means_out is not None:
        bucket_means_out.append((occupied, means[occupied]))
    return means[bucket_indices]


def _simulate_lsv(ts: int, n: int, N: int, dt: float, sq_dt: float,
                   underlyings, r_eff: float, L: np.ndarray, Z: np.ndarray, Zv: np.ndarray,
                   lv_grids, nK: int, logKmin: float, logKmax: float,
                   spot_mult=None, vol_add=None, r_path=None, Z_r=None,
                   vol_out=None, *, leverage_grids=None, factor_init=None, factor_out=None, local_vol_anchor=None) -> np.ndarray:
    """Local-Stochastic Vol (Guyon & Henry-Labordère) — a stochastic variance
    process (the same Heston QE dynamics as _simulate_heston, but vectorized
    via _heston_qe_vectorized) whose effect on the spot is rescaled at every
    time step by a "leverage" function to approximate the MARGINAL distribution
    implied by the Dupire local vol target (lv_grids, the same grid used by
    _simulate_lv). Finite particles, buckets, steps and clipping leave a
    calibration residual which must be checked on vanillas and digitals.
    The PATH dynamics (forward
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
      1. Bucket the current cross-section (S, V_old) into a finer conditional
         log-moneyness grid (independent of lv_grids), and average V_old within each bucket
         -> an estimate of the conditional expectation E[V|S] (the
         "particles" of the method). Buckets with fewer than
         _LSV_MIN_BUCKET_PATHS paths borrow adjacent spot buckets until
         sufficiently populated, rather than using unconditional variance.
         V_old (the
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
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z

    S = np.ones((ts+1, n, N), dtype=np.float64)
    if spot_mult is not None:
        S[0] = _seed_spot(spot_mult)

    V = [np.full(N, u.get("v0", 0.04), dtype=np.float64) if factor_init is None
         else np.asarray(factor_init[i], dtype=np.float64).copy()
         for i, u in enumerate(underlyings)]
    if factor_out is not None:
        factor_out[0] = V

    dlogK = (logKmax - logKmin) / (nK - 1)
    # Preserve conditional spot resolution when an offline target supplies a
    # wider LV domain. The historical [.2,3] grid still has exactly 200 bins.
    conditional_buckets = max(_LSV_CONDITIONAL_BUCKETS,
        round((logKmax-logKmin)/math.log(15)*(_LSV_CONDITIONAL_BUCKETS-1))+1)
    conditional_step = (logKmax-logKmin)/(conditional_buckets-1)
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)

    lengths = _durations(dt, ts)
    for step in range(ts):
        dt = float(lengths[step])
        sq_dt = math.sqrt(dt)
        r_term = r_eff if r_path is None else r_path[step]
        for i, u in enumerate(underlyings):
            kappa = u.get("kappa", 2.0)
            theta = u.get("theta", 0.04)
            xi    = u.get("xi", 0.35)
            rho_h = u.get("rho_h", -0.70)
            rhop  = math.sqrt(max(0.0, 1.0 - rho_h*rho_h))
            c_fx = heston_variance_shift(u)

            # Variance Brownian, correlated with the spot driver via rho_h —
            # same construction as _simulate_heston's zv.
            zv_i = rho_h * Zc[step, i, :] + rhop * Zv[step, i, :]
            V_old = V[i]
            V_next = _heston_qe_vectorized(
                V_old, kappa, heston_effective_theta(theta, kappa, c_fx, V_old), xi, dt, zv_i)

            S_c = S[step, i, :]
            logS = np.log(np.maximum(S_c, 1e-8)) - (math.log(local_vol_anchor[i]) if local_vol_anchor is not None else 0.)
            kif = (logS - logKmin) / dlogK
            k0 = np.clip(kif.astype(int), 0, nK-2)
            frac = np.clip(kif - k0, 0.0, 1.0)
            g = lv_grids[i]
            lv_target = g[step, k0] * (1.0-frac) + g[step, k0+1] * frac

            # Particle-method conditional expectation E[V|S], bucketed on a
            # finer grid than the local-vol lookup above. Uses
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
            if leverage_grids is None:
                conditional_bucket = np.clip(((logS-logKmin)/conditional_step).astype(int),
                                              0, conditional_buckets-2)
                E_V_given_S = _lsv_conditional_variance(conditional_bucket, V_old,
                                                       conditional_buckets)
                leverage = np.clip(lv_target / np.sqrt(np.maximum(E_V_given_S, 1e-6)), 0.2, 5.0)
            else:
                row = leverage_grids[i][step]
                leverage = row[k0] * (1.0-frac) + row[k0+1] * frac
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
            drift = asset_carry_rate(u, r_term, step) - q_term - q_adj - 0.5*eff_vol**2
            S[step+1, i, :] = S_c * np.exp(drift*dt + eff_vol*sq_dt*z_i)
            V[i] = V_next
            if factor_out is not None:
                factor_out[step + 1, i] = V_next

    return S


# ── Continuous barrier monitoring (Brownian bridge extrema) ─────────

def _bridge_extrema(S: np.ndarray, vol_used: np.ndarray, dt: float, rng,
                    corr_matrix=None, *, substeps=None, diagnostics=None) -> tuple:
    """Conditional extrema; the basket joint law is explicitly approximate.

    See bridge.py for correlated midpoint refinement and residual leaf laws.
    Row k covers (k, k+1], as does S_min[step-1].
    """
    matrix = np.asarray(corr_matrix) if corr_matrix is not None else None
    if (matrix is not None and matrix.shape == (S.shape[1], S.shape[1])
            and np.isfinite(matrix).all() and np.linalg.eigvalsh(matrix).min() < -1e-10):
        # Match a material PSD repair used by endpoint simulation. An already
        # PSD singular input keeps its exact perfect factors in the bridge.
        factor = cholesky(corr_matrix, S.shape[1])
        corr_matrix = factor @ factor.T
    return bridge_extrema(S, vol_used, dt, rng, corr_matrix, substeps=substeps, diagnostics=diagnostics)
