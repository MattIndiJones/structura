"""SQLite engines for tests, with or without the production's referential integrity.

Kept out of conftest.py so that a test module can import it: importing
conftest.py itself would execute it a second time under another module name.
"""
import sqlite3

import sqlalchemy
from sqlalchemy import event
from sqlmodel import SQLModel

# conftest.py wraps sqlalchemy.create_engine; these engines set their own rule.
_create_engine = getattr(sqlalchemy.create_engine, "__wrapped__", sqlalchemy.create_engine)


def foreign_keys_on(dbapi_connection, _record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def moteur_sqlite(integrite: bool = True):
    """Un moteur SQLite en mémoire, schéma créé.

    `integrite=True` le fait se comporter comme celui de la production : les
    clés étrangères déclarées sont réellement appliquées, quel que soit le
    module de test. `integrite=False` donne un moteur sans contrainte, pour
    comparer les deux comportements.
    """
    moteur = _create_engine("sqlite://", connect_args={"check_same_thread": False})
    if integrite:
        event.listen(moteur, "connect", foreign_keys_on)
    SQLModel.metadata.create_all(moteur)
    return moteur


_moteur_sqlite = moteur_sqlite
