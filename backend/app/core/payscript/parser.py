"""
PayScript DSL parser.
Transpiles PayScript code to compiled Python event functions.

Grammar:
  PARAM NAME = value[%]   [# description]
  CONSTAT NAME            (single date, filled in via the UI)
  CONSTAT() NAME          (a CONSTAT() calendar: start/end/roll/freq/stub)
  CONSTAT()() NAME        (CONSTAT() + a sub-frequency)
  AT date, date, ...:
    body
  AT NAME:                (NAME = a CONSTAT declared above — resolved at
    body                   pricing time via resolve_constats, not parse time)
  AT MATURITY:
    body
  SET VAR = expr
  PAY / FLOW expr
  ACCRUE expr
  IF cond:
    body
  [ELSE IF cond:]
    body
  [ELSE:]
    body
  STOP
"""
from __future__ import annotations
import re
import math
from dataclasses import dataclass
from typing import Callable


# ── Safe math namespace exposed to PayScript ──────────────────────
_SAFE_MATH = {
    '__builtins__': {},
    'max': max, 'min': min, 'abs': abs, 'int': int, 'float': float,
    'sqrt': math.sqrt, 'exp': math.exp, 'log': math.log,
    'floor': math.floor, 'ceil': math.ceil,
    'round': round,
}


@dataclass
class Param:
    name: str
    raw_default: float
    stored_val: float
    is_pct: bool
    desc: str


@dataclass
class Constat:
    """A CONSTAT declaration — "expert mode" calendar metadata, surfaced to the
    UI exactly like Param so the user can fill in real dates for it.
    kind: 'single' (CONSTAT, one date) | 'schedule' (CONSTAT(), a CONSTAT()
    calendar) | 'nested_schedule' (CONSTAT()(), adds a sub-frequency).
    Referenced from AT via `AT Name:` (every date) or a qualifier — see
    CompiledEvent.constat_qualifier and resolve_constats."""
    name: str
    kind: str


@dataclass
class CompiledScript:
    events: list
    init_fn: Callable | None
    params: list[Param]
    constats: list[Constat]
    has_stop: bool = False


@dataclass
class CompiledEvent:
    type: str
    dates: list[float]
    fn: Callable
    # Set when this event was declared as `AT <ConstatName>:` instead of literal
    # dates — `dates` is then empty until resolve_constats() fills it in from
    # the user-provided CONSTAT values (not available at parse time).
    constat_ref: str | None = None
    # Narrows constat_ref to one specific date: None (every date) |
    # ('first',) | ('last',) | ('index', N) for `AT Name.first:` /
    # `AT Name.last:` / `AT Name[N]:` (N is 1-indexed, like S[i]).
    constat_qualifier: tuple | None = None


