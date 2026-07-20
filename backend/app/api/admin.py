"""Generic administration endpoints — admin-only. Covers the RFQ provider
catalog, the generic read-only+delete data browser (core/admin_registry.py),
and Users/Entities CRUD, all gated by get_current_admin."""
from __future__ import annotations
import bcrypt
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import RfqProvider, User, Entity, Counterparty
from .auth import get_current_admin
from ..core import admin_registry

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# ── Pydantic schemas ──────────────────────────────────────────────────

class RfqProviderCreate(BaseModel):
    label: str
    mode: str = "manual"


class RfqProviderUpdate(BaseModel):
    label: Optional[str] = None
    mode: Optional[str] = None
    active: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────

def _row(p: RfqProvider) -> dict:
    return {
        "id": p.id,
        "label": p.label,
        "mode": p.mode,
        "active": p.active,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/rfq-providers")
def list_rfq_providers(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    providers = session.exec(select(RfqProvider).order_by(RfqProvider.label)).all()
    return [_row(p) for p in providers]


@router.post("/rfq-providers", status_code=201)
def create_rfq_provider(
    body: RfqProviderCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    label = body.label.strip()
    if not label:
        raise HTTPException(422, "Le nom du fournisseur est requis")
    p = RfqProvider(label=label, mode=body.mode)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _row(p)


@router.patch("/rfq-providers/{provider_id}")
def update_rfq_provider(
    provider_id: int,
    body: RfqProviderUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(RfqProvider, provider_id)
    if not p:
        raise HTTPException(404, "Fournisseur introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return _row(p)


@router.delete("/rfq-providers/{provider_id}", status_code=204)
def delete_rfq_provider(
    provider_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(RfqProvider, provider_id)
    if not p:
        raise HTTPException(404, "Fournisseur introuvable")
    session.delete(p)
    session.commit()


# ── Counterparties eligible to face a booked deal ─────────────────────

class CounterpartyCreate(BaseModel):
    name: str
    country: str = ""


class CounterpartyUpdate(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    active: Optional[bool] = None


def _cpty_row(c: Counterparty) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "country": c.country,
        "active": c.active,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


@router.get("/counterparties")
def list_counterparties(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    cptys = session.exec(select(Counterparty).order_by(Counterparty.name)).all()
    return [_cpty_row(c) for c in cptys]


@router.post("/counterparties", status_code=201)
def create_counterparty(
    body: CounterpartyCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Le nom de la contrepartie est requis")
    if session.exec(select(Counterparty).where(Counterparty.name == name)).first():
        raise HTTPException(400, "Cette contrepartie existe déjà")
    c = Counterparty(name=name, country=body.country.strip())
    session.add(c)
    session.commit()
    session.refresh(c)
    return _cpty_row(c)


@router.patch("/counterparties/{cpty_id}")
def update_counterparty(
    cpty_id: int,
    body: CounterpartyUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    c = session.get(Counterparty, cpty_id)
    if not c:
        raise HTTPException(404, "Contrepartie introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    c.updated_at = datetime.utcnow()
    session.add(c)
    session.commit()
    return _cpty_row(c)


@router.delete("/counterparties/{cpty_id}", status_code=204)
def delete_counterparty(
    cpty_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    c = session.get(Counterparty, cpty_id)
    if not c:
        raise HTTPException(404, "Contrepartie introuvable")
    session.delete(c)
    session.commit()


# ── Data browser (read-only + delete, see core/admin_registry.py) ─────

@router.get("/browse")
def browse_tables(admin: Annotated[User, Depends(get_current_admin)]):
    return admin_registry.registry_meta()


@router.get("/browse/{table_key}")
def browse_table_rows(
    table_key: str,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    return admin_registry.list_rows(table_key, session)


@router.delete("/browse/{table_key}/{row_id}", status_code=204)
def browse_delete_row(
    table_key: str,
    row_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    admin_registry.delete_row(table_key, row_id, session)


# ── Users (full CRUD except delete — soft-delete via is_active) ───────

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"
    entity_id: Optional[int] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    entity_id: Optional[int] = None
    is_active: Optional[bool] = None


def _user_row(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "email": u.email, "role": u.role,
        "entity_id": u.entity_id, "is_active": u.is_active,
        "created_at": u.created_at.isoformat(),
    }


@router.get("/users")
def list_users(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    users = session.exec(select(User).order_by(User.username)).all()
    return [_user_row(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    body: UserCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    if session.exec(select(User).where(User.username == body.username)).first():
        raise HTTPException(400, "Cet identifiant est déjà utilisé")
    if session.exec(select(User).where(User.email == body.email)).first():
        raise HTTPException(400, "Cet e-mail est déjà utilisé")
    u = User(
        username=body.username, email=body.email,
        password_hash=_hash_pw(body.password),
        role=body.role, entity_id=body.entity_id,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return _user_row(u)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(u, field, value)
    session.add(u)
    session.commit()
    return _user_row(u)


# ── Entities (create + rename — no delete in v1) ───────────────────────

class EntityCreate(BaseModel):
    name: str


class EntityUpdate(BaseModel):
    name: Optional[str] = None


def _entity_row(e: Entity) -> dict:
    return {"id": e.id, "name": e.name, "created_at": e.created_at.isoformat()}


@router.get("/entities")
def list_entities(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    entities = session.exec(select(Entity).order_by(Entity.name)).all()
    return [_entity_row(e) for e in entities]


@router.post("/entities", status_code=201)
def create_entity(
    body: EntityCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Le nom est requis")
    e = Entity(name=name)
    session.add(e)
    session.commit()
    session.refresh(e)
    return _entity_row(e)


@router.patch("/entities/{entity_id}")
def update_entity(
    entity_id: int,
    body: EntityUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    e = session.get(Entity, entity_id)
    if not e:
        raise HTTPException(404, "Entité introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(e, field, value)
    session.add(e)
    session.commit()
    return _entity_row(e)
