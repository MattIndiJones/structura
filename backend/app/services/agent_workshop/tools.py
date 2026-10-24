"""Agent tools acting on public authenticated HTTP and real browser screens."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import secrets
from uuid import uuid4
from urllib.parse import urlparse
import httpx
from fastapi.encoders import jsonable_encoder
from dateutil.relativedelta import relativedelta
from ...core.payscript.templates import TEMPLATES
from ...core.product.models import ProductTerms
from ...core.calendars import adjust, add_business_days, BusinessDayConvention
from .store import contract_mandate
from .persistence import atomic_write
from .native_rfq import NativeRfq, requester
from .configuration import is_diagnostic, participants, funding_at, PAYOFFS
from .historical_market import market_path


class _LoginRejected(ValueError):
    """A native login refusal, distinct from a browser navigation failure."""


class Tools:
    def __init__(self, directory, state, browser, provision_owner=None, on_activity=None):
        self.directory, self.state, self.browser = directory, state, browser
        self.contexts, self.pages, self.tokens = {}, {}, {}
        self.http = httpx.Client(timeout=90, trust_env=False)
        self.calls = []
        self.provision_owner = provision_owner
        self.on_activity = on_activity
        self.network = NativeRfq(self)

    def notify_request(self, key, request):
        if self.on_activity:
            self.on_activity(key, request, self.calls[:])

    def close(self):
        for context in self.contexts.values():
            try:
                context.close()
            except Exception as exc:
                if 'Event loop is closed' not in str(exc) and 'has been closed' not in str(exc):
                    raise
        self.http.close()

    def actor(self, key):
        if key not in self.state["actors"]:
            raise ValueError("Intervenant inconnu.")
        return self.state["actors"][key]

    def responders(self, case=None):
        if case and 'recipients' in case:
            return case['recipients']
        if is_diagnostic(self.state['config']):
            return [k for k,p in participants(self.state['config']).items() if p['respond_rfq']]
        return [k for k,a in self.state['actors'].items() if a['role']=='bank']

    def connect(self, key, credentials):
        response = self.http.post(self.actor(key)['url']+'/api/auth/login', data={k:credentials[k] for k in ('username','password')})
        response.raise_for_status()
        self.tokens[key] = response.json()['access_token']
        who = self.api(key, 'GET', '/api/auth/me')
        if who['username'] != credentials['username']:
            raise ValueError('Identité de session inattendue.')
        self.actor(key).update(registered=True, online=True, username=who['username'], entity_id=who['entity_id'], account_role=who['role'], status='Prêt')
        self.page(key).add_init_script('sessionStorage.setItem("auth_token", '+json.dumps(self.tokens[key])+');')
        self.refresh_native_facts(key)
        return {'prepared':True, 'registration_exercised':False}

    def refresh_native_facts(self, key):
        """Read native relations and executions after free navigation or API writes."""
        actor = self.actor(key)
        try:
            catalog = {r['id']: r['name'] for r in self.api(key, 'GET', '/api/deals/counterparties')}
            relations = self.api(key, 'GET', '/api/trading/relationships')
            executions = self.api(key, 'GET', '/api/trading/executions')
            entities = {a['entity']: k for k, a in self.state['actors'].items()}
            local_relations = {entities[catalog[r['counterparty_id']]]: r for r in relations
                               if catalog.get(r['counterparty_id']) in entities}
            cases = {c['instrument_reference']: c for c in self.state['cases'].values() if c.get('instrument_reference')}
            local_deals = []
            for row in executions:
                case = cases.get(row['instrument_reference'])
                leg = 'UNMAPPED'
                if case:
                    trade = case['instrument_reference']
                    if key == requester(case):
                        leg = 'HECTOR_BUY' if row['trade_reference'] == trade + '-BANK' and row['our_side'] == 'BUY' else 'HECTOR_SELL' if row['trade_reference'] == trade + '-CLIENT' and row['our_side'] == 'SELL' else 'UNEXPECTED'
                    elif key == 'client':
                        leg = 'CLIENT_BUY' if row['trade_reference'] == trade + '-CLIENT' and row['our_side'] == 'BUY' else 'UNEXPECTED'
                    elif actor['role'] == 'bank' or actor.get('capabilities', {}).get('respond_rfq'):
                        leg = 'BANK_SELL' if row['trade_reference'] == trade + '-BANK' and row['our_side'] == 'SELL' else 'UNEXPECTED'
                local_deals.append(dict(row, case_id=case['id'] if case else '', leg=leg))
            actor['relations'], actor['deals'] = local_relations, local_deals
            actor['native_refreshed_at'] = self.state['business_date']
            actor.pop('native_sync_error', None)
            return {'relationships': len(local_relations), 'executions': len(local_deals),
                    'unmapped_executions': sum(d['leg'] == 'UNMAPPED' for d in local_deals)}
        except Exception as exc:
            actor['native_sync_error'] = str(exc)[:1000]
            raise ValueError('Les faits natifs n’ont pas pu être relus ; le suivi reste à vérifier. ' + str(exc)) from exc

    def recover_workflow(self):
        """Recover committed quotes/agreements after interruption without new writes."""
        for case in self.state['cases'].values():
            if not case.get('rfq_id'):
                continue
            sender=requester(case)
            native=self.api(sender,'GET',f"/api/rfq/{case['rfq_id']}")
            if case.get('native_terms_version') and native['product_terms_version']!=case['native_terms_version']:
                raise ValueError('Version Product changée ; reprise suspendue : '+case['id'])
            for bank in self.responders(case):
                rows=[q for q in native['quotes'] if q['provider']==self.actor(bank)['entity'] and not q.get('superseded')]
                local=next((q for q in self.state['quotes'] if q['case_id']==case['id'] and q['bank']==bank),None)
                if local:
                    same=next((q for q in native['quotes'] if q['id']==local.get('native_id')),None)
                    if not same or same['price']!=local['price']:
                        raise ValueError('Cotation native différente de la preuve : '+case['id'])
                elif len(rows)>1:
                    raise ValueError('Plusieurs publications à rapprocher avant reprise : '+case['id'])
                elif rows and rows[0]['price'] is not None:
                    q=rows[0]
                    self.state['quotes'].append({'id':hashlib.sha256(f"{case['id']}:{bank}:{q['id']}".encode()).hexdigest()[:12],
                        'case_id':case['id'],'bank':bank,'native_id':q['id'],'price':q['price'],'currency':q['currency'],
                        'nominal':case['nominal'],'valid_until':q['valid_until'],'firmness':q['firmness'],'source':'RECOVERED_NATIVE_PUBLICATION'})
            agreements=[a for a in native.get('execution_agreements',[]) if a['state'] in {'REQUESTED','CONFIRMED','BOOKED_LOCALLY'}]
            if len(agreements)>1:
                raise ValueError('Plusieurs traitements actifs à rapprocher : '+case['id'])
            if agreements:
                agreement=agreements[0]
                quote=next(q for q in self.state['quotes'] if q['case_id']==case['id'] and q.get('native_id')==agreement['quote_id'])
                if case['id'] not in self.state['client_acceptances']:
                    raise ValueError('Accord client absent des preuves ; reprise suspendue : '+case['id'])
                self.state['accepted'][case['id']]=quote['id']
                case['execution_agreement']=agreement
                if agreement.get('confirmed_at'):
                    case['trade_confirmed']=True
        return {'recovered_from':'NATIVE_RFQ','writes':0}

    def api(self, key, method, path, body=None):
        if not path.startswith("/api/") or ".." in path or "#" in path or "\\" in path:
            raise ValueError("Une route API locale explicite est requise.")
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH"}:
            raise ValueError("Méthode non disponible pour l'agent.")
        if path.startswith("/api/auth/") and path != "/api/auth/me":
            raise ValueError("La connexion et l'inscription passent par l'écran avec register.")
        self.notify_request(key, {"method": method, "path": path, "status": "PENDING"})
        for attempt in range(2):
            try:
                response = self.http.request(method, self.actor(key)["url"] + path,
                    headers={"Authorization": "Bearer " + self.tokens.get(key, "")},
                    **({"json": body} if body is not None else {}))
                break
            except (httpx.ReadError, httpx.RemoteProtocolError):
                if method != "GET" or attempt:
                    raise
        try:
            result = response.json()
        except ValueError:
            result = {"text": response.text[:2000]}
        self.calls.append({"method": method, "path": path, "status": response.status_code})
        self.notify_request(key, self.calls[-1])
        if not response.is_success:
            raise ValueError(f"HTTP {response.status_code} {path} : {json.dumps(result, ensure_ascii=False)[:2200]}")
        return result

    def page(self, key):
        if key not in self.pages:
            self.contexts[key] = self.browser.new_context(viewport={"width": 1280, "height": 850}, locale="fr-FR")
            self.pages[key] = self.contexts[key].new_page()
            self.pages[key].set_default_timeout(12000)
        return self.pages[key]

    def screenshot(self, key):
        directory = self.directory / "screenshots"
        directory.mkdir(exist_ok=True)
        name = f"{key}-{len(self.state['actions']):05d}-{uuid4().hex[:8]}.png"
        self.page(key).screenshot(path=str(directory / name), full_page=False)
        return name

    def mail(self, key, to, subject, body, case_id="", attachment=None, kind="NOTIFICATION"):
        self.actor(to)
        if to == key:
            raise ValueError("Choisir un autre destinataire.")
        if len(body) > 6000 or len(subject) > 250:
            raise ValueError("Message trop long.")
        row = {"id": uuid4().hex, "from": key, "to": to, "subject": subject, "body": body, "kind": kind,
            "case_id": case_id, "date": self.state["business_date"], "attachment": attachment}
        self.state["messages"].append(row)
        return {"message_id": row["id"], "delivered": to}

    def cpty(self, key, party):
        name = self.actor(party)["entity"]
        rows = self.api(key, "GET", "/api/deals/counterparties")
        match = next((r for r in rows if r["name"] == name), None)
        if match is None:
            raise ValueError("Contrepartie absente du catalogue administré.")
        return match

    def relation(self, key, party):
        rows = self.api(key, "GET", "/api/trading/relationships")
        cp = self.cpty(key, party)
        return next((r for r in rows if r["counterparty_id"] == cp["id"]), None)

    def eligible(self, key, party):
        row = self.relation(key, party)
        if not row or row["status"] != "ACTIVE" or not row["note_distribution_allowed"]:
            raise ValueError("EXPECTED_REFUSAL : relation NOTE non active ou documentation incomplète.")
        as_of = self.state["business_date"]
        if row["effective_date"] > as_of or (row["expiry_date"] and row["expiry_date"] < as_of):
            raise ValueError("EXPECTED_REFUSAL : dates de relation hors périmètre.")
        return row

    def register(self, key):
        actor = self.actor(key)
        secret_file = self.directory / "instances" / key / "agent_credentials.json"
        existing_credentials = secret_file.exists()
        if existing_credentials:
            credentials = json.loads(secret_file.read_text(encoding="utf-8"))
        else:
            credentials = {"username": "agent_" + key, "email": key + "@recette.invalid", "password": secrets.token_urlsafe(16)}
            atomic_write(secret_file, json.dumps(credentials))
        page = self.page(key)
        page.goto(actor["url"] + "/#/login")
        # A previous attempt may have authenticated successfully, then failed
        # while setting up desks. Reuse the session already in this actor's tab.
        token = page.evaluate("sessionStorage.getItem('auth_token')")
        session_ready = False
        if token:
            self.tokens[key] = token
            try:
                who = self.api(key, "GET", "/api/auth/me")
            except ValueError as exc:
                if not str(exc).startswith("HTTP 401 "):
                    raise
                self.tokens.pop(key, None)
            else:
                if who["username"] != credentials["username"]:
                    self.tokens.pop(key, None)
                    raise ValueError("La session de cet onglet n'appartient pas au compte attendu.")
                session_ready = True

        def response_for(path):
            return lambda response: (urlparse(response.url).path == path and response.request.method == "POST")

        def login():
            page.locator('input[type="text"]').fill(credentials["username"])
            page.locator('input[type="password"]').fill(credentials["password"])
            # The hash change precedes a full reload. A token or hash alone is
            # not proof that the new document's execution context is ready.
            with page.expect_event("load"):
                with page.expect_response(response_for("/api/auth/login")) as response:
                    page.get_by_role("button", name="Se connecter", exact=True).click()
                if response.value.status != 200:
                    if response.value.status in {400, 401}:
                        raise _LoginRejected("Connexion refusée pour le compte de cet acteur.")
                    raise ValueError(f"La connexion a reçu HTTP {response.value.status}.")
                credentials["account_created"] = True
                atomic_write(secret_file, json.dumps(credentials))

        def register():
            page.get_by_role("button", name="Créer un compte", exact=True).click()
            page.get_by_placeholder("ex: jdupont").fill(credentials["username"])
            page.get_by_placeholder("ex: j.dupont@banque.fr").fill(credentials["email"])
            page.locator('input[type="password"]').nth(0).fill(credentials["password"])
            page.locator('input[type="password"]').nth(1).fill(credentials["password"])
            page.get_by_placeholder("ex: Desk Structuration").fill(actor["entity"])
            with page.expect_event("load"):
                with page.expect_response(response_for("/api/auth/register")) as response:
                    page.get_by_role("button", name="Créer mon compte", exact=True).click()
                if not response.value.ok:
                    raise ValueError(f"L'inscription a reçu HTTP {response.value.status} ; aucun second compte créé.")
                # Persist before navigation/provisioning: a later failure must
                # resume the native account, never repeat its registration.
                credentials["account_created"] = True
                atomic_write(secret_file, json.dumps(credentials))

        if session_ready:
            page.goto(actor["url"] + "/#/")
        elif existing_credentials or actor["registered"]:
            try:
                login()
            except _LoginRejected:
                if actor["registered"] or credentials.get("account_created"):
                    raise
                register()
        else:
            register()
        page.wait_for_function("Boolean(sessionStorage.getItem('auth_token'))")
        self.tokens[key] = page.evaluate("sessionStorage.getItem('auth_token')")
        who = self.api(key, "GET", "/api/auth/me")
        if who["username"] != credentials["username"]:
            self.tokens.pop(key, None)
            raise ValueError("La session de cet onglet n'appartient pas au compte attendu.")
        if self.provision_owner:
            self.provision_owner(key, who["id"])
            who = self.api(key, "GET", "/api/auth/me")
            page.reload()
        actor["account_role"] = who["role"]
        actor["registered"] = True; actor["online"] = True
        actor["username"] = who["username"]; actor["entity_id"] = who["entity_id"]
        actor["status"] = "Connecté"
        self.refresh_native_facts(key)
        self.state["coverage"]["registration_ui"] = "EXERCISED"
        return {"username": who["username"], "entity_id": who["entity_id"], "account_role": who["role"], "channel": "UI", "screenshot": self.screenshot(key)}

    def relationship(self, key, party, status="ACTIVE", otc=False):
        mandate=contract_mandate(self.state).get(party if key=='hector' else key,{'note_ready':True,'otc_ready':False})
        if is_diagnostic(self.state['config']):
            policies = contract_mandate(self.state)
            target = party if participants(self.state['config']).get(party,{}).get('respond_rfq') else key
            mandate = {'note_ready':policies[key]['note_ready'] and policies[party]['note_ready'],
                       'otc_ready':policies.get(target,{}).get('otc_ready',False) and party!='client' and key!='client'}
        if not mandate['note_ready']:
            status = "PENDING"
        if not mandate['otc_ready']:otc=False
        cp = self.cpty(key, party)
        existing = self.relation(key, party)
        prefix = 'REL' if is_diagnostic(self.state['config']) else f"REL-{self.state['id'][:8]}"
        fields = {"counterparty_id": cp["id"], "reference": f"{prefix}-{sorted([key, party])[0]}-{sorted([key, party])[1]}",
            "status": status, "effective_date": self.state["config"]["start_date"],
            "note_distribution_allowed": True, "documentation_reference":
                "Programme de notes et convention de distribution — recette" if status == "ACTIVE" else "",
            "gross_notional_limit": max(self.state["config"]["target_volume"] * 4, self.state['config']['ticket']*self.state['config']['months']*3),
            "notes": "Données fictives de recette ; documentation incomplète." if status == "PENDING" else "Relation de recette négociée par les agents."}
        if is_diagnostic(self.state['config']):
            policy = participants(self.state['config']).get(party) or participants(self.state['config']).get(key)
            fields['gross_notional_limit'] = policy['bilateral_limit_eur']
        if existing:
            otc = otc or (existing['otc_allowed'] and not is_diagnostic(self.state['config']))
            if existing['status']==status and existing['otc_allowed']==otc and existing['effective_date']==fields['effective_date'] and existing['gross_notional_limit']==fields['gross_notional_limit']:
                if otc:
                    config=self.api(key,'GET',f"/api/ccr/counterparties/{cp['id']}/configuration")
                    ns=next((n for n in config['netting-sets'] if n['data'].get('netting_set_id')==existing['reference']+'-OTC'),None)
                    if ns:self.actor(key).setdefault('otc_sets',{})[party]=ns['id']
                self.actor(key)['relations'][party]=existing
                return existing
        if is_diagnostic(self.state['config']) and not otc:
            fields.update(otc_allowed=False,csa_required=False,master_agreement_id=None,csa_id=None)
        if otc:
            def save(kind, reference_field, data):
                config=self.api(key,'GET',f"/api/ccr/counterparties/{cp['id']}/configuration")
                previous=next((r for r in config[kind] if r['data'].get(reference_field)==data[reference_field]),None)
                if previous:
                    if all(previous['data'].get(k)==v for k,v in data.items()):return previous
                    return self.api(key,'PUT',f"/api/ccr/counterparties/{cp['id']}/{kind}/{previous['id']}",{'data':{**previous['data'],**data},'expected_version':previous['version']})
                return self.api(key,'POST',f"/api/ccr/counterparties/{cp['id']}/{kind}",{'data':data})
            master = save('agreements','agreement_id', {
                "agreement_id": fields["reference"] + "-ISDA", "agreement_version": "2002",
                "effective_date": fields["effective_date"], "governing_law": "English law",
                "status": status, "legal_opinion_available": True, "close_out_netting_enforceable": True,
                "cross_product_netting_allowed": False, "notes": "Hypothèse contractuelle fictive de recette."})
            master_id = master["id"]
            csa = save('csas','csa_id', {
                "csa_id": fields["reference"] + "-CSA", "master_agreement_id": master_id,
                "bilateral": True, "collateralised": True, "vm_required": True, "im_required": False,
                "segregated": False, "mpor_days": 10, "active": status == "ACTIVE"})
            fields.update(otc_allowed=status == "ACTIVE", csa_required=True, master_agreement_id=master_id, csa_id=csa["id"])
            netting = save('netting-sets','netting_set_id', {
                "netting_set_id":fields["reference"]+"-OTC", "master_agreement_id":master_id, "csa_id":csa["id"],
                "currency":"EUR", "product_scope":["OTC_TEST_CALL"], "our_legal_entity":self.actor(key)["entity"],
                "counterparty_legal_entity":self.actor(party)["entity"], "active":status=="ACTIVE", "enforceable_netting":True})
            self.actor(key).setdefault("otc_sets", {})[party] = netting["id"]
        if existing:
            fields['expected_version']=existing['version']
            row=self.api(key,'PUT',f"/api/trading/relationships/{existing['id']}",fields)
        else:row = self.api(key, "POST", "/api/trading/relationships", fields)
        self.actor(key)["relations"][party] = row
        if otc: self.state["coverage"]["bilateral_isda_csa"] = "EXERCISED"
        self.mail(key, party, "Préparation de notre relation", f"Relation {row['reference']} enregistrée : {row['status']}.", attachment=row)
        return row

    def crm(self, key):
        if key != "hector" and not self.actor(key).get('capabilities', {}).get('request_rfq'):
            raise ValueError("Ce dossier client est celui d'Hector.")
        actor = self.actor(key)
        if actor["crm"]:
            return actor["crm"]
        client = self.api(key, "POST", "/api/clients", {"name": self.actor("client")["entity"], "client_type": "other",
            "status": "active", "data_origin": "demo", "notes": "Investisseur fictif suivi par l'agent Hector."})
        person = self.api(key, "POST", "/api/persons", {"first_name": "Élodie", "last_name": "Recette",
            "email": "client@recette.invalid", "client_id": client["id"], "start_date": self.state["business_date"]})
        mandate = self.api(key, "POST", f"/api/clients/{client['id']}/mandates", {"name": "Allocation produits structurés",
            "mandate_type": "mandate", "reference_currency": "EUR", "data_origin": "demo"})
        interaction = self.api(key, "POST", "/api/interactions", {"client_id": client["id"], "interaction_date": self.state["business_date"],
            "interaction_type": "other", "summary": "Présentation et recueil du besoin de l'investisseur fictif."})
        actor["crm"] = {"client_id": client["id"], "person_id": person["id"], "mandate_id": mandate["id"], "interaction_id": interaction["id"]}
        self.state["coverage"]["crm"] = "EXERCISED"
        return actor["crm"]

    def propose(self, key, template, coupon, barrier, explanation):
        if key!='hector' or not self.actor(key)['crm']:
            raise ValueError('Hector doit ouvrir son dossier client avant une proposition.')
        if template not in {'reverse_convertible','phoenix'} or not 0<=float(coupon)<=30 or not 1<=float(barrier)<=100 or len(explanation.strip())<10:
            raise ValueError('Proposition incomplète : préciser structure, termes et adéquation au besoin.')
        month=self.state['month']
        prior=next((p for p in self.actor(key).get('proposals',[]) if p['month']==month),None)
        if prior:return prior
        idea={'month':month,'template':template,'coupon':float(coupon),'barrier':float(barrier),'explanation':explanation,
              'status':'IDEA_NOT_PRICED','date':self.state['business_date']}
        row=self.api(key,'POST','/api/interactions',{'client_id':self.actor(key)['crm']['client_id'],
            'interaction_date':idea['date'],'interaction_type':'other',
            'summary':f"Proposition à étudier, non cotée : {template}, coupon {coupon} %, barrière {barrier} %. {explanation}"})
        idea['interaction_id']=row['id'];self.actor(key).setdefault('proposals',[]).append(idea)
        self.mail(key,'client','Une piste pour votre allocation',f"À étudier, sous réserve de pricing et de votre accord : {template}, coupon {coupon} %, barrière {barrier} %. {explanation}",attachment=idea)
        self.mail(key,'achille','Revue commerciale de ma proposition',
            'Vérifie cette explication au regard des termes et du PayScript de référence. Signale toute garantie de capital/rendement ou qualification des risques incorrecte. '+json.dumps(idea,ensure_ascii=False),
            attachment={'type':'commercial_review','payoff_script':TEMPLATES[template]['script']})
        self.state['coverage']['proactive_client_proposals']='EXERCISED'
        return idea

    def request(self, key, template="reverse_convertible", coupon=8, barrier=60, _task=None):
        scheduled = self.state['config'].get('payoff_templates') or []
        if scheduled and not _task:
            # The test matrix owns the product family; the client still decides
            # whether to invest after the actual commercial offer is received.
            template = scheduled[self.state['month'] % len(scheduled)]
        if key != "client" or template not in PAYOFFS:
            raise ValueError("Besoin réservé au client et à un produit qualifié du catalogue.")
        month = self.state["month"]
        previous = self.state['cases'].get(_task['id']) if _task else next((x for x in self.state["cases"].values() if x["month"] == month), None)
        if previous:
            return {'case_id':previous['id'], 'nominal':previous['nominal'], 'template':previous['template'], 'already_requested':True}
        if not 0 <= float(coupon) <= 30 or not 1 <= float(barrier) <= 100:
            raise ValueError("Coupon ou barrière hors bornes de recette.")
        case_id = _task['id'] if _task else "CASE-" + str(month + 1).zfill(3)
        settings = _task['product'] if _task else {}
        sender = _task['requester'] if _task else 'hector'
        strike = adjust(date.fromisoformat(self.state["business_date"]), "EUR", BusinessDayConvention.FOLLOWING)
        maturity = adjust(strike + relativedelta(months=settings.get('maturity_months', self.state['config'].get('maturity_months', 6))), "EUR", BusinessDayConvention.MODIFIED_FOLLOWING)
        pricing = {"script": TEMPLATES[template]["script"], "underlyings": [{"name": "S1", "ticker": "AIR.PA", "ccy": "EUR",
            "spot0": 100, "sigma": .23, "q": .02}], "corr_matrix": [[1]], "model": "constant", "r": .025,
            "N": 2000, "T": (maturity-strike).days/365.25, "user_params": {"COUPON": float(coupon)/100, "M_KI_BAR": float(barrier)/100},
            "anchor": strike.isoformat(), "strike_date": strike.isoformat(), "value_date": strike.isoformat(),
            "maturity_date": maturity.isoformat(), "payment_date": add_business_days(maturity, 3, "EUR").isoformat(),
            "settlement_ccy": "EUR", "constats": {"STARTDATE": {"date": strike.isoformat()}, "MATURITYDATE": maturity.isoformat()}}
        from ..scenario_market import history
        tickers = settings.get('tickers',['AIR.PA'])
        market = history(tickers, (strike-timedelta(days=7)).isoformat(), self.state['business_date'],
                         path=market_path(self.directory,self.state['config']), as_of=date.fromisoformat(self.state['business_date']))
        if market.get('error'):
            raise ValueError(market['error'])
        if _task:
            pricing['N'] = self.state['config']['cadences']['pricing_paths']
        pricing['underlyings'] = [{'name':f'S{i+1}', 'ticker':ticker, 'ccy':'EUR',
                                  'spot0':settings.get('spot_overrides',{}).get(ticker,market['prices'][ticker][-1]),
                                  'sigma':.23, 'q':.02} for i,ticker in enumerate(tickers)]
        pricing['corr_matrix'] = [[1 if i==j else .4 for j in range(len(tickers))] for i in range(len(tickers))]
        if template in {'phoenix', 'autocall_athena'}:
            pricing["user_params"].update(M_AC_BAR=1.0)
            if template == 'phoenix':
                pricing['user_params']['M_CPN_BAR'] = .70
            pricing["constats"].pop("MATURITYDATE")
            pricing["constats"]["OBSERVATIONDATES"] = {"period_start_date": strike.isoformat(),
                "first_observation_date": (strike+relativedelta(months=12 if template=='autocall_athena' else 3)).isoformat(), "end_date": maturity.isoformat(),
                "roll_date": strike.isoformat(), "frequency": "1Y" if template=='autocall_athena' else "3M", "stub": "short_last", "convention": "modified_following", "settlement_lag":3}
        case = {"id": case_id, "month": month, "template": template, "nominal": settings.get('nominal', self.state["config"]["ticket"]),
            "pricing": pricing, "source":market['provider'], "market_reference":{k:market.get(k) for k in ('provider','effective_dates','price_type','provenance','warnings')},
            "rfq_sent": False, "declines": [], "requester":sender, "instrument_reference": f"NOTE-{self.state['id'][:8]}-{case_id}"}
        if _task:
            case['recipients'] = _task['recipients']
        self.state["cases"][case_id] = case
        self.mail(key, sender, "Besoin d'investissement " + case_id,
            f"Je souhaite investir {case['nominal']:,.0f} EUR en {template}, coupon {coupon} %, barrière {barrier} %. Merci de me proposer les conditions.", case_id,
            {field:case[field] for field in ('id','template','nominal','instrument_reference')})
        return {"case_id": case_id, "nominal": case["nominal"], "template": template}

    def case(self, key, case_id):
        case = self.state["cases"].get(case_id)
        if not case:
            raise ValueError("Besoin inconnu.")
        if key not in {"client", requester(case)} and not any(m["to"] == key and m["case_id"] == case_id for m in self.state["messages"]):
            raise ValueError("Ce besoin n'a pas été communiqué à cet agent.")
        return case

    def price(self, key, case, spread=0, refresh=False):
        actor = self.actor(key)
        if case["id"] in actor["prices"] and not refresh:
            return actor["prices"][case["id"]]
        payload = deepcopy(case["pricing"])
        payload["funding_spread"] = float(spread)
        funding = None
        if is_diagnostic(self.state['config']) and key in self.responders(case):
            funding, policy = funding_at(self.state['config'], key, self.state['month'])
            payload.update(funding_curve=funding, funding_spread=0)
        if actor['role'] == 'client' and case.get('exchange_terms') and key not in case.get('native_products', {}):
            terms = ProductTerms.model_validate(case['exchange_terms'])
            contract_input = jsonable_encoder(terms.pricing_fields())
            contract_input.update({field:payload[field] for field in ('r','N','model','corr_matrix')})
            contract_input['underlyings'] = [{**identity, **{field:value for field,value in market.items() if field in {'spot0','sigma','q'}}}
                for identity, market in zip(contract_input['underlyings'], payload['underlyings'])]
            private = self.api(key, 'POST', '/api/products', {
                'command_key':hashlib.sha256((self.state['id'] + case['id'] + '-INVESTOR-PRODUCT').encode()).hexdigest(),
                'name':case['id'] + ' — investisseur', 'pricing_input':contract_input,
                'intent':{'nominal':case['nominal'], 'side':'BUY', 'transaction_format':'EMTN', 'instrument_family':'NOTE'}})
            if ProductTerms.model_validate(private['terms']).fingerprint != case['terms_fingerprint']:
                raise ValueError('Le Product investisseur ne reprend pas les termes canoniques reçus.')
            case.setdefault('native_products', {})[key] = private['product_id']
        product_id = case.get('native_products', {}).get(key)
        if product_id:
            product = self.api(key, 'GET', f'/api/products/{product_id}')
            context = {field:payload[field] for field in ('r','N','model','corr_matrix','underlyings')}
            context['underlyings'] = [{field:value for field,value in u.items() if field in {'spot0','sigma','q'}}
                                      for u in context['underlyings']]
            context.update(seed=self.state['config']['seed'], antithetic=True)
            if actor['role'] == 'bank' and not is_diagnostic(self.state['config']):
                banks = [k for k,a in self.state['actors'].items() if a['role'] == 'bank']
                context['underlyings'][0]['sigma'] = .18 + .015 * banks.index(key)
            if key == requester(case) and case.get('rfq_id'):
                rfq_pricing = self.api(key, 'POST', f"/api/rfq/{case['rfq_id']}/pricing-input", {
                    'expected_terms_version':product['terms_version']})
                payload = rfq_pricing['pricing_input']
            else:
                rfq_pricing = None
                payload = self.api(key, 'POST', f'/api/products/{product_id}/pricing-input', {
                    'expected_terms_version':product['terms_version'], 'context':context})
            if funding is not None:
                payload.update(funding_curve=funding, funding_spread=0)
        result = self.api(key, "POST", "/api/price", payload)
        calculation_id = None
        if product_id:
            stored_product = self.api(key, 'POST', f'/api/products/{product_id}/calculations', {
                'command_key':str(uuid4()), 'expected_revision':product['revision'], 'pricing_receipt':result['pricing_receipt']})
            calculation_id = stored_product['calculations'][-1]['id']
            if key == requester(case) and case.get('rfq_id'):
                self.api(key, 'PATCH', f"/api/rfq/{case['rfq_id']}", {
                    'model_price':result['price'] * 100, 'expected_model_input_hash':rfq_pricing['input_hash']})
        stored = {"input": payload, "result": result}
        directory = self.directory / "instances" / key / "pricing"
        directory.mkdir(exist_ok=True)
        (directory / (case["id"] + ".json")).write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        actor["prices"][case["id"]] = {"price_pct": result["price"] * 100, "path": case["id"] + ".json", 'calculation_id':calculation_id,
                                      'funding_curve':funding, 'as_of':self.state['business_date']}
        self.state['usage']['pricings'] = self.state['usage'].get('pricings', 0)+1
        self.state["coverage"]["native_pricing"] = "EXERCISED"
        return actor["prices"][case["id"]]

    def reprice(self, key, case_id):
        result = self.price(key, self.case(key, case_id), refresh=True)
        return {**result,"case_id":case_id,"message":"Nouveau calcul natif conservé ; les accords de prix restent inchangés."}

    def rfq(self, key, case_id):
        case = self.case(key, case_id)
        if key != requester(case):
            raise ValueError("Hector prépare cet AO.")
        case = self.case(key, case_id)
        if case["rfq_sent"]:
            return {"rfq_id": case["rfq_id"], "already_sent": True}
        banks = self.responders(case)
        for bank in banks:
            if not self.relation(key, bank):
                raise ValueError("Préparer toutes les relations avant cet AO.")
        if not self.actor(key)["crm"]:
            raise ValueError("Créer le dossier client avant l'AO.")
        actor = self.actor(key)
        desk_id = actor.get("pilot_desk_id")
        desks = self.api(key, "GET", "/api/rfq-desks")
        desk = next((row for row in desks if row["id"] == desk_id and row["entity_id"] == actor["entity_id"]), None)
        if not desk or not desk["active"] or not {"read", "prepare"} <= set(desk["rights"]):
            raise ValueError("Le desk pilote explicite est absent ou non habilité ; aucune opportunité créée.")
        crm = actor["crm"]
        source = f"SIMULATION:{self.state['id']}:{case_id}"
        title = case_id + " — investissement"
        if case.get("opportunity_id"):
            opportunity = self.api(key, "GET", f"/api/opportunities/{case['opportunity_id']}")
        else:
            # Reconcile even when a previous POST committed but its response
            # or the controller's next save was lost. Refuse ambiguous history.
            rows = self.api(key, "GET", f"/api/opportunities?client_id={crm['client_id']}")
            matches = [row for row in rows if row.get("source") == source or (
                not row.get("source") and row["title"] == title and row.get("mandate_id") == crm["mandate_id"]
                and row.get("amount") == case["nominal"] and row.get("data_origin") == "demo")]
            if len(matches) > 1:
                raise ValueError("Plusieurs opportunités correspondent au dossier ; rapprocher avant de reprendre.")
            opportunity = matches[0] if matches else self.api(key, "POST", "/api/opportunities", {
                "client_id": crm["client_id"], "mandate_id": crm["mandate_id"], "source": source,
                "title": title, "amount": case["nominal"], "data_origin": "demo",
                "payoff_family": 'Autocall' if case['template']=='autocall_athena' else PAYOFFS[case['template']]})
        if (opportunity["client_id"] != crm["client_id"] or opportunity.get("mandate_id") != crm["mandate_id"]
                or opportunity["title"] != title or opportunity.get("amount") != case["nominal"]):
            raise ValueError("L'opportunité existante ne correspond plus au dossier ; reprise suspendue.")
        case["opportunity_id"] = opportunity["id"]
        rows = self.api(key, "GET", "/api/rfq")
        matches = [row for row in rows if row["name"] == case_id and row.get("opportunity_id") == opportunity["id"]
                   and row.get("pilot_desk_id") == desk_id]
        if len(matches) > 1:
            raise ValueError("Plusieurs RFQ correspondent au dossier ; rapprocher avant de reprendre.")
        expected_params = {**case["pricing"], "currency": "EUR", "notional": case["nominal"]}
        if matches and (matches[0]["script_snapshot"] != case["pricing"]["script"]
                        or matches[0]["params"] != expected_params
                        or matches[0]["kind"] != "to_trade" or matches[0]["sens"] != "achat"):
            raise ValueError("La RFQ existante ne correspond plus aux termes attendus ; rapprocher avant de reprendre.")
        rfq = matches[0] if matches else self.api(key, "POST", "/api/rfq", {
            "pilot_desk_id": desk_id, "opportunity_id": opportunity["id"],
            "client_id": crm["client_id"], "mandate_id": crm["mandate_id"],
            "name": case_id, "kind": "to_trade", "sens": "achat",
            "script_snapshot": case["pricing"]["script"], "params": expected_params,
            "transaction_format": "EMTN", "instrument_family": "NOTE", "documentation_reference":
                next((r["documentation_reference"] for r in self.actor(key)["relations"].values() if r["status"] == "ACTIVE"), "")})
        case["rfq_id"] = rfq["id"]
        if self.state['config'].get('native_rfq', True):
            self.network.send(key, case, rfq)
        case["rfq_sent"] = True
        for bank in banks:
            self.mail(key, bank, "Demande de prix " + case_id, "Demande livrée dans RFQ reçues : coter dans votre installation privée.", case_id,
                      {'case_id':case_id, 'instrument_reference':case['instrument_reference'], 'network_state':case.get('network_state')})
        return {"rfq_id": rfq["id"], "recipients": banks}

    def quote(self, key, case_id, margin_bps=30):
        case = self.case(key, case_id)
        if key not in self.responders(case):
            raise ValueError("Seule une banque cote cet AO.")
        case = self.case(key, case_id)
        existing = next((q for q in self.state["quotes"] if q["bank"] == key and q["case_id"] == case_id), None)
        if existing:
            return existing
        try:
            self.eligible(key, requester(case))
        except ValueError as exc:
            if key not in case["declines"]:
                case["declines"].append(key)
                self.mail(key, requester(case), "Cotation refusée " + case_id, str(exc), case_id)
            if all(k in case['declines'] for k in self.responders(case)):
                case['outcome']='NO_QUOTE'
            raise
        margin = float(margin_bps)
        if is_diagnostic(self.state['config']):
            _, policy = funding_at(self.state['config'], key, self.state['month'])
            if not policy['margin_min_bps'] <= margin <= policy['margin_max_bps']:
                raise ValueError('La marge sort de la politique de cet émetteur.')
        if not -100 <= margin <= 1000:
            raise ValueError("Marge hors limites de recette.")
        if self.state['config'].get('native_rfq', True):
            self.network.bank_product(key, case)
        price = self.price(key, case)
        q = {"id": uuid4().hex[:12], "bank": key, "case_id": case_id,
            "price": round(price["price_pct"] + margin/100, 6), "currency": "EUR", "nominal": case["nominal"],
            "valid_until": self.state["business_date"] + "T17:00:00", "firmness": "FIRM"}
        if self.state['config'].get('native_rfq', True):
            native = self.network.publish(key, case, q['price'])
            q['native_id'] = native['id']
            q['valid_until'] = native['valid_until']
            q['source'] = 'NATIVE_RFQ_PUBLICATION'
        self.state["quotes"].append(q)
        self.actor(key).setdefault('private_quote_policies', {})[case_id] = {'margin_bps':margin, 'funding_curve':price.get('funding_curve'), 'as_of':self.state['business_date']}
        self.mail(key, requester(case), "Réponse ferme " + case_id,
            f"Prix proposé {q['price']:.6f} % du nominal, EUR, valable jusqu'à {q['valid_until']}.", case_id, deepcopy(q))
        return q

    def decline(self, key, case_id, explanation):
        case=self.case(key,case_id)
        if key not in self.responders(case) or len(explanation.strip())<5:
            raise ValueError('Une banque doit expliquer son refus de cotation.')
        case=self.case(key,case_id)
        if any(q['bank']==key and q['case_id']==case_id for q in self.state['quotes']):
            raise ValueError('Une cotation ferme existe déjà ; son retrait requiert un workflow distinct.')
        relationship=self.relation(key,requester(case))
        if key not in case['declines']:
            case['declines'].append(key)
            self.mail(key,requester(case),'Refus de cotation '+case_id,explanation,case_id,{'declined':True,'relationship_status':relationship['status'] if relationship else 'MISSING'})
        if not relationship or relationship['status']!='ACTIVE':
            self.state['coverage']['incomplete_relationship']='DECLINED_WITH_LEGAL_EVIDENCE'
        banks=self.responders(case)
        if all(k in case['declines'] for k in banks): case['outcome']='NO_QUOTE'
        return {'case_id':case_id,'declined':True,'explanation':explanation}

    def received_quote(self, key, quote_id):
        quote = next((q for q in self.state["quotes"] if q["id"] == quote_id), None)
        if not quote or (key not in {requester(self.state['cases'][quote['case_id']]), quote["bank"]}):
            raise ValueError("Cotation non accessible à cet agent.")
        return quote

    def offer(self, key, quote_id, margin_bps=40, justification=""):
        if len(justification.strip()) < 5:
            raise ValueError("Hector doit motiver son choix.")
        quote = self.received_quote(key, quote_id)
        case = self.case(key, quote["case_id"])
        if key != requester(case):
            raise ValueError('Seul le demandeur choisit son offre.')
        if case["id"] in self.state["client_acceptances"]:
            raise ValueError("L'offre acceptée est figée ; ouvrir un nouveau besoin pour changer ses termes.")
        self.eligible(key, quote["bank"])
        expected = self.responders(case)
        if any(not any(q["bank"] == k and q["case_id"] == case["id"] for q in self.state["quotes"]) and k not in case["declines"] for k in expected):
            raise ValueError("Attendre les autres réponses éligibles, ou leur refus explicite.")
        value = float(margin_bps)
        if not -100 <= value <= 1000:
            raise ValueError("Marge client hors limites.")
        offer = {"case_id": case["id"], "quote_id": quote_id, "issuer": self.actor(quote["bank"])["entity"],
            "client_price": round(quote["price"] + value/100, 6), "justification": justification,
            "nominal": case["nominal"], "currency": "EUR"}
        self.state["client_offers"][case["id"]] = offer
        self.mail(key, "client", "Proposition " + case["id"],
            f"Note {offer['issuer']} à {offer['client_price']} % du nominal. {justification}. Risque émetteur et perte en capital selon le payoff.", case["id"], deepcopy(offer))
        return offer

    def client_accept(self, key, case_id, accept=True, explanation="Termes compris et acceptés"):
        if key != "client" or case_id not in self.state["client_offers"]:
            raise ValueError("Aucune offre reçue à accepter.")
        if not isinstance(accept, bool):
            raise ValueError("L'acceptation doit être un booléen.")
        if accept and case_id not in self.state["client_acceptances"]:
            self.state["client_acceptances"].append(case_id)
        if not accept:
            if case_id in self.state["accepted"]:
                raise ValueError("Un trade déjà accepté doit faire l'objet d'une annulation négociée.")
            self.state["client_acceptances"] = [c for c in self.state["client_acceptances"] if c != case_id]
            self.state["cases"][case_id]["outcome"] = "CLIENT_DECLINED"
        self.mail(key, requester(self.state['cases'][case_id]), ("Acceptation " if accept else "Refus ") + case_id, explanation, case_id,
            {"accept": accept, "offer": deepcopy(self.state["client_offers"][case_id])})
        return {"accepted": accept, "case_id": case_id}

    def accept_quote(self, key, quote_id, justification=""):
        if len(justification.strip()) < 5:
            raise ValueError("Hector doit motiver l'acceptation.")
        quote = self.received_quote(key, quote_id)
        case = self.case(key, quote["case_id"])
        if key != requester(case):
            raise ValueError('Seul le demandeur accepte cette cotation.')
        if case["id"] not in self.state["client_acceptances"] or self.state["client_offers"][case["id"]]["quote_id"] != quote_id:
            raise ValueError("Attendre l'accord client sur cette offre.")
        self.eligible(key, quote["bank"])
        self.price(key, case)
        if self.state['config'].get('native_rfq', True):
            self.api(key, 'PATCH', f"/api/rfq/{case['rfq_id']}", {
                'selected_quote_id':quote['native_id'], 'selection_reason_code':'other', 'selection_reason_note':justification})
            agreement = self.api(key, 'POST', f"/api/rfq/{case['rfq_id']}/treatment", {
                'quote_id':quote['native_id'], 'expected_terms_version':case['native_terms_version'],
                'expected_terms_fingerprint':case['terms_fingerprint'],
                'command_key':hashlib.sha256((self.state['id'] + case['id'] + '-TREATMENT').encode()).hexdigest(),
                'source':'DOCUMENT', 'reference':'Demande explicite fictive de traitement après accord client',
                'bank_contact':self.actor(quote['bank'])['name'] + ' — desk fictif'})
            case['execution_agreement'] = agreement
            self.state['accepted'][case['id']] = quote['id']
            self.mail(key, quote['bank'], 'Demande de confirmation ' + case['id'],
                      'Merci de confirmer explicitement prix, nominal et termes avant le booking.', case['id'], deepcopy(quote))
            return {'accepted_quote':quote_id, 'rfq_id':case['rfq_id'], 'confirmation_pending':True}
        for q in [x for x in self.state["quotes"] if x["case_id"] == case["id"]]:
            if "native_id" not in q:
                native = self.api(key, "POST", f"/api/rfq/{case['rfq_id']}/quotes", {"provider": self.actor(q["bank"])["entity"]})
                q["native_id"] = native["id"]
                self.api(key, "PATCH", f"/api/rfq/{case['rfq_id']}/quotes/{native['id']}",
                    {"price": q["price"], "currency": "EUR", "status": "recu", "firmness": "FIRM", "valid_until": q["valid_until"]})
        self.api(key, "PATCH", f"/api/rfq/{case['rfq_id']}", {"model_price": self.actor(key)["prices"][case["id"]]["price_pct"],
            "selected_quote_id": quote["native_id"], "selection_reason_code": "other", "selection_reason_note": justification})
        self.state["accepted"][case["id"]] = quote["id"]
        self.mail(key, quote["bank"], "Accord ferme " + case["id"], f"Nous traitons {quote['nominal']} EUR à {quote['price']} %. {justification}", case["id"], deepcopy(quote))
        return {"accepted_quote": quote_id, "rfq_id": case["rfq_id"]}

    def confirm_trade(self, key, case_id):
        case = self.case(key, case_id)
        quote = next(q for q in self.state['quotes'] if q['id'] == self.state['accepted'].get(case_id))
        if key == quote['bank']:
            self.eligible(key, requester(case))
            self.api(key, 'GET', f"/api/rfq-inbox/{case['inbox_ids'][key]}")
            confirmation = {'bank':key, 'reference':case['instrument_reference'] + '-BANK',
                'price':quote['price'], 'nominal':case['nominal'], 'terms_fingerprint':case['terms_fingerprint'],
                'at':self.state['business_date'] + 'T09:00:00Z',
                'evidence':'Confirmation explicite du compte bancaire de simulation sur prix, nominal et termes figés'}
            case['bank_confirmation'] = confirmation
            self.mail(key, requester(case), 'Confirmation ferme ' + case_id, confirmation['evidence'], case_id, deepcopy(confirmation))
            return {'case_id':case_id, 'bank_confirmed':True}
        if key != requester(case) or not case.get('bank_confirmation'):
            raise ValueError('Attendre la confirmation explicite de la banque retenue.')
        confirmation = case['bank_confirmation']
        if confirmation['price'] != quote['price'] or confirmation['terms_fingerprint'] != case['terms_fingerprint']:
            raise ValueError('La confirmation reçue ne correspond pas à la cotation acceptée.')
        agreement = case['execution_agreement']
        confirmed = self.api(key, 'POST', f"/api/rfq/{case['rfq_id']}/treatment/{agreement['id']}/confirm", {
            'expected_snapshot_hash':agreement['snapshot_hash'], 'execution_reference':confirmation['reference'],
            'acceptance_received_at':confirmation['at'], 'acceptance_evidence':confirmation['evidence'],
            'confirmed_at':confirmation['at'], 'source':'BANK_CONFIRMATION', 'evidence':confirmation['evidence'],
            'bank_contact':self.actor(quote['bank'])['name'] + ' — compte bancaire fictif'})
        case['execution_agreement'] = confirmed
        case['trade_confirmed'] = True
        self.state['coverage']['confirmation_before_booking'] = 'EXERCISED'
        return {'case_id':case_id, 'agreement_id':confirmed['id'], 'trade_confirmed':True}

    def book(self, key, case_id, leg):
        case = self.case(key, case_id)
        accepted_id = self.state["accepted"].get(case_id)
        if not accepted_id:
            raise ValueError("Aucun accord ferme pour cette opération.")
        if self.state['config'].get('native_rfq', True) and not case.get('trade_confirmed'):
            raise ValueError('La confirmation bancaire doit être consignée avant le booking.')
        if key == "client" and leg == "CLIENT_BUY" and case_id in self.state["client_acceptances"]:
            q = next(x for x in self.state["quotes"] if x["id"] == accepted_id)
        else:
            q = self.received_quote(key, accepted_id)
        if leg == "BANK_SELL" and key == q["bank"]:
            party, side, trade_price = requester(case), "SELL", q["price"]
        elif leg == "HECTOR_BUY" and key == requester(case):
            party, side, trade_price = q["bank"], "BUY", q["price"]
        elif leg == "HECTOR_SELL" and key == requester(case):
            party, side, trade_price = "client", "SELL", self.state["client_offers"][case_id]["client_price"]
        elif leg == "CLIENT_BUY" and key == "client":
            party, side, trade_price = requester(case), "BUY", self.state["client_offers"][case_id]["client_price"]
        else:
            raise ValueError("Cette jambe appartient à un autre acteur.")
        actor = self.actor(key)
        previous = next((d for d in actor["deals"] if d["case_id"] == case_id and d["leg"] == leg), None)
        if previous:
            return previous
        relation = self.eligible(key, party)
        self.price(key, case, refresh=leg == 'HECTOR_BUY' and self.state['config'].get('native_rfq', True))
        saved = json.loads((self.directory / "instances" / key / "pricing" / (case_id + ".json")).read_text(encoding="utf-8"))
        p, r = saved["input"], saved["result"]
        deal = {"sens": "vente" if side == "BUY" else "achat", "contrepartie": self.actor(party)["entity"],
            "counterparty_id": self.cpty(key, party)["id"],
            "devise": "EUR", "product_type": TEMPLATES[case["template"]]["label"], "nominal": case["nominal"],
            "fair_value": r["price"]*100, "price_traded": trade_price, "trade_date": self.state["business_date"],
            **{field:p[field] for field in ("strike_date", "value_date", "maturity_date", "payment_date", "T")},
            "underlyings": [{**u, "s0_abs": u["spot0"]} for u in p["underlyings"]], "observation_times": [],
            "script_snapshot": p["script"], "market_snapshot": {"constats": p["constats"], "user_params": p["user_params"]},
            "pricing_receipt": r["pricing_receipt"], "transaction_format": "EMTN", "instrument_family": "NOTE",
            "documentation_reference": relation["documentation_reference"]}
        if leg == "HECTOR_BUY":
            deal["rfq_id"] = case["rfq_id"]
            if case.get('execution_agreement'):
                deal['execution_agreement_id'] = case['execution_agreement']['id']
        product_id = case.get('native_products', {}).get(key)
        if leg == 'HECTOR_SELL' and product_id:
            resale_id = case.get('resale_product_id')
            if not resale_id:
                contractual_input = {field:value for field,value in p.items() if field not in {'valuation_date','strike_levels'}}
                resale = self.api(key, 'POST', '/api/products', {
                    'command_key':hashlib.sha256((self.state['id'] + case_id + '-CLIENT-PRODUCT').encode()).hexdigest(),
                    'name':case_id + ' — distribution client', 'pricing_input':contractual_input,
                    'intent':{'nominal':case['nominal'], 'side':'SELL', 'transaction_format':'EMTN', 'instrument_family':'NOTE',
                              'documentation_reference':relation['documentation_reference']},
                    'commercial':{'client_id':actor['crm']['client_id'], 'mandate_id':actor['crm']['mandate_id'],
                                  'opportunity_id':case['opportunity_id']}})
                if ProductTerms.model_validate(resale['terms']).fingerprint != case['terms_fingerprint']:
                    raise ValueError('Le dossier de distribution ne reprend pas exactement les termes figés.')
                resale_id = resale['product_id']
                case['resale_product_id'] = resale_id
            product_id = resale_id
        if product_id:
            product = self.api(key, 'GET', f'/api/products/{product_id}')
            deal.update(product_id=product_id, product_terms_version=product['terms_version'])
        if leg == "HECTOR_SELL":
            deal["client_id"] = actor["crm"]["client_id"]
            deal["mandate_id"] = actor["crm"]["mandate_id"]
            deal["opportunity_id"] = case["opportunity_id"]
        trade_ref = case["instrument_reference"] + ("-CLIENT" if leg in {"HECTOR_SELL", "CLIENT_BUY"} else "-BANK")
        result = self.api(key, "POST", "/api/trading/book-note", {"trade_reference": trade_ref,
            "relationship_id": relation["id"], "issuer": self.actor(q["bank"])["entity"], "our_side": side,
            "instrument_reference": case["instrument_reference"], "deal": deal})
        result.update(case_id=case_id, leg=leg)
        actor["deals"].append(result)
        self.state["coverage"]["notes_booking"] = "EXERCISED"
        self.mail(key, party, "Confirmation " + trade_ref, f"Booking enregistré dans mon Structura : {result['deal_reference']}.", case_id,
            {k:v for k,v in result.items() if k not in {"request_hash", "user_id", "entity_id"}})
        return result

    def risk(self, key, case_id, party, spread_bps=100, recovery=.4):
        """A real CCR hypothetical OTC calculation, separately from note books."""
        if self.actor(key)["role"] not in {"issuer","bank"}:
            raise ValueError("Le client final n'administre pas ce périmètre OTC.")
        case = self.case(key, case_id)
        relation = self.eligible(key, party)
        if not relation["otc_allowed"] or party not in self.actor(key).get("otc_sets", {}):
            raise ValueError("EXPECTED_REFUSAL : périmètre OTC/ISDA/CSA non constitué.")
        if not 0 <= float(spread_bps) <= 5000 or not 0 <= float(recovery) < 1:
            raise ValueError("Hypothèses de crédit hors bornes.")
        cp = self.cpty(key, party)
        config = self.api(key,"GET",f"/api/ccr/counterparties/{cp['id']}/configuration")
        data = {"legal_name":self.actor(party)["entity"], "counterparty_type":"Bank" if self.actor(party)["role"]=="bank" else "Broker",
            "currency":"EUR", "recovery":float(recovery), "recovery_source":"USER_ASSUMPTION",
            "curve_source":"MANUAL", "pd_measure":"RISK_NEUTRAL", "spread_curve":[[1,float(spread_bps)/10000],[3,float(spread_bps)/10000]],
            "has_isda":True,"has_csa":True}
        existing = config["profiles"][0] if config["profiles"] else None
        if existing:
            self.api(key,"PUT",f"/api/ccr/counterparties/{cp['id']}/profiles/{existing['id']}",{"data":data,"expected_version":existing["version"]})
        else:
            self.api(key,"POST",f"/api/ccr/counterparties/{cp['id']}/profiles",{"data":data})
        p = deepcopy(case["pricing"])
        p.update(script=TEMPLATES["call"]["script"], user_params={"STRIKE":1.0})
        if is_diagnostic(self.state['config']):
            strike=date.fromisoformat(self.state['business_date'])
            maturity=adjust(strike+relativedelta(years=1),'EUR',BusinessDayConvention.MODIFIED_FOLLOWING)
            p.update(strike_date=strike.isoformat(),value_date=add_business_days(strike,2,'EUR').isoformat(),
                     maturity_date=maturity.isoformat(),payment_date=add_business_days(maturity,2,'EUR').isoformat(),
                     T=(maturity-strike).days/365.25)
            from ..scenario_market import history
            tickers=[u['ticker'] for u in p['underlyings']]
            market=history(tickers,(strike-timedelta(days=7)).isoformat(),strike.isoformat(),
                           path=market_path(self.directory,self.state['config']),as_of=strike)
            if market.get('error'):raise ValueError(market['error'])
            for u in p['underlyings']:u['spot0']=market['prices'][u['ticker']][-1]
        p["constats"]={"STARTDATE":{"date":p["strike_date"]},"MATURITYDATE":p["maturity_date"]}
        ns = self.actor(key)["otc_sets"][party]
        # The test starts this hypothetical OTC perimeter with declared zero
        # collateral. Missing is not zero: persist that assumption explicitly.
        if not any(r["data"]["netting_set_id"] == ns and r["data"]["as_of_date"] == self.state["business_date"] for r in config["collateral"]):
            self.api(key,"POST",f"/api/ccr/counterparties/{cp['id']}/collateral",{"data":{
                "netting_set_id":ns,"as_of_date":self.state["business_date"],"currency":"EUR",
                "held":0,"posted":0,"im_held":0,"recognised":True,"collateral_type":"CASH",
                "source":"RECETTE — position initiale nulle déclarée pour le call OTC hypothétique"}})
        result = self.api(key,"POST","/api/ccr/calculate",{"counterparty_id":cp["id"],"netting_set_id":ns,
            "as_of_date":self.state["business_date"],"currency":"EUR","mode":"FULL","n_outer":32,"n_inner":32,"n_dates":4,
            "allow_market_fetch":False,"common_rate":.025,"common_rate_source":"TEMPORARY_ASSUMPTION",
            "proposed":{"pricing":p,"nominal":case["nominal"],"currency":"EUR","sens":"vente","product_type":"OTC_TEST_CALL","netting_set_id":ns}})
        # Full assumptions/results are archived by the native CCR endpoint.
        summary = {"date":self.state["business_date"],"party":party,"case_id":case_id,
            "scope":"HYPOTHETICAL_OTC_CALL — aucune note incluse dans ce netting set", "run_id":result.get("run_id"),
            "status":result.get("status"),"after":result.get("after"),"errors":result.get("errors"),"warnings":result.get("warnings")}
        self.actor(key).setdefault("risk_runs",[]).append(summary)
        self.state["coverage"]["otc_credit_risk"]="EXERCISED" if result.get('status')=='CALCULATED' else 'NOT_EXERCISED'
        return summary

    def settle(self, key):
        results = []
        for row in self.api(key, "GET", "/api/trading/executions"):
            if row["settlement_status"] == "PENDING" and row["value_date"] <= self.state["business_date"]:
                updated = self.api(key, "POST", f"/api/trading/executions/{row['id']}/settle", {"reference": "RECETTE-DVP-" + row["trade_reference"]})
                results.append(updated)
                for local in self.actor(key)["deals"]:
                    if local["id"] == updated["id"]:
                        local.update(updated)
        return {"settled": len(results)}

    def review(self, key):
        cadence = self.state['config'].get('cadences', {})
        diagnostic = is_diagnostic(self.state['config'])
        rows = self.api(key, "GET", "/api/deals")
        if any(row["status"] == "en_reglement" and (row.get("settlement_date") or row["payment_date"]) <= self.state["business_date"] for row in rows):
            # Ordinary user dashboard refresh also closes reached payment
            # dates; the real-time scheduler is disabled in accelerated games.
            self.api(key, "POST", "/api/alerts/refresh-book")
            rows = self.api(key, "GET", "/api/deals")
        valuations, lifecycle = [], []
        from ..scenario_market import history
        today = date.fromisoformat(self.state["business_date"])
        for row in rows:
            if row["status"] not in {"actif", "en_reglement"}:
                continue
            if row["status"] == "actif":
                refreshed = self.api(key, "POST", f"/api/deals/{row['id']}/events/refresh")
                # Sign sourced replay fixings through the ordinary audited
                # exception workflow; preserve the actual cache provenance.
                detail = self.api(key, "GET", f"/api/deals/{row['id']}")
                self.actor(key).setdefault('next_event_dates', {})[str(row['id'])] = [e['event_date'] for e in detail.get('events', []) if e['event_date']>self.state['business_date']]
                for event in detail.get("events", []):
                    if event.get("status") == "annulé" or event["event_date"] > self.state["business_date"] or event["fixing_status"] in {"VALIDATED", "APPLIED"}:
                        continue
                    self.api(key, "POST", f"/api/deals/{row['id']}/events/refresh")
                    latest = self.api(key, "GET", f"/api/deals/{row['id']}")
                    if latest["status"] != "actif":
                        break
                    event = next(e for e in latest["events"] if e["id"] == event["id"])
                    if event["fixing_status"] in {"VALIDATED", "APPLIED"}:
                        continue
                    tickers = [u["ticker"] for u in detail["underlyings"]]
                    market = history(tickers, (date.fromisoformat(event["event_date"])-timedelta(days=7)).isoformat(), event["event_date"],
                        path=market_path(self.directory,self.state['config']), as_of=today)
                    if market.get("error"):
                        raise ValueError(market["error"])
                    fixing_spots = {u['name']:market['prices'][u['ticker']][-1] for u in detail['underlyings']}
                    if event['event_date']==detail.get('strike_date'):
                        local = next(d for d in self.actor(key)['deals'] if d['deal_id']==row['id'])
                        case = self.state['cases'][local['case_id']]
                        fixing_spots = {u['name']:u['spot0'] for u in case['pricing']['underlyings']}
                    result = self.api(key, "POST", f"/api/deals/{row['id']}/events/{event['id']}/resolve-auto-exception", {
                        "action":"REPLACE_MANUAL", "expected_version_id":event.get("current_fixing_version_id"),
                        "spots": fixing_spots,
                        "source_reference":f"{market['provider']}:{self.state['id']}:{event['event_date']}:observed={json.dumps(market.get('effective_dates',{}),sort_keys=True)}",
                        "reason":"Recette : cours conservé à sa date effective, déclaré et tracé dans le circuit natif."})
                    lifecycle.append({"deal_id":row["id"], "event_date":event["event_date"], "decision":result.get("event", {}).get("fixing_status"), "source":market["provider"]})
                    if (result.get("lifecycle_proposal") or {}).get("status") == "APPLIED":
                        break
                row = self.api(key, "GET", f"/api/deals/{row['id']}")
            if row["status"] not in {"actif","en_reglement"}:
                self.actor(key).get("next_event_dates",{}).pop(str(row["id"]),None)
            cadence = self.state['config'].get('cadences', {})
            diagnostic = is_diagnostic(self.state['config'])
            last = self.actor(key).get('mtm_checkpoints', {}).get(str(row['id']))
            last_month=last.get('month') if isinstance(last,dict) else last
            last_date=last.get('date') if isinstance(last,dict) else None
            event_due=cadence.get('mtm_on_events') and any(e['deal_id']==row['id'] for e in lifecycle) and last_date!=self.state['business_date']
            due = not diagnostic or (self.state['month'] % cadence['mtm_months']==0 and last_month!=self.state['month']) or event_due or (self.state['config'].get('end_date')==self.state['business_date'] and last_date!=self.state['business_date'])
            if row["status"] in {"actif", "en_reglement"} and due:
                body = {"valuation_date":self.state["business_date"],"recalibrate":"none"}
                if diagnostic:
                    from .configuration import funding_at
                    local = next(d for d in self.actor(key)['deals'] if d['deal_id']==row['id'])
                    selected = self.state['accepted'][local['case_id']]
                    issuer = next(q['bank'] for q in self.state['quotes'] if q['id']==selected)
                    curve, _ = funding_at(self.state['config'], issuer, self.state['month'])
                    body.update(funding_curve=curve, funding_spread=0,
                                funding_source_reference=f"SCENARIO:{self.state['id']}:{issuer}:{self.state['business_date']}")
                valued = self.api(key, "POST", f"/api/deals/{row['id']}/mtm?n_paths=2000", body)
                valuations.append({"deal_id":row["id"], "date":valued.get("valuation_date"), "mtm":valued.get("mtm"), "settlement_pending":valued.get("settlement_pending",False), "provider":self.state.get("market_mode",self.state["config"].get("market_mode","synthetic"))})
                self.actor(key).setdefault('mtm_checkpoints', {})[str(row['id'])] = {'month':self.state['month'],'date':self.state['business_date']}
                self.state['usage']['mtms'] = self.state['usage'].get('mtms',0)+1
        rows = self.api(key, "GET", "/api/deals")
        positions = self.api(key, "GET", "/api/trading/positions")
        journal = self.api(key, "GET", "/api/trading/executions")
        for local in self.actor(key)["deals"]:
            current = next((x for x in journal if x["id"] == local["id"]), None)
            if current: local.update(current)
        self.actor(key)["last_review"] = {"date": self.state["business_date"], "deals": len(rows), "active_deals":sum(r['status'] in {'actif','en_reglement'} for r in rows), "positions": positions, "valuations":valuations, "fixings":lifecycle}
        self.state["coverage"]["native_mtm"] = "EXERCISED" if valuations else self.state["coverage"].get("native_mtm","NOT_EXERCISED")
        if lifecycle: self.state["coverage"]["sourced_manual_fixings"] = "EXERCISED"
        risk_checkpoint = self.actor(key).get('risk_checkpoint')
        risk_due = (not risk_checkpoint or (today-date.fromisoformat(risk_checkpoint['date'])).days >= 15) if cadence.get('risk_days')==15 else (not risk_checkpoint or risk_checkpoint['month'] != self.state['month'])
        if diagnostic and risk_due:
            self.actor(key).setdefault('risk_reports', []).append({'date':self.state['business_date'],
                'positions':positions, 'source':'NATIVE_POSITIONS', 'commentary_ia':False,
                'valuation_freshness':'CURRENT' if valuations else 'NO_NEW_MTM',
                'exposure':self.api(key,'GET','/api/portfolios/exposure-by-counterparty')})
            self.actor(key)['risk_checkpoint'] = {'date':self.state['business_date'], 'month':self.state['month']}
            self.state['usage']['risk_reports'] = self.state['usage'].get('risk_reports',0)+1
        if key == "hector" and rows and not diagnostic:
            summary = f"Suivi au {self.state['business_date']} : {len([d for d in self.actor(key)['deals'] if d['leg']=='HECTOR_SELL'])} opérations clients, {len(valuations)} valorisations, {len(lifecycle)} constatations. Les flux restent conditionnels aux constatations ; les données utilisées sont synthétiques de recette."
            self.mail(key, "client", "Suivi de vos investissements", summary)
            self.api(key, "POST", "/api/interactions", {"client_id":self.actor(key)["crm"]["client_id"],"interaction_date":self.state["business_date"],"interaction_type":"other","summary":summary})
        return self.actor(key)["last_review"]

    def browser_action(self, key, action="observe", path="/", selector="", value=""):
        page = self.page(key)
        if action == "open":
            if not path.startswith("/") or path.startswith("//") or ":" in path:
                raise ValueError("Une page locale de ton Structura est requise.")
            page.goto(self.actor(key)["url"] + "/#" + path)
        elif action == "click":
            page.locator(selector).click()
        elif action == "fill":
            page.locator(selector).fill(value)
        elif action != "observe":
            raise ValueError("Action navigateur inconnue.")
        if urlparse(page.url).netloc != urlparse(self.actor(key)["url"]).netloc:
            raise ValueError("La navigation a quitté ton instance.")
        return {"url": page.url, "text": page.locator("body").inner_text()[:7000],
            "fields": page.locator("input,select,textarea").evaluate_all("els=>els.filter(e=>e.offsetParent!==null).map(e=>({tag:e.tagName,type:e.type,placeholder:e.placeholder,name:e.name,id:e.id}))"),
            "screenshot": self.screenshot(key)}

    def help(self, key, query="", remember=True):
        """Read current application capabilities from its actual OpenAPI."""
        response = self.http.get(self.actor(key)["url"] + "/openapi.json")
        response.raise_for_status()
        specification = response.json()
        matches = []
        words = query.lower().split()
        for path, operations in specification.get("paths", {}).items():
            for method, operation in operations.items():
                text = path + " " + operation.get("summary", "") + " " + operation.get("description", "")
                if words and not any(word in text.lower() for word in words):
                    continue
                schema = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
                if "$ref" in schema:
                    schema = specification.get("components", {}).get("schemas", {}).get(schema["$ref"].rsplit("/",1)[1], {})
                matches.append({"path":path,"method":method.upper(),"summary":operation.get("summary"),
                    "description":operation.get("description", "")[:900], "body_schema":schema,
                    "parameters":operation.get("parameters", [])})
        discovered = matches[:8]
        if remember:
            self.actor(key)['api_capabilities'] = discovered
        return {"source":"OpenAPI de l'instance en cours", "total_paths":len(specification.get("paths",{})),
            "matching_operations":len(matches), "operations":discovered}

    def execute(self, key, tool, args):
        self.calls = []
        if tool != "register" and key not in self.tokens and not (key=='achille' and tool in {'mail','report'}):
            raise ValueError("Utiliser register pour créer ou reconnecter ton compte.")
        methods = {"register": self.register, "relationship": self.relationship, "crm": self.crm, "reprice":self.reprice,
            "propose":self.propose, "request": self.request, "rfq": self.rfq, "quote": self.quote, "decline":self.decline, "offer": self.offer,
            "client_accept": self.client_accept, "accept_quote": self.accept_quote, "confirm_trade":self.confirm_trade, "book": self.book,
            "settle": self.settle, "review": self.review, "browser": self.browser_action, "help":self.help, "risk":self.risk}
        if tool in methods:
            result = methods[tool](key, **args)
            if tool == 'browser' and args.get('action') == 'click':
                result['native_refresh'] = self.refresh_native_facts(key)
            return result
        if tool == "mail":
            return self.mail(key, **args, kind="MESSAGE")
        if tool == "api":
            result = self.api(key, args.get("method", "GET"), args["path"], args.get("body"))
            if args.get('method', 'GET').upper() != 'GET':
                self.refresh_native_facts(key)
            return result
        if tool == "report":
            row = {"id": uuid4().hex, "actor": key, "kind": args.get("kind", "IMPROVEMENT"),
                "description": args["description"], "date": self.state["business_date"], "source": "AGENT"}
            self.state["incidents"].append(row)
            return row
        if tool == "wait":
            return {"waiting": True, "explanation": args.get("explanation", "Attente d'un message")}
        raise ValueError("Outil inconnu : " + tool)
