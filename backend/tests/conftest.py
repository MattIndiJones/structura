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

── 2. L'intégrité référentielle est toujours appliquée ──────────────

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

Il n'y a pas d'exemption. Mesuré le 19/11/2026 à la mise en place de la
règle : 464 échecs dans 49 modules, tous `FOREIGN KEY constraint failed`.
Il s'agissait le plus souvent d'une fixture qui insérait `Deal(user_id=1)` ou
`User(entity_id=7)` sans créer la ligne qu'elle nommait. Ces modules ont été
exemptés le temps de leur mise en conformité, puis la liste a été vidée le
20/11/2026. Les fixtures créent désormais ce qu'elles référencent, avec les
aides de `integrity_fixtures.py`.

La mise en conformité a trouvé deux vrais défauts. `delete_client` et
`delete_script` supprimaient le parent dans le même flush que ses enfants : sans
`relationship()`, SQLAlchemy n'ordonne pas ces suppressions. Une fixture qui
échoue sur une clé étrangère se corrige en créant le parent, pas en coupant la
contrainte.
"""
import atexit
import os
import shutil
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
# Every documented response is checked against its contract (api/contracts.py,
# P1-11): a route that drifts from what it declares fails the test that calls it.
os.environ["STRUCTURA_VALIDATE_RESPONSES"] = "1"

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

# ── 2. Intégrité référentielle, sans exemption ────────────────────────────

_TESTS_DIR = Path(__file__).resolve().parent
_OWN_FILES = {Path(__file__).resolve(), _TESTS_DIR / "sqlite_engines.py"}
_sqlmodel_create_engine = sqlmodel.create_engine


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
                and not event.contains(engine, "connect", foreign_keys_on)):
            event.listen(engine, "connect", foreign_keys_on)
        return engine
    create_engine.__wrapped__ = original
    return create_engine


sqlalchemy.create_engine = _with_integrity(_create_engine)
sqlmodel.create_engine = _with_integrity(_sqlmodel_create_engine)


_moteur_sqlite = moteur_sqlite


@pytest.fixture
def moteur_integre():
    """Un moteur qui applique les clés étrangères, comme la production."""
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
