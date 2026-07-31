"""Admin data browser — editable_fields allowlist (core/admin_registry.py).
Offline, in-memory SQLite, calling the registry functions directly (same
pattern as test_rfq.py)."""
import json
from datetime import date

import pytest
from sqlmodel import SQLModel, Session, create_engine, select
from fastapi import HTTPException

from backend.app.core import admin_registry
from backend.app.db.models import AdminAuditLog, Deal, RfqRequest


def _make_session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _add_deal(s: Session) -> Deal:
    deal = Deal(
        reference="TEST-001", user_id=1, contrepartie="BNP Paribas",
        devise="EUR", nominal=1_000_000.0, fair_value=97.5, price_traded=97.5,
        trade_date=date.today().isoformat(), strike_date=date.today().isoformat(),
        value_date=date.today().isoformat(),
        maturity_date=date.today().isoformat(), T=3.0,
        script_snapshot="AT MATURITY\n  PAY 1",
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1"}]),
        market_snapshot_json=json.dumps({"r": 3.0}),
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    return deal


def test_get_row_includes_editable_fields_missing_from_the_summary_columns():
    s = _make_session()
    deal = _add_deal(s)

    detail = admin_registry.get_row("deals", deal.id, s)

    # Only fields safe to correct without rebuilding lifecycle are exposed.
    assert detail["price_traded"] == 97.5
    assert detail["contrepartie"] == "BNP Paribas"
    assert "trade_date" not in detail


def test_deals_table_accepts_a_whitelisted_correction():
    s = _make_session()
    deal = _add_deal(s)

    result = admin_registry.update_row("deals", deal.id, {"contrepartie": "Goldman Sachs", "nominal": 2_000_000.0}, s)

    assert result["contrepartie"] == "Goldman Sachs"
    assert result["nominal"] == 2_000_000.0
    refreshed = s.get(Deal, deal.id)
    assert refreshed.contrepartie == "Goldman Sachs"
    assert refreshed.nominal == 2_000_000.0
    audit = s.exec(select(AdminAuditLog)).one()
    assert json.loads(audit.before_json)["nominal"] == 1_000_000.0
    assert json.loads(audit.after_json)["nominal"] == 2_000_000.0


def test_deals_table_rejects_a_non_whitelisted_field():
    s = _make_session()
    deal = _add_deal(s)
    original_snapshot = deal.script_snapshot

    with pytest.raises(HTTPException) as exc:
        admin_registry.update_row("deals", deal.id, {"script_snapshot": "HACKED"}, s)
    assert exc.value.status_code == 422

    refreshed = s.get(Deal, deal.id)
    assert refreshed.script_snapshot == original_snapshot


@pytest.mark.parametrize("patch", [
    {"nominal": -5.0},
    {"price_traded": 0.0},
    {"contrepartie": "   "},
    {"devise": "EURO"},
    {"maturity_date": "2020-01-01"},
    {"status": "incoherent"},
])
def test_admin_refuse_les_corrections_qui_cassent_le_deal(patch):
    s = _make_session()
    deal = _add_deal(s)
    with pytest.raises(HTTPException) as exc:
        admin_registry.update_row("deals", deal.id, patch, s)
    assert exc.value.status_code == 422


def test_a_table_without_editable_fields_is_rejected_entirely():
    s = _make_session()
    rfq = RfqRequest(reference="RFQ-TEST-001", user_id=1, name="test")
    s.add(rfq)
    s.commit()
    s.refresh(rfq)

    with pytest.raises(HTTPException) as exc:
        admin_registry.update_row("rfq_requests", rfq.id, {"name": "renamed"}, s)
    assert exc.value.status_code == 403


def test_update_row_404s_on_missing_record():
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        admin_registry.update_row("deals", 9999, {"contrepartie": "X"}, s)
    assert exc.value.status_code == 404


def test_registry_meta_exposes_editable_fields_for_deals_only():
    meta = {m["key"]: m["editable_fields"] for m in admin_registry.registry_meta()}
    assert set(meta["deals"]) == {
        "contrepartie", "devise", "product_type", "nominal", "price_traded",
    }
    assert meta["rfq_requests"] == {}
    assert meta["scripts"] == {}


# ── Suppression en lot (sélection multiple de l'écran Données) ──────────

def test_bulk_delete_removes_every_selected_row():
    s = _make_session()
    ids = []
    for i in range(3):
        d = _add_deal(s)
        d.reference = f"TEST-BULK-{i}"
        s.add(d)
        s.commit()
        ids.append(d.id)

    report = admin_registry.delete_rows("deals", ids, s)

    assert sorted(report["deleted"]) == sorted(ids)
    assert report["blocked"] == []
    assert all(s.get(Deal, i) is None for i in ids)


def test_a_protected_row_does_not_sink_the_batch():
    """Sélectionner cinquante deals à purger et voir le troisième faire échouer
    le lot — en laissant deviner lesquels sont passés — serait pire que pas de
    lot du tout. La ligne protégée est refusée, nommée, et les autres passent."""
    s = _make_session()
    free_before = _add_deal(s)
    free_before.reference = "TEST-LIBRE-1"
    s.add(free_before)

    rfq = RfqRequest(reference="RFQ-BLOQUANTE", user_id=1,
                     script_snapshot="AT MATURITY\n  PAY 1")
    s.add(rfq)
    s.flush()
    protected = _add_deal(s)
    protected.reference = "TEST-BLOQUE"
    protected.rfq_id = rfq.id           # une RFQ dont un deal est booké
    s.add(protected)

    free_after = _add_deal(s)
    free_after.reference = "TEST-LIBRE-2"
    s.add(free_after)
    s.commit()

    # La RFQ est refusée tant que le deal qui en est issu existe…
    report = admin_registry.delete_rows("rfq_requests", [rfq.id], s)
    assert report["deleted"] == []
    assert len(report["blocked"]) == 1
    assert report["blocked"][0]["id"] == rfq.id
    assert "deals" in report["blocked"][0]["reason"]
    assert s.get(RfqRequest, rfq.id) is not None

    # …et le lot de deals passe entièrement, blocage de la RFQ ou non.
    report = admin_registry.delete_rows("deals", [free_before.id, protected.id, free_after.id], s)
    assert sorted(report["deleted"]) == sorted([free_before.id, protected.id, free_after.id])

    # Le deal parti, la RFQ redevient supprimable.
    assert admin_registry.delete_rows("rfq_requests", [rfq.id], s)["deleted"] == [rfq.id]


def test_bulk_delete_keeps_going_after_a_blocked_row():
    s = _make_session()
    blocked_rfq = RfqRequest(reference="RFQ-A", user_id=1, script_snapshot="AT MATURITY\n  PAY 1")
    free_rfq = RfqRequest(reference="RFQ-B", user_id=1, script_snapshot="AT MATURITY\n  PAY 1")
    s.add(blocked_rfq)
    s.add(free_rfq)
    s.flush()
    d = _add_deal(s)
    d.rfq_id = blocked_rfq.id
    s.add(d)
    s.commit()

    report = admin_registry.delete_rows("rfq_requests", [blocked_rfq.id, free_rfq.id], s)

    assert report["deleted"] == [free_rfq.id]          # la suivante est bien passée
    assert [b["id"] for b in report["blocked"]] == [blocked_rfq.id]
    assert s.get(RfqRequest, blocked_rfq.id) is not None
    assert s.get(RfqRequest, free_rfq.id) is None


def test_bulk_delete_reports_a_missing_row_instead_of_crashing():
    s = _make_session()
    d = _add_deal(s)
    report = admin_registry.delete_rows("deals", [d.id, 999999], s)
    assert report["deleted"] == [d.id]
    assert report["blocked"][0]["id"] == 999999
