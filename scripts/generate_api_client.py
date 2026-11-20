"""Write frontend/src/api/generated.js from the server's OpenAPI schema (P1-11, A4).

One function per route that documents its response (api/contracts.py), with
JSDoc types read from the schema: the interface calls the server through
names and shapes the server publishes, instead of paths and fields typed by
hand. backend/tests/test_api_client.py fails when the file no longer matches
the schema: change a contract, then run

    .venv\\Scripts\\python.exe scripts\\generate_api_client.py

The schema is built from the application in this process; nothing is fetched.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend" / "src" / "api" / "generated.js"

HEADER = """\
// Généré par scripts/generate_api_client.py depuis le schéma OpenAPI du serveur
// (P1-11). Ne pas modifier à la main : changer le contrat de réponse de la
// route (backend/app/api/responses.py), puis relancer le script. Un test
// backend échoue tant que ce fichier ne correspond plus au schéma.
import { apiFetch, apiErrorMessage } from '../utils/api.js'

/** Refus du serveur : le message lisible, le statut HTTP et le corps reçu. */
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function call(method, path, { query, body } = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== undefined && value !== null) params.append(key, String(value))
  }
  const url = params.toString() ? `${path}?${params}` : path
  const init = { method }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const res = await apiFetch(url, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(apiErrorMessage(data, `Erreur ${res.status}`), res.status, data)
  return data
}
"""


def _app():
    # A throwaway data folder: building the schema imports the application,
    # whose modules fix their paths at import.
    os.environ.setdefault("STRUCTURA_DATA_DIR", tempfile.mkdtemp(prefix="structura-openapi-"))
    sys.path.insert(0, str(ROOT))
    from backend.app.main import app
    return app


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def js_type(schema: dict) -> str:
    if not schema:
        return "*"
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "const" in schema:
        return repr(schema["const"]).replace("True", "true").replace("False", "false")
    if "enum" in schema:
        return "|".join(f"'{v}'" if isinstance(v, str) else str(v).lower() for v in schema["enum"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return "(" + "|".join(dict.fromkeys(js_type(s) for s in schema[key])) + ")"
    kind = schema.get("type")
    if kind == "array":
        item = js_type(schema.get("items", {}))
        return f"Array<{item}>"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and not schema.get("properties"):
            return f"Object<string, {js_type(extra)}>"
        return "Object"
    return {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}.get(kind, "*")


def _refs(schema, found: set[str], components: dict) -> None:
    if isinstance(schema, dict):
        if "$ref" in schema:
            name = _ref_name(schema["$ref"])
            if name not in found:
                found.add(name)
                _refs(components.get(name, {}), found, components)
        for value in schema.values():
            _refs(value, found, components)
    elif isinstance(schema, list):
        for value in schema:
            _refs(value, found, components)


def _typedef(name: str, schema: dict) -> str:
    lines = ["/**"]
    description = (schema.get("description") or "").strip().splitlines()
    lines += [f" * {line}".rstrip() for line in description]
    if schema.get("type") == "object" or "properties" in schema:
        lines.append(f" * @typedef {{Object}} {name}")
        required = set(schema.get("required", []))
        for prop, sub in schema.get("properties", {}).items():
            label = prop if prop in required else f"[{prop}]"
            lines.append(f" * @property {{{js_type(sub)}}} {label}")
    else:
        lines.append(f" * @typedef {{{js_type(schema)}}} {name}")
    lines.append(" */")
    return "\n".join(lines)


def _response_schema(operation: dict) -> dict | None:
    for code, response in sorted(operation.get("responses", {}).items()):
        if code.startswith("2"):
            schema = response.get("content", {}).get("application/json", {}).get("schema")
            if schema:
                return schema
    return None


def _function_name(operation: dict) -> str:
    # FastAPI's summary is the endpoint's name, title-cased: "List Alerts".
    words = re.findall(r"[A-Za-z0-9]+", operation.get("summary") or operation["operationId"])
    name = _camel("_".join(word.lower() for word in words))
    return name[:-len("Endpoint")] if name.endswith("Endpoint") and len(name) > len("Endpoint") else name


def render(spec: dict) -> str:
    components = spec.get("components", {}).get("schemas", {})
    functions, used = [], set()
    for path, operations in sorted(spec["paths"].items()):
        for method, operation in sorted(operations.items()):
            response = _response_schema(operation)
            if response is None:
                continue
            _refs(response, used, components)
            name = _function_name(operation)
            path_params = re.findall(r"{(\w+)}", path)
            query = [p for p in operation.get("parameters", []) if p.get("in") == "query"]
            body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body:
                _refs(body, used, components)
            args, doc = [], ["/**", f" * {method.upper()} {path}"]
            summary = (operation.get("description") or operation.get("summary") or "").strip().splitlines()
            if summary:
                doc.append(f" * {summary[0]}")
            for param in path_params:
                args.append(param)
                doc.append(f" * @param {{number|string}} {param}")
            if body:
                args.append("body")
                doc.append(f" * @param {{{js_type(body)}}} body")
            if query:
                args.append("query = {}")
                doc.append(" * @param {Object} [query]")
                for param in query:
                    label = f"query.{param['name']}" if param.get("required") else f"[query.{param['name']}]"
                    doc.append(f" * @param {{{js_type(param.get('schema', {}))}}} {label}")
            doc.append(f" * @returns {{Promise<{js_type(response)}>}}")
            doc.append(" */")
            url = "`" + re.sub(r"{(\w+)}", r"${encodeURIComponent(\1)}", path) + "`" if path_params else f"'{path}'"
            options = ", ".join(part for part in (("query" if query else ""), ("body" if body else "")) if part)
            call_args = f"'{method.upper()}', {url}" + (f", {{ {options} }}" if options else "")
            functions.append("\n".join(doc) + f"\nexport function {name}({', '.join(args)}) {{\n  return call({call_args})\n}}")
    typedefs = [_typedef(name, components[name]) for name in sorted(used) if name in components]
    return HEADER + "\n" + "\n\n".join(typedefs) + "\n\n" + "\n\n".join(functions) + "\n"


def generate() -> str:
    app = _app()
    return render(app.openapi())


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generate(), encoding="utf-8", newline="\n")
    print(f"{TARGET.relative_to(ROOT)} écrit.")
