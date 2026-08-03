"""Declarative registry of business tables browsable from the admin data
viewer: read-only + delete by default, since several of these tables carry
JSON blobs (script_snapshot, underlyings_json...) that a naive column editor
would corrupt. To add a table, add an entry here; no other code changes
required.

A table becomes editable (not just delete-able) by adding an
`editable_fields` list. Booked deals deliberately have none: every economic
correction now goes through the controlled amendment request envelope.

KidRecord/EmtRecord are deliberately absent — they're immutable regulatory
records (see db/models.py docstrings) and must never be admin-editable or
admin-deletable.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ..db.models import (
    Script, Folder, Deal, DealEvent, Document, AmcStudy, Indicative,
    KidRecord, EmtRecord, RfqRequest, RfqQuote, User, AdminAuditLog,
    Alert, ShockRun, LifecycleProposal, TradeAmendmentRequest,
    DealContractVersion, OfficialFixingVersion,
)
from .audit import commit_rejection

_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "documents"


def _cleanup_document_file(row: Document) -> None:
    """Mirror of api/documents.py::delete_document's file cleanup."""
    path = _DOCS_DIR / row.file_path
    if path.exists():
        path.unlink()


def _break_deal_fixing_cycle(row: Deal, session: Session) -> None:
    """Cut `deal_events.current_fixing_version_id` before anything is deleted.

    `deal_events` points at `official_fixing_versions`, which points back at
    `deal_events`. A cycle cannot be topologically sorted, so SQLAlchemy stops
    trying to order the DELETEs by dependency and emits them in an order of its
    own — in practice `DELETE FROM deals` first, which fails on its own
    children. That is why deleting ANY deal returned "Erreur suppression",
    even one with nothing but three lifecycle events attached.

    Nulling the forward pointer removes the cycle; the versions themselves are
    then deleted as children, before the events they belong to."""
    session.execute(
        text("UPDATE deal_events SET current_fixing_version_id = NULL "
             "WHERE deal_id = :did"),
        {"did": row.id})
    session.flush()


def _break_rfq_quote_cycle(row: RfqRequest, session: Session) -> None:
    """Same shape of problem on the tender side: `rfq_requests` keeps a
    `selected_quote_id` pointing into `rfq_quotes`, and quotes can point at a
    parent quote of the same tender. Deleting the quotes while either pointer
    still holds fails on the foreign key — the observed
    `DELETE FROM rfq_quotes ... FOREIGN KEY constraint failed`."""
    session.execute(
        text("UPDATE rfq_requests SET selected_quote_id = NULL WHERE id = :rid"),
        {"rid": row.id})
    session.execute(
        text("UPDATE rfq_quotes SET parent_quote_id = NULL WHERE rfq_id = :rid"),
        {"rid": row.id})
    session.flush()


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
        "prepare": _break_deal_fixing_cycle,
        # ORDER MATTERS and is enforced by a flush between each entry, because
        # SQLAlchemy's own ordering cannot be trusted here (see the cycle in
        # _break_deal_fixing_cycle). Everything that points at deal_events must
        # go before deal_events itself.
        #
        # Only DealEvent used to be listed, so a deal carrying an alert, a
        # lifecycle proposal, an amendment request or a fixing version could
        # not be deleted at all — and the failure surfaced as a bare
        # "Erreur suppression" with no indication of what was holding it.
        "children": [
            (OfficialFixingVersion, "deal_id"),
            (LifecycleProposal, "deal_id"),
            (TradeAmendmentRequest, "deal_id"),
            (DealContractVersion, "deal_id"),
            (Alert, "deal_id"),
            (ShockRun, "deal_id"),
            (Document, "deal_id"),
            (DealEvent, "deal_id"),
        ],
        # KID and EMT stay blockers rather than cascades: they are the
        # regulatory records the client was actually handed, and they must
        # outlive an administrative purge or be removed deliberately first.
        "blockers": [(KidRecord, "deal_id"), (EmtRecord, "deal_id")],
        "editable_fields": {},
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
        "prepare": _break_rfq_quote_cycle,
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

    try:
        # Cut any pointer that would make the dependency graph cyclic, before
        # anything is removed.
        prepare = cfg.get("prepare")
        if prepare:
            prepare(row, session)

        # One flush per level, in the order declared above. Marking every
        # child for deletion and letting a single commit sort it out is what
        # used to fail: with a cycle in the schema SQLAlchemy gives up on
        # dependency ordering and can emit the parent's DELETE first.
        for child_model, fk in cfg.get("children", []):
            children = session.exec(
                select(child_model).where(getattr(child_model, fk) == row_id)).all()
            if not children:
                continue
            child_cfg = _config_for_model(child_model)
            child_hook = child_cfg.get("on_delete") if child_cfg else None
            for child in children:
                if child_hook:
                    child_hook(child)      # e.g. remove the document's file
                session.delete(child)
            session.flush()

        on_delete = cfg.get("on_delete")
        if on_delete:
            on_delete(row)

        session.delete(row)
        session.commit()
    except IntegrityError as exc:
        # A relation nobody declared. Rather than a bare 500 and a blank
        # "Erreur suppression" on screen, name the row and say what to do —
        # and make the gap visible so the registry above gets completed.
        session.rollback()
        detail = str(getattr(exc, "orig", exc)).strip()
        raise HTTPException(
            409,
            f"Suppression impossible : cet enregistrement est encore référencé "
            f"par d'autres données ({detail}). Supprimez-les d'abord, ou "
            f"signalez-le — la table de dépendances de l'explorateur est "
            f"probablement incomplète pour « {cfg['label']} ».") from exc


def _config_for_model(model) -> dict | None:
    for cfg in REGISTRY.values():
        if cfg["model"] is model:
            return cfg
    return None


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
    """Admin correction boundary. Booked deals are immutable here too."""
    cfg = _get_config(table_key)
    row = session.get(cfg["model"], row_id)
    if not row:
        raise HTTPException(404, "Enregistrement introuvable")

    if table_key == "deals" and patch:
        before = {field: getattr(row, field, None) for field in patch}
        commit_rejection(
            session,
            action="POST_BOOKING_MODIFICATION_REJECTED",
            object_type="DEAL",
            object_id=row.id,
            actor_user_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            before=before,
            after=patch,
            reason="La correction admin directe est interdite; utilisez une demande d'amendement.",
            metadata={"channel": "ADMIN_REGISTRY", "fields": sorted(patch)},
        )
        raise HTTPException(
            409, "Deal booké immuable : créez une demande d'amendement contrôlée.")

    editable = cfg.get("editable_fields")
    if not editable:
        raise HTTPException(403, "Cette table n'est pas modifiable depuis l'admin.")

    unknown = set(patch) - set(editable)
    if unknown:
        raise HTTPException(422, f"Champ(s) non modifiable(s) : {', '.join(sorted(unknown))}")

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
