"""Fixed CLN terms and resolved credit observation and payment dates."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.core.product.models import CLNTerms, Product
from backend.app.core.product.native_schedule import native_draft_diagnostics, resolve_native_schedule
from backend.app.core.product.native_schedule_models import NativeSchedule


@pytest.fixture
def cln_terms():
    return CLNTerms(
        schema_version=2, payoff_mode="native", instrument_type="CLN",
        template_id="cln-eur-july-2021", template_version=1, currency="EUR",
        effective_date=date(2021, 3, 22), maturity_date=date(2022, 3, 21),
        issuer_reference="synthetic-issuer", reference_entity_id="synthetic-reference",
        seniority="senior", documentation="synthetic-cds-documentation", restructuring="synthetic-clause",
        fixed_leg={
            "calendar": "TARGET", "business_day_convention": "modified_following",
            "frequency_months": 3, "payment_lag_business_days": 0,
            "day_count": "ACT/360", "coupon_rate": 0.04,
        },
        redemption_fraction=1, coupon_entitlement="survival_through_accrual_end",
        coupon_on_default="none", default_redemption="nominal_times_recovery",
        default_settlement_lag_calendar_days=5,
    )


def test_cln_terms_and_fixed_bullet_schedule_are_product_bound(cln_terms):
    prepared = resolve_native_schedule(cln_terms, product_id=19, terms_version=2)
    assert prepared.status == "ready"
    schedule = prepared.schedule
    assert schedule.terms_fingerprint == cln_terms.fingerprint
    assert NativeSchedule.model_validate_json(schedule.model_dump_json()) == schedule
    product = Product(terms=cln_terms, product_id=19, terms_version=2, native_schedule=schedule)
    assert Product.model_validate_json(product.model_dump_json()) == product
    coupon, principal = schedule.legs
    assert coupon.kind == "fixed_coupon" and principal.kind == "principal"
    assert [(period.payment_date, period.day_count_days) for period in coupon.periods] == [
        (date(2021, 6, 21), 91), (date(2021, 9, 21), 92),
        (date(2021, 12, 21), 91), (date(2022, 3, 21), 90),
    ]
    assert all(period.credit_observation_date == period.accrual_end for period in coupon.periods)
    assert all(period.fixing_date is None for period in coupon.periods)
    final, = principal.events
    assert final.date == coupon.periods[-1].payment_date
    assert final.flow_id == "cln-principal" and final.flow_id != coupon.periods[-1].flow_id


def test_cln_30e360_fractions_and_payment_lag_are_separate_from_credit_observation(cln_terms):
    fixed = cln_terms.fixed_leg.model_copy(update={"day_count": "30E/360", "payment_lag_business_days": 2})
    terms = cln_terms.model_copy(update={"effective_date": date(2021, 6, 21), "fixed_leg": fixed})
    schedule = resolve_native_schedule(terms).schedule
    coupon, principal = schedule.legs
    assert [period.year_fraction for period in coupon.periods] == [0.25] * 3
    last = coupon.periods[-1]
    assert last.credit_observation_date == date(2022, 3, 21)
    assert last.payment_date == principal.events[0].date == date(2022, 3, 23)


def test_distinct_credit_identity_and_explicit_coupon_rule(cln_terms):
    payload = cln_terms.model_dump(mode="json")
    for replacement in ("SYNTHETIC-REFERENCE", "   "):
        with pytest.raises(ValidationError, match="distincts"):
            CLNTerms.model_validate({**payload, "issuer_reference": replacement})
    with pytest.raises(ValidationError, match="coupon_on_default"):
        CLNTerms.model_validate({**payload, "coupon_on_default": "pro_rata"})


def test_missing_fixed_coupon_keeps_a_dated_cln_draft(cln_terms):
    fixed = cln_terms.fixed_leg.model_copy(update={"coupon_rate": None})
    terms = cln_terms.model_copy(update={"fixed_leg": fixed})
    assert resolve_native_schedule(terms).schedule is not None
    product = Product(terms=terms)
    assert native_draft_diagnostics(product) == ("À préciser : nominal.", "À préciser : taux du coupon fixe de la CLN.")
