"""Business acceptance of the generic catalogue against independent cash amounts."""
from datetime import date, timedelta
from copy import deepcopy

import pytest

from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import eval_script_on_history, run_mc

START = date(2024, 1, 2)
END = date(2027, 1, 2)
DAYS = [(START + timedelta(days=n)).isoformat() for n in range((END - START).days + 1)]
PARAMETERS = {'COUPON': .08, 'M_AC_BAR': 1., 'M_KI_BAR': .6, 'M_CPN_BAR': .8,
              'M_PDI_BAR': .6, 'M_PUT_STRIKE': .8, 'GEARING': 1.5, 'CAP': 1.3,
              'PART': 1.5, 'STRIKE': 1., 'K1': 1., 'K2': 1.2, 'M_KO_BAR': 1.3,
              'REBATE': .03}


def contract(key, start=START, end=END):
    compiled = parse_script(PRODUCTS[key]['script'])
    values = {}
    for declaration in compiled.constats:
        if declaration.role == 'initial_fixing':
            value = start.isoformat()
        elif declaration.kind == 'single':
            value = end.isoformat()
        else:
            value = {'first_observation_date': start.replace(year=start.year + 1).isoformat(),
                     'end_date': end.isoformat(), 'frequency': '1Y'}
        if declaration.reduction:
            value = {'date': value} if isinstance(value, str) else value
            value['window_frequency'] = '1D'
            if declaration.window_scope != 'period':
                value['window_length'] = '3D'
        values[declaration.name] = value
    return resolve_constats(compiled, values, anchor=start, currency='EUR')


def params(key):
    result = {p.name: PARAMETERS[p.name] for p in parse_script(PRODUCTS[key]['script']).params}
    if key == 'autocall_barriere_degressive':
        result['M_AC_BAR'] = [1., .9, .8]
    return result


def replay(key, levels, extra_params=None):
    compiled = contract(key)
    return eval_script_on_history(compiled, DAYS, {'A': levels}, 0,
        (END - START).days / 365.25, {**params(key), **(extra_params or {})}, ['A'], 0., origine=START)


def expected_redemption(key, level):
    """Independent investor-side totals for the selected contractual scenarios."""
    if key.startswith('autocall'):
        barriers = [1., .9, .8] if key == 'autocall_barriere_degressive' else [1.] * 3
        rank = next((i for i, barrier in enumerate(barriers, 1) if level >= barrier), None)
        if rank:
            return 1.08 if key == 'autocall_gear_put' else 1 + .08 * rank
        if key == 'autocall_gear_put':
            return max(0., 1 - 1.5 * max(0., 1 - level / .8))
        return level if level < .6 else 1.
    if key in {'phoenix', 'phoenix_memoire'}:
        if level >= 1.:
            return 1.08
        return (level if level < .6 else 1.) + (.24 if level >= .8 else 0.)
    if key in {'reverse_convertible', 'brc_ki_americaine'}:
        return .08 + (level if level < .6 else 1.)
    if key == 'capital_garanti':
        return 1 + 1.5 * max(level - 1, 0)
    if key == 'twin_win':
        return level if level < .6 else min(1.3, 1 + abs(level - 1))
    if key == 'booster':
        return level if level < 1 else min(1.3, 1 + 1.5 * (level - 1))
    if key == 'shark_note':
        return 1.03 if level >= 1.3 else 1 + 1.5 * max(level - 1, 0)
    if key in {'call', 'call_panier_moyenne', 'call_lookback'}:
        return max(level - 1, 0)
    if key == 'put':
        return max(1 - level, 0)
    if key == 'call_spread':
        return min(max(level - 1, 0), .2)
    if key == 'digitale':
        return .08 if level >= 1 else 0.
    raise AssertionError(f'Missing independent oracle: {key}')


@pytest.mark.parametrize('key', list(PRODUCTS))
@pytest.mark.parametrize('level', [.4, .6, .9, 1., 1.15, 1.4])
def test_all_nineteen_payoffs_against_independent_redemption(key, level):
    # The initial fixing window is flat. Every later fixing has the same level.
    result = replay(key, [100. if i < 6 else 100 * level for i in range(len(DAYS))])
    assert sum(flow['cf'] for flow in result['cash_flows']) == pytest.approx(expected_redemption(key, level))
    assert all(flow['t'] > 0 for flow in result['cash_flows'])


@pytest.mark.parametrize('key,total', [('phoenix', 1.16), ('phoenix_memoire', 1.24)])
def test_coupon_memory_catches_up_exactly_once(key, total):
    levels = [100. if day == str(START) else 70. if day <= '2025-01-02' else 90. for day in DAYS]
    result = replay(key, levels)
    assert sum(flow['cf'] for flow in result['cash_flows']) == pytest.approx(total)


