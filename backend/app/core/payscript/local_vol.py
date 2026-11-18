"""Dupire local volatility: implied-smile inversion, dividend steps, SSVI
wings and the local-volatility grid fed to the Local Vol and LSV simulators.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

import math
import numpy as np
from .time_grid import durations as _durations, time_at as _time_at, times as _times


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
    """Vol locale de Dupire, exprimée en VARIANCE TOTALE (Gatheral, éq. 1.10) :

        σ²_loc = ∂w/∂T / [1 − (y/w)·∂w/∂y
                          + ¼(−¼ − 1/w + y²/w²)(∂w/∂y)² + ½·∂²w/∂y²]

    avec w(y,T) = σ_imp(y,T)²·T la variance totale et y = log(K/F_T) la
    log-moneyness par rapport au forward.

    Elle remplace une inversion par différences finies sur des prix
    Black-Scholes, qui divisait par un ∂²C/∂K² minuscule dans les ailes et
    approchait ∂C/∂T par une différence AVANT sur un pas valant jusqu'à 23 % de
    la maturité (`max(3/52, 6 % de T)`). Sur une nappe implicite PLATE à 20 % —
    cas où la réponse exacte est 20 % partout, par identité — elle rendait
    jusqu'à 150 % de vol locale à K = 60 % et T = 3 mois, le plafond de la
    fonction transformant la divergence en un nombre d'allure plausible. Un
    autocall phoenix à constatations trimestrielles y perdait 26,7 bps ; un
    autocall à constatations annuelles, qui ne visite pas cette zone, 5 bps
    seulement — le défaut ne se signalait donc sur aucun produit en particulier.

    Ici l'identité est ALGÉBRIQUE et non numérique : nappe plate ⇒ ∂w/∂y = 0 et
    ∂²w/∂y² = 0 ⇒ dénominateur = 1 ⇒ σ²_loc = ∂w/∂T = σ₀². Aucun prix n'est
    construit, aucune petite quantité n'est mise au dénominateur."""
    if (not all(math.isfinite(v) for v in (K, T, sigma0, skew, curvature, r, q))
            or K <= 0 or T <= 0):
        raise ValueError('Domaine Dupire legacy invalide (strike ou maturité).')
    x = math.log(K)
    sigma = sigma0+skew*x+curvature*x*x
    if not 0 < sigma <= 2:
        raise ValueError('Smile legacy hors domaine : volatilité implicite non positive ou supérieure à 200 %. Requalifiez explicitement la surface.')
    # Exact derivatives of the unmodified legacy polynomial. No implied-vol
    # fallback, short-tenor substitution or hidden clipping is admissible.
    slope = skew+2*curvature*x
    y = x-(r-q)*T
    w0 = sigma*sigma*T
    dwdT = sigma*sigma+2*T*sigma*slope*(r-q)
    dwdy = 2*T*sigma*slope
    d2wdy2 = 2*T*(slope*slope+2*sigma*curvature)
    den = (1.0 - y * dwdy / w0
           + 0.25 * (-0.25 - 1.0 / w0 + y * y / (w0 * w0)) * dwdy ** 2
           + 0.5 * d2wdy2)
    if not (math.isfinite(dwdT) and math.isfinite(den)) or den <= 1e-9 or dwdT <= 0:
        raise ValueError('Smile legacy non admissible en Local Vol : densité ou variance calendaire invalide. Requalifiez explicitement la surface.')
    sig = math.sqrt(dwdT / den)
    if not math.isfinite(sig) or sig <= 0:
        raise ValueError('Smile legacy : volatilité locale non finie ou non positive.')
    if sig > 3:
        raise ValueError(
            f'Smile legacy : volatilité locale de {100*sig:.2f} % au niveau {100*K:.2f} % '
            f'du spot de référence à {T:.4f} an. Plafond numérique : 300 %.'
        )
    return sig


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

    times = _times(dt, ts)[1:]
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


_SSVI_LOCAL_VOL_LIMIT = 3.
_SSVI_PROTECTED_LOG_FORWARD = (math.log(.20), math.log(1.80))


def _extend_ssvi_local_vol_wings(row, log_forward):
    """Bound only contiguous outer runs above the numerical limit."""
    valid = np.flatnonzero(row <= _SSVI_LOCAL_VOL_LIMIT)
    if not len(valid):
        return None
    first, last = int(valid[0]), int(valid[-1])
    if len(valid) != last - first + 1:
        return None
    # Preserve the interpolation segment containing each protected endpoint.
    lower, upper = _SSVI_PROTECTED_LOG_FORWARD
    if (first and log_forward[first] > lower) or (last < len(row) - 1 and log_forward[last] < upper):
        return None
    wings = {}
    if first:
        row[:first] = _SSVI_LOCAL_VOL_LIMIT
        wings["left"] = math.exp(log_forward[first - 1])
    if last < len(row) - 1:
        row[last + 1:] = _SSVI_LOCAL_VOL_LIMIT
        wings["right"] = math.exp(log_forward[last + 1])
    return wings


