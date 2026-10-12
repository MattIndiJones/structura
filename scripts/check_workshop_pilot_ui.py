"""Pilot UI qualification with isolated campaign APIs and explicit display fixtures.

No model or business backend is started. These states qualify presentation,
diagnosis, pagination and reconciliation, not autonomous commercial decisions.
"""
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse
import os
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
output = Path(os.environ.get('STRUCTURA_TEST_OUTPUT', ROOT / 'output/agent-workshop-ui'))
output.mkdir(parents=True, exist_ok=True)

with ExitStack() as cleanup:
    local = Store(Path(cleanup.enter_context(TemporaryDirectory(prefix='pilot-ui-'))) / 'campaigns')
    manager = Manager()
    cleanup.enter_context(patch.object(engine, 'store', local))
    cleanup.enter_context(patch.object(agent_workshop, 'store', local))
    cleanup.enter_context(patch.object(agent_workshop, 'manager', manager))
    app = FastAPI(); app.include_router(agent_workshop.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=3, role='user')
    api = cleanup.enter_context(TestClient(app))
    state = local.create(CampaignConfig(name='Partie de qualification du pilotage', months=12), 3)
    state.update(status='COMPLETED', month=12, turns=201)
    state['actions'] = [dict(actor='bnp', tool='api', args={'path':'/api/missing'}, reason='Examiner une capacité',
        result={'error':'Ancienne erreur HTTP 404'}, http_calls=[{'method':'GET','path':'/api/missing','status':404}],
        status='FAILED', date=state['business_date'])]
    state['actions'] += [dict(actor='hector', tool='mail', args={'to':'bnp'}, result={'delivered':'bnp'},
        status='SUCCESS', reason='Dialogue courant', date=state['business_date']) for _ in range(200)]
    state['messages'] = [dict(id=str(i), **{'from':'hector','to':'bnp'}, body='Message ancien à retrouver' if i==0 else 'Dialogue courant',
        subject='Échange', date=state['business_date'], case_id='', attachment=None) for i in range(201)]
    state['cases'] = {'CASE-001':dict(id='CASE-001',month=0,nominal=1e7,instrument_reference='NOTE',rfq_sent=True,declines=['ca','sg'])}
    state['accepted']={'CASE-001':'q'}
    state['quotes']=[dict(id='q',bank='bnp',case_id='CASE-001',price=100)]
    fields=dict(case_id='CASE-001',instrument_reference='NOTE',trade_reference='BANK',issuer=state['actors']['bnp']['entity'],
                nominal=1e7,currency='EUR',price_traded=100,value_date=state['business_date'],contract_hash='fixture-terms',settlement_status='SETTLED')
    for actor,leg,side,party in [('bnp','BANK_SELL','SELL','hector'),('hector','HECTOR_BUY','BUY','bnp'),('hector','HECTOR_SELL','SELL','client'),('client','CLIENT_BUY','BUY','hector')]:
        state['actors'][actor]['deals'].append(dict(fields,leg=leg,our_side=side,counterparty=state['actors'][party]['entity'],
            trade_reference='CLIENT' if leg in {'HECTOR_SELL','CLIENT_BUY'} else 'BANK',price_traded=101 if leg in {'HECTOR_SELL','CLIENT_BUY'} else 100))
    local.save(state)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
        def guess_type(self,path):
            if path.endswith('.js'): return 'text/javascript'
            if path.endswith('.css'): return 'text/css'
            return super().guess_type(path)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'frontend/dist')))
    cleanup.callback(server.server_close);cleanup.callback(server.shutdown)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    playwright=cleanup.enter_context(sync_playwright())
    browser=playwright.chromium.launch(headless=True);cleanup.callback(browser.close)
    page=browser.new_page(viewport={'width':1500,'height':1100},locale='fr-FR')
    page.add_init_script("localStorage.setItem('auth_token','isolated-pilot-fixture')")
    errors=[];writes=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def route_api(route):
        path=urlparse(route.request.url).path
        if path=='/api/auth/me': route.fulfill(json={'id':3,'username':'Philippe','role':'user','entity_id':1});return
        if path=='/api/agent-workshop/models': route.fulfill(json={'models':['qwen2.5-coder:7b']});return
        assert path.startswith('/api/agent-workshop'),path
        if route.request.method!='GET':writes.append((route.request.method,path))
        response=api.request(route.request.method,path,content=route.request.post_data)
        route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.route('**/api/**',route_api)
    page.goto(f'http://127.0.0.1:{server.server_port}/#/agent-workshop')
    expect(page.get_by_role('heading',name='Simulation entre agents')).to_be_visible()
    expect(page.get_by_role('heading',name='Campagne terminée : aucun agent n’agit actuellement')).to_be_visible()
    page.screenshot(path=str(output/'pilot-overview-desktop.png'),full_page=False)
    page.get_by_role('button',name='Actions et preuves',exact=True).click()
    page.get_by_label('Rechercher dans le journal').fill('Ancienne erreur')
    expect(page.locator('.table-wrap tbody tr')).to_have_count(1)
    page.locator('.table-wrap tbody tr').click()
    expect(page.locator('.action-proof')).to_contain_text('HTTP 404')
    expect(page.locator('.table-wrap tbody tr').last).to_contain_text('#1')
    page.get_by_label('Rechercher dans le journal').fill('')
    for _ in range(8):page.get_by_role('button',name='Actions suivantes',exact=True).click()
    expect(page.get_by_role('navigation',name='Pages des actions')).to_contain_text('page 9 / 9')
    expect(page.locator('section.panel tbody tr').last).to_contain_text('#1')
    page.get_by_role('button',name='Conversations',exact=True).click()
    page.get_by_label('Rechercher dans le journal').fill('Message ancien')
    expect(page.locator('.feed article')).to_have_count(1)
    page.locator('.controls').get_by_role('button',name='Voir les problèmes (1)',exact=True).click()
    page.get_by_role('button',name='Qualifier ce point',exact=True).click()
    page.get_by_label('Qualification du signalement').select_option('USAGE')
    page.get_by_label('État du signalement').select_option('CLOSED')
    page.get_by_label('Diagnostic du signalement').fill('Route inventée par l’agent ; capacités natives vérifiées.')
    page.get_by_role('button',name='Enregistrer le diagnostic',exact=True).click()
    expect(page.locator('.diagnosis')).to_contain_text('Route inventée')
    expect(page.locator('.controls')).to_contain_text('0 ouvert(s)')
    assert api.get(f"/api/agent-workshop/{state['id']}/export").json()['issue_reviews']['action-0']['status']=='CLOSED'
    page.screenshot(path=str(output/'pilot-issue-diagnosis.png'),full_page=False)
    page.get_by_role('button',name='Books et risques',exact=True).click()
    expect(page.get_by_role('region',name='Dossiers et books')).to_contain_text('Quatre écritures rapprochées')
    state['actors']['client']['deals'].append(dict(state['actors']['client']['deals'][0]))
    local.save(state)
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('region',name='Dossiers et books')).to_contain_text('Écart entre books')
    expect(page.get_by_role('region',name='Dossiers et books')).to_contain_text('Nombre d’écritures')
    page.screenshot(path=str(output/'pilot-book-mismatch.png'),full_page=False)
    state.update(status='RUNNING',month=0,run_started_at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat(),
        activity={'actor':'bnp','phase':'EXECUTING','tool':'quote','reason':'Calculer une cotation','started_at':datetime.now(timezone.utc).isoformat(),
                  'request':{'method':'POST','path':'/api/price','status':'PENDING'}})
    local.save(state)
    lease=CampaignLease(local.path(state['id']))
    try:
        page.get_by_role('button',name='Actualiser',exact=True).click()
        expect(page.get_by_role('heading',name='BNP · Calculer et envoyer un prix')).to_be_visible()
        expect(page.get_by_role('region',name='Suivi de la simulation')).to_contain_text('Structura traite')
        page.get_by_role('button',name='Pause',exact=True).click()
        expect(page.locator('.content>.panel').first).to_contain_text('Pause en cours')
        state.update(status='PAUSED',pause_reason='ERROR',activity=None,last_control_id=local.read_command(state['id'])['id'])
        local.save(state)
        page.get_by_role('button',name='Actualiser',exact=True).click()
        expect(page.get_by_role('region',name='Suivi de la simulation')).to_contain_text('plusieurs erreurs')
        page.locator('.management summary').click()
        expect(page.get_by_role('button',name='Recommencer la campagne',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='Supprimer la campagne',exact=True)).to_be_disabled()
        page.get_by_role('button',name='Reprendre',exact=True).click()
        expect(page.get_by_role('button',name='Pause',exact=True)).to_be_visible()
        page.get_by_role('button',name='Arrêter',exact=True).click()
        expect(page.locator('.content>.panel').first).to_contain_text('Fermeture en cours')
        state.update(status='STOPPED',pause_reason='USER',last_control_id=local.read_command(state['id'])['id'])
        local.save(state)
    finally:
        lease.close()
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('button',name='Démarrer les IA',exact=True)).to_be_enabled()
    state.update(status='ATTENTION',turns=800)
    local.save(state)
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('button',name='Démarrer les IA',exact=True)).to_be_disabled()
    expect(page.get_by_role('region',name='Suivi de la simulation')).to_contain_text('Budget de décisions épuisé')
    page.get_by_role('button',name='Préparer une nouvelle campagne',exact=True).click()
    expect(page.get_by_label('Décisions maximum',exact=True)).to_have_value('800')
    page.get_by_role('button',name='Fermer la configuration',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Mobile overflow'
    page.screenshot(path=str(output/'pilot-mobile.png'),full_page=False,animations='disabled')
    assert not errors,errors
    assert all(not path.endswith('/start') for _,path in writes),writes
    print('PILOT_UI_OK full-history/diagnosis/export/books/mismatch/live/pause/resume/stop/budget/390px; isolated fixtures, no model')
