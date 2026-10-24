"""C04: stable concentration identities and atomic replacement credit checks."""
import json
from datetime import date, timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from backend.app.api import deals, portfolios, admin
from backend.app.core.ccr import service as credit
from backend.app.db import database
from backend.app.db.models import (Deal, Counterparty, User, TradeAmendmentRequest,
    DealContractVersion, ProductRecord, AuditEvent, ValuationRun)
from backend.app.services.product_repository import load_product
from backend.tests.test_rfq_execution import execution_context, execution_case, booking_body
from backend.tests.test_business_permissions import access_case, _rfq_with_evidence
from backend.tests.test_booking_legal_exception import exception_body
from backend.tests.test_ccr_scope import scope_client

REASON = 'Amendement économique contrôlé et documenté'
DECISION = deals.AmendmentDecisionRequest(reason=REASON)


def approved(session, deal, user, field='nominal', value=1_400_000):
    request = deals.request_amendment(deal.id, deals.AmendmentRequestCreate(
        field_name=field, new_value=value, reason=REASON), user, session)
    deals.approve_amendment(deal.id, request['id'], DECISION, user, session)
    return request['id']


def policy(session, user, cpty=1, metric='gross_notional', amount=1_500_000, action='HARD_BLOCK'):
    return credit.save_record(session, user, cpty, 'limits', {'metric': metric, 'amount': amount,
        'currency': 'EUR', 'action': action, 'effective_date': date.today().isoformat()})


def booked_case(case):
    engine, record, _, _ = case
    session = Session(engine)
    user = session.get(User, 1)
    row = deals._book_deal(booking_body(record), user, session)
    return session, user, session.get(Deal, row['id'])


def test_limit_blocks_two_million_atomically_but_accepts_replacement_at_1_4m(execution_case):
    session, user, deal = booked_case(execution_case)
    with session:
        policy(session, user)
        request_id = approved(session, deal, user, value=2_000_000)
        before = load_product(session, deal.product_id).model_dump(mode='json')
        with pytest.raises(HTTPException) as blocked:
            deals.apply_amendment(deal.id, request_id, DECISION, user, session)
        assert blocked.value.detail['credit_check']['after']['gross_notional'] == 2_000_000
        session.refresh(deal)
        assert deal.nominal == 1_000_000 and deal.contract_version == 1
        assert load_product(session, deal.product_id).model_dump(mode='json') == before
        assert not session.exec(select(DealContractVersion)).all()
        request = session.get(TradeAmendmentRequest, request_id)
        assert request.status == 'APPROVED' and request.credit_check_json is None
        # Close the refused proposal before making a new proposal on the same field.
        request.status = 'REJECTED'; session.add(request); session.commit()
        allowed = approved(session, deal, user, value=1_400_000)
        result = deals.apply_amendment(deal.id, allowed, DECISION, user, session)
        proof = result['amendment']['credit_check']
        assert proof['after']['gross_notional'] == 1_400_000  # Not 2.4 million.
        assert proof['decision']['booking_allowed'] and proof['evaluation_basis'] == 'RESULTING_PORTFOLIO'
        assert proof['limits_policy'][0]['id'] and proof['input_hash']
        assert result['deal']['contract_version'] == 2
        product = load_product(session, deal.product_id)
        assert product.intent.nominal == 1_400_000
        assert product.execution.to_dict()['amendment_credit_check'] == proof
        snapshots = session.exec(select(DealContractVersion).order_by(DealContractVersion.version)).all()
        assert json.loads(snapshots[0].snapshot_json)['nominal'] == 1_000_000
        assert json.loads(snapshots[1].snapshot_json)['amendment_credit_check'] == proof
        audit = session.exec(select(AuditEvent).where(AuditEvent.action == 'AMENDMENT_APPLIED')).one()
        assert json.loads(audit.metadata_json)['credit_check'] == proof
        with pytest.raises(HTTPException): deals.apply_amendment(deal.id, allowed, DECISION, user, session)


