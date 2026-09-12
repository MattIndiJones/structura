"""Shared interpretation of economic terms embedded in PayScript parameters."""


def classify_param_barrier(name: str, value: float) -> str | None:
    """Best-effort classification for legacy scripts without M_ monitors."""
    if not 0.2 <= value <= 3.0:
        return None
    normalized = name.upper()
    if "KI" in normalized or "KNOCK" in normalized:
        return "ki"
    if "AC" in normalized or "CALL" in normalized or "BAR" in normalized:
        return "autocall"
    return None
