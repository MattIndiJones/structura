"""Shared session policy; independent of business database initialization."""
import hashlib
import uuid
from datetime import datetime, timezone


def validate_password(password: str) -> str:
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise ValueError("Le mot de passe doit contenir au moins 12 caractères et au plus 72 octets UTF-8.")
    return password


def session_claims(version: int) -> dict:
    return {"jti": str(uuid.uuid4()), "iat": datetime.now(timezone.utc), "session_version": version}


def session_digest(payload: dict) -> str:
    identifier = payload.get("jti")
    if not isinstance(identifier, str) or len(identifier) != 36 or type(payload.get("session_version")) is not int:
        raise ValueError("Session antérieure ou invalide ; reconnectez-vous.")
    uuid.UUID(identifier)
    return hashlib.sha256(identifier.encode()).hexdigest()
