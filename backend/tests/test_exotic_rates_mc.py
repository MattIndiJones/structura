"""Independent payment-measure and deterministic witnesses for native rates MC."""

from functools import lru_cache
from math import exp, log, sqrt

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import ndtr, roots_hermitenorm

from backend.app.core.product.exotic_rates_mc import (
    ExoticRatesTerms, FixedCashflow, ForwardPeriod, HwCurve, HwMarket, RangeAccrualCoupon,
    RangeObservation, RateCoupon, RateExercise, RatesMCError, RatesMCResult, RatesMCSettings,
    SwapRate, conditional_ois_bond, paired_rates_mc_difference, price_exotic_rates, simulate_hull_white,
)
from backend.app.core.product.models import Product
from backend.app.core.product.native_market import prepare_native_context
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_pilot import pilot_market, pilot_payment, pilot_terms
from backend.app.core.product.rates_pricing import price_rates


def _curve(*nodes):
    return HwCurve(pillars=[{"time": t, "factor": factor} for t, factor in nodes])


@pytest.fixture
def flat():
    curve = _curve((0, 1), (6, exp(-.02 * 6)))
    return HwMarket(discount=curve, projection=curve, mean_reversion=.1, volatility=.01)


@pytest.fixture
def nonflat():
    return HwMarket(
        discount=_curve((0, 1), (.5, 1.002), (2, .973), (4, .887), (6, .834)),
        projection=_curve((0, 1), (.5, 1.001), (2, .944), (4, .891), (6, .803)),
        mean_reversion=.12, volatility=.013,
    )


def _swap(fixing, years):
    starts = [fixing + i for i in range(years)]
    return SwapRate(
        fixed_periods=[{"payment": start + 1, "year_fraction": 1} for start in starts],
        floating_periods=[{"start": start, "end": start + 1, "year_fraction": 1} for start in starts],
    )


def _price(market, *flows, paths=2**16, seed=713, exercises=(), training=None, degree=2):
    return price_exotic_rates(
        ExoticRatesTerms(nominal_eur=1e6, cashflows=flows, exercises=exercises), market,
        RatesMCSettings(paths=paths, seed=seed, training_paths=training, regression_degree=degree),
    )


@lru_cache(maxsize=1024)
def _loading(a, years):
    return quad(lambda s: exp(-a * s), 0, years, epsabs=1e-14)[0]


@lru_cache(maxsize=1024)
def _integrated_variance(a, sigma, date):
    return sigma**2 * quad(lambda s: _loading(a, s)**2, 0, date, epsabs=1e-14)[0]


def _interpolated_log_factor(curve, time):
    return float(np.interp(time, [p.time for p in curve.pillars], [log(p.factor) for p in curve.pillars]))


def _state_law(market, fixing, payment, *, origin=0., state=0.):
    a, sigma = market.mean_reversion, market.volatility
    variance = sigma**2 * quad(lambda s: exp(-2 * a * (fixing - s)), origin, fixing)[0]
    tilt = sigma**2 * quad(lambda s: exp(-a * (fixing - s)) * _loading(a, payment - s), origin, fixing)[0]
    return state * exp(-a * (fixing - origin)) - tilt, sqrt(variance)


def _conditional_curve_ref(market, curve, fixing, maturity, state):
    variance = lambda t: _integrated_variance(market.mean_reversion, market.volatility, t)
    remaining = maturity - fixing
    drift_integral = .5 * (variance(maturity) - variance(fixing))
    fitted = _interpolated_log_factor(curve, maturity) - _interpolated_log_factor(curve, fixing)
    return np.exp(fitted - drift_integral + .5 * variance(remaining)
                  - _loading(market.mean_reversion, remaining) * state)


def _forward_ref(market, fixing, index, state):
    start = _conditional_curve_ref(market, market.projection, fixing, index.start, state)
    end = _conditional_curve_ref(market, market.projection, fixing, index.end, state)
    return (start / end - 1) / index.year_fraction


def _swap_ref(market, fixing, swap, state):
    discount = lambda t: _conditional_curve_ref(market, market.discount, fixing, t, state)
    annuity = sum(period.year_fraction * discount(period.payment) for period in swap.fixed_periods)
    floating = sum(period.year_fraction * discount(period.end) * _forward_ref(market, fixing, period, state)
                   for period in swap.floating_periods)
    return floating / annuity


