"""
Simulation tools — higher-level workflows built on top of the Monte Carlo
pricing engine (engine.run_mc). Two features:

  - solve_for_param: find the script PARAM value that hits a target price
    (1D root-finding by bisection).
  - compute_price_grid: 2D price heatmap over two script PARAM ranges.

Both vary ONE OR TWO of the script's PARAM values (the same `user_params`
override mechanism used everywhere else) while holding the market data and
all other PARAMs fixed, and reuse the SAME MC seed across every evaluation
(common random numbers — the same trick engine.compute_greeks uses). This
keeps the price curve/surface smooth enough to root-find or grid reliably
despite Monte Carlo noise.
"""
from __future__ import annotations
from .parser import CompiledScript
from .engine import run_mc

# Every solver iteration / grid cell is a fresh full MC run, so cost scales as
# N_eval * N (solver) or x_steps * y_steps * N (grid). Keep N modest by default.
DEFAULT_SOLVER_N = 8000
DEFAULT_GRID_N = 4000


def _price_with_params(script: CompiledScript, underlyings, corr_matrix, r: float,
                        T: float, N: int, model: str, seed: int,
                        base_user_params: dict, overrides: dict,
                        yield_curve=None, sigma_r: float = 0.0, a_r: float = 0.0,
                        barrier_monitoring: str = "weekly",
                        state: dict | None = None, funding_curve=None,
                        funding_spread: float = 0.0, valuation_context=None) -> float:
    """Price the product with one or more PARAMs overridden, all else held fixed.

    `state` porte l'etat d'un produit deja en cours de vie — memoire de coupons,
    extrema franchis, niveau du jour. Entonnoir unique du solveur ET de la
    grille : le brancher ici les aligne tous les deux sur la jambe residuelle.
    """
    user_params = {**base_user_params, **overrides}
    if valuation_context is not None:
        from copy import deepcopy
        from ..valuation_context import run_valuation
        context = deepcopy(valuation_context)
        context.user_params = user_params
        return run_valuation(script, context)['price']
    res = run_mc(script, underlyings, corr_matrix, r, T, N, model, seed,
                 antithetic=True, user_params=user_params,
                 yield_curve=yield_curve or [], sigma_r=sigma_r, a_r=a_r,
                 funding_curve=funding_curve or [], funding_spread=funding_spread,
                 barrier_monitoring=barrier_monitoring, **(state or {}))
    return res["price"]


# ── Solver: 1D root-find on a single PARAM ──────────────────────────

def _solver_result(param_name: str, x: float, price: float, target: float, iterations: int,
                    trace: list[dict], converged: bool, message: str | None = None) -> dict:
    return {
        "param_name": param_name,
        "param_value": round(x, 6),
        "achieved_price": price,
        "target_price": target,
        "residual": price - target,
        "iterations": iterations,
        "converged": converged,
        "message": message,
        "trace": [{"iter": t["iter"], "x": t["x"], "price": t["price"]}
                  for t in trace],
    }


