"""Daily lifecycle refresh + alert creation.

One pass over ACTIVE deals officialises controlled, unadjusted provider closes
and may apply a deterministic terminal result. Barrier alerts remain
indicative until their contractual observation date.

Ran two ways:
- by the in-process scheduler (main.py) every day at 23:00 local time,
  after the US close — events are close-of-day observations and Yahoo
  only serves reliable closes, so intraday runs would add noise, not info;
- on demand for one user, or the full visible book for an administrator, via
  POST /api/alerts/refresh-book.

Alerts are deduplicated by logical fact.  A terminal KI crossing keeps one
permanent key; an autocall heads-up includes its contractual observation date
so the next observation can alert again without duplicating the current one.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ..db.database import engine
from ..db.models import Deal, Alert, SchedulerRun
from ..core.audit import record_audit_event

log = logging.getLogger("structura.lifecycle")

# An "above the autocall barrier" heads-up is only actionable close to the
# fixing that would trigger it — a deal above its recall level with the next
# observation months away is just noise on the desk.
_AC_ALERT_MAX_DAYS = 30
SCHEDULER_TIMEZONE = "Europe/Paris"
SCHEDULER_JOB_KEY = "lifecycle_refresh"
_SCHEDULER_TZ = ZoneInfo(SCHEDULER_TIMEZONE)
_refresh_deal_handler = None
_watchlist_handler = None


def configure_lifecycle_handlers(refresh_deal, build_watchlist) -> None:
    """Composition-root injection; keeps this service independent of routes."""
    global _refresh_deal_handler, _watchlist_handler
    _refresh_deal_handler = refresh_deal
    _watchlist_handler = build_watchlist


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
    if _refresh_deal_handler is None or _watchlist_handler is None:
        raise RuntimeError("Handlers lifecycle non configurés.")

    q = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    if user_id is not None:
        q = q.where(Deal.user_id == user_id)
    deals = session.exec(q).all()

    today = date.today()
    summary = {"deals": len(deals), "refreshed": 0, "settled": 0,
               "alerts_created": 0,
               "proposed": [], "resolved": [], "errors": []}

    for deal in deals:
        if deal.status == "en_reglement":
            try:
                payment = date.fromisoformat(deal.payment_date)
            except (TypeError, ValueError):
                summary["errors"].append(
                    f"{deal.reference}: date de règlement absente ou invalide")
                continue
            if today >= payment:
                before = {"status": deal.status,
                          "settlement_amount": deal.settlement_amount}
                deal.status = "échu"
                deal.updated_at = datetime.utcnow()
                session.add(deal)
                record_audit_event(
                    session, action="DEAL_SETTLED", object_type="DEAL",
                    object_id=deal.id, actor_user_id=None, actor_type="PROCESS",
                    result="SUCCESS", before=before,
                    after={"status": deal.status,
                           "settlement_amount": deal.settlement_amount},
                    reason=f"Date de règlement atteinte ({deal.payment_date}).",
                    metadata={"payment_date": deal.payment_date},
                )
                session.commit()
                summary["settled"] += 1
            continue
        try:
            res = _refresh_deal_handler(deal, session)   # commits on success
        except Exception as e:
            summary["errors"].append(f"{deal.reference}: {e}")
            continue
        summary["refreshed"] += 1

        ev = (res or {}).get("evaluation") or {}
        outcome = ev.get("outcome")
        proposal = (res or {}).get("proposal") or {}
        if outcome in ("callé", "ki", "final"):
            target = (
                summary["resolved"]
                if proposal.get("status") == "APPLIED"
                else summary["proposed"]
            )
            target.append({"reference": deal.reference, "outcome": outcome})

        # An automated resolution has just made the deal terminal.  There is
        # no remaining barrier watchlist to inspect in this pass.
        if proposal.get("status") == "APPLIED":
            continue

        # Still active — barrier crossings on the same gaps the watchlist shows.
        try:
            row = _watchlist_handler(deal, session, today)
        except Exception as e:   # a broken snapshot must not sink the whole run
            summary["errors"].append(f"{deal.reference}: watchlist — {e}")
            continue
        days_to_next = row.get("days_to_next")
        next_observation_date = (row.get("next_event") or {}).get("date")
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
                  and days_to_next is not None and days_to_next <= _AC_ALERT_MAX_DAYS
                  and next_observation_date):
                created = _alert_once(
                    session, deal, "barrier_ac",
                    f"{deal.reference} : {obs}, au-dessus de la barrière de rappel {b['name']} "
                    f"({_pct(b['level'])}) — rappel probable à l'observation du "
                    f"{next_observation_date} (dans {days_to_next} j)",
                    f"deal:{deal.id}:barrier:{b['name']}:{next_observation_date}")
            else:
                created = False
            if created:
                summary["alerts_created"] += 1
        session.commit()

    return summary


def scheduled_slot(now: datetime | None = None) -> datetime:
    """Latest 23:00 Paris slot, persisted as naive UTC."""
    local_now = now.astimezone(_SCHEDULER_TZ) if now else datetime.now(_SCHEDULER_TZ)
    candidate = local_now.replace(hour=23, minute=0, second=0, microsecond=0)
    if candidate > local_now:
        candidate -= timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def _claim_scheduler_run(session: Session, slot: datetime,
                         trigger: str) -> SchedulerRun | None:
    existing = session.exec(select(SchedulerRun).where(
        SchedulerRun.job_key == SCHEDULER_JOB_KEY,
        SchedulerRun.scheduled_for == slot,
    )).first()
    now = datetime.utcnow()
    if existing:
        stale_running = (existing.status == "RUNNING"
                         and existing.started_at < now - timedelta(hours=1))
        if existing.status != "FAILED" and not stale_running:
            return None
        claimed = session.exec(
            update(SchedulerRun)
            .where(SchedulerRun.id == existing.id,
                   SchedulerRun.status == existing.status,
                   SchedulerRun.started_at == existing.started_at)
            .values(status="RUNNING", trigger=trigger, started_at=now,
                    finished_at=None, error=None)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        return session.get(SchedulerRun, existing.id) if claimed.rowcount == 1 else None
    row = SchedulerRun(
        job_key=SCHEDULER_JOB_KEY, scheduled_for=slot,
        timezone=SCHEDULER_TIMEZONE, status="RUNNING", trigger=trigger,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(row)
    return row


def run_scheduled_refresh(scheduled_for: datetime | None = None,
                          trigger: str = "SCHEDULED") -> dict:
    """Entry point for the daily in-process scheduler — own session, never
    raises (the loop in main.py must survive any single bad day)."""
    slot = scheduled_for or scheduled_slot()
    try:
        with Session(engine) as session:
            journal = _claim_scheduler_run(session, slot, trigger)
            if journal is None:
                return {"status": "SKIPPED", "scheduled_for": slot.isoformat()}
            summary = refresh_book(session)
            journal = session.get(SchedulerRun, journal.id)
            journal.status = "SUCCESS"
            journal.result_json = json.dumps(summary)
            journal.finished_at = datetime.utcnow()
            session.add(journal)
            session.commit()
        log.info(
            "Refresh quotidien : %s deal(s) actifs, %s rafraîchi(s), %s alerte(s), propositions=%s, résolutions=%s, erreurs=%s",
            summary["deals"], summary["refreshed"], summary["alerts_created"],
            summary["proposed"], summary["resolved"], summary["errors"],
        )
        return {"status": "SUCCESS", "scheduled_for": slot.isoformat(),
                "summary": summary}
    except Exception as exc:
        try:
            with Session(engine) as session:
                journal = session.exec(select(SchedulerRun).where(
                    SchedulerRun.job_key == SCHEDULER_JOB_KEY,
                    SchedulerRun.scheduled_for == slot,
                )).first()
                if journal:
                    journal.status = "FAILED"
                    journal.error = str(exc)
                    journal.finished_at = datetime.utcnow()
                    session.add(journal)
                    session.commit()
        except Exception:
            log.exception("Journalisation de l'échec du scheduler impossible")
        log.exception("Refresh quotidien échoué")
        return {"status": "FAILED", "scheduled_for": slot.isoformat(),
                "error": str(exc)}


def run_missed_refresh_if_needed(now: datetime | None = None) -> dict:
    """Run the latest missed slot once; never fabricate one run per missed day."""
    return run_scheduled_refresh(scheduled_slot(now), trigger="CATCH_UP")
