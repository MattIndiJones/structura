"""UI-only observability checks with intercepted API fixtures, no campaign writes.

The existing server supplies static assets only. Recorded campaign data validates
history presentation; live phases are explicit display fixtures, not AI trades.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from contextlib import ExitStack
import threading
from urllib.parse import urlparse
import argparse
import json
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--base',default=None)
args=parser.parse_args()
record=json.loads((ROOT/'backend/data/agent_workshop/4181bbaf4ef7481dbc2131ed1f253236/campaign.json').read_text(encoding='utf-8'))
from backend.app.services.agent_workshop.engine import check_books
record['book_checks']=check_books(record)
record['commercial_volume']=sum(c['client_volume'] for c in record['book_checks'])
state=deepcopy(record)
state['config']['name']='Recette du suivi — historique conservé'
output=ROOT/'output/agent-workshop-ui';output.mkdir(parents=True,exist_ok=True)
errors=[]
offline=False

with ExitStack() as cleanup:
    if not args.base:
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
            def guess_type(self,path):
                if path.endswith('.js'):return 'text/javascript'
                if path.endswith('.css'):return 'text/css'
                return super().guess_type(path)
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'frontend/dist')))
        cleanup.callback(server.server_close)
        cleanup.callback(server.shutdown)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        args.base='http://127.0.0.1:'+str(server.server_port)
    p=cleanup.enter_context(sync_playwright())
    browser=p.chromium.launch(headless=True)
    cleanup.callback(browser.close)
    context=browser.new_context(viewport={'width':1500,'height':1100},locale='fr-FR')
    context.add_init_script("localStorage.setItem('auth_token','ui-fixture-no-real-login')")
    page=context.new_page()
    page.on('pageerror',lambda error:errors.append(str(error)))
    def console_message(message):
        if message.type!='error':return
        # The offline fixture deliberately aborts this campaign GET request.
        # Keep all script errors and every unexpected resource error visible.
        if offline and message.text=='Failed to load resource: net::ERR_FAILED':return
        errors.append(message.text)
    page.on('console',console_message)
    def api(route):
        path=urlparse(route.request.url).path
        assert route.request.method=='GET','UI check must not mutate any backend'
        if path=='/api/auth/me':body={'id':3,'username':'Philippe','role':'user','entity_id':1}
        elif path=='/api/agent-workshop':body=[{**{k:state[k] for k in ('id','config','business_date','created_at')},'status':'RUNNING','turns':0}]
        elif path=='/api/agent-workshop/models':body={'models':['qwen2.5-coder:7b']}
        elif path=='/api/agent-workshop/'+state['id']:
            if offline:route.abort();return
            body=state
        elif '/screenshots/' in path:
            file=ROOT/'backend/data/agent_workshop'/state['id']/'screenshots'/path.rsplit('/',1)[-1]
            route.fulfill(status=200,body=file.read_bytes(),content_type='image/png');return
        else:body=[]
        route.fulfill(status=200,json=body)
    page.route('**/api/**',api)
    page.goto(args.base+'/#/agent-workshop')
    try:
        page.get_by_role('heading',name='Campagne terminée : aucun agent n’agit actuellement').wait_for(timeout=10000)
    except Exception:
        print('UI_DIAGNOSTIC',page.locator('body').inner_text()[:2500],errors,flush=True)
        page.screenshot(path=str(output/'observability-diagnostic.png'),full_page=True)
        raise
    expect(page.get_by_role('heading',name='Campagne terminée : aucun agent n’agit actuellement')).to_be_visible()
    expect(page.locator('.campaign.selected')).to_contain_text('Terminée · 504 décisions')
    expect(page.locator('.proof-summary')).to_contain_text('actions par API')
    assert not page.get_by_label('Nom',exact=True).is_visible()
    help_button=page.locator('[data-help="volume"]').get_by_role('button')
    help_button.focus()
    expect(page.get_by_role('tooltip')).to_contain_text('quatre écritures')
    help_button.press('Escape')
    expect(page.get_by_role('tooltip')).not_to_be_visible()
    page.screenshot(path=str(output/'observability-completed-desktop.png'),full_page=False)
    page.get_by_role('button',name='Filtrer BNP',exact=True).click()
    assert page.locator('.history-body strong').count()>0
    assert all('BNP ·' in t for t in page.locator('.history-body strong').all_text_contents())
    page.locator('.history button').first.click()
    expect(page.get_by_role('heading',name='Journal des actions terminées')).to_be_visible()
    expect(page.locator('.action-proof')).to_contain_text('HTTP 200')
    expect(page.locator('.action-proof')).to_contain_text('Aucune capture de navigation')
    page.get_by_role('button',name='Vue d’ensemble',exact=True).click()
    page.get_by_role('button',name='Tous les acteurs ×').click()
    page.get_by_role('button',name='+ Nouvelle campagne',exact=True).click()
    expect(page.get_by_label('Nom',exact=True)).to_be_visible()
    page.locator('[data-help="seed"]').get_by_role('button').hover()
    expect(page.get_by_role('tooltip')).to_contain_text('ne garantit pas des décisions IA identiques')
    page.get_by_label('Nom',exact=True).click()
    expect(page.get_by_role('tooltip')).not_to_be_visible()
    page.get_by_role('button',name='Fermer la configuration',exact=True).click()
    state['status']='RUNNING'
    state['activity']={'actor':'bnp','phase':'THINKING','started_at':datetime.now(timezone.utc).isoformat(),'tasks':['Calculer une cotation dans mon Pricer']}
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('heading',name='BNP réfléchit à sa prochaine action')).to_be_visible()
    expect(page.locator('.current').first).to_contain_text('Aucune nouvelle opération métier')
    state['activity'].update(phase='EXECUTING',tool='quote',reason='Calculer un prix avec ma marge',request={'method':'POST','path':'/api/price','status':'PENDING'})
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('heading',name='BNP · Calculer et envoyer un prix')).to_be_visible()
    expect(page.locator('.current').first).to_contain_text('Structura traite : POST /api/price')
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(output/'observability-live-desktop.png'),full_page=False)
    state['status']='PAUSED';state['activity']=None
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('heading',name='Simulation en pause',exact=True)).to_be_visible()
    state['status']='RUNNING';state['controller_active']=False
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('heading',name='Aucun contrôleur actif : les IA ne poursuivent plus la campagne')).to_be_visible()
    expect(page.locator('.campaign.selected')).to_contain_text('Exécution non confirmée')
    expect(page.get_by_role('button',name='Démarrer les IA',exact=True)).to_be_visible()
    assert not page.get_by_role('button',name='Pause',exact=True).is_visible()
    state['status']='COMPLETED'
    page.get_by_role('button',name='Actualiser',exact=True).click()
    expect(page.get_by_role('heading',name='Campagne terminée : aucun agent n’agit actuellement')).to_be_visible()
    page.get_by_role('button',name='Voir les problèmes (4)',exact=True).first.click()
    expect(page.get_by_role('region',name='Registre des problèmes')).to_be_visible()
    assert not page.get_by_role('region',name='Suivi de la simulation').count()
    expect(page.locator('.issue-register')).to_contain_text('non confirmé')
    page.get_by_role('button',name='Vue d’ensemble',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflow'
    page.screenshot(path=str(output/'observability-mobile.png'),full_page=True)
    booking_help=page.locator('[data-help="booking"]').get_by_role('button')
    booking_help.scroll_into_view_if_needed()
    # Let scroll events settle: the shared HelpTip closes on scrolling.
    page.wait_for_timeout(700)
    booking_help.focus()
    expect(page.get_by_role('tooltip')).to_contain_text('1 / 4')
    assert page.get_by_role('tooltip').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth}'),'Tooltip clipped on mobile'
    page.screenshot(path=str(output/'help-mobile-tooltip.png'),full_page=False)
    booking_help.press('Escape')
    page.set_viewport_size({'width':1500,'height':1100})
    offline=True
    page.clock.install()
    page.clock.fast_forward(18000)
    expect(page.get_by_text('L’état affiché est la dernière réponse reçue ; l’activité actuelle ne peut pas être confirmée.')).to_be_visible()
    offline=False
    problem_file=ROOT/'backend/data/agent_workshop/6b0197fc9f0f439e9ade308c88f268ec/campaign.json'
    if problem_file.is_file():
        state=json.loads(problem_file.read_text(encoding='utf-8'))
        state['book_checks']=check_books(state)
        state['commercial_volume']=sum(c['client_volume'] for c in state['book_checks'])
        page.reload()
        page.get_by_role('button',name='Voir les problèmes (12)',exact=True).first.click()
        expect(page.get_by_role('region',name='Registre des problèmes')).to_be_visible()
        expect(page.locator('.issue-card')).to_have_count(12)
        page.get_by_label('Catégorie de problème').select_option('structura')
        expect(page.locator('.issue-card')).to_have_count(4)
        expect(page.locator('.issue-register')).to_contain_text('route que son installation n’a pas trouvée')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(output/'help-issues-desktop.png'),full_page=False)
        page.locator('.issue-card').first.get_by_role('button',name='Voir l’action et sa preuve').click()
        expect(page.locator('.action-proof')).to_contain_text('/api/pricing/retry')
        expect(page.locator('.action-proof')).to_contain_text('HTTP 404')
        page.get_by_role('button',name='Voir les problèmes (12)',exact=True).first.click()
        with page.expect_download() as download:
            page.get_by_role('button',name='Télécharger les signalements',exact=True).click()
        report=Path(download.value.path()).read_text(encoding='utf-8')
        assert 'POINT 12' in report and 'PRODUCT_PRICING_RECEIPT_INVALID' in report and 'hector@structura.com' in report
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Issue register mobile overflow'
        page.screenshot(path=str(output/'help-issues-mobile.png'),full_page=False)
    assert not errors,errors
    browser.close()
print('OBSERVABILITY_UI_OK phases/help-keyboard/help-mobile/12-issues/native-filter/proof/txt-export/390px; API fixtures, no real writes')
