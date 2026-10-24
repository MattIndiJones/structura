"""C05: calendar parity, explicit policy, settlement and frozen contracts."""
import asyncio
import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api.schedule import generate_schedule_endpoint, resolve_business_day, window_preview_endpoint
from backend.app.api.deals import _resoudre_pour_booking, _reinvest_context
from backend.app.api.pricing import parse_endpoint, price_endpoint
from backend.app.core.calendars import (BusinessDayConvention as BDC, calendar_context,
                                       add_business_days, is_business_day)
from backend.app.core.product.inputs import terms_from_input
from backend.app.core.product.calendar import freeze_calendar, restore_calendar
from backend.app.core.payscript.parser import parse_script, resolve_constats, resolve_analysis_constats
from backend.app.core.schedule import generate_schedule, generate_main_schedule, parse_tenor, StubConvention as SC
from backend.app.core.schemas import ScheduleRequest, BusinessDayRequest, WindowPreviewRequest, ParseRequest, PricingRequest
from backend.tests.test_products import product_client
from backend.tests.test_business_permissions import access_case

SCRIPT = 'CONSTAT() OBS\nAT OBS:\n  PAY 0.01'
ORIGIN = date(2026, 1, 31)
VALUES = dict(start_date='2026-01-31', end_date='2026-05-31', roll_date='2026-01-31', frequency='1M')


def preview(values=VALUES, **changes):
    return asyncio.run(generate_schedule_endpoint(ScheduleRequest(**{**values, 'currency': 'EUR', **changes})))


def compiled(values=VALUES, script=SCRIPT):
    return resolve_constats(parse_script(script), {'OBS': values}, anchor=ORIGIN, currency='EUR')


def product_payload(values=VALUES):
    return dict(script=SCRIPT, constats={'OBS': values}, strike_date=ORIGIN.isoformat(),
                value_date='2026-02-02', maturity_date='2026-05-31', payment_date='2026-06-02',
                T=120/365.25, settlement_ccy='EUR',
                underlyings=[dict(name='A', ticker='A', ccy='EUR', sigma=0., q=0.)])


@pytest.mark.parametrize('year,feb', [(2026, 28), (2028, 29)])
@pytest.mark.parametrize('stub', [SC.SHORT_LAST, SC.SHORT_FIRST])
def test_month_end_is_anchored_in_both_directions_and_leap_year(year, feb, stub):
    dates = generate_main_schedule(date(year, 1, 31), date(year, 5, 31), date(year, 1, 31), parse_tenor('1M'), stub)
    assert dates == [date(year, 1, 31), date(year, 2, feb), date(year, 3, 31), date(year, 4, 30), date(year, 5, 31)]


def test_nested_monthly_grid_keeps_original_roll_before_business_adjustment():
    result = generate_schedule(ORIGIN, date(2026, 5, 31), ORIGIN, parse_tenor('4M'), SC.SHORT_LAST,
                               parse_tenor('1M'), currency='EUR', convention=BDC.MODIFIED_FOLLOWING)
    assert result['raw_dates'] == [ORIGIN, date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]
    assert result['dates'] == [date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 29)]
    assert all(pay >= obs for obs, pay in zip(result['dates'], result['payment_dates']))


@pytest.mark.parametrize('lag', [-3, 1.8, 100, True, '3', None])
def test_invalid_lag_rejected_without_coercion_at_every_boundary(lag):
    values = {**VALUES, 'settlement_lag': lag}
    with pytest.raises(ValidationError): ScheduleRequest(**values)
    with pytest.raises(ValidationError): BusinessDayRequest(date='2026-04-02', business_days=lag)
    with pytest.raises(ValueError, match='entier entre 0 et 30'): compiled(values)
    with pytest.raises(ValueError, match='entier entre 0 et 30'): terms_from_input(product_payload(values))
    req = PricingRequest(**product_payload(values), r=0., N=1000, corr_matrix=[[1.]])
    with pytest.raises(HTTPException) as priced: price_endpoint(req)
    assert priced.value.status_code == 422 and 'entier entre 0 et 30' in str(priced.value.detail)
    body = SimpleNamespace(script_snapshot=SCRIPT, market_snapshot={'constats': {'OBS': values}},
                           strike_date=ORIGIN.isoformat(), value_date=ORIGIN.isoformat(), devise='EUR')
    with pytest.raises(ValueError, match='entier entre 0 et 30'): _resoudre_pour_booking(body)


