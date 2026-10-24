"""Canonical read scope for booked contracts and their derived projections."""
from sqlmodel import Session

from ..core.access import has_capability
from ..db.models import Deal, RfqOwnership, RfqRequest, User


def deal_entity_id(deal: Deal, session: Session) -> int | None:
    if deal.entity_id is not None:
        return deal.entity_id
    owner = session.get(User, deal.user_id)
    return owner.entity_id if owner else None


def can_read_deal(deal: Deal, user: User, session: Session) -> bool:
    if deal is None or not has_capability(user, "business.read"):
        return False
    from ..hybrid.config import current_config
    if user.role == "admin" and current_config() is None:
        return True
    entity = deal_entity_id(deal, session)
    if entity is None:
        return deal.user_id == user.id
    if user.entity_id != entity:
        return False
    from ..db.models import ProductRecord
    product = session.get(ProductRecord, deal.product_id) if deal.product_id else None
    if product is not None and product.origin_product_id is not None:
        if not can_read_product_contract(session, product.id, user):
            return False
    if deal.rfq_id and session.get(RfqOwnership, deal.rfq_id):
        from .rfq_access import effective_rights
        rfq = session.get(RfqRequest, deal.rfq_id)
        return bool(rfq and "read" in effective_rights(session, rfq, user))
    if deal.rfq_id:
        # Do not reinterpret the access of historical RFQs without desk scope.
        return deal.user_id == user.id or user.role in {"ops_maker", "checker", "organization_admin"}
    return True


def visible_deals(session: Session, rows, user: User):
    return [row for row in rows if can_read_deal(row, user, session)]


def can_read_organization_record(row, user: User) -> bool:
    if row is None or not has_capability(user, "business.read"):
        return False
    from ..hybrid.config import current_config
    if user.role == "admin" and current_config() is None:
        return True
    if row.entity_id is None:
        return row.user_id == user.id
    return row.entity_id == user.entity_id


def can_read_product_contract(session: Session, product_id: int, user: User,
                              _lineage: frozenset[int] = frozenset()) -> bool:
    from ..db.models import ProductRecord
    from .rfq_bank import case_for_product, private_product_access
    row = session.get(ProductRecord, product_id)
    if not can_read_organization_record(row, user):
        return False
    if product_id in _lineage:
        return False
    if row.origin_product_id is not None and not can_read_product_contract(
            session, row.origin_product_id, user, _lineage | {product_id}):
        return False
    owner = session.get(User, row.user_id)
    if owner and owner.username == "__rfq_transport__":
        return False
    case = case_for_product(session, product_id)
    if case:
        from fastapi import HTTPException
        try:
            private_product_access(session, case, user)
            return has_capability(user, "business.price")
        except HTTPException:
            return False
    from sqlmodel import select
    from .rfq_access import effective_rights
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.product_id == product_id)).all()
    return all("read" in effective_rights(session, rfq, user) for rfq in rfqs)
