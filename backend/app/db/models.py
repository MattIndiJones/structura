from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text


class Entity(SQLModel, table=True):
    __tablename__ = "entities"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="user")          # "admin" | "user"
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReferenceCounter(SQLModel, table=True):
    """Atomic allocator state for externally visible business references."""
    __tablename__ = "reference_counters"
    prefix: str = Field(primary_key=True)
    last_value: int = Field(default=0)


class AdminAuditLog(SQLModel, table=True):
    """Append-only trace of privileged corrections made through Admin."""
    __tablename__ = "admin_audit_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    table_key: str = Field(index=True)
    row_id: int = Field(index=True)
    action: str = Field(default="update")
    before_json: str = Field(default="{}", sa_column=Column(Text))
    after_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Folder(SQLModel, table=True):
    __tablename__ = "folders"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    parent_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    user_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Portfolio(SQLModel, table=True):
    """A user-defined named bucket of deals, for aggregating risk (see
    api/portfolios.py). A deal belongs to exactly one portfolio at all times
    — no association table, just Deal.portfolio_id, never NULL: risk must
    always be monitored somewhere. Each user gets one is_default=True
    portfolio (auto-created, never deletable) that catches deals not
    explicitly filed elsewhere."""
    __tablename__ = "portfolios"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    user_id: int = Field(foreign_key="users.id")
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Script(SQLModel, table=True):
    __tablename__ = "scripts"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = Field(default="")
    folder_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    user_id: int = Field(foreign_key="users.id")
    script_text: str = Field(default="")
    params_json: str = Field(default="{}")        # paramOverrides
    constats_json: str = Field(default="{}")      # constatOverrides (raw values)
    global_params_json: str = Field(default="{}")  # r, T, model, underlyings, etc.
    category: str = Field(default="")
    tags: str = Field(default="")                 # comma-separated
    is_shared: bool = Field(default=False)        # visible to same entity members
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Deal(SQLModel, table=True):
    __tablename__ = "deals"
    id: Optional[int] = Field(default=None, primary_key=True)
    # Unique: the reference is the trade's business identity (valuation notes,
    # KID, client correspondence). Handed out by core/references.py, which
    # numbers off the highest suffix rather than the row count so deleting one
    # never frees a number for reuse. Existing databases get the constraint as
    # an index in db/database.py:_migrate.
    reference: str = Field(index=True, unique=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    user_id: int = Field(foreign_key="users.id")

    # Pre-trade opportunity this deal was booked from, if any — a permanent
    # backward pointer. Indicative-stage KID/EMT records stay attached to
    # indicative_id forever (never re-keyed); this is the only link needed
    # to retrieve them alongside the booked deal's own documents.
    indicative_id: Optional[int] = Field(default=None, foreign_key="indicatives.id")

    # Same idea, for a deal booked from a competitive RFQ's winning quote
    # (see api/rfq.py selected_quote_id) — set at booking time, never re-keyed.
    # A competitive tender can execute into one and only one deal. SQLite
    # permits multiple NULLs in a unique index, so non-RFQ bookings are not
    # affected.
    rfq_id: Optional[int] = Field(
        default=None, foreign_key="rfq_requests.id", unique=True)

    # Frozen best-execution record: who was in competition, at what prices,
    # what our model said, and what we actually traded — captured at booking
    # (api/deals.py:book_deal). rfq_id alone doesn't survive as evidence: the
    # RFQ stays editable afterwards (a price corrected, a quote deleted), so
    # the justification of THIS trade has to be a snapshot, not a live join.
    # None for a deal booked outside any tender.
    rfq_provenance_json: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Risk-aggregation grouping (api/portfolios.py) — one portfolio at a time,
    # reassignable. Always set going forward (book_deal assigns the user's
    # default portfolio at creation); column stays nullable only so a
    # pre-existing db can be backfilled once at boot (see
    # database.py:_backfill_default_portfolios).
    portfolio_id: Optional[int] = Field(default=None, foreign_key="portfolios.id")

    # Script frozen at booking time
    script_snapshot: str = Field(default="", sa_column=Column(Text))
    script_id: Optional[int] = Field(default=None, foreign_key="scripts.id")

    # Deal economics
    # Written from the COUNTERPARTY's point of view — "vente" means the bank
    # sells, so we are the buyer and hold the product long. Deliberately the
    # opposite convention to RfqRequest.sens (our own side); the two are
    # inverted when a deal is booked from an RFQ. See position_sign().
    sens: str = Field(default="vente")         # "achat" | "vente"
    contrepartie: str = Field(default="")
    devise: str = Field(default="EUR")
    nominal: float = Field(default=0.0)
    fair_value: float = Field(default=0.0)     # % at booking time
    price_traded: float = Field(default=0.0)   # % actually traded
    # Free-text family (e.g. "Autocall Athena", "Reverse Convertible") — set
    # at booking time, used to classify/filter the Booking view. No formal
    # link to Script.tags — a deal booked from an unsaved ad-hoc script has
    # nothing to inherit tags from, so this stays a plain field on the deal.
    product_type: str = Field(default="")

    # Dates (ISO strings)
    trade_date: str = Field(default="")
    strike_date: str = Field(default="")
    value_date: str = Field(default="")
    maturity_date: str = Field(default="")
    payment_date: str = Field(default="")
    T: float = Field(default=0.0)
    # Total cash flow actually realized (fraction of nominal), computed once
    # the deal resolves (callé/échu) — see api/deals.py:_evaluate_lifecycle.
    # None while still actif.
    realized_payout: Optional[float] = Field(default=None)
    # Mirrors the terminal event's status ("callé" | "ki" | "final") once
    # resolved — lets the Booking view compute a hit-ratio straight from the
    # deal list, no per-deal events fetch needed. None while still actif.
    resolution_outcome: Optional[str] = Field(default=None)

    # JSON blobs
    underlyings_json: str = Field(default="[]", sa_column=Column(Text))   # [{name, ticker, s0_abs}]
    market_snapshot_json: str = Field(default="{}", sa_column=Column(Text))

    # Last computed Greeks (bump-and-reprice, see api/deals.py POST /{id}/greeks) —
    # overwritten at each recompute, no history kept. None while never computed.
    greeks_json: str = Field(default="{}", sa_column=Column(Text))
    greeks_computed_at: Optional[datetime] = Field(default=None)

    status: str = Field(default="actif")  # actif | callé | échu | résilié

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    user_id: int = Field(foreign_key="users.id")
    doc_type: str = Field(default="")   # kid | termsheet_indicatif | termsheet_final | confirmation | autre
    title: str = Field(default="")
    filename: str = Field(default="")
    file_path: str = Field(default="")  # path relative to data/documents/
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata_json: str = Field(default="{}", sa_column=Column(Text))


class AmcStudy(SQLModel, table=True):
    __tablename__ = "amc_studies"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    isin: str = Field(default="", index=True)
    product_name: str = Field(default="")
    label: str = Field(default="")
    folder: str = Field(default="")
    manifest_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    synthese_text: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Indicative(SQLModel, table=True):
    """A pre-trade pricing opportunity — exists before any Deal does.

    Holds its own frozen script/market snapshot exactly like Deal does, so
    KID/EMT generated during client discussion have something stable to
    attach to. If it converts to a trade, the resulting Deal points back via
    Deal.indicative_id — this row's id never changes and nothing here is
    ever re-keyed.
    """
    __tablename__ = "indicatives"
    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(index=True, unique=True)   # see Deal.reference
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    user_id: int = Field(foreign_key="users.id")

    script_snapshot: str = Field(default="", sa_column=Column(Text))
    script_id: Optional[int] = Field(default=None, foreign_key="scripts.id")

    contrepartie: str = Field(default="")
    devise: str = Field(default="EUR")
    nominal: float = Field(default=0.0)

    underlyings_json: str = Field(default="[]", sa_column=Column(Text))
    market_snapshot_json: str = Field(default="{}", sa_column=Column(Text))

    status: str = Field(default="ouvert")  # ouvert | converti | abandonné

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class KidRecord(SQLModel, table=True):
    """One immutable KID PRIIPs computation. Never updated in place — each
    regeneration (required at least annually under PRIIPs) is a new row, so
    what was shown to a client at a given date stays reconstructable.
    Attached to exactly one of indicative_id / deal_id, whichever exists at
    generation time."""
    __tablename__ = "kid_records"
    id: Optional[int] = Field(default=None, primary_key=True)
    indicative_id: Optional[int] = Field(default=None, foreign_key="indicatives.id")
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    user_id: int = Field(foreign_key="users.id")

    product_title: str = Field(default="")
    sri: int = Field(default=0)
    mrm: int = Field(default=0)
    crm: int = Field(default=0)
    # None is meaningful: a total-loss first percentile has no finite VEV,
    # while its market-risk class is forced to 7.
    vev: Optional[float] = Field(default=None)
    t_rhp: float = Field(default=0.0)
    horizons_json: str = Field(default="[]", sa_column=Column(Text))
    costs_json: str = Field(default="{}", sa_column=Column(Text))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class EmtRecord(SQLModel, table=True):
    """One immutable EMT / target-market computation — same append-only
    logic as KidRecord. sri/mrm/crm are copied from the KidRecord it was
    generated from (see emt.py), never recomputed independently."""
    __tablename__ = "emt_records"
    id: Optional[int] = Field(default=None, primary_key=True)
    indicative_id: Optional[int] = Field(default=None, foreign_key="indicatives.id")
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    user_id: int = Field(foreign_key="users.id")

    product_title: str = Field(default="")
    sri: int = Field(default=0)
    mrm: int = Field(default=0)
    crm: int = Field(default=0)
    t_rhp: float = Field(default=0.0)

    capital_tier: str = Field(default="")
    capital_label: str = Field(default="")
    knowledge_tier: str = Field(default="")
    knowledge_label: str = Field(default="")
    risk_tolerance: str = Field(default="")
    objective: str = Field(default="")
    features_json: str = Field(default="{}", sa_column=Column(Text))

    client_type: str = Field(default="retail")
    distribution: str = Field(default="advice")
    negative_target_market: str = Field(default="", sa_column=Column(Text))
    description: str = Field(default="", sa_column=Column(Text))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class RfqRequest(SQLModel, table=True):
    """A request for quote sent to one or more counterparty banks for a
    structured product. Mirrors Deal/Indicative: script frozen at creation
    time (template snapshot or copied from an existing Script), never
    re-keyed. Individual bank responses live in RfqQuote."""
    __tablename__ = "rfq_requests"
    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(index=True, unique=True)   # see Deal.reference
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    user_id: int = Field(foreign_key="users.id")

    name: str = Field(default="")
    ao_date: str = Field(default="")  # ISO date — when the tender was actually sent, distinct from created_at
    # indicatif: quick price check to fine-tune an idea, no trade expected —
    #   Normal-mode scripts, created from a no-code template or a saved script.
    # to_trade: meant to actually execute — must parse and reference a real
    #   CONSTAT calendar (Expert mode) for the precision an actual trade needs;
    #   see api/rfq.py create_rfq. It may originate from the script library,
    #   an expert template, or a previously booked deal snapshot.
    kind: str = Field(default="indicatif")  # indicatif | to_trade
    # Our own side of the trade — deliberately NOT the same convention as
    # Deal.sens, which is written from the counterparty's point of view
    # ("Vente (banque vend)"). Here 'achat' means WE buy from the solicited
    # providers, the normal direction for this module (they're "fournisseurs"),
    # hence the default. It decides which response wins the tender — cheapest
    # when we buy, richest when we sell — so it drives bestQuote and the
    # favourable/unfavourable colouring in RfqView.vue, and gets INVERTED when
    # prefilling Deal.sens at booking (see pricing.js:loadFromRfq).
    sens: str = Field(default="achat")  # achat | vente (côté Structura)
    template_type: str = Field(default="")
    script_id: Optional[int] = Field(default=None, foreign_key="scripts.id")
    script_snapshot: str = Field(default="", sa_column=Column(Text))
    params_json: str = Field(default="{}", sa_column=Column(Text))

    model_price: Optional[float] = Field(default=None)
    model_price_at: Optional[datetime] = Field(default=None)

    # draft | envoye | quote | retenue | clos | sans_suite.
    # Derived server-side from the tender's own facts on every mutation (see
    # api/rfq.py _derive_status) — never posed by the caller, except the two
    # terminal states: "clos" by book_deal, "sans_suite" (AO abandoned/lost,
    # the majority of them) by the desk via PATCH.
    status: str = Field(default="draft")

    # The quote the desk has decided to trade on — set via
    # PATCH /rfq/{id} {selected_quote_id}, which is what makes the derived
    # status "retenue". Points at either a top-level quote or a last-look child
    # (RfqQuote.parent_quote_id) — whichever price/time actually got traded.
    selected_quote_id: Optional[int] = Field(default=None, foreign_key="rfq_quotes.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RfqQuote(SQLModel, table=True):
    __tablename__ = "rfq_quotes"
    id: Optional[int] = Field(default=None, primary_key=True)
    rfq_id: int = Field(foreign_key="rfq_requests.id", index=True)
    provider: str = Field(default="manuel")
    contact: Optional[str] = Field(default=None)
    price: Optional[float] = Field(default=None)
    currency: Optional[str] = Field(default=None)
    status: str = Field(default="en_attente")  # en_attente | recu | decline | expire
    note: Optional[str] = Field(default=None)
    quoted_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Last look: this provider (often the one who originated the idea) gets
    # a chance to match the best competing price, or keep the deal at their
    # own price if close enough, after seeing the field. Setting this True
    # spawns a child RfqQuote (same provider, parent_quote_id = this row's
    # id) with its own fresh price/quoted_at — the re-quote itself. Both
    # rows stay visible: the original response is kept for the record next
    # to the last-look counter-quote (see api/rfq.py update_quote).
    last_look: bool = Field(default=False)
    parent_quote_id: Optional[int] = Field(default=None, foreign_key="rfq_quotes.id")


class Counterparty(SQLModel, table=True):
    """Admin-managed catalog of counterparties eligible to face a booked
    deal. Deal.contrepartie stores the name directly (free string, not a FK)
    — same rationale as RfqProvider: booked history stays readable if a
    counterparty is later renamed or removed from the eligible list.

    limit_eur is an optional soft concentration limit (nominal EUR-converted
    across every active deal facing this counterparty) — set by an admin,
    read by the Risk Management "Contreparties" exposure view
    (api/portfolios.py:exposure-by-counterparty) to flag a breach. None means
    no limit configured (no breach ever flagged), not a zero limit."""
    __tablename__ = "counterparties"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    country: str = Field(default="")
    active: bool = Field(default=True)
    limit_eur: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RfqProvider(SQLModel, table=True):
    """Admin-managed catalog of RFQ counterparties. RfqQuote.provider stores
    the label directly (free string, not a FK) so historical quotes stay
    readable even if a provider is later renamed or deleted."""
    __tablename__ = "rfq_providers"
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    mode: str = Field(default="manual")  # manual | api
    active: bool = Field(default=True)
    # Which eligible counterparty a deal booked out of this provider's quote
    # actually faces. Optional and NOT a hard identity: a quoting channel is
    # not always the legal entity the trade ends up with (a platform such as
    # deritrade quotes, the issuing bank faces the trade). Left unset, the
    # booking prefill can only fall back to matching labels between the two
    # admin catalogs, and refuses to prefill a counterparty it can't find —
    # see api/rfq.py _counterparty_by_provider and DealTab.vue.
    counterparty_id: Optional[int] = Field(default=None, foreign_key="counterparties.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Alert(SQLModel, table=True):
    """Lifecycle/barrier alert raised by the daily refresh (or the manual
    'Rafraîchir le book' action) — see services/lifecycle_alerts.py.
    dedup_key guarantees at most one alert per logical fact (one per deal
    resolution, one per barrier crossing) no matter how many runs re-detect
    it; deal_reference is denormalized so the alert stays readable even if
    the deal is later deleted."""
    __tablename__ = "alerts"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    deal_reference: str = Field(default="")
    kind: str = Field(default="")   # callé | ki | final | barrier_ki | barrier_ac
    message: str = Field(default="", sa_column=Column(Text))
    dedup_key: str = Field(default="", index=True)
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


def position_sign(deal: "Deal") -> float:
    """+1 if we hold the product, -1 if we sold it.

    `Deal.sens` is written from the bank's side: "vente" = the bank sells =
    we bought = long. Every risk aggregate — Greeks, shocked MtM, VaR
    scenarios — must carry this sign, or a hedge adds to the exposure it was
    put on to offset instead of cancelling it.

    Raises on anything else rather than defaulting: a silent `else` branch on a
    mistyped sens is exactly how the RFQ module ended up reading every trade
    backwards, and a risk number that is merely negated looks entirely
    plausible."""
    if deal.sens == "vente":
        return 1.0
    if deal.sens == "achat":
        return -1.0
    raise ValueError(
        f"Sens de position inconnu sur le deal {deal.reference!r} : {deal.sens!r} — "
        f"valeurs admises : 'vente' (la banque vend, nous sommes acheteurs) ou "
        f"'achat' (la banque achète, nous sommes vendeurs)."
    )


class DealEvent(SQLModel, table=True):
    __tablename__ = "deal_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    event_index: int = Field(default=0)
    event_date: str = Field(default="")    # ISO calendar date
    t_years: float = Field(default=0.0)    # time from value_date in years
    spots_json: str = Field(default="{}")  # {underlying_name: spot_value}
    source: str = Field(default="pending") # pending | auto | manuel
    status: str = Field(default="futur")   # futur | observé | callé | ki | final | annulé
    label: str = Field(default="")


class ShockRun(SQLModel, table=True):
    """One market-shock scenario (spot/vol/rate/corr, full reprice — see
    api/shocks.py) played against a deal or a portfolio. Append-only, same
    immutable-history pattern as KidRecord/EmtRecord — a shock's parameters
    can change on the next run, so past runs stay reconstructable rather than
    overwritten."""
    __tablename__ = "shock_runs"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    scope: str = Field(default="deal")   # "deal" | "portfolio" | "global"
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    portfolio_id: Optional[int] = Field(default=None, foreign_key="portfolios.id")
    label: str = Field(default="")
    params_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ComputeBatch(SQLModel, table=True):
    """One submission to the generic parallel compute module
    (core/compute/) — a set of independent jobs, all processed by the same
    pricer (`kind`), executed by a worker daemon (scripts/run_compute_worker.py)
    that polls this table. Mirrors ShockRun's persistence intent (a run's
    inputs/outputs stay reconstructable) but adds a full queued → running →
    terminal lifecycle instead of append-only, since a batch (unlike a
    single shock) can take long enough to need polling from the caller.

    First consumer in mind: a VaR/ES study (chantier #2) submits one batch
    per method (historical/parametric), one job per market scenario — but
    nothing here is VaR-specific; `kind` + each job's own payload_json is
    where the actual meaning lives (see core/compute/pricers/)."""
    __tablename__ = "compute_batches"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str = Field(default="")   # selects the pricer in core/compute/pricers/PRICERS
    label: str = Field(default="")
    status: str = Field(default="queued")  # queued | running | completed | completed_with_failures | failed
    total_jobs: int = Field(default=0)
    completed_jobs: int = Field(default=0)
    failed_jobs: int = Field(default=0)
    params_json: str = Field(default="{}", sa_column=Column(Text))            # batch-level config (max_workers, executor kind...)
    result_summary_json: str = Field(default="{}", sa_column=Column(Text))    # kind-specific aggregation, filled by the caller once every job is in a terminal state
    worker_name: Optional[str] = Field(default=None)   # host-pid of whichever worker last claimed this batch
    claimed_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ComputeJob(SQLModel, table=True):
    """One independent unit of work inside a ComputeBatch — payload_json is
    pure data (never a live Python object): on ProcessPoolExecutor (the
    default — see core/compute/executor.py for why threads don't help the
    PayScript engine), a job payload crosses a real process boundary via
    pickle, so anything not JSON-plain (a CompiledScript's exec()-produced
    closures, in particular) can never be part of it — only script TEXT and
    market data, recompiled fresh in the worker."""
    __tablename__ = "compute_jobs"
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="compute_batches.id", index=True)
    job_index: int = Field(default=0)      # order within the batch, stable regardless of completion order
    label: str = Field(default="")         # human-readable (e.g. a historical scenario's date, a deal reference)
    payload_json: str = Field(default="{}", sa_column=Column(Text))
    status: str = Field(default="queued")  # queued | done | failed
    result_json: str = Field(default="{}", sa_column=Column(Text))
    error: Optional[str] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
