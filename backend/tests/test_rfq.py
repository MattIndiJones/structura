"""RFQ module — offline, in-memory SQLite, endpoint functions called
directly (same pattern as test_portfolio_pnl.py). Covers three fixes/
features from the 2026-07-29 session:
  1. quoted_at timezone round-trip (13:05 redisplaying as 11:05 for a
     UTC+2 user) and quote sort order (previously created_at only, never
     moved by editing the actual response time).
  2. Last look: toggling it on a quote spawns a linked child quote: nested
     right after its parent regardless of timing, can't be un-toggled once
     it has an answer.
  3. Selected/"retenue" quote on the RFQ, including cleanup when the
     selected quote is deleted.
"""
import json
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import admin as admin_api
from backend.app.api import deals as deals_api
from backend.app.api import rfq as rfq_api
from backend.app.api.auth import receipt_signing_secret
from backend.app.core.schemas import PricingRequest
from backend.app.core.valuation_context import build_pricing_receipt
from backend.app.db.models import (
    AuditEvent, Client, ClientMandate, Counterparty, Deal, Opportunity,
    ProductRecord, RfqProvider, RfqProviderContact, RfqQuote, RfqRequest,
)
from backend.app.core.references import next_reference
from backend.app.core.rfq_controls import booking_terms_differences, pricing_input_hash
from backend.app.services.product_receipts import signed_receipt
from backend.app.services.product_repository import load_product

USER = SimpleNamespace(id=1, entity_id=1)


def _make_session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _rfq_params(**over):
    strike = date.today()
    maturity = strike + timedelta(days=1096)
    params = {
        "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}],
        "notional": 1_000_000.0,
        "currency": "EUR",
        "strike_date": strike.isoformat(),
        "value_date": strike.isoformat(),
        "maturity_date": maturity.isoformat(),
        "payment_date": (strike + timedelta(days=1101)).isoformat(),
        "T": 3.0,
    }
    params.update(over)
    return params


def _new_rfq(s: Session):
    body = rfq_api.RfqCreate(
        name="Autocall test", script_snapshot="AT MATURITY\n  PAY 1",
        params=_rfq_params())
    return rfq_api.create_rfq(body, USER, s)


def _add_quote(s: Session, rfq_id: int, provider: str = "BNP Paribas"):
    return rfq_api.add_quote(rfq_id, rfq_api.QuoteCreate(provider=provider), USER, s)


def test_rfq_provider_contacts_are_admin_managed_and_offered_on_rfq():
    s = _make_session()
    provider = admin_api.create_rfq_provider(
        admin_api.RfqProviderCreate(label="BNP Paribas"), USER, s)
    first = admin_api.create_rfq_provider_contact(
        provider["id"], admin_api.RfqContactCreate(
            name="Virginie", email="virginie@example.com"), USER, s)
    assert [c["name"] for c in rfq_api.list_providers(USER, s)[0]["contacts"]] == ["Virginie"]
    with pytest.raises(HTTPException) as duplicate:
        admin_api.create_rfq_provider_contact(
            provider["id"], admin_api.RfqContactCreate(name="virginie"), USER, s)
    assert duplicate.value.status_code == 409
    admin_api.update_rfq_provider_contact(
        provider["id"], first["id"], admin_api.RfqContactUpdate(active=False), USER, s)
    assert rfq_api.list_providers(USER, s)[0]["contacts"] == []
    assert s.get(RfqProviderContact, first["id"]).name == "Virginie"


def test_price_is_a_valid_selection_reason():
    assert rfq_api.RfqUpdate(selection_reason_code="price").selection_reason_code == "price"


def test_rfq_creates_an_internal_product_before_its_own_record():
    s = _make_session()

    rfq = _new_rfq(s)

    assert rfq["product_id"] is not None
    record = s.get(ProductRecord, rfq["product_id"])
    assert record.listed is False
    product = load_product(s, record.id)
    assert product.terms_version == rfq["product_terms_version"] == 1
    assert [item.to_dict()["id"] for item in product.rfqs] == [rfq["id"]]


def test_rfq_contract_change_creates_a_product_terms_version():
    s = _make_session()
    rfq = _new_rfq(s)
    changed_params = dict(rfq["params"])
    changed_params["T"] = 2.0
    changed_params["maturity_date"] = (
        date.today() + timedelta(days=730)).isoformat()
    changed_params["payment_date"] = (
        date.today() + timedelta(days=735)).isoformat()

    updated = rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(params=changed_params), USER, s)

    product = load_product(s, rfq["product_id"])
    assert updated["product_terms_version"] == 2
    assert product.terms_version == 2
    assert product.terms.T == 2.0
    assert product.terms.maturity_date.isoformat() == changed_params["maturity_date"]


def test_deleted_rfq_and_quote_ids_are_never_reused_by_sqlite():
    s = _make_session()
    first = _new_rfq(s)
    first_quote = _add_quote(s, first["id"])
    rfq_api.delete_rfq(first["id"], USER, s)

    second = _new_rfq(s)
    second_quote = _add_quote(s, second["id"])

    assert second["id"] > first["id"]
    assert second_quote["id"] > first_quote["id"]


def test_to_trade_calendar_is_rejected_before_the_rfq_is_created():
    s = _make_session()
    strike = date.today() + timedelta(days=14)
    end = strike + timedelta(days=365)
    with pytest.raises(HTTPException) as exc:
        rfq_api.create_rfq(rfq_api.RfqCreate(
            name="Calendrier incomplet",
            kind="to_trade",
            script_snapshot="CONSTAT() OBS\nAT OBS:\n  PAY 1",
            params={
                "underlyings": [{"name": "UL", "ticker": "UL.PA", "ccy": "EUR"}],
                "notional": 1_000_000,
                "currency": "EUR",
                "strike_date": strike.isoformat(),
                "value_date": (strike - timedelta(days=2)).isoformat(),
                "payment_date": (end + timedelta(days=3)).isoformat(),
                "T": 1.0,
                "constats": {"OBS": {
                    "start_date": strike.isoformat(),
                    "end_date": end.isoformat(),
                    "frequency": "3M",
                    # roll_date deliberately absent
                }},
            },
        ), USER, s)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CONTRACT_CALENDAR_INVALID"
    assert s.exec(select(RfqRequest)).all() == []


def test_multi_underlying_rfq_requires_a_complete_correlation_matrix():
    s = _make_session()
    strike = date.today()
    end = strike + timedelta(days=365)
    params = {
        "underlyings": [
            {"name": "LVMH", "ticker": "MC.PA", "ccy": "EUR"},
            {"name": "DAX", "ticker": "^GDAXI", "ccy": "EUR"},
        ],
        "notional": 1_000_000, "currency": "EUR", "T": 1.0,
        "strike_date": strike.isoformat(),
        "value_date": strike.isoformat(),
        "payment_date": (end + timedelta(days=3)).isoformat(),
        "constats": {"OBS": {
            "start_date": strike.isoformat(), "end_date": end.isoformat(),
            "roll_date": (strike + timedelta(days=90)).isoformat(),
            "frequency": "3M",
        }},
    }
    with pytest.raises(HTTPException) as exc:
        rfq_api.create_rfq(rfq_api.RfqCreate(
            name="Worst-of incomplet", kind="to_trade",
            script_snapshot="CONSTAT() OBS\nAT OBS:\n  PAY WOF",
            params=params,
        ), USER, s)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CORRELATION_MATRIX_INVALID"
    assert s.exec(select(RfqRequest)).all() == []


def test_multi_underlying_repricing_cannot_replace_the_matrix_with_an_incomplete_one():
    s = _make_session()
    params = {
        "underlyings": [
            {"name": "LVMH", "ticker": "MC.PA", "ccy": "EUR"},
            {"name": "DAX", "ticker": "^GDAXI", "ccy": "EUR"},
        ],
        "corr_matrix": [[1.0, 0.45], [0.45, 1.0]],
        **{key: value for key, value in _rfq_params().items()
           if key != "underlyings"},
    }
    rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
        name="Worst-of", script_snapshot="AT MATURITY\n  PAY WOF", params=params,
    ), USER, s)

    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(
            rfq["id"], rfq_api.RfqUpdate(pricing_params={"corr_matrix": [[1.0]]}),
            USER, s)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CORRELATION_MATRIX_INVALID"
    stored = json.loads(s.get(RfqRequest, rfq["id"]).params_json)
    assert stored["corr_matrix"] == [[1.0, 0.45], [0.45, 1.0]]


# ── 1. Timezone round-trip + sort order ────────────────────────────────

def test_quoted_at_round_trips_without_timezone_shift():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])

    # Frontend always sends new Date(value).toISOString() — Z-suffixed UTC.
    sent = "2026-07-29T11:05:00.000Z"  # 13:05 local (UTC+2) round-tripped to UTC
    updated = rfq_api.update_quote(
        rfq["id"], q["id"], rfq_api.QuoteUpdate(quoted_at=sent), USER, s)

    # The API must hand back an unambiguous UTC string — no naive
    # offset-less value that a browser could reinterpret as local time.
    assert updated["quoted_at"].endswith("Z") or "+00:00" in updated["quoted_at"]
    parsed = datetime.fromisoformat(updated["quoted_at"].replace("Z", "+00:00"))
    assert parsed == datetime(2026, 7, 29, 11, 5, tzinfo=timezone.utc)

    # And the value actually stored is naive-UTC (not, say, shifted by a
    # local offset at write time) — reading the raw column confirms the
    # SQLite round-trip preserved the right numbers.
    raw = s.get(RfqQuote, q["id"])
    assert raw.quoted_at == datetime(2026, 7, 29, 11, 5)


def test_quotes_sorted_by_response_time_not_add_order():
    s = _make_session()
    rfq = _new_rfq(s)
    # Added in this order: first, second, third — but they respond out of
    # order, and one never responds at all.
    first = _add_quote(s, rfq["id"], "First-added")
    second = _add_quote(s, rfq["id"], "Second-added")
    third = _add_quote(s, rfq["id"], "Never-responds")

    rfq_api.update_quote(rfq["id"], first["id"],
                          rfq_api.QuoteUpdate(quoted_at="2026-07-29T12:00:00.000Z"), USER, s)
    rfq_api.update_quote(rfq["id"], second["id"],
                          rfq_api.QuoteUpdate(quoted_at="2026-07-29T09:00:00.000Z"), USER, s)
    # third: no quoted_at at all — must sort to the end, not by created_at.

    ordered = rfq_api._get_quotes(rfq["id"], s)
    assert [q.provider for q in ordered] == ["Second-added", "First-added", "Never-responds"]


# ── 2. Last look ────────────────────────────────────────────────────────

