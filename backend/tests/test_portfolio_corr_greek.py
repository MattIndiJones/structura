"""Portfolio-level correlation-Greek aggregation — _aggregate_risk's new
corr_pairs bucket (portfolios.py). Pure arithmetic over already-persisted
greeks_json, same as the pre-existing per_underlying/scalar aggregation, so
no monkeypatching is needed: EUR-denominated deals make get_fx_series a
no-op (from_ccy == to_ccy short-circuits before any network call)."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import portfolios as portfolios_api
from backend.app.db.models import Deal, Portfolio

USER = SimpleNamespace(id=1)


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _add_deal(s: Session, reference: str, names_tickers: list[tuple[str, str]],
              corr_pairs: dict, nominal: float = 1_000_000.0, portfolio_id=None) -> Deal:
    deal = Deal(
        reference=reference, user_id=1, script_snapshot="AT MATURITY:\n  PAY 1.0",
        underlyings_json=json.dumps([{"name": n, "ticker": t, "s0_abs": 100.0}
                                      for n, t in names_tickers]),
        market_snapshot_json="{}",
        strike_date="2020-01-01", value_date="2020-01-01",
        maturity_date="2030-01-01", T=3.0, devise="EUR",
        nominal=nominal, price_traded=98.0, status="actif",
        portfolio_id=portfolio_id,
        greeks_json=json.dumps({"per_underlying": {}, "scalar": {}, "corr_pairs": corr_pairs}),
        greeks_computed_at=datetime.utcnow(),
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    return deal


def test_corr_pairs_bucket_same_underlying_pair_regardless_of_order(monkeypatch):
    """Deal A names its basket 'Amazon'/'LVMH' (tickers AMZN/MC.PA); deal B
    names the SAME real pair 'Sous-jacent 1'/'Sous-jacent 2' with the tickers
    reversed (MC.PA/AMZN). Both must land in one bucket, not two."""
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_KEY", {})
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_LABEL", {})
    s = _make_session()
    p = Portfolio(name="Book corr", user_id=1)
    s.add(p); s.commit(); s.refresh(p)

    _add_deal(s, "CORR-A",
              [("Amazon", "AMZN"), ("LVMH", "MC.PA")],
              {"Amazon / LVMH": 20.0},          # raw Greek, per 1.0 (100pts) of corr
              nominal=1_000_000.0, portfolio_id=p.id)
    _add_deal(s, "CORR-B",
              [("Sous-jacent 1", "MC.PA"), ("Sous-jacent 2", "AMZN")],
              {"Sous-jacent 1 / Sous-jacent 2": 10.0},
              nominal=500_000.0, portfolio_id=p.id)
    try:
        res = portfolios_api.portfolio_risk(p.id, USER, s)
        assert len(res["corr_pairs"]) == 1
        bucket = next(iter(res["corr_pairs"].values()))
        # amt = v * 0.01 * nominal (fx=1, both EUR): A -> 20*0.01*1e6=200000,
        # B -> 10*0.01*5e5=50000, summed = 250000.
        assert bucket["corr_eur"] == pytest.approx(250_000.0, abs=0.01)
        assert len(bucket["contributions"]) == 2
        refs = {c["reference"] for c in bucket["contributions"]}
        assert refs == {"CORR-A", "CORR-B"}
    finally:
        s.close()


def test_corr_pairs_distinct_pairs_stay_separate(monkeypatch):
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_KEY", {})
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_LABEL", {})
    s = _make_session()
    p = Portfolio(name="Book corr 2", user_id=1)
    s.add(p); s.commit(); s.refresh(p)

    _add_deal(s, "PAIR-1",
              [("A", "TKA"), ("B", "TKB")], {"A / B": 15.0}, portfolio_id=p.id)
    _add_deal(s, "PAIR-2",
              [("C", "TKC"), ("D", "TKD")], {"C / D": -8.0}, portfolio_id=p.id)
    try:
        res = portfolios_api.portfolio_risk(p.id, USER, s)
        assert len(res["corr_pairs"]) == 2
        totals = {b["label"]: b["corr_eur"] for b in res["corr_pairs"].values()}
        assert totals["A / B"] == pytest.approx(15.0 * 0.01 * 1_000_000.0, abs=0.01)
        assert totals["C / D"] == pytest.approx(-8.0 * 0.01 * 1_000_000.0, abs=0.01)
    finally:
        s.close()


def test_deal_with_no_basket_has_no_corr_contribution(monkeypatch):
    """A single-underlying deal's greeks_json has no corr_pairs at all — must
    not appear in the aggregate, and must not break the loop for the rest."""
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_KEY", {})
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_LABEL", {})
    s = _make_session()
    p = Portfolio(name="Book mixed", user_id=1)
    s.add(p); s.commit(); s.refresh(p)

    _add_deal(s, "VANILLA", [("UL1", "TK1")], {}, portfolio_id=p.id)
    _add_deal(s, "BASKET", [("A", "TKA"), ("B", "TKB")], {"A / B": 5.0}, portfolio_id=p.id)
    try:
        res = portfolios_api.portfolio_risk(p.id, USER, s)
        assert len(res["deals_included"]) == 2
        assert len(res["corr_pairs"]) == 1
    finally:
        s.close()