def _pay_df(market, time):
    return exp(_interpolated_log_factor(market.discount, time) - market.funding_bps / 10_000 * time)


def _band_probability(rate_of_state, mean, sd, lower, upper):
    def threshold(rate):
        return brentq(lambda x: rate_of_state(x) - rate, -.75, .75, xtol=1e-14)

    return ndtr((threshold(upper) - mean) / sd) - ndtr((threshold(lower) - mean) / sd)


def test_joint_ou_uses_exact_nonuniform_integral_and_reprices_two_curves(nonflat):
    times = (0., .18, .63, 1.4, 2.6)
    paths = simulate_hull_white(nonflat, times, paths=2**18, seed=27, antithetic=True)
    a, sigma = nonflat.mean_reversion, nonflat.volatility
    t = times[3]
    state = paths.state[3]
    integral = -np.log(paths.discount[3]) + nonflat.discount.log_factor(t) - .5 * _integrated_variance(a, sigma, t)
    variance_x = sigma**2 * quad(lambda s: exp(-2 * a * t * s), 0, 1)[0] * t
    covariance = sigma**2 * quad(lambda u: exp(-a * u) * _loading(a, u), 0, t)[0]
    assert np.var(state) == pytest.approx(variance_x, rel=.012)
    assert np.var(integral) == pytest.approx(_integrated_variance(a, sigma, t), rel=.012)
    assert np.cov(state, integral)[0, 1] == pytest.approx(covariance, rel=.012)

    for moment, discount in zip(times, paths.discount):
        assert discount.mean() == pytest.approx(_pay_df(nonflat, moment), abs=1e-5)
    future_zero = conditional_ois_bond(nonflat, t, times[-1], state)
    assert (paths.discount[3] * future_zero).mean() == pytest.approx(_pay_df(nonflat, times[-1]), abs=1e-5)

    forward = ForwardPeriod(start=1.5, end=2.25, year_fraction=.75)
    coupon = RateCoupon(flow_id="forward", fixing=t, payment=forward.end, index=forward, year_fraction=.75)
    market_forward_cash = 1e6 * (exp(nonflat.projection.log_factor(forward.start)
                                    - nonflat.projection.log_factor(forward.end)) - 1)
    estimate = _price(nonflat, coupon, paths=2**17).result
    benchmark = market_forward_cash * _pay_df(nonflat, forward.end)
    assert abs(estimate.pv_eur - benchmark) + (estimate.ci95_eur[1] - estimate.pv_eur) <= 100


@pytest.mark.parametrize("a", [0.0, 1e-12])
def test_brownian_limit_is_exact_for_tiny_mean_reversion(flat, a):
    paths = simulate_hull_white(flat.model_copy(update={"mean_reversion": a}), (0., .4, 1.7),
                                paths=2**15, seed=122, antithetic=True)
    last = paths.state[-1]
    integral = -np.log(paths.discount[-1]) - .02 * 1.7 - .5 * .01**2 * 1.7**3 / 3
    assert np.var(last) == pytest.approx(.01**2 * 1.7, rel=.02)
    assert np.var(integral) == pytest.approx(.01**2 * 1.7**3 / 3, rel=.02)
    assert np.cov(last, integral)[0, 1] == pytest.approx(.01**2 * 1.7**2 / 2, rel=.02)


