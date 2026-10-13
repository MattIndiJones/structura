"""Private native bank pricing of immutable received terms on FK-enforced memory DB."""
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import select

from backend.app.api import products as products_api, rfq as rfq_api, rfq_inbox as inbox
from backend.app.api.pricing import price_endpoint
from backend.app.core.product.inputs import pricing_input
from backend.app.core.product.models import TradeIntent
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import AuditEvent, ProductRecord, RfqBankCase, RfqDeskMembership, RfqSolicitation, User
from backend.app.services import rfq_bank as bank
from backend.app.services.product_repository import load_product
from backend.tests.test_rfq_relationships import network_case, active
from backend.tests.test_rfq_network_delivery import send_body


@pytest.fixture
def received_case(network_case):
    session, users, rfq = network_case
    relation = active(session, users)
    session.add(RfqDeskMembership(desk_id=21, user_id=users[1].id,
        rights_json='["read","prepare","price","organize"]'))
    session.commit()
    sent = rfq_api.send_rfq_exchange(rfq['id'], send_body(session, users, rfq, relation), users[3], session)
    yield session, users, rfq, sent['solicitation_ids'][0]


def context(rate=0.03):
    return {'r': rate, 'N': 1000, 'model': 'constant', 'corr_matrix': [[1.0]],
            'underlyings': [{'sigma': 0.2, 'q': 0.0}]}


def test_claim_creates_bank_product_once_with_identical_terms(received_case):
    session, users, rfq, item_id = received_case
    item = session.get(RfqSolicitation, item_id)
    snapshot = json.loads(item.request_json)
    first = inbox.claim_request(item_id, users[1], session)
    product = load_product(session, first['case']['product_id'])
    assert product.terms.model_dump(mode='json', exclude={'schedule_error'}) == snapshot['terms']
    assert product.terms_fingerprint == snapshot['terms_fingerprint']
    assert product.intent.nominal == snapshot['nominal'] and product.intent.side == 'SELL'
    assert product.product_id != rfq['product_id']
    assert product.data_origin == 'imported' and not product.listed
    assert product.commercial.client_id is None and not product.rfqs
    assert session.get(ProductRecord, product.product_id).entity_id == users[1].entity_id
    assert inbox.claim_request(item_id, users[1], session)['case']['product_id'] == product.product_id
    assert len(session.exec(select(RfqBankCase)).all()) == 1
    assert len(session.exec(select(AuditEvent).where(AuditEvent.action == 'RFQ_BANK_CLAIMED')).all()) == 1


def test_native_engine_prices_and_retains_signed_bank_calculation_privately(received_case):
    session, users, rfq, item_id = received_case
    case = inbox.claim_request(item_id, users[1], session)['case']
    product = load_product(session, case['product_id'])
    params = products_api.compose_product_pricing_input(product.product_id,
        products_api.ProductPricingInput(expected_terms_version=product.terms_version, context=context()), users[1], session)
    result = price_endpoint(PricingRequest(**params))
    assert result.price is not None
    saved = products_api.retain_product_calculation(product.product_id, products_api.ProductCalculationCreate(
        command_key=str(uuid4()), expected_revision=product.revision, pricing_receipt=result.pricing_receipt), users[1], session)
    assert len(saved['calculations']) == 1
    assert load_product(session, product.product_id).terms_fingerprint == product.terms_fingerprint
    work = inbox.received_request(item_id, users[1], session)
    assert work['case']['calculations'][0]['price'] == pytest.approx(result.price * 100)
    displayed_at = datetime.fromisoformat(work['case']['calculations'][0]['calculated_at'])
    assert displayed_at.utcoffset() == timedelta(0)
    assert displayed_at.replace(tzinfo=None) == datetime.fromisoformat(result.pricing_receipt['calculated_at'])
    calculation = products_api.get_product_calculation(product.product_id, saved['calculations'][0]['id'], users[1], session)
    assert calculation['input']['r'] == 0.03
    sender = rfq_api.rfq_exchange_tracking(rfq['id'], users[3], session)
    assert 'calculations' not in json.dumps(sender) and 'model_price' not in json.dumps(sender)
    assert rfq_api.get_rfq(rfq['id'], users[3], session)['quotes'] == []
    assert load_product(session, rfq['product_id']).terms_fingerprint == product.terms_fingerprint


