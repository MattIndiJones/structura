"""Conditional barrier reconstruction and its explicit basket approximation.

Correlated Gaussian midpoint bridges carry the dependence between assets.
At the last subinterval only, one-dimensional exact extrema are sampled with
independent residuals between non-perfectly-correlated factors. Refinement
reduces that residual joint-law approximation; it does not make it exact.
"""
import math
from .time_grid import durations

import numpy as np

BASKET_BRIDGE_SUBSTEPS = 64
MAX_BASKET_BRIDGE_SUBSTEPS = 1024
QUALIFICATION_TOLERANCE_NOMINAL = .001
BRIDGE_POLICY = "C16-CORRELATED-MIDPOINTS-MARGINAL-LEAVES-2026-10-21"


def basket_bridge_substeps(correlation=None):
    """Explicit refinement policy; unknown matrices use the conservative cap."""
    if correlation is None:
        return MAX_BASKET_BRIDGE_SUBSTEPS
    matrix = np.asarray(correlation, dtype=float)
    off_diagonal = np.abs(matrix - np.diag(np.diag(matrix)))
    strongest = off_diagonal.max()
    if strongest <= .5:
        return BASKET_BRIDGE_SUBSTEPS
    if strongest <= .9:
        return 256
    return MAX_BASKET_BRIDGE_SUBSTEPS


def validate_bridge_domain(underlyings, correlation, model, stochastic_rates=False):
    """Admit only the locally qualified basket domain; never change monitoring."""
    n = len(underlyings)
    if n <= 1:
        return
    matrix = np.asarray(correlation)
    bodies = [{key: value for key, value in u.items() if key not in {"name", "ticker"}}
              for u in underlyings]
    copies = np.all(matrix == 1.) and all(body == bodies[0] for body in bodies)
    if model == "constant" and copies:
        return
    if n == 2 and model == "constant" and not stochastic_rates and abs(matrix[0, 1]) <= .99:
        return
    raise ValueError(
        "Monitoring continu panier non qualifié pour cette configuration : domaine local C16 "
        "limité au GBM à deux actifs, taux déterministes et |corrélation| <= 99 %, ou aux "
        "copies GBM équivalentes corrélées à 1. Aucun passage automatique en hebdomadaire. "
        "Une qualification complémentaire est nécessaire.")


def resolve_bridge_substeps(correlation, override=None):
    selected = basket_bridge_substeps(correlation)
    if override is None:
        return selected
    if (not isinstance(override, int) or override < selected or override > MAX_BASKET_BRIDGE_SUBSTEPS
            or override & (override-1)):
        raise ValueError("Raffinement des ponts inférieur à la politique C16 ou hors domaine.")
    return override


def semidefinite_factor(matrix):
    """PSD square root without artificial noise on zero-variance factors."""
    values, vectors = np.linalg.eigh(matrix)
    factor = vectors * np.sqrt(np.where(values > 1e-12, values, 0.))[None, :]
    for i in range(len(matrix)):
        for j in range(i):
            if np.array_equal(matrix[i], matrix[j]):
                factor[i] = factor[j]
                break
    return factor


def _marginal_extrema(left, right, volatility, duration, rng, groups=None):
    variance = volatility**2 * duration
    shape = left.shape
    if groups is None:
        lower_u = rng.uniform(1e-12, 1.0, size=shape)
        upper_u = rng.uniform(1e-12, 1.0, size=shape)
    else:
        count = max(group for group, _ in groups) + 1
        u = rng.uniform(1e-12, 1.0, size=(count, shape[-1]))
        v = rng.uniform(1e-12, 1.0, size=(count, shape[-1]))
        # Opposite Brownian factors exchange their lower/upper excursions.
        lower_u = np.array([u[g] if sign == 1 else v[g] for g, sign in groups])
        upper_u = np.array([v[g] if sign == 1 else u[g] for g, sign in groups])
    delta_squared = (right - left)**2
    lower = .5 * (left + right - np.sqrt(delta_squared - 2 * variance * np.log(lower_u)))
    upper = .5 * (left + right + np.sqrt(delta_squared - 2 * variance * np.log(upper_u)))
    return lower, upper


def _correlation_factor(correlation, n):
    matrix = np.asarray(correlation, dtype=float)
    if (matrix.shape != (n, n) or not np.isfinite(matrix).all()
            or not np.allclose(matrix, matrix.T, atol=1e-12, rtol=0)
            or not np.allclose(np.diag(matrix), 1., atol=1e-12, rtol=0)
            or np.abs(matrix).max() > 1. + 1e-12):
        raise ValueError("Corrélation des ponts browniens invalide.")
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    if eigenvalues.min() < -1e-10:
        raise ValueError("La corrélation des ponts browniens doit être positive semi-définie.")
    # A PSD square root preserves singular perfect factors without diagonal jitter.
    factor = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0.))[None, :]
    groups, representatives = [], []
    for i in range(n):
        for group, representative in enumerate(representatives):
            rho = matrix[i, representative]
            if rho == 1. or rho == -1.:
                sign = 1 if rho == 1. else -1
                groups.append((group, sign))
                factor[i] = sign * factor[representative]
                break
        else:
            groups.append((len(representatives), 1))
            representatives.append(i)
    return factor, groups