def test_last_look_creates_nested_child_quote():
    s = _make_session()
    rfq = _new_rfq(s)
    original = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], original["id"],
                          rfq_api.QuoteUpdate(quoted_at="2026-07-29T09:00:00.000Z", price=98.0),
                          USER, s)

    updated = rfq_api.update_quote(
        rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    assert updated["last_look"] is True

    ordered = rfq_api._get_quotes(rfq["id"], s)
    assert len(ordered) == 2
    child = ordered[1]
    assert child.parent_quote_id == original["id"]
    assert child.provider == "BNP Paribas"
    assert child.price is None and child.quoted_at is None

    # The child sorts immediately after its parent even though it has no
    # quoted_at of its own (it would otherwise sort to "unanswered" last).
    assert ordered[0].id == original["id"]


def test_last_look_cannot_be_reverted_once_answered():
    s = _make_session()
    rfq = _new_rfq(s)
    original = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(price=100.0), USER, s)
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    child_id = rfq_api._get_quotes(rfq["id"], s)[1].id

    # Not yet answered — reverting is allowed and removes the child.
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=False), USER, s)
    assert len(rfq_api._get_quotes(rfq["id"], s)) == 1

    # Re-enable, then answer it — now reverting must be rejected.
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    new_child_id = rfq_api._get_quotes(rfq["id"], s)[1].id
    rfq_api.update_quote(rfq["id"], new_child_id, rfq_api.QuoteUpdate(price=99.5), USER, s)

    try:
        rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=False), USER, s)
        assert False, "expected HTTPException"
    except Exception as e:
        assert getattr(e, "status_code", None) == 422
    assert len(rfq_api._get_quotes(rfq["id"], s)) == 2  # child untouched


# ── 3. Selected ("retenue") quote ──────────────────────────────────────

def test_selecting_an_unpriced_quote_is_rejected():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])

    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(
            rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    assert exc.value.status_code == 422
    assert "sans prix" in exc.value.detail


def test_selecting_an_expired_quote_is_rejected():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(
        rfq["id"], q["id"], rfq_api.QuoteUpdate(
            price=98.0, quoted_at="2025-12-31T10:00:00.000Z",
            valid_until="2026-01-01T10:00:00.000Z"), USER, s)

    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(
            rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    assert exc.value.status_code == 422
    assert "expiré" in exc.value.detail


def test_selecting_a_quote_from_another_rfq_is_rejected():
    s = _make_session()
    rfq_a = _new_rfq(s)
    rfq_b = _new_rfq(s)
    q_b = _add_quote(s, rfq_b["id"])

    try:
        rfq_api.update_rfq(rfq_a["id"], rfq_api.RfqUpdate(selected_quote_id=q_b["id"]), USER, s)
        assert False, "expected HTTPException"
    except Exception as e:
        assert getattr(e, "status_code", None) == 404


def test_deleting_the_selected_quote_clears_the_selection():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)

    rfq_api.delete_quote(rfq["id"], q["id"], USER, s)

    refreshed = rfq_api.get_rfq(rfq["id"], USER, s)
    assert refreshed["selected_quote_id"] is None


def test_changing_the_selected_quote_does_not_reuse_the_previous_reason():
    s = _make_session()
    rfq = _new_rfq(s)
    first = _add_quote(s, rfq["id"], "BNP Paribas")
    second = _add_quote(s, rfq["id"], "Marex")
    rfq_api.update_quote(
        rfq["id"], first["id"], rfq_api.QuoteUpdate(price=99.0), USER, s)
    rfq_api.update_quote(
        rfq["id"], second["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(
            selected_quote_id=first["id"],
            selection_reason_code="documentation"), USER, s)

    changed = rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(selected_quote_id=second["id"]), USER, s)
    assert changed["selected_quote_id"] == second["id"]
    assert changed["selection_reason_code"] is None
    assert changed["selection_reason_note"] is None


def test_deleting_a_quote_cascades_to_its_last_look_child():
    s = _make_session()
    rfq = _new_rfq(s)
    original = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(price=100.0), USER, s)
    rfq_api.update_quote(rfq["id"], original["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    assert len(rfq_api._get_quotes(rfq["id"], s)) == 2

    rfq_api.delete_quote(rfq["id"], original["id"], USER, s)
    assert rfq_api._get_quotes(rfq["id"], s) == []


# ── 4. RFQ kind: indicatif vs to_trade ──────────────────────────────────

def test_rfq_defaults_to_indicatif_kind():
    s = _make_session()
    rfq = _new_rfq(s)
    assert rfq["kind"] == "indicatif"


def test_to_trade_rfq_requires_an_expert_calendar_script():
    s = _make_session()
    # Normal-mode script (hardcoded AT dates, no CONSTAT) — rejected even
    # with a script_id, since script_id alone doesn't guarantee Expert mode.
    try:
        rfq_api.create_rfq(
            rfq_api.RfqCreate(name="Autocall précis", kind="to_trade", script_id=7,
                               script_snapshot="AT 1, 2, 3\n  PAY 1"),
            USER, s)
        assert False, "expected HTTPException"
    except Exception as e:
        assert getattr(e, "status_code", None) == 422

    # Expert-mode script with its resolved calendar is allowed even with no
    # script_id, e.g. sourced from an already-booked deal rather than the
    # script library. A CONSTAT declaration alone is not executable.
    start = date.today() + timedelta(days=7)
    end = start + timedelta(days=365)
    rfq = rfq_api.create_rfq(
        rfq_api.RfqCreate(name="Autocall précis", kind="to_trade",
                           script_snapshot="CONSTAT() Cal\nAT Cal:\n  PAY 0\nAT MATURITY\n  PAY 1",
                           params={**_rfq_params(T=1.0), "constats": {"CAL": {
                               "start_date": start.isoformat(),
                               "end_date": end.isoformat(),
                               "roll_date": end.isoformat(),
                               "frequency": "3M",
                           }}}),
        USER, s)
    assert rfq["kind"] == "to_trade"


# ── 5. RFQ → Deal booking link ──────────────────────────────────────────

def test_booking_from_an_rfq_links_deal_and_closes_the_rfq():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)

    body = deals_api.DealCreate(
        contrepartie="BNP Paribas", nominal=1_000_000.0, fair_value=97.9,
        price_traded=98.0, trade_date=date.today().isoformat(),
        strike_date=date.today().isoformat(), value_date=date.today().isoformat(),
        maturity_date=(date.today() + timedelta(days=1096)).isoformat(),
        # Reglement final cinq jours apres la derniere constatation.
        payment_date=(date.today() + timedelta(days=1101)).isoformat(), T=3.0,
        underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "s0_abs": 100.0}],
        observation_times=[1.0, 2.0, 3.0],
        script_snapshot="AT MATURITY\n  PAY 1",
        rfq_id=rfq["id"],
    )
    deal = _book_deal(body, USER, s)

    assert deal["rfq_id"] == rfq["id"]
    closed_rfq = s.get(RfqRequest, rfq["id"])
    assert closed_rfq.status == "clos"


def test_multi_underlying_rfq_reaches_the_deal_without_losing_market_inputs():
    s = _make_session()
    strike = date.today()
    maturity = strike + timedelta(days=365)
    payment = maturity + timedelta(days=3)
    script = "CONSTAT() OBS\nAT OBS:\n  PAY WOF"
    rfq_underlyings = [
        {"name": "LVMH", "ticker": "MC.PA", "ccy": "EUR", "sigma": 0.21, "q": 0.018},
        {"name": "DAX", "ticker": "^GDAXI", "ccy": "EUR", "sigma": 0.27, "q": 0.031},
    ]
    correlation = [[1.0, 0.45], [0.45, 1.0]]
    constats = {"OBS": {
        "start_date": strike.isoformat(), "end_date": maturity.isoformat(),
        "roll_date": (strike + timedelta(days=90)).isoformat(),
        "frequency": "3M",
    }}
    params = {
        "underlyings": rfq_underlyings, "corr_matrix": correlation,
        "notional": 1_000_000, "currency": "EUR", "T": 1.0,
        "strike_date": strike.isoformat(), "value_date": strike.isoformat(),
        "maturity_date": maturity.isoformat(), "payment_date": payment.isoformat(),
        "constats": constats, "user_params": {}, "r": 0.03, "model": "constant",
    }
    rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
        name="Worst-of LVMH DAX", kind="to_trade",
        script_snapshot=script, params=params,
    ), USER, s)
    quote = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(
        rfq["id"], quote["id"], rfq_api.QuoteUpdate(price=98.2), USER, s)
    rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(selected_quote_id=quote["id"]), USER, s)

    booked_underlyings = [
        {**underlying, "s0_abs": 100.0} for underlying in rfq_underlyings
    ]
    market_underlyings = [
        {**rfq_underlyings[0], "sigma": 21.0, "q": 1.8},
        {**rfq_underlyings[1], "sigma": 27.0, "q": 3.1},
    ]
    deal = _book_deal(_booking_body(
        rfq_id=rfq["id"], script_snapshot=script,
        nominal=1_000_000, devise="EUR", T=1.0,
        strike_date=strike.isoformat(), value_date=strike.isoformat(),
        maturity_date=maturity.isoformat(), payment_date=payment.isoformat(),
        underlyings=booked_underlyings,
        market_snapshot={
            "underlyings": market_underlyings, "corrMatrix": correlation,
            "constats": constats, "user_params": {}, "r": 3.0,
            "model": "constant", "antithetic": True,
        },
        fair_value=97.9, price_traded=98.2,
    ), USER, s)

    assert [u["ticker"] for u in deal["underlyings"]] == ["MC.PA", "^GDAXI"]
    assert [u["name"] for u in deal["market_snapshot"]["underlyings"]] == ["LVMH", "DAX"]
    assert [u["sigma"] for u in deal["market_snapshot"]["underlyings"]] == [21.0, 27.0]
    assert [u["q"] for u in deal["market_snapshot"]["underlyings"]] == pytest.approx([1.8, 3.1])
    assert deal["market_snapshot"]["corrMatrix"] == correlation
    assert deal["rfq_provenance"]["product_terms"]["underlyings"] == [
        {"name": "LVMH", "ticker": "MC.PA", "ccy": "EUR"},
        {"name": "DAX", "ticker": "^GDAXI", "ccy": "EUR"},
    ]
    assert s.get(RfqRequest, rfq["id"]).status == "clos"


def test_booking_never_reuses_a_deal_id_retained_by_the_audit_trail():
    s = _make_session()
    s.add(AuditEvent(
        action="OLD_BOOKING", object_type="DEAL", object_id=80,
        result="SUCCESS"))
    s.commit()

    deal = _book_deal(_booking_body(), USER, s)

    assert deal["id"] > 80


