"""Lot 2 — faits éligibles, périmètres et habitudes de sélection.

Ces tests portent sur les règles qui seraient faciles à rendre trompeuses :
les données fictives ne contaminent pas un profil réel, l'agrégat Client ne
masque pas deux mandats opposés, et un meilleur prix non retenu reste une
observation réversible plutôt qu'une exclusion déduite.
"""
import json
from datetime import date

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.client_intelligence import (
    Transaction, client_intelligence, provider_selection_analysis,
)
from backend.app.db.models import Client, ClientMandate, ClientTradeHistory, Deal


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _history(client_id, mandate_id, index, *, transaction_format,
             instrument_family, payoff_family):
    return ClientTradeHistory(
        entity_id=1, client_id=client_id, mandate_id=mandate_id,
        trade_date=f"2026-0{index + 1}-15", maturity_date="2029-01-15",
        product_type=payoff_family, transaction_format=transaction_format,
        instrument_family=instrument_family, payoff_family=payoff_family,
        documentation_reference=f"DOC-{transaction_format}",
        issuer="Marex", currency="EUR", notional=1_000_000,
        external_ref=f"{mandate_id}-{index}")


def test_l_agregat_client_signale_les_mandats_aux_habitudes_opposees():
    session = _session()
    client = Client(entity_id=1, name="Client réel", data_origin="native")
    session.add(client)
    session.flush()
    note = ClientMandate(entity_id=1, client_id=client.id, name="Fonds Notes",
                         data_origin="native")
    swap = ClientMandate(entity_id=1, client_id=client.id, name="Compte Swaps",
                         data_origin="native")
    session.add_all([note, swap])
    session.flush()
    for index in range(3):
        session.add(_history(
            client.id, note.id, index, transaction_format="EMTN",
            instrument_family="Note", payoff_family="Autocall"))
        session.add(_history(
            client.id, swap.id, index, transaction_format="OTC",
            instrument_family="Swap", payoff_family="Swap"))
    session.commit()

    profile = client_intelligence(session, client.id, asof=date(2026, 9, 1))

    assert profile["behaviour"]["n_trades"] == 6
    assert {row["name"]: row["behaviour"]["n_trades"]
            for row in profile["per_mandate"]} == {
                "Fonds Notes": 3, "Compte Swaps": 3}
    assert {row["key"] for row in profile["mandate_divergences"]} >= {
        "transaction_formats", "instrument_families", "payoff_families"}

    scoped = client_intelligence(
        session, client.id, mandate_id=note.id, asof=date(2026, 9, 1))
    assert scoped["scope"]["kind"] == "mandate"
    assert scoped["behaviour"]["transaction_formats"] == [("EMTN", 3)]
    format_habit = next(row for row in scoped["habits"]
                        if row["key"] == "transaction_format")
    assert format_habit["coverage_count"] == 3
    assert format_habit["values"][0]["share"] == 1.0
    assert len(format_habit["values"][0]["evidence"]) == 3


def test_un_client_reel_exclut_les_deals_uat_par_defaut():
    session = _session()
    client = Client(entity_id=1, name="Client réel", data_origin="native")
    session.add(client)
    session.flush()
    session.add_all([
        Deal(reference="DEAL-REAL", entity_id=1, user_id=1,
             client_id=client.id, trade_date="2026-01-15",
             product_type="Autocall", nominal=1_000_000),
        Deal(reference="DEAL-UAT", entity_id=1, user_id=1,
             client_id=client.id, uat_batch_id=99, trade_date="2026-02-15",
             product_type="Phoenix", nominal=2_000_000),
    ])
    session.commit()

    profile = client_intelligence(session, client.id, asof=date(2026, 9, 1))
    assert profile["analysis_mode"] == "real"
    assert profile["behaviour"]["n_trades"] == 1
    assert profile["excluded_demo_count"] == 1
    assert [row["reference"] for row in profile["transactions"]] == ["DEAL-REAL"]

    diagnostic = client_intelligence(
        session, client.id, asof=date(2026, 9, 1), include_demo=True)
    assert diagnostic["behaviour"]["n_trades"] == 2


def _rfq_transaction(index, *, select_marex):
    marex_price = 98.0
    bnp_price = 99.0
    selected = "Marex" if select_marex else "BNP Paribas"
    responses = [
        {"provider": "Marex", "price": marex_price, "status": "recu",
         "is_final": True, "comparable": True, "selected": select_marex},
        {"provider": "BNP Paribas", "price": bnp_price, "status": "recu",
         "is_final": True, "comparable": True, "selected": not select_marex},
    ]
    return Transaction(
        trade_date=f"2026-0{index + 1}-10", maturity_date="2029-01-01",
        reference_date=f"2026-0{index + 1}-10", product_type="Autocall",
        currency="EUR", issuer=selected, notional=1_000_000,
        underlyings=["SX5E"], imported=False, reference=f"DEAL-{index}",
        source_id=index, rfq_provenance={
            "rfq_id": index, "reference": f"RFQ-{index}", "sens": "achat",
            "retained": {"provider": selected,
                         "price": marex_price if select_marex else bnp_price},
            "selection_reason_code": None if select_marex else "documentation",
            "responses": responses,
        })


def test_marex_peut_etre_souvent_meilleur_puis_finalement_retenu():
    transactions = [
        _rfq_transaction(0, select_marex=False),
        _rfq_transaction(1, select_marex=False),
        _rfq_transaction(2, select_marex=False),
        _rfq_transaction(3, select_marex=True),
    ]

    analysis = provider_selection_analysis(
        transactions, asof=date(2026, 9, 1))
    marex = next(row for row in analysis["providers"]
                 if row["provider"] == "Marex")

    assert marex["best"] == 4
    assert marex["best_not_selected"] == 3
    assert marex["selected"] == 1
    assert analysis["questions"][0]["provider"] == "Marex"
    assert "revalider" in analysis["questions"][0]["message"]
    # La quatrième RFQ prouve qu'il ne s'agit jamais d'une exclusion déduite.
    assert any(case["selected"] for case in marex["cases"])


def _profile_query_count(mandate_count):
    session = _session()
    client = Client(entity_id=1, name="Client volumique", data_origin="native")
    session.add(client)
    session.flush()
    for index in range(mandate_count):
        mandate = ClientMandate(
            entity_id=1, client_id=client.id, name=f"Mandat {index}",
            data_origin="native")
        session.add(mandate)
        session.flush()
        session.add(_history(
            client.id, mandate.id, index % 3,
            transaction_format="EMTN", instrument_family="Note",
            payoff_family="Autocall"))
    session.commit()

    statements = []
    engine = session.get_bind()

    def count_statement(*_args):
        statements.append(1)

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        client_intelligence(session, client.id, asof=date(2026, 9, 1))
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
    return len(statements)


def test_le_nombre_de_requetes_ne_depend_pas_du_nombre_de_mandats():
    assert _profile_query_count(20) <= _profile_query_count(1) + 1
