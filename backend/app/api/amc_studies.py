"""Server-side persistence for AMC study runs (manifest + result + synthèse)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from ..core.amc_controls import fingerprint
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import AmcStudy, User
from .auth import get_current_user

router = APIRouter(prefix="/api/amc/studies", tags=["amc-studies"])


class AmcStudyCreate(BaseModel):
    isin: str = ""
    product_name: str = ""
    label: str = ""
    folder: str = ""
    manifest: dict = {}
    result: dict = {}
    synthese: str = ""


def _summary_row(s: AmcStudy) -> dict:
    return {
        "id": s.id,
        "isin": s.isin,
        "product_name": s.product_name,
        "label": s.label,
        "folder": s.folder,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


def _detail_row(s: AmcStudy) -> dict:
    return {
        **_summary_row(s),
        "manifest": json.loads(s.manifest_json),
        "result": json.loads(s.result_json),
        "synthese": s.synthese_text,
    }


@router.get("")
def list_studies(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Lightweight list of the current user's saved studies, most recent first."""
    rows = session.exec(
        select(AmcStudy)
        .where(AmcStudy.user_id == current.id)
        .order_by(AmcStudy.updated_at.desc())
    ).all()
    return [_summary_row(s) for s in rows]


@router.get("/{study_id}")
def get_study(
    study_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(AmcStudy, study_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Étude introuvable")
    return _detail_row(s)


@router.post("")
def create_study(
    payload: AmcStudyCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    result = dict(payload.result)
    result.pop("_snapshot_integrity", None)
    snapshot = {"manifest": payload.manifest, "result": result, "synthese": payload.synthese}
    try:
        encoded = json.dumps(snapshot, allow_nan=False)
    except ValueError:
        raise HTTPException(422, "Le résultat contient des nombres non finis")
    if len(encoded.encode()) > 30 * 1024 * 1024:
        raise HTTPException(413, "Instantané trop volumineux (30 Mo maximum)")
    result["_snapshot_integrity"] = fingerprint(snapshot)
    label = payload.label.strip() or f"{payload.isin} — {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
    s = AmcStudy(
        user_id=current.id,
        isin=payload.isin,
        product_name=payload.product_name,
        label=label,
        folder=payload.folder,
        manifest_json=json.dumps(payload.manifest),
        result_json=json.dumps(result, allow_nan=False),
        synthese_text=payload.synthese,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return _summary_row(s)


@router.delete("/{study_id}")
def delete_study(
    study_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(AmcStudy, study_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Étude introuvable")
    session.delete(s)
    session.commit()
    return {"ok": True}


@router.get("/{study_id}/archive")
def export_study_archive(study_id: int, current: Annotated[User, Depends(get_current_user)],
                         session: Annotated[Session, Depends(get_session)]):
    """Export the saved version, including optional PDF bytes and AI provenance."""
    data = get_study(study_id, current, session)
    content = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    return Response(content, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="study_{study_id}.json"',
        "X-Content-SHA256": __import__("hashlib").sha256(content).hexdigest()})


@router.get("/{study_id}/compare/{other_id}")
def compare_studies(study_id: int, other_id: int, current: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_session)]):
    left, right = get_study(study_id, current, session), get_study(other_id, current, session)
    def flatten(value, prefix=""):
        out = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(item, dict): out.update(flatten(item, path))
            else: out[path] = item
        return out
    a, b = flatten(left["result"]), flatten(right["result"])
    return {"left": study_id, "right": other_id, "differences": [
        {"field": key, "left": a.get(key), "right": b.get(key)}
        for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key)]}