def test_current_policy_and_other_positions_are_reread_at_application(execution_case):
    session, user, deal = booked_case(execution_case)
    with session:
        request_id = approved(session, deal, user)
        policy(session, user, amount=1_500_000)
        # Another position appears after approval, including outside any portfolio.
        other = Deal(reference='LATE-EXPOSURE', entity_id=1, user_id=1, counterparty_id=1,
                     contrepartie='Old descriptive name', nominal=200_000, devise='EUR')
        session.add(other); session.commit()
        with pytest.raises(HTTPException) as blocked:
            deals.apply_amendment(deal.id, request_id, DECISION, user, session)
        assert blocked.value.detail['credit_check']['after']['gross_notional'] == 1_600_000
        assert session.get(Deal, deal.id).nominal == 1_000_000


def test_concentration_and_limit_survive_rename_inactive_bank_and_historical_labels(execution_case):
    engine, _, _, _ = execution_case
    with Session(engine) as session:
        user = session.get(User, 1)
        bank = session.get(Counterparty, 1); bank.limit_eur = 1_500_000; session.add(bank)
        rows = [Deal(id=90, reference='OLD-A', nominal=1_000_000, counterparty_id=1, contrepartie='Historical bank'),
                Deal(id=91, reference='OLD-B', nominal=600_000, counterparty_id=1, contrepartie=bank.name)]
        session.commit()
        before = portfolios._aggregate_exposure_by_counterparty(rows, session)
        admin.update_counterparty(1, admin.CounterpartyUpdate(name='Renamed legal bank', active=False,
            reason=REASON), user, session)
        after = portfolios._aggregate_exposure_by_counterparty(rows, session)
        first, second = before['by_counterparty'][0], after['by_counterparty'][0]
        for field in ['identity_key', 'counterparty_id', 'nominal_eur', 'limit_eur', 'limit_breached', 'deals']:
            assert first[field] == second[field]
        assert second['limit_breached'] and second['identity_status'] == 'INACTIVE'
        assert second['contrepartie'] == 'Renamed legal bank'
        assert [row.contrepartie for row in rows] == ['Historical bank', 'BNP juridique']


def test_unknown_same_name_exception_and_missing_fx_remain_explicit(execution_case, monkeypatch):
    engine, _, _, _ = execution_case
    with Session(engine) as session:
        bank = session.get(Counterparty, 1); bank.limit_eur = 100; session.add(bank); session.commit()
        rows = [Deal(id=90, reference='KNOWN', nominal=50, counterparty_id=1, contrepartie=bank.name),
                Deal(id=91, reference='LEGACY', nominal=500, contrepartie=bank.name),
                Deal(id=92, reference='D01', nominal=1000, contrepartie='Uncatalogued', devise='ZZZ',
                     legal_identity_exception_json='{"reason":"approved at booking"}')]
        monkeypatch.setattr(portfolios, '_fx_to_reporting', lambda currency, *args, **kwargs: 1 if currency == 'EUR' else None)
        result = portfolios._aggregate_exposure_by_counterparty(rows, session)
        assert len(result['by_counterparty']) == 3
        assert result['nominal_total_eur'] == 550 and result['hhi'] is None
        assert {row['id'] for row in result['deals_requiring_qualification']} == {91, 92}
        assert result['deals_requiring_qualification'][1]['administrator_exception']
        legacy = next(row for row in result['by_counterparty'] if row['identity_key'].startswith('unqualified:') and row['nominal_eur'])
        assert legacy['limit_eur'] is None and legacy['limit_breached'] is None
        assert not result['coverage_complete'] and result['deals_missing_fx'][0]['id'] == 92


