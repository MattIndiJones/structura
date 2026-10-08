"""Explicit Economics basket binding and initial-fixing syntax.

Lower the object syntax into the existing event compiler. Initialization is a
contractual fixing operation, never an ordinary coupon event on the MC grid.
No user-controlled Python attribute access is emitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class SourceBinding:
    name: str
    fixing: str


def code_part(line: str) -> str:
    """Ignore comments without stripping a # inside a quoted flow label."""
    return re.split(r'#(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', line, maxsplit=1)[0].rstrip()


def lower_source(source: str) -> tuple[str, SourceBinding | None]:
    lines = source.splitlines()
    declarations = []
    for i, line in enumerate(lines):
        m = re.fullmatch(r'UNDERLYING\s+([A-Za-z]\w*)\s*', code_part(line), re.I)
        if m:
            declarations.append((i, m[1].upper()))
    if not declarations:
        return source, None
    if len(declarations) != 1:
        raise ValueError('Déclarez un seul UNDERLYING lié au panier Economics.')
    declaration_line, name = declarations[0]
    alias = re.escape(name)
    assignments = []
    block = None
    first_event = None
    for i, line in enumerate(lines):
        text = code_part(line)
        at = re.fullmatch(r'AT\s+(.+?)\s*:', text, re.I)
        if at:
            block = (i, at[1].upper())
            if first_event is None:
                first_event = i
        m = re.fullmatch(rf'\s+{alias}\.spot0\s*=\s*{alias}\.spot\s*@\s*([A-Za-z]\w*)\s*', text, re.I)
        if m:
            if block is None or block[1] != m[1].upper():
                raise ValueError('spot0 doit être initialisé dans AT <date du fixing initial>.')
            assignments.append((i, block[0], m[1].upper()))
    if len(assignments) != 1:
        raise ValueError(f'{name}.spot0 doit être initialisé exactement une fois : '
                         f'{name}.spot0 = {name}.spot@StartDate dans AT StartDate.')
    assignment_line, init_line, fixing = assignments[0]
    if init_line != first_event:
        raise ValueError('Le bloc de fixing initial doit précéder les observations.')
    fixing_decl = next((code_part(x).strip() for x in lines
                       if re.match(rf'^CONSTAT(?:\(\))*\s+{re.escape(fixing)}\b', code_part(x), re.I)), None)
    if not fixing_decl:
        raise ValueError(f'CONSTAT {fixing} doit être déclaré.')
    if re.match(r'^CONSTAT\(', fixing_decl, re.I):
        raise ValueError('Le fixing initial utilise CONSTAT (date unique), avec AVG/MIN/MAX '
                         'pour une fenêtre explicite ; un calendrier ne peut pas réinitialiser spot0.')
    if re.search(r'\bPERIOD\b', fixing_decl, re.I):
        raise ValueError('La fenêtre initiale doit avoir une longueur explicite, pas PERIOD.')
    for i in range(init_line + 1, len(lines)):
        text = code_part(lines[i])
        if text and not lines[i].startswith(' '):
            break
        if text.strip() and i != assignment_line:
            raise ValueError('Le bloc initial contient uniquement l’affectation de spot0.')

    lowered = []
    date_variable = None
    for i, line in enumerate(lines):
        if i in (declaration_line, init_line, assignment_line):
            lowered.append('')
            continue
        text = code_part(line)
        loop = re.fullmatch(r'AT\s+([A-Za-z]\w*)\s+FROM\s+([A-Za-z]\w*)\s*:', text, re.I)
        if loop:
            date_variable = loop[1]
            lowered.append(f'AT {loop[2]}:')
            continue
        if text and not line.startswith(' '):
            date_variable = None
        # Preserve labels/comments verbatim: only expression segments are lowered.
        parts = re.split(r'("[^"]*")', text)
        for j in range(0, len(parts), 2):
            part = parts[j]
            if re.search(r'\b__ASSET_', part, re.I):
                raise ValueError('Identifiant interne réservé.')
            if date_variable:
                part = re.sub(rf'\b{alias}\.spot\s*@\s*{re.escape(date_variable)}\b',
                              f'{name}.spot', part, flags=re.I)
            part = re.sub(rf'\b{alias}\.spot\s*/\s*{alias}\.spot0\b',
                          f'{name}.yield', part, flags=re.I)
            part = re.sub(rf'\b{alias}\.(yield|spot0|spot)\b',
                          lambda m: '__ASSET_' + m[1].upper(), part, flags=re.I)
            if '@' in part or re.search(rf'\b{alias}\s*\.', part, re.I):
                raise ValueError('Propriété Basket ou référence de fixing non prise en charge.')
            lowered_part = part
            if re.search(r'__ASSET_.*(?:__\w+__|\.)', lowered_part):
                # Decimal numeric constants remain valid; Python attribute chains do not.
                if re.search(r'__ASSET_\w+\s*\.', lowered_part):
                    raise ValueError('Accès à un attribut non autorisé.')
            parts[j] = part
        comment = line[len(text):] if line.startswith(text) else ''
        lowered.append(''.join(parts) + comment)
    return '\n'.join(lowered), SourceBinding(name=name, fixing=fixing)


