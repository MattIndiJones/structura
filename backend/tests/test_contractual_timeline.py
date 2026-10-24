"""C14: contract chronology and a shared exact simulation horizon."""
from datetime import date
from dataclasses import replace
import json

import numpy as np
import pytest
from scipy.stats import norm

from backend.app.core.payscript import engine as engine
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.deal_valuation import mtm_core
from backend.app.db.models import Deal, DealEvent
from backend.tests.product_helpers import attach_product_to_deal
from backend.tests.test_workflow_controls import _session

UL = [{"name": "A", "ticker": "TK1", "ccy": "EUR", "sigma": 0., "q": 0.}]
CORR = [[1.]]


def memory_contract(reverse=False, same_day=False):
    early, late = 30/365.25, (30 if same_day else 31)/365.25
    blocks = [f"AT {early}:\n  SET MEMORY = 1\n",
              f"AT {late}:\n  IF MEMORY >= 1:\n    PAY MEMORY\n    STOP\n"]
    return parse_script("SET MEMORY = 0\n" + "\n".join(blocks[::-1] if reverse else blocks))


@pytest.mark.parametrize("consumer", ["price", "probabilities", "paths", "profile"])
def test_distinct_dates_execute_chronologically_in_one_diffusion_step(consumer):
    values = []
    for reverse in [False, True]:
        script = memory_contract(reverse)
        if consumer == "price":
            result = engine.run_mc(script, UL, CORR, 0., 1., 16, antithetic=False)
            value = result["price"]
        elif consumer == "probabilities":
            result = engine.run_mc_proba(script, UL, CORR, 0., 1., N=16)
            value = result["price"]
        elif consumer == "paths":
            result = engine.run_mc_paths(script, UL, CORR, 0., 1., N_stat=16)
            value = result["autocall_count"]/result["total"]
        else:
            result = engine.run_payoff_profile(script, UL, CORR, 0., 1., n_pts=3)
            value = result["payoffs"][1]/100
        values.append(value)
    assert values == [1., 1.]


def test_same_date_retains_explicit_source_order():
    prices = [engine.run_mc(memory_contract(reverse, True), UL, CORR, 0., 1., 4,
                           antithetic=False)["price"] for reverse in [False, True]]
    assert prices == [1., 0.]


def test_frozen_calendar_january_31_then_february_1_matches_historical_replay():
    script=resolve_constats(parse_script("""CONSTAT EARLY
CONSTAT LATE
SET MEMORY = 0
AT LATE:
  PAY MEMORY
  STOP
AT EARLY:
  SET MEMORY = 1
AT MATURITY:
  PAY 100
"""),{"EARLY":"2028-01-31","LATE":"2028-02-01"},anchor=date(2028,1,1),currency="EUR")
    price=engine.run_mc(script,UL,CORR,0.,1.,4,antithetic=False,per_path_flows=True)
    replay=engine.eval_script_on_history(script,["2028-01-01","2028-01-31","2028-02-01"],
        {"TK1":[100.,100.,100.]},0,1.,{},["TK1"],0.,origine=date(2028,1,1))
    assert price["price"]==sum(cf["cf"] for cf in replay["cash_flows"])==1.
    assert replay["cash_flows"][0]["date"]=="2028-02-01"


def test_dated_blocks_precede_maturity_even_if_declared_after_it():
    script=parse_script("AT MATURITY:\n  PAY 100\nAT 1:\n  PAY 1\n  STOP")
    assert engine.run_mc(script,UL,CORR,0.,1.,4,antithetic=False)["price"]==1.


