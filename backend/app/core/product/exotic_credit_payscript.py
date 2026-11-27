"""Bounded credit PayScript for annual coupons and amounts at the default trigger."""

from dataclasses import dataclass
from types import FunctionType
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from ..compute_budget import validate_script_source
from ..payscript.bindings import effective_parameters
from ..payscript.parser import parse_script, script_source_hash
from .exotic_rates_payscript import _check_vector_expression, _read_source
from .models import FrozenModel, FrozenObject
from .rates_payscript import RatesScriptParameter, _parameter_values


PROFILE = "credit-exotic-payoff-v1"
CreditScriptEvent = Literal["CDS_PREMIUM", "CLN_COUPON", "CDS_PROTECTION", "CLN_DEFAULT_REDEMPTION"]
_OBSERVABLES = {
    "CDS_PREMIUM": ("COUPON_RATE",), "CLN_COUPON": ("COUPON_RATE",),
    "CDS_PROTECTION": ("RECOVERY_FRACTION", "DEFAULT_RANK"),
    "CLN_DEFAULT_REDEMPTION": ("RECOVERY_FRACTION", "DEFAULT_RANK"),
}
_RESERVED = frozenset(item for observables in _OBSERVABLES.values() for item in observables)


class ExoticCreditScriptError(ValueError):
    code = "MC_CREDIT_PAYSCRIPT"


class CreditScriptSource(FrozenModel):
    source: str = Field(min_length=1, max_length=4096)
    parameters: FrozenObject = Field(default_factory=lambda: FrozenObject({}))


class ExoticCreditScript(FrozenModel):
    profile: Literal["credit-exotic-payoff-v1"]
    coupon: CreditScriptSource | None = Field(default=None, exclude_if=lambda value: value is None)
    default: CreditScriptSource | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def requires_script(self):
        if self.coupon is None and self.default is None:
            raise ValueError("Renseignez un PayScript de coupon ou de règlement au défaut.")
        return self


class CreditScriptMetadata(FrozenModel):
    profile: Literal["credit-exotic-payoff-v1"] = PROFILE
    source_hash: str
    event: CreditScriptEvent
    observables: tuple[str, ...]
    parameters: tuple[RatesScriptParameter, ...]
    label: str
    output_unit: Literal["annual_fraction_of_nominal", "fraction_of_nominal"]


class CreditScriptMemberAmount(FrozenModel):
    reference_entity_id: str
    recovery_fraction: float
    payout_fraction: float


class CreditPayoffEvidence(FrozenModel):
    profile: Literal["credit-exotic-payoff-v1"] = PROFILE
    coupon: CreditScriptMetadata | None = None
    default: CreditScriptMetadata | None = None
    effective_coupon_rate: float
    member_amounts: tuple[CreditScriptMemberAmount, ...]


@dataclass(frozen=True)
class CompiledExoticCreditPayScript:
    fn: FunctionType
    metadata: CreditScriptMetadata

    def evaluate(self, **inputs: float | np.ndarray) -> np.ndarray:
        if set(inputs) != set(self.metadata.observables):
            raise ExoticCreditScriptError("Les observables ne correspondent pas à l’événement crédit.")
        arrays = {name: np.asarray(value, dtype=float) for name, value in inputs.items()}
        shape = np.broadcast_shapes(*(value.shape for value in arrays.values()))
        if not all(np.isfinite(value).all() for value in arrays.values()):
            raise ExoticCreditScriptError("Les observables crédit doivent être finis.")
        context = {"done": False, "memo": {item.name: item.value for item in self.metadata.parameters}}
        context["memo"].update(arrays)
        state = {"done": False, "flows": []}
        try:
            with np.errstate(divide="raise", invalid="raise", over="raise"):
                self.fn(context, state)
                result = np.broadcast_to(np.asarray(state["flows"][0]["v"]), shape)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ExoticCreditScriptError(f"PAY hors domaine numérique dans AT {self.metadata.event}.") from exc
        if (result.dtype.kind not in "iuf" or not np.isfinite(result).all()
                or (result < 0).any() or (result > 1).any()):
            raise ExoticCreditScriptError("PAY doit donner une fraction finie du nominal comprise entre 0 et 1.")
        return result


def compile_credit_event(source: CreditScriptSource, event: CreditScriptEvent) -> CompiledExoticCreditPayScript:
    observables = _OBSERVABLES.get(event)
    if observables is None:
        raise ExoticCreditScriptError("L’événement indiqué ne fait pas partie du profil PayScript crédit.")
    try:
        validate_script_source(source.source)
        declarations, expression, label = _read_source(source.source, event)
        if declarations.keys() & _RESERVED:
            raise ValueError("Les observables crédit sont réservés et ne peuvent être déclarés comme PARAM.")
        _check_vector_expression(expression, set(declarations).union(observables))
        prefix = [*(f"PARAM {name} = 0" for name in observables), f"CONSTAT() {event}"]
        program = parse_script("\n".join([*prefix, *declarations.values(), f"AT {event}:", f"  PAY {expression}"]))
        overrides = _parameter_values(source.parameters.to_dict())
        if unknown := overrides.keys() - declarations.keys():
            raise ValueError(f"Paramètres crédit non déclarés : {', '.join(sorted(unknown))}.")
        parameters = [item for item in program.params if item.name in declarations]
        effective = effective_parameters(parameters, overrides)
    except (ValueError, OverflowError) as exc:
        raise ExoticCreditScriptError(str(exc)) from exc
    block, = program.events
    fn = FunctionType(block.fn.__code__, {
        "__builtins__": {}, "abs": np.abs, "min": np.minimum, "max": np.maximum,
        "int": lambda comparison: np.asarray(comparison, dtype=float),
    })
    return CompiledExoticCreditPayScript(fn, CreditScriptMetadata(
        source_hash=script_source_hash(source.source), event=event, observables=observables, label=label,
        output_unit="annual_fraction_of_nominal" if event in ("CDS_PREMIUM", "CLN_COUPON") else "fraction_of_nominal",
        parameters=tuple(RatesScriptParameter(name=item.name, value=effective[item.name],
                                              unit="decimal_fraction" if item.is_pct else "scalar") for item in parameters),
    ))


def credit_coupon_rate(
    script: ExoticCreditScript, *, cln: bool, native_rate: float,
) -> tuple[float, CreditScriptMetadata | None]:
    if script.coupon is None:
        return native_rate, None
    compiled = compile_credit_event(script.coupon, "CLN_COUPON" if cln else "CDS_PREMIUM")
    return float(compiled.evaluate(COUPON_RATE=native_rate)), compiled.metadata


def credit_default_amounts(
    script: ExoticCreditScript, *, cln: bool, recovery: np.ndarray, rank: int,
) -> tuple[np.ndarray, CreditScriptMetadata | None]:
    if script.default is None:
        return recovery if cln else 1.0 - recovery, None
    compiled = compile_credit_event(script.default, "CLN_DEFAULT_REDEMPTION" if cln else "CDS_PROTECTION")
    return compiled.evaluate(RECOVERY_FRACTION=recovery, DEFAULT_RANK=float(rank)), compiled.metadata
