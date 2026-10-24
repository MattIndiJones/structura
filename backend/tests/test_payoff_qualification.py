"""C09: fail closed on lost instructions and unreviewed economic adapters."""
import pytest
from pydantic import ValidationError

from backend.app.core.payscript import qualification as q
from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script, script_source_hash
from backend.app.core.product_optimizer import service, validation
from backend.app.core.product_optimizer.capabilities import capabilities
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.services.llm.validate import validate
from backend.tests.test_llm_scripting import UL
from backend.tests.test_product_optimizer import request


@pytest.mark.parametrize('instruction', ['PAY .08', 'STOP', 'SET X = 1', 'ACCRUE .08'])
@pytest.mark.parametrize('context', ['event', 'if', 'else', 'else_if'])
def test_unexpected_indent_never_discards_an_instruction(instruction, context):
    body = '  PAY 1\n    '+instruction
    if context == 'if':
        body = '  IF WOF >= 1:\n    PAY 1\n      '+instruction
    elif context == 'else':
        body = '  IF WOF >= 1:\n    PAY 1\n  ELSE:\n    PAY 1\n      '+instruction
    elif context == 'else_if':
        body = '  IF WOF >= 1:\n    PAY 1\n  ELSE IF WOF >= .5:\n    PAY 1\n      '+instruction
    source = 'AT MATURITY:\n'+body
    with pytest.raises(ValueError, match=f'Ligne {len(source.splitlines())}: indentation inattendue'):
        parse_script(source)


@pytest.mark.parametrize('source,line', [
    ('AT MATURITY:\n  IF WOF >= 1:\n  PAY 1', 2),
    ('AT MATURITY:', 1),
    ('AT MATURITY:\n\tPAY 1', 2),
    ('AT MATURITY:\n    PAY 1\n  PAY .08', 3),
])
def test_empty_blocks_tabs_and_bad_dedents_are_explicit_errors(source, line):
    with pytest.raises(ValueError, match=f'Ligne {line}:'):
        parse_script(source)


def test_valid_coupon_is_paid_and_stop_cancels_maturity_flows():
    capital_coupon = parse_script('AT MATURITY:\n  PAY 1\n  PAY .08')
    result = run_mc(capital_coupon, UL, [[1.]], r=0., T_max=1., N=4, model='constant', seed=7)
    assert result['price'] == pytest.approx(1.08)
    recall = parse_script('AT .25:\n  IF WOF >= 0:\n    PAY 1.08\n    STOP\nAT MATURITY:\n  PAY 1')
    result = run_mc(recall, UL, [[1.]], r=0., T_max=1., N=4, model='constant', seed=7, per_path_flows=True)
    assert result['price'] == pytest.approx(1.08)
    assert all(flows == [( .25, 1.08)] for flows in result['path_flows'])


@pytest.mark.parametrize('key', q.APPROVED_SOURCES)
def test_all_approved_sources_pass_independent_cashflow_panels(key):
    proof = q.qualify_payoff(key, PRODUCTS[key]['script'], include_cases=True)
    assert proof['status'] == 'REFERENCE_PATHS_PASSED'
    assert proof['source_hash'] == q.APPROVED_SOURCES[key]
    assert len(proof['reference_panel_hash']) == 64
    assert proof['case_count'] == len(proof['cases']) >= 54
    for case in proof['cases']:
        assert [(f[0], f[2]) for f in case['actual']] == [(f[0], f[2]) for f in case['expected']]
        assert [f[1] for f in case['actual']] == pytest.approx([f[1] for f in case['expected']], abs=1e-12)
    if key == 'booster':
        assert set(proof['parameter_affinity'].values()) == {'PIECEWISE_AFFINE'}


def test_memory_panel_has_known_missed_catchup_reset_unpaid_and_recall_cashflows():
    cases = q.qualify_payoff('phoenix_memoire', PRODUCTS['phoenix_memoire']['script'], include_cases=True)['cases']
    def flows(name):
        return next(c['actual'] for c in cases if c['name'] == name)
    assert flows('miss_catchup_reset_q0.02') == [
        [2, .04, 'Coupon et rattrapage'], [4, .04, 'Coupon et rattrapage'], [4, 1., 'Capital — remboursement à maturité']]
    assert flows('unpaid_memory_q0.02') == [[1, .02, 'Coupon et rattrapage'], [4, 1., 'Capital — remboursement à maturité']]
    assert flows('early_call_q0.02') == [[1, .02, 'Coupon et rattrapage'], [1, 1., 'Remboursement anticipé']]


@pytest.mark.parametrize('key', q.APPROVED_SOURCES)
def test_economic_change_invalidates_source_approval_even_with_identical_declarations(key, monkeypatch):
    source = PRODUCTS[key]['script']
    quantity = 'PART' if key in {'capital_garanti', 'booster'} else 'COUPON'
    # Modify an expression, leaving PARAM, calendar, flow label and STOP intact.
    lines = source.splitlines()
    index = next(i for i, line in enumerate(lines) if line.strip().startswith('PAY ') and quantity in line)
    lines[index] = lines[index].replace(quantity, f'{quantity} * {quantity}', 1)
    changed = {**PRODUCTS[key], 'script': '\n'.join(lines)}
    assert [(p.name, p.kind) for p in parse_script(source).params] == [(p.name, p.kind) for p in parse_script(changed['script']).params]
    monkeypatch.setitem(PRODUCTS, key, changed)
    assert next(f for f in capabilities()['families'] if f['product_family'] == key)['status'] == 'UNSUPPORTED'
    with pytest.raises(ValueError, match='qualification'):
        q.qualify_payoff(key, changed['script'])


