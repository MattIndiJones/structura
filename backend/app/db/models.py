from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import UniqueConstraint
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


class AuditEvent(SQLModel, table=True):
    """Append-only business audit trail for critical workflow decisions."""
    __tablename__ = "audit_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(index=True)
    object_type: str = Field(index=True)
    object_id: Optional[int] = Field(default=None, index=True)
    actor_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    actor_type: str = Field(default="USER")       # USER | PROCESS | SYSTEM
    result: str = Field(default="SUCCESS", index=True)  # SUCCESS | REJECTED | ERROR
    before_json: str = Field(default="{}", sa_column=Column(Text))
    after_json: str = Field(default="{}", sa_column=Column(Text))
    reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    data_source: Optional[str] = Field(default=None)
    correlation_id: Optional[str] = Field(default=None, index=True)
    metadata_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class UatGenerationBatch(SQLModel, table=True):
    """Admin-created, reproducible RFQ/deal test-data lot.

    Generated rows carry this batch id, which is the only deletion boundary:
    ordinary business data can never be swept by a reference-prefix purge.
    The row itself is retained after cleanup so the operator history remains
    auditable.
    """
    __tablename__ = "uat_generation_batches"
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_key: str = Field(unique=True, index=True)
    label: str = Field(default="")
    created_by: int = Field(foreign_key="users.id", index=True)
    target_user_id: int = Field(foreign_key="users.id", index=True)
    mode: str = Field(index=True)  # RFQ_ONLY | BOOKED_ONLY | FULL_CHAIN
    seed: int
    requested_count: int
    rfq_count: int = Field(default=0)
    deal_count: int = Field(default=0)
    status: str = Field(default="RUNNING", index=True)  # RUNNING | COMPLETED | FAILED | DELETED
    config_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    completed_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)


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
    # Provenance : un script écrit par un modèle doit rester identifiable comme
    # tel. Sur un desk, « qui a écrit ce script » est une question qui se pose,
    # et la réponse ne peut pas être perdue au premier enregistrement.
    # Vide pour tout script écrit à la main — l'écrasante majorité.
    ai_provider: str = Field(default="")          # ollama | openai | anthropic
    ai_model: str = Field(default="")
    ai_prompt: str = Field(default="")            # la description en français
    ai_generated_at: Optional[datetime] = Field(default=None)
    # ── Filiation ───────────────────────────────────────────────────
    # Une variante d'un deal existant : elle ne stocke QUE ses écarts, dans
    # variant_delta_json, et hérite tout le reste de son parent à la lecture.
    # Voir core/variants.py pour le pourquoi — en résumé : une copie ne peut pas
    # distinguer « on l'a enlevé » de « il n'y a jamais été », donc elle ne peut
    # pas afficher un retrait en grisé.
    #
    # Variantes à PLAT, un seul niveau : toutes rattachées à l'origine. Une
    # variante de variante rendrait « différent de quoi ? » ambigu et la
    # couleur illisible ; pour itérer, on duplique en sœur.
    parent_id: Optional[int] = Field(default=None, foreign_key="scripts.id", index=True)
    variant_title: str = Field(default="")
    # 'avenant' (le contrat continue, seul l'avenir change) | 'roll' (débouclage
    # et note neuve strikée aujourd'hui). Deux prix et deux économies, pas deux
    # paramétrages — cf. build_residual.
    variant_mode: str = Field(default="")
    variant_delta_json: str = Field(default="{}")


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
    # Explicit provenance for synthetic Admin data. Never inferred from the
    # visible reference, because references are labels rather than ownership.
    uat_batch_id: Optional[int] = Field(
        default=None, foreign_key="uat_generation_batches.id", index=True)

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

    # ── Rattachement commercial (Client Intelligence) ──────────────────
    # À QUI le produit a été vendu. Le reste du modèle décrit l'offre :
    # contrepartie est l'émetteur qui fait face au trade, rfq_id l'appel
    # d'offres aux banques, user_id notre commercial. Sans ces colonnes, aucun
    # trade n'est attribuable à un investisseur et le Cycle Engine n'a rien à
    # mesurer.
    #
    # Les trois sont nullables : un deal booké avant ce module, ou hors de
    # tout parcours client, reste parfaitement valide et non rattaché.
    client_id: Optional[int] = Field(default=None, foreign_key="clients.id", index=True)
    opportunity_id: Optional[int] = Field(
        default=None, foreign_key="opportunities.id", index=True)
    # L'AFFILIATION, pas la personne — c'est ce qui rend impossible qu'un trade
    # de 2024 chez Bank A devienne un trade Bank B le jour où son interlocuteur
    # change d'employeur. L'affiliation ne se réaffecte jamais.
    primary_affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    mandate_id: Optional[int] = Field(
        default=None, foreign_key="client_mandates.id", index=True)
    # Même raison d'être que rfq_provenance_json juste au-dessus : le pointeur
    # garantit la justesse, le cliché garantit la preuve. Une fiche client peut
    # être corrigée, une personne renommée, une affiliation supprimée par
    # erreur — ce qu'on a écrit au booking, lui, ne bouge plus. Porte le nom du
    # client, celui de la personne et sa fonction au moment du trade.
    client_provenance_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Attribution courante après une éventuelle rectification gouvernée. Le
    # cliché initial ci-dessus n'est jamais réécrit ; celui-ci est versionné
    # avec le contrat et ne change que via le workflow d'amendement.
    client_attribution_json: Optional[str] = Field(default=None, sa_column=Column(Text))

    # ── Structure juridique et produit ───────────────────────────────
    # Ces champs ne sont PAS commerciaux : un deal Produit autonome les porte
    # aussi. Ils sont gelés au booking et restent nullables pour tout
    # l'historique antérieur au Lot 1.
    transaction_format: Optional[str] = Field(default=None, index=True)
    instrument_family: Optional[str] = Field(default=None, index=True)
    payoff_family: Optional[str] = Field(default=None, index=True)
    payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Requis seulement lorsqu'un booking direct est volontairement rattaché à
    # un Client sans Opportunity ni RFQ. Un booking Produit autonome n'a rien à
    # justifier.
    commercial_reason: Optional[str] = Field(default=None, sa_column=Column(Text))

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
    # Frozen lifecycle policy.  Classic products use the automated Yahoo
    # unadjusted close; controlled products retain the four-eyes workflow.
    fixing_policy: str = Field(default="AUTO_YAHOO", index=True)

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

    # L'échéancier contractuel, FIGÉ au booking — voir
    # core/payscript/schedule_model.Echeancier et CONSTATATIONS_PERIODE_DESIGN.md.
    # Par constatation : sa date calendaire, son rang, sa réduction, ses relevés
    # et les blocs du script qu'elle déclenche, dans l'ordre contractuel.
    #
    # Figé, et non recalculé : les dates d'un deal booké se reconstruisaient
    # jusqu'ici à chaque valorisation depuis ses CONSTAT et son ancrage. Une
    # convention de jour ouvré modifiée, un référentiel de fériés mis à jour, ou
    # simplement un changement dans la génération de calendrier déplaçaient donc
    # rétroactivement les constatations d'un contrat déjà signé. Ce que le
    # term sheet dit ne doit dépendre d'aucun code exécuté plus tard.
    #
    # Vide sur un deal booké avant ce champ : les écrans doivent le dire plutôt
    # que d'échouer — aucune migration des anciens deals n'est prévue.
    schedule_json: str = Field(default="{}", sa_column=Column(Text))

    # Last computed Greeks (bump-and-reprice, see api/deals.py POST /{id}/greeks) —
    # overwritten at each recompute, no history kept. None while never computed.
    greeks_json: str = Field(default="{}", sa_column=Column(Text))
    greeks_computed_at: Optional[datetime] = Field(default=None)

    status: str = Field(default="actif")  # actif | callé | échu | résilié
    # Monotonic version of the operational contract row. Every governed
    # amendment snapshots both the previous and resulting version in
    # DealContractVersion; a concurrent/stale request can therefore never
    # overwrite a newer contractual state.
    contract_version: int = Field(default=1)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TradeAmendmentRequest(SQLModel, table=True):
    """Governed maker-checker request against one contract version."""
    __tablename__ = "trade_amendment_requests"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    field_name: str = Field(index=True)
    old_value_json: str = Field(default="null", sa_column=Column(Text))
    new_value_json: str = Field(default="null", sa_column=Column(Text))
    reason: str = Field(default="", sa_column=Column(Text))
    requested_by: Optional[int] = Field(default=None, foreign_key="users.id")
    status: str = Field(default="PENDING", index=True)
    base_contract_version: int = Field(default=1)
    validated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validated_at: Optional[datetime] = Field(default=None)
    decision_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    rejected_by: Optional[int] = Field(default=None, foreign_key="users.id")
    rejected_at: Optional[datetime] = Field(default=None)
    applied_by: Optional[int] = Field(default=None, foreign_key="users.id")
    applied_at: Optional[datetime] = Field(default=None)
    applied_contract_version: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class DealContractVersion(SQLModel, table=True):
    """Immutable snapshot of a booked contract version."""
    __tablename__ = "deal_contract_versions"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    version: int = Field(index=True)
    dedup_key: str = Field(unique=True, index=True)
    snapshot_json: str = Field(default="{}", sa_column=Column(Text))
    amendment_request_id: Optional[int] = Field(
        default=None, foreign_key="trade_amendment_requests.id", index=True)
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


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

    # Le besoin commercial qui a motivé ce prix, s'il est connu. Nullable :
    # un indicatif se price très bien sans dossier client, et c'était le seul
    # mode de fonctionnement avant ce module. Une opportunité porte plusieurs
    # indicatifs — on price trois idées, une seule se traite.
    opportunity_id: Optional[int] = Field(
        default=None, foreign_key="opportunities.id", index=True)

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
    uat_batch_id: Optional[int] = Field(
        default=None, foreign_key="uat_generation_batches.id", index=True)

    name: str = Field(default="")
    ao_date: str = Field(default="")  # ISO date — when the tender was actually sent, distinct from created_at
    # indicatif: quick price check to fine-tune an idea, no trade expected —
    #   Normal-mode scripts, created from a no-code template or a saved script.
    # to_trade: meant to actually execute — must parse and reference a real
    #   CONSTAT calendar (Expert mode) for the precision an actual trade needs;
    #   see api/rfq.py create_rfq. It may originate from the script library,
    #   an expert template, or a previously booked deal snapshot.
    kind: str = Field(default="indicatif")  # indicatif | to_trade
    # Le besoin client à l'origine de cet appel d'offres, s'il y en a un.
    # Nullable et sans effet sur le reste du module : une RFQ créée hors de
    # tout parcours client se comporte exactement comme avant. Le lien sert
    # à remonter Trade → RFQ → Opportunity → Client → Affiliation.
    opportunity_id: Optional[int] = Field(
        default=None, foreign_key="opportunities.id", index=True)
    # Contexte Client facultatif. Les pointeurs restent NULL sur une RFQ
    # Produit autonome. Quand une Opportunity est fournie, le serveur les
    # déduit d'elle plutôt que de faire confiance au navigateur.
    client_id: Optional[int] = Field(default=None, foreign_key="clients.id", index=True)
    mandate_id: Optional[int] = Field(
        default=None, foreign_key="client_mandates.id", index=True)
    primary_affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    commercial_context_json: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Identité juridique/produit, utilisable avec ou sans contexte Client.
    transaction_format: Optional[str] = Field(default=None, index=True)
    instrument_family: Optional[str] = Field(default=None, index=True)
    payoff_family: Optional[str] = Field(default=None, index=True)
    payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))
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
    # NULL on a legacy row means that the scalar price cannot be tied to an
    # exact input snapshot and is therefore not executable for a new booking.
    model_input_hash: Optional[str] = Field(default=None, index=True)

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
    # Optional factual explanation recorded by the desk when the retained
    # response is not the best executable price.  It never changes the quote
    # ranking and never blocks selection: an absent explanation must stay
    # visible as unknown rather than being guessed by Client Intelligence.
    selection_reason_code: Optional[str] = Field(default=None, index=True)
    selection_reason_note: Optional[str] = Field(default=None, sa_column=Column(Text))

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
    # Existing quotes migrate to UNKNOWN and require an explicit desk
    # qualification before they can be used to execute a trade.
    firmness: str = Field(default="UNKNOWN")  # UNKNOWN | INDICATIVE | FIRM
    valid_until: Optional[datetime] = Field(default=None)
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


