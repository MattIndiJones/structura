"""C03: legal identity follows quotes, network, booking and contract amendments."""
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from backend.tests.test_rfq_execution import (execution_context, execution_case, network_execution_case,
    select_manual, request, confirm, booking_body)
from backend.tests.test_workflow_phase2 import _session, _deal, MAKER, CHECKER
from backend.app.api import admin, rfq, deals, ccr
from backend.app.db.models import (Counterparty, RfqProvider, RfqQuote, User, Deal, DealContractVersion,
                                   RfqQuotePublication, RfqRelationshipSide, RfqSolicitation, AuditEvent)
from backend.app.services import rfq_execution, product_repository
from backend.app.core.ccr import service as credit


def test_provider_rename_and_reassignment_never_reassign_historical_quotes(execution_case):
    engine,record,clock,quote_id=execution_case
    with Session(engine) as session:
        user=session.get(User,1)
        quote=session.get(RfqQuote,quote_id)
        assert quote.counterparty_id==1 and quote.provider_id==1
        admin.update_rfq_provider(1,admin.RfqProviderUpdate(label='New channel',counterparty_id=2,reason='Nouveau rattachement juridique'),user,session)
        historic=rfq.get_rfq(record['id'],user,session)['quotes'][0]
        assert historic['provider']=='BNP manuel' and historic['counterparty_id']==1 and historic['counterparty']=='BNP juridique'
        assert rfq_execution._counterparty(session,session.get(rfq.RfqRequest,record['id']),quote).id==1
        newer=rfq.add_quote(record['id'],rfq.QuoteCreate(provider='New channel'),user,session)
        assert newer['provider_id']==1 and newer['counterparty_id']==2


def test_unfrozen_quote_requires_explicit_audited_qualification(execution_case):
    engine,record,_,quote_id=execution_case
    with Session(engine) as session:
        user=session.get(User,1);quote=session.get(RfqQuote,quote_id)
        quote.identity_frozen=False;quote.counterparty_id=None;quote.counterparty_name=None
        session.add(quote);session.commit()
        with pytest.raises(HTTPException): ccr.rfq_credit_context(record['id'],quote_id,user,session)
        row=rfq.update_quote(record['id'],quote_id,rfq.QuoteUpdate(counterparty_id=1,identity_reason='Confirmation juridique du desk'),user,session)
        assert row['counterparty_id']==1 and row['identity_status']=='FROZEN'
        assert ccr.rfq_credit_context(record['id'],quote_id,user,session)['counterparty_id']==1
        with pytest.raises(HTTPException):
            rfq.update_quote(record['id'],quote_id,rfq.QuoteUpdate(counterparty_id=2,identity_reason='Tentative de substitution'),user,session)
        session.rollback()
        assert session.exec(select(AuditEvent).where(AuditEvent.action=='QUOTE_LEGAL_IDENTITY_QUALIFIED')).first()


def test_network_mapping_accepts_different_local_name_and_refuses_inactive_id(network_execution_case):
    engine,record,clock,published,_=network_execution_case
    with Session(engine) as session:
        user=session.get(User,1)
        legal=session.get(Counterparty,1);legal.name='BNP Paribas SA local';session.add(legal);session.commit()
        quoted=session.get(RfqQuote,published['quote_id'])
        packet=session.get(RfqQuotePublication,published['id'])
        assert json.loads(packet.payload_json)['counterparty_name']!=legal.name
        assert rfq_execution._counterparty(session,session.get(rfq.RfqRequest,record['id']),quoted).id==1
        agreement=request(session,record,quoted.id)
        legal.active=False;session.add(legal);session.commit()
        with pytest.raises(HTTPException): confirm(session,record,agreement,clock)


@pytest.mark.parametrize('changes',[{'counterparty_id':None},{'counterparty_id':999},{'contrepartie':'Unknown '}])
def test_direct_booking_rejects_missing_unknown_or_inconsistent_legal_identity(execution_case,changes):
    engine,record,_,_=execution_case
    with Session(engine) as session:
        body=booking_body(record).model_copy(update={**changes,'rfq_id':None})
        with pytest.raises(HTTPException): deals._book_deal(body,session.get(User,1),session)
        assert not session.exec(select(Deal)).all()


