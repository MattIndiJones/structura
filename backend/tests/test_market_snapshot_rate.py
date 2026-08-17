"""Le taux d'un snapshot de booking est une valeur, pas une présence.

Régression de l'audit du 07/08/2026 (P1-01) : le motif
``(market.get("r", 3.0) or 3.0) / 100.0`` était écrit à cinq endroits, dont le
replay **officiel** du cycle de vie. ``0 or 3.0`` valant ``3.0`` en Python, un
deal booké à taux nul était actualisé à 3 % — soit ~3 points de nominal par année
résiduelle, sans que rien à l'écran ne le signale.

Les tests unitaires ci-dessous verrouillent la sémantique du lecteur partagé ; le
test de bout en bout prouve le comportement sur un zéro-coupon, où la valeur
attendue est fermée (df = exp(-rT)).
"""
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals as deals_api
from backend.app.core.market_snapshot import (
    DEFAULT_RATE_PCT, snapshot_rate, snapshot_rate_is_default,
)
from backend.app.db.models import Deal, DealEvent, Portfolio, User

USER = SimpleNamespace(id=1, entity_id=None, role="user")


# ── Sémantique du lecteur ─────────────────────────────────────────────

@pytest.mark.parametrize("stored, expected", [
    (0, 0.0),          # le cas du bug : zéro est une valeur
    (0.0, 0.0),
    (3.0, 0.03),
    (2.5, 0.025),
    (-0.5, -0.005),    # taux négatif : légitime, ne doit pas être écrasé
])
def test_snapshot_rate_honours_the_booked_value(stored, expected):
    assert snapshot_rate({"r": stored}) == pytest.approx(expected)


def test_snapshot_rate_falls_back_only_when_the_key_is_absent():
    assert snapshot_rate({}) == pytest.approx(DEFAULT_RATE_PCT / 100.0)
    assert snapshot_rate(None) == pytest.approx(DEFAULT_RATE_PCT / 100.0)
    # Une clé présente à None est un snapshot incomplet, pas un taux nul.
    assert snapshot_rate({"r": None}) == pytest.approx(DEFAULT_RATE_PCT / 100.0)


def test_snapshot_rate_is_default_distinguishes_a_substitution():
    assert snapshot_rate_is_default({}) is True
    assert snapshot_rate_is_default({"r": None}) is True
    # Un zéro booké n'est pas une substitution — c'est tout l'objet du correctif.
    assert snapshot_rate_is_default({"r": 0}) is False
    assert snapshot_rate_is_default({"r": 3.0}) is False


def test_snapshot_rate_refuses_an_unreadable_value():
    with pytest.raises(ValueError, match="illisible"):
        snapshot_rate({"r": "trois pour cent"})


# ── Le motif ne doit pas réapparaître ─────────────────────────────────

def test_no_call_site_reintroduces_the_or_fallback():
    """Garde-fou : c'est un idiome, il se recopie. Il ne doit plus exister."""
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        f"{path.relative_to(root)}:{i}"
        for path in root.rglob("*.py")
        # Le module de remplacement cite l'idiome dans sa docstring pour
        # expliquer pourquoi il existe — c'est la seule occurrence légitime.
        if path.name != "market_snapshot.py"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r'get\(\s*["\']r["\']\s*,\s*[\d.]+\s*\)\s*or\b', line)
    ]
    assert not offenders, (
        "Le repli `get(\"r\", x) or x` avale un taux nul — utilisez "
        f"core.market_snapshot.snapshot_rate. Sites : {offenders}"
    )


# ── Bout en bout : un ZC booké à 0 % vaut le pair ─────────────────────

