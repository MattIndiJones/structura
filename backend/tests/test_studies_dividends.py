"""Hand-worked dividend accounting, cutoffs and reinvestment controls."""
import datetime as dt
import json

import pytest
from backend.app.core.amc_dividends import prepare_dividends, DividendPolicy


def order(oid='buy', qty=10, date='2024-01-01', isin='X', price=100):
    return dict(id=oid, isin=isin, name=isin, executed_qty=qty, ordered_qty=qty,
                date=dt.datetime.fromisoformat(date), state='Done', price_local=price,
                price_prod=price, fx=1, ccy='USD', notional_prod=abs(qty*price), side='BUY' if qty > 0 else 'SELL')


def event(**kwargs):
    return dict(id='D1', asset_id='X', currency='USD', ex_date='2024-01-05',
                payment_date='2024-01-10', gross_per_share=10, withholding_rate=.1, **kwargs)


def run(tmp_path, events=None, orders=None, end='2024-01-31', policy=None, currency='USD', fee=0):
    p = tmp_path/'dividends.json'
    p.write_text(json.dumps({'events': [event()] if events is None else events}))
    return prepare_dividends(str(p), '', {'status': 'provided', **(policy or {})},
                             [order()] if orders is None else orders, '2024-01-01', end, currency,
                             transaction_fee_pct=fee)


def test_detachment_receivable_payment_is_not_second_income(tmp_path):
    before = run(tmp_path, end='2024-01-04')
    detached = run(tmp_path, end='2024-01-08')
    paid = run(tmp_path)
    assert before['totals']['net_income_prod'] == 0
    assert detached['totals']['receivable_prod'] == detached['totals']['net_income_prod'] == 90
    assert detached['totals']['paid_prod'] == 0
    assert paid['totals']['net_income_prod'] == paid['totals']['paid_prod'] == 90
    assert paid['totals']['receivable_prod'] == 0
    assert paid['events'][0]['withholding_local'] == 10


def test_entitlement_before_ex_date_trades(tmp_path):
    r = run(tmp_path, orders=[order(), order('sale', -10, '2024-01-05')])
    assert r['totals']['net_income_prod'] == 90
    with pytest.raises(ValueError, match='Quantité'):
        run(tmp_path, events=[event(eligible_quantity=11)])


def test_unknown_none_and_contradiction(tmp_path):
    for status, value in [('unknown', None), ('none', 0)]:
        r = prepare_dividends('', '', {'status': status}, [], '2024-01-01', '2024-12-31', 'USD')
        assert r['totals']['net_income_prod'] == value
    with pytest.raises(ValueError, match='statut renseignés'):
        run(tmp_path, policy={'status': 'none'})


def test_fx_receivable_and_payment(tmp_path):
    e = event()
    e.update(currency='EUR', fx_at_ex=1.1, fx_at_payment=1.2,
             fx_at_valuation=1.15, fx_valuation_date='2024-01-08')
    r = run(tmp_path, events=[e], end='2024-01-08')
    assert r['totals']['income_at_ex_prod'] == pytest.approx(99)
    assert r['totals']['receivable_prod'] == pytest.approx(103.5)
    assert r['totals']['fx_pnl_prod'] == pytest.approx(4.5)
    paid = run(tmp_path, events=[e])
    assert paid['totals']['net_income_prod'] == pytest.approx(108)
    assert paid['totals']['fx_pnl_prod'] == pytest.approx(9)
    with pytest.raises(ValueError, match='date exacte'):
        run(tmp_path, events=[e], end='2024-01-09')


@pytest.mark.parametrize('fractional,quantity,left', [(True, 4.5, 0), (False, 4, 10)])
def test_reinvestment_new_lot_and_cash_remainder(tmp_path, fractional, quantity, left):
    e = event(executions=[dict(asset_id='X', date='2024-01-10', price_local=20, currency='USD')])
    r = run(tmp_path, events=[e], policy={'treatment': 'automatic', 'execution_source': 'reconstruct', 'fractional_shares': fractional})
    assert r['totals']['net_income_prod'] == 90
    assert r['generated_orders'][0]['executed_qty'] == quantity
    assert r['events'][0]['cash_after_reinvestment_prod'] == left
    assert r['generated_orders'][0]['dividend_reconstructed'] is True


def test_existing_purchase_is_linked_not_duplicated(tmp_path):
    e = event(executions=[dict(asset_id='X', date='2024-01-10', order_id='reinvest')])
    r = run(tmp_path, events=[e], orders=[order(), order('reinvest', 4.5, '2024-01-10', price=20)], policy={'treatment': 'automatic'})
    assert r['generated_orders'] == []
    assert r['totals']['reinvested_prod'] == 90
    assert r['totals']['net_income_prod'] == 90


