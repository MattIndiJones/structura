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
    # sum/len: needed by the RAW transpiled code of two built-in keywords —
    # bare BASKET() ("(sum(_c['spots'])/max(1,len(_c['spots'])))", see
    # _transpile_expr below) and N ("len(_c['spots'])", the BV table below) —
    # not just by script-callable functions. __builtins__ is deliberately {}
    # above (no sandbox escape via e.g. __import__), so anything the
    # transpiler emits by name must be listed here explicitly or it's a
    # NameError at eval time, not at parse time (parse_script never executes
    # the body, only compiles it — this class of bug is invisible until a
    # script using the keyword actually prices).
    'sum': sum, 'len': len,
}


# ── Vocabulaire du langage, énumérable ─────────────────────────────
#
# Ces tables vivaient à l'intérieur de _transpile_expr. Elles sont remontées au
# niveau module parce que deux consommateurs doivent pouvoir les LIRE et non
# seulement les exécuter : la référence de langage (docs/PAYSCRIPT_REFERENCE.md)
# et le prompt de l'assistant IA, qui décrit à un modèle ce qu'il a le droit
# d'écrire. Un test compare le vocabulaire réel à la référence, de sorte qu'un
# mot ajouté ici sans documentation — ou documenté sans exister — casse la
# construction plutôt que de produire des scripts générés systématiquement faux.
#
# Nom PayScript -> expression Python émise par le transpileur.
MARKET_VARS = {
    'WOF': 'min(_c["spots"])', 'BOF': 'max(_c["spots"])',
    'WOF_MIN': '_c["wof_min"]', 'BOF_MAX': '_c["bof_max"]',
    'ACCUM': '_c["accum"]', 'INDEX': '_c["index"]',
    'T': '_c["t"]', 'N': 'len(_c["spots"])',
    'REALVOL': '_c["realvol"]',
}

# Variables par sous-jacent, indicées de 1 à N : S[i], S_MIN[i], ...
INDEXED_VARS = ('S', 'S_MIN', 'S_MAX', 'S_PREV')

# Réductions d'une constatation sur période. Se posent sur la déclaration
# CONSTAT, jamais sur un bloc AT : la longueur de la fenêtre se saisit à
# l'écran, et un `AT 3 AVG:` n'aurait aucun endroit où la porter.
REDUCTIONS = ('MIN', 'MAX', 'AVG')
# Portée de la fenêtre. Sans ce mot, elle a une LONGUEUR, saisie à l'écran :
# « les 30 derniers jours de bourse ». Avec, elle est la PÉRIODE écoulée depuis
# la constatation précédente : « la moyenne de l'année ». Deux mots pour deux
# choses, parce qu'un lecteur ne doit pas avoir à deviner laquelle en regardant
# ailleurs dans la déclaration.
PERIOD_SCOPE = 'PERIOD'
# Le CONSTAT qui porte la fenetre de depart, celle qui fixe S0.
STRIKE_FIX_NAME = 'STRIKE_FIX'
_RED_SUFFIX = r'(?:\s+(MIN|MAX|AVG)(\s+PERIOD)?)?\s*$'


def _parse_qualifiers(raw: str) -> list[tuple] | None:
    """".last.last" / "[3]" / "" -> liste de niveaux, ou None si aucun."""
    if not raw:
        return None
    out = []
    for m in re.finditer(r'\.(first|last)|\[(\d+)\]', raw, re.I):
        out.append((m.group(1).lower(),) if m.group(1) else ('index', int(m.group(2))))
    return out or None


def _reduction_of(m: re.Match) -> tuple[str | None, str]:
    """(réduction, portée) d'une regex CONSTAT — absentes le plus souvent."""
    red, scope = m.groups()[-2], m.groups()[-1]
    if not red:
        return None, 'length'
    return red.upper(), ('period' if scope else 'length')

# Nom PayScript -> fonction du bac à sable _SAFE_MATH.
FUNCTIONS = {
    'MAX': 'max', 'MIN': 'min', 'ABS': 'abs',
    'FLOOR': 'floor', 'CEIL': 'ceil',
    'SQRT': 'sqrt', 'LOG': 'log', 'EXP': 'exp',
    'INDIC': 'int', 'ROUND': 'round',
}

# BASKET a sa propre analyse (trois formes : nu, (), (poids...)).
BASKET_KEYWORD = 'BASKET'

LOGIC_KEYWORDS = ('AND', 'OR', 'NOT', 'TRUE', 'FALSE')

