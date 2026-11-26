"""Reverse Convertible cash flows, annual coupon and calendar witnesses."""

from datetime import timedelta
from math import exp

import pytest
from pydantic import ValidationError

from backend.app.core.structured_indices.athena import check_athena_lifecycle, price_athena_issue
from backend.app.core.structured_indices.schemas import (
    AthenaFixedCoupon, AthenaIssueRequest, AthenaLifecycleRequest, AthenaMarkRequest, AthenaPricing,
    AthenaSolvedCoupon, AthenaTerms,
)
from backend.tests.test_structured_indices_athena import (
    FINAL, FIRST, PRICING, SEMIANNUAL, STRIKE, _fixing, _mark, _market, _terms, _vintage,
)


def _reverse_terms(*, lag=2):
    return AthenaTerms.model_validate({
        **_terms(days=(FINAL,), lag=lag).model_dump(), "reverse_convertible": True, "maturity_years": 2,
    })


@pytest.mark.parametrize("invalid", [
    {"reverse_convertible": False},
    {"reverse_convertible": None},
    {"maturity_years": None},
    {"maturity_years": 0},
    {"maturity_years": 11},
    {"maturity_years": 2.0},
    {"maturity_months": 24},
    {"observations": _terms().observations},
    {"observation_months": 6},
    {"call_barrier": .90},
    {"call_barriers": (1.,)},
    {"protection_barrier": 1.01},
    {"coupon_barrier": .70},
    {"coupon_memory": True},
])
def test_reverse_convertible_terms_reject_noncontractual_settings(invalid):
    assert not {"reverse_convertible", "maturity_years", "maturity_months"} & _terms().model_dump().keys()
    with pytest.raises(ValidationError):
        AthenaTerms.model_validate({**_reverse_terms().model_dump(), **invalid})


def test_reverse_convertible_requires_qualified_pricing_model():
    with pytest.raises(ValidationError, match="qualifié.*Reverse Convertible"):
        AthenaMarkRequest(vintage=_vintage(_reverse_terms()), market=_market(STRIKE),
                          pricing=AthenaPricing(model="heston", n_paths=32), fixings=())


def test_reverse_convertible_issue_and_solve_with_unconditional_two_year_coupon():
    terms = _reverse_terms()
    request = AthenaIssueRequest(
        note_id="reverse-convertible", market=_market(STRIKE, spot=2750.), terms=terms, pricing=PRICING,
        coupon=AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), initial_fixing=5000.,
        initial_fixing_reference="initial-sx5e",
    )
    payment = terms.observations[0].payment_date
    expected = (55. + 12.) * exp(-.03 * (payment - STRIKE).days / 365.25)
    assert price_athena_issue(request)["price"] == pytest.approx(expected, abs=.0002)
    solved = price_athena_issue(request.model_copy(update={
        "coupon": AthenaSolvedCoupon(mode="solve_to_target", target_price=expected, min_coupon=0., max_coupon=.20),
    }))
    assert solved["status"] == "issued"
    assert solved["coupon_rate"] == pytest.approx(.06, abs=.000001)
    assert solved["price"] == pytest.approx(expected, abs=.0002)


def test_six_month_reverse_convertible_prorates_issue_and_terminal_coupon():
    terms = AthenaTerms.model_validate({
        **_terms(days=(SEMIANNUAL,), lag=0).model_dump(),
        "reverse_convertible": True, "maturity_months": 6,
    })
    vintage = _vintage(terms)
    request = AthenaIssueRequest(
        note_id=vintage.note_id, market=_market(STRIKE), terms=terms, pricing=PRICING,
        coupon=AthenaFixedCoupon(mode="fixed", fixed_coupon=.06), initial_fixing=vintage.initial_fixing,
        initial_fixing_reference=vintage.initial_fixing_reference,
    )
    assert price_athena_issue(request)["price"] == pytest.approx(
        103. * exp(-.03 * (SEMIANNUAL - STRIKE).days / 365.25), abs=.0002,
    )
    fixings = (_fixing(SEMIANNUAL, 5200.),)
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=SEMIANNUAL, fixings=fixings))
    assert [claim["amount"] for claim in life["coupon_claims"]] == [3.]
    assert sum(claim["pv"] for claim in _mark(vintage, SEMIANNUAL, fixings)["claims"]) == pytest.approx(103.)


def test_reverse_convertible_does_not_test_barrier_or_pay_coupon_before_maturity():
    vintage = _vintage(_reverse_terms())
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=FIRST, fixings=()))
    assert life["status"] == "active" and not life["terminated"]
    assert life["barriers"] == life["coupon_claims"] == []
    assert life["redemption"] is None
    with pytest.raises(ValidationError, match="constats échus"):
        AthenaLifecycleRequest(vintage=vintage, as_of=FIRST, fixings=(_fixing(FIRST, 2200.),))
    with pytest.raises(ValueError, match="Fixing.*manquant"):
        check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=FINAL, fixings=()))
    mark = _mark(vintage, FIRST, spot=5100.)
    payment = vintage.terms.observations[0].payment_date
    expected = 112. * exp(-.03 * (payment - FIRST).days / 365.25)
    assert mark["residual_pv"] == pytest.approx(expected, abs=.0002)
    assert "next_call" not in mark
    assert mark["barriers"] == mark["claims"] == []


@pytest.mark.parametrize("spot, amount, protected", [
    (5300., 100., True), (3000., 100., True), (2999., 59.98, False), (2750., 55., False), (0., 0., False),
])
def test_reverse_convertible_terminal_barrier_and_same_day_settlement(spot, amount, protected):
    vintage = _vintage(_reverse_terms(lag=0))
    fixing = _fixing(FINAL, spot)
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=FINAL, fixings=(fixing,)))
    assert life["status"] == "matured" and life["terminated"]
    assert [(row["kind"], row["condition_met"]) for row in life["barriers"]] == [("capital", protected)]
    assert life["redemption"]["kind"] == "redemption"
    assert life["redemption"]["amount"] == pytest.approx(amount)
    [coupon] = life["coupon_claims"]
    assert coupon["kind"] == "coupon" and coupon["amount"] == 12.
    assert coupon["event_id"] != life["redemption"]["event_id"]
    mark = _mark(vintage, FINAL, (fixing,))
    assert mark["residual_pv"] == 0 and "next_call" not in mark
    assert mark["claims"] == [{**claim, "pv": claim["amount"]} for claim in (coupon, life["redemption"])]
    assert _mark(vintage, FINAL + timedelta(days=1), (fixing,))["claims"] == []


def test_reverse_convertible_zero_coupon_retains_zero_redemption():
    vintage = _vintage(_reverse_terms()).model_copy(update={"annual_coupon": 0.})
    fixing = _fixing(FINAL, 0.)
    life = check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=FINAL, fixings=(fixing,)))
    assert life["coupon_claims"] == []
    assert life["redemption"]["amount"] == 0.
    [redemption] = _mark(vintage, FINAL, (fixing,))["claims"]
    assert redemption == {**life["redemption"], "pv": 0.}
