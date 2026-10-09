"""Inspect an existing real campaign and qualify cross-controller UI controls."""
import argparse
from pathlib import Path
import time
import httpx
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('campaign')
    parser.add_argument('--base',default='http://127.0.0.1:8054')
    args=parser.parse_args()
    output=Path(__file__).resolve().parents[1]/'output/agent-workshop-ui'
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1500,'height':1000},locale='fr-FR')
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.base+'/#/login')
        page.locator('input[type=text]').fill('admin');page.locator('input[type=password]').fill('admin123')
        page.get_by_role('button',name='Se connecter',exact=True).click()
        page.wait_for_url('**/#/')
        token=page.evaluate("localStorage.getItem('auth_token')")
        headers={'Authorization':'Bearer '+token}
        base=args.base+'/api/admin/agent-workshop/'+args.campaign
        client=httpx.Client(trust_env=False)
        data=client.get(base,headers=headers).json()
        page.goto(args.base+'/#/admin/agent-workshop')
        page.locator('button.campaign').filter(has_text=data['config']['name']).first.click()
        page.get_by_role('heading',name=data['config']['name'],exact=True).wait_for()
        page.get_by_label('Configuration contractuelle').select_option('random')
        page.get_by_role('button',name='Pause',exact=True).click()
        try:
            page.get_by_role('button',name='Reprendre',exact=True).wait_for(timeout=60000)
            paused=client.get(base,headers=headers).json()
            assert paused['status']=='PAUSED',paused['status']
            time.sleep(2)
            stable=client.get(base,headers=headers).json()
            assert (stable['turns'],stable['business_date'])==(paused['turns'],paused['business_date'])
            page.get_by_role('button',name='Books et risques',exact=True).click()
            page.screenshot(path=str(output/'annual-books-desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'annual-books-mobile.png'))
            print('MOBILE_LAYOUT',page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))})"),flush=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Mobile overflow'
            assert not errors,errors
            page.get_by_role('button',name='Reprendre',exact=True).click()
            page.get_by_role('button',name='Pause',exact=True).wait_for(timeout=30000)
            print('CROSS_CONTROLLER_UI_CHECK_OK',paused['turns'],paused['business_date'],output,flush=True)
        finally:
            client.post(base+'/resume',headers=headers).raise_for_status()
            client.close();browser.close()


if __name__=='__main__':main()
