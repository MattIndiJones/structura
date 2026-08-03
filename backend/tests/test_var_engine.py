"""VaR/ES engine (core/var_engine.py) — scenario generation, calibration
sign conventions, aggregation math, and the pure-data round-trip through the
compute module's var_scenario pricer. Offline: synthetic price series (no
network), same in-memory-SQLite fixture style as test_portfolio_pnl.py for
the deal-context extraction tests."""
import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals as deals_api
from backend.app.db.models import Deal, DealEvent
from backend.app.core import var_engine as ve
from backend.app.core.compute.pricers.var_scenario import price_var_scenario_job

USER = SimpleNamespace(id=1)


# ── Synthetic market data ─────────────────────────────────────────────

def _synthetic_two_ticker_history(n_calm=250, n_crisis=20, n_calm_after=30, seed=7):
    """Two tickers, near-zero correlation and low vol in calm regimes,
    strongly positive correlation and a sharp common drawdown during a
    'crisis' window in the middle — built so calibrate_comovement's sign
    (vol/corr rise when the market drops) is unambiguous, not a coin flip."""
    rng = np.random.default_rng(seed)
    calm1 = rng.normal(0.0, 0.008, size=(n_calm, 2))
    factor = rng.normal(-0.025, 0.025, size=n_crisis)
    idio = rng.normal(0.0, 0.004, size=(n_crisis, 2))
    crisis = np.column_stack([factor, factor]) + idio
    calm2 = rng.normal(0.0, 0.008, size=(n_calm_after, 2))
    rets = np.vstack([calm1, crisis, calm2])

    n = rets.shape[0] + 1
    start = date.today() - timedelta(days=round(n * 1.45))   # ~calendar days for n trading days
    dates = [(start + timedelta(days=k)).isoformat() for k in range(n)]
    px = np.zeros((n, 2))
    px[0] = [100.0, 100.0]
    for k in range(1, n):
        px[k] = px[k - 1] * np.exp(rets[k - 1])

    prices = {"TKA": [round(float(v), 4) for v in px[:, 0]],
              "TKB": [round(float(v), 4) for v in px[:, 1]]}
    return prices, dates


# ── generate_historical_scenarios ─────────────────────────────────────

def test_historical_scenarios_carry_real_dates_and_moves():
    prices, dates = _synthetic_two_ticker_history()
    scenarios = ve.generate_historical_scenarios(prices, dates, ["TKA", "TKB"], lookback_years=2.0)
    assert scenarios, "expected at least one historical scenario"
    for s in scenarios:
        assert s.method == "historical"
        assert s.label in dates      # real calendar date, not a synthetic "j-N" fallback
        assert set(s.spot_pct) == {"TKA", "TKB"}


def test_historical_scenarios_worst_day_matches_biggest_realized_drop():
    prices, dates = _synthetic_two_ticker_history()
    scenarios = ve.generate_historical_scenarios(prices, dates, ["TKA", "TKB"], lookback_years=2.0)
    worst = min(scenarios, key=lambda s: s.spot_pct["TKA"])
    # The crisis window was built with a common ~-2.5% factor — the worst
    # single-day scenario found must be a real crash, not sampling noise.
    assert worst.spot_pct["TKA"] < -3.0


def test_historical_scenarios_single_ticker_has_no_corr_shock():
    prices, dates = _synthetic_two_ticker_history()
    scenarios = ve.generate_historical_scenarios(prices, dates, ["TKA"], lookback_years=2.0)
    assert scenarios
    assert all(s.corr_delta == 0.0 for s in scenarios)


# ── calibrate_comovement sign convention ──────────────────────────────

def test_calibrate_comovement_signs_match_crisis_dynamics():
    """In the synthetic crisis, returns are strongly negative WHILE vol and
    correlation both rise — calibrate_comovement's betas must be negative
    (a negative return coincides with vol/corr going UP, i.e. slope < 0),
    and the actual scenario-facing formula in generate_parametric_scenarios
    (beta * market_move, no extra sign flip) must then predict a POSITIVE
    vol/corr shock for a simulated crash draw. This test exists specifically
    because an earlier version of this code had the sign backwards."""
    prices, dates = _synthetic_two_ticker_history()
    comove = ve.calibrate_comovement(prices, dates, ["TKA", "TKB"])
    assert comove["vol_beta"] < 0, "vol must rise as returns fall -> negative slope"
    assert comove["corr_beta"] < 0, "corr must rise as returns fall -> negative slope"

    crash_move = -0.05   # a simulated drawdown, same sign as the synthetic crisis
    predicted_vol_shock = comove["vol_beta"] * crash_move * 100.0
    predicted_corr_shock = comove["corr_beta"] * crash_move * 100.0
    assert predicted_vol_shock > 0, "a crash draw must predict a vol INCREASE"
    assert predicted_corr_shock > 0, "a crash draw must predict a correlation INCREASE"


