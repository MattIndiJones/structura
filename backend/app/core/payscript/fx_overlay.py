"""Cross-currency underlyings: quanto and compo.

Every underlying is diffused under the measure of the deal currency (the one
the payoff is paid and discounted in). An underlying quoted in another
currency comes in one of two ways, chosen per underlying by `fx_mode`:

- ``"quanto"``: the performance of the asset in its own currency is paid in
  the deal currency at a rate fixed in advance. Under the deal measure the
  asset drifts at ``r_ccy - q - rho * sigma * sigma_fx`` (+ ``ccyh``, the
  cross-currency basis), with ``r_ccy`` the risk-free rate of the asset's
  currency. The FX rate itself never appears in the payoff.
- ``"compo"``: the payoff reads the asset converted into the deal currency,
  ``S * X``. The asset is diffused with the same quanto drift, and a
  correlated FX path ``dX/X = (r_deal - r_ccy) dt + sigma_fx dW_X`` is laid
  over it, with ``dW_X = rho dW_S + sqrt(1 - rho^2) dW_perp`` built on the
  asset's own Brownian. The product drifts at ``r_deal - q`` with the
  composite variance ``sigma^2 + sigma_fx^2 + 2 rho sigma sigma_fx``, under
  any spot model whose Brownian is the correlated draw (GBM, Heston, SABR).

Conventions: ``X`` is the number of deal-currency units for one unit of the
asset's currency (EUR per USD for an S&P 500 in a EUR deal), and ``rho_sfx``
is the correlation between the asset and that ``X``.

``fx_mode`` absent keeps the historical behaviour bit for bit: the asset
drifts at the deal rate, adjusted by ``ccyh`` and ``rho * sigma * sigma_fx``.
Products booked before 26/11/2026 carry no mode and are priced as before.
"""
from __future__ import annotations

import numpy as np

from .rates import _blend_rate_factor
from .time_grid import durations as _durations

FX_MODES = ("quanto", "compo")
_SUPPORTED_MODELS = ("constant", "heston", "sabr", "localvol", "lsv")


def fx_mode(u) -> str | None:
    mode = u.get("fx_mode")
    return mode or None


def foreign_rate(u, step=None):
    """Risk-free rate of the asset's currency: the flat r_ccy, or the step
    forward of its own curve once attach_ccy_curves has built it. With
    step=None, the whole (ts, 1) column for the vectorised GBM."""
    fwd = u.get("_ccy_fwd")
    if fwd is None:
        return float(u["r_ccy"])
    return fwd[:, None] if step is None else float(fwd[step])


def foreign_zero(u, step):
    """Zero rate of the asset's currency to grid step `step` (flat r_ccy without a curve)."""
    zero = u.get("_ccy_zero")
    return float(u["r_ccy"]) if zero is None else float(zero[step])


def attach_ccy_curves(underlyings, ts: int, dt):
    """Copies of the underlyings carrying their own-currency curve on the run grid.

    Built with the same _build_rate_term as the deal curve, so forwards and
    zero rates telescope exactly. An asset without a curve is returned as is:
    its flat r_ccy keeps the scalar path, bit for bit."""
    from .rates import _build_rate_term
    out = []
    for u in underlyings:
        if fx_mode(u) in FX_MODES and u.get("ccy_curve"):
            fallback = u.get("r_ccy")
            if fallback is None:
                fallback = float(u["ccy_curve"][0][1])
            term = _build_rate_term(u["ccy_curve"], ts, dt, float(fallback))
            u = dict(u, r_ccy=float(fallback), _ccy_fwd=term.step_fwd, _ccy_zero=term.zero)
        out.append(u)
    return out


def asset_carry_rate(u, r_term, step=None):
    """Rate carrying the asset in its own drift, before dividends and the
    quanto correction. The deal rate for a deal-currency asset, the asset's
    own currency rate (flat or curve) for a quanto or compo one. `step` is the
    grid step of the step-wise simulators; None for the vectorised GBM."""
    if fx_mode(u) in FX_MODES:
        return foreign_rate(u, step) + u.get("ccyh", 0.0)
    return r_term + u.get("ccyh", 0.0)


