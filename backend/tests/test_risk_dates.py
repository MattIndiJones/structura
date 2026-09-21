import json
from datetime import date, datetime
from types import SimpleNamespace

from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import portfolios as portfolios_api
from backend.app.db.models import Deal, DealEvent, ValuationRun


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _greeks(delta: float, valuation_date: str) -> dict:
    return {
        "valuation_date": valuation_date,
        "computed_at": "2026-09-19T12:00:00",
        "per_underlying": {"Action": {"delta": delta}},
        "scalar": {},
        "corr_pairs": {},
        "vega_scope": {"type": "total"},
    }


def test_risk_uses_the_snapshot_for_the_selected_date_and_grays_outside_life():
    session = _session()
    try:
        live = Deal(
            reference="DATED", user_id=1, status="callé", sens="vente",
            trade_date="2026-01-10", maturity_date="2027-01-10",
            nominal=1_000_000, devise="EUR",
            underlyings_json=json.dumps([{"name": "Action", "ticker": "ACT"}]),
            greeks_json=json.dumps(_greeks(0.90, "2026-05-01")),
            greeks_computed_at=datetime(2026, 9, 19, 12),
        )
        session.add(live)
        session.flush()
        session.add(DealEvent(
            deal_id=live.id, event_index=1, event_date="2026-06-15",
            status="callé",
        ))
        session.add(ValuationRun(
            deal_id=live.id, user_id=1, run_type="GREEKS",
            context_hash="dated-run", result_json=json.dumps(_greeks(0.25, "2026-03-01")),
            created_at=datetime(2026, 9, 18, 12),
        ))
        session.commit()

        march = portfolios_api.risk_global(
            SimpleNamespace(id=1, role="user"), session, date(2026, 3, 1))
        june = portfolios_api.risk_global(
            SimpleNamespace(id=1, role="user"), session, date(2026, 6, 15))

        assert march["per_underlying"]["ACT"]["delta_eur"] == 250_000
        assert march["valuation_date"] == "2026-03-01"
        assert june["deals_included"] == []
        assert june["deals_outside_scope"][0]["reference"] == "DATED"
        assert "Terminé le 2026-06-15" in june["deals_outside_scope"][0]["reason"]
    finally:
        session.close()


def test_risk_does_not_reuse_greeks_from_another_date():
    session = _session()
    try:
        deal = Deal(
            reference="WRONG-DATE", user_id=1, status="actif", sens="vente",
            trade_date="2026-01-01", maturity_date="2027-01-01",
            nominal=100_000, devise="EUR", underlyings_json="[]",
            greeks_json=json.dumps(_greeks(0.50, "2026-09-18")),
            greeks_computed_at=datetime(2026, 9, 18, 12),
        )
        session.add(deal)
        session.commit()

        result = portfolios_api.risk_global(
            SimpleNamespace(id=1, role="user"), session, date(2026, 9, 19))

        assert result["deals_included"] == []
        assert result["deals_missing_greeks"][0]["reference"] == "WRONG-DATE"
    finally:
        session.close()