def test_reconstruction_refuses_ambiguous_existing_buy(tmp_path):
    e = event(executions=[dict(asset_id='X', date='2024-01-10', price_local=20, currency='USD')])
    with pytest.raises(ValueError, match='déjà présent'):
        run(tmp_path, events=[e], orders=[order(), order('real', 4.5, '2024-01-10')],
            policy={'treatment': 'automatic', 'execution_source': 'reconstruct'})


def test_basket_fee_and_reinvestment_entitlement(tmp_path):
    e = event(executions=[dict(asset_id='Y', date='2024-01-10', price_local=9, currency='USD'),
                         dict(asset_id='Z', date='2024-01-10', price_local=18, currency='USD')])
    policy = {'treatment': 'automatic', 'execution_source': 'reconstruct', 'destination': 'basket',
              'allocations': {'Y': .5, 'Z': .5}, 'reinvestment_fee_pct': 1}
    r = run(tmp_path, events=[e], policy=policy)
    assert sum(o['notional_prod'] for o in r['generated_orders']) == pytest.approx(90/1.01)
    assert r['totals']['reinvestment_cost_prod'] == pytest.approx(90-90/1.01)
    assert r['transaction_fee_adjustment'] == pytest.approx(90-90/1.01)


def test_second_dividend_includes_reconstructed_shares(tmp_path):
    e = event(executions=[dict(asset_id='X', date='2024-01-10', price_local=20, currency='USD')])
    e2 = dict(e, id='D2', ex_date='2024-01-15', payment_date='2024-02-10', executions=[])
    r = run(tmp_path, events=[e, e2], policy={'treatment': 'automatic', 'execution_source': 'reconstruct'})
    assert r['events'][1]['eligible_quantity'] == 14.5
    assert r['events'][1]['receivable_prod'] == 130.5


def test_pending_reinvestment_and_missing_execution(tmp_path):
    r = run(tmp_path, policy={'treatment': 'automatic'}, end='2024-01-08')
    assert r['issues'] == []
    r = run(tmp_path, policy={'treatment': 'automatic'})
    assert r['issues'] and r['generated_orders'] == []


@pytest.mark.parametrize('change', [{'payment_date': '2024-01-04'}, {'gross_local': 999},
    {'net_local': 999}, {'withholding_rate': float('nan')}, {'fx_at_ex': 2}])
def test_invalid_events_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        run(tmp_path, events=[dict(event(), **change)])


def test_duplicates_and_unknown_tax_rejected(tmp_path):
    with pytest.raises(ValueError, match='dupliqué'):
        run(tmp_path, events=[event(), event()])
    e = event()
    del e['withholding_rate']
    with pytest.raises(ValueError, match='Retenue inconnue'):
        run(tmp_path, events=[e])
    e.update(net_local=100)
    assert run(tmp_path, events=[e])['totals']['net_income_prod'] == 100


def test_policy_allocations_and_discretionary_reconstruction_rejected():
    with pytest.raises(ValueError):
        DividendPolicy(destination='basket', allocations={'X': .5})
    with pytest.raises(ValueError):
        DividendPolicy(treatment='discretionary', execution_source='reconstruct')


def test_split_units_and_net_only_event(tmp_path):
    e = event(entitlement_unit_factor=.5, eligible_quantity=10)
    r = run(tmp_path, events=[e], orders=[order(qty=20)])
    assert r['totals']['net_income_prod'] == 90
    e = event()
    del e['gross_per_share']
    del e['withholding_rate']
    e['net_local'] = 90
    r = run(tmp_path, events=[e])
    assert r['events'][0]['gross_local'] is None
    assert r['events'][0]['withholding_local'] is None
    assert r['totals']['net_income_prod'] == 90


def test_reinvestment_overspend_and_order_reuse(tmp_path):
    e = event(executions=[dict(asset_id='X', date='2024-01-10', order_id='reinvest')])
    with pytest.raises(ValueError, match='supérieur'):
        run(tmp_path, events=[e], orders=[order(), order('reinvest', 5, '2024-01-10', price=20)], policy={'treatment': 'automatic'})
    e2 = dict(e, id='D2', asset_id='Y')
    with pytest.raises(ValueError, match='plusieurs'):
        run(tmp_path, events=[e, e2], orders=[order(), order('y', isin='Y'), order('reinvest', 4.5, '2024-01-10', price=20)],
            policy={'treatment': 'automatic', 'destination': 'basket', 'allocations': {'X': 1}})


def test_weekday_delay_and_missing_price(tmp_path):
    e = dict(event(), payment_date='2024-01-12', executions=[dict(asset_id='X', date='2024-01-15', price_local=10, currency='USD')])
    r = run(tmp_path, events=[e], policy={'treatment': 'automatic', 'execution_source': 'reconstruct', 'delay_weekdays': 1})
    assert r['generated_orders'][0]['date'].date() == dt.date(2024, 1, 15)
    del e['executions'][0]['price_local']
    with pytest.raises(ValueError, match='Prix et devise'):
        run(tmp_path, events=[e], policy={'treatment': 'automatic', 'execution_source': 'reconstruct', 'delay_weekdays': 1})


