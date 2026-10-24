"""Read governed fixing versions and overlay contractual dates for valuation."""
from copy import deepcopy
from math import isfinite
import json

from fastapi import HTTPException

from ..db.models import OfficialFixingVersion


def official_history(session, deal, events, prices, dates, asof):
    underlyings = json.loads(deal.underlyings_json or "[]")
    names = {u["name"]: u["ticker"] for u in underlyings}
    rows, versions, strike = {}, [], {}
    for event in events:
        if event.event_date > asof.isoformat():
            continue
        version = session.get(OfficialFixingVersion, event.current_fixing_version_id) if event.current_fixing_version_id else None
        if not version:
            if event.current_fixing_version_id or event.fixing_version:
                raise HTTPException(409, {"code": "OFFICIAL_FIXING_VERSION_MISSING", "event_id": event.id})
            if event.data_category == "FIXING_CANDIDATE":
                raise HTTPException(409, {"code": "OFFICIAL_FIXING_PENDING", "event_id": event.id})
            continue
        if version.status not in {"VALIDATED", "APPLIED"}:
            raise HTTPException(409, {"code": "OFFICIAL_FIXING_PENDING", "event_id": event.id,
                "message": "Une version de fixing attend une décision ; le MtM ne peut lui substituer le fournisseur."})
        values = json.loads(version.spots_json)
        if (version.deal_id != deal.id or version.deal_event_id != event.id
                or version.record_sha256 != event.fixing_record_sha256
                or values != json.loads(event.spots_json or "{}")
                or set(values) != set(names)
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not isfinite(v) or v <= 0 for v in values.values())):
            raise HTTPException(409, {"code": "OFFICIAL_FIXING_LEDGER_MISMATCH", "event_id": event.id})
        points = {names[name]: float(v) for name, v in values.items()}
        if event.event_date in rows and rows[event.event_date] != points:
            raise HTTPException(409, {"code": "OFFICIAL_FIXING_DATE_CONFLICT", "event_date": event.event_date})
        rows[event.event_date] = points
        versions.append({"event_id": event.id, "event_date": event.event_date, "version_id": version.id,
                         "version": version.version, "record_sha256": version.record_sha256})
        if event.t_years == 0 and event.parent_event_id is None:
            strike = values
    # Add missing contractual dates without manufacturing observations for
    # another ticker. Each official row contains the complete contractual basket.
    combined = sorted({d for d in dates if d <= asof.isoformat()} | set(rows))
    original = {d: i for i, d in enumerate(dates)}
    overlaid = {tk: [rows[d][tk] if d in rows else prices[tk][original[d]]
                    for d in combined] for tk in names.values()}
    evidence = {"authority": "OFFICIAL_FIXINGS_WITH_PROVIDER_HISTORY" if versions else "INDICATIVE_PROVIDER_HISTORY",
                "official_fixings": versions, "official_dates": sorted(rows),
                "provider_history_overridden": bool(versions)}
    return overlaid, combined, deepcopy(strike), evidence
