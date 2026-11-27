"""Common credit result projection and time-grid valuation for synthetic cases."""
from __future__ import annotations

from datetime import date, datetime, timezone
from math import exp
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..calendars import BusinessDayConvention, adjust
from ..valuation_context import json_transport_fingerprint
from .credit_pilot import CALIBRATION_RECOVERY, SYNTHETIC_OIS, CreditCase, CreditMode, benchmark_quotes, case_mode
from .credit_pricing import CreditCoupon, CreditPricingError, SurvivalPillar, calibrate_survival, value_cds, value_cln
from .models import CDSTerms, FrozenModel, FrozenObject, Product


CreditState = Literal["alive", "recovery_pending", "settlement_pending", "settled"]
CreditUnit = Literal["EUR", "bp", "fraction", "per_100_notional", "days", "years", "factor"]
_PARIS = ZoneInfo("Europe/Paris")


class CreditMetric(FrozenModel):
    key: str
    label: str
    value: float | None
    unit: CreditUnit


class CreditMeasure(FrozenModel):
    kind: Literal["cds_clean_price", "cln_clean_price", "credit_pv"]
    unit: Literal["EUR", "per_100_notional"]
    value: float | None


class CreditFlow(FrozenModel):
    flow_id: str
    label: str
    state: str
    payment_date: date | None = None
    time_years: float | None = None
    amount_eur: float | None = None
    pv_eur: float | None = None


class CreditResult(FrozenModel):
    instrument_type: Literal["CDS", "CLN"]
    scenario_id: CreditCase
    mode: CreditMode
    state: CreditState
    market_quality: Literal["published_historical_benchmark", "synthetic"]
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float = Field(gt=0)
    side: Literal["BUY", "SELL"]
    valuation_date: date
    cutoff: AwareDatetime
    measure: CreditMeasure
    metrics: tuple[CreditMetric, ...]
    sensitivities: tuple[CreditMetric, ...] = ()
    flows: tuple[CreditFlow, ...] = ()
    calibration: tuple[SurvivalPillar, ...] = ()
    events: tuple[FrozenObject, ...] = ()


