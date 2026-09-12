#!/usr/bin/env python3
"""Offline, backed-up SQLite schema rebuild against current SQLModel metadata.

Without --apply the source is opened read-only and the rebuilt copy is only
validated.  The live file is never opened through the application engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid

from sqlalchemy import create_engine
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import backend.app.db.models  # noqa: E402,F401 - register every table


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {name: sql for name, sql in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")}


def _column_default(table: str, column: str):
    metadata_table = SQLModel.metadata.tables.get(table)
    if metadata_table is None:
        raise RuntimeError(f"Valeur absente sans modèle : {table}.{column}")
    model_column = metadata_table.c[column]
    default = model_column.default
    if default is None:
        if model_column.nullable:
            return None
        raise RuntimeError(f"Aucun défaut pour la colonne obligatoire {table}.{column}")
    value = default.arg
    if callable(value):
        try:
            return value()
        except TypeError:
            return value(None)
    return value


def rebuild(source: Path, *, apply: bool = False) -> dict:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    backup = None
    if apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = source.with_name(f"{source.stem}.backup-{stamp}{source.suffix}")
        shutil.copy2(source, backup)
        target = source.with_name(f".{source.name}.rebuild-{uuid.uuid4().hex}.tmp")
        cleanup_target = True
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="structura-schema-")
        target = Path(temp_dir.name) / source.name
        cleanup_target = False

    try:
        engine = create_engine(f"sqlite:///{target}")
        SQLModel.metadata.create_all(engine)
        engine.dispose()
        src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            dst.execute("PRAGMA foreign_keys=OFF")
            dst.execute("CREATE TABLE IF NOT EXISTS app_migrations ("
                        "key TEXT PRIMARY KEY, applied_at DATETIME NOT NULL "
                        "DEFAULT CURRENT_TIMESTAMP)")
            source_tables = _tables(src)
            target_tables = _tables(dst)
            unknown = sorted(set(source_tables) - set(target_tables))
            # Historical tables may no longer have an ORM class.  A schema
            # repair must preserve them byte-for-byte at the logical level,
            # never silently turn code retirement into data deletion.
            for table in unknown:
                create_sql = source_tables[table]
                if not create_sql:
                    raise RuntimeError(f"DDL introuvable pour la table historique {table}")
                dst.execute(create_sql)
                for (index_sql,) in src.execute(
                        "SELECT sql FROM sqlite_master WHERE type='index' "
                        "AND tbl_name=? AND sql IS NOT NULL", (table,)):
                    dst.execute(index_sql)
            target_tables = _tables(dst)
            counts = {}
            for table in source_tables:
                source_columns = [row[1] for row in src.execute(
                    f"PRAGMA table_info({_q(table)})")]
                target_info = list(dst.execute(f"PRAGMA table_info({_q(table)})"))
                target_columns = [row[1] for row in target_info]
                columns = target_columns
                if not columns:
                    continue
                names = ",".join(_q(column) for column in columns)
                placeholders = ",".join("?" for _ in columns)
                source_names = ",".join(_q(column) for column in source_columns)
                raw_rows = src.execute(
                    f"SELECT {source_names} FROM {_q(table)}").fetchall()
                source_index = {column: i for i, column in enumerate(source_columns)}
                rows = []
                for raw in raw_rows:
                    converted = []
                    for column in columns:
                        if column in source_index:
                            value = raw[source_index[column]]
                            if value is None:
                                target_row = next(r for r in target_info if r[1] == column)
                                if target_row[3]:
                                    value = _column_default(table, column)
                        else:
                            value = _column_default(table, column)
                        converted.append(value)
                    rows.append(tuple(converted))
                if rows:
                    dst.executemany(
                        f"INSERT INTO {_q(table)} ({names}) VALUES ({placeholders})", rows)
                counts[table] = len(rows)
            dst.execute(
                "INSERT OR IGNORE INTO app_migrations(key) VALUES (?)",
                ("schema_rebuild_current_metadata_v1",),
            )
            dst.commit()
            dst.execute("PRAGMA foreign_keys=ON")
            violations = dst.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    f"{len(violations)} violation(s) de clé étrangère après reconstruction")
            for table, expected in counts.items():
                actual = dst.execute(
                    f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]
                valid_count = (actual >= expected if table == "app_migrations"
                               else actual == expected)
                if not valid_count:
                    raise RuntimeError(
                        f"Comptage divergent pour {table}: {expected} -> {actual}")
        finally:
            src.close()
            dst.close()
        if apply:
            os.replace(target, source)
            cleanup_target = False
        return {
            "validated": True, "applied": apply, "tables": len(counts),
            "rows": sum(counts.values()), "backup": str(backup) if backup else None,
        }
    finally:
        if cleanup_target and target.exists():
            target.unlink()
        if not apply:
            temp_dir.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--apply", action="store_true",
                        help="Remplace la base après sauvegarde et validation")
    args = parser.parse_args()
    result = rebuild(args.database, apply=args.apply)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
