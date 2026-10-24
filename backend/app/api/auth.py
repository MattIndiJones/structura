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
from sqlalchemy import update
from ..db.database import get_session
from ..db.models import Entity, User, RevokedSession
from ..core.session_security import session_claims, session_digest, validate_password
from ..core.audit import record_audit_event
from pydantic import field_validator
from ..core.workflow import amendment_four_eyes_enabled
from ..core.access import capabilities, is_local_admin, profile, require_managed_capability, require_capability
from ..hybrid.config import current_config, signing_secret
from ..hybrid.development import DevelopmentTicket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

from ..runtime import consultation_mode
from ..core import consultation_sessions
from ..core.instance_signing import (
    _LEAKED_SECRET, _SECRET_FILE, _load_secret, process_secret, receipt_signing_secret,
)

_SECRET = process_secret()
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
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def _identity_config():
    from ..hybrid.admin_workbench import config as workbench_config
    return current_config() or workbench_config()


def _make_token(user_id: int, role: str, entity_id: int | None, developer_origin=None, *, auth_version=0) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "entity_id": entity_id,
        "exp": datetime.utcnow() + timedelta(days=_EXPIRE_DAYS),
        **session_claims(auth_version),
    }
    config = _identity_config()
    if config:
        payload.update(iss=str(config.installation_id), aud=str(config.installation_id),
                       organization_id=str(config.organization_id))
    if developer_origin:
        payload["developer_origin"] = developer_origin
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


def get_current_user(
    token: Annotated[str, Depends(_oauth2)],
    session: Annotated[Session, Depends(get_session)],
    request: Request = None,
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        config = _identity_config()
        options = {"require_exp": True, **({"require_iss": True, "require_aud": True} if config else {})}
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO], options=options,
            **({"issuer": str(config.installation_id), "audience": str(config.installation_id)} if config else {}))
        user_id = int(payload["sub"])
        digest = session_digest(payload)
    except (JWTError, KeyError, ValueError, TypeError):
        raise exc
    user = consultation_sessions.load_user(session, user_id=user_id) if consultation_mode() else session.get(User, user_id)
    revoked = consultation_sessions.revoked(digest) if consultation_mode() else session.get(RevokedSession, digest)
    if not user or not user.is_active or payload["session_version"] != user.auth_version or revoked:
        raise exc
    if current_config():
        from ..hybrid.business import HybridBootstrap
        marker = session.get(HybridBootstrap, 1)
        if not marker or marker.installation_id != str(config.installation_id) or user.entity_id != marker.entity_id \
                or payload.get("organization_id") != str(config.organization_id) or user.role not in {"organization_admin", "user", "ops_maker", "checker"}:
            raise exc
    elif config:
        from ..hybrid.admin_workbench import AdminWorkbenchIdentity
        marker = session.get(AdminWorkbenchIdentity, 1)
        if not marker or marker.installation_id != str(config.installation_id):
            raise exc
    if user.password_change_required and request and request.url.path not in {
            "/api/auth/me", "/api/auth/password", "/api/auth/logout", "/api/auth/logout-all"}:
        raise HTTPException(403, "Changez le mot de passe provisoire avant de poursuivre.")
    return user


def revoke_user_sessions(session: Session, user: User):
    """Atomic epoch increment: concurrent revocations must never restore a session."""
    session.add(user)
    session.flush()
    session.execute(update(User).where(User.id == user.id).values(auth_version=User.auth_version + 1))
    session.refresh(user)


