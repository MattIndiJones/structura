"""Financial regressions for the independent vanilla audit and LSV estimator."""
import math

import numpy as np
import pytest

from backend.app.core.payscript import engine
from backend.app.core.compute_budget import ensure_budget, estimate_mc
from backend.scripts.vol_model_references import black_scholes, cev_zero_carry, sabr_spot_pde


def test_sabr_pde_reduces_to_black_scholes():
    strikes = [.6,1.,1.2]
    rows=sabr_spot_pde(strikes,[1.,4.],beta=1.,nu=0.,ds=.0125,
                       steps_per_year=200,dy=.5,y_width=.5)
    for row in rows:
        for i,k in enumerate(strikes):
            call,put,digital=black_scholes(k,row['expiry'],.2)
            assert abs(row['call'][i]-call)<.0001
            assert abs(row['put'][i]-put)<.0001
            assert abs(row['digital'][i]-digital)<.0002


def test_sabr_pde_reduces_to_absorbing_cev_including_zero_mass():
    # alpha=.6, beta=.5, 4Y: the exact law has ~25% mass at zero.
    strikes=[.2,.6,1.]
    rows=sabr_spot_pde(strikes,[1.,4.],alpha=.6,beta=.5,nu=0.,dividend=.03,
                        s_max=12.,ds=.025,dy=.5,y_width=.5)
    for row in rows:
        for i,k in enumerate(strikes):
            call,put=cev_zero_carry(k,row['expiry'],.6,.5)
            assert abs(row['call'][i]-call)<.00015
            assert abs(row['put'][i]-put)<.00015
            assert abs(row['call'][i]-row['put'][i]-math.exp(-.03*row['expiry'])*(1-k))<1e-9


def test_lsv_thin_tail_uses_neighbouring_conditional_variance():
    # Sparse low spot has high variance; far-away low-variance mass must not
    # replace E[V|S]. Only neighbouring buckets are borrowed to reach 30.
    buckets=np.array([0]*2+[1]*30+[4]*100)
    variance=np.array([.16]*2+[.09]*30+[.01]*100)
    estimated=engine._lsv_conditional_variance(buckets,variance,5)
    assert estimated[0]==pytest.approx((2*.16+30*.09)/32)
    assert np.allclose(estimated[2:32],.09)
    assert np.allclose(estimated[32:],.01)
    assert not np.isclose(estimated[0],variance.mean())


def test_lsv_conditional_variance_handles_tiny_sample_and_zero_variance():
    buckets=np.array([0,4])
    assert np.allclose(engine._lsv_conditional_variance(buckets,np.array([.1,.3]),5),.2)
    assert np.array_equal(engine._lsv_conditional_variance(buckets,np.zeros(2),5),np.zeros(2))


def test_sabr_downside_put_matches_spot_pde_reference_in_audited_regime():
    # Independently converged PDE (see the 07/10 audit), not Hagan's
    # asymptotic expansion: same spot carry, alpha and absorbing boundary.
    n,ts,dt=20000,208,1/52
    ensure_budget(estimate_mc(operation='sabr_vanilla_regression',maturity_years=4.,
                              underlyings=1,paths=n,model='sabr'))
    params=[dict(alpha=.2,beta=.5,rho=-.6,nu=.5,q=.02)]
    rng=np.random.default_rng(42)
    z=rng.standard_normal((ts,1,n)); za=rng.standard_normal(z.shape)
    payoffs=[]
    for sign in (1.,-1.):
        paths=engine._simulate_sabr(ts,1,n,dt,math.sqrt(dt),params,.03,np.eye(1),sign*z,sign*za)
        payoffs.append(math.exp(-.03*4)*np.maximum(.6-paths[-1,0],0))
        del paths
    paired=(payoffs[0]+payoffs[1])/2
    se=float(paired.std(ddof=1)/math.sqrt(n))
    assert abs(float(paired.mean())-.04017668000564815)<3*se+.0002


@pytest.mark.parametrize('seed',[42,17,93])
def test_lsv_flat_surface_does_not_create_spurious_deep_puts(seed):
    # Same tails/regime as the audit: old unconditional fallback failed all
    # three seeds (1.1--1.7 bp), despite acceptable ATM calls.
    n,ts,dt=50000,104,1/52
    ensure_budget(estimate_mc(operation='lsv_tail_regression',maturity_years=2.,
                              underlyings=1,paths=n,model='lsv'))
    params=[dict(sigma=.2,skew=0.,curvature=0.,q=.02,
                 v0=.04,theta=.04,kappa=2.,xi=.5,rho_h=-.8)]
    grid=engine._build_lv_grid(params,engine._build_rate_term([],ts,dt,.03,0.),ts,dt)
    rng=np.random.default_rng(seed)
    z=rng.standard_normal((ts,1,n))
    zv=rng.standard_normal(z.shape)
    payoffs=[]
    for sign in (1.,-1.):
        paths=engine._simulate_lsv(ts,1,n,dt,math.sqrt(dt),params,.03,np.eye(1),
                                   sign*z,sign*zv,*grid)
        payoffs.append(math.exp(-.03*2)*np.maximum(.4-paths[-1,0],0))
        del paths
    paired=(payoffs[0]+payoffs[1])/2
    reference=black_scholes(.4,2.,.2)[1]
    # Fixed economic tolerance, rather than treating interacting particles as
    # independent observations. Multiple independent seed runs are required.
    assert abs(float(paired.mean())-reference)<.00005


@pytest.mark.parametrize('model',['constant','heston','sabr','localvol','lsv'])
def test_multi_asset_marginals_use_same_dynamics_as_correlated_mono(model):
    ts,n,paths,dt=12,2,128,.1
    params=[dict(sigma=.2,q=.02,v0=.04,theta=.04,kappa=2.,xi=.5,rho_h=-.8,
                  alpha=.2,beta=.5,rho=-.6,nu=.5,skew=-.04,curvature=.02),
            dict(sigma=.27,q=.04,v0=.07,theta=.08,kappa=1.4,xi=.35,rho_h=-.3,
                  alpha=.25,beta=.7,rho=.1,nu=.3,skew=-.02,curvature=.01)]
    chol=np.linalg.cholesky([[1.,.5],[.5,1.]])
    rng=np.random.default_rng(71)
    z=rng.standard_normal((ts,n,paths)); zv=rng.standard_normal(z.shape)
    correlated=np.einsum('ij,tjp->tip',chol,z)
    rates=engine._build_rate_term([],ts,dt,.03,0.)
    grid=engine._build_lv_grid(params,rates,ts,dt)
    def simulate(p,zz,vv,ll,gg,initial):
        args=(ts,len(p),paths,dt,math.sqrt(dt),p,.03,ll,zz)
        kw=dict(spot_mult=initial,vol_add=[.01]*len(p))
        if model=='constant':
            return engine._simulate_gbm(*args,**kw)
        if model=='heston':
            return engine._simulate_heston(*args,vv,**kw)
        if model=='sabr':
            return engine._simulate_sabr(*args,vv,**kw)
        if model=='localvol':
            return engine._simulate_lv(*args,*gg,**kw)
        return engine._simulate_lsv(*args,vv,*gg,**kw)
    initial=np.array([1.02,.91])
    multi=simulate(params,z,zv,chol,grid,initial)
    for i in range(n):
        mono_grid=([grid[0][i]],*grid[1:])
        mono=simulate([params[i]],correlated[:,i:i+1],zv[:,i:i+1],np.eye(1),
                       mono_grid,initial[i:i+1])
        np.testing.assert_allclose(multi[:,i],mono[:,0],atol=2e-14,rtol=2e-14)
