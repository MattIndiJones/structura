"""Select changed tests and their direct backend consumers without importing the app."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess


# These entry points fan out across unrelated domains. Select their scope manually.
SHARED_MODULES = {
    "backend.app.main", "backend.app.db.models", "backend.app.db.database",
    "backend.app.core.schemas",
}


def module_name(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def imported_modules(source: str) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Include monkeypatch/importlib targets that do not use an import statement.
            if node.value.startswith("backend."):
                modules.add(node.value)
    return modules


def select_backend(root: Path, changed: list[str]) -> tuple[list[str], list[str]]:
    tests = sorted(root.glob("backend/tests/test_*.py"))
    selected = {p for p in changed if p.startswith("backend/tests/test_")
                and p.endswith(".py") and (root / p).is_file()}
    modules = {module_name(p) for p in changed
               if p.startswith(("backend/app/", "backend/scripts/")) and p.endswith(".py")}
    shared = modules & SHARED_MODULES
    modules -= SHARED_MODULES
    for path in tests:
        imports = imported_modules(path.read_text(encoding="utf-8-sig"))
        if any(ref == module or ref.startswith(module + ".")
               for module in modules for ref in imports):
            selected.add(path.relative_to(root).as_posix())
    notes = []
    if shared or "backend/tests/conftest.py" in changed:
        notes.append("Module partagé modifié : préciser les tests du domaine en lancement manuel ; aucune suite complète automatique.")
    if modules and not selected:
        notes.append("Aucun consommateur direct détecté : préciser les tests d'intégration en lancement manuel.")
    # A broad selection must never turn into an implicit full-suite request.
    if tests and len(selected) == len(tests):
        selected.clear()
        notes.append("Sélection couvrant toute la suite : lancement manuel avec périmètre explicite requis.")
    return sorted(selected), notes


def manual_targets(root: Path, value: str) -> list[str]:
    targets = value.split()
    for target in targets:
        path = target.split("::", 1)[0]
        if (not path.startswith("backend/tests/") or not path.endswith(".py")
                or ".." in Path(path).parts or not (root / path).is_file()):
            raise ValueError(f"Cible pytest invalide : {target}")
    return list(dict.fromkeys(targets))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> None:
    root = Path.cwd()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    inputs = event.get("inputs", {}) if os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch" else {}
    full = str(inputs.get("full_suite", "false")).lower() == "true"
    pr = event.get("pull_request", {})
    before = event.get("before") if event.get("action") == "synchronize" else None
    base = before or (git("merge-base", pr["base"]["sha"], "HEAD") if pr else git("rev-parse", "HEAD^"))
    changed = git("diff", "--name-only", "--no-renames", base, "HEAD").splitlines()
    targets, notes = select_backend(root, changed)
    if inputs.get("backend_tests", "").strip():
        targets = manual_targets(root, inputs["backend_tests"])
        notes = []
    if full:
        targets, notes = ["backend/tests"], []
    frontend = full or any(p.startswith("frontend/") and not p.startswith("frontend/dist/") for p in changed)
    output = {"backend_tests": json.dumps(targets), "frontend": str(frontend).lower(), "base": base}
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for key, value in output.items():
            stream.write(f"{key}={value}\n")
    summary = "\n".join([
        "### Tests sélectionnés", "",
        "Suite complète demandée." if full else "Tests modifiés et consommateurs directs ; périmètre indicatif à compléter si nécessaire.",
        *[f"- `{target}`" for target in targets], *[f"- {note}" for note in notes],
        "Tests frontend liés aux changements et build." if frontend else "Frontend inchangé : aucun test ni build rejoué.",
    ])
    print(summary)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
        stream.write(summary + "\n")


if __name__ == "__main__":
    main()