def test_measured_limit_missing_data_blocks_then_qualified_current_value_is_used(execution_case):
    session, user, deal = booked_case(execution_case)
    with session:
        policy(session, user, metric='current_exposure')
        request_id = approved(session, deal, user, value=2_000_000)
        with pytest.raises(HTTPException) as missing:
            deals.apply_amendment(deal.id, request_id, DECISION, user, session)
        assert missing.value.detail['credit_check']['after']['current_exposure'] is None
        assert missing.value.detail['credit_check']['decision']['hard_block']
        # A real frozen settlement valuation qualifies the same 1.0 fraction.
        deal.status = 'en_reglement'; deal.settlement_amount = 1
        session.add(deal); session.add(ValuationRun(deal_id=deal.id, user_id=user.id, contract_version=1,
            context_hash='QUALIFIED', context_json='{"settlement_claim":true,"fixed_price":1}',
            result_json=json.dumps({'valuation_date':str(date.today()), 'mtm':1})))
        session.commit()
        with pytest.raises(HTTPException) as breach:
            deals.apply_amendment(deal.id, request_id, DECISION, user, session)
        proof = breach.value.detail['credit_check']
        assert proof['after']['current_exposure'] == 2_000_000
        assert proof['valuation_run_id'] and proof['decision']['hard_block']
        assert session.get(Deal, deal.id).nominal == 1_000_000


@pytest.mark.parametrize('metric,limit', [('current_exposure',1_500_000), ('pfe95',1_500_000),
    ('pfe99',1_500_000), ('cva',60_000)])
@pytest.mark.parametrize('new_nominal,allowed', [(1_400_000,True),(2_000_000,False)])
def test_qualified_native_measures_drive_replacement_decision(execution_case, metric, limit, new_nominal, allowed):
    session, user, deal = booked_case(execution_case)
    with session:
        policy(session,user,metric=metric,amount=limit)
        credit.save_record(session,user,1,'profiles',{'recovery':.4,'recovery_source':'USER_ASSUMPTION',
            'curve_source':'MANUAL','pd_measure':'RISK_NEUTRAL','pd_curve':[[5,.1]],'has_isda':False,'has_csa':False})
        deal.status='en_reglement';deal.settlement_amount=1;session.add(deal)
        session.add(ValuationRun(deal_id=deal.id,user_id=user.id,contract_version=1,context_hash='QUALIFIED',
            context_json='{"settlement_claim":true,"fixed_price":1}',
            result_json=json.dumps({'valuation_date':str(date.today()),'mtm':1})))
        session.commit()
        request_id=approved(session,deal,user,value=new_nominal)
        if allowed:
            result=deals.apply_amendment(deal.id,request_id,DECISION,user,session)
            proof=result['amendment']['credit_check']
            assert result['deal']['nominal']==new_nominal
        else:
            with pytest.raises(HTTPException) as blocked:
                deals.apply_amendment(deal.id,request_id,DECISION,user,session)
            proof=blocked.value.detail['credit_check']
            assert session.get(Deal,deal.id).nominal==1_000_000
        assert proof['after'][metric] > 0
        assert proof['decision']['booking_allowed'] is allowed
        assert proof['after']['gross_notional']==new_nominal


def test_changed_payment_horizon_cannot_reuse_old_measured_value(execution_case):
    session,user,deal=booked_case(execution_case)
    with session:
        policy(session,user,metric='current_exposure')
        session.add(ValuationRun(deal_id=deal.id,user_id=user.id,contract_version=1,context_hash='OLD-HORIZON',
            context_json='{"settlement_claim":true,"fixed_price":1}',
            result_json=json.dumps({'valuation_date':str(date.today()),'mtm':1})))
        session.commit()
        old_payment=deal.payment_date
        new_payment=(date.fromisoformat(old_payment)+timedelta(days=7)).isoformat()
        request_id=approved(session,deal,user,field='payment_date',value=new_payment)
        with pytest.raises(HTTPException) as blocked:
            deals.apply_amendment(deal.id,request_id,DECISION,user,session)
        assert blocked.value.detail['credit_check']['after']['current_exposure'] is None
        session.refresh(deal)
        assert deal.payment_date==old_payment and deal.contract_version==1


