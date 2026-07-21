"""Market-shock scenarios (POST /deals/{id}/shock, /portfolios/{id}/shock) —
offline: in-memory SQLite + monkeypatched Yahoo history, same fixture style as
test_mtm_explain.py. Uses payoffs with a known closed form (PAY S[1] and
PAY 1) so the shock's direction AND magnitude can be checked precisely,
not just its sign."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.api import shocks as shocks_api
from backend.app.db.models import Deal, DealEvent, Portfolio, ShockRun

TODAY = date.today()
VALUE_D = TODAY - timedelta(days=400)
MATURITY = VALUE_D + timedelta(days=1096)

USER = SimpleNamespace(id=1)


def _add_deal(s: Session, script: str, reference: str, n_underlyings: int = 1,
              nominal: float = 1_000_000.0, portfolio_id=None) -> tuple[Deal, list]:
    names = [f"UL{i+1}" for i in range(n_underlyings)]
    tickers = [f"TK{i+1}" for i in range(n_underlyings)]
    corr = [[1.0 if i == j else 0.3 for j in range(n_underlyings)] for i in range(n_underlyings)]
    deal = Deal(
        reference=reference, user_id=1, script_snapshot=script,
        underlyings_json=json.dumps([{"name": n, "ticker": t, "s0_abs": 100.0}
                                       for n, t in zip(names, tickers)]),
        market_snapshot_json=json.dumps({
            "underlyings": [{"name": n, "ticker": t, "ccy": "EUR", "sigma": 20.0, "q": 0.0}
                             for n, t in zip(names, tickers)],
            "corrMatrix": corr, "r": 3.0, "model": "constant",
            "antithetic": True, "user_params": {},
        }),
        strike_date=VALUE_D.isoformat(), value_date=VALUE_D.isoformat(),
        maturity_date=MATURITY.isoformat(), T=3.0, devise="EUR",
        nominal=nominal, price_traded=98.0, status="actif",
        portfolio_id=portfolio_id,
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    s.add(DealEvent(deal_id=deal.id, event_index=0,
                    event_date=VALUE_D.isoformat(), t_years=0.0,
                    spots_json=json.dumps({n: 100.0 for n in names}),
                    status="observé", label="Strike"))
    s.commit()
    return deal, tickers


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _fake_prices(tks, start, end):
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
    return {"dates": [d.isoformat() for d in days],
            "prices": {tk: [100.0 for _ in days] for tk in tks}}


def test_spot_shock_matches_closed_form(monkeypatch):
    """PAY S[1] with q=0: price == S0*exp(-qT) == spot_mult, independent of
    r/vol (drift cancels against discounting) — a -20% spot shock must move
    price by exactly -0.20 (up to MC noise)."""
    s = _make_session()
    deal, tickers = _add_deal(s, "AT MATURITY\n  PAY S[1]", "SHOCK-1")
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(spot_shock_pct=-20.0)
        res = shocks_api.shock_deal(deal.id, body, USER, s, n_paths=40000)
        assert res["mtm_before"] == pytest.approx(1.0, abs=0.02)
        assert res["delta_pts"] == pytest.approx(-0.20, abs=0.02)
    finally:
        s.close()


def test_vol_shock_has_no_first_order_effect(monkeypatch):
    """Same script — E[S_T] is vol-independent under GBM, so a vol-only
    shock must leave the price essentially unchanged (CRN keeps the noise
    on the difference itself very small)."""
    s = _make_session()
    deal, tickers = _add_deal(s, "AT MATURITY\n  PAY S[1]", "SHOCK-2")
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(vol_shock_pts=30.0)
        res = shocks_api.shock_deal(deal.id, body, USER, s, n_paths=40000)
        assert res["delta_pts"] == pytest.approx(0.0, abs=0.02)
    finally:
        s.close()


def test_rate_shock_reduces_zero_coupon_price(monkeypatch):
    """PAY 1 (pure discount bond): price == exp(-rT), strictly decreasing in
    r — a +100bp rate shock must reduce price."""
    s = _make_session()
    deal, tickers = _add_deal(s, "AT MATURITY\n  PAY 1", "SHOCK-3")
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(rate_shock_bp=100.0)
        res = shocks_api.shock_deal(deal.id, body, USER, s, n_paths=20000)
        assert res["delta_pts"] < 0
    finally:
        s.close()


def test_corr_shock_no_op_on_single_underlying(monkeypatch):
    """_shock_corr must not blow up on a 1x1 correlation matrix (nothing off
    the diagonal to shift)."""
    s = _make_session()
    deal, tickers = _add_deal(s, "AT MATURITY\n  PAY S[1]", "SHOCK-4")
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(corr_shock_pts=50.0)
        res = shocks_api.shock_deal(deal.id, body, USER, s, n_paths=4000)
        assert res["skipped"] is False
        assert res["delta_pts"] == pytest.approx(0.0, abs=0.02)
    finally:
        s.close()


def test_corr_shock_runs_on_basket(monkeypatch):
    """2-underlying worst-of basket: a correlation shock must run without
    error and produce a finite, positive price."""
    s = _make_session()
    deal, tickers = _add_deal(s, "AT MATURITY\n  PAY WOF", "SHOCK-5", n_underlyings=2)
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(corr_shock_pts=30.0)
        res = shocks_api.shock_deal(deal.id, body, USER, s, n_paths=8000)
        assert res["skipped"] is False
        assert res["mtm_after"] > 0
    finally:
        s.close()


def test_portfolio_shock_aggregates_and_persists_one_run(monkeypatch):
    """Two deals in the same portfolio: total_delta_eur must equal the sum
    of the per-deal contributions, and exactly one ShockRun row must be
    persisted for the whole book (not one per deal)."""
    s = _make_session()
    portfolio = Portfolio(name="Book test", user_id=1)
    s.add(portfolio)
    s.commit()
    s.refresh(portfolio)

    _add_deal(s, "AT MATURITY\n  PAY S[1]", "SHOCK-P1", nominal=1_000_000.0,
              portfolio_id=portfolio.id)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "SHOCK-P2", nominal=500_000.0,
              portfolio_id=portfolio.id)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices)
    try:
        body = shocks_api.ShockRequest(spot_shock_pct=-10.0)
        res = shocks_api.shock_portfolio(portfolio.id, body, USER, s, n_paths=20000)

        assert len(res["contributions"]) == 2
        assert res["total_delta_eur"] == pytest.approx(
            sum(c["delta_eur"] for c in res["contributions"]), abs=0.01)

        # Closed form: -10% spot shock on PAY S[1] (q=0) moves each deal's
        # price by exactly -0.10 -> nominal-weighted total impact is exactly
        # -10% of the portfolio's total nominal (1_000_000 + 500_000), a
        # precise check that pct_impact isn't just "some nonzero number".
        assert res["nominal_total_eur"] == pytest.approx(1_500_000.0, abs=1.0)
        assert res["pct_impact"] == pytest.approx(-10.0, abs=0.2)

        runs = s.exec(select(ShockRun).where(ShockRun.portfolio_id == portfolio.id)).all()
        assert len(runs) == 1
        assert runs[0].scope == "portfolio"
    finally:
        s.close()
