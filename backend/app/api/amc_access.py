"""Filesystem scope and bounded concurrency for Studies."""
import os
import threading
from pathlib import Path
from contextlib import contextmanager
from fastapi import HTTPException

_slots = threading.BoundedSemaphore(2)


def study_folder(folder, current):
    path = Path(folder).resolve()
    if current.role != "admin":
        configured = os.environ.get("STRUCTURA_STUDIES_ROOT")
        if not configured or current.id is None:
            raise HTTPException(403, "Dossier Studies non configuré pour cet utilisateur.")
        root = (Path(configured) / str(current.id)).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(403, "Dossier extérieur à votre espace Studies.")
    if not path.is_dir():
        raise HTTPException(422, "Dossier Studies introuvable.")
    return str(path)


@contextmanager
def study_slot():
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, "Deux études sont déjà en cours. Réessayez après leur fin.")
    try:
        yield
    finally:
        _slots.release()
