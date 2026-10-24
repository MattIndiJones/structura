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
from ..runtime import business_today
import json
from zoneinfo import ZoneInfo
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from ..db.database import engine
from ..db.models import Deal, Alert, SchedulerRun
from ..core.audit import record_audit_event
from .product_lifecycle import stage_product_lifecycle

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


def refresh_book(session: Session, user_id: int | None = None, *, current=None) -> dict:
    """Refresh every active deal (of one user, or all users for the
    scheduler), create alerts, and return a summary dict."""
    if _refresh_deal_handler is None or _watchlist_handler is None:
        raise RuntimeError("Handlers lifecycle non configurés.")

    q = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    if user_id is not None:
        q = q.where(Deal.user_id == user_id)
    deals = session.exec(q).all()
    if current is not None:
        from .business_access import visible_deals
        deals = visible_deals(session, deals, current)

    today = business_today()
    summary = {"deals": len(deals), "refreshed": 0, "settled": 0,
               "alerts_created": 0, "proposed": [], "resolved": [],
               "errors": [], "results": []}
    # Capture identities before a rollback expires the session's loaded rows.
    identities = [(deal.id, deal.reference) for deal in deals]
    for deal_id, reference in identities:
        result = {"deal_id": deal_id, "reference": reference, "status": "SUCCESS",
                  "stage": "refresh", "refreshed": False, "alerts_created": 0}
        try:
            deal = session.get(Deal, deal_id)
            if deal.status == "en_reglement":
                result["stage"] = "settlement"
                try:
                    payment = date.fromisoformat(deal.settlement_date or deal.payment_date)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Date de règlement absente ou invalide") from exc
                result["action"] = "WAITING_SETTLEMENT"
                if today >= payment:
                    before = {"status": deal.status, "settlement_amount": deal.settlement_amount}
                    deal.status = "callé" if deal.resolution_outcome == "callé" else "échu"
                    deal.updated_at = datetime.utcnow()
                    session.add(deal)
                    record_audit_event(
                        session, action="DEAL_SETTLED", object_type="DEAL",
                        object_id=deal.id, actor_user_id=None, actor_type="PROCESS",
                        result="SUCCESS", before=before,
                        after={"status": deal.status, "settlement_amount": deal.settlement_amount},
                        reason=f"Date de règlement atteinte ({payment.isoformat()}).",
                        metadata={"payment_date": payment.isoformat(), "contractual_payment_date": deal.payment_date})
                    if deal.product_id is not None:
                        stage_product_lifecycle(session, deal, actor_user_id=None,
                            action="PRODUCT_DEAL_SETTLED",
                            reason=f"Date de règlement atteinte ({payment.isoformat()}).")
                    session.commit()
                    summary["settled"] += 1
                    result["action"] = "SETTLED"
            else:
                res = _refresh_deal_handler(deal, session) or {}  # commits its own official facts
                summary["refreshed"] += 1
                result["refreshed"] = True
                ev = res.get("evaluation") or {}
                proposal = res.get("proposal") or {}
                if ev.get("outcome") in ("callé", "ki", "final"):
                    target = summary["resolved"] if proposal.get("status") == "APPLIED" else summary["proposed"]
                    target.append({"reference": reference, "outcome": ev["outcome"]})
                if proposal.get("status") != "APPLIED":
                    result["stage"] = "watchlist"
                    row = _watchlist_handler(deal, session, today)
                    result["market_coverage"] = row.get("market_coverage")
                    missing = [b.get("observable") or b["name"] for b in row.get("barriers", [])
                               if b.get("value_status") == "UNAVAILABLE" and b.get("kind") != "neutral"]
                    days = row.get("days_to_next")
                    next_date = (row.get("next_event") or {}).get("date")
                    created_count = 0
                    for barrier in row.get("barriers", []):
                        gap = barrier.get("gap_pts")
                        if gap is None:
                            continue
                        obs = f"{barrier['observable']} à {_pct(barrier['level'] + gap / 100)}"
                        if barrier.get("monitoring_basis") == "SAMPLED_CLOSES_SINCE_STRIKE":
                            obs += " (clôtures indicatives depuis le strike)"
                        created = False
                        if barrier["kind"] == "ki" and gap <= 0:
                            created = _alert_once(session, deal, "barrier_ki",
                                f"{reference} : {obs}, SOUS la barrière {barrier['name']} ({_pct(barrier['level'])})",
                                f"deal:{deal.id}:barrier:{barrier['name']}")
                        elif (barrier["kind"] == "autocall" and gap >= 0
                              and days is not None and 0 <= days <= _AC_ALERT_MAX_DAYS and next_date):
                            created = _alert_once(session, deal, "barrier_ac",
                                f"{reference} : {obs}, au-dessus de la barrière de rappel {barrier['name']} "
                                f"({_pct(barrier['level'])}) — rappel probable à l'observation du "
                                f"{next_date} (dans {days} j)",
                                f"deal:{deal.id}:barrier:{barrier['name']}:{next_date}")
                        created_count += int(created)
                    session.commit()
                    summary["alerts_created"] += created_count
                    result["alerts_created"] = created_count
                    if missing:
                        result.update(status="FAILED", error="Observables indisponibles : " + ", ".join(missing))
                        summary["errors"].append(f"{reference}: {result['error']}")
        except Exception as exc:
            session.rollback()
            message = str(getattr(exc, "detail", exc))
            result.update(status="FAILED", error=message)
            summary["errors"].append(f"{reference}: {result['stage']} — {message}")
        summary["results"].append(result)
    succeeded = sum(result["status"] == "SUCCESS" for result in summary["results"])
    failed = len(identities) - succeeded
    summary["coverage"] = {"total": len(identities), "succeeded": succeeded, "failed": failed}
    summary["status"] = "PARTIAL" if failed and succeeded else "FAILED" if failed else "SUCCESS"
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
        try:
            legacy_errors = existing.status == "SUCCESS" and bool(json.loads(existing.result_json).get("errors"))
        except (ValueError, AttributeError):
            legacy_errors = False
        if existing.status not in {"FAILED", "PARTIAL"} and not stale_running and not legacy_errors:
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
        if claimed.rowcount != 1:
            return None
        session.refresh(existing)
        return existing
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
    """Persist actual coverage, and permit retries of failed or partial slots."""
    slot = scheduled_for or scheduled_slot()
    claim_id = claimed_at = None
    try:
        with Session(engine) as session:
            journal = _claim_scheduler_run(session, slot, trigger)
            if journal is None:
                return {"status": "SKIPPED", "scheduled_for": slot.isoformat()}
            claim_id, claimed_at = journal.id, journal.started_at
            summary = refresh_book(session)
            status = summary["status"]
            completed = session.exec(update(SchedulerRun).where(
                SchedulerRun.id == claim_id, SchedulerRun.started_at == claimed_at,
                SchedulerRun.status == "RUNNING").values(
                    status=status, result_json=json.dumps(summary), finished_at=datetime.utcnow(),
                    error="; ".join(summary["errors"]) or None)
                .execution_options(synchronize_session=False))
            session.commit()
            if completed.rowcount != 1:
                return {"status": "SUPERSEDED", "scheduled_for": slot.isoformat(), "summary": summary}
        report = log.info if status == "SUCCESS" else log.warning
        report("Refresh quotidien %s : couverture=%s, erreurs=%s", status, summary["coverage"], summary["errors"])
        return {"status": status, "scheduled_for": slot.isoformat(), "summary": summary}
    except Exception as exc:
        if claim_id is not None:
            try:
                with Session(engine) as session:
                    session.exec(update(SchedulerRun).where(
                        SchedulerRun.id == claim_id, SchedulerRun.started_at == claimed_at,
                        SchedulerRun.status == "RUNNING").values(
                            status="FAILED", error=str(exc), finished_at=datetime.utcnow())
                        .execution_options(synchronize_session=False))
                    session.commit()
            except Exception:
                log.exception("Journalisation de l'échec du scheduler impossible")
        log.exception("Refresh quotidien échoué")
        return {"status": "FAILED", "scheduled_for": slot.isoformat(), "error": str(exc)}


def run_missed_refresh_if_needed(now: datetime | None = None) -> dict:
    """Run the latest missed slot once; never fabricate one run per missed day."""
    return run_scheduled_refresh(scheduled_slot(now), trigger="CATCH_UP")
