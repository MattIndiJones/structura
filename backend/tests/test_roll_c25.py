"""C25: executable roll budget, nominal basis and proven recovery bounds."""
from copy import deepcopy
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import variants, scripts_db
from backend.app.api.auth import get_current_user
from backend.app.db.database import get_session
from backend.app.db.models import Entity, User
from backend.app.db.models import Script, VariantStudyArchive
from backend.app.core.roll_economics import RollFinancing, fixed_maturity_cap, recovery_summary, roll_budget
from backend.app.services.archived_documents import unseal
from backend.tests.test_variantes_comparaison import BASE, CONTEXTE, _historique


@pytest.fixture
def roll_case(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def fk(conn, record): conn.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Entity(id=1, name='C25 isolated')); session.flush()
        session.add(User(id=1, username='roll', email='roll@example.test', password_hash='x', entity_id=1))
        session.commit()
    monkeypatch.setattr('backend.app.api.inlife.load_hist_prices', lambda *args, **kw: _historique())
    app = FastAPI(); app.include_router(variants.router); app.include_router(scripts_db.router)
    def session_provider():
        with Session(engine) as session: yield session
    def current():
        with Session(engine) as session: return session.get(User, 1)
    app.dependency_overrides[get_session] = session_provider
    app.dependency_overrides[get_current_user] = current
    with TestClient(app) as http:
        context = deepcopy(CONTEXTE)
        context.update(script_text='AT MATURITY\n  PAY 1.147961', params={}, constats={})
        context['global']['r'] = 0
        parent = http.post('/api/db/scripts', json={'name': 'C25 constant origin',
            'script_text': context['script_text'], 'params_json': '{}', 'constats_json': '{}',
            'global_params_json': json.dumps(context['global'])})
        assert parent.status_code == 201, parent.text
        pid = parent.json()['id']
        child = http.post(f'/api/db/scripts/{pid}/variants', json={
            'variant_title': 'C25 PAY 120%', 'variant_mode': 'roll',
            'delta': {'set': {'script': 'AT MATURITY\n  PAY 1.2'}}})
        assert child.status_code == 201, child.text
        base = {**deepcopy(BASE), 'script': context['script_text'], 'r': 0, 'constats': {}, 'user_params': {}}
        request = dict(base=base, parent_id=pid, variant_ids=[child.json()['id']], N=1000)
        yield http, engine, request
    engine.dispose()


def compare(http, request, **changes):
    response = http.post('/api/variants/compare', json={**deepcopy(request), **changes})
    assert response.status_code == 200, response.text
    return response.json()


def test_fixed_120_percent_payoff_is_distinct_from_quantity_and_recovers_above_par(roll_case):
    http, _, request = roll_case
    result = compare(http, request)
    row = result['lignes'][1]
    assert row['plafond'] > 1, 'A fixed 120% payoff cannot be capped at the nominal ratio'
    assert row['reinvested_notional'] == pytest.approx(.956635, abs=1e-6)
    assert row['recovery_mean'] == pytest.approx(1.147961, abs=1e-6)
    assert row['plafond'] == pytest.approx(row['reinvested_notional'] * 1.2)
    assert row['plafond'] > 1 and row['proba_pair_origine'] == 1


def test_observed_bid_and_entry_costs_really_change_quantity_and_recovery(roll_case):
    http, _, request = roll_case
    mid = compare(http, request)['lignes'][1]
    changed = compare(http, request, roll_financing={'exit_basis': 'observed_bid',
        'bid_pct': 112.7961, 'bid_source': 'Bank secondary desk quotation',
        'bid_observed_at': '2026-06-14T10:00:00+02:00', 'exit_cost_points': .5,
        'entry_cost_points': 1})['lignes'][1]
    assert changed['plafond'] < mid['plafond'], 'Changing the funding budget must change recovery'
    assert changed['reinvested_notional'] == pytest.approx((1.127961 - .005) / 1.21)
    assert changed['recovery_mean'] == pytest.approx(changed['reinvested_notional'] * 1.2)
    assert changed['recovery_mean'] < mid['recovery_mean']
    assert changed['roll_financing']['bid_source'] == 'Bank secondary desk quotation'


@pytest.mark.parametrize('costs', [
    {'exit_basis': 'model_haircut', 'haircut_points': 2},
    {'exit_cost_points': 2}, {'entry_cost_points': 2},
])
def test_each_cost_changes_recovery_without_changing_model_prices_or_amendments(roll_case, costs):
    http, _, request = roll_case
    created = http.post(f"/api/db/scripts/{request['parent_id']}/variants", json={
        'variant_title': 'Unchanged amendment', 'variant_mode': 'avenant', 'delta': {}})
    assert created.status_code == 201, created.text
    request['variant_ids'].append(created.json()['id'])
    before = compare(http, request)
    after = compare(http, request, roll_financing=costs)
    assert after['lignes'][1]['recovery_mean'] < before['lignes'][1]['recovery_mean']
    assert [row['prix'] for row in after['lignes']] == [row['prix'] for row in before['lignes']]
    assert after['lignes'][0] == before['lignes'][0]
    assert after['lignes'][2] == before['lignes'][2]
    assert after['lignes'][1]['roll_financing']['model_calculated_at']
    assert after['lignes'][1]['roll_financing']['exit_evidence'] == 'MODEL_HYPOTHESIS'


