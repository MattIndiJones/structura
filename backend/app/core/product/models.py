"""Immutable product snapshots, distinct from external calculation inputs."""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, RootModel, TypeAdapter, field_validator, model_serializer, model_validator,
)

from ..calendars import BusinessDayConvention
from ..valuation_context import canonical_fingerprint, canonical_json
from .native_schedule_models import NativeSchedule


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class FrozenObject(RootModel[str]):
    """An immutable copy of a parser/domain JSON object.

    Only the encoded text is held internally. Every public projection is a
    fresh tree, so nested calendar edits cannot change a received product.
    This is used for existing versioned domain payloads, not arbitrary fields
    added to Product by consumers.
    """
    model_config = ConfigDict(frozen=True)
    root: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def encode(cls, value):
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("Un objet JSON est requis.")
        return canonical_json(value)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        return self.to_dict()

    def to_dict(self) -> dict:
        return json.loads(self.root)


class UnderlyingIdentity(FrozenModel):
    name: str = Field(min_length=1)
    ticker: str = ""
    ccy: str = Field(min_length=3, max_length=3)
    # Quanto or compo is a clause of the term sheet, not a market assumption:
    # a pricing context must never be able to turn one into the other. Absent
    # for every product saved before 26/11/2026, so their fingerprint is unchanged.
    fx_mode: Literal["quanto", "compo"] | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("fx_mode", mode="before")
    @classmethod
    def blank_is_historical(cls, value):
        return value or None


class ContractParameter(FrozenModel):
    name: str = Field(min_length=1)
    value: float | tuple[float | None, ...] | None
    is_pct: bool
    kind: Literal["scalar", "array"]
    description: str = ""

    @model_validator(mode="after")
    def shape(self):
        if isinstance(self.value, tuple) and (not self.value or self.kind != "array"):
            raise ValueError("Série de paramètres vide ou incompatible avec PARAM scalaire.")
        return self


class ProductTerms(FrozenModel):
    schema_version: Literal[1] = 1
    script: str = Field(min_length=1, max_length=32000)
    parameters: tuple[ContractParameter, ...] = ()
    underlyings: tuple[UnderlyingIdentity, ...] = Field(default=(), max_length=12)
    constats: FrozenObject = Field(default_factory=FrozenObject)
    T: float | None = Field(default=None, gt=0, le=30)
    strike_date: date | None = None
    value_date: date | None = None
    maturity_date: date | None = None
    payment_date: date | None = None
    anchor: date | None = None
    settlement_ccy: str | None = None
    schedule: FrozenObject | None = None
    resolved_events: FrozenObject | None = None
    schedule_error: str | None = None

    @model_validator(mode="after")
    def identities(self):
        names = [u.name for u in self.underlyings]
        if len(names) != len(set(names)):
            raise ValueError("Les noms des sous-jacents doivent être uniques.")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Un paramètre contractuel ne peut être déclaré deux fois.")
        if self.strike_date and self.maturity_date and self.maturity_date < self.strike_date:
            raise ValueError("La maturité ne peut pas précéder le strike.")
        if self.payment_date and self.maturity_date and self.payment_date < self.maturity_date:
            raise ValueError("Le paiement ne peut pas précéder la maturité.")
        return self

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self.model_dump(mode="json"))

    def user_params(self) -> dict:
        return {p.name: list(p.value) if isinstance(p.value, tuple) else p.value
                for p in self.parameters}

    def require_complete(self):
        missing = [p.name for p in self.parameters if p.value is None]
        for p in self.parameters:
            if isinstance(p.value, tuple):
                missing.extend(f'{p.name}[{i + 1}]' for i, value in enumerate(p.value) if value is None)
        if not self.underlyings:
            missing.append('panier de sous-jacents')
        if self.T is None:
            missing.append('calendrier / maturité')
        if missing:
            raise ValueError('Produit incomplet : ' + ', '.join(missing) + '.')
        if self.schedule_error:
            raise ValueError(self.schedule_error)

    def pricing_fields(self) -> dict:
        """Fresh contractual projection; market fields cannot be supplied here."""
        return {
            "script": self.script,
            "underlyings": [u.model_dump() for u in self.underlyings],
            "user_params": self.user_params(), "constats": self.constats.to_dict(),
            "T": self.T, "strike_date": self.strike_date,
            "value_date": self.value_date, "maturity_date": self.maturity_date,
            "payment_date": self.payment_date, "anchor": self.anchor,
            "settlement_ccy": self.settlement_ccy,
            "frozen_schedule": self.resolved_events.to_dict() if self.resolved_events else None,
        }


