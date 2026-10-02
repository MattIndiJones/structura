"""Explicit CCR input contracts. Money is in the stated currency; rates are fractions."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas import PricingRequest


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CreditProfile(Contract):
    legal_name: str = ""
    short_name: str = ""
    lei: str = ""
    counterparty_type: Literal["Bank", "Broker", "Asset Manager", "Fund", "Corporate", "Insurance", "Client", "CCP", "Internal", "Other"] = "Other"
    parent_group: str = ""
    currency: str = "EUR"
    internal_rating: str = ""
    external_rating: str = ""
    recovery: float | None = Field(default=None, ge=0, lt=1)
    recovery_source: Literal["MARKET_DATA", "INTERNAL_DATA", "USER_ASSUMPTION", "SYSTEM_DEFAULT", "UNKNOWN"] = "UNKNOWN"
    curve_source: Literal["CDS_MARKET", "BOND_IMPLIED", "INTERNAL_PD", "RATING_BASED", "MANUAL", "UNKNOWN"] = "UNKNOWN"
    pd_measure: Literal["RISK_NEUTRAL", "HISTORICAL", "UNKNOWN"] = "UNKNOWN"
    pd_curve: list[list[float]] = Field(default_factory=list)
    spread_curve: list[list[float]] = Field(default_factory=list)
    has_isda: bool | None = None
    has_csa: bool | None = None

    @model_validator(mode="after")
    def curves(self):
        for curve, is_pd in [(self.pd_curve, True), (self.spread_curve, False)]:
            prev_t, prev_pd = 0, 0
            for node in curve:
                if len(node) != 2 or node[0] <= prev_t or node[1] < 0:
                    raise ValueError("Courbe : maturités croissantes et valeurs positives requises")
                if is_pd and (node[1] < prev_pd or node[1] > 1):
                    raise ValueError("Les PD cumulées doivent croître entre 0 et 1")
                prev_t, prev_pd = node
        if self.pd_curve and self.spread_curve:
            raise ValueError("Choisir une seule courbe de crédit active : PD ou spread")
        if (self.pd_curve or self.spread_curve) and (self.curve_source == "UNKNOWN" or self.pd_measure == "UNKNOWN"):
            raise ValueError("Source et mesure de probabilité obligatoires")
        if self.recovery is not None and self.recovery_source == "UNKNOWN":
            raise ValueError("La provenance du recouvrement est obligatoire")
        return self


class MasterAgreement(Contract):
    agreement_id: str = Field(min_length=1)
    agreement_version: str = ""
    effective_date: date
    governing_law: str = Field(min_length=1)
    status: Literal["ACTIVE", "INACTIVE", "PENDING", "UNKNOWN"] = "UNKNOWN"
    legal_opinion_available: bool | None = None
    close_out_netting_enforceable: bool | None = None
    cross_product_netting_allowed: bool | None = None
    notes: str = ""


class CSAAgreement(Contract):
    csa_id: str = Field(min_length=1)
    master_agreement_id: int
    bilateral: bool = True
    collateralised: bool | None = None
    vm_required: bool | None = None
    vm_frequency_days: int = Field(default=1, ge=1, le=365)
    threshold_counterparty: float = Field(default=0, ge=0)
    threshold_our_side: float = Field(default=0, ge=0)
    mta: float = Field(default=0, ge=0)
    independent_amount: float = Field(default=0, ge=0)
    im_required: bool | None = None
    im_model: str = "FIXED"
    im_amount: float = Field(default=0, ge=0)
    segregated: bool | None = None
    im_recognised: bool = False
    base_currency: str = "EUR"
    eligible_collateral: list[str] = Field(default_factory=lambda: ["CASH"])
    collateral_haircut: float = Field(default=0, ge=0, lt=1)
    settlement_lag_days: int = Field(default=0, ge=0, le=60)
    mpor_days: int | None = Field(default=None, ge=1, le=365)
    active: bool = True


class NettingSet(Contract):
    netting_set_id: str = Field(min_length=1)
    master_agreement_id: int
    csa_id: int | None = None
    currency: str = "EUR"
    product_scope: list[str] = Field(min_length=1)
    our_legal_entity: str = Field(min_length=1)
    counterparty_legal_entity: str = Field(min_length=1)
    active: bool = True
    enforceable_netting: bool | None = None


Metric = Literal["gross_notional", "current_exposure", "pfe95", "pfe99", "ead", "cva", "stressed_exposure"]


class CreditLimit(Contract):
    metric: Metric
    amount: float = Field(gt=0)
    currency: str = "EUR"
    warning_threshold: float = Field(default=0.8, ge=0)
    hard_threshold: float = Field(default=1, gt=0)
    action: Literal["INFORMATION_ONLY", "WARNING", "REQUIRE_APPROVAL", "HARD_BLOCK"] = "INFORMATION_ONLY"
    active: bool = True
    effective_date: date
    expiry_date: date | None = None

    @model_validator(mode="after")
    def thresholds(self):
        if self.warning_threshold >= self.hard_threshold:
            raise ValueError("Seuil d'alerte strictement inférieur au seuil dur requis")
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("La date d'expiration précède la date d'effet")
        return self


class CollateralPosition(Contract):
    netting_set_id: int
    as_of_date: date
    currency: str = "EUR"
    collateral_type: str = "CASH"
    held: float = Field(default=0, ge=0)
    posted: float = Field(default=0, ge=0)
    im_held: float = Field(default=0, ge=0)
    recognised: bool = False
    source: str = Field(min_length=1)


class CreditOverride(Contract):
    limit_id: int
    requested_by: int
    approved_by: int | None = None
    reason: str = Field(min_length=1)
    effective_date: date
    expiry_date: date
    previous_limit: float = Field(gt=0)
    temporary_limit: float = Field(gt=0)
    status: Literal["REQUESTED", "APPROVED", "REJECTED"] = "REQUESTED"


class RegulatoryFramework(Contract):
    framework: str
    version: str
    effective_date: date
    jurisdiction: str
    alpha: float = Field(gt=0)


class ProposedTrade(Contract):
    pricing: PricingRequest
    nominal: float = Field(gt=0)
    currency: str = "EUR"
    sens: Literal["achat", "vente"] = "vente"
    product_type: str = ""
    netting_set_id: int | None = None


class MarketOverride(Contract):
    sigma: float | None = Field(default=None, ge=0)
    q: float | None = None


class PriceHistory(Contract):
    dates: list[date]
    closes: list[float]

    @model_validator(mode="after")
    def ordered(self):
        if not self.dates or len(self.dates) != len(self.closes) or any(v <= 0 for v in self.closes):
            raise ValueError("Historique : dates et clôtures positives de même longueur requises")
        if any(b <= a for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError("Historique : dates strictement croissantes requises")
        return self


class CalculationRequest(Contract):
    prepare_mtm: bool = False
    refresh_mtm: bool = False
    mtm_paths: int = Field(default=10000, ge=1000, le=100000)
    common_rate: float | None = Field(default=None, gt=-1, lt=1)
    common_rate_source: Literal["TEMPORARY_ASSUMPTION", "USER_OVERRIDE"] | None = None
    common_market: bool = False
    market_overrides: dict[str, MarketOverride] = Field(default_factory=dict)
    allow_market_fetch: bool = False
    price_histories: dict[str, PriceHistory] = Field(default_factory=dict)
    data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION"
    uat_batch_id: int | None = Field(default=None, gt=0)
    valuation_method: Literal["FULL_REVALUATION", "NESTED_MONTE_CARLO", "PROXY", "REGRESSION", "INTERPOLATION"] = "NESTED_MONTE_CARLO"
    counterparty_id: int | None = None
    netting_set_id: int | None = None
    deal_id: int | None = None
    portfolio_id: int | None = None
    as_of_date: date = Field(default_factory=date.today)
    currency: str = "EUR"
    proposed: ProposedTrade | None = None
    mode: Literal["FULL", "FAST"] = "FULL"
    n_outer: int = Field(default=256, ge=32, le=5000)
    n_inner: int = Field(default=128, ge=32, le=5000)
    n_dates: int = Field(default=8, ge=2, le=60)
    seed: int = Field(default=42, ge=0, le=2147483647)
    # Cross-product pairs missing from booked matrices require explicit input.
    correlations: dict[str, float] = Field(default_factory=dict)
    hypothetical_profile: CreditProfile | None = None
    stress: dict[str, float] = Field(default_factory=dict)
    wwr: Literal["NONE", "GENERAL", "SPECIFIC", "STRESS"] = "NONE"
    credit_spread_multiplier: float = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def scope(self):
        if self.uat_batch_id is not None and self.data_scope != "UAT":
            raise ValueError("Un lot UAT nécessite le périmètre Recette UAT")
        return self


SCHEMAS = {
    "profiles": CreditProfile, "agreements": MasterAgreement, "csas": CSAAgreement,
    "netting-sets": NettingSet, "limits": CreditLimit, "collateral": CollateralPosition,
    "overrides": CreditOverride,
}
