"""Schedule API endpoint — CONSTAT()/CONSTAT()() calendar generation (expert
mode), independent of any PayScript. See core/schedule.py for the algorithm."""
from datetime import date
from fastapi import APIRouter, HTTPException
from ..core.schemas import BusinessDayRequest, ScheduleRequest
from ..core.calendars import (
    BusinessDayConvention, UnsupportedCurrency, add_business_days, adjust,
)
from ..core.schedule import generate_schedule, parse_tenor, StubConvention

router = APIRouter(prefix="/api", tags=["schedule"])


def _parse_date(s: str, field: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} invalide (attendu YYYY-MM-DD): {s!r}")


@router.post("/schedule/generate")
async def generate_schedule_endpoint(req: ScheduleRequest):
    """Build a CONSTAT()/CONSTAT()() date schedule and its year-fraction preview."""
    start = _parse_date(req.start_date, "start_date")
    end = _parse_date(req.end_date, "end_date")
    roll = _parse_date(req.roll_date, "roll_date")

    try:
        frequency = parse_tenor(req.frequency)
        sub_frequency = parse_tenor(req.sub_frequency) if req.sub_frequency else None
        stub = StubConvention(req.stub)
        result = generate_schedule(
            start, end, roll, frequency, stub, sub_frequency,
            currency=req.currency,
            convention=BusinessDayConvention(req.convention),
            settlement_lag=req.settlement_lag)
    except (ValueError, UnsupportedCurrency) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "main_dates": [d.isoformat() for d in result["main_dates"]],
        "dates": [d.isoformat() for d in result["dates"]],
        "raw_dates": [d.isoformat() for d in result["raw_dates"]],
        "payment_dates": [d.isoformat() for d in result["payment_dates"]],
        "year_fractions": result["year_fractions"],
    }


@router.post("/calendar/resolve")
def resolve_business_day(req: BusinessDayRequest):
    """Une date contractuelle, resolue sur le calendrier de sa devise.

    Retourne la date d origine et la date effective : l interface affiche les
    deux, pour qu une date saisie ne se deplace jamais hors de la vue de qui
    la saisit."""
    d = _parse_date(req.date, "date")
    try:
        moved = add_business_days(d, req.business_days, req.currency) if req.business_days             else adjust(d, req.currency, BusinessDayConvention(req.convention))
    except UnsupportedCurrency as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"date": moved.isoformat(), "source": d.isoformat(), "moved": moved != d}
