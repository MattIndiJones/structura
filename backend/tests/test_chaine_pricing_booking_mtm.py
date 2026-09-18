"""Invariant bout en bout du lot 3 : un deal est le pricing identifié."""
import json
import hashlib
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.api.deals import (
    DealCreate, _ai_script_provenance, _apply_pricing_receipt,
)
from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.db.models import Counterparty, Deal, DealEvent


SCRIPT = "AT MATURITY\n  PAY 1\n"


def test_pricing_booking_mtm_au_strike_conservent_le_meme_produit(monkeypatch):
    strike = date.today()
    maturity = strike + timedelta(days=365)
    payment = maturity + timedelta(days=5)
    tenor = (maturity - strike).days / 365.25
    request = PricingRequest(
        script=SCRIPT,
        underlyings=[{
            "name": "AAA", "ticker": "AAA", "ccy": "EUR",
            "sigma": 0.20, "q": 0.01,
        }],
        corr_matrix=[[1.0]], r=0.03, T=tenor, N=2000,
        funding_spread=0.015, barrier_monitoring="continuous",
        strike_date=strike, value_date=strike, maturity_date=maturity,
        payment_date=payment, settlement_ccy="EUR",
    )
    priced = price_endpoint(request)
    body = DealCreate(
        contrepartie="Banque", nominal=1_000_000,
        fair_value=priced.price * 100, price_traded=priced.price * 100,
        trade_date=strike.isoformat(), strike_date=strike.isoformat(),
        value_date=strike.isoformat(), maturity_date=maturity.isoformat(),
        payment_date=payment.isoformat(), T=tenor, devise="EUR",
        underlyings=[{"name": "AAA", "ticker": "AAA", "ccy": "EUR"}],
        observation_times=[tenor], script_snapshot=SCRIPT,
        pricing_receipt=priced.pricing_receipt,
        market_snapshot={"ai_script_provenance": {
            "generation_id": "gen-1", "checks_status": "warning",
            "warnings_acknowledged": True, "adopted_script_text": SCRIPT,
            "script_sha256": hashlib.sha256(SCRIPT.encode()).hexdigest(),
        }},
    )
    ai_provenance = _ai_script_provenance(body)
    _apply_pricing_receipt(body, ai_provenance)
    assert body.market_snapshot["ai_script_provenance"]["generation_id"] == "gen-1"

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Counterparty(name="Banque", active=True))
        session.commit()
        booked = deals_api.book_deal(
            body, SimpleNamespace(id=1, entity_id=None), session)
        deal = session.get(Deal, booked["id"])
        assert deal.product_id is not None
        strike_event = next(
            event for event in session.exec(
                select(DealEvent).where(DealEvent.deal_id == deal.id)).all()
            if event.t_years == 0.0)
        strike_event.spots_json = json.dumps({"AAA": 100.0})
        strike_event.source = "fixture"
        strike_event.status = "observé"
        session.add(strike_event)
        session.commit()
        monkeypatch.setattr(deals_api, "load_hist_prices", lambda *_args, **_kwargs: {
            "dates": [strike.isoformat()], "prices": {"AAA": [100.0]},
        })

        mtm, _ctx = deals_api._mtm_core(deal, session, n_paths=2000, asof=strike)

    assert mtm["mtm"] == priced.price
    assert mtm["market_used"]["funding_spread"] == 1.5
    assert mtm["market_used"]["barrier_monitoring"] == "continuous"
