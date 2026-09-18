from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.api import portfolios as portfolios_api
from backend.app.db import database as database_module
from backend.app.db.models import Deal, DealPortfolioMembership, Entity, Portfolio, User


def test_portfolio_count_uses_the_live_risk_perimeter():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        portfolio = Portfolio(name="Book EUR", user_id=1, is_default=True)
        session.add(portfolio)
        session.flush()
        session.add(Deal(reference="LIVE-1", user_id=1, portfolio_id=portfolio.id, status="actif"))
        session.add(Deal(reference="MATURED-1", user_id=1, portfolio_id=portfolio.id, status="echu"))
        session.commit()

        rows = portfolios_api.list_portfolios(SimpleNamespace(id=1), session)

    assert rows[0]["deal_count"] == 1


def test_legacy_pointer_is_backfilled_once_and_default_lock_is_retired(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        portfolio = Portfolio(name="Ancien défaut", user_id=1, is_default=True)
        session.add(portfolio)
        session.flush()
        session.add(Deal(
            reference="LEGACY-PF", user_id=1, portfolio_id=portfolio.id,
            status="actif",
        ))
        session.commit()

    monkeypatch.setattr(database_module, "engine", engine)
    database_module._backfill_portfolio_memberships()
    database_module._backfill_portfolio_memberships()

    with Session(engine) as session:
        memberships = session.exec(select(DealPortfolioMembership)).all()
        portfolio = session.exec(select(Portfolio)).one()
        assert len(memberships) == 1
        assert portfolio.is_default is False


def test_admin_lists_every_owners_portfolios_while_user_stays_scoped():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Portfolio(name="Admin book", user_id=1, is_default=True))
        session.add(Portfolio(name="Test book", user_id=2, is_default=True))
        session.commit()

        admin_rows = portfolios_api.list_portfolios(SimpleNamespace(id=1, role="admin"), session)
        user_rows = portfolios_api.list_portfolios(SimpleNamespace(id=2, role="user"), session)

    assert {row["user_id"] for row in admin_rows} == {1, 2}
    assert {row["user_id"] for row in user_rows} == {2}


def test_admin_assigns_a_deal_only_to_a_portfolio_of_its_owner():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        admin_book = Portfolio(name="Admin book", user_id=1, is_default=True)
        owner_book = Portfolio(name="Test book", user_id=2, is_default=True)
        session.add(admin_book)
        session.add(owner_book)
        session.flush()
        deal = Deal(reference="USER-2-DEAL", user_id=2, portfolio_id=owner_book.id, status="actif")
        session.add(deal)
        session.commit()
        session.refresh(deal)
        deal_id = deal.id
        owner_book_id = owner_book.id

        admin = SimpleNamespace(id=1, role="admin")
        with pytest.raises(HTTPException) as exc:
            deals_api.assign_deal_portfolio(
                deal.id,
                deals_api.DealPortfolioAssign(portfolio_id=admin_book.id),
                admin,
                session,
            )
        assert exc.value.status_code == 422

        result = deals_api.assign_deal_portfolio(
            deal.id,
            deals_api.DealPortfolioAssign(portfolio_id=owner_book.id),
            admin,
            session,
        )

    assert result == {"id": deal_id, "portfolio_ids": [owner_book_id]}


def test_same_deal_can_belong_to_multiple_portfolios():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = Portfolio(name="Mandat", user_id=2)
        second = Portfolio(name="Desk", user_id=2)
        session.add(first)
        session.add(second)
        session.flush()
        first_id, second_id = first.id, second.id
        deal = Deal(reference="MULTI-PF", user_id=2, status="actif")
        session.add(deal)
        session.commit()
        deal_id = deal.id

        result = deals_api.set_deal_portfolios(
            deal.id,
            deals_api.DealPortfoliosSet(portfolio_ids=[first_id, second_id]),
            SimpleNamespace(id=1, role="admin"),
            session,
        )
        memberships = session.exec(select(DealPortfolioMembership)).all()

    assert result["portfolio_ids"] == sorted([first_id, second_id])
    assert {(m.deal_id, m.portfolio_id) for m in memberships} == {
        (deal_id, first_id), (deal_id, second_id),
    }


def test_admin_deletes_portfolio_without_deleting_deal_or_other_membership():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        deleted = Portfolio(name="Vue temporaire", user_id=2, is_default=True)
        kept = Portfolio(name="Vue conservée", user_id=2)
        session.add(deleted)
        session.add(kept)
        session.flush()
        deal = Deal(reference="KEEP-ME", user_id=2, status="actif")
        session.add(deal)
        session.flush()
        session.add(DealPortfolioMembership(deal_id=deal.id, portfolio_id=deleted.id))
        session.add(DealPortfolioMembership(deal_id=deal.id, portfolio_id=kept.id))
        session.commit()

        portfolios_api.delete_portfolio(
            deleted.id, SimpleNamespace(id=1, role="admin"), session)

        assert session.get(Deal, deal.id) is not None
        remaining = session.exec(select(DealPortfolioMembership)).all()
        assert [(m.deal_id, m.portfolio_id) for m in remaining] == [(deal.id, kept.id)]


def test_admin_creates_a_portfolio_for_the_selected_account():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        entity = Entity(name="Structura France")
        session.add(entity)
        session.flush()
        owner = User(
            username="test",
            email="test@example.test",
            password_hash="unused",
            entity_id=entity.id,
        )
        session.add(owner)
        session.commit()
        session.refresh(owner)

        created = portfolios_api.create_portfolio(
            portfolios_api.PortfolioCreate(name="  Mandat test  ", user_id=owner.id),
            SimpleNamespace(id=99, role="admin"),
            session,
        )

        assert created["name"] == "Mandat test"
        assert created["user_id"] == owner.id
        assert created["owner_username"] == "test"
        assert created["owner_entity_name"] == "Structura France"
