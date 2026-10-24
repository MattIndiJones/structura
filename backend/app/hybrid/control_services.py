"""Owned auxiliary services outside the six manual business installations."""
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import InstallationConfig, read_config
from .deployment import atomic_json
from .development import enabled


def prepare_controls(platform):
    root = platform.data_dir.parent
    result = {}
    for key, service, port, name in (
        ("simulation", "simulation_controller", platform.port + 7, "Simulation avec agents"),
        ("admin-workbench", "admin_workbench", 8000, "Structura complet — Admin"),
    ):
        directory = root / key
        manifest = directory / "installation.json"
        if not manifest.exists():
            if directory.exists() and any(directory.iterdir()):
                raise ValueError("Répertoire auxiliaire non identifié ; aucun remplacement.")
            directory.mkdir(parents=True, exist_ok=True)
            config = InstallationConfig(installation_id=uuid4(), key=key, name=name, kind="platform",
                                        service=service, data_dir=directory, port=port)
            atomic_json(manifest, config.model_dump(mode="json"))
        config = read_config(str(manifest.resolve()))
        if config.service != service or config.data_dir != directory or config.key != key:
            raise ValueError("Identité de service auxiliaire incohérente.")
        for folder in ("tmp", "logs", "campaigns"):
            (directory / folder).mkdir(exist_ok=True)
        keyfile = directory / ".jwt_secret"
        if not keyfile.exists():
            keyfile.write_text(secrets.token_urlsafe(64), encoding="utf-8")
        if service == "admin_workbench" and not (directory / ".bootstrap_credentials.json").exists():
            atomic_json(directory / ".bootstrap_credentials.json", {"admin": secrets.token_urlsafe(32)})
        atomic_json(directory / "platform.json", platform.public_descriptor())
        if service == "simulation_controller":
            from cryptography.hazmat.primitives import serialization
            private = serialization.load_pem_private_key((platform.data_dir / ".developer_private.pem").read_bytes(), password=None)
            atomic_json(directory / ".developer_trust.json", {"installation_id": str(platform.installation_id),
                "url": platform.public_descriptor()["url"], "public_key": private.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()})
            atomic_json(platform.data_dir / "simulation.json", {"manifest": str(manifest.resolve()), "installation_id": str(config.installation_id)})
        result[key] = config
    if len({platform.port, *(c.port for c in result.values())}) != 3:
        raise ValueError("Les ports du portail et des services auxiliaires se recouvrent.")
    return result


def simulation_config(platform):
    payload = json.loads((platform.data_dir / "simulation.json").read_text(encoding="utf-8"))
    expected = platform.data_dir.parent / "simulation" / "installation.json"
    if Path(payload["manifest"]).resolve() != expected.resolve():
        raise RuntimeError("Contrôleur de simulation hors périmètre.")
    config = read_config(str(expected.resolve()))
    if config.service != "simulation_controller" or str(config.installation_id) != payload["installation_id"]:
        raise RuntimeError("Identité du contrôleur de simulation incohérente.")
    return config


def owned_stop(app, request):
    expected = os.environ.get("STRUCTURA_INSTANCE_CONTROL_TOKEN", "")
    if not expected or not secrets.compare_digest(expected, request.headers.get("X-Instance-Control", "")):
        raise HTTPException(404)
    app.state.instance_server.should_exit = True
    return {"stopping": True}


def redirect_app(config):
    descriptor = json.loads((config.data_dir / "platform.json").read_text(encoding="utf-8"))
    app = FastAPI(title="Structura — accès historique", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        return {"status": "ok", "kind": "portal_redirect", "instance_id": str(config.installation_id),
                "process_id": os.getpid(), "launch_id": os.environ.get("STRUCTURA_LAUNCH_ID"),
                "developer_access": enabled(config)}

    @app.post("/_instance/stop", include_in_schema=False)
    def stop(request: Request):
        return owned_stop(app, request)

    @app.get("/{path:path}")
    def redirect(path: str):
        # A fragment is retained by the browser when this target has none.
        return RedirectResponse(descriptor["url"] + "/", status_code=307)

    return app
