"""Qualify note issuance through the normal UI in private installations."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['STRUCTURA_DATA_DIR']=tempfile.mkdtemp(prefix='structura-trading-ui-')
os.environ['STRUCTURA_DISABLE_SCHEDULER']='1'
from backend.app.services.agent_workshop.store import store,CampaignConfig
from backend.app.services.agent_workshop.instances import Instances
from backend.app.services.agent_workshop.tools import Tools
from playwright.sync_api import sync_playwright


def main():
    state=store.create(CampaignConfig(months=1,include_sg=False),1)
    state['actors']={k:v for k,v in state['actors'].items() if k in {'hector','client','achille'}}
    directory=store.path(state['id']);instances=Instances(directory,state)
    print('EVIDENCE_DIR',directory,flush=True)
    try:
        instances.start()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            tools=Tools(directory,state,browser,instances.provision_owner)
            try:
                for actor in ('hector','client'):tools.register(actor)
                page=tools.page('hector');errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(state['actors']['hector']['url']+'/#/trading')
                page.get_by_role('heading',name='Relations et exécutions').wait_for()
                cp=tools.cpty('hector','client')
                page.get_by_label('Contrepartie').select_option(str(cp['id']))
                page.get_by_label('Référence',exact=True).fill('REL-UI-ISSUANCE')
                page.get_by_label('État').select_option('ACTIVE')
                page.get_by_label('Date d’effet',exact=True).fill(state['business_date'])
                page.get_by_label('Documentation / accord signé',exact=True).fill('Programme de notes fictif — recette UI')
                with page.expect_response(lambda r:'/api/trading/relationships' in r.url and r.request.method=='POST') as created:
                    page.get_by_role('button',name='Enregistrer',exact=True).click()
                assert created.value.status==201,created.value.text()
                relation=created.value.json()
                tools.crm('hector')
                proposal=tools.propose('hector','phoenix',8,60,'Coupon conditionnel, diversification et risque émetteur à discuter avec le client.')
                assert proposal['status']=='IDEA_NOT_PRICED'
                case_id=tools.request('client')['case_id'];case=state['cases'][case_id];price=case['pricing']
                globals_data={'r':price['r']*100,'T':price['T'],'N':2000,'seed':42,'model':'constant','deal_ccy':'EUR',
                    'nominal':1000000,'valuation_date':state['business_date'],'trade_date':state['business_date'],
                    **{k:price[k] for k in ('strike_date','value_date','maturity_date','payment_date')},
                    'underlyings':[{**u,'sigma':u['sigma']*100,'q':u['q']*100} for u in price['underlyings']],
                    'corr_matrix':[[1]],'funding':{'enabled':False},'yield_curve_enabled':False}
                saved=tools.api('hector','POST','/api/db/scripts',{'name':'Recette émission UI','script_text':price['script'],
                    'params_json':json.dumps({'COUPON':8,'M_KI_BAR':60}),'constats_json':json.dumps(price['constats']),
                    'global_params_json':json.dumps(globals_data)})
                page.goto(state['actors']['hector']['url']+'/#/pricer/'+str(saved['id']))
                with page.expect_response(lambda r:r.url.endswith('/api/price') and r.request.method=='POST',timeout=90000) as priced:
                    page.get_by_role('button',name='▶ Pricer',exact=True).click()
                assert priced.value.status==200,priced.value.text()
                page.get_by_role('button',name='📋 Deal',exact=True).click()
                def field(label,tag='input'):
                    return page.locator('label').filter(has_text=label).locator('..').locator(tag).first
                field('Contrepartie','select').select_option(state['actors']['client']['entity'])
                page.get_by_role('button',name='↓ Achat — la banque achète, nous vendons',exact=True).click()
                field('Appellation / variante du produit').fill('Reverse convertible — émission Hector')
                field('Format juridique').fill('EMTN');field('Instrument').fill('Note')
                field('Famille de payoff','select').select_option(label='Reverse convertible')
                page.get_by_placeholder('Term sheet / ISDA / confirmation').fill(relation['documentation_reference'])
                field('Trade date').fill(state['business_date'])
                field('Prix traité (%)').fill('101')
                page.get_by_label('Inscrire une exécution de note dans le journal des relations').check()
                page.get_by_label('Relation active avec la contrepartie').select_option(str(relation['id']))
                page.get_by_placeholder('Nom exact de l’entité émettrice').fill('Maison Hector')
                page.get_by_placeholder('ISIN ou référence commune aux livres').fill('NOTE-UI-HECTOR')
                page.get_by_placeholder('Même référence chez les deux intervenants').fill('TRADE-UI-HECTOR')
                page.get_by_role('button',name='📋 Vérifier les paramètres et booker',exact=True).click()
                with page.expect_response(lambda r:r.url.endswith('/api/trading/book-note') and r.request.method=='POST',timeout=30000) as booked:
                    page.get_by_role('button',name='Confirmer le booking',exact=True).click()
                assert booked.value.status==201,booked.value.text()
                execution=booked.value.json()
                assert execution['our_side']=='SELL' and execution['issuer']=='Maison Hector'
                page.get_by_text('✓ Deal booké',exact=False).wait_for()
                page.screenshot(path=str(directory/'screenshots'/'native-ui-booking.png'))
                page.goto(state['actors']['hector']['url']+'/#/trading')
                page.get_by_placeholder('Référence de la preuve').fill('RECETTE-UI-DVP-HECTOR')
                with page.expect_response(lambda r:'/settle' in r.url and r.request.method=='POST') as settled:
                    page.get_by_role('button',name='Confirmer le règlement',exact=True).click()
                assert settled.value.status==200,settled.value.text()
                page.get_by_text('RECETTE-UI-DVP-HECTOR',exact=True).wait_for()
                page.screenshot(path=str(directory/'screenshots'/'native-ui-journal.png'))
                positions=tools.api('hector','GET','/api/trading/positions')
                assert positions['positions'][0]['nominal']==-1000000
                assert not errors,errors
                print('TRADING_UI_CHECK_OK',execution['deal_reference'],positions,flush=True)
            except Exception:
                tools.page('hector').screenshot(path=str(directory/'screenshots'/'native-ui-error.png'),full_page=True)
                raise
            finally:tools.close();browser.close()
    finally:instances.stop();store.save(state)


if __name__=='__main__':main()
