"""Client Intelligence — la migration d'une base DÉJÀ déployée.

`structura.db` n'est pas versionné : la base de Philippe porte des deals, des
appels d'offres et des études réels que personne ne peut recréer. Une migration
qui « marche sur une base neuve » ne prouve donc rien du tout — create_all()
crée les tables manquantes mais n'ALTER jamais une table existante, et c'est
précisément là que se jouent les quatre colonnes ajoutées à `deals`.

Ces tests partent d'une base à l'ancien schéma, avec des lignes dedans, et
vérifient qu'après migration les colonnes existent, que les données n'ont pas
bougé, et que rejouer la migration ne casse rien.
"""
import sqlite3

from sqlalchemy import text
from sqlmodel import create_engine

from backend.app.db import database as db


# Le schéma tel qu'il existait AVANT ce module : les colonnes de rattachement
# commercial n'y sont pas. Réduit à ce que la migration touche.
DEALS_ANCIEN_SCHEMA = """
CREATE TABLE deals (
    id INTEGER PRIMARY KEY,
    reference TEXT,
    user_id INTEGER,
    entity_id INTEGER,
    contrepartie TEXT,
    devise TEXT,
    nominal REAL,
    rfq_id INTEGER
)
"""
RFQ_ANCIEN_SCHEMA = """
CREATE TABLE rfq_requests (
    id INTEGER PRIMARY KEY,
    reference TEXT,
    user_id INTEGER,
    name TEXT
)
"""
INDICATIFS_ANCIEN_SCHEMA = """
CREATE TABLE indicatives (
    id INTEGER PRIMARY KEY,
    reference TEXT,
    user_id INTEGER,
    nominal REAL
)
"""
OPPORTUNITIES_ANCIEN_SCHEMA = """
CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY,
    reference TEXT,
    entity_id INTEGER,
    owner_user_id INTEGER,
    client_id INTEGER,
    title TEXT,
    status TEXT
)
"""
MANDATES_ANCIEN_SCHEMA = """
CREATE TABLE client_mandates (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER,
    client_id INTEGER NOT NULL,
    mandate_type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    reference_currency TEXT,
    external_ref TEXT,
    notes TEXT,
    data_origin TEXT NOT NULL,
    created_by_user_id INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def _base_ancienne(tmp_path):
    """Une base au schéma d'avant, avec des lignes réelles dedans."""
    chemin = tmp_path / "structura_ancienne.db"
    conn = sqlite3.connect(chemin)
    conn.execute(DEALS_ANCIEN_SCHEMA)
    conn.execute(RFQ_ANCIEN_SCHEMA)
    conn.execute(INDICATIFS_ANCIEN_SCHEMA)
    conn.execute(OPPORTUNITIES_ANCIEN_SCHEMA)
    conn.execute(MANDATES_ANCIEN_SCHEMA)
    conn.execute(
        "INSERT INTO deals(id, reference, user_id, entity_id, contrepartie, "
        "devise, nominal, rfq_id) VALUES (1, 'DEAL-20240614-001', 3, 7, "
        "'Marex', 'EUR', 1000000.0, NULL)")
    conn.execute(
        "INSERT INTO rfq_requests(id, reference, user_id, name) "
        "VALUES (1, 'RFQ-20260827-001', 3, 'Athena Stellantis 3Y')")
    conn.execute(
        "INSERT INTO indicatives(id, reference, user_id, nominal) "
        "VALUES (1, 'IND-20260101-001', 3, 500000.0)")
    conn.execute(
        "INSERT INTO opportunities(id, reference, entity_id, owner_user_id, "
        "client_id, title, status) VALUES "
        "(1, 'OPP-20260101-001', 7, 3, 9, 'Besoin historique', 'lead')")
    conn.execute(
        "INSERT INTO client_mandates(id, entity_id, client_id, mandate_type, "
        "name, status, reference_currency, notes, data_origin, created_at, updated_at) "
        "VALUES (1, 7, 9, 'fund', 'Fonds historique', 'active', 'EUR', "
        "'Conserver cette note', 'demo', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()
    return chemin


def _colonnes(chemin, table):
    conn = sqlite3.connect(chemin)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _migrer(monkeypatch, chemin):
    moteur = create_engine(f"sqlite:///{chemin}")
    monkeypatch.setattr(db, "engine", moteur)
    db._migrate()
    return moteur


def test_les_colonnes_de_rattachement_arrivent_sur_une_base_existante(
        tmp_path, monkeypatch):
    chemin = _base_ancienne(tmp_path)
    avant = _colonnes(chemin, "deals")
    assert "client_id" not in avant          # on part bien de l'ancien schéma

    _migrer(monkeypatch, chemin)

    apres = _colonnes(chemin, "deals")
    for colonne in (
        "client_id", "mandate_id", "opportunity_id", "primary_affiliation_id",
        "client_provenance_json", "client_attribution_json",
        "transaction_format", "instrument_family", "payoff_family",
        "payoff_description", "documentation_reference", "commercial_reason",
    ):
        assert colonne in apres, f"{colonne} n'a pas été ajoutée"
    for colonne in (
        "opportunity_id", "client_id", "mandate_id", "primary_affiliation_id",
        "commercial_context_json", "transaction_format", "instrument_family",
        "payoff_family", "payoff_description", "documentation_reference",
        "selection_reason_code", "selection_reason_note",
    ):
        assert colonne in _colonnes(chemin, "rfq_requests")
    assert "opportunity_id" in _colonnes(chemin, "indicatives")
    for colonne in (
        "mandate_id", "transaction_format", "instrument_family",
        "payoff_family", "payoff_description", "data_origin",
    ):
        assert colonne in _colonnes(chemin, "opportunities")
    assert "comment" in _colonnes(chemin, "client_mandates")


def test_les_lignes_existantes_ne_bougent_pas(tmp_path, monkeypatch):
    """Le vrai risque d'une migration : perdre ou déformer ce qui était là.
    Les nouvelles colonnes arrivent à NULL — un deal booké avant ce module
    reste ce qu'il était, simplement non rattaché."""
    chemin = _base_ancienne(tmp_path)
    _migrer(monkeypatch, chemin)

    conn = sqlite3.connect(chemin)
    try:
        ligne = conn.execute(
            "SELECT reference, user_id, entity_id, contrepartie, devise, nominal, "
            "client_id, opportunity_id, primary_affiliation_id, "
            "client_provenance_json FROM deals WHERE id = 1").fetchone()
        opportunite = conn.execute(
            "SELECT reference, title, status, mandate_id, transaction_format "
            "FROM opportunities WHERE id = 1").fetchone()
        mandat = conn.execute(
            "SELECT name, notes, comment FROM client_mandates WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()

    assert ligne[:6] == ("DEAL-20240614-001", 3, 7, "Marex", "EUR", 1000000.0)
    assert ligne[6:] == (None, None, None, None)
    assert opportunite == (
        "OPP-20260101-001", "Besoin historique", "lead", None, None)
    assert mandat == (
        "Fonds historique", "Conserver cette note", "Conserver cette note")


def test_rejouer_la_migration_ne_casse_rien(tmp_path, monkeypatch):
    """init_db() tourne à chaque démarrage : la migration doit être idempotente,
    sinon le deuxième boot échoue sur un « duplicate column name »."""
    chemin = _base_ancienne(tmp_path)
    _migrer(monkeypatch, chemin)
    _migrer(monkeypatch, chemin)      # ne doit pas lever
    _migrer(monkeypatch, chemin)

    apres = _colonnes(chemin, "deals")
    assert "client_id" in apres
    conn = sqlite3.connect(chemin)
    try:
        assert conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 1
    finally:
        conn.close()


def test_les_index_de_recherche_sont_poses(tmp_path, monkeypatch):
    """§68 — les listes filtrent par client et par opportunité. Sans index, la
    montée en volume se paie sur chaque écran."""
    chemin = _base_ancienne(tmp_path)
    _migrer(monkeypatch, chemin)

    conn = sqlite3.connect(chemin)
    try:
        index = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'")}
    finally:
        conn.close()

    for attendu in ("ix_deals_client_id", "ix_deals_mandate_id", "ix_deals_opportunity_id",
                    "ix_deals_primary_affiliation_id",
                    "ix_rfq_requests_client_id", "ix_rfq_requests_mandate_id",
                    "ix_rfq_requests_opportunity_id",
                    "ix_indicatives_opportunity_id"):
        assert attendu in index, f"index {attendu} absent"


def test_un_nouveau_clone_traverse_la_sequence_de_demarrage(tmp_path, monkeypatch):
    """Nouveau clone : base vide, puis la séquence réelle de `init_db()` —
    create_all() d'abord, _migrate() ensuite.

    L'ordre compte et n'est pas décoratif : le premier bloc de `_migrate` ALTER
    `deals` sans vérifier que la table existe (il ne teste que l'absence de la
    colonne), donc il ne tient que parce que create_all l'a créée juste avant.
    Ce test fige cette séquence plutôt que de la supposer.
    """
    from sqlmodel import SQLModel
    chemin = tmp_path / "nouveau_clone.db"
    moteur = create_engine(f"sqlite:///{chemin}")
    monkeypatch.setattr(db, "engine", moteur)

    SQLModel.metadata.create_all(moteur)
    db._migrate()                     # ne doit pas lever

    colonnes = _colonnes(chemin, "deals")
    for colonne in ("client_id", "mandate_id", "opportunity_id",
                    "primary_affiliation_id", "client_provenance_json",
                    "client_attribution_json", "transaction_format"):
        assert colonne in colonnes
    # Les tables du module sont arrivées seules, sans migration.
    conn = sqlite3.connect(chemin)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    for table in ("clients", "client_mandates", "persons", "affiliations", "client_coverage",
                  "contact_coverage", "interactions", "interaction_participants",
                  "opportunities", "opportunity_participants",
                  "client_preference_statements"):
        assert table in tables, f"table {table} absente"
