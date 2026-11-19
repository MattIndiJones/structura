"""Numbered migrations and schema version (P1-7, D3).

The runner is tested on throwaway migrations; the frozen baseline on the real
schema. Every engine is a file, as in production: the copy taken before an
upgrade needs one, and SQLite's transactional DDL behaves on a file as it does
on the desk.
"""
import logging
import sqlite3
import types

import pytest
from sqlalchemy import create_engine, event, text
from sqlmodel import SQLModel

from backend.app.db import database, migrations  # noqa: F401  (database registers every table)

# Fingerprint of migrations/m0001_baseline.py and of the four helper modules
# frozen with it. If this test fails, the baseline was edited: revert, and
# write the change as a new migration m0002_… instead.
BASELINE_FINGERPRINT = "58a3580ab120ff8989495d740465f44ba77a047803af8b762c6e8cfbf0d2f8b9"


def _engine(path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    return engine


def _fake(tmp_path, version, upgrade, *, transactional=True, foreign_keys_off=False, source=None):
    path = tmp_path / f"m{version:04d}_essai.py"
    path.write_text(source or f"# migration d'essai {version}\n", encoding="utf-8")
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    module.VERSION, module.NAME, module.upgrade = version, f"Essai {version}", upgrade
    module.TRANSACTIONAL, module.FOREIGN_KEYS_OFF = transactional, foreign_keys_off
    return migrations.migration_from(module)


def _base(tmp_path):
    """A database already at v1, with one business table."""
    engine = _engine(tmp_path / "structura.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE books (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO books (name) VALUES ('Book EUR')"))
    first = _fake(tmp_path, 1, lambda engine: None, transactional=False)
    migrations.upgrade(engine, migrations=[first])
    return engine, first


def _columns(engine, table):
    with engine.connect() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def _versions(engine):
    with engine.connect() as conn:
        return sorted(migrations.applied(conn))


def _schema(engine):
    with engine.connect() as conn:
        return sorted(conn.execute(text(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            f"AND name != '{migrations.TABLE}'")).all())


# ── The migrations this code ships ──────────────────────────────────────

def test_les_migrations_livrees_sont_numerotees_sans_trou():
    known = migrations.discover()
    assert [m.version for m in known] == list(range(1, len(known) + 1))
    baseline = known[0]
    assert baseline.name == "Base figée au 19/11/2026" and baseline.transactional is False


def test_la_base_figee_ne_change_plus():
    baseline = migrations.discover()[0]
    assert baseline.checksum == BASELINE_FINGERPRINT, (
        "migrations/m0001_baseline.py ou un module figé avec elle a changé. La base du 19/11/2026 ne "
        "se modifie pas : annulez la modification et écrivez une nouvelle migration m0002_….")


def test_une_base_neuve_recoit_la_v1_une_seule_fois(tmp_path):
    engine = _engine(tmp_path / "structura.db")
    SQLModel.metadata.create_all(engine)
    report = migrations.upgrade(engine)
    assert report["from"] == 0 and report["applied"] == [1] and report["backup"] is None
    assert migrations.upgrade(engine)["applied"] == []
    state = migrations.status(engine)
    assert state["version"] == state["expected"] and state["pending"] == [] and state["modified"] == []


def test_une_installation_anterieure_passe_en_v1_sans_changer_de_schema(tmp_path):
    # Before P1-7 a database was brought up to date at every start, without
    # any version. Its first start now records v1 and alters nothing.
    engine = _engine(tmp_path / "structura.db")
    SQLModel.metadata.create_all(engine)
    migrations.discover()[0].module.upgrade(engine)
    before = _schema(engine)
    assert migrations.upgrade(engine)["applied"] == [1]
    assert _schema(engine) == before
    assert _versions(engine) == [1]


def test_une_base_d_une_version_plus_recente_est_refusee_intacte(tmp_path):
    engine, first = _base(tmp_path)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {migrations.TABLE} VALUES (2, 'Future', 'x', '2027-01-01', 1)"))
    before = _schema(engine)
    with pytest.raises(migrations.SchemaTooNew, match="schéma v2.*s'arrête à v1"):
        migrations.upgrade(engine, migrations=[first])
    assert _schema(engine) == before


