"""Persistent controller; commercial decisions belong to the model agents."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import re
import time
import threading
import httpx
from uuid import uuid4
from dateutil.relativedelta import relativedelta
from ...core.calendars import adjust, BusinessDayConvention
from .store import store, contract_mandate, source_manifest
from .instances import Instances, clock_file
from .tools import Tools
from .brain import Decision, DecisionCancelled, decide, action_schema, prepare_model
from .openai_model import BudgetReached, ModelUnavailable
from .lease import CampaignLease
from .reconciliation import check_books


def public_state(state):
    result = deepcopy(state)
    for actor in result["actors"].values():
        actor.pop("history", None)
    return result


def safe_record(value):
    if isinstance(value, dict):
        return {k:("[REDACTED]" if k.lower() in {"password","access_token","auth_token","refresh_token","authorization","api_key"} else safe_record(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [safe_record(v) for v in value]
    return value


def failure_message(exc, decision, timeout):
    if isinstance(exc, httpx.TimeoutException):
        if decision is None:
            return f"Le modèle IA n’a pas répondu dans le délai de {timeout} secondes. Vérifier Ollama et sa charge ; aucune action métier n’a été exécutée pour cette décision."
        return "Une requête à Structura a dépassé son délai. Vérifier la disponibilité de l’installation et relire les faits natifs avant de retenter une écriture."
    return str(exc) or f"Erreur {type(exc).__name__} sans message détaillé. Examiner les journaux de l’installation."


PASSIVE_TOOLS = {'mail', 'wait', 'report', 'help', 'browser', 'api'}


def routine_decision(actor, current):
    """Execute mandatory setup without paying a model to choose a fixed step."""
    if not current['connected']:
        return Decision(tool='register', args={}, reason='Initialiser le compte privé prévu pour cet acteur.')
    if 'relationship' in current['available_tools'] and current['relation_tasks']:
        party = current['relation_tasks'][0]
        mandate = current['contract_mandate'][party]
        args = {'party': party, 'status': 'ACTIVE' if mandate['note_ready'] else 'PENDING',
                'otc': bool(mandate['note_ready'] and mandate['otc_ready'])}
        return Decision(tool='relationship', args=args,
                        reason='Appliquer le mandat contractuel déjà approuvé pour cette relation.')
    if actor['id'] == 'hector' and 'crm' in current['available_tools']:
        return Decision(tool='crm', args={}, reason='Initialiser le dossier client fictif prévu pour la campagne.')
    return None


def needs_agent_decision(current):
    return bool(set(current['available_tools']) - PASSIVE_TOOLS or current.get('solicitations'))


def account_model_usage(state, metadata):
    if metadata.get('provider') != 'openai':
        return
    usage = state['usage']
    if metadata.get('cost_unknown'):
        usage['unknown_cost_calls'] = usage.get('unknown_cost_calls',0)+1
    usage['model_input_tokens'] = usage.get('model_input_tokens', 0) + int(metadata.get('input_tokens') or 0)
    usage['model_output_tokens'] = usage.get('model_output_tokens', 0) + int(metadata.get('output_tokens') or 0)
    usage['model_cost_usd'] = round(usage.get('model_cost_usd', 0) + float(metadata.get('cost_usd') or 0), 8)


def model_limit_reason(state):
    config, usage = state['config'], state['usage']
    if usage.get('model_calls', 0) >= config.get('max_model_calls', 20000):
        return 'Nombre maximal d’appels au modèle atteint.'
    if config.get('provider', 'ollama') == 'openai' and usage.get('model_cost_usd', 0) >= config.get('max_ai_cost_usd', 5):
        return 'Plafond de dépense IA de la campagne atteint.'
    return None


def workflow_facts(state):
    """Exclude conversation and diagnostics from evidence of business progress."""
    fields = ('registered', 'relations', 'crm', 'prices', 'deals', 'last_review', 'risk_runs', 'proposals')
    return json.dumps({
        'actors': {key: {field: actor.get(field) for field in fields} for key, actor in state['actors'].items()},
        **{field: state[field] for field in ('cases', 'quotes', 'accepted', 'client_offers', 'client_acceptances')},
    }, sort_keys=True, ensure_ascii=False)


def context_result(action):
    """Keep errors and useful identifiers; full native receipts stay in the journal."""
    result = action['result']
    if action['status'] != 'SUCCESS':
        return result
    if not isinstance(result, dict):
        serialized = json.dumps(result, ensure_ascii=False)
        return result if len(serialized)<2600 else {'preview':serialized[:2600], 'complete_evidence_saved':True}
    if action['tool'] == 'review':
        return {key: result.get(key) for key in ('date', 'deals')} | {
            'valuations': len(result.get('valuations', [])), 'fixings': len(result.get('fixings', []))}
    fields = ('id', 'case_id', 'leg', 'status', 'settlement_status', 'price', 'client_price', 'accepted',
        'accepted_quote', 'quote_id', 'bank', 'declined', 'settled', 'already_sent', 'rfq_id', 'recipients',
        'client_id', 'mandate_id', 'run_id', 'party', 'date', 'delivered', 'waiting', 'explanation', 'description')
    summary = {key: result[key] for key in fields if key in result}
    summary = summary or {'completed': True, 'complete_evidence_saved': True}
    serialized = json.dumps(summary, ensure_ascii=False)
    return summary if len(serialized)<2600 else {'preview':serialized[:2600], 'complete_evidence_saved':True}


def context_message(message):
    result = deepcopy(message)
    attachment = result.get('attachment')
    if isinstance(attachment, dict) and 'pricing' in attachment:
        attachment.pop('pricing')  # The current case exposes the contractual terms below.
    return result


def context_terms(case):
    """Present percentages in the same units as request/propose arguments."""
    pricing = case.get('pricing', {})
    params = pricing.get('user_params', {})
    terms = {field:pricing.get(field) for field in ('strike_date', 'value_date', 'maturity_date', 'payment_date', 'constats')}
    for param, field in (('COUPON', 'coupon_percent'), ('M_KI_BAR', 'capital_barrier_percent'),
                         ('M_AC_BAR', 'autocall_barrier_percent'), ('M_CPN_BAR', 'coupon_barrier_percent')):
        if param in params:
            terms[field] = round(float(params[param])*100, 10)
    terms['percentage_units'] = '8 signifie 8 %, comme les arguments coupon et barrier ; aucune fraction moteur dans ces champs.'
    terms['capital_risk'] = 'Capital non garanti. La barrière ne plafonne pas la perte ; sous la barrière le capital remboursé peut être proche de zéro.'
    terms['coupon_conditional'] = case.get('template')=='phoenix'
    return terms


def observation(state, key, tools):
    actor = state["actors"][key]
    targets = ([k for k,a in state["actors"].items() if a["role"] in {"bank", "client"}] if key == "hector" else ["hector"])
    mandates=contract_mandate(state)
    my_mandate={p:mandates.get(p if key=='hector' else key,{'note_ready':True,'otc_ready':False}) for p in targets}
    otc_parties=[p for p in targets if my_mandate[p]['note_ready'] and my_mandate[p]['otc_ready']]
    relation_tasks = [p for p in targets if p not in actor['relations'] or (actor['relations'][p]['status']=='PENDING' and my_mandate[p]['note_ready'])
        or (p in otc_parties and not actor['relations'][p]['otc_allowed'])]
    messages = [m for m in state["messages"] if m["to"] == key or m["from"] == key]
    seen = set(actor.get("seen_message_ids", []))
    unread = [m for m in messages if m["to"] == key and m["id"] not in seen]
    quotes = [q for q in state["quotes"] if key == "hector" or q["bank"] == key]
    known = {m["case_id"] for m in messages if m["case_id"]}
    cases = [c for c in state["cases"].values() if key in {"hector", "client"} or c["id"] in known]
    candidates = []
    book_tasks={}
    risk_parties=[]
    if key not in tools.tokens:
        candidates = ["Créer ou reconnecter mon compte avec register."]
    else:
        if actor['history'] and actor['history'][-1]['status']=='FAILED' and 'PRICING_RECEIPT' in json.dumps(actor['history'][-1]['result']):
            candidates.append("Relancer mon pricing avec reprice pour obtenir un nouveau reçu avant de réessayer le booking.")
        candidates += [f"Préparer ma relation avec {party}." for party in targets if party not in actor["relations"]]
        candidates += [f"Finaliser la documentation de ma relation avec {party} via relationship, status ACTIVE, si l'accord est obtenu."
            for party in targets if party in actor["relations"] and actor["relations"][party]["status"] == "PENDING" and my_mandate[party]['note_ready']]
        candidates += [f"Finaliser la documentation ISDA/CSA avec {party} via relationship, status ACTIVE et otc true, conformément au mandat approuvé."
            for party in otc_parties if party in actor['relations'] and not actor['relations'][party]['otc_allowed']]
        if key == "hector" and not actor["crm"]:
            candidates.append("Créer mon dossier client avec crm.")
        if state['config'].get('exploratory_actions', True) and key=='hector' and actor['crm'] and state['month']<state['config']['months'] and not any(p['month']==state['month'] for p in actor.get('proposals',[])):
            candidates.append('Proposer une structure adaptée au client avec propose, en expliquant le besoin et les risques ; idée non cotée et non contraignante.')
        if key == "client" and state["month"] < state["config"]["months"] and not any(c["month"] == state["month"] for c in cases):
            candidates.append("Exprimer un nouveau besoin ce mois avec request.")
        for c in cases:
            cid = c["id"]
            if c.get("outcome") in {"CLIENT_DECLINED", "NO_QUOTE"}:
                continue
            if key == "hector":
                if not c["rfq_sent"]:
                    candidates.append(f"Adresser le besoin {cid} aux banques avec rfq après les relations et le CRM.")
                elif not any(q["case_id"] == cid for q in quotes):
                    candidates.append(f"Attendre les réponses pour {cid}.")
                elif cid not in state["client_offers"] and all(k in c['declines'] or any(q['case_id']==cid and q['bank']==k for q in quotes) for k,a in state['actors'].items() if a['role']=='bank'):
                    candidates.append(f"Comparer les réponses puis proposer une offre pour {cid} avec offer.")
                elif cid not in state['client_offers']:
                    candidates.append(f"Attendre les autres réponses bancaires ou refus explicites pour {cid}.")
                elif cid not in state["client_acceptances"]:
                    candidates.append(f"Attendre ou clarifier l'accord client sur {cid}.")
                elif cid not in state["accepted"]:
                    candidates.append(f"Accepter la quote retenue pour {cid} avec accept_quote, en utilisant son vrai quote_id.")
                elif state['config'].get('native_rfq', True) and not c.get('trade_confirmed'):
                    if c.get('bank_confirmation'):
                        candidates.append(f"Confirmer le traitement de {cid} avec confirm_trade après lecture de l'accord bancaire.")
                    else:
                        candidates.append(f"Attendre la confirmation explicite de la banque retenue pour {cid}.")
                else:
                    for leg in ("HECTOR_BUY", "HECTOR_SELL"):
                        if not any(d["case_id"] == cid and d["leg"] == leg for d in actor["deals"]):
                            candidates.append(f"Enregistrer {leg} pour {cid} avec book.")
                            if leg!='HECTOR_SELL' or any(d['case_id']==cid and d['leg']=='HECTOR_BUY' for d in actor['deals']):
                                book_tasks.setdefault(cid,[]).append(leg)
            elif actor["role"] == "bank" and c["rfq_sent"]:
                if not any(q["case_id"] == cid for q in quotes) and key not in c["declines"]:
                    relation_status=actor['relations'].get('hector',{}).get('status','MISSING')
                    candidates.append(f"Coter {cid} avec quote ou refuser explicitement avec decline. MA relation NOTE avec Hector est {relation_status} ; la situation d'une autre banque ne bloque pas mon prix.")
                elif cid in state["accepted"] and any(q["id"] == state["accepted"][cid] for q in quotes) and not any(d["case_id"] == cid for d in actor["deals"]):
                    if state['config'].get('native_rfq', True) and not c.get('trade_confirmed'):
                        if not c.get('bank_confirmation'):
                            candidates.append(f"Confirmer le prix, le nominal et les termes de {cid} avec confirm_trade.")
                    else:
                        candidates.append(f"Accord reçu : enregistrer BANK_SELL pour {cid} avec book.")
                        book_tasks[cid]=['BANK_SELL']
            elif key == "client" and cid in state["client_offers"] and cid not in state["client_acceptances"]:
                candidates.append(f"Décider sur l'offre reçue pour {cid} avec client_accept.")
            elif key == "client" and cid in state["accepted"] and (not state['config'].get('native_rfq', True) or c.get('trade_confirmed')) and not any(d["case_id"] == cid for d in actor["deals"]):
                candidates.append(f"Accord reçu : enregistrer CLIENT_BUY pour {cid} avec book.")
                book_tasks[cid]=['CLIENT_BUY']
        if any(d["settlement_status"] == "PENDING" and d["value_date"] <= state["business_date"] for d in actor["deals"]):
            candidates.append("Enregistrer mes preuves fictives de règlement avec settle.")
        if actor["deals"] and (actor.get("last_review", {}).get("date") != state["business_date"] or actor.get("last_review", {}).get("deals") != len(actor["deals"])):
            candidates.append("Consulter mon book et effectuer le suivi de vie avec review, puis settle.")
        current_cases = [c for c in cases if c["month"]==state["month"]]
        if state['config'].get('exploratory_actions', True) and current_cases and actor.get("otc_sets"):
            for party in actor["otc_sets"]:
                if not any(r["date"]==state["business_date"] and r["party"]==party for r in actor.get("risk_runs",[])):
                    risk_parties.append(party)
                    candidates.append(f"Tester le risque OTC hypothétique pour {current_cases[0]['id']} face à {party} avec risk, dans son périmètre séparé des notes.")
    visible_offers = state["client_offers"] if key in {"hector", "client"} else {}
    # Like enabled controls in a screen, expose the semantic operations that
    # have work to do. Free mail, browser and public API exploration remain.
    available = {"mail", "browser", "report", "wait", "help"}
    if actor.get('api_capabilities'):
        available.add('api')
    labels = {"Préparer ma relation":"relationship", "Finaliser la documentation":"relationship", "Créer mon dossier":"crm",
        "Relancer mon pricing":"reprice", "Proposer une structure":"propose",
        "Exprimer un nouveau":"request", "Adresser le besoin":"rfq", "Comparer les réponses":"offer",
        "Accepter la quote":"accept_quote", "Confirmer le":"confirm_trade", "Enregistrer HECTOR":"book", "Accord reçu":"book",
        "Coter ":"quote", "Décider sur l’offre":"client_accept", "Décider sur l'offre":"client_accept",
        "Enregistrer mes preuves":"settle", "Consulter mon book":"review", "Tester le risque OTC":"risk"}
    for candidate in candidates:
        for prefix, tool in labels.items():
            if candidate.startswith(prefix): available.add(tool)
    if 'quote' in available: available.add('decline')
    if key not in tools.tokens:
        available = {"register"}
    if key == "hector" and (not actor["crm"] or any(p not in actor["relations"] for p in targets)):
        available.discard("rfq")
    business=available-{'mail','browser','api','report','wait','help'}
    # Bound conversation/exploration when it does not change any business fact.
    # A new failure still permits diagnosis. Commercial alternatives stay free.
    tail=actor['history'][-2:]
    if business and len(tail)==2 and all(a['status']=='SUCCESS' and a['tool'] in PASSIVE_TOOLS
            and not a.get('business_progress', False) for a in tail):
        available -= PASSIVE_TOOLS
    elif not business and not unread and len(tail)==2 and all(a['status']=='SUCCESS' and a['tool'] in PASSIVE_TOOLS
            and not a.get('business_progress', False) for a in tail):
        available = {'wait'}
    # Portfolio reviews read every native deal. Only live commercial dossiers
    # and missing bookings need to occupy the model's decision context.
    context_cases = [c for c in cases if c['month']==state['month'] or c['id'] in book_tasks]
    if not context_cases and state['month']<state['config']['months']:
        context_cases = cases[-1:]
    context_ids = {c['id'] for c in context_cases}
    profile = {k:actor[k] for k in ("id", "name", "role", "goal", "registered", "relations", "crm", "prices")}
    relation_fields = ('id', 'version', 'status', 'currency', 'effective_date', 'expiry_date',
        'note_distribution_allowed', 'otc_allowed', 'gross_notional_limit', 'documentation_reference', 'master_agreement_id', 'csa_id')
    profile['relations'] = {party:{f:relation[f] for f in relation_fields if f in relation}
        for party,relation in actor['relations'].items()}
    profile['prices'] = {cid:price for cid,price in actor['prices'].items() if cid in context_ids}
    profile["deals"] = [{f:d[f] for f in ("id","case_id","leg","issuer","our_side","nominal","price_traded","settlement_status")} for d in actor["deals"][-8:]]
    profile["completed_client_notional"] = sum(d["nominal"] for d in actor["deals"] if d["leg"] == "HECTOR_SELL")
    total_bank_volume=sum(d['nominal'] for a in state['actors'].values() for d in a['deals'] if d['leg']=='BANK_SELL')
    my_bank_volume=sum(d['nominal'] for d in actor['deals'] if d['leg']=='BANK_SELL')
    profile['market_share_percent']=round(100*my_bank_volume/total_bank_volume,2) if total_bank_volume else 0
    profile['total_bank_market_volume']=total_bank_volume
    recent = []
    for action in actor["history"][-4:]:
        recent.append({**action, 'result': context_result(action)})
    notes = actor.get('coaching_notes', [])
    memory = [n['text'][:1000] for n in notes[-5:] if n['type']=='COMMERCIAL'
        or actor['history'] and actor['history'][-1]['status']=='FAILED' and n['tool']==actor['history'][-1]['tool']]
    if not notes and actor['history'] and actor['history'][-1]['status']=='FAILED':
        memory = [m[:1000] for m in actor['memory'][-2:]]
    scheduled = state['config'].get('payoff_templates') or []
    scheduled_template = scheduled[state['month'] % len(scheduled)] if scheduled and key == 'client' and state['month'] < state['config']['months'] else None
    return {"actor": profile,
        "connected": key in tools.tokens, "contract_mandate":my_mandate, "relation_tasks":relation_tasks, "book_tasks":book_tasks, "correspondents":[k for k in state['actors'] if k!=key], "date": state["business_date"], "month": state["month"]+1,
        "scheduled_template": scheduled_template,
        "api_capabilities": actor.get('api_capabilities', []),
        "possible_actions": candidates, "available_tools":sorted(available), "risk_parties":risk_parties,
        "messages": [context_message(m) for m in unread[-8:]],
        "solicitations": [m['id'] for m in unread if m.get('kind', 'MESSAGE') == 'MESSAGE'],
        "quotes": [q for q in quotes if q['case_id'] in context_ids],
        "cases": [{**{k:v for k,v in c.items() if k not in {'pricing','native_products','inbox_ids','execution_agreement','exchange_terms'}
                     and (key in {'hector', 'client'} or k not in {'declines', 'opportunity_id', 'rfq_id','bank_confirmation'})},
            "terms": context_terms(c),
            "my_declined": key in c.get('declines', []) if actor['role']=='bank' else None,
            "client_accepted":c['id'] in state['client_acceptances'] if key in {'hector','client'} else None,
            "accepted_quote_id":state['accepted'].get(c['id']) if key in {'hector','client'} or any(q['id']==state['accepted'].get(c['id']) for q in quotes) else None,
            "my_booked_legs":[d['leg'] for d in actor['deals'] if d['case_id']==c['id']]} for c in context_cases],
        "historical_cases_count": len(cases)-len(context_cases),
        "client_offers": {k:v for k,v in visible_offers.items() if k in context_ids}, "my_last_results": recent, "memory": memory}


class Manager:
    def __init__(self):
        self.lock = threading.RLock()
        self.thread = None
        self.key = None
        self.pause = threading.Event()
        self.cancel = threading.Event()
        self.live = None
        self.published = None
        self.lease = None

    def snapshot(self, key):
        with self.lock:
            if self.key == key and self.published is not None and not (store.path(key) / 'campaign.json').is_file():
                raise FileNotFoundError('Campagne introuvable.')
            state = deepcopy(self.published) if self.key == key and self.published is not None else store.load(key)
        checks = check_books(state)
        state["book_checks"] = checks
        state["commercial_volume"] = sum(c["client_volume"] for c in checks)
        command=store.read_command(key)
        if command and command['id']!=state.get('last_control_id') and state['status'] in {'RUNNING','PAUSED','PAUSING','STOPPING'}:
            state['status']={'pause':'PAUSING','stop':'STOPPING','resume':'RUNNING'}.get(command['action'],state['status'])
        state['controller_active'] = bool(self.thread and self.thread.is_alive()) if self.key == key else CampaignLease.is_held(store.path(key))
        state['issue_reviews'] = store.issue_reviews(key)
        state['elapsed_seconds'] = state.get('usage', {}).get('duration_seconds', 0)
        if state['controller_active'] is True and state.get('run_started_at'):
            state['elapsed_seconds'] += max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(state['run_started_at'])).total_seconds())
        return public_state(state)

    def start(self, key, model=None):
        with self.lock, store.lifecycle_guard(key):
            if self.thread and self.thread.is_alive():
                if self.key == key:
                    if self.cancel.is_set():
                        raise ValueError("L'arrêt est en cours. Attendre la fermeture des instances.")
                    self.pause.clear()
                    self.live.pop('pause_reason', None)
                    self.published["status"] = "RUNNING"
                    return
                raise ValueError("Une campagne tourne déjà ; l'arrêter avant d'en lancer une autre.")
            state = store.load(key)
            if state['config'].get('schema_version') == 2:
                if model and model != state['config']['model']:
                    raise ValueError('Modifier le modèle dans les paramètres avant le premier démarrage ; il reste ensuite figé.')
                if state['usage']['duration_seconds'] >= state['config']['max_wall_minutes']*60:
                    raise ValueError('Durée réelle maximale atteinte ; rejouer dans une campagne avec une durée supérieure.')
                unresolved = [i for i in state['incidents'] if i.get('severity')=='BLOCKING'
                              and store.issue_reviews(key).get(i['id'],{}).get('status')!='CLOSED']
                if unresolved:
                    raise ValueError('Qualifier et clôturer le blocage après correction et vérification sur une copie avant de reprendre.')
                from .configuration import preview
                state.setdefault('forecast_at_start', preview(state['config']))
                state.setdefault('config_frozen_at', datetime.now(timezone.utc).isoformat())
            from .consultation import consultations
            if consultations.active(key):
                raise ValueError("Fermer les consultations avant de redémarrer les IA.")
            if state["status"] == "COMPLETED":
                raise ValueError("Cette campagne est terminée. Créer une nouvelle campagne pour un nouvel essai.")
            if state["turns"] >= state["config"]["max_turns"]:
                raise ValueError("Budget atteint. Créer une nouvelle campagne avec un budget supérieur.")
            if model_limit_reason(state):
                raise ValueError(model_limit_reason(state) + ' Créer une nouvelle campagne pour reprendre.')
            if state.get('budget_blocked'):
                raise ValueError('Plafond IA de cette campagne atteint. Créer une nouvelle campagne pour reprendre.')
            self.lease = CampaignLease(store.path(key))
            if model:
                state["config"]["model"] = model
                store.save(state)
            self.key, self.live = key, state
            previous_command=store.read_command(key)
            state['last_control_id']=previous_command['id'] if previous_command else None
            self.pause.clear(); self.cancel.clear()
            state.pop('provider_stop', None)
            state["status"] = "RUNNING"
            state['run_started_at'] = datetime.now(timezone.utc).isoformat()
            state.pop('pause_reason', None)
            state.setdefault('run_manifests',[]).append(source_manifest(include_git=True))
            state['clock_reason']='Préparation des installations privées'
            store.save(state)
            self.published = deepcopy(state)
            self.thread = threading.Thread(target=self.run, name="Structura AI users", daemon=True)
            self.thread.start()

    def manage(self, key, owner, action):
        """Retire inactive test data only; do not touch the main Structura DB."""
        if action not in {'reset', 'delete', 'replay'}:
            raise ValueError('Commande inconnue.')
        with self.lock, store.lifecycle_guard(key):
            state = store.load(key)
            if state['owner'] != owner:
                raise FileNotFoundError('Campagne introuvable.')
            from .consultation import consultations
            if consultations.active(key):
                raise ValueError("Fermer les consultations avant de recommencer ou supprimer cette campagne.")
            if self.key == key and self.thread and self.thread.is_alive():
                raise ValueError('Arrêter les IA et attendre la fermeture des installations avant cette opération.')
            if CampaignLease.is_held(store.path(key)) is not False:
                raise ValueError('Un contrôleur utilise encore cette campagne ; arrêter les IA avant cette opération.')
            # After a controller crash, verify identity and close only its own workers.
            directory = store.path(key)
            instances = Instances(directory, state)
            for actor in state['actors']:
                worker = directory / 'instances' / actor
                if worker.resolve() != directory.resolve() / 'instances' / actor:
                    raise ValueError('Dossier acteur invalide ; opération annulée.')
                instances.recover(worker)
            result = store.replay(key, owner) if action == 'replay' else store.restart(key, owner) if action == 'reset' else store.archive(key)
            if self.key == key and action != 'replay':
                self.key = self.live = self.published = self.thread = None
            return result if action in {'reset', 'replay'} else {'id': key, 'deleted': True}

    def control(self, key, action):
        if self.key != key or not self.thread or not self.thread.is_alive():
            state=store.load(key)
            if state['status'] in {'RUNNING','PAUSED','PAUSING','STOPPING'}:
                store.command(key,action)
                return
            if action == "stop":
                state["status"] = "STOPPED"; store.save(state)
                return
            raise ValueError("La campagne n'est pas active.")
        if action == "pause":
            self.pause.set()
            self.live['pause_reason']='USER'
            with self.lock: self.published["status"] = "PAUSING"
        elif action == "resume":
            self.pause.clear()
            self.live.pop('pause_reason',None)
            with self.lock: self.published["status"] = "RUNNING"
        elif action == "stop":
            self.cancel.set(); self.pause.clear()
            with self.lock: self.published["status"] = "STOPPING"
        else:
            raise ValueError("Commande inconnue.")

    def consume_command(self):
        command=store.read_command(self.key)
        if command and command['id']!=self.live.get('last_control_id'):
            action=command['action']
            if action=='stop':self.cancel.set();self.pause.clear()
            elif action=='pause':self.pause.set();self.live['pause_reason']='USER'
            elif action=='resume':self.pause.clear();self.live.pop('pause_reason',None)
            self.live['last_control_id']=command['id']
        return self.cancel.is_set()

    def incident(self, actor, kind, text):
        row = {"id": uuid4().hex, "actor": actor, "kind": kind, "description": text,
            "date": self.live["business_date"], "source": "CONTROLLER", "action_index": len(self.live["actions"])}
        self.live["incidents"].append(row)
        return row

    def persist(self):
        with self.lock:
            store.save(self.live)
            self.published = deepcopy(self.live)

    def begin_activity(self, actor, phase, decision=None, tasks=None):
        previous = self.live.get('activity') or {}
        now = datetime.now(timezone.utc).isoformat()
        self.live['active_actor'] = actor
        self.live['activity'] = {
            'actor': actor, 'phase': phase,
            'started_at': previous['started_at'] if phase == 'EXECUTING' and previous.get('actor') == actor else now,
            'phase_started_at': now, 'tool': decision.tool if decision else None,
            'args': safe_record(decision.args) if decision else {},
            'reason': decision.reason if decision else '', 'tasks': (tasks or [])[:5],
            'http_calls': [], 'request': None,
        }
        self.persist()

    def request_activity(self, actor, request, calls):
        if self.live['config'].get('schema_version')==2 and request.get('status')=='PENDING' and self.consume_command():
            raise RuntimeError('Arrêt demandé avant la prochaine requête métier.')
        activity = self.live.get('activity')
        if activity and activity['actor'] == actor and activity['phase'] == 'EXECUTING':
            activity['request'] = request
            activity['http_calls'] = calls
            self.persist()

    def coach(self, key, error, tools, commercial=None):
        actor = self.live["actors"].get("achille")
        if not self.live["config"]["coaching"] or not actor or model_limit_reason(self.live):
            return
        context = {"connected": True, "mission": "Tu es superviseur, sans compte commercial. Réponds avec mail pour expliquer l'erreur au destinataire indiqué. Ne propose ni faux prix ni contournement d'un contrôle.",
            "to": key, "correspondents":[key], "error": error, "last_action": {
                **{f:self.live['actions'][-1].get(f) for f in ('actor', 'tool', 'args', 'reason', 'status')},
                'result':context_result(self.live['actions'][-1])}, "available_tools": ["mail"]}
        if commercial:
            context['review_type']='COMMERCIAL';context['payoff_script']=commercial['payoff_script']
            context['payoff_risks']='Reverse convertible/Phoenix : capital non garanti ; la barrière ne plafonne jamais la perte à 100 % moins la barrière. Sous la barrière, le capital remboursé peut être proche de zéro. Le coupon Phoenix est conditionnel.'
            context['available_tools']=['mail','report']
        actor['status']='Analyse en cours'
        try:
            path = re.search(r"/api/[^\s:]+", error)
            if key in tools.tokens:
                actual = observation(self.live,key,tools)
                context['user_tasks']=actual['possible_actions']
                context['current_tool_signatures']=action_schema(self.live['actors'][key],actual)
                if not commercial:
                    query = "/".join(path.group().split("/")[:3]) if path else ""
                    context["native_capabilities"] = tools.help(key, query, remember=False)
                    context['native_capabilities']['operations']=context['native_capabilities']['operations'][:3]
            self.live["usage"]["model_calls"] += 1
            self.begin_activity('achille', 'THINKING', tasks=[f"Conseiller {key} à partir du résultat observé."])
            decision, metadata = decide(actor, context, self.live["config"], self.consume_command, self.live['usage'])
            account_model_usage(self.live, metadata)
            if self.consume_command():
                return
            self.begin_activity('achille', 'EXECUTING', decision)
            if decision.tool=='report' and commercial:
                result=tools.execute('achille','report',decision.args)
                description=decision.args['description']
                tools.mail('achille',key,'Correction de la proposition',description)
                self.live['actors'][key]['memory'].append(description)
                self.live['actions'].append({'actor':'achille','tool':'report','args':decision.args,'reason':decision.reason,
                    'result':result,'status':'SUCCESS','channel':'MAIL','date':self.live['business_date'],'model':metadata})
            if decision.tool == "mail" and decision.args.get("to") == key:
                result = tools.mail("achille", key, "Aide à l'utilisation", decision.args.get("body", decision.reason))
                self.live["actions"].append({"actor": "achille", "tool": "mail", "args": {}, "reason": decision.reason,
                    "result": result, "status": "SUCCESS", "channel": "MAIL", "date": self.live["business_date"], "model": metadata})
                self.live["actors"][key]["memory"].append(decision.args.get("body", decision.reason))
            if decision.tool in {'mail', 'report'}:
                target = self.live['actors'][key]
                target.setdefault('coaching_notes', []).append({
                    'type': 'COMMERCIAL' if commercial else 'ERROR',
                    'tool': context['last_action']['tool'], 'action_index': len(self.live['actions']),
                    'text': decision.args.get('body', decision.args.get('description', decision.reason)),
                })
            actor['status']='Conseil adressé'
        except DecisionCancelled:
            return
        except BudgetReached:
            self.live['budget_blocked'] = True
        except ModelUnavailable as exc:
            account_model_usage(self.live, exc.metadata)
            self.live['provider_stop'] = True
            self.incident('achille', 'HARNESS', 'Coaching interrompu : ' + str(exc)[:500])
        except Exception as exc:
            account_model_usage(self.live, getattr(exc, 'metadata', {}))
            self.incident("achille", "HARNESS", "Coaching indisponible : " + str(exc)[:500])
        finally:
            self.live['activity'] = None
            self.persist()

    def supervise_messages(self, tools):
        actor=self.live['actors'].get('achille')
        if not actor or not self.live['config']['coaching']:
            return
        seen=set(actor.get('seen_message_ids',[]))
        messages=[m for m in self.live['messages'] if m['to']=='achille' and m['id'] not in seen]
        for message in messages[-3:]:
            if self.cancel.is_set(): break
            attachment=message.get('attachment') or {}
            self.coach(message['from'],message['body'],tools,commercial=attachment if attachment.get('type')=='commercial_review' else None)
            seen.add(message['id'])
        actor['seen_message_ids']=list(seen)

    def run(self):
        if self.live['config'].get('schema_version') == 2:
            from .diagnostic import run
            return run(self)
        state = self.live
        directory = store.path(state["id"])
        instances = Instances(directory, state, self.consume_command)
        tools = None
        started = time.monotonic()
        try:
            from playwright.sync_api import sync_playwright
            state['activity'] = {'phase': 'PREPARING', 'actor': None, 'started_at': datetime.now(timezone.utc).isoformat()}
            state['clock_reason'] = 'Chargement du modèle local avant les décisions'
            self.persist()
            state['model_preparation'] = prepare_model(state['config'], self.consume_command)
            state['clock_reason'] = 'Préparation des installations privées'
            self.persist()
            instances.start(); self.persist()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                tools = Tools(directory, state, browser, instances.provision_owner, on_activity=self.request_activity)
                actors = [k for k in state["actors"] if k != "achille"]
                errors = {k:0 for k in actors}
                idle_rounds=0
                while not self.cancel.is_set() and state["turns"] < state["config"]["max_turns"]:
                    if self.consume_command(): break
                    if state.get('budget_blocked') or model_limit_reason(state):
                        state['status'] = 'ATTENTION'
                        self.incident('achille', 'HARNESS', model_limit_reason(state) or 'Plafond IA de la campagne atteint.')
                        self.persist()
                        break
                    if self.pause.is_set():
                        state["status"] = "PAUSED"; state["clock_reason"] = "Pause demandée"
                        state['activity'] = None; state['active_actor'] = None
                        self.persist(); self.cancel.wait(.3); continue
                    state["status"] = "RUNNING"
                    progress = False
                    for key in actors:
                        if self.consume_command() or self.pause.is_set():
                            break
                        actor = state["actors"][key]
                        obs = observation(state, key, tools)
                        message_cursor = obs["messages"][-1]["id"] if obs["messages"] else ""
                        if not needs_agent_decision(obs):
                            actor['seen_message_ids'] = list(set(actor.get('seen_message_ids', [])) |
                                {message['id'] for message in obs['messages']})
                            actor['status'] = 'En attente'
                            continue
                        if not (set(obs.get('available_tools', []))-PASSIVE_TOOLS) and actor.get("idle_messages") == message_cursor:
                            continue
                        state["active_actor"] = key; state["clock_reason"] = "Décision IA / action Structura"
                        actor["status"] = "Réfléchit"
                        self.begin_activity(key, 'THINKING', tasks=obs['possible_actions'])
                        call_start = time.monotonic()
                        tools.calls = []
                        decision = None
                        metadata = {"model": state["config"]["model"], "decision_received": False}
                        before = workflow_facts(state)
                        try:
                            decision = routine_decision(actor, obs)
                            if decision is None:
                                state["usage"]["model_calls"] += 1
                                decision, received_metadata = decide(actor, obs, state["config"], self.consume_command, state['usage'])
                            else:
                                received_metadata = {'provider': 'controller', 'model': None, 'seconds': 0}
                            metadata.update(received_metadata)
                            account_model_usage(state, received_metadata)
                            metadata["decision_received"] = True
                            if self.consume_command():
                                raise DecisionCancelled()
                            actor['status'] = 'Utilise Structura' if decision.tool not in {'mail','wait','report','request','client_accept'} else 'Exécute sa décision'
                            self.begin_activity(key, 'EXECUTING', decision)
                            result = tools.execute(key, decision.tool, decision.args)
                            status = "SUCCESS"
                            errors[key] = 0
                            actor["status"] = "En attente" if decision.tool == "wait" else "Action réalisée"
                            if decision.tool == "wait":
                                actor["idle_messages"] = message_cursor
                        except DecisionCancelled:
                            result = {"cancelled": True, "explanation": "Arrêt demandé ; décision non exécutée."}
                            status = "CANCELLED"
                            actor["status"] = "Arrêt demandé"
                        except Exception as exc:
                            result = {"error": failure_message(exc, decision, state['config']['timeout_seconds'])[:2600], "error_detail": str(exc)[:2600]}
                            metadata.update(getattr(exc, "metadata", {}))
                            account_model_usage(state, getattr(exc, 'metadata', {}))
                            if isinstance(exc, BudgetReached):
                                state['budget_blocked'] = True
                            elif isinstance(exc, ModelUnavailable):
                                state['provider_stop'] = True
                            metadata.setdefault("seconds", round(time.monotonic()-call_start, 2))
                            metadata["error_stage"] = "decision" if decision is None else "tool"
                            expected = "EXPECTED_REFUSAL" in str(exc)
                            status = "EXPECTED_REFUSAL" if expected else "FAILED"
                            actor["status"] = "Refus attendu" if expected else "Erreur à diagnostiquer"
                            if expected:
                                state["coverage"]["incomplete_relationship"] = "EXPECTED_REFUSAL"
                            else:
                                errors[key] += 1
                                self.incident(key, "TO_DIAGNOSE", result['error'])
                        state["turns"] += 1
                        business_progress = workflow_facts(state) != before
                        progress = progress or business_progress
                        action = {"actor": key, "tool": decision.tool if decision else "model", "args": decision.args if decision else {},
                            "reason": decision.reason if decision else "Réponse IA indisponible", "result": result, "status": status,
                            "date": state["business_date"], "channel": "UI" if decision and decision.tool in {"register", "browser"} else "API" if tools.calls else "MAIL",
                            "http_calls": tools.calls[:], "model": metadata,
                            "started_at": (state.get('activity') or {}).get('started_at'),
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "duration_seconds": round(time.monotonic()-call_start, 3), 'business_progress': business_progress}
                        action = safe_record(action)
                        state["actions"].append(action)
                        state['activity'] = None
                        actor["history"].append({"tool": action["tool"], "status": status, "result": safe_record(result), 'business_progress': business_progress})
                        actor["seen_message_ids"] = list(set(actor.get("seen_message_ids", [])) | {m["id"] for m in obs["messages"]})
                        if status == "FAILED" and decision is not None and errors[key] <= 2 and not self.cancel.is_set():
                            self.coach(key, result["error"], tools)
                        self.persist()
                        if state.get('budget_blocked') or model_limit_reason(state):
                            state['status'] = 'ATTENTION'
                            self.incident('achille', 'HARNESS', model_limit_reason(state) or 'Plafond IA de la campagne atteint.')
                            self.persist()
                            break
                        if state.get('provider_stop'):
                            state['status'] = 'ATTENTION'
                            self.incident('achille', 'HARNESS', 'Fournisseur IA indisponible ; aucun nouvel appel automatique.')
                            self.persist()
                            break
                        if errors[key] >= 4:
                            self.pause.set(); state["status"] = "PAUSED"
                            state['pause_reason']='ERROR'
                            self.incident(key, "HARNESS", "Quatre échecs consécutifs : campagne en pause pour conserver les preuves et permettre une reprise.")
                            self.persist(); break
                    if state['status'] == 'ATTENTION' and (state.get('budget_blocked') or state.get('provider_stop') or model_limit_reason(state)):
                        break
                    if self.consume_command() or self.pause.is_set():
                        continue
                    self.supervise_messages(tools)
                    current = next((c for c in check_books(state) if state["cases"][c["case_id"]]["month"] == state["month"]), None)
                    current_case = next((c for c in state["cases"].values() if c["month"] == state["month"]), None)
                    if current and (current['status'] == 'MISMATCH' or current['status'] == 'UNVERIFIED' and current['legs'] >= 4):
                        self.pause.set(); state['status'] = 'PAUSED'
                        state['pause_reason'] = 'RECONCILIATION'
                        incident = self.incident('achille', 'RECONCILIATION', f"Dossier {current['case_id']} : rapprochement à vérifier avant de poursuivre. Les écritures sont conservées.")
                        incident.update(case_id=current['case_id'], details=current)
                        self.persist(); continue
                    commercial_closed = current_case and current_case.get("outcome") in {"CLIENT_DECLINED", "NO_QUOTE"}
                    reviewed = all(not a["deals"] or (a.get("last_review", {}).get("date") == state["business_date"] and a.get("last_review", {}).get("deals") == len(a["deals"])
                        and all(d["settlement_status"] == "SETTLED" for d in a["deals"])) for a in state["actors"].values())
                    active_books = any(a.get('last_review', {}).get('active_deals', 0) for a in state['actors'].values())
                    if state["month"] >= state["config"]["months"] and reviewed and not active_books:
                        state["status"] = "COMPLETED"; break
                    if state['month'] >= state['config']['months'] and reviewed and active_books:
                        state['month'] += 1
                        state['business_date'] = adjust(date.fromisoformat(state['config']['start_date'])+relativedelta(months=state['month']), 'EUR', BusinessDayConvention.FOLLOWING).isoformat()
                        clock_file(directory, state['business_date'])
                        for actor in state['actors'].values():
                            actor.pop('idle_messages', None)
                        state['clock_reason'] = 'Suivi des derniers coupons et remboursements après la période commerciale'
                        self.persist(); continue
                    if (current and current["status"] == "COMPLETE" and any(d["case_id"] == current["case_id"] for d in state["actors"]["client"]["deals"]) or commercial_closed) and reviewed:
                        state["milestones"].append({"date": state["business_date"], "case_id": current_case["id"], "status": "NO_TRADE" if commercial_closed else "BOOKS_MATCHED"})
                        state["month"] += 1
                        state["business_date"] = adjust(date.fromisoformat(state["config"]["start_date"])+relativedelta(months=state["month"]), "EUR", BusinessDayConvention.FOLLOWING).isoformat()
                        clock_file(directory, state["business_date"])
                        for actor in state["actors"].values():
                            actor.pop("idle_messages", None)
                        self.persist()
                    elif not progress:
                        idle_rounds+=1
                        ready=any(set(observation(state,k,tools)['available_tools'])-{'mail','browser','api','report','wait','help'} for k in actors)
                        if ready and idle_rounds<=3:
                            continue
                        self.pause.set(); state["status"] = "PAUSED"
                        state['pause_reason']='IDLE'
                        self.incident("achille", "HARNESS", "Les acteurs attendent sans opération complète. Revoir les échanges avant de poursuivre.")
                        self.persist()
                    else:
                        idle_rounds=0
                if self.cancel.is_set():
                    state["status"] = "STOPPED"
                elif state["turns"] >= state["config"]["max_turns"] and state["status"] != "COMPLETED":
                    state["status"] = "ATTENTION"
                    self.incident("achille", "HARNESS", "Budget de décisions atteint ; les opérations incomplètes restent visibles.")
                tools.close(); tools = None
                browser.close()
        except Exception as exc:
            state["status"] = "STOPPED" if self.cancel.is_set() else "ATTENTION"
            if not self.cancel.is_set(): self.incident("achille", "HARNESS", str(exc)[:2600])
        finally:
            if tools:
                try: tools.close()
                except Exception: pass
            ending_status = state['status']
            state['activity'] = None; state['active_actor'] = None
            state['status'] = 'STOPPING'
            state['clock_reason'] = 'Fermeture des installations privées'
            self.persist()
            try:
                instances.stop()
                state['status'] = ending_status
            except Exception as exc:
                state["status"] = "ATTENTION"
                self.incident("achille", "HARNESS", "Fermeture à vérifier : " + str(exc)[:1000])
            finally:
                state['activity'] = None
                state["active_actor"] = None
                state["clock_reason"] = "Période terminée ; installations privées fermées" if state['status'] == 'COMPLETED' else "Campagne arrêtée ; installations privées fermées"
                state["usage"]["duration_seconds"] += round(time.monotonic()-started, 2)
                self.persist()
                if self.lease:
                    self.lease.close(); self.lease = None

    def shutdown(self):
        self.cancel.set(); self.pause.clear()
        if self.thread:
            self.thread.join(timeout=200)


manager = Manager()
