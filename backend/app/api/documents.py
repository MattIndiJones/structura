"""Document library — store, list, download generated documents (KID PDF, term sheets, etc.)."""
from __future__ import annotations
import json
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Optional
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import Deal, Document, User
from ..core.product.models import FrozenObject
from ..services.product_repository import ProductError, load_product, owned_record, stage_revision
from .auth import get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])

_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "documents"
_DOCS_DIR.mkdir(parents=True, exist_ok=True)


# ── Schemas ───────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    doc_type: str = "autre"     # kid | termsheet_indicatif | termsheet_final | confirmation | autre
    deal_id: Optional[int] = None
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    metadata: dict = Field(default_factory=dict)


def _doc_row(d: Document) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "doc_type": d.doc_type,
        "filename": d.filename,
        "deal_id": d.deal_id,
        "product_id": d.product_id,
        "product_terms_version": d.product_terms_version,
        "created_at": d.created_at.isoformat(),
        "metadata": json.loads(d.metadata_json),
    }


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("")
def list_documents(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    deal_id: Optional[int] = None,
    product_id: Optional[int] = None,
):
    q = select(Document).where(Document.user_id == current.id)
    if deal_id is not None:
        q = q.where(Document.deal_id == deal_id)
    if product_id is not None:
        q = q.where(Document.product_id == product_id)
    docs = session.exec(q.order_by(Document.created_at.desc())).all()
    return [_doc_row(d) for d in docs]


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile,
    title: str,
    doc_type: str = "autre",
    deal_id: Optional[int] = None,
    product_id: Optional[int] = None,
    product_terms_version: Optional[int] = None,
    meta: str = "{}",
    current: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """Upload a file (PDF/HTML/etc.) and store its metadata."""
    if deal_id is not None:
        deal = session.get(Deal, deal_id)
        if deal is None or deal.user_id != current.id:
            raise HTTPException(404, "Deal introuvable")
        if deal.product_id is None:
            raise HTTPException(409, detail={
                "code": "DEAL_PRODUCT_MISSING",
                "message": "Le deal ne possède pas de Product canonique.",
            })
        if product_id is not None and deal.product_id != product_id:
            raise HTTPException(422, "Le deal ne correspond pas au Product demandé.")
        product_id = product_id or deal.product_id
    if product_id is None:
        raise HTTPException(422, detail={
            "code": "DOCUMENT_PRODUCT_REQUIRED",
            "message": "Un document persistant doit être rattaché à un Product.",
        })
    product = None
    if product_id is not None:
        try:
            owned_record(session, product_id, current)
            product = load_product(session, product_id)
        except ProductError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)})
        if product_terms_version is not None and product_terms_version != product.terms_version:
            raise HTTPException(409, "La version des termes du Product a changé.")
    user_dir = _DOCS_DIR / str(current.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    try:
        metadata = json.loads(meta)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "Les métadonnées du document ne sont pas un JSON valide.") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(422, "Les métadonnées du document doivent former un objet JSON.")

    # Sanitize filename
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    original_name = Path(file.filename or "document").name
    safe_name = f"{ts}_{uuid4().hex}_{original_name}"
    dest = user_dir / safe_name
    dest.write_bytes(await file.read())

    doc = Document(
        user_id=current.id,
        deal_id=deal_id,
        product_id=product_id,
        product_terms_version=product.terms_version if product else None,
        doc_type=doc_type,
        title=title,
        filename=safe_name,
        file_path=str(dest.relative_to(_DOCS_DIR)),
        metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
    try:
        session.add(doc)
        session.flush()
        if product is not None:
            snapshot = FrozenObject({
                "kind": "DOCUMENT", "record_id": doc.id, "doc_type": doc.doc_type,
                "title": doc.title, "filename": doc.filename,
                "terms_version": product.terms_version,
                "created_at": doc.created_at.isoformat(),
            })
            product = product.model_copy(update={"documents": (*product.documents, snapshot)})
            stage_revision(session, product, expected_revision=product.revision,
                           actor_id=current.id, action="PRODUCT_DOCUMENT_RETAINED",
                           reason="Conservation d’un document sur le Product.")
        session.commit()
    except Exception:
        session.rollback()
        dest.unlink(missing_ok=True)
        raise
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
    if doc.product_id is not None:
        raise HTTPException(
            409, "Ce document appartient à l’historique d’un Product conservé et ne peut pas être supprimé.")
    path = _DOCS_DIR / doc.file_path
    if path.exists():
        path.unlink()
    session.delete(doc)
    session.commit()