@pytest.mark.parametrize('convention', [None, 'none', 'modified_following', 'following', 'preceding'])
def test_preview_product_pricing_and_booking_share_dates_and_defaults(convention):
    values = {**VALUES, 'settlement_lag': 3}
    if convention: values['convention'] = convention
    expected = preview(values)
    assert len(expected['dates']) == 5
    resolved = compiled(values)
    terms = terms_from_input(product_payload(values))
    body = SimpleNamespace(script_snapshot=SCRIPT, market_snapshot={'constats': {'OBS': values}},
                           strike_date=ORIGIN.isoformat(), value_date=ORIGIN.isoformat(), devise='EUR')
    booked, _ = _resoudre_pour_booking(body)
    priced = resolve_analysis_constats(parse_script(SCRIPT), PricingRequest(**product_payload(values), corr_matrix=[[1.]]))
    assert resolved.events[0].dates == booked.events[0].dates == priced.events[0].dates
    assert freeze_calendar(resolved) == terms.resolved_events.to_dict()
    assert [r['date'] for r in resolved.echeancier.to_dict()['constatations']] == expected['dates'][1:]
    assert [r['date_paiement'] for r in resolved.echeancier.to_dict()['constatations']] == expected['payment_dates'][1:]


def test_target_payment_proposal_crosses_easter_and_thirty_is_supported():
    result = resolve_business_day(BusinessDayRequest(date='2026-04-02', currency='EUR', business_days=3))
    assert result['date'] == '2026-04-09'
    assert preview({**VALUES, 'settlement_lag': 30})['payment_dates'][-1] > '2026-05-31'


def test_nyse_closure_does_not_close_target_settlement_and_policy_is_retained():
    values = {**VALUES, 'first_observation_date': '2026-07-03', 'end_date': '2026-07-03',
              'roll_date': '2026-07-03', 'convention': 'following',
              'observation_calendars': ['NYSE'], 'observation_join': 'all_open',
              'settlement_calendars': ['TARGET'], 'settlement_join': 'all_open', 'settlement_lag': 1}
    result = preview(values)
    assert result['raw_dates'] == ['2026-07-03']
    assert result['dates'] == ['2026-07-06'] and result['payment_dates'] == ['2026-07-07']
    obs, paid = calendar_context(values, 'EUR')
    assert not is_business_day(date(2026, 7, 3), obs) and is_business_day(date(2026, 7, 3), paid)
    terms = terms_from_input({**product_payload(values), 'maturity_date': '2026-07-06', 'payment_date': '2026-07-07'})
    assert terms.constats.to_dict()['OBS'] == values


@pytest.mark.parametrize('join,observed,paid', [('all_open', '2026-07-06', '2026-07-07'),
                                             ('any_open', '2026-07-03', '2026-07-06')])
def test_basket_rule_is_explicit_and_shared_with_windows(join, observed, paid):
    values = {**VALUES, 'first_observation_date': '2026-07-03', 'end_date': '2026-07-03', 'roll_date': '2026-07-03',
              'observation_calendars': ['NYSE', 'XETR'], 'observation_join': join,
              'settlement_calendars': ['TARGET'], 'convention': 'following', 'settlement_lag': 1}
    result = preview(values)
    assert result['dates'] == [observed] and result['payment_dates'] == [paid]
    window = asyncio.run(window_preview_endpoint(WindowPreviewRequest(date='2026-07-03',
        window_length='1D', currency='EUR', convention='following',
        observation_calendars=['NYSE', 'XETR'], observation_join=join)))
    assert window['dates'] == [observed]
    assert compiled(values).echeancier.to_dict()['constatations'][0]['date'] == observed


