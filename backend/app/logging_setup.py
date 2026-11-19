"""Process logging: one rotating file per installation (P1-9).

Before this module, nothing configured logging: only warnings and errors
reached stderr, through Python's last-resort handler, and the launcher
redirected stderr into an unbounded server.log. The INFO records the code
already writes (scheduler coverage, venue calendars, provider failures) were
lost, and so were the tracebacks of every request error, which uvicorn logs on
loggers that do not propagate to the root.

`configure_logging` keeps that console behaviour (WARNING and above on
stderr) and adds `<data dir>/logs/structura.log`, rotated at 5 MB with five
backups, at INFO or `STRUCTURA_LOG_LEVEL`. It is idempotent: a second call
replaces its own handlers and leaves any other handler alone.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

LOG_FILE = "structura.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
FORMAT = "%(asctime)s %(levelname)s [%(process)d %(threadName)s] %(name)s : %(message)s"

# uvicorn's own loggers keep their console handlers and do not propagate: the
# file is added to them explicitly, so a request's traceback reaches it. The
# access log stays out of the file: one line per request would rotate the
# errors away within hours.
_UVICORN = "uvicorn"
# Libraries that log every HTTP call at INFO.
_QUIET = ("httpx", "httpcore", "urllib3", "yfinance", "peewee", "multipart")
_MARK = "_structura_handler"


def _remove_own(logger: logging.Logger) -> None:
    for handler in [h for h in logger.handlers if getattr(h, _MARK, False)]:
        logger.removeHandler(handler)
        handler.close()


def configure_logging(directory: Path | None, *, level: str | None = None) -> Path | None:
    """Configure the process; return the log file, or None without a directory."""
    level_name = (level or os.environ.get("STRUCTURA_LOG_LEVEL") or "INFO").upper()
    file_level = logging.getLevelName(level_name)
    if not isinstance(file_level, int):
        file_level = logging.INFO
    root, server = logging.getLogger(), logging.getLogger(_UVICORN)
    _remove_own(root)
    _remove_own(server)
    formatter = logging.Formatter(FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    setattr(console, _MARK, True)
    root.addHandler(console)

    path = None
    if directory is not None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / LOG_FILE
        # One handler for both loggers: two rotating handlers on one file
        # would fight over the rename on Windows. uvicorn's configuration
        # (applied before the app starts) stops its records propagating; when
        # it has not, the root handler already receives them.
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8", delay=True)
        handler.setLevel(file_level)
        handler.setFormatter(formatter)
        setattr(handler, _MARK, True)
        root.addHandler(handler)
        if not server.propagate:
            server.addHandler(handler)
    root.setLevel(min(file_level, logging.WARNING) if path else logging.WARNING)
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
    return path


def log_task_failure(logger: logging.Logger, label: str):
    """Done-callback for a background asyncio task: an exception that ends the
    task is otherwise only reported, without context, when the task is
    garbage-collected."""
    def done(task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Tâche de fond arrêtée : %s", label, exc_info=exc)
    return done


SERVER_LOG_MAX_BYTES = 10 * 1024 * 1024
SERVER_LOG_BACKUPS = 3


def rotate_server_log(path: Path, *, max_bytes: int = SERVER_LOG_MAX_BYTES,
                      backups: int = SERVER_LOG_BACKUPS) -> bool:
    """Rotate the launcher's stdout capture before a start, when it is too big.

    The launcher redirects the server's console into this file, which nothing
    rotated. It cannot be rotated while the server writes into it, so it is
    done at each start: server.log.1 … server.log.<backups>."""
    path = Path(path)
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return False
        oldest = path.with_name(f"{path.name}.{backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(backups - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        # Held by a process that outlived its launcher: keep appending.
        logging.getLogger(__name__).warning("Rotation de %s impossible", path, exc_info=True)
        return False
