"""Prepare and fingerprint the effective inputs for a native Product valuation."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..valuation_context import canonical_fingerprint
from .isda_market import IsdaMarket, IsdaMarketSelection, prepare_isda_market
from .models import CDSTerms, FRNTerms, IRSTerms, FrozenModel, Product
from .rates_market import RatesMarket, RatesMarketSelection, prepare_rates_market


NativeMarket = Annotated[RatesMarket | IsdaMarket, Field(discriminator="kind")]
MarketSelection = Annotated[RatesMarketSelection | IsdaMarketSelection, Field(discriminator="kind")]


class NativeMarketError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NativeValuationInputs(FrozenModel):
    schema_version: Literal[1] = 1
    product_id: int | None = Field(ge=1)
    terms_version: int | None = Field(ge=1)
    terms_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    schedule_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    instrument_type: Literal["FRN", "IRS", "CDS"]
    currency: Literal["EUR"]
    nominal: float = Field(gt=0)
    side: Literal["BUY", "SELL"]
    valuation_date: date
    value_date: date
    cutoff: AwareDatetime
    cutoff_timezone: Literal["Europe/Paris"] = "Europe/Paris"
    readiness: Literal["ready_for_pricing", "ready_for_curve_construction_and_conversion"]
    market: MarketSelection

    @field_validator("cutoff")
    @classmethod
    def normalize_cutoff(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_market_binding(self):
        is_cds = self.instrument_type == "CDS"
        if (self.product_id is None) != (self.terms_version is None):
            raise ValueError("Les références du dossier et de la version de termes doivent être cohérentes.")
        expected = ("isda", "ready_for_curve_construction_and_conversion") if is_cds else ("rates", "ready_for_pricing")
        if (self.market.kind, self.readiness) != expected:
            raise ValueError("La préparation du marché ne correspond pas à l’instrument.")
        if isinstance(self.market, RatesMarketSelection) and (
            self.market.valuation_date, self.market.cutoff_utc, self.market.settlement_date,
        ) != (self.valuation_date, self.cutoff, self.value_date):
            raise ValueError("L’arrêté du marché de taux ne correspond pas au contexte.")
        if isinstance(self.market, IsdaMarketSelection) and (
            self.market.ois_quotes.chronology.anchor_date != self.valuation_date
            or self.market.contract_terms.notional_eur != self.nominal
        ):
            raise ValueError("Le jour d’ancrage ou le nominal ISDA ne correspond pas au contexte.")
        return self


class NativeValuationContext(NativeValuationInputs):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self):
        if canonical_fingerprint(self.model_dump(mode="json", exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("L’empreinte du contexte de valorisation est incohérente.")
        return self

    @classmethod
    def seal(cls, inputs: NativeValuationInputs) -> NativeValuationContext:
        payload = inputs.model_dump(mode="json")
        return cls.model_validate({**payload, "fingerprint": canonical_fingerprint(payload)})


def prepare_native_context(product: Product, *, valuation_date: date, cutoff: datetime,
                           market: NativeMarket | IsdaMarketSelection, value_date: date | None = None,
                           allow_draft: bool = False, allow_overdue_rates_payments: bool = False) -> NativeValuationContext:
    terms = product.terms
    schedule = product.native_schedule
    if not isinstance(terms, (FRNTerms, IRSTerms, CDSTerms)):
        raise NativeMarketError("PRODUCT_TERMS_UNSUPPORTED", "La préparation native requiert un FRN, un IRS ou un CDS.")
    terms_version = None if product.product_id is None else product.terms_version
    if (schedule is None or (product.product_id is None and not allow_draft)
            or (schedule.product_id, schedule.terms_version) != (product.product_id, terms_version)
            or schedule.terms_fingerprint != terms.fingerprint):
        raise NativeMarketError("PRODUCT_SCHEDULE_NOT_READY", "Une version de produit avec échéancier figé est requise.")
    if product.intent.nominal is None:
        raise NativeMarketError("PRODUCT_NOMINAL_REQUIRED", "Le nominal est requis pour préparer la valorisation.")
    if cutoff.utcoffset() is None:
        raise NativeMarketError("MARKET_CUTOFF_INVALID", "Le cut-off doit indiquer son fuseau horaire.")
    cutoff = cutoff.astimezone(timezone.utc)
    value_date = valuation_date if value_date is None else value_date
    if value_date != valuation_date:
        raise NativeMarketError("MARKET_VALUE_DATE_UNSUPPORTED", "Le témoin utilise la date de valorisation comme date de valeur.")

    if isinstance(terms, CDSTerms) and isinstance(market, (IsdaMarket, IsdaMarketSelection)):
        selection = prepare_isda_market(product, valuation_date, cutoff, market)
        readiness = "ready_for_curve_construction_and_conversion"
    elif isinstance(terms, (FRNTerms, IRSTerms)) and isinstance(market, RatesMarket):
        selection = prepare_rates_market(product, valuation_date, cutoff, market,
                                         allow_overdue_payments=allow_overdue_rates_payments)
        readiness = "ready_for_pricing"
    else:
        raise NativeMarketError("MARKET_INSTRUMENT_MISMATCH", "Le jeu de marché est incompatible avec l’instrument.")

    inputs = NativeValuationInputs(
        product_id=product.product_id,
        terms_version=terms_version,
        terms_fingerprint=terms.fingerprint,
        schedule_fingerprint=schedule.fingerprint,
        instrument_type=terms.instrument_type,
        currency=terms.currency,
        nominal=product.intent.nominal,
        side=product.intent.side,
        valuation_date=valuation_date,
        value_date=value_date,
        cutoff=cutoff,
        readiness=readiness,
        market=selection,
    )
    return NativeValuationContext.seal(inputs)
