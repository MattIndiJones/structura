"""Read-only native book viewers; every fixture lives in a temporary directory."""
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import agent_workshop
from backend.app.api.auth import get_current_user
from backend.app.db.models import Deal, Entity, User
from backend.app.services.agent_workshop import consultation, engine
from backend.app.services.agent_workshop.consultation import Consultations
from backend.app.services.agent_workshop.engine import Manager
from backend.app.services.agent_workshop.lease import CampaignLease
from backend.app.services.agent_workshop.store import Store, CampaignConfig


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = Store(tmp_path / 'campaigns')
    viewer = Consultations()
    manager = Manager()
    monkeypatch.setattr(consultation, 'store', store)
    monkeypatch.setattr(consultation, 'consultations', viewer)
    monkeypatch.setattr(engine, 'store', store)
    monkeypatch.setattr(agent_workshop, 'store', store)
    monkeypatch.setattr(agent_workshop, 'manager', manager)
    monkeypatch.setattr(agent_workshop, 'consultations', viewer)
    monkeypatch.delenv('STRUCTURA_WORKSHOP_CHILD', raising=False)
    state = store.create(CampaignConfig(months=1), 3)
    state.update(status='STOPPED', turns=42, month=1)
    state['actors']['hector']['registered'] = True
    store.save(state)
    app = FastAPI(); app.include_router(agent_workshop.router)
    identity = SimpleNamespace(id=3, role='admin')
    app.dependency_overrides[get_current_user] = lambda: identity
    with TestClient(app) as client:
        yield store, viewer, manager, state, client, identity
    viewer.shutdown()


def test_permissions_actor_boundary_and_missing_book(setup, monkeypatch):
    store, _, _, state, client, identity = setup
    path = f"/api/agent-workshop/{state['id']}/consultations/hector"
    identity.role = 'user'
    assert client.post(path).status_code == client.delete(path).status_code == 403
    identity.role = 'admin'
    identity.id = 4
    assert client.post(path).status_code == 404
    assert client.delete(path).status_code == 404
    identity.id = 3
    assert client.post(path).status_code == 409
    assert client.post(path.replace('hector', 'achille')).status_code == 422
    assert client.post(path.replace('hector', 'bnp')).status_code == 409
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD', '1')
    assert client.post(path).status_code == client.delete(path).status_code == 403
    assert store.load(state['id'])['turns'] == 42


@pytest.mark.parametrize('status', ['DRAFT', 'RUNNING', 'PAUSED', 'PAUSING', 'STOPPING'])
def test_viewer_never_opens_for_an_active_or_unprepared_campaign(setup, status):
    store, _, _, state, client, _ = setup
    state['status'] = status; store.save(state)
    response = client.post(f"/api/agent-workshop/{state['id']}/consultations/hector")
    assert response.status_code == 409
    assert not (store.path(state['id'])/'consultations').exists()


def test_external_controller_lease_blocks_consultation(setup):
    store, _, _, state, client, _ = setup
    lease = CampaignLease(store.path(state['id']))
    try:
        assert client.post(f"/api/agent-workshop/{state['id']}/consultations/hector").status_code == 409
    finally:
        lease.close()


def test_live_viewer_blocks_ai_restart_and_retirement(setup, monkeypatch):
    _, viewer, manager, state, _, _ = setup
    monkeypatch.setattr(viewer, 'active', lambda key: key == state['id'])
    with pytest.raises(ValueError, match='consultations'):
        manager.start(state['id'])
    for action in ['reset', 'delete', 'replay']:
        with pytest.raises(ValueError, match='consultations'):
            manager.manage(state['id'], 3, action)
    assert manager.thread is None


def test_other_instance_identity_is_never_closed(setup, monkeypatch):
    store, viewer, _, state, _, _ = setup
    directory = viewer._path(state['id'], 'hector'); directory.mkdir(parents=True)
    record = {'actor':'hector','identity':'owned','url':'http://127.0.0.1:1234','token':'secret'}
    (directory/'instance_control.json').write_text(json.dumps(record), encoding='utf-8')
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url):
            return httpx.Response(200, json={'instance_id':'unrelated','read_only':True}, request=httpx.Request('GET',url))
        def post(self, *args, **kwargs):
            raise AssertionError('An unrelated server must never be stopped')
    monkeypatch.setattr(consultation.httpx, 'Client', Client)
    assert viewer.close(state['id'], 3, 'hector')['closed']


