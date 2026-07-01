from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Folder, User
from .auth import get_current_user

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str


def _build_tree(folders: list[Folder]) -> list[dict]:
    """Return flat list with computed depth for frontend rendering."""
    by_id = {f.id: f for f in folders}
    result = []

    def depth(fid):
        d, cur = 0, fid
        while cur and by_id.get(cur) and by_id[cur].parent_id:
            cur = by_id[cur].parent_id
            d += 1
            if d > 20:
                break
        return d

    for f in sorted(folders, key=lambda x: x.name):
        result.append({
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "depth": depth(f.id),
            "created_at": f.created_at.isoformat(),
        })
    result.sort(key=lambda x: (x["depth"], x["name"]))
    return result


@router.get("")
def list_folders(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    folders = session.exec(select(Folder).where(Folder.user_id == current.id)).all()
    return _build_tree(list(folders))


@router.post("", status_code=201)
def create_folder(
    body: FolderCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if body.parent_id:
        parent = session.get(Folder, body.parent_id)
        if not parent or parent.user_id != current.id:
            raise HTTPException(404, "Dossier parent introuvable")
    f = Folder(name=body.name.strip(), parent_id=body.parent_id, user_id=current.id)
    session.add(f)
    session.commit()
    session.refresh(f)
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "depth": 0}


@router.put("/{folder_id}")
def rename_folder(
    folder_id: int,
    body: FolderRename,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    f = session.get(Folder, folder_id)
    if not f or f.user_id != current.id:
        raise HTTPException(404, "Dossier introuvable")
    f.name = body.name.strip()
    session.add(f)
    session.commit()
    return {"id": f.id, "name": f.name}


@router.delete("/{folder_id}", status_code=204)
def delete_folder(
    folder_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    f = session.get(Folder, folder_id)
    if not f or f.user_id != current.id:
        raise HTTPException(404, "Dossier introuvable")
    # Move children to parent before deleting
    children = session.exec(select(Folder).where(Folder.parent_id == folder_id)).all()
    for child in children:
        child.parent_id = f.parent_id
        session.add(child)
    session.delete(f)
    session.commit()
