"""Inventory and retire identified fictitious data, without broad directory deletion."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess

from .deployment import atomic_json, load_layout


def safe_path(path, root):
    root, path = Path(root).resolve(), Path(path).absolute()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("La cible sort du dépôt autorisé.")
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part.exists() and (part.is_symlink() or getattr(part.stat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("Lien ou point de réanalyse refusé pour le nettoyage.")
    if path.resolve() != path:
        raise ValueError("Chemin redirigé refusé.")
    return path


def fingerprint(path):
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def identified_database(path):
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {"users", "entities"}.issubset(names) or {"platform_identity", "platform_users"}.issubset(names)
    except sqlite3.DatabaseError:
        return False


def inventory(root, runtime_root):
    root, runtime_root = Path(root).resolve(), Path(runtime_root).resolve()
    configs = load_layout(runtime_root)
    # New manual installations must exist and contain no business dossier.
    for config in configs:
        filename = "platform.db" if config.kind == "platform" else "structura.db"
        database = config.data_dir / filename
        if not identified_database(database):
            raise ValueError("Initialisation du nouveau runtime requise avant nettoyage.")
        if config.kind == "organization":
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
                for table in ("deals", "products", "rfq_requests", "amc_studies", "portfolios"):
                    if connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]:
                        raise ValueError("Le nouveau runtime contient déjà des dossiers ; nettoyage initial refusé.")
    targets, databases, skipped = set(), [], []
    for base in (root / "backend" / "data", root / "tmp"):
        for database in base.rglob("*.db"):
            path = safe_path(database, root)
            if path.is_relative_to(runtime_root):
                continue
            # Another checkout, even inside tmp/, belongs to another work.
            nested_repo = any((parent / ".git").exists() for parent in path.parents if parent != root and parent.is_relative_to(root))
            first = path.relative_to(base).parts[0]
            known_recipe = first.startswith(("rfq-", "hybrid-", "ccr-ui-")) or first == "postfix_validation.db"
            if nested_repo or (base.name == "tmp" and not known_recipe):
                skipped.append(str(path))
                continue
            if not identified_database(path):
                skipped.append(str(path))
                continue
            databases.append(str(path))
            targets.add(path)
            for suffix in ("-wal", "-shm", "-journal"):
                companion = Path(str(path) + suffix)
                if companion.exists():
                    targets.add(safe_path(companion, root))
            # Remove credentials, documents and runtime payloads only beside an
            # identified old installation, never an arbitrary temporary parent.
            if path.name in {"structura.db", "platform.db"}:
                for name in (".jwt_secret", ".bootstrap_credentials.json", ".developer_private.pem", ".process.json"):
                    candidate = path.parent / name
                    if candidate.is_file():
                        targets.add(safe_path(candidate, root))
                for name in ("documents", "studies"):
                    directory = path.parent / name
                    if directory.exists():
                        safe_path(directory, root)
                        targets.update(safe_path(p, root) for p in directory.rglob("*") if p.is_file())
    legacy = root / "backend" / "data"
    # The workshop's dedicated app storage is identified by campaign manifests.
    workshop = legacy / "agent_workshop"
    if workshop.exists():
        safe_path(workshop, root)
        campaigns = list(workshop.glob("*/campaign.json"))
        if not campaigns:
            raise ValueError("Stockage de simulation non identifié ; nettoyage refusé.")
        for campaign in campaigns:
            payload = json.loads(campaign.read_text(encoding="utf-8"))
            if payload.get("status") not in {"STOPPED", "COMPLETED", "FAILED", "CREATED"}:
                raise ValueError("Une campagne n'est pas arrêtée ; nettoyage refusé.")
        targets.update(safe_path(p, root) for p in workshop.rglob("*") if p.is_file())
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout.decode().split("\0")
    tracked_paths = {root / name for name in tracked if name}
    if targets & tracked_paths:
        raise ValueError("Un fichier versionné apparaît dans le nettoyage ; opération refusée.")
    return {"kind": "STRUCTURA_FICTITIOUS_RESET_1", "root": str(root), "runtime_root": str(runtime_root),
            "prepared_at": datetime.now(timezone.utc).isoformat(), "databases": databases,
            "files": [fingerprint(path) for path in sorted(targets)], "unidentified_databases_preserved": skipped}


def require_inactive(root, runtime_root):
    ports = {8000, *(c.port for c in load_layout(runtime_root))}
    # Include declared actor/recipe ports, without ever stopping their owners.
    for base in (root / "backend" / "data" / "agent_workshop", root / "tmp"):
        for path in base.rglob("*.json"):
            if path.name not in {"installation.json", "campaign.json", "instance.json"}:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                def collect(value):
                    if isinstance(value, dict):
                        for key, item in value.items():
                            if key == "port" and isinstance(item, int): ports.add(item)
                            else: collect(item)
                    elif isinstance(value, list):
                        for item in value: collect(item)
                collect(payload)
            except (ValueError, OSError):
                continue
    for port in ports:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise ValueError(f"Port {port} actif ; aucun nettoyage ni arrêt implicite.")
    if os.name == "nt":
        result = subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|node' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        processes = json.loads(result.stdout or "[]")
        if isinstance(processes, dict): processes = [processes]
        for process in processes:
            command = (process.get("CommandLine") or "").lower().replace("\\", "/")
            if str(root).lower().replace("\\", "/") in command and any(term in command for term in ("backend/run.py", "uvicorn", "vite")):
                raise ValueError(f"Processus Structura {process['ProcessId']} actif ; nettoyage refusé.")


def apply_inventory(plan, root, runtime_root):
    root, runtime_root = Path(root).resolve(), Path(runtime_root).resolve()
    if plan.get("kind") != "STRUCTURA_FICTITIOUS_RESET_1" or plan.get("root") != str(root) or plan.get("runtime_root") != str(runtime_root):
        raise ValueError("Inventaire incompatible.")
    require_inactive(root, runtime_root)
    current = inventory(root, runtime_root)
    if current["files"] != plan["files"]:
        raise ValueError("Les données ont changé depuis l'inventaire ; nettoyage refusé.")
    for entry in plan["files"]:
        path = safe_path(entry["path"], root)
        if path.is_relative_to(runtime_root):
            raise ValueError("Le runtime manuel ne peut pas être supprimé.")
    for entry in plan["files"]:
        safe_path(entry["path"], root).unlink()
    marker = root / "backend" / "data" / ".hybrid-retired.json"
    atomic_json(marker, {"retired_at": datetime.now(timezone.utc).isoformat(), "reason": "Fictitious data reset; use the hybrid installations"})
    result = {"deleted_files": len(plan["files"]), "deleted_databases": len(plan["databases"]),
              "legacy_sessions_invalidated": True, "manual_runtime_preserved": True,
              "unidentified_databases_preserved": plan["unidentified_databases_preserved"]}
    atomic_json(runtime_root / "cleanup-result.json", result)
    return result
