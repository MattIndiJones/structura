"""July default, recovery, pending claim and single cash confirmation for CDS and CLN."""

from datetime import date, datetime

import pytest

from backend.app.core.product.credit_default import (
    CreditDefaultContext, CreditDefaultDiscount, CreditDefaultError, prepare_credit_default, price_credit_default,
)
from backend.app.core.product.models import Product
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_market import PaymentConfirmation
from backend.tests.test_rates_credit_cds_schedule import cds_terms  # noqa: F401
from backend.tests.test_rates_credit_cln_schedule import cln_terms  # noqa: F401
from backend.tests.test_rates_credit_facts import july_facts  # noqa: F401


_DISCOUNT = CreditDefaultDiscount(ois_rate=0.02, cln_funding_bps=0)
_PLANNED = date(2021, 7, 20)


def _cutoff(day, hour=16):
    return datetime.fromisoformat(f"2021-07-{day:02d}T{hour:02d}:00:00+02:00")


@pytest.fixture
def credit_products(cds_terms, cln_terms):
    return {
        terms.instrument_type: Product(
            product_id=identity, terms_version=1, revision=1, terms=terms,
            native_schedule=resolve_native_schedule(terms, product_id=identity, terms_version=1).schedule,
            intent={"nominal": nominal, "side": "BUY"},
        )
        for terms, identity, nominal in ((cds_terms, 1, 10_000_000), (cln_terms, 2, 1_000_000))
    }


@pytest.fixture
def facts(july_facts):
    default, recovery, settlement = july_facts
    return default, recovery, settlement.model_copy(update={"default_version": 1, "recovery_version": 1})


def _paid_coupon(product):
    premium = product.native_schedule.legs[0].periods[0]
    amount = -25_277.78 if product.terms.instrument_type == "CDS" else 10_111.11
    timestamp = datetime.fromisoformat("2021-06-21T12:00:00+02:00")
    return PaymentConfirmation(
        fact_id=f"{product.terms.instrument_type.lower()}-june-paid", version=1,
        schedule_fingerprint=product.native_schedule.fingerprint, flow_id=premium.flow_id,
        effect_date=premium.payment_date, amount_eur=amount if product.intent.side == "BUY" else -amount,
        status="validated", available_at=timestamp, validated_at=timestamp,
        source={"kind": "synthetic", "provider": "july-fixture", "reference": "earlier-coupon-paid"},
    )


def _prepare(product, cutoff, facts, **overrides):
    defaults = {
        "valuation_date": cutoff.date(), "cutoff": cutoff,
        "default_id": facts[0].default_id, "facts": facts,
        "settlement_date": _PLANNED, "discount": _DISCOUNT,
        "reference_entity_id": product.terms.reference_entity_id, "prior_payments": (_paid_coupon(product),),
    }
    return prepare_credit_default(product, **{**defaults, **overrides})


@pytest.mark.parametrize(("instrument", "net", "pv", "amounts", "days"), [
    ("CDS", 6_493_333.33, 6_492_977.54, [6_500_000, -6_666.67], 24),
    ("CLN", 350_000.00, 349_980.82, [350_000], 0),
])
def test_july_state_transitions_and_cash_reconciliation(credit_products, facts, instrument, net, pv, amounts, days):
    product = credit_products[instrument]
    before = _prepare(product, _cutoff(15, 9), facts)
    before_result = price_credit_default(product, before)
    assert before_result.state == "alive"
    assert before_result.economic_pv_eur is before_result.contingent_pv_eur is None
    assert before.planned_settlement_date is None and before.facts.default is None

    pending = price_credit_default(product, _prepare(product, _cutoff(15, 10), facts))
    assert pending.state == "recovery_pending"
    assert pending.default_date == date(2021, 7, 15)
    assert pending.default_known_at == _cutoff(15, 10)
    assert pending.accrued_days_at_default == days and pending.contingent_pv_eur == 0
    assert pending.measure.value is pending.recovery_fraction is pending.net_due_eur is None
    assert pending.settlement_flow is None and pending.realized_cash_eur == 0
    assert [(flow.state, flow.paid_date) for flow in pending.earned_coupon_flows] == [("paid", date(2021, 6, 21))]

    context = _prepare(product, _cutoff(19), facts)
    assert CreditDefaultContext.model_validate_json(context.model_dump_json()) == context
    due = price_credit_default(product, context)
    assert due.state == "settlement_pending" and due.recovery_fraction == 0.35
    assert due.accrued_days_at_default == days
    assert due.settlement_flow.state == "due" and due.settlement_flow.paid_date is None
    assert due.settlement_flow.scheduled_date == _PLANNED
    assert due.net_due_eur == net and due.realized_cash_eur == 0
    assert [line.amount_eur for line in due.components] == amounts
    assert due.economic_pv_eur == pytest.approx(pv, abs=0.01, rel=0)
    assert due.measure.value == due.claim_pv_eur

    before_payment = price_credit_default(product, _prepare(product, _cutoff(20, 14), facts))
    assert before_payment.state == "settlement_pending" and before_payment.claim_pv_eur == net
    settled = price_credit_default(product, _prepare(product, _cutoff(20, 15), facts))
    assert settled.state == "settled"
    assert settled.net_due_eur == settled.economic_pv_eur == settled.measure.value == 0
    assert settled.realized_cash_eur == settled.cash_on_value_date_eur == before_payment.claim_pv_eur
    assert settled.settlement_flow.state == "paid" and settled.settlement_flow.paid_date == _PLANNED
    assert settled.settlement_flow.flow_id == due.settlement_flow.flow_id
    assert [line.flow_id for line in settled.components] == [line.flow_id for line in due.components]
    assert price_credit_default(product, _prepare(product, _cutoff(20, 15), (*facts, facts[-1]))) == settled
    following_day = price_credit_default(product, _prepare(product, _cutoff(21), facts))
    assert following_day.settlement_flow == settled.settlement_flow
    assert following_day.cash_on_value_date_eur == 0


