"""D03/C13: a published daily close is eligible at session end, with no delay.

Eligibility under this operational policy is not an exchange certification.
Unknown venues, missing timestamps and closed sessions fail closed.
"""
from datetime import date, datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

POLICY_VERSION = "D03-C13-PUBLISHED-CLOSE-NO-DELAY-2026-10-21"
# Explicit Yahoo exchange identifiers. Never infer a venue from currency.
VENUES = {
    "NYQ": "XNYS", "NMS": "XNAS", "NGM": "XNAS", "NCM": "XNAS",
    "PAR": "XPAR", "AMS": "XAMS", "BRU": "XBRU", "LIS": "XLIS",
    "GER": "XETR", "FRA": "XFRA", "LSE": "XLON", "EBS": "XSWX",
    "JPX": "XTKS", "TYO": "XTKS", "HKG": "XHKG", "SES": "XSES",
    "TOR": "XTSE", "ASX": "XASX", "MCE": "XMAD", "MIL": "XMIL",
}


def utc_now():
    return datetime.now(timezone.utc)


@lru_cache(maxsize=128)
def session_calendar(name, year):
    import exchange_calendars as calendars
    return calendars.get_calendar(name, start=f"{year-1}-01-01", end=f"{year+1}-12-31")


def qualify_close(market_date, source, *, now=None):
    result = {"policy": POLICY_VERSION, "qualified": False, "market_date": market_date}
    try:
        day = date.fromisoformat(market_date)
        calendar_name = VENUES.get(source.get("exchange"))
        if not calendar_name:
            return {**result, "status": "VENUE_UNKNOWN"}
        cal = session_calendar(calendar_name, day.year)
        zone = ZoneInfo(str(source.get("timezone") or ""))
        if str(zone) != str(cal.tz):
            return {**result, "status": "TIMEZONE_MISMATCH", "calendar": calendar_name}
        result.update(calendar=calendar_name, timezone=str(zone), exchange=source["exchange"])
        if not cal.is_session(day.isoformat()):
            return {**result, "status": "NON_SESSION"}
        eligible_at = cal.session_close(day.isoformat()).to_pydatetime()
        result["eligible_at"] = eligible_at.isoformat()
        clock = now or utc_now()
        if clock.tzinfo is None:
            raise ValueError("Clock must be timezone aware")
        if clock < eligible_at:
            return {**result, "status": "WAITING_SESSION_CLOSE"}
        fetched = datetime.fromisoformat(str(source.get("fetched_at") or "").replace("Z", "+00:00"))
        if fetched.tzinfo is None or fetched < eligible_at or fetched > clock:
            return {**result, "status": "PUBLICATION_UNVERIFIED"}
        return {**result, "qualified": True, "status": "ELIGIBLE_PUBLISHED_CLOSE",
                "fetched_at": fetched.isoformat(), "calendar_version": __import__("exchange_calendars").__version__}
    except (ValueError, TypeError, KeyError, ImportError, OverflowError):
        return {**result, "status": "SESSION_METADATA_UNAVAILABLE"}