# Instructions reconnues, niveau 0 (déclarations et blocs) puis corps de bloc.
TOP_LEVEL_STATEMENTS = ('PARAM', 'PARAM()', 'CONSTAT', 'CONSTAT()', 'CONSTAT()()',
                        'SET', 'AT', 'AT MATURITY')
BODY_STATEMENTS = ('IF', 'ELSE IF', 'ELSE', 'PAY', 'FLOW', 'ACCRUE', 'SET', 'STOP')


# Noms qu'un PARAM ou un SET ne peut pas porter : le transpileur les résout en
# priorité, si bien qu'un `PARAM FLOOR = 100%` compilait sans broncher puis
# évaluait `floor + 0.4` — la fonction, pas le paramètre — et mourait au pricing
# sur un TypeError Python sans rapport visible avec le script. Le template
# « Booster 3Y » livré dans l'éditeur portait exactement ce défaut.
RESERVED_NAMES = (
    frozenset(MARKET_VARS) | frozenset(FUNCTIONS) | frozenset(INDEXED_VARS)
    | frozenset(LOGIC_KEYWORDS) | {BASKET_KEYWORD}
    | frozenset(REDUCTIONS) | {PERIOD_SCOPE, STRIKE_FIX_NAME}
    | {'PARAM', 'CONSTAT', 'SET', 'AT', 'MATURITY', 'IF', 'ELSE',
       'PAY', 'FLOW', 'ACCRUE', 'STOP'}
)


def check_reserved(name: str, line_no: int, kind: str) -> str | None:
    """Message d'erreur si `name` empiète sur le vocabulaire du langage."""
    if name.upper() not in RESERVED_NAMES:
        return None
    return (f'Ligne {line_no}: "{name.upper()}" est un mot réservé du langage '
            f'— impossible de le déclarer comme {kind}. Choisissez un autre nom '
            f'(par exemple {name.upper()}_LVL).')


