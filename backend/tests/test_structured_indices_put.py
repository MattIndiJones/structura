"""European put premium and payoff witnesses, in EUR per 100 of strike-date reference."""

from datetime import timedelta
from math import exp

import pytest
from pydantic import ValidationError

from backend.app.core.structured_indices.athena import check_athena_lifecycle, price_athena_issue
from backend.app.core.structured_indices.schemas import AthenaIssueRequest, AthenaLifecycleRequest
from backend.tests.test_structured_indices_athena import FIRST, FINAL, PRICING, STRIKE, _fixing, _mark, _market, _terms


def _request(spot=5000., *, strike=.90, lag=2, days=(FIRST,)):
    return AthenaIssueRequest(
        note_id="european-put",
        terms={**_terms(days=days, lag=lag).model_dump(), "payoff": {"id": "european-put-sx5e", "strike_ratio": strike}},
        initial_fixing=5000., initial_fixing_reference="official-strike",
        market=_market(STRIKE, spot=spot), pricing=PRICING, quote={"mode": "fixed"},
    )


def _discounted(amount, origin, payment):
    return amount * exp(-.03 * (payment - origin).days / 365.25)


def test_put_long_price_and_live_mark_use_strike_reference_and_accept_zero_premium():
    request = _request(spot=4200.)
    issue = price_athena_issue(request)
    due = request.terms.observations[0].payment_date
    assert issue["status"] == "issued" and issue["price"] == pytest.approx(_discounted(6., STRIKE, due), abs=.0002)
    assert "coupon_rate" not in issue and "annual_coupon" not in issue["vintage"] and "quote_result" not in issue
    live = AthenaLifecycleRequest(vintage=issue["vintage"], as_of=STRIKE, fixings=())
    lifecycle = check_athena_lifecycle(live)
    assert lifecycle["status"] == "active" and lifecycle["option_settlement"] is None
    assert lifecycle["redemption"] is None and lifecycle["barriers"] == []
    day = FIRST - timedelta(days=3)
    mark = _mark(live.vintage, day, spot=4000.)
    assert mark["residual_pv"] == pytest.approx(_discounted(10., day, due), abs=.0002)
    assert mark["claims"] == mark["barriers"] == [] and "next_call" not in mark
    zero = price_athena_issue(_request())
    assert zero["price"] == 0. and zero["status"] == "issued" and zero["vintage"] is not None


@pytest.mark.parametrize("spot,amount", [(0., 90.), (4200., 6.), (4500., 0.), (5000., 0.)])
@pytest.mark.parametrize("lag", [0, 2])
def test_put_at_expiry_settles_only_the_intrinsic_amount(spot, amount, lag):
    issue = price_athena_issue(_request(lag=lag))
    fixing = _fixing(FIRST, spot)
    lifecycle = AthenaLifecycleRequest(vintage=issue["vintage"], as_of=FIRST, fixings=(fixing,))
    result = check_athena_lifecycle(lifecycle)
    assert result["status"] == "matured" and result["terminated"]
    assert result["redemption"] is None and result["barriers"] == []
    payoff = result["option_settlement"]
    due = lifecycle.vintage.terms.observations[0].payment_date
    assert payoff["kind"] == "option_payoff"
    assert payoff["amount"] == pytest.approx(amount)
    assert payoff["observed_date"] == FIRST.isoformat() and payoff["payment_date"] == due.isoformat()
    assert result["fixing_references"][FIRST.isoformat()] == fixing.reference
    mark = _mark(lifecycle.vintage, FIRST, (fixing,), spot=5200.)
    assert mark["residual_pv"] == 0. and "next_call" not in mark and mark["barriers"] == []
    assert mark["claims"] == [{**payoff, "pv": _discounted(payoff["amount"], FIRST, due)}]
    assert _mark(lifecycle.vintage, max(FIRST + timedelta(days=1), due), (fixing,))["claims"] == []


@pytest.mark.parametrize("invalid", [{"strike": 0.}, {"strike": 3.1}, {"days": (FIRST, FINAL)}])
def test_european_put_rejects_invalid_strike_and_observation_cardinality(invalid):
    with pytest.raises(ValidationError):
        _request(**invalid)
