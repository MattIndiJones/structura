"""Deterministic economic witnesses for the isolated Athena research pricer."""
from datetime import date, timedelta
from math import erf, exp, log, sqrt

import pytest
from pydantic import ValidationError

from backend.app.core.calendars import add_business_days
from backend.app.core.structured_indices import athena
from backend.app.core.structured_indices.athena import (
    check_athena_lifecycle,
    price_athena_issue,
    price_athena_mark,
)
from backend.app.core.structured_indices.schemas import (
    AthenaFixing,
    AthenaFixedCoupon,
    AthenaIssueRequest,
    AthenaLifecycleRequest,
    AthenaMarkRequest,
    AthenaMarket,
    AthenaObservation,
    AthenaPricing,
    AthenaSolvedCoupon,
    AthenaTerms,
    AthenaVintage,
)


STRIKE = date(2025, 11, 3)
FIRST = date(2026, 11, 3)
FINAL = date(2027, 11, 3)
SEMIANNUAL = date(2026, 5, 4)
PRICING = AthenaPricing(n_paths=32, seed=42, steps_per_year=52)


def _terms(days=(FIRST, FINAL), months=12, lag=2):
    return AthenaTerms(
        strike_date=STRIKE, calendar_reference="test-target",
        observation_months=months, settlement_lag=lag,
        observations=tuple(AthenaObservation(
            observation_date=day, payment_date=add_business_days(day, lag, "TARGET")) for day in days),
    )


def _market(day, spot=5200, volatility=0.0):
    return AthenaMarket(
        as_of=day, reference=f"market-{day}", spot=spot, volatility=volatility,
        rate=.02, dividend_yield=.02, funding_spread=.01,
    )


def _vintage(terms=None):
    return AthenaVintage(
        note_id="athena-a", terms=terms or _terms(), initial_fixing=5000,
        initial_fixing_reference="strike-fixing", annual_coupon=.06,
    )


def _fixing(day, spot):
    return AthenaFixing(day=day, spot=spot, reference=f"fixing-{day}")


def _mark(vintage, day, fixings=(), spot=5200):
    return price_athena_mark(AthenaMarkRequest(
        vintage=vintage, market=_market(day, spot=spot), pricing=PRICING, fixings=fixings,
    ))


def _issue(coupon, *, spot=5200, volatility=0.0, pricing=PRICING):
    vintage = _vintage()
    return AthenaIssueRequest(
        note_id=vintage.note_id, terms=vintage.terms, market=_market(STRIKE, spot, volatility),
        pricing=pricing, coupon=coupon, initial_fixing=vintage.initial_fixing,
        initial_fixing_reference=vintage.initial_fixing_reference,
    )


MONTHLY_DATES = (date(2025, 12, 3), date(2026, 1, 5), date(2026, 2, 3))


def test_monthly_three_month_note_prorates_coupons_and_preserves_dated_terms():
    legacy = _terms(MONTHLY_DATES, months=1)
    assert "maturity_months" not in legacy.model_dump(mode="json")
    terms = AthenaTerms.model_validate({**legacy.model_dump(), "maturity_months": 3})
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06)).model_copy(update={"terms": terms})
    issue = price_athena_issue(request)
    first_payment = terms.observations[0].payment_date
    assert issue["vintage"]["terms"]["maturity_months"] == 3
    assert issue["price"] == pytest.approx(100.5 * exp(-.03 * (first_payment - STRIKE).days / 365.25), abs=.0002)

    vintage = AthenaVintage.model_validate(issue["vintage"])
    first, second, final = MONTHLY_DATES
    fixings = (_fixing(first, 4500.), _fixing(second, 4500.), _fixing(final, 5000.))
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=final, fixings=fixings))
    assert life["status"] == "called"
    assert life["redemption"]["amount"] == pytest.approx(101.5)
    assert _mark(vintage, final, fixings)["claims"][0]["amount"] == pytest.approx(101.5)