# ── Expression transpiler ─────────────────────────────────────────
def _transpile_expr(src: str) -> str:
    s = src.strip()
    out = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            out.append(' '); i += 1; continue
        two = s[i:i+2]
        if two in ('>=', '<='):
            out.append(two); i += 2; continue
        if two in ('!=', '<>'):
            out.append('!='); i += 2; continue
        if two == '==':
            out.append('=='); i += 2; continue
        if s[i].isdigit() or (s[i] == '.' and i+1 < len(s) and s[i+1].isdigit()):
            n = ''
            while i < len(s) and (s[i].isdigit() or s[i] == '.'):
                n += s[i]; i += 1
            out.append(n); continue
        if s[i].isalpha() or s[i] == '_':
            ident = ''
            while i < len(s) and (s[i].isalnum() or s[i] == '_'):
                ident += s[i]; i += 1
            u = ident.upper()
            if u == 'S' and i < len(s) and s[i] == '[':
                idx = ''; i += 1
                while i < len(s) and s[i] != ']':
                    idx += s[i]; i += 1
                if i < len(s): i += 1
                out.append(f'_c["spots"][int({_transpile_expr(idx)})-1]'); continue
            if u in ('S_MIN', 'S_MAX', 'S_PREV') and i < len(s) and s[i] == '[':
                idx = ''; i += 1
                while i < len(s) and s[i] != ']':
                    idx += s[i]; i += 1
                if i < len(s): i += 1
                key = {'S_MIN': 's_min', 'S_MAX': 's_max', 'S_PREV': 's_prev'}[u]
                out.append(f'_c["{key}"][int({_transpile_expr(idx)})-1]'); continue
            if u == 'AND': out.append(' and '); continue
            if u == 'OR':  out.append(' or ');  continue
            if u == 'NOT': out.append(' not '); continue
            if u == 'TRUE':  out.append('True');  continue
            if u == 'FALSE': out.append('False'); continue
            BV = {
                'WOF': 'min(_c["spots"])', 'BOF': 'max(_c["spots"])',
                'WOF_MIN': '_c["wof_min"]', 'BOF_MAX': '_c["bof_max"]',
                'ACCUM': '_c["accum"]', 'INDEX': '_c["index"]',
                'T': '_c["t"]', 'N': 'len(_c["spots"])',
                'REALVOL': '_c["realvol"]',
            }
            if u in BV: out.append(BV[u]); continue
            MF = {
                'MAX': 'max', 'MIN': 'min', 'ABS': 'abs',
                'FLOOR': 'floor', 'CEIL': 'ceil',
                'SQRT': 'sqrt', 'LOG': 'log', 'EXP': 'exp',
                'INDIC': 'int', 'ROUND': 'round',
            }
            if u in MF: out.append(MF[u]); continue
            if u == 'BASKET':
                if i < len(s) and s[i] == '(':
                    j = i + 1
                    while j < len(s) and s[j].isspace(): j += 1
                    if j < len(s) and s[j] == ')':
                        out.append('(sum(_c["spots"])/max(1,len(_c["spots"])))'); i = j + 1
                    else:
                        out.append('_basket(_c,'); i += 1
                else:
                    out.append('(sum(_c["spots"])/max(1,len(_c["spots"])))')
                continue
            out.append(f'_c["memo"].get("{u}", 0)'); continue
        if s[i] == '=' and (not out or out[-1].strip() not in ('!', '<', '>', '=')):
            out.append('=='); i += 1; continue
        out.append(s[i]); i += 1
    return ''.join(out)


def _basket(ctx, *weights):
    spots = ctx['spots']
    if not weights:
        return sum(spots) / max(1, len(spots))
    t = sum(weights) or 1
    return sum(s * w for s, w in zip(spots, weights)) / t


