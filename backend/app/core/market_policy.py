"""Explicit dated-market freshness policy; contractual finality is separate."""
from datetime import date


# D03: user-approved calendar-day limits, inclusive at the boundary.
POLICY_VERSION = "D03-C11-2026-10-21-3D"
HISTORY_MAX_AGE_DAYS: int | None = 3
REPORTING_FX_MAX_AGE_DAYS: int | None = 3


def freshness(effective: str | date | None, requested: str | date, usage: str) -> dict:
    requested = date.fromisoformat(requested) if isinstance(requested, str) else requested
    effective = date.fromisoformat(effective) if isinstance(effective, str) else effective
    maximum = REPORTING_FX_MAX_AGE_DAYS if usage == "reporting_fx" else HISTORY_MAX_AGE_DAYS
    age = (requested-effective).days if effective else None
    status = ("MISSING" if age is None else "FUTURE" if age < 0 else "FRESH" if age == 0
              else "POLICY_NOT_CONFIGURED" if maximum is None else "CARRIED" if age <= maximum else "STALE")
    return dict(policy_version=POLICY_VERSION, usage=usage, requested_asof=requested.isoformat(),
                effective_date=effective.isoformat() if effective else None, age_days=age,
                max_age_days=maximum, status=status, qualified=status in {"FRESH", "CARRIED"})
