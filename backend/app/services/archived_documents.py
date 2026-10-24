"""Dated immutable documents. Export reads retained bytes and never reprices."""
import base64
from copy import deepcopy
import hashlib
import hmac
import json
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..core.valuation_context import canonical_json, json_transport_json
from ..core.valuation_runs import calculation_identity
from ..db.models import ArchivedDocument


class DocumentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_id: str = Field(min_length=1, max_length=40)


class ProposalFreeze(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview: dict


def sign_preview(data, request, deal, user, *, purpose="PROPOSAL"):
    from ..runtime import business_now
    claims = {"deal_id": deal.id, "user_id": user.id, "purpose": purpose,
              "product_id": deal.product_id, "product_terms_version": deal.product_terms_version,
              "contract_version": deal.contract_version,
              "created_at": business_now().isoformat(), "request": request,
              "calculation_identity": calculation_identity(), "data": deepcopy(data)}
    return seal(claims)


def seal(claims):
    from ..core.instance_signing import receipt_signing_secret
    digest = hmac.new(receipt_signing_secret().encode(),
                      ("document-preview-v1:" + json_transport_json(claims)).encode(), hashlib.sha256).hexdigest()
    return {"claims": claims, "signature": digest}


def verify_preview(preview, deal, user, *, purpose="PROPOSAL"):
    claims = unseal(preview, user.id, purpose)
    if claims.get("deal_id") != deal.id:
        raise HTTPException(404, "Proposition introuvable.")
    if (claims.get("contract_version") != deal.contract_version
            or claims.get("product_id") != deal.product_id
            or claims.get("product_terms_version") != deal.product_terms_version):
        raise HTTPException(409, "Le contrat a changé ; générez une nouvelle proposition.")
    return claims


def unseal(preview, user_id, purpose):
    from ..core.instance_signing import receipt_signing_secret
    claims = preview.get("claims") or {}
    expected = hmac.new(receipt_signing_secret().encode(),
                        ("document-preview-v1:" + json_transport_json(claims)).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(preview.get("signature") or "")):
        raise HTTPException(422, "La proposition affichée ne porte pas une preuve serveur valide.")
    if claims.get("user_id") != user_id:
        raise HTTPException(404, "Proposition introuvable.")
    if claims.get("purpose") != purpose:
        raise HTTPException(422, "La preuve ne correspond pas à cette opération.")
    return claims


def stage(session, *, kind, deal, user, request, data, pdf, parent_id=None):
    if parent_id:
        load(session, parent_id, kind=kind, deal=deal, user=user)
    encoded = canonical_json(data)
    row = ArchivedDocument(id=str(uuid4()), kind=kind, deal_id=deal.id, user_id=user.id,
                           parent_id=parent_id, contract_version=deal.contract_version,
                           request_json=canonical_json(request), data_json=encoded,
                           content_hash=hashlib.sha256(encoded.encode()).hexdigest(),
                           pdf_base64=base64.b64encode(pdf).decode())
    session.add(row)
    session.flush()
    from ..core.audit import record_audit_event
    record_audit_event(session, action="DOCUMENT_FROZEN", object_type="DEAL",
                       object_id=deal.id, actor_user_id=user.id, result="SUCCESS",
                       after={"archive_id": row.id, "kind": kind, "content_hash": row.content_hash})
    return row


def load(session, archive_id, *, kind, deal, user):
    row = session.get(ArchivedDocument, archive_id)
    if not row or row.deal_id != deal.id or row.user_id != user.id or row.kind != kind:
        raise HTTPException(404, "Document archivé introuvable.")
    return row


def response(row):
    from fastapi.responses import Response
    return Response(base64.b64decode(row.pdf_base64), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{row.kind}_{row.id}.pdf"'})
