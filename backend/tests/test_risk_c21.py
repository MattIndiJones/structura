"""C21: offline coverage, short credit exposure and current-data validity."""
from datetime import date, datetime, timedelta
from copy import deepcopy
import json

import numpy as np
import pytest
from fastapi import HTTPException

from backend.app.api import portfolios, var
from backend.app.core import var_engine
from backend.app.core.ccr import service
from backend.app.core.ccr.contracts import CreditProfile, CreditLimit, CalculationRequest
from backend.app.core.ccr.exposure import cva
from backend.app.db.database import get_session
from backend.app.db.models import DealEvent, ValuationRun
from backend.tests.test_portfolio_corr_greek import _make_session, _add_deal
from backend.tests.test_ccr_scope import scope_client


def test_missing_scenario_factor_is_rejected():
    base = {"tickers": ["TK1", "TK2"], "base": {"corr": [[1, 0], [0, 1]]}}
    scenario = var_engine.MarketScenario("x", "x", "historical", {"TK1": -10}, {"TK1": 1})
    with pytest.raises(ValueError, match="TK2"):
        var_engine.apply_scenario_to_deal_base(base, scenario)


@pytest.mark.parametrize("bad", [[], [100, float("nan"), 101], [100, 0, 101]])
def test_invalid_history_is_not_a_covered_factor(bad):
    assert var_engine._usable_tickers({"TK2": bad}, ["1", "2", "3"], ["TK2"]) == []


def test_partial_greeks_are_unknown_with_latest_run_source():
    with _make_session() as session:
        deal = _add_deal(session, "PARTIAL", [("Action", "ACT")], {},
                         per_underlying={"Action": {"delta": .3, "gamma": .8}})
        old = json.loads(deal.greeks_json)
        old["scalar"] = {"rho": 12}
        session.add(ValuationRun(deal_id=deal.id, user_id=1, run_type="GREEKS",
            context_hash="full", result_json=json.dumps(old), created_at=datetime.utcnow()-timedelta(hours=1)))
        latest = {**old, "per_underlying": {"Action": {"delta": .5}}, "scalar": {}}
        run = ValuationRun(deal_id=deal.id, user_id=1, run_type="GREEKS", context_hash="partial",
                           result_json=json.dumps(latest), created_at=datetime.utcnow()+timedelta(seconds=1))
        session.add(run); session.commit()
        risk = portfolios._aggregate_risk([deal], session)
        assert risk["per_underlying"]["ACT"]["delta_eur"] == 500_000
        assert risk["per_underlying"]["ACT"]["gamma_eur"] is None
        assert risk["scalar"]["rho"] is None
        assert risk["metric_coverage"]["gamma"]["coverage_pct"] == 0
        assert risk["metric_coverage"]["delta"]["coverage_pct"] == 100
        assert risk["metric_coverage"]["delta"]["sources"][0]["run_id"] == run.id
        assert risk["metric_coverage"]["rho"]["missing"][0]["deal_id"] == deal.id


def claim_inputs(days=2, rate=0):
    today = date.today()
    req = CalculationRequest(counterparty_id=1, as_of_date=today, n_outer=32, n_inner=32, n_dates=3)
    payment = str(today+timedelta(days=days))
    profile = CreditProfile(recovery=.4, recovery_source="USER_ASSUMPTION", pd_measure="RISK_NEUTRAL",
                            curve_source="MANUAL", pd_curve=[(1., .2)])
    return {"request": req.model_dump(mode="json"), "configuration": {
        "profiles": [{"id": 1, "data": profile.model_dump(mode="json")}],
        "limits": [{"id": 1, "data": CreditLimit(metric="cva", amount=100,
            effective_date=today, action="HARD_BLOCK").model_dump(mode="json")}]},
        "trades": [{"key": "1", "deal_id": 1, "reference": "CLAIM", "product_type": "Note",
            "currency": "EUR", "nominal": 1e6, "sens": "vente", "netting_set_id": None,
            "mtm_fraction": float(np.exp(-rate*days/365.25)), "replay": {"settlement_claim": True},
            "payment_date": payment, "settlement_amount": 1.}]}


@pytest.mark.parametrize("days", [1, 2, 3, 7, 9])
def test_short_claim_keeps_exposure_and_blocks_cva_limit(days):
    data = claim_inputs(days)
    result = service.evaluate_inputs(data)
    assert not result["errors"]
    assert result["after"]["cva"] == pytest.approx(1e6*.6*.2*days/365.25)
    assert result["after"]["epe"] == pytest.approx(1e6)
    profile = result["after"]["profile"]
    assert profile[-1]["t"] == pytest.approx(days/365.25)
    assert profile[-1]["ee"] == 0
    assert next(check for check in result["limits"] if check["metric"] == "cva")["status"] == "BREACH"
    assert not result["decision"]["booking_allowed"]
    assert service.evaluate_inputs(deepcopy(data)) == result


