"""Daily Booking restoration and real calculation progress; no live data/DB."""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as api
from backend.app.api.valuation_progress import valuation_progress_response
from backend.app.db.models import Deal, DealEvent, User, ValuationRun


@pytest.fixture
def book(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'booking.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="test", email="test@example.invalid", password_hash="unused")
        session.add(user)
        session.flush()
        strike = date.today() - timedelta(days=100)
        deal = Deal(
            user_id=user.id, reference="DAILY-1", status="actif", nominal=1000,
            price_traded=100, T=2, script_snapshot="AT MATURITY:\n  PAY WOF\n",
            trade_date=(strike - timedelta(days=1)).isoformat(),
            strike_date=strike.isoformat(), value_date=strike.isoformat(),
            maturity_date=(strike + timedelta(days=730)).isoformat(),
            underlyings_json=json.dumps([{"name": "S1", "ticker": "TK1", "s0_abs": 100}]),
            market_snapshot_json=json.dumps({
                "underlyings": [{"name": "S1", "ticker": "TK1", "sigma": 20, "q": 0, "ccy": "EUR"}],
                "r": 3, "corrMatrix": [[1]], "model": "constant",
            }),
        )
        product = api.stage_internal_product(
            session, user=user, name="Daily MtM fixture", reason="test",
            terms=api.terms_from_input({
                "script": deal.script_snapshot,
                "underlyings": [{"name": "S1", "ticker": "TK1", "ccy": "EUR"}],
                "strike_date": deal.strike_date, "value_date": deal.value_date,
                "maturity_date": deal.maturity_date, "T": deal.T,
                "payment_date": deal.maturity_date, "settlement_ccy": "EUR",
            }),
        )
        deal.product_id = product.product_id
        deal.product_terms_version = product.terms_version
        session.add(deal)
        session.flush()
        session.add(DealEvent(deal_id=deal.id, event_index=0, event_date=strike.isoformat(),
                              t_years=0, spots_json='{"S1":100}', status="observé"))
        session.commit()
        yield session, user, deal
    engine.dispose()


def add_run(session, deal, created, *, mode="realized", valuation="2026-09-17", **request):
    run = ValuationRun(
        deal_id=deal.id, user_id=deal.user_id, created_at=created, context_hash="test",
        contract_version=deal.contract_version,
        result_json=json.dumps({"mtm": 1.02, "valuation_date": valuation}),
        diagnostics_json=json.dumps({"request": {"recalibrate": mode, **request}}),
    )
    session.add(run)
    session.commit()
    return run


def test_restoration_selects_latest_compatible_run_with_local_midnight_bounds(book):
    session, user, deal = book
    add_run(session, deal, datetime(2026, 9, 16, 21, 59))  # yesterday in Berlin
    eligible = add_run(session, deal, datetime(2026, 9, 16, 22, 15))  # today in Berlin
    add_run(session, deal, datetime(2026, 9, 17, 10), mode="none")
    add_run(session, deal, datetime(2026, 9, 17, 11), valuation="2026-09-15")
    add_run(session, deal, datetime(2026, 9, 17, 12), r=4)
    add_run(session, deal, datetime(2026, 9, 17, 13), window_days=60)
    add_run(session, deal, datetime(2026, 9, 17, 22))  # tomorrow in Berlin
    kwargs = dict(created_from=datetime(2026, 9, 16, 22, tzinfo=timezone.utc),
                  created_before=datetime(2026, 9, 17, 22, tzinfo=timezone.utc),
                  valuation_date=date(2026, 9, 17), recalibrate="realized")
    runs = api.latest_mtm_runs(user, session, str(deal.id), **kwargs)
    assert [run["id"] for run in runs] == [eligible.id]
    assert len(api.list_valuation_runs(deal.id, user, session)) == 7
    # A contract amendment invalidates automatic restoration, not audit history.
    deal.contract_version += 1
    session.add(deal)
    session.commit()
    assert api.latest_mtm_runs(user, session, str(deal.id), **kwargs) == []
    assert len(api.list_valuation_runs(deal.id, user, session)) == 7


def test_restoration_keeps_access_controls(book):
    session, user, deal = book
    add_run(session, deal, datetime.utcnow())
    other = User(id=user.id + 1, username="other", email="other@example.invalid", password_hash="unused")
    assert api.latest_mtm_runs(other, session, str(deal.id)) == []
    with pytest.raises(HTTPException) as error:
        api.deal_mtm(deal.id, other, session, stream=True)
    assert error.value.status_code == 404


async def collect(response):
    return [json.loads(line) async for line in response.body_iterator]


def test_stream_matches_regular_mtm_and_records_one_run(book, monkeypatch):
    session, user, deal = book
    timeline = []

    def prices(tickers, start, end, **kwargs):
        timeline.append("prices")
        days = [date.fromisoformat(start) + timedelta(days=i)
                for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
        return {"dates": [d.isoformat() for d in days],
                "prices": {tk: [100 + (d.toordinal() % 7) * 0.1 for d in days] for tk in tickers}}

    monkeypatch.setattr(api, "load_hist_prices", prices)
    monkeypatch.setattr(api, "dividend_profile", lambda *args: {"ok": True, "yield_declared": 0.01})
    body = api.MtmRequest(recalibrate="realized", valuation_date=date.today())
    regular = api.deal_mtm(deal.id, user, session, n_paths=1000, body=body)
    response = api.deal_mtm(deal.id, user, session, n_paths=1000, body=body, stream=True)
    events = asyncio.run(collect(response))
    assert [e["phase"] for e in events if e["type"] == "progress"] == ["history", "calibration", "pricing", "saving"]
    result = events[-1]["data"]
    assert result["mtm"] == regular["mtm"]
    assert result["market_used"] == regular["market_used"]
    assert len(session.exec(select(ValuationRun)).all()) == 2  # one per explicit call
    assert result["valuation_run_id"] != regular["valuation_run_id"]

    timeline.clear()
    api._mtm_core(deal, session, 1000, body, progress=timeline.append)
    assert timeline == ["history", "prices", "calibration", "prices", "pricing"]


def test_stream_reports_market_failure_without_persisting(book, monkeypatch):
    session, user, deal = book
    monkeypatch.setattr(api, "load_hist_prices", lambda *args, **kwargs: {"error": "Cours indisponibles"})
    response = api.deal_mtm(deal.id, user, session, body=api.MtmRequest(recalibrate="realized"), stream=True)
    events = asyncio.run(collect(response))
    assert events[-1] == {"type": "error", "detail": "Cours indisponibles", "status": 422}
    assert not session.exec(select(ValuationRun)).all()


def test_progress_is_delivered_before_computation_completes():
    from threading import Event
    release = Event()

    def compute(progress):
        progress("calibration")
        assert release.wait(5), "Progress was buffered until the calculation completed"
        progress("pricing")
        return {"mtm": 1}

    async def consume():
        response = valuation_progress_response(compute)
        first = json.loads(await anext(response.body_iterator))
        assert first == {"type": "progress", "phase": "calibration"}
        release.set()
        remaining = await collect(response)
        assert remaining[-1] == {"type": "result", "data": {"mtm": 1}}

    asyncio.run(consume())
