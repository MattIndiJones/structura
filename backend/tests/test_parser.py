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


def test_typo_in_param_reference_raises():
    """A PAY/SET expression referencing a name that's neither a declared
    PARAM nor a SET target must raise, not silently price it as 0 — regression
    for the "COUPOM" vs "COUPON" class of typo that used to compile silently."""
    with pytest.raises(ValueError, match='COUPON'):
        parse_script('PARAM COUPOM = 8%\n\nAT MATURITY\n  PAY COUPON')


def test_set_variable_reference_does_not_raise():
    """A SET-assigned name used later in the same or a different event is a
    legitimate reference, not a typo — must not trip the unknown-identifier
    check."""
    cs = parse_script('PARAM BAR = 80%\n\nAT MATURITY\n  SET KI = INDIC(S[1] < BAR)\n  PAY (1 - KI) * 1\n  PAY KI * S[1]')
    assert len(cs.events) == 1


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


# ── Audit 2026-07: AT dates <= 0 rejected at parse ──────────────────

def test_at_date_zero_or_negative_rejected():
    """AT 0 / AT -1 would make the engine index S_min[-1]/WOF_min[-1] — the
    END of the simulated path (Python negative indexing), a silent look-ahead.
    Rejected at parse instead."""
    import pytest
    with pytest.raises(ValueError, match="strictement positives"):
        parse_script("AT 0:\n  PAY 1\n")
    with pytest.raises(ValueError, match="strictement positives"):
        parse_script("AT -1:\n  PAY 1\n")
    # Positive dates keep working, including sub-year ones.
    cs = parse_script("AT 0.5, 1:\n  PAY 1\n")
    assert cs.events[0].dates == [0.5, 1.0]


# ── PARAM() (valeurs par observation) & convention M_ ────────────────