def test_cms_cap_and_digital_converge_across_sizes_and_replicates(flat):
    fixing, payment, fraction = 1., 1.25, .25
    index = _swap(fixing, 5)
    cms = RateCoupon(flow_id="cms", fixing=fixing, payment=payment, year_fraction=fraction, index=index)
    caplet = cms.model_copy(update={"flow_id": "caplet", "payoff": "caplet", "strike": .02})
    digital = RangeAccrualCoupon(
        flow_id="digital", payment=payment, year_fraction=fraction, annual_rate=.05,
        lower=-.01, upper=.025, observations=(RangeObservation(time=fixing, index=index, weight=1),),
    )
    mean, sd = _state_law(flat, fixing, payment)
    rate = lambda x: _swap_ref(flat, fixing, index, x)
    density = lambda z: exp(-z*z/2) / sqrt(2 * np.pi)
    linear_ref = quad(lambda z: rate(mean + sd * z) * density(z), -10, 10, epsabs=1e-12)[0]
    kink = (brentq(lambda x: rate(x) - .02, -.2, .2) - mean) / sd
    cap_ref = quad(lambda z: (rate(mean + sd * z) - .02) * density(z), kink, 10, epsabs=1e-12)[0]
    probability = _band_probability(rate, mean, sd, -.01, .025)
    money_probability = _band_probability(rate, 0, sd, -.01, .025)
    assert probability == pytest.approx(.728141933, abs=1e-9)
    assert money_probability == pytest.approx(.725779934, abs=1e-9)
    benchmarks = np.array((linear_ref, cap_ref, .05 * probability)) * _pay_df(flat, payment) * 1e6 * fraction
    assert benchmarks == pytest.approx((4965.56, 791.69, 8877.05), abs=.006)

    levels = (2**13, 2**15, 2**17)
    seeds = (713, 1297, 1921)
    half_widths = []
    for n in levels:
        summaries = [[_price(flat, flow, paths=n, seed=seed).result for seed in seeds] for flow in (cms, caplet, digital)]
        means = np.array([np.mean([result.pv_eur for result in replicas]) for replicas in summaries])
        standard_errors = np.array([sqrt(sum(result.standard_error_eur**2 for result in replicas)) / len(seeds)
                                    for replicas in summaries])
        half_widths.append(1.96 * standard_errors)
    assert np.asarray(half_widths[1:]) == pytest.approx(np.asarray(half_widths[:-1]) / 2, rel=.08)
    assert (half_widths[-1] < 25).all()
    assert (np.abs(means - benchmarks) + half_widths[-1] + .01 < 50).all()


def test_multicurve_steepener_independent_reference_and_cap_floor_parity(nonflat):
    fixing, pay, fraction = .75, 1.05, .25
    long, short = _swap(fixing, 4), _swap(fixing, 2)
    steepener = RateCoupon(
        flow_id="steepener", fixing=fixing, payment=pay, year_fraction=fraction, index=long,
        spread_index=short, margin=.006, gearing=3, floor=0, cap=.025,
    )
    mean, sd = _state_law(nonflat, fixing, pay)
    states, weights = roots_hermitenorm(200)
    stress = 3 * (_swap_ref(nonflat, fixing, long, mean + sd * states)
                  - _swap_ref(nonflat, fixing, short, mean + sd * states)) + .006
    benchmark = np.average(np.clip(stress, 0, .025), weights=weights) * _pay_df(nonflat, pay) * 1e6 * fraction
    result = _price(nonflat, steepener)
    assert abs(result.result.pv_eur - benchmark) + (result.result.ci95_eur[1] - result.result.pv_eur) < 50

    same = steepener.model_copy(update={"spread_index": long, "margin": 0.0})
    assert _price(nonflat, same, paths=4096).result.pv_eur == 0
    zero_leverage = steepener.model_copy(update={"gearing": 0.0})
    clamped_margin = FixedCashflow(flow_id="margin-only", payment=pay, amount_eur=1e6 * fraction * steepener.margin)
    common_grid = FixedCashflow(flow_id="grid-anchor", payment=fixing, amount_eur=0)
    assert paired_rates_mc_difference(_price(nonflat, zero_leverage, paths=8192),
                                      _price(nonflat, clamped_margin, common_grid, paths=8192)).pv_eur == 0

    linear = steepener.model_copy(update={"spread_index": None, "floor": None, "cap": None})
    strike = .035
    cap = _price(nonflat, linear.model_copy(update={"payoff": "caplet", "strike": strike}), paths=2048)
    floor = _price(nonflat, linear.model_copy(update={"payoff": "floorlet", "strike": strike}), paths=2048)
    shifted = _price(nonflat, linear.model_copy(update={"margin": linear.margin - strike}), paths=2048)
    assert cap.independent_pv_eur - floor.independent_pv_eur == pytest.approx(shifted.independent_pv_eur, abs=1e-11)