def bridge_extrema(spots, volatilities, dt, rng, correlation=None,
                   *, substeps=None, diagnostics=None):
    """Return positive lower/upper extrema of shape (steps, assets, paths).

    Mono preserves the existing analytic marginal sampler and its RNG order.
    Identical conditional copies with correlation +1 share its exact draws.
    Other baskets use correlated midpoint bridges and marginal leaf extrema.
    The two extrema of one leaf are sampled independently: their joint law is
    approximate even in mono; no general double-barrier exactness is claimed.
    """
    if (spots.ndim != 3 or volatilities.shape != (spots.shape[0]-1, *spots.shape[1:])
            or min(volatilities.shape) < 1
            or not np.isfinite(spots).all() or (spots <= 0).any()
            or not np.isfinite(volatilities).all() or (volatilities < 0).any()):
        raise ValueError("Trajectoires, volatilités ou pas des ponts browniens invalides.")
    if substeps is None:
        substeps = basket_bridge_substeps(correlation)
    if not isinstance(substeps, int) or substeps < 1 or substeps > 1024 or substeps & (substeps-1):
        raise ValueError("Le raffinement des ponts doit être une puissance de deux entre 1 et 1024.")
    steps, n, paths = volatilities.shape
    lengths = durations(dt, steps)
    logs = np.log(spots)
    if n == 1:
        if diagnostics is not None:
            diagnostics.update(method="analytic_marginals", basket_substeps=1,
                               conditional_asset_dependence_exact=True)
        low, high = _marginal_extrema(logs[:-1], logs[1:], volatilities, lengths[:, None, None], rng)
        return np.exp(low), np.exp(high)
    if correlation is None:
        raise ValueError("Le pont brownien panier exige sa matrice de corrélation.")
    factor, groups = _correlation_factor(correlation, n)
    ratios = spots / spots[:, :1]
    if (all(group == (0, 1) for group in groups)
            and np.allclose(ratios, ratios[:1], rtol=1e-12, atol=0)
            and np.array_equal(volatilities, np.repeat(volatilities[:, :1], n, axis=1))):
        low, high = bridge_extrema(spots[:, :1], volatilities[:, :1], dt, rng)
        if diagnostics is not None:
            diagnostics.update(method="equivalent_conditional_copies", basket_substeps=1,
                               conditional_asset_dependence_exact=True)
        return low * ratios[:1], high * ratios[:1]
    if all(group == (0, 1) for group in groups):
        raise ValueError("Les copies du panier ne partagent pas le même pont conditionnel ; configuration non qualifiée.")
    if diagnostics is not None:
        diagnostics.update(method="correlated_midpoints_with_marginal_leaves", basket_substeps=substeps,
                           conditional_asset_dependence_exact=False)

    low, high = np.empty_like(volatilities), np.empty_like(volatilities)
    depth = substeps.bit_length() - 1
    for step in range(steps):
        volatility = volatilities[step]
        def refine(left, right, duration, remaining):
            if remaining == 0:
                return _marginal_extrema(left, right, volatility, duration, rng, groups)
            noise = factor @ rng.standard_normal((n, paths))
            middle = .5 * (left + right) + .5 * math.sqrt(duration) * volatility * noise
            low_left, high_left = refine(left, middle, duration / 2, remaining - 1)
            low_right, high_right = refine(middle, right, duration / 2, remaining - 1)
            return np.minimum(low_left, low_right), np.maximum(high_left, high_right)
        low[step], high[step] = refine(logs[step], logs[step+1], float(lengths[step]), depth)
    return np.exp(low), np.exp(high)


def bridge_metadata(n, correlation=None, substeps=None):
    return {
        "policy": BRIDGE_POLICY,
        "method": "analytic_marginals" if n == 1 else "correlated_midpoints_with_marginal_leaves",
        "basket_substeps": resolve_bridge_substeps(correlation, substeps) if n > 1 else 1,
        "refinement_rule": "64 if max(abs(rho))<=0.5; 256 if <=0.9; 1024 otherwise",
        "joint_extrema_exact": False,
        "qualification": "local_synthetic_panel_only",
        "qualification_scope": "one_sided_two_asset_gbm_conditional_digital_or_equivalent_copies",
        "qualification_tolerance_nominal": QUALIFICATION_TOLERANCE_NOMINAL,
        "per_run_error_bound": None,
    }


def bridge_note(n, correlation=None, substeps=None):
    if n == 1:
        return ("Monitoring continu par pont brownien : chaque extremum marginal est exact "
                "conditionnellement aux extrémités sous GBM à volatilité constante et taux "
                "déterministes. La loi jointe minimum/maximum et les autres modèles restent approximatifs.")
    return (f"Monitoring continu panier approximatif : ponts browniens corrélés, "
            f"jusqu'à {resolve_bridge_substeps(correlation, substeps)} sous-pas par pas MC et extrema marginaux sur les sous-intervalles. "
            "La dépendance résiduelle des extrema reste approximative ; ce calcul n'est pas "
            "une loi jointe exacte. Qualification locale limitée au panel documenté C16.")
