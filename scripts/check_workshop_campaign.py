"""Verify a finished real-agent campaign against its isolated native databases.

Read-only: no agent decisions, business writes, resumptions or synthetic results.
The optional report is a qualification artifact, not a campaign state mutation.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.core.rfq_controls import product_terms, product_terms_hash
from backend.app.services.agent_workshop.reconciliation import check_books
from backend.app.services.agent_workshop.store import source_manifest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(directory, main_db_sha256=None):
    directory = directory.resolve()
    state = json.loads((directory / 'campaign.json').read_text(encoding='utf-8'))
    native = deepcopy(state)
    validations, installations = [], {}

    def check(name, passed, detail=''):
        validations.append({'criterion': name, 'passed': bool(passed), 'detail': detail})

    check('Campagne terminée sur toute sa période', state['status']=='COMPLETED' and state['month']==state['config']['months'])
    check('Une seule exécution vierge, sans reprise humaine', len(state.get('run_manifests',[]))==1
          and not state.get('last_control_id') and not (directory/'control.json').exists())
    manifests=state.get('run_manifests') or [{}]
    check('Code métier identique du démarrage à la qualification', manifests[0].get('source_sha256')==source_manifest()['source_sha256'])
    decisions = [a for a in state['actions'] if a['status'] in {'SUCCESS','EXPECTED_REFUSAL'}]
    check('Chaque action réussie provient du modèle réel', bool(decisions) and all(
        a.get('model',{}).get('model')==state['config']['model']
        and a['model'].get('input_tokens',0)>0 and a['model'].get('output_tokens',0)>0 for a in decisions))
    check('Aucun échec opérationnel non attendu', not any(a['status']=='FAILED' for a in state['actions']))
    check('Contrôleur et installations fermés', not state['processes'] and state.get('activity') is None)
    for key, actor in state['actors'].items():
        if key=='achille':
            continue
        database = (directory/'instances'/key/'structura.db').resolve()
        if not database.is_relative_to(directory/'instances'):
            raise ValueError('Base native hors des installations isolées.')
        with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as connection:
            connection.row_factory = sqlite3.Row
            def rows(table):
                return [dict(r) for r in connection.execute(f'SELECT * FROM {table}')]
            deals = {r['id']:r for r in rows('deals')}
            executions = rows('trading_executions')
            valuations = rows('valuation_runs')
            fixings = rows('official_fixing_versions')
            proposals = rows('lifecycle_proposals')
            events = rows('deal_events')
            audits = rows('audit_events')
            users = rows('users')
        check(f'{key} : compte créé par écran et décisions IA', actor['registered'] and any(
            a['actor']==key and a['tool']=='register' and a['status']=='SUCCESS' and a['channel']=='UI' for a in decisions))
        check(f'{key} : écritures natives sans deal orphelin', len(deals)==len(executions)
              and all(d['product_id'] is not None and d['product_terms_version'] is not None for d in deals.values()))
        native_rows = []
        local_by_id = {r['id']:r for r in actor['deals']}
        for execution in executions:
            deal = deals[execution['deal_id']]
            inputs = json.loads(deal['market_snapshot_json'] or '{}')
            terms = product_terms(deal['script_snapshot'], inputs.get('pricing_input') or inputs)
            terms.update(currency=deal['devise'], strike_date=deal['strike_date'], maturity_date=deal['maturity_date'],
                         payment_date=deal['payment_date'], transaction_format=deal['transaction_format'])
            local = local_by_id.get(execution['id'], {})
            native_rows.append({**local, **execution, 'nominal':deal['nominal'], 'currency':deal['devise'],
                'price_traded':deal['price_traded'], 'counterparty':deal['contrepartie'], 'value_date':deal['value_date'],
                'contract_hash':product_terms_hash(terms), 'status':deal['status']})
        native['actors'][key]['deals'] = native_rows
        check(f'{key} : journal pilote exhaustif face au journal natif', set(local_by_id)=={r['id'] for r in executions})
        check(f'{key} : règlements initiaux prouvés', all(r['settlement_status']=='SETTLED' and r['settlement_reference'] for r in executions))
        if deals:
            review = actor.get('last_review',{})
            check(f'{key} : suivi à la dernière date du jeu', review.get('date')==state['business_date'] and review.get('deals')==len(deals))
            check(f'{key} : valorisations natives archivées pour chaque deal', set(deals)<={r['deal_id'] for r in valuations})
            due = [e for e in events if e['event_date']<=state['business_date'] and e['status']!='annulé']
            check(f'{key} : constatations échues traitées', all(e['fixing_status'] in {'VALIDATED','APPLIED'} for e in due))
            check(f'{key} : flux et clôtures des maturités payées', all(d['realized_payout'] is not None
                  and d['status'] not in {'actif','en_reglement'} for d in deals.values() if d['payment_date']<=state['business_date']))
        official = [f for f in fixings if f['status'] in {'VALIDATED','APPLIED'}]
        check(f'{key} : provenance synthétique explicite des fixings officiels', all(
            f['external_reference'].startswith('SYNTHETIC_SCENARIO:'+state['id']+':') and f['record_sha256'] for f in official))
        port = int(actor['url'].rsplit(':',1)[1])
        with socket.socket() as sock:
            sock.settimeout(.5)
            check(f'{key} : port privé libéré', sock.connect_ex(('127.0.0.1',port))!=0)
        installations[key] = {
            'database_sha256':digest(database), 'executions':len(executions),
            'deals_by_status':dict(Counter(d['status'] for d in deals.values())),
            'valuation_runs':len(valuations), 'official_fixings':len(official),
            'applied_lifecycle_proposals':sum(p['status']=='APPLIED' for p in proposals),
            'audit_events':len(audits), 'agent_user_ids':[u['id'] for u in users if u['username']=='agent_'+key],
            'resolved_payouts':[{'deal_id':d['id'],'realized_payout':d['realized_payout'],'outcome':d['resolution_outcome']}
                                for d in deals.values() if d['realized_payout'] is not None],
        }
    books = check_books(native)
    check('Tous les dossiers clos : quatre jambes rapprochées ou refus commercial explicite', bool(books)
          and len(books)==state['config']['months'] and all(b['status'] in {'COMPLETE','NO_TRADE'} for b in books))
    complete = [b for b in books if b['status']=='COMPLETE']
    check('Au moins un booking complet, sans volume forcé', bool(complete))
    check('Suivi de vie exercé avec valorisations, fixings et résolutions natives',
          sum(i['valuation_runs'] for i in installations.values())>0
          and sum(i['official_fixings'] for i in installations.values())>0
          and sum(i['applied_lifecycle_proposals'] for i in installations.values())>0)
    if main_db_sha256:
        check('Base utilisateur intacte', digest(ROOT/'backend/data/structura.db')==main_db_sha256.lower())
    return {'campaign_id':state['id'],'qualified_at':datetime.now(timezone.utc).isoformat(),
        'passed':all(v['passed'] for v in validations),'validations':validations,
        'months':state['config']['months'],'business_date':state['business_date'],
        'volume':sum(b['client_volume'] for b in books),'completed_cases':len(complete),
        'no_trade_cases':len(books)-len(complete),'turns':state['turns'],'usage':state['usage'],
        'actions_by_status':dict(Counter(a['status'] for a in state['actions'])),
        'incidents':len(state['incidents']),'book_checks':books,'installations':installations}


def main():
    parser=argparse.ArgumentParser(description='Qualification native d’une campagne IA terminée')
    parser.add_argument('directory',type=Path)
    parser.add_argument('--main-db-sha256')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=qualify(args.directory,args.main_db_sha256)
    if args.report:
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['passed'] else 2


if __name__=='__main__':
    sys.exit(main())
