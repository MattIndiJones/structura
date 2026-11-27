"""Lot 4 Research motor acceptance with frozen synthetic terms and facts."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_market import RatesMarketError
from backend.app.core.structured_indices.rates_credit import (
    RatesCreditJob,
    RatesCreditPrepareRequest,
    RatesCreditResearchError,
    RatesCreditResult,
    prepare_rates_credit,
    price_rates_credit,
)
from backend.tests.rates_credit_roll_fixture import cln_market, frn_market, terms_for


def _prepare(vintage, *, terms=None, nominal=1_000_000.0):
    return prepare_rates_credit(RatesCreditPrepareRequest(
        millesime_id=vintage, terms=terms or terms_for(vintage),
        intent={"nominal": nominal, "side": "BUY"},
    ))


def _job(prepared, case, *, variant="normal"):
    product = prepared.as_product()
    market, cutoff = (
        frn_market(case, product) if product.terms.instrument_type == "FRN"
        else cln_market(case, product, case=variant)
    )
    return RatesCreditJob.model_validate({
        "job_id": f"{prepared.millesime_id}-{case}", "millesime": prepared.model_dump(mode="json"),
        "valuation_date": cutoff[:10], "cutoff": cutoff, "market": market,
    })


def _flow(result, *, kind=None, flow_id=None):
    flow, = [flow for flow in result.flows if (
        flow.flow_id == flow_id if flow_id is not None else flow.kind == kind
    )]
    return flow


def test_frn_prices_coupon_detachment_and_roll_terms():
    first, replacement = _prepare("frn-first"), _prepare("frn-next")
    a = price_rates_credit(_job(first, "A"), operation="issue")
    b = price_rates_credit(_job(first, "B"))
    owed = price_rates_credit(_job(first, "C-open"), operation="lifecycle")
    paid = price_rates_credit(_job(first, "C"))
    entry = price_rates_credit(_job(replacement, "C"), operation="issue")
    next_day = price_rates_credit(_job(replacement, "D"))

    assert a.dirty_per_100 == pytest.approx(102.9418961778, abs=1e-10)
    assert a.unit == "EUR_per_100" and a.currency == "EUR"
    assert b.dirty_per_100 == pytest.approx(103.3653007825, abs=1e-10)
    assert b.accrued_per_100 == pytest.approx(.478333333333)
    assert b.clean_per_100 + b.accrued_per_100 == pytest.approx(b.dirty_per_100)
    first_coupon = first.native_schedule.legs[0].periods[0].flow_id
    assert _flow(a, flow_id=first_coupon).state == "projected"
    fixed = _flow(b, flow_id=first_coupon)
    assert fixed.state == "fixed" and fixed.effect_date == date(2026, 9, 17)
    assert fixed.fact_id is not None and fixed.version == 1
    assert b.receivable_pv_per_100 == 0

    before, after = (_flow(result, flow_id=first_coupon) for result in (owed, paid))
    assert owed.residual_pv_per_100 == paid.residual_pv_per_100 == pytest.approx(102.6889466169, abs=1e-10)
    assert owed.market_fingerprint == paid.market_fingerprint
    assert before.state == "due" and before.paid_date is None
    assert before.pv_per_100 == owed.receivable_pv_per_100 == pytest.approx(1.036388888889)
    assert after.state == "paid" and after.paid_date == after.effect_date == date(2026, 12, 21)
    assert after.amount_per_100 == pytest.approx(1.036389)
    assert after.pv_per_100 == paid.receivable_pv_per_100 == 0
    assert before.scheduled_date == after.scheduled_date == date(2026, 12, 21)
    assert not owed.effective_market.to_dict()["payments"]
    assert paid.effective_market.to_dict()["payments"][0]["fact_id"] == after.fact_id
    assert after.available_at <= paid.cutoff and after.validated_at <= paid.cutoff

    assert entry.dirty_per_100 == pytest.approx(103.0522363261, abs=1e-10)
    assert next_day.dirty_per_100 == pytest.approx(103.0578831787, abs=1e-10)
    assert entry.prepared_fingerprint == replacement.fingerprint
    assert entry.schedule_fingerprint != paid.schedule_fingerprint
    final_coupon = replacement.native_schedule.legs[0].periods[-1]
    principal = _flow(entry, kind="principal")
    assert final_coupon.payment_date == principal.scheduled_date
    assert final_coupon.flow_id != principal.flow_id


def test_frn_past_due_only_in_research_and_late_confirmation_preserves_original_date():
    first, replacement = _prepare("frn-first"), _prepare("frn-next")
    paid_on_c = _job(first, "C")
    next_market = _job(replacement, "D").market
    payment, = paid_on_c.market.payments
    late = payment.model_copy(update={
        "available_at": datetime(2026, 12, 22, 11, tzinfo=timezone.utc),
        "validated_at": datetime(2026, 12, 22, 11, tzinfo=timezone.utc),
    })
    next_market = next_market.model_copy(update={"payments": (late,)})
    morning = RatesCreditJob(
        job_id="late-frn", millesime=first, valuation_date=date(2026, 12, 22),
        cutoff=datetime(2026, 12, 22, 10, 59, tzinfo=timezone.utc), market=next_market,
    )
    with pytest.raises(RatesMarketError) as refused:
        prepare_native_context(
            first.as_product(), valuation_date=morning.valuation_date,
            cutoff=morning.cutoff, market=next_market, allow_draft=True,
        )
    assert refused.value.code == "RATES_OVERDUE_PAYMENT"

    owed = price_rates_credit(morning)
    assert not owed.effective_market.to_dict()["payments"]
    assert owed.effective_market.to_dict()["overdue_treatment"] == "face_at_valuation_date"
    flow = _flow(owed, flow_id=payment.flow_id)
    assert flow.state == "past_due" and flow.paid_date is None
    assert flow.pv_per_100 == flow.amount_per_100 == owed.receivable_pv_per_100

    afternoon = morning.model_copy(update={"cutoff": late.available_at})
    paid = price_rates_credit(afternoon)
    resolved = _flow(paid, flow_id=payment.flow_id)
    assert resolved.state == "paid" and paid.receivable_pv_per_100 == 0.0
    assert resolved.paid_date == date(2026, 12, 21)
    assert resolved.available_at.date() == paid.valuation_date
    assert price_rates_credit(morning) == owed


def test_frn_at_maturity_coupon_and_principal_keep_two_settlement_identities():
    fixture = _job(_prepare("frn-first"), "C")
    terms = fixture.millesime.terms.model_copy(update={"maturity_date": fixture.valuation_date})
    prepared = _prepare("frn-at-maturity", terms=terms)
    job = fixture.model_copy(update={
        "millesime": prepared, "market": fixture.market.model_copy(update={"payments": ()}),
    })
    maturity = price_rates_credit(job)
    coupon, principal = maturity.flows
    assert maturity.state == "settlement_pending" and maturity.residual_pv_per_100 == 0
    assert coupon.flow_id != principal.flow_id
    assert coupon.kind == "coupon" and principal.kind == "principal"
    assert coupon.scheduled_date == principal.scheduled_date == job.valuation_date
    assert coupon.state == principal.state == "due"
    assert maturity.receivable_pv_per_100 == pytest.approx(101.0363888889)

    original, = fixture.market.payments
    confirmations = tuple(original.model_copy(update={
        "fact_id": f"synthetic-receipt-{flow.kind}", "flow_id": flow.flow_id,
        "schedule_fingerprint": prepared.schedule_fingerprint,
        "amount_eur": round(flow.amount_per_100 * 10_000, 2),
    }) for flow in maturity.flows)
    settled = price_rates_credit(job.model_copy(update={
        "market": job.market.model_copy(update={"payments": confirmations}),
    }))
    assert settled.state == "settled" and settled.receivable_pv_per_100 == 0
    assert tuple(flow.flow_id for flow in settled.flows) == (coupon.flow_id, principal.flow_id)
    assert all(flow.state == "paid" and flow.paid_date == job.valuation_date for flow in settled.flows)


def test_research_rejects_in_place_cash_changes_only_once_they_are_eligible():
    job = _job(_prepare("frn-first"), "C")
    original, = job.market.payments
    effective = job.cutoff + timedelta(minutes=1)
    correction = original.model_copy(update={
        "fact_id": "superseding-cash", "version": 2, "amount_eur": original.amount_eur + 1,
        "available_at": effective, "validated_at": effective,
    })
    revised_market = job.market.model_copy(update={"payments": (original, correction)})
    before = price_rates_credit(job.model_copy(update={"market": revised_market}))
    actual = price_rates_credit(job)
    assert before.effective_market == actual.effective_market
    assert before.flows == actual.flows
    assert before.request_fingerprint != actual.request_fingerprint
    with pytest.raises(RatesCreditResearchError) as refused:
        price_rates_credit(job.model_copy(update={"market": revised_market, "cutoff": effective}))
    assert refused.value.code == "RESEARCH_PAID_CASH_CONFLICT"


def test_cln_default_lifecycle_holds_claim_until_confirmation():
    first, following = _prepare("cln-first"), _prepare("cln-next")
    alive = price_rates_credit(_job(first, 14), operation="issue")
    pending = price_rates_credit(_job(first, 15), operation="lifecycle")
    due = price_rates_credit(_job(first, 19))
    paid = price_rates_credit(_job(first, 20))
    new = price_rates_credit(_job(following, 21), operation="issue")
    next_day = price_rates_credit(_job(following, 22))

    assert alive.dirty_per_100 == pytest.approx(100.8188560829, abs=1e-10)
    assert alive.dirty_per_100 == alive.residual_pv_per_100
    paid_june, = [flow for flow in alive.flows if flow.state == "paid"]
    assert paid_june.paid_date == date(2021, 6, 21) < alive.value_date
    assert alive.effective_market.to_dict()["payments"][0]["fact_id"] == paid_june.fact_id
    assert alive.effective_market.to_dict().get("default_context") is None

    assert pending.state == "recovery_pending"
    assert pending.dirty_per_100 is None and pending.receivable_pv_per_100 is None
    assert pending.residual_pv_per_100 == 0.0
    claim = _flow(pending, kind="default_settlement")
    assert claim.state == "pending" and claim.amount_per_100 is None
    assert tuple(event.to_dict()["kind"] for event in pending.events) == ("default",)
    with pytest.raises(RatesCreditResearchError) as refused:
        price_rates_credit(_job(first, 15), operation="issue")
    assert refused.value.code == "RESEARCH_NOT_ISSUABLE"

    unpaid, settled = (_flow(result, flow_id=claim.flow_id) for result in (due, paid))
    assert unpaid.state == "due" and unpaid.amount_per_100 == 35.0
    assert due.receivable_pv_per_100 == pytest.approx(34.99808224432255)
    assert due.residual_pv_per_100 == paid.residual_pv_per_100 == 0.0
    assert paid.state == "settled" and paid.receivable_pv_per_100 == 0.0
    assert settled.state == "paid" and settled.amount_per_100 == 35.0
    assert settled.paid_date == settled.scheduled_date == date(2021, 7, 20)
    assert new.dirty_per_100 == pytest.approx(100.8186080657, abs=1e-10)
    assert next_day.dirty_per_100 == pytest.approx(100.8274659852, abs=1e-10)


def test_cln_late_notice_late_payment_and_zero_are_observed_at_their_first_cutoffs():
    prepared = _prepare("cln-first")
    unforeseen = price_rates_credit(_job(prepared, 15, variant="late_notice"))
    known = price_rates_credit(_job(prepared, 16, variant="late_notice"))
    assert unforeseen.state == "alive" and unforeseen.events == ()
    assert known.state == "recovery_pending"
    assert known.events[0].to_dict()["effect_date"] == "2021-07-15"

    same_day = price_rates_credit(_job(prepared, 20, variant="late_payment"))
    assert _flow(same_day, kind="default_settlement").state == "due"
    assert same_day.receivable_pv_per_100 == 35.0
    intraday = _job(prepared, 21, variant="late_payment")
    overdue = price_rates_credit(intraday.model_copy(update={
        "cutoff": datetime(2021, 7, 21, 9, tzinfo=timezone.utc),
    }))
    paid = price_rates_credit(intraday)
    waiting, resolved = (_flow(result, kind="default_settlement") for result in (overdue, paid))
    assert waiting.state == "past_due" and waiting.pv_per_100 == 35.0
    assert resolved.state == "paid" and resolved.flow_id == waiting.flow_id
    assert resolved.paid_date == date(2021, 7, 20)
    assert resolved.available_at.date() == paid.valuation_date

    zero = price_rates_credit(_job(prepared, 20, variant="zero"))
    assert zero.state == "settled" and zero.receivable_pv_per_100 == 0.0
    clear = _flow(zero, kind="default_settlement")
    assert clear.state == "paid" and clear.amount_per_100 == 0.0


def test_cln_known_claim_uses_discount_without_survival_and_unpaid_coupon_holds_pocket():
    prepared = _prepare("cln-first")
    due_job = _job(prepared, 19)
    claims_market = due_job.market.model_copy(update={"hazard_rate": None, "pricing_recovery_fraction": None})
    claim = price_rates_credit(due_job.model_copy(update={"market": claims_market}))
    assert claim.receivable_pv_per_100 == price_rates_credit(due_job).receivable_pv_per_100

    job = _job(prepared, 20)
    market = job.market.model_copy(update={"payments": ()})
    valuation = price_rates_credit(job.model_copy(update={"market": market}))
    coupon = _flow(valuation, kind="coupon")
    assert coupon.state == "past_due" and coupon.amount_per_100 == pytest.approx(1.011111)
    assert _flow(valuation, kind="default_settlement").state == "paid"
    assert valuation.state == "settlement_pending"
    assert valuation.receivable_pv_per_100 == coupon.pv_per_100


def test_cln_recovery_amendment_reprices_open_claim_but_preserves_confirmed_cash():
    prepared = _prepare("cln-first")
    open_job = _job(prepared, 19)
    paid_job = _job(prepared, 21)
    _, recovery, _ = open_job.market.credit_facts
    before, after = (
        datetime(2021, 7, 19, 13, tzinfo=timezone.utc),
        datetime(2021, 7, 21, 13, tzinfo=timezone.utc),
    )
    original_claim = _flow(price_rates_credit(open_job), kind="default_settlement")
    original_paid = _flow(price_rates_credit(paid_job), kind="default_settlement")
    for job, clock, expected in ((open_job, before, original_claim), (paid_job, after, original_paid)):
        correction = recovery.model_copy(update={
            "fact_id": "recovery-v2", "version": 2, "recovery_fraction": .25,
            "effect_date": clock.date(), "available_at": clock, "validated_at": clock,
        })
        revised = job.model_copy(update={
            "market": job.market.model_copy(update={"credit_facts": (*job.market.credit_facts, correction)}),
        })
        valuation = price_rates_credit(revised)
        claim = _flow(valuation, kind="default_settlement")
        assert claim.flow_id == expected.flow_id
        assert valuation.effective_market.to_dict()["default_context"]["facts"]["recovery"]["version"] == 2
        if job is open_job:
            assert claim.amount_per_100 == 25.0 and claim.state == "due"
            assert claim.version == 2 and claim.pv_per_100 == pytest.approx(25 * original_claim.pv_per_100 / 35)
        else:
            basis = valuation.effective_market.to_dict()["default_context"]["paid_basis"]
            assert basis["recovery"]["version"] == 1
            assert claim == original_paid and claim.amount_per_100 == 35.0
    assert _flow(price_rates_credit(open_job), kind="default_settlement") == original_claim


def test_preparation_binding_serialization_and_reference_nominal_invariance():
    terms = terms_for("frn-first")
    saved_schedule = resolve_native_schedule(terms, product_id=7, terms_version=2).schedule
    archived = prepare_rates_credit(
        RatesCreditPrepareRequest(
            millesime_id="saved-vintage", terms_version=2, terms=terms,
            intent={"nominal": 1_000_000.0, "side": "BUY"},
        ),
        schedule=saved_schedule, product_id=7, product_reference="STRU-RESEARCH-007",
    )
    job = _job(archived, "A")
    result = price_rates_credit(RatesCreditJob.model_validate_json(job.model_dump_json()), operation="issue")
    assert RatesCreditResult.model_validate_json(result.model_dump_json()) == result
    assert result.product_id == 7 and result.terms_version == 2 and result.product_reference == "STRU-RESEARCH-007"
    assert result.schedule_fingerprint == saved_schedule.fingerprint
    other_vintage = _prepare("frn-first", nominal=47_000.0)
    other = price_rates_credit(job.model_copy(update={"millesime": other_vintage}), operation="issue")
    assert result.dirty_per_100 == pytest.approx(other.dirty_per_100, abs=1e-11)
    assert result.prepared_fingerprint != other.prepared_fingerprint

    bad_schedule = saved_schedule.model_copy(update={"legs": saved_schedule.legs[::-1]})
    altered = job.model_copy(update={"millesime": archived.model_copy(update={"native_schedule": bad_schedule})})
    with pytest.raises(ValueError, match="échéancier figés"):
        price_rates_credit(altered, operation="issue")
