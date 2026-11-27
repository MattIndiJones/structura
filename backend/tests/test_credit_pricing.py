"""Independent schedule-free CDS and CLN benchmarks declared in the lot 3 plan."""

from math import exp

import pytest

from backend.app.core.product.credit_pricing import (
    CreditPricingError, CreditQuote, SurvivalCurve, calibrate_survival, default_integral, value_cds, value_cln,
)


_SPREADS = (60.150187499589, 99.511580327049, 151.993987948377)
_UPFRONTS = (-.00391599759070, -.00013887327427, .02354002074515)


@pytest.mark.parametrize(("kind", "values"), [("par_spread", _SPREADS), ("clean_upfront", _UPFRONTS)])
def test_same_survival_and_cds_legs_from_both_quote_conventions(kind, values):
    quotes = tuple(CreditQuote(maturity_years=t, kind=kind, value=value) for t, value in zip((1, 3, 5), values))
    calibrated = calibrate_survival(quotes, discount=.02, recovery=.4)
    assert calibrated.curve.hazards == pytest.approx((.01, .02, .04), abs=1e-10)
    assert [p.survival for p in calibrated.pillars] == pytest.approx(
        (.990049833749168, .951229424500714, .878095430920561), abs=1e-10,
    )
    assert all(abs(p.reprice_error_eur) <= .01 for p in calibrated.pillars)
    cds = value_cds(calibrated.curve, .02, 5, nominal=10_000_000, coupon_bps=100, recovery=.4)
    assert cds.protection_pv_eur == pytest.approx(688_145.26, abs=.01)
    assert cds.scheduled_premium_pv_eur == pytest.approx(451_314.46, abs=.01)
    assert cds.accrual_on_default_pv_eur == pytest.approx(1_430.59, abs=.01)
    assert cds.dirty_pv_eur == pytest.approx(235_400.21, abs=.01)
    assert cds.par_spread_bps == pytest.approx(_SPREADS[-1], abs=1e-9)


def test_cln_components_funding_cs01_and_jump_to_default():
    base = SurvivalCurve(maturities=(1, 3, 5), hazards=(.01, .02, .04))
    args = dict(nominal=1_000_000, coupon_rate=.04, recovery=.4, settlement_delay=30 / 365)
    cln = value_cln(base, .02, 5, **args)
    assert cln.coupon_pv_eur == pytest.approx(180_525.78, abs=.01)
    assert cln.survival_principal_pv_eur == pytest.approx(794_533.60, abs=.01)
    assert cln.default_redemption_pv_eur == pytest.approx(45_801.00, abs=.01)
    assert cln.clean_pv_eur == cln.dirty_pv_eur == pytest.approx(1_020_860.38, abs=.01)
    assert cln.par_coupon_fraction == pytest.approx(.035377860308, abs=1e-8)
    assert value_cln(base, .02, 5, funding_bps=100, **args).dirty_pv_eur == pytest.approx(976_221.15, abs=.01)
    no_default = SurvivalCurve(maturities=(5,), hazards=(0,))
    assert value_cln(no_default, .02, 5, **args).dirty_pv_eur == pytest.approx(1_094_687.17, abs=.01)
    quotes = tuple(CreditQuote(maturity_years=t, kind="par_spread", value=s + 1) for t, s in zip((1, 3, 5), _SPREADS))
    bumped = calibrate_survival(quotes, discount=.02, recovery=.4).curve
    assert value_cln(bumped, .02, 5, **args).dirty_pv_eur - cln.dirty_pv_eur == pytest.approx(-465.22, abs=.01)
    cds_args = dict(nominal=1_000_000, coupon_bps=100, recovery=.4)
    cds = value_cds(base, .02, 5, **cds_args)
    assert value_cds(bumped, .02, 5, **cds_args).dirty_pv_eur - cds.dirty_pv_eur == pytest.approx(443.08, abs=.01)
    assert 600_000 - cds.dirty_pv_eur == pytest.approx(576_459.98, abs=.01)
    assert 400_000 * exp(-.02 * 30 / 365) - cln.dirty_pv_eur == pytest.approx(-621_517.38, abs=.01)


def test_calibration_rejects_duplicates_inconsistent_quotes_and_maturity_outside_coverage():
    q = CreditQuote(maturity_years=1, kind="par_spread", value=150)
    with pytest.raises(CreditPricingError, match="croissantes"):
        calibrate_survival((q, q), discount=.02, recovery=.4)
    inconsistent = CreditQuote(maturity_years=3, kind="par_spread", value=0)
    with pytest.raises(CreditPricingError, match="intensité positive"):
        calibrate_survival((q, inconsistent), discount=.02, recovery=.4)
    calibrated = calibrate_survival((q.model_copy(update={"value": 0.0}),), discount=-.01, recovery=.4)
    assert calibrated.curve.hazards == (0,)
    assert calibrated.curve.survival_at(1) == 1
    with pytest.raises(CreditPricingError, match="durée"):
        calibrated.curve.survival_at(2)


def test_negative_discount_at_exact_rate_hazard_cancellation():
    curve = SurvivalCurve(maturities=(1,), hazards=(.02,))
    assert default_integral(curve, -.02, 0, 1) == pytest.approx(.02, abs=1e-14)
    assert default_integral(curve, -.02000000000001, 0, 1, accrual_start=0) == pytest.approx(.01, abs=1e-14)


def test_conventional_quoted_spread_normalizes_to_the_standard_coupon():
    quote = CreditQuote(maturity_years=5, kind="quoted_spread", value=150)
    calibration = calibrate_survival((quote,), discount=.02, recovery=.4)
    pillar = calibration.pillars[0]
    assert pillar.source_kind == "quoted_spread" and pillar.normalized_coupon_bps == 100
    assert pillar.normalized_upfront_fraction > 0
    cds = value_cds(calibration.curve, .02, 5, nominal=10_000_000, coupon_bps=100, recovery=.4)
    assert cds.par_spread_bps == pytest.approx(150)
    assert cds.clean_pv_eur == pytest.approx(10_000_000 * pillar.normalized_upfront_fraction, abs=.01)
