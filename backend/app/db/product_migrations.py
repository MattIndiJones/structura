"""Additive product links; called only by the normal application migration."""
from sqlalchemy import text


def migrate_product_links(conn):
    columns = {
        "deals": {
            "product_id": "INTEGER REFERENCES products(id)",
            "product_terms_version": "INTEGER",
            "counterparty_id": "INTEGER REFERENCES counterparties(id)",
        },
        "rfq_requests": {"product_id": "INTEGER REFERENCES products(id)",
                         "product_terms_version": "INTEGER"},
        "indicatives": {"product_id": "INTEGER REFERENCES products(id)"},
        "documents": {"product_id": "INTEGER REFERENCES products(id)",
                      "product_terms_version": "INTEGER"},
        "kid_records": {"product_id": "INTEGER REFERENCES products(id)",
                        "product_terms_version": "INTEGER"},
        "emt_records": {"product_id": "INTEGER REFERENCES products(id)",
                        "product_terms_version": "INTEGER"},
    }
    for table, additions in columns.items():
        existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table}")'))}
        if not existing:
            continue
        for column, declaration in additions.items():
            if column not in existing:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}'))
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "ix_{table}_product_id" ON "{table}" (product_id)'))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_deals_product ON deals(product_id) WHERE product_id IS NOT NULL"))
    # Immutable evidence must also survive accidental writes outside services.
    for table in ("product_terms_versions", "product_revisions", "product_calculation_runs"):
        exists = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"),
            {"table": table}).first()
        if not exists:
            continue
        for action in ("UPDATE", "DELETE"):
            conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS protect_{table}_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT, 'Historique produit immuable'); END"""))