def test_foreign_admin_and_read_only_bank_member_cannot_read_private_product(received_case):
    session, users, rfq, item_id = received_case
    product_id = inbox.claim_request(item_id, users[1], session)['case']['product_id']
    reader = User(id=10, username='bank-reader', email='reader@example.test', password_hash='x', entity_id=2)
    session.add(reader); session.flush()
    session.add(RfqDeskMembership(desk_id=21, user_id=10, rights_json='["read"]')); session.commit()
    for user in [users[0], users[2], users[3], reader]:
        with pytest.raises(HTTPException) as err:
            products_api.get_product(product_id, user, session)
        assert err.value.status_code == 404
    work = inbox.received_request(item_id, reader, session)
    assert 'product_id' not in work['case'] and 'calculations' not in work['case']
    with pytest.raises(HTTPException) as err:
        inbox.claim_request(item_id, reader, session)
    assert err.value.status_code == 403


def test_terms_and_trade_intent_locked_even_through_product_apis(received_case):
    session, users, rfq, item_id = received_case
    product = load_product(session, inbox.claim_request(item_id, users[1], session)['case']['product_id'])
    payload = pricing_input(product, context())
    payload['script'] = 'AT MATURITY\n  PAY 0.5'
    with pytest.raises(HTTPException) as err:
        products_api.revise_product_terms(product.product_id, products_api.ProductTermsUpdate(command_key=str(uuid4()),
            expected_revision=product.revision, pricing_input=payload, reason='Modification interdite'), users[1], session)
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:
        products_api.update_product(product.product_id, products_api.ProductUpdate(expected_revision=product.revision,
            intent=TradeIntent(nominal=2_000_000), reason='Nominal différent'), users[1], session)
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:
        products_api.compose_product_pricing_input(product.product_id, products_api.ProductPricingInput(
            expected_terms_version=1, context={**context(), 'user_params': {'coupon': 0.1}}), users[1], session)
    assert err.value.status_code == 422


def test_assignment_is_explicit_stale_protected_and_ownership_not_transferred(received_case):
    session, users, rfq, item_id = received_case
    case = inbox.claim_request(item_id, users[1], session)['case']
    colleague = User(id=11, username='bank-pricer', email='pricer@example.test', password_hash='x', entity_id=2)
    session.add(colleague); session.flush()
    session.add(RfqDeskMembership(desk_id=21, user_id=11, rights_json='["read","prepare","price"]')); session.commit()
    with pytest.raises(HTTPException) as err:
        inbox.claim_request(item_id, colleague, session)
    assert err.value.status_code == 409
    reassigned = inbox.assign_request(item_id, inbox.BankAssignment(responsible_user_id=11, expected_revision=1,
        reason='Passage au structureur'), users[1], session)
    assert reassigned['case']['responsible_user_id'] == 11 and reassigned['case']['product_id'] == case['product_id']
    with pytest.raises(HTTPException) as err:
        products_api.compose_product_pricing_input(case['product_id'], products_api.ProductPricingInput(
            expected_terms_version=1, context=context()), users[1], session)
    assert err.value.status_code == 403
    assert products_api.compose_product_pricing_input(case['product_id'], products_api.ProductPricingInput(
        expected_terms_version=1, context=context()), colleague, session)['r'] == 0.03
    with pytest.raises(HTTPException) as err:
        inbox.assign_request(item_id, inbox.BankAssignment(responsible_user_id=users[1].id, expected_revision=1,
            reason='Ancien écran'), colleague, session)
    assert err.value.status_code == 409


def test_closed_round_or_revoked_membership_blocks_new_private_calculations(received_case):
    session, users, rfq, item_id = received_case
    case = inbox.claim_request(item_id, users[1], session)['case']
    from backend.app.services.rfq_exchange import round_for
    row = round_for(session, rfq['id']); row.state = 'SUPERSEDED'; session.add(row); session.commit()
    with pytest.raises(HTTPException) as err:
        products_api.compose_product_pricing_input(case['product_id'], products_api.ProductPricingInput(
            expected_terms_version=1, context=context()), users[1], session)
    assert err.value.status_code == 409
    assert not inbox.received_request(item_id, users[1], session)['open_for_work']
    membership = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.user_id == users[1].id)).first()
    membership.active = False; session.add(membership); session.commit()
    with pytest.raises(HTTPException) as err:
        products_api.get_product(case['product_id'], users[1], session)
    assert err.value.status_code == 404


def test_unsupported_terms_remain_readable_without_silent_default_product(received_case):
    session, users, rfq, item_id = received_case
    item = session.get(RfqSolicitation, item_id)
    request = json.loads(item.request_json); request['product_model']['payscript_semantics_version'] = 999
    item.request_json = json.dumps(request); session.add(item); session.commit()
    assert inbox.received_request(item_id, users[1], session)['request']['product_model']['payscript_semantics_version'] == 999
    with pytest.raises(HTTPException) as err:
        inbox.claim_request(item_id, users[1], session)
    assert err.value.status_code == 422
    session.rollback()
    assert session.get(RfqBankCase, item_id) is None
    assert len(session.exec(select(ProductRecord)).all()) == 1
