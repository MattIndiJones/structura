"""Independent cash-flow witnesses for the Phoenix without memory research adapter."""

from datetime import timedelta
from math import exp

import pytest
from pydantic import ValidationError

from backend.app.core.structured_indices.athena import check_athena_lifecycle, price_athena_issue
from backend.app.core.structured_indices.pricing_catalogue import athena_pricing_catalogue
from backend.app.core.structured_indices.schemas import (
    AthenaFixedCoupon, AthenaIssueRequest, AthenaLifecycleRequest, AthenaMarkRequest, AthenaPricing,
    AthenaSolvedCoupon, AthenaTerms,
)
from backend.tests.test_structured_indices_athena import (
    FINAL, FIRST, SEMIANNUAL, STRIKE, PRICING, _fixing, _market, _mark, _terms, _vintage,
)


def _phoenix_terms(*, coupon_barrier=.70, lag=2, days=(FIRST, FINAL), months=12):
    existing = _terms(days=days, months=months, lag=lag)
    return AthenaTerms.model_validate({**existing.model_dump(), "coupon_barrier": coupon_barrier})


def _lifecycle(vintage, day, *fixings):
    return check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=day, fixings=fixings))


def _principal_discounted(amount, valuation_day, payment_day):
    return amount * exp(-.03 * (payment_day - valuation_day).days / 365.25)


def test_phoenix_capability_matches_wire_guard_and_keeps_legacy_omission():
    capability = next(row for row in athena_pricing_catalogue().payoffs if row.id == "phoenix-sx5e")
    assert capability.version == "phoenix-sx5e-v1"
    assert capability.issue_models == capability.mtm_models == ["constant"]
    terms = _phoenix_terms()
    assert _terms().model_dump().get("coupon_barrier", "omitted") == "omitted"
    assert terms.model_dump()["coupon_barrier"] == .70
    for incompatible in ({"call_barriers": (1., .95)}, {"coupon_barrier": 1.01}):
        with pytest.raises(ValidationError):
            AthenaTerms.model_validate({**terms.model_dump(), **incompatible})
    with pytest.raises(ValidationError, match="qualifié.*Phoenix"):
        AthenaMarkRequest(vintage=_vintage(terms), market=_market(STRIKE),
                          pricing=AthenaPricing(model="heston", n_paths=32), fixings=())


def test_phoenix_coupon_solves_on_two_disjoint_periodic_cashflows():
    terms = _phoenix_terms()
    request = AthenaIssueRequest(
        note_id="phoenix", terms=terms, market=_market(STRIKE, spot=4500.), pricing=PRICING,
        coupon=AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), initial_fixing=5000., initial_fixing_reference="strike",
    )
    payments = [event.payment_date for event in terms.observations]
    # All paths stay at 90% of strike: both coupons pay, the final nominal
    # pays under terminal protection, and no autocall happens.
    expected = sum(_principal_discounted(amount, STRIKE, day) for amount, day in zip((6., 106.), payments))
    issue = price_athena_issue(request)
    assert issue["price"] == pytest.approx(expected, abs=.0002)
    solved = price_athena_issue(request.model_copy(update={"coupon": AthenaSolvedCoupon(
        mode="solve_to_target", target_price=expected, min_coupon=0., max_coupon=.20,
    )}))
    assert solved["status"] == "issued"
    assert solved["coupon_rate"] == pytest.approx(.06, abs=.000005)
    assert solved["price"] == pytest.approx(expected, abs=.0002)


