from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import httpx
from .persistence import atomic_write

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

    def start(self):
        clock = clock_file(self.directory, self.state["business_date"])
        from ..scenario_market import create_market
        market = self.directory / "synthetic_market.json"
        if not market.exists():
            create_market(market, self.state["config"]["start_date"], self.state["config"]["seed"], self.state["config"]["months"])
        for key, actor in self.state["actors"].items():
            if key == "achille":
                continue
            directory = self.directory / "instances" / key
            directory.mkdir(parents=True, exist_ok=True)
            if self.cancelled():
                raise RuntimeError("Arrêt demandé pendant la préparation des instances.")
            self.recover(directory)
            actor["url"] = f"http://127.0.0.1:{free_port()}"
            control = secrets.token_urlsafe(48)
            identity = secrets.token_urlsafe(24)
            env = {**os.environ, "STRUCTURA_DATA_DIR": str(directory),
                "STRUCTURA_WORKSHOP_ROOT": str(directory / "agent_workshop"),
                "STRUCTURA_PORT": actor["url"].rsplit(":", 1)[1],
                "STRUCTURA_ALLOW_REGISTRATION": "1", "STRUCTURA_DISABLE_SCHEDULER": "1",
                "STRUCTURA_BUSINESS_CLOCK": str(clock), "STRUCTURA_WORKSHOP_CHILD": "1",
                "STRUCTURA_SCENARIO_MARKET": str(market),
                "STRUCTURA_INSTANCE_CONTROL_TOKEN": control,
                "STRUCTURA_INSTANCE_ID": identity,
                "PYTHONPATH": str(ROOT / "backend")}
            # Each installation persists its own signing key in its private
            # data directory. Restarting must preserve native pricing proofs.
            env.pop("STRUCTURA_JWT_SECRET", None)
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
                login = client.post(actor["url"] + "/api/auth/login", data={"username": "admin", "password": "admin123"})
                login.raise_for_status()
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                existing = client.get(actor["url"] + "/api/admin/counterparties", headers=headers).json()
                names = {row["name"] for row in existing}
                for other in self.state["actors"].values():
                    if other["role"] != "supervisor" and other["entity"] not in names:
                        reply = client.post(actor["url"] + "/api/admin/counterparties", headers=headers,
                            json={"name": other["entity"], "country": "FR"})
                        reply.raise_for_status()
                counterparties = client.get(actor["url"] + "/api/admin/counterparties", headers=headers).json()
                catalog = {r["name"]: r["id"] for r in counterparties}
                providers = client.get(actor["url"] + "/api/admin/rfq-providers", headers=headers).json()
                for other in self.state["actors"].values():
                    if other["role"] != "bank":
                        continue
                    provider = next((p for p in providers if p["label"] == other["entity"]), None)
                    payload = {"counterparty_id": catalog[other["entity"]], "mode": "banque"}
                    if provider:
                        reply = client.patch(actor["url"] + f"/api/admin/rfq-providers/{provider['id']}", headers=headers, json=payload)
                    else:
                        reply = client.post(actor["url"] + "/api/admin/rfq-providers", headers=headers, json={**payload, "label": other["entity"]})
                    reply.raise_for_status()
                actor["online"] = True

    def stop(self):
        for process, (url, token) in zip(self.processes, self.controls):
            if process.poll() is None:
                try:
                    httpx.post(url + "/_instance/stop", headers={"X-Instance-Control": token}, timeout=10, trust_env=False)
                    process.wait(timeout=35)
                except (httpx.HTTPError, subprocess.TimeoutExpired):
                    # Only this controller's exact child tree, never an arbitrary Python PID.
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    else:
                        process.terminate()
                    process.wait(timeout=10)
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
        if actor["role"] not in {"bank", "issuer"}:
            return
        if actor["url"] not in {url for url, _ in self.controls}:
            raise ValueError("Cette instance n'appartient pas au contrôleur.")
        with httpx.Client(timeout=10, trust_env=False) as client:
            login = client.post(actor["url"] + "/api/auth/login", data={"username":"admin", "password":"admin123"})
            login.raise_for_status()
            reply = client.patch(actor["url"] + f"/api/admin/users/{user_id}",
                headers={"Authorization":"Bearer " + login.json()["access_token"]}, json={"role":"admin"})
            reply.raise_for_status()