# ── Body compiler ─────────────────────────────────────────────────
def _compile_body(lines: list[dict], errors: list, base_indent: int = 0) -> str:
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln['indent'] < base_indent: i += 1; continue
        if ln['indent'] > base_indent: i += 1; continue
        text, no = ln['text'], ln['line_no']

        m = re.match(r'^IF\s+(.+?)\s*:?\s*$', text, re.I)
        if m:
            try: cond = _transpile_expr(m.group(1))
            except Exception as e: errors.append(f'Ligne {no}: {e}'); i += 1; continue
            i += 1
            body_lines = []
            while i < len(lines) and lines[i]['indent'] > base_indent:
                body_lines.append(lines[i]); i += 1
            nbi = body_lines[0]['indent'] if body_lines else base_indent + 4
            body_code = _compile_body(body_lines, errors, nbi)
            out.append(f'if {cond}:')
            for bl in body_code.splitlines(): out.append('  ' + bl)
            while i < len(lines) and lines[i]['indent'] == base_indent:
                et = lines[i]['text']
                mei = re.match(r'^ELSE\s+IF\s+(.+?)\s*:?\s*$', et, re.I)
                me  = re.match(r'^ELSE\s*:?\s*$', et, re.I)
                if mei:
                    try: ec = _transpile_expr(mei.group(1))
                    except Exception as e: errors.append(str(e)); break
                    i += 1
                    el = []
                    while i < len(lines) and lines[i]['indent'] > base_indent: el.append(lines[i]); i += 1
                    nbi2 = el[0]['indent'] if el else base_indent + 4
                    ec_code = _compile_body(el, errors, nbi2)
                    out.append(f'elif {ec}:')
                    for bl in ec_code.splitlines(): out.append('  ' + bl)
                elif me:
                    i += 1
                    el = []
                    while i < len(lines) and lines[i]['indent'] > base_indent: el.append(lines[i]); i += 1
                    nbi2 = el[0]['indent'] if el else base_indent + 4
                    el_code = _compile_body(el, errors, nbi2)
                    out.append('else:')
                    for bl in el_code.splitlines(): out.append('  ' + bl)
                    break
                else:
                    break
            continue

        if re.match(r'^STOP$', text, re.I):
            out.append('if not _c["done"] and not _st["done"]: _st["done"] = True; return')
            i += 1; continue

        m = re.match(r'^(?:PAY|FLOW)\s+(.+?)(?:\s+"([^"]*)")?\s*$', text, re.I)
        if m:
            raw_expr, lbl_raw = m.group(1), (m.group(2) or m.group(1))
            try: e = _transpile_expr(raw_expr)
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            lbl = lbl_raw.replace("'", "\\'")
            out.append(f"if not _c['done'] and not _st['done']: _st['flows'].append({{'v': {e}, 'lbl': '{lbl}'}})")
            i += 1; continue

        m = re.match(r'^ACCRUE\s+(.+?)(?:\s+"[^"]*")?\s*$', text, re.I)
        if m:
            try: e = _transpile_expr(m.group(1))
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            out.append(f"_c['accum'] += {e}")
            i += 1; continue

        m = re.match(r'^SET\s+([A-Za-z_]\w*)\s*=\s*(.+)$', text, re.I)
        if m:
            try: e = _transpile_expr(m.group(2))
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            out.append(f"_c['memo']['{m.group(1).upper()}'] = {e}")
            i += 1; continue

        errors.append(f'Ligne {no}: instruction inconnue: "{text}"')
        i += 1

    return '\n'.join(out) if out else 'pass'


def _parse_dates(s: str, line_no: int) -> list[float]:
    dates = []
    for part in s.split(','):
        part = part.strip()
        m = re.match(r'^([\d.]+)\.\.([\d.]+)(?::([\d.]+))?$', part)
        if m:
            start, end = float(m.group(1)), float(m.group(2))
            step = float(m.group(3)) if m.group(3) else 1.0
            t = start
            while t <= end + 1e-9:
                dates.append(round(t, 10))
                t = round(t + step, 10)
        else:
            v = part.rstrip('Yy')
            try:
                dates.append(float(v))
            except ValueError:
                raise ValueError(f'Ligne {line_no}: date invalide: "{part}"')
    return sorted(set(dates))


