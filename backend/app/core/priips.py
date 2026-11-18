"""PRIIPs KID rules for Category 3 products, as written in the regulation.

Source: Commission Delegated Regulation (EU) 2017/653, consolidated on
01/01/2023 (amendments of Delegated Regulation (EU) 2021/2268 included), read
on EUR-Lex on 18/11/2026. Point numbers below refer to that text. This module
holds the regulatory arithmetic only — tables, thresholds, formulas — so each
rule can be checked against the text without running a simulation.
"""
from __future__ import annotations

import math

import numpy as np

# Annex II, Part 1, point 2 — VEV upper bounds of MRM classes 1 to 6.
VEV_THRESHOLDS = (0.005, 0.05, 0.12, 0.20, 0.30, 0.80)

# Annex II, Part 1, point 16 — VaR confidence level for Category 3.
VAR_CONFIDENCE = 0.975

# Annex II, Part 1, point 19 — minimum number of simulations.
MIN_SIMULATIONS = 10_000

# Annex II, Part 3, point 52 — SRI by CRM class (rows) and MRM class (columns).
# The table in the regulation reads CRM down the side and MRM across the top;
# the former implementation had it transposed and shifted, which put a common
# autocall (MRM 5, CRM 3) at SRI 4 instead of 5.
SRI_TABLE = {
    1: (1, 2, 3, 4, 5, 6, 7),
    2: (1, 2, 3, 4, 5, 6, 7),
    3: (3, 3, 3, 4, 5, 6, 7),
    4: (5, 5, 5, 5, 5, 6, 7),
    5: (5, 5, 5, 5, 5, 6, 7),
    6: (6, 6, 6, 6, 6, 6, 7),
}


# Annex II, Part 2, point 39: credit assessments map to credit quality steps
# (CQS) through Implementing Regulation (EU) 2016/1800 — on the long-term
# scale, AAA is step 0 and CCC or below step 6.
RATING_TO_CQS = {"AAA": 0, "AA": 1, "A": 2, "BBB": 3, "BB": 4, "B": 5, "CCC": 6}

# Point 43: default step for an obligor without external credit assessment.
UNRATED_REGULATED_CQS = 3       # credit institution or insurer, as qualified by point 43(a)
UNRATED_OTHER_CQS = 5

# Point 42: step adjusted to the maturity — up to 1 year, 1 to 12 years, beyond.
CQS_MATURITY_ADJUSTMENT = {
    0: (0, 0, 0), 1: (0, 1, 1), 2: (1, 2, 2), 3: (2, 3, 3),
    4: (3, 4, 5), 5: (4, 5, 6), 6: (6, 6, 6),
}

# Point 45: adjusted step to credit risk measure.
CQS_TO_CRM = {0: 1, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}


def crm_from_credit(rating: str | None, maturity_years: float, *,
                    unrated_regulated: bool = False) -> dict:
    """Annex II, Part 2, points 39 to 45: credit quality step of the obligor,
    adjusted to the PRIIP's maturity, mapped to a CRM class."""
    if rating:
        key = rating.strip().upper()
        if key not in RATING_TO_CQS:
            raise ValueError(f"Note inconnue : {rating!r} (AAA, AA, A, BBB, BB, B ou CCC).")
        cqs, basis = RATING_TO_CQS[key], f"note {key}"
    else:
        cqs = UNRATED_REGULATED_CQS if unrated_regulated else UNRATED_OTHER_CQS
        basis = ("sans note, établissement régulé (point 43 a)" if unrated_regulated
                 else "sans note (point 43 b)")
    column = 0 if maturity_years <= 1.0 + 1e-9 else (1 if maturity_years <= 12.0 + 1e-9 else 2)
    adjusted = CQS_MATURITY_ADJUSTMENT[cqs][column]
    return {"crm": CQS_TO_CRM[adjusted], "credit_quality_step": cqs,
            "adjusted_credit_quality_step": adjusted, "basis": basis}


def mrm_from_vev(vev: float | None) -> int:
    """Annex II, Part 1, point 2. No finite VEV (total loss at the VaR) is class 7."""
    if vev is None:
        return 7
    for index, threshold in enumerate(VEV_THRESHOLDS):
        if vev < threshold:
            return index + 1
    return 7


def sri(mrm: int, crm: int) -> int:
    """Annex II, Part 3, point 52."""
    if not 1 <= mrm <= 7 or not 1 <= crm <= 6:
        raise ValueError(f"Classes hors échelle : MRM {mrm}, CRM {crm}.")
    return SRI_TABLE[crm][mrm - 1]


