"""Configuration partagée de la suite de tests.

Contient pour l'instant une seule chose : de quoi tester AVEC les clés
étrangères, là où c'est le sujet.

── Pourquoi ce n'est pas activé partout ──────────────────────────────

SQLite n'applique pas les clés étrangères déclarées tant qu'on ne l'a pas
demandé, connexion par connexion. `db/database.py` pose donc
`PRAGMA foreign_keys=ON` par un listener sur SON moteur. Mais 31 des 65
fichiers de tests construisent le leur avec `create_engine("sqlite://")`, sans
ce listener : **ils tournent sans intégrité référentielle pendant que la
production l'applique.**

Ce n'est pas théorique. Le retrait du jeu de démonstration
(`scripts/seed_client_demo.py --purge`) était vert en test et a échoué au
premier essai sur la vraie base — il supprimait des interactions avant leurs
participants, et le test ne pouvait pas le voir.

La correction évidente serait d'activer le PRAGMA globalement, par un listener
sur la classe `Engine`. Elle a été essayée et MESURÉE, le 31/08/2026 :

    258 échecs et 148 erreurs sur 1292 tests — un tiers de la suite.

Et la cause n'est pas une famille de bugs latents : c'est une convention. Les
fixtures écrivent `Deal(user_id=1, entity_id=7, …)` sans jamais créer la ligne
`User` ni l'`Entity` correspondantes. Sous contrainte, chaque insertion est
refusée. Rendre la suite conforme demanderait de reprendre les fixtures de 31
fichiers — pour des tests dont le sujet est le pricing, les chocs ou le P&L, où
l'intégrité référentielle n'apporte rien.

D'où le choix inverse : **l'intégrité s'active à la demande**, dans les tests où
elle EST le sujet — ordre de suppression, cascades, archivage contre
suppression. C'est là que vivent les défauts qu'elle attrape, et nulle part
ailleurs.

Si la suite est un jour reprise en profondeur, le bon geste est de basculer ce
défaut : listener global, et `moteur_sqlite(integrite=False)` pour les rares
tests qui s'en dispensent.
"""
import sqlite3

import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, create_engine


def _moteur_sqlite(integrite: bool = True):
    """Un moteur SQLite en mémoire, schéma créé.

    `integrite=True` le fait se comporter comme celui de la production : les
    clés étrangères déclarées sont réellement appliquées. Le listener est posé
    sur CE moteur et non sur la classe `Engine`, pour qu'un test qui demande
    l'intégrité ne l'impose pas aux autres.
    """
    moteur = create_engine("sqlite://",
                           connect_args={"check_same_thread": False})
    if integrite:
        @event.listens_for(moteur, "connect")
        def _pragmas(connexion_dbapi, _record):
            if isinstance(connexion_dbapi, sqlite3.Connection):
                curseur = connexion_dbapi.cursor()
                curseur.execute("PRAGMA foreign_keys=ON")
                curseur.close()
    SQLModel.metadata.create_all(moteur)
    return moteur


@pytest.fixture
def moteur_integre():
    """Un moteur qui applique les clés étrangères, comme la production.

    À demander dans tout test qui SUPPRIME quelque chose : c'est là que l'ordre
    des suppressions compte, et c'est le seul endroit où l'absence de
    contrainte laisse passer un vrai défaut.

        def test_le_retrait_est_propre(moteur_integre):
            session = Session(moteur_integre)
            ...
    """
    return _moteur_sqlite(integrite=True)


@pytest.fixture
def fabrique_moteur():
    """Pour un test qui a besoin de PLUSIEURS moteurs — comparer le
    comportement avec et sans contrainte, par exemple."""
    return _moteur_sqlite


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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def integrity(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

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
