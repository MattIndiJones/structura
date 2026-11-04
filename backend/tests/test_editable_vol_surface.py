import math
from copy import deepcopy

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.auth import get_current_user
from backend.app.api.volatility import router
from backend.app.api.inlife import _snapshot_underlying
from backend.app.core.inlife_valuation import _engine_underlyings
from backend.app.core.schemas import UnderlyingParams, VolatilitySurfaceParams
from backend.app.core.volatility_surface import TermSSVISurface, surface_from_underlying
from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script


def payload(vol=.3, rho=-.75, eta=.85):
    return dict(profile='equity',mode='automatic',rho=rho,eta=eta,shape_scale=.04,
                max_expiry=10.,atm_nodes=[[t,vol] for t in (.25,.5,1.,2.,3.,5.,7.,10.)])


def test_class_and_level_profiles_match_proposed_anchors_and_flat_limit():
    equity=TermSSVISurface(payload())
    index=TermSSVISurface(payload(.2,-.8,1.05))
    np.testing.assert_allclose(equity.implied_vol([.6,.8,1.,1.2],1),[.422476,.356977,.3,.252116],atol=1e-6)
    assert index.implied_vol(.8,1)>.26
    assert equity.implied_vol(.8,4)<equity.implied_vol(.8,1)
    assert TermSSVISurface(payload(.4)).implied_vol(.8,1)>equity.implied_vol(.8,1)
    flat=TermSSVISurface(payload(eta=0))
    np.testing.assert_allclose(flat.local_vol(np.linspace(-10,10,101),2),.3,atol=1e-12)


def test_nonflat_atm_term_structure_has_positive_density_and_calendar_derivative():
    p=payload();p['atm_nodes']=[[.5,.32],[1,.30],[2,.28],[5,.25],[10,.24]]
    s=TermSSVISurface(p)
    for t in np.geomspace(.001,10,20):
        k=np.linspace(-12,12,501)
        assert np.all(s.derivatives(k,t)[3]>0)
        assert np.all(s.density_factor(k,t)>0)
    k=-.3;t=1.4;h=1e-5
    assert s.derivatives(k,t)[3]==pytest.approx((s.derivatives(k,t+h)[0]-s.derivatives(k,t-h)[0])/(2*h),rel=1e-7)
    assert s.implied_vol(1,1)==pytest.approx(.3)


def test_invalid_manual_edits_are_rejected_not_fallback():
    p=payload();p['atm_nodes'][2][1]=.01
    with pytest.raises(ValueError,match='variance totale'): VolatilitySurfaceParams(**p)
    p=payload();p['eta']=3
    with pytest.raises(ValueError): VolatilitySurfaceParams(**p)
    p=payload();p['atm_nodes'][0][1]=math.nan
    with pytest.raises(ValueError): VolatilitySurfaceParams(**p)


def test_surface_survives_display_booking_residual_roundtrip_without_percent_conversion():
    u=UnderlyingParams(name='SG',ticker='GLE.PA',sigma=.3,asset_class='equity',vol_surface=payload(),smile_parameter_mode='manual')
    snapshot=_snapshot_underlying(u)
    result=_engine_underlyings({'underlyings':[snapshot]},[{'name':'SG','ticker':'GLE.PA'}])[0]
    assert result['vol_surface']==u.vol_surface.model_dump()
    assert result['sigma']==.3
    assert result['asset_class']=='equity'
    assert result['smile_parameter_mode']=='manual'
    result['vol_surface']['atm_nodes'][0][1]=.4
    assert snapshot['vol_surface']['atm_nodes'][0][1]==.3


