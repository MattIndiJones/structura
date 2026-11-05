"""Per-calculation diffusion frequency, including legacy snapshot semantics.

The context is local to a thread/task and always reset. It lets internal Greeks
and residual helpers inherit the explicit serialized calculation setting without
ever modifying the historical module constant or another concurrent request.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
from typing import Literal

GridFrequency = Literal[52, 104, 208]
_frequency = ContextVar('structura_steps_per_year', default=52)


def grid_frequency(value=None) -> int:
    if value is None:
        return _frequency.get()
    if isinstance(value, bool) or value not in (52, 104, 208):
        raise ValueError('La grille de diffusion doit être de 52, 104 ou 208 pas par an.')
    return int(value)


@contextmanager
def simulation_grid(value):
    token = _frequency.set(grid_frequency(value))
    try:
        yield _frequency.get()
    finally:
        _frequency.reset(token)


def with_simulation_grid(function):
    @wraps(function)
    def scoped(*args, **kwargs):
        frequency = kwargs.pop('steps_per_year', None)
        with simulation_grid(frequency):
            return function(*args, **kwargs)
    return scoped


def with_request_grid(function):
    """Bind numerical helpers to validated request settings, including budgets."""
    signature = inspect.signature(function, eval_str=True)
    @wraps(function)
    def scoped(*args, **kwargs):
        request = signature.bind_partial(*args, **kwargs).arguments.get('req')
        with simulation_grid(getattr(request, 'steps_per_year', None)):
            return function(*args, **kwargs)
    scoped.__signature__ = signature
    return scoped


def snapshot_grid(market: dict) -> int:
    raw = (market.get('pricing_input') or {}).get('steps_per_year')
    if raw is None:
        raw = market.get('steps_per_year', market.get('stepsPerYear', 52))
    return grid_frequency(raw)


def grid_warning(booked: int, effective: int) -> str | None:
    if booked == effective:
        return None
    return (f'Deal booké à {booked} pas/an. '
            f'Cette valorisation utilise {effective} pas/an.')
