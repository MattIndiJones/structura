"""Generic administration endpoints — admin-only. Covers the RFQ provider
catalog, the generic read-only+delete data browser (core/admin_registry.py),
and Users/Entities CRUD, all gated by get_current_admin."""
from __future__ import annotations
import bcrypt
from datetime import datetime, date
from typing import Annotated, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import RfqProvider, User, Entity, Counterparty
from .auth import get_current_admin
from ..core import admin_registry
from ..core.amc_prices import fetch_prices as _fetch_prices, price_status as _price_status, _slug

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# ── Pydantic schemas ──────────────────────────────────────────────────

class RfqProviderCreate(BaseModel):
    label: str
    mode: str = "manual"
    counterparty_id: Optional[int] = None


class RfqProviderUpdate(BaseModel):
    label: Optional[str] = None
    mode: Optional[str] = None
    active: Optional[bool] = None
    # Explicitly nullable: sending null unlinks the provider from its
    # counterparty (the update loop below sets whatever was sent, unset
    # fields excluded).
    counterparty_id: Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────

def _row(p: RfqProvider, cpty_names: dict | None = None) -> dict:
    return {
        "id": p.id,
        "label": p.label,
        "mode": p.mode,
        "active": p.active,
        # The counterparty a deal booked out of this provider's quote faces —
        # see models.py:RfqProvider.counterparty_id. Name resolved here so the
        # admin screen doesn't have to join two catalogs itself.
        "counterparty_id": p.counterparty_id,
        "counterparty_name": (cpty_names or {}).get(p.counterparty_id),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _cpty_names(session: Session) -> dict:
    return {c.id: c.name for c in session.exec(select(Counterparty)).all()}


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/rfq-providers")
def list_rfq_providers(
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    providers = session.exec(select(RfqProvider).order_by(RfqProvider.label)).all()
    names = _cpty_names(session)
    return [_row(p, names) for p in providers]


@router.post("/rfq-providers", status_code=201)
def create_rfq_provider(
    body: RfqProviderCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    label = body.label.strip()
    if not label:
        raise HTTPException(422, "Le nom du fournisseur est requis")
    p = RfqProvider(label=label, mode=body.mode, counterparty_id=body.counterparty_id)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _row(p, _cpty_names(session))


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
    return _row(p, _cpty_names(session))


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
    limit_eur: Optional[float] = None


class CounterpartyUpdate(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    active: Optional[bool] = None
    limit_eur: Optional[float] = None


def _cpty_row(c: Counterparty) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "country": c.country,
        "active": c.active,
        "limit_eur": c.limit_eur,
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
    c = Counterparty(name=name, country=body.country.strip(), limit_eur=body.limit_eur)
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
    former_name = c.name
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    c.updated_at = datetime.utcnow()
    session.add(c)

    # Un renommage cassait en silence le rapprochement par nom identique :
    # « BNP Paribas » devenu « BNP Paribas SA » et le fournisseur RFQ du même
    # nom ne résolvait plus rien, découvert au booking suivant. Les
    # fournisseurs qui tenaient par ce nom sont rattachés par id avant que le
    # nom ne change — le lien explicite, lui, survit à tout renommage.
    if c.name != former_name:
        orphans = session.exec(
            select(RfqProvider).where(RfqProvider.label == former_name,
                                       RfqProvider.counterparty_id == None)  # noqa: E711
        ).all()
        for p in orphans:
            p.counterparty_id = c.id
            session.add(p)
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


@router.get("/browse/{table_key}/{row_id}")
def browse_get_row(
    table_key: str,
    row_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    return admin_registry.get_row(table_key, row_id, session)


@router.delete("/browse/{table_key}/{row_id}", status_code=204)
def browse_delete_row(
    table_key: str,
    row_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    admin_registry.delete_row(table_key, row_id, session)


class BrowseDelete(BaseModel):
    ids: list[int]


@router.post("/browse/{table_key}/delete")
def browse_delete_rows(
    table_key: str,
    body: BrowseDelete,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """Suppression en lot. POST et non DELETE : la liste d'ids voyage dans le
    corps, qu'un DELETE ne transporte pas de façon fiable. Renvoie le détail
    par ligne — supprimées d'un côté, bloquées avec leur raison de l'autre."""
    if not body.ids:
        raise HTTPException(422, "Aucun enregistrement sélectionné.")
    return admin_registry.delete_rows(table_key, body.ids, session)


@router.patch("/browse/{table_key}/{row_id}")
def browse_update_row(
    table_key: str,
    row_id: int,
    patch: dict,
    admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    return admin_registry.update_row(table_key, row_id, patch, session, actor_id=admin.id)


# ── Users (full CRUD except delete — soft-delete via is_active) ───────

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: Literal["user", "checker", "admin"] = "user"
    entity_id: Optional[int] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[Literal["user", "checker", "admin"]] = None
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


# ── Market data catalog ────────────────────────────────────────────────

_CATALOG = [
    # Indices US
    {"key": "SPX",  "ticker": "^GSPC",     "label": "S&P 500",           "category": "Indices US"},
    {"key": "NDX",  "ticker": "^NDX",      "label": "Nasdaq 100",        "category": "Indices US"},
    {"key": "DJI",  "ticker": "^DJI",      "label": "Dow Jones",         "category": "Indices US"},
    {"key": "RTY",  "ticker": "^RUT",      "label": "Russell 2000",      "category": "Indices US"},
    {"key": "VIX",  "ticker": "^VIX",      "label": "VIX",               "category": "Indices US"},
    # Indices EU
    {"key": "SX5E", "ticker": "^STOXX50E", "label": "EuroStoxx 50",     "category": "Indices EU"},
    {"key": "DAX",  "ticker": "^GDAXI",    "label": "DAX 40",            "category": "Indices EU"},
    {"key": "CAC",  "ticker": "^FCHI",     "label": "CAC 40",            "category": "Indices EU"},
    {"key": "SMI",  "ticker": "^SSMI",     "label": "SMI",               "category": "Indices EU"},
    {"key": "FTSE", "ticker": "^FTSE",     "label": "FTSE 100",          "category": "Indices EU"},
    {"key": "AEX",  "ticker": "^AEX",      "label": "AEX",               "category": "Indices EU"},
    {"key": "IBEX", "ticker": "^IBEX",     "label": "IBEX 35",           "category": "Indices EU"},
    {"key": "MIB",  "ticker": "FTSEMIB.MI","label": "FTSE MIB",          "category": "Indices EU"},
    # Indices Asie
    {"key": "NKY",  "ticker": "^N225",     "label": "Nikkei 225",        "category": "Indices Asie"},
    {"key": "HSI",  "ticker": "^HSI",      "label": "Hang Seng",         "category": "Indices Asie"},
    {"key": "KS11", "ticker": "^KS11",     "label": "KOSPI",             "category": "Indices Asie"},
    {"key": "AXJO", "ticker": "^AXJO",     "label": "ASX 200",           "category": "Indices Asie"},
    # Actions US
    {"key": "AAPL", "ticker": "AAPL",      "label": "Apple",             "category": "Actions US"},
    {"key": "MSFT", "ticker": "MSFT",      "label": "Microsoft",         "category": "Actions US"},
    {"key": "AMZN", "ticker": "AMZN",      "label": "Amazon",            "category": "Actions US"},
    {"key": "GOOGL","ticker": "GOOGL",     "label": "Alphabet",          "category": "Actions US"},
    {"key": "META", "ticker": "META",      "label": "Meta",              "category": "Actions US"},
    {"key": "NVDA", "ticker": "NVDA",      "label": "Nvidia",            "category": "Actions US"},
    {"key": "TSLA", "ticker": "TSLA",      "label": "Tesla",             "category": "Actions US"},
    {"key": "AMD",  "ticker": "AMD",       "label": "AMD",               "category": "Actions US"},
    {"key": "INTC", "ticker": "INTC",      "label": "Intel",             "category": "Actions US"},
    {"key": "JPM",  "ticker": "JPM",       "label": "JPMorgan",          "category": "Actions US"},
    {"key": "BAC",  "ticker": "BAC",       "label": "Bank of America",   "category": "Actions US"},
    {"key": "GS",   "ticker": "GS",        "label": "Goldman Sachs",     "category": "Actions US"},
    {"key": "V",    "ticker": "V",         "label": "Visa",              "category": "Actions US"},
    {"key": "MA",   "ticker": "MA",        "label": "Mastercard",        "category": "Actions US"},
    {"key": "JNJ",  "ticker": "JNJ",       "label": "Johnson & Johnson", "category": "Actions US"},
    {"key": "PFE",  "ticker": "PFE",       "label": "Pfizer",            "category": "Actions US"},
    {"key": "LLY",  "ticker": "LLY",       "label": "Eli Lilly",         "category": "Actions US"},
    {"key": "ABBV", "ticker": "ABBV",      "label": "AbbVie",            "category": "Actions US"},
    {"key": "AMGN", "ticker": "AMGN",      "label": "Amgen",             "category": "Actions US"},
    {"key": "XOM",  "ticker": "XOM",       "label": "ExxonMobil",        "category": "Actions US"},
    {"key": "NKE",  "ticker": "NKE",       "label": "Nike",              "category": "Actions US"},
    {"key": "COIN", "ticker": "COIN",      "label": "Coinbase",          "category": "Actions US"},
    # Actions EU
    {"key": "ASML", "ticker": "ASML",      "label": "ASML",              "category": "Actions EU"},
    {"key": "MC",   "ticker": "MC.PA",     "label": "LVMH",              "category": "Actions EU"},
    {"key": "OR",   "ticker": "OR.PA",     "label": "L'Oreal",           "category": "Actions EU"},
    {"key": "AIR",  "ticker": "AIR.PA",    "label": "Airbus",            "category": "Actions EU"},
    {"key": "TTE",  "ticker": "TTE.PA",    "label": "TotalEnergies",     "category": "Actions EU"},
    {"key": "SAN",  "ticker": "SAN.PA",    "label": "Sanofi",            "category": "Actions EU"},
    {"key": "BNP",  "ticker": "BNP.PA",    "label": "BNP Paribas",       "category": "Actions EU"},
    {"key": "AXA",  "ticker": "CS.PA",     "label": "AXA",               "category": "Actions EU"},
    {"key": "SIE",  "ticker": "SIE.DE",    "label": "Siemens",           "category": "Actions EU"},
    {"key": "SAP",  "ticker": "SAP.DE",    "label": "SAP",               "category": "Actions EU"},
    {"key": "BMW",  "ticker": "BMW.DE",    "label": "BMW",               "category": "Actions EU"},
    {"key": "VOW",  "ticker": "VOW3.DE",   "label": "Volkswagen",        "category": "Actions EU"},
    {"key": "BAYN", "ticker": "BAYN.DE",   "label": "Bayer",             "category": "Actions EU"},
    {"key": "ENI",  "ticker": "ENI.MI",    "label": "Eni",               "category": "Actions EU"},
    {"key": "ITX",  "ticker": "ITX.MC",    "label": "Inditex",           "category": "Actions EU"},
    # Actions CH
    {"key": "NESN", "ticker": "NESN.SW",   "label": "Nestle",            "category": "Actions CH"},
    {"key": "NOVN", "ticker": "NOVN.SW",   "label": "Novartis",          "category": "Actions CH"},
    {"key": "UBSG", "ticker": "UBSG.SW",   "label": "UBS Group",         "category": "Actions CH"},
    {"key": "ABBN", "ticker": "ABBN.SW",   "label": "ABB",               "category": "Actions CH"},
    {"key": "ZURN", "ticker": "ZURN.SW",   "label": "Zurich Insurance",  "category": "Actions CH"},
    {"key": "CFR",  "ticker": "CFR.SW",    "label": "Richemont",         "category": "Actions CH"},
    # Matières premières
    {"key": "GOLD", "ticker": "GC=F",      "label": "Or (Gold)",         "category": "Matières premières"},
    {"key": "SILV", "ticker": "SI=F",      "label": "Argent (Silver)",   "category": "Matières premières"},
    {"key": "OIL",  "ticker": "CL=F",      "label": "Pétrole WTI",       "category": "Matières premières"},
    # Crypto
    {"key": "BTC",  "ticker": "BTC-USD",   "label": "Bitcoin",           "category": "Crypto"},
    {"key": "ETH",  "ticker": "ETH-USD",   "label": "Ethereum",          "category": "Crypto"},
    {"key": "SOL",  "ticker": "SOL-USD",   "label": "Solana",            "category": "Crypto"},
]


@router.get("/market-data")
def market_data_catalog(admin: Annotated[User, Depends(get_current_admin)]):
    stored = {s["key"]: s for s in _price_status()}
    today = date.today()
    result = []
    for item in _CATALOG:
        slug = _slug(item["key"])
        s = stored.get(slug, {})
        available = s.get("available", False)
        date_max = s.get("date_max", "")
        if not available or not date_max:
            cache_status = "missing"
        else:
            days_old = (today - date.fromisoformat(date_max)).days
            cache_status = "stale" if days_old > 7 else "ok"
        result.append({
            **item,
            "slug":         slug,
            "available":    available,
            "date_min":     s.get("date_min", ""),
            "date_max":     date_max,
            "rows":         s.get("rows", 0),
            "currency":     s.get("currency", ""),
            "cache_status": cache_status,
        })
    return result


class MarketDataFetchRequest(BaseModel):
    key: str
    ticker: str


@router.post("/market-data/fetch")
def market_data_fetch(
    body: MarketDataFetchRequest,
    admin: Annotated[User, Depends(get_current_admin)],
):
    try:
        return _fetch_prices(body.key, body.ticker)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur Yahoo Finance : {e}")
