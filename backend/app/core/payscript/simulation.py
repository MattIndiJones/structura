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
                        base_user_params: dict, overrides: dict) -> float:
    """Price the product with one or more PARAMs overridden, all else held fixed."""
    user_params = {**base_user_params, **overrides}
    res = run_mc(script, underlyings, corr_matrix, r, T, N, model, seed,
                 antithetic=True, user_params=user_params)
    return res["price"]


# ── Solver: 1D root-find on a single PARAM ──────────────────────────

def _solver_result(param_name: str, x: float, price: float, target: float, iterations: int,
                    trace: list[dict], converged: bool, message: str | None = None) -> dict:
    return {
        "param_name": param_name,
        "param_value": round(x, 6),
        "achieved_price": round(price, 6),
        "target_price": round(target, 6),
        "residual": round(price - target, 6),
        "iterations": iterations,
        "converged": converged,
        "message": message,
        "trace": [{"iter": t["iter"], "x": round(t["x"], 6), "price": round(t["price"], 6)}
                  for t in trace],
    }


def solve_for_param(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                     model: str, seed: int, base_user_params: dict,
                     param_name: str, target_price: float, lo: float, hi: float,
                     N: int = DEFAULT_SOLVER_N, tol: float = 1e-4, max_iter: int = 40) -> dict:
    """Bisection root-find: find param_value in [lo, hi] such that
    price(param_value) == target_price.

    Bisection requires price(lo) and price(hi) to bracket target_price — true for
    the common monotonic cases (e.g. higher COUPON -> higher price). If the bracket
    doesn't hold, the closest endpoint is returned with converged=False rather than
    raising, so the caller can inspect the trace and adjust [lo, hi].
    """
    def f(x: float) -> float:
        return _price_with_params(script, underlyings, corr_matrix, r, T, N, model, seed,
                                   base_user_params, {param_name: x}) - target_price

    f_lo, f_hi = f(lo), f(hi)
    trace = [{"iter": 0, "x": lo, "price": f_lo + target_price},
              {"iter": 0, "x": hi, "price": f_hi + target_price}]

    if abs(f_lo) < tol:
        return _solver_result(param_name, lo, f_lo + target_price, target_price, 0, trace, True)
    if abs(f_hi) < tol:
        return _solver_result(param_name, hi, f_hi + target_price, target_price, 0, trace, True)
    if (f_lo > 0) == (f_hi > 0):
        best_x, best_f = (lo, f_lo) if abs(f_lo) < abs(f_hi) else (hi, f_hi)
        return _solver_result(
            param_name, best_x, best_f + target_price, target_price, 0, trace, False,
            "Le prix cible n'est pas compris entre les prix aux bornes lo/hi — "
            "élargissez l'intervalle de recherche.")

    a, b, fa = lo, hi, f_lo
    x_mid, f_mid = a, fa
    for i in range(1, max_iter + 1):
        x_mid = (a + b) / 2
        f_mid = f(x_mid)
        trace.append({"iter": i, "x": x_mid, "price": f_mid + target_price})
        if abs(f_mid) < tol or (b - a) / 2 < tol:
            return _solver_result(param_name, x_mid, f_mid + target_price, target_price, i, trace, True)
        if (f_mid > 0) == (fa > 0):
            a, fa = x_mid, f_mid
        else:
            b = x_mid

    return _solver_result(
        param_name, x_mid, f_mid + target_price, target_price, max_iter, trace, False,
        "Nombre maximal d'itérations atteint sans convergence sous la tolérance.")


# ── Grid: 2D price heatmap over two PARAMs ──────────────────────────

def compute_price_grid(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                        model: str, seed: int, base_user_params: dict,
                        param_x: str, x_min: float, x_max: float, x_steps: int,
                        param_y: str, y_min: float, y_max: float, y_steps: int,
                        N: int = DEFAULT_GRID_N) -> dict:
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
                                    base_user_params, {param_x: x, param_y: y})
            row.append(round(p, 6))
        prices.append(row)

    return {
        "param_x": param_x, "x_values": [round(x, 6) for x in xs],
        "param_y": param_y, "y_values": [round(y, 6) for y in ys],
        "prices": prices,
    }