class CouponLegTerms(FrozenModel):
    calendar: str = Field(min_length=1)
    business_day_convention: BusinessDayConvention
    frequency_months: int = Field(strict=True, gt=0, le=12)
    payment_lag_business_days: int = Field(strict=True, ge=0, le=30)


class EuriborLegTerms(CouponLegTerms):
    index: Literal["EURIBOR_3M"]
    day_count: Literal["ACT/360"]
    margin_bps: Annotated[float, Field(strict=True)] | None
    fixing_calendar: str = Field(min_length=1)
    fixing_lag_business_days: int = Field(strict=True, ge=0, le=30)


class FixedLegTerms(CouponLegTerms):
    day_count: Literal["30E/360"]
    # Rate as a decimal fraction of nominal per year.
    coupon_rate: Annotated[float, Field(strict=True)] | None


class CDSPremiumLegTerms(CouponLegTerms):
    day_count: Literal["ACT/360"]
    coupon_bps: Annotated[float, Field(strict=True, ge=0)] | None


class NativeProductTerms(FrozenModel):
    schema_version: Literal[2]
    payoff_mode: Literal["native"]
    template_id: str = Field(min_length=1)
    template_version: int = Field(strict=True, ge=1)
    currency: Literal["EUR"]
    effective_date: date | None = None
    maturity_date: date | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.effective_date and self.maturity_date and self.maturity_date <= self.effective_date:
            raise ValueError("La maturité doit suivre la date d’effet.")
        return self

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self.model_dump(mode="json"))


class RatesScriptTerms(FrozenModel):
    profile: Literal["rates-deterministic-v1"]
    source: str = Field(min_length=1, max_length=12000)
    parameters: FrozenObject = Field(default_factory=lambda: FrozenObject.model_validate({}))

    @model_validator(mode="after")
    def check_parameters(self):
        parameters = self.parameters.to_dict()
        if len(parameters) > 32 or any(
            not key.isidentifier() or type(value) not in (int, float) for key, value in parameters.items()
        ):
            raise ValueError("Les paramètres du PayScript de taux doivent être des valeurs numériques nommées.")
        return self


class RatesProductTerms(NativeProductTerms):
    payoff_mode: Literal["native", "scripted"]
    rates_script: RatesScriptTerms | None = Field(default=None, exclude_if=lambda value: value is None)
    floating_leg: EuriborLegTerms

    @model_validator(mode="after")
    def check_payoff_mode(self):
        if (self.payoff_mode == "scripted") != (self.rates_script is not None):
            raise ValueError("Le PayScript de taux est requis en mode scripté et absent en mode Template.")
        return self


class FRNTerms(RatesProductTerms):
    instrument_type: Literal["FRN"]
    redemption_fraction: float = Field(strict=True, ge=1, le=1)
    issuer_reference: str | None = None
    security_id: str | None = None


class IRSTerms(RatesProductTerms):
    instrument_type: Literal["IRS"]
    fixed_leg: FixedLegTerms
    collateral_reference: str | None = None


