"""Declarative registry of business tables browsable from the admin data
viewer: read-only + delete only — no generic field editor, since several of
these tables carry JSON blobs (script_snapshot, underlyings_json...) that a
naive column editor would corrupt. To add a table, add an entry here; no
other code changes required.

KidRecord/EmtRecord are deliberately absent — they're immutable regulatory
records (see db/models.py docstrings) and must never be admin-editable or
admin-deletable.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from sqlmodel import Session, select
from ..db.models import (
    Script, Folder, Deal, DealEvent, Document, AmcStudy, Indicative,
    KidRecord, EmtRecord, RfqRequest, RfqQuote, User,
)

_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "documents"


def _cleanup_document_file(row: Document) -> None:
    """Mirror of api/documents.py::delete_document's file cleanup."""
    path = _DOCS_DIR / row.file_path
    if path.exists():
        path.unlink()


REGISTRY: dict[str, dict] = {
    "scripts": {
        "model": Script, "label": "Scripts",
        "columns": ["id", "name", "category", "user_id", "is_shared", "created_at", "updated_at"],
    },
    "folders": {
        "model": Folder, "label": "Dossiers",
        "columns": ["id", "name", "parent_id", "user_id", "created_at"],
    },
    "deals": {
        "model": Deal, "label": "Deals",
        "columns": ["id", "reference", "contrepartie", "devise", "nominal", "status", "user_id", "created_at"],
        "children": [(DealEvent, "deal_id")],
        "blockers": [(KidRecord, "deal_id"), (EmtRecord, "deal_id")],
    },
    "documents": {
        "model": Document, "label": "Documents",
        "columns": ["id", "doc_type", "title", "filename", "deal_id", "user_id", "created_at"],
        "on_delete": _cleanup_document_file,
    },
    "amc_studies": {
        "model": AmcStudy, "label": "Études AMC",
        "columns": ["id", "isin", "product_name", "label", "user_id", "created_at", "updated_at"],
    },
    "indicatives": {
        "model": Indicative, "label": "Indicatives",
        "columns": ["id", "reference", "contrepartie", "nominal", "status", "user_id", "created_at"],
        "blockers": [(KidRecord, "indicative_id"), (EmtRecord, "indicative_id")],
    },
    "rfq_requests": {
        "model": RfqRequest, "label": "RFQ",
        "columns": ["id", "reference", "name", "template_type", "status", "user_id", "created_at"],
        "children": [(RfqQuote, "rfq_id")],
    },
}


def registry_meta() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in REGISTRY.items()]


def _get_config(table_key: str) -> dict:
    cfg = REGISTRY.get(table_key)
    if not cfg:
        raise HTTPException(404, "Table inconnue")
    return cfg


def list_rows(table_key: str, session: Session) -> list[dict]:
    cfg = _get_config(table_key)
    model = cfg["model"]
    rows = session.exec(select(model).order_by(model.id.desc())).all()

    owners: dict[int, str] = {}
    def owner_name(uid: int | None) -> str | None:
        if uid is None:
            return None
        if uid not in owners:
            u = session.get(User, uid)
            owners[uid] = u.username if u else "?"
        return owners[uid]

    out = []
    for row in rows:
        entry = {}
        for col in cfg["columns"]:
            v = getattr(row, col, None)
            entry[col] = v.isoformat() if isinstance(v, datetime) else v
        if "user_id" in cfg["columns"]:
            entry["owner"] = owner_name(row.user_id)
        out.append(entry)
    return out


def delete_row(table_key: str, row_id: int, session: Session) -> None:
    cfg = _get_config(table_key)
    row = session.get(cfg["model"], row_id)
    if not row:
        raise HTTPException(404, "Enregistrement introuvable")

    for blocker_model, fk in cfg.get("blockers", []):
        blocked = session.exec(select(blocker_model).where(getattr(blocker_model, fk) == row_id)).first()
        if blocked:
            raise HTTPException(409, f"Suppression bloquée : des {blocker_model.__tablename__} sont rattachés à cet enregistrement")

    for child_model, fk in cfg.get("children", []):
        for child in session.exec(select(child_model).where(getattr(child_model, fk) == row_id)).all():
            session.delete(child)

    on_delete = cfg.get("on_delete")
    if on_delete:
        on_delete(row)

    session.delete(row)
    session.commit()
