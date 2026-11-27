"""Restricted vector PayScript runs the same qualified Hull–White coupon events."""

from math import exp

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.product.exotic_rates_mc import (
    ExoticRatesTerms, ForwardPeriod, RangeAccrualCoupon, RangeObservation, RateCoupon, RateExercise,
    RatesMCSettings, price_exotic_rates,
)
from backend.app.core.product.exotic_rates_payscript import (
    ExoticRatesScript, ExoticRatesScriptError, compile_exotic_rates_script,
)
from backend.tests.test_exotic_rates_mc import _swap, flat, nonflat  # noqa: F401


def _script(event, expression, declarations="", **values):
    source = f'{declarations}\nAT {event}:\n  PAY {expression} "Coupon # témoin"'
    return ExoticRatesScript(profile="rates-exotic-coupon-v1", source=source, **({"parameters": values} if values else {}))


def _terms(*flows, exercises=()):
    return ExoticRatesTerms(nominal_eur=1e6, cashflows=flows, exercises=exercises)


_MC = RatesMCSettings(paths=32_768, seed=713)


def test_cms_caplet_script_runs_on_same_paths_and_honours_effective_parameters(flat):
    resolved = dict(flow_id="caplet", fixing=1., payment=1.25, index=_swap(1., 5), year_fraction=.25)
    vanilla = RateCoupon(**resolved, payoff="caplet", strike=.02)
    callback = _script("CMS_COUPON", "MAX(CMS_RATE - STRIKE_LEVEL, 0) * YEAR_FRACTION",
                       "PARAM STRIKE_LEVEL = 2%")
    scripted = _terms(RateCoupon(**resolved, payscript=callback))
    benchmark, valuation = [price_exotic_rates(terms, flat, _MC) for terms in (_terms(vanilla), scripted)]
    np.testing.assert_allclose(valuation.independent_pv_eur, benchmark.independent_pv_eur, rtol=1e-14, atol=1e-11)
    assert valuation.result.draw_fingerprint == benchmark.result.draw_fingerprint
    assert "payscript_metadata" not in benchmark.result.model_dump(mode="json")
    meta, = valuation.result.payscript_metadata
    assert meta.flow_id == "caplet" and meta.label == "Coupon # témoin"
    assert meta.profile == callback.profile and meta.output_unit == "fraction_of_nominal"
    assert meta.observables == ("CMS_RATE", "YEAR_FRACTION")
    parameter, = meta.parameters
    assert (parameter.name, parameter.value, parameter.unit) == ("STRIKE_LEVEL", .02, "decimal_fraction")

    effective = callback.model_copy(update={"parameters": type(callback.parameters)({"strike_level": .025})})
    changed = _terms(RateCoupon(**resolved, payscript=effective))
    greater_strike = price_exotic_rates(changed, flat, _MC)
    assert greater_strike.result.payscript_metadata[0].source_hash == meta.source_hash
    assert greater_strike.result.payscript_metadata[0].parameters[0].value == .025
    assert greater_strike.result.pv_eur < valuation.result.pv_eur
    replay = price_exotic_rates(ExoticRatesTerms.model_validate_json(scripted.model_dump_json()), flat, _MC)
    assert replay.result == valuation.result
    np.testing.assert_array_equal(replay.independent_pv_eur, valuation.independent_pv_eur)


def test_cms_spread_script_matches_steepener_with_qualified_basis_and_acquired_fixing(nonflat):
    callback = _script("CMS_SPREAD_COUPON", "YEAR_FRACTION * MIN(MAX(MARGIN_LEVEL + GEAR * CMS_SPREAD, 0), CAP_LEVEL)",
                       "PARAM MARGIN_LEVEL = 0.6%\nPARAM GEAR = 3\nPARAM CAP_LEVEL = 2.5%")
    for fixing, realized_rate in ((.75, None), (0, .01)):
        resolved = dict(flow_id="steepener", fixing=fixing, payment=1.05, index=_swap(.75, 4), spread_index=_swap(.75, 2),
                        year_fraction=.25, realized_rate=realized_rate)
        script = RateCoupon(**resolved, payscript=callback)
        vanilla = RateCoupon(**resolved, margin=.006, gearing=3, floor=0, cap=.025)
        before, after = [price_exotic_rates(_terms(flow), nonflat, _MC) for flow in (vanilla, script)]
        np.testing.assert_allclose(before.independent_pv_eur, after.independent_pv_eur, rtol=1e-14, atol=1e-11)
        assert after.result.payscript_metadata[0].observables == ("CMS_SPREAD", "YEAR_FRACTION")


