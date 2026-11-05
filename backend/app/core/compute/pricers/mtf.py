"""Prepared MTF jobs carry resolved terms and market state across process boundaries."""
from dataclasses import fields, replace
import math

from ...payscript.engine import run_mark_to_future
from ...payscript.parser import CompiledEvent, parse_script
from ...valuation_context import run_valuation, valuation_context_from_dict


def freeze_mtf_script(compiled, source):
    # A resolved occurrence retains its original block function, even when
    # lifecycle replay removes earlier blocks or shifts their dates.
    blocks = {event.fn.__code__: i for i, event in enumerate(parse_script(source).events)}
    events = []
    for event in compiled.events:
        index = blocks.get(event.fn.__code__)
        if index is None:
            raise ValueError("Un bloc du payoff résiduel ne correspond pas au script du MTF.")
        values = {field.name: getattr(event, field.name) for field in fields(event) if field.name != 'fn'}
        events.append({'block': index, 'values': values})
    return dict(events=events, strike_fix_dates=compiled.strike_fix_dates,
                strike_fix_reduction=compiled.strike_fix_reduction,
                releves_realises=compiled.releves_realises)


def price_mtf_job(payload):
    ctx = valuation_context_from_dict(payload['context'])
    script = parse_script(ctx.script_text)
    frozen = payload['script']
    events = [CompiledEvent(fn=script.events[row['block']].fn, **row['values']) for row in frozen['events']]
    script = replace(script, **{**frozen, 'events': events})
    settings = payload['settings']
    flows, terminated = settings['initial_flows'], settings['initial_terminated']
    # The reference sample is independent of the outer sample. Both models
    # in a comparison still share the reference seed and spot shocks.
    reference_seed = ctx.seed + 7919
    leverage = None
    if ctx.model == 'lsv' and not terminated:
        from ...payscript.lsv_leverage import prepare_mtf_leverage
        leverage = prepare_mtf_leverage(script, ctx, settings['mtm_dates'], qualify=True)
    unpaid = sum(flow['amount'] * math.exp(-ctx.r * flow['payment_t'])
                 for flow in flows if flow['payment_t'] > 1e-9)
    reference = {}
    if terminated:
        price, ci = unpaid, [unpaid, unpaid]
    else:
        reference = run_valuation(script, replace(ctx, seed=reference_seed),
                                  additional_grid_dates=settings['mtm_dates'], lsv_leverage=leverage)
        price = reference['price'] + unpaid
        ci = [value + unpaid for value in reference['ic95']]
    fan = run_mark_to_future(
        script, ctx.underlyings, ctx.corr_matrix, ctx.r, ctx.T, round(100 * price, 4),
        model=ctx.model, seed=ctx.seed, state=ctx.state, user_params=ctx.user_params,
        barrier_monitoring=ctx.barrier_monitoring, maturity_payment_t=ctx.maturity_payment_t,
        aligned_grid=True, local_vol_anchor=ctx.local_vol_anchor, gbm_atm_curve=ctx.gbm_atm_curve, lsv_leverage=leverage, **settings,
    steps_per_year=ctx.steps_per_year)
    fan.update(model=ctx.model, reference_ci95=[100 * value for value in ci],
               reference_paths=ctx.N, reference_seed=reference_seed)
    if reference.get('surface_context') is not None:
        fan['surface_context'] = reference['surface_context']
    if reference.get('lsv_calibration') is not None:
        fan['lsv_calibration'] = reference['lsv_calibration']
    if leverage is not None:
        from ...payscript.lsv_leverage import leverage_digest
        fan['lsv_leverage_digest'] = leverage_digest(leverage)
    return fan
