"""Offline checks of the EUR RFR ISDA reference, before curve construction."""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def isda_reference():
    fixture_path = Path(__file__).with_name("fixtures") / "rates_credit_isda.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"), parse_float=Decimal)


def _shift_weekdays(day, count):
    step = timedelta(days=1 if count > 0 else -1)
    for _ in range(abs(count)):
        day += step
        while day.weekday() >= 5:
            day += step
    return day


def test_published_source_and_signed_ois_quotes(isda_reference):
    assert isda_reference["fixture_version"] == 1
    source = isda_reference["provenance"]
    assert source["kind"] == "published_historical_benchmark"
    assert source["archive_url"].endswith("/EUR/EUR_ESTER_20210426.zip")
    assert source["archive_size_bytes"] == 415381
    assert source["archive_sha256"] == "f859e49978d6c8f6d6cc64eff3907ac67f4a1e527c7dcb720f08c09dc5e71a9a"
    assert source["workbook_member"] == "EUR_ESTER_20210426.xlsx"
    assert source["workbook_sha256"] == "79efda2a2d3bdacc377da487a1807c206977a85026192e7c01deca5e9bdc7db5"
    assert source["redistribution_rights"] == "unverified"

    quotes = isda_reference["ois_quotes"]
    assert (quotes["currency"], quotes["index"], quotes["rate_unit"]) == ("EUR", "ESTR", "fraction")
    assert (quotes["source_sheet"], quotes["source_range"], quotes["source_type_code"]) == (
        "RFR Curve", "A3:C19", "S"
    )
    assert quotes["source_publication_timestamp"] is None
    assert quotes["intraday_eligibility"] == "unverified"
    assert quotes["readiness"] == "raw_quotes"

    rows = quotes["rows"]
    expected_tenors = ["1M", "3M", "6M", *[f"{years}Y" for years in range(1, 11)], "12Y", "15Y", "20Y", "30Y"]
    assert [row["tenor"] for row in rows] == expected_tenors
    assert [row["source_cells"] for row in rows] == [f"A{index}:C{index}" for index in range(3, 20)]
    rates = {row["tenor"]: row["rate"] for row in rows}
    assert all(rates[tenor] < 0 for tenor in expected_tenors[:13])
    assert all(rates[tenor] > 0 for tenor in expected_tenors[13:])
    assert rates["1M"] == Decimal("-0.005683")
    assert rates["1Y"] == Decimal("-0.005760")
    assert rates["10Y"] == Decimal("-0.000780")
    assert rates["12Y"] == Decimal("0.000431")
    assert rates["30Y"] == Decimal("0.003360")


def test_cds_and_ois_chronologies_have_distinct_date_roles(isda_reference):
    cds = {role: date.fromisoformat(value) for role, value in isda_reference["cds_chronology"].items()}
    ois_quotes = isda_reference["ois_quotes"]
    ois = {role: date.fromisoformat(value) for role, value in ois_quotes["chronology"].items()}
    cds_conventions = isda_reference["cds_conventions"]
    ois_conventions = ois_quotes["conventions"]
    assert cds_conventions["calendar"] == ois_conventions["calendar"] == "weekdays_only"
    assert cds_conventions["premium_day_count"] == ois_conventions["fixed_day_count"] == "ACT/360"
    assert cds_conventions["premium_payment_adjustment"] == "Following"
    assert ois_conventions["payment_adjustment"] == "Modified Following"
    assert ois_conventions["specification_date"] == "2021-04-07"

    trade_date = cds["trade_date"]
    assert trade_date == ois["anchor_date"] == date(2021, 4, 26)
    assert ois_conventions["locked_rate_business_days"] == -1
    assert ois_conventions["spot_business_days"] == 2
    assert cds_conventions["step_in_calendar_days"] == 1
    assert cds_conventions["initial_settlement_business_days"] == 3
    assert ois["locked_rate_date"] == _shift_weekdays(trade_date, -1) == date(2021, 4, 23)
    assert ois["spot_date"] == _shift_weekdays(trade_date, 2) == date(2021, 4, 28)
    assert cds["step_in_date"] == trade_date + timedelta(days=1) == date(2021, 4, 27)
    assert cds["initial_cash_settlement_date"] == _shift_weekdays(trade_date, 3) == date(2021, 4, 29)
    assert cds["initial_accrual_start_date"] == date(2021, 3, 22)
    assert (cds["step_in_date"] - cds["initial_accrual_start_date"]).days == 36
    assert cds["protection_end_inclusive_date"] == date(2026, 6, 20)
    assert cds["final_accrual_end_exclusive_date"] == date(2026, 6, 21)
    assert cds["final_premium_payment_date"] == date(2026, 6, 22)
    assert cds["final_accrual_end_exclusive_date"] - cds["protection_end_inclusive_date"] == timedelta(days=1)
    assert cds["final_premium_payment_date"] - cds["protection_end_inclusive_date"] == timedelta(days=2)


