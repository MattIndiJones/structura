"""Freeze organization ownership when upgrading formerly personal collections."""
from sqlalchemy import text


def migrate_organization_scopes(conn):
    for table in ("portfolios", "amc_studies"):
        columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        if columns and "entity_id" not in columns:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN entity_id INTEGER REFERENCES entities(id)"))
            conn.execute(text(f"UPDATE {table} SET entity_id = (SELECT entity_id FROM users WHERE users.id = {table}.user_id)"))
