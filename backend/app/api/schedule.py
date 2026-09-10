"""Schedule API endpoint — CONSTAT()/CONSTAT()() calendar generation (expert
mode), independent of any PayScript. See core/schedule.py for the algorithm."""
from datetime import date
from fastapi import APIRouter, HTTPException
from ..core.schemas import (BusinessDayRequest, PeriodWindowPreviewRequest,
                            ScheduleRequest, WindowPreviewRequest)
from ..core.calendars import (
    BusinessDayConvention, UnsupportedCurrency, add_business_days, adjust,
)
from ..core.schedule import (generate_schedule, observation_window,
                             parse_tenor, period_windows, StubConvention)

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


@router.post("/schedule/window")
async def window_preview_endpoint(req: WindowPreviewRequest):
    """Les dates qu'une fenêtre de constatation retient réellement.

    Sert à contrôler une saisie contre un term sheet sans avoir à convertir des
    jours ouvrés de tête. Le pricing publie ensuite le nombre de points de
    grille effectivement retenus, qui est une autre question : celle de ce que
    la grille hebdomadaire du moteur sait représenter."""
    anchor = _parse_date(req.date, "date")
    try:
        dates = observation_window(
            anchor, parse_tenor(req.window_length), parse_tenor(req.window_frequency),
            forward=req.forward, currency=req.currency,
            convention=BusinessDayConvention(req.convention))
    except (ValueError, UnsupportedCurrency) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "dates": [d.isoformat() for d in dates],
        "first": dates[0].isoformat(),
        "last": dates[-1].isoformat(),
        "count": len(dates),
    }


@router.post("/schedule/period-window")
async def period_window_preview_endpoint(req: PeriodWindowPreviewRequest):
    """Constatations d'un calendrier à fenêtre de PÉRIODE, et leurs relevés.

    Répond à la seule question que pose la saisie : « 1Y » et « 3M » donnent-ils
    3 constatations de 4 relevés, ou 12 observations ?"""
    try:
        obs, windows = period_windows(
            _parse_date(req.start_date, "start_date"),
            _parse_date(req.end_date, "end_date"),
            _parse_date(req.roll_date, "roll_date"),
            parse_tenor(req.frequency), StubConvention(req.stub),
            parse_tenor(req.window_frequency), currency=req.currency,
            convention=BusinessDayConvention(req.convention))
    except (ValueError, UnsupportedCurrency) as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Un calendrier absurde — une année tapée « 0026 » au lieu de « 2026 » — ne
    # doit pas produire deux mille constatations que l'écran déverserait. Il est
    # refusé, en nommant la cause la plus probable : c'est presque toujours une
    # date, jamais une intention.
    if len(obs) > 500:
        raise HTTPException(
            status_code=422,
            detail=f"{len(obs)} constatations sur ce calendrier — vérifiez les dates "
                   f"de début et de fin (une année à deux chiffres donne des siècles) "
                   f"et la fréquence.")
    tailles = [len(w) for w in windows]

    def _borne(w):
        """Une fenêtre quotidienne sur un an, c'est 250 dates : on montre les
        deux bouts. Le compte, lui, est toujours exact — c'est ce qu'on vient
        vérifier."""
        iso = [d.isoformat() for d in w]
        if len(iso) <= 10:
            return {"dates": iso, "tronque": False}
        return {"dates": iso[:6] + iso[-3:], "tronque": True}

    return {
        "count": len(obs),
        "releves_min": min(tailles) if tailles else 0,
        "releves_max": max(tailles) if tailles else 0,
        "premiere_constatation": obs[0].isoformat() if obs else None,
        "derniere_constatation": obs[-1].isoformat() if obs else None,
        # Une entrée par constatation : la date qu'elle porte, et les relevés
        # qu'elle moyenne. C'est le seul moyen de contrôler qu'un calendrier
        # annuel relevé trimestriellement fait bien 3 × 4 et non 12 × 1.
        "fenetres": [
            {"constatation": o.isoformat(), "n": len(w), **_borne(w)}
            for o, w in zip(obs, windows)
        ],
    }
