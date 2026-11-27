"""Validate the PayScript profiles supported by the exotic Pricers."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .auth import get_current_pricer
from ..core.product.exotic_credit_payscript import CreditScriptSource, compile_credit_event
from ..core.product.exotic_rates_payscript import ExoticRatesScript, compile_exotic_rates_script
from ..core.product.models import FrozenModel, FrozenObject
from ..db.models import User


router = APIRouter(prefix="/api/products/exotics/payscript", tags=["exotic-payscript"])


class _Script(FrozenModel):
    source: str = Field(min_length=1, max_length=4096)
    parameters: FrozenObject = Field(default_factory=lambda: FrozenObject({}))


class RatesScriptValidation(_Script):
    profile: Literal["rates-exotic-coupon-v1"]
    event: Literal["CMS_COUPON", "CMS_SPREAD_COUPON", "RANGE_COUPON"]


class CreditScriptValidation(_Script):
    profile: Literal["credit-exotic-payoff-v1"]
    event: Literal["CDS_PREMIUM", "CLN_COUPON", "CDS_PROTECTION", "CLN_DEFAULT_REDEMPTION"]


ScriptValidation = Annotated[RatesScriptValidation | CreditScriptValidation, Field(discriminator="profile")]


@router.post("/validate")
def validate_exotic_payscript(body: ScriptValidation, current: Annotated[User, Depends(get_current_pricer)]):
    try:
        if isinstance(body, RatesScriptValidation):
            script = ExoticRatesScript(profile=body.profile, source=body.source, parameters=body.parameters)
            compiled = compile_exotic_rates_script(script, event=body.event, flow_id="validation")
        else:
            script = CreditScriptSource(source=body.source, parameters=body.parameters)
            compiled = compile_credit_event(script, event=body.event)
        return {"metadata": compiled.metadata.model_dump(mode="json")}
    except ValueError as exc:
        raise HTTPException(422, detail={"code": getattr(exc, "code", "EXOTIC_PAYSCRIPT_INVALID"),
                                         "message": str(exc)}) from exc