def test_consultation_lease_blocks_restart_even_without_http_health(setup, monkeypatch):
    _, viewer, manager, state, _, _ = setup
    directory=viewer._path(state['id'],'hector'); directory.mkdir(parents=True)
    lease=CampaignLease(directory)
    try:
        monkeypatch.setattr(viewer,'status',lambda key:{})
        assert viewer.active(state['id'])
        with pytest.raises(ValueError,match='consultations'):
            manager.start(state['id'])
    finally:
        lease.close()
    assert not viewer.active(state['id'])


def test_native_viewer_preserves_books_campaign_and_reuses_its_process(setup):
    store, viewer, _, state, client, _ = setup
    state['actors']['hector']['entity'] = 'Maison Hector'
    store.save(state)
    directory = store.path(state['id']) / 'instances/hector'; directory.mkdir(parents=True)
    database = directory/'structura.db'
    native = create_engine(f'sqlite:///{database}')
    SQLModel.metadata.create_all(native)
    with Session(native) as session:
        entity=Entity(id=2,name='Maison Hector'); session.add(entity)
        session.add(User(id=3,username='agent_hector',email='hector@recette.invalid',password_hash='unused',role='admin',entity_id=2))
        session.add(Deal(id=1,user_id=3,entity_id=2,reference='CONSULT-001',contrepartie='BNP Paribas',nominal=10_000_000,
                         devise='EUR',strike_date='2025-10-13',value_date='2025-10-13',maturity_date='2026-04-13',
                         payment_date='2026-04-16',script_snapshot='AT MATURITYDATE:\n    PAY 1',market_snapshot_json='{}'))
        session.commit()
    native.dispose()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    saved = (store.path(state['id'])/'campaign.json').read_bytes()
    path = f"/api/agent-workshop/{state['id']}/consultations/hector"
    try:
        opened = client.post(path)
        assert opened.status_code == 200, opened.text
        data = opened.json()
        assert data['read_only'] and '#/consultation?token=' in data['launch_url']
        from urllib.parse import parse_qs, urlsplit
        token = parse_qs(urlsplit(data['launch_url']).fragment.split('?',1)[1])['token'][0]
        with httpx.Client(base_url=data['url'], headers={'Authorization':'Bearer '+token}, trust_env=False, timeout=10) as api:
            me = api.get('/api/auth/me').json()
            assert me['read_only'] is True and me['consultation']['entity']=='Maison Hector'
            deals = api.get('/api/deals')
            assert deals.status_code==200, deals.text
            assert len(deals.json())==1 and deals.json()[0]['reference']=='CONSULT-001'
            for method, route in [('POST','/api/deals'),('DELETE','/api/deals/1'),('PATCH','/api/deals/1'),
                                  ('POST','/api/deals/1/mtm'),('POST','/api/alerts/refresh-book'),('POST','/api/auth/register')]:
                assert api.request(method,route,json={}).status_code==403
            assert api.post('/_instance/consultation-session').status_code==404
            assert api.post('/api/auth/logout-all').status_code==204
            assert api.get('/api/auth/me').status_code==401
        first_pid=viewer.children[(state['id'],'hector')][0].pid
        assert client.post(path).json()['url']==data['url']
        assert viewer.children[(state['id'],'hector')][0].pid==first_pid
        public=client.get(f"/api/agent-workshop/{state['id']}").json()
        assert public['status']=='STOPPED' and public['turns']==42
        assert public['consultations']['hector']['online']
        assert 'token' not in public['consultations']['hector']
        assert client.post(f"/api/agent-workshop/{state['id']}/start").status_code==409
        assert client.delete(f"/api/agent-workshop/{state['id']}").status_code==409
        assert client.delete(path).status_code==200
        with httpx.Client(timeout=1, trust_env=False) as probe:
            with pytest.raises(httpx.HTTPError): probe.get(data['url']+'/health')
    finally:
        viewer.shutdown()
    program = """
from backend.app.db.database import engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
try:
    with engine.begin() as connection:
        connection.execute(text('UPDATE deals SET nominal=1'))
except OperationalError as error:
    assert 'readonly' in str(error).lower(), str(error)
else:
    raise AssertionError('SQLite must reject writes even without HTTP middleware')
"""
    check = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True,
                           env={**os.environ, 'STRUCTURA_DATA_DIR':str(directory), 'STRUCTURA_CONSULTATION':'1'})
    assert check.returncode==0, check.stderr
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    assert (store.path(state['id'])/'campaign.json').read_bytes()==saved
    assert store.load(state['id'])['usage']['model_calls']==0