def effective_parameters(params, supplied: dict | None, *, allow_missing=False) -> dict:
    """The sole fallback is an explicitly declared default, never zero."""
    supplied = supplied or {}
    result = {}
    for param in params:
        value = supplied[param.name] if param.name in supplied else param.stored_val
        if value is None or value == '':
            if allow_missing:
                result[param.name] = None
                continue
            raise ValueError(f'PARAM {param.name} : valeur à renseigner dans Economics.')
        sequence = isinstance(value, (list, tuple))
        values = value if sequence else [value]
        if not values or (sequence and param.kind != 'array'):
            raise ValueError(f'PARAM {param.name} : série vide ou incompatible avec un scalaire.')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
            raise ValueError(f'PARAM {param.name} : valeur numérique finie requise.')
        result[param.name] = list(values) if sequence else value
    return result


def asset_values(ctx: dict, attribute: str):
    if attribute == 'yield':
        return ctx['spots']
    initial = ctx.get('memo', {}).get('__REFERENCE_SPOTS')
    if initial is None:
        initial = ctx.get('reference_spots')
    if initial is None:
        raise ValueError('Les cours initiaux individuels sont requis pour lire Basket.spot/spot0. '
                         'Basket.yield utilise directement les niveaux relatifs.')
    if len(initial) != len(ctx['spots']) or any(not math.isfinite(v) or v <= 0 for v in initial):
        raise ValueError('Cours initiaux du panier invalides.')
    return initial if attribute == 'spot0' else [s * s0 for s, s0 in zip(ctx['spots'], initial)]


def average(values):
    if not values:
        raise ValueError('AVG exige un panier non vide.')
    return sum(values) / len(values)


def shift_calendars(values: dict, old_origin, new_origin) -> dict:
    """Roll contractual dates together; convention adjustment happens afterwards."""
    from datetime import date
    from copy import deepcopy
    old = date.fromisoformat(str(old_origin))
    new = date.fromisoformat(str(new_origin))
    shift = new - old
    result = deepcopy(values)
    keys = ('date', 'start_date', 'first_observation_date', 'period_start_date', 'end_date', 'roll_date')
    def move(value):
        return (date.fromisoformat(value) + shift).isoformat() if value else value
    for name, value in result.items():
        if isinstance(value, str):
            result[name] = move(value)
        elif isinstance(value, dict):
            for key in keys:
                if value.get(key):
                    value[key] = move(value[key])
    return result


def monitoring_source(source: str) -> str:
    """Resolve simple observable aliases at their point of use, never by name alone."""
    lowered, binding = lower_source(source)
    aliases = {}
    output = []
    block_indent = None
    for line in lowered.splitlines():
        code = code_part(line)
        if re.match(r'^AT\s', code, re.I):
            aliases.clear()
            block_indent = None
        code = re.sub(r'"[^"]*"', '""', code)
        for function, observable in [('WORSTOF', 'WOF'), ('BESTOF', 'BOF'), ('AVG', 'BASKET')]:
            code = re.sub(rf'\b{function}\s*\(\s*__ASSET_YIELD\s*\)', observable, code, flags=re.I)
        if code.strip() and line[:1].isspace() and block_indent is None:
            block_indent = len(line) - len(line.lstrip())
        # Only exact scalar observable definitions are eligible. Arbitrary
        # arithmetic, stateful aliases and ambiguous expressions stay unclassified.
        expanded = re.sub(r'\b[A-Za-z_]\w*\b', lambda m: aliases.get(m[0].upper(), m[0]), code)
        assign = re.match(r'\s*SET\s+(\w+)\s*=\s*(.*)', code, re.I)
        if assign:
            indent = len(line) - len(line.lstrip())
            rhs = re.sub(r'\b[A-Za-z_]\w*\b', lambda m: aliases.get(m[0].upper(), m[0]), assign[2]).strip().upper()
            aliases.pop(assign[1].upper(), None)
            if block_indent is not None and indent == block_indent and re.fullmatch(r'WOF|BOF|BASKET|S\[\d+\]', rhs):
                aliases[assign[1].upper()] = rhs
        output.append(expanded)
    return '\n'.join(output)
