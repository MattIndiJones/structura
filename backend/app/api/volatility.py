"""Authenticated, stateless validation of editable smile assumptions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import get_current_user, receipt_signing_secret
from ..services.calibration_evidence import sign_calibration
from ..core.schemas import VolatilitySurfaceParams
from ..core.volatility_surface import TermSSVISurface
from ..core.smile_calibration import calibrate_surface

router=APIRouter(prefix='/api/volatility',tags=['volatility'],
                 dependencies=[Depends(get_current_user)])


class SurfaceRequest(BaseModel):
    surface: VolatilitySurfaceParams


class CalibrationRequest(SurfaceRequest):
    model: str = Field(pattern='^(heston|sabr|lsv)$')
    horizon: float = Field(gt=0, le=30)
    rate: float = Field(default=.03,ge=-.25,le=1)
    dividend: float = Field(default=.02,ge=0,le=2)


@router.post('/validate')
def validate_surface(req: SurfaceRequest):
    surface=TermSSVISurface(req.surface.model_dump())
    return dict(surface=req.surface.model_dump(),certificate=surface.certificate())


@router.post('/calibrate')
def calibrate(req: CalibrationRequest):
    try:
        result = calibrate_surface(req.surface.model_dump(),req.model,req.horizon,req.rate,req.dividend)
        result['calibration_evidence'] = sign_calibration(result['dossier'], secret=receipt_signing_secret())
        return result
    except (ValueError, FloatingPointError) as exc:
        raise HTTPException(422,detail=str(exc)) from exc
