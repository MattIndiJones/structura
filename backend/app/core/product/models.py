"""Immutable product snapshots, distinct from external calculation inputs."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, RootModel, model_serializer, model_validator,
)

from ..valuation_context import canonical_fingerprint, canonical_json


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


class ContractParameter(FrozenModel):
    name: str = Field(min_length=1)
    value: float | tuple[float, ...]
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
    underlyings: tuple[UnderlyingIdentity, ...] = Field(min_length=1, max_length=12)
    constats: FrozenObject = Field(default_factory=FrozenObject)
    T: float = Field(gt=0, le=30)
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
    terms: ProductTerms
    intent: TradeIntent = Field(default_factory=TradeIntent)
    commercial: CommercialContext = Field(default_factory=CommercialContext)
    indicatives: tuple[FrozenObject, ...] = ()
    rfqs: tuple[FrozenObject, ...] = ()
    execution: FrozenObject | None = None
    lifecycle: FrozenObject | None = None
    documents: tuple[FrozenObject, ...] = ()
    calculations: tuple[CalculationRef, ...] = ()

    @property
    def terms_fingerprint(self) -> str:
        return self.terms.fingerprint

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
