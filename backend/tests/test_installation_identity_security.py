"""C02 central sessions and pre-migration Admin workspace identity checks."""
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.hybrid.deployment import prepare
from backend.app.hybrid.control_services import prepare_controls
from backend.app.hybrid.config import credentials
from backend.app.hybrid.platform import create_app, initialize
from backend.app.hybrid import admin_workbench
from backend.app.db import database
from backend.app.db.models import Entity, User


def test_password_portal_directory_and_central_session_revocation_without_developer_mode(tmp_path, monkeypatch):
    config = prepare(tmp_path/'hybrid')[0]
    monkeypatch.setenv('STRUCTURA_INSTALLATION_CONFIG', str(config.data_dir/'installation.json'))
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(config.data_dir))
    monkeypatch.delenv('STRUCTURA_DEVELOPER_ACCESS', raising=False)
    with TestClient(create_app()) as client:
        def login(password=None):
            response = client.post('/api/auth/login', data={'username':'admin','password':password or credentials(config)['admin']})
            assert response.status_code == 200, response.text
            return {'Authorization':'Bearer '+response.json()['access_token']}
        assert client.get('/api/auth/options').json()['installation_portal']
        directory = client.get('/api/platform/login-options').json()
        assert len(directory['installations']) == 7
        assert all(set(row) == {'installation_id','organization_id','kind','name','key','url'} for row in directory['installations'])
        assert client.get('/api/platform/development/access').json() == {'enabled':False,'installations':[]}
        assert client.get('/api/platform/installations').status_code == 401
        assert client.get('/api/auth/identity').json()['installation']['installation_id'] == str(config.installation_id)
        first, second = login(), login()
        assert client.post('/api/auth/logout',headers=first).status_code == 204
        assert client.get('/api/auth/me',headers=first).status_code == 401
        assert client.get('/api/auth/me',headers=second).status_code == 200
        # Revocations survive initialization/restart.
        initialize(config)
        assert client.get('/api/auth/me',headers=first).status_code == 401
        assert client.post('/api/auth/logout-all',headers=second).status_code == 204
        assert client.get('/api/auth/me',headers=second).status_code == 401
        fresh = login()
        body = {'current_password': credentials(config)['admin'], 'new_password':'Central-New-Password-2026'}
        assert client.post('/api/auth/password',json={**body,'new_password':'x'},headers=fresh).status_code == 422
        assert client.post('/api/auth/password',json=body,headers=fresh).status_code == 204
        assert client.get('/api/auth/me',headers=fresh).status_code == 401
        assert client.get('/api/auth/me',headers=login(body['new_password'])).status_code == 200


@pytest.mark.parametrize('contents', ['business','unmarked-admin','foreign-marker'])
def test_admin_preflight_rejects_foreign_or_unmarked_db_before_any_migration(tmp_path, monkeypatch, contents):
    config = prepare_controls(prepare(tmp_path/'hybrid')[0])['admin-workbench']
    path = config.data_dir/'structura.db'
    with sqlite3.connect(path) as connection:
        if contents == 'foreign-marker':
            connection.execute('CREATE TABLE admin_workbench_identity(id INTEGER PRIMARY KEY, installation_id TEXT, entity_id INTEGER)')
            connection.execute("INSERT INTO admin_workbench_identity VALUES(1,'foreign',1)")
        else:
            connection.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)')
            connection.execute('INSERT INTO users VALUES(1,?)', ('admin' if contents=='unmarked-admin' else 'client-user',))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    engine = create_engine(f'sqlite:///{path}')
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'_DB_PATH',path)
    monkeypatch.delenv('STRUCTURA_INSTALLATION_CONFIG',raising=False)
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE','admin_workbench')
    monkeypatch.setenv('STRUCTURA_ADMIN_WORKBENCH_CONFIG',str(config.data_dir/'installation.json'))
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(config.data_dir))
    with pytest.raises(RuntimeError):
        database.init_db()
    engine.dispose()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_marked_admin_workspace_starts_idempotently_and_retains_revocations(tmp_path, monkeypatch):
    config = prepare_controls(prepare(tmp_path/'hybrid')[0])['admin-workbench']
    monkeypatch.delenv('STRUCTURA_INSTALLATION_CONFIG',raising=False)
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE','admin_workbench')
    monkeypatch.setenv('STRUCTURA_ADMIN_WORKBENCH_CONFIG',str(config.data_dir/'installation.json'))
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(config.data_dir))
    engine = create_engine(f'sqlite:///{config.data_dir / "structura.db"}')
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'_DB_PATH',config.data_dir / 'structura.db')
    database.init_db()
    with Session(engine) as session:
        marker = session.get(admin_workbench.AdminWorkbenchIdentity,1)
        assert marker.installation_id == str(config.installation_id)
        user = session.exec(select(User).where(User.username=='admin')).one()
        user.auth_version=4; user.is_active=False; session.add(user); session.commit()
    database.init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username=='admin')).one()
        assert user.auth_version==4 and not user.is_active
    engine.dispose()


