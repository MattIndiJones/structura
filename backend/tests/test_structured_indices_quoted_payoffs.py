"""Independent price, solver and dated cash flow witnesses for the three quoted payoffs."""

from datetime import timedelta
from math import exp

import pytest
from pydantic import ValidationError

from backend.app.core.structured_indices.athena import check_athena_lifecycle, price_athena_issue
from backend.app.core.structured_indices.schemas import AthenaIssueRequest, AthenaLifecycleRequest
from backend.tests.test_structured_indices_athena import (
    FINAL, FIRST, SEMIANNUAL, PRICING, STRIKE, _fixing, _mark, _market, _terms,
)


GUARANTEED = {"id": "capital-guaranteed-sx5e", "participation_strike": 1., "participation": 1.5}
BOOSTER = {"id": "booster-sx5e", "participation": 1.5, "redemption_cap": 1.3}
GEAR = {"id": "autocall-gear-put-sx5e", "put_strike": .6, "gearing": 2., "single_coupon": .075}


def _issue_arguments(payoff, *, days=(FINAL,), lag=2, months=12, spot=5500.):
    return {
        "note_id": payoff["id"], "terms": {**_terms(days=days, months=months, lag=lag).model_dump(), "payoff": payoff},
        "initial_fixing": 5000., "initial_fixing_reference": "official-strike",
        "market": _market(STRIKE, spot=spot), "pricing": PRICING, "quote": {"mode": "fixed"},
    }


def _issue_request(payoff, **kwargs):
    return AthenaIssueRequest.model_validate(_issue_arguments(payoff, **kwargs))


def _vintage(request):
    return price_athena_issue(request)["vintage"]


def _life(vintage, day, *fixings):
    return check_athena_lifecycle(AthenaLifecycleRequest(vintage=vintage, as_of=day, fixings=fixings))


def _discounted(amount, day, payment):
    return amount * exp(-.03 * (payment - day).days / 365.25)


@pytest.mark.parametrize("payoff,quantity,expected,integral,limits,method", [
    (GUARANTEED, "participation", 1.5, 115., (0., 3.), "affine_common_random_numbers"),
    (BOOSTER, "participation", 1.5, 115., (0., 4.), "bisection_common_random_numbers"),
    ({**BOOSTER, "participation": 3.}, "redemption_cap", 1.2, 120., (1., 1.25), "bisection_common_random_numbers"),
    (GEAR, "single_coupon", .075, 107.5, (0., .3), "affine_common_random_numbers"),
])
def test_solve_contract_quantity_on_frozen_paths(payoff, quantity, expected, integral, limits, method):
    args = _issue_arguments({key: value for key, value in payoff.items() if key != quantity})
    payment = args["terms"]["observations"][0]["payment_date"]
    target = _discounted(integral, STRIKE, payment)
    args["quote"] = {
        "mode": "solve_to_target", "quantity": quantity, "target_price": target,
        "minimum": limits[0], "maximum": limits[1],
    }
    request = AthenaIssueRequest.model_validate(args)
    result = price_athena_issue(request)
    assert result["status"] == "issued", result
    raw = result["quote_result"]
    assert (raw["quantity"], raw["unit"]) == (quantity, "fraction")
    assert raw["value"] == pytest.approx(expected, abs=.001)
    assert result["solver"]["method"] == method
    assert result["solver"]["minimum_price"] <= target <= result["solver"]["maximum_price"]
    assert result["price"] == pytest.approx(target, abs=.01)
    assert result["vintage"]["terms"]["payoff"][quantity] == raw["value"]
    assert "coupon_rate" not in result and "annual_coupon" not in result["vintage"]
    assert price_athena_issue(request) == result


def test_quote_reports_unreachable_budget_and_booster_plateau_uses_upper_bound():
    capital_args = _issue_arguments({"id": GUARANTEED["id"], "participation_strike": 1.})
    capital_args["quote"] = {"mode": "solve_to_target", "quantity": "participation",
                             "target_price": 50., "minimum": 0., "maximum": 3.}
    no_issue = price_athena_issue(AthenaIssueRequest.model_validate(capital_args))
    assert no_issue["status"] == "no_parameter_in_bounds"
    assert no_issue["vintage"] is no_issue["price"] is None and no_issue["receipt_id"]
    assert "quote_result" not in no_issue

    booster_args = _issue_arguments({"id": BOOSTER["id"], "redemption_cap": 1.3}, spot=6000.)
    payment = booster_args["terms"]["observations"][0]["payment_date"]
    booster_args["quote"] = {"mode": "solve_to_target", "quantity": "participation",
                              "target_price": _discounted(130., STRIKE, payment), "minimum": 0., "maximum": 5.}
    issue = price_athena_issue(AthenaIssueRequest.model_validate(booster_args))
    assert issue["quote_result"]["value"] == 5. and issue["status"] == "issued"


