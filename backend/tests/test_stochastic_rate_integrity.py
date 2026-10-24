"""C15: funding separation, joint Gaussian drivers and stable short rates."""
import json
import math

import numpy as np
import pytest

from backend.app.core.payscript import engine as engine
from backend.app.core.payscript.parser import parse_script

MODELS = ["constant", "heston", "sabr", "localvol", "lsv"]
UL = {"name":"A", "ticker":"TK1", "ccy":"EUR", "sigma":.2, "q":0.,
      "v0":.04, "theta":.04, "kappa":2., "xi":.3, "rho_h":-.5,
      "alpha":.2, "beta":1., "rho":-.3, "nu":.4, "skew":0., "curvature":0.}


def price(source="AT MATURITY:\n  PAY 1", **kwargs):
    options=dict(r=.03,T_max=1.,N=32,antithetic=True,sigma_r=.02,a_r=.3)
    options.update(kwargs)
    return engine.run_mc(parse_script(source),[dict(UL)],[[1.]],**options)


@pytest.mark.parametrize("model",MODELS)
@pytest.mark.parametrize("a_r",[0.,1e-8,.3])
def test_vanishing_rate_volatility_has_one_funding_discount(model,a_r):
    result=price(model=model,a_r=a_r,sigma_r=1e-12,funding_spread=.02)
    assert result["price"]==pytest.approx(math.exp(-.05),abs=5.1e-7)


@pytest.mark.parametrize("funding",[{"funding_spread":.02},{"funding_curve":[[.5,.02],[2.,.02]]}])
def test_payment_rebase_and_parallel_shocks_do_not_double_count_funding(funding):
    result=price(sigma_r=1e-12,yield_curve=[[.5,.03],[2.,.03]],
                 dr=.004,ds=.003,maturity_payment_t=1.25,value_date_t=.1,**funding)
    expected=math.exp(-(.03+.004+.02+.003)*(1.25-.1))
    assert result["price"]==pytest.approx(expected,abs=5.1e-7)


@pytest.mark.parametrize("model",MODELS)
@pytest.mark.parametrize("antithetic", [False, True])
@pytest.mark.parametrize("funding", [
    {"funding_spread": .02},
    {"funding_curve": [[.5, .01], [2., .04]]},
    {"ds": .02},
])
def test_funding_changes_present_value_without_changing_raw_asset_payoffs(model,antithetic,funding):
    kwargs=dict(model=model,N=64,sigma_r=.02,a_r=.3,antithetic=antithetic,yield_curve=[[.5,.01],[2.,.04]])
    clean=price("AT MATURITY:\n  PAY WOF",**kwargs)
    funded=price("AT MATURITY:\n  PAY WOF",**funding,**kwargs)
    # The non-flat zero-spread curve interpolates to 2% at the one-year payment.
    assert clean["payoffs"]==funded["payoffs"]
    assert funded["price"]==pytest.approx(clean["price"]*math.exp(-.02),abs=1.1e-6)


def test_funding_leaves_stochastic_rates_and_risk_free_factors_identical(monkeypatch):
    observed=[]
    original=engine._stochastic_rate_paths
    def capture(*args, **kwargs):
        rates, dfs=original(*args, **kwargs)
        observed.append((rates.copy(), dfs.copy()))
        return rates, dfs
    monkeypatch.setattr(engine,"_stochastic_rate_paths",capture)
    price()
    price(funding_curve=[[.5,.01],[2.,.04]],ds=.003)
    for clean, funded in zip(observed[:2], observed[2:]):
        np.testing.assert_array_equal(clean[0], funded[0])
        np.testing.assert_array_equal(clean[1], funded[1])


@pytest.mark.parametrize("model",MODELS)
@pytest.mark.parametrize("rho",[-1.,-.8,0.,.8,1.])
def test_mono_uses_the_joint_factor_in_every_simulator(model,rho,monkeypatch):
    observed=[]
    original=engine._blend_rate_factor
    def capture(asset,rate,correlation):
        combined=original(asset,rate,correlation)
        observed.append((np.asarray(combined).ravel(),np.asarray(rate).ravel()))
        return combined
    monkeypatch.setattr(engine,"_blend_rate_factor",capture)
    ul=[{**UL,"rho_rS":rho}]
    engine.run_mc(parse_script("AT MATURITY:\n  PAY 1"),ul,[[1.]],.03,1/365.25,16000,
                  model=model,antithetic=False,sigma_r=.02,a_r=.3)
    assert observed
    combined,rate=observed[0]
    assert np.var(combined)==pytest.approx(1.,abs=.04)
    assert np.corrcoef(combined,rate)[0,1]==pytest.approx(rho,abs=.015)


def test_joint_basket_covariance_is_preserved(monkeypatch):
    observed=[]
    original=engine._blend_rate_factor
    def capture(asset,rate,rho):
        result=original(asset,rate,rho)
        observed.append((np.asarray(result).ravel(),np.asarray(rate).ravel()))
        return result
    monkeypatch.setattr(engine,"_blend_rate_factor",capture)
    engine.run_mc(parse_script("AT MATURITY:\n  PAY 1"),[{**UL,"rho_rS":.6},{**UL,"name":"B","rho_rS":-.2}],
                  [[1.,.3],[.3,1.]],.03,1/365.25,16000,antithetic=False,sigma_r=.02)
    first,rate=observed[0]; second,_=observed[1]
    assert np.var(first)==pytest.approx(1.,abs=.04)
    assert np.var(second)==pytest.approx(1.,abs=.04)
    assert np.corrcoef(first,second)[0,1]==pytest.approx(.3,abs=.02)
    assert np.corrcoef(first,rate)[0,1]==pytest.approx(.6,abs=.02)
    assert np.corrcoef(second,rate)[0,1]==pytest.approx(-.2,abs=.02)