@pytest.mark.parametrize("family, requested_family", [
    ("Phoenix", None),
    ("Autocall", "Autocall"),
])
def test_booking_uses_the_rfq_commercial_and_legal_context_as_authority(
    family, requested_family,
):
    s = _make_session()
    client = Client(name="Banque privée A", entity_id=1, data_origin="native")
    s.add(client); s.flush()
    mandate = ClientMandate(
        entity_id=1, client_id=client.id, mandate_type="fund",
        name="Fonds Rendement", status="active", data_origin="native",
        created_by_user_id=USER.id,
    )
    s.add(mandate); s.flush()
    opportunity = Opportunity(
        reference="OPP-20260901-001", entity_id=1, owner_user_id=USER.id,
        client_id=client.id, mandate_id=mandate.id, title="Phoenix 3Y",
        transaction_format="EMTN", instrument_family="Note",
        payoff_family=family, data_origin="native",
    )
    s.add(opportunity); s.commit(); s.refresh(opportunity)

    rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
        name="AO Client", opportunity_id=opportunity.id,
        script_snapshot="AT MATURITY\n  PAY 1",
        params=_rfq_params(),
    ), USER, s)
    quote = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(
        rfq["id"], quote["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(selected_quote_id=quote["id"]), USER, s)

    if family == "Autocall":
        # Pre-catalogue rows used Athena as the family; the new booking form
        # proposes Autocall. Both describe the same payoff family.
        source = s.get(RfqRequest, rfq["id"])
        source.payoff_family = "ATHENA"
        s.add(source)
        s.commit()

    deal = _book_deal(_booking_body(
        rfq_id=rfq["id"], payoff_family=requested_family), USER, s)
    assert deal["client_id"] == client.id
    assert deal["mandate_id"] == mandate.id
    assert deal["opportunity_id"] == opportunity.id
    assert deal["transaction_format"] == "EMTN"
    assert deal["instrument_family"] == "Note"
    assert deal["payoff_family"] == family
    assert deal["client_provenance"]["mandate"]["name"] == "Fonds Rendement"
    assert s.get(Opportunity, opportunity.id).status == "partially_won"



def _booking_body(**over):
    base = dict(
        contrepartie="BNP Paribas", nominal=1_000_000.0, fair_value=97.9,
        price_traded=98.0, trade_date=date.today().isoformat(),
        strike_date=date.today().isoformat(), value_date=date.today().isoformat(),
        maturity_date=(date.today() + timedelta(days=1096)).isoformat(),
        # Reglement final cinq jours apres la derniere constatation.
        payment_date=(date.today() + timedelta(days=1101)).isoformat(), T=3.0,
        underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "s0_abs": 100.0}],
        observation_times=[1.0, 2.0, 3.0],
        script_snapshot="AT MATURITY\n  PAY 1",
    )
    base.update(over)
    return deals_api.DealCreate(**base)


def _pricing_receipt_for_booking(body):
    """Issue the same signed evidence a successful /api/price call returns."""
    market = body.market_snapshot or {}
    if isinstance(market.get("pricing_input"), dict):
        payload = dict(market["pricing_input"])
    else:
        display_underlyings = market.get("underlyings")
        underlyings = []
        for source in display_underlyings or body.underlyings:
            item = {
                "name": source.get("name") or "Underlying",
                "ticker": source.get("ticker") or "",
                "ccy": source.get("ccy") or body.devise,
            }
            if display_underlyings:
                if source.get("sigma") is not None:
                    item["sigma"] = float(source["sigma"]) / 100.0
                if source.get("q") is not None:
                    item["q"] = float(source["q"]) / 100.0
            underlyings.append(item)
        count = len(underlyings)
        corr = market.get("corrMatrix") or market.get("corr_matrix")
        if corr is None:
            corr = [[1.0 if i == j else 0.0 for j in range(count)]
                    for i in range(count)]
        raw_rate = market.get("r", 3.0)
        payload = {
            "script": body.script_snapshot,
            "underlyings": underlyings,
            "corr_matrix": corr,
            "r": float(raw_rate) / 100.0,
            "T": body.T,
            "N": 2000,
            "model": market.get("model") or "constant",
            "antithetic": market.get("antithetic", True),
            "user_params": market.get("user_params") or {},
            "constats": market.get("constats") or {},
            "strike_date": body.strike_date,
            "value_date": body.value_date,
            "maturity_date": body.maturity_date,
            "payment_date": body.payment_date or None,
            "settlement_ccy": body.devise,
        }
    request = PricingRequest.model_validate(payload)
    return signed_receipt(
        build_pricing_receipt(request, body.fair_value / 100.0),
        secret=receipt_signing_secret(),
        result={"price": body.fair_value / 100.0},
    )


def _book_deal(body, current, s, fermete="FIRM"):
    """Upgrade legacy success fixtures to the now-explicit execution contract.

    Tests that exercise missing/foreign/unselected RFQs remain untouched: only
    a retained, owned quote is qualified here. Production code has no fallback.
    """
    if body.pricing_receipt is None:
        body.pricing_receipt = _pricing_receipt_for_booking(body)
    if body.rfq_id:
        rfq = s.get(RfqRequest, body.rfq_id)
        selected = s.get(RfqQuote, rfq.selected_quote_id) \
            if rfq and rfq.user_id == current.id and rfq.selected_quote_id else None
        if rfq and selected and rfq.status == "retenue":
            params = json.loads(rfq.params_json or "{}")
            if not params.get("underlyings"):
                params = {
                    "underlyings": body.underlyings,
                    "user_params": (body.market_snapshot or {}).get("user_params", {}),
                    "constats": (body.market_snapshot or {}).get("constats", {}),
                    "notional": body.nominal, "currency": body.devise,
                    "strike_date": body.strike_date, "value_date": body.value_date,
                    "payment_date": body.payment_date,
                    "T": body.T, "model": "constant", "r": 0.03,
                }
                rfq.params_json = json.dumps(params)
            rfq.kind = "to_trade"
            rfq.model_price = rfq.model_price or body.fair_value
            rfq.model_price_at = datetime.utcnow()
            rfq.model_input_hash = pricing_input_hash(rfq.script_snapshot, params)
            selected.firmness = fermete
            selected.valid_until = datetime.utcnow() + timedelta(minutes=30)
            selected.status = "recu"
            cpty = s.exec(select(Counterparty).where(
                Counterparty.name == body.contrepartie)).first()
            if not cpty:
                cpty = Counterparty(name=body.contrepartie, active=True)
                s.add(cpty); s.flush()
            provider = s.exec(select(RfqProvider).where(
                RfqProvider.label == selected.provider)).first()
            if not provider:
                provider = RfqProvider(
                    label=selected.provider, active=True, counterparty_id=cpty.id)
            else:
                provider.counterparty_id = cpty.id
                provider.active = True
            s.add(provider); s.add(selected); s.add(rfq); s.commit()
    return deals_api.book_deal(body, current, s)


# ── 6. Sens (notre côté) et normalisation de l'écart ────────────────────

def test_rfq_defaults_to_achat():
    """Les fournisseurs cotent un produit qu'on leur achète — c'est le sens
    normal du module, et il décide quelle réponse gagne l'AO."""
    s = _make_session()
    assert _new_rfq(s)["sens"] == "achat"


def test_edge_is_positive_when_a_provider_quotes_below_model_on_a_buy():
    # On achète : coter SOUS le prix modèle nous est favorable.
    assert rfq_api._edge_bps(price=97.0, model=100.0, sens="achat") == 300.0
    assert rfq_api._edge_bps(price=103.0, model=100.0, sens="achat") == -300.0


def test_edge_flips_sign_on_a_sell():
    # On vend : c'est coter AU-DESSUS qui nous est favorable.
    assert rfq_api._edge_bps(price=103.0, model=100.0, sens="vente") == 300.0
    assert rfq_api._edge_bps(price=97.0, model=100.0, sens="vente") == -300.0


def test_edge_is_none_without_a_model_price():
    assert rfq_api._edge_bps(price=98.0, model=None, sens="achat") is None
    assert rfq_api._edge_bps(price=None, model=100.0, sens="achat") is None


def test_history_reports_edge_alongside_the_raw_spread():
    """Sur un AO d'achat, une cotation sous le modèle donne un spread brut
    négatif mais un edge positif — c'est l'edge que la vue Analyse agrège,
    sinon un bon achat et une bonne vente s'annulent en moyenne."""
    s = _make_session()
    rfq = _new_rfq(s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(model_price=100.0), USER, s)
    q = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=97.0), USER, s)

    row = rfq_api.rfq_history(USER, s)[0]
    assert row["sens"] == "achat"
    assert row["spread_bps"] == -300.0
    assert row["edge_bps"] == 300.0


def test_booking_rejects_an_unknown_rfq_id():
    """The RFQ link is a best-execution trail — a dangling id must not be
    silently persisted on the deal (previous behaviour: stored as-is, only
    the RFQ close was skipped)."""
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(rfq_id=9999), USER, s)
    assert exc.value.status_code == 404


def test_booking_rejects_another_users_rfq():
    s = _make_session()
    other_rfq = rfq_api.create_rfq(
        rfq_api.RfqCreate(
            name="RFQ d'un autre desk", script_snapshot="AT MATURITY\n  PAY 1",
            params=_rfq_params()),
        SimpleNamespace(id=99, entity_id=1), s)

    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(rfq_id=other_rfq["id"]), USER, s)
    assert exc.value.status_code == 404
    # …and the foreign RFQ is left untouched, not closed by someone else's book.
    assert s.get(RfqRequest, other_rfq["id"]).status == "draft"


# ── 7. Workflow de statuts déduit du déroulé de l'AO ────────────────────

def test_status_follows_the_tender_from_draft_to_retenue():
    """« Envoyée » et « Cotée » n'étaient jamais posés par personne : une RFQ
    avec cinq cotations en main affichait « Brouillon » puis sautait
    directement à « Retenue »."""
    s = _make_session()
    rfq = _new_rfq(s)
    assert rfq["status"] == "draft"

    q = _add_quote(s, rfq["id"])
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "envoye"

    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "quote"

    updated = rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    assert updated["status"] == "retenue"


def test_deselecting_a_quote_takes_the_rfq_back_to_cotee():
    """Le trou d'origine : désélectionner remettait selected_quote_id à null
    mais laissait « Retenue » — une RFQ retenue sans rien de retenu."""
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)

    back = rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=None), USER, s)
    assert back["selected_quote_id"] is None
    assert back["status"] == "quote"


def test_deleting_the_selected_quote_takes_the_rfq_back_too():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)

    rfq_api.delete_quote(rfq["id"], q["id"], USER, s)
    # Plus aucune cotation : retour au tout début, pas « Retenue » ni « Cotée ».
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "draft"


def test_clearing_a_price_takes_the_rfq_back_to_envoyee():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=None), USER, s)
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "envoye"


