"""Secrets at rest protected by the operating system (P1-8, finding S5).

Provider API keys, the session signing key and bootstrap credentials sat in
plain files of the data directory: anyone able to copy that directory had
them. On Windows they are now sealed with DPAPI under the current Windows
account (`CryptProtectData`, no dependency): a copy of the directory read
from another account or machine yields nothing.

That is also the price, accepted on 19/11/2026: a data directory restored on
another machine cannot read these secrets. Sessions restart, AI keys are
entered again, bootstrap accounts are reset by the installation procedure.
The pricing-receipt key is deliberately NOT sealed (decision of 19/11/2026):
receipts signed with it must stay verifiable after a migration.

A file written before this version is plain text: it is read as such and
sealed in place on first read. Off Windows there is no account-bound store
without a new dependency; files stay plain and owner-only (0600), and
`protection_status()` says so.
"""
from __future__ import annotations

import base64
import ctypes
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER = b"STRUCTURA-DPAPI-1\n"
# Ties the blob to this use: another DPAPI consumer of the same account
# cannot unseal it by accident.
_ENTROPY = b"structura-secret-store-v1"


class SecretUnavailable(RuntimeError):
    """A sealed secret that this Windows account cannot open."""


def available() -> bool:
    return sys.platform == "win32"


def protection_status() -> str:
    return "DPAPI" if available() else "FILE_PERMISSIONS"


if available():
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def _blob(data: bytes) -> _Blob:
        buffer = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    def _take(blob: _Blob) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            _kernel32.LocalFree(blob.pbData)

    def _protect(data: bytes) -> bytes:
        source, entropy, out = _blob(data), _blob(_ENTROPY), _Blob()
        if not _crypt32.CryptProtectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                                         _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise OSError(ctypes.get_last_error(), "CryptProtectData a échoué")
        return _take(out)

    def _unprotect(data: bytes) -> bytes:
        source, entropy, out = _blob(data), _blob(_ENTROPY), _Blob()
        if not _crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                                           _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise SecretUnavailable(
                "Secret scellé par un autre compte Windows ou une autre machine : illisible ici.")
        return _take(out)


def seal(value: str) -> bytes:
    if not available():
        return value.encode("utf-8")
    return MARKER + base64.b64encode(_protect(value.encode("utf-8")))


def unseal(raw: bytes) -> tuple[str, bool]:
    """(value, was_sealed)."""
    if raw.startswith(MARKER):
        if not available():
            raise SecretUnavailable("Secret scellé par Windows : illisible sur ce système.")
        try:
            blob = base64.b64decode(raw[len(MARKER):], validate=True)
        except ValueError as error:
            raise SecretUnavailable("Secret scellé corrompu, ou d'un autre compte Windows : illisible ici.") from error
        return _unprotect(blob).decode("utf-8"), True
    return raw.decode("utf-8"), False


def write_secret(path: Path, value: str) -> None:
    """Seal and write atomically; owner-only where the system has modes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(seal(value))
    if not available():
        os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def read_secret(path: Path) -> str:
    """The secret's text, unsealed. A plain file is sealed in place."""
    path = Path(path)
    value, sealed = unseal(path.read_bytes())
    from ..runtime import consultation_mode
    # Consultation never writes into the installation it reads.
    if not sealed and available() and not consultation_mode():
        try:
            write_secret(path, value)
        except OSError:
            logger.warning("Scellement de %s impossible ; il reste en clair", path.name, exc_info=True)
    return value


def is_sealed(path: Path) -> bool:
    try:
        return Path(path).read_bytes().startswith(MARKER)
    except OSError:
        return False