def test_sell_protection_inverts_components_and_claim_value(credit_products, facts):
    buyer = credit_products["CDS"]
    seller = buyer.model_copy(update={"intent": buyer.intent.model_copy(update={"side": "SELL"})})
    buy = price_credit_default(buyer, _prepare(buyer, _cutoff(19), facts))
    sell = price_credit_default(seller, _prepare(seller, _cutoff(19), facts))
    assert sell.net_due_eur == -buy.net_due_eur and sell.economic_pv_eur == -buy.economic_pv_eur
    assert [part.amount_eur for part in sell.components] == [-part.amount_eur for part in buy.components]


def test_zero_recovery_for_cln_resolves_without_cash(credit_products, facts):
    product = credit_products["CLN"]
    default, recovery, settlement = facts
    zero = (default, recovery.model_copy(update={"recovery_fraction": 0}), settlement)
    due = price_credit_default(product, _prepare(product, _cutoff(19), zero))
    assert due.state == "settlement_pending" and due.recovery_fraction == 0 and due.net_due_eur == 0
    paid = price_credit_default(product, _prepare(product, _cutoff(20), zero))
    assert paid.state == "settled" and paid.settlement_flow.state == "paid"
    assert paid.realized_cash_eur == 0
    assert paid.settlement_flow.flow_id == due.settlement_flow.flow_id


def test_late_notice_and_delayed_confirmation_keep_effective_dates(credit_products, facts):
    product = credit_products["CLN"]
    default, recovery, settlement = facts
    late_default = default.model_copy(update={"available_at": _cutoff(16), "validated_at": _cutoff(16, 17)})
    late_settlement = settlement.model_copy(update={
        "effect_date": date(2021, 7, 22), "available_at": _cutoff(23), "validated_at": _cutoff(23),
    })
    facts = late_default, recovery, late_settlement
    early = price_credit_default(product, _prepare(product, _cutoff(16), facts))
    assert early.state == "alive"
    known = price_credit_default(product, _prepare(product, _cutoff(16, 17), facts))
    assert known.default_known_at == _cutoff(16, 17) and known.default_date == date(2021, 7, 15)
    still_due = price_credit_default(product, _prepare(product, _cutoff(22), facts))
    assert still_due.state == "settlement_pending"
    assert still_due.settlement_flow.state == "past_due" and still_due.claim_pv_eur == 350_000
    assert still_due.cash_on_value_date_eur == 0
    confirmed = price_credit_default(product, _prepare(product, _cutoff(23), facts))
    assert confirmed.settlement_flow.flow_id == still_due.settlement_flow.flow_id
    assert confirmed.settlement_flow.paid_date == date(2021, 7, 22)
    assert confirmed.realized_cash_eur == 350_000 and confirmed.cash_on_value_date_eur == 0


