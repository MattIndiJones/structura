"""PRIIPs Category 3 arithmetic, checked against the regulation's own text.

Delegated Regulation (EU) 2017/653, consolidated 01/01/2023 (with 2021/2268),
read on EUR-Lex on 18/11/2026. Each expected value below is copied from the
text or computed by hand from its formula, never from the implementation.
"""
import math

import pytest

from backend.app.core import priips


# Annex II, Part 3, point 52 — rows CR1..CR6, columns MR1..MR7, as printed.
REGULATION_SRI = {
    1: [1, 2, 3, 4, 5, 6, 7],
    2: [1, 2, 3, 4, 5, 6, 7],
    3: [3, 3, 3, 4, 5, 6, 7],
    4: [5, 5, 5, 5, 5, 6, 7],
    5: [5, 5, 5, 5, 5, 6, 7],
    6: [6, 6, 6, 6, 6, 6, 7],
}


@pytest.mark.parametrize("crm", range(1, 7))
@pytest.mark.parametrize("mrm", range(1, 8))
def test_sri_follows_the_aggregation_table_of_point_52(mrm, crm):
    assert priips.sri(mrm, crm) == REGULATION_SRI[crm][mrm - 1]


def test_the_former_table_understated_a_common_autocall():
    """MRM 5 with the default CRM 3 is SRI 5, not 4; MRM 7 is always 7."""
    assert priips.sri(5, 3) == 5
    assert all(priips.sri(7, crm) == 7 for crm in range(1, 7))


@pytest.mark.parametrize("vev,mrm", [
    (0.0, 1), (0.0049, 1), (0.005, 2), (0.0499, 2), (0.05, 3), (0.1199, 3), (0.12, 4),
    (0.1999, 4), (0.20, 5), (0.2999, 5), (0.30, 6), (0.7999, 6), (0.80, 7), (None, 7),
])
def test_mrm_class_bounds_of_point_2(vev, mrm):
    assert priips.mrm_from_vev(vev) == mrm


def test_vev_formula_of_point_17_by_hand():
    # VaR 0.70 over 5 years: (sqrt(3.842 - 2 ln 0.70) - 1.96) / sqrt(5)
    expected = (math.sqrt(3.842 - 2 * math.log(0.70)) - 1.96) / math.sqrt(5)
    assert priips.vev_from_var(0.70, 5.0) == pytest.approx(expected, abs=1e-15)
    # sqrt(3.842 + 0.71335) = 2.13433 ; (2.13433 - 1.96) / 2.23607 = 0.07796
    assert expected == pytest.approx(0.07796, abs=1e-5)


def test_a_var_at_or_above_par_gives_a_near_zero_vev_and_total_loss_none():
    # ln(1) = 0: sqrt(3.842) = 1.9601020 ; 0.0001020 / sqrt(3) = 0.0000589.
    assert priips.vev_from_var(1.0, 3.0) == pytest.approx(0.0000589, abs=1e-7)
    assert priips.mrm_from_vev(priips.vev_from_var(1.0, 3.0)) == 1
    assert priips.vev_from_var(0.0, 3.0) is None


def test_var_is_the_97_5_percent_outcome_and_uses_its_own_life():
    # 1 000 outcomes 0.001 .. 1.000; the 2.5th percentile is the 25th lowest.
    values = [i / 1000 for i in range(1, 1001)]
    lives = [5.0] * 1000
    lives[24] = 1.0           # that outcome was called after one year
    var, years = priips.var_975(values, lives, 5.0)
    assert var == pytest.approx(0.025)
    assert years == 1.0


@pytest.mark.parametrize("rhp,periods", [
    (0.75, []), (1.0, []), (2.0, [1.0]), (5.0, [1.0]), (9.5, [1.0]),
    (10.0, [1.0, 5.0]), (11.0, [1.0, 6.0]), (15.0, [1.0, 8.0]),
])
def test_intermediate_periods_of_annex_iv_points_32_to_34(rhp, periods):
    assert priips.intermediate_periods(rhp) == periods


@pytest.mark.parametrize("amount,rounded", [(10_434.0, 10_430.0), (10_435.1, 10_440.0), (7.0, 10.0)])
def test_scenario_amounts_round_to_the_nearest_ten_euros(amount, rounded):
    assert priips.round_amount(amount) == rounded


@pytest.mark.parametrize("value,years,expected", [
    (11_000.0, 2.0, (1.1 ** 0.5) - 1),     # point 44, annualised over two years
    (11_000.0, 1.0, 0.10),                 # point 45, one year: not annualised
    (10_500.0, 0.5, 0.05),                 # point 45, under one year
    (0.0, 3.0, -1.0),                      # total loss
])
def test_scenario_return_of_annex_iv_points_44_and_45(value, years, expected):
    assert priips.scenario_return(value, 10_000.0, years) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("rating,maturity,crm", [
    ("AAA", 5.0, 1), ("AA", 0.5, 1), ("AA", 5.0, 1), ("A", 0.5, 1), ("A", 5.0, 2),
    ("BBB", 0.5, 2), ("BBB", 5.0, 3), ("BBB", 15.0, 3), ("BB", 5.0, 4), ("BB", 15.0, 5),
    ("B", 0.5, 4), ("B", 15.0, 6), ("CCC", 0.5, 6),
])
def test_crm_from_rating_adjusted_to_maturity_points_42_and_45(rating, maturity, crm):
    """Point 42 table (up to 1 year / 1-12 years / beyond) then point 45."""
    assert priips.crm_from_credit(rating, maturity)["crm"] == crm


def test_unrated_issuer_defaults_of_point_43():
    assert priips.crm_from_credit(None, 5.0, unrated_regulated=True)["crm"] == 3
    assert priips.crm_from_credit(None, 5.0)["crm"] == 5


def test_costs_over_time_is_the_moderate_return_without_minus_with_costs():
    """Annex VI points 70-71: 11 000 gross against 10 600 net over two years."""
    costs = priips.costs_over_time(11_000.0, 10_600.0, 10_000.0, 2.0)
    gross = 1.1 ** 0.5 - 1
    net = 1.06 ** 0.5 - 1
    assert costs["total_costs"] == 400
    assert costs["annual_cost_impact_pct"] == round((gross - net) * 100, 1)


def test_cost_composition_on_ten_thousand_invested():
    composition = priips.cost_composition(2.0, 1.0, 0.5, 10_000.0)
    assert composition["entry"] == {"pct": 2.0, "amount": 200}
    assert composition["exit"] == {"pct": 1.0, "amount": 100}
    assert composition["ongoing_per_year"] == {"pct": 0.5, "amount": 50}
