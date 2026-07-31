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

from backend.app.api import deals as deals_api
from backend.app.api import rfq as rfq_api
from backend.app.db.models import Counterparty, RfqProvider, RfqQuote, RfqRequest
from backend.app.core.references import next_reference
from backend.app.core.rfq_controls import pricing_input_hash

USER = SimpleNamespace(id=1, entity_id=1)


def _make_session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _new_rfq(s: Session):
    body = rfq_api.RfqCreate(name="Autocall test", script_snapshot="AT MATURITY\n  PAY 1")
    return rfq_api.create_rfq(body, USER, s)


def _add_quote(s: Session, rfq_id: int, provider: str = "BNP Paribas"):
    return rfq_api.add_quote(rfq_id, rfq_api.QuoteCreate(provider=provider), USER, s)


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

    # Expert-mode script (CONSTAT calendar) — allowed even with no script_id
    # at all, e.g. sourced from an already-booked deal rather than the
    # script library.
    rfq = rfq_api.create_rfq(
        rfq_api.RfqCreate(name="Autocall précis", kind="to_trade",
                           script_snapshot="CONSTAT() Cal\nAT Cal:\n  PAY 0\nAT MATURITY\n  PAY 1"),
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
        maturity_date=(date.today() + timedelta(days=1096)).isoformat(), T=3.0,
        underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "s0_abs": 100.0}],
        observation_times=[1.0, 2.0, 3.0],
        script_snapshot="AT MATURITY\n  PAY 1",
        rfq_id=rfq["id"],
    )
    deal = _book_deal(body, USER, s)

    assert deal["rfq_id"] == rfq["id"]
    closed_rfq = s.get(RfqRequest, rfq["id"])
    assert closed_rfq.status == "clos"


def _booking_body(**over):
    base = dict(
        contrepartie="BNP Paribas", nominal=1_000_000.0, fair_value=97.9,
        price_traded=98.0, trade_date=date.today().isoformat(),
        strike_date=date.today().isoformat(), value_date=date.today().isoformat(),
        maturity_date=(date.today() + timedelta(days=1096)).isoformat(), T=3.0,
        underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "s0_abs": 100.0}],
        observation_times=[1.0, 2.0, 3.0],
        script_snapshot="AT MATURITY\n  PAY 1",
    )
    base.update(over)
    return deals_api.DealCreate(**base)


def _book_deal(body, current, s):
    """Upgrade legacy success fixtures to the now-explicit execution contract.

    Tests that exercise missing/foreign/unselected RFQs remain untouched: only
    a retained, owned quote is qualified here. Production code has no fallback.
    """
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
                    "T": body.T, "model": "constant", "r": 0.03,
                }
                rfq.params_json = json.dumps(params)
            rfq.kind = "to_trade"
            rfq.model_price = rfq.model_price or body.fair_value
            rfq.model_price_at = datetime.utcnow()
            rfq.model_input_hash = pricing_input_hash(rfq.script_snapshot, params)
            selected.firmness = "FIRM"
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
        rfq_api.RfqCreate(name="RFQ d'un autre desk", script_snapshot="AT MATURITY\n  PAY 1"),
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

_CALENDAR = {"OBSERVATIONS": {
    "start_date": "2026-08-30", "end_date": "2029-08-30",
    "roll_date": "2027-08-30", "frequency": "1Y", "stub": "short_last",
}}


def _expert_booking(**over):
    base = dict(
        script_snapshot=_EXPERT_SCRIPT,
        market_snapshot={"constats": _CALENDAR},
        value_date="2026-09-03",
        maturity_date="2029-08-30",
        T=2.9897,
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
    assert times[1:] == [0.9884, 1.9904, 2.9897]


def test_the_contractual_calendar_wins_over_the_simulation_grid():
    """Les temps envoyés par le client sont ceux de la grille hebdomadaire du
    Monte Carlo (0.9808 = 51/52), pas ceux du calendrier (0.9884) — 3 jours
    d'écart sur chaque date d'observation dont le cycle de vie se sert."""
    s = _make_session()
    deal = _book_deal(
        _expert_booking(observation_times=[0.9808, 2.0, 2.9808]), USER, s)

    assert [e["t_years"] for e in deal["events"]][1:] == [0.9884, 1.9904, 2.9897]
    # …et la date affichée redevient celle du contrat.
    assert deal["events"][1]["event_date"] == "2027-08-30"


def test_an_unresolvable_script_is_refused_even_with_client_times():
    """Une grille Monte-Carlo cliente n'est pas un calendrier contractuel."""
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(
            _expert_booking(market_snapshot={}, observation_times=[1.0, 2.0]), USER, s)
    assert exc.value.status_code == 422
    assert "calendrier contractuel" in exc.value.detail


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
        script_snapshot=_ATHENA_MATURITY, T=3.0,
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
        script_snapshot=_ATHENA_MATURITY, T=3.0,
        market_snapshot={"constats": short_cal},
        maturity_date="2029-09-03", observation_times=[]), USER, s)

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
    assert "calendrier contractuel" in exc.value.detail
    assert "end_date" in exc.value.detail        # la cause exacte est nommée


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


def test_booking_refuses_a_settlement_before_its_own_strike():
    s = _make_session()
    with pytest.raises(HTTPException) as exc:
        _book_deal(_booking_body(strike_date="2026-09-03",
                                           value_date="2026-08-30"), USER, s)
    assert exc.value.status_code == 422
    assert "date de valeur" in exc.value.detail


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
        name="AO vente", sens="vente", script_snapshot="AT MATURITY\n  PAY 1"), USER, s)
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
