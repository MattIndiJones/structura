"""Valo Explain: isolated DB, frozen inputs, draft conflicts and actual PDFs."""
from copy import deepcopy
from datetime import date, timedelta
import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.tests.test_booking_mtm_daily import book, collect
from backend.app.api import deals, valuation_notes as api
from backend.app.core import valuation_notes as core
from backend.app.core.valuation_runs import engine_identity
from backend.app.db.models import User, ValuationRun, ValuationNote, ValuationNoteVersion


@pytest.fixture
def calculated(book, monkeypatch):
    session, user, deal = book
    def prices(tickers, start, end, **kwargs):
        days = [date.fromisoformat(start) + timedelta(days=i)
                for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
        return {"dates": [d.isoformat() for d in days],
                "prices": {t: [100 + .02 * i for i in range(len(days))] for t in tickers}}
    monkeypatch.setattr(deals, "load_hist_prices", prices)
    result = deals.deal_mtm(deal.id, user, session, n_paths=400,
                           body=deals.MtmRequest(recalibrate="none", valuation_date=date.today()))
    run = session.get(ValuationRun, result["valuation_run_id"])
    def offline(*args, **kwargs):
        raise AssertionError("Valo Explain must not fetch live market inputs")
    monkeypatch.setattr(deals, "load_hist_prices", offline)
    monkeypatch.setattr(deals, "dividend_profile", offline)
    return session, user, deal, run


def create(calculated, ids=None, key=None):
    session, user, deal, run = calculated
    body = api.CreateNote(deal_id=deal.id, run_ids=ids or [run.id], request_key=key or uuid4())
    return api.create_note(body, False, user, session)


def cloned_run(session, original, change):
    payload = json.loads(original.context_json)
    change(payload)
    result = json.loads(original.result_json)
    result["mtm"] = core.price_var_scenario_job(payload)["price"]
    run = ValuationRun(deal_id=original.deal_id, user_id=original.user_id,
                       context_hash="test", context_json=json.dumps(payload),
                       contract_version=original.contract_version, engine_fingerprint=engine_identity()[1],
                       result_json=json.dumps(result), diagnostics_json=original.diagnostics_json,
                       market_data_json=original.market_data_json)
    session.add(run); session.commit()
    return run


def test_note_reuses_exact_price_archives_history_and_computes_frozen_greeks(calculated):
    session, user, deal, run = calculated
    phases = []
    original_context = run.context_json
    body = api.CreateNote(deal_id=deal.id, run_ids=[run.id], request_key=uuid4())
    note = api._create(session, user, body, phases.append)
    data = note["evidence"]["runs"][0]["data"]
    assert data["mtm"]["mtm"] == json.loads(run.result_json)["mtm"]
    assert data["history"]["series"]["S1"]
    assert data["greeks"][0]["delta_pts"] > 0
    assert not note["evidence"]["warnings"]
    assert any("sensibilités" in p for p in phases)
    assert run.context_json == original_context
    assert api._create(session, user, body)["id"] == note["id"]
    assert len(session.exec(select(ValuationNote)).all()) == 1
    assert len(session.exec(select(ValuationRun)).all()) == 1
    # Identity, observations and prices are copied into the note.
    deal.reference = "CHANGED"; session.add(deal); session.commit()
    stored = api.get_note(note["id"], user, session)
    assert stored["evidence"]["runs"][0]["data"]["deal"]["reference"] == "DAILY-1"


def test_stream_has_progress_and_persists_one_note(calculated):
    session, user, deal, run = calculated
    response = api.create_note(api.CreateNote(deal_id=deal.id, run_ids=[run.id], request_key=uuid4()), True, user, session)
    events = asyncio.run(collect(response))
    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "result", events
    assert len(session.exec(select(ValuationNote)).all()) == 1


def test_drafts_are_revision_checked_and_versions_keep_identical_pdf(calculated):
    session, user, deal, run = calculated
    note = create(calculated)
    edited = api.save_note(note["id"], api.UpdateNote(revision=1, title="Note client",
                          draft=api.Editorial(synthese="COMMENTAIRE & <b>texte littéral</b>")), user, session)
    assert edited["revision"] == 2
    assert edited["evidence"] == note["evidence"]
    with pytest.raises(HTTPException) as error:
        api.save_note(note["id"], api.UpdateNote(revision=1, title="Stale", draft=api.Editorial()), user, session)
    assert error.value.status_code == 409
    version = api.freeze_note(note["id"], api.Revision(revision=2), user, session)
    assert api.freeze_note(note["id"], api.Revision(revision=2), user, session) == version
    pdf = api.note_pdf(note["id"], version_id=version["id"], current=user, session=session).body
    assert pdf.startswith(b"%PDF")
    api.save_note(note["id"], api.UpdateNote(revision=2, title="Changed", draft=api.Editorial(synthese="NEW")), user, session)
    assert api.note_pdf(note["id"], version_id=version["id"], current=user, session=session).body == pdf
    assert len(session.exec(select(ValuationNoteVersion)).all()) == 1
    with pytest.raises(HTTPException) as stale:
        api.note_pdf(note["id"], revision=2, current=user, session=session)
    assert stale.value.status_code == 409


def test_ownership_and_http_validation(calculated):
    session, user, deal, run = calculated
    note = create(calculated)
    other = User(id=user.id + 1, username="other", email="other@example.invalid", password_hash="unused")
    for operation in (lambda: api.get_note(note["id"], other, session),
                      lambda: api.note_pdf(note["id"], revision=1, current=other, session=session),
                      lambda: api.versions(note["id"], other, session)):
        with pytest.raises(HTTPException) as error:
            operation()
        assert error.value.status_code == 404
    assert api.list_notes(current=other, session=session) == []
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[api.get_current_user] = lambda: user
    def db():
        with Session(session.get_bind()) as s:
            yield s
    app.dependency_overrides[api.get_session] = db
    with TestClient(app) as client:
        response = client.patch(f"/api/valuation-notes/{note['id']}", json={
            "title": "Injected", "revision": 1, "draft": {}, "evidence": {"mtm": 10}})
        assert response.status_code == 422
        assert client.get(f"/api/valuation-notes/{note['id']}").json()["revision"] == 1


def test_two_identical_frozen_contexts_have_zero_attribution(calculated):
    session, user, deal, first = calculated
    second = cloned_run(session, first, lambda p: None)
    result = core.compare_runs(first, second)
    assert result["available"]
    assert all(s["delta_pts"] == 0 for s in result["steps"])
    assert result["residual_pts"] == 0


def test_frozen_spot_move_and_funding_are_separate_and_telescope(calculated):
    session, user, deal, first = calculated
    def change(p):
        p["norm_spots"][0] *= 1.1
        p["valuation_context"]["funding_spread"] = .01
    second = cloned_run(session, first, change)
    result = core.compare_runs(first, second)
    contributions = {s["label"]: s["delta_pts"] for s in result["steps"]}
    assert result["available"]
    assert contributions["Spots"] > 0
    assert contributions["Financement"] < 0
    assert contributions["Taux"] == 0
    assert sum(contributions.values()) + result["residual_pts"] == pytest.approx(result["delta_pts"], abs=1e-12)
    note = create(calculated, [first.id, second.id])
    assert note["kind"] == "comparison"
    assert api.note_pdf(note["id"], revision=1, current=user, session=session).body.startswith(b"%PDF")


@pytest.mark.parametrize("field", ["contract_version", "engine_fingerprint", "seed", "N", "model"])
def test_noncomparable_runs_show_only_observed_difference(calculated, field):
    session, user, deal, first = calculated
    second = cloned_run(session, first, lambda p: p["norm_spots"].__setitem__(0, 1.1))
    if field in {"contract_version", "engine_fingerprint"}:
        setattr(second, field, 99 if field == "contract_version" else "old")
    else:
        p = json.loads(second.context_json); p["valuation_context"][field] = "changed"
        second.context_json = json.dumps(p)
    result = core.compare_runs(first, second)
    assert not result["available"]
    assert result["steps"] == []
    assert result["warnings"]
    assert result["delta_pts"] != 0


def test_replay_mismatch_blocks_attribution(calculated):
    session, user, deal, first = calculated
    second = cloned_run(session, first, lambda p: None)
    result = json.loads(second.result_json); result["mtm"] += .03
    second.result_json = json.dumps(result)
    assert not core.compare_runs(first, second)["available"]


def test_ai_is_explicit_grounded_and_does_not_change_draft(calculated, monkeypatch):
    from backend.app.services.llm import providers
    session, user, deal, run = calculated
    note = create(calculated)
    captured = []
    monkeypatch.setattr(providers, "complete_with_metadata", lambda **kwargs: captured.append(json.loads(kwargs["user"])) or providers.Completion("Proposition à relire", "test"))
    preview = api.preview_assist_note(note["id"], api.AssistNote(revision=1, section="analyse", action="expliquer"), user, session)
    assert captured == []
    assert "valorisations" in preview["user"]
    assert len(preview["base_hash"]) == 64
    result = api.assist_note(note["id"], api.AssistNote(revision=1, section="analyse", action="expliquer", model="test"), user, session)
    assert result["suggestion"] == "Proposition à relire"
    assert result["prompt"] == {k: preview[k] for k in ("system", "user")}
    from backend.app.core.ai_contract import PromptOverride
    custom = api.AssistNote(revision=1, section="analyse", action="expliquer", model="test",
        prompt_override=PromptOverride(base_hash=preview["base_hash"], system=preview["system"] + "\nRédige simplement.", user=preview["user"]))
    edited = api.assist_note(note["id"], custom, user, session)
    assert edited["prompt_customized"] and edited["prompt"]["system"].endswith("Rédige simplement.")
    assert captured[0]["valorisations"][0]["mtm_pct"] == json.loads(run.result_json)["mtm"] * 100
    assert "DAILY-1" not in json.dumps(captured)
    assert "nominal" not in captured[0]
    assert api.get_note(note["id"], user, session)["draft"] == note["draft"]
    monkeypatch.setattr(providers, "complete_with_metadata", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("SECRET")))
    with pytest.raises(HTTPException) as error:
        api.assist_note(note["id"], api.AssistNote(revision=1, section="analyse", action="expliquer", model="test"), user, session)
    assert "SECRET" not in error.value.detail