@pytest.mark.parametrize(("days", "interval", "months"), [
    (MONTHLY_DATES, 6, 3),
    (MONTHLY_DATES[:2], 1, 3),
    ((MONTHLY_DATES[0], MONTHLY_DATES[-1], date(2026, 3, 3)), 1, 3),
])
def test_explicit_maturity_rejects_incompatible_observation_schedule(days, interval, months):
    with pytest.raises(ValidationError, match="maturité"):
        AthenaTerms.model_validate({**_terms(days, months=interval).model_dump(), "maturity_months": months})


def test_ten_year_monthly_step_down_keeps_all_barriers_and_fixings():
    strike_month = STRIKE.year * 12 + STRIKE.month - 1
    days = tuple(date(month // 12, month % 12 + 1, STRIKE.day)
                 for month in range(strike_month + 1, strike_month + 121))
    terms = AthenaTerms.model_validate({
        **_terms(days, months=1).model_dump(), "maturity_months": 120, "call_barriers": (1.,) * 120,
    })
    vintage = _vintage(terms)
    fixings = tuple(_fixing(day, 4500.) for day in days)
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=days[-1], fixings=fixings))
    assert life["status"] == "matured"
    assert len([row for row in life["barriers"] if row["kind"] == "call"]) == 120
    assert _mark(vintage, days[-1], fixings)["claims"][0]["amount"] == pytest.approx(100.)


STEP_DOWN_DATES = (SEMIANNUAL, FIRST, date(2027, 5, 3), FINAL)


def _step_down_terms(levels=(1., .95, .9, .85)):
    terms = _terms(STEP_DOWN_DATES, months=6)
    return AthenaTerms.model_validate({**terms.model_dump(), "call_barriers": levels})


@pytest.mark.parametrize("levels", [
    (), (1., .95, .9), (.99, .95, .9, .85), (1., .95, .96, .85), (1., .95, .9, .59), (1., .95, .9, 0.),
])
def test_step_down_rejects_invalid_barrier_schedules(levels):
    with pytest.raises(ValidationError):
        _step_down_terms(levels)


def test_native_payoff_capabilities_match_issue_and_mtm_model_guards():
    from backend.app.core.structured_indices.pricing_catalogue import athena_pricing_catalogue

    capabilities = {payoff.id: payoff for payoff in athena_pricing_catalogue().payoffs}
    classical = capabilities["athena-sx5e"]
    assert classical.issue_models == classical.mtm_models == ["constant", "heston", "sabr", "localvol"]
    variant = capabilities["athena-step-down-sx5e"]
    assert variant.version == "athena-step-down-sx5e-v1"
    assert variant.issue_models == variant.mtm_models == ["constant"]
    issue = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06))
    terms = _step_down_terms()
    heston = AthenaPricing(model="heston", n_paths=32)
    with pytest.raises(ValidationError, match="qualifi"):
        AthenaIssueRequest.model_validate({**issue.model_dump(), "terms": terms, "pricing": heston})
    with pytest.raises(ValidationError, match="qualifi"):
        AthenaMarkRequest(vintage=_vintage(terms), market=issue.market, pricing=heston, fixings=())


def test_flat_barriers_reproduce_standard_payoff_along_the_same_paths():
    classical = _terms(STEP_DOWN_DATES, months=6)
    identical = _step_down_terms((1., 1., 1., 1.))
    assert "call_barriers" not in classical.model_dump(mode="json")
    assert identical.model_dump(mode="json")["call_barriers"] == [1., 1., 1., 1.]
    issue = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), volatility=.23)
    classical_issue = price_athena_issue(issue.model_copy(update={"terms": classical}))
    step_down_issue = price_athena_issue(issue.model_copy(update={"terms": identical}))
    for key in ("price", "coupon_rate", "confidence_interval"):
        assert step_down_issue[key] == classical_issue[key]
    assert step_down_issue["terms_reference"] != classical_issue["terms_reference"]

    past = (_fixing(SEMIANNUAL, 4900),)
    market = _market(FIRST - timedelta(days=8), spot=4960., volatility=.23)
    classical_mark = price_athena_mark(AthenaMarkRequest(
        vintage=_vintage(classical), market=market, pricing=issue.pricing, fixings=past,
    ))
    step_down_mark = price_athena_mark(AthenaMarkRequest(
        vintage=_vintage(identical), market=market, pricing=issue.pricing, fixings=past,
    ))
    for key in ("residual_pv", "confidence_interval", "status"):
        assert step_down_mark[key] == classical_mark[key]
    analytics = dict(step_down_mark["next_call"])
    assert analytics.pop("threshold") == 1.
    assert analytics == classical_mark["next_call"]


