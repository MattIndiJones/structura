"""Prepare and operate only explicitly owned, fictitious local installations."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

from .config import InstallationConfig, credentials, read_config, signing_secret

ROOT = Path(__file__).resolve().parents[3]
LAYOUT_KIND = "STRUCTURA_HYBRID_DEV_1"
ORGANIZATIONS = (
    ("bnp-paribas", "BNP Paribas", "respond_rfq"),
    ("societe-generale", "Société Générale", "respond_rfq"),
    ("citi", "Citi", "respond_rfq"),
    ("ubs", "UBS", "respond_rfq"),
    ("leonteq", "Leonteq", "request_rfq"),
    ("kepler-cheuvreux-solutions", "Kepler Cheuvreux Solutions", "request_rfq"),
)


def atomic_json(path, payload):
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_layout(root):
    root = Path(root).resolve()
    payload = json.loads((root / "layout.json").read_text(encoding="utf-8"))
    if payload.get("kind") != LAYOUT_KIND or payload.get("root") != str(root):
        raise ValueError("Ce répertoire n'est pas un environnement Structura hybride identifié.")
    expected = {"platform", *(row[0] for row in ORGANIZATIONS)}
    if set(payload["installations"]) != expected:
        raise ValueError("L'environnement doit contenir exactement les sept installations prévues.")
    configs = []
    for key, value in payload["installations"].items():
        path = Path(value).resolve()
        if path != root / key / "installation.json":
            raise ValueError("Un manifeste sort du périmètre de son installation.")
        config = read_config(str(path))
        if config.key != key or config.data_dir.resolve() != root / key:
            raise ValueError("Identité ou répertoire d'installation incohérent.")
        if config.service != "application":
            raise ValueError("Un contrôleur auxiliaire ne peut pas remplacer une installation du portail.")
        configs.append(config)
    if len({str(c.installation_id) for c in configs}) != 7 or len({c.port for c in configs}) != 7:
        raise ValueError("Identités ou ports d'installation dupliqués.")
    directories = [c.data_dir.resolve() for c in configs]
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(directories) for b in directories[i + 1:]):
        raise ValueError("Les répertoires privés se recouvrent.")
    return configs


def prepare(root, base_port=8100):
    root = Path(root).resolve()
    protected = [ROOT, ROOT / "backend" / "data", ROOT / ".git"]
    if any(root == p or root in p.parents or p in root.parents for p in protected[1:]) or root == ROOT or root in ROOT.parents:
        raise ValueError("Ce chemin ne peut pas servir de runtime hybride.")
    if root.is_relative_to(ROOT) and not any(root == allowed or root.is_relative_to(allowed)
            for allowed in (ROOT / "tmp", ROOT / ".runtime" / "hybrid-saas")):
        raise ValueError("Un runtime dans le dépôt doit rester dans tmp/ ou .runtime/hybrid-saas/, ignorés par Git.")
    if not 1024 <= base_port <= 65529:
        raise ValueError("La plage de sept ports est invalide.")
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "layout.json"
    if marker.exists():
        configs = load_layout(root)
        if next(c.port for c in configs if c.key == "platform") != base_port:
            raise ValueError("La plage de ports existante est différente ; aucun remplacement implicite.")
    else:
        # A preparation marker permits recovery after a partially written layout.
        staging = root / "preparation.json"
        if staging.exists():
            payload = json.loads(staging.read_text(encoding="utf-8"))
            if payload.get("kind") != LAYOUT_KIND or payload.get("root") != str(root) or payload.get("base_port") != base_port:
                raise ValueError("Préparation incompatible ; aucun nettoyage automatique.")
        else:
            if any(root.iterdir()):
                raise ValueError("Le répertoire contient des données non identifiées ; préparation refusée.")
            atomic_json(staging, {"kind": LAYOUT_KIND, "root": str(root), "base_port": base_port})
        entries = [("platform", "Admin Structura", None), *ORGANIZATIONS]
        for index, (key, name, capability) in enumerate(entries):
            directory = root / key
            directory.mkdir(exist_ok=True)
            manifest = directory / "installation.json"
            if not manifest.exists():
                config = InstallationConfig(installation_id=uuid4(), organization_id=uuid4() if capability else None,
                    key=key, name=name, kind="organization" if capability else "platform",
                    data_dir=directory, port=base_port + index, capabilities=(capability,) if capability else ())
                atomic_json(manifest, config.model_dump(mode="json"))
        atomic_json(marker, {"kind": LAYOUT_KIND, "root": str(root),
            "installations": {key: str(root / key / "installation.json") for key, _, _ in entries}})
        configs = load_layout(root)
    for config in configs:
        directory = config.data_dir
        for name in ("logs", "tmp", "documents", "underlying_prices", "fx_rates", "ff_factors", "whisper_models", "studies"):
            (directory / name).mkdir(exist_ok=True)
        secret = directory / ".jwt_secret"
        if not secret.exists():
            if (directory / "structura.db").exists() or (directory / "platform.db").exists():
                raise ValueError("Une base existante a perdu sa clé ; restauration requise.")
            secret.write_text(secrets.token_urlsafe(64), encoding="utf-8")
        signing_secret(config)
        private = directory / ".bootstrap_credentials.json"
        if not private.exists():
            if (directory / "structura.db").exists() or (directory / "platform.db").exists():
                raise ValueError("Identifiants de bootstrap manquants pour une base existante.")
            names = ["admin"] if config.kind == "platform" else ["superuser", "front", "operations", "controller"]
            atomic_json(private, {name: secrets.token_urlsafe(32) for name in names})
        credentials(config)
        if config.kind == "organization":
            for source in (ROOT / "backend" / "data" / "ff_factors").glob("*.parquet"):
                target = directory / "ff_factors" / source.name
                if not target.exists():
                    shutil.copy2(source, target)
    descriptors = [c.public_descriptor() for c in configs if c.kind == "organization"]
    atomic_json(root / "platform" / "directory.json", descriptors)
    # Organization services only receive the public verification key. The
    # platform cannot mint normal organization sessions or read their secrets.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    platform = next(c for c in configs if c.kind == "platform")
    private_path = platform.data_dir / ".developer_private.pem"
    if not private_path.exists():
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path.write_bytes(private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    trust = {"installation_id": str(platform.installation_id), "url": platform.public_descriptor()["url"],
             "public_key": private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    for config in configs[1:]:
        atomic_json(config.data_dir / ".developer_trust.json", trust)
    return configs


def environment(config):
    env = {k: v for k, v in os.environ.items() if not k.startswith("STRUCTURA_") and k not in
           {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PYTEST_CURRENT_TEST"}}
    env.update(STRUCTURA_DATA_DIR=str(config.data_dir),
        STRUCTURA_INSTALLATION_CONFIG=str(config.data_dir / "installation.json"),
        STRUCTURA_PORT=str(config.port), STRUCTURA_INSTANCE_ID=str(config.installation_id),
        STRUCTURA_ALLOW_REGISTRATION="0", STRUCTURA_WORKSHOP_CHILD="1",
        STRUCTURA_STUDIES_ROOT=str(config.data_dir / "studies"),
        PYTHONPATH=str(ROOT / "backend"), TMP=str(config.data_dir / "tmp"), TEMP=str(config.data_dir / "tmp"))
    if config.service == "simulation_controller":
        env.update(STRUCTURA_WORKSHOP_CHILD="0", STRUCTURA_WORKSHOP_ROOT=str(config.data_dir / "campaigns"),
                   STRUCTURA_DISABLE_SCHEDULER="1")
    elif config.service == "admin_workbench":
        env.update(STRUCTURA_BOOTSTRAP_PROFILE="admin_workbench", STRUCTURA_WORKSHOP_CHILD="0",
                   STRUCTURA_WORKSHOP_ROOT=str(config.data_dir / "campaigns"))
    if config.service in {"admin_workbench", "simulation_controller"}:
        # Only the central campaign controller may call the external model.
        # Organization installations and agent children must not receive this key.
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_key:
            env["OPENAI_API_KEY"] = openai_key
    return env


def initialize(config):
    result = subprocess.run([sys.executable, str(ROOT / "backend" / "run.py"), "--initialize-only"],
        cwd=ROOT, env=environment(config), capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
    if result.returncode:
        raise RuntimeError(f"Initialisation {config.name} refusée : {result.stderr[-3000:]}")
    return {"key": config.key, "initialized": True, "report": result.stdout.strip()}


def probe(config):
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            response = client.get(config.public_descriptor()["url"] + "/health")
            response.raise_for_status()
            payload = response.json()
            return payload if payload.get("instance_id") == str(config.installation_id) else None
    except (httpx.HTTPError, ValueError):
        return None


def stop_candidate(config):
    """Skip never-started or confirmed-stopped services without HTTP waits."""
    control_path = config.data_dir / ".process.json"
    if not control_path.exists():
        return False
    control = json.loads(control_path.read_text(encoding="utf-8"))
    receipt_path = config.data_dir / "last_stop.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (control.get("launch_id") and receipt.get("launch_id") == control["launch_id"]
                and receipt.get("process_exited") and receipt.get("port_released")):
            return False
    with socket.socket() as sock:
        sock.settimeout(.15)
        return sock.connect_ex(("127.0.0.1", config.port)) == 0


def stop(config, timeout_seconds=40):
    control_path = config.data_dir / ".process.json"
    if not control_path.exists():
        return {"key": config.key, "stopped": False, "reason": "Aucun processus géré"}
    control = json.loads(control_path.read_text(encoding="utf-8"))
    health = probe(config)
    if health is None:
        with socket.socket() as sock:
            sock.settimeout(.15)
            occupied = sock.connect_ex(("127.0.0.1", config.port)) == 0
        if occupied:
            raise RuntimeError("Le port appartient à une autre instance ; aucun arrêt envoyé.")
        return {"key": config.key, "stopped": True, "port_released": True}
    if (control.get("server_pid") is not None and health["process_id"] != control["server_pid"]) or health.get("launch_id") != control["launch_id"]:
        raise RuntimeError("Identité du processus différente ; aucun arrêt envoyé.")
    server_pid = health["process_id"]
    # Pin the actual Windows process handle before sending the stop request.
    # This also proves exit when Uvicorn has released the port before finishing shutdown.
    handle = None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, server_pid)
        if not handle:
            raise RuntimeError("Le processus identifié ne peut pas être suivi ; aucun arrêt envoyé.")
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            response = client.post(config.public_descriptor()["url"] + "/_instance/stop",
                headers={"X-Instance-Control": control["token"]})
            response.raise_for_status()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                sock.settimeout(.05)
                released = sock.connect_ex(("127.0.0.1", config.port)) != 0
            if handle:
                exited = kernel.WaitForSingleObject(handle, 0) == 0
            elif os.name != "nt":
                try:
                    os.kill(server_pid, 0)
                    exited = False
                except ProcessLookupError:
                    exited = True
            else:
                exited = False
            if released and exited:
                result = {"key": config.key, "stopped": True, "pid": server_pid,
                          "launcher_pid": control["pid"], "launch_id": control["launch_id"],
                          "process_exited": True, "port_released": True}
                atomic_json(config.data_dir / "last_stop.json", result)
                return result
            time.sleep(.1)
        raise RuntimeError("L'arrêt propre n'est pas confirmé ; contrôle manuel du processus requis.")
    finally:
        if handle:
            kernel.CloseHandle(handle)


def start(config, developer_access=False, launcher_id=None):
    # A service opened from the portal belongs to the launcher's current scope.
    # Read the parent's live control record so a reused portal adopts the window
    # that explicitly opened it, without changing its PID or control secret.
    if launcher_id is None:
        from .config import current_config
        parent = current_config()
        if parent:
            path = parent.data_dir / ".process.json"
            if path.exists():
                metadata = json.loads(path.read_text(encoding="utf-8"))
                if metadata.get("launch_id") == os.environ.get("STRUCTURA_LAUNCH_ID"):
                    launcher_id = metadata.get("launcher_id")
    existing = probe(config)
    if existing:
        if bool(existing.get("developer_access")) != developer_access:
            raise RuntimeError("Le mode développeur du service existant diffère ; aucun redémarrage implicite.")
        record_path = config.data_dir / ".process.json"
        if launcher_id and record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("launch_id") == existing.get("launch_id") and record.get("installation_id") == str(config.installation_id):
                record["launcher_id"] = launcher_id
                atomic_json(record_path, record)
        return {"key": config.key, "started": False, "reused": True, "pid": existing["process_id"]}
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", config.port))
        except OSError as exc:
            raise RuntimeError(f"Port {config.port} occupé ; aucun processus remplacé.") from exc
    token, launch_id = secrets.token_urlsafe(48), str(uuid4())
    env = environment(config)
    env["STRUCTURA_DEVELOPER_ACCESS"] = "1" if developer_access else "0"
    env.update(STRUCTURA_INSTANCE_CONTROL_TOKEN=token, STRUCTURA_LAUNCH_ID=launch_id)
    command = [sys.executable, str(ROOT / "backend" / "run.py")]
    with (config.data_dir / "logs" / "server.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    record = {"pid": process.pid, "started_at": datetime.now(timezone.utc).isoformat(),
        "command": command, "installation_id": str(config.installation_id),
        "launch_id": launch_id, "token": token}
    if launcher_id:
        record["launcher_id"] = launcher_id
    try:
        atomic_json(config.data_dir / ".process.json", record)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{config.name} a quitté ; consulter son journal privé.")
            health = probe(config)
            if health and health.get("launch_id") == launch_id:
                record["server_pid"] = health["process_id"]
                atomic_json(config.data_dir / ".process.json", record)
                return {"key": config.key, "started": True, "pid": health["process_id"], "launcher_pid": process.pid,
                        "started_at": record["started_at"], "command": command}
            time.sleep(.2)
        raise RuntimeError(f"Démarrage {config.name} non confirmé.")
    except BaseException:
        # Windows virtualenv redirectors launch a second Python PID. Prefer
        # stopping its verified server, then reap the redirector; never kill a
        # preexisting process or trust a bare recycled PID.
        if process.poll() is None:
            try:
                health = probe(config)
                if health and health.get("launch_id") == launch_id:
                    stop(config)
                    process.wait(timeout=15)
                else:
                    raise RuntimeError("Serveur de notre lancement non confirmé")
            except Exception:
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    else:
                        process.terminate()
                    process.wait(timeout=15)
        raise
