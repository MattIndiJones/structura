"""P1-8 / S1: every response carries the browser security headers."""
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.core.security_headers import CONTENT_SECURITY_POLICY, install_security_headers


def test_the_application_sends_the_security_headers():
    response = TestClient(main.app).get("/health")
    headers = response.headers
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert "microphone=(self)" in headers["permissions-policy"]      # script dictation
    assert "strict-transport-security" not in headers                # plain HTTP on loopback


def test_errors_carry_them_too():
    response = TestClient(main.app).get("/api/deals")                 # 401 without a token
    assert response.status_code == 401
    assert response.headers["x-frame-options"] == "DENY"


def test_the_policy_allows_what_the_interface_loads_and_nothing_else():
    policy = dict(part.split(" ", 1) for part in CONTENT_SECURITY_POLICY.split("; "))
    assert policy["script-src"] == "'self'"                           # no eval, no inline script
    assert "frame-ancestors" in policy and policy["frame-ancestors"] == "'none'"
    assert "blob:" in policy["frame-src"]                             # valuation note preview
    assert "http://127.0.0.1:*" in policy["connect-src"]              # portal → installations
    assert "https://fonts.gstatic.com" in policy["font-src"]
    assert policy["object-src"] == "'none'"


def test_https_adds_hsts():
    response = TestClient(main.app, base_url="https://testserver").get("/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_the_api_docs_keep_their_cdn_but_not_the_framing():
    response = TestClient(main.app).get("/docs")
    assert "content-security-policy" not in response.headers
    assert response.headers["x-frame-options"] == "DENY"


def test_a_route_that_sets_a_header_keeps_its_value():
    app = FastAPI()
    install_security_headers(app)

    @app.get("/report")
    def report():
        return Response("x", headers={"Referrer-Policy": "same-origin"})

    assert TestClient(app).get("/report").headers["referrer-policy"] == "same-origin"
