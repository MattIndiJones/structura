"""C22: contractual cash dates, coherent receivables and dividend attribution."""
from copy import deepcopy
from datetime import date, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals, portfolios
from backend.app.core import valuation_notes
from backend.app.db.models import Deal, DealEvent, ValuationRun
from backend.tests.product_helpers import attach_product_to_deal

USER = SimpleNamespace(id=1, role='user', entity_id=None)
ORIGIN = date(2026, 1, 15)
OBS = date(2026, 9, 15)
PAYMENT = date(2026, 9, 22)
MATURITY = date(2027, 1, 15)
SCRIPT = 'CONSTAT() OBS\nAT OBS:\n  PAY 0.1 "coupon"\nAT MATURITY:\n  PAY 1 "capital"'


@pytest.fixture
def book(monkeypatch):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        policy = dict(start_date=str(ORIGIN), first_observation_date=str(OBS), end_date=str(OBS),
            roll_date=str(OBS), frequency='1Y', convention='following', settlement_lag=5,
            observation_calendars=['TARGET'], observation_join='all_open',
            settlement_calendars=['TARGET'], settlement_join='all_open')
        deal = Deal(reference='C22', user_id=1, status='actif', sens='vente', devise='EUR', nominal=1e6,
            script_snapshot=SCRIPT, strike_date=str(ORIGIN), value_date=str(ORIGIN),
            maturity_date=str(MATURITY), payment_date=str(MATURITY), T=(MATURITY-ORIGIN).days/365.25,
            underlyings_json='[{"name":"Action", "ticker":"TK1", "s0_abs":100}]',
            market_snapshot_json=json.dumps({'model':'constant','r':0,'corrMatrix':[[1]],
                'antithetic':True, 'underlyings':[{'name':'Action','ticker':'TK1','sigma':20,'q':0}],
                'constats':{'OBS':policy}}))
        attach_product_to_deal(session, deal)
        session.add(deal); session.flush()
        session.add(DealEvent(deal_id=deal.id, event_index=0, event_date=str(ORIGIN),
            t_years=0, spots_json='{"Action":100}', status='observé', label='Strike', source='manuel'))
        session.commit(); session.refresh(deal)
        def prices(tickers, start, end, **kwargs):
            days = [date.fromisoformat(start)+timedelta(days=i)
                    for i in range((date.fromisoformat(end)-date.fromisoformat(start)).days+1)]
            return {'dates':list(map(str,days)), 'prices':{tk:[100.]*len(days) for tk in tickers},
                    'provider':'SYNTHETIC'}
        monkeypatch.setattr(deals, 'load_hist_prices', prices)
        monkeypatch.setattr(deals, 'realized_market', lambda *a,**kw: {'sigma':{'TK1':.2}, 'corr':[[1]], 'n_returns':252})
        monkeypatch.setattr(deals, 'dividend_profile', lambda *a,**kw: {'ok':True,'yield_declared':0.})
        yield session, deal


def explain(book, first, last, recalibrate='none'):
    session, deal = book
    return deals._explain_core(deal, session, 1000,
        deals.MtmExplainRequest(date1=str(first), date2=str(last), recalibrate=recalibrate))[0]


@pytest.mark.parametrize('start,end,cash,delta', [
    (14,16,0.,0.), (16,21,0.,0.), (21,23,10.,-10.), (21,22,10.,-10.), (22,23,0.,0.)])
def test_coupon_cash_uses_payment_day_and_reconciles(book, start, end, cash, delta):
    result = explain(book, date(2026,9,start), date(2026,9,end))
    assert result['flows_total_pts'] == pytest.approx(cash, abs=1e-9)
    assert result['delta_pts'] == pytest.approx(delta, abs=1e-9)
    assert result['pnl_total_pts'] == pytest.approx(0., abs=1e-9)
    assert result['residual_pts'] == pytest.approx(0., abs=1e-9)
    assert sum(s['delta_pts'] for s in result['steps']) == pytest.approx(delta, abs=1e-9)
    if delta == 0:
        assert all(abs(s['delta_pts']) < 1e-9 for s in result['steps'])
    if cash:
        assert result['flows_detached'][0]['payment_date'] == str(PAYMENT)
        assert result['flows_detached'][0]['date'] == str(OBS)


@pytest.mark.parametrize('sense,sign', [('vente',1),('achat',-1)])
def test_portfolio_cash_and_mtm_have_one_position_sign(book, sense, sign):
    session, deal = book
    deal.sens = sense
    result = portfolios._run_explain_on_book([deal], session, 1000,
        deals.MtmExplainRequest(date1='2026-09-21', date2='2026-09-23', recalibrate='none'))
    assert not result['errors'] and not result['skipped']
    assert result['flows_total_eur'] == pytest.approx(sign*100_000)
    assert result['delta_mtm_eur'] == pytest.approx(-sign*100_000)
    assert result['pnl_total_eur'] == pytest.approx(0.,abs=1e-6)
    assert result['contributions'][0]['pnl_eur'] == pytest.approx(0.,abs=1e-6)


