"""C19 archive/replay acceptance: isolated SQLite, synthetic data, no providers."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.tests.test_booking_mtm_daily import book
from backend.tests.test_valuation_notes import calculated, cloned_run
from backend.tests.test_rfq_desk_access import desk_case, _create
from backend.app.api import deals
from backend.app.core import valuation_notes
from backend.app.core.compute.pricers.var_scenario import price_var_scenario_job
from backend.app.core.valuation_runs import replay_valuation_run, calculation_identity
from backend.app.db.archive_integrity import migrate
from backend.app.db.models import DealEvent, OptimizerResearch, ArchivedDocument, RfqRequest, RfqQuote
from backend.app.services import archived_documents as archives
from backend.app.services.rfq_model_reference import snapshot


@pytest.mark.parametrize("upgraded", [False, True])
@pytest.mark.parametrize("mutation", ["result_json=NULL", "status=NULL", "request_hash=NULL", "DELETE"])
def test_optimizer_terminal_evidence_is_null_safe_and_undeletable(tmp_path, upgraded, mutation):
    engine = create_engine(f"sqlite:///{tmp_path / 'archive.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        if upgraded:
            conn.execute(text("DROP TRIGGER optimizer_research_immutable"))
            conn.execute(text("DROP TRIGGER optimizer_research_no_delete"))
            migrate(conn)
            migrate(conn)
    with Session(engine) as session:
        row = OptimizerResearch(id="study", user_id=1, command_key="key", title="Étude",
            summary="S", product_family="phoenix", pricing_date="2026-10-21",
            status="COMPLETED", request_hash="hash", request_json="{}", context_json="{}",
            result_json='{"price":1}', finished_at=datetime.utcnow())
        session.add(row); session.commit()
        statement = ("DELETE FROM optimizer_researches WHERE id='study'" if mutation == "DELETE"
                     else f"UPDATE optimizer_researches SET {mutation} WHERE id='study'")
        with pytest.raises(IntegrityError, match="immutable|Archive"):
            session.exec(text(statement))
        session.rollback()
        session.exec(text("UPDATE optimizer_researches SET archived=1 WHERE id='study'"))
        session.commit()
        assert session.get(OptimizerResearch, "study").result_json == '{"price":1}'
    engine.dispose()


def claim():
    return dict(settlement_claim=True, amount=1.12, valuation_date="2026-10-01",
                payment_date="2026-10-31", r=.03, yield_curve=[[0., .02], [1., .04]],
                funding_spread=.01, funding_curve=[])


@pytest.mark.parametrize("field,value", [("amount",1.2), ("payment_date","2026-11-30"),
    ("valuation_date","2026-10-02"), ("yield_curve",[[0.,.09],[1.,.10]]),
    ("funding_spread",.03), ("funding_curve",[[0.,.05],[1.,.06]]), ("dr",.01)])
def test_receivable_replay_really_uses_its_inputs(field, value):
    initial = claim()
    base = price_var_scenario_job(initial)["price"]
    changed = {**initial, field:value, "fixed_price":base}
    assert price_var_scenario_job(changed)["price"] != base


def test_legacy_fixed_price_is_not_a_replay():
    with pytest.raises(ValueError, match="rejeu indisponible"):
        price_var_scenario_job({"settlement_claim":True,"fixed_price":1.12})


def test_known_claim_var_scenario_carries_rate_shock_without_asset_correlation():
    from backend.app.core.var_engine import apply_scenario_to_deal_base, MarketScenario
    base={"tickers":[],"base":claim()}
    shocked=apply_scenario_to_deal_base(base,MarketScenario(key="rates",label="+100 pb",method="manual",dr_frac=.01))
    assert price_var_scenario_job(shocked)["price"] < price_var_scenario_job(base["base"])["price"]


def test_historical_claim_remains_priceable_after_current_settlement(book):
    session, user, deal = book
    terminal = date.today()-timedelta(days=10)
    payment = date.today()-timedelta(days=5)
    session.add(DealEvent(deal_id=deal.id,event_index=1,event_date=terminal.isoformat(),
                          t_years=.2,status="callé",payout=1.12))
    deal.status="échu"; deal.settlement_amount=1.12; deal.settlement_date=payment.isoformat()
    session.add(deal);session.commit()
    payload, ctx = deals._mtm_core(deal, session, 100, deals.MtmRequest(recalibrate="none"),
                                   asof=terminal+timedelta(days=2))
    assert payload["mtm"] < 1.12
    assert ctx["settlement_claim"]
    assert price_var_scenario_job({"settlement_claim":True,**ctx["claim_inputs"]})["price"] == payload["mtm"]


def test_replay_uses_frozen_calendar_and_never_current_resolver(calculated, monkeypatch):
    session, user, deal, run = calculated
    original = run.result_json
    payload=json.loads(run.context_json)
    assert payload["frozen_calendar"]["events"]
    def fail(*args, **kwargs): raise AssertionError("Current calendar resolver called")
    monkeypatch.setattr("backend.app.core.payscript.parser.resolve_constats", fail)
    replay = replay_valuation_run(run)
    assert replay["within_tolerance"] and replay["qualified"]
    assert run.result_json == original


def test_old_identity_is_not_invented_and_probe_does_not_overwrite(calculated):
    session,user,deal,run=calculated
    old=SimpleNamespace(**run.model_dump());old.diagnostics_json="{}";old.engine_fingerprint="old"
    original=old.result_json
    result=replay_valuation_run(old)
    assert result["mode"] == "probe" and not result["qualified"]
    assert old.result_json == original


def test_numerical_replay_failure_keeps_observed_difference(calculated, monkeypatch):
    session,user,deal,first=calculated
    second=cloned_run(session,first,lambda p:p["norm_spots"].__setitem__(0,1.1))
    def fail(*args,**kwargs): raise ValueError("Synthetic numerical failure")
    monkeypatch.setattr(valuation_notes,"price_var_scenario_job",fail)
    evidence,draft=valuation_notes.build_note(deal,[first,second])
    comparison=evidence["comparison"]
    assert not comparison["available"] and comparison["steps"] == []
    assert comparison["delta_pts"] != 0
    assert any("Synthetic numerical failure" in warning for warning in evidence["warnings"])
    assert valuation_notes.render_note(evidence,draft,"Écart observé").startswith(b"%PDF")


def test_invalid_contract_calendar_still_blocks_note(calculated):
    session,user,deal,first=calculated
    second=SimpleNamespace(**first.model_dump())
    payload=json.loads(first.context_json);payload["frozen_calendar"].update(events=[])
    second.context_json=json.dumps(payload)
    with pytest.raises(ValueError,match="calendrier figé"):
        valuation_notes.compare_runs(first,second)


def test_unverified_scalar_model_benchmark_is_dated_and_detached(book):
    session,user,deal=book
    rfq=RfqRequest(id=22,user_id=user.id,reference="RFQ",model_price=98.2,
                   model_price_at=datetime(2026,10,1),model_input_hash="hash")
    frozen=json.loads(snapshot(session,rfq))
    rfq.model_price=105
    assert frozen["price"] == 98.2 and frozen["calculated_at"] == "2026-10-01T00:00:00"
    assert frozen["qualification"] == "UNVERIFIED_SCALAR"


def test_archive_owner_immutability_and_identical_pdf(book):
    session,user,deal=book
    row=archives.stage(session,kind="EXPLAIN",deal=deal,user=user,request={},
        data={"price":1.0141602},pdf=b"%PDF-frozen")
    session.commit()
    assert archives.response(archives.load(session,row.id,kind="EXPLAIN",deal=deal,user=user)).body == b"%PDF-frozen"
    other=SimpleNamespace(id=999)
    with pytest.raises(HTTPException) as error:
        archives.load(session,row.id,kind="EXPLAIN",deal=deal,user=other)
    assert error.value.status_code == 404
    for sql in ("UPDATE archived_documents SET data_json='{}'", "DELETE FROM archived_documents"):
        with pytest.raises(IntegrityError,match="immutable"):
            session.exec(text(sql))
        session.rollback()


def test_rfq_history_uses_dated_benchmark_and_keeps_it_private(desk_case):
    from backend.app.api import rfq as api
    session, users = desk_case
    created = _create(session, users[0])
    rfq = session.get(RfqRequest, created["id"])
    rfq.model_price = 98.2; rfq.model_price_at = datetime(2026,10,1)
    session.add(rfq)
    quote = RfqQuote(rfq_id=rfq.id, provider="Manual bank")
    session.add(quote); session.commit()
    api.update_quote(rfq.id, quote.id, api.QuoteUpdate(price=100.,status="recu"), users[0], session)
    first=api.rfq_history(users[0],session)[0]
    rfq.model_price=105.;session.add(rfq);session.commit()
    second=api.rfq_history(users[0],session)[0]
    assert second["model_price"] == first["model_price"] == 98.2
    assert second["edge_bps"] == first["edge_bps"]
    assert second["model_reference"]["qualification"] == "UNVERIFIED_SCALAR"
    assert api.rfq_history(users[1],session) == []
    assert "model_reference" not in api.get_rfq(rfq.id,users[1],session)["quotes"][0]


def test_fixing_correction_invalidates_current_projection_without_changing_archive(calculated):
    from backend.app.core.valuation_runs import current_fixings_match
    session,user,deal,run=calculated
    original=run.result_json
    assert current_fixings_match(session,run)
    event=session.exec(select(DealEvent).where(DealEvent.deal_id==deal.id)).first()
    event.fixing_version=1;event.fixing_record_sha256='new-official-proof'
    session.add(event);session.commit()
    assert not current_fixings_match(session,run)
    assert deals.latest_mtm_runs(user,session,deal_ids=str(deal.id)) == []
    assert run.result_json == original
    assert deals.list_valuation_runs(deal.id,user,session)[0]["id"] == run.id


def test_calculation_receipt_binds_engine_identity_to_signature():
    from backend.app.core.valuation_context import build_pricing_receipt
    from backend.app.core.schemas import PricingRequest
    from backend.app.services.product_receipts import signed_receipt, verify_server_receipt
    req=PricingRequest(script="AT MATURITY:\n  PAY 1\n",underlyings=[{"name":"S1","sigma":.2,"q":0}],corr_matrix=[[1]],r=.03,T=1,N=1000)
    receipt=signed_receipt(build_pricing_receipt(req,1),secret="test")
    assert verify_server_receipt(receipt,secret="test")["result"]["calculation_identity"] == calculation_identity()
    receipt["result"]["calculation_identity"]["engine_fingerprint"]="invented"
    with pytest.raises(ValueError): verify_server_receipt(receipt,secret="test")


def proposal_data(vol=.1):
    return {"deal":{"reference":"DAILY-1","devise":"EUR","nominal":1000},
        "candidate":{"ticker":"TK1","name":"S1","sigma":vol,"q":0.,
            "param_name":"Coupon","solved_param":.141602 if vol == .1 else .5,
            "price":1.,"ki_pct":0.,"autocall_pct":0.,"capital_loss_pct":0.,"full_coupon_pct":100.},
        "T":1.,"param_is_pct":True,"backtest":{"error":"Historique synthétique"}}


def proposal_request(**extra):
    return deals.ReinvestProposalRequest(ticker="TK1",param_name="Coupon",target_price=1.,
                                         lo=0.,hi=1.,**extra)


def test_proposal_pdf_keeps_displayed_coupon_after_vol_changes_and_separate_successor(book,monkeypatch):
    session,user,deal=book
    source={"vol":.1}
    monkeypatch.setattr(deals,"_reinvest_proposal_data",lambda *a:proposal_data(source["vol"]))
    displayed=deals.reinvest_proposal_endpoint(deal.id,proposal_request(),user,session)
    source["vol"]=.6
    first=deals.freeze_reinvest_proposal(deal.id,archives.ProposalFreeze(preview=displayed["preview"]),user,session)
    assert first["data"]["candidate"]["solved_param"] == .141602
    assert first["data"]["study"]["data"]["results"][0]["sigma"] == .1
    selection=archives.DocumentSelection(archive_id=first["archive_id"])
    pdf=deals.reinvest_proposal_pdf_endpoint(deal.id,selection,user,session).body
    assert pdf.startswith(b"%PDF")
    assert deals.freeze_reinvest_proposal(deal.id,archives.ProposalFreeze(preview=displayed["preview"]),user,session)["archive_id"] == first["archive_id"]
    next_display=deals.reinvest_proposal_endpoint(deal.id,proposal_request(parent_archive_id=first["archive_id"]),user,session)
    second=deals.freeze_reinvest_proposal(deal.id,archives.ProposalFreeze(preview=next_display["preview"]),user,session)
    assert first["archive_id"] != second["archive_id"]
    assert second["data"]["candidate"]["solved_param"] == .5
    assert session.get(ArchivedDocument,second["archive_id"]).parent_id == first["archive_id"]
    assert deals.reinvest_proposal_pdf_endpoint(deal.id,selection,user,session).body == pdf
    assert len(deals.list_deal_archives(deal.id,user,session)) == 2


@pytest.mark.parametrize("tamper",["price","author","contract","purpose"])
def test_freeze_refuses_modified_or_wrong_proof(book,tamper):
    session,user,deal=book
    preview=archives.sign_preview(proposal_data(),{},deal,user)
    if tamper == "price": preview["claims"]["data"]["candidate"]["solved_param"]=.9
    if tamper == "author": preview["claims"]["user_id"]=999
    if tamper == "contract": deal.contract_version+=1
    if tamper == "purpose": preview=archives.sign_preview(proposal_data(),{},deal,user,purpose="STUDY")
    with pytest.raises(HTTPException):
        deals.freeze_reinvest_proposal(deal.id,archives.ProposalFreeze(preview=preview),user,session)
    assert session.exec(text("SELECT count(*) FROM archived_documents")).one()[0] == 0


def test_archive_upgrade_adds_reference_column_and_reinstalls_same_guards(tmp_path,monkeypatch):
    from backend.app.db import database as db
    engine=create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE rfq_quotes DROP COLUMN model_reference_json')
        conn.exec_driver_sql('DROP TRIGGER optimizer_research_immutable')
    monkeypatch.setattr(db,'engine',engine)
    db._migrate();db._migrate()
    with engine.connect() as conn:
        assert 'model_reference_json' in {r[1] for r in conn.exec_driver_sql('PRAGMA table_info(rfq_quotes)')}
        sql=conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='optimizer_research_immutable'").scalar()
        assert 'NEW.result_json IS NOT OLD.result_json' in sql
    engine.dispose()
