"""Isolated, authenticated RFQ pilot on three native Structura installations.

Run from the repository root with .venv/Scripts/python.exe. No pytest fixtures,
mock prices, external data download or user database are used. Every run creates
a fresh directory under tmp/rfq-lot8. HTTPS uses a disposable private CA, with
certificate and hostname verification enabled. Only the QA runtime supplies
this trust anchor to native transport clients; production trust is unchanged.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def utc():
    return datetime.now(timezone.utc)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def certificates(work):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Structura isolated RFQ QA")])
    ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(utc()-timedelta(minutes=5)).not_valid_after(utc()+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(key, hashes.SHA256()))
    (work/"ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for name in ("requester", "bnp", "socgen"):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name+".qa.invalid")]))
                .issuer_name(ca.subject).public_key(private.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(utc()-timedelta(minutes=5))
                .not_valid_after(utc()+timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                .sign(key, hashes.SHA256()))
        directory = work/name
        directory.mkdir()
        (directory/"cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (directory/"key.pem").write_bytes(private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def serve(work, name, port, ui_port):
    """Native server with a private CA adapter and a loopback UI reverse proxy."""
    work=work.resolve()
    assert (ROOT/'tmp'/'rfq-lot8').resolve() in work.parents, 'QA server requires its isolated run directory'
    assert (work/name/'structura.db').is_file(), 'An explicitly seeded QA database is required'
    os.environ["STRUCTURA_DATA_DIR"] = str(work/name)
    os.environ["STRUCTURA_DISABLE_SCHEDULER"] = "1"
    sys.path.insert(0, str(ROOT))
    import httpx
    import uvicorn
    from types import SimpleNamespace
    from threading import Thread
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from backend.app.services import rfq_transport
    from backend.app.api import rfq_transport as transport_api
    from backend.app.main import app
    from backend.app.db.database import engine
    assert Path(engine.url.database).resolve()==(work/name/'structura.db').resolve()
    context = ssl.create_default_context(cafile=str(work/"ca.pem"))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    original = rfq_transport.deliver_one

    def delivery(engine, message_id, client=None):
        if client is not None:
            return original(engine, message_id, client)
        with httpx.Client(verify=context, timeout=10, trust_env=False, follow_redirects=False) as trusted:
            return original(engine, message_id, trusted)

    def trusted_client(**kwargs):
        return httpx.Client(verify=context, **kwargs)

    rfq_transport.deliver_one = delivery
    transport_api.httpx = SimpleNamespace(Client=trusted_client, HTTPError=httpx.HTTPError)

    class Proxy(BaseHTTPRequestHandler):
        def forward(self):
            payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection"}}
            try:
                with httpx.Client(verify=context, trust_env=False, timeout=30) as client:
                    response = client.request(self.command, f"https://127.0.0.1:{port}"+self.path,
                                              headers=headers, content=payload)
                self.send_response(response.status_code)
                for k, v in response.headers.items():
                    if k.lower() not in {"transfer-encoding", "connection", "content-length", "content-encoding"}:
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)
            except (httpx.HTTPError, BrokenPipeError):
                self.send_error(502)
        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = forward
        def log_message(self, *_):
            pass

    proxy = ThreadingHTTPServer(("127.0.0.1", ui_port), Proxy)
    Thread(target=proxy.serve_forever, daemon=True).start()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, reload=False, timeout_graceful_shutdown=5,
        ssl_keyfile=str(work/name/"key.pem"), ssl_certfile=str(work/name/"cert.pem")))
    app.state.instance_server = server
    try:
        server.run()
    finally:
        proxy.shutdown()
        proxy.server_close()


def seed(work, password, resume=False):
    """Bootstrap only fictitious organizations, explicit rights and agreements."""
    os.environ["STRUCTURA_DATA_DIR"] = str(work/"requester")
    sys.path.insert(0, str(ROOT))
    from sqlmodel import Session, SQLModel, create_engine
    from backend.app.db.database import engine, _hash_pw
    from backend.app.db.models import (Entity, User, Counterparty, RfqDesk, RfqDeskMembership,
                                      RfqRelationship, RfqRelationshipSide, RfqProvider)
    from backend.app.db.trading_models import TradingRelationship
    from backend.app.services.rfq_relationships import RelationshipTerms
    assert Path(engine.url.database).resolve() == (work/"requester"/"structura.db").resolve()
    hashed = _hash_pw(password)
    terms = RelationshipTerms(formats=["EMTN"], instruments=["Note"], payoff_families=["Autocall"],
        currencies=["EUR"], effective_date=date.today(), solicitation_allowed=True,
        indicative_allowed=False, to_trade_allowed=True, treatment_allowed=True,
        documentation_reference="Programme EMTN fictif de recette").model_dump_json()
    configurations = {
        "requester": dict(sales=1, banks=[(2,"BNP fictif",21,101),(3,"SocGen fictif",31,102)], user=51, desk=11),
        "bnp": dict(sales=101, banks=[(202,"BNP fictif",721,700)], user=502, desk=721),
        "socgen": dict(sales=301, banks=[(303,"SocGen fictif",933,900)], user=803, desk=933),
    }
    if resume:
        import sqlite3
        for name in configurations:
            path=work/name/'structura.db'
            assert path.is_file()
            with sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True) as connection:
                assert connection.execute('SELECT username FROM users WHERE username=?',('qa.'+name,)).fetchone()
        return configurations
    sales_rights = ["read","prepare","price","select","solicit","book","organize"]
    bank_rights = ["read","prepare","price","organize","validate_quote","publish_quote"]
    for name, cfg in configurations.items():
        db = create_engine(f"sqlite:///{work/name/'structura.db'}")
        SQLModel.metadata.create_all(db)
        with Session(db) as session:
            session.add(Entity(id=cfg['sales'], name="ClientTech fictif"))
            for bid, label, desk, _ in cfg['banks']:
                session.add(Entity(id=bid, name=label))
            session.flush()
            own = cfg['sales'] if name == "requester" else cfg['banks'][0][0]
            session.add_all([User(id=cfg['user'], username="qa."+name, email=name+"@qa.invalid",
                entity_id=own, role="admin", password_hash=hashed),
                User(id=cfg['user']+1, username="qa."+name+".checker", email=name+".checker@qa.invalid",
                entity_id=own, role="user", password_hash=hashed),
                User(id=cfg['user']+2, username="qa."+name+".outsider", email=name+".outsider@qa.invalid",
                entity_id=cfg['sales'] if name != "requester" else cfg['banks'][0][0], role="user", password_hash=hashed)])
            session.add(RfqDesk(id=cfg['desk'], entity_id=own, name="Sales" if name == "requester" else "Pricing"))
            for index, (bid, label, desk, rid) in enumerate(cfg['banks'], start=1):
                if name == "requester":
                    session.add(RfqDesk(id=desk, entity_id=bid, name="Pricing"))
                session.add(Counterparty(id=index, name=label+" juridique"))
            session.add(Counterparty(id=10, name="ClientTech fictif juridique"))
            session.flush()
            session.add_all([RfqDeskMembership(desk_id=cfg['desk'], user_id=cfg['user'],
                rights_json=json.dumps(sales_rights if name == "requester" else bank_rights)),
                RfqDeskMembership(desk_id=cfg['desk'], user_id=cfg['user']+1,
                rights_json=json.dumps(["read","validate_quote","publish_quote"]))])
            for index, (bid, label, desk, rid) in enumerate(cfg['banks'], start=1):
                legal = index if name == "requester" else 10
                session.add(TradingRelationship(id=index, entity_id=own, counterparty_id=legal,
                    reference="QA-TRADING-"+name+"-"+str(index), updated_by=cfg['user'], terms_json=json.dumps({
                        "status":"ACTIVE", "currency":"EUR", "documentation_reference":"Programme EMTN fictif de recette",
                        "note_distribution_allowed":True,"effective_date":date.today().isoformat()})))
                version = 2 if name == "requester" else 5
                session.add(RfqRelationship(id=rid, requester_entity_id=cfg['sales'], partner_entity_id=bid,
                    receiver_desk_id=desk, reference="QA-"+name+"-"+label, version=version, terms_json=terms,
                    created_by=cfg['user']))
                session.flush()
                for entity_id in (cfg['sales'], bid):
                    session.add(RfqRelationshipSide(relationship_id=rid, entity_id=entity_id,
                        counterparty_id=legal if entity_id==own else (10 if name=="requester" else index),
                        trading_relationship_id=index if entity_id==own else None,
                        recognized_version=version, updated_by=cfg['user']))
            if name == "requester":
                session.add(RfqProvider(label="BNP fictif juridique", counterparty_id=1))
            session.commit()
        db.dispose()
    return configurations


class Pilot:
    def __init__(self, work, checkpoint_seconds, resume=False):
        import httpx
        self.work, self.checkpoint_seconds = work, checkpoint_seconds
        self.password = "rfq-lot8-isolated-demo"
        self.cfg = seed(work, self.password,resume)
        self.ports, self.ui_ports = {}, {}
        selected = set()
        for name in self.cfg:
            for mapping in (self.ports, self.ui_ports):
                port = free_port()
                while port in selected:
                    port = free_port()
                selected.add(port)
                mapping[name] = port
        self.client = httpx.Client(verify=ssl.create_default_context(cafile=str(work/"ca.pem")),
                                  trust_env=False, timeout=30, headers={'Connection':'close'})
        self.processes, self.history, self.auth = {}, [], {}
        prior=json.loads((work/'evidence.json').read_text(encoding='utf-8')) if resume else {}
        self.results = prior.get('scenarios',[])
        self.history = prior.get('process_history',[])
        if resume:
            from urllib.parse import urlsplit
            # Channels retain their peer origin. Restart on the original ports.
            for name in self.cfg:
                owned=next(row for row in prior['process_history'] if row['name']==name)
                self.ports[name]=urlsplit(owned['url']).port
                self.ui_ports[name]=urlsplit(owned['ui_url']).port
            for port in [*self.ports.values(),*self.ui_ports.values()]:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',port))
        self.failure = None
        catalogue = json.loads((ROOT/"frontend/src/data/productCatalogue.json").read_text(encoding="utf-8"))
        self.script = "\n".join(next(p for p in catalogue['products'] if p['key']=="autocall_athena")['script'])
        strike = date.today()
        observations = [strike.replace(year=strike.year+i).isoformat() for i in (1,2,3)]
        self.params = dict(currency="EUR", notional=1_000_000, strike_date=strike.isoformat(),
            value_date=strike.isoformat(), maturity_date=observations[-1],
            payment_date=(date.fromisoformat(observations[-1])+timedelta(days=5)).isoformat(),
            T=round((date.fromisoformat(observations[-1])-strike).days/365.25,6),
            user_params={"COUPON":0.08,"M_AC_BAR":1.0,"M_KI_BAR":0.6},
            constats={"STARTDATE":dict(date=strike.isoformat(),convention='none'),
                "OBSERVATIONDATES":dict(first_observation_date=observations[0],end_date=observations[-1],
                    roll_date=observations[0],frequency='1Y',convention='none',settlement_lag=0)},
            r=0.03,N=2000,model="constant",seed=42,antithetic=True,corr_matrix=[[1.0]],
            underlyings=[dict(name="Basket",ticker="QA_SYNTHETIC",ccy="EUR",sigma=0.2,q=0.01)])
        from backend.app.core.rfq_controls import contract_calendar_failures
        failures=contract_calendar_failures(self.script,self.params)
        assert not failures, [f.as_dict() for f in failures]

    def url(self, name):
        return f"https://127.0.0.1:{self.ports[name]}"

    def api(self, name, path, method="GET", body=None, actor=None, expected=None, data=None):
        actor = actor or name
        response = self.client.request(method, self.url(name)+path, json=body, data=data,
            headers=self.auth.get(actor, {}))
        if expected is not None:
            assert response.status_code in expected, f"{name} {path}: expected {expected}, got {response.status_code} {response.text[:350]}"
            return dict(status=response.status_code, detail=response.json().get("detail"))
        if not response.is_success:
            raise RuntimeError(f"{name} {method} {path}: {response.status_code} {response.text[:650]}")
        return response.json()

    def record(self, key, **details):
        self.results.append(dict(scenario=key, state="PASS", at=utc().isoformat(), **details))
        write_json(self.work/"evidence.json", dict(scenarios=self.results, process_history=self.history))
        print("PASS "+key, flush=True)

    def poll(self, call, predicate, timeout=45):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            value = call()
            if predicate(value):
                return value
            time.sleep(.25)
        raise RuntimeError("Pilot condition did not complete within timeout")

    def start(self, name):
        token, iid = secrets.token_urlsafe(48), str(uuid4())
        env = {**os.environ, 'STRUCTURA_DATA_DIR':str(self.work/name),'STRUCTURA_DISABLE_SCHEDULER':'1',
               'STRUCTURA_INSTANCE_CONTROL_TOKEN':token,'STRUCTURA_INSTANCE_ID':iid}
        for key in ('STRUCTURA_JWT_SECRET','STRUCTURA_BUSINESS_CLOCK','STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP',
                    'STRUCTURA_DISABLE_RFQ_TRANSPORT','STRUCTURA_CONSULTATION','PYTEST_CURRENT_TEST'):
            env.pop(key, None)
        command = [sys.executable,str(Path(__file__).resolve()),'--serve',name,'--work',str(self.work),
                   '--port',str(self.ports[name]),'--ui-port',str(self.ui_ports[name])]
        log = (self.work/name/"server.log").open('a',encoding='utf-8')
        process = subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        owned = dict(name=name,pid=process.pid,instance_id=iid,started_at=utc().isoformat(),command=command,
                     url=self.url(name),ui_url=f"http://127.0.0.1:{self.ui_ports[name]}")
        self.history.append(owned)
        self.processes[name] = process, log, token, owned
        def ready():
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited; see {self.work/name/'server.log'}")
            try:
                return self.client.get(self.url(name)+"/health").json()
            except Exception:
                return {}
        health = self.poll(ready,lambda v:v.get('instance_id')==iid)
        owned['server_pid'] = health['process_id']
        self.login(name)

    def stop(self, name):
        if name not in self.processes:
            return
        process, log, token, owned = self.processes[name]
        if process.poll() is None:
            health = self.client.get(self.url(name)+"/health").json()
            assert health['instance_id']==owned['instance_id'] and health['process_id']==owned['server_pid']
            self.client.post(self.url(name)+"/_instance/stop",headers={'X-Instance-Control':token}).raise_for_status()
            process.wait(timeout=45)
        log.close()
        owned['stopped_at'] = utc().isoformat()
        for port in (self.ports[name],self.ui_ports[name]):
            with socket.socket() as sock:
                assert sock.connect_ex(('127.0.0.1',port)) != 0
        del self.processes[name]

    def login(self, name, suffix=''):
        value=self.api(name,'/api/auth/login','POST',data={'username':'qa.'+name+suffix,'password':self.password})
        self.auth[name+suffix]={'Authorization':'Bearer '+value['access_token']}

    def pair(self):
        import httpx
        try:
            with httpx.Client(trust_env=False,timeout=5) as untrusted:
                untrusted.get(self.url('requester')+'/health')
        except httpx.ConnectError:
            pass
        else:
            raise AssertionError('Disposable CA must not be trusted by the default transport')
        identities={name:self.api(name,'/api/rfq-transport/channels')['installation_id'] for name in self.cfg}
        self.channels={}
        for index,name in enumerate(('bnp','socgen'),start=1):
            a=self.api('requester','/api/rfq-transport/channels','POST',dict(relationship_id=100+index,
                expected_version=2,role='REQUESTER',peer_installation_id=identities[name],peer_url=self.url(name),
                peer_counterparty_id=10,reason='Appairage isolé du lot 8'))
            self.api(name,'/api/rfq-transport/channels','POST',dict(relationship_id=self.cfg[name]['banks'][0][3],
                expected_version=5,role='BANK',peer_installation_id=identities['requester'],peer_url=self.url('requester'),
                peer_counterparty_id=1,channel_id=a['id'],secret=a['pairing']['secret'],reason='Import isolé du lot 8'))
            self.api('requester',f"/api/rfq-transport/channels/{a['id']}/probe",'POST')
            self.channels[name]=a['id']
        self.record('https_pairing_independent_ids', installations=3, certificate_verification=True)

    def duplicate_request(self, sent, bank):
        from sqlmodel import Session, create_engine
        from backend.app.db.models import RfqTransportOutbox, RfqChannel, RfqSolicitation
        from backend.app.services import rfq_transport as transport
        db=create_engine(f"sqlite:///{self.work/'requester'/'structura.db'}")
        with Session(db) as session:
            item=session.get(RfqSolicitation,sent['solicitation_ids'][0])
            row=session.get(RfqTransportOutbox,item.message_id)
            channel=session.get(RfqChannel,row.channel_id)
            packet=transport.envelope(session,channel,'DELIVER',transport.wire_message(row))
            changed=json.loads(json.dumps(packet))
            changed['body']['message']['payload']['title']='Contenu modifié après remise'
            changed['signature']=transport.signature(channel,changed['body'])
        before=len(self.api(bank,'/api/rfq-inbox'))
        first=self.api(bank,'/api/rfq-transport/receive','POST',packet)
        second=self.api(bank,'/api/rfq-transport/receive','POST',packet)
        assert first['body']['message']==second['body']['message']
        assert len(self.api(bank,'/api/rfq-inbox'))==before
        invalid={**packet,'signature':'0'*64}
        self.api(bank,'/api/rfq-transport/receive','POST',invalid,expected={401})
        self.api(bank,'/api/rfq-transport/receive','POST',changed,expected={409,422})
        db.dispose()
        self.record('duplicate_delivery_and_signature_payload_conflicts',unchanged_inbox_count=before)

    def create(self, title):
        return self.api('requester','/api/rfq','POST',dict(pilot_desk_id=11,name=title,kind='to_trade',sens='achat',
            template_type='autocall_athena',script_snapshot=self.script,params=self.params,
            transaction_format='EMTN',instrument_family='Note',payoff_family='Autocall',
            documentation_reference='Programme EMTN fictif de recette'))

    def send(self, rfq, banks):
        body=dict(expected_terms_version=1,shared_title=rfq['name'],response_deadline=(utc()+timedelta(hours=1)).isoformat(),
                  relationship_ids=[101 if b=='bnp' else 102 for b in banks])
        preview=self.api('requester',f"/api/rfq/{rfq['id']}/exchange-preview",'POST',body)
        payload={**body,'command_key':str(uuid4()),'expected_preview_hash':preview['preview_hash']}
        sent=self.api('requester',f"/api/rfq/{rfq['id']}/send",'POST',payload)
        replay=self.api('requester',f"/api/rfq/{rfq['id']}/send",'POST',payload)
        assert sent['solicitation_ids']==replay['solicitation_ids']
        return sent,preview

    def received(self, name, preview):
        rows=self.poll(lambda:self.api(name,'/api/rfq-inbox'),
            lambda rows:any(r['title']==preview['request']['title'] for r in rows))
        return next(r['id'] for r in rows if r['title']==preview['request']['title'])

    def price(self, name, product, sigma=.2):
        row=self.api(name,f'/api/products/{product}')
        value=self.api(name,f'/api/products/{product}/pricing-input','POST',dict(expected_terms_version=1,
            context=dict(r=.03,N=2000,model='constant',seed=42,antithetic=True,corr_matrix=[[1.0]],
                         underlyings=[dict(sigma=sigma,q=.01)])))
        computed=self.api(name,'/api/price','POST',value)
        saved=self.api(name,f'/api/products/{product}/calculations','POST',dict(command_key=str(uuid4()),
            expected_revision=row['revision'],pricing_receipt=computed['pricing_receipt']))
        return computed,saved['calculations'][-1]['id']

    def draft(self, name, item, calculation, price, seconds=1800, second=False, revision=0):
        current=self.api(name,f'/api/rfq-inbox/{item}')
        policy=current.get('publication_policy') or {}
        self.api(name,f'/api/rfq-inbox/{item}/publication-policy','PUT',dict(expected_version=policy.get('version',0),
            second_validation_required=second,max_calculation_age_minutes=60,reason='Politique explicite du pilote isolé'))
        return self.api(name,f'/api/rfq-inbox/{item}/quote-draft','PUT',dict(expected_revision=revision,
            calculation_id=calculation,price=price,firmness='FIRM',valid_until=(utc()+timedelta(seconds=seconds)).isoformat(),
            conditions_type='NONE',issuer_name=self.cfg[name]['banks'][0][1]+' juridique',
            documentation_reference='Programme EMTN fictif de recette'))

    def publish(self, name, item, draft, actor=None):
        decision=dict(expected_revision=draft['quote_draft']['revision'],expected_payload_hash=draft['quote_draft']['payload_hash'])
        self.api(name,f'/api/rfq-inbox/{item}/validate','POST',decision,actor)
        return self.api(name,f'/api/rfq-inbox/{item}/publish','POST',decision,actor)

    def quotes(self, rfq, count):
        return self.poll(lambda:self.api('requester',f"/api/rfq/{rfq['id']}"),lambda v:len(v['quotes'])==count)['quotes']

    def treatment(self, rfq, quote, preview):
        self.api('requester',f"/api/rfq/{rfq['id']}",'PATCH',dict(selected_quote_id=quote['id'],selection_reason_code='price'))
        return self.api('requester',f"/api/rfq/{rfq['id']}/treatment",'POST',dict(quote_id=quote['id'],
            expected_terms_version=1,expected_terms_fingerprint=preview['request']['terms_fingerprint'],
            command_key=str(uuid4()),source='PHONE',reference='Appel de recette sans exécution réelle',bank_contact='Desk BNP fictif'))

    def confirm(self, rfq, agreement, reference):
        return self.api('requester',f"/api/rfq/{rfq['id']}/treatment/{agreement['id']}/confirm",'POST',dict(
            expected_snapshot_hash=agreement['snapshot_hash'],execution_reference=reference,
            acceptance_received_at=utc().isoformat(),confirmed_at=utc().isoformat(),source='BANK_CONFIRMATION',
            acceptance_evidence='Réception fictive horodatée de recette',evidence='Accord externe fictif sur termes prix et nominal',bank_contact='BNP fictif'))

    def booking(self, rfq, agreement, computed):
        p=self.params
        return dict(rfq_id=rfq['id'],product_id=rfq['product_id'],product_terms_version=1,
            execution_agreement_id=agreement['id'] if agreement else None,sens='vente',contrepartie='BNP fictif juridique',
            devise='EUR',product_type='autocall_athena',nominal=p['notional'],fair_value=computed['price']*100,price_traded=98.5,
            trade_date=p['strike_date'],strike_date=p['strike_date'],value_date=p['value_date'],maturity_date=p['maturity_date'],
            payment_date=p['payment_date'],T=computed['pricing_receipt']['pricing_input']['T'],underlyings=p['underlyings'],
            observation_times=sorted({entry['t'] for entry in computed['flux_table'].values()}),
            script_snapshot=self.script,pricing_receipt=computed['pricing_receipt'],market_snapshot=dict(r=3.,model='constant',
                constats=p['constats'],user_params=p['user_params'],underlyings=[dict(name='Basket',ticker='QA_SYNTHETIC',ccy='EUR',sigma=20.,q=1.)]))

    def run(self):
        for name in self.cfg:
            self.start(name)
        self.pair()
        rfq=self.create('Lot 8 · Athena BNP · reprise et booking')
        self.stop('bnp')
        sent,preview=self.send(rfq,['bnp'])
        tracking=self.poll(lambda:self.api('requester',f"/api/rfq/{rfq['id']}/exchange"),
            lambda t:t['deliveries'][0]['transport']['attempts']>=1)
        assert tracking['deliveries'][0]['delivered_at'] is None
        self.stop('requester')
        self.start('bnp'); self.start('requester')
        item=self.received('bnp',preview)
        self.record('interruption_restart_persistent_delivery',rfq=rfq['reference'],item=item)
        self.api('bnp',f'/api/rfq-inbox/{item}/read','POST')
        case=self.api('bnp',f'/api/rfq-inbox/{item}/claim','POST')['case']
        computed,calc=self.price('bnp',case['product_id'])
        assert not self.api('requester',f"/api/rfq/{rfq['id']}")['quotes']
        self.record('private_calculation_before_publication',price=computed['price']*100)
        draft=self.draft('bnp',item,calc,98.5,seconds=18)
        publication=self.publish('bnp',item,draft)
        quote=self.quotes(rfq,1)[0]
        assert quote['origin']=='NETWORK' and quote['price']==98.5 and quote['comparable']
        self.record('bank_validation_automatic_return',commercial_price=quote['price'])
        self.login('requester','.outsider'); self.login('bnp','.outsider')
        self.api('requester',f"/api/rfq/{rfq['id']}",actor='requester.outsider',expected={403,404})
        self.api('bnp',f'/api/rfq-inbox/{item}',actor='bnp.outsider',expected={403,404})
        self.api('requester',f"/api/rfq/{rfq['id']}/quotes/{quote['id']}",'PATCH',dict(price=1),expected={409,422})
        self.record('foreign_organization_and_native_quote_edit_refused')
        self.api('bnp',f"/api/products/{case['product_id']}",actor='bnp.outsider',expected={403,404})
        requester_price,_=self.price('requester',rfq['product_id'])
        inp=self.api('requester',f"/api/rfq/{rfq['id']}/pricing-input",'POST',dict(expected_terms_version=1))
        self.api('requester',f"/api/rfq/{rfq['id']}",'PATCH',dict(model_price=requester_price['price']*100,expected_model_input_hash=inp['input_hash']))
        agreement=self.treatment(rfq,quote,preview)
        body=self.booking(rfq,agreement,requester_price)
        refusal=self.api('requester','/api/deals','POST',body,expected={409,422})
        self.record('requested_without_confirmation_booking_refused',http_status=refusal['status'])
        agreement=self.confirm(rfq,agreement,'QA-BNP-EXEC-001')
        expiry=datetime.fromisoformat(quote['valid_until'].replace('Z','+00:00'))
        while utc()<=expiry:
            time.sleep(.25)
        body=self.booking(rfq,agreement,requester_price)
        with ThreadPoolExecutor(max_workers=2) as pool:
            bookings=list(pool.map(lambda _:self.api('requester','/api/deals','POST',body),range(2)))
        assert bookings[0]['id']==bookings[1]['id']
        refusal=self.api('requester','/api/deals','POST',{**body,'price_traded':99},expected={409})
        row=self.api('requester',f"/api/rfq/{rfq['id']}")
        assert row['execution_agreements'][0]['state']=='BOOKED_LOCALLY'
        self.record('confirmed_before_expiry_booking_after_expiry_unique',deal=bookings[0]['reference'],
                    simultaneous_requests=2,changed_payload_http_status=refusal['status'])
        mixed=self.create('Lot 8 · Athena deux banques et manuel')
        mixed_sent,mixed_preview=self.send(mixed,['bnp','socgen'])
        items={name:self.received(name,mixed_preview) for name in ('bnp','socgen')}
        self.duplicate_request(mixed_sent,'bnp')
        calculations={}
        for name,sigma in [('bnp',.2),('socgen',.3)]:
            detail=self.api(name,f"/api/rfq-inbox/{items[name]}")
            assert detail['request']['terms_fingerprint']==mixed_preview['request']['terms_fingerprint']
            product=self.api(name,f"/api/rfq-inbox/{items[name]}/claim",'POST')['case']['product_id']
            result,identifier=self.price(name,product,sigma)
            calculations[name]=(result,identifier)
        assert calculations['bnp'][0]['price']!=calculations['socgen'][0]['price']
        self.record('same_athena_terms_distinct_private_market',terms_fingerprint=mixed_preview['request']['terms_fingerprint'],
            bnp_model_price=calculations['bnp'][0]['price']*100,socgen_model_price=calculations['socgen'][0]['price']*100)
        drafts={name:self.draft(name,items[name],calculations[name][1],98.5 if name=='bnp' else 99.1,second=name=='socgen')
                for name in items}
        previous=dict(expected_revision=drafts['bnp']['quote_draft']['revision'],
                      expected_payload_hash=drafts['bnp']['quote_draft']['payload_hash'])
        self.api('bnp',f"/api/rfq-inbox/{items['bnp']}/validate",'POST',previous)
        drafts['bnp']=self.draft('bnp',items['bnp'],calculations['bnp'][1],98.4,revision=previous['expected_revision'])
        self.api('bnp',f"/api/rfq-inbox/{items['bnp']}/publish",'POST',previous,expected={409})
        self.record('changed_validated_draft_requires_new_validation')
        decision=dict(expected_revision=drafts['socgen']['quote_draft']['revision'],expected_payload_hash=drafts['socgen']['quote_draft']['payload_hash'])
        self.api('socgen',f"/api/rfq-inbox/{items['socgen']}/validate",'POST',decision,expected={403,409})
        self.login('socgen','.checker')
        checker=self.cfg['socgen']['user']+1
        membership=dict(user_id=checker,rights=['read','validate_quote','publish_quote'],active=False)
        self.api('socgen',f'/api/rfq-desks/admin/933/members/{checker}','PUT',membership)
        self.api('socgen',f"/api/rfq-inbox/{items['socgen']}/validate",'POST',decision,actor='socgen.checker',expected={403,404})
        self.api('socgen',f'/api/rfq-desks/admin/933/members/{checker}','PUT',{**membership,'active':True})
        self.record('revoked_desk_rights_refused')
        pubs={name:self.publish(name,items[name],drafts[name],actor='socgen.checker' if name=='socgen' else None) for name in items}
        self.quotes(mixed,2)
        manual=self.api('requester',f"/api/rfq/{mixed['id']}/quotes",'POST',dict(provider='BNP fictif juridique',note='Téléphone de recette'))
        self.api('requester',f"/api/rfq/{mixed['id']}/quotes/{manual['id']}",'PATCH',dict(price=100,currency='EUR',status='recu'))
        quotes=self.quotes(mixed,3)
        assert sorted(q.get('origin','MANUAL') for q in quotes)==['MANUAL','NETWORK','NETWORK']
        self.record('second_validation_and_mixed_comparison',quotes=3)
        self.finish_mixed(mixed,items,pubs)

    def resume_tail(self):
        """Finish the mixed recipe after a QA assertion fix, without rebooking."""
        assert any(r['scenario']=='confirmed_before_expiry_booking_after_expiry_unique' for r in self.results)
        assert any(r['scenario']=='revoked_desk_rights_refused' for r in self.results)
        for name in self.cfg:
            self.start(name)
        channels=self.api('requester','/api/rfq-transport/channels')['channels']
        self.channels={name:next(c['id'] for c in channels if c['relationship_id']==rid)
                       for name,rid in [('bnp',101),('socgen',102)]}
        rows=self.api('requester','/api/rfq')
        mixed=next(r for r in rows if r['name']=='Lot 8 · Athena deux banques et manuel')
        mixed=self.api('requester',f"/api/rfq/{mixed['id']}")
        assert sorted(q.get('origin','MANUAL') for q in mixed['quotes'])==['MANUAL','NETWORK','NETWORK']
        items={name:next(r['id'] for r in self.api(name,'/api/rfq-inbox') if r['title']==mixed['name']) for name in ('bnp','socgen')}
        pubs={name:self.api(name,f"/api/rfq-inbox/{items[name]}") for name in items}
        self.record('second_validation_and_mixed_comparison',quotes=3,resumed_private_run=True)
        self.finish_mixed(mixed,items,pubs)

    def finish_mixed(self,mixed,items,pubs):
        self.api('bnp',f"/api/rfq-inbox/{items['bnp']}/withdraw",'POST',dict(publication_id=pubs['bnp']['publications'][0]['id'],reason='Retrait fictif avant acceptation'))
        self.poll(lambda:self.api('requester',f"/api/rfq/{mixed['id']}"),
            lambda r:any(q.get('publication',{}).get('state')=='WITHDRAWN' for q in r['quotes']))
        self.record('withdrawal_before_acceptance_received')
        cid=self.channels['bnp']
        self.api('requester',f'/api/rfq-transport/channels/{cid}','PUT',dict(active=False,expected_version=2,reason='Suspension pilote'))
        suspended=self.create('Lot 8 · canal suspendu')
        self.api('requester',f"/api/rfq/{suspended['id']}/exchange-preview",'POST',dict(expected_terms_version=1,
            shared_title=suspended['name'],response_deadline=(utc()+timedelta(hours=1)).isoformat(),relationship_ids=[101]),expected={409,422})
        m=self.api('requester',f"/api/rfq/{suspended['id']}/quotes",'POST',dict(provider='BNP fictif juridique'))
        self.api('requester',f"/api/rfq/{suspended['id']}/quotes/{m['id']}",'PATCH',dict(price=98.5,currency='EUR',status='recu',
            valid_until=(utc()+timedelta(minutes=30)).isoformat()))
        self.record('channel_suspension_manual_remains_available')
        priced,_=self.price('requester',suspended['product_id'])
        inp=self.api('requester',f"/api/rfq/{suspended['id']}/pricing-input",'POST',dict(expected_terms_version=1))
        self.api('requester',f"/api/rfq/{suspended['id']}",'PATCH',dict(model_price=priced['price']*100,
            expected_model_input_hash=inp['input_hash'],selected_quote_id=m['id']))
        manual_deal=self.api('requester','/api/deals','POST',self.booking(suspended,None,priced))
        self.record('manual_booking_preserved_with_network_suspended',deal=manual_deal['reference'])
        self.api('requester',f'/api/rfq-transport/channels/{cid}','PUT',dict(active=True,expected_version=2,reason='Réactivation après contrôle'))
        self.api('requester',f'/api/rfq-transport/channels/{cid}/probe','POST')
        self.api('requester',f"/api/rfq/{mixed['id']}",'PATCH',dict(status='sans_suite'))
        for name in items:
            self.poll(lambda:self.api(name,f"/api/rfq-inbox/{items[name]}"),lambda r:not r['open_for_work'])
        self.record('closure_received_each_bank')
        self.core_complete=True
        if self.checkpoint_seconds:
            active=self.create('Lot 8 · contrôle des masques')
            _,p=self.send(active,['bnp'])
            active_item=self.received('bnp',p)
            product=self.api('bnp',f'/api/rfq-inbox/{active_item}/claim','POST')['case']['product_id']
            _,calc=self.price('bnp',product)
            d=self.draft('bnp',active_item,calc,98.5)
            self.publish('bnp',active_item,d)
            self.quotes(active,1)
            write_json(self.work/'browser_ready.json',dict(work=str(self.work),rfq_id=active['id'],bank_item_id=active_item,
                requester_url=f"http://127.0.0.1:{self.ui_ports['requester']}/#/rfq?rfq={active['id']}",
                bank_url=f"http://127.0.0.1:{self.ui_ports['bnp']}/#/rfq/recues",password=self.password))
            print('BROWSER_READY '+str(self.work/'browser_ready.json'),flush=True)
            deadline=time.monotonic()+self.checkpoint_seconds
            while not (self.work/'browser_done').exists() and time.monotonic()<deadline:
                time.sleep(.25)

    def close(self):
        errors=[]
        for name in list(self.processes):
            try:
                self.stop(name)
            except Exception as exc:
                errors.append(str(exc))
        write_json(self.work/'evidence.json',dict(scenarios=self.results,process_history=self.history,
            core_complete=getattr(self,'core_complete',False),failure=self.failure,
            cleanup_errors=errors,remaining_owned_processes=list(self.processes)))
        self.client.close()
        if errors:
            raise RuntimeError('Private server cleanup failed: '+'; '.join(errors))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve',choices=['requester','bnp','socgen'])
    parser.add_argument('--work',type=Path)
    parser.add_argument('--port',type=int)
    parser.add_argument('--ui-port',type=int)
    parser.add_argument('--checkpoint-seconds',type=int,default=0)
    parser.add_argument('--resume-work',type=Path,help='Finish an isolated run interrupted during mixed-comparison QA')
    args=parser.parse_args()
    if args.serve:
        serve(args.work,args.serve,args.port,args.ui_port)
        return
    work=(args.resume_work.resolve() if args.resume_work else
          ROOT/'tmp'/'rfq-lot8'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:6]))
    assert (ROOT/'tmp'/'rfq-lot8').resolve() in work.resolve().parents
    if not args.resume_work:
        work.mkdir(parents=True)
        certificates(work)
    print('WORK '+str(work),flush=True)
    pilot=Pilot(work,args.checkpoint_seconds,bool(args.resume_work))
    try:
        if args.resume_work:
            pilot.resume_tail()
        else:
            pilot.run()
    except Exception as exc:
        pilot.failure=str(exc)
        raise
    finally:
        pilot.close()
    print('PILOT_COMPLETE '+str(work/'evidence.json'),flush=True)


if __name__=='__main__':
    main()
