"""Additive product links; called only by the normal application migration."""
from sqlalchemy import text


def migrate_product_links(conn):
    product_columns = {
        row[1] for row in conn.execute(text('PRAGMA table_info("products")'))
    }
    if product_columns and "uat_batch_id" not in product_columns:
        conn.execute(text(
            'ALTER TABLE "products" ADD COLUMN "uat_batch_id" INTEGER '
            'REFERENCES uat_generation_batches(id)'))
    if product_columns and "listed" not in product_columns:
        # Products predating internal workflow creation were all explicitly
        # retained from the Pricer, so they remain visible after migration.
        conn.execute(text(
            'ALTER TABLE "products" ADD COLUMN "listed" BOOLEAN '
            'NOT NULL DEFAULT 1'))
    if product_columns:
        conn.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_products_uat_batch_id" '
            'ON "products" (uat_batch_id)'))
        conn.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_products_listed" '
            'ON "products" (listed)'))
    columns = {
        "deals": {
            "product_id": "INTEGER REFERENCES products(id)",
            "product_terms_version": "INTEGER",
            "counterparty_id": "INTEGER REFERENCES counterparties(id)",
        },
        "rfq_requests": {"product_id": "INTEGER REFERENCES products(id)",
                         "product_terms_version": "INTEGER"},
        "indicatives": {"product_id": "INTEGER REFERENCES products(id)",
                        "product_terms_version": "INTEGER"},
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
    # Existing UAT rows may remain nullable, but every new durable workflow
    # object must enter through the canonical Product identity. Triggers make
    # the invariant hold even for SQL or a future endpoint that bypasses the
    # current service layer.
    for table in (
        "deals", "rfq_requests", "indicatives", "documents",
        "kid_records", "emt_records",
    ):
        exists = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"),
            {"table": table}).first()
        if not exists:
            continue
        conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS require_{table}_product_insert
            BEFORE INSERT ON {table}
            WHEN NEW.product_id IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'Product canonique requis');
            END"""))
        conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS protect_{table}_product_link
            BEFORE UPDATE OF product_id ON {table}
            WHEN NEW.product_id IS NULL OR OLD.product_id IS NOT NEW.product_id
            BEGIN
                SELECT RAISE(ABORT, 'Lien Product immuable');
            END"""))
        # Validate the PAIR, including historical versions. Existing unqualified
        # rows are preserved; no version is guessed during migration.
        for operation, suffix in (("INSERT", "insert"),
                                  ("UPDATE OF product_id, product_terms_version", "update")):
            conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS require_{table}_product_version_{suffix}
                BEFORE {operation} ON {table}
                WHEN NEW.product_id IS NULL OR NEW.product_terms_version IS NULL
                  OR NOT EXISTS (SELECT 1 FROM product_terms_versions v
                                 JOIN products p ON p.id = v.product_id
                                 WHERE v.product_id = NEW.product_id
                                   AND v.version = NEW.product_terms_version)
                BEGIN
                    SELECT RAISE(ABORT, 'Version Product canonique valide requise');
                END"""))
    conn.execute(text("""CREATE TRIGGER IF NOT EXISTS protect_products_terms_pointer
        BEFORE UPDATE OF terms_version ON products
        WHEN NEW.terms_version < OLD.terms_version
          OR NOT EXISTS (SELECT 1 FROM product_terms_versions
                         WHERE product_id = NEW.id AND version = NEW.terms_version)
        BEGIN
            SELECT RAISE(ABORT, 'Version courante Product invalide ou rétrograde');
        END"""))
    conn.execute(text("""CREATE TRIGGER IF NOT EXISTS require_product_revisions_version_insert
        BEFORE INSERT ON product_revisions
        WHEN NOT EXISTS (SELECT 1 FROM products p JOIN product_terms_versions v ON v.product_id=p.id
                         WHERE p.id=NEW.product_id AND v.version=NEW.terms_version
                           AND p.revision=NEW.revision AND p.terms_version=NEW.terms_version)
        BEGIN SELECT RAISE(ABORT, 'Révision et version Product incohérentes'); END"""))
    conn.execute(text("""CREATE TRIGGER IF NOT EXISTS require_product_calculation_runs_version_insert
        BEFORE INSERT ON product_calculation_runs
        WHEN NOT EXISTS (SELECT 1 FROM products p JOIN product_terms_versions v ON v.product_id=p.id
                         WHERE p.id=NEW.product_id AND v.version=NEW.terms_version)
        BEGIN SELECT RAISE(ABORT, 'Version Product du calcul invalide'); END"""))
    # Immutable evidence must also survive accidental writes outside services.
    for table in ("product_terms_versions", "product_revisions", "product_calculation_runs"):
        exists = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"),
            {"table": table}).first()
        if not exists:
            continue
        conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS protect_{table}_update
            BEFORE UPDATE ON {table} BEGIN
            SELECT RAISE(ABORT, 'Historique produit immuable'); END"""))
        # Synthetic UAT Products are the sole exception to append-only
        # retention.  Their explicit batch pointer makes removal deterministic
        # while ordinary Product evidence stays structurally protected.
        conn.execute(text(f"DROP TRIGGER IF EXISTS protect_{table}_delete"))
        conn.execute(text(f"""CREATE TRIGGER protect_{table}_delete
            BEFORE DELETE ON {table}
            WHEN NOT EXISTS (
                SELECT 1 FROM products
                WHERE products.id = OLD.product_id
                  AND products.uat_batch_id IS NOT NULL
            )
            BEGIN
                SELECT RAISE(ABORT, 'Historique produit immuable');
            END"""))