class CreditContext(FrozenModel):
    version: Literal[1] = 1
    valuation_date: date
    cutoff: AwareDatetime
    product_id: int | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    nominal: float = Field(gt=0)
    side: Literal["BUY", "SELL"]
    market: FrozenObject
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("cutoff")
    @classmethod
    def normalize_cutoff(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def verify_seal(self):
        if (self.product_id is None) != (self.terms_version is None) or (
            self.fingerprint != json_transport_fingerprint(self.model_dump(mode="json", exclude={"fingerprint"}))
        ):
            raise ValueError("La preuve du contexte de crédit est incohérente.")
        return self

    @classmethod
    def seal(cls, product: Product, *, valuation_date: date, cutoff: datetime, market: dict) -> CreditContext:
        payload = {"version": 1, "valuation_date": valuation_date.isoformat(),
                   "cutoff": cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                   "product_id": product.product_id, "terms_version": product.terms_version if product.product_id else None,
                   "terms_fingerprint": product.terms_fingerprint, "schedule_fingerprint": product.native_schedule.fingerprint,
                   "nominal": product.intent.nominal, "side": product.intent.side, "market": market}
        return cls.model_validate({**payload, "fingerprint": json_transport_fingerprint(payload)})


def metric(key: str, label: str, value: float | None, unit: CreditUnit = "EUR") -> CreditMetric:
    return CreditMetric(key=key, label=label, value=value, unit=unit)


def result_for(product: Product, case: CreditCase, cutoff: datetime, *, state: CreditState = "alive",
               measure: CreditMeasure, metrics: tuple[CreditMetric, ...], **parts) -> CreditResult:
    mode = case_mode(case)
    return CreditResult(instrument_type=product.terms.instrument_type, scenario_id=case, mode=mode, state=state,
                        market_quality="published_historical_benchmark" if mode == "isda_converter" else "synthetic",
                        nominal_eur=product.intent.nominal, side=product.intent.side, valuation_date=cutoff.astimezone(_PARIS).date(),
                        cutoff=cutoff, measure=measure, metrics=metrics, **parts)


def analytic_value(product: Product, case: CreditCase, cutoff: datetime, *, recovery: float,
                   funding_bps: float) -> tuple[CreditResult, dict]:
    terms = product.terms
    nominal, side = product.intent.nominal, 1 if product.intent.side == "BUY" else -1
    is_cds = isinstance(terms, CDSTerms)
    initial = case == "INITIAL-DATED"
    dated = initial or case == "JULY-BEFORE"
    quotes = benchmark_quotes(case)
    protected_from = 0.0
    if initial:
        anchor = cutoff.astimezone(_PARIS).date()
        quotes = tuple(quote.model_copy(update={"maturity_years":
            (adjust(anchor + relativedelta(years=int(quote.maturity_years)), "TARGET",
                    BusinessDayConvention.FOLLOWING) - anchor).days / 365}) for quote in quotes)
    calibration = calibrate_survival(quotes, discount=SYNTHETIC_OIS, recovery=CALIBRATION_RECOVERY)
    maturity, coupons, periods, accrued, principal_payment, principal_date = 5.0, None, (), 0.0, None, None
    if dated:
        valuation_date = cutoff.date()

        def year(day):
            return (day - valuation_date).days / 365

        coupon_leg = next(leg for leg in product.native_schedule.legs if leg.kind == ("premium" if is_cds else "fixed_coupon"))
        periods = tuple(period for period in coupon_leg.periods if period.credit_observation_date >= valuation_date
                        and period.payment_date >= valuation_date)
        if not periods:
            raise CreditPricingError("CREDIT_DATES_INVALID", "L’échéancier ne porte aucun coupon futur à l’arrêté.")
        maturity = year(periods[-1].credit_observation_date) + (1 / 365 if is_cds else 0)
        coupons = tuple(CreditCoupon(start=year(period.accrual_start),
                                     end=year(period.accrual_end), payment=year(period.payment_date),
                                     observation=year(period.credit_observation_date),
                                     year_fraction=period.year_fraction) for period in periods)
        first = periods[0]
        accrued = max(0, (valuation_date - first.accrual_start).days) / 360
        if initial and is_cds:
            settlement = next(leg.events[0] for leg in product.native_schedule.legs if leg.kind == "initial_settlement")
            accrued = settlement.accrued_days / 360
            protected_from = year(terms.effective_date)
        if not is_cds:
            principal_date = next(leg.events[0].date for leg in product.native_schedule.legs if leg.kind == "principal")
            principal_payment = year(principal_date)

    if is_cds:
        def calculate(curve):
            return value_cds(curve, SYNTHETIC_OIS, maturity, nominal=nominal, coupon_bps=terms.premium_leg.coupon_bps,
                             recovery=recovery, coupons=coupons, protected_from=protected_from,
                             initial_accrued_fraction=accrued)

        base = calculate(calibration.curve)
        measure = CreditMeasure(kind="credit_pv", unit="EUR", value=side * base.dirty_pv_eur)
        metrics = (metric("protection", "Protection", side * base.protection_pv_eur),
                   metric("scheduled_premiums", "Primes programmées", -side * base.scheduled_premium_pv_eur),
                   metric("accrual_on_default", "Prime attendue au défaut", -side * base.accrual_on_default_pv_eur),
                   metric("dirty_pv", "PV dirty", side * base.dirty_pv_eur),
                   metric("clean_pv", "PV clean", side * base.clean_pv_eur),
                   metric("par_spread", "Spread au pair", base.par_spread_bps, "bp"))
        additional_flows = (
            CreditFlow(flow_id="cds-protection-expected", label="Protection attendue", state="expected", pv_eur=side * base.protection_pv_eur),
            CreditFlow(flow_id="cds-aod-expected", label="Prime attendue au défaut", state="expected", pv_eur=-side * base.accrual_on_default_pv_eur),
        )
        gain_on_default = nominal * ((1 - recovery) - terms.premium_leg.coupon_bps * accrued / 10_000)
        funding_sensitivity = ()
    else:
        delay = terms.default_settlement_lag_calendar_days / 365

        def calculate(curve, funding=funding_bps):
            return value_cln(curve, SYNTHETIC_OIS, maturity, nominal=nominal, coupon_rate=terms.fixed_leg.coupon_rate,
                             recovery=recovery, coupons=coupons, principal_payment=principal_payment,
                             settlement_delay=delay, funding_bps=funding, accrued_fraction=accrued)

        base = calculate(calibration.curve)
        measure = CreditMeasure(kind="cln_clean_price", unit="per_100_notional", value=100 * side * base.clean_pv_eur / nominal)
        metrics = (metric("coupon_pv", "Coupons sur survie", side * base.coupon_pv_eur),
                   metric("survival_principal", "Principal sur survie", side * base.survival_principal_pv_eur),
                   metric("default_redemption", "Remboursement attendu au défaut", side * base.default_redemption_pv_eur),
                   metric("dirty_pv", "PV dirty", side * base.dirty_pv_eur), metric("accrued", "Couru", side * base.accrued_eur),
                   metric("clean_pv", "PV clean", side * base.clean_pv_eur),
                   metric("par_coupon", "Coupon au pair", base.par_coupon_fraction, "fraction"))
        additional_flows = (
            CreditFlow(flow_id=(next(leg.events[0].flow_id for leg in product.native_schedule.legs if leg.kind == "principal")
                                if initial else "cln-survival-principal"), label="Principal sur survie", state="expected",
                       payment_date=principal_date, time_years=None if dated else maturity,
                       amount_eur=side * nominal, pv_eur=side * base.survival_principal_pv_eur),
            CreditFlow(flow_id="cln-default-redemption-expected", label="Remboursement attendu au défaut", state="expected",
                       pv_eur=side * base.default_redemption_pv_eur),
        )
        gain_on_default = nominal * recovery * exp(-(SYNTHETIC_OIS + funding_bps / 10_000) * delay)
        funding_sensitivity = (metric("funding100", "Hausse du funding de 100 pb",
                                      side * (calculate(calibration.curve, funding_bps + 100).dirty_pv_eur - base.dirty_pv_eur)),)

    upfront = case == "SURVIVAL-UPFRONT"
    bump = .0001 if upfront else 1.0
    bumped_quotes = tuple(q.model_copy(update={"value": q.value + bump}) for q in quotes)
    bumped = calibrate_survival(bumped_quotes, discount=SYNTHETIC_OIS, recovery=CALIBRATION_RECOVERY)
    sensitivity = side * (calculate(bumped.curve).dirty_pv_eur - base.dirty_pv_eur)
    sensitivities = (metric("upfront01" if upfront else "cs01", "Upfronts clean +1 pb" if upfront else "CS01 parallèle +1 pb", sensitivity),
                     metric("jump_to_default", "Défaut immédiat · variation de PV", side * (gain_on_default - base.dirty_pv_eur)),
                     *funding_sensitivity)
    signed_coupon_rate = (-terms.premium_leg.coupon_bps / 10_000 if is_cds else terms.fixed_leg.coupon_rate) * side
    coupon_flows = tuple(CreditFlow(flow_id=periods[i].flow_id if dated else f"{terms.instrument_type.lower()}-analytical-coupon-{i + 1}",
                                     label="Prime programmée" if is_cds else "Coupon sur survie", state="expected",
                                     payment_date=periods[i].payment_date if dated else None,
                                     time_years=None if dated else (i + 1) / 4,
                                     amount_eur=nominal * signed_coupon_rate * (periods[i].year_fraction if dated else .25),
                                     pv_eur=side * (-pv if is_cds else pv))
                         for i, pv in enumerate(base.coupon_pvs_eur))
    result = result_for(product, case, cutoff, measure=measure, metrics=metrics,
                        flows=(*coupon_flows, *additional_flows), calibration=calibration.pillars, sensitivities=sensitivities)
    market = {"provenance": {"kind": "synthetic", "reference": ("eur-credit-survival-1y3y5y-target-following-v1"
                                                               if initial else "eur-credit-survival-1y3y5y-v1")},
              "reference_entity_id": terms.reference_entity_id, "ois_rate": SYNTHETIC_OIS, "funding_bps": funding_bps,
              "calibration_recovery_fraction": CALIBRATION_RECOVERY, "pricing_recovery_fraction": recovery,
              "source_quotes": [quote.model_dump(mode="json") for quote in quotes],
              "survival_curve": calibration.curve.model_dump(mode="json"),
              "time_model": "actual_days_365" if dated else "exact_quarters",
              "jump_to_default": {"valuation_date": cutoff.date().isoformat(), "recovery_fraction": recovery,
                                   "delay_days": 0 if is_cds else terms.default_settlement_lag_calendar_days,
                                   "accrued_fraction": accrued if is_cds else 0.0}}
    return result, market