def _zero_coupon_deal(session: Session, r_pct: float) -> Deal:
    today = date.today()
    strike = today - timedelta(days=365)
    maturity = today + timedelta(days=365)
    market = {
        "r": r_pct,
        "model": "constant",
        "underlyings": [{"name": "AAA", "ticker": "AAA", "ccy": "EUR",
                         "spot": 100.0, "sigma": 0.20, "q": 0.0}],
        "corrMatrix": [[1.0]],
        "user_params": {}, "constats": {},
        "barrierMonitoring": "weekly", "antithetic": True,
    }
    deal = Deal(
        reference=f"ZC-{r_pct}", user_id=1, portfolio_id=1,
        script_snapshot="AT MATURITY\n  PAY 1",
        sens="vente", contrepartie="BNP", devise="EUR", nominal=1_000_000.0,
        fair_value=95.0, price_traded=96.0,
        trade_date=strike.isoformat(), strike_date=strike.isoformat(),
        value_date=strike.isoformat(), maturity_date=maturity.isoformat(),
        payment_date=(maturity + timedelta(days=5)).isoformat(),
        T=(maturity - strike).days / 365.25,
        underlyings_json=json.dumps([{"name": "AAA", "ticker": "AAA", "ccy": "EUR"}]),
        market_snapshot_json=json.dumps(market),
        status="actif",
    )
    session.add(deal)
    session.flush()
    session.add(DealEvent(deal_id=deal.id, event_index=0,
                          event_date=strike.isoformat(), t_years=0.0,
                          spots_json=json.dumps({"AAA": 100.0}),
                          source="manuel", status="observé", label="Strike"))
    session.add(DealEvent(deal_id=deal.id, event_index=1,
                          event_date=maturity.isoformat(), t_years=deal.T,
                          spots_json="{}", source="pending", status="futur",
                          label="Maturité"))
    session.commit()
    session.refresh(deal)
    return deal


@pytest.fixture
def session_with_flat_history(monkeypatch):
    """Historique plat : le spot ne bouge jamais, donc seul le taux
    d'actualisation peut expliquer un écart de prix."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(id=1, username="u", email="u@x", password_hash="x"))
    session.add(Portfolio(id=1, name="P", user_id=1, is_default=True))
    session.commit()

    today = date.today()
    dates, d = [], today - timedelta(days=400)
    while d <= today:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    payload = {"dates": dates, "prices": {"AAA": [100.0] * len(dates)}}
    monkeypatch.setattr(deals_api, "load_hist_prices",
                        lambda tickers, start, end=None: payload)
    return session


def test_zero_rate_deal_is_not_discounted(session_with_flat_history):
    session = session_with_flat_history
    deal = _zero_coupon_deal(session, 0.0)

    payload, _ctx = deals_api._mtm_core(deal, session, n_paths=2000)

    assert payload["market_used"]["r"] == 0.0
    assert payload["market_used"]["r_is_default"] is False
    # Un ZC non actualisé vaut le pair, quel que soit le nombre de chemins.
    assert payload["mtm"] == pytest.approx(1.0, abs=1e-6)


def test_three_percent_deal_still_discounts(session_with_flat_history):
    session = session_with_flat_history
    deal = _zero_coupon_deal(session, 3.0)

    payload, _ctx = deals_api._mtm_core(deal, session, n_paths=2000)

    assert payload["market_used"]["r"] == 3.0
    assert payload["market_used"]["r_is_default"] is False
    expected = math.exp(-0.03 * payload["T_remaining"])
    assert payload["mtm"] == pytest.approx(expected, abs=1e-4)


def test_zero_and_three_percent_no_longer_price_identically(session_with_flat_history):
    """Le symptôme exact de la sonde d'audit : les deux MtM étaient égaux."""
    session = session_with_flat_history
    at_zero, _ = deals_api._mtm_core(
        _zero_coupon_deal(session, 0.0), session, n_paths=2000)
    at_three, _ = deals_api._mtm_core(
        _zero_coupon_deal(session, 3.0), session, n_paths=2000)

    assert at_zero["mtm"] > at_three["mtm"]
    assert at_zero["mtm"] - at_three["mtm"] == pytest.approx(0.0295, abs=2e-3)


def test_legacy_snapshot_without_rate_is_flagged(session_with_flat_history):
    session = session_with_flat_history
    deal = _zero_coupon_deal(session, 3.0)
    market = json.loads(deal.market_snapshot_json)
    del market["r"]
    deal.market_snapshot_json = json.dumps(market)
    session.add(deal)
    session.commit()
    session.refresh(deal)

    payload, _ctx = deals_api._mtm_core(deal, session, n_paths=2000)

    assert payload["market_used"]["r"] == pytest.approx(DEFAULT_RATE_PCT)
    # Le repli reste possible, mais il se voit.
    assert payload["market_used"]["r_is_default"] is True
