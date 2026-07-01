"""Tests for the schedule/CONSTAT calendar generator."""
import pytest
from datetime import date
from backend.app.core.schedule import (
    generate_main_schedule, generate_schedule, parse_tenor, Tenor, StubConvention as SC,
)


def test_parse_tenor():
    assert parse_tenor("3M") == Tenor(3, "M")
    assert parse_tenor("1w") == Tenor(1, "W")
    assert parse_tenor(" 12Y ") == Tenor(12, "Y")
    with pytest.raises(ValueError):
        parse_tenor("3X")
    with pytest.raises(ValueError):
        parse_tenor("M3")


def test_perfectly_aligned_schedule_has_no_stub():
    """When roll_date == start_date and the range is an exact multiple of the
    frequency, every period is exactly regular — start/end included, no stub."""
    dates = generate_main_schedule(date(2024, 1, 15), date(2025, 1, 15),
                                    date(2024, 1, 15), parse_tenor("3M"), SC.SHORT_LAST)
    assert dates == [date(2024, 1, 15), date(2024, 4, 15), date(2024, 7, 15),
                      date(2024, 10, 15), date(2025, 1, 15)]
    # every period is exactly 3 months
    for lo, hi in zip(dates[:-1], dates[1:]):
        assert hi.month - lo.month in (3, -9)   # handles year wraparound


def test_start_and_end_always_included():
    dates = generate_main_schedule(date(2024, 1, 10), date(2024, 11, 20),
                                    date(2024, 1, 15), parse_tenor("3M"), SC.SHORT_LAST)
    assert dates[0] == date(2024, 1, 10)
    assert dates[-1] == date(2024, 11, 20)


def test_short_last_stub_is_short():
    """*_LAST grids forward from roll_date; the irregular boundary lands at the
    end and is left short."""
    dates = generate_main_schedule(date(2024, 1, 10), date(2024, 11, 20),
                                    date(2024, 1, 15), parse_tenor("3M"), SC.SHORT_LAST)
    assert dates == [date(2024, 1, 10), date(2024, 1, 15), date(2024, 4, 15),
                      date(2024, 7, 15), date(2024, 10, 15), date(2024, 11, 20)]
    last_period = (dates[-1] - dates[-2]).days
    regular_period = (dates[-2] - dates[-3]).days
    assert last_period < regular_period


def test_long_last_merges_short_stub():
    """Same case as above, but LONG_LAST must merge the short final stub into
    the previous period instead of leaving it short."""
    dates = generate_main_schedule(date(2024, 1, 10), date(2024, 11, 20),
                                    date(2024, 1, 15), parse_tenor("3M"), SC.LONG_LAST)
    assert dates == [date(2024, 1, 10), date(2024, 1, 15), date(2024, 4, 15),
                      date(2024, 7, 15), date(2024, 11, 20)]
    last_period = (dates[-1] - dates[-2]).days
    regular_period = (dates[-2] - dates[-3]).days
    assert last_period > regular_period


def test_short_first_stub_is_short():
    """*_FIRST grids backward from roll_date; the irregular boundary lands at
    the start and is left short."""
    dates = generate_main_schedule(date(2024, 1, 10), date(2024, 11, 20),
                                    date(2024, 11, 20), parse_tenor("3M"), SC.SHORT_FIRST)
    assert dates == [date(2024, 1, 10), date(2024, 2, 20), date(2024, 5, 20),
                      date(2024, 8, 20), date(2024, 11, 20)]
    first_period = (dates[1] - dates[0]).days
    regular_period = (dates[2] - dates[1]).days
    assert first_period < regular_period


def test_long_first_merges_short_stub():
    dates = generate_main_schedule(date(2024, 1, 10), date(2024, 11, 20),
                                    date(2024, 11, 20), parse_tenor("3M"), SC.LONG_FIRST)
    assert dates == [date(2024, 1, 10), date(2024, 5, 20), date(2024, 8, 20),
                      date(2024, 11, 20)]
    first_period = (dates[1] - dates[0]).days
    regular_period = (dates[2] - dates[1]).days
    assert first_period > regular_period


def test_end_before_start_raises():
    with pytest.raises(ValueError):
        generate_main_schedule(date(2024, 11, 20), date(2024, 1, 10),
                                date(2024, 1, 15), parse_tenor("3M"), SC.SHORT_LAST)


def test_sub_frequency_subdivides_every_main_interval():
    """CONSTAT()() — every interval of the main schedule gets evenly subdivided
    by the sub-frequency, with no stub logic of its own (per spec)."""
    res = generate_schedule(date(2024, 1, 15), date(2024, 7, 15), date(2024, 1, 15),
                             parse_tenor("3M"), SC.SHORT_LAST, parse_tenor("1M"))
    assert res["main_dates"] == [date(2024, 1, 15), date(2024, 4, 15), date(2024, 7, 15)]
    assert res["dates"] == [
        date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15), date(2024, 4, 15),
        date(2024, 5, 15), date(2024, 6, 15), date(2024, 7, 15),
    ]


def test_no_sub_frequency_dates_equals_main_dates():
    res = generate_schedule(date(2024, 1, 15), date(2025, 1, 15), date(2024, 1, 15),
                             parse_tenor("3M"), SC.SHORT_LAST)
    assert res["dates"] == res["main_dates"]


def test_year_fractions_start_at_zero_and_increase():
    res = generate_schedule(date(2024, 1, 15), date(2025, 1, 15), date(2024, 1, 15),
                             parse_tenor("3M"), SC.SHORT_LAST)
    assert res["year_fractions"][0] == 0.0
    assert all(b > a for a, b in zip(res["year_fractions"], res["year_fractions"][1:]))
    assert abs(res["year_fractions"][-1] - 1.0) < 0.01   # ~1 year, ACT/365.25
