"""Keep the actual settlement declaration separate from contractual dates."""
from sqlalchemy import text


def migrate_settlement_evidence(conn):
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(trading_executions)"))}
    if columns and "settled_at" not in columns:
        # Historical declarations without a recorded timestamp stay unknown.
        conn.execute(text("ALTER TABLE trading_executions ADD COLUMN settled_at DATETIME"))
