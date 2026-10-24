"""C13 acceptance: publication, official authority, atomic decisions and MtM."""
import base64
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlmodel import select
from fastapi import HTTPException

from backend.app.api import deals as api
from backend.app.core import fixing_finality as finality
from backend.app.core.deal_valuation import mtm_core
from backend.app.core.official_history import official_history
from backend.app.core.valuation_runs import stage_valuation_run, replay_valuation_run
from backend.app.db.models import AuditEvent, Deal, DealEvent, OfficialFixingVersion, ProductRevision, ValuationRun
from backend.app.services import market_data
from backend.tests.product_helpers import attach_product_to_deal
from backend.tests.test_workflow_controls import (
    _session, _deal, _events, _enable_auto_yahoo, _yahoo_closes,
    _resolve_auto_exception, _fixing_submission, OPS_MAKER,
)


def source(fetched=None, exchange="PAR", zone="Europe/Paris"):
    return {"exchange": exchange, "timezone": zone, "fetched_at": fetched or datetime.now(timezone.utc).isoformat()}


@pytest.mark.parametrize("exchange,zone,day,close", [
    ("PAR", "Europe/Paris", "2026-10-21", "2026-10-21T15:30:00+00:00"),
    ("NYQ", "America/New_York", "2026-11-27", "2026-11-27T18:00:00+00:00"),
    ("NYQ", "America/New_York", "2026-03-09", "2026-03-09T20:00:00+00:00"),
    ("NYQ", "America/New_York", "2026-03-02", "2026-03-02T21:00:00+00:00"),
    ("JPX", "Asia/Tokyo", "2026-10-21", "2026-10-21T06:30:00+00:00"),
])
def test_no_delay_but_no_intraday_bar(exchange, zone, day, close):
    clock = datetime.fromisoformat(close)
    before = clock - timedelta(seconds=1)
    assert finality.qualify_close(day, source(before.isoformat(), exchange, zone), now=before)["status"] == "WAITING_SESSION_CLOSE"
    # Exactly at close: zero added delay, provided the bar was fetched then.
    result = finality.qualify_close(day, source(close, exchange, zone), now=clock)
    assert result["qualified"] and result["eligible_at"] == close
    assert finality.qualify_close(day, source(before.isoformat(), exchange, zone), now=clock)["status"] == "PUBLICATION_UNVERIFIED"


@pytest.mark.parametrize("day,metadata,status", [
    ("2026-12-25", source(), "NON_SESSION"),
    ("2026-10-24", source(), "NON_SESSION"),
    ("2026-10-21", {}, "VENUE_UNKNOWN"),
    ("2026-10-21", source(zone="UTC"), "TIMEZONE_MISMATCH"),
    ("2026-10-21", source(fetched="2026-10-21T23:00:00"), "PUBLICATION_UNVERIFIED"),
])
def test_finality_fails_closed(day, metadata, status):
    assert finality.qualify_close(day, metadata, now=datetime(2026, 12, 31, tzinfo=timezone.utc))["status"] == status


def test_intraday_cannot_create_official_version_or_coupon(monkeypatch):
    s = _session(); d = _enable_auto_yahoo(s, _deal(s)); event = _events(s, d)[0]
    close = finality.session_calendar("XPAR", date.fromisoformat(event.event_date).year).session_close(event.event_date).to_pydatetime()
    monkeypatch.setattr(finality, "utc_now", lambda: close-timedelta(seconds=1))
    changed, diagnostic = api._auto_validate_yahoo_event(d, event, json.loads(d.underlyings_json), _yahoo_closes(d), s, 1)
    assert not changed and diagnostic["waiting_for_close"]
    assert not s.exec(select(OfficialFixingVersion)).all()
    assert event.fixing_status == "EXPECTED"
    assert json.loads(event.indicative_spots_json)=={"UL1":100.}
    assert d.status == "actif"
    monkeypatch.setattr(finality, "utc_now", lambda: close)
    data=_yahoo_closes(d)
    data["sources"]["TK1"]["fetched_at"]=close.isoformat()
    monkeypatch.setattr(api,"business_today",lambda:date.fromisoformat(event.event_date))
    changed,diagnostic=api._auto_validate_yahoo_event(d,event,json.loads(d.underlyings_json),data,s,1)
    assert changed and diagnostic is None and event.fixing_status=="VALIDATED"
    version=s.get(OfficialFixingVersion,event.current_fixing_version_id)
    proof=json.loads(base64.b64decode(version.evidence_payload_b64))
    assert proof["inputs"][0]["finality"]["qualified"]