def test_legacy_note_warns_without_inventing_history(calculated):
    session, user, deal, run = calculated
    run.diagnostics_json = "{}"; run.engine_fingerprint = "old"
    session.add(run); session.commit()
    note = create(calculated)
    assert note["evidence"]["runs"][0]["data"]["history"]["dates"] == []
    assert note["evidence"]["warnings"]


def test_saved_notes_block_normal_deal_deletion_but_uat_purge_cleans_children(calculated):
    from backend.app.core.admin_registry import delete_row
    from backend.app.db.models import UatGenerationBatch
    from backend.app.services.uat_generation import delete_batch
    session, user, deal, run = calculated
    note = create(calculated)
    api.freeze_note(note["id"], api.Revision(revision=1), user, session)
    with pytest.raises(HTTPException) as error:
        delete_row("deals", deal.id, session)
    assert error.value.status_code == 409
    batch = UatGenerationBatch(batch_key="notes-test", created_by=user.id, target_user_id=user.id,
                               mode="BOOKED_ONLY", seed=42, requested_count=1, deal_count=1)
    session.add(batch); session.flush()
    deal.uat_batch_id = batch.id; session.add(deal); session.commit()
    assert delete_batch(batch.id, user, session)["deleted_deals"] == 1
    assert not session.exec(select(ValuationNote)).all()
    assert not session.exec(select(ValuationNoteVersion)).all()


