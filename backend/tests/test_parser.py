"""Tests for the PayScript parser."""
import math
import pytest
from datetime import date, timedelta
from backend.app.core.payscript.parser import (
    parse_script, resolve_constats, effective_T_max, CompiledScript,
)


SIMPLE_VANILLA = """
PARAM K = 1.0 "strike"
PARAM T = 1   "maturity"

AT MATURITY
  PAY MAX(S[1] - K, 0) "payoff"
"""

AUTOCALL = """
PARAM barrier = 1.0  "barrier"
PARAM coupon  = 10%  "coupon"

AT 1, 2, 3
  IF S[1] >= barrier
    PAY 1 + coupon * INDEX "recall"
    STOP

AT MATURITY
  PAY MAX(S[1] - 1, 0) "residual"
"""

RANGE_ACCRUAL = """
PARAM lo = 0.90  "lower bound"
PARAM hi = 1.10  "upper bound"

AT 0.5..3:0.5
  IF S[1] >= lo AND S[1] <= hi
    ACCRUE 0.05 "accrual"

AT MATURITY
  PAY ACCUM "total coupon"
"""

INVALID_SCRIPT = """
AT 1
  UNKNOWNCMD x
"""


def test_parse_vanilla():
    cs = parse_script(SIMPLE_VANILLA)
    assert len(cs.params) == 2
    assert cs.params[0].name == 'K'
    assert cs.params[0].stored_val == pytest.approx(1.0)
    assert len(cs.events) == 1
    assert cs.events[0].type == 'AT_MATURITY'


def test_parse_autocall():
    cs = parse_script(AUTOCALL)
    assert len(cs.params) == 2
    at_events = [e for e in cs.events if e.type == 'AT']
    mat_events = [e for e in cs.events if e.type == 'AT_MATURITY']
    assert len(at_events) == 1
    assert at_events[0].dates == [1.0, 2.0, 3.0]
    assert len(mat_events) == 1


def test_parse_range_accrual():
    cs = parse_script(RANGE_ACCRUAL)
    at_events = [e for e in cs.events if e.type == 'AT']
    assert len(at_events) == 1
    dates = at_events[0].dates
    assert dates == pytest.approx([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])


def test_params_pct_detection():
    cs = parse_script(AUTOCALL)
    coupon_p = next(p for p in cs.params if p.name == 'COUPON')
    assert coupon_p.is_pct is True
    assert coupon_p.stored_val == pytest.approx(0.10)


def test_constat_single():
    cs = parse_script('CONSTAT TradeDate\nAT MATURITY:\n  PAY 1')
    assert len(cs.constats) == 1
    assert cs.constats[0].name == 'TRADEDATE'
    assert cs.constats[0].kind == 'single'


def test_constat_schedule():
    cs = parse_script('CONSTAT() Observations\nAT MATURITY:\n  PAY 1')
    assert len(cs.constats) == 1
    assert cs.constats[0].name == 'OBSERVATIONS'
    assert cs.constats[0].kind == 'schedule'


def test_constat_nested_schedule():
    cs = parse_script('CONSTAT()() Observations\nAT MATURITY:\n  PAY 1')
    assert len(cs.constats) == 1
    assert cs.constats[0].name == 'OBSERVATIONS'
    assert cs.constats[0].kind == 'nested_schedule'


def test_constat_mixed_with_params_and_multiple_kinds():
    script = """
PARAM COUPON = 8%
CONSTAT TradeDate
CONSTAT() Observations
CONSTAT()() SubObs
PARAM BARRIER = 60%

AT MATURITY:
  PAY 1
"""
    cs = parse_script(script)
    assert [p.name for p in cs.params] == ['COUPON', 'BARRIER']
    kinds = {c.name: c.kind for c in cs.constats}
    assert kinds == {'TRADEDATE': 'single', 'OBSERVATIONS': 'schedule', 'SUBOBS': 'nested_schedule'}


def test_no_constat_gives_empty_list():
    cs = parse_script(SIMPLE_VANILLA)
    assert cs.constats == []


def test_param_description_quoted_form():
    cs = parse_script('PARAM K = 5% "five percent"\nAT MATURITY:\n  PAY 1')
    assert cs.params[0].desc == 'five percent'


def test_param_description_comment_form():
    """The '# desc' form used to be dead code: the comment was stripped from the
    line before the PARAM regex ever saw it, so it always fell back to the param
    name. Regression test for the fix."""
    cs = parse_script('PARAM K = 5% # five percent\nAT MATURITY:\n  PAY 1')
    assert cs.params[0].desc == 'five percent'


def test_param_description_falls_back_to_name():
    cs = parse_script('PARAM K = 5%\nAT MATURITY:\n  PAY 1')
    assert cs.params[0].desc == 'K'


def test_events_callable():
    cs = parse_script(AUTOCALL)
    ev = next(e for e in cs.events if e.type == 'AT')
    ctx = {
        'spots': [1.05],
        'accum': 0.0,
        'index': 1,
        'wof_min': 1.05,
        'bof_max': 1.05,
        't': 1.0,
        'done': False,
        'memo': {'BARRIER': 1.0, 'COUPON': 0.10},
        'total_cf': 0.0,
    }
    st = {'flows': [], 'done': False}
    ev.fn(ctx, st)
    assert len(st['flows']) == 1
    assert st['flows'][0]['v'] == pytest.approx(1.1)
    assert st['done'] is True


