"""Regression tests for the remediation of AUDIT_COMPLET_2026-08-02.md.

One test per defect the audit measured, asserting the number it measured.
They exist so a future change cannot quietly reopen any of them: every one of
these produced a plausible, finite, unflagged result before being fixed, which
is exactly the class of defect a green suite does not catch on its own.
"""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd
import pytest

from backend.app.api import auth as auth_api
from backend.app.api.kid import _horizon_percentiles, _mc_percentiles
from backend.app.core.amc_prices import fx_rate_to
from backend.app.core.payscript.engine import compute_irr, run_mc
from backend.app.core.payscript.parser import parse_script
from backend.app.core.var_engine import aggregate_var


UL = dict(name="S1", ticker="", ccy="EUR", sigma=0.20, q=0.0,
          v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
          alpha=0.20, beta=0.5, rho=-0.30, nu=0.40,
          sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
CORR3 = [[1.0, 0.3, 0.3], [0.3, 1.0, 0.3], [0.3, 0.3, 1.0]]
WORST_OF = "AT MATURITY\n  PAY WOF \"worst of\"\n"


def _three(rho_rS: float) -> list[dict]:
    return [dict(UL, name=f"S{i + 1}", rho_rS=rho_rS) for i in range(3)]


# ── SEC-101 — signing key ────────────────────────────────────────────

def test_signing_key_is_not_the_published_one():
    """The value that used to be compiled into auth.py must never sign again."""
    assert auth_api._SECRET != auth_api._LEAKED_SECRET
    assert len(auth_api._SECRET) >= 32


@pytest.mark.parametrize("value, reason", [
    (auth_api._LEAKED_SECRET, "the published example"),
    ("court", "shorter than 32 chars"),
])
def test_unusable_env_secret_is_refused(monkeypatch, value, reason):
    """A misconfigured key must stop the process, not be accepted silently."""
    monkeypatch.setenv("STRUCTURA_JWT_SECRET", value)
    with pytest.raises(RuntimeError):
        auth_api._load_secret()


def test_env_secret_wins_over_the_stored_file(monkeypatch):
    proper = "x" * 48
    monkeypatch.setenv("STRUCTURA_JWT_SECRET", proper)
    assert auth_api._load_secret() == proper


# ── SEC-102 — login throttling ───────────────────────────────────────

def test_login_locks_out_after_five_consecutive_failures():
    key = ("cible", "203.0.113.7")
    auth_api._attempts.clear()
    try:
        for _ in range(auth_api._MAX_FAILURES):
            auth_api._check_not_locked(key)      # still allowed
            auth_api._record_failure(key)
        with pytest.raises(Exception) as exc:
            auth_api._check_not_locked(key)
        assert getattr(exc.value, "status_code", None) == 429
    finally:
        auth_api._attempts.clear()


def test_successful_login_clears_the_counter():
    key = ("cible", "203.0.113.8")
    auth_api._attempts.clear()
    try:
        for _ in range(auth_api._MAX_FAILURES):
            auth_api._record_failure(key)
        auth_api._record_success(key)
        auth_api._check_not_locked(key)          # must not raise
    finally:
        auth_api._attempts.clear()


# ── QNT-201 — missing FX ─────────────────────────────────────────────

def test_no_conversion_needed_answers_one():
    assert fx_rate_to("EUR", "EUR") == 1.0
    assert fx_rate_to("", "EUR") == 1.0
    assert fx_rate_to(None, "EUR") == 1.0


def test_unknown_currency_answers_none_not_parity():
    """The whole defect in one assertion: an unloadable pair used to become
    1.0, booking a JPY notional at 164x its size with nothing on screen."""
    assert fx_rate_to("ZZZ", "EUR") is None


@pytest.mark.parametrize("module", ["portfolios", "shocks", "var"])
def test_no_module_still_falls_back_to_parity(module):
    import importlib
    mod = importlib.import_module(f"backend.app.api.{module}")
    with open(mod.__file__, encoding="utf-8") as fh:
        assert "fx.empty else 1.0" not in fh.read()


# ── QNT-202 — backward fill ──────────────────────────────────────────

def test_history_no_longer_backfills_before_the_first_quote():
    """A ticker starting mid-window used to receive its first known close on
    every earlier date: five fabricated flat returns here, realized vol 21.8%
    too low, and a barrier that could not be breached over the fabricated
    stretch."""
    idx = pd.date_range("2026-01-01", periods=10, freq="D")
    frame = pd.DataFrame({
        "ANCIEN": pd.Series(range(100, 110), index=idx, dtype=float),
        "NOUVEAU": pd.Series([np.nan] * 5 + [50, 55, 60, 58, 62.0], index=idx),
    }).dropna(how="all").ffill()

    prices = frame.dropna()                      # the production expression

    assert len(prices) == 5                      # pre-listing sessions dropped
    assert prices.index.min() == idx[5]
    returns = prices["NOUVEAU"].pct_change().dropna()
    assert len(returns) == 4                     # only the observable ones
    assert returns.std() == pytest.approx(0.0614, abs=1e-3)


def test_load_hist_prices_carries_no_bfill():
    from backend.app.services import market_data
    with open(market_data.__file__, encoding="utf-8") as fh:
        body = fh.read()
    assert ".ffill().bfill()" not in body


# ── QNT-120 — IRR ────────────────────────────────────────────────────

def test_total_loss_has_an_irr_of_minus_one():
    """It used to return None, so the worst window of a backtest vanished
    from the statistics computed over the survivors."""
    assert compute_irr([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 0.0}]) == -1.0


