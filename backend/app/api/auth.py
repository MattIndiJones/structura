import logging
import os
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Entity, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Value that used to be compiled into this file — and therefore into every
# clone, backup and fork of the repository. Anyone holding a copy could mint a
# token for any user id, admin included, without a password. Kept here only to
# be REFUSED: an installation still carrying it must not start.
_LEAKED_SECRET = "structura-jwt-secret-change-in-prod"

# backend/app/api/auth.py -> parents[2] == backend/
_SECRET_FILE = Path(__file__).resolve().parents[2] / "data" / ".jwt_secret"


def _load_secret() -> str:
    """Signing key, in order of preference: environment, then a per-machine
    file, then a freshly generated one.

    The key must not live in the repository, but hard-failing without one
    would make a fresh clone unusable and push people towards putting it back.
    So an absent key is generated once and stored in `backend/data/` — the
    directory that already holds the un-versioned database — which keeps
    sessions alive across the backend restarts this project does constantly,
    while giving every machine a distinct key. Deployments override it through
    STRUCTURA_JWT_SECRET and never touch the file.

    Tokens signed with the previously hard-coded value stop verifying here.
    That is the point, not a side effect."""
    from_env = os.environ.get("STRUCTURA_JWT_SECRET", "").strip()
    if from_env:
        if from_env == _LEAKED_SECRET:
            raise RuntimeError(
                "STRUCTURA_JWT_SECRET porte la valeur d'exemple publiée dans le "
                "dépôt : elle ne signe plus rien. Générez une clé propre "
                "(python -c \"import secrets; print(secrets.token_urlsafe(64))\").")
        if len(from_env) < 32:
            raise RuntimeError(
                f"STRUCTURA_JWT_SECRET fait {len(from_env)} caractères — 32 au "
                f"minimum sont exigés pour une signature HS256 sérieuse.")
        return from_env

    try:
        if _SECRET_FILE.exists():
            stored = _SECRET_FILE.read_text(encoding="utf-8").strip()
            if stored and stored != _LEAKED_SECRET and len(stored) >= 32:
                return stored
        generated = secrets.token_urlsafe(64)
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_FILE.write_text(generated, encoding="utf-8")
        logger.warning(
            "Cle de signature JWT generee dans %s (fichier non versionne). "
            "Les jetons anterieurs sont invalides : reconnectez-vous.",
            _SECRET_FILE)
        return generated
    except OSError as exc:
        # Read-only filesystem, permissions, container without volume: an
        # ephemeral key still beats a published one. Sessions die on restart.
        logger.warning(
            "Cle JWT non persistable (%s) — cle ephemere pour ce processus. "
            "Definissez STRUCTURA_JWT_SECRET pour des sessions durables.", exc)
        return secrets.token_urlsafe(64)


_SECRET = _load_secret()
_ALGO = "HS256"
_EXPIRE_DAYS = 7

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ── Anti-bruteforce sur /login ──────────────────────────────────────────
# In-process, volontairement. L'application tourne en un seul uvicorn sur un
# poste : un compteur mémoire couvre le cas réel sans dépendance ni table. Il
# ne survit pas à un redémarrage et ne couvre pas un déploiement multi-worker —
# à remplacer par un stockage partagé le jour où ce sera le cas.
_MAX_FAILURES = 5
_LOCK_SECONDS = (60, 300, 900)     # after 5, 10, 15 consecutive failures
_attempts: dict[tuple[str, str], list] = {}   # (user, ip) -> [count, locked_until]
_attempts_lock = threading.Lock()


def _throttle_key(username: str, request: Request | None) -> tuple[str, str]:
    ip = "?"
    if request is not None and request.client is not None:
        ip = request.client.host or "?"
    return (username.lower().strip(), ip)


def _check_not_locked(key: tuple[str, str]) -> None:
    with _attempts_lock:
        entry = _attempts.get(key)
        if not entry:
            return
        _count, locked_until = entry
        if locked_until and locked_until > datetime.utcnow():
            wait = int((locked_until - datetime.utcnow()).total_seconds()) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Trop de tentatives infructueuses. Réessayez dans {wait} s.",
                headers={"Retry-After": str(wait)},
            )


def _record_failure(key: tuple[str, str]) -> None:
    with _attempts_lock:
        entry = _attempts.setdefault(key, [0, None])
        entry[0] += 1
        if entry[0] >= _MAX_FAILURES:
            tier = min((entry[0] - _MAX_FAILURES) // _MAX_FAILURES,
                       len(_LOCK_SECONDS) - 1)
            entry[1] = datetime.utcnow() + timedelta(seconds=_LOCK_SECONDS[tier])


def _record_success(key: tuple[str, str]) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _make_token(user_id: int, role: str, entity_id: int | None) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "entity_id": entity_id,
        "exp": datetime.utcnow() + timedelta(days=_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


def get_current_user(
    token: Annotated[str, Depends(_oauth2)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise exc
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise exc
    return user


def get_current_admin(current: Annotated[User, Depends(get_current_user)]) -> User:
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    return current


@router.post("/login")
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
):
    """Password login, rate-limited per (identifiant, IP).

    Nothing capped the number of attempts before: a six-character minimum
    password with no complexity rule and no throttle is an offline-speed
    guess, online. The counter is keyed on the pair so that hammering one
    account does not lock out a colleague sharing an address, and so that a
    single client cannot walk the user list for free.

    The 429 deliberately says nothing about whether the identifiant exists —
    same reason the failure below returns one generic message."""
    key = _throttle_key(form.username, request)
    _check_not_locked(key)

    user = session.exec(select(User).where(User.username == form.username)).first()
    if not user or not _verify_pw(form.password, user.password_hash):
        _record_failure(key)
        raise HTTPException(status_code=400, detail="Identifiants incorrects")

    _record_success(key)
    return {
        "access_token": _make_token(user.id, user.role, user.entity_id),
        "token_type": "bearer",
    }


@router.get("/me")
def me(current: Annotated[User, Depends(get_current_user)]):
    return {
        "id": current.id,
        "username": current.username,
        "email": current.email,
        "role": current.role,
        "entity_id": current.entity_id,
    }


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    entity_name: Optional[str] = None   # créer une nouvelle entité, ou rejoindre "Demo"


@router.post("/register", status_code=201)
def register(body: RegisterRequest, session: Annotated[Session, Depends(get_session)]):
    if len(body.username) < 3:
        raise HTTPException(status_code=400, detail="L'identifiant doit faire au moins 3 caractères")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 6 caractères")
    if session.exec(select(User).where(User.username == body.username)).first():
        raise HTTPException(status_code=400, detail="Cet identifiant est déjà utilisé")
    if session.exec(select(User).where(User.email == body.email)).first():
        raise HTTPException(status_code=400, detail="Cet e-mail est déjà utilisé")

    # Entité : créer ou utiliser l'entité Demo par défaut
    entity_name = (body.entity_name or "").strip() or "Demo"
    entity = session.exec(select(Entity).where(Entity.name == entity_name)).first()
    if not entity:
        entity = Entity(name=entity_name)
        session.add(entity)
        session.flush()

    user = User(
        username=body.username,
        email=body.email,
        password_hash=_hash_pw(body.password),
        role="user",
        entity_id=entity.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {
        "access_token": _make_token(user.id, user.role, user.entity_id),
        "token_type": "bearer",
    }