class CDSTerms(NativeProductTerms):
    instrument_type: Literal["CDS"]
    trade_date: date | None = None
    reference_entity_id: str = Field(min_length=1)
    seniority: str = Field(min_length=1)
    documentation: str = Field(min_length=1)
    restructuring: str = Field(min_length=1)
    premium_leg: CDSPremiumLegTerms
    step_in_lag_calendar_days: int = Field(strict=True, ge=0, le=30)
    cash_settlement_lag_business_days: int = Field(strict=True, ge=0, le=30)
    accrued_on_default: bool = Field(strict=True)


class CLNCouponLegTerms(CouponLegTerms):
    day_count: Literal["ACT/360", "30E/360"]
    coupon_rate: Annotated[float, Field(strict=True, ge=0)] | None


class CLNTerms(NativeProductTerms):
    instrument_type: Literal["CLN"]
    issuer_reference: str = Field(min_length=1)
    reference_entity_id: str = Field(min_length=1)
    seniority: str = Field(min_length=1)
    documentation: str = Field(min_length=1)
    restructuring: str = Field(min_length=1)
    fixed_leg: CLNCouponLegTerms
    redemption_fraction: float = Field(strict=True, ge=1, le=1)
    coupon_entitlement: Literal["survival_through_accrual_end"]
    coupon_on_default: Literal["none"]
    default_redemption: Literal["nominal_times_recovery"]
    default_settlement_lag_calendar_days: int = Field(strict=True, ge=0, le=365)

    @model_validator(mode="after")
    def distinct_issuer_and_reference(self):
        issuer = self.issuer_reference.strip().casefold()
        reference = self.reference_entity_id.strip().casefold()
        if not issuer or not reference or issuer == reference:
            raise ValueError("La CLN requiert un émetteur et une entité de référence distincts.")
        return self


class ExoticTerms(NativeProductTerms):
    instrument_type: Literal["EXOTIC_RATES", "EXOTIC_CREDIT"]
    payoff_mode: Literal["native", "scripted"]
    effective_date: date
    maturity_date: date
    time_origin: date
    clock: Literal["ACT/365F"] = "ACT/365F"
    contract: FrozenObject
    reference_entities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def check_contract(self):
        payload = self.contract.to_dict()
        if {"nominal_eur", "side"}.intersection(payload):
            raise ValueError("Le nominal et le sens du contrat exotique relèvent de la position.")
        if self.instrument_type == "EXOTIC_RATES":
            from .exotic_rates_mc import ExoticRatesTerms

            # Use a structural witness only to validate a past observation's
            # shape. The actual acquired level lives in the pricing receipt.
            flows = payload.get("cashflows")
            if not isinstance(flows, list):
                raise ValueError("La liste des flux exotiques est requise.")
            for flow in flows:
                if not isinstance(flow, dict):
                    raise ValueError("Un flux exotique doit être un objet JSON.")
                observations = [flow] if flow.get("kind") == "rate" else flow.get("observations", [])
                if not isinstance(observations, list) or not all(isinstance(item, dict) for item in observations):
                    raise ValueError("Les observations exotiques doivent être des objets JSON.")
                for observation in observations:
                    if "realized_rate" in observation:
                        raise ValueError("Les fixings acquis appartiennent à l’arrêté de valorisation.")
                    time = observation.get("fixing", observation.get("time"))
                    if type(time) in (int, float) and time <= 0:
                        observation["realized_rate"] = 0
            parsed = ExoticRatesTerms.model_validate({**payload, "nominal_eur": 1, "side": "BUY"})
            scripted = any(getattr(flow, "payscript", None) is not None for flow in parsed.cashflows)
            if self.reference_entities or (self.payoff_mode == "scripted") != scripted:
                raise ValueError("Le payoff taux et les références du contrat sont incohérents.")
        else:
            from .exotic_credit_mc import CreditMcContract

            parsed = CreditMcContract.model_validate({**payload, "nominal_eur": 1, "side": "BUY"})
            refs = self.reference_entities
            if (refs != tuple(sorted(set(refs))) or not all(item.strip() for item in refs)
                    or (len(refs) < max(2, parsed.trigger_rank) if parsed.kind == "basket_cds" else len(refs) != 1)
                    or (self.payoff_mode == "scripted") != (parsed.payscript is not None)):
                raise ValueError("Le payoff crédit et les références du contrat exotique sont incohérents.")
        return self


