"""Offline surveillance and daily-run acceptance with enforced foreign keys."""
import json
from datetime import date, datetime

import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.db.models import Alert, Deal, DealEvent, SchedulerRun, User
from backend.app.services import lifecycle_alerts as service

TODAY = date(2026, 10, 20)
DATES = ["2026-10-16", "2026-10-19", "2026-10-20"]
SLOT = datetime(2026, 10, 20, 21)


@pytest.fixture
def book(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(service, "engine", engine)
    monkeypatch.setattr(service, "business_today", lambda: TODAY)
    monkeypatch.setattr(service, "_refresh_deal_handler", lambda *_: {})
    monkeypatch.setattr(service, "_watchlist_handler", lambda *_: {})
    with Session(engine) as session:
        user = User(username="c26", email="c26@example.test", password_hash="x")
        session.add(user); session.commit(); session.refresh(user)
        yield session, user
    engine.dispose()


def contract(book, reference="WATCH", observable="S[1]", count=2):
    session, user = book
    deal = Deal(reference=reference, user_id=user.id, status="actif",
        strike_date=DATES[0], value_date=DATES[0], T=1,
        script_snapshot=f"PARAM M_KI_BAR = 60%\nAT MATURITY:\n  PAY INDIC({observable} < M_KI_BAR)",
        underlyings_json=json.dumps([{"name":f"UL{i}","ticker":f"TK{i}"} for i in range(1,count+1)]),
        market_snapshot_json="{}")
    session.add(deal); session.commit(); session.refresh(deal)
    session.add(DealEvent(deal_id=deal.id,event_index=0,event_date=DATES[0],
        t_years=0,spots_json=json.dumps({f"UL{i}":100 for i in range(1,count+1)}),status="observé",label="Strike"))
    session.commit()
    return deal


def prices(monkeypatch, values, **metadata):
    monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:
        dict(dates=DATES,prices=values,**metadata))


def test_missing_first_underlying_never_becomes_second(book,monkeypatch):
    deal=contract(book)
    prices(monkeypatch,{"TK2":[100,80,90]})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["barriers"][0]["gap_pts"] is None
    assert row["wof"] is None
    assert row["underlyings"][1]["perf"] == .9


@pytest.mark.parametrize("observable,expected",[("S_MIN[1]",-10),("S_MAX[1]",40)])
def test_indexed_extrema_read_the_history(book,monkeypatch,observable,expected):
    deal=contract(book,observable=observable,count=1)
    prices(monkeypatch,{"TK1":[100,50,100]})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["barriers"][0]["gap_pts"] == expected


def test_all_failed_run_is_failed_and_same_slot_can_retry(book,monkeypatch):
    contract(book)
    def unavailable(*_): raise RuntimeError("source indisponible")
    monkeypatch.setattr(service,"_refresh_deal_handler",unavailable)
    first=service.run_scheduled_refresh(SLOT)
    assert first["status"] == "FAILED"
    monkeypatch.setattr(service,"_refresh_deal_handler",lambda *_:{})
    assert service.run_scheduled_refresh(SLOT)["status"] == "SUCCESS"
    assert service.run_scheduled_refresh(SLOT)["status"] == "SKIPPED"


def test_partial_run_has_explicit_coverage_and_is_retryable(book,monkeypatch):
    contract(book,"GOOD");contract(book,"BAD")
    def refresh(deal,session):
        if deal.reference=="BAD": raise RuntimeError("échec ciblé")
        return {}
    monkeypatch.setattr(service,"_refresh_deal_handler",refresh)
    result=service.run_scheduled_refresh(SLOT)
    assert result["status"] == "PARTIAL"
    assert result["summary"]["coverage"] == dict(total=2,succeeded=1,failed=1)
    monkeypatch.setattr(service,"_refresh_deal_handler",lambda *_:{})
    assert service.run_scheduled_refresh(SLOT)["status"] == "SUCCESS"


@pytest.mark.parametrize("observable",["WOF","BOF","BASKET()","WOF_MIN","BOF_MAX","S_MIN[1]","S_MAX[1]"])
def test_missing_member_leaves_basket_and_its_own_extrema_unavailable(book,monkeypatch,observable):
    deal=contract(book,observable=observable)
    prices(monkeypatch,{"TK2":[100,80,90]})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["barriers"][0]["gap_pts"] is None
    assert row["barriers"][0]["value_status"] == "UNAVAILABLE"
    assert row["market_coverage"]["current_available"] == 1


def test_second_index_stays_available_when_first_is_missing(book,monkeypatch):
    deal=contract(book,observable="S[2]")
    prices(monkeypatch,{"TK2":[100,80,90]})
    assert deals_api.build_watchlist_row(deal,book[0],TODAY)["barriers"][0]["gap_pts"] == 30


