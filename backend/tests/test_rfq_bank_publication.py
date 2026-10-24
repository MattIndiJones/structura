"""Exact human approval, four-eyes policy, immutable delivery and withdrawals."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import select

from backend.app.api import rfq as api, rfq_inbox as inbox, products as products_api
from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import RfqBankQuoteDraft, RfqDeskMembership, RfqQuote, RfqQuotePublication, User
from backend.app.services import rfq_publication as service, rfq_relationships as relationships
from backend.app.services.product_repository import load_product
from backend.tests.test_rfq_bank_pricing import received_case, context
from backend.tests.test_rfq_relationships import network_case


@pytest.fixture
def publication_case(received_case):
    session, users, rfq, item_id = received_case
    membership = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == users[1].id)).first()
    membership.rights_json = '["read","prepare","price","organize","validate_quote","publish_quote"]'
    session.add(membership)
    reviewer = User(id=12, username='bank-reviewer', email='reviewer@example.test', password_hash='x', entity_id=2)
    session.add(reviewer); session.flush()
    session.add(RfqDeskMembership(desk_id=21, user_id=12, rights_json='["read","price","validate_quote"]'))
    session.commit()
    case = inbox.claim_request(item_id, users[1], session)['case']
    product = load_product(session, case['product_id'])
    engine_input = products_api.compose_product_pricing_input(product.product_id, products_api.ProductPricingInput(
        expected_terms_version=1, context=context()), users[1], session)
    computed = price_endpoint(PricingRequest(**engine_input))
    saved = products_api.retain_product_calculation(product.product_id, products_api.ProductCalculationCreate(
        command_key=str(uuid4()), expected_revision=product.revision, pricing_receipt=computed.pricing_receipt), users[1], session)
    yield session, users, rfq, item_id, reviewer, saved['calculations'][-1]['id']


def policy(session, user, item_id, dual=False, version=0):
    return inbox.set_publication_policy(item_id, service.PolicyPut(expected_version=version,
        second_validation_required=dual, max_calculation_age_minutes=60, reason='Politique de recette explicite'), user, session)


def prepare(session, user, item_id, calculation_id, revision=0, **updates):
    body = dict(expected_revision=revision, calculation_id=calculation_id, price=98.5,
        firmness='INDICATIVE', valid_until=datetime.now(timezone.utc)+timedelta(minutes=30), conditions_type='NONE',
        issuer_name='BNP juridique fictif', documentation_reference='Programme EMTN fictif')
    body.update(updates)
    return inbox.prepare_quote(item_id, service.DraftPut(**body), user, session)


def decision(row):
    return service.Decision(expected_revision=row['quote_draft']['revision'], expected_payload_hash=row['quote_draft']['payload_hash'])


def test_single_validator_publishes_commercial_price_once_without_private_inputs(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    # The managed superuser uses explicit desk grants, not the technical admin role.
    users[1].role = 'organization_admin'
    session.add(users[1])
    session.commit()
    policy(session, users[1], item_id)
    draft = prepare(session, users[1], item_id, calculation_id)
    assert api.get_rfq(rfq['id'], users[3], session)['quotes'] == []
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id, decision(draft), users[1], session)
    assert err.value.status_code == 409
    session.rollback()
    approved = inbox.validate_quote(item_id, decision(draft), users[1], session)
    delivered = inbox.publish_quote(item_id, decision(approved), users[1], session)
    assert delivered['publications'][0]['response']['price'] == 98.5
    assert inbox.publish_quote(item_id, decision(approved), users[1], session)['publications'][0]['id'] == delivered['publications'][0]['id']
    assert len(session.exec(select(RfqQuotePublication)).all()) == 1
    received = api.get_rfq(rfq['id'], users[3], session)
    q = received['quotes'][0]
    assert received['status'] == 'quote' and q['price'] == 98.5 and q['origin'] == 'NETWORK' and q['comparable']
    assert q['counterparty'] == 'BNP juridique'
    response = json.dumps(q['publication'])
    for secret in ['calculation_id','model_price','corr_matrix','sigma','validated_by','pricing_receipt']:
        assert secret not in response
    assert api.rfq_exchange_tracking(rfq['id'], users[3], session)['deliveries'][0]['business_status'] == 'QUOTE_RECEIVED'
    assert session.get(RfqQuote, q['id']).price != load_product(session, draft['case']['product_id']).calculations[-1].price


def test_second_validator_required_and_configurable(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id, dual=True)
    draft = prepare(session, users[1], item_id, calculation_id)
    with pytest.raises(HTTPException) as err:
        inbox.validate_quote(item_id, decision(draft), users[1], session)
    assert err.value.status_code == 403
    session.rollback()
    approved = inbox.validate_quote(item_id, decision(draft), reviewer, session)
    assert approved['quote_draft']['validated_by'] == reviewer.id
    assert inbox.publish_quote(item_id, decision(approved), users[1], session)['publications']


def test_editing_price_invalidates_validation_and_stale_recap_is_rejected(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id)
    draft = prepare(session, users[1], item_id, calculation_id)
    inbox.validate_quote(item_id, decision(draft), users[1], session)
    revised = prepare(session, users[1], item_id, calculation_id, revision=1, price=98.75)
    assert revised['quote_draft']['revision'] == 2 and not revised['quote_draft']['validation_current']
    for body in [decision(draft), decision(revised)]:
        with pytest.raises(HTTPException) as err:
            inbox.publish_quote(item_id, body, users[1], session)
        assert err.value.status_code == 409
        session.rollback()


def test_changed_policy_or_revoked_validator_blocks_publication(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id)
    draft = prepare(session, users[1], item_id, calculation_id)
    inbox.validate_quote(item_id, decision(draft), users[1], session)
    policy(session, users[1], item_id, dual=True, version=1)
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id, decision(draft), users[1], session)
    assert err.value.status_code == 409
    session.rollback()
    inbox.validate_quote(item_id, decision(draft), reviewer, session)
    member = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == reviewer.id)).first()
    member.active=False; session.add(member); session.commit()
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id, decision(draft), users[1], session)
    assert err.value.status_code == 409


def test_price_received_is_readonly_and_manual_still_works(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id)
    draft = prepare(session, users[1], item_id, calculation_id)
    inbox.validate_quote(item_id, decision(draft), users[1], session)
    sent = inbox.publish_quote(item_id, decision(draft), users[1], session)
    quote_id=sent['publications'][0]['quote_id']
    for callback in [lambda: api.update_quote(rfq['id'],quote_id,api.QuoteUpdate(price=99),users[3],session),
                     lambda: api.delete_quote(rfq['id'],quote_id,users[3],session)]:
        with pytest.raises(HTTPException) as err: callback()
        assert err.value.status_code==409
        session.rollback()
    manual=api.add_quote(rfq['id'],api.QuoteCreate(provider='Banque manuelle'),users[3],session)
    assert api.update_quote(rfq['id'],manual['id'],api.QuoteUpdate(price=97.8),users[3],session)['price']==97.8


def test_revision_keeps_original_and_does_not_move_selection(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    first=inbox.publish_quote(item_id,decision(draft),users[1],session)['publications'][0]
    from backend.app.db.models import RfqRequest
    record=session.get(RfqRequest,rfq['id']);record.selected_quote_id=first['quote_id'];session.add(record);session.commit()
    revised=prepare(session,users[1],item_id,calculation_id,revision=1,price=98.8)
    inbox.validate_quote(item_id,decision(revised),users[1],session)
    result=inbox.publish_quote(item_id,decision(revised),users[1],session)
    assert len(result['publications'])==2 and result['publications'][1]['state']=='REPLACED'
    assert result['publications'][1]['response']['price']==98.5
    assert api.get_rfq(rfq['id'],users[3],session)['selected_quote_id'] is None
    assert [q['comparable'] for q in api.get_rfq(rfq['id'],users[3],session)['quotes']]==[False,True]


def test_withdrawal_preserves_price_and_acceptance_prevents_withdrawal(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    sent=inbox.publish_quote(item_id,decision(draft),users[1],session)['publications'][0]
    row=session.get(RfqQuotePublication,sent['id']);row.acceptance_received_at=datetime.utcnow();session.add(row);session.commit()
    with pytest.raises(HTTPException) as err:
        inbox.withdraw_quote(item_id,inbox.Withdrawal(publication_id=row.id,reason='Erreur de saisie'),users[1],session)
    assert err.value.status_code==409
    session.rollback()
    row=session.get(RfqQuotePublication,sent['id']);row.acceptance_received_at=None;session.add(row);session.commit()
    withdrawn=inbox.withdraw_quote(item_id,inbox.Withdrawal(publication_id=row.id,reason='Offre retirée avant accord'),users[1],session)
    assert withdrawn['publications'][0]['state']=='WITHDRAWN'
    customer=api.get_rfq(rfq['id'],users[3],session)['quotes'][0]
    assert customer['price']==98.5 and not customer['comparable']


def test_conditional_response_not_ranked_as_compliant_and_stale_calculation_refused(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id,conditions_type='CONDITIONAL',
        conditions=[service.QuoteCondition(code='CREDIT_APPROVAL',description='Sous accord crédit explicite')])
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    inbox.publish_quote(item_id,decision(draft),users[1],session)
    assert not api.get_rfq(rfq['id'],users[3],session)['quotes'][0]['comparable']
    from backend.app.db.models import ProductCalculationRun
    calc=session.get(ProductCalculationRun,calculation_id);calc.calculated_at=datetime.utcnow()-timedelta(hours=2);session.add(calc);session.commit()
    with pytest.raises(HTTPException) as err:
        prepare(session,users[1],item_id,calculation_id,revision=1)
    assert err.value.status_code==409


def test_sender_and_bank_without_explicit_grants_cannot_validate_or_publish(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    with pytest.raises(HTTPException) as err:
        inbox.validate_quote(item_id,decision(draft),users[0],session)
    assert err.value.status_code==404
    member=session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id==users[1].id)).first()
    member.rights_json='["read","prepare","price"]';session.add(member);session.commit()
    for callback in [inbox.validate_quote,inbox.publish_quote]:
        with pytest.raises(HTTPException) as err: callback(item_id,decision(draft),users[1],session)
        assert err.value.status_code==403
        session.rollback()


def test_suspended_relation_rechecked_at_publication(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    relationships.suspend_relation(session,1,users[1],relationships.RelationshipSuspension(
        expected_version=2,suspended=True,reason='Suspension bancaire après contrôle'))
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id,decision(draft),users[1],session)
    assert err.value.status_code==409
    assert session.exec(select(RfqQuotePublication)).all()==[]


def test_payload_fingerprint_is_recomputed_before_publication(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    row=session.get(RfqBankQuoteDraft,item_id)
    payload=json.loads(row.payload_json);payload['price']=99.5
    row.payload_json=json.dumps(payload);session.add(row);session.commit()
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id,decision(draft),users[1],session)
    assert err.value.status_code==409
    assert session.exec(select(RfqQuotePublication)).all()==[]


def test_firm_offer_requires_recognized_treatment_permissions(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    with pytest.raises(HTTPException) as err:
        prepare(session,users[1],item_id,calculation_id,firmness='FIRM')
    assert err.value.status_code==422
    session.rollback()
    assert session.get(RfqBankQuoteDraft,item_id) is None


def test_newer_calculation_invalidates_approved_response(publication_case):
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session,users[1],item_id)
    draft=prepare(session,users[1],item_id,calculation_id)
    inbox.validate_quote(item_id,decision(draft),users[1],session)
    product=load_product(session,draft['case']['product_id'])
    inputs=products_api.compose_product_pricing_input(product.product_id,products_api.ProductPricingInput(
        expected_terms_version=1,context=context(0.04)),users[1],session)
    result=price_endpoint(PricingRequest(**inputs))
    products_api.retain_product_calculation(product.product_id,products_api.ProductCalculationCreate(
        command_key=str(uuid4()),expected_revision=product.revision,pricing_receipt=result.pricing_receipt),users[1],session)
    with pytest.raises(HTTPException) as err:
        inbox.publish_quote(item_id,decision(draft),users[1],session)
    assert err.value.status_code==409


@pytest.mark.parametrize("revocation", ["inactive_membership", "expired_membership", "inactive_user"])
def test_revoked_approval_is_not_current_in_workspace_and_history_is_preserved(publication_case, revocation):
    from backend.app.db.models import RfqSolicitation
    session, users, rfq, item_id, reviewer, calculation_id = publication_case
    policy(session, users[1], item_id, dual=True)
    draft = prepare(session, users[1], item_id, calculation_id)
    approved = inbox.validate_quote(item_id, decision(draft), reviewer, session)
    assert approved['quote_draft']['validation_current']
    member = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == reviewer.id)).first()
    if revocation == "inactive_membership":
        member.active = False
    elif revocation == "expired_membership":
        member.expires_at = datetime.utcnow() - timedelta(seconds=1)
    else:
        reviewer.is_active = False
    session.add(member); session.add(reviewer); session.commit()
    shown = service.workspace(session, session.get(RfqSolicitation, item_id), users[1])
    assert shown['quote_draft']['validation_current'] is False
    assert shown['quote_draft']['validated_by'] == reviewer.id
    assert shown['quote_draft']['validated_at'] == approved['quote_draft']['validated_at']
    with pytest.raises(HTTPException) as refusal:
        inbox.publish_quote(item_id, decision(draft), users[1], session)
    assert refusal.value.status_code == 409
    session.rollback()
    member.active = True; member.expires_at = None; reviewer.is_active = True
    session.add(member); session.add(reviewer); session.commit()
    renewed = inbox.validate_quote(item_id, decision(draft), reviewer, session)
    assert renewed['quote_draft']['validation_current']
