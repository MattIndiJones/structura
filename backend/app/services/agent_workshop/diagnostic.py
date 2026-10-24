"""Event-driven diagnostic controller using Structura's ordinary business tools."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import time
from uuid import uuid4

from dateutil.relativedelta import relativedelta

from .configuration import PARTIES, PAYOFFS, participants, schedule, preview, funding_at
from .reconciliation import check_books


def diagnostic_defaults():
    from .store import CampaignConfig
    config = CampaignConfig(schema_version=2, name='Diagnostic Structura — notes sur cinq ans',
                            market_mode='historical', end_date=date.today().isoformat(),
                            start_date=(date.today()-relativedelta(years=5)).isoformat(),
                            provider='openai', model='gpt-6-luna', max_ai_cost_usd=2,
                            max_model_calls=60, max_turns=5000, coaching=False,
                            exploratory_actions=False, contract_scenario='all_complete',
                            payoff_templates=list(PAYOFFS)).model_dump()
    for p in config['participants']:
        if p['key'] in {'bnp','sg','ca'}:
            economy = deepcopy(config['economy_common'])
            shift = {'bnp':0, 'sg':20, 'ca':35}[p['key']]
            economy['funding'][0]['pillars'] = [[t, s+shift] for t,s in economy['funding'][0]['pillars']]
            economy['funding'].append({'month':24,'pillars':[[t,s+(45 if p['key']=='bnp' else -15)] for t,s in economy['funding'][0]['pillars']]})
            economy['funding'].append({'month':60,'pillars':economy['funding'][0]['pillars']})
            economy['margin_target_bps'] = {'bnp':35, 'sg':45, 'ca':25}[p['key']]
            p['economy'] = economy
    return config


def calendar_month(origin, day):
    """Completed calendar periods, including events before the monthly anniversary."""
    months = (day.year-origin.year)*12+day.month-origin.month
    return max(0, months-int(day < origin+relativedelta(months=months)))


def convert_legacy(state):
    config = diagnostic_defaults()
    old = state['config']
    for key in ('name','provider','model','start_date','max_ai_cost_usd','max_model_calls','max_turns','timeout_seconds','seed','coaching'):
        if key in old:
            config[key] = old[key]
    config['name'] += ' — scénario converti'
    for p in config['participants']:
        p['active'] = p['key'] in state['actors']
        p['request_rfq'] = p['key']=='hector'
        p['respond_rfq'] = p['key'] in state['actors'] and state['actors'][p['key']]['role']=='bank'
        p['issue_notes'] = p['respond_rfq']
    templates = old.get('payoff_templates') or ['reverse_convertible','phoenix']
    config['products'] = [{**p, 'nominal':old['ticket'], 'maturity_months':old.get('maturity_months',6)}
                          for p in config['products'] if p['template'] in templates]
    config['calendar'] = [{'month':m+1,'count':1,'slots':[{'requester':'hector','template':templates[m%len(templates)],'recipients':[]}]}
                          for m in range(old['months'])]
    config['horizon_months'] = max(60, old['months'])
    return config


def observation(state, key, tools):
    """Private observations: only the requester sees competing prices."""
    actor = state['actors'][key]
    candidates, available, book_tasks, steps = [], set(), {}, []
    visible = []
    quotes = [q for q in state['quotes'] if key == state['cases'][q['case_id']]['requester'] or key==q['bank']]
    for case in state['cases'].values():
        sender, cid = case['requester'], case['id']
        if key not in {sender,'client',*case['recipients']}:
            continue
        accepted = next((q for q in state['quotes'] if q['id']==state['accepted'].get(cid)), None)
        own = [d['leg'] for d in actor['deals'] if d['case_id']==cid]
        terms = {'coupon_percent':case['pricing']['user_params']['COUPON']*100,
                 'capital_barrier_percent':case['pricing']['user_params']['M_KI_BAR']*100,
                 'maturity_date':case['pricing']['maturity_date'], 'capital_guaranteed':False}
        visible.append({k:case[k] for k in ('id','month','template','nominal','requester','recipients')} | {
            'terms':terms, 'outcome':case.get('outcome'), 'my_booked_legs':own,
            'my_declined':key in case['declines'], 'client_accepted':cid in state['client_acceptances'] if key in {sender,'client'} else None,
            'accepted_quote_id':accepted['id'] if accepted and key in {sender,accepted['bank'],'client'} else None})
        if case.get('outcome') or case['month'] != state['month']:
            continue
        def task(tool, text, leg=None):
            available.add(tool); candidates.append(f'{cid} : {text}')
            steps.append({'tool':tool, 'case_id':cid, **({'leg':leg} if leg else {})})
            if leg:
                book_tasks.setdefault(cid, []).append(leg)
        if key == sender:
            if not case['rfq_sent']:
                task('rfq','Envoyer la RFQ aux destinataires prévus.')
            elif cid not in state['client_offers']:
                if all(b in case['declines'] or any(q['bank']==b and q['case_id']==cid for q in quotes) for b in case['recipients']):
                    task('offer','Comparer les cotations puis proposer une offre motivée au client.')
            elif cid in state['client_acceptances'] and not accepted:
                task('accept_quote','Accepter la cotation liée à l’offre client.')
            elif accepted and not case.get('trade_confirmed'):
                if case.get('bank_confirmation'):
                    task('confirm_trade','Consigner la confirmation bancaire reçue.')
            elif accepted:
                if 'HECTOR_BUY' not in own:
                    task('book','Booker l’achat confirmé.', 'HECTOR_BUY')
                elif 'HECTOR_SELL' not in own:
                    task('book','Booker la distribution au client.', 'HECTOR_SELL')
        elif key == 'client':
            if cid in state['client_offers'] and cid not in state['client_acceptances']:
                task('client_accept','Accepter ou refuser l’offre et expliquer le risque.')
            elif accepted and case.get('trade_confirmed') and 'CLIENT_BUY' not in own:
                task('book','Inscrire l’achat client.', 'CLIENT_BUY')
        elif key in case['recipients']:
            if case['rfq_sent'] and key not in case['declines'] and not any(q['case_id']==cid for q in quotes):
                task('quote','Coter dans RFQ reçues avec la politique privée de marge, ou refuser explicitement.')
                available.add('decline')
            elif accepted and accepted['bank']==key:
                if not case.get('bank_confirmation'):
                    task('confirm_trade','Confirmer explicitement le prix et les termes.')
                elif case.get('trade_confirmed') and 'BANK_SELL' not in own:
                    task('book','Booker la vente bancaire confirmée.', 'BANK_SELL')
    seen = set(actor.get('seen_message_ids', []))
    unread = [m for m in state['messages'] if m['to']==key and m['id'] not in seen]
    policy = funding_at(state['config'], key, state['month'])[1] if key in participants(state['config']) else None
    return {'actor':{k:actor[k] for k in ('id','name','role','goal','registered','relations')},
            'diagnostic':True, 'connected':key in tools.tokens, 'date':state['business_date'], 'month':state['month']+1,
            'available_tools':sorted(available), 'possible_actions':candidates, 'ready_steps':steps, 'cases':visible,
            'quotes':quotes, 'book_tasks':book_tasks, 'correspondents':[k for k in state['actors'] if k!=key],
            'client_offers':{cid:o for cid,o in state['client_offers'].items() if key in {'client',state['cases'][cid]['requester']}},
            'messages':[{k:m[k] for k in ('id','from','subject','body','case_id')} for m in unread[-5:]],
            'last_quantitative_report':actor.get('risk_reports',[])[-1:] or None,
            'private_margin_policy':{k:policy[k] for k in ('margin_min_bps','margin_target_bps','margin_max_bps')} if policy else None,
            'my_last_results':actor['history'][-2:], 'relation_tasks':[], 'solicitations':[]}


def ready_action(state, key, current):
    """Solicit one decision; deterministic transitions retain native checks."""
    step = current['ready_steps'][0]
    tool, cid = step['tool'], step['case_id']
    case = state['cases'][cid]
    if tool in {'quote', 'offer', 'client_accept'}:
        scoped = dict(current)
        scoped.update(available_tools=[tool, 'decline'] if tool=='quote' else [tool],
                      ready_steps=[step], possible_actions=[t for t in current['possible_actions'] if t.startswith(cid+' :')],
                      cases=[c for c in current['cases'] if c['id']==cid],
                      quotes=[q for q in current['quotes'] if q['case_id']==cid],
                      client_offers={c:o for c,o in current['client_offers'].items() if c==cid})
        return tool, {'case_id':cid}, scoped
    args = {k:v for k,v in step.items() if k!='tool'}
    if tool=='accept_quote':
        args = {'quote_id':state['client_offers'][cid]['quote_id'], 'justification':'Offre explicitement acceptée par le client.'}
    return tool, args, None


def review_due(state, actor):
    today = state['business_date']
    active = [d for d in actor['deals'] if d.get('status') in {'actif','en_reglement'}]
    if not active or (actor.get('last_review') or {}).get('date') == today:
        return False
    if not actor.get('last_review'):
        return True
    if state['config'].get('market_mode')=='historical' and state['config'].get('end_date')==today:
        return True
    checkpoint = actor.get('risk_checkpoint') or {}
    if state['config']['cadences']['risk_days']==15:
        if not checkpoint or (date.fromisoformat(today)-date.fromisoformat(checkpoint['date'])).days>=15:
            return True
    elif checkpoint.get('month') != state['month']:
        return True
    if any(today in dates for dates in actor.get('next_event_dates',{}).values()):
        return True
    return any((d.get('settlement_date') or d.get('payment_date','9999-12-31')) <= today
               for d in active if d['status']=='en_reglement')


def checked_action(manager, tools, key, tool, args, reason, model=False, current=None):
    from .brain import decide, Decision, DecisionCancelled
    from .engine import account_model_usage, safe_record
    from .openai_model import BudgetReached, ModelUnavailable
    state = manager.live
    tools.calls = []
    decision = Decision(tool=tool, args=args, reason=reason) if tool and not model else None
    metadata = None
    task_id = f"{state['business_date']}:{key}:{tool or 'decision'}:{args.get('case_id','')}"
    state['checkpoint']['current_task'] = task_id
    try:
        if model:
            current = current or observation(state, key, tools)
            cid = args.get('case_id') or current['ready_steps'][0]['case_id']
            case = state['cases'][cid]
            identity = f"{key}:{cid}:{tool}:{case.get('native_terms_version',1)}:{case.get('terms_fingerprint','')}"
            decisions = state.setdefault('decisions',{})
            previous = decisions.get(identity)
            if previous and previous['status'] in {'READY','APPLIED'}:
                decision = Decision(**previous['decision'])
            elif previous:
                raise ModelUnavailable('Cette sollicitation IA a déjà été tentée ; preuve à qualifier avant une nouvelle décision.')
            else:
                decisions[identity]={'status':'CALLING','actor':key,'case_id':cid,'stage':tool,'date':state['business_date']}
                manager.persist()
                manager.begin_activity(key, 'THINKING', tasks=current['possible_actions'])
                state['usage']['model_calls'] += 1
                decision, metadata = decide(state['actors'][key], current, state['config'], manager.consume_command, state['usage'])
                account_model_usage(state, metadata)
                if decision.tool not in current['available_tools'] or (decision.args.get('case_id') and decision.args['case_id']!=cid):
                    raise ModelUnavailable('La décision IA ne correspond pas à la sollicitation enregistrée.')
                decisions[identity].update(status='READY',decision={'tool':decision.tool,'args':decision.args,'reason':decision.reason},model=metadata)
                manager.persist()
        if manager.consume_command():
            return False
        action_cid = decision.args.get('case_id') or next((q['case_id'] for q in state['quotes'] if q['id']==decision.args.get('quote_id')), '')
        task_id=f"{state['business_date']}:{key}:{decision.tool}:{action_cid}:{decision.args.get('leg','')}"
        state['checkpoint']['current_task']=task_id
        if task_id in state['checkpoint']['completed_tasks']:
            return True
        manager.begin_activity(key, 'EXECUTING', decision)
        result = tools.execute(key, decision.tool, decision.args)
        row = {'actor':key,'tool':decision.tool,'args':decision.args,'reason':decision.reason,'result':safe_record(result),
               'status':'SUCCESS','date':state['business_date'],'channel':'API' if tools.calls else 'CONTROLLER',
               'http_calls':tools.calls[:], 'model':metadata}
        state['actions'].append(row); state['actors'][key]['history'].append(row)
        state['actors'][key]['seen_message_ids'] = [m['id'] for m in state['messages'] if m['to']==key]
        state['turns'] += 1
        if task_id not in state['checkpoint']['completed_tasks']:
            state['checkpoint']['completed_tasks'].append(task_id)
        state['checkpoint']['current_task'] = None
        if model:
            decisions[identity]['status']='APPLIED'
        manager.persist()
        return True
    except DecisionCancelled:
        state['usage']['unknown_cost_calls'] = state['usage'].get('unknown_cost_calls',0)+1
        return False
    except Exception as exc:
        if metadata is None:
            account_model_usage(state, getattr(exc,'metadata',{}))
        row = {'actor':key,'tool':decision.tool if decision else tool,'args':decision.args if decision else args,
               'reason':reason,'result':str(exc),'status':'FAILED','date':state['business_date'],'http_calls':tools.calls[:], 'model':metadata}
        if getattr(exc, 'raw_response', None) is not None:
            from .store import store
            evidence = store.path(state['id']) / 'provider-responses'
            evidence.mkdir(parents=True, exist_ok=True)
            filename = f'{uuid4().hex}.txt'
            raw = exc.raw_response.encode('utf-8')
            (evidence / filename).write_bytes(raw)
            row['provider_response'] = {'path': f'provider-responses/{filename}',
                                        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        state['actions'].append(row); state['actors'][key]['history'].append(row)
        if manager.cancel.is_set():
            row['status']='CANCELLED';state['status']='STOPPED';state['stop_reason']={'kind':'USER'}
            manager.persist();return False
        if 'EXPECTED_REFUSAL' in str(exc) and decision and decision.tool=='quote':
            row['status']='EXPECTED_REFUSAL'
            case_id=decision.args.get('case_id')
            state['cases'][case_id].setdefault('expected_refusals',{})[key]=str(exc)
            if key not in state['cases'][case_id]['declines']:
                state['cases'][case_id]['declines'].append(key)
            if model:
                decisions[identity]['status']='APPLIED'
            state['turns']+=1;state['checkpoint']['completed_tasks'].append(task_id)
            state['checkpoint']['current_task']=None
            manager.persist();return True
        infrastructure = isinstance(exc, (BudgetReached, ModelUnavailable)) or (model and decision is None)
        failed = manager.incident(key, 'HARNESS' if infrastructure else 'BUG', str(exc))
        actual_tool=decision.tool if decision else tool or 'decision'
        case_id=(decision.args if decision else args).get('case_id')
        case=state['cases'].get(case_id,{})
        module={'quote':'rfq','rfq':'rfq','offer':'rfq','accept_quote':'rfq','confirm_trade':'rfq','book':'booking','review':'lifecycle','settle':'settlements'}.get(actual_tool,actual_tool)
        failed.update(module=module, tool=actual_tool, case_id=case_id, product_terms_version=case.get('native_terms_version'),
                      terms_fingerprint=case.get('terms_fingerprint'), severity='BLOCKING', expected='Action métier terminée une seule fois',
                      observed=str(exc), reproduction={'task_id':task_id,'args':safe_record(row['args'])}, evidence_index=len(state['actions'])-1)
        failed['severity'] = 'OPERATIONAL_STOP' if infrastructure else 'BLOCKING'
        kind = 'BUDGET' if isinstance(exc, BudgetReached) else 'PROVIDER' if infrastructure else 'BLOCKING_ERROR'
        state['stop_reason'] = {'kind':kind, 'incident_id':failed['id'], 'task_id':task_id}
        state['status'] = 'ATTENTION'
        manager.persist()
        return False


def run(manager):
    from playwright.sync_api import sync_playwright
    from .instances import Instances, clock_file
    from .tools import Tools
    from .store import store
    from .store import source_manifest
    from .brain import prepare_model
    from .engine import model_limit_reason
    from .coverage import exercise
    state = manager.live
    directory = store.path(state['id'])
    workers = Instances(directory, state, manager.consume_command)
    started = time.monotonic()
    session_sources = source_manifest()['source_sha256']
    tools = None
    phase='MODEL_PREPARATION'
    try:
        prepare_model(state['config'], manager.consume_command)
        phase='INSTALLATION_PREPARATION'
        workers.start(); manager.persist()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            tools = Tools(directory, state, browser, workers.provision_owner, manager.request_activity)
            for key in state['actors']:
                if key!='achille':
                    manager.begin_activity(key, 'PREPARING')
                    tools.connect(key, workers.ensure_identity(key))
            tools.recover_workflow()
            if any(c['status']=='MISMATCH' for c in check_books(state)):
                raise ValueError('Books incohérents après relecture native ; reprise refusée.')
            enabled = participants(state['config'])
            for key in enabled:
                peers = {'client'} | {k for k in enabled if k!=key and (enabled[key]['request_rfq'] or enabled[key]['respond_rfq']) and (enabled[k]['request_rfq'] or enabled[k]['respond_rfq'])}
                for peer in sorted(peers):
                    if peer not in state['actors'][key]['relations']:
                        tools.relationship(key, peer, otc=enabled.get(peer,enabled[key])['otc_ready'])
                if enabled[key]['request_rfq']:
                    tools.relationship('client', key)
            workers.capture_baseline()
            for key in enabled:
                if enabled[key]['request_rfq']:
                    tools.crm(key)
            tasks = schedule(state['config'])
            phase='BUSINESS'
            while not manager.consume_command():
                if manager.pause.is_set():
                    state['status']='PAUSED'; manager.persist(); manager.cancel.wait(.2); continue
                state['status']='RUNNING'
                if source_manifest()['source_sha256'] != session_sources:
                    state['stop_reason']={'kind':'SOURCE_CHANGED','detail':'Le code a changé pendant la session ; arrêt avant la prochaine écriture.'}
                    break
                if model_limit_reason(state) or state['turns']>=state['config']['max_turns']:
                    state['stop_reason']={'kind':'BUDGET','detail':model_limit_reason(state) or 'Plafond d’actions atteint.'}; break
                if state['usage']['duration_seconds']+time.monotonic()-started >= state['config']['max_wall_minutes']*60:
                    state['stop_reason']={'kind':'WALL_TIME'}; break
                pending = [t for t in tasks if t['month']==state['month'] and t['id'] not in state['cases']]
                for task in pending:
                    tools.request('client', task['template'], task['product']['coupon_percent'], task['product']['barrier_percent'], _task=task)
                    manager.persist()
                ready = next(((k,observation(state,k,tools)) for k in state['actors'] if k!='achille' and observation(state,k,tools)['available_tools']), None)
                if ready:
                    key, current = ready
                    tool, args, solicitation = ready_action(state,key,current)
                    if not checked_action(manager,tools,key,tool,args,'Étape native prête après les accords requis.',model=solicitation is not None,current=solicitation):
                        break
                    if any(c['status']=='MISMATCH' for c in check_books(state)):
                        raise ValueError('Rapprochement incohérent ou jambe en double.')
                    continue
                checks = check_books(state)
                current = [c for c in checks if state['cases'][c['case_id']]['month']==state['month']]
                if any(c['status'] not in {'COMPLETE','NO_TRADE'} for c in current):
                    raise ValueError('Dossier commercial obligatoire incomplet ; aucune progression artificielle du calendrier.')
                for key, actor in state['actors'].items():
                    if key=='achille' or not actor['deals']:
                        continue
                    pending_cash = any(d.get('settlement_status')=='PENDING' and d.get('value_date','9999-12-31')<=state['business_date'] for d in actor['deals'])
                    if pending_cash and not checked_action(manager,tools,key,'settle',{},'Règlements fictifs arrivés à valeur.'):
                        return
                    if review_due(state,actor) and not checked_action(manager,tools,key,'review',{},'Échéances contractuelles et calculs à la cadence configurée.'):
                        return
                exercise(manager, tools)
                if state['status']=='ATTENTION':
                    break
                active = any(a.get('last_review',{}).get('active_deals',0) for a in state['actors'].values())
                historical_end = state['config'].get('end_date') if state['config'].get('market_mode')=='historical' else None
                if historical_end and state['business_date']>=historical_end:
                    state['status']='COMPLETED'
                    state['completion_scope']='HISTORICAL_CUTOFF'
                    state['open_positions']={k:[d for d in a['deals'] if d.get('status') in {'actif','en_reglement'}] for k,a in state['actors'].items()}
                    break
                if state['month']>=state['config']['horizon_months'] and not active:
                    if historical_end:
                        # The configured end date is authoritative, including a final partial month.
                        pass
                    else:
                        state['status']='COMPLETED'; break
                # Monthly/fortnightly surveillance, plus exact contractual dates.
                today = date.fromisoformat(state['business_date'])
                origin = date.fromisoformat(state['config']['start_date'])
                from ...core.calendars import adjust, BusinessDayConvention
                next_month = adjust(origin+relativedelta(months=state['month']+1), 'EUR', BusinessDayConvention.FOLLOWING)
                candidates = [next_month]
                fortnight = origin+relativedelta(months=state['month'], days=15)
                if state['config']['cadences']['risk_days']==15 and today < fortnight < next_month:
                    candidates.append(fortnight)
                for case in state['cases'].values():
                    for field in ('value_date','maturity_date','payment_date'):
                        if not case['pricing'].get(field):continue
                        day = date.fromisoformat(case['pricing'][field])
                        if day>today: candidates.append(day)
                for actor in state['actors'].values():
                    for dates in actor.get('next_event_dates', {}).values():
                        candidates.extend(date.fromisoformat(d) for d in dates if date.fromisoformat(d)>today)
                    candidates.extend(date.fromisoformat(d['settlement_date']) for d in actor['deals'] if d.get('settlement_date') and d['settlement_date']>state['business_date'])
                if historical_end:
                    candidates.append(date.fromisoformat(historical_end))
                next_day = min(d for d in candidates if d>today)
                state['month'] = calendar_month(origin, next_day)
                state['business_date']=next_day.isoformat(); clock_file(directory,state['business_date'])
                state['clock_reason']='Prochaine échéance utile du calendrier de diagnostic'
                state['checkpoint']['pending_tasks']=[t['id'] for t in tasks if t['id'] not in state['cases']]
                manager.persist()
            if state['status'] not in {'COMPLETED','ATTENTION'}:
                state['status']='STOPPED' if manager.cancel.is_set() else 'ATTENTION'
            tools.close(); tools=None; browser.close()
    except Exception as exc:
        if manager.cancel.is_set():
            state['status']='STOPPED';state['stop_reason']={'kind':'USER'}
            return
        provider=phase=='MODEL_PREPARATION'
        incident = manager.incident('achille','BUG' if phase=='BUSINESS' else 'HARNESS',str(exc))
        incident.update(module='provider' if provider else 'orchestration', severity='OPERATIONAL_STOP' if provider else 'BLOCKING',
                        expected='État natif cohérent et progression sûre', observed=str(exc))
        state['stop_reason']={'kind':'PROVIDER' if provider else 'BLOCKING_ERROR','incident_id':incident['id']}
        state['status']='STOPPED' if manager.cancel.is_set() else 'ATTENTION'
    finally:
        if tools:
            try:
                tools.close()
            except Exception as exc:
                manager.incident('achille','HARNESS','Fermeture navigateur : '+str(exc))
        try:
            workers.stop()
        except Exception as exc:
            manager.incident('achille','HARNESS','Fermeture à vérifier : '+str(exc)); state['status']='ATTENTION'
        state['usage']['duration_seconds'] += round(time.monotonic()-started,2)
        state['activity']=None; state['active_actor']=None; state.pop('run_started_at',None)
        manager.persist()
        if manager.lease:
            manager.lease.close(); manager.lease=None
