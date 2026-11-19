"""Numbered schema migrations and the version they leave behind (P1-7, D3).

Before this package, every startup replayed some six hundred lines of
conditional ALTER TABLE: nothing said which state a database was in, nothing
refused a database written by a newer version, and a change of two steps
could stop halfway. Now:

- each migration is a module `mNNNN_<name>.py` of this package, numbered
  without gaps, applied once per database and recorded in `schema_migrations`
  (version, name, fingerprint of its source, date, duration);
- migration 1 is the schema as it stood on 19/11/2026, frozen;
- a later migration runs in ONE transaction, DDL included: it is applied
  entirely or not at all. It receives the connection and must not commit;
- a migration that rebuilds a table declares FOREIGN_KEYS_OFF: the runner
  suspends the constraint, as SQLite requires for such a rebuild, then checks
  every reference before committing;
- before raising an existing database to a newer version, the runner copies
  it to `backups/migrations/` (the last three copies are kept);
- a database whose version is beyond what this code knows is refused: the
  code would read columns it does not understand.

Every migration runs after create_all(), which lays the current tables on a
fresh database: a migration checks before it alters, and finds nothing to do
on a table created already in its final shape.
"""
from __future__ import annotations

import hashlib
import importlib
import logging
import pkgutil
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType

from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLE = "schema_migrations"
# Tables that describe the schema rather than the business: an installation
# check that looks for business rows ignores them (hybrid/business.py).
BOOKKEEPING_TABLES = frozenset({"app_migrations", TABLE})
BACKUPS_KEPT = 3
_MODULE_NAME = re.compile(r"^m(\d{4})_[a-z0-9_]+$")


class SchemaTooNew(RuntimeError):
    """The database was migrated by a newer version of Structura."""


