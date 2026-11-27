"""Reproducible exact-time credit Monte Carlo and independent reference checks."""
from math import asin, comb, exp, log, pi

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.product.credit_pricing import CreditQuote, SurvivalCurve, calibrate_survival, quarterly_coupons
from backend.app.core.product.exotic_credit_mc import (
    CreditMcContract, CreditMcMarginal, CreditMcMarket, CreditMcRequest, CreditMcSettings,
    CreditMcError, invert_default_times, price_credit_mc, simulate_credit_mc,
)
from backend.tests.test_rates_credit_default import _cutoff, _prepare, credit_products, facts  # noqa: F401
from backend.tests.test_rates_credit_cds_schedule import cds_terms  # noqa: F401
from backend.tests.test_rates_credit_cln_schedule import cln_terms  # noqa: F401
from backend.tests.test_rates_credit_facts import july_facts  # noqa: F401


_FLAT = SurvivalCurve(maturities=(5,), hazards=(.02,))
_LOT3 = SurvivalCurve(maturities=(1, 3, 5), hazards=(.01, .02, .04))


def _member(name, curve=_FLAT, recovery=.4, loading=0):
    return CreditMcMarginal(reference_entity_id=name, curve=curve, recovery_fraction=recovery, loading=loading,
                            source_id=f"synthetic-curve-{name}", source_version=1)


def _request(kind, members, *, rank=None, paths=65_536, seed=42, factor=False, funding=0.0,
             rate=.02, estimator="plain", nominal=1_000_000.0, **terms):
    return CreditMcRequest(
        contract=CreditMcContract(kind=kind, nominal_eur=nominal, maturity_years=5, trigger_rank=rank,
                                  coupons=quarterly_coupons(5), side="BUY",
                                  **{"coupon_bps": 400.0 if kind == "cln" else 100.0, **terms}),
        market=CreditMcMarket(source_id="synthetic-recipe", source_version=1, discount_rate=rate,
                              funding_bps=funding, marginals=tuple(members),
                              **({"dependence_model": "gaussian_one_factor", "dependence_source_id": "factor-recipe",
                                  "dependence_source_version": 1} if factor else {})),
        settings=CreditMcSettings(paths=paths, seed=seed, estimator=estimator),
    )


def _change(request, **changes):
    return CreditMcRequest.model_validate({**request.model_dump(mode="json"), **changes})


def _close_components(result, expected, *, sigmas=4.5):
    for key, value in expected.items():
        assert getattr(result.reference, key) == pytest.approx(value, abs=.01, rel=0)
        sample = getattr(result.estimate, key)
        assert abs(sample.mean - value) <= sigmas * sample.standard_error + .01


def test_exact_inversion_uses_hazard_knots_skips_zero_hazards_and_stops_at_maturity():
    curve = SurvivalCurve(maturities=(1, 2, 3, 5), hazards=(0, .125, 0, .25))
    times = invert_default_times(curve, np.array([0, .0625, .125, .25, .625, .626]), 5)
    np.testing.assert_array_equal(times, [1, 1.5, 2, 3.5, 5, np.inf])
    np.testing.assert_array_equal(invert_default_times(curve, np.array([.125, .250]), 3.25), [2, np.inf])
    with pytest.raises(ValueError):
        invert_default_times(curve, np.array([-.01]), 5)