class Underlying(SQLModel, table=True):
    """Catalogue de sous-jacents administrable.

    Cette liste vivait dans un fichier JavaScript du front : seul un
    développeur pouvait y ajouter un titre, et il fallait un rebuild. Elle est
    ici pour que l'ajout d'un sous-jacent redevienne un geste d'administration.

    Un ticker peut figurer dans PLUSIEURS groupes — BNP Paribas est à la fois
    une valeur du CAC et une banque — donc l'unicité porte sur le couple
    (ticker, groupe) et non sur le ticker seul. C'est le comportement qu'avait
    le fichier, et il rend le choix d'un sous-jacent plus rapide selon qu'on
    raisonne par indice ou par secteur.

    Le ticker est la clé Yahoo, place de cotation comprise : STMicroelectronics
    existe à Paris (STMPA.PA) et à Milan (STMMI.MI), et une note italienne fixe
    sur l'une des deux, pas sur l'autre."""
    __tablename__ = "underlyings"
    __table_args__ = (UniqueConstraint("ticker", "group_name",
                                        name="uq_underlying_ticker_group"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    label: str
    # `group` est un mot réservé SQL : la colonne s'appelle group_name, l'API
    # expose « group ».
    group_name: str = Field(default="Autres")
    ccy: str = Field(default="EUR")
    # Place de cotation telle que Yahoo la nomme (PAR, MIL, NYQ…), renseignée
    # par la recherche. Purement informative, elle aide à trancher entre deux
    # cotations du même titre.
    exchange: str = Field(default="")
    active: bool = Field(default=True)
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
    # Official/manual candidate fixing. Indicative monitoring data is stored
    # separately and can never overwrite this value.
    spots_json: str = Field(default="{}")  # {underlying_name: spot_value}
    indicative_spots_json: str = Field(default="{}", sa_column=Column(Text))
    source: str = Field(default="pending") # pending | auto | manuel
    status: str = Field(default="futur")   # futur | observé | callé | ki | final | annulé
    fixing_status: str = Field(default="EXPECTED", index=True)
    data_category: str = Field(default="UNKNOWN")
    # Pointer and denormalised summary of the current governed fixing version.
    # The immutable history lives in OfficialFixingVersion below; these fields
    # make the operational event readable without reconstructing its ledger.
    current_fixing_version_id: Optional[int] = Field(
        default=None, foreign_key="official_fixing_versions.id", index=True)
    fixing_version: int = Field(default=0)
    fixing_entered_by: Optional[int] = Field(default=None, foreign_key="users.id")
    fixing_entered_at: Optional[datetime] = Field(default=None)
    fixing_provider: Optional[str] = Field(default=None)
    fixing_source_type: Optional[str] = Field(default=None)
    fixing_external_reference: Optional[str] = Field(default=None)
    fixing_observed_at: Optional[datetime] = Field(default=None)
    fixing_venue: Optional[str] = Field(default=None)
    fixing_calendar: Optional[str] = Field(default=None)
    fixing_timezone: Optional[str] = Field(default=None)
    fixing_evidence_sha256: Optional[str] = Field(default=None)
    fixing_record_sha256: Optional[str] = Field(default=None, index=True)
    fixing_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    validated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validated_at: Optional[datetime] = Field(default=None)
    applied_at: Optional[datetime] = Field(default=None)
    label: str = Field(default="")

    # ── Constatation sur période ───────────────────────────────────────
    # Une constatation moyennée n'est pas observable directement : elle se
    # calcule depuis les cours de sa fenêtre. Ces cours-là doivent donc exister
    # comme lignes à part entière — sinon ils n'ont ni fixing officiel, ni
    # provenance, ni preuve, et l'agrégat n'est calculable depuis rien.
    #
    # `parent_event_id` non nul = cette ligne est un RELEVÉ, qui alimente la
    # réduction de la constatation qu'il désigne. Nul = c'est une constatation.
    #
    # Un relevé peut par ailleurs déclencher un bloc (`AT OBS[2][1]`) : il reste
    # alors UNE SEULE ligne, donc un seul fixing officiel pour les deux usages.
    # C'est l'invariant « aucun fixing compté deux fois », tenu par construction
    # plutôt que par vérification.
    parent_event_id: Optional[int] = Field(
        default=None, foreign_key="deal_events.id", index=True)
    # Règle d'agrégation de CETTE constatation : 'MIN' | 'MAX' | 'AVG', vide
    # pour une constatation ponctuelle ou pour un relevé.
    reduction: str = Field(default="")


class OfficialFixingVersion(SQLModel, table=True):
    """Immutable evidence record for one submitted official-fixing candidate.

    A correction always creates a new row.  The event above only points to the
    current operational version; prior values, evidence and actors are never
    overwritten or deleted.
    """
    __tablename__ = "official_fixing_versions"
    __table_args__ = (
        UniqueConstraint(
            "deal_event_id", "version", name="uq_official_fixing_event_version"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    deal_event_id: int = Field(foreign_key="deal_events.id", index=True)
    version: int = Field(index=True)
    supersedes_id: Optional[int] = Field(
        default=None, foreign_key="official_fixing_versions.id", index=True)
    status: str = Field(default="RECEIVED", index=True)
    spots_json: str = Field(default="{}", sa_column=Column(Text))
    provider: str
    source_type: str
    external_reference: str
    observed_at: datetime
    received_at: datetime = Field(default_factory=datetime.utcnow)
    venue: str
    calendar: str
    timezone: str
    evidence_sha256: str
    evidence_filename: str = Field(default="")
    evidence_content_type: str = Field(default="application/octet-stream")
    evidence_size_bytes: int = Field(default=0)
    evidence_payload_b64: str = Field(default="", sa_column=Column(Text))
    record_sha256: str = Field(index=True)
    capture_reason: str = Field(sa_column=Column(Text))
    entered_by: int = Field(foreign_key="users.id", index=True)
    # ``entered_by`` remains populated for FK/backward compatibility.  This
    # field distinguishes a human capture from an automated provider record.
    capture_actor_type: str = Field(default="USER", index=True)
    validated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validation_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    validated_at: Optional[datetime] = Field(default=None)
    rejected_by: Optional[int] = Field(default=None, foreign_key="users.id")
    rejection_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    rejected_at: Optional[datetime] = Field(default=None)
    applied_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class LifecycleProposal(SQLModel, table=True):
    """Non-binding result proposed from monitoring data.

    Validation and application are explicit separate transitions.  The
    economic result is immutable once proposed.
    """
    __tablename__ = "lifecycle_proposals"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    event_id: Optional[int] = Field(default=None, foreign_key="deal_events.id", index=True)
    dedup_key: str = Field(unique=True, index=True)
    status: str = Field(default="PROPOSED", index=True)
    proposed_outcome: str = Field(index=True)
    result_json: str = Field(default="{}", sa_column=Column(Text))
    data_source: str = Field(default="INDICATIVE")
    # Replay produced only from validated official inputs. It is frozen at
    # validation and re-hashed before application.
    official_result_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    official_input_hash: Optional[str] = Field(default=None, index=True)
    official_replayed_at: Optional[datetime] = Field(default=None)
    comparison_status: Optional[str] = Field(default=None, index=True)
    proposed_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validation_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    validated_at: Optional[datetime] = Field(default=None)
    applied_by: Optional[int] = Field(default=None, foreign_key="users.id")
    applied_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    correlation_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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


# ═══════════════════════════════════════════════════════════════════════
# Client Intelligence — la couche commerciale.
#
# Tout le reste de l'application décrit l'OFFRE : Counterparty est l'entité
# éligible à porter un deal, RfqProvider la banque qu'on sollicite,
# Deal.contrepartie l'émetteur qui fait face au trade. Rien n'y représentait
# l'investisseur final. Ces tables décrivent la DEMANDE, et se raccordent à
# l'existant par les seules colonnes ajoutées à deals/rfq_requests/indicatives.
#
# Règle structurante — les objets commerciaux pointent sur l'AFFILIATION,
# jamais sur la Person. Une affiliation lie une personne à un client sur une
# période, et ce lien ne se réécrit jamais. Un historique ne PEUT donc pas
# suivre une personne qui change d'employeur : créer l'affiliation suivante
# n'écrit rien sur la précédente. C'est une garantie de structure, pas une
# convention qu'un appelant pourrait oublier de respecter.
# ═══════════════════════════════════════════════════════════════════════


class Client(SQLModel, table=True):
    """Une organisation cliente — jamais une personne.

    Portée par l'entité, pas par l'utilisateur : deux commerciaux qui couvrent
    tous deux « ABC Asset Management » doivent voir UNE ligne, pas deux. Qui
    couvre quoi se lit dans ClientCoverage.

    constraints_json est le nom technique historique du profil courant :
    devises, formats, instruments, payoffs, univers et habitudes d'émetteurs.
    Ces informations guident le commercial mais ne bloquent aucun RFQ ni Deal.
    Une restriction opérationnelle réelle reste explicitement distinguée dans
    le référentiel. JSON plutôt que colonnes parce que le vocabulaire bouge
    avec le métier, comme market_snapshot_json ailleurs.
    """
    __tablename__ = "clients"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    name: str = Field(index=True)
    legal_name: Optional[str] = Field(default=None)
    # private_bank | asset_manager | family_office | insurance | corporate
    # | institutional | distributor | bank | other
    client_type: str = Field(default="other", index=True)
    country: Optional[str] = Field(default=None)
    # prospect | active | dormant | inactive | archived
    status: str = Field(default="prospect", index=True)
    external_ref: Optional[str] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    # demo | imported | native. Toute la base commerciale actuelle étant
    # fictive, `demo` est volontairement le défaut de migration. Le passage
    # à une donnée réelle est un geste explicite, jamais une déduction.
    data_origin: str = Field(default="demo", index=True)

    # ── Contraintes institutionnelles ─────────────────────────────────
    # Scalaires en colonnes, listes en JSON. La coupure n'est pas
    # esthétique, elle suit deux critères :
    #
    #   • ces sept-là entrent dans la question « chez quels clients cette idée
    #     est-elle cohérente avec les habitudes connues ? » et se trient dans
    #     une liste, sans jamais devenir un filtre bloquant ;
    #   • surtout, ils se modifient INDÉPENDAMMENT : deux UPDATE sur deux
    #     colonnes différentes survivent tous les deux, là où deux
    #     écritures du même blob JSON se perdent l'une l'autre en silence.
    #
    # Le second point est la vraie raison. Les listes, elles, restent en
    # JSON et sont protégées par constraints_version plus bas.
    ticket_min: Optional[float] = Field(default=None)
    ticket_max: Optional[float] = Field(default=None)
    ticket_currency: str = Field(default="EUR")
    # En MOIS, pas en années : un 18 mois doit être exprimable.
    maturity_min_months: Optional[int] = Field(default=None)
    maturity_max_months: Optional[int] = Field(default=None)
    # Échelle S&P/Fitch, comparée par rang (core/client_controls.rating_rank),
    # jamais par ordre alphabétique — 'BBB' précède 'A' dans l'alphabet.
    min_rating: Optional[str] = Field(default=None)
    max_concentration_pct: Optional[float] = Field(default=None)

    # Devises, classes d'actifs, formats, instruments, univers, payoffs,
    # habitudes d'émetteurs, références juridiques et remarques. Schéma strict
    # validé à l'écriture (client_controls.validate_constraints) : une clé
    # inconnue ou un vocabulaire hors liste est refusé, sans quoi 'A-' et
    # 'a-' coexisteraient sans que rien ne proteste.
    constraints_json: str = Field(default="{}", sa_column=Column(Text))
    # Verrou optimiste sur le blob ci-dessus. Deux utilisateurs qui éditent
    # les contraintes du même client font tous deux un lire-modifier-
    # réécrire de l'objet entier : sans ce compteur, le second écrase le
    # premier sans erreur ni trace. Même mécanisme que Deal.contract_version
    # sur les amendements, et même refus explicite plutôt qu'une perte
    # silencieuse.
    constraints_version: int = Field(default=1)

    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ClientMandate(SQLModel, table=True):
    """Mandat, fonds, compte ou desk couvert pour un Client.

    L'objet précise le périmètre d'une attribution commerciale mais ne devient
    jamais une dépendance du moteur Produit. Il s'archive lorsqu'il n'est plus
    utilisable ; les objets historiques gardent leur lien et leurs snapshots.
    """
    __tablename__ = "client_mandates"
    __table_args__ = (
        UniqueConstraint("client_id", "name", name="uq_client_mandate_name"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    # mandate | fund | account | desk | other
    mandate_type: str = Field(default="mandate", index=True)
    name: str = Field(index=True)
    # active | archived
    status: str = Field(default="active", index=True)
    reference_currency: Optional[str] = Field(default=None)
    comment: Optional[str] = Field(default=None, sa_column=Column(Text))
    # demo | imported | native
    data_origin: str = Field(default="demo", index=True)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ClientPreferenceStatement(SQLModel, table=True):
    """Append-only evidence for a declared or commercially recorded preference.

    `Client.constraints_json` remains the compatibility projection used by the
    existing form.  This table answers the questions that a current JSON blob
    cannot: who said what, for which mandate/contact, on which date, and what
    statement superseded the previous understanding.

    Rows are never updated to mark them obsolete.  The current view is derived
    deterministically from the latest effective statement for a scope/key;
    older rows therefore remain auditable without a mutable status flag.
    """
    __tablename__ = "client_preference_statements"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    mandate_id: Optional[int] = Field(
        default=None, foreign_key="client_mandates.id", index=True)
    affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    preference_key: str = Field(index=True)
    # JSON scalar/list/object, or JSON null for an explicit retraction.
    value_json: str = Field(default="null", sa_column=Column(Text))
    # client_declared | client_confirmed | client_contradicted | sales_note
    # | legacy_snapshot (system-created, explicitly undated baseline)
    statement_kind: str = Field(default="client_declared", index=True)
    statement_date: str = Field(default="", index=True)  # ISO date of the statement
    source_affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    # meeting | phone | email | other
    channel: Optional[str] = Field(default=None, index=True)
    interaction_id: Optional[int] = Field(
        default=None, foreign_key="interactions.id", index=True)
    note: Optional[str] = Field(default=None, sa_column=Column(Text))
    recorded_by_user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Person(SQLModel, table=True):
    """Une personne physique, dont l'identité ne dépend d'aucun employeur.

    Pas de client_id ici, délibérément : l'employeur du jour se lit dans
    l'affiliation ouverte (end_date IS NULL). Poser un client_id permanent
    serait exactement le raccourci qui fait basculer un historique entier
    d'une société à l'autre le jour d'un changement de poste.

    email est indexé mais PAS unique : la détection de doublons avertit, elle
    ne bloque pas. Deux homonymes existent, et une adresse peut être ressaisie
    légitimement — une contrainte dure interdirait à l'utilisateur de confirmer
    qu'il s'agit bien d'une nouvelle personne.
    """
    __tablename__ = "persons"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    first_name: str = Field(default="", index=True)
    last_name: str = Field(default="", index=True)
    email: Optional[str] = Field(default=None, index=True)
    phone: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_active: bool = Field(default=True, index=True)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Affiliation(SQLModel, table=True):
    """Le pivot historique : une personne, chez un client, sur une période.

    C'est l'objet sur lequel pointent Interaction, Opportunity et Deal. Son
    couple (person_id, client_id) est immuable après création — le corriger
    reviendrait à réécrire un passé. Une erreur de saisie se répare en
    supprimant l'affiliation tant qu'elle ne porte rien, jamais en la
    réaffectant à un autre client.

    « Actuelle » n'est pas stockée : elle se DÉDUIT de end_date IS NULL, comme
    RfqRequest.status se déduit des faits du dossier. Un booléen redondant peut
    diverger de la date qui fait foi, et la question « qui travaille ici
    aujourd'hui » n'aurait alors plus une seule réponse.

    preferences_json porte ce qui est propre à cette personne DANS cette
    société — Jean aime les autocalls, mais chez Bank B il est tenu à une
    maturité ≤ 3 ans. Les préférences durables de la personne restent sur
    Person, les contraintes de la société sur Client.constraints_json : les
    trois niveaux existent et ne doivent pas être confondus.
    """
    __tablename__ = "affiliations"
    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="persons.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    job_title: str = Field(default="")
    # decision_maker | cio | portfolio_manager | investment_advisor
    # | influencer | execution | originator | other
    commercial_role: str = Field(default="other", index=True)
    start_date: str = Field(default="")                        # ISO
    end_date: Optional[str] = Field(default=None, index=True)   # ISO ; NULL = en cours
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    preferences_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ClientCoverage(SQLModel, table=True):
    """Qui, chez nous, couvre ce client. Le client reste une identité unique ;
    seule la couverture est propre à un utilisateur."""
    __tablename__ = "client_coverage"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_client_coverage_user_client"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    # primary | secondary | read_only
    coverage_role: str = Field(default="primary", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ContactCoverage(SQLModel, table=True):
    """Qui couvre quel contact. Porte sur l'AFFILIATION et non la Person :
    deux commerciaux peuvent couvrir le même client sur des contacts
    différents — l'un le CIO, l'autre les conseillers."""
    __tablename__ = "contact_coverage"
    __table_args__ = (
        UniqueConstraint("user_id", "affiliation_id",
                         name="uq_contact_coverage_user_affiliation"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    affiliation_id: int = Field(foreign_key="affiliations.id", index=True)
    # primary | secondary | read_only
    coverage_role: str = Field(default="primary", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Interaction(SQLModel, table=True):
    """Un événement commercial daté.

    opportunity_id est nullable et le restera : une prospection initiale n'a
    aucune opportunité derrière elle, et l'exiger obligerait à ouvrir un
    dossier vide pour enregistrer un premier appel.
    """
    __tablename__ = "interactions"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)          # auteur
    client_id: int = Field(foreign_key="clients.id", index=True)
    opportunity_id: Optional[int] = Field(
        default=None, foreign_key="opportunities.id", index=True)
    interaction_date: str = Field(default="", index=True)             # ISO
    # call | meeting | email | idea_sent | client_feedback
    # | indicative_request | follow_up | other
    interaction_type: str = Field(default="other", index=True)
    summary: str = Field(default="")
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    next_action: Optional[str] = Field(default=None)
    next_action_date: Optional[str] = Field(default=None, index=True)  # ISO
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InteractionParticipant(SQLModel, table=True):
    """Les personnes présentes, désignées par leur affiliation du moment."""
    __tablename__ = "interaction_participants"
    __table_args__ = (
        UniqueConstraint("interaction_id", "affiliation_id",
                         name="uq_interaction_participant"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    interaction_id: int = Field(foreign_key="interactions.id", index=True)
    affiliation_id: int = Field(foreign_key="affiliations.id", index=True)
    role: str = Field(default="other")


class Opportunity(SQLModel, table=True):
    """Une intention d'investissement — distincte d'une RFQ et d'un Indicative.

    Un Indicative est un PRIX figé avec son script, son snapshot de marché et
    son KID ; une Opportunity est le BESOIN commercial qui a motivé ce prix.
    Un même besoin fait souvent pricer trois idées dont une seule se traite :
    les fondre écraserait cette cardinalité. Indicative.opportunity_id et
    RfqRequest.opportunity_id portent le rattachement, tous deux nullables pour
    que ces deux modules continuent de fonctionner sans client identifié.

    primary_affiliation_id est nullable : un besoin institutionnel peut arriver
    par la société sans qu'une personne en particulier le porte. Quand il est
    posé, il doit désigner une affiliation DE CE CLIENT — contrôle serveur,
    parce qu'un contrôle d'écran se contourne par un appel direct.
    """
    __tablename__ = "opportunities"
    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(index=True, unique=True)      # OPP-AAAAMMJJ-nnn
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    owner_user_id: int = Field(foreign_key="users.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    primary_affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    mandate_id: Optional[int] = Field(
        default=None, foreign_key="client_mandates.id", index=True)

    title: str = Field(default="")
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    amount: Optional[float] = Field(default=None)
    currency: str = Field(default="EUR")
    horizon: Optional[str] = Field(default=None)
    expected_trade_date: Optional[str] = Field(default=None, index=True)   # ISO
    expected_window_start: Optional[str] = Field(default=None)             # ISO
    expected_window_end: Optional[str] = Field(default=None)               # ISO
    # low | medium | high
    priority: str = Field(default="medium", index=True)
    source: Optional[str] = Field(default=None)
    # Structure envisagée. Les champs restent ouverts : l'interface propose
    # les standards, mais une valeur spécifique Client doit rester exprimable.
    transaction_format: Optional[str] = Field(default=None, index=True)
    instrument_family: Optional[str] = Field(default=None, index=True)
    payoff_family: Optional[str] = Field(default=None, index=True)
    payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    data_origin: str = Field(default="demo", index=True)
    # lead | need_identified | idea | client_interest | structuring
    # | rfq | negotiation | partially_won | won | lost | cancelled | archived
    status: str = Field(default="lead", index=True)
    # Renseignée quand le statut devient 'lost' — c'est la matière première de
    # Client Intelligence : savoir POURQUOI vaut mieux que savoir combien.
    lost_reason: Optional[str] = Field(default=None, index=True)
    lost_comment: Optional[str] = Field(default=None, sa_column=Column(Text))
    next_action: Optional[str] = Field(default=None)
    next_action_date: Optional[str] = Field(default=None, index=True)      # ISO
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_activity_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OpportunityParticipant(SQLModel, table=True):
    """Les autres personnes impliquées, hors contact principal.

    Une opportunité n'est presque jamais l'affaire d'une seule personne : le
    gérant décide, le CIO valide, le middle exécute. L'unicité empêche qu'une
    même affiliation figure deux fois ; que le contact principal n'y figure pas
    est un contrôle applicatif, la base ne voit pas cette colonne.
    """
    __tablename__ = "opportunity_participants"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "affiliation_id",
                         name="uq_opportunity_participant"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunities.id", index=True)
    affiliation_id: int = Field(foreign_key="affiliations.id", index=True)
    # originator | decision_maker | influencer | advisor | execution | other
    role: str = Field(default="other")


# ═══════════════════════════════════════════════════════════════════════
# Import d'historique commercial.
#
# Un client arrive presque toujours avec un passé stocké ailleurs — un
# classeur Excel, un export de son ancien outil. Sans lui, le moteur de
# cycles n'a rien à mesurer et dit « historique insuffisant » pendant des
# mois. Ces deux tables permettent de le verser.
# ═══════════════════════════════════════════════════════════════════════


class ClientImportBatch(SQLModel, table=True):
    """Un versement, avec de quoi le défaire.

    Chaque ligne écrite par un import porte l'identifiant de son lot. C'est
    ce qui rend un import RÉVERSIBLE : sans cela, un fichier mal formaté
    versé sur une base déjà peuplée laisserait des lignes qu'on ne saurait
    plus distinguer des vraies, et le seul remède serait de repartir d'une
    sauvegarde.

    `report_json` conserve le compte rendu tel qu'il a été montré avant la
    validation — combien de lignes lues, créées, mises à jour, ignorées, et
    pourquoi. Une reprise six mois plus tard doit pouvoir répondre à « d'où
    sort cette ligne » sans reconstituer le fichier d'origine.
    """
    __tablename__ = "client_import_batches"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    filename: str = Field(default="")
    source_format: str = Field(default="xlsx")     # xlsx | json
    status: str = Field(default="applied", index=True)  # applied | reverted
    rows_created: int = Field(default=0)
    rows_updated: int = Field(default=0)
    rows_skipped: int = Field(default=0)
    report_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reverted_at: Optional[datetime] = Field(default=None)


class ClientTradeHistory(SQLModel, table=True):
    """Une transaction passée d'un client, versée depuis un fichier.

    **Délibérément PAS un `Deal`.** Un Deal est une position que nous portons :
    il alimente le booking, l'agrégation de risque, le MtM et le cycle de vie,
    et il suppose un script, un instantané de marché et un calendrier de
    constatations. Une ligne d'historique client n'a rien de tout cela — c'est
    le fait qu'un investisseur a acheté quelque chose, souvent par un autre
    canal que nous.

    Les fondre créerait de fausses positions dans le book : exactement le
    défaut relevé sur les deals UAT, qui entrent aujourd'hui dans l'exposition
    contrepartie et le HHI sans être des trades réels. Cette table est lue par
    Client Intelligence et par personne d'autre.

    Comme un Deal rattaché, elle pointe sur l'AFFILIATION : une transaction
    faite chez Bank A en 2024 y reste, même si son auteur travaille ailleurs
    aujourd'hui.
    """
    __tablename__ = "client_trade_history"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    import_batch_id: Optional[int] = Field(
        default=None, foreign_key="client_import_batches.id", index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    affiliation_id: Optional[int] = Field(
        default=None, foreign_key="affiliations.id", index=True)
    mandate_id: Optional[int] = Field(
        default=None, foreign_key="client_mandates.id", index=True)

    trade_date: str = Field(default="", index=True)          # ISO
    maturity_date: Optional[str] = Field(default=None)       # ISO
    product_type: str = Field(default="")
    transaction_format: Optional[str] = Field(default=None, index=True)
    instrument_family: Optional[str] = Field(default=None, index=True)
    payoff_family: Optional[str] = Field(default=None, index=True)
    payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))
    underlying: Optional[str] = Field(default=None)
    issuer: Optional[str] = Field(default=None)
    currency: str = Field(default="EUR")
    notional: Optional[float] = Field(default=None)
    coupon_pct: Optional[float] = Field(default=None)
    barrier_pct: Optional[float] = Field(default=None)

    # ── Traité avec nous, ou ailleurs ? ────────────────────────────────
    # Trois états, pas deux. `None` veut dire « on ne sait pas », et c'est le
    # défaut : un historique versé qui ne le précise pas ne doit PAS être
    # présumé traité ailleurs. Le compter comme perdu gonflerait artificiellement
    # la part de marché qu'on croit ne pas avoir, et fausserait exactement la
    # lecture pour laquelle ce champ existe.
    traded_with_us: Optional[bool] = Field(default=None, index=True)
    # Prix traité, en pourcentage du nominal — même convention que
    # Deal.price_traded. Sur une ligne traitée ailleurs, c'est le renseignement
    # le plus utile du module : il dit à quel niveau la concurrence a servi.
    price_pct: Optional[float] = Field(default=None)

    external_ref: Optional[str] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConstraintDefinition(SQLModel, table=True):
    """Un champ du profil déclaré — par l'admin, ou pour un client précis.

    Le profil se stocke dans le blob historique `constraints_json` sur `Client`, et
    `validate_constraints` refuse toute clé qu'aucune définition ne décrit.
    Cette table est ce qui rend le refus extensible sans le rendre laxiste : une
    clé devient connue parce qu'elle a été DÉCLARÉE, jamais parce qu'elle a été
    envoyée.

    `client_id` porte toute la nuance du besoin. Nul, le champ vaut pour toute
    la maison — un vocabulaire interne, une catégorie suivie partout.
    Renseigné, c'est un nom convenu entre l'utilisateur et ce client-là : sa
    « poche défensive », sa « limite Rouge ». Ce vocabulaire n'a de sens que
    dans cette relation ; le proposer aux autres clients serait du bruit, et le
    ranger dans un champ de notes le rendrait illisible par le module.

    Rien n'est jamais supprimé, seulement `archived` : la valeur déjà saisie
    chez un client survivrait à la définition, et la validation suivante la
    refuserait comme clé inconnue.
    """
    __tablename__ = "constraint_definitions"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id", index=True)
    # Nul = toute l'entité. Renseigné = ce client seulement.
    client_id: Optional[int] = Field(default=None, foreign_key="clients.id", index=True)

    key: str = Field(index=True)              # snake_case, jamais renommée
    label: str                                 # libellé français affiché
    kind: str = Field(default="text")          # cf. client_constraints_ref.KINDS
    options_json: str = Field(default="[]")    # list_enum : les valeurs admises
    catalog: Optional[str] = Field(default=None)   # underlyings, counterparties…
    unit: Optional[str] = Field(default=None)
    help_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    free_entry: bool = Field(default=True)

    archived: bool = Field(default=False, index=True)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
