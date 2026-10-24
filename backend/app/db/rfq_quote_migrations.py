"""Additive quote revisions; historical decisions are never silently requalified."""
from sqlalchemy import text


def migrate_quote_revisions(conn):
    for table, column, declaration in (
        ('rfq_quotes', 'revision', 'INTEGER NOT NULL DEFAULT 1'),
        ('rfq_requests', 'selected_quote_revision', 'INTEGER'),
    ):
        columns = {row[1] for row in conn.execute(text(f'PRAGMA table_info({table})'))}
        if columns and column not in columns:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}'))