def test_dupire_bounds_only_exterior_ssvi_wings():
    log_forward = np.log([.01, .05, .1, .19, .21, 1., 1.79, 1.81, 3., 10.])
    row = np.array([4.2, 3.2, 2.8, 2., 1.8, .55, .5, .6, 3.2, 4.])
    assert engine._extend_ssvi_local_vol_wings(row, log_forward) == pytest.approx(
        {"left": .05, "right": 3.})
    np.testing.assert_array_equal(row, [3., 3., 2.8, 2., 1.8, .55, .5, .6, 3., 3.])

    for rejected in ([4., 4., 4., 4., 2., .55, .5, .6, 1., 1.],
                     [1., 4., 1., 1., 1., .55, .5, .6, 1., 1.]):
        row = np.array(rejected)
        assert engine._extend_ssvi_local_vol_wings(row, log_forward) is None
        np.testing.assert_array_equal(row, rejected)


def test_stm_actions_default_is_accepted_in_dupire_but_not_lsv_grid():
    stm = dict(name='STM', sigma=.5464613633861714, q=.007388, vol_surface=payload(.5464613633861714))
    rates = engine._build_rate_term([], 156, 1/52, .03, 0.)
    wings = []
    grids, *_ = engine._build_lv_grid([stm], rates, 156, 1/52, allow_ssvi_wings=True,
                                     wing_diagnostics=wings)
    assert np.max(grids[0]) == 3.
    assert len(wings) == 1
    assert wings[0]['underlying'] == 'STM' and wings[0]['side'] == 'left'
    assert max(step['boundary_forward'] for step in wings[0]['steps']) < .10
    with pytest.raises(ValueError, match='Plafond numérique : 300 %'):
        engine._build_lv_grid([stm], rates, 156, 1/52)


def test_dupire_grid_still_rejects_a_breach_in_the_protected_range(monkeypatch):
    monkeypatch.setattr(TermSSVISurface, 'local_vol',
                        lambda self, k, t: np.where(k < np.log(.30), 3.2, .40))
    rates = engine._build_rate_term([], 1, 1/52, .03, 0.)
    with pytest.raises(ValueError, match='Plafond numérique : 300 %'):
        engine._build_lv_grid([dict(vol_surface=payload())], rates, 1, 1/52,
                              allow_ssvi_wings=True)


def test_surface_grid_uses_term_carry_and_responds_to_sigma_scenario():
    u=dict(sigma=.3,q=.02,vol_surface=payload(),dividend_curve=[[1,.02],[2,.01]])
    rates=engine._build_rate_term([[1,.03],[2,.04]],104,1/52,.03,0)
    grids,n,lo,hi=engine._build_lv_grid([u],rates,104,1/52)
    assert n==300 and grids[0].shape==(104,300)
    assert np.all(np.isfinite(grids[0]))
    bumped=deepcopy(u);bumped['sigma']=.35
    assert surface_from_underlying(bumped).implied_vol(1,1)==pytest.approx(.35)
    assert not np.allclose(engine._build_lv_grid([bumped],rates,104,1/52)[0][0],grids[0])


def test_surface_reaches_pricing_and_flat_target_equals_gbm_with_common_random_numbers():
    script=parse_script('AT MATURITY:\n  PAY MAX(1 - WOF, 0)\n')
    u=dict(name='SG',sigma=.3,q=.02,vol_surface=payload(eta=0))
    args=dict(script=script,underlyings=[u],corr_matrix=[[1]],r=.03,T_max=1.,N=12000,seed=42)
    constant=engine.run_mc(**args,model='constant')['price']
    flat=engine.run_mc(**args,model='localvol')['price']
    assert flat==pytest.approx(constant,abs=1e-10)
    u['vol_surface']=payload()
    smile=engine.run_mc(**args,model='localvol')['price']
    assert abs(smile-flat)>.001