# ── generate_parametric_scenarios ─────────────────────────────────────

def test_parametric_scenarios_shape_and_reproducibility():
    prices, dates = _synthetic_two_ticker_history()
    a = ve.generate_parametric_scenarios(prices, dates, ["TKA", "TKB"], n_scenarios=200, seed=42)
    b = ve.generate_parametric_scenarios(prices, dates, ["TKA", "TKB"], n_scenarios=200, seed=42)
    assert len(a) == 200
    assert [s.spot_pct for s in a] == [s.spot_pct for s in b], "same seed must reproduce the same draws"
    assert all(s.method == "parametric" for s in a)


def test_parametric_worst_draws_have_positive_vol_shock():
    """The draws with the biggest simulated crashes should, on average, come
    out with a positive vol shock — the calibrated co-movement actually
    doing something, not just returning zero everywhere."""
    prices, dates = _synthetic_two_ticker_history()
    scenarios = ve.generate_parametric_scenarios(prices, dates, ["TKA", "TKB"], n_scenarios=1000, seed=1)
    by_move = sorted(scenarios, key=lambda s: s.spot_pct["TKA"])
    worst_decile = by_move[:100]
    avg_vol_shock = sum(s.vol_pts["TKA"] for s in worst_decile) / len(worst_decile)
    assert avg_vol_shock > 0


# ── apply_scenario_to_deal_base ────────────────────────────────────────

def test_apply_scenario_neutral_shock_for_untouched_ticker():
    deal_base = {
        "tickers": ["TKA", "TKB"],
        "base": {"corr": [[1.0, 0.2], [0.2, 1.0]]},
    }
    scenario = ve.MarketScenario(key="k", label="l", method="historical",
                                 spot_pct={"TKA": -10.0}, vol_pts={"TKA": 5.0}, corr_delta=20.0)
    payload = ve.apply_scenario_to_deal_base(deal_base, scenario)
    assert payload["spot_mult"] == [0.9, 1.0]     # TKB untouched -> neutral 1.0
    assert payload["vol_add"] == [0.05, 0.0]
    assert payload["corr_shocked"][0][1] == pytest.approx(0.4)   # 0.2 + 20pts


# ── aggregate_var ──────────────────────────────────────────────────────

def test_aggregate_var_matches_hand_computed_percentile():
    """10 scénarios à 90 % : la queue pèse alpha*n = 1 scénario, donc la VaR est
    la pire perte et l'ES vaut cette même perte.

    L'ancienne convention prenait floor(alpha*n)+1 = 2 scénarios : elle
    annonçait une VaR de 500 et une ES de 750, en moyennant dans la queue une
    perte qui n'y appartient pas. La queue faisait ainsi 20 % de la
    distribution pour une mesure à 10 % — l'ES ressortait systématiquement plus
    douce que ce que son nom promet."""
    deltas = [-1000.0, -500.0, -100.0, 0.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0]
    res = ve.aggregate_var(deltas, confidence=0.90)
    assert res["var_eur"] == 1000.0
    assert res["es_eur"] == pytest.approx(1000.0)
    assert res["n_scenarios"] == 10
    assert res["n_tail"] == 1.0


def test_aggregate_var_queue_fractionnaire():
    """30 scénarios à 95 % : la queue pèse 1,5 scénario. La VaR est la 2e pire
    perte (la frontière de cette queue) et l'ES pondère la seconde par le reste
    fractionnaire, conformément à ES = (1/alpha)·∫VaR — ce qui garantit
    ES >= VaR par construction."""
    deltas = [-1000.0, -600.0] + [float(i) for i in range(28)]
    res = ve.aggregate_var(deltas, confidence=0.95)
    assert res["n_tail"] == 1.5
    assert res["var_eur"] == 600.0
    assert res["es_eur"] == pytest.approx((1000.0 + 0.5*600.0)/1.5, abs=0.01)
    assert res["es_eur"] >= res["var_eur"]


def test_aggregate_var_empty_input():
    res = ve.aggregate_var([])
    assert res["var_eur"] is None
    assert res["n_scenarios"] == 0


# ── build_deal_scenario_base + var_scenario pricer round-trip ─────────

