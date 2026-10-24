"""C07: lossless drafts, bounded dossiers and audited invalid booking inputs."""
import json
from datetime import datetime, date
from uuid import uuid4
from time import perf_counter

import pytest
from sqlmodel import select

from backend.app.db.models import ProductRecord, Deal, AuditEvent
from backend.app.core.product.models import Product
from backend.app.core.product.inputs import terms_from_input
from backend.app.services.product_repository import stage_new_product, stage_revision, stage_calculation, load_product
from backend.app.core.valuation_context import build_pricing_receipt
from backend.app.services.product_receipts import signed_receipt
from backend.app.api.auth import receipt_signing_secret
from backend.app.api import deals as deals_api
from backend.tests.test_products import product_client, _pricing_input, _create
from backend.tests.test_business_permissions import access_case
from backend.tests.test_booking_legal_exception import exception_body
from backend.tests.test_booking_mtm_daily import book, add_run


def draft_input():
    payload = _pricing_input(script='PARAM() COUPON = 8%\nAT MATURITY\n  PAY 1')
    payload.update(T=None, user_params={'COUPON': [.08, None, .12]}, strike_date=None,
                   value_date=None, maturity_date=None, payment_date=None, anchor=None)
    return payload


def test_partial_draft_can_be_retained_completed_and_reopened_without_losing_cells(product_client):
    client = product_client
    draft = _create(client, pricing_input=draft_input())
    assert draft['terms']['parameters'][0]['value'] == [.08, None, .12]
    assert draft['terms']['T'] is None and draft['terms']['schedule_error']
    with pytest.raises(ValueError, match=r'COUPON\[2\]'):
        Product.model_validate(draft).terms.require_complete()
    blocked = client.post(f"/api/products/{draft['product_id']}/pricing-input", json={
        'expected_terms_version': 1, 'context': {'underlyings': [{'sigma': .2}]}})
    assert blocked.status_code == 422
    completed = _pricing_input(script=draft['terms']['script'], user_params={'COUPON': [.08, .10, .12]})
    response = client.post(f"/api/products/{draft['product_id']}/terms", json={
        'command_key': uuid4().hex, 'expected_revision': draft['revision'],
        'reason': 'Compléter le brouillon sans remplacer ses données', 'pricing_input': completed})
    assert response.status_code == 200, response.text
    reopened = client.get(f"/api/products/{draft['product_id']}").json()
    assert reopened['terms_version'] == 2 and reopened['terms']['parameters'][0]['value'] == [.08, .10, .12]
    Product.model_validate({k:v for k,v in reopened.items() if k != 'description'}).terms.require_complete()
    historic = client.get(f"/api/products/{draft['product_id']}?terms_version=1").json()
    assert historic['terms']['parameters'][0]['value'] == [.08, None, .12]
    stale = client.post(f"/api/products/{draft['product_id']}/terms", json={
        'command_key': uuid4().hex, 'expected_revision': draft['revision'],
        'reason': 'Ancienne copie de travail', 'pricing_input': completed})
    assert stale.status_code == 409


def add_calculation(client, product, price=.98):
    canonical = load_product(client.session, product['product_id'])
    receipt = signed_receipt(build_pricing_receipt(_pricing_input(), price),
        secret=receipt_signing_secret(), result={'price': price})
    enriched = stage_calculation(client.session, canonical, user=client.users['alice'], receipt=receipt)
    saved = stage_revision(client.session, enriched, expected_revision=canonical.revision,
        actor_id=client.users['alice'].id, action='TEST_CALCULATION', reason='Isolated C07 calculation')
    client.session.commit()
    return saved


def test_library_labels_old_price_and_paginates_calculations_and_history(product_client):
    client = product_client; product = _create(client)
    for i in range(7): add_calculation(client, product, .98 + i*.001)
    before = load_product(client.session, product['product_id'])
    revised = client.post(f"/api/products/{product['product_id']}/terms", json={
        'command_key': uuid4().hex, 'expected_revision': before.revision, 'reason': 'Nouvelle version sans calcul',
        'pricing_input': _pricing_input(script='AT MATURITY\n  PAY .8')})
    assert revised.status_code == 200, revised.text
    summary = client.get('/api/products?paged=true&limit=1').json()['items'][0]
    assert summary['latest_price'] is None and summary['historical_price_terms_version'] == 1
    assert summary['historical_price'] == pytest.approx(98.6)
    path = f"/api/products/{product['product_id']}"
    first = client.get(path+'?calculations_limit=3').json()
    second = client.get(path+'?calculations_limit=3&calculations_offset=3').json()
    assert len(first['calculations']) == len(second['calculations']) == 3
    assert first['calculation_page']['has_more'] and second['calculation_page']['has_more']
    assert not ({c['id'] for c in first['calculations']} & {c['id'] for c in second['calculations']})
    assert first['calculations'][-1]['price'] == pytest.approx(98.6)
    history = client.get(path+'/history?limit=2').json()
    assert len(history['items']) == 2 and history['has_more']
    assert history['items'][0]['terms_version'] == 2
    client.current['user'] = client.users['bob']
    assert client.get(path+'/history').status_code == 404
    assert client.get(path+'?calculations_limit=3').status_code == 404