def parse_script(code: str) -> CompiledScript:
    raw_lines = code.split('\n')
    lines = []
    for i, raw in enumerate(raw_lines):
        # Capture the trailing comment (if any) before stripping it, so PARAM can
        # use it as a description — once stripped, '#' is gone and unrecoverable.
        m_comment = re.match(r'^([^#]*)#(.*)$', raw)
        text, comment = (m_comment.group(1).rstrip(), m_comment.group(2).strip()) \
            if m_comment else (raw.rstrip(), None)
        indent = len(raw) - len(raw.lstrip(' '))
        stripped = text.strip()
        if stripped:
            lines.append({'indent': indent, 'text': stripped, 'line_no': i + 1, 'comment': comment})

    if not lines:
        return CompiledScript(events=[], init_fn=None, params=[], constats=[])

    errors = []
    events = []
    top_stmts = []
    params = []
    constats = []
    i = 0
    exec_globals = {**_SAFE_MATH, '_basket': _basket}

    while i < len(lines):
        ln = lines[i]
        text, no = ln['text'], ln['line_no']

        if ln['indent'] != 0:
            errors.append(f'Ligne {no}: indentation 0 attendue pour "{text}"')
            i += 1; continue

        # PARAM K = 1.0  "description"  OR  # description  OR no description.
        # The trailing comment (if any) was captured before stripping, in
        # ln['comment'] — '#...' is gone from `text` by this point, so it can
        # only be recovered from there, not re-matched against `text` itself.
        m_quoted = re.match(r'^PARAM\s+([A-Za-z_]\w*)\s*=\s*([\d.]+)(%?)\s*"([^"]*)"\s*$', text, re.I)
        m_bare = re.match(r'^PARAM\s+([A-Za-z_]\w*)\s*=\s*([\d.]+)(%?)\s*$', text, re.I)
        m = m_quoted or m_bare
        if m:
            name = m.group(1).upper()
            raw_val = float(m.group(2))
            is_pct = m.group(3) == '%'
            stored = raw_val / 100 if is_pct else raw_val
            if m_quoted:
                desc = m.group(4).strip() or name
            elif ln.get('comment'):
                desc = ln['comment']
            else:
                desc = name
            params.append(Param(name=name, raw_default=raw_val, stored_val=stored, is_pct=is_pct, desc=desc))
            i += 1; continue

        # CONSTAT Name          -> single date, filled in via the UI
        # CONSTAT() Name        -> a CONSTAT() schedule (start/end/roll/freq/stub)
        # CONSTAT()() Name      -> CONSTAT() + a sub-frequency
        # Pure declarations (no inline default, unlike PARAM) — checked from
        # most to least specific so anchoring isn't load-bearing, but the
        # trailing \s+ after the parens already prevents any ambiguity.
        m = re.match(r'^CONSTAT\(\)\(\)\s+([A-Za-z_]\w*)\s*$', text, re.I)
        if m:
            constats.append(Constat(name=m.group(1).upper(), kind='nested_schedule'))
            i += 1; continue

        m = re.match(r'^CONSTAT\(\)\s+([A-Za-z_]\w*)\s*$', text, re.I)
        if m:
            constats.append(Constat(name=m.group(1).upper(), kind='schedule'))
            i += 1; continue

        m = re.match(r'^CONSTAT\s+([A-Za-z_]\w*)\s*$', text, re.I)
        if m:
            constats.append(Constat(name=m.group(1).upper(), kind='single'))
            i += 1; continue

        m = re.match(r'^SET\s+([A-Za-z_]\w*)\s*=\s*(.+)$', text, re.I)
        if m:
            try: e = _transpile_expr(m.group(2))
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            top_stmts.append(f"_c['memo']['{m.group(1).upper()}'] = {e}")
            i += 1; continue

        if re.match(r'^AT\s+MATURITY\s*:?\s*$', text, re.I):
            i += 1
            body_lines = []
            while i < len(lines) and lines[i]['indent'] > 0:
                body_lines.append(lines[i]); i += 1
            bi = body_lines[0]['indent'] if body_lines else 4
            body_code = _compile_body(body_lines, errors, bi)
            fn_src = "def _fn(_c, _st):\n"
            for bl in body_code.splitlines():
                fn_src += f"  {bl}\n"
            try:
                ns = {}
                exec(compile(fn_src, '<payscript>', 'exec'), exec_globals, ns)
                events.append(CompiledEvent(type='AT_MATURITY', dates=[], fn=ns['_fn']))
            except SyntaxError as e:
                errors.append(f'AT MATURITY compile: {e}')
            continue

        m = re.match(r'^AT\s+(.+?)\s*:?\s*$', text, re.I)
        if m:
            at_arg = m.group(1).strip()
            # AT <ConstatName>:              -> every date
            # AT <ConstatName>.first/.last:  -> just the first/last date
            # AT <ConstatName>[N]:           -> just the Nth date (1-indexed)
            # Dates aren't known yet (the real values live in the UI, not the
            # script text) — resolved later by resolve_constats(), once the
            # request supplies them.
            constat_match = re.match(r'^([A-Za-z_]\w*)(?:\.(first|last)|\[(\d+)\])?$', at_arg, re.I)
            constat_names = {c.name for c in constats}
            if constat_match and constat_match.group(1).upper() in constat_names:
                constat_ref = constat_match.group(1).upper()
                if constat_match.group(2):
                    constat_qualifier = (constat_match.group(2).lower(),)
                elif constat_match.group(3):
                    constat_qualifier = ('index', int(constat_match.group(3)))
                else:
                    constat_qualifier = None
                dates = []
            else:
                try:
                    dates = _parse_dates(at_arg, no)
                except ValueError as e:
                    errors.append(str(e)); i += 1; continue
                constat_ref = None
                constat_qualifier = None
            i += 1
            body_lines = []
            while i < len(lines) and lines[i]['indent'] > 0:
                body_lines.append(lines[i]); i += 1
            bi = body_lines[0]['indent'] if body_lines else 4
            body_code = _compile_body(body_lines, errors, bi)
            fn_src = "def _fn(_c, _st):\n"
            for bl in body_code.splitlines():
                fn_src += f"  {bl}\n"
            try:
                ns = {}
                exec(compile(fn_src, '<payscript>', 'exec'), exec_globals, ns)
                events.append(CompiledEvent(type='AT', dates=dates, fn=ns['_fn'],
                                             constat_ref=constat_ref, constat_qualifier=constat_qualifier))
            except SyntaxError as e:
                errors.append(f'AT compile: {e}')
            continue

        errors.append(f'Ligne {no}: instruction inconnue au niveau 0: "{text}"')
        i += 1

    if errors:
        raise ValueError('\n'.join(errors))

    init_fn = None
    if top_stmts:
        init_src = "def _init(_c):\n"
        for stmt in top_stmts:
            init_src += f"  {stmt}\n"
        ns = {}
        exec(compile(init_src, '<payscript_init>', 'exec'), exec_globals, ns)
        init_fn = ns['_init']

    has_stop = bool(re.search(r'^\s*STOP\s*$', code, re.I | re.MULTILINE))
    return CompiledScript(events=events, init_fn=init_fn, params=params, constats=constats,
                          has_stop=has_stop)


