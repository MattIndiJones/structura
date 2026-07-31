from pathlib import Path
import bcrypt
from sqlalchemy import event, text
from sqlmodel import SQLModel, Session, create_engine
from .models import (
    Entity, User, Folder, Script, Deal, DealEvent, Document, AmcStudy,
    Indicative, KidRecord, EmtRecord, RfqRequest, RfqQuote, RfqProvider,
    Counterparty, Alert, Portfolio, ShockRun, ComputeBatch, ComputeJob,
)

_DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "structura.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False,
                        connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_integrity_pragmas(dbapi_connection, _connection_record):
    """SQLite does not enforce declared foreign keys unless enabled per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_session():
    with Session(engine) as session:
        yield session


def _migrate():
    """Additive, idempotent schema patches for columns added to tables that
    already exist in deployed databases — create_all() only creates missing
    tables, it never ALTERs an existing one. No Alembic in this project;
    keep patches here small and check-before-add."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(deals)"))}
        if "indicative_id" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN indicative_id INTEGER"))
            conn.commit()

        if "payment_date" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN payment_date TEXT DEFAULT ''"))
            conn.commit()

        if "realized_payout" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN realized_payout REAL"))
            conn.commit()

        if "resolution_outcome" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN resolution_outcome TEXT"))
            conn.commit()

        if "product_type" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN product_type TEXT DEFAULT ''"))
            conn.commit()

        if "greeks_json" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN greeks_json TEXT DEFAULT '{}'"))
            conn.commit()

        if "greeks_computed_at" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN greeks_computed_at DATETIME"))
            conn.commit()

        if "portfolio_id" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN portfolio_id INTEGER"))
            conn.commit()

        rfq_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rfq_requests)"))}
        if rfq_cols and "ao_date" not in rfq_cols:
            conn.execute(text("ALTER TABLE rfq_requests ADD COLUMN ao_date TEXT DEFAULT ''"))
            conn.commit()

        portfolio_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(portfolios)"))}
        if portfolio_cols and "is_default" not in portfolio_cols:
            conn.execute(text("ALTER TABLE portfolios ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            conn.commit()

        cpty_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(counterparties)"))}
        if cpty_cols and "limit_eur" not in cpty_cols:
            conn.execute(text("ALTER TABLE counterparties ADD COLUMN limit_eur REAL"))
            conn.commit()

        if "rfq_id" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN rfq_id INTEGER"))
            conn.commit()

        rfq_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rfq_requests)"))}
        if rfq_cols and "selected_quote_id" not in rfq_cols:
            conn.execute(text("ALTER TABLE rfq_requests ADD COLUMN selected_quote_id INTEGER"))
            conn.commit()

        quote_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rfq_quotes)"))}
        if quote_cols and "last_look" not in quote_cols:
            conn.execute(text("ALTER TABLE rfq_quotes ADD COLUMN last_look BOOLEAN DEFAULT 0"))
            conn.commit()
        if quote_cols and "parent_quote_id" not in quote_cols:
            conn.execute(text("ALTER TABLE rfq_quotes ADD COLUMN parent_quote_id INTEGER"))
            conn.commit()

        rfq_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rfq_requests)"))}
        if rfq_cols and "kind" not in rfq_cols:
            conn.execute(text("ALTER TABLE rfq_requests ADD COLUMN kind TEXT DEFAULT 'indicatif'"))
            conn.commit()

        # Pre-existing RFQs land on 'achat' like new ones: this module solicits
        # "fournisseurs", so buying is what they were, even though the old
        # best-quote logic (highest price wins) implicitly assumed the opposite.
        # Their stored prices don't move — only which one is flagged as best.
        if rfq_cols and "sens" not in rfq_cols:
            conn.execute(text("ALTER TABLE rfq_requests ADD COLUMN sens TEXT DEFAULT 'achat'"))
            conn.commit()

        if "rfq_provenance_json" not in cols:
            conn.execute(text("ALTER TABLE deals ADD COLUMN rfq_provenance_json TEXT"))
            conn.commit()

        provider_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rfq_providers)"))}
        if provider_cols and "counterparty_id" not in provider_cols:
            conn.execute(text("ALTER TABLE rfq_providers ADD COLUMN counterparty_id INTEGER"))
            conn.commit()

        for table in ("deals", "indicatives", "rfq_requests"):
            _ensure_unique_reference(conn, table)
        _ensure_one_deal_per_rfq(conn)
        _ensure_rfq_integrity_triggers(conn)
        _make_kid_vev_nullable(conn)


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
    """Migrate old NOT NULL VEV storage to the total-loss-aware contract."""
    columns = conn.execute(text("PRAGMA table_info(kid_records)")).all()
    vev = next((row for row in columns if row[1] == "vev"), None)
    if not vev or not vev[3]:
        return
    conn.execute(text("""
        CREATE TABLE kid_records__vev_nullable (
            id INTEGER NOT NULL PRIMARY KEY,
            indicative_id INTEGER,
            deal_id INTEGER,
            user_id INTEGER NOT NULL,
            product_title VARCHAR NOT NULL,
            sri INTEGER NOT NULL,
            mrm INTEGER NOT NULL,
            crm INTEGER NOT NULL,
            vev FLOAT,
            t_rhp FLOAT NOT NULL,
            horizons_json TEXT,
            costs_json TEXT,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(indicative_id) REFERENCES indicatives(id),
            FOREIGN KEY(deal_id) REFERENCES deals(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """))
    conn.execute(text("""
        INSERT INTO kid_records__vev_nullable
        SELECT id, indicative_id, deal_id, user_id, product_title, sri, mrm,
               crm, vev, t_rhp, horizons_json, costs_json, created_at
        FROM kid_records
    """))
    conn.execute(text("DROP TABLE kid_records"))
    conn.execute(text("ALTER TABLE kid_records__vev_nullable RENAME TO kid_records"))
    conn.commit()


