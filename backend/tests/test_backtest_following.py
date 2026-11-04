"""Independent dated-payoff and genuine-source checks for backtest substitutions."""
from dataclasses import replace
from datetime import date
import json
import math

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.app.api import pricing
from backend.app.core.backtest_history import BacktestHistoryError
from backend.app.core.payscript.engine import eval_script_on_history
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.schemas import BacktestRequest
from backend.app.services import market_data, market_history


T = 1/365.25
DATES = ["2024-01-02", "2024-01-04", "2024-01-05", "2024-01-08"]


@pytest.fixture(autouse=True)
def isolated_prices(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("STRUCTURA_SCENARIO_MARKET", raising=False)
    market_data.vider_cache_prix()
    yield
    market_data.vider_cache_prix()


def replay(script=None, *, dates=None, prices=None, mode="following", maximum=10, **kwargs):
    return eval_script_on_history(
        script or parse_script(f"AT {T}:\n  PAY WOF\n  STOP"), dates or DATES,
        prices or {"A": [100., 120., 130., 140.]}, 0, 3*T, {}, list(prices or {"A": []}),
        history_policy=dict(mode=mode, max_delay_days=maximum, **kwargs))


def test_following_reads_the_next_actual_quote_and_dates_its_cashflow():
    result = replay()
    flow = result["cash_flows"][0]
    assert flow["cf"] == 1.2
    assert flow["requested_date"] == "2024-01-03"
    assert flow["date"] == flow["payment_date"] == "2024-01-04"
    assert flow["t"] == flow["payment_t"] == 2*T
    assert result["history_adjustments"] == [dict(ticker="A", requested_date="2024-01-03",
        effective_date="2024-01-04", delay_days=1, window_start="2024-01-02", reason="MISSING_QUOTE")]


def test_official_default_reader_keeps_its_existing_previous_close_convention():
    script = parse_script(f"AT {T}:\n  PAY WOF\n  STOP")
    result = eval_script_on_history(script, DATES, {"A": [100., 120., 130., 140.]}, 0, 3*T, {}, ["A"])
    assert result["cash_flows"][0]["cf"] == 1.
    assert result["cash_flows"][0]["date"] == "2024-01-02"
    assert "history_adjustments" not in result


def test_strict_refuses_instead_of_reusing_a_previous_or_future_price():
    with pytest.raises(BacktestHistoryError, match="Mode strict.*2024-01-03.*A"):
        replay(mode="strict")


@pytest.mark.parametrize("mode", ["strict", "following"])
def test_an_exact_observation_needs_no_substitution(mode):
    result = replay(dates=["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"], mode=mode)
    assert result["history_adjustments"] == []
    assert result["cash_flows"][0]["t"] == T


def test_realized_vol_uses_elapsed_time_instead_of_counting_a_gap_as_one_day():
    script = parse_script(f"AT {T}:\n  PAY REALVOL\n  STOP")
    result = replay(script)
    assert result["cash_flows"][0]["cf"] == pytest.approx(abs(math.log(1.2))/math.sqrt(2*T))


@pytest.mark.parametrize("days,allowed", [(10, True), (11, False)])
def test_ten_calendar_day_limit_is_inclusive(days, allowed):
    dates = ["2024-01-02", f"2024-01-{3+days:02}", "2024-02-01", "2024-02-02"]
    if allowed:
        assert replay(dates=dates)["history_adjustments"][0]["delay_days"] == 10
    else:
        with pytest.raises(BacktestHistoryError, match="11 jours calendaires.*maximum 10"):
            replay(dates=dates)


def test_following_never_reads_after_the_end_of_the_supplied_history():
    with pytest.raises(BacktestHistoryError, match="aucun cours commun suivant"):
        replay(dates=["2024-01-02"], prices={"A": [100.]})


def test_basket_keeps_one_observation_date_and_identifies_the_asset_causing_it():
    result = replay(prices={"A": [100., 120., 130., 140.], "B": [100., 90., 80., 70.]},
        observation_dates={"A": ["2024-01-02", "2024-01-03", *DATES[1:]], "B": DATES})
    assert result["cash_flows"][0]["cf"] == .9
    assert {r["effective_date"] for r in result["history_adjustments"]} == {"2024-01-04"}
    assert {r["ticker"]: r["reason"] for r in result["history_adjustments"]} == {
        "A": "COMMON_BASKET_DATE", "B": "MISSING_QUOTE"}


def test_following_retains_every_averaging_fixing_instead_of_dropping_missing_dates():
    script = resolve_constats(parse_script("CONSTAT OBS AVG\nAT OBS:\n  PAY WOF\n  STOP"),
        {"OBS": dict(date="2024-01-05", window_length="3D", window_frequency="1D")},
        anchor=date(2024, 1, 2), currency="EUR")
    result = replay(script)
    assert result["cash_flows"][0]["cf"] == pytest.approx((1.2+1.2+1.3)/3)
    assert result["history_adjustments"][0]["requested_date"] == "2024-01-03"
    with pytest.raises(BacktestHistoryError):
        replay(script, mode="strict")


def test_later_unused_dates_do_not_fail_or_enter_the_adjustment_log_after_stop():
    script = parse_script(f"AT {T}:\n  PAY 1.1\n  STOP\nAT 1:\n  PAY 99")
    assert len(replay(script)["history_adjustments"]) == 1


def test_two_dates_mapped_to_the_same_quote_keep_contractual_order_and_memory():
    script = parse_script(f"SET MEMORY = 0\nAT {T}:\n  SET MEMORY = 1\nAT {2*T}:\n  PAY MEMORY\n  STOP")
    assert replay(script)["cash_flows"][0]["cf"] == 1.


def test_payment_lag_is_preserved_without_antidating_a_following_observation():
    script = parse_script(f"AT {T}:\n  PAY 1.1\n  STOP")
    script = replace(script, events=[replace(script.events[0], payment_dates=[3*T])])
    flow = replay(script)["cash_flows"][0]
    assert flow["requested_payment_date"] == "2024-01-05"
    assert flow["payment_date"] == "2024-01-06"
    assert flow["payment_t"] == 4*T


def test_policy_cannot_be_applied_to_an_official_single_contract_replay():
    with pytest.raises(ValueError, match="réservée au backtest"):
        eval_script_on_history(parse_script("AT MATURITY:\n  PAY 1"), DATES, {"A": [100.]*4},
            0, T, {}, ["A"], origine="2024-01-02", history_policy={})


def test_common_axis_keeps_genuine_prices_and_first_dates_without_any_fill():
    series = {"A": pd.Series([100., 101., 102.], index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])),
              "B": pd.Series([200., 202.], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))}
    result = market_history.align_backtest_history(["A", "B"], series, "2020-01-01", "2024-01-04", False, {}, {})
    assert result["dates"] == ["2024-01-03", "2024-01-04"]
    assert result["prices"] == {"A": [101., 102.], "B": [200., 202.]}
    assert result["first_dates"] == {"A": "2024-01-02", "B": "2024-01-03"}
    assert result["observation_dates"]["A"][0] == "2024-01-02"


