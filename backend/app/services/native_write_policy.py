"""Native Product writes for isolated recipes and the development Admin workbench."""

import os
import stat
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from ..core.access import has_capability
from ..db.models import User
from ..runtime import DEFAULT_DATA_DIR, consultation_mode


def _uses_database(session: Session, directory: Path) -> bool:
    try:
        if directory.resolve(strict=True) != directory or directory.is_relative_to(DEFAULT_DATA_DIR.resolve()):
            return False
        url = session.get_bind().engine.url
        expected = directory / "structura.db"
        if url.get_backend_name() != "sqlite" or url.query.get("mode") == "ro":
            return False
        if not url.database or Path(url.database) != expected or expected.resolve(strict=True) != expected:
            return False
        metadata = expected.stat()
        return stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
    except (OSError, RuntimeError, ValueError, SQLAlchemyError):
        return False


def _uses_pinned_database(session: Session) -> bool:
    directory = Path(os.environ.get("STRUCTURA_DATA_DIR", ""))
    pinned = Path(os.environ.get("STRUCTURA_NATIVE_WRITES_DATA_DIR", ""))
    try:
        return (directory.is_absolute() and directory == pinned
                and not (directory / "installation.json").exists()
                and not (directory / ".hybrid-retired.json").exists()
                and _uses_database(session, directory))
    except OSError:
        return False


def isolated_native_actor(user: User, session: Session) -> bool:
    if (os.environ.get("STRUCTURA_NATIVE_WRITES") != "1"
            or os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") != "simulation"
            or os.environ.get("STRUCTURA_WORKSHOP_CHILD") != "1"
            or os.environ.get("STRUCTURA_INSTALLATION_CONFIG")
            or os.environ.get("STRUCTURA_ADMIN_WORKBENCH_CONFIG")
            or consultation_mode()):
        return False

    allowed = {name.strip() for name in os.environ.get("STRUCTURA_NATIVE_WRITES_USERS", "").split(",") if name.strip()}
    return (
        user.id is not None and user.username in allowed and getattr(user, "is_active", True)
        and _uses_pinned_database(session)
    )


def native_write_scope(user: User, session: Session) -> str | None:
    if isolated_native_actor(user, session):
        return "isolated_recipe"
    if (consultation_mode() or os.environ.get("STRUCTURA_DEVELOPER_ACCESS") != "1"
            or os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") != "admin_workbench"
            or os.environ.get("STRUCTURA_INSTALLATION_CONFIG") or user.id is None
            or user.entity_id is None or not getattr(user, "is_active", True)):
        return None

    from ..hybrid.admin_workbench import AdminWorkbenchIdentity, config

    try:
        workbench = config()
        if workbench is None or not _uses_database(session, workbench.data_dir):
            return None
        identity = session.get(AdminWorkbenchIdentity, 1)
        if identity and (identity.installation_id, identity.entity_id) == (str(workbench.installation_id), user.entity_id):
            return "admin_workbench"
    except (OSError, RuntimeError, ValueError, SQLAlchemyError):
        pass
    return None


def native_writes_enabled(user: User, session: Session) -> bool:
    return (native_write_scope(user, session) is not None and has_capability(user, "business.prepare")
            and has_capability(user, "business.price"))
