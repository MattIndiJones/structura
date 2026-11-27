"""Native Product commands serialize against a real isolated SQLite file."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier, get_ident

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.api import products as products_api
from backend.app.db.migrations import m0002_native_valuation_contexts
from backend.app.db.models import (
    AuditEvent, Entity, NativeValuationContextRecord, ProductCommand,
    ProductRecord, ProductRevision, ProductTermsVersion, User,
)
from backend.app.services.product_repository import load_product
from backend.tests.test_rates_credit_mixed_reader import _native_terms
from backend.tests.test_rates_credit_rates_market import build_rates_market
from backend.tests.test_rates_credit_rates_schedule import abc_reference


@pytest.fixture
def concurrent_recipe(tmp_path, monkeypatch):
    directory = tmp_path.resolve()
    for name, value in {
        "STRUCTURA_DATA_DIR": str(directory),
        "STRUCTURA_NATIVE_WRITES_DATA_DIR": str(directory),
        "STRUCTURA_BOOTSTRAP_PROFILE": "simulation",
        "STRUCTURA_WORKSHOP_CHILD": "1",
        "STRUCTURA_NATIVE_WRITES": "1",
        "STRUCTURA_NATIVE_WRITES_USERS": "alice,bob",
    }.items():
        monkeypatch.setenv(name, value)
    engine = create_engine(
        f"sqlite:///{(directory / 'structura.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        m0002_native_valuation_contexts.upgrade(connection)
    with Session(engine) as session:
        session.add(Entity(id=1, name="Équipe de recette"))
        session.flush()
        session.add_all([
            User(id=1, entity_id=1, username="alice", email="alice@recipe.test", password_hash="fixture", role="user"),
            User(id=2, entity_id=1, username="bob", email="bob@recipe.test", password_hash="fixture", role="user"),
        ])
        session.commit()
    yield engine
    engine.dispose()


def _create_body(key):
    return products_api.NativeProductCreate(
        command_key=key, name="FRN de recette concurrente", terms=_native_terms("FRN"),
        intent={"nominal": 1_000_000, "side": "BUY"},
    )


def _terms_body(key, margin_bps):
    terms = _native_terms("FRN")
    terms["floating_leg"]["margin_bps"] = margin_bps
    return products_api.NativeProductRevision(
        command_key=key, expected_revision=1, terms=terms, reason="Révision concurrente de recette",
    )


def _race(engine, invoke, *, actors):
    starting_line = Barrier(2)

    def run(index, actor_id):
        with Session(engine) as session:
            actor = session.get(User, actor_id)
            connection = session.connection().connection.driver_connection
            starting_line.wait(timeout=10)
            try:
                result = invoke(index, actor, session)
            except HTTPException as exc:
                result = exc
            return get_ident(), id(connection), result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, index, actor_id) for index, actor_id in enumerate(actors)]
        first, second = (future.result(timeout=20) for future in futures)
    assert first[0] != second[0] and first[1] != second[1]
    return first[2], second[2]


def _assert_committed_product(engine, created, advanced, *, creation_key, revision_key=None, revision_actor=None):
    product_id = created["product_id"]
    snapshots = [created] if advanced is None else [created, advanced]
    actions = ["PRODUCT_SAVED"] if advanced is None else ["PRODUCT_SAVED", "PRODUCT_TERMS_REVISED"]
    actors = [1] if revision_actor is None else [1, revision_actor]
    expected_commands = [(1, creation_key, product_id, 1)]
    if revision_key is not None:
        expected_commands.append((revision_actor, revision_key, product_id, 2))

    with Session(engine) as session:
        product = session.exec(select(ProductRecord)).one()
        assert (product.id, product.reference, product.entity_id) == (product_id, created["reference"], 1)
        assert product.revision == product.terms_version == len(snapshots)
        versions = session.exec(select(ProductTermsVersion).order_by(ProductTermsVersion.version)).all()
        revisions = session.exec(select(ProductRevision).order_by(ProductRevision.revision)).all()
        audit_events = session.exec(select(AuditEvent).order_by(AuditEvent.id)).all()
        for rank, (expected, terms, revision, event, action, actor_id) in enumerate(
            zip(snapshots, versions, revisions, audit_events, actions, actors, strict=True), start=1,
        ):
            assert (terms.product_id, terms.version, terms.parent_version) == (product_id, rank, rank - 1 or None)
            assert json.loads(terms.terms_json) == expected["terms"]
            assert (revision.product_id, revision.revision, revision.terms_version) == (product_id, rank, rank)
            assert (revision.action, revision.actor_user_id) == (action, actor_id)
            assert json.loads(revision.snapshot_json)["native_schedule"] == expected["description"]["schedule"]
            assert (event.object_type, event.object_id, event.action, event.result, event.actor_user_id) == (
                "PRODUCT", product_id, action, "SUCCESS", actor_id,
            )
            assert json.loads(event.after_json) == {
                "revision": rank, "terms_version": rank, "terms_fingerprint": terms.fingerprint,
            }
        commands = session.exec(select(ProductCommand).order_by(ProductCommand.id)).all()
        assert [(item.user_id, item.command_key, item.product_id, item.result_revision) for item in commands] == expected_commands


def test_same_actor_same_key_concurrent_creation_and_revision_each_commit_once(concurrent_recipe):
    creation_key = "native-concurrent-create"
    create_body = _create_body(creation_key)
    first, retry = _race(
        concurrent_recipe,
        lambda _, actor, session: products_api.create_native_product(create_body, actor, session),
        actors=(1, 1),
    )
    assert isinstance(first, dict) and first == retry
    assert (first["revision"], first["terms_version"]) == (1, 1)
    _assert_committed_product(concurrent_recipe, first, None, creation_key=creation_key)

    revision_key = "native-concurrent-revise"
    revision_body = _terms_body(revision_key, 110)
    advanced, retry = _race(
        concurrent_recipe,
        lambda _, actor, session: products_api.revise_native_product_terms(
            first["product_id"], revision_body, actor, session,
        ),
        actors=(1, 1),
    )
    assert isinstance(advanced, dict) and advanced == retry
    assert (advanced["product_id"], advanced["reference"]) == (first["product_id"], first["reference"])
    assert (advanced["revision"], advanced["terms_version"]) == (2, 2)
    _assert_committed_product(
        concurrent_recipe, first, advanced, creation_key=creation_key, revision_key=revision_key, revision_actor=1,
    )

    with Session(concurrent_recipe) as session:
        assert products_api.create_native_product(create_body, session.get(User, 1), session) == first
    _assert_committed_product(
        concurrent_recipe, first, advanced, creation_key=creation_key, revision_key=revision_key, revision_actor=1,
    )


def test_distinct_same_entity_actors_cannot_both_revise_from_the_same_version(concurrent_recipe):
    creation_key = "native-version-race-create"
    with Session(concurrent_recipe) as session:
        first = products_api.create_native_product(_create_body(creation_key), session.get(User, 1), session)

    revision_bodies = (_terms_body("native-version-race-alice", 111), _terms_body("native-version-race-bob", 112))
    outcomes = _race(
        concurrent_recipe,
        lambda index, actor, session: products_api.revise_native_product_terms(
            first["product_id"], revision_bodies[index], actor, session,
        ),
        actors=(1, 2),
    )
    (winner_index, winner), = [(index, result) for index, result in enumerate(outcomes) if isinstance(result, dict)]
    loser = outcomes[1 - winner_index]
    assert isinstance(loser, HTTPException)
    assert (loser.status_code, loser.detail["code"]) == (409, "PRODUCT_REVISION_STALE")
    assert (winner["revision"], winner["terms_version"]) == (2, 2)
    assert winner["terms"]["floating_leg"]["margin_bps"] == revision_bodies[winner_index].terms.floating_leg.margin_bps
    _assert_committed_product(
        concurrent_recipe, first, winner, creation_key=creation_key,
        revision_key=revision_bodies[winner_index].command_key, revision_actor=winner_index + 1,
    )


def test_native_context_failed_commit_rolls_back_the_archive_and_can_be_retried(
    concurrent_recipe, abc_reference, monkeypatch,
):
    creation_key = "native-market-failure-create"
    with Session(concurrent_recipe) as session:
        user = session.get(User, 1)
        saved = products_api.create_native_product(_create_body(creation_key), user, session)
        product_id = saved["product_id"]
        product = load_product(session, product_id, allow_native=True)
        market = build_rates_market(abc_reference, (product,), "A")
        command = products_api.NativeContextRequest(
            command_key="native-market-failure-prepare", terms_version=product.terms_version,
            valuation_date=market.market_date,
            cutoff=datetime.fromisoformat(abc_reference["snapshots"]["A"]["cutoff_local"]),
            market=market,
        )

        def fail_before_commit():
            staged = session.exec(select(NativeValuationContextRecord)).one()
            assert (staged.command_key, staged.product_id) == (command.command_key, product_id)
            with Session(concurrent_recipe) as observer:
                assert observer.exec(select(NativeValuationContextRecord)).all() == []
            raise RuntimeError("injected archive commit failure")

        with monkeypatch.context() as fault:
            fault.setattr(session, "commit", fail_before_commit)
            with pytest.raises(RuntimeError, match="injected archive commit failure"):
                products_api.retain_native_valuation_context(product_id, command, user, session)

    _assert_committed_product(concurrent_recipe, saved, None, creation_key=creation_key)
    with Session(concurrent_recipe) as session:
        assert session.exec(select(NativeValuationContextRecord)).all() == []
        prepared = products_api.retain_native_valuation_context(product_id, command, session.get(User, 1), session)
        assert prepared.context.schedule_fingerprint == product.native_schedule.fingerprint

    with Session(concurrent_recipe) as session:
        retry = products_api.retain_native_valuation_context(product_id, command, session.get(User, 1), session)
        assert retry == prepared
        row = session.exec(select(NativeValuationContextRecord)).one()
        assert (row.id, row.command_key, row.fingerprint) == (
            prepared.context_id, command.command_key, prepared.context.fingerprint,
        )
    _assert_committed_product(concurrent_recipe, saved, None, creation_key=creation_key)