def test_verified_max_history_is_reused_without_an_older_history_fetch(monkeypatch):
    values = pd.Series([100., 120.], index=pd.to_datetime(["2024-01-02", "2024-01-12"]))
    market_history.store_history("A", values, False, "2024-01-02", "2024-01-12", full_history=True)
    class ForbiddenProvider:
        def Ticker(self, *_):
            pytest.fail("Existing raw observations must be reused")
    monkeypatch.setattr(market_data, "yf", ForbiddenProvider())
    monkeypatch.setattr(market_data, "_HAS_YF", True)
    bounds = market_history.backtest_history_bounds(["A"], "2024-01-12")
    assert bounds["available"] and bounds["start_effective"] == "2024-01-02"
    result = market_data.load_hist_prices(["A"], None, "2024-01-12", raw_history=True)
    assert result["prices"]["A"] == [100., 120.] and not result.get("error")
    # Other consumers retain the existing gap policy, independent from Following.
    assert "UNBOUNDED_HISTORY_GAP" in market_data.load_hist_prices(["A"], "2024-01-02", "2024-01-12")["error"]


@pytest.mark.parametrize("start", [None, "2024-01-02"])
def test_missing_local_data_loads_the_available_provider_history_only_at_launch(monkeypatch, start):
    calls = []
    frame = pd.DataFrame({"Close": [100., 110.]}, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    class Provider:
        def Ticker(self, ticker):
            assert ticker == "A"
            return self
        def history(self, **kwargs):
            calls.append(kwargs)
            return frame
    monkeypatch.setattr(market_data, "yf", Provider())
    monkeypatch.setattr(market_data, "_HAS_YF", True)
    assert not market_history.backtest_history_bounds(["A"], "2024-01-03")["available"]
    assert calls == []
    result = market_data.load_hist_prices(["A"], start, "2024-01-03", raw_history=True)
    assert result["start_effective"] == "2024-01-02"
    assert result["prices"] == {"A": [100., 110.]}
    assert calls == [{**({"period": "max"} if start is None else {"start": start}),
                      "end": "2024-01-04", "auto_adjust": False}]


def test_bounds_are_local_only_and_find_the_first_simultaneous_date(monkeypatch):
    values = {"A": pd.Series([100., 110.], index=pd.to_datetime(["2024-01-02", "2024-01-04"])),
              "B": pd.Series([200., 210.], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))}
    monkeypatch.setattr(market_history, "local_history", lambda tk, *_: (values[tk], {}))
    result = pricing.backtest_history_bounds_endpoint("A,B", "2024-01-04")
    assert result["first_dates"] == {"A": "2024-01-02", "B": "2024-01-03"}
    assert result["start_effective"] == "2024-01-04" and result["local_only"]