def _backfill_default_portfolios():
    """Risk must always be monitored somewhere — every deal.portfolio_id is
    non-NULL from here on. Assigns any orphan deal (pre-existing db, or a
    deal booked before this feature) to its owner's default portfolio,
    creating that portfolio (is_default=True, never deletable — see
    api/portfolios.py) the first time it's needed. Idempotent: a user with
    no orphans and no default portfolio yet gets neither created."""
    from sqlmodel import select
    with Session(engine) as s:
        orphan_user_ids = {
            d.user_id for d in s.exec(select(Deal).where(Deal.portfolio_id == None)).all()  # noqa: E711
        }
        for uid in orphan_user_ids:
            default = s.exec(
                select(Portfolio).where(Portfolio.user_id == uid, Portfolio.is_default == True)  # noqa: E712
            ).first()
            if not default:
                default = Portfolio(name="Portefeuille par défaut", user_id=uid, is_default=True)
                s.add(default)
                s.flush()
            orphans = s.exec(
                select(Deal).where(Deal.user_id == uid, Deal.portfolio_id == None)  # noqa: E711
            ).all()
            for d in orphans:
                d.portfolio_id = default.id
                s.add(d)
        s.commit()


def _backfill_rfq_statuses():
    """RFQ statuses used to be posed by the caller, which only ever wrote
    'draft', 'retenue' or 'clos': 'envoye'/'quote' existed as labels but
    nothing set them, so a tender with five prices in hand still displayed
    "Brouillon", and de-selecting a response left it on "Retenue" with
    nothing retained. They're deduced from the facts now — realign the rows
    written before that. Terminal states (booked, sans suite) are left alone,
    exactly as the derivation itself leaves them. A durable marker makes this
    full-table migration run once rather than at every application startup.

    _derive_status is imported lazily: api\\rfq.py imports this module for
    get_session, so a module-level import here would be circular."""
    from sqlmodel import select
    from ..api.rfq import _derive_status
    with Session(engine) as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS app_migrations (
                key TEXT PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        marker = "rfq_statuses_derived_v1"
        if s.execute(text(
                "SELECT 1 FROM app_migrations WHERE key = :key"),
                {"key": marker}).first():
            return
        rfqs = s.exec(select(RfqRequest)).all()
        quotes_by_rfq: dict[int, list] = {}
        for q in s.exec(select(RfqQuote)).all():
            quotes_by_rfq.setdefault(q.rfq_id, []).append(q)
        for r in rfqs:
            derived = _derive_status(r, quotes_by_rfq.get(r.id, []))
            if derived != r.status:
                r.status = derived
                s.add(r)
        s.execute(text(
            "INSERT OR IGNORE INTO app_migrations(key) VALUES (:key)"),
            {"key": marker})
        s.commit()


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate()
    _seed()
    _seed_rfq_providers()
    _seed_counterparties()
    _backfill_default_portfolios()
    _backfill_rfq_statuses()


def _seed():
    with Session(engine) as s:
        # Idempotent — skip if already seeded
        if s.query(Entity).count() > 0:
            return

        demo = Entity(name="Demo")
        s.add(demo)
        s.flush()

        admin = User(
            username="admin",
            email="admin@structura.local",
            password_hash=_hash_pw("admin123"),
            role="admin",
            entity_id=demo.id,
        )
        test = User(
            username="test",
            email="test@structura.local",
            password_hash=_hash_pw("test123"),
            role="user",
            entity_id=demo.id,
        )
        s.add(admin)
        s.add(test)
        s.commit()


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
    with Session(engine) as s:
        if s.query(Counterparty).count() > 0:
            return
        for name, country in _DEFAULTS:
            s.add(Counterparty(name=name, country=country, active=True))
        s.commit()


def _seed_rfq_providers():
    """Independent idempotency check (not gated behind _seed()'s early
    return) so this default catalog still gets created on a database that
    was already seeded with users before RfqProvider existed."""
    with Session(engine) as s:
        if s.query(RfqProvider).count() > 0:
            return
        for label in ["Saisie manuelle", "UBS", "Vontobel (deritrade)", "Leonteq", "BNP Paribas", "Société Générale"]:
            s.add(RfqProvider(label=label, mode="manual", active=True))
        s.commit()
