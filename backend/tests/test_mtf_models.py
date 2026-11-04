"""Model state, shared time axis and process-backed A/B comparisons."""
import math
from datetime import date

import numpy as np
import pytest
from fastapi import HTTPException

from backend.app.api.pricing import mtf_comparison_endpoint, mtf_drilldown_endpoint, mtf_endpoint
from backend.app.core.payscript import engine
from backend.app.core.schemas import MtfComparisonRequest, MtfDrilldownRequest, MtfRequest


UL = dict(name='BNP Paribas', ticker='BNP.PA', sigma=.2761, q=.0653,
          v0=.27**2, theta=.24**2, kappa=1.7, xi=.45, rho_h=-.55,
          alpha=.25, beta=.8, nu=.4, rho=-.4, skew=0., curvature=0.)
MODELS = ['constant', 'heston', 'sabr', 'localvol']
R = .03


@pytest.mark.parametrize('model,simulator', [('heston', engine._simulate_heston), ('sabr', engine._simulate_sabr)])
def test_latent_state_restarts_the_same_diffusion(model, simulator):
    rng = np.random.default_rng(123)
    dt = np.array([.031, .05, .012, .028, .01])
    z, zv = rng.normal(size=(2, len(dt), 1, 32))
    factors = np.empty((len(dt) + 1, 1, 32))
    spots = simulator(len(dt), 1, 32, dt, np.sqrt(dt), [UL], R, np.eye(1), z, zv,
                      factor_out=factors)
    assert np.ptp(factors[2]) > .01
    tail = dt[2:]
    restarted = simulator(len(tail), 1, 32, tail, np.sqrt(tail), [UL], R, np.eye(1), z[2:], zv[2:],
                          spots[2], factor_init=factors[2])
    np.testing.assert_array_equal(restarted, spots[2:])
    reset = simulator(len(tail), 1, 32, tail, np.sqrt(tail), [UL], R, np.eye(1), z[2:], zv[2:], spots[2])
    assert not np.allclose(reset[-1], spots[-1])


def test_flat_localvol_and_constant_alpha_sabr_reduce_to_gbm():
    ul = [dict(UL, alpha=UL['sigma'], beta=1., nu=0., skew=0., curvature=0.)]
    dt = np.array([.031, .05, .012, .028, .01])
    args = (ul, [[1.]], R, [.131], 32, 42, None, dt)
    gbm, _, _ = engine._mtf_outer_state('constant', *args)
    for model in ['sabr', 'localvol']:
        spot, _, _ = engine._mtf_outer_state(model, *args)
        np.testing.assert_allclose(spot, gbm, atol=2e-6, rtol=0)


def test_heston_low_vol_of_vol_approaches_gbm():
    ul = [dict(UL, v0=UL['sigma']**2, theta=UL['sigma']**2, xi=1e-5, rho_h=0.)]
    dt = np.full(52, 1/52)
    args = (ul, [[1.]], R, [1.], 128, 42, None, dt)
    gbm, _, _ = engine._mtf_outer_state('constant', *args)
    heston, _, _ = engine._mtf_outer_state('heston', *args)
    np.testing.assert_allclose(heston, gbm, atol=6e-5, rtol=0)


def test_frozen_lsv_restarts_at_the_outer_spot_variance_and_surface_time():
    dt = np.array([.02, .03, .01, .04])
    z, zv = np.random.default_rng(123).normal(size=(2, len(dt), 1, 32))
    target = np.full((len(dt), 3), .3)
    leverage = np.arange(1., 5.)[:, None] * np.ones((1, 3))
    factors = np.empty((len(dt) + 1, 1, 32))
    start = 2
    spots = engine._simulate_lsv(
        len(dt), 1, 32, dt, np.sqrt(dt), [UL], R, np.eye(1), z, zv,
        [target], 3, -1., 1., leverage_grids=[leverage], factor_out=factors)
    tail = dt[start:]
    resumed = engine._simulate_lsv(
        len(tail), 1, 32, tail, np.sqrt(tail), [UL], R, np.eye(1), z[start:], zv[start:],
        [target[start:]], 3, -1., 1., spots[start],
        leverage_grids=[leverage[start:]], factor_init=factors[start])
    assert np.ptp(factors[start]) > .01
    np.testing.assert_array_equal(resumed, spots[start:])


def test_local_vol_inner_diffusion_keeps_the_absolute_surface_clock():
    ul = [dict(UL, sigma=.3, vol_surface=dict(rho=0., eta=0., shape_scale=.04, max_expiry=2.,
                                   atm_nodes=[[.5, .2], [1., .3], [2., .3]]))]
    dt = np.full(52, 1/52)
    spots, factors, surface = engine._mtf_outer_state('localvol', ul, [[1.]], R, [1.], 2, 42, None, dt)
    tail = dt[26:]
    actual = engine._mtf_inner_paths('localvol', ul, R, np.eye(1), tail, 50, 42, 0, 0, 2,
                                     spots[26], factors, surface, 26)
    # ATM total variance rises from .02 to .09 on [.5,1]. The surface
    # is strike-flat, so each tail step has constant instantaneous vol.
    sigma = math.sqrt((.09-.02)/.5)
    z = np.random.default_rng(42 + 1_000_003).normal(size=(26, 1, 100))
    start = np.repeat(spots[26], 50, axis=1)
    expected = start * np.exp((R-UL['q']-.5*sigma**2)*.5 + sigma*math.sqrt(1/52)*z.sum(axis=0))
    np.testing.assert_allclose(actual[-1], expected, atol=1e-12, rtol=0)


