"""Contractual checks of UAT scripts, without providers or a persistent DB."""
from datetime import date

import pytest

from backend.app.core.calendars import adjust, BusinessDayConvention
from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.engine import eval_script_on_history
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.services.uat_generation import (
    LIFECYCLE_PROFILE_KEYS, UatGenerationRequest, _build_specs,
)


CATALOGUE_KEYS = {
    "ATHENA": "autocall_athena",
    "PHOENIX": "phoenix_memoire",
    "REVERSE_CONVERTIBLE": "reverse_convertible",
    "CAPITAL_GUARANTEED": "capital_garanti",
}


def _spec(family, count_underlyings=1, profile="FORWARD_START"):
    return _build_specs(UatGenerationRequest(
        target_user_id=1, count=1, seed=29, product_types=[family],
        underlying_tickers=["AAPL", "MC.PA"],
        min_underlyings=count_underlyings, max_underlyings=count_underlyings,
        maturity_min_years=4, maturity_max_years=4,
        lifecycle_profile=profile,
    ))[0]


def _resolved(spec):
    params = spec["params"]
    return resolve_constats(parse_script(spec["script"]), params["constats"],
                           anchor=date.fromisoformat(params["strike_date"]),
                           currency=params["currency"])


@pytest.mark.parametrize("family", CATALOGUE_KEYS)
def test_uat_uses_the_exact_current_catalogue_script(family):
    spec = _spec(family)
    assert spec["script"] == PRODUCTS[CATALOGUE_KEYS[family]]["script"]
    compiled = _resolved(spec)
    assert compiled.underlying_name == "BASKET"
    assert compiled.initial_fixing_name == "STARTDATE"
    assert all(p.required and p.is_pct for p in compiled.params)
    assert set(spec["params"]["user_params"]) == {p.name for p in compiled.params}


PROFILE_FAMILIES = [
    (profile, family)
    for profile in LIFECYCLE_PROFILE_KEYS
    for family in CATALOGUE_KEYS
    if not (profile in {"ACTIVE_1Y_PENDING", "ACTIVE_2Y_OFFICIAL", "CALLED"}
            and family not in {"ATHENA", "PHOENIX"})
    and not (profile == "MATURED_KI" and family == "CAPITAL_GUARANTEED")
]


@pytest.mark.parametrize("profile,family", PROFILE_FAMILIES)
@pytest.mark.parametrize("count_underlyings", [1, 2])
def test_generated_calendars_keep_fixing_separate_and_include_first_observation(
    profile, family, count_underlyings,
):
    spec = _spec(family, count_underlyings, profile)
    compiled = _resolved(spec)
    params = spec["params"]
    assert len(params["underlyings"]) == count_underlyings
    assert params["constats"]["STARTDATE"] == params["strike_date"]
    assert compiled.origine == date.fromisoformat(params["strike_date"])
    assert all(c.t > 0 for c in compiled.echeancier.constatations)
    if family in {"ATHENA", "PHOENIX"}:
        event = compiled.events[0]
        calendar = params["constats"]["OBSERVATIONDATES"]
        first = adjust(date.fromisoformat(calendar["first_observation_date"]),
                       params["currency"], BusinessDayConvention.FOLLOWING)
        assert event.dates[0] == pytest.approx((first - compiled.origine).days / 365.25)
        assert event.ranks == list(range(1, len(event.dates) + 1))
        assert compiled.events[-1].dates == [event.dates[-1]]
    assert max(d for e in compiled.events for d in e.dates) == pytest.approx(params["T"], abs=1e-6)


def _replay(family, levels, count_underlyings=1, **overrides):
    spec = _spec(family, count_underlyings)
    compiled = _resolved(spec)
    observations = sorted({c.jour for c in compiled.echeancier.constatations})
    days = [compiled.origine.isoformat(), *(d.isoformat() for d in observations)]
    # Individual initial levels must cancel in Basket.yield. In a multi-asset
    # case the second asset remains high, leaving the first as the worst-of.
    prices = {"A": [100, *(100 * levels[min(i, len(levels) - 1)]
                            for i in range(len(observations)))]}
    if count_underlyings == 2:
        prices["B"] = [200, *([240] * len(observations))]
    parameters = {**spec["params"]["user_params"], **overrides}
    result = eval_script_on_history(compiled, days, prices, 0, spec["params"]["T"],
                                    parameters, list(prices), r=0,
                                    origine=compiled.origine)
    return result["cash_flows"], parameters, len(observations)


@pytest.mark.parametrize("count_underlyings", [1, 2])
def test_phoenix_memory_catches_up_missed_coupon_before_call(count_underlyings):
    flows, _, _ = _replay("PHOENIX", [.5, .9, 1.], count_underlyings,
                          COUPON=.025, M_CPN_BAR=.8, M_AC_BAR=1., M_KI_BAR=.6)
    assert [f["cf"] for f in flows] == pytest.approx([.05, .025, 1.])
    assert flows[0]["date"] < flows[1]["date"] == flows[2]["date"]
    assert sum(f["cf"] for f in flows) == pytest.approx(1.075)


@pytest.mark.parametrize("family", ["ATHENA", "PHOENIX"])
def test_first_observation_coupon_does_not_count_startdate(family):
    flows, _, _ = _replay(family, [1.], COUPON=.025, M_AC_BAR=1., M_KI_BAR=.6,
                          **({"M_CPN_BAR": .8} if family == "PHOENIX" else {}))
    assert sum(f["cf"] for f in flows) == pytest.approx(1.025)
    assert len(flows) == 2


@pytest.mark.parametrize("family", ["ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE"])
@pytest.mark.parametrize("count_underlyings", [1, 2])
def test_maturity_keeps_capital_and_sold_put_as_separate_flows(family, count_underlyings):
    overrides = {"COUPON": .08, "M_KI_BAR": .6}
    if family in {"ATHENA", "PHOENIX"}:
        overrides["M_AC_BAR"] = 1.
    if family == "PHOENIX":
        overrides["M_CPN_BAR"] = .8
    flows, _, _ = _replay(family, [.4], count_underlyings, **overrides)
    assert [f["cf"] for f in flows[-2:]] == pytest.approx([1., -.6])
    assert len(flows) == (3 if family == "REVERSE_CONVERTIBLE" else 2)
    expected = .48 if family == "REVERSE_CONVERTIBLE" else .4
    assert sum(f["cf"] for f in flows) == pytest.approx(expected)


def test_capital_guaranteed_participation_is_supplied_by_economics():
    flows, _, _ = _replay("CAPITAL_GUARANTEED", [1.2], PART=.9, STRIKE=1.)
    assert [f["cf"] for f in flows] == pytest.approx([1., .18])