def test_step_down_issued_coupon_and_in_life_calls_use_the_correct_observation_rank():
    terms = _step_down_terms()
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), spot=4800.)
    request = request.model_copy(update={"terms": terms})
    payment = terms.observations[1].payment_date
    quoted = price_athena_issue(request)
    # A flat path at 96% misses 100% and is recalled at the second threshold.
    expected = 106 * exp(-.03 * (payment - STRIKE).days / 365.25)
    assert quoted["price"] == pytest.approx(expected, abs=.0001)
    solved = price_athena_issue(request.model_copy(update={"coupon": AthenaSolvedCoupon(
        mode="solve_to_target", min_coupon=.01, max_coupon=.2, target_price=expected,
    )}))
    assert solved["coupon_rate"] == pytest.approx(.06, abs=2e-6)
    assert solved["price"] == pytest.approx(expected, abs=.01)
    vintage = AthenaVintage.model_validate(solved["vintage"])
    past = (_fixing(SEMIANNUAL, 4800),)
    live = _mark(vintage, SEMIANNUAL, past, spot=4800.)
    assert live["barriers"][0]["threshold"] == 1.
    assert live["next_call"]["probability"] == 1.
    assert live["next_call"]["threshold"] == .95
    assert live["next_call"]["observation_date"] == FIRST.isoformat()
    assert live["next_call"]["redemption_amount"] == 106.
    assert live["residual_pv"] == pytest.approx(106 * exp(-.03 * (payment - SEMIANNUAL).days / 365.25), abs=.0001)
    called = check_athena_lifecycle(AthenaLifecycleRequest(
        vintage=vintage, as_of=FIRST, fixings=(*past, _fixing(FIRST, 4750)),
    ))
    assert [barrier["threshold"] for barrier in called["barriers"]] == [1., .95]
    assert called["status"] == "called"
    assert called["redemption"]["amount"] == 106.
    assert called["redemption"]["payment_date"] == payment.isoformat()
    called_mark = _mark(vintage, FIRST, (*past, _fixing(FIRST, 4750)))
    assert called_mark["claims"][0]["event_id"] == called["redemption"]["event_id"]
    assert "next_call" not in called_mark


@pytest.mark.parametrize("final_spot, expected_status, expected_amount", [
    (4250, "called", 112.),
    (4200, "matured", 100.),
    (3000, "matured", 100.),
    (2999, "matured", 59.98),
])
def test_step_down_final_threshold_and_protection_are_independent(final_spot, expected_status, expected_amount):
    vintage = _vintage(_step_down_terms())
    past = tuple(_fixing(day, 4200) for day in STEP_DOWN_DATES[:-1])
    live = _mark(vintage, STEP_DOWN_DATES[-2], past, spot=4300)
    assert live["next_call"]["is_final_observation"] is True
    assert live["next_call"]["threshold"] == .85
    assert live["next_call"]["probability"] == 1.
    assert live["next_call"]["redemption_amount"] == pytest.approx(112.)
    mark = _mark(vintage, FINAL, (*past, _fixing(FINAL, final_spot)))
    assert mark["status"] == expected_status
    assert mark["barriers"][0]["threshold"] == .85
    assert mark["claims"][0]["amount"] == pytest.approx(expected_amount)


def test_issue_and_first_mtm_use_the_same_frozen_strike_and_payment():
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06))
    issue = price_athena_issue(request)
    vintage = AthenaVintage.model_validate(issue["vintage"])
    mark = _mark(vintage, STRIKE)
    payment = vintage.terms.observations[0].payment_date
    expected = 106 * exp(-.03 * (payment - STRIKE).days / 365.25)
    assert issue["price"] == pytest.approx(expected, abs=.0001)
    assert issue["price"] == mark["residual_pv"]
    assert issue["terms_reference"] == mark["terms_reference"]
    assert issue["market_snapshot_id"] == mark["market_snapshot_id"]
    assert issue == price_athena_issue(request)


