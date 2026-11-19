from pathlib import Path
from datetime import datetime
import bcrypt
from sqlalchemy import event, text
from sqlmodel import SQLModel, Session, create_engine, select
from .models import (
    Entity, User, Folder, Script, Deal, DealEvent, Document, AmcStudy,
    Indicative, KidRecord, EmtRecord, RfqRequest, RfqQuote, RfqProvider,
    Counterparty, Alert, Portfolio, DealPortfolioMembership, ShockRun, ComputeBatch, ComputeJob,
    AuditEvent, LifecycleProposal, TradeAmendmentRequest, DealContractVersion,
    OfficialFixingVersion, UatGenerationBatch, Underlying,
    ValuationRun, SchedulerRun,
)
from . import trading_models  # Register reusable trading tables before create_all.

from ..runtime import data_path, consultation_mode
from ..hybrid import business as hybrid_business  # Register managed bootstrap before create_all.

_DB_PATH = data_path("structura.db")
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_DATABASE_URL = (f"sqlite:///{_DB_PATH.as_uri()}?mode=ro&uri=true"
                 if consultation_mode() else f"sqlite:///{_DB_PATH}")
engine = create_engine(_DATABASE_URL, echo=False,
                        connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_integrity_pragmas(dbapi_connection, _connection_record):
    """SQLite does not enforce declared foreign keys unless enabled per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    if consultation_mode():
        cursor.execute("PRAGMA query_only=ON")
    cursor.close()


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_session():
    with Session(engine) as session:
        yield session


def _baseline():
    from .migrations import m0001_baseline
    return m0001_baseline


def _migrate():
    """The frozen baseline's schema steps, then the startup invariants.

    init_db() no longer calls this: it applies the numbered migrations once
    per database (migrations/), then the invariants. Kept for the tests that
    shape an old database by hand and bring it up to date."""
    _baseline().apply_schema_patches(engine)
    _ensure_invariants()


def _migrate_underlying_classes(conn):
    _baseline().migrate_underlying_classes(conn)


def _ensure_invariants():
    """Guarantees re-asserted at every start, unlike migrations.

    Each one repairs or completes itself: an append-only trigger dropped by
    hand comes back, an audit event inserted in raw SQL is chained, and a
    unique index refused because of duplicates is created once they are
    fixed. They run after the migrations, on the final schema."""
    from .archive_integrity import migrate as archive_triggers
    from .audit_integrity import migrate as audit_triggers_and_chain
    with engine.connect() as conn:
        archive_triggers(conn)
        audit_triggers_and_chain(conn)
        conn.commit()
        for table in ("deals", "indicatives", "rfq_requests"):
            _ensure_unique_reference(conn, table)
        _ensure_one_deal_per_rfq(conn)
        _ensure_rfq_integrity_triggers(conn)


def _ensure_unique_reference(conn, table: str) -> None:
    """References used to be numbered by counting rows, so deleting one freed
    its number for the next creation — 'RFQ-20260730-002' could exist twice.
    The generator no longer does that (core/references.py); this index makes
    the guarantee structural, including against a concurrent double-booking.

    A database that already contains duplicates is left WITHOUT the index and
    reported instead: silently renaming a reference already printed on a
    valuation note or a KID would be worse than the duplicate itself. Fix the
    offending rows (Administration → Base) and restart to get the index."""
    if not conn.execute(text(f"PRAGMA table_info({table})")).first():
        return   # table not created yet (fresh database — create_all handles it)
    dupes = conn.execute(text(
        f"SELECT reference FROM {table} GROUP BY reference HAVING COUNT(*) > 1"
    )).all()
    if dupes:
        refs = ", ".join(d[0] for d in dupes[:5]) + ("..." if len(dupes) > 5 else "")
        # ASCII on purpose: this lands in a Windows console whose codepage
        # mangles accented characters, and an unreadable warning is a warning
        # nobody acts on.
        print(f"[migrate] {table}: {len(dupes)} reference(s) en double ({refs}) - "
              f"index d'unicite NON cree. Corrigez ces doublons "
              f"(Administration > Base) puis redemarrez.")
        return
    conn.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_reference ON {table}(reference)"))
    conn.commit()


def _ensure_one_deal_per_rfq(conn) -> None:
    """Structural one-tender/one-trade invariant for upgraded databases."""
    if not conn.execute(text("PRAGMA table_info(deals)")).first():
        return
    dupes = conn.execute(text("""
        SELECT rfq_id FROM deals WHERE rfq_id IS NOT NULL
        GROUP BY rfq_id HAVING COUNT(*) > 1
    """)).all()
    if dupes:
        ids = ", ".join(str(row[0]) for row in dupes[:5])
        print(f"[migrate] deals: RFQ dupliquees ({ids}) - index unique NON cree.")
        return
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_deals_rfq_id
        ON deals(rfq_id) WHERE rfq_id IS NOT NULL
    """))
    conn.commit()