def _session_audit(session, action, user, request, *, result="SUCCESS", username=None):
    import uuid
    config = _identity_config()
    if consultation_mode():
        consultation_sessions.audit({"action": action, "result": result, "user_id": user.id if user else None,
                                    "username": user.username if user else (username or "")[:128],
                                    "correlation_id": str(uuid.uuid4()), "installation_id": os.environ.get("STRUCTURA_INSTANCE_ID"),
                                    "client_ip": request.client.host if request.client else None})
        return
    record_audit_event(session, action=action, object_type="SESSION", object_id=user.id if user else None,
        actor_user_id=user.id if user else None, result=result, correlation_id=str(uuid.uuid4()),
        metadata={"installation_id": str(config.installation_id) if config else "standalone",
                  "username": user.username if user else (username or "")[:128],
                  "client_ip": request.client.host if request.client else None})


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    _validate = field_validator("new_password")(validate_password)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, request: Request,
                    current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    if consultation_mode():
        raise HTTPException(403, "Le book consulté reste en lecture seule.")
    if not _verify_pw(body.current_password, current.password_hash) or body.current_password == body.new_password:
        _session_audit(session, "PASSWORD_CHANGE", current, request, result="REJECTED")
        session.commit()
        raise HTTPException(400, "Mot de passe actuel incorrect ou nouveau mot de passe inchangé.")
    current.password_hash = _hash_pw(body.new_password)
    current.password_change_required = False
    revoke_user_sessions(session, current)
    _session_audit(session, "PASSWORD_CHANGE", current, request)
    session.commit()


@router.post("/logout", status_code=204)
def logout(request: Request, current: Annotated[User, Depends(get_current_user)],
           token: Annotated[str, Depends(_oauth2)], session: Annotated[Session, Depends(get_session)]):
    payload = jwt.get_unverified_claims(token)  # Already verified by get_current_user.
    if consultation_mode():
        consultation_sessions.audit({"action": "LOGOUT", "user_id": current.id},
                                    digest=session_digest(payload), expires_at=payload["exp"])
        return
    session.merge(RevokedSession(token_digest=session_digest(payload), user_id=current.id,
                                expires_at=datetime.utcfromtimestamp(payload["exp"])))
    _session_audit(session, "LOGOUT", current, request)
    session.commit()


@router.post("/logout-all", status_code=204)
def logout_all(request: Request, current: Annotated[User, Depends(get_current_user)],
               session: Annotated[Session, Depends(get_session)]):
    if consultation_mode():
        consultation_sessions.audit({"action": "LOGOUT_ALL", "user_id": current.id}, revoke_user_id=current.id)
        return
    revoke_user_sessions(session, current)
    _session_audit(session, "LOGOUT_ALL", current, request)
    session.commit()


def get_current_admin(current: Annotated[User, Depends(get_current_user)], request: Request = None) -> User:
    if not is_local_admin(current):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    if current_config() and request and request.url.path.startswith("/api/admin/browse"):
        raise HTTPException(403, "Le navigateur SQL technique n'est pas accessible au super utilisateur métier.")
    return current


def get_current_pricer(current: Annotated[User, Depends(get_current_user)]) -> User:
    require_capability(current, "business.price")
    return current


def get_current_simulation_admin(current: Annotated[User, Depends(get_current_user)]) -> User:
    if current.role != "admin" or current_config():
        raise HTTPException(403, "Simulation réservée à l'administration technique, hors installation métier.")
    return current


@router.get("/options")
def login_options():
    from ..hybrid.admin_workbench import options
    return {"registration_enabled": not current_config() and os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") == "simulation"
            and os.environ.get("STRUCTURA_WORKSHOP_CHILD") == "1"
            and os.environ.get("STRUCTURA_ALLOW_REGISTRATION", "").lower() in {"1", "true", "yes"}, **options()}


@router.get("/identity")
def login_identity():
    config = _identity_config()
    return {"installation": config.public_descriptor() if config else None}