def test_near_total_loss_is_solved_not_dropped():
    irr = compute_irr([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 0.01}])
    assert irr == pytest.approx(-0.9999, abs=1e-6)


@pytest.mark.parametrize("flows, expected", [
    ([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 110.0}], 0.10),
    ([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 5.0}], -0.95),
    ([{"t": 0.0, "cf": -100.0}, {"t": 10.0, "cf": 300.0}], 0.1161231740),
    ([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 108.0}], 0.08),
])
def test_ordinary_windows_are_unchanged(flows, expected):
    assert compute_irr(flows) == pytest.approx(expected, abs=1e-8)


def test_several_sign_changes_return_none_rather_than_one_arbitrary_root():
    """-100, +250, -155 has two mathematical IRRs (13.8% and 36.2%). Reporting
    whichever Newton reached first was not a measure of anything."""
    assert compute_irr([{"t": 0.0, "cf": -100.0}, {"t": 1.0, "cf": 250.0},
                        {"t": 2.0, "cf": -155.0}]) is None


# ── QNT-116/117 — VaR quantiles ──────────────────────────────────────

@pytest.mark.parametrize("n", [20, 37, 100, 200])
def test_var_and_p5_are_one_definition(n):
    """Both estimate the 5% quantile of the same sample. They used to disagree
    (96.00 against -95.05 on 100 scenarios) with nothing saying which was it."""
    out = aggregate_var([-float(i) for i in range(1, n + 1)], confidence=0.95)
    assert out["var_eur"] == pytest.approx(-out["distribution_summary"]["p5"])


def test_var_and_es_are_exact_on_a_known_sample():
    out = aggregate_var([-float(i) for i in range(1, 101)], confidence=0.95)
    assert out["var_eur"] == 96.0            # 5th worst
    assert out["es_eur"] == 98.0             # mean of the 5 worst
    assert out["n_tail"] == 5.0
    assert out["quantile_convention"] == "empirique_inverse_cdf"


# ── QNT-113 — rate/equity correlation ────────────────────────────────

def test_rho_rS_no_longer_moves_the_equity_correlation():
    """Three assets entered at 0.30 used to come out at 0.867 when each was
    0.90 correlated to the rate factor, moving a worst-of by 7.6 points."""
    kw = dict(r=0.03, T_max=1.0, N=40000, model="constant", seed=42, sigma_r=0.01)
    script = parse_script(WORST_OF)
    flat = run_mc(script, _three(0.0), CORR3, **kw)["price"]
    tilted = run_mc(script, _three(0.7), CORR3, **kw)["price"]
    assert abs(tilted - flat) < 1e-3, f"{flat:.6f} -> {tilted:.6f}"


