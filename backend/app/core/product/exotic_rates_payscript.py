"""Vector PayScript coupons on the frozen Hull–White event inputs."""
from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
import re
from types import FunctionType
from typing import Literal

import numpy as np
from pydantic import Field

from ..compute_budget import validate_script_source
from ..payscript.bindings import code_part, effective_parameters
from ..payscript.parser import _transpile_expr, parse_script, script_source_hash
from .models import FrozenModel, FrozenObject
from .rates_payscript import RatesScriptParameter, _expression_words, _parameter_values


PROFILE = "rates-exotic-coupon-v1"
Event = Literal["CMS_COUPON", "CMS_SPREAD_COUPON", "RANGE_COUPON"]
_OBSERVABLES = {
    "CMS_COUPON": ("CMS_RATE", "YEAR_FRACTION"),
    "CMS_SPREAD_COUPON": ("CMS_SPREAD", "YEAR_FRACTION"),
    "RANGE_COUPON": ("RANGE_FRACTION", "YEAR_FRACTION", "ANNUAL_RATE"),
}
_NAMES = frozenset(name for names in _OBSERVABLES.values() for name in names)
_PARAMETER = re.compile(r"PARAM\s+([A-Za-z][A-Za-z_0-9]*)\b", re.I)
_PAY = re.compile(r'\s+PAY\s+(.+?)(?:\s+"([^"]*)")?$', re.I)
_FUNCTION_ARITY = {"min": 2, "max": 2, "abs": 1, "int": 1}
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Constant, ast.Compare,
    ast.Attribute, ast.Subscript, ast.Load, ast.UAdd, ast.USub,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


class ExoticRatesScriptError(ValueError):
    code = "MC_RATES_PAYSCRIPT"


class ExoticRatesScript(FrozenModel):
    profile: Literal["rates-exotic-coupon-v1"]
    source: str = Field(min_length=1, max_length=4096)
    parameters: FrozenObject = Field(default_factory=lambda: FrozenObject({}))


class ExoticRatesScriptMetadata(FrozenModel):
    flow_id: str
    profile: Literal["rates-exotic-coupon-v1"] = PROFILE
    source_hash: str
    event: Event
    observables: tuple[str, ...]
    parameters: tuple[RatesScriptParameter, ...]
    label: str
    output_unit: Literal["fraction_of_nominal"] = "fraction_of_nominal"


@dataclass(frozen=True)
class CompiledExoticRatesPayScript:
    evaluate_event: Callable[[dict, dict], None]
    metadata: ExoticRatesScriptMetadata

    def evaluate(self, paths: int, **inputs: float | np.ndarray) -> np.ndarray:
        if inputs.keys() != set(self.metadata.observables):
            raise ExoticRatesScriptError("Les observables doivent correspondre au coupon PayScript résolu.")
        context = {"done": False, "memo": {item.name: item.value for item in self.metadata.parameters}}
        for name, observation in inputs.items():
            value = np.asarray(observation, dtype=float)
            if value.shape not in ((), (paths,)) or not np.all(np.isfinite(value)):
                raise ExoticRatesScriptError(f"L’observable {name} est invalide sur les trajectoires du coupon.")
            context["memo"][name] = value
        state = {"done": False, "flows": []}
        try:
            with np.errstate(divide="raise", invalid="raise", over="raise"):
                self.evaluate_event(context, state)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ExoticRatesScriptError(f"PAY hors domaine numérique pour le coupon {self.metadata.flow_id}.") from exc
        payment = np.asarray(state["flows"][0]["v"])
        if (payment.shape not in ((), (paths,)) or payment.dtype.kind not in "iuf"
                or not np.all(np.isfinite(payment))):
            raise ExoticRatesScriptError("PAY doit produire un facteur fini en fraction du nominal par trajectoire.")
        return np.broadcast_to(payment, (paths,))