def test_sans_suite_is_terminal_until_reopened():
    """La majorité des AO n'aboutit pas : « sans suite » est le seul statut
    posé à la main, et il ne doit pas être effacé par une cotation qui
    arrive après coup."""
    s = _make_session()
    rfq = _new_rfq(s)
    _add_quote(s, rfq["id"])

    marked = rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(status="sans_suite"), USER, s)
    assert marked["status"] == "sans_suite"

    q2 = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(rfq["id"], q2["id"], rfq_api.QuoteUpdate(price=99.0), USER, s)
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "sans_suite"

    reopened = rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(status="auto"), USER, s)
    assert reopened["status"] == "quote"   # rendu à la déduction, pas à « Brouillon »


def test_a_booked_rfq_never_falls_back():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "clos"

    # Désélectionner après booking ne « rouvre » pas la piste d'audit — depuis
    # l'audit du 30/07 la mutation est refusée d'entrée (§ 15), au lieu d'être
    # simplement sans effet sur le statut.
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=None), USER, s)
    assert exc.value.status_code == 409
    assert rfq_api.get_rfq(rfq["id"], USER, s)["status"] == "clos"


def test_status_cannot_be_posed_by_hand_beyond_sans_suite():
    s = _make_session()
    rfq = _new_rfq(s)
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(status="retenue"), USER, s)
    assert exc.value.status_code == 422


# ── 8. Références uniques (point 4 de l'audit) ──────────────────────────

def test_reference_numbering_survives_a_deletion():
    """Numéroter par comptage rendait un numéro réutilisable : créer 001 et
    002, supprimer 001, recréer → 002 en double, alors que la référence est la
    piste de best execution de l'AO."""
    s = _make_session()
    first = _new_rfq(s)
    second = _new_rfq(s)
    assert first["reference"].endswith("-001")
    assert second["reference"].endswith("-002")

    rfq_api.delete_rfq(first["id"], USER, s)
    third = _new_rfq(s)
    assert third["reference"].endswith("-003")


def test_reference_numbering_ignores_foreign_formats():
    """Une référence saisie à la main ne doit pas faire planter la création
    suivante (suffixe non numérique)."""
    s = _make_session()
    _new_rfq(s)
    hand_written = s.exec(select(RfqRequest)).first()
    hand_written.reference = f"RFQ-{date.today().strftime('%Y%m%d')}-BIS"
    s.add(hand_written)
    s.commit()
    # 001 was already allocated and must never be silently reused, even if an
    # admin later changes the visible reference to a foreign format.
    assert _new_rfq(s)["reference"].endswith("-002")


# ── 9. La RFQ d'un deal booké n'est plus supprimable ────────────────────

def test_deleting_an_rfq_a_deal_was_booked_from_is_refused():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)

    with pytest.raises(HTTPException) as exc:
        rfq_api.delete_rfq(rfq["id"], USER, s)
    assert exc.value.status_code == 409
    assert s.get(RfqRequest, rfq["id"]) is not None


def test_an_rfq_without_a_booked_deal_stays_deletable():
    s = _make_session()
    rfq = _new_rfq(s)
    _add_quote(s, rfq["id"])
    rfq_api.delete_rfq(rfq["id"], USER, s)
    assert s.get(RfqRequest, rfq["id"]) is None


# ── 10. Contrepartie du booking résolue hors du catalogue fournisseurs ──

def _catalog(s, providers, counterparties):
    """providers: [(label, counterparty_name|None)] — le lien explicite.
    counterparties: [(name, active)]."""
    by_name = {}
    for name, active in counterparties:
        c = Counterparty(name=name, active=active)
        s.add(c)
        s.flush()
        by_name[name] = c.id
    for label, linked in providers:
        s.add(RfqProvider(label=label, counterparty_id=by_name.get(linked)))
    s.commit()
    return by_name


def test_provider_with_an_identical_name_needs_no_configuration():
    s = _make_session()
    _catalog(s, [("UBS", None)], [("UBS", True)])
    assert rfq_api._counterparty_by_provider(s) == {"UBS": "UBS"}


def test_diverging_labels_resolve_through_the_explicit_link():
    """« Vontobel (deritrade) » cote, « Vontobel » fait face au trade — sans
    le lien, le libellé du fournisseur partait tel quel dans un <select>
    alimenté par un autre catalogue : champ vide à l'écran, deal quand même
    booké contre une contrepartie hors catalogue."""
    s = _make_session()
    _catalog(s, [("Vontobel (deritrade)", "Vontobel")], [("Vontobel", True)])
    assert rfq_api._counterparty_by_provider(s) == {"Vontobel (deritrade)": "Vontobel"}


def test_unmatched_provider_resolves_to_nothing_rather_than_its_label():
    s = _make_session()
    _catalog(s, [("Leonteq", None)], [("UBS", True)])
    assert rfq_api._counterparty_by_provider(s) == {}


def test_an_inactive_counterparty_is_never_proposed():
    """Le formulaire de booking ne propose que les contreparties actives —
    en préremplir une inactive recréerait exactement le décalage corrigé ici."""
    s = _make_session()
    _catalog(s, [("Barclays", None), ("HSBC", "HSBC")], [("Barclays", False), ("HSBC", False)])
    assert rfq_api._counterparty_by_provider(s) == {}


def test_quote_row_carries_the_resolved_counterparty():
    s = _make_session()
    _catalog(s, [("Vontobel (deritrade)", "Vontobel")], [("Vontobel", True)])
    rfq = _new_rfq(s)
    _add_quote(s, rfq["id"], "Vontobel (deritrade)")
    _add_quote(s, rfq["id"], "Leonteq")

    quotes = rfq_api.get_rfq(rfq["id"], USER, s)["quotes"]
    by_provider = {q["provider"]: q["counterparty"] for q in quotes}
    assert by_provider["Vontobel (deritrade)"] == "Vontobel"
    assert by_provider["Leonteq"] is None


# ── 11. Historique : last look final, hit ratio (point 5) ───────────────

def _answered_last_look(s, rfq_id, parent_id, price):
    rfq_api.update_quote(rfq_id, parent_id, rfq_api.QuoteUpdate(last_look=True), USER, s)
    child = [q for q in rfq_api._get_quotes(rfq_id, s) if q.parent_quote_id == parent_id][0]
    rfq_api.update_quote(rfq_id, child.id, rfq_api.QuoteUpdate(price=price), USER, s)
    return child


def test_an_answered_last_look_supersedes_its_parent():
    """Deux lignes pour un seul fournisseur sur un seul AO : la cotation
    initiale et sa contre-cote. Compter les deux met la banque deux fois et
    tire ses statistiques vers son prix amélioré."""
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.5), USER, s)
    child = _answered_last_look(s, rfq["id"], q["id"], 98.1)

    rows = {r["quote_id"]: r for r in rfq_api.rfq_history(USER, s)}
    assert rows[q["id"]]["superseded"] is True
    assert rows[q["id"]]["is_last_look"] is False
    assert rows[child.id]["superseded"] is False
    assert rows[child.id]["is_last_look"] is True


def test_an_unanswered_last_look_supersedes_nothing():
    """Tant que la contre-cote n'a pas de prix, la cotation initiale reste la
    réponse vivante du fournisseur."""
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.5), USER, s)
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)

    row = next(r for r in rfq_api.rfq_history(USER, s) if r["quote_id"] == q["id"])
    assert row["superseded"] is False


def test_history_flags_the_winner_only_once_the_deal_is_booked():
    """« Retenue » n'est pas un AO gagné : le deal peut encore ne pas se
    faire — c'est exactement ce que le statut « sans suite » enregistre."""
    s = _make_session()
    rfq = _new_rfq(s)
    winner = _add_quote(s, rfq["id"], "UBS")
    loser = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], winner["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(rfq["id"], loser["id"], rfq_api.QuoteUpdate(price=98.6), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=winner["id"]), USER, s)

    assert all(not r["won"] for r in rfq_api.rfq_history(USER, s))

    _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    rows = {r["quote_id"]: r for r in rfq_api.rfq_history(USER, s)}
    assert rows[winner["id"]]["won"] is True
    assert rows[loser["id"]]["won"] is False
    assert rows[loser["id"]]["rfq_status"] == "clos"   # le dénominateur du hit ratio


# ── 12. Garde-fous et provenance au booking (point 6) ───────────────────

def test_booking_from_an_rfq_without_a_retained_quote_is_refused():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)

    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    assert exc.value.status_code == 422
    # …et la RFQ n'a pas été close au passage.
    assert s.get(RfqRequest, rfq["id"]).status == "quote"


def test_booking_freezes_the_competitive_picture_on_the_deal():
    s = _make_session()
    rfq = _new_rfq(s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(model_price=97.9), USER, s)
    winner = _add_quote(s, rfq["id"], "UBS")
    loser = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], winner["id"], rfq_api.QuoteUpdate(price=98.2), USER, s)
    rfq_api.update_quote(rfq["id"], loser["id"], rfq_api.QuoteUpdate(price=98.7), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=winner["id"]), USER, s)

    deal = _book_deal(_booking_body(rfq_id=rfq["id"], price_traded=98.2), USER, s)
    prov = deal["rfq_provenance"]
    assert prov["reference"] == rfq["reference"]
    assert prov["model_price"] == 97.9
    assert prov["retained"]["provider"] == "UBS"
    assert prov["retained"]["price"] == 98.2
    assert prov["retained"]["is_last_look"] is False
    assert prov["retained"]["quoted_at"] is not None
    assert prov["competition"] == [{"provider": "BNP Paribas", "price": 98.7}]
    assert prov["price_traded"] == 98.2

    # La provenance est un instantané, pas une jointure : même si une cotation
    # bouge (l'API le refuse désormais sur un AO booké — § 15 — mais une reprise
    # en base, une migration ou un futur chemin d'écriture le pourrait), la
    # justification du trade ne suit pas.
    s.get(RfqQuote, loser["id"]).price = 1.0
    s.commit()
    reread = deals_api.get_deal(deal["id"], USER, s)
    assert reread["rfq_provenance"]["competition"] == [{"provider": "BNP Paribas", "price": 98.7}]