def test_discounted_claim_cva_matches_constant_discounted_exposure():
    data = claim_inputs(2, .05)
    result = service.evaluate_inputs(data)
    assert result["after"]["cva"] == pytest.approx(1e6*np.exp(-.05*2/365.25)*.6*.2*2/365.25)


def test_monitor_and_preparation_invalidate_after_official_fixing(scope_client):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    event = DealEvent(deal_id=deals[0].id, event_index=0, event_date=deals[0].strike_date,
        t_years=0, spots_json='{"Synthetic":100}', status='observé', source='manuel', fixing_version=1,
        fixing_record_sha256='initial-official-fixing')
    session.add(event); session.commit()
    body = dict(counterparty_id=cpty, prepare_mtm=True, common_rate=.03, n_outer=32, n_inner=32, n_dates=3)
    first = client.post('/api/ccr/calculate', json=body).json()
    assert not first['errors']
    assert not client.get('/api/ccr/monitor').json()[0]['stale']
    archived = client.get(f"/api/ccr/runs/{first['run_id']}").json()
    event.fixing_version = 2
    event.fixing_record_sha256 = 'corrected-official-fixing'
    event.spots_json = '{"Synthetic":101}'
    session.add(event)
    session.commit()
    assert client.get('/api/ccr/monitor').json()[0]['stale']
    second = client.post('/api/ccr/calculate', json=body).json()
    assert not second['preparation_cache']['reused']
    assert client.get(f"/api/ccr/runs/{first['run_id']}").json() == archived


def test_var_launch_refuses_incomplete_factors_before_enqueue(monkeypatch):
    from types import SimpleNamespace
    deals = [SimpleNamespace(id=i, reference=f"D{i}", nominal=1e6, devise="EUR", sens="vente") for i in (1,2)]
    monkeypatch.setattr(var, "build_deal_scenario_base", lambda d,*a: dict(deal_id=d.id, reference=d.reference,
        nominal=d.nominal, mtm_before=1, tickers=[f"TK{d.id}"],
        base={"corr":[[1]], "T_remaining":1, "engine_uls":[{"sigma":.2}], "n_paths":1000}))
    monkeypatch.setattr(var, "fx_rate_to", lambda *a: 1)
    monkeypatch.setattr(var, "load_hist_prices", lambda *a,**kw: {"dates": [str(i) for i in range(70)],
        "prices": {"TK1": [100+np.sin(i) for i in range(70)]}})
    monkeypatch.setattr(var, "enqueue_batch", lambda *a,**kw: pytest.fail("No incomplete batch"))
    with pytest.raises(HTTPException) as exc:
        var._launch_var_study(deals, None, 1, "test", var.VarRequest(method="historical"))
    assert exc.value.status_code == 422
    assert "TK2" in str(exc.value.detail)


def test_partial_portfolio_totals_are_separate_from_available_sums():
    with _make_session() as session:
        a = _add_deal(session, 'KNOWN', [('Action', 'ACT')], {},
            per_underlying={'Action': {'delta': 0., 'gamma': .2}})
        b = _add_deal(session, 'MISSING', [('Action', 'ACT')], {},
            per_underlying={'Action': {'delta': .5}})
        result = portfolios._aggregate_risk([a, b], session)
        bucket = result['per_underlying']['ACT']
        assert bucket['gamma_eur'] is None
        assert bucket['available_gamma_eur'] == 200_000
        assert bucket['delta_eur'] == 500_000
        assert result['metric_coverage']['gamma']['coverage_pct'] == 50
        assert result['metric_coverage']['delta']['coverage_pct'] == 100  # Real zero is known.


def test_risk_scope_defaults_to_production_with_explicit_uat():
    with _make_session() as session:
        a = _add_deal(session, 'PROD', [('Action', 'ACT')], {}, per_underlying={'Action': {'delta': .1}})
        b = _add_deal(session, 'UAT', [('Action', 'ACT')], {}, per_underlying={'Action': {'delta': .9}})
        b.uat_batch_id = 1
        session.add(b); session.commit()
        prod = portfolios._aggregate_risk([a,b], session)
        uat = portfolios._aggregate_risk([a,b], session, data_scope='UAT')
        assert prod['per_underlying']['ACT']['delta_eur'] == 100_000
        assert uat['per_underlying']['ACT']['delta_eur'] == 900_000
        assert not prod['is_test'] and uat['is_test']
        assert prod['metric_coverage']['delta']['required'] == 1


def test_corrected_fixing_rejects_archived_mtm_and_cached_greeks(scope_client):
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    deal = deals[0]
    request = CalculationRequest(counterparty_id=cpty)
    assert 'missing' not in service.archived_trade(session, deal, request)
    deal.greeks_json = json.dumps({'valuation_date':str(date.today()), 'contract_version':deal.contract_version,
        'per_underlying':{'Synthetic':{'delta':.5}}, 'scalar':{}})
    session.add(deal)
    session.add(DealEvent(deal_id=deal.id, event_index=0, event_date=deal.strike_date, fixing_version=1,
        fixing_record_sha256='official', spots_json='{"Synthetic":101}'))
    session.commit()
    assert 'missing' in service.archived_trade(session, deal, request)
    assert portfolios._greeks_snapshots([deal], session, date.today()) == {}


