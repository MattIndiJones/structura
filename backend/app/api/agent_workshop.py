from typing import Annotated, Literal
import json
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .auth import get_current_admin, get_current_simulation_admin
from ..db.models import User
from ..services.agent_workshop.store import store, CampaignConfig
from ..services.agent_workshop.engine import manager
from ..services.agent_workshop.consultation import consultations
from ..services.agent_workshop.configuration import preview

def controller_only():
    if os.environ.get("STRUCTURA_WORKSHOP_CHILD") == "1":
        raise HTTPException(403, "Une instance acteur ne pilote pas les campagnes de recette.")


routes = APIRouter(tags=["AI user acceptance"], dependencies=[Depends(controller_only)])
Owner = Annotated[User, Depends(get_current_simulation_admin)]


def owned(key, admin):
    try: state = manager.snapshot(key)
    except (ValueError, FileNotFoundError): raise HTTPException(404, "Campagne introuvable.")
    if state["owner"] != admin.id:
        raise HTTPException(404, "Campagne introuvable.")
    state["consultations"] = consultations.status(key)
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
    from ..services.agent_workshop.openai_model import MODELS, DEFAULT_MODEL
    from ..services.llm.keys import load_key
    openai_ready = bool(load_key('openai'))
    providers = [{'key': 'openai', 'label': 'OpenAI · clé Structura existante',
        'ready': openai_ready, 'default_model': DEFAULT_MODEL,
        'models': [{'id': key, **value} for key, value in MODELS.items()],
        'hint': None if openai_ready else 'Clé OpenAI absente du processus de simulation.'}]
    try:
        response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5, trust_env=False)
        response.raise_for_status()
        installed = [x['name'] for x in response.json().get('models', [])]
        providers.insert(0, {'key': 'ollama', 'label': 'Ollama · local', 'ready': bool(installed),
            'default_model': installed[0] if installed else None,
            'models': [{'id': name, 'label': name} for name in installed], 'hint': None})
        return {'providers': providers, 'models': installed, 'provider': 'Ollama local'}
    except Exception:
        providers.insert(0, {'key': 'ollama', 'label': 'Ollama · local', 'ready': False,
            'default_model': None, 'models': [], 'hint': 'Ollama local indisponible.'})
        return {'providers': providers, 'models': [],
            'error': None if openai_ready else 'Ollama local indisponible et clé OpenAI absente.'}


@routes.post("", status_code=201)
def create(body: CampaignConfig, admin: Owner):
    try: return store.create(body, admin.id)
    except ValueError as exc: raise HTTPException(422, str(exc))


@routes.get('/defaults')
def defaults(admin: Owner):
    from ..services.agent_workshop.diagnostic import diagnostic_defaults
    return diagnostic_defaults()


@routes.post('/preview')
def preview_scenario(body: CampaignConfig, admin: Owner):
    if body.schema_version != 2:
        raise HTTPException(422, 'Prévisualisation réservée aux scénarios version 2.')
    return preview(body.model_dump())


@routes.patch('/{key}/configuration')
def configure(key: str, body: CampaignConfig, admin: Owner):
    owned(key, admin)
    try:
        return store.configure(key, admin.id, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@routes.get("/{key}")
def detail(key: str, admin: Owner):
    return owned(key, admin)


@routes.post("/{key}/{action}")
def command(key: str, action: Literal["start", "pause", "resume", "stop", "reset", "replay"], admin: Owner):
    owned(key, admin)
    try:
        if action in {'reset', 'replay'}:
            fresh = manager.manage(key, admin.id, action)
            return manager.snapshot(fresh['id'])
        if action == "start": manager.start(key)
        else: manager.control(key, action)
    except ValueError as exc: raise HTTPException(409, str(exc))
    except FileNotFoundError: raise HTTPException(404, 'Campagne introuvable.')
    except (OSError, RuntimeError, httpx.HTTPError): raise HTTPException(409, 'Les installations ou la sauvegarde ne sont pas disponibles ; opération annulée. Réessayer après leur fermeture.')
    return manager.snapshot(key)


class IssueReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['OPEN', 'IN_PROGRESS', 'CLOSED'] = 'OPEN'
    qualification: Literal['UNCONFIRMED', 'CONFIRMED_BUG', 'USAGE', 'EXPECTED_REFUSAL', 'HARNESS', 'MISSING', 'DATA'] = 'UNCONFIRMED'
    note: str = Field(default='', max_length=3000)

    @model_validator(mode='after')
    def require_diagnosis(self):
        self.note = self.note.strip()
        if (self.status == 'CLOSED' or self.qualification != 'UNCONFIRMED') and not self.note:
            raise ValueError('Préciser le diagnostic ou le motif de clôture.')
        return self


ConsultationActor = Literal['hector', 'bnp', 'ca', 'sg', 'ubs', 'leonteq', 'client']


@routes.post('/{key}/consultations/{actor}')
def open_consultation(key: str, actor: ConsultationActor, admin: Owner):
    owned(key, admin)
    try:
        return consultations.open(key, admin.id, actor)
    except FileNotFoundError:
        raise HTTPException(404, 'Campagne introuvable.')
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        raise HTTPException(409, str(exc))


@routes.delete('/{key}/consultations/{actor}')
def close_consultation(key: str, actor: ConsultationActor, admin: Owner):
    owned(key, admin)
    try:
        return consultations.close(key, admin.id, actor)
    except FileNotFoundError:
        raise HTTPException(404, 'Campagne introuvable.')
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        raise HTTPException(409, str(exc))


@routes.patch('/{key}/issues/{issue_id}')
def review_issue(key: str, issue_id: str, body: IssueReview, admin: Owner):
    owned(key, admin)
    try:
        return store.review_issue(key, admin.id, issue_id, body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except OSError:
        raise HTTPException(409, 'Le diagnostic n’a pas pu être enregistré. Réessayer.')


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
