"""Declarative registry of business tables browsable from the admin data
viewer: read-only + delete by default, since several of these tables carry
JSON blobs (script_snapshot, underlyings_json...) that a naive column editor
would corrupt. To add a table, add an entry here; no other code changes
required.

A table becomes editable (not just delete-able) by adding an
`editable_fields` list — an explicit whitelist, never "every column", so a
frozen-at-booking field (script_snapshot, market_snapshot_json...) can never
be admin-edited by mistake. Only `deals` has this today, and only corrections
that do not require rebuilding lifecycle are exposed. Dates and status remain
domain operations, not raw table patches.

KidRecord/EmtRecord are deliberately absent — they're immutable regulatory
records (see db/models.py docstrings) and must never be admin-editable or
admin-deletable.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from sqlmodel import Session, select
from ..db.models import (
    Script, Folder, Deal, DealEvent, Document, AmcStudy, Indicative,
    KidRecord, EmtRecord, RfqRequest, RfqQuote, User, AdminAuditLog,
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
        # field -> input kind, for AdminBrowseView.vue's edit form. Deliberately
        # excludes fair_value (Structura's own computed price at booking, not
        # something a client would ask to "correct") and every JSON/frozen
        # field (script_snapshot, market_snapshot_json, underlyings_json,
        # greeks_json, realized_payout, resolution_outcome) — those stay
        # view+delete only, same as every other table in this registry.
        "editable_fields": {
            "contrepartie": "text",
            "devise": "text",
            "product_type": "text",
            "nominal": "number",
            "price_traded": "number",
        },
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
        # A booked deal's tender is its best-execution trail — same rule the
        # RFQ module enforces on its own delete (api/rfq.py:delete_rfq).
        "blockers": [(Deal, "rfq_id")],
    },
}


def registry_meta() -> list[dict]:
    return [
        {"key": k, "label": v["label"], "editable_fields": v.get("editable_fields", {})}
        for k, v in REGISTRY.items()
    ]


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


def get_row(table_key: str, row_id: int, session: Session) -> dict:
    """Single-row detail for the edit form — list_rows only projects
    `columns` (the table's display columns), which for `deals` is a
    deliberately short summary and doesn't include most `editable_fields`
    (product_type, price_traded, the date fields...). The edit form needs
    those actual current values to prefill, not blanks."""
    cfg = _get_config(table_key)
    row = session.get(cfg["model"], row_id)
    if not row:
        raise HTTPException(404, "Enregistrement introuvable")
    fields = set(cfg["columns"]) | set(cfg.get("editable_fields", {}))
    return {f: (getattr(row, f).isoformat() if isinstance(getattr(row, f, None), datetime) else getattr(row, f, None))
            for f in fields}


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


def delete_rows(table_key: str, row_ids: list, session: Session) -> dict:
    """Batch delete, row by row, with the SAME rules as the single delete —
    blockers and cascades included. Deliberately not a bulk SQL DELETE: that
    would step over the blockers (a deal's KID/EMT records, an RFQ a deal was
    booked from) which is the whole point of going through here.

    A blocked row must not sink the batch: the others go through and the
    caller gets told, per row, what happened. Selecting fifty deals to purge
    and having the third one abort the lot — leaving the operator to guess
    which ones went — is worse than no batch at all."""
    deleted, blocked = [], []
    for row_id in row_ids:
        try:
            delete_row(table_key, row_id, session)
            deleted.append(row_id)
        except HTTPException as e:
            session.rollback()
            blocked.append({"id": row_id, "reason": e.detail})
    return {"deleted": deleted, "blocked": blocked}


def update_row(table_key: str, row_id: int, patch: dict, session: Session,
               actor_id: int | None = None) -> dict:
    """Admin-only correction of a handful of whitelisted fields — see the
    module docstring for why this is an explicit per-table allowlist rather
    than a generic 'edit any column' endpoint. Bypasses the normal
    ownership check the user-facing PATCH /api/deals/{id} enforces, since
    the whole point is fixing another user's booked deal on a client's
    request."""
    cfg = _get_config(table_key)
    editable = cfg.get("editable_fields")
    if not editable:
        raise HTTPException(403, "Cette table n'est pas modifiable depuis l'admin.")

    row = session.get(cfg["model"], row_id)
    if not row:
        raise HTTPException(404, "Enregistrement introuvable")

    unknown = set(patch) - set(editable)
    if unknown:
        raise HTTPException(422, f"Champ(s) non modifiable(s) : {', '.join(sorted(unknown))}")

    if table_key == "deals":
        if "nominal" in patch and (patch["nominal"] is None or patch["nominal"] <= 0):
            raise HTTPException(422, "Le nominal doit être strictement positif.")
        if "price_traded" in patch and (
                patch["price_traded"] is None or patch["price_traded"] <= 0):
            raise HTTPException(422, "Le prix traité doit être strictement positif.")
        if "contrepartie" in patch:
            patch["contrepartie"] = str(patch["contrepartie"] or "").strip()
            if not patch["contrepartie"]:
                raise HTTPException(422, "La contrepartie est obligatoire.")
        if "devise" in patch:
            patch["devise"] = str(patch["devise"] or "").strip().upper()
            if len(patch["devise"]) != 3 or not patch["devise"].isalpha():
                raise HTTPException(422, "La devise doit être un code ISO à trois lettres.")

    before = {field: getattr(row, field, None) for field in patch}
    for field, value in patch.items():
        setattr(row, field, value)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()
    session.add(row)
    session.add(AdminAuditLog(
        admin_user_id=actor_id,
        table_key=table_key,
        row_id=row_id,
        action="update",
        before_json=json.dumps(before, ensure_ascii=False, default=str),
        after_json=json.dumps(
            {field: getattr(row, field, None) for field in patch},
            ensure_ascii=False, default=str),
    ))
    session.commit()
    session.refresh(row)

    return {col: (getattr(row, col).isoformat() if isinstance(getattr(row, col, None), datetime) else getattr(row, col, None))
            for col in cfg["columns"]}