def test_large_library_materializes_only_the_requested_page(product_client, monkeypatch):
    client = product_client
    for i in range(220):
        stage_new_product(client.session, Product(name=f'C07 volume {i}', terms=terms_from_input(_pricing_input())),
            user=client.users['alice'])
    client.session.commit()
    from backend.app.api import products as api
    loaded = []; original = api.load_product
    def traced(*args, **kwargs):
        loaded.append(args[1]); assert kwargs['calculation_page'] == (0, 0)
        return original(*args, **kwargs)
    monkeypatch.setattr(api, 'load_product', traced)
    start = perf_counter()
    first = client.get('/api/products?paged=true&limit=20').json()
    elapsed = perf_counter() - start
    second = client.get('/api/products?paged=true&limit=20&offset=20').json()
    assert len(loaded) == 40 and len(set(loaded)) == 40
    assert first['has_more'] and second['has_more']
    assert not ({p['id'] for p in first['items']} & {p['id'] for p in second['items']})
    assert client.get('/api/products?limit=101').status_code == 422
    print(f'C07 library: 220 dossiers, page=20, first_page_seconds={elapsed:.4f}, bytes={len(json.dumps(first))}')


def test_calculation_comparison_can_cross_a_page_boundary(product_client):
    client = product_client; product = _create(client)
    for i in range(3): add_calculation(client, product, .95 + i*.01)
    path = f"/api/products/{product['product_id']}"
    last = client.get(path+'?calculations_limit=1').json()['calculations'][0]
    assert last['price'] == pytest.approx(97)
    detail = client.get(path+f"/calculations/{last['id']}").json()
    assert detail['previous_calculation_id'] != last['id']
    previous = client.get(path+f"/calculations/{detail['previous_calculation_id']}").json()
    assert previous['result']['price'] == pytest.approx(.96)
    assert previous['terms_version'] == detail['terms_version']


def test_incomplete_retained_product_cannot_be_booked_using_a_different_complete_receipt(product_client):
    client = product_client; product = _create(client, pricing_input=draft_input())
    priced = _pricing_input(script=product['terms']['script'], user_params={'COUPON':[.08,.1,.12]})
    receipt = signed_receipt(build_pricing_receipt(priced, 1), secret=receipt_signing_secret(), result={'price':1})
    response = client.post('/api/deals', json={
        'product_id':product['product_id'], 'product_terms_version':1,
        'sens':'vente', 'contrepartie':'Banque Test', 'counterparty_id':1, 'devise':'EUR',
        'nominal':1_000_000, 'fair_value':100, 'price_traded':100,
        'trade_date':'2026-09-14', 'strike_date':priced['strike_date'], 'value_date':priced['value_date'],
        'maturity_date':priced['maturity_date'], 'payment_date':priced['payment_date'], 'T':1,
        'underlyings':[{'name':'SX5E','ticker':'^STOXX50E','ccy':'EUR'}], 'observation_times':[1],
        'script_snapshot':priced['script'], 'market_snapshot':{}, 'pricing_receipt':receipt,
    })
    assert response.status_code == 422, response.text
    assert response.json()['detail']['code'] == 'PRODUCT_TERMS_MISMATCH'
    assert not client.session.exec(select(Deal)).all()
    assert load_product(client.session, product['product_id']).to_dict() == product
    assert client.session.exec(select(AuditEvent).where(AuditEvent.action=='BOOKING_REJECTED')).one()


@pytest.mark.parametrize('field', ['nominal', 'fair_value', 'price_traded', 'T', 'underlyings', 'market_snapshot'])
@pytest.mark.parametrize('number', [float('inf'), float('-inf'), float('nan')])
def test_non_finite_booking_is_refused_before_hashing_and_leaves_no_partial_product(access_case, field, number):
    session, users, login, managed = access_case
    body = exception_body().model_dump(mode='json')
    body.update(counterparty_id=1, contrepartie='BNP Paribas', legal_identity_exception=None)
    if field == 'underlyings': body['underlyings'][0]['s0_abs'] = number
    elif field == 'market_snapshot': body['market_snapshot']['funding_spread'] = number
    else: body[field] = number
    response = login('superuser').post('/api/deals', content=json.dumps(body), headers={'Content-Type':'application/json'})
    assert response.status_code == 422, response.text
    assert response.json()['detail']['code'] == 'BOOKING_NON_FINITE'
    assert any(p.startswith(field) for p in response.json()['detail']['fields'])
    assert not session.exec(select(Deal)).all() and not session.exec(select(ProductRecord)).all()
    audit = session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_REJECTED')).one()
    assert 'BOOKING_NON_FINITE' in audit.reason
    json.loads(audit.after_json, parse_constant=lambda value: pytest.fail('Invalid strict JSON audit: '+value))


@pytest.mark.parametrize('funding', [dict(funding_spread=.01), dict(funding_spread=0), dict(funding_curve=[]),
    dict(funding_curve=[[1,.01]]), dict(funding_source_reference='Desk curve'), dict(new_material_option=True)])
def test_custom_funding_never_masks_the_older_standard_booking_run(book, funding):
    session, user, deal = book
    eligible = add_run(session, deal, datetime(2026,9,17,9), mode='none')
    add_run(session, deal, datetime(2026,9,17,10), mode='none', **funding)
    rows = deals_api.latest_mtm_runs(user, session, str(deal.id), valuation_date=date(2026,9,17), recalibrate='none')
    assert [r['id'] for r in rows] == [eligible.id]
    assert len(deals_api.list_valuation_runs(deal.id, user, session)) == 2