@pytest.mark.parametrize('changes', [dict(observation_calendars=['NYSE', 'XETR']),
    dict(observation_calendars=[]), dict(observation_calendars=['MISSING']),
    dict(observation_join='all_open'), dict(settlement_calendars=['NYSE']),
    dict(observation_calendars=['NYSE'], observation_join='guess')])
def test_invalid_policy_is_refused_even_without_business_adjustment(changes):
    values = {**VALUES, **changes}
    with pytest.raises(HTTPException) as failure: preview(values)
    assert failure.value.status_code == 422
    with pytest.raises(ValueError): compiled(values)


@pytest.mark.parametrize('stub,roll,expected', [
    (SC.SHORT_LAST, '2026-01-15', ['2026-01-15', '2026-02-15', '2026-03-05']),
    (SC.LONG_LAST, '2026-01-15', ['2026-01-15', '2026-03-05']),
    (SC.SHORT_FIRST, '2026-03-05', ['2026-01-15', '2026-02-05', '2026-03-05']),
    (SC.LONG_FIRST, '2026-03-05', ['2026-01-15', '2026-03-05']),
])
def test_long_stub_always_merges_irregular_boundary_without_half_period_threshold(stub, roll, expected):
    dates = generate_main_schedule(date(2026, 1, 15), date(2026, 3, 5), date.fromisoformat(roll), parse_tenor('1M'), stub)
    assert [d.isoformat() for d in dates] == expected


@pytest.mark.parametrize('stub', [SC.LONG_FIRST, SC.LONG_LAST])
def test_long_stub_does_not_merge_regular_boundary(stub):
    assert len(generate_main_schedule(ORIGIN, date(2026, 5, 31), ORIGIN, parse_tenor('1M'), stub)) == 5


def test_frozen_pre_c05_calendar_is_restored_verbatim_even_with_old_drift():
    frozen = freeze_calendar(compiled())
    historical = deepcopy(frozen)
    historical['events'][0]['dates'][1] = round((date(2026, 3, 28)-ORIGIN).days/365.25, 6)
    historical['schedule']['constatations'][1]['date'] = '2026-03-28'
    historical['schedule']['constatations'][1]['t'] = historical['events'][0]['dates'][1]
    restored = restore_calendar(parse_script(SCRIPT), historical)
    assert freeze_calendar(restored) == historical
    assert historical != frozen


def test_param_arrays_expose_their_own_named_calendar_to_economics():
    source = ('PARAM() CPN = 2%\nPARAM() CALL = 100%\nCONSTAT() QUARTER\nCONSTAT() YEAR\n'
              'AT QUARTER:\n  PAY CPN\nAT YEAR.last:\n  IF WOF >= CALL:\n    PAY 1\n    STOP')
    response = parse_endpoint(ParseRequest(script=source))
    assert response.ok
    assert {p['name']: p['observation_calendar'] for p in response.params} == {'CPN': 'QUARTER', 'CALL': 'YEAR'}


def test_reinvestment_refuses_extra_observation_created_by_month_end_roll(monkeypatch):
    from backend.app.api import deals
    monkeypatch.setattr(deals, 'business_today', lambda: date(2026, 10, 20))
    script = ('UNDERLYING Basket\nCONSTAT StartDate\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n' + SCRIPT)
    values = {'STARTDATE': '2026-01-31', 'OBS': {**VALUES, 'frequency': '3M',
        'first_observation_date': '2026-04-30', 'end_date': '2029-01-31'}}
    market = dict(constats=values)
    deal = SimpleNamespace(script_snapshot=script, market_snapshot_json=json.dumps(market), strike_date=ORIGIN.isoformat(),
        underlyings_json='[{"name":"A","ticker":"A"}]', devise='EUR', T=3.)
    with pytest.raises(HTTPException, match='nombre de constatations'):
        _reinvest_context(deal, None)