def test_booking_freezes_selection_reason_and_every_final_response():
    """Le meilleur prix non retenu est un fait explicable, pas une exclusion.

    Les non-réponses et déclins restent aussi dans le cliché : sans eux on ne
    pourrait distinguer « non sollicité » de « sollicité sans prix ».
    """
    s = _make_session()
    rfq = _new_rfq(s)
    retained = _add_quote(s, rfq["id"], "BNP Paribas")
    best = _add_quote(s, rfq["id"], "Marex")
    declined = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(
        rfq["id"], retained["id"], rfq_api.QuoteUpdate(price=99.0), USER, s)
    rfq_api.update_quote(
        rfq["id"], best["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(
        rfq["id"], declined["id"], rfq_api.QuoteUpdate(status="decline"), USER, s)
    rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(
            selected_quote_id=retained["id"],
            selection_reason_code="documentation",
            selection_reason_note="Programme EMTN déjà référencé chez le Client."),
        USER, s)

    deal = _book_deal(_booking_body(rfq_id=rfq["id"], price_traded=99.0), USER, s)
    provenance = deal["rfq_provenance"]

    assert provenance["selection_reason_code"] == "documentation"
    assert provenance["selection_reason_note"].startswith("Programme EMTN")
    assert {row["provider"] for row in provenance["responses"]} == {
        "BNP Paribas", "Marex", "UBS"}
    by_provider = {row["provider"]: row for row in provenance["responses"]}
    assert by_provider["BNP Paribas"]["selected"] is True
    assert by_provider["Marex"]["comparable"] is True
    assert by_provider["UBS"]["status"] == "decline"
    assert by_provider["UBS"]["comparable"] is False


def test_provenance_keeps_only_final_quotes_as_competition():
    """Une cotation remplacée par le last look du même fournisseur n'est pas
    un concurrent de plus."""
    s = _make_session()
    rfq = _new_rfq(s)
    winner = _add_quote(s, rfq["id"], "UBS")
    rival = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], winner["id"], rfq_api.QuoteUpdate(price=98.2), USER, s)
    rfq_api.update_quote(rfq["id"], rival["id"], rfq_api.QuoteUpdate(price=98.9), USER, s)
    _answered_last_look(s, rfq["id"], rival["id"], 98.4)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=winner["id"]), USER, s)

    deal = _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    assert deal["rfq_provenance"]["competition"] == [{"provider": "BNP Paribas", "price": 98.4}]
    responses = deal["rfq_provenance"]["responses"]
    assert next(row for row in responses if row["quote_id"] == rival["id"])["is_final"] is False


def test_a_deal_booked_outside_any_tender_has_no_provenance():
    s = _make_session()
    assert _book_deal(_booking_body(), USER, s)["rfq_provenance"] is None


# ── 13. Un AO ne s'exécute qu'une fois ──────────────────────────────────

def _booked_rfq(s):
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    return rfq, _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)


def test_an_rfq_cannot_be_booked_twice():
    """Deux deals se réclamant de la même mise en concurrence : le hit ratio
    de la banque gagnante compterait double et aucun des deux ne serait LE
    trade issu de cet AO."""
    s = _make_session()
    rfq, first = _booked_rfq(s)

    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    assert exc.value.status_code == 409
    assert first["reference"] in exc.value.detail   # l'erreur nomme le deal existant


def test_a_booked_rfq_points_at_its_deal():
    """Ce que l'écran RFQ utilise pour remplacer « Booker cette réponse » par
    « Voir le booking »."""
    s = _make_session()
    rfq, deal = _booked_rfq(s)

    detail = rfq_api.get_rfq(rfq["id"], USER, s)
    assert detail["booked_deal"] == {"id": deal["id"], "reference": deal["reference"]}
    listed = next(r for r in rfq_api.list_rfqs(USER, s) if r["id"] == rfq["id"])
    assert listed["booked_deal"]["reference"] == deal["reference"]


def test_an_unbooked_rfq_has_no_deal_pointer():
    s = _make_session()
    rfq = _new_rfq(s)
    assert rfq_api.get_rfq(rfq["id"], USER, s)["booked_deal"] is None


# ── 14. Le calendrier d'observation vient du produit, pas du pricing ────

_EXPERT_SCRIPT = """
PARAM COUPON = 8%
CONSTAT() OBSERVATIONS
AT OBSERVATIONS:
  PAY COUPON
AT MATURITY:
  PAY 1
"""

# Les temps d observation se comptent depuis la date de strike des fixtures,
# qui est celle du jour : ils doivent donc se calculer, pas se figer.
_DATES_OBS = ("2027-08-30", "2028-08-30", "2029-08-30")


def _annees_depuis_strike(jour: str) -> float:
    return round((date.fromisoformat(jour) - date.today()).days / 365.25, 4)


_CALENDAR = {"OBSERVATIONS": {
    "start_date": "2026-08-30", "end_date": "2029-08-30",
    "roll_date": "2027-08-30", "frequency": "1Y", "stub": "short_last",
}}


def _expert_booking(**over):
    base = dict(
        script_snapshot=_EXPERT_SCRIPT,
        market_snapshot={"constats": _CALENDAR},
        # Relative au strike, comme T juste en dessous. Figée, elle est devenue
        # antérieure au strike le jour où `date.today()` l'a dépassée, et tout
        # le booking expert a cessé d'être testé — le commentaire de T disait
        # déjà pourquoi : « une constante deviendrait fausse dès le lendemain ».
        value_date=(date.today() + timedelta(days=4)).isoformat(),
        maturity_date="2029-08-30",
        # T se compte depuis la date de strike (celle de _booking_body, soit
        # aujourd hui). Calcule, jamais fige : une constante deviendrait
        # fausse des le lendemain.
        T=_annees_depuis_strike("2029-08-30"),
        observation_times=[],
    )
    base.update(over)
    return _booking_body(**base)


def test_observations_are_derived_without_any_pricing():
    """Booker depuis le prefill d'une RFQ (qui vide volontairement les
    résultats) ne donnait qu'un seul event, le strike : pas de surveillance de
    barrière, pas de MtM résiduel, pas de résolution automatique — en
    silence."""
    s = _make_session()
    deal = _book_deal(_expert_booking(), USER, s)

    times = [e["t_years"] for e in deal["events"]]
    assert times[0] == 0.0                      # strike
    assert len(times) == 4                      # + 3 constatations annuelles
    assert times[1:] == [_annees_depuis_strike(d) for d in _DATES_OBS]


def test_the_contractual_calendar_wins_over_the_simulation_grid():
    """Les temps envoyés par le client sont ceux de la grille hebdomadaire du
    Monte Carlo, pas ceux du calendrier — plusieurs jours d'écart sur chaque
    date d'observation dont le cycle de vie se sert. Les temps attendus se
    comptent depuis la date de strike, origine de la diffusion."""
    s = _make_session()
    deal = _book_deal(
        _expert_booking(observation_times=[0.9808, 2.0, 2.9808]), USER, s)

    assert [e["t_years"] for e in deal["events"]][1:] == [_annees_depuis_strike(d) for d in _DATES_OBS]
    # …et la date affichée redevient celle du contrat.
    assert deal["events"][1]["event_date"] == "2027-08-30"


def test_an_unresolvable_script_is_refused_even_with_client_times():
    """Une grille Monte-Carlo cliente n'est pas un calendrier contractuel."""
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(
            _expert_booking(market_snapshot={}, observation_times=[1.0, 2.0]), USER, s)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "PRODUCT_TERMS_INVALID"
    assert "OBSERVATIONS" in exc.value.detail["message"]


# ── 15. Audit du 2026-07-30 — constats 1, 2 et 3 ────────────────────────

_ATHENA_MATURITY = """PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
CONSTAT() OBSERVATIONS
AT OBSERVATIONS:
  SET C = INDIC(WOF >= M_AC_BAR)
  PAY C * (1 + COUPON)
  IF C = 1:
    STOP
AT MATURITY:
  PAY 1
"""


def test_maturity_lands_on_the_deals_own_maturity_date():
    """Constat 1 — AT_MATURITY n'a pas de date propre : il tombait à
    max(T du formulaire, fin de calendrier). Avec le T par défaut (3.0) et un
    calendrier finissant à 2.9897, le remboursement était simulé 4 jours APRÈS
    la maturité que le deal lui-même déclare, et une 5ᵉ constatation
    apparaissait sur un produit qui en a quatre."""
    s = _make_session()
    deal = _book_deal(_expert_booking(
        script_snapshot=_ATHENA_MATURITY, T=_annees_depuis_strike("2029-08-30"),
        maturity_date="2029-08-30", observation_times=[]), USER, s)

    # 4 lignes : le strike + 3 constatations annuelles. La 5ᵉ, au 2029-09-03,
    # n'existe pas au contrat.
    assert len(deal["events"]) == 4
    assert [e["event_date"] for e in deal["events"][1:]] == [
        "2027-08-30", "2028-08-30", "2029-08-30"]
    assert deal["events"][-1]["label"] == "Maturité"
    assert deal["events"][-1]["event_date"] == "2029-08-30"   # == deal.maturity_date


def test_a_coupon_calendar_shorter_than_the_note_keeps_the_notes_maturity():
    """L'inverse doit rester vrai : 2 ans de coupons sur une note à 3 ans,
    c'est la note qui dit quand elle rembourse, pas le calendrier."""
    s = _make_session()
    short_cal = {"OBSERVATIONS": dict(_CALENDAR["OBSERVATIONS"], end_date="2028-08-30")}
    deal = _book_deal(_expert_booking(
        # 2029-09-03 moins la date de strike, en annees : 1104 / 365,25.
        script_snapshot=_ATHENA_MATURITY, T=_annees_depuis_strike("2029-09-03"),
        market_snapshot={"constats": short_cal},
        maturity_date="2029-09-03", payment_date="2029-09-10",
        observation_times=[]), USER, s)

    assert deal["events"][-1]["event_date"] == "2029-09-03"
    assert deal["events"][-1]["label"] == "Maturité"


def test_a_deal_with_no_observation_at_all_is_refused():
    """Constat 3 — un calendrier incohérent faisait lever la génération, le
    repli tombait sur une liste client vide, et le deal était booké avec la
    seule ligne de strike : ni surveillance, ni MtM, ni dénouement, sans un
    mot."""
    s = _make_session()
    broken = {"OBSERVATIONS": dict(_CALENDAR["OBSERVATIONS"], end_date="2026-08-01")}
    with pytest.raises(HTTPException) as exc:
        _book_deal(_expert_booking(
            market_snapshot={"constats": broken}, observation_times=[]), USER, s)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "PRODUCT_TERMS_INVALID"
    assert "end_date" in exc.value.detail["message"]
    assert "end_date" in exc.value.detail["message"]  # la cause exacte est nommée


def test_a_broken_calendar_is_not_rescued_by_pricing_times():
    """Un calendrier contractuel invalide doit bloquer le booking."""
    s = _make_session()
    broken = {"OBSERVATIONS": dict(_CALENDAR["OBSERVATIONS"], end_date="2026-08-01")}
    with pytest.raises(HTTPException) as exc:
        _book_deal(_expert_booking(
            market_snapshot={"constats": broken}, observation_times=[1.0, 2.0]), USER, s)
    assert exc.value.status_code == 422