def test_occurrences_keep_their_rank_window_and_payment_without_mutating_terms():
    script=parse_script("PARAM() CPN = 1%\nCONSTAT() OBS\nAT OBS:\n  PAY CPN")
    early,late=30/365.25,31/365.25
    event=replace(script.events[0],dates=[late,early],ranks=[2,1],
                  window_dates=[[late],[early]],reduction="AVG",payment_dates=[late+.01,early+.02])
    script=replace(script,events=[event])
    schedule,_,payments=engine._event_schedule(script.events,52,1/52,horizon=1.)
    occurrences=list(schedule.values())[0]
    assert [e.dates for e in occurrences]==[[early],[late]]
    assert [e.ranks for e in occurrences]==[[1],[2]]
    assert [e.window_dates for e in occurrences]==[[[early]],[[late]]]
    assert list(payments.values())[0]==[early+.02,late+.01]
    assert script.events[0].dates==[late,early]
    result=engine.run_mc(script,UL,CORR,0.,1.,8,user_params={"CPN":[.1,.2]},antithetic=False)
    assert result["price"]==pytest.approx(.3)


def test_flow_times_are_contractual_and_stop_prevents_later_cashflows():
    script=memory_contract(True)
    result=engine.run_mc(script,UL,CORR,0.,1.,4,antithetic=False,per_path_flows=True)
    assert result["path_flows"][0]==[(31/365.25,1.)]
    assert next(iter(result["flux_table"].values()))["t"]==31/365.25


def test_calendar_rounding_is_admitted_without_executing_a_future_date():
    T=363/365.25
    script=parse_script(f"AT {round(T,6)}:\n  PAY 1\nAT {T+1/365.25}:\n  PAY 100")
    result=engine.run_mc(script,UL,CORR,0.,T,4,antithetic=False)
    assert result["price"]==1.
    assert next(iter(result["flux_table"].values()))["t"] <= T


@pytest.mark.parametrize("T", [1/365.25, 2/365.25, .037, .37])
def test_price_probabilities_and_paths_share_exact_terminal_time(T):
    script = parse_script("PARAM BAR = 100.05%\nAT MATURITY:\n  PAY INDIC(WOF >= BAR)")
    price = engine.run_mc(script, UL, CORR, .05, T, 16, antithetic=False)
    probabilities = engine.run_mc_proba(script, UL, CORR, .05, T, N=16)
    paths = engine.run_mc_paths(script, UL, CORR, .05, T, N_display=1, N_stat=16)
    assert price["price"] == probabilities["price"]
    assert probabilities["expected_life"] == pytest.approx(T,abs=1e-9)
    assert paths["path_data"][0]["times"][-1] == pytest.approx(T, abs=1e-9)
    assert paths["path_data"][0]["wof"][-1] == pytest.approx(np.exp(.05*T), abs=5.1e-5)


@pytest.mark.parametrize("T", [1/365.25, .037, .37])
def test_realvol_annualization_matches_dated_and_maturity_blocks(T):
    ul = [{**UL[0], "sigma": .5}]
    dated = parse_script(f"AT {T}:\n  PAY REALVOL")
    maturity = parse_script("AT MATURITY:\n  PAY REALVOL")
    price = engine.run_mc(maturity, ul, CORR, 0., T, 2000, antithetic=False)
    assert engine.run_mc(dated, ul, CORR, 0., T, 2000, antithetic=False)["price"] == price["price"]
    assert engine.run_mc_proba(maturity, ul, CORR, 0., T, N=2000)["price"] == price["price"]


def one_day_deal():
    session = _session()
    script = "AT MATURITY:\n  PAY MAX(WOF - 1, 0)"
    deal = Deal(reference="C14-ONE-DAY", user_id=1, script_snapshot=script,
        trade_date="2025-01-06", strike_date="2025-01-06", value_date="2025-01-06",
        maturity_date="2026-01-07", payment_date="2026-01-09", T=366/365.25,
        devise="EUR", nominal=1_000_000., price_traded=1.,
        underlyings_json=json.dumps(UL),
        market_snapshot_json=json.dumps({"r":0.,"model":"constant",
            "underlyings":[{"name":"A","ticker":"TK1","sigma":50.,"q":0.}]}))
    attach_product_to_deal(session,deal); session.add(deal); session.commit(); session.refresh(deal)
    session.add(DealEvent(deal_id=deal.id,event_date=deal.strike_date,t_years=0.,
                          spots_json='{"A":100.0}',status="observé"))
    session.commit()
    return session,deal