def solve_for_param(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                     model: str, seed: int, base_user_params: dict,
                     param_name: str, target_price: float, lo: float, hi: float,
                     N: int = DEFAULT_SOLVER_N, tol: float = 1e-4, max_iter: int = 40,
                     yield_curve=None, sigma_r: float = 0.0, a_r: float = 0.0,
                     barrier_monitoring: str = "weekly",
                     state: dict | None = None, funding_curve=None,
                     funding_spread: float = 0.0, valuation_context=None,
                     param_tol: float = 5e-7) -> dict:
    """Bisection root-find: find param_value in [lo, hi] such that
    price(param_value) == target_price.

    Bisection requires price(lo) and price(hi) to bracket target_price — true for
    the common monotonic cases (e.g. higher COUPON -> higher price). If the bracket
    doesn't hold, the closest endpoint is returned with converged=False rather than
    raising, so the caller can inspect the trace and adjust [lo, hi].
    ``tol`` measures price error; ``param_tol`` only stops interval reduction.
    Convergence is checked again at the six-decimal parameter being published.
    """
    def f(x: float) -> float:
        return _price_with_params(script, underlyings, corr_matrix, r, T, N, model, seed,
                                   base_user_params, {param_name: x},
                                   yield_curve=yield_curve, sigma_r=sigma_r, a_r=a_r,
                                   barrier_monitoring=barrier_monitoring, state=state,
                                   funding_curve=funding_curve, funding_spread=funding_spread,
                                   valuation_context=valuation_context) - target_price

    if tol <= 0 or param_tol <= 0 or lo > hi:
        raise ValueError("Tolérances positives et intervalle lo <= hi requis.")

    def finish(x, iterations, reason, parameter_converged=False):
        # Only the parameter actually published is actionable. Reprice it even
        # when rounding crosses a payoff discontinuity or a steep price slope.
        published = round(x, 6)
        residual = f(published)
        price_converged = abs(residual) <= tol
        if price_converged:
            reason = "price_tolerance"
        elif reason == "price_tolerance":
            reason = "parameter_rounding"
        messages = {
            "price_tolerance": None,
            "parameter_tolerance": "Intervalle du paramètre réduit sans atteindre le prix cible.",
            "parameter_rounding": "Le paramètre arrondi publié n'atteint pas le prix cible.",
            "not_bracketed": "Le prix cible n'est pas compris entre les prix aux bornes lo/hi — élargissez l'intervalle de recherche.",
            "max_iterations": "Nombre maximal d'itérations atteint sans convergence en prix.",
        }
        result = _solver_result(
            param_name, published, residual + target_price, target_price,
            iterations, trace, price_converged, messages[reason])
        result.update(price_converged=price_converged,
                      parameter_converged=parameter_converged,
                      stop_reason=reason, price_tolerance=tol,
                      parameter_tolerance=param_tol,
                      published_parameter_repriced=True)
        return result

    f_lo, f_hi = f(lo), f(hi)
    trace = [{"iter": 0, "x": lo, "price": f_lo + target_price},
              {"iter": 0, "x": hi, "price": f_hi + target_price}]

    if abs(f_lo) <= tol:
        return finish(lo, 0, "price_tolerance")
    if abs(f_hi) <= tol:
        return finish(hi, 0, "price_tolerance")
    if (f_lo > 0) == (f_hi > 0):
        best_x = lo if abs(f_lo) < abs(f_hi) else hi
        return finish(best_x, 0, "not_bracketed")

    a, b, fa = lo, hi, f_lo
    x_mid, f_mid = a, fa
    for i in range(1, max_iter + 1):
        x_mid = (a + b) / 2
        f_mid = f(x_mid)
        trace.append({"iter": i, "x": x_mid, "price": f_mid + target_price})
        if abs(f_mid) <= tol:
            return finish(x_mid, i, "price_tolerance")
        if (b - a) / 2 <= param_tol:
            return finish(x_mid, i, "parameter_tolerance", True)
        if (f_mid > 0) == (fa > 0):
            a, fa = x_mid, f_mid
        else:
            b = x_mid

    return finish(x_mid, max_iter, "max_iterations")


# ── Grid: 2D price heatmap over two PARAMs ──────────────────────────

def compute_price_grid(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                        model: str, seed: int, base_user_params: dict,
                        param_x: str, x_min: float, x_max: float, x_steps: int,
                        param_y: str, y_min: float, y_max: float, y_steps: int,
                        N: int = DEFAULT_GRID_N,
                        yield_curve=None, sigma_r: float = 0.0, a_r: float = 0.0,
                        barrier_monitoring: str = "weekly",
                        state: dict | None = None, valuation_context=None) -> dict:
    """2D price heatmap: price(param_x, param_y) over an evenly-spaced grid, all
    other PARAMs and market data held at their current values.

    Returns prices as a list of rows (one per y value), each row a list of prices
    across x values — i.e. prices[j][i] is the price at (x_values[i], y_values[j]).
    """
    xs = [x_min + i * (x_max - x_min) / max(1, x_steps - 1) for i in range(x_steps)]
    ys = [y_min + j * (y_max - y_min) / max(1, y_steps - 1) for j in range(y_steps)]

    prices: list[list[float]] = []
    for y in ys:
        row = []
        for x in xs:
            p = _price_with_params(script, underlyings, corr_matrix, r, T, N, model, seed,
                                    base_user_params, {param_x: x, param_y: y},
                                    yield_curve=yield_curve, sigma_r=sigma_r, a_r=a_r,
                                    barrier_monitoring=barrier_monitoring, state=state,
                                    valuation_context=valuation_context)
            row.append(round(p, 6))
        prices.append(row)

    return {
        "param_x": param_x, "x_values": [round(x, 6) for x in xs],
        "param_y": param_y, "y_values": [round(y, 6) for y in ys],
        "prices": prices,
    }
