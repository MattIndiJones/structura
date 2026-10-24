"""C16 acceptance: identical factors, marginal laws and explicit approximation."""
import math

import numpy as np
import pytest

from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.bridge import basket_bridge_substeps, bridge_extrema

def conditional_inputs(n=2, paths=32000, sigma=.2):
    return np.ones((2,n,paths)), np.full((1,n,paths),sigma)


def test_identical_bridges_share_extrema_and_conditional_crossings():
    spots,vol=conditional_inputs()
    low,high=engine._bridge_extrema(spots,vol,1.,np.random.default_rng(17),[[1.,1.],[1.,1.]])
    np.testing.assert_array_equal(low[:,0],low[:,1])
    np.testing.assert_array_equal(high[:,0],high[:,1])
    target=math.exp(-2*math.log(.8)**2/.2**2)
    actual=np.mean(np.min(low,axis=1)<.8)
    assert actual==pytest.approx(target,abs=.006)


@pytest.mark.parametrize("source",[
    "AT MATURITY:\n  PAY INDIC(WOF_MIN < 0.98)",
    "AT MATURITY:\n  PAY INDIC(BOF_MAX > 1.02)",
    "AT 0.5:\n  IF WOF_MIN < 0.98:\n    PAY 0.7\n    STOP\nAT MATURITY:\n  PAY WOF",
])
def test_complete_payoff_is_unchanged_when_the_same_conditional_path_is_duplicated(source,monkeypatch):
    original_bridge=engine._bridge_extrema
    def bridge(spots,vol,dt,rng,*args,**kwargs):
        return original_bridge(spots,vol,dt,np.random.default_rng(991),*args,**kwargs)
    monkeypatch.setattr(engine,"_bridge_extrema",bridge)
    def paths(ts,n,N,*args,**kwargs):
        # One pre-sampled bank of endpoint paths, shared by mono and copies.
        base=np.ones((ts+1,n,N))
        if kwargs.get("vol_out") is not None:
            kwargs["vol_out"][:]=0.
            kwargs["vol_out"][0]=.2
        return base
    monkeypatch.setattr(engine,"_simulate_gbm",paths)
    ul={"name":"A","sigma":.2,"q":0.}
    script=parse_script(source)
    mono=engine.run_mc(script,[ul],[[1.]],0.,1.,512,barrier_monitoring="continuous",per_path_flows=True)
    copies=engine.run_mc(script,[ul,{**ul,"name":"B"}],[[1.,1.],[1.,1.]],0.,1.,512,
        barrier_monitoring="continuous",per_path_flows=True)
    assert copies["price"]==mono["price"]
    assert copies["payoffs"]==mono["payoffs"]
    assert copies["path_flows"]==mono["path_flows"]


def test_zero_volatility_never_creates_a_barrier_crossing():
    spots,vol=conditional_inputs(sigma=0.)
    low,high=engine._bridge_extrema(spots,vol,1.,np.random.default_rng(1),[[1.,.5],[.5,1.]])
    np.testing.assert_array_equal(low,1.)
    np.testing.assert_array_equal(high,1.)


def test_basket_result_explicitly_labels_the_joint_approximation():
    result=engine.run_mc(parse_script("AT MATURITY:\n  PAY INDIC(WOF_MIN < .8)"),
        [{"name":"A","sigma":.2,"q":0.},{"name":"B","sigma":.2,"q":0.}],
        [[1.,.5],[.5,1.]],0.,1.,128,barrier_monitoring="continuous")
    assert result["barrier_monitoring_details"]["joint_extrema_exact"] is False
    assert result["barrier_monitoring_details"]["basket_substeps"]==64
    assert "approximatif" in result["barrier_monitoring_note"]


@pytest.mark.parametrize("rho",[-1.,-.9,0.,.5,.9,1.])
def test_each_refined_marginal_keeps_the_exact_conditional_law(rho):
    spots,vol=conditional_inputs(paths=16384)
    low,high=bridge_extrema(spots,vol,1.,np.random.default_rng(31),[[1.,rho],[rho,1.]],substeps=8)
    target=math.exp(-2*math.log(.8)**2/.2**2)
    for asset in range(2):
        assert np.mean(low[:,asset]<.8)==pytest.approx(target,abs=.007)
        assert np.mean(high[:,asset]>1/.8)==pytest.approx(target,abs=.007)
    if rho==-1.:
        np.testing.assert_allclose(low[:,0]*high[:,1],1.,rtol=2e-14,atol=0)


def test_independent_assets_match_the_union_of_two_analytic_crossings():
    spots,vol=conditional_inputs(paths=32768)
    low,_=bridge_extrema(spots,vol,1.,np.random.default_rng(19),np.eye(2),substeps=8)
    p=math.exp(-2*math.log(.8)**2/.2**2)
    assert np.mean(np.min(low,axis=1)<.8)==pytest.approx(1-(1-p)**2,abs=.007)


@pytest.mark.parametrize("sigma_r,rho_rS",[(0.,0.),(.02,0.),(.02,.8)])
def test_perfect_asset_factors_remain_identical_with_c15_rates(sigma_r,rho_rS,monkeypatch):
    observed=[]
    original=engine._simulate_gbm
    def capture(*args,**kwargs):
        result=original(*args,**kwargs)
        observed.append(result.copy())
        return result
    monkeypatch.setattr(engine,"_simulate_gbm",capture)
    ul={"name":"A","sigma":.2,"q":0.,"rho_rS":rho_rS}
    engine.run_mc(parse_script("AT MATURITY:\n  PAY INDIC(WOF_MIN < .8)"),
        [ul,{**ul,"name":"B"}],[[1.,1.],[1.,1.]],.03,1.,64,
        sigma_r=sigma_r,barrier_monitoring="continuous")
    assert observed
    for paths in observed:
        np.testing.assert_array_equal(paths[:,0],paths[:,1])