def test_range_accrual_uses_contractual_weights_past_fixings_and_payment_measure(nonflat):
    lower, upper, payment = .01, .04, 1.5
    observations = (
        RangeObservation(time=-.1, index=ForwardPeriod(start=-.1, end=.15, year_fraction=.25),
                         weight=1, realized_rate=lower),
        RangeObservation(time=.7, index=ForwardPeriod(start=.7, end=.95, year_fraction=.25), weight=3),
        RangeObservation(time=1.1, index=ForwardPeriod(start=1.1, end=1.35, year_fraction=.25), weight=1),
    )
    coupon = RangeAccrualCoupon(
        flow_id="weighted-range", payment=payment, observations=observations, year_fraction=.25, annual_rate=.04,
        lower=lower, upper=upper,
    )
    marginal = sum(obs.weight * _band_probability(
        lambda x: _forward_ref(nonflat, obs.time, obs.index, x), *_state_law(nonflat, obs.time, payment), lower, upper,
    ) for obs in observations[1:])
    benchmark = 10_000 * (1 + marginal) / 5 * _pay_df(nonflat, payment)
    inclusive = _price(nonflat, coupon, paths=2**18)
    exclusive = _price(nonflat, coupon.model_copy(update={"lower_inclusive": False}), paths=2**18)
    result = inclusive.result
    assert result.event_times == (0., .7, 1.1, payment)
    assert abs(result.pv_eur - benchmark) + (result.ci95_eur[1] - result.pv_eur) < 50
    difference = paired_rates_mc_difference(exclusive, inclusive)
    assert difference.pv_eur == pytest.approx(2000 * _pay_df(nonflat, payment), abs=.1)
    assert difference.standard_error_eur < result.standard_error_eur / 50


def test_paired_values_preserve_draws_and_funding_only_changes_discount(flat):
    flow = RateCoupon(flow_id="swap-coupon", fixing=1, payment=1.25, year_fraction=.25, index=_swap(1., 4))
    base = _price(flat, flow, paths=1024)
    rerun = _price(flat, flow, paths=1024)
    funded = _price(flat.model_copy(update={"funding_bps": 100}), flow, paths=1024)
    assert base.result == rerun.result == RatesMCResult.model_validate_json(base.result.model_dump_json())
    assert np.array_equal(base.independent_pv_eur, rerun.independent_pv_eur)
    assert not base.independent_pv_eur.flags.writeable
    assert base.result.independent_paths == 512
    assert funded.result.flows[0].mean_amount_eur == base.result.flows[0].mean_amount_eur
    assert funded.independent_pv_eur == pytest.approx(base.independent_pv_eur * exp(-.01 * flow.payment), abs=3e-12)
    assert paired_rates_mc_difference(base, rerun).ci95_eur == (0, 0)
    assert paired_rates_mc_difference(base, funded).standard_error_eur < base.result.standard_error_eur
    with pytest.raises(RatesMCError, match="grilles ou les tirages"):
        paired_rates_mc_difference(base, _price(flat, flow, paths=1024, seed=57))
    extra_event = FixedCashflow(flow_id="zero", payment=1.1, amount_eur=0)
    with pytest.raises(RatesMCError, match="grilles ou les tirages"):
        paired_rates_mc_difference(base, _price(flat, flow, extra_event, paths=1024))


def _vanilla_terms(product, native, as_of):
    to_time = lambda day: (day - as_of).days / 365
    periods = {period.flow_id: period for leg in product.native_schedule.legs for period in leg.periods}
    cashflows = []
    for row in native.flows:
        if row.state == "paid":
            continue
        time = to_time(row.payment_date)
        if row.kind != "floating_coupon":
            cashflows.append(FixedCashflow(flow_id=row.flow_id, payment=time, amount_eur=row.amount_eur))
            continue
        period = periods[row.flow_id]
        sign = 1 if product.terms.instrument_type == "FRN" else -1
        index = ForwardPeriod(start=to_time(period.projection_start), end=to_time(period.projection_end),
                              year_fraction=period.year_fraction)
        cashflows.append(RateCoupon(
            flow_id=row.flow_id, fixing=to_time(period.fixing_date), payment=time, index=index,
            year_fraction=period.year_fraction, gearing=sign, margin=sign * row.margin_bps / 10_000,
            realized_rate=row.rate if row.fixing_state == "fixed" else None,
        ))
    return ExoticRatesTerms(nominal_eur=product.intent.nominal, cashflows=cashflows)


