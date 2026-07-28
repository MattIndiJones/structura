"""Portfolio-level barrier proximity (GET /portfolios/barriers-global,
/portfolios/{id}/barriers) — offline: in-memory SQLite + monkeypatched Yahoo
history, same fixture style as test_portfolio_pnl.py. Reuses build_watchlist_row
(api/deals.py) under the hood, so these tests exercise the aggregation/severity
layer added in portfolios.py (sorting, KPI counts, error bucketing), not
barrier detection itself (already covered by parser tests for _analyze_monitors)."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals as deals_api
from backend.app.api import portfolios as portfolios_api
from backend.app.db.models import Deal, DealEvent, Portfolio

TODAY = date.today()
VALUE_D = TODAY - timedelta(days=100)
MATURITY = VALUE_D + timedelta(days=1096)
NEXT_OBS = TODAY + timedelta(days=20)

USER = SimpleNamespace(id=1)

KI_SCRIPT = """
PARAM M_KI_BAR = 0.6 "KI barrier"
AT MATURITY:
  IF WOF < M_KI_BAR:
    PAY 0.0
  ELSE:
    PAY 1.0
"""

AC_SCRIPT = """
PARAM M_AC_BAR = 1.0 "autocall barrier"
AT 1:
  IF WOF >= M_AC_BAR:
    PAY 1.05
    STOP
AT MATURITY:
  PAY 1.0
"""


def _add_deal(s: Session, script: str, reference: str, ticker: str,
              nominal: float = 1_000_000.0, portfolio_id=None) -> Deal:
    deal = Deal(
        reference=reference, user_id=1, script_snapshot=script,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": ticker, "s0_abs": 100.0}]),
        market_snapshot_json=json.dumps({"user_params": {}}),
        strike_date=VALUE_D.isoformat(), value_date=VALUE_D.isoformat(),
        maturity_date=MATURITY.isoformat(), T=3.0, devise="EUR",
        nominal=nominal, price_traded=98.0, status="actif",
        portfolio_id=portfolio_id,
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    s.add(DealEvent(deal_id=deal.id, event_index=0, event_date=VALUE_D.isoformat(),
                    t_years=0.0, spots_json=json.dumps({"UL1": 100.0}),
                    status="observé", label="Strike"))
    s.add(DealEvent(deal_id=deal.id, event_index=1, event_date=NEXT_OBS.isoformat(),
                    t_years=1.0, spots_json="{}", status="à venir", label="Obs. 1"))
    s.commit()
    return deal


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _fake_prices_by_ticker(ticker_spot: dict):
    """Flat price series per ticker — build_watchlist_row calls
    load_hist_prices once per deal with only that deal's own tickers, so a
    per-ticker constant is enough to control each deal's WOF precisely."""
    def fake(tickers, start, end):
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
        return {"dates": [d.isoformat() for d in days],
                "prices": {tk: [ticker_spot[tk]] * len(days) for tk in tickers}}
    return fake


