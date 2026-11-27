"""Exact native EUR FRN and IRS cash-flow dates against the frozen A/B/C case."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.core.product.models import FRNTerms, IRSTerms
from backend.app.core.product.rates_schedule import resolve_rates_schedule


@pytest.fixture(scope="module")
def abc_reference():
    fixture_path = Path(__file__).with_name("fixtures") / "rates_credit_abc.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def abc_terms(abc_reference):
    terms = abc_reference["terms"]
    floating = terms["floating"]
    common = {
        "schema_version": 2, "payoff_mode": "native", "template_version": 1,
        "currency": terms["currency"], "effective_date": terms["effective_date"],
        "maturity_date": terms["maturity_date"],
    }
    calendar = {
        "calendar": terms["calendar"], "business_day_convention": terms["business_day_convention"],
        "payment_lag_business_days": floating["payment_lag_target_days"],
    }
    floating_leg = {
        **calendar, "frequency_months": floating["frequency_months"],
        "index": f"{floating['index']}_{floating['tenor']}", "day_count": floating["day_count"],
        "fixing_calendar": terms["calendar"], "fixing_lag_business_days": floating["fixing_lag_target_days"],
    }
    frn = FRNTerms(
        **common, instrument_type="FRN", template_id="frn-eur-pilot",
        floating_leg={**floating_leg, "margin_bps": float(terms["frn"]["margin_bp"])},
        redemption_fraction=float(terms["frn"]["principal_fraction"]),
    )
    irs_terms = terms["irs"]
    irs = IRSTerms(
        **common, instrument_type="IRS", template_id="irs-eur-pilot",
        floating_leg={**floating_leg, "margin_bps": float(irs_terms["floating_margin_bp"])},
        fixed_leg={
            **calendar, "frequency_months": irs_terms["fixed_frequency_months"],
            "day_count": irs_terms["fixed_day_count"], "coupon_rate": float(irs_terms["fixed_rate"]),
        },
    )
    return frn, irs


def test_frn_and_irs_share_the_same_euribor_schedule(abc_terms, abc_reference):
    frn, irs = abc_terms
    for terms, flow_key in ((frn, "frn_flow_id"), (irs, "irs_flow_id")):
        floating = resolve_rates_schedule(terms)[0]
        assert (floating.leg_id, floating.kind) == ("floating", "floating_coupon")
        assert floating.calendar == floating.fixing_calendar == "TARGET"
        assert floating.business_day_convention == "modified_following"
        assert floating.fixing_lag_business_days == 2
        assert floating.payment_lag_business_days == 0
        assert floating.roll_rule == "effective_day_of_month"
        assert floating.events == ()
        assert len(floating.periods) == 8
        for rank, (period, expected) in enumerate(
            zip(floating.periods, abc_reference["floating_periods"], strict=True), start=1,
        ):
            assert period.model_dump(mode="json") == {
                "period_id": expected["period_id"], "rank": rank, "flow_id": expected[flow_key],
                "unadjusted_start": expected["start_unadjusted"], "unadjusted_end": expected["end_unadjusted"],
                "accrual_start": expected["start_adjusted"], "accrual_end": expected["end_adjusted"],
                "day_count": "ACT/360", "day_count_days": expected["act360_days"], "day_count_denominator": 360,
                "fixing_date": expected["fixing_date"], "payment_date": expected["payment_date"],
                "projection_start": expected["start_adjusted"], "projection_end": expected["end_adjusted"],
                "credit_observation_date": None,
            }
        assert sum(period.day_count_days for period in floating.periods) == 731
        assert floating.periods[0].fixing_date < terms.effective_date
        assert floating.periods[0].flow_id == abc_reference["first_payment"][flow_key]
        assert floating.periods[0].payment_date.isoformat() == abc_reference["first_payment"]["effect_date"]


def test_distinct_fixed_and_principal_flows_at_the_same_payment_date(abc_terms, abc_reference):
    frn, irs = abc_terms
    floating, principal = resolve_rates_schedule(frn)
    assert (principal.leg_id, principal.kind, principal.periods) == ("principal", "principal", ())
    event, = principal.events
    reference = abc_reference["terms"]["frn"]
    assert principal.roll_rule == "last_coupon_payment"
    assert event.event_id == "principal-01"
    assert event.kind == "principal"
    assert event.flow_id == reference["principal_flow_id"] != floating.periods[-1].flow_id
    assert event.date == floating.periods[-1].payment_date == date.fromisoformat(reference["principal_payment_date"])

    floating, fixed = resolve_rates_schedule(irs)
    assert (fixed.leg_id, fixed.kind, fixed.events) == ("fixed", "fixed_coupon", ())
    for rank, (period, expected) in enumerate(
        zip(fixed.periods, abc_reference["fixed_periods"], strict=True), start=1,
    ):
        assert (period.rank, period.period_id, period.flow_id) == (rank, f"fixed-{rank:02d}", expected["flow_id"])
        assert period.accrual_start == period.unadjusted_start == date.fromisoformat(expected["start_date"])
        assert period.accrual_end == period.unadjusted_end == date.fromisoformat(expected["end_date"])
        assert period.payment_date == date.fromisoformat(expected["payment_date"])
        assert (period.day_count, period.day_count_days, period.day_count_denominator) == ("30E/360", 360, 360)
        assert Decimal(period.day_count_days) / period.day_count_denominator == Decimal(expected["fraction_30e360"])
        assert period.fixing_date is period.projection_start is period.projection_end is None
    assert fixed.periods[-1].payment_date == floating.periods[-1].payment_date
    assert fixed.periods[-1].flow_id != floating.periods[-1].flow_id
    assert resolve_rates_schedule(irs) == (floating, fixed)


@pytest.mark.parametrize(
    ("convention", "lag", "adjusted_end", "paid"),
    [
        ("modified_following", 0, date(2026, 10, 30), date(2026, 10, 30)),
        ("following", 0, date(2026, 11, 2), date(2026, 11, 2)),
        ("modified_following", 1, date(2026, 10, 30), date(2026, 11, 2)),
    ],
)
def test_target_month_end_adjustment_and_separate_payment_lag(abc_terms, convention, lag, adjusted_end, paid):
    payload = abc_terms[0].model_dump(mode="json")
    payload.update(effective_date="2026-07-31", maturity_date="2026-10-31")
    payload["floating_leg"].update(business_day_convention=convention, payment_lag_business_days=lag)
    coupon, principal = resolve_rates_schedule(FRNTerms.model_validate(payload))
    period, = coupon.periods
    assert period.unadjusted_end == date(2026, 10, 31)
    assert period.accrual_end == period.projection_end == adjusted_end
    assert period.payment_date == principal.events[0].date == paid


def test_30e_360_caps_day_31_without_moving_february_or_losing_the_roll_anchor(abc_terms):
    payload = abc_terms[1].model_dump(mode="json")
    payload.update(effective_date="2025-01-31", maturity_date="2025-07-31")
    payload["fixed_leg"]["frequency_months"] = 1
    _, fixed = resolve_rates_schedule(IRSTerms.model_validate(payload))
    first, second = fixed.periods[:2]
    assert (first.unadjusted_end, second.unadjusted_end) == (date(2025, 2, 28), date(2025, 3, 31))
    assert (first.day_count_days, second.day_count_days) == (28, 32)


def test_target_fixing_counts_back_through_easter(abc_terms):
    payload = abc_terms[0].model_dump(mode="json")
    payload.update(effective_date="2026-04-07", maturity_date="2026-07-07")
    floating, _ = resolve_rates_schedule(FRNTerms.model_validate(payload))
    assert floating.periods[0].fixing_date == date(2026, 4, 1)


def test_draft_with_dates_and_missing_coupon_still_resolves_the_same_schedule(abc_terms):
    _, irs = abc_terms
    payload = irs.model_dump(mode="json")
    payload["fixed_leg"]["coupon_rate"] = None
    payload["floating_leg"]["margin_bps"] = None
    assert resolve_rates_schedule(IRSTerms.model_validate(payload)) == resolve_rates_schedule(irs)


@pytest.mark.parametrize(
    ("leg_updates", "term_updates", "diagnostic"),
    [
        ({"calendar": "UNKNOWN"}, {}, "calendrier de règlement inconnu"),
        ({"fixing_calendar": "UNKNOWN"}, {}, "calendrier de fixing inconnu"),
        ({"frequency_months": 6}, {}, "fréquence trimestrielle"),
        ({}, {"maturity_date": "2028-09-20"}, "stub non pris en charge"),
        ({}, {"effective_date": None}, "dates d’effet et de maturité sont requises"),
    ],
)
def test_unknown_or_incomplete_schedule_is_refused(abc_terms, leg_updates, term_updates, diagnostic):
    payload = abc_terms[0].model_dump(mode="json")
    payload.update(term_updates)
    payload["floating_leg"].update(leg_updates)
    with pytest.raises(ValueError, match=diagnostic):
        resolve_rates_schedule(FRNTerms.model_validate(payload))