def test_phoenix_coupon_at_the_barrier_detaches_without_terminating_or_double_counting():
    terms = _phoenix_terms()
    note = _vintage(terms)
    first = _fixing(FIRST, 3500.)
    coupon_day, final_day = (event.payment_date for event in terms.observations)
    life = _lifecycle(note, FIRST, first)
    assert life["status"] == "active" and life["redemption"] is None
    assert [(row["kind"], row["condition_met"]) for row in life["barriers"]] == [("call", False), ("coupon", True)]
    [coupon] = life["coupon_claims"]
    assert coupon == {"event_id": coupon["event_id"], "observed_date": FIRST.isoformat(),
                      "payment_date": coupon_day.isoformat(), "amount": 6., "kind": "coupon"}
    on_obs = _mark(note, FIRST, (first,), spot=4500.)
    next_day = _mark(note, FIRST + timedelta(days=1), (first,), spot=4500.)
    on_payment = _mark(note, coupon_day, (first,), spot=4500.)
    assert not on_obs["terminated"] and not on_payment["terminated"]
    assert on_obs["residual_pv"] == pytest.approx(_principal_discounted(106., FIRST, final_day), abs=.0002)
    assert on_obs["claims"] == [{**coupon, "pv": _principal_discounted(6., FIRST, coupon_day)}]
    assert next_day["claims"][0]["event_id"] == coupon["event_id"]
    assert next_day["claims"][0]["pv"] > on_obs["claims"][0]["pv"]
    assert on_payment["claims"] == []
    assert _lifecycle(note, coupon_day, first)["coupon_claims"] == [coupon]
    assert on_obs["next_call"]["probability"] == 0.0
    assert on_obs["next_call"]["threshold"] == 1.0
    assert on_obs["next_call"]["redemption_amount"] == 106.0


@pytest.mark.parametrize(
    "final_spot, status, principal, coupon, capital_check",
    [(5000., "called", 100., True, None), (3500., "matured", 100., True, True),
     (2750., "matured", 55., True, False), (0., "matured", 0., False, False)],
)
def test_phoenix_maturity_and_no_memory_with_coincident_flows(final_spot, status, principal, coupon, capital_check):
    # Coupon barrier below protection: final positive coupon and capital loss can coexist.
    note = _vintage(_phoenix_terms(coupon_barrier=.50, lag=0))
    first, final = _fixing(FIRST, 2400.), _fixing(FINAL, final_spot)
    life = _lifecycle(note, FINAL, first, final)
    assert life["status"] == status
    assert life["redemption"]["amount"] == pytest.approx(principal)
    assert life["redemption"]["kind"] == "redemption"
    assert [claim["amount"] for claim in life["coupon_claims"]] == ([6.] if coupon else [])
    mark = _mark(note, FINAL, (first, final))
    assert mark["terminated"] and mark["residual_pv"] == 0 and "next_call" not in mark
    assert mark["claims"] == [{**claim, "pv": claim["amount"]}
                              for claim in [*life["coupon_claims"], life["redemption"]]]
    assert len({row["event_id"] for row in mark["claims"]}) == len(mark["claims"])
    assert {row["kind"]: row["condition_met"] for row in mark["barriers"]}.get("capital") is capital_check
    assert _mark(note, FINAL + timedelta(days=1), (first, final))["claims"] == []


def test_phoenix_semiannual_early_call_pays_only_current_period():
    note = _vintage(_phoenix_terms(days=(SEMIANNUAL, FIRST, FINAL), months=6))
    missed = _fixing(SEMIANNUAL, 3400.)
    pre_call = _mark(note, FIRST - timedelta(days=1), (missed,), spot=5100.)
    assert pre_call["next_call"]["probability"] == 1.0
    assert pre_call["next_call"]["redemption_amount"] == 103.0
    face = _fixing(FIRST, 5000.)
    mark = _mark(note, FIRST, (missed, face))
    assert mark["status"] == "called"
    assert [(claim["kind"], claim["amount"]) for claim in mark["claims"]] == [("coupon", 3.), ("redemption", 100.)]


def test_phoenix_zero_coupon_has_a_barrier_check_without_a_receivable():
    note = _vintage(_phoenix_terms()).model_copy(update={"annual_coupon": 0.})
    first = _fixing(FIRST, 4500.)
    mark = _mark(note, FIRST, (first,))
    assert mark["claims"] == []
    assert next(row for row in mark["barriers"] if row["kind"] == "coupon")["condition_met"]
