from copy import deepcopy
from types import SimpleNamespace

from backend.app.services.agent_workshop.reconciliation import check_books
from backend.app.services.agent_workshop.store import Store, CampaignConfig
from backend.app.services.agent_workshop.engine import observation
from backend.app.services.agent_workshop.engine import failure_message
from backend.app.services.agent_workshop.tools import Tools
import httpx


def matched():
    fields = dict(case_id='CASE-001', trade_reference='NOTE-BANK', instrument_reference='NOTE', issuer='BNP', nominal=1e7,
                  currency='EUR', price_traded=100, value_date='2025-10-08', contract_hash='terms', settlement_status='SETTLED')
    return {'cases': {'CASE-001': {'id': 'CASE-001', 'nominal': 1e7, 'instrument_reference': 'NOTE'}}, 'actors': {
        'hector': {'entity': 'Hector', 'deals': [dict(fields, leg='HECTOR_BUY', our_side='BUY', counterparty='BNP'),
            dict(fields, trade_reference='NOTE-CLIENT', price_traded=101, leg='HECTOR_SELL', our_side='SELL', counterparty='Client')]},
        'bnp': {'entity': 'BNP', 'role': 'bank', 'deals': [dict(fields, leg='BANK_SELL', our_side='SELL', counterparty='Hector')]},
        'client': {'entity': 'Client', 'deals': [dict(fields, trade_reference='NOTE-CLIENT', price_traded=101, leg='CLIENT_BUY', our_side='BUY', counterparty='Hector')]}}}


def test_extra_booking_cannot_count_as_complete():
    state = matched()
    assert check_books(state)[0]['status'] == 'COMPLETE'
    state['actors']['client']['deals'].append(deepcopy(state['actors']['client']['deals'][0]))
    result = check_books(state)[0]
    assert result['status'] == 'MISMATCH' and result['client_volume'] == 0
    assert result['issues'][0]['code'] == 'DUPLICATE_LEG'


def test_wrong_counterparty_and_wrong_actor_are_detected():
    state = matched()
    state['actors']['hector']['deals'][0]['counterparty'] = 'Other bank'
    assert any(i['code'] == 'COUNTERPARTY_MISMATCH' for i in check_books(state)[0]['issues'])
    state = matched()
    state['actors']['bnp']['deals'].append(state['actors']['client']['deals'].pop())
    assert any(i['code'] == 'ACTOR_MISMATCH' for i in check_books(state)[0]['issues'])


def test_missing_evidence_is_not_filled_in_from_the_other_book():
    state = matched()
    del state['actors']['client']['deals'][0]['contract_hash']
    assert check_books(state)[0]['status'] == 'UNVERIFIED'
    state = matched()
    state['cases']['CASE-001']['outcome'] = 'CLIENT_DECLINED'
    assert check_books(state)[0]['status'] == 'MISMATCH'


def test_matching_books_cannot_contradict_the_accepted_quote():
    state = matched()
    state['quotes'] = [{'id': 'accepted', 'bank': 'bnp', 'price': 100}]
    state['accepted'] = {'CASE-001': 'accepted'}
    state['actors']['hector']['deals'][0]['price_traded'] = 102
    state['actors']['bnp']['deals'][0]['price_traded'] = 102
    result = check_books(state)[0]
    assert result['status'] == 'MISMATCH' and result['client_volume'] == 0
    assert any(i['code'] == 'ACCEPTED_PRICE_MISMATCH' for i in result['issues'])


def test_bank_does_not_receive_competitor_declines(tmp_path):
    state = Store(tmp_path).initial_state(CampaignConfig(months=1), 1)
    state['actors']['bnp']['relations'] = {'hector': {'status': 'ACTIVE', 'otc_allowed': False}}
    state['cases'] = {'CASE-001': {'id': 'CASE-001', 'month': 0, 'rfq_sent': True, 'declines': ['sg'], 'pricing': {}, 'rfq_id': 25}}
    state['messages'] = [{'id': 'a', 'to': 'bnp', 'from': 'hector', 'case_id': 'CASE-001'}]
    case = observation(state, 'bnp', SimpleNamespace(tokens={'bnp': 'fixture'}))['cases'][0]
    assert 'declines' not in case and 'rfq_id' not in case


def test_free_api_updates_native_relationships_and_bookings(tmp_path):
    state = Store(tmp_path).initial_state(CampaignConfig(months=1), 1)
    state['cases'] = {'CASE-001': {'id': 'CASE-001', 'instrument_reference': 'NOTE'}}
    tools = Tools.__new__(Tools)
    tools.state, tools.calls, tools.tokens = state, [], {'hector': 'fixture'}
    replies = {'/api/deals/counterparties': [{'id': 2, 'name': state['actors']['bnp']['entity']}],
               '/api/trading/relationships': [{'id': 7, 'counterparty_id': 2, 'status': 'ACTIVE'}],
               '/api/trading/executions': [{'id': 8, 'instrument_reference': 'NOTE', 'trade_reference': 'NOTE-BANK', 'our_side': 'BUY'}]}
    tools.api = lambda key, method, path, body=None: replies[path] if method == 'GET' else {'id': 8}
    tools.execute('hector', 'api', {'method': 'POST', 'path': '/api/trading/book-note'})
    assert state['actors']['hector']['relations']['bnp']['id'] == 7
    assert state['actors']['hector']['deals'][0]['leg'] == 'HECTOR_BUY'
    assert state['actors']['hector']['deals'][0]['case_id'] == 'CASE-001'


def test_timeouts_distinguish_no_model_decision_from_an_uncertain_native_write():
    assert 'aucune action métier' in failure_message(httpx.ReadTimeout(''), None, 90)
    assert 'relire les faits natifs' in failure_message(httpx.ReadTimeout(''), object(), 90)