def test_at_maturity_payoff():
    cs = parse_script(SIMPLE_VANILLA)
    ev = cs.events[0]
    ctx = {
        'spots': [1.10],
        'accum': 0.0,
        'index': 0,
        'wof_min': 1.10,
        'bof_max': 1.10,
        't': 1.0,
        'done': False,
        'memo': {'K': 1.0, 'T': 1.0},
        'total_cf': 0.0,
    }
    st = {'flows': [], 'done': False}
    ev.fn(ctx, st)
    assert st['flows'][0]['v'] == pytest.approx(0.10)


def test_at_maturity_otm():
    cs = parse_script(SIMPLE_VANILLA)
    ev = cs.events[0]
    ctx = {
        'spots': [0.90],
        'accum': 0.0,
        'index': 0,
        'wof_min': 0.90,
        'bof_max': 0.90,
        't': 1.0,
        'done': False,
        'memo': {'K': 1.0, 'T': 1.0},
        'total_cf': 0.0,
    }
    st = {'flows': [], 'done': False}
    ev.fn(ctx, st)
    total = sum(f['v'] for f in st['flows'])
    assert total == pytest.approx(0.0)


def test_invalid_body_raises():
    with pytest.raises(ValueError):
        parse_script(INVALID_SCRIPT)


# ── AT <ConstatName>: recognition + resolve_constats (Phase 2) ─────

def test_at_recognizes_declared_constat_name():
    cs = parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1')
    assert len(cs.events) == 1
    assert cs.events[0].constat_ref == 'OBSERVATIONS'
    assert cs.events[0].dates == []


def test_at_literal_dates_unaffected_by_constat_presence():
    """A script can mix a CONSTAT declaration with ordinary literal AT dates —
    only AT clauses that are themselves a bare matching name get deferred."""
    cs = parse_script('CONSTAT() Observations\nAT 1, 2, 3:\n  PAY 1')
    assert cs.events[0].constat_ref is None
    assert cs.events[0].dates == [1.0, 2.0, 3.0]


def test_resolve_constats_noop_without_constat_ref():
    cs = parse_script('AT 1, 2, 3:\n  PAY 1')
    resolved = resolve_constats(cs, {})
    assert resolved is cs   # short-circuits, same object


def test_resolve_constats_unknown_name_raises():
    cs = parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1')
    with pytest.raises(ValueError, match='manquantes'):
        resolve_constats(cs, {})


def test_resolve_constats_single():
    cs = parse_script('CONSTAT TradeDate\nAT TradeDate:\n  PAY 1')
    target = date.today() + timedelta(days=365)
    resolved = resolve_constats(cs, {'TRADEDATE': target.isoformat()})
    assert resolved.events[0].dates == [pytest.approx(1.0, abs=0.01)]
    assert resolved.events[0].constat_ref is None


def test_resolve_constats_schedule_excludes_start_date():
    """The schedule's own start_date is the beginning of the first accrual
    period, not an observation date — it must not appear in resolved dates."""
    cs = parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1')
    today = date.today()
    end = today + timedelta(days=365 * 3)
    resolved = resolve_constats(cs, {
        'OBSERVATIONS': {
            'start_date': today.isoformat(), 'end_date': end.isoformat(),
            'roll_date': today.isoformat(), 'frequency': '1Y', 'stub': 'short_last',
        },
    })
    dates = resolved.events[0].dates
    assert len(dates) == 3
    assert all(d > 0 for d in dates)
    assert dates == sorted(dates)


def test_resolve_constats_nested_schedule_sub_frequency():
    cs = parse_script('CONSTAT()() Observations\nAT Observations:\n  PAY 1')
    today = date.today()
    end = today + timedelta(days=365)
    resolved = resolve_constats(cs, {
        'OBSERVATIONS': {
            'start_date': today.isoformat(), 'end_date': end.isoformat(),
            'roll_date': today.isoformat(), 'frequency': '6M', 'stub': 'short_last',
            'sub_frequency': '1M',
        },
    })
    # ~6 monthly sub-dates per half-year x 2 halves, minus the dropped start_date
    assert len(resolved.events[0].dates) >= 10


# ── AT Constat.first / .last / [N] qualifiers ───────────────────────

def _values_4y(start, end):
    return {'OBSERVATIONS': {
        'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'roll_date': start.isoformat(), 'frequency': '1Y', 'stub': 'short_last',
    }}


def test_at_qualifier_parsing_first_last_index():
    cs = parse_script(
        'CONSTAT() Observations\n'
        'AT Observations.first:\n  PAY 1\n'
        'AT Observations.last:\n  PAY 2\n'
        'AT Observations[3]:\n  PAY 3\n'
        'AT Observations:\n  PAY 4\n'
    )
    quals = [ev.constat_qualifier for ev in cs.events]
    assert quals == [('first',), ('last',), ('index', 3), None]
    assert all(ev.constat_ref == 'OBSERVATIONS' for ev in cs.events)