def test_calendar_http_routes_keep_c01_business_price_permissions(access_case):
    from backend.app.api import schedule
    _, _, login, _ = access_case
    client = login('front')
    client.app.include_router(schedule.router)
    for name in ['checker', 'ops']:
        assert login(name).get('/api/calendar/catalog').status_code == 403
        assert login(name).post('/api/schedule/generate', json={**VALUES, 'currency': 'EUR'}).status_code == 403
    assert login('front').get('/api/calendar/catalog').status_code == 200
    assert login('front').post('/api/schedule/generate', json={**VALUES, 'currency': 'EUR'}).status_code == 200
    client.headers.pop('Authorization')
    assert client.get('/api/calendar/catalog').status_code == 401


@pytest.mark.parametrize('lag', [-3, 1.8, 100])
def test_http_previews_refuse_invalid_settlement_lag(product_client, lag):
    assert product_client.post('/api/schedule/generate', json={**VALUES, 'settlement_lag': lag}).status_code == 422
    assert product_client.post('/api/calendar/resolve', json={'date': '2026-04-02', 'settlement_lag': lag}).status_code == 422


def test_product_price_and_booking_retain_the_explicit_calendar_and_dates(product_client):
    from sqlmodel import select
    from backend.app.db.models import Deal
    values = {**VALUES, 'settlement_lag': 3, 'observation_calendars': ['NYSE', 'XETR'],
              'observation_join': 'all_open', 'settlement_calendars': ['TARGET'], 'settlement_join': 'all_open'}
    payload = {**product_payload(values), 'N': 1000, 'r': 0., 'corr_matrix': [[1.]]}
    priced = product_client.post('/api/price', json=payload)
    assert priced.status_code == 200, priced.text
    receipt = priced.json()['pricing_receipt']
    created = product_client.post('/api/products', json={'command_key': 'c05-calendar-product',
        'name': 'Calendriers distincts', 'pricing_input': payload, 'pricing_receipt': receipt})
    assert created.status_code == 201, created.text
    product = created.json()
    assert product['terms']['constats']['OBS'] == values
    response = product_client.post('/api/deals', json={
        'transaction_format': 'EMTN', 'instrument_family': 'Note',
        'product_id': product['product_id'], 'product_terms_version': product['terms_version'],
        'counterparty_id': 1, 'contrepartie': 'Banque Test', 'sens': 'vente', 'devise': 'EUR',
        'nominal': 1_000_000, 'fair_value': priced.json()['price']*100, 'price_traded': priced.json()['price']*100,
        **{key: payload[key] for key in ['strike_date', 'value_date', 'maturity_date', 'payment_date', 'T']},
        'trade_date': payload['strike_date'], 'underlyings': payload['underlyings'],
        'observation_times': compiled(values).events[0].dates, 'script_snapshot': SCRIPT,
        'market_snapshot': {'r': 0., 'constats': {'OBS': values}, 'underlyings': [{'name': 'A', 'ticker': 'A', 'ccy': 'EUR', 'sigma': 0., 'q': 0.}]},
        'pricing_receipt': receipt,
    })
    assert response.status_code == 201, response.text
    row = product_client.session.exec(select(Deal)).one()
    frozen = json.loads(row.schedule_json)
    assert frozen == product['terms']['schedule']
    assert [item['date'] for item in frozen['constatations']] == preview(values)['dates'][1:]
    assert [item['date_paiement'] for item in frozen['constatations']] == preview(values)['payment_dates'][1:]
    assert json.loads(row.market_snapshot_json)['constats']['OBS'] == values
    detail = product_client.get(f'/api/deals/{row.id}').json()
    assert detail['calendar_status'] == 'FROZEN'
    assert detail['frozen_schedule'] == product['terms']['resolved_events']
    # A newer Product pointer must not change the calendar of a Deal linked to v1.
    from backend.app.services.product_repository import load_product, stage_booked_terms_amendment, stage_revision
    latest = load_product(product_client.session, row.product_id)
    next_values = {**values, 'end_date': '2026-06-30'}
    next_terms = terms_from_input({**product_payload(next_values), 'maturity_date': '2026-06-30', 'payment_date': '2026-07-03'})
    revised = stage_booked_terms_amendment(product_client.session, latest, next_terms, reason='Test de pointeur distinct')
    stage_revision(product_client.session, revised, expected_revision=latest.revision, actor_id=1,
                   action='TEST_NEXT_TERMS', reason='Version future distincte du Deal v1')
    product_client.session.commit()
    preserved = product_client.get(f'/api/deals/{row.id}').json()
    assert preserved['calendar_status'] == 'FROZEN'
    assert preserved['frozen_schedule'] == product['terms']['resolved_events']
    inconsistent = deepcopy(frozen)
    inconsistent['constatations'][0]['date'] = '2026-03-01'
    row.schedule_json = json.dumps(inconsistent); product_client.session.add(row); product_client.session.commit()
    blocked = product_client.get(f'/api/deals/{row.id}').json()
    assert blocked['calendar_status'] == 'UNAVAILABLE' and blocked['frozen_schedule'] is None
    assert blocked['schedule'] == inconsistent  # consultation never rewrites history


