"""Check the real admin UI against an explicitly isolated test server."""
from pathlib import Path
import json
import time
import httpx
from playwright.sync_api import sync_playwright

BASE='http://127.0.0.1:8054'
OUTPUT=Path(__file__).resolve().parents[1]/'output'/'agent-workshop-ui'
OUTPUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1000},locale='fr-FR')
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/#/login')
    page.locator('input[type=text]').fill('admin')
    page.locator('input[type=password]').fill('admin123')
    page.get_by_role('button',name='Se connecter',exact=True).click()
    page.wait_for_function("Boolean(localStorage.getItem('auth_token'))")
    page.wait_for_url('**/#/')
    page.goto(BASE+'/#/admin/agent-workshop')
    page.get_by_role('heading',name='Recette par utilisateurs IA').wait_for()
    if not page.get_by_label('Nom',exact=True).is_visible():
        page.get_by_role('button',name='+ Nouvelle campagne',exact=True).click()
    page.get_by_label('Nom',exact=True).fill('Qualification IA depuis les vrais écrans')
    page.get_by_label('Mois',exact=True).fill('1')
    page.get_by_label('Inclure Société Générale').uncheck()
    page.get_by_label('Décisions maximum').fill('100')
    page.get_by_role('button',name='Créer la campagne',exact=True).click()
    page.get_by_role('button',name='Démarrer les IA',exact=True).wait_for()
    page.get_by_role('heading',name='Qualification IA depuis les vrais écrans',exact=True).wait_for()
    page.screenshot(path=str(OUTPUT/'desktop.png'),full_page=False)
    token=page.evaluate("localStorage.getItem('auth_token')")
    campaigns=httpx.get(BASE+'/api/admin/agent-workshop',headers={'Authorization':'Bearer '+token},trust_env=False).json()
    key=next(c['id'] for c in campaigns if c['config']['name']=='Qualification IA depuis les vrais écrans')
    print('UI_CAMPAIGN',key,flush=True)
    page.get_by_role('button',name='Démarrer les IA',exact=True).click()
    page.get_by_role('button',name='Pause',exact=True).wait_for()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUTPUT/'mobile.png'),full_page=False)
    assert not errors,errors
    response=httpx.post(BASE+f'/api/admin/agent-workshop/{key}/stop',headers={'Authorization':'Bearer '+token},trust_env=False)
    assert response.status_code==200,response.text
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        data=httpx.get(BASE+f'/api/admin/agent-workshop/{key}',headers={'Authorization':'Bearer '+token},trust_env=False).json()
        if data['status']=='STOPPED' and not data['processes']:break
        time.sleep(.5)
    else:raise AssertionError('Private worker instances have not closed')
    print('UI_CHECK_OK',OUTPUT,flush=True)
    browser.close()
