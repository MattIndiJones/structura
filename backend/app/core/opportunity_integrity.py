"""Serialize CRM attribution changes with their Product/RFQ/Deal consumers."""
from sqlalchemy import func, update
from sqlmodel import select
from ..db.models import Deal, Indicative, Interaction, Opportunity, ProductRevision, RfqRequest


def lock_opportunity(session, opportunity_id):
    session.execute(update(Opportunity).where(Opportunity.id==opportunity_id)
        .values(id=Opportunity.id).execution_options(synchronize_session=False))
    return session.get(Opportunity,opportunity_id,populate_existing=True)


def has_attribution_evidence(session, opportunity_id):
    for model in (Deal,RfqRequest,Indicative,Interaction):
        if session.exec(select(model.id).where(model.opportunity_id==opportunity_id)).first() is not None:
            return True
    # Historical Product snapshots are evidence even if a later revision detaches the context.
    return session.exec(select(ProductRevision.id).where(
        func.json_extract(ProductRevision.snapshot_json,'$.commercial.opportunity_id')==opportunity_id)).first() is not None
