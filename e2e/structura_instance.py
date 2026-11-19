"""A throwaway Structura instance for the end-to-end journeys (P1-10, U4/U5).

The journeys drive the real interface: the built frontend (frontend/dist)
served by the real backend, in a real browser. The backend runs as a separate
process on a private data directory, never backend/data:

- simulation profile, the only start allowed without an installation
  identity (db/database.py, _require_simulation_bootstrap);
- one technical account whose password is generated here and sealed in the
  data directory, as the workshop does (core/simulation_bootstrap.py);
- scheduler and RFQ transport off, no AI key forwarded.

The process is stopped through its own control route, then, only if it does
not leave, by killing this exact process tree. Nothing else is touched.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
USERNAME = "workshop_admin"

# Environment that must never leak from the developer's shell into the
# throwaway instance: another installation's identity, keys or mode.
_INHERITED = ("STRUCTURA_JWT_SECRET", "STRUCTURA_INSTALLATION_CONFIG", "STRUCTURA_ADMIN_WORKBENCH_CONFIG",
              "STRUCTURA_DEVELOPER_ACCESS", "STRUCTURA_LAUNCH_ID", "STRUCTURA_CONSULTATION",
              "STRUCTURA_CONSULTATION_USER_ID", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _port_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


@dataclass
class Account:
    """A user of the instance, signed in through the API."""
    url: str
    username: str
    password: str
    desk_id: int | None = None
    _token: str | None = field(default=None, repr=False)

    def token(self) -> str:
        if self._token is None:
            reply = httpx.post(self.url + "/api/auth/login", data={"username": self.username, "password": self.password},
                               timeout=30, trust_env=False)
            assert reply.status_code == 200, f"connexion {self.username} → {reply.status_code} {reply.text[:300]}"
            self._token = reply.json()["access_token"]
        return self._token

    def call(self, method: str, path: str, payload=None, *, expected=(200, 201, 204)):
        reply = httpx.request(method, self.url + path, json=payload, timeout=120, trust_env=False,
                              headers={"Authorization": "Bearer " + self.token()})
        assert reply.status_code in expected, f"{method} {path} → {reply.status_code} {reply.text[:400]}"
        return reply.json() if reply.content else None


@dataclass
class Instance:
    url: str
    password: str
    data_dir: Path
    process: subprocess.Popen
    control: str
    port: int
    _token: str | None = field(default=None, repr=False)
    _business: "Account | None" = field(default=None, repr=False)

    @property
    def username(self) -> str:
        return USERNAME

    def token(self) -> str:
        if self._token is None:
            reply = httpx.post(self.url + "/api/auth/login", data={"username": USERNAME, "password": self.password},
                               timeout=30, trust_env=False)
            reply.raise_for_status()
            self._token = reply.json()["access_token"]
        return self._token

    def api(self, method: str, path: str, payload=None, *, expected=(200, 201)):
        """Arrange data through the API, so each journey tests one screen."""
        reply = httpx.request(method, self.url + path, json=payload, timeout=120, trust_env=False,
                              headers={"Authorization": "Bearer " + self.token()})
        assert reply.status_code in expected, f"{method} {path} → {reply.status_code} {reply.text[:400]}"
        return reply.json() if reply.content else None

    def business(self) -> "Account":
        """A front-office account (role `user`) on a pilot desk, for the journeys.

        The technical account administers; it does not structure. Nobody grants
        RFQ rights to themselves (api/rfq_desks.py), so the administrator
        creates the account, which sets its own password, then the
        administrator puts it on the desk."""
        if self._business is None:
            me = self.api("GET", "/api/auth/me")
            desk = self.api("POST", "/api/rfq-desks/admin", {"entity_id": me["entity_id"], "name": "Desk parcours"})
            provisional, final = secrets.token_urlsafe(24) + "aA1!", secrets.token_urlsafe(24) + "bB2?"
            user = self.api("POST", "/api/admin/users", {"username": "structureur", "email": "structureur@recette.invalid",
                                                        "password": provisional, "role": "user", "entity_id": me["entity_id"]})
            account = Account(self.url, "structureur", provisional)
            account.call("POST", "/api/auth/password", {"current_password": provisional, "new_password": final})
            account = Account(self.url, "structureur", final)
            self.api("PUT", f"/api/rfq-desks/admin/{desk['id']}/members/{user['id']}",
                     {"user_id": user["id"], "rights": ["read", "prepare", "price", "select", "solicit", "book"]})
            account.desk_id = desk["id"]
            self._business = account
        return self._business

    def log_tail(self, lines: int = 60) -> str:
        path = self.data_dir / "server.log"
        if not path.exists():
            return ""
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _environment(data_dir: Path, port: int, control: str) -> dict:
    # PYTEST_CURRENT_TEST would make the server believe it runs under pytest
    # (main.py): no pricing worker, no prewarm — the queue never answers.
    env = {key: value for key, value in os.environ.items()
           if key not in _INHERITED and not key.startswith("PYTEST")}
    env.update({
        "STRUCTURA_DATA_DIR": str(data_dir),
        "STRUCTURA_PORT": str(port),
        "STRUCTURA_BOOTSTRAP_PROFILE": "simulation",
        "STRUCTURA_WORKSHOP_CHILD": "1",
        "STRUCTURA_DISABLE_SCHEDULER": "1",
        "STRUCTURA_DISABLE_RFQ_TRANSPORT": "1",
        "STRUCTURA_INSTANCE_CONTROL_TOKEN": control,
        "STRUCTURA_WORKSHOP_ROOT": str(data_dir / "agent_workshop"),
        "STRUCTURA_STUDIES_ROOT": str(data_dir / "studies"),
        "TMP": str(data_dir / "tmp"), "TEMP": str(data_dir / "tmp"),
        "PYTHONPATH": str(ROOT / "backend"),
    })
    return env


def _stop(instance: Instance) -> None:
    process = instance.process
    if process.poll() is None:
        try:
            httpx.post(instance.url + "/_instance/stop", headers={"X-Instance-Control": instance.control},
                       timeout=5, trust_env=False)
            process.wait(timeout=20)
        except (httpx.HTTPError, subprocess.TimeoutExpired):
            if process.poll() is None:
                # This exact tree only: the server and the pricing workers it spawned.
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                   timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    process.kill()
                process.wait(timeout=15)
    deadline = time.monotonic() + 15
    while not _port_free(instance.port) and time.monotonic() < deadline:
        time.sleep(0.2)


@contextmanager
def running_instance(data_dir: Path, *, startup_timeout: float = 120):
    if not (DIST / "index.html").is_file():
        raise RuntimeError("frontend/dist absent : lancez `npm run build` dans frontend/ avant les parcours.")
    data_dir = Path(data_dir).resolve()
    if data_dir.is_relative_to((ROOT / "backend" / "data").resolve()):
        raise RuntimeError("Les parcours ne s'exécutent jamais sur backend/data.")
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("tmp", "studies", "agent_workshop"):
        (data_dir / name).mkdir(exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from backend.app.core.secret_store import write_secret
    from backend.app.core.simulation_bootstrap import BOOTSTRAP_FILENAME
    password = secrets.token_urlsafe(32)
    write_secret(data_dir / BOOTSTRAP_FILENAME, json.dumps({
        "username": USERNAME, "email": "e2e-bootstrap@recette.invalid", "password": password}))
    port, control = _free_port(), secrets.token_urlsafe(32)
    log = (data_dir / "server.log").open("a", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py")], cwd=str(ROOT),
                               env=_environment(data_dir, port, control), stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    instance = Instance(url=f"http://127.0.0.1:{port}", password=password, data_dir=data_dir,
                        process=process, control=control, port=port)
    try:
        deadline = time.monotonic() + startup_timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError("Le serveur des parcours s'est arrêté au démarrage :\n" + instance.log_tail())
            try:
                if httpx.get(instance.url + "/health/ready", timeout=2, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Le serveur des parcours ne répond pas :\n" + instance.log_tail())
            time.sleep(0.5)
        yield instance
    finally:
        _stop(instance)
        log.close()
