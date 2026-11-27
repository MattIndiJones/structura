"""Accounting edge cases on the actual lot 4 engine and the reference replay."""

import pytest

from backend.app.core.structured_indices.rates_credit import (
    RatesCreditJob, RatesCreditPrepareRequest, prepare_rates_credit, price_rates_credit,
)
from backend.app.core.structured_indices.rates_credit_evidence import sign_admission, sign_research_receipt
from backend.tests.rates_credit_roll import replay_roll
from backend.tests.rates_credit_roll_fixture import build_roll_plan, cln_market


def _prepare(plan):
    return {vintage["millesime_id"]: prepare_rates_credit(RatesCreditPrepareRequest.model_validate(vintage))
            for vintage in plan["millesimes"]}


def _price(plan, prepared):
    evidence = {}
    for session in plan["sessions"]:
        for request in session["jobs"]:
            job_id, operation = request["job_id"], request["operation"]
            job = RatesCreditJob.model_validate({
                "job_id": job_id, "millesime": prepared[request["millesime_id"]],
                "valuation_date": session["day"], "value_date": session["day"], "cutoff": session["cutoff"],
                "market": request["market"],
            })
            result = price_rates_credit(job, operation=operation).model_dump(mode="json")
            admission = sign_admission(job.model_dump(mode="json"), run_id=plan["run_id"], user_id=1,
                                       operation=operation, secret="test-only")
            receipt = sign_research_receipt(admission, result, "test-only").model_dump(mode="json")
            evidence[job_id] = {"result": result, "receipt": receipt}
    return evidence


def test_late_confirmation_moves_cash_only_at_the_eligible_cutoff():
    plan = build_roll_plan("CLN")
    prepared = _prepare(plan)
    first = prepared["cln-first"].as_product()
    for session, day in zip(plan["sessions"][2:4], (20, 21), strict=True):
        market, cutoff = cln_market(day, first, case="late_payment")
        session["cutoff"] = cutoff
        session["jobs"] = [{"operation": "mtm", "job_id": f"cln-late-{day}", "millesime_id": "cln-first", "market": market}]
    plan["sessions"] = plan["sessions"][:4]
    replay = replay_roll(plan, _price(plan, prepared))
    due, paid = replay["rows"][-2:]
    assert due["receivables_pv_eur"] == pytest.approx(350_000)
    assert due["cash_eur"] == 0
    assert paid["receivables_pv_eur"] == 0
    assert paid["cash_eur"] == pytest.approx(350_000)
    settlement, deferred = paid["events"]
    assert settlement["event"] == "settlement"
    assert settlement["scheduled_date"] == settlement["paid_date"] == "2021-07-20"
    assert settlement["applied_on"] == "2021-07-21"
    assert deferred["event"] == "roll_deferred"
    assert paid["explain"]["nav_move_eur"] == pytest.approx(0)


@pytest.mark.parametrize("reserve", [0, 10_000])
def test_zero_recovery_is_settled_without_cash_credit(reserve):
    plan = build_roll_plan("CLN")
    plan["initial_cash_reserve_eur"] = reserve
    prepared = _prepare(plan)
    first = prepared["cln-first"].as_product()
    for session, day in zip(plan["sessions"][1:3], (19, 20), strict=True):
        market, cutoff = cln_market(day, first, case="zero")
        session["jobs"][0]["market"] = market
        session["cutoff"] = cutoff
    replay = replay_roll(plan, _price(plan, prepared))
    settled = replay["rows"][2]
    assert settled["day"] == "2021-07-20"
    assert settled["cash_eur"] == reserve
    assert settled["millesime_id"] is None
    assert [item["amount_eur"] for item in settled["events"] if item["event"] == "settlement"] == [0]
    if reserve == 0:
        assert replay["state"] == "extinguished"
        assert len(replay["rows"]) == 3 and settled["level"] == 0
    else:
        assert replay["state"] == "completed"
        assert replay["rows"][3]["millesime_id"] == "cln-next"
        assert replay["rows"][3]["nav_eur"] == reserve