@pytest.mark.parametrize("target,accepted",[("2026-01-08",True),("2026-01-09",False)])
def test_three_calendar_day_carry_boundary(target,accepted):
    event=DealEvent(deal_id=1,event_date=target)
    data={"series":{"TK1":{"2026-01-05":100.}},"sources":{"TK1":source()}}
    _,_,failures,_=api._auto_yahoo_event_values(event,[{"name":"UL1","ticker":"TK1"}],data)
    assert (not failures)==accepted
    if not accepted:
        assert failures[0]["code"]=="YAHOO_CLOSE_STALE"


def test_official_automatic_fixing_survives_missing_provider_row(monkeypatch):
    s = _session(); d = _enable_auto_yahoo(s, _deal(s)); event = _events(s, d)[0]
    underlyings = json.loads(d.underlyings_json)
    assert api._auto_validate_yahoo_event(d, event, underlyings, _yahoo_closes(d), s, 1)[0]
    s.commit(); version_id = event.current_fixing_version_id
    assert api._auto_validate_yahoo_event(d, event, underlyings, {"series": {}}, s, 1) == (False, None)
    s.commit(); s.refresh(event)
    assert event.fixing_status == "VALIDATED" and event.current_fixing_version_id == version_id
    assert s.get(OfficialFixingVersion, version_id).status == "VALIDATED"
    assert s.exec(select(AuditEvent).where(AuditEvent.action == "OFFICIAL_FIXING_SOURCE_UNAVAILABLE")).first()


def test_total_outage_keeps_official_prefix_and_diagnoses_source(monkeypatch):
    s = _session(); d = _enable_auto_yahoo(s, _deal(s)); strike, maturity = _events(s, d)
    maturity.event_date = (date.today()+timedelta(days=30)).isoformat()
    s.add(maturity); s.commit()
    api._auto_validate_yahoo_event(d, strike, json.loads(d.underlyings_json), _yahoo_closes(d), s, 1)
    s.commit()
    monkeypatch.setattr(api, "load_yahoo_reference_closes", lambda *a: {"error": "offline"})
    response = api.refresh_deal_core(d, s, 1)
    assert response["monitoring_error"] == "offline"
    assert strike.fixing_status == "VALIDATED" and d.status == "actif"


def test_exception_decision_rolls_back_and_same_request_can_retry(monkeypatch):
    s = _session(); d = _enable_auto_yahoo(s, _deal(s)); event = _events(s, d)[0]
    api.update_event(d.id, event.id, _fixing_submission(event, {"UL1": 100.0}), OPS_MAKER, s)
    before = event.current_fixing_version_id
    revisions = len(s.exec(select(ProductRevision)).all())
    original = api._user_exception_lifecycle_evaluation
    monkeypatch.setattr(api, "_user_exception_lifecycle_evaluation", lambda *a: (_ for _ in ()).throw(RuntimeError("injected replay failure")))
    with pytest.raises(RuntimeError, match="injected replay"):
        _resolve_auto_exception(s, d, event)
    s.refresh(event)
    assert event.current_fixing_version_id == before
    assert len(s.exec(select(OfficialFixingVersion)).all()) == 1
    assert len(s.exec(select(ProductRevision)).all()) == revisions
    assert s.get(OfficialFixingVersion, before).status == "RECEIVED"
    monkeypatch.setattr(api, "_user_exception_lifecycle_evaluation", original)
    _resolve_auto_exception(s, d, event)
    assert event.fixing_status == "VALIDATED" and event.current_fixing_version_id != before


