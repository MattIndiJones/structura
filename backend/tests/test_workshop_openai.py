"""Targeted offline checks for workshop model selection and spending controls."""
from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.services.agent_workshop import openai_model
from backend.app.services.agent_workshop.brain import _openai_decision, action_schema, decide
from backend.app.services.agent_workshop.engine import (account_model_usage, model_limit_reason,
    needs_agent_decision, observation, routine_decision)
from backend.app.services.agent_workshop.store import CampaignConfig, Store
from backend.app.services.agent_workshop.tools import Tools


def test_existing_key_is_used_for_json_decision_without_storing_response(monkeypatch):
    monkeypatch.setattr(openai_model, 'load_key', lambda provider: 'fixture-key')
    seen = {}

    def fake_request(body, key, timeout, cancelled):
        seen.update(body=body, key=key, timeout=timeout)
        return {'status': 'completed', 'model': 'gpt-6-luna', 'usage': {'input_tokens': 3000, 'output_tokens': 100},
                'output': [{'type': 'message', 'content': [{'type': 'output_text',
                    'text': '{"decision":{"tool":"register","args":{},"reason":"Compte nécessaire"}}'}]}]}

    monkeypatch.setattr(openai_model, '_request', fake_request)
    config = CampaignConfig(provider='openai', model='gpt-6-luna').model_dump()
    actor = {'id': 'client', 'name': 'Client', 'role': 'client', 'goal': 'Tester'}
    observation = {'available_tools': ['register'], 'connected': False}
    result = openai_model.response(config, [{'role': 'user', 'content': 'JSON'}], 20, usage={},
        action_schema=action_schema(actor, observation))
    assert seen['key'] == 'fixture-key'
    assert seen['body']['store'] is False
    assert seen['body']['text']['format']['type'] == 'json_schema'
    assert seen['body']['text']['format']['strict'] is True
    schema = seen['body']['text']['format']['schema']
    assert schema['properties']['decision']['anyOf'][0]['properties']['args']['type'] == 'object'
    assert seen['body']['reasoning'] == {'effort': 'none'}
    assert result['metadata']['cost_usd'] == pytest.approx(0.00035)
    monkeypatch.setattr(openai_model, 'response', lambda *args: result)
    decision, metadata = decide(actor, observation, config, usage={})
    assert decision.tool == 'register' and metadata['provider'] == 'openai'


def test_openai_duplicate_json_is_accepted_only_when_decisions_match():
    first = '{"decision":{"tool":"quote","args":{"case_id":"CASE-0006","margin_bps":40},"reason":"Marge cible"}}'
    other = '{"decision":{"tool":"decline","args":{"case_id":"CASE-0006"},"reason":"Refus"}}'
    assert _openai_decision(first + '\n' + first)['tool'] == 'quote'
    with pytest.raises(ValueError, match='plusieurs décisions'):
        _openai_decision(first + '\n' + other)
    with pytest.raises(ValueError):
        _openai_decision(first + '\ntexte libre')


def test_budget_blocks_before_paid_call(monkeypatch):
    monkeypatch.setattr(openai_model, 'load_key', lambda provider: 'fixture-key')
    monkeypatch.setattr(openai_model, '_request', lambda *args: pytest.fail('No API request allowed'))
    config = CampaignConfig(provider='openai', model='gpt-6-sol', max_ai_cost_usd=0.01).model_dump()
    with pytest.raises(openai_model.BudgetReached):
        openai_model.response(config, [{'role': 'user', 'content': 'JSON'}], 20, usage={'model_cost_usd': 0.005})


def test_truncated_response_keeps_usage_and_is_retryable(monkeypatch):
    monkeypatch.setattr(openai_model, 'load_key', lambda provider: 'fixture-key')
    monkeypatch.setattr(openai_model, '_request', lambda *args: {
        'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
        'model': 'gpt-6-luna', 'usage': {'input_tokens': 2500, 'output_tokens': 4000}, 'output': [],
    })
    config = CampaignConfig(provider='openai', model='gpt-6-luna').model_dump()
    with pytest.raises(openai_model.IncompleteOutput) as caught:
        openai_model.response(config, [{'role': 'user', 'content': 'JSON'}], 20, usage={})
    assert caught.value.metadata['output_tokens'] == 4000
    assert caught.value.metadata['cost_usd'] > 0
    assert not isinstance(caught.value, openai_model.ModelUnavailable)


