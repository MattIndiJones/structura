"""Pre-trade pricing opportunities — the stage before a Deal exists.

An Indicative is what KID/EMT attach to while a product is still being
discussed with a client (no trade yet, so no Deal row). If it converts,
the resulting Deal keeps a permanent pointer back via Deal.indicative_id —
the Indicative's own id never changes and its KID/EMT records are never
re-keyed. See db/models.py:Indicative for the full rationale.
"""
from __future__ import annotations
import json
from datetime import datetime, date
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Indicative, Entity, User, Deal
from ..core.product.inputs import terms_from_input
from ..core.product.models import FrozenObject, TradeIntent
from ..core.references import next_reference
from ..services.product_repository import (
    ProductError, load_product, owned_record, stage_internal_product,
    stage_revision,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/indicatives", tags=["indicatives"])


class IndicativeCreate(BaseModel):
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    product_name: str = ""
    pricing_input: Optional[dict] = None
    contrepartie: str = ""
    devise: str = "EUR"
    nominal: float = 0.0
    underlyings: List[dict] = []
    script_snapshot: str
    script_id: Optional[int] = None
    market_snapshot: dict = {}


class IndicativeUpdate(BaseModel):
    status: Optional[str] = None
    contrepartie: Optional[str] = None
    nominal: Optional[float] = None
    script_snapshot: Optional[str] = None
    underlyings: Optional[List[dict]] = None
    market_snapshot: Optional[dict] = None


def _gen_ref(entity_name: str | None, session: Session) -> str:
    prefix = ((entity_name or "IND")[:4].upper().replace(" ", "").ljust(4, "X"))
    return next_reference(session, Indicative,
                          f"{prefix}-IND-{date.today().strftime('%Y%m%d')}-")


def _row(i: Indicative) -> dict:
    return {
        "id": i.id,
        "reference": i.reference,
        "entity_id": i.entity_id,
        "user_id": i.user_id,
        "product_id": i.product_id,
        "product_terms_version": i.product_terms_version,
        "contrepartie": i.contrepartie,
        "devise": i.devise,
        "nominal": i.nominal,
        "underlyings": json.loads(i.underlyings_json),
        "market_snapshot": json.loads(i.market_snapshot_json),
        "script_snapshot": i.script_snapshot,
        "script_id": i.script_id,
        "status": i.status,
        "created_at": i.created_at.isoformat(),
        "updated_at": i.updated_at.isoformat(),
    }


def _indicative_snapshot(indicative: Indicative) -> FrozenObject:
    return FrozenObject(_row(indicative))


def _sync_product_indicative(
    session: Session, indicative: Indicative, product, current: User, *, action: str,
):
    indicatives = tuple(
        item for item in product.indicatives
        if item.to_dict().get("id") != indicative.id
    ) + (_indicative_snapshot(indicative),)
    intent = TradeIntent(**{
        **product.intent.model_dump(mode="json"),
        "nominal": indicative.nominal or product.intent.nominal,
        "counterparty_name": (
            indicative.contrepartie or product.intent.counterparty_name),
    })
    return stage_revision(
        session,
        product.model_copy(update={"indicatives": indicatives, "intent": intent}),
        expected_revision=product.revision,
        actor_id=current.id,
        action=action,
        reason=f"Synchronisation de {indicative.reference} dans le Product.",
    )


@router.post("", status_code=201)
def create_indicative(
    body: IndicativeCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    entity = session.get(Entity, current.entity_id) if current.entity_id else None
    reference = _gen_ref(entity.name if entity else None, session)

    try:
        if body.product_id is not None:
            owned_record(session, body.product_id, current)
            product = load_product(session, body.product_id)
            if (body.product_terms_version is not None
                    and body.product_terms_version != product.terms_version):
                raise ProductError(
                    "PRODUCT_TERMS_STALE",
                    "La version des termes du Product a changé.")
            if body.pricing_input:
                submitted_terms = terms_from_input(
                    body.pricing_input, allow_unresolved=False)
                if submitted_terms.fingerprint != product.terms_fingerprint:
                    raise ProductError(
                        "PRODUCT_TERMS_MISMATCH",
                        "La fiche indicative ne porte pas les termes du Product ouvert.",
                        422,
                    )
        else:
            if not body.pricing_input:
                raise ProductError(
                    "INDICATIVE_PRODUCT_INPUT_REQUIRED",
                    "Les termes complets du Product sont requis pour créer un indicatif.",
                    422,
                )
            product = stage_internal_product(
                session,
                user=current,
                name=body.product_name or "Produit structuré",
                terms=terms_from_input(body.pricing_input, allow_unresolved=False),
                intent=TradeIntent(
                    nominal=body.nominal or None,
                    counterparty_name=body.contrepartie,
                ),
                reason="Création interne du Product pour la fiche indicative.",
            )
    except (ProductError, ValueError) as exc:
        session.rollback()
        detail = ({"code": exc.code, "message": str(exc)}
                  if isinstance(exc, ProductError) else {
                      "code": "PRODUCT_TERMS_INVALID", "message": str(exc)})
        raise HTTPException(
            exc.status if isinstance(exc, ProductError) else 422,
            detail=detail,
        ) from exc

    ind = Indicative(
        product_id=product.product_id,
        product_terms_version=product.terms_version,
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        script_snapshot=product.terms.script,
        script_id=body.script_id,
        contrepartie=body.contrepartie,
        devise=body.devise,
        nominal=body.nominal,
        underlyings_json=json.dumps([
            item.model_dump(mode="json") for item in product.terms.underlyings]),
        market_snapshot_json=json.dumps({
            **body.market_snapshot,
            **({"pricing_input": body.pricing_input} if body.pricing_input else {}),
        }),
    )
    session.add(ind)
    session.flush()
    _sync_product_indicative(
        session, ind, product, current, action="PRODUCT_INDICATIVE_CREATED")
    session.commit()
    session.refresh(ind)
    return _row(ind)


@router.get("")
def list_indicatives(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.exec(
        select(Indicative).where(Indicative.user_id == current.id)
        .order_by(Indicative.created_at.desc())
    ).all()
    return [_row(i) for i in rows]


@router.get("/{indicative_id}")
def get_indicative(
    indicative_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")
    return _row(ind)


@router.patch("/{indicative_id}")
def update_indicative(
    indicative_id: int,
    body: IndicativeUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")

    if ind.product_id is None:
        raise HTTPException(409, detail={
            "code": "INDICATIVE_PRODUCT_MISSING",
            "message": "Cet indicatif ne possède pas de Product canonique.",
        })
    product = load_product(session, ind.product_id)
    data = body.model_dump(exclude_unset=True)
    if ("script_snapshot" in data and data["script_snapshot"] != ind.script_snapshot) \
            or ("underlyings" in data and data["underlyings"] != json.loads(ind.underlyings_json)):
        raise HTTPException(409, detail={
            "code": "PRODUCT_TERMS_REVISION_REQUIRED",
            "message": "Révisez les termes du Product avant de modifier le contrat indicatif.",
        })
    data.pop("script_snapshot", None)
    data.pop("underlyings", None)
    if "underlyings" in data:
        ind.underlyings_json = json.dumps(data.pop("underlyings"))
    if "market_snapshot" in data:
        ind.market_snapshot_json = json.dumps(data.pop("market_snapshot"))
    for field, value in data.items():
        if value is not None:
            setattr(ind, field, value)

    ind.updated_at = datetime.utcnow()
    session.add(ind)
    _sync_product_indicative(
        session, ind, product, current, action="PRODUCT_INDICATIVE_UPDATED")
    session.commit()
    return _row(ind)


@router.get("/{indicative_id}/deal")
def get_linked_deal(
    indicative_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """The Deal this indicative converted into, if any — null while still open."""
    ind = session.get(Indicative, indicative_id)
    if not ind or ind.user_id != current.id:
        raise HTTPException(404, "Indicatif introuvable")
    deal = session.exec(select(Deal).where(Deal.indicative_id == indicative_id)).first()
    return {"deal_id": deal.id if deal else None, "reference": deal.reference if deal else None}