def coupon_deal():
    s = _session()
    script = """PARAM CPN = 10%
PARAM BAR = 80%
AT 1, 2, 3:
  SET DUE = DUE + CPN
  IF WOF >= BAR:
    PAY DUE
    SET DUE = 0
AT MATURITY:
  PAY 1
"""
    d = Deal(reference="C13-CPN", user_id=1, entity_id=7, script_snapshot=script,
        underlyings_json=json.dumps([{"name":"UL1", "ticker":"TK1", "ccy":"EUR"}]),
        market_snapshot_json=json.dumps({"underlyings":[{"name":"UL1", "ticker":"TK1", "sigma":20., "q":0.}], "r":0., "model":"constant"}),
        trade_date="2025-01-06", strike_date="2025-01-06", value_date="2025-01-06",
        maturity_date="2028-01-06", payment_date="2028-01-10", T=3., devise="EUR",
        fixing_policy="AUTO_YAHOO", nominal=1_000_000, price_traded=100.)
    attach_product_to_deal(s, d); s.add(d); s.commit(); s.refresh(d)
    for i, (day, t) in enumerate([("2025-01-06",0.),("2026-01-06",1.)]):
        s.add(DealEvent(deal_id=d.id, event_index=i, event_date=day, t_years=t))
    s.commit()
    data = {"series":{"TK1":{"2025-01-06":100.,"2026-01-06":90.}}, "sources":{"TK1":source()}}
    for event in _events(s, d):
        assert api._auto_validate_yahoo_event(d, event, json.loads(d.underlyings_json), data, s, 1)[0]
    s.commit()
    return s, d


def test_mtm_uses_official_90_for_coupon_not_provider_40():
    s, d = coupon_deal()
    def prices(*a):
        return {"dates":["2025-01-06","2026-01-06","2026-01-07"], "prices":{"TK1":[100.,40.,40.]}}
    payload, ctx = mtm_core(d, s, 128, asof=date(2026,1,7), load_prices=prices,
                           dividend_loader=lambda *a, **k: {"ok":False})
    assert sum(cf["cf"] for cf in payload["realized_cash_flows"]) == pytest.approx(.1)
    assert ctx["state"]["memo"].get("DUE", 0.) == 0.
    assert ctx["norm_spots"] == [.4]
    ledger = payload["market_used"]["data"]["fixing_registry"]
    assert len(ledger["official_fixings"]) == 2
    assert ctx["prices"]["TK1"][1] == 90.


def test_pending_version_is_not_a_provider_fallback():
    s, d = coupon_deal(); event = _events(s,d)[-1]
    version = s.get(OfficialFixingVersion,event.current_fixing_version_id)
    version.status = "RECEIVED"; s.add(version); s.commit()
    with pytest.raises(HTTPException) as exc:
        official_history(s,d,_events(s,d),{"TK1":[40.]},[event.event_date],date(2026,1,7))
    assert exc.value.detail["code"] == "OFFICIAL_FIXING_PENDING"


def test_unversioned_candidate_is_never_a_legacy_strike_reference():
    s=_session(); d=_deal(s); event=_events(s,d)[0]
    event.data_category="FIXING_CANDIDATE"; event.spots_json='{"UL1":100}'
    with pytest.raises(HTTPException) as exc:
        official_history(s,d,[event],{"TK1":[40.]},[event.event_date],date.today())
    assert exc.value.detail["code"]=="OFFICIAL_FIXING_PENDING"