@pytest.mark.parametrize(("kind", "expected", "nominal", "delay"), [
    ("cds", dict(protection_pv_eur=688_145.26, scheduled_premium_pv_eur=451_314.46,
                 accrual_on_default_pv_eur=1430.59, dirty_pv_eur=235_400.21), 10_000_000, 0),
    ("cln", dict(coupon_pv_eur=180_525.78, survival_principal_pv_eur=794_533.60,
                 default_redemption_pv_eur=45_801.00, dirty_pv_eur=1_020_860.38), 1_000_000, 30 / 365),
])
def test_lot3_single_name_value_by_leg_with_conditioned_sampling(kind, expected, nominal, delay):
    quotes = tuple(CreditQuote(maturity_years=years, kind="par_spread", value=spread) for years, spread in (
        (1, 60.150187499589), (3, 99.511580327049), (5, 151.993987948377),
    ))
    curve = calibrate_survival(quotes, discount=.02, recovery=.4).curve
    request = _request(kind, [_member("reference", curve)], paths=250_000, seed=53, nominal=nominal,
                       default_settlement_delay_years=delay, estimator="conditional_single_name")
    result = price_credit_mc(request)
    _close_components(result, expected)
    stat = result.estimate.dirty_pv_eur
    assert stat.ci95_half_width <= nominal * .005 / 100
    assert abs(stat.mean - result.reference.dirty_pv_eur) + stat.ci95_half_width <= nominal * .01 / 100
    assert result.estimate.trigger_probability.mean == pytest.approx(1 - .878095430920561, abs=1e-14)
    assert result.estimate.trigger_probability.standard_error == 0
    for observation in result.survival:
        assert observation.reference == pytest.approx(_LOT3.survival_at(observation.time_years), abs=1e-14)
        sample = observation.estimate
        assert abs(sample.mean - observation.reference) <= 4.5 * sample.standard_error + 1e-12


@pytest.mark.parametrize(("rank", "probability", "protection", "regular", "accrual", "dirty", "tolerance", "width"), [
    (1, .2591817793, 148_355.98, 40_799.27, 308.04, 107_248.67, 1500, 600),
    (2, .0254441821, 14_306.18, 47_022.85, 30.25, -32_746.92, 600, 220),
    (3, .0008617844, 480.17, 47_451.19, 1.02, -46_972.05, 150, 45),
])
def test_independent_three_name_basket_price_and_convergence(rank, probability, protection, regular, accrual, dirty,
                                                            tolerance, width):
    p = 1 - exp(-.1)
    components = dict(protection_pv_eur=protection, scheduled_premium_pv_eur=regular,
                      accrual_on_default_pv_eur=accrual, dirty_pv_eur=dirty)
    for seed in (42, 117):
        errors = []
        for paths in (62_500, 250_000, 1_000_000):
            result = price_credit_mc(_request("basket_cds", [_member(name) for name in "BAC"],
                                              rank=rank, paths=paths, seed=seed))
            assert result.reference.method == "independent_poisson_binomial"
            assert result.provenance.independent_samples == paths
            _close_components(result, components)
            frequency = result.estimate.trigger_probability
            assert result.reference.trigger_probability == pytest.approx(probability, abs=1e-10)
            assert abs(frequency.mean - probability) <= 4.5 * frequency.standard_error
            assert sum(item.estimate.mean for item in result.default_count_at_maturity) == pytest.approx(1, abs=1e-12)
            for count, item in enumerate(result.default_count_at_maturity):
                assert item.reference == pytest.approx(comb(3, count) * p**count * (1 - p)**(3 - count), abs=1e-14)
            stat = result.estimate.dirty_pv_eur
            errors.append(stat.standard_error)
        assert errors[0] / errors[1] == pytest.approx(2.0, abs=.35)
        assert errors[1] / errors[2] == pytest.approx(2.0, abs=.20)
        assert stat.ci95_half_width <= width
        assert abs(stat.mean - dirty) + stat.ci95_half_width + result.reference.quadrature_error_estimate_eur <= tolerance


def test_gaussian_factor_has_closed_two_name_probability_and_preserves_margins():
    half_probability = SurvivalCurve(maturities=(5,), hazards=(log(2) / 5,))
    request = _request("basket_cds", [_member("A", half_probability, .5, .6), _member("B", half_probability, .5, .8)],
                       rank=2, factor=True, coupon_bps=0, rate=0, paths=250_000)
    result = price_credit_mc(request)
    joint_default = .25 + asin(.48) / (2 * pi)
    count = result.default_count_at_maturity
    assert result.reference.method == "gaussian_factor_quadrature"
    assert count[2].reference == pytest.approx(joint_default, abs=1e-11)
    assert count[1].reference + 2 * count[2].reference == pytest.approx(1, abs=1e-11)
    assert count[1].estimate.mean + 2 * count[2].estimate.mean == pytest.approx(1, abs=.007)
    assert result.reference.quadrature_error_estimate_eur < .01
    _close_components(result, dict(protection_pv_eur=500_000 * joint_default, dirty_pv_eur=500_000 * joint_default))
    matrix = np.asarray(result.provenance.gaussian_asset_correlation)
    np.testing.assert_allclose(matrix, [[1, .48], [.48, 1]], rtol=0, atol=1e-15)
    assert min(np.linalg.eigvalsh(matrix)) > 0


