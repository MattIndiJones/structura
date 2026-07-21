from pathlib import Path
import bcrypt
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine
from .models import (
    Entity, User, Folder, Script, Deal, DealEvent, Document, AmcStudy,
    Indicative, KidRecord, EmtRecord, RfqRequest, RfqQuote, RfqProvider,
    Counterparty, Alert, Portfolio, ShockRun,
)

_DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "structura.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False,
                        connect_args={"check_same_thread": False})


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


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate()
    _seed()
    _seed_rfq_providers()
    _seed_counterparties()
    _backfill_default_portfolios()


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
