from typing import Annotated, Literal
import json
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from .auth import get_current_admin, get_current_user
from ..db.models import User
from ..services.agent_workshop.store import store, CampaignConfig
from ..services.agent_workshop.engine import manager

def controller_only():
    if os.environ.get("STRUCTURA_WORKSHOP_CHILD") == "1":
        raise HTTPException(403, "Une instance acteur ne pilote pas les campagnes de recette.")


routes = APIRouter(tags=["AI user acceptance"], dependencies=[Depends(controller_only)])
Owner = Annotated[User, Depends(get_current_user)]


def owned(key, admin):
    try: state = manager.snapshot(key)
    except (ValueError, FileNotFoundError): raise HTTPException(404, "Campagne introuvable.")
    if state["owner"] != admin.id:
        raise HTTPException(404, "Campagne introuvable.")
    return state


@routes.get("")
def listing(admin: Owner):
    rows = store.list(admin.id)
    for row in rows:
        if row['status'] in {'RUNNING','PAUSED','PAUSING','STOPPING'}:
            state = manager.snapshot(row['id'])
            row.update(status=state['status'],turns=state['turns'],business_date=state['business_date'],controller_active=state.get('controller_active'))
    return rows


@routes.get("/models")
def models(admin: Owner):
    import httpx
    try:
        response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5, trust_env=False)
        response.raise_for_status()
        return {"models": [x["name"] for x in response.json().get("models", [])], "provider": "Ollama local"}
    except Exception:
        return {"models": [], "error": "Ollama local indisponible. Démarrer Ollama avant la campagne."}


@routes.post("", status_code=201)
def create(body: CampaignConfig, admin: Owner):
    try: return store.create(body, admin.id)
    except ValueError as exc: raise HTTPException(422, str(exc))


@routes.get("/{key}")
def detail(key: str, admin: Owner):
    return owned(key, admin)


@routes.post("/{key}/{action}")
def command(key: str, action: Literal["start", "pause", "resume", "stop", "reset"], admin: Owner):
    owned(key, admin)
    try:
        if action == 'reset':
            fresh = manager.manage(key, admin.id, 'reset')
            return manager.snapshot(fresh['id'])
        if action == "start": manager.start(key)
        else: manager.control(key, action)
    except ValueError as exc: raise HTTPException(409, str(exc))
    except FileNotFoundError: raise HTTPException(404, 'Campagne introuvable.')
    except (OSError, RuntimeError, httpx.HTTPError): raise HTTPException(409, 'Les installations ou la sauvegarde ne sont pas disponibles ; opération annulée. Réessayer après leur fermeture.')
    return manager.snapshot(key)


@routes.delete('/{key}')
def delete(key: str, admin: Owner):
    owned(key, admin)
    try:
        return manager.manage(key, admin.id, 'delete')
    except ValueError as exc: raise HTTPException(409, str(exc))
    except FileNotFoundError: raise HTTPException(404, 'Campagne introuvable.')
    except (OSError, RuntimeError, httpx.HTTPError): raise HTTPException(409, 'Les installations ou la sauvegarde ne sont pas disponibles ; suppression annulée. Réessayer après leur fermeture.')


@routes.get("/{key}/export")
def export(key: str, admin: Owner):
    state = owned(key, admin)
    return Response(json.dumps(state, ensure_ascii=False, indent=2), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="recette-{key[:8]}.json"'})


@routes.get("/{key}/screenshots/{filename}")
def screenshot(key: str, filename: str, admin: Owner):
    owned(key, admin)
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".png"):
        raise HTTPException(404)
    path = store.path(key) / "screenshots" / filename
    if not path.is_file(): raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


router = APIRouter()
router.include_router(routes, prefix="/api/agent-workshop")
admin_router = APIRouter(dependencies=[Depends(get_current_admin)])
admin_router.include_router(routes, prefix="/api/admin/agent-workshop")
