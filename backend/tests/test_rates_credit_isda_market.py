"""Prepare the three EUR ISDA price-converter inputs without running a model."""

from datetime import date, datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core.product.isda_market import IsdaMarket, IsdaMarketError, IsdaMarketSelection, prepare_isda_market
from backend.app.core.product.models import Product
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.tests.test_rates_credit_cds_schedule import cds_terms  # noqa: F401


_REFERENCE = Path(__file__).with_name("fixtures") / "rates_credit_isda.json"
_VALUATION_DATE = date(2021, 4, 26)
_CUTOFF = datetime.fromisoformat("2021-04-26T12:00:00+02:00")


@pytest.fixture
def request_data():
    source = json.loads(_REFERENCE.read_text(encoding="utf-8"))
    return {
        **source,
        "policy": "historical_isda_benchmark",
        "scenario_id": source["scenarios"][0]["id"],
    }


@pytest.fixture
def cds_product(cds_terms):
    schedule = resolve_native_schedule(cds_terms, product_id=7, terms_version=1).schedule
    return Product.model_validate({
        "product_id": 7, "terms_version": 1, "revision": 2,
        "terms": cds_terms, "native_schedule": schedule,
        "intent": {"nominal": 10_000_000, "side": "BUY"},
    })


def test_three_separate_inputs_keep_one_shared_raw_ois_snapshot(cds_product, request_data):
    selections = []
    for scenario in request_data["scenarios"]:
        request_data["scenario_id"] = scenario["id"]
        market = IsdaMarket.model_validate(request_data)
        result = prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF, market)
        assert result.scenario.id == scenario["id"]
        assert result.scenario.source_cells == scenario["source_cells"]
        assert result.scenario.market_inputs.model_dump() == dict(
            scenario["market_inputs"], quote_type="quoted_spread", spread_unit="basis_points",
        )
        assert result.kind == "isda" and result.policy == "historical_isda_benchmark"
        assert result.status == "ready_for_curve_construction_and_conversion"
        assert result.cds_chronology.protection_end_inclusive_date == date(2026, 6, 20)
        assert result.cds_chronology.initial_cash_settlement_date == date(2021, 4, 29)
        assert result.contract_terms.coupon_bp == 100 and result.contract_terms.notional_eur == 10_000_000
        assert result.ois_quotes.source_publication_timestamp is result.ois_quotes.source_validation_timestamp is None
        assert result.ois_quotes.intraday_eligibility == "unverified"
        assert result.ois_quotes.readiness == "raw_quotes"
        assert result.ois_quotes.chronology.anchor_date == _VALUATION_DATE
        assert result.ois_quotes.chronology.locked_rate_date == date(2021, 4, 23)
        assert result.ois_quotes.chronology.spot_date == date(2021, 4, 28)
        assert [item.model_dump() for item in result.ois_quotes.rows] == request_data["ois_quotes"]["rows"]
        assert result.ois_quotes.rows[0].rate == -0.005683
        assert result.provenance.model_dump(mode="json") == request_data["provenance"]
        assert result.scenario_source.model_dump(mode="json") == request_data["scenario_source"]
        assert IsdaMarketSelection.model_validate_json(result.model_dump_json()) == result
        selections.append(result)
    assert len({item.scenario.id for item in selections}) == 3
    assert len({item.scenario.source_cells for item in selections}) == 3
    assert {item.scenario.market_inputs.quoted_spread_bp for item in selections} == {50, 100, 150}
    assert all(item.ois_quotes == selections[0].ois_quotes for item in selections)


def test_selection_contains_no_oracle_or_curve_calibration(cds_product, request_data):
    market = IsdaMarket.model_validate(request_data)
    baseline = prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF, market)
    # The archived comparison output must never change the effective inputs.
    request_data["scenarios"][0]["workbook_results"]["clean_upfront_fraction"] = -0.75
    changed_market = IsdaMarket.model_validate(request_data)
    assert prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF, changed_market) == baseline
    assert not hasattr(baseline.scenario, "workbook_results")
    assert "comparison_tolerances" not in baseline.model_dump()
    assert "discount_factors" not in baseline.ois_quotes.model_dump()
    assert "calibrated_hazard" not in baseline.scenario.market_inputs.model_dump()
    with pytest.raises(ValidationError, match="frozen"):
        baseline.ois_quotes.rows[0].rate = -0.01
    with pytest.raises(ValidationError, match="frozen"):
        baseline.scenario.market_inputs.calibration_recovery_fraction = 0.5
    altered = baseline.model_dump(mode="json")
    altered["scenario"]["source_cells"] = "A2427:M2427"
    with pytest.raises(ValidationError, match="scénario CDS ISDA incohérentes"):
        IsdaMarketSelection.model_validate(altered)