def test_next_call_counts_principal_at_zero_coupon():
    terms = _terms()
    vintage = _vintage(terms).model_copy(update={"annual_coupon": 0.})
    day = FIRST - timedelta(days=1)
    mark = _mark(vintage, day)
    payment = terms.observations[0].payment_date
    assert mark["next_call"] == {
        "observation_date": FIRST.isoformat(),
        "payment_date": payment.isoformat(),
        "is_final_observation": False,
        "probability": 1.,
        "redemption_amount": 100.,
        "redemption_pv": pytest.approx(100 * exp(-.03 * (payment - day).days / 365.25)),
    }
    called = _mark(vintage, FIRST, (_fixing(FIRST, 5000),))
    assert called["terminated"] is True
    assert "next_call" not in called


def test_next_call_advances_at_a_missed_fixing_and_excludes_final_principal_from_calls():
    terms = _terms((SEMIANNUAL, FIRST), months=6)
    vintage = _vintage(terms)
    mark = _mark(vintage, SEMIANNUAL, (_fixing(SEMIANNUAL, 4900),), spot=4900)
    assert mark["terminated"] is False
    assert mark["next_call"]["observation_date"] == FIRST.isoformat()
    assert mark["next_call"]["is_final_observation"] is True
    assert mark["next_call"]["probability"] == 0.
    assert mark["next_call"]["redemption_amount"] == 106.
    payment = terms.observations[-1].payment_date
    assert mark["residual_pv"] == pytest.approx(100 * exp(-.03 * (payment - SEMIANNUAL).days / 365.25), abs=.0001)


@pytest.mark.parametrize("antithetic", [False, True])
def test_next_call_has_the_gbm_conditional_probability_from_one_pricing(monkeypatch, antithetic):
    recorded = []
    run_valuation = athena.run_valuation

    def record_valuation(script, context, **options):
        result = run_valuation(script, context, **options)
        recorded.append(result)
        return result

    monkeypatch.setattr(athena, "run_valuation", record_valuation)
    vintage = _vintage()
    day = FIRST - timedelta(days=8)
    pricing = PRICING.model_copy(update={"n_paths": 1024, "antithetic": antithetic})
    market = _market(day, spot=4950, volatility=.2)
    mark = price_athena_mark(AthenaMarkRequest(vintage=vintage, market=market, pricing=pricing, fixings=()))
    t = (FIRST - day).days / 365.25
    d2 = (log(market.spot / vintage.initial_fixing) - .5 * market.volatility**2 * t) / (market.volatility * sqrt(t))
    expected = (1 + erf(d2 / sqrt(2))) / 2
    assert mark["next_call"]["probability"] == pytest.approx(expected, abs=.045)
    [pricing_result] = recorded
    assert mark["residual_pv"] == 100 * pricing_result["price"]


def test_affine_solver_reprices_the_published_coupon_and_proves_outside_bounds():
    coupon = AthenaFixedCoupon(mode="fixed", fixed_coupon=.072345)
    request = _issue(coupon, volatility=.25)
    target = price_athena_issue(request)["price"]
    solved = price_athena_issue(request.model_copy(update={
        "coupon": AthenaSolvedCoupon(mode="solve_to_target", min_coupon=.01, max_coupon=.2, target_price=target),
    }))
    assert solved["status"] == "issued"
    assert solved["coupon_rate"] == pytest.approx(coupon.fixed_coupon, abs=2e-6)
    assert solved["price"] == pytest.approx(target, abs=.01)
    skipped = price_athena_issue(request.model_copy(update={
        "coupon": AthenaSolvedCoupon(mode="solve_to_target", min_coupon=.01, max_coupon=.02, target_price=200),
    }))
    assert skipped["status"] == "no_coupon_in_bounds"
    assert skipped["solver"]["max_coupon_price"] < 200
    assert skipped["price"] is None
    assert skipped["vintage"] is None
    assert skipped["receipt_id"]


