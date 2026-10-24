"""C06: pinned RFQ terms, owned transitions and real SQLite link guards."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import rfq as rfq_api
from backend.app.core.product.models import Product
from backend.app.core.product.inputs import terms_from_input
from backend.app.db import models
from backend.app.db.product_migrations import migrate_product_links
from backend.app.services.product_repository import load_product, stage_new_product, stage_revision, stage_terms, ProductError
from backend.tests.test_business_permissions import access_case
from backend.tests.test_products import _pricing_input
from backend.tests.test_booking_legal_exception import exception_body
from backend.tests.test_economic_amendments import booked_case, approved, execution_context, execution_case


@pytest.fixture
def transition_case(access_case):
    session, users, login, managed = access_case
    migrate_product_links(session.connection()); session.commit()
    session.add(models.Client(id=1, entity_id=1, name='C06 Client', status='active', data_origin='native'))
    session.flush()
    session.add(models.ClientMandate(id=1, entity_id=1, client_id=1, name='C06 Mandat', data_origin='native'))
    session.commit()
    yield session, users, login


def create_product(login, **changes):
    payload = dict(command_key=uuid4().hex, name='C06 Product', pricing_input=_pricing_input(),
        intent=dict(side='SELL', nominal=2_000_000, transaction_format='OTC', instrument_family='Swap',
                    payoff_family='Autocall', documentation_reference='ISDA C06'),
        commercial=dict(client_id=1, mandate_id=1))
    response = login('front').post('/api/products', json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def create_rfq(login, product):
    response = login('front').post('/api/rfq', json=dict(pilot_desk_id=11, product_id=product['product_id'],
        product_terms_version=product['terms_version'], name='RFQ C06', kind='indicatif', script_snapshot='Ignored'))
    assert response.status_code == 201, response.text
    return response.json()


def revise(login, product_id):
    current = login('front').get(f'/api/products/{product_id}').json()
    response = login('front').post(f'/api/products/{product_id}/terms', json=dict(command_key=uuid4().hex,
        expected_revision=current['revision'], reason='Nouvelle version explicite',
        pricing_input=_pricing_input(script='AT MATURITY\n  PAY 0.8')))
    assert response.status_code == 200, response.text
    return response.json()


def test_product_to_rfq_inherits_sell_nominal_and_commercial_context(transition_case):
    session, users, login = transition_case
    product = create_product(login); rfq = create_rfq(login, product)
    assert rfq['sens'] == 'vente' and rfq['params']['notional'] == 2_000_000
    assert (rfq['client_id'], rfq['mandate_id'], rfq['transaction_format'], rfq['instrument_family']) == (1, 1, 'OTC', 'Swap')
    retained = load_product(session, product['product_id'])
    assert retained.intent.model_dump(mode='json') == product['intent']
    assert retained.commercial.model_dump(mode='json') == product['commercial']


@pytest.mark.parametrize('change', [dict(name='Nom documentaire'), dict(pricing_params={'r': .02})])
def test_old_rfq_sync_never_regresses_terms_or_overwrites_current_context(transition_case, change):
    session, users, login = transition_case
    rfq = create_rfq(login, create_product(login)); revised = revise(login, rfq['product_id'])
    context = {**revised['intent'], 'nominal': 3_000_000}
    edited = login('front').patch(f"/api/products/{rfq['product_id']}", json=dict(expected_revision=revised['revision'],
        intent=context, reason='Intention courante explicite'))
    assert edited.status_code == 200, edited.text
    before = edited.json()
    updated = login('front').patch(f"/api/rfq/{rfq['id']}", json=change)
    assert updated.status_code == 200, updated.text
    latest = load_product(session, rfq['product_id'])
    assert latest.terms_version == 2 and latest.terms.script == revised['terms']['script']
    assert latest.intent.model_dump(mode='json') == before['intent']
    assert latest.commercial.model_dump(mode='json') == before['commercial']
    assert latest.revision == before['revision'] + 1
    assert latest.rfqs[-1].to_dict()['product_terms_version'] == 1
    assert session.get(models.RfqRequest, rfq['id']).product_terms_version == 1


def test_promoting_terms_from_obsolete_rfq_is_a_conflict_without_writes(transition_case):
    session, users, login = transition_case
    rfq = create_rfq(login, create_product(login)); revised = revise(login, rfq['product_id'])
    original = session.get(models.RfqRequest, rfq['id']).params_json
    params = {**json.loads(original), 'payment_date': '2027-09-20'}
    rejected = login('front').patch(f"/api/rfq/{rfq['id']}", json={'params': params})
    assert rejected.status_code == 409, rejected.text
    session.expire_all()
    assert session.get(models.RfqRequest, rfq['id']).params_json == original
    assert load_product(session, rfq['product_id']).revision == revised['revision']
    assert len(session.exec(select(models.ProductTermsVersion)).all()) == 2


@pytest.mark.parametrize('incoming', [
    {'payment_date': '2099-01-01'}, {'maturity_date': '2099-01-01'}, {'frozen_schedule': {}},
    {'date_conventions': {}}, {'anchor': '2099-01-01'}, {'settlement_ccy': 'USD'},
    {'script': 'AT MATURITY\n  PAY 2'}, {'T': 9}, {'notional': 999}, {'future_unknown_key': 1},
    {'underlyings': [{'ticker': 'OTHER', 'sigma': .3}]},
])
def test_pricing_patch_cannot_smuggle_contract_terms_and_is_atomic(transition_case, incoming):
    session, users, login = transition_case
    rfq = create_rfq(login, create_product(login))
    solicited = login('front').post(f"/api/rfq/{rfq['id']}/quotes", json={'provider': 'BNP Paribas'})
    assert solicited.status_code == 201, solicited.text
    source = session.get(models.RfqRequest, rfq['id'])
    original = source.params_json; before = load_product(session, source.product_id).to_dict()
    rejected = login('front').patch(f"/api/rfq/{rfq['id']}", json={'name': 'Must not persist', 'pricing_params': incoming})
    assert rejected.status_code in (409, 422), rejected.text
    session.expire_all()
    assert session.get(models.RfqRequest, rfq['id']).params_json == original
    assert session.get(models.RfqRequest, rfq['id']).name == 'RFQ C06'
    assert load_product(session, source.product_id).to_dict() == before


def test_allowed_market_inputs_preserve_the_frozen_calendar_and_context(transition_case):
    session, users, login = transition_case
    rfq = create_rfq(login, create_product(login))
    login('front').post(f"/api/rfq/{rfq['id']}/quotes", json={'provider': 'BNP Paribas'})
    before = load_product(session, rfq['product_id'])
    response = login('front').patch(f"/api/rfq/{rfq['id']}", json={'pricing_params': {
        'r': .02, 'N': 1000, 'funding_spread': .01, 'underlyings': [{'sigma': .31, 'q': .02}]}})
    assert response.status_code == 200, response.text
    after = load_product(session, rfq['product_id'])
    assert after.terms == before.terms and after.intent == before.intent and after.commercial == before.commercial
    assert response.json()['params']['r'] == .02
    assert response.json()['params']['underlyings'][0]['sigma'] == .31


@pytest.mark.parametrize('field', ['intent', 'commercial'])
def test_generic_booked_context_mutation_is_refused_but_cosmetic_edit_is_allowed(transition_case, field):
    session, users, login = transition_case
    body = exception_body().model_dump(mode='json')
    body.update(counterparty_id=1, contrepartie='BNP Paribas', legal_identity_exception=None)
    booked = login('superuser').post('/api/deals', json=body)
    assert booked.status_code == 201, booked.text
    deal_id = booked.json()['id']; product_id = booked.json()['product_id']
    original = load_product(session, product_id)
    values = ({**original.intent.model_dump(mode='json'), 'nominal': 5_000_000} if field == 'intent'
              else {'client_id': 1, 'mandate_id': 1})
    rejected = login('superuser').patch(f'/api/products/{product_id}', json=dict(expected_revision=original.revision,
        reason='Tentative de mutation gÃ©nÃ©rique', **{field: values}))
    assert rejected.status_code == 409, rejected.text
    assert load_product(session, product_id) == original
    accepted = login('superuser').patch(f'/api/products/{product_id}', json=dict(expected_revision=original.revision,
        reason='Nom de classement documentaire', name='Nouveau classement', listed=True))
    assert accepted.status_code == 200, accepted.text
    assert load_product(session, product_id).intent == original.intent
    assert session.get(models.Deal, deal_id).nominal == body['nominal']


@pytest.fixture
def linked_db(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path/"c06.db").as_posix()}')
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _record): conn.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        migrate_product_links(connection); migrate_product_links(connection)
    with Session(engine) as session:
        user = models.User(id=1, username='c06', email='c06@example.test', role='admin', password_hash='x')
        session.add(user); session.commit()
        product = stage_new_product(session, Product(terms=terms_from_input(_pricing_input())), user=user)
        changed = stage_terms(session, product, terms_from_input(_pricing_input(script='AT MATURITY\n  PAY 0.9')),
                              actor_id=1, reason='Version 2')
        product = stage_revision(session, changed, expected_revision=product.revision, actor_id=1, action='TEST_VERSION')
        session.commit()
        yield session, product
    engine.dispose()


DURABLE = [models.Deal, models.RfqRequest, models.Indicative, models.Document, models.KidRecord, models.EmtRecord]


def durable(model, product_id, version):
    return model(user_id=1, reference=uuid4().hex, product_id=product_id, product_terms_version=version)


@pytest.mark.parametrize('model', DURABLE, ids=lambda model: model.__tablename__)
@pytest.mark.parametrize('version', [None, 999])
def test_sql_insert_requires_an_existing_product_version_pair(linked_db, model, version):
    session, product = linked_db
    session.add(durable(model, product.product_id, version))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()
    assert not session.exec(select(model)).all()


@pytest.mark.parametrize('model', DURABLE, ids=lambda model: model.__tablename__)
@pytest.mark.parametrize('version', [None, 999])
def test_sql_update_requires_a_valid_version_and_keeps_historical_link(linked_db, model, version):
    session, product = linked_db
    row = durable(model, product.product_id, 1); session.add(row); session.commit()
    identity = row.id
    row.product_terms_version = version; session.add(row)
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()
    assert session.get(model, identity).product_terms_version == 1


def test_repository_and_sql_refuse_retrograde_current_pointer(linked_db):
    session, current = linked_db
    historical = load_product(session, current.product_id, terms_version=1)
    with pytest.raises(ProductError, match='version|termes'):
        stage_revision(session, historical, expected_revision=current.revision, actor_id=1, action='TEST_STALE')
    session.rollback()
    with pytest.raises(IntegrityError):
        session.execute(text('UPDATE products SET terms_version=1 WHERE id=:id'), {'id': current.product_id})
    session.rollback()
    assert load_product(session, current.product_id).terms_version == 2


def test_same_version_cannot_hide_changed_terms_or_an_invalid_revision(linked_db):
    session, current = linked_db
    forged = current.model_copy(update={'terms': terms_from_input(_pricing_input(script='AT MATURITY\n  PAY 0.7'))})
    with pytest.raises(ProductError, match='termes'):
        stage_revision(session, forged, expected_revision=current.revision, actor_id=1, action='TEST_FORGED')
    session.rollback()
    session.add(models.ProductRevision(product_id=current.product_id, revision=current.revision+1,
        terms_version=1, snapshot_json='{}', action='INVALID_DIRECT_WRITE'))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()
    assert load_product(session, current.product_id) == current


@pytest.mark.parametrize('model', DURABLE, ids=lambda model: model.__tablename__)
def test_null_product_is_rejected_even_with_a_valid_version_number(linked_db, model):
    session, _ = linked_db
    session.add(durable(model, None, 1))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()


def test_migration_preserves_unqualified_historical_rows_without_inventing_a_version(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path/"legacy.db").as_posix()}')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(models.User(id=1, username='legacy', email='legacy@example.test', password_hash='x'))
        session.commit()
        row = models.RfqRequest(reference='LEGACY', user_id=1, params_json='{"legacy":true}')
        session.add(row); session.commit(); identity = row.id
        migrate_product_links(session.connection()); session.commit()
        session.expire_all(); restored = session.get(models.RfqRequest, identity)
        assert restored.product_id is None and restored.product_terms_version is None
        assert restored.params_json == '{"legacy":true}'
    engine.dispose()


def test_another_products_version_does_not_qualify_a_link(linked_db):
    session, current = linked_db
    other = stage_new_product(session, Product(terms=terms_from_input(_pricing_input())), user=session.get(models.User, 1))
    session.commit()
    assert current.terms_version == 2 and other.terms_version == 1
    session.add(durable(models.Document, other.product_id, 2))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()
    assert not session.exec(select(models.Document)).all()


def test_rfq_annotation_never_reverts_c04_governed_amendment(execution_case):
    from backend.app.api import deals
    session, user, deal = booked_case(execution_case)
    with session:
        migrate_product_links(session.connection()); session.commit()
        request_id = approved(session, deal, user, value=1_400_000)
        deals.apply_amendment(deal.id, request_id, deals.AmendmentDecisionRequest(reason='Contrôle C06'), user, session)
        before = load_product(session, deal.product_id)
        snapshots = [row.snapshot_json for row in session.exec(select(models.DealContractVersion)).all()]
        rfq_api.update_rfq(deal.rfq_id, rfq_api.RfqUpdate(name='Classement documentaire après amendement'), user, session)
        after = load_product(session, deal.product_id)
        assert deal.nominal == after.intent.nominal == 1_400_000
        assert after.intent == before.intent and after.commercial == before.commercial
        assert after.execution == before.execution and after.lifecycle == before.lifecycle
        assert after.terms == before.terms and after.revision == before.revision+1
        assert [row.snapshot_json for row in session.exec(select(models.DealContractVersion)).all()] == snapshots


def test_sql_guards_allow_c04_payment_amendment_and_keep_rfq_on_old_version(execution_case):
    from datetime import date, timedelta
    from backend.app.api import deals
    session, user, deal = booked_case(execution_case)
    with session:
        migrate_product_links(session.connection()); session.commit()
        old_payment = deal.payment_date
        new_payment = (date.fromisoformat(old_payment)+timedelta(days=1)).isoformat()
        request_id = approved(session, deal, user, field='payment_date', value=new_payment)
        deals.apply_amendment(deal.id, request_id, deals.AmendmentDecisionRequest(reason='Règlement amendé C06'), user, session)
        before = load_product(session, deal.product_id)
        assert before.terms_version == deal.product_terms_version == 2
        assert before.terms.payment_date.isoformat() == new_payment
        assert session.get(models.RfqRequest, deal.rfq_id).product_terms_version == 1
        rfq_api.update_rfq(deal.rfq_id, rfq_api.RfqUpdate(name='Annotation après règlement amendé'), user, session)
        after = load_product(session, deal.product_id)
        assert after.terms_version == 2 and after.terms == before.terms and after.execution == before.execution
        snapshots = session.exec(select(models.DealContractVersion).order_by(models.DealContractVersion.version)).all()
        assert json.loads(snapshots[0].snapshot_json)['payment_date'] == old_payment
        assert json.loads(snapshots[1].snapshot_json)['payment_date'] == new_payment