@pytest.mark.parametrize("rho,refinement",[(0.,64),(.5,64),(.7,256),(.9,256),(.99,1024)])
def test_refinement_policy_is_explicit(rho,refinement):
    assert basket_bridge_substeps([[1.,rho],[rho,1.]])==refinement


@pytest.mark.parametrize("model,rho,n,sigma_r",[
    ("constant",.9999,2,0.),("constant",.5,3,0.),
    ("heston",.5,2,0.),("sabr",.5,2,0.),("localvol",.5,2,0.),("lsv",.5,2,0.),
    ("constant",.5,2,.02),
])
def test_unqualified_basket_domains_are_refused_without_changing_monitoring(model,rho,n,sigma_r):
    ul={"name":"A","sigma":.2,"q":0.}
    matrix=np.full((n,n),rho);np.fill_diagonal(matrix,1.)
    with pytest.raises(ValueError,match="non qualifié"):
        engine.run_mc(parse_script("AT MATURITY:\n  PAY 1"),[dict(ul) for _ in range(n)],
            matrix.tolist(),0.,1.,64,model=model,sigma_r=sigma_r,barrier_monitoring="continuous")


@pytest.mark.parametrize("entrypoint",[engine.run_mc_paths,engine.run_mc_proba])
def test_neighbor_analyses_apply_the_same_admission_rule(entrypoint):
    with pytest.raises(ValueError,match="non qualifié"):
        entrypoint(parse_script("AT MATURITY:\n  PAY 1"),
            [{"name":"A","sigma":.2},{"name":"B","sigma":.2}],
            [[1.,.9999],[.9999,1.]],0.,1.,barrier_monitoring="continuous")


@pytest.mark.parametrize("entrypoint",[engine.run_mc_paths,engine.run_mc_proba])
def test_neighbor_analyses_expose_the_same_approximation_policy(entrypoint):
    result=entrypoint(parse_script("AT MATURITY:\n  PAY 1"),
        [{"name":"A","sigma":.2},{"name":"B","sigma":.2}],
        [[1.,.5],[.5,1.]],0.,1/365.25,barrier_monitoring="continuous")
    assert result["barrier_monitoring_details"]["basket_substeps"]==64
    assert result["barrier_monitoring_details"]["qualification_tolerance_nominal"]==.001
    assert "approximatif" in result["barrier_monitoring_note"]


def test_resource_estimate_accounts_for_correlation_dependent_refinement():
    from backend.app.core.compute_budget import estimate_mc
    options=dict(operation="C16",maturity_years=1.,underlyings=2,paths=1000,
                 model="constant",continuous_monitoring=True)
    moderate=estimate_mc(**options,corr_matrix=[[1.,.5],[.5,1.]])
    strong=estimate_mc(**options,corr_matrix=[[1.,.99],[.99,1.]])
    assert strong.work_units==16*moderate.work_units
    assert strong.estimated_peak_bytes>moderate.estimated_peak_bytes


def test_correlation_greeks_keep_one_refinement_across_the_bump(monkeypatch):
    calls=[]
    def fake(*args,**kwargs):
        calls.append(kwargs)
        return {"price":.95}
    monkeypatch.setattr(engine,"run_mc",fake)
    engine.compute_greeks(parse_script("AT MATURITY:\n  PAY 1"),
        [{"name":"A","sigma":.2},{"name":"B","sigma":.2}],
        [[1.,.49],[.49,1.]],.03,1.,2000,"constant",42,{},selected=["corr"],barrier_monitoring="continuous")
    assert len(calls)==2
    assert all(call["bridge_substeps"]==256 for call in calls)


@pytest.mark.parametrize("correlation",[None,[[1.,2.],[2.,1.]],[[1.,.3]],[[1.,float("nan")],[float("nan"),1.]]])
def test_invalid_or_missing_joint_correlations_fail_closed(correlation):
    spots,vol=conditional_inputs(paths=8)
    with pytest.raises(ValueError):
        engine._bridge_extrema(spots,vol,1.,np.random.default_rng(7),correlation)


def test_price_api_preserves_the_numeric_policy_and_warning():
    from backend.app.api.pricing import price_endpoint
    from backend.app.core.schemas import PricingRequest
    request=PricingRequest(script="AT MATURITY:\n  PAY 1",
        underlyings=[{"name":"A","ticker":"","ccy":"EUR","sigma":.2,"q":0.},
                     {"name":"B","ticker":"","ccy":"EUR","sigma":.2,"q":0.}],
        corr_matrix=[[1.,.5],[.5,1.]],r=.03,T=1/365.25,N=2000,barrier_monitoring="continuous")
    result=price_endpoint(request)
    assert result.barrier_monitoring_details["basket_substeps"]==64
    assert result.barrier_monitoring_details["per_run_error_bound"] is None
    assert "approximatif" in result.barrier_monitoring_note


def test_archived_run_identity_includes_the_bridge_source(monkeypatch):
    from pathlib import Path
    from backend.app.core.valuation_runs import engine_identity
    fingerprint=engine_identity()[1]
    original=Path.read_bytes
    def changed(path):
        content=original(path)
        return content+b"\n# Different bridge implementation\n" if path.name=="bridge.py" else content
    monkeypatch.setattr(Path,"read_bytes",changed)
    assert engine_identity()[1]!=fingerprint