def _request(model='constant', **overrides):
    body = dict(script='AT 1:\n  PAY 0.01\nAT MATURITY:\n  PAY 1',
                underlyings=[UL], corr_matrix=[[1.]], r=R, T=1.105, model=model,
                strike_date='2026-11-03', value_date='2026-11-03', payment_date='2028-01-14',
                main_price=8, reference_paths=1000, n_outer=20, n_inner=50,
                mtm_dates=[.423, 1.05, 1.15, 1.2])
    return MtfRequest(**(body | overrides))


def test_lsv_mtf_qualifies_near_constant_variance_and_replays_the_mark():
    surface = dict(rho=0., eta=0., atm_nodes=[[1., .25], [2., .25]])
    underlying = dict(UL, sigma=.25, v0=.25**2, theta=.25**2, xi=1e-8, vol_surface=surface)
    req = _request('lsv', underlyings=[underlying], T=.55, payment_date=None,
                   script='AT MATURITY:\n  PAY MAX(WOF - 1, 0)', mtm_dates=[.25, .55])
    fan = mtf_endpoint(req)
    local = mtf_endpoint(req.model_copy(update={'model': 'localvol'}))
    assert fan['main_price'] == local['main_price']
    np.testing.assert_allclose(fan['results'][0]['pvs'], local['results'][0]['pvs'], atol=.0002, rtol=0)
    drill_request = MtfDrilldownRequest(**(req.model_dump() | dict(
        t=.25, scenario_ids=[0], main_price=fan['main_price'],
        context_fingerprint=fan['context_fingerprint'], lsv_qualification=fan['lsv_qualification'])))
    drill = mtf_drilldown_endpoint(drill_request)
    assert drill['scenarios'][0]['mtf'] == pytest.approx(fan['results'][0]['pvs'][0], abs=.000051)
    with pytest.raises(HTTPException, match='levier LSV a changé'):
        mtf_drilldown_endpoint(drill_request.model_copy(update={'lsv_qualification': '0'*64}))


@pytest.mark.parametrize('slope', [0., .10])
def test_gbm_atm_curve_reference_and_drilldown(slope):
    from scipy.special import ndtr

    surface = dict(atm_scenario='flat' if slope == 0 else 'contango', rho=-.75, eta=.85,
                   atm_nodes=[[t, .25*(1+slope*(t-1)/9)] for t in range(1, 11)])
    req = _request(script='AT MATURITY:\n  PAY MAX(WOF - 1, 0)',
                   underlyings=[dict(UL, sigma=.25, vol_surface=surface)],
                   T=4., payment_date=None, mtm_dates=[1., 2.125, 4.],
                   reference_paths=8000, gbm_atm_curve=True)
    fan = mtf_endpoint(req)
    assert fan['gbm_atm_curve']
    if slope == 0:
        legacy = mtf_endpoint(req.model_copy(update={'gbm_atm_curve': False}))
        assert legacy['main_price'] == fan['main_price']
        assert [row['pvs'] for row in legacy['results']] == [row['pvs'] for row in fan['results']]
    variance = 4*surface['atm_nodes'][3][1]**2
    d1 = ((R-UL['q'])*4+.5*variance)/math.sqrt(variance)
    exact = 100*(math.exp(-4*UL['q'])*ndtr(d1)-math.exp(-4*R)*ndtr(d1-math.sqrt(variance)))
    assert fan['main_price'] == pytest.approx(exact, abs=.6)
    row = fan['results'][1]
    detail = mtf_drilldown_endpoint(MtfDrilldownRequest(**(req.model_dump() | dict(
        t=row['t'], scenario_ids=[0, 19], main_price=fan['main_price'],
        context_fingerprint=fan['context_fingerprint']))))
    for index, scenario in zip((0, 19), detail['scenarios']):
        assert scenario['mtf'] == pytest.approx(row['pvs'][index], abs=.0001)


def test_gbm_atm_step_variance_across_a_pillar():
    steps = np.array([.5, 1., .5])
    ul = [dict(vol_surface=dict(max_expiry=2., atm_nodes=[[1., .2], [2., .3]]))]
    actual = engine._atm_step_vols(ul, steps, len(steps))[:, 0]**2 * steps
    np.testing.assert_allclose(actual, [.02, .09, .07])


