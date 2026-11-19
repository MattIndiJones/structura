"""Write requirements.lock.txt: every package, pinned and hashed (P1-8, S12).

The lock used to pin the 26 direct dependencies only, out of 94 installed:
the other 68 floated with each install. This script takes the direct pins of
requirements.direct.txt, walks their dependencies in the environment that
ran the tests (markers evaluated for it: Windows, Python 3.11, like the CI),
and pins each package at its INSTALLED version. It then lists the SHA-256 of
every file PyPI publishes for that version, so `pip install --require-hashes`
works on any platform and refuses a file that was swapped on the index.

    .venv/Scripts/python.exe scripts/lock_requirements.py

Network: one JSON request per package to pypi.org, nothing else is sent.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
DIRECT = ROOT / "requirements.direct.txt"
LOCK = ROOT / "requirements.lock.txt"


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def direct_requirements() -> list[Requirement]:
    lines = [line.split("#", 1)[0].strip() for line in DIRECT.read_text(encoding="utf-8").splitlines()]
    return [Requirement(line) for line in lines if line]


def closure(roots: list[Requirement]) -> dict[str, tuple[str, str]]:
    """canonical name -> (distribution name, installed version)."""
    found: dict[str, tuple[str, str]] = {}
    pending = [(requirement, frozenset(requirement.extras)) for requirement in roots]
    seen_extras: dict[str, set] = {}
    base = default_environment()
    while pending:
        requirement, extras = pending.pop()
        key = canonical(requirement.name)
        known = seen_extras.setdefault(key, set())
        if key in found and extras <= known:
            continue
        known |= extras
        distribution = metadata.distribution(requirement.name)
        version = distribution.version
        if requirement.specifier and version not in requirement.specifier:
            raise SystemExit(f"{requirement.name} {version} installé, {requirement.specifier} demandé.")
        found[key] = (distribution.metadata["Name"], version)
        for line in distribution.requires or []:
            child = Requirement(line)
            if child.marker is not None:
                if not any(child.marker.evaluate({**base, "extra": extra}) for extra in (extras or {""})):
                    continue
            pending.append((child, frozenset(child.extras)))
    return found


def published_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "structura-lock/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        files = json.load(response)["urls"]
    hashes = sorted({item["digests"]["sha256"] for item in files})
    if not hashes:
        raise SystemExit(f"Aucun fichier publié pour {name}=={version}.")
    return hashes


def main() -> None:
    roots = direct_requirements()
    extras = {canonical(r.name): sorted(r.extras) for r in roots if r.extras}
    packages = closure(roots)
    lines = [
        "# Généré par scripts/lock_requirements.py — ne pas éditer à la main.",
        f"# {len(packages)} paquets : dépendances directes de requirements.direct.txt et toutes",
        "# leurs dépendances, aux versions installées qui ont passé les tests (Windows,",
        f"# Python {sys.version_info.major}.{sys.version_info.minor}). Chaque fichier publié sur PyPI a son empreinte :",
        "#     python -m pip install --require-hashes -r requirements.lock.txt",
        "",
    ]
    for key in sorted(packages):
        name, version = packages[key]
        suffix = f"[{','.join(extras[key])}]" if key in extras else ""
        hashes = published_hashes(name, version)
        lines.append(f"{name}{suffix}=={version} \\")
        lines.extend(f"    --hash=sha256:{digest}" + (" \\" if i < len(hashes) - 1 else "")
                     for i, digest in enumerate(hashes))
    LOCK.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{LOCK.name} : {len(packages)} paquets verrouillés.")


if __name__ == "__main__":
    main()
