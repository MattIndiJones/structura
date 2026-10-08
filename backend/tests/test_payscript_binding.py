"""Contract tests for Economics-bound baskets and explicit initial fixings."""
from datetime import date
import pytest

from backend.app.core.payscript.bindings import effective_parameters
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import run_mc, eval_script_on_history


ATHENA = '''UNDERLYING Basket
PARAM COUPON
PARAM M_AC_BAR
PARAM M_KI_BAR
CONSTAT StartDate
CONSTAT() ObservationDates
AT StartDate:
    Basket.spot0 = Basket.spot@StartDate
AT Date FROM ObservationDates:
    SET PERF = WORSTOF(Basket.yield)
    IF PERF >= M_AC_BAR:
        PAY COUPON * INDEX "Coupons cumulés"
        PAY 1 "Capital au rappel"
        STOP
AT ObservationDates.last:
    SET PERF = WORSTOF(Basket.yield)
    SET KI = INDIC(PERF < M_KI_BAR)
    PAY 1 "Capital à maturité"
    PAY -KI * MAX(1 - PERF, 0) "Put vendu"
'''


def contract(script=ATHENA, first='2027-10-06', last='2029-10-06'):
    return resolve_constats(parse_script(script), {
        'StartDate': '2026-10-06', 'ObservationDates': {
            'first_observation_date': first, 'end_date': last,
            'frequency': '1Y', 'convention': 'none',
        }}, anchor=date(2026, 10, 6), currency='EUR')


def test_fixing_is_separate_from_coupon_rank_and_first_observation_is_included():
    script = contract()
    assert script.underlying_name == 'BASKET'
    assert script.initial_fixing_name == 'STARTDATE'
    assert len(script.events) == 2
    assert script.events[0].ranks == [1, 2, 3]
    assert script.events[1].ranks == [3]
    assert script.events[0].dates[0] == pytest.approx(365 / 365.25, abs=1e-6)
    assert all(p.required and p.is_pct and p.stored_val is None for p in script.params)


def test_missing_parameter_fails_in_engine_instead_of_defaulting_to_zero():
    script = contract()
    with pytest.raises(ValueError, match='COUPON'):
        run_mc(script, [{'name': 'A', 'sigma': 0., 'q': 0.}], [[1]], 0., 3., 4,
               user_params={'M_AC_BAR': 1., 'M_KI_BAR': .6})


@pytest.mark.parametrize('barrier, expected', [(1., 1.08), (1.1, 1.)])
def test_mc_recall_or_maturity_has_distinct_cash_legs(barrier, expected):
    script = contract(first='2027-10-06', last='2027-10-06')
    result = run_mc(script, [{'name': 'A', 'sigma': 0., 'q': 0.}], [[1]], 0.,
                    script.events[0].dates[0], 4, antithetic=False,
                    user_params={'COUPON': .08, 'M_AC_BAR': barrier, 'M_KI_BAR': .6},
                    per_path_flows=True)
    assert result['price'] == pytest.approx(expected)
    labels = {r['lbl'] for r in result['flux_table'].values()}
    assert labels == ({'Coupons cumulés', 'Capital au rappel'} if barrier == 1.
                      else {'Capital à maturité', 'Put vendu'})
    if barrier > 1:
        put = next(r for r in result['flux_table'].values() if r['lbl'] == 'Put vendu')
        assert put['sum'] == 0 and put['n'] == 0


def test_explicit_raw_default_and_required_array_are_distinct():
    script = parse_script('PARAM GEARING = 1.5\nPARAM() COUPON\nAT 1:\n  PAY GEARING * COUPON')
    assert effective_parameters(script.params, {'COUPON': [.08]}) == {'GEARING': 1.5, 'COUPON': [.08]}
    with pytest.raises(ValueError, match='série vide'):
        effective_parameters(script.params, {'COUPON': []})


def test_history_uses_individual_initial_levels():
    script = contract(first='2027-10-06', last='2027-10-06')
    result = eval_script_on_history(script, ['2026-10-06', '2027-10-06'],
                                    {'A': [100., 110.], 'B': [200., 80.]}, 0,
                                    script.events[0].dates[0],
                                    {'COUPON': .08, 'M_AC_BAR': 1., 'M_KI_BAR': .6},
                                    ['A', 'B'], 0.)
    assert sum(f['cf'] for f in result['cash_flows']) == pytest.approx(.4)