@pytest.mark.parametrize(("path", "replacement"), [
    (("policy",), "current_market"),
    (("scenario_id",), "unknown"),
    (("provenance", "archive_sha256"), "0" * 64),
    (("provenance", "workbook_sha256"), "0" * 64),
    (("ois_quotes", "rows", 0, "rate"), 0.005683),
    (("ois_quotes", "rows", 0, "source_cells"), "A4:C4"),
    (("ois_quotes", "rate_unit"), "basis_points"),
    (("ois_quotes", "readiness"), "calibrated"),
    (("ois_quotes", "source_publication_timestamp"), "2021-04-26T09:00:00+02:00"),
    (("ois_quotes", "chronology", "spot_date"), "2021-04-29"),
    (("scenarios", 0, "source_cells"), "A2427:M2427"),
    (("scenarios", 0, "market_inputs", "spread_unit"), "fraction"),
    (("scenarios", 0, "market_inputs", "quote_type"), "clean_upfront"),
    (("scenarios", 0, "market_inputs", "calibration_recovery_fraction"), 0.35),
    (("credit_facts",), []),
])
def test_altered_evidence_and_incompatible_spread_units_are_refused(request_data, path, replacement):
    target = request_data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(ValidationError):
        IsdaMarket.model_validate(request_data)


@pytest.mark.parametrize("field", ["scenario_id", "policy"])
def test_explicit_historical_policy_and_scenario_are_required(request_data, field):
    del request_data[field]
    with pytest.raises(ValidationError, match=field):
        IsdaMarket.model_validate(request_data)


def test_archive_refuses_to_replace_an_independent_scenario_with_a_duplicate(request_data):
    request_data["scenarios"][1] = request_data["scenarios"][0]
    with pytest.raises(ValidationError, match="scénarios CDS ISDA doivent être distincts"):
        IsdaMarket.model_validate(request_data)


@pytest.mark.parametrize("changes", [
    {"reference_entity_id": "different"},
    {"documentation": "different"},
    {"seniority": "different"},
    {"restructuring": "different"},
    {"accrued_on_default": False},
])
def test_incompatible_product_is_refused(cds_product, request_data, changes):
    product = cds_product.model_copy(update={"terms": cds_product.terms.model_copy(update=changes)})
    with pytest.raises(IsdaMarketError) as exc:
        prepare_isda_market(product, _VALUATION_DATE, _CUTOFF, IsdaMarket.model_validate(request_data))
    assert exc.value.code == "ISDA_PRODUCT_INCOMPATIBLE"


def test_frozen_schedule_is_bound_to_the_product_terms_and_version(cds_product, request_data):
    market = IsdaMarket.model_validate(request_data)
    for product, code in (
        (cds_product.model_copy(update={"native_schedule": None}), "ISDA_SCHEDULE_MISSING"),
        (cds_product.model_copy(update={"terms_version": 2}), "ISDA_SCHEDULE_INCOMPATIBLE"),
        (cds_product.model_copy(update={
            "native_schedule": cds_product.native_schedule.model_copy(update={"fingerprint": "a" * 64}),
        }), "ISDA_SCHEDULE_INCOMPATIBLE"),
    ):
        with pytest.raises(IsdaMarketError) as exc:
            prepare_isda_market(product, _VALUATION_DATE, _CUTOFF, market)
        assert exc.value.code == code


def test_preparation_requires_archived_valuation_date_and_aware_cutoff(cds_product, request_data):
    market = IsdaMarket.model_validate(request_data)
    with pytest.raises(IsdaMarketError) as exc:
        prepare_isda_market(cds_product, date(2021, 4, 27), _CUTOFF, market)
    assert exc.value.code == "ISDA_DATE_INCOMPATIBLE"
    with pytest.raises(IsdaMarketError) as exc:
        prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF.replace(tzinfo=None), market)
    assert exc.value.code == "ISDA_CUTOFF_INVALID"
    utc_cutoff = datetime.fromisoformat("2021-04-26T10:00:00+00:00")
    assert prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF, market) == prepare_isda_market(
        cds_product, _VALUATION_DATE, utc_cutoff, market,
    )
    paris_midnight = datetime.fromisoformat("2021-04-25T22:00:00+00:00")
    assert prepare_isda_market(cds_product, _VALUATION_DATE, _CUTOFF, market) == prepare_isda_market(
        cds_product, _VALUATION_DATE, paris_midnight, market,
    )
    with pytest.raises(IsdaMarketError) as exc:
        prepare_isda_market(cds_product, _VALUATION_DATE, datetime.fromisoformat("2021-04-26T22:00:00+00:00"), market)
    assert exc.value.code == "ISDA_CUTOFF_INVALID"
