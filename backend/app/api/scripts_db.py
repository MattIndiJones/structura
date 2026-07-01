from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, or_
from ..db.database import get_session
from ..db.models import Script, User, Folder
from .auth import get_current_user

router = APIRouter(prefix="/api/db/scripts", tags=["scripts-db"])


class ScriptCreate(BaseModel):
    name: str
    description: str = ""
    folder_id: int | None = None
    script_text: str = ""
    params_json: str = "{}"
    constats_json: str = "{}"
    global_params_json: str = "{}"
    category: str = ""
    tags: str = ""
    is_shared: bool = False


class ScriptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    folder_id: int | None = None
    script_text: str | None = None
    params_json: str | None = None
    constats_json: str | None = None
    global_params_json: str | None = None
    category: str | None = None
    tags: str | None = None
    is_shared: bool | None = None


def _row(s: Script, owner_name: str) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "folder_id": s.folder_id,
        "user_id": s.user_id,
        "owner": owner_name,
        "script_text": s.script_text,
        "params_json": s.params_json,
        "constats_json": s.constats_json,
        "global_params_json": s.global_params_json,
        "category": s.category,
        "tags": s.tags,
        "is_shared": s.is_shared,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


@router.get("")
def list_scripts(
    folder_id: int | None = None,
    current: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """Return scripts owned by current user + scripts shared within same entity."""
    stmt = select(Script).where(
        or_(
            Script.user_id == current.id,
            Script.is_shared == True,          # noqa: E712
        )
    )
    if folder_id is not None:
        stmt = stmt.where(Script.folder_id == folder_id)
    scripts = session.exec(stmt).all()

    # For shared scripts, filter to same entity
    entity_id = current.entity_id
    owners: dict[int, str] = {}

    def get_owner(uid: int) -> str:
        if uid not in owners:
            u = session.get(User, uid)
            owners[uid] = u.username if u else "?"
        return owners[uid]

    result = []
    for s in scripts:
        if s.user_id != current.id and s.is_shared:
            owner = session.get(User, s.user_id)
            if not owner or owner.entity_id != entity_id:
                continue
        result.append(_row(s, get_owner(s.user_id)))

    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


@router.post("", status_code=201)
def create_script(
    body: ScriptCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if body.folder_id:
        f = session.get(Folder, body.folder_id)
        if not f or f.user_id != current.id:
            raise HTTPException(404, "Dossier introuvable")
    s = Script(
        name=body.name.strip(),
        description=body.description,
        folder_id=body.folder_id,
        user_id=current.id,
        script_text=body.script_text,
        params_json=body.params_json,
        constats_json=body.constats_json,
        global_params_json=body.global_params_json,
        category=body.category,
        tags=body.tags,
        is_shared=body.is_shared,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return _row(s, current.username)


@router.get("/{script_id}")
def get_script(
    script_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script introuvable")
    if s.user_id != current.id:
        if not s.is_shared:
            raise HTTPException(403, "Accès refusé")
        owner = session.get(User, s.user_id)
        if not owner or owner.entity_id != current.entity_id:
            raise HTTPException(403, "Accès refusé")
    owner_name = (session.get(User, s.user_id) or User(username="?")).username
    return _row(s, owner_name)


@router.put("/{script_id}")
def update_script(
    script_id: int,
    body: ScriptUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(Script, script_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Script introuvable ou accès refusé")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    return _row(s, current.username)


@router.delete("/{script_id}", status_code=204)
def delete_script(
    script_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(Script, script_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Script introuvable ou accès refusé")
    session.delete(s)
    session.commit()
