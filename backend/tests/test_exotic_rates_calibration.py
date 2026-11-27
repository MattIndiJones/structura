"""Synthetic swaption quote conversions and out-of-sample Hull–White controls."""

from math import exp, log, sqrt

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.stats import norm

from backend.app.core.product.exotic_rates_calibration import (
    HullWhiteCalibrationError, HullWhiteCalibrationRequest, HullWhiteCalibrationResult, NormalSwaptionQuote,
    PVSwaptionQuote, ShiftedBlackSwaptionQuote, SwaptionCalibrationPoint, calibrate_hull_white,
)
from backend.app.core.product.exotic_rates_mc import (
    HwCurve, SwapRate, conditional_ois_bond, conditional_swap_rate, simulate_hull_white,
)


_A = .12
_SIGMA = .012
_NOMINAL = 1_000_000.


def _curve(*points):
    return HwCurve(pillars=[{"time": time, "factor": factor} for time, factor in points])


@pytest.fixture
def curves():
    return (
        _curve((0, 1), (.5, 1.002), (1.4, 1.005), (3, .957), (6, .869)),
        _curve((0, 1), (.5, 1.003), (1.4, 1.012), (3, .936), (6, .832)),
    )


def _df(curve, time):
    return exp(float(np.interp(time, [p.time for p in curve.pillars], [log(p.factor) for p in curve.pillars])))


def _forward_and_annuity(curves, swap):
    discount, projection = curves
    annuity = sum(_df(discount, p.payment) * p.year_fraction for p in swap.fixed_periods)
    floating = sum(_df(discount, p.end) * (_df(projection, p.start) / _df(projection, p.end) - 1)
                   for p in swap.floating_periods)
    return floating / annuity, annuity


def _swap(*dates):
    return SwapRate(
        fixed_periods=[{"payment": t2, "year_fraction": t2 - t1} for t1, t2 in zip(dates, dates[1:])],
        floating_periods=[{"start": t1, "end": t2, "year_fraction": t2 - t1} for t1, t2 in zip(dates, dates[1:])],
    )


def _exchange_option(curves, expiry, swap, strike, side, sigma=_SIGMA, a=_A, nominal=_NOMINAL):
    """One-period swaption as an exchange option on two correlated bonds."""
    discount, projection = curves
    period, = swap.floating_periods
    maturity_discount = _df(discount, period.end)
    bond_long = maturity_discount * _df(projection, period.start) / _df(projection, period.end)
    bond_short = maturity_discount * (1 + strike * period.year_fraction)
    if sigma == 0:
        return nominal * max(0, side * (bond_long - bond_short))
    decay = lambda expiry_to_date: quad(lambda t: exp(-a * t), 0, expiry_to_date)[0]
    expiry_factor_std = sigma * sqrt(quad(lambda time: exp(-2 * a * time), 0, expiry)[0])
    relative_std = expiry_factor_std * (decay(period.end - expiry) - decay(period.start - expiry))
    d = log(bond_long / bond_short) / relative_std
    return nominal * side * (bond_long * norm.cdf(side * (d + relative_std / 2))
                             - bond_short * norm.cdf(side * (d - relative_std / 2)))


def _normal_atm_point(curves, *, sigma=_SIGMA, a=_A):
    expiry = .35
    swap = _swap(.50, 1.30)
    forward, annuity = _forward_and_annuity(curves, swap)
    pv = _exchange_option(curves, expiry, swap, forward, 1, sigma=sigma, a=a)
    normal_vol = pv / (_NOMINAL * annuity * sqrt(expiry) * norm.pdf(0))
    return SwaptionCalibrationPoint(
        quote_id="normal-atm-negative", expiry=expiry, swap=swap, side="payer",
        strike=forward, nominal_eur=_NOMINAL, role="calibration", quote=NormalSwaptionQuote(volatility=normal_vol),
    )