class MigrationError(RuntimeError):
    """A migration could not be applied; the database is left as it was."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    module: ModuleType
    checksum: str
    transactional: bool = True
    foreign_keys_off: bool = False


def fingerprint(module: ModuleType) -> str:
    """SHA-256 of the migration's source and of the modules frozen with it."""
    digest = hashlib.sha256()
    # Relative names: the package is "app" under run.py, "backend.app" under pytest.
    paths = [module.__file__, *(importlib.import_module(name, module.__package__).__file__
                                for name in getattr(module, "FROZEN_WITH", ()))]
    for path in paths:
        digest.update(Path(path).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def migration_from(module: ModuleType) -> Migration:
    return Migration(version=int(module.VERSION), name=str(module.NAME), module=module,
                     checksum=fingerprint(module), transactional=getattr(module, "TRANSACTIONAL", True),
                     foreign_keys_off=getattr(module, "FOREIGN_KEYS_OFF", False))


def discover(package: ModuleType | None = None) -> list[Migration]:
    package = package or sys.modules[__name__]
    found = []
    for info in pkgutil.iter_modules(package.__path__):
        match = _MODULE_NAME.match(info.name)
        if not match:
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        if int(getattr(module, "VERSION", -1)) != int(match.group(1)):
            raise MigrationError(f"{info.name} : VERSION ne correspond pas au numéro du fichier.")
        found.append(migration_from(module))
    found.sort(key=lambda m: m.version)
    if [m.version for m in found] != list(range(1, len(found) + 1)):
        raise MigrationError("Les migrations doivent être numérotées 1, 2, 3… sans trou ni doublon.")
    return found


def _ensure_table(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at DATETIME NOT NULL,
            duration_ms INTEGER NOT NULL
        )"""))


def applied(conn) -> dict[int, dict]:
    if not conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"), {"t": TABLE}).first():
        return {}
    rows = conn.execute(text(f"SELECT version, name, checksum, applied_at FROM {TABLE}")).mappings()
    return {row["version"]: dict(row) for row in rows}


def status(engine, migrations: list[Migration] | None = None) -> dict:
    """Read-only: where the database stands against what this code knows."""
    known = discover() if migrations is None else migrations
    with engine.connect() as conn:
        done = applied(conn)
    expected = known[-1].version if known else 0
    current = max(done, default=0)
    return {
        "version": current,
        "expected": expected,
        "pending": [m.version for m in known if m.version not in done],
        "modified": [m.version for m in known if m.version in done and done[m.version]["checksum"] != m.checksum],
        "unknown": sorted(v for v in done if v > expected),
    }


def check_compatible(engine, migrations: list[Migration] | None = None) -> dict:
    state = status(engine, migrations)
    if state["unknown"]:
        raise SchemaTooNew(
            f"La base est au schéma v{state['version']}, et cette version de Structura s'arrête à "
            f"v{state['expected']}. Démarrez la version de Structura qui l'a migrée ; aucune modification appliquée.")
    return state


def _record(conn, migration: Migration, started: float) -> None:
    conn.execute(text(f"INSERT INTO {TABLE} (version, name, checksum, applied_at, duration_ms) "
                      "VALUES (:v, :n, :c, :a, :d)"),
                 {"v": migration.version, "n": migration.name, "c": migration.checksum,
                  "a": datetime.utcnow().isoformat(sep=" "), "d": int((time.perf_counter() - started) * 1000)})


def _apply_transactional(engine, migration: Migration) -> None:
    started = time.perf_counter()
    with engine.connect() as conn:
        driver = conn.connection.driver_connection
        previous = driver.isolation_level
        # pysqlite only opens a transaction before DML, so an ALTER TABLE would
        # commit on its own. The transaction is therefore opened explicitly.
        driver.isolation_level = None
        try:
            if migration.foreign_keys_off:
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                migration.module.upgrade(conn)
                if not driver.in_transaction:
                    raise MigrationError(f"Migration {migration.version} : elle a validé sa transaction elle-même.")
                if migration.foreign_keys_off:
                    broken = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                    if broken:
                        raise MigrationError(f"Migration {migration.version} : {len(broken)} référence(s) rompue(s), "
                                             f"par exemple {tuple(broken[0])}.")
                _record(conn, migration, started)
                conn.exec_driver_sql("COMMIT")
            except BaseException:
                if driver.in_transaction:
                    conn.exec_driver_sql("ROLLBACK")
                raise
        finally:
            if migration.foreign_keys_off:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            driver.isolation_level = previous


def _apply_legacy(engine, migration: Migration) -> None:
    started = time.perf_counter()
    migration.module.upgrade(engine)
    with engine.begin() as conn:
        _record(conn, migration, started)


def backup(engine, directory: Path, version: int) -> Path | None:
    """Consistent copy of the database through SQLite's backup API."""
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"structura-v{version:04d}-{datetime.now():%Y%m%d-%H%M%S}.db"
    source = sqlite3.connect(database)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    for old in sorted(directory.glob("structura-v*.db"))[:-BACKUPS_KEPT]:
        old.unlink()
    return target


def upgrade(engine, *, migrations: list[Migration] | None = None, backup_dir: Path | None = None) -> dict:
    """Apply what the database lacks, in order; refuse a database from the future."""
    known = discover() if migrations is None else migrations
    with engine.begin() as conn:
        _ensure_table(conn)
    state = check_compatible(engine, known)
    for version in state["modified"]:
        logger.warning("Migration %s modifiée depuis son application : son empreinte ne correspond plus.", version)
    pending = [m for m in known if m.version in state["pending"]]
    if pending and min(m.version for m in pending) < state["version"]:
        raise MigrationError(f"Migrations antérieures absentes d'une base en v{state['version']} : "
                             f"{[m.version for m in pending]}. Aucune modification appliquée.")
    copy = None
    if pending and state["version"] >= 1 and backup_dir is not None:
        copy = backup(engine, backup_dir, state["version"])
        logger.info("Copie de la base avant migration : %s", copy)
    for migration in pending:
        logger.info("Migration %s — %s", migration.version, migration.name)
        try:
            (_apply_transactional if migration.transactional else _apply_legacy)(engine, migration)
        except MigrationError:
            raise
        except Exception as exc:
            raise MigrationError(f"Migration {migration.version} ({migration.name}) refusée : {exc}") from exc
    return {"from": state["version"], "to": known[-1].version if known else 0,
            "applied": [m.version for m in pending], "backup": str(copy) if copy else None}
