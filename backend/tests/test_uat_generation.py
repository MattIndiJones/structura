"""Regression tests for the Admin RFQ / booking UAT generator."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.rfq_controls import booking_gate_failures
from backend.app.db.models import (
    Alert, AuditEvent, Counterparty, Deal, DealEvent, Entity, LifecycleProposal,
    OfficialFixingVersion, RfqProvider, RfqQuote, RfqRequest,
    UatGenerationBatch, User,
)
from backend.app.services.uat_generation import (
    UatGenerationRequest, delete_batch, generate_batch, preview_generation,
)


def _session_and_users() -> tuple[Session, User, User]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    entity = Entity(name="UAT tests")
    session.add(entity)
    session.flush()
    admin = User(
        username="uat-admin", email="uat-admin@test", password_hash="x",
        role="admin", entity_id=entity.id)
    target = User(
        username="uat-target", email="uat-target@test", password_hash="x",
        role="user", entity_id=entity.id)
    ubs = Counterparty(name="UBS", country="CH", active=True)
    bnp = Counterparty(name="BNP Paribas", country="FR", active=True)
    session.add(admin); session.add(target); session.add(ubs); session.add(bnp)
    session.flush()
    session.add(RfqProvider(label="UBS", counterparty_id=ubs.id, active=True))
    session.add(RfqProvider(
        label="BNP Paribas", counterparty_id=bnp.id, active=True))
    session.commit()
    session.refresh(admin); session.refresh(target)
    return session, admin, target


def _request(target: User, **overrides) -> UatGenerationRequest:
    values = {
        "target_user_id": target.id,
        "mode": "FULL_CHAIN",
        "count": 2,
        "seed": 17,
        "product_types": ["ATHENA", "PHOENIX"],
        "underlying_tickers": ["^STOXX50E", "^GSPC"],
        "max_underlyings": 2,
        "quotes_per_rfq": 2,
    }
    values.update(overrides)
    return UatGenerationRequest(**values)


def test_preview_is_deterministic_and_read_only():
    session, _, target = _session_and_users()
    body = _request(target)
    first = preview_generation(body, session)
    second = preview_generation(body, session)
    assert first == second
    assert first["rfq_count"] == 2
    assert first["deal_count"] == 2
    assert not session.exec(select(RfqRequest)).first()
    assert not session.exec(select(Deal)).first()
    assert not session.exec(select(UatGenerationBatch)).first()


def test_full_chain_uses_uat_references_and_batch_cleanup_is_isolated():
    session, admin, target = _session_and_users()
    ordinary = Deal(
        reference="LIVE-DO-NOT-DELETE", user_id=target.id,
        script_snapshot="AT MATURITY\n  PAY 1", sens="vente",
        contrepartie="UBS", devise="EUR", nominal=100_000,
        fair_value=99.0, price_traded=99.2,
        trade_date=date.today().isoformat(), strike_date=date.today().isoformat(),
        value_date=date.today().isoformat(), maturity_date="2030-01-01", T=3.0,
        underlyings_json="[]", market_snapshot_json="{}")
    session.add(ordinary)
    session.commit()

    batch = generate_batch(_request(target), admin, session)
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).all()
    deals = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).all()
    assert batch["status"] == "COMPLETED"
    assert len(rfqs) == len(deals) == 2
    assert all(rfq.reference.startswith("UAT-RFQ-") for rfq in rfqs)
    assert all(deal.reference.startswith("UAT-DEAL-") for deal in deals)
    assert all(deal.rfq_id for deal in deals)
    assert all(rfq.status == "clos" for rfq in rfqs)
    created_audit = session.exec(select(AuditEvent).where(
        AuditEvent.action == "RFQ_CREATED",
        AuditEvent.object_id == rfqs[0].id)).one()
    booked_audit = session.exec(select(AuditEvent).where(
        AuditEvent.action == "BOOKING_ACCEPTED",
        AuditEvent.object_id == deals[0].id)).one()
    assert json.loads(created_audit.after_json)["reference"].startswith("UAT-RFQ-")
    assert json.loads(booked_audit.after_json)["reference"].startswith("UAT-DEAL-")
    assert session.exec(select(AuditEvent).where(
        AuditEvent.action == "UAT_BATCH_GENERATED")).one()

    deleted = delete_batch(batch["id"], admin, session)
    assert deleted == {
        "id": batch["id"], "status": "DELETED",
        "deleted_rfqs": 2, "deleted_deals": 2,
    }
    assert session.exec(select(Deal).where(
        Deal.reference == "LIVE-DO-NOT-DELETE")).one()
    assert not session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).first()
    assert session.get(UatGenerationBatch, batch["id"]).status == "DELETED"


def test_rfq_control_mix_builds_expected_non_bookable_cases():
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, mode="RFQ_ONLY", count=4, quotes_per_rfq=1,
        rfq_profile="CONTROL_MIX"), admin, session)
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"]).order_by(RfqRequest.created_at)).all()
    assert len(rfqs) == 4

    codes_by_index = []
    for rfq in rfqs:
        selected = session.get(RfqQuote, rfq.selected_quote_id) \
            if rfq.selected_quote_id else None
        expected_counterparty = selected.provider if selected else ""
        codes_by_index.append({failure.code for failure in booking_gate_failures(
            rfq, selected,
            expected_counterparty=expected_counterparty or None,
            requested_counterparty=expected_counterparty,
        )})
    assert codes_by_index[0] == set()
    assert "QUOTE_EXPIRED" in codes_by_index[1]
    # Le scénario INDICATIVE reste généré — c'est un état de donnée réel —
    # mais il ne bloque plus le booking : aucune étiquette de fermeté ne le
    # fait depuis le 29/08/2026. Ce qu'il valait est conservé dans la
    # provenance du deal, pas opposé au desk.
    assert codes_by_index[2] == set()
    assert "QUOTE_NOT_SELECTED" in codes_by_index[3]


def test_invalid_ranges_are_rejected_before_batch_creation():
    session, _, target = _session_and_users()
    with pytest.raises(HTTPException) as exc:
        preview_generation(_request(
            target, maturity_min_years=5, maturity_max_years=1), session)
    assert exc.value.status_code == 422
    assert "maturité minimale" in str(exc.value.detail).lower()
    assert not session.exec(select(UatGenerationBatch)).first()


@pytest.mark.parametrize("family", [
    "ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED",
])
def test_every_offered_product_family_completes_the_full_chain(family):
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, count=1, product_types=[family], seed=3), admin, session)
    assert batch["status"] == "COMPLETED"
    assert batch["rfq_count"] == batch["deal_count"] == 1


@pytest.mark.parametrize(("profile", "family"), [
    ("CURRENT_ACTIVE", "ATHENA"),
    ("ACTIVE_1Y_PENDING", "ATHENA"),
    ("ACTIVE_2Y_OFFICIAL", "PHOENIX"),
    ("MATURED_PENDING", "REVERSE_CONVERTIBLE"),
    ("CALLED", "ATHENA"),
    ("MATURED_FINAL", "CAPITAL_GUARANTEED"),
    ("MATURED_KI", "REVERSE_CONVERTIBLE"),
])
def test_every_reached_observation_carries_its_real_close(profile, family):
    """One observation, one date, that underlying's actual close on that date.

    The generator used to attach a constant ratio instead — a flat 0.80, or
    1.15 to force a call, 0.35 to force a knock-in — so a deal showed the same
    number at three different dates (430 -> 344, 344, 344) and every profile
    that skipped the machinery had no strike fixing at all, leaving the barrier
    watchlist with no S0 to measure against.

    The deal's outcome is deliberately not asserted: it is whatever the script
    makes of the real closes, which is the point. The profile only sets how far
    back the deal was traded.
    """
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target,
        mode="BOOKED_ONLY",
        count=1,
        seed=29,
        product_types=[family],
        lifecycle_profile=profile,
    ), admin, session)
    assert batch["status"] == "COMPLETED"
    assert batch["result"]["scenarios"][0]["profile"] == profile

    deal = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).one()
    events = session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id).order_by(DealEvent.event_index)).all()
    today = date.today().isoformat()
    reached = [e for e in events if e.event_date <= today]
    assert reached, f"{profile} devrait avoir au moins la constatation de strike"

    # The strike must be fixed: without S0 the barrier watchlist computes
    # nothing at all, which is how four active deals out of five ended up
    # showing "en attente du strike" for ever.
    strike = next(e for e in events if e.t_years == 0.0)
    s0 = json.loads(strike.spots_json or "{}")
    assert s0, "pas de S0 : la surveillance des barrières ne peut rien calculer"
    assert set(s0) == {u["name"] for u in json.loads(deal.underlyings_json)}
    assert all(v > 0 for v in s0.values())

    for event in reached:
        spots = json.loads(event.spots_json or "{}")
        assert spots, f"{event.label} atteinte mais sans cours"
        assert all(v > 0 for v in spots.values())

    # No cloned values: a ratio applied to S0 gave the exact same number at
    # every date, which no underlying ever does.
    if len(reached) > 2:
        first = json.loads(reached[1].spots_json)
        assert any(json.loads(e.spots_json) != first for e in reached[2:]), \
            "toutes les observations portent le même cours — ratio synthétique ?"


def test_forward_start_has_nothing_to_fix_yet():
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, mode="BOOKED_ONLY", count=1, seed=29,
        product_types=["CAPITAL_GUARANTEED"], lifecycle_profile="FORWARD_START",
    ), admin, session)
    deal = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).one()
    events = session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id)).all()

    assert date.fromisoformat(deal.strike_date) > date.today()
    assert all(date.fromisoformat(e.event_date) > date.today() for e in events)
    assert all(not json.loads(e.spots_json or "{}") for e in events)
    assert batch["result"]["scenarios"][0]["official_fixings"] == 0


@pytest.mark.parametrize("profile", ["ACTIVE_1Y_PENDING", "MATURED_PENDING"])
def test_controlled_deal_is_never_auto_filled(profile):
    """A FOUR_EYES deal has no automatic source, so nothing is invented for it.

    Its values are entered by hand — but they are left plainly empty rather
    than dressed up: the exception modal labels the indicative column "dernière
    valeur Yahoo", and a fabricated number there is officialised in one click.
    """
    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, mode="BOOKED_ONLY", count=1, seed=29,
        product_types=["ATHENA"], lifecycle_profile=profile,
        fixing_policy="FOUR_EYES",
    ), admin, session)
    deal = session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).one()
    events = session.exec(select(DealEvent).where(
        DealEvent.deal_id == deal.id)).all()

    assert deal.fixing_policy == "FOUR_EYES"
    assert batch["result"]["scenarios"][0]["official_fixings"] == 0
    assert all(not json.loads(e.spots_json or "{}") for e in events)
    assert all(not json.loads(e.indicative_spots_json or "{}") for e in events)


def test_complete_mix_covers_all_eight_profiles_and_cleans_terminal_dependencies():
    session, admin, target = _session_and_users()
    body = _request(
        target,
        mode="FULL_CHAIN",
        count=8,
        seed=31,
        product_types=[
            "ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED",
        ],
        lifecycle_profile="COMPLETE_MIX",
    )
    preview = preview_generation(body, session)
    assert set(preview["profile_counts"]) == {
        "CURRENT_ACTIVE", "FORWARD_START", "ACTIVE_1Y_PENDING",
        "ACTIVE_2Y_OFFICIAL", "MATURED_PENDING", "CALLED",
        "MATURED_FINAL", "MATURED_KI",
    }
    assert all(count == 1 for count in preview["profile_counts"].values())

    batch = generate_batch(body, admin, session)
    assert {row["profile"] for row in batch["result"]["scenarios"]} \
        == set(preview["profile_counts"])
    assert session.exec(select(OfficialFixingVersion)).first()
    assert session.exec(select(LifecycleProposal)).first()
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).all()
    assert len(rfqs) == 8
    assert all(rfq.status == "clos" for rfq in rfqs)
    assert any(date.fromisoformat(rfq.ao_date) < date.today() for rfq in rfqs)

    delete_batch(batch["id"], admin, session)
    assert not session.exec(select(Deal).where(Deal.uat_batch_id == batch["id"])).first()
    assert not session.exec(select(OfficialFixingVersion)).first()
    assert not session.exec(select(LifecycleProposal)).first()
    assert not session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"])).first()


def test_periodic_historical_profile_rejects_non_periodic_product_selection():
    session, _, target = _session_and_users()
    with pytest.raises(HTTPException) as exc:
        preview_generation(_request(
            target,
            product_types=["REVERSE_CONVERTIBLE", "CAPITAL_GUARANTEED"],
            lifecycle_profile="ACTIVE_2Y_OFFICIAL",
        ), session)
    assert exc.value.status_code == 422
    assert "Athena ou Phoenix" in str(exc.value.detail)


@pytest.mark.parametrize("jour", [
    pytest.param(date(2026, 8, 24), id="lundi"),
    pytest.param(date(2026, 8, 26), id="mercredi"),
    pytest.param(date(2026, 8, 28), id="vendredi"),
    pytest.param(date(2026, 8, 29), id="samedi"),
    pytest.param(date(2026, 8, 30), id="dimanche"),
])
def test_le_lot_de_controle_reste_bookable_quel_que_soit_le_jour(monkeypatch, jour):
    """Régression : la RFQ propre du lot de contrôle vieillissait le week-end.

    `_profile_dates` cale ses dates sur un jour ouvré en RECULANT. Le profil
    CURRENT_ACTIVE pose `trade = today` — délibérément, pour garder une RFQ
    fraîche et bookable dans le lot — puis se fait ramener au vendredi dès qu'on
    génère un samedi. La garde d'ancienneté comparait ce jour ouvré à une date
    CALENDAIRE : la RFQ était donc vieillie, et sortait avec QUOTE_EXPIRED et
    MODEL_PRICE_STALE.

    Le défaut ne se voyait ni le lundi ni le jeudi. Ce test parcourt la semaine
    entière, parce qu'un cas nominal en semaine passerait sans rien prouver.
    """
    import backend.app.services.uat_generation as gen

    class _Date(date):
        @classmethod
        def today(cls):
            return jour
    monkeypatch.setattr(gen, "date", _Date)

    session, admin, target = _session_and_users()
    batch = generate_batch(_request(
        target, mode="RFQ_ONLY", count=4, quotes_per_rfq=1,
        rfq_profile="CONTROL_MIX"), admin, session)
    rfqs = session.exec(select(RfqRequest).where(
        RfqRequest.uat_batch_id == batch["id"]).order_by(RfqRequest.created_at)).all()

    selected = session.get(RfqQuote, rfqs[0].selected_quote_id)
    codes = {f.code for f in booking_gate_failures(
        rfqs[0], selected,
        expected_counterparty=selected.provider,
        requested_counterparty=selected.provider)}
    assert codes == set(), f"généré un {jour:%A} : {sorted(codes)}"