def _shifted_point(curves):
    expiry = .20
    swap = _swap(.42, 1.13)
    nominal = 2 * _NOMINAL
    forward, annuity = _forward_and_annuity(curves, swap)
    strike, shift = -.006, .04
    pv = _exchange_option(curves, expiry, swap, strike, -1, nominal=nominal)

    def shifted_put(vol):
        price_forward, strike_forward = forward + shift, strike + shift
        total = vol * sqrt(expiry)
        d1 = log(price_forward / strike_forward) / total + total / 2
        return nominal * annuity * (strike_forward * norm.cdf(total - d1) - price_forward * norm.cdf(-d1))

    return SwaptionCalibrationPoint(
        quote_id="shifted-negative-receiver", expiry=expiry, swap=swap, side="receiver",
        strike=strike, nominal_eur=nominal, role="calibration", weight=2.,
        quote=ShiftedBlackSwaptionQuote(volatility=brentq(lambda vol: shifted_put(vol) - pv, 1e-7, 4.), shift=shift),
    )


def _pv_point(curves, *, quote_id="pv-quote", expiry=1.25, start=1.31, end=2.65, strike=.026,
              role="calibration", sigma=_SIGMA, discrepancy=0., a=_A):
    swap = _swap(start, end)
    pv = _exchange_option(curves, expiry, swap, strike, 1, sigma=sigma, a=a)
    return SwaptionCalibrationPoint(
        quote_id=quote_id, expiry=expiry, swap=swap, side="payer", strike=strike, nominal_eur=_NOMINAL,
        role=role, quote=PVSwaptionQuote(pv_eur=pv + discrepancy),
    )


def _request(curves, *points, bound=.05, a=_A):
    return HullWhiteCalibrationRequest(
        discount=curves[0], projection=curves[1], mean_reversion=a, volatility_upper_bound=bound,
        dataset_id="eur-synthetic-swaption-grid-v1", quotes=points,
    )


def test_mixed_quotes_recover_short_rate_vol_and_a_holdout_cannot_change_fit(curves):
    normal, shifted = _normal_atm_point(curves), _shifted_point(curves)
    pv = _pv_point(curves)
    holdout = _pv_point(curves, quote_id="independent-expiry-and-tenor", expiry=1.6, start=1.77, end=3.96,
                        strike=.045, role="validation")
    request = _request(curves, normal, shifted, pv, holdout)
    result = calibrate_hull_white(request)
    assert result.quality == "synthetic"
    assert result.market.mean_reversion == _A and result.market.funding_bps == 0.
    assert result.market.volatility == pytest.approx(_SIGMA, abs=3e-9)
    assert result.market.discount == curves[0] and result.market.projection == curves[1]
    assert result.volatility_at_bound is None
    assert result.calibration_rmse_eur_per_100 < 1e-7
    assert result.validation_rmse_eur_per_100 < 1e-7
    assert result == HullWhiteCalibrationResult.model_validate_json(result.model_dump_json())
    assert [row.quote for row in result.residuals] == [normal.quote, shifted.quote, pv.quote, holdout.quote]
    assert result.residuals[0].forward_swap_rate < 0 and result.residuals[1].forward_swap_rate < 0
    assert result.residuals[3].underlier_start == 1.77 and result.residuals[3].underlier_maturity == 3.96
    for point, row in zip(request.quotes, result.residuals, strict=True):
        direction = 1 if point.side == "payer" else -1
        target = _exchange_option(curves, point.expiry, point.swap, point.strike, direction, nominal=point.nominal_eur)
        assert row.market_pv_eur == pytest.approx(target, abs=2e-7)
        assert row.model_pv_eur == pytest.approx(target, abs=.001)
    revised_holdout = holdout.model_copy(update={"quote": PVSwaptionQuote(pv_eur=holdout.quote.pv_eur + 123.)})
    revised = calibrate_hull_white(_request(curves, normal, shifted, pv, revised_holdout))
    assert revised.request_fingerprint != result.request_fingerprint
    assert revised.market == result.market
    assert revised.residuals[:3] == result.residuals[:3]
    assert revised.residuals[-1].residual_eur == pytest.approx(-123., abs=.001)
    assert revised.validation_rmse_eur_per_100 == pytest.approx(.0123, abs=1e-7)