@pytest.mark.parametrize("values",[[100,None,100],[100,float('nan'),100],[100,0,100],[100,float('inf'),100], [100,-5,100]])
def test_a_hole_or_invalid_price_does_not_publish_an_extremum(book,monkeypatch,values):
    deal=contract(book,observable="S_MIN[1]",count=1)
    prices(monkeypatch,{"TK1":values})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["underlyings"][0]["perf"] == 1
    assert row["barriers"][0]["gap_pts"] is None


@pytest.mark.parametrize("effective,available",[("2026-10-17",True),("2026-10-16",False),("2026-10-21",False)])
def test_current_price_respects_c11_source_age(book,monkeypatch,effective,available):
    deal=contract(book,count=1)
    prices(monkeypatch,{"TK1":[100,90,90]},effective_dates={"TK1":effective})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert (row["barriers"][0]["gap_pts"] is not None) is available


def test_no_pre_strike_extremum_or_future_price_is_used(book,monkeypatch):
    deal=contract(book,observable="S_MIN[1]",count=1)
    monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:dict(
        dates=["2026-10-15",*DATES,"2026-10-21"],prices={"TK1":[1,100,90,100,2]}))
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["barriers"][0]["gap_pts"] == 30
    assert row["barriers"][0]["monitoring_basis"] == "SAMPLED_CLOSES_SINCE_STRIKE"


def test_pre_strike_spot_is_never_a_since_strike_extremum(book,monkeypatch):
    from backend.app.core.watchlist_observations import watchlist_observations
    data=watchlist_observations([{"name":"UL1","ticker":"TK1"}],{"UL1":100},
        {"dates":["2026-10-15"],"prices":{"TK1":[50]}},"2026-10-16","2026-10-16")
    assert data["wof"] == .5
    assert data["wof_min"] is None


def test_maximum_includes_the_initial_level_and_keeps_index(book,monkeypatch):
    deal=contract(book,observable="S_MAX[2]")
    prices(monkeypatch,{"TK1":[100,50,100],"TK2":[100,130,110]})
    row=deals_api.build_watchlist_row(deal,book[0],TODAY)
    assert row["barriers"][0]["gap_pts"] == 70


def test_missing_watchlist_is_failed_even_after_refresh_succeeded(book,monkeypatch):
    contract(book)
    def watch(*_): raise RuntimeError("historique illisible")
    monkeypatch.setattr(service,"_watchlist_handler",watch)
    result=service.run_scheduled_refresh(SLOT)
    assert result["status"] == "FAILED"
    assert result["summary"]["refreshed"] == 1
    assert result["summary"]["coverage"]["succeeded"] == 0
    assert result["summary"]["results"][0]["stage"] == "watchlist"


def test_unavailable_barrier_is_visible_in_run_coverage(book,monkeypatch):
    contract(book)
    monkeypatch.setattr(service,"_watchlist_handler",lambda *_:dict(barriers=[
        dict(name="M_KI_BAR",kind="ki",observable="S[1]",gap_pts=None,value_status="UNAVAILABLE")]))
    result=service.run_scheduled_refresh(SLOT)
    assert result["status"] == "FAILED"
    assert "S[1]" in result["summary"]["errors"][0]


def test_rollback_discards_dirty_failed_deal_and_continues(book,monkeypatch):
    session,_=book
    bad=contract(book,"BAD");contract(book,"GOOD")
    def refresh(deal,session):
        if deal.reference=="BAD":
            deal.status="échu";session.add(deal)
            raise RuntimeError("échec après mutation")
        return {}
    monkeypatch.setattr(service,"_refresh_deal_handler",refresh)
    summary=service.refresh_book(session)
    assert summary["status"] == "PARTIAL"
    assert session.get(Deal,bad.id).status == "actif"
    assert summary["results"][1]["status"] == "SUCCESS"


def test_settlement_failure_is_per_deal_and_does_not_leave_audit_or_status(book,monkeypatch):
    from backend.app.db.models import AuditEvent
    session,_=book
    bad=contract(book,"BAD");contract(book,"GOOD")
    bad.status="en_reglement";bad.settlement_date=TODAY.isoformat();session.add(bad);session.commit()
    real=service.record_audit_event
    def broken(*a,**k):
        real(*a,**k)
        raise RuntimeError("audit incomplet")
    monkeypatch.setattr(service,"record_audit_event",broken)
    summary=service.refresh_book(session)
    assert summary["status"] == "PARTIAL"
    assert summary["settled"] == 0
    assert session.get(Deal,bad.id).status == "en_reglement"
    assert session.exec(select(AuditEvent)).all() == []


def test_legacy_false_success_with_errors_can_be_reclaimed(book):
    session,_=book
    session.add(SchedulerRun(job_key=service.SCHEDULER_JOB_KEY,scheduled_for=SLOT,
        status="SUCCESS",result_json=json.dumps({"errors":["ancienne panne"]})))
    session.commit()
    assert service.run_scheduled_refresh(SLOT)["status"] == "SUCCESS"
    assert len(session.exec(select(SchedulerRun)).all()) == 1