def test_legal_amendment_updates_deal_product_and_keeps_original_snapshot():
    with _session() as session:
        session.add_all([Counterparty(id=1,name='BNP'),Counterparty(id=2,name='SG')]);session.flush()
        deal=_deal(session);deal.counterparty_id=1;deal.contrepartie='BNP';session.add(deal);session.commit()
        change=deals.request_amendment(deal.id,deals.AmendmentRequestCreate(field_name='contrepartie',new_value={'counterparty_id':2},reason='Transfert juridique vers SG'),MAKER,session)
        deals.approve_amendment(deal.id,change['id'],deals.AmendmentDecisionRequest(reason='Contrôle de la nouvelle banque'),CHECKER,session)
        result=deals.apply_amendment(deal.id,change['id'],deals.AmendmentDecisionRequest(reason='Application du transfert juridique'),CHECKER,session)
        assert result['deal']['counterparty_id']==2 and result['deal']['contrepartie']=='SG'
        product=product_repository.load_product(session,deal.product_id)
        assert product.intent.counterparty_id==2 and product.intent.counterparty_name=='SG'
        snapshots=session.exec(select(DealContractVersion).order_by(DealContractVersion.version)).all()
        assert json.loads(snapshots[0].snapshot_json)['counterparty_id']==1
        assert json.loads(snapshots[0].snapshot_json)['contrepartie']=='BNP'
        scoped=credit.portfolio_deals(session,CHECKER,credit.CalculationRequest(counterparty_id=2))
        assert deal.id in [item.id for item in scoped]


def test_legal_amendment_credit_refusal_has_no_partial_mutation(monkeypatch):
    with _session() as session:
        session.add_all([Counterparty(id=1,name='BNP'),Counterparty(id=2,name='SG')]);session.flush()
        deal=_deal(session);deal.counterparty_id=1;deal.contrepartie='BNP';session.add(deal);session.commit()
        change=deals.request_amendment(deal.id,deals.AmendmentRequestCreate(field_name='contrepartie',new_value={'counterparty_id':2},reason='Transfert à soumettre au crédit'),MAKER,session)
        deals.approve_amendment(deal.id,change['id'],deals.AmendmentDecisionRequest(reason='Approbation juridique du changement'),CHECKER,session)
        before=product_repository.load_product(session,deal.product_id).model_dump(mode='json')
        def blocked(*args): raise HTTPException(409,{'code':'CCR_CREDIT_BLOCK','message':'Limite dépassée'})
        monkeypatch.setattr(credit,'enforce_amendment',blocked)
        with pytest.raises(HTTPException): deals.apply_amendment(deal.id,change['id'],deals.AmendmentDecisionRequest(reason='Application sous contrôle crédit'),CHECKER,session)
        session.refresh(deal)
        assert deal.counterparty_id==1 and deal.contrepartie=='BNP' and deal.contract_version==1
        assert product_repository.load_product(session,deal.product_id).model_dump(mode='json')==before
        assert not session.exec(select(DealContractVersion)).all()


def test_real_credit_limit_blocks_bank_transfer_without_rewriting_contract(execution_case):
    from datetime import date
    engine,record,_,_=execution_case
    with Session(engine) as session:
        user=session.get(User,1)
        booked=deals._book_deal(booking_body(record),user,session)
        deal=session.get(Deal,booked['id'])
        credit.save_record(session,user,2,'limits',{'metric':'gross_notional','amount':500000,
            'currency':'EUR','action':'HARD_BLOCK','effective_date':date.today().isoformat()})
        change=deals.request_amendment(deal.id,deals.AmendmentRequestCreate(field_name='contrepartie',
            new_value={'counterparty_id':2},reason='Transfert soumis à la limite destination'),user,session)
        decision=deals.AmendmentDecisionRequest(reason='Application sous contrôle de crédit')
        deals.approve_amendment(deal.id,change['id'],decision,user,session)
        before=product_repository.load_product(session,deal.product_id).model_dump(mode='json')
        with pytest.raises(HTTPException) as blocked: deals.apply_amendment(deal.id,change['id'],decision,user,session)
        assert 'CCR_CREDIT_BLOCK' in str(blocked.value.detail),blocked.value.detail
        session.refresh(deal)
        assert deal.counterparty_id==1 and deal.contract_version==1
        assert product_repository.load_product(session,deal.product_id).model_dump(mode='json')==before


def test_trailing_space_cannot_bypass_a_real_booking_credit_limit(execution_case):
    from datetime import date
    engine,record,_,_=execution_case
    with Session(engine) as session:
        user=session.get(User,1)
        credit.save_record(session,user,1,'limits',{'metric':'gross_notional','amount':500000,
            'currency':'EUR','action':'HARD_BLOCK','effective_date':date.today().isoformat()})
        body=booking_body(record).model_copy(update={'contrepartie':'BNP juridique '})
        with pytest.raises(HTTPException) as blocked: deals._book_deal(body,user,session)
        assert blocked.value.status_code==409 and blocked.value.detail['code']=='CCR_CREDIT_BLOCK'
        assert not session.exec(select(Deal)).all()