def test_portfolio_barriers_ranks_by_urgency_and_counts_severity(monkeypatch):
    """3 deals: a KI close to breach (critique), an autocall just under its
    call level (attention), a KI far from danger (ok). Rows must come back
    sorted by min_gap ascending (most urgent first) and counts must bucket
    each deal by its worst barrier's direction-aware severity, not a naive
    abs(gap) read (an already-triggered autocall is never 'critique')."""
    s = _make_session()
    p = Portfolio(name="Book barrières", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, KI_SCRIPT, "KI-CRIT", "TK-KI-CRIT", portfolio_id=p.id)
    _add_deal(s, AC_SCRIPT, "AC-ATT", "TK-AC-ATT", portfolio_id=p.id)
    _add_deal(s, KI_SCRIPT, "KI-OK", "TK-KI-OK", portfolio_id=p.id)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices_by_ticker({
        "TK-KI-CRIT": 62.0,   # WOF .62 vs KI .6 -> gap +2.0pts -> critique
        "TK-AC-ATT": 97.0,    # WOF .97 vs AC 1.0 -> gap -3.0pts -> attention
        "TK-KI-OK": 100.0,    # WOF 1.0 vs KI .6 -> gap +40pts -> ok
    }))
    try:
        res = portfolios_api.portfolio_barriers(p.id, USER, s)

        assert res["scope"] == "portfolio"
        assert res["errors"] == []
        assert [r["reference"] for r in res["rows"]] == ["KI-CRIT", "AC-ATT", "KI-OK"]
        assert res["rows"][0]["min_gap"] == pytest.approx(2.0, abs=0.05)
        assert res["rows"][1]["min_gap"] == pytest.approx(3.0, abs=0.05)
        assert res["rows"][2]["min_gap"] == pytest.approx(40.0, abs=0.05)
        assert res["counts"] == {"critique": 1, "attention": 1, "ok": 1}

        crit = res["rows"][0]
        assert crit["barriers"][0]["kind"] == "ki"
        assert crit["nominal"] == 1_000_000.0
        assert crit["devise"] == "EUR"
    finally:
        s.close()


def test_barriers_global_spans_portfolios(monkeypatch):
    s = _make_session()
    p1 = Portfolio(name="A", user_id=1)
    p2 = Portfolio(name="B", user_id=1)
    s.add(p1); s.add(p2); s.commit(); s.refresh(p1); s.refresh(p2)
    _add_deal(s, KI_SCRIPT, "G1", "TK-G1", portfolio_id=p1.id)
    _add_deal(s, AC_SCRIPT, "G2", "TK-G2", portfolio_id=p2.id)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices_by_ticker({
        "TK-G1": 100.0, "TK-G2": 100.0,
    }))
    try:
        res = portfolios_api.barriers_global(USER, s)
        assert res["scope"] == "global"
        assert {r["reference"] for r in res["rows"]} == {"G1", "G2"}
    finally:
        s.close()


def test_barriers_deal_with_no_monitored_params_is_excluded(monkeypatch):
    """A vanilla script with no M_-prefixed PARAM has no barriers to show —
    it must be silently dropped from `rows`, not appear with an empty list."""
    s = _make_session()
    p = Portfolio(name="Book vanille", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, "AT MATURITY:\n  PAY MAX(S[1] - 1.0, 0)", "VANILLA", "TK-VAN", portfolio_id=p.id)

    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices_by_ticker({"TK-VAN": 100.0}))
    try:
        res = portfolios_api.portfolio_barriers(p.id, USER, s)
        assert res["rows"] == []
        assert res["counts"] == {"critique": 0, "attention": 0, "ok": 0}
    finally:
        s.close()


def test_barriers_bucket_unexpected_failure_without_aborting_book(monkeypatch):
    """If build_watchlist_row blows up for one deal (e.g. a market-data
    outage), the rest of the book must still come back — same discipline as
    _run_explain_on_book's skipped/errors bucketing."""
    s = _make_session()
    p = Portfolio(name="Book erreur", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, KI_SCRIPT, "OK-DEAL", "TK-OK", portfolio_id=p.id)
    _add_deal(s, KI_SCRIPT, "BOOM-DEAL", "TK-BOOM", portfolio_id=p.id)

    good_fake = _fake_prices_by_ticker({"TK-OK": 100.0, "TK-BOOM": 100.0})

    def flaky(tickers, start, end):
        if "TK-BOOM" in tickers:
            raise RuntimeError("yfinance timeout")
        return good_fake(tickers, start, end)

    monkeypatch.setattr(deals_api, "load_hist_prices", flaky)
    try:
        res = portfolios_api.portfolio_barriers(p.id, USER, s)
        assert [r["reference"] for r in res["rows"]] == ["OK-DEAL"]
        assert len(res["errors"]) == 1
        assert res["errors"][0]["reference"] == "BOOM-DEAL"
    finally:
        s.close()
