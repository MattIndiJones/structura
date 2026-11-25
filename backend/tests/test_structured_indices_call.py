"""Independent European call and call-put parity witnesses on the Structura adapter."""

from math import exp, log, sqrt
from statistics import NormalDist

import pytest

from backend.app.core.structured_indices.athena import check_athena_lifecycle, price_athena_issue
from backend.app.core.structured_indices.schemas import AthenaIssueRequest, AthenaLifecycleRequest
from backend.tests.test_structured_indices_athena import FIRST, STRIKE, _fixing, _mark
from backend.tests.test_structured_indices_put import _request as _put_request


def _call_request(put):
    source = put.model_dump()
    source["terms"]["payoff"]["id"] = "european-call-sx5e"
    return AthenaIssueRequest.model_validate(source)


def test_call_and_put_price_parity_with_dated_payment_and_forward():
    put = _put_request(spot=4800., strike=1.02)
    market = put.market.model_copy(update={"rate": .031, "dividend_yield": .05, "volatility": .22})
    put = put.model_copy(update={"market": market, "pricing": put.pricing.model_copy(update={"n_paths": 20_000})})
    call = _call_request(put)
    settlement = put.terms.observations[0].payment_date
    term = (FIRST - STRIKE).days / 365.25
    forward = market.spot / put.initial_fixing * exp((market.rate - market.dividend_yield) * term)
    strike = put.terms.payoff.strike_ratio
    discount = exp(-(market.rate + market.funding_spread) * (settlement - STRIKE).days / 365.25)
    total_vol = market.volatility * sqrt(term)
    d1 = log(forward / strike) / total_vol + total_vol / 2
    d2 = d1 - total_vol
    cdf = NormalDist().cdf
    analytical_call = 100 * discount * (forward * cdf(d1) - strike * cdf(d2))
    put_price = price_athena_issue(put)["price"]
    call_price = price_athena_issue(call)["price"]
    assert call_price == pytest.approx(analytical_call, abs=.15)
    assert call_price - put_price == pytest.approx(100 * (forward - strike) * discount, abs=.10)


@pytest.mark.parametrize("spot,amount", [(0., 0.), (4750., 0.), (5200., 9.), (12500., 155.)])
def test_call_settles_only_the_right_side_of_the_strike(spot, amount):
    request = _call_request(_put_request(lag=0, strike=.95))
    call = price_athena_issue(request)
    assert call["status"] == "issued" and "coupon_rate" not in call
    final = _fixing(FIRST, spot)
    lifecycle = AthenaLifecycleRequest(vintage=call["vintage"], as_of=FIRST, fixings=(final,))
    receipt = check_athena_lifecycle(lifecycle)
    assert receipt["status"] == "matured" and receipt["redemption"] is None and receipt["barriers"] == []
    claim = receipt["option_settlement"]
    assert claim["kind"] == "option_payoff" and claim["amount"] == pytest.approx(amount)
    mark = _mark(lifecycle.vintage, FIRST, (final,))
    assert mark["claims"] == [{**claim, "pv": claim["amount"]}]
    assert mark["residual_pv"] == 0. and "next_call" not in mark