@pytest.mark.parametrize('key,total', [('autocall_athena', 1.24), ('phoenix', 1.24), ('phoenix_memoire', 1.24)])
def test_final_date_recall_does_not_also_pay_terminal_capital(key, total):
    result = replay(key, [100. if day in {str(START), str(END)} else 90. for day in DAYS])
    assert sum(flow['cf'] for flow in result['cash_flows']) == pytest.approx(total)
    assert sum(flow['cf'] == 1. for flow in result['cash_flows']) == 1


@pytest.mark.parametrize('european,american,coupon', [
    ('autocall_athena', 'autocall_athena_ki_americaine', 0.),
    ('reverse_convertible', 'brc_ki_americaine', .08),
])
def test_inter_observation_breach_distinguishes_european_and_american(european, american, coupon):
    levels = [100. if day == str(START) else 40. if day == '2024-06-03' else 90. for day in DAYS]
    assert sum(flow['cf'] for flow in replay(european, levels)['cash_flows']) == pytest.approx(1 + coupon)
    assert sum(flow['cf'] for flow in replay(american, levels)['cash_flows']) == pytest.approx(.9 + coupon)


@pytest.mark.parametrize('antithetic', [False, True])
@pytest.mark.parametrize('level', [.4, .6, 1.])
def test_mc_cash_legs_reconcile_to_price_and_independent_redemption(antithetic, level):
    compiled = contract('autocall_athena')
    result = run_mc(compiled, [{'name':'A', 'sigma':0., 'q':0., 'spot0':100.}], [[1.]],
                    0., (END - START).days / 365.25, 8, antithetic=antithetic,
                    user_params=params('autocall_athena'), spot_mult=[level])
    assert result['price'] == pytest.approx(expected_redemption('autocall_athena', level))
    flows = list(result['flux_table'].values())
    assert len(flows) == 2
    assert sum(flow['sum'] for flow in flows) / result['n_paths'] == pytest.approx(result['price'])


def test_explicit_basket_contract_reaches_actual_ccr_engine():
    from backend.tests.test_ccr import proposed, inputs, legal_config, DAY
    from backend.app.core.ccr.service import evaluate_inputs
    long = proposed()
    long['pricing'].update(script=PRODUCTS['call']['script'], user_params={'STRIKE':1.},
        constats={'STARTDATE': str(DAY), 'MATURITYDATE': str(DAY.replace(year=DAY.year + 1))})
    long.update(key='1', deal_id=1, reference='existing')
    short = deepcopy(long)
    short.update(key='proposed', deal_id=None, reference='proposed', sens='achat')
    result = evaluate_inputs(inputs([long, short], legal_config()))
    assert result['errors'] == []
    assert result['before']['current_exposure'] > 50_000
    assert result['after']['pfe95'] == pytest.approx(0., abs=.001)


def test_solver_and_grid_inject_their_candidates_into_required_parameters():
    from backend.app.api.simulation import solve_endpoint, grid_endpoint
    from backend.app.core.schemas import SolverRequest, GridRequest
    common = dict(script=PRODUCTS['reverse_convertible']['script'],
        underlyings=[{'name':'A', 'ticker':'TEST', 'ccy':'EUR', 'sigma':0., 'q':0.}],
        corr_matrix=[[1.]], r=0., T=1., N=1000, strike_date='2026-10-06',
        settlement_ccy='EUR', constats={'STARTDATE':'2026-10-06', 'MATURITYDATE':'2027-10-06'})
    solved = solve_endpoint(SolverRequest(**common, user_params={'M_KI_BAR':.6},
        param_name='COUPON', lo=0., hi=.2, target_price=1.08))
    assert solved['converged']
    assert solved['param_value'] == pytest.approx(.08, abs=.001)
    grid = grid_endpoint(GridRequest(**common, user_params={},
        param_x='COUPON', x_min=.04, x_max=.08, x_steps=2,
        param_y='M_KI_BAR', y_min=.5, y_max=.6, y_steps=2))
    for row in grid['prices']:
        assert row == pytest.approx([1.04, 1.08])


def test_terminal_window_does_not_read_a_fixing_after_its_observation():
    compiled = contract('call_panier_moyenne')
    event = compiled.events[0]
    assert max(event.window_dates[0]) == event.dates[0]
    assert len(event.window_dates[0]) == 3


def test_terminal_average_includes_its_contractual_last_fixing():
    levels = [100. for _ in DAYS]
    for day, value in [('2026-12-30', 90.), ('2026-12-31', 120.), ('2027-01-02', 150.)]:
        levels[DAYS.index(day)] = value
    result = replay('call_panier_moyenne', levels)
    # (90 + 120 + 150) / 3 / 100 - 1 = 20%; no later fixing can enter.
    assert sum(flow['cf'] for flow in result['cash_flows']) == pytest.approx(.2)


@pytest.mark.parametrize('forward', [False, True])
def test_one_day_window_on_closed_day_keeps_one_fixing(forward):
    from backend.app.core.schedule import observation_window, Tenor
    saturday = date(2027, 1, 2)
    assert observation_window(saturday, Tenor(1, 'D'), Tenor(1, 'D'),
        forward=forward, currency='EUR', convention='none') == [saturday]
