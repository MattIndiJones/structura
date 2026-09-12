#!/usr/bin/env python3
"""Fail-fast smoke check for a newly installed Structura environment."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


MIN_PYTHON = (3, 11)
MODULES = (
    "fastapi", "uvicorn", "numpy", "scipy", "statsmodels", "pydantic",
    "httpx", "yfinance", "pandas", "pyarrow", "matplotlib", "reportlab",
    "openpyxl", "holidays", "sqlmodel", "sqlalchemy", "jose", "bcrypt",
    "faster_whisper",
)


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        print("ERREUR: Structura requiert Python 3.11 ou ultérieur.")
        return 1
    failures = []
    for module in MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failures.append(f"{module}: {exc}")
    if failures:
        print("ERREUR: environnement incomplet")
        for failure in failures:
            print(f"- {failure}")
        return 1
    from backend.app.main import app
    assert app.title
    print(f"OK: Python {sys.version.split()[0]}, {len(MODULES)} modules, import backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
