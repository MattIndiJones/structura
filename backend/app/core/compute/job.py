"""In-memory result shape for a single compute job — see executor.py for
what produces it and queue_store.py for how it gets persisted."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class JobResult:
    job_id: int
    ok: bool
    result: Optional[dict] = None
    error: Optional[str] = None