def test_incompatible_rate_and_equity_correlations_are_refused():
    """0.30 between assets and 0.90 each against a shared rate factor
    describes a matrix that does not exist — going through the rate alone
    already forces about 0.81 between them."""
    with pytest.raises(ValueError, match="incompatibles"):
        run_mc(parse_script(WORST_OF), _three(0.9), CORR3,
               r=0.03, T_max=1.0, N=4000, model="constant", seed=42, sigma_r=0.01)


def test_rho_rS_stays_inert_without_a_stochastic_rate():
    kw = dict(r=0.03, T_max=1.0, N=8000, model="constant", seed=42)
    script = parse_script(WORST_OF)
    assert (run_mc(script, _three(0.0), CORR3, **kw)["price"]
            == run_mc(script, _three(0.7), CORR3, **kw)["price"])


# ── QNT-105 — PRIIPs intermediate horizons ───────────────────────────

KID_AUTOCALL = """
PARAM AC_BAR = 100%  "rappel"
PARAM CPN = 8%  "coupon"
PARAM KI_BAR = 60%  "barriere KI"

AT 1, 2, 3, 4
  IF WOF >= AC_BAR
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1 "capital protege"
  PAY KI * WOF "capital a risque"
"""


def _kid_common():
    return dict(compiled=parse_script(KID_AUTOCALL), uls=[dict(UL, sigma=0.25)],
                corr=[[1.0]], r=0.03, T_run=5.0, N=20000, model="constant",
                seed=42, antithetic=True, user_params={}, yield_curve=[],
                sigma_r=0.0, a_r=0.0)


def test_intermediate_horizon_does_not_redeem_the_product():
    """At the 1-year horizon a 5-year autocall used to price at 1.0000 with a
    median gross payoff of 1.0000: the AT MATURITY block fired at the
    truncated date and repaid the capital four years early."""
    sc = _horizon_percentiles(**_kid_common(), T_cap=1.0,
                              n_outer=400, n_inner=120)
    assert abs(sc["p50"] - 1.0) > 1e-3
    assert sc["p90"] - sc["p10"] > 0.05          # no longer degenerate
    assert 0.0 < sc["terminated_pct"] < 100.0


def test_every_horizon_agrees_on_the_present_value():
    """No arbitrage: the value of the position does not depend on the date you
    choose to look at it. The rows used to disagree by 5 points and were not
    even monotone in horizon."""
    common = _kid_common()
    v1 = _horizon_percentiles(**common, T_cap=1.0, n_outer=400, n_inner=120)["pv"]
    vm = _horizon_percentiles(**common, T_cap=2.5, n_outer=400, n_inner=120)["pv"]
    vf = _mc_percentiles(**common, T_cap=5.0, floor_price=0.0)["pv"]
    assert max(v1, vm, vf) - min(v1, vm, vf) < 0.03, f"{v1:.4f}/{vm:.4f}/{vf:.4f}"


# ── KID annualisation — amounts held at the horizon ──────────────────

CERTAIN_RECALL = """
PARAM AC_BAR = 50%  "rappel quasi certain"
PARAM CPN = 8%  "coupon"

AT 1, 2, 3, 4
  IF WOF >= AC_BAR
    PAY 1 + CPN "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
"""


def _certain_common():
    """sigma=1%: recall at year 1 is as good as certain, so the right answer
    is known in closed form and the test asserts it rather than a snapshot."""
    return dict(compiled=parse_script(CERTAIN_RECALL), uls=[dict(UL, sigma=0.01)],
                corr=[[1.0]], r=0.03, T_run=5.0, N=8000, model="constant",
                seed=42, antithetic=True, user_params={}, yield_curve=[],
                sigma_r=0.0, a_r=0.0)


def test_amount_is_what_the_investor_receives():
    """No discounting and no reinvestment: 1.08 paid at year 1 is 1.08."""
    sc = _mc_percentiles(**_certain_common(), T_cap=5.0, floor_price=0.0)
    assert sc["p50"] == pytest.approx(1.08, abs=1e-4)