def _ensure_rfq_integrity_triggers(conn) -> None:
    """Restore FK-like checks for columns added by legacy SQLite ALTERs."""
    if not conn.execute(text("PRAGMA table_info(rfq_requests)")).first():
        return
    statements = (
        """CREATE TRIGGER IF NOT EXISTS fk_deals_rfq_insert
           BEFORE INSERT ON deals
           WHEN NEW.rfq_id IS NOT NULL AND
                NOT EXISTS (SELECT 1 FROM rfq_requests WHERE id = NEW.rfq_id)
           BEGIN SELECT RAISE(ABORT, 'rfq_id introuvable'); END""",
        """CREATE TRIGGER IF NOT EXISTS fk_deals_rfq_update
           BEFORE UPDATE OF rfq_id ON deals
           WHEN NEW.rfq_id IS NOT NULL AND
                NOT EXISTS (SELECT 1 FROM rfq_requests WHERE id = NEW.rfq_id)
           BEGIN SELECT RAISE(ABORT, 'rfq_id introuvable'); END""",
        """CREATE TRIGGER IF NOT EXISTS fk_rfq_selected_quote_update
           BEFORE UPDATE OF selected_quote_id ON rfq_requests
           WHEN NEW.selected_quote_id IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM rfq_quotes
               WHERE id = NEW.selected_quote_id AND rfq_id = NEW.id)
           BEGIN SELECT RAISE(ABORT, 'selected_quote_id hors RFQ'); END""",
    )
    for statement in statements:
        conn.execute(text(statement))
    conn.commit()


def _make_kid_vev_nullable(conn) -> None:
    _baseline().make_kid_vev_nullable(conn)


def _migrate_kid_evidence(conn):
    _baseline().migrate_kid_evidence(conn)


def _backfill_portfolio_memberships():
    _baseline().backfill_portfolio_memberships(engine)


def _backfill_rfq_statuses():
    _baseline().backfill_rfq_statuses(engine)


def _retire_four_eyes_fixing_policy():
    _baseline().retire_four_eyes_fixing_policy(engine)


def _require_simulation_bootstrap():
    """Only an explicitly isolated workshop can start without installation identity."""
    import os
    raw = os.environ.get('STRUCTURA_DATA_DIR', '')
    directory = Path(raw) if raw else None
    private_data = Path(__file__).resolve().parents[2] / 'data'
    if (os.environ.get('STRUCTURA_BOOTSTRAP_PROFILE') != 'simulation'
            or os.environ.get('STRUCTURA_WORKSHOP_CHILD') != '1'
            or directory is None or not directory.is_absolute()
            or directory.resolve() != _DB_PATH.parent.resolve()
            or directory.resolve().is_relative_to(private_data.resolve())
            or (directory / '.hybrid-retired.json').exists()):
        raise RuntimeError(
            "Installation non configurée : aucun compte par défaut n'est créé. "
            "Utilisez scripts/manage_hybrid_dev.py ou un workspace Admin configuré.")
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        for table in ('hybrid_bootstrap', 'admin_workbench_identity'):
            if table in tables and conn.execute(text(f'SELECT 1 FROM {table} LIMIT 1')).first():
                raise RuntimeError("Une base d'installation ne peut pas être démarrée comme simulation.")


