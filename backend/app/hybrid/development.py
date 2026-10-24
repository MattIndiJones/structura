"""Explicit loopback-only development access; no organization password broker."""
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict

from .config import current_config


class DevelopmentTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: str
    username: str = "superuser"
    start_if_needed: bool = False


class DevelopmentTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str


def enabled(config=None):
    config = config or current_config()
    return bool(config and config.environment == "DEVELOPMENT"
                and os.environ.get("STRUCTURA_DEVELOPER_ACCESS") == "1")


def origins(config):
    if config.kind == "platform":
        url = config.public_descriptor()["url"]
    else:
        url = json.loads((config.data_dir / ".developer_trust.json").read_text(encoding="utf-8"))["url"]
    return [url, url.replace("127.0.0.1", "localhost"), "http://localhost:5173", "http://127.0.0.1:5173"]


def add_portal_cors(app, config):
    """Password login and API calls need the configured portal in every mode."""
    if config:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware, allow_origins=origins(config),
                           allow_methods=["*"], allow_headers=["*"], allow_credentials=False)


def require_access(request: Request, config):
    if not enabled(config):
        raise HTTPException(404, "Accès développeur désactivé.")
    if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Accès développeur limité au poste local.")
    origin = request.headers.get("origin")
    if origin and origin not in origins(config):
        raise HTTPException(403, "Origine du portail non autorisée.")
    if request.headers.get("sec-fetch-site") == "cross-site" and origin not in origins(config):
        raise HTTPException(403, "Origine du portail non autorisée.")
    if request.method == "POST" and request.headers.get("X-Structura-Development") != "1":
        raise HTTPException(403, "Requête développeur explicite requise.")


def issue(config, target_id, organization_id, username, origin):
    now = datetime.now(timezone.utc)
    payload = {"iss": str(config.installation_id), "aud": target_id, "sub": username,
               "organization_id": organization_id, "purpose": "development_access",
               "jti": str(uuid4()), "iat": now, "exp": now + timedelta(seconds=60),
               "developer_origin": origin}
    key = (config.data_dir / ".developer_private.pem").read_text(encoding="utf-8")
    return jwt.encode(payload, key, algorithm="RS256"), payload["jti"]


def verify(config, ticket):
    trust = json.loads((config.data_dir / ".developer_trust.json").read_text(encoding="utf-8"))
    try:
        payload = jwt.decode(ticket, trust["public_key"], algorithms=["RS256"],
            audience=str(config.installation_id), issuer=trust["installation_id"],
            options={"require_exp": True, "require_aud": True, "require_iss": True, "require_iat": True, "require_jti": True})
        if payload.get("purpose") != "development_access" or payload.get("organization_id") != str(config.organization_id):
            raise ValueError("Scope")
        if payload.get("sub") not in {"superuser", "front", "operations", "controller"}:
            raise ValueError("Account")
        return payload
    except (JWTError, ValueError, KeyError):
        raise HTTPException(401, "Accès développeur invalide ou expiré.")
