"""
Stress scenario grid — price the product under combined spot x vol shocks.

Unlike simulation.py (which shocks script PARAMs), this shocks MARKET data:
spot (multiplicative, e.g. -10% -> spot_mult=0.90) and vol (additive, e.g.
+5pp -> vol_add=0.05), applied uniformly to every underlying. Both are
already native parameters of engine.run_mc (the same mechanism compute_greeks
uses for bump-and-reprice), so this module is just the grid loop around it —
no new pricing primitive needed, and every model (constant/heston/sabr/
localvol) is supported as-is since vol_add is wired into all four.

Same seed as the main pricing run (common random numbers) keeps the grid
smooth and comparable cell-to-cell: differences between cells reflect the
shock, not Monte Carlo noise.
"""
from __future__ import annotations
from .parser import CompiledScript
from .engine import run_mc

# Stress cells use a reduced path count by default — the grid only needs to be
# smooth/comparable, not maximally precise, and cost scales as
# len(spot_shocks) * len(vol_shocks) * N.
DEFAULT_SCENARIO_N = 2000


def _price_with_shocks(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                        N: int, model: str, seed: int, user_params: dict,
                        spot_shock: float, vol_shock: float, rate_shock: float = 0.0) -> float:
    """Reprice with shocked spot/vol/rate, all else (incl. seed) held fixed.

    rate_shock defaults to 0 and isn't exposed as a grid axis yet — run_mc
    already accepts it (dr), so adding a 3rd axis later only means wiring a
    new loop dimension here, not a new pricing primitive.
    """
    n = len(underlyings)
    res = run_mc(script, underlyings, corr_matrix, r, T, N, model, seed,
                 antithetic=True, user_params=user_params,
                 spot_mult=[1.0 + spot_shock] * n, vol_add=[vol_shock] * n, dr=rate_shock)
    return res["price"]


def compute_scenario_grid(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
                           model: str, seed: int, user_params: dict,
                           spot_shocks: list[float], vol_shocks: list[float],
                           N: int = DEFAULT_SCENARIO_N) -> dict:
    """2D stress grid: price(spot_shock, vol_shock) for every combination, plus
    the unshocked base price for reference (computed independently of whether
    0.0 is actually present in the shock lists)."""
    base_price = _price_with_shocks(script, underlyings, corr_matrix, r, T, N, model, seed,
                                     user_params, 0.0, 0.0)

    prices: list[list[float]] = []
    for dV in vol_shocks:
        row = [round(_price_with_shocks(script, underlyings, corr_matrix, r, T, N, model, seed,
                                         user_params, dS, dV), 6)
               for dS in spot_shocks]
        prices.append(row)

    return {
        "spot_shocks": spot_shocks,
        "vol_shocks": vol_shocks,
        "base_price": round(base_price, 6),
        "prices": prices,
    }
