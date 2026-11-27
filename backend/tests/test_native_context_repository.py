"""Native preparation archives use a versioned Product and a caller-owned transaction."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from backend.app.core.product.isda_market import IsdaMarket
from backend.app.core.product.models import Product
from backend.app.core.product.native_market import NativeValuationContext, NativeValuationInputs, prepare_native_context
from backend.app.db.migrations import m0002_native_valuation_contexts as context_migration
from backend.app.db.models import NativeValuationContextRecord, ProductRevision, ProductTermsVersion, User
from backend.app.services.native_context_repository import load_native_context, store_native_context
from backend.app.services.product_repository import ProductError, stage_new_product, stage_revision, stage_terms
from backend.tests.test_rates_credit_mixed_reader import _ISDA, _native_terms


def _new_product(session, owner):
    dossier = Product.model_validate({
        "name": "CDS de recette",
        "terms": _native_terms("CDS"),
        "intent": {"side": "BUY", "nominal": _ISDA["contract_terms"]["notional_eur"]},
    })
    return stage_new_product(session, dossier, user=owner)


def _market(scenario_index=0, *, changed_oracle=False):
    payload = deepcopy(_ISDA)
    if changed_oracle:
        payload["scenarios"][1]["workbook_results"]["clean_price_per_100"] += 0.5
    return IsdaMarket.model_validate({
        **payload, "policy": "historical_isda_benchmark", "scenario_id": payload["scenarios"][scenario_index]["id"],
    })


def _prepare(product, market):
    return prepare_native_context(product, market=market, valuation_date=date(2021, 4, 26),
                                  cutoff=datetime(2021, 4, 26, 10, tzinfo=timezone.utc))


@pytest.fixture
def archive(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'contexts.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        context_migration.upgrade(conn)
    with Session(engine) as session:
        owner = User(username="alice", email="alice@desk.test", password_hash="fixture", role="user")
        other = User(username="bob", email="bob@desk.test", password_hash="fixture", role="user")
        session.add_all([owner, other])
        session.flush()
        product = _new_product(session, owner)
        owner_id, other_id = owner.id, other.id
        session.commit()
    yield engine, owner_id, other_id, product
    engine.dispose()


def test_context_retry_returns_same_id_and_reopens_in_a_new_session(archive):
    engine, owner_id, _, product = archive
    market = _market()
    context = _prepare(product, market)
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        context_id = store_native_context(session, user=owner, command_key="prepare-isda",
                                          context=context, received_market=market)
        session.commit()

    with Session(engine) as session:
        owner = session.get(User, owner_id)
        changed_market = _market(changed_oracle=True)
        unchanged_context = _prepare(product, changed_market)
        assert changed_market != market and unchanged_context == context
        assert store_native_context(session, user=owner, command_key="prepare-isda",
                                    context=unchanged_context, received_market=changed_market) == context_id
        assert load_native_context(session, product.product_id, context_id, user=owner) == context
        row = session.exec(select(NativeValuationContextRecord)).one()
        assert (row.id, row.fingerprint) == (context_id, context.fingerprint)
        assert json.loads(row.context_json) == context.model_dump(mode="json")
        assert json.loads(row.received_market_json) == market.model_dump(mode="json")
        assert row.received_market_fingerprint == sha256(row.received_market_json.encode("utf-8")).hexdigest()
        assert len(session.exec(select(ProductRevision)).all()) == len(session.exec(select(ProductTermsVersion)).all()) == 1
        other_market = _market(1)
        with pytest.raises(ProductError) as error:
            store_native_context(session, user=owner, command_key="prepare-isda",
                                 context=_prepare(product, other_market), received_market=other_market)
        assert (error.value.code, error.value.status) == ("NATIVE_CONTEXT_COMMAND_CONFLICT", 409)


def test_context_insert_is_rolled_back_by_caller(archive):
    engine, owner_id, _, product = archive
    market = _market()
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        store_native_context(session, user=owner, command_key="rolled-back",
                             context=_prepare(product, market), received_market=market)
        session.rollback()
    with Session(engine) as session:
        assert session.exec(select(NativeValuationContextRecord)).all() == []


def test_context_uses_the_bound_schedule_and_reopens_after_a_new_terms_version(archive):
    engine, owner_id, _, product = archive
    market = _market()
    context = _prepare(product, market)
    wrong_inputs = context.model_dump(exclude={"fingerprint"})
    wrong_inputs["schedule_fingerprint"] = "0" * 64
    wrong = NativeValuationContext.seal(NativeValuationInputs.model_validate(wrong_inputs))
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        with pytest.raises(ProductError) as error:
            store_native_context(session, user=owner, command_key="wrong-schedule", context=wrong, received_market=market)
        assert error.value.code == "NATIVE_CONTEXT_SCHEDULE_MISMATCH"
        session.rollback()

        context_id = store_native_context(session, user=owner, command_key="original-terms",
                                          context=context, received_market=market)
        amended = {**_native_terms("CDS"), "reference_entity_id": "synthetic-amendment"}
        candidate = stage_terms(session, product, Product.model_validate({"terms": amended}).terms,
                                actor_id=owner_id, reason="Référence synthétique modifiée")
        revised = stage_revision(session, candidate, expected_revision=1, actor_id=owner_id,
                                 action="PRODUCT_TERMS_REVISED", reason="Référence synthétique modifiée")
        session.commit()
        assert revised.terms_version == 2 and revised.native_schedule.fingerprint != context.schedule_fingerprint
        assert load_native_context(session, product.product_id, context_id, user=owner) == context


def test_context_concurrent_retries_are_serialized(archive):
    engine, owner_id, _, product = archive
    market = _market()
    context = _prepare(product, market)
    started = Barrier(2)

    def run():
        with Session(engine) as session:
            owner = session.get(User, owner_id)
            started.wait(timeout=5)
            context_id = store_native_context(session, user=owner, command_key="concurrent",
                                              context=context, received_market=market)
            session.commit()
            return context_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        both = [pool.submit(run) for _ in range(2)]
        first, second = (future.result(timeout=10) for future in both)
    assert first == second
    with Session(engine) as session:
        assert session.exec(select(NativeValuationContextRecord)).one().id == first


def test_context_archive_checks_current_access_before_read_and_retry(archive):
    engine, owner_id, other_id, product = archive
    market = _market()
    context = _prepare(product, market)
    with Session(engine) as session:
        owner, other = session.get(User, owner_id), session.get(User, other_id)
        context_id = store_native_context(session, user=owner, command_key="prepared",
                                          context=context, received_market=market)
        session.commit()
        with pytest.raises(ProductError) as error:
            load_native_context(session, product.product_id, context_id, user=other)
        assert error.value.status == 404

        owner.is_active = False
        session.add(owner)
        session.commit()
        with pytest.raises(ProductError) as error:
            store_native_context(session, user=owner, command_key="prepared", context=context, received_market=market)
        assert error.value.status == 404


@pytest.mark.parametrize(("column", "path"), [
    ("context_json", "$.nominal"),
    ("received_market_json", "$.comparison_tolerances.cash_eur"),
])
def test_context_archive_prevents_sql_mutations_and_rejects_invalid_digest(archive, column, path):
    engine, owner_id, _, product = archive
    market = _market()
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        context_id = store_native_context(session, user=owner, command_key="frozen",
                                          context=_prepare(product, market), received_market=market)
        session.commit()

    for change in (
        "UPDATE native_valuation_contexts SET fingerprint = 'edited'",
        "DELETE FROM native_valuation_contexts",
        "INSERT OR REPLACE INTO native_valuation_contexts SELECT * FROM native_valuation_contexts",
    ):
        with pytest.raises(IntegrityError, match="immuable"), engine.begin() as conn:
            conn.exec_driver_sql(change)

    # Model a damaged backup in the disposable database, beyond the normal SQL guards.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER native_valuation_contexts_no_update")
        conn.exec_driver_sql(f"UPDATE native_valuation_contexts SET {column} = json_set({column}, ?, 1)", (path,))
    with Session(engine) as session:
        with pytest.raises(ProductError) as error:
            load_native_context(session, product.product_id, context_id, user=session.get(User, owner_id))
        assert error.value.code == "NATIVE_CONTEXT_INVALID"


def test_context_archive_does_not_follow_a_reused_product_id(archive):
    engine, owner_id, _, product = archive
    market = _market()
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        context_id = store_native_context(session, user=owner, command_key="old-product",
                                          context=_prepare(product, market), received_market=market)
        session.commit()
    # Reproduce the Product removal performed by synthetic batch cleanup.
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM product_revisions")
        conn.exec_driver_sql("DELETE FROM product_terms_versions")
        conn.exec_driver_sql("DELETE FROM products")
    with Session(engine) as session:
        owner = session.get(User, owner_id)
        replacement = _new_product(session, owner)
        session.commit()
        assert replacement.product_id == product.product_id
        assert replacement.reference != product.reference
        assert replacement.native_schedule.fingerprint == product.native_schedule.fingerprint
        with pytest.raises(ProductError) as error:
            load_native_context(session, product.product_id, context_id, user=owner)
        assert (error.value.code, error.value.status) == ("NATIVE_CONTEXT_NOT_FOUND", 404)