@pytest.mark.parametrize("case", ["A", "B", "C"])
@pytest.mark.parametrize("instrument", [0, 1], ids=["FRN", "IRS"])
def test_zero_vol_reproduces_vanilla_pv_coupon_and_ois_or_projection_dv01(case, instrument):
    market, cutoff = pilot_market(case)
    terms = pilot_terms()[instrument]
    product = Product(terms=terms, intent={"nominal": 1e6, "side": "BUY"}, native_schedule=resolve_native_schedule(terms).schedule)
    if case == "C":
        market = market.model_copy(update={"payments": (pilot_payment(product, equivalent_payoff=True),)})
    as_of = market.market_date
    native = price_rates(product, prepare_native_context(
        product, valuation_date=as_of, cutoff=cutoff, market=market, allow_draft=True,
    ))
    mc_terms = _vanilla_terms(product, native, as_of)
    to_curve = lambda curve: _curve(*(((p.date - as_of).days / 365, p.factor) for p in curve.pillars))
    hw = HwMarket(discount=to_curve(market.discount), projection=to_curve(market.projection), mean_reversion=.1, volatility=0.)
    settings = RatesMCSettings(paths=8, seed=13)
    base = price_exotic_rates(mc_terms, hw, settings)
    assert base.result.pv_eur == pytest.approx(native.economic_pv_eur, abs=1e-8)
    assert base.result.standard_error_eur == 0
    open_native = [row for row in native.flows if row.state != "paid"]
    assert [f.pv_eur for f in base.result.flows] == pytest.approx([row.pv_eur for row in open_native], abs=1e-8)
    for role in ("discount", "projection"):
        curve = getattr(hw, role)
        bumped_curve = _curve(*((p.time, p.factor * exp(-.0001 * p.time)) for p in curve.pillars))
        bumped = price_exotic_rates(mc_terms, hw.model_copy(update={role: bumped_curve}), settings)
        difference = paired_rates_mc_difference(base, bumped)
        assert difference.pv_eur == pytest.approx(getattr(native.sensitivities, f"{role}_eur"), abs=1e-8)
        assert difference.standard_error_eur == 0


def _callable_cashflows():
    return tuple(FixedCashflow(flow_id=f"coupon-{t}", payment=t, amount_eur=40_000) for t in (1, 2, 3)) + (
        FixedCashflow(flow_id="principal", payment=3, amount_eur=1e6, is_coupon=False),
    )


def _callable_reference(market, both):
    def zero(time, later, x):
        return _conditional_curve_ref(market, market.discount, time, later, x)

    def european_pass(x):
        return 40_000 * zero(1, 2, x) + 1_040_000 * zero(1, 3, x)

    # Integrate the year-2 payoff conditional on year-1 under the year-2 numeraire.
    # Split both integrations at the exercise thresholds to avoid smoothing the kink.
    threshold_at_2 = brentq(lambda x: 1_040_000 * zero(2, 3, x) - 1e6, -.3, .3)
    pdf = lambda z: exp(-z*z/2) / sqrt(2 * np.pi)

    def later_exercise(x):
        mean, sd = _state_law(market, 2, 2, origin=1, state=x)
        kink = (threshold_at_2 - mean) / sd
        below = 1e6 * ndtr(kink)
        above = quad(lambda z: 1_040_000 * zero(2, 3, mean + sd * z) * pdf(z),
                     max(-10, min(kink, 10)), 10, epsabs=.001)[0]
        return zero(1, 2, x) * (40_000 + below + above)

    continuation = later_exercise if both else european_pass
    threshold_at_1 = brentq(lambda x: continuation(x) - 1e6, -.3, .3)
    mean, sd = _state_law(market, 1, 1)
    kink = (threshold_at_1 - mean) / sd
    below = 1e6 * ndtr(kink)
    above = quad(lambda z: continuation(mean + sd * z) * pdf(z), kink, 10, epsabs=.001)[0]
    return _pay_df(market, 1) * (40_000 + below + above)