def flat_prices(tickers,start,end):
    return {"dates":["2025-01-06",end],"prices":{tk:[100.,100.] for tk in tickers}}


def test_one_day_mtm_uses_contractual_horizon_and_converges(record_property):
    session,deal = one_day_deal()
    exact_T = 1/365.25
    reference = float(2*norm.cdf(.5*np.sqrt(exact_T)/2)-1)
    measured=[]
    for N in [4000,16000,64000]:
        payload,ctx = mtm_core(deal,session,N,asof=date(2026,1,6),load_prices=flat_prices)
        assert ctx["T_remaining"] == exact_T
        assert ctx["valuation_context"]["T"] == exact_T
        assert payload["best_case"]["horizon_years"] == pytest.approx(exact_T,abs=1e-10)
        assert payload["market_used"]["time_axis"]["horizon"] == exact_T
        half_width = (payload["ic95"][1]-payload["ic95"][0])/2
        assert abs(payload["mtm"]-reference) <= 2*half_width+1e-6
        measured.append({"N":N,"mtm":payload["mtm"],"reference":reference,"half_width_95":half_width})
    assert measured[-1]["half_width_95"] < measured[0]["half_width_95"]
    record_property("one_day_call_convergence",json.dumps(measured))


@pytest.mark.parametrize("model",["constant","heston","sabr","localvol","lsv"])
def test_short_axis_is_shared_by_every_supported_model(model):
    T=1/365.25
    script=parse_script("AT MATURITY:\n  PAY MAX(WOF - 1, 0)")
    ul=[{**UL[0],"sigma":.2,"v0":.04,"theta":.04,"kappa":2.,"xi":.3,"rho_h":-.5,
         "alpha":.2,"beta":1.,"rho":-.3,"nu":.4}]
    price=engine.run_mc(script,ul,CORR,0.,T,2000,model=model,antithetic=False)
    probabilities=engine.run_mc_proba(script,ul,CORR,0.,T,N=2000,model=model)
    paths=engine.run_mc_paths(script,ul,CORR,0.,T,N_stat=16,model=model)
    assert price["price"]==probabilities["price"]
    assert price["time_axis"]==probabilities["time_axis"]==paths["time_axis"]
    assert price["time_axis"]["dt"]==T


def test_one_day_horizon_reaches_var_worker_and_offline_run(monkeypatch):
    from backend.app.core import deal_valuation,var_engine
    from backend.app.core.compute.pricers.var_scenario import price_var_scenario_job
    session,deal=one_day_deal()
    monkeypatch.setattr(deal_valuation,"business_today",lambda:date(2026,1,6))
    monkeypatch.setattr(deal_valuation,"load_hist_prices",flat_prices)
    scenario=var_engine.build_deal_scenario_base(deal,session,n_paths=2000)
    assert not scenario.get("skipped")
    assert scenario["base"]["T_remaining"]==1/365.25
    assert scenario["base"]["valuation_context"]["T"]==1/365.25
    assert price_var_scenario_job(scenario["base"])["price"]==scenario["mtm_before"]


def test_unbooked_inlife_pricing_keeps_the_same_one_day_horizon(monkeypatch):
    from backend.app.api import inlife
    from backend.tests.test_inlife_pricing import _requete,USER
    monkeypatch.setattr(inlife,"load_hist_prices",flat_prices)
    request=_requete(script="AT MATURITY:\n  PAY MAX(WOF - 1, 0)",
        r=0.,N=4000,strike_date=date(2025,1,6),value_date=date(2025,1,6),
        valuation_date=date(2026,1,6),maturity_date=date(2026,1,7),payment_date=date(2026,1,9),
        constats={},strike_levels={"A":100.},
        underlyings=[{**UL[0],"sigma":.5}])
    context=inlife.build_request_residual(request)
    assert context.T_remaining==1/365.25
    result=inlife.price_in_life(request,USER)
    assert result["price"]==pytest.approx(.0104369,abs=.0005)
    assert result["time_axis"]["horizon"]==1/365.25