def linear_deal(book):
    session, deal = book
    deal.script_snapshot = 'AT MATURITY:\n  PAY S[1] "final"'
    market = json.loads(deal.market_snapshot_json)
    market['constats'] = {}
    deal.market_snapshot_json = json.dumps(market)
    attach_product_to_deal(session, deal)
    session.add(deal); session.commit(); session.refresh(deal)
    return deal


def test_only_q_change_has_dividend_effect_and_no_vega(book, monkeypatch):
    linear_deal(book)
    monkeypatch.setattr(deals, 'dividend_profile', lambda tk, asof: {
        'ok':True,'yield_declared':0. if asof < str(OBS) else .08})
    result = explain(book, date(2026,9,14), date(2026,9,16), 'realized')
    steps = {s['label']:s['delta_pts'] for s in result['steps']}
    assert result['market1']['sigma'] == result['market2']['sigma']
    assert steps['Effet volatilité'] == pytest.approx(0.,abs=1e-12)
    assert steps['Effet dividendes'] < -1
    assert sum(steps.values())+result['residual_pts'] == pytest.approx(result['delta_pts'],abs=1e-9)


def test_portfolio_keeps_dividend_contribution(book, monkeypatch):
    linear_deal(book)
    monkeypatch.setattr(deals, 'dividend_profile', lambda tk, asof: {
        'ok':True,'yield_declared':0. if asof < str(OBS) else .08})
    session, deal = book
    result = portfolios._run_explain_on_book([deal],session,1000,
        deals.MtmExplainRequest(date1='2026-09-14',date2='2026-09-16',recalibrate='realized'))
    assert not result['errors'] and not result['skipped']
    steps = {s['key']:s['delta_eur'] for s in result['steps']}
    assert steps['dividendes'] < -10_000
    assert steps['vol'] == pytest.approx(0.,abs=1e-9)
    assert sum(steps.values())+result['residual_eur'] == pytest.approx(result['delta_mtm_eur'],abs=.02)


def frozen_runs(book, first, last):
    session, deal = book
    ids = [deals.deal_mtm(deal.id, USER, session, n_paths=1000,
        body=deals.MtmRequest(recalibrate='none',valuation_date=day))['valuation_run_id']
        for day in (first,last)]
    return [session.get(ValuationRun, rid) for rid in ids]


@pytest.mark.parametrize('start,end,delta', [(14,16,0.), (21,23,-10.)])
def test_frozen_comparison_rolls_receivables_with_realized_state_without_false_jump(book, start, end, delta):
    runs = frozen_runs(book, date(2026,9,start), date(2026,9,end))
    before = [(r.context_json,r.result_json,r.diagnostics_json) for r in runs]
    result = valuation_notes.compare_runs(*runs)
    assert result['available']
    assert result['delta_pts'] == pytest.approx(delta,abs=1e-10)
    assert result['steps'][0]['delta_pts'] == pytest.approx(delta,abs=1e-10)
    assert all(abs(s['delta_pts']) < 1e-10 for s in result['steps'][1:])
    assert 'pnl_total_pts' not in result  # Frozen Valo Explain remains a change in MtM.
    assert result['residual_pts'] == pytest.approx(0.,abs=1e-10)
    assert [(r.context_json,r.result_json,r.diagnostics_json) for r in runs] == before


def replace_script(book, script):
    session, deal = book
    deal.script_snapshot = script
    attach_product_to_deal(session, deal)
    session.add(deal); session.commit(); session.refresh(deal)


def test_realized_coupon_memory_moves_with_calendar(book):
    replace_script(book, 'CONSTAT() OBS\nAT OBS:\n  SET DUE = DUE + 0.1\n'
        '  IF WOF >= 1.1:\n    PAY DUE "coupon"\n    SET DUE = 0\n'
        'AT MATURITY:\n  PAY 1 + DUE "capital et mémoire"')
    result = explain(book, date(2026,9,14), date(2026,9,16))
    assert result['flows_total_pts'] == 0
    assert result['pnl_total_pts'] == pytest.approx(0.,abs=1e-10)
    assert all(abs(s['delta_pts']) < 1e-10 for s in result['steps'])
    assert result['residual_pts'] == pytest.approx(0.,abs=1e-10)


def test_equal_pay_legs_are_not_deduplicated(book):
    replace_script(book, SCRIPT.replace('PAY 0.1 "coupon"', 'PAY 0.05 "coupon"\n  PAY 0.05 "coupon"'))
    result = explain(book, date(2026,9,21), date(2026,9,23))
    assert len(result['cash_flows']) == 2
    assert result['flows_total_pts'] == pytest.approx(10)
    assert result['pnl_total_pts'] == pytest.approx(0.,abs=1e-10)


