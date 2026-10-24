"""Treatment evidence, preserved agreements and concurrent idempotent booking."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import rfq as api, deals, rfq_inbox as inbox, products
from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import (Counterparty, Deal, Entity, RfqDesk, RfqDeskMembership,
    RfqExecutionAgreement, RfqExecutionBooking, RfqProvider, RfqQuote, User)
from backend.app.db.rfq_execution_integrity import install_execution_guards
from backend.app.db.trading_models import TradingRelationship
from backend.app.services import rfq_execution as service, rfq_publication as publication, rfq_relationships as relations
from backend.app.services import rfq_state
from backend.app.services.product_repository import load_product
from backend.tests.product_helpers import add_pricing_receipt
from backend.tests.test_rfq_network_delivery import send_body
from backend.tests.test_rfq import _rfq_params


def setup_case(engine, monkeypatch):
    install_execution_guards(engine)
    clock = {'now': datetime.utcnow()}
    for module in (service, publication, api, deals, rfq_state):
        monkeypatch.setattr(module, 'business_now', lambda: clock['now'])
    with Session(engine) as session:
        session.add_all([Entity(id=1, name='ClientTech'), Entity(id=2, name='BNP')])
        session.flush()
        session.add_all([User(id=1, username='sales', email='sales@example.test', entity_id=1, role='admin', password_hash='x'),
                         User(id=2, username='bank', email='bank@example.test', entity_id=2, role='admin', password_hash='x')])
        session.add_all([Counterparty(id=1, name='BNP juridique'), Counterparty(id=2, name='ClientTech juridique')])
        session.add_all([RfqDesk(id=11, name='Sales', entity_id=1), RfqDesk(id=21, name='Pricing', entity_id=2)])
        session.flush()
        session.add_all([RfqDeskMembership(desk_id=11, user_id=1, rights_json='["read","prepare","price","select","solicit","book"]'),
                         RfqDeskMembership(desk_id=21, user_id=2, rights_json='["read","prepare","price","organize","validate_quote","publish_quote"]'),
                         RfqProvider(id=1, label='BNP manuel', counterparty_id=1)])
        session.commit()
        user = session.get(User, 1)
        params = _rfq_params(r=0.03, N=1000, model='constant', corr_matrix=[[1.0]])
        params['underlyings'][0].update(sigma=0.2, q=0.0)
        params['constats'] = {'FINAL': params['maturity_date']}
        rfq = api.create_rfq(api.RfqCreate(pilot_desk_id=11, name='Athena de recette', kind='to_trade',
            transaction_format='EMTN', instrument_family='Note', payoff_family='Autocall',
            documentation_reference='Programme EMTN fictif',
            script_snapshot='CONSTAT FINAL\nAT FINAL:\n  PAY 1', params=params), user, session)
        api.update_rfq(rfq['id'], api.RfqUpdate(model_price=100), user, session)
    return engine, rfq, clock


@pytest.fixture
def execution_context(moteur_integre, monkeypatch):
    return setup_case(moteur_integre, monkeypatch)


def select_manual(engine, rfq, clock):
    with Session(engine) as session:
        user = session.get(User, 1)
        quote = api.add_quote(rfq['id'], api.QuoteCreate(provider='BNP manuel'), user, session)
        api.update_quote(rfq['id'], quote['id'], api.QuoteUpdate(price=98.5, currency='EUR', status='recu',
            valid_until=(clock['now']+timedelta(minutes=2)).replace(tzinfo=timezone.utc).isoformat()), user, session)
        api.update_rfq(rfq['id'], api.RfqUpdate(selected_quote_id=quote['id']), user, session)
    return quote['id']


@pytest.fixture
def execution_case(execution_context):
    engine, rfq, clock = execution_context
    return engine, rfq, clock, select_manual(engine, rfq, clock)


def request(session, rfq, quote_id, user=None, **changes):
    user = user or session.get(User, 1)
    product = load_product(session, rfq['product_id'])
    body = dict(quote_id=quote_id, expected_terms_version=1, expected_terms_fingerprint=product.terms_fingerprint,
        command_key=str(uuid4()), source='PHONE', reference='Appel BNP prix demandé', bank_contact='Desk BNP')
    body.update(changes)
    return api.declare_treatment(rfq['id'], service.TreatmentRequest(**body), user, session)


def confirmation(agreement, clock, **changes):
    body = dict(expected_snapshot_hash=agreement['snapshot_hash'], execution_reference='BNP-EXEC-001',
        acceptance_received_at=clock['now'].replace(tzinfo=timezone.utc),
        confirmed_at=clock['now'].replace(tzinfo=timezone.utc),
        acceptance_evidence='Courriel horodaté de réception BNP', source='BANK_CONFIRMATION',
        evidence='Confirmation BNP sur les termes, prix et nominal exacts', bank_contact='Desk BNP')
    body.update(changes)
    return service.TreatmentConfirmation(**body)


def confirm(session, rfq, agreement, clock, **changes):
    return api.confirm_treatment(rfq['id'], agreement['id'], confirmation(agreement, clock, **changes), session.get(User, 1), session)


def booking_body(rfq, agreement=None):
    p = rfq['params']
    body = dict(rfq_id=rfq['id'], product_id=rfq['product_id'], product_terms_version=1,
        execution_agreement_id=agreement['id'] if agreement else None,
        sens='vente', contrepartie='BNP juridique', devise='EUR', product_type='', nominal=p['notional'],
        fair_value=100, price_traded=98.5, trade_date=p['strike_date'],
        strike_date=p['strike_date'], value_date=p['value_date'], maturity_date=p['maturity_date'],
        payment_date=p['payment_date'], T=p['T'], underlyings=p['underlyings'], observation_times=[p['T']],
        script_snapshot=rfq['script_snapshot'], market_snapshot={'r':3, 'constats':p['constats'],
            'underlyings':[{'name':'UL1','ticker':'TK1','ccy':'EUR','sigma':20,'q':0}]})
    return deals.DealCreate(**{**add_pricing_receipt(body), "counterparty_id": 1})


@pytest.fixture
def network_execution_case(execution_context):
    engine, rfq, clock = execution_context
    with Session(engine) as session:
        sales, bank = session.get(User,1), session.get(User,2)
        for entity_id, cpty_id, actor_id in [(1,1,1),(2,2,2)]:
            session.add(TradingRelationship(id=entity_id, entity_id=entity_id, counterparty_id=cpty_id,
                reference=f'BOOKING-{entity_id}', updated_by=actor_id, terms_json=json.dumps({
                    'status':'ACTIVE', 'currency':'EUR', 'documentation_reference':'Programme EMTN fictif',
                    'note_distribution_allowed':True, 'effective_date':rfq['params']['strike_date']})))
        session.commit()
        perimeter=relations.RelationshipTerms(formats=['EMTN'], instruments=['Note'],payoff_families=['Autocall'],
            currencies=['EUR'],effective_date=rfq['params']['strike_date'],solicitation_allowed=True,indicative_allowed=False,to_trade_allowed=True,
            treatment_allowed=True,documentation_reference='Programme EMTN fictif')
        relation=relations.create_relation(session,sales,relations.RelationshipCreate(partner_entity_id=2,
            receiver_desk_id=21,reference='CLIENT-BNP',terms=perimeter,counterparty_id=1,trading_relationship_id=1,
            reason='Recette RFQ avec traitement'))
        relation=relations.update_relation(session,relation['id'],bank,relations.RelationshipUpdate(
            expected_version=relation['version'],receiver_desk_id=21,terms=perimeter,counterparty_id=2,
            trading_relationship_id=2,reason='Mapping et accord bancaire'))
        for actor in (sales,bank):
            relation=relations.recognize_relation(session,relation['id'],actor,relations.RelationshipDecision(
                expected_version=relation['version'],reason='Reconnaissance des termes'))
        # The helper indexes the sales actor at 3, matching existing network fixtures.
        sent=api.send_rfq_exchange(rfq['id'],send_body(session,[sales,bank,None,sales],rfq,relation),sales,session)
        item_id=sent['solicitation_ids'][0]
        case=inbox.claim_request(item_id,bank,session)['case']
        product=load_product(session,case['product_id'])
        pricing=products.compose_product_pricing_input(product.product_id,products.ProductPricingInput(
            expected_terms_version=1,context={'r':0.03,'N':1000,'model':'constant','corr_matrix':[[1.0]],
                'underlyings':[{'sigma':0.2,'q':0.0}]}),bank,session)
        calculation=price_endpoint(PricingRequest(**pricing))
        saved=products.retain_product_calculation(product.product_id,products.ProductCalculationCreate(
            command_key=str(uuid4()),expected_revision=product.revision,pricing_receipt=calculation.pricing_receipt),bank,session)
        clock['now']=datetime.utcnow()
        inbox.set_publication_policy(item_id,publication.PolicyPut(expected_version=0,second_validation_required=False,
            max_calculation_age_minutes=60,reason='Politique explicite de recette'),bank,session)
        prepared=inbox.prepare_quote(item_id,publication.DraftPut(expected_revision=0,calculation_id=saved['calculations'][-1]['id'],
            price=98.5,firmness='INDICATIVE',valid_until=(clock['now']+timedelta(minutes=2)).replace(tzinfo=timezone.utc),
            conditions_type='NONE',issuer_name='BNP juridique',documentation_reference='Programme EMTN fictif'),bank,session)
        decision=publication.Decision(expected_revision=prepared['quote_draft']['revision'],
            expected_payload_hash=prepared['quote_draft']['payload_hash'])
        inbox.validate_quote(item_id,decision,bank,session)
        published=inbox.publish_quote(item_id,decision,bank,session)
        q=published['publications'][0]
        api.update_rfq(rfq['id'],api.RfqUpdate(selected_quote_id=q['quote_id']),sales,session)
    return engine,rfq,clock,q,item_id


def test_network_booking_requires_exact_confirmation_without_rewriting_publication(network_execution_case):
    engine,rfq,clock,published,item_id=network_execution_case
    with Session(engine) as session:
        from backend.app.api import ccr
        context=ccr.rfq_credit_context(rfq['id'],published['quote_id'],session.get(User,1),session)
        assert context['counterparty_id']==1
        with pytest.raises(HTTPException): ccr.rfq_credit_context(rfq['id'],published['quote_id'],session.get(User,2),session)
        with pytest.raises(HTTPException): deals.book_deal(booking_body(rfq),session.get(User,1),session)
        with pytest.raises(HTTPException):
            deals.book_deal(booking_body(rfq).model_copy(update={'rfq_id':None}),session.get(User,1),session)
        agreement=request(session,rfq,published['quote_id'])
        agreement=confirm(session,rfq,agreement,clock)
        with pytest.raises(HTTPException):
            inbox.withdraw_quote(item_id,inbox.Withdrawal(publication_id=published['id'],reason='Retrait après accord'),session.get(User,2),session)
        session.rollback()
        deal=deals.book_deal(booking_body(rfq,agreement),session.get(User,1),session)
        assert deal['rfq_id']==rfq['id']
        quote=api.get_rfq(rfq['id'],session.get(User,1),session)['quotes'][0]
        assert quote['firmness']=='INDICATIVE' and quote['price']==98.5
        assert quote['publication']['state']=='RESERVED'


def test_relationship_suspension_blocks_new_confirmation(network_execution_case):
    engine,rfq,clock,published,item_id=network_execution_case
    with Session(engine) as session:
        agreement=request(session,rfq,published['quote_id'])
        from backend.app.db.models import RfqSolicitation
        relation_id=session.get(RfqSolicitation,item_id).relationship_id
        relation=relations.row_for(session,session.get(relations.RfqRelationship,relation_id),1)
        relations.suspend_relation(session,relation_id,session.get(User,1),relations.RelationshipSuspension(
            expected_version=relation['version'],suspended=True,reason='Suspension du traitement'))
        with pytest.raises(HTTPException): confirm(session,rfq,agreement,clock)
        session.rollback()
        assert session.get(RfqExecutionAgreement,agreement['id']).state=='REQUESTED'


def test_requested_is_not_confirmation_and_cancel_preserves_history(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session, rfq, quote_id)
        with pytest.raises(HTTPException, match='confirmation'):
            deals.book_deal(booking_body(rfq, agreement), session.get(User,1), session)
        assert not session.exec(select(Deal)).all()
        cancelled = api.cancel_treatment(rfq['id'], agreement['id'], api.TreatmentCancellation(reason='Appel interrompu'), session.get(User,1), session)
        assert cancelled['state']=='CANCELLED'
        assert request(session, rfq, quote_id)['id'] != agreement['id']
        assert len(api.get_rfq(rfq['id'], session.get(User,1), session)['execution_agreements'])==2


def test_external_confirmation_freezes_terms_and_preserves_manual_route(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session, rfq, quote_id)
        clock['now'] += timedelta(seconds=1)
        confirmed = confirm(session, rfq, agreement, clock, source='PHONE_DECLARATION')
        assert confirmed['state']=='CONFIRMED' and confirmed['written_confirmation_pending']
        for action in [lambda: api.update_rfq(rfq['id'],api.RfqUpdate(selected_quote_id=None),session.get(User,1),session),
                       lambda: api.update_quote(rfq['id'],quote_id,api.QuoteUpdate(price=99),session.get(User,1),session),
                       lambda: api.cancel_treatment(rfq['id'],agreement['id'],api.TreatmentCancellation(reason='Annulation'),session.get(User,1),session)]:
            with pytest.raises(HTTPException): action()
            session.rollback()
        assert session.get(RfqQuote,quote_id).price==98.5
        assert load_product(session, rfq['product_id']).rfqs[-1].to_dict()['execution_agreements'][0]['state']=='CONFIRMED'


def test_confirmed_trade_books_after_quote_expiry_and_replays_once(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session, rfq, quote_id)
        accepted = clock['now'] + timedelta(seconds=1)
        clock['now'] += timedelta(minutes=3)
        agreement = confirm(session, rfq, agreement, clock, acceptance_received_at=accepted.replace(tzinfo=timezone.utc))
        payload = booking_body(rfq,agreement).model_dump(mode='json')
        deal = deals.book_deal(deals.DealCreate(**payload),session.get(User,1),session)
        again = deals.book_deal(deals.DealCreate(**payload),session.get(User,1),session)
        assert again['id']==deal['id'] and len(session.exec(select(Deal)).all())==1
        assert len(session.exec(select(RfqExecutionBooking)).all())==1
        assert api.get_rfq(rfq['id'],session.get(User,1),session)['execution_agreements'][0]['state']=='BOOKED_LOCALLY'
        assert deal['rfq_provenance']['execution_agreement']['execution_reference']=='BNP-EXEC-001'
        with pytest.raises(HTTPException) as failure:
            deals.book_deal(deals.DealCreate(**{**payload,'price_traded':99}),session.get(User,1),session)
        assert failure.value.status_code==409


def test_expired_offer_cannot_be_backdated_into_a_new_treatment(execution_case):
    engine, rfq, clock, quote_id = execution_case
    clock['now'] += timedelta(minutes=3)
    with Session(engine) as session:
        with pytest.raises(HTTPException): request(session,rfq,quote_id)
        assert not session.exec(select(RfqExecutionAgreement)).all()


def test_acceptance_after_expiry_or_future_confirmation_is_rejected(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session,rfq,quote_id)
        clock['now'] += timedelta(minutes=3)
        with pytest.raises(HTTPException): confirm(session,rfq,agreement,clock)
        session.rollback()
        with pytest.raises(HTTPException):
            confirm(session,rfq,agreement,clock, confirmed_at=(clock['now']+timedelta(minutes=1)).replace(tzinfo=timezone.utc))
        session.rollback()
        assert session.get(RfqExecutionAgreement,agreement['id']).state=='REQUESTED'


def test_booking_refusal_preserves_confirmation_and_block_reason(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session,rfq,quote_id)
        agreement = confirm(session,rfq,agreement,clock)
        body = booking_body(rfq,agreement).model_copy(update={'nominal':1})
        with pytest.raises(HTTPException): deals.book_deal(body,session.get(User,1),session)
        row = api.get_rfq(rfq['id'],session.get(User,1),session)['execution_agreements'][0]
        assert row['state']=='CONFIRMED' and row['booking_block_reason'] and not row['booked_deal']
        assert load_product(session,rfq['product_id']).rfqs[-1].to_dict()['execution_agreements'][0]['booking_block_reason']


def test_no_book_right_and_foreign_organization_cannot_confirm(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        with pytest.raises(HTTPException): request(session,rfq,quote_id,user=session.get(User,2))
        membership = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id==1)).one()
        membership.rights_json='["read","prepare","price","select"]'
        session.add(membership); session.commit()
        with pytest.raises(HTTPException) as failure: request(session,rfq,quote_id)
        assert failure.value.status_code==403


def test_immutable_evidence_and_duplicate_execution_reference(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        agreement = request(session,rfq,quote_id)
        confirm(session,rfq,agreement,clock)
        with pytest.raises(IntegrityError):
            session.execute(text('UPDATE rfq_execution_agreements SET snapshot_json = :value WHERE id = :id'), {'value':'{}','id':agreement['id']})
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text('DELETE FROM rfq_execution_agreements WHERE id = :id'), {'id':agreement['id']})
            session.commit()
        session.rollback()
        with pytest.raises(HTTPException): confirm(session,rfq,agreement,clock,execution_reference='OTHER-REFERENCE')


def test_manual_booking_without_new_confirmation_keeps_existing_workflow(execution_case):
    engine, rfq, clock, quote_id = execution_case
    with Session(engine) as session:
        result = deals.book_deal(booking_body(rfq),session.get(User,1),session)
        assert result['rfq_id']==rfq['id'] and not session.exec(select(RfqExecutionAgreement)).all()


def test_duplicate_execution_reference_across_rfqs_has_conflict(execution_case):
    engine,rfq,clock,quote_id=execution_case
    with Session(engine) as session:
        agreement=request(session,rfq,quote_id)
        confirm(session,rfq,agreement,clock)
        other=api.create_rfq(api.RfqCreate(pilot_desk_id=11,name='Autre consultation',kind='to_trade',
            script_snapshot=rfq['script_snapshot'],params=rfq['params'],transaction_format='EMTN',
            instrument_family='Note',payoff_family='Autocall'),session.get(User,1),session)
    other_quote=select_manual(engine,other,clock)
    with Session(engine) as session:
        second=request(session,other,other_quote)
        with pytest.raises(HTTPException) as failure:
            confirm(session,other,second,clock,execution_reference=' bnp-exec-001 ')
        assert failure.value.status_code==409
        session.rollback()
        assert session.get(RfqExecutionAgreement,second['id']).state=='REQUESTED'


def test_external_conflict_keeps_confirmed_trade_and_blocks_booking(execution_case):
    engine,rfq,clock,quote_id=execution_case
    with Session(engine) as session:
        agreement=request(session,rfq,quote_id)
        confirm(session,rfq,agreement,clock)
        service.flag_external_conflict(session,quote_id,str(uuid4()),'Révision externe après accord : revue requise')
        session.commit()
        with pytest.raises(HTTPException): deals.book_deal(booking_body(rfq,agreement),session.get(User,1),session)
        assert session.get(RfqExecutionAgreement,agreement['id']).state=='CONFIRMED'
        assert session.get(RfqExecutionAgreement,agreement['id']).review_required_reason
        assert not session.exec(select(Deal)).all()


def test_concurrent_booking_of_same_execution_returns_one_deal(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'execution.db'}",connect_args={'check_same_thread':False,'timeout':15})
    SQLModel.metadata.create_all(engine)
    engine,rfq,clock=setup_case(engine,monkeypatch)
    quote_id=select_manual(engine,rfq,clock)
    with Session(engine) as session:
        agreement=request(session,rfq,quote_id)
        agreement=confirm(session,rfq,agreement,clock)
    payload=booking_body(rfq,agreement).model_dump(mode='json')
    barrier=Barrier(2)
    def execute():
        with Session(engine) as session:
            user=session.get(User,1)
            barrier.wait(timeout=10)
            return deals.book_deal(deals.DealCreate(**payload),user,session)['id']
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(execute) for _ in range(2)]
            ids=[future.result(timeout=25) for future in futures]
        assert ids[0]==ids[1]
        with Session(engine) as session:
            assert len(session.exec(select(Deal)).all())==1
            assert len(session.exec(select(RfqExecutionBooking)).all())==1
    finally: engine.dispose()