def test_return_is_the_irr_over_the_scenario_own_life():
    """An 8% coupon redeemed at year 1 returns 8% — whatever horizon the row
    is labelled with. `(amount/notional)^(1/T_h)` published 1.55% because the
    exponent said five years; the scenario had lived one."""
    from backend.app.api.kid import _scenario_row
    sc = _mc_percentiles(**_certain_common(), T_cap=5.0, floor_price=0.0)
    row = _scenario_row(sc, 5.0, 0.0, 0.0, 0.0)
    assert row["modere"]["ann_return"] == pytest.approx(8.0, abs=0.05)
    assert row["modere"]["life"] == pytest.approx(1.0, abs=1e-6)
    assert row["modere"]["amount"] == pytest.approx(10_800.0, abs=1.0)


@pytest.mark.parametrize("call_year", [1, 2, 3, 5])
def test_annual_coupon_gives_the_same_irr_whenever_it_is_called(call_year):
    """The property that makes the measure trustworthy: an 8% annual coupon
    yields 8% no matter which year the product redeems."""
    flows = [{"t": 0.0, "cf": -1.0}]
    flows += [{"t": float(i), "cf": 0.08} for i in range(1, call_year)]
    flows += [{"t": float(call_year), "cf": 1.08}]
    assert compute_irr(flows) == pytest.approx(0.08, abs=1e-6)


def test_each_cell_carries_the_life_it_was_annualised_over():
    """Two cells of one column can legitimately hold different horizons once
    the exponent follows the scenario. That has to be readable, or the table
    looks internally inconsistent."""
    common = _kid_common()
    sc = _horizon_percentiles(**common, T_cap=2.5, n_outer=400, n_inner=120)
    from backend.app.api.kid import _scenario_row
    row = _scenario_row(sc, 2.5, 0.0, 0.0, 0.0)
    for cell in ("stress", "defavorable", "modere", "favorable"):
        assert 0.0 < row[cell]["life"] <= 2.5 + 1e-9


def test_amount_and_return_come_from_the_same_scenario():
    """Reading the percentile of amounts and the percentile of returns apart
    would pair one scenario's payout with another one's holding period."""
    sc = _mc_percentiles(**_kid_common(), T_cap=5.0, floor_price=0.0)
    for key in ("p1", "p10", "p50", "p90"):
        cell = sc["scenarios"][key]
        assert cell["amount"] == pytest.approx(sum(f["cf"] for f in cell["flows"]))


def test_per_path_flows_stay_opt_in():
    """Dated flows are the only output growing with the number of flows."""
    script = parse_script("AT MATURITY\n  PAY 1.0 \"zc\"\n")
    kw = dict(underlyings=[dict(UL)], corr_matrix=[[1.0]], r=0.03, T_max=2.0,
              N=2000, model="constant", seed=42)
    assert "path_flows" not in run_mc(script, **kw)
    out = run_mc(script, **kw, per_path_flows=True)
    assert out["path_flows"][0] == [(pytest.approx(2.0), pytest.approx(1.0))]


def test_uncertainty_widens_with_the_horizon():
    common = _kid_common()
    v1 = _horizon_percentiles(**common, T_cap=1.0, n_outer=400, n_inner=120)
    vm = _horizon_percentiles(**common, T_cap=2.5, n_outer=400, n_inner=120)
    assert (v1["p90"] - v1["p1"]) < (vm["p90"] - vm["p1"])


@pytest.mark.parametrize("extra", [
    {"yield_curve": [{"t": 1.0, "r": 0.03}]},
    {"sigma_r": 0.01},
])
def test_intermediate_horizons_refuse_what_they_cannot_price(extra):
    """The residual repricing runs off a scalar rate. Absorbing a curve would
    put two rate conventions in one regulatory document."""
    common = _kid_common()
    common.update(extra)
    with pytest.raises(ValueError):
        _horizon_percentiles(**common, T_cap=1.0, n_outer=100, n_inner=50)


# ── MTF — distribution conditionnelle à la survie ────────────────────

