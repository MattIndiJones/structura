"""Production/UAT boundaries and frozen historical classification, offline."""
import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import portfolios, shocks, var
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import (ComputeBatch, Deal, Entity, Portfolio, ShockRun,
                                   UatGenerationBatch, User)


@pytest.fixture
def case(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def foreign_keys(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        entity=Entity(name='Local');other_entity=Entity(name='Other')
        session.add_all([entity,other_entity]);session.commit()
        user=User(username='front',email='front@example.test',password_hash='x',role='user',entity_id=entity.id)
        colleague=User(username='colleague',email='colleague@example.test',password_hash='x',role='user',entity_id=entity.id)
        session.add_all([user,colleague]);session.commit()
        batch=UatGenerationBatch(batch_key='c27',label='C27',created_by=user.id,
            target_user_id=user.id,mode='BOOKED_ONLY',seed=27,requested_count=1)
        portfolio=Portfolio(name='Mixed membership',user_id=user.id,entity_id=entity.id)
        session.add_all([batch,portfolio]);session.commit()
        deals=[]
        for reference,uat,owner,entity_id in [('PROD',None,user.id,entity.id),('UAT',batch.id,user.id,entity.id),
                ('COLLEAGUE',None,colleague.id,entity.id),('FOREIGN',None,user.id,other_entity.id)]:
            deal=Deal(reference=reference,user_id=owner,entity_id=entity_id,uat_batch_id=uat,
                portfolio_id=portfolio.id,nominal=1e6,devise='EUR',sens='vente',status='actif',
                trade_date='2026-01-01',strike_date='2026-01-01',value_date='2026-01-01',T=5,
                underlyings_json='[]',script_snapshot='AT MATURITY:\n  PAY 1')
            session.add(deal);deals.append(deal)
        session.commit()
        app=FastAPI();app.include_router(portfolios.router);app.include_router(shocks.router);app.include_router(var.router)
        app.dependency_overrides[get_session]=lambda:session
        app.dependency_overrides[get_current_user]=lambda:user
        monkeypatch.setattr(portfolios,'_aggregate_exposure_by_counterparty',lambda ds,_:dict(nominal_total_eur=sum(d.nominal for d in ds)))
        monkeypatch.setattr(portfolios,'_aggregate_barriers',lambda ds,_:dict(rows=[dict(reference=d.reference) for d in ds]))
        monkeypatch.setattr(portfolios,'_run_explain_on_book',lambda ds,*a:dict(nominal_total_eur=sum(d.nominal for d in ds)))
        monkeypatch.setattr(shocks,'_run_shock_on_book',lambda ds,*a:dict(nominal_total_eur=sum(d.nominal for d in ds),contributions=[dict(deal_id=d.id) for d in ds]))
        monkeypatch.setattr(shocks,'_run_smile_on_book',lambda ds,*a:dict(nominal_total_eur=sum(d.nominal for d in ds),contributions=[dict(deal_id=d.id) for d in ds]))
        with TestClient(app) as client:
            yield client,session,user,portfolio,deals
    engine.dispose()


def test_default_exposure_excludes_uat_and_other_organization(case):
    client,*_=case
    response=client.get('/api/portfolios/exposure-by-counterparty')
    assert response.status_code==200
    assert response.json()['nominal_total_eur']==2e6


def test_explicit_uat_exposure_is_not_a_mixed_total(case):
    assert case[0].get('/api/portfolios/exposure-by-counterparty?data_scope=UAT').json()['nominal_total_eur']==1e6


def test_shock_persists_the_selected_scope_and_frozen_universe(case):
    client,session,_,_,deals=case
    result=client.post('/api/portfolios/shock-global',json={'data_scope':'UAT'})
    assert result.status_code==200
    data=result.json();assert data['nominal_total_eur']==1e6
    stored=session.get(ShockRun,data['run_id'])
    params=json.loads(stored.params_json)
    assert params['data_scope']=='UAT'
    assert [row['deal_id'] for row in params['requested_deals']]==[deals[1].id]


def test_legacy_shock_is_not_relabelled_production(case):
    client,session,user,_,_=case
    row=ShockRun(user_id=user.id,scope='global',label='old mixed study',params_json='{}',result_json='{"nominal_total_eur":2000000}')
    session.add(row);session.commit()
    assert client.get('/api/shocks?scope=global').json()==[]
    history=client.get('/api/shocks?scope=global&data_scope=LEGACY_UNQUALIFIED').json()
    assert [x['id'] for x in history]==[row.id]
    assert history[0]['data_scope']=='LEGACY_UNQUALIFIED'


@pytest.mark.parametrize('origin,nominal',[('PRODUCTION',2e6),('UAT',1e6)])
@pytest.mark.parametrize('kind',['shock','smile-risk','pnl-explain','exposure-by-counterparty','barriers'])
def test_all_portfolio_consumers_share_origin_and_c01_visibility(case,origin,nominal,kind):
    client,_,_,portfolio,_=case
    url=f'/api/portfolios/{portfolio.id}/{kind}?data_scope={origin}'
    if kind in {'shock','smile-risk'}:
        response=client.post(url,json={'data_scope':origin})
    elif kind=='pnl-explain':response=client.post(url,json={})
    else:response=client.get(url)
    assert response.status_code==200,response.text
    data=response.json()
    if kind=='barriers':assert len(data['rows'])==(2 if origin=='PRODUCTION' else 1)
    else:assert data['nominal_total_eur']==nominal
    assert data['data_scope']==origin
    assert sum(d['nominal'] for d in data['requested_deals'])==nominal


@pytest.mark.parametrize('url', ['/api/portfolios/shock-global','/api/portfolios/smile-risk-global'])
def test_global_calculations_use_the_visible_collective_book(case,url):
    response=case[0].post(url,json={})
    assert response.status_code==200
    assert response.json()['nominal_total_eur']==2e6


def test_membership_badges_follow_selected_origin(case):
    client,_,_,portfolio,_=case
    for origin,count in [('PRODUCTION',2),('UAT',1)]:
        row=next(r for r in client.get(f'/api/portfolios?data_scope={origin}').json() if r['id']==portfolio.id)
        assert row['deal_count']==count and row['data_scope']==origin


def test_history_filters_before_limiting_and_never_reclassifies_from_live_deals(case):
    client,session,user,portfolio,deals=case
    prod=client.post('/api/portfolios/shock-global',json={}).json()
    uat=client.post('/api/portfolios/shock-global',json={'data_scope':'UAT'}).json()
    run=session.get(ShockRun,uat['run_id']);frozen=(run.params_json,run.result_json)
    # Simulate later provenance/membership changes: the archive owns its original universe.
    deals[1].uat_batch_id=None;deals[1].portfolio_id=None;session.add(deals[1]);session.commit()
    listed=client.get('/api/shocks?scope=global&limit=1').json()
    assert [r['id'] for r in listed]==[prod['run_id']]
    assert [r['id'] for r in client.get('/api/shocks?scope=global&data_scope=UAT').json()]==[uat['run_id']]
    assert (session.get(ShockRun,run.id).params_json,session.get(ShockRun,run.id).result_json)==frozen


def test_unknown_origin_is_rejected_for_reads_and_new_studies(case):
    client,*_=case
    assert client.post('/api/portfolios/shock-global',json={'data_scope':'MIXED'}).status_code==422
    assert client.post('/api/portfolios/smile-risk-global',json={'data_scope':'LEGACY_UNQUALIFIED'}).status_code==422
    assert client.get('/api/portfolios/barriers-global?data_scope=MIXED').status_code==422


def test_explicit_deal_shock_uses_its_origin_and_refuses_a_conflicting_body(case,monkeypatch):
    client,session,_,_,deals=case
    monkeypatch.setattr(shocks,'_run_shock_on_deal',lambda d,*a:dict(deal_id=d.id,delta_eur=0))
    response=client.post(f'/api/deals/{deals[1].id}/shock',json={})
    assert response.status_code==200
    assert response.json()['data_scope']=='UAT'
    assert client.post(f'/api/deals/{deals[1].id}/shock',json={'data_scope':'PRODUCTION'}).status_code==422


def test_var_history_is_frozen_per_origin_and_portfolio_and_keeps_legacy_separate(case):
    client,session,user,portfolio,_=case
    items=[('PRODUCTION','global',None),('UAT','global',None),('PRODUCTION','portfolio',portfolio.id)]
    rows=[]
    for origin,scope,pid in items:
        row=ComputeBatch(user_id=user.id,kind='var_scenario',label=origin+scope,
            params_json=json.dumps(dict(data_scope=origin,scope=scope,portfolio_id=pid)),status='queued')
        session.add(row);rows.append(row)
    legacy=ComputeBatch(user_id=user.id,kind='var_scenario',label='old mixed',params_json='{}',status='queued')
    c21=ComputeBatch(user_id=user.id,kind='var_scenario',label='C21 unknown portfolio',params_json='{"data_scope":"PRODUCTION"}',status='queued')
    session.add_all([legacy,c21]);session.commit()
    assert [r['id'] for r in client.get('/api/portfolios/var-history').json()]==[rows[0].id]
    assert [r['id'] for r in client.get('/api/portfolios/var-history?data_scope=UAT').json()]==[rows[1].id]
    assert [r['id'] for r in client.get(f'/api/portfolios/var-history?scope=portfolio&portfolio_id={portfolio.id}').json()]==[rows[2].id]
    assert {r['id'] for r in client.get('/api/portfolios/var-history?data_scope=LEGACY_UNQUALIFIED').json()}=={legacy.id,c21.id}
    result=client.get(f'/api/portfolios/var/{legacy.id}').json()
    assert result['data_scope']=='LEGACY_UNQUALIFIED' and result['params']=={}


def test_other_users_var_and_shock_histories_remain_private(case):
    client,session,_,_,deals=case
    other=deals[2].user_id
    batch=ComputeBatch(user_id=other,kind='var_scenario',label='private',params_json='{}',status='queued')
    shock=ShockRun(user_id=other,scope='global',label='private',params_json='{}',result_json='{}')
    session.add_all([batch,shock]);session.commit()
    assert client.get('/api/shocks?data_scope=LEGACY_UNQUALIFIED').json()==[]
    assert client.get('/api/portfolios/var-history?data_scope=LEGACY_UNQUALIFIED').json()==[]
    assert client.get(f'/api/portfolios/var/{batch.id}').status_code==404


@pytest.mark.parametrize('origin,expected',[('PRODUCTION',2),('UAT',1)])
def test_var_creation_freezes_origin_and_view_without_reusing_a_current_book_later(case,monkeypatch,origin,expected):
    client,session,_,portfolio,_=case
    # Exercise actual enqueue + scope metadata while keeping the quantitative preflight offline.
    monkeypatch.setattr(var,'build_deal_scenario_base',lambda d,*a:dict(skipped=True,reason='test preflight exclusion'))
    response=client.post(f'/api/portfolios/{portfolio.id}/var',json={'data_scope':origin})
    assert response.status_code==202,response.text
    stored=session.get(ComputeBatch,response.json()['batch_id'])
    params=json.loads(stored.params_json)
    assert params['data_scope']==origin and params['scope']=='portfolio' and params['portfolio_id']==portfolio.id
    assert len(params['requested_deals'])==expected
    assert client.get(f'/api/portfolios/var-history?scope=portfolio&portfolio_id={portfolio.id}&data_scope={origin}').json()[0]['id']==stored.id


def test_deleted_portfolio_archives_keep_their_frozen_view_and_are_still_browsable(case,monkeypatch):
    client,session,user,portfolio,_=case
    result=client.post(f'/api/portfolios/{portfolio.id}/shock',json={}).json()
    shock=session.get(ShockRun,result['run_id'])
    shock_bytes=(shock.params_json,shock.result_json)
    batch=ComputeBatch(user_id=user.id,kind='var_scenario',label='VaR — archived book',
        status='queued',params_json=json.dumps(dict(data_scope='PRODUCTION',scope='portfolio',portfolio_id=portfolio.id)))
    session.add(batch);session.commit()
    pid=portfolio.id
    assert client.delete(f'/api/portfolios/{pid}').status_code==204
    session.expire_all()
    assert session.get(ShockRun,shock.id).portfolio_id is None
    assert (session.get(ShockRun,shock.id).params_json,session.get(ShockRun,shock.id).result_json)==shock_bytes
    history=client.get('/api/shocks?scope=global&all_views=true').json()
    assert history[0]['portfolio_id']==pid
    assert history[0]['params']['portfolio_name']=='Mixed membership'
    assert client.get('/api/portfolios/var-history?all_views=true').json()[0]['id']==batch.id


def test_one_million_production_and_one_million_uat_never_make_a_two_million_default(case):
    client,session,_,_,deals=case
    deals[2].status='annulé';session.add(deals[2]);session.commit()
    for origin in ['PRODUCTION','UAT']:
        exposure=client.get(f'/api/portfolios/exposure-by-counterparty?data_scope={origin}').json()
        shock=client.post('/api/portfolios/shock-global',json={'data_scope':origin}).json()
        assert exposure['nominal_total_eur']==1e6
        assert shock['nominal_total_eur']==1e6
        assert len(shock['requested_deals'])==1