def test_successful_alerts_are_deduplicated_on_partial_retry(book,monkeypatch):
    session,_=book
    contract(book,"GOOD");contract(book,"BAD")
    failing={"BAD"}
    def refresh(deal,_):
        if deal.reference in failing:raise RuntimeError("panne")
        return {}
    monkeypatch.setattr(service,"_refresh_deal_handler",refresh)
    monkeypatch.setattr(service,"_watchlist_handler",lambda *_:dict(barriers=[
        dict(name="M_KI_BAR",kind="ki",observable="S_MIN[1]",level=.6,gap_pts=-10,
             monitoring_basis="SAMPLED_CLOSES_SINCE_STRIKE")]))
    assert service.run_scheduled_refresh(SLOT)["status"] == "PARTIAL"
    failing.clear()
    assert service.run_scheduled_refresh(SLOT)["status"] == "SUCCESS"
    alerts=session.exec(select(Alert)).all()
    assert len(alerts) == 2
    assert all("clôtures indicatives" in alert.message for alert in alerts)


@pytest.mark.parametrize("replacement,raises",[("SUCCESS",False),("RUNNING",True)])
def test_old_worker_cannot_overwrite_a_new_claim(book,monkeypatch,replacement,raises):
    session,_=book
    engine=session.get_bind()
    def replaced(_):
        with Session(engine) as other:
            row=other.exec(select(SchedulerRun)).one()
            row.started_at=datetime(2099,1,1);row.status=replacement
            other.add(row);other.commit()
        if raises:raise RuntimeError("ancien worker")
        return dict(status="SUCCESS",coverage=dict(total=0,succeeded=0,failed=0),errors=[])
    monkeypatch.setattr(service,"refresh_book",replaced)
    result=service.run_scheduled_refresh(SLOT)
    assert result["status"] == ("FAILED" if raises else "SUPERSEDED")
    session.expire_all()
    row=session.exec(select(SchedulerRun)).one()
    assert row.status == replacement and row.started_at == datetime(2099,1,1)


def test_future_strike_requires_no_market_call_and_is_expected_pending(book,monkeypatch):
    session,_=book
    deal=contract(book);deal.strike_date="2026-11-20";session.add(deal);session.commit()
    monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:pytest.fail("Future strike"))
    row=deals_api.build_watchlist_row(deal,session,TODAY)
    assert row["barriers"][0]["value_status"] == "STRIKE_PENDING"


def test_out_of_range_index_is_unavailable(book,monkeypatch):
    deal=contract(book,observable="S[3]")
    prices(monkeypatch,{"TK1":[100,50,100],"TK2":[100,80,90]})
    assert deals_api.build_watchlist_row(deal,book[0],TODAY)["barriers"][0]["gap_pts"] is None


def test_database_flush_failure_is_rolled_back_before_next_deal(book,monkeypatch):
    session,_=book
    contract(book,"BAD");contract(book,"GOOD")
    def refresh(deal,session):
        if deal.reference=="BAD":
            session.add(Alert(user_id=999999,deal_id=deal.id,kind="test",message="invalid foreign key",dedup_key="bad"))
            session.flush()
        return {}
    monkeypatch.setattr(service,"_refresh_deal_handler",refresh)
    result=service.refresh_book(session)
    assert result["coverage"] == dict(total=2,succeeded=1,failed=1)
    assert session.exec(select(Alert)).all() == []


@pytest.mark.parametrize("when",["2026-10-21","invalide"])
def test_settlement_wait_and_invalid_date_have_distinct_outcomes(book,when):
    session,_=book
    deal=contract(book);deal.status="en_reglement";deal.settlement_date=when
    session.add(deal);session.commit()
    result=service.refresh_book(session)
    assert result["settled"] == 0
    assert result["status"] == ("SUCCESS" if when=="2026-10-21" else "FAILED")
    assert deal.status == "en_reglement"


def test_current_claim_is_skipped_and_stale_running_claim_can_resume(book):
    from datetime import timedelta
    session,_=book
    row=SchedulerRun(job_key=service.SCHEDULER_JOB_KEY,scheduled_for=SLOT,status="RUNNING")
    session.add(row);session.commit()
    assert service.run_scheduled_refresh(SLOT)["status"] == "SKIPPED"
    row.started_at=datetime.utcnow()-timedelta(hours=2);session.add(row);session.commit()
    assert service.run_scheduled_refresh(SLOT)["status"] == "SUCCESS"


