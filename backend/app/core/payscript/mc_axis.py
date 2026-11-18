"""Time axis shared by every Monte Carlo entry point: grid constant, contract
event schedule on the simulation steps.

Split out of engine.py on 18/11/2026; engine.py re-exports every name.
"""
from __future__ import annotations

from dataclasses import replace
from ..simulation_grid import grid_frequency
from .parser import validate_observation_dates
from .time_grid import contract_axis, step_at as _step_at, time_at as _time_at


SY = 52       # weekly steps per year


TIME_AXIS_POLICY = "EXACT-CONTRACT-DATES-2026-10-24"


class _ContractEventSchedule(dict):
    """Occurrence map whose dates are contractual, not a synthetic test clock."""


def _simulation_axis(horizon: float, script=None, extra_dates=(), *, steps_per_year=None):
    return contract_axis(horizon, script, extra_dates, frequency=grid_frequency(steps_per_year))


def _event_schedule(events, steps, dt, *, horizon=None, maturity_payment_t=None, date_tolerance=1e-6):
    """Order occurrences by contract time, then source order for simultaneity.

    One occurrence per copy keeps ranks, windows and payments aligned even
    when several dates of the same block map to one diffusion step. The
    compiled/frozen contract is never mutated. Dated blocks precede MATURITY.
    """
    occurrences, maturity = [], []
    fields = ("payment_dates", "window_dates", "ranks", "releves_passes")
    for source_order, event in enumerate(events):
        if event.type == "AT_MATURITY":
            maturity.append(event)
            continue
        validate_observation_dates((event,))
        for i, when in enumerate(event.dates):
            step = max(1, _step_at(dt, when))
            # Resolved/residual calendars store year-fractions to six decimals.
            # Admit that representation tolerance, never an extra market day.
            if step > steps or (horizon is not None and when > horizon + date_tolerance):
                continue
            if horizon is not None:
                when = min(when, horizon)
            attributes = {field: [value[i]] if value is not None and i < len(value) else None
                          for field in fields if (value := getattr(event, field)) is not None}
            occurrence = replace(event, dates=[when], **attributes)
            payment = occurrence.payment_dates[0] if occurrence.payment_dates else when
            if maturity_payment_t is not None and abs(when - horizon) <= 1e-6:
                payment = maturity_payment_t
            occurrences.append((when, source_order, i, step, occurrence, payment))
    schedule, payments = _ContractEventSchedule(), {}
    for when, source_order, i, step, occurrence, payment in sorted(occurrences, key=lambda row: row[:3]):
        schedule.setdefault(step, []).append(occurrence)
        payments.setdefault(step, []).append(payment)
    return schedule, maturity, payments


def _event_times(step_map, dt):
    # Direct evaluator clients (notably the independent C09 payoff panel)
    # deliberately construct a synthetic clock from step numbers. Preserve
    # that contract. Normal pricing consumers supply the occurrence schedule.
    if not isinstance(step_map, _ContractEventSchedule):
        return {step: [_time_at(dt, step)] * len(events) for step, events in step_map.items()}
    return {step: [next((d for d in event.dates if max(1, _step_at(dt, d)) == step), _time_at(dt, step))
                   for event in events] for step, events in step_map.items()}