def test_qualifier_first_resolves_to_first_date():
    cs = parse_script('CONSTAT() Observations\nAT Observations.first:\n  PAY 1')
    today = date.today()
    resolved = resolve_constats(cs, _values_4y(today, today + timedelta(days=365 * 4)))
    full = resolve_constats(parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1'),
                             _values_4y(today, today + timedelta(days=365 * 4)))
    assert resolved.events[0].dates == [full.events[0].dates[0]]


def test_qualifier_last_resolves_to_last_date():
    cs = parse_script('CONSTAT() Observations\nAT Observations.last:\n  PAY 1')
    today = date.today()
    resolved = resolve_constats(cs, _values_4y(today, today + timedelta(days=365 * 4)))
    full = resolve_constats(parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1'),
                             _values_4y(today, today + timedelta(days=365 * 4)))
    assert resolved.events[0].dates == [full.events[0].dates[-1]]


def test_qualifier_index_is_one_indexed():
    cs = parse_script('CONSTAT() Observations\nAT Observations[3]:\n  PAY 1')
    today = date.today()
    resolved = resolve_constats(cs, _values_4y(today, today + timedelta(days=365 * 4)))
    full = resolve_constats(parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1'),
                             _values_4y(today, today + timedelta(days=365 * 4)))
    assert resolved.events[0].dates == [full.events[0].dates[2]]   # 1-indexed 3rd = Python index 2


def test_unqualified_block_is_additive_with_qualified_blocks():
    """The core promise (classic Athena pattern): `AT Name:` still fires at
    EVERY date, including the one a qualified block also targets — `.last`
    adds an extra event there, it doesn't carve that date out of the plain
    form. Mirrors how AT_MATURITY already layers on top of regular AT."""
    cs = parse_script(
        'CONSTAT() Observations\n'
        'AT Observations:\n  PAY 1\n'
        'AT Observations.last:\n  PAY 2\n'
    )
    today = date.today()
    resolved = resolve_constats(cs, _values_4y(today, today + timedelta(days=365 * 4)))
    plain_dates, last_dates = resolved.events[0].dates, resolved.events[1].dates
    assert len(plain_dates) == 4   # all 4 dates, unfiltered
    assert len(last_dates) == 1
    assert last_dates[0] == plain_dates[-1]   # the same date, fired by both blocks


def test_qualifier_index_out_of_range_raises():
    cs = parse_script('CONSTAT() Observations\nAT Observations[99]:\n  PAY 1')
    today = date.today()
    with pytest.raises(ValueError, match='hors limites'):
        resolve_constats(cs, _values_4y(today, today + timedelta(days=365 * 4)))


def test_qualifier_on_single_constat_raises():
    cs = parse_script('CONSTAT TradeDate\nAT TradeDate.last:\n  PAY 1')
    with pytest.raises(ValueError, match='date unique'):
        resolve_constats(cs, {'TRADEDATE': date.today().isoformat()})


# ── effective_T_max ──────────────────────────────────────────────

def test_effective_t_max_noop_when_dates_fit():
    """When every event date already fits within requested_T, the effective
    horizon is just requested_T — no surprise expansion for the common case."""
    cs = parse_script('AT 1, 2, 3:\n  PAY 1')
    assert effective_T_max(cs, 3.0) == 3.0
    assert effective_T_max(cs, 5.0) == 5.0


def test_effective_t_max_extends_for_literal_dates_beyond_requested_T():
    """Not CONSTAT-specific — a literal AT date past a too-small Maturité has
    the same out-of-bounds failure mode, so the safety net applies there too."""
    cs = parse_script('AT 1, 2, 5:\n  PAY 1')
    assert effective_T_max(cs, 3.0) == 5.0


def test_effective_t_max_extends_for_resolved_constat_dates():
    cs = parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1')
    today = date.today()
    end = today + timedelta(days=365 * 5)
    resolved = resolve_constats(cs, {
        'OBSERVATIONS': {
            'start_date': today.isoformat(), 'end_date': end.isoformat(),
            'roll_date': today.isoformat(), 'frequency': '1Y', 'stub': 'short_last',
        },
    })
    T_eff = effective_T_max(resolved, 3.0)   # stale Maturité=3Y, calendar runs to ~5Y
    assert T_eff > 3.0
    assert T_eff == pytest.approx(5.0, abs=0.02)


def test_effective_t_max_ignores_at_maturity_event():
    """AT_MATURITY events carry no dates of their own (they fire at T_max by
    construction) — they must not interfere with the max() computation."""
    cs = parse_script('AT MATURITY:\n  PAY 1')
    assert effective_T_max(cs, 4.0) == 4.0


def test_resolve_constats_missing_field_raises():
    cs = parse_script('CONSTAT() Observations\nAT Observations:\n  PAY 1')
    with pytest.raises(ValueError, match='end_date'):
        resolve_constats(cs, {
            'OBSERVATIONS': {'start_date': date.today().isoformat(), 'roll_date': date.today().isoformat(),
                              'frequency': '1Y', 'stub': 'short_last'},
        })
