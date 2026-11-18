"""One application version: OpenAPI metadata, /health and the frontend package.

Three different numbers coexisted (0.2.0, 0.1.0, 0.1.0) and no delivery could
be named. backend/app/version.py is now the only source.
"""
import asyncio
import json
from pathlib import Path

from backend.app import main
from backend.app.version import VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_api_metadata_and_health_report_the_single_version(monkeypatch):
    monkeypatch.delenv("STRUCTURA_INSTANCE_ID", raising=False)
    assert main.app.version == VERSION
    assert asyncio.run(main.health())["version"] == VERSION


def test_frontend_package_follows_the_application_version():
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == VERSION