@pytest.mark.parametrize('model', MODELS)
def test_reference_and_drilldown_keep_delayed_capital_on_custom_grid(model):
    surface = dict(rho=-.4, eta=.1, shape_scale=.04, max_expiry=3.,
                   atm_nodes=[[.25, .24], [1., .2761], [3., .30]])
    req = _request(model, underlyings=[dict(UL, vol_surface=surface)] if model == 'localvol' else [UL])
    fan = mtf_endpoint(req)
    payment = round((date(2028, 1, 14)-date(2026, 11, 3)).days/365.25, 6)
    p0 = math.exp(-R) + 100 * math.exp(-R*payment)
    assert fan['model'] == model
    assert fan['main_price'] == pytest.approx(p0, abs=.0001)
    for row in fan['results']:
        mark = row['t']
        cash = sum(flow['amount'] * 100 * math.exp(-R*flow['payment_t']) for flow in row['settled_flows'][0])
        assert math.exp(-R*mark)*row['pvs'][0] + cash == pytest.approx(p0, abs=.0001)
        detail = mtf_drilldown_endpoint(MtfDrilldownRequest(**(req.model_dump() | dict(
            t=mark, scenario_ids=[0, 19], main_price=fan['main_price'],
            context_fingerprint=fan['context_fingerprint']))))
        for scenario in detail['scenarios']:
            assert scenario['mtf'] == pytest.approx(row['pvs'][scenario['id']], abs=5.1e-5)
            assert scenario['sum_pv'] == pytest.approx(scenario['mtf'], abs=5e-6)
    assert fan['results'][2]['n_pending_settlement'] == 20
    assert fan['results'][-1]['n_outstanding'] == 0


def test_comparison_runs_through_process_executor_and_isolates_an_invalid_leg():
    a, b = _request(), _request('heston')
    pair = mtf_comparison_endpoint(MtfComparisonRequest(a=a, b=b))
    assert pair['a']['result']['mtm_dates'] == pair['b']['result']['mtm_dates']
    assert pair['a']['result']['context_fingerprint'] != pair['b']['result']['context_fingerprint']
    bad = _request('heston', underlyings=[dict(UL, xi=-.1)])
    partial = mtf_comparison_endpoint(MtfComparisonRequest(a=a, b=bad))
    assert partial['a']['result']['main_price'] == pair['a']['result']['main_price']
    assert 'xi' in partial['b']['error']
    with pytest.raises(HTTPException, match='même produit'):
        mtf_comparison_endpoint(MtfComparisonRequest(a=a, b=_request('heston', r=.04)))
    with pytest.raises(HTTPException, match='contexte'):
        mtf_drilldown_endpoint(MtfDrilldownRequest(**(b.model_dump() | dict(
            t=1.15, scenario_ids=[0], main_price=pair['a']['result']['main_price'],
            context_fingerprint=pair['a']['result']['context_fingerprint']))))


def test_comparison_freezes_lifecycle_once_and_includes_acquired_claim_in_p0(monkeypatch):
    from backend.app.api import inlife

    loads = []
    def history(*args, **kwargs):
        loads.append(args)
        return dict(dates=['2026-11-03', '2027-11-03', '2027-11-04'],
                    prices={'BNP.PA': [100., 90., 91.]})

    monkeypatch.setattr(inlife, 'load_hist_prices', history)
    a = _request(script='CONSTAT() OBS\nAT OBS:\n  PAY 0.08\nAT MATURITY:\n  PAY 1',
                 T=3., maturity_date='2029-11-05', payment_date='2029-11-08',
                 valuation_date='2027-11-04', settlement_ccy='EUR', mtm_dates=[1/365.25, .5, 2.1],
                 constats={'OBS': dict(start_date='2026-11-03', roll_date='2027-11-03',
                                       end_date='2029-11-05', frequency='1Y',
                                       convention='following', settlement_lag=3)})
    b = a.model_copy(update={'model': 'heston'})
    pair = mtf_comparison_endpoint(MtfComparisonRequest(a=a, b=b))
    assert len(loads) == 1
    fan = pair['b']['result']
    assert fan['main_price'] == pair['a']['result']['main_price']
    assert fan['results'][0]['pending_pvs'][0] == pytest.approx(8*math.exp(-R*3/365.25))
    for row in fan['results']:
        cash = sum(flow['amount']*100*math.exp(-R*flow['payment_t']) for flow in row['settled_flows'][0])
        assert row['pvs'][0]*math.exp(-R*row['t']) + cash == pytest.approx(fan['main_price'], abs=.00012)
    detail = mtf_drilldown_endpoint(MtfDrilldownRequest(**(b.model_dump() | dict(
        t=fan['mtm_dates'][0], scenario_ids=[0], main_price=fan['main_price'],
        context_fingerprint=fan['context_fingerprint']))))
    assert detail['model'] == 'heston'
    assert detail['scenarios'][0]['mtf'] == pytest.approx(fan['results'][0]['pvs'][0], abs=5.1e-5)