def test_disabling_antithetic_pairs_changes_both_issue_and_live_mtm():
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), volatility=.27)
    paired = price_athena_issue(request)
    unpaired_pricing = request.pricing.model_copy(update={"antithetic": False})
    unpaired = price_athena_issue(request.model_copy(update={"pricing": unpaired_pricing}))
    assert unpaired["price"] != paired["price"]
    assert unpaired["pricing"]["antithetic"] is False
    assert unpaired["pricing"]["model"] == "constant"

    vintage = AthenaVintage.model_validate(unpaired["vintage"])
    mark = price_athena_mark(AthenaMarkRequest(vintage=vintage, market=request.market, pricing=unpaired_pricing, fixings=()))
    assert mark["residual_pv"] == unpaired["price"]
    assert mark["pricing"] == unpaired["pricing"]


@pytest.mark.parametrize(("model", "change"), [
    ("heston", {"v0": .11}), ("sabr", {"alpha": .39}), ("localvol", {"skew": -.20}),
])
def test_native_model_inputs_reach_coupon_solver_and_residual_mtm(model, change):
    default = AthenaPricing.model_validate({"model": model, "n_paths": 512})
    changed = AthenaPricing.model_validate({**default.model_dump(), **change})
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.09), pricing=changed, volatility=.23)
    fixed = price_athena_issue(request)
    solved = price_athena_issue(request.model_copy(update={"coupon": AthenaSolvedCoupon(
        mode="solve_to_target", min_coupon=.01, max_coupon=.2, target_price=fixed["price"],
    )}))
    assert solved["coupon_rate"] == pytest.approx(.09, abs=2e-6)
    assert solved["pricing"] == changed.model_dump()
    assert fixed["price"] != price_athena_issue(request.model_copy(update={"pricing": default}))["price"]
    vintage = AthenaVintage.model_validate(solved["vintage"])
    mark = AthenaMarkRequest(vintage=vintage, market=request.market, pricing=changed, fixings=())
    assert price_athena_mark(mark)["residual_pv"] == solved["price"]
    live = mark.model_copy(update={"market": _market(STRIKE + timedelta(days=62), spot=4900, volatility=.23)})
    assert price_athena_mark(live)["residual_pv"] != price_athena_mark(live.model_copy(update={"pricing": default}))[
        "residual_pv"]


def test_native_curves_apply_at_issue_live_mtm_and_detached_redemption():
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), spot=4950.)
    market = AthenaMarket.model_validate({
        **request.market.model_dump(), "dividend_curve": [[1, .02], [2, 0.]],
        "yield_curve": [[.002, .02], [2.1, .02]], "funding_curve": [[.002, .04], [2.1, .04]],
    })
    curve_request = request.model_copy(update={"market": market})
    issue = price_athena_issue(curve_request)
    final_payment = request.terms.observations[-1].payment_date
    assert issue["price"] == pytest.approx(112 * exp(-.06 * (final_payment - STRIKE).days / 365.25), abs=.0001)
    assert issue["price"] != price_athena_issue(request)["price"]
    vintage = AthenaVintage.model_validate(issue["vintage"])
    mark = AthenaMarkRequest(vintage=vintage, market=market, pricing=curve_request.pricing, fixings=())
    assert price_athena_mark(mark)["residual_pv"] == issue["price"]

    claim_market = AthenaMarket.model_validate({
        **market.model_dump(), "as_of": FIRST, "yield_curve": [[.002, .02], [.01, .06]],
        "funding_curve": [[.002, .01], [.01, .05]],
    })
    claim_mark = AthenaMarkRequest(vintage=vintage, market=claim_market, pricing=PRICING,
                                 fixings=(_fixing(FIRST, 5000),))
    [claim] = price_athena_mark(claim_mark)["claims"]
    t = (request.terms.observations[0].payment_date - FIRST).days / 365.25
    expected_rate = .03 + .08 * (t - .002) / (.01 - .002)
    assert claim["pv"] == pytest.approx(106 * exp(-expected_rate * t))
    assert claim["pv"] != pytest.approx(106 * exp(-(.02 + .01) * t), abs=1e-6)


