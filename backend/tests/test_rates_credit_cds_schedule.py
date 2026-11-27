"""EUR CDS converter schedule checks against the frozen grid and edge cases."""

from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from backend.app.core.calendars import is_business_day
from backend.app.core.product.cds_schedule import cds_default_accrued_days, resolve_cds_schedule
from backend.app.core.product.models import CDSTerms


_ISDA = json.loads(Path(__file__).with_name("fixtures").joinpath("rates_credit_isda.json").read_text(encoding="utf-8"))
_EXPECTED_PREMIUMS = (
    ("2021-06-21", 91), ("2021-09-20", 91), ("2021-12-20", 91),
    ("2022-03-21", 91), ("2022-06-20", 91), ("2022-09-20", 92), ("2022-12-20", 91),
    ("2023-03-20", 90), ("2023-06-20", 92), ("2023-09-20", 92), ("2023-12-20", 91),
    ("2024-03-20", 91), ("2024-06-20", 92), ("2024-09-20", 92), ("2024-12-20", 91),
    ("2025-03-20", 90), ("2025-06-20", 92), ("2025-09-22", 94), ("2025-12-22", 91),
    ("2026-03-20", 88), ("2026-06-22", 93),
)


@pytest.fixture
def cds_terms():
    dates, conventions = _ISDA["cds_chronology"], _ISDA["cds_conventions"]
    return CDSTerms.model_validate({
        "schema_version": 2,
        "payoff_mode": "native",
        "instrument_type": "CDS",
        "template_id": "cds-eur-pilot",
        "template_version": 1,
        "currency": _ISDA["contract_terms"]["currency"],
        "trade_date": dates["trade_date"],
        "effective_date": dates["step_in_date"],
        "maturity_date": dates["protection_end_inclusive_date"],
        "reference_entity_id": "synthetic-reference",
        "seniority": "senior",
        "documentation": "synthetic-cds-documentation",
        "restructuring": "synthetic-clause",
        "premium_leg": {
            "calendar": conventions["calendar"],
            "business_day_convention": conventions["premium_payment_adjustment"].lower(),
            "frequency_months": conventions["premium_frequency_months"],
            "day_count": conventions["premium_day_count"],
            "payment_lag_business_days": 0,
            "coupon_bps": _ISDA["contract_terms"]["coupon_bp"],
        },
        "step_in_lag_calendar_days": conventions["step_in_calendar_days"],
        "cash_settlement_lag_business_days": conventions["initial_settlement_business_days"],
        "accrued_on_default": True,
    })


def test_isda_eur_premium_schedule_and_protection(cds_terms):
    premium, protection, upfront = resolve_cds_schedule(cds_terms)
    assert (premium.kind, protection.kind, upfront.kind) == ("premium", "protection", "initial_settlement")
    assert (premium.calendar, premium.business_day_convention, premium.roll_rule) == (
        "weekdays_only", "following", "quarterly_20th",
    )
    assert premium.payment_lag_business_days == 0
    assert protection.step_in_lag_calendar_days == 1
    assert (upfront.calendar, upfront.business_day_convention, upfront.payment_lag_business_days) == (
        "weekdays_only", "following", 3,
    )
    assert tuple((item.payment_date.isoformat(), item.day_count_days) for item in premium.periods) == _EXPECTED_PREMIUMS
    assert [
        (period.unadjusted_end.month, period.unadjusted_end.day)
        for period in premium.periods
    ] == [(6, 20), (9, 20), (12, 20)] + [(3, 20), (6, 20), (9, 20), (12, 20)] * 4 + [(3, 20), (6, 20)]

    first, last = premium.periods[0], premium.periods[-1]
    dates = _ISDA["cds_chronology"]
    assert first.unadjusted_start == date(2021, 3, 20)
    assert first.accrual_start.isoformat() == dates["initial_accrual_start_date"]
    assert first.accrual_end == date(2021, 6, 21)
    assert first.credit_observation_date == date(2021, 6, 20)
    assert last.accrual_start == date(2026, 3, 20)
    assert last.accrual_end.isoformat() == dates["final_accrual_end_exclusive_date"]
    assert last.payment_date.isoformat() == dates["final_premium_payment_date"]
    assert last.credit_observation_date == last.unadjusted_end == cds_terms.maturity_date
    for previous, following in zip(premium.periods, premium.periods[1:]):
        assert previous.unadjusted_end == following.unadjusted_start
        assert previous.accrual_end == following.accrual_start
    for period in premium.periods:
        assert period.day_count == "ACT/360" and period.day_count_denominator == 360
        assert period.fixing_date is period.projection_start is period.projection_end is None
        assert (period.accrual_end - period.accrual_start).days == period.day_count_days
        assert period.credit_observation_date == period.accrual_end - timedelta(days=1)

    step_in, protection_end = protection.events
    assert (step_in.kind, step_in.date.isoformat()) == ("step_in", dates["step_in_date"])
    assert (protection_end.kind, protection_end.date.isoformat()) == (
        "protection_end", dates["protection_end_inclusive_date"],
    )
    assert (protection_end.date - step_in.date).days + 1 == 1881
    assert step_in.flow_id is protection_end.flow_id is None
    initial, = upfront.events
    assert (initial.kind, initial.date.isoformat()) == (
        "initial_settlement", dates["initial_cash_settlement_date"],
    )
    assert initial.accrued_days == 36
    assert sum(item.day_count_days for item in premium.periods) == initial.accrued_days + 1881 == 1917
    for scenario in _ISDA["scenarios"]:
        assert initial.accrued_days == pytest.approx(scenario["workbook_results"]["days_accrued"], abs=1e-12)
    ranks = [item.rank for item in premium.periods]
    assert ranks == list(range(1, 22))
    assert len({item.period_id for item in premium.periods}) == 21
    assert len({initial.flow_id, *(item.flow_id for item in premium.periods)}) == 22
    terms_reloaded = CDSTerms.model_validate_json(cds_terms.model_dump_json())
    assert resolve_cds_schedule(terms_reloaded) == (premium, protection, upfront)


