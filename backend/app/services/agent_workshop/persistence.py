"""Atomic evidence writes resilient to brief Windows reader locks."""
from pathlib import Path
import time
from uuid import uuid4


def atomic_write(path: Path, text: str):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.next')
    temporary.write_text(text,encoding='utf-8')
    try:
        for attempt in range(40):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt==39:raise
                time.sleep(.05)
    finally:
        try:temporary.unlink(missing_ok=True)
        except PermissionError:pass
