"""Dated Athena volatility uses only qualified closes known by that session."""

from datetime import date, timedelta
from math import exp, sqrt

import pytest

from backend.app.api import structured_indices


VOLATILITY = "/api/v1/structured-indices/athena/realized-volatility"


@pytest.fixture
def client(authenticated_client):
    authenticated_client.app.include_router(structured_indices.router)
    return authenticated_client


def _sample():
    start = date(2024, 1, 1)
    closes = [{"day": start.isoformat(), "close": 100.}]
    for index in range(1, 255):
        daily_return = .01 if index <= 252 else (.03 if index == 253 else .30)
        closes.append({"day": (start + timedelta(days=index)).isoformat(),
                       "close": closes[-1]["close"] * exp(daily_return)})
    return closes


def test_uses_252_returns_until_each_requested_date(client):
    closes = _sample()
    dates = [point["day"] for point in closes[252:254]]
    response = client.post(VOLATILITY, json={"closes": closes, "sessions": dates})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["method"] == "RMS_LOG_RETURNS"
    assert result["window_sessions"] == result["annualization"] == 252
    assert [row["day"] for row in result["observations"]] == dates
    assert [row["volatility"] for row in result["observations"]] == pytest.approx([
        .01 * sqrt(252), sqrt(251 * .01**2 + .03**2),
    ])


def test_rejects_dates_without_closes_or_warmup(client):
    closes = _sample()
    for day, error in [(closes[251]["day"], "253 clôtures"), ("2024-12-30", "absente")]:
        response = client.post(VOLATILITY, json={"closes": closes, "sessions": [day]})
        assert response.status_code == 422, response.text
        assert error in response.json()["detail"]


def test_rejects_unordered_or_repeated_dates_and_unauthenticated_requests(client):
    closes = _sample()
    dates = [point["day"] for point in closes[252:254]]
    for bad_closes, bad_dates in [([*closes, closes[-1]], dates), (closes, dates[::-1])]:
        response = client.post(VOLATILITY, json={"closes": bad_closes, "sessions": bad_dates})
        assert response.status_code == 422, response.text
    response = client.post(VOLATILITY, headers={"Authorization": "Bearer invalid"},
                           json={"closes": closes, "sessions": dates})
    assert response.status_code == 401, response.text