def test_range_callback_uses_contractual_weights_and_boundaries_and_can_apply_coupon_gate(flat):
    index = ForwardPeriod(start=0, end=.25, year_fraction=.25)
    core = dict(flow_id="range", payment=.25, year_fraction=.25, annual_rate=.05, lower=.01, upper=.03,
                lower_inclusive=False, upper_inclusive=True, observations=tuple(
                    RangeObservation(time=time, index=index, weight=weight, realized_rate=rate)
                    for time, weight, rate in ((-.2, 1, .01), (-.1, 3, .02), (0, 1, .03))
                ))
    market = flat.model_copy(update={"volatility": 0.})
    callback = _script("RANGE_COUPON", "RANGE_FRACTION * ANNUAL_RATE * YEAR_FRACTION")
    plain, scripted = [price_exotic_rates(_terms(RangeAccrualCoupon(**core, payscript=script)), market, _MC)
                       for script in (None, callback)]
    expected_pv = 1e6 * (4 / 5) * .05 * .25 * exp(-.02 * .25)
    assert scripted.result.pv_eur == pytest.approx(expected_pv, abs=1e-9)
    assert scripted.result.pv_eur == pytest.approx(plain.result.pv_eur, abs=1e-9)
    gate = _script("RANGE_COUPON", "ANNUAL_RATE * YEAR_FRACTION * INDIC(RANGE_FRACTION > THRESHOLD)", "PARAM THRESHOLD = 80%")
    assert price_exotic_rates(_terms(RangeAccrualCoupon(**core, payscript=gate)), market, _MC).result.pv_eur == 0


@pytest.mark.parametrize("body", [
    "PAY S[1]", "PAY CMS_SPREAD", "PAY IF(CMS_RATE)", "PAY 1 ** 200", "PAY CMS_RATE(1)",
    "PAY INDIC(0 < CMS_RATE < .03)", "PAY INDIC(CMS_RATE)", "PAY MAX(CMS_RATE, 0, CMS_RATE)",
    "PAY INDIC(CMS_RATE > 0 AND CMS_RATE < .03)", "PAY (CMS_RATE, CMS_RATE)",
    "STOP", "SET EXERCISE = 1", "PAY CMS_RATE\n  PAY 1", "PAY CMS_RATE\nAT 2:\n  PAY 1",
])
def test_profile_rejects_non_event_observables_memory_commands_and_unqualified_expression_forms(body):
    code = ExoticRatesScript(profile="rates-exotic-coupon-v1", source=f"AT CMS_COUPON:\n  {body}")
    with pytest.raises(ExoticRatesScriptError):
        compile_exotic_rates_script(code, event="CMS_COUPON", flow_id="test")


def test_profile_does_not_invent_parameters_or_accept_non_finite_factors():
    missing = _script("CMS_COUPON", "CMS_RATE + MARGIN_LEVEL", "PARAM MARGIN_LEVEL")
    with pytest.raises(ExoticRatesScriptError, match="MARGIN_LEVEL"):
        compile_exotic_rates_script(missing, event="CMS_COUPON", flow_id="test")
    operation = compile_exotic_rates_script(_script("CMS_COUPON", "YEAR_FRACTION / CMS_RATE"),
                                            event="CMS_COUPON", flow_id="test")
    with pytest.raises(ExoticRatesScriptError, match="numérique"):
        operation.evaluate(2, CMS_RATE=np.array([.02, 0]), YEAR_FRACTION=.25)
    with pytest.raises(ExoticRatesScriptError, match="observables"):
        operation.evaluate(2, CMS_RATE=.02, INDEX=2)


def test_template_payoff_coordinates_and_optimal_exercise_do_not_mix_with_script():
    script = _script("CMS_COUPON", "YEAR_FRACTION * CMS_RATE")
    kwargs = dict(flow_id="cms", fixing=1., payment=1.25, index=_swap(1., 5), year_fraction=.25, payscript=script)
    with pytest.raises(ValidationError, match="propres paramètres"):
        RateCoupon(**kwargs, payoff="caplet", strike=.02)
    with pytest.raises(ValidationError, match="indices CMS"):
        RateCoupon(**{**kwargs, "index": ForwardPeriod(start=1, end=1.25, year_fraction=.25)})
    exercise = RateExercise(exercise_id="call", decision=.75, settlement=.75, redemption_eur=1e6,
                            owner="issuer", coupon_priority="before")
    with pytest.raises(ValidationError, match="flux fixes"):
        _terms(RateCoupon(**kwargs), exercises=(exercise,))
