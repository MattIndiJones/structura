"""Lot 4 invariants: data type, replay units and settlement exposure."""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

from sqlmodel import Session, SQLModel, create_engine

from backend.app.api.shocks import ShockRequest, _run_shock_on_deal
from backend.app.api.portfolios import _aggregate_exposure_by_counterparty
from backend.app.core.deal_valuation import MtmRequest, mtm_core
from backend.app.core.payscript.engine import eval_script_on_history
from backend.app.core.payscript.parser import parse_script
from backend.app.core.var_engine import build_deal_scenario_base
from backend.app.db.models import Deal, DealEvent
from backend.app.services.lifecycle_alerts import refresh_book


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _deal(session: Session, *, status: str = "actif") -> Deal:
    today = date.today()
    strike = today - timedelta(days=40)
    maturity = today + timedelta(days=40)
    deal = Deal(
        reference=f"LOT4-{status}", user_id=1, entity_id=1,
        script_snapshot="AT MATURITY\n  PAY 1\n", sens="vente",
        contrepartie="Bank", devise="EUR", nominal=1_000_000,
        strike_date=strike.isoformat(), value_date=strike.isoformat(),
        maturity_date=maturity.isoformat(),
        payment_date=(maturity + timedelta(days=5)).isoformat(),
        T=(maturity - strike).days / 365.25,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1"}]),
        market_snapshot_json=json.dumps({
            "r": 3.0, "funding_spread": 0.015,
            "underlyings": [{"name": "UL1", "sigma": 20.0, "q": 0.0}],
        }),
        status=status,
    )
    session.add(deal)
    session.flush()
    session.add(DealEvent(
        deal_id=deal.id, event_index=0, event_date=strike.isoformat(),
        t_years=0.0, spots_json=json.dumps({"UL1": 100.0}), label="Strike"))
    session.commit()
    session.refresh(deal)
    return deal


def test_recalibration_uses_adjusted_history_but_contract_replay_stays_raw():
    session = _session()
    deal = _deal(session)
    calls = []
    captured = {}
    start = date.fromisoformat(deal.strike_date) - timedelta(days=2)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(45)]

    def loader(_tickers, _start, _end=None, adjusted=False):
        calls.append(adjusted)
        base = 200.0 if adjusted else 100.0
        return {"dates": dates, "prices": {"TK1": [base + i for i in range(45)]},
                "provider": "YAHOO_FINANCE",
                "price_type": "ADJUSTED_CLOSE" if adjusted else "UNADJUSTED_CLOSE",
                "adjusted": adjusted}

    def realized(prices, _tickers, _window):
        captured["first"] = prices["TK1"][0]
        return {"sigma": {"TK1": 0.2}, "corr": [[1.0]], "n_returns": 40}

    payload, _ = mtm_core(
        deal, session, 1000, MtmRequest(recalibrate="realized"),
        load_prices=loader, realized_loader=realized,
        dividend_loader=lambda *_: {"ok": False})

    assert calls == [False, True]
    assert captured["first"] == 200.0
    assert payload["market_used"]["data"]["provider"] == "YAHOO_FINANCE"
    assert payload["market_used"]["data"]["contractual_history"]["price_type"] == \
        "UNADJUSTED_CLOSE"
    assert payload["market_used"]["data"]["statistical_history"]["price_type"] == \
        "ADJUSTED_CLOSE"


def test_replay_uses_the_booked_s0_as_its_unit():
    origin = date(2026, 1, 1)
    maturity = origin + timedelta(days=30)
    compiled = parse_script("AT MATURITY\n  PAY WOF\n")
    result = eval_script_on_history(
        compiled,
        [origin.isoformat(), maturity.isoformat()],
        {"TK1": [100.0, 100.0]}, 0, 30 / 365.25, {}, ["TK1"],
        origine=origin, reference_levels={"TK1": 200.0})

    assert result is not None
    assert result["cash_flows"][-1]["cf"] == 0.5
    assert result["state"]["wof_min"] == 0.5


def test_known_maturity_cashflow_is_valued_until_payment_and_kept_in_var():
    session = _session()
    deal = _deal(session, status="en_reglement")
    today = date.today()
    deal.maturity_date = (today - timedelta(days=1)).isoformat()
    deal.payment_date = (today + timedelta(days=5)).isoformat()
    deal.settlement_amount = 0.8
    deal.realized_payout = 0.9
    session.add(deal)
    session.commit()

    payload, ctx = mtm_core(deal, session, 1000)
    expected = 0.8 * math.exp(-(0.03 + 0.015) * 5 / 365.25)

    assert payload["status"] == "en_reglement"
    assert payload["mtm"] == expected
    assert payload["unsettled_total"] == 0.8
    assert ctx["settlement_claim"] is True

    base = build_deal_scenario_base(deal, session, 1000)
    assert base["base"]["settlement_claim"] is True
    assert base["mtm_before"] == expected

    exposure = _aggregate_exposure_by_counterparty([deal], session)
    assert exposure["nominal_total_eur"] == 800_000.0
    assert exposure["by_counterparty"][0]["deals"][0]["exposure_basis"] == \
        "settlement_amount"

    spot_shock = _run_shock_on_deal(
        deal, session, 1000, ShockRequest(spot_shock_pct=-20.0))
    rate_shock = _run_shock_on_deal(
        deal, session, 1000, ShockRequest(rate_shock_bp=100.0))
    assert spot_shock["delta_pts"] == 0.0
    assert spot_shock["n_paths"] == 0
    assert rate_shock["delta_pts"] < 0.0


def test_settlement_window_closes_on_the_payment_date():
    session = _session()
    deal = _deal(session, status="en_reglement")
    deal.maturity_date = (date.today() - timedelta(days=2)).isoformat()
    deal.payment_date = date.today().isoformat()
    deal.settlement_amount = 1.0
    session.add(deal)
    session.commit()

    summary = refresh_book(session, user_id=deal.user_id)
    session.refresh(deal)

    assert summary["settled"] == 1
    assert deal.status == "échu"
