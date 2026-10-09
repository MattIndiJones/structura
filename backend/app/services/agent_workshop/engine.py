"""Persistent controller; commercial decisions belong to the model agents."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import re
import time
import threading
from uuid import uuid4
from dateutil.relativedelta import relativedelta
from ...core.calendars import adjust, BusinessDayConvention
from .store import store, contract_mandate, source_manifest
from .instances import Instances, clock_file
from .tools import Tools
from .brain import decide, action_schema
from .lease import CampaignLease


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


def check_books(state):
    checks = []
    for case in state["cases"].values():
        legs = [dict(d, actor=k) for k,a in state["actors"].items() for d in a["deals"] if d["case_id"] == case["id"]]
        buy = next((d for d in legs if d["leg"] == "HECTOR_BUY"), None)
        sell = next((d for d in legs if d["leg"] == "BANK_SELL"), None)
        client = next((d for d in legs if d["leg"] == "HECTOR_SELL"), None)
        client_buy = next((d for d in legs if d["leg"] == "CLIENT_BUY"), None)
        status = "PENDING"
        if not legs and case.get('outcome') in {'CLIENT_DECLINED','NO_QUOTE'}:
            status='NO_TRADE'
        if buy and sell:
            status = "MATCHED" if all(buy[f] == sell[f] for f in ("trade_reference", "instrument_reference", "issuer", "nominal", "currency", "price_traded", "value_date", "contract_hash")) and buy["our_side"] == "BUY" and sell["our_side"] == "SELL" else "MISMATCH"
        if client and status == "MATCHED":
            status = "MATCHED" if all(client[f] == buy[f] for f in ("nominal", "instrument_reference", "issuer", "currency", "contract_hash")) else "MISMATCH"
            if client_buy and status == "MATCHED":
                status = "COMPLETE" if all(client[f] == client_buy[f] for f in ("trade_reference", "instrument_reference", "issuer", "nominal", "currency", "price_traded", "value_date", "contract_hash")) and client["our_side"] == "SELL" and client_buy["our_side"] == "BUY" else "MISMATCH"
        checks.append({"case_id": case["id"], "status": status, "legs": len(legs),
            "client_volume": client["nominal"] if status == "COMPLETE" else 0})
    return checks


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
        if key=='hector' and actor['crm'] and state['month']<state['config']['months'] and not any(p['month']==state['month'] for p in actor.get('proposals',[])):
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
                    candidates.append(f"Accord reçu : enregistrer BANK_SELL pour {cid} avec book.")
                    book_tasks[cid]=['BANK_SELL']
            elif key == "client" and cid in state["client_offers"] and cid not in state["client_acceptances"]:
                candidates.append(f"Décider sur l'offre reçue pour {cid} avec client_accept.")
            elif key == "client" and cid in state["accepted"] and not any(d["case_id"] == cid for d in actor["deals"]):
                candidates.append(f"Accord reçu : enregistrer CLIENT_BUY pour {cid} avec book.")
                book_tasks[cid]=['CLIENT_BUY']
        if any(d["settlement_status"] == "PENDING" and d["value_date"] <= state["business_date"] for d in actor["deals"]):
            candidates.append("Enregistrer mes preuves fictives de règlement avec settle.")
        if actor["deals"] and (actor.get("last_review", {}).get("date") != state["business_date"] or actor.get("last_review", {}).get("deals") != len(actor["deals"])):
            candidates.append("Consulter mon book et effectuer le suivi de vie avec review, puis settle.")
        current_cases = [c for c in cases if c["month"]==state["month"]]
        if current_cases and actor.get("otc_sets"):
            for party in actor["otc_sets"]:
                if not any(r["date"]==state["business_date"] and r["party"]==party for r in actor.get("risk_runs",[])):
                    risk_parties.append(party)
                    candidates.append(f"Tester le risque OTC hypothétique pour {current_cases[0]['id']} face à {party} avec risk, dans son périmètre séparé des notes.")
    visible_offers = state["client_offers"] if key in {"hector", "client"} else {}
    # Like enabled controls in a screen, expose the semantic operations that
    # have work to do. Free mail, browser and public API exploration remain.
    available = {"mail", "browser", "api", "report", "wait", "help"}
    labels = {"Préparer ma relation":"relationship", "Finaliser la documentation":"relationship", "Créer mon dossier":"crm",
        "Relancer mon pricing":"reprice", "Proposer une structure":"propose",
        "Exprimer un nouveau":"request", "Adresser le besoin":"rfq", "Comparer les réponses":"offer",
        "Accepter la quote":"accept_quote", "Enregistrer HECTOR":"book", "Accord reçu":"book",
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
    # Bounded conversational loops: once ready work has been ignored twice,
    # require an operational decision or an explicit problem report. Choosing
    # a bank, a margin, a refusal or a client acceptance remains the model's.
    tail=actor['history'][-2:]
    if business and len(tail)==2 and all(a['tool'] in {'mail','wait'} for a in tail):
        available.discard('mail');available.discard('wait')
    profile = {k:actor[k] for k in ("id", "name", "role", "goal", "registered", "relations", "crm", "prices")}
    profile["deals"] = [{f:d[f] for f in ("id","case_id","leg","issuer","our_side","nominal","price_traded","settlement_status")} for d in actor["deals"][-8:]]
    profile["completed_client_notional"] = sum(d["nominal"] for d in actor["deals"] if d["leg"] == "HECTOR_SELL")
    total_bank_volume=sum(d['nominal'] for a in state['actors'].values() for d in a['deals'] if d['leg']=='BANK_SELL')
    my_bank_volume=sum(d['nominal'] for d in actor['deals'] if d['leg']=='BANK_SELL')
    profile['market_share_percent']=round(100*my_bank_volume/total_bank_volume,2) if total_bank_volume else 0
    profile['total_bank_market_volume']=total_bank_volume
    recent = []
    for action in actor["history"][-4:]:
        serialized = json.dumps(action["result"], ensure_ascii=False)
        recent.append({**action,"result":action["result"] if len(serialized)<2600 else {"preview":serialized[:2600], "complete_evidence_saved":True}})
    return {"actor": profile,
        "connected": key in tools.tokens, "contract_mandate":my_mandate, "relation_tasks":relation_tasks, "book_tasks":book_tasks, "correspondents":[k for k in state['actors'] if k!=key], "date": state["business_date"], "month": state["month"]+1,
        "possible_actions": candidates, "available_tools":sorted(available), "risk_parties":risk_parties, "messages": unread[-8:], "quotes": quotes[-8:],
        "cases": [{**{k:v for k,v in c.items() if k != "pricing"},
            "client_accepted":c['id'] in state['client_acceptances'] if key in {'hector','client'} else None,
            "accepted_quote_id":state['accepted'].get(c['id']) if key in {'hector','client'} or any(q['id']==state['accepted'].get(c['id']) for q in quotes) else None,
            "my_booked_legs":[d['leg'] for d in actor['deals'] if d['case_id']==c['id']]} for c in cases[-3:]],
        "client_offers": {k:v for k,v in visible_offers.items() if k in {c['id'] for c in cases[-3:]}}, "my_last_results": recent, "memory": [m[:1000] for m in actor["memory"][-5:]]}


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
            if state["status"] == "COMPLETED":
                raise ValueError("Cette campagne est terminée. Créer une nouvelle campagne pour un nouvel essai.")
            if state["turns"] >= state["config"]["max_turns"]:
                raise ValueError("Budget atteint. Créer une nouvelle campagne avec un budget supérieur.")
            self.lease = CampaignLease(store.path(key))
            if model:
                state["config"]["model"] = model
                store.save(state)
            self.key, self.live = key, state
            previous_command=store.read_command(key)
            state['last_control_id']=previous_command['id'] if previous_command else None
            self.pause.clear(); self.cancel.clear()
            state["status"] = "RUNNING"
            state.pop('pause_reason', None)
            state.setdefault('run_manifests',[]).append(source_manifest())
            state['clock_reason']='Préparation des installations privées'
            store.save(state)
            self.published = deepcopy(state)
            self.thread = threading.Thread(target=self.run, name="Structura AI users", daemon=True)
            self.thread.start()

    def manage(self, key, owner, action):
        """Retire inactive test data only; do not touch the main Structura DB."""
        if action not in {'reset', 'delete'}:
            raise ValueError('Commande inconnue.')
        with self.lock, store.lifecycle_guard(key):
            state = store.load(key)
            if state['owner'] != owner:
                raise FileNotFoundError('Campagne introuvable.')
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
            result = store.restart(key, owner) if action == 'reset' else store.archive(key)
            if self.key == key:
                self.key = self.live = self.published = self.thread = None
            return result if action == 'reset' else {'id': key, 'deleted': True}

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
        activity = self.live.get('activity')
        if activity and activity['actor'] == actor and activity['phase'] == 'EXECUTING':
            activity['request'] = request
            activity['http_calls'] = calls
            self.persist()

    def coach(self, key, error, tools, commercial=None):
        actor = self.live["actors"].get("achille")
        if not self.live["config"]["coaching"] or not actor:
            return
        context = {"connected": True, "mission": "Tu es superviseur, sans compte commercial. Réponds avec mail pour expliquer l'erreur au destinataire indiqué. Ne propose ni faux prix ni contournement d'un contrôle.",
            "to": key, "correspondents":[key], "error": error, "last_action": self.live["actions"][-1], "available_tools": ["mail"]}
        if commercial:
            context['review_type']='COMMERCIAL';context['payoff_script']=commercial['payoff_script']
            context['available_tools']=['mail','report']
        actor['status']='Analyse en cours'
        try:
            path = re.search(r"/api/[^\s:]+", error)
            if key in tools.tokens:
                query = "/".join(path.group().split("/")[:3]) if path else ""
                context["native_capabilities"] = tools.help(key, query)
                context['native_capabilities']['operations']=context['native_capabilities']['operations'][:3]
                actual = observation(self.live,key,tools)
                context['user_tasks']=actual['possible_actions']
                context['current_tool_signatures']=action_schema(self.live['actors'][key],actual)
            self.live["usage"]["model_calls"] += 1
            self.begin_activity('achille', 'THINKING', tasks=[f"Conseiller {key} à partir du résultat observé."])
            decision, metadata = decide(actor, context, self.live["config"])
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
            actor['status']='Conseil adressé'
        except Exception as exc:
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
        state = self.live
        directory = store.path(state["id"])
        instances = Instances(directory, state, self.consume_command)
        tools = None
        started = time.monotonic()
        try:
            from playwright.sync_api import sync_playwright
            state['activity'] = {'phase': 'PREPARING', 'actor': None, 'started_at': datetime.now(timezone.utc).isoformat()}
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
                        if not obs["possible_actions"] and actor.get("idle_messages") == message_cursor:
                            continue
                        state["active_actor"] = key; state["clock_reason"] = "Décision IA / action Structura"
                        actor["status"] = "Réfléchit"
                        self.begin_activity(key, 'THINKING', tasks=obs['possible_actions'])
                        call_start = time.monotonic()
                        tools.calls = []
                        decision = None
                        try:
                            state["usage"]["model_calls"] += 1
                            decision, metadata = decide(actor, obs, state["config"])
                            actor['status'] = 'Utilise Structura' if decision.tool not in {'mail','wait','report','request','client_accept'} else 'Exécute sa décision'
                            self.begin_activity(key, 'EXECUTING', decision)
                            result = tools.execute(key, decision.tool, decision.args)
                            status = "SUCCESS"
                            errors[key] = 0
                            actor["status"] = "En attente" if decision.tool == "wait" else "Action réalisée"
                            if decision.tool != "wait":
                                progress = True
                            else:
                                actor["idle_messages"] = message_cursor
                        except Exception as exc:
                            result = {"error": str(exc)[:2600]}; metadata = {"seconds": round(time.monotonic()-call_start, 2)}
                            expected = "EXPECTED_REFUSAL" in str(exc)
                            status = "EXPECTED_REFUSAL" if expected else "FAILED"
                            actor["status"] = "Refus attendu" if expected else "Erreur à diagnostiquer"
                            if expected:
                                state["coverage"]["incomplete_relationship"] = "EXPECTED_REFUSAL"
                                progress = True
                            else:
                                errors[key] += 1
                                self.incident(key, "TO_DIAGNOSE", str(exc)[:2600])
                        state["turns"] += 1
                        action = {"actor": key, "tool": decision.tool if decision else "model", "args": decision.args if decision else {},
                            "reason": decision.reason if decision else "Réponse IA indisponible", "result": result, "status": status,
                            "date": state["business_date"], "channel": "UI" if decision and decision.tool in {"register", "browser"} else "API" if tools.calls else "MAIL",
                            "http_calls": tools.calls[:], "model": metadata,
                            "started_at": (state.get('activity') or {}).get('started_at'),
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "duration_seconds": round(time.monotonic()-call_start, 3)}
                        action = safe_record(action)
                        state["actions"].append(action)
                        state['activity'] = None
                        actor["history"].append({"tool": action["tool"], "status": status, "result": safe_record(result)})
                        actor["seen_message_ids"] = list(set(actor.get("seen_message_ids", [])) | {m["id"] for m in obs["messages"]})
                        if status == "FAILED" and errors[key] <= 2:
                            self.coach(key, result["error"], tools)
                        self.persist()
                        if errors[key] >= 4:
                            self.pause.set(); state["status"] = "PAUSED"
                            state['pause_reason']='ERROR'
                            self.incident(key, "HARNESS", "Quatre échecs consécutifs : campagne en pause pour conserver les preuves et permettre une reprise.")
                            self.persist(); break
                    if self.consume_command() or self.pause.is_set():
                        continue
                    self.supervise_messages(tools)
                    current = next((c for c in check_books(state) if state["cases"][c["case_id"]]["month"] == state["month"]), None)
                    current_case = next((c for c in state["cases"].values() if c["month"] == state["month"]), None)
                    commercial_closed = current_case and current_case.get("outcome") in {"CLIENT_DECLINED", "NO_QUOTE"}
                    reviewed = all(not a["deals"] or (a.get("last_review", {}).get("date") == state["business_date"] and a.get("last_review", {}).get("deals") == len(a["deals"])
                        and all(d["settlement_status"] == "SETTLED" for d in a["deals"])) for a in state["actors"].values())
                    if state["month"] >= state["config"]["months"] and reviewed:
                        state["status"] = "COMPLETED"; break
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
