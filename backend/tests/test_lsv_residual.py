"""Residual market coordinates are independent of the contractual fixing."""
from dataclasses import replace
import math
import numpy as np
import pytest
from backend.app.core.payscript import engine
from backend.app.core.valuation_context import ValuationContext, valuation_context_from_dict, residual_surface_anchor, run_valuation
from backend.app.core.payscript.parser import parse_script
from backend.tests.test_simulation_grid import asset

@pytest.mark.parametrize('model',['localvol','lsv'])
def test_market_coordinates_restart_at_current_spot_but_keep_contractual_paths(model):
    intervals=np.array([.02,.013,.04,.05])
    ul=[asset('STM','STMPA.PA',.54646136,.007388)]
    rows=np.tile(np.linspace(.9,.2,301),(len(intervals),1))
    grid=([rows],301,math.log(.01),math.log(10.))
    rng=np.random.default_rng(318)
    z=rng.standard_normal((len(intervals),1,512));zv=rng.standard_normal(z.shape)
    args=(len(intervals),1,512,intervals,np.sqrt(intervals),ul,.03,np.eye(1),z)
    if model=='lsv':
        grid=(*grid,);extra={'leverage_grids':[rows]}
        simulate=lambda spot,anchor:engine._simulate_lsv(*args,zv,*grid,spot,local_vol_anchor=anchor,**extra)
    else:
        simulate=lambda spot,anchor:engine._simulate_lv(*args,*grid,spot,local_vol_anchor=anchor)
    base=simulate([1.],None)
    for current in (.45,.9,1.4):
        anchored=simulate([current],[current])
        np.testing.assert_allclose(anchored,current*base,rtol=1e-13,atol=1e-13)
        assert np.max(abs(anchored-simulate([current],None)))>1e-3


def test_context_freezes_anchor_and_variance_assumption_and_preserves_old_contexts():
    u=asset('STM','STMPA.PA',.54646136,.007388)
    ctx=ValuationContext(underlyings=[u],corr_matrix=[[1.]],r=.03,T=1.,N=1000,model='lsv',local_vol_anchor=[.5])
    restored=valuation_context_from_dict(ctx.to_dict())
    assert restored.local_vol_anchor==[.5]
    assert restored.underlyings[0]['v0']==u['v0']
    old=ctx.to_dict();old.pop('local_vol_anchor')
    assert valuation_context_from_dict(old).local_vol_anchor is None
    assert 'local_vol_anchor' not in valuation_context_from_dict(old).to_dict()
    for wrong in ([],[0.],[float('nan')],[.5,.7]):
        with pytest.raises(ValueError,match='Ancrage'):replace(ctx,local_vol_anchor=wrong)
    assert residual_surface_anchor('lsv',[u],[.5])==[.5]
    assert residual_surface_anchor('lsv',[u],[.5],pre_strike=True) is None

@pytest.mark.parametrize('frequency',[52,104,208])
def test_residual_lsv_paths_keep_martingale_and_payoff_at_current_level(frequency):
    u=asset('STM','STMPA.PA',.54646136,.007388)
    # Independent deterministic-volatility limit gives an analytic oracle.
    u['vol_surface']['eta']=0.;u['xi']=1e-10
    ctx=ValuationContext(underlyings=[u],corr_matrix=[[1.]],r=.03,T=.25,N=16000,model='lsv',
        local_vol_anchor=[.45],steps_per_year=frequency,state={'spot_base':[.45],'spot_mult':[.45]})
    result=run_valuation(parse_script('AT MATURITY:\n  PAY WOF'),ctx)
    assert result['lsv_calibration']['status']=='QUALIFIED'
    assert result['lsv_frozen_leverage']
    exact=.45*math.exp(-u['q']*ctx.T)
    assert result['ic95'][0]<exact<result['ic95'][1]
    assert result['surface_context']['initial_variance']==[u['v0']]
    assert result['time_axis']['steps_per_year']==frequency
    from scipy.special import ndtr
    for row in result['lsv_calibration']['underlyings'][0]['controls']:
        expiry,k=row['expiry'],row['strike']
        sd=u['sigma']*math.sqrt(expiry)
        d1=(-math.log(k)+(.03-u['q'])*expiry+.5*sd**2)/sd
        expected=(k*math.exp(-.03*expiry)*ndtr(-d1+sd)-math.exp(-u['q']*expiry)*ndtr(-d1)
                  if row['kind']=='vanille' else math.exp(-.03*expiry)*ndtr(-d1+sd))
        assert row['surface_premium']==pytest.approx(expected,abs=1e-6)



def test_unqualified_leverage_remains_a_hard_error(monkeypatch):
    from backend.app.core.payscript import lsv_leverage
    u=asset('STM','STMPA.PA',.54646136,.007388)
    monkeypatch.setattr(lsv_leverage,'_qualification_rows',lambda *a,**k:[dict(
        kind='vanille',expiry=1.,strike=.6,error_bp=11.,half_ci95_bp=1.,limit_bp=5.)])
    with pytest.raises(ValueError,match='non qualifié'):
        engine.run_mc(parse_script('AT MATURITY:\n  PAY 1'),[u],[[1.]],.03,.1,1000,
            model='lsv',spot_mult=[.5],spot_base=[.5],local_vol_anchor=[.5])


@pytest.mark.parametrize('model',['localvol','lsv'])
def test_mtf_inner_keeps_anchor_clock_and_outer_variance(model):
    u=[asset('STM','STMPA.PA',.54646136,.007388)]
    dt=np.array([.07,.03,.04,.02])
    anchor=[.45]
    local=np.arange(1,len(dt)+1)[:,None]*np.linspace(.25,.1,101)[None,:]
    grid=([local],101,math.log(.01),math.log(10.))
    if model=='lsv':grid+=((local,),)
    grid+=(anchor,)
    rng=np.random.default_rng(72)
    factors=np.empty((len(dt)+1,1,2)) if model=='lsv' else None
    spots=engine._mtf_model_paths(model,u,.03,np.eye(1),dt,2,rng,[.45],grid,factor_out=factors)
    step=2;inner=10;seed=37
    actual=engine._mtf_inner_paths(model,u,.03,np.eye(1),dt[step:],inner,seed,0,0,2,
        spots[step],factors,grid,step)
    tail=([local[step:]],*grid[1:4])
    if model=='lsv':tail+=((local[step:],),)
    tail+=(anchor,)
    initial=np.repeat(spots[step],inner,axis=1)
    variance=None if factors is None else np.repeat(factors[step],inner,axis=1)
    expected=engine._mtf_model_paths(model,u,.03,np.eye(1),dt[step:],20,
        np.random.default_rng(seed+1_000_003),initial,tail,factor_init=variance)
    np.testing.assert_array_equal(actual,expected)
    if model=='lsv':
        reset=engine._mtf_model_paths(model,u,.03,np.eye(1),dt[step:],20,
            np.random.default_rng(seed+1_000_003),initial,tail)
        assert not np.allclose(actual,reset)


def test_residual_mtf_budget_includes_the_stronger_independent_controls():
    from backend.app.api.pricing import _lsv_qualification_work
    from backend.app.core.payscript.lsv_leverage import (RESIDUAL_TRAINING_PATHS,CONTROL_PATHS,RESIDUAL_CONTROL_SEEDS)
    actual=_lsv_qualification_work(104,2,residual=True)
    assert actual==104*2*(RESIDUAL_TRAINING_PATHS+2*CONTROL_PATHS*len(RESIDUAL_CONTROL_SEEDS))
    assert actual>_lsv_qualification_work(104,2)