@router.post("/development-admin-session", include_in_schema=False)
def development_admin_session(request: Request):
    from ..hybrid.admin_workbench import login
    return login(request)


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
    user = consultation_sessions.load_user(session, username=form.username) if consultation_mode() else session.exec(select(User).where(User.username == form.username)).first()
    try:
        _check_not_locked(key)
    except HTTPException:
        _session_audit(session, "LOGIN_THROTTLED", user, request, result="REJECTED", username=form.username)
        session.commit()
        raise
    if not user or not user.is_active or not _verify_pw(form.password, user.password_hash):
        _record_failure(key)
        _session_audit(session, "LOGIN", user, request, result="REJECTED", username=form.username)
        session.commit()
        raise HTTPException(status_code=400, detail="Identifiants incorrects")

    _record_success(key)
    identity = (user.id, user.role, user.entity_id, user.auth_version)
    _session_audit(session, "LOGIN", user, request)
    session.commit()
    return {
        "access_token": _make_token(*identity[:3], auth_version=identity[3]),
        "token_type": "bearer",
    }


@router.post("/development-session")
def development_session(body: DevelopmentTicket,
                        request: Request, session: Annotated[Session, Depends(get_session)]):
    from ..hybrid.development import require_access, verify
    from ..hybrid.business import HybridBootstrap, ROLES, DevelopmentRedemption
    from ..core.audit import record_audit_event
    from sqlalchemy.exc import IntegrityError
    import json
    config = current_config()
    require_access(request, config)
    payload = verify(config, body.ticket)
    marker = session.get(HybridBootstrap, 1)
    user = session.exec(select(User).where(User.username == payload["sub"])).first()
    if not marker or not user or not user.is_active or user.entity_id != marker.entity_id or user.role != ROLES[payload["sub"]]:
        raise HTTPException(403, "Ce compte ou son profil de développement est indisponible.")
    origin = payload["developer_origin"]
    session.add(DevelopmentRedemption(ticket_id=payload["jti"], user_id=user.id, origin_json=json.dumps(origin)))
    record_audit_event(session, action="DEVELOPMENT_LOGIN", object_type="SESSION", object_id=None,
        actor_user_id=user.id, result="SUCCESS", correlation_id=payload["jti"],
        metadata={"effective_username": user.username, "effective_role": user.role, "developer_origin": origin})
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Cet accès développeur a déjà été utilisé.")
    return {"access_token": _make_token(user.id, user.role, user.entity_id, origin, auth_version=user.auth_version), "token_type": "bearer"}


@router.get("/me")
def me(current: Annotated[User, Depends(get_current_user)], token: Annotated[str, Depends(_oauth2)]):
    from ..runtime import consultation_mode, business_today
    from ..hybrid.development import enabled
    config = current_config()
    origin = jwt.get_unverified_claims(token).get("developer_origin") if config else None
    from ..hybrid.admin_workbench import options
    return {
        **options(),
        "id": current.id,
        "username": current.username,
        "email": current.email,
        "password_change_required": current.password_change_required,
        "role": current.role,
        "entity_id": current.entity_id,
        "profile": profile(current),
        "capabilities": capabilities(current),
        "installation": _identity_config().public_descriptor() if _identity_config() else None,
        "developer_access": enabled(config),
        "developer_origin": origin,
        # Deployment-wide governance, not a per-user right: the UI needs it to
        # decide whether an amendment must be handed to somebody else or can be
        # carried through by whoever opened it (see core/workflow.py).
        "amendment_four_eyes": amendment_four_eyes_enabled(),
        "read_only": consultation_mode(),
        "consultation": {"entity": os.environ.get("STRUCTURA_CONSULTATION_ENTITY", ""),
                         "date": business_today().isoformat()} if consultation_mode() else None,
    }


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    entity_name: Optional[str] = None   # créer une nouvelle entité, ou rejoindre "Demo"
    _validate = field_validator("password")(validate_password)


@router.post("/register", status_code=201)
def register(body: RegisterRequest, session: Annotated[Session, Depends(get_session)]):
    if current_config():
        raise HTTPException(403, "Admission locale par un administrateur de l'organisation requise.")
    if os.environ.get("STRUCTURA_ALLOW_REGISTRATION", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(403, "Inscription publique désactivée. Contactez un administrateur.")
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
        "access_token": _make_token(user.id, user.role, user.entity_id, auth_version=user.auth_version),
        "token_type": "bearer",
    }
