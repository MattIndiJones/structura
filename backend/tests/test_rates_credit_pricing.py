"""Deterministic FRN and IRS benchmarks on the frozen A/B/C witnesses."""

from datetime import datetime
from math import exp, fsum

import pytest
from pydantic import TypeAdapter

from backend.app.core.product.models import FRNTerms, Product
from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_pricing import (
    FRNPriceResult, IRSPriceResult, RatesPayoffAmount, RatesPriceResult, RatesPricingError, price_rates,
)
from backend.tests.test_rates_credit_rates_market import abc_products, market_for
from backend.tests.test_rates_credit_rates_schedule import abc_reference, abc_terms


def _prepare(product, market, cutoff):
    return prepare_native_context(product, valuation_date=market.market_date, cutoff=cutoff, market=market)


def _at(reference, case):
    return datetime.fromisoformat(reference["snapshots"][case]["cutoff_local"])


def _eur(reference):
    return pytest.approx(float(reference), rel=0, abs=0.01)


@pytest.mark.parametrize("case", ["A", "B", "C"])
def test_native_rate_prices_match_the_six_reference_contexts(case, abc_reference, abc_products, market_for):
    market = market_for(case)
    cutoff = _at(abc_reference, case)
    expected = abc_reference["snapshots"][case]
    frn, irs = (price_rates(product, _prepare(product, market, cutoff)) for product in abc_products)
    assert isinstance(frn, FRNPriceResult) and isinstance(irs, IRSPriceResult)
    assert (frn.perspective, irs.perspective) == ("long", "receive_fixed")
    assert frn.market_fingerprint == irs.market_fingerprint
    assert frn.nominal_eur == irs.nominal_eur == 1_000_000
    assert frn.payoff_mode == irs.payoff_mode == "native"
    assert frn.qualification == irs.qualification == "deterministic_reference"
    assert frn.measure.unit == "per_100_notional" and irs.measure.unit == "EUR"
    assert frn.measure.value == frn.clean_price_per_100
    assert irs.measure.value == irs.net_pv_eur
    assert frn.clean_price_per_100 == pytest.approx(float(expected["frn_clean_price"]), abs=1e-8, rel=0)
    assert frn.clean_price_per_100 == 100 * frn.clean_pv_eur / frn.nominal_eur
    assert frn.clean_pv_eur == frn.dirty_pv_eur - frn.accrued_eur
    assert frn.coupon_pv_eur + frn.principal_pv_eur == pytest.approx(frn.dirty_pv_eur, abs=1e-9, rel=0)
    assert frn.coupon_pv_eur == _eur(expected["frn_expected_eur"]["coupon_pv"])
    assert frn.principal_pv_eur == _eur(expected["frn_expected_eur"]["principal_pv"])
    assert frn.dirty_pv_eur == _eur(expected["frn_expected_eur"]["dirty_pv"])
    assert frn.clean_pv_eur == _eur(expected["frn_expected_eur"]["clean_pv"])
    assert frn.accrued_eur == _eur(expected["frn_expected_eur"]["accrued"])
    assert irs.fixed_pv_eur + irs.floating_pv_eur == pytest.approx(irs.net_pv_eur, abs=1e-9, rel=0)
    assert irs.fixed_pv_eur == _eur(expected["irs_expected_eur"]["fixed_pv"])
    assert irs.floating_pv_eur == _eur(-float(expected["irs_expected_eur"]["floating_pv_abs"]))
    assert irs.net_pv_eur == _eur(expected["irs_expected_eur"]["net_pv"])
    assert irs.fixed_coupon_rate == float(abc_reference["terms"]["irs"]["fixed_rate"])
    assert irs.par_rate == pytest.approx(float(expected["irs_par_rate"]), abs=1e-8, rel=0)
    assert irs.par_rate == -irs.floating_pv_eur / irs.fixed_annuity_eur
    if case == "A":
        assert irs.fixed_coupon_rate == pytest.approx(irs.par_rate, abs=1e-14, rel=0)
    for prefix, result in (("frn", frn), ("irs", irs)):
        assert result.sensitivities.bump_bp == 1
        assert result.sensitivities.discount_eur == _eur(expected["dv01_eur"][f"{prefix}_discount"])
        assert result.sensitivities.projection_eur == _eur(expected["dv01_eur"][f"{prefix}_projection"])
        assert fsum(item.pv_eur for item in result.flows) == result.economic_pv_eur
        assert result.detached_pv_eur == 0
        first = result.flows[0]
        assert first.state == expected["first_payment_state"]
        assert first.flow_id == abc_reference["first_payment"][f"{prefix}_flow_id"]
        assert len({item.flow_id for item in result.flows}) == len(result.flows)
        assert TypeAdapter(RatesPriceResult).validate_json(result.model_dump_json()) == result
        expected_rows = abc_reference["floating_periods"]
        for period, flow in zip(expected_rows, result.flows[:8], strict=True):
            assert (flow.period_id, flow.flow_id) == (period["period_id"], period[f"{prefix}_flow_id"])
            assert flow.payment_date.isoformat() == period["payment_date"]
            assert flow.fixing_date.isoformat() == period["fixing_date"]
            assert (flow.day_count, flow.day_count_days) == ("ACT/360", period["act360_days"])
            if case == "A":
                oracle = period["a_frn_coupon_eur"] if prefix == "frn" else -float(period["a_irs_floating_abs_eur"])
                assert flow.amount_eur == _eur(oracle)
                assert flow.rate == pytest.approx(
                    float(abc_reference["additional_references"]["forward_rate_by_act360_days"][str(flow.day_count_days)]),
                    abs=1e-12, rel=0,
                )
                assert flow.rate_origin == "projected"
    assert frn.flows[-1].payment_date == frn.flows[-2].payment_date
    assert frn.flows[-1].flow_id == abc_reference["terms"]["frn"]["principal_flow_id"]
    if case == "B":
        assert frn.flows[0].rate == irs.flows[0].rate == 0.031
        assert frn.flows[0].amount_eur == _eur(abc_reference["additional_references"]["b_first_frn_coupon_eur"])
        assert irs.flows[0].amount_eur == _eur(abc_reference["additional_references"]["b_first_irs_floating_eur"])
        days = expected["accrued_days"]
        expected_accrued = frn.nominal_eur * days / 360 * (0.031 + 0.01)
        assert frn.accrued_eur == pytest.approx(expected_accrued, abs=1e-10, rel=0)
    if case == "C":
        assert frn.flows[1].rate == irs.flows[1].rate == 0.028
        assert frn.flows[1].amount_eur == _eur(abc_reference["additional_references"]["c_second_frn_coupon_eur"])
        assert frn.cum_value_eur == _eur(abc_reference["additional_references"]["c_frn_cum_payment_dirty_pv_eur"])
        assert irs.cum_value_eur == _eur(abc_reference["additional_references"]["c_irs_cum_payment_net_pv_eur"])


