"""Immutable treatment snapshots and local execution/booking evidence."""
from sqlalchemy import text


def install_execution_guards(engine):
    if engine.dialect.name != 'sqlite':
        return
    fixed = ('rfq_id', 'entity_id', 'quote_id', 'command_key', 'request_hash',
             'snapshot_json', 'snapshot_hash', 'requested_by', 'requested_at',
             'request_source', 'request_reference')
    confirmed = ('state', 'execution_reference', 'acceptance_received_at', 'acceptance_evidence',
                 'confirmed_at', 'confirmed_by', 'confirmation_source', 'confirmation_evidence',
                 'confirmation_hash', 'written_confirmation_pending', 'bank_contact')
    different = lambda fields: ' OR '.join(f'NEW.{name} IS NOT OLD.{name}' for name in fields)
    with engine.begin() as connection:
        connection.execute(text(f'''CREATE TRIGGER IF NOT EXISTS rfq_execution_snapshot_immutable
            BEFORE UPDATE ON rfq_execution_agreements WHEN {different(fixed)}
            BEGIN SELECT RAISE(ABORT, 'RFQ execution snapshot is immutable'); END'''))
        connection.execute(text(f'''CREATE TRIGGER IF NOT EXISTS rfq_execution_confirmation_immutable
            BEFORE UPDATE ON rfq_execution_agreements
            WHEN OLD.state = 'CONFIRMED' AND ({different(confirmed)})
            BEGIN SELECT RAISE(ABORT, 'RFQ execution confirmation is immutable'); END'''))
        connection.execute(text('''CREATE TRIGGER IF NOT EXISTS rfq_execution_no_delete
            BEFORE DELETE ON rfq_execution_agreements
            BEGIN SELECT RAISE(ABORT, 'RFQ execution evidence cannot be deleted'); END'''))
        for operation in ('UPDATE', 'DELETE'):
            connection.execute(text(f'''CREATE TRIGGER IF NOT EXISTS rfq_execution_booking_no_{operation.lower()}
                BEFORE {operation} ON rfq_execution_bookings
                BEGIN SELECT RAISE(ABORT, 'RFQ execution booking is immutable'); END'''))
