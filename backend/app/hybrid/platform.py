"""Central directory only: separate schema, signing key and administrative scope."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager, asynccontextmanager
import json
import os
import secrets
import sqlite3
import threading
import asyncio
from pathlib import Path
from typing import Annotated

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import credentials, current_config, signing_secret, DirectoryEntry
from .development import DevelopmentTarget, enabled, origins, require_access, issue
from ..core.session_security import session_claims, session_digest, validate_password
from pydantic import BaseModel, field_validator


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    _validate = field_validator("new_password")(validate_password)


@contextmanager
def connect(config):
    connection = sqlite3.connect(config.data_dir / "platform.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(config):
    if config.kind != "platform":
        raise RuntimeError("Le schéma central ne peut pas être créé dans une installation métier.")
    password = credentials(config)["admin"]
    directory = [DirectoryEntry.model_validate(item).model_dump(mode="json") for item in
                 json.loads((config.data_dir / "directory.json").read_text(encoding="utf-8"))]
    if len(directory) != 6 or len({d["installation_id"] for d in directory}) != 6 or len({d["organization_id"] for d in directory}) != 6:
        raise RuntimeError("L'annuaire de développement doit contenir six installations et organisations distinctes.")
    with connect(config) as connection:
        allowed = {"platform_identity", "platform_users", "platform_installations", "platform_audit", "platform_revoked_sessions"}
        present = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'")}
        if present - allowed:
            raise RuntimeError("Base centrale non identifiée ou contenant un schéma métier ; initialisation refusée.")
        existing = connection.execute("SELECT installation_id FROM platform_identity WHERE id=1").fetchone() if "platform_identity" in present else None
        if existing and existing[0] != str(config.installation_id):
            raise RuntimeError("La base centrale appartient à une autre installation.")
        if not existing and any(connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() for table in present):
            raise RuntimeError("Base centrale occupée sans identité ; aucune migration appliquée.")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS platform_identity(id INTEGER PRIMARY KEY CHECK(id=1), installation_id TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS platform_users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role='platform_admin'), active INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_installations(installation_id TEXT PRIMARY KEY, descriptor_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_audit(id INTEGER PRIMARY KEY, actor_id INTEGER,
                action TEXT NOT NULL, received_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_revoked_sessions(token_digest TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(platform_users)")}
        if "auth_version" not in columns:
            connection.execute("ALTER TABLE platform_users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")
        existing = connection.execute("SELECT installation_id FROM platform_identity WHERE id=1").fetchone()
        if existing and existing[0] != str(config.installation_id):
            raise RuntimeError("La base centrale appartient à une autre installation.")
        connection.execute("INSERT OR IGNORE INTO platform_identity VALUES(1,?)", (str(config.installation_id),))
        connection.execute("INSERT OR IGNORE INTO platform_users(username,password_hash,role,active) VALUES(?,?,?,1)",
            ("admin", bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(), "platform_admin"))
        for descriptor in directory:
            connection.execute("INSERT INTO platform_installations VALUES(?,?) ON CONFLICT(installation_id) DO UPDATE SET descriptor_json=excluded.descriptor_json",
                (descriptor["installation_id"], json.dumps(descriptor, ensure_ascii=False)))
    return {"accounts": 1, "registry_state": "NOT_CONFIGURED", "billing_enabled": False}


def create_app():
    config = current_config()
    if not config or config.kind != "platform":
        raise RuntimeError("Manifeste central explicite requis.")
    secret = signing_secret(config)
    @asynccontextmanager
    async def lifespan(app):
        initialize(config)
        yield
    app = FastAPI(title="Structura — plateforme locale de développement", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=origins(config),
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Structura-Development"])
    oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    attempts, lock = {}, threading.Lock()

    def audit(connection, actor_id, action):
        connection.execute("INSERT INTO platform_audit(actor_id,action,received_at) VALUES(?,?,?)",
            (actor_id, action, datetime.now(timezone.utc).isoformat()))

    def admin(token: Annotated[str, Depends(oauth)]):
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"], audience=str(config.installation_id),
                issuer=str(config.installation_id), options={"require_exp": True, "require_aud": True, "require_iss": True})
            with connect(config) as connection:
                digest = session_digest(payload)
                user = connection.execute("SELECT * FROM platform_users WHERE id=? AND active=1", (int(payload["sub"]),)).fetchone()
                revoked = connection.execute("SELECT 1 FROM platform_revoked_sessions WHERE token_digest=?", (digest,)).fetchone()
            if not user or user["role"] != "platform_admin" or user["auth_version"] != payload["session_version"] or revoked:
                raise ValueError("Session revoked")
            return dict(user)
        except (JWTError, ValueError, KeyError, TypeError):
            raise HTTPException(401, "Session centrale invalide ou expirée", headers={"WWW-Authenticate": "Bearer"})

    def make_token(user, **extra):
        return jwt.encode({"sub": str(user["id"]), "iss": str(config.installation_id),
            "aud": str(config.installation_id), "exp": datetime.now(timezone.utc) + timedelta(days=7),
            **session_claims(user["auth_version"]), **extra}, secret, algorithm="HS256")

    @app.post("/api/auth/logout", status_code=204)
    def logout(token: Annotated[str, Depends(oauth)], user=Depends(admin)):
        payload = jwt.get_unverified_claims(token)
        with connect(config) as connection:
            connection.execute("INSERT OR IGNORE INTO platform_revoked_sessions VALUES(?,?)", (session_digest(payload), payload["exp"]))
            audit(connection, user["id"], "LOGOUT")

    @app.post("/api/auth/logout-all", status_code=204)
    def logout_all(user=Depends(admin)):
        with connect(config) as connection:
            connection.execute("UPDATE platform_users SET auth_version=auth_version+1 WHERE id=?", (user["id"],))
            audit(connection, user["id"], "LOGOUT_ALL")

    @app.post("/api/auth/password", status_code=204)
    def change_password(body: PasswordChange, user=Depends(admin)):
        try:
            valid = bcrypt.checkpw(body.current_password.encode(), user["password_hash"].encode())
        except ValueError:
            valid = False
        with connect(config) as connection:
            if not valid or body.current_password == body.new_password:
                audit(connection, user["id"], "PASSWORD_CHANGE_REJECTED")
                connection.commit()
                raise HTTPException(400, "Mot de passe actuel incorrect ou nouveau mot de passe inchangé.")
            connection.execute("UPDATE platform_users SET password_hash=?,auth_version=auth_version+1 WHERE id=?",
                (bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode(), user["id"]))
            audit(connection, user["id"], "PASSWORD_CHANGE")

    @app.get("/health")
    def health():
        return {"status": "ok", "instance_id": str(config.installation_id), "process_id": os.getpid(),
                "launch_id": os.environ.get("STRUCTURA_LAUNCH_ID"), "kind": "platform", "registry_state": "NOT_CONFIGURED",
                "developer_access": enabled(config)}

    @app.post("/_instance/stop", include_in_schema=False)
    def stop(request: Request):
        expected = os.environ.get("STRUCTURA_INSTANCE_CONTROL_TOKEN", "")
        if not expected or not secrets.compare_digest(expected, request.headers.get("X-Instance-Control", "")):
            raise HTTPException(404)
        app.state.instance_server.should_exit = True
        return {"stopping": True}

    @app.post("/api/auth/login")
    def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
        key = (request.client.host if request.client else "?", form.username)
        now = datetime.now(timezone.utc)
        with lock:
            count, until = attempts.get(key, (0, now))
            if until > now:
                raise HTTPException(429, "Trop de tentatives ; réessayez plus tard.")
        with connect(config) as connection:
            user = connection.execute("SELECT * FROM platform_users WHERE username=? AND active=1", (form.username,)).fetchone()
            try:
                valid = user is not None and bcrypt.checkpw(form.password.encode(), user["password_hash"].encode())
            except ValueError:
                valid = False
            if not valid:
                with lock:
                    count += 1
                    attempts[key] = (count, now + timedelta(seconds=60 if count >= 5 else 0))
                audit(connection, user["id"] if user else None, json.dumps({"action": "LOGIN_REJECTED", "username": form.username[:128], "installation_id": str(config.installation_id), "client_ip": key[0]}))
                connection.commit()
                raise HTTPException(400, "Identifiants incorrects")
            with lock:
                attempts.pop(key, None)
            audit(connection, user["id"], "LOGIN")
            token = make_token(user)
        return {"access_token": token, "token_type": "bearer"}

    @app.get("/api/auth/options")
    def login_options():
        result = {"registration_enabled": False, "installation_portal": True}
        if enabled(config):
            from .config import read_config
            directory = config.data_dir.parent / "admin-workbench"
            try:
                workbench = read_config(str(directory / "installation.json"))
                if workbench.service == "admin_workbench" and workbench.data_dir == directory:
                    result["admin_workbench_url"] = workbench.public_descriptor()["url"]
            except (OSError, ValueError, RuntimeError):
                pass
        return result

    @app.get("/api/auth/identity")
    def login_identity():
        return {"installation": config.public_descriptor()}

    @app.get("/api/platform/login-options")
    def password_login_options():
        with connect(config) as connection:
            rows = connection.execute("SELECT descriptor_json FROM platform_installations ORDER BY rowid").fetchall()
        keys = ("installation_id", "organization_id", "kind", "name", "key", "url")
        return {"installations": [{key: item[key] for key in keys}
                for item in [*[json.loads(row[0]) for row in rows], config.public_descriptor()]]}

    @app.get("/api/auth/me")
    def me(user=Depends(admin)):
        return {"id": user["id"], "username": user["username"], "role": "platform_admin",
                "profile": "central_admin", "installation": config.public_descriptor(),
                "capabilities": ["directory.read", *(["simulation.manage", "installations.manage"] if enabled(config) else [])],
                "developer_access": enabled(config)}

    @app.get("/api/platform/development/access")
    def development_access(request: Request):
        if not enabled(config):
            return {"enabled": False, "installations": []}
        require_access(request, config)
        with connect(config) as connection:
            rows = connection.execute("SELECT descriptor_json FROM platform_installations ORDER BY rowid").fetchall()
        return {"enabled": True, "installations": [json.loads(row[0]) for row in rows] + [config.public_descriptor()]}

    @app.post("/api/platform/development/admin-workbench")
    def open_admin_workbench(request: Request):
        require_access(request, config)
        from .control_services import prepare_controls
        from .deployment import start
        workbench = prepare_controls(config)["admin-workbench"]
        result = start(workbench, developer_access=True)
        with connect(config) as connection:
            audit(connection, None, json.dumps({"action": "OPEN_DEVELOPMENT_ADMIN_WORKBENCH",
                "installation_id": str(workbench.installation_id), "started": result["started"]}))
        return {"url": workbench.public_descriptor()["url"] + "/#/login?development_admin=1"}

    @app.post("/api/platform/development/session")
    def development_session(body: DevelopmentTarget, request: Request):
        require_access(request, config)
        with connect(config) as connection:
            # Keep a prior central identity as the origin when opening a test
            # context. Anonymous card access is identified explicitly.
            actor_id = None
            authorization = request.headers.get("authorization", "")
            if authorization.startswith("Bearer "):
                actor_id = admin(authorization[7:])["id"]
            origin = {"kind": "CENTRAL_ADMIN" if actor_id else "DEVELOPMENT_PORTAL",
                      "platform_installation_id": str(config.installation_id), "actor_id": actor_id}
            if body.installation_id == str(config.installation_id):
                if body.username != "admin":
                    raise HTTPException(403, "Compte central non autorisé.")
                user = connection.execute("SELECT * FROM platform_users WHERE username='admin' AND active=1").fetchone()
                if not user:
                    raise HTTPException(403, "Compte central indisponible.")
                token = make_token(user, developer_origin=origin)
                audit(connection, user["id"], json.dumps({"action": "DEVELOPMENT_LOGIN", "origin": origin}))
                return {"access_token": token, "installation": config.public_descriptor()}
            if body.username not in {"superuser", "front", "operations", "controller"}:
                raise HTTPException(403, "Profil de développement non autorisé.")
            row = connection.execute("SELECT descriptor_json FROM platform_installations WHERE installation_id=?", (body.installation_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Installation inconnue.")
            descriptor = json.loads(row[0])
            if body.start_if_needed:
                from .deployment import load_layout, start
                try:
                    target = next((item for item in load_layout(config.data_dir.parent)
                                   if str(item.installation_id) == body.installation_id and item.kind == "organization"), None)
                    if not target or target.public_descriptor() != descriptor:
                        raise ValueError("Directory and local manifest differ")
                    result = start(target, developer_access=True)
                except (OSError, ValueError, RuntimeError):
                    raise HTTPException(503, "Installation indisponible. Réessayez ou revenez à Structura Admin.")
                audit(connection, actor_id, json.dumps({"action": "DEVELOPMENT_INSTALLATION_START",
                    "key": target.key, "started": result["started"]}))
            ticket, ticket_id = issue(config, body.installation_id, descriptor["organization_id"], body.username, origin)
            audit(connection, actor_id, json.dumps({"action": "DEVELOPMENT_GRANT", "ticket_id": ticket_id,
                "installation_id": body.installation_id, "username": body.username, "origin": origin}))
            return {"ticket": ticket, "installation": descriptor}

    @app.get("/api/platform/installations")
    def directory(user=Depends(admin)):
        with connect(config) as connection:
            rows = connection.execute("SELECT descriptor_json FROM platform_installations ORDER BY installation_id").fetchall()
            audit(connection, user["id"], "DIRECTORY_READ")
        return {"installations": [json.loads(row[0]) for row in rows],
                "registry_state": "NOT_CONFIGURED", "billing_enabled": False}

    @app.get("/api/platform/status")
    async def status(user=Depends(admin)):
        if not enabled(config):
            raise HTTPException(403, "Supervision locale de développement désactivée.")
        from .deployment import load_layout, probe
        from .control_services import simulation_config
        configs = load_layout(config.data_dir.parent)
        try:
            configs.append(simulation_config(config))
        except (OSError, ValueError, RuntimeError):
            pass
        values = await asyncio.gather(*(asyncio.to_thread(probe, item) for item in configs))
        with connect(config) as connection:
            audit(connection, user["id"], "INSTALLATION_STATUS_READ")
        return {"services": [{"key": item.key, "name": item.name, "port": item.port,
            "state": "RUNNING" if health else "STOPPED_OR_UNAVAILABLE", "process_id": health.get("process_id") if health else None}
            for item, health in zip(configs, values)]}

    @app.post("/api/platform/installations/{key}/start")
    async def start_organization(key: str, user=Depends(admin)):
        if not enabled(config):
            raise HTTPException(403, "Accès de développement désactivé.")
        from .deployment import load_layout, start
        target = next((item for item in load_layout(config.data_dir.parent) if item.kind == "organization" and item.key == key), None)
        if not target:
            raise HTTPException(404, "Organisation inconnue.")
        try:
            result = await asyncio.to_thread(start, target, developer_access=True)
        except (RuntimeError, OSError, ValueError):
            raise HTTPException(503, "Installation indisponible. Consultez l'état dans le lanceur.")
        with connect(config) as connection:
            audit(connection, user["id"], json.dumps({"action": "DEVELOPMENT_INSTALLATION_START", "key": key, "started": result["started"]}))
        return {"available": True}

    from .simulation_gateway import register_gateway
    register_gateway(app, config, admin, audit, connect)

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

        @app.get("/tp_logo.png", include_in_schema=False)
        def logo():
            return FileResponse(dist / "tp_logo.png", media_type="image/png")

        @app.get("/", include_in_schema=False)
        def portal():
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    return app