def test_short_optional_projection_is_unavailable_instead_of_extended():
    from backend.tests.test_ccr import proposed
    trade = proposed()
    trade['pricing'].update(T=2/365.25, strike_date=str(date.today()),
        script='AT MATURITY\n  PAY 1 "capital"')
    data = claim_inputs()
    data['trades'] = [trade]
    result = service.evaluate_inputs(data)
    assert result['after']['cva'] is None and result['after']['pfe95'] is None
    assert not result['decision']['booking_allowed']
    assert any('sous une semaine' in e for e in result['errors'])


def test_fixed_claims_net_only_over_their_actual_common_life():
    data = claim_inputs(3)
    first = data['trades'][0]
    first['netting_set_id'] = 1
    second = {**first, 'key':'2', 'deal_id':2, 'sens':'achat',
              'payment_date':str(date.today()+timedelta(days=1))}
    data['trades'].append(second)
    from backend.tests.test_ccr import legal_config
    config = legal_config()
    config['agreements'][0]['data']['effective_date'] = str(date.today())
    config['netting-sets'][0]['data']['product_scope'] = ['Note']
    data['configuration'].update(config)
    result = service.evaluate_inputs(data)
    assert not result['errors']
    assert result['after']['current_exposure'] == 0
    assert result['after']['cva'] == pytest.approx(1e6*.6*.2*2/365.25)


def test_c04_amendment_rechecks_short_claim_cva_without_mutating_terms(scope_client):
    from sqlmodel import select
    from backend.app.db.models import User, ProductRecord
    from backend.app.db.ccr_models import RECORDS
    from backend.tests.product_helpers import attach_product_to_deal
    client, cpty, _, deals, _ = scope_client
    session = client.app.dependency_overrides[get_session]()
    user = session.exec(select(User).where(User.username == 'risk')).one()
    deal = deals[0]
    deal.payment_date = str(date.today()+timedelta(days=2))
    attach_product_to_deal(session, deal)
    session.add(deal)
    limit_row = session.exec(select(RECORDS['limits'])).one()
    limit_row.payload_json = json.dumps(claim_inputs()['configuration']['limits'][0]['data'])
    session.add(limit_row)
    session.add(RECORDS['profiles'](entity_id=user.entity_id, counterparty_id=cpty, updated_by=user.id,
        payload_json=json.dumps(claim_inputs()['configuration']['profiles'][0]['data'])))
    session.commit()
    session.refresh(deal)
    before = deal.model_dump(mode='json')
    product_before = session.get(ProductRecord, deal.product_id).model_dump(mode='json')
    with pytest.raises(HTTPException) as exc:
        service.enforce_amendment(session, user, deal, {'nominal':1_100_000})
    proof = exc.value.detail['credit_check']
    assert proof['after']['cva'] == pytest.approx(1_100_000*.6*.2*2/365.25)
    assert proof['decision']['hard_block']
    assert proof['valuation_run_id']
    session.refresh(deal)
    assert deal.model_dump(mode='json') == before
    assert session.get(ProductRecord, deal.product_id).model_dump(mode='json') == product_before


def test_var_http_production_uat_and_c01_visibility_are_preserved(scope_client, monkeypatch):
    from types import SimpleNamespace
    client, _, _, deals, _ = scope_client
    client.app.include_router(var.router)
    recorded = []
    def enqueue(*args, **kwargs):
        recorded.append(kwargs['params'])
        return SimpleNamespace(id=len(recorded), status='queued', total_jobs=len(kwargs['job_payloads']))
    monkeypatch.setattr(var, 'enqueue_batch', enqueue)
    monkeypatch.setattr(var, 'build_deal_scenario_base', lambda d,*a: {
        'deal_id':d.id, 'reference':d.reference, 'nominal':d.nominal, 'mtm_before':1,
        'tickers':[], 'base':{'settlement_claim':True}})
    monkeypatch.setattr(var, 'fx_rate_to', lambda *a:1.)
    prod = client.post('/api/portfolios/var-global', json={'method':'historical'})
    assert prod.status_code == 202, prod.text
    assert [d['deal_id'] for d in recorded[-1]['requested_deals']] == [deals[0].id]
    assert recorded[-1]['data_scope'] == 'PRODUCTION' and not recorded[-1]['is_test']
    uat = client.post('/api/portfolios/var-global', json={'method':'historical','data_scope':'UAT'})
    assert uat.status_code == 202, uat.text
    assert {d['deal_id'] for d in recorded[-1]['requested_deals']} == {deals[1].id, deals[2].id}
    assert recorded[-1]['is_test']
    assert deals[3].id not in {d['deal_id'] for p in recorded for d in p['requested_deals']}
