"""D01: administrator-only, motivated, atomic and visible legal exceptions."""
import json
from datetime import date
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.api import deals
from backend.app.db import database
from backend.app.db.models import Counterparty, Deal, DealContractVersion, AuditEvent, User
from backend.app.services.product_repository import load_product
from backend.app.core.ccr import service as credit
from backend.tests.test_business_permissions import access_case
from backend.tests.test_rfq_execution import execution_context, execution_case, booking_body
from backend.tests.test_rfq import _rfq_params

REASON = 'Booking exceptionnel autorisé après vérification du dossier juridique'


def exception_body(record=None, **changes):
    if record is None:
        params = _rfq_params()
        params['constats'] = {'FINAL': params['maturity_date']}
        record = {'id': 0, 'product_id': None, 'params': params,
                  'script_snapshot': 'CONSTAT FINAL\nAT FINAL:\n  PAY 1'}
    return booking_body(record).model_copy(update={
        'rfq_id': None, 'product_id': None, 'product_terms_version': None,
        'counterparty_id': None, 'contrepartie': 'Banque Nouvelle SA',
        'legal_identity_exception': deals.LegalIdentityExceptionRequest(reason=REASON), **changes})


def test_http_permissions_default_refusal_and_admin_atomic_acceptance(access_case):
    session, users, login, managed = access_case
    payload = exception_body().model_dump(mode='json')
    for name in ['front', 'ops', 'checker']:
        rejected = login(name).post('/api/deals', json=payload)
        assert rejected.status_code == 403, rejected.text
    # A free-text name alone remains forbidden, including for administrators.
    assert login('superuser').post('/api/deals', json={**payload, 'legal_identity_exception': None}).status_code == 422
    assert not session.exec(select(Deal)).all()
    for exception in [{}, {'reason': REASON, 'actor_user_id': users['superuser'].id}]:
        assert login('superuser').post('/api/deals', json={**payload, 'legal_identity_exception': exception}).status_code == 422
    accepted = login('superuser').post('/api/deals', json=payload)
    assert accepted.status_code == 201, accepted.text
    row = accepted.json()
    assert row['counterparty_id'] is None and row['contrepartie'] == payload['contrepartie']
    evidence = row['legal_identity_exception']
    assert evidence['reason'] == REASON and evidence['actor_user_id'] == users['superuser'].id
    assert evidence['entity_id'] == 1 and evidence['actor_role'] == 'organization_admin'
    assert evidence['credit_status'] == 'NOT_ASSESSED' and evidence['requires_legal_qualification']
    assert evidence['approved_at'] and len(evidence['booking_request_hash']) == 64
    product = load_product(session, row['product_id'])
    assert product.intent.counterparty_id is None
    assert product.execution.to_dict()['legal_identity_exception'] == evidence
    event = session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED')).one()
    assert event.actor_user_id == users['superuser'].id and event.object_id == row['id']
    assert event.reason == REASON and json.loads(event.after_json) == evidence
    assert not session.exec(select(AuditEvent).where(AuditEvent.action == 'CCR_BOOKING_CHECK')).all()
    assert login('superuser').get(f"/api/deals/{row['id']}").json()['legal_identity_exception'] == evidence
    assert login('foreign').get(f"/api/deals/{row['id']}").status_code == (401 if managed else 404)
    foreign_list = login('foreign').get('/api/deals')
    if managed:
        assert foreign_list.status_code == 401
    else:
        assert row['id'] not in [d['id'] for d in foreign_list.json()]
    # Managed technical administrators cannot acquire business override rights.
    if managed:
        assert login('admin').post('/api/deals', json=payload).status_code == 401


@pytest.mark.parametrize('changes', [
    {'legal_identity_exception': deals.LegalIdentityExceptionRequest(reason='   ')},
    {'legal_identity_exception': deals.LegalIdentityExceptionRequest(reason='court')},
    {'legal_identity_exception': deals.LegalIdentityExceptionRequest(reason='x' * 2001)},
    {'contrepartie': ' '}, {'contrepartie': 'Bank\nSA'},
    {'counterparty_id': 999}, {'counterparty_id': 1}, {'ccr_netting_set_id': 123},
    {'contrepartie': '  bnp   JURIDIQUE  '},
])
def test_exception_invalid_inputs_are_audited_and_never_booked(execution_case, changes):
    engine, record, _, _ = execution_case
    with Session(engine) as session:
        with pytest.raises(HTTPException) as error:
            deals._book_deal(exception_body(record, **changes), session.get(User, 1), session)
        assert error.value.status_code == 422
        assert not session.exec(select(Deal)).all()
        assert session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_REJECTED')).all()
        assert not session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED')).all()


