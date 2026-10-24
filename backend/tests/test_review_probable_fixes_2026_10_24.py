"""Isolated evidence for KID provenance, document budgets and bootstrap retirement."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import kid, documents
from backend.app.core import document_uploads as uploads
from backend.app.db import database
from backend.app.db.models import KidRecord, Document, Entity, User, ProductRecord
from backend.app.services.kid_receipts import bind_kid_receipt
from backend.app.services.product_repository import load_product
from backend.tests.test_products import product_client, _create, _pricing_input


def kid_input():
    return _pricing_input(script='AT MATURITY:\n  PAY 1', T=round(91/365.25, 6), N=1000,
        strike_date='2026-01-05', value_date='2026-01-05', anchor='2026-01-05',
        maturity_date='2026-04-06', payment_date='2026-04-06')


def compute_and_save_body(client, *, linked=True):
    request = kid_input()
    product = _create(client, key='kid-evidence', pricing_input=request)
    if linked:
        request.update(product_id=product['product_id'], product_terms_version=product['terms_version'])
    response = client.post('/api/kid/compute', json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    return product, {**{k: data[k] for k in ('sri','mrm','crm','vev','T_rhp','horizons','costs','calculation_receipt')},
        'product_id': product['product_id'], 'product_terms_version': product['terms_version'], 'product_title': 'Titre éditorial'}


@pytest.mark.parametrize('linked', [True, False])
def test_kid_retains_real_computation_and_contract_without_recomputing(product_client, monkeypatch, linked):
    product, body = compute_and_save_body(product_client, linked=linked)
    def forbidden(*args, **kwargs):
        raise AssertionError('Saving evidence must not start another calculation')
    monkeypatch.setattr(kid, 'run_valuation', forbidden)
    response = product_client.post('/api/kid/save', json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['provenance_status'] == 'SERVER_COMPUTED'
    assert row['methodology_status'] == 'INDICATIVE_NON_PRIIPS'
    assert row['horizons'] == body['horizons']
    assert row['calculation_evidence']['retained_product_id'] == product['product_id']
    assert row['calculation_evidence']['input']['r'] == .03
    assert row['calculation_evidence']['calculation_identity']['kid_implementation_sha256']
    rows = product_client.get('/api/kid/records', params={'product_id':product['product_id']}).json()
    assert rows[0]['provenance_status'] == 'SERVER_COMPUTED'


@pytest.mark.parametrize('mutation', ['missing','sri','scenario','costs','signature','input','identity','signed_result'])
def test_kid_refuses_unsigned_or_modified_values_atomically(product_client, mutation):
    product, body = compute_and_save_body(product_client)
    revision = product_client.session.get(ProductRecord, product['product_id']).revision
    if mutation == 'missing':
        body.pop('calculation_receipt')
    elif mutation == 'sri':
        body['sri'] = 7
    elif mutation == 'scenario':
        body['horizons'][0]['modere']['amount'] += 1
    elif mutation == 'costs':
        body['costs']['ongoing'] += .5
    elif mutation == 'signature':
        body['calculation_receipt']['server_signature'] = '0' * 64
    elif mutation == 'input':
        body['calculation_receipt']['input']['r'] = .2
    elif mutation == 'identity':
        body['calculation_receipt']['calculation_identity']['kid_implementation_sha256'] = 'changed'
    else:
        body['calculation_receipt']['result']['sri'] = 7
    response = product_client.post('/api/kid/save', json=body)
    assert response.status_code == 422, response.text
    assert product_client.session.exec(select(KidRecord)).all() == []
    assert product_client.session.get(ProductRecord, product['product_id']).revision == revision


@pytest.mark.parametrize('foreign_user', [False, True])
def test_kid_receipt_cannot_be_transferred_to_another_product_or_user(product_client, foreign_user):
    _, body = compute_and_save_body(product_client)
    if foreign_user:
        product_client.current['user'] = product_client.users['bob']
    other = _create(product_client, key='other-product', pricing_input=kid_input())
    body.update(product_id=other['product_id'], product_terms_version=other['terms_version'])
    response = product_client.post('/api/kid/save', json=body)
    assert response.status_code == 422, response.text
    assert product_client.session.exec(select(KidRecord)).all() == []


def test_legacy_kid_is_unverified_and_altered_retained_values_are_detected(product_client):
    product, body = compute_and_save_body(product_client)
    saved = product_client.post('/api/kid/save', json=body).json()
    row = product_client.session.get(KidRecord, saved['id'])
    row.sri = 7
    assert kid._kid_record_row(row)['provenance_status'] == 'INVALID_EVIDENCE'
    product_client.session.rollback()
    legacy = KidRecord(user_id=1, product_id=product['product_id'], sri=4, mrm=4, crm=2)
    assert kid._kid_record_row(legacy)['provenance_status'] == 'LEGACY_UNVERIFIED'


@pytest.mark.parametrize('change', ['version','terms'])
def test_kid_evidence_rejects_stale_contract_even_when_client_changes_metadata(product_client, change):
    product, body = compute_and_save_body(product_client, linked=change == 'version')
    current = load_product(product_client.session, product['product_id'])
    if change == 'version':
        current = current.model_copy(update={'terms_version': current.terms_version + 1})
    else:
        current = current.model_copy(update={'terms': current.terms.model_copy(update={'T': .4})})
    with pytest.raises(ValueError, match='version|termes'):
        bind_kid_receipt(body['calculation_receipt'], body, product_client.current['user'], current)


def test_kid_evidence_survives_browser_number_serialization(product_client):
    _, body = compute_and_save_body(product_client)
    def browser(value):
        if isinstance(value,dict):
            return {k:browser(v) for k,v in value.items()}
        if isinstance(value,list):
            return [browser(v) for v in value]
        return int(value) if isinstance(value,float) and value.is_integer() else value
    response = product_client.post('/api/kid/save',json=browser(body))
    assert response.status_code == 201, response.text
    assert response.json()['provenance_status'] == 'SERVER_COMPUTED'


def test_kid_revision_failure_does_not_retain_an_orphan_record(product_client, monkeypatch):
    _, body = compute_and_save_body(product_client)
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic KID revision failure')
    monkeypatch.setattr(kid,'stage_revision',fail)
    with pytest.raises(RuntimeError,match='Synthetic KID'):
        product_client.post('/api/kid/save',json=body)
    assert product_client.session.exec(select(KidRecord)).all() == []


def test_kid_evidence_migration_is_additive_idempotent_and_preserves_links():
    engine = create_engine('sqlite://')
    with engine.connect() as conn:
        conn.execute(text('''CREATE TABLE kid_records (
            id INTEGER PRIMARY KEY, indicative_id INTEGER, deal_id INTEGER, user_id INTEGER NOT NULL,
            product_title TEXT NOT NULL, sri INTEGER NOT NULL,mrm INTEGER NOT NULL,crm INTEGER NOT NULL,
            vev FLOAT NOT NULL,t_rhp FLOAT NOT NULL,horizons_json TEXT,costs_json TEXT,created_at TEXT NOT NULL,
            product_id INTEGER,product_terms_version INTEGER)'''))
        conn.execute(text("INSERT INTO kid_records VALUES(1,NULL,NULL,1,'legacy',4,4,2,12.,1.,'[]','{}','2026-01-01',42,3)"))
        conn.execute(text('CREATE INDEX legacy_kid_user_idx ON kid_records(user_id)'))
        conn.execute(text("""CREATE TRIGGER require_kid_records_product_insert BEFORE INSERT ON kid_records
            WHEN NEW.product_id IS NULL BEGIN SELECT RAISE(ABORT, 'Product canonique requis'); END"""))
        conn.commit()
        database._make_kid_vev_nullable(conn)
        database._migrate_kid_evidence(conn)
        database._migrate_kid_evidence(conn)
        row = conn.execute(text('SELECT product_id,product_terms_version,vev,calculation_evidence_json FROM kid_records')).one()
        assert tuple(row) == (42,3,12.,'{}')
        assert any(r[3] == 'product_id' and r[2] == 'products' for r in conn.execute(text('PRAGMA foreign_key_list(kid_records)')))
        assert conn.execute(text("SELECT 1 FROM sqlite_master WHERE name='legacy_kid_user_idx'")).first()
        with pytest.raises(IntegrityError, match='Product canonique requis'):
            conn.execute(text("INSERT INTO kid_records(id,user_id,product_title,sri,mrm,crm,t_rhp,created_at) VALUES(2,1,'x',4,4,2,1.,'2026-01-01')"))
        conn.execute(text('UPDATE kid_records SET vev=NULL WHERE id=1'))
        conn.commit()
    engine.dispose()


@pytest.mark.parametrize('size', [8, 9])
def test_document_limit_preserves_bytes_or_leaves_no_file_or_db_row(product_client, monkeypatch, size):
    monkeypatch.setattr(uploads, 'MAX_DOCUMENT_BYTES', 8)
    product = _create(product_client, key='upload-product')
    revision = product_client.session.get(ProductRecord, product['product_id']).revision
    content = b'x' * size
    response = product_client.post('/api/documents', params={'title':'Pièce','product_id':product['product_id']},
                                   files={'file':('proof.pdf', content, 'application/pdf')})
    if size == 8:
        assert response.status_code == 201, response.text
        assert product_client.get(f"/api/documents/{response.json()['id']}/download").content == content
    else:
        assert response.status_code == 413, response.text
        assert product_client.session.exec(select(Document)).all() == []
        assert not list(documents._DOCS_DIR.rglob('*.pdf'))
        assert product_client.session.get(ProductRecord, product['product_id']).revision == revision


@pytest.mark.parametrize('failure', ['overflow','read_error','collision'])
def test_bounded_copy_checks_actual_bytes_and_cleans_only_its_own_file(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(uploads, 'MAX_DOCUMENT_BYTES', 8)
    destination = tmp_path/'proof.pdf'
    class Source:
        size = None
        reads = 0
        async def read(self, size=-1):
            assert 0 < size <= uploads.UPLOAD_CHUNK_BYTES
            self.reads += 1
            if self.reads == 1:
                return b'12345678'
            if failure == 'read_error':
                raise OSError('Synthetic stream failure')
            return b'9' if self.reads == 2 else b''
    if failure == 'collision':
        destination.write_bytes(b'existing')
    error = FileExistsError if failure == 'collision' else OSError if failure == 'read_error' else HTTPException
    with pytest.raises(error):
        asyncio.run(uploads.copy_document(Source(), destination))
    if failure == 'collision':
        assert destination.read_bytes() == b'existing'
    else:
        assert not destination.exists()


def test_document_db_failure_removes_the_uploaded_file(product_client, monkeypatch):
    product = _create(product_client, key='upload-rollback')
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic revision failure')
    monkeypatch.setattr(documents, 'stage_revision', fail)
    with pytest.raises(RuntimeError, match='Synthetic'):
        product_client.post('/api/documents',params={'title':'Pièce','product_id':product['product_id']},
                            files={'file':('proof.pdf',b'abc','application/pdf')})
    assert product_client.session.exec(select(Document)).all() == []
    assert not list(documents._DOCS_DIR.rglob('*.pdf'))


@pytest.mark.parametrize('header,expected_reads', [(b'10',0),(b'1',2),(None,2)])
def test_body_budget_rejects_before_multipart_even_without_trustworthy_length(header, expected_reads):
    called, sent, reads = [], [], []
    async def downstream(scope, receive, send):
        called.append(True)
    async def receive():
        reads.append(True)
        return {'type':'http.request','body':b'12345','more_body':True}
    async def send(message):
        sent.append(message)
    scope = {'type':'http','method':'POST','path':'/api/documents',
             'headers':[] if header is None else [(b'content-length',header)]}
    asyncio.run(uploads.DocumentUploadLimitMiddleware(downstream,max_body_bytes=8)(scope,receive,send))
    assert sent[0]['status'] == 413
    assert len(reads) == expected_reads and called == []


@pytest.mark.parametrize('body', [b'',b'12345678'])
def test_body_budget_replays_accepted_payload_exactly(body):
    captured = []
    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            captured.append(message['body'])
            if not message.get('more_body'):
                break
    async def receive():
        return {'type':'http.request','body':body,'more_body':False}
    async def send(message):
        pass
    scope={'type':'http','method':'POST','path':'/api/documents','headers':[]}
    asyncio.run(uploads.DocumentUploadLimitMiddleware(downstream,max_body_bytes=8)(scope,receive,send))
    assert b''.join(captured) == body


def test_body_budget_is_enforced_behind_an_asgi_mount_prefix():
    called, sent = [], []
    async def downstream(*args):
        called.append(True)
    async def receive():
        raise AssertionError('Oversized declared bodies must be refused before reading')
    async def send(message):
        sent.append(message)
    scope={'type':'http','method':'POST','path':'/desk/api/documents','root_path':'/desk',
           'headers':[(b'content-length',b'9')]}
    asyncio.run(uploads.DocumentUploadLimitMiddleware(downstream,max_body_bytes=8)(scope,receive,send))
    assert sent[0]['status'] == 413 and called == []


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    for key in ('STRUCTURA_INSTALLATION_CONFIG','STRUCTURA_ADMIN_WORKBENCH_CONFIG','STRUCTURA_BOOTSTRAP_PROFILE','STRUCTURA_WORKSHOP_CHILD'):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path/'structura.db'
    engine = create_engine(f'sqlite:///{path}')
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'_DB_PATH',path)
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(tmp_path))
    yield engine,path
    engine.dispose()


@pytest.mark.parametrize('profile', [None,'simulation','admin_workbench','unknown'])
def test_unconfigured_bootstrap_fails_before_database_creation(bootstrap, monkeypatch, profile):
    _,path=bootstrap
    if profile:
        monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE',profile)
    with pytest.raises(RuntimeError,match='non configurée'):
        database.init_db()
    assert not path.exists()


def test_explicit_simulation_creates_no_shared_accounts_and_keeps_users(bootstrap, monkeypatch):
    engine,_=bootstrap
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE','simulation')
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD','1')
    database.init_db()
    with Session(engine) as session:
        assert session.exec(select(User)).all() == []
        entity = session.exec(select(Entity)).one()
        user = User(username='scenario-user',email='scenario@example.test',password_hash='test-fixture',entity_id=entity.id)
        session.add(user);session.commit()
    database.init_db()
    with Session(engine) as session:
        assert [u.username for u in session.exec(select(User)).all()] == ['scenario-user']


def test_simulation_cannot_adopt_managed_identity(bootstrap, monkeypatch):
    engine,path=bootstrap
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE','simulation')
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD','1')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE hybrid_bootstrap(id INTEGER PRIMARY KEY)'))
        conn.execute(text('INSERT INTO hybrid_bootstrap VALUES(1)'))
    before=path.read_bytes()
    with pytest.raises(RuntimeError,match='comme simulation'):
        database.init_db()
    engine.dispose()
    assert path.read_bytes() == before


def private_bootstrap(directory):
    from backend.app.services.agent_workshop.instances import Instances
    instances = Instances(directory / 'campaign', {'config': {'participants': []}})
    actor_directory = instances.directory / 'instances' / 'bank'
    actor_directory.mkdir(parents=True)
    return instances, actor_directory


def test_workshop_prepares_private_credentials_and_refuses_legacy_books(tmp_path):
    from backend.app.core.simulation_bootstrap import BOOTSTRAP_FILENAME
    instances, directory = private_bootstrap(tmp_path)
    credentials = instances.bootstrap_credentials('bank', create=True)
    assert credentials['username'] == 'workshop_admin'
    assert 32 <= len(credentials['password']) <= 72
    assert instances.bootstrap_credentials('bank') == credentials
    assert (directory / BOOTSTRAP_FILENAME).is_file()
    assert instances.baseline().name.startswith('v3-private-bootstrap-')
    # No private credential is added to the campaign state returned by its export API.
    assert credentials['password'] not in json.dumps(instances.state)
    (directory / BOOTSTRAP_FILENAME).unlink()
    book = directory / 'structura.db'
    book.write_bytes(b'Existing isolated book must survive')
    with pytest.raises(RuntimeError, match='book existant est conservé'):
        instances.bootstrap_credentials('bank', create=True)
    assert book.read_bytes() == b'Existing isolated book must survive'
    assert not (directory / BOOTSTRAP_FILENAME).exists()


def test_private_baseline_restores_matching_bootstrap_credentials_without_signing_key(tmp_path):
    import sqlite3
    from backend.app.services.agent_workshop.instances import Instances
    instances, directory = private_bootstrap(tmp_path)
    instances.state.update(cases=[], actors={'bank': {'deals': []}})
    instances.state['config']['schema_version'] = 2
    credentials = instances.bootstrap_credentials('bank', create=True)
    with sqlite3.connect(directory / 'structura.db') as connection:
        connection.execute('CREATE TABLE proof(value TEXT)')
        connection.execute('INSERT INTO proof VALUES (?)', (credentials['username'],))
    (directory / '.jwt_secret').write_text('isolated-test-key', encoding='utf-8')
    instances.capture_baseline()
    fresh = Instances(tmp_path / 'next-campaign', instances.state)
    target = fresh.directory / 'instances' / 'bank'
    target.mkdir(parents=True)
    fresh.restore_baseline(target, 'bank')
    assert fresh.bootstrap_credentials('bank') == credentials
    with sqlite3.connect(target / 'structura.db') as connection:
        assert connection.execute('SELECT value FROM proof').fetchone()[0] == credentials['username']
    assert not (target / '.jwt_secret').exists()


def test_private_simulation_admin_can_provision_and_is_not_restored_after_revocation(bootstrap, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.database import get_session
    from backend.app.core.simulation_bootstrap import BOOTSTRAP_FILENAME
    engine, path = bootstrap
    instances, directory = private_bootstrap(path.parent)
    credentials = instances.bootstrap_credentials('bank', create=True)
    (path.parent / BOOTSTRAP_FILENAME).write_text(json.dumps(credentials), encoding='utf-8')
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE', 'simulation')
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD', '1')
    assert database.init_db()['accounts_created'] == 1
    assert database.init_db()['accounts_created'] == 0
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        assert [u.username for u in users] == ['workshop_admin']
        assert users[0].password_hash != credentials['password']
        assert database._verify_pw(credentials['password'], users[0].password_hash)
        app.dependency_overrides[get_session] = lambda: session
        try:
            client = TestClient(app)
            response = client.post('/api/auth/login', data={k: credentials[k] for k in ('username', 'password')})
            assert response.status_code == 200, response.text
            headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
            response = client.post('/api/admin/users', headers=headers, json={
                'username': 'agent_bank', 'email': 'bank@recette.invalid',
                'password': 'Generated-agent-password-for-test-123!', 'role': 'user', 'entity_id': users[0].entity_id})
            assert response.status_code == 201, response.text
        finally:
            app.dependency_overrides.clear()
        users[0].is_active = False
        session.add(users[0]); session.commit()
    with pytest.raises(RuntimeError, match='aucune restauration automatique'):
        database.init_db()
    with Session(engine) as session:
        assert not session.exec(select(User).where(User.username == 'workshop_admin')).one().is_active
        assert {u.username for u in session.exec(select(User)).all()} == {'workshop_admin', 'agent_bank'}


def test_simulation_profile_never_opens_the_application_data_directory(bootstrap, monkeypatch):
    from pathlib import Path
    private_directory = Path(database.__file__).resolve().parents[2] / 'data'
    monkeypatch.setattr(database, '_DB_PATH', private_directory / 'must-not-open.db')
    monkeypatch.setenv('STRUCTURA_DATA_DIR', str(private_directory))
    monkeypatch.setenv('STRUCTURA_BOOTSTRAP_PROFILE', 'simulation')
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD', '1')
    def forbidden():
        raise AssertionError('No database connection is allowed for this path')
    monkeypatch.setattr(database.engine, 'connect', forbidden)
    with pytest.raises(RuntimeError, match='non configurée'):
        database._require_simulation_bootstrap()


@pytest.mark.parametrize('password', ['too-short', 'x' * 73, None])
def test_simulation_refuses_invalid_explicit_private_credentials(tmp_path, password):
    from backend.app.core.simulation_bootstrap import BOOTSTRAP_FILENAME, simulation_credentials
    (tmp_path / BOOTSTRAP_FILENAME).write_text(json.dumps({
        'username': 'workshop_admin', 'email': 'bank@recette.invalid', 'password': password}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='privés de simulation'):
        simulation_credentials(tmp_path)