def _booked_for_freeze(s):
    rfq = _new_rfq(s)
    win = _add_quote(s, rfq["id"], "UBS")
    lose = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], lose["id"], rfq_api.QuoteUpdate(price=98.6), USER, s)
    rfq_api.update_quote(rfq["id"], win["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(model_price=97.9), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=win["id"]), USER, s)
    deal = _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s)
    return rfq, win, deal


@pytest.mark.parametrize("label, mutate", [
    ("désélectionner la gagnante",
     lambda api, s, rfq, q: api.update_rfq(rfq["id"], api.RfqUpdate(selected_quote_id=None), USER, s)),
    ("réécrire le prix de la gagnante",
     lambda api, s, rfq, q: api.update_quote(rfq["id"], q["id"], api.QuoteUpdate(price=1.0), USER, s)),
    ("supprimer la gagnante",
     lambda api, s, rfq, q: api.delete_quote(rfq["id"], q["id"], USER, s)),
    ("inverser le sens de l'AO",
     lambda api, s, rfq, q: api.update_rfq(rfq["id"], api.RfqUpdate(sens="vente"), USER, s)),
    ("reclasser sans suite",
     lambda api, s, rfq, q: api.update_rfq(rfq["id"], api.RfqUpdate(status="sans_suite"), USER, s)),
    ("réécrire le prix modèle",
     lambda api, s, rfq, q: api.update_rfq(rfq["id"], api.RfqUpdate(model_price=50.0), USER, s)),
    ("ajouter un fournisseur après coup",
     lambda api, s, rfq, q: api.add_quote(rfq["id"], api.QuoteCreate(provider="Tardif"), USER, s)),
])
def test_the_competitive_record_is_frozen_once_the_tender_traded(label, mutate):
    """Constat 2 — toutes ces mutations passaient sur un AO déjà booké, et
    l'écran Analyse lit la RFQ vivante : la statistique qui sert à décider qui
    mettre en concurrence demain était réécrivable après coup."""
    s = _make_session()
    rfq, win, deal = _booked_for_freeze(s)
    with pytest.raises(HTTPException) as exc:
        mutate(rfq_api, s, rfq, win)
    assert exc.value.status_code == 409
    assert deal["reference"] in exc.value.detail


def test_the_winner_survives_every_refused_mutation():
    s = _make_session()
    rfq, win, deal = _booked_for_freeze(s)
    for m in (lambda: rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=None), USER, s),
              lambda: rfq_api.delete_quote(rfq["id"], win["id"], USER, s)):
        with pytest.raises(HTTPException):
            m()
    assert {h["provider"]: h["won"] for h in rfq_api.rfq_history(USER, s)} == {
        "UBS": True, "BNP Paribas": False}


def test_annotating_a_booked_tender_stays_possible():
    """Une note documente, elle ne fait pas preuve — la geler n'apporte rien."""
    s = _make_session()
    rfq, win, deal = _booked_for_freeze(s)
    assert rfq_api.update_quote(rfq["id"], win["id"],
                                 rfq_api.QuoteUpdate(note="confirmé par tél."), USER, s)["note"]
    assert rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(name="Athena 3Y BNP"), USER, s)["name"]


# ── 16. Audit du 2026-07-30 — les six constats moyens ───────────────────

@pytest.mark.parametrize("label, over, expect", [
    ("nominal nul",            dict(nominal=0.0),                "nominal"),
    ("nominal négatif",        dict(nominal=-5e6),               "nominal"),
    ("fair value nulle",       dict(fair_value=0.0),             "fair value"),
    ("fair value négative",    dict(fair_value=-3.0),            "fair value"),
    ("prix traité nul",        dict(price_traded=0.0),           "prix traité"),
    ("contrepartie vide",      dict(contrepartie="   "),         "contrepartie"),
    ("règlement avant maturité", dict(payment_date="2029-01-01"), "règlement"),
])
def test_booking_refuses_what_is_not_a_trade(label, over, expect):
    """Constat 4 — le formulaire contrôlait une partie de ça, mais la
    frontière c'est l'API : un nominal négatif SOUSTRAYAIT ensuite de
    l'exposition contrepartie."""
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(**over), USER, s)
    assert exc.value.status_code == 422
    assert expect in exc.value.detail


def test_booking_accepts_a_forward_start_paid_before_its_strike():
    s = _make_session()
    deal = _book_deal(_booking_body(strike_date="2026-09-03",
                                    value_date="2026-08-30"), USER, s)
    assert deal["strike_date"] == "2026-09-03"
    assert deal["value_date"] == "2026-08-30"


def test_a_counterparty_outside_the_catalog_stays_accepted():
    """Volontaire : Deal.contrepartie est une chaîne libre pour que l'historique
    reste lisible après un renommage du catalogue."""
    s = _make_session()
    assert _book_deal(
        _booking_body(contrepartie="Banque Inconnue"), USER, s)["contrepartie"] == "Banque Inconnue"


@pytest.mark.parametrize("price, expect", [
    (0.0, "nul ou négatif"), (-50.0, "nul ou négatif"), (10000.0, "invraisemblable"),
])
def test_quote_prices_are_percentage_points(price, expect):
    """Constat 5 — 9850 saisi pour 98,50, ou un montant en devise dans un champ
    en pourcentage."""
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=price), USER, s)
    assert exc.value.status_code == 422
    assert expect in exc.value.detail


def test_the_same_provider_cannot_be_solicited_twice_on_one_tender():
    """Deux lignes pour la même banque la font peser double dans l'écart moyen
    et le hit ratio, et rendent le last look ambigu."""
    s = _make_session()
    rfq = _new_rfq(s)
    _add_quote(s, rfq["id"], "UBS")
    with pytest.raises(HTTPException) as exc:
        _add_quote(s, rfq["id"], "UBS")
    assert exc.value.status_code == 409
    # …mais le last look, lui, crée bien sa seconde ligne du même fournisseur.
    first = rfq_api._get_quotes(rfq["id"], s)[0]
    rfq_api.update_quote(rfq["id"], first.id, rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(rfq["id"], first.id, rfq_api.QuoteUpdate(last_look=True), USER, s)
    assert len(rfq_api._get_quotes(rfq["id"], s)) == 2


def test_a_last_look_that_degrades_the_price_is_refused():
    """Constat 6 — la contre-cote remplace la cotation initiale : acceptée
    dégradée, elle sortait la meilleure réponse du fournisseur de ses propres
    statistiques (+102 bps devenus -102 bps à l'écran)."""
    s = _make_session()
    rfq = _new_rfq(s)   # sens 'achat' par défaut : le mieux est plus bas
    q = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=97.0), USER, s)
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    child = [x for x in rfq_api._get_quotes(rfq["id"], s) if x.parent_quote_id == q["id"]][0]

    with pytest.raises(HTTPException) as exc:
        rfq_api.update_quote(rfq["id"], child.id, rfq_api.QuoteUpdate(price=99.0), USER, s)
    assert exc.value.status_code == 422
    # La bonne cotation reste la réponse du fournisseur.
    rows = rfq_api.rfq_history(USER, s)
    assert [(h["price"], h["superseded"]) for h in rows] == [(97.0, False)]

    # S'aligner exactement, ou améliorer, restent possibles.
    rfq_api.update_quote(rfq["id"], child.id, rfq_api.QuoteUpdate(price=97.0), USER, s)
    rfq_api.update_quote(rfq["id"], child.id, rfq_api.QuoteUpdate(price=96.5), USER, s)


def test_a_last_look_that_degrades_is_read_the_other_way_on_a_sell():
    s = _make_session()
    rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
        name="AO vente", sens="vente", script_snapshot="AT MATURITY\n  PAY 1",
        params=_rfq_params()), USER, s)
    q = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=99.0), USER, s)
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    child = [x for x in rfq_api._get_quotes(rfq["id"], s) if x.parent_quote_id == q["id"]][0]
    # On vend : revenir plus BAS est une dégradation.
    with pytest.raises(HTTPException):
        rfq_api.update_quote(rfq["id"], child.id, rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(rfq["id"], child.id, rfq_api.QuoteUpdate(price=99.4), USER, s)


@pytest.mark.parametrize("field, value", [("sens", "lateral"), ("kind", "n_importe_quoi")])
def test_sens_and_kind_are_constrained(field, value):
    """Constat 7 — _edge_bps teste `sens == "achat"` et retombe SINON sur la
    branche vente : un sens mal orthographié inversait la lecture de tous les
    écarts."""
    with pytest.raises(Exception) as exc:
        rfq_api.RfqCreate(name="X", script_snapshot="AT MATURITY\n  PAY 1", **{field: value})
    assert "pattern" in str(exc.value)


def test_a_negative_model_price_is_refused():
    """Constat 9 — tous les écarts aux cotations en découlent."""
    s = _make_session()
    rfq = _new_rfq(s)
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(model_price=-5.0), USER, s)
    assert exc.value.status_code == 422


# ── 17. Invariants contractuels issus de l'audit final ────────────────

def _rfq_with_contractual_terms(s):
    today = date.today().isoformat()
    params = {
        "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR",
                         "sigma": 0.20, "q": 0.02}],
        "user_params": {"COUPON": 0.08},
        "constats": {},
        "notional": 1_000_000.0,
        "currency": "EUR",
        "strike_date": today,
        "value_date": today,
        # Reglement final cinq jours apres la maturite : c est le term sheet
        # qui le fixe, il ne se deduit d aucune constatation.
        "payment_date": (date.today() + timedelta(days=1101)).isoformat(),
        "T": 3.0,
        "model": "constant",
        "r": 0.03,
    }
    script = "PARAM COUPON = 8%\nAT MATURITY\n  PAY 1 + COUPON"
    rfq = rfq_api.create_rfq(
        rfq_api.RfqCreate(name="Termes figés", script_snapshot=script, params=params), USER, s)
    q = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)
    market = {
        "underlyings": params["underlyings"],
        "user_params": params["user_params"],
        "constats": {},
    }
    return rfq, q, params, _booking_body(
        script_snapshot=script, market_snapshot=market, rfq_id=rfq["id"])


def test_booking_refuse_un_autre_produit_sous_le_meme_rfq_id():
    s = _make_session()
    rfq, q, params, body = _rfq_with_contractual_terms(s)
    body.script_snapshot = "AT MATURITY\n  PAY 0.25"
    with pytest.raises(HTTPException) as exc:
        _book_deal(body, USER, s)
    assert exc.value.status_code == 422
    assert "script_snapshot" in exc.value.detail


def test_booking_conforme_fige_un_hash_des_termes_rfq():
    s = _make_session()
    rfq, q, params, body = _rfq_with_contractual_terms(s)
    deal = _book_deal(body, USER, s)
    assert len(deal["rfq_provenance"]["product_terms_sha256"]) == 64
    assert deal["rfq_provenance"]["retained"]["price"] == 98.0


