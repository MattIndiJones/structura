"""Inputs of the synthetic EUR FRN/IRS pilot, with no reference price data."""

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from .models import FRNTerms, IRSTerms, Product
from .rates_market import CurvePillar, EuriborFixing, PaymentConfirmation, RatesCurve, RatesMarket, RatesSource


RatesCase = Literal["A", "B", "C"]
_PARIS = ZoneInfo("Europe/Paris")
_TERMINAL = date(2028, 9, 21)
_VALUES = {
    "A": (date(2026, 9, 16), 12, 0.9604736150914566, 0.9508385886131090),
    "B": (date(2026, 11, 2), 12, 0.9629503514328859, 0.9539044394695700),
    "C": (date(2026, 12, 21), 16, 0.9655392811652148, 0.9571112779029973),
}


def _source(reference: str) -> RatesSource:
    return RatesSource(kind="synthetic", provider="structura-fixture", reference=reference)


def _fixing(day: date, rate: float) -> EuriborFixing:
    fixing_id = f"euribor-3m-{day.isoformat()}-v1"
    timestamp = datetime.combine(day, time(11), _PARIS)
    return EuriborFixing(fixing_id=fixing_id, version=1, observation_date=day, currency="EUR",
                         index="EURIBOR", tenor="3M", rate=rate, status="validated", source=_source(fixing_id),
                         available_at=timestamp, validated_at=timestamp)


_FIXINGS = (_fixing(date(2026, 9, 17), .031), _fixing(date(2026, 12, 17), .028))
_C_REFERENCE_PAYMENTS = {"FRN": 10_363.89, "IRS": -7_836.11}


def pilot_cases() -> tuple[dict, ...]:
    return tuple({"id": key, "valuation_date": day, "value_date": day,
                  "cutoff": datetime.combine(day, time(hour), _PARIS)}
                 for key, (day, hour, _, _) in _VALUES.items())


def pilot_terms() -> tuple[FRNTerms, IRSTerms]:
    base = {"schema_version": 2, "payoff_mode": "native", "template_version": 1, "currency": "EUR",
            "effective_date": date(2026, 9, 21), "maturity_date": _TERMINAL}
    cadence = {"calendar": "TARGET", "business_day_convention": "modified_following",
               "payment_lag_business_days": 0}
    floating = {**cadence, "frequency_months": 3, "day_count": "ACT/360", "index": "EURIBOR_3M",
                "fixing_calendar": "TARGET", "fixing_lag_business_days": 2}
    return (
        FRNTerms.model_validate({**base, "instrument_type": "FRN", "template_id": "frn-eur-pilot",
                                 "floating_leg": {**floating, "margin_bps": 100.0}, "redemption_fraction": 1.0}),
        IRSTerms.model_validate({**base, "instrument_type": "IRS", "template_id": "irs-eur-pilot",
                                 "floating_leg": {**floating, "margin_bps": 0.0},
                                 "fixed_leg": {**cadence, "frequency_months": 12, "day_count": "30E/360",
                                               "coupon_rate": .0253021092847019}}),
    )


def pilot_market(case: RatesCase) -> tuple[RatesMarket, datetime]:
    day, hour, ois, euribor = _VALUES[case]
    timestamp = datetime.combine(day, time(9), _PARIS)
    market_id = f"eur-frn-irs-abc-{case}-v1"

    def curve(key, role, index, tenor, factor):
        return RatesCurve(curve_id=f"{market_id}-{key}", version=1, role=role, currency="EUR", index=index, tenor=tenor,
                          anchor_date=day, pillars=(CurvePillar(date=day, factor=1.0), CurvePillar(date=_TERMINAL, factor=factor)),
                          source=_source(f"{key}_pillars"), available_at=timestamp, validated_at=timestamp)

    market = RatesMarket(market_id=market_id, market_version=1, market_date=day, frn_funding_bps=0.0,
                         discount=curve("ois", "discount", "ESTR", None, ois),
                         projection=curve("euribor", "projection", "EURIBOR", "3M", euribor), fixings=_FIXINGS)
    return market, datetime.combine(day, time(hour), _PARIS)


def pilot_payment(product: Product, *, equivalent_payoff: bool) -> PaymentConfirmation | None:
    """Scope the noon C confirmation to the benchmark contract and nominal."""
    terms = product.terms
    if (product.intent.nominal != 1_000_000 or product.native_schedule is None
            or (terms.payoff_mode == "scripted" and not equivalent_payoff)):
        return None
    benchmark = next(item for item in pilot_terms() if item.instrument_type == terms.instrument_type)
    ignored = {"rates_script", "payoff_mode"}
    if terms.model_dump(exclude=ignored) != benchmark.model_dump(exclude=ignored):
        return None
    floating = next(leg for leg in product.native_schedule.legs if leg.kind == "floating_coupon")
    first = floating.periods[0]
    fact_id = "first-floating-payment-v1"
    amount_eur = _C_REFERENCE_PAYMENTS[terms.instrument_type] * (1 if product.intent.side == "BUY" else -1)
    timestamp = datetime.combine(first.payment_date, time(12), _PARIS)
    return PaymentConfirmation(fact_id=fact_id, version=1, schedule_fingerprint=product.native_schedule.fingerprint,
                               flow_id=first.flow_id, effect_date=first.payment_date, amount_eur=amount_eur, status="validated",
                               source=_source(fact_id), available_at=timestamp, validated_at=timestamp)
