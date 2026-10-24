"""Durable per-actor booking intents; no successful command without its Deal."""
from sqlmodel import Session, select

from ..core.valuation_context import canonical_fingerprint
from ..db.models import BookingCommand, Deal, User
from .product_repository import ProductError, lock_command_actor


def booking_intent(session: Session, user: User, body, *, uat_batch_id=None,
                   reference_prefix=None):
    payload = body.model_dump(mode='json', exclude={'command_key'})
    digest = canonical_fingerprint({
        'booking': payload, 'entity_id': user.entity_id,
        'uat_batch_id': uat_batch_id, 'reference_prefix': reference_prefix,
    })
    # Older callers cannot express two identical independent intentions. Their
    # exact request is deduplicated; current clients always send an explicit key.
    key = body.command_key or f'legacy-booking-{digest}'
    lock_command_actor(session, user)
    command = session.exec(select(BookingCommand).where(
        BookingCommand.user_id == user.id, BookingCommand.command_key == key)).first()
    if command is not None:
        if command.entity_id != user.entity_id or command.input_hash != digest:
            raise ProductError('BOOKING_COMMAND_CONFLICT',
                'Cette commande de booking a déjà été exécutée avec un autre contenu.')
        deal = session.get(Deal, command.deal_id) if command.deal_id is not None else None
        if deal is None:
            raise ProductError('BOOKING_COMMAND_RESULT_MISSING',
                'Le résultat de ce booking est indisponible ; une revue est requise.')
        return key, digest, deal
    return key, digest, None


def stage_booking_command(session: Session, user: User, key: str, digest: str, deal: Deal):
    session.add(BookingCommand(user_id=user.id, entity_id=user.entity_id,
        command_key=key, input_hash=digest, deal_id=deal.id))
    session.flush()