def test_raw_scenario_retains_its_label_and_independent_observation_dates(tmp_path, monkeypatch):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"provider": "SYNTHETIC_SCENARIO", "method": "Synthetic acceptance only",
        "series": {"A": {"2024-01-02": 100., "2024-01-03": 101., "2024-01-04": 102.},
                   "B": {"2024-01-02": 200., "2024-01-04": 202.}}}), encoding="utf-8")
    monkeypatch.setenv("STRUCTURA_SCENARIO_MARKET", str(path))
    monkeypatch.setenv("STRUCTURA_WORKSHOP_CHILD", "1")
    result = market_data.load_hist_prices(["A", "B"], None, "2024-01-04", raw_history=True)
    assert result["dates"] == ["2024-01-02", "2024-01-04"]
    assert "2024-01-03" in result["observation_dates"]["A"]
    assert result["price_type"] == "SYNTHETIC_RAW_CLOSE"
    assert result["provider"] == "SYNTHETIC_SCENARIO"
    assert result["warnings"][0]["code"] == "SYNTHETIC_DATA"


@pytest.mark.parametrize("changes", [{"history_mode": "preceding"}, {"max_delay_days": -1}, {"max_delay_days": 32}])
def test_request_rejects_unsupported_or_unbounded_policies(changes):
    with pytest.raises(ValueError):
        BacktestRequest(script="AT MATURITY:\n  PAY 1", underlyings=[dict(name="A", ticker="A")], corr_matrix=[[1.]], **changes)


def test_api_returns_reproducible_adjustments_and_irr_at_the_effective_payment_date(monkeypatch):
    payload = dict(dates=DATES, prices={"A": [100., 110., 120., 130.]}, observation_dates={"A": DATES})
    calls = []
    def load(*args, **kwargs):
        calls.append((args, kwargs)); return payload
    monkeypatch.setattr(pricing, "load_hist_prices", load)
    request = BacktestRequest(script=f"AT {T}:\n  PAY 1.001\n  STOP", T=T,
        underlyings=[dict(name="A", ticker="A")], corr_matrix=[[1.]], end_date="2024-01-08", freq=252)
    result = pricing.backtest_endpoint(request)
    assert calls[0][0][1] is None and calls[0][1] == {"raw_history": True, "full_history": True}
    assert result["history_policy"]["max_delay_days"] == 10
    assert result["history_policy"]["adjustment_count"] == 1
    assert result["history_policy"]["disclaimer"]
    assert result["rows"][0]["irr"] == pytest.approx(1.001**(365.25/2)-1, abs=5.1e-5)
    with pytest.raises(HTTPException) as error:
        pricing.backtest_endpoint(request.model_copy(update={"history_mode": "strict"}))
    assert error.value.status_code == 422 and "Mode strict" in error.value.detail


def test_the_only_complete_window_is_not_discarded(monkeypatch):
    monkeypatch.setattr(pricing, "load_hist_prices", lambda *a, **kw:
        dict(dates=["2024-01-02", "2024-01-03"], prices={"A": [100., 101.]}))
    request = BacktestRequest(script="AT MATURITY:\n  PAY 1.001", T=T,
        underlyings=[dict(name="A", ticker="A")], corr_matrix=[[1.]], history_mode="strict")
    assert pricing.backtest_endpoint(request)["n_windows"] == 1
