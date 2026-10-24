"""Isolated simulation controller; only signed central administrative requests."""
import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from jose import JWTError, jwt

from .config import current_config
from .control_services import owned_stop
from .development import enabled


def request_signature(platform, controller, actor_id, method, path, body):
    payload = {"iss": str(platform.installation_id), "aud": str(controller.installation_id),
               "sub": str(actor_id), "purpose": "simulation_request", "method": method,
               "path": path, "body_sha256": hashlib.sha256(body).hexdigest(),
               "jti": str(uuid4()), "exp": datetime.now(timezone.utc) + timedelta(seconds=60)}
    return jwt.encode(payload, (platform.data_dir / ".developer_private.pem").read_text(encoding="utf-8"), algorithm="RS256")


def initialize_controller(config):
    with closing(sqlite3.connect(config.data_dir / "controller.db")) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {"controller_identity", "request_receipts"}:
            raise RuntimeError("Le contrôleur ne peut pas contenir de schéma métier privé.")
        connection.execute("CREATE TABLE IF NOT EXISTS controller_identity(id INTEGER PRIMARY KEY, installation_id TEXT UNIQUE)")
        connection.execute("CREATE TABLE IF NOT EXISTS request_receipts(ticket_id TEXT PRIMARY KEY, actor_id INTEGER NOT NULL, received_at TEXT NOT NULL)")
        previous = connection.execute("SELECT installation_id FROM controller_identity WHERE id=1").fetchone()
        if previous and previous[0] != str(config.installation_id):
            raise RuntimeError("Contrôleur appartenant à une autre installation.")
        connection.execute("INSERT OR IGNORE INTO controller_identity VALUES(1,?)", (str(config.installation_id),))
        connection.commit()


def create_app(config=None):
    config = config or current_config()
    if not config or config.service != "simulation_controller":
        raise RuntimeError("Manifeste de simulation explicite requis.")
    # The existing campaign/actor code is reused in this separate process. Its
    # authentication dependencies are replaced, not its business workflows.
    from ..api import agent_workshop
    from ..api.auth import get_current_admin, get_current_simulation_admin
    from ..services.agent_workshop.store import store
    from ..services.agent_workshop.engine import manager
    from ..services.agent_workshop.consultation import consultations
    store.root = config.data_dir / "campaigns"
    trust = json.loads((config.data_dir / ".developer_trust.json").read_text(encoding="utf-8"))

    @asynccontextmanager
    async def lifespan(app):
        initialize_controller(config)
        try:
            yield
        finally:
            await asyncio.to_thread(manager.shutdown)
            await asyncio.to_thread(consultations.shutdown)

    app = FastAPI(title="Structura — contrôleur de simulation isolé", lifespan=lifespan)

    async def delegated_admin(request: Request):
        if hasattr(request.state, "simulation_actor"):
            return request.state.simulation_actor
        if not enabled(config):
            raise HTTPException(404, "Simulation de développement désactivée.")
        authorization = request.headers.get("Authorization", "")
        try:
            if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"} or not authorization.startswith("Bearer "):
                raise ValueError("Caller")
            payload = jwt.decode(authorization[7:], trust["public_key"], algorithms=["RS256"],
                audience=str(config.installation_id), issuer=trust["installation_id"],
                options={"require_exp": True, "require_iss": True, "require_aud": True, "require_jti": True})
            path = request.url.path + ("?" + request.url.query if request.url.query else "")
            digest = hashlib.sha256(await request.body()).hexdigest()
            if payload.get("purpose") != "simulation_request" or payload.get("method") != request.method or payload.get("path") != path \
                    or not secrets.compare_digest(payload.get("body_sha256", ""), digest):
                raise ValueError("Request")
            actor_id = int(payload["sub"])
            if actor_id <= 0:
                raise ValueError("Identity")
        except (JWTError, ValueError, KeyError):
            raise HTTPException(401, "Délégation de simulation invalide ou expirée.")
        try:
            with closing(sqlite3.connect(config.data_dir / "controller.db")) as connection:
                connection.execute("INSERT INTO request_receipts VALUES(?,?,?)",
                    (payload["jti"], actor_id, datetime.now(timezone.utc).isoformat()))
                connection.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Cette délégation a déjà été utilisée.")
        request.state.simulation_actor = SimpleNamespace(id=actor_id, role="admin")
        return request.state.simulation_actor

    app.dependency_overrides[get_current_simulation_admin] = delegated_admin
    app.dependency_overrides[get_current_admin] = delegated_admin
    app.include_router(agent_workshop.router)
    app.include_router(agent_workshop.admin_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "kind": "simulation_controller", "instance_id": str(config.installation_id),
                "process_id": os.getpid(), "launch_id": os.environ.get("STRUCTURA_LAUNCH_ID"), "developer_access": enabled(config)}

    @app.post("/_instance/stop", include_in_schema=False)
    def stop(request: Request):
        return owned_stop(app, request)

    return app