def test_termes_contractuels_rfqs_sont_figes_apres_sollicitation():
    s = _make_session()
    rfq, q, params, body = _rfq_with_contractual_terms(s)
    changed = dict(params, user_params={"COUPON": 0.20})
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(params=changed), USER, s)
    assert exc.value.status_code == 409

    # Une hypothèse de pricing peut être rafraîchie sans changer le produit.
    repriced = dict(params, r=0.04, model="heston")
    updated = rfq_api.update_rfq(
        rfq["id"], rfq_api.RfqUpdate(params=repriced), USER, s)
    assert updated["params"]["r"] == 0.04


def test_last_look_ne_peut_pas_devenir_une_chaine_cachee():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"], "UBS")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(last_look=True), USER, s)
    child = next(x for x in rfq_api._get_quotes(rfq["id"], s) if x.parent_quote_id)
    with pytest.raises(HTTPException) as exc:
        rfq_api.update_quote(
            rfq["id"], child.id, rfq_api.QuoteUpdate(last_look=True), USER, s)
    assert exc.value.status_code == 422


def test_datetime_avec_offset_est_normalise_en_utc():
    s = _make_session()
    rfq = _new_rfq(s)
    q = _add_quote(s, rfq["id"])
    updated = rfq_api.update_quote(
        rfq["id"], q["id"],
        rfq_api.QuoteUpdate(quoted_at="2026-07-29T13:05:00+02:00"), USER, s)
    assert datetime.fromisoformat(updated["quoted_at"].replace("Z", "+00:00")) == \
        datetime(2026, 7, 29, 11, 5, tzinfo=timezone.utc)


def test_calendrier_post_maturite_est_refuse():
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(
            _expert_booking(maturity_date="2027-08-30", T=1.0), USER, s)
    assert exc.value.status_code == 422
    assert "dépasse la maturité" in exc.value.detail


_NOTE_COUPONS_DEUX_ANS = """PARAM COUPON = 5%
CONSTAT() COUPONS
CONSTAT MATURITE
AT COUPONS:
  PAY COUPON
AT MATURITE:
  PAY 1
"""


def _dans_ans(annees: int) -> date:
    jour = date.today()
    try:
        return jour.replace(year=jour.year + annees)
    except ValueError:                      # 29 février
        return jour.replace(year=jour.year + annees, day=28)


def test_deux_ans_de_coupons_sur_une_note_a_trois_ans_se_booke():
    """M4 (14/09/2026) : la maturité est la dernière date de constatation du
    produit, tous échéanciers confondus. La règle du 13/09 retenait la fin des
    coupons : maturité à deux ans, et la constatation finale à trois ans était
    refusée comme postérieure à la maturité. Le contrôle du booking reste la
    garantie ; c'est la maturité envoyée qui change."""
    fin_coupons, maturite = _dans_ans(2).isoformat(), _dans_ans(3).isoformat()
    constats = {
        "COUPONS": {"start_date": date.today().isoformat(), "end_date": fin_coupons,
                    "roll_date": fin_coupons, "frequency": "1Y", "stub": "short_last"},
        "MATURITE": maturite,
    }
    base = dict(script_snapshot=_NOTE_COUPONS_DEUX_ANS,
                market_snapshot={"constats": constats}, observation_times=[])

    deal = _book_deal(_booking_body(
        **base, maturity_date=maturite, T=_annees_depuis_strike(maturite)), USER, _make_session())
    dates = [e["event_date"] for e in deal["events"]]
    assert dates[-1] == maturite
    assert fin_coupons in dates and len(dates) == 4     # strike + 2 coupons + maturité

    # L'ancienne dérivation (fin des coupons) : le booking la refusait.
    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(
            **base, maturity_date=fin_coupons, T=_annees_depuis_strike(fin_coupons)),
            USER, _make_session())
    assert "dépasse la maturité" in exc.value.detail


# ── 18. Identité RFQ → deal : le contrat, pas son écriture ─────────────

_AUTOCALL_A_ECHEANCIER = """PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


def _rfq_a_echeancier(s):
    """RFQ-20260914-002, ramené à la date du jour : un autocall trimestriel à
    trois ans, strike dans deux semaines.

    Chaque écran écrit le même contrat à sa façon. L'écran RFQ fige T à quatre
    décimales et un échéancier sans clés de fenêtre ; le Pricer renvoie T
    recalculé depuis la maturité à six décimales, et deux clés de fenêtre
    vides."""
    strike = date.today() + timedelta(days=14)
    try:
        fin = strike.replace(year=strike.year + 3)
    except ValueError:                      # 29 février
        fin = strike.replace(year=strike.year + 3, day=28)
    jours = (fin - strike).days
    echeancier = {
        "start_date": strike.isoformat(), "end_date": fin.isoformat(),
        "roll_date": fin.isoformat(), "frequency": "3M", "stub": "short_last",
        "sub_frequency": None, "convention": "none", "settlement_lag": 0,
    }
    params = {
        "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}],
        "user_params": {"COUPON": 0.08, "M_AC_BAR": 1.0, "M_KI_BAR": 0.6},
        "constats": {"OBSERVATIONS": echeancier},
        "notional": 1_000_000.0, "currency": "EUR",
        "strike_date": strike.isoformat(),
        "value_date": (strike + timedelta(days=2)).isoformat(),
        "payment_date": (fin + timedelta(days=5)).isoformat(),
        "T": round(jours / 365.25, 4),            # RfqView.vue : yearsBetween
        "model": "constant", "r": 0.03,
    }
    rfq = rfq_api.create_rfq(rfq_api.RfqCreate(
        name="Autocall à échéancier", script_snapshot=_AUTOCALL_A_ECHEANCIER,
        params=params), USER, s)
    q = _add_quote(s, rfq["id"], "BNP Paribas")
    rfq_api.update_quote(rfq["id"], q["id"], rfq_api.QuoteUpdate(price=98.0), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=q["id"]), USER, s)

    body = _booking_body(
        script_snapshot=_AUTOCALL_A_ECHEANCIER,
        market_snapshot={
            "underlyings": params["underlyings"],
            "user_params": params["user_params"],
            "constats": params["constats"],
        },
        rfq_id=rfq["id"], strike_date=params["strike_date"],
        value_date=params["value_date"], maturity_date=fin.isoformat(),
        payment_date=params["payment_date"],
        # Le Pricer reprend le T canonique du Product créé par la RFQ.
        T=params["T"],
        observation_times=[])
    return params, body


def test_le_pricer_reprend_le_contrat_canonique_du_product_de_la_rfq():
    """Le Pricer ne recalcule pas T : il reprend la valeur portée par Product."""
    s = _make_session()
    params, body = _rfq_a_echeancier(s)
    assert body.T == params["T"]

    deal = _book_deal(body, USER, s)

    assert deal["rfq_provenance"]["retained"]["price"] == 98.0


@pytest.mark.parametrize("changement, champ", [
    ("maturite_un_jour_plus_tard", "T"),
    ("frequence", "constats"),
    ("fenetre_de_constatation", "constats"),
])
def test_un_autre_contrat_reste_refuse_au_booking_de_la_rfq(changement, champ):
    """La comparaison tolère l'écriture, jamais le contrat : un jour de
    maturité, une fréquence ou une fenêtre qui porte une valeur restent des
    termes différents de ceux que les fournisseurs ont cotés."""
    s = _make_session()
    params, body = _rfq_a_echeancier(s)
    observations = body.market_snapshot["constats"]["OBSERVATIONS"]
    if changement == "maturite_un_jour_plus_tard":
        body.T = round(body.T + 1 / 365.25, 6)
    elif changement == "frequence":
        observations["frequency"] = "6M"
    else:
        observations.update(window_length="10D", window_frequency="1D")

    with pytest.raises(HTTPException) as exc:
        _book_deal(body, USER, s)

    assert exc.value.status_code == 422
    assert exc.value.detail.endswith(
        f"figés de la RFQ : {champ}. Rechargez le booking depuis la RFQ ; "
        "pour un autre produit, créez une nouvelle RFQ.")


def test_t_se_compare_en_jours_arrondis_comme_les_ecrans():
    """T = 2 fait 730,5 jours. Le Pricer en tire une maturité 731 jours après
    le strike (Math.round), puis T = 731 / 365,25 ; l'arrondi bancaire de
    Python aurait compté 730 jours et inventé un jour d'écart."""
    assert booking_terms_differences({"T": 2.0}, {"T": 731 / 365.25}) == []
    assert booking_terms_differences({"T": 2.0}, {"T": 732 / 365.25}) == ["T"]