def test_correction_invalidates_current_but_preserves_frozen_run():
    s,d = coupon_deal()
    def prices(*a):
        return {"dates":["2025-01-06","2026-01-06","2026-01-07"], "prices":{"TK1":[100.,40.,40.]}}
    def value():
        return mtm_core(d,s,128,asof=date(2026,1,7),load_prices=prices,dividend_loader=lambda *a,**kw:{"ok":False})
    payload,ctx=value()
    run,_=stage_valuation_run(s,d,1,"MTM",ctx,payload); s.commit()
    before=(run.context_json,run.result_json,run.data_versions_json)
    d.greeks_json='{"delta":42}'; s.add(d); s.commit()
    coupon=_events(s,d)[-1]
    coupon.fixing_status="MANUAL_REVIEW_REQUIRED"; s.add(coupon); s.commit()
    _resolve_auto_exception(s,d,coupon,action="REPLACE_MANUAL",spots={"UL1":70.})
    s.refresh(d); s.refresh(run)
    assert d.latest_valuation_run_id is None and d.greeks_json=="{}"
    assert (run.context_json,run.result_json,run.data_versions_json)==before
    assert s.get(ValuationRun,run.id) is not None
    assert replay_valuation_run(run)["within_tolerance"]
    corrected,corrected_ctx=value()
    assert corrected["realized_total"]==0.
    assert corrected_ctx["state"]["memo"]["DUE"]==pytest.approx(.1)
    old=json.loads(before[2])["fixing_registry"]["official_fixings"][-1]
    new=corrected["market_used"]["data"]["fixing_registry"]["official_fixings"][-1]
    assert new["version_id"]!=old["version_id"]


def test_failure_during_application_rolls_back_fixing_and_product(monkeypatch):
    s = _session(); d = _enable_auto_yahoo(s,_deal(s)); strike,maturity=_events(s,d)
    api._auto_validate_yahoo_event(d,strike,json.loads(d.underlyings_json),_yahoo_closes(d),s,1); s.commit()
    api.update_event(d.id,maturity.id,_fixing_submission(maturity,{"UL1":100.}),OPS_MAKER,s)
    pointer=maturity.current_fixing_version_id
    count=len(s.exec(select(OfficialFixingVersion)).all())
    original=api._auto_apply_lifecycle
    def broken(*a,**kw):
        result=original(*a,**kw)
        raise RuntimeError("application failure after staging")
    monkeypatch.setattr(api,"_auto_apply_lifecycle",broken)
    with pytest.raises(RuntimeError,match="application failure"):
        _resolve_auto_exception(s,d,maturity)
    s.refresh(d); s.refresh(maturity)
    assert d.status=="actif" and maturity.current_fixing_version_id==pointer
    assert len(s.exec(select(OfficialFixingVersion)).all())==count
    monkeypatch.setattr(api,"_auto_apply_lifecycle",original)
    _resolve_auto_exception(s,d,maturity)
    s.refresh(d)
    assert d.status in {"échu", "en_reglement"}


def test_reference_feed_uses_atomic_local_copy_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURA_DATA_DIR",str(tmp_path))
    calls=[]
    class Instrument:
        fast_info={"currency":"EUR"}
        def history(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame({"Close":[100.,90.]},index=pd.to_datetime(["2025-01-06","2026-01-06"]).tz_localize("Europe/Paris"))
        def get_history_metadata(self):
            return {"exchangeName":"PAR","exchangeTimezoneName":"Europe/Paris"}
    monkeypatch.setattr(market_data,"yf",SimpleNamespace(Ticker=lambda tk:Instrument()))
    monkeypatch.setattr(market_data,"_HAS_YF",True)
    first=market_data.load_yahoo_reference_closes(["TK1"],"2025-01-06","2026-01-06")
    second=market_data.load_yahoo_reference_closes(["TK1"],"2025-01-06","2026-01-06")
    assert len(calls)==1
    assert first["series"]==second["series"]
    assert second["sources"]["TK1"]["storage"]=="MARKET_REFERENCE"
