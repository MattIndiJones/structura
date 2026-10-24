from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import shutil
import sqlite3
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import httpx
from .persistence import atomic_write
from ...core.simulation_bootstrap import BOOTSTRAP_FILENAME, simulation_credentials

ROOT = Path(__file__).resolve().parents[4]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def clock_file(directory, business_date):
    path = directory / "clock.json"
    atomic_write(path,json.dumps({"now": business_date + "T09:00:00"}))
    return path


class Instances:
    def __init__(self, directory, state, cancelled=None):
        self.directory = directory
        self.state = state
        self.processes = []
        self.logs = []
        self.controls = []
        self.cancelled = cancelled or (lambda: False)

    def baseline(self):
        reference = [{k:v for k,v in p.items() if k != 'economy'} for p in self.state['config'].get('participants', [])]
        digest = hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()[:20]
        return self.directory.parent / '_baselines' / ('v3-private-bootstrap-' + digest)

    def bootstrap_credentials(self, key, *, create=False):
        directory = self.directory / 'instances' / key
        credentials = simulation_credentials(directory)
        if credentials is None:
            if not create or (directory / 'structura.db').exists():
                raise RuntimeError('Ancienne simulation sans identifiants techniques privés ; créez une nouvelle simulation. Le book existant est conservé.')
            credentials = {'username': 'workshop_admin', 'email': key + '-bootstrap@recette.invalid',
                           'password': secrets.token_urlsafe(32)}
            atomic_write(directory / BOOTSTRAP_FILENAME, json.dumps(credentials))
        return credentials

    def restore_baseline(self, directory, key):
        if self.state['config'].get('schema_version') != 2 or (directory/'structura.db').exists():
            return
        source = self.baseline()/key
        if not (source/'ready.json').exists():
            return
        for name in ('structura.db', BOOTSTRAP_FILENAME, 'agent_credentials.json', 'provisioner_credentials.json',
                     'checker_credentials.json', 'simulation_bootstrap.json'):
            if (source/name).exists():
                shutil.copy2(source/name, directory/name)

    def capture_baseline(self):
        if self.state['config'].get('schema_version') != 2 or self.state['cases'] or any(a['deals'] for a in self.state['actors'].values()):
            return
        for key, actor in self.state['actors'].items():
            if key == 'achille':
                continue
            source = self.directory/'instances'/key
            destination = self.baseline()/key
            destination.mkdir(parents=True, exist_ok=True)
            if (destination/'ready.json').exists():
                continue
            # SQLite backup is consistent while the isolated service is running.
            with sqlite3.connect(source/'structura.db') as db, sqlite3.connect(destination/'structura.db') as copy:
                db.backup(copy)
            for name in (BOOTSTRAP_FILENAME, 'agent_credentials.json', 'provisioner_credentials.json', 'checker_credentials.json', 'simulation_bootstrap.json'):
                if (source/name).exists():
                    shutil.copy2(source/name, destination/name)
            atomic_write(destination/'ready.json', json.dumps({'scope':'PRIVATE_SIMULATION_REFERENTIAL', 'actor':key, 'created_at':datetime.utcnow().isoformat()}))

    def ensure_identity(self, key):
        """Provision once, then reuse the baseline identity without signup UI."""
        actor = self.state['actors'][key]
        file = self.directory/'instances'/key/'agent_credentials.json'
        credentials = json.loads(file.read_text()) if file.exists() else {
            'username':'agent_'+key, 'email':key+'@recette.invalid', 'password':secrets.token_urlsafe(24)}
        with httpx.Client(timeout=10, trust_env=False) as client:
            technical = self.bootstrap_credentials(key)
            reply = client.post(actor['url']+'/api/auth/login', data={k:technical[k] for k in ('username','password')})
            reply.raise_for_status()
            headers = {'Authorization':'Bearer '+reply.json()['access_token']}
            reply = client.get(actor['url']+'/api/admin/users', headers=headers); reply.raise_for_status()
            user = next((u for u in reply.json() if u['username'] == credentials['username']), None)
            if not user:
                reply = client.get(actor['url']+'/api/admin/entities', headers=headers); reply.raise_for_status()
                entity = next((e for e in reply.json() if e['name'] == actor['entity']), None)
                if not entity:
                    reply = client.post(actor['url']+'/api/admin/entities', headers=headers, json={'name':actor['entity']}); reply.raise_for_status()
                    entity = reply.json()
                reply = client.post(actor['url']+'/api/admin/users', headers=headers,
                                    json={**credentials,'role':'user','entity_id':entity['id']})
                reply.raise_for_status(); user = reply.json()
            if not user['is_active']:
                raise ValueError('Le compte de simulation est désactivé ; aucune réactivation automatique.')
            atomic_write(file, json.dumps(credentials))
            self.provision_owner(key, user['id'])
        return credentials

    def recover(self, directory):
        """Close a surviving private worker after a controller crash.

        The secret and instance identity are private local control material,
        excluded from campaign JSON and exports. Never kill a recycled PID.
        """
        path = directory / "instance_control.json"
        if not path.exists():
            return
        previous = json.loads(path.read_text(encoding="utf-8"))
        with httpx.Client(timeout=3, trust_env=False) as client:
            try:
                health = client.get(previous["url"] + "/health").json()
            except (httpx.HTTPError, ValueError):
                return
            if health.get("instance_id") != previous["identity"]:
                return
            response = client.post(previous["url"] + "/_instance/stop", headers={"X-Instance-Control": previous["token"]})
            response.raise_for_status()
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                try:
                    client.get(previous["url"] + "/health")
                except httpx.HTTPError:
                    return
                time.sleep(.2)
            raise RuntimeError("L'ancienne instance privée ne s'est pas arrêtée ; reprise annulée.")

    def start(self, only=None):
        clock = clock_file(self.directory, self.state["business_date"])
        from ..scenario_market import create_market
        from .historical_market import market_path
        market = market_path(self.directory, self.state['config'])
        if not market.exists():
            if self.state['config'].get('market_mode') == 'historical':
                from .historical_market import freeze_market
                self.state['market_sources'] = freeze_market(market, self.state['config'])
            else:
                tickers = sorted({t for p in self.state['config'].get('products',[]) for t in p['tickers']})
                create_market(market, self.state["config"]["start_date"], self.state["config"]["seed"],
                    max(self.state["config"]["months"],self.state['config'].get('horizon_months',0)) + 61, tickers=tickers)
        for key, actor in self.state["actors"].items():
            if key == "achille" or only is not None and key not in only:
                continue
            directory = self.directory / "instances" / key
            directory.mkdir(parents=True, exist_ok=True)
            self.restore_baseline(directory, key)
            if self.cancelled():
                raise RuntimeError("Arrêt demandé pendant la préparation des instances.")
            self.recover(directory)
            self.bootstrap_credentials(key, create=True)
            if actor.get('url'):
                previous = urlsplit(actor['url'])
                if previous.scheme != 'http' or previous.hostname != '127.0.0.1' or not previous.port:
                    raise RuntimeError('Adresse privée de reprise invalide.')
                with socket.socket() as check:
                    try:
                        check.bind(('127.0.0.1', previous.port))
                    except OSError as exc:
                        raise RuntimeError('Le port privé précédent est occupé ; aucun changement implicite de canal RFQ.') from exc
            else:
                actor["url"] = f"http://127.0.0.1:{free_port()}"
            control = secrets.token_urlsafe(48)
            identity = secrets.token_urlsafe(24)
            env = {**os.environ, "STRUCTURA_DATA_DIR": str(directory),
                "STRUCTURA_WORKSHOP_ROOT": str(directory / "agent_workshop"),
                "STRUCTURA_PORT": actor["url"].rsplit(":", 1)[1],
                "STRUCTURA_ALLOW_REGISTRATION": "1", "STRUCTURA_DISABLE_SCHEDULER": "1",
                "STRUCTURA_BUSINESS_CLOCK": str(clock), "STRUCTURA_WORKSHOP_CHILD": "1",
                "STRUCTURA_SCENARIO_MARKET": str(market),
                "STRUCTURA_BOOTSTRAP_PROFILE": "simulation",
                "STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP": "1",
                "STRUCTURA_INSTANCE_CONTROL_TOKEN": control,
                "STRUCTURA_INSTANCE_ID": identity,
                "STRUCTURA_STUDIES_ROOT": str(directory / "studies"),
                "TMP": str(directory / "tmp"), "TEMP": str(directory / "tmp"),
                "PYTHONPATH": str(ROOT / "backend")}
            (directory / "tmp").mkdir(exist_ok=True)
            (directory / "studies").mkdir(exist_ok=True)
            # Each installation persists its own signing key in its private
            # data directory. Restarting must preserve native pricing proofs.
            env.pop("STRUCTURA_JWT_SECRET", None)
            env.pop("STRUCTURA_INSTALLATION_CONFIG", None)
            env.pop("STRUCTURA_ADMIN_WORKBENCH_CONFIG", None)
            env.pop("STRUCTURA_DEVELOPER_ACCESS", None)
            env.pop("STRUCTURA_LAUNCH_ID", None)
            env.pop("OPENAI_API_KEY", None)
            env.pop("ANTHROPIC_API_KEY", None)
            (directory / "instance_control.json").write_text(json.dumps({"url":actor["url"],"identity":identity,"token":control}), encoding="utf-8")
            output = (directory / "server.log").open("a", encoding="utf-8")
            self.logs.append(output)
            process = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py")],
                cwd=str(ROOT), env=env, stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.processes.append(process)
            self.controls.append((actor["url"], control))
            self.state["processes"].append({"actor": key, "pid": process.pid,
                "started_at": datetime.utcnow().isoformat(), "command": [sys.executable, str(ROOT / "backend" / "run.py")],
                "url": actor["url"]})
            deadline = time.monotonic() + 60
            with httpx.Client(timeout=3, trust_env=False) as client:
                while time.monotonic() < deadline:
                    if self.cancelled():
                        raise RuntimeError("Arrêt demandé pendant le démarrage des instances.")
                    if process.poll() is not None:
                        raise RuntimeError(f"L'instance {key} a quitté : consulter son server.log.")
                    try:
                        response = client.get(actor["url"] + "/health")
                        if response.status_code == 200 and response.json().get("instance_id") == identity:
                            self.state["processes"][-1]["server_pid"] = response.json()["process_id"]
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError(f"L'instance {key} ne démarre pas.")
                # Technical administrator prepares the public counterparty catalog.
                technical = self.bootstrap_credentials(key)
                login = client.post(actor["url"] + "/api/auth/login", data={k:technical[k] for k in ('username','password')})
                login.raise_for_status()
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                response = client.get(actor["url"] + "/api/admin/counterparties", headers=headers)
                response.raise_for_status()
                existing = response.json()
                names = {row["name"] for row in existing}
                for other in self.state["actors"].values():
                    if other["role"] != "supervisor" and other["entity"] not in names:
                        reply = client.post(actor["url"] + "/api/admin/counterparties", headers=headers,
                            json={"name": other["entity"], "country": "FR", "reason": "Provisionnement du référentiel de simulation isolée"})
                        reply.raise_for_status()
                        names.add(other["entity"])
                response = client.get(actor["url"] + "/api/admin/counterparties", headers=headers)
                response.raise_for_status()
                counterparties = response.json()
                catalog = {r["name"]: r["id"] for r in counterparties}
                if self.state['config'].get('schema_version')==2:
                    for policy in self.state['config']['participants']:
                        peer=self.state['actors'].get(policy['key'])
                        if peer:
                            row=next(r for r in counterparties if r['name']==peer['entity'])
                            if row.get('limit_eur')!=policy['concentration_limit_eur']:
                                reply=client.patch(actor['url']+f"/api/admin/counterparties/{row['id']}",headers=headers,
                                                   json={'limit_eur':policy['concentration_limit_eur'], 'reason':'Application de la politique de simulation isolée'})
                                reply.raise_for_status()
                response = client.get(actor["url"] + "/api/admin/rfq-providers", headers=headers)
                response.raise_for_status()
                providers = response.json()
                for other in self.state["actors"].values():
                    if other["role"] != "bank" and not other.get('capabilities', {}).get('respond_rfq'):
                        continue
                    provider = next((p for p in providers if p["label"] == other["entity"]), None)
                    payload = {"counterparty_id": catalog[other["entity"]], "mode": "banque"}
                    if provider:
                        if all(provider.get(field) == value for field, value in payload.items()):
                            continue
                        reply = client.patch(actor["url"] + f"/api/admin/rfq-providers/{provider['id']}", headers=headers, json={**payload, "reason":"Rattachement juridique du canal de simulation isolée"})
                    else:
                        reply = client.post(actor["url"] + "/api/admin/rfq-providers", headers=headers, json={**payload, "label": other["entity"], "reason":"Admission du canal de simulation isolée"})
                    reply.raise_for_status()
                actor["online"] = True

    def stop(self):
        def stop_worker(worker):
            process, (url, token) = worker
            if process.poll() is None:
                try:
                    response = httpx.post(url + "/_instance/stop", headers={"X-Instance-Control": token}, timeout=3, trust_env=False)
                    response.raise_for_status()
                    process.wait(timeout=8)
                except (httpx.HTTPError, subprocess.TimeoutExpired):
                    # Only this controller's exact child tree, never an arbitrary Python PID.
                    if process.poll() is None:
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        else:
                            process.terminate()
                    process.wait(timeout=10)
        workers = [(process, control) for process, control in zip(self.processes, self.controls)
                   if process.poll() is None]
        if workers:
            with ThreadPoolExecutor(max_workers=len(workers)) as executor:
                # Observe every failure before closing the campaign's resources.
                futures = [executor.submit(stop_worker, worker) for worker in workers]
                failures = []
                for future in futures:
                    try:
                        future.result()
                    except Exception as exc:
                        failures.append(str(exc))
            if failures:
                raise RuntimeError("Fermeture des instances à vérifier : " + "; ".join(failures))
        for log in self.logs:
            log.close()
        self.state.setdefault("process_history", []).extend({**p,"stopped_at":datetime.utcnow().isoformat()} for p in self.state["processes"])
        self.state["processes"] = []
        for actor in self.state["actors"].values():
            actor["online"] = False

    def provision_owner(self, key, user_id):
        """Grant ownership only in this controller's private actor installation.

        The agent still registers through the normal screen. Legal administration
        requires the real admin permission, so bank/issuer owners receive it via
        the public administration API, never by bypassing the CCR access check.
        """
        actor = self.state["actors"][key]
        if actor["url"] not in {url for url, _ in self.controls}:
            raise ValueError("Cette instance n'appartient pas au contrôleur.")
        directory = self.directory / "instances" / key
        control = json.loads((directory / "instance_control.json").read_text(encoding="utf-8"))
        if (control["url"], control["token"]) not in self.controls:
            raise ValueError("Le contrôle privé de cette instance a changé.")
        with httpx.Client(timeout=10, trust_env=False) as client:
            health = client.get(actor["url"] + "/health")
            health.raise_for_status()
            if health.json().get("instance_id") != control["identity"]:
                raise ValueError("L'identité de cette installation privée a changé.")
            technical = self.bootstrap_credentials(key)
            login = client.post(actor["url"] + "/api/auth/login", data={k:technical[k] for k in ('username','password')})
            login.raise_for_status()
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            users = client.get(actor["url"] + "/api/admin/users", headers=headers)
            users.raise_for_status()
            user = next((row for row in users.json() if row["id"] == user_id), None)
            if not user or user["username"] != "agent_" + key or user["entity_id"] is None:
                raise ValueError("Le compte à initialiser n'est pas celui de cet acteur.")
            technical = next(row for row in users.json() if row['username'] == 'admin')
            if technical['entity_id'] is not None:
                # Explicit technical setup in this verified fictitious installation.
                # This account gets no RFQ desk membership or business ownership.
                reply = client.patch(actor['url'] + f"/api/admin/users/{technical['id']}",
                                     headers=headers, json={'entity_id': None})
                reply.raise_for_status()
            self.prepare_reference_directory(actor, user, client, headers)
            marker = directory / "simulation_bootstrap.json"
            if marker.exists():
                baseline = json.loads(marker.read_text(encoding="utf-8"))
                if baseline["user_id"] != user_id or baseline["entity_id"] != user["entity_id"]:
                    raise ValueError("Le compte ou l'organisation du bootstrap a changé.")
                actor["pilot_desk_id"] = baseline["pilot_desk_id"]
                # Reconnecting must never restore revoked roles or memberships.
                return
            if actor["role"] in {"bank", "issuer"} and user["role"] != "admin":
                reply = client.patch(actor["url"] + f"/api/admin/users/{user_id}",
                    headers=headers, json={"role": "admin"})
                reply.raise_for_status()

            # An administrator in the same private entity sets the actor's grants.
            # Keep self-grant prohibition and organization scoping intact.
            secret_file = directory / "provisioner_credentials.json"
            if secret_file.exists():
                credentials = json.loads(secret_file.read_text(encoding="utf-8"))
            else:
                credentials = {"username": "workshop_provisioner", "email": key + "-setup@recette.invalid",
                               "password": secrets.token_urlsafe(24)}
                atomic_write(secret_file, json.dumps(credentials))
            provisioner = next((row for row in users.json() if row["username"] == credentials["username"]), None)
            if provisioner is None:
                reply = client.post(actor["url"] + "/api/admin/users", headers=headers,
                    json={**credentials, "role": "admin", "entity_id": user["entity_id"]})
                reply.raise_for_status()
                provisioner = reply.json()
            if (provisioner["entity_id"] != user["entity_id"] or provisioner["role"] != "admin"
                    or not provisioner["is_active"]):
                raise ValueError("Le compte de préparation privé a une habilitation différente.")
            login = client.post(actor["url"] + "/api/auth/login", data={
                "username": credentials["username"], "password": credentials["password"]})
            login.raise_for_status()
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            reply = client.get(actor["url"] + "/api/rfq-desks/admin", headers=headers)
            reply.raise_for_status()
            desks = reply.json()
            from ..rfq_access import RIGHTS
            rights = sorted(RIGHTS if actor["role"] in {"bank", "issuer"} else {"read"})
            primary_name = {"issuer": "Structuration", "bank": "Cotation", "client": "Investissement"}[actor["role"]]
            prepared = []
            for name in (primary_name, "Opérations"):
                desk = next((row for row in desks if row["name"] == name), None)
                if desk is None:
                    reply = client.post(actor["url"] + "/api/rfq-desks/admin", headers=headers,
                        json={"entity_id": user["entity_id"], "name": name})
                    reply.raise_for_status()
                    desk = reply.json()
                if not desk["active"]:
                    raise ValueError("Le desk de simulation a été désactivé ; aucune réactivation automatique.")
                member = next((row for row in desk.get("members", []) if row["user_id"] == user_id), None)
                if member is not None:
                    if not member["active"] or sorted(member["rights"]) != rights or member["expires_at"] is not None:
                        raise ValueError("L'habilitation a changé ; aucune restauration automatique.")
                else:
                    reply = client.put(actor["url"] + f"/api/rfq-desks/admin/{desk['id']}/members/{user_id}",
                        headers=headers, json={"user_id": user_id, "rights": rights, "active": True, "expires_at": None})
                    reply.raise_for_status()
                prepared.append(desk["id"])
            if actor['role'] == 'bank' or actor.get('capabilities',{}).get('respond_rfq'):
                checker_file = directory / 'checker_credentials.json'
                if checker_file.exists():
                    checker_credentials = json.loads(checker_file.read_text(encoding='utf-8'))
                else:
                    checker_credentials = {'username':'checker_' + key, 'email':key + '-checker@recette.invalid',
                                           'password':secrets.token_urlsafe(24)}
                    atomic_write(checker_file, json.dumps(checker_credentials))
                reply = client.get(actor['url'] + '/api/admin/users', headers=headers)
                reply.raise_for_status()
                checker = next((u for u in reply.json() if u['username'] == checker_credentials['username']), None)
                if checker is None:
                    reply = client.post(actor['url'] + '/api/admin/users', headers=headers,
                                        json={**checker_credentials, 'role':'checker', 'entity_id':user['entity_id']})
                    reply.raise_for_status()
                    checker = reply.json()
                reply = client.get(actor['url'] + '/api/rfq-desks/admin', headers=headers)
                reply.raise_for_status()
                primary = next(d for d in reply.json() if d['id'] == prepared[0])
                if not any(m['user_id'] == checker['id'] for m in primary['members']):
                    reply = client.put(actor['url'] + f"/api/rfq-desks/admin/{prepared[0]}/members/{checker['id']}",
                        headers=headers, json={'user_id':checker['id'], 'rights':['read','validate_quote'], 'active':True})
                    reply.raise_for_status()
            baseline = {"user_id": user_id, "entity_id": user["entity_id"], "desk_ids": prepared,
                        "pilot_desk_id": prepared[0], "rights": rights, "expires_at": None,
                        "scope": "PRIVATE_SIMULATION", "created_at": datetime.utcnow().isoformat()}
            atomic_write(marker, json.dumps(baseline))
            actor["pilot_desk_id"] = baseline["pilot_desk_id"]

    def prepare_reference_directory(self, actor, user, client, headers):
        """Public remote directory needed by bilateral RFQ, never remote books."""
        reply = client.get(actor['url'] + '/api/admin/entities', headers=headers)
        reply.raise_for_status()
        entities = {row['name']: row for row in reply.json()}
        reply = client.get(actor['url'] + '/api/rfq-desks/admin', headers=headers)
        reply.raise_for_status()
        desks = reply.json()
        directory = {}
        for key, peer in self.state['actors'].items():
            if peer['role'] == 'supervisor' or peer['entity'] == actor['entity']:
                continue
            entity = entities.get(peer['entity'])
            if entity is None:
                reply = client.post(actor['url'] + '/api/admin/entities', headers=headers, json={'name':peer['entity']})
                reply.raise_for_status()
                entity = reply.json()
                entities[peer['entity']] = entity
            name = {'issuer':'Structuration', 'bank':'Cotation', 'client':'Investissement'}[peer['role']]
            desk = next((d for d in desks if d['entity_id'] == entity['id'] and d['name'] == name), None)
            if desk is None:
                reply = client.post(actor['url'] + '/api/rfq-desks/admin', headers=headers,
                                    json={'entity_id':entity['id'], 'name':name})
                reply.raise_for_status()
                desk = reply.json()
                desks.append(desk)
            directory[key] = {'entity_id':entity['id'], 'desk_id':desk['id']}
        actor['rfq_directory'] = directory