def test_paths_expose_the_start_spot_vol_on_both_sides_of_the_crossing():
    maturity = 1.
    nsteps = 52
    dt = maturity / nsteps
    u = dict(name='SG', sigma=.35, q=.02, vol_surface=payload(.35))
    result = engine.run_mc_paths(parse_script('AT MATURITY:\n  PAY 1'),
                                 [u], [[1]], .03, maturity, model='localvol')
    trace = result['local_vol_trace']
    steps = trace['steps']
    index = trace['crossing_step'] - 1
    assert 0 < index < len(steps)-1
    crossing = steps[index]
    after = steps[index+1]
    assert crossing['start_spot'] >= .60 > crossing['end_spot']
    assert after['start_spot'] == crossing['end_spot']
    assert after['start_time'] == crossing['end_time']
    assert crossing['local_vol'] != after['local_vol']
    rates = engine._build_rate_term([], nsteps, dt, .03, 0.)
    grid, nodes, lo, hi = engine._build_lv_grid([u], rates, nsteps, dt)
    for row in steps:
        expected = np.interp(np.log(row['start_spot']), np.linspace(lo, hi, nodes), grid[0][row['step']-1])
        assert row['local_vol'] == pytest.approx(expected)


def test_authenticated_surface_api_rejects_invalid_and_returns_full_certificate():
    app=FastAPI();app.include_router(router)
    client=TestClient(app)
    assert client.post('/api/volatility/validate',json={'surface':payload()}).status_code==401
    app.dependency_overrides[get_current_user]=lambda:object()
    response=client.post('/api/volatility/validate',json={'surface':payload()})
    assert response.status_code==200
    assert response.json()['certificate']['calendar_monotone']
    assert response.json()['certificate']['parameters']['atm_nodes']==payload()['atm_nodes']
    invalid=payload();invalid['rho']=-1
    assert client.post('/api/volatility/validate',json={'surface':invalid}).status_code==422


def test_left_wing_request_keeps_atm_and_prices_the_achieved_surface():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: object()
    original = payload(.349524, eta=.95)
    original['atm_nodes'][0][1] = .343992
    original['atm_nodes'][-1][1] = .35451
    base = TermSSVISurface(original)
    res = TestClient(app).post('/api/volatility/left-wing', json=dict(
        surface=original, expiry=.5, strike=.2, target=1.1, horizon=3,
        rate=.03, dividend=.028009))
    assert res.status_code == 200, res.text
    fitted = res.json()
    assert fitted['changed'] and fitted['reason'] == 'dupire'
    assert .90 < fitted['achieved'] < 1.1
    target = TermSSVISurface(fitted['surface'])
    assert target.implied_vol(.2, .5) == pytest.approx(fitted['achieved'])
    for t in (.25, .5, .75, 1., 3., 10.):
        assert target.implied_vol(1., t) == pytest.approx(base.implied_vol(1., t))
    k, t, h = -1.2, .42, 1e-5
    assert target.derivatives(k, t)[3] == pytest.approx(
        (target.derivatives(k, t+h)[0]-target.derivatives(k, t-h)[0])/(2*h), rel=1e-7)
    u = dict(name='SG', sigma=.349524, q=.028009, vol_surface=fitted['surface'])
    result = engine.run_mc(parse_script('AT MATURITY:\n  PAY MAX(1 - WOF, 0)\n'),
                           [u], [[1]], .03, 3., 2000, 'localvol', 42)
    assert 0 < result['price'] < 1


def test_heston_fit_changes_initial_variance_with_target_level():
    from backend.app.core.smile_calibration import calibrate_surface
    first=calibrate_surface(payload(.2),'heston',2)
    second=calibrate_surface(payload(.3),'heston',2)
    assert first['parameters']['v0']<second['parameters']['v0']
    assert first['method']=='Fourier Heston'
    assert math.isfinite(first['max_price_error_bp'])
    assert first['approximate']


def test_legacy_shape_scenario_cannot_silently_ignore_the_new_surface():
    from backend.app.core.valuation_context import ValuationContext, run_valuation
    context=ValuationContext(underlyings=[dict(name='SG',sigma=.3,vol_surface=payload())],
                             corr_matrix=[[1]],r=.03,T=1,N=2000,model='localvol')
    with pytest.raises(ValueError,match='surface SSVI'):
        run_valuation(parse_script('AT MATURITY:\n  PAY 1\n'),context,
                      underlying_overrides={'SG':{'skew':-.15}})