def test_holdout_multiple_coupons_matches_separate_mc_payoff_under_ois_measure(curves):
    point = _pv_point(curves)
    expiry = 1.1
    swap = _swap(1.2, 2., 2.9, 4.1)
    strike, annuity = _forward_and_annuity(curves, swap)
    calibration = calibrate_hull_white(_request(curves, point))
    market = calibration.market
    # Independent path estimate of physical entry into the underlying swap.
    paths = simulate_hull_white(market, (0., expiry), paths=2**18, seed=4442, antithetic=True)
    state, ois = paths.state[-1], paths.discount[-1]
    par = conditional_swap_rate(market, expiry, swap, state)
    annuity_at_exercise = sum(p.year_fraction * conditional_ois_bond(market, expiry, p.payment, state)
                              for p in swap.fixed_periods)
    payoff = _NOMINAL * ois * annuity_at_exercise * np.maximum(par - strike, 0)
    first, second = np.split(payoff, 2)
    independent = .5 * (first + second)
    holdout = SwaptionCalibrationPoint(
        quote_id="three-coupons-holdout", expiry=expiry, swap=swap, side="payer", strike=strike,
        nominal_eur=_NOMINAL, role="validation", quote=PVSwaptionQuote(pv_eur=independent.mean()),
    )
    result = calibrate_hull_white(_request(curves, point, holdout))
    residual = result.residuals[-1]
    assert result.market == market
    assert residual.annuity_per_eur == pytest.approx(annuity)
    assert abs(residual.residual_eur) <= 3.5 * independent.std(ddof=1) / sqrt(independent.size)


def test_calibration_respects_zero_volatility_and_constrained_fit_flags(curves):
    zero = calibrate_hull_white(_request(curves, _normal_atm_point(curves, sigma=0., a=0.), a=0.))
    assert zero.market.mean_reversion == 0.
    assert zero.market.volatility == 0.
    assert zero.volatility_at_bound == "lower"
    assert zero.calibration_rmse_eur_per_100 < 1e-12
    assert zero.validation_rmse_eur_per_100 is None
    constrained = calibrate_hull_white(_request(curves, _pv_point(curves), bound=.005))
    assert constrained.market.volatility == .005
    assert constrained.volatility_at_bound == "upper"
    assert constrained.calibration_rmse_eur_per_100 > 0
    assert constrained.residuals[0].residual_eur < 0


def test_inconsistent_quotes_use_declared_weights_in_per_100_pv_objective(curves):
    low = _pv_point(curves, quote_id="same-swap-low", sigma=.008)
    high = _pv_point(curves, quote_id="same-swap-high", sigma=.020)
    enlarged = high.model_copy(update={
        "nominal_eur": 2 * high.nominal_eur,
        "quote": PVSwaptionQuote(pv_eur=2 * high.quote.pv_eur),
        "weight": 3.,
    })
    result = calibrate_hull_white(_request(curves, low, enlarged))
    pv_target = (low.quote.pv_eur + 3 * high.quote.pv_eur) / 4
    assert .008 < result.market.volatility < .020
    assert result.residuals[0].model_pv_eur == pytest.approx(pv_target, abs=.001)
    first, second = (row.residual_eur_per_100 for row in result.residuals)
    assert result.calibration_rmse_eur_per_100 == pytest.approx(sqrt((first**2 + 3 * second**2) / 4))


def test_invalid_quote_regimes_and_missing_underlier_coverage_are_explicit(curves):
    normal = _normal_atm_point(curves)
    invalid = normal.model_copy(update={"quote": ShiftedBlackSwaptionQuote(volatility=.25, shift=.001)})
    with pytest.raises(HullWhiteCalibrationError) as invalid_shift:
        calibrate_hull_white(_request(curves, invalid))
    assert invalid_shift.value.code == "MC_CALIBRATION_BLACK_DOMAIN"

    bad_pv = _pv_point(curves, strike=.005).model_copy(update={"quote": PVSwaptionQuote(pv_eur=0.)})
    with pytest.raises(HullWhiteCalibrationError) as too_low:
        calibrate_hull_white(_request(curves, bad_pv))
    assert too_low.value.code == "MC_CALIBRATION_BELOW_INTRINSIC"

    holdout = normal.model_copy(update={"quote_id": "outside-market", "role": "validation", "swap": _swap(.5, 3.2, 6.1)})
    with pytest.raises(HullWhiteCalibrationError) as uncovered:
        calibrate_hull_white(_request(curves, normal, holdout))
    assert uncovered.value.code == "MC_CALIBRATION_CURVE_COVERAGE"
    assert "outside-market" in str(uncovered.value)

    cash_settled = {**normal.model_dump(mode="json"), "settlement": "cash"}
    with pytest.raises(ValueError, match="physical"):
        SwaptionCalibrationPoint.model_validate(cash_settled)