def test_modified_athena_is_refused_by_request_and_existing_candidate(monkeypatch):
    req = request()
    candidate = next(service.generate_candidates(req))
    monkeypatch.setitem(PRODUCTS, 'autocall_athena', {**PRODUCTS['autocall_athena'],
        'script': PRODUCTS['autocall_athena']['script'].replace('COUPON * INDEX', 'COUPON * COUPON * INDEX')})
    with pytest.raises(ValidationError, match='qualification'):
        OptimizationRequest.model_validate(req.model_dump())
    result = validation.evaluate_validation(req, candidate, 1)
    assert result.validation_status == 'FAILED'
    assert result.rank is None and result.constraint_status == 'REJECTED'


@pytest.mark.parametrize('mismatch', ['compiled', 'input', 'missing'])
def test_diagnostic_requires_compiled_and_input_identity(mismatch):
    req = request(); candidate = next(service.generate_candidates(req)); candidate.coupon = .08
    script, inputs = service.build_candidate(req, candidate)
    assert script.source_hash == script_source_hash(inputs['script'])
    if mismatch == 'compiled':
        script = parse_script('AT MATURITY:\n  PAY 1')
    elif mismatch == 'input':
        inputs['script'] += '\n# changed'
    else:
        script.source_hash = None
    diagnostic = validation.coupon_diagnostic({}, script, inputs, candidate, 10, .05)
    assert diagnostic['status'] == 'UNAVAILABLE_PAYOFF_QUALIFICATION'
    assert diagnostic['payoff_qualification']['source_hash'] == q.APPROVED_SOURCES[candidate.product_family]


def test_source_proof_normalization_is_narrow_and_cache_cannot_be_mutated():
    source = PRODUCTS['phoenix_memoire']['script']
    proof = q.qualify_payoff('phoenix_memoire', source)
    assert proof == q.qualify_payoff('phoenix_memoire', source.replace('\n', '\r\n').rstrip('\r\n'))
    proof['parameter_affinity'].clear()
    assert q.qualify_payoff('phoenix_memoire', source)['parameter_affinity']
    assert script_source_hash(source) != script_source_hash(source.replace('    PAY', '      PAY', 1))


def test_reference_failure_cannot_keep_a_green_approval(monkeypatch):
    q._run_panel.cache_clear()
    monkeypatch.setattr(q, 'expected_cashflows', lambda *args: ([], 0))
    with pytest.raises(ValueError, match='qualification'):
        q.qualify_payoff('phoenix_memoire', PRODUCTS['phoenix_memoire']['script'])
    assert q.recognize_payoff(PRODUCTS['phoenix_memoire']['script'])['status'] == 'UNQUALIFIED'
    q._run_panel.cache_clear()


def test_nonfinite_reference_price_is_never_qualified(monkeypatch):
    from backend.app.core.payscript import engine
    original = engine._eval_paths
    def nonfinite(*args, **kwargs):
        pv, rest = original(*args, **kwargs)
        pv[:] = float('nan')
        return pv, rest
    q._run_panel.cache_clear()
    monkeypatch.setattr(engine, '_eval_paths', nonfinite)
    with pytest.raises(ValueError, match='qualification'):
        q.qualify_payoff('phoenix_memoire', PRODUCTS['phoenix_memoire']['script'])
    q._run_panel.cache_clear()


@pytest.mark.parametrize('source', ['SET MEMO = 0\nAT MATURITY:\n  PAY 1',
                                  'AT MATURITY:\n  PAY 1'])
def test_assistant_does_not_qualify_unused_or_missing_memory(source):
    v = validate(source, description='coupon à mémoire', underlyings=UL, corr=[[1.]], r=0., T=None, user_params={})
    check = next(c for c in v.checks if c.label == 'Coupon à mémoire')
    assert check.level == 'attention'
    assert v.as_dict()['payoff_qualification']['status'] == 'STRUCTURAL_ONLY'
    assert 'Mémoire mise à jour après versement' not in check.detail


def test_assistant_recognizes_only_the_tested_memory_source():
    source = PRODUCTS['phoenix_memoire']['script']
    v = validate(source, description='phoenix coupon à mémoire', underlyings=UL, corr=[[1.]], r=0., T=None, user_params={})
    assert v.payoff_qualification['status'] == 'REFERENCE_PATHS_PASSED'
    assert next(c for c in v.checks if c.label == 'Coupon à mémoire').level == 'ok'
    changed = source.replace('(INDEX - MEMO)', 'INDEX')
    v = validate(changed, description='coupon à mémoire', underlyings=UL, corr=[[1.]], r=0., T=None, user_params={})
    assert v.payoff_qualification['status'] == 'STRUCTURAL_ONLY'
    assert next(c for c in v.checks if c.label == 'Coupon à mémoire').level == 'attention'
