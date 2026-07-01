"""Schedule API endpoint — CONSTAT()/CONSTAT()() calendar generation (expert
mode), independent of any PayScript. See core/schedule.py for the algorithm."""
from datetime import date
from fastapi import APIRouter, HTTPException
from ..core.schemas import ScheduleRequest
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
        result = generate_schedule(start, end, roll, frequency, stub, sub_frequency)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "main_dates": [d.isoformat() for d in result["main_dates"]],
        "dates": [d.isoformat() for d in result["dates"]],
        "year_fractions": result["year_fractions"],
    }