def test_heterogeneous_recovery_and_exact_perfect_dependence_tie_by_identifier():
    larger = SurvivalCurve(maturities=(5,), hazards=(.05,))
    request = _request("basket_cds", [_member("B", larger, .8), _member("A", _FLAT, .2)],
                       rank=1, rate=0, coupon_bps=0, paths=250_000)
    result = price_credit_mc(request)
    reference = 1_000_000 * (1 - exp(-.07 * 5)) * (.05 * .2 + .02 * .8) / .07
    _close_components(result, dict(protection_pv_eur=reference, dirty_pv_eur=reference))

    members = [_member("C", recovery=.9, loading=1), _member("A", recovery=.1, loading=1),
               _member("B", recovery=.3, loading=1)]
    correlated = _request("basket_cds", members, rank=2, factor=True, rate=0, coupon_bps=0, paths=65_536)
    result = simulate_credit_mc(correlated, retain_samples=True)
    permuted = _change(correlated, market={**correlated.market.model_dump(mode="json"),
                                           "marginals": tuple(reversed(members))})
    replay = simulate_credit_mc(permuted, retain_samples=True)
    assert result.result.reference.method == "perfect_dependence_limit"
    assert result.result.reference.protection_pv_eur == pytest.approx(700_000 * (1 - exp(-.1)), abs=1e-9)
    assert set(result.dirty_samples) == {0, 700_000}
    np.testing.assert_array_equal(result.dirty_samples, replay.dirty_samples)
    assert result.draw_fingerprint == replay.draw_fingerprint == result.result.provenance.draw_fingerprint
    assert result.result.provenance.request_fingerprint != replay.result.provenance.request_fingerprint
    assert result.result.default_count_at_maturity[1].reference == result.result.default_count_at_maturity[2].reference == 0
    with pytest.raises(ValueError):
        result.dirty_samples.setflags(write=True)


def test_single_name_basket_reduction_replay_and_paired_funding_difference():
    member = _member("underlier", _LOT3)
    single = _request("cds", [member], paths=32_768, initial_accrued_fraction=.02)
    basket = _request("basket_cds", [member], rank=1, paths=32_768, initial_accrued_fraction=.02)
    assert price_credit_mc(single).estimate == price_credit_mc(basket).estimate
    assert price_credit_mc(single).reference == price_credit_mc(basket).reference

    base = _request("cln", [member], paths=65_536, estimator="conditional_single_name")
    higher_funding = _change(base, market={**base.market.model_dump(mode="json"), "funding_bps": 100})
    first, second = (simulate_credit_mc(case, retain_samples=True) for case in (base, higher_funding))
    assert first.draw_fingerprint == second.draw_fingerprint
    assert first.result.provenance.market_fingerprint != second.result.provenance.market_fingerprint
    changes = second.dirty_samples - first.dirty_samples
    reference_change = second.result.reference.dirty_pv_eur - first.result.reference.dirty_pv_eur
    assert np.max(changes) < 0
    paired_se = np.std(changes, ddof=1) / np.sqrt(len(changes))
    assert abs(np.mean(changes) - reference_change) < 4.5 * paired_se
    assert paired_se < second.result.estimate.dirty_pv_eur.standard_error
    archived = CreditMcRequest.model_validate_json(base.model_dump_json())
    assert price_credit_mc(archived) == first.result


def test_zero_hazard_has_no_sampling_error_and_delay_can_extend_beyond_maturity():
    zero = _member("reference", SurvivalCurve(maturities=(5,), hazards=(0,)))
    result = price_credit_mc(_request("cln", [zero], paths=131_072))
    assert result.estimate.dirty_pv_eur.standard_error == 0
    assert result.estimate.trigger_probability.mean == 0
    assert result.reference.dirty_pv_eur == pytest.approx(1_094_687.17, abs=.01)
    assert result.estimate.dirty_pv_eur.mean == pytest.approx(result.reference.dirty_pv_eur, abs=1e-9)

    immediate, delayed = [simulate_credit_mc(_request("cds", [_member("reference")],
                                                       default_settlement_delay_years=delay), retain_samples=True)
                          for delay in (0, .25)]
    assert immediate.draw_fingerprint == delayed.draw_fingerprint
    assert delayed.result.reference.protection_pv_eur == pytest.approx(
        immediate.result.reference.protection_pv_eur * exp(-.02 * .25), abs=1e-10,
    )
    assert delayed.result.estimate.trigger_probability == immediate.result.estimate.trigger_probability
    assert delayed.result.estimate.scheduled_premium_pv_eur == immediate.result.estimate.scheduled_premium_pv_eur


