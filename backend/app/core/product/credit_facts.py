"""Versioned facts for the synthetic credit-event recipe."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .models import FrozenModel


_PARIS = ZoneInfo("Europe/Paris")


class _SyntheticCreditFact(FrozenModel):
    source: Literal["synthetic_credit_recipe"] = "synthetic_credit_recipe"
    default_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)
    version: int = Field(strict=True, ge=1)
    effect_date: date
    available_at: AwareDatetime
    validated_at: AwareDatetime | None

    @field_validator("available_at", "validated_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class SyntheticDefaultFact(_SyntheticCreditFact):
    kind: Literal["default"] = "default"


class SyntheticRecoveryFact(_SyntheticCreditFact):
    kind: Literal["recovery_final"] = "recovery_final"
    recovery_fraction: float = Field(strict=True, ge=0, le=1)


class SyntheticSettlementFact(_SyntheticCreditFact):
    kind: Literal["settlement_confirmed"] = "settlement_confirmed"
    default_version: int | None = Field(default=None, strict=True, ge=1, exclude_if=lambda value: value is None)
    recovery_version: int | None = Field(default=None, strict=True, ge=1, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def requires_both_links(self):
        if (self.default_version is None) != (self.recovery_version is None):
            raise ValueError("Le règlement lie les versions du défaut et du recouvrement ensemble.")
        return self


SyntheticCreditFact = Annotated[
    SyntheticDefaultFact | SyntheticRecoveryFact | SyntheticSettlementFact, Field(discriminator="kind"),
]


class SyntheticCreditSelection(FrozenModel):
    default_id: str
    default: SyntheticDefaultFact | None = None
    recovery: SyntheticRecoveryFact | None = None
    settlement: SyntheticSettlementFact | None = None

    @property
    def state(self) -> Literal["alive", "recovery_pending", "settlement_pending", "settled"]:
        if self.default is None:
            return "alive"
        if self.recovery is None:
            return "recovery_pending"
        return "settled" if self.settlement else "settlement_pending"


def select_synthetic_credit_facts(
    default_id: str, facts: Sequence[SyntheticCreditFact], cutoff: AwareDatetime,
) -> SyntheticCreditSelection:
    """Select eligible versions for a synthetic default without deriving cash."""
    if cutoff.utcoffset() is None:
        raise ValueError("Le cut-off des faits de crédit doit indiquer son fuseau horaire.")
    as_of = cutoff.astimezone(_PARIS).date()
    cutoff = cutoff.astimezone(timezone.utc)
    latest = {}
    versions = {}
    for fact in facts:
        if (
            fact.default_id != default_id
            or fact.effect_date > as_of
            or fact.validated_at is None
            or max(fact.available_at, fact.validated_at) > cutoff
        ):
            continue
        key = (fact.kind, fact.version)
        if key in versions and versions[key] != fact:
            raise ValueError("Deux preuves de crédit diffèrent pour la même version.")
        versions[key] = fact
        previous = latest.get(fact.kind)
        if previous is None or fact.version > previous.version:
            latest[fact.kind] = fact

    default = latest.get("default")
    recovery = latest.get("recovery_final") if default else None
    settlement = latest.get("settlement_confirmed") if recovery else None
    if recovery and recovery.effect_date < default.effect_date:
        raise ValueError("Le recouvrement constaté précède la date d’effet du défaut.")
    if settlement and settlement.recovery_version is None and settlement.effect_date < recovery.effect_date:
        raise ValueError("Le règlement confirmé précède la date d’effet du recouvrement.")
    return SyntheticCreditSelection(
        default_id=default_id, default=default, recovery=recovery, settlement=settlement,
    )
