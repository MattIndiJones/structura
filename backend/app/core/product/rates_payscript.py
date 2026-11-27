"""PayScript event evaluation for deterministic FRN and IRS schedules."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
import re
from typing import TYPE_CHECKING, Literal

from ..compute_budget import validate_script_source
from ..payscript.bindings import effective_parameters
from ..payscript.parser import parse_script, script_source_hash
from .models import FRNTerms, IRSTerms, FrozenModel, Product

if TYPE_CHECKING:
    from .rates_pricing import RatesPayoffAmount, RatesPayoffInput


RATES_PAYSCRIPT_PROFILE = "rates-deterministic-v1"
FRN_RATES_PAYSCRIPT = """# FRN Euribor 3M bullet
PARAM MARGIN

AT FLOATING_COUPON:
  PAY (EURIBOR_RATE + MARGIN) * YEAR_FRACTION "Coupon Euribor"

AT PRINCIPAL:
  PAY 1 "Remboursement du principal"
"""

IRS_RATES_PAYSCRIPT = """# IRS fixe contre Euribor 3M, receveur fixe
PARAM MARGIN
PARAM FIXED_RATE

AT FLOATING_COUPON:
  PAY -(EURIBOR_RATE + MARGIN) * YEAR_FRACTION "Jambe Euribor payée"

AT FIXED_COUPON:
  PAY FIXED_RATE * YEAR_FRACTION "Jambe fixe reçue"
