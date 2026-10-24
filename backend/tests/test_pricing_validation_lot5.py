from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.app.api.pricing import router
from backend.app.api.auth import get_current_user
from backend.app.core.schemas import PricingRequest


BASE = {
    "script": 'AT MATURITY\n  PAY 1 "capital"',
    "underlyings": [{"name": "S1", "sigma": 0.20, "q": 0.0}],
    "corr_matrix": [[1.0]],
    "r": 0.03,
    "T": 1.0,
    "N": 1000,
}


@pytest.fixture
def client(authenticated_client):
    authenticated_client.app.include_router(router)
    return authenticated_client


def test_pricing_route_refuses_anonymous_access():
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/price", json=BASE)
    assert response.status_code == 401


def test_noeud_de_courbe_malforme_retourne_422(client):
    response = client.post("/api/price", json={**BASE, "yield_curve": [[1.0]]})
    assert response.status_code == 422


@pytest.mark.parametrize("corr", [
    [[0.99]],
    [[1.0, 0.2], [0.3, 1.0]],
    [[1.0, 1.01], [1.01, 1.0]],
])
def test_matrice_de_correlation_malformee_est_refusee(corr):
    underlyings = BASE["underlyings"] * len(corr)
    with pytest.raises(ValidationError):
        PricingRequest(**{**BASE, "underlyings": underlyings, "corr_matrix": corr})


def test_reparation_correlation_et_approximation_barriere_traversent_api(client):
    correlation = [[1.0 if i == j else -0.5000001 for j in range(3)] for i in range(3)]
    repaired = client.post("/api/price", json={
        **BASE, "underlyings": [dict(BASE["underlyings"][0], name=f"S{i}") for i in range(3)],
        "corr_matrix": correlation,
    })
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["corr_repair"]["max_shift"] > 0
    assert repaired.json()["corr_repair"]["matrix_used"]
    payload = {
        **BASE,
        "underlyings": [
            {"name": "S1", "sigma": 0.20, "q": 0.0},
            {"name": "S2", "sigma": 0.20, "q": 0.0},
        ],
        "corr_matrix": [[1.0, 1.0], [1.0, 1.0]],
        "barrier_monitoring": "continuous",
        "T": 0.10,
    }
    response = client.post("/api/price", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    # Perfect copies use the exact semidefinite factor, without added noise.
    assert not body["corr_repair"]
    assert body["barrier_monitoring"] == "continuous"
    assert "brownien" in body["barrier_monitoring_note"]