def test_exception_cannot_reactivate_inactive_bank_or_skip_known_credit_limit(execution_case):
    engine, record, _, _ = execution_case
    with Session(engine) as session:
        user = session.get(User, 1)
        credit.save_record(session, user, 1, 'limits', {'metric': 'gross_notional', 'amount': 1,
            'currency': 'EUR', 'action': 'HARD_BLOCK', 'effective_date': date.today().isoformat()})
        for body in [exception_body(record, contrepartie='BNP juridique'), exception_body(record, counterparty_id=1)]:
            with pytest.raises(HTTPException): credit.enforce_booking(session, user, body)
        with pytest.raises(HTTPException) as blocked:
            deals._book_deal(booking_body(record), user, session)
        assert blocked.value.detail['code'] == 'CCR_CREDIT_BLOCK'
        bank = session.get(Counterparty, 1); bank.active = False; session.add(bank); session.commit()
        with pytest.raises(HTTPException):
            deals._book_deal(exception_body(record, contrepartie='BNP juridique'), user, session)
        assert not session.exec(select(Deal)).all()


@pytest.mark.parametrize('changes', [{'rfq_id': 'source'}, {'pricing_receipt': None}, {'nominal': -1}])
def test_exception_never_replaces_rfq_or_pricing_or_economics(execution_case, changes):
    engine, record, _, _ = execution_case
    changes = {key: record['id'] if value == 'source' else value for key, value in changes.items()}
    with Session(engine) as session:
        with pytest.raises(HTTPException):
            deals._book_deal(exception_body(record, **changes), session.get(User, 1), session)
        assert not session.exec(select(Deal)).all()
        assert not session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED')).all()


def test_regularization_checks_credit_preserves_exception_and_original_contract(execution_case):
    engine, record, _, _ = execution_case
    with Session(engine) as session:
        user = session.get(User, 1)
        row = deals._book_deal(exception_body(record), user, session)
        evidence = row['legal_identity_exception']
        change = deals.request_amendment(row['id'], deals.AmendmentRequestCreate(field_name='contrepartie',
            new_value={'counterparty_id': 1}, reason='Qualification du dossier juridique confirmé'), user, session)
        decision = deals.AmendmentDecisionRequest(reason='Application sous contrôle de crédit')
        deals.approve_amendment(row['id'], change['id'], decision, user, session)
        credit.save_record(session, user, 1, 'limits', {'metric': 'gross_notional', 'amount': 1,
            'currency': 'EUR', 'action': 'HARD_BLOCK', 'effective_date': date.today().isoformat()})
        with pytest.raises(HTTPException) as blocked:
            deals.apply_amendment(row['id'], change['id'], decision, user, session)
        assert blocked.value.detail['code'] == 'AMENDMENT_LEGAL_OR_CREDIT_BLOCK'
        assert 'CCR_CREDIT_BLOCK' in blocked.value.detail['message']
        session.expire_all()
        assert session.get(Deal, row['id']).counterparty_id is None
        assert load_product(session, row['product_id']).intent.counterparty_id is None
        for policy in session.exec(select(credit.RECORDS['limits'])).all(): session.delete(policy)
        session.commit()
        result = deals.apply_amendment(row['id'], change['id'], decision, user, session)['deal']
        assert result['counterparty_id'] == 1 and result['legal_identity_exception'] == evidence
        product = load_product(session, row['product_id'])
        assert product.intent.counterparty_id == 1 and product.execution.to_dict()['legal_identity_exception'] == evidence
        first = session.exec(select(DealContractVersion).where(DealContractVersion.deal_id == row['id']).order_by(DealContractVersion.version)).first()
        original = json.loads(first.snapshot_json)
        assert original['counterparty_id'] is None and original['legal_identity_exception'] == evidence


def test_exception_column_migration_is_additive_idempotent_and_does_not_qualify_legacy(execution_case, monkeypatch):
    engine, _, _, _ = execution_case
    with Session(engine) as session:
        session.add(Deal(id=1, reference='LEGACY-D01', entity_id=1, user_id=1, contrepartie='Archive inconnue'))
        session.commit()
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE deals DROP COLUMN legal_identity_exception_json'))
    monkeypatch.setattr(database, 'engine', engine)
    for _ in range(2):
        database._migrate()
        with engine.connect() as conn:
            assert 'legal_identity_exception_json' in {row[1] for row in conn.execute(text('PRAGMA table_info(deals)'))}
        with Session(engine) as session:
            legacy = session.get(Deal, 1)
            assert legacy.contrepartie == 'Archive inconnue' and legacy.counterparty_id is None
            assert legacy.legal_identity_exception_json is None


def test_audit_failure_rolls_back_deal_product_and_exception(execution_case, monkeypatch):
    engine, record, _, _ = execution_case
    original = deals.record_audit_event
    def fail_exception_audit(session, **kwargs):
        if kwargs['action'] == 'BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED':
            raise IntegrityError('forced audit insertion failure', {}, RuntimeError('audit unavailable'))
        return original(session, **kwargs)
    monkeypatch.setattr(deals, 'record_audit_event', fail_exception_audit)
    with Session(engine) as session:
        from backend.app.db.models import ProductRecord
        before = len(session.exec(select(ProductRecord)).all())
        with pytest.raises(HTTPException) as error:
            deals._book_deal(exception_body(record), session.get(User, 1), session)
        assert error.value.status_code == 409
        assert not session.exec(select(Deal)).all()
        assert len(session.exec(select(ProductRecord)).all()) == before
        assert not session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_LEGAL_IDENTITY_EXCEPTION_APPROVED')).all()
