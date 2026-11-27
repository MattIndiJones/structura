"""Check the synthetic FRN/IRS reference with an independent Decimal calculation."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


REFERENCE_FILE = Path(__file__).with_name("fixtures") / "rates_credit_abc.json"
ONE_BP = Decimal("0.0001")


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))


def _date(value):
    return date.fromisoformat(value)


def _instant(value):
    return datetime.fromisoformat(value)


def _eligible(record, cutoff):
    return (
        record["validated_at"] is not None
        and _instant(record["available_at"]) <= cutoff
        and _instant(record["validated_at"]) <= cutoff
    )


def _fixing_for_period(reference, period, cutoff, observations):
    contractual_date = _date(period["fixing_date"])
    eligible_fixings = [
        item for item in observations
        if item["observation_date"] == period["fixing_date"]
        and item["status"] == "validated"
        and _eligible(item, cutoff)
    ]
    if eligible_fixings:
        return max(eligible_fixings, key=lambda item: item["version"])
    due = time.fromisoformat(reference["clock"]["fixing_due_local"])
    if datetime.combine(contractual_date, due, ZoneInfo(reference["clock"]["timezone"])) <= cutoff:
        raise ValueError("fixing_unavailable")
    return None


def _payment_state(payment, cutoff):
    if cutoff.date() < _date(payment["effect_date"]):
        return "future"
    return "paid" if _eligible(payment, cutoff) else "due_open"


def _factor(pillars, target, shift=Decimal("0")):
    (anchor, anchor_factor), (terminal, terminal_factor) = pillars
    elapsed = (target - _date(anchor)).days
    duration = (_date(terminal) - _date(anchor)).days
    assert 0 <= elapsed <= duration, "Requested date is outside the reference curve"
    weight = Decimal(elapsed) / duration
    log_factor = Decimal(anchor_factor).ln() * (1 - weight) + Decimal(terminal_factor).ln() * weight
    return (log_factor - shift * elapsed / 365).exp()


def _forward(pillars, period, shift):
    start = _date(period["start_adjusted"])
    end = _date(period["end_adjusted"])
    fraction = Decimal(period["act360_days"]) / 360
    return (_factor(pillars, start, shift) / _factor(pillars, end, shift) - 1) / fraction


def _price(reference, snapshot, cutoff, observations=None, *, discount_shift=Decimal("0"), projection_shift=Decimal("0")):
    terms = reference["terms"]
    notional = Decimal(terms["notional_eur"])
    margin = Decimal(terms["frn"]["margin_bp"]) * ONE_BP
    fixed_rate = Decimal(terms["irs"]["fixed_rate"])
    settlement = _date(snapshot["settlement_date"])
    payment = reference["first_payment"]
    observations = reference["fixings"] if observations is None else observations
    coupon_pv = floating_pv = accrued = Decimal("0")
    flows = {}
    for period in reference["floating_periods"]:
        fixing = _fixing_for_period(reference, period, cutoff, observations)
        rate = Decimal(fixing["rate"]) if fixing else _forward(snapshot["euribor_pillars"], period, projection_shift)
        fraction = Decimal(period["act360_days"]) / 360
        frn_coupon = notional * (rate + margin) * fraction
        irs_coupon = notional * rate * fraction
        flows[period["period_id"]] = (frn_coupon, -irs_coupon)
        if period["frn_flow_id"] == payment["frn_flow_id"] and _payment_state(payment, cutoff) == "paid":
            continue
        discount = _factor(snapshot["ois_pillars"], _date(period["payment_date"]), discount_shift)
        coupon_pv += frn_coupon * discount
        floating_pv += irs_coupon * discount
        start, end = _date(period["start_adjusted"]), _date(period["end_adjusted"])
        if start <= settlement < end:
            accrued = notional * (rate + margin) * (settlement - start).days / 360

    principal_pv = (
        notional * Decimal(terms["frn"]["principal_fraction"])
        * _factor(snapshot["ois_pillars"], _date(terms["frn"]["principal_payment_date"]), discount_shift)
    )
    annuity = sum(
        Decimal(period["fraction_30e360"])
        * _factor(snapshot["ois_pillars"], _date(period["payment_date"]), discount_shift)
        for period in reference["fixed_periods"]
    )
    fixed_pv = notional * fixed_rate * annuity
    dirty = coupon_pv + principal_pv
    return {
        "frn": {
            "coupon_pv": coupon_pv, "principal_pv": principal_pv,
            "dirty_pv": dirty, "accrued": accrued, "clean_pv": dirty - accrued,
        },
        "irs": {"fixed_pv": fixed_pv, "floating_pv_abs": floating_pv, "net_pv": fixed_pv - floating_pv},
        "clean_price": (dirty - accrued) / notional * 100,
        "par_rate": floating_pv / (notional * annuity),
        "flows": flows,
    }


def _amounts_close(actual, expected, tolerance):
    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        assert abs(actual[name] - Decimal(value)) <= tolerance, name


def test_contractual_reference_eur_terms_and_dates(reference):
    terms = reference["terms"]
    assert reference["provenance"]["kind"] == "synthetic"
    assert terms["calendar"] == "TARGET"
    assert terms["business_day_convention"] == "modified_following"
    assert terms["floating"]["day_count"] == "ACT/360"
    assert terms["floating"]["index"] == "EURIBOR" and terms["floating"]["tenor"] == "3M"
    assert terms["irs"]["fixed_day_count"] == "30E/360"
    assert Decimal(terms["frn"]["funding_bp"]) == Decimal(terms["irs"]["floating_margin_bp"]) == 0
    assert terms["irs"]["position"] == "receive_fixed"
    assert not terms["irs"]["exchange_notional"] and not terms["frn"]["include_subscription_cash"]

    periods = reference["floating_periods"]
    assert [item["act360_days"] for item in periods] == [91, 91, 91, 92, 91, 91, 92, 92]
    assert periods[0]["start_adjusted"] == terms["effective_date"]
    assert periods[-1]["payment_date"] == terms["maturity_date"] == terms["frn"]["principal_payment_date"]
    flow_ids = [terms["frn"]["principal_flow_id"]]
    for period in periods:
        start, end = _date(period["start_adjusted"]), _date(period["end_adjusted"])
        assert period["payment_date"] == period["end_adjusted"]
        assert (end - start).days == period["act360_days"]
        # There are no TARGET holidays in these eight specific fixing windows.
        fixing = start
        for _ in range(terms["floating"]["fixing_lag_target_days"]):
            fixing -= timedelta(days=1)
            while fixing.weekday() >= 5:
                fixing -= timedelta(days=1)
        assert fixing == _date(period["fixing_date"])
        flow_ids.extend([period["frn_flow_id"], period["irs_flow_id"]])
    for previous, following in zip(periods, periods[1:]):
        assert previous["end_unadjusted"] == following["start_unadjusted"]
        assert previous["end_adjusted"] == following["start_adjusted"]
    assert periods[1]["end_unadjusted"] == "2027-03-21"
    assert periods[1]["end_adjusted"] == "2027-03-22"
    fixed = reference["fixed_periods"]
    assert [item["payment_date"] for item in fixed] == ["2027-09-21", "2028-09-21"]
    assert [Decimal(item["fraction_30e360"]) for item in fixed] == [1, 1]
    notional = Decimal(terms["notional_eur"])
    fixed_rate = Decimal(terms["irs"]["fixed_rate"])
    for period in fixed:
        coupon = notional * fixed_rate * Decimal(period["fraction_30e360"])
        assert coupon.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(period["coupon_eur"])
    flow_ids.extend(item["flow_id"] for item in fixed)
    assert len(flow_ids) == len(set(flow_ids))


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_market_snapshot_timestamps_pillars_and_selected_observations(reference, label):
    definition = reference["curve_definitions"]
    snapshot = reference["snapshots"][label]
    cutoff = _instant(snapshot["cutoff_local"])
    paris = ZoneInfo(reference["clock"]["timezone"])
    settlement = _date(snapshot["settlement_date"])
    assert cutoff.astimezone(timezone.utc) == _instant(snapshot["cutoff_utc"])
    assert cutoff.utcoffset() == cutoff.astimezone(paris).utcoffset()
    assert cutoff.date() == _date(snapshot["market_date"]) == _date(snapshot["valuation_date"]) == settlement
    assert _instant(snapshot["market_available_at"]).time() == time(9)
    assert _instant(snapshot["market_available_at"]) == _instant(snapshot["market_validated_at"]) <= cutoff
    assert reference["clock"]["inclusive_cutoff"]
    assert len({item["market_id"] for item in reference["snapshots"].values()}) == 3
    assert snapshot["market_version"] == 1
    assert definition["ois"]["role"] == "discount" and definition["ois"]["index"] == "ESTR"
    assert definition["euribor"]["role"] == "projection" and definition["euribor"]["tenor"] == "3M"
    assert definition["day_count"] == "ACT/365F"
    assert definition["interpolation"] == "log_linear_factor" and not definition["extrapolation"]
    tolerance = Decimal(reference["tolerances"]["curve_factor"])
    for name in ("ois", "euribor"):
        (anchor, anchor_factor), (terminal, terminal_factor) = snapshot[f"{name}_pillars"]
        assert (anchor, terminal) == (snapshot["market_date"], reference["terms"]["maturity_date"])
        days = (_date(terminal) - _date(anchor)).days
        assert days == snapshot["anchor_to_terminal_days"]
        assert Decimal(anchor_factor) == 1
        terminal_from_rate = (-Decimal(definition[name]["continuous_zero_rate"]) * days / 365).exp()
        assert abs(Decimal(terminal_factor) - terminal_from_rate) <= tolerance

    periods = reference["floating_periods"]
    selected = [_fixing_for_period(reference, period, cutoff, reference["fixings"]) for period in periods]
    assert [fixing["fixing_id"] for fixing in selected if fixing] == snapshot["acquired_fixing_ids"]
    assert next(period["start_adjusted"] for period, fixing in zip(periods, selected) if fixing is None) == (
        snapshot["first_required_projection_date"]
    )
    assert _payment_state(reference["first_payment"], cutoff) == snapshot["first_payment_state"]
    elapsed_days = [
        (settlement - _date(period["start_adjusted"])).days
        for period in periods
        if _date(period["start_adjusted"]) <= settlement < _date(period["end_adjusted"])
    ]
    assert sum(elapsed_days) == snapshot["accrued_days"]


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_decimal_reference_prices_and_dv01(reference, label):
    snapshot = reference["snapshots"][label]
    cutoff = _instant(snapshot["cutoff_local"])
    base = _price(reference, snapshot, cutoff)
    amount_tolerance = Decimal(reference["tolerances"]["amount_eur"])
    rate_tolerance = Decimal(reference["tolerances"]["rate_fraction"])
    _amounts_close(base["frn"], snapshot["frn_expected_eur"], amount_tolerance)
    _amounts_close(base["irs"], snapshot["irs_expected_eur"], amount_tolerance)
    assert abs(base["clean_price"] - Decimal(snapshot["frn_clean_price"])) <= Decimal("0.00000001")
    assert abs(base["par_rate"] - Decimal(snapshot["irs_par_rate"])) <= rate_tolerance
    if label == "A":
        assert abs(base["par_rate"] - Decimal(reference["terms"]["irs"]["fixed_rate"])) < Decimal("1e-15")

    projection = _price(reference, snapshot, cutoff, projection_shift=ONE_BP)
    discount = _price(reference, snapshot, cutoff, discount_shift=ONE_BP)
    changes = {
        "frn_projection": projection["frn"]["dirty_pv"] - base["frn"]["dirty_pv"],
        "irs_projection": projection["irs"]["net_pv"] - base["irs"]["net_pv"],
        "frn_discount": discount["frn"]["dirty_pv"] - base["frn"]["dirty_pv"],
        "irs_discount": discount["irs"]["net_pv"] - base["irs"]["net_pv"],
    }
    _amounts_close(changes, snapshot["dv01_eur"], amount_tolerance)
    assert abs(changes["frn_projection"] + changes["irs_projection"]) < Decimal("1e-20")
    assert discount["flows"] == base["flows"]
    assert projection["frn"]["accrued"] == discount["frn"]["accrued"] == base["frn"]["accrued"]


def test_projected_and_acquired_flows_and_payment_transition(reference):
    snapshots = reference["snapshots"]
    a, b, c = (
        _price(reference, snapshots[label], _instant(snapshots[label]["cutoff_local"]))
        for label in ("A", "B", "C")
    )
    expected = reference["additional_references"]
    amount_tolerance = Decimal(reference["tolerances"]["amount_eur"])
    first, second = reference["floating_periods"][:2]
    for period in reference["floating_periods"]:
        frn, irs = a["flows"][period["period_id"]]
        assert abs(frn - Decimal(period["a_frn_coupon_eur"])) <= amount_tolerance
        assert abs(-irs - Decimal(period["a_irs_floating_abs_eur"])) <= amount_tolerance
        forward = _forward(snapshots["A"]["euribor_pillars"], period, Decimal("0"))
        assert abs(forward - Decimal(expected["forward_rate_by_act360_days"][str(period["act360_days"])])) < Decimal("1e-12")
    assert abs(b["flows"][first["period_id"]][0] - Decimal(expected["b_first_frn_coupon_eur"])) <= amount_tolerance
    assert abs(b["flows"][first["period_id"]][1] - Decimal(expected["b_first_irs_floating_eur"])) <= amount_tolerance
    assert abs(c["flows"][second["period_id"]][0] - Decimal(expected["c_second_frn_coupon_eur"])) <= amount_tolerance

    variant = reference["variants"]["first_payment_boundary"]
    before, at = (_instant(variant[name]) for name in ("before_cutoff", "at_cutoff"))
    payment = reference["first_payment"]
    assert _payment_state(payment, before) == variant["before_state"]
    assert _payment_state(payment, at) == variant["at_state"]
    assert (payment["frn_flow_id"], payment["irs_flow_id"]) == (first["frn_flow_id"], first["irs_flow_id"])
    c_snapshot = snapshots[variant["base_snapshot"]]
    assert _factor(c_snapshot["ois_pillars"], _date(payment["effect_date"])) == 1
    cum, ex = (_price(reference, c_snapshot, cutoff) for cutoff in (before, at))
    assert ex == c
    frn_cash, irs_cash = ex["flows"][first["period_id"]]
    assert abs(frn_cash - Decimal(payment["frn_cash_eur"])) <= amount_tolerance
    assert abs(irs_cash - Decimal(payment["irs_cash_eur"])) <= amount_tolerance
    assert abs(cum["frn"]["dirty_pv"] - ex["frn"]["dirty_pv"] - frn_cash) < Decimal("1e-20")
    assert abs(cum["irs"]["net_pv"] - ex["irs"]["net_pv"] - irs_cash) < Decimal("1e-20")
    assert abs(cum["frn"]["dirty_pv"] - Decimal(expected["c_frn_cum_payment_dirty_pv_eur"])) <= amount_tolerance
    assert abs(cum["irs"]["net_pv"] - Decimal(expected["c_irs_cum_payment_net_pv_eur"])) <= amount_tolerance
    discount_factor = _factor(snapshots["A"]["ois_pillars"], _date(first["payment_date"]))
    assert abs(discount_factor - Decimal(expected["a_first_payment_ois_factor"])) <= Decimal(reference["tolerances"]["curve_factor"])


def test_fixing_boundaries_missing_data_and_late_correction(reference):
    variants = reference["variants"]
    fixings = reference["fixings"]
    first = reference["floating_periods"][0]
    snapshots = reference["snapshots"]
    preloaded = variants["future_fixing_preloaded"]
    a = snapshots[preloaded["base_snapshot"]]
    before_fixing = _instant(a["cutoff_local"])
    assert any(item["fixing_id"] == preloaded["preloaded_fixing_id"] for item in fixings)
    assert preloaded["expected_state"] == "projected"
    assert _price(reference, a, before_fixing, fixings) == _price(reference, a, before_fixing, [])
    boundary = variants["first_fixing_boundary"]
    before, at = (_instant(boundary[name]) for name in ("before_cutoff", "at_cutoff"))
    assert _fixing_for_period(reference, first, before, fixings) is None
    assert _fixing_for_period(reference, first, at, fixings) == fixings[0]

    for missing in variants["missing_fixing"]:
        snapshot = snapshots[missing["base_snapshot"]]
        remaining = [item for item in fixings if item["fixing_id"] != missing["excluded_fixing_id"]]
        with pytest.raises(ValueError, match=missing["expected_state"]):
            _price(reference, snapshot, _instant(snapshot["cutoff_local"]), remaining)

    indicative = variants["indicative_fixing"]
    indicative_fixings = [
        dict(item, status=indicative["status"], validated_at=indicative["validated_at"])
        if item["fixing_id"] == indicative["fixing_id"] else item
        for item in fixings
    ]
    b = snapshots[indicative["base_snapshot"]]
    quote_cutoff = _instant(b["cutoff_local"])
    with pytest.raises(ValueError, match=indicative["expected_state"]):
        _price(reference, b, quote_cutoff, indicative_fixings)
    late_validation = dict(fixings[0], validated_at="2026-09-17T11:00:01+02:00")
    with pytest.raises(ValueError, match="fixing_unavailable"):
        _fixing_for_period(reference, first, at, [late_validation])

    correction = variants["late_first_fixing_correction"]
    corrected = correction["fixing"]
    assert corrected["supersedes"] == fixings[0]["fixing_id"]
    assert _price(reference, b, quote_cutoff, fixings + [corrected]) == _price(reference, b, quote_cutoff)
    assert _fixing_for_period(reference, first, _instant(correction["at_cutoff"]), fixings + [corrected]) == corrected
    assert Decimal(corrected["rate"]) == Decimal("0.0311")


def test_negative_and_zero_projection_rates(reference):
    variant = reference["variants"]["negative_projection_rate"]
    a = reference["snapshots"][variant["base_snapshot"]]
    first = reference["floating_periods"][0]
    rate = Decimal(variant["continuous_zero_rate"])
    terminal_factor = (-rate * a["anchor_to_terminal_days"] / 365).exp()
    pillars = [[a["market_date"], "1"], [reference["terms"]["maturity_date"], str(terminal_factor)]]
    assert terminal_factor > 1
    forward = _forward(pillars, first, Decimal("0"))
    assert abs(forward - Decimal(variant["first_forward_rate"])) < Decimal("1e-12")
    amount = -forward * Decimal(first["act360_days"]) * Decimal(reference["terms"]["notional_eur"]) / 360
    assert amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(variant["first_irs_floating_eur"])
    pillars[-1][1] = "1"
    assert _forward(pillars, first, Decimal("0")) == 0
