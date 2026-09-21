"""Fund-independent unit cases and frozen six-year independent accounting oracle."""
import csv
import datetime as dt
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.app.core.amc_blocks import _nav_reconciliation, block_b_attribution, block_d_behaviour
from backend.app.core.amc_manifest import detect_study_folder, StudyManifest
from backend.app.core.fifo.engine import reconstruct
from backend.app.core.fifo.schema import Order


def nav(values, dates=None):
    dates = dates or ['2024-01-05', '2024-01-08']
    return [{'date': d, 'nav': v, 'outstanding': 100} for d, v in zip(dates, values)]


@pytest.mark.parametrize('basis,expected', [('previous_nav_act365', 10000*.01*3/365),
    ('current_nav_act365', 11000*.01*3/365), ('previous_nav_act360', 10000*.01*3/360),
    ('current_nav_act360', 11000*.01*3/360), ('nav_252', 21000*.01/252)])
def test_management_conventions(basis, expected):
    result = _nav_reconciliation(nav([100, 110]), 1, '2024-01-08', management_fee_basis=basis)
    assert result['fee_breakdown']['management_fee_prod'] == pytest.approx(-expected, abs=.005)


def test_annual_hwm_reversal_and_partial_cutoff():
    rows = nav([100, 117, 108.5, 95, 110, 117],
        ['2020-01-01', '2020-06-01', '2020-12-31', '2021-12-31', '2022-06-01', '2022-12-30'])
    partial = _nav_reconciliation(rows, 0, '2020-06-01', 15, performance_crystallization='annual')
    assert partial['fee_breakdown']['performance_fee_prod'] == -300
    assert partial['fee_breakdown']['performance_fee_hwm_final'] == 100
    final = _nav_reconciliation(rows, 0, '2022-12-30', 15, performance_crystallization='annual')
    assert final['fee_breakdown']['performance_fee_prod'] == -300
    assert final['fee_breakdown']['performance_fee_hwm_final'] == 117


def test_periodic_fees_reject_flows():
    rows = nav([100, 110])
    rows[-1]['outstanding'] = 101
    with pytest.raises(ValueError, match='égalisation'):
        _nav_reconciliation(rows, 1, '2024-01-08', 15, performance_crystallization='annual')


def test_cash_income_cutoff_no_double_deduction_and_duplicates(tmp_path):
    from backend.app.core.amc_cash_events import load_cash_income
    p = tmp_path/'cash.csv'
    header = 'date,type,asset_id,amount_local,currency,amount_prod\n'
    body = '2024-01-01,DIVIDEND,X,10,EUR,10\n2024-01-02,MANAGEMENT_FEE_PAYMENT,, -3,EUR,-3\n2024-02-01,DIVIDEND,X,20,EUR,20\n'
    p.write_text(header+body)
    assert load_cash_income(str(p), 'EUR', '2024-01-01', '2024-01-31') == 10
    p.write_text(header+body+body.splitlines()[0]+'\n')
    with pytest.raises(ValueError, match='dupliqué'):
        load_cash_income(str(p), 'EUR', '2024-01-01', '2024-01-31')


def test_snapshot_cannot_value_an_earlier_cutoff(tmp_path):
    from backend.app.core.amc_orderbook import load_study_data
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/studies_long_only_reference.zip') as archive:
        archive.extractall(tmp_path)
    manifest = detect_study_folder(str(tmp_path))['manifest']
    with pytest.raises(ValueError, match='même date'):
        load_study_data(str(tmp_path), manifest['files'], as_of='2024-12-31', valuation_source='composition', orders_split_adjusted=True)


@pytest.mark.parametrize('frequency,total', [('monthly', 300), ('quarterly', 150), ('annual', 150)])
def test_crystallization_periods(frequency, total):
    rows = nav([100, 117, 108.5], ['2024-01-01', '2024-01-31', '2024-02-29'])
    result = _nav_reconciliation(rows, 0, '2024-02-29', 15, performance_crystallization=frequency)
    assert result['fee_breakdown']['performance_fee_prod'] == -total


