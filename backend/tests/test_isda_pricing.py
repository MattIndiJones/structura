"""Reproduce the published EUR RFR converter from the archived input quotes."""

from datetime import date, datetime, timedelta
from math import exp, fsum

import pytest
from scipy.integrate import quad

from backend.app.core.product.isda_market import IsdaMarket
from backend.app.core.product.isda_pricing import (
    IsdaCdsPriceResult, IsdaPricingError, _exponential_moments, build_isda_ois_curve, price_isda_cds,
)
from backend.app.core.product.models import Product
from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.tests.test_rates_credit_cds_schedule import cds_terms
from backend.tests.test_rates_credit_isda_market import cds_product, request_data


_TRADE = date(2021, 4, 26)
_CUTOFF = datetime.fromisoformat("2021-04-26T12:00:00+02:00")


def _context(product, request_data, *, allow_draft=False):
    return prepare_native_context(
        product, valuation_date=_TRADE, cutoff=_CUTOFF,
        market=IsdaMarket.model_validate(request_data), allow_draft=allow_draft,
    )


@pytest.mark.parametrize("scenario_index", [0, 1, 2], ids=["50bp", "100bp", "150bp"])
def test_isda_converter_matches_each_workbook_row(cds_product, request_data, scenario_index):
    scenario = request_data["scenarios"][scenario_index]
    request_data["scenario_id"] = scenario["id"]
    oracle = scenario["workbook_results"]
    tolerances = request_data["comparison_tolerances"]
    context = _context(cds_product, request_data)
    result = price_isda_cds(cds_product, context)
    assert result.market_quality == "historical_benchmark"
    assert result.benchmark_id == request_data["benchmark_id"]
    assert (result.scenario_id, result.scenario_source_cells) == (scenario["id"], scenario["source_cells"])
    assert result.context_fingerprint == context.fingerprint
    assert result.clean_upfront_fraction * 100 == pytest.approx(
        oracle["clean_upfront_fraction"] * 100, rel=0, abs=tolerances["upfront_pct_of_notional_points"],
    )
    assert result.clean_price_per_100 == pytest.approx(
        oracle["clean_price_per_100"], rel=0, abs=tolerances["clean_price_per_100_points"],
    )
    assert result.cash_settlement_eur_buyer_to_seller == pytest.approx(
        oracle["cash_settlement_eur_buyer_to_seller"], rel=0, abs=tolerances["cash_eur"],
    )
    assert result.accrued_premium_eur == pytest.approx(oracle["accrued_premium_eur"], rel=0, abs=tolerances["cash_eur"])
    assert result.accrued_days == round(oracle["days_accrued"]) == 36
    assert result.quoted_spread_bps == scenario["market_inputs"]["quoted_spread_bp"]
    assert result.calibration_recovery_fraction == result.pricing_recovery_fraction == 0.4
    assert result.constant_hazard_rate > 0
    assert result.par_spread_bps == pytest.approx(result.quoted_spread_bps, abs=1e-9, rel=0)
    assert abs(result.calibration_residual_fraction) < 1e-12
    assert 0 < result.terminal_survival_fraction < 1

    assert result.valuation_date == _TRADE
    assert result.step_in_date == date(2021, 4, 27)
    assert result.initial_cash_settlement_date == date(2021, 4, 29)
    assert result.protection_end_inclusive_date == date(2026, 6, 20)
    assert result.final_premium_payment_date == date(2026, 6, 22)
    first, last = result.premium_flows[0], result.premium_flows[-1]
    assert first.accrual_start == date(2021, 3, 22)
    assert last.accrual_end_exclusive == date(2026, 6, 21)
    assert last.credit_observation_date == result.protection_end_inclusive_date
    assert last.payment_date == result.final_premium_payment_date
    assert result.terminal_survival_fraction == last.survival_fraction
    assert len(result.premium_flows) == len({flow.flow_id for flow in result.premium_flows}) == 21
    assert result.initial_settlement_flow_id not in {flow.flow_id for flow in result.premium_flows}
    assert result.protection_pv_eur > 0
    assert result.scheduled_premium_pv_eur == fsum(flow.scheduled_pv_eur for flow in result.premium_flows) < 0
    assert result.accrual_on_default_pv_eur == fsum(flow.accrual_on_default_pv_eur for flow in result.premium_flows) < 0
    assert result.dirty_pv_eur == pytest.approx(
        result.protection_pv_eur + result.scheduled_premium_pv_eur + result.accrual_on_default_pv_eur, rel=0, abs=1e-9,
    )
    assert result.dirty_pv_eur == pytest.approx(
        result.cash_settlement_eur_buyer_to_seller * result.initial_settlement_discount_factor, rel=0, abs=1e-9,
    )
    assert result.clean_pv_eur == pytest.approx(
        result.dirty_pv_eur + result.accrued_premium_eur * result.initial_settlement_discount_factor, rel=0, abs=1e-9,
    )
    assert result.position_settlement_cash_eur == -result.cash_settlement_eur_buyer_to_seller
    assert result.cs01_eur > 0
    assert IsdaCdsPriceResult.model_validate_json(result.model_dump_json()) == result


