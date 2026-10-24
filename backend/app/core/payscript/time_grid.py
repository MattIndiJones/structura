"""Explicit nonuniform simulation intervals shared by diffusion and contracts."""
import numpy as np


def durations(dt, steps):
    values = np.asarray(dt, dtype=float)
    if values.ndim == 0:
        values = np.full(steps, float(values))
    if values.shape != (steps,) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Intervalles de simulation invalides.")
    return values


def times(dt, steps):
    if np.ndim(dt) == 0:
        return np.arange(steps + 1, dtype=float) * dt
    return np.r_[0., np.cumsum(durations(dt, steps))]


def time_at(dt, step):
    return float(step * dt) if np.ndim(dt) == 0 else float(np.sum(dt[:step]))


def step_at(dt, when, steps=None):
    """Locate a contractual date; scalar grids retain the legacy helper contract."""
    if np.ndim(dt) == 0:
        return round(when / dt)
    axis = times(dt, len(dt))
    index = int(np.searchsorted(axis, when))
    if index == len(axis):
        return index - 1
    if index and abs(axis[index - 1] - when) < abs(axis[index] - when):
        index -= 1
    return index


def contract_axis(horizon, script=None, extra_dates=(), frequency=52):
    if not np.isfinite(horizon) or horizon <= 0:
        raise ValueError("Horizon de simulation strictement positif requis.")
    steps = max(1, round(horizon * frequency))
    dt = horizon / steps
    dates = list(extra_dates)
    if script is not None:
        dates.extend(script.strike_fix_dates or [])
        for event in script.events:
            dates.extend(event.dates or [])
            for window in event.window_dates or []:
                dates.extend(window)
    axis = list(np.arange(steps + 1) * dt)
    # Replace numerically identical nodes, preserving the contractual value.
    for value in sorted(set(float(d) for d in dates if d is not None and 0 < d < horizon)):
        index = int(np.searchsorted(axis, value))
        near = min(range(max(0, index - 1), min(len(axis), index + 1)), key=lambda i: abs(axis[i] - value))
        if abs(axis[near] - value) <= 1e-12:
            axis[near] = value
        else:
            axis.insert(index, value)
    if len(axis) == steps + 1 and np.array_equal(axis, np.arange(steps + 1) * dt):
        return steps, dt
    return len(axis) - 1, np.diff(axis)


def metadata(policy, horizon, steps, dt):
    return {"policy": policy, "horizon": horizon, "steps": steps,
            "dt": horizon / steps, "grid_times": times(dt, steps).tolist(),
            "event_order": "CONTRACT_TIME_THEN_SOURCE_ORDER"}
