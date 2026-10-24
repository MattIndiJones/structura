"""Instance key loading shared by authentication and retained evidence."""
import logging
import os
import secrets

from ..runtime import data_path
from ..hybrid.config import current_config, signing_secret

logger = logging.getLogger(__name__)
_LEAKED_SECRET = "structura-jwt-secret-change-in-prod"
_SECRET_FILE = data_path(".jwt_secret")


def _load_secret() -> str:
    """Signing key, in order of preference: environment, then a per-machine
    file, then a freshly generated one.

    The key must not live in the repository, but hard-failing without one
    would make a fresh clone unusable and push people towards putting it back.
    So an absent key is generated once and stored in `backend/data/` — the
    directory that already holds the un-versioned database — which keeps
    sessions alive across the backend restarts this project does constantly,
    while giving every machine a distinct key. Deployments override it through
    STRUCTURA_JWT_SECRET and never touch the file.

    Tokens signed with the previously hard-coded value stop verifying here.
    That is the point, not a side effect."""
    config = current_config()
    if config:
        return signing_secret(config)
    from_env = os.environ.get("STRUCTURA_JWT_SECRET", "").strip()
    if from_env:
        if from_env == _LEAKED_SECRET:
            raise RuntimeError(
                "STRUCTURA_JWT_SECRET porte la valeur d'exemple publiée dans le "
                "dépôt : elle ne signe plus rien. Générez une clé propre "
                "(python -c \"import secrets; print(secrets.token_urlsafe(64))\").")
        if len(from_env) < 32:
            raise RuntimeError(
                f"STRUCTURA_JWT_SECRET fait {len(from_env)} caractères — 32 au "
                f"minimum sont exigés pour une signature HS256 sérieuse.")
        return from_env

    try:
        if _SECRET_FILE.exists():
            stored = _SECRET_FILE.read_text(encoding="utf-8").strip()
            if stored and stored != _LEAKED_SECRET and len(stored) >= 32:
                return stored
        generated = secrets.token_urlsafe(64)
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_FILE.write_text(generated, encoding="utf-8")
        logger.warning(
            "Cle de signature JWT generee dans %s (fichier non versionne). "
            "Les jetons anterieurs sont invalides : reconnectez-vous.",
            _SECRET_FILE)
        return generated
    except OSError as exc:
        # Read-only filesystem, permissions, container without volume: an
        # ephemeral key still beats a published one. Sessions die on restart.
        logger.warning(
            "Cle JWT non persistable (%s) — cle ephemere pour ce processus. "
            "Definissez STRUCTURA_JWT_SECRET pour des sessions durables.", exc)
        return secrets.token_urlsafe(64)


_PROCESS_SECRET = _load_secret()


def process_secret():
    return _PROCESS_SECRET


def receipt_signing_secret():
    config = current_config()
    return signing_secret(config) if config else _PROCESS_SECRET
