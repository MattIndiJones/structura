from datetime import date, datetime, timezone
from math import exp, sqrt

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm

from backend.app.core.product.exotic_rates_mc import (
    ExoticRatesTerms, FixedCashflow, ForwardPeriod, HwCurve, HwMarket, RangeAccrualCoupon, RangeObservation,
    RateCoupon, RateExercise, RatesMCSettings, SwapRate, price_exotic_rates, simulate_hull_white,
)
from backend.app.services.exotic_mtf import ExoticMtfError, _credit_populations, _rates_populations, mark_exotic_to_future
from backend.app.services.exotic_valuation import ExoticCreditScenario, ExoticRatesScenario


STAMP = {
    "valuation_date": date(2026, 9, 16), "cutoff": datetime(2026, 9, 16, 14, tzinfo=timezone.utc),
    "position_id": "mtf-test", "market_source": {"kind": "synthetic", "source_id": "test", "version": 1,
        "available_at": datetime(2026, 9, 16, 10, tzinfo=timezone.utc),
        "validated_at": datetime(2026, 9, 16, 10, tzinfo=timezone.utc)},
}


def _rates(flows, *, vol=0., exercises=()):
    curve = HwCurve(pillars=({"time": 0, "factor": 1.}, {"time": 6, "factor": exp(-.12)}))
    market = HwMarket(discount=curve, projection=curve, mean_reversion=.1, volatility=vol)
    return ExoticRatesScenario(
        **STAMP, family="rates", market=market, terms=ExoticRatesTerms(nominal_eur=100., cashflows=flows, exercises=exercises),
        settings=RatesMCSettings(paths=8192, seed=21, training_paths=2048 if exercises else None),
    )


def _credit(kind, names, *, rank=None, delay=0., dependence="independence", coupons=()):
    return ExoticCreditScenario.model_validate({
        **STAMP, "family": "credit", "credit": {
            "contract": {"kind": kind, "nominal_eur": 100., "maturity_years": 1., "coupons": coupons,
                         "coupon_bps": 0., "side": "BUY", "trigger_rank": rank, "default_settlement_delay_years": delay},
            "market": {"quality": "synthetic", "source_id": "credit", "source_version": 1, "discount_rate": 0.,
                       "marginals": [{
                           "reference_entity_id": f"name-{i}", "curve": {"maturities": [1.], "hazards": [hazard]},
                           "source_id": f"source-{i}", "source_version": 1, "recovery_fraction": recovery,
                       } for i, (hazard, recovery) in enumerate(names)], "dependence_model": dependence,
                       "dependence_source_id": "factor" if dependence != "independence" else None,
                       "dependence_source_version": 1 if dependence != "independence" else None},
            "settings": {"paths": 8192, "seed": 21, "estimator": "plain"},
        },
    })


def test_rates_sigma_zero_and_cash_paid_on_horizon_are_separate():
    scenario = _rates((FixedCashflow(flow_id="cash-t1", amount_eur=100, payment=.5),
                       FixedCashflow(flow_id="cash-t2", amount_eur=50, payment=1.)))
    result = mark_exotic_to_future(scenario, horizons_years=(.5, 1.), paths=128)
    early, maturity = result.horizons
    assert early.mean_cash_paid_eur == 100
    assert early.mean_pv_eur == pytest.approx(50 * exp(-.01))
    assert early.mean_pv_eur == pytest.approx(early.p05_pv_eur)
    assert early.active_probability == 1
    assert len(early.histogram) == 1 and early.histogram[0].count == 128
    assert maturity.mean_cash_paid_eur == 150
    assert maturity.mean_pv_eur == 0 and maturity.settled_probability == 1


def test_rates_stochastic_mark_is_the_conditional_zero_and_has_correct_quantiles():
    scenario = _rates((FixedCashflow(flow_id="principal", amount_eur=100, payment=2.),), vol=.016)
    horizon, end = .5, 2.
    mark, = mark_exotic_to_future(scenario, horizons_years=(horizon,), paths=4096).horizons
    a, sigma = scenario.market.mean_reversion, scenario.market.volatility
    b = lambda time: quad(lambda t: exp(-a * t), 0, time)[0]
    v = lambda time: sigma**2 * quad(lambda t: b(t)**2, 0, time)[0]
    var_x = sigma**2 * quad(lambda t: exp(-2*a*t), 0, horizon)[0]
    mean_log = -.02 * (end - horizon) + .5 * (v(end - horizon) - v(end) + v(horizon))
    sd_log = b(end - horizon) * sqrt(var_x)
    expected = [100 * exp(mean_log + sd_log * norm.ppf(q)) for q in (.05, .5, .95)]
    assert (mark.p05_pv_eur, mark.p50_pv_eur, mark.p95_pv_eur) == pytest.approx(expected, abs=.13)
    assert mark.standard_deviation_eur > 1 and mark.mean_cash_paid_eur == 0


def test_cms_horizon_before_fixing_and_event_boundary():
    index = SwapRate(fixed_periods=({"payment": 2, "year_fraction": 1},),
                     floating_periods=({"start": 1, "end": 2, "year_fraction": 1},))
    flow = RateCoupon(flow_id="cms", fixing=1, payment=1.25, index=index, year_fraction=.25)
    scenario = _rates((flow,))
    mark, = mark_exotic_to_future(scenario, horizons_years=(.5,), paths=64).horizons
    assert mark.mean_pv_eur == pytest.approx(100 * .25 * (exp(.02) - 1) * exp(-.02 * .75))
    with pytest.raises(ExoticMtfError) as refused:
        mark_exotic_to_future(scenario, horizons_years=(1.,), paths=64)
    assert refused.value.code == "EXOTIC_MTF_UNREALIZED_STATE"


