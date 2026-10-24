"""Atomic market-file generations, published by one durable manifest pointer."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

import numpy as np
import pandas as pd

from ..runtime import data_path

_view = ContextVar('market_storage_view', default=None)
_writing = ContextVar('market_storage_writer', default=None)
_root_override = ContextVar('market_storage_root', default=None)
_locks_guard = threading.Lock()
_locks = {}


def _root():
    return _root_override.get() or data_path('market_storage')


@contextmanager
def store_context(data_directory):
    """Explicit store root for standalone reference installers; no env mutation."""
    token = _root_override.set(Path(data_directory).resolve()/'market_storage')
    try:
        yield
    finally:
        _root_override.reset(token)


def _identity(path):
    return os.path.normcase(str(Path(path).resolve()))


def _logical_name(path):
    try:
        return Path(path).resolve().relative_to(_root().resolve().parent).as_posix()
    except ValueError:
        return None


def _entry_key(name):
    return sha256(name.casefold().encode()).hexdigest()


def _manifest():
    path = _root()/'manifest.json'
    if not path.exists():
        return {'version':1, 'revision':'legacy', 'entries':{}}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if (value['version'] != 1 or not isinstance(value['entries'], dict)
                or not isinstance(value['revision'],str)
                or any(not isinstance(entry,dict) or not isinstance(entry.get('logical_path'),str)
                       or 'file' not in entry for entry in value['entries'].values())):
            raise ValueError('Invalid market manifest')
        for key,entry in value['entries'].items():
            name = entry['logical_path']
            if (not name or name.startswith('/') or '\\' in name or ':' in name
                    or '..' in name.split('/') or key != _entry_key(name)):
                raise ValueError('Invalid logical market path')
        return value
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('Manifeste de marché illisible ; remplacement suspendu.') from exc


def revision():
    return _identity(_root()), _manifest()['revision']


def view_revision():
    snapshot = _view.get()
    root = _identity(_root())
    return (root, snapshot[1]['revision']) if snapshot and snapshot[0] == root else revision()


def _file_version(path, manifest):
    name = _logical_name(path)
    entry = manifest['entries'].get(_entry_key(name)) if name else None
    if entry is not None:
        return ('generation', entry.get('file'))
    value = Path(path)
    return ('legacy', value.stat().st_mtime_ns, value.stat().st_size) if value.exists() else ('absent',)


def versions(paths):
    snapshot = _view.get()
    manifest = snapshot[1] if snapshot and snapshot[0] == _identity(_root()) else _manifest()
    return {str(Path(path).resolve()):_file_version(path, manifest) for path in paths}


def current_path(path, *, manifest=None):
    """Resolve once; immutable generations remain readable after a later commit."""
    name = _logical_name(path)
    snapshot = _view.get()
    if manifest is None:
        manifest = snapshot[1] if snapshot and snapshot[0] == _identity(_root()) else _manifest()
    entry = manifest['entries'].get(_entry_key(name)) if name else None
    if entry is None:
        return Path(path)
    if entry.get('logical_path','').casefold() != name.casefold():
        raise ValueError('Identité de fichier de marché incohérente.')
    filename = entry.get('file')
    if filename is None:
        return _root()/'deleted'/_entry_key(name)
    if not isinstance(filename, str) or not re.fullmatch(r'[0-9a-f]{32}\.(parquet|json)', filename):
        raise ValueError('Référence de génération de marché invalide.')
    resolved = _root()/'objects'/filename
    if not resolved.is_file():
        raise ValueError('Génération de marché manquante ; reprise explicite requise.')
    return resolved


def logical_paths(directory, suffix='.parquet'):
    paths = {_identity(path):path for path in Path(directory).glob('*'+suffix)}
    snapshot = _view.get()
    manifest = snapshot[1] if snapshot and snapshot[0] == _identity(_root()) else _manifest()
    for entry in manifest['entries'].values():
        path = _root().parent/entry['logical_path']
        if _identity(path.parent) == _identity(directory) and path.suffix == suffix:
            if entry['file'] is None:
                paths.pop(_identity(path), None)
            else:
                paths[_identity(path)] = path
    return list(paths.values())


@contextmanager
def read_view():
    """A request reads one committed mapping across all its local market files."""
    existing = _view.get()
    if existing and existing[0] == _identity(_root()):
        yield existing[1]['revision']
        return
    manifest = _manifest()
    token = _view.set((_identity(_root()), manifest))
    try:
        yield manifest['revision']
    finally:
        _view.reset(token)


def consistent_read(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with read_view():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def _writer_lock():
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    with _locks_guard:
        lock = _locks.setdefault(_identity(root), threading.RLock())
    with lock:
        with (root/'writer.lock').open('a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            deadline = time.monotonic()+30
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (OSError, BlockingIOError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Stockage de marché occupé ; aucune modification publiée.')
                    time.sleep(.01)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Transaction:
    def __init__(self):
        self.manifest = deepcopy(_manifest())
        self.manifest['revision'] = uuid4().hex
        self.staged = []
        self.changed = False

    def path(self, path):
        return current_path(path, manifest=self.manifest)

    def require_unchanged(self, expected):
        if any(_file_version(path,self.manifest) != version for path,version in (expected or {}).items()):
            raise ValueError('Série modifiée pendant le chargement ; réponse ancienne non publiée. Relancez le chargement.')

    def _entry(self, path, filename):
        name = _logical_name(path)
        if name is None:
            raise ValueError('Écriture de marché hors du répertoire de données configuré.')
        self.manifest['entries'][_entry_key(name)] = {
            'logical_path':name, 'file':filename,
        }
        self.changed = True

    def parquet(self, path, frame):
        target = _root()/'objects'/(uuid4().hex+'.parquet')
        target.parent.mkdir(parents=True, exist_ok=True)
        self.staged.append(target)
        value = frame.copy(deep=True)
        value.attrs['storage_revision'] = self.manifest['revision']
        value.to_parquet(target)
        with target.open('r+b') as handle:
            os.fsync(handle.fileno())
        self._entry(path, target.name)

    def json(self, path, value):
        content = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        target = _root()/'objects'/(uuid4().hex+'.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        self.staged.append(target)
        with target.open('wb') as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        self._entry(path, target.name)

    def delete(self, path):
        self._entry(path, None)

    def publish(self):
        if not self.changed:
            return
        temporary = _root()/(uuid4().hex+'.tmp')
        try:
            with temporary.open('w', encoding='utf-8', newline='\n') as handle:
                json.dump(self.manifest, handle, ensure_ascii=False, allow_nan=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, _root()/'manifest.json')
            self.staged.clear()
        finally:
            temporary.unlink(missing_ok=True)

    def discard(self):
        for path in self.staged:
            path.unlink(missing_ok=True)


@contextmanager
def transaction():
    if _writing.get() == _identity(_root()):
        raise RuntimeError('Nested market transactions must reuse the active transaction explicitly.')
    with _writer_lock():
        pending = Transaction()
        token = _writing.set(_identity(_root()))
        try:
            yield pending
            pending.publish()
        finally:
            try:
                pending.discard()
            finally:
                _writing.reset(token)


def validate_frame(frame, fields=('close',)):
    """Reject an entire malformed EOD series instead of dropping bad rows."""
    if frame.empty or frame.columns.has_duplicates:
        raise ValueError('Série vide ou colonnes dupliquées.')
    value = frame.copy(deep=True)
    if any(isinstance(item,(int,float,np.number)) for item in value.index):
        raise ValueError('Les dates doivent être explicites, sans numéro de série implicite.')
    if any(isinstance(item,str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',item) for item in value.index):
        raise ValueError('Dates texte attendues au format AAAA-MM-JJ.')
    try:
        value.index = pd.DatetimeIndex(pd.to_datetime(value.index, errors='raise')).tz_localize(None)
    except (TypeError, ValueError) as exc:
        raise ValueError('Dates de marché invalides.') from exc
    if value.index.hasnans or value.index.has_duplicates:
        raise ValueError('Dates manquantes ou dupliquées ; aucune ligne écartée automatiquement.')
    if not value.index.equals(value.index.normalize()):
        raise ValueError('Série EOD attendue : une date sans heure intrajournalière.')
    for field in fields:
        if field not in value:
            raise ValueError(f'Colonne {field} absente.')
        if value[field].map(lambda item:isinstance(item, (bool, np.bool_))).any():
            raise ValueError('Un prix doit être un nombre positif fini.')
        try:
            numeric = pd.to_numeric(value[field], errors='raise').astype(float)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Prix non numérique dans {field}.') from exc
        if not (np.isfinite(numeric) & (numeric > 0)).all():
            raise ValueError(f'Prix manquant, non positif ou non fini dans {field}.')
        value[field] = numeric
    value.index.name = 'date'
    return value.sort_index()
