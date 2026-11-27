"""Retain and reopen native valuation inputs in the caller's transaction."""

from hashlib import sha256

from sqlalchemy import case, func
from sqlmodel import Session, select

from ..core.product.native_market import NativeMarket, NativeValuationContext
from ..core.valuation_context import canonical_json
from ..db.models import NativeValuationContextRecord, ProductRecord, User
from .product_repository import ProductError, load_product, lock_command_actor, owned_record


def _read_context(payload: str) -> NativeValuationContext:
    try:
        return NativeValuationContext.model_validate_json(payload)
    except ValueError as exc:
        raise ProductError("NATIVE_CONTEXT_INVALID", "Le contexte de valorisation et son empreinte sont incohérents.") from exc


def _verify_schedule(session: Session, context: NativeValuationContext) -> None:
    product = load_product(session, context.product_id, terms_version=context.terms_version,
                           allow_native=True)
    schedule = product.native_schedule
    if schedule is None or (schedule.fingerprint, schedule.terms_fingerprint, schedule.instrument_type) != (
        context.schedule_fingerprint, context.terms_fingerprint, context.instrument_type,
    ):
        raise ProductError("NATIVE_CONTEXT_SCHEDULE_MISMATCH", "Le contexte ne correspond pas à l’échéancier figé.")


def _restore(session: Session, row: NativeValuationContextRecord, record: ProductRecord) -> NativeValuationContext:
    if row.product_reference != record.reference:
        raise ProductError("NATIVE_CONTEXT_NOT_FOUND", "Contexte de valorisation introuvable.", 404)
    context = _read_context(row.context_json)
    if (context.product_id, context.fingerprint) != (row.product_id, row.fingerprint):
        raise ProductError("NATIVE_CONTEXT_INVALID", "Les références du contexte archivé sont incohérentes.")
    if sha256(row.received_market_json.encode("utf-8")).hexdigest() != row.received_market_fingerprint:
        raise ProductError("NATIVE_CONTEXT_INVALID", "L’empreinte du jeu de marché reçu est incohérente.")
    _verify_schedule(session, context)
    return context


def _context_command(session: Session, user: User, command_key: str) -> NativeValuationContextRecord | None:
    return session.exec(select(NativeValuationContextRecord).where(
        NativeValuationContextRecord.user_id == user.id,
        NativeValuationContextRecord.command_key == command_key,
    )).first()


def prior_native_context(session: Session, record: ProductRecord, *, user: User,
                         command_key: str, terms_version: int) -> NativeValuationContext | None:
    row = _context_command(session, user, command_key)
    if row is None:
        return None
    if (row.product_id, row.product_reference) != (record.id, record.reference):
        raise ProductError("NATIVE_CONTEXT_COMMAND_CONFLICT", "Cette clé de commande désigne un autre contexte.")
    context = _restore(session, row, record)
    if context.terms_version != terms_version:
        raise ProductError("NATIVE_CONTEXT_COMMAND_CONFLICT", "Cette clé de commande désigne une autre version de termes.")
    return context


def store_native_context(
    session: Session, *, user: User, command_key: str, context: NativeValuationContext,
    received_market: NativeMarket,
) -> int:
    if context.product_id is None or context.terms_version is None:
        raise ProductError("NATIVE_CONTEXT_SCHEDULE_MISMATCH", "Le contexte concerne un brouillon non conservé.")
    lock_command_actor(session, user)
    record = owned_record(session, context.product_id, user, right="prepare")
    context_json = canonical_json(context.model_dump(mode="json"))
    context = _read_context(context_json)

    existing = _context_command(session, user, command_key)
    if existing is not None:
        if (existing.product_id, existing.product_reference, existing.fingerprint) != (
            context.product_id, record.reference, context.fingerprint,
        ):
            raise ProductError("NATIVE_CONTEXT_COMMAND_CONFLICT", "Cette clé de commande désigne un autre contexte.")
        _restore(session, existing, record)
        return existing.id

    _verify_schedule(session, context)
    received_market_json = canonical_json(received_market.model_dump(mode="json"))
    row = NativeValuationContextRecord(
        user_id=user.id, command_key=command_key, product_id=context.product_id,
        product_reference=record.reference, fingerprint=context.fingerprint,
        context_json=context_json,
        received_market_fingerprint=sha256(received_market_json.encode("utf-8")).hexdigest(),
        received_market_json=received_market_json,
    )
    session.add(row)
    session.flush()
    return row.id


def load_native_context(session: Session, product_id: int, context_id: int, *, user: User) -> NativeValuationContext:
    record = owned_record(session, product_id, user)
    row = session.get(NativeValuationContextRecord, context_id)
    if row is None or row.product_id != product_id:
        raise ProductError("NATIVE_CONTEXT_NOT_FOUND", "Contexte de valorisation introuvable.", 404)
    return _restore(session, row, record)


def list_native_contexts(
    session: Session, record: ProductRecord, *, terms_version: int, limit: int, offset: int,
) -> list[tuple[int, NativeValuationContext]]:
    payload = NativeValuationContextRecord.context_json
    stored_version = case((func.json_valid(payload), func.json_extract(payload, "$.terms_version")),
                          else_=terms_version)
    rows = session.exec(select(NativeValuationContextRecord).where(
        NativeValuationContextRecord.product_id == record.id,
        NativeValuationContextRecord.product_reference == record.reference,
        stored_version == terms_version,
    ).order_by(NativeValuationContextRecord.id.desc()).offset(offset).limit(limit)).all()
    return [(row.id, _restore(session, row, record)) for row in rows]
