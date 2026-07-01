from datetime import datetime, timedelta
from typing import Annotated, Optional
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Entity, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_SECRET = "structura-jwt-secret-change-in-prod"
_ALGO = "HS256"
_EXPIRE_DAYS = 7

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


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


@router.post("/login")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
):
    user = session.exec(select(User).where(User.username == form.username)).first()
    if not user or not _verify_pw(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Identifiants incorrects")
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