@pytest.mark.parametrize('cutoff,quantity', [('2024-01-08', 10), ('2024-01-10', 11)])
def test_full_pipeline_receivable_then_reinvestment(tmp_path, monkeypatch, cutoff, quantity):
    from backend.app.core.amc_study import run_study
    from backend.app.core import amc_prices
    from backend.app.core.amc_manifest import StudyManifest
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected market lookup')
    monkeypatch.setattr(amc_prices, 'build_marks', forbidden)
    monkeypatch.setattr(amc_prices, 'auto_populate_store', forbidden)
    (tmp_path/'orders.json').write_text(json.dumps({'data': {'orders': {'items': [dict(
        id='initial', state='Done', tradeDate='2024-01-01', executedQuantity=10,
        executionPrice={'amount': 100, 'currency': 'USD'}, usedFxRate=1,
        underlying={'isin': 'X', 'name': 'X', 'currency': 'USD'})]}}}))
    (tmp_path/'nav.csv').write_text('Date,Price,Outstanding quantity\n2024-01-01,100,10\n'+cutoff+',99,10\n')
    (tmp_path/'composition.json').write_text(json.dumps({'data': {'products': {'items': [dict(
        isin='FUND', currency='USD', outstandingQuantity=10, netAssetValue={'value': 99, 'date': cutoff},
        components=[{'underlying': {'isin': 'X', 'name': 'X', 'currency': 'USD'}, 'position': quantity, 'weight': quantity*90/990}]) ]}}}))
    e = event(executions=[dict(asset_id='X', date='2024-01-10', price_local=90, currency='USD')])
    (tmp_path/'dividends.json').write_text(json.dumps({'events': [e]}))
    manifest = StudyManifest.model_validate({'product': {'isin': 'FUND', 'currency': 'USD'},
        'files': {'orders': ['orders.json'], 'nav_timeseries': 'nav.csv', 'composition': 'composition.json', 'dividends': 'dividends.json'},
        'params': {'valuation_source': 'composition', 'orders_split_adjusted': True, 'management_fee_pct': 0,
            'perf_fee_pct': 0, 'txn_cost_pct': 0, 'dividends': {'status': 'provided', 'treatment': 'automatic', 'execution_source': 'reconstruct'}},
        'blocks': {'A_factor': False, 'B_attribution': True, 'C_trading': True, 'D_behaviour': True, 'E_bh': False,
            'F_replicability': False, 'H_timing': False, 'I_stockpicking': False, 'J_riskmanagement': False, 'K_marketshocks': False}})
    result = run_study(manifest.model_dump(), str(tmp_path))
    b = result['block_b']
    assert b['totals']['unreal_pnl'] == -100
    assert b['totals']['total_pnl_net_of_fees'] == -10
    assert b['totals']['reconciliation']['gap_prod'] == 0
    assert b['per_name'][0]['dividends_net'] == 90
    assert b['per_name'][0]['total_with_dividends'] == -10
    assert len(result['reconstructed_dividend_orders']) == quantity-10
    assert result['dividends']['totals']['receivable_prod'] == (90 if quantity == 10 else 0)


def test_dated_six_year_oracle_per_asset(tmp_path, monkeypatch):
    import csv
    import shutil
    import zipfile
    from pathlib import Path
    from backend.app.core import amc_prices
    from backend.app.core.amc_study import run_study
    from backend.app.core.amc_manifest import detect_study_folder
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected market lookup')
    monkeypatch.setattr(amc_prices, 'build_marks', forbidden)
    monkeypatch.setattr(amc_prices, 'auto_populate_store', forbidden)
    fixtures = Path(__file__).parent/'fixtures'
    with zipfile.ZipFile(fixtures/'studies_long_only_reference.zip') as archive:
        archive.extractall(tmp_path)
    shutil.copy2(fixtures/'studies_dividends.json', tmp_path/'dividends.json')
    manifest = detect_study_folder(str(tmp_path))['manifest']
    manifest['files']['dividends'] = 'dividends.json'
    manifest['params']['dividends'] = {'status': 'provided', 'treatment': 'cash'}
    result = run_study(manifest, str(tmp_path))
    assert len(result['dividends']['events']) == 480
    assert result['dividends']['totals']['net_income_prod'] == pytest.approx(917678.5284811842)
    assert result['dividends']['totals']['receivable_prod'] == 0
    assert result['block_b']['totals']['reconciliation']['gap_prod'] == 0
    with (tmp_path/'reference/fifo_by_asset.csv').open() as f:
        reference = {r['asset_id']: r for r in csv.DictReader(f)}
    for r in result['block_b']['per_name']:
        assert r['dividends_net'] == pytest.approx(float(reference[r['isin']]['dividends_usd']), abs=.005)
        assert r['total_with_dividends'] == pytest.approx(float(reference[r['isin']]['total_pnl_before_fees_usd']), abs=.005)
    assert result['confidence']['overall_pct'] == 100
