"""Representative model paths reconstructed from a signed exotic valuation."""
from math import ceil, isfinite
from typing import Literal

import numpy as np

from ..core.product.exotic_credit_mc import _HazardSegments, _draw_default_times
from ..core.product.exotic_rates_mc import _event_times, simulate_hull_white
from ..core.product.models import FrozenModel
from .exotic_valuation import ExoticCreditScenario, ExoticRatesScenario, ExoticScenario, ExoticValuationError


PREVIEW_PATHS = 48


class PreviewPoint(FrozenModel):
    time: float
    value: float


class PreviewPath(FrozenModel):
    path: int
    triggered: bool | None = None
    points: tuple[PreviewPoint, ...]


class ExoticPaths(FrozenModel):
    family: Literal["rates", "credit"]
    measure: Literal["hw_factor_bp", "credit_default_count"]
    seed: int
    horizon_years: float
    path_count: int
    result_fingerprint: str
    paths: tuple[PreviewPath, ...]


def _rates_preview(scenario: ExoticRatesScenario, seed: int) -> tuple[float, tuple[PreviewPath, ...]]:
    events = _event_times(scenario.terms)
    horizon = events[-1]
    if horizon == 0:
        raise ExoticValuationError("EXOTIC_PATHS_TERMINAL", "Ce calcul ne contient aucun événement futur.")
    steps = min(120, max(2, ceil(12 * horizon)))
    times = tuple(sorted({*events, *np.linspace(0.0, horizon, steps + 1)}))
    if len(times) > 400:
        raise ExoticValuationError("EXOTIC_PATHS_GRID_LIMIT", "La grille de ce contrat dépasse le plafond du tracé.")
    drawn = simulate_hull_white(
        scenario.market, times, paths=PREVIEW_PATHS, seed=seed, antithetic=scenario.settings.antithetic,
    )
    return horizon, tuple(
        PreviewPath(path=index + 1, points=tuple(
            PreviewPoint(time=time, value=float(state) * 10_000)
            for time, state in zip(drawn.times, drawn.state[:, index], strict=True)
        )) for index in range(PREVIEW_PATHS)
    )


def _credit_preview(scenario: ExoticCreditScenario, seed: int) -> tuple[float, tuple[PreviewPath, ...]]:
    request = scenario.credit
    if request.realized is not None:
        raise ExoticValuationError("EXOTIC_PATHS_REALIZED", "Le défaut constaté utilise les faits archivés.")
    maturity = request.contract.maturity_years
    rank = request.contract.trigger_rank or 1
    members = sorted(request.market.marginals, key=lambda member: member.reference_entity_id)
    segments = tuple(_HazardSegments.from_curve(member.curve, maturity) for member in members)
    sampled = _draw_default_times(np.random.Generator(np.random.PCG64(seed)), PREVIEW_PATHS, segments,
                                  np.asarray([member.loading for member in members]), False, 0.0)
    rows = []
    for index, dates in enumerate(sampled, start=1):
        observed = sorted(float(time) for time in dates if isfinite(time) and time <= maturity)
        points = [PreviewPoint(time=0.0, value=0)]
        for count, time in enumerate(observed):
            points.append(PreviewPoint(time=time, value=count))
            points.append(PreviewPoint(time=time, value=count + 1))
        points.append(PreviewPoint(time=maturity, value=len(observed)))
        rows.append(PreviewPath(path=index, triggered=len(observed) >= rank, points=tuple(points)))
    return maturity, tuple(rows)


def preview_exotic_paths(scenario: ExoticScenario, result_fingerprint: str) -> ExoticPaths:
    if isinstance(scenario, ExoticRatesScenario):
        seed = _preview_seed(scenario.settings.seed)
        horizon, paths = _rates_preview(scenario, seed)
        measure = "hw_factor_bp"
    else:
        seed = _preview_seed(scenario.credit.settings.seed)
        horizon, paths = _credit_preview(scenario, seed)
        measure = "credit_default_count"
    return ExoticPaths(family=scenario.family, measure=measure, seed=seed, horizon_years=horizon,
                       path_count=PREVIEW_PATHS, result_fingerprint=result_fingerprint, paths=paths)


def _preview_seed(archived_seed: int) -> int:
    return int(np.random.SeedSequence(archived_seed, spawn_key=(4,)).generate_state(1)[0])