def test_sources_are_compact_authorized_and_preserve_dates(calculated):
    session, user, deal, run = calculated
    result = api.note_sources(deal.id, user, session)
    assert result[0]["id"] == run.id
    assert result[0]["result"]["valuation_date"] == date.today().isoformat()
    assert "diagnostics" not in result[0]
    assert "context" not in result[0]


def test_reversed_comparison_and_calendar_roll_reconcile(calculated):
    session, user, deal, first = calculated
    def roll(p):
        p["T_elapsed"] += .1
        if p["passe_jusqu_a"] is not None:
            p["passe_jusqu_a"] += .1
        p["valuation_context"]["T"] -= .1
        p["valuation_context"]["maturity_payment_t"] -= .1
        p["norm_spots"][0] *= .95
    second = cloned_run(session, first, roll)
    forward = core.compare_runs(first, second)
    reverse = core.compare_runs(second, first)
    assert forward["available"] and reverse["available"]
    assert reverse["delta_pts"] == pytest.approx(-forward["delta_pts"])
    for result in (forward, reverse):
        assert sum(s["delta_pts"] for s in result["steps"]) + result["residual_pts"] == pytest.approx(result["delta_pts"], abs=1e-12)
        assert abs(result["residual_pts"]) < 1e-10


def test_two_underlying_correlation_change_uses_archived_matrix():
    from backend.app.core.valuation_context import ValuationContext
    context = ValuationContext(
        underlyings=[{"name": "S1", "sigma": .2, "q": .01},
                     {"name": "S2", "sigma": .25, "q": .01}],
        corr_matrix=[[1, .2], [.2, 1]], r=.03, T=1, N=1000, model="constant").to_dict()
    a = {"script_text": "AT MATURITY:\n  PAY WOF\n", "value_date": "2026-01-01",
         "strike_date": "2026-01-01", "settlement_ccy": "EUR", "constat_values": {},
         "T_elapsed": 0, "passe_jusqu_a": None, "state": {}, "norm_spots": [1, 1],
         "corr": context["corr_matrix"], "valuation_context": context, "unsettled_pv": 0}
    b = deepcopy(a)
    b["corr"] = b["valuation_context"]["corr_matrix"] = [[1, .8], [.8, 1]]
    def record(p):
        return ValuationRun(deal_id=1, user_id=1, context_hash="test", contract_version=1,
                            engine_fingerprint=engine_identity()[1], context_json=json.dumps(p),
                            result_json=json.dumps({"mtm": core.price_var_scenario_job(p)["price"],
                                                    "valuation_date": "2026-01-01"}))
    result = core.compare_runs(record(a), record(b))
    assert result["available"]
    for step in result["steps"]:
        if step["label"] == "Corrélations":
            assert step["delta_pts"] > 0  # higher correlation raises the expected worst-of
        else:
            assert step["delta_pts"] == 0
    assert result["residual_pts"] == 0