def test_legacy_flat_contract_and_native_curve_constraints():
    market = _market(STRIKE)
    assert set(market.model_dump()) == {"as_of", "reference", "spot", "rate", "volatility", "dividend_yield", "funding_spread"}
    assert set(PRICING.model_dump()) == {"model", "n_paths", "seed", "steps_per_year", "antithetic"}
    high_dividend = AthenaMarket.model_validate({
        **market.model_dump(), "dividend_yield": 2., "dividend_curve": [[1, 2.], [2, 1.]],
    })
    assert high_dividend.dividend_yield == 2.
    assert AthenaMarket.model_validate({**market.model_dump(), "dividend_yield": -.25}).dividend_yield == -.25
    with pytest.raises(ValidationError, match="less than or equal to 2"):
        AthenaMarket.model_validate({**market.model_dump(), "dividend_yield": 2.01})
    with pytest.raises(ValidationError, match="premier bucket"):
        AthenaMarket.model_validate({**market.model_dump(), "dividend_curve": [[1, .03]]})
    with pytest.raises(ValidationError, match="strictement croissantes"):
        AthenaMarket.model_validate({**market.model_dump(), "yield_curve": [[1, .03], [1, .04]]})
    with pytest.raises(ValidationError, match="non utilisés"):
        AthenaPricing.model_validate({"model": "constant", "v0": .05})


def test_native_ssvi_surface_reaches_issue_and_current_spot_anchored_mtm():
    pricing = AthenaPricing(model="localvol", n_paths=512)
    request = _issue(AthenaFixedCoupon(mode="fixed", fixed_coupon=.09), volatility=.22, pricing=pricing)
    surface = {"profile": "index", "mode": "manual", "rho": -.6, "eta": .7, "max_expiry": 5.,
               "atm_nodes": [[.5, .25], [1., .24], [2., .23], [5., .22]]}
    market = AthenaMarket.model_validate({**request.market.model_dump(), "vol_surface": surface})
    curved = price_athena_issue(request.model_copy(update={"market": market}))
    assert curved["price"] != price_athena_issue(request)["price"]
    vintage = AthenaVintage.model_validate(curved["vintage"])
    live_market = AthenaMarket.model_validate({
        **market.model_dump(), "as_of": STRIKE + timedelta(days=75), "spot": 4720.,
    })
    mark = AthenaMarkRequest(vintage=vintage, market=live_market, pricing=pricing, fixings=())
    flat_mark = mark.model_copy(update={"market": live_market.model_copy(update={"vol_surface": None})})
    assert price_athena_mark(mark)["residual_pv"] != price_athena_mark(flat_mark)["residual_pv"]
    with pytest.raises(ValidationError, match="utilisable avec le modèle Local Vol"):
        AthenaMarkRequest(vintage=vintage, market=live_market, pricing=PRICING, fixings=())


def test_annual_athena_reconciles_to_independent_truncated_lognormal_value():
    terms = _terms((FIRST,))
    discount_t = (terms.observations[0].payment_date - STRIKE).days / 365.25
    observation_t = (FIRST - STRIKE).days / 365.25
    r, q, funding, volatility, coupon = .025, .01, .013, .23, .07
    stdev = volatility * sqrt(observation_t)

    def cdf(z):
        return (1 + erf(z / sqrt(2))) / 2

    prices = []
    for spot in (4700, 5300):
        mean = log(spot / 5000) + (r - q - volatility**2 / 2) * observation_t
        below_protection = (log(terms.protection_barrier) - mean) / stdev
        below_call = (log(terms.call_barrier) - mean) / stdev
        loss_leg = exp(mean + stdev**2 / 2) * cdf(below_protection - stdev)
        undiscounted = loss_leg + (1 - cdf(below_protection)) + coupon * (1 - cdf(below_call))
        expected = 100 * exp(-(r + funding) * discount_t) * undiscounted

        quote = price_athena_issue(AthenaIssueRequest(
            note_id="athena-analytical", terms=terms,
            market=AthenaMarket(as_of=STRIKE, reference="analytical-market", spot=spot, rate=r,
                                volatility=volatility, dividend_yield=q, funding_spread=funding),
            pricing=AthenaPricing(n_paths=8192, seed=42, steps_per_year=52),
            coupon=AthenaFixedCoupon(mode="fixed", fixed_coupon=coupon),
            initial_fixing=5000, initial_fixing_reference="analytical-strike",
        ))
        lower, upper = quote["confidence_interval"]
        assert quote["price"] == pytest.approx(expected, abs=.75 * (upper - lower))
        prices.append(quote["price"])
    assert prices[1] > prices[0]


