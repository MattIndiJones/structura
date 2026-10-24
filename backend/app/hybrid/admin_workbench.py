"""Complete local development application, independent of client installations."""
import json
import os

from fastapi import HTTPException, Request
from sqlmodel import SQLModel, Field
from sqlalchemy import text

from .config import credentials, read_config


class AdminWorkbenchIdentity(SQLModel, table=True):
    __tablename__ = "admin_workbench_identity"
    id: int = Field(default=1, primary_key=True)
    installation_id: str = Field(unique=True)
    entity_id: int = Field(foreign_key="entities.id")


def preflight(engine, installation):
    """Read-only identity check, necessarily before create_all/migrations/seeding."""
    from pathlib import Path
    if installation.service != "admin_workbench" or Path(engine.url.database).resolve() != (installation.data_dir / "structura.db").resolve():
        raise RuntimeError("Le moteur SQL ne correspond pas au workspace Admin.")
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'"))}
        if tables - (set(SQLModel.metadata.tables) | {"app_migrations"}):
            raise RuntimeError("Schéma du workspace Admin non identifié ; aucune mise à jour appliquée.")
        marker = connection.execute(text("SELECT installation_id FROM admin_workbench_identity WHERE id=1")).first() \
            if "admin_workbench_identity" in tables else None
        if marker:
            if marker[0] != str(installation.installation_id):
                raise RuntimeError("La base appartient à un autre workspace Admin ; aucune mise à jour appliquée.")
            if "entities" not in tables or not connection.execute(text(
                    "SELECT 1 FROM entities JOIN admin_workbench_identity ON entities.id=admin_workbench_identity.entity_id WHERE admin_workbench_identity.id=1")).first():
                raise RuntimeError("Organisation du workspace Admin absente ; aucune mise à jour appliquée.")
            if "hybrid_bootstrap" in tables and connection.execute(text("SELECT 1 FROM hybrid_bootstrap LIMIT 1")).first():
                raise RuntimeError("Identités métier et Admin incompatibles ; aucune mise à jour appliquée.")
            return
        for table in tables - {"app_migrations"}:
            identifier = '"' + table.replace('"', '""') + '"'
            if connection.execute(text(f"SELECT 1 FROM {identifier} LIMIT 1")).first():
                raise RuntimeError("Base Admin occupée sans identité attestée ; provisionnement explicite requis avant toute migration.")


def config():
    path = os.environ.get("STRUCTURA_ADMIN_WORKBENCH_CONFIG")
    if os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") != "admin_workbench" or not path:
        return None
    result = read_config(path)
    if result.service != "admin_workbench" or str(result.data_dir) != os.environ.get("STRUCTURA_DATA_DIR"):
        raise RuntimeError("Le workspace Admin ne correspond pas à son répertoire privé.")
    return result


def options():
    installation = config()
    return {"admin_workbench": bool(installation), "development_admin_enabled": bool(installation
            and os.environ.get("STRUCTURA_DEVELOPER_ACCESS") == "1"),
            "platform_url": json.loads((installation.data_dir / "platform.json").read_text(encoding="utf-8"))["url"]
                if installation else None}


def seed(engine):
    import bcrypt
    from sqlmodel import Session, select
    from ..db.models import Entity, User
    installation = config()
    if not installation:
        raise RuntimeError("Manifeste Admin requis.")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "admin")).first()
        marker = session.get(AdminWorkbenchIdentity, 1)
        if marker and marker.installation_id != str(installation.installation_id):
            raise RuntimeError("Identité du workspace Admin incompatible.")
        if marker:
            return {"accounts": len(session.exec(select(User)).all()), "admin_workbench": True}
        if session.exec(select(Entity)).first() or session.exec(select(User)).first():
            raise RuntimeError("Workspace Admin déjà occupé ; aucun remplacement de comptes.")
        entity = Entity(name="Structura — développement Admin")
        session.add(entity)
        session.flush()
        session.add(AdminWorkbenchIdentity(installation_id=str(installation.installation_id), entity_id=entity.id))
        password = credentials(installation)["admin"]
        session.add(User(username="admin", email="admin@structura.local", role="admin", entity_id=entity.id,
                         password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()))
        session.commit()
    return {"accounts": 1, "admin_workbench": True}


def login(request: Request):
    from sqlmodel import Session, select
    from ..db.database import engine
    from ..db.models import User
    from ..api.auth import _make_token
    from ..core.audit import record_audit_event
    installation = config()
    if not installation or os.environ.get("STRUCTURA_DEVELOPER_ACCESS") != "1":
        raise HTTPException(404, "Accès Admin local désactivé.")
    origin = request.headers.get("origin")
    allowed = {installation.public_descriptor()["url"], f"http://localhost:{installation.port}"}
    if not request.client or request.client.host not in {"127.0.0.1", "::1"} \
            or origin and origin not in allowed or request.headers.get("sec-fetch-site") == "cross-site" \
            or request.headers.get("X-Structura-Development") != "1":
        raise HTTPException(403, "Accès Admin limité au lanceur et au navigateur local.")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "admin", User.role == "admin", User.is_active == True)).first()
        if not user:
            raise HTTPException(403, "Le compte Admin est indisponible.")
        record_audit_event(session, action="DEVELOPMENT_ADMIN_LOGIN", object_type="USER", object_id=user.id,
                           actor_user_id=user.id, actor_type="USER", result="SUCCESS")
        session.commit()
        return {"access_token": _make_token(user.id, user.role, user.entity_id, auth_version=user.auth_version), "token_type": "bearer"}