@pytest.mark.parametrize('replacement', ['Basket.spot@Tomorrow', 'Basket.secret', 'Basket.yield.__class__'])
def test_unsupported_property_or_future_reference_fails(replacement):
    with pytest.raises(ValueError):
        parse_script(ATHENA.replace('WORSTOF(Basket.yield)', f'WORSTOF({replacement})'))


def test_generic_draft_does_not_invent_economics():
    from backend.app.core.product.inputs import terms_from_input
    draft = terms_from_input({'script': ATHENA}, allow_unresolved=True)
    assert draft.T is None and draft.underlyings == ()
    assert all(p.value is None for p in draft.parameters)
    with pytest.raises(ValueError, match='incomplet'):
        draft.require_complete()


def test_frozen_calendar_binds_the_payoff_version_and_preserves_initial_fixing():
    from backend.app.core.product.calendar import freeze_calendar, restore_calendar
    original = contract()
    frozen = freeze_calendar(original)
    restored = restore_calendar(parse_script(ATHENA), frozen)
    assert frozen['version'] == 2
    assert restored.origine == date(2026, 10, 6)
    assert restored.events[0].ranks == [1, 2, 3]
    with pytest.raises(ValueError, match='version'):
        restore_calendar(parse_script(ATHENA.replace('PAY 1 ', 'PAY 2 ')), frozen)


@pytest.mark.parametrize('expr, expected', [
    ('WORSTOF(Basket.yield)', .4), ('BESTOF(Basket.yield)', 1.1),
    ('AVG(Basket.yield)', .75), ('AVG(Basket.spot)', 95.),
    ('AVG(Basket.spot0)', 150.), ('AVG(Basket.spot / Basket.spot0)', .75),
])
def test_basket_observables_use_contractual_order_and_units(expr, expected):
    source = ATHENA[:ATHENA.index('AT Date FROM')] + f'AT ObservationDates.last:\n  PAY {expr} "Cash"\n'
    compiled = contract(source, last='2027-10-06')
    replay = eval_script_on_history(compiled, ['2026-10-06', '2027-10-06'],
        {'A': [100., 110.], 'B': [200., 80.]}, 0, 1.,
        {'COUPON': 0., 'M_AC_BAR': 1., 'M_KI_BAR': .6}, ['A', 'B'], 0.)
    assert sum(f['cf'] for f in replay['cash_flows']) == pytest.approx(expected)


def test_raw_levels_are_carried_from_initial_window_into_mc():
    source = ATHENA[:ATHENA.index('AT Date FROM')].replace('CONSTAT StartDate', 'CONSTAT StartDate AVG')
    source += 'AT ObservationDates.last:\n  PAY AVG(Basket.spot0) "Fixing"\n'
    compiled = resolve_constats(parse_script(source), {
        'STARTDATE': {'date': '2026-10-06', 'window_length': '3D', 'window_frequency': '1D'},
        'OBSERVATIONDATES': {'first_observation_date': '2026-11-06', 'end_date': '2026-11-06', 'frequency': '1M'},
    }, anchor=date(2026, 10, 6), currency='EUR')
    result = run_mc(compiled, [{'name':'A','sigma':0.,'q':0.,'spot0':100.},
        {'name':'B','sigma':0.,'q':0.,'spot0':200.}], [[1.,0.],[0.,1.]], 0., 31/365.25, 4,
        user_params={'COUPON':0.,'M_AC_BAR':1.,'M_KI_BAR':.6})
    assert result['price'] == pytest.approx(150.)


def test_initial_date_conflicts_and_observation_at_strike_are_rejected():
    from types import SimpleNamespace
    from backend.app.core.payscript.parser import analysis_origin
    with pytest.raises(ValueError, match='même fixing'):
        analysis_origin(SimpleNamespace(script=ATHENA, constats={'STARTDATE':'2026-10-06'}, strike_date='2026-10-07'))
    with pytest.raises(ValueError, match='suivre'):
        contract(first='2026-10-06')


