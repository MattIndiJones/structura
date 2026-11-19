"""SQLite guards for immutable transport contents and durable receipt evidence."""
from sqlalchemy import text


def seal_channel_secrets(connection) -> int:
    """Seal the channel keys stored in clear before P1-8 (S5)."""
    from ..core.secret_store import available
    from ..services.rfq_transport import SEALED_CHANNEL_PREFIX, seal_channel_secret
    if not available() or not connection.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rfq_channels'")).first():
        return 0
    rows = connection.execute(text("SELECT id, secret FROM rfq_channels WHERE secret NOT LIKE :p"),
                              {"p": SEALED_CHANNEL_PREFIX + "%"}).all()
    for channel_id, secret in rows:
        connection.execute(text("UPDATE rfq_channels SET secret=:s WHERE id=:id"),
                           {"s": seal_channel_secret(secret), "id": channel_id})
    return len(rows)


def install_transport_guards(engine):
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        seal_channel_secrets(connection)
    with engine.begin() as connection:
        for table in ("rfq_transport_inbox", "rfq_installation"):
            for operation in ("UPDATE", "DELETE"):
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable "
                    f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable RFQ transport evidence'); END"))
        fields = "id, channel_id, solicitation_id, request_message_id, sequence, kind, payload_json, payload_hash, actor_user_id, created_at"
        connection.execute(text("CREATE TRIGGER IF NOT EXISTS rfq_outbox_payload_immutable "
            f"BEFORE UPDATE OF {fields} ON rfq_transport_outbox "
            "BEGIN SELECT RAISE(ABORT, 'Immutable RFQ transport payload'); END"))
        connection.execute(text("CREATE TRIGGER IF NOT EXISTS rfq_outbox_delete_immutable "
            "BEFORE DELETE ON rfq_transport_outbox BEGIN SELECT RAISE(ABORT, 'Durable RFQ outbox'); END"))
        connection.execute(text("CREATE TRIGGER IF NOT EXISTS rfq_outbox_receipt_immutable "
            "BEFORE UPDATE OF receipt_json, signed_receipt_json, received_at ON rfq_transport_outbox "
            "WHEN OLD.receipt_json IS NOT NULL BEGIN SELECT RAISE(ABORT, 'Immutable RFQ receipt'); END"))