def test_campaign_accounting_and_model_guards():
    state = {'config': CampaignConfig(provider='openai', model='gpt-6-luna', max_ai_cost_usd=0.01,
        max_model_calls=2).model_dump(), 'usage': {'model_calls': 1}}
    account_model_usage(state, {'provider': 'openai', 'input_tokens': 3000, 'output_tokens': 100, 'cost_usd': 0.00035})
    assert state['usage']['model_input_tokens'] == 3000
    assert state['usage']['model_cost_usd'] == pytest.approx(0.00035)
    assert model_limit_reason(state) is None
    state['usage']['model_calls'] = 2
    assert 'Nombre maximal' in model_limit_reason(state)
    with pytest.raises(ValueError):
        CampaignConfig(provider='openai', model='qwen2.5-coder:7b')
    with pytest.raises(ValueError):
        CampaignConfig(provider='openai', model='gpt-6-luna', environment='legacy')


def test_payoff_schedule_and_multiyear_maturity_use_existing_templates(tmp_path, monkeypatch):
    import backend.app.services.scenario_market as market

    monkeypatch.setattr(market, 'history', lambda *args, **kwargs: {'prices': {'AIR.PA': [100]}, 'provider': 'fixture'})
    state = Store(tmp_path / 'campaigns').create(CampaignConfig(months=2, maturity_months=24,
        payoff_templates=['reverse_convertible', 'phoenix'], start_date='2025-10-13'), 1)
    tools = Tools(tmp_path, state, None)
    monkeypatch.setattr(tools, 'mail', lambda *args, **kwargs: None)
    try:
        first = tools.request('client', 'phoenix', 8, 60)
        assert first['template'] == 'reverse_convertible'
        assert date.fromisoformat(state['cases'][first['case_id']]['pricing']['maturity_date']).year == 2027
        state['month'] = 1
        state['business_date'] = '2025-11-13'
        second = tools.request('client', 'reverse_convertible', 8, 60)
        assert second['template'] == 'phoenix'
        obs = observation(state, 'client', SimpleNamespace(tokens={}))
        assert obs['scheduled_template'] == 'phoenix'
    finally:
        tools.close()


def test_routine_setup_and_notification_only_do_not_consume_model_calls():
    actor = {'id': 'bnp'}
    initial = {'connected': False, 'available_tools': ['register'], 'relation_tasks': [],
               'contract_mandate': {}, 'solicitations': []}
    assert routine_decision(actor, initial).tool == 'register'
    relation = {'connected': True, 'available_tools': ['relationship', 'wait'],
                'relation_tasks': ['hector'], 'contract_mandate': {'hector': {'note_ready': True,
                'otc_ready': True}}, 'solicitations': []}
    assert routine_decision(actor, relation).args == {'party': 'hector', 'status': 'ACTIVE', 'otc': True}
    notification = {'available_tools': ['wait', 'mail'], 'solicitations': []}
    assert not needs_agent_decision(notification)
    assert needs_agent_decision({'available_tools': ['mail', 'wait'], 'solicitations': ['direct-message']})
    assert needs_agent_decision({'available_tools': ['quote', 'wait'], 'solicitations': []})


def test_strict_openai_schema_keeps_native_tool_arguments():
    actor = {'id': 'bnp', 'role': 'bank'}
    current = {'connected': True, 'available_tools': ['quote', 'decline', 'wait'],
               'cases': [], 'month': 1}
    schema = openai_model._decision_schema(action_schema(actor, current))
    choices = schema['properties']['decision']['anyOf']
    quote = next(choice for choice in choices if choice['properties']['tool']['enum'] == ['quote'])
    assert quote['properties']['args']['required'] == ['case_id', 'margin_bps']
    assert quote['properties']['args']['additionalProperties'] is False
    assert not any('args_json' in choice['properties'] for choice in choices)