def test_seller_reverses_net_price_and_full_recovery_cancels_protection_at_negative_rate():
    buyer = _request("cds", [_member("reference", recovery=1)], paths=65_536, rate=-.02,
                     estimator="conditional_single_name", initial_accrued_fraction=.03)
    seller = _change(buyer, contract={**buyer.contract.model_dump(mode="json"), "side": "SELL"})
    long, short = (simulate_credit_mc(case, retain_samples=True) for case in (buyer, seller))
    assert long.draw_fingerprint == short.draw_fingerprint
    np.testing.assert_array_equal(short.dirty_samples, -long.dirty_samples)
    for outcome in (long.result, short.result):
        assert outcome.reference.protection_pv_eur == outcome.estimate.protection_pv_eur.mean == 0
    assert long.result.estimate.scheduled_premium_pv_eur == short.result.estimate.scheduled_premium_pv_eur
    assert long.result.reference.dirty_pv_eur == -short.result.reference.dirty_pv_eur
    assert long.result.estimate.clean_pv_eur.mean - long.result.estimate.dirty_pv_eur.mean == pytest.approx(300)


@pytest.mark.parametrize("instrument", ["CDS", "CLN"])
def test_realized_single_name_uses_lot3_facts_and_never_draws(credit_products, facts, instrument):
    product = credit_products[instrument]
    base = _request(instrument.lower(), [_member(product.terms.reference_entity_id)], nominal=product.intent.nominal)
    base = _change(base, contract={**base.contract.model_dump(mode="json"),
                                   "coupon_bps": (product.terms.premium_leg.coupon_bps if instrument == "CDS"
                                                  else product.terms.fixed_leg.coupon_rate * 10_000)})
    pending, due, paid = [simulate_credit_mc(_change(base, realized={"product": product,
                                                                   "context": _prepare(product, _cutoff(day), facts)}),
                                             retain_samples=True) for day in (15, 19, 20)]
    assert [item.result.state for item in (pending, due, paid)] == ["recovery_pending", "settlement_pending", "settled"]
    assert pending.result.realized.economic_pv_eur is None
    assert due.result.realized.recovery_fraction == .35
    assert paid.result.realized.realized_cash_eur == due.result.realized.net_due_eur
    assert paid.result.realized.net_due_eur == 0
    assert all(item.dirty_samples is None and item.draw_fingerprint is None and item.result.estimate is None
               and item.result.provenance.independent_samples == 0 for item in (pending, due, paid))
    before_notice = _change(base, realized={"product": product, "context": _prepare(product, _cutoff(15, 9), facts)})
    with pytest.raises(CreditMcError, match="état réalisé"):
        price_credit_mc(before_notice)


def test_invalid_margins_ranks_dependency_funding_and_estimator_are_rejected():
    a, b = _member("A"), _member("B")
    with pytest.raises(ValidationError, match="admissible"):
        _request("basket_cds", [a, b], rank=3)
    with pytest.raises(ValidationError, match="dépendance déclaré"):
        _request("basket_cds", [a, _member("B", loading=.8)], rank=1)
    with pytest.raises(ValidationError, match="unitaires"):
        _request("basket_cds", [_member("A", loading=1), b], rank=1, factor=True)
    with pytest.raises(ValidationError, match="uniques"):
        _request("basket_cds", [a, a], rank=1)
    with pytest.raises(ValidationError, match="conditionnel"):
        _request("basket_cds", [a, b], rank=2, estimator="conditional_single_name")
    with pytest.raises(ValidationError, match="funding"):
        _request("cds", [a], funding=100)
    with pytest.raises(ValidationError, match="couvrir"):
        _request("cds", [_member("A", SurvivalCurve(maturities=(3,), hazards=(.02,)))])
