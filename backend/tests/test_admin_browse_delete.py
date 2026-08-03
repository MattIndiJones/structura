"""Deleting a deal or an RFQ from the admin data browser.

Every one of these failed in production with a bare "Erreur suppression":
the registry declared only part of what points at a deal, the schema contains
a cycle SQLAlchemy cannot order DELETEs around, and the resulting
IntegrityError escaped as a 500 with no detail for the UI to show.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import event, text
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core import admin_registry
from backend.app.db.models import (
    Alert, Deal, DealEvent, Entity, LifecycleProposal, OfficialFixingVersion,
    RfqQuote, RfqRequest, TradeAmendmentRequest, User,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")     # as db/database.py does
        cur.close()

    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    # Foreign keys are enforced here exactly as in production, so the owning
    # rows have to exist before anything can reference them.
    session.add(Entity(name="Demo"))
    session.commit()
    for name in ("owner", "ops"):
        session.add(User(username=name, email=f"{name}@x", password_hash="x",
                         role="user", entity_id=1))
    session.commit()
    return session


def _deal(session: Session, reference: str = "TEST-DEL-001") -> Deal:
    deal = Deal(
        reference=reference, user_id=1, entity_id=1, status="actif",
        notional=1_000_000.0, script_text="AT MATURITY\n  PAY 1\n",
        params_json="{}", underlyings_json="[]", corr_json="[[1.0]]",
        trade_date=date.today().isoformat(),
        maturity_date=(date.today() + timedelta(days=365)).isoformat(),
        price=100.0, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    session.add(deal)
    session.commit()
    session.refresh(deal)
    return deal


def _fixing_version(deal: Deal, event_id: int) -> OfficialFixingVersion:
    return OfficialFixingVersion(
        deal_id=deal.id, deal_event_id=event_id, version=1, provider="UBS",
        source_type="MANUAL", external_reference="REF-1",
        observed_at=datetime.utcnow(), venue="XSWX", calendar="CH",
        timezone="Europe/Zurich", evidence_sha256="a" * 64,
        record_sha256="b" * 64, capture_reason="test", entered_by=2,
    )


def test_deleting_a_bare_deal_works():
    """The simplest case, and it failed too: three lifecycle events and
    nothing else. deal_events points at official_fixing_versions, which points
    back at deal_events, and a cycle stops SQLAlchemy ordering the DELETEs —
    it emitted `DELETE FROM deals` first, before its own children."""
    s = _session()
    deal = _deal(s)
    for _ in range(3):
        s.add(DealEvent(deal_id=deal.id))
    s.commit()

    admin_registry.delete_row("deals", deal.id, s)

    assert s.exec(select(Deal)).all() == []
    assert s.exec(select(DealEvent)).all() == []


def test_deleting_a_deal_carrying_its_whole_lifecycle():
    """Alerts, proposals, amendment requests and fixing versions were absent
    from the registry, so any deal that had actually lived was undeletable."""
    s = _session()
    deal = _deal(s)
    ev = DealEvent(deal_id=deal.id)
    s.add(ev)
    s.commit()
    s.refresh(ev)

    fv = _fixing_version(deal, ev.id)
    s.add(fv)
    s.commit()
    s.refresh(fv)
    # The forward half of the cycle — what production rows actually carry.
    ev.current_fixing_version_id = fv.id
    s.add(ev)
    s.add(Alert(user_id=1, deal_id=deal.id))
    s.add(LifecycleProposal(deal_id=deal.id, event_id=ev.id,
                            dedup_key="k1", proposed_outcome="AUTOCALL"))
    s.add(TradeAmendmentRequest(deal_id=deal.id, requested_by=1,
                                field_name="nominal", reason="test"))
    s.commit()

    admin_registry.delete_row("deals", deal.id, s)

    for model in (Deal, DealEvent, OfficialFixingVersion, Alert,
                  LifecycleProposal, TradeAmendmentRequest):
        assert s.exec(select(model)).all() == [], model.__name__
    assert s.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_deleting_an_rfq_with_a_selected_quote():
    """`rfq_requests.selected_quote_id` still pointed at the quote being
    deleted: DELETE FROM rfq_quotes failed on the foreign key. Any tender that
    had retained a price — i.e. any tender that mattered — was undeletable."""
    s = _session()
    rfq = RfqRequest(reference="RFQ-TEST-001", name="Test", user_id=1,
                     status="retenue")
    s.add(rfq)
    s.commit()
    s.refresh(rfq)
    q = RfqQuote(rfq_id=rfq.id, provider="UBS", price=98.5)
    s.add(q)
    s.commit()
    s.refresh(q)
    rfq.selected_quote_id = q.id
    s.add(rfq)
    s.commit()

    admin_registry.delete_row("rfq_requests", rfq.id, s)

    assert s.exec(select(RfqRequest)).all() == []
    assert s.exec(select(RfqQuote)).all() == []


def test_a_booked_tender_is_still_protected():
    """The best-execution trail must survive an administrative purge — this
    blocker is the one thing that legitimately refuses."""
    s = _session()
    rfq = RfqRequest(reference="RFQ-TEST-002", name="Test", user_id=1,
                     status="clos")
    s.add(rfq)
    s.commit()
    s.refresh(rfq)
    deal = _deal(s, "TEST-DEL-002")
    deal.rfq_id = rfq.id
    s.add(deal)
    s.commit()

    with pytest.raises(HTTPException) as exc:
        admin_registry.delete_row("rfq_requests", rfq.id, s)
    assert exc.value.status_code == 409


def test_batch_delete_reports_each_row():
    """A refusal must not sink the batch, and the caller must be told which
    rows stayed and why."""
    s = _session()
    free = _deal(s, "TEST-DEL-003")
    rfq = RfqRequest(reference="RFQ-TEST-003", name="Test", user_id=1)
    s.add(rfq)
    s.commit()
    s.refresh(rfq)
    held = _deal(s, "TEST-DEL-004")
    s.commit()

    out = admin_registry.delete_rows("deals", [free.id, held.id], s)
    assert sorted(out["deleted"]) == sorted([free.id, held.id])
    assert out["blocked"] == []


def test_an_undeclared_relation_gives_an_actionable_message():
    """Belt and braces: whatever the registry forgets next must surface as a
    409 naming the constraint, not a 500 the UI renders as 'Erreur
    suppression'."""
    s = _session()
    deal = _deal(s, "TEST-DEL-005")
    ev = DealEvent(deal_id=deal.id)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    s.add(_fixing_version(deal, ev.id))
    s.commit()

    # Simulate a forgotten dependency by removing it from the cascade list.
    cfg = admin_registry.REGISTRY["deals"]
    original = cfg["children"]
    cfg["children"] = [(DealEvent, "deal_id")]
    try:
        with pytest.raises(HTTPException) as exc:
            admin_registry.delete_row("deals", deal.id, s)
        assert exc.value.status_code == 409
        assert "référencé" in exc.value.detail
    finally:
        cfg["children"] = original