def test_rfq_retains_explicit_policy_and_frozen_dates_with_real_desk(product_client):
    from backend.app.db.models import Entity, RfqDesk, RfqDeskMembership
    session = product_client.session
    session.add(Entity(id=1, name='C05 organisation')); session.flush()
    user = product_client.users['alice']; user.entity_id = 1; session.add(user)
    session.add(RfqDesk(id=11, name='Structuration', entity_id=1)); session.flush()
    session.add(RfqDeskMembership(desk_id=11, user_id=user.id, rights_json='["read","prepare","price","solicit"]'))
    session.commit()
    values = {**VALUES, 'observation_calendars': ['NYSE', 'XETR'], 'observation_join': 'any_open',
              'settlement_calendars': ['TARGET'], 'settlement_join': 'all_open', 'settlement_lag': 3}
    created = product_client.post('/api/products', json={'command_key': 'c05-calendar-rfq',
        'name': 'Calendriers du panier', 'pricing_input': {**product_payload(values), 'corr_matrix': [[1.]]}})
    assert created.status_code == 201, created.text
    product = created.json()
    rfq = product_client.post('/api/rfq', json={'product_id': product['product_id'],
        'product_terms_version': product['terms_version'], 'pilot_desk_id': 11,
        'name': 'AO calendrier C05', 'kind': 'indicatif', 'sens': 'achat', 'script_snapshot': SCRIPT,
        'params': {'underlyings': [{'sigma': .2, 'q': 0.}], 'corr_matrix': [[1.]], 'r': 0., 'N': 1000, 'model': 'constant'}})
    assert rfq.status_code == 201, rfq.text
    assert rfq.json()['params']['constats']['OBS'] == values
    assert rfq.json()['params']['frozen_schedule'] == product['terms']['resolved_events']


@pytest.mark.parametrize('maturity', [1., 5.])
@pytest.mark.parametrize('explicit', [False, True])
def test_reinvestment_refuses_partial_calendar_resizing_without_mutating_source(maturity, explicit, monkeypatch):
    from backend.app.api import deals
    monkeypatch.setattr(deals, 'business_today', lambda: ORIGIN)
    values = {'OBS': {**VALUES, 'start_date': '2026-01-31', 'end_date': '2029-01-31', 'frequency': '3M'}}
    script = SCRIPT
    if explicit:
        script = 'UNDERLYING Basket\nCONSTAT StartDate\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n' + SCRIPT
        values['STARTDATE'] = '2026-01-31'
        values['OBS']['first_observation_date'] = '2026-04-30'
    market_json = json.dumps({'constats': values, 'r': 0., 'underlyings': [{'name': 'A', 'ticker': 'A', 'sigma': 20., 'q': 0.}]})
    deal = SimpleNamespace(script_snapshot=script, market_snapshot_json=market_json, strike_date='2026-01-31',
                           underlyings_json='[{"name":"A","ticker":"A"}]', devise='EUR', T=3.)
    with pytest.raises(HTTPException, match='reconstruire') as rejected: _reinvest_context(deal, maturity)
    assert rejected.value.status_code == 422 and deal.market_snapshot_json == market_json
    resolved, _, _, _, horizon = _reinvest_context(deal, None)
    assert len(resolved.events[0].dates) == 12
    assert horizon == pytest.approx(3., abs=.003)
