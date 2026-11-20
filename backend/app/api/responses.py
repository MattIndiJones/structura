"""What the most used routes return (P1-11, A4).

The twenty routes with the most calls in real use (access log of the Admin
workspace, 3–19/11/2026), plus the pricing job routes the Pricer now goes
through. Each model describes the response as the route builds it today; see
api/contracts.py for how the description is checked and why it does not
change the response itself.

Conventions: a field the route always writes is required; a field written
only in some cases, or read from a nullable column, has a default. Nested
blocks whose content belongs to the pricing engine (distributions, flow
tables, calibration dossiers) are typed as objects, not unfolded.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from .contracts import Contract, OpenContract

Json = dict[str, Any]


# ── Calendars and schedules ─────────────────────────────────────────────

class CalendarCatalog(Contract):
    codes: list[str]
    observation_codes: list[str]
    settlement_codes: list[str]
    joins: list[str]


class GeneratedSchedule(Contract):
    first_is_observation: bool
    main_dates: list[str]
    dates: list[str]
    raw_dates: list[str]
    payment_dates: list[str]
    year_fractions: list[float]


class ResolvedBusinessDay(Contract):
    date: str
    source: str
    moved: bool
    payment_date: str


# ── Volatility assumptions ──────────────────────────────────────────────

class ValidatedSurface(Contract):
    surface: Json
    certificate: Json


class LeftWingAdjustment(Contract):
    surface: Json
    achieved: Optional[float] = None
    reason: Optional[str] = None
    changed: bool


class SmileCalibration(OpenContract):
    """calibrate_surface's result, plus its signed evidence."""
    dossier: Json
    calibration_evidence: Json


# ── Market data ─────────────────────────────────────────────────────────

class HistoricalPrices(OpenContract):
    """Closes per ticker on common dates, or an error. The provenance of the
    history (provider, price type, storage, gaps) follows the source."""
    dates: Optional[list[str]] = None
    prices: Optional[dict[str, list[Optional[float]]]] = None
    error: Optional[str] = None


class RealizedMarket(OpenContract):
    """Realized volatility, dividends and correlation at a date, or an error.
    The history's provenance fields are carried over as they come."""
    tickers: Optional[list[str]] = None
    vols: Optional[dict[str, float]] = None
    div_yields: Optional[dict[str, float]] = None
    dividend_profiles: Optional[dict[str, Any]] = None
    missing_dividends: Optional[list[str]] = None
    corr: Optional[dict[str, dict[str, float]]] = None
    period: Optional[str] = None
    window_days: Optional[int] = None
    n_obs: Optional[int] = None
    requested_asof: Optional[str] = None
    estimator: Optional[Json] = None
    error: Optional[str] = None


class UnderlyingItem(Contract):
    ticker: str
    label: str
    ccy: str
    asset_class: str


class UnderlyingGroup(Contract):
    group: str
    items: list[UnderlyingItem]


# ── Account ─────────────────────────────────────────────────────────────

class WorkbenchOptions(Contract):
    admin_workbench: bool
    development_admin_enabled: bool
    platform_url: Optional[str] = None


class LoginOptions(WorkbenchOptions):
    registration_enabled: bool


class CurrentUser(WorkbenchOptions):
    id: int
    username: str
    email: str
    password_change_required: bool
    role: str
    entity_id: Optional[int] = None
    profile: str
    capabilities: list[str]
    installation: Optional[Json] = None
    developer_access: bool
    developer_origin: Optional[Json] = None
    amendment_four_eyes: bool
    read_only: bool
    consultation: Optional[Json] = None


# ── Alerts, studies, trading relationships ──────────────────────────────

class AlertRow(Contract):
    id: int
    deal_id: Optional[int] = None
    deal_reference: str
    kind: str
    message: str
    read: bool
    created_at: str


class AlertList(Contract):
    unread: int
    alerts: list[AlertRow]


class AmcStudySummary(Contract):
    id: int
    isin: str
    product_name: str
    label: str
    folder: str
    created_at: str
    updated_at: str


class TradingRelationshipRow(Contract):
    """A relationship's version and its terms (api/trading.RelationshipTerms)."""
    id: int
    version: int
    counterparty_id: int
    reference: str
    status: Literal["PENDING", "ACTIVE", "SUSPENDED", "EXPIRED"]
    effective_date: str
    expiry_date: Optional[str] = None
    currency: str
    note_distribution_allowed: bool
    otc_allowed: bool
    documentation_reference: str
    gross_notional_limit: float
    master_agreement_id: Optional[int] = None
    csa_id: Optional[int] = None
    csa_required: bool
    settlement: Literal["DVP", "FREE_OF_PAYMENT"]
    notes: str


# ── Deals ───────────────────────────────────────────────────────────────

class EligibleCounterparty(Contract):
    id: int
    name: str
    country: Optional[str] = None