MTF_AUTOCALL = """
PARAM AC_BAR = 100%  "rappel"
PARAM CPN = 8%  "coupon"
PARAM KI_BAR = 60%  "barriere KI"

AT 1, 2, 3
  IF WOF >= AC_BAR
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1 "capital protege"
  PAY KI * WOF "capital a risque"
"""


def _mtf():
    from backend.app.core.payscript.engine import run_mark_to_future
    return run_mark_to_future(
        parse_script(MTF_AUTOCALL), [dict(UL, sigma=0.25)], [[1.0]], r=0.03,
        T_max=3.0, main_price=96.7, model="constant",
        n_outer=800, n_inner=150, n_dates=5, seed=42, user_params={})


def test_recalled_paths_leave_the_sample_instead_of_marking_zero():
    """Marking dead contracts at 0 put them at the bottom of the distribution,
    so the published P05 was made of products that had just paid ~108% and
    finished — while the genuinely worst outcome, a live product deep under
    its barrier, sat in the middle of the fan. The chart hid its own tail."""
    for row in _mtf()["results"]:
        if row["stats"] is None:
            continue
        assert row["stats"]["p05"] > 1.0, row["t"]
        assert row["stats"]["p50"] > 1.0, row["t"]
        assert row["n_alive"] == sum(row["alive"])


def test_surviving_marks_decline_as_the_bad_scenarios_accumulate():
    """A surviving path is one that never reached its call barrier. The worst
    of them drift towards the terminal worst-of, so the conditional P05 must
    decrease with the horizon."""
    p05 = [r["stats"]["p05"] for r in _mtf()["results"] if r["stats"]]
    assert p05 == sorted(p05, reverse=True), p05


def test_a_survivor_can_still_be_worth_more_than_par():
    """Missing a call is a single-date test: the worst-of can be back above
    the barrier weeks later, with the coupon still accruing. A conditional
    distribution capped at 100 would be a bug, not prudence."""
    rows = [r for r in _mtf()["results"] if r["stats"] and r["t"] > 1.0]
    assert any(r["stats"]["p95"] > 100.0 for r in rows)


def test_no_cash_series_is_published_next_to_the_mark():
    """The "cash already received" series described the RECALLED scenarios —
    the ones now excluded from the sample — and carried an exp(r*t0) factor,
    i.e. the coupon reinvested at the risk-free rate. It documented rows
    nobody looks at while inviting the reader to add it to a mark it does not
    belong to. One screen, one quantity: the discounted mark of the contracts
    still alive."""
    for row in _mtf()["results"]:
        assert "realized_pvs" not in row


def test_no_percentile_is_published_on_a_thin_sample():
    from backend.app.core.payscript.engine import MTF_MIN_ALIVE
    for row in _mtf()["results"]:
        if row["n_alive"] < MTF_MIN_ALIVE:
            assert row["stats"] is None


# ── RFQ — re-pricing d'un AO déjà coté ───────────────────────────────

def _rfq_session():
    import json as _json
    from sqlalchemy import event as _event
    from sqlmodel import SQLModel as _SQLModel, create_engine as _ce, Session as _S
    from backend.app.db.models import Entity, User, RfqRequest, RfqQuote
    engine = _ce("sqlite://", connect_args={"check_same_thread": False})

    @_event.listens_for(engine, "connect")
    def _fk(dbapi, _rec):
        cur = dbapi.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.close()

    _SQLModel.metadata.create_all(engine)
    s = _S(engine)
    s.add(Entity(name="E")); s.commit()
    s.add(User(username="u", email="u@x", password_hash="x", role="user", entity_id=1))
    s.commit()
    params = {
        "underlyings": [
            {"name": "Microsoft", "ticker": "MSFT", "ccy": "EUR", "sigma": 0.20, "q": 0.02},
            {"name": "Apple", "ticker": "AAPL", "ccy": "EUR", "sigma": 0.24, "q": 0.01},
        ],
        "r": 0.03, "T": 4.75, "N": 20000, "model": "constant",
        "user_params": {"CPN": 0.08}, "constats": {"OBS": {"end_date": "2031-08-01"}},
        "notional": 1_060_000.0, "currency": "EUR",
        "strike_date": "2026-10-31", "value_date": "2026-10-31",
    }
    rfq = RfqRequest(reference="RFQ-T-001", name="T", user_id=1, status="retenue",
                     script_snapshot="AT MATURITY\n  PAY 1\n",
                     params_json=_json.dumps(params), model_price=98.12,
                     model_input_hash="stale")
    s.add(rfq); s.commit(); s.refresh(rfq)
    s.add(RfqQuote(rfq_id=rfq.id, provider="UBS", price=98.5)); s.commit()
    return s, rfq, params


