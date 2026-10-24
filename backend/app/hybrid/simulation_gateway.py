"""Administrative gateway only; never forwards manual organization APIs."""
import hashlib
import json
import re
import asyncio

import httpx
from fastapi import Depends, HTTPException, Request, Response

from .control_services import simulation_config
from .development import enabled
from .deployment import start, probe


def register_gateway(app, platform, admin, audit, connect):
    def require_development():
        if not enabled(platform):
            raise HTTPException(403, "Simulation limitée à l'administration de développement.")

    def controller():
        try:
            return simulation_config(platform)
        except (ValueError, OSError, RuntimeError):
            raise HTTPException(503, "Contrôleur non préparé. Ouvrez le lanceur Structura.")

    @app.post("/api/platform/simulation/start")
    async def start_simulation(user=Depends(admin)):
        require_development()
        config = controller()
        try:
            result = await asyncio.to_thread(start, config, developer_access=True)
        except (ValueError, OSError, RuntimeError):
            raise HTTPException(503, "Démarrage de la simulation indisponible. Consultez l'état dans le lanceur.")
        with connect(platform) as connection:
            audit(connection, user["id"], json.dumps({"action": "SIMULATION_CONTROLLER_START", "started": result["started"]}))
        return {"available": True}

    async def forward(request: Request, tail: str, user):
        require_development()
        if not re.fullmatch(r"(?:/[a-zA-Z0-9_.-]+)*", tail) or any(part in {".", ".."} for part in tail.split("/")):
            raise HTTPException(404)
        config = controller()
        if await asyncio.to_thread(probe, config) is None:
            raise HTTPException(503, "Simulation arrêtée. Ouvrez-la depuis l'administration centrale ou le lanceur.")
        path = "/api/agent-workshop" + tail + ("?" + request.url.query if request.url.query else "")
        body = await request.body()
        from .simulation import request_signature
        delegation = request_signature(platform, config, user["id"], request.method, path, body)
        with connect(platform) as connection:
            audit(connection, user["id"], json.dumps({"action": "SIMULATION_REQUEST", "method": request.method,
                "path": path, "body_sha256": hashlib.sha256(body).hexdigest()}))
        try:
            async with httpx.AsyncClient(timeout=150, trust_env=False, follow_redirects=False) as client:
                result = await client.request(request.method, config.public_descriptor()["url"] + path, content=body,
                    headers={"Authorization": "Bearer " + delegation, "Content-Type": request.headers.get("Content-Type", "application/json")})
        except httpx.HTTPError:
            raise HTTPException(503, "Le contrôleur n'a pas confirmé la réponse. Rechargez l'état avant de réessayer.")
        with connect(platform) as connection:
            audit(connection, user["id"], json.dumps({"action": "SIMULATION_RESPONSE", "method": request.method,
                "path": path, "status": result.status_code}))
        headers = {name: result.headers[name] for name in ("content-type", "content-disposition") if name in result.headers}
        return Response(result.content, status_code=result.status_code, headers=headers)

    @app.api_route("/api/agent-workshop", methods=["GET", "POST"])
    @app.api_route("/api/admin/agent-workshop", methods=["GET", "POST"])
    async def root(request: Request, user=Depends(admin)):
        return await forward(request, "", user)

    @app.api_route("/api/agent-workshop/{tail:path}", methods=["GET", "POST", "PATCH", "DELETE"])
    @app.api_route("/api/admin/agent-workshop/{tail:path}", methods=["GET", "POST", "PATCH", "DELETE"])
    async def resource(tail: str, request: Request, user=Depends(admin)):
        return await forward(request, "/" + tail, user)
