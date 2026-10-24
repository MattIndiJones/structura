"""C02 acceptance with real HTTP authentication and isolated managed databases."""
import json
import pytest
from jose import jwt
from sqlmodel import Session, select

from backend.tests.test_hybrid_bootstrap import managed, login
from backend.app.api import auth, schedule
from backend.app.db.models import User, Entity, AuditEvent, RevokedSession


def user_id(engine, name="front"):
    with Session(engine) as session:
        return session.exec(select(User).where(User.username == name)).one().id


def test_logout_is_persistent_and_only_revokes_current_session(managed):
    config, engine, client, _ = managed
    first, second = login(client, config, "front"), login(client, config, "front")
    assert first != second
    assert client.post('/api/auth/logout', headers=first).status_code == 204
    assert client.get('/api/auth/me', headers=first).status_code == 401
    assert client.get('/api/auth/me', headers=second).status_code == 200
    with Session(engine) as session:
        row = session.exec(select(RevokedSession)).one()
        assert len(row.token_digest) == 64 and row.token_digest not in first['Authorization']
    assert client.post('/api/auth/logout-all', headers=second).status_code == 204
    assert client.get('/api/auth/me', headers=second).status_code == 401
    assert client.get('/api/auth/me', headers=login(client, config, "front")).status_code == 200


@pytest.mark.parametrize('change', [{'is_active': False}, {'role': 'checker'}])
def test_habilitation_change_and_reactivation_never_resurrect_old_tokens(managed, change):
    config, engine, client, _ = managed
    front, admin = login(client, config, "front"), login(client, config, "superuser")
    uid = user_id(engine)
    assert client.patch(f'/api/admin/users/{uid}', json=change, headers=admin).status_code == 200
    assert client.get('/api/auth/me', headers=front).status_code == 401
    assert client.patch(f'/api/admin/users/{uid}', json={'is_active': True, 'role': 'user'}, headers=admin).status_code == 200
    assert client.get('/api/auth/me', headers=front).status_code == 401
    fresh = login(client, config, "front")
    assert client.post(f'/api/admin/users/{uid}/revoke-sessions', headers=admin).status_code == 204
    assert client.get('/api/auth/me', headers=fresh).status_code == 401


def test_temporary_password_activation_personal_change_and_admin_reset(managed):
    config, engine, client, _ = managed
    admin = login(client, config, 'superuser')
    entity = client.get('/api/auth/me', headers=admin).json()['entity_id']
    payload = {'username': 'new-user', 'email': 'new@example.test', 'entity_id': entity, 'password': 'x'}
    assert client.post('/api/admin/users', json=payload, headers=admin).status_code == 422
    assert client.post('/api/admin/users', json={**payload, 'password': 'é'*37}, headers=admin).status_code == 422
    payload['password'] = 'Temporary-Password-2026'
    created = client.post('/api/admin/users', json=payload, headers=admin)
    assert created.status_code == 201 and created.json()['password_change_required']
    uid = created.json()['id']
    def password_login(password):
        response = client.post('/api/auth/login', data={'username': 'new-user', 'password': password})
        assert response.status_code == 200, response.text
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    temporary = password_login(payload['password'])
    assert client.get('/api/auth/me', headers=temporary).status_code == 200
    assert client.get('/api/rfq-desks', headers=temporary).status_code == 403
    body = {'current_password': 'wrong', 'new_password': 'Personal-Password-2026'}
    assert client.post('/api/auth/password', json=body, headers=temporary).status_code == 400
    assert client.post('/api/auth/password', json={**body, 'current_password': payload['password']}, headers=temporary).status_code == 204
    assert client.get('/api/auth/me', headers=temporary).status_code == 401
    fresh = password_login(body['new_password'])
    assert client.get('/api/auth/me', headers=fresh).json()['password_change_required'] is False
    assert client.post(f'/api/admin/users/{uid}/reset-password', json={'password': 'x'}, headers=admin).status_code == 422
    assert client.post(f'/api/admin/users/{uid}/reset-password', json={'password': 'Another-Temporary-2026'}, headers=admin).status_code == 204
    assert client.get('/api/auth/me', headers=fresh).status_code == 401
    reset = password_login('Another-Temporary-2026')
    assert client.get('/api/auth/me', headers=reset).json()['password_change_required']


def test_password_audit_correlates_success_failure_and_contains_no_secrets(managed):
    config, engine, client, _ = managed
    from backend.app.hybrid.config import credentials
    login(client, config, 'front')
    assert client.post('/api/auth/login', data={'username': 'front', 'password': 'incorrect-secret'}).status_code == 400
    assert client.post('/api/auth/login', data={'username': 'absent', 'password': 'other-secret'}).status_code == 400
    with Session(engine) as session:
        events = session.exec(select(AuditEvent).where(AuditEvent.action == 'LOGIN')).all()
        assert len(events) == 3
        assert [event.result for event in events] == ['SUCCESS', 'REJECTED', 'REJECTED']
        assert events[0].actor_user_id == events[1].actor_user_id == user_id(engine)
        assert events[2].actor_user_id is None
        assert all(e.correlation_id and e.created_at for e in events)
        metadata = [json.loads(e.metadata_json) for e in events]
        assert all(e['installation_id'] == str(config.installation_id) for e in metadata)
        serialized = repr([e.model_dump() for e in events])
        assert all(secret not in serialized for secret in ('incorrect-secret', 'other-secret', credentials(config)['front']))


