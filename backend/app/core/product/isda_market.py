"""Prepare raw inputs for the archived EUR RFR ISDA converter benchmark."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from ..valuation_context import canonical_fingerprint
from .models import CDSTerms, FrozenModel, Product


_BENCHMARK_ID = "isda-eur-estr-20210426"
_ARCHIVE_SHA256 = "f859e49978d6c8f6d6cc64eff3907ac67f4a1e527c7dcb720f08c09dc5e71a9a"
_WORKBOOK_SHA256 = "79efda2a2d3bdacc377da487a1807c206977a85026192e7c01deca5e9bdc7db5"
# Canonical JSON of the ordered extraction from RFR Curve!A3:C19.
_RAW_OIS_ROWS_SHA256 = "297186afc5fde016b4ec9f435afb82140194074f64ac67b53af50ef163766d47"
_TRADE_DATE = date(2021, 4, 26)
_PARIS = ZoneInfo("Europe/Paris")
_CASE_ROWS = {50: 2407, 100: 2427, 150: 2447}


class IsdaMarketError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _Provenance(FrozenModel):
    kind: Literal["published_historical_benchmark"]
    publishers: tuple[Literal["ISDA"], Literal["S&P Global"]]
    index_url: Literal["https://www.cdsmodel.com/rfr-test-grids.html"]
    archive_url: Literal["https://www.cdsmodel.com/assets/cds-model/rfr-test-grids/EUR/EUR_ESTER_20210426.zip"]
    archive_sha256: Literal[_ARCHIVE_SHA256]
    archive_size_bytes: Literal[415381]
    workbook_member: Literal["EUR_ESTER_20210426.xlsx"]
    workbook_sha256: Literal[_WORKBOOK_SHA256]
    source_access: Literal["public_download"]
    redistribution_rights: Literal["unverified"]


class _NotionalEvidence(FrozenModel):
    method: Literal["accrued_premium_divided_by_coupon_fraction_and_act_360_fraction"]
    workbook_defined_name: Literal["Notional"]
    workbook_reference: Literal["'Test Grid'!#REF!"]


class _BenchmarkContract(FrozenModel):
    instrument: Literal["CDS_SINGLE_NAME"]
    currency: Literal["EUR"]
    position: Literal["PROTECTION_BUYER"]
    coupon_bp: Literal[100]
    notional_eur: Literal[10000000]
    notional_evidence: _NotionalEvidence


class _CdsConventions(FrozenModel):
    profile: Literal["isda_standard_cds_converter"]
    specification_url: Literal[
        "https://cdsmodel.com/assets/cds-model/docs/"
        "ISDA%20Standard%20CDS%20Contract%20Converter%20Specification%20-%20Sept%204%2C%202009.pdf"
    ]
    calendar: Literal["weekdays_only"]
    premium_frequency_months: Literal[3]
    premium_day_count: Literal["ACT/360"]
    premium_payment_adjustment: Literal["Following"]
    step_in_calendar_days: Literal[1]
    initial_settlement_business_days: Literal[3]
    calibration_model: Literal["constant_hazard"]


class _CdsChronology(FrozenModel):
    trade_date: date
    initial_accrual_start_date: date
    step_in_date: date
    initial_cash_settlement_date: date
    protection_end_inclusive_date: date
    final_accrual_end_exclusive_date: date
    final_premium_payment_date: date


class _OisConventions(FrozenModel):
    profile: Literal["isda_eur_rfr_2021-04-07"]
    specification_date: date
    documentation_url: Literal["https://www.cdsmodel.com/documentation.html"]
    calendar: Literal["weekdays_only"]
    locked_rate_business_days: Literal[-1]
    spot_business_days: Literal[2]
    fixed_day_count: Literal["ACT/360"]
    payment_adjustment: Literal["Modified Following"]
    single_payment_through_tenor: Literal["1Y"]
    fixed_frequency_months_beyond_1y: Literal[12]
    interpolation: Literal["log_linear_discount_factors"]


class _OisChronology(FrozenModel):
    anchor_date: date
    locked_rate_date: date
    spot_date: date


class _OisQuote(FrozenModel):
    source_cells: str
    tenor: str
    rate: float = Field(strict=True)


class _OisQuotes(FrozenModel):
    currency: Literal["EUR"]
    index: Literal["ESTR"]
    instrument: Literal["ois_swap"]
    rate_unit: Literal["fraction"]
    source_sheet: Literal["RFR Curve"]
    source_range: Literal["A3:C19"]
    source_type_code: Literal["S"]
    source_publication_timestamp: None
    source_validation_timestamp: None = None
    intraday_eligibility: Literal["unverified"]
    readiness: Literal["raw_quotes"]
    chronology: _OisChronology
    conventions: _OisConventions
    rows: tuple[_OisQuote, ...] = Field(min_length=17, max_length=17)

    @model_validator(mode="after")
    def verify_extraction(self):
        chronology = self.chronology
        if (chronology.anchor_date, chronology.locked_rate_date, chronology.spot_date) != (
            _TRADE_DATE, date(2021, 4, 23), date(2021, 4, 28),
        ) or self.conventions.specification_date != date(2021, 4, 7):
            raise ValueError("Dates du profil OIS ISDA incompatibles avec le benchmark.")
        rows = [row.model_dump(mode="json") for row in self.rows]
        if canonical_fingerprint(rows) != _RAW_OIS_ROWS_SHA256:
            raise ValueError("Les cotes brutes OIS diffèrent de l’extraction RFR Curve!A3:C19.")
        return self


class _ScenarioColumns(FrozenModel):
    trade_date: Literal["A"]
    protection_end_inclusive_date: Literal["B"]
    currency: Literal["C"]
    coupon_bp: Literal["D"]
    quoted_spread_bp: Literal["E"]
    calibration_recovery_fraction: Literal["F"]
    clean_upfront_fraction: Literal["G"]
    cash_settlement_eur_buyer_to_seller: Literal["H"]
    clean_price_per_100: Literal["I"]
    days_accrued: Literal["J"]
    accrued_premium_eur: Literal["K"]
    initial_cash_settlement_date: Literal["L"]
    step_in_date: Literal["M"]


class _ScenarioSource(FrozenModel):
    sheet: Literal["Test Grid"]
    columns: _ScenarioColumns


class _ConversionInputs(FrozenModel):
    quote_type: Literal["quoted_spread"] = "quoted_spread"
    spread_unit: Literal["basis_points"] = "basis_points"
    quoted_spread_bp: Literal[50, 100, 150]
    calibration_recovery_fraction: float = Field(strict=True, ge=0, le=1)


class _ScenarioInput(FrozenModel):
    id: str
    source_cells: str
    market_inputs: _ConversionInputs

    @model_validator(mode="after")
    def verify_source_row(self):
        spread = self.market_inputs.quoted_spread_bp
        row = _CASE_ROWS[spread]
        if (
            self.id != f"{_BENCHMARK_ID}-{spread}bp"
            or self.source_cells != f"A{row}:M{row}"
            or self.market_inputs.calibration_recovery_fraction != 0.4
        ):
            raise ValueError("Identité, cellules ou cote du scénario CDS ISDA incohérentes.")
        return self


class _WorkbookOracle(FrozenModel):
    clean_upfront_fraction: float = Field(strict=True)
    cash_settlement_eur_buyer_to_seller: float = Field(strict=True)
    clean_price_per_100: float = Field(strict=True)
    days_accrued: float = Field(strict=True, ge=0)
    accrued_premium_eur: float = Field(strict=True, ge=0)


class _ArchivedScenario(_ScenarioInput):
    workbook_results: _WorkbookOracle


class _OracleTolerances(FrozenModel):
    cash_eur: float = Field(strict=True, gt=0)
    upfront_pct_of_notional_points: float = Field(strict=True, gt=0)
    clean_price_per_100_points: float = Field(strict=True, gt=0)


class _BenchmarkEvidence(FrozenModel):
    kind: Literal["isda"] = "isda"
    policy: Literal["historical_isda_benchmark"]
    fixture_version: Literal[1]
    benchmark_id: Literal[_BENCHMARK_ID]
    provenance: _Provenance
    contract_terms: _BenchmarkContract
    cds_conventions: _CdsConventions
    cds_chronology: _CdsChronology
    ois_quotes: _OisQuotes
    scenario_source: _ScenarioSource

    @model_validator(mode="after")
    def verify_chronology(self):
        chronology = self.cds_chronology
        if (
            chronology.trade_date, chronology.initial_accrual_start_date, chronology.step_in_date,
            chronology.initial_cash_settlement_date, chronology.protection_end_inclusive_date,
            chronology.final_accrual_end_exclusive_date, chronology.final_premium_payment_date,
        ) != (
            _TRADE_DATE, date(2021, 3, 22), date(2021, 4, 27), date(2021, 4, 29),
            date(2026, 6, 20), date(2026, 6, 21), date(2026, 6, 22),
        ):
            raise ValueError("Dates contractuelles incompatibles avec la grille CDS ISDA.")
        return self


class IsdaMarket(_BenchmarkEvidence):
    """Raw archive evidence and the scenario requested from it."""

    scenario_id: str
    scenarios: tuple[_ArchivedScenario, ...] = Field(min_length=3, max_length=3)
    comparison_tolerances: _OracleTolerances

    @model_validator(mode="after")
    def verify_scenarios(self):
        ids = {scenario.id for scenario in self.scenarios}
        if len(ids) != len(self.scenarios):
            raise ValueError("Les trois scénarios CDS ISDA doivent être distincts.")
        if self.scenario_id not in ids:
            raise ValueError("Scénario CDS ISDA inconnu.")
        return self


class IsdaMarketSelection(_BenchmarkEvidence):
    """One converter scenario with its input quote and OIS source evidence."""

    scenario: _ScenarioInput
    status: Literal["ready_for_curve_construction_and_conversion"] = "ready_for_curve_construction_and_conversion"


def _verify_product(product: Product, market: IsdaMarket | IsdaMarketSelection) -> None:
    terms, schedule = product.terms, product.native_schedule
    if not isinstance(terms, CDSTerms):
        raise IsdaMarketError("ISDA_PRODUCT_INCOMPATIBLE", "Le benchmark ISDA requiert un CDS EUR single-name.")
    if schedule is None:
        raise IsdaMarketError("ISDA_SCHEDULE_MISSING", "Échéancier CDS figé indisponible.")
    chronology = market.cds_chronology
    contract = market.contract_terms
    if (
        terms.trade_date, terms.effective_date, terms.maturity_date,
        terms.currency, terms.premium_leg.coupon_bps, product.intent.nominal,
    ) != (
        chronology.trade_date, chronology.step_in_date, chronology.protection_end_inclusive_date,
        contract.currency, contract.coupon_bp, contract.notional_eur,
    ):
        raise IsdaMarketError("ISDA_PRODUCT_INCOMPATIBLE", "Dates, devise, coupon ou nominal incompatibles avec la grille ISDA.")
    # The grid has no named reference entity, documentation or seniority quote.
    # These identifiers bind the published converter cases to the recipe Product.
    if (terms.reference_entity_id, terms.seniority, terms.documentation, terms.restructuring) != (
        "synthetic-reference", "senior", "synthetic-cds-documentation", "synthetic-clause",
    ):
        raise IsdaMarketError("ISDA_PRODUCT_INCOMPATIBLE", "Entité, séniorité ou documentation incompatibles avec le témoin ISDA.")
    conventions = market.cds_conventions
    leg_terms = terms.premium_leg
    if (
        leg_terms.calendar, leg_terms.business_day_convention, leg_terms.frequency_months,
        leg_terms.day_count, leg_terms.payment_lag_business_days, terms.step_in_lag_calendar_days,
        terms.cash_settlement_lag_business_days, terms.accrued_on_default,
    ) != (
        conventions.calendar, conventions.premium_payment_adjustment.lower(), conventions.premium_frequency_months,
        conventions.premium_day_count, 0, conventions.step_in_calendar_days,
        conventions.initial_settlement_business_days, True,
    ):
        raise IsdaMarketError("ISDA_PRODUCT_INCOMPATIBLE", "Conventions contractuelles incompatibles avec le convertisseur ISDA.")
    expected_version = product.terms_version if product.product_id is not None else None
    if (
        schedule.instrument_type != "CDS"
        or schedule.terms_fingerprint != product.terms_fingerprint
        or (schedule.product_id, schedule.terms_version) != (product.product_id, expected_version)
        or canonical_fingerprint(schedule.model_dump(mode="json", exclude={"fingerprint"})) != schedule.fingerprint
    ):
        raise IsdaMarketError("ISDA_SCHEDULE_INCOMPATIBLE", "Échéancier CDS incohérent avec la version de termes.")
    if tuple(item.kind for item in schedule.legs) != ("premium", "protection", "initial_settlement"):
        raise IsdaMarketError("ISDA_SCHEDULE_INCOMPATIBLE", "Jambes CDS incompatibles avec le profil ISDA.")
    premium, protection, upfront = schedule.legs
    if (
        premium.calendar != market.cds_conventions.calendar
        or len(premium.periods) != 21
        or premium.periods[0].accrual_start != chronology.initial_accrual_start_date
        or premium.periods[-1].accrual_end != chronology.final_accrual_end_exclusive_date
        or premium.periods[-1].payment_date != chronology.final_premium_payment_date
        or tuple((event.kind, event.date) for event in protection.events) != (
            ("step_in", chronology.step_in_date), ("protection_end", chronology.protection_end_inclusive_date),
        )
        or tuple((event.kind, event.date, event.accrued_days) for event in upfront.events) != (
            ("initial_settlement", chronology.initial_cash_settlement_date, 36),
        )
    ):
        raise IsdaMarketError("ISDA_SCHEDULE_INCOMPATIBLE", "Dates ou conventions de l’échéancier CDS incohérentes avec la grille ISDA.")


def prepare_isda_market(product: Product, valuation_date: date, cutoff: datetime,
                        market: IsdaMarket | IsdaMarketSelection) -> IsdaMarketSelection:
    """Select the requested archived input row without assuming intraday eligibility."""
    if cutoff.utcoffset() is None:
        raise IsdaMarketError("ISDA_CUTOFF_INVALID", "Le cut-off du benchmark ISDA doit indiquer son fuseau horaire.")
    if valuation_date != market.ois_quotes.chronology.anchor_date:
        raise IsdaMarketError("ISDA_DATE_INCOMPATIBLE", "Le benchmark ISDA est réservé à sa date historique de valorisation.")
    if cutoff.astimezone(_PARIS).date() != valuation_date:
        raise IsdaMarketError("ISDA_CUTOFF_INVALID", "Le cut-off doit tomber le jour de valorisation en Europe/Paris.")
    _verify_product(product, market)
    if isinstance(market, IsdaMarketSelection):
        return market
    archived = next(item for item in market.scenarios if item.id == market.scenario_id)
    scenario = _ScenarioInput(
        id=archived.id, source_cells=archived.source_cells, market_inputs=archived.market_inputs,
    )
    return IsdaMarketSelection(
        **market.model_dump(exclude={"scenario_id", "scenarios", "comparison_tolerances"}),
        scenario=scenario,
    )
