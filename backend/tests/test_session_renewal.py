"""P1-8 / S4: 30-minute tokens renewed by the open tab, 12-hour sessions."""
import time

from jose import jwt

from backend.app.api import auth
from backend.tests.test_hybrid_bootstrap import login, managed  # noqa: F401  (fixture)


def _claims(headers):
    return jwt.get_unverified_claims(headers["Authorization"].split(" ", 1)[1])


def _bearer(token):
    return {"Authorization": "Bearer " + token}


def _reissued(headers, **changes):
    """The same signed session with some claims rewritten."""
    claims = {**_claims(headers), **changes}
    for name in [name for name, value in changes.items() if value is None]:
        claims.pop(name)
    return _bearer(jwt.encode(claims, auth._SECRET, algorithm=auth._ALGO))


def test_a_login_token_lasts_thirty_minutes_and_records_its_session_start(managed):
    config, _engine, client, _ = managed
    claims = _claims(login(client, config, "front"))
    assert 29 * 60 <= claims["exp"] - time.time() <= 30 * 60
    assert abs(claims["auth_time"] - time.time()) < 60


def test_refresh_gives_a_new_token_for_the_same_session(managed):
    config, _engine, client, _ = managed
    first = login(client, config, "front")
    response = client.post("/api/auth/refresh", headers=first)
    assert response.status_code == 200 and response.json()["expires_in"] == 1800
    renewed = _bearer(response.json()["access_token"])
    assert _claims(renewed)["auth_time"] == _claims(first)["auth_time"]
    assert _claims(renewed)["jti"] != _claims(first)["jti"]
    assert client.get("/api/auth/me", headers=renewed).json()["username"] == "front"


def test_renewal_never_extends_a_session_past_twelve_hours(managed):
    config, _engine, client, _ = managed
    started = int(time.time()) - 12 * 3600 + 600          # ten minutes left
    old = _reissued(login(client, config, "front"), auth_time=started)
    renewed = _bearer(client.post("/api/auth/refresh", headers=old).json()["access_token"])
    assert _claims(renewed)["exp"] <= started + 12 * 3600


def test_a_session_older_than_twelve_hours_is_refused_even_with_a_valid_token(managed):
    config, _engine, client, _ = managed
    stale = _reissued(login(client, config, "front"), auth_time=int(time.time()) - 12 * 3600 - 1)
    for call in (lambda: client.get("/api/auth/me", headers=stale),
                 lambda: client.post("/api/auth/refresh", headers=stale)):
        response = call()
        assert response.status_code == 401 and "12 heures" in response.json()["detail"]


def test_a_seven_day_token_issued_before_the_change_ends_twelve_hours_after_its_issue(managed):
    config, _engine, client, _ = managed
    headers = login(client, config, "front")
    week = int(time.time()) + 7 * 86400
    recent = _reissued(headers, auth_time=None, exp=week)
    assert client.get("/api/auth/me", headers=recent).status_code == 200
    old = _reissued(headers, auth_time=None, exp=week, iat=int(time.time()) - 13 * 3600)
    assert client.get("/api/auth/me", headers=old).status_code == 401


def test_a_revoked_session_cannot_be_renewed(managed):
    config, _engine, client, _ = managed
    headers = login(client, config, "front")
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.post("/api/auth/refresh", headers=headers).status_code == 401


def test_a_user_who_must_change_a_temporary_password_keeps_the_session_alive(managed):
    config, _engine, client, _ = managed
    admin = login(client, config, "superuser")
    entity = client.get("/api/auth/me", headers=admin).json()["entity_id"]
    created = client.post("/api/admin/users", headers=admin, json={
        "username": "temp-user", "email": "temp@example.test", "entity_id": entity,
        "password": "Temporary-Password-2026"})
    assert created.status_code == 201
    token = client.post("/api/auth/login", data={"username": "temp-user",
                                                 "password": "Temporary-Password-2026"}).json()["access_token"]
    assert client.post("/api/auth/refresh", headers=_bearer(token)).status_code == 200