def test_ois_spot_bootstrap_reprices_every_signed_input_and_rebases_to_trade(cds_product, request_data):
    context = _context(cds_product, request_data)
    quote_set = context.market.ois_quotes
    curve = build_isda_ois_curve(quote_set)
    assert curve.anchor_date == _TRADE
    assert curve.spot_date == date(2021, 4, 28)
    assert len(curve.pillars) == 17
    assert curve.factor_at(_TRADE) == 1
    assert curve.factor_at(curve.spot_date) > 1
    assert curve.pillars[0].maturity_date == date(2021, 5, 28)
    assert next(pillar for pillar in curve.pillars if pillar.tenor == "3Y").maturity_date == date(2024, 4, 29)
    assert curve.factor_at(date(2021, 4, 29)) == pytest.approx(1.0000473706728887, rel=0, abs=1e-14)
    for pillar, quote in zip(curve.pillars, quote_set.rows, strict=True):
        assert (pillar.tenor, pillar.source_cells, pillar.input_rate_fraction) == (quote.tenor, quote.source_cells, quote.rate)
        assert pillar.repriced_rate_fraction == pytest.approx(quote.rate, abs=1e-13, rel=0)
        assert abs(pillar.residual_rate_fraction) < 1e-13
    first = curve.pillars[0]
    assert first.discount_factor / curve.factor_at(curve.spot_date) == pytest.approx(
        1 / (1 + first.input_rate_fraction * (first.maturity_date - curve.spot_date).days / 360), rel=0, abs=1e-14,
    )
    for uncovered in (_TRADE - timedelta(days=1), curve.pillars[-1].maturity_date + timedelta(days=1)):
        with pytest.raises(IsdaPricingError) as error:
            curve.factor_at(uncovered)
        assert error.value.code == "ISDA_CURVE_COVERAGE"


def test_position_reversal_leaves_the_market_quote_unchanged(cds_product, request_data):
    request_data["scenario_id"] = request_data["scenarios"][2]["id"]
    buyer = price_isda_cds(cds_product, _context(cds_product, request_data))
    seller = cds_product.model_copy(update={"intent": cds_product.intent.model_copy(update={"side": "SELL"})})
    short = price_isda_cds(seller, _context(seller, request_data))
    assert (buyer.perspective, short.perspective) == ("buy_protection", "sell_protection")
    for name in ("clean_upfront_fraction", "clean_price_per_100", "cash_settlement_eur_buyer_to_seller", "accrued_premium_eur"):
        assert getattr(short, name) == getattr(buyer, name)
    for name in (
        "position_settlement_cash_eur", "protection_pv_eur", "scheduled_premium_pv_eur",
        "accrual_on_default_pv_eur", "dirty_pv_eur", "clean_pv_eur", "cs01_eur",
    ):
        assert getattr(short, name) == -getattr(buyer, name)


def test_published_outputs_cannot_influence_the_calculation(cds_product, request_data):
    original = _context(cds_product, request_data)
    for scenario in request_data["scenarios"]:
        scenario["workbook_results"]["clean_upfront_fraction"] += 0.25
        scenario["workbook_results"]["cash_settlement_eur_buyer_to_seller"] += 1000
    altered = _context(cds_product, request_data)
    assert original == altered
    assert price_isda_cds(cds_product, original) == price_isda_cds(cds_product, altered)


def test_unbound_preview_reuses_the_exact_same_converter(cds_product, request_data):
    draft = Product(
        terms=cds_product.terms, intent=cds_product.intent, native_schedule=resolve_native_schedule(cds_product.terms).schedule,
    )
    retained = price_isda_cds(cds_product, _context(cds_product, request_data))
    preview_context = _context(draft, request_data, allow_draft=True)
    preview = price_isda_cds(draft, preview_context)
    assert preview.product_id is preview.terms_version is None
    assert preview.clean_upfront_fraction == retained.clean_upfront_fraction
    assert preview.premium_flows == retained.premium_flows
    with pytest.raises(IsdaPricingError) as error:
        price_isda_cds(cds_product, preview_context)
    assert error.value.code == "ISDA_CONTEXT_MISMATCH"


@pytest.mark.parametrize("net_exponent", [0.0, -1e-10, 1e-10, -0.02, 0.02, 0.5])
def test_segment_integrals_remain_stable_across_rate_hazard_cancellation(net_exponent):
    zero, first = _exponential_moments(net_exponent)
    assert zero == pytest.approx(quad(lambda u: exp(-net_exponent * u), 0, 1)[0], abs=1e-14, rel=0)
    assert first == pytest.approx(quad(lambda u: u * exp(-net_exponent * u), 0, 1)[0], abs=1e-14, rel=0)