def test_d01_attestation_does_not_authorize_later_nominal_change(execution_case):
    engine,record,_,_=execution_case
    with Session(engine) as session:
        user=session.get(User,1)
        row=deals._book_deal(exception_body(record),user,session)
        deal=session.get(Deal,row['id'])
        request_id=approved(session,deal,user)
        with pytest.raises(HTTPException): deals.apply_amendment(deal.id,request_id,DECISION,user,session)
        session.refresh(deal)
        assert deal.counterparty_id is None and deal.nominal==1_000_000
        assert json.loads(deal.legal_identity_exception_json)['reason']==row['legal_identity_exception']['reason']


@pytest.mark.parametrize('metric', ['pfe95', 'pfe99', 'ead', 'cva', 'stressed_exposure'])
def test_full_measured_limits_are_never_cleared_by_nominal_only_data(execution_case, metric):
    session, user, deal = booked_case(execution_case)
    with session:
        policy(session, user, metric=metric)
        request_id = approved(session, deal, user)
        with pytest.raises(HTTPException) as missing:
            deals.apply_amendment(deal.id, request_id, DECISION, user, session)
        proof = missing.value.detail['credit_check']
        assert proof['requested_mode'] == 'FULL'
        assert proof['after'][metric] is None and proof['decision']['hard_block']


def test_http_c01_permissions_and_shared_operations_amendment(access_case, monkeypatch):
    session, users, login, managed = access_case
    body = exception_body(counterparty_id=1, contrepartie='BNP Paribas', legal_identity_exception=None)
    booked = deals._book_deal(body, users['ops'], session)
    path = f"/api/deals/{booked['id']}/amendment-requests"
    command = {'field_name':'nominal', 'new_value':1_400_000, 'reason':REASON}
    for name in ['front','checker','foreign']:
        assert login(name).post(path, json=command).status_code in (401,403,404)
    request = login('ops').post(path, json=command)
    assert request.status_code == 201, request.text
    request_id = request.json()['id']
    if managed:
        assert login('front').post(f'{path}/{request_id}/approve',json={'reason':REASON}).status_code == 403
        assert login('checker').post(f'{path}/{request_id}/approve',json={'reason':REASON}).status_code == 403
    monkeypatch.setenv('STRUCTURA_AMENDMENT_FOUR_EYES','1')
    assert login('ops').post(f'{path}/{request_id}/approve',json={'reason':REASON}).status_code == 403
    approved_response = login('checker').post(f'{path}/{request_id}/approve',json={'reason':REASON})
    assert approved_response.status_code == 200, approved_response.text
    applied = login('checker').post(f'{path}/{request_id}/apply',json={'reason':REASON})
    assert applied.status_code == 200, applied.text
    assert applied.json()['amendment']['credit_check']['decision']['status'] == 'NO_LIMIT'
    assert 'sigma' not in json.dumps(applied.json()['amendment']['credit_check'])


@pytest.mark.parametrize('value', [float('inf'), float('nan'), 10**1000])
def test_non_finite_numeric_amendments_are_rejected(execution_case, value):
    session, user, deal = booked_case(execution_case)
    with session:
        request = deals.request_amendment(deal.id, deals.AmendmentRequestCreate(field_name='nominal',new_value=value,reason=REASON), user, session)
        with pytest.raises(HTTPException): deals.approve_amendment(deal.id,request['id'],DECISION,user,session)
        assert session.get(Deal,deal.id).nominal == 1_000_000


def test_credit_evidence_migration_is_additive_and_idempotent(execution_case, monkeypatch):
    session, user, deal = booked_case(execution_case)
    with session:
        request_id = approved(session, deal, user)
    engine = execution_case[0]
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE trade_amendment_requests DROP COLUMN credit_check_json'))
    monkeypatch.setattr(database,'engine',engine)
    for _ in range(2):
        database._migrate()
        with Session(engine) as session:
            request = session.get(TradeAmendmentRequest,request_id)
            assert request.status == 'APPROVED' and request.credit_check_json is None


