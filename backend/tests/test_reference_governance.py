"""C03: governed catalogs, local reuse, frozen identities and legal controls."""
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select
from backend.tests.test_hybrid_bootstrap import managed, login
from backend.app.api import admin, rfq, deals
from backend.app.db import database
from backend.app.db.models import (Underlying, Counterparty, RfqProvider, RfqQuote,
                                   AuditEvent, ReferenceCatalogState, User, DealContractVersion)
from backend.app.core.ccr import service as credit
from backend.app.services.legal_identity import provider_identity, quote_counterparty

REASON='Qualification du référentiel par le desk'


def test_catalog_uses_local_metadata_offline_and_prevents_currency_divergence(managed, monkeypatch):
    config, engine, client, _=managed
    with Session(engine) as session:
        session.add(Underlying(ticker='AAPL',label='Apple',group_name='US',ccy='USD',exchange='NMS',asset_class='equity'))
        session.commit()
    monkeypatch.setattr(admin,'probe_ticker',lambda *_: pytest.fail('Local instrument must not trigger external fetching'))
    headers=login(client,config,'superuser')
    body={'ticker':'AAPL','group':'Technologie','reason':REASON}
    response=client.post('/api/admin/underlyings',json=body,headers=headers)
    assert response.status_code==201,response.text
    row=response.json()
    assert row['label']=='Apple' and row['ccy']=='USD' and row['asset_class']=='equity' and row['probe']['source']=='LOCAL_REFERENCE'
    assert client.post('/api/admin/underlyings',json={**body,'group':'Autre','ccy':'EUR'},headers=headers).status_code==409
    assert client.patch(f"/api/admin/underlyings/{row['id']}",json={'ccy':'JPY','reason':REASON},headers=headers).status_code==200
    with Session(engine) as session:
        assert {u.ccy for u in session.exec(select(Underlying)).all()}=={'JPY'}
        events=session.exec(select(AuditEvent).where(AuditEvent.action.in_(['REFERENCE_CREATED','REFERENCE_CURRENCY_UPDATED','REFERENCE_UPDATED']))).all()
        assert len(events)==3 and all(e.reason==REASON and e.actor_user_id for e in events)
        assert json.loads(events[-1].before_json)['ccy']=='USD'


@pytest.mark.parametrize('path,body',[
    ('counterparties',{'name':'  '}),('counterparties',{'name':'Bank','limit_eur':-1}),
    ('rfq-providers',{'label':'   '}),('underlyings',{'ticker':'X','label':' ','group':'Test'}),
    ('underlyings',{'ticker':'X','label':'X','group':'Test','ccy':'ZZZ'}),
])
def test_invalid_reference_metadata_is_rejected(managed,monkeypatch,path,body):
    config,_,client,_=managed
    monkeypatch.setattr(admin,'probe_ticker',lambda *_:{'ok':True,'ccy':'USD'})
    headers=login(client,config,'superuser')
    assert client.post('/api/admin/'+path,json={**body,'reason':REASON},headers=headers).status_code==422


def test_reference_reason_authorization_soft_delete_and_explicit_revalidation(managed,monkeypatch):
    config,engine,client,_=managed
    headers=login(client,config,'superuser')
    body={'ticker':'NEW','label':'Nouveau titre','group':'Test','reason':REASON}
    monkeypatch.setattr(admin,'probe_ticker',lambda *_:{'ok':True})
    assert client.post('/api/admin/underlyings',json={**body,'reason':'  '},headers=headers).status_code==422
    assert client.post('/api/admin/underlyings',json=body,headers=login(client,config,'front')).status_code==403
    response=client.post('/api/admin/underlyings',json=body,headers=headers)
    assert response.status_code==201,response.text
    row=response.json();path=f"/api/admin/underlyings/{row['id']}"
    assert row['ccy']=='' and row['metadata_status']=='TO_QUALIFY'
    monkeypatch.setattr(admin,'probe_ticker',lambda *_:{'ok':True,'ccy':'USD'})
    result=client.post(path+'/revalidate',json={'reason':REASON},headers=headers).json()
    assert result['probe']['ccy']=='USD' and not result['applied'] and result['reference']['ccy']==''
    assert client.request('DELETE',path,json={'reason':REASON},headers=headers).status_code==204
    with Session(engine) as session:
        assert session.get(Underlying,row['id']).active is False


