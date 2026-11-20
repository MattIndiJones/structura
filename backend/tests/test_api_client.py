"""The interface's generated client follows the server's contracts (P1-11, A4)."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.contracts import Contract, ContractRoute, returns

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    spec = importlib.util.spec_from_file_location("generate_api_client", ROOT / "scripts" / "generate_api_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_le_client_genere_correspond_au_schema_du_serveur():
    generator = _generator()
    expected = generator.generate()
    current = generator.TARGET.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == expected, (
        "frontend/src/api/generated.js ne correspond plus aux contrats de réponse du serveur : "
        "lancez .venv\\Scripts\\python.exe scripts\\generate_api_client.py puis relisez le diff.")


def test_les_routes_les_plus_utilisees_publient_leur_reponse():
    from backend.app.main import app
    spec = app.openapi()
    typed = {(method.upper(), path) for path, operations in spec["paths"].items()
             for method, operation in operations.items()
             if any(r.get("content", {}).get("application/json", {}).get("schema")
                    for code, r in operation.get("responses", {}).items() if code.startswith("2"))}
    for route in [("GET", "/api/deals"), ("GET", "/api/deals/{deal_id}"), ("POST", "/api/deals/{deal_id}/mtm"),
                  ("GET", "/api/auth/me"), ("POST", "/api/schedule/generate"), ("POST", "/api/calendar/resolve"),
                  ("GET", "/api/finance/hist_prices"), ("POST", "/api/price/in-life"), ("GET", "/api/price/jobs/{job_id}")]:
        assert route in typed
    assert len(typed) >= 26


def test_les_fonctions_generees_ont_des_noms_uniques():
    source = _generator().TARGET.read_text(encoding="utf-8")
    names = [line.split("(")[0].removeprefix("export function ") for line in source.splitlines()
             if line.startswith("export function ")]
    assert len(names) == len(set(names)) >= 26


# ── The contract check itself ───────────────────────────────────────────

class Greeting(Contract):
    text: str
    count: int


def _app(payload):
    app = FastAPI()
    from fastapi import APIRouter
    router = APIRouter(route_class=ContractRoute)

    @router.get("/greeting", responses=returns(Greeting))
    def greeting():
        return payload

    @router.get("/free")
    def free():
        return {"anything": True}

    app.include_router(router)
    return TestClient(app)


def test_une_reponse_conforme_passe_intacte():
    reply = _app({"text": "bonjour", "count": 2}).get("/greeting")
    assert reply.status_code == 200 and reply.json() == {"text": "bonjour", "count": 2}


@pytest.mark.parametrize("payload, field", [
    ({"text": "bonjour", "count": 2, "extra": 1}, "extra"),       # a field nobody declared
    ({"text": "bonjour"}, "count"),                               # a declared field gone
    ({"text": "bonjour", "count": "deux"}, "count"),              # a type that changed
])
def test_une_reponse_qui_derive_de_son_contrat_echoue_en_test(payload, field):
    reply = _app(payload).get("/greeting")
    assert reply.status_code == 500
    body = reply.json()
    assert body["detail"] == "Réponse hors contrat sur GET /greeting."
    assert body["contract_errors"][0]["champ"] == field


def test_une_route_sans_contrat_n_est_pas_controlee():
    assert _app({}).get("/free").json() == {"anything": True}


def test_hors_validation_la_reponse_n_est_jamais_touchee(monkeypatch):
    monkeypatch.setenv("STRUCTURA_VALIDATE_RESPONSES", "0")
    reply = _app({"text": "bonjour", "count": 2, "extra": 1}).get("/greeting")
    assert reply.status_code == 200 and json.loads(reply.content)["extra"] == 1