def init_db():
    if (_DB_PATH.parent / ".hybrid-retired.json").exists():
        raise RuntimeError("Ancienne base fictive retirée. Démarrez les installations avec scripts/manage_hybrid_dev.py.")
    from . import migrations
    if consultation_mode():
        if not _DB_PATH.is_file():
            raise RuntimeError("Le book sauvegardé est introuvable ; consultation annulée.")
        # Read-only: nothing is migrated, but a book from a newer version is refused.
        migrations.check_compatible(engine)
        return
    from ..hybrid.config import current_config
    config = current_config()
    if config:
        if _DB_PATH.resolve() != (config.data_dir / "structura.db").resolve():
            raise RuntimeError("Le moteur SQL ne correspond pas à l'installation configurée.")
        hybrid_business.preflight(engine, config)
    from ..hybrid import admin_workbench
    workbench_config = admin_workbench.config()
    if workbench_config:
        admin_workbench.preflight(engine, workbench_config)
    if config is None and workbench_config is None:
        _require_simulation_bootstrap()
    # Before anything writes: a database migrated by a newer version stays untouched.
    migrations.check_compatible(engine)
    SQLModel.metadata.create_all(engine)
    from .rfq_transport_integrity import install_transport_guards
    install_transport_guards(engine)
    from .rfq_execution_integrity import install_execution_guards
    install_execution_guards(engine)
    migrations.upgrade(engine, backup_dir=_DB_PATH.parent / "backups" / "migrations")
    _ensure_invariants()
    report = _seed()
    _seed_rfq_providers()
    _seed_counterparties()
    _seed_underlyings()
    return report


def _seed_underlyings():
    """Initialize once, or adopt existing rows without restoring removed groups."""
    from .underlyings_seed import UNDERLYINGS_SEED, seeded_asset_class

    from .models import ReferenceCatalogState
    from ..core.audit import record_audit_event
    with Session(engine) as s:
        if s.get(ReferenceCatalogState, "underlyings"):
            return
        existing = bool(s.exec(select(Underlying.id)).first())
        if not existing:
            s.add_all([Underlying(ticker=ticker, label=label, group_name=group, ccy=ccy,
                                  asset_class=seeded_asset_class(ticker))
                       for ticker, label, group, ccy in UNDERLYINGS_SEED])
        s.add(ReferenceCatalogState(key="underlyings", adopted_existing=existing))
        record_audit_event(s, action="REFERENCE_CATALOG_INITIALIZED", object_type="UNDERLYINGS", object_id=None,
                           actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
                           after={"adopted_existing": existing}, reason="Initialisation unique ; catalogue existant conservé sans réinsertion.")
        s.commit()


def _seed():
    from ..hybrid.config import current_config
    config = current_config()
    if config:
        return hybrid_business.seed(engine, config)
    import os
    if os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") == "admin_workbench":
        from ..hybrid.admin_workbench import seed
        return seed(engine)
    _require_simulation_bootstrap()
    from ..core.simulation_bootstrap import simulation_credentials
    credentials = simulation_credentials(_DB_PATH.parent)
    with Session(engine) as s:
        # Simulation identities are registered explicitly by the workshop.
        # Never create accounts with shared, published passwords.
        if s.exec(select(Entity.id)).first() is None:
            s.add(Entity(name="Demo"))
            s.flush()
        created = 0
        if credentials:
            user = s.exec(select(User).where(User.username == credentials['username'])).first()
            if user is None:
                if s.exec(select(User.id)).first() is not None:
                    raise RuntimeError('Simulation existante sans compte technique attesté ; aucune habilitation ajoutée.')
                entity = s.exec(select(Entity).where(Entity.name == 'Demo')).one()
                s.add(User(username=credentials['username'], email=credentials['email'],
                    password_hash=_hash_pw(credentials['password']), role='admin', entity_id=entity.id))
                created = 1
            elif (not user.is_active or user.role != 'admin'
                    or not _verify_pw(credentials['password'], user.password_hash)):
                raise RuntimeError('Habilitation technique de simulation modifiée ; aucune restauration automatique.')
        s.commit()
        return {"profile": "simulation", "accounts_created": created}