def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


CALL_SCRIPT = "PARAM K = 1.0\n\nAT MATURITY\n  PAY MAX(0, S[1] - K)\n"


def _add_active_deal(s: Session, value_date, maturity, script=CALL_SCRIPT) -> Deal:
    deal = Deal(
        reference="VAR-1", user_id=1, script_snapshot=script,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1", "s0_abs": 100.0}]),
        market_snapshot_json=json.dumps({
            "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "sigma": 20.0, "q": 0.0}],
            "corrMatrix": [[1.0]], "r": 3.0, "model": "constant",
            "antithetic": True, "user_params": {"K": 1.0},
        }),
        strike_date=value_date.isoformat(), value_date=value_date.isoformat(),
        maturity_date=maturity.isoformat(), T=1.0, devise="EUR",
        nominal=1_000_000.0, price_traded=100.0, status="actif",
    )
    s.add(deal); s.commit(); s.refresh(deal)
    s.add(DealEvent(deal_id=deal.id, event_index=0, event_date=value_date.isoformat(),
                    t_years=0.0, spots_json=json.dumps({"UL1": 100.0}),
                    status="observé", label="Strike"))
    s.commit()
    return deal


def _flat_prices(tk_prices: dict, start: str, end: str):
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
    return {"dates": [d.isoformat() for d in days],
            "prices": {tk: [p] * len(days) for tk, p in tk_prices.items()}}


def test_build_deal_scenario_base_is_json_serializable_and_matches_mtm(monkeypatch):
    """The whole point of this pure-data extraction: it must survive
    json.dumps (i.e. be safe to persist in ComputeJob.payload_json / ship
    across a process boundary), and repricing it with a NEUTRAL (no-op)
    scenario through the compute module's pricer must reproduce the exact
    same MtM _mtm_core already computed — same seed, same n_paths, same
    inputs, so this is a bit-level round-trip check, not just 'close enough'."""
    value_d = date.today() - timedelta(days=100)
    maturity = value_d + timedelta(days=365)
    s = _make_session()
    deal = _add_active_deal(s, value_d, maturity)

    monkeypatch.setattr(deals_api, "load_hist_prices",
                        lambda tickers, start, end=None: _flat_prices({"TK1": 100.0}, start, end))

    base = ve.build_deal_scenario_base(deal, s, n_paths=3000)
    assert not base.get("skipped"), base.get("reason")

    # Round-trips through json exactly like ComputeJob.payload_json would.
    dumped = json.dumps(base)
    reloaded = json.loads(dumped)
    assert reloaded == base

    zero_scenario = ve.MarketScenario(key="zero", label="zero", method="historical")
    job_payload = ve.apply_scenario_to_deal_base(base, zero_scenario)
    job_payload["_meta"] = {"scenario_key": "zero"}   # harmless extra key, same as the real API path
    result = price_var_scenario_job(job_payload)

    assert result["price"] == pytest.approx(base["mtm_before"], abs=1e-6)


def test_build_deal_scenario_base_skips_matured_deal(monkeypatch):
    value_d = date.today() - timedelta(days=800)
    maturity = date.today() - timedelta(days=10)   # already past
    s = _make_session()
    deal = _add_active_deal(s, value_d, maturity)
    monkeypatch.setattr(deals_api, "load_hist_prices",
                        lambda tickers, start, end=None: _flat_prices({"TK1": 100.0}, start, end))

    base = ve.build_deal_scenario_base(deal, s, n_paths=2000)
    assert base.get("skipped") is True
    assert base.get("reason")


def test_var_scenario_pricer_reacts_to_spot_shock(monkeypatch):
    """A -20% spot shock on an ATM call must lower its price vs the
    unshocked baseline — sanity on the whole shocked round-trip, not just
    the neutral no-op case above."""
    value_d = date.today() - timedelta(days=100)
    maturity = value_d + timedelta(days=365)
    s = _make_session()
    deal = _add_active_deal(s, value_d, maturity)
    monkeypatch.setattr(deals_api, "load_hist_prices",
                        lambda tickers, start, end=None: _flat_prices({"TK1": 100.0}, start, end))

    base = ve.build_deal_scenario_base(deal, s, n_paths=3000)
    down_scenario = ve.MarketScenario(key="down", label="down", method="historical",
                                      spot_pct={"TK1": -20.0})
    shocked_payload = ve.apply_scenario_to_deal_base(base, down_scenario)
    shocked_price = price_var_scenario_job(shocked_payload)["price"]

    assert shocked_price < base["mtm_before"]
