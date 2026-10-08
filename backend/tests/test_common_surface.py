import math
import numpy as np
import pytest

from backend.app.core.volatility_surface import SSVISurface
from backend.scripts.vol_model_references import black_scholes
from backend.scripts.compare_common_surface import athena_flows


def test_ssvi_static_arbitrage_certificate_covers_all_strikes_and_horizon():
    surface=SSVISurface()
    certificate=surface.certificate()
    assert certificate['butterfly_slope_bound']<4
    assert certificate['butterfly_curvature_bound']<4
    for t in np.geomspace(.001,5,20):
        k=np.linspace(-15,15,1001)
        w,wk,wkk,wt=surface.derivatives(k,t)
        assert np.all(w>0) and np.all(wt>0)
        assert np.all(surface.density_factor(k,t)>0)
        assert np.all(np.isfinite(surface.local_vol(k,t)))


def test_ssvi_derivatives_and_digital_match_independent_finite_differences():
    surface=SSVISurface();t=2.;k=-.3;h=1e-4
    w,wk,wkk,wt=surface.derivatives(k,t)
    assert wk==pytest.approx((surface.derivatives(k+h,t)[0]-surface.derivatives(k-h,t)[0])/(2*h),rel=1e-6)
    assert wkk==pytest.approx((surface.derivatives(k+h,t)[0]-2*w+surface.derivatives(k-h,t)[0])/h**2,rel=1e-6)
    assert wt==pytest.approx((surface.derivatives(k,t+h)[0]-surface.derivatives(k,t-h)[0])/(2*h),rel=1e-6)
    for strike in (.4,.6,.8,1.,1.2,1.5):
        call,put,digital=surface.vanillas(strike,t)
        numerical=(surface.vanillas(strike+h,t)[1]-surface.vanillas(strike-h,t)[1])/(2*h)
        assert digital==pytest.approx(numerical,abs=1e-7)
        assert call-put==pytest.approx(math.exp(-.02*t)-strike*math.exp(-.03*t),abs=1e-12)
        assert 0<=digital<=math.exp(-.03*t)


def test_ssvi_flat_limit_and_equity_smile():
    flat=SSVISurface(eta=0)
    for t in (1.,4.):
        for k in (.6,1.,1.2):
            np.testing.assert_allclose(flat.vanillas(k,t),black_scholes(k,t,.2),atol=1e-14)
        np.testing.assert_allclose(flat.local_vol(np.array([-1,0,1]),t),.2)
        surface=SSVISurface()
        vol=np.sqrt(surface.derivatives(np.log([.6,.8,1,1.2])-.01*t,t)[0]/t)
        assert np.all(np.diff(vol)<0)
        assert vol[0]>.26


def test_ssvi_rejects_invalid_surface_instead_of_falling_back():
    with pytest.raises(ValueError): SSVISurface(eta=4,shape_scale=.04)
    with pytest.raises(ValueError): SSVISurface(rho=-1)
    with pytest.raises(ValueError): SSVISurface().local_vol(0,6)


def test_athena_separates_capital_coupon_and_put_and_stops_at_recall():
    levels=np.array([[1.01,.8,.7,.8],[.2,.9,.7,1.03],[.1,.95,.7,.1],[.1,.7,.4,.1]])[:,None,:]
    pv,flows=athena_flows(levels,[1.,2.,3.,4.])
    np.testing.assert_allclose(pv,[1.1*math.exp(-.03),math.exp(-.12),.4*math.exp(-.12),1.2*math.exp(-.06)])
    np.testing.assert_allclose(sum(x['capital'] for x in flows),1)
    assert flows[0]['coupons'][0]==pytest.approx(.1)
    assert flows[1]['coupons'][3]==pytest.approx(.2)
    assert flows[-1]['capital'][2]==1
    assert flows[-1]['put'][2]==pytest.approx(-.6)


def test_athena_final_recall_and_exact_protection_boundary():
    levels=np.array([[.7,.7],[.7,.7],[.7,.7],[1.,.6]])[:,None,:]
    _,flows=athena_flows(levels,[1.,2.,3.,4.])
    np.testing.assert_allclose(flows[-1]['coupons'],[.4,0])
    np.testing.assert_allclose(flows[-1]['put'],[0,0])