@pytest.mark.parametrize("payoff,final_spot,principal,gain", [
    (GUARANTEED, 0., 100., 0.), (GUARANTEED, 5000., 100., 0.), (GUARANTEED, 5500., 100., 15.),
    (BOOSTER, 0., 0., 0.), (BOOSTER, 2000., 40., 0.), (BOOSTER, 5000., 100., 0.),
    (BOOSTER, 5500., 100., 15.), (BOOSTER, 6500., 100., 30.),
])
def test_terminal_payoffs_separate_participation_from_principal(payoff, final_spot, principal, gain):
    vintage = _vintage(_issue_request(payoff, lag=0))
    assert _life(vintage, FIRST)["participation_claims"] == []
    mark = _mark(vintage, FIRST, spot=5500.)
    assert mark["status"] == "active" and "next_call" not in mark
    assert mark["residual_pv"] == pytest.approx(_discounted(115., FIRST, FINAL), abs=.0002)
    assert mark["claims"] == mark["barriers"] == []
    final = _fixing(FINAL, final_spot)
    life = _life(vintage, FINAL, final)
    assert life["status"] == "matured" and life["barriers"] == []
    assert life["fixing_references"][FINAL.isoformat()] == final.reference
    assert life["redemption"]["amount"] == pytest.approx(principal)
    assert [row["amount"] for row in life["participation_claims"]] == pytest.approx([gain] if gain else [])
    claims = _mark(vintage, FINAL, (final,))["claims"]
    assert [row["kind"] for row in claims] == (["participation"] if gain else []) + ["redemption"]
    assert claims == [{**row, "pv": row["amount"]} for row in [*life["participation_claims"], life["redemption"]]]
    assert len({row["event_id"] for row in claims}) == len(claims)
    assert _mark(vintage, FINAL + timedelta(days=1), (final,))["claims"] == []


@pytest.mark.parametrize("final_spot,status,principal,capital_passed", [
    (5000., "called", 100., None), (3000., "matured", 100., True), (2700., "matured", 80., False),
    (1500., "matured", 0., False), (0., "matured", 0., False),
])
def test_gear_put_call_and_leveraged_loss_relative_to_put_strike(final_spot, status, principal, capital_passed):
    vintage = _vintage(_issue_request(GEAR, days=(SEMIANNUAL, FIRST, FINAL), months=6, lag=0))
    missed = (_fixing(SEMIANNUAL, 3000.), _fixing(FIRST, 4500.))
    before = _mark(vintage, FINAL - timedelta(days=1), missed, spot=5500.)
    assert before["next_call"]["probability"] == 1.
    assert before["next_call"]["is_final_observation"]
    assert before["next_call"]["redemption_amount"] == pytest.approx(107.5)
    assert before["claims"] == []
    final = _fixing(FINAL, final_spot)
    life = _life(vintage, FINAL, *missed, final)
    assert life["status"] == status and life["redemption"]["amount"] == pytest.approx(principal)
    assert [row["amount"] for row in life["coupon_claims"]] == ([7.5] if status == "called" else [])
    barriers = [(row["kind"], row["threshold"], row["condition_met"]) for row in life["barriers"]]
    assert barriers[:3] == [("call", 1., False), ("call", 1., False), ("call", 1., status == "called")]
    assert barriers[3:] == ([("capital", .6, capital_passed)] if capital_passed is not None else [])


def test_gear_put_first_semester_coupon_is_not_annualized():
    vintage = _vintage(_issue_request(GEAR, days=(SEMIANNUAL, FIRST, FINAL), months=6))
    life = _life(vintage, SEMIANNUAL, _fixing(SEMIANNUAL, 5000.))
    assert life["status"] == "called"
    assert [row["amount"] for row in life["coupon_claims"]] == [7.5]


@pytest.mark.parametrize("payoff,terms_override,quote,extra", [
    (GUARANTEED, {"call_barrier": .95}, {"mode": "fixed"}, {}),
    (GUARANTEED, {"coupon_memory": True}, {"mode": "fixed"}, {}),
    (GUARANTEED, {}, {"mode": "fixed"}, {"coupon": {"mode": "fixed", "fixed_coupon": .06}}),
    (GUARANTEED, {}, {"mode": "solve_to_target", "quantity": "participation", "minimum": 0., "maximum": 5.,
                     "target_price": 100.}, {}),
    (GEAR, {"call_barrier": 1.3}, {"mode": "fixed"}, {}),
    ({**GEAR, "put_strike": 1.1}, {}, {"mode": "fixed"}, {}),
    ({**GEAR, "gearing": .5}, {}, {"mode": "fixed"}, {}),
    ({"id": BOOSTER["id"], "participation": 0.}, {}, {"mode": "solve_to_target", "quantity": "redemption_cap",
                                                     "minimum": 1., "maximum": 2., "target_price": 100.}, {}),
    ({**BOOSTER, "redemption_cap": .99}, {}, {"mode": "fixed"}, {}),
    (BOOSTER, {}, {"mode": "fixed"}, {"pricing": {"model": "heston", "n_paths": 32}}),
])
def test_quoted_contract_validation_rejects_mixed_or_out_of_domain_terms(payoff, terms_override, quote, extra):
    raw = _issue_arguments(payoff)
    raw["terms"].update(terms_override)
    raw.update(quote=quote, **extra)
    with pytest.raises(ValidationError):
        AthenaIssueRequest.model_validate(raw)
