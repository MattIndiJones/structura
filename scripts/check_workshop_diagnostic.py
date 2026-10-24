"""Bounded native acceptance check; isolated data, no model calls, owned cleanup."""
from datetime import datetime, timezone, date
from dateutil.relativedelta import relativedelta
import json
from pathlib import Path
import sys
import shutil
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.agent_workshop.diagnostic import diagnostic_defaults
from app.services.agent_workshop.configuration import participants, schedule
from app.services.agent_workshop.store import Store, CampaignConfig
from app.services.agent_workshop.instances import Instances, clock_file
from app.services.agent_workshop.tools import Tools
from app.services.agent_workshop.reconciliation import check_books
from app.core.calendars import adjust,BusinessDayConvention


def run_ui():
    """Static built frontend only: no Structura backend, model or actor process."""
    from functools import partial
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    from threading import Thread
    from types import SimpleNamespace
    from playwright.sync_api import sync_playwright
    directory=ROOT/'.runtime'/'diagnostic-acceptance'/('ui-'+uuid4().hex)
    directory.mkdir(parents=True)
    class StaticHandler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(StaticHandler,directory=str(ROOT/'frontend/dist')))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(locale='fr-FR')
            context.add_init_script("sessionStorage.setItem('auth_token','STATIC_PREVIEW')")
            page=context.new_page()
            page.route('**/api/**',lambda route:route.fulfill(json={'id':1,'role':'admin','username':'preview','entity_id':1} if route.request.url.endswith('/api/auth/me') else []))
            state={'actors':{'hector':{'url':'http://127.0.0.1:'+str(server.server_port)}}}
            result=check_configuration(SimpleNamespace(page=lambda key:page),state,directory)
            result.update(backend_processes=0,model_calls=0)
            (directory/'acceptance-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps({'path':str(directory),**result}),flush=True)
            context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def check_configuration(tools,state,directory):
    """Rendered frontend with offline controller responses, without starting AI."""
    from app.services.agent_workshop.configuration import preview
    page=tools.page('hector')
    provider={'key':'openai','label':'OpenAI','ready':False,'default_model':'gpt-6-luna',
              'models':[{'id':'gpt-6-luna','label':'GPT-6 Luna'}]}
    calls=[]
    def controller(route):
        endpoint=route.request.url.split('/api/agent-workshop',1)[1]
        calls.append({'path':endpoint,'method':route.request.method})
        response=preview(route.request.post_data_json) if endpoint=='/preview' else diagnostic_defaults() if endpoint=='/defaults' else {'providers':[provider]} if endpoint=='/models' else []
        route.fulfill(json=response)
    page.route('**/api/agent-workshop**',controller)
    page.set_viewport_size({'width':1440,'height':1000})
    page.goto(state['actors']['hector']['url']+'/#/agent-workshop')
    pane=page.locator('.configuration');pane.wait_for(state='visible')
    page.locator('.config-summary .estimate').wait_for()
    desktop=pane.bounding_box()
    assert desktop['width']>1000,desktop
    assert page.locator('.campaign-sidebar').count()==0
    page.get_by_role('button',name='Calendrier RFQ',exact=True).click()
    field=page.get_by_label('RFQ du mois 1',exact=True)
    field.fill('0')
    page.wait_for_function("document.querySelector('.estimate')?.textContent.includes('3 RFQ')")
    field.fill('5')
    page.wait_for_function("document.querySelector('.estimate')?.textContent.includes('8 RFQ')")
    page.screenshot(path=str(directory/'configuration-desktop.png'))
    page.set_viewport_size({'width':900,'height':780})
    assert page.locator('.configuration').bounding_box()['width']>800
    bounds=page.locator('.config-summary .actions').bounding_box()
    assert bounds['y']+bounds['height']<=780,bounds
    page.screenshot(path=str(directory/'configuration-compact.png'))
    assert all(c['path'] not in {'/start','/resume'} for c in calls)
    page.unroute('**/api/agent-workshop**',controller)
    return {'full_width_desktop':desktop['width'],'estimate_reactive':True,'no_start':True,'compact_actions_visible':True}


class CoverageController:
    def __init__(self,state,store):self.live=state;self.store=store
    def consume_command(self):return False
    def begin_activity(self,*a,**k):pass
    def persist(self):self.store.save(self.live)
    def incident(self,actor,kind,text):
        row={'id':uuid4().hex,'actor':actor,'kind':kind,'description':text,'date':self.live['business_date']}
        self.live['incidents'].append(row);return row


def run():
    from playwright.sync_api import sync_playwright
    root=ROOT/'.runtime'/'diagnostic-acceptance'/uuid4().hex
    root.mkdir(parents=True)
    config=diagnostic_defaults()
    config.update(name='Recette native bornée — sans IA', start_date='2021-10-14',end_date='2026-10-14',coaching=False)
    config['calendar']=[{'month':1,'count':0,'slots':[]},{'month':2,'count':2,'slots':[
        {'requester':'leonteq','template':'reverse_convertible','recipients':['bnp','sg','ca']},
        {'requester':'hector','template':'phoenix','recipients':['bnp','sg','ca']}]},
        {'month':3,'count':1,'slots':[{'requester':'hector','template':'autocall_athena','recipients':['bnp','sg','ca']}]}]
    components=len(sys.argv)==3 and sys.argv[1]=='--components'
    if len(sys.argv)==3 and sys.argv[1] in {'--resume','--components'}:
        directory=Path(sys.argv[2]).resolve()
        if not directory.is_relative_to((ROOT/'.runtime'/'diagnostic-acceptance').resolve()):
            raise ValueError('La reprise doit désigner une recette isolée identifiée.')
        store=Store(directory.parent);state=store.load(directory.name);config=state['config']
        if components:
            copied=root/directory.name
            shutil.copytree(directory,copied)
            directory=copied;store=Store(root)
            for name in ('pricing','documents','optimizer','screens','valuations','ccr'):
                state['coverage_matrix'][name]={'status':'NOT_TESTED','evidence':[]}
            state['incidents']=[]
    else:
        store=Store(root);state=store.create(CampaignConfig(**config),1);directory=store.path(state['id'])
    instances=Instances(directory,state)
    tools=None
    baseline=instances.baseline()
    existing=ROOT/'.runtime'/'hybrid-saas'/'admin-workbench'/'campaigns'/'_baselines'/baseline.name
    if not baseline.exists() and existing.exists():
        shutil.copytree(existing,baseline)
    report={'started_at':datetime.now(timezone.utc).isoformat(),'path':str(directory),'model_calls':0,'checks':[]}
    try:
        instances=Instances(directory,state)
        instances.start(only={'leonteq','hector'} if components else None)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            tools=Tools(directory,state,browser,instances.provision_owner)
            for key in state['actors']:
                if key!='achille' and (not components or key in {'leonteq','hector'}):tools.connect(key,instances.ensure_identity(key))
            if components:
                tools.recover_workflow()
                tools.relationship('leonteq','bnp',otc=True)
                for month in (3,6):
                    state['month']=month;state['business_date']=(date.fromisoformat(config['start_date'])+relativedelta(months=month)).isoformat()
                    clock_file(directory,state['business_date'])
                    tools.review('leonteq')
                report['checks'].append({'two_quarterly_mtms':state['usage'].get('mtms',0)})
            for key,policy in participants(config).items():
                if components:continue
                for peer in state['actors']:
                    if peer not in {key,'achille'}:
                        tools.relationship(key,peer,otc=False)
                if policy['request_rfq']:
                    tools.relationship('client',key);tools.crm(key)
            if not state['cases']:report['checks'].append({'empty_first_month':True})
            for task in schedule(config):
                if components:continue
                state['month']=task['month']
                state['business_date']=adjust(date.fromisoformat(config['start_date'])+relativedelta(months=task['month']),'EUR',BusinessDayConvention.FOLLOWING).isoformat()
                clock_file(directory,state['business_date'])
                case_id=task['id'];sender=task['requester']
                previous=next((c for c in check_books(state) if c['case_id']==case_id),None)
                if previous and previous['status']=='COMPLETE':
                    report['checks'].append({'case':case_id,'template':task['template'],'reused_completed':True,'reconciliation':previous})
                    continue
                tools.request('client',task['template'],task['product']['coupon_percent'],60,_task=task)
                if case_id==schedule(config)[0]['id']:
                    relation=tools.relation('bnp',sender)
                    original={k:v for k,v in relation.items() if k not in {'id','version'}}
                    suspended=tools.api('bnp','PUT',f"/api/trading/relationships/{relation['id']}",dict(original,status='SUSPENDED',expected_version=relation['version']))
                    try:
                        tools.eligible('bnp',sender)
                        raise AssertionError('La relation suspendue a été acceptée')
                    except ValueError as exc:
                        assert 'EXPECTED_REFUSAL' in str(exc)
                        report['checks'].append({'legal_refusal':'EXPECTED_REFUSAL','actor':'bnp','created_counterparty':False})
                    tools.api('bnp','PUT',f"/api/trading/relationships/{relation['id']}",dict(original,expected_version=suspended['version']))
                tools.rfq(sender,case_id)
                offers=[]
                for bank in task['recipients']:
                    target=(next(p for p in config['participants'] if p['key']==bank)['economy'] or config['economy_common'])['margin_target_bps']
                    offers.append(tools.quote(bank,case_id,target))
                assert all(state['actors'][q['bank']]['prices'][case_id]['funding_curve'] for q in offers)
                quote=min(offers,key=lambda q:q['price'])
                if case_id not in state['client_offers']:
                    tools.offer(sender,quote['id'],40,'Comparaison des cotations natives sur des termes identiques.')
                if case_id not in state['client_acceptances']:
                    tools.client_accept('client',case_id,True,'Recette : termes et risque compris.')
                if case_id not in state['accepted']:
                    tools.accept_quote(sender,quote['id'],'Recette : cotation retenue après comparaison.')
                if not state['cases'][case_id].get('bank_confirmation'):
                    tools.confirm_trade(quote['bank'],case_id)
                if not state['cases'][case_id].get('trade_confirmed'):
                    tools.confirm_trade(sender,case_id)
                if case_id==schedule(config)[0]['id']:
                    bank=quote['bank'];relation=tools.relation(bank,sender)
                    original={k:v for k,v in relation.items() if k not in {'id','version'}}
                    limited=tools.api(bank,'PUT',f"/api/trading/relationships/{relation['id']}",dict(original,gross_notional_limit=1,expected_version=relation['version']))
                    before=len(state['actors'][bank]['deals'])
                    try:
                        tools.book(bank,case_id,'BANK_SELL')
                        raise AssertionError('Le dépassement de limite a été accepté')
                    except ValueError as exc:
                        assert 'HTTP 422' in str(exc) and 'Limite' in str(exc),str(exc)
                        assert len(state['actors'][bank]['deals'])==before
                        report['checks'].append({'notional_limit':'EXPECTED_REFUSAL','actor':bank,'no_booking_created':True})
                    tools.api(bank,'PUT',f"/api/trading/relationships/{relation['id']}",dict(original,expected_version=limited['version']))
                for actor,leg in ((quote['bank'],'BANK_SELL'),(sender,'HECTOR_BUY'),(sender,'HECTOR_SELL'),('client','CLIENT_BUY')):
                    tools.book(actor,case_id,leg);tools.settle(actor)
                check=next(c for c in check_books(state) if c['case_id']==case_id)
                assert check['status']=='COMPLETE',check
                count=len(state['actors'][sender]['deals'])
                tools.book(sender,case_id,'HECTOR_BUY')
                assert len(state['actors'][sender]['deals'])==count
                report['checks'].append({'case':case_id,'template':task['template'],'requester':sender,'reconciliation':check,'quotes':len(offers)})
                print(json.dumps(report['checks'][-1]),flush=True)
            before=state['usage'].get('mtms',0)
            if not components:state['month']=2
            for key,actor in state['actors'].items():
                if not components and key!='achille' and actor['deals']:tools.review(key)
            assert state['usage'].get('mtms',0)==before,'MTM non trimestriel exécuté'
            from app.services.agent_workshop.coverage import exercise
            # One quarterly stop plus the final cutoff, not sixty repeated months.
            for day,month in (('2022-01-14',3),(config['end_date'],60)):
                state['business_date']=day;state['month']=month;clock_file(directory,day)
                for key,actor in state['actors'].items():
                    if key!='achille' and actor['deals']:
                        tools.review(key)
                if month==3:exercise(CoverageController(state,store),tools)
            report['checks'].append({'historical_cutoff':state['business_date'],'remaining_active':{k:a.get('last_review',{}).get('active_deals',0) for k,a in state['actors'].items()},'market_sources':state.get('market_sources')})
            assert state['business_date']==config['end_date']
            assert not any(row['status']=='FAILED' for row in state['coverage_matrix'].values()),state['incidents']
            report['coverage']={k:{'status':r['status'],'remaining':r.get('remaining')} for k,r in state['coverage_matrix'].items()}
            report['configuration_ui']=check_configuration(tools,state,directory)
            report['status']='PASS';tools.close();tools=None;browser.close()
    except Exception as exc:
        report.update(status='FAIL',error=str(exc));raise
    finally:
        if tools:
            try:tools.close()
            except Exception as exc:report['browser_cleanup_error']=str(exc)
        instances.stop();store.save(state)
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (directory/('acceptance-'+uuid4().hex+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        report['cleanup']={'remaining_owned_processes':state['processes'],'all_actors_offline':all(not a.get('online') for a in state['actors'].values())}
        (directory/'acceptance-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['--ui']:run_ui()
    else:run()
