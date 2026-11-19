"""Configuration partagée de la suite de tests.

Deux règles, appliquées à toute la session avant le premier import de
l'application (P1-6 de l'audit du 16/11/2026, constats D2 et D5).

── 1. Les données du poste sont hors d'atteinte ──────────────────────

Plusieurs modules figent un chemin au premier import : la base
(`db/database.py`), le magasin de prix AMC (`core/amc_prices.py`), les
documents, la clé de signature, les clés LLM. Un `monkeypatch.setenv` posé
dans un test arrive trop tard pour eux. Constaté le 18/11/2026 : selon l'ordre
de collecte, des tests lisaient les vraies séries GLE.PA et CS.PA du magasin
AMC du poste, et un test a écrit la série Yahoo d'`AAA` dans `backend/data`.

D'où, ici, avant tout import : les variables `STRUCTURA_*` héritées du shell
sont retirées (une installation, une horloge métier ou un marché de scénario
ne doivent pas fuir dans un test), et `STRUCTURA_DATA_DIR` pointe vers un
dossier temporaire propre à la session (à chaque processus sous xdist). Seules
les données versionnées, les facteurs Fama-French, y sont recopiées : la suite
voit ce que voit la CI. Un test qui veut son propre dossier pose toujours le
sien.

── 2. L'intégrité référentielle est appliquée par défaut ─────────────

SQLite n'applique les clés étrangères que si on le demande, connexion par
connexion. `db/database.py` le fait pour le moteur de production. Les tests
qui créent leur propre moteur (`create_engine("sqlite://")`) tournaient sans :
le retrait du jeu de démonstration était vert en test et a échoué au premier
essai sur la vraie base, parce qu'il supprimait des interactions avant leurs
participants.

`create_engine` est donc enveloppé : tout moteur SQLite créé depuis un fichier
de `backend/tests` pose `PRAGMA foreign_keys=ON`, comme la production, à chaque
prise de connexion. L'application ne crée elle-même que le moteur de
production, qui l'applique déjà : la règle ne peut pas rendre un test plus
strict que la production.

Les modules de test qui n'y sont pas encore conformes sont listés dans
`SANS_INTEGRITE`. La règle suit le test EN COURS, pas le module qui a créé le
moteur : la plupart des moteurs viennent de modules d'aide partagés, dont les
propres tests sont conformes. Le cas typique est une convention de
fixture, pas un défaut : `Deal(user_id=1, entity_id=7, …)` sans créer la ligne
`User` ni l'`Entity`. Un module sort de la liste quand ses fixtures créent ce
qu'elles référencent ; la liste ne doit que raccourcir.
"""
import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# ── 1. Environnement isolé, avant tout import de l'application ───────

_KEEP_ENV = {"STRUCTURA_DISABLE_SCHEDULER", "STRUCTURA_DISABLE_RFQ_TRANSPORT"}
for _name in [name for name in os.environ if name.startswith("STRUCTURA_") and name not in _KEEP_ENV]:
    del os.environ[_name]
# The configuration the nightly full suite runs under.
os.environ.setdefault("STRUCTURA_DISABLE_SCHEDULER", "1")
os.environ.setdefault("STRUCTURA_DISABLE_RFQ_TRANSPORT", "1")

_REPOSITORY_DATA = Path(__file__).resolve().parents[1] / "data"
SESSION_DATA_DIR = Path(tempfile.mkdtemp(prefix="structura-tests-"))
shutil.copytree(_REPOSITORY_DATA / "ff_factors", SESSION_DATA_DIR / "ff_factors")
os.environ["STRUCTURA_DATA_DIR"] = str(SESSION_DATA_DIR)
atexit.register(shutil.rmtree, SESSION_DATA_DIR, True)

if any(name == "backend.app" or name.startswith("backend.app.") for name in sys.modules):
    raise RuntimeError("Un module de l'application a été importé avant conftest.py : "
                       "ses chemins visent peut-être les données du poste.")

import pytest  # noqa: E402
import sqlalchemy  # noqa: E402
import sqlmodel  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from backend.tests.sqlite_engines import _create_engine, foreign_keys_on, moteur_sqlite  # noqa: E402

# ── 2. Intégrité référentielle par défaut ────────────────────────────

