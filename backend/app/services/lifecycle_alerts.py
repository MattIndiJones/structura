"""Daily lifecycle refresh + alert creation.

One pass over the ACTIVE deals: replay each frozen script on history
(api/deals.refresh_deal_core) to catch resolutions (callé / échu / ki),
then, for deals still alive, read the same barrier gaps the watchlist
shows (api/deals.build_watchlist_row) and raise crossing alerts.

Ran two ways:
- by the in-process scheduler (main.py) every day at 23:00 local time,
  after the US close — events are close-of-day observations and Yahoo
  only serves reliable closes, so intraday runs would add noise, not info;
- on demand for one user via POST /api/alerts/refresh-book.

Alerts are deduplicated forever by Alert.dedup_key: a resolution or a
barrier crossing alerts once, no matter how many later runs re-detect it.
"""
from __future__ import annotations
import logging
from datetime import date
from sqlmodel import Session, select
from ..db.database import engine
from ..db.models import Deal, Alert

log = logging.getLogger("structura.lifecycle")

# An "above the autocall barrier" heads-up is only actionable close to the
# fixing that would trigger it — a deal above its recall level with the next
# observation months away is just noise on the desk.
_AC_ALERT_MAX_DAYS = 30


def _alert_once(session: Session, deal: Deal, kind: str, message: str,
                dedup_key: str) -> bool:
    if session.exec(select(Alert).where(Alert.dedup_key == dedup_key)).first():
        return False
    session.add(Alert(
        user_id=deal.user_id, deal_id=deal.id, deal_reference=deal.reference,
        kind=kind, message=message, dedup_key=dedup_key,
    ))
    return True


def _pct(x) -> str:
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "?"


def refresh_book(session: Session, user_id: int | None = None) -> dict:
    """Refresh every active deal (of one user, or all users for the
    scheduler), create alerts, and return a summary dict."""
    from ..api.deals import refresh_deal_core, build_watchlist_row

    q = select(Deal).where(Deal.status == "actif")
    if user_id is not None:
        q = q.where(Deal.user_id == user_id)
    deals = session.exec(q).all()

    today = date.today()
    summary = {"deals": len(deals), "refreshed": 0, "alerts_created": 0,
               "resolved": [], "errors": []}

    for deal in deals:
        try:
            res = refresh_deal_core(deal, session)   # commits on success
        except ValueError as e:
            summary["errors"].append(f"{deal.reference}: {e}")
            continue
        summary["refreshed"] += 1

        ev = (res or {}).get("evaluation") or {}
        outcome = ev.get("outcome")
        if outcome in ("callé", "ki", "final"):
            when = ev.get("event_date", "?")
            payout = _pct(ev.get("realized_payout"))
            msg = {
                "callé": f"{deal.reference} : rappel anticipé détecté le {when} — remboursement total {payout}",
                "ki": f"{deal.reference} : échéance en knock-in le {when} — remboursement total {payout}",
                "final": f"{deal.reference} : arrivé à échéance le {when} — remboursement total {payout}",
            }[outcome]
            if _alert_once(session, deal, outcome, msg,
                           f"deal:{deal.id}:lifecycle:{outcome}"):
                summary["alerts_created"] += 1
            summary["resolved"].append({"reference": deal.reference, "outcome": outcome})
            session.commit()
            continue

        # Still active — barrier crossings on the same gaps the watchlist shows.
        try:
            row = build_watchlist_row(deal, session, today)
        except Exception as e:   # a broken snapshot must not sink the whole run
            summary["errors"].append(f"{deal.reference}: watchlist — {e}")
            continue
        days_to_next = row.get("days_to_next")
        for b in row.get("barriers", []):
            gap = b.get("gap_pts")
            if gap is None:
                continue
            obs = f"{b['observable']} à {_pct(b['level'] + gap / 100)}"
            if b["kind"] == "ki" and gap <= 0:
                created = _alert_once(
                    session, deal, "barrier_ki",
                    f"{deal.reference} : {obs}, SOUS la barrière {b['name']} ({_pct(b['level'])})",
                    f"deal:{deal.id}:barrier:{b['name']}")
            elif (b["kind"] == "autocall" and gap >= 0
                  and days_to_next is not None and days_to_next <= _AC_ALERT_MAX_DAYS):
                created = _alert_once(
                    session, deal, "barrier_ac",
                    f"{deal.reference} : {obs}, au-dessus de la barrière de rappel {b['name']} "
                    f"({_pct(b['level'])}) — rappel probable à l'observation dans {days_to_next} j",
                    f"deal:{deal.id}:barrier:{b['name']}")
            else:
                created = False
            if created:
                summary["alerts_created"] += 1
        session.commit()

    return summary


def run_scheduled_refresh() -> None:
    """Entry point for the daily in-process scheduler — own session, never
    raises (the loop in main.py must survive any single bad day)."""
    try:
        with Session(engine) as session:
            summary = refresh_book(session)
        log.info(
            "Refresh quotidien : %s deal(s) actifs, %s rafraîchi(s), %s alerte(s), résolus=%s, erreurs=%s",
            summary["deals"], summary["refreshed"], summary["alerts_created"],
            summary["resolved"], summary["errors"],
        )
    except Exception:
        log.exception("Refresh quotidien échoué")