NativeTerms = Annotated[FRNTerms | IRSTerms | CDSTerms | CLNTerms | ExoticTerms, Field(discriminator="instrument_type")]
_native_terms_adapter = TypeAdapter(NativeTerms)


def product_terms_schema(payload: object) -> int:
    """Distinguish a missing v1 marker from invalid or unsupported markers."""
    if not isinstance(payload, dict):
        raise ValueError("Les termes du produit doivent être un objet JSON.")
    version = payload.get("schema_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("La version du schéma des termes est inconnue ou invalide.")
    if version == 1 and ("instrument_type" in payload or "payoff_mode" in payload):
        raise ValueError("Les termes PayScript historiques ne portent pas de discriminant natif.")
    return version


class TradeIntent(FrozenModel):
    nominal: float | None = Field(default=None, gt=0)
    side: Literal["BUY", "SELL"] = "BUY"
    counterparty_id: int | None = None
    counterparty_name: str = ""
    product_type: str = ""
    transaction_format: str = ""
    instrument_family: str = ""
    payoff_family: str = ""
    payoff_description: str = ""
    documentation_reference: str = ""


class CommercialContext(FrozenModel):
    client_id: int | None = None
    mandate_id: int | None = None
    opportunity_id: int | None = None
    primary_affiliation_id: int | None = None


class CalculationRef(FrozenModel):
    id: int
    terms_version: int
    kind: str
    calculated_at: str
    valuation_date: str | None = None
    price: float | None = None
    source: str
    measure: Literal["frn_clean_price", "irs_net_pv", "cds_clean_price", "cln_clean_price", "credit_pv", "exotic_economic_pv"] | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    price_unit: Literal["per_100_notional", "EUR"] | None = Field(default=None, exclude_if=lambda value: value is None)
    nominal: float | None = Field(default=None, exclude_if=lambda value: value is None)
    side: Literal["BUY", "SELL"] | None = Field(default=None, exclude_if=lambda value: value is None)


class Product(FrozenModel):
    schema_version: Literal[1] = 1
    product_id: int | None = None
    reference: str | None = None
    name: str = ""
    revision: int = 0
    terms_version: int = 0
    origin_product_id: int | None = None
    data_origin: Literal["native", "demo", "uat", "imported"] = "native"
    # Persistence and library visibility are separate. Existing explicitly
    # retained Products default to listed; workflow-created Products override
    # this to False until the user chooses to expose them in "Mes produits".
    listed: bool = True
    archived: bool = False
    terms: ProductTerms | NativeTerms
    intent: TradeIntent = Field(default_factory=TradeIntent)
    commercial: CommercialContext = Field(default_factory=CommercialContext)
    indicatives: tuple[FrozenObject, ...] = ()
    rfqs: tuple[FrozenObject, ...] = ()
    execution: FrozenObject | None = None
    lifecycle: FrozenObject | None = None
    documents: tuple[FrozenObject, ...] = ()
    calculations: tuple[CalculationRef, ...] = ()
    native_schedule: NativeSchedule | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("terms", mode="before")
    @classmethod
    def read_versioned_terms(cls, value):
        if isinstance(value, (ProductTerms, FRNTerms, IRSTerms, CDSTerms, CLNTerms, ExoticTerms)):
            return value
        if product_terms_schema(value) == 1:
            return ProductTerms.model_validate(value)
        return _native_terms_adapter.validate_python(value)

    @property
    def terms_fingerprint(self) -> str:
        return self.terms.fingerprint

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
