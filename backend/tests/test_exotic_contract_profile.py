"""The contract profile sweeps a coupon input or recovery, without a reprice."""

from copy import deepcopy

import pytest

from backend.app.services.exotic_contract_profile import ExoticContractProfileError, exotic_contract_profile
from backend.app.services.exotic_valuation import read_scenario
from backend.tests.test_exotic_pricer_api import EXOTICS, _credit, _json, _price, _rates, product_client  # noqa: F401


def test_cms_cap_floor_and_spread_have_the_contractual_signed_amount():
    body = _rates()
    body["terms"]["side"] = "SELL"
    flow = body["terms"]["cashflows"][0]
    flow.update(payoff="caplet", strike=.02)
    profile = exotic_contract_profile(read_scenario(body), points=(.01, .02, .03))
    assert profile.selected.axis == "rate_fraction"
    assert profile.side == "SELL"
    assert [row.amount_eur for row in profile.points] == pytest.approx([0, 0, -2500])
    assert [row.amount_per_100 for row in profile.points] == pytest.approx([0, 0, -.25])
    flow["payoff"] = "floorlet"
    assert [row.amount_eur for row in exotic_contract_profile(read_scenario(body), points=(.01, .02, .03)).points] == pytest.approx([
        -2500, 0, 0,
    ])

    flow.update(payoff="linear", strike=None, gearing=3, margin=.006, floor=0, cap=.025,
                spread_index={"kind": "swap", "fixed_periods": [{"payment": 2, "year_fraction": 1}],
                              "floating_periods": [{"start": 1, "end": 2, "year_fraction": 1}]})
    spread = exotic_contract_profile(read_scenario(body), points=(-.01, 0., .02))
    assert spread.selected.axis == "spread_fraction"
    assert [row.amount_eur for row in spread.points] == pytest.approx([0, -1500, -6250])


def test_profile_uses_effective_payscript_parameters_and_identifies_acquired_fixing():
    body = _rates()
    flow = body["terms"]["cashflows"][0]
    flow.update(fixing=0.0, realized_rate=.031, payscript={
        "profile": "rates-exotic-coupon-v1",
        "source": "PARAM STRIKE = 2%\nAT CMS_COUPON:\n  PAY YEAR_FRACTION * MAX(CMS_RATE - STRIKE, 0)",
        "parameters": {"STRIKE": .025},
    })
    snapshot = read_scenario(body)
    initial = snapshot.model_dump(mode="json")
    profile = exotic_contract_profile(snapshot, points=(.02, .025, .03))
    assert profile.selected.calculation == "payscript"
    assert profile.acquired_x == .031 and profile.acquired_amount_eur == pytest.approx(1500)
    assert [row.amount_eur for row in profile.points] == pytest.approx([0, 0, 1250])
    assert snapshot.model_dump(mode="json") == initial


def test_range_bounds_retain_acquired_weights_and_script_controls_payout():
    body = _rates()
    index = {"kind": "forward", "start": 0.5, "end": .75, "year_fraction": .25}
    flow = {
        "kind": "range_accrual", "flow_id": "range", "payment": 1., "year_fraction": .25,
        "annual_rate": .04, "lower": .01, "upper": .03, "lower_inclusive": False, "observations": [
            {"time": -0.5, "index": index, "weight": 1, "realized_rate": .01},
            {"time": -0.25, "index": index, "weight": 1, "realized_rate": .03},
            {"time": .5, "index": index, "weight": 2},
        ],
    }
    body["terms"]["cashflows"] = [flow]
    profile = exotic_contract_profile(read_scenario(body), points=(.25, .5, .75))
    assert profile.selected.axis == "occupation_fraction"
    assert (profile.minimum_x, profile.maximum_x) == (.25, .75)
    assert [row.amount_eur for row in profile.points] == pytest.approx([2500, 5000, 7500])
    with pytest.raises(ExoticContractProfileError) as refused:
        exotic_contract_profile(read_scenario(body), points=(0., 1.))
    assert refused.value.code == "EXOTIC_CONTRACT_PROFILE_GRID"

    flow["payscript"] = {
        "profile": "rates-exotic-coupon-v1",
        "source": "AT RANGE_COUPON:\n  PAY YEAR_FRACTION * ANNUAL_RATE * INDIC(RANGE_FRACTION > 0.5)",
    }
    result = exotic_contract_profile(read_scenario(body), points=(.25, .5, .75))
    assert [row.amount_eur for row in result.points] == pytest.approx([0, 0, 10000])


def test_credit_profiles_are_gross_recovery_or_protection_in_position_sign():
    body = _credit()
    body["credit"]["contract"]["side"] = "SELL"
    seller = exotic_contract_profile(read_scenario(body), points=(0., .40, 1.))
    assert seller.selected.flow_id == "protection"
    assert [row.amount_eur for row in seller.points] == pytest.approx([-1e6, -600_000, 0])
    assert seller.selected.axis == "recovery_fraction"
    body["credit"]["market"]["marginals"] = body["credit"]["market"]["marginals"][:1]
    body["credit"]["contract"].update(kind="cln", trigger_rank=None, side="BUY")
    cln = exotic_contract_profile(read_scenario(body), points=(0., .40, 1.))
    assert cln.selected.flow_id == "default_redemption"
    assert [row.amount_eur for row in cln.points] == pytest.approx([0, 400_000, 1e6])


def test_contract_profile_http_uses_signed_receipt_and_same_engine(product_client):
    run = _price(product_client, _rates())
    path = f"{EXOTICS}/contract-profile"
    profile = _json(product_client.post(path, json={"receipt": run["receipt"], "flow_id": "cms", "points": [-.01, .02]}))
    assert profile["measure"] == "undiscounted_signed_contractual_amount"
    assert [point["amount_eur"] for point in profile["points"]] == pytest.approx([-2500, 5000])
    invalid = deepcopy(run["receipt"])
    invalid["request"]["terms"]["nominal_eur"] = 5e6
    _json(product_client.post(path, json={"receipt": invalid}), 422)
    product_client.current["user"] = product_client.users["bob"]
    _json(product_client.post(path, json={"receipt": run["receipt"]}), 404)