"""

_TERM_PARAMETERS = {"MARGIN", "FIXED_RATE"}
_EVENT_OBSERVABLES = {
    "FLOATING_COUPON": frozenset({"EURIBOR_RATE", "YEAR_FRACTION", "IS_FIXED"}),
    "FIXED_COUPON": frozenset({"YEAR_FRACTION"}),
    "PRINCIPAL": frozenset(),
}
_OBSERVABLES = frozenset().union(*_EVENT_OBSERVABLES.values())
_STATEMENT_PAY = re.compile(r'^(?:PAY|FLOW)\s+(.+?)(?:\s+"[^"]*")?$', re.I)
_STATEMENT_IF = re.compile(r"^(?:IF|ELSE\s+IF)\s+(.+?)\s*:$", re.I)
_STATEMENT_ELSE = re.compile(r"^ELSE\s*:$", re.I)
_PARAM = re.compile(r"^PARAM\s+([A-Za-z][A-Za-z_0-9]*)\b", re.I)
_EVENT = re.compile(r"^AT\s+([A-Za-z][A-Za-z_0-9]*)\s*:$", re.I)
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z_0-9]*")
_EXPR_TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d*)?|\.\d+|\s+|[()+\-*/,<>=!]")
_EXPR_WORDS = {"AND", "OR", "NOT", "TRUE", "FALSE", "MIN", "MAX", "ABS", "INDIC"}
_QUALIFIED = {
    "FRN": ({"MARGIN"}, {
        "FLOATING_COUPON": ["(EURIBOR_RATE+MARGIN)*YEAR_FRACTION"],
        "PRINCIPAL": ["1"],
    }),
    "IRS": ({"MARGIN", "FIXED_RATE"}, {
        "FLOATING_COUPON": ["-(EURIBOR_RATE+MARGIN)*YEAR_FRACTION"],
        "FIXED_COUPON": ["FIXED_RATE*YEAR_FRACTION"],
    }),
}


class RatesScriptParameter(FrozenModel):
    name: str
    value: float
    unit: Literal["decimal_fraction", "scalar"]


class RatesScriptMetadata(FrozenModel):
    profile: Literal["rates-deterministic-v1"]
    source_hash: str
    parameters: tuple[RatesScriptParameter, ...]
    result_kind: Literal["qualified_linear", "deterministic_scenario"]


@dataclass(frozen=True)
class RatesScriptPayment:
    factor: float
    label: str


@dataclass(frozen=True)
class CompiledRatesPayScript:
    blocks: tuple[tuple[str, Callable], ...]
    metadata: RatesScriptMetadata
    qualified_instrument: Literal["FRN", "IRS"] | None

    def evaluate(
        self, leg_kind: str, *, rate: float | None = None, year_fraction: float | None = None,
        is_fixed: bool = False,
    ) -> tuple[RatesScriptPayment, ...]:
        role = leg_kind.upper()
        if role not in _EVENT_OBSERVABLES:
            raise ValueError(f"Événement PayScript de taux inconnu « {leg_kind} ».")
        context = {"memo": {item.name: item.value for item in self.metadata.parameters}, "done": False}
        if role != "PRINCIPAL":
            if year_fraction is None or not math.isfinite(year_fraction) or year_fraction < 0:
                raise ValueError("La fraction de période du coupon doit être finie et positive ou nulle.")
            context["memo"]["YEAR_FRACTION"] = year_fraction
        if role == "FLOATING_COUPON":
            if rate is None or not math.isfinite(rate):
                raise ValueError("Le taux Euribor 3M de la période est requis.")
            context["memo"].update(EURIBOR_RATE=rate, IS_FIXED=is_fixed)

        state = {"flows": [], "done": False}
        try:
            for event, block in self.blocks:
                if event == role:
                    block(context, state)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError(f"Erreur d’exécution PayScript de taux sur {role} : {exc}") from exc

        payments = []
        for flow in state["flows"]:
            factor = flow["v"]
            try:
                finite = type(factor) in (int, float) and math.isfinite(factor)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("PAY doit produire un facteur numérique fini en fraction de nominal.")
            payments.append(RatesScriptPayment(float(factor), flow["lbl"]))
        return tuple(payments)


def _expression_words(expression: str, line_no: int) -> set[str]:
    consumed = 0
    words = set()
    for token in _EXPR_TOKEN.finditer(expression):
        if token.start() != consumed:
            break
        consumed = token.end()
        if token[0][0].isalpha() or token[0][0] == "_":
            words.add(token[0].upper())
    if consumed != len(expression):
        raise ValueError(f"Ligne {line_no} : opérateur ou accès hors profil PayScript de taux.")
    return words


def _read_profile(source: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    declared = {}
    expressions = {}
    references = []
    event = None
    for line_no, line in enumerate(source.splitlines(), 1):
        statement = line.split("#", 1)[0].strip()
        if not statement:
            continue
        if not line[0].isspace():
            if match := _PARAM.match(statement):
                name = match[1].upper()
                if name in _OBSERVABLES or name in _EVENT_OBSERVABLES:
                    raise ValueError(f"Ligne {line_no} : « {name} » est réservé au profil de taux.")
                declared[name] = line_no
                event = None
                continue
            match = _EVENT.fullmatch(statement)
            event = match[1].upper() if match else None
            if event not in _EVENT_OBSERVABLES:
                raise ValueError(f"Ligne {line_no} : seuls PARAM et AT par jambe sont acceptés au niveau principal.")
            if event in expressions:
                raise ValueError(f"Ligne {line_no} : le bloc AT {event} est déjà déclaré.")
            expressions[event] = []
            continue

        if event is None:
            raise ValueError(f"Ligne {line_no} : instruction hors d’un événement de taux.")
        if match := _STATEMENT_PAY.fullmatch(statement):
            expression = match[1]
            expressions[event].append(re.sub(r"\s+", "", expression).upper())
        elif match := _STATEMENT_IF.fullmatch(statement):
            expression = match[1]
            expressions[event].append("IF")
        elif _STATEMENT_ELSE.fullmatch(statement):
            expressions[event].append("ELSE")
            continue
        else:
            raise ValueError(f"Ligne {line_no} : seuls PAY, FLOW et les conditions sont acceptés.")
        references.append((event, line_no, _expression_words(expression, line_no)))

    if not expressions:
        raise ValueError("Déclarez au moins un bloc de paiement AT de taux.")
    for event, line_no, words in references:
        unknown = words - declared.keys() - _EVENT_OBSERVABLES[event] - _EXPR_WORDS
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Ligne {line_no} : identifiants hors profil ou indisponibles sur {event} : {names}.")
    return declared, expressions


def _parameter_values(supplied: Mapping[str, float] | None) -> dict[str, float]:
    values = {}
    for name, value in (supplied or {}).items():
        if not _IDENTIFIER.fullmatch(name) or name.upper() in values:
            raise ValueError(f"Nom de paramètre de taux invalide ou dupliqué « {name} ».")
        values[name.upper()] = value
    return values


def compile_rates_payscript(
    source: str, parameters: Mapping[str, float] | None = None, *,
    profile: str = RATES_PAYSCRIPT_PROFILE,
    contractual_parameters: Mapping[str, float | None] | None = None,
) -> CompiledRatesPayScript:
    """Compile the rate profile through the existing PayScript event parser."""
    if profile != RATES_PAYSCRIPT_PROFILE:
        raise ValueError(f"Profil PayScript de taux inconnu « {profile} ».")
    validate_script_source(source)
    declared, expressions = _read_profile(source)
    prefix_lines = [f"PARAM {name} = 0" for name in sorted(_OBSERVABLES)]
    prefix_lines.extend(f"CONSTAT() {name}" for name in expressions)
    # The lexical profile above owns access to event inputs. The parser resolves
    # their scalar names and compiles the same PAY/condition blocks as PayScript.
    try:
        compiled = parse_script("\n".join([*prefix_lines, source]))
    except ValueError as exc:
        message = re.sub(
            r"Ligne (\d+)",
            lambda match: f"Ligne {int(match[1]) - len(prefix_lines)}",
            str(exc),
        )
        raise ValueError(message) from exc
    params = [param for param in compiled.params if param.name in declared]
    supplied = _parameter_values(parameters)
    if contractual_parameters is not None:
        if _TERM_PARAMETERS & supplied.keys():
            raise ValueError("MARGIN et FIXED_RATE sont fournis par les termes contractuels.")
        for param in params:
            if param.name in _TERM_PARAMETERS:
                if param.stored_val is not None or param.name not in contractual_parameters:
                    raise ValueError(f"PARAM {param.name} doit lire le terme contractuel sans valeur par défaut.")
                supplied[param.name] = contractual_parameters[param.name]
    unknown = supplied.keys() - declared.keys()
    if unknown:
        raise ValueError(f"Paramètres de taux non déclarés : {', '.join(sorted(unknown))}.")
    try:
        effective = effective_parameters(params, supplied)
    except OverflowError as exc:
        raise ValueError("Les paramètres du PayScript de taux doivent être numériques et finis.") from exc
    qualified = next(
        (kind for kind, shape in _QUALIFIED.items() if shape == (declared.keys(), expressions)),
        None,
    )
    metadata = RatesScriptMetadata(
        profile=RATES_PAYSCRIPT_PROFILE,
        source_hash=script_source_hash(source),
        parameters=tuple(RatesScriptParameter(
            name=param.name, value=effective[param.name],
            unit="decimal_fraction" if param.is_pct or param.name in _TERM_PARAMETERS else "scalar",
        ) for param in params),
        result_kind="qualified_linear" if qualified else "deterministic_scenario",
    )
    return CompiledRatesPayScript(
        blocks=tuple((event.constat_ref, event.fn) for event in compiled.events),
        metadata=metadata, qualified_instrument=qualified,
    )


def rates_payoff(product: Product) -> tuple[
    Callable[[RatesPayoffInput], RatesPayoffAmount], bool, RatesScriptMetadata,
]:
    """Bind contractual parameters and adapt signed script flows to pricing legs."""
    from .rates_pricing import RatesPayoffAmount

    terms = product.terms
    if not isinstance(terms, (FRNTerms, IRSTerms)) or terms.rates_script is None:
        raise ValueError("Le dossier doit porter un FRN ou IRS en PayScript de taux.")
    is_irs = isinstance(terms, IRSTerms)
    margin_bps = terms.floating_leg.margin_bps
    contractual = {"MARGIN": margin_bps / 10_000 if margin_bps is not None else None}
    if is_irs:
        contractual["FIXED_RATE"] = terms.fixed_leg.coupon_rate
    script = terms.rates_script
    compiled = compile_rates_payscript(
        script.source, script.parameters.to_dict(), profile=script.profile, contractual_parameters=contractual,
    )
    incompatible = "PRINCIPAL" if is_irs else "FIXED_COUPON"
    if any(role == incompatible for role, _ in compiled.blocks):
        raise ValueError(f"L’événement {incompatible} est incompatible avec ce dossier {terms.instrument_type}.")

    def payoff(event: RatesPayoffInput) -> RatesPayoffAmount:
        if event.instrument_type != terms.instrument_type:
            raise ValueError("L’événement PayScript de taux ne correspond pas au dossier.")
        flows = compiled.evaluate(
            event.kind, rate=event.rate, year_fraction=event.accrual_fraction, is_fixed=event.is_fixed,
        )
        try:
            factor = math.fsum(flow.factor for flow in flows)
        except OverflowError as exc:
            raise ValueError("Le facteur agrégé des paiements PayScript est hors limites.") from exc
        if is_irs and event.kind == "floating_coupon":
            factor = -factor
        return RatesPayoffAmount(
            amount_eur=event.nominal_eur * factor,
            label=" / ".join(dict.fromkeys(flow.label for flow in flows)) or None,
        )

    return payoff, compiled.qualified_instrument == terms.instrument_type, compiled.metadata