def test_t08_official_correction_updates_watchlist_without_rewriting_previous_result(monkeypatch):
    from backend.tests.test_fixing_finality_registry import coupon_deal, _events, _resolve_auto_exception
    from backend.app.db.models import OfficialFixingVersion
    session,deal=coupon_deal()
    try:
        monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:dict(
            dates=["2025-01-06","2026-01-06"],prices={"TK1":[30,40]}))
        asof=date(2026,1,6)
        old=deals_api.build_watchlist_row(deal,session,asof)
        assert old["wof"] == .9  # both the initial level and today's close are governed
        coupon=_events(session,deal)[-1]
        prior=session.get(OfficialFixingVersion,coupon.current_fixing_version_id)
        prior_bytes=prior.spots_json
        coupon.fixing_status="MANUAL_REVIEW_REQUIRED";session.add(coupon);session.commit()
        _resolve_auto_exception(session,deal,coupon,action="REPLACE_MANUAL",spots={"UL1":70.})
        new=deals_api.build_watchlist_row(deal,session,asof)
        assert new["wof"] == .7 and old["wof"] == .9
        assert new["fixing_registry"]["official_fixings"][-1]["version_id"] != old["fixing_registry"]["official_fixings"][-1]["version_id"]
        assert session.get(OfficialFixingVersion,prior.id).spots_json == prior_bytes
    finally:
        session.close()


def test_pending_official_version_cannot_fall_back_to_provider_in_watchlist(monkeypatch):
    from fastapi import HTTPException
    from backend.tests.test_fixing_finality_registry import coupon_deal, _events
    from backend.app.db.models import OfficialFixingVersion
    session,deal=coupon_deal()
    try:
        coupon=_events(session,deal)[-1]
        version=session.get(OfficialFixingVersion,coupon.current_fixing_version_id)
        version.status="RECEIVED";session.add(version);session.commit()
        monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:dict(
            dates=["2025-01-06","2026-01-06"],prices={"TK1":[100,40]}))
        with pytest.raises(HTTPException) as exc:
            deals_api.build_watchlist_row(deal,session,date(2026,1,6))
        assert exc.value.detail["code"] == "OFFICIAL_FIXING_PENDING"
    finally:
        session.close()


def test_official_fixing_is_newer_than_a_carried_provider_row(monkeypatch):
    from backend.tests.test_fixing_finality_registry import coupon_deal
    session,deal=coupon_deal()
    try:
        monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:dict(
            dates=["2025-01-06","2026-01-05","2026-01-07"],prices={"TK1":[100,40,40]},
            effective_dates={"TK1":"2026-01-05"},source_observation_dates={
                "TK1":["2025-01-06","2026-01-05","2026-01-05"]}))
        row=deals_api.build_watchlist_row(deal,session,date(2026,1,7))
        assert row["wof"] == .9
        assert row["underlyings"][0]["effective_date"] == "2026-01-06"
    finally:
        session.close()


def test_provider_outage_keeps_the_recent_official_watchlist_level(monkeypatch):
    from backend.tests.test_fixing_finality_registry import coupon_deal
    session,deal=coupon_deal()
    try:
        monkeypatch.setattr(deals_api,"load_hist_prices",lambda *a,**k:{"error":"panne fournisseur"})
        row=deals_api.build_watchlist_row(deal,session,date(2026,1,7))
        assert row["wof"] == .9
        assert len(row["fixing_registry"]["official_fixings"]) == 2
    finally:
        session.close()


def test_full_watchlist_to_alert_retry_never_crosses_on_the_wrong_constituent(book,monkeypatch):
    session,_=book
    contract(book,observable="S_MIN[1]")
    prices(monkeypatch,{"TK2":[100,50,100]})
    monkeypatch.setattr(service,"_watchlist_handler",deals_api.build_watchlist_row)
    first=service.run_scheduled_refresh(SLOT)
    assert first["status"] == "FAILED"
    assert session.exec(select(Alert)).all() == []
    prices(monkeypatch,{"TK1":[100,50,100],"TK2":[100,100,100]})
    recovered=service.run_scheduled_refresh(SLOT)
    assert recovered["status"] == "SUCCESS"
    assert recovered["summary"]["alerts_created"] == 1
    assert "S_MIN[1] à 50.0%" in session.exec(select(Alert)).one().message
    assert service.run_scheduled_refresh(SLOT)["status"] == "SKIPPED"


def test_missing_initial_level_does_not_shift_the_other_constituent(book,monkeypatch):
    session,_=book
    deal=contract(book)
    strike=session.exec(select(DealEvent).where(DealEvent.deal_id==deal.id)).one()
    strike.spots_json='{"UL2":100}';session.add(strike);session.commit()
    prices(monkeypatch,{"TK1":[100,50,100],"TK2":[100,80,90]})
    row=deals_api.build_watchlist_row(deal,session,TODAY)
    assert row["barriers"][0]["gap_pts"] is None
    assert row["wof"] is None
    assert row["underlyings"][1]["perf"] == .9
