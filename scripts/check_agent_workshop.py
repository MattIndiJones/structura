"""Qualify real HTTP/browser adapters, independently of AI commercial decisions.

Uses fresh disposable instances; never opens the user's Structura database.
Run from repository root: .venv/Scripts/python.exe scripts/check_agent_workshop.py
"""
import json
import argparse
from datetime import date
from dateutil.relativedelta import relativedelta
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['STRUCTURA_DATA_DIR'] = tempfile.mkdtemp(prefix='structura-adapter-check-')
os.environ['STRUCTURA_DISABLE_SCHEDULER'] = '1'
from backend.app.services.agent_workshop.store import store, CampaignConfig
from backend.app.services.agent_workshop.instances import Instances, clock_file
from backend.app.services.agent_workshop.tools import Tools
from backend.app.services.agent_workshop.engine import check_books
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--template',choices=['reverse_convertible','phoenix'],default='reverse_convertible')
    parser.add_argument('--with-sg',action='store_true',help='Qualify a justified choice of the more expensive bank')
    args=parser.parse_args()
    state = store.create(CampaignConfig(months=12, include_sg=args.with_sg), 1)
    directory = store.path(state['id'])
    instances = Instances(directory, state)
    print('EVIDENCE_DIR', directory, flush=True)
    try:
        instances.start()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            tools = Tools(directory, state, browser, instances.provision_owner)
            def action(actor, name, args=None):
                result = tools.execute(actor, name, args or {})
                print(actor, name, json.dumps(result, ensure_ascii=True)[:600], flush=True)
                store.save(state)
                return result
            try:
                for actor in [k for k in state['actors'] if k!='achille']:
                    action(actor, 'register')
                parties=[('hector','bnp'),('hector','ca'),('hector','client'),('bnp','hector'),('ca','hector'),('client','hector')]
                if args.with_sg:parties += [('hector','sg'),('sg','hector')]
                for actor, party in parties:
                    initial=action(actor, 'relationship', {'party':party, 'otc':False})
                    if actor in {'bnp','sg'} or party in {'bnp','sg'}:
                        upgraded=action(actor,'relationship',{'party':party,'otc':True})
                        assert upgraded['id']==initial['id'] and upgraded['version']==initial['version']+1 and upgraded['otc_allowed']
                        repeated=action(actor,'relationship',{'party':party,'otc':True})
                        assert repeated['id']==upgraded['id'] and repeated['version']==upgraded['version']
                        cp=tools.cpty(actor,party)
                        config=tools.api(actor,'GET',f"/api/ccr/counterparties/{cp['id']}/configuration")
                        assert all(len(config[k])==1 for k in ('agreements','csas','netting-sets')),config
                action('hector','crm')
                case = action('client','request',{'template':args.template})['case_id']
                action('hector','rfq',{'case_id':case})
                try:
                    action('ca','quote',{'case_id':case})
                    raise AssertionError('Missing documentation must refuse pricing')
                except ValueError as exc:
                    assert 'EXPECTED_REFUSAL' in str(exc)
                quote = action('bnp','quote',{'case_id':case, 'margin_bps':30})
                selected='bnp'
                if args.with_sg:
                    expensive=action('sg','quote',{'case_id':case,'margin_bps':80})
                    assert expensive['price']>quote['price']
                    quote=expensive;selected='sg'
                risk = action('bnp','risk',{'case_id':case,'party':'hector','spread_bps':100,'recovery':.4})
                assert risk['status']=='CALCULATED' and risk['after']['pfe95'] is not None, risk
                justification='Banque plus chère retenue : diversification émetteur et qualité de service documentée' if args.with_sg else 'Prix ferme et documentation complète'
                action('hector','offer',{'quote_id':quote['id'], 'justification':justification})
                action('client','client_accept',{'case_id':case})
                action('hector','accept_quote',{'quote_id':quote['id'], 'justification':justification})
                rfq=tools.api('hector','GET',f"/api/rfq/{state['cases'][case]['rfq_id']}")
                assert rfq['selection_reason_note']==justification
                for actor,leg in [(selected,'BANK_SELL'),('hector','HECTOR_BUY'),('hector','HECTOR_SELL'),('client','CLIENT_BUY')]:
                    action(actor,'book',{'case_id':case,'leg':leg})
                opportunity_id=state['cases'][case]['opportunity_id']
                opportunity=tools.api('hector','GET',f'/api/opportunities/{opportunity_id}')
                assert opportunity['status']=='partially_won',opportunity
                sales=[d for d in state['actors']['hector']['deals'] if d['leg']=='HECTOR_SELL']
                sale=tools.api('hector','GET',f"/api/deals/{sales[0]['deal_id']}")
                assert sale['opportunity_id']==opportunity_id
                for actor in (selected,'hector','client'):
                    action(actor,'settle')
                    action(actor,'review')
                checks=check_books(state)
                assert checks[0]['status']=='COMPLETE', checks
                for month in (3,6,7,12):
                    state['business_date']=(date.fromisoformat(state['config']['start_date'])+relativedelta(months=month)).isoformat()
                    clock_file(directory,state['business_date'])
                    for actor in (selected,'hector','client'):
                        action(actor,'review')
                assert all(d['status'] not in {'actif','en_reglement'} for a in state['actors'].values() for d in a['deals']), 'Notes still active after payment'
                print('ADAPTER_CHECK_OK', checks, flush=True)
            finally:
                tools.close(); browser.close()
    finally:
        instances.stop(); store.save(state)


if __name__ == '__main__':
    main()
