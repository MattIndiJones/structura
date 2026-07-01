"""Document library — store, list, download generated documents (KID PDF, term sheets, etc.)."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import Document, User
from .auth import get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])

_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "documents"
_DOCS_DIR.mkdir(parents=True, exist_ok=True)


# ── Schemas ───────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    doc_type: str = "autre"     # kid | termsheet_indicatif | termsheet_final | confirmation | autre
    deal_id: Optional[int] = None
    metadata: dict = {}


def _doc_row(d: Document) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "doc_type": d.doc_type,
        "filename": d.filename,
        "deal_id": d.deal_id,
        "created_at": d.created_at.isoformat(),
        "metadata": json.loads(d.metadata_json),
    }


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("")
def list_documents(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    deal_id: Optional[int] = None,
):
    q = select(Document).where(Document.user_id == current.id)
    if deal_id is not None:
        q = q.where(Document.deal_id == deal_id)
    docs = session.exec(q.order_by(Document.created_at.desc())).all()
    return [_doc_row(d) for d in docs]


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile,
    title: str,
    doc_type: str = "autre",
    deal_id: Optional[int] = None,
    meta: str = "{}",
    current: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """Upload a file (PDF/HTML/etc.) and store its metadata."""
    user_dir = _DOCS_DIR / str(current.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{ts}_{file.filename or 'document'}"
    dest = user_dir / safe_name
    dest.write_bytes(await file.read())

    doc = Document(
        user_id=current.id,
        deal_id=deal_id,
        doc_type=doc_type,
        title=title,
        filename=safe_name,
        file_path=str(dest.relative_to(_DOCS_DIR)),
        metadata_json=meta,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return _doc_row(doc)


@router.get("/{doc_id}/download")
def download_document(
    doc_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    doc = session.get(Document, doc_id)
    if not doc or doc.user_id != current.id:
        raise HTTPException(404, "Document introuvable")
    path = _DOCS_DIR / doc.file_path
    if not path.exists():
        raise HTTPException(404, "Fichier introuvable sur le serveur")
    return FileResponse(str(path), filename=doc.filename, media_type="application/octet-stream")


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    doc = session.get(Document, doc_id)
    if not doc or doc.user_id != current.id:
        raise HTTPException(404, "Document introuvable")
    path = _DOCS_DIR / doc.file_path
    if path.exists():
        path.unlink()
    session.delete(doc)
    session.commit()