@pytest.mark.parametrize('bad', [
    {'exit_basis': 'observed_bid', 'bid_pct': 90},
    {'exit_basis': 'observed_bid', 'bid_pct': 90, 'bid_source': '   ', 'bid_observed_at': '2026-06-14T10:00:00Z'},
    {'exit_basis': 'observed_bid', 'bid_pct': 90, 'bid_source': 'Bank', 'bid_observed_at': '2026-06-14T10:00:00'},
    {'exit_basis': 'model', 'bid_pct': 90}, {'exit_basis': 'model', 'haircut_points': 2},
    {'entry_cost_points': -1}, {'exit_cost_points': None}, {'unexpected_entry_fee': 2},
])
def test_incomplete_or_ambiguous_financing_is_rejected_before_pricing(roll_case, monkeypatch, bad):
    http, _, request = roll_case
    monkeypatch.setattr(variants, '_prix', lambda *args: pytest.fail('Invalid inputs must not run pricing'))
    response = http.post('/api/variants/compare', json={**request, 'roll_financing': bad})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('field', ['bid_pct', 'haircut_points', 'exit_cost_points', 'entry_cost_points'])
def test_non_finite_financing_is_never_accepted(field):
    from pydantic import ValidationError
    with pytest.raises(ValidationError): RollFinancing.model_validate({field: float('nan')})
    with pytest.raises(ValidationError): RollFinancing.model_validate({field: float('inf')})


def test_a_bid_after_asof_and_a_negative_budget_leave_explicit_unpriced_rows(roll_case):
    http, _, request = roll_case
    for financing in [dict(exit_cost_points=200), dict(exit_basis='observed_bid', bid_pct=90,
        bid_source='Bank input', bid_observed_at='2026-06-15T10:00:00Z')]:
        row = compare(http, request, roll_financing=financing)['lignes'][1]
        assert row['prix'] is None and row['reinvested_notional'] is None
        assert row['refus'] and row['plafond'] is None and row['proba_pair_origine'] is None


def test_zero_cash_means_zero_position_and_never_a_free_note(roll_case):
    http, _, request = roll_case
    row = compare(http, request, roll_financing={'exit_basis': 'observed_bid', 'bid_pct': 0,
        'bid_source': 'Bank zero bid', 'bid_observed_at': '2026-06-14T10:00:00Z'})['lignes'][1]
    assert row['reinvested_notional'] == row['recovery_mean'] == row['plafond'] == row['proba_pair_origine'] == 0
    with pytest.raises(ValueError, match='strictement positif'):
        roll_budget(1, 0, RollFinancing(), valuation_date='2026-06-14', calculated_at='2026-06-14T10:00:00Z')


@pytest.mark.parametrize('script,cap', [
    ('AT MATURITY\n  PAY 1.2', 1.2), ('# fixed\nAT MATURITY:\n  PAY 100%\n  PAY 20% "Coupon"', 1.2),
    ('AT MATURITY\n  PAY .1\n  PAY .1', .2),
    ('AT MATURITY\n  PAY WOF', None), ('PARAM C = 120%\nAT MATURITY\n  PAY C', None),
    ('AT MATURITY\n  IF WOF < 2:\n    PAY 1\n  ELSE:\n    PAY WOF', None),
    ('AT 1\n  PAY 1.2', None), ('AT MATURITY\n  PAY 1.2\n  STOP', None),
])
def test_only_proven_literal_contracts_publish_a_cap(script, cap):
    assert fixed_maturity_cap(script) == cap


def test_finite_sample_max_is_never_a_contractual_cap(roll_case):
    http, _, request = roll_case
    child = http.post(f"/api/db/scripts/{request['parent_id']}/variants", json={
        'variant_title': 'Unbounded equity', 'variant_mode': 'roll',
        'delta': {'set': {'script': 'AT MATURITY\n  PAY WOF'}}})
    assert child.status_code == 201, child.text
    row = compare(http, {**request, 'variant_ids': [child.json()['id']]})['lignes'][1]
    assert row['recovery_sample_max'] > 0 and row['plafond'] is None
    assert row['recovery_cap_method'] == 'NOT_PROVEN'
    assert recovery_summary({'payoffs': [1, 1]}, 1)['plafond'] is None
    assert recovery_summary({'payoffs': []}, 1)['recovery_mean'] is None
    with pytest.raises(ValueError): recovery_summary({'payoffs': [float('nan')]}, 1)