def _me():
    from types import SimpleNamespace
    return SimpleNamespace(id=1, entity_id=1, role="user")


def test_model_price_can_be_recomputed_with_quotes_in_hand():
    """The tender freezes WHAT is being priced, never the market assumptions.
    Re-pricing used to resubmit the whole params blob rebuilt from the form —
    constats regenerated, dates re-read, user_params re-derived — which did not
    round-trip to the stored value, so the freeze fired on terms nobody had
    touched and a quoted tender could no longer be re-priced at all."""
    import json as _json
    from backend.app.api import rfq as rfq_api
    s, rfq, before = _rfq_session()

    rfq_api.update_rfq(rfq.id, rfq_api.RfqUpdate(pricing_params={
        "underlyings": [{"sigma": 0.22}, {"sigma": 0.26}],
        "r": 0.035, "N": 50000, "model": "heston",
    }), _me(), s)

    s.refresh(rfq)
    after = _json.loads(rfq.params_json)
    assert [u["sigma"] for u in after["underlyings"]] == [0.22, 0.26]
    assert (after["r"], after["N"], after["model"]) == (0.035, 50000, "heston")
    # A scalar price cannot survive an input change.
    assert rfq.model_price is None


def test_repricing_never_touches_the_contractual_identity():
    """Belt and braces: contractual keys sent through the pricing channel are
    ignored rather than applied — the freeze cannot be walked around."""
    import json as _json
    from backend.app.api import rfq as rfq_api
    s, rfq, before = _rfq_session()

    rfq_api.update_rfq(rfq.id, rfq_api.RfqUpdate(pricing_params={
        "user_params": {"CPN": 0.20}, "strike_date": "2030-01-01", "T": 1.0,
        "constats": {"OBS": {"end_date": "2028-01-01"}},
        "underlyings": [{"name": "PIRATE", "ticker": "XXX", "ccy": "USD", "sigma": 0.9}],
    }), _me(), s)

    s.refresh(rfq)
    after = _json.loads(rfq.params_json)
    for key in ("user_params", "strike_date", "value_date", "T", "constats", "notional"):
        assert after[key] == before[key], key
    ul = after["underlyings"][0]
    assert (ul["name"], ul["ticker"], ul["ccy"]) == ("Microsoft", "MSFT", "EUR")
    assert ul["sigma"] == 0.9                    # the model half does go through


def test_repricing_keeps_every_underlying_of_the_basket():
    """The old rebuild wrote `underlyings: [one]`, silently reducing a worst-of
    to its first name at every model price computation."""
    import json as _json
    from backend.app.api import rfq as rfq_api
    s, rfq, _ = _rfq_session()

    rfq_api.update_rfq(rfq.id, rfq_api.RfqUpdate(
        pricing_params={"underlyings": [{"sigma": 0.30}]}), _me(), s)

    s.refresh(rfq)
    after = _json.loads(rfq.params_json)
    assert [u["name"] for u in after["underlyings"]] == ["Microsoft", "Apple"]
    assert after["underlyings"][1]["sigma"] == 0.24      # untouched, not dropped


def test_a_genuine_term_change_is_still_refused():
    from fastapi import HTTPException
    from backend.app.api import rfq as rfq_api
    s, rfq, before = _rfq_session()
    changed = dict(before, user_params={"CPN": 0.20})

    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(rfq.id, rfq_api.RfqUpdate(params=changed), _me(), s)
    assert exc.value.status_code == 409
