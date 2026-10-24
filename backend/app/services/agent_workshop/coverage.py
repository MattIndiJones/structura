"""Bounded native checks, with honest evidence and no code repair during a run."""
from datetime import date
import json
from uuid import uuid5, NAMESPACE_URL

from .configuration import PAYOFFS


class IntegrityError(ValueError):
    pass


def exercise(manager, tools):
    state = manager.live
    matrix = state['coverage_matrix']
    example = next((c for c in state['cases'].values() if c.get('trade_confirmed')), None)
    if not example:
        return
    key = example['requester']
    actor = state['actors'][key]
    deal = next((d for d in actor['deals'] if d['case_id']==example['id'] and d['leg']=='HECTOR_BUY'), None)
    if not deal:
        return
    raw = json.loads((tools.directory/'instances'/key/'pricing'/(example['id']+'.json')).read_text(encoding='utf-8'))
    payload = raw['input']
    def get(path):
        return tools.api(key,'GET',path)
    def post(path, body):
        return tools.api(key,'POST',path,body)
    def products():
        from ...core.product.models import ProductTerms
        product = get(f"/api/products/{example['native_products'][key]}")
        if product['terms_version'] != example['native_terms_version'] or ProductTerms.model_validate(product['terms']).fingerprint != example['terms_fingerprint']:
            raise IntegrityError('Les termes Product exécutés ont changé.')
        return {'product_id':product['product_id'], 'terms_version':product['terms_version'], 'scripts':get('/api/db/scripts')}
    def documents():
        kid = post('/api/kid/compute', {**payload,'N':1000})
        emt = post('/api/emt/compute', {**payload,'sri':kid['sri'],'mrm':kid['mrm'],'crm':kid.get('crm',3),
                                     'capital_protection_level_pct':0,'capital_protection_condition':'conditional'})
        saved = post('/api/kid/save', {**{k:v for k,v in kid.items() if k in {'sri','mrm','crm','vev','T_rhp','horizons','costs'}},
                                      'deal_id':deal['deal_id'],'product_title':example['id']})
        return {'kid':kid,'emt':emt, 'kid_record':saved,'scope':'Calcul KID/EMT et archive KID ; aucune synthèse IA'}
    def risk():
        from .configuration import funding_at
        quote = next(q for q in state['quotes'] if q['id']==state['accepted'][example['id']])
        curve, _ = funding_at(state['config'], quote['bank'], state['month'])
        body = {'valuation_date':state['business_date'],'recalibrate':'none','funding_curve':curve,
                'funding_source_reference':f"SCENARIO:{state['id']}:{quote['bank']}:{state['business_date']}"}
        greeks = post(f"/api/deals/{deal['deal_id']}/greeks?n_paths=1000", body)
        exposure = get('/api/portfolios/exposure-by-counterparty')
        stress = post(f"/api/deals/{deal['deal_id']}/shock?n_paths=1000", {**body,'spot_shock_pct':-20,'vol_shock_pts':5})
        return {'greeks':greeks,'exposure':exposure,'stress':stress,'commentary_ia':False}
    def ccr():
        eligible = next(iter(actor.get('otc_sets',{})), None)
        if not eligible:
            return {'not_applicable':True,'reason':'Aucun accord OTC utilisable ; les notes restent hors netting OTC.'}
        result=tools.risk(key,example['id'],eligible)
        if result['status']!='CALCULATED':
            raise ValueError('CCR non calculé : '+str(result.get('errors') or result['status']))
        return result
    def optimizer():
        ul = payload['underlyings'][0]
        catalog=get('/api/admin/underlyings')
        reference=next((u for u in catalog if u['ticker']==ul['ticker'] and u['active']),None)
        from ...db.underlyings_seed import seeded_asset_class
        kind=(reference or {}).get('asset_class')
        kind=kind if kind in {'equity','index'} else seeded_asset_class(ul['ticker'])
        if not reference or kind not in {'equity','index'}:
            return {'not_applicable':True,'reason':'Sous-jacent non qualifié dans le catalogue natif pour l’Optimizer.'}
        day = state['business_date']
        optimization = {'product_family':'autocall_athena','objective':'maximize_coupon','model':'constant',
            'currency':'EUR','strike_date':day,'convention':'modified_following',
            'market':{'as_of':day,'rate':.025,'underlyings':[{'ticker':ul['ticker'],'name':ul['name'],'asset_type':kind,'currency':'EUR','sigma':.23,'q':.02}], 'correlation':[[1]]},
            'ranges':{'maturity_months':{'minimum':12,'maximum':12,'step':12},
                      'protection_barrier':{'minimum':.6,'maximum':.6,'step':.05},
                      'autocall_trigger':{'minimum':1,'maximum':1,'step':.05},'observation_months':[12]},
            'search':{'simulations':1000,'max_candidates':1,'parallel_workers':1,'max_seconds':30}}
        estimate = post('/api/product-optimizer/estimate-search',optimization)
        research = post('/api/product-optimizer/researches',{'optimization':optimization,
                        'title':'Recette ciblée '+example['id'],'intention':'Vérifier un candidat et son archivage, sans décision de vente.',
                        'command_key':state['id']+'-OPTIMIZER'})
        identity = research.get('research_id') or research.get('id')
        result = tools.network.wait(lambda:get('/api/product-optimizer/researches/'+identity),
                                    lambda r:r.get('status') in {'COMPLETED','PARTIAL','FAILED','INTERRUPTED'}, timeout=50)
        if result['status']=='FAILED':
            raise ValueError('La recherche native a échoué : '+str(result.get('error')))
        return {'estimate':estimate,'research':result,'scope':'Un candidat Athena et relecture de recherche.'}
    def reinvestment():
        from ...core.schemas import ReinvestScanRequest
        ul=payload['underlyings'][0]
        if len(payload['underlyings'])!=1:
            return {'not_applicable':True,'reason':'Le scan natif v1 est mono-actif.'}
        request = ReinvestScanRequest(candidates=[{'ticker':ul['ticker'],'name':ul['name']}],param_name='COUPON',
                                      target_price=1,lo=0,hi=.30,N=1000,model='constant')
        result = post(f"/api/deals/{deal['deal_id']}/reinvest/scan",request.model_dump())
        return {'scan':result,'scope':'Une alternative ; aucun nouvel RFQ ni booking hors calendrier.'}
    def valuations():
        runs=get(f"/api/deals/{deal['deal_id']}/valuation-runs?run_type=MTM")
        compatible=runs
        if len(compatible)<2:
            return {'pending':True,'reason':'Deux MtM enregistrés nécessaires, sans pricing supplémentaire.'}
        note=post('/api/valuation-notes',{'deal_id':deal['deal_id'],'run_ids':[r['id'] for r in compatible[:2]],
                                         'request_key':str(uuid5(NAMESPACE_URL,state['id']+'-VALUATION-NOTE'))})
        return {'runs':runs,'note':note,'scope':'Deux calculs existants et note Valo Explain.'}
    def screens():
        evidence = []
        page = tools.page(key)
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        for route in ('/clients/liste','/products','/pricer','/rfq','/rfq/recues','/booking','/risk','/risk/ccr','/structuring/optimizer','/admin'):
            page.goto(actor['url']+'/#'+route)
            headings={'/clients/liste':'Clients','/products':'Mes Produits','/pricer':'Pricer',
                      '/rfq':'RFQ Fournisseurs','/rfq/recues':'RFQ reçues','/booking':'Booking',
                      '/risk':'Risk','/risk/ccr':'CCR','/structuring/optimizer':'Optimizer','/admin':'Administration'}
            page.wait_for_function("([route,heading]) => location.hash === '#'+route && Array.from(document.querySelectorAll('h1,h2,button')).some(h=>h.innerText.includes(heading)) && !Array.from(document.querySelectorAll('main')).some(m=>m.innerText.includes('Chargement…'))",arg=[route,headings[route]],timeout=15000)
            text = page.locator('#app > div > div.flex-1').first.inner_text()
            if not text.strip() or 'Internal Server Error' in text:
                raise ValueError('Écran vide ou erreur serveur : '+route)
            image = tools.screenshot(key)
            evidence.append({'route':route,'screenshot':image,'visible_text':text[:700]})
        if errors:
            raise ValueError('Erreurs Vue : '+'; '.join(errors))
        return {'screens':evidence,'scope':'Chargement visuel et erreurs JS ; ergonomie détaillée à qualifier humainement.'}
    recipes = {
        'clients':lambda:{'client':get(f"/api/clients/{actor['crm']['client_id']}"),'crm':actor['crm']},
        'products':products,
        'pricing':lambda:post('/api/profile',payload),
        'rfq':lambda:get(f"/api/rfq/{example['rfq_id']}"),
        'booking':lambda:{'executions':get('/api/trading/executions'),'reconciliation':state.get('book_checks')},
        'risk':risk, 'ccr':ccr, 'documents':documents,
        'valuations':valuations, 'optimizer':optimizer, 'reinvestment':reinvestment,
        'administration':lambda:{'users':get('/api/admin/users'),'desks':get('/api/rfq-desks/admin'),'counterparties':get('/api/admin/counterparties')},
        'screens':screens,
    }
    # End-to-end business adapters can only claim the exact scenarios performed.
    for module, row in matrix.items():
        if manager.consume_command() or row['status']!='NOT_TESTED':
            continue
        if module=='lifecycle':
            if not any(a.get('last_review',{}).get('fixings') for a in state['actors'].values()):
                continue
            row.update(status='EXERCISED',evidence=[{'fixings':a['last_review']['fixings'],'actor':k} for k,a in state['actors'].items() if a.get('last_review',{}).get('fixings')]); manager.persist(); continue
        tools.calls=[]
        manager.begin_activity(key,'EXECUTING',tasks=['Recette ciblée : '+module])
        try:
            result = recipes[module]()
            if isinstance(result,dict) and result.get('pending'):
                row['remaining']=result['reason']; manager.persist(); continue
            row.update(status='NOT_APPLICABLE' if isinstance(result,dict) and result.get('not_applicable') else 'EXERCISED',
                       date=state['business_date'],actor=key,evidence=[{'result':result,'http_calls':tools.calls[:]}])
        except Exception as exc:
            incident = manager.incident(key,'BUG',str(exc))
            incident.update(module=module,severity='BLOCKING' if isinstance(exc,IntegrityError) else 'NON_BLOCKING',expected='Scénario natif représentatif utilisable',
                            observed=str(exc),reproduction={'case_id':example['id'],'deal_id':deal['deal_id']},http_calls=tools.calls[:])
            row.update(status='FAILED',incident_id=incident['id'],date=state['business_date'],evidence=[{'http_calls':tools.calls[:]}])
            if isinstance(exc,IntegrityError):
                state['status']='ATTENTION';state['stop_reason']={'kind':'BLOCKING_ERROR','incident_id':incident['id']}
                manager.persist();return
        manager.persist()
