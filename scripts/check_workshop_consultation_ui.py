"""Inspect saved BNP/Hector books via native read-only Structura and the built UI.

The campaign is never resumed. All API writes in the viewer must be rejected;
source campaign and database hashes must remain identical. No main DB is opened.
"""
import argparse
from contextlib import ExitStack
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('campaign', type=Path)
args = parser.parse_args()
campaign = args.campaign.resolve()
state = json.loads((campaign/'campaign.json').read_text(encoding='utf-8'))
assert state['status'] in {'STOPPED','COMPLETED','ATTENTION'}
assert campaign.name==state['id']
output = ROOT/'output/agent-workshop-consultation-ui'
output.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix='controller-',dir=output)).resolve()
assert scratch.parent==output.resolve()
os.environ['STRUCTURA_DATA_DIR']=str(scratch)
os.environ['STRUCTURA_DISABLE_SCHEDULER']='1'

from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from backend.app.api import agent_workshop
from backend.app.api.auth import get_current_user
from backend.app.services.agent_workshop import consultation, engine
from backend.app.services.agent_workshop.consultation import Consultations
from backend.app.services.agent_workshop.engine import Manager
from backend.app.services.agent_workshop.store import Store

files=[campaign/'campaign.json']+[campaign/'instances'/a/'structura.db' for a in ['bnp','hector']]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
store=Store(campaign.parent); viewer=Consultations(); manager=Manager()
result={'campaign_id':state['id'],'books':{},'model_calls_before':state['usage']['model_calls']}
with ExitStack() as cleanup:
    for module in [agent_workshop,consultation,engine]: cleanup.enter_context(patch.object(module,'store',store))
    cleanup.enter_context(patch.object(agent_workshop,'manager',manager))
    for module in [agent_workshop,consultation]: cleanup.enter_context(patch.object(module,'consultations',viewer))
    cleanup.callback(viewer.shutdown)
    app=FastAPI();app.include_router(agent_workshop.router)
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=state['owner'],role='admin')
    api=cleanup.enter_context(TestClient(app))
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
        def guess_type(self,path):
            if path.endswith('.js'):return 'application/javascript'
            if path.endswith('.css'):return 'text/css'
            return super().guess_type(path)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT/'frontend/dist')))
    cleanup.callback(server.server_close);cleanup.callback(server.shutdown)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    pw=cleanup.enter_context(sync_playwright())
    browser=pw.chromium.launch(headless=True);cleanup.callback(browser.close)
    context=browser.new_context(viewport={'width':1500,'height':1000},locale='fr-FR')
    page=context.new_page();page.add_init_script("localStorage.setItem('auth_token','isolated-owner-session')")
    errors=[]
    context.on('page',lambda p:p.on('pageerror',lambda e:errors.append(str(e))))
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api_route(route):
        path=urlparse(route.request.url).path
        if path=='/api/auth/me':
            route.fulfill(json={'id':state['owner'],'username':'admin','role':'admin','entity_id':1});return
        if path=='/api/agent-workshop/models':
            route.fulfill(json={'models':[]});return
        response=api.request(route.request.method,path,content=route.request.post_data)
        route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.route('**/api/**',api_route)
    page.goto(f'http://127.0.0.1:{server.server_port}/#/agent-workshop')
    page.get_by_placeholder('Nom ou référence').fill(state['id'][:8])
    page.locator('.campaign').filter(has_text=state['config']['name']).click()
    expect(page.get_by_role('heading',name=state['config']['name'],exact=True)).to_be_visible()
    for actor in ['bnp','hector']:
        name=state['actors'][actor]['name']
        card=page.locator('.actor').filter(has=page.get_by_role('button',name='Filtrer '+name,exact=True))
        with context.expect_page(timeout=60000) as created:
            card.get_by_role('button',name='Ouvrir le Structura de '+name+' en consultation',exact=True).click()
        native=created.value
        expect(native.get_by_role('heading',name='Booking — produits bookés',exact=True)).to_be_visible(timeout=60000)
        expect(native.locator('.consultation-banner')).to_contain_text(state['actors'][actor]['entity'])
        expect(native.locator('.consultation-banner')).to_contain_text(state['business_date'])
        expect(native.get_by_role('button',name=re.compile('Rafraîchir le book'))).to_be_disabled()
        assert 'token=' not in native.url
        deals=native.evaluate("async()=>{const r=await fetch('/api/deals',{headers:{Authorization:'Bearer '+localStorage.getItem('auth_token')}});return r.json()}")
        assert len(deals)==len(state['actors'][actor]['deals'])
        declined=native.evaluate("async()=>{const r=await fetch('/api/deals/1/mtm',{method:'POST',headers:{Authorization:'Bearer '+localStorage.getItem('auth_token')}});return r.status}")
        assert declined==403
        root=native.url.split('/#',1)[0]
        native.goto(root+'/#/booking?deal=1')
        expect(native.locator('#deal-1').get_by_text('calcul archivé, enregistré le',exact=False)).to_be_visible(timeout=30000)
        native.screenshot(path=str(output/f'{actor}-booking.png'),full_page=True)
        native.goto(root+'/#/booking/1/valuations')
        expect(native.get_by_role('heading',name='Calculs de MtM enregistrés',exact=True)).to_be_visible()
        assert native.locator('.valuation-error').count()==0
        native.screenshot(path=str(output/f'{actor}-mtm-history.png'),full_page=True)
        result['books'][actor]={'native_deals':len(deals),'mtm_history_visible':True,'frozen_date_mtm_restored':True,'write_denied':declined,'url':root}
        expect(card.get_by_role('button',name='Fermer la consultation',exact=True)).to_be_visible()
        page.locator('.management summary').click()
        expect(page.get_by_role('button',name='Recommencer la campagne',exact=True)).to_be_disabled()
        page.locator('.management summary').click()
        card.get_by_role('button',name='Fermer la consultation',exact=True).click()
        expect(card.get_by_role('button',name='Fermer la consultation',exact=True)).not_to_be_visible(timeout=30000)
        native.close()
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Ouvrir le Structura de Hector en consultation',exact=True).scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(output/'consultation-mobile.png'),full_page=True)
    assert not errors,errors
    assert not viewer.active(state['id'])
after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
assert after==before,'The saved campaign and books must remain byte-identical'
result.update(source_files_unchanged=True,javascript_errors=errors,model_calls_after=json.loads((campaign/'campaign.json').read_text(encoding='utf-8'))['usage']['model_calls'])
assert result['model_calls_before']==result['model_calls_after']
(output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
