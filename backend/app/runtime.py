"""Instance configuration and optional isolated business clock."""
from datetime import date, datetime
import json
import os
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def data_path(*parts: str) -> Path:
    return Path(os.environ.get("STRUCTURA_DATA_DIR", DEFAULT_DATA_DIR)).resolve().joinpath(*parts)


def business_now() -> datetime:
    clock = os.environ.get("STRUCTURA_BUSINESS_CLOCK")
    if not clock:
        return datetime.utcnow()
    return datetime.fromisoformat(json.loads(Path(clock).read_text(encoding="utf-8"))["now"])


def business_today() -> date:
    if not os.environ.get('STRUCTURA_BUSINESS_CLOCK'):
        return date.today()
    return business_now().date()
