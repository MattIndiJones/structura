"""Frozen inputs for the published ISDA and synthetic lot 3 recipes."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import cache
from pathlib import Path
from typing import Literal

from .credit_facts import SyntheticDefaultFact, SyntheticRecoveryFact, SyntheticSettlementFact
from .credit_pricing import CreditPricingError, CreditQuote
from .isda_market import IsdaMarketSelection
from .models import CDSTerms, CLNTerms, Product
from .rates_market import PaymentConfirmation, RatesSource


CreditCase = Literal[
    "INITIAL-DATED", "ISDA-50", "ISDA-100", "ISDA-150", "SURVIVAL-PAR", "SURVIVAL-UPFRONT",
    "JULY-BEFORE", "JULY-PENDING", "JULY-DUE", "JULY-PAID", "JULY-ZERO",
]
CreditMode = Literal["isda_converter", "piecewise_survival", "default_case"]
REFERENCE_ENTITY = "synthetic-reference"
SYNTHETIC_OIS = .02
CALIBRATION_RECOVERY = .40
_PAR = (60.150187499589, 99.511580327049, 151.993987948377)
_UPFRONT = (-.00391599759070, -.00013887327427, .02354002074515)
_ISDA_CUTOFF = "2021-04-26T12:00:00+02:00"
_SURVIVAL_CUTOFF = "2026-09-21T12:00:00+02:00"
_CASE_CUTOFF = {
    "INITIAL-DATED": _SURVIVAL_CUTOFF,
    "ISDA-50": _ISDA_CUTOFF, "ISDA-100": _ISDA_CUTOFF, "ISDA-150": _ISDA_CUTOFF,
    "SURVIVAL-PAR": _SURVIVAL_CUTOFF, "SURVIVAL-UPFRONT": _SURVIVAL_CUTOFF,
    "JULY-BEFORE": "2021-07-15T09:59:59+02:00", "JULY-PENDING": "2021-07-15T10:00:00+02:00",
    "JULY-DUE": "2021-07-19T13:00:00+02:00", "JULY-PAID": "2021-07-20T15:00:00+02:00",
    "JULY-ZERO": "2021-07-20T15:00:00+02:00",
}
_CASE_LABELS = {
    "INITIAL-DATED": "Arrêté initial · échéancier contractuel",
    "ISDA-50": "ISDA · 50 pb", "ISDA-100": "ISDA · 100 pb", "ISDA-150": "ISDA · 150 pb",
    "SURVIVAL-PAR": "Survie 1, 3 et 5 ans · spreads au pair",
    "SURVIVAL-UPFRONT": "Survie 1, 3 et 5 ans · upfronts clean",
    "JULY-BEFORE": "Juillet 2021 · avant validation du défaut",
    "JULY-PENDING": "Juillet 2021 · recouvrement en attente",
    "JULY-DUE": "Juillet 2021 · règlement dû",
    "JULY-PAID": "Juillet 2021 · règlement confirmé",
    "JULY-ZERO": "Juillet 2021 · recouvrement final de 0 %",
}


def case_cutoff(case: CreditCase) -> datetime:
    return datetime.fromisoformat(_CASE_CUTOFF[case])


def case_mode(case: CreditCase) -> CreditMode:
    if case.startswith("ISDA"):
        return "isda_converter"
    return "piecewise_survival" if case == "INITIAL-DATED" or case.startswith("SURVIVAL") else "default_case"


@cache
def _isda_inputs() -> dict:
    path = Path(__file__).with_name("data") / "isda_eur_20210426.json"
    return json.loads(path.read_text(encoding="utf-8"))


def isda_selection(case: CreditCase) -> IsdaMarketSelection:
    args = _isda_inputs()
    spread = int(case.rsplit("-", 1)[-1])
    scenario = next(row for row in args["scenarios"] if row["market_inputs"]["quoted_spread_bp"] == spread)
    return IsdaMarketSelection.model_validate({**{key: value for key, value in args.items() if key != "scenarios"},
                                               "policy": "historical_isda_benchmark", "scenario": scenario})


def benchmark_quotes(case: CreditCase) -> tuple[CreditQuote, ...]:
    upfront = case == "SURVIVAL-UPFRONT"
    return tuple(CreditQuote(maturity_years=tenor, kind="clean_upfront" if upfront else "par_spread", value=value)
                 for tenor, value in zip((1, 3, 5), _UPFRONT if upfront else _PAR))


def benchmark_terms(instrument: Literal["CDS", "CLN"], case: CreditCase) -> CDSTerms | CLNTerms:
    mode = case_mode(case)
    base = {"schema_version": 2, "instrument_type": instrument, "payoff_mode": "native",
            "template_id": f"{instrument.lower()}-eur-pilot", "template_version": 1, "currency": "EUR",
            "reference_entity_id": REFERENCE_ENTITY, "seniority": "senior",
            "documentation": "synthetic-cds-documentation", "restructuring": "synthetic-clause"}
    leg = {"calendar": "weekdays_only", "business_day_convention": "following", "frequency_months": 3,
           "payment_lag_business_days": 0, "day_count": "ACT/360"}
    if instrument == "CDS":
        trade = date(2026, 9, 21) if mode == "piecewise_survival" else date(2021, 4, 26)
        return CDSTerms.model_validate({**base, "trade_date": trade, "effective_date": trade + timedelta(days=1),
                                        "maturity_date": date(2031, 9, 20) if mode == "piecewise_survival" else date(2026, 6, 20),
                                        "premium_leg": {**leg, "coupon_bps": 100.0}, "step_in_lag_calendar_days": 1,
                                        "cash_settlement_lag_business_days": 3, "accrued_on_default": True})
    analytical = mode == "piecewise_survival"
    return CLNTerms.model_validate({**base, "issuer_reference": "synthetic-issuer", "redemption_fraction": 1.0,
                                    "coupon_entitlement": "survival_through_accrual_end", "coupon_on_default": "none",
                                    "default_redemption": "nominal_times_recovery",
                                    "default_settlement_lag_calendar_days": 30 if analytical else 5,
                                    "effective_date": date(2026, 9, 21) if analytical else date(2021, 3, 22),
                                    "maturity_date": date(2031, 9, 21) if analytical else date(2026, 6, 21),
                                    "fixed_leg": {**leg, "calendar": "TARGET", "business_day_convention": "modified_following",
                                                  "day_count": "30E/360" if analytical else "ACT/360", "coupon_rate": .04}})


def credit_catalogue() -> list[dict]:
    products = []
    for instrument, name in (("CDS", "CDS single-name EUR"), ("CLN", "CLN fixe EUR")):
        products.append({"instrument_type": instrument, "name": name, "cases": [
            {"id": case, "label": _CASE_LABELS[case], "mode": case_mode(case), "cutoff": case_cutoff(case),
             "valuation_date": case_cutoff(case).date(), "terms": benchmark_terms(instrument, case),
             "intent": {"nominal": 10_000_000 if instrument == "CDS" else 1_000_000, "side": "BUY"}}
            for case in _CASE_CUTOFF if instrument == "CDS" or not case.startswith("ISDA")
        ]})
    return products


def verify_synthetic_terms(product: Product, case: CreditCase) -> None:
    terms = product.terms
    if case == "INITIAL-DATED":
        anchor = terms.trade_date if isinstance(terms, CDSTerms) else terms.effective_date
        if anchor != case_cutoff(case).date() or terms.reference_entity_id != REFERENCE_ENTITY:
            raise CreditPricingError("CREDIT_PILOT_TERMS_INCOMPATIBLE", "L’arrêté initial exige la date d’origine et l’entité de référence du marché synthétique.")
        return
    expected = benchmark_terms(terms.instrument_type, case)
    candidate = terms.model_dump(mode="json")
    reference = expected.model_dump(mode="json")
    if case_mode(case) == "piecewise_survival":
        # The actuarial fixture is defined on exact year fractions. Only payoff
        # parameters independent of that time grid may change inside this recipe.
        leg, rate = ("premium_leg", "coupon_bps") if isinstance(terms, CDSTerms) else ("fixed_leg", "coupon_rate")
        candidate[leg].pop(rate)
        reference[leg].pop(rate)
        if isinstance(terms, CLNTerms):
            candidate.pop("default_settlement_lag_calendar_days")
            reference.pop("default_settlement_lag_calendar_days")
            candidate.pop("issuer_reference")
            reference.pop("issuer_reference")
    for payload in (candidate, reference):
        payload.pop("template_id")
        payload.pop("template_version")
    if candidate != reference:
        raise CreditPricingError("CREDIT_PILOT_TERMS_INCOMPATIBLE", "Le scénario exige un contrat compatible avec les dates, conventions et le référentiel de crédit du témoin.")


def july_facts(case: CreditCase):
    zero = case == "JULY-ZERO"
    default_id = "july-zero-recovery-v1" if zero else "july-credit-default-v1"
    at = datetime.fromisoformat
    return default_id, (
        SyntheticDefaultFact(default_id=default_id, fact_id=f"{default_id}-notice", version=1, effect_date=date(2021, 7, 15),
                             available_at=at("2021-07-15T09:00:00+02:00"), validated_at=at("2021-07-15T10:00:00+02:00")),
        SyntheticRecoveryFact(default_id=default_id, fact_id=f"{default_id}-recovery", version=1, effect_date=date(2021, 7, 19),
                              available_at=at("2021-07-19T11:00:00+02:00"), validated_at=at("2021-07-19T12:00:00+02:00"),
                              recovery_fraction=0.0 if zero else .35),
        SyntheticSettlementFact(default_id=default_id, fact_id=f"{default_id}-settled", version=1, effect_date=date(2021, 7, 20),
                                available_at=at("2021-07-20T15:00:00+02:00"), validated_at=at("2021-07-20T14:00:00+02:00"),
                                default_version=1, recovery_version=1),
    )


def july_prior_payment(product: Product) -> PaymentConfirmation:
    terms = product.terms
    day = date(2021, 6, 21)
    timestamp = datetime.fromisoformat("2021-06-21T12:00:00+02:00")
    coupon_leg = "premium" if isinstance(terms, CDSTerms) else "fixed_coupon"
    schedule = product.native_schedule
    coupon = next(p for leg in schedule.legs if leg.kind == coupon_leg for p in leg.periods if p.payment_date == day)
    rate = (-Decimal(str(terms.premium_leg.coupon_bps)) / 10_000 if isinstance(terms, CDSTerms)
            else Decimal(str(terms.fixed_leg.coupon_rate)))
    side = 1 if product.intent.side == "BUY" else -1
    cash = side * Decimal(str(product.intent.nominal)) * rate * coupon.day_count_days / coupon.day_count_denominator
    return PaymentConfirmation(fact_id="july-prior-coupon-20210621-v1", version=1, schedule_fingerprint=schedule.fingerprint,
                               flow_id=coupon.flow_id, effect_date=day,
                               amount_eur=float(cash.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                               status="validated", source=RatesSource(kind="synthetic", provider="structura-fixture", reference="july-2021-v1"),
                               available_at=timestamp, validated_at=timestamp)
