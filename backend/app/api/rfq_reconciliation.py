"""Scoped read and explicit durable resume for electronic RFQ reconciliation."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import User, RfqElectronicExecution
from ..services import rfq_reconciliation as service
from .auth import get_current_user

router=APIRouter(prefix='/api/rfq-reconciliation',tags=['rfq'])

@router.get('')
def list_reconciliation(current:Annotated[User,Depends(get_current_user)],
                        session:Annotated[Session,Depends(get_session)],
                        before_id:Annotated[int|None,Query(gt=0)]=None):
    if not service.available(session):
        return {'items':[],'next_before_id':None}
    query=select(RfqElectronicExecution).order_by(RfqElectronicExecution.solicitation_id.desc())
    if before_id is not None:
        query=query.where(RfqElectronicExecution.solicitation_id<before_id)
    output=[]
    for entry in session.exec(query).yield_per(100):
        try:
            service.authorize(session,entry.id,current)
        except HTTPException as exc:
            if exc.status_code in (403,404):continue
            raise
        output.append({'solicitation_id':entry.solicitation_id,'role':entry.role,
            **service.workspace(session,entry)})
        if len(output)==100:break
    return {'items':output,'next_before_id':output[-1]['solicitation_id'] if len(output)==100 else None}

@router.get('/{execution_id}')
def get_reconciliation(execution_id:str,current:Annotated[User,Depends(get_current_user)],
                       session:Annotated[Session,Depends(get_session)]):
    return service.workspace(session,service.authorize(session,execution_id,current))

@router.post('/{execution_id}/refresh')
def refresh_reconciliation(execution_id:str,body:service.RefreshCommand,
                           current:Annotated[User,Depends(get_current_user)],
                           session:Annotated[Session,Depends(get_session)]):
    return service.refresh(session,execution_id,current,body)
