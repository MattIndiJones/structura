"""Explicit dated-market freshness policy; contractual finality is separate."""
from datetime import date


# D03: user-approved limits, inclusive at the boundary. Calendar days, minus
# the weekday closures of the security's venue (decision of 19/11/2026: on a
# day the venue does not trade, the last known close is the price). Weekends
# still count, and an unknown venue keeps the plain calendar-day rule.
POLICY_VERSION = "D03-C11-2026-11-19-3D-VENUE"
HISTORY_MAX_AGE_DAYS: int | None = 3
REPORTING_FX_MAX_AGE_DAYS: int | None = 3


def _venue_closed_days(venue, effective, requested):
    from .venue_closures import closures_between, weekday_closures
    closures = weekday_closures(venue, effective, requested)
    return int(closures_between(closures, [effective], [requested], include_upto=True)[0])


def freshness(effective: str | date | None, requested: str | date, usage: str,
              venue: str | None = None) -> dict:
    """Age of the last close at the requested date.

    `venue` is the exchange calendar of the listing (core/venue_closures
    .venue_calendar). Its weekday closures in (effective, requested] do not
    age the close: the last close before Easter Monday is still Monday's price
    on Euronext. Reporting FX has no venue and keeps calendar days."""
    requested = date.fromisoformat(requested) if isinstance(requested, str) else requested
    effective = date.fromisoformat(effective) if isinstance(effective, str) else effective
    maximum = REPORTING_FX_MAX_AGE_DAYS if usage == "reporting_fx" else HISTORY_MAX_AGE_DAYS
    age = (requested-effective).days if effective else None
    closed = (_venue_closed_days(venue, effective, requested)
              if venue and usage != "reporting_fx" and age is not None and age > 0 else 0)
    policy_age = age - closed if age is not None else None
    status = ("MISSING" if age is None else "FUTURE" if age < 0 else "FRESH" if age == 0
              else "POLICY_NOT_CONFIGURED" if maximum is None else "CARRIED" if policy_age <= maximum else "STALE")
    return dict(policy_version=POLICY_VERSION, usage=usage, requested_asof=requested.isoformat(),
                effective_date=effective.isoformat() if effective else None, age_days=age,
                venue_calendar=venue, venue_closed_days=closed,
                policy_age_days=policy_age, max_age_days=maximum, status=status,
                qualified=status in {"FRESH", "CARRIED"})