def language_vocabulary() -> dict[str, tuple]:
    """Tout ce qu'un script a le droit d'écrire, par catégorie. Consommé par la
    référence de langage et par le prompt de l'assistant IA — un seul endroit
    à mettre à jour quand le langage bouge."""
    return {
        'market': tuple(sorted(MARKET_VARS)),
        'indexed': INDEXED_VARS,
        'functions': tuple(sorted(FUNCTIONS)),
        'basket': (BASKET_KEYWORD,),
        'reductions': REDUCTIONS + (PERIOD_SCOPE, STRIKE_FIX_NAME),
        'logic': LOGIC_KEYWORDS,
        'top_level': TOP_LEVEL_STATEMENTS,
        'body': BODY_STATEMENTS,
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
    CompiledEvent.constat_qualifier and resolve_constats.

    reduction ('MIN' | 'MAX' | 'AVG' | None) turns every date of this CONSTAT
    into a constatation over a WINDOW instead of a single point: each
    underlying is reduced over its own window, and only then do WOF/BOF/BASKET
    aggregate. None keeps the historical behaviour, which is exactly the
    degenerate case of a one-point window. The window's LENGTH and SAMPLING
    FREQUENCY are not in the script — they are term-sheet data filled in
    through the UI, alongside the dates, so changing 10 days to 30 never edits
    a payoff. See CONSTATATIONS_PERIODE_DESIGN.md."""
    name: str
    kind: str
    reduction: str | None = None
    # 'length' — la fenêtre a une longueur, saisie à l'écran (le défaut).
    # 'period' — elle court de la constatation précédente à celle-ci, bornes
    # ouverte à gauche et fermée à droite ; seule la fréquence de relevé se
    # saisit alors, la longueur n'a plus de sens.
    window_scope: str = 'length'


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
    # Resolved dates (year-fractions) of the reserved `CONSTAT STRIKE_FIX`
    # window, if declared — filled in by resolve_constats(), None until then
    # (and None permanently for scripts that don't declare it). The window
    # DEPARTS from the strike date, unlike every other one.
    strike_fix_dates: list[float] | None = None
    # How those dates reduce to the initial level S0_i of each underlying:
    # 'MIN' | 'MAX' | 'AVG'. None with dates present is the legacy shape (the
    # script did its own `WOF / FIX_AVG`); None with no dates is the ordinary
    # product whose S0 is the strike-date close.
    strike_fix_reduction: str | None = None
    # L'échéancier contractuel résolu — voir schedule_model.Echeancier. Rempli
    # par resolve_constats(), qui est le seul endroit où les dates CALENDAIRES
    # sont encore disponibles : après lui, tout est en year-fractions. C'est
    # cette structure que le booking fige et que le cycle de vie relit, plutôt
    # que de reconstruire chacun la sienne.
    echeancier: object | None = None


@dataclass
class CompiledEvent:
    type: str
    dates: list[float]
    fn: Callable
    # Set when this event was declared as `AT <ConstatName>:` instead of literal
    # dates — `dates` is then empty until resolve_constats() fills it in from
    # the user-provided CONSTAT values (not available at parse time).
    constat_ref: str | None = None
    # Narrows constat_ref down. A LIST of levels: the first indexes the
    # calendar's constatations, an optional second indexes the relevés inside
    # that constatation's window. Each level is ('first',) | ('last',) |
    # ('index', N), N 1-indexed like S[i]. None means every date, unfiltered.
    constat_qualifier: list | None = None
    # When each date's cash actually moves, as year-fractions on the same
    # anchor as `dates` — one entry per observation. A coupon observed on the
    # 15th and paid five business days later is worth its discounted value at
    # the payment date, not at the fixing. None means "paid at observation":
    # literal `AT 1, 2, 3:` events, and CONSTAT calendars resolved without a
    # settlement calendar.
    payment_dates: list[float] | None = None
    # Constatation over a window: one list of year-fractions PER observation
    # date, aligned index by index with `dates` exactly like payment_dates.
    # Each underlying is reduced over its own window (see `reduction`) before
    # WOF/BOF/BASKET aggregate. None — the overwhelming common case — means
    # every observation reads a single point.
    window_dates: list[list[float]] | None = None
    reduction: str | None = None
    # Rang de chaque date DANS L'ÉCHÉANCIER QUE LE BLOC NOMME, aligné index par
    # index avec `dates` comme payment_dates et window_dates le sont déjà.
    # C'est ce que le script lit sous le nom `INDEX`.
    #
    # Le rang est une propriété de la DATE, pas un compteur d'exécution : la
    # troisième constatation porte 3 qu'on la price neuve ou à mi-vie, et un
    # bloc posé sur une sous-date ne décale plus rien. Un compteur global, lui,
    # additionnait les calendriers (2/4/6 au lieu de 1/2/3 sur deux calendriers)
    # et devait être réamorcé à la main en vie résiduelle — d'où `index_offset`,
    # que ceci rend inutile. Voir CONSTATATIONS_PERIODE_DESIGN.md §13.
    #
    # None sur AT_MATURITY, qui ne nomme aucun échéancier : `INDEX` y est refusé
    # à la compilation plutôt que de valoir un rang inventé.
    ranks: list[int] | None = None


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
                out.append(f'_sidx(_c["spots"], {_transpile_expr(idx, unknown, array_params)}, "S")'); continue
            if u in ('S_MIN', 'S_MAX', 'S_PREV') and i < len(s) and s[i] == '[':
                idx = ''; i += 1
                while i < len(s) and s[i] != ']':
                    idx += s[i]; i += 1
                if i < len(s): i += 1
                key = {'S_MIN': 's_min', 'S_MAX': 's_max', 'S_PREV': 's_prev'}[u]
                out.append(f'_sidx(_c["{key}"], {_transpile_expr(idx, unknown, array_params)}, "{u}")'); continue
            if u == 'AND': out.append(' and '); continue
            if u == 'OR':  out.append(' or ');  continue
            if u == 'NOT': out.append(' not '); continue
            if u == 'TRUE':  out.append('True');  continue
            if u == 'FALSE': out.append('False'); continue
            if u in MARKET_VARS: out.append(MARKET_VARS[u]); continue
            if u in FUNCTIONS: out.append(FUNCTIONS[u]); continue
            if u == BASKET_KEYWORD:
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


def _sidx(seq, idx, name: str):
    """S[i] and friends, 1-indexed with a real bounds check.

    Plain `seq[int(idx)-1]` let S[0] read seq[-1] — the LAST underlying —
    silently pricing a different product. Python's negative indexing makes the
    one wrong index in the language the only one that doesn't raise."""
    i = int(idx)
    if not 1 <= i <= len(seq):
        raise ValueError(
            f"{name}[{i}] : indice hors bornes — les sous-jacents sont "
            f"numérotés de 1 à {len(seq)}.")
    return seq[i - 1]


def _basket(ctx, *weights):
    spots = ctx['spots']
    if not weights:
        return sum(spots) / max(1, len(spots))
    # zip() truncates to the shorter side but sum(weights) counts them all, so
    # a weight vector longer than the basket used to divide by a denominator
    # that included weights no asset ever matched: BASKET(0.5, 0.5) on a single
    # underlying returned half its level, with no error anywhere.
    if len(weights) != len(spots):
        raise ValueError(
            f"BASKET : {len(weights)} poids pour {len(spots)} sous-jacent(s) — "
            f"il en faut exactement un par sous-jacent.")
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
            # array_params matters here exactly as it does for SET/IF/ACCRUE:
            # without it a per-observation PARAM() resolves to the whole list
            # instead of this observation's row, and the flow carries a list
            # that blows up on `fl["v"] * disc` — outside the evaluator's
            # try/except, so it escaped as a raw TypeError rather than a
            # PayScript error. PAY was the only statement in the language that
            # dropped it.
            try: e = _transpile_expr(raw_expr, refs, array_params)
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
            bad = check_reserved(m.group(1), no, 'variable SET')
            if bad:
                errors.append(bad); i += 1; continue
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
    exec_globals = {**_SAFE_MATH, '_basket': _basket, '_pobs': _pobs, '_sidx': _sidx}
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
            bad = check_reserved(name, no, 'PARAM()')
            if bad:
                errors.append(bad); i += 1; continue
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
            bad = check_reserved(name, no, 'PARAM')
            if bad:
                errors.append(bad); i += 1; continue
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
        m = re.match(r'^CONSTAT\(\)\(\)\s+([A-Za-z_]\w*)' + _RED_SUFFIX, text, re.I)
        if m:
            _red, _scope = _reduction_of(m)
            constats.append(Constat(name=m.group(1).upper(), kind='nested_schedule',
                                    reduction=_red, window_scope=_scope))
            i += 1; continue

        m = re.match(r'^CONSTAT\(\)\s+([A-Za-z_]\w*)' + _RED_SUFFIX, text, re.I)
        if m:
            _red, _scope = _reduction_of(m)
            constats.append(Constat(name=m.group(1).upper(), kind='schedule',
                                    reduction=_red, window_scope=_scope))
            i += 1; continue

        m = re.match(r'^CONSTAT\s+([A-Za-z_]\w*)' + _RED_SUFFIX, text, re.I)
        if m:
            _red, _scope = _reduction_of(m)
            constats.append(Constat(name=m.group(1).upper(), kind='single',
                                    reduction=_red, window_scope=_scope))
            i += 1; continue

        m = re.match(r'^SET\s+([A-Za-z_]\w*)\s*=\s*(.+)$', text, re.I)
        if m:
            bad = check_reserved(m.group(1), no, 'variable SET')
            if bad:
                errors.append(bad); i += 1; continue
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
            # AT <ConstatName>.last.last:    -> the last RELEVÉ of the last
            #   constatation — a second level descends from the calendar into
            #   the window. One qualifier names a constatation, and reads what
            #   the CONSTAT declares (the reduction); two name one fixing
            #   inside its window, and read the raw close. That is how a PDI
            #   observed on the closing price coexists with a coupon observed
            #   on an average, at the same date, in the same calendar — and
            #   with a single set of dates, which two CONSTAT would not give.
            # Dates aren't known yet (the real values live in the UI, not the
            # script text) — resolved later by resolve_constats(), once the
            # request supplies them.
            constat_match = re.match(
                r'^([A-Za-z_]\w*)((?:\.(?:first|last)|\[\d+\])*)$', at_arg, re.I)
            constat_names = {c.name for c in constats}
            if constat_match and constat_match.group(1).upper() in constat_names:
                constat_ref = constat_match.group(1).upper()
                constat_qualifier = _parse_qualifiers(constat_match.group(2))
                if constat_qualifier and len(constat_qualifier) > 2:
                    errors.append(
                        f'Ligne {no}: "{at_arg}" — au plus deux niveaux de '
                        f'qualificateur (le calendrier, puis la fenêtre de '
                        f'constatation).')
                    i += 1; continue
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
                events.append(CompiledEvent(
                    type='AT', dates=dates, fn=ns['_fn'],
                    constat_ref=constat_ref, constat_qualifier=constat_qualifier,
                    # `AT 1, 2, 3:` — le calendrier du bloc EST sa liste de dates.
                    ranks=list(range(1, len(dates) + 1)) if dates else None))
            except SyntaxError as e:
                errors.append(f'AT compile: {e}')
            continue

        errors.append(f'Ligne {no}: instruction inconnue au niveau 0: "{text}"')
        i += 1

    for name, line_no in unknown.items():
        if name not in declared:
            errors.append(f'Ligne {line_no}: identifiant inconnu "{name}" (ni PARAM ni SET déclaré — faute de frappe ?)')

    # Portée du rang d'observation : deux écritures le rendent indéfini.
    errors.extend(_verifier_portee_du_rang(_blocs_et_references(lines), array_params))

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

    # Détecté sur les lignes DÉCOMMENTÉES, exactement comme _compile_body le
    # fait : la recherche portait sur le texte brut, si bien qu'un
    # `STOP  # le contrat s'arrête ici` — écriture idiomatique — compilait bien
    # un arrêt mais laissait has_stop à False. Le produit se pricait juste et se
    # décrivait faux : durée de vie espérée non calculée (engine.run_mc), rappel
    # anticipé absent du fichier réglementaire EMT (api/emt.py: has_autocall),
    # détection de cycle de vie muette (api/deals.py).
    has_stop = any(re.match(r'^STOP$', ln['text'], re.I) for ln in lines)
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


def _blocs_et_references(lines: list[dict]) -> list[tuple[str | None, set[str]]]:
    """(échéancier visé, identifiants lus) pour chaque bloc `AT` du script.

    Analyse du TEXTE, comme `_analyze_monitors` : ce qu'on cherche ici — quel
    bloc lit quoi — n'existe pas dans les fonctions compilées, qui ne sont plus
    que du code Python.

    L'échéancier visé est le nom du CONSTAT (qualificateurs retirés : `OBS.last`
    et `OBS[2][1]` visent tous deux OBS), `None` pour un bloc à dates littérales
    — dont l'échéancier est sa propre liste de dates, donc le rang y est défini —
    et la chaîne `MATURITY` pour `AT MATURITY`, seul bloc qui ne relève d'aucun
    échéancier."""
    out: list[tuple[str | None, set[str]]] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'^AT\s+(.+?)\s*:?\s*$', ln['text'], re.I) if ln['indent'] == 0 else None
        if not m:
            i += 1
            continue
        cible = m.group(1).strip()
        if re.match(r'^MATURITY$', cible, re.I):
            nom = 'MATURITY'
        else:
            mc = re.match(r'^([A-Za-z_]\w*)', cible)
            nom = mc.group(1).upper() if mc and not cible[0].isdigit() else None
        refs: set[str] = set()
        i += 1
        while i < len(lines) and lines[i]['indent'] > 0:
            refs.update(w.upper() for w in re.findall(r'[A-Za-z_]\w*', lines[i]['text']))
            i += 1
        out.append((nom, refs))
    return out


