"""Authenticated, stateless validation of editable smile assumptions."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .auth import get_current_user, receipt_signing_secret
from ..services.calibration_evidence import sign_calibration
from ..core.schemas import VolatilitySurfaceParams
from ..core.volatility_surface import TermSSVISurface, fit_left_wing
from ..core.smile_calibration import calibrate_surface

router=APIRouter(prefix='/api/volatility',tags=['volatility'],
                 dependencies=[Depends(get_current_user)])


class SurfaceRequest(BaseModel):
    surface: VolatilitySurfaceParams


class LeftWingRequest(SurfaceRequest):
    expiry: float = Field(ge=1/12, le=30)
    strike: float = Field(ge=.2, le=.8)
    target: float = Field(gt=0, le=3)
    horizon: float = Field(gt=0, le=30)
    rate: float = Field(ge=-.25, le=1)
    dividend: float = Field(ge=0, le=2)


@router.post('/left-wing')
def adjust_left_wing(req: LeftWingRequest):
    try:
        original = req.surface.model_dump()
        surface, achieved, reason = fit_left_wing(
            original, req.expiry, req.strike, req.target, req.horizon, req.rate, req.dividend)
        return dict(surface=VolatilitySurfaceParams(**surface).model_dump(),
                    achieved=achieved, reason=reason, changed=surface is not original)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


class HestonFit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vanilla_limit_bp: float | None = Field(default=10., gt=0, le=1000)
    mode: Literal['atm', 'atm_digital', 'atm_smile'] | None = None


class CalibrationRequest(SurfaceRequest):
    model: str = Field(pattern='^(heston|sabr|lsv)$')
    horizon: float = Field(gt=0, le=30)
    rate: float = Field(default=.03,ge=-.25,le=1)
    dividend: float = Field(default=.02,ge=0,le=2)
    heston_fit: HestonFit | None = None


@router.post('/validate')
def validate_surface(req: SurfaceRequest):
    surface=TermSSVISurface(req.surface.model_dump())
    return dict(surface=req.surface.model_dump(),certificate=surface.certificate())


@router.post('/calibrate')
def calibrate(req: CalibrationRequest):
    try:
        options = {} if req.heston_fit is None else {'heston_fit': (
            {'mode': req.heston_fit.mode} if req.heston_fit.mode else
            {'vanilla_limit_bp': req.heston_fit.vanilla_limit_bp})}
        result = calibrate_surface(req.surface.model_dump(),req.model,req.horizon,req.rate,req.dividend,**options)
        result['calibration_evidence'] = sign_calibration(result['dossier'], secret=receipt_signing_secret())
        return result
    except (ValueError, FloatingPointError) as exc:
        raise HTTPException(422,detail=str(exc)) from exc
