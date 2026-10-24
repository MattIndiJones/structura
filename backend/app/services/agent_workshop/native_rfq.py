"""Simulation adapter for the existing authenticated bilateral RFQ workflow."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import time
from uuid import uuid4


def requester(case):
    return case.get('requester', 'hector')


def command(state, case, action):
    return hashlib.sha256(f"{state['id']}:{case['id']}:{action}".encode()).hexdigest()


class NativeRfq:
    def __init__(self, tools):
        self.tools = tools
        self.checkers = {}

    def wait(self, fetch, ready, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            value = fetch()
            if ready(value):
                return value
            if time.monotonic() >= deadline:
                raise ValueError('Synchronisation RFQ encore en attente ; reprendre la même demande sans recréer les objets.')
            time.sleep(.2)

    def pair(self, sender, bank):
        t = self.tools
        left, right = t.actor(sender), t.actor(bank)
        a, b = t.relation(sender, bank), t.relation(bank, sender)
        if not a or not b or a['status'] != 'ACTIVE' or b['status'] != 'ACTIVE':
            raise ValueError('EXPECTED_REFUSAL : les deux accords de distribution doivent être actifs avant appairage RFQ.')
        terms = {'formats':['EMTN'], 'instruments':['NOTE'], 'payoff_families':['Reverse convertible','Phoenix','Autocall'],
                 'currencies':['EUR'], 'effective_date':t.state['config']['start_date'],
                 'solicitation_allowed':True, 'indicative_allowed':True, 'to_trade_allowed':True,
                 'treatment_allowed':True, 'documentation_reference':a['documentation_reference']}
        references = {}
        for key, peer, booking in ((sender, bank, a), (bank, sender, b)):
            actor = t.actor(key)
            directory = actor['rfq_directory']
            partner = directory[bank] if key == sender else {'entity_id':actor['entity_id'], 'desk_id':actor['pilot_desk_id']}
            owner = actor['entity_id'] if key == sender else directory[sender]['entity_id']
            reference = 'SIM-' + sender + '-' + bank
            rows = t.api(key, 'GET', '/api/rfq-relations')
            row = next((r for r in rows if r['reference'] == reference), None)
            if row is None:
                row = t.api(key, 'POST', '/api/rfq-relations', {
                    'requester_entity_id':owner, 'partner_entity_id':partner['entity_id'],
                    'receiver_desk_id':partner['desk_id'], 'reference':reference, 'terms':terms,
                    'counterparty_id':t.cpty(key, peer)['id'], 'trading_relationship_id':booking['id'],
                    'reason':'Appairage explicite des installations privées de simulation'})
            if not row['local']['recognized']:
                row = t.api(key, 'POST', f"/api/rfq-relations/{row['id']}/recognize", {
                    'expected_version':row['version'], 'reason':'Accord de recette fictif approuvé dans le périmètre déclaré'})
            references[key] = row
        directories = {key:t.api(key, 'GET', '/api/rfq-transport/channels') for key in (sender, bank)}
        channels = {key:next((c for c in directories[key]['channels'] if c['relationship_id'] == references[key]['id']), None)
                    for key in (sender, bank)}
        private = t.directory / 'instances' / sender / ('channel-' + bank + '.json')
        if channels[sender] is None:
            channels[sender] = t.api(sender, 'POST', '/api/rfq-transport/channels', {
                'relationship_id':references[sender]['id'], 'expected_version':references[sender]['version'],
                'role':'REQUESTER', 'peer_installation_id':directories[bank]['installation_id'],
                'peer_url':right['url'], 'peer_counterparty_id':t.cpty(sender, bank)['id'],
                'reason':'Canal de simulation local signé ; aucune ouverture de production'})
            private.write_text(json.dumps(channels[sender]['pairing']), encoding='utf-8')
        if channels[bank] is None:
            secret = json.loads(private.read_text(encoding='utf-8'))
            channels[bank] = t.api(bank, 'POST', '/api/rfq-transport/channels', {
                'relationship_id':references[bank]['id'], 'expected_version':references[bank]['version'],
                'role':'BANK', 'peer_installation_id':directories[sender]['installation_id'], 'peer_url':left['url'],
                'channel_id':secret['channel_id'], 'secret':secret['secret'],
                'peer_counterparty_id':t.cpty(bank, bank)['id'], 'reason':'Import explicite du canal privé de simulation'})
        if channels[sender]['peer_url'] != right['url'] or channels[bank]['peer_url'] != left['url']:
            raise ValueError('Les adresses du canal ont changé ; reconfigurer explicitement avant reprise.')
        t.api(sender, 'POST', f"/api/rfq-transport/channels/{channels[sender]['id']}/probe")
        return references[sender]['id']

    def send(self, key, case, rfq):
        t = self.tools
        banks = []
        for bank in t.responders(case):
            try:
                t.eligible(key, bank); t.eligible(bank, key)
            except ValueError as exc:
                if 'EXPECTED_REFUSAL' not in str(exc):
                    raise
                if bank not in case['declines']:
                    case['declines'].append(bank)
                case.setdefault('expected_refusals', {})[bank] = str(exc)
            else:
                banks.append(bank)
        if not banks:
            case['outcome']='NO_QUOTE'
            return {'expected_refusal':True, 'reason':'Aucun destinataire juridiquement éligible.'}
        relations = [self.pair(key, bank) for bank in banks]
        payload = {'expected_terms_version':rfq['product_terms_version'], 'shared_title':case['id'],
                   'response_deadline':case['pricing']['strike_date'] + 'T18:00:00Z', 'relationship_ids':relations}
        preview = t.api(key, 'POST', f"/api/rfq/{rfq['id']}/exchange-preview", payload)
        sent = t.api(key, 'POST', f"/api/rfq/{rfq['id']}/send", {
            **payload, 'command_key':command(t.state, case, 'SEND'), 'expected_preview_hash':preview['preview_hash']})
        case['terms_fingerprint'] = preview['request']['terms_fingerprint']
        case['exchange_terms'] = preview['request']['terms']
        case.setdefault('native_products', {})[key] = rfq['product_id']
        case['native_terms_version'] = rfq['product_terms_version']
        case['network_state'] = 'QUEUED'
        for bank in banks:
            rows = self.wait(lambda:t.api(bank, 'GET', '/api/rfq-inbox'),
                             lambda rows:any(r['title'] == case['id'] and r['requester']['organization'] == t.actor(key)['entity'] for r in rows))
            item = next(r for r in rows if r['title'] == case['id'] and r['requester']['organization'] == t.actor(key)['entity'])
            case.setdefault('inbox_ids', {})[bank] = item['id']
        case['network_state'] = 'DELIVERED'
        t.state['coverage']['inter_entity_rfq_network'] = 'EXERCISED'
        return sent

    def bank_product(self, key, case):
        t = self.tools
        item = case['inbox_ids'][key]
        received = t.api(key, 'POST', f'/api/rfq-inbox/{item}/claim')
        if received['case']['terms_fingerprint'] != case['terms_fingerprint']:
            raise ValueError('Les termes reçus ne correspondent pas à la demande figée.')
        t.api(key, 'POST', f'/api/rfq-inbox/{item}/read')
        case.setdefault('native_products', {})[key] = received['case']['product_id']
        return received

    def validate_as_checker(self, key, item, decision):
        t = self.tools
        if key not in self.checkers:
            credentials = json.loads((t.directory / 'instances' / key / 'checker_credentials.json').read_text(encoding='utf-8'))
            context = t.browser.new_context(viewport={'width':1280, 'height':850}, locale='fr-FR')
            t.contexts[key + '_checker'] = context
            page = context.new_page()
            page.goto(t.actor(key)['url'] + '/#/login')
            page.locator('input[type="text"]').fill(credentials['username'])
            page.locator('input[type="password"]').fill(credentials['password'])
            with page.expect_event('load'):
                page.get_by_role('button', name='Se connecter', exact=True).click()
            token = page.evaluate("sessionStorage.getItem('auth_token')")
            if not token:
                raise ValueError('Le contrôleur de publication ne dispose pas de session propre.')
            self.checkers[key] = token
        path = f'/api/rfq-inbox/{item}/validate'
        response = t.http.post(t.actor(key)['url'] + path, headers={'Authorization':'Bearer ' + self.checkers[key]}, json=decision)
        t.calls.append({'method':'POST', 'path':path, 'status':response.status_code, 'profile':'checker'})
        response.raise_for_status()
        return response.json()

    def publish(self, key, case, price):
        t = self.tools
        item = case['inbox_ids'][key]
        received = t.api(key, 'GET', f'/api/rfq-inbox/{item}')
        policy = received.get('publication_policy') or {}
        diagnostic = t.state['config'].get('schema_version') == 2
        if not policy.get('version') or (not diagnostic and not policy.get('second_validation_required')):
            t.api(key, 'PUT', f'/api/rfq-inbox/{item}/publication-policy', {
                'expected_version':policy.get('version', 0), 'second_validation_required':not diagnostic,
                'max_calculation_age_minutes':60, 'reason':'Politique explicite du desk fictif de diagnostic'})
        revision = (received.get('quote_draft') or {}).get('revision', 0)
        calculation = t.actor(key)['prices'][case['id']]['calculation_id']
        draft = t.api(key, 'PUT', f'/api/rfq-inbox/{item}/quote-draft', {
            'expected_revision':revision, 'calculation_id':calculation, 'price':price, 'firmness':'FIRM',
            'valid_until':case['pricing']['strike_date'] + 'T17:00:00Z', 'conditions_type':'NONE',
            'issuer_name':t.actor(key)['entity'], 'documentation_reference':t.relation(key, requester(case))['documentation_reference'],
            'comment':'Cotation fictive calculée dans cette installation privée'})
        decision = {'expected_revision':draft['quote_draft']['revision'], 'expected_payload_hash':draft['quote_draft']['payload_hash']}
        if not diagnostic or policy.get('second_validation_required'):
            self.validate_as_checker(key, item, decision)
        else:
            t.api(key, 'POST', f'/api/rfq-inbox/{item}/validate', decision)
        t.api(key, 'POST', f'/api/rfq-inbox/{item}/publish', decision)
        rows = self.wait(lambda:t.api(requester(case), 'GET', f"/api/rfq/{case['rfq_id']}"),
                         lambda r:any(q['provider'] == t.actor(key)['entity'] and q['status'] == 'recu' for q in r['quotes']))
        if not diagnostic:
            t.state['coverage']['bank_second_validation'] = 'EXERCISED'
        return next(q for q in rows['quotes'] if q['provider'] == t.actor(key)['entity'] and q['status'] == 'recu')