def test_call_uses_exact_contractual_fixing_and_only_accrued_semiannual_coupon():
    vintage = _vintage(_terms((SEMIANNUAL, FIRST), months=6))
    call_fixing = _fixing(SEMIANNUAL, 5000)
    first_mark = _mark(vintage, SEMIANNUAL, (call_fixing,), spot=4800)
    assert first_mark["status"] == "called"
    assert first_mark["terminated"] is True
    assert first_mark["residual_pv"] == 0
    assert first_mark["confidence_interval"] is None
    claim = first_mark["claims"][0]
    assert claim["amount"] == 103
    assert claim["pv"] == pytest.approx(103 * exp(-.03 * 2 / 365.25))
    assert first_mark["barriers"][0]["condition_met"] is True
    assert first_mark["barriers"][0]["ratio"] == 1
    assert first_mark["fixing_references"][str(SEMIANNUAL)] == call_fixing.reference

    last_mark = _mark(vintage, date(2026, 5, 5), (call_fixing,))
    assert last_mark["claims"][0]["event_id"] == claim["event_id"]
    assert last_mark["claims"][0]["pv"] == pytest.approx(103 * exp(-.03 / 365.25))
    assert last_mark["barriers"] == []
    assert _mark(vintage, date(2026, 5, 6), (call_fixing,))["claims"] == []
    lifecycle = check_athena_lifecycle(AthenaLifecycleRequest(
        vintage=vintage, as_of=FINAL, fixings=(call_fixing,)))
    assert lifecycle["redemption"] == {key: value for key, value in claim.items() if key != "pv"}
    assert len(lifecycle["barriers"]) == 1


@pytest.mark.parametrize(
    ("spot", "status", "amount", "conditions"),
    [(5000, "called", 112, [True]), (3000, "matured", 100, [False, True]),
     (2995, "matured", 59.9, [False, False]), (0, "matured", 0, [False, False])],
)
def test_final_observation_uses_call_priority_and_inclusive_capital_protection(spot, status, amount, conditions):
    vintage = _vintage(_terms(lag=0))
    result = _mark(vintage, FINAL, (_fixing(FIRST, 4500), _fixing(FINAL, spot)))
    assert result["status"] == status
    assert [check["condition_met"] for check in result["barriers"]] == conditions
    claim, = result["claims"]
    assert claim["amount"] == pytest.approx(amount)
    assert claim["pv"] == claim["amount"]
    assert claim["observed_date"] == claim["payment_date"] == str(FINAL)


def test_live_valuation_rejects_a_missing_fixing_before_using_today_market_spot():
    vintage = _vintage()
    with pytest.raises(ValueError, match="Fixing Athena manquant"):
        _mark(vintage, FIRST)
    prior = FIRST - timedelta(days=1)
    first_payment = vintage.terms.observations[0].payment_date
    assert _mark(vintage, prior)["residual_pv"] == pytest.approx(
        106 * exp(-.03 * (first_payment - prior).days / 365.25), abs=.0001,
    )
    # Below the barrier on the contractual fixing, even though the simulation
    # spot is above it. Year-two redemption must still carry both coupons.
    valuation = _mark(vintage, FIRST, (_fixing(FIRST, 4900),))
    payment = vintage.terms.observations[-1].payment_date
    expected = 112 * exp(-.03 * (payment - FIRST).days / 365.25)
    assert valuation["status"] == "active"
    assert valuation["barriers"][0]["condition_met"] is False
    assert valuation["residual_pv"] == pytest.approx(expected, abs=.0001)
    assert valuation["claims"] == []
    next_day = FIRST + timedelta(days=1)
    next_mark = _mark(vintage, next_day, (_fixing(FIRST, 4900),))
    assert next_mark["residual_pv"] == pytest.approx(
        112 * exp(-.03 * (payment - next_day).days / 365.25), abs=.0001,
    )
    assert next_mark["barriers"] == []
