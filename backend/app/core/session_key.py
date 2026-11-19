"""The key that signs session tokens, apart from the pricing-receipt key (P1-8, S5).

One key, `.jwt_secret`, used to sign both the 30-minute session tokens and
the pricing receipts kept with deals for years. Sealing it with DPAPI would
have bound every receipt to one Windows account. They are now two keys:

- `.session_secret`, sealed by the system (core/secret_store.py). Losing it
  costs a login: a fresh one is generated and every session restarts;
- `.jwt_secret`, unchanged and still readable, signs receipts only
  (core/instance_signing.receipt_signing_secret).

`STRUCTURA_JWT_SECRET` still overrides the session key outside an
installation, as it did. Consultation never writes into the installation it
reads: its sessions use a key of the process, gone with it.
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from .secret_store import SecretUnavailable, read_secret, write_secret

logger = logging.getLogger(__name__)

SESSION_FILE = ".session_secret"
MINIMUM_LENGTH = 64


def session_secret_at(directory: Path) -> str:
    """The session key of a data directory, created and sealed if absent."""
    path = Path(directory) / SESSION_FILE
    if path.exists():
        try:
            value = read_secret(path).strip()
            if len(value) >= MINIMUM_LENGTH:
                return value
        except SecretUnavailable:
            logger.warning("Clé de session illisible sur ce compte Windows : nouvelle clé, "
                           "toutes les sessions sont à rouvrir.")
    value = secrets.token_urlsafe(64)
    write_secret(path, value)
    return value


def load_session_secret() -> str:
    from ..runtime import consultation_mode, data_path
    from ..hybrid.config import current_config
    if consultation_mode():
        return secrets.token_urlsafe(64)
    config = current_config()
    if config:
        return session_secret_at(config.data_dir)
    from_env = os.environ.get("STRUCTURA_JWT_SECRET", "").strip()
    if from_env:
        # Validated once by instance_signing._load_secret, imported first.
        return from_env
    try:
        return session_secret_at(data_path())
    except OSError as exc:
        logger.warning("Clé de session non persistable (%s) : clé éphémère pour ce processus.", exc)
        return secrets.token_urlsafe(64)