def test_callable_out_of_sample_policy_matches_backward_payment_measure(flat):
    flows = _callable_cashflows()
    rights = tuple(RateExercise(
        exercise_id=f"call-{t}", decision=t, settlement=t, redemption_eur=1e6, owner="issuer", coupon_priority="before",
    ) for t in (1, 2))
    theoretical = sum(flow.amount_eur * _pay_df(flat, flow.payment) for flow in flows)
    one, both = (_callable_reference(flat, multiple) for multiple in (False, True))
    assert (theoretical, one, both) == pytest.approx((1_057_074.64, 1_019_329.69, 1_019_266.90), abs=.01)
    no_call = _price(flat, *flows, paths=2**17).result
    assert abs(no_call.pv_eur - theoretical) + (no_call.ci95_eur[1] - no_call.pv_eur) < 100

    for profile, reference in ((rights[:1], one), (rights, both)):
        estimates = [_price(flat, *flows, paths=2**17, seed=921, training=2**15,
                            exercises=profile, degree=degree).result for degree in (2, 3)]
        for result in estimates:
            half_width = result.ci95_eur[1] - result.pv_eur
            assert half_width < 250
            assert abs(result.pv_eur - reference) + half_width + .01 < 500
            assert result.pv_eur + half_width >= reference
            assert sum(flow.pv_eur for flow in result.flows) == pytest.approx(result.pv_eur, abs=1e-8)
            principal = [flow for flow in result.flows if flow.flow_id == "principal"][0]
            calls = [flow for flow in result.flows if flow.kind == "exercise"]
            assert principal.paid_probability + sum(flow.paid_probability for flow in calls) == 1
            assert len(result.exercise_policy) == len(profile)
        assert abs(estimates[0].pv_eur - estimates[1].pv_eur) < 100
    value_draws = simulate_hull_white(flat, (0., 1.), paths=16, seed=921, antithetic=True)
    train_draws = simulate_hull_white(flat, (0., 1.), paths=16, seed=921, antithetic=True, stream="training")
    assert not np.array_equal(value_draws.state, train_draws.state)


def test_callable_priorities_notice_lag_position_and_holder_direction(flat):
    flat = flat.model_copy(update={"volatility": 0})
    decision, settlement = 1., 1.1
    right = RateExercise(exercise_id="call", decision=decision, settlement=settlement,
                         redemption_eur=1e6, owner="issuer", coupon_priority="before")
    flows = _callable_cashflows()
    settings = RatesMCSettings(paths=16, seed=2, training_paths=32)
    terms = ExoticRatesTerms(nominal_eur=1e6, cashflows=flows, exercises=(right,))
    expected = 40_000 * _pay_df(flat, decision) + 1e6 * _pay_df(flat, settlement)
    before = price_exotic_rates(terms, flat, settings).result
    assert before.pv_eur == pytest.approx(expected, abs=1e-9)
    assert before.standard_error_eur == 0
    after_right = right.model_copy(update={"coupon_priority": "after"})
    after_terms = terms.model_copy(update={"exercises": (after_right,)})
    assert price_exotic_rates(after_terms, flat, settings).result.pv_eur == pytest.approx(1e6 * _pay_df(flat, settlement))
    holder = terms.model_copy(update={"exercises": (right.model_copy(update={"owner": "holder"}),)})
    holder_value = price_exotic_rates(holder, flat, settings).result.pv_eur
    assert holder_value == pytest.approx(sum(flow.amount_eur * _pay_df(flat, flow.payment) for flow in flows))
    sell = price_exotic_rates(terms.model_copy(update={"side": "SELL"}), flat, settings).result
    assert sell.pv_eur == -before.pv_eur and sell.exercise_policy == before.exercise_policy


def test_market_and_state_gates_refuse_incomplete_inputs(flat):
    index = _swap(1., 4)
    with pytest.raises(ValueError, match="niveau acquis"):
        RateCoupon(flow_id="missing", fixing=0, payment=.2, year_fraction=.25, index=index)
    flow = RateCoupon(flow_id="cms", fixing=1, payment=1.25, year_fraction=.25, index=index)
    shorter = flat.model_copy(update={"projection": _curve((0, 1), (2.5, .95))})
    with pytest.raises(RatesMCError) as rejected:
        _price(shorter, flow, paths=32)
    assert rejected.value.code == "MC_CURVE_COVERAGE"
    with pytest.raises(ValueError, match="échantillonnage antithétique"):
        RatesMCSettings(paths=35, seed=123)
    with pytest.raises(RatesMCError) as no_exercise:
        _price(flat, flow, paths=32, training=32)
    assert no_exercise.value.code == "MC_LSM_SAMPLE"