def _seed_counterparties():
    """Default catalog of major international banks eligible as deal
    counterparties. Same independent-idempotency pattern as the RFQ
    providers: not gated behind _seed()'s early return so an already-seeded
    database still gets the catalog on first boot after this feature."""
    _DEFAULTS = [
        ("JP Morgan", "US"), ("Goldman Sachs", "US"), ("Morgan Stanley", "US"),
        ("Bank of America", "US"), ("Citigroup", "US"),
        ("UBS", "CH"), ("Barclays", "GB"), ("HSBC", "GB"),
        ("Deutsche Bank", "DE"), ("BNP Paribas", "FR"), ("Société Générale", "FR"),
        ("Crédit Agricole CIB", "FR"), ("Natixis", "FR"),
        ("Santander", "ES"), ("Nomura", "JP"), ("Mizuho", "JP"),
    ]
    from .models import ReferenceCatalogState
    from ..core.audit import record_audit_event
    with Session(engine) as s:
        if s.get(ReferenceCatalogState, "counterparties"):
            return
        existing = bool(s.exec(select(Counterparty.id)).first())
        if existing:
            s.add(ReferenceCatalogState(key="counterparties", adopted_existing=True))
            record_audit_event(s, action="REFERENCE_CATALOG_INITIALIZED", object_type="COUNTERPARTIES", object_id=None,
                               actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
                               after={"adopted_existing": True}, reason="Reprise explicite du catalogue existant, sans restauration automatique.")
            s.commit()
            return
        for name, country in _DEFAULTS:
            s.add(Counterparty(name=name, country=country, active=True))
        s.add(ReferenceCatalogState(key="counterparties", adopted_existing=False))
        record_audit_event(s, action="REFERENCE_CATALOG_INITIALIZED", object_type="COUNTERPARTIES", object_id=None,
                           actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
                           after={"adopted_existing": False}, reason="Initialisation unique du catalogue standard.")
        s.commit()


def _seed_rfq_providers():
    """Independent idempotency check (not gated behind _seed()'s early
    return) so this default catalog still gets created on a database that
    was already seeded with users before RfqProvider existed."""
    from .models import ReferenceCatalogState
    from ..core.audit import record_audit_event
    with Session(engine) as s:
        if s.get(ReferenceCatalogState, "rfq_providers"):
            return
        existing = bool(s.exec(select(RfqProvider.id)).first())
        if existing:
            s.add(ReferenceCatalogState(key="rfq_providers", adopted_existing=True))
            record_audit_event(s, action="REFERENCE_CATALOG_INITIALIZED", object_type="RFQ_PROVIDERS", object_id=None,
                               actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
                               after={"adopted_existing": True}, reason="Reprise explicite du catalogue existant, sans restauration automatique.")
            s.commit()
            return
        for label in ["Saisie manuelle", "UBS", "Vontobel (deritrade)", "Leonteq", "BNP Paribas", "Société Générale"]:
            s.add(RfqProvider(label=label, mode="manual", active=True))
        s.add(ReferenceCatalogState(key="rfq_providers", adopted_existing=False))
        record_audit_event(s, action="REFERENCE_CATALOG_INITIALIZED", object_type="RFQ_PROVIDERS", object_id=None,
                           actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
                           after={"adopted_existing": False}, reason="Initialisation unique du catalogue standard.")
        s.commit()