def test_central_foreign_identity_is_refused_without_schema_changes(tmp_path):
    config = prepare(tmp_path/'hybrid')[0]
    path = config.data_dir/'platform.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE platform_identity(id INTEGER PRIMARY KEY, installation_id TEXT)')
        connection.execute("INSERT INTO platform_identity VALUES(1,'foreign')")
    before = path.read_bytes()
    with pytest.raises(RuntimeError): initialize(config)
    assert path.read_bytes() == before


def test_additive_session_migration_preserves_accounts_and_is_repeatable(tmp_path, monkeypatch):
    from sqlalchemy import text
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Entity(id=1,name='Legacy'))
        session.add(User(id=1,username='legacy',email='legacy@example.test',password_hash='unchanged-hash',entity_id=1))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE users DROP COLUMN auth_version'))
        connection.execute(text('ALTER TABLE users DROP COLUMN password_change_required'))
    monkeypatch.setattr(database,'engine',engine)
    for _ in range(2):
        database._migrate()
        with Session(engine) as session:
            user=session.get(User,1)
            assert user.password_hash=='unchanged-hash' and user.entity_id==1 and user.auth_version==0
            assert user.password_change_required is False
    engine.dispose()


def test_legacy_read_only_book_uses_separate_revocation_and_audit_store(tmp_path, monkeypatch):
    import bcrypt
    from sqlalchemy import text
    from fastapi import FastAPI
    from backend.app.api import auth
    from backend.app.db.database import get_session
    path=tmp_path/'archive.db'
    engine=create_engine(f'sqlite:///{path}')
    SQLModel.metadata.create_all(engine)
    password='Read-Only-Password-2026'
    with Session(engine) as session:
        session.add(Entity(id=1,name='Archived'))
        session.add(User(id=1,username='archived',email='archive@example.test',password_hash=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),entity_id=1))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE users DROP COLUMN auth_version'))
        connection.execute(text('ALTER TABLE users DROP COLUMN password_change_required'))
        connection.execute(text('DROP TABLE revoked_sessions'))
    engine.dispose()
    before=path.read_bytes()
    lock_dir=tmp_path/'viewer'; lock_dir.mkdir()
    monkeypatch.setenv('STRUCTURA_CONSULTATION','1')
    monkeypatch.setenv('STRUCTURA_CONSULTATION_LOCK_DIR',str(lock_dir))
    monkeypatch.delenv('STRUCTURA_INSTALLATION_CONFIG',raising=False)
    readonly=create_engine(f'sqlite:///{path.as_uri()}?mode=ro&uri=true',connect_args={'check_same_thread':False})
    app=FastAPI(); app.include_router(auth.router)
    def sessions():
        with Session(readonly) as session: yield session
    app.dependency_overrides[get_session]=sessions
    with TestClient(app) as client:
        def login():
            response=client.post('/api/auth/login',data={'username':'archived','password':password})
            assert response.status_code==200,response.text
            return {'Authorization':'Bearer '+response.json()['access_token']}
        first,second=login(),login()
        assert client.get('/api/auth/me',headers=first).json()['read_only']
        assert client.post('/api/auth/logout',headers=first).status_code==204
        assert client.get('/api/auth/me',headers=first).status_code==401
        assert client.get('/api/auth/me',headers=second).status_code==200
        assert client.post('/api/auth/logout-all',headers=second).status_code==204
        assert client.get('/api/auth/me',headers=second).status_code==401
        assert client.get('/api/auth/me',headers=login()).status_code==200
        assert client.post('/api/auth/password',headers=login(),json={'current_password':password,'new_password':'Another-Password-2026'}).status_code==403
    readonly.dispose()
    assert path.read_bytes()==before
    with sqlite3.connect(lock_dir/'sessions.db') as connection:
        assert connection.execute('SELECT count(*) FROM audit').fetchone()[0]>=4
