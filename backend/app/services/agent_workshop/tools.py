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
from dateutil.relativedelta import relativedelta
from ...core.payscript.templates import TEMPLATES
from ...core.calendars import adjust, add_business_days, BusinessDayConvention
from .store import contract_mandate


class Tools:
    def __init__(self, directory, state, browser, provision_owner=None, on_activity=None):
        self.directory, self.state, self.browser = directory, state, browser
        self.contexts, self.pages, self.tokens = {}, {}, {}
        self.http = httpx.Client(timeout=90, trust_env=False)
        self.calls = []
        self.provision_owner = provision_owner
        self.on_activity = on_activity

    def notify_request(self, key, request):
        if self.on_activity:
            self.on_activity(key, request, self.calls[:])

    def close(self):
        for context in self.contexts.values():
            context.close()
        self.http.close()

    def actor(self, key):
        if key not in self.state["actors"]:
            raise ValueError("Intervenant inconnu.")
        return self.state["actors"][key]

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
        name = f"{key}-{len(self.state['actions']):05d}.png"
        self.page(key).screenshot(path=str(directory / name), full_page=False)
        return name

    def mail(self, key, to, subject, body, case_id="", attachment=None):
        self.actor(to)
        if to == key:
            raise ValueError("Choisir un autre destinataire.")
        if len(body) > 6000 or len(subject) > 250:
            raise ValueError("Message trop long.")
        row = {"id": uuid4().hex, "from": key, "to": to, "subject": subject, "body": body,
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
        if secret_file.exists():
            credentials = json.loads(secret_file.read_text(encoding="utf-8"))
        else:
            credentials = {"username": "agent_" + key, "email": key + "@recette.invalid", "password": secrets.token_urlsafe(16)}
            secret_file.write_text(json.dumps(credentials), encoding="utf-8")
        page = self.page(key)
        page.goto(actor["url"] + "/#/login")
        if actor["registered"]:
            page.locator('input[type="text"]').fill(credentials["username"])
            page.locator('input[type="password"]').fill(credentials["password"])
            page.get_by_role("button", name="Se connecter", exact=True).click()
        else:
            page.get_by_role("button", name="Créer un compte", exact=True).click()
            page.get_by_placeholder("ex: jdupont").fill(credentials["username"])
            page.get_by_placeholder("ex: j.dupont@banque.fr").fill(credentials["email"])
            page.locator('input[type="password"]').nth(0).fill(credentials["password"])
            page.locator('input[type="password"]').nth(1).fill(credentials["password"])
            page.get_by_placeholder("ex: Desk Structuration").fill(actor["entity"])
            page.get_by_role("button", name="Créer mon compte", exact=True).click()
        page.wait_for_function("Boolean(localStorage.getItem('auth_token'))")
        self.tokens[key] = page.evaluate("localStorage.getItem('auth_token')")
        who = self.api(key, "GET", "/api/auth/me")
        if self.provision_owner:
            self.provision_owner(key, who["id"])
            who = self.api(key, "GET", "/api/auth/me")
        actor["account_role"] = who["role"]
        actor["registered"] = True; actor["online"] = True
        actor["username"] = who["username"]; actor["entity_id"] = who["entity_id"]
        actor["status"] = "Connecté"
        self.state["coverage"]["registration_ui"] = "EXERCISED"
        return {"username": who["username"], "entity_id": who["entity_id"], "account_role": who["role"], "channel": "UI", "screenshot": self.screenshot(key)}

    def relationship(self, key, party, status="ACTIVE", otc=False):
        mandate=contract_mandate(self.state).get(party if key=='hector' else key,{'note_ready':True,'otc_ready':False})
        if not mandate['note_ready']:
            status = "PENDING"
        if not mandate['otc_ready']:otc=False
        cp = self.cpty(key, party)
        existing = self.relation(key, party)
        fields = {"counterparty_id": cp["id"], "reference": f"REL-{self.state['id'][:8]}-{sorted([key, party])[0]}-{sorted([key, party])[1]}",
            "status": status, "effective_date": self.state["config"]["start_date"],
            "note_distribution_allowed": True, "documentation_reference":
                "Programme de notes et convention de distribution — recette" if status == "ACTIVE" else "",
            "gross_notional_limit": max(self.state["config"]["target_volume"] * 4, self.state['config']['ticket']*self.state['config']['months']*3),
            "notes": "Données fictives de recette ; documentation incomplète." if status == "PENDING" else "Relation de recette négociée par les agents."}
        if existing:
            otc = otc or existing['otc_allowed']
            if existing['status']==status and (not otc or existing['otc_allowed']):
                if otc:
                    config=self.api(key,'GET',f"/api/ccr/counterparties/{cp['id']}/configuration")
                    ns=next((n for n in config['netting-sets'] if n['data'].get('netting_set_id')==existing['reference']+'-OTC'),None)
                    if ns:self.actor(key).setdefault('otc_sets',{})[party]=ns['id']
                self.actor(key)['relations'][party]=existing
                return existing
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
        if key != "hector":
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

    def request(self, key, template="reverse_convertible", coupon=8, barrier=60):
        if key != "client" or template not in {"reverse_convertible", "phoenix"}:
            raise ValueError("Besoin réservé au client et à un produit qualifié du catalogue.")
        month = self.state["month"]
        previous = next((x for x in self.state["cases"].values() if x["month"] == month), None)
        if previous:
            return previous
        if not 0 <= float(coupon) <= 30 or not 1 <= float(barrier) <= 100:
            raise ValueError("Coupon ou barrière hors bornes de recette.")
        case_id = "CASE-" + str(month + 1).zfill(3)
        strike = adjust(date.fromisoformat(self.state["business_date"]), "EUR", BusinessDayConvention.FOLLOWING)
        maturity = adjust(strike + relativedelta(months=6), "EUR", BusinessDayConvention.MODIFIED_FOLLOWING)
        pricing = {"script": TEMPLATES[template]["script"], "underlyings": [{"name": "S1", "ticker": "AIR.PA", "ccy": "EUR",
            "spot0": 100, "sigma": .23, "q": .02}], "corr_matrix": [[1]], "model": "constant", "r": .025,
            "N": 2000, "T": (maturity-strike).days/365.25, "user_params": {"COUPON": float(coupon)/100, "M_KI_BAR": float(barrier)/100},
            "anchor": strike.isoformat(), "strike_date": strike.isoformat(), "value_date": strike.isoformat(),
            "maturity_date": maturity.isoformat(), "payment_date": add_business_days(maturity, 3, "EUR").isoformat(),
            "settlement_ccy": "EUR", "constats": {"STARTDATE": {"date": strike.isoformat()}, "MATURITYDATE": maturity.isoformat()}}
        from ..scenario_market import history
        market = history(["AIR.PA"], (strike-timedelta(days=7)).isoformat(),
            self.state["business_date"], path=self.directory / "synthetic_market.json", as_of=date.fromisoformat(self.state["business_date"]))
        if market.get("error"):
            raise ValueError(market["error"])
        pricing["underlyings"][0]["spot0"] = market["prices"]["AIR.PA"][-1]
        if template == "phoenix":
            pricing["user_params"].update(M_AC_BAR=1.0, M_CPN_BAR=.70)
            pricing["constats"].pop("MATURITYDATE")
            pricing["constats"]["OBSERVATIONDATES"] = {"period_start_date": strike.isoformat(),
                "first_observation_date": (strike+relativedelta(months=3)).isoformat(), "end_date": maturity.isoformat(),
                "roll_date": strike.isoformat(), "frequency": "3M", "stub": "short_last", "business_day_convention": "MODIFIED_FOLLOWING"}
        case = {"id": case_id, "month": month, "template": template, "nominal": self.state["config"]["ticket"],
            "pricing": pricing, "source": "Marché synthétique explicite de recette, pas un prix historique réel.",
            "rfq_sent": False, "declines": [], "instrument_reference": f"NOTE-{self.state['id'][:8]}-{case_id}"}
        self.state["cases"][case_id] = case
        self.mail(key, "hector", "Besoin d'investissement " + case_id,
            f"Je souhaite investir {case['nominal']:,.0f} EUR en {template}, coupon {coupon} %, barrière {barrier} %. Merci de me proposer les conditions.", case_id, deepcopy(case))
        return {"case_id": case_id, "nominal": case["nominal"], "template": template}

    def case(self, key, case_id):
        case = self.state["cases"].get(case_id)
        if not case:
            raise ValueError("Besoin inconnu.")
        if key not in {"client", "hector"} and not any(m["to"] == key and m["case_id"] == case_id for m in self.state["messages"]):
            raise ValueError("Ce besoin n'a pas été communiqué à cet agent.")
        return case

    def price(self, key, case, spread=0, refresh=False):
        actor = self.actor(key)
        if case["id"] in actor["prices"] and not refresh:
            return actor["prices"][case["id"]]
        payload = deepcopy(case["pricing"])
        payload["funding_spread"] = float(spread)
        result = self.api(key, "POST", "/api/price", payload)
        stored = {"input": payload, "result": result}
        directory = self.directory / "instances" / key / "pricing"
        directory.mkdir(exist_ok=True)
        (directory / (case["id"] + ".json")).write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        actor["prices"][case["id"]] = {"price_pct": result["price"] * 100, "path": case["id"] + ".json"}
        self.state["coverage"]["native_pricing"] = "EXERCISED"
        return actor["prices"][case["id"]]

    def reprice(self, key, case_id):
        result = self.price(key, self.case(key, case_id), refresh=True)
        return {**result,"case_id":case_id,"message":"Nouveau calcul natif conservé ; les accords de prix restent inchangés."}

    def rfq(self, key, case_id):
        if key != "hector":
            raise ValueError("Hector prépare cet AO.")
        case = self.case(key, case_id)
        if case["rfq_sent"]:
            return {"rfq_id": case["rfq_id"], "already_sent": True}
        banks = [k for k,a in self.state["actors"].items() if a["role"] == "bank"]
        for bank in banks:
            if not self.relation(key, bank):
                raise ValueError("Préparer toutes les relations avant cet AO.")
        if not self.actor(key)["crm"]:
            raise ValueError("Créer le dossier client avant l'AO.")
        opportunity = self.api(key, "POST", "/api/opportunities", {"client_id": self.actor(key)["crm"]["client_id"],
            "mandate_id":self.actor(key)["crm"]["mandate_id"],
            "title": case_id + " — investissement", "amount": case["nominal"], "data_origin": "demo",
            "payoff_family": "Reverse convertible" if case["template"] == "reverse_convertible" else "Phoenix"})
        case["opportunity_id"] = opportunity["id"]
        rfq = self.api(key, "POST", "/api/rfq", {"name": case_id, "kind": "to_trade", "sens": "achat",
            "script_snapshot": case["pricing"]["script"], "params": {**case["pricing"], "currency": "EUR", "notional": case["nominal"]},
            "transaction_format": "EMTN", "instrument_family": "NOTE", "documentation_reference":
                next((r["documentation_reference"] for r in self.actor(key)["relations"].values() if r["status"] == "ACTIVE"), "")})
        case["rfq_id"] = rfq["id"]
        case["rfq_sent"] = True
        for bank in banks:
            self.mail(key, bank, "Demande de prix " + case_id, "Merci de coter la note jointe avec vos conditions et validité.", case_id, deepcopy(case))
        return {"rfq_id": rfq["id"], "recipients": banks}

    def quote(self, key, case_id, margin_bps=30):
        if self.actor(key)["role"] != "bank":
            raise ValueError("Seule une banque cote cet AO.")
        case = self.case(key, case_id)
        existing = next((q for q in self.state["quotes"] if q["bank"] == key and q["case_id"] == case_id), None)
        if existing:
            return existing
        try:
            self.eligible(key, "hector")
        except ValueError as exc:
            if key not in case["declines"]:
                case["declines"].append(key)
                self.mail(key, "hector", "Cotation refusée " + case_id, str(exc), case_id)
            if all(k in case['declines'] for k,a in self.state['actors'].items() if a['role']=='bank'):
                case['outcome']='NO_QUOTE'
            raise
        margin = float(margin_bps)
        if not -100 <= margin <= 1000:
            raise ValueError("Marge hors limites de recette.")
        price = self.price(key, case)
        q = {"id": uuid4().hex[:12], "bank": key, "case_id": case_id,
            "price": round(price["price_pct"] + margin/100, 6), "currency": "EUR", "nominal": case["nominal"],
            "valid_until": self.state["business_date"] + "T17:00:00", "firmness": "FIRM"}
        self.state["quotes"].append(q)
        self.mail(key, "hector", "Réponse ferme " + case_id,
            f"Prix proposé {q['price']:.6f} % du nominal, EUR, valable jusqu'à {q['valid_until']}.", case_id, deepcopy(q))
        return q

    def decline(self, key, case_id, explanation):
        if self.actor(key)['role']!='bank' or len(explanation.strip())<5:
            raise ValueError('Une banque doit expliquer son refus de cotation.')
        case=self.case(key,case_id)
        if any(q['bank']==key and q['case_id']==case_id for q in self.state['quotes']):
            raise ValueError('Une cotation ferme existe déjà ; son retrait requiert un workflow distinct.')
        relationship=self.relation(key,'hector')
        if key not in case['declines']:
            case['declines'].append(key)
            self.mail(key,'hector','Refus de cotation '+case_id,explanation,case_id,{'declined':True,'relationship_status':relationship['status'] if relationship else 'MISSING'})
        if not relationship or relationship['status']!='ACTIVE':
            self.state['coverage']['incomplete_relationship']='DECLINED_WITH_LEGAL_EVIDENCE'
        banks=[k for k,a in self.state['actors'].items() if a['role']=='bank']
        if all(k in case['declines'] for k in banks): case['outcome']='NO_QUOTE'
        return {'case_id':case_id,'declined':True,'explanation':explanation}

    def received_quote(self, key, quote_id):
        quote = next((q for q in self.state["quotes"] if q["id"] == quote_id), None)
        if not quote or (key not in {"hector", quote["bank"]}):
            raise ValueError("Cotation non accessible à cet agent.")
        return quote

    def offer(self, key, quote_id, margin_bps=40, justification=""):
        if key != "hector" or len(justification.strip()) < 5:
            raise ValueError("Hector doit motiver son choix.")
        quote = self.received_quote(key, quote_id)
        case = self.case(key, quote["case_id"])
        if case["id"] in self.state["client_acceptances"]:
            raise ValueError("L'offre acceptée est figée ; ouvrir un nouveau besoin pour changer ses termes.")
        self.eligible(key, quote["bank"])
        expected = [k for k,a in self.state["actors"].items() if a["role"] == "bank"]
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
        self.mail(key, "hector", ("Acceptation " if accept else "Refus ") + case_id, explanation, case_id,
            {"accept": accept, "offer": deepcopy(self.state["client_offers"][case_id])})
        return {"accepted": accept, "case_id": case_id}

    def accept_quote(self, key, quote_id, justification=""):
        if key != "hector" or len(justification.strip()) < 5:
            raise ValueError("Hector doit motiver l'acceptation.")
        quote = self.received_quote(key, quote_id)
        case = self.case(key, quote["case_id"])
        if case["id"] not in self.state["client_acceptances"] or self.state["client_offers"][case["id"]]["quote_id"] != quote_id:
            raise ValueError("Attendre l'accord client sur cette offre.")
        self.eligible(key, quote["bank"])
        self.price(key, case)
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

    def book(self, key, case_id, leg):
        case = self.case(key, case_id)
        accepted_id = self.state["accepted"].get(case_id)
        if not accepted_id:
            raise ValueError("Aucun accord ferme pour cette opération.")
        if key == "client" and leg == "CLIENT_BUY" and case_id in self.state["client_acceptances"]:
            q = next(x for x in self.state["quotes"] if x["id"] == accepted_id)
        else:
            q = self.received_quote(key, accepted_id)
        if leg == "BANK_SELL" and key == q["bank"]:
            party, side, trade_price = "hector", "SELL", q["price"]
        elif leg == "HECTOR_BUY" and key == "hector":
            party, side, trade_price = q["bank"], "BUY", q["price"]
        elif leg == "HECTOR_SELL" and key == "hector":
            party, side, trade_price = "client", "SELL", self.state["client_offers"][case_id]["client_price"]
        elif leg == "CLIENT_BUY" and key == "client":
            party, side, trade_price = "hector", "BUY", self.state["client_offers"][case_id]["client_price"]
        else:
            raise ValueError("Cette jambe appartient à un autre acteur.")
        actor = self.actor(key)
        previous = next((d for d in actor["deals"] if d["case_id"] == case_id and d["leg"] == leg), None)
        if previous:
            return previous
        relation = self.eligible(key, party)
        self.price(key, case)
        saved = json.loads((self.directory / "instances" / key / "pricing" / (case_id + ".json")).read_text(encoding="utf-8"))
        p, r = saved["input"], saved["result"]
        deal = {"sens": "vente" if side == "BUY" else "achat", "contrepartie": self.actor(party)["entity"],
            "devise": "EUR", "product_type": TEMPLATES[case["template"]]["label"], "nominal": case["nominal"],
            "fair_value": r["price"]*100, "price_traded": trade_price, "trade_date": self.state["business_date"],
            **{field:p[field] for field in ("strike_date", "value_date", "maturity_date", "payment_date", "T")},
            "underlyings": [{**u, "s0_abs": u["spot0"]} for u in p["underlyings"]], "observation_times": [],
            "script_snapshot": p["script"], "market_snapshot": {"constats": p["constats"], "user_params": p["user_params"]},
            "pricing_receipt": r["pricing_receipt"], "transaction_format": "EMTN", "instrument_family": "NOTE",
            "documentation_reference": relation["documentation_reference"]}
        if leg == "HECTOR_BUY":
            deal["rfq_id"] = case["rfq_id"]
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
        self.state["coverage"]["otc_credit_risk"]="EXERCISED"
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
        rows = self.api(key, "GET", "/api/deals")
        if any(row["status"] == "en_reglement" and row["payment_date"] <= self.state["business_date"] for row in rows):
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
                # Sign explicit synthetic fixings using Structura's ordinary,
                # audited manual-exception workflow. Never call them Yahoo.
                detail = self.api(key, "GET", f"/api/deals/{row['id']}")
                for event in detail.get("events", []):
                    if event["event_date"] > self.state["business_date"] or event["fixing_status"] in {"VALIDATED", "APPLIED"}:
                        continue
                    self.api(key, "POST", f"/api/deals/{row['id']}/events/refresh")
                    latest = self.api(key, "GET", f"/api/deals/{row['id']}")
                    event = next(e for e in latest["events"] if e["id"] == event["id"])
                    if event["fixing_status"] in {"VALIDATED", "APPLIED"}:
                        continue
                    tickers = [u["ticker"] for u in detail["underlyings"]]
                    market = history(tickers, (date.fromisoformat(event["event_date"])-timedelta(days=7)).isoformat(), event["event_date"],
                        path=self.directory / "synthetic_market.json", as_of=today)
                    if market.get("error"):
                        raise ValueError(market["error"])
                    result = self.api(key, "POST", f"/api/deals/{row['id']}/events/{event['id']}/resolve-auto-exception", {
                        "action":"REPLACE_MANUAL", "expected_version_id":event.get("current_fixing_version_id"),
                        "spots": {u["name"]:market["prices"][u["ticker"]][-1] for u in detail["underlyings"]},
                        "source_reference":f"SYNTHETIC_SCENARIO:{self.state['id']}:{event['event_date']}:seed={self.state['config']['seed']}",
                        "reason":"Recette : déclaration explicite du fixing synthétique commun aux parties, sans donnée Yahoo."})
                    lifecycle.append({"deal_id":row["id"], "event_date":event["event_date"], "decision":result.get("event", {}).get("fixing_status"), "source":"SYNTHETIC_SCENARIO"})
                    if (result.get("lifecycle_proposal") or {}).get("status") == "APPLIED":
                        break
                row = self.api(key, "GET", f"/api/deals/{row['id']}")
            if row["status"] in {"actif", "en_reglement"}:
                valued = self.api(key, "POST", f"/api/deals/{row['id']}/mtm?n_paths=2000", {"valuation_date":self.state["business_date"],"recalibrate":"none"})
                valuations.append({"deal_id":row["id"], "date":valued.get("valuation_date"), "mtm":valued.get("mtm"), "settlement_pending":valued.get("settlement_pending",False), "provider":"SYNTHETIC_SCENARIO"})
        positions = self.api(key, "GET", "/api/trading/positions")
        journal = self.api(key, "GET", "/api/trading/executions")
        for local in self.actor(key)["deals"]:
            current = next((x for x in journal if x["id"] == local["id"]), None)
            if current: local.update(current)
        self.actor(key)["last_review"] = {"date": self.state["business_date"], "deals": len(rows), "positions": positions, "valuations":valuations, "fixings":lifecycle}
        self.state["coverage"]["native_mtm"] = "EXERCISED" if valuations else self.state["coverage"].get("native_mtm","NOT_EXERCISED")
        if lifecycle: self.state["coverage"]["sourced_manual_fixings"] = "EXERCISED"
        if key == "hector" and rows:
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

    def help(self, key, query=""):
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
        return {"source":"OpenAPI de l'instance en cours", "total_paths":len(specification.get("paths",{})),
            "matching_operations":len(matches), "operations":matches[:8]}

    def execute(self, key, tool, args):
        self.calls = []
        if tool != "register" and key not in self.tokens and not (key=='achille' and tool in {'mail','report'}):
            raise ValueError("Utiliser register pour créer ou reconnecter ton compte.")
        methods = {"register": self.register, "relationship": self.relationship, "crm": self.crm, "reprice":self.reprice,
            "propose":self.propose, "request": self.request, "rfq": self.rfq, "quote": self.quote, "decline":self.decline, "offer": self.offer,
            "client_accept": self.client_accept, "accept_quote": self.accept_quote, "book": self.book,
            "settle": self.settle, "review": self.review, "browser": self.browser_action, "help":self.help, "risk":self.risk}
        if tool in methods:
            return methods[tool](key, **args)
        if tool == "mail":
            return self.mail(key, **args)
        if tool == "api":
            return self.api(key, args.get("method", "GET"), args["path"], args.get("body"))
        if tool == "report":
            row = {"id": uuid4().hex, "actor": key, "kind": args.get("kind", "IMPROVEMENT"),
                "description": args["description"], "date": self.state["business_date"], "source": "AGENT"}
            self.state["incidents"].append(row)
            return row
        if tool == "wait":
            return {"waiting": True, "explanation": args.get("explanation", "Attente d'un message")}
        raise ValueError("Outil inconnu : " + tool)
