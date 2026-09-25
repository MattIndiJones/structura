"""Acceptance regressions: unusable AI output and faithful fee reporting."""
import pytest
from backend.app.core.amc_synthesize import build_synthesis_payload, validate_synthesis
from backend.app.services.llm.providers import LlmError, _complete_ollama


@pytest.mark.parametrize('text,reason', [
    ('```json\n{"data":{"sha256":"abc"', None),
    ('{"data": {"n_obs":1566}}', None),
    ('La NAV progresse. ' * 50, 'length'),
    ('La NAV progresse. ' * 50, 'max_tokens'),
    ('Analyse', None),
])
def test_reject_unusable_synthesis(text, reason):
    with pytest.raises(LlmError):
        validate_synthesis(text, reason)


def test_prose_is_allowed_without_certifying_its_content():
    validate_synthesis('La performance du fonds est positive sur la période observée. '
                       'Les frais et les dividendes doivent être rapprochés de la NAV. '
                       'Le score descriptif ne constitue pas une preuve de talent durable. '
                       'La comparaison au panier passif reste conditionnelle aux conventions de frais et de dividendes.', 'stop')


def test_prompt_keeps_financial_controls_without_raw_hash_catalogue():
    payload = build_synthesis_payload({'meta': {'currency': 'USD'},
        'provenance': {'sources': {'bundle:test': {'sha256': 'SECRET_HASH'}}},
        'data_quality': {'status': 'ready'},
        'block_b': {'totals': {'reconciliation': {'cash_income_prod': 917678.53,
             'performance_crystallization': 'annual', 'gap_prod': 0}}}})
    assert 'SECRET_HASH' not in payload
    assert '917678.53' in payload and 'annual' in payload and 'ready' in payload
    assert payload.endswith('400 à 600 mots maximum.')


def test_editorial_brief_distinguishes_lifetime_and_yearly_returns():
    from backend.app.core.amc_synthesize import build_synthesis_brief
    brief = build_synthesis_brief({'meta': {'nav_start_value': 100, 'nav_current_value': 138.0652},
        'block_a': {'net': {'performance': {'full_total_ret_pct': 38.07},
                           'regression': {'alpha_pvalue': .53}}},
        'block_b': {'totals': {'reconciliation': {'annual_fees': [{'year': 2025, 'return_pct': 24.65}]}}},
        'provenance': {'data': {'hash': 'NOT_FOR_THE_MODEL'}}})
    assert 'nav_current_value = 138.0652' in brief
    assert 'full_total_ret_pct = 38.07' in brief
    assert 'ANNÉE 2025 UNIQUEMENT' in brief and 'return_pct = 24.65' in brief
    assert 'alpha_pvalue = 0.53' in brief
    assert 'NOT_FOR_THE_MODEL' not in brief


def test_ollama_context_and_truncation_metadata(monkeypatch):
    from backend.app.services.llm import providers
    sent = []
    def post(url, payload):
        sent.append(payload)
        return {'model': 'local', 'message': {'content': 'Texte'}, 'done_reason': 'length'}
    monkeypatch.setattr(providers, '_post', post)
    result = _complete_ollama('local', 'Système', 'Données', .3, 3000, context_tokens=16384)
    assert sent[0]['options']['num_ctx'] == 16384
    assert result.finish_reason == 'length'


def test_factorial_turnover_uses_calendar_time_not_nav_count():
    from backend.app.core.amc_engine import _compute_activity
    orders = [{'Date': d, 'Side': 'BUY', 'USD Notional Abs': 500} for d in
              ('2023-01-01', '2024-01-01')]
    nav = [{'nav': 100, 'Outstanding Quantity': 10}] * 8
    assert _compute_activity(orders, nav)['turnover_ann_pct'] == 100
    assert _compute_activity(orders, nav * 20)['turnover_ann_pct'] == 100
    assert _compute_activity(orders[:1], nav)['turnover_ann_pct'] is None


def test_api_rejects_technical_synthesis(monkeypatch):
    from fastapi import HTTPException
    from backend.app.api import amc
    monkeypatch.setattr(amc, 'generate_text', lambda *a, **k: {
        'text': '```json\n{"sha256":"broken"', 'finish_reason': 'length'})
    with pytest.raises(HTTPException) as error:
        amc.synthesize_study(amc.SynthesizeRequest(study_result={'meta': {}}), None)
    assert error.value.status_code == 422


def test_pdf_fee_text_and_dividend_bridge():
    from backend.app.core.amc_pdf import _append_block_b
    from reportlab.platypus import Spacer, Table, Paragraph
    story = []
    _append_block_b(story, {'totals': {'reconciliation': {
        'cash_income_prod': 917678.53, 'management_fee_basis': 'previous_nav_act365',
        'performance_crystallization': 'annual',
        'fee_breakdown': {'management_fee_pct': 1, 'management_fee_prod': -660069.4,
                         'performance_fee_pct': 15, 'performance_fee_prod': -671738.44}},
        'total_pnl': 4345268.22, 'fee_drag_prod': -1456428.95,
        'total_pnl_net_of_fees': 3806517.8}}, 'USD', lambda n: Spacer(1, n))
    def texts(v):
        if isinstance(v, Paragraph): return v.getPlainText()
        if isinstance(v, Table): return texts(v._cellvalues)
        if isinstance(v, (list, tuple)): return '\n'.join(texts(x) for x in v)
        return ''
    text = texts(story)
    assert 'Dividendes acquis' in text and '917.7k' in text
    assert 'NAV précédente ACT/365' in text and 'cristallisation annuelle' in text
    assert 'prélevé le jour même' not in text and 'HWM journalier' not in text
    assert 'P&L;' not in text
