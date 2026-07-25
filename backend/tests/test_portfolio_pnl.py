"""Portfolio-level P&L explain (POST /portfolios/{id}/pnl-explain,
/portfolios/pnl-explain-global) — offline: in-memory SQLite + monkeypatched
Yahoo history, same fixture style as test_shocks.py. Uses PAY S[1] (price ==
normalized spot, closed form) so the aggregated waterfall's magnitude can be
checked precisely, plus the skip path (deal booked after date 2)."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals as deals_api
from backend.app.api import portfolios as portfolios_api
from backend.app.db.models import Deal, DealEvent, Portfolio

TODAY = date.today()
VALUE_D = TODAY - timedelta(days=400)
MATURITY = VALUE_D + timedelta(days=1096)

USER = SimpleNamespace(id=1)
BODY = deals_api.MtmExplainRequest(recalibrate="none")   # σ booking aux 2 dates


def _add_deal(s: Session, script: str, reference: str,
              nominal: float = 1_000_000.0, portfolio_id=None,
              value_date: date = VALUE_D) -> Deal:
    deal = Deal(
        reference=reference, user_id=1, script_snapshot=script,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1", "s0_abs": 100.0}]),
        market_snapshot_json=json.dumps({
            "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR",
                             "sigma": 20.0, "q": 0.0}],
            "corrMatrix": [[1.0]], "r": 3.0, "model": "constant",
            "antithetic": True, "user_params": {},
        }),
        strike_date=value_date.isoformat(), value_date=value_date.isoformat(),
        maturity_date=MATURITY.isoformat(), T=3.0, devise="EUR",
        nominal=nominal, price_traded=98.0, status="actif",
        portfolio_id=portfolio_id,
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    s.add(DealEvent(deal_id=deal.id, event_index=0,
                    event_date=value_date.isoformat(), t_years=0.0,
                    spots_json=json.dumps({"UL1": 100.0}),
                    status="observé", label="Strike"))
    s.commit()
    return deal


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _fake_prices(price_at):
    def fake(tickers, start, end):
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
        return {"dates": [d.isoformat() for d in days],
                "prices": {tk: [price_at(d) for d in days] for tk in tickers}}
    return fake


def test_portfolio_pnl_aggregates_spot_ramp(monkeypatch):
    """Two PAY S[1] deals (1M + 500k EUR), spot 100 → 110 : ΔMtM = +10 pts on
    each deal, so the aggregated spot effect must be +10% of the 1.5M total
    nominal (≈ +150k EUR), and every EUR total must telescope."""
    s = _make_session()
    p = Portfolio(name="Book PNL", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-1", nominal=1_000_000.0, portfolio_id=p.id)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-2", nominal=500_000.0, portfolio_id=p.id)

    ramp_start = TODAY - timedelta(days=60)

    def price_at(d):
        if d <= ramp_start:
            return 100.0
        return 100.0 + 10.0 * min(1.0, (d - ramp_start).days / 60.0)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(price_at))
    try:
        res = portfolios_api.pnl_explain_portfolio(p.id, USER, s, n_paths=4000, body=BODY)

        assert res["scope"] == "portfolio"
        assert len(res["contributions"]) == 2
        assert res["skipped"] == [] and res["errors"] == []
        assert res["nominal_total_eur"] == pytest.approx(1_500_000.0, abs=1.0)

        # Aggregation identities: totals == sum of per-deal contributions,
        # and the EUR waterfall telescopes to ΔMtM (up to rounding).
        assert res["pnl_total_eur"] == pytest.approx(
            sum(c["pnl_eur"] for c in res["contributions"]), abs=0.1)
        assert res["delta_mtm_eur"] == pytest.approx(
            sum(c["delta_mtm_eur"] for c in res["contributions"]), abs=0.1)
        chain = sum(st["delta_eur"] for st in res["steps"]) + res["residual_eur"]
        assert chain == pytest.approx(res["delta_mtm_eur"], abs=200.0)

        # Closed form: PAY S[1] price == normalized spot → +10% ramp gives
        # +10 pts per deal, ≈ +150k EUR total, all carried by the spot effect.
        by = {st["key"]: st["delta_eur"] for st in res["steps"]}
        assert by["vol"] == pytest.approx(0.0, abs=200.0)
        assert by["spot"] == pytest.approx(150_000.0, rel=0.05)
        assert res["pct_impact"] == pytest.approx(10.0, abs=0.5)
        assert "corr" not in by   # mono sous-jacent partout
    finally:
        s.close()


def test_portfolio_pnl_skips_unexplainable_deal(monkeypatch):
    """A deal booked after date 2 can't be explained on that window (its d1
    clamps to its value date, past d2 → 422) — it must land in `skipped`
    without aborting the rest of the book, while still counting in the
    nominal denominator (same convention as the shock endpoints)."""
    s = _make_session()
    p = Portfolio(name="Book skip", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-OK1", nominal=1_000_000.0, portfolio_id=p.id)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-OK2", nominal=500_000.0, portfolio_id=p.id)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-LATE", nominal=250_000.0,
              portfolio_id=p.id, value_date=TODAY - timedelta(days=5))

    # Non-flat closes: at d1 ≠ value date _explain_core recalibrates σ on the
    # realized window, and a flat series (vol nulle) would 422 every deal.
    monkeypatch.setattr(deals_api, "load_hist_prices",
                        _fake_prices(lambda d: 100.0 + 0.5 * (d.toordinal() % 7)))
    try:
        body = deals_api.MtmExplainRequest(
            recalibrate="none",
            date1=(TODAY - timedelta(days=60)).isoformat(),
            date2=(TODAY - timedelta(days=10)).isoformat())
        res = portfolios_api.pnl_explain_portfolio(p.id, USER, s, n_paths=4000, body=body)

        assert len(res["contributions"]) == 2
        assert len(res["skipped"]) == 1
        assert res["skipped"][0]["reference"] == "PNL-LATE"
        assert res["errors"] == []
        assert res["nominal_total_eur"] == pytest.approx(1_750_000.0, abs=1.0)
    finally:
        s.close()


def test_global_pnl_spans_portfolios(monkeypatch):
    """pnl-explain-global aggregates across every portfolio of the user."""
    s = _make_session()
    p1 = Portfolio(name="A", user_id=1)
    p2 = Portfolio(name="B", user_id=1)
    s.add(p1); s.add(p2); s.commit(); s.refresh(p1); s.refresh(p2)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-G1", nominal=1_000_000.0, portfolio_id=p1.id)
    _add_deal(s, "AT MATURITY\n  PAY S[1]", "PNL-G2", nominal=500_000.0, portfolio_id=p2.id)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(lambda d: 100.0))
    try:
        res = portfolios_api.pnl_explain_global(USER, s, n_paths=4000, body=BODY)
        assert res["scope"] == "global"
        assert len(res["contributions"]) == 2
        assert res["nominal_total_eur"] == pytest.approx(1_500_000.0, abs=1.0)
        # Flat market → the whole P&L is the (small) time effect; strict zero
        # on spot/vol thanks to CRN (same seed, same arguments).
        by = {st["key"]: st["delta_eur"] for st in res["steps"]}
        assert by["spot"] == 0.0
        assert by["vol"] == 0.0
    finally:
        s.close()