def _read_source(source: str, event: Event) -> tuple[dict[str, str], str, str]:
    params = {}
    payment = None
    in_event = False
    for line in source.splitlines():
        statement = code_part(line)
        if not statement.strip():
            continue
        declaration = _PARAMETER.match(statement)
        if declaration and not in_event:
            name = declaration[1].upper()
            if name in _NAMES or name in params or len(params) >= 16:
                raise ExoticRatesScriptError(f"Paramètre réservé, dupliqué ou nombre de paramètres atteint : {name}.")
            params[name] = statement
        elif not in_event and re.fullmatch(rf"AT\s+{event}\s*:", statement, re.I):
            in_event = True
        elif in_event and payment is None and (match := _PAY.fullmatch(statement)):
            payment = (match[1], match[2] or match[1])
        else:
            raise ExoticRatesScriptError(f"Le profil attend des PARAM scalaires et un PAY dans AT {event}.")
    if payment is None:
        raise ExoticRatesScriptError(f"Un PAY est requis dans AT {event}.")
    return params, *payment


def _check_vector_expression(expression: str, names: set[str]) -> None:
    unknown = _expression_words(expression, 1) - names - {"MIN", "MAX", "ABS", "INDIC", "TRUE", "FALSE"}
    if unknown:
        raise ExoticRatesScriptError(f"Identifiants hors profil PayScript du coupon : {', '.join(sorted(unknown))}.")
    try:
        parsed = ast.parse(_transpile_expr(expression).strip(), mode="eval")
    except SyntaxError as exc:
        raise ExoticRatesScriptError("Expression PAY invalide.") from exc
    nodes = tuple(ast.walk(parsed))
    if len(nodes) > 160 or any(not isinstance(node, _ALLOWED_NODES) for node in nodes):
        raise ExoticRatesScriptError("PAY accepte les opérations arithmétiques simples et les comparaisons isolées.")
    for node in nodes:
        if isinstance(node, ast.Compare) and len(node.ops) != 1:
            raise ExoticRatesScriptError("Séparez les comparaisons en indicatrices distinctes.")
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            # This is the parser's lookup of a validated parameter or observable.
            continue
        if not isinstance(node.func, ast.Name) or len(node.args) != _FUNCTION_ARITY.get(node.func.id):
            raise ExoticRatesScriptError("Appel invalide pour MIN, MAX, ABS ou INDIC.")
        if node.func.id == "int":
            argument = node.args[0]
            if not (isinstance(argument, ast.Compare) or (isinstance(argument, ast.Constant) and type(argument.value) is bool)):
                raise ExoticRatesScriptError("INDIC attend une comparaison simple.")


def compile_exotic_rates_script(script: ExoticRatesScript, *, event: Event, flow_id: str) -> CompiledExoticRatesPayScript:
    try:
        validate_script_source(script.source)
        params, expression, label = _read_source(script.source, event)
        observables = _OBSERVABLES[event]
        _check_vector_expression(expression, set(params).union(observables))
        prefix = [*(f"PARAM {name} = 0" for name in observables), f"CONSTAT() {event}"]
        # The historical tokenizer can treat # inside a PAY label as a comment.
        # The label is already stored by this profile and never influences amounts.
        compiled = parse_script("\n".join([*prefix, *params.values(), f"AT {event}:", f"  PAY {expression}"]))
        supplied = _parameter_values(script.parameters.to_dict())
        unknown = supplied.keys() - params
        if unknown:
            raise ValueError(f"Paramètres de coupon non déclarés : {', '.join(sorted(unknown))}.")
        parsed = [item for item in compiled.params if item.name in params]
        effective = effective_parameters(parsed, supplied)
    except (ValueError, OverflowError) as exc:
        raise ExoticRatesScriptError(str(exc)) from exc
    block, = compiled.events
    # One PAY has no branch or state mutation. Replace only its scalar math primitives.
    fn = FunctionType(block.fn.__code__, {
        "__builtins__": {}, "abs": np.abs, "min": np.minimum, "max": np.maximum,
        "int": lambda compared: np.asarray(compared, dtype=float),
    })
    return CompiledExoticRatesPayScript(fn, ExoticRatesScriptMetadata(
        flow_id=flow_id, source_hash=script_source_hash(script.source), event=event,
        observables=observables, label=label,
        parameters=tuple(RatesScriptParameter(name=item.name, value=effective[item.name],
                                              unit="decimal_fraction" if item.is_pct else "scalar") for item in parsed),
    ))
