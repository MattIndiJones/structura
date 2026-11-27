"""Retain versioned native market preparations as append-only evidence."""

VERSION = 2
NAME = "Contextes de valorisation natifs figés"


def upgrade(conn):
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS native_valuation_contexts (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            command_key VARCHAR NOT NULL,
            product_id INTEGER NOT NULL,
            product_reference VARCHAR NOT NULL,
            fingerprint VARCHAR NOT NULL,
            context_json TEXT NOT NULL,
            received_market_fingerprint VARCHAR NOT NULL,
            received_market_json TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE (user_id, command_key)
        )
    """)
    for event in ("UPDATE", "DELETE"):
        conn.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS native_valuation_contexts_no_{event.lower()}
            BEFORE {event} ON native_valuation_contexts
            BEGIN
                SELECT RAISE(ABORT, 'Contexte de valorisation immuable');
            END
        """)
    # SQLite REPLACE can bypass a delete trigger when recursive triggers are off.
    conn.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS native_valuation_contexts_no_replace
        BEFORE INSERT ON native_valuation_contexts
        WHEN EXISTS (
            SELECT 1 FROM native_valuation_contexts
            WHERE id = NEW.id
               OR (user_id = NEW.user_id AND command_key = NEW.command_key)
        )
        BEGIN
            SELECT RAISE(ABORT, 'Contexte de valorisation immuable');
        END
    """)