def test_negative_contractual_cash_is_preserved(book):
    replace_script(book, SCRIPT.replace('PAY 0.1', 'PAY -0.1'))
    result = explain(book, date(2026,9,21), date(2026,9,23))
    assert result['flows_total_pts'] == pytest.approx(-10)
    assert result['delta_pts'] == pytest.approx(10)
    assert result['pnl_total_pts'] == pytest.approx(0.,abs=1e-10)


@pytest.mark.parametrize('field,value', [('q',.08), ('dividend_curve',[[.1,.08],[1.,.02]])])
def test_frozen_dividends_do_not_change_diffusion_bucket(book, field, value):
    from backend.tests.test_valuation_notes import cloned_run
    linear_deal(book)
    session, _ = book
    first = frozen_runs(book, date(2026,9,14),date(2026,9,14))[0]
    def change(payload):
        underlying = payload['valuation_context']['underlyings'][0]
        underlying[field] = value
        if field == 'dividend_curve':
            underlying['q'] = value[0][1]
    second = cloned_run(session,first,change)
    result = valuation_notes.compare_runs(first,second)
    steps = {s['label']:s['delta_pts'] for s in result['steps']}
    assert result['available']
    assert steps['Dividendes'] < -.1
    assert steps['Diffusion et change'] == 0
    assert result['residual_pts'] == pytest.approx(0.,abs=1e-12)


def test_portfolio_uses_prices_before_rounding_points(book, monkeypatch):
    linear_deal(book)
    session, deal = book
    deal.nominal = 1e9
    monkeypatch.setattr(deals,'dividend_profile',lambda tk,asof:{'ok':True,'yield_declared':0. if asof < str(OBS) else .0137})
    body = deals.MtmExplainRequest(date1='2026-09-14',date2='2026-09-16',recalibrate='realized')
    raw,_,_ = deals._explain_core(deal,session,1000,body)
    result = portfolios._run_explain_on_book([deal],session,1000,body)
    assert result['delta_mtm_eur'] == pytest.approx(round((raw['mtm2']-raw['mtm1'])*deal.nominal,2),abs=.005)
    assert sum(s['delta_eur'] for s in result['steps'])+result['residual_eur'] == pytest.approx(result['delta_mtm_eur'],abs=.02)


@pytest.mark.parametrize('row', [{}, {'cf':.1,'date':'2026-09-22'},
    {'cf':.1,'payment_date':'invalid'}, {'cf':float('nan'),'payment_date':'2026-09-22'}])
def test_unknown_payment_or_amount_does_not_become_observation_cash(row):
    from backend.app.core.valuation_attribution import contractual_cash_in_period
    with pytest.raises(ValueError):
        contractual_cash_in_period({'settled_cash_flows':[row]},date(2026,9,21),date(2026,9,23))


def test_official_correction_changes_new_cash_but_not_archived_explain(monkeypatch, tmp_path):
    from backend.tests.test_fixing_finality_registry import coupon_deal
    from backend.tests.test_workflow_controls import _events, _resolve_auto_exception, OPS_MAKER
    from backend.app.db.models import ArchivedDocument
    from backend.tests.test_mtm_explain import _fake_prices
    session, deal = coupon_deal()
    monkeypatch.setattr(deals,'load_hist_prices',_fake_prices(lambda day:40.))
    monkeypatch.setattr(deals,'realized_market',lambda *a,**kw:{'sigma':{'TK1':.2},'corr':[[1]],'n_returns':252})
    monkeypatch.setattr(deals,'dividend_profile',lambda *a,**kw:{'ok':False})
    body = deals.MtmExplainRequest(date1='2026-01-05',date2='2026-01-07',recalibrate='none')
    first = deals.deal_mtm_explain(deal.id,OPS_MAKER,session,n_paths=1000,body=body)
    assert first['flows_total_pts'] == 10
    archived = session.get(ArchivedDocument,first['archive_id'])
    before = (archived.data_json,archived.pdf_base64,archived.content_hash)
    import base64
    (tmp_path/'explain-before-correction.pdf').write_bytes(base64.b64decode(archived.pdf_base64))
    event = _events(session,deal)[-1]
    version = event.current_fixing_version_id
    event.fixing_status = 'MANUAL_REVIEW_REQUIRED'
    session.add(event);session.commit()
    _resolve_auto_exception(session,deal,event,action='REPLACE_MANUAL',spots={'UL1':70.})
    second = deals.deal_mtm_explain(deal.id,OPS_MAKER,session,n_paths=1000,body=body)
    assert event.current_fixing_version_id != version
    assert second['flows_total_pts'] == 0
    assert first['archive_id'] != second['archive_id']
    (tmp_path/'explain-after-correction.pdf').write_bytes(base64.b64decode(
        session.get(ArchivedDocument,second['archive_id']).pdf_base64))
    session.refresh(archived)
    assert (archived.data_json,archived.pdf_base64,archived.content_hash) == before
    assert second['market2']['data']['fixing_registry']['official_fixings'][-1]['version_id'] == event.current_fixing_version_id
    session.close()