def _verifier_portee_du_rang(blocs, array_param_names) -> list[str]:
    """Erreurs de portée du rang d'observation — voir §13 de la note de
    conception. `INDEX` est le rang de la date dans l'échéancier que le bloc
    nomme ; deux écritures rendent ce rang indéfini, et sont refusées plutôt que
    servies par un nombre inventé."""
    errs = []
    for nom, refs in blocs:
        if nom == 'MATURITY' and 'INDEX' in refs:
            errs.append(
                "INDEX dans un bloc qui ne nomme aucun échéancier : le rang "
                "d'observation se compte DANS un calendrier. Utilisez "
                "`AT <Calendrier>.last:` plutôt que `AT MATURITY:`.")
    # Un PARAM() lu depuis deux calendriers différents n'a plus de nombre de
    # lignes défini : trois valeurs ici, une autre là. Refusé plutôt que deviné.
    for nom_param in array_param_names:
        cals = {nom for nom, refs in blocs
                if nom and nom != 'MATURITY' and nom_param in refs}
        if len(cals) > 1:
            errs.append(
                f"PARAM() {nom_param} est lu depuis plusieurs calendriers "
                f"({', '.join(sorted(cals))}) : « une valeur par observation » "
                f"n'a alors plus de nombre de lignes défini. Déclarez un "
                f"PARAM() par calendrier, ou visez une date précise avec "
                f"`AT <Calendrier>.last:`.")
    return errs


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
def resolve_analysis_constats(compiled, req):
    """Resout le calendrier d'une requete d'analyse EXACTEMENT comme le prix.

    Toutes les analytiques derivees d'un script — profil de payoff, chemins MC,
    probabilites, Mark-to-Future, backtest, solveur, grille, scenarios — doivent
    voir le meme produit que /api/price. Chacune appelait `resolve_constats`
    avec le seul `anchor`, sans devise : un CONSTAT portant un decalage de
    reglement les faisait toutes echouer, et un ancrage sur la value date leur
    aurait de toute facon donne un calendrier decale de quelques jours.

    Passer par ici plutot que d'appeler `resolve_constats` directement est ce
    qui empeche ces dix points d'appel de rediverger au prochain chantier.

    L'origine suit la meme regle qu'ailleurs : la date de STRIKE, ou `anchor`
    en repli pour les appelants qui n'en declarent pas.
    """
    return resolve_constats(compiled, req.constats, anchor=analysis_origin(req),
                            currency=getattr(req, "settlement_ccy", None))