def test_callable_contingent_value_before_exercise_uses_frozen_policy():
    flows = tuple(FixedCashflow(flow_id=f"coupon-{year}", amount_eur=4., payment=year) for year in (1, 2, 3)) + (
        FixedCashflow(flow_id="principal", amount_eur=100., payment=3, is_coupon=False),
    )
    rights = tuple(RateExercise(exercise_id=f"call-{year}", decision=year, settlement=year,
                               redemption_eur=100, owner="issuer", coupon_priority="before") for year in (1, 2))
    scenario = _rates(flows, exercises=rights)
    archive = price_exotic_rates(scenario.terms, scenario.market, scenario.settings).result.model_dump(mode="json")
    mark, = mark_exotic_to_future(scenario, horizons_years=(.5,), paths=64, archived_result=archive).horizons
    assert mark.mean_pv_eur == pytest.approx(104 * exp(-.01))
    assert mark.quadrature_refinement_eur == 0
    with pytest.raises(ExoticMtfError) as refused:
        mark_exotic_to_future(scenario, horizons_years=(.5,), paths=64)
    assert refused.value.code == "EXOTIC_MTF_EXERCISE_PROOF"


def test_stochastic_conditional_range_and_callable_discount_back_to_the_price():
    rate = ForwardPeriod(start=.75, end=1.0, year_fraction=.25)
    range_coupon = RangeAccrualCoupon(
        flow_id="range", payment=1.1, year_fraction=.25, annual_rate=.05, lower=.01, upper=.03,
        observations=(RangeObservation(
            time=-.25, index=ForwardPeriod(start=-.25, end=0, year_fraction=.25), weight=1, realized_rate=.01),
            RangeObservation(time=.75, index=rate, weight=3)),
    )
    flows = tuple(FixedCashflow(flow_id=f"coupon-{year}", amount_eur=4.0, payment=year) for year in (1, 2, 3)) + (
        FixedCashflow(flow_id="principal", amount_eur=100.0, payment=3, is_coupon=False),
    )
    rights = tuple(RateExercise(exercise_id=f"call-{year}", decision=year, settlement=year,
                               redemption_eur=100, owner="issuer", coupon_priority="before") for year in (1, 2))
    horizon = .40
    for scenario, tolerance in ((_rates((range_coupon,), vol=.01), .023), (_rates(flows, vol=.01, exercises=rights), .08)):
        value = price_exotic_rates(scenario.terms, scenario.market, scenario.settings).result
        archive = value.model_dump(mode="json")
        population, = _rates_populations(scenario, (horizon,), 4096, archive)
        discounts = simulate_hull_white(
            scenario.market, (0.0, horizon), paths=4096, seed=scenario.settings.seed, antithetic=False,
        ).discount[-1]
        assert np.mean(population.values * discounts) == pytest.approx(value.pv_eur, abs=tolerance)


def test_independent_second_to_default_grouped_by_survivors_and_not_simulated_future():
    scenario = _credit("basket_cds", [(1.1, .4), (.7, .7)], rank=2)
    h = .5
    population, = _credit_populations(scenario, (h,), 2048)
    observed = np.unique(population.values)
    # Conditional protection if only one name is alive, plus the two-name
    # Poisson-binomial expectation before the second default.
    a, b, dt = 1.1, .7, 1 - h
    second_a = quad(lambda t: a * exp(-a*t) * (1 - exp(-b*t)), 0, dt)[0]
    second_b = quad(lambda t: b * exp(-b*t) * (1 - exp(-a*t)), 0, dt)[0]
    expected = sorted([0, 60 * second_a + 30 * second_b, 60 * (1 - exp(-a*dt)), 30 * (1 - exp(-b*dt))])
    assert observed == pytest.approx(expected, abs=1e-8)
    result = mark_exotic_to_future(scenario, horizons_years=(h, 1.), paths=2048)
    assert result.horizons[0].settled_probability == pytest.approx((1 - exp(-a*h)) * (1 - exp(-b*h)), abs=.022)
    assert result.horizons[-1].settled_probability == 1 and result.horizons[-1].mean_pv_eur == 0


def test_credit_delay_preserves_pending_claim_and_later_cash_and_declines_copula():
    scenario = _credit("cln", [(3., .35)], delay=.2)
    before, end = mark_exotic_to_future(scenario, horizons_years=(.3, 1.2), paths=4096).horizons
    assert before.claim_probability == pytest.approx(exp(-3*.1) - exp(-3*.3), abs=.023)
    assert before.active_probability == pytest.approx(exp(-3*.3), abs=.023)
    assert before.mean_cash_paid_eur == pytest.approx(35 * (1 - exp(-.3)), abs=.8)
    assert end.settled_probability == 1.0 and end.mean_pv_eur == 0.0
    assert end.mean_cash_paid_eur == pytest.approx(35 * (1 - exp(-3)) + 100 * exp(-3), abs=.8)
    gaussian = _credit("basket_cds", [(1., .4), (1., .4)], rank=1, dependence="gaussian_one_factor")
    with pytest.raises(ExoticMtfError) as refused:
        mark_exotic_to_future(gaussian, horizons_years=(.5,), paths=64)
    assert refused.value.code == "EXOTIC_MTF_DEPENDENCE"
