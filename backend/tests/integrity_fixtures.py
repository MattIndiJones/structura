"""Parent rows that the tests' fixtures reference (P1-6, D2).

A fixture that inserts `User(entity_id=7)` or `Deal(user_id=1)` without the
Entity or User it names passes on an engine without foreign keys, and fails
on the production's. These helpers create those parents, idempotently, so a
fixture states what it relies on instead of leaning on a missing constraint.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlmodel import Session

from backend.app.db.models import Entity, UatGenerationBatch, User


# The account most fixtures book under (user_id=1, entity_id=1).
DEFAULT_ACTOR = SimpleNamespace(id=1, entity_id=1, role="user")


def ensure_entities(session: Session, *entity_ids: int | None) -> None:
    """The organisations these ids name, created if absent."""
    for entity_id in dict.fromkeys(entity_ids):
        if entity_id is not None and session.get(Entity, entity_id) is None:
            session.add(Entity(id=entity_id, name=f"Organisation {entity_id}"))
    session.flush()


def ensure_users(session: Session, *actors) -> None:
    """A User row for each actor (anything with id, and optionally entity_id,
    role, username), with its organisation, created if absent."""
    ensure_entities(session, *(getattr(actor, "entity_id", None) for actor in actors))
    for actor in actors:
        if session.get(User, actor.id) is not None:
            continue
        username = getattr(actor, "username", None) or f"utilisateur{actor.id}"
        session.add(User(id=actor.id, username=username, email=f"{username}@test.invalid",
                         password_hash="!", role=getattr(actor, "role", None) or "user",
                         entity_id=getattr(actor, "entity_id", None)))
    session.flush()


def seeded_session(engine, *actors) -> Session:
    """A session on `engine` whose actors exist, committed — the default actor
    when none is named."""
    session = Session(engine)
    ensure_users(session, *(actors or (DEFAULT_ACTOR,)))
    session.commit()
    return session


def ensure_uat_batch(session: Session, batch_id: int, user_id: int = 1) -> None:
    """The UAT generation lot a test deal is tagged with, created if absent;
    its operator and target is `user_id`, who must exist."""
    if session.get(UatGenerationBatch, batch_id) is None:
        session.add(UatGenerationBatch(
            id=batch_id, batch_key=f"uat-test-{batch_id}", created_by=user_id,
            target_user_id=user_id, mode="BOOKED_ONLY", seed=0, requested_count=1))
    session.flush()
