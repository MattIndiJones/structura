"""Exercise the built UI against real management APIs with temporary campaigns.

No main DB, AI model or private backend is started. Only the models inventory is
stubbed; campaign GET/reset/DELETE run the actual router, controller and store.
"""
from contextlib import ExitStack
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse
import json
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from backend.app.api import agent_workshop
from backend.app.api.auth import get_current_user
from backend.app.services.agent_workshop import engine
from backend.app.services.agent_workshop.engine import Manager
from backend.app.services.agent_workshop.lease import CampaignLease
from backend.app.services.agent_workshop.store import Store, CampaignConfig

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'output/agent-workshop-ui'
output.mkdir(parents=True, exist_ok=True)

with ExitStack() as cleanup:
    temporary = Path(cleanup.enter_context(TemporaryDirectory(prefix='management-ui-', dir=output)))
    assert temporary.resolve().parent == output.resolve()
    store = Store(temporary / 'campaigns')
    manager = Manager()
    cleanup.enter_context(patch.object(engine, 'store', store))
    cleanup.enter_context(patch.object(agent_workshop, 'store', store))
    cleanup.enter_context(patch.object(agent_workshop, 'manager', manager))
    app = FastAPI(); app.include_router(agent_workshop.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=3, role='user')
    api = cleanup.enter_context(TestClient(app))
    other = store.create(CampaignConfig(name='Essai à conserver', months=1), 3)
    state = store.create(CampaignConfig(name='Essai de remise à zéro', months=1, seed=17), 3)
    state.update(status='COMPLETED', turns=58)
    state['actions'] = [{'actor':'hector','tool':'mail','args':{},'reason':'Dialoguer avec BNP','status':'SUCCESS','channel':'MAIL','result':{},'date':state['business_date']}]
    store.save(state)
    private = store.path(state['id']) / 'instances/hector'
    private.mkdir(parents=True)
    (private / 'structura.db').write_bytes(b'isolated private book')

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
        def guess_type(self, path):
            if path.endswith('.js'): return 'text/javascript'
            if path.endswith('.css'): return 'text/css'
            return super().guess_type(path)
    server = ThreadingHTTPServer(('127.0.0.1',0), partial(QuietHandler,directory=str(ROOT/'frontend/dist')))
    cleanup.callback(server.server_close); cleanup.callback(server.shutdown)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    playwright = cleanup.enter_context(sync_playwright())
    browser = playwright.chromium.launch(headless=True); cleanup.callback(browser.close)
    page = browser.new_page(viewport={'width':1500,'height':1100}, locale='fr-FR')
    page.add_init_script("localStorage.setItem('auth_token','isolated-ui-fixture')")
    errors=[]; writes=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    def route_api(route):
        path = urlparse(route.request.url).path
        if path == '/api/auth/me':
            route.fulfill(json={'id':3,'username':'Philippe','role':'user','entity_id':1}); return
        if path == '/api/agent-workshop/models':
            route.fulfill(json={'models':['qwen2.5-coder:7b']}); return
        assert path.startswith('/api/agent-workshop'), path
        if route.request.method != 'GET': writes.append((route.request.method,path))
        response = api.request(route.request.method,path,content=route.request.post_data)
        route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.route('**/api/**',route_api)
    page.goto(f'http://127.0.0.1:{server.server_port}/#/agent-workshop')
    expect(page.get_by_role('heading',name=state['config']['name'],exact=True)).to_be_visible()

    page.get_by_role('button',name='+ Nouvelle campagne',exact=True).click()
    page.get_by_label('Nom',exact=True).fill('Brouillon perdu')
    page.get_by_label('Mois',exact=True).fill('3')
    page.get_by_role('button',name='Réinitialiser les champs',exact=True).click()
    expect(page.get_by_label('Nom',exact=True)).to_have_value('Une année avec Hector')
    expect(page.get_by_label('Mois',exact=True)).to_have_value('12')
    page.get_by_role('button',name='Fermer la configuration',exact=True).click()
    page.get_by_role('button',name='Filtrer Hector',exact=True).click()
    page.get_by_role('button',name='Actions et preuves',exact=True).click()
    page.locator('tbody tr').first.click()
    expect(page.locator('.action-proof')).to_be_visible()
    page.get_by_role('button',name='Réinitialiser la vue',exact=True).click()
    expect(page.get_by_role('region',name='Suivi de la simulation')).to_be_visible()
    assert not page.get_by_role('button',name='Tous les acteurs ×').count()
    assert not page.locator('.action-proof').count()
    assert not writes

    page.get_by_role('button',name='Supprimer la campagne',exact=True).click()
    expect(page.get_by_role('dialog')).to_contain_text('sauvegarde locale')
    page.get_by_role('button',name='Annuler',exact=True).click()
    assert not writes and len(store.list(3)) == 2

    # The lease can change after a screen was read: the backend must still refuse.
    lease = CampaignLease(store.path(state['id']))
    try:
        page.get_by_role('button',name='Recommencer la campagne',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='Recommencer à zéro',exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('contrôleur utilise encore')
        assert store.load(state['id'])['turns'] == 58
    finally: lease.close()
    page.get_by_role('button',name='Recommencer la campagne',exact=True).click()
    page.get_by_role('dialog').get_by_role('button',name='Recommencer à zéro',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Campagne réinitialisée')
    expect(page.get_by_role('button',name='Démarrer les IA',exact=True)).to_be_visible()
    fresh = next(row for row in store.list(3) if row['id'] != other['id'])
    assert fresh['id'] != state['id'] and fresh['turns'] == 0
    assert len(store.list(3)) == 2
    assert not store.path(state['id']).exists()
    assert next((store.root/'_archive').glob('*/instances/hector/structura.db')).read_bytes() == b'isolated private book'
    expect(page.get_by_role('button',name='Démarrer les IA',exact=True)).to_be_enabled()
    page.screenshot(path=str(output/'management-reset-desktop.png'),full_page=False)

    # A paused campaign is still live and must first be stopped.
    live = store.load(fresh['id']); live['status']='PAUSED'; store.save(live)
    lease = CampaignLease(store.path(fresh['id']))
    try:
        page.get_by_role('button',name='Actualiser',exact=True).click()
        expect(page.get_by_role('button',name='Recommencer la campagne',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='Supprimer la campagne',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='Arrêter',exact=True)).to_be_visible()
    finally: lease.close()
    live['status']='STOPPED';store.save(live)
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('button',name='Supprimer la campagne',exact=True)).to_be_enabled()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Management mobile overflow'
    page.get_by_role('button',name='Supprimer la campagne',exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert page.get_by_role('dialog').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth}'), 'Mobile confirmation overflow'
    page.screenshot(path=str(output/'management-delete-mobile.png'),full_page=False,animations='disabled')
    page.get_by_role('dialog').get_by_role('button',name='Supprimer la campagne',exact=True).click()
    expect(page.get_by_role('heading',name=other['config']['name'],exact=True)).to_be_visible()
    assert len(store.list(3)) == 1 and store.list(3)[0]['id'] == other['id']
    expect(page.get_by_role('dialog')).not_to_be_visible()
    page.get_by_role('button',name='Supprimer la campagne',exact=True).click()
    page.get_by_role('dialog').get_by_role('button',name='Supprimer la campagne',exact=True).click()
    expect(page.get_by_role('heading',name='Faire utiliser Structura par des IA',exact=True)).to_be_visible()
    expect(page.get_by_label('Nom',exact=True)).to_be_visible()
    assert not store.list(3) and len(list((store.root/'_archive').iterdir())) == 3
    assert not errors, errors
    assert all(not path.endswith('/start') for _,path in writes), writes
    print('MANAGEMENT_UI_OK view/fields/cancel/reset/delete-last/active-guard/private-backup/390px; real APIs, isolated temporary data')