PARAM_ARRAY_SCRIPT = """
PARAM COUPON = 8%
PARAM() M_AC_BAR = 105%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


def _run_obs(cs, memo, spots, index, event_idx=0):
    """Evaluate one compiled event with a minimal engine-shaped context."""
    ctx = {"spots": spots, "accum": 0.0, "index": index, "wof_min": min(spots),
           "bof_max": max(spots), "t": float(index), "s_min": spots, "s_max": spots,
           "s_prev": spots, "realvol": 0.0, "fix_min": 1.0, "fix_max": 1.0,
           "fix_avg": 1.0, "done": False, "memo": dict(memo), "total_cf": 0.0}
    st = {"flows": [], "done": False}
    cs.events[event_idx].fn(ctx, st)
    return st


def test_param_array_declaration():
    cs = parse_script(PARAM_ARRAY_SCRIPT)
    kinds = {p.name: p.kind for p in cs.params}
    assert kinds == {"COUPON": "scalar", "M_AC_BAR": "array", "M_KI_BAR": "scalar"}
    seed = next(p for p in cs.params if p.name == "M_AC_BAR")
    assert seed.stored_val == pytest.approx(1.05)
    assert seed.is_pct is True


def test_param_array_no_seed_defaults():
    cs = parse_script("PARAM() M_BAR\nAT 1:\n  PAY INDIC(WOF >= M_BAR)")
    p = cs.params[0]
    assert p.kind == "array" and p.raw_default == 0.0 and p.is_pct is True


def test_param_array_per_observation_resolution():
    """Degressive barrier [105%, 100%, 95%]: obs1 must NOT call at WOF=102%,
    obs2 must call — the whole point of per-observation values."""
    cs = parse_script(PARAM_ARRAY_SCRIPT)
    memo = {"COUPON": 0.08, "M_AC_BAR": [1.05, 1.00, 0.95], "M_KI_BAR": 0.6}
    r1 = _run_obs(cs, memo, [1.02], 1)
    r2 = _run_obs(cs, memo, [1.02], 2)
    assert not r1["done"]
    assert r2["done"]
    assert [f["v"] for f in r2["flows"]] == [pytest.approx(0.16), 1]


def test_param_array_last_row_extends():
    """Fewer rows than observations → last row extends. One row == scalar."""
    cs = parse_script(PARAM_ARRAY_SCRIPT)
    memo = {"COUPON": 0.08, "M_AC_BAR": [1.05, 1.00, 0.95], "M_KI_BAR": 0.6}
    # index 5 beyond the 3 rows → row 3 (95%) applies
    assert _run_obs(cs, memo, [0.96], 5)["done"]
    memo["M_AC_BAR"] = [1.10]
    assert not _run_obs(cs, memo, [1.05], 3)["done"]
    assert _run_obs(cs, memo, [1.11], 3)["done"]


def test_param_array_scalar_passthrough():
    """A scalar sent for a PARAM() (e.g. legacy user_params) passes through."""
    cs = parse_script(PARAM_ARRAY_SCRIPT)
    memo = {"COUPON": 0.08, "M_AC_BAR": 1.0, "M_KI_BAR": 0.6}
    assert _run_obs(cs, memo, [1.02], 1)["done"]


def test_param_array_maturity_uses_last_relevant_row():
    """AT MATURITY keeps INDEX at the last observation → last relevant row.
    KI barrier as array: [70%, 60%] with WOF=65% at maturity (index 3) →
    row 2 (60%) applies → no KI."""
    script = PARAM_ARRAY_SCRIPT.replace("PARAM M_KI_BAR = 60%", "PARAM() M_KI_BAR = 60%")
    cs = parse_script(script)
    memo = {"COUPON": 0.08, "M_AC_BAR": [9.9], "M_KI_BAR": [0.70, 0.60]}
    st = _run_obs(cs, memo, [0.65], 3, event_idx=1)   # AT MATURITY event
    # no KI → PAY (1-0)*1 = 1 and PAY 0*WOF = 0
    assert [f["v"] for f in st["flows"]] == [1, 0.0]


def test_monitors_direction_from_usage():
    cs = parse_script(PARAM_ARRAY_SCRIPT)
    mons = {m["name"]: m for m in cs.monitors}
    assert mons["M_AC_BAR"] == {"name": "M_AC_BAR", "observable": "WOF", "direction": "up"}
    assert mons["M_KI_BAR"] == {"name": "M_KI_BAR", "observable": "WOF", "direction": "down"}


def test_monitors_reversed_comparison_and_other_observables():
    script = """
PARAM M_KO_BAR = 130%
PARAM M_FLOOR = 60%
AT MATURITY:
  SET KO = INDIC(M_KO_BAR <= BOF_MAX)
  SET KI = INDIC(M_FLOOR > WOF_MIN)
  PAY KO + KI
"""
    cs = parse_script(script)
    mons = {m["name"]: m for m in cs.monitors}
    # M_KO_BAR <= BOF_MAX : level below obs → fires when obs above → up
    assert mons["M_KO_BAR"]["observable"] == "BOF_MAX"
    assert mons["M_KO_BAR"]["direction"] == "up"
    # M_FLOOR > WOF_MIN : fires when obs below the level → down
    assert mons["M_FLOOR"]["observable"] == "WOF_MIN"
    assert mons["M_FLOOR"]["direction"] == "down"


def test_monitors_ambiguous_usage_is_neutral():
    script = """
PARAM M_X = 100%
AT 1:
  PAY INDIC(WOF >= M_X) + INDIC(WOF < M_X)
AT MATURITY:
  PAY 0
"""
    cs = parse_script(script)
    mon = cs.monitors[0]
    assert mon["name"] == "M_X" and mon["direction"] is None


def test_monitors_unused_m_param_has_no_direction():
    """M_ param used only in arithmetic (no comparison) → observable/direction
    None — the watchlist shows a neutral gap."""
    script = """
PARAM M_PUT_STRIKE = 80%
AT MATURITY:
  PAY MAX(0, 1 - WOF/M_PUT_STRIKE)
"""
    cs = parse_script(script)
    mon = cs.monitors[0]
    assert mon["observable"] is None and mon["direction"] is None