@pytest.mark.parametrize("instrument_idx", [0, 1], ids=["FRN", "IRS"])
def test_detached_coupon_becomes_confirmed_cash_without_double_counting(
    abc_reference, abc_products, market_for, instrument_idx,
):
    product = abc_products[instrument_idx]
    market = market_for("C")
    boundary = abc_reference["variants"]["first_payment_boundary"]
    cutoff_before = datetime.fromisoformat(boundary["before_cutoff"])
    cutoff_paid = datetime.fromisoformat(boundary["at_cutoff"])
    before = price_rates(product, _prepare(product, market, cutoff_before))
    paid = price_rates(product, _prepare(product, market, cutoff_paid))
    first = before.flows[0]
    settled = paid.flows[0]
    assert first.flow_id == settled.flow_id
    assert (first.state, first.bucket, first.discount_factor) == ("due_open", "detached", 1)
    assert first.pv_eur == before.detached_pv_eur == first.amount_eur
    assert before.realized_cash_eur == before.cash_on_value_date_eur == 0
    assert before.economic_pv_eur == paid.economic_pv_eur + before.detached_pv_eur
    assert (settled.state, settled.bucket, settled.discount_factor) == ("paid", "cash", None)
    assert settled.pv_eur == paid.detached_pv_eur == 0
    assert settled.payment_fact_id == abc_reference["first_payment"]["fact_id"]
    assert paid.realized_cash_eur == paid.cash_on_value_date_eur == settled.amount_eur
    assert paid.cum_value_eur == _eur(before.cum_value_eur)
    assert before.flows[1:] == paid.flows[1:]
    assert before.sensitivities == paid.sensitivities
    if isinstance(before, FRNPriceResult):
        assert before.dirty_pv_eur == paid.dirty_pv_eur
        assert before.accrued_eur == paid.accrued_eur == 0
    else:
        assert before.net_pv_eur == paid.net_pv_eur
        assert before.par_rate == paid.par_rate