def test_pricing_api_returns_actionable_error_for_missing_economics():
    from fastapi import HTTPException
    from backend.app.api.pricing import price_endpoint
    from backend.app.core.schemas import PricingRequest
    body = dict(script=ATHENA, underlyings=[{'name':'A','ccy':'EUR','sigma':.2,'q':0.}],
        corr_matrix=[[1.]], N=1000, strike_date='2026-10-06', settlement_ccy='EUR',
        constats={'STARTDATE':'2026-10-06','OBSERVATIONDATES':{
            'first_observation_date':'2027-10-06','end_date':'2027-10-06','frequency':'1Y'}})
    with pytest.raises(HTTPException) as error:
        price_endpoint(PricingRequest(**body))
    assert error.value.status_code == 422
    assert 'COUPON' in error.value.detail


def test_conditional_alias_does_not_misclassify_the_observable():
    source = ATHENA.replace('    SET PERF = WORSTOF(Basket.yield)',
        '    IF INDEX > 1:\n        SET PERF = WORSTOF(Basket.yield)')
    compiled = parse_script(source)
    assert all(m['observable'] is None for m in compiled.monitors)


def test_explicit_fixing_and_put_survive_residual_pricing(monkeypatch):
    from backend.tests.test_inlife_pricing import _historique, STRIKE, _requete, USER
    from backend.app.api import inlife as api
    monkeypatch.setattr(api, 'load_hist_prices', lambda tickers, start, end:
        _historique(date(2024, 6, 7), date.fromisoformat(end), 40.))
    req = _requete(script=ATHENA, r=0., N=1000, valuation_date=date(2026, 6, 16),
        constats={'STARTDATE':'2024-06-14','OBSERVATIONDATES':{
            'first_observation_date':'2025-06-14','end_date':'2027-06-14','frequency':'1Y'}},
        user_params={'COUPON':.08,'M_AC_BAR':1.,'M_KI_BAR':.6},
        underlyings=[{'name':'U1','ticker':'UL.PA','ccy':'EUR','sigma':0.,'q':0.}])
    result = api.price_in_life(req, USER)
    assert result['price'] == pytest.approx(.4)
    assert result['past']['observations_done'] == 2
    assert result['past']['strike_levels']['U1'] == 100.
    assert '__REFERENCE_SPOTS' not in result['past']['memory']


@pytest.mark.parametrize('with_interim', [False, True])
def test_reinvestment_moves_initial_and_observation_dates_together(with_interim):
    import json
    from types import SimpleNamespace
    from backend.app.api.deals import _reinvest_context
    source = contract()
    market = {'constats':source.constats[0].calendar_values,
              'user_params':{'COUPON':.08,'M_AC_BAR':1.,'M_KI_BAR':.6},
              'r':0.,'underlyings':[{'name':'U1','ticker':'TEST','sigma':20.,'q':0.}]}
    script = ATHENA
    if with_interim:
        script = script.replace('CONSTAT StartDate', 'CONSTAT Interim\nCONSTAT StartDate')
        script += '\nAT Interim:\n  PAY 0.01 "Flux intermédiaire"\n'
        market['constats']['INTERIM'] = '2028-04-06'
    deal = SimpleNamespace(script_snapshot=script, strike_date='2026-10-06',
        market_snapshot_json=json.dumps(market), underlyings_json=json.dumps([{'name':'U1','ticker':'TEST'}]), devise='EUR', T=3.)
    rolled, _, _, _, horizon = _reinvest_context(deal, 2.)
    assert rolled.origine == date.today()
    assert horizon == pytest.approx(round(2*365.25)/365.25, abs=1e-6)
    assert len(rolled.events[0].dates) == 2
    if with_interim:
        interim = next(event for event in rolled.events if event.constat_ref == 'INTERIM')
        assert interim.dates == pytest.approx([(date(2028, 4, 6)-date(2026, 10, 6)).days/365.25])


def test_reinvestment_risk_flags_use_booked_values_of_required_parameters():
    import json
    from types import SimpleNamespace
    from backend.app.api.deals import _script_flags
    deal = SimpleNamespace(script_snapshot=ATHENA, market_snapshot_json=json.dumps({
        'user_params': {'COUPON': .08, 'M_AC_BAR': 1., 'M_KI_BAR': .6}}))
    assert _script_flags(deal) == {
        'has_stop': True, 'has_ki_param': True, 'has_autocall_param': True}