def test_friday_trade_has_calendar_day_step_in_and_weekday_cash_lag(cds_terms):
    friday = cds_terms.model_copy(update={
        "trade_date": date(2021, 4, 23), "effective_date": date(2021, 4, 24),
    })
    _, protection, upfront = resolve_cds_schedule(friday)
    assert protection.events[0].date == date(2021, 4, 24)
    assert upfront.events[0].date == date(2021, 4, 28)
    assert upfront.events[0].accrued_days == 33

    good_friday = date(2021, 4, 2)
    assert not is_business_day(good_friday, "TARGET")
    holiday_trade = friday.model_copy(update={
        "trade_date": good_friday, "effective_date": date(2021, 4, 3),
    })
    assert resolve_cds_schedule(holiday_trade)[2].events[0].date == date(2021, 4, 7)


def test_accrual_starts_at_the_last_adjusted_roll_on_or_before_step_in(cds_terms):
    # The Sunday June 20 roll adjusts to June 21 and is still ahead at step-in.
    before_roll = cds_terms.model_copy(update={
        "trade_date": date(2021, 6, 18), "effective_date": date(2021, 6, 19),
    })
    assert resolve_cds_schedule(before_roll)[0].periods[0].accrual_start == date(2021, 3, 22)
    on_roll = cds_terms.model_copy(update={
        "trade_date": date(2023, 9, 19), "effective_date": date(2023, 9, 20),
    })
    premium, _, upfront = resolve_cds_schedule(on_roll)
    assert premium.periods[0].accrual_start == date(2023, 9, 20)
    assert upfront.events[0].accrued_days == 0


def test_weekday_maturity_is_included_in_accrual_at_unshifted_payment(cds_terms):
    friday_maturity = cds_terms.model_copy(update={"maturity_date": date(2026, 3, 20)})
    premium, protection, _ = resolve_cds_schedule(friday_maturity)
    last = premium.periods[-1]
    assert last.payment_date == last.credit_observation_date == protection.events[1].date == date(2026, 3, 20)
    assert last.accrual_end == date(2026, 3, 21)


def test_default_accrual_excludes_the_supplied_effective_date(cds_terms):
    premium, protection, upfront = resolve_cds_schedule(cds_terms)
    period = premium.periods[1]
    default_date = date(2021, 7, 15)
    assert period.accrual_start == date(2021, 6, 21)
    assert cds_default_accrued_days(period, default_date) == 24
    assert cds_default_accrued_days(period, period.accrual_start) == 0
    with pytest.raises(ValueError, match="période de prime CDS"):
        cds_default_accrued_days(period, period.accrual_end)
    assert {event.kind for leg in (premium, protection, upfront) for event in leg.events} == {
        "step_in", "protection_end", "initial_settlement",
    }


def test_coupon_amount_is_independent_of_contractual_dates(cds_terms):
    draft_premium = cds_terms.premium_leg.model_copy(update={"coupon_bps": None})
    draft = cds_terms.model_copy(update={"premium_leg": draft_premium})
    assert resolve_cds_schedule(draft) == resolve_cds_schedule(cds_terms)


@pytest.mark.parametrize(("changes", "diagnostic"), [
    ({"trade_date": None}, "incomplet"),
    ({"effective_date": None}, "incomplet"),
    ({"maturity_date": None}, "incomplet"),
    ({"effective_date": date(2021, 4, 28)}, "coïncider"),
    ({"maturity_date": date(2026, 6, 21)}, "maturité CDS"),
    ({"maturity_date": date(2021, 3, 20)}, "doit suivre la date de transaction"),
    ({"trade_date": date(2021, 4, 25)}, "transaction doit être ouvrée"),
    ({"step_in_lag_calendar_days": 0}, r"T\+1"),
    ({"cash_settlement_lag_business_days": 2}, r"T\+3"),
    ({"accrued_on_default": False}, "couru de prime au défaut"),
])
def test_invalid_or_incomplete_cds_terms_are_refused(cds_terms, changes, diagnostic):
    with pytest.raises(ValueError, match=diagnostic):
        resolve_cds_schedule(cds_terms.model_copy(update=changes))


@pytest.mark.parametrize(("changes", "diagnostic"), [
    ({"calendar": "TARGET"}, "weekdays_only"),
    ({"frequency_months": 6}, "trimestrielles"),
    ({"business_day_convention": "modified_following"}, "Following"),
    ({"payment_lag_business_days": 1}, "sans délai"),
])
def test_unqualified_premium_profiles_are_refused(cds_terms, changes, diagnostic):
    premium_leg = cds_terms.premium_leg.model_copy(update=changes)
    with pytest.raises(ValueError, match=diagnostic):
        resolve_cds_schedule(cds_terms.model_copy(update={"premium_leg": premium_leg}))