def test_position_sign_and_funding_do_not_change_forward_or_fixing(abc_reference, abc_products, market_for):
    market = market_for("B")
    cutoff = _at(abc_reference, "B")
    for product in abc_products:
        base = price_rates(product, _prepare(product, market, cutoff))
        inverse = product.model_copy(update={"intent": product.intent.model_copy(update={"side": "SELL"})})
        reversed_position = price_rates(inverse, _prepare(inverse, market, cutoff))
        assert reversed_position.economic_pv_eur == -base.economic_pv_eur
        assert reversed_position.sensitivities.discount_eur == -base.sensitivities.discount_eur
        assert reversed_position.sensitivities.projection_eur == -base.sensitivities.projection_eur
        assert [flow.rate for flow in reversed_position.flows] == [flow.rate for flow in base.flows]
        assert [flow.amount_eur for flow in reversed_position.flows] == [-flow.amount_eur for flow in base.flows]
        if isinstance(base, IRSPriceResult):
            assert reversed_position.par_rate == base.par_rate

        funding_market = market.model_copy(update={"frn_funding_bps": 100})
        funded = price_rates(product, _prepare(product, funding_market, cutoff))
        assert [flow.amount_eur for flow in funded.flows] == [flow.amount_eur for flow in base.flows]
        assert [flow.rate for flow in funded.flows] == [flow.rate for flow in base.flows]
        if isinstance(base, FRNPriceResult):
            assert funded.funding_spread_bps == 100
            assert funded.dirty_pv_eur < base.dirty_pv_eur
            assert funded.accrued_eur == base.accrued_eur
            for bumped, original in zip(funded.flows, base.flows, strict=True):
                days = (original.payment_date - base.valuation_date).days
                assert bumped.discount_factor == pytest.approx(
                    original.discount_factor * exp(-0.01 * days / 365), abs=1e-14, rel=0,
                )
        else:
            assert funded.net_pv_eur == base.net_pv_eur
            assert funded.sensitivities == base.sensitivities


@pytest.mark.parametrize("flat_rate", [-0.005, 0], ids=["negative", "zero"])
def test_projected_negative_and_zero_rates_remain_signed(flat_rate, abc_reference, abc_products, market_for):
    market = market_for("A")
    cutoff = _at(abc_reference, "A")
    anchor, last = market.projection.pillars
    years = (last.date - anchor.date).days / 365
    curve = market.projection.model_copy(update={"pillars": (
        anchor, last.model_copy(update={"factor": exp(-flat_rate * years)}),
    )})
    market = market.model_copy(update={"projection": curve})
    irs = abc_products[1]
    result = price_rates(irs, _prepare(irs, market, cutoff))
    first = result.flows[0]
    if flat_rate < 0:
        expected = abc_reference["variants"]["negative_projection_rate"]
        assert first.rate == pytest.approx(float(expected["first_forward_rate"]), abs=1e-12, rel=0)
        assert first.amount_eur == _eur(expected["first_irs_floating_eur"])
        assert result.par_rate < 0
    else:
        assert first.rate == first.amount_eur == result.floating_pv_eur == result.par_rate == 0


