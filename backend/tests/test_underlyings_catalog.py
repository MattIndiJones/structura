"""Chantier A — le référentiel de sous-jacents devient administrable.

La liste vivait dans un fichier JavaScript : seul un développeur pouvait y
ajouter un titre, et il fallait un rebuild. Elle est désormais en base, et
l'ajout passe par une recherche Yahoo puis une vérification que le ticker
répond — un ticker muet inscrit en silence ne se découvre qu'au moment de
pricer, c'est-à-dire trop tard.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import admin as admin_api
from backend.app.db import database as db
from backend.app.db.models import Underlying

ADMIN = SimpleNamespace(id=1, entity_id=1, role="admin")


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture
def s():
    with _session() as session:
        yield session


@pytest.fixture
def yahoo_ok(monkeypatch):
    """Yahoo répond : un titre coté, en euros."""
    monkeypatch.setattr(admin_api, "probe_ticker", lambda t: {
        "ok": True, "last_close": 84.71, "last_date": "2026-08-27",
        "points": 24, "ccy": "EUR"})


def test_le_semis_reprend_la_liste_du_front(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    db._seed_underlyings()
    db._seed_underlyings()   # deux fois : le semis ne doit rien dupliquer
    with Session(engine) as session:
        rows = session.exec(select(Underlying)).all()
    assert len(rows) == 65
    # Un ticker peut figurer dans deux groupes, comme dans le fichier d'origine.
    bnp = [u.group_name for u in rows if u.ticker == "BNP.PA"]
    assert len(bnp) == 2, bnp


def test_ajouter_un_titre_verifie_qu_il_repond(s, yahoo_ok):
    row = admin_api.create_underlying(
        admin_api.UnderlyingCreate(ticker="UCG.MI", label="UniCredit",
                                    group="Actions IT (FTSE MIB)"),
        ADMIN, s)
    assert row["ticker"] == "UCG.MI"
    # La devise vient de Yahoo, pas d'une déduction sur le suffixe.
    assert row["ccy"] == "EUR"
    assert row["probe"]["last_close"] == 84.71


def test_un_ticker_muet_est_refuse(s, monkeypatch):
    monkeypatch.setattr(admin_api, "probe_ticker",
                        lambda t: {"ok": False, "error": f"Aucune cotation pour « {t} »."})
    with pytest.raises(HTTPException) as exc:
        admin_api.create_underlying(
            admin_api.UnderlyingCreate(ticker="ZZZZ.XX", group="Autres"), ADMIN, s)
    assert exc.value.status_code == 422
    assert "ZZZZ.XX" in exc.value.detail
    assert s.exec(select(Underlying)).all() == []


def test_le_meme_ticker_peut_vivre_dans_deux_groupes(s, yahoo_ok):
    admin_api.create_underlying(
        admin_api.UnderlyingCreate(ticker="BNP.PA", label="BNP Paribas",
                                    group="Banques"), ADMIN, s)
    admin_api.create_underlying(
        admin_api.UnderlyingCreate(ticker="BNP.PA", label="BNP Paribas",
                                    group="Actions FR (CAC)"), ADMIN, s)
    assert len(s.exec(select(Underlying)).all()) == 2


def test_le_meme_couple_ticker_groupe_est_refuse(s, yahoo_ok):
    admin_api.create_underlying(
        admin_api.UnderlyingCreate(ticker="BNP.PA", group="Banques"), ADMIN, s)
    with pytest.raises(HTTPException) as exc:
        admin_api.create_underlying(
            admin_api.UnderlyingCreate(ticker="BNP.PA", group="Banques"), ADMIN, s)
    assert exc.value.status_code == 409


def test_la_liste_sort_triee_par_groupe_puis_libelle(s, yahoo_ok):
    for ticker, label, groupe in [("ZZZ", "Zebra", "Banques"),
                                   ("AAA", "Alpha", "Luxe"),
                                   ("MMM", "Milieu", "Banques")]:
        admin_api.create_underlying(
            admin_api.UnderlyingCreate(ticker=ticker, label=label, group=groupe), ADMIN, s)
    rows = admin_api.list_underlyings(ADMIN, s)
    assert [(r["group"], r["label"]) for r in rows] == [
        ("Banques", "Milieu"), ("Banques", "Zebra"), ("Luxe", "Alpha")]


def test_desactiver_retire_des_menus_sans_perdre_la_ligne(s, yahoo_ok):
    row = admin_api.create_underlying(
        admin_api.UnderlyingCreate(ticker="UCG.MI", group="Banques"), ADMIN, s)
    admin_api.update_underlying(row["id"], admin_api.UnderlyingUpdate(active=False), ADMIN, s)
    restant = s.exec(select(Underlying)).one()
    assert restant.active is False
    assert restant.ticker == "UCG.MI"
