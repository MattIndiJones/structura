from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.db.models import Alert, Deal, User
from backend.app.services import lifecycle_alerts


def _session_with_deal():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(username="alertes", email="alertes@example.test", password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    deal = Deal(reference="DEAL-ALERT-1", user_id=user.id, status="actif")
    session.add(deal)
    session.commit()
    session.refresh(deal)
    return session, user, deal


def test_deux_observations_de_rappel_creent_deux_alertes(monkeypatch):
    session, user, deal = _session_with_deal()
    observation = {"date": "2026-09-20"}

    monkeypatch.setattr(deals_api, "refresh_deal_core", lambda *_args, **_kwargs: {})

    def watchlist(*_args, **_kwargs):
        return {
            "days_to_next": 9,
            "next_event": {"date": observation["date"], "label": "Observation"},
            "barriers": [{
                "name": "M_AC_BAR", "kind": "autocall", "observable": "WOF",
                "level": 1.0, "gap_pts": 2.0,
            }],
        }

    monkeypatch.setattr(deals_api, "build_watchlist_row", watchlist)
    lifecycle_alerts.configure_lifecycle_handlers(
        deals_api.refresh_deal_core, deals_api.build_watchlist_row)

    assert lifecycle_alerts.refresh_book(session, user.id)["alerts_created"] == 1
    assert lifecycle_alerts.refresh_book(session, user.id)["alerts_created"] == 0
    observation["date"] = "2027-09-20"
    assert lifecycle_alerts.refresh_book(session, user.id)["alerts_created"] == 1

    alerts = session.exec(select(Alert).where(Alert.deal_id == deal.id)).all()
    assert len(alerts) == 2
    assert {a.dedup_key.rsplit(":", 1)[-1] for a in alerts} == {
        "2026-09-20", "2027-09-20",
    }


def test_le_ki_garde_une_cle_terminale_independante_des_observations(monkeypatch):
    session, user, deal = _session_with_deal()
    observation = {"date": "2026-09-20"}
    monkeypatch.setattr(deals_api, "refresh_deal_core", lambda *_args, **_kwargs: {})

    def watchlist(*_args, **_kwargs):
        return {
            "days_to_next": 9,
            "next_event": {"date": observation["date"], "label": "Observation"},
            "barriers": [{
                "name": "M_KI_BAR", "kind": "ki", "observable": "WOF_MIN",
                "level": 0.6, "gap_pts": -2.0,
            }],
        }

    monkeypatch.setattr(deals_api, "build_watchlist_row", watchlist)
    lifecycle_alerts.configure_lifecycle_handlers(
        deals_api.refresh_deal_core, deals_api.build_watchlist_row)
    assert lifecycle_alerts.refresh_book(session, user.id)["alerts_created"] == 1
    observation["date"] = "2027-09-20"
    assert lifecycle_alerts.refresh_book(session, user.id)["alerts_created"] == 0

    alerts = session.exec(select(Alert).where(Alert.deal_id == deal.id)).all()
    assert len(alerts) == 1
    assert alerts[0].dedup_key == f"deal:{deal.id}:barrier:M_KI_BAR"