def test_missing_latent_is_not_zero():
    recon = SimpleNamespace(round_trips=[], open_positions=[{'isin': 'X', 'name': 'X', 'ccy': 'USD', 'unreal_pnl_prod': None}])
    result = block_b_attribution(recon, {'components': []}, nav=nav([100, 110]), fifo_as_of='2024-01-08')
    assert result['totals']['unreal_pnl'] is None
    assert result['totals']['total_pnl'] is None
    assert result['per_name'][0]['total_pnl'] is None
    assert 'reconciliation' not in result['totals']


def test_cash_and_zero_results_not_classified_as_losses():
    recon = SimpleNamespace(round_trips=[], open_positions=[])
    result = block_d_behaviour(recon, [], {'components': [{'isin': '', 'name': 'USD', 'weight': .9}]}, 180, 4)
    assert sum(result['conviction_matrix']['counts'].values()) == 0


def test_fifo_roundoff_does_not_create_trades_and_tiny_real_trades_survive():
    def order(i, q):
        return Order(id=str(i), date=dt.date(2024, 1, i), isin='X', name='X', qty=q,
                     price_local=100, price_ccy='USD', fx=1, price_prod=100)
    result = reconstruct([order(1, .1+.2), order(2, -.3), order(3, .1), order(4, -.1)], {}, dt.date(2024, 1, 4), 'USD', recon_mode='strict')
    assert len(result.round_trips) == 2
    assert not result.open_positions
    assert result.total_latent == 0
    tiny = reconstruct([order(1, 1e-12), order(2, -1e-12)], {}, dt.date(2024, 1, 4), 'USD', recon_mode='strict')
    assert len(tiny.round_trips) == 1


def test_saved_manifest_is_used_and_paths_confined(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'product': {'isin': 'TEST', 'currency': 'USD'},
        'files': {}, 'params': {'management_fee_basis': 'previous_nav_act360'}}))
    assert detect_study_folder(str(tmp_path))['manifest']['params']['management_fee_basis'] == 'previous_nav_act360'
    (tmp_path/'manifest.json').write_text(json.dumps({'product': {'isin': 'TEST'}, 'files': {'cash_events': '../escape.csv'}}))
    with pytest.raises(ValueError, match='appartenir'):
        detect_study_folder(str(tmp_path))


def test_six_year_reference_end_to_end(tmp_path, monkeypatch):
    from backend.app.core.amc_study import run_study
    from backend.app.core import amc_prices
    def forbidden(*args, **kwargs):
        raise AssertionError('No external prices are needed for snapshot valuation')
    monkeypatch.setattr(amc_prices, 'auto_populate_store', forbidden)
    monkeypatch.setattr(amc_prices, 'build_marks', forbidden)
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/studies_long_only_reference.zip') as archive:
        archive.extractall(tmp_path)
    manifest = StudyManifest.model_validate(detect_study_folder(str(tmp_path))['manifest'])
    result = run_study(manifest.model_dump(), str(tmp_path))
    expected = json.loads((tmp_path/'reference/summary.json').read_text())
    b = result['block_b']['totals']
    assert b['realized_pnl'] == pytest.approx(3777696.128121476, abs=.005)
    assert b['unreal_pnl'] == pytest.approx(567572.093733965, abs=.005)
    assert abs(b['reconciliation']['gap_prod']) <= .02
    assert b['reconciliation']['cash_income_prod'] == pytest.approx(expected['dividends_usd'])
    for kind in ['management', 'performance', 'transaction']:
        field = kind+'_expense_usd' if kind != 'transaction' else 'transaction_cost_usd'
        assert b['reconciliation']['fee_breakdown'][kind+'_fee_prod' if kind != 'transaction' else 'transaction_cost_prod'] == pytest.approx(-expected[field], abs=.005)
    c = result['block_c']['round_trips']
    assert c['count'] == 1341
    assert c['win_rate_pct'] == 59.1
    assert c['median_holding_days'] == 151
    assert c['profit_factor'] == 1.72
    d = result['block_d']
    assert d['holding_distribution']['long_term_count'] + d['holding_distribution']['tactical_count'] == 1341
    assert sum(d['conviction_matrix']['counts'].values()) == 20
    assert result['data_quality']['status'] == 'ready'