def test_allocation_de_references_est_atomique_sous_concurrence(tmp_path):
    db = tmp_path / "references.db"
    eng = create_engine(
        f"sqlite:///{db}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    SQLModel.metadata.create_all(eng)
    prefix = "RFQ-20991231-"

    def allocate(i):
        with Session(eng) as session:
            ref = next_reference(session, RfqRequest, prefix)
            session.add(RfqRequest(
                reference=ref, user_id=1, name=f"RFQ {i}",
                script_snapshot="AT MATURITY\n  PAY 1"))
            session.commit()
            return ref

    with ThreadPoolExecutor(max_workers=8) as executor:
        refs = list(executor.map(allocate, range(8)))
    assert len(set(refs)) == 8
    assert sorted(refs) == [f"{prefix}{i:03d}" for i in range(1, 9)]


def test_unicite_structurelle_un_deal_par_rfq():
    s = _make_session()
    rfq = RfqRequest(reference="RFQ-UNIQUE", user_id=1, name="unique")
    s.add(rfq)
    s.flush()
    first = _booking_body(rfq_id=rfq.id)
    # Test the database invariant directly, independent of the endpoint's
    # earlier and friendlier 409 check.
    from backend.app.db.models import Deal
    common = dict(
        user_id=1, rfq_id=rfq.id, sens=first.sens,
        contrepartie=first.contrepartie, devise=first.devise,
        nominal=first.nominal, fair_value=first.fair_value,
        price_traded=first.price_traded, trade_date=first.trade_date,
        strike_date=first.strike_date, value_date=first.value_date,
        maturity_date=first.maturity_date, T=first.T,
        script_snapshot=first.script_snapshot,
    )
    s.add(Deal(reference="DEAL-UNIQUE-1", **common))
    s.add(Deal(reference="DEAL-UNIQUE-2", **common))
    with pytest.raises(IntegrityError):
        s.commit()
    s.rollback()


def test_backfill_statuts_rfq_est_une_migration_executee_une_seule_fois(monkeypatch):
    from backend.app.db import database as database_api

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rfq = RfqRequest(reference="RFQ-BACKFILL", user_id=1, status="draft")
        s.add(rfq)
        s.flush()
        s.add(RfqQuote(rfq_id=rfq.id, provider="UBS", price=98.0))
        s.commit()

    monkeypatch.setattr(database_api, "engine", eng)
    database_api._backfill_rfq_statuses()
    database_api._backfill_rfq_statuses()

    with Session(eng) as s:
        assert s.exec(select(RfqRequest)).one().status == "quote"
        count = s.execute(text(
            "SELECT COUNT(*) FROM app_migrations WHERE key='rfq_statuses_derived_v1'"
        )).scalar_one()
        assert count == 1


def test_renaming_a_counterparty_keeps_its_providers_attached():
    """Constat 8 — « BNP Paribas » renommé « BNP Paribas SA » et le fournisseur
    RFQ du même nom ne résolvait plus rien, découvert au booking suivant."""
    from backend.app.api import admin as admin_api
    s = _make_session()
    c = Counterparty(name="BNP Paribas", active=True)
    s.add(c)
    s.flush()
    s.add(RfqProvider(label="BNP Paribas"))
    s.commit()
    assert rfq_api._counterparty_by_provider(s) == {"BNP Paribas": "BNP Paribas"}

    admin_api.update_counterparty(c.id, admin_api.CounterpartyUpdate(name="BNP Paribas SA"),
                                   USER, s)
    # Le fournisseur suit le renommage au lieu de tomber dans le vide.
    assert rfq_api._counterparty_by_provider(s) == {"BNP Paribas": "BNP Paribas SA"}


# ── 4. Hypothèses de marché du prix modèle (28/08/2026) ────────────────
#
# Un AO doit pouvoir être valorisé avant de solliciter les contreparties, avec
# une courbe de taux, une courbe de dividende et un spread émetteur. Trois
# façons de rater ce branchement, une seule s'entend :
#
#   — les clés n'atteignent pas les params stockés (fil coupé) ;
#   — elles les atteignent mais emportent les termes contractuels au passage,
#     et le contrôle de gel se déclenche sur ce que personne n'a touché ;
#   — elles arrivent, sont conservées… et ne déplacent pas le prix.
#
# Le troisième cas est celui que le projet a déjà connu : une hypothèse
# saisissable et sans effet. Une courbe de dividende à 8 % vaut −491,6 bps.

_CONTRACTUEL = {
    "underlyings": [{"name": "STM", "ticker": "STM.PA", "ccy": "EUR",
                     "sigma": 0.30, "q": 0.04}],
    "corr_matrix": [[1.0]], "notional": 1_000_000, "currency": "EUR",
    "strike_date": "2026-01-15", "value_date": "2026-01-20", "T": 3.0,
    "user_params": {"M_KI": 0.60}, "constats": {},
    "r": 0.03, "N": 8000, "model": "constant",
}


def _rfq_avec_params(s: Session):
    # `create_rfq` rend la vue sérialisée ; on veut la ligne.
    cree = _new_rfq(s)
    rfq = s.get(RfqRequest, cree["id"])
    rfq.params_json = json.dumps(_CONTRACTUEL)
    s.add(rfq)
    s.commit()
    s.refresh(rfq)
    return rfq


def _pricer(s: Session, rfq_id: int, hypotheses: dict):
    """Le vrai chemin de l'écran : PATCH pricing_params, puis lecture."""
    rfq_api.update_rfq(rfq_id, rfq_api.RfqUpdate(pricing_params=hypotheses), USER, s)
    return json.loads(s.get(RfqRequest, rfq_id).params_json)


def test_les_hypotheses_de_marche_atteignent_les_params_stockes():
    with _make_session() as s:
        rfq = _rfq_avec_params(s)
        params = _pricer(s, rfq.id, {
            "yield_curve": [[1, 0.05], [3, 0.055], [5, 0.06]],
            "funding_spread": 0.015,
            "underlyings": [{"dividend_curve": [[1, 0.04], [2, 0.036]],
                             "dividend_decay": 0.10}],
        })

        assert params["yield_curve"] == [[1, 0.05], [3, 0.055], [5, 0.06]]
        assert params["funding_spread"] == 0.015
        assert params["underlyings"][0]["dividend_curve"] == [[1, 0.04], [2, 0.036]]
        assert params["underlyings"][0]["dividend_decay"] == 0.10


def test_les_hypotheses_ne_deplacent_aucun_terme_contractuel():
    # Le contrôle négatif du test précédent : ce qui passe est cantonné aux
    # hypothèses de modèle. Sans lui, un AO cotations en main deviendrait
    # impossible à re-pricer — le gel se déclencherait sur des termes intacts.
    with _make_session() as s:
        rfq = _rfq_avec_params(s)
        params = _pricer(s, rfq.id, {
            "yield_curve": [[1, 0.05]],
            "strike_date": "2099-12-31",       # contractuel : doit être ignoré
            "user_params": {"M_KI": 0.99},     # idem
            "underlyings": [{"ticker": "AAAA.PA", "dividend_decay": 0.10}],
        })

        assert params["strike_date"] == "2026-01-15"
        assert params["user_params"] == {"M_KI": 0.60}
        assert params["underlyings"][0]["ticker"] == "STM.PA"
        assert params["underlyings"][0]["dividend_decay"] == 0.10   # le fil passe


def test_les_hypotheses_survivent_a_un_second_calcul():
    # Rouvrir un AO recharge les cartes depuis les params ; renvoyer ce
    # qu'elles portent ne doit rien effacer. Une carte qui rouvrirait décochée
    # renverrait une courbe vide et le prix changerait sans que personne n'ait
    # touché à une hypothèse.
    with _make_session() as s:
        rfq = _rfq_avec_params(s)
        _pricer(s, rfq.id, {"yield_curve": [[1, 0.05]], "funding_spread": 0.015})
        params = _pricer(s, rfq.id, {"yield_curve": [[1, 0.05]],
                                     "funding_spread": 0.015, "N": 12000})

        assert params["yield_curve"] == [[1, 0.05]]
        assert params["funding_spread"] == 0.015
        assert params["N"] == 12000


# ── 5. Le booking qualifie la cotation retenue (29/08/2026) ────────────
#
# Décider de booker EST l'affirmation que le prix engage la contrepartie : on
# ne traite pas sur un prix qui n'engage personne. La laisser « à qualifier »
# ferait mentir l'analyse contrepartie, qui compterait comme non qualifié un
# prix sur lequel on a effectivement traité.
#
# Ce que la provenance doit distinguer, six mois plus tard : une fermeté
# affirmée par la BANQUE avant le trade, et une fermeté affirmée par l'acte de
# booking. Les deux se lisent « FIRM » sur la quote ; seule la provenance dit
# laquelle, et c'est la distinction qui a une valeur probante.

def _rfq_bookee(s, fermete):
    rfq = _new_rfq(s)
    quote = _add_quote(s, rfq["id"])
    rfq_api.update_quote(rfq["id"], quote["id"], rfq_api.QuoteUpdate(
        price=99.1, quoted_at=datetime.utcnow().isoformat()), USER, s)
    rfq_api.update_rfq(rfq["id"], rfq_api.RfqUpdate(selected_quote_id=quote["id"]), USER, s)
    deal = _book_deal(_booking_body(rfq_id=rfq["id"]), USER, s, fermete=fermete)
    return (s.get(RfqQuote, quote["id"]),
            json.loads(s.get(Deal, deal["id"]).rfq_provenance_json))


def test_le_booking_qualifie_une_quote_a_qualifier():
    with _make_session() as s:
        quote, provenance = _rfq_bookee(s, "UNKNOWN")

        assert quote.firmness == "FIRM"
        assert provenance["retained"]["firmness_asserted_at_booking"] is True


def test_une_quote_deja_ferme_ne_doit_rien_au_booking():
    # Le contrôle négatif : sans lui, la provenance dirait « affirmée au
    # booking » de toute cotation, et la distinction ne vaudrait plus rien.
    with _make_session() as s:
        quote, provenance = _rfq_bookee(s, "FIRM")

        assert quote.firmness == "FIRM"
        assert provenance["retained"]["firmness_asserted_at_booking"] is False


def test_une_quote_indicative_se_booke_et_laisse_sa_trace():
    """Le booking n'est plus bloqué, et la piste d'audit ne perd rien.

    C'est tout l'échange du 29/08/2026 : le portillon refusait de booker la
    solution retenue tant qu'elle n'était pas écrite « ferme ». Retenir puis
    booker EST l'affirmation qu'elle engage — l'étiquette n'apprenait rien à
    personne.

    Ce qu'il ne fallait pas perdre en levant le blocage : « on a booké sur une
    cotation marquée indicative » est un fait qui doit rester lisible six mois
    plus tard. Il vit maintenant dans la provenance, pas dans un refus.
    """
    with _make_session() as s:
        quote, provenance = _rfq_bookee(s, "INDICATIVE")

        assert quote.firmness == "FIRM"                       # qualifiée au booking
        retenue = provenance["retained"]
        assert retenue["firmness_before_booking"] == "INDICATIVE"
        assert retenue["firmness_asserted_at_booking"] is True


# ── Le refus à l'ÉCRITURE (29/08/2026) ────────────────────────────────
#
# Le signaler au booking ne suffit pas : un AO reçoit des cotations en quelques
# minutes, et ses termes sont alors gelés. Une incohérence acceptée à la
# création devient impossible à corriger.

_SCRIPT_EXPERT = """PARAM COUPON = 8%
CONSTAT() OBSERVATIONS

AT OBSERVATIONS.last:
  PAY 1
"""

_DATES = {
    "underlyings": [{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}],
    "notional": 1_000_000, "currency": "EUR", "T": 3.0,
    "strike_date": "2026-08-31", "value_date": "2026-08-31",
    "constats": {"OBSERVATIONS": {
        "start_date": "2026-08-31", "end_date": "2029-08-31", "frequency": "1Y"}},
}


def _creer(s, payment_date):
    return rfq_api.create_rfq(rfq_api.RfqCreate(
        name="Autocall SX5E", script_snapshot=_SCRIPT_EXPERT,
        params={**_DATES, "payment_date": payment_date}), USER, s)


def test_un_ao_reglant_avant_sa_maturite_est_refuse_a_la_creation():
    with _make_session() as s:
        with pytest.raises(HTTPException) as exc:
            _creer(s, "2026-09-03")

        assert exc.value.status_code == 422
        assert "précède la maturité" in exc.value.detail


def test_un_ao_coherent_se_cree_normalement():
    # Le contrôle négatif, sans lequel le garde pourrait tout refuser.
    with _make_session() as s:
        assert _creer(s, "2029-09-05")["reference"].startswith("RFQ-")


def test_le_refus_vaut_aussi_a_la_modification():
    # L'autre porte d'écriture. Sans elle, on créerait cohérent puis on
    # rendrait incohérent à la première modification.
    with _make_session() as s:
        cree = _creer(s, "2029-09-05")
        with pytest.raises(HTTPException) as exc:
            rfq_api.update_rfq(cree["id"], rfq_api.RfqUpdate(
                params={**_DATES, "payment_date": "2026-09-03"}), USER, s)

        assert exc.value.status_code == 422
        assert "précède la maturité" in exc.value.detail
