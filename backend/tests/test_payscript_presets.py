"""Example terms must bind to the production scripts and business calendars."""
import asyncio
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta

from backend.app.api.schedule import generate_schedule_endpoint, resolve_business_day
from backend.app.core.schemas import BusinessDayRequest, ScheduleRequest
from backend.app.core.payscript.catalogue import PRODUCTS, TENORS
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import eval_script_on_history
from backend.app.api import inlife
from backend.app.core.schemas import UnderlyingParams
from types import SimpleNamespace

PRESETS = json.loads((Path(__file__).resolve().parents[2] / 'frontend/src/data/payscriptPresets.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('preset', PRESETS, ids=lambda p: p['key'])
@pytest.mark.parametrize('count', [1, 2])
def test_forward_start_examples_price_without_historical_data(monkeypatch, preset, count):
    def unavailable(*args, **kwargs):
        pytest.fail('No historical fixing may be requested before StartDate')
    monkeypatch.setattr(inlife, 'load_hist_prices', unavailable)
    start, dates, payments, compiled, params = prepare(preset, '2026-10-14')
    constats = next(c.calendar_values for c in compiled.constats if c.calendar_values)
    req = inlife.InLifePricingRequest(
        script=PRODUCTS[preset['model_key']]['script'], constats=constats,
        user_params=params,
        underlyings=[UnderlyingParams(name=f'U{i}', ticker='' if i == 0 else 'AXA.PA',
                                      sigma=.3, q=.02) for i in range(count)],
        corr_matrix=[[1. if i == j else .4 for i in range(count)] for j in range(count)],
        r=.03, N=1000, model='constant', settlement_ccy='EUR',
        strike_date=start, value_date=start, valuation_date=date(2026, 10, 7),
        maturity_date=date.fromisoformat(dates[-1]), payment_date=date.fromisoformat(payments[-1]))
    result = inlife.price_in_life(req, SimpleNamespace(id=1, entity_id=1))
    assert result['pre_strike'] is True
    assert result['past']['strike_levels'] == {}
    assert result['past']['observations_done'] == 0
    assert result['price'] > 0


def prepare(preset, requested='2026-10-07', currency='EUR'):
    """Mirror the date requests made by the picker, using the actual API."""
    start = date.fromisoformat(resolve_business_day(BusinessDayRequest(
        date=requested, currency=currency, convention='following'))['date'])
    end = start + relativedelta(months=TENORS[preset['tenor']]['months'])
    model = PRODUCTS[preset['model_key']]
    values, dates, payments = {}, [], []
    for name, spec in model['constats'].items():
        if spec['role'] == 'initial_fixing':
            values[name] = {'date': start.isoformat()}
        elif spec['role'] == 'observations':
            frequency = preset.get('frequency', spec['frequency'])
            months = int(frequency[:-1]) * (12 if frequency[-1] == 'Y' else 1)
            value = dict(first_observation_date=(start + relativedelta(months=months)).isoformat(),
                         period_start_date=start.isoformat(), end_date=end.isoformat(),
                         roll_date=start.isoformat(), frequency=frequency, stub='short_last',
                         convention='following', settlement_lag=3, currency=currency)
            result = asyncio.run(generate_schedule_endpoint(ScheduleRequest(**value)))
            dates, payments = result['dates'], result['payment_dates']
            # The saved end is the effective final observation, as in the UI.
            value['end_date'] = dates[-1]
            roundtrip = asyncio.run(generate_schedule_endpoint(ScheduleRequest(**value)))
            assert roundtrip['dates'] == dates
            assert roundtrip['payment_dates'] == payments
            values[name] = value
        else:
            maturity = resolve_business_day(BusinessDayRequest(
                date=end.isoformat(), currency=currency, convention='following'))['date']
            dates = [maturity]
            payments = [resolve_business_day(BusinessDayRequest(
                date=maturity, currency=currency, business_days=3))['date']]
            values[name] = dict(date=maturity, convention='following', settlement_lag=3)
    compiled = resolve_constats(parse_script(model['script']), values, anchor=start, currency=currency)
    params = {p.name: [v / 100 for v in preset['params'][p.name]] if p.kind == 'array'
              else preset['params'][p.name] / 100 for p in compiled.params}
    return start, dates, payments, compiled, params


@pytest.mark.parametrize('preset', PRESETS, ids=lambda p: p['key'])
@pytest.mark.parametrize('requested', ['2026-10-07', '2026-01-31', '2028-02-29'])
@pytest.mark.parametrize('currency', ['EUR', 'CHF'])
def test_examples_match_scripts_and_survive_calendar_roundtrip(preset, requested, currency):
    model = PRODUCTS[preset['model_key']]
    compiled = parse_script(model['script'])
    assert preset['tenor'] in model['tenors']
    assert set(preset['params']) == {p.name for p in compiled.params}
    assert all(p.required and p.is_pct for p in compiled.params)
    start, dates, payments, _, _ = prepare(preset, requested, currency)
    assert start.isoformat() < dates[0]
    assert all(a < b for a, b in zip(dates, dates[1:]))
    assert all(observation < payment for observation, payment in zip(dates, payments))
    months = TENORS[preset['tenor']]['months']
    expected_count = months // (int(preset['frequency'][:-1]) * (12 if preset['frequency'][-1] == 'Y' else 1)) if 'frequency' in preset else 1
    assert len(dates) == expected_count
    for value in preset['params'].values():
        if isinstance(value, list):
            assert len(value) == len(dates)


def replay(key, levels):
    preset = deepcopy(next(p for p in PRESETS if p['key'] == key))
    start, dates, _, compiled, params = prepare(preset)
    end = date.fromisoformat(dates[-1])
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    prices = [100. if d == start.isoformat() else 100 * levels(d, dates) for d in days]
    return eval_script_on_history(compiled, days, {'A': prices}, 0,
        (end - start).days / 365.25, params, ['A'], 0., origine=start)


@pytest.mark.parametrize('level,total', [(1.05, 1.10), (.9, 1.), (.5, .5)])
def test_autocall_3y_separates_coupon_capital_and_put(level, total):
    result = replay('autocall_3y', lambda d, obs: level)
    flows = result['cash_flows']
    assert sum(f['cf'] for f in flows) == pytest.approx(total)
    assert sum(f['cf'] == 1. for f in flows) == 1
    if level < .6:
        assert any(f['cf'] == -.5 for f in flows)
    else:
        assert all(f['t'] > 0 for f in flows)


def test_phoenix_memory_coupon_is_per_quarter_and_catches_up():
    result = replay('phoenix_memory_3y', lambda d, obs: .5 if d <= obs[1] else 1.05)
    # Two missed coupons, then recall on the third quarter: 3 x 2% + capital.
    assert sum(f['cf'] for f in result['cash_flows']) == pytest.approx(1.06)


def test_stepdown_example_uses_the_third_barrier_and_three_coupons():
    result = replay('autocall_stepdown_5y', lambda d, obs: .92)
    assert sum(f['cf'] for f in result['cash_flows']) == pytest.approx(1.30)