def _build_lv_grid(underlyings, rates: "_RateTerm", ts: int, dt: float, nK: int = 50,
                   *, allow_ssvi_wings=False, wing_diagnostics=None):
    """Precompute local vol grid (ts, nK) for each underlying asset.

    Takes the run's rate term rather than a scalar so the Black-Scholes prices
    the Dupire inversion is built on are discounted at the same curve that
    discounts the payoff — the calibration is the third place a rate enters a
    pricing run, and it used to be the one nobody wired to the curve."""
    has_surface = any(u.get('vol_surface') for u in underlyings)
    if has_surface:
        nK = max(nK, 300)
    logKmin, logKmax = ((math.log(.01), math.log(10.)) if has_surface
                       else (math.log(.20), math.log(3.)))
    Ks = [math.exp(logKmin + i/(nK-1)*(logKmax-logKmin)) for i in range(nK)]
    log_spots = np.log(Ks)
    grids = []
    dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)
    for asset_index, u in enumerate(underlyings):
        if u.get('vol_surface'):
            from ..volatility_surface import surface_from_underlying
            surface = surface_from_underlying(u, _time_at(dt, ts))
            grid = np.empty((ts, nK), dtype=np.float64)
            wing_steps = {}
            for step in range(ts):
                t = (_time_at(dt, step) + .5 * _durations(dt, ts)[step])
                # Integrate the same carry used by the diffusion, interpolated
                # to mid-step. Dupire derivatives are at fixed forward k.
                r0 = rates.r_flat if rates.zero is None else float(rates.zero[step])
                r1 = rates.r_flat if rates.zero is None else float(rates.zero[step+1])
                carry = (r0*_time_at(dt, step)+r1*_time_at(dt, step + 1))/2
                carry -= (u.get('q',.02)*t if dividend_steps is None else
                          float(np.dot(dividend_steps[:step,asset_index], _durations(dt, ts)[:step]))+
                          .5*_durations(dt, ts)[step]*float(dividend_steps[step,asset_index]))
                log_forward = log_spots - carry
                row = surface.local_vol(log_forward, t)
                if not np.all(np.isfinite(row)) or np.any(row <= 0):
                    raise ValueError('Surface Local Vol/LSV : volatilité locale non finie ou non positive.')
                if allow_ssvi_wings and np.any(row > _SSVI_LOCAL_VOL_LIMIT):
                    wings = _extend_ssvi_local_vol_wings(row, log_forward)
                    if wings is not None:
                        for side, boundary in wings.items():
                            wing_steps.setdefault(side, []).append(dict(t=t, boundary_forward=boundary))
                grid[step] = row
            if np.any(grid > _SSVI_LOCAL_VOL_LIMIT):
                step, node = np.unravel_index(np.argmax(grid), grid.shape)
                t = _time_at(dt, step) + .5 * _durations(dt, ts)[step]
                raise ValueError(
                    f'Surface Local Vol/LSV : volatilité locale de {100*grid[step, node]:.2f} % '
                    f'au niveau {100*Ks[node]:.2f} % du spot de référence à {t:.4f} an. '
                    'Plafond numérique : 300 %.'
                )
            if wing_diagnostics is not None:
                for side, steps in wing_steps.items():
                    wing_diagnostics.append(dict(
                        underlying_index=asset_index,
                        underlying=u.get("name") or u.get("ticker") or f"S{asset_index + 1}",
                        side=side, limit=_SSVI_LOCAL_VOL_LIMIT, steps=steps))
            grids.append(grid)
            continue
        sig0 = u.get("sigma", 0.20)
        skew = u.get("skew", 0.0)
        curv = u.get("curvature", 0.0)
        q_flat = u.get("q", 0.02)
        g = np.zeros((ts, nK), dtype=np.float32)
        for step in range(ts):
            T_s = _time_at(dt, step + 1)
            # Zero rate to this maturity — the right discount for a call
            # expiring at T_s. Falls back to the scalar when there is no curve.
            r_s = rates.r_flat if rates.zero is None else float(rates.zero[step + 1])
            # The Dupire surface needs the same cumulative dividend carry as
            # the paths. For a term structure this is the continuously
            # compounded zero-equivalent q(0,T); for the legacy flat case the
            # scalar is retained exactly.
            q_s = (q_flat if dividend_steps is None
                   else float(np.average(dividend_steps[:step + 1, asset_index], weights=_durations(dt, ts)[:step + 1])))
            for ki, K in enumerate(Ks):
                lv = _dupire_vol(K, T_s, sig0, skew, curv, r_s, q_s)
                g[step, ki] = lv
        grids.append(g)
    return grids, nK, logKmin, logKmax
