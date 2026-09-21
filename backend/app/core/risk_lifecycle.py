"""As-of lifecycle scope shared by risk calculations and deal listings."""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from ..db.models import Deal, DealEvent


TERMINAL_EVENT_STATUSES = ("callé", "ki", "final")


def terminal_dates_by_deal(
    session: Session | None, deal_ids: list[int],
) -> dict[int, date]:
    """Return the first contractual event that ended each deal's risk life."""
    if session is None or not deal_ids:
        return {}
    events = session.exec(
        select(DealEvent).where(
            DealEvent.deal_id.in_(deal_ids),
            DealEvent.status.in_(TERMINAL_EVENT_STATUSES),
        )
    ).all()
    result: dict[int, date] = {}
    for event in events:
        try:
            event_date = date.fromisoformat(event.event_date)
        except (TypeError, ValueError):
            continue
        previous = result.get(event.deal_id)
        if previous is None or event_date < previous:
            result[event.deal_id] = event_date
    return result


def deal_risk_state(
    deal: Deal,
    valuation_date: date,
    terminal_date: date | None = None,
) -> tuple[bool, str | None]:
    """Whether the optional exposure existed at the requested close of day.

    A deal enters the book on trade date (inclusive) and leaves it on the
    first terminal observation date (inclusive): once that observation is
    known, the optional exposure has disappeared.
    """
    try:
        trade_date = date.fromisoformat(deal.trade_date) if deal.trade_date else None
    except ValueError:
        return False, "Date de trade invalide"
    if trade_date and valuation_date < trade_date:
        return False, f"Pas encore booké (trade le {trade_date.isoformat()})"
    if terminal_date and valuation_date >= terminal_date:
        return False, f"Terminé le {terminal_date.isoformat()}"
    if not terminal_date and deal.status not in {"actif", "en_reglement"}:
        return False, f"Deal {deal.status}"
    return True, None