def test_incompatible_joint_correlations_are_refused():
    with pytest.raises(ValueError, match="Corrélations incompatibles"):
        engine.run_mc(parse_script("AT MATURITY:\n  PAY 1"),
            [{**UL,"rho_rS":.9},{**UL,"name":"B","rho_rS":.9}],
            [[1.,.3],[.3,1.]],.03,1.,32,sigma_r=.02)


def test_prepaid_forward_martingale_on_independent_replications(record_property):
    results=[]
    target=math.exp(-.01)
    for seed in [7,19,41,101]:
        result=engine.run_mc(parse_script("AT MATURITY:\n  PAY WOF"),[{**UL,"q":.01,"rho_rS":.8}],[[1.]],
            .03,1.,8192,seed=seed,antithetic=True,sigma_r=.03,a_r=.3)
        se=(result["ic95"][1]-result["ic95"][0])/3.92
        assert abs(result["price"]-target)<=5*se+1e-6
        results.append({"seed":seed,"price":result["price"],"standard_error":se,"target":target})
    average=np.mean([r["price"] for r in results])
    se=math.sqrt(sum(r["standard_error"]**2 for r in results))/len(results)
    assert abs(average-target)<=3*se+1e-6
    record_property("prepaid_forward_replications",json.dumps(results))


@pytest.mark.parametrize("T",[1/365.25,1.,30.])
@pytest.mark.parametrize("a_r",[0.,1e-4,1e-6,1e-8,.3])
def test_discrete_convexity_matches_independent_gaussian_covariance(T,a_r):
    steps,dt=engine._simulation_axis(T)
    sigma=.03
    t=np.arange(1,steps+1)*dt
    minimum=np.minimum(t[:,None],t[None,:])
    if a_r==0:
        covariance=sigma**2*minimum
    else:
        covariance=(sigma**2*np.exp(-a_r*np.abs(t[:,None]-t[None,:]))
                    *(-np.expm1(-2*a_r*minimum))/(2*a_r))
    # Dense Gaussian covariance is an independent oracle for Var(dt * sum x),
    # including every intermediate pillar, rather than a copy of the recurrence.
    variance=np.diag(np.cumsum(np.cumsum(covariance,axis=0),axis=1))*dt**2
    phi=math.exp(-a_r*dt)
    step_sd=sigma*math.sqrt(dt if a_r==0 else -math.expm1(-2*a_r*dt)/(2*a_r))
    actual=2*np.cumsum(engine._hw_convexity(sigma,a_r,dt,steps,phi,step_sd))*dt
    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual,variance,rtol=3e-12,atol=1e-20)


@pytest.mark.parametrize("T",[1/365.25,1.,30.])
def test_paths_and_factors_are_continuous_at_zero_reversion(T):
    steps,dt=engine._simulation_axis(T)
    shocks=np.random.default_rng(42).standard_normal((steps,16))
    fwd=np.full(steps,.03)
    r0,df0=engine._stochastic_rate_paths(fwd,.03,0.,math.sqrt(dt),dt,shocks)
    for a in [1e-4,1e-6,1e-8]:
        rates,dfs=engine._stochastic_rate_paths(fwd,.03,a,math.sqrt(dt),dt,shocks)
        assert np.isfinite(rates).all() and np.isfinite(dfs).all() and (dfs>0).all()
        if a==1e-8:
            np.testing.assert_allclose(rates,r0,rtol=0,atol=2e-6)
            np.testing.assert_allclose(dfs,df0,rtol=5e-6,atol=1e-12)


@pytest.mark.parametrize("a_r",[0.,1e-4,1e-6,1e-8])
def test_zero_coupon_price_is_finite_and_continuous_near_zero(a_r):
    result=price(a_r=a_r,sigma_r=.03,N=2048)
    reference=price(a_r=0.,sigma_r=.03,N=2048)
    assert math.isfinite(result["price"])
    assert result["price"]==pytest.approx(reference["price"],abs=1e-5)


@pytest.mark.parametrize("T", [1/365.25, 30.])
def test_short_and_long_zero_coupon_prices_have_a_continuous_zero_limit(T):
    reference=price(T_max=T,a_r=0.,sigma_r=.03,N=256)["price"]
    for a in [1e-4,1e-6,1e-8]:
        value=price(T_max=T,a_r=a,sigma_r=.03,N=256)["price"]
        assert math.isfinite(value) and value>0.
        assert value==pytest.approx(reference,rel=.005)
        if a==1e-8:
            assert value==pytest.approx(reference,abs=1e-5)


@pytest.mark.parametrize("field,value",[("sigma_r",float("nan")),("sigma_r",-.01),("a_r",float("nan")),("a_r",-.01)])
def test_invalid_rate_parameters_fail_closed(field,value):
    params=dict(fwd=np.array([.03]),sigma_r=.03,a_r=.3,sq_dt=1.,dt=1.,Z_r=np.zeros((1,2)))
    params[field]=value
    with pytest.raises(ValueError):
        engine._stochastic_rate_paths(**params)
    with pytest.raises(ValueError):
        price(**{field:value})


def test_nonfinite_or_underflowed_factors_are_refused():
    for shocks in [np.array([[float("nan")]]),np.array([[float("inf")]]),np.array([[1e6]])]:
        with pytest.raises(ValueError):
            engine._stochastic_rate_paths(np.array([.03]),.1,0.,1.,1.,shocks)