def test_later_recovery_fact_does_not_rewrite_paid_cash(credit_products, facts):
    product = credit_products["CLN"]
    _, recovery, settlement = facts
    new_recovery = recovery.model_copy(update={
        "version": 2, "fact_id": "recovery-v2", "recovery_fraction": 0.2,
        "available_at": _cutoff(21), "validated_at": _cutoff(21),
    })
    old = _prepare(product, _cutoff(20), facts)
    assert _prepare(product, _cutoff(20), (*facts, new_recovery)) == old
    newer = _prepare(product, _cutoff(21), (*facts, new_recovery))
    assert newer.facts.recovery.recovery_fraction == 0.2
    assert newer.paid_basis.recovery.recovery_fraction == 0.35
    assert price_credit_default(product, newer).settlement_flow == price_credit_default(product, old).settlement_flow

    mislinked = settlement.model_copy(update={"recovery_version": 2})
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(product, _cutoff(21), (*facts[:2], mislinked, new_recovery))
    assert exc.value.code == "CREDIT_SETTLEMENT_BINDING"
    confirmed_later = mislinked.model_copy(update={"available_at": _cutoff(22), "validated_at": _cutoff(22)})
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(product, _cutoff(22), (*facts[:2], confirmed_later, new_recovery))
    assert exc.value.code == "CREDIT_SETTLEMENT_BINDING"


def test_existing_claim_survives_reference_default_and_no_new_principal_is_generated(credit_products, facts):
    product = credit_products["CLN"]
    due = price_credit_default(product, _prepare(product, _cutoff(19), facts, prior_payments=()))
    earned, = due.earned_coupon_flows
    assert earned.flow_id == product.native_schedule.legs[0].periods[0].flow_id
    assert (earned.state, earned.amount_eur, earned.pv_eur) == ("past_due", 10_111.11, 10_111.11)
    assert due.net_due_eur == 360_111.11
    assert due.contingent_pv_eur == 0
    assert product.native_schedule.legs[1].events[0].flow_id not in {
        flow.flow_id for flow in (*due.earned_coupon_flows, *due.components, due.settlement_flow)
    }


def test_default_priority_prevents_coupon_acquisition_on_same_day(credit_products, facts):
    product = credit_products["CLN"]
    default, recovery, _ = facts
    default = default.model_copy(update={"effect_date": date(2021, 6, 21)})
    due = price_credit_default(product, _prepare(product, _cutoff(19), (default, recovery)))
    assert not due.earned_coupon_flows
    assert due.net_due_eur == 350_000


def test_invalid_product_context_reference_and_settlement_date_are_refused(credit_products, facts):
    cln, cds = credit_products["CLN"], credit_products["CDS"]
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(cln, _cutoff(19), facts, settlement_date=date(2021, 7, 19))
    assert exc.value.code == "CREDIT_SETTLEMENT_DATE"
    early_paid = facts[-1].model_copy(update={"effect_date": date(2021, 7, 19)})
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(cln, _cutoff(20), (*facts[:2], early_paid))
    assert exc.value.code == "CREDIT_SETTLEMENT_DATE"
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(cln, _cutoff(19), facts, reference_entity_id="unrelated-reference")
    assert exc.value.code == "CREDIT_DEFAULT_REFERENCE"
    with pytest.raises(CreditDefaultError) as exc:
        _prepare(cds, _cutoff(19), facts, discount=CreditDefaultDiscount(ois_rate=0.02, cln_funding_bps=100))
    assert exc.value.code == "CREDIT_DEFAULT_FUNDING"
    context = _prepare(cln, _cutoff(19), facts)
    wrong_nominal = cln.model_copy(update={"intent": cln.intent.model_copy(update={"nominal": 1_100_000})})
    with pytest.raises(CreditDefaultError) as exc:
        price_credit_default(wrong_nominal, context)
    assert exc.value.code == "CREDIT_DEFAULT_CONTEXT"


def test_cln_funding_changes_only_carry_value_of_known_claim(credit_products, facts):
    cln = credit_products["CLN"]
    base = price_credit_default(cln, _prepare(cln, _cutoff(19), facts))
    discount = CreditDefaultDiscount(ois_rate=0.02, cln_funding_bps=100)
    funded = price_credit_default(cln, _prepare(cln, _cutoff(19), facts, discount=discount))
    assert funded.claim_pv_eur == pytest.approx(349_971.23, abs=0.01, rel=0)
    assert funded.claim_pv_eur < base.claim_pv_eur
    assert funded.net_due_eur == base.net_due_eur == 350_000
    assert funded.recovery_fraction == base.recovery_fraction == 0.35
