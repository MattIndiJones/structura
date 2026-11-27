"""Prepare effective market and life-cycle inputs for the native EUR rates pilots."""

from bisect import bisect_left
from datetime import date as Date, datetime, time, timezone
from math import exp, log
from typing import Annotated, Literal, TypeVar
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..valuation_context import canonical_fingerprint
from .models import FRNTerms, FrozenModel, IRSTerms, Product
from .native_schedule_models import NativeSchedule, SchedulePeriod


_POLICY_VERSION = "eur-rates-synthetic-v1"
_POLICY_ZONE = "Europe/Paris"
_FIXING_DUE = time(11)
_FIXING_IDENTITY = ("EUR", "EURIBOR", "3M")

Identifier = Annotated[str, Field(min_length=1)]
Version = Annotated[int, Field(strict=True, gt=0)]
Number = Annotated[float, Field(strict=True)]


class RatesMarketError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RatesSource(FrozenModel):
    kind: Literal["synthetic", "observed", "indicative"]
    provider: Identifier
    reference: Identifier


class _VersionedSource(FrozenModel):
    version: Version
    source: RatesSource
    available_at: AwareDatetime
    validated_at: AwareDatetime | None

    @field_validator("available_at", "validated_at")
    @classmethod
    def utc_timestamp(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None

    def eligible_at(self, cutoff: datetime) -> bool:
        return (
            self.source.kind == "synthetic" and self.validated_at is not None
            and max(self.available_at, self.validated_at) <= cutoff
        )


class CurvePillar(FrozenModel):
    date: Date
    factor: Annotated[float, Field(strict=True, gt=0)]


class RatesCurveOverride(FrozenModel):
    override_id: Identifier
    pillars: tuple[CurvePillar, ...] = Field(min_length=2)
    reason: Identifier
    author: Identifier
    approved_at: AwareDatetime

    @field_validator("approved_at")
    @classmethod
    def utc_approval(cls, value):
        return value.astimezone(timezone.utc)


class SelectedRatesCurve(_VersionedSource):
    curve_id: Identifier
    role: Literal["discount", "projection"]
    currency: Identifier
    index: Identifier
    tenor: Identifier | None = None
    anchor_date: Date
    pillars: tuple[CurvePillar, ...] = Field(min_length=2)
    day_count: Literal["ACT/365F"] = "ACT/365F"
    interpolation: Literal["log_linear_factor"] = "log_linear_factor"
    extrapolation: Literal[False] = False
    override: RatesCurveOverride | None = None

    @model_validator(mode="after")
    def curve_shape(self):
        self._validate_pillars(self.pillars)
        if self.override is not None:
            self._validate_pillars(self.override.pillars)
        return self

    def _validate_pillars(self, pillars: tuple[CurvePillar, ...]) -> None:
        if pillars[0].date != self.anchor_date or pillars[0].factor != 1.0:
            raise ValueError("Le premier pilier de courbe doit être à l’ancrage, avec un facteur de 1.")
        if any(left.date >= right.date for left, right in zip(pillars, pillars[1:])):
            raise ValueError("Les dates des piliers doivent être uniques et strictement croissantes.")

    @property
    def effective_pillars(self) -> tuple[CurvePillar, ...]:
        return self.override.pillars if self.override is not None else self.pillars

    def factor_at(self, day: Date) -> float:
        pillars = self.effective_pillars
        if not self.anchor_date <= day <= pillars[-1].date:
            raise RatesMarketError(
                "RATES_CURVE_COVERAGE", f"La courbe {self.role} « {self.curve_id} » ne couvre pas le {day:%d/%m/%Y}.",
            )
        right = bisect_left(pillars, day, key=lambda pillar: pillar.date)
        if pillars[right].date == day:
            return pillars[right].factor
        before, after = pillars[right - 1], pillars[right]
        weight = (day - before.date).days / (after.date - before.date).days
        log_before = log(before.factor)
        return exp(log_before + weight * (log(after.factor) - log_before))


class RatesCurve(SelectedRatesCurve):
    ingested_at: AwareDatetime | None = None


class _ValidatedObservation(_VersionedSource):
    status: Literal["validated", "indicative"]

    @model_validator(mode="after")
    def requires_validation_timestamp(self):
        if self.status == "validated" and self.validated_at is None:
            raise ValueError("Une donnée validée doit porter son horodatage de validation.")
        return self

    def eligible_at(self, cutoff: datetime) -> bool:
        return self.status == "validated" and super().eligible_at(cutoff)


class SelectedEuriborFixing(_ValidatedObservation):
    fixing_id: Identifier
    observation_date: Date
    currency: Identifier
    index: Identifier
    tenor: Identifier
    rate: Number
    rate_unit: Literal["decimal_fraction"] = "decimal_fraction"
    supersedes: Identifier | None = None


class EuriborFixing(SelectedEuriborFixing):
    ingested_at: AwareDatetime | None = None


class SelectedPaymentConfirmation(_ValidatedObservation):
    fact_id: Identifier
    schedule_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    flow_id: Identifier
    effect_date: Date
    amount_eur: Number


class PaymentConfirmation(SelectedPaymentConfirmation):
    ingested_at: AwareDatetime | None = None


class RatesMarket(FrozenModel):
    kind: Literal["rates"] = "rates"
    market_id: Identifier
    market_version: Version
    market_date: Date
    discount: RatesCurve
    projection: RatesCurve
    fixings: tuple[EuriborFixing, ...] = ()
    payments: tuple[PaymentConfirmation, ...] = ()
    frn_funding_bps: Number


class RatesFlowSelection(FrozenModel):
    flow_id: Identifier
    leg_id: Identifier
    period_id: Identifier | None = None
    payment_date: Date
    state: Literal["future", "due_open", "paid"]
    fixing_state: Literal["projected", "fixed"] | None = None
    fixing_id: Identifier | None = None
    fixing_version: Version | None = None
    payment_fact_id: Identifier | None = None
    payment_version: Version | None = None


class RatesMarketSelection(FrozenModel):
    kind: Literal["rates"] = "rates"
    market_id: Identifier
    market_version: Version
    market_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_version: Literal["eur-rates-synthetic-v1"] = _POLICY_VERSION
    valuation_date: Date
    cutoff_utc: AwareDatetime
    settlement_date: Date
    discount: SelectedRatesCurve
    projection: SelectedRatesCurve
    frn_funding_bps: Number
    fixings: tuple[SelectedEuriborFixing, ...]
    payments: tuple[SelectedPaymentConfirmation, ...]
    flows: tuple[RatesFlowSelection, ...]
    discount_dates: tuple[Date, ...]
    projection_dates: tuple[Date, ...]
    overdue_treatment: Literal["face_at_valuation_date"] | None = Field(default=None, exclude_if=lambda value: value is None)


def _select_curve(curve: RatesCurve, role: Literal["discount", "projection"],
                  valuation_date: Date, cutoff: datetime) -> SelectedRatesCurve:
    index, tenor = ("ESTR", None) if role == "discount" else ("EURIBOR", "3M")
    if (curve.role, curve.currency, curve.index, curve.tenor) != (role, "EUR", index, tenor):
        raise RatesMarketError(
            "RATES_CURVE_INCOMPATIBLE", f"La courbe {role} « {curve.curve_id} » a un rôle, une devise, un indice ou un tenor incompatible.",
        )
    if curve.anchor_date != valuation_date:
        raise RatesMarketError("RATES_CURVE_INCOMPATIBLE", f"La courbe {role} doit être ancrée à l’arrêté.")
    if curve.source.kind != "synthetic":
        raise RatesMarketError("RATES_SOURCE_NOT_ALLOWED", f"La source de la courbe {role} est hors de la politique de recette.")
    if not curve.eligible_at(cutoff):
        raise RatesMarketError("RATES_CURVE_UNAVAILABLE", f"La courbe {role} est indisponible ou non validée à l’arrêté.")

    effective = curve.model_dump(exclude={"ingested_at"})
    if curve.override is not None and curve.override.approved_at > cutoff:
        effective["override"] = None
    return SelectedRatesCurve.model_validate(effective)


_Observation = TypeVar("_Observation", bound=_ValidatedObservation)


def _latest_eligible(candidates: list[_Observation], label: str) -> _Observation | None:
    if not candidates:
        return None
    if len({item.source.provider for item in candidates}) != 1:
        raise RatesMarketError("RATES_SOURCE_AMBIGUOUS", f"Plusieurs sources éligibles pour {label}.")
    latest_version = max(item.version for item in candidates)
    latest = [item for item in candidates if item.version == latest_version]
    selected = latest[0]
    effective = selected.model_dump(exclude={"ingested_at"})
    if any(item.model_dump(exclude={"ingested_at"}) != effective for item in latest[1:]):
        raise RatesMarketError("RATES_SOURCE_AMBIGUOUS", f"Versions concurrentes pour {label}.")
    return selected


def _validate_product(product: Product) -> NativeSchedule:
    terms = product.terms
    if not isinstance(terms, (FRNTerms, IRSTerms)):
        raise RatesMarketError("RATES_TERMS_UNSUPPORTED", "Cette préparation est réservée aux FRN et IRS EUR.")
    if (
        product.intent.nominal is None or terms.floating_leg.margin_bps is None
        or (isinstance(terms, IRSTerms) and terms.fixed_leg.coupon_rate is None)
    ):
        raise RatesMarketError("RATES_TERMS_INCOMPLETE", "Précisez le nominal et les conditions de coupon requises.")
    schedule = product.native_schedule
    if schedule is None:
        raise RatesMarketError("RATES_SCHEDULE_REQUIRED", "L’échéancier natif figé est requis.")
    terms_version = product.terms_version if product.product_id is not None else None
    if (
        schedule.terms_fingerprint != terms.fingerprint or schedule.instrument_type != terms.instrument_type
        or schedule.product_id != product.product_id or schedule.terms_version != terms_version
    ):
        raise RatesMarketError("RATES_SCHEDULE_INCOMPATIBLE", "L’échéancier figé ne correspond pas à la version de termes.")
    return schedule


def _select_fixing(period: SchedulePeriod, valuation_date: Date, cutoff: datetime, zone: ZoneInfo,
                   fixings: dict[Date, list[EuriborFixing]]) -> SelectedEuriborFixing | None:
    day = period.fixing_date
    if day is None:
        raise RatesMarketError("RATES_SCHEDULE_INCOMPATIBLE", f"La période {period.period_id} n’a pas de date de fixing.")
    if day > valuation_date or datetime.combine(day, _FIXING_DUE, tzinfo=zone) > cutoff:
        return None
    fixing = _latest_eligible(fixings.get(day, []), f"le fixing Euribor 3M du {day:%d/%m/%Y}")
    if fixing is None:
        raise RatesMarketError("RATES_FIXING_UNAVAILABLE", f"Fixing Euribor 3M du {day:%d/%m/%Y} indisponible à l’arrêté.")
    return SelectedEuriborFixing.model_validate(fixing.model_dump(exclude={"ingested_at"}))


def _open_state(payment_date: Date, valuation_date: Date, allow_overdue_payments: bool) -> Literal["future", "due_open"]:
    if payment_date < valuation_date and not allow_overdue_payments:
        raise RatesMarketError(
            "RATES_OVERDUE_PAYMENT", f"Créance ouverte échue le {payment_date:%d/%m/%Y}, politique d’impayé requise.",
        )
    return "due_open" if payment_date <= valuation_date else "future"


def prepare_rates_market(product: Product, valuation_date: Date, cutoff: datetime,
                         market: RatesMarket, *, allow_overdue_payments: bool = False) -> RatesMarketSelection:
    """Select eligible versions and cover contractual dates using a frozen schedule."""
    schedule = _validate_product(product)
    zone = ZoneInfo(_POLICY_ZONE)
    if cutoff.utcoffset() is None:
        raise RatesMarketError("RATES_CUTOFF_INVALID", "L’arrêté doit porter un fuseau horaire.")
    if cutoff.astimezone(zone).date() != valuation_date or market.market_date != valuation_date:
        raise RatesMarketError("RATES_DATE_INCOMPATIBLE", "Les dates d’arrêté et de marché doivent concorder dans le fuseau de recette.")
    cutoff = cutoff.astimezone(timezone.utc)
    discount = _select_curve(market.discount, "discount", valuation_date, cutoff)
    projection = _select_curve(market.projection, "projection", valuation_date, cutoff)

    fixings_by_date: dict[Date, list[EuriborFixing]] = {}
    for fixing in market.fixings:
        if (fixing.currency, fixing.index, fixing.tenor) == _FIXING_IDENTITY and fixing.eligible_at(cutoff):
            fixings_by_date.setdefault(fixing.observation_date, []).append(fixing)
    payments_by_flow: dict[str, list[PaymentConfirmation]] = {}
    for payment in market.payments:
        if (payment.schedule_fingerprint == schedule.fingerprint
                and payment.effect_date <= valuation_date and payment.eligible_at(cutoff)):
            payments_by_flow.setdefault(payment.flow_id, []).append(payment)

    selected_fixings: dict[Date, SelectedEuriborFixing] = {}
    selected_payments = []
    flows = []
    discount_dates: set[Date] = set()
    projection_dates: set[Date] = set()
    for leg in schedule.legs:
        for flow in (*leg.periods, *leg.events):
            period = flow if isinstance(flow, SchedulePeriod) else None
            payment_date = period.payment_date if period is not None else flow.date
            if flow.flow_id is None or payment_date is None:
                raise RatesMarketError("RATES_SCHEDULE_INCOMPATIBLE", "Un flux de l’échéancier est sans identité ou date de paiement.")

            payment = _latest_eligible(payments_by_flow.pop(flow.flow_id, []), f"le paiement {flow.flow_id}")
            if payment is not None:
                if payment.effect_date < payment_date:
                    raise RatesMarketError("RATES_PAYMENT_INCOMPATIBLE", f"Le paiement {flow.flow_id} précède son échéance.")
                selected_payments.append(SelectedPaymentConfirmation.model_validate(payment.model_dump(exclude={"ingested_at"})))
            else:
                discount_dates.add(max(payment_date, valuation_date))
            state = "paid" if payment is not None else _open_state(payment_date, valuation_date, allow_overdue_payments)

            fixing = None
            fixing_state = None
            if period is not None and leg.kind == "floating_coupon":
                fixing = _select_fixing(period, valuation_date, cutoff, zone, fixings_by_date)
                if fixing is not None:
                    selected_fixings[fixing.observation_date] = fixing
                else:
                    if period.projection_start is None or period.projection_end is None:
                        raise RatesMarketError("RATES_SCHEDULE_INCOMPATIBLE", f"La période {period.period_id} n’a pas de bornes de projection.")
                    projection_dates.update((period.projection_start, period.projection_end))
                fixing_state = "fixed" if fixing is not None else "projected"
            flows.append(RatesFlowSelection(
                flow_id=flow.flow_id, leg_id=leg.leg_id, period_id=period.period_id if period is not None else None,
                payment_date=payment_date, state=state, fixing_state=fixing_state,
                fixing_id=fixing.fixing_id if fixing is not None else None, fixing_version=fixing.version if fixing is not None else None,
                payment_fact_id=payment.fact_id if payment is not None else None, payment_version=payment.version if payment is not None else None,
            ))

    if payments_by_flow:
        raise RatesMarketError("RATES_PAYMENT_INCOMPATIBLE", "Un paiement validé vise un flux absent de l’échéancier.")
    for day in sorted(discount_dates):
        discount.factor_at(day)
    for day in sorted(projection_dates):
        projection.factor_at(day)

    market_fingerprint = canonical_fingerprint({
        "policy_version": _POLICY_VERSION,
        "market_id": market.market_id, "market_version": market.market_version, "market_date": market.market_date.isoformat(),
        "discount": discount.model_dump(mode="json"), "projection": projection.model_dump(mode="json"),
        "frn_funding_bps": market.frn_funding_bps,
    })
    return RatesMarketSelection(
        market_id=market.market_id, market_version=market.market_version, market_fingerprint=market_fingerprint,
        valuation_date=valuation_date, cutoff_utc=cutoff, settlement_date=valuation_date,
        discount=discount, projection=projection, frn_funding_bps=market.frn_funding_bps,
        fixings=tuple(selected_fixings[day] for day in sorted(selected_fixings)), payments=tuple(selected_payments),
        flows=tuple(flows), discount_dates=tuple(sorted(discount_dates)), projection_dates=tuple(sorted(projection_dates)),
        overdue_treatment="face_at_valuation_date" if allow_overdue_payments else None,
    )
