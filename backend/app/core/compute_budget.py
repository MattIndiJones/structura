"""Central resource limits for PayScript parsing and quantitative calculations.

The limits are business-facing safeguards, not performance promises.  They keep
one malformed or oversized request from exhausting the local workstation while
leaving a wide margin above Structura's current product templates.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass


MAX_SCRIPT_CHARS = 32_000
MAX_SCRIPT_LINES = 1_000
MAX_EXPANDED_DATES = 5_000
MATURITY_WARNING_YEARS = 10.0
MAX_MATURITY_YEARS = 30.0
UNDERLYING_WARNING_COUNT = 6
MAX_UNDERLYINGS = 12

SYNC_MEMORY_LIMIT_BYTES = 1 * 1024**3
WORKER_MEMORY_LIMIT_BYTES = 2 * 1024**3

# A unit is one weekly path/asset/model operation.  The value is deliberately
# independent of wall-clock time; model and machine speed cannot turn a hard
# safety rule into a moving target.
SYNC_WORK_LIMIT = 250_000_000
ABSOLUTE_WORK_LIMIT = 1_000_000_000
BATCH_CONFIRM_WORK_LIMIT = 5_000_000_000
BATCH_ABSOLUTE_WORK_LIMIT = 50_000_000_000
BATCH_ABSOLUTE_CELLS = 50_000

_MODEL_WORK_FACTOR = {
    "constant": 1.0,
    "heston": 2.0,
    "sabr": 2.0,
    "localvol": 2.5,
    "lsv": 3.5,
}
_MODEL_ARRAY_FACTOR = {
    "constant": 2.0,   # Gaussian tensor + path tensor
    "heston": 3.0,     # + variance Gaussian tensor
    "sabr": 3.0,       # + alpha Gaussian tensor
    "localvol": 2.5,   # interpolation workspace
    "lsv": 3.5,        # local-vol workspace + variance Gaussian tensor
}
_SCRIPT_EVENT_WORK_FACTOR = 4.0


@dataclass(frozen=True)
class CalculationEstimate:
    operation: str
    maturity_years: float
    steps: int
    underlyings: int
    paths: int
    repricings: float
    expanded_dates: int
    work_units: int
    estimated_peak_bytes: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        out = asdict(self)
        out["estimated_peak_mb"] = round(self.estimated_peak_bytes / 1024**2, 1)
        out["warnings"] = list(self.warnings)
        return out


def validate_script_source(script: str) -> None:
    if len(script) > MAX_SCRIPT_CHARS:
        raise ValueError(
            f"Script PayScript trop volumineux : {len(script):,} caractères "
            f"(maximum {MAX_SCRIPT_CHARS:,})."
        )
    lines = script.count("\n") + 1
    if lines > MAX_SCRIPT_LINES:
        raise ValueError(
            f"Script PayScript trop long : {lines:,} lignes "
            f"(maximum {MAX_SCRIPT_LINES:,})."
        )


def validate_problem_dimensions(maturity_years: float, underlyings: int) -> None:
    if not math.isfinite(maturity_years) or maturity_years <= 0:
        raise ValueError("La maturité doit être un nombre fini strictement positif.")
    if maturity_years > MAX_MATURITY_YEARS:
        raise ValueError(
            f"Maturité effective trop longue : {maturity_years:g} ans "
            f"(maximum {MAX_MATURITY_YEARS:g} ans)."
        )
    if underlyings < 1:
        raise ValueError("Le calcul requiert au moins un sous-jacent.")
    if underlyings > MAX_UNDERLYINGS:
        raise ValueError(
            f"Trop de sous-jacents : {underlyings} "
            f"(maximum {MAX_UNDERLYINGS})."
        )


def count_compiled_dates(script) -> int:
    total = 0
    for event in getattr(script, "events", ()):
        total += len(getattr(event, "dates", ()) or ())
        for window in getattr(event, "window_dates", ()) or ():
            total += len(window or ())
    total += len(getattr(script, "strike_fix_dates", ()) or ())
    return total


def validate_compiled_dates(script) -> None:
    total = count_compiled_dates(script)
    if total > MAX_EXPANDED_DATES:
        raise ValueError(
            f"Calendrier trop volumineux : {total:,} dates développées "
            f"(maximum {MAX_EXPANDED_DATES:,})."
        )


def estimate_mc(
    *,
    operation: str,
    maturity_years: float,
    underlyings: int,
    paths: int,
    model: str,
    antithetic: bool = True,
    continuous_monitoring: bool = False,
    stochastic_rates: bool = False,
    repricings: float = 1.0,
    expanded_dates: int = 0,
) -> CalculationEstimate:
    validate_problem_dimensions(maturity_years, underlyings)
    if paths < 1:
        raise ValueError("Le nombre de trajectoires doit être strictement positif.")
    if not math.isfinite(repricings) or repricings <= 0:
        raise ValueError("Le multiplicateur de calcul doit être strictement positif.")
    if expanded_dates < 0 or expanded_dates > MAX_EXPANDED_DATES:
        raise ValueError(
            f"Nombre de dates développées invalide : {expanded_dates} "
            f"(maximum {MAX_EXPANDED_DATES:,})."
        )

    steps = max(1, round(maturity_years * 52))
    model_work = _MODEL_WORK_FACTOR.get(model, 1.0)
    work_factor = model_work
    if antithetic:
        work_factor *= 2.0
    if continuous_monitoring:
        work_factor *= 1.35
    if stochastic_rates:
        work_factor *= 1.25
    simulation_units = steps * underlyings * paths * work_factor
    path_legs = 2.0 if antithetic else 1.0
    script_units = expanded_dates * paths * path_legs * _SCRIPT_EVENT_WORK_FACTOR
    work_units = math.ceil((simulation_units + script_units) * repricings)

    # The antithetic leg reuses the Gaussian tensors and releases the first
    # path tensor before allocating the second, so it affects work but not the
    # leading peak-memory term.  35% covers state arrays and Python containers.
    array_factor = _MODEL_ARRAY_FACTOR.get(model, 2.0)
    if continuous_monitoring:
        array_factor += 1.0
    cells = (steps + 1) * underlyings * paths
    peak = math.ceil(cells * 8 * array_factor * 1.35)
    if stochastic_rates:
        peak += math.ceil((steps + 1) * paths * 8 * 3.0 * 1.20)

    warnings: list[str] = []
    if maturity_years > MATURITY_WARNING_YEARS:
        warnings.append(f"Maturité longue : {maturity_years:g} ans.")
    if underlyings > UNDERLYING_WARNING_COUNT:
        warnings.append(f"Panier large : {underlyings} sous-jacents.")
    if peak > SYNC_MEMORY_LIMIT_BYTES or work_units > SYNC_WORK_LIMIT:
        warnings.append("Calcul lourd : exécution synchrone déconseillée.")

    return CalculationEstimate(
        operation=operation,
        maturity_years=float(maturity_years),
        steps=steps,
        underlyings=underlyings,
        paths=paths,
        repricings=float(repricings),
        expanded_dates=expanded_dates,
        work_units=work_units,
        estimated_peak_bytes=peak,
        warnings=tuple(warnings),
    )


def ensure_budget(
    estimate: CalculationEstimate,
    *,
    memory_limit_bytes: int = SYNC_MEMORY_LIMIT_BYTES,
    work_limit: int = SYNC_WORK_LIMIT,
) -> None:
    if estimate.estimated_peak_bytes > memory_limit_bytes:
        raise ValueError(
            f"Calcul refusé : mémoire estimée {estimate.estimated_peak_bytes / 1024**3:.2f} Go, "
            f"limite {memory_limit_bytes / 1024**3:.2f} Go. Réduisez les trajectoires, "
            "la maturité ou le nombre de sous-jacents."
        )
    if estimate.work_units > work_limit:
        raise ValueError(
            f"Calcul refusé : coût estimé {estimate.work_units:,} unités, "
            f"limite {work_limit:,}. Réduisez les trajectoires, la maturité, "
            "le nombre de sous-jacents ou le nombre de repricings."
        )


def greek_repricing_equivalent(selected: list[str] | None, underlyings: int) -> float:
    """Number of full-N-equivalent runs used by compute_greeks.

    Greek legs use N/4 paths (with a floor of 1,000).  The caller multiplies
    this raw reprice count by that path ratio when estimating the whole request.
    """
    selected_set = set(selected or ())
    count = 0
    if selected_set & {"gamma", "theta", "corr"}:
        count += 1
    if selected_set & {"delta", "gamma"}:
        count += 2 * underlyings
    if "gamma" in selected_set:
        count += 2 * underlyings
    if "vega" in selected_set:
        count += 2 * underlyings
    if "rho" in selected_set:
        count += 2
    if "credit" in selected_set:
        count += 2
    if "corr" in selected_set and underlyings > 1:
        count += underlyings * (underlyings - 1) // 2
    if "theta" in selected_set:
        count += 1
    return float(count)


def estimate_pricing_request(
    *,
    maturity_years: float,
    underlyings: int,
    paths: int,
    model: str,
    antithetic: bool,
    continuous_monitoring: bool,
    stochastic_rates: bool,
    selected_greeks: list[str] | None = None,
    expanded_dates: int = 0,
) -> CalculationEstimate:
    """Estimate one synchronous pricing request, including requested Greeks.

    Greek repricings run sequentially at ``max(1_000, N/4)`` paths.  They add
    work, while peak memory remains the larger of one main or Greek run.
    """
    base = estimate_mc(
        operation="pricing",
        maturity_years=maturity_years,
        underlyings=underlyings,
        paths=paths,
        model=model,
        antithetic=antithetic,
        continuous_monitoring=continuous_monitoring,
        stochastic_rates=stochastic_rates,
        expanded_dates=expanded_dates,
    )
    greek_runs = greek_repricing_equivalent(selected_greeks, underlyings)
    if not greek_runs:
        return base

    greek_paths = max(1_000, paths // 4)
    greek = estimate_mc(
        operation="greeks",
        maturity_years=maturity_years,
        underlyings=underlyings,
        paths=greek_paths,
        model=model,
        antithetic=antithetic,
        continuous_monitoring=continuous_monitoring,
        stochastic_rates=stochastic_rates,
        repricings=greek_runs,
        expanded_dates=expanded_dates,
    )
    warnings = list(dict.fromkeys((*base.warnings, *greek.warnings)))
    total_work = base.work_units + greek.work_units
    if total_work > SYNC_WORK_LIMIT and "Calcul lourd : exécution synchrone déconseillée." not in warnings:
        warnings.append("Calcul lourd : exécution synchrone déconseillée.")
    return CalculationEstimate(
        operation="pricing_with_greeks",
        maturity_years=base.maturity_years,
        steps=base.steps,
        underlyings=base.underlyings,
        paths=base.paths,
        repricings=1.0 + greek_runs * greek_paths / paths,
        expanded_dates=expanded_dates,
        work_units=total_work,
        estimated_peak_bytes=max(base.estimated_peak_bytes, greek.estimated_peak_bytes),
        warnings=tuple(warnings),
    )


def estimate_mc_batch(
    *,
    operation: str,
    maturity_years: float,
    underlyings: int,
    paths_per_run: int,
    total_runs: float,
    model: str,
    antithetic: bool = True,
    continuous_monitoring: bool = False,
    stochastic_rates: bool = False,
    concurrent_runs: int = 1,
    expanded_dates: int = 0,
) -> CalculationEstimate:
    """Estimate a grid, solver or nested calculation made of MC repricings."""
    if concurrent_runs < 1:
        raise ValueError("Le nombre de calculs concurrents doit être positif.")
    estimate = estimate_mc(
        operation=operation,
        maturity_years=maturity_years,
        underlyings=underlyings,
        paths=paths_per_run,
        model=model,
        antithetic=antithetic,
        continuous_monitoring=continuous_monitoring,
        stochastic_rates=stochastic_rates,
        repricings=total_runs,
        expanded_dates=expanded_dates,
    )
    peak = estimate.estimated_peak_bytes * min(concurrent_runs, math.ceil(total_runs))
    warnings = list(estimate.warnings)
    if peak > SYNC_MEMORY_LIMIT_BYTES and "Calcul lourd : exécution synchrone déconseillée." not in warnings:
        warnings.append("Calcul lourd : exécution synchrone déconseillée.")
    return CalculationEstimate(
        operation=estimate.operation,
        maturity_years=estimate.maturity_years,
        steps=estimate.steps,
        underlyings=estimate.underlyings,
        paths=estimate.paths,
        repricings=estimate.repricings,
        expanded_dates=expanded_dates,
        work_units=estimate.work_units,
        estimated_peak_bytes=peak,
        warnings=tuple(warnings),
    )


def estimate_var_portfolio(bases: list[dict], scenario_count: int,
                           max_workers: int) -> dict:
    """Aggregate heterogeneous residual deal costs without averaging risk.

    One cell is one full reprice of one deal under one market scenario.  The
    work estimate is additive; peak memory is the sum of the largest active
    jobs because the worker runs them in separate processes.
    """
    if scenario_count < 1:
        raise ValueError("La VaR requiert au moins un scénario.")
    estimates = []
    for item in bases:
        base = item.get("base") or {}
        if base.get("settlement_claim"):
            continue
        ctx = base.get("valuation_context") or {}
        underlyings = len(ctx.get("underlyings") or base.get("engine_uls") or [])
        estimates.append(estimate_mc(
            operation="var_cell",
            maturity_years=float(ctx.get("T") or base.get("T_remaining") or 0.0),
            underlyings=underlyings,
            paths=int(ctx.get("N") or base.get("n_paths") or 0),
            model=str(ctx.get("model") or base.get("model_used") or "constant"),
            antithetic=bool(ctx.get("antithetic", base.get("antithetic", True))),
            continuous_monitoring=(ctx.get("barrier_monitoring") == "continuous"),
            stochastic_rates=bool(ctx.get("sigma_r") or base.get("sigma_r")),
        ))
    cells = len(bases) * scenario_count
    total_work = sum(e.work_units for e in estimates) * scenario_count
    largest = sorted((e.estimated_peak_bytes for e in estimates), reverse=True)
    peak = sum(largest[:max(1, min(max_workers, len(largest)))])
    hard_reasons = []
    if cells > BATCH_ABSOLUTE_CELLS:
        hard_reasons.append(
            f"{cells:,} valorisations dépassent le plafond de {BATCH_ABSOLUTE_CELLS:,}.")
    if total_work > BATCH_ABSOLUTE_WORK_LIMIT:
        hard_reasons.append(
            f"Le coût {total_work:,} dépasse le plafond de {BATCH_ABSOLUTE_WORK_LIMIT:,} unités.")
    if peak > WORKER_MEMORY_LIMIT_BYTES:
        hard_reasons.append(
            f"La mémoire concurrente estimée ({peak / 1024**3:.2f} Go) dépasse 2 Go.")
    confirmation_required = (
        not hard_reasons and total_work > BATCH_CONFIRM_WORK_LIMIT
    )
    return {
        "deals": len(bases), "scenarios": scenario_count, "cells": cells,
        "paths_per_scenario": max((e.paths for e in estimates), default=0),
        "work_units": total_work,
        "estimated_peak_bytes": peak,
        "estimated_peak_mb": round(peak / 1024**2, 1),
        "confirmation_required": confirmation_required,
        "hard_refusal": bool(hard_reasons),
        "hard_reasons": hard_reasons,
        "policy": {
            "confirmation_work_limit": BATCH_CONFIRM_WORK_LIMIT,
            "absolute_work_limit": BATCH_ABSOLUTE_WORK_LIMIT,
            "absolute_cells": BATCH_ABSOLUTE_CELLS,
            "worker_memory_limit_bytes": WORKER_MEMORY_LIMIT_BYTES,
        },
    }
