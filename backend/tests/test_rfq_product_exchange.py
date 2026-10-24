"""Native RFQ projections use canonical terms; no network or real database."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import select

from backend.app.api import products as products_api, rfq as rfq_api
from backend.app.api.pricing import price_endpoint
from backend.app.core.product.inputs import terms_from_input
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import AuditEvent, Entity, ProductRecord, RfqProvider, RfqRequest
from backend.app.services.product_repository import load_product, stage_revision, stage_terms
from backend.tests.test_rfq import _make_session, _new_rfq, _rfq_params, USER, OTHER

@pytest.fixture
def dossier():
    with _make_session() as session:
        entity = session.get(Entity, 1)
        entity.name = 'ClientTech'
        session.add(entity)
        session.add(RfqProvider(id=1, label='Banque A'))
        session.add(RfqProvider(id=2, label='Banque B'))
        session.commit()
        rfq = _new_rfq(session)
        yield session, rfq

def preview_body(rfq, **overrides):
    return rfq_api.RfqExchangePreview(**{
        'expected_terms_version': rfq['product_terms_version'], 'shared_title': 'Produit partagé',
        'response_deadline': datetime.now(timezone.utc) + timedelta(hours=1),
        'provider_ids': [1, 2], **overrides,
    })

def test_request_projection_uses_product_and_keeps_private_data_out(dossier):
    session, rfq = dossier
    source = session.get(RfqRequest, rfq['id'])
    product = load_product(session, source.product_id)
    before_revision = product.revision
    before_audit = len(session.exec(select(AuditEvent)).all())
    packet = rfq_api.preview_rfq_exchange(source.id, preview_body(rfq), USER, session)
    request = packet['request']
    assert request['terms'] == product.terms.model_dump(mode='json', exclude={'schedule_error'})
    assert request['terms_fingerprint'] == product.terms_fingerprint
    assert request['nominal'] == 1_000_000
    assert request['requester']['organization'] == 'ClientTech'
    assert 'model_price' not in request and 'commercial' not in request and 'recipients' not in request
    assert 'sigma' not in request['terms']['underlyings'][0]
    assert packet['messages'][0]['request']['recipient'] == {'provider': 'Banque A'}
    assert 'Banque B' not in str(packet['messages'][0])
    assert packet['delivery_available'] is False
    assert session.get(ProductRecord, source.product_id).revision == before_revision
    assert len(session.exec(select(AuditEvent)).all()) == before_audit
    assert rfq_api.get_rfq(source.id, USER, session)['quotes'] == []

def test_rfqs_keep_their_own_terms_version_after_a_product_revision(dossier):
    session, rfq = dossier
    original = load_product(session, rfq['product_id'])
    new_terms = terms_from_input({'script': 'AT MATURITY\n  PAY 0.5', **_rfq_params(), 'settlement_ccy': 'EUR'})
    changed = stage_terms(session, original, new_terms, actor_id=USER.id, reason='Nouveau cas')
    stage_revision(session, changed, expected_revision=original.revision, actor_id=USER.id, action='TEST_REVISION')
    session.commit()
    packet = rfq_api.preview_rfq_exchange(rfq['id'], preview_body(rfq), USER, session)
    assert packet['request']['terms_version'] == original.terms_version
    assert packet['request']['terms']['script'] == original.terms.script
    snapshot = products_api.get_product(rfq['product_id'], USER, session, terms_version=original.terms_version)
    assert snapshot['terms']['script'] == original.terms.script
    assert load_product(session, rfq['product_id']).terms_version == 2

@pytest.mark.parametrize('version', [2, 99])
def test_stale_version_never_prepares_a_different_request(dossier, version):
    session, rfq = dossier
    with pytest.raises(HTTPException) as failure:
        rfq_api.preview_rfq_exchange(rfq['id'], preview_body(rfq, expected_terms_version=version), USER, session)
    assert failure.value.status_code == 409

@pytest.mark.parametrize('ids', [[1, 1], [99]])
def test_invalid_or_duplicate_recipient_is_refused(dossier, ids):
    session, rfq = dossier
    with pytest.raises(HTTPException) as failure:
        rfq_api.preview_rfq_exchange(rfq['id'], preview_body(rfq, provider_ids=ids), USER, session)
    assert failure.value.status_code == 422

def test_inactive_recipient_and_past_or_unzoned_deadlines_are_refused(dossier):
    session, rfq = dossier
    provider = session.get(RfqProvider, 1)
    provider.active = False
    session.add(provider)
    session.commit()
    for body in [preview_body(rfq, provider_ids=[1]), preview_body(rfq, provider_ids=[2], response_deadline=datetime.now(timezone.utc) - timedelta(hours=1)),
                 preview_body(rfq, provider_ids=[2], response_deadline=datetime.now() + timedelta(hours=1))]:
        with pytest.raises(HTTPException) as failure:
            rfq_api.preview_rfq_exchange(rfq['id'], body, USER, session)
        assert failure.value.status_code == 422

def test_another_user_cannot_read_either_projection(dossier):
    session, rfq = dossier
    stranger = OTHER
    with pytest.raises(HTTPException) as failure:
        rfq_api.preview_rfq_exchange(rfq['id'], preview_body(rfq), stranger, session)
    assert failure.value.status_code == 404
    with pytest.raises(HTTPException) as failure:
        rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1), stranger, session)
    assert failure.value.status_code == 404

def test_native_pricing_uses_the_current_engine_and_persisted_private_inputs(dossier):
    session, rfq = dossier
    rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(pricing_params={
        'r': 0.02, 'N': 1000, 'funding_spread': 0.01,
        'valuation_date': rfq['params']['strike_date']}), USER, session)
    packet = rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1), USER, session)
    fields = packet['pricing_input']
    assert fields['script'] == load_product(session, rfq['product_id']).terms.script
    assert fields['r'] == 0.02 and fields['N'] == 1000 and fields['funding_spread'] == 0.01
    priced = price_endpoint(PricingRequest(**fields)).model_dump(mode='json')
    assert 0 < priced['price'] < 1
    assert priced['pricing_receipt']['server_signature']
    recorded = rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(model_price=priced['price'] * 100,
        pricing_receipt=priced['pricing_receipt'], expected_model_input_hash=packet['input_hash']), USER, session)
    assert recorded['model_input_hash'] == packet['input_hash']
    refreshed = rfq_api.get_rfq(rfq['id'], USER, session)
    assert (refreshed['model_price'], refreshed['model_price_at'], refreshed['model_input_hash']) == (
        recorded['model_price'], recorded['model_price_at'], packet['input_hash'])
    assert recorded['model_price'] == pytest.approx(priced['price'] * 100)

def test_price_is_not_recorded_after_inputs_change(dossier):
    session, rfq = dossier
    packet = rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1), USER, session)
    rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(pricing_params={'r': 0.04}), USER, session)
    with pytest.raises(HTTPException) as failure:
        rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(model_price=98.0, expected_model_input_hash=packet['input_hash']), USER, session)
    assert failure.value.status_code == 409
    assert session.get(RfqRequest, rfq['id']).model_price is None


def test_inception_receipt_cannot_attest_a_later_rfq_valuation(dossier):
    from datetime import date
    from backend.app.db.models import RfqBookingEvidence
    session, rfq = dossier
    later = (date.fromisoformat(rfq['params']['strike_date']) + timedelta(days=1)).isoformat()
    rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(pricing_params={
        'valuation_date': later, 'N': 1000}), USER, session)
    packet = rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1), USER, session)
    priced = price_endpoint(PricingRequest(**packet['pricing_input'])).model_dump(mode='json')
    with pytest.raises(HTTPException, match='valuation_date') as error:
        rfq_api.update_rfq(rfq['id'], rfq_api.RfqUpdate(model_price=priced['price'] * 100,
            pricing_receipt=priced['pricing_receipt'], expected_model_input_hash=packet['input_hash']), USER, session)
    assert error.value.status_code == 422
    assert session.get(RfqRequest, rfq['id']).model_price is None
    assert session.get(RfqBookingEvidence, rfq['id']) is None

def test_pricer_can_change_private_context_but_not_contractual_terms(dossier):
    session, rfq = dossier
    product = load_product(session, rfq['product_id'])
    context = {'underlyings': [{'sigma': 0.45, 'q': 0.03}], 'corr_matrix': [[1]], 'r': 0.01, 'N': 1000}
    packet = rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1, context=context), USER, session)
    assert packet['pricing_input']['underlyings'][0]['sigma'] == 0.45
    assert packet['input_hash'] is None
    assert load_product(session, product.product_id).revision == product.revision
    with pytest.raises(HTTPException) as failure:
        rfq_api.compose_rfq_pricing_input(rfq['id'], rfq_api.RfqPricingInput(expected_terms_version=1, context={**context, 'script': 'AT MATURITY\n  PAY 99'}), USER, session)
    assert failure.value.status_code == 422