def heston_variance_shift(u) -> float:
    """Coefficient c of the variance drift added under the deal measure.

    The variance Brownian carries corr(W_V, W_X) = rho_h * rho_sfx, and
    Girsanov shifts it by that correlation times sigma_fx, a constant. dV
    therefore gains -xi * sigma_fx * rho_h * rho_sfx * sqrt(V) dt = -c sqrt(V) dt:
    in sqrt(V), not in V, so the deal-measure variance is no longer an affine
    Heston process. 0.0 without an FX mode.
    """
    if fx_mode(u) not in FX_MODES:
        return 0.0
    return (float(u.get("xi", 0.35)) * float(u.get("sigma_fx", 0.0))
            * float(u.get("rho_h", -0.70)) * float(u.get("rho_sfx", 0.0)))


def heston_effective_theta(theta: float, kappa: float, c: float, V_old):
    """Long-run level that makes kappa*(theta_eff - V) carry the -c sqrt(V)
    term over one step, frozen at the start of the step for each path.
    Floored at zero: a negative target would only pull variance below zero."""
    if not c:
        return theta
    return np.maximum(theta - c * np.sqrt(np.maximum(V_old, 0.0)) / kappa, 0.0)


def sabr_alpha_drift(u) -> float:
    """Drift of log(alpha) added under the deal measure: -nu*sigma_fx*rho_sabr*rho_sfx,
    since the alpha Brownian carries corr(W_alpha, W_X) = rho_sabr * rho_sfx."""
    if fx_mode(u) not in FX_MODES:
        return 0.0
    return -(float(u.get("nu", 0.40)) * float(u.get("sigma_fx", 0.0))
             * float(u.get("rho", -0.30)) * float(u.get("rho_sfx", 0.0)))


def validate_fx_terms(underlyings, model: str, path_simulator=None) -> None:
    for u in underlyings:
        mode = fx_mode(u)
        if mode is None:
            continue
        name = u.get("name", "sous-jacent")
        if mode not in FX_MODES:
            raise ValueError(f"{name} : mode de change {mode!r} inconnu (quanto ou compo).")
        if u.get("r_ccy") is None and not u.get("ccy_curve"):
            raise ValueError(f"{name} : le {mode} exige le taux sans risque de la devise du sous-jacent.")
        if not -1.0 <= float(u.get("rho_sfx", 0.0)) <= 1.0:
            raise ValueError(f"{name} : la corrélation sous-jacent/change doit être entre -100 % et 100 %.")
        if model not in _SUPPORTED_MODELS:
            raise ValueError(f"{name} : le {mode} n'est pas disponible sous le modèle {model}.")
        if mode == "compo" and path_simulator is not None:
            raise ValueError(f"{name} : le compo n'est pas disponible sur des trajectoires fournies.")


def has_compo(underlyings) -> bool:
    return any(fx_mode(u) == "compo" for u in underlyings)


def compo_indices(underlyings) -> list[int]:
    return [i for i, u in enumerate(underlyings) if fx_mode(u) == "compo"]


def apply_compo(S, Z, L, W_perp, underlyings, dt, ts, r_eff, r_path, Z_r, vol_out=None):
    """Convert compo assets into the deal currency, in place.

    Z, L, Z_r are exactly what the simulator received, so the asset Brownian
    rebuilt here is the one that drove S. W_perp is (ts, n_compo, N): the FX
    leg independent from the asset. vol_out, when the bridge needs it, is
    switched to the composite instantaneous vol.
    """
    idx = compo_indices(underlyings)
    if not idx:
        return S
    n, N = S.shape[1], S.shape[2]
    if n > 1:
        Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts * N)
        Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
    else:
        Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z
    lengths = _durations(dt, ts)[:, None]
    r_dom = r_eff if r_path is None else r_path
    for k, i in enumerate(idx):
        u = underlyings[i]
        z_s = (_blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0))
               if Z_r is not None else Zc[:, i, :])
        rho = float(u.get("rho_sfx", 0.0))
        sx = float(u.get("sigma_fx", 0.0))
        z_x = rho * z_s + np.sqrt(max(0.0, 1.0 - rho * rho)) * W_perp[:, k, :]
        log_x = ((r_dom - foreign_rate(u) - 0.5 * sx * sx) * lengths
                 + sx * np.sqrt(lengths) * z_x)
        S[1:, i, :] *= np.exp(np.cumsum(log_x, axis=0))
        if vol_out is not None:
            v = vol_out[:, i, :]
            vol_out[:, i, :] = np.sqrt(np.maximum(v * v + sx * sx + 2.0 * rho * v * sx, 0.0))
    return S
