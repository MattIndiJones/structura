"""Native read-only viewers of saved actor books, independent of AI execution."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode

import httpx
from .instances import ROOT, free_port, clock_file
from .lease import CampaignLease
from .persistence import atomic_write
from .store import store

ACTOR_KEYS = {"hector", "bnp", "ca", "sg", "client"}
INACTIVE = {"STOPPED", "COMPLETED", "ATTENTION"}


class Consultations:
    def __init__(self):
        self.lock = threading.RLock()
        self.children = {}

    def _path(self, key, actor):
        if actor not in ACTOR_KEYS:
            raise ValueError("Cet acteur ne possède pas d'installation consultable.")
        root = store.path(key).resolve()
        path = root / "consultations" / actor
        if path.resolve() != path:
            raise ValueError("Dossier de consultation invalide.")
        return path

    def _record(self, key, actor):
        path = self._path(key, actor) / "instance_control.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def _health(self, record):
        if not record:
            return None
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                response = client.get(record["url"] + "/health")
                response.raise_for_status()
                health = response.json()
            if (health.get("instance_id") == record["identity"] and health.get("read_only") is True
                    and (not record.get("server_pid") or health.get("process_id") == record["server_pid"])):
                return health
        except (httpx.HTTPError, ValueError):
            pass
        return None

    def status(self, key):
        result = {}
        for actor in ACTOR_KEYS:
            record = self._record(key, actor)
            if record and self._health(record):
                result[actor] = {k: record[k] for k in ("actor", "url", "opened_at", "business_date")}
                result[actor].update(read_only=True, online=True)
        return result

    def active(self, key):
        # The OS lease survives a controller restart and does not depend on HTTP health.
        return any(CampaignLease.is_held(self._path(key, actor)) is not False for actor in ACTOR_KEYS) or bool(self.status(key))

    def _session(self, record):
        with httpx.Client(timeout=5, trust_env=False) as client:
            response = client.post(record["url"] + "/_instance/consultation-session",
                                   headers={"X-Instance-Control": record["token"]})
            response.raise_for_status()
            token = response.json()["access_token"]
        # The token remains in the URL fragment, never in HTTP access logs.
        return {"actor": record["actor"], "url": record["url"], "read_only": True,
                "business_date": record["business_date"],
                "launch_url": record["url"] + "/#/consultation?" + urlencode({"token": token})}

    def open(self, key, owner, actor):
        with self.lock, store.lifecycle_guard(key):
            state = store.load(key)
            if state["owner"] != owner:
                raise FileNotFoundError("Campagne introuvable.")
            directory = self._path(key, actor)
            if state["status"] not in INACTIVE or CampaignLease.is_held(store.path(key)) is not False:
                raise ValueError("Arrêter les IA et attendre leur fermeture avant d'ouvrir une consultation.")
            saved = state["actors"].get(actor)
            if not saved or not saved["registered"]:
                raise ValueError("Cet acteur ne possède pas encore de compte sauvegardé.")
            previous = self._record(key, actor)
            if self._health(previous):
                return self._session(previous)
            if CampaignLease.is_held(directory) is not False:
                raise ValueError("La consultation existante est encore ouverte ; la fermer avant de réessayer.")
            child = self.children.get((key, actor))
            if child and child[0].poll() is None:
                raise RuntimeError("La consultation existante ne répond pas ; la fermer avant de réessayer.")
            source = store.path(key).resolve() / "instances" / actor
            database = source / "structura.db"
            if source.resolve() != source or not database.is_file() or database.resolve() != database:
                raise ValueError("Le book sauvegardé de cet acteur est introuvable.")
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
                user = connection.execute("SELECT id FROM users WHERE username=? AND is_active=1",
                                          ("agent_" + actor,)).fetchone()
            if not user:
                raise ValueError("Le compte sauvegardé de cet acteur est indisponible.")
            directory.mkdir(parents=True, exist_ok=True)
            clock = clock_file(directory, state["business_date"])
            record = {"actor": actor, "url": f"http://127.0.0.1:{free_port()}",
                      "identity": secrets.token_urlsafe(24), "token": secrets.token_urlsafe(48),
                      "opened_at": datetime.now(timezone.utc).isoformat(), "business_date": state["business_date"]}
            environment = {**os.environ, "STRUCTURA_DATA_DIR": str(source),
                "STRUCTURA_PORT": record["url"].rsplit(":", 1)[1], "STRUCTURA_CONSULTATION": "1",
                "STRUCTURA_CONSULTATION_USER_ID": str(user[0]), "STRUCTURA_CONSULTATION_ENTITY": saved["entity"],
                "STRUCTURA_CONSULTATION_LOCK_DIR": str(directory),
                "STRUCTURA_ALLOW_REGISTRATION": "0", "STRUCTURA_DISABLE_SCHEDULER": "1",
                "STRUCTURA_WORKSHOP_CHILD": "1", "STRUCTURA_BUSINESS_CLOCK": str(clock),
                "STRUCTURA_SCENARIO_MARKET": str(store.path(key).resolve() / "synthetic_market.json"),
                "STRUCTURA_WORKSHOP_ROOT": str(directory / "agent_workshop"),
                "STRUCTURA_INSTANCE_CONTROL_TOKEN": record["token"], "STRUCTURA_INSTANCE_ID": record["identity"],
                "STRUCTURA_JWT_SECRET": secrets.token_urlsafe(64), "PYTHONPATH": str(ROOT / "backend")}
            output = (directory / "server.log").open("a", encoding="utf-8")
            command = [sys.executable, str(ROOT / "backend" / "run.py")]
            try:
                process = subprocess.Popen(command, cwd=str(ROOT), env=environment, stdout=output,
                    stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:
                output.close()
                raise
            self.children[(key, actor)] = (process, output)
            record.update(pid=process.pid, command=command)
            atomic_write(directory / "instance_control.json", json.dumps(record))
            try:
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("La consultation n'a pas démarré ; consulter son journal serveur.")
                    health = self._health(record)
                    if health:
                        record["server_pid"] = health["process_id"]
                        atomic_write(directory / "instance_control.json", json.dumps(record))
                        return self._session(record)
                    time.sleep(.2)
                raise RuntimeError("La consultation ne répond pas ; aucun agent IA n'a été relancé.")
            except Exception:
                self._close(key, actor, record)
                raise

    def _close(self, key, actor, record):
        child = self.children.get((key, actor))
        if self._health(record):
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.post(record["url"] + "/_instance/stop",
                                       headers={"X-Instance-Control": record["token"]})
                response.raise_for_status()
            deadline = time.monotonic() + (5 if child else 40)
            while time.monotonic() < deadline and self._health(record):
                time.sleep(.2)
        if child:
            process, output = child
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # A live Popen handle belongs to this exact child, not a recycled PID.
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    process.terminate()
                process.wait(timeout=10)
            output.close()
            self.children.pop((key, actor), None)
        if self._health(record) or CampaignLease.is_held(self._path(key, actor)) is not False:
            raise RuntimeError("La consultation ne s'est pas fermée ; conserver le book et réessayer.")

    def close(self, key, owner, actor):
        with self.lock, store.lifecycle_guard(key):
            if store.load(key)["owner"] != owner:
                raise FileNotFoundError("Campagne introuvable.")
            record = self._record(key, actor)
            if record:
                self._close(key, actor, record)
            return {"actor": actor, "closed": True}

    def shutdown(self):
        with self.lock:
            for key, actor in list(self.children):
                self._close(key, actor, self._record(key, actor))


consultations = Consultations()