@pytest.mark.parametrize('tenor', [1, 5])
def test_t16_costs_funding_calendar_and_frozen_study_survive_market_and_variant_changes(roll_case, monkeypatch, tenor):
    http, engine, request = roll_case
    strike = date.fromisoformat(request['base']['valuation_date'])
    payment = strike + timedelta(days=round(365.25 * tenor) + 7)
    child = http.post(f"/api/db/scripts/{request['parent_id']}/variants", json={
        'variant_title': 'T16 explicit tenor', 'variant_mode': 'roll', 'delta': {'set': {
            'script': 'AT MATURITY\n  PAY 1.2', 'global.T': tenor,
            'global.payment_date': payment.isoformat()}}})
    assert child.status_code == 201, child.text
    request['variant_ids'] = [child.json()['id']]
    request['base'].update(r=.03, funding_spread=.02)
    result = compare(http, request, roll_financing={'exit_basis': 'model_haircut', 'haircut_points': 2,
        'exit_cost_points': .25, 'entry_cost_points': 1})
    row = result['lignes'][1]
    assert not row.get('refus'), row
    budget = row['roll_financing']
    assert row['reinvested_notional'] == pytest.approx((budget['model_exit_price'] - .0225) / (row['prix'] + .01))
    assert row['recovery_mean'] == pytest.approx(row['reinvested_notional'] * 1.2)
    claims = unseal(result['preview'], 1, 'VARIANT_STUDY')
    assert claims['evidence'][1]['input']['funding_spread'] == .02
    assert claims['evidence'][1]['input']['payment_date'] == payment.isoformat()
    frozen = http.post('/api/variants/archives', json={'preview': result['preview']})
    assert frozen.status_code == 200, frozen.text
    archive_id = frozen.json()['archive_id']
    with Session(engine) as session:
        original_bytes = session.get(VariantStudyArchive, archive_id).evidence_json
        child_row = session.get(Script, child.json()['id'])
        child_row.variant_delta_json = json.dumps({'set': {'script': 'AT MATURITY\n  PAY 3'}})
        session.add(child_row); session.commit()
    request['base']['underlyings'][0]['sigma'] = .6
    request['base']['funding_spread'] = .05
    monkeypatch.setattr(variants, '_prix', lambda *args: pytest.fail('Archive reads must not price'))
    loaded = http.get(f"/api/variants/archives/{request['parent_id']}")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()[0]['evidence']['result'] == claims['result']
    repeated = http.post('/api/variants/archives', json={'preview': result['preview']})
    assert repeated.status_code == 200 and repeated.json()['archive_id'] == archive_id
    with Session(engine) as session:
        assert session.get(VariantStudyArchive, archive_id).evidence_json == original_bytes


def test_recovery_threshold_changes_when_costs_make_par_unaffordable(roll_case):
    http, _, request = roll_case
    row = compare(http, request, roll_financing={'exit_basis': 'observed_bid', 'bid_pct': 90,
        'bid_source': 'Bank lower bid', 'bid_observed_at': '2026-06-14T10:00:00Z'})['lignes'][1]
    assert row['reinvested_notional'] == pytest.approx(.75)
    assert row['recovery_mean'] == pytest.approx(.9)
    assert row['proba_pair_origine'] == 0 and row['plafond'] == pytest.approx(.9)


def test_cost_evidence_cannot_be_changed_after_server_sealing(roll_case):
    http, engine, request = roll_case
    result = compare(http, request, roll_financing={'entry_cost_points': 1})
    preview = deepcopy(result['preview'])
    preview['claims']['request']['roll_financing']['entry_cost_points'] = 0
    response = http.post('/api/variants/archives', json={'preview': preview})
    assert response.status_code == 422, response.text
    with Session(engine) as session:
        assert not session.exec(select(VariantStudyArchive)).all()


def test_cost_inputs_do_not_allow_another_user_to_read_or_archive_the_study(roll_case):
    http, engine, request = roll_case
    result = compare(http, request)
    frozen = http.post('/api/variants/archives', json={'preview': result['preview']})
    assert frozen.status_code == 200
    with Session(engine) as session:
        session.add(Entity(id=2, name='Other')); session.flush()
        other = User(id=2, entity_id=2, role='user', username='other', email='other@example.test', password_hash='x')
        session.add(other); session.commit(); session.refresh(other)
        http.app.dependency_overrides[get_current_user] = lambda: other
        assert http.get(f"/api/variants/archives/{request['parent_id']}").status_code == 403
        assert http.post('/api/variants/archives', json={'preview': result['preview']}).status_code == 404


def test_model_timestamp_preserves_the_instant_of_an_aware_business_clock(roll_case, monkeypatch):
    http, _, request = roll_case
    monkeypatch.setattr('backend.app.runtime.business_now',
        lambda: datetime(2026, 6, 14, 10, tzinfo=timezone(timedelta(hours=2))))
    result = compare(http, request)
    assert result['calculated_at'] == '2026-06-14T08:00:00+00:00'
    assert result['lignes'][1]['roll_financing']['model_calculated_at'] == result['calculated_at']
