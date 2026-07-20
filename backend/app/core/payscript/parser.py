"""
PayScript DSL parser.
Transpiles PayScript code to compiled Python event functions.

Grammar:
  PARAM NAME = value[%]   [# description]
  PARAM() NAME [= seed%]  (per-observation values: the UI supplies a table of
                           rows, one per observation, resolved by INDEX at
                           runtime; the last row extends to any further
                           observations, so one row behaves like a scalar.
                           The optional `= seed` only pre-fills row 1.)
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
    # 'scalar' (PARAM) | 'array' (PARAM() — one value per observation, the UI
    # supplies a table; stored_val/raw_default then only seed the first row).
    kind: str = 'scalar'


def _pobs(ctx, name):
    """Resolve a PARAM() value for the current observation. The UI supplies a
    list in memo; INDEX (1-based observation counter, unchanged during the
    AT MATURITY block) picks the row. The last row extends to any further
    observations — so a single row behaves exactly like a scalar PARAM, and
    AT MATURITY naturally lands on the last row. A plain scalar (user sent
    one value, or the seed default) passes through untouched."""
    v = ctx["memo"].get(name, 0)
    if isinstance(v, (list, tuple)):
        if not v:
            return 0
        idx = int(ctx.get("index", 1)) - 1
        if idx < 0:
            idx = 0
        return v[idx] if idx < len(v) else v[-1]
    return v


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
    # Monitoring contract derived from M_-prefixed PARAMs: for each, how the
    # script actually compares it — [{name, observable, direction}] where
    # direction is 'up' (condition fires when the observable rises to the
    # level — autocall-like), 'down' (fires below — KI-like) or None when the
    # usage is ambiguous/undetected. See _analyze_monitors.
    monitors: list | None = None
    # Resolved dates (year-fractions) of the reserved `CONSTAT() STRIKE_FIX`
    # fixing window, if declared — filled in by resolve_constats(), None until
    # then (and None permanently for scripts that don't declare it).
    strike_fix_dates: list[float] | None = None


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
def _transpile_expr(src: str, unknown: set | None = None,
                     array_params: set | None = None) -> str:
    """unknown, when passed, collects (uppercased) identifiers that fall
    through to the generic memo lookup below — used by parse_script() to
    flag typos (a PARAM/SET name referenced but never declared) instead of
    letting them silently price as 0. array_params holds the PARAM() names:
    those resolve through _pobs (per-observation row lookup) instead of the
    plain memo get — scalar params keep the fast direct lookup."""
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
                out.append(f'_c["spots"][int({_transpile_expr(idx, unknown, array_params)})-1]'); continue
            if u in ('S_MIN', 'S_MAX', 'S_PREV') and i < len(s) and s[i] == '[':
                idx = ''; i += 1
                while i < len(s) and s[i] != ']':
                    idx += s[i]; i += 1
                if i < len(s): i += 1
                key = {'S_MIN': 's_min', 'S_MAX': 's_max', 'S_PREV': 's_prev'}[u]
                out.append(f'_c["{key}"][int({_transpile_expr(idx, unknown, array_params)})-1]'); continue
            if u == 'AND': out.append(' and '); continue
            if u == 'OR':  out.append(' or ');  continue
            if u == 'NOT': out.append(' not '); continue
            if u == 'TRUE':  out.append('True');  continue
            if u == 'FALSE': out.append('False'); continue
            BV = {
                'WOF': 'min(_c["spots"])', 'BOF': 'max(_c["spots"])',
                'WOF_MIN': '_c["wof_min"]', 'BOF_MAX': '_c["bof_max"]',
                'FIX_MIN': '_c["fix_min"]', 'FIX_MAX': '_c["fix_max"]',
                'FIX_AVG': '_c["fix_avg"]',
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
            if unknown is not None:
                unknown.add(u)
            if array_params and u in array_params:
                out.append(f'_pobs(_c, "{u}")'); continue
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
def _compile_body(lines: list[dict], errors: list, base_indent: int = 0,
                   declared: set | None = None, unknown: dict | None = None,
                   array_params: set | None = None) -> str:
    """declared collects every SET-assigned name (uppercased); unknown maps
    every identifier that fell through to the generic memo lookup to a line
    number it was seen on. parse_script() diffs the two afterwards to flag
    typos instead of letting them silently price as 0."""
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln['indent'] < base_indent: i += 1; continue
        if ln['indent'] > base_indent: i += 1; continue
        text, no = ln['text'], ln['line_no']

        m = re.match(r'^IF\s+(.+?)\s*:?\s*$', text, re.I)
        if m:
            refs: set = set()
            try: cond = _transpile_expr(m.group(1), refs, array_params)
            except Exception as e: errors.append(f'Ligne {no}: {e}'); i += 1; continue
            if unknown is not None:
                for name in refs: unknown[name] = no
            i += 1
            body_lines = []
            while i < len(lines) and lines[i]['indent'] > base_indent:
                body_lines.append(lines[i]); i += 1
            nbi = body_lines[0]['indent'] if body_lines else base_indent + 4
            body_code = _compile_body(body_lines, errors, nbi, declared, unknown, array_params)
            out.append(f'if {cond}:')
            for bl in body_code.splitlines(): out.append('  ' + bl)
            while i < len(lines) and lines[i]['indent'] == base_indent:
                et = lines[i]['text']
                mei = re.match(r'^ELSE\s+IF\s+(.+?)\s*:?\s*$', et, re.I)
                me  = re.match(r'^ELSE\s*:?\s*$', et, re.I)
                if mei:
                    erefs: set = set()
                    try: ec = _transpile_expr(mei.group(1), erefs, array_params)
                    except Exception as e: errors.append(str(e)); break
                    if unknown is not None:
                        for name in erefs: unknown[name] = no
                    i += 1
                    el = []
                    while i < len(lines) and lines[i]['indent'] > base_indent: el.append(lines[i]); i += 1
                    nbi2 = el[0]['indent'] if el else base_indent + 4
                    ec_code = _compile_body(el, errors, nbi2, declared, unknown, array_params)
                    out.append(f'elif {ec}:')
                    for bl in ec_code.splitlines(): out.append('  ' + bl)
                elif me:
                    i += 1
                    el = []
                    while i < len(lines) and lines[i]['indent'] > base_indent: el.append(lines[i]); i += 1
                    nbi2 = el[0]['indent'] if el else base_indent + 4
                    el_code = _compile_body(el, errors, nbi2, declared, unknown, array_params)
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
            refs = set()
            try: e = _transpile_expr(raw_expr, refs)
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            if unknown is not None:
                for name in refs: unknown[name] = no
            lbl = lbl_raw.replace("'", "\\'")
            out.append(f"if not _c['done'] and not _st['done']: _st['flows'].append({{'v': {e}, 'lbl': '{lbl}'}})")
            i += 1; continue

        m = re.match(r'^ACCRUE\s+(.+?)(?:\s+"[^"]*")?\s*$', text, re.I)
        if m:
            refs = set()
            try: e = _transpile_expr(m.group(1), refs, array_params)
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            if unknown is not None:
                for name in refs: unknown[name] = no
            out.append(f"_c['accum'] += {e}")
            i += 1; continue

        m = re.match(r'^SET\s+([A-Za-z_]\w*)\s*=\s*(.+)$', text, re.I)
        if m:
            refs = set()
            try: e = _transpile_expr(m.group(2), refs, array_params)
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            if declared is not None:
                declared.add(m.group(1).upper())
            if unknown is not None:
                for name in refs: unknown[name] = no
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
    # A date <= 0 would make the engine index the path tensor from the END
    # (Python negative indexing on S_min/WOF_min) — a look-ahead, not an error
    # it can detect itself. t=0 is the pricing date: nothing observes there.
    bad = [d for d in dates if d <= 0]
    if bad:
        raise ValueError(f'Ligne {line_no}: date d\'observation invalide ({bad[0]:g}) — '
                         f'les dates AT doivent être strictement positives.')
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
    exec_globals = {**_SAFE_MATH, '_basket': _basket, '_pobs': _pobs}
    # Every PARAM/SET name ever declared, vs. every identifier that fell
    # through to the generic memo lookup (name -> a line it appeared on) —
    # diffed at the end so a typo (referenced but never declared) raises a
    # clear error instead of silently pricing as 0.
    declared: set = set()
    unknown: dict = {}

    # Pre-pass: PARAM() names must be known BEFORE any AT body is compiled
    # (the transpiler routes them through _pobs), and declaration order in the
    # script is free — a PARAM() below an AT block must still work.
    array_params: set = set()
    for ln0 in lines:
        m0 = re.match(r'^PARAM\(\)\s+([A-Za-z_]\w*)', ln0['text'], re.I)
        if m0 and ln0['indent'] == 0:
            array_params.add(m0.group(1).upper())

    while i < len(lines):
        ln = lines[i]
        text, no = ln['text'], ln['line_no']

        if ln['indent'] != 0:
            errors.append(f'Ligne {no}: indentation 0 attendue pour "{text}"')
            i += 1; continue

        # PARAM() NAME [= seed[%]] ["description" | # description] — per-
        # observation values. The seed (optional) only pre-fills the first UI
        # row; the actual rows arrive at pricing time via user_params.
        m = re.match(r'^PARAM\(\)\s+([A-Za-z_]\w*)\s*(?:=\s*([\d.]+)(%?))?\s*(?:"([^"]*)")?\s*$', text, re.I)
        if m:
            name = m.group(1).upper()
            raw_val = float(m.group(2)) if m.group(2) else 0.0
            is_pct = m.group(3) == '%' if m.group(2) else True
            stored = raw_val / 100 if is_pct else raw_val
            desc = (m.group(4) or '').strip() or ln.get('comment') or name
            params.append(Param(name=name, raw_default=raw_val, stored_val=stored,
                                is_pct=is_pct, desc=desc, kind='array'))
            declared.add(name)
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
            declared.add(name)
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
            refs: set = set()
            try: e = _transpile_expr(m.group(2), refs, array_params)
            except Exception as ex: errors.append(f'Ligne {no}: {ex}'); i += 1; continue
            declared.add(m.group(1).upper())
            for name in refs: unknown[name] = no
            top_stmts.append(f"_c['memo']['{m.group(1).upper()}'] = {e}")
            i += 1; continue

        if re.match(r'^AT\s+MATURITY\s*:?\s*$', text, re.I):
            i += 1
            body_lines = []
            while i < len(lines) and lines[i]['indent'] > 0:
                body_lines.append(lines[i]); i += 1
            bi = body_lines[0]['indent'] if body_lines else 4
            body_code = _compile_body(body_lines, errors, bi, declared, unknown, array_params)
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
            body_code = _compile_body(body_lines, errors, bi, declared, unknown, array_params)
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

    for name, line_no in unknown.items():
        if name not in declared:
            errors.append(f'Ligne {line_no}: identifiant inconnu "{name}" (ni PARAM ni SET déclaré — faute de frappe ?)')

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
    monitors = _analyze_monitors(code, [p.name for p in params if p.name.startswith('M_')])
    return CompiledScript(events=events, init_fn=init_fn, params=params, constats=constats,
                          has_stop=has_stop, monitors=monitors)


# ── M_ monitoring analysis ──────────────────────────────────────────
#
# PARAMs prefixed M_ are the script author's explicit "watch this" contract
# (used by the deals watchlist). The prefix says WHAT to watch; the DIRECTION
# and the OBSERVABLE come from how the script actually compares the param —
# `WOF >= M_AC_BAR` fires when the worst-of RISES to the level (autocall-
# like, 'up'), `WOF < M_KI_BAR` fires below it (KI-like, 'down'). Deriving
# this from usage keeps it impossible for the monitoring metadata to diverge
# from the payoff itself. Conflicting usages → direction None (the watchlist
# shows a neutral gap, no color).
_MONITOR_OBS = r'(WOF_MIN|BOF_MAX|WOF|BOF|BASKET(?:\(\))?|S\[\d+\]|S_MIN\[\d+\]|S_MAX\[\d+\])'


def _analyze_monitors(code: str, m_param_names: list[str]) -> list[dict]:
    monitors = []
    for name in m_param_names:
        found: list[tuple] = []   # (observable, direction)
        # observable OP name  — e.g. "WOF >= M_AC_BAR"
        for m in re.finditer(_MONITOR_OBS + r'\s*(>=|<=|>|<)\s*' + re.escape(name) + r'\b', code, re.I):
            obs, op = m.group(1).upper().replace('()', ''), m.group(2)
            found.append((obs, 'up' if op in ('>=', '>') else 'down'))
        # name OP observable  — e.g. "M_AC_BAR <= WOF" (level below obs = obs above level)
        for m in re.finditer(r'\b' + re.escape(name) + r'\s*(>=|<=|>|<)\s*' + _MONITOR_OBS, code, re.I):
            op, obs = m.group(1), m.group(2).upper().replace('()', '')
            found.append((obs, 'down' if op in ('>=', '>') else 'up'))

        if not found:
            monitors.append({'name': name, 'observable': None, 'direction': None})
            continue
        observables = {f[0] for f in found}
        directions = {f[1] for f in found}
        monitors.append({
            'name': name,
            'observable': found[0][0] if len(observables) == 1 else None,
            'direction': found[0][1] if len(directions) == 1 else None,
        })
    return monitors


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
def resolve_constats(script: CompiledScript, constat_values: dict,
                     anchor=None) -> CompiledScript:
    """Resolve constat_ref-only events into concrete dates. Raises ValueError
    if an AT references a CONSTAT with no corresponding entry in
    constat_values, or with malformed values.

    anchor is the date the year-fractions are measured from (default: today —
    the pre-trade pricing case). Replaying a deal booked in the past must pass
    its value_date, otherwise every calendar date lands too early by the time
    already elapsed.

    Qualifiers (`AT Name.first:` / `.last:` / `[N]:`) pin down ONE date out of
    the full schedule, as an ADDITIONAL event at that date — `AT Name:` still
    fires there too. This mirrors how AT_MATURITY already layers on top of
    regular AT blocks: e.g. a classic Athena autocall checks the call
    condition at every date via the plain form, and ALSO runs its capital
    protection check at the last date via `.last` — both bodies run at that
    date, in script order, same mechanism step_map already uses for any two
    events that land on the same step (a STOP in the first skips the second,
    since both share the same per-path `done` flag)."""
    has_strike_fix = any(c.name == 'STRIKE_FIX' for c in script.constats)
    if not has_strike_fix and not any(getattr(ev, 'constat_ref', None) for ev in script.events):
        return script   # nothing to resolve — common/simple-mode case

    from datetime import date
    from ..schedule import generate_schedule, parse_tenor, StubConvention

    today = anchor or date.today()
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

    strike_fix_dates = _full_dates('STRIKE_FIX') if has_strike_fix else None

    return CompiledScript(events=new_events, init_fn=script.init_fn,
                           params=script.params, constats=script.constats,
                           has_stop=script.has_stop, strike_fix_dates=strike_fix_dates)


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
