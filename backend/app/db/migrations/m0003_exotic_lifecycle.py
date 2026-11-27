"""Retain native exotic lifecycle observations and decisions without updates."""

VERSION = 3
NAME = "Preuves de cycle de vie natif exotique"


def upgrade(conn):
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS native_exotic_lifecycle_entries (
            id INTEGER PRIMARY KEY, deal_id INTEGER NOT NULL, deal_reference VARCHAR NOT NULL,
            contract_version INTEGER NOT NULL, schedule_fingerprint VARCHAR NOT NULL,
            actor_id INTEGER NOT NULL, command_key VARCHAR NOT NULL, proposal_id INTEGER,
            entry_hash VARCHAR NOT NULL, entry_json TEXT NOT NULL, created_at DATETIME NOT NULL,
            UNIQUE (actor_id, command_key), UNIQUE (proposal_id)
        )
    """)
    conn.exec_driver_sql("""
        CREATE INDEX IF NOT EXISTS ix_native_exotic_lifecycle_entries_deal_id
        ON native_exotic_lifecycle_entries (deal_id)
    """)
    for event in ("UPDATE", "DELETE"):
        conn.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS native_exotic_lifecycle_no_{event.lower()}
            BEFORE {event} ON native_exotic_lifecycle_entries
            BEGIN
                SELECT RAISE(ABORT, 'Preuve de cycle de vie immuable');
            END
        """)
    conn.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS native_exotic_lifecycle_no_replace
        BEFORE INSERT ON native_exotic_lifecycle_entries
        WHEN EXISTS (
            SELECT 1 FROM native_exotic_lifecycle_entries
            WHERE id = NEW.id OR proposal_id = NEW.proposal_id
                  OR (actor_id = NEW.actor_id AND command_key = NEW.command_key)
        )
        BEGIN
            SELECT RAISE(ABORT, 'Preuve de cycle de vie immuable');
        END
    """)