class DealRow(Contract):
    """api/deals/serializers._deal_row."""
    id: int
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    reference: str
    entity_id: Optional[int] = None
    user_id: int
    counterparty_id: Optional[int] = None
    legal_identity_exception: Optional[Json] = None
    ccr_netting_set_id: Optional[int] = None
    uat_batch_id: Optional[int] = None
    indicative_id: Optional[int] = None
    rfq_id: Optional[int] = None
    rfq_provenance: Optional[Json] = None
    client_id: Optional[int] = None
    market_data_provider: str
    opportunity_id: Optional[int] = None
    primary_affiliation_id: Optional[int] = None
    mandate_id: Optional[int] = None
    client_provenance: Optional[Json] = None
    client_attribution_current: Optional[Json] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    documentation_reference: Optional[str] = None
    commercial_reason: Optional[str] = None
    portfolio_ids: list[int]
    portfolio_id: Optional[int] = None
    sens: str
    contrepartie: str
    devise: str
    product_type: Optional[str] = None
    fixing_policy: Optional[str] = None
    nominal: float
    fair_value: float
    price_traded: float
    margin: float
    trade_date: Optional[str] = None
    strike_date: Optional[str] = None
    value_date: Optional[str] = None
    maturity_date: Optional[str] = None
    payment_date: Optional[str] = None
    risk_terminal_date: Optional[str] = None
    T: float
    realized_payout: Optional[float] = None
    settlement_amount: Optional[float] = None
    settlement_date: Optional[str] = None
    resolution_outcome: Optional[str] = None
    underlyings: list[Json]
    market_snapshot: Json
    greeks: Json
    greeks_computed_at: Optional[str] = None
    latest_valuation_run_id: Optional[int] = None
    status: str
    contract_version: Optional[int] = None
    script_id: Optional[int] = None
    script_snapshot: str
    created_at: str
    updated_at: str


class DealEventRow(Contract):
    """api/deals/serializers._event_row, with the event's fixing versions."""
    id: int
    deal_id: int
    event_index: int
    event_date: str
    t_years: float
    parent_event_id: Optional[int] = None
    reduction: Optional[str] = None
    spots: Json
    indicative_spots: Json
    source: str
    status: str
    fixing_status: str
    data_category: str
    current_fixing_version_id: Optional[int] = None
    fixing_version: Optional[int] = None
    fixing_entered_by: Optional[int] = None
    fixing_entered_at: Optional[str] = None
    fixing_provider: Optional[str] = None
    fixing_source_type: Optional[str] = None
    fixing_external_reference: Optional[str] = None
    fixing_observed_at: Optional[str] = None
    fixing_venue: Optional[str] = None
    fixing_calendar: Optional[str] = None
    fixing_timezone: Optional[str] = None
    fixing_evidence_sha256: Optional[str] = None
    fixing_record_sha256: Optional[str] = None
    fixing_reason: Optional[str] = None
    validated_by: Optional[int] = None
    validated_at: Optional[str] = None
    applied_at: Optional[str] = None
    label: str
    fixing_versions: list[Json] = []


class DealDetail(DealRow):
    events: list[DealEventRow]
    schedule: Optional[Json] = None
    frozen_schedule: Optional[Json] = None
    calendar_status: Literal["FROZEN", "UNAVAILABLE"]
    terms: Any = None
    flags: Any = None
    lifecycle_proposals: list[Json]
    amendment_requests: list[Json]


class DealMtm(OpenContract):
    """Residual MtM of a booked deal (core/deal_valuation.mtm_core), staged as
    a valuation run. Its market and provenance blocks follow the engine."""
    mtm: Optional[float] = None
    ic95: Optional[list[float]] = None
    valuation_date: Optional[str] = None
    market_used: Optional[Json] = None
    resolved_pending: Optional[bool] = None
    message: Optional[str] = None


# ── Pricing ─────────────────────────────────────────────────────────────

class InLifeEarlyRecall(Contract):
    """The replay of past closes finds the product already recalled."""
    early_recall: Literal[True]
    message: str
    T_actual: Optional[float] = None
    valuation_date: str


class InLifePrice(Contract):
    """api/inlife.price_in_life: the residual price and what produced it."""
    price: float
    valuation_context: Json
    frozen_calendar: Optional[Json] = None
    T_elapsed: float
    steps_per_year: int
    surface_context: Optional[Json] = None
    lsv_calibration: Optional[Json] = None
    lsv_frozen_leverage: Any = None
    lsv_limits: Optional[Json] = None
    time_axis: Optional[Json] = None
    barrier_monitoring: Optional[str] = None
    barrier_monitoring_note: Optional[str] = None
    barrier_monitoring_details: Any = None
    grid_notice: Optional[str] = None
    local_vol_wings: Any = None
    ic95: list[float]
    median: float
    var5: float
    prob_gt100: float
    payoffs: list[float]
    calculation_budget: Json
    elapsed_ms: float
    greeks: Optional[Json] = None
    n_paths: int
    t_max_effective: float
    flux_table: Json
    schedule: Optional[Json] = None
    n_eff: Optional[float] = None
    fugit: Optional[float] = None
    valuation_date: str
    in_life: bool
    pre_strike: bool
    variant_state_check: Any = None
    pricing_receipt: Json
    past: Json


InLifeResult = Union[InLifeEarlyRecall, InLifePrice]


class PricingJob(Contract):
    """State of an interactive pricing job (core/compute/interactive.Job.snapshot)."""
    job_id: str
    kind: str
    status: Literal["queued", "running", "done", "failed", "cancelled", "timeout", "abandoned"]
    queue_position: Optional[int] = None
    elapsed_ms: int
    result: Any = None
    status_code: Optional[int] = None
    detail: Any = None