def test_payoff_adapter_is_reused_for_accrual_and_shocks(abc_reference, abc_products, market_for):
    records = []

    def payoff(inputs):
        records.append(inputs)
        amount = inputs.nominal_eur * (
            inputs.redemption_fraction if inputs.kind == "principal" else
            inputs.accrual_fraction * (inputs.rate + (inputs.margin_bps or 0) / 10_000)
        )
        return RatesPayoffAmount(amount_eur=amount, label="Coupon scripté")

    market = market_for("B")
    cutoff = _at(abc_reference, "B")
    for product in abc_products:
        records.clear()
        context = _prepare(product, market, cutoff)
        template = price_rates(product, context)
        scripted = price_rates(product, context, payoff=payoff, equivalent_payoff=True)
        assert scripted.payoff_mode == "scripted"
        assert scripted.measure.value == pytest.approx(template.measure.value, abs=1e-9, rel=0)
        assert scripted.sensitivities.discount_eur == pytest.approx(template.sensitivities.discount_eur, abs=1e-9, rel=0)
        assert scripted.sensitivities.projection_eur == pytest.approx(template.sensitivities.projection_eur, abs=1e-9, rel=0)
        assert scripted.flows[0].label == "Coupon scripté"
        first = [item for item in records if item.flow_id == scripted.flows[0].flow_id and not item.is_accrual]
        assert len(first) == 3 and all(item.rate == 0.031 and item.is_fixed for item in first)
        second = [item for item in records if item.flow_id == scripted.flows[1].flow_id]
        assert len(second) == 3 and second[0].rate == second[1].rate < second[2].rate
        if isinstance(template, FRNPriceResult):
            accrual_calls = [claim for claim in records if claim.is_accrual]
            assert len(accrual_calls) == 3
            assert all(claim.day_count_days == 42 and claim.accrual_fraction == 42 / 360 for claim in accrual_calls)
        else:
            assert scripted.par_rate == pytest.approx(template.par_rate, abs=1e-12, rel=0)
            scenario = price_rates(product, context, payoff=payoff)
            assert scenario.qualification == "deterministic_scenario"
            assert scenario.par_rate is scenario.fixed_annuity_eur is None


def test_confirmed_cash_is_not_recomputed_by_an_edited_payoff(abc_reference, abc_products, market_for):
    market = market_for("C")
    frn = abc_products[0]
    context = _prepare(frn, market, _at(abc_reference, "C"))

    def all_zero(inputs):
        assert inputs.flow_id != abc_reference["first_payment"]["frn_flow_id"]
        return RatesPayoffAmount(amount_eur=0)

    result = price_rates(frn, context, payoff=all_zero)
    assert result.dirty_pv_eur == result.economic_pv_eur == 0
    assert result.flows[0].amount_eur == result.realized_cash_eur == result.cum_value_eur
    assert result.realized_cash_eur == float(abc_reference["first_payment"]["frn_cash_eur"])


def test_price_refuses_a_context_bound_to_a_different_instrument(abc_reference, abc_products, market_for):
    market = market_for("A")
    frn, irs = abc_products
    context = _prepare(frn, market, _at(abc_reference, "A"))
    with pytest.raises(RatesPricingError) as error:
        price_rates(irs, context)
    assert error.value.code == "RATES_PRICE_CONTEXT_MISMATCH"


def test_unbound_preview_works_and_a_script_cannot_fall_back_to_template(abc_reference, abc_products, market_for):
    frn = abc_products[0]
    market = market_for("A")
    cutoff = _at(abc_reference, "A")
    resolved_draft = Product(
        terms=frn.terms, intent=frn.intent, native_schedule=resolve_native_schedule(frn.terms).schedule,
    )
    context = prepare_native_context(
        resolved_draft, valuation_date=market.market_date, cutoff=cutoff, market=market, allow_draft=True,
    )
    preview = price_rates(resolved_draft, context)
    retained = price_rates(frn, _prepare(frn, market, cutoff))
    assert preview.product_id is preview.terms_version is None
    assert preview.clean_price_per_100 == retained.clean_price_per_100
    assert preview.flows == retained.flows

    scripted_terms = FRNTerms.model_validate({
        **frn.terms.model_dump(), "payoff_mode": "scripted",
        "rates_script": {"profile": "rates-deterministic-v1", "source": "AT PRINCIPAL\n  PAY 1", "parameters": {}},
    })
    scripted_draft = Product(
        terms=scripted_terms, intent=frn.intent, native_schedule=resolve_native_schedule(scripted_terms).schedule,
    )
    context = prepare_native_context(
        scripted_draft, valuation_date=market.market_date, cutoff=cutoff, market=market, allow_draft=True,
    )
    with pytest.raises(RatesPricingError) as error:
        price_rates(scripted_draft, context)
    assert error.value.code == "RATES_PRICE_PAYOFF_REQUIRED"