# ── CONSTAT resolution (Phase 2: plugged into the engine) ───────────
#
# parse_script() only sees the script TEXT — a `CONSTAT() Observations`
# declaration has no dates of its own, just a name and a kind. The actual
# start/end/roll/frequency/stub values are user input (from the UI), supplied
# separately at pricing time as `constat_values`. resolve_constats() is the
# bridge: it turns every `AT <ConstatName>:` event's constat_ref into concrete
# year-fraction dates, ready for run_mc exactly like literal `AT 1, 2, 3:`
# dates. Scripts with no constat-referencing AT are a complete no-op here.
#
# All dates are converted to T-offsets from TODAY — the same implicit t=0 the
# rest of the engine already uses everywhere (T_max is "years from now").
# Using each CONSTAT's own start_date as its private zero instead would make
# multiple CONSTATs in the same script inconsistent with each other.
def resolve_constats(script: CompiledScript, constat_values: dict) -> CompiledScript:
    """Resolve constat_ref-only events into concrete dates. Raises ValueError
    if an AT references a CONSTAT with no corresponding entry in
    constat_values, or with malformed values.

    Qualifiers (`AT Name.first:` / `.last:` / `[N]:`) pin down ONE date out of
    the full schedule, as an ADDITIONAL event at that date — `AT Name:` still
    fires there too. This mirrors how AT_MATURITY already layers on top of
    regular AT blocks: e.g. a classic Athena autocall checks the call
    condition at every date via the plain form, and ALSO runs its capital
    protection check at the last date via `.last` — both bodies run at that
    date, in script order, same mechanism step_map already uses for any two
    events that land on the same step (a STOP in the first skips the second,
    since both share the same per-path `done` flag)."""
    if not any(getattr(ev, 'constat_ref', None) for ev in script.events):
        return script   # nothing to resolve — common/simple-mode case

    from datetime import date
    from ..schedule import generate_schedule, parse_tenor, StubConvention

    today = date.today()
    constat_by_name = {c.name: c for c in script.constats}

    def _to_year_frac(d: date) -> float:
        return round((d - today).days / 365.25, 6)

    def _parse_date_field(raw: str, constat_name: str, field: str) -> date:
        if not raw:
            raise ValueError(f"CONSTAT {constat_name}: champ '{field}' manquant.")
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"CONSTAT {constat_name}: '{field}' invalide (attendu YYYY-MM-DD): {raw!r}")

    def _resolve_full(name: str) -> list[float]:
        """The complete, unfiltered date list for a CONSTAT (every date)."""
        if name not in constat_by_name:
            raise ValueError(f"CONSTAT inconnu référencé par AT: {name}")
        if name not in constat_values:
            raise ValueError(f"Valeurs manquantes pour le CONSTAT '{name}'.")
        kind = constat_by_name[name].kind
        v = constat_values[name]

        if kind == 'single':
            raw = v if isinstance(v, str) else v.get('date') if isinstance(v, dict) else None
            return [_to_year_frac(_parse_date_field(raw, name, 'date'))]

        start = _parse_date_field(v.get('start_date'), name, 'start_date')
        end = _parse_date_field(v.get('end_date'), name, 'end_date')
        roll = _parse_date_field(v.get('roll_date'), name, 'roll_date')
        if not v.get('frequency'):
            raise ValueError(f"CONSTAT {name}: champ 'frequency' manquant.")
        freq = parse_tenor(v['frequency'])
        try:
            stub = StubConvention(v.get('stub', 'short_last'))
        except ValueError:
            raise ValueError(f"CONSTAT {name}: convention de stub invalide: {v.get('stub')!r}")
        sub_freq = parse_tenor(v['sub_frequency']) if v.get('sub_frequency') else None

        result = generate_schedule(start, end, roll, freq, stub, sub_freq)
        # Drop the schedule's own start_date: it's the start of the first
        # accrual period, not itself an observation/payment date.
        return [_to_year_frac(d) for d in result['dates'][1:]]

    _cache: dict[str, list[float]] = {}

    def _full_dates(name: str) -> list[float]:
        if name not in _cache:
            _cache[name] = _resolve_full(name)
        return _cache[name]

    def _qualifier_index(qualifier: tuple, n: int, name: str) -> int:
        if constat_by_name[name].kind == 'single':
            raise ValueError(
                f"CONSTAT {name} est une date unique — .first/.last/[N] ne s'appliquent "
                f"qu'à un CONSTAT()/CONSTAT()() (plusieurs dates).")
        if qualifier[0] == 'first':
            return 0
        if qualifier[0] == 'last':
            return n - 1
        idx = qualifier[1]   # ('index', N), 1-indexed like S[i]
        if idx < 1 or idx > n:
            raise ValueError(f"CONSTAT {name}[{idx}]: index hors limites ({n} date(s) au total).")
        return idx - 1

    new_events = []
    for ev in script.events:
        if not ev.constat_ref:
            new_events.append(ev)
            continue
        dates = _full_dates(ev.constat_ref)
        if ev.constat_qualifier:
            idx = _qualifier_index(ev.constat_qualifier, len(dates), ev.constat_ref)
            resolved = [dates[idx]]
        else:
            resolved = list(dates)   # plain `AT Name:` — every date, unfiltered
        new_events.append(CompiledEvent(type=ev.type, dates=resolved, fn=ev.fn))

    return CompiledScript(events=new_events, init_fn=script.init_fn,
                           params=script.params, constats=script.constats)


def effective_T_max(script: CompiledScript, requested_T: float) -> float:
    """The simulation horizon must cover every AT event's date, or indexing
    into the simulated path array goes out of bounds. Returns
    max(requested_T, the latest date among all of this script's events) — a
    no-op when the script's dates already fit within requested_T (the
    overwhelming common case), and a safety net otherwise. This isn't
    CONSTAT-specific: a literal `AT 1, 2, 5:` with a stale/too-small Maturité
    has the exact same failure mode — CONSTAT-resolved schedules just make it
    much easier to hit in practice (the calendar's real end date can easily
    drift past whatever Maturité value happens to be sitting in the form)."""
    max_date = requested_T
    for ev in script.events:
        if ev.dates:
            max_date = max(max_date, max(ev.dates))
    return max_date