def analysis_origin(req):
    """Origine de l'axe des temps d'une requete : la date de STRIKE.

    Repli sur `anchor` pour les appelants qui ne declarent pas de strike, puis
    sur aujourd'hui. Expose separement parce que /api/price a besoin de la
    valeur elle-meme, pour situer la date de paiement et la value date sur le
    meme axe que les constatations.
    """
    from datetime import date as _date
    return (getattr(req, "strike_date", None)
            or getattr(req, "anchor", None)
            or _date.today())


def resolve_constats(script: CompiledScript, constat_values: dict,
                     anchor=None, currency: str | None = None) -> CompiledScript:
    """Resolve constat_ref-only events into concrete dates. Raises ValueError
    if an AT references a CONSTAT with no corresponding entry in
    constat_values, or with malformed values.

    anchor is the date the year-fractions are measured from (default: today —
    the pre-trade pricing case). Replaying a deal booked in the past must pass
    its value_date, otherwise every calendar date lands too early by the time
    already elapsed.

    currency names the settlement calendar. Each CONSTAT then carries its own
    date handling, alongside its dates and frequency:
      convention — how a date that is not a business day is moved onto one.
                   Absent means no adjustment: a date fixed by a term sheet on
                   a closed day stays where the term sheet put it. There is no
                   global default, because two calendars of the same product
                   legitimately roll differently.
      settlement_lag — business days between an observation and the movement of
                   its cash, which produces every flow's payment date.
    Without a currency, dates stay raw calendar dates and flows are paid at
    observation — the historical behaviour, kept for callers with no currency
    to offer.

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
        # Rien à résoudre — mode simple, dates écrites en dur. L'échéancier se
        # construit quand même : un produit en mode normal se booke, se suit et
        # s'affiche comme les autres, et ses dates sont déjà là.
        from .schedule_model import construire as _construire_echeancier
        script.echeancier = _construire_echeancier(script)
        return script

    from datetime import date
    from ..calendars import BusinessDayConvention, add_business_days, adjust
    from ..schedule import (generate_schedule, observation_window, parse_tenor,
                            period_windows, StubConvention)

    today = anchor or date.today()

    def _convention(name: str, v) -> BusinessDayConvention:
        raw = v.get('convention') if isinstance(v, dict) else None
        if not raw:
            return BusinessDayConvention.NONE
        try:
            return BusinessDayConvention(raw)
        except ValueError:
            raise ValueError(
                f"CONSTAT {name}: convention de jour ouvré inconnue: {raw!r} "
                f"(attendu {', '.join(c.value for c in BusinessDayConvention)}).")
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

    def _resolve_full(name: str) -> tuple[list[float], list[float], list[date]]:
        """Observation dates and their payment dates for a CONSTAT, unfiltered.

        The absolute observation dates come back alongside the year-fractions
        because a constatation window is built in calendar space — business
        days off the observation date — and only then converted."""
        if name not in constat_by_name:
            raise ValueError(f"CONSTAT inconnu référencé par AT: {name}")
        if name not in constat_values:
            raise ValueError(f"Valeurs manquantes pour le CONSTAT '{name}'.")
        kind = constat_by_name[name].kind
        v = constat_values[name]

        lag = int(v.get('settlement_lag') or 0) if isinstance(v, dict) else 0
        conv = _convention(name, v)

        if kind == 'single':
            raw = v if isinstance(v, str) else v.get('date') if isinstance(v, dict) else None
            observed = _parse_date_field(raw, name, 'date')
            if currency:
                observed = adjust(observed, currency, conv)
                paid = add_business_days(observed, lag, currency)
            elif lag:
                raise ValueError(
                    f"CONSTAT {name}: un décalage de règlement suppose un calendrier — "
                    f"précisez la devise de règlement.")
            else:
                paid = observed
            return [_to_year_frac(observed)], [_to_year_frac(paid)], [observed]

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

        result = generate_schedule(start, end, roll, freq, stub, sub_freq,
                                   currency=currency, convention=conv,
                                   settlement_lag=lag)
        # Drop the schedule's own start_date: it's the start of the first
        # accrual period, not itself an observation/payment date.
        return ([_to_year_frac(d) for d in result['dates'][1:]],
                [_to_year_frac(d) for d in result['payment_dates'][1:]],
                list(result['dates'][1:]))

    _cache: dict[str, tuple[list[float], list[float], list[date]]] = {}

    def _full_dates(name: str) -> tuple[list[float], list[float], list[date]]:
        if name not in _cache:
            _cache[name] = _resolve_full(name)
        return _cache[name]

    def _window_tenors(name: str) -> tuple:
        """(length, frequency) of a CONSTAT's constatation window, from the UI.

        A PERIOD window has no length — it runs from one constatation to the
        next — so only the sampling frequency is read."""
        v = constat_values.get(name) or {}
        if not isinstance(v, dict):
            v = {}
        freq = parse_tenor(v.get('window_frequency') or '1D')
        if constat_by_name[name].window_scope == 'period':
            return None, freq
        raw_len = v.get('window_length')
        if not raw_len:
            raise ValueError(
                f"CONSTAT {name}: une réduction {constat_by_name[name].reduction} est "
                f"déclarée dans le script mais la longueur de la fenêtre de constatation "
                f"n'est pas renseignée (champ 'window_length', ex. '30D').")
        return parse_tenor(raw_len), freq

    def _period_grid(name: str) -> tuple[list[date], list[list[date]]]:
        """Constatations et relevés d'un CONSTAT à fenêtre de PÉRIODE."""
        v = constat_values[name]
        _, freq = _window_tenors(name)
        return period_windows(
            _parse_date_field(v.get('start_date'), name, 'start_date'),
            _parse_date_field(v.get('end_date'), name, 'end_date'),
            _parse_date_field(v.get('roll_date'), name, 'roll_date'),
            parse_tenor(v['frequency']),
            StubConvention(v.get('stub', 'short_last')),
            freq, currency=currency, convention=_convention(name, v))

    def _windows_dates(name: str, observed: list[date]) -> list[list[date]] | None:
        """Une fenêtre par constatation, en dates. None si ce CONSTAT ne
        déclare aucune réduction — le cas ponctuel ordinaire."""
        c = constat_by_name[name]
        if not c.reduction:
            return None
        if c.window_scope == 'period':
            if c.kind == 'single':
                raise ValueError(
                    f"CONSTAT {name}: une fenêtre de PÉRIODE court d'une constatation "
                    f"à la suivante — elle suppose un calendrier CONSTAT(), pas une "
                    f"date unique. Retirez PERIOD et donnez une longueur de fenêtre.")
            if c.kind == 'nested_schedule':
                # Deux grilles fines pour un seul calendrier : la sous-fréquence
                # du CONSTAT()() et la fréquence de relevé de la fenêtre. Elles
                # ne peuvent pas décrire la même chose, et l'une serait ignorée
                # en silence — le genre d'hypothèse saisissable et sans effet
                # que la règle A7 dit de traquer.
                raise ValueError(
                    f"CONSTAT {name}: PERIOD et une sous-fréquence CONSTAT()() se "
                    f"contredisent — la sous-fréquence produit des OBSERVATIONS, la "
                    f"fenêtre de période des RELEVÉS moyennés. Choisissez : "
                    f"CONSTAT() {name} {c.reduction} PERIOD pour moyenner sur la "
                    f"période, ou CONSTAT()() {name} sans PERIOD pour observer à la "
                    f"sous-fréquence.")
            return _period_grid(name)[1]
        length, freq = _window_tenors(name)
        v = constat_values.get(name) or {}
        conv = _convention(name, v)
        # STRIKE_FIX is the one window that DEPARTS from its date: it fixes S0
        # going forward. Every other constatation ARRIVES at its date.
        forward = (name == 'STRIKE_FIX')
        return [observation_window(obs, length, freq, forward=forward,
                                   currency=currency, convention=conv)
                for obs in observed]

    def _windows_for(name: str, observed: list[date]) -> list[list[float]] | None:
        w = _windows_dates(name, observed)
        return None if w is None else [[_to_year_frac(d) for d in win] for win in w]

    def _pick(qualifier: tuple, n: int, label: str) -> int:
        """Index 0-based désigné par un niveau de qualificateur."""
        if qualifier[0] == 'first':
            return 0
        if qualifier[0] == 'last':
            return n - 1
        idx = qualifier[1]   # ('index', N), 1-indexed like S[i]
        if idx < 1 or idx > n:
            raise ValueError(f"{label}[{idx}]: index hors limites ({n} date(s) au total).")
        return idx - 1

    def _qualifier_index(qualifier: tuple, n: int, name: str) -> int:
        if constat_by_name[name].kind == 'single':
            raise ValueError(
                f"CONSTAT {name} est une date unique — .first/.last/[N] ne s'appliquent "
                f"qu'à un CONSTAT()/CONSTAT()() (plusieurs dates).")
        return _pick(qualifier, n, f"CONSTAT {name}")

    new_events = []
    for ev in script.events:
        if not ev.constat_ref:
            new_events.append(ev)
            continue
        name = ev.constat_ref
        dates, payments, observed = _full_dates(name)
        win_dates = _windows_dates(name, observed)
        windows = None if win_dates is None else [
            [_to_year_frac(d) for d in w] for w in win_dates]
        quals = ev.constat_qualifier or []
        reduction = constat_by_name[name].reduction
        # Le rang suit la CONSTATATION, jamais le relevé : `AT X[2][1]` parle du
        # deuxième coupon même s'il lit le premier relevé de sa fenêtre.
        if len(quals) >= 2:
            # Deuxième niveau : on ne vise plus une constatation mais UN RELEVÉ
            # dans sa fenêtre. L'événement lit alors le cours de ce jour-là, pas
            # la réduction — c'est ce qui permet à un PDI sur clôture de cohabiter
            # avec un coupon sur moyenne, même date, même calendrier.
            if win_dates is None:
                raise ValueError(
                    f"CONSTAT {name}: un second qualificateur descend dans la fenêtre "
                    f"de constatation, mais ce CONSTAT n'en déclare aucune (il faudrait "
                    f"MIN, MAX ou AVG sur sa déclaration).")
            k = _qualifier_index(quals[0], len(dates), name)
            w = win_dates[k]
            j = _pick(quals[1], len(w), f"CONSTAT {name} (relevés)")
            resolved = [_to_year_frac(w[j])]
            # Le règlement suit la CONSTATATION, pas le relevé : c'est elle qui
            # déclenche le flux.
            resolved_pay, resolved_win, reduction = [payments[k]], None, None
            resolved_ranks = [k + 1]
        elif quals:
            k = _qualifier_index(quals[0], len(dates), name)
            resolved, resolved_pay = [dates[k]], [payments[k]]
            resolved_win = [windows[k]] if windows else None
            # Le rang dans le CALENDRIER, pas dans le bloc : `AT X.last:` sur un
            # calendrier de trois dates vaut 3, sinon l'idiome Athena — dernier
            # coupon `COUPON * INDEX` — paierait un coupon au lieu de trois.
            resolved_ranks = [k + 1]
        else:
            # plain `AT Name:` — every date, unfiltered
            resolved, resolved_pay = list(dates), list(payments)
            resolved_win = list(windows) if windows else None
            resolved_ranks = list(range(1, len(dates) + 1))
        new_events.append(CompiledEvent(
            type=ev.type, dates=resolved, fn=ev.fn,
            constat_ref=name, constat_qualifier=ev.constat_qualifier,
            payment_dates=resolved_pay if currency else None,
            window_dates=resolved_win, reduction=reduction,
            ranks=resolved_ranks))

    strike_fix_dates = strike_fix_reduction = None
    if has_strike_fix:
        red = constat_by_name['STRIKE_FIX'].reduction
        if red:
            # A reduction turns STRIKE_FIX into a real window around one date;
            # its own schedule (if it was declared as CONSTAT()) is then only
            # the anchor, and the window is what the UI supplies.
            _, _, observed = _full_dates('STRIKE_FIX')
            strike_fix_dates = _windows_for('STRIKE_FIX', observed)[0]
            strike_fix_reduction = red
        else:
            strike_fix_dates = _full_dates('STRIKE_FIX')[0]

    resolu = CompiledScript(events=new_events, init_fn=script.init_fn,
                            params=script.params, constats=script.constats,
                            has_stop=script.has_stop, monitors=script.monitors,
                            strike_fix_dates=strike_fix_dates,
                            strike_fix_reduction=strike_fix_reduction)

    # L'échéancier contractuel, bâti ICI parce que c'est le dernier endroit où
    # les dates calendaires existent encore : `_full_dates` les a, `_windows_dates`
    # aussi, et tout ce qui suit ne manipule plus que des year-fractions. Les
    # reconstruire plus tard supposerait de re-choisir une origine — l'erreur
    # d'ancrage qui est revenue cinq fois en une seule session.
    from .schedule_model import construire as _construire_echeancier
    jours, fenetres = {}, {}
    for c in script.constats:
        if c.name not in constat_values:
            continue
        try:
            _, _, observed = _full_dates(c.name)
        except ValueError:
            continue
        # Les dates de paiement calendaires ne sont pas conservées par
        # _full_dates — seules leurs year-fractions le sont. La constatation les
        # portera le jour où le booking en aura besoin.
        jours[c.name] = (observed, [])
        w = _windows_dates(c.name, observed)
        if w is not None:
            fenetres[c.name] = w
    resolu.echeancier = _construire_echeancier(resolu, jours, fenetres)
    return resolu


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