# Test modules (file stem) whose fixtures insert rows referencing parents they
# never create. The rule follows the RUNNING test, not the module that built
# the engine: most engines come from shared helpers (test_workflow_controls,
# test_ccr…) whose own tests conform. Measured on 19/11/2026 on the full suite:
# 464 failures, all FOREIGN KEY constraint failed, mostly a User inserted with
# an entity_id whose Entity was never created. Shrink only.
SANS_INTEGRITE: frozenset[str] = frozenset({
    "test_admin_registry", "test_amc_studies", "test_c19_archives",
    "test_calibration_window", "test_client_affiliations", "test_client_analytics",
    "test_client_api", "test_client_card", "test_client_coherence",
    "test_client_constraints", "test_client_constraints_ref", "test_client_demo_seed",
    "test_client_import", "test_client_intelligence", "test_client_lot2",
    "test_client_technical", "test_contractual_timeline", "test_fixing_finality_registry",
    "test_fixings_releves", "test_inlife_pricing", "test_kid_mrm",
    "test_legal_identity_workflows", "test_lifecycle_c26", "test_market_data_lot4",
    "test_market_snapshot_rate", "test_mtm_explain", "test_mtm_realized_sessions",
    "test_pnl_c22", "test_portfolio_barriers", "test_portfolio_corr_greek",
    "test_portfolio_pnl", "test_portfolios_crud", "test_reference_governance",
    "test_releves_consommateurs", "test_review_followup_2026_10_24",
    "test_review_probable_fixes_2026_10_24", "test_rfq", "test_rfq_desk_access",
    "test_risk_c21", "test_risk_dates", "test_shocks", "test_underlyings_catalog",
    "test_valuation_semantics", "test_var_engine", "test_variantes_comparaison",
    "test_variantes_filiation", "test_workflow_controls", "test_workflow_phase2",
    "test_workshop_consultation",
})

_TESTS_DIR = Path(__file__).resolve().parent
_OWN_FILES = {Path(__file__).resolve(), _TESTS_DIR / "sqlite_engines.py"}
_integrity = {"on": True}
_sqlmodel_create_engine = sqlmodel.create_engine


def _apply_rule(dbapi_connection, record, *_):
    """Apply the current test's rule on every connection, pooled ones included.

    An exemption only withdraws what the rule itself set: a test that enables
    the constraint on its own engine keeps it, exempt module or not."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    set_by_rule = record.info.get("foreign_keys_by_rule", False)
    if _integrity["on"] == set_by_rule:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=%s" % ("ON" if _integrity["on"] else "OFF"))
    cursor.close()
    record.info["foreign_keys_by_rule"] = _integrity["on"]


def _created_by_a_test():
    """True when the engine is created from a file of backend/tests.

    Test modules are imported as `tests.test_x` by pytest and as
    `backend.tests.test_x` by the modules that reuse their helpers: the file
    path is the only stable identity. The application's own engine (db/
    database.py) already enforces the constraint and is left alone."""
    frame = sys._getframe(2)
    while frame is not None:
        path = Path(frame.f_code.co_filename).resolve()
        if path in _OWN_FILES or "site-packages" in path.parts:
            frame = frame.f_back
            continue
        return path.parent == _TESTS_DIR
    return False


def _with_integrity(original):
    def create_engine(*args, **kwargs):
        engine = original(*args, **kwargs)
        if (engine.dialect.name == "sqlite" and _created_by_a_test()
                and not event.contains(engine, "checkout", _apply_rule)):
            event.listen(engine, "connect", _apply_rule)
            event.listen(engine, "checkout", _apply_rule)
        return engine
    create_engine.__wrapped__ = original
    return create_engine


sqlalchemy.create_engine = _with_integrity(_create_engine)
sqlmodel.create_engine = _with_integrity(_sqlmodel_create_engine)


@pytest.fixture(autouse=True)
def _integrite_referentielle(request):
    _integrity["on"] = Path(str(request.node.fspath)).stem not in SANS_INTEGRITE
    yield
    _integrity["on"] = True


_moteur_sqlite = moteur_sqlite


@pytest.fixture
def moteur_integre():
    """Un moteur qui applique les clés étrangères, comme la production,
    y compris dans un module exempté."""
    return moteur_sqlite(integrite=True)


@pytest.fixture
def fabrique_moteur():
    """Pour un test qui a besoin de PLUSIEURS moteurs — comparer le
    comportement avec et sans contrainte, par exemple."""
    return moteur_sqlite


@pytest.fixture
def authenticated_client(monkeypatch):
    """Standalone Front session with real JWT validation and private SQLite."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session
    from backend.app.api import auth
    from backend.app.db.database import get_session
    from backend.app.db.models import Entity, User

    monkeypatch.delenv("STRUCTURA_INSTALLATION_CONFIG", raising=False)
    engine = _create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", foreign_keys_on)

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Entity(id=1, name="Authenticated test organization"))
        session.flush()
        user = User(id=1, username="front", email="front@example.test",
                    password_hash="test-only", role="user", entity_id=1)
        session.add(user)
        session.commit()
        token = auth._make_token(user.id, user.role, user.entity_id, auth_version=user.auth_version)
    app = FastAPI()
    app.include_router(auth.router)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app, headers={"Authorization": "Bearer " + token}) as client:
            yield client
    finally:
        engine.dispose()