def test_restart_preserves_catalog_moves_deactivations_and_even_an_empty_catalog(tmp_path,monkeypatch):
    monkeypatch.delenv('STRUCTURA_INSTALLATION_CONFIG',raising=False)
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE','simulation')
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD','1')
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(database,'_DB_PATH',tmp_path/'catalog.db')
    engine=create_engine(f'sqlite:///{tmp_path/"catalog.db"}')
    monkeypatch.setattr(database,'engine',engine)
    database.init_db()
    with Session(engine) as session:
        actor=User(username='catalog-admin',email='catalog@example.test',password_hash='fixture',role='admin',entity_id=1)
        session.add(actor);session.commit()
        item=session.exec(select(Underlying).where(Underlying.ticker=='BNP.PA')).first()
        admin.update_underlying(item.id,admin.UnderlyingUpdate(group='Desk local',active=False,reason=REASON),actor,session)
        count=len(session.exec(select(Underlying)).all())
        old_id=item.id
    engine.dispose()
    engine=create_engine(f'sqlite:///{tmp_path/"catalog.db"}')
    monkeypatch.setattr(database,'engine',engine)
    database.init_db()
    with Session(engine) as session:
        assert len(session.exec(select(Underlying)).all())==count
        item=session.get(Underlying,old_id)
        assert item.group_name=='Desk local' and not item.active
        for row in session.exec(select(Underlying)).all(): session.delete(row)
        session.commit()
    database.init_db()
    with Session(engine) as session:
        assert session.exec(select(Underlying)).all()==[]
        assert session.get(ReferenceCatalogState,'underlyings')
    engine.dispose()


def test_explicit_invalid_provider_link_never_falls_back_to_homonymous_bank():
    engine=create_engine('sqlite://');SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        inactive=Counterparty(id=1,name='Old',active=False)
        session.add_all([inactive,Counterparty(id=2,name='Bank'),RfqProvider(label='Bank',counterparty_id=1)])
        session.commit()
        assert provider_identity(session,'Bank')[1] is None
        assert 'Bank' not in rfq._counterparty_by_provider(session)
    engine.dispose()


@pytest.mark.parametrize('identity', [None,999,2])
def test_credit_control_never_silently_skips_unknown_or_inactive_identity(identity):
    engine=create_engine('sqlite://');SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Counterparty(id=2,name='Inactive',active=False));session.commit()
        with pytest.raises(HTTPException) as error:
            credit.enforce_booking(session,SimpleNamespace(id=1,entity_id=1),SimpleNamespace(counterparty_id=identity,contrepartie='Unknown '))
        assert error.value.status_code==422
    engine.dispose()


def test_legacy_quote_migration_never_invents_a_historical_identity(tmp_path,monkeypatch):
    from sqlalchemy import text
    from backend.app.db.models import RfqRequest
    engine=create_engine(f'sqlite:///{tmp_path/"legacy-quotes.db"}')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Counterparty(id=1,name='Bank'),RfqProvider(id=1,label='Bank',counterparty_id=1)])
        session.add(RfqRequest(id=1,user_id=1,reference='LEGACY',name='Archive',script_snapshot='AT MATURITY\n  PAY 1',params_json='{}'))
        session.add(RfqQuote(id=1,rfq_id=1,provider='Bank'))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE legacy_quotes AS SELECT id, rfq_id, provider, contact, price, currency, status, note, quoted_at, firmness, valid_until, created_at, last_look, parent_quote_id FROM rfq_quotes'))
        connection.execute(text('DROP TABLE rfq_quotes'))
        connection.execute(text('ALTER TABLE legacy_quotes RENAME TO rfq_quotes'))
    monkeypatch.setattr(database,'engine',engine)
    for _ in range(2):
        database._migrate()
        with Session(engine) as session:
            quote=session.get(RfqQuote,1)
            assert not quote.identity_frozen and quote.provider_id is None and quote.counterparty_id is None
            assert rfq._quote_row(quote,rfq._counterparty_by_provider(session))['identity_status']=='TO_QUALIFY'
    engine.dispose()