def test_read_scope_and_strict_checker_scope_remain_identical_to_c01(access_case,monkeypatch):
    session,users,login,managed=access_case
    source=_rfq_with_evidence(session,users['front'])
    review=login('ops').get(f"/api/rfq/{source['id']}/booking-review").json()
    booked=login('ops').post(f"/api/rfq/{source['id']}/book",json={'review_token':review['review_token']}).json()
    path=f"/api/deals/{booked['id']}/amendment-requests"
    request=login('ops').post(path,json={'field_name':'nominal','new_value':1_400_000,'reason':REASON}).json()
    # Same organization is insufficient when the RFQ desk is not readable.
    outsider=users['outsider'];outsider.role='checker';session.add(outsider);session.commit()
    monkeypatch.setenv('STRUCTURA_AMENDMENT_FOUR_EYES','1')
    assert login('outsider').post(f"{path}/{request['id']}/approve",json={'reason':REASON}).status_code==404
    assert login('outsider').get('/api/deals/amendment-requests/pending').json()==[]
    exposure=login('outsider').get('/api/portfolios/exposure-by-counterparty')
    assert exposure.status_code==200
    assert exposure.json()['nominal_total_eur']==0 and exposure.json()['by_counterparty']==[]


def test_replacement_uat_is_scoped_to_its_batch_without_production_consumption(scope_client):
    client,_,_,positions,_=scope_client
    from backend.app.db.database import get_session
    session=client.app.dependency_overrides[get_session]()
    user=session.get(User,positions[0].user_id)
    for position in positions[:2]:
        proof=credit.enforce_amendment(session,user,position,{'nominal':1_400_000})
        assert proof['after']['gross_notional']==1_400_000
        assert proof['data_scope']==('UAT' if position.uat_batch_id else 'PRODUCTION')
        assert proof['decision']['booking_allowed']
        assert position.nominal==1_000_000


def test_two_concurrent_amendments_cannot_both_consume_the_same_remaining_limit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlmodel import SQLModel,create_engine
    from backend.app.db.models import Entity
    from backend.tests.product_helpers import attach_product_to_deal
    engine=create_engine(f'sqlite:///{tmp_path/"concurrent-credit.db"}',connect_args={'check_same_thread':False,'timeout':15})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Entity(id=1,name='Desk'));session.flush()
        user=User(id=1,username='admin',email='admin@example.test',password_hash='x',entity_id=1,role='admin')
        session.add_all([user,Counterparty(id=1,name='Bank')]);session.commit()
        request_ids=[]
        for index in (1,2):
            position=Deal(id=index,reference=f'CONCURRENT-{index}',entity_id=1,user_id=1,
                transaction_format='EMTN',instrument_family='Note',
                counterparty_id=1,contrepartie='Bank',nominal=500_000,script_snapshot='AT MATURITY\n  PAY 1',T=1,
                strike_date=str(date.today()),value_date=str(date.today()),maturity_date=str(date.today()+timedelta(days=365)),
                payment_date=str(date.today()+timedelta(days=369)),underlyings_json='[{"name":"UL1","ticker":"TK1","ccy":"EUR"}]')
            attach_product_to_deal(session,position);session.add(position);session.commit()
            request_ids.append(approved(session,position,user,value=900_000))
        policy(session,user)
    barrier=Barrier(2)
    def apply(index):
        with Session(engine) as session:
            user=session.get(User,1)
            barrier.wait(timeout=10)
            try:
                deals.apply_amendment(index+1,request_ids[index],DECISION,user,session)
                return 'APPLIED'
            except HTTPException as error:
                assert error.status_code==409
                return 'BLOCKED'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(apply,[0,1]))==['APPLIED','BLOCKED']
    with Session(engine) as session:
        assert sorted(row.nominal for row in session.exec(select(Deal)).all())==[500_000,900_000]
        assert len(session.exec(select(DealContractVersion)).all())==2
    engine.dispose()
