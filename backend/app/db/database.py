from pathlib import Path
import bcrypt
from sqlmodel import SQLModel, Session, create_engine
from .models import Entity, User, Folder, Script, Deal, DealEvent, Document

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


def init_db():
    SQLModel.metadata.create_all(engine)
    _seed()


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
