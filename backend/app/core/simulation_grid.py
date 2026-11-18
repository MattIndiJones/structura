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


# Models whose volatility depends on the level reached: their skew is frozen
# over each step, so a coarse grid biases the wings and the short smile.
SMILE_MODELS = frozenset({'sabr', 'localvol', 'lsv'})

SMILE_GRID_NOTICE = (
    "Grille de 52 pas par an avec un modèle à smile : la discrétisation biaise les options "
    "en dehors de la monnaie et le smile court. Mesures d'instance (validation du 18/11/2026) : "
    "smile SABR à 3 mois aplati de 0,1 à 0,2 point de vol ; call 120 % à 1 an en vol locale "
    "surévalué de 2 à 5 pb, ramené dans le bruit à 208 pas. Sur un produit court, une barrière "
    "proche ou une digitale, recouper à 104 ou 208 pas.")


def smile_grid_notice(model: str | None, steps_per_year=None) -> str | None:
    """Warning carried by a price computed with a smile model on the 52-step
    grid. The default stays at 52 for speed; the price says what it costs."""
    if model not in SMILE_MODELS or grid_frequency(steps_per_year) != 52:
        return None
    return SMILE_GRID_NOTICE


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