def vev_from_var(var_price_space: float, years: float) -> float | None:
    """Annex II, Part 1, point 17: VEV = (sqrt(3.842 - 2 ln VaR) - 1.96) / sqrt(T).

    VaR is the 97.5 % value of the PRIIP as a fraction of the amount invested,
    discounted at the risk-free rate. A non-positive VaR (total loss) has no
    finite VEV; the caller then assigns MRM 7."""
    if years <= 0:
        raise ValueError("La durée de la VEV doit être strictement positive.")
    if var_price_space <= 0:
        return None
    radicand = 3.842 - 2.0 * math.log(var_price_space)
    if radicand <= 0:          # VaR above e^1.921 ~ 6.8x the investment
        return 0.0
    return max(0.0, (math.sqrt(radicand) - 1.96) / math.sqrt(years))


def var_975(present_values, lives, rhp: float) -> tuple[float, float]:
    """Annex II, Part 1, points 16-17.

    `present_values` — one value per simulation, per unit invested, discounted
    to today at the risk-free rate; `lives` — each simulation's life in years
    (its call date when it is called before the RHP). Returns the VaR at
    97.5 % confidence (the 2.5th percentile outcome) and the period T to use in
    the VEV: the life of that very outcome, so a product called before the RHP
    is measured over the time it actually ran."""
    values = np.asarray(present_values, dtype=float)
    if values.size == 0:
        raise ValueError("Distribution vide : aucune VaR calculable.")
    order = np.argsort(values, kind="stable")
    # round(): (1 - 0.975) * 1000 is 25.000000000000021 in binary floating
    # point, and the ceiling would pick the 26th outcome instead of the 25th.
    rank = max(0, math.ceil(round((1.0 - VAR_CONFIDENCE) * values.size, 9)) - 1)
    index = int(order[rank])
    life = float(lives[index]) if lives is not None else rhp
    return float(values[index]), min(rhp, life) if life > 0 else rhp


def intermediate_periods(rhp: float) -> list[float]:
    """Annex IV, points 32 to 34: the holding periods shown before the RHP.

    RHP of one year or less: none. From one to ten years: one year. Ten years
    or more: one year, and half the RHP rounded up to the end of a year."""
    if rhp <= 1.0 + 1e-9:
        return []
    if rhp < 10.0 - 1e-9:
        return [1.0]
    half = float(math.ceil(rhp / 2.0 - 1e-9))
    return sorted({1.0, half} - {rhp})


def scenario_return(value: float, investment: float, years: float) -> float:
    """Annex IV, points 44 and 45: the return shown for a scenario.

    (value / investment) ^ (1 / T) - 1 when the holding period T exceeds one
    year; over one year or less the return is not annualised. `value` is the
    sum of what the investor receives, coupons included, net of costs and
    without reinvestment (point 42); T is that scenario's own holding period —
    its call date when it is called (Annex V point 17)."""
    if investment <= 0 or years <= 0:
        raise ValueError("Investissement et durée doivent être strictement positifs.")
    ratio = value / investment
    if ratio <= 0:
        return -1.0
    return ratio ** (1.0 / years) - 1.0 if years > 1.0 + 1e-9 else ratio - 1.0


def costs_over_time(gross_value: float, net_value: float, investment: float, years: float) -> dict:
    """Annex VI points 70-71 and Annex VII table 1, on the moderate scenario.

    Total costs are what the costs take from the moderate outcome; the annual
    cost impact (reduction in yield) is the return without costs minus the
    return with costs, both by the formula of Annex IV point 44. Rounded per
    Annex VI point 78: euros to the unit, percentages to one decimal."""
    gross_return = scenario_return(gross_value, investment, years)
    net_return = scenario_return(net_value, investment, years)
    return {"total_costs": round(gross_value - net_value),
            "annual_cost_impact_pct": round((gross_return - net_return) * 100.0, 1),
            "return_before_costs_pct": round(gross_return * 100.0, 1),
            "return_after_costs_pct": round(net_return * 100.0, 1),
            "annualised": years > 1.0 + 1e-9}


def cost_composition(entry_pct: float, exit_pct: float, ongoing_pct: float,
                     investment: float) -> dict:
    """Annex VII table 2, simplified: one-off entry and exit costs on the
    amount invested, ongoing costs per year on that amount. Transaction and
    incidental costs are not modelled separately."""
    return {"entry": {"pct": round(entry_pct, 1), "amount": round(investment * entry_pct / 100)},
            "exit": {"pct": round(exit_pct, 1), "amount": round(investment * exit_pct / 100)},
            "ongoing_per_year": {"pct": round(ongoing_pct, 1),
                                 "amount": round(investment * ongoing_pct / 100)},
            "transaction_and_incidental": None,
            "method": "simplified"}


def round_amount(amount: float) -> float:
    """Annex IV, point 42: scenario figures rounded to the nearest 10 EUR."""
    return float(round(amount / 10.0) * 10.0)