def test_init_db_refuse_une_base_du_futur_avant_toute_ecriture(monkeypatch, tmp_path):
    engine = _engine(tmp_path / "structura.db")
    with engine.begin() as conn:
        migrations._ensure_table(conn)
        conn.execute(text(f"INSERT INTO {migrations.TABLE} VALUES (999, 'Future', 'x', '2027-01-01', 1)"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_require_simulation_bootstrap", lambda: None)
    with pytest.raises(migrations.SchemaTooNew):
        database.init_db()
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert tables == {migrations.TABLE}      # create_all never ran


# ── A later migration: all or nothing ───────────────────────────────────

def test_une_migration_s_applique_entiere_et_s_enregistre(tmp_path):
    engine, first = _base(tmp_path)

    def upgrade(conn):
        conn.execute(text("ALTER TABLE books ADD COLUMN currency TEXT"))
        conn.execute(text("UPDATE books SET currency = 'EUR'"))

    second = _fake(tmp_path, 2, upgrade)
    report = migrations.upgrade(engine, migrations=[first, second])
    assert report["applied"] == [2] and report["from"] == 1 and report["to"] == 2
    with engine.connect() as conn:
        assert conn.execute(text("SELECT currency FROM books")).scalar_one() == "EUR"
        row = conn.execute(text(f"SELECT name, checksum FROM {migrations.TABLE} WHERE version=2")).one()
    assert row == ("Essai 2", second.checksum)


def test_une_migration_en_echec_ne_laisse_rien_meme_en_ddl(tmp_path):
    engine, first = _base(tmp_path)

    def upgrade(conn):
        conn.execute(text("ALTER TABLE books ADD COLUMN currency TEXT"))
        conn.execute(text("CREATE TABLE ledger (id INTEGER PRIMARY KEY)"))
        raise ValueError("devise inconnue")

    with pytest.raises(migrations.MigrationError, match="Migration 2 .*devise inconnue"):
        migrations.upgrade(engine, migrations=[first, _fake(tmp_path, 2, upgrade)])
    assert "currency" not in _columns(engine, "books")
    assert not _columns(engine, "ledger")
    assert _versions(engine) == [1]


def test_une_migration_qui_valide_elle_meme_est_signalee(tmp_path):
    engine, first = _base(tmp_path)

    def upgrade(conn):
        conn.execute(text("ALTER TABLE books ADD COLUMN currency TEXT"))
        conn.commit()

    with pytest.raises(migrations.MigrationError, match="validé sa transaction elle-même"):
        migrations.upgrade(engine, migrations=[first, _fake(tmp_path, 2, upgrade)])
    assert _versions(engine) == [1]


def _rebuild(target):
    def upgrade(conn):
        conn.execute(text("CREATE TABLE owners (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO owners (id) VALUES (1)"))
        conn.execute(text(
            "CREATE TABLE books_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "owner_id INTEGER NOT NULL REFERENCES owners(id))"))
        conn.execute(text(f"INSERT INTO books_new SELECT id, name, {target} FROM books"))
        conn.execute(text("DROP TABLE books"))
        conn.execute(text("ALTER TABLE books_new RENAME TO books"))
    return upgrade


def test_une_reconstruction_de_table_suspend_puis_verifie_les_references(tmp_path):
    engine, first = _base(tmp_path)
    second = _fake(tmp_path, 2, _rebuild(1), foreign_keys_off=True)
    migrations.upgrade(engine, migrations=[first, second])
    assert "owner_id" in _columns(engine, "books")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_une_reconstruction_qui_rompt_une_reference_est_annulee(tmp_path):
    engine, first = _base(tmp_path)
    second = _fake(tmp_path, 2, _rebuild(42), foreign_keys_off=True)
    with pytest.raises(migrations.MigrationError, match="référence\\(s\\) rompue\\(s\\)"):
        migrations.upgrade(engine, migrations=[first, second])
    assert _columns(engine, "books") == {"id", "name"}
    assert not _columns(engine, "owners")
    assert _versions(engine) == [1]
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_une_migration_manquante_avant_une_appliquee_est_refusee(tmp_path):
    engine, first = _base(tmp_path)
    third = _fake(tmp_path, 3, lambda conn: None)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {migrations.TABLE} VALUES (3, 'Essai 3', :c, '2026-11-19', 1)"),
                     {"c": third.checksum})
    with pytest.raises(migrations.MigrationError, match="antérieures absentes"):
        migrations.upgrade(engine, migrations=[first, _fake(tmp_path, 2, lambda conn: None), third])


def test_une_migration_modifiee_apres_coup_est_signalee(tmp_path, caplog):
    engine, first = _base(tmp_path)
    edited = _fake(tmp_path, 1, lambda engine: None, transactional=False, source="# modifiée\n")
    with caplog.at_level(logging.WARNING, logger="backend.app.db.migrations"):
        migrations.upgrade(engine, migrations=[edited])
    assert migrations.status(engine, [edited])["modified"] == [1]
    assert "Migration 1 modifiée" in caplog.text


def test_la_decouverte_refuse_une_numerotation_trouee(tmp_path, monkeypatch):
    package = tmp_path / "essais"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for number in (1, 3):
        (package / f"m{number:04d}_essai.py").write_text(
            f"VERSION = {number}\nNAME = 'Essai'\ndef upgrade(conn):\n    pass\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    with pytest.raises(migrations.MigrationError, match="sans trou"):
        migrations.discover(importlib.import_module("essais"))


# ── The copy taken before an upgrade ────────────────────────────────────

def test_une_base_existante_est_copiee_avant_de_monter_de_version(tmp_path):
    engine, first = _base(tmp_path)
    copies = tmp_path / "backups"

    def upgrade(conn):
        conn.execute(text("DELETE FROM books"))

    report = migrations.upgrade(engine, migrations=[first, _fake(tmp_path, 2, upgrade)], backup_dir=copies)
    assert report["backup"]
    with sqlite3.connect(report["backup"]) as saved:
        assert saved.execute("SELECT name FROM books").fetchall() == [("Book EUR",)]
        assert saved.execute(f"SELECT max(version) FROM {migrations.TABLE}").fetchone() == (1,)


def test_seules_les_trois_dernieres_copies_sont_gardees(tmp_path):
    engine, _ = _base(tmp_path)
    copies = tmp_path / "backups"
    copies.mkdir()
    for day in range(1, 5):
        (copies / f"structura-v0001-2026010{day}-000000.db").write_bytes(b"")
    migrations.backup(engine, copies, 1)
    kept = sorted(p.name for p in copies.iterdir())
    assert len(kept) == 3 and "structura-v0001-20260101-000000.db" not in kept


def test_une_base_neuve_n_est_pas_copiee(tmp_path):
    engine = _engine(tmp_path / "structura.db")
    first = _fake(tmp_path, 1, lambda engine: None, transactional=False)
    assert migrations.upgrade(engine, migrations=[first], backup_dir=tmp_path / "backups")["backup"] is None
    assert not (tmp_path / "backups").exists()


# ── What the installation checks and /health see ────────────────────────

def test_la_table_de_version_ne_compte_pas_comme_donnee_metier():
    assert migrations.TABLE in migrations.BOOKKEEPING_TABLES
    assert "app_migrations" in migrations.BOOKKEEPING_TABLES


def test_health_donne_la_version_du_schema(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import main
    engine = _engine(tmp_path / "structura.db")
    SQLModel.metadata.create_all(engine)
    migrations.upgrade(engine)
    monkeypatch.setattr(database, "engine", engine)
    body = TestClient(main.app).get("/health").json()
    expected = migrations.discover()[-1].version
    assert body["schema"] == {"version": expected, "expected": expected}
