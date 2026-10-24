"""Build a static, data-free inventory for the application review.

This script parses source text only. It does not import the application, open
business databases, initialize services, collect tests, or access the network.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from collections import Counter

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
EXCLUDED = ("frontend/dist/", "docs/projects/platform/application-map-",)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8", "replace").strip()


def source(node):
    return ast.unparse(node) if node is not None else None


def doc(node):
    return (ast.get_docstring(node) or "")[:1600]


def function(node):
    return {
        "name": node.name, "line": node.lineno, "end_line": node.end_lineno,
        "signature": source(node.args), "returns": source(node.returns),
        "decorators": [source(x) for x in node.decorator_list], "docstring": doc(node),
    }


def inspect_python(path, text):
    tree = ast.parse(text, filename=path)
    classes, functions, routes, env = [], [], [], []
    prefixes = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if isinstance(value, ast.Call) and source(value.func).endswith("APIRouter"):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                prefix = next((source(k.value) for k in value.keywords if k.arg == "prefix"), "''")
                for target in targets:
                    prefixes[source(target)] = prefix.strip("'\"")
        if isinstance(node, ast.ClassDef):
            fields = []
            attributes = {}
            for member in node.body:
                if isinstance(member, ast.AnnAssign):
                    fields.append({"name": source(member.target), "type": source(member.annotation),
                                   "definition": source(member), "line": member.lineno})
                if isinstance(member, ast.Assign):
                    for target in member.targets:
                        if source(target) in {'__tablename__', '__table_args__', 'model_config'}:
                            attributes[source(target)] = source(member.value)
            classes.append({"name": node.name, "line": node.lineno, "end_line": node.end_lineno,
                            "bases": [source(x) for x in node.bases],
                            "keywords": [source(x) for x in node.keywords], "docstring": doc(node),
                            "attributes": attributes,
                            "fields": fields,
                            "methods": [function(x) for x in node.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(function(node))
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    method = decorator.func.attr
                    if method in {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}:
                        receiver = source(decorator.func.value)
                        route_path = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else source(decorator.args[0]) if decorator.args else ""
                        routes.append({"file": path, "line": node.lineno, "router": receiver,
                                       "method": method.upper(), "declared_path": route_path,
                                       "local_full_path": prefixes.get(receiver, "") + str(route_path),
                                       "function": node.name, "signature": source(node.args),
                                       "decorator": source(decorator), "docstring": doc(node)})
    known_routes = {(r['line'], r['method'], r['declared_path']) for r in routes}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    method = decorator.func.attr
                    if method in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'websocket', 'api_route'}:
                        receiver = source(decorator.func.value)
                        route_path = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else source(decorator.args[0]) if decorator.args else ''
                        key = (node.lineno, method.upper(), route_path)
                        if key not in known_routes:
                            declared_methods = next((ast.literal_eval(k.value) for k in decorator.keywords if k.arg == 'methods'), None)
                            routes.append({'file': path, 'line': node.lineno, 'router': receiver,
                                'method': method.upper(), 'declared_path': route_path,
                                'declared_methods': declared_methods,
                                'local_full_path': prefixes.get(receiver, '') + str(route_path),
                                'function': node.name, 'signature': source(node.args),
                                'decorator': source(decorator), 'docstring': doc(node), 'nested_factory': True})
                            known_routes.add(key)
        if isinstance(node, ast.Call) and source(node.func) in {"os.getenv", "os.environ.get", "getenv"}:
            if node.args and isinstance(node.args[0], ast.Constant):
                env.append({"name": node.args[0].value, "line": node.lineno})
        if isinstance(node, ast.Subscript) and source(node.value) == "os.environ" and isinstance(node.slice, ast.Constant):
            env.append({"name": node.slice.value, "line": node.lineno})
    router_declarations = [source(n) for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))
        and isinstance(n.value, ast.Call) and source(n.value.func).endswith('APIRouter')]
    mounts = [{'line': n.lineno, 'call': source(n)} for n in ast.walk(tree) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr in {'include_router', 'mount'}]
    return {"path": path, "docstring": doc(tree), "classes": classes,
            "functions": functions, "routes": routes, "environment": env,
            "router_declarations": router_declarations, "mounts": mounts,
            "imports": [source(x) for x in tree.body if isinstance(x, (ast.Import, ast.ImportFrom))]}


def main():
    names = sorted(set(git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()))
    files, python, frontend, tests, errors = [], [], [], [], []
    for name in names:
        if name.startswith("docs/audits/application-review-2026-10-24/") or name == "docs/audits/APPLICATION_REVIEW_2026-10-24.md":
            continue
        target = ROOT / name
        if not target.is_file() or name.startswith(EXCLUDED):
            continue
        if target.suffix.lower() not in {".py", ".vue", ".js", ".json", ".md", ".yml", ".yaml", ".txt", ".bat", ".vbs", ".toml", ".html", ".css"}:
            continue
        raw = target.read_bytes()
        text = raw.decode("utf-8-sig", "replace")
        files.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(),
                      "bytes": len(raw), "lines": len(text.splitlines())})
        if target.suffix == ".py" and (name.startswith(("backend/", "scripts/")) or name in {"book_campaign_v2.py"}):
            try:
                inspected = inspect_python(name, text)
                python.append(inspected)
                if name.startswith("backend/tests/"):
                    identifiers = [{"name": f["name"], "line": f["line"], "decorators": f["decorators"]}
                                   for f in inspected["functions"] if f["name"].startswith("test_")]
                    for cls in inspected["classes"]:
                        identifiers.extend({"name": cls["name"] + "::" + f["name"], "line": f["line"], "decorators": f["decorators"]}
                                           for f in cls["methods"] if f["name"].startswith("test_"))
                    tests.append({"path": name, "definitions": identifiers})
            except SyntaxError as exc:
                errors.append({"path": name, "error": str(exc)})
        if name.startswith("frontend/src/") and target.suffix in {".js", ".vue"}:
            frontend.append({"path": name,
                             "imports": re.findall(r"(?:import|from)\s*['\"]([^'\"]+)['\"]", text),
                             "api_literals": sorted(set(re.findall(r"['\"`](/api/[^'\"`\s]*)", text))),
                             "store_ids": re.findall(r"defineStore\(\s*['\"]([^'\"]+)", text),
                             "test_labels": re.findall(r"\b(?:it|test|describe)\(\s*['\"]([^'\"]+)", text)})
    routes = [r for module in python for r in module["routes"]]
    frontend_routes = []
    router_text = (ROOT / 'frontend/src/router/index.js').read_text(encoding='utf-8')
    for match in re.finditer(r"path:\s*'([^']+)'", router_text):
        tail = router_text[match.end():match.end()+220]
        view = re.search(r"views/([^']+)\.vue", tail)
        title = re.search(r"title:\s*'([^']+)'", tail)
        frontend_routes.append({'path': match[1], 'line': router_text[:match.start()].count('\n')+1,
            'view': view[1] if view else None, 'title': title[1] if title else None,
            'note': 'Lexical extraction; redirect target literals may also appear. See router source.'})
    models = [{"path": module["path"], **cls} for module in python for cls in module["classes"]
              if module["path"].startswith("backend/app/") and ("BaseModel" in str(cls["bases"]) or "SQLModel" in str(cls["bases"]) or "FrozenModel" in str(cls["bases"]) or "db/" in module["path"])]
    summary = {
        "inspection": "Static source parsing only; no application imports, data access, tests, runtime or network",
        "date": "2026-10-24", "timezone": "Europe/Berlin", "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"), "git_status_initial": git("status", "--porcelain=v1"),
        "source_files": len(files), "python_files_parsed": len(python), "python_syntax_errors": errors,
        "backend_app_files": sum(f["path"].startswith("backend/app/") and f["path"].endswith(".py") for f in files),
        "backend_app_lines": sum(f["lines"] for f in files if f["path"].startswith("backend/app/") and f["path"].endswith(".py")),
        "frontend_source_files": len(frontend),
        "frontend_source_lines": sum(f["lines"] for f in files if f["path"].startswith("frontend/src/") and f["path"].endswith((".vue", ".js"))),
        "route_declarations": len(routes), "backend_test_files": len(tests),
        "backend_test_definitions": sum(len(f["definitions"]) for f in tests),
        "frontend_test_files": sum(f["path"].endswith(".test.js") for f in frontend),
        "manifest_exclusions": ["ignored files", "binary files", "frontend/dist", "historical HTML atlas", "this report directory"],
        "top_backend_modules": sorted((f for f in files if f["path"].startswith("backend/app/") and f["path"].endswith(".py")), key=lambda f: -f["lines"])[:35],
    }
    payloads = {"SOURCE_MANIFEST.json": files, "PYTHON_SYMBOLS.json": python, "API_ROUTES.json": routes,
                "MODELS_AND_FIELDS.json": models, "FRONTEND_INVENTORY.json": frontend,
                "FRONTEND_ROUTES.json": frontend_routes,
                "TEST_DEFINITIONS.json": tests, "INSPECTION_REFERENCE.json": summary}
    for name, content in payloads.items():
        (OUT / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"git_status_initial", "top_backend_modules"}}, ensure_ascii=False, indent=2))
    print("Largest backend modules:")
    for item in summary["top_backend_modules"]:
        print(item["lines"], item["path"])


if __name__ == "__main__":
    main()