def test_managed_organization_is_unique_and_name_locked(managed):
    config, engine, client, _ = managed
    admin = login(client, config, 'superuser')
    with Session(engine) as session:
        foreign = Entity(name='Foreign'); session.add(foreign); session.commit(); session.refresh(foreign)
        foreign_id = foreign.id
        foreign_user = User(username='foreign',email='foreign@example.test',password_hash='unused',entity_id=foreign.id)
        session.add(foreign_user); session.commit(); session.refresh(foreign_user)
        foreign_user_id=foreign_user.id
    entities = client.get('/api/admin/entities', headers=admin).json()
    assert len(entities) == 1 and entities[0]['name'] == config.name
    assert client.post('/api/admin/entities', json={'name': 'Second'}, headers=admin).status_code == 403
    path = f"/api/admin/entities/{entities[0]['id']}"
    assert client.patch(path, json={'name': 'Renamed'}, headers=admin).status_code == 403
    assert client.patch(path, json={'name': config.name}, headers=admin).status_code == 200
    assert client.patch(f'/api/admin/entities/{foreign_id}', json={'name': config.name}, headers=admin).status_code == 404
    for action in ('reset-password', 'revoke-sessions'):
        assert client.post(f'/api/admin/users/99999/{action}', headers=admin, json={'password':'Temporary-2026-Password'}).status_code == 404
        assert client.post(f'/api/admin/users/{foreign_user_id}/{action}', headers=admin, json={'password':'Temporary-2026-Password'}).status_code == 404


def test_pre_c02_token_requires_reauthentication(managed):
    config, engine, client, _ = managed
    headers = login(client, config, 'front')
    payload = jwt.get_unverified_claims(headers['Authorization'][7:])
    payload.pop('jti')
    old = jwt.encode(payload, auth._SECRET, algorithm='HS256')
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + old}).status_code == 401


def test_canonical_name_drift_requires_provisioning_without_implicit_repair(managed):
    from backend.app.hybrid.business import preflight
    config, engine, _, _ = managed
    with Session(engine) as session:
        entity=session.exec(select(Entity)).one()
        entity.name='Old local rename'; session.add(entity); session.commit()
    with pytest.raises(RuntimeError,match='Nom canonique'):
        preflight(engine,config)
    with Session(engine) as session:
        assert session.exec(select(Entity)).one().name=='Old local rename'


def test_normal_portal_cors_is_allowed_without_developer_access(managed, monkeypatch):
    from backend.app.hybrid.development import add_portal_cors, origins
    config, _, client, _ = managed
    monkeypatch.delenv('STRUCTURA_DEVELOPER_ACCESS', raising=False)
    # A fresh ASGI instance uses exactly the production CORS configuration.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides.update(client.app.dependency_overrides)
    add_portal_cors(app,config)
    origin = origins(config)[0]
    with TestClient(app) as browser:
        response = browser.options('/api/auth/login',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
        assert response.status_code==200 and response.headers['access-control-allow-origin']==origin
        response = browser.get('/api/auth/identity',headers={'Origin':origin})
        assert response.status_code==200 and response.headers['access-control-allow-origin']==origin
        response = browser.options('/api/auth/login',headers={'Origin':'https://foreign.example','Access-Control-Request-Method':'POST'})
        assert response.status_code==400 and 'access-control-allow-origin' not in response.headers


CALENDARS = [
    ('/api/schedule/generate', {'start_date':'2026-01-01','end_date':'2027-01-01','frequency':'3M'}),
    ('/api/calendar/resolve', {'date':'2026-01-01'}),
    ('/api/schedule/window', {'date':'2026-01-01','window_length':'1M','window_frequency':'1D'}),
    ('/api/schedule/period-window', {'start_date':'2026-01-01','end_date':'2029-01-01','roll_date':'2026-01-01','frequency':'1Y','window_frequency':'3M'}),
]


@pytest.mark.parametrize('path,body', CALENDARS)
def test_calendars_require_price_capability_and_allow_valid_previews(managed, path, body):
    config, _, client, _ = managed
    client.app.include_router(schedule.router)
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=login(client,config,'operations')).status_code == 403
    response = client.post(path, json=body, headers=login(client,config,'front'))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('path,body,generator', [
    (CALENDARS[0][0], {**CALENDARS[0][1], 'start_date':'0026-01-01'}, 'generate_schedule'),
    (CALENDARS[0][0], {**CALENDARS[0][1], 'roll_date':'1900-01-01'}, 'generate_schedule'),
    (CALENDARS[0][0], {**CALENDARS[0][1], 'end_date':'2050-01-01', 'frequency':'1D'}, 'generate_schedule'),
    (CALENDARS[1][0], {'date':'9999-12-31'}, 'adjust'),
    (CALENDARS[2][0], {**CALENDARS[2][1], 'window_length':'99999999Y'}, 'observation_window'),
    (CALENDARS[3][0], {**CALENDARS[3][1], 'end_date':'2046-01-01','frequency':'1M','window_frequency':'1D'}, 'period_windows'),
])
def test_calendar_budget_rejects_before_generator(managed, monkeypatch, path, body, generator):
    config, _, client, _ = managed
    client.app.include_router(schedule.router)
    def forbidden(*args, **kwargs):
        pytest.fail('Calendar generator called before budget rejection')
    monkeypatch.setattr(schedule, generator, forbidden)
    assert client.post(path, json=body, headers=login(client,config,'front')).status_code == 422