def test_scenarios_reference_separate_workbook_rows(isda_reference):
    source = isda_reference["scenario_source"]
    assert source["sheet"] == "Test Grid"
    assert list(source["columns"].values()) == list("ABCDEFGHIJKLM")
    scenarios = isda_reference["scenarios"]
    assert [(case["id"], case["source_cells"]) for case in scenarios] == [
        ("isda-eur-estr-20210426-50bp", "A2407:M2407"),
        ("isda-eur-estr-20210426-100bp", "A2427:M2427"),
        ("isda-eur-estr-20210426-150bp", "A2447:M2447"),
    ]
    assert isda_reference["contract_terms"]["notional_evidence"]["workbook_reference"] == "'Test Grid'!#REF!"


@pytest.mark.parametrize(
    ("spread_bp", "upfront_percent", "settlement_eur"),
    [
        (50, "-2.591616314313", "-269161.63"),
        (100, "0", "-10000.00"),
        (150, "2.482356060193", "238235.61"),
    ],
)
def test_workbook_clean_price_accrual_and_buyer_to_seller_settlement(
    isda_reference, spread_bp, upfront_percent, settlement_eur
):
    scenario_id = f"{isda_reference['benchmark_id']}-{spread_bp}bp"
    scenario = next(case for case in isda_reference["scenarios"] if case["id"] == scenario_id)
    assert scenario["market_inputs"] == {
        "quoted_spread_bp": spread_bp,
        "calibration_recovery_fraction": Decimal("0.4"),
    }
    terms = isda_reference["contract_terms"]
    assert terms["position"] == "PROTECTION_BUYER"
    assert (terms["currency"], terms["coupon_bp"]) == ("EUR", 100)
    coupon_fraction = Decimal(terms["coupon_bp"]) / 10_000

    outputs = scenario["workbook_results"]
    chronology = isda_reference["cds_chronology"]
    accrual_start = date.fromisoformat(chronology["initial_accrual_start_date"])
    step_in = date.fromisoformat(chronology["step_in_date"])
    days_accrued = (step_in - accrual_start).days
    # The source cells contain binary floating-point noise around integer days.
    assert days_accrued == 36
    assert abs(outputs["days_accrued"] - days_accrued) < Decimal("1e-10")
    accrual_fraction = Decimal(days_accrued) / 360
    assert terms["notional_eur"] == 10_000_000
    assert round(outputs["accrued_premium_eur"] / (coupon_fraction * accrual_fraction), 2) == terms["notional_eur"]

    tolerance = isda_reference["comparison_tolerances"]
    assert tolerance == {
        "cash_eur": Decimal("0.01"),
        "upfront_pct_of_notional_points": Decimal("0.0000001"),
        "clean_price_per_100_points": Decimal("0.0000001"),
    }
    upfront = outputs["clean_upfront_fraction"]
    settlement = outputs["cash_settlement_eur_buyer_to_seller"]
    assert abs(100 * upfront - Decimal(upfront_percent)) <= tolerance["upfront_pct_of_notional_points"]
    assert abs(outputs["clean_price_per_100"] - 100 * (1 - upfront)) <= tolerance["clean_price_per_100_points"]
    assert abs(outputs["accrued_premium_eur"] - 10_000) <= tolerance["cash_eur"]
    assert abs(settlement - Decimal(settlement_eur)) <= tolerance["cash_eur"]
    assert abs(settlement - (terms["notional_eur"] * upfront - outputs["accrued_premium_eur"])) <= tolerance["cash_eur"]
    if upfront:
        notional_from_settlement = (settlement + outputs["accrued_premium_eur"]) / upfront
        assert round(notional_from_settlement, 2) == terms["notional_eur"]
